# Research: MCP Server Implementation Patterns

- **Query**: MCP Server SDK comparison, transport modes, authentication, tool mapping, session isolation, Docker deployment patterns
- **Scope**: mixed (external: MCP spec, SDK docs, GitHub; internal: project PRD context)
- **Date**: 2026-05-29

## 1. MCP Server SDKs: Python vs Node.js/TypeScript

### 1.1 Python: Official MCP SDK (`mcp` package on PyPI)

The official Python SDK (`pip install "mcp[cli]"`) provides a full implementation of the MCP specification, including:

- **`MCPServer`** (formerly `FastMCP`): High-level server class with decorator-based tool registration
- **Transports**: stdio, SSE, and Streamable HTTP
- **Auth**: OAuth 2.1 Resource Server support via `TokenVerifier` protocol
- **ASGI integration**: Mountable as a Starlette app via `mcp.http_app()`

Key API pattern (from official SDK README):

```python
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("StatelessServer")

@mcp.tool()
def greet(name: str = "World") -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run(transport="streamable-http", stateless_http=True, json_response=True)
```

**Strengths for REST API wrapping**:
- Type-hint-based automatic schema generation (no manual schema declaration needed for simple tools)
- `json_response=True` mode ideal for wrapping REST APIs that return structured data
- ASGI standard = easy Docker deployment (Uvicorn)
- OAuth 2.1 auth built into the SDK (`mcp.server.auth`)
- `stateless_http=True` mode eliminates session storage needs in multi-instance Docker deployments

**Weaknesses**:
- v2 SDK is pre-alpha on `main` branch; v1.x is stable
- FastMCP was merged into the official SDK, but the standalone FastMCP has diverged

### 1.2 Python: Standalone FastMCP (by PrefectHQ)

The standalone `fastmcp` package (v3+, `pip install fastmcp`) is the independent continuation of the original FastMCP. It has diverged from the official SDK.

```python
from fastmcp import FastMCP

mcp = FastMCP("My Server")

@mcp.tool
def process_data(input: str) -> str:
    """Process data on the server"""
    return f"Processed: {input}"

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
```

**Strengths for REST API wrapping**:
- Richer auth ecosystem: `TokenVerifier` (JWT), `RemoteAuthProvider` (OAuth with DCR), `OAuthProxy` (non-DCR OAuth), `OAuthProvider` (full auth server), `MultiAuth`
- Bearer token auth support out of the box
- FastAPI integration: `mcp.mount_to_fastapi(app)`
- Health check routes via `@mcp.custom_route`
- CORS middleware support
- Claims 70% of MCP server market share across all languages
- `BearerAuth` helper for simple API key auth

**Weaknesses**:
- Not the official SDK -- divergence from `mcp` package API
- Documentation is comprehensive but separate from official MCP docs
- May lag behind official MCP spec updates

### 1.3 Node.js/TypeScript: Official `@modelcontextprotocol/server`

The TS SDK (`npm install @modelcontextprotocol/server`) provides:

- **`McpServer`**: High-level server with explicit `registerTool()`, `registerResource()`, `registerPrompt()`
- **Transports**: `StdioServerTransport`, `NodeStreamableHTTPServerTransport`
- **Auth**: OAuth 2.1 support, `requireBearerAuth` middleware, `demoTokenVerifier`
- **Middleware packages**: Express (`@modelcontextprotocol/express`), Hono (`@modelcontextprotocol/hono`), Node.js HTTP (`@modelcontextprotocol/node`)

Key API pattern:

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import { NodeStreamableHTTPServerTransport } from '@modelcontextprotocol/node';
import * as z from 'zod/v4';

const server = new McpServer({ name: 'my-server', version: '1.0.0' });

server.registerTool(
    'greet',
    {
        description: 'A simple greeting tool',
        inputSchema: z.object({ name: z.string().describe('Name to greet') })
    },
    async ({ name }) => ({
        content: [{ type: 'text', text: `Hello, ${name}!` }]
    })
);

