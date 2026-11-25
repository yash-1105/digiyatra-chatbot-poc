"""Small registry of pinned authoritative sources and an independently reviewed serving index."""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import KnowledgeGap, KnowledgeRevision
from app.db.session import Database, utcnow
from app.rag.query import INTENT_TERMS, normalize_query
from app.rag.retriever import RetrievedChunk
from app.security.guardrails import assess_input
from app.services.faq import stable_json

INDIA = ZoneInfo("Asia/Kolkata")
MAX_SOURCE_BYTES = 512_000
TRIAL_TOPIC = "international_trial"
AIRPORT_TOPIC = "domestic_airport_coverage"


@dataclass(frozen=True)
class SourcePolicy:
    topic: str
    url: str
    title: str
    published: str | None
    starts: str | None
    ends: str | None
    risk: str
    # Conjunctive checks within each text block. The block itself is retained as evidence.
    checks: tuple[tuple[str, ...], ...]
    claim: str
    conflict: str | None = None
    travel_checks: tuple[str, str] | None = None
    eligibility: tuple[str, str] | None = None
    airport_count: int | None = None


SOURCES = {
    "pib-2331200": SourcePolicy(
        TRIAL_TOPIC, "https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2331200&lang=2&reg=48",
        "Ministry of Civil Aviation international passenger trial (PIB)", "2026-11-01", "2026-11-01",
        "2026-12-31", "high",
        (
            ("Digi Yatra has commenced trials", "November to December 2026", "eligible Indian nationals holding e-passports",
             "select international flights operated by Air India and IndiGo"),
            ("Delhi, Bengaluru, Hyderabad, Cochin, Mumbai, Chennai and Amritsar", "wherever the required infrastructure is available",
             "inform the planning of a wider rollout in 2027"),
            ("eligible Indian nationals must create an e-passport-based Verifiable Credential",
             "Near Field Communication (NFC)", "compatible smartphone"),
            ("not replace, existing travel processes", "mandatory airline document checks", "immigration procedures",
             "continue to carry their travel documents"),
        ),
        "Digi Yatra is available for selected international flights in a limited November–December 2026 trial ending 31 December 2026. "
        "Eligible Indian nationals holding e-passports can use enabled touchpoints on selected Air India and IndiGo flights. "
        "The seven (7) participating airports are Delhi, Bengaluru, Hyderabad, Cochin, Mumbai, Chennai and Amritsar. "
        "During the trial, a compatible smartphone uses NFC to read the e-passport chip for enrollment. "
        "Passengers still need to carry passports and complete regular airline document checks and immigration procedures. "
        "Trial feedback will inform planning for a wider rollout in 2027. There is no guaranteed rollout or confirmed extension.",
        "Supersedes the older domestic-only scope and international proposal for the dated trial only.",
        ("You still need to carry your passport and complete the usual airline document and immigration checks.",
         "पासपोर्ट साथ रखना और एयरलाइन की सामान्य दस्तावेज़ जाँच व इमिग्रेशन प्रक्रिया पूरी करना ज़रूरी है।"),
        ("Participation is limited to eligible Indian nationals with e-passports.",
         "इसमें केवल पात्र भारतीय ई-पासपोर्ट धारक भाग ले सकते हैं।"),
    ),
    "pib-2331200-domestic": SourcePolicy(
        AIRPORT_TOPIC, "https://www.pib.gov.in/PressReleseDetailm.aspx?PRID=2331200&lang=1&reg=1",
        "Ministry of Civil Aviation domestic Digi Yatra coverage (PIB)", "2026-11-01", "2026-11-01", None, "high",
        (("journeys across 39 domestic airports", "serving domestic airlines"),),
        "On 1 November 2026 the Ministry reported Digi Yatra journeys across 39 domestic airports. "
        "The announcement gives a count without an airport-by-airport directory. "
        "The older 24-airport directory is historical and cannot establish current coverage or live gate status.",
        "Supersedes the older 24-airport snapshot as the latest verified count. The names remain historical.",
        airport_count=39,
    ),
    "digilocker-overview": SourcePolicy(
        "digilocker_definition", "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2198743&lang=2&reg=3",
        "Government overview of DigiLocker", "2025-12-04", None, None, "low",
        (("DigiLocker is a secure, cloud-based platform", "storage, sharing, and verification of digital documents"),),
        "DigiLocker is a digital document wallet for accessing and sharing official documents.",
    ),
}


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.block = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "template", "noscript"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "div", "section", "h1", "h2", "h3", "li", "br"}:
            self.flush()

    def handle_endtag(self, tag):
        if self.hidden and tag in {"script", "style", "template", "noscript"}:
            self.hidden -= 1
        if not self.hidden and tag in {"p", "div", "section", "h1", "h2", "h3", "li"}:
            self.flush()

    def handle_data(self, data):
        if not self.hidden:
            self.block.append(data)

    def flush(self):
        if value := " ".join("".join(self.block).split()):
            self.blocks.append(value)
        self.block.clear()


