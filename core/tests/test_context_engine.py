"""
Tests for ContextEngine.build():
1. Build context for a known query — output contains expected memories.
2. Token budget respected — truncates when max_tokens is tight.
3. Repo filter — only memories from the specified repo appear.
4. Format modes — "raw", "claude", "markdown" each produce valid output.
"""

import pytest
from datetime import datetime, timedelta

from core.memory_store import MemoryStore
from core.context_engine import ContextEngine
from core.schema import Memory
from core.embeddings import embed


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path))


@pytest.fixture
def engine(store):
    return ContextEngine(store)


def _make_memory(
    id: str,
    summary: str,
    repo: str = "test-repo",
    importance: float = 0.5,
    hours_ago: float = 0,
) -> Memory:
    return Memory(
        id=id,
        type="agent_solution",
        summary=summary,
        raw_text=summary,
        source="test",
        repo=repo,
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
        tags=[],
        importance=importance,
    )


# ── Tests ─────────────────────────────────────────────────────────────


def test_build_context_contains_expected_memory(store, engine):
    """
    Inserting a memory whose summary matches the query should make it
    appear in the 'memories' list returned by build().
    """
    mem = _make_memory("ctx-1", "Redis connection pool timeout fix", importance=0.9)
    store.add(mem, embed(mem.summary))

    result = engine.build("Redis timeout")

    assert result["query"] == "Redis timeout"
    assert result["memory_count"] >= 1
    ids = [m["id"] for m in result["memories"]]
    assert "ctx-1" in ids, "Expected memory should appear in context output"
    assert isinstance(result["context_text"], str)
    assert len(result["context_text"]) > 0


def test_token_budget_truncates_results(store, engine):
    """
    When max_tokens is very small, build() must return fewer memories
    than the total inserted — proving the budget is enforced.
    """
    # Insert 20 memories, each summary ~10 words (~10 tokens each + 20 overhead = ~30/each)
    for i in range(20):
        mem = _make_memory(
            f"tok-{i}",
            f"background job queue processing worker timeout fix number {i}",
            importance=0.5,
        )
        store.add(mem, embed(mem.summary))

    # Budget of 100 tokens can fit at most ~3 memories (30 tokens each)
    result = engine.build("background job", max_tokens=100, max_memories=20)

    assert result["memory_count"] < 20, (
        "Token budget should truncate results well below the total inserted"
    )
    assert result["token_estimate"] <= 100, (
        "Reported token estimate must not exceed the budget"
    )


def test_repo_filter_excludes_other_repos(store, engine):
    """
    When repo= is provided, only memories from that repo should appear.
    """
    mem_a = _make_memory("repo-a", "Celery task retry with exponential backoff", repo="proj-alpha", importance=0.8)
    mem_b = _make_memory("repo-b", "Celery beat scheduler cron job setup", repo="proj-beta", importance=0.8)

    store.add(mem_a, embed(mem_a.summary))
    store.add(mem_b, embed(mem_b.summary))

    result = engine.build("Celery", repo="proj-alpha")

    repos = [m.get("repo") for m in result["memories"]]
    assert all(r == "proj-alpha" for r in repos), (
        "All returned memories must belong to the filtered repo"
    )
    ids = [m["id"] for m in result["memories"]]
    assert "repo-b" not in ids, "Memory from excluded repo must not appear"


def test_repo_filter_is_passed_to_hybrid_search(store, engine, monkeypatch):
    """
    Repo filtering must happen inside the store query, not only after global
    over-retrieval, otherwise relevant repo-local memories can be missed.
    """
    captured = {}

    def fake_hybrid_search(query, vector, k=5, type_filter=None, repo_filter=None, speaker_filter=None):
        captured["repo_filter"] = repo_filter
        return []

    monkeypatch.setattr(store, "hybrid_search", fake_hybrid_search)

    engine.build("repo filter pass-through unique", vector=[0.0] * 384, repo="proj-alpha")

    assert captured["repo_filter"] == "proj-alpha"


def test_format_modes_produce_valid_output(store, engine):
    """
    Each format mode ('raw', 'claude', 'markdown') must produce a non-empty
    string with the expected structural markers.
    """
    mem = _make_memory("fmt-1", "Kubernetes pod OOMKilled memory limit increase", importance=0.9)
    store.add(mem, embed(mem.summary))

    raw = engine.build("Kubernetes", format="raw")
    assert "Kubernetes" in raw["context_text"]
    assert "<context>" not in raw["context_text"]

    claude = engine.build("Kubernetes", format="claude")
    assert claude["context_text"].startswith("<context>")
    assert claude["context_text"].endswith("</context>")
    assert "Kubernetes" in claude["context_text"]

    markdown = engine.build("Kubernetes", format="markdown")
    assert "### Relevant Past Solutions" in markdown["context_text"]
    assert "Kubernetes" in markdown["context_text"]