// Streamable HTTP with Express
import { createMcpExpressApp } from '@modelcontextprotocol/express';
const app = createMcpExpressApp();
const transports: Record<string, NodeStreamableHTTPServerTransport> = {};

app.post('/mcp', async (req: Request, res: Response) => {
    const sessionId = req.headers['mcp-session-id'] as string;
    let transport = sessionId ? transports[sessionId] : null;
    // ... session/transport management ...
    await transport.handleRequest(req, res, req.body);
});
```

**Strengths for REST API wrapping**:
- Fine-grained control over HTTP transport (Express/Hono integration)
- Explicit schema definition via Zod (good for complex, nested schemas that map to REST API parameters)
- Multi-node deployment patterns well-documented (stateless, persistent storage, pub/sub routing)
- `enableJsonResponse: true` option for JSON-only responses (no SSE overhead)
- Rich middleware ecosystem
- Session isolation pattern explicitly documented with `transports` map keyed by `sessionId`

**Weaknesses**:
- v2 SDK is pre-alpha on `main`; v1.x branch is the stable version
- More boilerplate than Python (manual transport/session management vs Python's `mcp.run()`)
- Requires Zod or another schema library (heavier dependency chain)

### 1.4 Recommendation for This Project

**Python (official `mcp` SDK or standalone `fastmcp`) is the stronger choice** for wrapping kimi-webbridge as an MCP server:

1. **kimi-webbridge daemon is already a Python/CLI tool** -- Python MCP server can interact via subprocess or HTTP calls to the daemon
2. **Lower boilerplate** -- `@mcp.tool` decorator + type hints auto-generate MCP schemas, mapping 1:1 to REST API tool wrappers
3. **Streamable HTTP with `stateless_http=True` and `json_response=True`** is a one-line configuration, perfect for Docker deployment
4. **Bearer auth via `X-API-Key` header or JWT** is well-supported in FastMCP's client `headers` parameter
5. **Health check endpoints** built-in via `@mcp.custom_route("/health")`

The standalone FastMCP has a richer auth ecosystem, while the official `mcp` SDK ensures spec compliance. Either is a solid choice.

---

## 2. Transport Modes: SSE vs Streamable HTTP

### 2.1 Overview

Per the MCP specification (2025-06-18):

| Feature | SSE (Legacy) | Streamable HTTP (Current) |
|---------|-------------|---------------------------|
| Spec version | 2024-11-05 | 2025-03-26+ |
| HTTP endpoint | 2 endpoints (POST + GET/SSE) | 1 endpoint (POST + GET) |
| Response modes | SSE streaming only | JSON + optional SSE streaming |
| Session tracking | Implicit via SSE connection | Explicit via `mcp-session-id` header |
| Bidirectional | Yes (SSE duplex) | Yes (GET for server-initiated messages) |
| Browser support | Requires EventSource | Standard HTTP (CORS config needed) |
| Production readiness | Legacy, stable | Recommended for new deployments |
| Stateless mode | Not applicable | `stateless_http=True` / `sessionIdGenerator: undefined` |

### 2.2 Streamable HTTP Details

Streamable HTTP is the **recommended transport for production deployments**. Key characteristics:

**Single endpoint** (`/mcp`):
- **POST**: Client sends JSON-RPC requests. Server responds with either `Content-Type: text/event-stream` (SSE stream) or `Content-Type: application/json` (single JSON object).
- **GET**: Optional. Server can send server-initiated notifications/requests (if SSE is enabled).

**JSON response mode** (`json_response=True` / `enableJsonResponse: true`):
- Returns plain JSON instead of SSE stream
- No persistent connection needed between calls
- Ideal for REST API wrapping where each call is independent
- Cannot use server-initiated notifications (acceptable for a stateless API wrapper)

**Stateless mode** (`stateless_http=True` / `sessionIdGenerator: undefined`):
- No session ID tracking between requests
- Each request is independent
- Perfect for horizontally scaled Docker deployments behind a load balancer
- Eliminates the need for sticky sessions or shared session stores

### 2.3 SSE (Server-Sent Events) Transport

The legacy SSE transport:
- Uses separate `/sse` (GET) and `/messages` (POST) endpoints
- Maintains a persistent SSE connection for server-to-client messages
- Session is tied to the SSE connection lifecycle

### 2.4 Recommendation for This Project

**Streamable HTTP with JSON response mode and stateless operation** is the clear choice:

1. **Docker deployment** -- Single `/mcp` endpoint is simpler to expose and proxy. No sticky session requirements when stateless.
2. **REST API wrapping** -- Each tool call is a request-response cycle, mirroring REST semantics. No need for persistent bidirectional connections.
3. **Horizontal scaling** -- Stateless mode allows multiple container instances behind a load balancer without shared state.
4. **Security** -- Simpler attack surface (single endpoint vs two). Explicit session ID (when stateful) enables auth validation per request.

Configuration:
```python
# Python official SDK
mcp.run(transport="streamable-http", stateless_http=True, json_response=True)

