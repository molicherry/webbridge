"""Admin panel routes — Starlette Router for the web admin interface.

All HTML is inlined. No template engine, no external CSS/JS frameworks.
"""

import asyncio
import html as _html
import json as _json
import logging
import os
from typing import Any

import httpx
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route, Router

from ..call_logger import get_config, get_records, get_stats, set_config, get_api_keys, create_api_key, update_api_key, delete_api_key
from ..config import ADMIN_ENABLED, CDP_URL, EXTERNAL_API_KEY
from ..session_tracker import get_session as _get_tab_session
from .auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    _check_rate_limit,
    create_session_token,
    verify_password,
)

logger = logging.getLogger("kimi-webbridge-mcp.admin.routes")

_CDP_TIMEOUT = 30.0
_cdp_client: httpx.AsyncClient | None = None


def _get_cdp_client() -> httpx.AsyncClient:
    global _cdp_client
    if _cdp_client is None:
        _cdp_client = httpx.AsyncClient(timeout=_CDP_TIMEOUT)
    return _cdp_client


async def _cdp_get(path: str, parse_json: bool = True) -> Any:
    """GET from Chrome CDP with retry on transient failures."""
    last_exc = None
    for attempt in range(2):
        try:
            resp = await _get_cdp_client().get(f"{CDP_URL}{path}")
            resp.raise_for_status()
            return resp.json() if parse_json else resp.text
        except Exception as e:
            last_exc = e
            if attempt == 0:
                logger.warning("CDP request failed (attempt 1/2), retrying: %s", e)
                await asyncio.sleep(1)
            else:
                logger.exception("CDP request failed (attempt 2/2)")
    raise last_exc  # type: ignore[possibly-undefined]


# ── Helpers ──────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    """Extract client IP from request."""
    client = request.client
    if client is not None:
        return client.host
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return "127.0.0.1"


def _mask_key(key: str) -> str:
    """Mask an API key, showing first 4 and last 4 characters."""
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def _query_param(request: Request, name: str, default: str = "") -> str:
    """Get a query parameter with a default."""
    return request.query_params.get(name, default)


def _query_param_int(request: Request, name: str, default: int) -> int:
    """Get an integer query parameter, falling back to default on error."""
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (ValueError, TypeError):
        return default


