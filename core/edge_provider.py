from core.edge_store import EdgeStore

_edges: EdgeStore | None = None


def get_edges(db_path: str = "./memory_db") -> EdgeStore:
    global _edges
    if _edges is None:
        _edges = EdgeStore(db_path)
    return _edges
