from fastapi import APIRouter, Query
from core.store_provider import get_store
from core.embeddings import embed
from core.context_engine import ContextEngine

router = APIRouter()


@router.get("/context")
def get_context(
    q: str = Query(..., description="Context query"),
    repo: str | None = Query(None, description="Filter by repo name"),
    tokens: int = Query(4000, description="Max token budget"),
    format: str = Query("raw", description="Output format: raw | markdown | claude"),
    intent: str | None = Query(None, description="Intent override: debug | recall | architecture | implementation"),
):
    store = get_store()
    engine = ContextEngine(store)
    vector = embed(q)

    result = engine.build(
        query=q,
        vector=vector,
        repo=repo,
        max_tokens=tokens,
        format=format,
        intent=intent,
    )

    return {
        "query": q,
        "intent": result.get("intent", "general"),
        "cached": result.get("cached", False),
        "context": result["context_text"],
        "token_estimate": result["token_estimate"],
        "memory_count": result["memory_count"],
    }
