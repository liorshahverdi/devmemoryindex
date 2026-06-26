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

## 12. MCP Tools (Hermes / Claude Code / Generic MCP)

Verify the MCP server is registered in the MCP client you use:

```bash
# Hermes Agent
hermes mcp test devmemory

# Claude Code, if configured
claude mcp list
```

**Expect:** `devmemory` listed/connected and 21 tools discovered.

Test each tool from an MCP-capable agent session. The examples below use tool-call pseudocode and are not tied to a single client:

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
**Expect:** Formatted `<context>` block, within token budget. For architecture/codebase-map queries, Graphify-derived `graphify_node` and `graphify_report` memories are boosted when present.

### 12c-graphify. Graphify code graph MCP tools

After importing a Graphify output directory:

```bash
devmemory graphify ingest /path/to/repo --with-edges
```

Use MCP tools:

```
search_code_graph(query="authentication architecture", repo="my-repo", k=5)
get_code_entity_context(node_or_query="AuthService", repo="my-repo", depth=1)
```

**Expect:** `search_code_graph` returns only `graphify_node` / `graphify_report` memories. `get_code_entity_context` returns `status="ok"`, a hydrated `root`, hydrated neighboring `nodes`, and imported `EdgeStore` `edges` with `source="graphify"` when edges were ingested.

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

### 12k. Score diagnostics and context exclusion
```
explain_score(memory_id="<id>", query="hybrid search ranking")
why_not_included(memory_id="<id>", query="hybrid search ranking")
```
**Expect:** Score/component details for included memories and a diagnostic reason for memories excluded by deduplication, token budget, or low match quality.

### 12l. Store health, consolidation, and forgetting
```
get_store_health()
consolidate_memories(ids=["<id1>", "<id2>"], summary="canonical fix for ranking")
forget_memory(memory_id="<bad-id>", reason="outdated workaround")
```
**Expect:** Health metrics include type breakdown/stale/low-CTR signals; consolidation creates a canonical memory; forgetting excludes the memory from future search while preserving an audit trail.

### 12m. Batch search and memory graph
```
search_batch(queries=["hybrid search", "ranking formula"])
link_memories(from_id="<symptom-id>", to_id="<fix-id>", edge_type="fixed_by")
get_memory_graph(memory_id="<fix-id>", depth=2)
trace_causality(memory_id="<fix-id>")
```
**Expect:** Batch search returns deduplicated merged results; graph tools return typed edges useful for root-cause or fix-chain reasoning.

---

## 12.5. Auto-Link Edge Inference (Phase 8.2)

These steps verify the Phase 8.2 graph expansion in `daemon/jobs/edge_inference.py`: test failures link to commits, similar stack traces across repos link to each other, and failures link to solutions by stack/error signature.

### 12.5a. Run the focused regression tests
```bash
uv run pytest daemon/tests/test_edge_inference.py -q
```
**Expect:** `3 passed`. These tests create an isolated temporary LanceDB store and verify:
- `failure_note` → `git_commit` `fixed_by` when the same pytest test identifier appears in both memories.
- Cross-repo `failure_note` → `failure_note` `related_to` when stack/error signatures match.
- `failure_note` → `agent_solution` `references` when a stack trace signature matches the saved solution.

### 12.5b. Run neighboring graph/daemon tests
```bash
uv run pytest \
  daemon/tests/test_edge_inference.py \
  daemon/tests/test_scheduler.py \
  core/tests/test_daemon_jobs.py \
  cli/tests/test_graph_cli.py \
  -q
```
**Expect:** All tests pass. This confirms the new heuristics still work with weekly daemon scheduling and graph CLI rendering.

### 12.5c. Manually seed a scratch memory DB
Use a scratch DB so local production memories are not modified:

