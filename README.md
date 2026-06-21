# DevMemoryIndex

A persistent developer memory store that captures, indexes, and semantically searches knowledge from your development workflow — git commits, terminal commands, AI agent solutions, meeting transcripts, markdown notes, and more.

## Overview

DevMemoryIndex turns your day-to-day development activity into a searchable, vector-indexed knowledge base. Memories are stored with rich metadata and retrieved via hybrid search (semantic similarity + keyword matching). It runs as a local daemon, exposes a REST API for cross-machine access, and integrates with Hermes Agent, Claude Code, and other MCP-compatible coding agents via stdio MCP.

```
core/         Storage engine, embeddings, hybrid search, config, edge graph
api/          FastAPI REST server with optional API key auth
cli/          Typer CLI — commands covering search, ingest, API, MCP-adjacent workflows, voice, and maintenance
connectors/   Git commits/diffs, terminal, filesystem, markdown, Claude/Copilot, browser, meetings
daemon/       Background scheduler, file watcher, edge inference jobs
memory_db/    LanceDB on-disk database (auto-created)
```

---

## Installation

```bash
git clone <repo-url> && cd devmemoryindex
uv sync --group dev
```

The `devmemory` CLI is available via `uv run devmemory` or add it to your PATH.

For an installable CLI and MCP server entry point in a virtualenv, use:

```bash
uv pip install -e '.[mcp,watch,ml,llm]'
```

This installs both console scripts:

```bash
devmemory --help
devmemory-mcp-server  # stdio MCP server for Hermes, Claude Code, and generic MCP clients
```

---

## Quick Start

```bash
# 1. Add your repos to the ingest list
devmemory config add ~/projects/my-app

# 2. Ingest recent git commits
devmemory ingest --source git

# 3. Search your memory
devmemory search "redis connection timeout"

# 4. Start the background daemon (ingests on a schedule)
devmemory daemon start
```

---

## CLI Reference

### `search` — Query your memory

```bash
# Natural-language similarity search
devmemory search "how did we fix the billing timeout"

# Limit results
devmemory search "docker compose setup" --limit 10

# Filter by memory type
devmemory search "auth middleware" --type agent_solution

# Filter by repository
devmemory search "schema migration" --repo billing-api

# Voice input (macOS)
devmemory search --voice

# Speak the top result aloud (macOS)
devmemory search "redis fix" --speak
```

### `add` — Manually store a memory

```bash
# Provide a concise summary inline
# (the same text is stored as both summary and raw text)
devmemory add "Set X-Forwarded-Host header in nginx"

# Add metadata
devmemory add "Proxy fix" --type agent_solution --repo api-gateway --importance 0.8
```

### `get` — Inspect a single memory

```bash
# By full UUID or 8-char prefix (shown in search results)
devmemory get a3f9c12d
devmemory get a3f9c12d-4e5f-...
```

Prints full metadata panel (ID, type, repo, source, importance, tags, timestamp) and the raw content.

### `graph` — Visualize memory relationships

```bash
# Show typed relationships around a memory
# Edge types include fixed_by, caused_by, references, supersedes, contradicts, related_to
devmemory graph a3f9c12d

# Traverse more hops from the root memory
devmemory graph a3f9c12d --depth 3
```

Renders a Rich tree plus an edge table using the unified DevMemoryIndex memory graph. The daemon auto-infers new edges weekly from related memories (for example, `failure_note` → `git_commit` as `fixed_by`, and `failure_note` → `agent_solution` as `references`). Graphify-imported codebase nodes can use the same graph once ingested.

### `context` — Build AI-ready context

Retrieves and formats relevant memories as a context block ready to prepend to an LLM prompt.

```bash
devmemory context "implement retry logic with exponential backoff"

# Limit token budget
devmemory context "redis caching" --tokens 2000

# Filter to one repo
devmemory context "auth flow" --repo api-gateway

# Output formats: markdown (default), claude (XML), raw
devmemory context "deployment steps" --format claude

# Copy directly to clipboard
devmemory context "database migrations" --copy
```

### `suggest` — Suggest memories from current changes

```bash
# Reads your staged/unstaged git diff and surfaces relevant memories
devmemory suggest
```

### `stats` — Memory store statistics

```bash
devmemory stats
```

### `prune` — Remove stale memories

```bash
# Dry run — shows what would be removed
devmemory prune --dry-run

# Remove memories below importance threshold
devmemory prune --floor 0.3
```

### `health` — Store quality dashboard

```bash
devmemory health
devmemory health --json
```

Prints type breakdown, importance histogram, avg access count, stale memories (never accessed + >60 days old), and low click-through-rate memories. Use this before a consolidation or pruning pass.

### `audit` — Review deprecated memories

