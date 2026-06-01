"""SQLite-based call record storage and admin key-value config."""

import json
import logging
import os
import sqlite3
import threading
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from .config import DB_PATH, CALL_RECORD_RETENTION_DAYS

logger = logging.getLogger("kimi-webbridge-mcp.call-logger")

# ── Request context (set by middleware) ──────────────────────────────────

request_source: ContextVar[str] = ContextVar("request_source", default="unknown")
"""API key prefix or 'internal'."""
request_client_ip: ContextVar[str] = ContextVar("request_client_ip", default="")
request_user_agent: ContextVar[str] = ContextVar("request_user_agent", default="")

# ── Connection management ───────────────────────────────────────────────

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Get thread-local SQLite connection."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def init_db() -> None:
    """Create tables and indexes if they don't exist."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS call_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL DEFAULT (datetime('now')),
            source          TEXT    NOT NULL,
            method          TEXT    NOT NULL,
            params          TEXT    NOT NULL DEFAULT '{}',
            result_status   TEXT    NOT NULL DEFAULT 'unknown',
            duration_ms     INTEGER,
            client_ip       TEXT    DEFAULT '',
            user_agent      TEXT    DEFAULT '',
            error_msg       TEXT    DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_call_timestamp ON call_records(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_call_method    ON call_records(method);
        CREATE INDEX IF NOT EXISTS idx_call_source    ON call_records(source);
        CREATE INDEX IF NOT EXISTS idx_call_status    ON call_records(result_status);

        CREATE TABLE IF NOT EXISTS admin_config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        );
    """)
    conn.commit()
    logger.info("Database initialized at %s", DB_PATH)


# ── Call Recording ──────────────────────────────────────────────────────

def log_call(
    source: str,
    method: str,
    params: dict | None = None,
    result_status: str = "unknown",
    duration_ms: int | None = None,
    client_ip: str = "",
    user_agent: str = "",
    error_msg: str = "",
) -> None:
    """Record a tool call. Fire-and-forget — never raise."""
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO call_records
               (source, method, params, result_status, duration_ms, client_ip, user_agent, error_msg)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source[:64],
                method[:128],
                json.dumps(params or {}, ensure_ascii=False),
                result_status,
                duration_ms,
                client_ip[:64],
                user_agent[:256],
                error_msg[:1024],
            ),
        )
        conn.commit()
    except Exception:
        logger.exception("Failed to log call record")


def get_records(
    page: int = 1,
    per_page: int = 20,
    method: str = "",
    source: str = "",
    date_from: str = "",
    date_to: str = "",
    status: str = "",
) -> dict:
    """Retrieve paginated call records with optional filters.

    Returns dict with keys: records, total, page, per_page, total_pages.
    """
    conn = _get_conn()

    where_clauses: list[str] = []
    params: list = []

    if method:
        where_clauses.append("method = ?")
        params.append(method)
    if source:
        where_clauses.append("source LIKE ?")
        params.append(f"{source}%")
    if date_from:
        where_clauses.append("timestamp >= ?")
        params.append(date_from)
    if date_to:
        where_clauses.append("timestamp <= ?")
        params.append(date_to)
    if status:
        where_clauses.append("result_status = ?")
        params.append(status)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # Count total
    row = conn.execute(f"SELECT COUNT(*) as cnt FROM call_records WHERE {where_sql}", params).fetchone()
    total = row["cnt"] if row else 0
    total_pages = max(1, (total + per_page - 1) // per_page)
    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT * FROM call_records WHERE {where_sql} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params + [per_page, offset],
    ).fetchall()

    return {
        "records": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


def get_stats() -> dict:
    """Get aggregate statistics about call records."""
    conn = _get_conn()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

    total = conn.execute("SELECT COUNT(*) as cnt FROM call_records").fetchone()["cnt"]
    success = conn.execute("SELECT COUNT(*) as cnt FROM call_records WHERE result_status = 'success'").fetchone()["cnt"]
    error = conn.execute("SELECT COUNT(*) as cnt FROM call_records WHERE result_status = 'error'").fetchone()["cnt"]
    today = conn.execute("SELECT COUNT(*) as cnt FROM call_records WHERE timestamp >= ?", (today_start,)).fetchone()["cnt"]

    sources = [
        dict(r)
        for r in conn.execute(
            "SELECT source, COUNT(*) as cnt FROM call_records GROUP BY source ORDER BY cnt DESC LIMIT 10"
        ).fetchall()
    ]

    methods = [
        dict(r)
        for r in conn.execute(
            "SELECT method, COUNT(*) as cnt FROM call_records GROUP BY method ORDER BY cnt DESC"
        ).fetchall()
    ]

    avg_duration = conn.execute(
        "SELECT COALESCE(AVG(duration_ms), 0) as avg_ms FROM call_records WHERE duration_ms IS NOT NULL"
    ).fetchone()["avg_ms"]

    return {
        "total_calls": total,
        "success_count": success,
        "error_count": error,
        "today_calls": today,
        "success_rate": round(success / total * 100, 1) if total > 0 else 0.0,
        "top_sources": sources,
        "top_methods": methods,
        "avg_duration_ms": round(avg_duration, 1),
    }


def cleanup_old_records(days: int | None = None) -> int:
    """Delete records older than the specified number of days. Returns count deleted."""
    if days is None:
        days = CALL_RECORD_RETENTION_DAYS
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    try:
        conn = _get_conn()
        cursor = conn.execute("DELETE FROM call_records WHERE timestamp < ?", (cutoff,))
        conn.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info("Cleaned up %d old call records (older than %d days)", deleted, days)
        return deleted
    except Exception:
        logger.exception("Failed to cleanup old records")
        return 0


# ── Admin Config (key-value store) ──────────────────────────────────────

def get_config(key: str) -> str:
    """Get a config value by key. Returns empty string if not found."""
    conn = _get_conn()
    row = conn.execute("SELECT value FROM admin_config WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def set_config(key: str, value: str) -> None:
    """Set or update a config value."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO admin_config (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