```bash
SCRATCH_DB=/tmp/devmemory-edge-test
rm -rf "$SCRATCH_DB"

uv run python - <<'PY'
from datetime import datetime
from core.memory_store import MemoryStore, VECTOR_DIM
from core.schema import Memory

DB = "/tmp/devmemory-edge-test"
store = MemoryStore(DB)
vec = [0.1] * VECTOR_DIM

def add(id, type, summary, raw_text, repo):
    store.add(Memory(
        id=id,
        type=type,
        summary=summary,
        raw_text=raw_text,
        source="manual-edge-test",
        repo=repo,
        timestamp=datetime.utcnow(),
        tags=[],
        importance=0.7,
    ), vec)

add(
    "failure-login",
    "failure_note",
    "pytest test_login.py::test_refreshes_token_on_401 failed",
    "FAILED tests/test_login.py::test_refreshes_token_on_401 - AssertionError: expected token refresh",
    "api",
)
add(
    "commit-login",
    "git_commit",
    "Fix token refresh regression",
    "Fix failing tests/test_login.py::test_refreshes_token_on_401 by refreshing token on 401 responses",
    "api",
)
add(
    "failure-api",
    "failure_note",
    "Redis timeout in API user lookup",
    '''Traceback (most recent call last):
  File "app/cache.py", line 42, in get_user
    return client.fetch(user_id)
TimeoutError: Redis request timed out after 30s''',
    "api-service",
)
add(
    "failure-worker",
    "failure_note",
    "Redis timeout in worker user lookup",
    '''Traceback (most recent call last):
  File "worker/cache.py", line 19, in get_user
    return client.fetch(user_id)
TimeoutError: Redis request timed out after 30s''',
    "worker-service",
)
print("seeded", store.count(), "memories in", DB)
PY
```

**Expect:** `seeded 4 memories in /tmp/devmemory-edge-test`.

### 12.5d. Run edge inference against the scratch DB
```bash
uv run python - <<'PY'
from daemon.jobs.edge_inference import run_edge_inference
print(run_edge_inference('/tmp/devmemory-edge-test'))
PY
```
**Expect:** `edges_added` is at least `2`:
- one `fixed_by` edge from `failure-login` to `commit-login`
- one `related_to` edge between `failure-api` and `failure-worker`

Run it a second time:
```bash
uv run python - <<'PY'
from daemon.jobs.edge_inference import run_edge_inference
print(run_edge_inference('/tmp/devmemory-edge-test'))
PY
```
**Expect:** `edges_added` is `0` because duplicate edges are skipped.

### 12.5e. Inspect inferred edges directly
```bash
uv run python - <<'PY'
from core.edge_store import EdgeStore
for edge in EdgeStore('/tmp/devmemory-edge-test').get_all_edges():
    print(edge['from_id'], edge['edge_type'], edge['to_id'], edge['source'], round(edge['confidence'], 2))
PY
```
**Expect:** Output includes:
```text
failure-login fixed_by commit-login auto ...
failure-api related_to failure-worker auto ...
```

### 12.5f. Optional: inspect with graph CLI against an isolated DB
The CLI uses the default DB path, so only do this if you intentionally point your working directory at the scratch DB or temporarily copy the scratch DB into a disposable checkout. Prefer the direct `EdgeStore` inspection above for safe local verification.

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
uv run pytest daemon/tests/ -v        # daemon jobs, scheduler, edge inference, voice pipeline + formatter tests
uv run pytest daemon/tests/test_edge_inference.py -v
uv run pytest tests/test_packaging.py -v
```
**Expect:** All green.

---

## 17. Jarvis Mode — Voice Pipeline (Phase 8.1 + 8.3)

### Prerequisites

```bash
uv pip install -e '.[jarvis]'   # installs openwakeword, openai-whisper, sounddevice, edge-tts
ollama serve &                  # LLM backend for _answer()

# Download wake word model (one-time; requires internet)
python -c "from openwakeword.utils import download_models; download_models(['hey_jarvis'])"

