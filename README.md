# DevMemoryIndex

A developer memory index that captures, stores, and semantically searches knowledge fragments from your development workflow — git commits, terminal commands, agent solutions, Copilot chats, and file contents — using vector embeddings and LanceDB.

## Overview

DevMemoryIndex turns your day-to-day development activity into a searchable, vector-indexed knowledge base. Instead of relying on your own recall (or endlessly grepping through history), you can store memories with rich metadata and retrieve them later via natural-language similarity search.

## Architecture

```
core/               Core library (schema, embeddings, storage)
api/                REST API layer (FastAPI — planned)
cli/                Command-line interface (planned)
connectors/         Integrations (Git, terminal, Copilot — planned)
daemon/             Background indexing service (planned)
memory_db/          LanceDB on-disk database (auto-created)
```

## Functional Capabilities

### 1. Memory Schema (`core/schema.py`)

Defines the `Memory` dataclass — the atomic unit of knowledge stored in the index.

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Unique identifier (UUID or hash) |
| `type` | `str` | Category: `git_commit`, `terminal_command`, `agent_solution`, `copilot_chat`, `file_content` |
| `summary` | `str` | Short human-readable summary (~200 chars) |
| `raw_text` | `str` | Full original text |
| `source` | `str` | Origin — filepath, repo URL, agent name, etc. |
| `repo` | `str \| None` | Repository name (optional, for git-sourced memories) |
| `timestamp` | `datetime` | When the memory was created |
| `tags` | `List[str]` | Freeform keyword tags for filtering |
| `importance` | `float` | Ranking weight from 0 to 1 (default `0.5`) |

Supported memory types:
- **`git_commit`** — diffs, commit messages, and metadata from version control
- **`terminal_command`** — shell commands and their outputs
- **`agent_solution`** — solutions produced by AI coding agents
- **`copilot_chat`** — conversations and suggestions from GitHub Copilot
- **`file_content`** — raw file contents or excerpts

### 2. Embedding Generation (`core/embeddings.py`)

Converts text into 384-dimensional dense vectors using the [BAAI/bge-small-en](https://huggingface.co/BAAI/bge-small-en) sentence-transformer model.

| Function | Description |
|---|---|
| `embed(text: str) -> list` | Embed a single text string and return a float vector |
| `embed_batch(texts: list) -> list` | Embed multiple texts in one call (batch-optimized) |

- Model is loaded once at module import for fast repeated calls.
- Produces 384-dim float32 vectors compatible with LanceDB's vector search.

### 3. Memory Store (`core/memory_store.py`)

Persists memories with their embedding vectors in a LanceDB table and provides vector similarity search.

| Function | Description |
|---|---|
| `save_memory(memory, vector, collection=None)` | Insert a `Memory` + its embedding vector into the database |
| `search_memory(query_vector, n_results=5, collection=None)` | Find the top-N most similar memories by vector distance |

Key details:
- **Storage engine**: LanceDB (columnar, on-disk, embedded — no external server needed).
- **Vector dimension**: 384 (matches `bge-small-en` output).
- **Schema**: Apache Arrow schema with typed fields for all `Memory` attributes plus a `vector` column.
- **Default database path**: `./memory_db`.
- **Collection injection**: Both `save_memory` and `search_memory` accept an optional `collection` parameter, enabling dependency injection for testing or multi-tenant setups.

### 4. Test Suite (`core/tests/`)

Comprehensive pytest-based test coverage:

| Test File | Coverage |
|---|---|
| `test_schema.py` | Memory creation, field validation, default `importance` value |
| `test_memory_store.py` | Saving memories, single-result search, multi-memory ranked search |

Tests use temporary LanceDB instances (via `tmp_path` fixture) for full isolation.

## Planned Modules

| Module | Purpose |
|---|---|
| **`api/`** | FastAPI REST server exposing save/search endpoints over HTTP |
| **`cli/`** | Command-line tool for indexing and querying memories from the terminal |
| **`connectors/`** | Plug-in integrations to automatically ingest from Git, terminal history, Copilot, and other sources |
| **`daemon/`** | Background service that continuously watches for new developer activity and indexes it |

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.12+ |
| Embeddings | [sentence-transformers](https://www.sbert.net/) / `BAAI/bge-small-en` |
| Vector DB | [LanceDB](https://lancedb.com/) (embedded, columnar) |
| API (planned) | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| Testing | [pytest](https://docs.pytest.org/) |
| Build | [Hatch](https://hatch.pypa.io/) |
| Package manager | [uv](https://docs.astral.sh/uv/) |

## Getting Started

### Installation

```bash
# Clone the repository
git clone <repo-url> && cd devmemoryindex

# Create virtual environment and install dependencies
uv sync --group dev
```

### Usage

```python
from datetime import datetime
from core.schema import Memory
from core.embeddings import embed
from core.memory_store import save_memory, search_memory

# Create a memory
memory = Memory(
    id="abc-123",
    type="git_commit",
    summary="Fixed Redis timeout in billing API",
    raw_text="diff --git a/billing.py ...",
    source="/repos/billing-api",
    repo="billing-api",
    timestamp=datetime.now(),
    tags=["bugfix", "redis", "timeout"],
    importance=0.8,
)

# Embed and save
vector = embed(memory.raw_text)
save_memory(memory, vector)

# Search by natural language
query_vector = embed("redis connection timeout fix")
results = search_memory(query_vector, n_results=3)

for r in results:
    print(r["summary"], r["importance"])
```

### Running Tests

```bash
uv run pytest core/tests/ -v
```
