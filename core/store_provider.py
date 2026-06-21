from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.memory_store import MemoryStore

_store: "MemoryStore | None" = None


def get_store(db_path: str = "./memory_db") -> "MemoryStore":
    """Return the process-global memory store, loading DB deps lazily."""
    global _store
    if _store is None:
        try:
            from core.memory_store import MemoryStore
        except ModuleNotFoundError as exc:
            missing = exc.name or "required database dependency"
            raise RuntimeError(
                f"DevMemory's persistent store requires {missing}, but it is not installed. "
                "Install the full CLI dependencies with: uv pip install -e '.[mcp]' "
                "or pip install -e '.[mcp]'."
            ) from exc
        _store = MemoryStore(db_path)
    return _store