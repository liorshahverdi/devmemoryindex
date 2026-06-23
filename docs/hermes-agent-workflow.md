# Hermes Agent workflow for DevMemoryIndex

This workflow documents how Hermes should use DevMemoryIndex as a shared, repo-scoped memory layer through MCP. It is optimized for Hermes plus OpenAI/Pi-style coding agents, while Claude Code remains an optional compatible MCP client.

## Install and register with Hermes

Install DevMemoryIndex with the MCP extra so the `devmemory-mcp-server` console script is available:

```bash
uv pip install -e '.[mcp]'
```

Register the stdio MCP server in Hermes:

```bash
hermes mcp add devmemory --command devmemory-mcp-server
hermes mcp test devmemory
```

If you run from a checkout without console scripts, create a wrapper that changes to the repository root and runs:

```bash
python -m mcp_server.server
```

After registration, start a new Hermes session or restart the Hermes gateway so tool discovery refreshes.

## At the start of complex repo work

Use this order for complex implementation, debugging, refactoring, packaging, or daemon/MCP work:

1. Call `get_session_context` once with the task description, repo name, and likely files.
2. Read the returned context and decide whether it is enough to proceed.
3. If context is thin or misses a subsystem, call `search_memories` with specific technical terms.
4. For useful search hits, call `get_memory` on the result `id` and promising `related[]` IDs.
5. For broad multi-file work, call `build_context` to pack relevant memories into an AI-ready context block.
6. For codebase architecture/entity questions in repos with Graphify imports, call `search_code_graph`; then use `get_code_entity_context` to hydrate a selected Graphify node and its EdgeStore neighbors.
7. Use `plan_task` only when a grounded implementation plan is worth the extra LLM call.
8. Work normally with tests and verification.
9. After verified success, call `remember_memory` only for durable lessons, root causes, reusable commands, conventions, or architecture decisions.
10. If a dead end consumed meaningful time, call `remember_failure` with the exact attempted command/approach and why it failed.
11. If a retrieved memory directly helped, call `reinforce_memory`.
12. If a memory is wrong or stale, call `update_memory` or `forget_memory`.

## Graphify code graph workflow

When Graphify output has been imported with:

```bash
devmemory graphify ingest /path/to/repo --with-edges
```

Hermes can use DevMemoryIndex as a code graph context layer:

1. Use `search_code_graph("auth architecture", repo="my-repo")` for architecture, subsystem, symbol, or entity questions.
2. Use `get_code_entity_context("AuthService", repo="my-repo", depth=1)` to resolve a Graphify node and hydrate neighboring code graph memories through imported EdgeStore links.
3. Use `build_context(..., intent="architecture")` for broader context packing; architecture routing boosts `graphify_node` and `graphify_report` memories ahead of generic memories.

## Recommended Hermes prompt

```text
Before modifying this repo, use DevMemoryIndex to retrieve relevant context for: <task>. Call get_session_context once with the repo and likely files. If that context is insufficient, search specific technical terms and resolve promising IDs with get_memory. Do not write new memories until the result is verified.
```

## Memory hygiene for Hermes

Do store:

- root causes of non-obvious bugs
- durable environment quirks
- verified commands that future agents can reuse
- project conventions
- reusable debugging workflows
- architecture decisions and their rationale
- integration gotchas involving Hermes, MCP, local LLMs, LanceDB, packaging, or daemon service managers

Do not store:

- PR numbers, issue numbers, or branch names that will go stale
- temporary TODO state or task progress
- copied logs without explanation
- secrets, tokens, credentials, or API keys
- huge raw outputs that are better referenced by file path
- trivial successes or first-attempt typos

## Relationship to Hermes native memory

Hermes native memory remains the source for user preferences and stable personal/environment facts. DevMemoryIndex should hold project/repo memory: fixes, decisions, commands, architecture, and codebase-specific lessons. Avoid recursively indexing Hermes personal memory into DevMemoryIndex unless performing a deliberate migration.

## Verification checklist

Before relying on the integration:

```bash
hermes mcp list
hermes mcp test devmemory
```

Expected result: Hermes discovers the DevMemoryIndex MCP server and its registered tools. For a live coding session, verify that `get_session_context` returns a context block and that search results include actionable `id` values for follow-up `get_memory` calls.
