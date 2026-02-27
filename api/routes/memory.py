import hashlib
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from core.store_provider import get_store
from core.schema import Memory
from core.embeddings import embed

router = APIRouter()


class MemoryInput(BaseModel):
    summary: str
    raw_text: str | None = None
    memory_type: str = "agent_solution"
    repo: str | None = None
    importance: float = 0.9
    tags: list[str] = []


@router.post("/remember")
def remember(input: MemoryInput):
    """Manually store a memory via HTTP."""
    store = get_store()

    raw = input.raw_text or input.summary
    mem_id = hashlib.sha256(raw[:500].encode()).hexdigest()

    memory = Memory(
        id=mem_id,
        type=input.memory_type,
        summary=input.summary[:200],
        raw_text=raw,
        source="api",
        repo=input.repo,
        timestamp=datetime.utcnow(),
        tags=input.tags,
        importance=input.importance,
    )

    vector = embed(memory.summary)
    added = store.add(memory, vector)  # handles dedup + cache invalidation internally

    return {"status": "ok" if added else "duplicate", "id": mem_id}
