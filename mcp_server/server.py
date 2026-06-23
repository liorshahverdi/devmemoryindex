"""
DevMemoryIndex MCP Server

Exposes DevMemoryIndex tools to Claude Code, Hermes Agent, and any MCP-compatible
agent via stdio transport. The server currently registers 19 tools for:
  - memory search and AI-ready context building
  - session bootstrap from task + git state
  - memory creation, update, forgetting, reinforcement, and consolidation
  - score explainability and context exclusion diagnostics
  - store-health inspection and batch search
  - codebase maps plus typed memory graph / causality traversal

Transport: stdio (spawned on demand by the MCP client; no persistent MCP server
process is required).

Hermes Agent registration:
    hermes mcp add devmemory --command /path/to/devmemory-mcp-server

Claude Code registration (project-local, optional):
    claude mcp add devmemory -s local -- uv run python -m mcp_server.server

Generic MCP clients can use the same stdio command or wrapper script.

Config file: .mcp.json (project root) — useful for clients that auto-discover project MCP servers.
Verify in Hermes: run `hermes mcp test devmemory` — all registered tools should be discovered.
Verify in Claude Code: run /mcp — devmemory should appear as connected with 19 tools.

Note: directory is named mcp_server/ (not mcp/) to avoid shadowing the mcp PyPI package.
"""

from mcp.server.fastmcp import FastMCP
from mcp_server.tools import (
    search_memories,
    build_context,
    remember_memory,
    get_memory,
    get_session_context,
    remember_failure,
    update_memory,
    reinforce_memory,
    get_codebase_map,
    plan_task,
    # T1-A: Score Explainability
    explain_score,
    why_not_included,
    # T1-D: Forget with Audit Trail
    forget_memory,
    # T1-E: Store Health Dashboard
    get_store_health,
    # T1-C: Memory Consolidation
    consolidate_memories,
    # T1-F: Batch Search
    search_batch,
    # T2-A: Memory Entanglement
    link_memories,
    get_memory_graph,
    trace_causality,
)

mcp = FastMCP(
    "devmemory",
    instructions="""
    DevMemoryIndex: Persistent developer memory store for coding agents.

    Operational guide: mcp_server/AGENT_GUIDE.md documents the recommended
    autonomous-agent flow and memory hygiene rules.

    Recommended flow for complex repo work:
    1. Use get_session_context once at task start with task + repo + likely files.
       Do not call get_session_context repeatedly unless the task changes substantially.
    2. If context is insufficient, use search_memories with specific technical terms.
    3. Use get_memory for high-signal result IDs and related[] IDs before acting on them.
    4. Use build_context before broad implementation planning or multi-file changes.
    5. Use plan_task only for non-trivial implementation planning; it may call an LLM.
    6. After verified success, use remember_memory for durable root causes, commands,
       workflows, integration gotchas, and architecture decisions.
    7. After meaningful dead ends, use remember_failure with exact attempted commands
       and why they failed.
    8. Use reinforce_memory when a retrieved memory directly helped.
    9. Use update_memory or forget_memory when stored knowledge is wrong, outdated, or superseded.

    Memory hygiene:
    Avoid storing PR numbers, issue numbers, branch names, temporary TODO state,
    copied logs without explanation, secrets, tokens, credentials, or one-off progress.
    Prefer storing root causes, durable environment quirks, verified commands,
    project conventions, reusable debugging workflows, and architecture decisions.

    Score transparency:
    Use explain_score(memory_id, query) to understand WHY a memory ranked where it did.
    Use why_not_included(memory_id, query) to diagnose why a memory was excluded from context.
    search_memories() now returns score_breakdown on every result — check it!

    Memory lifecycle:
    Use forget_memory(id, reason) to deprecate bad knowledge (preserves for audit, excluded from search).
    Use consolidate_memories([id1, id2, ...]) to merge redundant memories into one canonical entry.
    Use get_store_health() to see store quality metrics: type breakdown, stale count, low-CTR memories.

    Memory graph (causal reasoning):
    Use link_memories(from_id, to_id, edge_type) to create typed edges between memories.
    Use get_memory_graph(memory_id, depth=2) to see all related memories up to N hops.
    Use trace_causality(memory_id) to follow the causal chain to a root cause.

    Batch search:
    Use search_batch(queries=[...]) to run multiple searches at once and get deduplicated results.

    Search with specific technical terms for best results.
    Always call get_session_context or build_context before starting complex implementation tasks.
    Check times_accessed in search_memories results: high access count = proven solution.
    """,
)

mcp.tool()(search_memories)
mcp.tool()(build_context)
mcp.tool()(remember_memory)
mcp.tool()(get_memory)
mcp.tool()(get_session_context)
mcp.tool()(remember_failure)
mcp.tool()(update_memory)
mcp.tool()(reinforce_memory)
mcp.tool()(get_codebase_map)
mcp.tool()(plan_task)
# T1-A
mcp.tool()(explain_score)
mcp.tool()(why_not_included)
# T1-D
mcp.tool()(forget_memory)
# T1-E
mcp.tool()(get_store_health)
# T1-C
mcp.tool()(consolidate_memories)
# T1-F
mcp.tool()(search_batch)
# T2-A
mcp.tool()(link_memories)
mcp.tool()(get_memory_graph)
mcp.tool()(trace_causality)

def main() -> None:
    """Run the DevMemoryIndex MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
