import hashlib
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from core.store_provider import get_store
from core.schema import Memory
from core.embeddings import embed

router = APIRouter()


class WebhookPayload(BaseModel):
    text: str
    source: str = "webhook"
    memory_type: str = "agent_solution"
    repo: str | None = None
    importance: float = 0.8
    tags: list[str] = []


@router.post("/ingest")
def webhook_ingest(payload: WebhookPayload):
    """Accept a pushed memory from an external process (CI/CD, deploy scripts, monitors)."""
    store = get_store()
    mem_id = hashlib.sha256((payload.text + payload.source).encode()).hexdigest()

    memory = Memory(
        id=mem_id,
        type=payload.memory_type,
        summary=payload.text[:200],
        raw_text=payload.text,
        source=payload.source,
        repo=payload.repo,
        timestamp=datetime.utcnow(),
        tags=payload.tags or ["webhook"],
        importance=payload.importance,
    )
    added = store.add(memory, embed(memory.summary))
    return {"status": "ok" if added else "duplicate", "id": mem_id}
