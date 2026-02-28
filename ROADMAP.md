# DevMemoryIndex — Master Roadmap

> **Persistent memory for developers and AI coding agents.**
>
> A local-first system that indexes your Git commits, terminal history, code files,
> notes, and AI agent conversations — then serves semantically relevant context to
> you (via CLI) and your tools (via API) instantly.

---

## Current State (Completed)

| Component | Status | Notes |
|---|---|---|
| `core/schema.py` — Memory dataclass | **Done** | id, type, summary, raw_text, source, repo, timestamp, tags, importance |
| `core/embeddings.py` — BAAI/bge-small-en (384d) | **Done** | `embed()` and `embed_batch()` working |
| `core/memory_store.py` — MemoryStore class | **Done** | `add()`, `semantic_search()`, `hybrid_search()`, `delete()`, `count()`, `get_all()`, `exists()`, `reinforce()`, `truncate()`. Uses `compute_score` from ranking module. `reinforce()` capped at 0.8 (not 1.0), boost=0.02. Keyword search extended to `raw_text` OR `summary`. Reinforce gated on similarity >= 0.7. |
| `core/store_provider.py` — Singleton factory | **Done** | `get_store()` returns shared `MemoryStore` instance |
| `core/ranking.py` — Scoring formula | **Done** | `recency_score()`, `compute_score()` — weights: similarity 0.75, importance 0.15, recency 0.10 (revised: semantic similarity given more weight to prevent high-importance unrelated results dominating) |
| `core/privacy.py` — Redaction filter | **Done** | `redact()` — strips API keys, bearer tokens, base64 blobs, SSNs, emails. Hooked into `connectors/base.py` via `_redact()`. |
| `core/tests/test_privacy.py` | **Done** | 4 tests — API key redaction, bearer token strip, clean text passthrough, end-to-end store test. All passing. |
| `core/speaker_profile.py` — Speaker identity | **Done** | `enroll()`, `load_profile()`, `is_self()` — cosine distance on pyannote embeddings, threshold 0.3 |
| `core/token_budget.py` — Token estimation | **Done** | `estimate_tokens()`, `pack_within_budget()` — enforces max_tokens and max_items limits. |
| `core/context_engine.py` — ContextEngine class | **Done** | `build()`, `_deduplicate()`, `_format()` fully implemented. |
| `core/tests/test_context_engine.py` | **Done** | 4 tests — build context, token budget truncation, repo filter, format modes. All passing. |
| `core/tests/test_schema.py` | **Done** | 2 tests — Memory creation, field validation, default importance. All passing. |
| `core/tests/test_memory_store.py` | **Done** | 3 tests — all passing. |
| `core/tests/test_ranking.py` | **Done** | 11 tests — recency decay, score formula, ranking order. All passing. |
| `core/tests/test_hybrid_search.py` | **Done** | 5 tests — keyword surfacing, deduplication, hybrid-vs-semantic, importance ranking, k limit. All passing. |
| `cli/main.py` — Typer entrypoint | **Done** | 17 commands/sub-apps registered: `search`, `add`, `stats`, `prune`, `dictate`, `voice`, `context`, `suggest`, `daemon`, `export`, `import`, `repl`, `ingest`, `config`, `serve`, `log`, `get`, `api-key`. |
| `cli/commands/search.py` | **Done** | `hybrid_search()`, `--type`/`--repo` filters, `--voice` (3s countdown + 8s record + quality gate), `--speak` flag. |
| `cli/commands/context.py` | **Done** | `devmemory context` — wraps `ContextEngine`, supports `--format raw/markdown/claude`, `--json`, `--copy`, `--repo`, `--tokens`. |
| `cli/commands/suggest.py` | **Done** | `devmemory suggest` — `git diff HEAD` → `ContextEngine` → print context. Falls back to `git log -5`. No query required. |
| `cli/commands/add.py` | **Done** | Manual memory insertion via CLI. |
| `cli/commands/stats.py` | **Done** | Shows total count and type breakdown. |
| `cli/commands/prune.py` | **Done** | Deletes memories below importance floor or over age+importance threshold. `--dry-run` supported. |
| `cli/commands/dictate.py` | **Done** | Record 5–60s, transcribe via Whisper, auto-index as voice_note. Noise gate + min-word guard. |
| `cli/commands/enroll.py` | **Done** | `devmemory voice enroll` — capture 30s voiceprint and save speaker profile. |
| `cli/commands/daemon_cmd.py` | **Done** | `devmemory daemon` — starts background scheduler loop. |
| `cli/commands/export.py` | **Done** | `devmemory export` / `devmemory import` — JSON dump and restore with duplicate skipping. |
| `cli/commands/repl.py` | **Done** | Interactive prompt loop — model stays loaded between queries. |
| `connectors/base.py` — Abstract Connector | **Done** | Abstract `Connector` class with `collect()` method and shared store access. |
| `connectors/registry.py` | **Done** | `get_connectors()` factory; `ALL_CONNECTORS` = `[GitConnector, ClaudeConnector, TerminalConnector, MarkdownConnector]`. |
| `connectors/git_connector.py` | **Done** | Fetches commit subject + body, embeds `subject+body[:512]`, stores full body in `raw_text`. Docs importance 0.5. |
| `connectors/claude_connector.py` | **Done** | Indexes `~/.claude/projects/**/*.jsonl` assistant responses (>= 150 chars). Repo from `cwd`. 89 memories on first run. |
| `connectors/terminal_connector.py` | **Done** | Indexes last 500 unique commands from `~/.zsh_history` / `~/.bash_history`. Filters trivial commands. Importance: docker/kubectl=0.8, git rebase=0.7, pip/uv=0.6. 535 memories on first run. |
| `connectors/voice_connector.py` | **Done** | Records mic audio, transcribes with Whisper, checks speaker identity (cosine), stores as `voice_note` or `voice_ambient`. |
| `core/intent_classifier.py` | **Done** | Rule-based classifier: debug / recall / architecture / implementation / general. Integrated into `ContextEngine.build()` and `search --voice`. Recall rule checked before implementation to prevent keyword overlap. Recall intent sets `sort_by_time: True` — results sorted by timestamp descending, output formatted as timeline with visible dates. |
| `connectors/markdown_connector.py` | **Done** | Indexes `.md` files from configured scan dirs. Chunks by H2 headings. Parses YAML frontmatter (title, tags). Skips hidden dirs. importance=0.85 for "important" tagged files, 0.7 default. `devmemory config add-notes <dir>` to configure. |
| `core/config.py` — markdown helpers | **Done** | `get_markdown_dirs()`, `add_markdown_dir()`, `remove_markdown_dir()` — `[markdown] scan_dirs` in config.toml. |
| `cli/commands/config_cmd.py` — notes commands | **Done** | `devmemory config add-notes <dir>`, `devmemory config remove-notes <dir>`. `list` shows both git repos and markdown dirs. |
| `core/memory_store.py` — type/repo filter in hybrid_search | **Done** | `hybrid_search()` now accepts `type_filter` and `repo_filter`; filters applied as DB-level WHERE clauses before the k-cap, preventing type-filtered searches from returning empty results. Each result includes `"related": [id, id, id]` — nearest neighbours from the semantic pool that didn't make top-k, at zero extra DB cost. |
| `api/server.py` + `api/routes/` | **Done** | Phase 4B REST API. `GET /memory/search`, `POST /memory/remember`, `GET /memory/context`, `POST /memory/ingest` (webhook). `devmemory serve` CLI command. `[api]` optional extra (fastapi + uvicorn). GitHub Actions integration documented. |
| `core/context_cache.py` | **Done** | Phase 5.B. Module-level LRU cache (50 entries, 5-min TTL) for `ContextEngine.build()`. Keyed on `sha256(query\|repo\|format\|intent)`. Auto-invalidated via `store.add()`. Context response includes `cached: true/false`. |
| `daemon/jobs/dedup.py` | **Done** | Phase 5.C. Groups memories by `summary[:100].lower()`, keeps highest-importance duplicate, deletes the rest. Runs weekly (Mondays) in daemon scheduler. |
| `core/memory_store.py` — get_by_id | **Done** | `get_by_id(memory_id)` — fetch a single memory by exact ID. Used to resolve `related[]` links from search results. |
| `mcp_server/server.py` | **Done** | FastMCP entrypoint, stdio transport, registered with Claude Code via `claude mcp add`. 4 tools. |
| `mcp_server/tools.py` | **Done** | `search_memories` (now uses DB-level type/repo filters, returns `id` + `related[]`), `build_context`, `remember_memory`, `get_memory` (resolves related IDs). |
| `api/routes/memory.py` — GET /{id} | **Done** | `GET /memory/{memory_id}` — fetch single memory by ID, 404 if not found. |
| `scripts/reset_importance.py` | **Done** | Clamps drifted importance values back to 0.8. `--dry-run` supported. |
| `daemon/scheduler.py` | **Done** | Per-connector schedule loop. Each connector fires independently when `now - last_run >= configured_interval`. Polls every 60 s. Logs to file via `daemon_log`. Trims log daily. Prunes daily, deduplicates weekly. |
| `daemon/daemon_log.py` | **Done** | File logger to `~/.local/share/devmemory/daemon.log`. `write(msg, level)`, `trim(max_lines=5000)` — trims on startup + daily, `tail(n)` for CLI viewer. 7 tests. |
| `cli/commands/log_cmd.py` | **Done** | `devmemory log [-n N]` — tail recent daemon log entries, colour-coded by level. `--path` prints log file path for `tail -f`. |
| `core/config.py` — schedule helpers | **Done** | `get_connector_interval(name)`, `set_connector_interval(name, seconds)`, `get_all_intervals()`. Defaults: git=10m, claude=5m, terminal=1h, markdown=30m. Persisted as integers in `[schedule]` section of config.toml. `_to_toml()` updated to handle int values. |
| `cli/commands/config_cmd.py` — set-schedule | **Done** | `devmemory config set-schedule <connector> <seconds>` — validates connector name, minimum 30 s. `devmemory config list` now always shows Connector Schedules table. |
| `cli/commands/daemon_cmd.py` | **Done** | Sub-app with 4 commands: `devmemory daemon start` (foreground), `install` (launchd), `uninstall`, `status`. |
| `daemon/launchd.py` | **Done** | macOS launchd integration. `install()` writes `~/Library/LaunchAgents/com.devmemory.daemon.plist` and loads it. `uninstall()` unloads + removes. `status()` checks PID via `launchctl list`. Daemon auto-starts at login, restarts on crash. stderr → `daemon-error.log`. |
| `daemon/watcher.py` | **Done** | Filesystem watcher using `watchdog`. Watches configured markdown scan dirs for `.md` create/modify/move events. 2-second debounce prevents rapid-save storms. On trigger: runs `MarkdownConnector().collect()`. Graceful fallback if `watchdog` not installed. Started as a daemon thread by `run_daemon()`. |
| `pyproject.toml` — watch extra | **Done** | `[watch]` optional dep: `watchdog>=3.0`. Also added to `[dev]` deps. |
| `daemon/jobs/memory_cleanup.py` | **Done** | `prune_memories()` — removes importance < 0.05 OR (age > 90 days AND importance < 0.15). |
| `daemon/jobs/importance_decay.py` | **Done** | `decay_importance(factor=0.99)` — daily decay on all non-pinned memories. |
| `scripts/truncate_memories.py` | **Done** | Standalone bulk-delete CLI with `--filter-repo`, `--dry-run`, `--yes` confirmation. |
| `pyproject.toml` | **Done** | `[project.scripts]` registered, hatchling build, dev deps + `[voice]` optional extras configured. |
| Project structure | **Done** | `core/`, `connectors/`, `cli/`, `api/`, `daemon/`, `scripts/` directories |
| LanceDB with explicit schema + timestamp("us") | **Done** | Proper Arrow types, 384-dim vector field |
| `connectors/filesystem_connector.py` | **Done** | Indexes code files from configured scan dirs. Language-aware importance: Python/TS/Go=0.7, others=0.5. Skips binaries, hidden dirs, `.gitignore` patterns. `devmemory config add-fs <dir>` to configure. |
| `connectors/copilot_connector.py` | **Done** | Indexes GitHub Copilot chat logs from VSCode `workspaceStorage`. Extracts assistant responses ≥ 100 chars. Importance 0.7. |
| `connectors/browser_connector.py` | **Done** | Indexes browser bookmarks from Chrome/Firefox/Safari. Extracts title + URL, stores as `browser_bookmark`. Importance 0.6. |
| `connectors/meeting_connector.py` | **Done** | Indexes meeting transcripts from configured dirs. Chunks by speaker turn. Speaker identification via cosine profile. importance=0.75 for self turns. |
| `core/config.py` — API key helpers | **Done** | `get_api_key()`, `set_api_key()`, `delete_api_key()` — `[api]` section in config.toml. |
| `api/auth.py` | **Done** | `verify_api_key` FastAPI dependency. Open if no key configured; 401 if key set and header missing/wrong; `DEVMEMORY_NO_AUTH` env var bypasses enforcement. |
| `cli/commands/api_key_cmd.py` | **Done** | `devmemory api-key generate/show/revoke` — 64-char hex key management. |
| `api/tests/test_auth.py` | **Done** | 10 tests — open access, key enforcement, wrong key, `--no-auth` bypass. All passing. |
| `cli/commands/serve.py` — `--no-auth` flag | **Done** | Disables key enforcement even if a key is configured. Passes `auth_enabled=False` → sets `DEVMEMORY_NO_AUTH=1`. |
| `cli/commands/get_cmd.py` | **Done** | `devmemory get <id-or-prefix>` — exact + prefix-scan lookup, metadata panel + raw_text panel. |
| `cli/commands/search.py` — ID column | **Done** | Search results table now includes an 8-char ID prefix column for quick copy-paste into `devmemory get`. |
| `core/hooks.py` | **Done** | `install_hook()`, `uninstall_hook()`, `hook_status()` — safe append/strip with marker block, `chmod +x`. |
| `cli/commands/hook_cmd.py` | **Done** | `devmemory hook install/uninstall/status` — defaults to cwd, falls back to all configured repos for status. |

**All connectors implemented:**
- `connectors/` — git, claude, terminal, markdown, voice, filesystem, copilot, browser, meeting — all done ✅
- `daemon/watcher.py` — filesystem watcher done ✅
- `api/auth.py` — optional API key auth done ✅

**What's next:**
1. **Phase 7.4** — Semantic diff awareness (`DiffConnector`, query code changes directly)
2. **Phase 7.1** — Local LLM / RAG (`devmemory ask`)

---

## Target Architecture

Two query tracks, one shared core:

```
VOICE QUERY TRACK (Human)           AGENT QUERY TRACK (AI)
─────────────────────────           ──────────────────────
speak → Whisper STT (local)         Claude Code tool call
  ↓                                   ↓
classify_intent() [rule-based]      MCP Server (Phase 4A)
  ↓                                 (stdio, no HTTP needed)
hybrid_search + ContextEngine         ↓
  ↓                                 hybrid_search + ContextEngine
confirm: "Searching for: X"           ↓
  ↓                                 returns list[dict] or claude XML
optional: say() top result

              SHARED CORE
         MemoryStore (LanceDB)
       hybrid_search + ranking
        ContextEngine.build()
         token_budget packing
             privacy.redact()

CONNECTORS (background)          REST API (Phase 4B — external)
──────────────────────           ──────────────────────────────
GitConnector ✅                  POST /memory/search
ClaudeConnector (next)           GET  /memory/context
TerminalConnector                POST /memory/remember
MarkdownConnector                POST /memory/ingest (CI/CD)
FilesystemConnector              GET  /memory/context/stream

DAEMON ✅                        CLI (Human)
──────                           ───────────
scheduler.py                     context, suggest, search --voice
importance_decay.py              ingest, dictate, voice enroll
memory_cleanup.py                add, stats, prune, config
```

### Target Repo Structure

```
devmemoryindex/
├── core/
│   ├── schema.py              # Memory dataclass
│   ├── embeddings.py          # Embedding model
│   ├── memory_store.py        # MemoryStore class (LanceDB)
│   ├── store_provider.py      # Singleton factory
│   ├── ranking.py             # Score = similarity × importance × recency
│   ├── filtering.py           # Repo/type/tag/recency filters
│   ├── context_engine.py      # Build AI-ready context blocks
│   ├── token_budget.py        # Enforce LLM token limits
│   ├── privacy.py             # Regex-based redaction (API keys, tokens, PII)
│   └── formatter.py           # Output formatting (raw/claude/chatgpt)
│
├── connectors/
│   ├── base.py                # Abstract Connector class
│   ├── registry.py            # List of active connectors
│   ├── git_connector.py       # Git commit history
│   ├── terminal_connector.py  # Shell history (.zsh_history / .bash_history)
│   ├── filesystem_connector.py# Code files (.py, .ts, .md, .json)
│   ├── markdown_connector.py  # Notes/Obsidian/knowledge dirs
│   ├── claude_connector.py    # Claude Code conversation logs
│   ├── copilot_connector.py   # VSCode Copilot chat (best-effort)
│   ├── voice_connector.py     # Microphone recordings via Whisper STT
│   └── browser_connector.py   # Chrome/Firefox bookmarks
│
├── cli/
│   ├── main.py                # Typer entrypoint
│   └── commands/
│       ├── search.py          # devmemory search "query" [--voice]
│       ├── ingest.py          # devmemory ingest [--source git|terminal|all]
│       ├── context.py         # devmemory context "query" [--json] [--copy] [--repo]
│       ├── add.py             # devmemory add (manual memory)
│       ├── stats.py           # devmemory stats
│       ├── dictate.py         # devmemory dictate (speak → auto-index)
│       ├── daemon_cmd.py      # devmemory daemon start
│       ├── tag.py             # devmemory tag add/remove/list
│       ├── pin.py             # devmemory pin / unpin
│       ├── export.py          # devmemory export / import
│       ├── audit.py           # devmemory audit (duplicates, orphans)
│       └── repl.py            # devmemory repl (interactive prompt loop)
│
├── api/
│   ├── server.py              # FastAPI app
│   └── routes/
│       ├── search.py          # POST /search
│       ├── memory.py          # POST /remember
│       ├── context.py         # POST /context
│       └── webhook.py         # POST /ingest (CI/CD push)
│
├── daemon/
│   ├── scheduler.py           # Periodic connector execution
│   ├── watcher.py             # Filesystem watcher (watchdog)
│   └── jobs/
│       └── importance_decay.py# Daily importance decay
│
└── memory_db/                 # LanceDB data directory
```

---

## Phase 1 — Complete the Core Engine

> **Goal:** MemoryStore becomes a fully functional memory brain — not just a
> thin DB wrapper — with hybrid search, ranking, and a singleton access pattern.

### 1.1 Finish MemoryStore class ✅

**Status: COMPLETED**

**File:** `core/memory_store.py`

The `MemoryStore` class now has all required methods:
- `add()` — insert a Memory + vector
- `semantic_search()` — vector similarity search
- `delete()` — remove by ID
- `count()` — row count
- `get_all()` — dump all records (debugging)

Legacy global functions (`save_memory`, `search_memory`, `_get_collection`) have been removed. Tests in `test_memory_store.py` have been rewritten to use the class directly with `tmp_path` isolation (3 tests, all passing).
---