```bash
# List all forgotten memories with their deprecation reasons
devmemory audit

# Permanently delete all deprecated memories after review
devmemory audit --purge
```

Memories marked with `forget_memory()` or `devmemory forget` are excluded from search but preserved here for review.

### `consolidate` — Merge redundant memories

```bash
# Merge two or more memories into one canonical entry
devmemory consolidate <id1> <id2> [<id3> ...]

# Provide a custom summary for the merged memory
devmemory consolidate <id1> <id2> --summary "canonical solution for X"
```

Combines the raw_text of all inputs, stores a new memory at max(importance), and permanently deletes the originals.

---

## Ingestion

### `ingest` — Run connectors manually

```bash
# Run all configured connectors
devmemory ingest

# Run a specific connector
devmemory ingest --source git
devmemory ingest --source diff
devmemory ingest --source terminal
devmemory ingest --source filesystem
devmemory ingest --source markdown
devmemory ingest --source claude
devmemory ingest --source copilot
devmemory ingest --source browser
devmemory ingest --source meeting
```

### Available connectors

| Source | What it indexes |
|---|---|
| `git` | Commit messages from configured repos |
| `diff` | Per-file code diffs from recent commits |
| `terminal` | Shell history (`~/.zsh_history`, `~/.bash_history`) |
| `filesystem` | Source files in configured code directories |
| `markdown` | Notes and docs from configured notes directories |
| `claude` | Claude Code session files (`~/.claude/projects/`) |
| `copilot` | GitHub Copilot chat logs |
| `browser` | Browser bookmarks/history metadata (Chrome/Firefox/Safari where available) |
| `meeting` | Meeting transcripts/recordings from configured directories |

---

## Configuration

```bash
# Add/remove repos for git + filesystem ingestion
devmemory config add ~/projects/my-app
devmemory config remove ~/projects/my-app

# Bulk-add all git repos under a directory
devmemory config scan ~/projects

# Add directories for markdown note scanning
devmemory config add-notes ~/notes
devmemory config remove-notes ~/notes

# Add directories for code file scanning
devmemory config add-code ~/projects/shared-libs
devmemory config remove-code ~/projects/shared-libs

# Add directories for meeting transcript scanning
devmemory config add-meetings ~/Downloads/meetings
devmemory config remove-meetings ~/Downloads/meetings

# Set per-connector ingest interval (seconds)
devmemory config set-schedule git 300

# Show current config
devmemory config list
```

Config is stored at `~/.config/devmemory/config.toml`.

---

## Daemon

Runs connectors on their configured schedules, watches markdown directories for live changes, and periodically infers memory-graph edges between related memories.

```bash
# Run in the foreground
devmemory daemon start

# Run with always-on voice/Jarvis mode (requires [jarvis] extra)
devmemory daemon start --jarvis

# Install as a native user service:
# - Linux: systemd --user at ~/.config/systemd/user/devmemory.service
# - macOS: launchd LaunchAgent at ~/Library/LaunchAgents/com.devmemory.daemon.plist
devmemory daemon install

# Preview the generated Linux systemd unit without writing or enabling it
devmemory daemon install --dry-run

# Check service status
devmemory daemon status

# Disable and remove the native user service
devmemory daemon uninstall

# View recent daemon log
devmemory log
devmemory log --lines 50
```

The daemon also runs maintenance jobs: daily pruning/log trimming, weekly deduplication, and weekly memory-graph edge inference. Edge inference currently links matching `failure_note` memories to likely fix commits/solutions so `devmemory graph` becomes richer over time.

On Linux, `devmemory daemon install` writes the systemd user service, runs
`systemctl --user daemon-reload`, and enables it with
`systemctl --user enable --now devmemory.service`. If `systemctl --user` is not
available, use `devmemory daemon install --dry-run` to print the unit and install
it manually in the target environment.

---

## Git Hook Integration

Automatically index every commit the moment it happens, without waiting for the daemon poll cycle.

```bash
# Install post-commit hook in the current repo
devmemory hook install

# Install in a specific repo
devmemory hook install ~/projects/my-app

# Check hook status across all configured repos
devmemory hook status

# Remove the hook
devmemory hook uninstall
```

The hook appends a marker-delimited block to your existing `post-commit` hook (safe to install alongside other hooks). It runs `devmemory ingest --source git` in the background after each commit.

---

## REST API

### Start the server

```bash
# Localhost only (default)
devmemory serve

# Expose on all interfaces (for cross-machine access)
devmemory serve --host 0.0.0.0 --port 7711

# Skip auth enforcement (even if a key is configured)
devmemory serve --no-auth
```

### API key authentication

Auth is **off by default**. When a key is configured, all endpoints require `Authorization: Bearer <key>`.

