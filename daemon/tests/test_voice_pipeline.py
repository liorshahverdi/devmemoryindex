"""Unit tests for daemon.voice_pipeline — Phase 8.3 / 8.2.

Tests the ACTIVE→PASSIVE state transitions using mocked helpers so no
microphone, Whisper, or LLM backend is required.
"""

from __future__ import annotations

import queue
import time
from unittest.mock import MagicMock, patch

import pytest

# The pipeline module imports daemon.wake_word at module level; we need to
# make sure detection_queue is patchable before importing the module under test.
import daemon.wake_word as _wake_word_module
from daemon.voice_pipeline import (
    STOP_PHRASES,
    VoicePipeline,
    _answer,
    _transcribe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pipeline() -> VoicePipeline:
    return VoicePipeline()


def _fake_audio():
    """Return a tiny non-silent numpy float32 array (avoids sounddevice)."""
    import numpy as np
    return (np.ones(16_000, dtype="float32") * 0.1)


# ---------------------------------------------------------------------------
# _enter_active: timeout when audio is always silent (None)
# ---------------------------------------------------------------------------

class TestActiveToPassiveOnTimeout:
    """VAD returns None every call → loop should exit after deadline."""

    def test_state_returns_to_passive(self):
        pipeline = _make_pipeline()
        # Patch ACTIVE_TIMEOUT to 0 so the deadline is already expired
        with patch("daemon.voice_pipeline.ACTIVE_TIMEOUT", 0.0):
            with patch("daemon.voice_pipeline._record_with_vad", return_value=None):
                pipeline._enter_active()

        assert pipeline._state == VoicePipeline.STATE_PASSIVE

    def test_history_not_populated_on_silence(self):
        pipeline = _make_pipeline()
        with patch("daemon.voice_pipeline.ACTIVE_TIMEOUT", 0.0):
            with patch("daemon.voice_pipeline._record_with_vad", return_value=None):
                pipeline._enter_active()

        assert pipeline._history == []


# ---------------------------------------------------------------------------
# _enter_active: stop phrase → immediate PASSIVE
# ---------------------------------------------------------------------------

class TestActiveToPassiveOnStopPhrase:
    """Each stop phrase should end the session immediately."""

    @pytest.mark.parametrize("phrase", sorted(STOP_PHRASES))
    def test_stop_phrase_exits_active(self, phrase):
        pipeline = _make_pipeline()

        # Audio returns something; transcription returns the stop phrase once,
        # then silence to prevent looping.
        call_count = {"n": 0}

        def fake_record(duration=8):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _fake_audio()
            return None  # silence on subsequent calls

        mock_speaker = MagicMock()
        mock_speaker_cls = MagicMock(return_value=mock_speaker)

        with patch("daemon.voice_pipeline._check_speaker", return_value=True):
            with patch("daemon.voice_pipeline._record_with_vad", side_effect=fake_record):
                with patch("daemon.voice_pipeline._transcribe", return_value=phrase):
                    with patch("daemon.voice_pipeline._speak") as mock_speak:
                        with patch(
                            "cli.commands._speak.StreamingSpeaker",
                            mock_speaker_cls,
                        ):
                            pipeline._enter_active()

        assert pipeline._state == VoicePipeline.STATE_PASSIVE
        # "Got it." should have been spoken
        mock_speak.assert_called_once()
        spoken_text = mock_speak.call_args[0][1]
        assert spoken_text == "Got it."


# ---------------------------------------------------------------------------
# _enter_active: normal query → answer spoken → timer resets → passive on next silence
# ---------------------------------------------------------------------------

class TestNormalQueryFlow:
    def test_answer_spoken_and_history_recorded(self):
        pipeline = _make_pipeline()
        call_count = {"n": 0}

        def fake_record(duration=8):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _fake_audio()
            return None  # silence ends the session

        with patch("daemon.voice_pipeline._check_speaker", return_value=True):
            with patch("daemon.voice_pipeline._record_with_vad", side_effect=fake_record):
                with patch("daemon.voice_pipeline._transcribe", return_value="What is LanceDB?"):
                    with patch(
                        "daemon.voice_pipeline._answer",
                        return_value="LanceDB is a vector database.",
                    ):
                        with patch("daemon.voice_pipeline._speak") as mock_speak:
                            pipeline._enter_active()

        assert pipeline._state == VoicePipeline.STATE_PASSIVE
        # History should contain one exchange
        assert len(pipeline._history) == 1
        assert pipeline._history[0] == (
            "What is LanceDB?",
            "LanceDB is a vector database.",
        )
        # Answer was spoken
        mock_speak.assert_called_once()
        spoken_text = mock_speak.call_args[0][1]
        assert spoken_text == "LanceDB is a vector database."

    def test_history_capped_at_max_history(self):
        from daemon.voice_pipeline import MAX_HISTORY
        pipeline = _make_pipeline()

        turns = MAX_HISTORY + 2
        call_count = {"n": 0}

        def fake_record(duration=8):
            call_count["n"] += 1
            if call_count["n"] <= turns:
                return _fake_audio()
            return None

        def fake_transcribe(audio):
            return f"question {call_count['n']}"

        with patch("daemon.voice_pipeline._check_speaker", return_value=True):
            with patch("daemon.voice_pipeline._record_with_vad", side_effect=fake_record):
                with patch("daemon.voice_pipeline._transcribe", side_effect=fake_transcribe):
                    with patch("daemon.voice_pipeline._answer", return_value="answer"):
                        with patch("daemon.voice_pipeline._speak"):
                            pipeline._enter_active()

        assert len(pipeline._history) <= MAX_HISTORY


# ---------------------------------------------------------------------------
# VoicePipeline.run: consumes detection_queue events
# ---------------------------------------------------------------------------

class TestPipelineRun:
    """run() should call _enter_active each time an event arrives."""

    def test_run_calls_enter_active_on_detection(self):
        pipeline = _make_pipeline()
        called = []

        def fake_enter_active():
            called.append(True)
            # Stop the loop after first call by raising to break out
            raise KeyboardInterrupt

        # Seed one detection event
        _wake_word_module.detection_queue.put_nowait({"score": 0.9, "time": time.monotonic()})

        pipeline._enter_active = fake_enter_active

        with pytest.raises(KeyboardInterrupt):
            pipeline.run()

        assert called == [True]


# ---------------------------------------------------------------------------
# Phase 8.2 — Speaker gate
# ---------------------------------------------------------------------------

class TestSpeakerGate:
    """_check_speaker() integration into the active loop."""

    def test_unrecognised_speaker_triggers_passive(self):
        """When _check_speaker returns False, pipeline speaks 'Do I know you?' and exits."""
        pipeline = _make_pipeline()
        call_count = {"n": 0}

        def fake_record(duration=8):
            call_count["n"] += 1
            return _fake_audio()

        with patch("daemon.voice_pipeline.SPEAKER_GATE_ENABLED", True):
            with patch("daemon.voice_pipeline._record_with_vad", side_effect=fake_record):
                with patch("daemon.voice_pipeline._check_speaker", return_value=False):
                    with patch("daemon.voice_pipeline._speak") as mock_speak:
                        pipeline._enter_active()

        assert pipeline._state == VoicePipeline.STATE_PASSIVE
        # "Do I know you?" must be spoken
        mock_speak.assert_called_once()
        spoken_text = mock_speak.call_args[0][1]
        assert "know you" in spoken_text.lower()

    def test_unrecognised_speaker_history_not_recorded(self):
        pipeline = _make_pipeline()

        with patch("daemon.voice_pipeline.SPEAKER_GATE_ENABLED", True):
            with patch("daemon.voice_pipeline._record_with_vad", return_value=_fake_audio()):
                with patch("daemon.voice_pipeline._check_speaker", return_value=False):
                    with patch("daemon.voice_pipeline._speak"):
                        pipeline._enter_active()

        assert pipeline._history == []

    def test_recognised_speaker_proceeds_to_query(self):
        """When _check_speaker returns True, transcription and answer are called."""
        pipeline = _make_pipeline()
        call_count = {"n": 0}

        def fake_record(duration=8):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _fake_audio()
            return None  # silence → exit after first exchange

        with patch("daemon.voice_pipeline.SPEAKER_GATE_ENABLED", True):
            with patch("daemon.voice_pipeline._record_with_vad", side_effect=fake_record):
                with patch("daemon.voice_pipeline._check_speaker", return_value=True):
                    with patch("daemon.voice_pipeline._transcribe", return_value="What is LanceDB?"):
                        with patch("daemon.voice_pipeline._answer", return_value="It is a vector DB."):
                            with patch("daemon.voice_pipeline._speak") as mock_speak:
                                pipeline._enter_active()

        assert pipeline._state == VoicePipeline.STATE_PASSIVE
        assert len(pipeline._history) == 1
        # Answer was spoken (not "Do I know you?")
        spoken_text = mock_speak.call_args[0][1]
        assert "know you" not in spoken_text.lower()

    def test_gate_disabled_skips_check(self):
        """When SPEAKER_GATE_ENABLED is False, _check_speaker is never called."""
        pipeline = _make_pipeline()
        call_count = {"n": 0}

        def fake_record(duration=8):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _fake_audio()
            return None

        with patch("daemon.voice_pipeline.SPEAKER_GATE_ENABLED", False):
            with patch("daemon.voice_pipeline._record_with_vad", side_effect=fake_record):
                with patch("daemon.voice_pipeline._check_speaker") as mock_gate:
                    with patch("daemon.voice_pipeline._transcribe", return_value="hello"):
                        with patch("daemon.voice_pipeline._answer", return_value="hi"):
                            with patch("daemon.voice_pipeline._speak"):
                                pipeline._enter_active()

        mock_gate.assert_not_called()

    def test_check_speaker_fail_open_on_verify_exception(self):
        """_check_speaker returns True when _verify_speaker raises (fail-open)."""
        import numpy as np
        from daemon.voice_pipeline import _check_speaker

        with patch(
            "cli.commands._voice._verify_speaker",
            side_effect=RuntimeError("pyannote broken"),
        ):
            result = _check_speaker(np.ones(1000, dtype="float32"))

        assert result is True
