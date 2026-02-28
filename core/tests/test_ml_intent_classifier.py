"""
Tests for core/ml_intent_classifier.py.

Covers:
- MLIntentClassifier class (load, train, classify)
- classify_intent_ml fallback behaviour
- Routing params are identical to INTENT_RULES
"""

import pytest
from pathlib import Path
from core.ml_intent_classifier import MLIntentClassifier, classify_intent_ml
from core.intent_classifier import INTENT_RULES

# Minimal labelled set — 5 per class (25 total), the minimum for 5-fold CV.
_MINIMAL_EXAMPLES = [
    ("error in the code", "debug"),
    ("why is it crashing", "debug"),
    ("fix the broken test", "debug"),
    ("exception from lancedb", "debug"),
    ("traceback from the search function", "debug"),
    ("when did I add this feature", "recall"),
    ("what was the solution last time", "recall"),
    ("remember the command I used", "recall"),
    ("what changed last week", "recall"),
    ("before the batch write was added", "recall"),
    ("how does the ranking work", "architecture"),
    ("design of the memory store", "architecture"),
    ("why did we choose lancedb", "architecture"),
    ("schema for memory records", "architecture"),
    ("pattern for the context engine", "architecture"),
    ("how to add a new connector", "implementation"),
    ("setup lancedb locally", "implementation"),
    ("how to deploy the API", "implementation"),
    ("configure the daemon schedule", "implementation"),
    ("how to install voice dependencies", "implementation"),
    ("show me recent memories", "general"),
    ("search for embed_batch", "general"),
    ("list all git memories", "general"),
    ("devmemory stats", "general"),
    ("find memories about ranking", "general"),
]


# ── MLIntentClassifier class ────────────────────────────────────────────────

