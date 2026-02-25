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
| `core/memory_store.py` — MemoryStore class | **Done** | `add()`, `semantic_search()`, `delete()`, `count()`, `get_all()`. Legacy global functions removed. |
| `core/store_provider.py` — Singleton factory | **Done** | `get_store()` returns shared `MemoryStore` instance |
| `core/tests/test_schema.py` | **Done** | Memory creation, field validation, default importance |
| `core/tests/test_memory_store.py` | **Done** | Tests use `MemoryStore` class directly with `tmp_path` isolation. All 3 tests passing. |
| `core/tests/try_queries.py` | **Broken** | Still uses removed legacy functions (`save_memory`, `search_memory`). Needs migration to `MemoryStore`. |
| Project structure | **Done** | `core/`, `connectors/`, `cli/`, `api/`, `daemon/` directories created |
| LanceDB with explicit schema + timestamp("us") | **Done** | Proper Arrow types, 384-dim vector field |

**What's empty:** `connectors/`, `cli/`, `api/`, `daemon/` — all currently have no files.

---

## Target Architecture

```
                    ┌──────────────────────┐
                    │      CONNECTORS      │
                    │  git · terminal ·    │
                    │  files · notes ·     │
                    │  claude · copilot    │
                    └──────────┬───────────┘
                               │
                        MemoryStore (core)
                     add / search / rank
                               │
        ┌──────────┬───────────┼───────────┬──────────┐
        │          │           │           │          │
       CLI        API        Daemon     Context    Tests
     (human)   (agents)   (background)  Engine
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
│   └── copilot_connector.py   # VSCode Copilot chat (best-effort)
│
├── cli/
│   ├── main.py                # Typer entrypoint
│   └── commands/
│       ├── search.py          # devmemory search "query"
│       ├── ingest.py          # devmemory ingest [--source git|terminal|all]
│       ├── context.py         # devmemory context "query" [--json] [--copy] [--repo]
│       ├── add.py             # devmemory add (manual memory)
│       ├── stats.py           # devmemory stats
│       └── daemon_cmd.py      # devmemory daemon start
│
├── api/
│   ├── server.py              # FastAPI app
│   └── routes/
│       ├── search.py          # POST /search
│       ├── memory.py          # POST /remember
│       └── context.py         # POST /context
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

**Remaining cleanup:** `core/tests/try_queries.py` still references the removed legacy functions and will fail if run. It needs to be migrated to use `MemoryStore`.

---

### 1.2 Create Store Provider (singleton) ✅

**Status: COMPLETED**

**File:** `core/store_provider.py`

Implemented as designed — `get_store(db_path)` returns a singleton `MemoryStore` instance. All future subsystems (CLI, API, connectors, daemon) will import `get_store()` instead of creating `MemoryStore` directly.

---

### 1.3 CLI Bootstrap (Scaffold + First Commands)

> **Why now?** The CLI entrypoint and at least one working command should exist as soon as the core engine is functional. This gives you a usable `devmemory` command immediately — you don't need connectors, the API, or the daemon to start searching and adding memories from the terminal.

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

> **Note:** Uses `semantic_search()` for now. After Phase 1.5 (hybrid search), update this to call `hybrid_search()` instead.

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

## stopPed hErE ##

**Upgrade path:** After Phase 1.5 (hybrid search), update `cli/commands/search.py` to call `store.hybrid_search(query, vector, k=...)` instead of `store.semantic_search(vector, k=...)`.

---

### 1.4 Implement Ranking Module

**File:** `core/ranking.py`

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

**Tests:** Create `core/tests/test_ranking.py` — verify that newer + higher-importance memories outrank older + lower-importance ones for equal similarity.

**Done when:** `compute_score()` returns a float and ranking order matches intuition.

---

### 1.5 Implement Hybrid Search

**Add to `MemoryStore` class in `core/memory_store.py`:**

```python
from core.ranking import compute_score

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

    # 4. Score and rank
    ranked = sorted(combined.values(), key=compute_score, reverse=True)

    return ranked[:k]
```

**Tests:** Create `core/tests/test_hybrid_search.py`:
- Insert memories with overlapping keywords and varying importance.
- Query with a keyword that appears in summary — verify it surfaces even if embedding similarity is mediocre.
- Verify deduplication (same memory from both paths appears only once).

**Done when:** `hybrid_search()` returns better results than `semantic_search()` alone for developer-specific queries.

---

### 1.6 Implement Context Engine

**File:** `core/context_engine.py`

This is the bridge between DevMemoryIndex and AI agents. It converts ranked memories into a token-budget-aware, formatted context block.

```python
from core.memory_store import MemoryStore
from core.embeddings import embed

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

        # 4. Pack within token budget
        selected = []
        token_count = 0
        for mem in candidates:
            est_tokens = len(mem["summary"].split()) + 20  # overhead
            if token_count + est_tokens > max_tokens:
                break
            selected.append(mem)
            token_count += est_tokens
            if len(selected) >= max_memories:
                break

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