### 1.2 Create Store Provider (singleton) ✅

**Status: COMPLETED**

**File:** `core/store_provider.py`

Implemented as designed — `get_store(db_path)` returns a singleton `MemoryStore` instance. All future subsystems (CLI, API, connectors, daemon) will import `get_store()` instead of creating `MemoryStore` directly.

---

### 1.3 CLI Bootstrap (Scaffold + First Commands) ✅

**Status: COMPLETED**

All 6 files created and working:
- `cli/__init__.py`, `cli/commands/__init__.py` — package inits
- `cli/main.py` — Typer entrypoint registering `search`, `add`, `stats`
- `cli/commands/search.py` — search memories (uses `hybrid_search()`)
- `cli/commands/add.py` — manual memory insertion
- `cli/commands/stats.py` — memory store statistics (adapted to use `to_arrow()` instead of `to_pandas()`)

`pyproject.toml` has `[project.scripts] devmemory = "cli.main:app"` registered.

**Upgrade complete:** `search.py` now calls `hybrid_search()` with `--type` and `--repo` filter support.

<details>
<summary>Original implementation spec (preserved for reference)</summary>

**Dependencies:** `typer`, `rich` — install with `uv add typer rich`

This step creates **6 files**. All code is listed below — nothing is deferred to a later section.

---

**Step 1 — Package init files:**

Create `cli/__init__.py` and `cli/commands/__init__.py` (both empty) so Python treats these directories as packages:

```
cli/__init__.py           # empty
cli/commands/__init__.py  # empty
```

# ** stopped here ** 
---

**Step 2 — Entrypoint:** `cli/main.py`

```python
import typer

app = typer.Typer(
    name="devmemory",
    help="Persistent memory for developers and AI coding agents.",
)

# Phase 1 commands (core engine only — no connectors needed)
from cli.commands.search import search
from cli.commands.add import add
from cli.commands.stats import stats

app.command()(search)
app.command()(add)
app.command()(stats)

if __name__ == "__main__":
    app()
```

---

**Step 3 — Register in `pyproject.toml`:**

```toml
[project.scripts]
devmemory = "cli.main:app"
```

Then run `uv pip install -e .` so the `devmemory` command is available in your shell.

---

**Step 4 — Search command:** `cli/commands/search.py`

```python
import typer
from rich.console import Console
from rich.table import Table
from core.store_provider import get_store
from core.embeddings import embed

console = Console()

def search(
    query: str = typer.Argument(..., help="Natural language search query"),
    k: int = typer.Option(5, "--limit", "-k", help="Number of results"),
    type: str | None = typer.Option(None, "--type", "-t", help="Filter by memory type"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Filter by repo name"),
):
    """Search your developer memory."""
    store = get_store()
    vector = embed(query)

    results = store.semantic_search(vector, k=k * 3)

    # Apply CLI filters
    if type:
        results = [r for r in results if r.get("type") == type]
    if repo:
        results = [r for r in results if r.get("repo") == repo]

    results = results[:k]

    if not results:
        console.print("[yellow]No memories found.[/yellow]")
        return

    table = Table(title=f"Results for: {query}")
    table.add_column("Type", style="cyan", width=16)
    table.add_column("Summary", style="white")
    table.add_column("Repo", style="green", width=16)
    table.add_column("Importance", justify="right", width=10)

    for r in results:
        table.add_row(
            r.get("type", ""),
            r.get("summary", "")[:80],
            r.get("repo", "N/A") or "N/A",
            f"{r.get('importance', 0.5):.1f}",
        )

    console.print(table)
```

---

**Step 5 — Add command:** `cli/commands/add.py`

```python
import typer
import hashlib
from datetime import datetime
from core.store_provider import get_store
from core.schema import Memory
from core.embeddings import embed

def add(
    summary: str = typer.Argument(..., help="Summary of the memory"),
    type: str = typer.Option("agent_solution", "--type", "-t"),
    repo: str | None = typer.Option(None, "--repo", "-r"),
    importance: float = typer.Option(0.9, "--importance", "-i"),
):
    """Manually add a memory (e.g., paste a Claude solution)."""
    store = get_store()

    mem_id = hashlib.sha256(summary.encode()).hexdigest()
    memory = Memory(
        id=mem_id,
        type=type,
        summary=summary[:200],
        raw_text=summary,
        source="manual",
        repo=repo,
        timestamp=datetime.utcnow(),
        tags=["manual"],
        importance=importance,
    )

    vector = embed(memory.summary)
    store.add(memory, vector)

    typer.echo(f"Memory added: {summary[:60]}...")
```

---

**Step 6 — Stats command:** `cli/commands/stats.py`

```python
import typer
from rich.console import Console
from rich.table import Table
from core.store_provider import get_store

console = Console()

def stats():
    """Show memory store statistics."""
    store = get_store()
    total = store.count()

    console.print(f"\n[bold]DevMemoryIndex Stats[/bold]")
    console.print(f"Total memories: {total}")

    try:
        all_data = store.collection.to_pandas()
        type_counts = all_data["type"].value_counts()
        table = Table(title="Memories by Type")
        table.add_column("Type", style="cyan")
        table.add_column("Count", justify="right")
        for mem_type, count in type_counts.items():
            table.add_row(mem_type, str(count))
        console.print(table)
    except Exception:
        pass
```

---

**Verification checklist:**

```bash
devmemory --help                          # shows search, add, stats
devmemory add "Fixed Redis timeout"       # inserts a memory
devmemory search "redis"                  # finds the memory
devmemory stats                           # shows 1 memory
```

**Done when:** All four commands above work. The CLI is usable even with zero connectors.

</details>

**Upgrade complete:** `cli/commands/search.py` now calls `store.hybrid_search(query, vector, k=...)` with CLI-level `--type` and `--repo` filtering.

---

### 1.4 Implement Ranking Module ✅

**Status: COMPLETED**

**File:** `core/ranking.py` — implemented as designed with `recency_score()` and `compute_score()`.

**Tests:** `core/tests/test_ranking.py` — 11 tests covering recency decay, score formula, default handling, and ranking order. All passing.

<details>
<summary>Original implementation spec (preserved for reference)</summary>

Scoring formula:
```
final_score = semantic_similarity * 0.6
            + importance * 0.25
            + recency * 0.15
```

Recency calculation:
```python
from datetime import datetime
import math

def recency_score(timestamp: datetime) -> float:
    age_hours = (datetime.utcnow() - timestamp).total_seconds() / 3600
    return math.exp(-age_hours / (30 * 24))  # decay over ~30 days

def compute_score(result: dict) -> float:
    semantic = 1 - result.get("_distance", 1.0)
    importance = result.get("importance", 0.5)
    recency = recency_score(result["timestamp"])
    return semantic * 0.6 + importance * 0.25 + recency * 0.15
```

</details>

---

### 1.5 Implement Hybrid Search ✅

**Status: COMPLETED**

**File:** `core/memory_store.py` — `hybrid_search()` method added. Combines semantic search (vector similarity) with keyword search (`LIKE` on summary), deduplicates by id, and ranks using `compute_score()` from the ranking module.

**Tests:** `core/tests/test_hybrid_search.py` — 5 tests:
- Keyword match surfaces despite weak embedding similarity
- Deduplication (same memory from both paths appears only once)
- Hybrid returns better results than semantic alone for keyword queries
- Higher importance ranks higher among keyword matches
- Respects k limit

All 5 passing.

<details>
<summary>Original implementation spec (preserved for reference)</summary>

```python
def hybrid_search(self, query: str, vector: list, k: int = 5) -> list:
    # 1. Semantic search — over-retrieve
    semantic_results = self.collection.search(vector).limit(50).to_list()

    # 2. Keyword search — catch exact term matches semantic may miss
    safe_query = query.replace("'", "''")
    try:
        keyword_results = (
            self.collection
            .search()
            .where(f"summary LIKE '%{safe_query}%'")
            .limit(50)
            .to_list()
        )
    except Exception:
        keyword_results = []

    # 3. Merge and deduplicate by id
    combined = {r["id"]: r for r in semantic_results}
    for r in keyword_results:
        if r["id"] not in combined:
            combined[r["id"]] = r

    # 4. Score and rank using compute_score from core.ranking
    ranked = sorted(combined.values(), key=compute_score, reverse=True)

    return ranked[:k]
```

</details>

---
### 1.6 Implement Context Engine ✅

**Status: COMPLETED**

**What is done:**
- `core/context_engine.py` — `ContextEngine` class fully implemented: `build()`, `_deduplicate()`, `_format()`.
- `core/token_budget.py` — `estimate_tokens()` and `pack_within_budget()` implemented.
- `core/tests/test_context_engine.py` — 4 tests, all passing:
  - Build context for a known query — output contains expected memory.
  - Token budget truncation — fewer memories returned when budget is tight.
  - Repo filter — only memories from specified repo appear.
  - All three format modes ("raw", "claude", "markdown") produce valid structured output.

**File:** `core/context_engine.py`

This is the bridge between DevMemoryIndex and AI agents. It converts ranked memories into a token-budget-aware, formatted context block.

```python
from core.memory_store import MemoryStore
from core.embeddings import embed
from core.token_budget import estimate_tokens, pack_within_budget

class ContextEngine:

    def __init__(self, store: MemoryStore):
        self.store = store

    def build(
        self,
        query: str,
        vector: list | None = None,
        repo: str | None = None,
        max_tokens: int = 4000,
        max_memories: int = 10,
        format: str = "raw",  # "raw" | "claude" | "markdown"
    ) -> dict:
        if vector is None:
            vector = embed(query)

        # 1. Hybrid search for candidates
        candidates = self.store.hybrid_search(query, vector, k=max_memories * 3)

        # 2. Optional repo filter
        if repo:
            candidates = [c for c in candidates if c.get("repo") == repo]

        # 3. Deduplicate near-identical summaries
        candidates = self._deduplicate(candidates)

        # 4. Pack within token budget (uses core.token_budget)
        selected, token_count = pack_within_budget(
            candidates, max_tokens=max_tokens, max_items=max_memories
        )

        # 5. Format output
        context_text = self._format(selected, format)

        return {
            "query": query,
            "memories": selected,
            "context_text": context_text,
            "token_estimate": token_count,
            "memory_count": len(selected),
        }

    def _deduplicate(self, memories: list, threshold: float = 0.9) -> list:
        seen = set()
        unique = []
        for m in memories:
            key = m["summary"][:100].lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(m)
        return unique

    def _format(self, memories: list, fmt: str) -> str:
        if fmt == "claude":
            header = "<context>\n"
            body = "\n".join(
                f"- [{m.get('type', 'memory')}] {m['summary']} "
                f"(repo: {m.get('repo', 'N/A')}, importance: {m.get('importance', 0.5):.1f})"
                for m in memories
            )
            return header + body + "\n</context>"

        if fmt == "markdown":
            lines = ["### Relevant Past Solutions\n"]
            for m in memories:
                lines.append(
                    f"- **[{m.get('type', '')}]** {m['summary']}  \n"
                    f"  Repo: {m.get('repo', 'N/A')} | "
                    f"Importance: {m.get('importance', 0.5):.1f}"
                )
            return "\n".join(lines)

        # raw
        return "\n\n".join(m["summary"] for m in memories)
```

**File:** `core/token_budget.py` — token estimation and budget packing, imported by `ContextEngine.build()`, `cli/commands/context.py`, and `api/routes/context.py`.

```python
METADATA_OVERHEAD = 20  # tokens for type/repo/importance labels per memory

def estimate_tokens(text: str) -> int:
    """Rough token estimate (~1 token per whitespace-delimited word)."""
    return len(text.split())

def pack_within_budget(
    memories: list[dict],
    max_tokens: int = 4000,
    max_items: int = 10,
    text_key: str = "summary",
) -> tuple[list[dict], int]:
    """Select memories that fit within a token budget.

    Returns (selected_memories, total_token_count).
    """
    selected = []
    token_count = 0
    for mem in memories:
        est = estimate_tokens(mem.get(text_key, "")) + METADATA_OVERHEAD
        if token_count + est > max_tokens:
            break
        selected.append(mem)
        token_count += est
        if len(selected) >= max_items:
            break
    return selected, token_count
```

**Used by:**
- `core/context_engine.py` — `pack_within_budget()` in `build()` to select memories that fit the token limit.
- `cli/commands/context.py` — `estimate_tokens()` available for displaying accurate estimates in `--json` output.
- `api/routes/context.py` — same pipeline via `ContextEngine`.

**Implementation summary:**
- `core/context_engine.py` — `ContextEngine.build()` implemented: hybrid search → repo filter → `_deduplicate()` (prefix key on first 100 chars) → `pack_within_budget()` → `_format()`. Returns dict with `query`, `memories`, `context_text`, `token_estimate`, `memory_count`.
- `core/token_budget.py` — `estimate_tokens()` (word count) and `pack_within_budget()` implemented. `METADATA_OVERHEAD = 20` tokens per memory.

**Tests:** `core/tests/test_context_engine.py` — 4 tests, all passing:
- Build context for a known query — output contains expected memory.
- Token budget truncation — fewer memories returned when budget is tight.
- Repo filter — only memories from specified repo appear.
- Each format mode ("raw", "claude", "markdown") produces valid output.

---

### 1.7 Content Hashing for Incremental Indexing ✅

**Status: COMPLETED** — `store.exists()` implemented in `core/memory_store.py`. Connectors can now deduplicate before inserting.

**Why:** Without this, re-running connectors re-embeds everything, which is slow and creates duplicates.

**Add to `MemoryStore`:**

```python
def exists(self, memory_id: str) -> bool:
    try:
        results = self.collection.search().where(f"id = '{memory_id}'").limit(1).to_list()
        return len(results) > 0
    except Exception:
        return False
```

**Convention:** All connectors generate `id = sha256(raw_text + source)`. Before calling `store.add()`, call `store.exists(id)` first. Skip if exists.

**Done when:** Running `ingest` twice produces no duplicates.

---

### 1.8 Privacy / Redaction Filter ✅

**Status: COMPLETED** — `core/privacy.py` implemented and hooked into `connectors/base.py`. 4 tests passing.

**Why:** Connectors ingest raw text from history files, code, and notes. Without redaction, secrets (API keys, tokens, passwords) and PII can be stored in plaintext inside LanceDB.

**File:** `core/privacy.py`

```python
import re

# Patterns that must never be stored in raw_text
_BLOCKLIST = [
    re.compile(r'(?i)(api[_-]?key|token|password|secret|passwd)\s*[:=]\s*\S+'),
    re.compile(r'(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*'),
    re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'),          # long base64 blobs (JWT, keys)
    re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),              # US SSN
    re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),  # email
]

_REDACT_PLACEHOLDER = "[REDACTED]"

def redact(text: str) -> str:
    """Replace sensitive patterns with [REDACTED]. Returns cleaned text."""
    for pattern in _BLOCKLIST:
        text = pattern.sub(_REDACT_PLACEHOLDER, text)
    return text
```

**Hook into connector base class** (`connectors/base.py`): call `redact(raw_text)` on the `Memory.raw_text` field before passing to `store.add()`:

```python
from core.privacy import redact

# Inside Connector.collect() — wrap raw_text before creating Memory:
memory = Memory(
    ...
    raw_text=redact(raw_text),
    ...
)
```

**Tests:** `core/tests/test_privacy.py`
- Verify API key patterns are replaced with `[REDACTED]`.
- Verify bearer tokens are stripped.
- Verify clean text is returned unchanged.
- Verify the redaction is applied end-to-end when a connector stores a memory.

**Done when:** A history file containing `export API_KEY=abc123` produces a memory with `[REDACTED]` instead of the key value.

---

## Phase 2 — Connectors (Memory Ingestion)

> **Status: IN PROGRESS** — Voice connector (2.9) done. Base class and registry scaffolded. Remaining connectors (git, terminal, filesystem, markdown, claude, copilot, browser) are next. Phase 1.7 (`store.exists()`) complete — connectors can now deduplicate.
>
> **Goal:** DevMemoryIndex automatically captures developer knowledge from
> six sources. Each connector inherits from a base class, creates Memory objects,
> embeds them, and saves them through MemoryStore.

### 2.1 Connector Base Class ✅

**Status: COMPLETED**

**File:** `connectors/base.py`

```python
from abc import ABC, abstractmethod
from core.store_provider import get_store
from core.memory_store import MemoryStore

class Connector(ABC):
    name: str = "base"

    def __init__(self):
        self.store: MemoryStore = get_store()

    @abstractmethod
    def collect(self) -> int:
        """Ingest memories. Return count of new memories added."""
        ...
```

**Done when:** All connectors inherit this and call `self.store.add()`.

---

### 2.2 Connector Registry ✅

**Status: COMPLETED** — Registry scaffolded with `get_connectors()` and `ALL_CONNECTORS` list. Connectors will be added as they are implemented in 2.3–2.10.

**File:** `connectors/registry.py`

```python
from connectors.git_connector import GitConnector
from connectors.terminal_connector import TerminalConnector
from connectors.filesystem_connector import FilesystemConnector
from connectors.markdown_connector import MarkdownConnector
from connectors.claude_connector import ClaudeConnector
from connectors.copilot_connector import CopilotConnector
from connectors.voice_connector import VoiceConnector
from connectors.browser_connector import BrowserConnector

# VoiceConnector intentionally excluded from ALL_CONNECTORS.
# It is triggered only by explicit user commands:
#   devmemory dictate
#   devmemory search --voice
# Running it on a schedule records silence, noise, and other people's speech.
ALL_CONNECTORS = [
    GitConnector,
    TerminalConnector,
    FilesystemConnector,
    MarkdownConnector,
    ClaudeConnector,
    CopilotConnector,
    # VoiceConnector — NOT here. Use VoiceConnector() directly in CLI commands.
    BrowserConnector,
]

# For explicit CLI use only (devmemory dictate, devmemory search --voice)
VOICE_ONLY_CONNECTORS = [VoiceConnector]

def get_connectors(names: list[str] | None = None) -> list:
    if names is None:
        return [C() for C in ALL_CONNECTORS]
    return [C() for C in ALL_CONNECTORS if C.name in names]
```

**Done when:** `get_connectors()` returns instantiated connector list. `get_connectors(["git"])` returns only GitConnector. VoiceConnector is not included in daemon runs.

---

### 2.3 Git Connector ✅

**Status: COMPLETED** — `connectors/git_connector.py` implemented. 3 tests passing. Wired into registry.

**Post-launch fixes:**
- Commit body (bullet points) now fetched via `git log -1 --format=%b` and stored in `raw_text`. Previously only the subject line was stored, causing body content to be unsearchable.
- Embedding now built from `subject + body` (up to 512 chars) rather than just the subject, so all bullet-point content is captured in the vector.
- `docs` commit importance raised from 0.3 → 0.5 (the `docs:` prefix is a conventional label, not an indicator of low significance).
- `scripts/reset_importance.py` added to clamp drifted importance values back to 0.8.

**File:** `connectors/git_connector.py`

**Purpose:** Capture commit messages, diff summaries, and timestamps as searchable developer decisions.

