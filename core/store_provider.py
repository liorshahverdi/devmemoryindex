from core.memory_store import MemoryStore

_store: MemoryStore | None = None

def get_store(db_path: str = "./memory_db") -> MemoryStore:
    global _store
    if _store is None:
        _store = MemoryStore(db_path)
    return _store