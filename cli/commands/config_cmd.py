import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
import core.config as cfg

console = Console()
app = typer.Typer(help="Manage DevMemoryIndex configuration.")


@app.command("add")
def add_repo(
    path: str = typer.Argument(..., help="Path to a git repository to track"),
):
    """Add a git repository to the ingest list."""
    resolved = str(Path(path).expanduser().resolve())
    if not Path(resolved).is_dir():
        console.print(f"[red]Path not found: {resolved}[/red]")
        raise typer.Exit(1)
    if cfg.add_git_path(resolved):
        console.print(f"[green]Added:[/green] {resolved}")
    else:
        console.print(f"[yellow]Already tracked:[/yellow] {resolved}")


@app.command("remove")
def remove_repo(
    path: str = typer.Argument(..., help="Path to remove from tracking"),
):
    """Remove a git repository from the ingest list."""
    resolved = str(Path(path).expanduser().resolve())
    if cfg.remove_git_path(resolved):
        console.print(f"[yellow]Removed:[/yellow] {resolved}")
    else:
        console.print(f"[red]Not found in config:[/red] {resolved}")


@app.command("list")
def list_config():
    """Show all configured paths and connector schedules."""
    git_paths = cfg.get_git_paths()
    md_dirs = cfg.get_markdown_dirs()
    fs_dirs = cfg.get_filesystem_dirs()
    meeting_dirs = cfg.get_meeting_dirs()
    intervals = cfg.get_all_intervals()

    any_paths = git_paths or md_dirs or fs_dirs or meeting_dirs
    if not any_paths:
        console.print(
            "[yellow]No paths configured.[/yellow]\n"
            "Run [bold]devmemory config add <path>[/bold] to track a git repo,\n"
            "[bold]devmemory config add-notes <dir>[/bold] to scan markdown notes,\n"
            "[bold]devmemory config add-code <dir>[/bold] to index source code, or\n"
            "[bold]devmemory config add-meetings <dir>[/bold] to transcribe recordings."
        )

    if git_paths:
        table = Table(title="Tracked Git Repos")
        table.add_column("#", style="dim", width=4)
        table.add_column("Path", style="cyan")
        for i, p in enumerate(git_paths, 1):
            table.add_row(str(i), p)
        console.print(table)

    if md_dirs:
        table = Table(title="Markdown Scan Dirs")
        table.add_column("#", style="dim", width=4)
        table.add_column("Path", style="green")
        for i, p in enumerate(md_dirs, 1):
            table.add_row(str(i), p)
        console.print(table)

    if fs_dirs:
        table = Table(title="Code Scan Dirs")
        table.add_column("#", style="dim", width=4)
        table.add_column("Path", style="blue")
        for i, p in enumerate(fs_dirs, 1):
            table.add_row(str(i), p)
        console.print(table)

    if meeting_dirs:
        table = Table(title="Meeting Recording Dirs")
        table.add_column("#", style="dim", width=4)
        table.add_column("Path", style="magenta")
        for i, p in enumerate(meeting_dirs, 1):
            table.add_row(str(i), p)
        console.print(table)

    sched_table = Table(title="Connector Schedules")
    sched_table.add_column("Connector", style="bold")
    sched_table.add_column("Interval", style="cyan")
    for name, secs in intervals.items():
        sched_table.add_row(name, _fmt_interval(secs))
    console.print(sched_table)


@app.command("set-schedule")
def set_schedule(
    connector: str = typer.Argument(..., help="Connector name: git, claude, terminal, markdown"),
    seconds: int = typer.Argument(..., help="Ingest interval in seconds"),
):
    """Set how often a connector ingests (e.g. devmemory config set-schedule git 300)."""
    if connector not in cfg.CONNECTOR_NAMES:
        console.print(
            f"[red]Unknown connector '{connector}'.[/red] "
            f"Valid: {', '.join(cfg.CONNECTOR_NAMES)}"
        )
        raise typer.Exit(1)
    if seconds < 30:
        console.print("[red]Minimum interval is 30 seconds.[/red]")
        raise typer.Exit(1)
    cfg.set_connector_interval(connector, seconds)
    console.print(f"[green]{connector}[/green] interval set to [cyan]{_fmt_interval(seconds)}[/cyan]")


