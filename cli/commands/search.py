import subprocess
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from core.store_provider import get_store
from core.embeddings import embed

console = Console()


def search(
    query: Optional[str] = typer.Argument(None, help="Natural language search query"),
    k: int = typer.Option(5, "--limit", "-k", help="Number of results"),
    memory_type: str | None = typer.Option(None, "--type", "-t", help="Filter by memory type"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Filter by repo name"),
    speaker: str | None = typer.Option(None, "--speaker", help="Filter by speaker name (use 'self' for your own utterances)"),
    voice: bool = typer.Option(False, "--voice", help="Speak your query instead of typing"),
    speak: bool = typer.Option(False, "--speak", help="Read top result aloud (macOS say)"),
):
    """Search your developer memory."""
    if voice:
        from cli.commands._voice import transcribe_or_exit
        text = transcribe_or_exit(duration=8)
        from core.intent_classifier import classify_intent as _ci
        _label, _ = _ci(text)
        intent_str = f" [dim](intent: {_label})[/dim]" if _label != "general" else ""
        console.print(f'\nSearching for: [bold]"{text}"[/bold]{intent_str}\n')
        query = text

    elif query is None:
        console.print("[red]Provide a query or use --voice.[/red]")
        raise typer.Exit(1)

    from core.intent_classifier import classify_intent
    intent_label, routing = classify_intent(query)

    store = get_store()
    vector = embed(query)
    results = store.hybrid_search(
        query, vector, k=k,
        type_filter=memory_type,
        repo_filter=repo,
        speaker_filter=speaker,
    )

    # Recall intent: sort by timestamp descending
    if routing.get("sort_by_time"):
        results = sorted(results, key=lambda r: r.get("timestamp") or 0, reverse=True)

    if not results:
        console.print("[yellow]No memories found.[/yellow]")
        return

    is_recall = routing.get("sort_by_time", False)

    table = Table(title=f"Results for: {query}")
    if is_recall:
        table.add_column("Date", style="dim", width=12)
    table.add_column("ID", style="dim", width=10)
    table.add_column("Type", style="cyan", width=16)
    table.add_column("Summary", style="white")
    table.add_column("Repo", style="green", width=16)

    for r in results:
        ts = r.get("timestamp")
        try:
            date_str = ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)[:10]
        except Exception:
            date_str = ""

        short_id = (r.get("id") or "")[:8]
        row = [short_id, r.get("type", ""), r.get("summary", "")[:80], r.get("repo", "N/A") or "N/A"]
        if is_recall:
            table.add_row(date_str, *row)
        else:
            table.add_row(*row)

    console.print(table)

    if speak and results:
        top = results[0].get("summary", "")[:100]
        try:
            subprocess.run(["say", top], check=True)
        except Exception:
            console.print("[yellow]Could not speak result (macOS only).[/yellow]")
