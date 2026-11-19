"""Shared request dependencies."""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from app.security.rate_limit import client_key

log = logging.getLogger(__name__)


def rate_limited(request: Request) -> None:
    state = request.app.state
    key = client_key(request, state.settings.trusted_proxies, state.settings.trusted_proxy_hops)
    # DEBUG only (IP addresses are personal data): used once after deployment to verify TRUSTED_PROXY_HOPS.
    log.debug("rate_limit client=%s peer=%s xff_entries=%d", key, request.client.host if request.client else "-",
              len([p for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]))
    allowed, retry_after = state.rate_limiter.check(key)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={"code": "rate_limited", "message": "Too many requests. Please wait a moment and try again."},
            headers={"Retry-After": str(retry_after)},
        )
