from pathlib import Path

import pytest

from core.memory_store import MemoryStore
from connectors.graphify_connector import GraphifyConnector, GraphifyOutputMissingError, _deterministic_node_id


FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "graphify"


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


def _connector(store, root=FIXTURE_ROOT, **kwargs):
    connector = GraphifyConnector(path=root, **kwargs)
    connector.store = store
    return connector


def test_graphify_connector_ingests_report_sections_and_nodes(monkeypatch, store):
    """Phase 1 imports GRAPH_REPORT.md sections and selected graph.json nodes."""
    monkeypatch.setattr("connectors.graphify_connector.embed_batch", lambda texts: [[0.1] * 384 for _ in texts])

    count = _connector(store).collect()

    assert count == 6
    memories = store.get_all()
    by_type = {memory["type"] for memory in memories}
    assert "graphify_report" in by_type
    assert "graphify_node" in by_type
    assert any(memory["summary"] == "Graphify report: Architecture Overview" for memory in memories)
    auth = next(memory for memory in memories if memory["summary"] == "Graphify node: AuthService (class)")
    assert auth["repo"] == "graphify"
    assert "graphify" in auth["tags"]
    assert "node_type:class" in auth["tags"]
    assert "source_file:src/auth.py" in auth["tags"]
    assert "Degree: 2" in auth["raw_text"]


def test_graphify_imported_report_is_searchable(monkeypatch, store):
    monkeypatch.setattr("connectors.graphify_connector.embed_batch", lambda texts: [[0.1] * 384 for _ in texts])
    _connector(store).collect()

    results = store.text_search("architecture auth flow", k=3, type_filter="graphify_report")

    assert results
    assert results[0]["type"] == "graphify_report"
    assert "Architecture Overview" in results[0]["summary"]


def test_graphify_connector_is_idempotent(monkeypatch, store):
    monkeypatch.setattr("connectors.graphify_connector.embed_batch", lambda texts: [[0.1] * 384 for _ in texts])
    connector = _connector(store)

    assert connector.collect() == 6
    assert connector.collect() == 0
    assert len(store.get_all()) == 6


def test_graphify_connector_min_degree_filters_low_signal_nodes(monkeypatch, store):
    monkeypatch.setattr("connectors.graphify_connector.embed_batch", lambda texts: [[0.1] * 384 for _ in texts])

    count = _connector(store, min_degree=1, no_report=True).collect()

    assert count == 2
    summaries = {memory["summary"] for memory in store.get_all()}
    assert "Graphify node: AuthService (class)" in summaries
    assert "Graphify node: ApiGateway (module)" in summaries
    assert "Graphify node: IsolatedHelper (function)" not in summaries


def test_graphify_connector_supports_edges_key_variant(monkeypatch, store, tmp_path):
    monkeypatch.setattr("connectors.graphify_connector.embed_batch", lambda texts: [[0.1] * 384 for _ in texts])
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "GRAPH_REPORT.md").write_text("# Report\n\n## Overview\n\nUses edges key.\n")
    (out / "graph.json").write_text(
        '{"nodes":[{"id":"a","label":"A","type":"module"},{"id":"b","label":"B","type":"class"}],'
        '"edges":[{"source":"a","target":"b","relation":"calls"}]}'
    )

    _connector(store, root=tmp_path, min_degree=1, no_report=True).collect()

    memories = store.get_all()
    assert {memory["summary"] for memory in memories} == {
        "Graphify node: A (module)",
        "Graphify node: B (class)",
    }
    assert all("Degree: 1" in memory["raw_text"] for memory in memories)


def test_graphify_connector_missing_output_returns_clear_error(tmp_path, store):
    connector = _connector(store, root=tmp_path)

    with pytest.raises(GraphifyOutputMissingError, match="graphify-out"):
        connector.collect()


def test_graphify_node_ids_are_deterministic():
    first = _deterministic_node_id("repo", "node-1")
    second = _deterministic_node_id("repo", "node-1")
    different_repo = _deterministic_node_id("other", "node-1")

    assert first == second
    assert first != different_repo
    assert len(first) == 64
