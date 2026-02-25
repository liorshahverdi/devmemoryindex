"""Quick script to test natural language queries against sample memories."""

import tempfile
import lancedb
from datetime import datetime
from core.schema import Memory
from core.embeddings import embed
from core.memory_store import save_memory, search_memory, _schema

# Use a temp DB so we don't pollute the real one
db = lancedb.connect(tempfile.mkdtemp())
collection = db.create_table("memories", schema=_schema)

# --- Sample memories ---
memories = [
    Memory(
        id="1", type="git_commit",
        summary="Fixed Redis timeout in billing API",
        raw_text="Increased Redis connection timeout from 5s to 30s in billing service to prevent dropped requests under load.",
        source="billing-api/redis_client.py", repo="billing-api",
        timestamp=datetime.now(), tags=["bugfix", "redis", "timeout"], importance=0.9,
    ),
    Memory(
        id="2", type="terminal_command",
        summary="Run database migration",
        raw_text="python manage.py migrate --database=default",
        source="terminal", repo="backend",
        timestamp=datetime.now(), tags=["migration", "django"], importance=0.5,
    ),
    Memory(
        id="3", type="agent_solution",
        summary="Retry logic for flaky HTTP calls",
        raw_text="Wrap external API calls with tenacity retry decorator using exponential backoff, max 3 attempts, on ConnectionError and Timeout.",
        source="copilot-agent", repo="payments-service",
        timestamp=datetime.now(), tags=["retry", "http", "resilience"], importance=0.85,
    ),
    Memory(
        id="4", type="copilot_chat",
        summary="How to mock Redis in pytest",
        raw_text="Use fakeredis library to create an in-memory Redis instance for unit tests. Install with pip install fakeredis and pass it as the connection to your Redis client.",
        source="copilot-chat", repo=None,
        timestamp=datetime.now(), tags=["testing", "redis", "mock"], importance=0.7,
    ),
    Memory(
        id="5", type="file_content",
        summary="Docker Compose setup for local Postgres",
        raw_text="services:\n  db:\n    image: postgres:16\n    ports:\n      - 5432:5432\n    environment:\n      POSTGRES_PASSWORD: dev\n      POSTGRES_DB: myapp",
        source="docker-compose.yml", repo="backend",
        timestamp=datetime.now(), tags=["docker", "postgres", "local-dev"], importance=0.6,
    ),
    Memory(
        id="6", type="git_commit",
        summary="Add JWT authentication middleware",
        raw_text="Implemented JWT token validation middleware for FastAPI. Tokens are verified using RS256 algorithm with public key from auth service.",
        source="auth/middleware.py", repo="api-gateway",
        timestamp=datetime.now(), tags=["auth", "jwt", "fastapi"], importance=0.95,
    ),
    Memory(
        id="7", type="git_commit",
        summary="How to set up Django Channels with WebSockets",
        raw_text="Implemented Django Channels with WebSockets for real-time communication. Configured routing, consumers, and authentication.",
        source="src/settings.py", repo="django-app",
        timestamp=datetime.now(), tags=["django", "channels", "websockets"], importance=0.95,
    )
]

# Embed and save all memories
print(f"Indexing {len(memories)} memories...")
for mem in memories:
    vector = embed(mem.raw_text)
    save_memory(mem, vector, collection=collection)
print("Done.\n")

# --- Queries to test ---
queries = [
    "redis connection issue",
    "how to run DB migrations",
    "retry failed API requests",
    "testing with fake redis",
    "setting up postgres locally",
    "authentication and tokens",
    "django websockets bootstrap"
]

for query in queries:
    print(f"Q: {query}")
    print("-" * 50)
    results = search_memory(embed(query), n_results=1, collection=collection)
    for i, r in enumerate(results, 1):
        print(f"  {i}. [{r['type']}] {r['summary']}  (importance={r['importance']:.1f})")
    print()
