"""
MCP tool tests — exercises search_memories, build_context, remember_memory,
and get_memory using the root conftest `store` fixture.
"""

import hashlib
import pytest
from datetime import datetime

from mcp_server.tools import search_memories, build_context, remember_memory, get_memory


def _seed(store, summary, memory_type="agent_solution", repo="testrepo"):
    from core.schema import Memory
    from core.embeddings import embed
    mem_id = hashlib.sha256(summary.encode()).hexdigest()
    memory = Memory(
        id=mem_id,
        type=memory_type,
        summary=summary,
        raw_text=summary,
        source="test",
        repo=repo,
        timestamp=datetime.utcnow(),
        tags=["test"],
        importance=0.8,
    )
    store.add(memory, embed(summary))
    return mem_id


# ── search_memories ───────────────────────────────────────────────────────────

class TestSearchMemories:

    def test_returns_list(self, store):
        _seed(store, "LanceDB schema timestamp fix")
        results = search_memories("lancedb schema")
        assert isinstance(results, list)

    def test_result_has_required_fields(self, store):
        _seed(store, "LanceDB schema fix")
        results = search_memories("lancedb")
        assert len(results) >= 1
        r = results[0]
        assert "id" in r
        assert "summary" in r
        assert "type" in r
        assert "related" in r

    def test_result_count_respects_k(self, store):
        for i in range(10):
            _seed(store, f"memory about redis fix number {i}")
        results = search_memories("redis fix", k=3)
        assert len(results) <= 3

    def test_type_filter(self, store):
        _seed(store, "agent memory", memory_type="agent_solution")
        _seed(store, "git commit memory", memory_type="git_commit")
        results = search_memories("memory", memory_type="agent_solution")
        assert all(r["type"] == "agent_solution" for r in results)

    def test_empty_store_returns_empty_list(self, store):
        results = search_memories("anything")
        assert results == []


# ── remember_memory ───────────────────────────────────────────────────────────

class TestRememberMemory:

    def test_returns_ok_status(self, store):
        result = remember_memory("Fixed auth timeout by refreshing token on 401")
        assert result["status"] == "ok"
        assert "id" in result

    def test_duplicate_returns_duplicate_status(self, store):
        remember_memory("Unique solution for dedup test")
        result = remember_memory("Unique solution for dedup test")
        assert result["status"] == "duplicate"

    def test_memory_persisted_to_store(self, store):
        remember_memory("Persisted solution test")
        assert store.count() == 1

    def test_custom_type_and_repo(self, store):
        result = remember_memory(
            "Architectural decision: use LanceDB",
            memory_type="architectural_decision",
            repo="devmemoryindex",
        )
        assert result["status"] == "ok"


# ── build_context ─────────────────────────────────────────────────────────────

class TestBuildContext:

    def test_returns_string(self, store):
        _seed(store, "Redis connection fix")
        result = build_context("redis fix")
        assert isinstance(result, str)

    def test_claude_format_has_context_tags(self, store):
        _seed(store, "LanceDB timestamp fix")
        result = build_context("lancedb", format="claude")
        assert "<context>" in result
        assert "</context>" in result

    def test_empty_store_returns_string(self, store):
        result = build_context("anything")
        assert isinstance(result, str)


# ── get_memory ────────────────────────────────────────────────────────────────

class TestGetMemory:

    def test_returns_memory_by_id(self, store):
        mem_id = _seed(store, "Get memory by ID test")
        result = get_memory(mem_id)
        assert result is not None
        assert result["id"] == mem_id
        assert result["summary"] == "Get memory by ID test"

    def test_returns_none_for_missing_id(self, store):
        result = get_memory("nonexistent_id_abc123")
        assert result is None

    def test_result_has_raw_text(self, store):
        mem_id = _seed(store, "Memory with raw text content")
        result = get_memory(mem_id)
        assert "raw_text" in result
        assert result["raw_text"] == "Memory with raw text content"

    def test_resolves_related_id(self, store):
        mem_id = _seed(store, "Related memory resolution test")
        result = get_memory(mem_id)
        assert result["id"] == mem_id
