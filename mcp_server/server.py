"""
DevMemoryIndex MCP Server

Exposes ten tools to Claude Code (and any MCP-compatible agent) via stdio transport:
  - search_memories      — hybrid search over all indexed developer memories
  - build_context        — formatted context block for a given task/query
  - remember_memory      — persist a solution or decision for future sessions
  - get_memory           — fetch a single memory by ID (resolve related[] links)
  - get_session_context  — call once at session start to bootstrap context from task + git state
  - remember_failure     — record a failed approach to avoid repeating it in future sessions
  - update_memory        — correct or improve an existing memory in-place
  - reinforce_memory     — explicitly boost importance after successfully applying a solution
  - get_codebase_map     — cluster file_content memories to reveal subsystem structure
  - plan_task            — generate a grounded implementation plan from memory + git context

Transport: stdio (spawned on-demand by Claude Code, no persistent process needed)

Registration (project-local):
    claude mcp add devmemory -s local -- uv run python -m mcp_server.server

Config file: .mcp.json (project root) — used by Claude Code to auto-discover the server.

Verify in Claude Code: run /mcp — devmemory should appear as connected with 10 tools.

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
    DevMemoryIndex: Persistent developer memory store.

    Use get_session_context FIRST at the start of any coding session — it combines your
    task description with current git state to surface the most relevant past context.
    Use search_memories to find relevant past solutions, decisions, and commands.
    Use build_context to get a formatted context block before starting complex tasks.
    Use remember_memory after solving a hard problem to persist the solution.
    Use remember_failure after hitting a dead end — records what failed and why so
    future sessions don't repeat the same mistake.
    Use get_memory to resolve related memory IDs returned in search results.
    Use update_memory to correct a wrong or outdated stored solution.
    Use reinforce_memory after successfully applying a solution — boosts its importance.
    Use get_codebase_map to get a structural overview of an unfamiliar or refactored repo.
    Use plan_task to generate a grounded implementation plan before writing code.

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

if __name__ == "__main__":
    mcp.run(transport="stdio")
