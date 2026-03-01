"""Voice pipeline for DevMemoryIndex — Phase 8.3 / 8.4 / 8.2.

State machine:
    PASSIVE    --(wake word detected)--> ACTIVE
    ACTIVE     --(30s silence / "stop")--> PASSIVE
    ACTIVE     --(query spoken)--> PROCESSING
    PROCESSING --(Whisper done)--> RESPONDING
    RESPONDING --(TTS done)--> ACTIVE  (reset 30s timer)

The wake word listener (Phase 8.1) remains untouched; this module only
consumes events from `detection_queue` and owns the conversational state.

Usage (started by daemon/scheduler.py):
    from daemon.voice_pipeline import VoicePipeline
    VoicePipeline().run()   # blocks; run in a daemon thread
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

import daemon.daemon_log as dlog
from daemon.wake_word import detection_queue


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACTIVE_TIMEOUT = 30.0    # seconds of silence before returning to PASSIVE
QUERY_DURATION = 8       # seconds of audio to record per query
VAD_SILENCE_RMS = 0.003  # float32 RMS below this → treat as silence
STOP_PHRASES: frozenset[str] = frozenset({
    "stop", "never mind", "nevermind", "goodbye", "quit", "bye",
})
MAX_HISTORY = 3          # conversation turns to prepend as context

# Phase 8.2 — speaker gate is applied to every query recording.
# Set to False to disable (e.g. during development with no enrolled profile).
SPEAKER_GATE_ENABLED = True


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class VoicePipeline:
    """Conversational voice pipeline consumed by the jarvis daemon thread."""

    STATE_PASSIVE = "passive"
    STATE_ACTIVE  = "active"

    def __init__(self) -> None:
        self._state = self.STATE_PASSIVE
        # conversation history for the current active session: [(user, assistant), …]
        self._history: list[tuple[str, str]] = []

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Blocking main loop — intended to run inside a daemon thread."""
        dlog.write("[pipeline] Voice pipeline running — waiting for wake word")
        while True:
            try:
                event = detection_queue.get()   # blocks until wake word fires
            except Exception as exc:
                dlog.write(f"[pipeline] Queue error: {exc}", "ERROR")
                continue

            score = event.get("score", 0.0)
            dlog.write(f"[pipeline] Wake word — score={score:.2f}  entering ACTIVE")
            self._history.clear()
            self._enter_active()

    # ------------------------------------------------------------------
    # Active session
    # ------------------------------------------------------------------

    def _enter_active(self) -> None:
        self._state = self.STATE_ACTIVE
        deadline = time.monotonic() + ACTIVE_TIMEOUT

        try:
            from cli.commands._speak import StreamingSpeaker
            speaker = StreamingSpeaker()
        except Exception as exc:
            dlog.write(f"[pipeline] StreamingSpeaker init failed: {exc}", "WARN")
            speaker = None

        while time.monotonic() < deadline:
            audio = _record_with_vad(QUERY_DURATION)

            if audio is None:
                # Silence / microphone idle — check if deadline expired
                dlog.write("[pipeline] Silence timeout → returning to PASSIVE")
                break

            # Phase 8.2: Speaker gate — verify every query against enrolled profile.
            # Fail-open: passes through when no profile enrolled or pyannote missing.
            if SPEAKER_GATE_ENABLED and not _check_speaker(audio):
                dlog.write("[pipeline] Speaker not recognised → returning to PASSIVE")
                if speaker:
                    _speak(speaker, "Do I know you?")
                break

            text = _transcribe(audio)
            if not text:
                dlog.write("[pipeline] Transcription empty — continuing active window")
                continue

            cleaned = text.lower().strip().rstrip(".")
            dlog.write(f"[pipeline] Transcribed: {text!r}")

            if cleaned in STOP_PHRASES:
                dlog.write("[pipeline] Stop phrase detected → returning to PASSIVE")
                if speaker:
                    _speak(speaker, "Got it.")
                break

            # --- PROCESSING → RESPONDING ---
            self._state = "processing"
            answer = _answer(text, self._history)

            self._state = "responding"
            from daemon.response_formatter import format_for_voice
            spoken = format_for_voice(answer)
            dlog.write(f"[pipeline] Answer: {spoken[:80]}{'…' if len(spoken) > 80 else ''}")

            # History stores the raw answer for richer follow-up RAG context.
            self._history.append((text, answer))
            if len(self._history) > MAX_HISTORY:
                self._history.pop(0)

            if speaker:
                interrupted = _speak(speaker, spoken)
            else:
                dlog.write(f"[pipeline] (no speaker) {spoken}")
                interrupted = False

            # Reset idle timer after each exchange (always — including interrupts)
            deadline = time.monotonic() + ACTIVE_TIMEOUT
            self._state = self.STATE_ACTIVE

            if interrupted:
                # Wake word fired mid-response; loop immediately to record
                # the follow-up query without waiting for the next VAD window.
                continue

        else:
            dlog.write("[pipeline] Active window expired → returning to PASSIVE")

        self._state = self.STATE_PASSIVE


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _record_with_vad(duration: int = QUERY_DURATION) -> Optional["np.ndarray"]:
    """Record up to `duration` seconds; return None if audio is silence.

    Reads audio from the wake word listener's shared InputStream via the
    subscriber API — no second audio device is ever opened, avoiding macOS
    CoreAudio AUHAL conflicts when both streams request the mic simultaneously.

    Returns float32 numpy array at 16 kHz, or None when the recording is
    below the VAD silence threshold (i.e. nobody spoke).
    """
    try:
        import numpy as np
        from daemon.wake_word import (
            _CHUNK_SAMPLES,
            _SAMPLE_RATE,
            _listener_active,
            subscribe_audio,
            unsubscribe_audio,
        )

        if not _listener_active.wait(timeout=5.0):
            dlog.write("[pipeline] Wake word listener not ready — skipping recording", "WARN")
            return None

        n_chunks = (duration * _SAMPLE_RATE) // _CHUNK_SAMPLES  # e.g. 8 s → 100 chunks
        dlog.write("[pipeline] Listening for query…")

        audio_q = subscribe_audio(maxsize=n_chunks + 20)
        chunks: list = []
        try:
            for _ in range(n_chunks):
                chunk = audio_q.get(timeout=duration + 2.0)
                chunks.append(chunk)
        except Exception:
            pass  # timeout → use whatever was collected
        finally:
            unsubscribe_audio(audio_q)

        if len(chunks) < n_chunks // 2:
            dlog.write("[pipeline] Recording too short — treating as silence")
            return None

        audio_f32 = np.concatenate(chunks).astype("float32") / 32768.0
        rms = float(np.sqrt(np.mean(audio_f32 ** 2)))
        if rms < VAD_SILENCE_RMS:
            dlog.write(f"[pipeline] Silent recording (RMS={rms:.4f}) → treating as silence")
            return None
        return audio_f32

    except ImportError as exc:
        dlog.write(
            f"[pipeline] sounddevice/numpy not available: {exc}  "
            "(install devmemory[jarvis])",
            "WARN",
        )
        return None
    except Exception as exc:
        dlog.write(f"[pipeline] Recording error: {exc}", "ERROR")
        return None


