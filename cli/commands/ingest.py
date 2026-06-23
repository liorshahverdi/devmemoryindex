import typer
from rich.console import Console

from connectors.filesystem_connector import FilesystemConnector
from connectors.registry import ACTIVE_CONNECTOR_NAMES, get_connectors

console = Console()


def _filesystem_progress(event: dict) -> None:
    if event.get("event") == "root":
        console.print(f"  [filesystem] scanning {event.get('root')}")
    elif event.get("event") == "file":
        inspected = event.get("inspected", 0)
        added = event.get("added", 0)
        skipped = event.get("skipped")
        suffix = f", skipped={skipped}" if skipped else ""
        console.print(f"  [filesystem] inspected={inspected}, added={added}{suffix}")


def _format_stats(stats: dict) -> str:
    skipped = stats.get("skipped", {}) or {}
    skipped_text = ", ".join(f"{k}={v}" for k, v in sorted(skipped.items())) or "none"
    return (
        f"inspected={stats.get('inspected', 0)}, "
        f"chunks_added={stats.get('chunks_added', 0)}, "
        f"skipped: {skipped_text}, "
        f"errors={stats.get('errors', 0)}"
    )


def ingest(
    source: str | None = typer.Option(
        None, "--source", "-s",
        help=f"Specific connector: {', '.join(ACTIVE_CONNECTOR_NAMES)}. Omit to run all.",
    ),
    repo: str | None = typer.Option(
        None,
        "--repo",
        help="Filesystem source only: scan roots whose repo/directory name matches this value.",
    ),
    max_files: int | None = typer.Option(
        None,
        "--max-files",
        min=1,
        help="Filesystem source only: inspect at most this many eligible files in this run.",
    ),
):
    """Run memory connectors to ingest developer knowledge."""
    if (repo or max_files) and source != "filesystem":
        console.print("[red]--repo and --max-files are only supported with --source filesystem.[/red]")
        raise typer.Exit(2)

    if source == "filesystem":
        connectors = [FilesystemConnector(repo=repo, max_files=max_files, progress_callback=_filesystem_progress)]
    else:
        connectors = get_connectors([source]) if source else get_connectors()

    if not connectors:
        console.print(f"[yellow]No connector found for source '{source}'.[/yellow]")
        raise typer.Exit(1)

    total = 0
    for c in connectors:
        try:
            count = c.collect()
            total += count
            console.print(f"  [{c.name}] +{count} memories")
            if c.name == "filesystem" and hasattr(c, "last_stats"):
                console.print(f"  [{c.name}] {_format_stats(c.last_stats)}")
        except Exception as e:
            console.print(f"  [red][{c.name}] Error: {e}[/red]")

    console.print(f"\n[green]Ingestion complete. {total} new memories added.[/green]")
