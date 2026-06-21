"""Packaging metadata regression tests."""

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_mcp_optional_dependency_uses_current_sdk_package_name():
    """The MCP SDK no longer publishes a `server` extra; avoid stale-extra warnings."""
    optional_deps = _pyproject()["project"]["optional-dependencies"]

    assert optional_deps["mcp"] == ["mcp>=1.0"]


def test_mcp_server_has_console_script_entry_point():
    """A normal package install should expose a stable stdio MCP server command."""
    scripts = _pyproject()["project"]["scripts"]

    assert scripts["devmemory-mcp-server"] == "mcp_server.server:main"
