from datetime import datetime

from core.memory_store import MemoryStore
from core.schema import Memory


def _mem(memory_id: str, summary: str, raw_text: str = "", repo: str = "devmemoryindex") -> Memory:
    return Memory(
        id=memory_id,
        type="agent_solution",
        summary=summary,
        raw_text=raw_text or summary,
        source="test",
        repo=repo,
        timestamp=datetime.utcnow(),
        tags=[],
        importance=0.8,
    )


def test_text_search_finds_relevant_memories_without_embedding(tmp_path):
    store = MemoryStore(db_path=str(tmp_path))
    store.add(_mem("text-1", "CLI QA fixes for base installs", "lazy imports avoid lancedb numpy failures"), [0.0] * 384)
    store.add(_mem("text-2", "Docker install notes", "apt install docker"), [0.0] * 384)

    results = store.text_search("CLI QA base installs optional dependencies", k=3, repo_filter="devmemoryindex")

    assert [r["id"] for r in results] == ["text-1"]


def test_hybrid_search_does_not_update_retrieval_counters_by_default(tmp_path):
    store = MemoryStore(db_path=str(tmp_path))
    store.add(_mem("counter-1", "CLI QA fixes for base installs"), [0.0] * 384)

    result = store.hybrid_search("CLI QA base installs", [0.0] * 384, k=1)
    fetched = store.get_by_id("counter-1", reinforce=False)

    assert result[0]["id"] == "counter-1"
    assert fetched["times_retrieved"] == 0


def test_hybrid_search_can_update_retrieval_counters_when_requested(tmp_path):
    store = MemoryStore(db_path=str(tmp_path))
    store.add(_mem("counter-2", "CLI QA fixes for base installs"), [0.0] * 384)

    store.hybrid_search("CLI QA base installs", [0.0] * 384, k=1, update_counters=True)
    fetched = store.get_by_id("counter-2", reinforce=False)

    assert fetched["times_retrieved"] == 1
