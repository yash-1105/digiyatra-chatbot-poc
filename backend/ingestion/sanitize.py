"""Sanitisation: strip markup/embedded media, keep only allow-listed links, redact PII."""

from __future__ import annotations

import re
from collections import Counter
from urllib.parse import urlparse

# Domains whose links may be kept as citation/reference URLs.
ALLOWED_LINK_DOMAINS = (
    "digiyatrafoundation.com",
    "youtube.com",
    "youtu.be",
    "play.google.com",
    "apps.apple.com",
)

# Organisational mailboxes that are published contact points (not personal data).
ALLOWED_EMAIL_DOMAINS = ("digiyatrafoundation.com",)

_HTML_BLOCK = re.compile(r"<(video|audio|iframe|script|style)\b.*?</\1>", re.S | re.I)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BARE_URL = re.compile(r"https?://[^\s)\"'<>\]]+")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
# Indian mobile numbers (optionally +91), but not things like years or 6-digit OTP examples.
_PHONE = re.compile(r"(?<![\w.])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?![\w.])")
# Aadhaar-like 12-digit identifiers (with optional spaces).
_AADHAAR = re.compile(r"(?<!\d)\d{4}\s?\d{4}\s?\d{4}(?!\d)")
# Indian passport number format.
_PASSPORT = re.compile(r"\b[A-PR-WY][1-9]\d\s?\d{4}[1-9]\b")


def _domain_allowed(url: str, allowed: tuple[str, ...]) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in allowed)


def strip_markup(text: str) -> str:
    """Remove embedded HTML media blocks, tags and images."""
    text = _HTML_BLOCK.sub("", text)
    text = _HTML_TAG.sub("", text)
    text = _MD_IMAGE.sub("", text)
    return text


def clean_quotes(text: str) -> str:
    """Undo spreadsheet-export quoting: surrounding quotes, trailing commas, doubled quotes."""
    t = text.strip()
    t = t.replace('""', '"')
    t = re.sub(r'^"\s*', "", t)
    t = re.sub(r'\s*"\s*,?\s*$', "", t)
    return t.strip()


def normalise_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln == "" and (not out or out[-1] == ""):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def sanitize_text(text: str) -> tuple[str, list[str], Counter]:
    """Return (clean_text, kept_urls, redaction_counts)."""
    redactions: Counter = Counter()
    kept_urls: list[str] = []

    text = strip_markup(text)

    def _link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        if _domain_allowed(url, ALLOWED_LINK_DOMAINS):
            kept_urls.append(url)
            return url if label.strip() == url else f"{label} ({url})"
        redactions["external_link"] += 1
        return label

    text = _MD_LINK.sub(_link, text)

    def _bare(m: re.Match) -> str:
        url = m.group(0).rstrip(".,;:")
        if _domain_allowed(url, ALLOWED_LINK_DOMAINS):
            if url not in kept_urls:
                kept_urls.append(url)
            return m.group(0)
        redactions["external_link"] += 1
        return ""

    text = _BARE_URL.sub(_bare, text)

    def _email(m: re.Match) -> str:
        if m.group(1).lower() in ALLOWED_EMAIL_DOMAINS:
            return m.group(0)
        redactions["email"] += 1
        return "[redacted email]"

    text = _EMAIL.sub(_email, text)

    for name, pattern, repl in (
        ("aadhaar_like_number", _AADHAAR, "[redacted id]"),
        ("phone", _PHONE, "[redacted phone]"),
        ("passport_number", _PASSPORT, "[redacted id]"),
    ):
        text, n = pattern.subn(repl, text)
        if n:
            redactions[name] += n

    return normalise_whitespace(text), kept_urls, redactions


def apply_drop_patterns(lines: list[str], patterns: list[str]) -> tuple[list[str], int]:
    compiled = [re.compile(p) for p in patterns]
    kept, dropped = [], 0
    for ln in lines:
        if any(p.search(ln.strip()) for p in compiled):
            dropped += 1
            continue
        kept.append(ln)
    return kept, dropped


def normalise_for_hash(text: str) -> str:
    """Canonical form used for duplicate detection."""
    t = text.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()
