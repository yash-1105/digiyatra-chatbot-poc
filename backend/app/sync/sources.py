"""Centralised allow-list of official sources (Pipeline A only).

Every reachable URL is either listed here or discovered from a listed source and
accepted by that source's discovery rules (same allow-listed host, path pattern and
Digi Yatra relevance). Passenger chat input can never add, change or trigger a source.
The registry is designed so Task 2 can add social/YouTube source types with the same
state, scheduling and verification lifecycle.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Organisations and the hosts that may be fetched for each (exact host match).
ALLOWED_HOSTS = {
    "digiyatrafoundation.com": "Digi Yatra Foundation",
    "www.digiyatrafoundation.com": "Digi Yatra Foundation",
    "www.civilaviation.gov.in": "Ministry of Civil Aviation",
    "civilaviation.gov.in": "Ministry of Civil Aviation",
    "www.pib.gov.in": "Press Information Bureau",
    "pib.gov.in": "Press Information Bureau",
}

HOST_ALIASES = {"digiyatrafoundation.com": "digiyatrafoundation.com", "www.digiyatrafoundation.com": "digiyatrafoundation.com",
                "civilaviation.gov.in": "www.civilaviation.gov.in", "pib.gov.in": "www.pib.gov.in"}

WEEKLY, FORTNIGHTLY = "weekly", "fortnightly"

# Source types handled by the extractor. Task 2 adds e.g. "social_post", "youtube_video".
SOURCE_TYPES = {"html_page", "html_faq", "html_press", "pdf", "discovery_search", "discovery_rss",
                "discovery_sitemap", "discovery_links"}
TRUST = {"official_operator", "official_government", "official_press"}

DIGI_YATRA = re.compile(r"digi\s*-?\s*yatra|digiyatra|डिजी\s*यात्रा|डिजीयात्रा", re.I)
# Never ingest: careers, procurement, decorative promotion and similar irrelevant pages.
EXCLUDED_PATH = re.compile(
    r"career|job|vacanc|recruit|tender|procure|empanel|rfp|eoi|gallery/photo|wallpaper|quiz|contest|login|"
    r"wp-admin|wp-login|cart|checkout|/feed/?$|/tag/|/author/|\.(?:jpe?g|png|gif|svg|webp|mp4|zip|docx?|xlsx?)$",
    re.I,
)


@dataclass(frozen=True)
class Discovery:
    """Rules for child URLs a discovery/listing source may register."""
    hosts: tuple[str, ...]
    path: str                       # regex on the URL path (+query)
    require_relevance: bool = True  # link text or URL must mention Digi Yatra
    max_children: int = 40
    child_cadence: str = FORTNIGHTLY
    child_topic: str = "announcements"
    child_risk: str = "high"
    pages: tuple[str, ...] = ()     # extra listing pages (e.g. paginated search) fetched with the parent


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    url: str
    organization: str
    source_type: str
    language: str
    trust: str
    cadence: str
    topic: str
    risk: str                       # "high" => every new/changed record requires human review
    enabled: bool = True
    section_filter: str | None = None   # keep only headed sections matching this regex
    discovery: Discovery | None = None
    historical_after_days: int | None = None  # dated announcements older than this are historical
    effective_from: str | None = None
    expires_on: str | None = None
    notes: str = ""
    fallbacks: tuple[str, ...] = field(default=())  # alternative discovery URLs (e.g. sitemap names)


SOURCES: dict[str, SourceSpec] = {s.source_id: s for s in (
    # ---- Digi Yatra Foundation (operator; app procedures, FAQs, trial, airports) --------------
    SourceSpec(
        "dyf-international-trial", "https://digiyatrafoundation.com/international-passenger-trial",
        "Digi Yatra Foundation", "html_faq", "en", "official_operator", WEEKLY, "international_trial", "high",
        notes="Priority: categorised accordion FAQs. Every question must have its complete answer.",
    ),
    SourceSpec(
        "dyf-airports-current", "https://digiyatrafoundation.com/digi-yatra-implementation-current/",
        "Digi Yatra Foundation", "html_page", "en", "official_operator", WEEKLY, "airport_coverage", "high",
        notes="Current implementation (airports/terminals). Names are never inferred from counts.",
    ),
    SourceSpec(
        "dyf-sitemap", "https://digiyatrafoundation.com/sitemap.xml",
        "Digi Yatra Foundation", "discovery_sitemap", "en", "official_operator", FORTNIGHTLY, "general", "high",
        discovery=Discovery(
            hosts=("digiyatrafoundation.com",),
            path=r"^/(?:[a-z0-9-]*(?:faq|about|how|register|registration|aadhaar|digilocker|boarding|face|"
                 r"privacy|data|security|support|help|troubleshoot|airport|airline|international|trial|"
                 r"child|dependent|news|announcement|press|update|implementation|passenger|journey)[a-z0-9-/]*)/?$",
            require_relevance=False, max_children=40, child_cadence=FORTNIGHTLY, child_topic="general",
        ),
        fallbacks=("https://digiyatrafoundation.com/sitemap_index.xml", "https://digiyatrafoundation.com/wp-sitemap.xml"),
    ),
    # ---- Ministry of Civil Aviation (government) ------------------------------------------------
    SourceSpec(
        "moca-digital-initiatives", "https://www.civilaviation.gov.in/our-digital-initiatives",
        "Ministry of Civil Aviation", "html_page", "en", "official_government", FORTNIGHTLY, "general", "low",
        section_filter=r"digi\s*yatra",
    ),
    SourceSpec(
        "moca-digital-initiatives-hi", "https://www.civilaviation.gov.in/hi/our-digital-initiatives",
        "Ministry of Civil Aviation", "html_page", "hi", "official_government", FORTNIGHTLY, "general", "low",
        section_filter=r"डिजी\s*यात्रा",
    ),
    SourceSpec(
        "moca-guidelines", "https://www.civilaviation.gov.in/ministry-documents/miscellaneous/digi-yatra-guidelines",
        "Ministry of Civil Aviation", "discovery_links", "en", "official_government", FORTNIGHTLY, "policy", "high",
        discovery=Discovery(hosts=("www.civilaviation.gov.in",), path=r"^/sites/default/files/.+\.pdf$",
                            require_relevance=False, max_children=3, child_topic="policy"),
    ),
    SourceSpec(
        "moca-search-en", "https://www.civilaviation.gov.in/search/node?keys=digi+yatra",
        "Ministry of Civil Aviation", "discovery_search", "en", "official_government", WEEKLY, "announcements", "high",
        discovery=Discovery(
            hosts=("www.civilaviation.gov.in",),
            path=r"^/(?:node/\d+|ministry-documents/[a-z0-9-]+/[a-z0-9-]+)$",
            max_children=30, child_cadence=FORTNIGHTLY,
            pages=("https://www.civilaviation.gov.in/search/node?keys=digi+yatra&page=1",
                   "https://www.civilaviation.gov.in/search/node?keys=digi+yatra&page=2"),
        ),
        historical_after_days=365,
    ),
    SourceSpec(
        "moca-search-hi", "https://www.civilaviation.gov.in/hi/search/node?keys=%E0%A4%A1%E0%A4%BF%E0%A4%9C%E0%A5%80"
        "+%E0%A4%AF%E0%A4%BE%E0%A4%A4%E0%A5%8D%E0%A4%B0%E0%A4%BE",
        "Ministry of Civil Aviation", "discovery_search", "hi", "official_government", WEEKLY, "announcements", "high",
        discovery=Discovery(
            hosts=("www.civilaviation.gov.in",),
            path=r"^/hi/(?:node/\d+|ministry-documents/[a-z0-9-]+/[a-z0-9-]+)$", max_children=15,
        ),
        historical_after_days=365,
    ),
    # ---- Press Information Bureau (dated government announcements) ------------------------------
    SourceSpec(
        "pib-rss", "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
        "Press Information Bureau", "discovery_rss", "en", "official_press", WEEKLY, "announcements", "high",
        discovery=Discovery(hosts=("www.pib.gov.in",), path=r"^/PressReleasePage\.aspx\?PRID=\d+$",
                            max_children=10, child_cadence=FORTNIGHTLY),
        historical_after_days=365,
    ),
    SourceSpec(
        "pib-2331200", "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2331200",
        "Press Information Bureau", "html_press", "en", "official_press", WEEKLY, "international_trial", "high",
        effective_from="2026-11-01", expires_on="2026-12-31",
        notes="International passenger trial (Nov–Dec 2026). Same release as the existing reviewed supplement.",
    ),
)}


def interval_days(cadence: str, settings) -> int:
    return settings.sync_weekly_days if cadence == WEEKLY else settings.sync_fortnightly_days


def canonical_url(url: str) -> str | None:
    """Normalise an allow-listed URL (https, lower-case host, no fragment/tracking); None if not allowed."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or host not in ALLOWED_HOSTS or parts.username or parts.password:
        return None
    if parts.port not in (None, 80, 443):
        return None
    host = HOST_ALIASES.get(host, host)
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
              if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if host == "www.pib.gov.in":
        # PIB serves one release under several endpoints; lang/reg only select a regional mirror.
        prid = next((v for k, v in params if k.lower() == "prid" and v.isdigit()), None)
        if prid and re.fullmatch(r"/Press\w*\.aspx", path, re.I):
            return f"https://www.pib.gov.in/PressReleasePage.aspx?PRID={prid}"
    return urlunsplit(("https", host, path, urlencode(sorted(params)), ""))


