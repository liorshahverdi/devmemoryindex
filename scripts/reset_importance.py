"""
One-time script to clamp all memory importance values to 0.8.

Fixes memories that have drifted above 0.8 due to over-aggressive reinforcement.

Usage:
    uv run python scripts/reset_importance.py           # dry-run
    uv run python scripts/reset_importance.py --yes     # apply
"""
import typer
from rich.console import Console
from core.store_provider import get_store

console = Console()
app = typer.Typer()


@app.command()
def main(yes: bool = typer.Option(False, "--yes", help="Apply the reset (default is dry-run)")):
    store = get_store()
    rows = store.get_all()

    bloated = [r for r in rows if r.get("importance", 0) > 0.8]
    console.print(f"Found {len(bloated)} memories with importance > 0.8")

    if not bloated:
        console.print("[green]Nothing to reset.[/green]")
        return

    for r in bloated:
        console.print(f"  [{r.get('repo', '?')}] {r['summary'][:60]} — {r['importance']:.2f} → 0.8")

    if not yes:
        console.print("\n[yellow]Dry-run. Pass --yes to apply.[/yellow]")
        return

    reset = 0
    for r in bloated:
        try:
            store.collection.update(
                where=f"id = '{r['id']}'",
                values={"importance": 0.8},
            )
            reset += 1
        except Exception as e:
            console.print(f"[red]Failed to reset {r['id'][:8]}: {e}[/red]")

    console.print(f"\n[green]Reset {reset} memories.[/green]")


if __name__ == "__main__":
    app()
