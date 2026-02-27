"""
Intent Classifier — rule-based, no LLM required.

Classifies a query into an intent category and returns routing parameters
that adjust how ContextEngine scores and filters candidates.

Intents:
  debug          — error/bug/crash queries → boost agent_solution + terminal_command
  architecture   — design/pattern/decision queries → boost agent_solution + git_commit
  implementation — how-to/setup/deploy queries → boost git_commit + terminal_command
  recall         — "what was"/"when did" queries → boost voice_note, raise recency weight
  general        — fallback, no routing applied
"""

INTENT_RULES: dict[str, dict] = {
    "debug": {
        "keywords": [
            "error", "fix", "bug", "crash", "exception", "traceback",
            "fail", "broken", "not working", "why is", "undefined",
        ],
        "type_boost": ["agent_solution", "terminal_command"],
        "importance_weight": 0.20,
        "recency_weight": 0.20,
    },
    "recall": {
        # Checked before implementation — "when did I add" must route to recall, not impl
        "keywords": [
            "what was", "remember", "last time", "before", "when did",
            "when was", "voice", "said", "told",
        ],
        "type_boost": ["voice_note", "agent_solution"],
        "importance_weight": 0.10,
        "recency_weight": 0.25,  # recall is highly recency-sensitive
    },
    "architecture": {
        "keywords": [
            "design", "pattern", "structure", "architecture", "how does",
            "why did", "decision", "approach", "schema", "model",
        ],
        "type_boost": ["agent_solution", "git_commit"],
        "importance_weight": 0.20,
        "recency_weight": 0.05,  # older architectural decisions still relevant
    },
    "implementation": {
        "keywords": [
            "how to", "implement", "create", "build", "integrate",
            "setup", "configure", "install", "deploy",
        ],
        "type_boost": ["git_commit", "terminal_command"],
        "importance_weight": 0.15,
        "recency_weight": 0.10,
    },
}


def classify_intent(query: str) -> tuple[str, dict]:
    """Classify query into an intent. Returns (intent_label, routing_params).

    routing_params keys:
      type_boost        — list of memory types to sort to the front
      importance_weight — adjusted importance weight for scoring (replaces 0.15 default)
      recency_weight    — adjusted recency weight for scoring (replaces 0.10 default)

    Returns ("general", {}) if no intent matches — caller uses default scoring.
    """
    query_lower = query.lower()
    for intent, config in INTENT_RULES.items():
        if any(kw in query_lower for kw in config["keywords"]):
            return intent, config
    return "general", {}
