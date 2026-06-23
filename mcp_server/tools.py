"""
MCP tool implementations for DevMemoryIndex.

These functions are exposed as MCP tools via mcp_server/server.py.
Their docstrings are what MCP clients expose as tool descriptions — keep them
precise, action-oriented, and agent-agnostic.

Tool summary:
  search_memories      — hybrid search (semantic + keyword) over the memory store
  build_context        — returns a formatted context block ready to paste into a prompt
  remember_memory      — persists a solution/decision so it's findable in future sessions
  get_memory           — fetch a single memory by ID (use to resolve related[] from search results)
  get_session_context  — call once at session start to bootstrap context from task + git state
  remember_failure     — record a failed approach so future sessions don't repeat the same mistake
  update_memory        — correct or improve an existing memory in-place
  reinforce_memory     — explicitly boost importance after successfully applying a solution
  get_codebase_map     — cluster file_content memories to reveal subsystem structure
  plan_task            — generate a grounded implementation plan from memory + git context
  explain_score        — explain why a specific memory ranked where it did (T1-A)
  why_not_included     — explain why a memory was excluded from build_context results (T1-A)
  forget_memory        — deprecate a memory with a reason; excludes from search but preserves for audit (T1-D)
  get_store_health     — return store quality metrics: type breakdown, stale count, CTR (T1-E)
  consolidate_memories — merge multiple memories into one canonical memory (T1-C)
  search_batch         — run multiple searches in parallel and return deduplicated results (T1-F)
  link_memories        — create a typed edge between two memories (T2-A)
  get_memory_graph     — return the subgraph of memories connected to a given memory (T2-A)
  trace_causality      — follow causal chain from a memory to its root cause (T2-A)
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
    speaker: str | None = None,
) -> list[dict]:
    """Search developer memory for relevant past solutions, commits, notes, and commands.

    Use before debugging, refactoring, changing unfamiliar code, or answering "how did
    we handle X before?" questions. Prefer specific technical terms, errors, file names,
    library names, and repo filters. Do not use broad queries like "bug" or "memory"
    unless exploring; narrow them after the first result. Use returned IDs with get_memory
    when a result or related[] ID looks actionable.

    Uses hybrid search (semantic vector similarity + keyword matching) over all indexed
    memories. Results are ranked by relevance, importance, and recency.

    Args:
        query:       Natural language search query. Use specific technical terms for
                     best results (e.g. "lancedb schema timestamp fix" not "database bug").
        k:           Max number of results to return. Default 5.
        memory_type: Optional filter by memory type. Common values:
                       "git_commit"     — indexed commit messages
                       "agent_solution" — solutions persisted by MCP agents via remember_memory
                       "voice_note"     — dictated voice memories
        repo:        Optional filter by repository name (e.g. "devmemoryindex").
        speaker:     Optional filter by speaker name (e.g. "Sarah" or "self").
                     Matches memories tagged with "speaker:<name>" from meeting transcripts.
                     Use "self" to find memories where you were the speaker.

    Returns:
        List of dicts with keys: summary, type, repo, importance, tags,
        times_retrieved, times_accessed, related.
        times_retrieved = how many times this memory appeared in search results.
        times_accessed  = how many times get_memory was called on it (explicit reads).
        High times_accessed relative to times_retrieved = proven, high-signal solution.
    """
    store = get_store()
    vector = embed(query)
    results = store.hybrid_search(
        query, vector, k=k,
        type_filter=memory_type,
        repo_filter=repo,
        speaker_filter=speaker,
    )
    return [
        {
            "id": r["id"],
            "summary": r["summary"],
            "type": r["type"],
            "repo": r.get("repo"),
            "importance": r.get("importance"),
            "tags": r.get("tags", []),
            "related": r.get("related", []),
            "times_retrieved": r.get("times_retrieved", 0) or 0,
            "times_accessed": r.get("times_accessed", 0) or 0,
            "score_breakdown": r.get("score_breakdown"),  # T1-A: explainability
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
) -> dict:
    """Build AI-ready context from developer memory for the given task or query.

    Runs hybrid search, deduplicates results, packs them within a token budget,
    and formats them as a structured context block. Use this before starting a
    complex implementation task to surface relevant past decisions and solutions.

    Args:
        query:      Describe the task or problem you're about to work on.
        max_tokens: Token budget for the returned context block. Default 4000.
        repo:       Optional filter to restrict context to a single repository.
        format:     Output format. Options:
                      "claude"   — <context>...</context> XML block (default; useful for XML-friendly agents)
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
        dict with keys:
          - "context_text": Formatted string ready to prepend to a prompt or display directly.
          - "retrieval_trace": {included, dropped_dedup, dropped_budget, intent_detected,
                                total_candidates} — shows which memories were included vs dropped.
          - "memory_count": number of memories included.
          - "token_estimate": estimated token count.
    """
    enriched = f"{query} {_file_signals(files)}".strip() if files else query
    store = get_store()
    engine = ContextEngine(store)
    result = engine.build(query=enriched, repo=repo, max_tokens=max_tokens, format=format, intent=intent)
    return {
        "context_text": result["context_text"],
        "retrieval_trace": result.get("retrieval_trace", {}),
        "memory_count": result.get("memory_count", 0),
        "token_estimate": result.get("token_estimate", 0),
    }


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

    Use only after a solution is verified, a durable architectural decision is made,
    or a reusable workflow/root cause is discovered. Do not store transient task progress,
    PR numbers, issue numbers, branch names, copied logs without explanation, or anything
    likely to be stale within a week. Do not store secrets, tokens, credentials, or private
    personal data. Duplicates are detected by content hash and silently skipped.

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

    # Quality check: auto-generate summary from raw_text if summary is blank/missing.
    # T1-G: If [connectors] auto_summarize = true, try LLM summarization first.
    if summary.strip():
        effective_summary = summary.strip()
    else:
        from core.config import get_auto_summarize
        if get_auto_summarize():
            from core.llm_backend import llm_summarize
            llm_result = llm_summarize(raw)
            effective_summary = llm_result or _auto_summarize(raw)
        else:
            effective_summary = _auto_summarize(raw)

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

    Use this as the first DevMemoryIndex call for complex coding/debugging work.
    Do not call repeatedly during the same task; reuse the returned context unless the
    task changes substantially. If returned context is insufficient, follow up with
    search_memories using specific technical terms, then get_memory for promising IDs.

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


def update_memory(
    memory_id: str,
    summary: str | None = None,
    raw_text: str | None = None,
    importance: float | None = None,
) -> dict:
    """Correct or improve an existing memory in-place.

    Use this when a stored solution turns out to be wrong, incomplete, or outdated.
    Prevents knowledge rot — bad memories at importance=0.9 stay bad without correction.

    Providing a new summary or raw_text triggers re-embedding so the memory is
    searchable by the updated content. Counters (times_retrieved, times_accessed)
    are preserved. The memory ID stays the same.

    Args:
        memory_id:  Exact ID of the memory to update (from search_memories or get_memory).
        summary:    New one-sentence description (max 200 chars). Pass None to keep existing.
        raw_text:   New full detail text. Pass None to keep existing.
        importance: New importance float 0.0–1.0. Pass None to keep existing.

    Returns:
        {"status": "ok", "id": "..."} on success.
        {"status": "not_found"} if memory_id does not exist.
    """
    store = get_store()
    ok = store.update(memory_id, summary=summary, raw_text=raw_text, importance=importance)
    if not ok:
        return {"status": "not_found"}
    return {"status": "ok", "id": memory_id}


def reinforce_memory(memory_id: str) -> dict:
    """Explicitly boost importance of a memory after successfully applying it.

    Call this when a retrieved solution or pattern was applied and worked.
    Boosts importance by +0.05 (capped at 0.95), making the memory rank higher
    in future searches. This is the explicit success feedback loop — use it to
    mark proven solutions so they surface ahead of untested ones.

    Args:
        memory_id: Exact ID of the memory to reinforce (from search_memories results).

    Returns:
        {"status": "ok", "id": "...", "new_importance": float} on success.
        {"status": "not_found"} if memory_id does not exist.
    """
    store = get_store()
    new_importance = store.boost_importance(memory_id, amount=0.05, cap=0.95)
    if new_importance is None:
        return {"status": "not_found"}
    return {"status": "ok", "id": memory_id, "new_importance": new_importance}


def get_codebase_map(
    repo: str | None = None,
    n_clusters: int = 8,
) -> dict:
    """Cluster indexed file_content memories to reveal the codebase's subsystem structure.

    Uses KMeans over stored embedding vectors to group files by semantic similarity.
    Each cluster gets a label (most common path prefix) and a representative file.
    Use this at the start of a session on an unfamiliar or recently-refactored repo
    to get a structural overview before searching for specific things.

    Requires scikit-learn: uv add 'devmemoryindex[ml]'

    Args:
        repo:       Optional repo name to restrict the map to a single project.
        n_clusters: Target number of clusters (adjusted down if fewer files exist).

    Returns:
        dict with:
          - "clusters": list of {label, size, representative, files[]}
          - "total_files": number of file_content memories clustered
          - "error": present only when clustering is not possible (too few files, missing dep)
    """
    from core.codebase_map import build_codebase_map
    store = get_store()
    return build_codebase_map(store, repo=repo, n_clusters=n_clusters)


def plan_task(
    description: str,
    repo: str | None = None,
    files: list[str] | None = None,
) -> dict:
    """Generate a grounded implementation plan backed by memory + current git state.

    Combines relevant past solutions from the memory index with the current git diff
    and recent commits, then calls the configured local LLM (Ollama by default) to
    produce a numbered step-by-step plan. Use this before writing any code on a
    non-trivial task to avoid repeating past mistakes and leverage prior art.

    Requires Ollama running locally (or configured LLM backend).

    Args:
        description: Plain-language description of the task to plan.
        repo:        Optional repo filter for memory retrieval.
        files:       Optional list of file paths you're about to edit — enriches
                     the memory search with import keywords and path signals.

    Returns:
        dict with:
          - "plan": the generated implementation plan (markdown string)
          - "memory_count": number of memories used as context
          - "error": present only if the LLM backend failed
    """
    from core.store_provider import get_store as _get_store
    from core.context_engine import ContextEngine
    from core.plan_engine import plan_task as _plan, get_git_context

    store = _get_store()
    engine = ContextEngine(store)

    file_signals = _file_signals(files) if files else ""
    enriched_query = f"{description} {file_signals}".strip()
    context_result = engine.build(query=enriched_query, repo=repo, max_tokens=2000, format="raw")
    memory_context = context_result["context_text"]
    memory_count = context_result.get("memory_count", 0)

    git_context = get_git_context()

    try:
        plan_text = _plan(description, memory_context, git_context, files)
    except Exception as e:
        return {"plan": "", "memory_count": memory_count, "error": str(e)}

    return {"plan": plan_text, "memory_count": memory_count}


# ── T1-A: Score Explainability ────────────────────────────────────────────────

def explain_score(memory_id: str, query: str) -> dict:
    """Explain why a specific memory ranked where it did for a given query.

    Returns the individual score components (semantic similarity, importance,
    recency) and a human-readable explanation of how they combined into the
    final score. Use this to understand why a memory surfaced or to diagnose
    ranking surprises.

    Args:
        memory_id: The exact ID of the memory to explain (from search results).
        query:     The search query used when this memory ranked.

    Returns:
        dict with:
          - "id": memory ID
          - "summary": memory summary (for context)
          - "score_breakdown": {semantic, importance, recency, final}
          - "explanation": human-readable explanation string
          - "query": the query used for scoring
    """
    from core.ranking import compute_score_breakdown
    store = get_store()
    record = store.get_by_id(memory_id, reinforce=False)
    if record is None:
        return {"error": f"Memory '{memory_id}' not found"}

    vector = embed(query)
    # Run search to get the _distance for this specific memory relative to the query
    candidates = store.hybrid_search(query, vector, k=50)
    match = next((c for c in candidates if c["id"] == memory_id), None)

    if match is None:
        # Memory wasn't in top-50 — score it with maximum distance
        record["_distance"] = 1.0
        breakdown = compute_score_breakdown(record)
        explanation = (
            f"This memory did not appear in the top-50 results for '{query}'. "
            f"Semantic similarity: {breakdown['semantic']:.2f} (low — memory content "
            f"is distant from the query vector). Importance: {breakdown['importance']:.2f}. "
            f"Recency: {breakdown['recency']:.2f}."
        )
    else:
        breakdown = match.get("score_breakdown") or compute_score_breakdown(match)
        sem = breakdown["semantic"]
        imp = breakdown["importance"]
        rec = breakdown["recency"]
        final = breakdown["final"]
        explanation = (
            f"Final score {final:.3f} = semantic({sem:.2f}) × 0.75 "
            f"+ importance({imp:.2f}) × 0.15 "
            f"+ recency({rec:.2f}) × 0.10. "
        )
        if sem >= 0.7:
            explanation += "High semantic similarity — content closely matches query. "
        elif sem >= 0.4:
            explanation += "Moderate semantic match. "
        else:
            explanation += "Low semantic similarity — may have ranked via keyword match. "
        if imp >= 0.8:
            explanation += f"High importance ({imp:.2f}) boosted rank. "
        if rec < 0.2:
            explanation += "Recency contribution is low — memory is older than 30 days."

    return {
        "id": memory_id,
        "summary": record.get("summary", ""),
        "query": query,
        "score_breakdown": breakdown,
        "explanation": explanation.strip(),
    }


def why_not_included(memory_id: str, query: str, max_tokens: int = 4000) -> dict:
    """Explain why a memory was excluded from a build_context result.

    Use this when a specific memory looks relevant but did not appear in the
    context block, or when tuning query wording/token budgets. Prefer running it
    with the same query and max_tokens used for build_context so diagnostics match.

    Diagnoses whether the memory was:
      - Not in any search results (too dissimilar to the query)
      - In results but dropped by deduplication (near-identical to a higher-ranked memory)
      - In results but dropped by the token budget

    Args:
        memory_id:  The memory ID to investigate.
        query:      The query used with build_context.
        max_tokens: Token budget that was used (default 4000).

    Returns:
        dict with:
          - "reason": one of "not_in_results" | "dropped_dedup" | "dropped_budget" | "included"
          - "explanation": human-readable explanation
          - "score_breakdown": score if it appeared in results
    """
    store = get_store()
    engine = ContextEngine(store)
    result = engine.build(query=query, max_tokens=max_tokens, format="raw")
    trace = result.get("retrieval_trace", {})

    if memory_id in trace.get("included", []):
        record = store.get_by_id(memory_id, reinforce=False)
        score = record.get("score_breakdown") if record else None
        return {
            "reason": "included",
            "explanation": "This memory WAS included in the context results.",
            "score_breakdown": score,
        }

    if memory_id in trace.get("dropped_dedup", []):
        return {
            "reason": "dropped_dedup",
            "explanation": (
                "This memory was retrieved but dropped during deduplication because "
                "another memory with a near-identical summary prefix was already included. "
                "Consider updating the summary to be more unique."
            ),
            "score_breakdown": None,
        }

    if memory_id in trace.get("dropped_budget", []):
        return {
            "reason": "dropped_budget",
            "explanation": (
                f"This memory was retrieved and passed deduplication but was excluded "
                f"because the token budget ({max_tokens} tokens) was exhausted by "
                f"higher-ranked memories. Try increasing max_tokens or narrowing the query."
            ),
            "score_breakdown": None,
        }

    # Not in any results
    vector = embed(query)
    candidates = store.hybrid_search(query, vector, k=50)
    match = next((c for c in candidates if c["id"] == memory_id), None)
    if match:
        breakdown = match.get("score_breakdown")
        return {
            "reason": "low_rank",
            "explanation": (
                f"This memory appeared in search results but ranked below the top-50 "
                f"selected for context building. Final score: {breakdown['final']:.3f}."
            ),
            "score_breakdown": breakdown,
        }

    return {
        "reason": "not_in_results",
        "explanation": (
            "This memory did not appear in the top-50 hybrid search results for this query. "
            "It may have low semantic similarity to the query, or the query terms don't "
            "match the memory's summary or raw_text. Try a more specific query or use "
            "search_memories() with different terms."
        ),
        "score_breakdown": None,
    }


# ── T1-D: Forget Memory with Audit Trail ─────────────────────────────────────

def forget_memory(memory_id: str, reason: str = "") -> dict:
    """Deprecate a memory — excludes it from all future searches but preserves it for audit.

    Use this instead of permanently deleting when you want to flag a memory as
    outdated, incorrect, or superseded without losing the record that it existed.
    Deprecated memories appear in `devmemory audit` and can be permanently deleted
    after human review.

    Args:
        memory_id: The exact memory ID to deprecate (from search_memories results).
        reason:    Human-readable explanation for why the memory is being deprecated.
                   E.g. "superseded by new lancedb schema", "approach was incorrect".

    Returns:
        {"status": "ok", "id": "...", "reason": "..."} on success.
        {"status": "not_found"} if memory_id does not exist.
    """
    store = get_store()
    ok = store.forget(memory_id, reason=reason)
    if not ok:
        return {"status": "not_found"}
    return {"status": "ok", "id": memory_id, "reason": reason}


# ── T1-E: Store Health ────────────────────────────────────────────────────────

def get_store_health() -> dict:
    """Return a quality and health report on the memory store.

    Use this before a cleanup/consolidation pass, when search quality appears noisy,
    or when diagnosing stale/low-signal memories. Do not treat metrics alone as a
    deletion mandate; inspect candidate memories before forgetting or consolidating.

    Surfaces metrics that help identify stale, redundant, or low-signal memories
    so agents can decide when to consolidate, forget, or prune the store.

    Returns:
        dict with:
          - "total": total memory count (active + deprecated)
          - "active": count of active (non-deprecated) memories
          - "deprecated": count of deprecated memories
          - "type_breakdown": {memory_type: count}
          - "importance_histogram": bucketed importance distribution
          - "avg_times_accessed": average explicit access count across active memories
          - "stale_count": active memories never accessed and older than 60 days
          - "low_ctr_count": retrieved 5+ times but accessed <10% of the time
    """
    store = get_store()
    return store.get_store_health()


# ── T1-C: Memory Consolidation ────────────────────────────────────────────────

def consolidate_memories(ids: list[str], summary: str | None = None) -> dict:
    """Merge multiple redundant memories into one canonical memory.

    Fetches all memories by the given IDs, combines their raw_text, and stores
    a new memory at the maximum importance of the originals. The original memories
    are permanently deleted. Use this to clean up 5+ variations of the same solution.

    Args:
        ids:     List of memory IDs to consolidate (minimum 2).
        summary: Optional new summary for the consolidated memory. If not provided,
                 uses the summary of the highest-importance memory in the set.

    Returns:
        {"status": "ok", "new_id": "...", "deleted": N} on success.
        {"status": "error", "message": "..."} if fewer than 2 valid IDs provided.
    """
    store = get_store()
    return store.consolidate(ids, summary=summary)


# ── T1-F: Batch Search ────────────────────────────────────────────────────────

def search_batch(queries: list[str], k: int = 5) -> dict:
    """Run multiple searches in parallel and return a deduplicated, unified result set.

    Use this when a task has several independent technical terms or hypotheses and
    separate searches would be redundant. Prefer 2-5 focused queries over one broad
    query. Do not use this for repeated variations of the same vague phrase.

    Useful when you want to search for several related topics at once without
    making separate search_memories() calls. Results are merged and deduplicated
    by ID, then re-ranked by final score.

    Args:
        queries: List of search queries (1–10 queries).
        k:       Max results per query before dedup (default 5).

    Returns:
        dict with:
          - "results": deduplicated list of memory results, sorted by score descending.
            Each result includes which query/queries retrieved it ("source_queries").
          - "total_unique": count of unique memories across all queries.
          - "query_count": number of queries run.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if not queries:
        return {"results": [], "total_unique": 0, "query_count": 0}

    store = get_store()

    def _run_query(q: str) -> tuple[str, list]:
        vector = embed(q)
        results = store.hybrid_search(q, vector, k=k)
        return q, results

    seen: dict[str, dict] = {}
    query_attribution: dict[str, list[str]] = {}

    with ThreadPoolExecutor(max_workers=min(len(queries), 5)) as pool:
        futures = {pool.submit(_run_query, q): q for q in queries[:10]}
        for future in as_completed(futures):
            try:
                q, results = future.result()
                for r in results:
                    mem_id = r["id"]
                    if mem_id not in seen:
                        seen[mem_id] = r
                    query_attribution.setdefault(mem_id, []).append(q)
            except Exception:
                pass

    merged = []
    for mem_id, r in seen.items():
        merged.append({
            "id": r["id"],
            "summary": r["summary"],
            "type": r["type"],
            "repo": r.get("repo"),
            "importance": r.get("importance"),
            "tags": r.get("tags", []),
            "score_breakdown": r.get("score_breakdown"),
            "times_retrieved": r.get("times_retrieved", 0) or 0,
            "times_accessed": r.get("times_accessed", 0) or 0,
            "source_queries": query_attribution.get(mem_id, []),
        })

    merged.sort(key=lambda x: (x.get("score_breakdown") or {}).get("final", 0), reverse=True)

    return {
        "results": merged,
        "total_unique": len(merged),
        "query_count": len(queries),
    }