```python
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from core.schema import Memory
from core.embeddings import embed
from connectors.base import Connector

class GitConnector(Connector):
    name = "git"

    def __init__(self, repo_paths: list[str] | None = None):
        super().__init__()
        self.repo_paths = repo_paths or ["."]

    def collect(self) -> int:
        count = 0
        for repo_path in self.repo_paths:
            count += self._index_repo(repo_path)
        return count

    def _index_repo(self, path: str) -> int:
        count = 0
        result = subprocess.run(
            ["git", "-C", path, "log",
             "--pretty=format:%H|%s|%an|%ct",
             "-n", "100"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return 0

        repo_name = Path(path).resolve().name

        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            sha, msg, author, ts = parts

            mem_id = hashlib.sha256(
                (sha + repo_name).encode()
            ).hexdigest()

            if self.store.exists(mem_id):
                continue

            # Get diff stat for richer context
            diff_result = subprocess.run(
                ["git", "-C", path, "diff", "--stat", f"{sha}~1", sha],
                capture_output=True, text=True
            )
            diff_summary = diff_result.stdout.strip()[:500] if diff_result.returncode == 0 else ""

            raw_text = f"{msg}\n\nAuthor: {author}\nFiles changed:\n{diff_summary}"

            memory = Memory(
                id=mem_id,
                type="git_commit",
                summary=msg[:200],
                raw_text=raw_text,
                source=sha,
                repo=repo_name,
                timestamp=datetime.fromtimestamp(int(ts)),
                tags=["git"],
                importance=self._estimate_importance(msg),
            )

            vector = embed(memory.summary)
            self.store.add(memory, vector)
            count += 1

        return count

    def _estimate_importance(self, message: str) -> float:
        msg_lower = message.lower()
        if any(word in msg_lower for word in ["fix", "bug", "patch", "hotfix"]):
            return 0.9
        if any(word in msg_lower for word in ["feat", "add", "implement"]):
            return 0.7
        if any(word in msg_lower for word in ["refactor", "clean", "rename"]):
            return 0.5
        if any(word in msg_lower for word in ["docs", "readme", "comment"]):
            return 0.3
        return 0.5
```

**Tests:** `connectors/tests/test_git_connector.py`
- Create a temp git repo with 3 commits.
- Run `GitConnector([temp_repo]).collect()`.
- Verify 3 memories stored. Verify deduplication on second run (count == 0).
- Verify bug-fix commits get importance 0.9.

**Done when:** `devmemory ingest --source git` captures real commits from your repos.

---

### 2.4 Terminal History Connector ✅

**File:** `connectors/terminal_connector.py`

**Purpose:** Remember debugging commands, docker invocations, kubectl operations, etc.

```python
import hashlib
import re
from datetime import datetime
from pathlib import Path
from core.schema import Memory
from core.embeddings import embed
from connectors.base import Connector

class TerminalConnector(Connector):
    name = "terminal"

    HISTORY_FILES = [
        Path.home() / ".zsh_history",
        Path.home() / ".bash_history",
    ]

    # Commands too short or generic to be useful
    MIN_CMD_LENGTH = 5
    IGNORE_PREFIXES = ["cd ", "ls", "pwd", "clear", "exit", "echo"]

    def collect(self) -> int:
        count = 0
        for hist_file in self.HISTORY_FILES:
            if hist_file.exists():
                count += self._index_history(hist_file)
        return count

    def _index_history(self, path: Path) -> int:
        count = 0
        lines = path.read_text(errors="ignore").splitlines()

        # Take last 500 unique commands
        seen_cmds = set()
        commands = []
        for line in reversed(lines):
            cmd = self._parse_line(line)
            if cmd and cmd not in seen_cmds and len(cmd) >= self.MIN_CMD_LENGTH:
                if not any(cmd.startswith(p) for p in self.IGNORE_PREFIXES):
                    seen_cmds.add(cmd)
                    commands.append(cmd)
            if len(commands) >= 500:
                break

        for cmd in commands:
            mem_id = hashlib.sha256(cmd.encode()).hexdigest()

            if self.store.exists(mem_id):
                continue

            memory = Memory(
                id=mem_id,
                type="terminal_command",
                summary=cmd[:200],
                raw_text=cmd,
                source=str(path),
                repo=None,
                timestamp=datetime.utcnow(),
                tags=["terminal"],
                importance=self._estimate_importance(cmd),
            )

            vector = embed(memory.summary)
            self.store.add(memory, vector)
            count += 1

        return count

    def _parse_line(self, line: str) -> str | None:
        """Handle zsh extended history format: ': timestamp:0;command'"""
        line = line.strip()
        match = re.match(r'^:\s*\d+:\d+;(.+)$', line)
        if match:
            return match.group(1).strip()
        return line if line else None

    def _estimate_importance(self, cmd: str) -> float:
        cmd_lower = cmd.lower()
        if any(w in cmd_lower for w in ["docker", "kubectl", "terraform", "ansible"]):
            return 0.8
        if any(w in cmd_lower for w in ["git rebase", "git cherry-pick", "git bisect"]):
            return 0.7
        if any(w in cmd_lower for w in ["pip install", "npm install", "brew install"]):
            return 0.6
        return 0.4
```

**Tests:** `connectors/tests/test_terminal_connector.py`
- Create a fake history file in tmp dir.
- Verify parsing of both plain and zsh extended format.
- Verify deduplication and filtering of trivial commands.
- Verify `docker` commands get importance 0.8.

**Done when:** `devmemory ingest --source terminal` captures meaningful shell commands.

---

### 2.5 Filesystem Connector ✅

**File:** `connectors/filesystem_connector.py`

**Purpose:** Index code and documentation files so you can search across your projects.

```python
import hashlib
from datetime import datetime
from pathlib import Path
from core.schema import Memory
from core.embeddings import embed
from connectors.base import Connector

class FilesystemConnector(Connector):
    name = "filesystem"

    EXTENSIONS = {".py", ".ts", ".js", ".md", ".json", ".yaml", ".yml", ".toml", ".sh"}
    MAX_FILE_SIZE = 50_000  # bytes — skip huge files
    CHUNK_SIZE = 500  # characters per chunk

    def __init__(self, scan_paths: list[str] | None = None):
        super().__init__()
        self.scan_paths = scan_paths or ["."]

    def collect(self) -> int:
        count = 0
        for scan_path in self.scan_paths:
            for file in Path(scan_path).rglob("*"):
                if (
                    file.is_file()
                    and file.suffix in self.EXTENSIONS
                    and file.stat().st_size < self.MAX_FILE_SIZE
                    and ".git" not in file.parts
                    and "__pycache__" not in file.parts
                    and "node_modules" not in file.parts
                ):
                    count += self._index_file(file)
        return count

    def _index_file(self, path: Path) -> int:
        count = 0
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            return 0

        chunks = self._chunk(text)
        repo_name = self._detect_repo(path)

        for i, chunk in enumerate(chunks):
            raw = chunk.strip()
            if len(raw) < 20:
                continue

            mem_id = hashlib.sha256(
                (str(path) + str(i) + raw[:100]).encode()
            ).hexdigest()

            if self.store.exists(mem_id):
                continue

            memory = Memory(
                id=mem_id,
                type="file_content",
                summary=f"{path.name}: {raw[:150]}",
                raw_text=raw,
                source=str(path),
                repo=repo_name,
                timestamp=datetime.fromtimestamp(path.stat().st_mtime),
                tags=["file", path.suffix.lstrip(".")],
                importance=0.5,
            )

            vector = embed(memory.summary)
            self.store.add(memory, vector)
            count += 1

        return count

    def _chunk(self, text: str) -> list[str]:
        chunks = []
        for i in range(0, len(text), self.CHUNK_SIZE):
            chunks.append(text[i:i + self.CHUNK_SIZE])
        return chunks

    def _detect_repo(self, path: Path) -> str | None:
        for parent in path.parents:
            if (parent / ".git").exists():
                return parent.name
        return None
```

**Tests:** `connectors/tests/test_filesystem_connector.py`
- Create temp directory with sample .py and .md files.
- Run connector, verify memories created per chunk.
- Verify .git and __pycache__ are excluded.

**Done when:** Running ingest on your project dir makes all Python and Markdown files searchable.

---

### 2.6 Markdown / Notes Connector ✅

**File:** `connectors/markdown_connector.py`

**Purpose:** Separately index personal knowledge directories (Obsidian vaults, ~/notes, etc.) with higher importance than generic code files.

```python
import hashlib
from datetime import datetime
from pathlib import Path
from core.schema import Memory
from core.embeddings import embed
from connectors.base import Connector

class MarkdownConnector(Connector):
    name = "markdown"

    DEFAULT_PATHS = [
        Path.home() / "notes",
        Path.home() / "obsidian",
        Path.home() / "knowledge",
        Path.home() / "Documents" / "notes",
    ]

    def __init__(self, note_paths: list[str] | None = None):
        super().__init__()
        self.note_paths = (
            [Path(p) for p in note_paths]
            if note_paths
            else self.DEFAULT_PATHS
        )

    def collect(self) -> int:
        count = 0
        for base in self.note_paths:
            if not base.exists():
                continue
            for md_file in base.rglob("*.md"):
                count += self._index_note(md_file)
        return count

    def _index_note(self, path: Path) -> int:
        count = 0
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            return 0

        # Split by headings for better semantic chunks
        sections = self._split_by_headings(text)

        for i, section in enumerate(sections):
            if len(section.strip()) < 30:
                continue

            mem_id = hashlib.sha256(
                (str(path) + str(i) + section[:100]).encode()
            ).hexdigest()

            if self.store.exists(mem_id):
                continue

            memory = Memory(
                id=mem_id,
                type="note",
                summary=f"{path.stem}: {section[:150]}",
                raw_text=section,
                source=str(path),
                repo=None,
                timestamp=datetime.fromtimestamp(path.stat().st_mtime),
                tags=["note", "markdown"],
                importance=0.7,  # Notes are intentional knowledge — higher importance
            )

            vector = embed(memory.summary)
            self.store.add(memory, vector)
            count += 1

        return count

    def _split_by_headings(self, text: str) -> list[str]:
        """Split markdown by headings (# lines). Each section includes its heading."""
        import re
        parts = re.split(r'(?=^#{1,3}\s)', text, flags=re.MULTILINE)
        return [p for p in parts if p.strip()]
```

**Tests:** Create a temp notes dir with markdown files containing headings. Verify each heading section becomes a separate memory. Verify importance = 0.7.

**Done when:** Your Obsidian/notes are searchable via `devmemory search "meeting notes about auth"`.

---

### 2.7 Claude Code Connector ✅

**File:** `connectors/claude_connector.py`

**Purpose:** Index Claude Code conversation logs so past AI solutions become searchable memory.

Claude Code stores conversations in `~/.claude/` and project-level `.claude/` directories.

```python
import hashlib
import json
from datetime import datetime
from pathlib import Path
from core.schema import Memory
from core.embeddings import embed
from connectors.base import Connector

class ClaudeConnector(Connector):
    name = "claude"

    SEARCH_PATHS = [
        Path.home() / ".claude",
    ]

    def collect(self) -> int:
        count = 0
        for base in self.SEARCH_PATHS:
            if not base.exists():
                continue
            # Look for conversation JSON files
            for json_file in base.rglob("*.json"):
                count += self._index_conversation(json_file)
            # Also look for markdown conversation logs
            for md_file in base.rglob("*.md"):
                count += self._index_markdown_log(md_file)
        return count

    def _index_conversation(self, path: Path) -> int:
        count = 0
        try:
            data = json.loads(path.read_text(errors="ignore"))
        except (json.JSONDecodeError, Exception):
            return 0

        messages = data if isinstance(data, list) else data.get("messages", [])

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "")
            content = msg.get("content", "")
            if not content or role != "assistant":
                continue
            if isinstance(content, list):
                content = " ".join(
                    block.get("text", "") for block in content
                    if isinstance(block, dict)
                )

            mem_id = hashlib.sha256(content[:500].encode()).hexdigest()

            if self.store.exists(mem_id):
                continue

            memory = Memory(
                id=mem_id,
                type="agent_solution",
                summary=content[:200],
                raw_text=content[:2000],
                source=str(path),
                repo=None,
                timestamp=datetime.fromtimestamp(path.stat().st_mtime),
                tags=["claude", "agent"],
                importance=0.9,
            )

            vector = embed(memory.summary)
            self.store.add(memory, vector)
            count += 1

        return count

    def _index_markdown_log(self, path: Path) -> int:
        count = 0
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            return 0

        # Split by conversation turns
        sections = text.split("\n---\n")
        for section in sections:
            if len(section.strip()) < 50:
                continue

            mem_id = hashlib.sha256(section[:500].encode()).hexdigest()

            if self.store.exists(mem_id):
                continue

            memory = Memory(
                id=mem_id,
                type="agent_solution",
                summary=section[:200],
                raw_text=section[:2000],
                source=str(path),
                repo=None,
                timestamp=datetime.fromtimestamp(path.stat().st_mtime),
                tags=["claude", "agent"],
                importance=0.9,
            )

            vector = embed(memory.summary)
            self.store.add(memory, vector)
            count += 1

        return count
```

**Actual format (confirmed):** `~/.claude/projects/<project-dir>/<session-uuid>.jsonl`. Each line is one event. Assistant turns: `{"type": "assistant", "message": {"role": "assistant", "content": <str|list>}, "cwd": "...", "timestamp": "..."}`. Content is a plain string or list of `{"type": "text", "text": "..."}` blocks. Repo derived from `cwd`. Only responses >= 150 chars indexed (skips trivial replies). 89 memories indexed on first run.

**Tests:** Create mock JSON/markdown conversation files, run connector, verify assistant messages are stored with importance 0.9.

**Done when:** Past Claude Code solutions appear in `devmemory search "auth middleware"`.

---

### 2.8 Copilot Chat Connector ✅

**File:** `connectors/copilot_connector.py`

**Purpose:** Attempt to capture GitHub Copilot chat history from VSCode's local storage.

**Reality:** Copilot does not expose a public API for reading chat data. This connector is best-effort — it scans VSCode workspace storage for any chat session files it can parse.

```python
import hashlib
import json
from datetime import datetime
from pathlib import Path
from core.schema import Memory
from core.embeddings import embed
from connectors.base import Connector

class CopilotConnector(Connector):
    name = "copilot"

    VSCODE_STORAGE = Path.home() / "Library" / "Application Support" / "Code" / "User"

    def collect(self) -> int:
        count = 0
        workspace_storage = self.VSCODE_STORAGE / "workspaceStorage"
        if not workspace_storage.exists():
            return 0

        # Search for any chat-related JSON files
        for json_file in workspace_storage.rglob("*chat*"):
            if json_file.is_file() and json_file.suffix == ".json":
                count += self._index_chat_file(json_file)

        return count

    def _index_chat_file(self, path: Path) -> int:
        count = 0
        try:
            data = json.loads(path.read_text(errors="ignore"))
        except (json.JSONDecodeError, Exception):
            return 0

        messages = data if isinstance(data, list) else []

        for msg in messages:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", "") or msg.get("text", "")
            if not content or len(content) < 30:
                continue

            mem_id = hashlib.sha256(content[:500].encode()).hexdigest()

            if self.store.exists(mem_id):
                continue

            memory = Memory(
                id=mem_id,
                type="copilot_chat",
                summary=content[:200],
                raw_text=content[:2000],
                source=str(path),
                repo=None,
                timestamp=datetime.fromtimestamp(path.stat().st_mtime),
                tags=["copilot", "agent"],
                importance=0.8,
            )

            vector = embed(memory.summary)
            self.store.add(memory, vector)
            count += 1

        return count
```

**Note:** This connector may capture nothing if Copilot stores data in non-standard formats. It is designed to fail silently and is considered optional.

**Done when:** The connector runs without errors. If it finds data, great. If not, it returns 0 gracefully.

---

### 2.9 Voice Connector ✅

**Status: COMPLETED** — Full implementation working with speaker identification, noise gate, and min-word guards. `devmemory dictate` and `devmemory voice enroll` both working.

**File:** `connectors/voice_connector.py`

**Purpose:** Record microphone audio, transcribe with local Whisper, and store the result as a `voice_note` memory. Called by the daemon on a schedule or manually via `devmemory dictate`.

**Dependencies:** `openai-whisper` (or `faster-whisper`), `sounddevice`, `scipy`

```bash
uv add openai-whisper sounddevice scipy
```

```python
import hashlib
import tempfile
import sounddevice as sd
import scipy.io.wavfile as wav
import whisper
from datetime import datetime
from core.schema import Memory
from core.embeddings import embed
from connectors.base import Connector

class VoiceConnector(Connector):
    name = "voice"

    def __init__(
        self,
        duration: int = 10,
        model_size: str = "base",  # "base" | "small" | "medium"
        repo: str | None = None,
    ):
        super().__init__()
        self.duration = duration
        self.model_size = model_size
        self.repo = repo
        self._model = None  # lazy-loaded

    def _get_model(self):
        if self._model is None:
            self._model = whisper.load_model(self.model_size)
        return self._model

    def collect(self) -> int:
        """Record audio, transcribe, and store as a memory. Returns 1 on success."""
        sample_rate = 16000
        audio = sd.rec(
            self.duration * sample_rate,
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        sd.wait()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav.write(f.name, sample_rate, audio)
            result = self._get_model().transcribe(f.name)

        text = result["text"].strip()
        if not text:
            return 0

        # Guard A — Noise gate: reject mostly-silent recordings
        segments = result.get("segments", [])
        if segments:
            avg_no_speech = sum(s.get("no_speech_prob", 0.0) for s in segments) / len(segments)
            if avg_no_speech > 0.6:
                return 0  # Mostly silence or background noise — discard

        # Guard A — Minimum word count gate (Whisper can hallucinate short phrases from noise)
        if len(text.split()) < 4:
            return 0

        # Guard B — Speaker identity check (enrolled profile gate)
        from core.speaker_profile import PROFILE_PATH, load_profile, is_self

        if PROFILE_PATH.exists():
            profile = load_profile()
            seg_emb = self._extract_speaker_embedding(f.name)
            if seg_emb is not None and not is_self(seg_emb, profile, threshold=0.3):
                mem_type = "voice_ambient"
                importance = 0.3
                tags = ["voice", "ambient"]
            else:
                mem_type = "voice_note"
                importance = 0.8
                tags = ["voice"]
        else:
            # No profile enrolled — store as voice_note but flag it
            mem_type = "voice_note"
            importance = 0.8
            tags = ["voice"]

        mem_id = hashlib.sha256((text + "voice").encode()).hexdigest()

        if self.store.exists(mem_id):
            return 0

        memory = Memory(
            id=mem_id,
            type=mem_type,
            summary=text[:200],
            raw_text=text,
            source="voice",
            repo=self.repo,
            timestamp=datetime.utcnow(),
            tags=tags,
            importance=importance,
        )

        self.store.add(memory, embed(memory.summary))
        return 1

    def _extract_speaker_embedding(self, wav_path: str):
        """Extract speaker embedding using pyannote/embedding. Returns None on failure."""
        try:
            from pyannote.audio import Model, Inference
            model = Model.from_pretrained("pyannote/embedding", use_auth_token=True)
            return Inference(model, window="whole")(wav_path)
        except Exception:
            return None
```