@app.command("add-notes")
def add_notes_dir(
    path: str = typer.Argument(..., help="Directory to scan for .md files"),
):
    """Add a directory to the markdown notes scan list."""
    resolved = str(Path(path).expanduser().resolve())
    if not Path(resolved).is_dir():
        console.print(f"[red]Path not found: {resolved}[/red]")
        raise typer.Exit(1)
    if cfg.add_markdown_dir(resolved):
        console.print(f"[green]Added:[/green] {resolved}")
    else:
        console.print(f"[yellow]Already tracked:[/yellow] {resolved}")


@app.command("remove-notes")
def remove_notes_dir(
    path: str = typer.Argument(..., help="Directory to remove from markdown scan list"),
):
    """Remove a directory from the markdown notes scan list."""
    resolved = str(Path(path).expanduser().resolve())
    if cfg.remove_markdown_dir(resolved):
        console.print(f"[yellow]Removed:[/yellow] {resolved}")
    else:
        console.print(f"[red]Not found in config:[/red] {resolved}")


@app.command("add-code")
def add_code_dir(
    path: str = typer.Argument(..., help="Directory to scan for source code"),
):
    """Add a directory to the code (filesystem) scan list."""
    resolved = str(Path(path).expanduser().resolve())
    if not Path(resolved).is_dir():
        console.print(f"[red]Path not found: {resolved}[/red]")
        raise typer.Exit(1)
    if cfg.add_filesystem_dir(resolved):
        console.print(f"[green]Added:[/green] {resolved}")
    else:
        console.print(f"[yellow]Already tracked:[/yellow] {resolved}")


@app.command("remove-code")
def remove_code_dir(
    path: str = typer.Argument(..., help="Directory to remove from code scan list"),
):
    """Remove a directory from the code (filesystem) scan list."""
    resolved = str(Path(path).expanduser().resolve())
    if cfg.remove_filesystem_dir(resolved):
        console.print(f"[yellow]Removed:[/yellow] {resolved}")
    else:
        console.print(f"[red]Not found in config:[/red] {resolved}")


@app.command("add-meetings")
def add_meetings_dir(
    path: str = typer.Argument(..., help="Directory to scan for audio recordings"),
):
    """Add a directory to the meeting recordings scan list."""
    resolved = str(Path(path).expanduser().resolve())
    if not Path(resolved).is_dir():
        console.print(f"[red]Path not found: {resolved}[/red]")
        raise typer.Exit(1)
    if cfg.add_meeting_dir(resolved):
        console.print(f"[green]Added:[/green] {resolved}")
    else:
        console.print(f"[yellow]Already tracked:[/yellow] {resolved}")


@app.command("remove-meetings")
def remove_meetings_dir(
    path: str = typer.Argument(..., help="Directory to remove from meetings scan list"),
):
    """Remove a directory from the meeting recordings scan list."""
    resolved = str(Path(path).expanduser().resolve())
    if cfg.remove_meeting_dir(resolved):
        console.print(f"[yellow]Removed:[/yellow] {resolved}")
    else:
        console.print(f"[red]Not found in config:[/red] {resolved}")


@app.command("scan")
def scan(
    directory: str = typer.Argument(..., help="Root directory to scan for git repos"),
    depth: int = typer.Option(3, "--depth", "-d", help="Max subdirectory depth to search"),
):
    """Scan a directory for git repos and add them all to the config."""
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        console.print(f"[red]Directory not found: {root}[/red]")
        raise typer.Exit(1)

    console.print(f"Scanning [cyan]{root}[/cyan] (depth={depth})...")
    found = _find_git_repos(root, max_depth=depth)

    if not found:
        console.print(f"[yellow]No git repos found under {root}[/yellow]")
        return

    added = 0
    for repo in sorted(found):
        repo_str = str(repo)
        if cfg.add_git_path(repo_str):
            console.print(f"  [green]+[/green] {repo_str}")
            added += 1
        else:
            console.print(f"  [dim]already tracked[/dim]  {repo_str}")

    console.print(f"\n[green]Done. {added} new repo(s) added.[/green]")


def _fmt_interval(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        m = seconds // 60
        s = seconds % 60
        return f"{m}m {s}s" if s else f"{m}m"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}m" if m else f"{h}h"


def _find_git_repos(root: Path, max_depth: int, _depth: int = 0) -> list[Path]:
    if _depth > max_depth:
        return []
    repos = []
    try:
        for entry in root.iterdir():
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if (entry / ".git").exists():
                repos.append(entry)
                # don't recurse into nested repos
            else:
                repos.extend(_find_git_repos(entry, max_depth, _depth + 1))
    except PermissionError:
        pass
    return repos
