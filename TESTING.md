# DevMemoryIndex — Step-by-Step Testing Guide

## Prerequisites

```bash
cd ~/projects/devmemoryindex
source .venv/bin/activate   # or: uv run devmemory ...
```

Ollama must be running for `ask` tests:
```bash
ollama serve &   # skip if already running
```

---

## 1. Basic Search

### 1a. Text search
```bash
devmemory search "hybrid search"
```
**Expect:** Table with results, 8-char ID prefix column, Score column. Results should include `memory_store.py` chunks.

### 1b. Type filter
```bash
devmemory search "git" --type git_commit
```
**Expect:** Only `git_commit` type rows.

### 1c. Repo filter
```bash
devmemory search "context engine" --repo devmemoryindex
```
**Expect:** Only memories with `repo=devmemoryindex`.

### 1d. Voice search (if mic available)
```bash
devmemory search --voice
```
**Expect:** 3-second countdown → records → transcribes → prints "Searching for: <text>" → results table.

---

## 2. Ingest

### 2a. Full ingest
```bash
devmemory ingest --source all
```
**Expect:** Progress messages per connector. Final line shows counts. Should report `0 new` for already-indexed memories (idempotent).

### 2b. Single connector
```bash
devmemory ingest --source git
devmemory ingest --source filesystem
```

### 2c. Clear + re-index file_content
```bash
devmemory ingest --source filesystem --clear
```
**Expect:** All previous `file_content` memories deleted, then re-indexed with updated summaries (definition-enriched: `· class ContextEngine, def build`).

---

## 3. Stats

```bash
devmemory stats
```
**Expect:** Total count + type breakdown table (git_commit, file_content, terminal_command, agent_solution, voice_note, etc.).

---

## 4. Ask — Query Planner Routing

These verify that `_quick_route()` picks the right type deterministically.

### 4a. Temporal → `git_commit`
```bash
devmemory ask "when did we add the filesystem connector?" --model llama3.2:1b
```
**Expect:** Dim hint line shows `[git_commit]`. Answer includes a date (from the `Date:` field in the memory prompt).

### 4b. Implementation → `file_content`
```bash
devmemory ask "how does context engine work?" --model llama3.2:1b
```
**Expect:** Hint shows `[file_content] ContextEngine context_engine`. Answer describes the actual `ContextEngine` class (not test code). Should cite `core/context_engine.py`.

### 4c. Decision → `agent_solution`
```bash
devmemory ask "why did we choose DuckDB for keyword search?" --model llama3.2:1b
```
**Expect:** Hint shows `[agent_solution]`. Answer pulls from ROADMAP notes or agent_solution memories.

### 4d. Command → `terminal_command`
```bash
devmemory ask "how do I run the daemon?" --model llama3.2:1b
```
**Expect:** Hint shows `[terminal_command]`. Answer shows the `devmemory daemon start` command.

### 4e. Failure/avoid → `failure_note`
```bash
devmemory ask "what went wrong when we tried to use --amend?" --model llama3.2:1b
```
**Expect:** Hint shows `[failure_note]` (if any failure_note memories exist).

### 4f. Ambiguous → LLM routing fallback
```bash
devmemory ask "tell me about the ranking formula" --model llama3.2:1b
```
**Expect:** No quick-route match → LLM planner fires → routes to an appropriate type.

### 4g. Disable planner
```bash
devmemory ask "how does MemoryStore work?" --model llama3.2:1b --no-plan
```
**Expect:** No dim hint. Straight retrieval without reformulation.

---

## 5. Ask — Voice + Speak

```bash
# Ask with voice input (speaks back the answer)
devmemory ask --voice --speak --model llama3.2:1b --voice-duration 5
```
Say: *"how does the context engine work"*

**Expect:**
- Transcribes to lowercase
- Routes to `file_content` via `_CODE_IMPL_RE` (voice-safe CamelCase synthesis: `ContextEngine context_engine`)
- Streams answer, speaks each sentence aloud as it's generated

```bash
# Ask with voice + type override
devmemory ask --voice --model llama3.2:1b --type git_commit
```
Say: *"when did we add the diff connector"*

**Expect:** Uses `git_commit` type regardless of planner.

---

## 6. Ask — Save Answer

```bash
devmemory ask "what is the purpose of the token budget?" --model llama3.2:1b --save
```
**Expect:** After streaming, prints `Saved memory: <id>`.

Verify it was stored:
```bash
devmemory search "token budget purpose" --type agent_solution
```
**Expect:** The Q&A memory appears.

---

## 7. Context Command

```bash
devmemory context "hybrid search ranking"
devmemory context "context engine" --format claude
devmemory context "memory store" --format markdown --tokens 500
devmemory context "ranking" --json
devmemory context "query planner" --copy   # copies to clipboard
```
**Expect:** Each format mode produces the correct output structure. `--tokens` limits the budget. `--json` produces valid JSON.

---

## 8. Suggest Command

```bash
# Run inside a git repo with uncommitted changes:
git diff HEAD    # verify there's a diff
devmemory suggest
```
**Expect:** Reads `git diff HEAD`, retrieves relevant memories, prints them as context block. Useful before asking an LLM for help.

