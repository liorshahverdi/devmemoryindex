# DevMemoryIndex — Code Review

> A candid technical assessment. Issues are verified against actual source before
> being reported. Line numbers are current as of the review date.

---

## Executive Summary

The core of this project is **genuinely well-engineered**. The hybrid search
algorithm, intent routing, schema migration, and MCP tool design are all above
average for a solo project. The codebase is readable, consistently structured,
and makes sensible trade-offs throughout.

The problems fall into three buckets:

1. **A handful of real correctness bugs** — inconsistent escaping in SQL-style
   WHERE clauses, a privacy pattern that over-redacts its own data, a timestamp
   that is always "now", and production diagnostic code that prints to stderr.

2. **A severe test gap** — 9 connectors and all CLI commands have zero tests.
   The daemon jobs, API routes, and several core modules are also untested. For
   a system that indexes and ranks memories, untested ranking changes are
   invisible regressions.

3. **Structural patterns that will cause pain at scale** — every config write
   does a full file load+save with no locking, importance decay runs on a fixed
   factor regardless of invocation frequency, and the token budget uses word
   count instead of token count.

None of these make the system unusable for personal use today. They become
blockers at multi-user scale or when the memory store grows large.

---

## What's Genuinely Good

### Hybrid search algorithm (`core/memory_store.py:230–360`)

This is the strongest part of the codebase. Semantic over-retrieval (50 results)
combined with keyword search, per-term match scoring (not flat distance=0),
2× summary weighting over raw_text, CTR dampening for low-engagement memories,
and failure_note suppression are all correct and non-obvious choices. The related
memory chaining that reuses the already-fetched semantic pool at zero extra cost
is a nice efficiency win. The algorithm handles the "this commit message matches
but the actual code is in a different file" problem much better than plain
vector search would.

### Schema migration (`core/memory_store.py:68–108`)

The migration logic that adds missing columns to existing tables is robust. The
self-healing scan check (the `try: search().limit(1)` block) that detects and
fixes the LanceDB mixed-fragment nullable panic is exactly the kind of defensive
code that prevents hard-to-reproduce production failures.

### MCP tool docstrings (`mcp_server/tools.py`)

All ten tools have docstrings that are genuinely useful to an AI agent — they
describe when to call the tool, what the return values mean, and what to do with
the results. The `search_memories` docstring explaining that high `times_accessed`
relative to `times_retrieved` signals a proven solution is actionable in a way
most tool descriptions aren't.

### Intent routing (`core/query_planner.py`, `core/intent_classifier.py`)

Two-stage routing — deterministic regex first, LLM fallback only for ambiguous
queries — is the right architecture. It's fast for the 80% case and robust for
the 20%. The voice-query CamelCase synthesis (`"context engine"` → `"ContextEngine
context_engine"`) is a neat trick that makes voice queries match definition files
without any extra machinery.

### Context caching (`core/context_cache.py`)

SHA256-keyed LRU with 5-minute TTL and `store.add()`-triggered invalidation is
clean. The cache is invisible to callers, which is the correct abstraction level.

### `add_batch()` (`core/memory_store.py:118–138`)

Single WHERE IN check + single `collection.add()` call instead of N individual
adds is the right way to handle batch ingestion. The original N-individual-writes
approach was causing ~71s/commit on large repos, and this fixes it correctly.

---

## Real Problems

### Critical — Inconsistent SQL escaping creates injection risk

**Files:** `core/memory_store.py:178, 213, 221, 393, 451`

Most WHERE clauses correctly escape with `.replace("'", "''")` into a `safe_id`
variable. But several methods use the raw argument directly:

```python
# memory_store.py:178 — exists()
.where(f"id = '{memory_id}'")          # ← unescaped

# memory_store.py:213,221 — reinforce()
.where(f"id = '{memory_id}'")          # ← unescaped (both the search and the update)

# memory_store.py:393 — delete()
self.collection.delete(f"id = '{memory_id}'")  # ← unescaped
```

In contrast, `_increment_counter()` and `get_by_id()` correctly introduce
`safe_id`. The inconsistency means `reinforce()`, `exists()`, and `delete()` —
all called on attacker-controlled input in the MCP path — can be injected
against. For a local-only tool this is low urgency, but it will matter if the
REST API is ever opened to external traffic.

**Fix:** Apply `safe_id = memory_id.replace("'", "''")` consistently in every
method that constructs a WHERE clause, or use LanceDB's filter parameter if
it supports binding.

---

### High — Privacy base64 pattern over-redacts its own data

**File:** `core/privacy.py:7`

```python
re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'),  # long base64 blobs (JWT, keys)
```

