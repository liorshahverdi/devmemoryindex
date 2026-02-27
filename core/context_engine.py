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
    ) -> dict:
        if vector is None:
            vector = embed(query)

        # 1. Hybrid search for candidates
        candidates = self.store.hybrid_search(query, vector, k=max_memories * 3)

        # 2. Optional repo filter
        if repo:
            candidates = [c for c in candidates if c.get("repo") == repo]

        # 3. Deduplicate near-identical summaries
        candidates = self._deduplicate(candidates)

        # 4. Pack within token budget (uses core.token_budget)
        selected, token_count = pack_within_budget(
            candidates, max_tokens=max_tokens, max_items=max_memories
        )

        # 5. Format output
        context_text = self._format(selected, format)

        return {
            "query": query,
            "memories": selected,
            "context_text": context_text,
            "token_estimate": token_count,
            "memory_count": len(selected),
        }

    def _deduplicate(self, memories: list, threshold: float = 0.9) -> list:
        seen = set()
        unique = []
        for m in memories:
            key = m["summary"][:100].lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(m)
        return unique

    def _format(self, memories: list, fmt: str) -> str:
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
