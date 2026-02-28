"""
RAG Engine — retrieval-augmented generation over the memory store.

RAGEngine.ask(query) → context retrieval → prompt → LLM → cited answer.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from core.memory_store import MemoryStore
from core.context_engine import ContextEngine

_SYSTEM_PROMPT = """\
You are a developer memory assistant. Answer the question using ONLY the \
memories provided below. Cite memory labels (e.g. [MEMORY-1]) when \
referencing them. If the memories don't contain enough information, say so \
clearly rather than guessing. Be concise and precise."""


class RAGEngine:

    def __init__(self, store: MemoryStore, backend):
        self.store = store
        self.backend = backend
        self._ctx = ContextEngine(store)

    def plan_query(self, query: str, repo: str | None = None) -> dict:
        """Run the query planner and return {query, type, reason}.

        Called by ask() when type_filter is None. Can also be called
        directly from the CLI to show the routing decision before asking.
        """
        from core.query_planner import QueryPlanner
        return QueryPlanner(self.backend).plan(query, repo=repo)

    def ask(
        self,
        query: str,
        repo: str | None = None,
        type_filter: str | None = None,
        max_context_tokens: int = 1500,
        stream: bool = True,
        plan: bool = True,
    ):
        """Retrieve memories and query the LLM.

        stream=True  → generator that yields text chunks
        stream=False → returns (full_answer: str, memories: list, plan: dict)

        When plan=True and type_filter is None, runs QueryPlanner first to
        determine the best type + reformulated query automatically.
        """
        planned: dict = {}
        if plan and type_filter is None:
            planned = self.plan_query(query, repo=repo)
            if planned.get("query"):
                query = planned["query"]
            if planned.get("type"):
                type_filter = planned["type"]

        ctx = self._ctx.build(
            query=query,
            repo=repo,
            type_filter=type_filter,
            max_tokens=max_context_tokens,
            format="raw",
        )
        memories = ctx["memories"]
        prompt = self._build_prompt(query, memories)

        if stream:
            return self.backend.generate(prompt, stream=True), planned

        chunks = list(self.backend.generate(prompt, stream=False))
        return "".join(chunks), memories, planned

    def _build_prompt(self, query: str, memories: list) -> str:
        return (
            f"{_SYSTEM_PROMPT}\n\n"
            f"MEMORIES:\n{self._format_memories(memories)}\n\n"
            f"QUESTION: {query}\n\n"
            f"ANSWER:"
        )

    def _format_memories(self, memories: list) -> str:
        if not memories:
            return "(no relevant memories found)"
        lines = []
        for i, m in enumerate(memories, 1):
            summary = m.get("summary", "")
            raw = (m.get("raw_text") or "")[:2000]
            body = raw if raw else summary
            ts = m.get("timestamp")
            ts_str = f"\nDate: {str(ts)[:10]}" if ts else ""
            lines.append(f"[MEMORY-{i}] {summary}{ts_str}\n{body}")
        return "\n\n---\n\n".join(lines)

    def save_answer(
        self,
        query: str,
        answer: str,
        repo: str | None = None,
    ) -> str | None:
        """Persist the LLM answer as an agent_solution memory. Returns memory ID or None."""
        from core.embeddings import embed
        from core.schema import Memory

        raw_text = f"Q: {query}\n\nA: {answer}"
        mem_id = hashlib.sha256(raw_text.encode()).hexdigest()
        vector = embed(f"{query} {answer[:200]}")

        memory = Memory(
            id=mem_id,
            type="agent_solution",
            summary=query[:100],
            raw_text=raw_text,
            source="devmemory ask",
            repo=repo or "",
            timestamp=datetime.now(),
            tags=["rag", "ask"],
            importance=0.75,
        )
        return mem_id if self.store.add(memory, vector) else None
