from core.store_provider import get_store


def decay_importance(factor: float = 0.99) -> int:
    """Reduce importance of non-pinned memories slightly. Run daily.

    Returns count of memories decayed.
    """
    store = get_store()
    try:
        all_records = store.collection.to_arrow().to_pylist()
    except Exception:
        return 0

    count = 0
    for r in all_records:
        if r.get("pinned", False):
            continue
        new_importance = r.get("importance", 0.5) * factor
        try:
            store.collection.update(
                where=f"id = '{r['id']}'",
                values={"importance": new_importance},
            )
            count += 1
        except Exception:
            pass

    return count
