"""
Meeting Connector — indexes meetings from audio files or text transcripts.

Scans configured directories for:
  - Audio files: transcribed locally using Whisper; speaker diarization (pyannote.audio)
    is used when available to prefix each segment with a speaker label.
  - Text files (.txt): parsed directly for named-speaker transcript formats produced by
    Zoom, Teams, Google Meet, etc.  Lines matching "Name: text" or "Name [HH:MM]: text"
    are recognised and all speaker names are stored as "speaker:<name>" tags.

Memory fields:
  type        "meeting_transcript"
  summary     first 200 chars of transcript
  raw_text    full transcript (possibly with "Name: ..." prefixes)
  source      file path
  repo        None
  timestamp   file mtime
  importance  0.75
  tags        ["meeting", "transcript", "speaker:<name>", ...]

Requires: openai-whisper  (uv pip install "devmemoryindex[voice]")  — audio only
Optional: pyannote.audio  (uv pip install "devmemoryindex[voice]")  — audio diarization

Configuration:
  devmemory config add-meetings ~/Recordings
  devmemory config remove-meetings ~/Recordings
"""

import hashlib
import re
from datetime import datetime
from pathlib import Path

import core.config as cfg
from connectors.base import Connector
from core.embeddings import embed
from core.schema import Memory

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".flac", ".webm", ".aac"}
TEXT_EXTENSIONS = {".txt"}
MAX_FILE_MB = 500  # skip files larger than 500 MB

# Matches "Name: text" or "Name [HH:MM]: text" or "Name [HH:MM:SS]: text"
# Name must start with a letter, max 40 chars, no colon in the name portion.
_SPEAKER_LINE_RE = re.compile(
    r"^(?P<name>[A-Za-z][A-Za-z0-9 \-\'\.]{0,39}?)"
    r"(?:\s+\[[\d:]+\])?"
    r":\s+(?P<text>.+)$"
)


class MeetingConnector(Connector):
    name = "meeting"

    def __init__(self, dirs: list[str] | None = None):
        super().__init__()
        self.dirs = dirs or cfg.get_meeting_dirs()

    def collect(self) -> int:
        if not self.dirs:
            return 0

        count = 0
        for d in self.dirs:
            root = Path(d).expanduser().resolve()
            if not root.is_dir():
                continue
            for f in sorted(root.rglob("*")):
                suffix = f.suffix.lower()
                if suffix in TEXT_EXTENSIONS:
                    if f.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                        continue
                    try:
                        count += self._index_text_file(f)
                    except Exception as e:
                        import warnings
                        warnings.warn(f"Failed to index {f.name}: {e}")
                elif suffix in AUDIO_EXTENSIONS:
                    if f.stat().st_size > MAX_FILE_MB * 1024 * 1024:
                        continue
                    try:
                        count += self._index_audio_file(f)
                    except Exception as e:
                        import warnings
                        warnings.warn(f"Failed to index {f.name}: {e}")
        return count

    def _index_text_file(self, path: Path) -> int:
        """Index a pre-transcribed text file (Zoom/Teams/Google Meet export)."""
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        mem_id = hashlib.sha256(
            f"{path}|{path.stat().st_mtime}".encode()
        ).hexdigest()

        if self.store.exists(mem_id):
            return 0

        try:
            raw = path.read_text(errors="replace").strip()
        except Exception:
            return 0

        if len(raw) < 50:
            return 0

        transcript, speaker_tags = _parse_text_transcript(raw)
        raw_text = self._redact(transcript[:5000])
        summary = transcript[:200].replace("\n", " ")

        memory = Memory(
            id=mem_id,
            type="meeting_transcript",
            summary=summary,
            raw_text=raw_text,
            source=str(path),
            repo=None,
            timestamp=mtime,
            tags=["meeting", "transcript"] + speaker_tags,
            importance=0.75,
        )
        self.store.add(memory, embed(summary[:512]))
        return 1

    def _index_audio_file(self, path: Path) -> int:
        """Transcribe an audio file with Whisper and index the result."""
        try:
            import whisper  # noqa: F401
        except ImportError:
            return 0  # silently skip if Whisper not installed

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


def _parse_text_transcript(raw: str) -> tuple[str, list[str]]:
    """Parse a pre-transcribed text file and extract speaker tags.

    Detects lines in the formats produced by Zoom/Teams/Google Meet:
      "Name: text"
      "Name [HH:MM]: text"
      "Name [HH:MM:SS]: text"

    Returns:
        (transcript, speaker_tags) where speaker_tags is a list of
        "speaker:<name_lowercase>" strings plus "speaker:self" when the
        user's configured name or aliases appear.

    Falls back to (raw, []) when no speaker lines are detected.
    """
    user_name = cfg.get_user_name()
    user_aliases = cfg.get_user_aliases()

    # Build a lowercase set of names/aliases that identify the user.
    self_names: set[str] = set()
    if user_name:
        self_names.add(user_name.lower())
    for alias in user_aliases:
        self_names.add(alias.lower())

    lines = raw.splitlines()
    detected_speakers: set[str] = set()
    speaker_lines_found = 0

    for line in lines:
        m = _SPEAKER_LINE_RE.match(line.strip())
        if m:
            speaker_lines_found += 1
            detected_speakers.add(m.group("name").strip())

    # Only apply speaker tagging if >30% of non-empty lines look like speaker lines
    # (prevents over-eager matching on plain text files).
    non_empty = sum(1 for l in lines if l.strip())
    if non_empty == 0 or speaker_lines_found / non_empty < 0.3:
        return raw, []

    speaker_tags: list[str] = []
    has_self = False
    for name in detected_speakers:
        name_lower = name.lower()
        speaker_tags.append(f"speaker:{name_lower}")
        if name_lower in self_names:
            has_self = True
    if has_self:
        speaker_tags.append("speaker:self")

    return raw, speaker_tags


def _ffmpeg_install_hint() -> str:
    """Return a platform-appropriate ffmpeg install hint."""
    import platform

    system = platform.system().lower()
    if system == "darwin":
        return "Install it with: brew install ffmpeg"
    if system == "linux":
        return "Install it with your package manager, e.g. sudo apt install ffmpeg or brew install ffmpeg."
    if system == "windows":
        return "Install ffmpeg and ensure ffmpeg.exe is on PATH."
    return "Install ffmpeg and ensure it is on PATH."


def _transcribe(path: Path) -> str:
    """
    Transcribe an audio file using Whisper.

    Attempts speaker diarization with pyannote.audio if available.
    Falls back to plain Whisper transcript if pyannote is not installed
    or if diarization fails.
    """
    import shutil
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not found. Whisper requires ffmpeg to decode audio files.\n"
            f"{_ffmpeg_install_hint()}"
        )

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
