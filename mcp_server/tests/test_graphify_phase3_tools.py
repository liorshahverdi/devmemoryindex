from __future__ import annotations

from datetime import UTC, datetime

import mcp_server.tools as tools


class FakeStore:
    def __init__(self):
        self.search_calls = []
        self.records = {
            "node-auth": {
                "id": "node-auth",
                "type": "graphify_node",
                "summary": "Graphify node: AuthService (class)",
                "raw_text": "AuthService validates tokens and calls UserRepo",
                "repo": "demo",
                "importance": 0.9,
                "tags": ["graphify", "code_graph", "node_type:class"],
                "timestamp": datetime.now(UTC),
            },
            "node-user": {
                "id": "node-user",
                "type": "graphify_node",
                "summary": "Graphify node: UserRepo (class)",
                "raw_text": "UserRepo loads users for AuthService",
                "repo": "demo",
                "importance": 0.8,
                "tags": ["graphify", "code_graph", "node_type:class"],
                "timestamp": datetime.now(UTC),
            },
            "report-arch": {
                "id": "report-arch",
                "type": "graphify_report",
                "summary": "Graphify report: Authentication architecture",
                "raw_text": "AuthService is the central authentication component",
                "repo": "demo",
                "importance": 0.85,
                "tags": ["graphify", "architecture"],
                "timestamp": datetime.now(UTC),
            },
            "ordinary": {
                "id": "ordinary",
                "type": "agent_solution",
                "summary": "Unrelated authentication note",
                "raw_text": "not graphify",
                "repo": "demo",
                "importance": 1.0,
                "tags": [],
                "timestamp": datetime.now(UTC),
            },
        }

    def hybrid_search(self, query, vector, k=5, type_filter=None, repo_filter=None, speaker_filter=None):
        self.search_calls.append({"query": query, "k": k, "type_filter": type_filter, "repo_filter": repo_filter})
        rows = [r for r in self.records.values() if r["type"].startswith(type_filter or "")]
        if repo_filter:
            rows = [r for r in rows if r["repo"] == repo_filter]
        return rows[:k]

    def get_by_id(self, memory_id, reinforce=True):
        return self.records.get(memory_id)


class FakeEdges:
    def get_graph(self, memory_id, depth=1):
        return {
            "root": memory_id,
            "nodes": [memory_id, "node-user"],
            "edges": [
                {
                    "from_id": memory_id,
                    "to_id": "node-user",
                    "edge_type": "references",
                    "confidence": 0.9,
                    "source": "graphify",
                    "created_at": "2026-01-01T00:00:00",
                }
            ],
        }


def test_search_code_graph_searches_graphify_nodes_and_reports(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(tools, "get_store", lambda: store)
    monkeypatch.setattr(tools, "embed", lambda query: [0.0] * 384)

    result = tools.search_code_graph("authentication architecture", repo="demo", k=5)

    assert [call["type_filter"] for call in store.search_calls] == ["graphify_node", "graphify_report"]
    assert result["query"] == "authentication architecture"
    assert result["repo"] == "demo"
    assert result["result_count"] == 3
    assert {row["type"] for row in result["results"]} == {"graphify_node", "graphify_report"}
    assert "ordinary" not in {row["id"] for row in result["results"]}


def test_get_code_entity_context_resolves_query_and_hydrates_graph_neighbors(monkeypatch):
    store = FakeStore()
    fake_edges = FakeEdges()
    monkeypatch.setattr(tools, "get_store", lambda: store)
    monkeypatch.setattr(tools, "embed", lambda query: [0.0] * 384)
    monkeypatch.setattr("core.edge_provider.get_edges", lambda: fake_edges)

    result = tools.get_code_entity_context("AuthService", repo="demo", depth=1)

    assert result["root"]["id"] == "node-auth"
    assert result["root"]["summary"] == "Graphify node: AuthService (class)"
    assert result["node_count"] == 2
    assert result["edge_count"] == 1
    assert result["edges"][0]["source"] == "graphify"
    assert {node["id"] for node in result["nodes"]} == {"node-auth", "node-user"}
    assert result["nodes"][1]["raw_text"].startswith("UserRepo")
