"""Wake word detection for DevMemoryIndex — Phase 8.1.

Listens continuously on the default microphone for the configured wake phrase
(default: "hey jarvis" via the bundled openWakeWord model; swap for a custom
"hey devmem" .onnx model via config).

On detection:
  1. Plays a short two-tone acknowledgment chime.
  2. Posts a detection event to `detection_queue` for the voice pipeline (8.3)
     to consume.

Usage:
    from daemon.wake_word import start_wake_word_thread, detection_queue

    start_wake_word_thread()

    # Blocks until wake word is detected:
    event = detection_queue.get()   # {"score": float, "time": float}

Configuration (config.toml [jarvis] section):
    wake_threshold = 0.5      # 0.0–1.0, higher = fewer false positives
    wake_model    = ""        # path to custom .onnx model; empty = bundled hey_jarvis

Install:
    uv pip install 'devmemoryindex[jarvis]'
"""

import queue
import threading
import time
from pathlib import Path

import daemon.daemon_log as dlog

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

# Consumer (voice pipeline) reads from this queue.
# maxsize=1: if the pipeline is still busy, the next detection is dropped
# rather than piling up stale events.
detection_queue: queue.Queue = queue.Queue(maxsize=1)

_SAMPLE_RATE = 16_000
_CHUNK_SAMPLES = 1_280       # 80 ms at 16 kHz — openWakeWord's expected frame size
_DEFAULT_THRESHOLD = 0.5
_COOLDOWN_SECONDS = 3.0      # suppress re-detection for this long after each hit
_BUNDLED_MODEL = "hey_jarvis"  # shipped with openwakeword; replace with hey_devmem later

_running = False
_thread: threading.Thread | None = None


# ---------------------------------------------------------------------------
# Acknowledgment chime
# ---------------------------------------------------------------------------

def _play_chime() -> None:
    """Play a short two-tone ascending chime (non-blocking caller, blocking internally)."""
    try:
        import numpy as np
        import sounddevice as sd

        sr = 22_050
        fade_samples = int(sr * 0.01)  # 10 ms fade to avoid clicks

        def _tone(freq: float, duration: float, volume: float = 0.3) -> np.ndarray:
            n = int(sr * duration)
            t = np.linspace(0, duration, n, endpoint=False)
            wave = (volume * np.sin(2 * np.pi * freq * t)).astype(np.float32)
            # Fade in/out
            wave[:fade_samples] *= np.linspace(0, 1, fade_samples)
            wave[-fade_samples:] *= np.linspace(1, 0, fade_samples)
            return wave

        silence = np.zeros(int(sr * 0.04), dtype=np.float32)
        chime = np.concatenate([_tone(880, 0.12), silence, _tone(1046, 0.10)])
        sd.play(chime, samplerate=sr, blocking=True)
    except Exception:
        pass  # chime is best-effort; never crash the listener thread


# ---------------------------------------------------------------------------
# Listener thread
# ---------------------------------------------------------------------------

def _listener_thread(threshold: float, model_path: str | None) -> None:
    global _running

    # --- import guard ---------------------------------------------------------
    try:
        import numpy as np          # noqa: F401  (used via openwakeword internally)
        import sounddevice as sd
        from openwakeword.model import Model
    except ImportError as exc:
        dlog.write(
            f"[wake_word] Cannot start — missing dependency: {exc}. "
            "Install with: uv pip install 'devmemoryindex[jarvis]'",
            "WARN",
        )
        return

    # --- load model -----------------------------------------------------------
    try:
        if model_path and Path(model_path).exists():
            oww = Model(wakeword_models=[model_path], inference_framework="onnx")
            model_label = Path(model_path).stem
        else:
            if model_path:
                dlog.write(
                    f"[wake_word] Model path not found: {model_path!r}; "
                    f"falling back to bundled '{_BUNDLED_MODEL}'",
                    "WARN",
                )
            oww = Model(wakeword_models=[_BUNDLED_MODEL], inference_framework="onnx")
            model_label = _BUNDLED_MODEL
    except Exception as exc:
        dlog.write(f"[wake_word] Model load failed: {exc}", "ERROR")
        return

    dlog.write(
        f"[wake_word] Listening — model={model_label!r}  threshold={threshold}  "
        f"device=default mic"
    )
    _running = True
    last_detection: float = 0.0

    try:
        with sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=_CHUNK_SAMPLES,
        ) as stream:
            while _running:
                chunk, _overflowed = stream.read(_CHUNK_SAMPLES)
                audio = chunk.squeeze()  # (1280, 1) → (1280,)

                predictions = oww.predict(audio)
                score = max(predictions.values()) if predictions else 0.0

                now = time.monotonic()
                if score >= threshold and (now - last_detection) > _COOLDOWN_SECONDS:
                    last_detection = now
                    dlog.write(f"[wake_word] Detected — score={score:.2f}")

                    # Non-blocking put: drop if the pipeline hasn't consumed yet
                    try:
                        detection_queue.put_nowait({"score": score, "time": now})
                    except queue.Full:
                        dlog.write("[wake_word] Pipeline busy — detection dropped", "WARN")

                    threading.Thread(target=_play_chime, daemon=True).start()

    except Exception as exc:
        dlog.write(f"[wake_word] Listener error: {exc}", "ERROR")
    finally:
        _running = False
        dlog.write("[wake_word] Listener stopped")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_wake_word_thread(
    threshold: float | None = None,
    model_path: str | None = None,
) -> threading.Thread:
    """Start the wake word listener as a background daemon thread.

    Args:
        threshold:  Detection confidence (0.0–1.0). Falls back to
                    config [jarvis] wake_threshold, then 0.5.
        model_path: Path to a custom .onnx wake word model. Falls back to
                    config [jarvis] wake_model, then the bundled hey_jarvis model.

    Returns the started thread. It is a daemon thread — it exits automatically
    when the main process terminates.
    """
    global _thread

    if threshold is None:
        try:
            from core.config import load as _cfg
            threshold = float(_cfg().get("jarvis", {}).get("wake_threshold", _DEFAULT_THRESHOLD))
        except Exception:
            threshold = _DEFAULT_THRESHOLD

    if model_path is None:
        try:
            from core.config import load as _cfg
            model_path = _cfg().get("jarvis", {}).get("wake_model") or None
        except Exception:
            model_path = None

    _thread = threading.Thread(
        target=_listener_thread,
        args=(threshold, model_path),
        daemon=True,
        name="devmemory-wake-word",
    )
    _thread.start()
    return _thread


def stop() -> None:
    """Signal the listener thread to stop on its next iteration."""
    global _running
    _running = False


def is_running() -> bool:
    return _running and (_thread is not None) and _thread.is_alive()