# Python FastMCP
mcp.run(transport="http", host="0.0.0.0", port=8000)
```

---

## 3. Authentication Patterns for MCP Remote Servers

### 3.1 MCP Authorization Specification (2025-06-18)

The MCP spec defines an **OAuth 2.1-based authorization framework**:

- **Authorization is OPTIONAL** for MCP implementations
- **HTTP-based transports SHOULD conform** to the spec when auth is used
- **STDIO transport SHOULD NOT** follow this spec (use environment credentials instead)
- MCP Server acts as an **OAuth 2.1 Resource Server** (RS)
- MCP Client acts as an **OAuth 2.1 Client**
- Uses **RFC 9728** (Protected Resource Metadata) for auth server discovery
- Uses **RFC 8414** (Authorization Server Metadata)
- Supports **Dynamic Client Registration** (RFC 7591)

### 3.2 Common Authentication Patterns in Practice

#### Pattern A: Bearer Token / API Key (Simplest)

Most suitable for service-to-service and non-interactive scenarios. This is the **most common pattern for Docker-deployed MCP servers**.

Server side (FastMCP):
```python
from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import JWTVerifier

auth = JWTVerifier(
    jwks_uri="https://auth.example.com/.well-known/jwks.json",
    issuer="https://auth.example.com",
    audience="kimi-webbridge-mcp"
)
mcp = FastMCP(name="Kimi WebBridge MCP", auth=auth)
```

Client side:
```python
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

transport = StreamableHttpTransport(
    "https://server.example.com/mcp",
    headers={"X-API-Key": "your-secret-key"},
)
async with Client(transport) as client:
    await client.ping()
```

Or with Bearer auth:
```python
transport = StreamableHttpTransport(
    "https://server.example.com/mcp",
    auth="your-jwt-token",  # FastMCP auto-applies "Bearer" prefix
)
```

Simple custom header auth for API Key (no framework auth provider):
```python
# Custom middleware pattern for simple API key check
from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        api_key = request.headers.get("X-API-Key")
        if api_key != API_KEYS.get_valid_key():
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)
```

#### Pattern B: OAuth 2.1 with Dynamic Client Registration (Full Spec)

Used when integrating with identity providers that support DCR (Descope, WorkOS AuthKit). Suitable for multi-tenant SaaS MCP servers.

```python
from fastmcp.server.auth.providers.workos import AuthKitProvider

auth = AuthKitProvider(
    authkit_domain="https://your-project.authkit.app",
    base_url="https://your-server.com"
)
mcp = FastMCP(name="Enterprise Server", auth=auth)
```

#### Pattern C: OAuth Proxy (for providers without DCR)

Used with GitHub, Google, Azure, AWS OAuth where manual app registration is required.

```python
from fastmcp.server.auth.providers.github import GitHubProvider