**File:** `core/token_budget.py` (helper, used above inline but extractable later)

```python
def estimate_tokens(text: str) -> int:
    return len(text.split())  # rough ~1 token per word estimate
```

**Tests:** Create `core/tests/test_context_engine.py`:
- Build context for a known query — verify output contains expected memories.
- Test token budget is respected (insert 50 memories, set max_tokens=200, verify truncation).
- Test repo filter — only memories from specified repo appear.
- Test each format mode ("raw", "claude", "markdown") produces valid output.

**Done when:** `ContextEngine.build("redis timeout")` returns a structured dict with formatted context text, token estimate, and list of selected memories.

---

### 1.7 Content Hashing for Incremental Indexing

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

## Phase 2 — Connectors (Memory Ingestion)

> **Goal:** DevMemoryIndex automatically captures developer knowledge from
> six sources. Each connector inherits from a base class, creates Memory objects,
> embeds them, and saves them through MemoryStore.

### 2.1 Connector Base Class

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

### 2.2 Connector Registry

**File:** `connectors/registry.py`

```python
from connectors.git_connector import GitConnector
from connectors.terminal_connector import TerminalConnector
from connectors.filesystem_connector import FilesystemConnector
from connectors.markdown_connector import MarkdownConnector
from connectors.claude_connector import ClaudeConnector
from connectors.copilot_connector import CopilotConnector

ALL_CONNECTORS = [
    GitConnector,
    TerminalConnector,
    FilesystemConnector,
    MarkdownConnector,
    ClaudeConnector,
    CopilotConnector,
]

def get_connectors(names: list[str] | None = None) -> list:
    if names is None:
        return [C() for C in ALL_CONNECTORS]
    return [C() for C in ALL_CONNECTORS if C.name in names]
```

**Done when:** `get_connectors()` returns instantiated connector list. `get_connectors(["git"])` returns only GitConnector.

---

### 2.3 Git Connector

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

### 2.4 Terminal History Connector

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

### 2.5 Filesystem Connector

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

### 2.6 Markdown / Notes Connector

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

### 2.7 Claude Code Connector

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

**Note:** The exact file format of Claude Code's local storage may vary. This connector should be adapted once you inspect the actual files in `~/.claude/`. The structure above handles both JSON conversation logs and markdown exports.

**Tests:** Create mock JSON/markdown conversation files, run connector, verify assistant messages are stored with importance 0.9.

**Done when:** Past Claude Code solutions appear in `devmemory search "auth middleware"`.

---

### 2.8 Copilot Chat Connector (Best-Effort)

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

## Phase 3 — CLI (Human Interface)

> **Goal:** A developer can operate DevMemoryIndex entirely from the terminal,
> like using `git` — no Python scripts needed.
>
> The CLI is built **incrementally across phases**, not all at once:
>
> | Command | Earliest Phase | Why |
> |---|---|---|
> | `devmemory search` | Phase 1 | Only needs `MemoryStore` + `embed()` |
> | `devmemory add` | Phase 1 | Only needs `MemoryStore` + `embed()` |
> | `devmemory stats` | Phase 1 | Only needs `MemoryStore` |
> | `devmemory context` | Phase 1 (after 1.6) | Needs `ContextEngine` |
> | `devmemory ingest` | Phase 2 | Needs connectors |
> | `devmemory daemon` | Phase 5 | Needs `daemon/scheduler.py` |
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

## Phase 4 — API (Agent Interface)

> **Goal:** AI agents (Claude Code, local LLMs, custom scripts) can query
> DevMemoryIndex over HTTP to get persistent developer memory.

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

## Phase 5 — Daemon (Automation)

> **Goal:** Memories appear automatically without running manual commands.
> The daemon runs connectors on a schedule and watches for filesystem changes.

### 5.1 Scheduler

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

### 5.2 File Watcher (Optional Enhancement)

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

### 5.3 Importance Decay Job

**File:** `daemon/jobs/importance_decay.py`

```python
from core.store_provider import get_store

def decay_importance(factor: float = 0.99):
    """Reduce importance of all memories slightly. Run daily."""
    store = get_store()
    try:
        df = store.collection.to_pandas()
        df["importance"] = df["importance"] * factor
        # Rewrite (LanceDB overwrite pattern)
        store.collection.merge_insert(df)
    except Exception:
        pass  # Non-critical job
```

**Done when:** `devmemory daemon` runs continuously, automatically ingests new data, and memories decay in importance over time.

---

## Phase 6 — Intelligence Layer (Post-Launch)

> These features turn DevMemoryIndex from a memory store into a cognitive system.
> Build these after Phases 1–5 are working and you use the tool daily.