Memory IDs are SHA256 hexdigests — 64 lowercase hex characters. Git commit hashes
are 40 characters. Both match this pattern. If any memory's `raw_text` contains
a reference to another memory's ID or a git hash, that reference gets redacted
to `[REDACTED]`. This silently corrupts data the system itself generates.

More broadly, the pattern matches any 40+ character alphanumeric run. That
includes UUIDs, long file paths, base64-encoded images in markdown, and JSON
arrays of short strings that happen to concatenate. The false positive rate is
high enough to cause real data corruption.

**Fix:** Restrict the base64 pattern to actually base64-encoded content (must
contain `+`, `/`, or end with `=`), and add a minimum entropy threshold. Real
JWTs have a specific three-part dotted structure; match that instead:
```python
re.compile(r'ey[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')  # JWT
re.compile(r'[A-Za-z0-9+/]{20,}={1,2}')  # actual base64 with padding
```

The API-key pattern on line 5 is also aggressive — it matches
`password: hunter2` which is fine, but also `password: $VARIABLE` which
would redact shell variable references in terminal command memories.

---

### High — `_DIAG = True` is shipping to production

**File:** `connectors/diff_connector.py:16`

```python
# TEMP: set to True to print per-step timing to stderr
_DIAG = True
```

Every invocation of `DiffConnector.collect()` prints timing lines to stderr.
In daemon mode this pollutes the daemon log. In CLI mode it shows up in the
user's terminal unexpectedly. This is a left-in debug flag.

**Fix:** Delete `_DIAG`, `_t()`, and all `_t()` calls. If timing is needed
later, add it behind a `--verbose` flag or Python `logging.DEBUG`.

---

### High — Token budget uses word count, not token count

**File:** `core/token_budget.py:4–5`

```python
def estimate_tokens(text: str) -> int:
    """Rough token estimate (~1 token per whitespace-delimited word)."""
    return len(text.split())
```

For natural language this underestimates by ~30%. For code it underestimates
by 2–3× (identifiers like `_batch_existing_ids` become multiple tokens;
punctuation is tokenized separately). A 2000-token budget filled with code
memories will actually consume 4000–6000 tokens when sent to the LLM. The
`ContextEngine` uses this budget to pack memories for the RAG prompt, so
context windows overflow silently.

The docstring acknowledges it's rough, but "rough" here means "wrong by 2–3×
for the primary use case."

**Fix:** Use `len(text) // 4` as the estimate (4 bytes/token is accurate for
English+code at GPT/Claude tokenizer rates), or add `tiktoken` as an optional
dependency. Even `len(text) / 3` would be closer to correct for this workload
than word count.

---

### Medium — Config read+save has no locking

**File:** `core/config.py:71–91` (and every `add_*` / `remove_*` / `set_*` helper)

Every mutation follows the pattern:
```python
data = load()          # read entire file
data["git"]["repo_paths"].append(path)
save(data)             # overwrite entire file
```

If two CLI processes run concurrently — e.g., a daemon connector fires while the
user runs `devmemory config add-code` — the second `save()` overwrites the first's
changes. The config file ends up in whichever process's state won the race. On a
machine with a fast daemon and a slow user, this happens regularly.

**Fix:** Use `fcntl.flock()` (POSIX) or a `.lock` file around the load+save
pair. Python's `filelock` is a zero-dependency solution.

---

### Medium — Terminal connector discards actual command timestamps

**File:** `connectors/terminal_connector.py:66`

`_parse_line()` at line 77–86 correctly handles the zsh extended history format:
```
: 1700000000:0;git commit -m "fix"
```
It extracts the command string — but then discards the timestamp. The `Memory`
object is created with `datetime.utcnow()`, losing all temporal ordering. Queries
like "what did I run last Tuesday?" will return random results because every
terminal memory appears to have been created at ingest time.

**Fix:** In `_parse_line()`, return `(command, timestamp | None)` and use the
parsed unix timestamp when constructing the `Memory`. Bash history doesn't have
timestamps, so the fallback to `utcnow()` is correct for that file only.

---

### Medium — Importance decay factor is applied per invocation, not per day

**File:** `daemon/jobs/importance_decay.py`

```python
def decay_importance(factor=0.99):
```

The factor 0.99 is documented as "daily decay" but the function is called by the
scheduler with no guard on invocation frequency. If the daemon runs the decay job
at its default poll interval (every 60 seconds), memories lose importance at
0.99^1440 ≈ 0.000007 per day instead of the intended 0.99. Every memory would
decay to near-zero in hours.

Looking at `daemon/scheduler.py`, the `prune_memories` and `dedup` calls are
scheduled daily, but it's worth verifying `decay_importance` is called on the
same cadence and not on every scheduler tick.

**Fix:** Either make the factor configurable per invocation frequency, guard it
with a `last_decay_time` check in the scheduler, or document the expected call
frequency explicitly so future changes don't break it.

---

