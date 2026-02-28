"""
DevMemoryIndex MCP Server

Exposes six tools to Claude Code (and any MCP-compatible agent) via stdio transport:
  - search_memories      — hybrid search over all indexed developer memories
  - build_context        — formatted context block for a given task/query
  - remember_memory      — persist a solution or decision for future sessions
  - get_memory           — fetch a single memory by ID (resolve related[] links)
  - get_session_context  — call once at session start to bootstrap context from task + git state
  - remember_failure     — record a failed approach to avoid repeating it in future sessions

Transport: stdio (spawned on-demand by Claude Code, no persistent process needed)

Registration (project-local):
    claude mcp add devmemory -s local -- uv run python -m mcp_server.server

Config file: .mcp.json (project root) — used by Claude Code to auto-discover the server.

Verify in Claude Code: run /mcp — devmemory should appear as connected with 6 tools.

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

    Search with specific technical terms for best results.
    Always call get_session_context or build_context before starting complex implementation tasks.
    """,
)

mcp.tool()(search_memories)
mcp.tool()(build_context)
mcp.tool()(remember_memory)
mcp.tool()(get_memory)
mcp.tool()(get_session_context)
mcp.tool()(remember_failure)

if __name__ == "__main__":
    mcp.run(transport="stdio")