# Enroll your voice (required for speaker gate)
uv run devmemory voice enroll
```

### 17a. Unit tests (no hardware required)

```bash
uv run pytest daemon/tests/ -v
```
**Expect:** 54 tests, all green, ~0.15s.

`test_voice_pipeline.py` (16 tests) covers:
- `ACTIVE → PASSIVE` on silence timeout
- `ACTIVE → PASSIVE` on each stop phrase (`stop`, `never mind`, `nevermind`, `goodbye`, `quit`, `bye`)
- Normal query flow: answer spoken, history recorded
- History capped at `MAX_HISTORY` (3 turns)
- `run()` consumes `detection_queue` events
- Speaker gate blocks unrecognised audio → PASSIVE (Phase 8.2)
- Speaker gate passes when no profile enrolled (fail-open)
- Speaker gate fail-open when `_verify_speaker` raises an exception

`test_response_formatter.py` (31 tests) covers:
- Empty / no-results → "Nothing on that."
- Long answer with no-results phrase in passing → kept
- Internal error → "Can't reach the store right now."
- Fenced code blocks stripped; inline backticks de-ticked
- File paths (`core/foo.py:42`) → basename (`foo.py`)
- ISO dates → relative phrases ("3 days ago", "yesterday", "last week")
- Sentence truncation to 3 max
- Future dates left unchanged

### 17b. Daemon startup — both threads start

```bash
uv run devmemory daemon start --jarvis
```
**Expect in log / stdout:**
```
Wake word listener started — say 'hey jarvis' to activate
[wake_word] Listening — model='hey_jarvis'  threshold=0.5  device=default mic
[pipeline] Voice pipeline running — waiting for wake word
Voice pipeline active — say 'hey jarvis' to start
```
If `openwakeword` is not installed you'll see a WARN and the pipeline will block indefinitely (wake word never fires). Fix: `uv pip install -e '.[jarvis]'`.

### 17c. Wake word detection

Say **"hey jarvis"** clearly into the default mic.

**Expect:**
- Two-tone chime plays (880 Hz → 1046 Hz)
- Log: `[wake_word] Detected — score=0.XX`
- Log: `[pipeline] Wake word — score=0.XX  entering ACTIVE`
- Log: `[pipeline] Listening for query…`

### 17d. Query → transcription → answer → TTS

While in ACTIVE state (after wake word), ask: *"What is LanceDB?"*

**Expect:**
- Log: `[pipeline] Transcribed: 'What is LanceDB?'`
- Log: `[pipeline] Answer: LanceDB is a vector...`
- TTS speaks the answer aloud

### 17e. Follow-up without re-triggering wake word

Immediately after the answer, ask: *"How is it different from Postgres?"* (no "hey jarvis")

**Expect:** Transcribes, answers, speaks — same flow, no new wake detection needed.
Log shows previous exchange was prepended as context.

### 17f. Stop phrase → PASSIVE

Say **"stop"** (or "never mind", "goodbye", "quit", "bye").

**Expect:**
- TTS speaks "Got it."
- Log: `[pipeline] Stop phrase detected → returning to PASSIVE`
- State returns to waiting for wake word

### 17g. Silence timeout → PASSIVE

Trigger wake word, then say nothing for 30 seconds.

**Expect:**
- Log: `[pipeline] Active window expired → returning to PASSIVE`
- No crash, no hung thread — pipeline resumes waiting for wake word cleanly

### 17h. Concurrent write safety

Run the daemon and observe the log for 10+ minutes across multiple connector cycles.

**Expect:** No `Append with different schema: missing=[times_retrieved, times_accessed]` errors.
Each connector run should log only `+N memories` or nothing (if no new data).

### 17i. Smoke-test pipeline logic (no mic, no LLM)

```bash
uv run python - <<'EOF'
import time
from unittest.mock import patch
import numpy as np
from daemon import wake_word as ww
from daemon.voice_pipeline import VoicePipeline

ww.detection_queue.put({"score": 0.9, "time": time.monotonic()})
p = VoicePipeline()

with patch("daemon.voice_pipeline._check_speaker", return_value=True):
    with patch("daemon.voice_pipeline._record_with_vad", side_effect=[
        np.ones(16000, dtype="float32") * 0.1,  # first call: audio
        None,                                    # second call: silence → exit
    ]):
        with patch("daemon.voice_pipeline._transcribe", return_value="What is LanceDB?"):
            with patch("daemon.voice_pipeline._answer", return_value="LanceDB is a vector DB."):
                with patch("daemon.voice_pipeline._speak", return_value=False):
                    p._enter_active()

