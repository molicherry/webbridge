import json
import logging
import os
import sqlite3
import threading
import time

_log = logging.getLogger("kimi-webbridge-mcp.session_tracker")

_DB_PATH = os.environ.get("DB_PATH", "/home/chrome/data/call_records.db")
_LOCK = threading.Lock()

_URL_SESSION_MAP: dict[str, dict] = {}


def _ensure_table() -> None:
    with _LOCK:
        db = sqlite3.connect(_DB_PATH)
        db.execute(
            "CREATE TABLE IF NOT EXISTS tab_sessions ("
            "  url TEXT PRIMARY KEY,"
            "  session_id TEXT NOT NULL,"
            "  group_title TEXT NOT NULL DEFAULT '',"
            "  key_alias TEXT NOT NULL DEFAULT '',"
            "  recorded_at REAL NOT NULL"
            ")"
        )
        db.commit()
        try:
            db.execute("ALTER TABLE tab_sessions ADD COLUMN key_alias TEXT NOT NULL DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        db.close()


def _load_from_db() -> None:
    with _LOCK:
        db = sqlite3.connect(_DB_PATH)
        rows = db.execute("SELECT url, session_id, group_title, key_alias, recorded_at FROM tab_sessions").fetchall()
        db.close()
        _URL_SESSION_MAP.clear()
        for url, sid, group_title, key_alias, recorded_at in rows:
            _URL_SESSION_MAP[url] = {
                "session_id": sid,
                "group_title": group_title,
                "key_alias": key_alias,
                "recorded_at": recorded_at,
            }
    _log.info("Loaded %d tab session mappings from DB", len(_URL_SESSION_MAP))


def record(url: str, session_id: str, group_title: str = "", title: str = "", key_alias: str = "") -> None:
    if not session_id:
        return
    normalized = url.rstrip("/").lower()
    entry = {
        "session_id": session_id,
        "group_title": group_title or f"agent:{session_id}",
        "title": title,
        "key_alias": key_alias,
        "recorded_at": time.time(),
    }
    _URL_SESSION_MAP[normalized] = entry
    try:
        with _LOCK:
            db = sqlite3.connect(_DB_PATH)
            db.execute(
                "INSERT OR REPLACE INTO tab_sessions (url, session_id, group_title, key_alias, recorded_at) VALUES (?,?,?,?,?)",
                (normalized, session_id, group_title or f"agent:{session_id}", key_alias, time.time()),
            )
            db.commit()
            db.close()
    except Exception as e:
        _log.warning("Failed to persist tab session: %s", e)


def remove(url: str) -> None:
    normalized = url.rstrip("/").lower()
    _URL_SESSION_MAP.pop(normalized, None)
    try:
        with _LOCK:
            db = sqlite3.connect(_DB_PATH)
            db.execute("DELETE FROM tab_sessions WHERE url = ?", (normalized,))
            db.commit()
            db.close()
    except Exception as e:
        _log.warning("Failed to remove tab session from DB: %s", e)


def get_session(url: str) -> dict | None:
    normalized = url.rstrip("/").lower()
    return _URL_SESSION_MAP.get(normalized)


def clear_session(session_id: str) -> None:
    to_remove = [u for u, i in _URL_SESSION_MAP.items() if i["session_id"] == session_id]
    for url in to_remove:
        del _URL_SESSION_MAP[url]
    try:
        with _LOCK:
            db = sqlite3.connect(_DB_PATH)
            db.execute("DELETE FROM tab_sessions WHERE session_id = ?", (session_id,))
            db.commit()
            db.close()
    except Exception as e:
        _log.warning("Failed to clear tab sessions from DB: %s", e)


# Initialize on module load
_ensure_table()
_load_from_db()
