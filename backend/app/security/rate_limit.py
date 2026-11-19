"""In-process sliding-window rate limiter keyed by client IP."""

from __future__ import annotations

import ipaddress
import threading
import time
from collections import defaultdict, deque

from fastapi import Request


class RateLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window_s - (now - q[0])) + 1)
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    del self._hits[k]
            return True, 0


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def client_key(request: Request, trusted_proxies: list[str], hops: int = 0) -> str:
    peer = request.client.host if request.client else "unknown"
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
