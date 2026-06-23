from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from core.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


def _vector(_text: str) -> list[float]:
    return [0.0] * 384


def test_collect_fetches_notes_api_and_indexes_chunks(store, monkeypatch):
    from connectors.markdown_notes_connector import MarkdownNotesApiConnector

    calls = []

    def fake_fetch(url: str, token: str, timeout: float):
        calls.append((url, token, timeout))
        return {
            "notes": [
                {
                    "id": "note-1",
                    "title": "Integration Plan",
                    "content": "## Architecture\n" + "Remote connector keeps cached notes available. " * 8,
                    "dateModified": 1_700_000_000_000,
                    "isPinned": True,
                    "folderId": "projects",
                }
            ],
            "total": 1,
        }

    monkeypatch.setattr("connectors.markdown_notes_connector.embed", _vector)
    connector = MarkdownNotesApiConnector(
        url="http://notes.local:5173/",
        token="mnpat_test",
        repo="personal-notes",
        fetch_json=fake_fetch,
    )
    connector.store = store

    assert connector.collect() == 1
    assert calls == [("http://notes.local:5173/api/notes", "mnpat_test", 5.0)]

    memories = store.get_all()
    assert len(memories) == 1
    memory = memories[0]
    assert memory["type"] == "markdown_notes_note"
    assert memory["source"] == "markdown-notes-api"
    assert memory["repo"] == "personal-notes"
    assert memory["summary"] == "Integration Plan > Architecture"
    assert "Remote connector keeps cached notes" in memory["raw_text"]
    assert "markdown-notes" in memory["tags"]
    assert "note_id:note-1" in memory["tags"]
    assert "folder:projects" in memory["tags"]
    assert "pinned" in memory["tags"]
    assert connector.last_status["ok"] is True
    assert connector.last_status["notes_seen"] == 1


def test_collect_is_idempotent_for_unchanged_remote_notes(store, monkeypatch):
    from connectors.markdown_notes_connector import MarkdownNotesApiConnector

    payload = {
        "notes": [
            {
                "id": "note-1",
                "title": "Stable Note",
                "content": "Stable note content " * 10,
                "dateModified": 1_700_000_000_000,
            }
        ],
        "total": 1,
    }

    monkeypatch.setattr("connectors.markdown_notes_connector.embed", _vector)
    connector = MarkdownNotesApiConnector(
        url="http://notes.local:5173",
        token="mnpat_test",
        repo="personal-notes",
        fetch_json=lambda *_args: payload,
    )
    connector.store = store

    assert connector.collect() == 1
    assert connector.collect() == 0
    assert len(store.get_all()) == 1


def test_unavailable_remote_does_not_delete_cached_notes(store, monkeypatch):
    from connectors.markdown_notes_connector import MarkdownNotesApiConnector

    payload = {
        "notes": [
            {
                "id": "note-1",
                "title": "Cached Note",
                "content": "Cached content survives remote outages. " * 8,
                "dateModified": 1_700_000_000_000,
            }
        ],
        "total": 1,
    }

    monkeypatch.setattr("connectors.markdown_notes_connector.embed", _vector)
    connector = MarkdownNotesApiConnector(
        url="http://notes.local:5173",
        token="mnpat_test",
        fetch_json=lambda *_args: payload,
    )
    connector.store = store
    assert connector.collect() == 1

    connector.fetch_json = lambda *_args: (_ for _ in ()).throw(URLError("offline"))
    assert connector.collect() == 0
    assert len(store.get_all()) == 1
    assert connector.last_status["ok"] is False
    assert "offline" in connector.last_status["error"]


def test_missing_url_or_token_is_a_noop(store):
    from connectors.markdown_notes_connector import MarkdownNotesApiConnector

    connector = MarkdownNotesApiConnector(url="", token="")
    connector.store = store

    assert connector.collect() == 0
    assert connector.last_status["ok"] is False
    assert connector.last_status["error"] == "missing_url_or_token"
