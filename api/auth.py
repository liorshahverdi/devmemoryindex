"""
FastAPI dependency for optional API key authentication.

Behaviour:
- No key in config          → open access (safe for localhost default)
- DEVMEMORY_NO_AUTH env var → open access (set by `devmemory serve --no-auth`)
- Key in config             → Authorization: Bearer <key> required on every request
- Wrong/missing key         → 401 Unauthorized
"""

import os

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import core.config as cfg

_bearer = HTTPBearer(auto_error=False)


def verify_api_key(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> None:
    if os.getenv("DEVMEMORY_NO_AUTH"):
        return  # --no-auth flag bypasses enforcement
    expected = cfg.get_api_key()
    if expected is None:
        return  # no key configured — open access
    if credentials is None or credentials.credentials != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