---

## 9. Codebase Map (`devmemory map`)

### 9a. Basic map
```bash
devmemory map --repo devmemoryindex
```
**Expect:** Rich table with columns `Label`, `Files`, `Representative`. Labels should be directory names (`core`, `cli`, `connectors`, `api`, `daemon`) not OS paths. `total_files` count shown in header.

### 9b. Adjust cluster count
```bash
devmemory map --repo devmemoryindex --clusters 10
```
**Expect:** Up to 10 clusters (fewer if not enough files). Labels should partition the repo into finer-grained subsystems.

### 9c. Verbose mode (list all files per cluster)
```bash
devmemory map --repo devmemoryindex --verbose
```
**Expect:** Same table, then per-cluster file lists below it showing all member files.

### 9d. No repo filter (all file_content memories)
```bash
devmemory map
```
**Expect:** Clusters across all repos in the store.

### 9e. Error case (no file_content memories for repo)
```bash
devmemory map --repo doesnotexist
```
**Expect:** Red error message: "Not enough file_content memories to cluster".

---

## 10. Plan Tool (`devmemory plan`)

### 10a. Basic plan
```bash
devmemory plan "add rate limiting middleware to the REST API"
```
**Expect:** `Using N memories. Generating plan via LLM...` → Rich-rendered numbered markdown plan. Plan should mention specific files (`api/routes/`, `api/server.py`) and steps.

### 10b. Plan with repo filter
```bash
devmemory plan "fix hybrid search scoring" --repo devmemoryindex
```
**Expect:** Memory retrieval restricted to `devmemoryindex`. Plan references `core/memory_store.py`, `core/ranking.py`.

### 10c. Plan with file hints
```bash
devmemory plan "refactor context engine" \
  --file core/context_engine.py \
  --file core/memory_store.py
```
**Expect:** Query enriched with file signals (import keywords, path components). Plan cites the specified files.

### 10d. Save plan as memory
```bash
devmemory plan "add API key rotation" --save
```
**Expect:** Plan rendered, then: `Saved plan as memory <8-char-id>`. Verify:
```bash
devmemory search "API key rotation plan" --type agent_solution
```
**Expect:** The plan appears.

### 10e. LLM not available
```bash
# Stop Ollama first: pkill ollama
devmemory plan "anything"
```
**Expect:** Red error: `LLM backend error: ...`. Exit code 1.

---

## 11. Memory Lifecycle

### 11a. Manual add
```bash
devmemory add
```
Fill in the prompts. Then:
```bash
devmemory search "<your summary text>"
```

### 11b. Get by ID
```bash
# Copy an 8-char ID prefix from search results
devmemory get <8-char-prefix>
```
**Expect:** Full metadata panel + raw_text panel.

### 11c. Prune (dry run)
```bash
devmemory prune --dry-run
```
**Expect:** Lists memories that would be deleted (importance < 0.05 or old+unimportant). No actual deletion.

---

## 12. MCP Tools (Claude Code Integration)

Verify the MCP server is registered:
```bash
claude mcp list
```
**Expect:** `devmemory` listed.

Test each tool in a Claude Code session:

### 12a. `get_session_context` (call at session start)
```
get_session_context("fix hybrid search ranking bug")
```
**Expect:** Returns `<context>...</context>` block with memories about memory_store, ranking, hybrid_search. Should include git signal from modified files.

### 12b. `search_memories`
```
search_memories(query="context engine build", k=3)
```
**Expect:** Top 3 memories with `id`, `summary`, `type`, `related[]`, `times_retrieved`, `times_accessed` fields. A high `times_accessed` relative to `times_retrieved` signals a proven solution.

### 12c. `build_context`
```
build_context(query="how does query planning work", format="claude", max_tokens=2000)
```
**Expect:** Formatted `<context>` block, within token budget.

### 12d. `remember_memory`
```
remember_memory(
  summary="use /api/chat not /api/generate for RAG answers",
  raw_text="...",
  tags=["ollama", "rag"]
)
```
**Expect:** `{"status": "ok", "id": "..."}`. Second call returns `{"status": "duplicate", ...}`.

### 12e. `remember_failure`
```
remember_failure(
  summary="tried flat distance=0.0 for all keyword hits",
  what_was_tried="assign _distance=0.0 to every keyword match",
  why_it_failed="all hits tied, sorted by recency only — wrong memory ranked first"
)
```
**Expect:** `{"status": "ok", "id": "..."}`.

Then verify failure_note ranking suppression:
```
search_memories(query="keyword hits distance")
```
**Expect:** `failure_note` memory ranked LOW (score penalized 0.4× unless query is negative-intent).

```
search_memories(query="what went wrong with keyword distance scoring")
```
**Expect:** `failure_note` appears near top (negative-intent keywords lift the penalty).

### 12f. `get_memory`
```
get_memory(memory_id="<id from search result>")
```
**Expect:** Full memory dict with `raw_text`.

