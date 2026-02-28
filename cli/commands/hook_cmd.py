"""
devmemory hook — manage git post-commit hooks for instant indexing.

Commands:
  install   [repo]  — install the devmemory block into a repo's post-commit hook
  uninstall [repo]  — remove the devmemory block from a repo's post-commit hook
  status    [repo]  — show hook installation state for one or all configured repos
"""

import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table

import core.config as cfg
from core.hooks import install_hook, uninstall_hook, hook_status

app = typer.Typer(help="Manage git post-commit hooks for instant memory indexing.")
console = Console()


def _resolve_repo(repo: str | None) -> str | None:
    """Return an absolute repo path, defaulting to cwd if not given."""
    if repo:
        return str(Path(repo).expanduser().resolve())
    cwd = str(Path.cwd())
    if (Path(cwd) / ".git").is_dir():
        return cwd
    return None


@app.command()
def install(
    repo: str | None = typer.Argument(None, help="Path to git repo (defaults to cwd)"),
):
    """Install the devmemory post-commit hook."""
    path = _resolve_repo(repo)
    if path is None:
        console.print("[red]No git repo found.[/red] Pass a path or run from inside a repo.")
        raise typer.Exit(1)

    result = install_hook(path)

    if result == "installed":
        console.print(f"[green]Hook installed[/green] in {path}")
        console.print("  Every [bold]git commit[/bold] will now run [bold]devmemory ingest --source git[/bold] in the background.")
    elif result == "appended":
        console.print(f"[green]Hook appended[/green] to existing post-commit hook in {path}")
    elif result == "already_installed":
        console.print(f"[yellow]Already installed[/yellow] in {path}")
    elif result == "error_not_a_repo":
        console.print(f"[red]Not a git repo:[/red] {path}")
        raise typer.Exit(1)


@app.command()
def uninstall(
    repo: str | None = typer.Argument(None, help="Path to git repo (defaults to cwd)"),
):
    """Remove the devmemory post-commit hook."""
    path = _resolve_repo(repo)
    if path is None:
        console.print("[red]No git repo found.[/red] Pass a path or run from inside a repo.")
        raise typer.Exit(1)

    result = uninstall_hook(path)

    if result == "removed":
        console.print(f"[green]Hook removed[/green] from {path}")
    elif result == "deleted":
        console.print(f"[green]Hook deleted[/green] (was the only content) from {path}")
    elif result == "not_installed":
        console.print(f"[yellow]Not installed[/yellow] in {path}")
    elif result == "error_not_a_repo":
        console.print(f"[red]Not a git repo:[/red] {path}")
        raise typer.Exit(1)


@app.command()
def status(
    repo: str | None = typer.Argument(None, help="Path to git repo (defaults to all configured repos)"),
):
    """Show hook installation status for one repo or all configured repos."""
    if repo:
        path = _resolve_repo(repo)
        if path is None:
            console.print(f"[red]Not a git repo:[/red] {repo}")
            raise typer.Exit(1)
        repos = [path]
    else:
        repos = [str(Path(p).expanduser().resolve()) for p in cfg.get_git_paths()]
        # Also include cwd if it's a git repo and not already listed
        cwd = str(Path.cwd())
        if (Path(cwd) / ".git").is_dir() and cwd not in repos:
            repos.append(cwd)

    if not repos:
        console.print("[yellow]No repos configured.[/yellow] Run [bold]devmemory config add-repo <path>[/bold] or pass a path.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Repo")
    table.add_column("Hook installed")

    for r in repos:
        installed = hook_status(r)
        mark = "[green]✓[/green]" if installed else "[dim]✗[/dim]"
        table.add_row(r, mark)

    console.print(table)
