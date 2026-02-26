from datetime import datetime, timedelta
from core.store_provider import get_store

PRUNE_IMPORTANCE_FLOOR = 0.05   # Memories decayed below this → pruneable
PRUNE_MAX_AGE_DAYS     = 90     # Memories older than this AND weak → pruneable
PRUNE_OLD_IMPORTANCE   = 0.15   # Importance threshold for the age-based rule


def prune_memories(
    importance_floor: float = PRUNE_IMPORTANCE_FLOOR,
    max_age_days: int = PRUNE_MAX_AGE_DAYS,
    dry_run: bool = False,
) -> int:
    """Delete underutilized memories. Respects pinned flag. Returns count deleted.

    Two pruning criteria (either qualifies):
    1. importance < importance_floor  (decayed past point of usefulness, regardless of age)
    2. older than max_age_days AND importance < PRUNE_OLD_IMPORTANCE  (old and weak)

    Memories with any recent retrieval will have boosted importance and survive.
    Pinned memories are always skipped.
    """
    store = get_store()
    cutoff = datetime.utcnow() - timedelta(days=max_age_days)

    try:
        all_records = store.collection.to_arrow().to_pylist()
    except Exception:
        return 0

    to_delete = []
    for r in all_records:
        if r.get("pinned", False):
            continue
        importance = r.get("importance", 0.5)
        ts = r.get("timestamp")

        below_floor = importance < importance_floor
        old_and_weak = (
            ts is not None
            and ts < cutoff
            and importance < PRUNE_OLD_IMPORTANCE
        )

        if below_floor or old_and_weak:
            to_delete.append(r["id"])

    if not dry_run:
        for mem_id in to_delete:
            store.delete(mem_id)

    return len(to_delete)
