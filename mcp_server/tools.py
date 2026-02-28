"""
MCP tool implementations for DevMemoryIndex.

These functions are exposed as MCP tools via mcp_server/server.py.
Their docstrings are what Claude sees as the tool description — keep them
precise and action-oriented.

Tool summary:
  search_memories      — hybrid search (semantic + keyword) over the memory store
  build_context        — returns a formatted context block ready to paste into a prompt
  remember_memory      — persists a solution/decision so it's findable in future sessions
  get_memory           — fetch a single memory by ID (use to resolve related[] from search results)
  get_session_context  — call once at session start to bootstrap context from task + git state
  remember_failure     — record a failed approach so future sessions don't repeat the same mistake
"""

import hashlib
import subprocess
from datetime import datetime
from pathlib import Path

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
    files: list[str] | None = None,
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
        files:      Optional list of file paths you're actively editing. Extracts stems,
                    parent dirs, and import keywords to enrich the query automatically.

    Returns:
        Formatted string ready to prepend to a prompt or display directly.
    """
    enriched = f"{query} {_file_signals(files)}".strip() if files else query
    store = get_store()
    engine = ContextEngine(store)
    result = engine.build(query=enriched, repo=repo, max_tokens=max_tokens, format=format, intent=intent)
    return result["context_text"]


def _auto_summarize(raw_text: str) -> str:
    """Extract a summary from raw_text when none is provided.

    Takes the first sentence longer than 30 characters that contains a space.
    Falls back to the first 100 characters of raw_text if no sentence qualifies.
    No LLM required — pure heuristic.
    """
    for sentence in raw_text.replace("\n", " ").split("."):
        s = sentence.strip()
        if len(s) > 30 and " " in s:
            return s[:200]
    return raw_text.strip()[:200]


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
        A "warning" key is included when the summary is too short for reliable retrieval.
    """
    store = get_store()
    raw = raw_text or summary

    # Quality check: auto-generate summary from raw_text if summary is blank/missing
    effective_summary = summary.strip() if summary.strip() else _auto_summarize(raw)

    mem_id = hashlib.sha256(raw[:500].encode()).hexdigest()
    if store.exists(mem_id):
        return {"status": "duplicate", "id": mem_id}
    memory = Memory(
        id=mem_id,
        type=memory_type,
        summary=effective_summary[:200],
        raw_text=raw,
        source="mcp_agent",
        repo=repo,
        timestamp=datetime.utcnow(),
        tags=tags + ["agent"],
        importance=importance,
    )
    store.add(memory, embed(memory.summary))
    result: dict = {"status": "ok", "id": mem_id}
    if len(effective_summary) < 20:
        result["warning"] = "summary may be too short for reliable retrieval — consider a more descriptive summary"
    return result


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


def _file_signals(files: list[str]) -> str:
    """Extract query-enriching terms from a list of file paths.

    For each file: takes the stem, parent directory name, and keywords from
    the first 20 lines (import module names + first docstring line).
    """
    signals = []
    for f in files:
        p = Path(f)
        signals.append(p.stem)
        if p.parent.name:
            signals.append(p.parent.name)
        try:
            with open(f, errors="replace") as fh:
                head = [fh.readline() for _ in range(20)]
            for line in head:
                s = line.strip()
                if s.startswith("import ") or s.startswith("from "):
                    # "from core.memory_store import MemoryStore" → ["core.memory_store", "MemoryStore"]
                    parts = s.split()
                    signals.extend(parts[1:4])
                elif s.startswith('"""') or s.startswith("'''"):
                    # first docstring line — strip quotes and take first 60 chars
                    signals.append(s.strip('"\' '))
        except Exception:
            pass
    return " ".join(signals)


def _git_signals() -> str:
    """Return modified file stems + recent commit subjects as extra query terms."""
    signals = []
    try:
        status = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, timeout=3
        ).stdout
        for line in status.splitlines():
            # " M core/memory_store.py" → "memory_store"
            path = line.strip().split()[-1]
            signals.append(Path(path).stem)
    except Exception:
        pass
    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True, text=True, timeout=3
        ).stdout
        signals.append(log.strip())
    except Exception:
        pass
    return " ".join(signals)


def get_session_context(
    task_description: str,
    repo: str | None = None,
    files: list[str] | None = None,
) -> str:
    """Call once at session start to surface relevant past context before writing any code.

    Combines the task description with current git state (modified files, recent commits)
    and optionally the content of files you're about to edit, to pull the most relevant
    memories without requiring a precise query.

    Args:
        task_description: What you're about to work on, in plain language.
        repo:             Optional repo filter.
        files:            Optional list of file paths you're about to edit. Extracts stems,
                          parent dirs, and import keywords to enrich the query automatically.

    Returns:
        Formatted <context>...</context> block ready to prepend to your working context.
    """
    git_extra = _git_signals()
    file_extra = _file_signals(files) if files else ""
    enriched_query = f"{task_description} {git_extra} {file_extra}".strip()
    store = get_store()
    engine = ContextEngine(store)
    result = engine.build(query=enriched_query, repo=repo, max_tokens=3000, format="claude")
    return result["context_text"]


def remember_failure(
    summary: str,
    what_was_tried: str,
    why_it_failed: str,
    repo: str | None = None,
) -> dict:
    """Record a failed approach so future sessions don't repeat the same mistake.

    Args:
        summary:        One sentence: what was attempted and that it failed.
        what_was_tried: The approach, command, or code that was tried.
        why_it_failed:  The error, reason, or consequence.
        repo:           Repository this applies to.

    Returns:
        {"status": "ok"|"duplicate", "id": "..."}
    """
    store = get_store()
    raw = f"ATTEMPTED: {what_was_tried}\n\nWHY IT FAILED: {why_it_failed}"
    mem_id = hashlib.sha256(raw[:500].encode()).hexdigest()
    if store.exists(mem_id):
        return {"status": "duplicate", "id": mem_id}
    memory = Memory(
        id=mem_id,
        type="failure_note",
        summary=summary[:200],
        raw_text=raw,
        source="mcp_agent",
        repo=repo,
        timestamp=datetime.utcnow(),
        tags=["attempted", "failed", "avoid"],
        importance=0.7,
    )
    store.add(memory, embed(memory.summary))
    return {"status": "ok", "id": mem_id}
