from rich.console import Console
from rich.table import Table
from core.store_provider import get_store
from collections import Counter

console = Console()

def stats():
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