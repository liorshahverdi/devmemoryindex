import lancedb
import pyarrow as pa
from core.schema import Memory

VECTOR_DIM = 384

db = lancedb.connect("./memory_db")

_schema = pa.schema([
    pa.field("id", pa.string()),
    pa.field("type", pa.string()),
    pa.field("summary", pa.string()),
    pa.field("raw_text", pa.string()),
    pa.field("source", pa.string()),
    pa.field("repo", pa.string()),
    pa.field("timestamp", pa.string()),
    pa.field("tags", pa.list_(pa.string())),
    pa.field("importance", pa.float64()),
    pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
])
collection = db.create_table("memories", schema=_schema, exist_ok=True)

def _get_collection(col=None):
    return col if col is not None else collection

def save_memory(memory: Memory, vector: list, collection=None):
    _get_collection(collection).add([{
        "id": memory.id,
        "type": memory.type,
        "summary": memory.summary,
        "raw_text": memory.raw_text,
        "source": memory.source,
        "repo": memory.repo,
        "timestamp": str(memory.timestamp),
        "tags": memory.tags,
        "importance": memory.importance,
        "vector": vector
    }])

def search_memory(query_vector: list, n_results: int = 5, collection=None):
    return _get_collection(collection).search(query_vector).limit(n_results).to_list()