class TestMLIntentClassifierClass:

    def test_load_returns_false_when_no_model(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.ml_intent_classifier._MODEL_PATH", tmp_path / "nonexistent.pkl")
        clf = MLIntentClassifier()
        assert clf.load() is False

    def test_classify_raises_before_training(self):
        clf = MLIntentClassifier()
        with pytest.raises(RuntimeError, match="not loaded"):
            clf.classify("some query")

    def test_train_returns_expected_shape(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.ml_intent_classifier._MODEL_PATH", tmp_path / "model.pkl")
        clf = MLIntentClassifier()
        texts = [e[0] for e in _MINIMAL_EXAMPLES]
        labels = [e[1] for e in _MINIMAL_EXAMPLES]

        # Write a minimal JSONL to disk
        import json
        labels_file = tmp_path / "labels.jsonl"
        labels_file.write_text(
            "\n".join(json.dumps({"query": t, "intent": l}) for t, l in zip(texts, labels))
        )

        result = clf.train(str(labels_file), eval_cv=False)

        assert result["n_train"] == len(_MINIMAL_EXAMPLES)
        assert set(result["classes"]) == {"debug", "recall", "architecture", "implementation", "general"}
        assert result["cv_accuracy"] is None  # eval_cv=False

    def test_train_saves_model_to_path(self, tmp_path, monkeypatch):
        model_path = tmp_path / "model.pkl"
        monkeypatch.setattr("core.ml_intent_classifier._MODEL_PATH", model_path)
        clf = MLIntentClassifier()

        import json
        labels_file = tmp_path / "labels.jsonl"
        labels_file.write_text(
            "\n".join(json.dumps({"query": t, "intent": l}) for t, l in _MINIMAL_EXAMPLES)
        )
        clf.train(str(labels_file), eval_cv=False)

        assert model_path.exists()

    def test_load_after_train(self, tmp_path, monkeypatch):
        model_path = tmp_path / "model.pkl"
        monkeypatch.setattr("core.ml_intent_classifier._MODEL_PATH", model_path)

        import json
        labels_file = tmp_path / "labels.jsonl"
        labels_file.write_text(
            "\n".join(json.dumps({"query": t, "intent": l}) for t, l in _MINIMAL_EXAMPLES)
        )

        trainer = MLIntentClassifier()
        trainer.train(str(labels_file), eval_cv=False)

        loader = MLIntentClassifier()
        assert loader.load() is True

    def test_classify_returns_label_and_confidence(self, tmp_path, monkeypatch):
        model_path = tmp_path / "model.pkl"
        monkeypatch.setattr("core.ml_intent_classifier._MODEL_PATH", model_path)

        import json
        labels_file = tmp_path / "labels.jsonl"
        labels_file.write_text(
            "\n".join(json.dumps({"query": t, "intent": l}) for t, l in _MINIMAL_EXAMPLES)
        )

        clf = MLIntentClassifier()
        clf.train(str(labels_file), eval_cv=False)

        label, confidence = clf.classify("error in memory store")
        assert isinstance(label, str)
        assert label in {"debug", "recall", "architecture", "implementation", "general"}
        assert 0.0 <= confidence <= 1.0

    def test_classify_obvious_debug(self, tmp_path, monkeypatch):
        model_path = tmp_path / "model.pkl"
        monkeypatch.setattr("core.ml_intent_classifier._MODEL_PATH", model_path)

        import json
        labels_file = tmp_path / "labels.jsonl"
        labels_file.write_text(
            "\n".join(json.dumps({"query": t, "intent": l}) for t, l in _MINIMAL_EXAMPLES)
        )

        clf = MLIntentClassifier()
        clf.train(str(labels_file), eval_cv=False)
        label, _ = clf.classify("fix the crashing exception")
        assert label == "debug"

    def test_cv_accuracy_reported_when_eval(self, tmp_path, monkeypatch):
        model_path = tmp_path / "model.pkl"
        monkeypatch.setattr("core.ml_intent_classifier._MODEL_PATH", model_path)

        import json
        labels_file = tmp_path / "labels.jsonl"
        labels_file.write_text(
            "\n".join(json.dumps({"query": t, "intent": l}) for t, l in _MINIMAL_EXAMPLES)
        )

        clf = MLIntentClassifier()
        result = clf.train(str(labels_file), eval_cv=True)
        assert result["cv_accuracy"] is not None
        assert 0.0 <= result["cv_accuracy"] <= 1.0


# ── classify_intent_ml fallback ─────────────────────────────────────────────

class TestClassifyIntentMlFallback:

    def _reset_singleton(self, monkeypatch):
        """Reset module-level singleton state between tests."""
        import core.ml_intent_classifier as mod
        fresh = MLIntentClassifier()
        monkeypatch.setattr(mod, "_classifier", fresh)
        monkeypatch.setattr(mod, "_loaded", False)

    def test_falls_back_to_rule_based_when_no_model(self, tmp_path, monkeypatch):
        import core.ml_intent_classifier as mod
        monkeypatch.setattr(mod, "_MODEL_PATH", tmp_path / "nonexistent.pkl")
        self._reset_singleton(monkeypatch)

        # Rule-based: "error" → debug
        label, routing = classify_intent_ml("error in the server")
        assert label == "debug"
        assert "agent_solution" in routing["type_boost"]

    def test_falls_back_when_confidence_below_threshold(self, tmp_path, monkeypatch):
        import core.ml_intent_classifier as mod
        model_path = tmp_path / "model.pkl"
        monkeypatch.setattr(mod, "_MODEL_PATH", model_path)
        self._reset_singleton(monkeypatch)

        import json
        labels_file = tmp_path / "labels.jsonl"
        labels_file.write_text(
            "\n".join(json.dumps({"query": t, "intent": l}) for t, l in _MINIMAL_EXAMPLES)
        )
        mod._classifier.train(str(labels_file), eval_cv=False)
        monkeypatch.setattr(mod, "_loaded", True)

        # Threshold of 1.0 is impossible to meet — must always fall back
        label, routing = classify_intent_ml("error in the server", confidence_threshold=1.0)
        # Rule-based kicks in: "error" → debug
        assert label == "debug"

    def test_uses_ml_when_confident(self, tmp_path, monkeypatch):
        import core.ml_intent_classifier as mod
        model_path = tmp_path / "model.pkl"
        monkeypatch.setattr(mod, "_MODEL_PATH", model_path)
        self._reset_singleton(monkeypatch)

        import json
        labels_file = tmp_path / "labels.jsonl"
        labels_file.write_text(
            "\n".join(json.dumps({"query": t, "intent": l}) for t, l in _MINIMAL_EXAMPLES)
        )
        mod._classifier.train(str(labels_file), eval_cv=False)
        monkeypatch.setattr(mod, "_loaded", True)

        # Very clear signal — expect ML to be confident enough at 0.0 threshold
        label, routing = classify_intent_ml("error in the code", confidence_threshold=0.0)
        assert label in INTENT_RULES or label == "general"

    def test_routing_params_from_intent_rules(self, tmp_path, monkeypatch):
        import core.ml_intent_classifier as mod
        model_path = tmp_path / "model.pkl"
        monkeypatch.setattr(mod, "_MODEL_PATH", model_path)
        self._reset_singleton(monkeypatch)

        import json
        labels_file = tmp_path / "labels.jsonl"
        labels_file.write_text(
            "\n".join(json.dumps({"query": t, "intent": l}) for t, l in _MINIMAL_EXAMPLES)
        )
        mod._classifier.train(str(labels_file), eval_cv=False)
        monkeypatch.setattr(mod, "_loaded", True)

        # Whatever the ML predicts, routing must come from INTENT_RULES
        label, routing = classify_intent_ml("error crash exception", confidence_threshold=0.0)
        if label in INTENT_RULES:
            assert routing == INTENT_RULES[label]
        else:
            assert routing == {}

    def test_general_intent_returns_empty_routing(self, tmp_path, monkeypatch):
        import core.ml_intent_classifier as mod
        monkeypatch.setattr(mod, "_MODEL_PATH", tmp_path / "nonexistent.pkl")
        self._reset_singleton(monkeypatch)

        # Falls back to rule-based; no keywords → general
        label, routing = classify_intent_ml("xkcd blorp zzz random gibberish")
        assert label == "general"
        assert routing == {}

    def test_return_type_is_tuple_of_str_and_dict(self, tmp_path, monkeypatch):
        import core.ml_intent_classifier as mod
        monkeypatch.setattr(mod, "_MODEL_PATH", tmp_path / "nonexistent.pkl")
        self._reset_singleton(monkeypatch)

        result = classify_intent_ml("some query")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], dict)
