"""
Query Planner — LLM-based routing for ask queries.

Before retrieval, the planner calls a small local LLM to determine:
  - The best memory type to search (file_content, git_diff, agent_solution, etc.)
  - A reformulated technical search query (concise, keyword-focused)

This prevents the common failure where "what connectors do we have" retrieves
stale git_commit summaries instead of current file_content source.

Falls back silently to (original_query, None) if the LLM is unavailable,
returns malformed output, or suggests an unknown type.
"""

from __future__ import annotations

import json
import re

_KNOWN_TYPES = {
    "file_content",
    "git_diff",
    "git_commit",
    "agent_solution",
    "failure_note",
    "terminal_command",
    "voice_note",
    "markdown",
}

_PROMPT_TEMPLATE = """\
You are a memory routing assistant for a developer memory index.
Given the question, respond with JSON only — no other text, no markdown fences.

Memory types:
- file_content    : current source code, registered items, data structures, config files
- git_diff        : what lines of code changed in a commit
- git_commit      : when a feature landed, commit history, release notes
- agent_solution  : past decisions, how something works, architectural choices
- failure_note    : approaches that failed, things to avoid, past mistakes
- terminal_command: shell commands, CLI usage, scripts run
- voice_note      : informal voice memos, spoken notes
- markdown        : documentation, READMEs, notes files

JSON schema:
{{
  "query": "<concise 2-6 word technical search query>",
  "type": "<one type from the list above, or null if any type is fine>",
  "reason": "<one short sentence>"
}}

Question: {query}\
"""


class QueryPlanner:
    """Plan the optimal type + query for an ask request."""

    def __init__(self, backend):
        self.backend = backend

    def plan(self, query: str, repo: str | None = None) -> dict:
        """Return {query, type, reason}. On any failure returns original query + null type."""
        prompt = _PROMPT_TEMPLATE.format(query=query)
        try:
            chunks = list(self.backend.generate(prompt, stream=False))
            raw = "".join(chunks).strip()
            result = _parse_json(raw)
            if result is None:
                return _fallback(query)

            planned_type = result.get("type")
            if planned_type not in _KNOWN_TYPES:
                planned_type = None

            planned_query = (result.get("query") or "").strip() or query
            reason = (result.get("reason") or "").strip()

            return {"query": planned_query, "type": planned_type, "reason": reason}
        except Exception:
            return _fallback(query)


def _fallback(query: str) -> dict:
    return {"query": query, "type": None, "reason": ""}


def _parse_json(text: str) -> dict | None:
    """Extract and parse the first JSON object from LLM output."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    # Find first {...}
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None
