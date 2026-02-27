import pytest
import math
from datetime import datetime, timedelta
from core.ranking import recency_score, compute_score


class TestRecencyScore:
    """Tests for the recency_score() helper."""

    def test_returns_float(self):
        score = recency_score(datetime.utcnow())
        assert isinstance(score, float)

    def test_now_is_close_to_one(self):
        score = recency_score(datetime.utcnow())
        assert score == pytest.approx(1.0, abs=0.01)

    def test_old_timestamp_decays(self):
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        score = recency_score(thirty_days_ago)
        # exp(-1) ≈ 0.368
        assert score == pytest.approx(math.exp(-1), abs=0.01)

    def test_very_old_timestamp_near_zero(self):
        one_year_ago = datetime.utcnow() - timedelta(days=365)
        score = recency_score(one_year_ago)
        assert score < 0.01

    def test_newer_beats_older(self):
        recent = recency_score(datetime.utcnow() - timedelta(hours=1))
        older = recency_score(datetime.utcnow() - timedelta(days=60))
        assert recent > older


class TestComputeScore:
    """Tests for the compute_score() ranking function."""

    def test_returns_float(self):
        result = {
            "_distance": 0.2,
            "importance": 0.8,
            "timestamp": datetime.utcnow(),
        }
        score = compute_score(result)
        assert isinstance(score, float)

    def test_perfect_result_near_one(self):
        """A result with zero distance, max importance, and just-now timestamp
        should score close to 1.0 (0.6 + 0.25 + 0.15 = 1.0)."""
        result = {
            "_distance": 0.0,
            "importance": 1.0,
            "timestamp": datetime.utcnow(),
        }
        score = compute_score(result)
        assert score == pytest.approx(1.0, abs=0.02)

    def test_worst_result_near_zero(self):
        """A distant, unimportant, ancient result should score near zero."""
        result = {
            "_distance": 1.0,
            "importance": 0.0,
            "timestamp": datetime.utcnow() - timedelta(days=365),
        }
        score = compute_score(result)
        assert score < 0.05

    def test_newer_higher_importance_outranks_older_lower_importance(self):
        """Core ranking intuition: a newer, more important memory should
        outrank an older, less important one when similarity is equal."""
        newer_important = {
            "_distance": 0.3,
            "importance": 0.9,
            "timestamp": datetime.utcnow() - timedelta(hours=2),
        }
        older_trivial = {
            "_distance": 0.3,
            "importance": 0.3,
            "timestamp": datetime.utcnow() - timedelta(days=90),
        }
        assert compute_score(newer_important) > compute_score(older_trivial)

    def test_importance_matters_at_equal_recency_and_similarity(self):
        """Higher importance wins when recency and similarity are the same."""
        now = datetime.utcnow()
        high = {"_distance": 0.2, "importance": 0.9, "timestamp": now}
        low = {"_distance": 0.2, "importance": 0.3, "timestamp": now}
        assert compute_score(high) > compute_score(low)

    def test_recency_matters_at_equal_importance_and_similarity(self):
        """A newer memory wins when importance and similarity are the same."""
        recent = {
            "_distance": 0.2,
            "importance": 0.7,
            "timestamp": datetime.utcnow() - timedelta(hours=1),
        }
        stale = {
            "_distance": 0.2,
            "importance": 0.7,
            "timestamp": datetime.utcnow() - timedelta(days=60),
        }
        assert compute_score(recent) > compute_score(stale)

    def test_similarity_dominates(self):
        """A much closer semantic match should still win even if it's older
        and less important, because similarity has the highest weight (0.6)."""
        close_match = {
            "_distance": 0.05,
            "importance": 0.4,
            "timestamp": datetime.utcnow() - timedelta(days=20),
        }
        far_match = {
            "_distance": 0.9,
            "importance": 1.0,
            "timestamp": datetime.utcnow(),
        }
        assert compute_score(close_match) > compute_score(far_match)

    def test_defaults_for_missing_distance_and_importance(self):
        """compute_score should handle missing _distance (defaults to 1.0 →
        similarity 0.0) and missing importance (defaults to 0.5)."""
        result = {"timestamp": datetime.utcnow()}
        score = compute_score(result)
        # similarity=0, importance=0.5 → 0*0.75 + 0.5*0.15 + ~1*0.10 = ~0.175
        assert 0.15 < score < 0.30

    def test_ranking_order_matches_intuition(self):
        """Sort a batch of results by compute_score and verify the order
        matches human intuition."""
        now = datetime.utcnow()
        results = [
            # Best: close match, high importance, very recent
            {"_distance": 0.05, "importance": 0.95, "timestamp": now},
            # Good: close match, medium importance, recent
            {"_distance": 0.1, "importance": 0.7, "timestamp": now - timedelta(days=3)},
            # Okay: moderate match, high importance, somewhat old
            {"_distance": 0.4, "importance": 0.9, "timestamp": now - timedelta(days=30)},
            # Poor: far match, low importance, old
            {"_distance": 0.8, "importance": 0.2, "timestamp": now - timedelta(days=120)},
        ]

        scores = [compute_score(r) for r in results]
        # Verify strictly decreasing order
        for i in range(len(scores) - 1):
            assert scores[i] > scores[i + 1], (
                f"Expected score[{i}]={scores[i]:.4f} > score[{i+1}]={scores[i+1]:.4f}"
            )
