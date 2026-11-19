"""Server-side access control for admin endpoints."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, Request

from app.services.auth import SessionInfo

SESSION_COOKIE = "dy_admin_session"
CSRF_COOKIE = "dy_admin_csrf"
CSRF_HEADER = "x-csrf-token"


def _err(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def require_db(request: Request):
    st = request.app.state
    if st.auth is None or not st.db.is_migrated():
        raise _err(503, "database_unavailable", "The administration database is not available.")
    return st


def require_admin(request: Request) -> SessionInfo:
    st = require_db(request)
    info = st.auth.validate_session(request.cookies.get(SESSION_COOKIE))
    if info is None:
        raise _err(401, "not_authenticated", "Please sign in as an administrator.")
    return info


def require_csrf(request: Request, info: SessionInfo) -> None:
    if not request.app.state.auth.check_csrf(info, request.headers.get(CSRF_HEADER)):
        raise _err(403, "csrf_failed", "Security check failed. Please reload the page and try again.")


def check_origin(request: Request) -> None:
    """Reject cross-site POSTs (login CSRF). Browsers always send Origin on POST."""
    origin = request.headers.get("origin")
    if origin is None:
        if request.headers.get("sec-fetch-site") in ("cross-site",):
            raise _err(403, "bad_origin", "Request origin not allowed.")
        return  # non-browser clients (CLI/tests)
    allowed = {o.rstrip("/") for o in request.app.state.settings.admin_allowed_origins}
    parsed = urlparse(origin)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if request.app.state.settings.environment == "production":
        if origin.rstrip("/") not in allowed:
            raise _err(403, "bad_origin", "Request origin not allowed.")
        return
    if origin.rstrip("/") not in allowed and parsed.netloc != host:
        raise _err(403, "bad_origin", "Request origin not allowed.")