_whisper_model = None  # cached after first load; Whisper is expensive to reload each query


def _transcribe(audio_f32: "np.ndarray") -> str:
    """Whisper transcription — returns cleaned text or empty string on failure.

    Reuses the same Whisper model as `devmemory ask --voice` but without
    sys.exit on failure (daemon must not exit).  The model is cached in
    `_whisper_model` so the 1–2 s load penalty only occurs once per daemon run.
    """
    global _whisper_model
    try:
        import os
        import whisper

        model_name = os.environ.get("DEVMEMORY_WHISPER_MODEL", "tiny")
        if _whisper_model is None:
            dlog.write(f"[pipeline] Loading Whisper model '{model_name}'…")
            _whisper_model = whisper.load_model(model_name)
        model = _whisper_model
        result = model.transcribe(audio_f32)
        text = result.get("text", "").strip()

        segments = result.get("segments", [])
        avg_no_speech = (
            sum(s.get("no_speech_prob", 0.0) for s in segments) / len(segments)
            if segments else 0.0
        )
        if avg_no_speech > 0.5:
            dlog.write(
                f"[pipeline] High no-speech probability ({avg_no_speech:.2f}) — discarding",
                "WARN",
            )
            return ""

        return text

    except ImportError as exc:
        dlog.write(f"[pipeline] Whisper not available: {exc}", "WARN")
        return ""
    except Exception as exc:
        dlog.write(f"[pipeline] Transcription error: {exc}", "ERROR")
        return ""


