# Kimi Browser — Remote Browser Control via MCP

You have access to a **remote Chromium browser** running in a Docker container, controlled via MCP. It has full web browsing capabilities with persistent cookies and session state.

## Architecture

```
You (Claude Code) ──MCP──▶ MCP Server (:8000) ──▶ Daemon (:10086) ──WebSocket──▶ Chromium + Kimi Extension
```

The browser is real Chromium with Xvfb virtual display. It shares the same profile across sessions — cookies, localStorage, and cache are **all shared**.

## Core Workflow

For any web interaction task, follow this pattern:

```
1. navigate(url, session_id="my-task")   → open page in a named tab group
2. snapshot(session_id="my-task")        → get accessibility tree with @e refs
3. click / fill / mouse_click            → interact using @e refs from snapshot
4. screenshot(session_id="my-task")      → visually verify (optional)
5. close_session / close_tab             → clean up when done
```

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
6. **Browser state is persistent** — Cookies and session data survive container restarts (stored in Docker volume).
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