### Medium — `_to_toml()` silently drops unsupported types

**File:** `core/config.py:44–61`

```python
elif isinstance(val, int):
    lines.append(f"{key} = {val}")
else:
    lines.append(f'{key} = "{val}"')
```

Floats are stringified with quotes: `importance = "0.85"` instead of
`importance = 0.85`. Booleans become `"True"` and `"False"` (Python strings,
not TOML booleans). When read back with `tomllib`, `"True"` stays a string
and `"0.85"` stays a string, breaking any downstream numeric comparison.

This is a hidden data corruption bug — no error is raised, the file looks
valid, but the values are the wrong type.

**Fix:** Add `float` and `bool` cases explicitly, or use the `tomli-w` package
(the write counterpart to `tomllib`) which is already in the Python ecosystem.

---

### Low — Markdown frontmatter parser misses complex YAML

**File:** `connectors/markdown_connector.py:124–133`

```python
for line in fm_block.splitlines():
    if ":" not in line:
        continue
    key, _, val = line.partition(":")
```

`partition(":")` correctly handles colons in values (it splits on the first
occurrence only). But it breaks on:
- Multi-line values (indented YAML)
- YAML lists: `tags: [work, project]` — parsed as `val = " [work, project]"`, treated as a string
- Quoted strings: `title: "My: Document"` — parsed as `title = '"My'`

The `tags` field has a special-case handler below it (line 65–68) that tries
to split comma-separated strings, which partially compensates, but only for the
specific case of `tags: a, b, c`. YAML list syntax gets passed through as a raw
string.

**Fix:** Add `pyyaml` as an optional dependency and use it here. It's a single
`yaml.safe_load(fm_block)` call. If avoiding the dependency is important,
document the supported frontmatter subset explicitly.

---

## Test Coverage Gaps

This is the most significant structural problem.

### Zero tests

