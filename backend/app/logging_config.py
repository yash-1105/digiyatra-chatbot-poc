"""Logging with a redaction filter: secrets and passenger identifiers never reach log output."""

from __future__ import annotations

import logging
import re

from app.config import get_settings

_PATTERNS = [
    (re.compile(r"(?i)(api[-_ ]?subscription[-_ ]?key|authorization|bearer|sarvam_api_key)(\W+)\S+"), r"\1\2[REDACTED]"),
    (re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)"), "[REDACTED-ID]"),
    (re.compile(r"(?<![\w.])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\w.])"), "[REDACTED-PHONE]"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[REDACTED-EMAIL]"),
]


class RedactingFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        self._secret: str | None = None

    def set_secret(self, value: str | None) -> None:
        self._secret = value if value and len(value) >= 8 else None

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if self._secret and self._secret in msg:
            msg = msg.replace(self._secret, "[REDACTED]")
        for pat, repl in _PATTERNS:
            msg = pat.sub(repl, msg)
        record.msg, record.args = msg, ()
        return True


_filter = RedactingFilter()


def configure_logging() -> None:
    settings = get_settings()
    _filter.set_secret(settings.sarvam_api_key.get_secret_value() if settings.sarvam_api_key else None)
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) and getattr(h, "_dy", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler._dy = True  # type: ignore[attr-defined]
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        handler.addFilter(_filter)
        root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    # Never let HTTP client libraries log request headers.
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    for h in root.handlers:
        if _filter not in h.filters:
            h.addFilter(_filter)
