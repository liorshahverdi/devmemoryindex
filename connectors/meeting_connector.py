"""
Meeting Connector — indexes audio recordings of meetings/calls.

Scans configured directories for audio files, transcribes them locally using
Whisper, and stores the transcript as a searchable memory. Speaker diarization
(pyannote.audio) is used when available to prefix each segment with a speaker
label; falls back to plain transcript if pyannote is not installed.

Memory fields:
  type        "meeting_transcript"
  summary     first 200 chars of transcript
  raw_text    full transcript (possibly with "SPEAKER_N: ..." prefixes)
  source      audio file path
  repo        None
  timestamp   file mtime
  importance  0.75
  tags        ["meeting", "transcript"]

Requires: openai-whisper  (uv pip install "devmemoryindex[voice]")
Optional: pyannote.audio  (uv pip install "devmemoryindex[voice]")

Configuration:
  devmemory config add-meetings ~/Recordings
  devmemory config remove-meetings ~/Recordings
"""

import hashlib
from datetime import datetime
from pathlib import Path

import core.config as cfg
from connectors.base import Connector
from core.schema import Memory

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".flac", ".webm", ".aac"}
MAX_FILE_MB = 500  # skip files larger than 500 MB


class MeetingConnector(Connector):
    name = "meeting"

    def __init__(self, dirs: list[str] | None = None):
        super().__init__()
        self.dirs = dirs or cfg.get_meeting_dirs()

    def collect(self) -> int:
        try:
            import whisper  # noqa: F401
        except ImportError:
            return 0  # silently skip if Whisper not installed

        import shutil
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "ffmpeg not found. Whisper requires ffmpeg to decode audio files.\n"
                "Install it with: brew install ffmpeg"
            )

        if not self.dirs:
            return 0

        count = 0
        for d in self.dirs:
            root = Path(d).expanduser().resolve()
            if not root.is_dir():
                continue
            for audio_file in sorted(root.rglob("*")):
                if audio_file.suffix.lower() not in AUDIO_EXTENSIONS:
                    continue
                if audio_file.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                    continue
                try:
                    count += self._index_file(audio_file)
                except Exception as e:
                    import warnings
                    warnings.warn(f"Failed to index {audio_file.name}: {e}")
        return count

    def _index_file(self, path: Path) -> int:
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        mem_id = hashlib.sha256(
            f"{path}|{path.stat().st_mtime}".encode()
        ).hexdigest()

        if self.store.exists(mem_id):
            return 0

        transcript = _transcribe(path)
        if not transcript or len(transcript.strip()) < 50:
            return 0

        raw_text = self._redact(transcript[:5000])
        summary = transcript[:200].replace("\n", " ")

        from core.embeddings import embed
        memory = Memory(
            id=mem_id,
            type="meeting_transcript",
            summary=summary,
            raw_text=raw_text,
            source=str(path),
            repo=None,
            timestamp=mtime,
            tags=["meeting", "transcript"],
            importance=0.75,
        )
        self.store.add(memory, embed(summary[:512]))
        return 1


# ── Helpers ────────────────────────────────────────────────────────────


def _transcribe(path: Path) -> str:
    """
    Transcribe an audio file using Whisper.

    Attempts speaker diarization with pyannote.audio if available.
    Falls back to plain Whisper transcript if pyannote is not installed
    or if diarization fails.
    """
    import whisper
    model = whisper.load_model("base")
    result = model.transcribe(str(path), fp16=False)

    # Try diarization (optional)
    try:
        return _diarize(path, result)
    except Exception:
        # Fall back to plain transcript segments
        segments = result.get("segments", [])
        if segments:
            return "\n".join(s["text"].strip() for s in segments if s.get("text"))
        return result.get("text", "").strip()


def _diarize(path: Path, whisper_result: dict) -> str:
    """
    Align Whisper segments with pyannote speaker labels.
    Raises ImportError if pyannote not installed — caller falls back to plain.
    """
    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=False,
    )
    diarization = pipeline(str(path))

    # Map each Whisper segment to the speaker active at its midpoint
    lines = []
    for seg in whisper_result.get("segments", []):
        mid = (seg["start"] + seg["end"]) / 2
        speaker = "SPEAKER_?"
        for turn, _, label in diarization.itertracks(yield_label=True):
            if turn.start <= mid <= turn.end:
                speaker = label
                break
        lines.append(f"{speaker}: {seg['text'].strip()}")
    return "\n".join(lines)
