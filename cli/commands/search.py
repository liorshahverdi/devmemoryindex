import time
import subprocess
import typer
from typing import Optional
from rich.console import Console
from rich.table import Table
from core.store_provider import get_store
from core.embeddings import embed

console = Console()


def _record_and_transcribe(duration: int = 8) -> tuple[str, float]:
    """Record audio and transcribe via Whisper. Returns (text, avg_no_speech_prob)."""
    import numpy as np
    import sounddevice as sd
    import whisper

    sample_rate = 16000

    for remaining in range(3, 0, -1):
        console.print(f"  [dim]{remaining}[/dim]", end="\r")
        time.sleep(1)
    console.print(f"[bold green]Recording...[/bold green] [dim]({duration}s)[/dim]")

    audio = sd.rec(
        duration * sample_rate,
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
    )
    sd.wait()

    audio_f32 = audio.squeeze().astype("float32") / float(32768)

    model = whisper.load_model("base")
    result = model.transcribe(audio_f32)

    text = result["text"].strip()
    segments = result.get("segments", [])
    avg_no_speech = (
        sum(s.get("no_speech_prob", 0.0) for s in segments) / len(segments)
        if segments else 0.0
    )
    return text, avg_no_speech


def search(
    query: Optional[str] = typer.Argument(None, help="Natural language search query"),
    k: int = typer.Option(5, "--limit", "-k", help="Number of results"),
    memory_type: str | None = typer.Option(None, "--type", "-t", help="Filter by memory type"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Filter by repo name"),
    voice: bool = typer.Option(False, "--voice", help="Speak your query instead of typing"),
    speak: bool = typer.Option(False, "--speak", help="Read top result aloud (macOS say)"),
):
    """Search your developer memory."""
    if voice:
        try:
            text, avg_no_speech = _record_and_transcribe(duration=8)
        except ImportError:
            console.print("[red]Voice search requires voice extras: uv pip install -e '.[voice]'[/red]")
            raise typer.Exit(1)

        if not text or avg_no_speech > 0.5:
            console.print("[yellow]Could not understand audio. Try again.[/yellow]")
            raise typer.Exit(1)

        if len(text.split()) < 2:
            console.print("[yellow]Query too short. Try again.[/yellow]")
            raise typer.Exit(1)

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
