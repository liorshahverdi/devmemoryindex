"""Streaming TTS speaker for CLI commands.

Buffers LLM text chunks and speaks complete sentences as they arrive,
keeping audio roughly in sync with the streaming display.

Preferred backend : edge-tts  en-GB-RyanNeural  (neural, human-like)
                    install:  uv pip install -e '.[speak]'
Fallback backend  : macOS say -v Daniel          (no extra deps, British)
"""

from __future__ import annotations

import queue
import re
import subprocess
import threading

# Sentence boundary: punctuation followed by whitespace or end-of-string.
_SENTENCE_RE = re.compile(r"(?<=[.!?])[ \t]+|(?<=[.!?])$")


def _edge_tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401
        return True
    except ImportError:
        return False


class StreamingSpeaker:
    """Feed LLM text chunks; complete sentences are spoken as they form.

    Usage:
        speaker = StreamingSpeaker()
        for chunk in llm_stream:
            display(chunk)
            speaker.feed(chunk)
        speaker.finish()   # flush remainder, block until audio queue drains

    Call cancel() from any thread to stop playback immediately (kills the
    current audio subprocess and drains the sentence queue).
    """

    def __init__(self, voice: str | None = None):
        self._use_edge = _edge_tts_available()
        self._voice = voice or ("en-GB-RyanNeural" if self._use_edge else "Daniel")
        self._buffer = ""
        self._q: queue.Queue[str | None] = queue.Queue()
        self._cancelled = threading.Event()
        self._proc: "subprocess.Popen | None" = None  # current audio subprocess
        self._proc_lock = threading.Lock()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------

    def feed(self, chunk: str) -> None:
        """Add a text chunk; speak any newly completed sentences."""
        if self._cancelled.is_set():
            return
        self._buffer += chunk
        sentences, self._buffer = _split_sentences(self._buffer)
        for s in sentences:
            if s.strip():
                self._q.put(s.strip())

    def finish(self) -> None:
        """Flush remaining buffer and block until all audio has played."""
        if not self._cancelled.is_set() and self._buffer.strip():
            self._q.put(self._buffer.strip())
        self._buffer = ""
        if not self._cancelled.is_set():
            self._q.put(None)   # sentinel
        self._thread.join()

    def cancel(self) -> None:
        """Stop playback immediately — safe to call from any thread."""
        self._cancelled.set()
        # Kill current audio subprocess
        with self._proc_lock:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        # Drain pending sentences so the worker can exit
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
        self._q.put(None)   # wake the worker so it sees the sentinel

    # ------------------------------------------------------------------

    def _worker(self) -> None:
        while True:
            text = self._q.get()
            if text is None or self._cancelled.is_set():
                break
            try:
                if self._use_edge:
                    _speak_edge(text, self._voice, self)
                else:
                    _speak_macos(text, self._voice, self)
            except Exception:
                # edge-tts failure (e.g. offline) → fall back to say
                try:
                    _speak_macos(text, "Daniel", self)
                except Exception:
                    pass


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _split_sentences(text: str) -> tuple[list[str], str]:
    """Return (complete_sentences, remainder)."""
    parts = _SENTENCE_RE.split(text)
    if len(parts) <= 1:
        return [], text
    return parts[:-1], parts[-1]


def _speak_edge(text: str, voice: str, speaker: "StreamingSpeaker | None" = None) -> None:
    """Speak via edge-tts neural voice, play with afplay (macOS)."""
    import asyncio
    import os
    import tempfile
    import edge_tts

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            path = f.name
        try:
            await communicate.save(path)
            proc = subprocess.Popen(["afplay", path],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if speaker is not None:
                with speaker._proc_lock:
                    speaker._proc = proc
            proc.wait()
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    asyncio.run(_run())


def _speak_macos(text: str, voice: str, speaker: "StreamingSpeaker | None" = None) -> None:
    """Speak via macOS say command."""
    proc = subprocess.Popen(["say", "-v", voice, text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if speaker is not None:
        with speaker._proc_lock:
            speaker._proc = proc
    proc.wait()