**Model tradeoffs:**

| Model | Size | Notes |
|---|---|---|
| `base` | 74 MB | Fast, good for clear speech |
| `small` | 244 MB | Better for technical terms (library names, CLI flags) |
| `faster-whisper/base` | ~same | Drop-in replacement, ~4× faster, lower memory |

Use `small` for developer dictation — technical vocabulary benefits from the larger model.

**Memory types produced by VoiceConnector:**

| Type | Source | Importance | Tags |
|---|---|---|---|
| `voice_note` | `VoiceConnector` (user identified or no profile enrolled) | 0.8 | `["voice"]` |
| `voice_ambient` | `VoiceConnector` (other speaker detected) | 0.3 | `["voice", "ambient"]` |

**Tests:** `connectors/tests/test_voice_connector.py`
- Mock `sd.rec` and `whisper.load_model` to return a known transcript.
- Verify memory is created with `type="voice_note"`, correct summary, and `source="voice"`.
- Verify `store.exists()` prevents duplicate indexing of identical transcripts.
- Test: silent recording (all segments have `no_speech_prob > 0.6`) → `collect()` returns 0, no memory stored.
- Test: short transcript (< 4 words after strip) → `collect()` returns 0.
- Test: enrolled profile present, `_extract_speaker_embedding` returns non-matching embedding → stores `voice_ambient` at `importance=0.3` with `tags=["voice", "ambient"]`.
- Test: enrolled profile present, `_extract_speaker_embedding` returns matching embedding → stores `voice_note` at `importance=0.8`.
- Test: no profile enrolled (`PROFILE_PATH` does not exist) → stores `voice_note` at `importance=0.8`.

**Done when:** `devmemory dictate` records, transcribes, and indexes speech. `devmemory search "redis timeout"` finds a memory that was spoken, not typed.

---

### 2.9b Meeting Connector + Speaker Identification ✅

**Status: Complete** — `connectors/meeting_connector.py`, `core/speaker_profile.py`, and `cli/commands/enroll.py` all done.

**Files:**
- `connectors/meeting_connector.py` — transcribes audio via Whisper, optional pyannote diarization, stores `meeting_transcript` memories ✅
- `core/speaker_profile.py` — enroll your voice once; load profile; cosine-similarity identification ✅
- `cli/commands/enroll.py` — `devmemory voice enroll` ✅

**Purpose:** Auto-index audio from recorded work meetings (Zoom, Teams, Google Meet local exports). Segments the audio by speaker turn, identifies which speaker is *you* using a stored voiceprint, and stores two classes of memory:
- `meeting_self` — things **you** said (higher importance, fully indexed)
- `meeting_context` — things **others** said (lower importance, available for search context)

This is a companion to `VoiceConnector` (live dictation). `MeetingConnector` operates on existing files, not live mic input.

---

**Dependencies:**

```bash
uv add pyannote.audio faster-whisper scipy huggingface_hub
```

| Library | Role |
|---|---|
| `pyannote.audio 3.x` | Speaker diarization + per-segment speaker embeddings |
| `faster-whisper` | Transcription with word-level timestamps (replaces `openai-whisper`) |
| `scipy` | Cosine distance for speaker similarity |
| `huggingface_hub` | Token auth for pyannote model download |

**One-time HuggingFace setup (required for pyannote):**

1. Create a free account at `huggingface.co`
2. Accept the model terms at `hf.co/pyannote/speaker-diarization-3.1` and `hf.co/pyannote/segmentation-3.0`
3. Generate a read token at `hf.co/settings/tokens`
4. Store it locally — pyannote reads it automatically:

```bash
huggingface-cli login
# paste your token when prompted; it saves to ~/.cache/huggingface/token
```

---

**`core/speaker_profile.py`**

```python
import json
import numpy as np
from pathlib import Path
from scipy.spatial.distance import cosine

PROFILE_PATH = Path.home() / ".devmemory" / "speaker_profile.json"

def save_profile(embedding: np.ndarray, path: Path = PROFILE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump({"embedding": embedding.tolist()}, f)

def load_profile(path: Path = PROFILE_PATH) -> np.ndarray:
    with open(path) as f:
        return np.array(json.load(f)["embedding"])

def is_self(segment_embedding: np.ndarray, profile: np.ndarray, threshold: float = 0.25) -> bool:
    """Cosine distance < threshold means same speaker. 0.25 is a practical starting point."""
    return cosine(segment_embedding, profile) < threshold
```

> **Note on threshold:** cosine *distance* (not similarity) — lower = more similar. 0.25 maps to ~cos-sim 0.75. If enrollment is misidentifying you, lower the threshold (stricter). If it's missing you, raise it.

---

**`cli/commands/enroll.py`**

```python
import tempfile
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import typer
from core.speaker_profile import save_profile, PROFILE_PATH

SAMPLE_RATE = 16000
DURATION = 30  # seconds — enough for a robust embedding

def enroll():
    """Record your voice (30s) and save a speaker profile for meeting identification."""
    typer.echo("Recording for 30 seconds. Speak naturally — describe your current project, read some code aloud, etc.")
    typer.echo("Starting in 3...")
    import time; time.sleep(3)

    audio = sd.rec(DURATION * SAMPLE_RATE, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    typer.echo("Recording complete. Extracting voiceprint...")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav.write(f.name, SAMPLE_RATE, audio)
        embedding = _extract_embedding(f.name)

    save_profile(embedding)
    typer.echo(f"Voiceprint saved to {PROFILE_PATH}")
    typer.echo("Run 'devmemory voice enroll' again any time to re-enroll.")

def _extract_embedding(wav_path: str) -> np.ndarray:
    from pyannote.audio import Model, Inference
    model = Model.from_pretrained("pyannote/embedding", use_auth_token=True)
    inference = Inference(model, window="whole")
    return inference(wav_path)
```

---

**`connectors/meeting_connector.py`**

```python
import hashlib
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline, Model, Inference

from connectors.base import Connector
from core.embeddings import embed
from core.schema import Memory
from core.speaker_profile import load_profile, is_self


class MeetingConnector(Connector):
    name = "meeting"

    def __init__(
        self,
        audio_path: str,
        whisper_model: str = "small",
        repo: str | None = None,
        self_threshold: float = 0.25,
    ):
        super().__init__()
        self.audio_path = Path(audio_path)
        self.whisper_model = whisper_model
        self.repo = repo
        self.self_threshold = self_threshold
        self._whisper = None
        self._diarizer = None
        self._embedder = None

    # ── lazy loaders ──────────────────────────────────────────────────────────

    def _get_whisper(self):
        if self._whisper is None:
            self._whisper = WhisperModel(self.whisper_model, device="cpu", compute_type="int8")
        return self._whisper

    def _get_diarizer(self):
        if self._diarizer is None:
            self._diarizer = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1", use_auth_token=True
            )
        return self._diarizer

    def _get_embedder(self):
        if self._embedder is None:
            model = Model.from_pretrained("pyannote/embedding", use_auth_token=True)
            self._embedder = Inference(model, window="whole")
        return self._embedder

    # ── main pipeline ─────────────────────────────────────────────────────────

    def collect(self) -> int:
        profile = load_profile()
        transcription = self._transcribe()           # list of (start, end, text)
        diarization = self._diarize()                # list of (start, end, speaker_label)
        merged = self._merge(transcription, diarization)   # list of (start, end, text, speaker_label)
        return self._store_memories(merged, profile)

    def _transcribe(self) -> list[tuple[float, float, str]]:
        segments, _ = self._get_whisper().transcribe(
            str(self.audio_path), word_timestamps=False
        )
        return [(s.start, s.end, s.text.strip()) for s in segments]

    def _diarize(self) -> list[tuple[float, float, str]]:
        result = self._get_diarizer()(str(self.audio_path))
        return [
            (turn.start, turn.end, speaker)
            for turn, _, speaker in result.itertracks(yield_label=True)
        ]

    def _merge(self, transcript, diarization) -> list[tuple]:
        """Assign each transcript segment to the diarization speaker with max overlap."""
        merged = []
        for t_start, t_end, text in transcript:
            best_speaker, best_overlap = "UNKNOWN", 0.0
            for d_start, d_end, speaker in diarization:
                overlap = max(0.0, min(t_end, d_end) - max(t_start, d_start))
                if overlap > best_overlap:
                    best_overlap, best_speaker = overlap, speaker
            merged.append((t_start, t_end, text, best_speaker))
        return merged

    def _speaker_embedding(self, start: float, end: float) -> np.ndarray | None:
        try:
            from pyannote.core import Segment
            return self._get_embedder().crop(str(self.audio_path), Segment(start, end))
        except Exception:
            return None

    def _store_memories(self, merged: list[tuple], profile: np.ndarray) -> int:
        count = 0
        for start, end, text, speaker_label in merged:
            if not text:
                continue

            seg_emb = self._speaker_embedding(start, end)
            speaker_is_self = seg_emb is not None and is_self(seg_emb, profile, self.self_threshold)

            mem_type = "meeting_self" if speaker_is_self else "meeting_context"
            importance = 0.85 if speaker_is_self else 0.4
            tags = ["meeting", "self"] if speaker_is_self else ["meeting", "participant"]
            source_label = f"meeting:{self.audio_path.name}"

            mem_id = hashlib.sha256(
                (text + source_label + str(round(start, 1))).encode()
            ).hexdigest()

            if self.store.exists(mem_id):
                continue

            memory = Memory(
                id=mem_id,
                type=mem_type,
                summary=text[:200],
                raw_text=text,
                source=source_label,
                repo=self.repo,
                timestamp=datetime.utcnow(),
                tags=tags,
                importance=importance,
            )
            self.store.add(memory, embed(memory.summary))
            count += 1
        return count
```

**Register the `ingest` command to support `--source meeting`:**

```bash
devmemory ingest --source meeting /path/to/recording.mp4
# or with options:
devmemory ingest --source meeting ~/Zoom/2026-02-26.mp4 --repo my-project --whisper-model small
```

**Register `voice enroll` in CLI:**

```python
# cli/commands/enroll.py registers under a `voice` sub-app in cli/main.py
voice_app = typer.Typer()
voice_app.command("enroll")(enroll)
app.add_typer(voice_app, name="voice")
```

---

**New Memory Types to add to `core/schema.py` docs / type literals:**

| Type | Source | Importance | Tags |
|---|---|---|---|
| `meeting_self` | `MeetingConnector` | 0.85 | `["meeting", "self"]` |
| `meeting_context` | `MeetingConnector` | 0.4 | `["meeting", "participant"]` |

---

### Hands-On Testing Steps

These steps use only macOS built-ins (`say`, `ffmpeg`) plus the project dependencies. No real meeting required.

---

#### Step 0 — Prerequisites

```bash
# Confirm ffmpeg is available (install via brew if not)
ffmpeg -version

# Confirm HuggingFace token is stored
cat ~/.cache/huggingface/token   # should print your token

# Install deps
uv add pyannote.audio faster-whisper scipy huggingface_hub
```

---

#### Step 1 — Generate a Synthetic Two-Speaker Meeting

Use macOS `say` with two different voices to simulate you vs. a colleague. This avoids needing a real recording.

```bash
# Voice 1 (you — will enroll this voice as "self")
say -v Alex  "I think we should migrate the auth service to JWT before Q2. The current session cookie approach breaks under horizontal scaling." \
    -o /tmp/speaker_self.aiff

# Voice 2 (colleague)
say -v Samantha "Agreed. The infra team said they need about two weeks to rotate the certificates. We should start the migration doc this week." \
    -o /tmp/speaker_other.aiff

# Convert both to 16kHz mono WAV (Whisper + pyannote requirement)
ffmpeg -y -i /tmp/speaker_self.aiff  -ar 16000 -ac 1 /tmp/self.wav
ffmpeg -y -i /tmp/speaker_other.aiff -ar 16000 -ac 1 /tmp/other.wav

# Add 1-second silence between speakers and concatenate
ffmpeg -y -f lavfi -t 1 -i anullsrc=r=16000:cl=mono /tmp/silence.wav
ffmpeg -y -i "concat:/tmp/self.wav|/tmp/silence.wav|/tmp/other.wav" \
    -ar 16000 -ac 1 /tmp/test_meeting.wav

# Verify: should be ~10–15 seconds
ffprobe -i /tmp/test_meeting.wav -show_entries format=duration -v quiet -of csv=p=0
```

---

#### Step 2 — Enroll Your Voice

Generate a second Alex clip (same voice = "you") to use as the enrollment sample:

```bash
say -v Alex \
  "Hi, this is my enrollment recording. I work on developer tools, mostly Python and TypeScript. \
   I use LanceDB for vector storage and Whisper for speech to text. \
   Our main repo is devmemoryindex and I run tests with pytest." \
  -o /tmp/enroll.aiff

ffmpeg -y -i /tmp/enroll.aiff -ar 16000 -ac 1 /tmp/enroll.wav
```

Then, instead of recording live mic, temporarily call the enrollment embedding path directly in a Python REPL to test it without needing a microphone:

```bash
python - <<'EOF'
from core.speaker_profile import save_profile
from cli.commands.enroll import _extract_embedding

emb = _extract_embedding("/tmp/enroll.wav")
save_profile(emb)
print(f"Profile saved. Embedding shape: {emb.shape}")
EOF
```

Expected output: `Profile saved. Embedding shape: (512,)` (or 192, depending on pyannote model version).

---

#### Step 3 — Manually Test Speaker Identification

Before running the full connector, verify that the self-vs-other cosine distance logic works on your synthetic clips:

```bash
python - <<'EOF'
import numpy as np
from pyannote.audio import Model, Inference
from core.speaker_profile import load_profile, is_self
from pyannote.core import Segment

model = Model.from_pretrained("pyannote/embedding", use_auth_token=True)
inf = Inference(model, window="whole")

profile = load_profile()

# Same voice as enrollment — should be "self"
self_emb = inf("/tmp/self.wav")
other_emb = inf("/tmp/other.wav")

from scipy.spatial.distance import cosine
print(f"Self distance:  {cosine(self_emb, profile):.4f}  → is_self={is_self(self_emb, profile)}")
print(f"Other distance: {cosine(other_emb, profile):.4f}  → is_self={is_self(other_emb, profile)}")
EOF
```

Expected:
```
Self distance:  0.08–0.18  → is_self=True
Other distance: 0.40–0.70  → is_self=False
```

If self-distance is above 0.25, adjust `threshold` in `speaker_profile.py`. If other-distance is below 0.25, lower the threshold. The gap between the two values is your margin.

---

#### Step 4 — Run the Full Meeting Connector

```bash
python - <<'EOF'
from connectors.meeting_connector import MeetingConnector

conn = MeetingConnector(
    audio_path="/tmp/test_meeting.wav",
    whisper_model="small",
    repo="devmemoryindex",
)
n = conn.collect()
print(f"Indexed {n} memories from meeting.")
EOF
```

Expected: `Indexed 2 memories from meeting.` (one `meeting_self`, one `meeting_context`).

---

#### Step 5 — Verify in CLI

```bash
# Should surface the JWT/auth content you "said"
devmemory search "auth migration JWT"

# Check that types are correct
devmemory search "auth" --type meeting_self
devmemory search "certificates" --type meeting_context

# Stats should show both new types
devmemory stats
```

Expected in stats output:

```
meeting_self       1
meeting_context    1
```

---

#### Step 6 — Run Unit Tests

**`connectors/tests/test_meeting_connector.py`**

```python
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from connectors.meeting_connector import MeetingConnector

FAKE_TRANSCRIPT = [(0.0, 5.0, "We should migrate auth to JWT.")]
FAKE_DIARIZATION = [(0.0, 5.0, "SPEAKER_00")]
FAKE_PROFILE = np.ones(512) / np.linalg.norm(np.ones(512))
SELF_EMB   = FAKE_PROFILE.copy()          # cosine distance ≈ 0 → is_self=True
OTHER_EMB  = -FAKE_PROFILE.copy()         # cosine distance ≈ 2 → is_self=False

@pytest.fixture
def connector(tmp_path):
    conn = MeetingConnector(audio_path=str(tmp_path / "meeting.wav"), repo="test")
    conn.store = MagicMock()
    conn.store.exists.return_value = False
    return conn

def test_self_segment_stored_as_meeting_self(connector):
    with patch.object(connector, "_transcribe", return_value=FAKE_TRANSCRIPT), \
         patch.object(connector, "_diarize",    return_value=FAKE_DIARIZATION), \
         patch.object(connector, "_speaker_embedding", return_value=SELF_EMB), \
         patch("connectors.meeting_connector.load_profile", return_value=FAKE_PROFILE):
        count = connector.collect()

    assert count == 1
    stored = connector.store.add.call_args[0][0]
    assert stored.type == "meeting_self"
    assert stored.importance == 0.85
    assert "self" in stored.tags

def test_other_segment_stored_as_meeting_context(connector):
    with patch.object(connector, "_transcribe", return_value=FAKE_TRANSCRIPT), \
         patch.object(connector, "_diarize",    return_value=FAKE_DIARIZATION), \
         patch.object(connector, "_speaker_embedding", return_value=OTHER_EMB), \
         patch("connectors.meeting_connector.load_profile", return_value=FAKE_PROFILE):
        count = connector.collect()

    assert count == 1
    stored = connector.store.add.call_args[0][0]
    assert stored.type == "meeting_context"
    assert stored.importance == 0.4
    assert "participant" in stored.tags

def test_duplicate_segment_skipped(connector):
    connector.store.exists.return_value = True
    with patch.object(connector, "_transcribe", return_value=FAKE_TRANSCRIPT), \
         patch.object(connector, "_diarize",    return_value=FAKE_DIARIZATION), \
         patch.object(connector, "_speaker_embedding", return_value=SELF_EMB), \
         patch("connectors.meeting_connector.load_profile", return_value=FAKE_PROFILE):
        count = connector.collect()

    assert count == 0
    connector.store.add.assert_not_called()

def test_empty_transcript_segment_skipped(connector):
    with patch.object(connector, "_transcribe", return_value=[(0.0, 2.0, "")]), \
         patch.object(connector, "_diarize",    return_value=FAKE_DIARIZATION), \
         patch("connectors.meeting_connector.load_profile", return_value=FAKE_PROFILE):
        count = connector.collect()

    assert count == 0
```

Run them:

```bash
pytest connectors/tests/test_meeting_connector.py -v
```

Expected: **4 passed**.

---

**`core/tests/test_speaker_profile.py`**

```python
import numpy as np
import pytest
from core.speaker_profile import save_profile, load_profile, is_self

def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "profile.json"
    emb = np.random.rand(512).astype(np.float32)
    save_profile(emb, path)
    loaded = load_profile(path)
    np.testing.assert_allclose(emb, loaded, rtol=1e-5)

def test_is_self_identical_embedding():
    emb = np.ones(512)
    assert is_self(emb, emb, threshold=0.25) is True

def test_is_self_orthogonal_embedding():
    a = np.zeros(512); a[0] = 1.0
    b = np.zeros(512); b[1] = 1.0
    assert is_self(a, b, threshold=0.25) is False

def test_is_self_threshold_boundary():
    # distance exactly at threshold should NOT be self (strict <)
    from scipy.spatial.distance import cosine
    a = np.ones(512)
    # craft b so cosine(a, b) = 0.25 exactly
    b = a.copy()
    b[0] -= 1.5
    b /= np.linalg.norm(b)
    dist = cosine(a / np.linalg.norm(a), b)
    result = is_self(a / np.linalg.norm(a), b, threshold=round(dist, 6))
    assert result is False
```

