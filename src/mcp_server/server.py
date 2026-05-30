"""Kimi WebBridge MCP Server — main application."""

import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("kimi-webbridge-mcp")

from fastmcp import FastMCP

from .auth import APIKeyMiddleware, get_api_key
from .tools import TOOL_REGISTRY

SERVER_NAME = "kimi-webbridge-mcp"
SERVER_VERSION = "1.0.0"

mcp = FastMCP(
    name=SERVER_NAME,
    version=SERVER_VERSION,
)

for handler, description in TOOL_REGISTRY:
    mcp.tool(name=handler.__name__, description=description)(handler)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return {"status": "ok", "server": SERVER_NAME, "version": SERVER_VERSION}


def main():
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))
    api_key = get_api_key()
    app = mcp.http_app(stateless_http=True, json_response=True, path="/mcp")
    app.add_middleware(APIKeyMiddleware, api_key=api_key)

    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
