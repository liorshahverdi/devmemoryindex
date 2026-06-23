# Agent Integration Improvements Roadmap

This document captures follow-up improvements discovered while installing DevMemoryIndex for multiple local repositories, running it as a Linux daemon, and registering it as a Hermes Agent MCP server.

The goal is to make DevMemoryIndex more reliable and ergonomic for long-running AI coding agents, especially Hermes Agent and OpenAI/Pi-style coding workflows that need a shared project memory layer. Claude Code remains a useful optional connector target, but this roadmap should not assume Claude Code is the primary user workflow.

## Goals

- Make DevMemoryIndex easy to install and run unattended on Linux/macOS.
- Make MCP integration predictable for both interactive and automated agent setups.
- Reduce startup-time fragility by lazy-loading heavy dependencies.
- Improve connector observability, performance, and failure recovery.
- Shape MCP tool descriptions and workflows around how autonomous coding agents actually use memory.
- Avoid memory pollution while still capturing durable, high-signal lessons.

## Initial PR focus

Prioritize the improvements that unblock reliable day-to-day use from Hermes and similar MCP clients:

1. **Lazy-load embeddings and heavy dependencies** so MCP startup, CLI help, and lightweight metadata operations do not pay the embedding-model import cost.
2. **Native Linux daemon install/status/uninstall** so Linux users can run always-on indexing with `systemd --user` without hand-written service files. ✅ Implemented in this branch.
3. **Packaging cleanup for the MCP dependency** so `devmemory-mcp-server` works from a normal install and clearly declares the optional/runtime packages it needs. ✅ Implemented in this branch.
4. **Agent-optimized MCP tool descriptions** so Hermes and other coding agents choose the right memory tools and avoid low-value writes or duplicate native-memory behavior.

The remaining sections are still valuable follow-ups, but these four are the tightest first implementation scope for this PR series.

## 1. Native Linux daemon install/status/uninstall

### Implemented behavior

`devmemory daemon install`, `devmemory daemon status`, and
`devmemory daemon uninstall` now dispatch to the native service manager for the
current platform:

- Linux uses a `systemd --user` service at `~/.config/systemd/user/devmemory.service`.
- macOS keeps the existing launchd LaunchAgent behavior.
- `devmemory daemon install --dry-run` prints the generated unit without writing
  files or running `systemctl`, which makes service generation easy to inspect
  and test in CI.

The Linux service uses the resolved `devmemory` executable, starts
`devmemory daemon start`, restarts on failure, and appends stdout/stderr to the
normal DevMemoryIndex daemon logs.

### Verification

- `daemon/tests/test_systemd.py` covers service unit rendering, install,
  dry-run, uninstall, status, and `systemctl --user` failure handling without
  requiring a real systemd daemon.
- `cli/commands/daemon_cmd.py` dispatches install/status/uninstall by platform
  and keeps macOS launchd behavior unchanged.

### Acceptance criteria

- Linux users can run one command to install the daemon.
- `status` reports the right backend on Linux and macOS.
- Existing macOS launchd behavior remains unchanged.

## 2. Better non-interactive MCP registration

### Implemented behavior

DevMemoryIndex now includes a scriptable MCP registration helper for Hermes:

```bash
devmemory mcp install-hermes --yes
hermes mcp test devmemory
```

The command writes a stable wrapper script and upserts a `mcp_servers.devmemory`
entry in the Hermes config without prompting. `--dry-run` prints the plan without
writing files, which keeps agent/bootstrap setup inspectable and safe.

Client examples live in `docs/mcp-clients.md` and cover:

- Hermes Agent non-interactive setup
- wrapper-script rationale
- manual Hermes config blocks
- Claude Code / generic MCP stdio JSON config

### Verification

- `cli/tests/test_mcp_registration_cli.py` covers config rendering, idempotent
  replacement of an existing `devmemory` server block, dry-run behavior, and
  real wrapper/config writes in a temp directory.
- `README.md` links to the non-interactive helper and client config docs.

### Acceptance criteria

- A fresh machine can register DevMemoryIndex MCP from copy-paste docs without opening an editor.
- Automated agents can perform the setup without hanging on prompts.
- `hermes mcp test devmemory` discovers all registered tools.

## 3. Packaging cleanup for MCP dependency

### Problem

Current MCP SDK releases do not expose a `server` extra, so DevMemoryIndex should depend on the base MCP SDK package directly and avoid confusing stale-extra install warnings.

Hermes and other MCP clients also need a stable command they can run after a normal package install, rather than requiring every user to hand-write a wrapper around `python -m mcp_server.server`.

### Implemented behavior

The branch now declares the MCP extra and console script as:

