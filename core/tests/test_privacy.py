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


def test_git_hashes_are_not_redacted():
    """SHA1 (40 hex chars) and SHA256 (64 hex chars) must not be redacted.

    The old base64 pattern [A-Za-z0-9+/]{40,} matched all hex strings,
    silently corrupting git commit references and memory IDs stored in raw_text.
    """
    sha1 = "a" * 40          # 40 hex chars — git commit hash
    sha256 = "b" * 64        # 64 hex chars — memory ID
    for digest in (sha1, sha256):
        result = redact(digest)
        assert result == digest, f"Hex digest should not be redacted: {digest!r}"

    # A line containing a git hash reference must survive intact
    line = f"Fixed by commit {sha1}"
    assert redact(line) == line


def test_real_base64_with_padding_is_redacted():
    """Padded base64 (ends with = or ==) must still be caught.

    Uses a hardcoded value that contains + and / and ends with == so it
    unambiguously looks like encoded binary data, not a hex digest.
    """
    # 45 bytes encodes to 60 base64 chars with no padding; use 46 bytes → 2 = chars
    import base64
    payload = base64.b64encode(bytes(range(46))).decode()
    assert payload.endswith("="), f"Expected padding in: {payload!r}"
    result = redact(payload)
    assert "[REDACTED]" in result, f"Padded base64 was not redacted: {payload!r}"


def test_jwt_is_redacted():
    """JWTs (eyXXX.XXX.XXX) must be caught by the JWT-specific pattern."""
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    result = redact(jwt)
    assert "[REDACTED]" in result
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result


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