print("State:", p._state)    # passive
print("History:", p._history)
EOF
```
**Expect:**
```
State: passive
History: [('What is LanceDB?', 'LanceDB is a vector DB.')]
```

### 17j. Speaker gate (Phase 8.2)

Requires an enrolled profile (`devmemory voice enroll`).

**Test A — recognised speaker:**
Trigger wake word, then speak a query in your own voice.

**Expect:**
- Log: `[speaker] cosine distance=0.XXXX  threshold=0.85` where distance < 0.85
- Log: `[pipeline] Speaker check: recognised`
- Query proceeds to transcription/answer/TTS

**Test B — unrecognised speaker:**
Trigger wake word, then play audio from a different speaker (or speak in an exaggerated different voice).

**Expect:**
- Log: `[pipeline] Speaker not recognised → returning to PASSIVE`
- TTS speaks "Do I know you?"
- Pipeline returns to PASSIVE without answering the query

**Test C — no profile enrolled (fail-open):**
Delete the profile (`rm ~/.config/devmemory/speaker_profile.pkl` or equivalent), trigger wake word, speak any query.

**Expect:** Query proceeds normally — no gate applied.

**Tuning note:** The speaker cosine distance threshold is `0.85` (`_voice.py`). If your voice is blocked at 0.85, check the logged distance and raise the threshold. Distances for the same speaker across different audio paths (enrollment vs pipeline subscriber) are typically 0.75–0.80; strangers are typically > 0.90.

### 17k. TTS interrupt on mid-response wake word

While the assistant is speaking a response, say **"hey jarvis"** again.

**Expect:**
- Audio playback stops immediately (within ~50 ms)
- Log: `[pipeline] TTS interrupted by wake word`
- Pipeline immediately records the next query (no need to wait for the full response)
- New query is answered and spoken

**Test the non-interrupt path:** Let a response play through to completion — `_speak()` returns `False`, deadline resets, pipeline continues normally.

### 17l. Daemon stop

```bash
uv run devmemory daemon stop
```
**Expect:**
```
Sent SIGTERM to PID(s): <pid>
```
Daemon process exits cleanly. Running `devmemory daemon stop` again immediately shows:
```
No running daemon found.
```

---

---

## 18. Score Explainability (T1-A)

### 18a. `score_breakdown` on every search result

```
search_memories(query="ranking formula", k=3)
```
**Expect:** Each result has a `score_breakdown` dict:
```json
{
  "semantic": 0.82,
  "importance": 0.70,
  "recency": 0.45,
  "final": 0.88
}
```
The three components multiplied by their weights (0.75/0.15/0.10) should sum to `final`.

### 18b. `explain_score` — why did this memory rank?

```
explain_score(
  memory_id="<id from search result>",
  query="hybrid search ranking"
)
```
**Expect:**
```json
{
  "id": "...",
  "summary": "...",
  "query": "hybrid search ranking",
  "score_breakdown": {"semantic": 0.79, "importance": 0.80, "recency": 0.60, "final": 0.83},
  "explanation": "Final score 0.831 = semantic(0.79) × 0.75 + importance(0.80) × 0.15 + recency(0.60) × 0.10. ..."
}
```

### 18c. `why_not_included` — debug missing memories

First find a memory ID that won't rank for a given query:
```
# Pick an unrelated memory ID from the store
why_not_included(memory_id="<an unrelated memory id>", query="redis timeout")
```
**Expect:** `"reason": "not_in_results"` with explanation about low semantic similarity.

To test budget-dropped: call with `max_tokens=50` on a store with many memories:
```
why_not_included(memory_id="<id that does rank>", query="ranking", max_tokens=50)
```
**Expect:** `"reason": "dropped_budget"` with explanation about token budget.

---

## 19. Retrieval Trace (T1-B)

### 19a. `build_context` returns dict with trace

```
result = build_context(query="context engine build", format="claude")
```
**Expect:** `result` is a dict, not a string:
```json
{
  "context_text": "<context>...</context>",
  "retrieval_trace": {
    "included": ["id1", "id2"],
    "dropped_dedup": ["id3"],
    "dropped_budget": [],
    "intent_detected": "implementation",
    "total_candidates": 15
  },
  "memory_count": 2,
  "token_estimate": 380
}
```

### 19b. CLI `devmemory context --json` includes trace

```bash
devmemory context "hybrid search" --json
```
**Expect:** JSON output contains `retrieval_trace` key with `included`, `dropped_dedup`, `dropped_budget`.

---

## 20. Memory Lifecycle — Forget & Audit (T1-D)

### 20a. Forget a memory

```bash
# Get an ID to deprecate
devmemory search "test" --limit 1
```
```
forget_memory(memory_id="<id>", reason="outdated — replaced by new approach")
```
**Expect:** `{"status": "ok", "id": "...", "reason": "outdated — replaced by new approach"}`.

### 20b. Forgotten memory excluded from search

```
# This memory should no longer appear
search_memories(query="<query that would have matched the memory>")
```
**Expect:** The deprecated memory is absent from all results.

### 20c. Audit CLI shows deprecated memories

```bash
devmemory audit
```
**Expect:** Table showing the deprecated memory with its ID, type, summary, and deprecation reason.

```bash
devmemory audit --json
```
**Expect:** JSON array with the same fields.

### 20d. Purge permanently deletes

```bash
devmemory audit --purge
```
**Expect:** `"Permanently deleted N deprecated memories."` Output. Running `devmemory audit` immediately after shows empty.

---

## 21. Store Health Dashboard (T1-E)

### 21a. CLI health report

```bash
devmemory health
```
**Expect:**
- Summary line: `Memory Store Health  (N total, N active, N deprecated)`
- Type breakdown table (git_commit, file_content, agent_solution, etc.)
- Importance distribution histogram (bars proportional to count)
- Stale count (memories never accessed, >60 days old)
- Low-CTR count (retrieved 5+ times, accessed <10% of the time)

### 21b. MCP tool returns structured dict

```
get_store_health()
```
**Expect:**
```json
{
  "total": 847,
  "active": 843,
  "deprecated": 4,
  "type_breakdown": {"git_commit": 312, "file_content": 280, ...},
  "importance_histogram": {"<0.3": 5, "0.3-0.5": 80, ...},
  "avg_times_accessed": 1.3,
  "stale_count": 12,
  "low_ctr_count": 3
}
```

---

## 22. Memory Consolidation (T1-C)

### 22a. Consolidate two memories

First add two similar memories:
```
id1 = remember_memory(
  summary="use /api/chat for Ollama RAG",
  raw_text="Always POST to /api/chat not /api/generate — proper role tokens",
  importance=0.7
)["id"]

