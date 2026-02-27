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

    console.print(f"[bold green]Listening...[/bold green] [dim]({duration}s)[/dim]")
    for remaining in range(duration, 0, -1):
        console.print(f"  [dim]{remaining}[/dim]", end="\r")
        time.sleep(1)
    console.print()

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
    type: str | None = typer.Option(None, "--type", "-t", help="Filter by memory type"),
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

        console.print(f'\nSearching for: [bold]"{text}"[/bold]\n')
        query = text

    elif query is None:
        console.print("[red]Provide a query or use --voice.[/red]")
        raise typer.Exit(1)

    store = get_store()
    vector = embed(query)
    results = store.hybrid_search(query, vector, k=k * 3)

    if type:
        results = [r for r in results if r.get("type") == type]
    if repo:
        results = [r for r in results if r.get("repo") == repo]

    results = results[:k]

    if not results:
        console.print("[yellow]No memories found.[/yellow]")
        return

    table = Table(title=f"Results for: {query}")
    table.add_column("Type", style="cyan", width=16)
    table.add_column("Summary", style="white")
    table.add_column("Repo", style="green", width=16)
    table.add_column("Importance", justify="right", width=10)

    for r in results:
        table.add_row(
            r.get("type", ""),
            r.get("summary", "")[:80],
            r.get("repo", "N/A") or "N/A",
            f"{r.get('importance', 0.5):.1f}",
        )

    console.print(table)

    if speak and results:
        top = results[0].get("summary", "")[:100]
        try:
            subprocess.run(["say", top], check=True)
        except Exception:
            console.print("[yellow]Could not speak result (macOS only).[/yellow]")