def fetch_source(source_id: str) -> str:
    # Only built-in, exact HTTPS URLs are reachable. No runtime passenger lookup,
    # redirect, environment proxy or configurable destination.
    policy = SOURCES[source_id]
    hostname = urlsplit(policy.url).hostname
    addresses = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise ValueError("Official source did not resolve to a public address")
    deadline = time.monotonic() + 12
    with httpx.Client(timeout=httpx.Timeout(8, connect=3), follow_redirects=False, trust_env=False) as client:
        with client.stream("GET", policy.url, headers={"Accept": "text/html", "Accept-Encoding": "identity"}) as rsp:
            if rsp.status_code != 200 or rsp.headers.get("Content-Type", "").split(";")[0].strip().lower() != "text/html":
                raise ValueError("Unexpected official source response")
            if rsp.headers.get("content-encoding", "identity").lower() != "identity":
                raise ValueError("Unexpected source encoding")
            contents = bytearray()
            for part in rsp.iter_raw():
                contents.extend(part)
                if time.monotonic() > deadline:
                    raise ValueError("Source exceeded time limit")
                if len(contents) > MAX_SOURCE_BYTES:
                    raise ValueError("Source exceeds size limit")
    return contents.decode("utf-8", errors="replace")


def verified_payload(source_id: str, html: str) -> dict:
    source = SOURCES[source_id]
    parser = VisibleText()
    parser.feed(html)
    parser.close()
    parser.flush()
    if source.published:
        published = date.fromisoformat(source.published).strftime("%d %b %Y").lower()
        if not any(f"posted on: {published}" in b.lower() for b in parser.blocks):
            raise ValueError("Official publication date mismatch")
    evidence = []
    for required in source.checks:
        block = next((b for b in parser.blocks if len(b) <= 1500 and all(s.lower() in b.lower() for s in required)), "")
        if not block or assess_input(block).injection:
            raise ValueError("Official source evidence did not pass verification")
        evidence.append(block)
    return {
        "url": source.url, "title": source.title, "published": source.published, "starts": source.starts,
        "ends": source.ends, "claim": source.claim, "evidence": evidence, "conflict": source.conflict, "travel_checks": list(source.travel_checks) if source.travel_checks else None,
        "eligibility": list(source.eligibility) if source.eligibility else None,
        **({"airport_count": source.airport_count} if source.airport_count else {}),
    }


def domestic_airport_catalog(question: str, intent: str | None) -> bool:
    q = normalize_query(question)
    return intent == "airport_catalog" or (
        not intent and bool(re.search(r"\bairports?\b", q))
        and bool(re.search(r"\b(?:how many|count|all|39|24)\b|सूची|कितने|kitne", q))
        and bool(re.search(r"\bdigi yatra\b", q))
    )


def historical_airport_catalog(question: str) -> bool:
    q = normalize_query(question)
    if re.search(r"\b(?:compare|vs|versus|now|today|current|39)\b|अब|आज|बनाम", q):
        return False
    return bool(re.search(r"\b(?:old(?:er)?|historical|previous|2024|2025)\b|पुरानी?|ऐतिहासिक|पहले", q))


def supplemental_topic(question: str, intent: str | None) -> str | None:
    q = normalize_query(question)
    if intent in {"international_scope", "epassport_scope"} or (
        "digi yatra" in q and re.search(r"\b(?:immigration|passport checks?)\b", q)
    ) or (
        ("international" in q or "e-passport" in q) and re.search(r"\b(?:trial|pilot|rollout|2027)\b", q)
    ) or ("digi yatra" in q and re.search(r"\bhow\b.{0,45}\bnfc\b", q)) or (
        re.search(r"\be-?passport\b", q) and re.search(r"\b(?:regist\w*|enrol\w*|credential|work|how|nfc)\b", q)
    ) or re.search(r"\bdy-?ipt\b", q):
        return TRIAL_TOPIC
    if domestic_airport_catalog(question, intent):
        return AIRPORT_TOPIC
    if intent == "digilocker_comparison":
        return "digilocker_definition"
    return None


def as_chunk(row: KnowledgeRevision) -> RetrievedChunk:
    data = row.metadata_json
    return RetrievedChunk(
        chunk_id=f"supplement-{row.id}-{row.digest[:12]}", source_file=f"supplement:{row.source_id}",
        doc_title=data["title"], section="Verified supplemental source", text=data["claim"],
        question=None, score=1.0, vector_score=0.0, keyword_score=1.0, coverage=1.0,
        time_sensitive=bool(data["ends"] or data.get("airport_count")), as_of=data["published"], verification_status="verified",
        conflict_ids=[], urls=[data["url"]], category=row.topic,
        extra={"supplemental": True, "ends": data["ends"], "travel_checks": data.get("travel_checks"),
               "eligibility": data.get("eligibility"), "airport_count": data.get("airport_count")},
    )


