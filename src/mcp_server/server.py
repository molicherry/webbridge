"""Kimi WebBridge MCP Server — main application."""

import logging
import os
import threading
import time as _time

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("kimi-webbridge-mcp")

from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from .auth import APIKeyMiddleware
from .call_logger import init_db, cleanup_old_records, request_source, request_client_ip, request_user_agent, bootstrap_default_key
from .config import ADMIN_ENABLED
from .tools import TOOL_REGISTRY

SERVER_NAME = "kimi-webbridge-mcp"
SERVER_VERSION = "1.0.0"

mcp = FastMCP(
    name=SERVER_NAME,
    version=SERVER_VERSION,
)

for handler, description in TOOL_REGISTRY:
    mcp.tool(name=handler.__name__, description=description)(handler)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Capture request metadata into ContextVars for call logging."""

    async def dispatch(self, request: Request, call_next) -> None:
        key = request.headers.get("X-API-Key", "")
        prefix = key[:8] if key else "unknown"
        token_source = request_source.set(prefix)
        token_ip = request_client_ip.set(request.client.host if request.client else "")
        token_ua = request_user_agent.set(request.headers.get("User-Agent", ""))
        try:
            response = await call_next(request)
            return response
        finally:
            request_source.reset(token_source)
            request_client_ip.reset(token_ip)
            request_user_agent.reset(token_ua)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"status": "ok", "server": SERVER_NAME, "version": SERVER_VERSION})


@mcp.custom_route("/admin", methods=["GET", "POST"])
async def admin_redirect(request):
    """Redirect /admin to /admin/ to avoid Cloudflare HTTP redirect."""
    return RedirectResponse(url="/admin/", status_code=307)


def main():
    init_db()
    bootstrap_default_key()
    logger.info("Database initialized, default key bootstrapped")

    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))

    app = mcp.http_app(stateless_http=True, json_response=True, path="/mcp")
    app.add_middleware(APIKeyMiddleware)
    app.add_middleware(RequestContextMiddleware)

    if ADMIN_ENABLED:
        from .admin.auth import AdminAuthMiddleware
        from .admin.routes import routes as admin_router

        app.add_middleware(AdminAuthMiddleware)
        app.mount("/admin", admin_router)
        logger.info("Admin panel enabled at /admin")

        def _cleanup_loop():
            while True:
                _time.sleep(3600)
                cleanup_old_records()

        cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True)
        cleanup_thread.start()

    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
