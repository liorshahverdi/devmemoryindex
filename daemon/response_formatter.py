"""Voice response formatter — Phase 8.4.

Converts raw LLM answer text into punchy spoken output:
  - Empty / no-results answer    → "Nothing on that."
  - Too long (> 3 sentences)     → truncated to 3 sentences
  - ISO dates in text            → relative ("3 days ago", "last week")
  - File paths                   → basename only ("core/foo.py:42" → "foo.py")
  - Code blocks / inline code    → stripped or de-backticked
  - Error fallback text          → "Can't reach the store right now."

Public API:
    from daemon.response_formatter import format_for_voice
    spoken = format_for_voice(raw_llm_answer)
"""

from __future__ import annotations

import re
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_SENTENCES = 3

# Phrases the LLM uses when it has no relevant memories.
# Keep this list short and precise — false positives silence real answers.
_NO_RESULT_PHRASES = (
    "no relevant memories",
    "no information",
    "don't have information",
    "do not have information",
    "nothing in my memory",
    "no memories found",
    "i'm not sure",
    "i am not sure",
    "cannot find",
    "can't find",
    "not enough information",
    "no context",
)

_ERROR_PHRASES = (
    "sorry, i couldn't retrieve",
    "can't reach the store",
)

# Matches ISO-8601 dates with optional time component.
# Group 1 = the date part (yyyy-mm-dd).
_DATE_RE = re.compile(
    r"\b(\d{4}[-/]\d{2}[-/]\d{2})(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?)?\b"
)

# Matches file paths with common source extensions.
# Captures the full match so we can replace with just the basename.
_PATH_RE = re.compile(
    r"(?:[\w./\-]+/)+([\w\-]+\.(?:py|ts|js|tsx|go|rs|md|toml|yaml|yml|json|txt))(?::\d+)?"
)

# Fenced and inline code blocks.
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_RE = re.compile(r"`([^`]+)`")

# Sentence boundary: punctuation followed by whitespace or end-of-string.
# Excludes common abbreviations by requiring the next char (if any) to be uppercase.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"])")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def format_for_voice(answer: str) -> str:
    """Return a voice-friendly version of a raw LLM answer string."""
    text = (answer or "").strip()

    if not text:
        return "Nothing on that."

    lower = text.lower()

    # Propagate internal error messages as a clean spoken phrase.
    if any(p in lower for p in _ERROR_PHRASES):
        return "Can't reach the store right now."

    # Detect "no results" answers — only short ones are truly empty responses;
    # a long answer that mentions "no information" in passing is still useful.
    if len(text) < 250 and any(p in lower for p in _NO_RESULT_PHRASES):
        return "Nothing on that."

    # Strip fenced code blocks entirely (not speakable).
    text = _CODE_BLOCK_RE.sub("", text)

    # De-backtick inline code — keep the text, drop the backticks.
    text = _INLINE_CODE_RE.sub(r"\1", text)

    # Humanize ISO dates.
    text = _DATE_RE.sub(_humanize_date, text)

    # Replace file paths with just the basename.
    text = _PATH_RE.sub(lambda m: m.group(1), text)

    # Collapse whitespace left by code block removal.
    text = re.sub(r"\n{2,}", " ", text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()

    # Truncate to the first _MAX_SENTENCES sentences.
    text = _truncate_sentences(text, _MAX_SENTENCES)

    return text or "Nothing on that."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _humanize_date(match: re.Match) -> str:
    """Replace an ISO date with a relative human-readable phrase."""
    try:
        date_str = match.group(1).replace("/", "-")
        parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
        today = date.today()
        delta = (today - parsed).days

        if delta < 0:
            # Future date — leave as-is.
            return match.group(0)
        if delta == 0:
            return "today"
        if delta == 1:
            return "yesterday"
        if delta < 7:
            return f"{delta} days ago"
        if delta < 11:
            return "last week"
        if delta < 14:
            return "about a week ago"
        if delta < 21:
            return "two weeks ago"
        if delta < 35:
            return "about a month ago"
        if delta < 60:
            return "last month"
        if delta < 365:
            months = round(delta / 30)
            return f"{months} months ago"
        years = round(delta / 365)
        return f"about a year ago" if years == 1 else f"{years} years ago"
    except Exception:
        return match.group(0)


def _truncate_sentences(text: str, max_sentences: int) -> str:
    """Return at most max_sentences complete sentences from text."""
    parts = _SENT_SPLIT_RE.split(text.strip())
    parts = [p.strip() for p in parts if p.strip()]
    if not parts or len(parts) <= max_sentences:
        return text.strip()
    return " ".join(parts[:max_sentences])
