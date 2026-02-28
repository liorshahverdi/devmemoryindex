# DevMemoryIndex

A persistent developer memory store that captures, indexes, and semantically searches knowledge from your development workflow — git commits, terminal commands, AI agent solutions, meeting transcripts, markdown notes, and more.

## Overview

DevMemoryIndex turns your day-to-day development activity into a searchable, vector-indexed knowledge base. Memories are stored with rich metadata and retrieved via hybrid search (semantic similarity + keyword matching). It runs as a local daemon, exposes a REST API for cross-machine access, and integrates directly into Claude Code via MCP.

```
core/         Storage engine, embeddings, hybrid search, config
api/          FastAPI REST server with optional API key auth
cli/          Typer CLI — 18 commands covering all features
connectors/   Git, terminal, filesystem, markdown, Copilot, browser, meetings
daemon/       Background scheduler + markdown file watcher
memory_db/    LanceDB on-disk database (auto-created)
```

---

## Installation

```bash
git clone <repo-url> && cd devmemoryindex
uv sync --group dev
```

The `devmemory` CLI is available via `uv run devmemory` or add it to your PATH.

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
# Paste a solution, note, or command interactively
devmemory add

# Provide inline
devmemory add --summary "Proxy fix" --raw "Set X-Forwarded-Host header in nginx"
```

### `get` — Inspect a single memory

```bash
# By full UUID or 8-char prefix (shown in search results)
devmemory get a3f9c12d
devmemory get a3f9c12d-4e5f-...
```

Prints full metadata panel (ID, type, repo, source, importance, tags, timestamp) and the raw content.

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
devmemory prune --min-importance 0.3
```

---

## Ingestion

### `ingest` — Run connectors manually

```bash
# Run all configured connectors
devmemory ingest

# Run a specific connector
devmemory ingest --source git
devmemory ingest --source terminal
devmemory ingest --source filesystem
devmemory ingest --source markdown
devmemory ingest --source claude
devmemory ingest --source copilot
```

### Available connectors

| Source | What it indexes |
|---|---|
| `git` | Commit messages + diffs from configured repos |
| `terminal` | Shell history (`~/.zsh_history`, `~/.bash_history`) |
| `filesystem` | Source files in configured code directories |
| `markdown` | Notes and docs from configured notes directories |
| `claude` | Claude Code session files (`~/.claude/projects/`) |
| `copilot` | GitHub Copilot chat logs |
| `browser` | Browser history (Chrome/Firefox) |
| `meetings` | Meeting transcripts from configured directories |

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

Runs connectors on their configured schedules and watches markdown directories for live changes.

```bash
# Run in the foreground
devmemory daemon start

# Install as a macOS launchd service (auto-starts at login)
devmemory daemon install
devmemory daemon uninstall

# Check service status
devmemory daemon status

# View recent daemon log
devmemory log
devmemory log --lines 50
```

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
curl -X POST http://localhost:7711/webhook/ingest \
  -H "Content-Type: application/json" \
  -d '{"summary": "Q1 planning call", "raw_text": "...", "type": "voice_note"}'

# Long texts are automatically chunked (~1000 chars/chunk, paragraph-aligned)
# Short text response: {"status": "ok", "id": "..."}
# Chunked response:    {"status": "ok", "count": 5, "added": 4, "ids": [...]}

# OpenAPI docs
open http://localhost:7711/docs
```

---

## MCP Server (Claude Code integration)

DevMemoryIndex exposes a Model Context Protocol server so Claude Code can query your memories directly.

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "devmemory": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/devmemoryindex", "python", "-m", "mcp_server"]
    }
  }
}
```

Available MCP tools: `search_memories`, `build_context`, `remember_memory`, `get_memory`.

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
