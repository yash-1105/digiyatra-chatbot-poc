"""Hardened HTTP retrieval for allow-listed official sources (Pipeline A only).

* exact host allow-list (sources.ALLOWED_HOSTS); HTTPS only; certificate verification on
* DNS answers AND the connected peer address must be public (blocks SSRF / DNS rebinding)
* redirects followed manually (max 3), each hop re-validated against the allow-list
* no environment proxies, bounded response size, per-request timeout and overall deadline
* conditional requests (ETag / Last-Modified), bounded retries with exponential backoff
  for 429/5xx/timeouts (Retry-After honoured up to a cap), per-host politeness interval
* robots.txt honoured (RFC 9309: 4xx => no rules, 5xx/unreachable => disallow)
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from app.sync.sources import ALLOWED_HOSTS, canonical_url

log = logging.getLogger(__name__)

HTML_TYPES = {"text/html", "application/xhtml+xml"}
XML_TYPES = {"application/xml", "text/xml", "application/rss+xml", "application/atom+xml"}
PDF_TYPES = {"application/pdf"}
JSON_TYPES = {"application/json", "text/json"}
RETRYABLE = {429, 500, 502, 503, 504}


class FetchError(Exception):
    """A fetch that must NOT be treated as successful ingestion."""

    def __init__(self, reason: str, status: int | None = None):
        super().__init__(reason)
        self.reason, self.status = reason, status


@dataclass
class FetchResult:
    url: str
    status: int
    content_type: str
    body: bytes
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


@dataclass
class FetchStats:
    requests: int = 0
    bytes: int = 0
    not_modified: int = 0
    retries: int = 0
    blocked: int = 0
    statuses: dict = field(default_factory=dict)


def _public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_link_local or ip.is_loopback)


def resolve_public(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise FetchError("dns_failure") from exc
    if not infos or any(not _public(i[4][0]) for i in infos):
        raise FetchError("non_public_address")


class SecureFetcher:
    def __init__(self, settings, *, transport: httpx.BaseTransport | None = None,
                 resolver: Callable[[str], None] = resolve_public, sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic, deadline: float | None = None):
        self.s = settings
        self.resolver, self.sleep, self.clock = resolver, sleep, clock
        self.deadline = deadline
        self.stats = FetchStats()
        self._last_host: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None | bool] = {}
        self._mocked = transport is not None
        self.client = httpx.Client(
            transport=transport, timeout=httpx.Timeout(settings.sync_request_timeout_s, connect=8),
            follow_redirects=False, trust_env=False, verify=True,
            headers={"User-Agent": settings.sync_user_agent, "Accept-Language": "en-IN,en;q=0.8,hi;q=0.6"},
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------------ helpers
    def _remaining(self) -> float:
        if self.deadline is None:
            return float("inf")
        left = self.deadline - self.clock()
        if left <= 1:
            raise FetchError("job_deadline")
        return left

    def _polite(self, host: str) -> None:
        wait = self._last_host.get(host, -1e9) + self.s.sync_host_interval_s - self.clock()
        if wait > 0:
            self.sleep(min(wait, self._remaining()))
        self._last_host[host] = self.clock()

    def _check_peer(self, response: httpx.Response) -> None:
        if self._mocked:
            return
        stream = response.extensions.get("network_stream")
        peer = stream.get_extra_info("server_addr") if stream else None
        if not peer or not _public(peer[0]):
            raise FetchError("non_public_peer")

    def _validate_url(self, url: str) -> str:
        """Allow-list + public-DNS check. The request URL keeps its own query (servers may
        redirect to a variant of the canonical identity); only the scheme is forced to HTTPS."""
        if not canonical_url(url):
            raise FetchError("url_not_allowed")
        parts = urlsplit(url.strip())
        host = (parts.hostname or "").lower()
        assert host in ALLOWED_HOSTS
        self.resolver(host)
        return urlunsplit(("https", host, parts.path or "/", parts.query, ""))

    # ------------------------------------------------------------------ robots
    def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.hostname or ""
        if host not in self._robots:
            rules: urllib.robotparser.RobotFileParser | None | bool
            try:
                r = self._raw_get(f"https://{host}/robots.txt", {}, set(), 200_000)
                parser = urllib.robotparser.RobotFileParser()
                text = r.body.decode("utf-8", "replace")
                # An HTML error page served as robots.txt carries no rules.
                parser.parse([] if "<html" in text[:500].lower() else text.splitlines())
                rules = parser
            except FetchError as exc:
                # RFC 9309 §2.3.1: 4xx => crawl allowed; 5xx/unreachable => complete disallow.
                rules = None if (exc.status and 400 <= exc.status < 500) else False
            self._robots[host] = rules
        rules = self._robots[host]
        if rules is False:
            return False
        if rules is None:
            return True
        return rules.can_fetch(self.s.sync_user_agent, url)

    # ------------------------------------------------------------------ fetch
    def _raw_get(self, url: str, headers: dict, allowed_types: set[str], max_bytes: int) -> FetchResult:
        current = self._validate_url(url)
        for _hop in range(4):
            host = urlsplit(current).hostname or ""
            self._polite(host)
            timeout = min(self.s.sync_request_timeout_s, self._remaining())
            self.stats.requests += 1
            try:
                with self.client.stream("GET", current, headers={**headers, "Accept-Encoding": "gzip, identity"},
                                        timeout=timeout) as rsp:
                    self._check_peer(rsp)
                    self.stats.statuses[str(rsp.status_code)] = self.stats.statuses.get(str(rsp.status_code), 0) + 1
                    if rsp.status_code in (301, 302, 303, 307, 308):
                        location = rsp.headers.get("location")
                        if not location:
                            raise FetchError("redirect_without_location", rsp.status_code)
                        current = self._validate_url(urljoin(current, location))
                        continue
                    if rsp.status_code == 304:
                        self.stats.not_modified += 1
                        return FetchResult(current, 304, "", b"", rsp.headers.get("etag"),
                                           rsp.headers.get("last-modified"), not_modified=True)
                    if rsp.status_code != 200:
                        reason = {403: "forbidden_or_waf_blocked", 404: "not_found", 410: "gone",
                                  429: "rate_limited"}.get(rsp.status_code, f"http_{rsp.status_code}")
                        if rsp.status_code == 403:
                            self.stats.blocked += 1
                        retry_after = rsp.headers.get("retry-after")
                        err = FetchError(reason, rsp.status_code)
                        err.retry_after = float(retry_after) if retry_after and retry_after.isdigit() else None
                        raise err
                    ctype = rsp.headers.get("content-type", "").split(";")[0].strip().lower()
                    if allowed_types and ctype not in allowed_types:
                        raise FetchError(f"unexpected_content_type:{ctype[:40]}", 200)
                    declared = rsp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise FetchError("response_too_large", 200)
                    body = bytearray()
                    for part in rsp.iter_bytes():
                        body.extend(part)
                        if len(body) > max_bytes:
                            raise FetchError("response_too_large", 200)
                        self._remaining()
                    self.stats.bytes += len(body)
                    return FetchResult(current, 200, ctype, bytes(body), rsp.headers.get("etag"),
                                       rsp.headers.get("last-modified"))
            except httpx.TimeoutException as exc:
                raise FetchError("timeout") from exc
            except httpx.HTTPError as exc:
                raise FetchError(f"network_error:{type(exc).__name__}") from exc
        raise FetchError("too_many_redirects")

    def get(self, url: str, kind: str, *, etag: str | None = None, last_modified: str | None = None,
            respect_robots: bool = True) -> FetchResult:
        allowed, limit = {
            "html": (HTML_TYPES, self.s.sync_max_html_bytes),
            "xml": (XML_TYPES | {"text/html"}, self.s.sync_max_html_bytes),
            "pdf": (PDF_TYPES, self.s.sync_max_pdf_bytes),
            "json": (JSON_TYPES, self.s.sync_max_html_bytes),
        }[kind]
        canon = self._validate_url(url)
        if respect_robots and not self.allowed_by_robots(canon):
            raise FetchError("disallowed_by_robots")
        headers = {"Accept": {"html": "text/html,application/xhtml+xml", "xml": "application/rss+xml,application/xml,text/xml",
                              "pdf": "application/pdf", "json": "application/json"}[kind]}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        attempt = 0
        while True:
            try:
                return self._raw_get(canon, headers, allowed, limit)
            except FetchError as exc:
                retryable = exc.reason == "timeout" or exc.reason.startswith("network_error") or (exc.status in RETRYABLE)
                if not retryable or attempt >= self.s.sync_max_retries:
                    raise
                attempt += 1
                self.stats.retries += 1
                delay = getattr(exc, "retry_after", None) or (2.0 * 2 ** (attempt - 1))
                self.sleep(min(delay, 60.0, max(0.0, self._remaining() - 2)))