def child_id(parent_id: str, url: str) -> str:
    return f"{parent_id}:{hashlib.sha256(url.encode()).hexdigest()[:12]}"


def accept_child(spec: SourceSpec, url: str, link_text: str = "") -> str | None:
    """Discovery gate: returns the canonical child URL or None."""
    if not spec.discovery:
        return None
    canon = canonical_url(url)
    if not canon:
        return None
    parts = urlsplit(canon)
    if parts.hostname not in spec.discovery.hosts:
        return None
    target = parts.path + (f"?{parts.query}" if parts.query else "")
    if EXCLUDED_PATH.search(target) or not re.search(spec.discovery.path, target, re.I):
        return None
    if spec.discovery.require_relevance and not (DIGI_YATRA.search(link_text or "") or DIGI_YATRA.search(target)):
        return None
    return canon


# Ministry press/document pages only wrap the PIB release or the PDF: they register those as children.
CHILD_LINKS = Discovery(hosts=("www.civilaviation.gov.in", "www.pib.gov.in"),
                        path=r"^(?:/sites/default/files/.+\.pdf|/PressReleasePage\.aspx\?PRID=\d+)$",
                        require_relevance=False, max_children=3, child_cadence=FORTNIGHTLY)


def child_type(url: str) -> str:
    path = urlsplit(url).path.lower()
    if path.endswith(".pdf"):
        return "pdf"
    if "pib.gov.in" in url:
        return "html_press"
    if "/ministry-documents/" in path or re.search(r"/node/\d+$", path):
        return "discovery_links"
    return "html_page"