### 6.1 Importance Reinforcement
When a memory is retrieved via search or context, boost its importance:
```python
def reinforce(self, memory_id: str, boost: float = 0.05):
    # Increase importance (cap at 1.0)
```

### 6.2 Memory Deduplication
Periodically scan for near-duplicate memories (similar summary text) and merge them, keeping the higher-importance version.

### 6.3 Memory Compression
Summarize old, low-importance memories into condensed versions. Store both original and compressed. Use compressed for context to save tokens.

### 6.4 Related Memories
After retrieving a memory, find its nearest neighbors and surface them as "related". This creates a knowledge graph effect.

### 6.5 Auto-Context (No Query Required)
New CLI command: `devmemory suggest`
- Reads the current `git diff` or staged changes.
- Automatically builds relevant context without the user writing a query.
- Useful for pre-populating Claude Code with project context.

### 6.6 Context Caching
Cache the result of `ContextEngine.build()` keyed by `hash(query + repo)`. Invalidate when new memories are added. Avoids re-embedding and re-searching for repeated queries.

### 6.7 Multi-Project Namespace
Add a `project` field to Memory schema. Allow queries scoped to a project:
```bash
devmemory search "auth" --project api-gateway
```

---

## Phase 7 — Advanced Features (Future Vision)

> These are longer-term enhancements for when DevMemoryIndex has active users.

### 7.1 Local LLM Integration (RAG Answers)
Connect to Ollama or llama.cpp. Pipeline: query → retrieve memories → LLM generates answer citing sources.
```bash
devmemory ask "how does auth work in this project?"
```

### 7.2 Memory Feedback Loop
Save LLM-generated answers back into memory. The system literally learns from its own answers over time.

### 7.3 Git Hook Integration
Auto-index on every commit without needing the daemon:
```bash
# .git/hooks/post-commit
devmemory ingest --source git
```

### 7.4 Semantic Diff Awareness
Store before/after state of code changes. Enables queries like "why did we remove Redis?" by understanding the delta, not just the commit message.

### 7.5 VSCode Extension
Minimal extension that adds a "Ask DevMemory" command. Sends selected code or current error to the API, returns relevant context inline.

### 7.6 Web UI (Svelte)
Local web dashboard with:
- Search bar
- Memory timeline (browse by date)
- Chat window (RAG interface)
- Context viewer
- Memory stats and graphs

### 7.7 Intent Classification
Detect whether a query is about debugging, architecture, refactoring, or explanation. Route to different retrieval strategies per intent.

### 7.8 Codebase Map Generation
Use embeddings to automatically cluster files and modules. Generate a visual map: `Auth → Database → API → Frontend`.

### 7.9 Agent Mode
```bash
devmemory plan "add websocket multiplayer"
```
Uses memory + repo knowledge + LLM to generate a multi-step implementation plan.

---

## Execution Order Summary

| Priority | Phase | What You Build | Depends On |
|---|---|---|---|
| **Now** | 1.1–1.2 | Finish MemoryStore class, store provider | Schema + embeddings (done) |
| **Now** | 1.3 | **CLI scaffold + `search`, `add`, `stats` commands** | Phase 1.1–1.2 |
| **Now** | 1.4–1.5 | Ranking module, hybrid search | Phase 1.1 |
| **Now** | 1.6–1.7 | Context engine, content hashing | Phase 1.4–1.5 |
| **Now** | 3.2b | **CLI `context` command** | Phase 1.6 |
| **Next** | 2 | Connectors (git, terminal, filesystem, markdown, claude, copilot) | Phase 1.7 |
| **Next** | 3.2a | **CLI `ingest` command** | Phase 2 |
| **Next** | 4 | API (search, remember, context endpoints) | Phase 1.6 |
| **Next** | 5 | Daemon (scheduler, watcher, decay) | Phase 2 |
| **Next** | 5+3.2c | **CLI `daemon` command** | Phase 5 |
| **Later** | 6 | Intelligence (reinforcement, dedup, compression, auto-context) | Phases 1–5 |
| **Future** | 7 | Advanced (LLM, VSCode, web UI, agent mode) | Phases 1–6 |

---

## Testing Strategy

| Component | Test Approach |
|---|---|
| Memory schema | Unit test: create objects, verify fields and defaults |
| MemoryStore | Unit test with temp LanceDB dir: add, search, delete, count |
| Ranking | Unit test: verify scoring formula and sort order |
| Hybrid search | Integration test: insert diverse memories, verify keyword+semantic mix |
| Context engine | Integration test: verify token budget, dedup, format output |
| Each connector | Unit test with mock data (temp repos, fake history files, mock JSON) |
| CLI | End-to-end: run commands, verify stdout output |
| API | HTTP tests with FastAPI TestClient |
| Daemon | Integration test: verify connector runs produce new memories |

---

*Last updated: February 2026*
