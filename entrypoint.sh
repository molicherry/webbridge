#!/bin/bash
set -e

# ── Configuration ──────────────────────────────────────────────────────

CHROME_USER_DATA="${CHROME_USER_DATA:-/home/chrome/data}"
CHROME_EXTENSION="${CHROME_EXTENSION:-/home/chrome/extensions/kimi-webbridge}"
CDP_PORT="${CDP_PORT:-9222}"
DAEMON_PORT="${DAEMON_PORT:-10086}"
MCP_PORT="${MCP_PORT:-8000}"

export MCP_HOST="${MCP_HOST:-0.0.0.0}"
export MCP_PORT
export DAEMON_URL="http://127.0.0.1:${DAEMON_PORT}"

# ── Cleanup ────────────────────────────────────────────────────────────

cleanup() {
    echo "[entrypoint] Shutting down..."
    kill $MONITOR_PID $MCP_PID $DAEMON_PID $CHROME_PID 2>/dev/null
    wait 2>/dev/null
    echo "[entrypoint] Shutdown complete."
}
trap cleanup EXIT SIGTERM SIGINT

# ── Chrome ─────────────────────────────────────────────────────────────

echo "[entrypoint] Starting Chrome..."
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
echo "[entrypoint] Chrome PID: ${CHROME_PID}"

# ── Wait for Chrome CDP ────────────────────────────────────────────────

echo "[entrypoint] Waiting for Chrome CDP..."
for i in $(seq 1 30); do
    if curl -s "http://127.0.0.1:${CDP_PORT}/json/version" > /dev/null 2>&1; then
        echo "[entrypoint] Chrome CDP ready."
        break
    fi
    if ! kill -0 ${CHROME_PID} 2>/dev/null; then
        echo "[entrypoint] Chrome exited unexpectedly." >&2
        exit 1
    fi
    sleep 1
done

# ── Kimi WebBridge Daemon ──────────────────────────────────────────────

echo "[entrypoint] Starting kimi-webbridge daemon..."
~/.kimi-webbridge/bin/kimi-webbridge start &
DAEMON_PID=$!
echo "[entrypoint] Daemon PID: ${DAEMON_PID}"

# Wait for daemon to be ready
for i in $(seq 1 15); do
    if curl -s "http://127.0.0.1:${DAEMON_PORT}/status" > /dev/null 2>&1; then
        echo "[entrypoint] Daemon ready."
        break
    fi
    if ! kill -0 ${DAEMON_PID} 2>/dev/null; then
        echo "[entrypoint] Daemon exited unexpectedly." >&2
        exit 1
    fi
    sleep 1
done

# ── Health Monitor (self-healing) ──────────────────────────────────────

(
    while true; do
        sleep 10

        if ! kill -0 ${CHROME_PID} 2>/dev/null; then
            echo "[monitor] Chrome process died — exiting for Docker restart." >&2
            kill $$ 2>/dev/null
            exit 1
        fi

        if ! curl -s "http://127.0.0.1:${CDP_PORT}/json/version" > /dev/null 2>&1; then
            echo "[monitor] Chrome CDP unresponsive — exiting for Docker restart." >&2
            kill $$ 2>/dev/null
            exit 1
        fi

        if ! kill -0 ${DAEMON_PID} 2>/dev/null; then
            if [ ${daemon_restarts} -ge 5 ]; then
                echo "[monitor] Daemon restart limit reached — exiting for Docker restart." >&2
                kill $$ 2>/dev/null
                exit 1
            fi
            echo "[monitor] Daemon died — restarting (attempt $((daemon_restarts + 1)))..." >&2
            ~/.kimi-webbridge/bin/kimi-webbridge start &
            DAEMON_PID=$!
            daemon_restarts=$((daemon_restarts + 1))
        fi

        if ! curl -s "http://127.0.0.1:${DAEMON_PORT}/status" > /dev/null 2>&1; then
            if [ ${daemon_restarts} -ge 5 ]; then
                echo "[monitor] Daemon restart limit reached — exiting for Docker restart." >&2
                kill $$ 2>/dev/null
                exit 1
            fi
            echo "[monitor] Daemon unresponsive — restarting..." >&2
            kill ${DAEMON_PID} 2>/dev/null || true
            sleep 2
            ~/.kimi-webbridge/bin/kimi-webbridge start &
            DAEMON_PID=$!
            daemon_restarts=$((daemon_restarts + 1))
        fi

        # Reset counter if daemon healthy for a while
        if [ ${daemon_restarts} -gt 0 ] && curl -s "http://127.0.0.1:${DAEMON_PORT}/status" > /dev/null 2>&1; then
            daemon_restarts=0
        fi
    done
) &
MONITOR_PID=$!

# ── MCP Server (foreground via bash, not exec, so trap fires on SIGTERM) ──

echo "[entrypoint] Starting MCP server on 0.0.0.0:${MCP_PORT}..."
python -m src.mcp_server.server &
MCP_PID=$!
wait ${MCP_PID}
