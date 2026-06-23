from pathlib import Path

from typer.testing import CliRunner

from cli.main import app


runner = CliRunner()
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "graphify"


def test_graphify_ingest_cli_imports_existing_output(monkeypatch, tmp_path):
    """devmemory graphify ingest should import an existing graphify-out directory."""
    store = __import__("core.memory_store", fromlist=["MemoryStore"]).MemoryStore(db_path=str(tmp_path / "db"))
    monkeypatch.setattr("connectors.base.get_store", lambda: store)
    monkeypatch.setattr("connectors.graphify_connector.embed_batch", lambda texts: [[0.1] * 384 for _ in texts])

    result = runner.invoke(app, ["graphify", "ingest", str(FIXTURE_ROOT), "--repo", "sample-repo", "--min-degree", "1"])

    assert result.exit_code == 0
    assert "[graphify] +5 memories" in result.output
    assert "reports=3" in result.output
    assert "nodes=2" in result.output
    assert "sample-repo" in result.output


def test_graphify_ingest_cli_reports_missing_output(tmp_path):
    result = runner.invoke(app, ["graphify", "ingest", str(tmp_path)])

    assert result.exit_code == 1
    assert "graphify-out" in result.output
    assert "graph.json" in result.output


def test_graphify_ingest_cli_supports_dry_run(monkeypatch, tmp_path):
    def fail_if_called(_texts):
        raise AssertionError("dry-run must not embed or write memories")

    monkeypatch.setattr("connectors.graphify_connector.embed_batch", fail_if_called)

    result = runner.invoke(app, ["graphify", "ingest", str(FIXTURE_ROOT), "--dry-run", "--no-report", "--min-degree", "1"])

    assert result.exit_code == 0
    assert "Dry run" in result.output
    assert "nodes=2" in result.output
    assert "reports=0" in result.output


def test_graphify_ingest_cli_supports_with_edges(monkeypatch, tmp_path):
    store = __import__("core.memory_store", fromlist=["MemoryStore"]).MemoryStore(db_path=str(tmp_path / "db"))
    edge_store = __import__("core.edge_store", fromlist=["EdgeStore"]).EdgeStore(db_path=str(tmp_path / "edges_db"))
    monkeypatch.setattr("connectors.base.get_store", lambda: store)
    monkeypatch.setattr("connectors.graphify_connector.get_edges", lambda: edge_store)
    monkeypatch.setattr("connectors.graphify_connector.embed_batch", lambda texts: [[0.1] * 384 for _ in texts])

    result = runner.invoke(app, ["graphify", "ingest", str(FIXTURE_ROOT), "--repo", "sample-repo", "--with-edges"])

    assert result.exit_code == 0
    assert "edges=2" in result.output
    assert len(edge_store.get_all_edges()) == 2
