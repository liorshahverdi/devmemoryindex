"""
API endpoint tests — uses FastAPI TestClient with a tmp_path-isolated store
provided by the root conftest `store` fixture.
"""

import hashlib
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

from api.server import app

client = TestClient(app)


def _seed(store, summary="Fixed Redis timeout", memory_type="agent_solution", repo="myapp"):
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


# ── GET /memory/search ────────────────────────────────────────────────────────

class TestSearchEndpoint:

    def test_search_returns_results(self, store):
        _seed(store, "Fixed Redis timeout issue")
        resp = client.get("/memory/search?q=redis+timeout")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_search_response_shape(self, store):
        _seed(store)
        resp = client.get("/memory/search?q=redis")
        result = resp.json()["results"][0]
        assert "id" in result
        assert "type" in result
        assert "summary" in result

    def test_search_type_filter(self, store):
        _seed(store, "agent memory", memory_type="agent_solution")
        _seed(store, "git commit memory", memory_type="git_commit")
        resp = client.get("/memory/search?q=memory&type=agent_solution")
        results = resp.json()["results"]
        assert all(r["type"] == "agent_solution" for r in results)

    def test_search_empty_store(self, store):
        resp = client.get("/memory/search?q=anything")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_search_requires_query(self, store):
        resp = client.get("/memory/search")
        assert resp.status_code == 422


# ── POST /memory/remember ─────────────────────────────────────────────────────

class TestRememberEndpoint:

    def test_remember_returns_ok(self, store):
        resp = client.post("/memory/remember", json={
            "summary": "Fixed JWT auth by refreshing on 401",
            "memory_type": "agent_solution",
            "repo": "api",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert "id" in resp.json()

    def test_remember_duplicate_returns_duplicate(self, store):
        payload = {"summary": "Unique memory for dedup test", "memory_type": "agent_solution"}
        client.post("/memory/remember", json=payload)
        resp = client.post("/memory/remember", json=payload)
        assert resp.json()["status"] == "duplicate"

    def test_remember_persists_to_store(self, store):
        client.post("/memory/remember", json={"summary": "persist test"})
        assert store.count() == 1

    def test_remember_missing_summary_fails(self, store):
        resp = client.post("/memory/remember", json={"memory_type": "agent_solution"})
        assert resp.status_code == 422


# ── GET /memory/{id} ─────────────────────────────────────────────────────────

class TestGetMemoryEndpoint:

    def test_get_existing_memory(self, store):
        mem_id = _seed(store, "Get by ID test")
        resp = client.get(f"/memory/{mem_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == mem_id
        assert resp.json()["summary"] == "Get by ID test"

    def test_get_missing_memory_returns_404(self, store):
        resp = client.get("/memory/nonexistentid123")
        assert resp.status_code == 404

    def test_get_response_has_raw_text(self, store):
        mem_id = _seed(store, "Memory with raw text")
        resp = client.get(f"/memory/{mem_id}")
        assert "raw_text" in resp.json()


# ── GET /memory/context ───────────────────────────────────────────────────────

class TestContextEndpoint:

    def test_context_returns_text(self, store):
        _seed(store, "Redis connection pool fix")
        resp = client.get("/memory/context?q=redis")
        assert resp.status_code == 200
        data = resp.json()
        assert "context" in data
        assert "memory_count" in data
        assert "token_estimate" in data

    def test_context_includes_intent(self, store):
        resp = client.get("/memory/context?q=error+in+auth")
        assert resp.json()["intent"] == "debug"

    def test_context_cached_flag(self, store):
        resp = client.get("/memory/context?q=unique+query+xyz+abc")
        assert resp.json()["cached"] is False

    def test_context_requires_query(self, store):
        resp = client.get("/memory/context")
        assert resp.status_code == 422


# ── POST /memory/ingest (webhook) ─────────────────────────────────────────────

class TestWebhookEndpoint:

    def test_ingest_returns_ok(self, store):
        resp = client.post("/memory/ingest", json={
            "text": "Deploy succeeded on main branch SHA abc123",
            "source": "github-actions",
            "repo": "myapp",
            "tags": ["deploy"],
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_ingest_duplicate_returns_duplicate(self, store):
        payload = {"text": "Deploy webhook dedup test", "source": "ci"}
        client.post("/memory/ingest", json=payload)
        resp = client.post("/memory/ingest", json=payload)
        assert resp.json()["status"] == "duplicate"

    def test_ingest_missing_text_fails(self, store):
        resp = client.post("/memory/ingest", json={"source": "ci"})
        assert resp.status_code == 422

    def test_ingest_persists_to_store(self, store):
        client.post("/memory/ingest", json={"text": "webhook persist test"})
        assert store.count() == 1