Run them:

```bash
pytest core/tests/test_speaker_profile.py -v
```

Expected: **4 passed**.

---

**Model tradeoffs:**

| Diarization model | Accuracy | GPU required | Notes |
|---|---|---|---|
| `pyannote/speaker-diarization-3.1` | High | No (slow on CPU) | Best quality; recommended |
| `resemblyzer` + `simple_diarizer` | Medium | No | No HuggingFace token needed; faster setup |

If you want to avoid the HuggingFace token requirement entirely during development, `resemblyzer` is a drop-in swap for the embedding + diarization steps — swap it in `meeting_connector.py` and `speaker_profile.py` only.

---

**Future daemon integration:**

```python
# daemon/jobs/meeting_watcher.py
# Watch ~/Zoom, ~/Downloads for *.mp4 / *.m4a, auto-ingest new files
WATCH_DIRS = [Path.home() / "Zoom", Path.home() / "Downloads"]
EXTENSIONS = {".mp4", ".m4a", ".wav", ".mp3"}
```

**Done when:**
- `devmemory voice enroll` saves a voiceprint without error.
- `devmemory ingest --source meeting /tmp/test_meeting.wav` returns "Indexed N memories."
- `devmemory search "JWT auth"` returns the `meeting_self` segment you "spoke" in Step 1.
- `devmemory search "certificates"` returns the `meeting_context` segment from the other speaker.
- All 8 unit tests pass.

---

### 2.10 Browser Bookmarks Connector ✅

**File:** `connectors/browser_connector.py`

**Purpose:** Index browser bookmarks (title + URL) so saved research pages are searchable alongside code and notes.

**Supported browsers:**
- **Chrome / Chromium** — reads `~/Library/Application Support/Google/Chrome/Default/Bookmarks` (JSON format)
- **Firefox** — reads `~/Library/Application Support/Firefox/Profiles/*/places.sqlite` (SQLite, `moz_bookmarks` + `moz_places`)

```python
import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from core.schema import Memory
from core.embeddings import embed
from connectors.base import Connector

class BrowserConnector(Connector):
    name = "browser"

    CHROME_PATH = (
        Path.home() / "Library" / "Application Support"
        / "Google" / "Chrome" / "Default" / "Bookmarks"
    )
    FIREFOX_PROFILE_DIR = (
        Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
    )

    def collect(self) -> int:
        count = 0
        count += self._collect_chrome()
        count += self._collect_firefox()
        return count

    # ── Chrome ────────────────────────────────────────────────────────────────

    def _collect_chrome(self) -> int:
        if not self.CHROME_PATH.exists():
            return 0
        try:
            data = json.loads(self.CHROME_PATH.read_text(errors="ignore"))
        except Exception:
            return 0
        count = 0
        for node in self._walk_chrome(data.get("roots", {})):
            count += self._store_bookmark(node["name"], node["url"], "chrome")
        return count

    def _walk_chrome(self, node):
        """Recursively yield bookmark leaf nodes from Chrome JSON."""
        if isinstance(node, dict):
            if node.get("type") == "url":
                yield node
            for child in node.get("children", []):
                yield from self._walk_chrome(child)
            for value in node.values():
                if isinstance(value, dict):
                    yield from self._walk_chrome(value)

    # ── Firefox ───────────────────────────────────────────────────────────────

    def _collect_firefox(self) -> int:
        if not self.FIREFOX_PROFILE_DIR.exists():
            return 0
        count = 0
        for db_path in self.FIREFOX_PROFILE_DIR.glob("*/places.sqlite"):
            count += self._read_firefox_db(db_path)
        return count

    def _read_firefox_db(self, db_path: Path) -> int:
        count = 0
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            rows = con.execute(
                "SELECT p.title, p.url FROM moz_bookmarks b "
                "JOIN moz_places p ON b.fk = p.id "
                "WHERE p.url NOT LIKE 'place:%'"
            ).fetchall()
            con.close()
        except Exception:
            return 0
        for title, url in rows:
            count += self._store_bookmark(title or url, url, "firefox")
        return count

    # ── Shared ────────────────────────────────────────────────────────────────

    def _store_bookmark(self, title: str, url: str, source: str) -> int:
        if not url or not url.startswith("http"):
            return 0
        raw = f"{title}\n{url}"
        mem_id = hashlib.sha256(raw.encode()).hexdigest()
        if self.store.exists(mem_id):
            return 0
        memory = Memory(
            id=mem_id,
            type="bookmark",
            summary=f"{title}: {url}"[:200],
            raw_text=raw,
            source=source,
            repo=None,
            timestamp=datetime.utcnow(),
            tags=["bookmark", source],
            importance=0.6,
        )
        self.store.add(memory, embed(memory.summary))
        return 1
```

**Tests:** `connectors/tests/test_browser_connector.py`
- Provide a sample Chrome Bookmarks JSON file in a temp dir and verify leaf nodes are stored as `type="bookmark"`.
- Provide a minimal Firefox `places.sqlite` with one row and verify it is indexed.
- Verify `importance = 0.6` on all stored memories.
- Verify deduplication: running the connector twice inserts zero new entries the second time.

**Done when:** `devmemory ingest --source browser` indexes your Chrome and Firefox bookmarks. `devmemory search "rust async"` surfaces a saved MDN or blog page.

---

## Phase 3 — CLI Completions (Human Interface)

> **Status: COMPLETE** — All commands done: `search` (inc. `--voice`, `--speak`), `add`, `stats`, `prune`, `dictate`, `voice enroll`, `ingest`, `config`, `context`, `suggest`, `daemon`, `export`, `import`, `repl`.
>
> **Revised subphase structure:**
> - **3.A** — `devmemory context`: wrap `ContextEngine.build()` as CLI command. Zero new architecture.
> - **3.B** — `devmemory suggest`: `git diff HEAD` → `ContextEngine.build()` → print context. Pulled forward from Phase 6.5 — all deps are done.
> - **3.C** — Enhanced `search --voice`: 8s recording, quality gate (`no_speech_prob`), confirmation display, optional `--speak` flag (macOS `say` / `espeak`).
> - **3.D** — Remaining specced commands: `repl`, `export`/`import`, `daemon`. Defer: `tag`, `pin`, `audit`.
>
> **`devmemory suggest` design** (`cli/commands/suggest.py`):
> ```
> devmemory suggest                  # git diff HEAD → ContextEngine → print
> devmemory suggest --staged         # git diff --cached
> devmemory suggest --format claude  # wrap in <context> tags
> devmemory suggest --copy           # also pipe to clipboard
> devmemory suggest --repo myapp     # filter context to one repo
> ```
> Falls back to `git log -5 --pretty=%s` if no diff exists.
>
> **When and why to use `suggest`:**
> The key difference from `devmemory context` is **no query required**. Instead of
> asking "what do I need?", you run `suggest` mid-feature and it infers what's
> relevant from your current working tree changes.
>
> Typical workflow:
> 1. You're mid-feature, hit a wall, or are about to write something non-trivial
> 2. Run `devmemory suggest` — no typing a query
> 3. It reads your current diff, extracts changed file names + added lines as a query
> 4. Surfaces past solutions, prior decisions, bugs you've hit in similar files
>
> It gets more useful as more connectors feed data in (git history, terminal,
> markdown notes). With only the git connector active, results are sparse until
> a meaningful commit history is indexed. Once terminal + markdown connectors
> exist, `suggest` becomes a zero-friction "what do I already know about this?"
> before writing new code.
>
> **Enhanced voice search design** (`cli/commands/search.py`):
> 1. Show "Listening..." with countdown
> 2. Record 8s (not 5s — natural queries take longer)
> 3. Quality gate: if avg `no_speech_prob > 0.5` → print "Could not understand" and exit
> 4. **Confirmation step**: print `Searching for: "<transcribed text>"` before results appear
> 5. Run `classify_intent()` (after Phase 5.A) to route query type
> 6. Show results table as normal
> 7. `--speak` flag: `say results[0]["summary"][:100]` for full voice loop (no cloud TTS)
>
> **Goal:** A developer can operate DevMemoryIndex entirely from the terminal,
> like using `git` — no Python scripts needed.
>
> The CLI is built **incrementally across phases**, not all at once:
>
> | Command | Earliest Phase | Why |
> |---|---|---|
> | `devmemory search` | Phase 1 | Only needs `MemoryStore` + `embed()` |
> | `devmemory search --voice` | Phase 2.9 | Needs `VoiceConnector` transcription |
> | `devmemory add` | Phase 1 | Only needs `MemoryStore` + `embed()` |
> | `devmemory stats` | Phase 1 | Only needs `MemoryStore` |
> | `devmemory context` | Phase 1 (after 1.6) | Needs `ContextEngine` |
> | `devmemory ingest` | Phase 2 | Needs connectors |
> | `devmemory dictate` | Phase 2.9 | Needs `VoiceConnector` |
> | `devmemory daemon` | Phase 5 | Needs `daemon/scheduler.py` |
> | `devmemory tag` | Phase 1 | Needs `MemoryStore` + schema `tags` field |
> | `devmemory pin` | Phase 1 | Needs schema `pinned` field |
> | `devmemory export` | Phase 1 | Needs `store.get_all()` |
> | `devmemory import` | Phase 1 | Needs `store.add()` |
> | `devmemory audit` | Phase 1.5 | Needs hybrid search for near-duplicate detection |
> | `devmemory repl` | Phase 1 | Needs `MemoryStore` + `embed()` |
>
> The entrypoint (`cli/main.py`) and first three commands are scaffolded in
> **Phase 1.3**. The remaining commands are added here as their dependencies
> become available.

**Dependencies:** `typer`, `rich` (for pretty output)

### 3.1 Early Commands — `search`, `add`, `stats`

> **Already fully specified in Phase 1.3** — including all file contents, directory setup, and verification steps. No additional work needed here. Refer to Phase 1.3 for the complete implementation.

---

### 3.2 Late Commands (Available After Their Dependencies)

These commands are **registered in `cli/main.py` only after** the phases they depend on are implemented. Expand the entrypoint as each one lands:

```python
# Add to cli/main.py after Phase 1.6 (context engine)
from cli.commands.context import context
app.command()(context)

# Add to cli/main.py after Phase 2 (connectors)
from cli.commands.ingest import ingest
app.command()(ingest)

# Add to cli/main.py after Phase 5 (daemon)
from cli.commands.daemon_cmd import daemon
app.command()(daemon)
```

#### 3.2a Ingest Command (Requires Phase 2 — Connectors)

**File:** `cli/commands/ingest.py`

```python
import typer
from rich.console import Console
from connectors.registry import get_connectors

console = Console()

def ingest(
    source: str | None = typer.Option(None, "--source", "-s",
        help="Specific connector: git, terminal, filesystem, markdown, claude, copilot. Omit to run all."),
):
    """Run memory connectors to ingest developer knowledge."""
    if source:
        connectors = get_connectors([source])
    else:
        connectors = get_connectors()

    if not connectors:
        console.print(f"[red]Unknown source: {source}[/red]")
        raise typer.Exit(1)

    total = 0
    for c in connectors:
        console.print(f"[cyan]Running {c.name} connector...[/cyan]")
        count = c.collect()
        console.print(f"  → {count} new memories")
        total += count

    console.print(f"\n[green]Ingestion complete. {total} new memories added.[/green]")
```

**Done when:** `devmemory ingest` runs all connectors. `devmemory ingest --source git` runs only git.

---

#### 3.2b Context Command (Requires Phase 1.6 — Context Engine)

**File:** `cli/commands/context.py`

```python
import typer
import json
import subprocess
from rich.console import Console
from core.store_provider import get_store
from core.embeddings import embed
from core.context_engine import ContextEngine

console = Console()

def context(
    query: str = typer.Argument(..., help="What context do you need?"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Filter by repo"),
    tokens: int = typer.Option(4000, "--tokens", help="Max token budget"),
    format: str = typer.Option("markdown", "--format", "-f",
        help="Output format: raw, markdown, claude"),
    as_json: bool = typer.Option(False, "--json", help="Output full JSON response"),
    copy: bool = typer.Option(False, "--copy", help="Copy context to clipboard"),
):
    """Build AI-ready context from your developer memory."""
    store = get_store()
    engine = ContextEngine(store)
    vector = embed(query)

    result = engine.build(
        query=query,
        vector=vector,
        repo=repo,
        max_tokens=tokens,
        format=format,
    )

    if as_json:
        # Strip non-serializable fields for JSON output
        output = {
            "query": result["query"],
            "context_text": result["context_text"],
            "token_estimate": result["token_estimate"],
            "memory_count": result["memory_count"],
        }
        console.print_json(json.dumps(output))
    else:
        console.print(result["context_text"])

    if copy:
        try:
            subprocess.run(
                ["pbcopy"],
                input=result["context_text"].encode(),
                check=True,
            )
            console.print("\n[green]Copied to clipboard.[/green]")
        except Exception:
            console.print("\n[yellow]Could not copy to clipboard.[/yellow]")

    console.print(
        f"\n[dim]{result['memory_count']} memories · "
        f"~{result['token_estimate']} tokens[/dim]"
    )
```

**Done when:**
- `devmemory context "redis timeout"` prints a formatted memory block.
- `devmemory context "auth" --format claude` prints `<context>...</context>` block.
- `devmemory context "docker" --json` prints JSON.
- `devmemory context "deploy" --copy` copies to macOS clipboard.

---

#### 3.2c Daemon Command (Requires Phase 5 — Daemon)

**File:** `cli/commands/daemon_cmd.py`

```python
import typer
from rich.console import Console

console = Console()

def daemon(
    interval: int = typer.Option(300, "--interval", "-i", help="Seconds between indexing runs"),
):
    """Start background memory daemon."""
    from daemon.scheduler import run_daemon
    console.print(f"[green]Starting daemon (interval: {interval}s)...[/green]")
    run_daemon(interval=interval)
```

**Done when:** `devmemory daemon` starts continuous background indexing.

---

#### 3.2d Dictate Command (Requires Phase 2.9 — Voice Connector)

**File:** `cli/commands/dictate.py`

Records microphone audio, transcribes it with Whisper, and stores the result as a `voice_note` memory.

```python
import typer
from rich.console import Console
from connectors.voice_connector import VoiceConnector

console = Console()

def dictate(
    duration: int = typer.Option(10, "--duration", "-d", help="Recording length in seconds"),
    model: str = typer.Option("base", "--model", "-m", help="Whisper model: base, small, medium"),
    repo: str | None = typer.Option(None, "--repo", "-r", help="Associate with a repo"),
    importance: float = typer.Option(0.8, "--importance", "-i"),
):
    """Record your voice and auto-index it as a memory."""
    console.print(f"[cyan]Recording for {duration}s... (speak now)[/cyan]")
    connector = VoiceConnector(duration=duration, model_size=model, repo=repo)
    count = connector.collect()
    if count:
        console.print("[bold green]Memory indexed.[/bold green]")
    else:
        console.print("[yellow]Nothing transcribed or already indexed.[/yellow]")
```

Register in `cli/main.py` after Phase 2.9:
```python
from cli.commands.dictate import dictate
app.command()(dictate)
```

Usage:
```bash
devmemory dictate                          # 10s clip, base model
devmemory dictate --duration 30 --model small --repo myapp
```

**Done when:** Speaking `devmemory dictate` records audio, prints "Memory indexed.", and the transcript is retrievable via `devmemory search`.

---

#### 3.2e Voice Search Flag (Requires Phase 2.9 — Voice Connector)

Adds `--voice` to the existing `devmemory search` command. When set, records a short clip, transcribes it, and passes the text into the normal `hybrid_search()` pipeline — no other changes.

**Edit `cli/commands/search.py`** — add one option and a transcription block at the top of `search()`:

```python
# Add to the function signature:
voice: bool = typer.Option(False, "--voice", "-v", help="Speak your search query"),

# Add at the top of the function body, before embed():
if voice:
    import sounddevice as sd, scipy.io.wavfile as wav, tempfile, whisper
    console.print("[cyan]Listening for query (5s)...[/cyan]")
    sr = 16000
    audio = sd.rec(5 * sr, samplerate=sr, channels=1, dtype="int16")
    sd.wait()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav.write(f.name, sr, audio)
        query = whisper.load_model("base").transcribe(f.name)["text"].strip()
    console.print(f"[green]Query:[/green] {query}")
```

Usage:
```bash
devmemory search --voice         # speak your query → hybrid_search()
```

**Done when:** `devmemory search --voice` transcribes spoken input and returns the same ranked results as a typed query.

---

#### 3.2f Tag Management (Requires Phase 1)

**File:** `cli/commands/tag.py`

Sub-commands via a Typer group:

```python
import typer
from rich.console import Console
from core.store_provider import get_store

app = typer.Typer(help="Manage tags on memories.")
console = Console()

@app.command("add")
def tag_add(memory_id: str = typer.Argument(...), tag: str = typer.Argument(...)):
    """Add a tag to a memory."""
    store = get_store()
    store.add_tag(memory_id, tag)
    console.print(f"[green]Tag '{tag}' added to {memory_id[:8]}[/green]")

@app.command("remove")
def tag_remove(memory_id: str = typer.Argument(...), tag: str = typer.Argument(...)):
    """Remove a tag from a memory."""
    store = get_store()
    store.remove_tag(memory_id, tag)
    console.print(f"[yellow]Tag '{tag}' removed from {memory_id[:8]}[/yellow]")

@app.command("list")
def tag_list(memory_id: str = typer.Argument(...)):
    """List all tags on a memory."""
    store = get_store()
    tags = store.get_tags(memory_id)
    console.print(f"Tags: {', '.join(tags) if tags else '(none)'}")
```

Also add `--tag` filter to `cli/commands/search.py`:

```python
tag: str | None = typer.Option(None, "--tag", help="Filter by tag"),

# In search body, after existing filters:
if tag:
    results = [r for r in results if tag in (r.get("tags") or [])]
```

Register in `cli/main.py`:
```python
from cli.commands.tag import app as tag_app
app.add_typer(tag_app, name="tag")
```

**Done when:** `devmemory tag add <id> important` adds the tag. `devmemory search "redis" --tag important` filters results.

---

#### 3.2g Pin / Unpin (Requires Phase 1 — schema change)

**Schema change** (`core/schema.py`): add `pinned: bool = False` to the `Memory` dataclass and the LanceDB Arrow schema.

**File:** `cli/commands/pin.py`

```python
import typer
from rich.console import Console
from core.store_provider import get_store

console = Console()

def pin(memory_id: str = typer.Argument(..., help="Memory ID to pin")):
    """Pin a memory so it is never decayed."""
    store = get_store()
    store.set_pinned(memory_id, True)
    console.print(f"[green]Pinned {memory_id[:8]}[/green]")

def unpin(memory_id: str = typer.Argument(..., help="Memory ID to unpin")):
    """Unpin a memory (resume importance decay)."""
    store = get_store()
    store.set_pinned(memory_id, False)
    console.print(f"[yellow]Unpinned {memory_id[:8]}[/yellow]")
```

