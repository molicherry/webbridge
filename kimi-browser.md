---
name: kimi-browser
description: Remote browser control via MCP — navigate, click, fill forms, screenshot, save as PDF, run JavaScript, monitor network requests, upload files. Persistent cookies and localStorage mean login state is reused automatically across calls. Use this skill whenever the user wants to browse the web, automate browser tasks, scrape webpage content, log in to a site, fill out web forms, capture screenshots, export pages to PDF, monitor API calls, or debug a webpage. Also use when the user mentions "browser", "webpage", "open URL", "screenshot", "scrape", "automation", "MCP browser", or Chinese keywords like "浏览器" "网页" "截图" "抓取" "自动化" "登录网站" "填表单". Session isolation (via session_id) supports parallel multi-task workflows.
---

# Kimi Browser — Remote Browser Control via MCP

You have access to a **remote browser** controlled via MCP. It has full web browsing capabilities with persistent cookies, localStorage, and cache shared across all sessions — **login state is reused automatically between calls**.

> **MCP tool name prefix**: All tools in this skill are exposed under the `mcp__kimi-browser__*` namespace.
> For brevity, this document refers to them by their short names (e.g. `navigate`, `click`, `snapshot`).
> When invoking, use the full MCP names: `mcp__kimi-browser__navigate`, `mcp__kimi-browser__click`, `mcp__kimi-browser__snapshot`, etc.

## Core Workflow

For any web interaction task, follow this pattern:

```
1. navigate(url, session_id="my-task")   → open page in a named tab group
2. snapshot(session_id="my-task")        → get accessibility tree with @e refs
3. click / fill / mouse_click            → interact using @e refs from snapshot
4. screenshot(session_id="my-task")      → visually verify (optional)
5. close_session("my-task")              → **REQUIRED: clean up when done**
```

**Always close sessions.** Tabs are never auto-closed — if you skip `close_session`, tabs accumulate indefinitely, wasting memory.

### Session Isolation

Use `session_id` to group tabs. Different agents/tasks can share the same browser but keep their tabs visually separated:

```
session_id="task-search"  → purple tab group
session_id="task-form"    → green tab group
```

## Tool Reference

### Navigation
- **`navigate(url, new_tab, group_title, session_id)`** — Open a page. Use `new_tab=true` on first call. `group_title` labels the tab group.
- **`find_tab(url, active, session_id)`** — Find an existing tab. Use before `navigate` if reusing tabs.
- **`list_tabs(session_id)`** — List all tabs in a session.
- **`close_tab(session_id)`** — Close current tab.
- **`close_session(session_id)`** — Close all tabs in a session.

### Page Inspection
- **`snapshot(session_id)`** — Get the accessibility tree. Returns `@e123` refs for every interactive element (buttons, inputs, links, etc.). Always run this before any click/fill.
- **`evaluate(code, session_id)`** — Execute JavaScript in the page. Use for data extraction, form state inspection, or when snapshot doesn't give enough detail. Supports `async/await`.

### Interaction
- **`click(selector, session_id)`** — DOM-level click. Works for most elements. Use `@e123` refs from snapshot, or CSS selectors.
- **`mouse_click(selector, session_id)`** — CDP-level mouse click with scroll-into-view and coordinate calculation. Use when `click` fails (display:none, detached, shadow DOM). More reliable for stubborn elements.
- **`fill(selector, value, session_id)`** — Replace the entire content of an input/textarea/contenteditable. Use for form filling.
- **`key_type(text, session_id)`** — Insert text at cursor position without replacing existing content. Better for typing into rich text editors.
- **`send_keys(keys, repeat, session_id)`** — Send keyboard events with modifiers. Examples: `"Enter"`, `"Mod+A"`, `"Ctrl+F5"`, `"Tab"`, `"Escape"`, `"PageDown"`. Mod auto-resolves to Cmd on Mac, Ctrl on Linux/Windows.

### Capture & Export
- **`screenshot(format, quality, selector, session_id)`** — Take a screenshot. Default PNG. Set `selector="@e42"` to capture only that element. Returns base64 data.
- **`save_as_pdf(paper_format, landscape, scale, print_background, session_id)`** — Export the current page as PDF. Returns base64 data.

### Advanced
- **`cdp(method, params, session_id)`** — Execute raw Chrome DevTools Protocol commands. Use for capabilities not covered by the other tools (e.g., `"Page.setDownloadBehavior"`, `"Emulation.setUserAgentOverride"`). `params` is a JSON string: `'{"behavior":"allow"}'`.
- **`network(cmd, url_filter, request_id, session_id)`** — Monitor network requests:
  - `cmd="start"` — begin capturing
  - `cmd="list"` — get captured requests
  - `cmd="detail"` — get request/response body for a specific request
  - `cmd="stop"` — stop capturing
- **`upload(selector, files, session_id)`** — Upload files to a file input. `files` is a comma-separated list of server-side file paths.

