"""
devmemory consolidate — Merge multiple memories into one canonical entry (T1-C)

Fetches memories by ID, combines their raw_text, stores a new consolidated
memory at max(importance), and permanently deletes the originals.
"""

import typer
from typing import List
from rich.console import Console
from core.store_provider import get_store

console = Console()


def consolidate(
    ids: List[str] = typer.Argument(..., help="Memory IDs to consolidate (minimum 2)"),
    summary: str = typer.Option("", "--summary", "-s", help="Custom summary for the new consolidated memory"),
) -> None:
    """Merge multiple redundant memories into one canonical entry."""
    if len(ids) < 2:
        console.print("[red]Error: provide at least 2 memory IDs to consolidate.[/red]")
        raise typer.Exit(1)

    store = get_store()
    result = store.consolidate(ids, summary=summary or None)

    if result["status"] == "error":
        console.print(f"[red]Error: {result['message']}[/red]")
        raise typer.Exit(1)

    new_id = result["new_id"]
    deleted = result["deleted"]
    console.print(
        f"[green]Consolidated {deleted} memories into new memory [bold]{new_id[:16]}...[/bold][/green]"
    )
    console.print(f"[dim]Run [bold]devmemory get {new_id}[/bold] to inspect the result.[/dim]")
