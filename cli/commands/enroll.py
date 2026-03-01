import tempfile
import time
import typer
from rich.console import Console

from core.speaker_profile import save_profile, PROFILE_PATH

SAMPLE_RATE = 16000
DURATION = 30  # seconds — enough for a robust embedding

console = Console()


def enroll():
    """Record your voice (30s) and save a speaker profile for speaker identification."""
    try:
        import sounddevice as sd
        import scipy.io.wavfile as wav
    except ImportError:
        console.print(
            "[red]Audio dependencies not installed.[/red] "
            "Run: [bold]uv pip install 'devmemoryindex[voice]'[/bold]"
        )
        raise typer.Exit(1)

    console.print(
        "[cyan]Recording for 30 seconds.[/cyan] "
        "Speak naturally — describe your current project, read some code aloud, etc."
    )
    console.print("Starting in 3...")
    time.sleep(3)

    audio = sd.rec(DURATION * SAMPLE_RATE, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    console.print("Recording complete. Extracting voiceprint...")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav.write(f.name, SAMPLE_RATE, audio)
        embedding = _extract_embedding(f.name)

    user_name = typer.prompt("Your name (used for speaker tagging in meeting transcripts)", default="").strip() or None
    save_profile(embedding, user_name=user_name)
    if user_name:
        console.print(f"[green]Voiceprint saved to {PROFILE_PATH}[/green] (enrolled as [bold]{user_name}[/bold])")
    else:
        console.print(f"[green]Voiceprint saved to {PROFILE_PATH}[/green]")
    console.print("Run [bold]devmemory voice enroll[/bold] again any time to re-enroll.")


def _extract_embedding(wav_path: str):
    try:
        from pyannote.audio import Model, Inference
    except ImportError:
        console.print(
            "[red]pyannote.audio not installed.[/red] "
            "Run: [bold]uv pip install 'devmemoryindex[voice]'[/bold]"
        )
        raise typer.Exit(1)

    model = Model.from_pretrained("pyannote/embedding", use_auth_token=True)
    inference = Inference(model, window="whole")

    # Load audio into-memory (use scipy to avoid adding soundfile dependency)
    try:
        import torch
        import numpy as np
        from scipy.io import wavfile as wavreader

        sample_rate, data = wavreader.read(wav_path)

        # Convert integer PCM to float32 in [-1, 1]
        if np.issubdtype(data.dtype, np.integer):
            info = np.iinfo(data.dtype)
            data = data.astype("float32") / float(info.max)
        else:
            data = data.astype("float32")

    except Exception:
        # Fallback to letting pyannote handle the file path
        return inference(wav_path)

    if data.ndim == 1:
        waveform = torch.from_numpy(data).unsqueeze(0)
    else:
        waveform = torch.from_numpy(data.T)

    return inference({"waveform": waveform, "sample_rate": int(sample_rate)})