## Best Practices

1. **Always snapshot before interacting** — The `@e` refs are more stable than CSS selectors.
2. **Use mouse_click for stubborn elements** — If `click` doesn't work, `mouse_click` uses real CDP mouse events.
3. **Use evaluate for data extraction** — `snapshot` gives structure, `evaluate` gives data. Combine them.
4. **Clean up sessions** — Call `close_session` when done to keep the browser manageable.
5. **One session per task** — Different tasks should use different `session_id` values.
6. **Browser state is persistent** — Cookies and session data are reused across calls; you typically don't need to log in twice.
7. **Wait for page loads** — After `navigate`, the tool waits up to 30s for the page to fully load.
8. **Network monitoring for debugging** — Use `network` to inspect API calls when a page behaves unexpectedly.

## Common Patterns

### Login to a site
```
navigate("https://example.com/login", session_id="login")
snapshot()                          → find @e refs for username/password fields + submit button
fill("@e5", "myuser")
fill("@e8", "mypassword")
click("@e12")                        → click login button
screenshot()                         → verify login success
```

### Scrape data from a page
```
navigate("https://example.com/data", session_id="scrape")
snapshot()                           → understand page structure
evaluate("JSON.stringify(Array.from(document.querySelectorAll('.item')).map(el => ({title: el.querySelector('h3').textContent, price: el.querySelector('.price').textContent})))")
```

### Fill a complex form
```
snapshot()                           → find all form field @e refs
fill("@e3", "John")
key_type("@e7", "additional notes")  → append text without clearing
click("@e15")                        → select a dropdown option
send_keys("Tab")                     → move to next field
send_keys("Enter")                   → submit form
```

### Debug a page issue
```
network("start", url_filter="api.example.com")
click("@e_button")
network("list")                      → see what API calls were made
network("detail", request_id="123")  → inspect response body
screenshot()                         → visual check
evaluate("document.title")           → quick JS check
```

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| **All MCP calls fail with connection error** | MCP server unreachable | Report to the user — this is a deployment/runtime issue outside the skill's control |
| **`snapshot` returns empty / no `@e` refs** | Page not fully loaded, or JavaScript-heavy SPA still rendering | Wait a moment then re-snapshot; or use `evaluate("document.readyState")` to confirm; for SPAs, poll until target elements appear |
| **`click(@eXX)` does nothing** | Element is `display:none`, detached, inside shadow DOM, or behind an overlay | Fall back to `mouse_click(@eXX)` — it uses real CDP mouse events with scroll-into-view |
| **`fill` doesn't replace content in a rich text editor** | The editor is contenteditable and intercepts value setting | Use `key_type` instead — it inserts text at cursor position via real keyboard events |
| **Session seems "stuck" / wrong page shown** | Stale tab in the session group, or navigation happened in a different tab | Run `list_tabs(session_id)` to inspect; use `find_tab` to locate the right one; or `close_session` + start fresh |
| **Tabs accumulating, browser slow** | Forgot to call `close_session` after previous tasks | Always call `close_session(session_id)` at task end; for cleanup, list and close orphaned sessions |
| **`navigate` times out after 30s** | Slow target site, or remote browser cannot reach the URL | Retry once; if persistent, report to the user with the URL |
| **Cookies/login state lost unexpectedly** | Remote state was cleared, or session profile changed | Re-login; if it keeps happening, report to the user |
| **`upload` fails** | File path is client-side, not on the remote browser's filesystem | `upload` expects paths reachable by the remote browser; ensure the file is accessible there before calling |
| **`evaluate` returns `undefined` for async code** | Missing `await` or implicit return | Wrap in IIFE: `(async () => { const r = await fetch(...); return await r.json(); })()` |

### Recovery checklist when things go wrong

1. `list_tabs(session_id)` — confirm tabs exist and are on the expected URL
2. `screenshot(session_id)` — visually verify page state
3. `evaluate("document.readyState", session_id)` — confirm page finished loading
4. `evaluate("document.title", session_id)` — confirm you're on the right page
5. If all fails: `close_session(session_id)` and restart the flow from `navigate`

## Behavior & Limitations

* **Skill version**: 1.0 (2026-06)
* **State persistence**: Cookies, localStorage, IndexedDB, and cache persist across calls — login state is reused automatically
* **Concurrency**: Multiple sessions identified by `session_id`; tab groups are visually color-coded per session
* **Known limitations**:
  - File uploads require paths reachable by the remote browser (no client-side upload bridge)
  - All sessions share the same browser profile (no profile-level isolation)
  - 30-second hard timeout on `navigate` page loads
  - Shadow DOM elements may require `mouse_click` instead of `click`
  - No built-in download interception — use `cdp("Page.setDownloadBehavior", ...)` if needed
* **Compatibility**: Prefer the full `mcp__kimi-browser__*` tool names in production scripts — short names may evolve.