id2 = remember_memory(
  summary="Ollama endpoint for instruction-tuned models",
  raw_text="Use /api/chat endpoint; /api/generate loses instruction formatting",
  importance=0.8
)["id"]
```

```
consolidate_memories(ids=[id1, id2])
```
**Expect:**
```json
{
  "status": "ok",
  "new_id": "...",
  "deleted": 2
}
```

The new memory should:
- Contain both raw_text blocks joined with a separator
- Have `importance = 0.8` (max of the originals)
- Include tags `consolidated`
- Be findable by searching for either original's keywords

Original IDs should no longer exist:
```
get_memory(id1)   # → null
get_memory(id2)   # → null
```

### 22b. CLI consolidate

```bash
devmemory consolidate <id1> <id2> --summary "canonical Ollama /api/chat pattern"
```
**Expect:** `Consolidated 2 memories into new memory <id16chars>...`

### 22c. Too few IDs

```
consolidate_memories(ids=["one-id"])
```
**Expect:** `{"status": "error", "message": "Need at least 2 valid memory IDs to consolidate"}`.

---

## 23. Batch Search (T1-F)

### 23a. Basic batch search

```
search_batch(queries=["redis timeout", "connection pool sizing", "retry backoff"], k=3)
```
**Expect:**
```json
{
  "results": [...],
  "total_unique": N,
  "query_count": 3
}
```
Each result has `source_queries` listing which of the 3 queries retrieved it.

### 23b. Deduplication works

A memory relevant to multiple queries should appear only once in `results`, with multiple entries in its `source_queries`.

### 23c. Results are sorted by score

`results[0]["score_breakdown"]["final"]` ≥ `results[1]["score_breakdown"]["final"]`

---

## 24. Auto-Summary on Ingest (T1-G)

### 24a. Enable the flag

```bash
# Add to ~/.config/devmemory/config.toml manually, or:
python -c "from core.config import set_auto_summarize; set_auto_summarize(True)"
```

### 24b. Remember a memory with no summary

```
remember_memory(
  summary="",
  raw_text="Always use exponential backoff with jitter when retrying HTTP calls to avoid thundering herd. Start at 1s, max 60s, jitter ±20%.",
  importance=0.8
)
```
**With Ollama running:** Summary should be an LLM-generated one-sentence description (not just the first 200 chars).
**Without Ollama:** Falls back to heuristic first-sentence extraction.

### 24c. Disable the flag

```python
from core.config import set_auto_summarize
set_auto_summarize(False)
```

---

## 25. Memory Entanglement — Edge Graph (T2-A)

### 25a. Create an edge

```
# First get two memory IDs
results = search_memories(query="lancedb schema", k=2)
id_a = results[0]["id"]
id_b = results[1]["id"]

