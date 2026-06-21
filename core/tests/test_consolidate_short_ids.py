"""Regression tests for memory consolidation behavior."""

from datetime import datetime

from core.memory_store import MemoryStore
from core.schema import Memory


_FAKE_VECTOR = [0.0] * 384


def _add_memory(store: MemoryStore, memory_id: str, summary: str) -> None:
    store.add(
        Memory(
            id=memory_id,
            type="agent_solution",
            summary=summary,
            raw_text=f"Full text for {summary}",
            source="test",
            repo="devmemoryindex",
            timestamp=datetime.utcnow(),
            tags=["qa"],
            importance=0.7,
        ),
        _FAKE_VECTOR,
    )


def test_consolidate_accepts_unique_short_id_prefixes(tmp_path, monkeypatch):
    """Search displays short IDs; consolidate should accept the same unique prefixes."""
    store = MemoryStore(db_path=str(tmp_path / "db"))
    first_id = "a6f37596" + "1" * 56
    second_id = "621bbfb6" + "2" * 56
    _add_memory(store, first_id, "First duplicate memory")
    _add_memory(store, second_id, "Second duplicate memory")

    monkeypatch.setattr("core.memory_store.embed", lambda _text: _FAKE_VECTOR, raising=False)

    result = store.consolidate([first_id[:8], second_id[:8]])

    assert result["status"] == "ok"
    assert result["deleted"] == 2
    assert store.get_by_id(first_id, reinforce=False) is None
    assert store.get_by_id(second_id, reinforce=False) is None
    assert store.get_by_id(result["new_id"], reinforce=False) is not None
