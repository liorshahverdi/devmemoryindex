"""
Context Engine

Responsible for:
- Turning search results into AI-friendly context
- Hybrid ranking (importance + recency)
- Token budget packing
- Formatting memories for LLM consumption

DOES NOT:
- Perform embeddings
- Query LanceDB directly.
- Estimate tokens (delegated)
"""

from core.memory_store import MemoryStore
from core.embeddings import embed
from core.token_budget import pack_within_budget
from core.intent_classifier import classify_intent
from core.ranking import recency_score
from core.context_cache import cache as _cache


class ContextEngine:

    def __init__(self, store: MemoryStore):
        self.store = store

    def build(
        self,
        query: str,
        vector: list | None = None,
        repo: str | None = None,
        max_tokens: int = 4000,
        max_memories: int = 10,
        format: str = "raw",  # "raw" | "claude" | "markdown"
        intent: str | None = None,  # override auto-classification if provided
    ) -> dict:
        # Check cache before doing any embedding or search work
        cached = _cache.get(query, repo, format, intent)
        if cached is not None:
            return {**cached, "cached": True}

        if vector is None:
            vector = embed(query)

        # 1. Hybrid search for candidates
        candidates = self.store.hybrid_search(query, vector, k=max_memories * 3)

        # 2. Optional repo filter
        if repo:
            candidates = [c for c in candidates if c.get("repo") == repo]

        # 3. Classify intent and re-rank with adjusted weights + type boosting
        detected_intent, routing = (
            (intent, {}) if intent else classify_intent(query)
        )
        if routing:
            if routing.get("sort_by_time"):
                candidates = sorted(
                    candidates,
                    key=lambda m: m.get("timestamp") or 0,
                    reverse=True,
                )
            else:
                candidates = self._apply_intent_routing(candidates, routing)

        # 4. Deduplicate near-identical summaries
        candidates = self._deduplicate(candidates)

        # 5. Pack within token budget (uses core.token_budget)
        selected, token_count = pack_within_budget(
            candidates, max_tokens=max_tokens, max_items=max_memories
        )

        # 5. Format output
        context_text = self._format(selected, format, intent=detected_intent)

        result = {
            "query": query,
            "intent": detected_intent,
            "memories": selected,
            "context_text": context_text,
            "token_estimate": token_count,
            "memory_count": len(selected),
            "cached": False,
        }
        _cache.set(query, repo, format, intent, result)
        return result

    def _apply_intent_routing(self, memories: list, routing: dict) -> list:
        """Re-score candidates with intent-adjusted weights and sort boosted types first."""
        type_boost = routing.get("type_boost", [])
        imp_w = routing.get("importance_weight", 0.15)
        rec_w = routing.get("recency_weight", 0.10)
        sem_w = 1.0 - imp_w - rec_w

        def intent_score(m: dict) -> tuple:
            semantic = 1 - m.get("_distance", 1.0)
            importance = m.get("importance", 0.5)
            recency = recency_score(m["timestamp"])
            score = semantic * sem_w + importance * imp_w + recency * rec_w
            boosted = 1 if m.get("type") in type_boost else 0
            return (boosted, score)

        return sorted(memories, key=intent_score, reverse=True)

    def _deduplicate(self, memories: list, threshold: float = 0.9) -> list:
        seen = set()
        unique = []
        for m in memories:
            key = m["summary"][:100].lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(m)
        return unique

    def _format(self, memories: list, fmt: str, intent: str = "general") -> str:
        if intent == "recall":
            return self._format_recall(memories, fmt)

        if fmt == "claude":
            header = "<context>\n"
            body = "\n".join(
                f"- [{m.get('type', 'memory')}] {m['summary']} "
                f"(repo: {m.get('repo', 'N/A')}, importance: {m.get('importance', 0.5):.1f})"
                for m in memories
            )
            return header + body + "\n</context>"

        if fmt == "markdown":
            lines = ["### Relevant Past Solutions\n"]
            for m in memories:
                lines.append(
                    f"- **[{m.get('type', '')}]** {m['summary']}  \n"
                    f"  Repo: {m.get('repo', 'N/A')} | "
                    f"Importance: {m.get('importance', 0.5):.1f}"
                )
            return "\n".join(lines)

        # raw
        return "\n\n".join(m["summary"] for m in memories)

    def _format_recall(self, memories: list, fmt: str) -> str:
        """Time-ordered format for recall queries — always shows the date."""
        def _date(m: dict) -> str:
            ts = m.get("timestamp")
            if ts is None:
                return "unknown date"
            try:
                if hasattr(ts, "strftime"):
                    return ts.strftime("%Y-%m-%d")
                from datetime import datetime
                return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")
            except Exception:
                return str(ts)[:10]

        if fmt == "claude":
            lines = ["<context>\n"]
            for m in memories:
                lines.append(
                    f"- [{_date(m)}] [{m.get('type', 'memory')}] {m['summary']} "
                    f"(repo: {m.get('repo', 'N/A')})"
                )
            return "\n".join(lines) + "\n</context>"

        if fmt == "markdown":
            lines = ["### Timeline\n"]
            for m in memories:
                lines.append(
                    f"- **{_date(m)}** — {m['summary']}  \n"
                    f"  Repo: {m.get('repo', 'N/A')}"
                )
            return "\n".join(lines)

        # raw
        return "\n\n".join(f"[{_date(m)}] {m['summary']}" for m in memories)