# ── T2-A: Memory Entanglement (Typed Edge Graph) ──────────────────────────────

def link_memories(from_id: str, to_id: str, edge_type: str, confidence: float = 1.0) -> dict:
    """Create a typed causal/semantic edge between two memories.

    Use this after you have inspected both memories and know the relationship.
    Prefer precise edge types like "fixed_by" or "caused_by" over "related_to" when
    evidence supports them. Do not link memories just because they share keywords.

    Edges encode the relationship between memories so you can trace causal chains,
    find what fixed a bug, or see what a solution references.

    Edge types:
      "caused_by"   — from_id was caused by to_id (e.g. a failure caused by a bad pattern)
      "fixed_by"    — from_id was fixed by to_id (e.g. failure_note fixed by a commit)
      "references"  — from_id references to_id for context
      "supersedes"  — from_id supersedes/replaces to_id
      "contradicts" — from_id contradicts to_id
      "related_to"  — loose semantic relationship

    Args:
        from_id:    Source memory ID.
        to_id:      Target memory ID.
        edge_type:  One of the edge types listed above.
        confidence: Confidence of the edge (0.0–1.0). Default 1.0 for agent-created edges.

    Returns:
        {"status": "ok", "from": from_id, "to": to_id, "type": edge_type}
        {"status": "duplicate"} if this exact edge already exists.
        {"status": "error", "message": "..."} for invalid edge types.
    """
    from core.edge_store import VALID_EDGE_TYPES
    from core.edge_provider import get_edges
    if edge_type not in VALID_EDGE_TYPES:
        return {"status": "error", "message": f"Invalid edge_type '{edge_type}'. Valid: {sorted(VALID_EDGE_TYPES)}"}
    edges = get_edges()
    added = edges.add_edge(from_id, to_id, edge_type, confidence=confidence, source="agent")
    if not added:
        return {"status": "duplicate", "from": from_id, "to": to_id, "type": edge_type}
    return {"status": "ok", "from": from_id, "to": to_id, "type": edge_type, "confidence": confidence}


