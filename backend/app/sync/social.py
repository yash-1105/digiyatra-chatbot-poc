"""Official social media, YouTube and transcript knowledge (Task 2; Pipeline A only).

Permitted collection mechanisms only:
* Posts by verified official accounts EMBEDDED on official government pages already crawled by
  Task 1 (civilaviation.gov.in): the page HTML contains the post text, author and permalink.
* YouTube Data API v3 (official; free quota; needs ``YOUTUBE_API_KEY``) for channel uploads,
  playlists, video metadata and caption-track *availability*. Caption *download* needs the channel
  owner's OAuth consent and is therefore not automated.
* Without an API key: YouTube oEmbed (documented, robots-permitted) to verify ownership/availability
  of KNOWN video IDs (from the approved corpus or an operator list). No page scraping, no feeds
  (``/feeds/videos.xml`` and ``/timedtext_video`` are disallowed by youtube.com/robots.txt).
* Operator imports: organisation-supplied caption files (.vtt/.srt) and social post exports.
X oEmbed (publish.x.com robots: Disallow /oembed), LinkedIn (403/login), Instagram and Facebook
(login walls) are never fetched automatically.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date

import lxml.html as lh

from app.sync.extract import EN_MONTHS, clean, language_of, node_text

YOUTUBE_CHANNEL_ID = "UCAW0wpe_OvaAe3M6EKRGMJw"
YOUTUBE_HANDLE_URL = "https://www.youtube.com/@DigiYatraFoundation"


@dataclass(frozen=True)
class Account:
    platform: str          # youtube | x | linkedin | instagram | facebook
    account_id: str        # stable ID where available (YouTube channel ID), else the handle/slug
    handle: str
    name: str
    profile_url: str
    owner: str
    status: str            # verified | verified_government | excluded | unverified
    automated: str         # how (or why not) it is collected automatically
    evidence: tuple[str, ...] = ()


ACCOUNTS: dict[str, Account] = {f"{a.platform}:{a.handle.lower().lstrip('@')}": a for a in (
    Account("youtube", YOUTUBE_CHANNEL_ID, "@DigiYatraFoundation", "Digi Yatra Foundation", YOUTUBE_HANDLE_URL,
            "Digi Yatra Foundation", "verified",
            "YouTube Data API v3 when YOUTUBE_API_KEY is set; otherwise oEmbed checks of known video IDs",
            ("All 7 YouTube videos linked from approved Digi Yatra knowledge documents are published by this channel "
             "(YouTube oEmbed author_url, checked 2026-11-25)",
             "Channel page canonical URL https://www.youtube.com/channel/UCAW0wpe_OvaAe3M6EKRGMJw (one-time check)")),
    Account("x", "DigiYatraOffice", "@DigiYatraOffice", "Digi Yatra Official", "https://x.com/DigiYatraOffice",
            "Digi Yatra Foundation", "verified",
            "posts embedded on civilaviation.gov.in pages; direct X access needs a paid API (not enabled)",
            ("Posts by @DigiYatraOffice are embedded on the Ministry of Civil Aviation website (node/7641, node/6053)",
             "X oEmbed author name 'Digi Yatra Official' (one-time manual check)")),
    Account("x", "MoCA_GoI", "@MoCA_GoI", "Ministry of Civil Aviation", "https://x.com/MoCA_GoI",
            "Ministry of Civil Aviation", "verified_government", "posts embedded on civilaviation.gov.in pages",
            ("Embedded on the Ministry's own website (11 Digi Yatra pages)",)),
    Account("x", "PIB_India", "@PIB_India", "PIB India", "https://x.com/PIB_India", "Press Information Bureau",
            "verified_government", "posts embedded on civilaviation.gov.in pages",
            ("Embedded on the Ministry of Civil Aviation website",)),
    Account("x", "AAI_Official", "@AAI_Official", "Airports Authority of India", "https://x.com/AAI_Official",
            "Airports Authority of India", "verified_government", "posts embedded on civilaviation.gov.in pages",
            ("Embedded on the Ministry of Civil Aviation website",)),
    Account("x", "RamMNK", "@RamMNK", "Personal account of a public official", "https://x.com/RamMNK", "individual",
            "excluded", "not ingested: personal account, not an organisation channel"),
    Account("linkedin", "digiyatrafoundation", "digiyatrafoundation", "Digi Yatra Foundation",
            "https://www.linkedin.com/company/digiyatrafoundation/", "Digi Yatra Foundation", "verified",
            "blocked (HTTP 403 / login wall); manual import of organisation-provided exports only",
            ("Company page and posts linked from approved Digi Yatra knowledge documents",
             "Approved LinkedIn-derived documents in the private approval manifest")),
    Account("instagram", "digiyatrafoundation", "digiyatrafoundation", "Digi Yatra Foundation (candidate)",
            "https://www.instagram.com/digiyatrafoundation/", "unknown", "unverified",
            "blocked (login wall); not verified — official website link needed before any import"),
    Account("facebook", "digiyatrafoundation", "digiyatrafoundation", "Digi Yatra Foundation (candidate)",
            "https://www.facebook.com/digiyatrafoundation", "unknown", "unverified",
            "blocked (login wall); no official reference found"),
)}


def account(platform: str, handle: str) -> Account | None:
    return ACCOUNTS.get(f"{platform}:{handle.lower().lstrip('@')}")


def ingestible(acc: Account | None) -> bool:
    return bool(acc and acc.status in {"verified", "verified_government"})


# --------------------------------------------------------------------------- classification
TOPICS: tuple[tuple[str, re.Pattern], ...] = tuple((t, re.compile(p, re.I)) for t, p in (
    ("international_trial", r"international|e-?passport|dy-?ipt|immigration|अंतरराष्ट्रीय|ई-?पासपोर्ट"),
    ("airport_coverage", r"\bairports?\b.{0,60}\b(?:live|launch|added|new|now|inaugurat|expan|enabled|operational)|"
                         r"(?:launch|inaugurat|expan|live|enabled)\w*.{0,60}\bairports?\b|हवाई अड्ड"),
    ("airline_integration", r"\bairlines?\b|indigo|air india|akasa|spicejet|vistara|alliance air|एयरलाइन"),
    ("app_update", r"app update|new feature|update (?:your|the) app|latest version|now available on|"
                   r"introduc\w* .{0,30}feature|ऐप अपडेट"),
    ("registration", r"regist|enrol|aadhaar|digilocker|onboard|credential|पंजीकरण|आधार"),
    ("boarding_pass", r"boarding pass|smart share|बोर्डिंग पास"),
    ("privacy", r"privacy|personal data|data (?:safety|security|protection)|consent|self-sovereign|गोपनीयता|डेटा"),
    ("troubleshooting", r"troubleshoot|not working|\berror\b|help ?desk|customer (?:care|support)|helpline|सहायता"),
    ("advisory", r"advisory|passengers are (?:advised|requested)|please note|important|सलाह"),
))
HIGH_RISK = {"international_trial", "airport_coverage", "airline_integration", "privacy", "registration", "advisory"}
GREETING = re.compile(r"\b(?:happy|wish(?:es|ing)?|greetings|diwali|holi|eid|christmas|new year|independence day|"
                      r"republic day|festival|yoga day|mother'?s day|women'?s day|congratulat\w*)\b|शुभकामना|बधाई", re.I)
CONTEST = re.compile(r"\b(?:quiz|contest|guess|giveaway|caption this|poll)\b", re.I)
# Events (summits, expos, awards) are historical per project rules unless they carry a consequential topic.
EVENT = re.compile(r"\b(?:summit|conference|expo|exhibition|award|felicitat\w*|ceremony|roadshow|webinar|hackathon)\b", re.I)
THANKS = re.compile(r"\bthank(?:s| you)\b|\bproud\b|\bkudos\b|धन्यवाद", re.I)
CLAIM_TYPES = (("pilot", r"\btrials?\b|\bpilot\b|\bbeta\b|परीक्षण"), ("future", r"\bwill\b|\bupcoming\b|\bsoon\b|"
               r"\bplanned\b|\bby 20\d\d\b|coming|जल्द"), ("proposed", r"\bpropos\w*|\bplan(?:s|ning)? to\b|consider"),
               ("announced", r"\blaunch\w*|\bintroduc\w*|\bannounc\w*|\bnow live\b|\binaugurat\w*|शुरू"))


def classify(text: str) -> tuple[str, str, str]:
    """(topic, risk, claim_type) — deterministic; never decides truth."""
    topic = next((t for t, rx in TOPICS if rx.search(text)), "general")
    if topic not in ("international_trial",) and re.search(r"\b\d{1,3}\s+(?:\w+\s+){0,2}airports\b|\d{1,3}\s+हवाई", text, re.I):
        topic = "airport_coverage"  # any airport count is a consequential coverage claim
    claim = next((c for c, p in CLAIM_TYPES if re.search(p, text, re.I)), "operational_or_general")
    return topic, ("high" if topic in HIGH_RISK else "low"), claim


def excluded_reason(text: str) -> str | None:
    if len(re.sub(r"\s+|#\w+|https?://\S+", "", text)) < 30:
        return "too_short"
    if CONTEST.search(text):
        return "contest_or_quiz"
    topic = classify(text)[0]
    if topic not in HIGH_RISK and EVENT.search(text):
        return "event_or_historical"
    if topic not in HIGH_RISK and (GREETING.search(text) or THANKS.search(text)):
        return "greeting_or_promotional"
    return None


# --------------------------------------------------------------------------- embedded posts
@dataclass
class Post:
    platform: str
    post_id: str
    handle: str
    account_name: str
    permalink: str
    published_on: str | None
    text: str
    language: str
    referenced_urls: list[str] = field(default_factory=list)
    media: dict = field(default_factory=dict)


STATUS_URL = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/(\w{1,30})/status/(\d{5,25})", re.I)
SIGNATURE = re.compile(r"—\s*(.+?)\s*\(@(\w{1,30})\)\s*([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})")


def embedded_posts(html: str) -> list[Post]:
    """Official X posts embedded on a page (``<blockquote class="twitter-tweet">``)."""
    root = lh.document_fromstring(html)
    posts: list[Post] = []
    for bq in root.xpath("//blockquote[contains(concat(' ',normalize-space(@class),' '),' twitter-tweet ')]"):
        para = bq.xpath(".//p")
        text = clean("\n".join(node_text(p) for p in para)) if para else ""
        sig_text = " ".join(bq.text_content().split())
        links = [a.get("href", "") for a in bq.xpath(".//a[@href]")]
        status = next((m for h in reversed(links) if (m := STATUS_URL.match(h))), None)
        sig = SIGNATURE.search(sig_text)
        if not status or not text:
            continue
        handle, post_id = status.group(1), status.group(2)
        published = None
        if sig and (month := EN_MONTHS.get(sig.group(3)[:3].lower())):
            try:
                published = date(int(sig.group(5)), month, int(sig.group(4))).isoformat()
            except ValueError:
                published = None
        refs = [h for h in links if h.startswith("http") and "/hashtag/" not in h and not STATUS_URL.match(h)]
        text = re.sub(r"\s*pic\.twitter\.com/\w+", "", text).strip()
        lang = (para[0].get("lang") if para else None) or language_of(text)
        posts.append(Post("x", post_id, handle, sig.group(1) if sig else handle, f"https://x.com/{handle}/status/{post_id}",
                          published, text, "hi" if lang == "hi" else ("en" if lang in ("en", "und", None) else lang),
                          refs[:5], {"has_media": "pic.twitter.com" in sig_text}))
    return posts


# --------------------------------------------------------------------------- YouTube
YOUTUBE_ID = re.compile(r"(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})")


def video_ids(text: str) -> list[str]:
    return list(dict.fromkeys(YOUTUBE_ID.findall(text)))


def watch_url(video_id: str, seconds: int | None = None) -> str:
    if not re.fullmatch(r"[\w-]{11}", video_id):
        raise ValueError("invalid video id")
    return f"https://www.youtube.com/watch?v={video_id}" + (f"&t={int(seconds)}" if seconds else "")


def iso_duration(value: str | None) -> int | None:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not m:
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return ((d * 24 + h) * 60 + mi) * 60 + s


DESCRIPTION_NOISE = re.compile(r"^(?:#\w+\s*)+$|subscribe|follow us|like and share|^\s*(?:facebook|instagram|twitter|x|"
                               r"linkedin|website)\s*[:\-]", re.I)


def relevant_description(text: str, limit: int = 1500) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    keep = [ln for ln in lines if ln and not DESCRIPTION_NOISE.search(ln) and not re.fullmatch(r"https?://\S+", ln)]
    return "\n".join(keep)[:limit]


# --------------------------------------------------------------------------- transcripts
CUE_TIME = re.compile(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d{1,2}):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
CAPTION_NOISE = re.compile(r"\[(?:music|applause|laughter|संगीत)\]|<[^>]+>|\{\\[^}]*\}", re.I)


@dataclass
class Segment:
    start: int
    end: int
    text: str


def parse_captions(data: bytes) -> list[Segment]:
    """WebVTT / SRT -> de-duplicated cues (rolling automatic-caption repeats removed)."""
    text = data.decode("utf-8-sig", "replace").replace("\r\n", "\n")
    cues: list[Segment] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        idx = next((i for i, ln in enumerate(lines) if CUE_TIME.search(ln)), None)
        if idx is None:
            continue
        m = CUE_TIME.search(lines[idx])
        h1, m1, s1, _, h2, m2, s2, _ = m.groups()
        start = int(h1 or 0) * 3600 + int(m1) * 60 + int(s1)
        end = int(h2 or 0) * 3600 + int(m2) * 60 + int(s2)
        body = " ".join(CAPTION_NOISE.sub("", ln).strip() for ln in lines[idx + 1:])
        body = " ".join(body.split())
        if body:
            cues.append(Segment(start, end, body))
    out: list[Segment] = []
    for c in cues:
        if out and (c.text == out[-1].text or out[-1].text.endswith(c.text)):
            out[-1].end = max(out[-1].end, c.end)
            continue
        if out and c.text.startswith(out[-1].text):  # rolling caption: keep only the new words
            c = Segment(c.start, c.end, c.text[len(out[-1].text):].strip())
            if not c.text:
                continue
        out.append(c)
    return out


def group_segments(segments: list[Segment], window_s: int = 75, max_chars: int = 900) -> list[Segment]:
    """Group cues into logically sized passages, breaking at sentence ends where possible."""
    groups: list[Segment] = []
    cur: Segment | None = None
    for s in segments:
        if cur and (s.start - cur.start >= window_s or len(cur.text) + len(s.text) > max_chars) and (
                re.search(r"[.!?।]$", cur.text) or s.start - cur.start >= window_s * 1.5):
            groups.append(cur)
            cur = None
        cur = Segment(s.start, s.end, s.text) if cur is None else Segment(cur.start, s.end, f"{cur.text} {s.text}")
    if cur:
        groups.append(cur)
    return groups


# --------------------------------------------------------------------------- manual social exports
SOCIAL_URL = {
    "x": re.compile(r"^https://(?:www\.)?(?:x|twitter)\.com/(\w{1,30})/status/(\d{5,25})/?$", re.I),
    "linkedin": re.compile(r"^https://www\.linkedin\.com/(?:posts/([\w-]+?)_[\w%-]+?-activity-(\d{10,25})-[\w-]+|"
                           r"feed/update/urn:li:activity:(\d{10,25}))/?$", re.I),
    "instagram": re.compile(r"^https://www\.instagram\.com/(?:p|reel)/([\w-]{5,20})/?$", re.I),
    "facebook": re.compile(r"^https://www\.facebook\.com/([\w.]+)/posts/([\w]+)/?$", re.I),
}


def parse_social_export(platform: str, data: bytes, handle: str | None = None) -> list[Post]:
    """Organisation-provided export (JSON list or CSV with url,published,text[,language,modified])."""
    raw = data.decode("utf-8-sig", "replace")
    rows = json.loads(raw) if raw.lstrip().startswith("[") else list(csv.DictReader(io.StringIO(raw)))
    rx = SOCIAL_URL.get(platform)
    if rx is None:
        raise ValueError("Unsupported platform")
    posts = []
    for row in rows[:500]:
        url, text = str(row.get("url", "")).strip(), clean(str(row.get("text", "")))
        m = rx.match(url)
        if not m or not text:
            raise ValueError(f"Invalid {platform} export row (permalink and text required)")
        groups = [g for g in m.groups() if g]
        if platform == "x":
            who, pid = groups[0], groups[1]
        elif platform == "linkedin":
            who, pid = (groups[0], groups[1]) if len(groups) == 2 else (handle or "", groups[0])
        else:
            who, pid = handle or "", groups[-1]
        acc = account(platform, who)
        if not ingestible(acc):
            raise ValueError(f"{platform} account {who or '(unspecified)'} is not a verified official account")
        published = str(row.get("published", ""))[:10] or None
        if published and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
            raise ValueError("published must be YYYY-MM-DD")
        posts.append(Post(platform, pid, acc.handle.lstrip("@"), acc.name, url.rstrip("/"), published, text,
                          str(row.get("language") or language_of(text))[:2],
                          media={"modified": str(row.get("modified", ""))[:10] or None}))
    return posts


def stable_hash(*parts) -> str:
    return hashlib.sha256("\x1f".join(str(p or "") for p in parts).encode()).hexdigest()
