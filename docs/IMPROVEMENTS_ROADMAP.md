# Agent Experience Improvements Roadmap

This document covers improvements to how AI agents interact with DevMemoryIndex — better surfacing, better memory quality, and capturing knowledge that currently falls through the cracks.

**Scope:** This file does NOT overlap with `ROADMAP.md`. It does not cover Phase 7 items (local LLM/RAG, VSCode extension, Web UI, ML classifier, codebase map, agent planning mode) or infrastructure (auth, connectors, daemon scheduling). Those remain in `ROADMAP.md`.

**Recommended implementation order:** ~~I1~~ → ~~I2~~ → I5 → I3 → I4

---

## ✅ I1 — Session Bootstrap (Proactive Context Push) — _Done (Phase 8)_

`get_session_context(task_description, repo)` MCP tool added. Combines task description with `git status --short` file stems and `git log --oneline -3` commit subjects, then calls `ContextEngine.build()` at `max_tokens=3000`. Silently no-ops outside git repos. Registered in server.py; instructions updated to call it first at session start.

---

## ✅ I2 — Failure / Negative Knowledge Memory Type — _Done (Phase 8)_

`remember_failure(summary, what_was_tried, why_it_failed, repo)` MCP tool added. Stores `failure_note` memories with `importance=0.7` and `tags=["attempted","failed","avoid"]`. `hybrid_search` applies a `0.4×` score penalty to `failure_note` results unless the query contains a negative-intent keyword (`avoid`, `failed`, `broken`, `error`, `bug`, `mistake`, `wrong`, `don't`, `shouldn't`, `didn't work`, `not work`). Registered in server.py.

---

## ✅ I3 — Summary Quality Enforcement — _Done (Phase 8)_

**Problem today:** Retrieval quality is directly determined by summary quality. Agents often save memories with generic summaries ("fixed the bug", "auth solution") that won't match future queries. There's no guard against low-signal summaries.

**Solution:**

In `remember_memory` (MCP tool), add a quality check at save time:
- If `summary` is under 20 characters, return a warning alongside the saved ID: `{"status": "ok", "id": "...", "warning": "summary may be too short for reliable retrieval"}`
- If `summary` is absent, auto-generate one from `raw_text`: take the first sentence longer than 30 characters that contains a space (no LLM needed — pure heuristic)

Add `devmemory stats --quality` that shows the distribution of summary lengths and flags memories with low-quality summaries (`< 20 chars`) for review or re-summarization.

Long-term: when Phase 7.1 (local LLM) lands, plug in LLM summarization as the `auto_summarize` backend for higher-quality fallbacks.

**Files to modify:**
- `mcp_server/tools.py` — quality check + auto-summarize in `remember_memory`
- `cli/commands/stats.py` — `--quality` flag
- `core/memory_store.py` — expose summary quality metric

---

## ✅ I4 — Retrieval-to-Use Quality Signal — _Done (Phase 8)_

**Problem today:** Every search hit is treated as equally relevant. There's no signal distinguishing memories an agent actually examined (called `get_memory` on) versus those it scrolled past. The importance/reinforce system can't tell "surfaced but ignored" from "surfaced and used."

**Solution:**

Track two counters per memory:
- `times_retrieved` — incremented each time the memory appears in a search result
- `times_accessed` — incremented each time `get_memory` is called for it (already partially signalled via `reinforce=True`)

The ratio `times_accessed / times_retrieved` is a click-through rate. A memory retrieved 20 times but never accessed likely has a poor summary or is no longer relevant.

Use this ratio as a soft signal in ranking: high-retrieval / low-access memories get a small importance dampening over time. Expose `devmemory stats --engagement` to surface these candidates for pruning or summary improvement.

**Files to modify:**
- `core/schema.py` — add `times_retrieved: int = 0`, `times_accessed: int = 0` fields
- `core/memory_store.py` — increment counters at the right points; use ratio in ranking
- `cli/commands/stats.py` — `--engagement` view
- `core/tests/` — test counter increments

---

## ✅ I5 — Workspace-Aware Context Surfacing — _Done (Phase 8)_

**Problem today:** When an agent is editing `core/memory_store.py`, it has no automatic way to surface memories related to that file or module. The agent must formulate a query itself — and if it doesn't know what's there, it won't know what to ask.

**Solution:**

Add an optional `files` parameter to `build_context` and `get_session_context`:
```
build_context(query, files=["core/memory_store.py", "core/embeddings.py"])
```

For each file path, extract lightweight signals with no deep parsing:
- Filename stem (`memory_store`)
- Parent directory (`core`)
- First 20 lines of the file: imports and docstring surface module-level keywords

Merge these signals with the task description query before hitting the search index. This means agents editing a known file automatically get relevant memories surfaced without having to name them.

**Files to modify:**
- `mcp_server/tools.py` — add `files` param to `build_context` and `get_session_context`
- `core/context_engine.py` — accept file hints as supplementary query terms
- `README.md` — document the pattern for Hermes Agent startup guidance and optional Claude Code project instructions

---

## Summary Table

| ID | Title | Complexity | Value | Depends on | Status |
|---|---|---|---|---|---|
| I1 | Session Bootstrap | Low | High | — | ✅ Done |
| I2 | Failure Memory Type | Low | High | — | ✅ Done |
| I5 | Workspace-Aware Surfacing | Medium | High | I1 | ✅ Done |
| I3 | Summary Quality Enforcement | Low | Medium | — | ✅ Done |
| I4 | Retrieval-to-Use Signal | Medium | Medium | — | ✅ Done |
