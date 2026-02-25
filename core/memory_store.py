import lancedb
import pyarrow as pa
from core.schema import Memory

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

    def semantic_search(self, vector: list, k: int = 5) -> list:
        return self.collection.search(vector).limit(k).to_list()
    
    def delete(self, memory_id: str):
        self.collection.delete(f"id = '{memory_id}'")

    def count(self) -> int:
        return self.collection.count_rows()
    
    def get_all(self) -> list:
        """
        Returns all memories as a list of dicts.
        For debugging use.
        """
        return self.collection.to_pandas().to_dict(orient="records")