import typer
from rich.console import Console
from connectors.registry import get_connectors

console = Console()


def _source_help() -> str:
    names = ", ".join(C.name for C in get_connectors.__globals__["ALL_CONNECTORS"])
    return f"Specific connector: {names}. Omit to run all."


def ingest(
    source: str | None = typer.Option(
        None, "--source", "-s",
        help=_source_help(),
    ),
):
    """Run memory connectors to ingest developer knowledge."""
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
        except Exception as e:
            console.print(f"  [red][{c.name}] Error: {e}[/red]")

    console.print(f"\n[green]Ingestion complete. {total} new memories added.[/green]")
