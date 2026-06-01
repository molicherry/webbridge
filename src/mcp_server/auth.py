import os
import secrets
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header against configured API key."""

    def __init__(self, app: Any, api_key: str) -> None:
        super().__init__(app)
        self.api_key = api_key

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.method == "GET" and request.url.path == "/health":
            return await call_next(request)

        if request.url.path.startswith("/admin"):
            return await call_next(request)

        key = request.headers.get("X-API-Key", "")
        if not secrets.compare_digest(key, self.api_key):
            return JSONResponse(
                {"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized: missing or invalid X-API-Key header"}, "id": None},
                status_code=401,
            )
        return await call_next(request)


def get_api_key() -> str:
    key = os.environ.get("MCP_API_KEY", "")
    if not key:
        raise RuntimeError("MCP_API_KEY environment variable is required but not set")
    return key
