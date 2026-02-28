import hashlib
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel
from core.store_provider import get_store
from core.schema import Memory
from core.embeddings import embed, embed_batch

router = APIRouter()

CHUNK_THRESHOLD = 1000   # chars — texts longer than this are split into chunks
CHUNK_TARGET    = 1000   # target chars per chunk
MIN_CHUNK_LEN   = 100    # discard leftover stubs shorter than this
EMBED_MAX       = 2000   # chars fed to the embedding model per chunk


class WebhookPayload(BaseModel):
    text: str
    source: str = "webhook"
    memory_type: str = "agent_solution"
    repo: str | None = None
    importance: float = 0.8
    tags: list[str] = []


@router.post("/ingest")
def webhook_ingest(payload: WebhookPayload):
    """Accept a pushed memory from an external process (CI/CD, deploy scripts, monitors).

    Short payloads (≤ 1000 chars) are stored as a single memory.
    Long payloads (meeting transcripts, logs, etc.) are split into paragraph-aligned
    chunks and stored as separate memories so search can surface specific sections.
    """
    text = payload.text.strip()
    store = get_store()

    if len(text) <= CHUNK_THRESHOLD:
        return _ingest_single(text, payload, store)
    else:
        return _ingest_chunked(text, payload, store)


# ── Single-memory path (short text) ──────────────────────────────────────────


def _ingest_single(text: str, payload: WebhookPayload, store) -> dict:
    mem_id = hashlib.sha256((text + payload.source).encode()).hexdigest()
    memory = Memory(
        id=mem_id,
        type=payload.memory_type,
        summary=text[:200],
        raw_text=text,
        source=payload.source,
        repo=payload.repo,
        timestamp=datetime.utcnow(),
        tags=payload.tags or ["webhook"],
        importance=payload.importance,
    )
    added = store.add(memory, embed(text[:EMBED_MAX]))
    return {"status": "ok" if added else "duplicate", "id": mem_id}


# ── Chunked path (long text) ──────────────────────────────────────────────────


def _ingest_chunked(text: str, payload: WebhookPayload, store) -> dict:
    chunks = _chunk_text(text)
    n = len(chunks)

    vectors = embed_batch([c[:EMBED_MAX] for c in chunks])

    ids: list[str] = []
    added_count = 0
    now = datetime.utcnow()

    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        mem_id = hashlib.sha256(
            f"{payload.source}|{i}|{chunk[:200]}".encode()
        ).hexdigest()
        summary = chunk[:200].replace("\n", " ")
        memory = Memory(
            id=mem_id,
            type=payload.memory_type,
            summary=summary,
            raw_text=chunk,
            source=payload.source,
            repo=payload.repo,
            timestamp=now,
            tags=payload.tags or ["webhook"],
            importance=payload.importance,
        )
        if store.add(memory, vector):
            added_count += 1
        ids.append(mem_id)

    return {"status": "ok", "count": n, "added": added_count, "ids": ids}


# ── Text chunker ──────────────────────────────────────────────────────────────


def _chunk_text(text: str) -> list[str]:
    """Split text into ~CHUNK_TARGET-char chunks at paragraph boundaries.

    Paragraphs (double-newline separated) are accumulated until the target size
    is reached, then flushed as a chunk. Single paragraphs longer than the target
    are kept whole rather than mid-sentence split.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if current_len + len(para) > CHUNK_TARGET and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if len(c) >= MIN_CHUNK_LEN]
