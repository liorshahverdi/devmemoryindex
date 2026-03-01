"""
devmemory audit — Review and permanently delete deprecated memories (T1-D)

Shows all memories that have been forgotten (status=deprecated) with their
deprecation reasons. Optionally purges them permanently.
"""

import json
import typer
from rich.console import Console
from rich.table import Table
from rich import box
from core.store_provider import get_store

console = Console()


def audit(
    purge: bool = typer.Option(False, "--purge", help="Permanently delete all deprecated memories"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Review deprecated memories and optionally purge them permanently."""
    store = get_store()
    deprecated = store.get_deprecated()

    if as_json:
        output = [
            {
                "id": r.get("id"),
                "summary": r.get("summary"),
                "type": r.get("type"),
                "deprecation_reason": r.get("deprecation_reason", ""),
                "timestamp": str(r.get("timestamp", "")),
            }
            for r in deprecated
        ]
        console.print_json(json.dumps(output))
        return

    if not deprecated:
        console.print("[green]No deprecated memories found.[/green]")
        return

    console.print(f"\n[bold]Deprecated Memories[/bold] ({len(deprecated)})\n")
    t = Table("ID (8)", "Type", "Summary", "Reason", box=box.SIMPLE, header_style="bold cyan")
    for r in deprecated:
        t.add_row(
            (r.get("id") or "")[:8],
            r.get("type", ""),
            (r.get("summary") or "")[:60],
            (r.get("deprecation_reason") or "")[:50],
        )
    console.print(t)

    if purge:
        count = 0
        for r in deprecated:
            try:
                store.delete(r["id"])
                count += 1
            except Exception:
                pass
        console.print(f"\n[red]Permanently deleted {count} deprecated memories.[/red]")
    else:
        console.print(
            "\n[dim]Run [bold]devmemory audit --purge[/bold] to permanently delete these memories.[/dim]"
        )
