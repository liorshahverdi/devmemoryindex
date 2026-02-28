import typer
from rich.console import Console
from rich.table import Table
from core.store_provider import get_store
from collections import Counter

console = Console()

def stats(
    quality: bool = typer.Option(False, "--quality", help="Show summary length distribution and flag low-quality summaries."),
    engagement: bool = typer.Option(False, "--engagement", help="Show retrieval-to-access click-through rates and flag low-engagement memories."),
):
    """Show memory store statistics."""
    store = get_store()
    total = store.count()

    console.print(f"\n[bold]DevMemoryIndex Stats[/bold]")
    console.print(f"Total memories: {total}")

    try:
        arrow_table = store.collection.to_arrow()
        type_col = arrow_table.column("type").to_pylist()
        type_counts = Counter(type_col)
        table = Table(title="Memories by Type")
        table.add_column("Type", style="cyan")
        table.add_column("Count", justify="right")
        for mem_type, count in sorted(type_counts.items()):
            table.add_row(mem_type, str(count))
        console.print(table)
    except Exception as e:
        console.print(f"[red]Could not load type breakdown: {e}[/red]")

    if quality:
        try:
            q = store.summary_quality()
            console.print(f"\n[bold]Summary Quality[/bold]  (avg length: {q['avg_length']} chars)")
            dist = Table(title="Summary Length Distribution")
            dist.add_column("Length bucket", style="cyan")
            dist.add_column("Count", justify="right")
            dist.add_column("% of total", justify="right")
            for bucket, count in q["buckets"].items():
                pct = f"{100 * count / q['total']:.1f}%" if q["total"] else "—"
                style = "red" if bucket == "<20" else ""
                dist.add_row(bucket, str(count), pct, style=style)
            console.print(dist)

            if q["short"]:
                console.print(f"\n[red bold]Low-quality summaries ({len(q['short'])} flagged)[/red bold]")
                flagged = Table()
                flagged.add_column("ID prefix", style="dim")
                flagged.add_column("Type", style="cyan")
                flagged.add_column("Summary")
                for m in q["short"]:
                    flagged.add_row(m["id"], m["type"], m["summary"] or "[empty]")
                console.print(flagged)
            else:
                console.print("\n[green]No low-quality summaries found.[/green]")
        except Exception as e:
            console.print(f"[red]Could not load quality report: {e}[/red]")

    if engagement:
        try:
            e = store.engagement_report()
            console.print(f"\n[bold]Engagement Report[/bold]  "
                          f"({e['total']} total, {e['untracked']} with < 5 retrievals)")

            if e["low_ctr"]:
                console.print(f"\n[red bold]Low click-through ({len(e['low_ctr'])} flagged — CTR < 10%)[/red bold]")
                low_table = Table()
                low_table.add_column("ID prefix", style="dim")
                low_table.add_column("Type", style="cyan")
                low_table.add_column("Retrieved", justify="right")
                low_table.add_column("Accessed", justify="right")
                low_table.add_column("CTR", justify="right", style="red")
                low_table.add_column("Summary")
                for m in e["low_ctr"]:
                    low_table.add_row(
                        m["id"], m["type"],
                        str(m["times_retrieved"]), str(m["times_accessed"]),
                        f"{m['ctr']:.0%}", m["summary"],
                    )
                console.print(low_table)
            else:
                console.print("\n[green]No low-engagement memories found.[/green]")

            if e["high_ctr"]:
                console.print(f"\n[green bold]High click-through ({len(e['high_ctr'])} memories — CTR ≥ 10%)[/green bold]")
                high_table = Table()
                high_table.add_column("ID prefix", style="dim")
                high_table.add_column("Type", style="cyan")
                high_table.add_column("Retrieved", justify="right")
                high_table.add_column("Accessed", justify="right")
                high_table.add_column("CTR", justify="right", style="green")
                high_table.add_column("Summary")
                for m in e["high_ctr"]:
                    high_table.add_row(
                        m["id"], m["type"],
                        str(m["times_retrieved"]), str(m["times_accessed"]),
                        f"{m['ctr']:.0%}", m["summary"],
                    )
                console.print(high_table)
        except Exception as ex:
            console.print(f"[red]Could not load engagement report: {ex}[/red]")