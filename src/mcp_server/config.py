"""Centralized configuration from environment variables."""

import os

# ── Admin Panel ─────────────────────────────────────────────────────────

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
"""Admin panel password. Empty string disables admin panel entirely."""

ADMIN_SESSION_SECRET = os.environ.get(
    "ADMIN_SESSION_SECRET",
    os.urandom(32).hex(),
)
"""HMAC secret for signing admin session cookies. Generated on startup if not set."""

SESSION_MAX_AGE = int(os.environ.get("SESSION_MAX_AGE", "86400"))
"""Admin session max age in seconds (default 24 hours)."""

# ── API Keys ────────────────────────────────────────────────────────────

MCP_API_KEY = os.environ.get("MCP_API_KEY", "")
"""MCP API key for client authentication (existing)."""

EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")
"""External API key configurable via admin panel. Default from env var."""

# ── Database ────────────────────────────────────────────────────────────

DB_PATH = os.environ.get("DB_PATH", "/home/chrome/data/call_records.db")
"""SQLite database path for call records and admin config."""

CALL_RECORD_RETENTION_DAYS = int(os.environ.get("CALL_RECORD_RETENTION_DAYS", "30"))
"""Number of days to retain call records before cleanup."""

# ── Chrome CDP ──────────────────────────────────────────────────────────

CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

# ── Admin Panel Gate ────────────────────────────────────────────────────

ADMIN_ENABLED = bool(ADMIN_PASSWORD)
"""Admin panel is enabled only when ADMIN_PASSWORD is set."""
