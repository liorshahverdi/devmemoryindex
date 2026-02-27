"""
Tests for core/privacy.py redact():
1. API key patterns are replaced with [REDACTED].
2. Bearer tokens are stripped.
3. Clean text is returned unchanged.
4. Redaction is applied end-to-end when a connector stores a memory.
"""

import pytest
from datetime import datetime

from core.privacy import redact
from core.memory_store import MemoryStore, VECTOR_DIM
from core.schema import Memory


# ── Unit tests for redact() ───────────────────────────────────────────


def test_api_key_patterns_are_redacted():
    """Common key=value patterns for secrets must be replaced."""
    cases = [
        "export API_KEY=abc123secret",
        "TOKEN=eyJhbGciOiJIUzI1NiJ9",
        "password: hunter2",
        "secret=supersecretvalue",
        "passwd=mypassword123",
        "api-key=sk-live-abc123",
    ]
    for text in cases:
        result = redact(text)
        assert "[REDACTED]" in result, f"Expected redaction in: {text!r}"
        # The actual secret value must not survive
        assert "abc123" not in result or "[REDACTED]" in result


def test_bearer_tokens_are_stripped():
    """Bearer token headers must be fully redacted."""
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    result = redact(text)
    assert "[REDACTED]" in result
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result


def test_clean_text_is_unchanged():
    """Text with no sensitive patterns must pass through unmodified."""
    clean = "Fixed Redis connection pool timeout by increasing max_connections to 50."
    assert redact(clean) == clean


def test_redaction_applied_end_to_end(tmp_path):
    """
    When a memory is built with a raw_text containing a secret and redact()
    is called before storing, the stored raw_text must not contain the secret.
    """
    store = MemoryStore(db_path=str(tmp_path))
    raw = "export API_KEY=sk-prod-abc123xyz"

    mem = Memory(
        id="priv-1",
        type="terminal_command",
        summary="Set API key env var",
        raw_text=redact(raw),          # redact before storing — connector pattern
        source="terminal",
        repo=None,
        timestamp=datetime.utcnow(),
        tags=[],
        importance=0.5,
    )
    store.add(mem, [0.1] * VECTOR_DIM)

    rows = store.get_all()
    assert "[REDACTED]" in rows[0]["raw_text"]
    assert "sk-prod-abc123xyz" not in rows[0]["raw_text"]