```toml
[project.scripts]
devmemory-mcp-server = "mcp_server.server:main"

[project.optional-dependencies]
mcp = [
    "mcp>=1.0",
    "lancedb",
    "sentence-transformers",
]
```

`mcp_server.server` exposes `main()`, so normal installs provide a `devmemory-mcp-server` stdio command for Hermes Agent, Claude Code, and generic MCP clients. The MCP extra also includes the runtime imports the server currently needs during startup.

### Verification

- `tests/test_packaging.py` asserts the MCP optional dependency uses `mcp>=1.0` without the stale `mcp[server]` extra.
- `tests/test_packaging.py` asserts the MCP extra includes current startup/runtime imports (`lancedb` and `sentence-transformers`).
- `tests/test_packaging.py` asserts the `devmemory-mcp-server` console script points at `mcp_server.server:main`.
- Editable install verification with `pip install -e '.[mcp]'` completed without stale-extra warnings.
- Wheel metadata verification asserts the MCP extra and console script are present in the built artifact.

### Acceptance criteria

- Installing `devmemoryindex[mcp]` produces no stale-extra warning.
- Normal installs expose a `devmemory-mcp-server` command.
- MCP server import succeeds in CI.
- README install instructions match `pyproject.toml`.

## 4. Lazy-load embeddings and heavy dependencies

### Problem

Some CLI commands import embedding/model code at startup even when the command does not need vector search. During setup, the CLI tried to load `BAAI/bge-small-en` while running a help-like command, and failed until the model was downloaded and cached.

This makes the CLI fragile in offline, fresh, or partially configured environments.

### Desired behavior

Commands that do not need embeddings should not import or initialize sentence-transformer models.

Examples that should not require model loading:

- `devmemory --help`
- `devmemory config list`
- `devmemory daemon status`
- `devmemory hook status`
- `devmemory api-key show`

Commands that do require embeddings can load lazily:

- `search`
- `context`
- `ingest` for sources that create embeddings
- MCP tools that search/build context

### Proposed implementation

- Move `SentenceTransformer("BAAI/bge-small-en")` initialization behind a function such as:

```python
_model = None

def get_embedding_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(configured_model_name())
    return _model
```

- Avoid importing `core.embeddings` from CLI modules that do not need it.
- Consider moving command imports inside command handlers if Typer startup imports too much.
- Add friendly error messages when the model cannot be downloaded:
  - explain how to pre-download
  - explain offline mode
  - show which command actually needed embeddings

### Tests

- Run `devmemory --help` with Hugging Face network disabled and no cached model.
- Run `devmemory config list` without cached embeddings.
- Run a search command and assert it loads embeddings only then.

### Acceptance criteria

- Non-search commands work without a cached embedding model.
- Search/context/ingest commands still work once the model is available.
- Error messages are actionable for offline environments.

## 5. Filesystem connector performance and resilience

### Implemented behavior

Filesystem ingestion is now observable, resumable, and tunable.

- `devmemory ingest --source filesystem --repo <name>` limits scans to a matching configured root/repo.
- `devmemory ingest --source filesystem --max-files <N>` bounds large scan runs.
- Per-file fingerprints are persisted to `~/.config/devmemory/filesystem_state.json` after each successfully inspected file, so repeated or interrupted scans skip unchanged files before embedding.
- `FilesystemConnector.last_stats` tracks inspected files, chunks added, errors, scanned roots, and skipped reasons.
- CLI output includes filesystem progress and a final summary with skipped reasons such as `unchanged`, `unsupported_extension`, `too_short`, `ignored_directory`, `large_file`, and `max_files`.

Example:

```bash
devmemory ingest --source filesystem --repo my-app --max-files 500
```

### Verification

- `connectors/tests/test_filesystem_connector_resilience.py` covers unchanged-file fast skips, max-file limits, progress events, repo filtering, and per-file fingerprint persistence after partial/interrupted scans.
- Existing filesystem connector tests continue to verify chunking, deduplication, skip directories, stale chunk eviction, and importance scoring.
- `cli/tests/test_ingest_cli.py` covers the filesystem-specific CLI options and summary output.

### Acceptance criteria

- Large initial scans provide visible progress.
- Repeated scans become fast.
- Timeout/interruption does not corrupt the store.
- Agents can distinguish no-op ingestion from slow ingestion.

## 6. Agent-optimized MCP tool descriptions

### Problem

The MCP tools are already useful, but autonomous agents need more precise operational guidance than humans. Tool descriptions should tell the agent when to call a tool, when not to call it, and what to do with returned IDs/results.

### Desired behavior

MCP tool docstrings should encode agent-use policy directly in the tool descriptions.

