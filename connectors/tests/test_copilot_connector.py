"""
Tests for CopilotConnector:
1. _parts_to_text extracts inline text parts.
2. _parts_to_text skips toolInvocationSerialized parts.
3. _parts_to_text skips inlineReference parts.
4. _parts_to_text concatenates thinking + text parts.
5. _parts_to_text returns empty string for empty parts.
6. _extract_responses_from_jsonl ignores kind != 2 lines.
7. _extract_responses_from_jsonl ignores kind=2 lines whose key doesn't end with "response".
8. _extract_responses_from_jsonl collects response text from matching lines.
9. Short responses (< MIN_RESPONSE_LEN) are skipped by _parse_session.
10. Valid responses are stored as copilot_chat memories.
11. Deduplication — same content indexed only once.
12. Malformed JSONL returns 0 without raising.
"""

import json
import pytest
from pathlib import Path
from connectors.copilot_connector import (
    CopilotConnector,
    _parts_to_text,
    _extract_responses_from_jsonl,
    MIN_RESPONSE_LEN,
)
from core.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


def _connector(store):
    c = CopilotConnector()
    c.store = store
    return c


def _write_jsonl(path: Path, lines: list) -> Path:
    path.write_text("\n".join(json.dumps(l) for l in lines), encoding="utf-8")
    return path


def _response_line(request_idx: int, parts: list) -> dict:
    return {"kind": 2, "k": ["requests", request_idx, "response"], "v": parts}


def _text_part(text: str) -> dict:
    return {"value": text, "supportThemeIcons": False, "supportHtml": False}


def _tool_part() -> dict:
    return {"kind": "toolInvocationSerialized", "invocationMessage": {"value": "Reading file"}}


def _ref_part() -> dict:
    return {"kind": "inlineReference", "inlineReference": {"name": "foo"}}


def _thinking_part(text: str) -> dict:
    return {"kind": "thinking", "value": text}


# ── _parts_to_text ─────────────────────────────────────────────────────────────

def test_parts_to_text_inline_text():
    assert _parts_to_text([_text_part("Hello world")]) == "Hello world"


def test_parts_to_text_skips_tool_parts():
    parts = [_tool_part(), _text_part("Here is the result.")]
    assert _parts_to_text(parts) == "Here is the result."


def test_parts_to_text_skips_inline_refs():
    parts = [_text_part("Use "), _ref_part(), _text_part(" to fix it.")]
    assert _parts_to_text(parts) == "Use  to fix it."


def test_parts_to_text_includes_thinking():
    parts = [_thinking_part("I should use create_table."), _text_part("The answer is x.")]
    result = _parts_to_text(parts)
    assert "I should use create_table." in result
    assert "The answer is x." in result


def test_parts_to_text_empty_parts():
    assert _parts_to_text([]) == ""


def test_parts_to_text_skips_empty_strings():
    parts = [{"value": "", "supportThemeIcons": False}, _text_part("actual content")]
    assert _parts_to_text(parts) == "actual content"


def test_parts_to_text_non_dict_parts_ignored():
    parts = ["string", None, 42, _text_part("valid")]
    assert _parts_to_text(parts) == "valid"


# ── _extract_responses_from_jsonl ─────────────────────────────────────────────

def test_extract_ignores_non_kind2(tmp_path):
    path = _write_jsonl(tmp_path / "s.jsonl", [
        {"kind": 0, "v": {"requests": []}},
        {"kind": 1, "k": ["requests", 0, "result"], "v": {}},
    ])
    assert _extract_responses_from_jsonl(path) == []


def test_extract_ignores_wrong_key(tmp_path):
    path = _write_jsonl(tmp_path / "s.jsonl", [
        {"kind": 2, "k": ["requests"], "v": [{"requestId": "abc"}]},
    ])
    assert _extract_responses_from_jsonl(path) == []


def test_extract_collects_response_text(tmp_path):
    line = _response_line(0, [_text_part("The fix is to use create_table with exist_ok=True.")])
    path = _write_jsonl(tmp_path / "s.jsonl", [line])
    results = _extract_responses_from_jsonl(path)
    assert len(results) == 1
    assert "create_table" in results[0]


def test_extract_multiple_responses(tmp_path):
    lines = [
        _response_line(0, [_text_part("First answer here.")]),
        _response_line(1, [_text_part("Second answer here.")]),
    ]
    path = _write_jsonl(tmp_path / "s.jsonl", lines)
    results = _extract_responses_from_jsonl(path)
    assert len(results) == 2


def test_extract_skips_tool_only_response(tmp_path):
    line = _response_line(0, [_tool_part()])
    path = _write_jsonl(tmp_path / "s.jsonl", [line])
    assert _extract_responses_from_jsonl(path) == []


def test_extract_malformed_jsonl(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text("not json\n{also bad\n", encoding="utf-8")
    assert _extract_responses_from_jsonl(path) == []


# ── CopilotConnector._parse_session ──────────────────────────────────────────

def test_short_response_skipped(store, tmp_path):
    c = _connector(store)
    line = _response_line(0, [_text_part("ok")])
    path = _write_jsonl(tmp_path / "s.jsonl", [line])
    assert c._parse_session(path) == 0


def test_long_response_indexed(store, tmp_path):
    c = _connector(store)
    text = "A" * (MIN_RESPONSE_LEN + 10)
    line = _response_line(0, [_text_part(text)])
    path = _write_jsonl(tmp_path / "s.jsonl", [line])
    assert c._parse_session(path) == 1
    memories = store.get_all()
    assert any(m["type"] == "copilot_chat" for m in memories)


def test_deduplication(store, tmp_path):
    c = _connector(store)
    text = "B" * (MIN_RESPONSE_LEN + 10)
    line = _response_line(0, [_text_part(text)])
    path = _write_jsonl(tmp_path / "s.jsonl", [line])
    first = c._parse_session(path)
    second = c._parse_session(path)
    assert first == 1
    assert second == 0


def test_repo_passed_through(store, tmp_path):
    c = _connector(store)
    text = "C" * (MIN_RESPONSE_LEN + 10)
    line = _response_line(0, [_text_part(text)])
    path = _write_jsonl(tmp_path / "s.jsonl", [line])
    c._parse_session(path, repo="/projects/myapp")
    memories = store.get_all()
    assert any(m["repo"] == "/projects/myapp" for m in memories)


def test_empty_jsonl_returns_zero(store, tmp_path):
    c = _connector(store)
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    assert c._parse_session(path) == 0
