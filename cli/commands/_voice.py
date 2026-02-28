"""Shared voice input utility for CLI commands."""

from rich.console import Console

console = Console()


def record_and_transcribe(duration: int = 8) -> tuple[str, float]:
    """Record audio and transcribe via Whisper. Returns (text, avg_no_speech_prob).

    Raises ImportError if voice extras are not installed.
    """
    import time
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


def transcribe_or_exit(duration: int = 8) -> str:
    """Record, transcribe, validate, and return the query text.

    Prints errors and raises SystemExit on failure so callers don't need
    to repeat the validation boilerplate.
    """
    import typer

    try:
        text, avg_no_speech = record_and_transcribe(duration=duration)
    except ImportError:
        console.print("[red]Voice input requires voice extras: uv pip install -e '.[voice]'[/red]")
        raise typer.Exit(1)

    if not text or avg_no_speech > 0.5:
        console.print("[yellow]Could not understand audio. Try again.[/yellow]")
        raise typer.Exit(1)

    if len(text.split()) < 2:
        console.print("[yellow]Query too short. Try again.[/yellow]")
        raise typer.Exit(1)

    return text
