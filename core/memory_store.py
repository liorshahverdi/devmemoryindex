import lancedb
import pyarrow as pa
from core.schema import Memory
from core.ranking import compute_score
from core.context_cache import cache as _context_cache

VECTOR_DIM = 384
_schema = pa.schema([
    pa.field("id", pa.string()),
    pa.field("type", pa.string()),
    pa.field("summary", pa.string()),
    pa.field("raw_text", pa.string()),
    pa.field("source", pa.string()),
    pa.field("repo", pa.string()),
    pa.field("timestamp", pa.timestamp("us")),
    pa.field("tags", pa.list_(pa.string())),
    pa.field("importance", pa.float64()),
    pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
    pa.field("times_retrieved", pa.int64()),
    pa.field("times_accessed", pa.int64()),
])

class MemoryStore:
    def __init__(self, db_path="./memory_db"):
        self.db = lancedb.connect(db_path)
        self.collection = self._init_table()

    def _init_table(self):
        # Open existing table without schema re-validation to allow migrations.
        # Create with full schema only for brand-new stores.
        if "memories" in self.db.table_names():
            table = self.db.open_table("memories")
        else:
            table = self.db.create_table("memories", schema=_schema)
        # Schema migration: add counter columns for stores created before I4
        existing = {f.name for f in table.schema}
        missing = {}
        if "times_retrieved" not in existing:
            missing["times_retrieved"] = "cast(0 as bigint)"
        if "times_accessed" not in existing:
            missing["times_accessed"] = "cast(0 as bigint)"
        if missing:
            try:
                table.add_columns(missing)
            except Exception:
                pass  # non-critical — counters default to 0 on read

        # Self-healing scan check: Lance 2.0.0 has a bug where add_columns
        # fills old fragments lazily, but once newer fragments have physical
        # counter values the mixed state causes a non-nullable null panic.
        # drop_columns is metadata-only (no scan), so we can safely drop and
        # re-add to put all fragments back into a consistent lazy-expression
        # state. Only runs when a scan actually fails.
        try:
            self.db.open_table("memories").search().limit(1).to_list()
        except Exception:
            counter_cols = ["times_retrieved", "times_accessed"]
            present = [c for c in counter_cols if c in {f.name for f in table.schema}]
            if present:
                try:
                    table.drop_columns(present)
                except Exception:
                    pass
            try:
                table.add_columns({c: "cast(0 as bigint)" for c in counter_cols})
            except Exception:
                pass
        return table
    
    def add(self, memory: Memory, vector: list) -> bool:
        """Insert a memory. Returns False (no-op) if the id already exists."""
        if self.exists(memory.id):
            return False
        self.collection.add([{
            "id": memory.id,
            "type": memory.type,
            "summary": memory.summary,
            "raw_text": memory.raw_text,
            "source": memory.source,
            "repo": memory.repo,
            "timestamp": memory.timestamp,
            "tags": memory.tags,
            "importance": memory.importance,
            "vector": vector,
            "times_retrieved": 0,
            "times_accessed": 0,
        }])
        _context_cache.invalidate()  # new memory may change context results
        return True

    def exists(self, memory_id: str) -> bool:
        try:
            results = (
                self.collection
                .search()
                .where(f"id = '{memory_id}'")
                .limit(1)
                .to_list()
            )
            return len(results) > 0
        except Exception:
            return False

    def _increment_counter(self, memory_id: str, column: str) -> None:
        """Increment times_retrieved or times_accessed by 1. Best-effort, never raises."""
        try:
            safe_id = memory_id.replace("'", "''")
            results = (
                self.collection
                .search()
                .where(f"id = '{safe_id}'")
                .limit(1)
                .to_list()
            )
            if not results:
                return
            new_val = (results[0].get(column) or 0) + 1
            self.collection.update(
                where=f"id = '{safe_id}'",
                values={column: new_val},
            )
        except Exception:
            pass

    def reinforce(self, memory_id: str, boost: float = 0.05) -> None:
        """Boost importance of a retrieved memory (cap at 1.0). Called after search hits."""
        try:
            results = (
                self.collection
                .search()
                .where(f"id = '{memory_id}'")
                .limit(1)
                .to_list()
            )
            if not results:
                return
            new_importance = min(0.8, results[0].get("importance", 0.5) + boost)
            self.collection.update(
                where=f"id = '{memory_id}'",
                values={"importance": new_importance},
            )
        except Exception:
            pass  # Non-critical

    def semantic_search(self, vector: list, k: int = 5) -> list:
        return self.collection.search(vector).limit(k).to_list()

    def hybrid_search(
        self,
        query: str,
        vector: list,
        k: int = 5,
        type_filter: str | None = None,
        repo_filter: str | None = None,
    ) -> list:
        # Build optional WHERE clause applied at the DB level so filters
        # don't silently exclude results after the k-cap is already applied.
        conditions: list[str] = []
        if type_filter:
            safe_type = type_filter.replace("'", "''")
            # Use prefix match so "meeting" finds "meeting_transcript",
            # "copilot" finds "copilot_chat", etc.
            conditions.append(f"type LIKE '{safe_type}%'")
        if repo_filter:
            safe_repo = repo_filter.replace("'", "''")
            conditions.append(f"repo = '{safe_repo}'")
        where_clause = " AND ".join(conditions) if conditions else None

        # 1. Semantic search — over-retrieve
        sem_q = self.collection.search(vector).limit(50)
        if where_clause:
            sem_q = sem_q.where(where_clause)
        semantic_results = sem_q.to_list()

        # 2. Keyword search — catch exact term matches semantic may miss
        safe_query = query.replace("'", "''")
        kw_where = f"summary LIKE '%{safe_query}%' OR raw_text LIKE '%{safe_query}%'"
        if where_clause:
            kw_where = f"({kw_where}) AND {where_clause}"
        try:
            keyword_results = (
                self.collection
                .search()
                .where(kw_where)
                .limit(50)
                .to_list()
            )
        except Exception:
            keyword_results = []

        # 3. Merge and deduplicate by id
        # Semantic results carry _distance from vector search.
        # Keyword results contain the exact query term — they should rank high
        # regardless of their embedding distance. Set _distance=0.0 for all
        # keyword matches (both keyword-only and those already in semantic pool)
        # so that an exact text match always gets maximum semantic score.
        keyword_ids = {r["id"] for r in keyword_results}
        combined = {r["id"]: r for r in semantic_results}
        for r in keyword_results:
            if r["id"] not in combined:
                combined[r["id"]] = r
        for r in combined.values():
            if r["id"] in keyword_ids:
                r["_distance"] = 0.0

        # 4. Score and rank
        scored = list(combined.values())
        for r in scored:
            r["_score"] = compute_score(r)

        # Deprioritize failure_note results unless the query signals negative intent.
        _NEGATIVE_KEYWORDS = {
            "avoid", "failed", "broken", "didn't work", "not work",
            "mistake", "wrong", "don't", "shouldn't", "error", "bug",
        }
        query_lower = query.lower()
        negative_intent = any(kw in query_lower for kw in _NEGATIVE_KEYWORDS)
        if not negative_intent:
            for r in scored:
                if r.get("type") == "failure_note":
                    r["_score"] *= 0.4

        # CTR dampening (I4): memories retrieved often but rarely accessed are likely
        # low-signal. Apply a soft penalty when click-through rate < 10% with enough
        # data (>= 5 retrievals) to avoid penalising brand-new memories.
        for r in scored:
            retrieved = r.get("times_retrieved", 0) or 0
            accessed = r.get("times_accessed", 0) or 0
            if retrieved >= 5 and (accessed / retrieved) < 0.1:
                r["_score"] *= 0.8

        ranked = sorted(scored, key=lambda r: r["_score"], reverse=True)

        top = ranked[:k]

        # 5. Attach related memory IDs — nearest neighbours from the semantic
        #    pool that didn't make it into top-k. No extra search calls needed.
        top_ids = {r["id"] for r in top}
        related_pool = [r for r in semantic_results if r["id"] not in top_ids]
        for r in top:
            r["related"] = [n["id"] for n in related_pool[:3]]

        # 6. Increment times_retrieved for all top results (best-effort).
        for r in top:
            self._increment_counter(r["id"], "times_retrieved")

        return top

    def get_by_id(self, memory_id: str, reinforce: bool = True) -> dict | None:
        """Fetch a single memory by exact ID.

        Reinforces importance by a small amount when reinforce=True (default) —
        an explicit fetch is a strong signal that this memory is useful.
        Returns None if not found.
        """
        safe_id = memory_id.replace("'", "''")
        try:
            results = (
                self.collection
                .search()
                .where(f"id = '{safe_id}'")
                .limit(1)
                .to_list()
            )
            if not results:
                return None
            if reinforce:
                self.reinforce(memory_id, boost=0.02)
                self._increment_counter(memory_id, "times_accessed")
            return results[0]
        except Exception:
            return None

    def delete(self, memory_id: str):
        self.collection.delete(f"id = '{memory_id}'")

    def summary_quality(self) -> dict:
        """Return summary length distribution and IDs of short-summary memories.

        A summary under 20 characters is flagged as low-quality — too short to
        reliably match future search queries.
        """
        records = self.get_all()
        lengths = [len(r.get("summary") or "") for r in records]
        short = [
            {"id": r["id"][:8], "summary": r.get("summary", ""), "type": r.get("type", "")}
            for r in records
            if len(r.get("summary") or "") < 20
        ]
        buckets = {"<20": 0, "20-50": 0, "51-100": 0, "101-200": 0, ">200": 0}
        for l in lengths:
            if l < 20:
                buckets["<20"] += 1
            elif l <= 50:
                buckets["20-50"] += 1
            elif l <= 100:
                buckets["51-100"] += 1
            elif l <= 200:
                buckets["101-200"] += 1
            else:
                buckets[">200"] += 1
        avg = sum(lengths) / len(lengths) if lengths else 0
        return {"total": len(records), "avg_length": round(avg, 1), "buckets": buckets, "short": short}

    def engagement_report(self, min_retrievals: int = 5) -> dict:
        """Return retrieval-to-access click-through rates per memory.

        Memories with >= min_retrievals but CTR < 10% are flagged as low-engagement
        candidates for pruning or summary improvement.
        """
        records = self.get_all()
        low_ctr = []
        high_ctr = []
        untracked = 0
        for r in records:
            retrieved = r.get("times_retrieved", 0) or 0
            accessed = r.get("times_accessed", 0) or 0
            if retrieved < min_retrievals:
                untracked += 1
                continue
            ctr = accessed / retrieved
            entry = {
                "id": r["id"][:8],
                "summary": r.get("summary", "")[:80],
                "type": r.get("type", ""),
                "times_retrieved": retrieved,
                "times_accessed": accessed,
                "ctr": round(ctr, 3),
            }
            if ctr < 0.1:
                low_ctr.append(entry)
            else:
                high_ctr.append(entry)
        low_ctr.sort(key=lambda x: x["times_retrieved"], reverse=True)
        high_ctr.sort(key=lambda x: x["ctr"], reverse=True)
        return {
            "total": len(records),
            "untracked": untracked,
            "low_ctr": low_ctr,
            "high_ctr": high_ctr,
        }

    def count(self) -> int:
        return self.collection.count_rows()

    def get_all(self) -> list:
        return self.collection.to_arrow().to_pylist()

    def truncate(self, dry_run: bool = True, filter_repo: str | None = None) -> int:
        """Remove records from the store.

        - If `filter_repo` is provided, only records whose `repo` equals that value
          will be removed.
        - By default this is a dry-run and returns the number of records that
          would be deleted. Set `dry_run=False` to actually perform deletions.
        """
        all_records = self.get_all()
        to_delete = []
        for r in all_records:
            if filter_repo is not None and r.get("repo") != filter_repo:
                continue
            to_delete.append(r["id"])

        if dry_run:
            return len(to_delete)

        deleted = 0
        for mem_id in to_delete:
            try:
                self.delete(mem_id)
                deleted += 1
            except Exception:
                # keep going on errors to avoid partial failures blocking the whole operation
                pass

        return deleted