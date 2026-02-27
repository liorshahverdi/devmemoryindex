"""
Tests for CopilotConnector:
1. Extracts assistant messages from {"role": "assistant", "content": "..."} format.
2. Extracts from {"role": "model", "parts": [{"text": "..."}]} format.
3. Extracts from nested {"messages": [...]} structure.
4. Short messages (< MIN_RESPONSE_LEN) are skipped.
5. Deduplication — same content indexed only once.
6. Missing/unrecognised JSON structure returns 0 without raising.
7. Deeply nested structures are guarded by depth limit.
"""

import json
import pytest
from connectors.copilot_connector import CopilotConnector, _extract_assistant_messages, MIN_RESPONSE_LEN
from core.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


def _connector(store):
    c = CopilotConnector()
    c.store = store
    return c


def _write_session(path, data):
    (path).write_text(json.dumps(data), encoding="utf-8")


# ── _extract_assistant_messages ───────────────────────────────────────────────

def test_extract_assistant_role():
    msg = "This is a helpful assistant response."
    data = {"messages": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": msg}]}
    results = _extract_assistant_messages(data)
    assert msg in results


def test_extract_model_parts():
    msg = "The answer is 42. Here is some extra detail for length."
    data = {"role": "model", "parts": [{"text": msg}]}
    results = _extract_assistant_messages(data)
    assert msg in results


def test_extract_nested_turns():
    msg = "Here is my detailed explanation of the algorithm."
    data = {"turns": [{"role": "assistant", "content": msg}]}
    results = _extract_assistant_messages(data)
    assert msg in results


def test_extract_content_list():
    """content as list of {type: text, text: ...} blocks."""
    msg = "This is the text content."
    data = {"role": "assistant", "content": [{"type": "text", "text": msg}]}
    results = _extract_assistant_messages(data)
    assert any(msg in r for r in results)


def test_extract_user_role_excluded():
    data = {"messages": [{"role": "user", "content": "What is Python?"}]}
    results = _extract_assistant_messages(data)
    assert results == []


def test_extract_top_level_list():
    msg = "Response in a top-level list of sessions."
    data = [{"messages": [{"role": "assistant", "content": msg}]}]
    results = _extract_assistant_messages(data)
    assert msg in results


def test_depth_guard():
    """Deeply nested structure does not recurse infinitely."""
    node = {"messages": []}
    for _ in range(15):
        node = {"messages": [node]}
    # Should complete without recursion error
    results = _extract_assistant_messages(node)
    assert isinstance(results, list)


# ── CopilotConnector._parse_session ──────────────────────────────────────────

def test_short_message_skipped(store, tmp_path):
    c = _connector(store)
    f = tmp_path / "session.json"
    _write_session(f, {"messages": [{"role": "assistant", "content": "ok"}]})
    assert c._parse_session(f) == 0


def test_long_message_indexed(store, tmp_path):
    c = _connector(store)
    f = tmp_path / "session.json"
    msg = "A" * (MIN_RESPONSE_LEN + 10)
    _write_session(f, {"messages": [{"role": "assistant", "content": msg}]})
    assert c._parse_session(f) == 1
    memories = store.get_all()
    assert any(m["type"] == "copilot_chat" for m in memories)


def test_deduplication(store, tmp_path):
    c = _connector(store)
    f = tmp_path / "session.json"
    msg = "B" * (MIN_RESPONSE_LEN + 10)
    _write_session(f, {"messages": [{"role": "assistant", "content": msg}]})
    first = c._parse_session(f)
    second = c._parse_session(f)
    assert first == 1
    assert second == 0


def test_invalid_json_returns_zero(store, tmp_path):
    c = _connector(store)
    f = tmp_path / "bad.json"
    f.write_text("not json at all", encoding="utf-8")
    assert c._parse_session(f) == 0


def test_missing_messages_key_returns_zero(store, tmp_path):
    c = _connector(store)
    f = tmp_path / "empty.json"
    _write_session(f, {"version": 1, "other": "data"})
    assert c._parse_session(f) == 0