### Examples

`get_session_context` should say:

- Call once near the start of a complex coding/debugging session.
- Include the current task and repo if known.
- Do not call repeatedly unless the task changes substantially.

`search_memories` should say:

- Use before debugging, refactoring, or touching unfamiliar code.
- Prefer specific technical terms.
- Use returned IDs with `get_memory` when a result looks actionable.

`remember_memory` should say:

- Use only after a solution is verified.
- Store durable patterns, root causes, commands, or decisions.
- Do not store transient task progress, PR numbers, or short-lived TODOs.

`remember_failure` should say:

- Use after a dead end consumed meaningful time.
- Include the failed hypothesis, exact command/approach, and why it failed.

### Proposed implementation

- Review every MCP tool docstring for:
  - trigger conditions
  - anti-triggers
  - input quality guidance
  - expected follow-up action
  - memory hygiene rules

- Add a short `mcp_server/AGENT_GUIDE.md` with recommended use flows.
- Consider adding tool metadata examples if supported by MCP clients.

### Tests

- Snapshot-test MCP tool descriptions so regressions are visible.
- Run `hermes mcp test devmemory` or equivalent and verify the descriptions remain concise enough for tool schemas.

### Acceptance criteria

- Agents receive clear guidance without needing separate docs.
- Tool descriptions reduce over-searching and memory pollution.
- Returned memory IDs are explicitly actionable.

## 7. Hermes-specific agent start workflow

### Problem

Hermes can use DevMemoryIndex through MCP, but the best workflow should be documented so the agent consistently uses memory without overusing it.

### Desired behavior

Document a Hermes-specific workflow that balances recall, grounding, and memory hygiene.

### Recommended workflow

At the start of complex repo work:

1. Call `get_session_context` with the task and repository.
2. If the context is insufficient, call `search_memories` with specific technical terms.
3. Use `get_memory` for any high-signal IDs that need full details.
4. Use `build_context` before broad implementation planning.
5. Use `plan_task` only when a grounded plan is helpful, not for tiny edits.
6. After verified success, call `remember_memory` for durable lessons.
7. After meaningful dead ends, call `remember_failure`.
8. If a prior memory helped, call `reinforce_memory`.
9. If a memory is wrong or stale, call `update_memory` or `forget_memory`.

### What not to store

Avoid storing:

- PR numbers
- branch names that will be stale soon
- temporary TODO state
- one-off task progress
- copied logs without explanation
- secrets, tokens, credentials
- huge raw outputs that are better referenced by file path

Prefer storing:

- root causes
- durable environment quirks
- verified commands
- project conventions
- reusable debugging workflows
- architecture decisions
- integration gotchas

### Proposed implementation

- Add a Hermes-focused section to the README or a dedicated `docs/hermes-agent-workflow.md`.
- Provide prompts/examples:

```text
Before modifying this repo, use DevMemoryIndex to retrieve relevant context for: <task>
```

- Add examples of good and bad `remember_memory` payloads.
- Consider a Hermes skill for DevMemoryIndex workflows if the pattern proves stable.

### Acceptance criteria

- Hermes can use DevMemoryIndex consistently across sessions.
- The workflow improves recall without adding noisy memories.
- The docs explain when to search, when to write, and when to update/forget.

## Suggested priority order

### Initial PR series

1. Lazy-load embeddings and heavy dependencies. ✅ Implemented
2. Native Linux daemon install/status/uninstall. ✅ Implemented
3. Packaging cleanup for MCP dependency. ✅ Implemented
4. Agent-optimized MCP tool descriptions. ✅ Implemented
5. Hermes-specific agent start workflow. ✅ Implemented

### Follow-up work

6. Better non-interactive MCP registration. ✅ Implemented
7. Filesystem connector performance and resilience. ✅ Implemented

This order prioritizes startup reliability, installability, MCP packaging correctness, and agent tool-choice quality first. Those are the highest-leverage improvements for a Hermes + OpenAI/Pi coding-agent workflow because they make DevMemoryIndex dependable as an always-on shared project-memory service before expanding connector scope.

## Notes from verified local setup

The following setup was verified on a Linux Hermes host:

- DevMemoryIndex installed in a Python 3.12 virtualenv.
- `BAAI/bge-small-en` downloaded and loaded with 384-dimensional embeddings.
- Five local git repositories configured for git, markdown, and code scanning.
- Git post-commit hooks installed in each repository.
- User-level systemd daemon running and watching configured repositories.
- Hermes MCP server `devmemory` registered through a wrapper script.
- `hermes mcp test devmemory` discovered 19 tools successfully.

These observations should be used as regression scenarios when implementing the improvements above.
