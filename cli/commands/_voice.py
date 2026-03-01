"""Shared voice input utility for CLI commands."""

import os
from rich.console import Console

console = Console()


def record_and_transcribe(duration: int = 8) -> tuple[str, float, "np.ndarray"]:
    """Record audio and transcribe via Whisper.

    Returns (text, avg_no_speech_prob, audio_f32).
    audio_f32 is the raw float32 waveform — callers can use it for speaker
    verification without re-recording.

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
    whisper_model = os.environ.get("DEVMEMORY_WHISPER_MODEL", "tiny")
    model = whisper.load_model(whisper_model)
    result = model.transcribe(audio_f32)

    text = result["text"].strip()
    segments = result.get("segments", [])
    avg_no_speech = (
        sum(s.get("no_speech_prob", 0.0) for s in segments) / len(segments)
        if segments else 0.0
    )
    return text, avg_no_speech, audio_f32


def _verify_speaker(audio_f32: "np.ndarray", sample_rate: int = 16000) -> bool:
    """Return True if audio matches the enrolled speaker profile (or if unverifiable).

    Returns True when:
      - No profile is enrolled (no regression for unenrolled users).
      - pyannote is not installed (graceful degradation).
      - Embedding extraction fails for any reason.

    Returns False only when a profile IS enrolled and the audio does NOT match.
    """
    from core.speaker_profile import load_profile, is_self

    profile = load_profile()
    if profile is None:
        return True  # no profile enrolled — open access

    try:
        import torch
        import numpy as np
        from pyannote.audio import Model, Inference

        model = Model.from_pretrained("pyannote/embedding", use_auth_token=True)
        inference = Inference(model, window="whole")

        waveform = torch.from_numpy(audio_f32).unsqueeze(0)
        embedding = inference({"waveform": waveform, "sample_rate": sample_rate})
        from scipy.spatial.distance import cosine as _cosine
        distance = float(_cosine(embedding, profile["embedding"] if isinstance(profile, dict) else profile))
        import daemon.daemon_log as _dlog
        _dlog.write(f"[speaker] cosine distance={distance:.4f}  threshold=0.85")
        return distance < 0.85
    except ImportError:
        # pyannote not installed — warn but allow through
        console.print("[dim yellow]Speaker verification skipped (pyannote not installed).[/dim yellow]")
        return True
    except Exception:
        # Any other error (model download, GPU unavailable, etc.) — allow through
        return True


def transcribe_or_exit(duration: int = 8) -> str:
    """Record, transcribe, verify speaker, and return the query text.

    Prints errors and raises SystemExit on failure so callers don't need
    to repeat the validation boilerplate.

    Speaker verification behaviour:
      - Profile enrolled  → voice queries require your voice; rejected with a clear error.
      - No profile        → voice queries work for anyone (no regression).
      - pyannote missing  → verification skipped with a warning, query proceeds.
    """
    import typer

    try:
        text, avg_no_speech, audio_f32 = record_and_transcribe(duration=duration)
    except ImportError:
        console.print("[red]Voice input requires voice extras: uv pip install -e '.[voice]'[/red]")
        raise typer.Exit(1)

    if not text or avg_no_speech > 0.5:
        console.print("[yellow]Could not understand audio. Try again.[/yellow]")
        raise typer.Exit(1)

    if len(text.split()) < 2:
        console.print("[yellow]Query too short. Try again.[/yellow]")
        raise typer.Exit(1)

    if not _verify_speaker(audio_f32):
        console.print("[red]Speaker not recognised. Voice queries require your enrolled voice.[/red]")
        raise typer.Exit(1)

    return text