### 12g. `update_memory`
```
update_memory(
  memory_id="<id from search result>",
  summary="Corrected: use /api/chat not /api/generate for RAG answers",
  importance=0.85
)
```
**Expect:** `{"status": "ok", "id": "..."}`. Then call `get_memory(id)` to verify the new summary and importance are stored. `times_retrieved` and `times_accessed` should be preserved from before the update.

Not-found case:
```
update_memory(memory_id="0000000000000000", summary="test")
```
**Expect:** `{"status": "not_found"}`.

### 12h. `reinforce_memory`
```
reinforce_memory(memory_id="<id from search result>")
```
**Expect:** `{"status": "ok", "id": "...", "new_importance": <old + 0.05 capped at 0.95>}`.

Repeated calls:
```
reinforce_memory(memory_id="<same id>")
reinforce_memory(memory_id="<same id>")
```
**Expect:** `new_importance` increases by 0.05 each time, never exceeds 0.95.

Not-found case:
```
reinforce_memory(memory_id="0000000000000000")
```
**Expect:** `{"status": "not_found"}`.

### 12i. `get_codebase_map`
```
get_codebase_map(repo="devmemoryindex", n_clusters=6)
```
**Expect:** Dict with `clusters` list and `total_files` count. Each cluster has `label`, `size`, `representative`, `files[]`. Labels should be directory names like `core`, `cli`, `connectors`, `api`, `daemon` — not OS path prefixes like `Users`.

No file_content memories:
```
get_codebase_map(repo="nonexistent-repo")
```
**Expect:** `{"clusters": [], "total_files": 0, "error": "Not enough file_content memories..."}`.

### 12j. `plan_task`
```
plan_task(
  description="add rate limiting middleware to the REST API",
  repo="devmemoryindex"
)
```
**Expect:** `{"plan": "<numbered markdown plan>", "memory_count": N}`. Plan should reference relevant past memories and list specific files to modify.

With files:
```
plan_task(
  description="fix hybrid search scoring",
  repo="devmemoryindex",
  files=["/Users/lshahverdi/projects/devmemoryindex/core/memory_store.py"]
)
```
**Expect:** `memory_count` reflects file-enriched query. Plan mentions `hybrid_search()` and `compute_score()`.

LLM not available:
```
plan_task(description="anything")
```
(with Ollama stopped)
**Expect:** `{"plan": "", "memory_count": N, "error": "LLM backend error: ..."}`.

---

## 13. Config Management

```bash
devmemory config list
```
**Expect:** Git repos, scan dirs, markdown dirs, connector schedules table, LLM config.

```bash
devmemory config add-code ~/projects/myapp
devmemory config remove-code ~/projects/myapp
devmemory config add-notes ~/notes
devmemory config set-schedule git 300
```

---

## 14. Daemon

```bash
devmemory daemon start    # foreground, Ctrl-C to stop
devmemory daemon status
devmemory log -n 20       # tail last 20 daemon log lines
devmemory log --path      # print log file path for tail -f
```

---

## 15. Export / Import

```bash
devmemory export --out /tmp/memories_backup.json
# In another environment:
devmemory import /tmp/memories_backup.json
```
**Expect:** Export produces valid JSON array. Import skips duplicates.

---

## 16. Run Tests

```bash
uv run pytest core/tests/ -v          # all core tests
uv run pytest core/tests/test_hybrid_search.py -v
uv run pytest core/tests/test_ranking.py -v
uv run pytest core/tests/test_context_engine.py -v
uv run pytest api/tests/test_auth.py -v
```
**Expect:** All green.

---

## Quick Sanity Checklist

| Command | Green if... |
|---|---|
| `devmemory stats` | Total > 0, multiple types shown |
| `devmemory search "memory store"` | `memory_store.py` chunks appear |
| `devmemory search "FileSystemConnector"` | `filesystem_connector.py` appears (case-insensitive) |
| `devmemory ask "how does context engine work?" --model llama3.2:1b` | Hint = `[file_content]`, answer describes `ContextEngine.build()` |
| `devmemory ask "when did we add the diff connector?" --model llama3.2:1b` | Hint = `[git_commit]`, answer has a date |
| `devmemory map --repo devmemoryindex` | Table with labels like `core`, `cli`, `connectors` — not `Users` |
| `devmemory plan "add rate limiting" --repo devmemoryindex` | Numbered markdown plan citing specific files |
| MCP `search_memories(query="ranking formula")` | Returns `core/ranking.py` chunk with `times_retrieved`, `times_accessed` fields |
| MCP `get_session_context("debug ranking")` | Returns `<context>` block |
| MCP `update_memory(id, summary="fixed summary")` | `{"status": "ok"}`, `get_memory(id)` shows new summary |
| MCP `reinforce_memory(id)` | `{"status": "ok", "new_importance": N}`, N ≤ 0.95 |
| MCP `get_codebase_map(repo="devmemoryindex")` | Clusters with directory-name labels, `total_files` > 0 |
| MCP `plan_task(description="fix scoring")` | `{"plan": "<text>", "memory_count": N}` |
