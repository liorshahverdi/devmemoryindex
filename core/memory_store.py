import lancedb
import pyarrow as pa
from core.schema import Memory
from core.ranking import compute_score

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
    
    def add(self, memory: Memory, vector: list):
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
            new_importance = min(1.0, results[0].get("importance", 0.5) + boost)
            self.collection.update(
                where=f"id = '{memory_id}'",
                values={"importance": new_importance},
            )
        except Exception:
            pass  # Non-critical

    def semantic_search(self, vector: list, k: int = 5) -> list:
        results = self.collection.search(vector).limit(k).to_list()
        for r in results:
            self.reinforce(r["id"], boost=0.05)
        return results

    def hybrid_search(self, query: str, vector: list, k: int = 5) -> list:
        # 1. Semantic search — over-retrieve
        semantic_results = self.collection.search(vector).limit(50).to_list()

        # 2. Keyword search — catch exact term matches semantic may miss
        safe_query = query.replace("'", "''")
        try:
            keyword_results = (
                self.collection
                .search()
                .where(f"summary LIKE '%{safe_query}%'")
                .limit(50)
                .to_list()
            )
        except Exception:
            keyword_results = []

        # 3. Merge and deduplicate by id
        combined = {r["id"]: r for r in semantic_results}
        for r in keyword_results:
            if r["id"] not in combined:
                combined[r["id"]] = r

        # 4. Score and rank
        ranked = sorted(combined.values(), key=compute_score, reverse=True)

        # 5. Reinforce retrieved memories (access-aware importance)
        for r in ranked[:k]:
            self.reinforce(r["id"], boost=0.05)

        return ranked[:k]

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