Register in `cli/main.py`:
```python
from cli.commands.pin import pin, unpin
app.command()(pin)
app.command()(unpin)
```

**Done when:** `devmemory pin <id>` marks the memory. Pinned memories are excluded from the importance decay job (see Phase 5.3).

---

#### 3.2h Export / Import (Requires Phase 1)

**File:** `cli/commands/export.py`

```python
import json
import typer
from pathlib import Path
from datetime import datetime
from rich.console import Console
from core.store_provider import get_store
from core.schema import Memory
from core.embeddings import embed

console = Console()

def export(
    output: Path = typer.Argument(..., help="Output JSON file path"),
):
    """Export all memories to a JSON file."""
    store = get_store()
    records = store.get_all()
    data = [dict(r) for r in records]
    output.write_text(json.dumps(data, indent=2, default=str))
    console.print(f"[green]Exported {len(data)} memories → {output}[/green]")

def import_memories(
    input_file: Path = typer.Argument(..., help="JSON file to import"),
):
    """Import memories from a JSON file (skips duplicates)."""
    store = get_store()
    data = json.loads(input_file.read_text())
    added = 0
    for record in data:
        mem_id = record.get("id", "")
        if store.exists(mem_id):
            continue
        memory = Memory(
            id=mem_id,
            type=record.get("type", "agent_solution"),
            summary=record.get("summary", "")[:200],
            raw_text=record.get("raw_text", ""),
            source=record.get("source", "import"),
            repo=record.get("repo"),
            timestamp=datetime.fromisoformat(record["timestamp"]) if record.get("timestamp") else datetime.utcnow(),
            tags=record.get("tags", []),
            importance=record.get("importance", 0.5),
        )
        vector = embed(memory.summary)
        store.add(memory, vector)
        added += 1
    console.print(f"[green]Imported {added} new memories.[/green]")
```

Register in `cli/main.py`:
```python
from cli.commands.export import export, import_memories
app.command(name="export")(export)
app.command(name="import")(import_memories)
```

**Done when:** `devmemory export memories.json` dumps all memories. `devmemory import memories.json` re-imports them on a fresh install without duplicates.

---

#### 3.2i Audit (Requires Phase 1.5 — Hybrid Search)

**File:** `cli/commands/audit.py`

Surfaces memory quality issues: near-duplicates, orphaned sources, never-retrieved memories, and very short entries.

```python
import typer
from rich.console import Console
from rich.table import Table
from core.store_provider import get_store

console = Console()

def audit():
    """Audit memory store for quality issues."""
    store = get_store()
    all_memories = store.get_all()

    issues = []

    # Very short entries (< 20 chars summary)
    short = [m for m in all_memories if len(m.get("summary", "")) < 20]
    for m in short:
        issues.append((m["id"][:8], "short", m.get("summary", "")))

    # Near-duplicates: check for memories with identical first 80 chars of summary
    seen_prefixes = {}
    for m in all_memories:
        prefix = m.get("summary", "")[:80].lower().strip()
        if prefix in seen_prefixes:
            issues.append((m["id"][:8], "near-duplicate", m.get("summary", "")[:60]))
        else:
            seen_prefixes[prefix] = m["id"]

    if not issues:
        console.print("[green]No issues found. Memory store looks healthy.[/green]")
        return

    table = Table(title="Audit Issues")
    table.add_column("ID", style="cyan", width=10)
    table.add_column("Issue", style="yellow", width=16)
    table.add_column("Preview", style="white")
    for mem_id, issue, preview in issues:
        table.add_row(mem_id, issue, preview)
    console.print(table)
```

Register in `cli/main.py`:
```python
from cli.commands.audit import audit
app.command()(audit)
```

**Done when:** `devmemory audit` surfaces duplicate and low-quality memories with actionable IDs.

---

#### 3.2j REPL (Requires Phase 1)

**File:** `cli/commands/repl.py`

A persistent interactive prompt that keeps the embedding model and store loaded between queries — avoids the cold-start latency of repeated `devmemory search` invocations.

```python
import typer
from rich.console import Console
from core.store_provider import get_store
from core.embeddings import embed

console = Console()

def repl():
    """Start an interactive memory search session (model stays loaded)."""
    store = get_store()
    console.print("[bold cyan]DevMemory REPL[/bold cyan] — type a query, or 'exit' to quit.\n")

    while True:
        try:
            query = input("devmemory> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Exiting REPL.[/yellow]")
            break

        if not query:
            continue
        if query.lower() in {"exit", "quit", "q"}:
            console.print("[yellow]Goodbye.[/yellow]")
            break

        vector = embed(query)
        results = store.hybrid_search(query, vector, k=5)

        if not results:
            console.print("[yellow]No results.[/yellow]\n")
            continue

        for i, r in enumerate(results, 1):
            console.print(
                f"[cyan]{i}.[/cyan] [{r.get('type', '')}] "
                f"{r.get('summary', '')[:100]}  "
                f"[dim](importance: {r.get('importance', 0.5):.1f})[/dim]"
            )
        console.print()
```

Register in `cli/main.py`:
```python
from cli.commands.repl import repl
app.command()(repl)
```

**Done when:** `devmemory repl` starts an interactive session. Queries return results without reloading the model each time.

---

#### 3.2k Prune Command (Requires Phase 5.4B — Memory Pruning)

**File:** `cli/commands/prune.py`

```python
import typer
from rich.console import Console
from daemon.jobs.memory_cleanup import prune_memories, PRUNE_IMPORTANCE_FLOOR, PRUNE_MAX_AGE_DAYS

console = Console()

def prune(
    importance_floor: float = typer.Option(PRUNE_IMPORTANCE_FLOOR, "--floor", "-f",
        help="Delete memories with importance below this threshold"),
    max_age_days: int = typer.Option(PRUNE_MAX_AGE_DAYS, "--age", "-a",
        help="Delete memories older than N days with low importance"),
    dry_run: bool = typer.Option(False, "--dry-run",
        help="Preview deletions without removing anything"),
):
    """Remove underutilized memories to reclaim database space."""
    count = prune_memories(
        importance_floor=importance_floor,
        max_age_days=max_age_days,
        dry_run=dry_run,
    )
    label = "Would delete" if dry_run else "Deleted"
    color = "yellow" if dry_run else "green"
    console.print(f"[{color}]{label} {count} memories.[/{color}]")
```

Register in `cli/main.py`:
```python
from cli.commands.prune import prune
app.command()(prune)
```

Usage:
```bash
devmemory prune                          # delete underutilized memories
devmemory prune --dry-run                # preview without deleting
devmemory prune --floor 0.1 --age 60    # stricter thresholds
```

**Done when:** `devmemory prune` removes decayed memories and reports count. `devmemory prune --dry-run` previews deletions without modifying the store.

---

## Phase 4A — MCP Server (Local Agent Interface)

> **Status: COMPLETED** — `mcp_server/` package implemented with 3 tools. `.mcp.json` created. Install: `uv pip install mcp>=1.0`. Note: directory named `mcp_server/` (not `mcp/`) to avoid shadowing the `mcp` PyPI package.
>
> **Why MCP before REST:** An agent calling `memory_search` via MCP requires zero server setup. The MCP server is spawned on-demand by Claude Code. REST requires a persistent `uvicorn` process and port management. For same-machine agent integration, MCP is strictly better.
>
> **All local. No cloud.** Uses `mcp[server]` (pure-Python PyPI package, stdio transport).

### 4A.1 MCP Server Setup

**Directory:** `mcp_server/` (named `mcp_server/` not `mcp/` to avoid shadowing the `mcp` PyPI package)

```
mcp_server/
├── __init__.py
├── server.py     # FastMCP entrypoint, tool registration, module-level setup docs
└── tools.py      # Tool implementations wrapping core/ modules, full docstrings
```

**New optional dependency:**
```toml
# pyproject.toml
[project.optional-dependencies]
mcp = ["mcp[server]>=1.0"]
```
Install: `uv pip install "devmemoryindex[mcp]"`

**Three tools to expose:**

`memory_search(query, k=5, memory_type=None, repo=None, intent=None) → list[dict]`
- Calls `store.hybrid_search(query, vector, k=k*2)`, applies type/repo filters
- Returns: list of `{summary, type, repo, importance, tags, related}`

`memory_context(query, max_tokens=4000, repo=None, format="claude") → str`
- Calls `ContextEngine.build()`, returns `context_text`
- Defaults to `format="claude"` → `<context>...</context>` XML that Claude parses best

`memory_remember(summary, raw_text=None, memory_type="agent_solution", repo=None, importance=0.9, tags=[]) → dict`
- Creates and stores a Memory. Returns `{status: "ok"|"duplicate", id}`
- **Closes the agent loop**: agent solves problem → stores solution → findable forever

```python
# mcp/server.py
from mcp.server.fastmcp import FastMCP
from mcp.tools import search_memories, build_context, remember_memory

mcp = FastMCP(
    "devmemory",
    instructions="""
    DevMemoryIndex: Persistent developer memory store.

    Use memory_search to find relevant past solutions, decisions, and commands.
    Use memory_context to get a formatted context block before starting complex tasks.
    Use memory_remember after solving a hard problem to persist the solution.

    Search with specific technical terms for best results.
    Always call memory_context before starting complex implementation tasks.
    """,
)

mcp.tool()(search_memories)
mcp.tool()(build_context)
mcp.tool()(remember_memory)

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

```python
# mcp/tools.py
from core.store_provider import get_store
from core.embeddings import embed
from core.context_engine import ContextEngine
from core.schema import Memory
import hashlib
from datetime import datetime


def search_memories(
    query: str,
    k: int = 5,
    memory_type: str | None = None,
    repo: str | None = None,
) -> list[dict]:
    """Search developer memory for relevant past solutions, commits, notes, and commands."""
    store = get_store()
    vector = embed(query)
    results = store.hybrid_search(query, vector, k=k * 2)
    if memory_type:
        results = [r for r in results if r.get("type") == memory_type]
    if repo:
        results = [r for r in results if r.get("repo") == repo]
    return [
        {
            "summary": r["summary"],
            "type": r["type"],
            "repo": r.get("repo"),
            "importance": r.get("importance"),
            "tags": r.get("tags", []),
        }
        for r in results[:k]
    ]


def build_context(
    query: str,
    max_tokens: int = 4000,
    repo: str | None = None,
    format: str = "claude",
) -> str:
    """Build AI-ready context from developer memory for the given task or query."""
    store = get_store()
    engine = ContextEngine(store)
    result = engine.build(query=query, repo=repo, max_tokens=max_tokens, format=format)
    return result["context_text"]


def remember_memory(
    summary: str,
    raw_text: str | None = None,
    memory_type: str = "agent_solution",
    repo: str | None = None,
    importance: float = 0.9,
    tags: list[str] = [],
) -> dict:
    """Persist a solution or decision to developer memory for future retrieval."""
    store = get_store()
    raw = raw_text or summary
    mem_id = hashlib.sha256(raw[:500].encode()).hexdigest()
    if store.exists(mem_id):
        return {"status": "duplicate", "id": mem_id}
    memory = Memory(
        id=mem_id,
        type=memory_type,
        summary=summary[:200],
        raw_text=raw,
        source="mcp_agent",
        repo=repo,
        timestamp=datetime.utcnow(),
        tags=tags + ["agent"],
        importance=importance,
    )
    store.add(memory, embed(memory.summary))
    return {"status": "ok", "id": mem_id}
```

### 4A.2 Claude Code Integration

**Project-local MCP config** (`.mcp.json` in project root — committed):
```json
{
  "mcpServers": {
    "devmemory": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp_server.server"],
      "cwd": "/Users/lshahverdi/projects/devmemoryindex"
    }
  }
}
```

**Registration command** (project-local, stored in `.claude/settings.json`):
```bash
claude mcp add devmemory -s local -- uv run python -m mcp_server.server
```

**Verification:** Run `/mcp` in Claude Code — `devmemory` appears as connected with 3 tools. Confirmed working ✅

**Status:** DONE — Claude Code can call all three tools natively. `memory_remember` verified: solutions persisted in one session are searchable via CLI (`devmemory search`) in subsequent sessions.

**MCP vs REST comparison:**

| | MCP Server (Phase 4A) | REST API (Phase 4B) |
|---|---|---|
| Target | Claude Code, Claude Desktop | CI/CD scripts, shell tools, cross-machine |
| Transport | stdio (same process, same machine) | HTTP (any network) |
| Server startup | On-demand by Claude Code | Requires persistent `uvicorn` process |
| Discovery | Automatic via `.mcp.json` config | Manual URL configuration |
| Best for | Agent querying memories in real-time | Webhook ingest, external automation |

**Done when:** Claude Code can call `memory_search("JWT auth")` and `memory_context("redis timeout")` as native tool calls, and `memory_remember("Fixed X by doing Y")` persists across sessions.

---

## Phase 4B — REST API (External Agent Interface) ✅

> **Status: COMPLETED** — `api/` fully implemented with auth.
>
> **Goal:** External processes (CI/CD pipelines, shell scripts, cross-machine agents) can push and query memories over HTTP. Not the primary agent interface — that's Phase 4A MCP.

### 4B.1 FastAPI Server

**File:** `api/server.py`

### 4.1 FastAPI Server

**File:** `api/server.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.search import router as search_router
from api.routes.memory import router as memory_router
from api.routes.context import router as context_router

app = FastAPI(
    title="DevMemoryIndex API",
    description="Persistent memory for developers and AI coding agents",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router, prefix="/memory", tags=["search"])
app.include_router(memory_router, prefix="/memory", tags=["memory"])
app.include_router(context_router, prefix="/memory", tags=["context"])

def start_server(host: str = "127.0.0.1", port: int = 7711):
    import uvicorn
    uvicorn.run(app, host=host, port=port)
```

---

### 4.2 Search Route

**File:** `api/routes/search.py`

```python
from fastapi import APIRouter, Query
from core.store_provider import get_store
from core.embeddings import embed

router = APIRouter()

@router.get("/search")
def search_memories(
    q: str = Query(..., description="Search query"),
    k: int = Query(5, description="Number of results"),
    type: str | None = Query(None, description="Filter by memory type"),
):
    store = get_store()
    vector = embed(q)
    results = store.hybrid_search(q, vector, k=k)

    if type:
        results = [r for r in results if r.get("type") == type]

    return {
        "query": q,
        "count": len(results),
        "results": [
            {
                "id": r.get("id"),
                "type": r.get("type"),
                "summary": r.get("summary"),
                "repo": r.get("repo"),
                "importance": r.get("importance"),
            }
            for r in results
        ],
    }
```

---

### 4.3 Memory Route (Add/Remember)

**File:** `api/routes/memory.py`

```python
import hashlib
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from core.store_provider import get_store
from core.schema import Memory
from core.embeddings import embed

router = APIRouter()

class MemoryInput(BaseModel):
    summary: str
    raw_text: str | None = None
    type: str = "agent_solution"
    repo: str | None = None
    importance: float = 0.9
    tags: list[str] = []

@router.post("/remember")
def remember(input: MemoryInput):
    store = get_store()

    raw = input.raw_text or input.summary
    mem_id = hashlib.sha256(raw[:500].encode()).hexdigest()

    memory = Memory(
        id=mem_id,
        type=input.type,
        summary=input.summary[:200],
        raw_text=raw,
        source="api",
        repo=input.repo,
        timestamp=datetime.utcnow(),
        tags=input.tags,
        importance=input.importance,
    )

    vector = embed(memory.summary)
    store.add(memory, vector)

    return {"status": "ok", "id": mem_id}
```

---

### 4.4 Context Route

**File:** `api/routes/context.py`

```python
from fastapi import APIRouter, Query
from core.store_provider import get_store
from core.embeddings import embed
from core.context_engine import ContextEngine

router = APIRouter()

@router.get("/context")
def get_context(
    q: str = Query(..., description="Context query"),
    repo: str | None = Query(None),
    tokens: int = Query(4000),
    format: str = Query("raw", description="raw | markdown | claude"),
):
    store = get_store()
    engine = ContextEngine(store)
    vector = embed(q)

    result = engine.build(
        query=q,
        vector=vector,
        repo=repo,
        max_tokens=tokens,
        format=format,
    )

    return {
        "query": q,
        "context": result["context_text"],
        "token_estimate": result["token_estimate"],
        "memory_count": result["memory_count"],
    }
```

**Run:** `uvicorn api.server:app --port 7711`

**Test:**
```bash
curl "http://localhost:7711/memory/search?q=redis+timeout"
curl "http://localhost:7711/memory/context?q=docker+networking&format=claude"
curl -X POST "http://localhost:7711/memory/remember" \
  -H "Content-Type: application/json" \
  -d '{"summary": "Fixed JWT auth by refreshing on 401", "repo": "api"}'
```

**Done when:** All three endpoints return valid JSON responses.

---

### 4.5 Webhook Route (Push Ingest)

**File:** `api/routes/webhook.py`

**Purpose:** Let CI/CD pipelines, deploy scripts, and monitoring tools push memories into DevMemoryIndex in real-time — no polling, no connector schedule required.

```python
import hashlib
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from core.store_provider import get_store
from core.schema import Memory
from core.embeddings import embed

router = APIRouter()

class WebhookPayload(BaseModel):
    text: str
    source: str = "webhook"
    type: str = "agent_solution"
    repo: str | None = None
    importance: float = 0.8
    tags: list[str] = []

@router.post("/ingest")
def webhook_ingest(payload: WebhookPayload):
    """Accept a pushed memory from an external process (CI/CD, deploy scripts, monitors)."""
    store = get_store()
    mem_id = hashlib.sha256((payload.text + payload.source).encode()).hexdigest()

    if store.exists(mem_id):
        return {"status": "duplicate", "id": mem_id}

    memory = Memory(
        id=mem_id,
        type=payload.type,
        summary=payload.text[:200],
        raw_text=payload.text,
        source=payload.source,
        repo=payload.repo,
        timestamp=datetime.utcnow(),
        tags=payload.tags or ["webhook"],
        importance=payload.importance,
    )
    store.add(memory, embed(memory.summary))
    return {"status": "ok", "id": mem_id}
```

Register in `api/server.py`:
```python
from api.routes.webhook import router as webhook_router
app.include_router(webhook_router, prefix="/memory", tags=["webhook"])
```

**Usage examples:**
```bash
# From a deploy script — push a deployment event as a memory
curl -X POST "http://localhost:7711/memory/ingest" \
  -H "Content-Type: application/json" \
  -d '{"text": "Deployed v2.3 to production (k8s rollout)", "source": "deploy-script", "type": "git_commit", "repo": "api"}'

# From a monitoring alert
curl -X POST "http://localhost:7711/memory/ingest" \
  -H "Content-Type: application/json" \
  -d '{"text": "OOM kill on worker-pod-3 at 03:14 UTC", "source": "alertmanager", "type": "terminal_command"}'
