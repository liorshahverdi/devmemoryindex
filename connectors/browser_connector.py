"""
Browser Connector — indexes bookmarks from Chrome-family browsers and Firefox.

Chrome, Brave, Edge, and Arc all use the same JSON bookmark format.
Firefox uses a SQLite database (stdlib sqlite3, no extra deps).

Memory fields:
  type        "browser_bookmark"
  summary     "Page Title: https://example.com"
  raw_text    "Title: ...\nURL: ...\nFolder: ..."
  source      "browser"
  repo        None
  timestamp   Chrome: bookmark add_date (epoch μs); Firefox: last_visit_date
  importance  0.5
  tags        ["bookmark", "browser", <browser_name>]
"""

import hashlib
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from connectors.base import Connector
from core.embeddings import embed
from core.schema import Memory

# Chrome-family bookmark file locations (macOS)
_CHROME_PROFILES = [
    ("chrome",  Path.home() / "Library/Application Support/Google/Chrome/Default/Bookmarks"),
    ("chrome",  Path.home() / "Library/Application Support/Google/Chrome/Profile 1/Bookmarks"),
    ("brave",   Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser/Default/Bookmarks"),
    ("edge",    Path.home() / "Library/Application Support/Microsoft Edge/Default/Bookmarks"),
    ("arc",     Path.home() / "Library/Application Support/Arc/User Data/Default/Bookmarks"),
    ("chromium",Path.home() / "Library/Application Support/Chromium/Default/Bookmarks"),
]

# Firefox profile directory (macOS)
_FIREFOX_DIR = Path.home() / "Library/Application Support/Firefox/Profiles"

# Chrome epoch starts at 1601-01-01; offset to Unix epoch in microseconds
_CHROME_EPOCH_OFFSET_US = 11_644_473_600 * 1_000_000


class BrowserConnector(Connector):
    name = "browser"

    def collect(self) -> int:
        count = 0
        seen_urls: set[str] = set()

        for browser_name, bookmark_path in _CHROME_PROFILES:
            if bookmark_path.exists():
                count += self._index_chrome(bookmark_path, browser_name, seen_urls)

        count += self._index_firefox(seen_urls)
        return count

    # ── Chrome-family ──────────────────────────────────────────────────

    def _index_chrome(self, path: Path, browser: str, seen_urls: set) -> int:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return 0

        roots = data.get("roots", {})
        bookmarks: list[tuple[str, str, str, int]] = []  # (title, url, folder, add_date)
        for root_key in ("bookmark_bar", "other", "synced", "mobile"):
            _walk_chrome_tree(roots.get(root_key, {}), bookmarks, folder="")

        added = 0
        for title, url, folder, add_date_us in bookmarks:
            if not url.startswith("http"):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            mem_id = hashlib.sha256(url.encode()).hexdigest()
            if self.store.exists(mem_id):
                continue

            # Chrome stores add_date as microseconds since 1601-01-01
            try:
                ts = datetime.fromtimestamp((add_date_us - _CHROME_EPOCH_OFFSET_US) / 1_000_000)
            except (OSError, ValueError):
                ts = datetime.now(timezone.utc)

            summary = f"{title}: {url}"[:200]
            raw_text = f"Title: {title}\nURL: {url}" + (f"\nFolder: {folder}" if folder else "")

            memory = Memory(
                id=mem_id,
                type="browser_bookmark",
                summary=summary,
                raw_text=raw_text,
                source="browser",
                repo=None,
                timestamp=ts,
                tags=["bookmark", "browser", browser],
                importance=0.5,
            )
            self.store.add(memory, embed(summary))
            added += 1
        return added

    # ── Firefox ────────────────────────────────────────────────────────

    def _index_firefox(self, seen_urls: set) -> int:
        if not _FIREFOX_DIR.exists():
            return 0
        added = 0
        for db_path in _FIREFOX_DIR.glob("*/places.sqlite"):
            added += self._index_firefox_db(db_path, seen_urls)
        return added

    def _index_firefox_db(self, db_path: Path, seen_urls: set) -> int:
        # Copy DB to temp file — Firefox locks the original while open
        tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        try:
            shutil.copy2(db_path, tmp_path)
            con = sqlite3.connect(tmp_path)
            rows = con.execute("""
                SELECT mp.title, mp.url, mp.last_visit_date
                FROM moz_places mp
                JOIN moz_bookmarks mb ON mb.fk = mp.id
                WHERE mp.url LIKE 'http%'
                  AND mp.title IS NOT NULL
                  AND mp.title != ''
                ORDER BY mp.last_visit_date DESC
            """).fetchall()
            con.close()
        except Exception:
            return 0
        finally:
            tmp_path.unlink(missing_ok=True)

        added = 0
        for title, url, last_visit_us in rows:
            if url in seen_urls:
                continue
            seen_urls.add(url)

            mem_id = hashlib.sha256(url.encode()).hexdigest()
            if self.store.exists(mem_id):
                continue

            try:
                ts = datetime.fromtimestamp(last_visit_us / 1_000_000) if last_visit_us else datetime.now(timezone.utc)
            except (OSError, ValueError):
                ts = datetime.now(timezone.utc)

            summary = f"{title}: {url}"[:200]
            memory = Memory(
                id=mem_id,
                type="browser_bookmark",
                summary=summary,
                raw_text=f"Title: {title}\nURL: {url}",
                source="browser",
                repo=None,
                timestamp=ts,
                tags=["bookmark", "browser", "firefox"],
                importance=0.5,
            )
            self.store.add(memory, embed(summary))
            added += 1
        return added


# ── Helpers ────────────────────────────────────────────────────────────


def _walk_chrome_tree(
    node: dict,
    result: list,
    folder: str,
) -> None:
    """Recursively collect (title, url, folder, add_date) from Chrome bookmark tree."""
    if not isinstance(node, dict):
        return
    node_type = node.get("type")
    if node_type == "url":
        result.append((
            node.get("name", ""),
            node.get("url", ""),
            folder,
            int(node.get("date_added", 0)),
        ))
    elif node_type == "folder":
        subfolder = node.get("name", "")
        full_folder = f"{folder}/{subfolder}".lstrip("/") if subfolder else folder
        for child in node.get("children", []):
            _walk_chrome_tree(child, result, full_folder)
    else:
        # Handle root-level container nodes without explicit type
        for child in node.get("children", []):
            _walk_chrome_tree(child, result, folder)
