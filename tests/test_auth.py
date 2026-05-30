"""Tests for API Key authentication middleware."""

import os
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from src.mcp_server.auth import APIKeyMiddleware, get_api_key


async def echo(request):
    return JSONResponse({"ok": True})


async def health(request):
    return JSONResponse({"status": "ok"})


@pytest.fixture
def client():
    app = Starlette(routes=[Route("/mcp", echo, methods=["POST"]), Route("/health", health, methods=["GET"])])
    app.add_middleware(APIKeyMiddleware, api_key="test-key-123")
    return TestClient(app)


def test_unauthorized_no_key(client):
    resp = client.post("/mcp", json={})
    assert resp.status_code == 401
    assert "Unauthorized" in resp.json()["error"]["message"]


def test_unauthorized_wrong_key(client):
    resp = client.post("/mcp", json={}, headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_authorized_correct_key(client):
    resp = client.post("/mcp", json={}, headers={"X-API-Key": "test-key-123"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_health_no_key_required(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_get_api_key_present():
    with patch.dict(os.environ, {"MCP_API_KEY": "my-key"}):
        assert get_api_key() == "my-key"


def test_get_api_key_missing():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RuntimeError, match="MCP_API_KEY"):
            get_api_key()
