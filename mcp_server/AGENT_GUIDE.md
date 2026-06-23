# DevMemoryIndex MCP Agent Guide

This guide is for autonomous coding agents using the DevMemoryIndex MCP server. It complements the tool descriptions exposed in MCP schemas and keeps the recommended flow explicit.

## Recommended flow for complex repo work

1. **Start with `get_session_context`.** Call it once near the start of a complex coding or debugging session with the task, repo, and likely files.
2. **Search only when needed.** If the bootstrap context is insufficient, call `search_memories` with specific technical terms: error text, library names, file names, component names, or architecture terms.
3. **Resolve promising IDs.** Call `get_memory` for high-signal search results and any `related[]` IDs that look actionable.
4. **Build a context block.** Use `build_context` before broad implementation planning, multi-file edits, or handoff to another agent.
5. **Plan selectively.** Use `plan_task` for non-trivial implementation plans. Skip it for tiny edits where direct work is clearer.
6. **Write only verified durable knowledge.** After verified success, call `remember_memory` for root causes, reusable commands, workflows, integration gotchas, and architecture decisions.
7. **Record meaningful dead ends.** Call `remember_failure` when a failed approach consumed real time and future agents should avoid it.
8. **Reinforce proven memories.** Call `reinforce_memory` when a retrieved memory directly helped solve the task.
9. **Correct stale knowledge.** Use `update_memory` when a memory is incomplete or outdated. Use `forget_memory` when it is wrong, superseded, or unsafe to keep active.
10. **Use graph tools when relationships matter.** Use `link_memories`, `get_memory_graph`, and `trace_causality` after inspecting relevant IDs, especially for bug/fix/root-cause chains.

## Anti-patterns

- Do not call `get_session_context` repeatedly for the same task. Reuse the result unless the task changes substantially.
- Do not use broad searches such as `bug`, `memory`, or `fix` unless you are exploring; refine quickly.
- Do not store PR numbers, issue numbers, branch names, temporary TODO state, copied logs without explanation, or one-off task progress.
- Do not store secrets, tokens, credentials, API keys, private personal data, or raw dumps that should live in files.
- Do not use `plan_task` for tiny changes just to appear systematic; it may invoke an LLM and add latency.
- Do not link memories only because they share keywords. Inspect both memories and choose a precise edge type.

## What to store

Prefer storing root causes and durable facts that make future work faster:

- verified commands and exact fixes that are likely reusable
- durable environment quirks
- project conventions and architectural decisions
- reusable debugging workflows
- integration gotchas between DevMemoryIndex, Hermes, MCP clients, local LLMs, LanceDB, or packaging
- explanations of why a failed approach failed

## Good query shapes

- `lancedb schema timestamp pyarrow field mismatch`
- `mcp server startup slow sentence transformers import`
- `hermes mcp add devmemory wrapper script tool discovery`
- `systemd user service daemon install dry run`

## Good memory write shapes

- Summary: `Lazy-load sentence-transformers so MCP tool discovery stays fast`
- Raw text: include the root cause, tested command, files changed, and verification result.
- Tags: include subsystem/library terms such as `mcp`, `lancedb`, `packaging`, `systemd`.

## Minimal Hermes startup prompt

```text
Before modifying this repo, use DevMemoryIndex to retrieve relevant context for: <task>. Start with get_session_context once, then search only if needed. Do not store anything until the fix is verified.
```
