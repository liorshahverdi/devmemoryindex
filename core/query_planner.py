"""
Query Planner — hybrid routing for ask queries.

Two-stage pipeline:
  1. Deterministic regex pre-routing for clear-cut patterns (fast, no LLM call).
  2. LLM routing for ambiguous queries (reformulates query + picks type).

This prevents the common failure where "what connectors do we have" retrieves
stale git_commit summaries instead of current file_content source.

Falls back silently to (original_query, None) if the LLM is unavailable,
returns malformed output, or suggests an unknown type.
"""

from __future__ import annotations

import json
import re

# --- Regex pre-routing patterns -------------------------------------------
# Ordered by specificity. First match wins and skips the LLM call entirely.

_TEMPORAL_RE = re.compile(
    r"\b(when (did|was|were)|added when|introduced when)\b", re.I
)
_DECISION_RE = re.compile(
    r"\b(why did (we|you)|why (do|did|was|were) we (use|choose|pick|go with|switch)|"
    r"what was the (reason|rationale|decision))\b", re.I
)
_COMMAND_RE = re.compile(
    r"\b(what command|how (do|did|can) (i|we) run|how to (run|invoke|start|install)|"
    r"what (flag|option|argument|param))\b", re.I
)
_AVOID_RE = re.compile(
    r"\b(what (to avoid|not to do|went wrong|failed)|"
    r"why (did|does) (it|this) (fail|break|not work)|"
    r"what (mistake|problem|bug|error))\b", re.I
)
# "how does X work" / "what does X do" / "show me X" where X looks like code
# Matches if there's a CamelCase word OR an explicit code-smell phrase
_CODE_IMPL_RE = re.compile(
    r"\b(how (does|do|is|are)|what does|show me (the )?|"
    r"walk me through|explain (the |how )?|what is in)\b.{0,60}"
    r"([A-Z][a-z]+[A-Z]\w*|[a-z]+_[a-z_]+\.(py|ts|go|js|rs)|\bcode\b|\bimplementation\b|\bsource\b)",
    re.I,
)


def _quick_route(query: str) -> dict | None:
    """Return a routing dict for clear-cut query patterns, or None to fall through to LLM."""
    if _TEMPORAL_RE.search(query):
        return {"query": query, "type": "git_commit", "reason": "temporal question — when something was added"}
    if _DECISION_RE.search(query):
        return {"query": query, "type": "agent_solution", "reason": "decision/rationale question"}
    if _COMMAND_RE.search(query):
        return {"query": query, "type": "terminal_command", "reason": "command or invocation question"}
    if _AVOID_RE.search(query):
        return {"query": query, "type": "failure_note", "reason": "failure or avoidance question"}
    if _CODE_IMPL_RE.search(query):
        # Prefer an explicit CamelCase identifier in the query (typed input).
        # For voice input ("how does context engine work"), Whisper produces lowercase,
        # so synthesize CamelCase + snake_case from the extracted subject words to
        # give definition files a clear keyword advantage over files that just import them.
        camel = re.search(r"\b([A-Z][a-z]+[A-Z]\w*)\b", query)
        if camel:
            refined = camel.group(1)
        else:
            subject = re.sub(
                r"^\s*(how does|how do|what does|show me( the)?|explain( the| how)?|"
                r"walk me through|what is in)\s*", "", query, flags=re.I
            )
            subject = re.sub(r"\s*(work|do|works?)\s*\??\s*$", "", subject, flags=re.I).strip()
            subject = subject or query
            words = subject.split()
            if len(words) > 1:
                # "context engine" → "ContextEngine context_engine"
                camel_form = "".join(w.capitalize() for w in words)
                snake_form = "_".join(w.lower() for w in words)
                refined = f"{camel_form} {snake_form}"
            else:
                refined = subject
        return {"query": refined, "type": "file_content", "reason": "implementation question about named code entity"}
    return None

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
- file_content    : how a named class/function/module works, current source code, implementations ("how does ContextEngine work", "what does embed() do")
- git_diff        : what lines changed in a commit
- git_commit      : when a feature was added/removed/changed, commit history ("when did we add X")
- agent_solution  : why a decision was made, architectural tradeoffs ("why did we choose X over Y")
- failure_note    : approaches that failed, things to avoid
- terminal_command: shell commands, how to invoke or run something
- voice_note      : spoken voice memos
- markdown        : documentation, README files

JSON schema:
{{
  "query": "<concise 2-6 word technical search query; use the exact class or function name if one is mentioned>",
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
        # Stage 1: fast deterministic routing for clear patterns.
        quick = _quick_route(query)
        if quick:
            return quick

        # Stage 2: LLM routing for ambiguous queries.
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
