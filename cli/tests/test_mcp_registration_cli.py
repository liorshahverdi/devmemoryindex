"""Tests for non-interactive MCP client registration helpers."""

from pathlib import Path

from typer.testing import CliRunner

from cli.main import app
from cli.commands import mcp_cmd


runner = CliRunner()


def test_render_hermes_config_block_uses_stable_wrapper_command():
    block = mcp_cmd.render_hermes_config_block(
        name="devmemory",
        command="/home/me/.local/bin/devmemory-mcp-server",
        timeout=180,
        connect_timeout=30,
    )

    assert "mcp_servers:" in block
    assert "devmemory:" in block
    assert 'command: "/home/me/.local/bin/devmemory-mcp-server"' in block
    assert "args: []" in block
    assert "timeout: 180" in block
    assert "connect_timeout: 30" in block


def test_upsert_hermes_config_adds_mcp_servers_without_editor():
    original = "model:\n  provider: openrouter\n"

    updated = mcp_cmd.upsert_hermes_mcp_server(
        original,
        name="devmemory",
        command="/tmp/devmemory-mcp-server",
    )

    assert "model:\n  provider: openrouter" in updated
    assert "mcp_servers:\n  devmemory:\n" in updated
    assert '    command: "/tmp/devmemory-mcp-server"' in updated


def test_upsert_hermes_config_replaces_existing_devmemory_entry():
    original = """mcp_servers:
  devmemory:
    command: "/old/path"
    args: []
  time:
    command: "uvx"
    args: ["mcp-server-time"]
"""

    updated = mcp_cmd.upsert_hermes_mcp_server(
        original,
        name="devmemory",
        command="/new/path",
    )

    assert "/old/path" not in updated
    assert '    command: "/new/path"' in updated
    assert "  time:\n    command: \"uvx\"" in updated


def test_install_hermes_mcp_dry_run_is_non_interactive_and_does_not_write(tmp_path):
    wrapper = tmp_path / "bin" / "devmemory-mcp-server"
    hermes_config = tmp_path / "config.yaml"

    result = runner.invoke(
        app,
        [
            "mcp",
            "install-hermes",
            "--yes",
            "--dry-run",
            "--wrapper-path",
            str(wrapper),
            "--hermes-config",
            str(hermes_config),
        ],
    )

    assert result.exit_code == 0
    assert "Non-interactive Hermes MCP registration plan" in result.output
    assert "devmemory-mcp-server" in result.output.replace("\n", "")
    assert not wrapper.exists()
    assert not hermes_config.exists()


def test_install_hermes_mcp_writes_wrapper_and_config_with_yes(tmp_path):
    wrapper = tmp_path / "bin" / "devmemory-mcp-server"
    hermes_config = tmp_path / "config.yaml"
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    result = runner.invoke(
        app,
        [
            "mcp",
            "install-hermes",
            "--yes",
            "--wrapper-path",
            str(wrapper),
            "--hermes-config",
            str(hermes_config),
            "--repo-dir",
            str(repo_dir),
        ],
    )

    assert result.exit_code == 0
    assert wrapper.exists()
    wrapper_text = wrapper.read_text()
    assert "set -euo pipefail" in wrapper_text
    assert f"cd {repo_dir}" in wrapper_text
    assert "python" in wrapper_text
    config_text = hermes_config.read_text()
    assert "mcp_servers:" in config_text
    assert 'command: "' in config_text
    assert str(wrapper) in config_text
