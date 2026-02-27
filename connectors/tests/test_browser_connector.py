"""
Tests for BrowserConnector:
1. Chrome bookmark JSON is parsed and memories stored.
2. Nested Chrome folders are traversed.
3. Non-http URLs (chrome-extension://, etc.) are skipped.
4. Deduplication — same URL indexed only once across two Chrome profiles.
5. _walk_chrome_tree handles folders and url nodes.
6. Firefox SQLite is parsed and memories stored.
7. seen_urls prevents double-indexing same URL across browsers.
"""

import hashlib
import json
import sqlite3
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

from connectors.browser_connector import (
    BrowserConnector,
    _walk_chrome_tree,
    _CHROME_EPOCH_OFFSET_US,
)
from core.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "db"))


def _connector(store):
    c = BrowserConnector()
    c.store = store
    return c


def _chrome_bookmarks(bookmarks: list[dict]) -> dict:
    """Build a minimal Chrome Bookmarks JSON structure."""
    return {
        "roots": {
            "bookmark_bar": {
                "children": bookmarks,
                "name": "Bookmarks bar",
                "type": "folder",
            },
            "other": {},
            "synced": {},
        }
    }


def _url_node(title, url, folder_children=None):
    node = {"type": "url", "name": title, "url": url, "date_added": str(_CHROME_EPOCH_OFFSET_US + 1_000_000)}
    return node


# ── _walk_chrome_tree ─────────────────────────────────────────────────────────

def test_walk_url_node():
    node = _url_node("Example", "https://example.com")
    result = []
    _walk_chrome_tree(node, result, "")
    assert len(result) == 1
    assert result[0][1] == "https://example.com"


def test_walk_folder_recurse():
    folder = {
        "type": "folder",
        "name": "Dev",
        "children": [_url_node("GitHub", "https://github.com")],
    }
    result = []
    _walk_chrome_tree(folder, result, "")
    assert len(result) == 1
    assert result[0][2] == "Dev"  # folder name captured


def test_walk_skips_non_dict():
    result = []
    _walk_chrome_tree("not a dict", result, "")
    assert result == []


def test_walk_nested_folders():
    inner = {"type": "folder", "name": "Python", "children": [_url_node("PyPI", "https://pypi.org")]}
    outer = {"type": "folder", "name": "Lang", "children": [inner]}
    result = []
    _walk_chrome_tree(outer, result, "")
    assert result[0][2] == "Lang/Python"


# ── Chrome indexing ───────────────────────────────────────────────────────────

def test_chrome_index(store, tmp_path):
    bm_file = tmp_path / "Bookmarks"
    data = _chrome_bookmarks([_url_node("Python", "https://python.org")])
    bm_file.write_text(json.dumps(data), encoding="utf-8")

    c = _connector(store)
    count = c._index_chrome(bm_file, "chrome", set())
    assert count == 1
    memories = store.get_all()
    assert any(m["type"] == "browser_bookmark" for m in memories)
    assert any("python.org" in m["summary"] for m in memories)


def test_chrome_skips_non_http(store, tmp_path):
    bm_file = tmp_path / "Bookmarks"
    data = _chrome_bookmarks([
        {"type": "url", "name": "Ext", "url": "chrome-extension://abc", "date_added": "0"},
    ])
    bm_file.write_text(json.dumps(data), encoding="utf-8")

    c = _connector(store)
    assert c._index_chrome(bm_file, "chrome", set()) == 0


def test_chrome_deduplication_across_profiles(store, tmp_path):
    url = "https://docs.python.org"
    data = _chrome_bookmarks([_url_node("Docs", url)])

    f1 = tmp_path / "Bookmarks1"
    f2 = tmp_path / "Bookmarks2"
    f1.write_text(json.dumps(data))
    f2.write_text(json.dumps(data))

    c = _connector(store)
    seen: set = set()
    first = c._index_chrome(f1, "chrome", seen)
    second = c._index_chrome(f2, "chrome", seen)  # same seen set
    assert first == 1
    assert second == 0  # URL already in seen_urls


def test_chrome_memory_has_browser_tag(store, tmp_path):
    bm_file = tmp_path / "Bookmarks"
    data = _chrome_bookmarks([_url_node("Brave Site", "https://brave.com")])
    bm_file.write_text(json.dumps(data))

    c = _connector(store)
    c._index_chrome(bm_file, "brave", set())
    memories = store.get_all()
    assert any("brave" in m["tags"] for m in memories)


# ── Firefox indexing ──────────────────────────────────────────────────────────

def _make_firefox_db(path: Path, rows: list[tuple]) -> Path:
    """Create a minimal places.sqlite with moz_places + moz_bookmarks."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE moz_places (id INTEGER PRIMARY KEY, title TEXT, url TEXT, last_visit_date INTEGER)")
    con.execute("CREATE TABLE moz_bookmarks (id INTEGER PRIMARY KEY, fk INTEGER)")
    for i, (title, url, ts) in enumerate(rows, 1):
        con.execute("INSERT INTO moz_places VALUES (?, ?, ?, ?)", (i, title, url, ts))
        con.execute("INSERT INTO moz_bookmarks VALUES (?, ?)", (i, i))
    con.commit()
    con.close()
    return path


def test_firefox_index(store, tmp_path):
    db = _make_firefox_db(
        tmp_path / "places.sqlite",
        [("Mozilla", "https://mozilla.org", 1_700_000_000 * 1_000_000)],
    )
    c = _connector(store)
    count = c._index_firefox_db(db, set())
    assert count == 1
    memories = store.get_all()
    assert any("mozilla.org" in m["summary"] for m in memories)


def test_firefox_dedup_with_seen_urls(store, tmp_path):
    db = _make_firefox_db(
        tmp_path / "places.sqlite",
        [("MDN", "https://developer.mozilla.org", 0)],
    )
    c = _connector(store)
    seen = {"https://developer.mozilla.org"}
    assert c._index_firefox_db(db, seen) == 0


def test_firefox_tag_includes_firefox(store, tmp_path):
    db = _make_firefox_db(
        tmp_path / "places.sqlite",
        [("Bugzilla", "https://bugzilla.mozilla.org", 0)],
    )
    c = _connector(store)
    c._index_firefox_db(db, set())
    memories = store.get_all()
    assert any("firefox" in m["tags"] for m in memories)
