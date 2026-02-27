from fastapi import APIRouter, Query
from core.store_provider import get_store
from core.embeddings import embed

router = APIRouter()


@router.get("/search")
def search_memories(
    q: str = Query(..., description="Search query"),
    k: int = Query(5, description="Number of results"),
    memory_type: str | None = Query(None, alias="type", description="Filter by memory type"),
    repo: str | None = Query(None, description="Filter by repo name"),
):
    store = get_store()
    vector = embed(q)
    results = store.hybrid_search(q, vector, k=k, type_filter=memory_type, repo_filter=repo)

    return {
        "query": q,
        "count": len(results),
        "results": [
            {
                "id": r.get("id"),
                "type": r.get("type"),
                "summary": r.get("summary"),
                "repo": r.get("repo"),
                "importance": r.get("importance"),
            }
            for r in results
        ],
    }