class Knowledge:
    def __init__(self, db: Database):
        self.db = db

    def gap(self, topic: str | None) -> None:
        if topic not in INTENT_TERMS and topic != "other_digi_yatra" and topic not in {p.topic for p in SOURCES.values()}:
            return
        with self.db.session() as s:
            insert = pg_insert if s.get_bind().dialect.name == "postgresql" else sqlite_insert
            stmt = insert(KnowledgeGap).values(topic=topic, observations=1, last_seen=utcnow())
            s.execute(stmt.on_conflict_do_update(index_elements=["topic"], set_={
                "observations": KnowledgeGap.observations + 1, "last_seen": stmt.excluded.last_seen,
            }))

    def verify(self, source_id: str, *, auto_publish: bool = False, snapshot: str | None = None) -> int:
        policy = SOURCES[source_id]
        payload = verified_payload(source_id, fetch_source(source_id) if snapshot is None else snapshot)
        payload["verification"] = "pinned-https" if snapshot is None else "operator-snapshot"
        digest = hashlib.sha256(stable_json(payload)).hexdigest()
        with self.db.session() as s:
            row = s.scalar(select(KnowledgeRevision).where(KnowledgeRevision.source_id == source_id,
                                                            KnowledgeRevision.digest == digest))
            if row is None:
                row = KnowledgeRevision(topic=policy.topic, source_id=source_id, digest=digest, status="pending",
                                        risk=policy.risk, metadata_json=payload, retrieved_at=utcnow())
                s.add(row)
                s.flush()
            elif row.status in {"pending", "published"}:
                row.retrieved_at = utcnow()
            if auto_publish and snapshot is None and policy.risk == "low" and not policy.conflict and row.status == "pending":
                # Auto-publish only the fixed stable definition with source-specific checks.
                # Subsequent materially changed evidence requires a human revision.
                other = s.scalar(select(KnowledgeRevision.id).where(KnowledgeRevision.topic == policy.topic,
                                                                    KnowledgeRevision.id != row.id).limit(1))
                if other is None:
                    row.status, row.reviewer, row.reviewed_at = "published", "source-policy", utcnow()
            return row.id

    def review(self, revision: int, status: str, reviewer: str) -> None:
        if status not in {"published", "rejected", "revoked"} or not re.fullmatch(r"[\w .@-]{1,80}", reviewer):
            raise ValueError("Invalid review decision")
        with self.db.session() as s:
            row = s.get(KnowledgeRevision, revision, with_for_update=True)
            if row is None or (row.status, status) not in {
                ("pending", "published"), ("pending", "rejected"), ("published", "revoked"),
            }:
                raise ValueError("Invalid revision transition")
            if status == "published":
                if not self.integrity(row):
                    raise ValueError("Revision failed integrity validation")
                s.execute(update(KnowledgeRevision).where(KnowledgeRevision.topic == row.topic,
                                                          KnowledgeRevision.status == "published",
                                                          KnowledgeRevision.id != row.id).values(status="superseded"))
            row.status, row.reviewer, row.reviewed_at = status, reviewer, utcnow()

    @staticmethod
    def integrity(row: KnowledgeRevision) -> bool:
        data = row.metadata_json
        source = SOURCES.get(row.source_id)
        return bool(source and source.topic == row.topic and source.risk == row.risk
            and data.get("url") == source.url and data.get("claim") == source.claim
            and (source.airport_count is None or (data.get("airport_count"), data.get("published"), data.get("starts"))
                 == (source.airport_count, source.published, source.starts))
            and row.digest == hashlib.sha256(stable_json(data)).hexdigest())

    def lookup(self, topic: str, today: date | None = None) -> tuple[RetrievedChunk | None, str | None]:
        today = today or datetime.now(INDIA).date()
        with self.db.session() as s:
            row = s.scalar(select(KnowledgeRevision).where(KnowledgeRevision.topic == topic,
                        KnowledgeRevision.status == "published").order_by(KnowledgeRevision.id.desc()).limit(1))
            if row is None or not self.integrity(row):
                return None, None
            data = row.metadata_json
            if data["starts"] and today < date.fromisoformat(data["starts"]):
                return None, None
            if data["ends"] and today > date.fromisoformat(data["ends"]):
                return None, data["ends"]
            if not data["ends"] and row.retrieved_at < utcnow() - timedelta(days=180):
                return None, None
            return as_chunk(row), None

    def inspect(self, revision: int):
        with self.db.session() as s:
            row = s.get(KnowledgeRevision, revision)
            if row is None:
                raise ValueError("Unknown revision")
            return dict(id=row.id, topic=row.topic, status=row.status, risk=row.risk, digest=row.digest,
                        retrieved_at=row.retrieved_at.isoformat(), reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at else None,
                        reviewer=row.reviewer, **row.metadata_json)

    def inventory(self):
        with self.db.session() as s:
            return [{ "id": r.id, "topic": r.topic, "risk": r.risk, "status": r.status, "reviewer": r.reviewer,
                      "title": r.metadata_json["title"], "url": r.metadata_json["url"],
                      "starts": r.metadata_json["starts"], "ends": r.metadata_json["ends"]}
                    for r in s.scalars(select(KnowledgeRevision).order_by(KnowledgeRevision.id))]
