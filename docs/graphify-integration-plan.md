# Graphify Integration Plan for DevMemoryIndex

## Purpose

DevMemoryIndex and Graphify solve adjacent problems:

- **Graphify** maps a repository or corpus into a structural/semantic knowledge graph.
- **DevMemoryIndex** stores persistent developer workflow memory across commits, terminal history, notes, AI sessions, meetings, voice, and agent feedback.

The integration should let DevMemoryIndex use Graphify as the **codebase graph provider**, while DevMemoryIndex remains the **long-term memory, retrieval, and agent-continuity layer**.

## Goals

1. Ingest Graphify outputs into DevMemoryIndex as searchable memories.
2. Preserve Graphify graph structure as typed DevMemoryIndex edges where useful.
3. Expose Graphify-derived context through existing CLI, API, and MCP tools.
4. Avoid duplicating Graphify’s AST/callgraph implementation inside DevMemoryIndex.
5. Keep Graphify optional: DevMemoryIndex must work without it installed.

## Non-goals

- Reimplement Graphify extraction.
- Replace DevMemoryIndex filesystem/markdown connectors immediately.
- Require Graphify for normal memory search.
- Store full `graph.html` or large visualization artifacts in LanceDB.
- Make DevMemoryIndex dependent on Graphify internals rather than stable output files.

---

## Integration Model

Graphify writes:

```text
graphify-out/
├── graph.json
├── GRAPH_REPORT.md
└── graph.html
```

DevMemoryIndex should ingest:

| Graphify artifact | DevMemoryIndex use |
|---|---|
| `GRAPH_REPORT.md` | High-level architecture memory chunks |
| `graph.json` nodes | Searchable code/entity/document memories |
| `graph.json` edges | Optional typed relationships in `EdgeStore` |
| `graph.html` | Not ingested; referenced by path only |

---

## Proposed Memory Types

Add the following memory types by convention; no schema change required because `Memory.type` is already a string.

| Type | Description |
|---|---|
| `graphify_report` | Chunks from `GRAPH_REPORT.md` |
| `graphify_node` | One memory per important graph node |
| `graphify_community` | Optional summary memory per Graphify community |
| `graphify_relation` | Optional text memory for important relationships |

Recommended tags:

```text
graphify
code_graph
architecture
community:<id>
node_type:<type>
source_file:<path>
```

---

## Edge Mapping

Graphify edges should be mapped into DevMemoryIndex `EdgeStore` only when they are useful for memory traversal.

| Graphify relation | DevMemoryIndex edge type |
|---|---|
| `calls` | `references` |
| `imports` / `imports_from` | `references` |
| `contains` | `references` |
| `implements` / `inherits` | `references` |
| `semantically_similar_to` | `related_to` |
| `supersedes` | `supersedes` |
| ambiguous/unknown | `related_to` |

Because `EdgeStore` currently links memory IDs, Graphify node IDs should be deterministically mapped to DevMemoryIndex memory IDs.

Suggested ID format:

```text
sha256("graphify-node:" + repo + ":" + graphify_node_id)
```

---

## CLI Design

Add a Graphify subcommand group:

```bash
devmemory graphify ingest [PATH]
devmemory graphify status [PATH]
devmemory graphify build [PATH]
devmemory graphify query "question" [--repo REPO]
```

### `devmemory graphify ingest [PATH]`

Reads an existing `graphify-out/` directory and stores graph memories.

Options:

```bash
--repo REPO              Override repo name
--graph PATH             Path to graph.json
--report PATH            Path to GRAPH_REPORT.md
--with-edges             Store graph edges in EdgeStore
--no-report              Skip report ingestion
--no-nodes               Skip node ingestion
--min-degree N           Only ingest nodes with degree >= N
--dry-run                Show counts without writing
```

### `devmemory graphify build [PATH]`

Runs Graphify if installed, then ingests output.

```bash
graphify .
devmemory graphify ingest .
```

Should gracefully fail with install guidance if `graphify` is unavailable.

### `devmemory graphify status [PATH]`

Reports whether Graphify output exists and when it was last modified.

### `devmemory graphify query "question"`

Optional helper that prioritizes `graphify_*` memories and returns architecture/codegraph context.

---

## Connector Design

Add `connectors/graphify_connector.py`.

Responsibilities:

1. Locate `graphify-out/graph.json` and `graphify-out/GRAPH_REPORT.md` under configured repos.
2. Parse Graphify node-link JSON.
3. Convert selected nodes/report sections into `Memory` objects.
4. Optionally create `EdgeStore` links between node memories.
5. Avoid duplicates using deterministic IDs.
6. Update changed nodes when graph content changes.

Configuration:

```toml
[graphify]
enabled = true
scan_dirs = ["/Users/me/projects/app"]
ingest_edges = true
min_degree = 1
```

Initial implementation can reuse existing git/filesystem repo paths instead of adding a new config section.

---

## MCP Tool Additions

Add these tools after CLI ingestion is stable:

### `ingest_graphify(repo_path: str, with_edges: bool = true)`

