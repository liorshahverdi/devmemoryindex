from typer.testing import CliRunner

from cli.main import app
import cli.commands.graph_cmd as graph_cmd


runner = CliRunner()


class FakeStore:
    def __init__(self, records):
        self.records = {r["id"]: r for r in records}

    def get_by_id(self, memory_id: str, reinforce: bool = True):
        if memory_id in self.records:
            return self.records[memory_id]
        matches = [r for id_, r in self.records.items() if id_.startswith(memory_id)]
        return matches[0] if len(matches) == 1 else None


class FakeEdges:
    def __init__(self, graph):
        self.graph = graph
        self.requested_depth = None

    def get_graph(self, memory_id: str, depth: int = 2):
        self.requested_depth = depth
        return self.graph


def test_graph_command_renders_memory_relationship_tree(monkeypatch):
    store = FakeStore([
        {"id": "failure-1", "summary": "Auth timeout failure", "type": "failure_note", "repo": "api"},
        {"id": "commit-1", "summary": "Fix auth timeout commit", "type": "git_commit", "repo": "api"},
        {"id": "runbook-1", "summary": "Auth runbook", "type": "markdown", "repo": "api"},
    ])
    edges = FakeEdges({
        "root": "failure-1",
        "nodes": ["failure-1", "commit-1", "runbook-1"],
        "edges": [
            {"from_id": "failure-1", "to_id": "commit-1", "edge_type": "fixed_by", "confidence": 0.95},
            {"from_id": "failure-1", "to_id": "runbook-1", "edge_type": "references", "confidence": 0.8},
        ],
    })
    monkeypatch.setattr(graph_cmd, "get_store", lambda: store)
    monkeypatch.setattr(graph_cmd, "get_edges", lambda: edges)

    result = runner.invoke(app, ["graph", "failure-1", "--depth", "2"])

    assert result.exit_code == 0
    assert edges.requested_depth == 2
    assert "Memory Graph" in result.output
    assert "Auth timeout failure" in result.output
    assert "fixed_by" in result.output
    assert "Fix auth timeout commit" in result.output
    assert "references" in result.output
    assert "Auth runbook" in result.output


def test_graph_command_accepts_unique_memory_prefix(monkeypatch):
    store = FakeStore([
        {"id": "failure-abcdef", "summary": "Failure from prefix", "type": "failure_note", "repo": "api"},
    ])
    edges = FakeEdges({"root": "failure-abcdef", "nodes": ["failure-abcdef"], "edges": []})
    monkeypatch.setattr(graph_cmd, "get_store", lambda: store)
    monkeypatch.setattr(graph_cmd, "get_edges", lambda: edges)

    result = runner.invoke(app, ["graph", "failure-a"])

    assert result.exit_code == 0
    assert "Failure from prefix" in result.output
    assert "No relationships found" in result.output


def test_graph_command_exits_when_root_memory_is_missing(monkeypatch):
    monkeypatch.setattr(graph_cmd, "get_store", lambda: FakeStore([]))
    monkeypatch.setattr(graph_cmd, "get_edges", lambda: FakeEdges({"root": "missing", "nodes": [], "edges": []}))

    result = runner.invoke(app, ["graph", "missing"])

    assert result.exit_code == 1
    assert "No memory found" in result.output
