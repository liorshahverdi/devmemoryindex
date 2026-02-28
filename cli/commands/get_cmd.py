import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from core.store_provider import get_store

console = Console()


def get(
    memory_id: str = typer.Argument(..., help="Memory ID or 8-char prefix shown in search results"),
):
    """Inspect a single memory by ID (or unique 8-char prefix)."""
    store = get_store()

    # Try exact match first (fast path)
    record = store.get_by_id(memory_id)

    # If not found, try prefix match across all records
    if record is None:
        prefix = memory_id.lower()
        matches = [r for r in store.get_all() if r.get("id", "").startswith(prefix)]
        if len(matches) == 1:
            record = matches[0]
        elif len(matches) > 1:
            console.print(
                f"[yellow]Ambiguous prefix '{memory_id}' matches {len(matches)} memories. "
                "Use more characters.[/yellow]"
            )
            for m in matches[:5]:
                console.print(f"  {m.get('id', '')[:16]}  {m.get('summary', '')[:60]}")
            raise typer.Exit(1)

    if record is None:
        console.print(f"[red]No memory found with ID or prefix:[/red] {memory_id}")
        raise typer.Exit(1)

    _print_memory(record)


def _print_memory(r: dict) -> None:
    ts = r.get("timestamp")
    try:
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(ts, "strftime") else str(ts)
    except Exception:
        ts_str = str(ts)

    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim")
    meta.add_column()
    meta.add_row("ID",         r.get("id", ""))
    meta.add_row("Type",       r.get("type", ""))
    meta.add_row("Repo",       r.get("repo", "") or "—")
    meta.add_row("Source",     r.get("source", "") or "—")
    meta.add_row("Importance", str(r.get("importance", "")))
    meta.add_row("Tags",       ", ".join(r.get("tags") or []) or "—")
    meta.add_row("Timestamp",  ts_str)

    console.print(Panel(meta, title="[bold]Memory[/bold]", border_style="dim"))
    console.print()
    console.print(Panel(
        Text(r.get("raw_text", "") or r.get("summary", ""), overflow="fold"),
        title="[bold]Content[/bold]",
        border_style="cyan",
    ))
