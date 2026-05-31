"""MCP tool handlers wrapping kimi-webbridge daemon REST API."""

import base64
import json
import os
from typing import Any

import httpx

DAEMON_URL = os.environ.get("DAEMON_URL", "http://127.0.0.1:10086")
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(base_url=DAEMON_URL, timeout=120.0)
    return _client


async def _call(action: str, args: dict[str, Any] | None = None, session_id: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"action": action, "args": args or {}}
    if session_id:
        body["session"] = session_id
    resp = await get_client().post("/command", json=body)
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()
    if "error" in data or data.get("success") is False:
        raise RuntimeError(f"kimi-webbridge error: {data}")
    return data


def _read_file_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ── Tools ──────────────────────────────────────────────────────────────


async def navigate(url: str, new_tab: bool = True, group_title: str = "", session_id: str = "") -> str:
    """Navigate to a URL. Supports new tab and tab group naming.

    Args:
        url: The URL to navigate to.
        new_tab: Open in a new tab (default true). Use false to reuse current tab.
        group_title: Title for the tab group (only applies when new_tab=true).
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    args: dict[str, Any] = {"url": url, "newTab": new_tab}
    if new_tab and group_title:
        args["group_title"] = group_title
    sid = session_id or None
    data = await _call("navigate", args, sid)
    return json.dumps(data, ensure_ascii=False)


async def find_tab(url: str = "", active: bool = False, session_id: str = "") -> str:
    """Find an already-open tab by URL or active state.

    Args:
        url: URL or domain to match. Empty string finds any tab.
        active: If true, returns the tab the user is currently viewing.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    args: dict[str, Any] = {}
    if url:
        args["url"] = url
    args["active"] = active
    data = await _call("find_tab", args, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def snapshot(session_id: str = "") -> str:
    """Get the accessibility tree of the current page. Returns @e refs for interactive elements.

    Args:
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("snapshot", {}, session_id or None)
    tree = data.get("tree", "")
    title = data.get("title", "")
    url = data.get("url", "")
    return json.dumps({"url": url, "title": title, "tree": tree}, ensure_ascii=False)


async def click(selector: str, session_id: str = "") -> str:
    """Click an element identified by @e ref (from snapshot) or CSS selector.

    Args:
        selector: The @e ref (e.g. @e123) or CSS selector of the element to click.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("click", {"selector": selector}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def fill(selector: str, value: str, session_id: str = "") -> str:
    """Fill text into input, textarea, or contenteditable elements.
    Replaces existing content (clear-and-insert).

    Args:
        selector: The @e ref or CSS selector of the input element.
        value: The text to fill into the element.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("fill", {"selector": selector, "value": value}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def mouse_click(selector: str, session_id: str = "") -> str:
    """Click an element using CDP-level mouse events (more reliable than DOM click).
    Handles edge cases like display:none, detached elements, or shadow DOM.

    Args:
        selector: The @e ref (e.g. @e123) or CSS selector of the element to click.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("mouse_click", {"selector": selector}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def cdp(method: str, params: str = "{}", session_id: str = "") -> str:
    """Execute a raw Chrome DevTools Protocol command. Full access to CDP.
    Use when no other tool can do what you need.

    Args:
        method: CDP method name (e.g. "Page.captureScreenshot", "Input.dispatchMouseEvent").
        params: JSON string of CDP params (e.g. '{"format":"png"}').
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    import json as _json
    data = await _call("cdp", {"method": method, "params": _json.loads(params)}, session_id or None)
    return _json.dumps(data, ensure_ascii=False)


async def key_type(text: str, session_id: str = "") -> str:
    """Insert text directly into the current input focus via Input.insertText.
    Unlike fill(), this types at the cursor position rather than replacing content.

    Args:
        text: The text to type.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("key_type", {"text": text}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def send_keys(keys: str, repeat: int = 1, session_id: str = "") -> str:
    """Send keyboard key events. Supports modifiers (Alt/Ctrl/Cmd/Shift/Meta),
    function keys (F1-F12), named keys (Enter, Escape, Tab, Backspace, etc.),
    and single characters. The 'Mod' modifier auto-resolves to Cmd on Mac or Ctrl on others.

    Examples: "Enter", "Mod+A", "Shift+Tab", "Ctrl+F5", "Enter Escape", "PageDown"

    Args:
        keys: Keys string. Use '+' for combos, space to separate multiple keys.
        repeat: Number of times to repeat the key sequence. Default 1, max 100.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("send_keys", {"keys": keys, "repeat": repeat}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def screenshot(format: str = "png", quality: int = 80, selector: str = "", session_id: str = "") -> str:
    """Take a screenshot of the current page or a specific element.
    Returns base64-encoded image data.

    Args:
        format: Image format ("png" or "jpeg"). Default png.
        quality: JPEG quality 0-100. Default 80.
        selector: Optional @e ref or CSS selector for element-only screenshot.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    args: dict[str, Any] = {"format": format, "quality": quality}
    if selector:
        args["selector"] = selector
    data = await _call("screenshot", args, session_id or None)
    path = data.get("path", "")
    if path:
        b64 = _read_file_b64(path)
        mime = data.get("mimeType", f"image/{format}")
        return json.dumps({"mimeType": mime, "data": b64, "sizeBytes": data.get("sizeBytes")}, ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False)


async def evaluate(code: str, session_id: str = "") -> str:
    """Execute JavaScript code in the browser page context.

    Args:
        code: JavaScript code to execute. Supports async/await.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("evaluate", {"code": code}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def network(cmd: str, url_filter: str = "", request_id: str = "", session_id: str = "") -> str:
    """Control network request monitoring: start, stop, list, or get detail.

    Args:
        cmd: One of "start", "stop", "list", "detail".
        url_filter: URL filter pattern (for start command).
        request_id: Specific request ID (for detail command).
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    args: dict[str, Any] = {"cmd": cmd}
    if url_filter:
        args["filter"] = url_filter
    if request_id:
        args["requestId"] = request_id
    data = await _call("network", args, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def upload(selector: str, files: str, session_id: str = "") -> str:
    """Upload files to a file input element.

    Args:
        selector: The @e ref or CSS selector of the file input.
        files: Comma-separated list of file paths to upload.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    file_list = [f.strip() for f in files.split(",") if f.strip()]
    data = await _call("upload", {"selector": selector, "files": file_list}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def save_as_pdf(
    paper_format: str = "letter",
    landscape: bool = False,
    scale: float = 1.0,
    print_background: bool = True,
    session_id: str = "",
) -> str:
    """Save the current page as PDF. Returns base64-encoded PDF data.

    Args:
        paper_format: "letter", "a4", "legal", "a3", or "tabloid". Default letter.
        landscape: Landscape orientation. Default false.
        scale: Scale factor 0.1-2.0. Default 1.0.
        print_background: Include background colors. Default true.
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    args: dict[str, Any] = {
        "paper_format": paper_format,
        "landscape": landscape,
        "scale": scale,
        "print_background": print_background,
    }
    data = await _call("save_as_pdf", args, session_id or None)
    path = data.get("path", "")
    if path:
        b64 = _read_file_b64(path)
        return json.dumps({"mimeType": "application/pdf", "data": b64, "pageTitle": data.get("pageTitle", ""), "sizeBytes": data.get("sizeBytes")}, ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False)


async def list_tabs(session_id: str = "") -> str:
    """List all open tabs in the current session.

    Args:
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("list_tabs", {}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def close_tab(session_id: str = "") -> str:
    """Close the current tab in the session.

    Args:
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("close_tab", {}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


async def close_session(session_id: str = "") -> str:
    """Close all tabs in the session.

    Args:
        session_id: Session ID for tab group isolation. Auto-generated if empty.
    """
    data = await _call("close_session", {}, session_id or None)
    return json.dumps(data, ensure_ascii=False)


TOOL_REGISTRY = [
    (navigate, "Navigate to a URL. Use new_tab=true for the first call to create a new tab group."),
    (find_tab, "Find an already-open tab by URL or active state. Use before navigate if reusing tabs."),
    (snapshot, "Get the accessibility tree of the current page with @e refs for interactive elements."),
    (click, "Click an element by @e ref (from snapshot) or CSS selector."),
    (mouse_click, "Click with CDP-level mouse events. More reliable for edge cases than DOM click."),
    (fill, "Fill text into input, textarea, or contenteditable fields. Replaces existing content."),
    (key_type, "Insert text at cursor position. Unlike fill(), types rather than replaces."),
    (send_keys, "Send keyboard events with modifiers. E.g. 'Mod+A', 'Enter', 'Ctrl+F5'."),
    (screenshot, "Take a screenshot. Returns base64 image data. Use for visual verification."),
    (evaluate, "Execute JavaScript in the page. Supports async/await. Use when snapshot/click/fill can't reach."),
    (cdp, "Execute a raw Chrome DevTools Protocol command. For advanced browser control."),
    (network, "Monitor network requests. Use url_filter to capture specific URLs."),
    (upload, "Upload files via a file input element."),
    (save_as_pdf, "Save the current page as PDF. Returns base64-encoded data."),
    (list_tabs, "List all open tabs in the session."),
    (close_tab, "Close the current tab. Always close tabs when done to free resources."),
    (close_session, "Close all tabs in the session. Always call this when a task completes — tabs are not auto-closed."),
]
