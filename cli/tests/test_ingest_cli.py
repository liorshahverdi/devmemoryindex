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