def _answer(query: str, history: list[tuple[str, str]] | None = None) -> str:
    """Retrieve memories and generate an LLM answer.

    Mirrors the `devmemory ask` pipeline (RAGEngine.ask stream=False).
    Prepends up to MAX_HISTORY prior exchanges as conversation context
    so follow-ups stay coherent within the active window.
    """
    try:
        from core.llm_backend import get_backend
        from core.rag_engine import RAGEngine
        from core.store_provider import get_store

        # Enrich query with recent conversation context
        context_prefix = ""
        if history:
            lines = []
            for user_turn, assistant_turn in history[-MAX_HISTORY:]:
                lines.append(f"User: {user_turn}")
                lines.append(f"Assistant: {assistant_turn[:200]}")
            context_prefix = "\n".join(lines) + "\n\n"

        enriched_query = context_prefix + query if context_prefix else query

        backend = get_backend()
        store = get_store()
        engine = RAGEngine(store, backend)
        answer, _memories, _planned = engine.ask(enriched_query, stream=False, plan=False)
        return answer

    except Exception as exc:
        dlog.write(f"[pipeline] Answer error: {exc}", "ERROR")
        return "Sorry, I couldn't retrieve an answer right now."


def _speak(speaker: "StreamingSpeaker", text: str) -> bool:
    """Feed text to the speaker; block until audio finishes or wake word interrupts.

    Returns True if playback was cut short by a new wake word detection so the
    caller can drain the detection queue and continue the active session.
    """
    try:
        import queue as _queue_mod
        from daemon.wake_word import _tts_interrupt, detection_queue as _dwq

        _tts_interrupt.clear()
        speaker.feed(text)

        # Run finish() in a background thread so we can poll for a wake-word
        # interrupt every 50 ms without blocking the main pipeline thread.
        finish_thread = threading.Thread(target=speaker.finish, daemon=True)
        finish_thread.start()

        while finish_thread.is_alive():
            if _tts_interrupt.is_set():
                speaker.cancel()
                finish_thread.join(timeout=1.0)
                # Drain the stale detection event so run() doesn't re-enter
                # ACTIVE immediately after we return to PASSIVE.
                try:
                    _dwq.get_nowait()
                except _queue_mod.Empty:
                    pass
                _tts_interrupt.clear()
                dlog.write("[pipeline] TTS interrupted by wake word")
                return True
            finish_thread.join(timeout=0.05)

        return False

    except Exception as exc:
        dlog.write(f"[pipeline] TTS error: {exc}", "WARN")
        return False


def _check_speaker(audio_f32: "np.ndarray") -> bool:
    """Return True if audio matches the enrolled speaker profile.

    Delegates to cli.commands._voice._verify_speaker() which handles:
      - No profile enrolled     → True  (open access, no regression)
      - pyannote not installed  → True  (graceful degradation)
      - Profile enrolled + match → True
      - Profile enrolled + no match → False

    Never raises — any infrastructure failure returns True (fail-open) so a
    broken pyannote install never locks the owner out.
    """
    try:
        from cli.commands._voice import _verify_speaker
        result = _verify_speaker(audio_f32)
        dlog.write(f"[pipeline] Speaker check: {'recognised' if result else 'NOT recognised'}")
        return result
    except Exception as exc:
        dlog.write(f"[pipeline] Speaker check error: {exc} — allowing through", "WARN")
        return True
