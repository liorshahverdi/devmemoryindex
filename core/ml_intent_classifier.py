"""
ML Intent Classifier — SGDClassifier + TF-IDF, confidence-gated.

Drop-in upgrade for core/intent_classifier.py. Falls back to the
rule-based classifier when the model is not trained or confidence
is below threshold.

Usage:
    from core.ml_intent_classifier import classify_intent_ml
    intent, params = classify_intent_ml(query)

Train:
    from core.ml_intent_classifier import MLIntentClassifier
    clf = MLIntentClassifier()
    n = clf.train("data/intent_labels.jsonl")
    print(f"Trained on {n} examples.")
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path

# Model persisted alongside other devmemory config.
_MODEL_PATH = Path.home() / ".config" / "devmemory" / "intent_model.pkl"

# Routing params are owned by the rule-based module — reuse them directly
# so ML and rule-based outputs are always interchangeable.
from core.intent_classifier import INTENT_RULES, classify_intent as _rule_classify


class MLIntentClassifier:
    """SGDClassifier on TF-IDF bigrams, trained on intent_labels.jsonl."""

    def __init__(self):
        self._pipeline = None  # sklearn Pipeline, loaded lazily

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> bool:
        """Load persisted model from disk. Returns True if successful."""
        if not _MODEL_PATH.exists():
            return False
        try:
            with open(_MODEL_PATH, "rb") as f:
                self._pipeline = pickle.load(f)
            return True
        except Exception:
            self._pipeline = None
            return False

    def train(self, labels_path: str, eval_cv: bool = True) -> dict:
        """Train on a JSONL file of {query, intent} examples.

        Returns:
            {
                "n_train": int,
                "classes": list[str],
                "cv_accuracy": float | None,  # None if eval_cv=False or n < 20
            }
        """
        from sklearn.pipeline import Pipeline
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import SGDClassifier

        examples = _load_jsonl(labels_path)
        if not examples:
            raise ValueError(f"No examples loaded from {labels_path}")

        texts = [e["query"] for e in examples]
        labels = [e["intent"] for e in examples]

        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=8000,
                sublinear_tf=True,
            )),
            ("clf", SGDClassifier(
                loss="log_loss",       # gives predict_proba
                max_iter=1000,
                tol=1e-3,
                random_state=42,
                class_weight="balanced",
            )),
        ])

        cv_accuracy = None
        if eval_cv and len(texts) >= 20:
            from sklearn.model_selection import cross_val_score
            scores = cross_val_score(pipeline, texts, labels, cv=5, scoring="accuracy")
            cv_accuracy = float(scores.mean())

        pipeline.fit(texts, labels)
        self._pipeline = pipeline

        _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump(pipeline, f)

        return {
            "n_train": len(texts),
            "classes": list(pipeline.classes_),
            "cv_accuracy": cv_accuracy,
        }

    def classify(self, query: str) -> tuple[str, float]:
        """Classify a query. Returns (intent_label, confidence).

        Raises RuntimeError if model is not loaded.
        """
        if self._pipeline is None:
            raise RuntimeError("Model not loaded — call load() or train() first.")
        proba = self._pipeline.predict_proba([query])[0]
        idx = int(proba.argmax())
        label = self._pipeline.classes_[idx]
        confidence = float(proba[idx])
        return label, confidence


# Module-level singleton — loaded once on first use.
_classifier = MLIntentClassifier()
_loaded = False


def _ensure_loaded() -> bool:
    global _loaded
    if not _loaded:
        _loaded = _classifier.load()
    return _loaded


def classify_intent_ml(
    query: str,
    confidence_threshold: float = 0.6,
) -> tuple[str, dict]:
    """Classify intent with ML, falling back to rule-based if needed.

    Falls back to rule-based when:
    - Model not found (not trained yet)
    - Predicted confidence < confidence_threshold

    Returns (intent_label, routing_params) — identical signature to
    core.intent_classifier.classify_intent.
    """
    if not _ensure_loaded():
        return _rule_classify(query)

    try:
        label, confidence = _classifier.classify(query)
    except Exception:
        return _rule_classify(query)

    if confidence < confidence_threshold:
        return _rule_classify(query)

    routing = INTENT_RULES.get(label, {})
    return label, routing


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _load_jsonl(path: str) -> list[dict]:
    examples = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if "query" in obj and "intent" in obj:
                    examples.append(obj)
            except json.JSONDecodeError:
                continue
    return examples