link_memories(from_id=id_a, to_id=id_b, edge_type="references")
```
**Expect:** `{"status": "ok", "from": "...", "to": "...", "type": "references", "confidence": 1.0}`

Calling again with the same triple:
```
link_memories(from_id=id_a, to_id=id_b, edge_type="references")
```
**Expect:** `{"status": "duplicate", ...}`

### 25b. Invalid edge type

```
link_memories(from_id=id_a, to_id=id_b, edge_type="invented_type")
```
**Expect:** `{"status": "error", "message": "Invalid edge_type 'invented_type'. Valid: [...]"}`

### 25c. Failure → fix causal chain

```
# Simulate a failure note that was fixed by a commit
failure_id = remember_failure(
  summary="LanceDB table corrupt after partial delete",
  what_was_tried="collection.delete() without write lock",
  why_it_failed="concurrent Lance fragment writes"
)["id"]

fix_id = remember_memory(
  summary="Always acquire _write_lock before LanceDB delete",
  raw_text="Use threading.Lock() around all LanceDB writes to prevent corruption"
)["id"]

link_memories(from_id=failure_id, to_id=fix_id, edge_type="fixed_by")
```

### 25d. `get_memory_graph` returns subgraph

```
get_memory_graph(memory_id=failure_id, depth=2)
```
**Expect:**
```json
{
  "root": "<failure_id>",
  "nodes": ["<failure_id>", "<fix_id>"],
  "edges": [{"from_id": "...", "to_id": "...", "edge_type": "fixed_by", "confidence": 1.0, ...}],
  "node_count": 2,
  "edge_count": 1
}
```

### 25e. `trace_causality` follows the chain

```
trace_causality(memory_id=failure_id)
```
**Expect:**
```json
{
  "chain": [
    {"memory_id": "<failure_id>", "step": 0, "via_edge": null},
    {"memory_id": "<fix_id>", "step": 1, "via_edge": "fixed_by"}
  ],
  "length": 2,
  "root_cause_id": "<fix_id>"
}
```

### 25f. Auto-inference job

```bash
uv run python -m daemon.jobs.edge_inference
```
**Expect:** JSON output like `{"edges_added": N, "pairs_scanned": M}`. The job scans failure_notes vs commits/solutions for keyword overlap.

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
| `uv run pytest daemon/tests/ -v` | 54 tests green, ~0.15s |
| `uv run devmemory daemon stop` | "Sent SIGTERM to PID(s): …" or "No running daemon found." |
| `devmemory daemon start --jarvis` | Both "Wake word listener started" and "Voice pipeline active" in log |
| Say "hey jarvis" → ask question | Chime → transcribe → answer spoken → state returns to ACTIVE |
| Say "stop" mid-session | "Got it." spoken, log shows PASSIVE |
| 30s silence after wake | Log shows "Active window expired → returning to PASSIVE" |
| Daemon running 10+ min | No `missing=[times_retrieved, times_accessed]` errors in log |
| `search_memories(query="x")` | Each result has `score_breakdown: {semantic, importance, recency, final}` |
| `build_context(query="x")` | Returns dict with `context_text` + `retrieval_trace` — not a bare string |
| `explain_score(id, query)` | Returns `score_breakdown` + human-readable `explanation` string |
| `forget_memory(id, reason="test")` | `{"status":"ok"}` → memory absent from subsequent searches |
| `devmemory audit` | Shows the forgotten memory in a table |
| `devmemory health` | Shows type breakdown, importance histogram, stale/low-CTR counts |
| `consolidate_memories([id1, id2])` | `{"status":"ok", "deleted":2}` → originals gone, new merged memory present |
| `search_batch(queries=["a","b"])` | Returns deduplicated results with `source_queries` per entry |
| `link_memories(a, b, "fixed_by")` | `{"status":"ok"}`, second call returns `{"status":"duplicate"}` |
| `get_memory_graph(id, depth=2)` | Returns `{root, nodes, edges, node_count, edge_count}` |
| `trace_causality(id)` | Returns `{chain, length, root_cause_id}` |
| `uv run python -m daemon.jobs.edge_inference` | `{"edges_added": N, "pairs_scanned": M}` |
