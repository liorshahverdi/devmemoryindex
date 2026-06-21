# DevMemoryIndex Improvement Report

## Highest-impact improvements

### 1. Split the config module
`core/config.py` is doing too much:
- git paths
- markdown dirs
- filesystem dirs
- meeting dirs
- API keys
- LLM settings
- schedules
- connector flags

That makes it a “god module” and increases maintenance cost.

**Improve it by:**
- introducing a `ConfigManager` or `ConfigStore`
- separating concerns into sections/classes
- centralizing load/save/locking once
- validating config shape instead of passing raw dicts everywhere

This would also reduce duplication in all the `add_*`, `remove_*`, `get_*` helpers.

---

### 2. Stop swallowing exceptions broadly
There are many `except Exception:` blocks across:
- `core/memory_store.py`
- `connectors/*`
- `daemon/*`
- `cli/*`

Some of those are probably intentional, but many hide real bugs and make failures hard to diagnose.

**Better pattern:**
- catch specific exceptions when possible
- log unexpected failures
- only suppress errors when there’s a strong reason

For example:
- `except Exception: pass`
becomes
- `except Exception as e: logger.debug("... failed: %s", e)`

This is one of the biggest maintainability wins.

---

### 3. Reduce reliance on global state
`core/store_provider.py` uses a module-level singleton, and `conftest.py` patches it for tests.

That works, but it makes:
- testing harder
- dependency flow less explicit
- runtime behavior harder to reason about

**Improve by:**
- passing the store explicitly into connectors/services
- using dependency injection where possible
- keeping `get_store()` as a fallback, not the default

This will make tests cleaner and code less coupled.

---

### 4. Add more lifecycle management for connectors
Connectors seem to expose `collect()`-style behavior, but there’s little visible lifecycle handling.

**Potential issues:**
- open file handles
- subprocesses
- long-lived watchers
- cleanup in daemon mode

**Improve by:**
- adding `close()` / `cleanup()` hooks
- making connectors context-manageable
- ensuring daemon jobs always release resources

---

### 5. Strengthen config serialization
`core/config.py` has a custom TOML writer `_to_toml()`.

That’s fragile over time, especially if config types expand.

**Better options:**
- use `tomli-w` or `tomlkit`
- add round-trip tests for config read/write
- enforce a config schema

This reduces subtle bugs and keeps config more future-proof.

---

## Testing improvements

### 6. Add tests for the most fragile runtime paths
The repo has tests, but coverage should focus more on the risky parts:

- daemon jobs
- connector ingestion
- config write/read behavior
- CLI command smoke tests
- API route behavior
- error handling paths

Especially important:
- config mutation
- filesystem/markdown connectors
- daemon scheduling and cleanup jobs
- memory pruning / consolidation operations

---

### 7. Add CLI smoke tests
The CLI is one of the main entrypoints, so it should have end-to-end-style tests.

Good candidates:
- `search`
- `add`
- `stats`
- `context`
- `get`
- `config`
- `serve`

Use `typer.testing.CliRunner` with mocked store/backend output.

---

### 8. Add API contract tests
`api/server.py` and the route modules should have tests for:
- auth enabled/disabled
- search response shape
- context generation
- memory create/update/delete
- invalid input handling

That will catch regressions when routes or auth logic change.

---

## Architecture / code organization improvements

### 9. Consolidate repeated CLI command patterns
A lot of CLI commands follow the same structure:
- parse args
- call service/store
- format output with Rich
- handle errors

You could extract shared helpers for:
- error formatting
- table rendering
- clipboard copying
- “save as memory” patterns
- optional dependency messaging

That would reduce boilerplate and inconsistencies.

---

### 10. Make optional dependencies more explicit
You already use `try/except ImportError` in `cli/main.py` for optional commands like `ask`, `plan`, `map`, `train-intent`.

That’s okay, but it can be improved by:
- registering commands via a feature registry
- showing unavailable commands in help with a reason
- making optional feature availability explicit in one place

This would make the CLI easier to extend.

---

### 11. Improve module boundaries
The repo has a solid top-level split:
- `core/`
- `cli/`
- `api/`
- `connectors/`
- `daemon/`

But some of the logic likely overlaps:
- memory storage
- ranking/search
- context generation
- LLM/RAG/planning
- CLI orchestration

A clean next step would be to introduce a small service layer:
- `MemoryService`
- `SearchService`
- `ConfigService`
- `IngestService`
- `ContextService`

That would keep CLI/API thin and move logic into reusable code.

---

## Reliability and observability improvements

### 12. Add structured logging
A lot of output is user-facing CLI text, but the daemon and connectors would benefit from consistent logs.

Add:
- module-level loggers
- log levels
- structured context for errors
- separate user output vs diagnostic logs

This makes daemon failures much easier to debug.

---

### 13. Add runtime health checks
There is already a `health` command, which is good.

You could expand it with:
- store integrity checks
- config validity
- connector status
- daemon liveness
- recent ingestion success/failure counts

That would help users troubleshoot broken setups faster.

---

## Documentation improvements

### 14. Trim or split large docs
`ROADMAP.md` is huge, and while that’s useful for planning, it can become hard to navigate.

Consider splitting into:
- `docs/architecture.md`
- `docs/cli.md`
- `docs/config.md`
- `docs/testing.md`
- `docs/roadmap.md`

That makes it easier for contributors to find the right entry point.

---

### 15. Add a contributor guide
A short `CONTRIBUTING.md` would help a lot:
- how to run tests
- how config works
- how connectors should be written
- how to add a CLI command
- how to add a route
- coding style expectations

That would reduce onboarding friction.

---

## If I had to prioritize 5 changes

1. **Refactor `core/config.py`**
2. **Replace broad `except Exception` usage with logging/specific exceptions**
3. **Add CLI smoke tests**
4. **Add connector/daemon tests**
5. **Reduce global state via dependency injection**

---

If you want, I can also turn this into a shorter actionable checklist, or break it into a prioritized engineering plan.
