"""
DevMemoryIndex REST API — Phase 4B

Exposes memory operations over HTTP for external agents (CI/CD, shell scripts,
cross-machine access). Not the primary agent interface — that's the MCP server
(Phase 4A). Use this when you need HTTP rather than stdio.

Endpoints:
  GET  /memory/search   — hybrid search (query, type, repo, k)
  POST /memory/remember — store a memory
  GET  /memory/context  — build AI-ready context block
  POST /memory/ingest   — webhook push from CI/CD / external tools

Run:
  uvicorn api.server:app --host 127.0.0.1 --port 7711 --reload

Or via CLI:
  devmemory serve
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.search import router as search_router
from api.routes.memory import router as memory_router
from api.routes.context import router as context_router
from api.routes.webhook import router as webhook_router

app = FastAPI(
    title="DevMemoryIndex API",
    description="Persistent memory for developers and AI coding agents",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router, prefix="/memory", tags=["search"])
app.include_router(memory_router, prefix="/memory", tags=["memory"])
app.include_router(context_router, prefix="/memory", tags=["context"])
app.include_router(webhook_router, prefix="/memory", tags=["webhook"])


def start_server(host: str = "127.0.0.1", port: int = 7711, reload: bool = False):
    import uvicorn
    uvicorn.run("api.server:app", host=host, port=port, reload=reload)
