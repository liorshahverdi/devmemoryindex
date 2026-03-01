"""Tests for daemon/jobs — dedup, importance decay, and memory pruning.

Each daemon job imports `get_store` at module level via
`from core.store_provider import get_store`, creating a local binding.
Monkeypatching `core.store_provider.get_store` does NOT update that binding.
Tests must patch the reference in each daemon module directly.
"""

import pytest
import daemon.jobs.dedup as dedup_mod
import daemon.jobs.importance_decay as decay_mod
import daemon.jobs.memory_cleanup as cleanup_mod

from datetime import datetime, timedelta
from core.memory_store import MemoryStore, VECTOR_DIM
from core.schema import Memory


# ── helpers ───────────────────────────────────────────────────────────────────

def _vec(seed: float = 0.1) -> list[float]:
    return [seed] * VECTOR_DIM


def _mem(
    mem_id: str,
    summary: str,
    importance: float = 0.5,
    hours_ago: float = 1.0,
) -> Memory:
    ts = datetime.utcnow() - timedelta(hours=hours_ago)
    return Memory(
        id=mem_id,
        type="agent_solution",
        summary=summary,
        raw_text=summary,
        source="test",
        repo="test-repo",
        timestamp=ts,
        tags=[],
        importance=importance,
    )


@pytest.fixture
def store(tmp_path):
    return MemoryStore(db_path=str(tmp_path))


# ── dedup ─────────────────────────────────────────────────────────────────────

class TestDedupMemories:
    def test_no_duplicates_returns_zero(self, store, monkeypatch):
        store.add(_mem("a", "unique memory alpha"), _vec(0.1))
        store.add(_mem("b", "unique memory beta"), _vec(0.2))

        monkeypatch.setattr(dedup_mod, "get_store", lambda: store)
        deleted = dedup_mod.dedup_memories()
        assert deleted == 0
        assert store.count() == 2

    def test_keeps_higher_importance_duplicate(self, store, monkeypatch):
        store.add(_mem("low", "duplicate summary prefix here", importance=0.3), _vec(0.1))
        store.add(_mem("high", "duplicate summary prefix here", importance=0.8), _vec(0.2))

        monkeypatch.setattr(dedup_mod, "get_store", lambda: store)
        deleted = dedup_mod.dedup_memories()

        assert deleted == 1
        assert store.count() == 1
        remaining = store.get_all()
        assert remaining[0]["id"] == "high"

    def test_dry_run_does_not_delete(self, store, monkeypatch):
        store.add(_mem("x", "same prefix content repeated"), _vec(0.1))
        store.add(_mem("y", "same prefix content repeated", importance=0.9), _vec(0.2))

        monkeypatch.setattr(dedup_mod, "get_store", lambda: store)
        deleted = dedup_mod.dedup_memories(dry_run=True)

        assert deleted == 1       # counts what would be deleted
        assert store.count() == 2  # nothing actually removed

    def test_deduplicates_multiple_groups(self, store, monkeypatch):
        # Group 1 — 3 duplicates
        store.add(_mem("g1a", "alpha group entry", importance=0.5), _vec(0.1))
        store.add(_mem("g1b", "alpha group entry", importance=0.7), _vec(0.2))
        store.add(_mem("g1c", "alpha group entry", importance=0.3), _vec(0.3))
        # Group 2 — 2 duplicates
        store.add(_mem("g2a", "beta group entry", importance=0.6), _vec(0.4))
        store.add(_mem("g2b", "beta group entry", importance=0.4), _vec(0.5))
        # Unique
        store.add(_mem("u", "unique record standalone"), _vec(0.6))

        monkeypatch.setattr(dedup_mod, "get_store", lambda: store)
        deleted = dedup_mod.dedup_memories()

        assert deleted == 3        # 2 from group1 + 1 from group2
        assert store.count() == 3  # winners + unique


# ── importance decay ──────────────────────────────────────────────────────────

class TestDecayImportance:
    def test_reduces_importance(self, store, monkeypatch):
        store.add(_mem("a", "decayable memory", importance=0.8), _vec(0.1))

        monkeypatch.setattr(decay_mod, "get_store", lambda: store)
        count = decay_mod.decay_importance(factor=0.99)

        assert count == 1
        rows = store.get_all()
        assert rows[0]["importance"] == pytest.approx(0.8 * 0.99, rel=1e-4)

    def test_returns_count_of_decayed(self, store, monkeypatch):
        store.add(_mem("a", "memory one", importance=0.6), _vec(0.1))
        store.add(_mem("b", "memory two", importance=0.7), _vec(0.2))

        monkeypatch.setattr(decay_mod, "get_store", lambda: store)
        count = decay_mod.decay_importance()

        assert count == 2

    def test_empty_store_returns_zero(self, store, monkeypatch):
        monkeypatch.setattr(decay_mod, "get_store", lambda: store)
        assert decay_mod.decay_importance() == 0


# ── memory prune ──────────────────────────────────────────────────────────────

class TestPruneMemories:
    def test_prunes_below_importance_floor(self, store, monkeypatch):
        store.add(_mem("weak", "low importance memory", importance=0.03), _vec(0.1))
        store.add(_mem("strong", "high importance memory", importance=0.8), _vec(0.2))

        monkeypatch.setattr(cleanup_mod, "get_store", lambda: store)
        deleted = cleanup_mod.prune_memories(importance_floor=0.05)

        assert deleted == 1
        assert store.count() == 1
        assert store.get_all()[0]["id"] == "strong"

    def test_prunes_old_and_weak(self, store, monkeypatch):
        old_weak = _mem("old", "old weak memory", importance=0.1, hours_ago=24 * 100)
        new_weak = _mem("new", "new weak memory", importance=0.1, hours_ago=1)
        store.add(old_weak, _vec(0.1))
        store.add(new_weak, _vec(0.2))

        monkeypatch.setattr(cleanup_mod, "get_store", lambda: store)
        deleted = cleanup_mod.prune_memories(importance_floor=0.05, max_age_days=90)

        assert deleted == 1
        remaining = store.get_all()
        assert remaining[0]["id"] == "new"

    def test_dry_run_does_not_delete(self, store, monkeypatch):
        store.add(_mem("doomed", "very weak memory", importance=0.01), _vec(0.1))

        monkeypatch.setattr(cleanup_mod, "get_store", lambda: store)
        deleted = cleanup_mod.prune_memories(importance_floor=0.05, dry_run=True)

        assert deleted == 1
        assert store.count() == 1   # still present

    def test_empty_store_returns_zero(self, store, monkeypatch):
        monkeypatch.setattr(cleanup_mod, "get_store", lambda: store)
        assert cleanup_mod.prune_memories() == 0

    def test_strong_memories_survive(self, store, monkeypatch):
        store.add(_mem("s1", "important solution alpha", importance=0.9), _vec(0.1))
        store.add(_mem("s2", "important solution beta", importance=0.75), _vec(0.2))

        monkeypatch.setattr(cleanup_mod, "get_store", lambda: store)
        deleted = cleanup_mod.prune_memories(importance_floor=0.05, max_age_days=90)

        assert deleted == 0
        assert store.count() == 2
