import pytest
from core.intent_classifier import classify_intent


class TestIntentClassifier:

    # ── debug ────────────────────────────────────────────────────────────

    def test_debug_error_keyword(self):
        label, routing = classify_intent("error in the ranking function")
        assert label == "debug"
        assert "agent_solution" in routing["type_boost"]

    def test_debug_broken_keyword(self):
        label, _ = classify_intent("why is the auth broken")
        assert label == "debug"

    def test_debug_fix_keyword(self):
        label, _ = classify_intent("how do I fix this crash")
        assert label == "debug"

    def test_debug_returns_routing_weights(self):
        _, routing = classify_intent("traceback in search")
        assert "importance_weight" in routing
        assert "recency_weight" in routing

    # ── recall ───────────────────────────────────────────────────────────

    def test_recall_when_did(self):
        label, routing = classify_intent("when did I add voice search")
        assert label == "recall"
        assert routing.get("sort_by_time") is True

    def test_recall_what_was(self):
        # avoid "fix" (debug keyword) — use a query with no ambiguous keywords
        label, _ = classify_intent("what was the lancedb timestamp issue")
        assert label == "recall"

    def test_recall_last_time(self):
        label, _ = classify_intent("last time I deployed this")
        assert label == "recall"

    def test_recall_not_confused_with_implementation(self):
        # "when did I add" — "add" was previously in implementation keywords
        label, _ = classify_intent("when did I add the markdown connector")
        assert label == "recall"

    # ── architecture ────────────────────────────────────────────────────

    def test_architecture_schema(self):
        label, _ = classify_intent("lancedb schema")
        assert label == "architecture"

    def test_architecture_how_does(self):
        label, _ = classify_intent("how does the context engine work")
        assert label == "architecture"

    def test_architecture_why_did(self):
        label, _ = classify_intent("why did we choose lancedb")
        assert label == "architecture"

    def test_architecture_low_recency_weight(self):
        # older architectural decisions are still relevant
        _, routing = classify_intent("design pattern for connectors")
        assert routing["recency_weight"] <= 0.10

    # ── implementation ───────────────────────────────────────────────────

    def test_implementation_how_to(self):
        label, _ = classify_intent("how to configure the daemon")
        assert label == "implementation"

    def test_implementation_deploy(self):
        label, _ = classify_intent("deploy to production steps")
        assert label == "implementation"

    def test_implementation_setup(self):
        label, _ = classify_intent("setup lancedb locally")
        assert label == "implementation"

    # ── general (fallback) ───────────────────────────────────────────────

    def test_general_no_keywords(self):
        label, routing = classify_intent("lancedb")
        assert label == "general"
        assert routing == {}

    def test_general_empty_query(self):
        label, routing = classify_intent("")
        assert label == "general"
        assert routing == {}

    def test_general_returns_empty_routing(self):
        _, routing = classify_intent("python list comprehension")
        assert routing == {}

    # ── case insensitivity ───────────────────────────────────────────────

    def test_case_insensitive(self):
        label1, _ = classify_intent("ERROR in auth")
        label2, _ = classify_intent("error in auth")
        assert label1 == label2 == "debug"
