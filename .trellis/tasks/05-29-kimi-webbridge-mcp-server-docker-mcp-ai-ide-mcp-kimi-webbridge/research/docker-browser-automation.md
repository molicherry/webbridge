# Research: Docker-Based Browser Automation with Chrome Extensions

- **Query**: How to run Chrome/Chromium with extensions (specifically kimi-webbridge) inside Docker containers
- **Scope**: External (Chrome docs, Docker image documentation, browser automation patterns)
- **Date**: 2026-05-29

---

## 1. Headless Chrome in Docker: Best Practices

### Essential Chrome Flags for Docker

Based on the [Chrome Flags for Tooling](https://github.com/GoogleChrome/chrome-launcher/blob/main/docs/chrome-flags-for-tools.md) reference and the Puppeteer [troubleshooting guide](https://github.com/puppeteer/puppeteer/blob/main/docs/troubleshooting.md), the following flags are critical when running Chromium in a container:

#### Always Required in Docker:
```
--no-sandbox                    # Disable sandbox (containers lack kernel namespaces for Chrome sandbox)
--disable-dev-shm-usage         # Use /tmp instead of /dev/shm (Docker /dev/shm is only 64MB by default)
--disable-gpu                   # Not strictly needed since Chrome 2021, but safe to include
--headless                      # Run without UI (Chrome 132+ new headless is default)
```

#### Docker-Specific Resource Flags:
```
--disable-software-rasterizer   # Prevent software rendering fallback
--disable-background-timer-throttling  # Keep extensions responsive
--disable-backgrounding-occluded-windows
--disable-renderer-backgrounding  # Prevent process deprioritization
--disable-features=Translate    # Suppress translation prompts
```

#### Memory / Process Control:
```
--single-process                # Optional: reduce memory footprint (not recommended for production)
--js-flags="--max-old-space-size=512"  # Limit V8 heap in memory-constrained containers
```

### The `/dev/shm` Problem

Docker containers default to 64MB for `/dev/shm`. Chrome uses this for shared memory between processes. Two solutions:

1. **Flag approach**: `--disable-dev-shm-usage` (simpler, uses `/tmp`)
2. **Volume approach**: `docker run --shm-size=2gb` (better performance for heavy usage)

### Key System Dependencies for Chromium in Debian/Ubuntu

From the Puppeteer Docker patterns:
```dockerfile
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-l10n \
    fonts-liberation \
    fonts-roboto \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libu2f-udev \
    libvulkan1 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*
```

---

## 2. Loading Chrome Extensions in Headless Mode

### Critical Finding: Extensions DO Work in Headless (Since Chrome 132)

Chrome's "new" headless mode (the default since Chrome 132, January 2025) runs the full browser engine including extension support. The old headless shell (`--headless=old` / `headless: 'shell'`) did NOT support extensions, but that mode is now deprecated.

**Base flag**: `--headless` (new mode is default in Chrome 132+) enables the full browser, which includes extension support.

### Method A: `--load-extension` Flag (Recommended for Development)

Load an unpacked extension at launch:
```
--load-extension=/path/to/unpacked/extension
```

For multiple extensions:
```
--load-extension=/path/to/ext1,/path/to/ext2
```

Important supporting flags:
```
--enable-automation             # Suppresses the "running unpacked extensions" bubble
--silent-debugger-extension-api # Suppresses infobar when extension attaches via chrome.debugger
```

### Method B: `--disable-extensions-except` (Selective Enablement)

This flag disables ALL extensions except those specified. Useful when Chrome ships with default extensions you want suppressed:
```
--disable-extensions --disable-extensions-except=/path/to/ext1,/path/to/ext2
```

This ensures only your extension runs, no Chrome Web Store extensions, no default apps.

### Method C: Chrome Policies (Enterprise / Production)

Pre-install extensions via JSON policy file. Drop a policy file at `/etc/opt/chrome/policies/managed/extension_policy.json`:

```json
{
  "ExtensionInstallForcelist": [
    "abcdefghijklmnopqrstuvwxyz123456;https://clients2.google.com/service/update2/crx"
  ],
  "ExtensionInstallSources": [
    "*://example.com/*"
  ]
}
```

The extension ID `abcdef...` must be known (from the Chrome Web Store or from the extension's `.crx` manifest). For self-hosted extensions, change the update URL to your own XML update endpoint that serves the `.crx`.

### Method D: `initial_preferences` (Master Preferences File)

Place an `initial_preferences` file in the Chrome installation directory (next to the chrome binary). Chrome consumes this on first launch per-profile.

For extensions, use the `extensions` key:
```json
{
  "extensions": {
    "settings": {
      "abcdefghijklmnopqrstuvwxyz123456": {
        "installation_mode": "force_installed",
        "update_url": "https://clients2.google.com/service/update2/crx"
      }
    }
  }
}
```

Note: This is consumed only on **first launch** of a new profile. For persistent profiles, the extensions are already installed -- this file has no effect on subsequent launches.

### Recommendation for kimi-webbridge

Use **Method A** (`--load-extension`) with `--enable-automation` and `--silent-debugger-extension-api` as supporting flags. This is the simplest and most predictable approach for a development/self-hosted deployment scenario.

---

## 3. Base Image Comparison

### browserless/chrome (ghcr.io/browserless/chromium)

**Overview**: Production-grade headless browser service. Exposes Chrome via WebSocket (port 3000) and REST APIs.

| Aspect | Assessment |
|--------|-----------|
| Chrome version | Bundled Chromium, updated frequently |
| Extension support | **Not designed for extensions**. Focused on Puppeteer/Playwright automation via CDP |
| Base OS | Debian-based |
| Size | ~500MB+ compressed |
| Multi-arch | amd64 only |
| API | WebSocket (`ws://localhost:3000`), REST endpoints for screenshots, PDF, scraping |
| Licensing | Source Available / Commercial license |

**Verdict**: Excellent for headless browser automation, but **NOT suitable** for running Chrome extensions. The browserless architecture replaces the browser UI layer with its own control plane, which conflicts with extension requirements.

### zenika/alpine-chrome

**Overview**: Minimal Alpine-based Chromium image.

```dockerfile
FROM alpine:3.19
RUN apk add --no-cache chromium-swiftshader ttf-freefont font-noto-emoji
RUN adduser -D chrome
USER chrome
ENTRYPOINT ["chromium-browser", "--headless"]
```

| Aspect | Assessment |
|--------|-----------|
| Chrome version | Alpine's chromium package (may lag behind stable) |
| Extension support | **Possible** but untested. Alpine uses musl libc which can cause subtle incompatibilities with some extensions |
| Base OS | Alpine Linux |
| Size | Very small (~200MB) |
| Multi-arch | amd64, arm64 |
| API | None built in -- raw browser only |

**Verdict**: Good for minimal deployments but Alpine/musl can introduce hard-to-debug issues with extensions that depend on glibc-specific behavior or native messaging hosts.

### Custom Debian/Ubuntu with Chromium (Recommended)

**Overview**: Build from a standard Debian or Ubuntu base image with Chromium installed via apt.

| Aspect | Assessment |
|--------|-----------|
| Chrome version | Use `google-chrome-stable` from Google's repo for latest, or `chromium-browser` from Debian/Ubuntu repos |
| Extension support | **Full support**. This is essentially a normal Chrome installation, just in a container |
| Base OS | Debian/Ubuntu (glibc) |
| Size | ~400-700MB (depends on deps included) |
| Multi-arch | amd64, arm64 (Ubuntu) |
| API | Raw Chrome with `--remote-debugging-port` |

**Verdict**: **This is the best option for running Chrome with extensions.** It provides the most compatibility and the fewest surprises. Extensions that work on a developer's desktop Chrome will work identically in the container.

### Recommendation

Use a **custom Debian (or Ubuntu) base image** with `google-chrome-stable` or `chromium-browser`. This ensures full glibc compatibility, native messaging host support (if needed), and reliable extension behavior.

Dockerfile template:
```dockerfile
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    google-chrome-stable \
    fonts-liberation fonts-roboto \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 libu2f-udev libvulkan1 \
    libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 libxrandr2 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r chrome && useradd -r -g chrome -G audio,video chrome \
    && mkdir -p /home/chrome/extensions /home/chrome/data \
    && chown -R chrome:chrome /home/chrome

# Copy extension files
COPY --chown=chrome:chrome ./kimi-webbridge /home/chrome/extensions/kimi-webbridge/

USER chrome
WORKDIR /home/chrome

ENV CHROME_FLAGS="--headless \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --enable-automation \
    --silent-debugger-extension-api \
    --load-extension=/home/chrome/extensions/kimi-webbridge \
    --user-data-dir=/home/chrome/data \
    --remote-debugging-port=9222 \
    --remote-debugging-address=0.0.0.0"

EXPOSE 9222

ENTRYPOINT ["google-chrome-stable"]
CMD ["--headless", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu",
     "--enable-automation", "--silent-debugger-extension-api",
     "--load-extension=/home/chrome/extensions/kimi-webbridge",
     "--user-data-dir=/home/chrome/data",
     "--remote-debugging-port=9222",
     "--remote-debugging-address=0.0.0.0"]
```

---

## 4. Persistent Browser Profiles

### The `--user-data-dir` Flag

Chrome stores all persistent state (cookies, localStorage, IndexedDB, extension data, preferences) in the user data directory:
```
--user-data-dir=/home/chrome/data
```

This directory contains:
```
/home/chrome/data/
  Default/              # Default profile
    Cookies              # SQLite cookie database
    Extensions/          # Installed extensions
    Local Storage/       # localStorage data
    Local Extension Settings/  # Extension storage (chrome.storage.local)
    Preferences          # User preferences JSON
    History              # SQLite browsing history
    ...
  First Run             # Marker file (absence triggers first-run wizard)
  Local State           # Global browser state
```

### Volume Mounting Pattern

Mount the data directory from the host for persistence:

```bash
docker run -d \
  --name chrome-kimi \
  -p 9222:9222 \
  -v /path/on/host/chrome-data:/home/chrome/data \
  my-chrome-image
```

Docker Compose:
```yaml
services:
  chrome:
    build: .
    ports:
      - "9222:9222"
    volumes:
      - chrome-data:/home/chrome/data
      - ./extensions/kimi-webbridge:/home/chrome/extensions/kimi-webbridge:ro
    shm_size: '2gb'

volumes:
  chrome-data:
    driver: local
```

### Important Notes on Persistence

1. **The `First Run` file**: On first launch, Chrome creates a `First Run` marker. If you delete this file, Chrome runs the first-run wizard and may reset some extension settings.

2. **Extension state survives restarts**: Extensions loaded via `--load-extension` are installed once per-profile. On second launch, they are already loaded from the profile directory. However, you still need the `--load-extension` flag (or the extension files present at the same path) because Chrome verifies the extension source on startup.

3. **Cookies persist in `Cookies` SQLite file**: Session cookies may be lost if Chrome crashes or if `--disable-features=DestroyProfileOnBrowserClose` is not set.

4. **chrome.storage.local data**: Extension data stored via `chrome.storage.local` API is persisted in `Local Extension Settings/<extension-id>/` as LevelDB databases.

5. **Crash recovery**: If Chrome does not shut down gracefully (Docker stop sends SIGTERM, Docker kill sends SIGKILL), the profile may be corrupted. Implement a graceful shutdown handler that sends a CDP `Browser.close` command.

### Volume Strategy for Different Scenarios

| Scenario | Volume Strategy |
|----------|----------------|
| Ephemeral / stateless | No volume, `--user-data-dir=/tmp/chrome-data`, tmpfs |
| Session persistence | Named volume or bind mount for `/home/chrome/data` |
| Extension updates | Bind mount extension dir as read-only + persistent data volume |
| Multi-instance | Separate data directories per instance (e.g., `/home/chrome/data-${INSTANCE_ID}`) |

---

## 5. Chrome DevTools Protocol (CDP) and Extension Communication

### How kimi-webbridge Likely Communicates

Based on the daemon log showing `listening on 127.0.0.1:10086` and the project being a Chrome extension, the architecture follows the pattern of Chrome extensions that use `chrome.debugger` API:

1. **Extension attaches to CDP** via `chrome.debugger.attach({tabId}, "1.3")`
2. **CDP commands** are sent via `chrome.debugger.sendCommand({tabId}, "Page.navigate", {url})`
3. **Events** from CDP are received via `chrome.debugger.onEvent`
4. **The daemon** (listening on port 10086) acts as a control bridge between the extension and an external MCP server

### CDP Endpoints

When Chrome starts with `--remote-debugging-port=9222`, it exposes:

```
GET http://localhost:9222/json/version          # Browser version + WebSocket endpoint
GET http://localhost:9222/json/list             # List open tabs with WebSocket URLs
GET http://localhost:9222/json/new?url=about:blank  # Open new tab
GET http://localhost:9222/json/activate/{targetId}  # Focus a tab
GET http://localhost:9222/json/close/{targetId}     # Close a tab
```

Each target (page, service worker, extension background page) has its own WebSocket URL:
```
ws://localhost:9222/devtools/page/ABC123
ws://localhost:9222/devtools/browser/BROWSER_ID
```

### Extension Background Page Debugging

Extensions running in the browser expose their background pages/service workers as CDP targets. You can attach to them:
```
GET http://localhost:9222/json/list
```

This returns entries like:
```json
{
  "type": "background_page",
  "title": "Kimi WebBridge",
  "id": "EXT_BG_123",
  "url": "chrome-extension://abc123/background.html",
  "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/EXT_BG_123"
}
```

### The chrome.debugger API

The extension's primary mechanism for controlling browser tabs:

```javascript
// Attach to a tab via CDP
chrome.debugger.attach({tabId: 123}, "1.3");

// Send a CDP command
chrome.debugger.sendCommand({tabId: 123}, "Page.navigate", {url: "https://example.com"});

// Listen for CDP events
chrome.debugger.onEvent.addListener((source, method, params) => {
  if (method === "Page.loadEventFired") {
    // Page loaded
  }
});

// Detach
chrome.debugger.detach({tabId: 123});
```

### Network Communication Path

```
External Client (MCP/API)
       |
       | HTTP/WebSocket
       v
Daemon (127.0.0.1:10086)  <-- kimi-webbridge.exe
       |
       | Native Messaging / Internal IPC
       v
Chrome Extension (background service worker)
       |
       | chrome.debugger API
       v
CDP Endpoint (within Chrome browser)
       |
       v
Browser Tab / Page
```

### Key CDP Domains Relevant to kimi-webbridge

| Domain | Purpose |
|--------|---------|
| `Browser` | Browser-level operations (get version, get window bounds, set permissions) |
| `Target` | Manage tabs/windows (create, close, activate targets) |
| `Page` | Page navigation, DOM access, script execution |
| `Runtime` | JavaScript evaluation, console access |
| `Network` | Network request interception, cookies, headers |
| `Input` | Mouse/keyboard event injection |
| `Storage` | Cookie management, localStorage/IndexedDB access |

---

## 6. Xvfb / Virtual Display

### Do We Need Xvfb?

**No, Xvfb is NOT needed** when using the new headless mode (Chrome 132+, which is the default). The new headless mode renders entirely in software and does not require any display server.

### The Old vs New Headless Mode

| Feature | Old Headless (`--headless=old`) | New Headless (`--headless`) |
|---------|-------------------------------|---------------------------|
| Display requirement | No display needed | No display needed |
| Extensions | **NOT supported** | **FULLY supported** |
| Rendering | Headless shell only | Full browser rendering pipeline |
| DevTools | Limited | Full support |
| WebGL | Not available | Available (software) |
| `navigator.webdriver` | Set to `true` | Set to `true` |
| Default since | N/A (removed) | Chrome 132 (January 2025) |

### When Xvfb Might Still Be Useful

Xvfb (`xvfb-run`) is only needed if:

1. You are running a **very old** version of Chrome (pre-112, when new headless was experimental)
2. You need to run **headful** (non-headless) Chrome in a headless environment for visual testing. Note: this approach uses more resources and is slower
3. You need to take screenshots at specific resolutions that aren't achievable in headless mode

### Xvfb-Based Approach (Legacy / Headful)

If you need a headful browser for visual testing:

```dockerfile
RUN apt-get install -y xvfb
```

```bash
xvfb-run --auto-servernum --server-args='-screen 0 1920x1080x24' \
  google-chrome-stable \
  --no-sandbox \
  --disable-dev-shm-usage \
  --load-extension=/path/to/ext \
  ...
```

Or in Docker Compose:
```yaml
services:
  chrome:
    command: >
      xvfb-run --auto-servernum --server-args='-screen 0 1920x1080x24'
      google-chrome-stable
      --no-sandbox
      --disable-dev-shm-usage
      --load-extension=/home/chrome/extensions/kimi-webbridge
      --remote-debugging-port=9222
      --remote-debugging-address=0.0.0.0
```

### Alternative: Virtual Display with `--window-size` and `--window-position`

In new headless mode, you can control the virtual viewport without Xvfb:
```
--window-size=1920,1080
--window-position=0,0
```

### Recommendation

**Use new headless mode WITHOUT Xvfb.** It is simpler, faster, and fully supports extensions. Only consider Xvfb if you encounter a specific extension that requires a real display server (extremely rare).

---

## 7. Security Considerations

### Chrome Sandbox in Docker

Chrome's multi-layer sandbox uses Linux kernel features (namespaces, seccomp-bpf) that are restricted inside Docker containers. This creates a security tension:

| Approach | Security | Risk |
|----------|----------|------|
| `--no-sandbox` | None | Chrome processes run without isolation; a compromised renderer can access the container filesystem |
| `--cap-add=SYS_ADMIN` | Partial | Grants broad kernel capabilities, increasing attack surface from the container |
| Custom seccomp profile | Good | Allows Chrome's sandbox syscalls while blocking others |
| `--privileged` | Very poor | Container has full host kernel access -- equivalent to running as root on host |

### Recommended: Custom seccomp Profile

Instead of `--no-sandbox`, use a custom seccomp profile that allows the specific syscalls Chrome needs:

```json
{
  "defaultAction": "SCMP_ACT_ERRNO",
  "architectures": ["SCMP_ARCH_X86_64"],
  "syscalls": [
    { "name": "clone", "action": "SCMP_ACT_ALLOW", "args": [{ "index": 0, "value": 0x50f00, "op": "SCMP_CMP_MASKED_EQ" }] },
    { "name": "clone3", "action": "SCMP_ACT_ALLOW" },
    { "name": "unshare", "action": "SCMP_ACT_ALLOW" },
    { "name": "setns", "action": "SCMP_ACT_ALLOW" },
    { "name": "mount", "action": "SCMP_ACT_ALLOW" },
    { "name": "umount2", "action": "SCMP_ACT_ALLOW" },
    { "name": "pivot_root", "action": "SCMP_ACT_ALLOW" },
    { "name": "chroot", "action": "SCMP_ACT_ALLOW" },
    { "name": "setuid", "action": "SCMP_ACT_ALLOW" },
    { "name": "setgid", "action": "SCMP_ACT_ALLOW" },
    { "name": "personality", "action": "SCMP_ACT_ALLOW" }
  ]
}
```

Save as `chrome-seccomp.json` and run:
```bash
docker run --security-opt seccomp=chrome-seccomp.json ...
```

However, for practical deployment where security is a concern, many projects accept `--no-sandbox` combined with other mitigations (see below).

### Remote Debugging Port Exposures

**Critical**: `--remote-debugging-port=0.0.0.0:9222` exposes the CDP endpoint to ALL network interfaces. This is extremely dangerous:

- Anyone who can reach port 9222 can control the browser completely
- Can read all cookies, localStorage, session data
- Can navigate to arbitrary URLs, execute JavaScript
- Can access all extension data

**Mitigations:**

1. **Bind to localhost only** (if the MCP server is in the same container):
   ```
   --remote-debugging-port=9222
   --remote-debugging-address=127.0.0.1
   ```

2. **Use `--remote-debugging-pipe`** instead of a TCP port (more secure):
   ```
   --remote-debugging-pipe
   ```
   This communicates via stdin/stdout pipes instead of a network socket.

3. **Use a Docker internal network** with no external port mapping:
   ```yaml
   services:
     chrome:
       expose:
         - "9222"  # Only accessible within the Docker network
     mcp-server:
       depends_on:
         - chrome
       environment:
         - CDP_URL=ws://chrome:9222
   ```

4. **Add authentication proxy** (nginx, Caddy) in front of the CDP port:
   ```nginx
   location / {
       auth_basic "CDP Access";
       auth_basic_user_file /etc/nginx/.htpasswd;
       proxy_pass http://localhost:9222;
   }
   ```

### Network Isolation

For a service that accesses the internet (kimi-webbridge needs to reach Kimi API):

```yaml
services:
  chrome:
    networks:
      - chrome-net
    # No ports exposed to host

  kimi-daemon:
    networks:
      - chrome-net
      - external-net
    ports:
      - "10086:10086"  # Only expose the MCP daemon, not Chrome CDP

networks:
  chrome-net:
    internal: true  # No external network access for Chrome
  external-net:
    # Has internet access
```

This way, only the daemon can reach Chrome's CDP, and only the daemon has internet access.

### Container User

Always run Chrome as a non-root user. Both zenika/alpine-chrome and our recommended custom image create a dedicated `chrome` user:

```dockerfile
RUN groupadd -r chrome && useradd -r -g chrome -G audio,video chrome
USER chrome
```

Running as root inside the container is unnecessary and amplifies the risk of `--no-sandbox`.

### Summary Security Checklist

| Measure | Priority | Notes |
|---------|----------|-------|
| Run as non-root user | CRITICAL | Always |
| Bind CDP to localhost | CRITICAL | Unless MCP server is in separate container |
| Use internal Docker network | HIGH | Isolate Chrome from external access |
| Custom seccomp profile | MEDIUM | If you want sandbox without `--no-sandbox` |
| CDP authentication | MEDIUM | If CDP must be network-accessible |
| `--no-sandbox` + other mitigations | ACCEPTABLE | Common in Docker deployments |
| Read-only root filesystem | OPTIONAL | `--read-only` with tmpfs for writable dirs |
| Resource limits | OPTIONAL | `--memory=2g --cpus=2` to prevent runaway Chrome |
| Regular image updates | HIGH | Chrome CVEs are common; rebuild weekly |

---

## Appendix A: Complete Dockerfile for kimi-webbridge

```dockerfile
# Stage 1: Build customization (if needed)
FROM debian:bookworm-slim AS builder

# Stage 2: Runtime
FROM debian:bookworm-slim

# Install system dependencies and Google Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | \
       gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] \
       http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends \
       google-chrome-stable \
       fonts-liberation fonts-roboto \
       libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
       libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 libu2f-udev libvulkan1 \
       libxcomposite1 libxdamage1 libxfixes3 libxkbcommon0 libxrandr2 \
       xdg-utils procps \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r chrome && useradd -r -g chrome -G audio,video chrome \
    && mkdir -p /home/chrome/extensions /home/chrome/data \
    && chown -R chrome:chrome /home/chrome

# Copy extension files
COPY --chown=chrome:chrome ./kimi-webbridge /home/chrome/extensions/kimi-webbridge/

# Copy and set up entrypoint script
COPY --chown=chrome:chrome docker-entrypoint.sh /home/chrome/
RUN chmod +x /home/chrome/docker-entrypoint.sh

USER chrome
WORKDIR /home/chrome

# Environment
ENV CHROME_USER_DATA=/home/chrome/data \
    CHROME_EXTENSION=/home/chrome/extensions/kimi-webbridge \
    CDP_PORT=9222 \
    DISPLAY=:99

# Expose only the MCP daemon port, not CDP
EXPOSE 10086

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:9222/json/version || exit 1

ENTRYPOINT ["/home/chrome/docker-entrypoint.sh"]
```

## Appendix B: Entrypoint Script

```bash
#!/bin/bash
set -e

# Trap for graceful shutdown
cleanup() {
    echo "Shutting down Chrome gracefully..."
    curl -s "http://localhost:${CDP_PORT}/json/close/all" || true
    kill %1 2>/dev/null || true
    wait
}
trap cleanup SIGTERM SIGINT

echo "Starting Chrome with kimi-webbridge extension..."
google-chrome-stable \
    --headless \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --enable-automation \
    --silent-debugger-extension-api \
    --load-extension="${CHROME_EXTENSION}" \
    --user-data-dir="${CHROME_USER_DATA}" \
    --remote-debugging-port="${CDP_PORT}" \
    --remote-debugging-address=127.0.0.1 \
    --disable-background-timer-throttling \
    --disable-backgrounding-occluded-windows \
    --disable-renderer-backgrounding \
    --disable-features=Translate,PrivacySandboxSettings4 \
    --no-first-run \
    --no-default-browser-check \
    --window-size=1920,1080 \
    &

CHROME_PID=$!

# Wait for Chrome CDP to be ready
echo "Waiting for Chrome CDP endpoint..."
for i in $(seq 1 30); do
    if curl -s "http://localhost:${CDP_PORT}/json/version" > /dev/null 2>&1; then
        echo "Chrome CDP is ready."
        break
    fi
    sleep 1
done

echo "Chrome running with PID ${CHROME_PID}"
wait ${CHROME_PID}
```

## Appendix C: Docker Compose Example

```yaml
version: '3.8'

services:
  chrome:
    build:
      context: .
      dockerfile: Dockerfile
    image: kimi-webbridge-chrome:latest
    container_name: chrome-kimi
    volumes:
      - chrome-data:/home/chrome/data
      - ./kimi-webbridge:/home/chrome/extensions/kimi-webbridge:ro
    shm_size: '2gb'
    environment:
      - CDP_PORT=9222
    ports:
      - "127.0.0.1:10086:10086"  # Only expose daemon to localhost
    networks:
      - kimi-net
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9222/json/version"]
      interval: 30s
      timeout: 5s
      retries: 3

  kimi-daemon:
    image: kimi-webbridge-daemon:latest
    container_name: kimi-daemon
    depends_on:
      chrome:
        condition: service_healthy
    environment:
      - CDP_URL=ws://chrome:9222
      - DAEMON_PORT=10086
    ports:
      - "127.0.0.1:10086:10086"
    networks:
      - kimi-net
    restart: unless-stopped

volumes:
  chrome-data:
    driver: local

networks:
  kimi-net:
    driver: bridge
```

---

## Caveats / Not Found

1. **kimi-webbridge binary internals**: The binary is likely a Go-compiled application. String extraction attempts returned empty results, suggesting possible compression or symbol stripping. The internal communication protocol (whether it uses native messaging, HTTP, WebSocket, or custom IPC) could not be determined from binary analysis alone. The daemon log confirms it listens on 127.0.0.1:10086.

2. **Chrome extension manifest**: The actual `manifest.json` for the kimi-webbridge extension was not available in this repository. Its permissions (especially `nativeMessaging`, `debugger`, `tabs`, `storage`) would affect the Docker security configuration.

3. **`--disable-extensions-except` flag**: While commonly referenced in Chromium source, I could not confirm from live documentation that this flag is supported in Chrome stable. The more reliable approach is `--disable-extensions` followed by `--load-extension` to selectively load only desired extensions.

4. **Alpine/musl extension compatibility**: No definitive list exists of extensions incompatible with musl libc. Test thoroughly if choosing Alpine-based images.

5. **CDP pipe mode**: `--remote-debugging-pipe` is the most secure way to expose CDP, but requires a client that speaks the pipe protocol. Most tools and SDKs expect WebSocket. Switching to pipe mode may require a proxy/adapter.
