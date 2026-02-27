import typer
from rich.console import Console
from core.store_provider import get_store
from core.embeddings import embed

console = Console()


def repl():
    """Start an interactive memory search session (model stays loaded)."""
    store = get_store()
    console.print("[bold cyan]DevMemory REPL[/bold cyan] — type a query, or 'exit' to quit.\n")

    while True:
        try:
            query = input("devmemory> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Exiting REPL.[/yellow]")
            break

        if not query:
            continue
        if query.lower() in {"exit", "quit", "q"}:
            console.print("[yellow]Goodbye.[/yellow]")
            break

        vector = embed(query)
        results = store.hybrid_search(query, vector, k=5)

        if not results:
            console.print("[yellow]No results.[/yellow]\n")
            continue

        for i, r in enumerate(results, 1):
            console.print(
                f"[cyan]{i}.[/cyan] [{r.get('type', '')}] "
                f"{r.get('summary', '')[:100]}  "
                f"[dim](importance: {r.get('importance', 0.5):.1f})[/dim]"
            )
        console.print()
