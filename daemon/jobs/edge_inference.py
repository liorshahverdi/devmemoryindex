"""
Edge Inference Job (T2-A)

Background weekly job that auto-links memories by inspecting:
  1. Git commits whose messages reference keywords from failure_notes →
     adds "fixed_by" edge: failure_note → git_commit
  2. Agent solutions whose summaries share significant keyword overlap with
     failure_notes → adds "references" edge

Run manually:
    python -m daemon.jobs.edge_inference

Scheduled in daemon/scheduler.py as weekly job.
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)


def _extract_keywords(text: str, min_len: int = 4) -> set[str]:
    """Extract meaningful lowercase words from text."""
    _STOPWORDS = {
        "a", "an", "the", "is", "in", "on", "at", "to", "for", "of", "and",
        "or", "where", "what", "how", "why", "when", "i", "me", "my", "it",
        "this", "that", "with", "from", "by", "be", "was", "are", "do", "did",
        "does", "not", "no", "can", "could", "would", "should", "have", "has",
        "had", "there", "any", "which", "who", "its", "as", "if", "fix", "fixed",
        "bug", "issue", "error", "the", "via", "into", "also", "adds", "added",
    }
    words = re.findall(r"\w+", (text or "").lower())
    return {w for w in words if len(w) >= min_len and w not in _STOPWORDS}


def _extract_test_identifiers(text: str) -> set[str]:
    """Extract pytest/unittest-style test identifiers from failure text."""
    if not text:
        return set()
    identifiers: set[str] = set()
    for match in re.findall(r"[\w./-]+\.py(?:::\w+)+", text):
        identifiers.add(match.lower())
        identifiers.add(match.split("::")[-1].lower())
    for match in re.findall(r"\btest_[A-Za-z0-9_]+\b", text):
        identifiers.add(match.lower())
    return identifiers


def _extract_stack_signatures(text: str) -> set[str]:
    """Extract stable stack-frame signatures independent of line numbers/paths.

    A signature is intentionally compact (e.g. ``frame:get_user`` or
    ``error:timeouterror:redis request timed out after 30s``) so the same failure
    in different repos can still be connected.
    """
    if not text:
        return set()
    signatures: set[str] = set()
    for func in re.findall(r'File "[^"]+", line \d+, in ([\w_<>]+)', text):
        signatures.add(f"frame:{func.lower()}")
    for exc, message in re.findall(r"(?m)^([A-Za-z_][\w.]*?(?:Error|Exception|Failure)):\s*(.+)$", text):
        normalized = re.sub(r"\s+", " ", message.strip().lower())[:120]
        signatures.add(f"error:{exc.lower()}:{normalized}")
        signatures.add(f"error-type:{exc.lower()}")
    return signatures


def _extract_error_signatures(text: str) -> set[str]:
    """Extract non-stack error messages commonly found in test/CI output."""
    if not text:
        return set()
    signatures = _extract_stack_signatures(text)
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.search(r"\b(assertionerror|failed|error|exception|timeout)\b", line, re.I):
            normalized = re.sub(r"\s+", " ", line.lower())[:160]
            signatures.add(f"line:{normalized}")
    return signatures


def _signals_for(memory: dict) -> set[str]:
    text = f"{memory.get('summary', '')}\n{memory.get('raw_text', '')}"
    return (
        _extract_test_identifiers(text)
        | _extract_stack_signatures(text)
        | _extract_error_signatures(text)
    )


def _looks_like_test_failure(memory: dict) -> bool:
    text = f"{memory.get('summary', '')}\n{memory.get('raw_text', '')}".lower()
    return bool(
        _extract_test_identifiers(text)
        or "pytest" in text
        or "failed " in text
        or " assertionerror" in text
    )


def run_edge_inference(db_path: str = "./memory_db") -> dict:
    """Scan recent memories and auto-infer edges between related memories.

    Heuristics:
    - If a git_commit summary shares 2+ keywords with a failure_note summary,
      add a "fixed_by" edge from the failure_note to the commit.
    - If an agent_solution shares 3+ keywords with a failure_note,
      add a "references" edge from the failure_note to the solution.

    Returns:
        {"edges_added": N, "pairs_scanned": M}
    """
    from core.memory_store import MemoryStore
    from core.edge_store import EdgeStore

    store = MemoryStore(db_path)
    edges = EdgeStore(db_path)

    all_memories = store.get_all()

    failure_notes = [
        m for m in all_memories
        if m.get("type") == "failure_note" and m.get("status", "active") == "active"
    ]
    commits = [
        m for m in all_memories
        if m.get("type") == "git_commit" and m.get("status", "active") == "active"
    ]
    solutions = [
        m for m in all_memories
        if m.get("type") in ("agent_solution", "architectural_decision", "debugging_insight")
        and m.get("status", "active") == "active"
    ]

    edges_added = 0
    pairs_scanned = 0

    failure_signals = {fn["id"]: _signals_for(fn) for fn in failure_notes}

    # Similar errors across repos: link failure notes that share a concrete
    # stack frame, exception signature, or test identifier. This makes the graph
    # useful even before a fix commit exists.
    for i, left in enumerate(failure_notes):
        for right in failure_notes[i + 1:]:
            if left.get("repo") == right.get("repo"):
                continue
            pairs_scanned += 1
            shared_signals = failure_signals[left["id"]] & failure_signals[right["id"]]
            if shared_signals:
                added = edges.add_edge(
                    from_id=left["id"],
                    to_id=right["id"],
                    edge_type="related_to",
                    confidence=min(0.9, 0.6 + len(shared_signals) * 0.1),
                    source="auto",
                )
                if added:
                    edges_added += 1
                    logger.info(
                        "Auto-linked similar failures %s → %s via 'related_to' "
                        "(signals: %s)",
                        left["id"][:8], right["id"][:8], shared_signals,
                    )

    for fn in failure_notes:
        fn_keywords = _extract_keywords(f"{fn.get('summary', '')} {fn.get('raw_text', '')}")
        fn_signals = failure_signals[fn["id"]]
        is_test_failure = _looks_like_test_failure(fn)

        for commit in commits:
            pairs_scanned += 1
            commit_text = f"{commit.get('summary', '')} {commit.get('raw_text', '')}"
            commit_keywords = _extract_keywords(commit_text)
            commit_signals = _signals_for(commit)
            overlap = fn_keywords & commit_keywords
            shared_signals = fn_signals & commit_signals
            should_link = len(overlap) >= 2 or bool(shared_signals)
            if is_test_failure and (_extract_test_identifiers(commit_text) & _extract_test_identifiers(f"{fn.get('summary', '')} {fn.get('raw_text', '')}")):
                should_link = True
            if should_link:
                confidence = 0.5 + len(overlap) * 0.1 + len(shared_signals) * 0.15
                added = edges.add_edge(
                    from_id=fn["id"],
                    to_id=commit["id"],
                    edge_type="fixed_by",
                    confidence=min(0.95, confidence),
                    source="auto",
                )
                if added:
                    edges_added += 1
                    logger.info(
                        "Auto-linked failure_note %s → commit %s via 'fixed_by' "
                        "(overlap: %s, signals: %s)",
                        fn["id"][:8], commit["id"][:8], overlap, shared_signals,
                    )

        for sol in solutions:
            pairs_scanned += 1
            sol_keywords = _extract_keywords(f"{sol.get('summary', '')} {sol.get('raw_text', '')}")
            sol_signals = _signals_for(sol)
            overlap = fn_keywords & sol_keywords
            shared_signals = fn_signals & sol_signals
            if len(overlap) >= 3 or shared_signals:
                confidence = 0.4 + len(overlap) * 0.1 + len(shared_signals) * 0.15
                added = edges.add_edge(
                    from_id=fn["id"],
                    to_id=sol["id"],
                    edge_type="references",
                    confidence=min(0.9, confidence),
                    source="auto",
                )
                if added:
                    edges_added += 1

    logger.info(
        "Edge inference complete: %d edges added, %d pairs scanned",
        edges_added, pairs_scanned,
    )
    return {"edges_added": edges_added, "pairs_scanned": pairs_scanned}


if __name__ == "__main__":
    import json
    result = run_edge_inference()
    print(json.dumps(result, indent=2))
