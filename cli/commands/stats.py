import typer
from rich.console import Console
from rich.table import Table
from core.store_provider import get_store

console = Console()

def stats():
    """Show memory store statistics."""
    store = get_store()
    total = store.count()

    console.print(f"\n[bold]DevMemoryIndex Stats[/bold]")
    console.print(f"Total memories: {total}")

    try:
        all_data = store.collection.to_pandas()
        type_counts = all_data["type"].value_counts()
        table = Table(title="Memories by Type")
        table.add_column("Type", style="cyan")
        table.add_column("Count", justify="right")
        for mem_type, count in type_counts.items():
            table.add_row(mem_type, str(count))
        console.print(table)
    except Exception:
        pass