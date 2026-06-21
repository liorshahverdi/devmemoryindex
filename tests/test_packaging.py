"""Packaging metadata regression tests."""

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def test_core_runtime_dependencies_are_project_dependencies():
    deps = _pyproject()["project"]["dependencies"]

    assert any(dep.startswith("lancedb") for dep in deps)
    assert any(dep.startswith("sentence-transformers") for dep in deps)


def test_mcp_optional_dependency_uses_current_sdk_package_name():
    """The MCP SDK no longer publishes a `server` extra; avoid stale-extra warnings."""
    optional_deps = _pyproject()["project"]["optional-dependencies"]

    assert "mcp>=1.0" in optional_deps["mcp"]
    assert all(not dep.startswith("mcp[") for dep in optional_deps["mcp"])


def test_mcp_optional_dependency_includes_runtime_import_dependencies():
    """A normal MCP install should include imports needed by mcp_server.server."""
    optional_deps = _pyproject()["project"]["optional-dependencies"]

    assert "lancedb" in optional_deps["mcp"]
    assert "sentence-transformers" in optional_deps["mcp"]


def test_mcp_server_has_console_script_entry_point():
    """A normal package install should expose a stable stdio MCP server command."""
    scripts = _pyproject()["project"]["scripts"]

    assert scripts["devmemory-mcp-server"] == "mcp_server.server:main"
