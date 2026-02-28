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

Auth:
  If [api] key is set in config.toml → Authorization: Bearer <key> required.
  If no key configured → open access (localhost-safe default).
  `devmemory serve --no-auth` bypasses enforcement even when a key is set.

Run:
  uvicorn api.server:app --host 127.0.0.1 --port 7711 --reload

Or via CLI:
  devmemory serve
"""

import os

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.auth import verify_api_key
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

_auth_dep = [Depends(verify_api_key)]

# Order matters: literal routes must be registered before /{memory_id} wildcard
app.include_router(search_router, prefix="/memory", tags=["search"], dependencies=_auth_dep)
app.include_router(context_router, prefix="/memory", tags=["context"], dependencies=_auth_dep)
app.include_router(webhook_router, prefix="/memory", tags=["webhook"], dependencies=_auth_dep)
app.include_router(memory_router, prefix="/memory", tags=["memory"], dependencies=_auth_dep)  # /{memory_id} last


def start_server(
    host: str = "127.0.0.1",
    port: int = 7711,
    reload: bool = False,
    auth_enabled: bool = True,
):
    import uvicorn

    if not auth_enabled:
        os.environ["DEVMEMORY_NO_AUTH"] = "1"
    elif "DEVMEMORY_NO_AUTH" in os.environ:
        del os.environ["DEVMEMORY_NO_AUTH"]

    uvicorn.run("api.server:app", host=host, port=port, reload=reload)
