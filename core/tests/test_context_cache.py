import time
import pytest
from core.context_cache import _ContextCache

# Use a fresh instance for each test — never touch the module-level singleton


def _result(memory_count=1):
    return {
        "query": "test",
        "intent": "general",
        "memories": [],
        "context_text": "hello",
        "token_estimate": 10,
        "memory_count": memory_count,
        "cached": False,
    }


class TestContextCache:

    def setup_method(self):
        self.cache = _ContextCache()

    # ── basic hit / miss ─────────────────────────────────────────────────

    def test_miss_on_empty_cache(self):
        assert self.cache.get("q", None, "raw", None) is None

    def test_set_then_get_returns_result(self):
        self.cache.set("q", None, "raw", None, _result())
        assert self.cache.get("q", None, "raw", None) is not None

    def test_get_returns_correct_result(self):
        r = _result(memory_count=5)
        self.cache.set("q", None, "raw", None, r)
        hit = self.cache.get("q", None, "raw", None)
        assert hit["memory_count"] == 5

    def test_different_query_is_miss(self):
        self.cache.set("query A", None, "raw", None, _result())
        assert self.cache.get("query B", None, "raw", None) is None

    def test_different_format_is_miss(self):
        self.cache.set("q", None, "raw", None, _result())
        assert self.cache.get("q", None, "claude", None) is None

    def test_different_repo_is_miss(self):
        self.cache.set("q", "repo1", "raw", None, _result())
        assert self.cache.get("q", "repo2", "raw", None) is None

    def test_different_intent_is_miss(self):
        self.cache.set("q", None, "raw", "debug", _result())
        assert self.cache.get("q", None, "raw", "recall") is None

    # ── invalidation ─────────────────────────────────────────────────────

    def test_invalidate_clears_all_entries(self):
        self.cache.set("q1", None, "raw", None, _result())
        self.cache.set("q2", None, "raw", None, _result())
        self.cache.invalidate()
        assert self.cache.size() == 0

    def test_get_after_invalidate_is_miss(self):
        self.cache.set("q", None, "raw", None, _result())
        self.cache.invalidate()
        assert self.cache.get("q", None, "raw", None) is None

    def test_set_after_invalidate_works(self):
        self.cache.set("q", None, "raw", None, _result())
        self.cache.invalidate()
        self.cache.set("q", None, "raw", None, _result(memory_count=99))
        hit = self.cache.get("q", None, "raw", None)
        assert hit["memory_count"] == 99

    # ── LRU eviction ─────────────────────────────────────────────────────

    def test_evicts_lru_when_over_max_size(self):
        from core.context_cache import _MAX_SIZE
        # Fill to max then add one more
        for i in range(_MAX_SIZE + 1):
            self.cache.set(f"query_{i}", None, "raw", None, _result())
        assert self.cache.size() == _MAX_SIZE

    def test_oldest_entry_evicted_first(self):
        from core.context_cache import _MAX_SIZE
        for i in range(_MAX_SIZE):
            self.cache.set(f"query_{i}", None, "raw", None, _result())
        # "query_0" is the LRU — adding one more should evict it
        self.cache.set("query_new", None, "raw", None, _result())
        assert self.cache.get("query_0", None, "raw", None) is None
        assert self.cache.get("query_new", None, "raw", None) is not None

    # ── TTL expiry ────────────────────────────────────────────────────────

    def test_expired_entry_returns_none(self):
        # Manually insert an entry with a past timestamp
        key = self.cache._key("q", None, "raw", None)
        self.cache._store[key] = (_result(), time.time() - 999)
        assert self.cache.get("q", None, "raw", None) is None

    def test_expired_entry_removed_from_store(self):
        key = self.cache._key("q", None, "raw", None)
        self.cache._store[key] = (_result(), time.time() - 999)
        self.cache.get("q", None, "raw", None)
        assert key not in self.cache._store

    def test_fresh_entry_not_expired(self):
        self.cache.set("q", None, "raw", None, _result())
        assert self.cache.get("q", None, "raw", None) is not None

    # ── size ─────────────────────────────────────────────────────────────

    def test_size_empty(self):
        assert self.cache.size() == 0

    def test_size_after_set(self):
        self.cache.set("q1", None, "raw", None, _result())
        self.cache.set("q2", None, "raw", None, _result())
        assert self.cache.size() == 2

    def test_size_after_invalidate(self):
        self.cache.set("q", None, "raw", None, _result())
        self.cache.invalidate()
        assert self.cache.size() == 0
