"""Tests for core/token_budget.py."""

from core.token_budget import estimate_tokens, pack_within_budget, METADATA_OVERHEAD


# ── estimate_tokens ──────────────────────────────────────────────────────────


def test_estimate_tokens_prose():
    """Prose estimate should be in a sane range (not wildly off)."""
    text = "The quick brown fox jumps over the lazy dog."
    est = estimate_tokens(text)
    # 44 chars → 11 tokens. Real tokenizers give ~11. Accept ±50%.
    assert 6 <= est <= 20, f"Unexpected estimate {est} for prose"


def test_estimate_tokens_code():
    """Code estimate must not severely undercount the way word-split did.

    A function definition with snake_case identifiers has many short tokens.
    Word-count gives 1 token per identifier, chars/4 is closer to reality.
    """
    code = "def _batch_existing_ids(self, ids: list[str]) -> set[str]:\n    pass"
    est = estimate_tokens(code)
    # 67 chars → 16 tokens. Word-count would give 8 (severely under).
    assert est >= 12, f"Code estimate {est} too low — likely using word count"


def test_estimate_tokens_empty():
    """Empty string returns at least 1 (never zero, avoids division issues)."""
    assert estimate_tokens("") == 1


def test_estimate_tokens_single_char():
    assert estimate_tokens("x") == 1


# ── pack_within_budget ───────────────────────────────────────────────────────


def _make_memories(summaries: list[str]) -> list[dict]:
    from datetime import datetime
    return [
        {"summary": s, "type": "agent_solution", "repo": None,
         "importance": 0.5, "timestamp": datetime.utcnow()}
        for s in summaries
    ]


def test_pack_respects_max_tokens():
    """Pack must not exceed the token budget."""
    # Each summary is 40 chars → ~10 tokens + 20 overhead = 30 per item
    memories = _make_memories(["x" * 40] * 20)
    selected, total = pack_within_budget(memories, max_tokens=100)
    assert total <= 100 + METADATA_OVERHEAD  # allow one item's overhead slack
    assert len(selected) < 20


def test_pack_respects_max_items():
    """Pack must not exceed the max_items cap even if budget allows more."""
    memories = _make_memories(["hi"] * 20)
    selected, _ = pack_within_budget(memories, max_tokens=10_000, max_items=5)
    assert len(selected) == 5


def test_pack_empty_input():
    selected, total = pack_within_budget([], max_tokens=4000)
    assert selected == []
    assert total == 0


def test_pack_preserves_order():
    """Items are taken greedily in input order (highest-ranked first)."""
    memories = _make_memories(["first", "second", "third"])
    selected, _ = pack_within_budget(memories, max_tokens=10_000, max_items=2)
    assert [m["summary"] for m in selected] == ["first", "second"]
