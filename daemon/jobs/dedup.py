"""
Memory Deduplication Job — daemon/jobs/dedup.py

Finds memories where summary[:100].lower() matches another entry.
Keeps the higher-importance version, deletes the lower.

Runs weekly via daemon/scheduler.py. Important after high-volume connectors
(Claude, Terminal, Markdown) accumulate duplicates over many ingest cycles.
"""

from core.store_provider import get_store


def dedup_memories(dry_run: bool = False) -> int:
    """
    Remove duplicate memories by summary prefix.

    Returns count of deleted memories.
    """
    store = get_store()
    all_records = store.collection.to_arrow().to_pylist()

    # Group by normalised summary prefix
    groups: dict[str, list[dict]] = {}
    for r in all_records:
        key = r["summary"][:100].lower().strip()
        groups.setdefault(key, []).append(r)

    deleted = 0
    for key, dupes in groups.items():
        if len(dupes) < 2:
            continue
        # Keep the one with the highest importance; break ties by most recent
        dupes.sort(key=lambda r: (r.get("importance", 0.5), r.get("timestamp", 0)), reverse=True)
        to_delete = dupes[1:]  # everything after the winner
        for r in to_delete:
            if not dry_run:
                store.delete(r["id"])
            deleted += 1

    return deleted
