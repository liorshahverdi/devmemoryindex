"""
Tests for MemoryStore.hybrid_search():
- Keyword matches surface even with mediocre embedding similarity.
- Deduplication: same memory from semantic + keyword paths appears only once.
- hybrid_search() returns better results than semantic_search() alone.
"""

import pytest
from datetime import datetime, timedelta
from core.memory_store import MemoryStore, VECTOR_DIM
from core.schema import Memory
from core.embeddings import embed


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path))


def _make_memory(id: str, summary: str, raw_text: str = "",
                 importance: float = 0.5, tags: list = None,
                 hours_ago: float = 0) -> Memory:
    return Memory(
        id=id,
        type="agent_solution",
        summary=summary,
        raw_text=raw_text or summary,
        source="test",
        repo="test-repo",
        timestamp=datetime.utcnow() - timedelta(hours=hours_ago),
        tags=tags or [],
        importance=importance,
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _distant_vector():
    """A vector far from any real text embedding — simulates mediocre similarity."""
    v = [0.0] * VECTOR_DIM
    v[0] = 1.0  # single hot-dimension, unlike any natural sentence embedding
    return v


# ── Tests ────────────────────────────────────────────────────────────


def test_keyword_match_surfaces_despite_weak_embedding(store):
    """
    A memory whose summary contains the query keyword should appear in
    hybrid_search results even when its embedding vector is far from the
    query vector (i.e. semantic similarity alone would rank it low).
    """
    # Memory 1: strong embedding match, does NOT mention "Celery"
    good_embed_mem = _make_memory(
        "sem-hit", "Background task queue processing with workers",
        importance=0.5,
    )
    good_embed_vec = embed("Background task queue processing with workers")

    # Memory 2: weak embedding match (distant vector), but summary contains "Celery"
    keyword_mem = _make_memory(
        "kw-hit", "Celery worker timeout fix for long-running tasks",
        importance=0.7,
    )
    keyword_vec = _distant_vector()

    store.add(good_embed_mem, good_embed_vec)
    store.add(keyword_mem, keyword_vec)

    # Query specifically about "Celery"
    query = "Celery"
    query_vec = embed(query)

    results = store.hybrid_search(query, query_vec, k=5)
    result_ids = [r["id"] for r in results]

    assert "kw-hit" in result_ids, (
        "Keyword-matching memory should appear in hybrid results "
        "even when its embedding similarity is low"
    )


def test_deduplication_same_memory_once(store):
    """
    A memory that matches BOTH the semantic path and the keyword path
    must appear only once in the results.
    """
    mem = _make_memory(
        "dedup-1", "Redis connection pool timeout handling",
        importance=0.8,
    )
    vec = embed(mem.summary)  # strong semantic match for "Redis timeout"
    store.add(mem, vec)

    query = "Redis"
    query_vec = embed(query)

    results = store.hybrid_search(query, query_vec, k=10)
    ids = [r["id"] for r in results]

    assert ids.count("dedup-1") == 1, (
        "Memory matched by both semantic and keyword paths must appear exactly once"
    )


def test_hybrid_beats_semantic_for_keyword_query(store):
    """
    hybrid_search should surface a keyword-relevant memory that
    semantic_search alone would miss or rank poorly.
    """
    # Insert several memories — only one mentions the exact keyword "Kubernetes"
    memories = [
        ("m1", "Python decorator patterns for retry logic", 0.6),
        ("m2", "Kubernetes pod crash loop debugging steps", 0.7),
        ("m3", "Docker container networking bridge setup", 0.5),
        ("m4", "Flask API rate limiting middleware", 0.5),
        ("m5", "PostgreSQL index tuning for slow queries", 0.6),
    ]

    for mid, summary, imp in memories:
        mem = _make_memory(mid, summary, importance=imp)
        # Give every memory the SAME distant vector so semantic search
        # treats them all equally (no embedding advantage).
        store.add(mem, _distant_vector())

    query = "Kubernetes"
    query_vec = embed(query)

    hybrid_results = store.hybrid_search(query, query_vec, k=5)
    semantic_results = store.semantic_search(query_vec, k=5)

    hybrid_ids = [r["id"] for r in hybrid_results]
    semantic_ids = [r["id"] for r in semantic_results]

    # Hybrid should reliably surface the Kubernetes memory via keyword path
    assert "m2" in hybrid_ids, (
        "hybrid_search must find the Kubernetes memory via keyword matching"
    )

    # Semantic search with all-identical vectors can't distinguish the
    # Kubernetes memory — it either doesn't appear or has no ranking edge.
    # Hybrid should place it higher (or at least include it).
    if "m2" in semantic_ids:
        hybrid_rank = hybrid_ids.index("m2")
        semantic_rank = semantic_ids.index("m2")
        assert hybrid_rank <= semantic_rank, (
            "hybrid_search should rank the keyword-matching memory at least "
            "as high as semantic_search does"
        )


def test_importance_influences_hybrid_ranking(store):
    """
    Among keyword-matching memories, higher importance should rank higher.
    """
    high_imp = _make_memory(
        "hi", "gRPC timeout configuration for microservices", importance=0.95
    )
    low_imp = _make_memory(
        "lo", "gRPC stream error handling patterns", importance=0.2
    )

    store.add(high_imp, embed(high_imp.summary))
    store.add(low_imp, embed(low_imp.summary))

    results = store.hybrid_search("gRPC", embed("gRPC"), k=5)
    result_ids = [r["id"] for r in results]

    assert "hi" in result_ids and "lo" in result_ids
    assert result_ids.index("hi") < result_ids.index("lo"), (
        "Higher-importance memory should rank above lower-importance one"
    )


def test_hybrid_returns_at_most_k_results(store):
    """hybrid_search respects the k limit."""
    for i in range(10):
        mem = _make_memory(f"mem-{i}", f"Webpack bundle optimization tip #{i}", importance=0.5)
        store.add(mem, embed(mem.summary))

    results = store.hybrid_search("Webpack", embed("Webpack"), k=3)
    assert len(results) <= 3


def test_keyword_only_hit_ranks_above_unrelated_semantic_hit(store):
    """
    Regression test: a keyword-exact match must outrank a semantically-close
    but topically unrelated result.

    Before the fix, keyword-only results defaulted to _distance=1.0 (semantic=0.0)
    and would sink to the bottom regardless of relevance.
    """
    # Memory that will score well semantically for "mule proxies" — but doesn't
    # contain the words (just semantically adjacent enough to land in top-50).
    sem_mem = _make_memory(
        "sem-only",
        "API gateway configuration and reverse proxy routing rules",
        importance=0.8,
    )
    sem_vec = embed(sem_mem.summary)

    # Memory that literally contains the exact query terms in raw_text,
    # but has a distant embedding vector.
    kw_mem = _make_memory(
        "kw-only",
        "Kyle Woolford 0:03",  # short, uninformative summary (like a transcript chunk)
        raw_text="We discussed how mule proxies handle the message routing between services.",
        importance=0.75,
    )
    kw_vec = _distant_vector()

    store.add(sem_mem, sem_vec)
    store.add(kw_mem, kw_vec)

    results = store.hybrid_search("mule proxies", embed("mule proxies"), k=5)
    ids = [r["id"] for r in results]

    assert "kw-only" in ids, "Keyword-exact match must appear in results"
    assert ids.index("kw-only") < ids.index("sem-only"), (
        "Keyword-exact match should rank above unrelated semantic hit"
    )
