"""In-process sliding-window rate limiter keyed by client IP."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import Request


class RateLimiter:
    MAX_KEYS = 10_000

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            if key not in self._hits and len(self._hits) >= self.MAX_KEYS:
                for old in list(self._hits):
                    events = self._hits[old]
                    while events and now - events[0] > self.window_s:
                        events.popleft()
                    if not events:
                        del self._hits[old]
                if len(self._hits) >= self.MAX_KEYS:
                    return False, max(1, int(self.window_s))  # fail closed under identity saturation
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window_s - (now - q[0])) + 1)
            q.append(now)
            return True, 0


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def client_key(request: Request, trusted_proxies: list[str], hops: int = 0) -> str:
    peer = request.client.host if request.client else "unknown"
    secret = request.app.state.settings.proxy_shared_secret
    if secret:
        # Only Vercel's server-side middleware can authenticate a forwarded client IP.
        ip = request.headers.get("x-dy-client-ip", "")
        signature = request.headers.get("x-dy-client-signature", "")
        expected = hmac.new(secret.get_secret_value().encode(), ip.encode(), hashlib.sha256).hexdigest()
        if _valid_ip(ip) and hmac.compare_digest(signature.encode(), expected.encode()):
            return ip
        return peer
    if hops > 0:
        chain = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(chain) >= hops and _valid_ip(chain[-hops]):
            return chain[-hops]
        return peer
    if peer in trusted_proxies:
        fwd = request.headers.get("x-forwarded-for", "")
        first = fwd.split(",")[0].strip()
        try:
            ipaddress.ip_address(first)
            return first
        except ValueError:
            pass
    return peer