```

**Done when:** `POST /memory/ingest` accepts a JSON body, creates a Memory, indexes it immediately, and returns `{"status": "ok", "id": "..."}`. Duplicate payloads return `{"status": "duplicate"}`.

---

### GitHub Actions Integration

**Use case:** Every CI run (deploy, test failure, release) gets indexed as a memory automatically. You can later ask `devmemory search "last time prod deploy failed"` or use voice search to recall what broke and when.

**Prerequisites:**
- `devmemory serve` running on a machine reachable from GitHub's runners
- Server exposed publicly — e.g. via `ngrok http 7711` or a VPS — not localhost
- Server URL stored as a GitHub Actions secret: `DEVMEMORY_URL`

**Example workflow** — `.github/workflows/deploy.yml`:

```yaml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run deploy
        id: deploy
        run: ./scripts/deploy.sh

      - name: Index deploy event in DevMemoryIndex
        if: always()   # run even if deploy fails
        env:
          DEVMEMORY_URL: ${{ secrets.DEVMEMORY_URL }}
          REPO: ${{ github.repository }}
          SHA: ${{ github.sha }}
          STATUS: ${{ job.status }}
          BRANCH: ${{ github.ref_name }}
          ACTOR: ${{ github.actor }}
        run: |
          TEXT="Deploy $STATUS on $REPO@${SHA:0:7} (branch: $BRANCH, actor: $ACTOR)"
          curl -s -X POST "$DEVMEMORY_URL/memory/ingest" \
            -H "Content-Type: application/json" \
            -d "{
              \"text\": \"$TEXT\",
              \"source\": \"github-actions\",
              \"memory_type\": \"agent_solution\",
              \"repo\": \"$REPO\",
              \"importance\": $([ \"$STATUS\" = \"failure\" ] && echo 0.95 || echo 0.75),
              \"tags\": [\"deploy\", \"ci\", \"$STATUS\"]
            }"
```

**What gets indexed:**
- `"Deploy success on myorg/api@a3f9c12 (branch: main, actor: lshahverdi)"` — importance 0.75
- `"Deploy failure on myorg/api@a3f9c12 (branch: main, actor: lshahverdi)"` — importance 0.95

**Querying later:**
```bash
devmemory search "deploy failure main branch"
devmemory search --voice   # speak: "when did the last deploy fail?"
```

**Other events to index:**

```yaml
# Test failures
- name: Index test failure
  if: failure()
  run: |
    curl -s -X POST "$DEVMEMORY_URL/memory/ingest" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"Tests failed on $REPO@${SHA:0:7}: ${{ steps.test.outputs.summary }}\",
           \"source\": \"github-actions\", \"memory_type\": \"debugging_insight\",
           \"repo\": \"$REPO\", \"importance\": 0.9, \"tags\": [\"test\", \"failure\"]}"

# Release published
- name: Index release
  if: github.event_name == 'release'
  run: |
    curl -s -X POST "$DEVMEMORY_URL/memory/ingest" \
      -H "Content-Type: application/json" \
      -d "{\"text\": \"Released ${{ github.event.release.tag_name }}: ${{ github.event.release.name }}\",
           \"source\": \"github-actions\", \"memory_type\": \"git_commit\",
           \"repo\": \"$REPO\", \"importance\": 0.85, \"tags\": [\"release\"]}"
```

---

### 4B.2 API Key Authentication ✅

**Files:**
- `api/auth.py` — `verify_api_key` FastAPI dependency; open if no key configured, 401 otherwise
- `cli/commands/api_key_cmd.py` — `devmemory api-key generate/show/revoke`
- `core/config.py` — `get_api_key()`, `set_api_key()`, `delete_api_key()` under `[api]` section
- `api/server.py` — `Depends(verify_api_key)` on all routers; `--no-auth` flag bypasses via `DEVMEMORY_NO_AUTH` env var
- `cli/commands/serve.py` — `--no-auth` flag

**Behaviour:**
- No key in config → all requests accepted (safe for localhost default)
- Key in config → `Authorization: Bearer <key>` required on every request
- Wrong or missing key → `401 Unauthorized`
- `devmemory serve --no-auth` → bypasses enforcement even if a key is configured

**Usage:**
```bash
devmemory api-key generate      # prints: API key saved. Use: Authorization: Bearer a3f9c1...
devmemory api-key show          # prints current key
devmemory api-key revoke        # removes key (re-opens server)
devmemory serve                 # enforces auth if key is set
devmemory serve --no-auth       # skips enforcement (localhost dev / debugging)

curl -H "Authorization: Bearer a3f9c1..." "http://machine:7711/memory/search?q=redis"
```

---

## Phase 5 — Daemon (Automation)

> **Goal:** Memories appear automatically without running manual commands.
> The daemon runs connectors on a schedule and watches for filesystem changes.

### 5.1 Scheduler ✅

**Status: COMPLETED** — `run_daemon()` loop implemented with connector dispatch, per-cycle counts, and daily pruning trigger.

**File:** `daemon/scheduler.py`

```python
import time
from rich.console import Console
from connectors.registry import get_connectors

console = Console()

def run_daemon(interval: int = 300):
    """Run all connectors periodically."""
    console.print(f"[green]DevMemoryIndex daemon started. Interval: {interval}s[/green]")

    while True:
        connectors = get_connectors()
        total = 0

        for c in connectors:
            try:
                count = c.collect()
                total += count
                if count > 0:
                    console.print(f"  [{c.name}] +{count} memories")
            except Exception as e:
                console.print(f"  [red][{c.name}] Error: {e}[/red]")

        if total > 0:
            console.print(f"[green]Cycle complete: +{total} new memories[/green]")

        time.sleep(interval)
```

### 5.2 File Watcher ✅

**File:** `daemon/watcher.py`

Uses `watchdog` to trigger immediate re-indexing when files change, rather than waiting for the next scheduler cycle.

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from connectors.filesystem_connector import FilesystemConnector

class MemoryEventHandler(FileSystemEventHandler):
    def __init__(self):
        self.connector = FilesystemConnector()

    def on_modified(self, event):
        if not event.is_directory and not event.src_path.startswith(".git"):
            # Re-index the changed file
            self.connector.collect()

def start_watcher(path: str = "."):
    observer = Observer()
    observer.schedule(MemoryEventHandler(), path, recursive=True)
    observer.start()
    return observer
```

### 5.3 Importance Decay Job ✅

**Status: COMPLETED** — `decay_importance(factor=0.99)` implemented in `daemon/jobs/importance_decay.py`. Skips pinned memories. Called daily by scheduler.

**File:** `daemon/jobs/importance_decay.py`

```python
from core.store_provider import get_store

def decay_importance(factor: float = 0.99):
    """Reduce importance of non-pinned memories slightly. Run daily."""
    store = get_store()
    try:
        df = store.collection.to_pandas()
        # Skip pinned memories — their importance must never decay
        mask = df.get("pinned", False) != True
        df.loc[mask, "importance"] = df.loc[mask, "importance"] * factor
        # Rewrite (LanceDB overwrite pattern)
        store.collection.merge_insert(df)
    except Exception:
        pass  # Non-critical job
```

**Done when:** `devmemory daemon` runs continuously, automatically ingests new data, memories decay in importance over time, and pinned memories are unaffected by decay.

---

### 5.4 Access Reinforcement + Memory Pruning ✅

**Status: COMPLETED** — `MemoryStore.reinforce()` implemented and called automatically after every search. `daemon/jobs/memory_cleanup.py` prunes by importance floor and age. `devmemory prune` CLI command wired.

This phase pulls Phase 6.1 (Importance Reinforcement) forward because the pruning system must be aware of access patterns. A memory queried yesterday should not be pruned, even if it is old.

---

#### 5.4A — Access Reinforcement (pulled forward from Phase 6.1)

**Add `reinforce()` to `MemoryStore`** (`core/memory_store.py`):

```python
def reinforce(self, memory_id: str, boost: float = 0.05) -> None:
    """Boost importance of a retrieved memory (cap at 1.0). Call after search hits."""
    try:
        results = self.collection.search().where(f"id = '{memory_id}'").limit(1).to_list()
        if not results:
            return
        r = results[0]
        new_importance = min(1.0, r.get("importance", 0.5) + boost)
        # LanceDB update via merge_insert on single row
        import pyarrow as pa
        tbl = pa.table({"id": [memory_id], "importance": [new_importance]})
        self.collection.merge_insert("id").when_matched_update_all().execute(tbl)
    except Exception:
        pass  # Non-critical
```

**Call `reinforce()` from search methods** — after `hybrid_search()` and `semantic_search()` return results, boost each returned memory's importance:

```python
# In hybrid_search() and semantic_search(), after building ranked list:
for r in ranked[:k]:
    self.reinforce(r["id"], boost=0.05)
return ranked[:k]
```

> **Effect on pruning:** A memory queried even once per month at 0.05 boost/query will offset the 0.99 daily decay (~0.70 per month decay vs. 0.05+ boost). Only memories that are genuinely never retrieved will decay past the prune floor.

---

#### 5.4B — Memory Pruning Job

**File:** `daemon/jobs/memory_cleanup.py`

```python
from datetime import datetime, timedelta
from core.store_provider import get_store

PRUNE_IMPORTANCE_FLOOR = 0.05   # Memories decayed below this → pruneable
PRUNE_MAX_AGE_DAYS     = 90     # Memories older than this AND weak → pruneable
PRUNE_OLD_IMPORTANCE   = 0.15   # Importance threshold for the age-based rule

def prune_memories(
    importance_floor: float = PRUNE_IMPORTANCE_FLOOR,
    max_age_days: int = PRUNE_MAX_AGE_DAYS,
    dry_run: bool = False,
) -> int:
    """Delete underutilized memories. Respects pinned flag. Returns count deleted.

    Two pruning criteria (either qualifies):
    1. importance < importance_floor  (decayed past point of usefulness, regardless of age)
    2. older than max_age_days AND importance < PRUNE_OLD_IMPORTANCE  (old and weak)

    Memories with any recent retrieval will have boosted importance and survive.
    Pinned memories are always skipped.
    """
    store = get_store()
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)

    try:
        all_records = store.collection.to_arrow().to_pylist()
    except Exception:
        return 0

    to_delete = []
    for r in all_records:
        if r.get("pinned", False):
            continue
        importance = r.get("importance", 0.5)
        ts = r.get("timestamp")

        below_floor = importance < importance_floor
        old_and_weak = ts is not None and ts < cutoff and importance < PRUNE_OLD_IMPORTANCE

        if below_floor or old_and_weak:
            to_delete.append(r["id"])

    if not dry_run:
        for mem_id in to_delete:
            store.delete(mem_id)

    return len(to_delete)
```

**Integrate into scheduler** (`daemon/scheduler.py`) — run `prune_memories()` once daily:

```python
import time
from datetime import date
from daemon.jobs.memory_cleanup import prune_memories

def run_daemon(interval: int = 300):
    last_prune_date = None
    while True:
        # ... run connectors as before ...

        today = date.today()
        if last_prune_date != today:
            pruned = prune_memories()
            if pruned > 0:
                console.print(f"[dim]Pruned {pruned} underutilized memories[/dim]")
            last_prune_date = today

        time.sleep(interval)
```

**Tests:** `daemon/tests/test_memory_cleanup.py`
- Insert 5 low-importance (0.02) unpinned memories + 1 pinned (0.02) → `prune_memories()` deletes 5, skips pinned.
- Insert 3 old (100+ days) weak-importance (0.1) memories → all 3 pruned.
- Insert 2 recently-reinforced high-importance (0.8) memories → none pruned.
- Dry run: returns correct count but store row count is unchanged.
- `reinforce()` test: boost a 0.5 importance memory → becomes 0.55; cap at 1.0 when already 0.98.

**Done when:** Running `devmemory daemon` auto-prunes underutilized memories daily. `devmemory prune --dry-run` previews deletions without removing anything.

---

## Phase 5 (new) — Smart Retrieval (Intelligence Layer)

> **Pulled forward from Phase 6.** These features directly improve query quality for both voice search and agent queries. Build after Phase 4A MCP is working. No LLMs required — all rule-based or lightweight.

### 5.A — Intent Classifier ✅

**New file:** `core/intent_classifier.py`

Classifies queries into intent categories and returns routing parameters that shift `ContextEngine`'s type weighting. No ML model — pure keyword matching on the already-transcribed or typed query.

```python
INTENT_RULES = {
    "debug": {
        "keywords": ["error", "fix", "bug", "crash", "exception", "traceback",
                     "fail", "broken", "not working", "why is", "undefined"],
        "type_boost": ["agent_solution", "terminal_command"],
        "importance_weight": 0.35,  # raise from default 0.25
        "recency_weight": 0.20,     # raise from default 0.15
    },
    "architecture": {
        "keywords": ["design", "pattern", "structure", "architecture", "how does",
                     "why did", "decision", "approach", "schema", "model"],
        "type_boost": ["agent_solution", "git_commit"],
        "importance_weight": 0.30,
        "recency_weight": 0.10,     # older architectural decisions still relevant
    },
    "implementation": {
        "keywords": ["how to", "implement", "add", "create", "build", "integrate",
                     "setup", "configure", "install", "deploy"],
        "type_boost": ["git_commit", "terminal_command", "file_content"],
        "importance_weight": 0.25,
        "recency_weight": 0.15,
    },
    "recall": {
        "keywords": ["what was", "remember", "last time", "before", "when did",
                     "voice", "said", "told"],
        "type_boost": ["voice_note", "meeting_self", "note"],
        "importance_weight": 0.20,
        "recency_weight": 0.25,     # recall queries are highly recency-sensitive
    },
}

def classify_intent(query: str) -> tuple[str, dict]:
    """Return (intent_label, routing_params). Falls back to 'general' with no routing."""
    query_lower = query.lower()
    for intent, config in INTENT_RULES.items():
        if any(kw in query_lower for kw in config["keywords"]):
            return intent, config
    return "general", {}
```

**Integration points:**
- `core/context_engine.py` — add `intent` param to `build()`, shift `pack_within_budget()` ordering
- `cli/commands/search.py --voice` — auto-classify transcribed query, optionally display with `--verbose`
- `mcp/tools.py` — accept explicit `intent` from agents, or auto-classify

**Done when:** `devmemory search --voice "why is the auth broken"` automatically routes as a `debug` query and returns `agent_solution` + `terminal_command` memories first.

---

### 5.B — Context Caching ✅

**Status: COMPLETED** — `core/context_cache.py` implemented.

Module-level LRU cache (50 entries, 5-min TTL) for `ContextEngine.build()`. Key: `sha256(query|repo|format|intent)`. Auto-invalidated via `store.add()`. Context response includes `cached: true/false`.

---

### 5.C — Memory Deduplication Job ✅

**Status: COMPLETED** — `daemon/jobs/dedup.py` implemented.

Groups memories by `summary[:100].lower()`, keeps highest-importance duplicate, deletes the rest. Runs weekly (Mondays) in daemon scheduler.

---

### 5.D — Related Memories ✅

**Status: COMPLETED** — `core/memory_store.py` updated.

`hybrid_search()` return value includes `"related": [ids of nearest neighbors from semantic_results not already in top-k][:3]`. No additional search calls. MCP `search_memories` and REST `/memory/search` both expose this field. `devmemory get <id>` resolves related IDs.

---

## Phase 6 — Intelligence Layer (Post-Launch)

> **Revised scope** — 6.1 (reinforcement), 6.5 (suggest), 6.2 (dedup), 6.4 (related), 6.6 (caching) pulled forward into new Phase 5. Remaining here: compression and namespace.

### 6.1 Importance Reinforcement *(completed — Phase 5.4A)*

> **Done.** `MemoryStore.reinforce()` implemented and called from `hybrid_search()` and `semantic_search()`.

### 6.2 Memory Deduplication *(moved to Phase 5.C)*

### 6.3 Memory Compression
Summarize old, low-importance memories into condensed versions. Store both original and compressed. Use compressed for context to save tokens. *Deferred — too complex for current scale.*

### 6.4 Related Memories *(moved to Phase 5.D)*

### 6.5 Auto-Context (No Query Required) *(moved to Phase 3.B — `devmemory suggest`)*

### 6.6 Context Caching *(moved to Phase 5.B)*

### 6.7 Multi-Project Namespace ✅ *(already implemented as `--repo`)*

Repo-scoped search was built as part of Phase 4B / hybrid_search. The `repo` field on the Memory schema, `--repo` CLI flag, `repo_filter` in `hybrid_search()`, and `repo=` in the MCP tool cover this entirely. No separate `project` field needed.

---

## Phase 7 — Advanced Features (Future Vision)

> These are longer-term enhancements for when DevMemoryIndex has active users.

**Recommended implementation order: 7.3 → 7.4 → 7.7 → 7.1 → 7.2 → 7.8 → 7.9 → 7.5 → 7.6**

**Dependency graph:**
```
7.1 (Local LLM/RAG) ──► 7.2 (Feedback Loop)
7.1 (Local LLM/RAG) ──► 7.9 (Agent Mode)
7.4 (Semantic Diff) ──► 7.8 (Codebase Map) [recommended]
7.1 (RAG API)       ──► 7.6 (Web UI chat window)
Phase 4B REST API   ──► 7.5 (VSCode Extension)
Phase 4B REST API   ──► 7.6 (Web UI)
Standalone:             7.3, 7.4
New [llm] dep:          7.1, 7.2, 7.9
New [ml] dep:           7.7, 7.8
```

---

### 7.1 Local LLM / RAG (`devmemory ask`)

`devmemory ask "why did we move from Redis?"` → retrieves top memories → injects into LLM prompt → streams cited answer to terminal.

**New files:**
- `core/llm_backend.py` — abstract `LLMBackend` + `OllamaBackend` (POST `http://localhost:11434/api/generate`, stream via `httpx`) + `LlamaCppBackend` (POST `/completion` port 8080) + `get_backend(cfg_dict)` factory
- `core/rag_engine.py` — `RAGEngine(store, backend)`: `ask(query, repo, max_context_tokens=3000, stream=True) -> (answer_str, cited_memories)`. Calls `ContextEngine.build(format="raw")`. `_format_for_prompt()` labels memories as `[MEMORY-1]...[MEMORY-N]`. `_build_prompt()` = system prompt + context + "Answer:"
- `cli/commands/ask.py` — `ask(query, repo, model, no_stream, save)`, Rich `Live` for streaming

**Modified files:** `core/config.py` (add `get_llm_config() -> dict` for `[llm]` section), `pyproject.toml` (add `llm = ["httpx>=0.27"]`), `cli/main.py` (register inside `try/except ImportError`)

**Reuses:** `ContextEngine.build()`, `get_store()`, `embed()`

**Verify:**
```bash
uv pip install -e ".[llm]"
ollama serve & ollama pull mistral
devmemory ask "how does the daemon scheduler work?"
# Streaming answer with [MEMORY-N] citations
```

---

### 7.2 Memory Feedback Loop

After `devmemory ask` completes, saves the Q&A pair as a new `agent_solution` memory (importance=0.75, tags=`["rag_answer", "auto_indexed"]`). Default on; `--no-save` to disable.

