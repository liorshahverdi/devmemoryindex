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

    for fn in failure_notes:
        fn_keywords = _extract_keywords(f"{fn.get('summary', '')} {fn.get('raw_text', '')}")

        for commit in commits:
            pairs_scanned += 1
            commit_keywords = _extract_keywords(f"{commit.get('summary', '')} {commit.get('raw_text', '')}")
            overlap = fn_keywords & commit_keywords
            if len(overlap) >= 2:
                added = edges.add_edge(
                    from_id=fn["id"],
                    to_id=commit["id"],
                    edge_type="fixed_by",
                    confidence=min(0.95, 0.5 + len(overlap) * 0.1),
                    source="auto",
                )
                if added:
                    edges_added += 1
                    logger.info(
                        "Auto-linked failure_note %s → commit %s via 'fixed_by' "
                        "(overlap: %s)",
                        fn["id"][:8], commit["id"][:8], overlap,
                    )

        for sol in solutions:
            pairs_scanned += 1
            sol_keywords = _extract_keywords(f"{sol.get('summary', '')} {sol.get('raw_text', '')}")
            overlap = fn_keywords & sol_keywords
            if len(overlap) >= 3:
                added = edges.add_edge(
                    from_id=fn["id"],
                    to_id=sol["id"],
                    edge_type="references",
                    confidence=min(0.9, 0.4 + len(overlap) * 0.1),
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
