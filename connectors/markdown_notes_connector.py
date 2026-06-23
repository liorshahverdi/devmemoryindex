"""
Remote Markdown Notes API connector.

Pulls notes from a running Markdown Notes web app using its bearer-token API and
indexes them into DevMemoryIndex without making the remote app a hard runtime
dependency. If the upstream is unavailable, collect() returns 0 and leaves any
previously cached memories intact.

Configuration can be supplied either directly to the constructor (tests/tools) or
via environment variables for daemon use:

  MARKDOWN_NOTES_URL=http://127.0.0.1:5173
  MARKDOWN_NOTES_TOKEN=mnpat_...
  MARKDOWN_NOTES_REPO=markdown-notes
  MARKDOWN_NOTES_TIMEOUT_SECONDS=5
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Callable, Any
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from connectors.base import Connector
from connectors.markdown_connector import _chunk_by_h2, MIN_CHUNK_LEN, MAX_CHUNK_LEN
from core.embeddings import embed
from core.schema import Memory

FetchJson = Callable[[str, str, float], dict[str, Any]]

DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_REPO = "markdown-notes"


class MarkdownNotesApiConnector(Connector):
    name = "markdown-notes-api"

    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        *,
        repo: str | None = None,
        timeout_seconds: float | None = None,
        fetch_json: FetchJson | None = None,
    ):
        super().__init__()
        self.url = (url if url is not None else os.environ.get("MARKDOWN_NOTES_URL", "")).strip()
        self.token = (token if token is not None else os.environ.get("MARKDOWN_NOTES_TOKEN", "")).strip()
        self.repo = (repo if repo is not None else os.environ.get("MARKDOWN_NOTES_REPO", DEFAULT_REPO)).strip() or DEFAULT_REPO
        self.timeout_seconds = _coerce_timeout(timeout_seconds)
        self.fetch_json: FetchJson = fetch_json or _fetch_json
        self.last_status: dict[str, Any] = {
            "ok": False,
            "error": "not_run",
            "notes_seen": 0,
            "chunks_added": 0,
        }

    def collect(self) -> int:
        if not self.url or not self.token:
            self.last_status = {
                "ok": False,
                "error": "missing_url_or_token",
                "notes_seen": 0,
                "chunks_added": 0,
            }
            return 0

        endpoint = _notes_endpoint(self.url)
        try:
            payload = self.fetch_json(endpoint, self.token, self.timeout_seconds)
        except Exception as exc:
            self.last_status = {
                "ok": False,
                "error": str(exc),
                "notes_seen": 0,
                "chunks_added": 0,
            }
            return 0

        notes = payload.get("notes", [])
        if not isinstance(notes, list):
            self.last_status = {
                "ok": False,
                "error": "invalid_notes_payload",
                "notes_seen": 0,
                "chunks_added": 0,
            }
            return 0

        memories: list[Memory] = []
        vectors: list[list[float]] = []
        for note in notes:
            if not isinstance(note, dict):
                continue
            for memory, embed_input in self._memories_for_note(note):
                memories.append(memory)
                vectors.append(embed(embed_input))

        added = self.store.add_batch(memories, vectors)
        self.last_status = {
            "ok": True,
            "error": "",
            "notes_seen": len(notes),
            "chunks_added": added,
            "endpoint": endpoint,
        }
        return added

    def _memories_for_note(self, note: dict[str, Any]) -> list[tuple[Memory, str]]:
        note_id = str(note.get("id") or "").strip()
        title = str(note.get("title") or note_id or "Untitled Note").strip()
        content = str(note.get("content") or "")
        if not note_id or not content.strip():
            return []

        timestamp = _parse_markdown_notes_timestamp(note.get("dateModified"))
        tags = ["markdown", "markdown-notes", "remote", f"note_id:{note_id}"]
        folder_id = note.get("folderId")
        if folder_id:
            tags.append(f"folder:{folder_id}")
        if note.get("isPinned"):
            tags.append("pinned")

        chunks = _chunk_by_h2(content, title)
        results: list[tuple[Memory, str]] = []
        for idx, (chunk_title, chunk_text) in enumerate(chunks):
            chunk_text = chunk_text.strip()
            if len(chunk_text) < MIN_CHUNK_LEN:
                continue
            redacted = self._redact(chunk_text)
            content_hash = hashlib.sha256(redacted.encode()).hexdigest()
            mem_id = hashlib.sha256(
                f"markdown-notes-api|{self.url}|{note_id}|{idx}|{content_hash}".encode()
            ).hexdigest()
            raw_text = redacted[:MAX_CHUNK_LEN]
            summary = chunk_title[:200]
            memory = Memory(
                id=mem_id,
                type="markdown_notes_note",
                summary=summary,
                raw_text=raw_text,
                source="markdown-notes-api",
                repo=self.repo,
                timestamp=timestamp,
                tags=tags,
                importance=0.82 if note.get("isPinned") else 0.72,
            )
            results.append((memory, f"{summary} {raw_text}"))
        return results


def _notes_endpoint(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/notes"


def _coerce_timeout(timeout_seconds: float | None) -> float:
    if timeout_seconds is not None:
        return float(timeout_seconds)
    raw = os.environ.get("MARKDOWN_NOTES_TIMEOUT_SECONDS")
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS


def _parse_markdown_notes_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        # Markdown Notes stores dateModified as epoch milliseconds.
        seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.utcnow()


def _fetch_json(url: str, token: str, timeout: float) -> dict[str, Any]:
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "devmemoryindex-markdown-notes-api/1.0",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} from Markdown Notes API") from exc
    except URLError as exc:
        raise RuntimeError(f"Markdown Notes API unavailable: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid JSON from Markdown Notes API") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Invalid JSON object from Markdown Notes API")
    return parsed