def _admin_disabled_page() -> HTMLResponse:
    return HTMLResponse(
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>管理面板 - 未启用</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:#f0f2f5; display:flex; align-items:center; justify-content:center; min-height:100vh; }
  .card { background:#fff; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1); padding:40px; width:360px; max-width:90vw; text-align:center; }
  h1 { font-size:20px; color:#1a1a2e; margin-bottom:12px; }
  p { color:#666; font-size:14px; }
</style>
</head>
<body>
  <div class="card">
    <h1>管理面板未启用</h1>
    <p>管理员面板需要设置 ADMIN_PASSWORD 环境变量才能使用。</p>
  </div>
</body>
</html>""",
        status_code=200,
    )


# ── HTML Templates ───────────────────────────────────────────────────────

LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kimi WebBridge 管理面板 - 登录</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:#f0f2f5; display:flex; align-items:center; justify-content:center; min-height:100vh; }
  .card { background:#fff; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.1); padding:40px; width:360px; max-width:90vw; }
  h1 { font-size:20px; margin-bottom:4px; color:#1a1a2e; }
  .subtitle { color:#666; font-size:14px; margin-bottom:24px; }
  label { display:block; font-size:14px; margin-bottom:6px; color:#333; font-weight:500; }
  input[type="password"] { width:100%; padding:10px 12px; border:1px solid #d9d9d9; border-radius:4px; font-size:14px; outline:none; transition:border-color 0.2s,box-shadow 0.2s; }
  input[type="password"]:focus { border-color:#4a6cf7; box-shadow:0 0 0 2px rgba(74,108,247,0.2); }
  button { width:100%; padding:10px; background:#4a6cf7; color:#fff; border:none; border-radius:4px; font-size:14px; cursor:pointer; margin-top:16px; font-weight:500; }
  button:hover { background:#3b5de7; }
  .error { color:#e74c3c; font-size:13px; margin-top:12px; text-align:center; }
</style>
</head>
<body>
  <div class="card">
    <h1>Kimi WebBridge 管理面板</h1>
    <div class="subtitle">请输入管理员密码</div>
    <form method="post" action="/admin/login">
      <label for="password">密码</label>
      <input type="password" id="password" name="password" autofocus required>
      <button type="submit">登录</button>
    </form>
    {error_html}
  </div>
</body>
</html>"""


# ── Route Handlers ───────────────────────────────────────────────────────


async def login_page(request: Request) -> HTMLResponse:
    """GET /admin/login — render the login form."""
    if not ADMIN_ENABLED:
        return _admin_disabled_page()
    error = _query_param(request, "error", "")
    error_html = f'<div class="error">{_html.escape(error)}</div>' if error else ""
    return HTMLResponse(LOGIN_PAGE_HTML.replace("{error_html}", error_html))


async def login_submit(request: Request) -> Response:
    """POST /admin/login — validate password, set session cookie, redirect."""
    if not ADMIN_ENABLED:
        return _admin_disabled_page()

    ip = _client_ip(request)
    if not _check_rate_limit(ip):
        logger.warning("Rate limit hit for admin login from %s", ip)
        return RedirectResponse(
            url="/admin/login?error=尝试次数过多，请一分钟后再试",
            status_code=302,
        )

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            body = {}
        password = str(body.get("password", ""))
    else:
        form = await request.form()
        password = str(form.get("password", ""))

    if verify_password(password):
        token = create_session_token()
        logger.info("Admin login successful from %s", ip)
        response: Response = RedirectResponse(url="/admin/", status_code=302)
        response.set_cookie(
            COOKIE_NAME,
            token,
            max_age=SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response

    logger.warning("Admin login failed from %s", ip)
    return RedirectResponse(
        url="/admin/login?error=密码错误，请重试",
        status_code=302,
    )


async def logout(request: Request) -> Response:
    """POST /admin/logout — clear session cookie and redirect to login."""
    if not ADMIN_ENABLED:
        return _admin_disabled_page()

    response: Response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    logger.info("Admin logout")
    return response


async def dashboard(request: Request) -> HTMLResponse:
    """GET /admin — render the dashboard page with stats, config, and records."""
    if not ADMIN_ENABLED:
        return _admin_disabled_page()

    return HTMLResponse(DASHBOARD_HTML, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


async def api_records(request: Request) -> JSONResponse:
    """GET /admin/api/records — return paginated call records as JSON."""
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)

    page = _query_param_int(request, "page", 1)
    per_page = _query_param_int(request, "per_page", 20)
    method = _query_param(request, "method", "")
    source = _query_param(request, "source", "")
    date_from = _query_param(request, "date_from", "")
    date_to = _query_param(request, "date_to", "")
    status = _query_param(request, "status", "")

    try:
        data = get_records(
            page=page,
            per_page=per_page,
            method=method,
            source=source,
            date_from=date_from,
            date_to=date_to,
            status=status,
        )
        # Ensure records are JSON-serializable; datetime-like strings are already str
        return JSONResponse(data)
    except Exception:
        logger.exception("Error fetching records")
        return JSONResponse({"error": "internal error"}, status_code=500)


async def api_stats(request: Request) -> JSONResponse:
    """GET /admin/api/stats — return aggregate statistics as JSON."""
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)

    try:
        data = get_stats()
        return JSONResponse(data)
    except Exception:
        logger.exception("Error fetching stats")
        return JSONResponse({"error": "internal error"}, status_code=500)


async def api_get_config(request: Request) -> JSONResponse:
    """GET /admin/api/config — return external API key (unmasked, admin-only)."""
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)

    try:
        stored = get_config("external_api_key") or EXTERNAL_API_KEY
        return JSONResponse({"external_api_key": stored})
    except Exception:
        logger.exception("Error fetching config")
        return JSONResponse({"error": "internal error"}, status_code=500)


async def api_set_config(request: Request) -> JSONResponse:
    """POST /admin/api/config — update external API key."""
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)

    try:
        body: dict[str, Any] = await request.json()
        value = str(body.get("value", ""))
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    if not value:
        return JSONResponse({"error": "value is required"}, status_code=400)

    try:
        set_config("external_api_key", value)
        logger.info("External API key updated via admin panel")
        return JSONResponse({"success": True})
    except Exception:
        logger.exception("Error updating config")
        return JSONResponse({"error": "internal error"}, status_code=500)


async def api_tabs(request: Request) -> JSONResponse:
    """GET /admin/api/tabs — list ALL open browser tabs via Chrome CDP.

    Queries Chrome CDP /json/list directly (bypasses daemon session filter)
    and enriches results with session/group info from the session tracker.
    """
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)

    try:
        targets = await _cdp_get("/json/list")
    except httpx.TimeoutException:
        logger.exception("CDP /json/list timed out")
        return JSONResponse({"error": "chrome CDP unavailable (timeout)"}, status_code=503)
    except httpx.ConnectError:
        logger.exception("CDP connection refused")
        return JSONResponse({"error": "chrome CDP unavailable (connection refused)"}, status_code=503)
    except Exception:
        logger.exception("Error querying Chrome CDP")
        return JSONResponse({"error": "chrome CDP unavailable"}, status_code=503)

    tabs: list[dict[str, Any]] = []
    for i, t in enumerate(targets):
        if t.get("type") != "page":
            continue
        url = t.get("url", "")
        if not url or url.startswith("chrome://") or url == "about:blank":
            continue
        session_info = _get_tab_session(url)
        tabs.append({
            "index": i,
            "targetId": t.get("id", ""),
            "url": url,
            "title": t.get("title", ""),
            "session": session_info["session_id"] if session_info else "—",
            "group": session_info["group_title"] if session_info else "—",
            "key": session_info.get("key_alias", "") or "—",
        })

    return JSONResponse({"data": {"success": True, "tabs": tabs}})


async def api_tabs_close(request: Request) -> JSONResponse:
    """POST /admin/api/tabs/close — close a specific tab via Chrome CDP."""
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)

    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)

    target_id = body.get("targetId", "")

    if not target_id:
        return JSONResponse({"error": "targetId required"}, status_code=400)

    try:
        await _cdp_get(f"/json/close/{target_id}", parse_json=False)
        logger.info("Tab closed via CDP: targetId=%s", target_id[:16])
        return JSONResponse({"success": True})
    except Exception:
        logger.exception("Error closing tab via CDP")
        return JSONResponse({"error": "chrome CDP unavailable"}, status_code=503)


