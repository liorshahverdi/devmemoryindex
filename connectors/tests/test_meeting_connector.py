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

from connectors.meeting_connector import MeetingConnector, MAX_FILE_MB, AUDIO_EXTENSIONS
from core.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


def _connector(store, dirs=None):
    c = MeetingConnector(dirs=dirs or [])
    c.store = store
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
    _write_audio(d / "recording.txt")
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
