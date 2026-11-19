"""Administrator authentication and analytics endpoints (all analytics require a valid session)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app.security.admin_auth import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    _err,
    check_origin,
    require_admin,
    require_csrf,
    require_db,
)
from app.security.rate_limit import client_key
from app.services.auth import SessionInfo

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
ALLOWED_DAYS = (7, 30)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SessionResponse(BaseModel):
    email: str
    expires_at: str
    csrf_token: str | None = None


def _set_cookies(response: Response, request: Request, token: str, csrf: str, max_age: int) -> None:
    secure = request.app.state.settings.secure_cookies
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=secure, samesite="strict", path="/")
    # Readable by the page so it can echo it in the X-CSRF-Token header (double-submit + server-side hash check).
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=secure, samesite="strict", path="/")


def _clear_cookies(response: Response, request: Request) -> None:
    secure = request.app.state.settings.secure_cookies
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=secure, httponly=name == SESSION_COOKIE, samesite="strict")


@router.post("/auth/login", response_model=SessionResponse)
async def login(body: LoginRequest, request: Request, response: Response) -> SessionResponse:
    st = require_db(request)
    check_origin(request)
    ip = client_key(request, st.settings.trusted_proxies, st.settings.trusted_proxy_hops)
    wait = st.login_throttle.blocked(ip, body.email)
    if wait:
        log.warning("admin login throttled")
        raise _err(429, "too_many_attempts", "Too many sign-in attempts. Please wait and try again later.")
    user = await run_in_threadpool(st.auth.authenticate, body.email, body.password)
    if user is None:
        st.login_throttle.failure(ip, body.email)
        log.warning("admin login failed")  # never log the password (or the attempted email)
        raise _err(401, "invalid_credentials", "The email or password is incorrect.")
    st.login_throttle.success(ip, body.email)
    new = await run_in_threadpool(st.auth.create_session, user.id)
    _set_cookies(response, request, new.token, new.csrf_token, int(st.auth.ttl.total_seconds()))
    log.info("admin login succeeded admin_id=%d", user.id)
    return SessionResponse(email=user.email, expires_at=new.expires_at.isoformat() + "Z", csrf_token=new.csrf_token)


@router.post("/auth/logout", status_code=204)
async def logout(request: Request) -> Response:
    st = require_db(request)
    check_origin(request)
    info = st.auth.validate_session(request.cookies.get(SESSION_COOKIE), touch=False)
    response = Response(status_code=204)
    if info is not None:
        require_csrf(request, info)
        await run_in_threadpool(st.auth.revoke, info.session_id)
        log.info("admin logout admin_id=%d", info.admin_id)
    _clear_cookies(response, request)
    return response


@router.get("/session", response_model=SessionResponse)
async def session(info: SessionInfo = Depends(require_admin)) -> SessionResponse:
    return SessionResponse(email=info.email, expires_at=info.expires_at.isoformat() + "Z")


@router.get("/analytics")
async def analytics(
    request: Request,
    days: int = Query(7, description="Reporting window: 7 or 30 days"),
    _: SessionInfo = Depends(require_admin),
) -> dict:
    if days not in ALLOWED_DAYS:
        raise _err(422, "validation_error", "days must be 7 or 30.")
    report = await run_in_threadpool(request.app.state.analytics.report, days)
    report["ai_usage"] = await run_in_threadpool(request.app.state.ai_usage.report, days)
    return report
