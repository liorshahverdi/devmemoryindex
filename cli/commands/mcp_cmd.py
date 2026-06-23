"""MCP client registration helpers.

These commands intentionally avoid interactive prompts so setup agents can
register DevMemoryIndex with Hermes from scripts/CI/bootstrap runs.
"""

from __future__ import annotations

import os
import shlex
import stat
import sys
from pathlib import Path

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="MCP client registration helpers.")


def _quote_yaml(value: str) -> str:
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def render_hermes_config_block(
    *,
    name: str = "devmemory",
    command: str,
    timeout: int = 120,
    connect_timeout: int = 60,
) -> str:
    """Render a Hermes `mcp_servers` YAML block for DevMemoryIndex."""
    return (
        "mcp_servers:\n"
        f"  {name}:\n"
        f"    command: {_quote_yaml(command)}\n"
        "    args: []\n"
        f"    timeout: {timeout}\n"
        f"    connect_timeout: {connect_timeout}\n"
    )


def _server_entry_lines(name: str, command: str, timeout: int, connect_timeout: int) -> list[str]:
    return [
        f"  {name}:",
        f"    command: {_quote_yaml(command)}",
        "    args: []",
        f"    timeout: {timeout}",
        f"    connect_timeout: {connect_timeout}",
    ]


def upsert_hermes_mcp_server(
    config_text: str,
    *,
    name: str = "devmemory",
    command: str,
    timeout: int = 120,
    connect_timeout: int = 60,
) -> str:
    """Insert or replace a top-level Hermes `mcp_servers.<name>` entry.

    This small YAML updater is deliberately scoped to the simple Hermes config
    shape we need, avoiding a new PyYAML dependency for one bootstrap command.
    Existing non-MCP config and sibling MCP server blocks are preserved.
    """
    entry = _server_entry_lines(name, command, timeout, connect_timeout)
    lines = config_text.splitlines()
    if not lines:
        return "\n".join(["mcp_servers:", *entry, ""])

    try:
        mcp_idx = next(i for i, line in enumerate(lines) if line.strip() == "mcp_servers:")
    except StopIteration:
        prefix = lines + ([] if lines[-1] == "" else [""])
        return "\n".join([*prefix, "mcp_servers:", *entry, ""])

    # Find the end of the top-level mcp_servers section.
    section_end = len(lines)
    for i in range(mcp_idx + 1, len(lines)):
        line = lines[i]
        if line and not line.startswith(" ") and not line.startswith("\t"):
            section_end = i
            break

    # Find an existing two-space-indented server block with this name.
    server_start = None
    server_end = None
    marker = f"  {name}:"
    for i in range(mcp_idx + 1, section_end):
        if lines[i] == marker:
            server_start = i
            server_end = section_end
            for j in range(i + 1, section_end):
                if lines[j].startswith("  ") and not lines[j].startswith("    "):
                    server_end = j
                    break
            break

    if server_start is None:
        new_lines = lines[:section_end] + entry + lines[section_end:]
    else:
        new_lines = lines[:server_start] + entry + lines[server_end:]
    return "\n".join(new_lines) + "\n"


def render_wrapper_script(repo_dir: Path, python_executable: str = sys.executable) -> str:
    """Render a stable stdio wrapper for MCP clients."""
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"cd {shlex.quote(str(repo_dir))}\n"
        f"exec {shlex.quote(python_executable)} -m mcp_server.server\n"
    )


def _default_hermes_config() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "config.yaml"


@app.command("install-hermes")
def install_hermes(
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply without prompting; required for non-interactive setup."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print the wrapper and config patch without writing files."),
    name: str = typer.Option("devmemory", "--name", help="Hermes MCP server name."),
    wrapper_path: Path = typer.Option(Path.home() / ".local" / "bin" / "devmemory-mcp-server", "--wrapper-path", help="Path for the stable wrapper script."),
    hermes_config: Path = typer.Option(_default_hermes_config(), "--hermes-config", help="Hermes config.yaml path."),
    repo_dir: Path = typer.Option(Path(__file__).resolve().parents[2], "--repo-dir", help="DevMemoryIndex repository/install directory."),
    timeout: int = typer.Option(120, "--timeout", help="Hermes per-tool timeout in seconds."),
    connect_timeout: int = typer.Option(60, "--connect-timeout", help="Hermes MCP startup/discovery timeout in seconds."),
):
    """Register DevMemoryIndex with Hermes without interactive prompts.

    Writes a stable wrapper script and upserts `mcp_servers.<name>` in the
    Hermes config. Restart Hermes or run `/reload-mcp` after applying.
    """
    repo_dir = repo_dir.expanduser().resolve()
    wrapper_path = wrapper_path.expanduser().resolve()
    hermes_config = hermes_config.expanduser().resolve()
    wrapper_text = render_wrapper_script(repo_dir=repo_dir)
    current_config = hermes_config.read_text() if hermes_config.exists() else ""
    new_config = upsert_hermes_mcp_server(
        current_config,
        name=name,
        command=str(wrapper_path),
        timeout=timeout,
        connect_timeout=connect_timeout,
    )

    if dry_run:
        console.print("[bold]Non-interactive Hermes MCP registration plan[/bold]")
        console.print(f"Wrapper path: {wrapper_path}")
        console.print(f"Hermes config: {hermes_config}")
        console.print("\n[bold]Wrapper script[/bold]")
        console.print(wrapper_text)
        console.print("[bold]Hermes config block[/bold]")
        console.print(render_hermes_config_block(name=name, command=str(wrapper_path), timeout=timeout, connect_timeout=connect_timeout))
        return

    if not yes:
        console.print("[red]Refusing to write without --yes. Use --dry-run to inspect the plan.[/red]")
        raise typer.Exit(2)

    wrapper_path.parent.mkdir(parents=True, exist_ok=True)
    wrapper_path.write_text(wrapper_text)
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    hermes_config.parent.mkdir(parents=True, exist_ok=True)
    hermes_config.write_text(new_config)

    console.print(f"[green]Installed Hermes MCP wrapper:[/green] {wrapper_path}")
    console.print(f"[green]Updated Hermes config:[/green] {hermes_config}")
    console.print("Run: hermes mcp test devmemory")