```bash
# Generate and save a key
devmemory api-key generate
# → API key saved. Use: Authorization: Bearer a3f9c12d...

# Show the current key
devmemory api-key show

# Remove the key (server re-opens)
devmemory api-key revoke
```

### Endpoints

```bash
# Search
curl "http://localhost:7711/memory/search?q=redis+timeout"
curl -H "Authorization: Bearer <key>" "http://machine:7711/memory/search?q=redis"

# Get memory by ID
curl "http://localhost:7711/memory/a3f9c12d-..."

# Context block
curl "http://localhost:7711/memory/context?q=auth+flow&format=markdown"

# Ingest via webhook (e.g. push a meeting transcript from another machine)
curl -X POST http://localhost:7711/memory/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "Q1 planning call transcript...", "source": "meeting-upload", "memory_type": "voice_note", "repo": "myapp", "tags": ["meeting"]}'

# Long texts are automatically chunked (~1000 chars/chunk, paragraph-aligned)
# Short text response: {"status": "ok", "id": "..."}
# Chunked response:    {"status": "ok", "count": 5, "added": 4, "ids": [...]}

# OpenAPI docs
open http://localhost:7711/docs
```

---

## MCP Server (agent integrations)

DevMemoryIndex exposes a Model Context Protocol server so MCP-compatible coding
agents can query and update your memories directly. The server uses stdio
transport, so the MCP client starts it on demand; you do not need to run a
separate long-lived MCP process.

### Hermes Agent

After installing `.[mcp]`, register the packaged stdio server command:

```bash
hermes mcp add devmemory --command devmemory-mcp-server
hermes mcp test devmemory
```

If you are running directly from a checkout without installing console scripts,
use an explicit Python command or a small wrapper that runs
`python -m mcp_server.server` from the repository root.

After adding the MCP server, start a new Hermes session or restart the gateway
so the discovered tools are available to the agent.

### Claude Code

Claude Code is also supported as an MCP client. Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "devmemory-mcp-server"
    }
  }
}
```


### Available tools

The MCP server currently registers 19 tools. Agent-facing descriptions should remain concise and operational because they are loaded into MCP clients as tool schemas.

**19 MCP tools available:**

| Tool | Purpose |
|---|---|
| `search_memories` | Hybrid search. Now returns `score_breakdown` on every result. |
| `build_context` | Formatted context block. Returns `{context_text, retrieval_trace, memory_count, token_estimate}`. |
| `get_session_context` | Call at session start — combines task + git state for bootstrapped context. |
| `remember_memory` | Persist a solution or decision. |
| `remember_failure` | Record a failed approach so it's never repeated. |
| `get_memory` | Fetch a single memory by ID (resolves `related[]` links). |
| `update_memory` | Correct an existing memory in-place. |
| `reinforce_memory` | Boost importance after successfully applying a solution. |
| `get_codebase_map` | KMeans cluster of `file_content` memories → subsystem overview. |
| `plan_task` | LLM-generated implementation plan grounded in memory + git state. |
| `explain_score` | Why did this memory rank here? Returns per-component breakdown + explanation. |
| `why_not_included` | Why was this memory absent from `build_context`? Diagnoses dedup / budget / no-match. |
| `forget_memory` | Deprecate bad knowledge. Excluded from search, preserved for audit. |
| `get_store_health` | Store quality report: type breakdown, stale count, low-CTR memories. |
| `consolidate_memories` | Merge N redundant memories into one canonical entry. |
| `search_batch` | Parallel search across multiple queries, deduplicated merged results. |
| `link_memories` | Create a typed causal edge between two memories. |
| `get_memory_graph` | Subgraph up to N hops from a root memory. |
| `trace_causality` | Follow `caused_by`/`fixed_by` edges to root cause. |

---

## Voice

```bash
# Dictate a memory (transcribed and indexed)
devmemory dictate

# Enroll a speaker profile for voice search
devmemory voice enroll

# Search using voice input
devmemory search --voice
```

---

## Export / Import

```bash
# Export all memories to JSON
devmemory export memories.json

# Import (skips duplicates by content hash)
devmemory import memories.json

# Interactive search REPL (model stays loaded between queries)
devmemory repl
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| Embeddings | `BAAI/bge-small-en` via sentence-transformers (384-dim) |
| Vector DB | LanceDB (embedded, columnar, no external server) |
| Search | Hybrid: vector similarity + keyword (WHERE LIKE) |
| API | FastAPI + Uvicorn |
| CLI | Typer + Rich |
| Package manager | uv |
| Testing | pytest |

---

## Running Tests

```bash
# All tests
uv run pytest -v

# Specific suites
uv run pytest core/tests/ -v
uv run pytest api/tests/ -v
uv run pytest core/tests/test_hybrid_search.py -v
uv run pytest core/tests/test_hooks.py -v
```