**No new files** — modifies only `core/rag_engine.py` and `cli/commands/ask.py` (both from 7.1):
- `rag_engine.py`: add `save_answer(query, answer, cited_memories, repo) -> mem_id`. ID = `sha256(raw_text[:500])` for idempotency. Calls `redact()` before storing. Importance capped at 0.75 to prevent auto-answers dominating search.
- `ask.py`: call `engine.save_answer()` after stream completes when `--save` (default True)

**Reuses:** `redact()` (`core/privacy.py`), `store.exists()` + `store.add()`, `embed()`

**Verify:**
```bash
devmemory ask "how does the dedup job work?"
devmemory search "dedup job" --type agent_solution  # returns saved answer
```

---

### 7.3 Git Hook Integration ✅

**Status: COMPLETED**

**Files:**
- `core/hooks.py` — `install_hook()`, `uninstall_hook()`, `hook_status()`. Appends/strips a marked block safely; never clobbers existing hook content. Sets `chmod +x`.
- `cli/commands/hook_cmd.py` — `devmemory hook install/uninstall/status`
- `core/tests/test_hooks.py` — 15 tests. All passing.

Installs a `post-commit` hook so every `git commit` immediately calls `devmemory ingest --source git &`. No daemon poll delay.

**New files:**
- `core/hooks.py` — pure Python, no new deps. `HOOK_MARKER = "# devmemory-hook"`. `install_hook(repo_path) -> "installed"|"appended"|"already_installed"|"error_not_a_repo"` (appends safely to existing hooks; sets `chmod +x`). `uninstall_hook()` strips only devmemory block (HOOK_MARKER to next blank line); deletes file if now empty. `hook_status(repo_path) -> bool`
- `cli/commands/hook_cmd.py` — Typer sub-app: `install [repo]`, `uninstall [repo]`, `status [repo]`

**Modified files:** `cli/main.py` — `app.add_typer(hook_app, name="hook")`

**Reuses:** `get_git_paths()` (`core/config.py`) for iterating all repos in `status`

**Verify:**
```bash
mkdir /tmp/testrepo && git init /tmp/testrepo
devmemory hook install /tmp/testrepo
echo "x" > /tmp/testrepo/f.txt && git -C /tmp/testrepo add . && git -C /tmp/testrepo commit -m "hook test"
sleep 2 && devmemory search "hook test"  # immediately indexed
devmemory hook uninstall /tmp/testrepo
```

---

### 7.4 Semantic Diff Awareness

New connector indexes per-file code diffs as `git_diff` memories. Enables semantic queries about code content ("why did we remove Redis?"), not just commit messages.

**New files:**
- `connectors/diff_connector.py` — `DiffConnector(Connector)`, `name = "diff"`, `commit_limit=50`. `_index_repo()`: `git log -n50` → for each commit: `git diff --unified=3 {sha}~1 {sha}` → `_split_diff_by_file()` splits on `diff --git` lines → one memory per file. Memory type `"git_diff"`, importance 0.6. ID = `sha256(f"{sha}|{repo_name}|{filepath}")`. embed_text uses only +/- lines (not context) for signal density, truncated to 512 chars. Applies `self._redact()` to raw diff.

**Modified files:**
- `connectors/registry.py` — add `DiffConnector` after `GitConnector` in `ALL_CONNECTORS`
- `core/intent_classifier.py` — add "why did", "removed", "deleted", "before" keywords to `architecture` and `recall` intents

**Reuses:** `Connector` base class, `embed()`, `get_git_paths()`, `hashlib.sha256`

**Verify:**
```bash
devmemory ingest --source diff
devmemory search "removed Redis" --type git_diff
```

---

### 7.5 VSCode Extension

Two VSCode commands: "DevMemory: Ask" (selected text or input → `GET /memory/context` → Output Channel) and "DevMemory: Remember selection" (`POST /memory/remember`). Talks to REST API on port 7711.

**New directory: `vscode-extension/`** (TypeScript, independent project)
```
vscode-extension/
  package.json     # engines: vscode ^1.85.0; zero runtime deps (uses built-in fetch)
  tsconfig.json
  src/
    extension.ts   # activate(): registers devmemory.ask + devmemory.remember
    api.ts         # getContext(query, apiUrl, format), rememberText(summary, raw, apiUrl)
```
- Uses `fetch()` (Node 18+ built-in in VS Code 1.85+) — no axios/node-fetch
- `devmemory.ask`: selected text → query, else `showInputBox`. Result → `OutputChannel("DevMemory")`
- `devmemory.remember`: requires selection; `showInputBox` for summary
- Error path: `showErrorMessage("Is devmemory serve running?")`
- Settings: `devmemory.apiUrl` (default `http://localhost:7711`), `devmemory.format` (default `"markdown"`)

**No Python changes** — CORS already `allow_origins=["*"]`

**Verify:** `devmemory serve` → F5 in VSCode → Extension Dev Host → select code → run "DevMemory: Ask"

---

### 7.6 Web UI (Svelte)

Local SPA at `http://localhost:7711/ui` with 5 tabs: Search, Timeline, Chat (RAG), Context, Stats.

**New directory: `ui/`** (Svelte + Vite, independent project)
```
ui/src/
  App.svelte              # tab navigation
  lib/api.ts              # search(), getContext(), askRAG(), getStats(), getTimeline()
  lib/stores.ts           # Svelte writable stores
  routes/
    Search.svelte         # search bar + type/repo filters + MemoryCard grid
    Timeline.svelte       # paginated chronological browser
    Chat.svelte           # streaming RAG (requires 7.1 /memory/ask endpoint)
    Context.svelte        # context viewer with copy button
    Stats.svelte          # Chart.js type breakdown
  components/
    MemoryCard.svelte     # type badge, summary, repo, importance
```

**New Python API routes:**
- `api/routes/stats.py` — `GET /memory/stats` → `{total, by_type: {type: count}}` via `store.get_all()`
- `api/routes/timeline.py` — `GET /memory/timeline?limit&offset` → paginated time-sorted memories
- `api/routes/ask.py` — `POST /memory/ask` (requires 7.1) → `StreamingResponse` wrapping `RAGEngine.ask()`

**Modified Python files:** `api/server.py` (include 3 new routers; mount `ui/dist/` as `StaticFiles` at `/ui`), `pyproject.toml` (add `ui = ["fastapi>=0.100", "uvicorn[standard]>=0.20", "aiofiles"]`)

**Verify:**
```bash
cd ui && npm install && npm run build
devmemory serve
# http://localhost:7711/ui → Search, Timeline, Stats tabs
```

---

### 7.7 ML Intent Classifier

Drop-in ML upgrade for `core/intent_classifier.py`. `SGDClassifier` on TF-IDF features, confidence-gated fallback to rule-based.

**New files:**
- `core/ml_intent_classifier.py` — `MLIntentClassifier`: `load() -> bool`, `train(labels_path) -> int`, `classify(query) -> (label, confidence)`. Model persisted at `~/.config/devmemory/intent_model.pkl`. `classify_intent_ml(query, confidence_threshold=0.6)` — falls back to rule-based if model not loaded or confidence < threshold
- `data/intent_labels.jsonl` — ≥200 hand-labeled examples, ≥40 per class (debug/recall/architecture/implementation/general). Format: `{"query": "...", "intent": "debug"}`
- `cli/commands/train_cmd.py` — `devmemory train-intent [--labels PATH] [--eval/--no-eval]`

**Modified files:** `core/context_engine.py` (swap classifier: `try: from core.ml_intent_classifier import classify_intent_ml as _classify / except ImportError: from core.intent_classifier import classify_intent as _classify`), `pyproject.toml` (add `ml = ["scikit-learn>=1.3"]`)

**Reuses:** `INTENT_RULES` dict from `core/intent_classifier.py` — ML label maps to same routing params

**Verify:**
```bash
uv pip install -e ".[ml]"
devmemory train-intent  # "Trained on N examples. CV accuracy: ~87%"
```

---

### 7.8 Codebase Map Generation

`devmemory map` clusters `git_diff` memories by their stored 384-dim vectors (no re-embedding), builds a weighted adjacency graph (edges = commits touching both clusters), outputs ASCII + JSON.

**New files:**
- `core/codebase_map.py` — `generate_map(store, min_cluster_size=3, n_clusters=None, output_format="json") -> dict`. Uses `store.get_all()` — reads stored vectors directly from LanceDB (key efficiency win, zero re-embedding). `_auto_cluster_count()` maximises silhouette score over k=3..15. `KMeans` on L2-normalised vectors. `_dominant_prefix()` labels cluster by most common `Path(f).parts[0]`. `_build_edges()` weights = commits touching files in both clusters (filters weight < 2). `_render_ascii()` adjacency list with `↔` arrows
- `cli/commands/map_cmd.py` — `devmemory map [--output json|ascii|both] [--min-cluster N] [--clusters K] [--save PATH]`

**Modified files:** `cli/main.py` (register `map` inside `try/except ImportError` for `[ml]`). Reuses `[ml]` extra from 7.7 — no additional deps.

**Verify:**
```bash
devmemory ingest --source diff  # 7.4 needed for git_diff memories
devmemory map --output ascii
devmemory map --output json --save map.json
```

---

### 7.9 Agent Mode (`devmemory plan`)

`devmemory plan "add websocket multiplayer"` → `git diff HEAD` + relevant memories + LLM → streamed numbered implementation plan, saved as memory.

**Hard dependency: Phase 7.1 must be implemented first.**

**New files:**
- `core/plan_engine.py` — `PlanEngine(store, backend)`: `generate_plan(task, repo_path=".", repo, include_diff=True, max_context_tokens=3500, stream=True) -> (plan_str, metadata_dict)`. Step 1: `git diff HEAD` via subprocess truncated to 2000 chars (same pattern as `cli/commands/suggest.py`). Step 2: `ContextEngine.build(intent="implementation")`. Step 3: `_build_plan_prompt()` = system prompt + diff section + memory section + "Plan:". Step 4: `backend.complete()`. Returns `(plan_text, {memories_used, diff_lines, tokens_estimated})`
- `cli/commands/plan.py` — `plan(task, repo, no_diff, save, stream)`. Renders with Rich `Markdown`. Saves via `RAGEngine.save_answer()` from 7.2.

**Modified files:** `cli/main.py` (register inside `try/except ImportError` for `[llm]`)

**Reuses:** `LLMBackend`/`get_backend()`/`get_llm_config()` (7.1), `ContextEngine.build()`, `RAGEngine.save_answer()` (7.2), git diff subprocess from `cli/commands/suggest.py`

**Verify:**
```bash
devmemory plan "add rate limiting to the API"
# Streamed numbered plan referencing past memories + git diff context
devmemory search "rate limiting" --type agent_solution  # plan saved
```

---

### Phase 7 Summary

| Phase | New Files | Modified Files | New Dep | Depends On |
|---|---|---|---|---|
| 7.1 | `core/llm_backend.py`, `core/rag_engine.py`, `cli/commands/ask.py` | `core/config.py`, `cli/main.py`, `pyproject.toml` | `[llm]` (httpx) | — |
| 7.2 | — | `core/rag_engine.py`, `cli/commands/ask.py` | — | 7.1 |
| 7.3 | `core/hooks.py`, `cli/commands/hook_cmd.py` | `cli/main.py` | — | — |
| 7.4 | `connectors/diff_connector.py` | `connectors/registry.py`, `core/intent_classifier.py` | — | — |
| 7.5 | `vscode-extension/src/*.ts`, `package.json` | — | TypeScript only | Phase 4B |
| 7.6 | `ui/src/**`, `api/routes/{ask,stats,timeline}.py` | `api/server.py`, `pyproject.toml` | `[ui]` (aiofiles) | Phase 4B; 7.1 for chat |
| 7.7 | `core/ml_intent_classifier.py`, `data/intent_labels.jsonl`, `cli/commands/train_cmd.py` | `core/context_engine.py`, `pyproject.toml` | `[ml]` (scikit-learn) | — |
| 7.8 | `core/codebase_map.py`, `cli/commands/map_cmd.py` | `cli/main.py` | reuses `[ml]` | 7.4 recommended |
| 7.9 | `core/plan_engine.py`, `cli/commands/plan.py` | `cli/main.py` | reuses `[llm]` | 7.1, 7.2 |

---

## Execution Order Summary

> **Revised priority** — ordered around two tracks: human voice query and agent querying. Connector volume is secondary to interface quality.

| Priority | Phase | What You Build | Time Est. | Status |
|---|---|---|---|---|
| ~~Done~~ | 1.1–1.8 | Core engine: MemoryStore, ranking, hybrid search, context engine, privacy, dedup | — | ✅ |
| ~~Done~~ | 2.1–2.3 | Connector base, registry, GitConnector | — | ✅ |
| ~~Done~~ | 3.x | CLI: search, add, stats, prune, dictate, voice enroll, ingest, config | — | ✅ |
| ~~Done~~ | 5.1, 5.3, 5.4 | Daemon scheduler, importance decay, reinforcement, memory pruning | — | ✅ |
| ~~Done~~ | 3.A | `devmemory context` command (ContextEngine already done, just wire CLI) | — | ✅ |
| ~~Done~~ | 3.B | `devmemory suggest` command (git diff → ContextEngine, zero new deps) | — | ✅ |
| ~~Done~~ | 3.C | Enhanced `search --voice` (8s, quality gate, confirmation display, --speak) | — | ✅ |
| ~~Done~~ | 3.D | `repl`, `export`/`import`, `daemon` CLI commands | — | ✅ |
| ~~Done~~ | 4A | MCP Server — `memory_search`, `memory_context`, `memory_remember` tools | — | ✅ |
| ~~Done~~ | 2 (Claude) | Claude Code Connector (past solutions = highest-value memories) | — | ✅ |
| ~~Done~~ | 2 (Terminal) | Terminal Connector | — | ✅ |
| ~~Done~~ | 5.A | Intent Classifier — rule-based keyword routing into ContextEngine | — | ✅ |
| **Week 2** | 2 (Markdown) | Markdown Connector (great for voice recall queries) | half day | |
| **Week 2** | 2 (Filesystem) | Filesystem Connector | 1 day | |
| **Week 2–3** | 4B | REST API — FastAPI server + 4 routes + streaming context endpoint | 2 days | |
| **Week 3** | 5.B | Context caching (in-memory, 5min TTL, keyed by query+repo+format) | half day | |
| **Week 3–4** | 5.C | Deduplication daemon job (weekly, merge near-duplicate summaries) | 1 day | |
| **Week 4** | 5.D | Related memories in hybrid_search output (no extra searches) | half day | |
| **Later** | 2.9b | Meeting Connector (full diarization with pyannote) | 2 days | |
| **Later** | 2.8, 2.10 | Copilot, Browser connectors | 1 day each | |
| **Later** | 5.2 | File Watcher (watchdog → filesystem events → auto-ingest) | 1 day | |
| **Deferred** | 3.2f–3.2i | tag, pin, audit, export commands | — | |
| **Future** | 7.3 | Git Hook Integration (`devmemory hook install/uninstall/status`) | half day | |
| **Future** | 7.4 | Semantic Diff Awareness (`DiffConnector`, `git_diff` memory type) | 1 day | |
| **Future** | 7.7 | ML Intent Classifier (SGDClassifier + TF-IDF, confidence-gated fallback) | 1 day | |
| **Future** | 7.1 | Local LLM / RAG (`devmemory ask`, Ollama/llama.cpp, `[llm]` extra) | 2 days | |
| **Future** | 7.2 | Memory Feedback Loop (save Q&A answers back as agent_solution memories) | half day | |
| **Future** | 7.8 | Codebase Map Generation (`devmemory map`, KMeans on stored vectors) | 1 day | |
| **Future** | 7.9 | Agent Mode (`devmemory plan`, git diff + memories + LLM) | 1 day | |
| **Future** | 7.5 | VSCode Extension (TypeScript, zero runtime deps, talks to REST API) | 2 days | |
| **Future** | 7.6 | Web UI (Svelte SPA at /ui, 5 tabs, 3 new API routes) | 3 days | |

**Explicitly deprioritized from old order:**
- `tag`, `pin`/`unpin`, `audit` commands — not on either primary goal track
- Phase 6.3 Memory Compression — too complex for current scale
- Phase 7.7 Intent Classification — simplified version pulled into Phase 5.A

---

## Testing Strategy

| Component | Test Approach | Status |
|---|---|---|
| Memory schema | Unit test: create objects, verify fields and defaults | ✅ 3 passing |
| MemoryStore | Unit test with temp LanceDB dir: add, search, delete, count | ⚠️ 1 failing (pandas) |
| Ranking | Unit test: verify scoring formula and sort order | ✅ 11 passing |
| Hybrid search | Integration test: insert diverse memories, verify keyword+semantic mix | ✅ 5 passing |
| Context engine | Integration test: verify token budget, dedup, format output | Not started |
| Each connector | Unit test with mock data (temp repos, fake history files, mock JSON) | Not started |
| Voice connector | Unit test with mocked `sd.rec` and `whisper.load_model`: noise gate (high `no_speech_prob` → 0), short transcript (< 4 words → 0), non-matching speaker → `voice_ambient`, matching speaker → `voice_note`, no profile → `voice_note` | Not started |
| Speaker profile | Unit test: save/load roundtrip, `is_self` with identical/orthogonal/boundary embeddings | Not started |
| Meeting connector | Unit test with mocked transcript + diarization + embeddings: verify `meeting_self`/`meeting_context` types, importance, tags, dedup | Not started |
| Privacy filter | Unit test: API key / bearer token patterns → `[REDACTED]`; clean text unchanged | Not started |
| Browser connector | Unit test with fixture Chrome JSON + minimal SQLite; verify `type="bookmark"`, `importance=0.6`, dedup | Not started |
| Tag management | Unit test: add/remove/list tags; `--tag` search filter returns only matching memories | Not started |
| Pin / Unpin | Unit test: pin a memory, run decay, verify its importance is unchanged | Not started |
| Export / Import | Round-trip test: export N memories to JSON, wipe store, import, verify count matches | Not started |
| Audit | Insert duplicate summaries, run audit, verify both issues are reported | Not started |
| REPL | Integration test: mock `input()` to feed queries, verify results are printed | Not started |
| Webhook | HTTP test with FastAPI TestClient: `POST /memory/ingest` creates memory; duplicate returns `"duplicate"` | Not started |
| CLI | End-to-end: run commands, verify stdout output | Not started |
| `MemoryStore.reinforce()` | Unit test: boost 0.5 → 0.55; cap at 1.0 from 0.98; no-op for unknown ID | Not started |
| Memory cleanup | Unit test: low-importance memories deleted; pinned skipped; old+weak deleted; high-importance kept; dry-run returns count without deletion | Not started |
| API | HTTP tests with FastAPI TestClient | Not started |
| Daemon | Integration test: verify connector runs produce new memories | Not started |

**Test totals:** 23 passing, 1 failing (out of 24 collected — `try_queries.py` not collected by pytest)

---

*Last updated: February 26, 2026 — Fixed Phase 1.6 status (PARTIALLY COMPLETE); added VoiceConnector quality gates (noise gate, speaker ID, registry exclusion) to Phase 2.9; added Phase 5.4 (Access Reinforcement + Memory Pruning); added `devmemory prune` CLI command; moved Phase 6.1 Importance Reinforcement to Phase 5.4A*