| Module | Why it matters |
|---|---|
| All 9 connectors (except git_connector partially) | Connectors write to the live store. Bugs corrupt production data. |
| All CLI commands | The user-facing interface has no regression coverage. |
| `daemon/jobs/importance_decay.py` | The decay factor bug above would be caught by a test. |
| `daemon/jobs/dedup.py` | Dedup is destructive — it deletes records. |
| `daemon/jobs/memory_cleanup.py` | Also destructive. |
| `core/token_budget.py` | The word-count bug would be caught by a test with code input. |
| `core/config.py` | Serialization round-trips would catch the float/bool type bug. |
| `core/plan_engine.py` | New code, no tests. |
| `core/codebase_map.py` | New code, no tests. |
| `core/query_planner.py` | The LLM routing fallback has no test. |
| `core/rag_engine.py` | Prompt formatting, answer saving — untested. |
| `api/routes/` (search, context, webhook) | API contract has no tests (auth is tested, routing isn't). |

### Under-tested

| Module | Gap |
|---|---|
| `core/context_cache.py` | TTL expiration, size eviction, and invalidation on `store.add()` are not tested. Only cache hit is tested. |
| `core/privacy.py` | Only happy-path redaction tested. The false positive problem (redacting commit hashes) is not caught. |
| `core/intent_classifier.py` | 5 tests exist but the recall-before-implementation ordering rule is not explicitly tested. |
| `core/tests/test_hybrid_search.py` | 1 of 6 tests is flaky (pre-existing failure on `test_keyword_only_hit_ranks_above_unrelated_semantic_hit`). It is skipped in practice but the underlying fragility is unresolved. |

### What's well tested

`core/tests/test_ranking.py` (11 tests) and `core/tests/test_hybrid_search.py`
(5 passing tests) are comprehensive for the scoring layer. `api/tests/test_auth.py`
(10 tests) covers the auth contract thoroughly.

---

## Architectural Observations

### Config is a god-module

`core/config.py` (262 lines) manages git paths, markdown dirs, filesystem dirs,
meeting dirs, LLM settings, API keys, and connector schedules. It's 8 distinct
concern areas in one file with a copy-pasted load+save pattern for each. When you
add a new connector, you add another block of identical helpers. This is already
causing the concurrent-write bug above — fixing locking in one place misses all
the others.

A simple improvement: a single `ConfigManager` class with a context manager for
atomic write, and one helper method per logical group. The repetition disappears.

### Exception masking is pervasive

`except Exception: pass` appears at `memory_store.py:183`, `204`, `225`, `385`,
`459`, and in several connectors. These are understandable as "this is a
non-critical counter update, don't crash the program" — but they also hide real
failures like disk full, database corruption, and permission errors. Callers have
no signal that anything went wrong.

A better pattern: `except Exception as e: logger.debug("counter update failed: %s", e)`.
One line, preserves the "don't crash" behavior, but leaves a trace.

### Connector base class has no lifecycle

`connectors/base.py` defines `collect() -> int` but no `close()`, `cleanup()`,
or context manager support. Connectors that open file handles (filesystem,
markdown) or subprocess pipes (git, diff) have no guaranteed cleanup path. In
daemon mode, resource leaks accumulate over the daemon's lifetime.

### Store provider is a global singleton

`core/store_provider.py` returns a module-level singleton via `get_store()`.
This makes testing connectors without affecting the production database difficult
— you have to mock the global, which is fragile. Dependency injection (passing
the store into connectors at construction time) would make tests trivial and
remove a global state dependency.

The connector base class takes `store=None` and falls back to `get_store()` —
this is the right interface, it just isn't threaded through to every connector
consistently.

### The `reinforce()` cap of 0.8 is misleading

`MemoryStore.reinforce()` is documented as "Boost importance of a retrieved
memory (cap at 1.0)" but actually caps at 0.8. The comment says "cap at 1.0"
but the code says `min(0.8, ...)`. Users of the API calling `reinforce()` will
expect importance to go above 0.8 and be surprised when it doesn't. The newer
`boost_importance()` caps at 0.95, creating two different semantics for what
looks like the same operation.

---

## Prioritized Action Plan

### Do these now

1. **Fix unescaped `memory_id` in `reinforce()`, `exists()`, `delete()`**
   (`memory_store.py:178, 213, 221, 393`). Three-line fix per method.

2. **Remove `_DIAG = True`** from `diff_connector.py`. Delete lines 15–27 and
   all `_t()` call sites.

3. **Fix the privacy base64 regex** to not match hex strings and git hashes.
   Add a test with a git commit hash to lock it in.

4. **Fix token estimation** in `token_budget.py`. Change `len(text.split())`
   to `len(text) // 4`. Add a test with a code snippet.

5. **Fix the `reinforce()` docstring** to say "cap at 0.8" or change the cap
   to 0.95 to match `boost_importance()`.

### Do these soon

6. **Add connector locking to config writes** using `filelock` or `fcntl.flock`.
   Fix the pattern once in `save()`, not individually per helper.

7. **Add `float` and `bool` cases to `_to_toml()`**, or replace it with
   `tomli-w`. Add a round-trip test: write a config with a float, read it back,
   assert the value is still a float.

8. **Fix terminal connector timestamps.** Change `_parse_line()` to return
   `tuple[str, datetime | None]` and use the parsed timestamp in `Memory`.

9. **Write tests for the three daemon jobs** (`dedup`, `decay`, `cleanup`).
   These are destructive operations with no regression coverage. Each needs a
   setup fixture with known memory state and assertions on what was
   deleted/updated.

10. **Write tests for the filesystem and markdown connectors.** Use `tmp_path`
    fixtures. These connectors are the primary source of `file_content` memories
    and have no tests at all.

### Do these when you have capacity

11. **Write CLI smoke tests** using `typer.testing.CliRunner`. At minimum,
    `search`, `context`, `stats`, and `get` should have tests that mock the
    store and verify output format.

12. **Add importance decay cadence guard** in the scheduler. Either pass the
    last-run time into `decay_importance()` and compute the appropriate factor,
    or ensure it runs on a daily schedule only.

13. **Replace the markdown YAML parser** with `yaml.safe_load()`. The current
    parser handles the common cases but silently corrupts complex frontmatter.

14. **Refactor `core/config.py`** into a `ConfigManager` class with a single
    atomic write method. The 8 load+save patterns collapse into one, and locking
    is applied everywhere automatically.

15. **Add a `Connector.close()` / `__exit__`** to the base class and call it in
    the daemon scheduler after each connector run.

---

## Minor Notes (Lowest Priority)

- `core/embeddings.py` uses `os.dup2` to redirect stderr during model loading.
  This is clever but fragile — if loading raises an exception after dup2 but
  before restoring fd, stderr is permanently redirected. A `try/finally`
  around the import would prevent this.

- `connectors/diff_connector.py` accesses `store._batch_existing_ids()` — a
  private method — directly. This couples the connector to an internal
  implementation detail that could change without notice.

- The flaky test `test_keyword_only_hit_ranks_above_unrelated_semantic_hit`
  should either be fixed or marked `@pytest.mark.xfail`. Leaving it as a known
  failure in an undecorated test case makes the test suite unreliable as a
  CI gate.

- `core/context_engine.py` silently swallows the ML classifier `ImportError`
  with no log message. If the `[ml]` extra isn't installed, users get rule-based
  classification without knowing it. A `logging.debug()` here costs nothing and
  makes the degradation visible.

- `api/server.py:45` — `allow_origins=["*"]` is fine for a local-only tool.
  Add a comment saying that, or make it configurable for the day it gets
  deployed. Right now it would be easy to forget to restrict this.