async def api_keys(request: Request) -> JSONResponse:
    """GET /admin/api/keys — list all API keys with usage stats."""
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)
    try:
        keys = get_api_keys()
        return JSONResponse({"keys": keys})
    except Exception:
        logger.exception("Error listing keys")
        return JSONResponse({"error": "internal error"}, status_code=500)


async def api_keys_create(request: Request) -> JSONResponse:
    """POST /admin/api/keys — create a new API key."""
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    key_value = str(body.get("key_value", ""))
    alias = str(body.get("alias", ""))
    if not key_value:
        key_value = f"kimi-{secrets.token_hex(16)}"
    if not alias:
        alias = f"key-{key_value[:8]}"
    try:
        key = create_api_key(key_value, alias)
        return JSONResponse({"key": key})
    except Exception as e:
        logger.exception("Error creating key")
        return JSONResponse({"error": str(e)}, status_code=400)


async def api_keys_update(request: Request) -> JSONResponse:
    """PUT /admin/api/keys/{key_id} — update alias or enabled status."""
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)
    key_id = request.path_params.get("key_id", "")
    if not key_id:
        return JSONResponse({"error": "key_id required"}, status_code=400)
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON body"}, status_code=400)
    alias = body.get("alias")
    enabled = body.get("enabled")
    try:
        ok = update_api_key(key_id, alias=alias, enabled=enabled)
        return JSONResponse({"success": ok})
    except Exception as e:
        logger.exception("Error updating key")
        return JSONResponse({"error": str(e)}, status_code=400)


async def api_keys_delete(request: Request) -> JSONResponse:
    """DELETE /admin/api/keys/{key_id} — delete an API key."""
    if not ADMIN_ENABLED:
        return JSONResponse({"error": "admin disabled"}, status_code=404)
    key_id = request.path_params.get("key_id", "")
    if not key_id:
        return JSONResponse({"error": "key_id required"}, status_code=400)
    try:
        ok = delete_api_key(key_id)
        return JSONResponse({"success": ok})
    except Exception as e:
        logger.exception("Error deleting key")
        return JSONResponse({"error": str(e)}, status_code=400)


# ── Router ───────────────────────────────────────────────────────────────

routes = Router(
    [
        # Auth pages
        Route("/login", endpoint=login_page, methods=["GET"]),
        Route("/login", endpoint=login_submit, methods=["POST"]),
        Route("/logout", endpoint=logout, methods=["POST"]),
        # Dashboard
        Route("/", endpoint=dashboard, methods=["GET"]),
        # API endpoints
        Route("/api/records", endpoint=api_records, methods=["GET"]),
        Route("/api/stats", endpoint=api_stats, methods=["GET"]),
        Route("/api/config", endpoint=api_get_config, methods=["GET"]),
        Route("/api/config", endpoint=api_set_config, methods=["POST"]),
        # Tab management
        Route("/api/tabs", endpoint=api_tabs, methods=["GET"]),
        Route("/api/tabs/close", endpoint=api_tabs_close, methods=["POST"]),
        # API key management
        Route("/api/keys", endpoint=api_keys, methods=["GET"]),
        Route("/api/keys", endpoint=api_keys_create, methods=["POST"]),
        Route("/api/keys/{key_id}", endpoint=api_keys_update, methods=["PUT"]),
        Route("/api/keys/{key_id}", endpoint=api_keys_delete, methods=["DELETE"]),
    ]
)


