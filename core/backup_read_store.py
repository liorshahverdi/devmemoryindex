"""Fast read-only memory store backed by the JSON backup export.

This avoids importing LanceDB/SentenceTransformer on latency-sensitive read paths
such as the default CLI `ask` command. It is intentionally read-only; writes still
use MemoryStore.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from core.ranking import recency_score

_STOPWORDS = {
    "a", "an", "the", "is", "in", "on", "at", "to", "for", "of", "and",
    "or", "where", "what", "how", "why", "when", "i", "me", "my", "it",
    "this", "that", "with", "from", "by", "be", "was", "are", "do", "did",
    "does", "not", "no", "can", "could", "would", "should", "have", "has",
    "had", "there", "any", "which", "who", "its", "as", "if", "were", "made",
}


_DEFAULT_BACKUP_PATH = Path.home() / ".config" / "devmemory" / "backups" / "memories_latest.json"


class BackupReadStore:
    def __init__(self, path: str | Path = _DEFAULT_BACKUP_PATH):
        self.path = Path(path)
        self._rows: list[dict[str, Any]] | None = None

    def _load(self) -> list[dict[str, Any]]:
        if self._rows is None:
            if not self.path.exists():
                self._rows = []
            else:
                self._rows = json.loads(self.path.read_text())
        return cast(list[dict[str, Any]], self._rows)

    @staticmethod
    def _recency(value: Any) -> float:
        if isinstance(value, datetime):
            return recency_score(value)
        if isinstance(value, str):
            try:
                return recency_score(datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None))
            except ValueError:
                return 0.0
        return 0.0

    @staticmethod
    def _terms(query: str) -> list[str]:
        seen: set[str] = set()
        terms: list[str] = []
        for word in re.findall(r"\w+", query.lower()):
            if word in _STOPWORDS or len(word) < 3 or word in seen:
                continue
            seen.add(word)
            terms.append(word)
        return terms[:6]

    @staticmethod
    def _active(row: dict[str, Any]) -> bool:
        return row.get("status") in (None, "", "active")

    def text_search(
        self,
        query: str,
        k: int = 5,
        type_filter: str | None = None,
        repo_filter: str | None = None,
        speaker_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        terms = self._terms(query)
        min_terms = 2 if len(terms) >= 3 else 1
        scored: list[tuple[tuple[float, ...], dict[str, Any]]] = []
        for row in self._load():
            if not self._active(row):
                continue
            if type_filter and row.get("type") != type_filter:
                continue
            if repo_filter and row.get("repo") != repo_filter:
                continue
            if speaker_filter and f"speaker:{speaker_filter}" not in (row.get("tags") or []):
                continue
            text = f"{row.get('summary') or ''} {row.get('raw_text') or ''}".lower()
            matches = sum(1 for term in terms if term in text)
            if matches < min_terms:
                continue
            summary_text = (row.get("summary") or "").lower()
            score = (
                float(matches),
                sum(1 for term in terms if term in summary_text),
                float(row.get("importance") or 0.0),
                self._recency(row.get("timestamp")),
            )
            scored.append((score, dict(row)))
        return [row for _score, row in sorted(scored, key=lambda item: item[0], reverse=True)[:k]]

    def hybrid_search(self, query: str, vector: list, **kwargs) -> list[dict[str, Any]]:
        return self.text_search(query, **kwargs)

    def get_by_id(self, memory_id: str):
        matches = [row for row in self._load() if str(row.get("id", "")).startswith(memory_id)]
        return matches[0] if len(matches) == 1 else None


def default_backup_path() -> Path:
    return _DEFAULT_BACKUP_PATH
