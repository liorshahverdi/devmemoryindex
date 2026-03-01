"""
devmemory health — Memory store quality dashboard (T1-E)

Prints a human-readable health report: type breakdown, importance histogram,
avg times_accessed, stale count, and low-CTR memories.
"""

import json
import typer
from rich.console import Console
from rich.table import Table
from rich import box
from core.store_provider import get_store

console = Console()


def health(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show memory store quality metrics and health indicators."""
    store = get_store()
    report = store.get_store_health()

    if as_json:
        console.print_json(json.dumps(report))
        return

    # Summary line
    total = report["total"]
    active = report["active"]
    deprecated = report["deprecated"]
    console.print(f"\n[bold]Memory Store Health[/bold]  [dim]({total} total, {active} active, {deprecated} deprecated)[/dim]\n")

    # Type breakdown table
    breakdown = report["type_breakdown"]
    if breakdown:
        t = Table("Type", "Count", box=box.SIMPLE, show_header=True, header_style="bold cyan")
        for mem_type, count in sorted(breakdown.items(), key=lambda x: -x[1]):
            t.add_row(mem_type, str(count))
        console.print(t)

    # Importance histogram
    hist = report["importance_histogram"]
    console.print("[bold]Importance Distribution:[/bold]")
    for bucket, count in hist.items():
        bar = "█" * min(count, 40)
        console.print(f"  {bucket:>10}  {bar} {count}")

    console.print()

    # Access stats
    avg_acc = report["avg_times_accessed"]
    stale = report["stale_count"]
    low_ctr = report["low_ctr_count"]

    status_color = "green" if stale == 0 and low_ctr == 0 else "yellow"
    console.print(f"[{status_color}]Avg times accessed:[/{status_color}] {avg_acc}")
    console.print(f"[{'green' if stale == 0 else 'yellow'}]Stale (never accessed, >60 days old):[/{'green' if stale == 0 else 'yellow'}] {stale}")
    console.print(f"[{'green' if low_ctr == 0 else 'yellow'}]Low CTR (retrieved 5+× but accessed <10%):[/{'green' if low_ctr == 0 else 'yellow'}] {low_ctr}")

    if deprecated > 0:
        console.print(f"\n[dim]Run [bold]devmemory audit[/bold] to review {deprecated} deprecated memories.[/dim]")

    console.print()
