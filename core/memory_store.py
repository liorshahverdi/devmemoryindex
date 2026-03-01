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

_STOPWORDS = {
    "a", "an", "the", "is", "in", "on", "at", "to", "for", "of", "and",
    "or", "where", "what", "how", "why", "when", "i", "me", "my", "it",
    "this", "that", "with", "from", "by", "be", "was", "are", "do", "did",
    "does", "not", "no", "can", "could", "would", "should", "have", "has",
    "had", "are", "there", "any", "which", "who", "its", "as", "if",
}


def _keyword_where(query: str) -> str:
    """Build a keyword WHERE clause from individual meaningful query terms.

    Splits the query into words, drops stopwords and short tokens, and returns
    a SQL OR chain matching summary or raw_text for each term (capped at 6).
    Falls back to a full-phrase match for very short queries (one meaningful term).
    """
    import re
    words = re.findall(r"\w+", query.lower())
    terms = [w for w in words if w not in _STOPWORDS and len(w) >= 3]

    if not terms:
        safe = query.lower().replace("'", "''")
        return f"LOWER(summary) LIKE '%{safe}%' OR LOWER(raw_text) LIKE '%{safe}%'"

    # Deduplicate while preserving order, cap to avoid huge WHERE clauses.
    seen: set[str] = set()
    unique_terms: list[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)
    unique_terms = unique_terms[:6]

    parts = []
    for term in unique_terms:
        safe = term.replace("'", "''")  # terms are already lowercased
        parts.append(f"LOWER(summary) LIKE '%{safe}%' OR LOWER(raw_text) LIKE '%{safe}%'")
    return " OR ".join(parts)


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
        self.collection.add([self._to_record(memory, vector)])
        _context_cache.invalidate()  # new memory may change context results
        return True

    def add_batch(self, memories: list[Memory], vectors: list[list]) -> int:
        """Insert multiple memories in a single DB write. Returns count added.

        Performs one batch exists-check and one collection.add() call, which is
        dramatically faster than calling add() N times (avoids N separate Lance
        fragment writes). Duplicates are silently skipped.
        """
        if not memories:
            return 0
        ids = [m.id for m in memories]
        existing = self._batch_existing_ids(ids)
        records = [
            self._to_record(m, v)
            for m, v in zip(memories, vectors)
            if m.id not in existing
        ]
        if not records:
            return 0
        self.collection.add(records)
        _context_cache.invalidate()
        return len(records)

    def _to_record(self, memory: Memory, vector: list) -> dict:
        return {
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
        }

    def _batch_existing_ids(self, ids: list[str]) -> set[str]:
        """Return the subset of ids already in the store (single WHERE IN query)."""
        if not ids:
            return set()
        try:
            escaped = "', '".join(i.replace("'", "''") for i in ids)
            results = (
                self.collection
                .search()
                .where(f"id IN ('{escaped}')")
                .limit(len(ids))
                .to_list()
            )
            return {r["id"] for r in results}
        except Exception:
            return set()

    def exists(self, memory_id: str) -> bool:
        safe_id = memory_id.replace("'", "''")
        try:
            results = (
                self.collection
                .search()
                .where(f"id = '{safe_id}'")
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
        """Passively boost importance of a retrieved memory, capped at 0.8.

        Called automatically after search hits and get_by_id(). Not intended
        for explicit agent feedback — use boost_importance() for that (cap 0.95).
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
                return
            new_importance = min(0.8, results[0].get("importance", 0.5) + boost)
            self.collection.update(
                where=f"id = '{safe_id}'",
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
        speaker_filter: str | None = None,
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

        # 2. Keyword search — catch exact term matches semantic may miss.
        # Use individual meaningful terms rather than the full query string so
        # natural-language questions ("where is buffer playback in the code")
        # still match memories containing "buffer" or "playback".
        kw_where = _keyword_where(query)
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
        # Keyword hits get a synthetic distance based on term-match ratio:
        # a memory matching all query terms gets distance=0.0 (perfect),
        # one matching only 1 of 3 terms gets distance=0.67.
        # This prevents the common failure where a generic term like "connector"
        # causes many loosely-related memories to tie at distance=0.0 and then
        # sort purely by recency, burying the specific commit that matches all terms.
        import re as _re
        _query_terms = [
            w for w in _re.findall(r"\w+", query.lower())
            if w not in _STOPWORDS and len(w) >= 3
        ][:6]

        def _term_match_distance(memory: dict) -> float:
            if not _query_terms:
                return 0.0
            summary_text = (memory.get("summary") or "").lower()
            raw_text = (memory.get("raw_text") or "").lower()
            # Summary hits count 2×: a term in the summary is a primary signal
            # (definition, filename) vs a secondary signal (import, passing reference).
            # This lets definition files outrank files that merely import the same class.
            score = 0
            for t in _query_terms:
                if t in summary_text:
                    score += 2
                elif t in raw_text:
                    score += 1
            max_score = len(_query_terms) * 2
            return max(0.0, 1.0 - score / max_score)

        keyword_ids = {r["id"] for r in keyword_results}
        combined = {r["id"]: r for r in semantic_results}
        for r in keyword_results:
            if r["id"] not in combined:
                combined[r["id"]] = r

        # Speaker filter: applied after merge, before scoring.
        # Matches memories with the tag "speaker:<speaker_filter_lowercase>".
        if speaker_filter:
            tag_to_find = f"speaker:{speaker_filter.lower()}"
            combined = {
                k: v for k, v in combined.items()
                if tag_to_find in (v.get("tags") or [])
            }

        for r in combined.values():
            if r["id"] in keyword_ids:
                kw_dist = _term_match_distance(r)
                # Only override if keyword match gives a better (lower) distance
                # than the semantic result's own distance.
                if kw_dist < r.get("_distance", 1.0):
                    r["_distance"] = kw_dist

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

    def update(
        self,
        memory_id: str,
        summary: str | None = None,
        raw_text: str | None = None,
        importance: float | None = None,
    ) -> bool:
        """Update an existing memory's fields in-place.

        Re-embeds and replaces the vector when summary or raw_text changes
        (requires delete + re-add). Preserves times_retrieved and times_accessed.
        Returns False if memory_id is not found.
        """
        record = self.get_by_id(memory_id, reinforce=False)
        if record is None:
            return False

        new_summary = (summary.strip()[:200] if summary else record.get("summary", ""))
        new_raw = raw_text if raw_text is not None else record.get("raw_text", "")
        new_importance = importance if importance is not None else record.get("importance", 0.5)
        text_changed = summary is not None or raw_text is not None

        if text_changed:
            from core.embeddings import embed
            new_vector = embed(new_summary)
            self.delete(memory_id)
            self.collection.add([{
                "id": memory_id,
                "type": record.get("type", "agent_solution"),
                "summary": new_summary,
                "raw_text": new_raw,
                "source": record.get("source", "mcp_agent"),
                "repo": record.get("repo"),
                "timestamp": record.get("timestamp"),
                "tags": record.get("tags", []),
                "importance": new_importance,
                "vector": new_vector,
                "times_retrieved": record.get("times_retrieved", 0) or 0,
                "times_accessed": record.get("times_accessed", 0) or 0,
            }])
        else:
            self.collection.update(
                where=f"id = '{memory_id}'",
                values={"importance": new_importance},
            )

        _context_cache.invalidate()
        return True

    def boost_importance(self, memory_id: str, amount: float = 0.05, cap: float = 0.95) -> float | None:
        """Explicitly boost importance by amount up to cap.

        Returns new importance value, or None if memory_id is not found.
        """
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
                return None
            new_val = min(cap, (results[0].get("importance") or 0.5) + amount)
            self.collection.update(
                where=f"id = '{safe_id}'",
                values={"importance": new_val},
            )
            return new_val
        except Exception:
            return None

    def delete(self, memory_id: str):
        safe_id = memory_id.replace("'", "''")
        self.collection.delete(f"id = '{safe_id}'")

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