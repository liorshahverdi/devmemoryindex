"""Regression tests for agent-optimized MCP tool descriptions.

The MCP server exposes function docstrings as tool descriptions. These tests keep
those descriptions useful for autonomous coding agents, not just humans.
"""

import inspect

from mcp_server import tools


AGENT_GUIDANCE_PHRASES = (
    "Use this",
    "Call this",
    "Do not",
    "Prefer",
    "Avoid",
    "Use ",
)


PUBLIC_TOOL_NAMES = [
    "search_memories",
    "build_context",
    "remember_memory",
    "get_memory",
    "get_session_context",
    "remember_failure",
    "update_memory",
    "reinforce_memory",
    "get_codebase_map",
    "plan_task",
    "explain_score",
    "why_not_included",
    "forget_memory",
    "get_store_health",
    "consolidate_memories",
    "search_batch",
    "link_memories",
    "get_memory_graph",
    "trace_causality",
]


def _doc(name: str) -> str:
    return inspect.getdoc(getattr(tools, name)) or ""


def test_all_public_mcp_tools_have_agent_action_guidance():
    missing = []
    for name in PUBLIC_TOOL_NAMES:
        doc = _doc(name)
        if not any(phrase in doc for phrase in AGENT_GUIDANCE_PHRASES):
            missing.append(name)

    assert missing == []


def test_session_context_description_encodes_startup_policy():
    doc = _doc("get_session_context")

    assert "Call once" in doc
    assert "start" in doc.lower()
    assert "Do not call repeatedly" in doc
    assert "If returned context is insufficient" in doc


def test_search_memories_description_encodes_query_and_followup_policy():
    doc = _doc("search_memories")

    assert "Use before debugging" in doc
    assert "Prefer specific technical terms" in doc
    assert "Use returned IDs with get_memory" in doc
    assert "Do not use broad queries" in doc


def test_remember_memory_description_encodes_memory_hygiene():
    doc = _doc("remember_memory")

    assert "Use only after" in doc
    assert "verified" in doc.lower()
    assert "Do not store transient task progress" in doc
    assert "Do not store secrets" in doc


def test_remember_failure_description_encodes_failed_attempt_shape():
    doc = _doc("remember_failure")

    assert "Use after a dead end" in doc
    assert "exact command" in doc
    assert "why it failed" in doc.lower()


def test_mcp_server_instructions_reference_agent_guide_and_memory_hygiene():
    from pathlib import Path

    server_source = (Path(__file__).resolve().parents[1] / "server.py").read_text()

    assert "mcp_server/AGENT_GUIDE.md" in server_source
    assert "Avoid storing PR numbers" in server_source
    assert "Do not call get_session_context repeatedly" in server_source
