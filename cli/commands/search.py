import typer
from rich.console import Console
from rich.table import Table
from core.store_provider import get_store
from core.embeddings import embed

console = Console()

def search(
    query: str = typer.Argument(..., help="Natural language search query"),
    k: int = typer.Option(5, "--limit", "-k", help="Number of results"),
    type: str | None = typer.Option(None, "--type", "-t", help="Filter by memory type"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Filter by repo name"),
):
    """Search your developer memory."""
    store = get_store()
    vector = embed(query)

    # TODO: Uses `semantic_search()` for now.
    # After Phase 1.5 (hybrid search), update this to call `hybrid_search()` instead.
    results = store.semantic_search(vector, k=k * 3)

    # Apply CLI filters
    if type:
        results = [r for r in results if r.get("type") == type]
    if repo:
        results = [r for r in results if r.get("repo") == repo]

    results = results[:k]

    if not results:
        console.print("[yellow]No memories found.[/yellow]")
        return

    table = Table(title=f"Results for: {query}")
    table.add_column("Type", style="cyan", width=16)
    table.add_column("Summary", style="white")
    table.add_column("Repo", style="green", width=16)
    table.add_column("Importance", justify="right", width=10)

    for r in results:
        table.add_row(
            r.get("type", ""),
            r.get("summary", "")[:80],
            r.get("repo", "N/A") or "N/A",
            f"{r.get('importance', 0.5):.1f}",
        )

    console.print(table)