from typer.testing import CliRunner

from cli.main import app


runner = CliRunner()


def test_ingest_help_lists_all_active_connector_sources():
    result = runner.invoke(app, ["ingest", "--help"])

    assert result.exit_code == 0
    for source in [
        "git",
        "diff",
        "terminal",
        "filesystem",
        "markdown",
        "claude",
        "copilot",
        "browser",
        "meeting",
    ]:
        assert source in result.output


def test_ingest_filesystem_accepts_repo_and_max_files_options(monkeypatch):
    """Filesystem-specific controls should be scriptable from the ingest CLI."""
    captured = {}

    class FakeFilesystemConnector:
        name = "filesystem"

        def __init__(self, dirs=None, *, max_files=None, repo=None, progress_callback=None):
            captured["max_files"] = max_files
            captured["repo"] = repo
            captured["progress_callback"] = progress_callback
            self.last_stats = {
                "inspected": 3,
                "chunks_added": 2,
                "skipped": {"unchanged": 1},
                "errors": 0,
            }

        def collect(self):
            self.last_stats["progress_callback_present"] = self.last_stats is not None
            return 2

    monkeypatch.setattr("cli.commands.ingest.FilesystemConnector", FakeFilesystemConnector)

    result = runner.invoke(app, ["ingest", "--source", "filesystem", "--repo", "my-app", "--max-files", "3"])

    assert result.exit_code == 0
    assert captured["repo"] == "my-app"
    assert captured["max_files"] == 3
    assert callable(captured["progress_callback"])
    assert "inspected=3" in result.output
    assert "unchanged=1" in result.output