auth = GitHubProvider(
    client_id="Ov23li...",
    client_secret="abc123...",
    base_url="https://your-server.com"
)
```

#### Pattern D: TokenVerifier (JWT-only, lightweight)

Pure token validation without OAuth metadata endpoints. Best for internal APIs where a JWKS endpoint already exists.

```python
from mcp.server.auth.provider import AccessToken, TokenVerifier

class SimpleTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        # Validate JWT signature, expiry, claims
        claims = validate_jwt(token, expected_audience="kimi-webbridge-mcp")
        if claims:
            return AccessToken(token=token, client_id=claims["sub"], scopes=claims.get("scopes", []))
        return None
```

### 3.3 Common Convention Summary

| Approach | Complexity | Use Case |
|----------|-----------|----------|
| `X-API-Key` header + custom middleware | Low | Internal tools, single-tenant |
| Bearer JWT + `JWTVerifier` | Medium | Internal with existing JWT infrastructure |
| OAuth 2.1 with DCR | High | Multi-tenant, enterprise SSO |
| OAuth Proxy (non-DCR) | High | GitHub/Google/Azure integration |

### 3.4 Recommendation for This Project

**Bearer Token / API Key via custom header** is the right starting point:

1. kimi-webbridge is a single-tenant / internal deployment tool
2. No need for full OAuth 2.1 flow -- a pre-shared API key suffices
3. Simple middleware to check `Authorization: Bearer <token>` or `X-API-Key: <key>` on POST `/mcp`
4. Can be upgraded to JWT verification later if multi-user auth is needed
5. Docker secrets can inject the API key at container startup

---

## 4. Tool Definition Patterns: Mapping REST API to MCP Tools

### 4.1 The Pattern

Each kimi-webbridge REST API endpoint becomes one MCP tool. The pattern is:

```
REST:  POST /api/navigate  { "url": "...", "session": "..." }  ->  { "status": "ok", "tab_id": "..." }
MCP:   tool "navigate"     { "url": "...", "session": "..." }  ->  { content: [{ type: "text", text: "Navigated to ..." }] }
```

### 4.2 Example: Python (Official MCP SDK)

```python
import httpx
from mcp.server.mcpserver import MCPServer

BASE_URL = "http://127.0.0.1:10086"  # kimi-webbridge daemon
client = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

mcp = MCPServer("Kimi WebBridge MCP")

@mcp.tool(description="Navigate to a URL in a browser tab")
async def navigate(url: str, session: str | None = None, wait_until: str = "load") -> str:
    """Navigate the browser to a URL.

    Args:
        url: The URL to navigate to
        session: Session ID (optional, auto-creates if omitted)
        wait_until: When to consider navigation done ("load", "domcontentloaded", "networkidle")
    """
    payload = {"url": url, "waitUntil": wait_until}
    if session:
        payload["session"] = session
    resp = await client.post("/api/navigate", json=payload)
    resp.raise_for_status()
    data = resp.json()
    return f"Navigated to {url}. Tab ID: {data.get('tabId', 'N/A')}, Session: {data.get('session', 'N/A')}"


@mcp.tool(description="Take a screenshot of the current page")
async def screenshot(session: str, full_page: bool = False) -> str:
    """Capture a screenshot of the browser tab.

    Args:
        session: Session ID of the target tab
        full_page: Whether to capture the full scrollable page
    """
    resp = await client.post("/api/screenshot", json={
        "session": session,
        "fullPage": full_page
    })
    resp.raise_for_status()
    data = resp.json()
    return data.get("screenshot", data.get("data", "Screenshot captured"))


@mcp.tool(description="Click on an element on the page")
async def click(session: str, selector: str) -> str:
    """Click an element identified by a CSS selector.

    Args:
        session: Session ID
        selector: CSS selector of the element to click
    """
    resp = await client.post("/api/click", json={
        "session": session,
        "selector": selector
    })
    resp.raise_for_status()
    return f"Clicked element: {selector}"


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        stateless_http=True,
        json_response=True,
        host="0.0.0.0",
        port=8000
    )
