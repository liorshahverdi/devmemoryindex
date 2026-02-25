"""Seed the memory store with test memories for development/testing."""

import uuid
from datetime import datetime
from core.schema import Memory
from core.memory_store import MemoryStore
from core.embeddings import embed

TEST_MEMORIES = [
    Memory(
        id=str(uuid.uuid4()),
        type="agent_solution",
        summary="Used Redis pub/sub for real-time notification service between microservices",
        raw_text="Implemented a Redis pub/sub pattern to handle real-time notifications. "
                 "The publisher service pushes events to a 'notifications' channel, and "
                 "subscriber services listen and forward to WebSocket clients. Used redis-py "
                 "with connection pooling. Key config: max_connections=20, decode_responses=True.",
        source="copilot-chat",
        repo="notification-service",
        timestamp=datetime(2026, 2, 10, 14, 30),
        tags=["redis", "pubsub", "microservices", "realtime"],
        importance=0.8,
    ),
    Memory(
        id=str(uuid.uuid4()),
        type="git_commit",
        summary="Fixed JWT auth token refresh race condition in middleware",
        raw_text="Commit abc123: Fixed a race condition where concurrent requests could "
                 "trigger multiple token refresh calls. Added a mutex lock around the refresh "
                 "logic and implemented a short TTL cache (5s) for the refreshed token. "
                 "Affected files: middleware/auth.py, utils/token_cache.py.",
        source="git",
        repo="backend-api",
        timestamp=datetime(2026, 1, 22, 9, 15),
        tags=["auth", "jwt", "race-condition", "middleware"],
        importance=0.9,
    ),
    Memory(
        id=str(uuid.uuid4()),
        type="terminal_command",
        summary="Debugged slow Postgres query with EXPLAIN ANALYZE",
        raw_text="Ran EXPLAIN ANALYZE on the users_search query and found a sequential scan "
                 "on the emails table (2.3s). Added a GIN trigram index: "
                 "CREATE INDEX idx_email_trgm ON users USING gin (email gin_trgm_ops); "
                 "Query time dropped to 12ms.",
        source="terminal",
        repo="backend-api",
        timestamp=datetime(2026, 2, 5, 16, 45),
        tags=["postgres", "performance", "indexing", "sql"],
        importance=0.7,
    ),
    Memory(
        id=str(uuid.uuid4()),
        type="copilot_chat",
        summary="How to structure a Python monorepo with shared packages",
        raw_text="Discussion about Python monorepo layout using a src/ layout with namespace "
                 "packages. Recommended structure: root pyproject.toml with hatch workspaces, "
                 "each sub-package has its own pyproject.toml. Shared code goes in packages/common. "
                 "Use relative path dependencies for local development.",
        source="copilot-chat",
        repo=None,
        timestamp=datetime(2026, 2, 18, 11, 0),
        tags=["python", "monorepo", "packaging", "project-structure"],
        importance=0.6,
    ),
    Memory(
        id=str(uuid.uuid4()),
        type="agent_solution",
        summary="Set up Docker multi-stage build to reduce image size from 1.2GB to 180MB",
        raw_text="Switched from python:3.12 to a multi-stage Docker build. Stage 1 uses "
                 "python:3.12 to install deps and build wheels. Stage 2 copies wheels into "
                 "python:3.12-slim and installs with --no-deps. Also added .dockerignore to "
                 "exclude tests/, docs/, and .git/. Final image: 180MB vs 1.2GB.",
        source="copilot-chat",
        repo="ml-pipeline",
        timestamp=datetime(2026, 2, 1, 10, 20),
        tags=["docker", "optimization", "python", "devops"],
        importance=0.7,
    ),
    Memory(
        id=str(uuid.uuid4()),
        type="file_content",
        summary="FastAPI error handling middleware with structured JSON responses",
        raw_text="Custom exception handler middleware for FastAPI:\n"
                 "- Catches ValidationError and returns 422 with field-level errors\n"
                 "- Catches HTTPException and wraps in {error: {code, message, details}}\n"
                 "- Catches unhandled exceptions, logs traceback, returns 500\n"
                 "- Adds request_id header for tracing\n"
                 "File: middleware/error_handler.py",
        source="backend-api/middleware/error_handler.py",
        repo="backend-api",
        timestamp=datetime(2026, 2, 12, 8, 0),
        tags=["fastapi", "error-handling", "middleware", "api"],
        importance=0.8,
    ),
    Memory(
        id=str(uuid.uuid4()),
        type="agent_solution",
        summary="Implemented retry logic with exponential backoff for flaky API calls",
        raw_text="Used tenacity library for retry logic on external API calls. Config: "
                 "retry=retry_if_exception_type((ConnectionError, Timeout)), "
                 "wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(5). "
                 "Also added circuit breaker pattern using pybreaker for the payment gateway.",
        source="copilot-chat",
        repo="backend-api",
        timestamp=datetime(2026, 1, 28, 13, 30),
        tags=["retry", "resilience", "tenacity", "circuit-breaker"],
        importance=0.8,
    ),
]


def seed():
    store = MemoryStore()
    existing = store.count()
    print(f"Current memory count: {existing}")

    for mem in TEST_MEMORIES:
        text_to_embed = f"{mem.summary} {mem.raw_text}"
        vector = embed(text_to_embed)
        store.add(mem, vector)
        print(f"  + [{mem.type}] {mem.summary[:60]}...")

    print(f"\nInserted {len(TEST_MEMORIES)} test memories. Total: {store.count()}")


if __name__ == "__main__":
    seed()
