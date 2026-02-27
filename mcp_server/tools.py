"""
MCP tool implementations for DevMemoryIndex.

These functions are exposed as MCP tools via mcp_server/server.py.
Their docstrings are what Claude sees as the tool description — keep them
precise and action-oriented.

Tool summary:
  search_memories  — hybrid search (semantic + keyword) over the memory store
  build_context    — returns a formatted context block ready to paste into a prompt
  remember_memory  — persists a solution/decision so it's findable in future sessions
  get_memory       — fetch a single memory by ID (use to resolve related[] from search results)
"""

import hashlib
from datetime import datetime

from core.store_provider import get_store
from core.embeddings import embed
from core.context_engine import ContextEngine
from core.schema import Memory


def search_memories(
    query: str,
    k: int = 5,
    memory_type: str | None = None,
    repo: str | None = None,
) -> list[dict]:
    """Search developer memory for relevant past solutions, commits, notes, and commands.

    Uses hybrid search (semantic vector similarity + keyword matching) over all indexed
    memories. Results are ranked by relevance, importance, and recency.

    Args:
        query:       Natural language search query. Use specific technical terms for
                     best results (e.g. "lancedb schema timestamp fix" not "database bug").
        k:           Max number of results to return. Default 5.
        memory_type: Optional filter by memory type. Common values:
                       "git_commit"     — indexed commit messages
                       "agent_solution" — solutions persisted by Claude via remember_memory
                       "voice_note"     — dictated voice memories
        repo:        Optional filter by repository name (e.g. "devmemoryindex").

    Returns:
        List of dicts with keys: summary, type, repo, importance, tags.
    """
    store = get_store()
    vector = embed(query)
    results = store.hybrid_search(query, vector, k=k, type_filter=memory_type, repo_filter=repo)
    return [
        {
            "id": r["id"],
            "summary": r["summary"],
            "type": r["type"],
            "repo": r.get("repo"),
            "importance": r.get("importance"),
            "tags": r.get("tags", []),
            "related": r.get("related", []),
        }
        for r in results
    ]


def build_context(
    query: str,
    max_tokens: int = 4000,
    repo: str | None = None,
    format: str = "claude",
    intent: str | None = None,
) -> str:
    """Build AI-ready context from developer memory for the given task or query.

    Runs hybrid search, deduplicates results, packs them within a token budget,
    and formats them as a structured context block. Use this before starting a
    complex implementation task to surface relevant past decisions and solutions.

    Args:
        query:      Describe the task or problem you're about to work on.
        max_tokens: Token budget for the returned context block. Default 4000.
        repo:       Optional filter to restrict context to a single repository.
        format:     Output format. Options:
                      "claude"   — <context>...</context> XML block (default, best for Claude)
                      "markdown" — ### Relevant Past Solutions header with bullet list
                      "raw"      — plain text, one summary per line
        intent:     Optional intent override to control result weighting. Options:
                      "debug"          — boost agent_solution + terminal_command
                      "architecture"   — boost agent_solution + git_commit, lower recency weight
                      "implementation" — boost git_commit + terminal_command
                      "recall"         — boost voice_note, raise recency weight
                    Auto-classified from query if not provided.

    Returns:
        Formatted string ready to prepend to a prompt or display directly.
    """
    store = get_store()
    engine = ContextEngine(store)
    result = engine.build(query=query, repo=repo, max_tokens=max_tokens, format=format, intent=intent)
    return result["context_text"]


def remember_memory(
    summary: str,
    raw_text: str | None = None,
    memory_type: str = "agent_solution",
    repo: str | None = None,
    importance: float = 0.9,
    tags: list[str] = [],
) -> dict:
    """Persist a solution or decision to developer memory for future retrieval.

    Call this after solving a non-trivial problem, making an architectural decision,
    or discovering something worth remembering across sessions. Duplicates are
    detected by content hash and silently skipped.

    Args:
        summary:     One-sentence description of the solution or decision (max 200 chars).
                     This is what appears in search results — make it specific and searchable.
        raw_text:    Full detail: code snippet, explanation, steps taken, error message, etc.
                     If omitted, summary is used as raw_text.
        memory_type: Category tag. Default "agent_solution". Other useful values:
                       "architectural_decision" — design choices and their rationale
                       "debugging_insight"      — non-obvious bugs and how they were found
                       "workflow"               — process or command sequences worth remembering
        repo:        Repository this memory belongs to (e.g. "devmemoryindex").
        importance:  Float 0.0–1.0. Default 0.9 for agent solutions (high value by default).
        tags:        Additional tags for filtering (e.g. ["lancedb", "schema"]).

    Returns:
        {"status": "ok", "id": "<hash>"} on success.
        {"status": "duplicate", "id": "<hash>"} if already stored.
    """
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


def get_memory(memory_id: str) -> dict | None:
    """Fetch a single memory by its exact ID.

    Use this to resolve related memory IDs returned by search_memories. Each
    search result includes a "related" field — a list of IDs of semantically
    nearby memories that didn't make it into the top-k results. Call get_memory
    on those IDs to pull in connected context without an extra search.

    Args:
        memory_id: The exact memory ID string (from search result "id" or "related" fields).

    Returns:
        Dict with keys: id, type, summary, raw_text, repo, importance, tags, timestamp.
        None if not found.
    """
    store = get_store()
    record = store.get_by_id(memory_id)
    if record is None:
        return None
    return {
        "id": record.get("id"),
        "type": record.get("type"),
        "summary": record.get("summary"),
        "raw_text": record.get("raw_text"),
        "repo": record.get("repo"),
        "importance": record.get("importance"),
        "tags": record.get("tags", []),
        "timestamp": str(record.get("timestamp")),
    }