```

### 4.3 Example: TypeScript

```typescript
import { McpServer } from '@modelcontextprotocol/server';
import { NodeStreamableHTTPServerTransport } from '@modelcontextprotocol/node';
import { createMcpExpressApp } from '@modelcontextprotocol/express';
import * as z from 'zod/v4';

const DAEMON_URL = process.env.DAEMON_URL || 'http://127.0.0.1:10086';

function getServer(): McpServer {
    const server = new McpServer({
        name: 'kimi-webbridge-mcp',
        version: '1.0.0'
    });

    server.registerTool(
        'navigate',
        {
            description: 'Navigate to a URL in a browser tab',
            inputSchema: z.object({
                url: z.string().describe('The URL to navigate to'),
                session: z.string().optional().describe('Session ID'),
                wait_until: z.enum(['load', 'domcontentloaded', 'networkidle']).default('load')
            })
        },
        async ({ url, session, wait_until }) => {
            const resp = await fetch(`${DAEMON_URL}/api/navigate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, session, waitUntil: wait_until })
            });
            const data = await resp.json();
            return {
                content: [{
                    type: 'text',
                    text: `Navigated to ${url}. Tab: ${data.tabId}, Session: ${data.session}`
                }]
            };
        }
    );

    server.registerTool(
        'screenshot',
        {
            description: 'Take a screenshot of the current page',
            inputSchema: z.object({
                session: z.string().describe('Session ID'),
                full_page: z.boolean().default(false)
            })
        },
        async ({ session, full_page }) => {
            const resp = await fetch(`${DAEMON_URL}/api/screenshot`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session, fullPage: full_page })
            });
            const data = await resp.json();
            return {
                content: [{ type: 'text', text: data.screenshot || data.data || 'Screenshot captured' }]
            };
        }
    );

    return server;
}
```

### 4.4 Key Patterns and Best Practices

1. **1:1 mapping**: Each kimi-webbridge tool (navigate, click, fill, screenshot, snapshot, etc.) becomes exactly one MCP tool
2. **Async HTTP calls**: Use `httpx.AsyncClient` (Python) or `fetch` (TS) for non-blocking REST calls
3. **Return type**: Always return `str` or structured text (JSON stringified) as text content. MCP tools return `{ content: [{ type: "text", text: "..." }] }`
4. **Error mapping**: Map REST API error responses to MCP errors (raise exceptions in handler, SDK converts to JSON-RPC errors)
5. **Connection pooling**: Create a single HTTP client instance (reused across all tool calls) for connection reuse
6. **Timeouts**: Set appropriate timeouts (browser operations can be slow -- 30-60s is reasonable for navigate/screenshot)

---

## 5. Session and Multi-User Isolation

### 5.1 How MCP Sessions Work

In Streamable HTTP transport, session management works via the `mcp-session-id` header:

**Stateful mode** (default):
1. Client sends `initialize` request (no session ID)
2. Server creates session, responds with `mcp-session-id` header
3. Client includes `mcp-session-id` in all subsequent requests
4. Server maps session ID to transport instance (in-memory map)
5. Only one transport instance exists per session

**Stateless mode** (`stateless_http=True`):
1. No session ID is generated
2. Each request is handled independently
3. No state is preserved between calls
4. The server does not require `mcp-session-id` in headers

### 5.2 Session Isolation in Stateful Mode

The typical pattern (from TS SDK reference implementation):

```typescript
// Map to store transports by session ID -- one per connected client
const transports: { [sessionId: string]: NodeStreamableHTTPServerTransport } = {};

app.post('/mcp', async (req: Request, res: Response) => {
    const sessionId = req.headers['mcp-session-id'] as string | undefined;

    if (sessionId && transports[sessionId]) {
        // Existing session -- reuse transport
        await transports[sessionId].handleRequest(req, res, req.body);
    } else if (!sessionId && isInitializeRequest(req.body)) {
        // New session -- create transport, connect server
        const transport = new NodeStreamableHTTPServerTransport({
            sessionIdGenerator: () => randomUUID(),
            onsessioninitialized: (sid) => {
                transports[sid] = transport;
            }
        });
        transport.onclose = () => {
            // Clean up on session close
            if (transport.sessionId) {
                delete transports[transport.sessionId];
            }
        };
        const server = getServer();  // Each session gets its own server instance
        await server.connect(transport);
        await transport.handleRequest(req, res, req.body);
    } else {
        res.status(400).json({ error: 'Bad Request: missing or invalid session' });
    }
});
```

In Python SDK:
```python
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("Kimi WebBridge MCP")

# In stateful mode, the SDK manages session isolation internally
# Each session gets its own request context
mcp.run(transport="streamable-http")  # stateful default
```

### 5.3 Multi-User Isolation Strategies

**Strategy A: Stateless mode (recommended for this project)**

Since kimi-webbridge daemon already handles session isolation internally (each `session` parameter maps to a tab group in the browser), the MCP layer does not need to maintain its own session state:

```python
mcp = MCPServer("Kimi WebBridge MCP")

@mcp.tool()
async def navigate(url: str, session: str) -> str:
    # session parameter comes from the AI IDE client
    # kimi-webbridge daemon handles session isolation internally
    resp = await client.post("/api/navigate", json={"url": url, "session": session})
    return resp.json()
```

- MCP server runs in stateless mode
- kimi-webbridge session IDs are passed through as tool parameters
- No MCP-level session storage needed
- Multiple AI IDE clients can connect simultaneously, each with their own kimi-webbridge sessions

**Strategy B: MCP session maps to kimi-webbridge session**

If you want MCP-level session isolation to automatically manage kimi-webbridge sessions:

```python
from contextvars import ContextVar

current_session: ContextVar[str | None] = ContextVar("current_session", default=None)

mcp = MCPServer("Kimi WebBridge MCP")

@mcp.tool()
async def navigate(url: str) -> str:
    sid = current_session.get()
    if not sid:
        # Create new kimi-webbridge session
        resp = await client.post("/api/new_session")
        sid = resp.json()["session"]
        current_session.set(sid)
    resp = await client.post("/api/navigate", json={"url": url, "session": sid})
    return resp.json()
```

This pattern works in stateful MCP mode but is more complex and less flexible than explicit session parameters.

### 5.4 Multi-Node Deployment Considerations

From the TypeScript SDK's documented patterns:

| Mode | Session state | Horizontal scaling | Complexity |
|------|--------------|-------------------|------------|
| Stateless | None | Load balancer + any node | Low |
| Persistent storage | In DB | Any node via shared DB | Medium |
| Local state + pub/sub routing | In-memory per node | Sticky sessions or message routing | High |

### 5.5 Recommendation

**Stateless mode with explicit `session` parameters on tools** is the best fit:

1. kimi-webbridge daemon already manages browser tab sessions internally
2. MCP server is a thin proxy -- no need to duplicate session management
3. Simplifies Docker deployment (any container can handle any request)
4. AI IDE clients explicitly control which kimi-webbridge session they're using via the `session` parameter

---

## 6. Existing Docker MCP Server Implementations

### 6.1 Official Reference Implementations

**TypeScript SDK examples** (from `@modelcontextprotocol/typescript-sdk`):
- `simpleStreamableHttp.ts` -- Stateful Streamable HTTP server with OAuth (Express + NodeStreamableHTTP)
- `simpleStatelessStreamableHttp.ts` -- Stateless server (no session tracking)
- `jsonResponseStreamableHttp.ts` -- JSON-only responses, no SSE streaming
- `resourceServerOnly.ts` -- Minimal OAuth Resource Server with `requireBearerAuth`
- These examples use the `createMcpExpressApp()` pattern which is Docker-friendly

**Python SDK examples** (from `modelcontextprotocol/python-sdk`):
- `streamable_config.py` -- Streamable HTTP with stateless + JSON response configuration
- `oauth_server.py` -- OAuth 2.1 Resource Server with TokenVerifier

### 6.2 Docker-Relevant Open-Source MCP Servers

From GitHub search results:

| Project | Stars | Description |
|---------|-------|-------------|
| `agent-infra/sandbox` | 4853 | All-in-One Sandbox with Browser, Shell, MCP in Docker |
| `AmoyLab/Unla` | 2127 | MCP Gateway + Docker deployment, zero-code API-to-MCP transformation |
| `alexei-led/k8s-mcp-server` | 210 | Kubernetes MCP server with Docker containerized deployment |
| `alexei-led/cloud-mcp-server` | 182 | AWS CLI MCP server in safe containerized environment |
| `ravindersirohi/McpServer-In-Docker` | 2 | Azure Function + MCP server Docker example |
| `SyedAanif/dockerise-mcp` | 1 | MCP client + server Docker build example |

### 6.3 Common Docker MCP Server Patterns

**Pattern A: Standard Dockerfile** (from TS SDK examples pattern)
```dockerfile
FROM node:22-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY dist/ ./
EXPOSE 3000
CMD ["node", "server.js"]
```

**Pattern B: Multi-stage build** (Python)
```dockerfile
FROM python:3.11-slim AS builder
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.11-slim
COPY --from=builder /app/.venv /app/.venv
COPY . .
EXPOSE 8000
CMD ["uv", "run", "mcp-server"]
```

**Pattern C: docker-compose** (MCP server + daemon)
```yaml
services:
  mcp-server:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DAEMON_URL=http://webbridge:10086
      - API_KEY=${API_KEY}
    depends_on:
      - webbridge

  webbridge:
    image: kimi-webbridge:latest  # custom image with browser + daemon
    ports:
      - "10086:10086"
    volumes:
      - browser_data:/data

volumes:
  browser_data:
```

### 6.4 Key Docker Deployment Considerations

1. **Expose only the MCP endpoint** (port 8000), not the kimi-webbridge daemon (port 10086) -- daemon should only be accessible within the Docker network
2. **Health check**: Use `@mcp.custom_route("/health")` (FastMCP) or a separate Express route (TS) for Docker healthcheck
3. **API key via Docker secrets or env var**: `API_KEY` injected at runtime
4. **Browser in container**: Need chromium + required deps -- expect ~1-2GB image size
5. **Network mode**: Use Docker internal network for MCP-to-daemon communication; only expose MCP port to host

---

## 7. Summary: Architecture Recommendation

Based on all six research areas, the recommended architecture for kimi-webbridge MCP Server is:

```
[Docker Container]
  ├── MCP Server (Python FastMCP or official mcp SDK)
  │   ├── Transport: Streamable HTTP (stateless, JSON response mode)
  │   ├── Auth: X-API-Key header checked via middleware
  │   ├── Port: 8000 (exposed)
  │   └── Tools: 1:1 mapping to kimi-webbridge REST API
  │
  ├── kimi-webbridge daemon
  │   ├── Port: 10086 (internal only)
  │   └── Communicates via localhost HTTP
  │
  └── Chromium Headless + Kimi WebBridge extension
      └── Browser session isolation per daemon session ID
```

Key decisions:
- **Language**: Python (lower boilerplate, existing ecosystem knowledge for REST wrapping)
- **Transport**: Streamable HTTP, stateless, JSON response mode
- **Auth**: `X-API-Key` header with custom middleware
- **Session isolation**: Pass kimi-webbridge session IDs through as tool parameters (stateless MCP)
- **Tool mapping**: 13+ tools mapping 1:1 to kimi-webbridge REST API endpoints
