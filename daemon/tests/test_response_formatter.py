"""Unit tests for daemon.response_formatter — Phase 8.4."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from daemon.response_formatter import _humanize_date, _truncate_sentences, format_for_voice


# ---------------------------------------------------------------------------
# format_for_voice — no-results detection
# ---------------------------------------------------------------------------

class TestNoResults:
    def test_empty_string(self):
        assert format_for_voice("") == "Nothing on that."

    def test_whitespace_only(self):
        assert format_for_voice("   ") == "Nothing on that."

    def test_none_like_empty(self):
        # Should not raise even if caller passes None-coerced value
        assert format_for_voice("") == "Nothing on that."

    def test_no_relevant_memories_phrase(self):
        assert format_for_voice("I'm sorry, there are no relevant memories about that topic.") == "Nothing on that."

    def test_no_information_phrase(self):
        assert format_for_voice("I do not have information about this in my memory.") == "Nothing on that."

    def test_long_answer_with_no_info_phrase_is_kept(self):
        # A long answer that mentions "no information" in passing should not be suppressed.
        long = (
            "Based on the memories provided, there is no information about X directly, "
            "but here is what I found about related topics. "
            "The context engine uses hybrid search combining semantic and keyword signals. "
            "The ranking formula weights importance, recency, and semantic distance."
        )
        result = format_for_voice(long)
        assert result != "Nothing on that."


class TestErrorMessages:
    def test_internal_error_passthrough(self):
        assert format_for_voice("Sorry, I couldn't retrieve an answer right now.") == "Can't reach the store right now."

    def test_cant_reach_passthrough(self):
        assert format_for_voice("Can't reach the store right now.") == "Can't reach the store right now."


# ---------------------------------------------------------------------------
# format_for_voice — code stripping
# ---------------------------------------------------------------------------

class TestCodeStripping:
    def test_fenced_code_block_removed(self):
        text = "Here is the answer.\n```python\nprint('hello')\n```\nThat is all."
        result = format_for_voice(text)
        assert "```" not in result
        assert "print" not in result

    def test_inline_backticks_stripped(self):
        result = format_for_voice("Use `store.add_batch()` for bulk inserts.")
        assert "`" not in result
        assert "store.add_batch()" in result

    def test_multiple_inline_backticks(self):
        result = format_for_voice("Call `foo()` then `bar()`.")
        assert "foo()" in result
        assert "bar()" in result
        assert "`" not in result


# ---------------------------------------------------------------------------
# format_for_voice — file path cleanup
# ---------------------------------------------------------------------------

class TestFilePaths:
    def test_nested_path_replaced_with_basename(self):
        result = format_for_voice("See core/memory_store.py for details.")
        assert "memory_store.py" in result
        assert "core/" not in result

    def test_path_with_line_number_cleaned(self):
        result = format_for_voice("The function is at core/ranking.py:42.")
        assert "ranking.py" in result
        assert ":42" not in result

    def test_short_relative_path(self):
        result = format_for_voice("Edit daemon/scheduler.py to enable it.")
        assert "scheduler.py" in result
        assert "daemon/" not in result


# ---------------------------------------------------------------------------
# format_for_voice — sentence truncation
# ---------------------------------------------------------------------------

class TestTruncation:
    def test_short_answer_not_truncated(self):
        text = "LanceDB is a vector database. It uses Apache Arrow internally."
        result = format_for_voice(text)
        assert "LanceDB" in result
        assert "Apache Arrow" in result

    def test_long_answer_truncated_to_three_sentences(self):
        sentences = [f"Sentence {i}." for i in range(1, 8)]
        text = " ".join(sentences)
        result = format_for_voice(text)
        # Should contain sentences 1-3 but not 4+
        assert "Sentence 1" in result
        assert "Sentence 2" in result
        assert "Sentence 3" in result
        assert "Sentence 4" not in result

    def test_exactly_three_sentences_unchanged(self):
        text = "First sentence. Second sentence. Third sentence."
        result = format_for_voice(text)
        assert "First" in result
        assert "Third" in result


# ---------------------------------------------------------------------------
# _humanize_date helper
# ---------------------------------------------------------------------------

class TestHumanizeDate:
    """Test the date humanizer in isolation using a mock match object."""

    class _MockMatch:
        def __init__(self, date_str: str):
            self._date_str = date_str

        def group(self, n: int):
            return self._date_str

    def _call(self, date_str: str) -> str:
        return _humanize_date(self._MockMatch(date_str))

    def test_today(self):
        assert self._call(date.today().strftime("%Y-%m-%d")) == "today"

    def test_yesterday(self):
        d = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert self._call(d) == "yesterday"

    def test_days_ago(self):
        d = (date.today() - timedelta(days=4)).strftime("%Y-%m-%d")
        assert self._call(d) == "4 days ago"

    def test_last_week(self):
        d = (date.today() - timedelta(days=9)).strftime("%Y-%m-%d")
        assert self._call(d) == "last week"

    def test_about_a_month(self):
        d = (date.today() - timedelta(days=28)).strftime("%Y-%m-%d")
        assert "month" in self._call(d)

    def test_months_ago(self):
        d = (date.today() - timedelta(days=90)).strftime("%Y-%m-%d")
        assert "month" in self._call(d)

    def test_future_date_unchanged(self):
        d = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        assert self._call(d) == d  # returned as-is

    def test_invalid_date_unchanged(self):
        result = _humanize_date(self._MockMatch("not-a-date"))
        assert result == "not-a-date"


# ---------------------------------------------------------------------------
# _truncate_sentences helper
# ---------------------------------------------------------------------------

class TestTruncateSentences:
    def test_fewer_than_max_unchanged(self):
        text = "One. Two."
        assert _truncate_sentences(text, 3) == "One. Two."

    def test_exactly_max_unchanged(self):
        text = "One. Two. Three."
        assert _truncate_sentences(text, 3) == "One. Two. Three."

    def test_more_than_max_truncated(self):
        text = "One. Two. Three. Four. Five."
        result = _truncate_sentences(text, 3)
        assert "One" in result
        assert "Three" in result
        assert "Four" not in result

    def test_no_sentence_boundary(self):
        text = "no boundary here"
        assert _truncate_sentences(text, 3) == "no boundary here"


# ---------------------------------------------------------------------------
# Integration: ISO date in a full answer
# ---------------------------------------------------------------------------

class TestDateInAnswer:
    def test_iso_date_replaced_in_answer(self):
        # Use a fixed past date
        past = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
        answer = f"This commit was merged on {past} and fixed the ranking bug."
        result = format_for_voice(answer)
        assert past not in result
        assert "days ago" in result or "yesterday" in result or "today" in result

    def test_iso_datetime_replaced(self):
        past = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        answer = f"The memory was created at {past}T14:32:00Z."
        result = format_for_voice(answer)
        assert past not in result
        assert "yesterday" in result
