"""Admin session authentication middleware and helpers."""

import hashlib
import hmac
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from ..config import ADMIN_PASSWORD, ADMIN_SESSION_SECRET, SESSION_MAX_AGE

COOKIE_NAME = "admin_session"
PUBLIC_PATHS = {"/admin/login", "/admin/static/"}
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 5

_rate_store: dict[str, list[float]] = {}


def _check_rate_limit(client_ip: str) -> bool:
    now = time.monotonic()
    attempts = _rate_store.get(client_ip, [])
    attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
    _rate_store[client_ip] = attempts
    if len(attempts) >= RATE_LIMIT_MAX:
        return False
    _rate_store[client_ip].append(now)
    return True


def create_session_token() -> str:
    payload = f"admin:{int(time.time()) + SESSION_MAX_AGE}"
    sig = hmac.new(
        ADMIN_SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}:{sig}"


def validate_session_token(token: str) -> bool:
    parts = token.rsplit(":", 1)
    if len(parts) != 2:
        return False
    payload, sig = parts
    expected_sig = hmac.new(
        ADMIN_SESSION_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False
    payload_parts = payload.split(":", 1)
    if len(payload_parts) != 2 or payload_parts[0] != "admin":
        return False
    try:
        expiry = int(payload_parts[1])
    except (ValueError, IndexError):
        return False
    return time.time() < expiry


class AdminAuthMiddleware(BaseHTTPMiddleware):
    """Validate admin session cookie for /admin/* routes.

    Skips /admin/login and /admin/static/.
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        path = request.url.path

        if not path.startswith("/admin"):
            return await call_next(request)

        if path in PUBLIC_PATHS or path.startswith("/admin/static/"):
            return await call_next(request)

        token = request.cookies.get(COOKIE_NAME, "")
        if validate_session_token(token):
            return await call_next(request)

        if path.startswith("/admin/api/"):
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        return RedirectResponse(url="/admin/login", status_code=302)


def verify_password(password: str) -> bool:
    return hmac.compare_digest(password, ADMIN_PASSWORD)
