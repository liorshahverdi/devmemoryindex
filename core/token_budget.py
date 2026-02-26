METADATA_OVERHEAD = 20  # tokens for type/repo/importance labels per memory

def estimate_tokens(text: str) -> int:
    """Rough token estimate (~1 token per whitespace-delimited word)."""
    return len(text.split())

def pack_within_budget(
    memories: list[dict],
    max_tokens: int = 4000,
    max_items: int = 10,
    text_key: str = "summary",
) -> tuple[list[dict], int]:
    """Select memories that fit within a token budget.

    Returns (selected_memories, total_token_count).
    """
    selected = []
    token_count = 0
    for mem in memories:
        est = estimate_tokens(mem.get(text_key, "")) + METADATA_OVERHEAD
        if token_count + est > max_tokens:
            break
        selected.append(mem)
        token_count += est
        if len(selected) >= max_items:
            break
    return selected, token_count