def get_memory_graph(memory_id: str, depth: int = 2) -> dict:
    """Return the subgraph of memories connected to a given memory.

    Traverses typed edges up to `depth` hops from the root memory, returning
    all reachable memory IDs and the edges connecting them. Use this to
    understand the full context around a decision, bug, or solution.

    Args:
        memory_id: Root memory ID to start the graph traversal from.
        depth:     Maximum hops to traverse (default 2, max 5).

    Returns:
        dict with:
          - "root": root memory ID
          - "nodes": all reachable memory IDs (including root)
          - "edges": list of {from_id, to_id, edge_type, confidence, source, created_at}
          - "node_count": number of nodes
          - "edge_count": number of edges
    """
    from core.edge_provider import get_edges
    edges = get_edges()
    depth = min(int(depth), 5)
    graph = edges.get_graph(memory_id, depth=depth)
    return {**graph, "node_count": len(graph["nodes"]), "edge_count": len(graph["edges"])}


def trace_causality(memory_id: str) -> dict:
    """Follow the causal chain from a memory back to its root cause.

    Use this for failure_note, bug, or incident memories that have caused_by/fixed_by
    links and you need root-cause context before changing code. Do not expect useful
    output until memories have been linked manually or by edge inference.

    Traverses "caused_by" and "fixed_by" edges from the given memory to the
    deepest ancestor in the causal chain. Returns an ordered sequence of
    memory IDs showing how a problem propagated or was resolved.

    Args:
        memory_id: Starting memory ID (typically a failure_note or bug report).

    Returns:
        dict with:
          - "chain": [{memory_id, step, via_edge}, ...] ordered from root to leaf
          - "length": number of steps in the chain
          - "root_cause_id": the last memory_id in the chain
    """
    from core.edge_provider import get_edges
    edges = get_edges()
    chain = edges.trace_causality(memory_id)
    return {
        "chain": chain,
        "length": len(chain),
        "root_cause_id": chain[-1]["memory_id"] if chain else memory_id,
    }


def remember_failure(
    summary: str,
    what_was_tried: str,
    why_it_failed: str,
    repo: str | None = None,
) -> dict:
    """Record a failed approach so future sessions don't repeat the same mistake.

    Use after a dead end consumed meaningful time, especially during debugging,
    installs, migrations, or performance work. Include the failed hypothesis, exact command
    or code path, observed error/output, and why it failed. Avoid recording
    trivial typos or first-attempt misses that future agents would not repeat.

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
