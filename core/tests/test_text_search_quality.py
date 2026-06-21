from datetime import datetime

from core.memory_store import MemoryStore
from core.schema import Memory


def _mem(memory_id: str, summary: str, raw_text: str, repo: str) -> Memory:
    return Memory(
        id=memory_id,
        type="git_commit",
        summary=summary,
        raw_text=raw_text,
        source="test",
        repo=repo,
        timestamp=datetime.utcnow(),
        tags=[],
        importance=0.9,
    )


def test_text_search_filters_single_term_noise_for_multi_term_queries(tmp_path):
    store = MemoryStore(db_path=str(tmp_path))
    store.add(_mem("good", "fix: address CLI QA findings", "base installs optional dependencies", "devmemoryindex"), [0.0] * 384)
    store.add(_mem("noise", "fix: cache precision", "cache dependency update", "other"), [0.0] * 384)

    results = store.text_search("CLI QA base installs optional dependencies", k=5)

    assert [r["id"] for r in results] == ["good"]