# ── Inlined Dashboard HTML ──────────────────────────────────────────────

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kimi WebBridge 管理面板</title>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; background:#f0f2f5; color:#333; }
  /* Header */
  .header { background:#1a1a2e; color:#fff; padding:0 24px; height:52px; display:flex; align-items:center; justify-content:space-between; }
  .header h1 { font-size:16px; font-weight:600; }
  .header .logout-btn { background:transparent; border:1px solid rgba(255,255,255,0.3); color:#fff; padding:6px 14px; border-radius:4px; cursor:pointer; font-size:13px; }
  .header .logout-btn:hover { background:rgba(255,255,255,0.1); }
  /* Main content */
  .main { max-width:1100px; margin:0 auto; padding:20px 24px 40px; }
  /* Stats cards */
  .stats-row { display:flex; gap:16px; margin-bottom:24px; flex-wrap:wrap; }
  .stat-card { flex:1; min-width:200px; background:#fff; border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,0.06); padding:20px 24px; }
  .stat-card .label { font-size:13px; color:#999; margin-bottom:6px; }
  .stat-card .value { font-size:28px; font-weight:700; color:#1a1a2e; }
  /* Sections */
  .section { background:#fff; border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,0.06); padding:20px 24px; margin-bottom:20px; }
  .section h2 { font-size:15px; font-weight:600; margin-bottom:16px; color:#1a1a2e; border-bottom:1px solid #f0f0f0; padding-bottom:10px; }
  /* Config section */
  .config-row { display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap; }
  .config-row .field { flex:1; min-width:260px; }
  .config-row label { display:block; font-size:13px; margin-bottom:4px; color:#666; }
  .config-row input[type="text"], .config-row input[type="password"] { width:100%; padding:8px 10px; border:1px solid #d9d9d9; border-radius:4px; font-size:13px; outline:none; font-family:monospace; }
  .config-row input:focus { border-color:#4a6cf7; box-shadow:0 0 0 2px rgba(74,108,247,0.15); }
  .btn { padding:8px 16px; border-radius:4px; font-size:13px; cursor:pointer; border:none; font-weight:500; }
  .btn-primary { background:#4a6cf7; color:#fff; }
  .btn-primary:hover { background:#3b5de7; }
  .btn-outline { background:#fff; color:#4a6cf7; border:1px solid #4a6cf7; }
  .btn-outline:hover { background:#f0f3ff; }
  .btn-sm { padding:5px 12px; font-size:12px; }
  .btn:disabled { opacity:0.5; cursor:not-allowed; }
  .config-msg { font-size:13px; margin-top:8px; }
  /* Filter bar */
  .filter-row { display:flex; gap:10px; margin-bottom:16px; flex-wrap:wrap; align-items:flex-end; }
  .filter-row .field { display:flex; flex-direction:column; gap:2px; }
  .filter-row label { font-size:12px; color:#999; }
  .filter-row select, .filter-row input { padding:6px 8px; border:1px solid #d9d9d9; border-radius:4px; font-size:13px; outline:none; }
  .filter-row select:focus, .filter-row input:focus { border-color:#4a6cf7; }
  .filter-row input[type="date"] { width:140px; }
  .filter-row input[type="text"] { width:160px; }
  /* Table */
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; padding:10px 12px; background:#fafafa; border-bottom:2px solid #f0f0f0; color:#666; font-weight:600; font-size:12px; text-transform:uppercase; }
  td { padding:10px 12px; border-bottom:1px solid #f5f5f5; }
  tr:hover { background:#fafbff; }
  .status-success { color:#27ae60; font-weight:500; }
  .status-error { color:#e74c3c; font-weight:500; }
  .mono { font-family:"SF Mono",Monaco,"Cascadia Code",monospace; font-size:12px; }
  .dim { color:#999; }
  /* Pagination */
  .pagination { display:flex; align-items:center; justify-content:center; gap:12px; margin-top:16px; font-size:13px; }
  .pagination .btn { padding:6px 14px; }
  .pagination .info { color:#666; }
  /* Empty state */
  .empty { text-align:center; padding:40px 0; color:#999; font-size:14px; }
  /* Toast */
  .toast { position:fixed; top:60px; right:20px; padding:10px 20px; border-radius:4px; font-size:13px; color:#fff; z-index:100; display:none; }
  .toast.success { background:#27ae60; }
  .toast.error { background:#e74c3c; }
</style>
</head>
<body>
  <!-- Header -->
  <div class="header">
    <h1>Kimi WebBridge 管理面板</h1>
    <form method="post" action="/admin/logout" style="margin:0;">
      <button type="submit" class="logout-btn">退出登录</button>
    </form>
  </div>

  <!-- Toast -->
  <div id="toast" class="toast"></div>

  <div class="main">
    <!-- Stats Cards -->
    <div class="stats-row" id="stats-row">
      <div class="stat-card"><div class="label">总调用数</div><div class="value" id="stat-total">--</div></div>
      <div class="stat-card"><div class="label">成功率</div><div class="value" id="stat-rate">--</div></div>
      <div class="stat-card"><div class="label">今日调用</div><div class="value" id="stat-today">--</div></div>
      <div class="stat-card"><div class="label">活跃来源</div><div class="value" id="stat-sources">--</div></div>
    </div>

    <!-- Key Management Section -->
    <div class="section">
      <h2>API Key 管理 <button id="create-key-btn" class="btn btn-primary btn-sm" type="button">+ 新建密钥</button></h2>
      <div id="keys-container">
        <table>
          <thead>
            <tr>
              <th>别名</th>
              <th>密钥</th>
              <th>状态</th>
              <th>调用次数</th>
              <th>创建时间</th>
              <th style="width:120px">操作</th>
            </tr>
          </thead>
          <tbody id="keys-tbody"></tbody>
        </table>
      </div>
      <!-- Create Key Modal -->
      <div id="create-key-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:200; align-items:center; justify-content:center;">
        <div style="background:#fff; border-radius:8px; padding:24px; width:400px; max-width:90vw;">
          <h3 style="margin-bottom:16px;">新建 API Key</h3>
          <label style="font-size:13px;display:block;margin-bottom:4px;">别名</label>
          <input id="new-key-alias" style="width:100%;padding:8px;border:1px solid #d9d9d9;border-radius:4px;margin-bottom:12px;" placeholder="例如: 客户A">
          <label style="font-size:13px;display:block;margin-bottom:4px;">密钥（留空自动生成）</label>
          <input id="new-key-value" style="width:100%;padding:8px;border:1px solid #d9d9d9;border-radius:4px;margin-bottom:16px;" placeholder="自动生成 64 位随机密钥">
          <div style="display:flex;gap:8px;justify-content:flex-end;">
            <button id="cancel-create-key" class="btn btn-outline btn-sm" type="button">取消</button>
            <button id="confirm-create-key" class="btn btn-primary btn-sm" type="button">创建</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Tabs Section -->
    <div class="section">
      <h2>浏览器页面管理 <button id="refresh-tabs" class="btn btn-outline btn-sm">刷新</button></h2>
      <div id="tabs-container">
        <table>
          <thead>
            <tr>
              <th style="width:40px">#</th>
              <th>URL</th>
              <th>标题</th>
              <th style="width:70px">密钥</th>
              <th style="width:80px">会话</th>
              <th style="width:100px">分组</th>
              <th style="width:90px">操作</th>
            </tr>
          </thead>
          <tbody id="tabs-tbody"></tbody>
        </table>
      </div>
    </div>

    <!-- Records Section -->
    <div class="section">
      <h2>调用记录 <button id="refresh-records" class="btn btn-outline btn-sm">刷新</button></h2>
      <!-- Filters -->
      <div class="filter-row" id="filter-row">
        <div class="field">
          <label>方法</label>
          <select id="filter-method"><option value="">全部</option></select>
        </div>
        <div class="field">
          <label>密钥</label>
          <input type="text" id="filter-source" placeholder="输入密钥别名">
        </div>
        <div class="field">
          <label>开始日期</label>
          <input type="date" id="filter-from">
        </div>
        <div class="field">
          <label>结束日期</label>
          <input type="date" id="filter-to">
        </div>
        <div class="field">
          <label>状态</label>
          <select id="filter-status">
            <option value="">全部</option>
            <option value="success">success</option>
            <option value="error">error</option>
          </select>
        </div>
        <button class="btn btn-primary btn-sm" id="filter-apply" type="button" style="align-self:flex-end;">查询</button>
      </div>

      <!-- Table -->
      <div id="records-container">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>密钥</th>
              <th>方法</th>
              <th>耗时</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody id="records-tbody"></tbody>
        </table>
        <!-- Pagination -->
        <div class="pagination" id="pagination">
          <button class="btn btn-outline btn-sm" id="btn-prev" disabled>上一页</button>
          <span class="info" id="page-info">--</span>
          <button class="btn btn-outline btn-sm" id="btn-next" disabled>下一页</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    // ── State ────────────────────────────────────────────────────────────
    var currentPage = 1;
    var totalPages = 1;

    // ── Helpers ──────────────────────────────────────────────────────────
    function formatDate(ts) {
      if (!ts) return '-';
      var d = new Date(ts.replace(' ','T') + 'Z');
      if (isNaN(d.getTime())) return ts.slice(0,19);
      var pad = function(n) { return n < 10 ? '0'+n : ''+n; };
      return d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate())+' '+pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds());
    }

    function showToast(msg, type) {
      var el = document.getElementById('toast');
      el.textContent = msg;
      el.className = 'toast ' + type;
      el.style.display = 'block';
      setTimeout(function(){ el.style.display = 'none'; }, 3000);
    }

    // ── Stats ────────────────────────────────────────────────────────────
    function loadStats() {
      fetch('/admin/api/stats', {credentials:'same-origin'})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d.error) return;
          document.getElementById('stat-total').textContent = d.total_calls != null ? d.total_calls : 0;
          document.getElementById('stat-rate').textContent = (d.success_rate != null ? d.success_rate : 0) + '%';
          document.getElementById('stat-today').textContent = d.today_calls != null ? d.today_calls : 0;
          var srcCount = (d.top_sources && d.top_sources.length) ? d.top_sources.length : 0;
          document.getElementById('stat-sources').textContent = srcCount;
          // Populate method filter
          var sel = document.getElementById('filter-method');
          sel.innerHTML = '<option value="">全部</option>';
          if (d.top_methods && d.top_methods.length > 0) {
            for (var i = 0; i < d.top_methods.length; i++) {
              var opt = document.createElement('option');
              opt.value = d.top_methods[i].method;
              opt.textContent = d.top_methods[i].method + ' (' + d.top_methods[i].cnt + ')';
              sel.appendChild(opt);
            }
          }
        })
        .catch(function(){});
    }

    // ── API Key Management ─────────────────────────────────────────────
    function loadKeys() {
      fetch('/admin/api/keys', {credentials:'same-origin'})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d.error) return;
          var tbody = document.getElementById('keys-tbody');
          var keys = d.keys || [];
          if (!keys.length) { tbody.innerHTML = '<tr><td colspan="5" class="empty">暂无密钥</td></tr>'; return; }
          var h = '';
          for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            var masked = k.key_value ? (k.key_value.substring(0,6) + '****' + k.key_value.substring(k.key_value.length-4)) : '****';
            var statusBadge = k.enabled ? '<span style="color:#27ae60;font-weight:500;">启用</span>' : '<span style="color:#e74c3c;font-weight:500;">禁用</span>';
            h += '<tr>' +
              '<td><span class="mono">' + escapeHtml(k.alias || '-') + '</span></td>' +
              '<td><span class="mono dim" title="' + escapeHtml(k.key_value||'') + '">' + escapeHtml(masked) + '</span></td>' +
              '<td>' + statusBadge + '</td>' +
              '<td>' + (k.call_count || 0) + '</td>' +
              '<td class="dim">' + formatDate(k.created_at) + '</td>' +
              '<td>' +
                '<button class="btn btn-outline btn-sm key-edit-btn" data-key-id="' + k.id + '" data-key-alias="' + escapeHtml(k.alias||'') + '" style="font-size:11px;">改名</button> ' +
                '<button class="btn btn-outline btn-sm key-toggle-btn" data-key-id="' + k.id + '" data-key-enabled="' + k.enabled + '" style="font-size:11px;">' + (k.enabled ? '禁用' : '启用') + '</button> ' +
                '<button class="btn btn-outline btn-sm key-delete-btn" data-key-id="' + k.id + '" style="color:#e74c3c;border-color:#e74c3c;font-size:11px;">删除</button>' +
              '</td></tr>';
          }
          tbody.innerHTML = h;
        }).catch(function(){});
    }

    document.getElementById('create-key-btn').addEventListener('click', function(){
      document.getElementById('create-key-modal').style.display = 'flex';
    });
    document.getElementById('cancel-create-key').addEventListener('click', function(){
      document.getElementById('create-key-modal').style.display = 'none';
    });
    document.getElementById('confirm-create-key').addEventListener('click', function(){
      var alias = document.getElementById('new-key-alias').value.trim() || 'new-key';
      var keyValue = document.getElementById('new-key-value').value.trim();
      this.disabled = true;
      fetch('/admin/api/keys', {
        method:'POST', credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({alias: alias, key_value: keyValue})
      }).then(function(r){ return r.json(); })
        .then(function(d){
          if (d.key) {
            document.getElementById('create-key-modal').style.display = 'none';
            showToast('密钥已创建:' + (d.key.key_value ? ' ' + d.key.key_value.substring(0,8)+'...' : ''), 'success');
            loadKeys();
          } else { showToast('创建失败: ' + (d.error||''), 'error'); }
        }).catch(function(){ showToast('网络错误', 'error'); })
        .finally(function(){ document.getElementById('confirm-create-key').disabled = false; });
    });
    function editKeyAlias(id, curAlias) {
      var alias = prompt('修改别名:', curAlias);
      if (alias === null) return;
      fetch('/admin/api/keys/' + id, {
        method:'PUT', credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({alias: alias})
      }).then(function(r){ return r.json(); })
        .then(function(d){ if (d.success) { showToast('别名已更新', 'success'); loadKeys(); } else { showToast('更新失败', 'error'); } })
        .catch(function(){ showToast('网络错误', 'error'); });
    }
    function toggleKey(id, curEnabled) {
      fetch('/admin/api/keys/' + id, {
        method:'PUT', credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({enabled: !curEnabled})
      }).then(function(r){ return r.json(); })
        .then(function(d){ if (d.success) { showToast(curEnabled ? '已禁用' : '已启用', 'success'); loadKeys(); } else { showToast('操作失败', 'error'); } })
        .catch(function(){ showToast('网络错误', 'error'); });
    }
    function deleteKey(id) {
      if (!confirm('确定删除？')) return;
      fetch('/admin/api/keys/' + id, {method:'DELETE', credentials:'same-origin'})
        .then(function(r){ return r.json(); })
        .then(function(d){ if (d.success) { showToast('已删除', 'success'); loadKeys(); } else { showToast('删除失败', 'error'); } })
        .catch(function(){ showToast('网络错误', 'error'); });
    }

    function loadRecords() {
      var params = new URLSearchParams();
      params.set('page', currentPage);
      params.set('per_page', '20');
      var method = document.getElementById('filter-method').value;
      var source = document.getElementById('filter-source').value.trim();
      var from = document.getElementById('filter-from').value;
      var to = document.getElementById('filter-to').value;
      var status = document.getElementById('filter-status').value;
      if (method) params.set('method', method);
      if (source) params.set('source', source);
      if (from) params.set('date_from', from + 'T00:00:00');
      if (to) params.set('date_to', to + 'T23:59:59');
      if (status) params.set('status', status);

      fetch('/admin/api/records?' + params.toString(), {credentials:'same-origin'})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d.error) {
            document.getElementById('records-tbody').innerHTML = '<tr><td colspan="5" class="empty">加载失败</td></tr>';
            return;
          }
          renderRecords(d);
        })
        .catch(function(){
          document.getElementById('records-tbody').innerHTML = '<tr><td colspan="5" class="empty">网络错误</td></tr>';
        });
    }

    function renderRecords(data) {
      var tbody = document.getElementById('records-tbody');
      var records = data.records || [];
      var total = data.total || 0;
      var page = data.page || 1;
      var tp = data.total_pages || 1;

      currentPage = page;
      totalPages = tp;

      if (records.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">暂无调用记录</td></tr>';
      } else {
        var html = '';
        for (var i = 0; i < records.length; i++) {
          var r = records[i];
          var statusClass = r.result_status === 'success' ? 'status-success' : 'status-error';
          var statusIcon = r.result_status === 'success' ? '✅ 成功' : '❌ 错误';
          var durationStr = (r.duration_ms != null) ? r.duration_ms + ' ms' : '-';
          html += '<tr>' +
            '<td class="dim">' + formatDate(r.timestamp) + '</td>' +
            '<td><span class="mono">' + escapeHtml(r.key_alias || '-') + '</span></td>' +
            '<td class="mono">' + escapeHtml(r.method||'') + '</td>' +
            '<td>' + escapeHtml(durationStr) + '</td>' +
            '<td class="' + statusClass + '">' + statusIcon + '</td>' +
            '</tr>';
        }
        tbody.innerHTML = html;
      }

      document.getElementById('page-info').textContent =
        '第 ' + page + ' 页 / 共 ' + tp + ' 页 (总计 ' + total + ' 条)';
      document.getElementById('btn-prev').disabled = (page <= 1);
      document.getElementById('btn-next').disabled = (page >= tp);
    }

    function escapeHtml(str) {
      var div = document.createElement('div');
      div.appendChild(document.createTextNode(str));
      return div.innerHTML;
    }

    // ── Pagination buttons ───────────────────────────────────────────────
    document.getElementById('btn-prev').addEventListener('click', function(){
      if (currentPage > 1) { currentPage--; loadRecords(); }
    });
    document.getElementById('btn-next').addEventListener('click', function(){
      if (currentPage < totalPages) { currentPage++; loadRecords(); }
    });

    // ── Filter apply ─────────────────────────────────────────────────────
    document.getElementById('filter-apply').addEventListener('click', function(){
      currentPage = 1;
      loadRecords();
    });

    // ── Tabs Management ───────────────────────────────────────────────────
    function loadTabs() {
      var container = document.getElementById('tabs-container');
      container.innerHTML = '<div class="empty">加载中…</div>';
      fetch('/admin/api/tabs', {credentials:'same-origin'})
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d.error) {
            var msg = d.error;
            if (d.error.indexOf('timeout') !== -1) {
              msg = 'Chrome 浏览器响应超时（可能正忙于处理请求），请稍后刷新';
            } else if (d.error.indexOf('connection') !== -1) {
              msg = '无法连接 Chrome 浏览器，请等待服务恢复';
            } else if (d.error.indexOf('CDP') !== -1) {
              msg = '浏览器 CDP 不可用（Chrome 连接异常）';
            }
            container.innerHTML = '<div class="empty">' + escapeHtml(msg) + '</div>';
            return;
          }
          renderTabs(d);
        })
        .catch(function(){
          container.innerHTML = '<div class="empty">页面查询失败（管理面板服务异常）</div>';
        });
    }

    function renderTabs(data) {
      var tabs = [];
      if (data.data && Array.isArray(data.data.tabs)) {
        tabs = data.data.tabs;
      } else if (data.tabs && Array.isArray(data.tabs)) {
        tabs = data.tabs;
      } else if (Array.isArray(data)) {
        tabs = data;
      }

      if (tabs.length === 0) {
        document.getElementById('tabs-container').innerHTML =
          '<table><thead><tr><th>#</th><th>URL</th><th>标题</th><th>密钥</th><th>会话</th><th>分组</th><th>操作</th></tr></thead>' +
          '<tbody><tr><td colspan="7" class="empty">暂无打开的页面</td></tr></tbody></table>';
        return;
      }

      var html = '<table><thead><tr><th>#</th><th>URL</th><th>标题</th><th>密钥</th><th>会话</th><th>分组</th><th>操作</th></tr></thead><tbody>';
      for (var i = 0; i < tabs.length; i++) {
        var t = tabs[i];
        var url = escapeHtml(t.url || '');
        var title = escapeHtml(t.title || '');
        var group = escapeHtml(t.group_title || t.group || t.groupTitle || '-');
        var index = t.index != null ? t.index : i;
         html += '<tr>' +
          '<td class="dim">' + (index + 1) + '</td>' +
          '<td><span class="mono" title="' + url + '">' + truncate(url, 60) + '</span></td>' +
          '<td>' + truncate(title, 40) + '</td>' +
          '<td class="dim">' + escapeHtml(t.key || '-') + '</td>' +
          '<td class="dim">' + escapeHtml(t.session || '-') + '</td>' +
          '<td class="dim">' + group + '</td>' +
          '<td><button class="btn btn-outline btn-sm tab-close-btn" data-target="' + escapeHtml(t.targetId || '') + '" style="color:#e74c3c;border-color:#e74c3c;">关闭</button></td>' +
          '</tr>';
      }
      html += '</tbody></table>';
      document.getElementById('tabs-container').innerHTML = html;
    }

    function closeTab(targetId) {
      if (!confirm('确定要关闭此页面吗？')) return;
      fetch('/admin/api/tabs/close', {
        method:'POST',
        credentials:'same-origin',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({targetId: targetId})
      })
        .then(function(r){ return r.json(); })
        .then(function(d){
          if (d.error) {
            showToast('关闭失败: ' + d.error, 'error');
          } else {
            showToast('页面已关闭', 'success');
            loadTabs();
          }
        })
        .catch(function(){
          showToast('网络错误', 'error');
        });
    }

    function truncate(str, len) {
      if (!str) return '-';
      return str.length > len ? str.substring(0, len) + '…' : str;
    }

    document.getElementById('refresh-tabs').addEventListener('click', loadTabs);
    document.getElementById('refresh-records').addEventListener('click', function(){ currentPage=1; loadRecords(); });
    document.addEventListener('click', function(e) {
      var btn = e.target.closest('.tab-close-btn');
      if (btn) { e.preventDefault(); closeTab(btn.getAttribute('data-target')); }
      var keb = e.target.closest('.key-edit-btn');
      if (keb) { e.preventDefault(); editKeyAlias(keb.getAttribute('data-key-id'), keb.getAttribute('data-key-alias')); }
      var ktb = e.target.closest('.key-toggle-btn');
      if (ktb) { e.preventDefault(); toggleKey(ktb.getAttribute('data-key-id'), ktb.getAttribute('data-key-enabled') === '1'); }
      var kdb = e.target.closest('.key-delete-btn');
      if (kdb) { e.preventDefault(); deleteKey(kdb.getAttribute('data-key-id')); }
    });

    // ── Init ─────────────────────────────────────────────────────────────
    loadStats();
    loadKeys();
    loadTabs();
    loadRecords();
  </script>
</body>
</html>"""
