"""
devmemory map — show a structural overview of indexed files via KMeans clustering.

Phase 7.8
"""

import typer
from rich.console import Console
from rich.table import Table

console = Console()


def map_codebase(
    repo: str = typer.Option(None, "--repo", "-r", help="Filter to a specific repo"),
    clusters: int = typer.Option(8, "--clusters", "-k", help="Number of clusters"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show all files per cluster"),
):
    """Show a structural map of indexed file_content memories via KMeans clustering."""
    from core.store_provider import get_store
    from core.codebase_map import build_codebase_map

    store = get_store()
    result = build_codebase_map(store, repo=repo, n_clusters=clusters)

    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
        raise typer.Exit(1)

    total = result.get("total_files", 0)
    n = len(result["clusters"])
    console.print(f"\n[bold]Codebase Map[/bold] — {total} file memories, {n} clusters\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Label", style="bold")
    table.add_column("Files", justify="right")
    table.add_column("Representative")

    for c in result["clusters"]:
        table.add_row(c["label"], str(c["size"]), c["representative"])

    console.print(table)

    if verbose:
        for c in result["clusters"]:
            if len(c["files"]) > 1:
                console.print(f"\n[cyan]{c['label']}[/cyan] ({c['size']} files):")
                for f in c["files"]:
                    console.print(f"  · {f}")
