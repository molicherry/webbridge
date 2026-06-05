import secrets
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .call_logger import get_api_key_by_value, request_key_alias, request_source


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header against api_keys table."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.method == "GET" and request.url.path == "/health":
            return await call_next(request)

        if request.url.path.startswith("/admin"):
            return await call_next(request)

        key = request.headers.get("X-API-Key", "")
        if key:
            key_info = get_api_key_by_value(key)
            if key_info:
                token_alias = request_key_alias.set(key_info["alias"])
                token_source = request_source.set(key[:8])
                try:
                    return await call_next(request)
                finally:
                    request_key_alias.reset(token_alias)
                    request_source.reset(token_source)

        return JSONResponse(
            {"jsonrpc": "2.0", "error": {"code": -32001, "message": "Unauthorized: missing or invalid X-API-Key header"}, "id": None},
            status_code=401,
        )
