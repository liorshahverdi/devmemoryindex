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
])

class MemoryStore:
    def __init__(self, db_path="./memory_db"):
        self.db = lancedb.connect(db_path)
        self.collection = self._init_table()

    def _init_table(self):
        return self.db.create_table("memories", schema=_schema, exist_ok=True)
    
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
            "vector": vector
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

        ranked = sorted(scored, key=lambda r: r["_score"], reverse=True)

        top = ranked[:k]

        # 5. Attach related memory IDs — nearest neighbours from the semantic
        #    pool that didn't make it into top-k. No extra search calls needed.
        top_ids = {r["id"] for r in top}
        related_pool = [r for r in semantic_results if r["id"] not in top_ids]
        for r in top:
            r["related"] = [n["id"] for n in related_pool[:3]]

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
            return results[0]
        except Exception:
            return None

    def delete(self, memory_id: str):
        self.collection.delete(f"id = '{memory_id}'")

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