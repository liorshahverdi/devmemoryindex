"""
Auth tests — verify API key enforcement behaviour.

Uses FastAPI TestClient with the root conftest `store` fixture.
Patches core.config.get_api_key() to control auth state without touching
the real config file.
"""

import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from api.server import app

client = TestClient(app, raise_server_exceptions=True)

_SEARCH_URL = "/memory/search?q=test"
_VALID_KEY = "a3f9c12dabcdef" * 4  # arbitrary test key


class TestOpenAccess:
    """When no key is configured, all requests must pass through."""

    def test_no_key_allows_request(self, store):
        with patch("core.config.get_api_key", return_value=None):
            resp = client.get(_SEARCH_URL)
        assert resp.status_code == 200

    def test_no_key_allows_post(self, store):
        with patch("core.config.get_api_key", return_value=None):
            resp = client.post("/memory/remember", json={"summary": "auth test"})
        assert resp.status_code == 200


class TestKeyEnforcement:
    """When a key is configured, requests without/wrong key must get 401."""

    def test_missing_auth_header_returns_401(self, store):
        with patch("core.config.get_api_key", return_value=_VALID_KEY):
            resp = client.get(_SEARCH_URL)
        assert resp.status_code == 401

    def test_wrong_key_returns_401(self, store):
        with patch("core.config.get_api_key", return_value=_VALID_KEY):
            resp = client.get(_SEARCH_URL, headers={"Authorization": "Bearer wrongkey"})
        assert resp.status_code == 401

    def test_correct_key_returns_200(self, store):
        with patch("core.config.get_api_key", return_value=_VALID_KEY):
            resp = client.get(_SEARCH_URL, headers={"Authorization": f"Bearer {_VALID_KEY}"})
        assert resp.status_code == 200

    def test_401_includes_www_authenticate_header(self, store):
        with patch("core.config.get_api_key", return_value=_VALID_KEY):
            resp = client.get(_SEARCH_URL)
        assert resp.headers.get("www-authenticate") == "Bearer"

    def test_401_detail_message(self, store):
        with patch("core.config.get_api_key", return_value=_VALID_KEY):
            resp = client.get(_SEARCH_URL)
        assert "Invalid or missing API key" in resp.json()["detail"]

    def test_post_endpoint_also_enforced(self, store):
        with patch("core.config.get_api_key", return_value=_VALID_KEY):
            resp = client.post("/memory/ingest", json={"text": "ci event"})
        assert resp.status_code == 401


class TestNoAuthBypass:
    """DEVMEMORY_NO_AUTH env var must bypass enforcement."""

    def test_no_auth_env_bypasses_key(self, store):
        with patch("core.config.get_api_key", return_value=_VALID_KEY):
            with patch.dict(os.environ, {"DEVMEMORY_NO_AUTH": "1"}):
                resp = client.get(_SEARCH_URL)
        assert resp.status_code == 200

    def test_no_auth_env_absent_still_enforces(self, store):
        env = {k: v for k, v in os.environ.items() if k != "DEVMEMORY_NO_AUTH"}
        with patch("core.config.get_api_key", return_value=_VALID_KEY):
            with patch.dict(os.environ, env, clear=True):
                resp = client.get(_SEARCH_URL)
        assert resp.status_code == 401
