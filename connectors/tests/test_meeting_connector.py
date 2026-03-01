"""
Tests for MeetingConnector:
1. Returns 0 gracefully when whisper is not installed.
2. Returns 0 when no meeting dirs configured.
3. Skips audio files larger than MAX_FILE_MB.
4. Skips files with unsupported extensions.
5. Short transcripts (< 50 chars) are skipped.
6. Valid transcripts are stored as meeting_transcript memories.
7. Deduplication — same file with same mtime returns 0 on second call.
8. _diarize raises ImportError when pyannote not installed.
"""

import hashlib
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from connectors.meeting_connector import (
    MeetingConnector, MAX_FILE_MB, AUDIO_EXTENSIONS,
    TEXT_EXTENSIONS, _parse_text_transcript,
)
from core.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


def _connector(store, dirs=None):
    """Create a connector with an explicit dirs list, bypassing system config."""
    c = MeetingConnector.__new__(MeetingConnector)
    # Call grandparent __init__ to set up self.store, then override
    from connectors.base import Connector
    Connector.__init__(c)
    c.store = store
    c.dirs = dirs if dirs is not None else []
    return c


def _write_audio(path: Path, size_bytes: int = 1024) -> Path:
    path.write_bytes(b"\x00" * size_bytes)
    return path


# ── No whisper installed ──────────────────────────────────────────────────────

def test_returns_zero_without_whisper(store, tmp_path):
    d = tmp_path / "recordings"
    d.mkdir()
    _write_audio(d / "meeting.wav")
    c = _connector(store, dirs=[str(d)])
    with patch.dict("sys.modules", {"whisper": None}):
        # ImportError path: collect() silently returns 0
        assert c.collect() == 0


# ── No dirs configured ────────────────────────────────────────────────────────

def test_no_dirs_returns_zero(store):
    c = _connector(store, dirs=[])
    assert c.collect() == 0


# ── File size limit ───────────────────────────────────────────────────────────

def test_large_file_skipped(store, tmp_path):
    d = tmp_path / "recordings"
    d.mkdir()
    big = d / "huge.wav"
    # Write more than MAX_FILE_MB
    big.write_bytes(b"\x00" * (MAX_FILE_MB * 1024 * 1024 + 1))
    c = _connector(store, dirs=[str(d)])

    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value.transcribe.return_value = {
        "text": "A" * 100, "segments": []
    }
    with patch.dict("sys.modules", {"whisper": mock_whisper}):
        assert c.collect() == 0


# ── Unsupported extension ─────────────────────────────────────────────────────

def test_unsupported_extension_skipped(store, tmp_path):
    d = tmp_path / "recordings"
    d.mkdir()
    _write_audio(d / "recording.pdf")  # .pdf is not a handled extension
    c = _connector(store, dirs=[str(d)])

    mock_whisper = MagicMock()
    with patch.dict("sys.modules", {"whisper": mock_whisper}):
        assert c.collect() == 0


# ── Short transcript skipped ─────────────────────────────────────────────────

def test_short_transcript_skipped(store, tmp_path):
    d = tmp_path / "recordings"
    d.mkdir()
    wav = _write_audio(d / "short.wav")
    c = _connector(store, dirs=[str(d)])

    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": "hi", "segments": []}
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model

    with patch.dict("sys.modules", {"whisper": mock_whisper}):
        with patch("connectors.meeting_connector._transcribe", return_value="hi"):
            assert c.collect() == 0


# ── Valid transcript indexed ──────────────────────────────────────────────────

def test_valid_transcript_stored(store, tmp_path):
    d = tmp_path / "recordings"
    d.mkdir()
    wav = _write_audio(d / "standup.mp3")
    c = _connector(store, dirs=[str(d)])

    long_transcript = "Speaker discussed the sprint goals and blockers. " * 5

    mock_whisper = MagicMock()
    with patch.dict("sys.modules", {"whisper": mock_whisper}):
        with patch("connectors.meeting_connector._transcribe", return_value=long_transcript):
            count = c.collect()

    assert count == 1
    memories = store.get_all()
    assert any(m["type"] == "meeting_transcript" for m in memories)
    assert any("meeting" in m["tags"] for m in memories)


# ── Deduplication ─────────────────────────────────────────────────────────────

def test_deduplication(store, tmp_path):
    d = tmp_path / "recordings"
    d.mkdir()
    wav = _write_audio(d / "daily.wav")
    c = _connector(store, dirs=[str(d)])

    long_transcript = "Team reviewed progress on all active tickets. " * 5

    mock_whisper = MagicMock()
    with patch.dict("sys.modules", {"whisper": mock_whisper}):
        with patch("connectors.meeting_connector._transcribe", return_value=long_transcript):
            first = c.collect()
            second = c.collect()

    assert first == 1
    assert second == 0  # mtime unchanged → same ID → already exists