Allows an agent to import a freshly generated Graphify graph.

### `search_code_graph(query: str, repo: str | None = None, k: int = 5)`

Thin wrapper over `search_memories(memory_type="graphify_node")` plus `graphify_report` fallback.

### `get_code_entity_context(node_or_query: str, depth: int = 1)`

Finds a Graphify node memory and expands through `EdgeStore` neighbors.

---

## Data Extraction Details

### Report ingestion

Split `GRAPH_REPORT.md` by headings and store each section as `graphify_report`.

Summary format:

```text
Graphify report: <heading>
```

Raw text should contain the full section.

Importance:

- `0.85` for god nodes / architecture overview / surprising connections
- `0.70` for regular sections

### Node ingestion

For each graph node, store:

```text
summary = "Graphify node: <label> (<type>)"
raw_text = "Label: ...\nType: ...\nSource file: ...\nCommunity: ...\nDegree: ...\nNeighbors: ..."
```

Importance heuristic:

```text
0.90  god/high-degree nodes
0.75  nodes with source files and multiple edges
0.60  regular nodes
0.40  isolated/low-signal nodes
```

### Community ingestion

If community labels are available, create one memory per community:

```text
summary = "Graphify community: <community_name>"
raw_text = list of top nodes, source files, and relationships
```

---

## Implementation Phases

## Phase 1 — Read-only Graphify Import ✅ Implemented

Deliverables:

- `connectors/graphify_connector.py` ✅
- `devmemory graphify ingest` ✅
- Report ingestion from `GRAPH_REPORT.md` ✅
- Node ingestion from `graph.json` ✅
- Tests using a small fixture graph ✅

Acceptance criteria:

- Running `devmemory graphify ingest .` imports report and node memories.
- Re-running the command is idempotent.
- `devmemory search "architecture auth flow" --type graphify_report` returns imported report sections.

## Phase 2 — EdgeStore Integration ✅ Implemented

Deliverables:

- `--with-edges` support ✅
- Graphify relation to `EdgeStore` mapping ✅
- `get_memory_graph` works for Graphify node memories ✅

Acceptance criteria:

- Imported nodes are linked according to Graphify edges. ✅
- `trace_causality` remains unaffected because Graphify references do not use causal edge types. ✅
- Edge ingestion is idempotent. ✅

## Phase 3 — Agent-Facing Context

Deliverables:

- MCP tool `search_code_graph`
- MCP tool `get_code_entity_context`
- `ContextEngine` boost for `graphify_report` and `graphify_node` on architecture/codebase-map intents

Acceptance criteria:

- Agents can ask codebase architecture questions without reading raw files first.
- `build_context(..., intent="architecture")` includes Graphify-derived memories when relevant.

## Phase 4 — Optional Build Automation

Deliverables:

- `devmemory graphify build`
- Optional daemon job to ingest changed `graphify-out/graph.json`
- Config flag for enabling/disabling scheduled Graphify ingestion

Acceptance criteria:

- If Graphify is installed, DevMemoryIndex can build and import graph output in one command.
- If Graphify is not installed, the CLI shows clear install instructions.

---

## Testing Plan

Add fixtures:

```text
tests/fixtures/graphify/graphify-out/graph.json
tests/fixtures/graphify/graphify-out/GRAPH_REPORT.md
```

Test cases:

1. Parses Graphify report sections.
2. Parses Graphify node-link JSON with `links` and `edges` variants.
3. Deterministic IDs prevent duplicates.
4. `--min-degree` filters low-signal nodes.
5. Edge ingestion maps known relations correctly.
6. Missing Graphify output returns a clear error.
7. Corrupt `graph.json` does not crash the CLI.
8. Search returns imported Graphify memories.

---

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Graphify output schema changes | Treat `graph.json` defensively; support both `links` and `edges`; ignore unknown fields |
| Too many node memories | Use `--min-degree`, degree-based importance, and optional community-only mode |
| Duplicate functionality with filesystem connector | Keep Graphify optional and architecture-focused; filesystem connector remains raw code chunk memory |
| EdgeStore pollution | Map most relations to `references`/`related_to`; avoid causal edge types |
| Large graph import latency | Batch embeddings with `embed_batch`; add dry-run/counts first |
| Privacy concerns from committed graph outputs | Reuse existing redaction where possible; document that Graphify output may contain source-derived content |

---

## Recommended First PR

Implement **Phase 1 only**.

Files likely needed:

```text
connectors/graphify_connector.py
cli/commands/graphify_cmd.py
cli/main.py
core/config.py                  # optional helpers only if adding config now
tests/fixtures/graphify/...
tests/test_graphify_connector.py
cli/tests/test_graphify_cli.py
README.md                       # short mention only
```

Keep the first PR small:

- Ingest `GRAPH_REPORT.md`
- Ingest selected `graph.json` nodes
- No daemon automation
- No edge ingestion by default
- No MCP changes yet

This gives DevMemoryIndex immediate value from Graphify while preserving a clean path toward deeper graph integration.
