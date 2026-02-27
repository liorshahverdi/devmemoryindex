"""
DevMemoryIndex MCP Server

Exposes four tools to Claude Code (and any MCP-compatible agent) via stdio transport:
  - search_memories  — hybrid search over all indexed developer memories
  - build_context    — formatted context block for a given task/query
  - remember_memory  — persist a solution or decision for future sessions
  - get_memory       — fetch a single memory by ID (resolve related[] links)

Transport: stdio (spawned on-demand by Claude Code, no persistent process needed)

Registration (project-local):
    claude mcp add devmemory -s local -- uv run python -m mcp_server.server

Config file: .mcp.json (project root) — used by Claude Code to auto-discover the server.

Verify in Claude Code: run /mcp — devmemory should appear as connected with 4 tools.

Note: directory is named mcp_server/ (not mcp/) to avoid shadowing the mcp PyPI package.
"""

from mcp.server.fastmcp import FastMCP
from mcp_server.tools import search_memories, build_context, remember_memory, get_memory

mcp = FastMCP(
    "devmemory",
    instructions="""
    DevMemoryIndex: Persistent developer memory store.

    Use search_memories to find relevant past solutions, decisions, and commands.
    Use build_context to get a formatted context block before starting complex tasks.
    Use remember_memory after solving a hard problem to persist the solution.
    Use get_memory to resolve related memory IDs returned in search results.

    Search with specific technical terms for best results.
    Always call build_context before starting complex implementation tasks.
    """,
)

mcp.tool()(search_memories)
mcp.tool()(build_context)
mcp.tool()(remember_memory)
mcp.tool()(get_memory)

if __name__ == "__main__":
    mcp.run(transport="stdio")