# ── Audio extension coverage ──────────────────────────────────────────────────

def test_audio_extensions_include_common():
    assert ".mp3" in AUDIO_EXTENSIONS
    assert ".wav" in AUDIO_EXTENSIONS
    assert ".m4a" in AUDIO_EXTENSIONS
    assert ".mp4" in AUDIO_EXTENSIONS
    assert ".webm" in AUDIO_EXTENSIONS


def test_text_extension_is_supported():
    assert ".txt" in TEXT_EXTENSIONS


# ── Text transcript parsing (_parse_text_transcript) ─────────────────────────

def test_parse_speaker_lines_simple():
    raw = "\n".join([
        "Alice: Let's discuss the sprint goals.",
        "Bob: Agreed, we should also review blockers.",
        "Alice: The main blocker is the auth service.",
    ])
    transcript, tags = _parse_text_transcript(raw)
    assert transcript == raw
    assert "speaker:alice" in tags
    assert "speaker:bob" in tags


def test_parse_speaker_lines_with_timestamp():
    raw = "\n".join([
        "Alice [00:00]: Welcome everyone.",
        "Bob [00:15]: Thanks for having me.",
        "Carol [01:30]: Let me share my screen.",
        "Alice [02:00]: Sure, go ahead.",
    ])
    _, tags = _parse_text_transcript(raw)
    assert "speaker:alice" in tags
    assert "speaker:bob" in tags
    assert "speaker:carol" in tags


def test_parse_self_speaker_detection():
    raw = "\n".join([
        "Lasha: We decided to use JWT for auth.",
        "Alice: Makes sense, agreed.",
        "Lasha: We'll revisit in the next sprint.",
    ])
    with patch("core.config.get_user_name", return_value="Lasha"), \
         patch("core.config.get_user_aliases", return_value=[]):
        _, tags = _parse_text_transcript(raw)
    assert "speaker:lasha" in tags
    assert "speaker:self" in tags
    assert "speaker:alice" in tags


def test_parse_no_speaker_format_returns_empty_tags():
    raw = "This is just a plain text document with no speaker labels at all."
    _, tags = _parse_text_transcript(raw)
    assert tags == []


def test_parse_mixed_lines_below_threshold():
    # Only 1 of 5 lines looks like a speaker line → below 30% threshold
    raw = "\n".join([
        "Meeting notes from 2025-01-01",
        "Topics covered:",
        "Alice: One speaker line among many non-speaker lines.",
        "  - Authentication design",
        "  - Sprint planning",
    ])
    _, tags = _parse_text_transcript(raw)
    assert tags == []


# ── Text file indexing via collect() ─────────────────────────────────────────

_FAKE_VECTOR = [0.0] * 384


def test_text_transcript_indexed(store, tmp_path):
    d = tmp_path / "transcripts"
    d.mkdir()
    transcript_content = "\n".join([
        "Alice: We agreed to use LanceDB for the memory store.",
        "Bob: The embedding model is BAAI/bge-small-en.",
        "Alice: Good, let's proceed with that approach.",
        "Bob: I'll update the schema and run migration.",
    ])
    (d / "standup.txt").write_text(transcript_content)
    c = _connector(store, dirs=[str(d)])

    with patch("core.config.get_user_name", return_value=None), \
         patch("core.config.get_user_aliases", return_value=[]), \
         patch("connectors.meeting_connector.embed", return_value=_FAKE_VECTOR):
        count = c.collect()

    assert count == 1
    memories = store.get_all()
    assert any(m["type"] == "meeting_transcript" for m in memories)
    mem = next(m for m in memories if m["type"] == "meeting_transcript")
    assert "speaker:alice" in mem["tags"]
    assert "speaker:bob" in mem["tags"]


def test_text_transcript_short_skipped(store, tmp_path):
    d = tmp_path / "transcripts"
    d.mkdir()
    (d / "empty.txt").write_text("too short")
    c = _connector(store, dirs=[str(d)])
    assert c.collect() == 0


def test_text_transcript_deduplication(store, tmp_path):
    d = tmp_path / "transcripts"
    d.mkdir()
    text = "\n".join([
        "Alice: We're testing deduplication logic here.",
        "Bob: It should index once and skip on second run.",
        "Alice: Exactly right, let's verify.",
    ])
    (d / "meeting.txt").write_text(text)
    c = _connector(store, dirs=[str(d)])

    with patch("core.config.get_user_name", return_value=None), \
         patch("core.config.get_user_aliases", return_value=[]), \
         patch("connectors.meeting_connector.embed", return_value=_FAKE_VECTOR):
        first = c.collect()
        second = c.collect()

    assert first == 1
    assert second == 0
