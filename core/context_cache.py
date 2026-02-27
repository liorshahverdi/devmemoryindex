"""
Context Cache — in-memory LRU cache for ContextEngine.build() results.

Eliminates redundant embed + search + format cycles for repeated queries
within the same process (e.g. multiple MCP tool calls in a Claude session).

Design:
- Module-level singleton (_cache) shared across all ContextEngine instances
- Key: sha256(query | repo | format | intent)
- Max 50 entries, 5-minute TTL
- Invalidated on store.add() so stale results never survive a new memory insert
"""

import hashlib
import time
from collections import OrderedDict

_MAX_SIZE = 50
_TTL = 300  # seconds


class _ContextCache:
    def __init__(self):
        # OrderedDict preserves insertion order for LRU eviction
        self._store: OrderedDict[str, tuple[dict, float]] = OrderedDict()

    @staticmethod
    def _key(query: str, repo: str | None, format: str, intent: str | None) -> str:
        raw = f"{query}|{repo or ''}|{format}|{intent or ''}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, query: str, repo: str | None, format: str, intent: str | None) -> dict | None:
        key = self._key(query, repo, format, intent)
        if key not in self._store:
            return None
        result, ts = self._store[key]
        if time.time() - ts > _TTL:
            del self._store[key]
            return None
        self._store.move_to_end(key)  # mark as recently used
        return result

    def set(self, query: str, repo: str | None, format: str, intent: str | None, result: dict) -> None:
        key = self._key(query, repo, format, intent)
        self._store[key] = (result, time.time())
        self._store.move_to_end(key)
        while len(self._store) > _MAX_SIZE:
            self._store.popitem(last=False)  # evict LRU

    def invalidate(self) -> None:
        """Clear all entries. Called when any new memory is added to the store."""
        self._store.clear()

    def size(self) -> int:
        return len(self._store)


# Module-level singleton — shared across all ContextEngine instances
cache = _ContextCache()
