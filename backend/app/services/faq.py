"""Reviewed public FAQ lookup. This module never learns from chat traffic."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from app.db.models import ApprovedFAQ
from app.db.session import utcnow
from app.rag.query import query_intent
from app.rag.retriever import RetrievedChunk
from app.security.grounding import ground_answer
from app.security.guardrails import assess_input, check_output
from app.services.prompts import CANARY, SYSTEM_PROMPT

# Closed allowlist. Every variant still requires its own reviewed answer in the requested locale.
PUBLIC_QUESTIONS = {
    "can i use digi yatra on android",
    "is digi yatra only for ios",
    "where can i download digi yatra",
    "डिजी यात्रा ऐप कहाँ डाउनलोड करूँ",
    "क्या मैं एंड्रॉयड पर डिजी यात्रा इस्तेमाल कर सकता हूँ",
    "digi yatra app kahan download karun",
}
ANSWER_RULES_REVISION = "2"


def faq_key(question):
    # NFC preserves meaningful punctuation, numerals, accents and negation.
    normalized = " ".join(unicodedata.normalize("NFC", question).lower().split()).removesuffix("?")
    return normalized if normalized in PUBLIC_QUESTIONS else None


def stable_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class FAQSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str
    source_file: str
    chunk_sha256: str
    document_sha256: str


class FAQEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    locale: Literal["en", "hi"]
    intent: Literal["app_download"]
    answer: str = Field(min_length=10, max_length=3500)
    sources: list[FAQSource] = Field(min_length=1, max_length=10)
    knowledge_version: str
    revision: int = Field(ge=1)
    reviewer: str = Field(min_length=1, max_length=80)
    expires_at: datetime
    eligibility: Literal["public_static"]
    origin: Literal["human_reviewed"]


class ReviewedFAQs:
    def __init__(self, db, settings, retriever):
        from ingestion.corpus import load_corpus

        self.db, self.r = db, retriever
        key = settings.faq_cache_signing_key
        self.secret = key.get_secret_value().encode() if key else b""
        if len(self.secret) < 32:
            raise ValueError("FAQ signing key missing or too short")
        chunks, corpus = load_corpus(settings.knowledge_corpus_dir)
        if retriever.index.meta().get("corpus_sha256") != corpus["corpus_sha256"]:
            raise ValueError("FAQ corpus revision unavailable")
        self.corpus_rows = {row["chunk_id"]: row for row in chunks}
        self.retriever_revision = retriever.corpus_revision
        self.table_version = retriever.index.table().version
        self.documents = {d["source_file"]: d["source_sha256"] for d in corpus["documents"]}
        self.excluded = set(corpus["excluded_documents"])
        self.version = hashlib.sha256(stable_json([
            corpus["corpus_sha256"], corpus["approval"]["manifest_sha256"], self.documents,
            retriever.corpus_revision, ANSWER_RULES_REVISION, SYSTEM_PROMPT.replace(CANARY, ""),
        ])).hexdigest()
        self.secrets = [k.get_secret_value() for k in (settings.sarvam_api_key, settings.anthropic_api_key, settings.novita_api_key, key) if k]

    def source_ref(self, chunk_id):
        row = self.r.lookup(chunk_id)
        if not row or row["source_file"] not in self.documents or row["source_file"] in self.excluded:
            raise ValueError("Unknown approved FAQ source")
        original = self.corpus_rows.get(chunk_id)
        if not original or any(row.get(k) != original.get(k) for k in (
            "text", "source_file", "content_hash", "approval_status", "verification_status",
        )):
            raise ValueError("FAQ evidence differs from approved corpus")
        return FAQSource(chunk_id=chunk_id, source_file=row["source_file"],
                         chunk_sha256=hashlib.sha256(stable_json(row)).hexdigest(),
                         document_sha256=self.documents[row["source_file"]])

    def verify(self, entry, key, locale):
        if (faq_key(entry.question) != key or entry.locale != locale
            or query_intent(entry.question) != entry.intent or entry.knowledge_version != self.version
            or entry.expires_at.tzinfo is not None or entry.expires_at <= utcnow()
            or self.r.corpus_revision != self.retriever_revision
            or self.r.index.table().version != self.table_version):
            raise ValueError("FAQ metadata mismatch")
        hits = []
        for ref in entry.sources:
            if ref != self.source_ref(ref.chunk_id):
                raise ValueError("FAQ source changed")
            row = self.r.lookup(ref.chunk_id)
            if (row["approval_status"] != "approved" or row["time_sensitive"] or row["conflict_ids"]
                or row["verification_status"] not in {"verified", "not_applicable"}):
                raise ValueError("FAQ source requires caveats")
            hits.append(RetrievedChunk(
                chunk_id=ref.chunk_id, source_file=ref.source_file, doc_title=row["doc_title"],
                section=row["section"], text=row["text"], question=row.get("question"), score=1.0,
                vector_score=0, keyword_score=0, coverage=0, time_sensitive=False,
                as_of=row["as_of"], verification_status=row["verification_status"],
                conflict_ids=[], urls=row["urls"], category=row["category"],
            ))
        if len({h.chunk_id for h in hits}) != len(hits):
            raise ValueError("Duplicate FAQ source")
        a = assess_input(entry.answer)
        devanagari = len(re.findall(r"[\u0900-\u097f]", entry.answer))
        if a.pii_types or a.injection or (devanagari > 12 if locale == "en" else devanagari < 12):
            raise ValueError("Ineligible FAQ answer")
        output = check_output(entry.answer, n_sources=len(hits), secrets=self.secrets, canary=CANARY,
                              allowed_urls={url for h in hits for url in h.urls}, allowed_url_prefixes=())
        grounded = ground_answer(output.text, {i: h - 1 for i, h in enumerate(output.cited, 1)},
                                 [h.text for h in hits])
        if (output.leaked or output.invalid_citations or output.removed_urls or output.removed_actions
            or grounded.dropped or grounded.reattributed or grounded.removed_markers
            or grounded.cited_hits != list(range(len(hits))) or grounded.text != entry.answer):
            raise ValueError("FAQ answer failed citation validation")
        return hits

    def signature(self, payload, revoked=False):
        return hmac.new(self.secret, stable_json([payload, revoked]), "sha256").hexdigest()

    def lookup(self, key, locale):
        with self.db.session() as session:
            if session.bind.dialect.name == "postgresql":
                session.execute(text("SET LOCAL statement_timeout = '250ms'"))
            row = session.get(ApprovedFAQ, (key, locale))
            if row is None:
                return "miss", None, []
            if not hmac.compare_digest(row.signature, self.signature(row.payload, row.revoked)):
                return "invalid", None, []
            if row.revoked:
                return "revoked", None, []
            entry = FAQEntry.model_validate(row.payload)
            if entry.knowledge_version != self.version or (
                entry.expires_at.tzinfo is None and entry.expires_at <= utcnow()
            ):
                return "stale", None, []
            return "hit", entry.answer, self.verify(entry, key, locale)

    def publish(self, entries):
        with self.db.session() as session:
            if session.bind.dialect.name == "postgresql":
                session.execute(text("LOCK TABLE approved_faq IN SHARE ROW EXCLUSIVE MODE"))
            for entry in entries:
                key = faq_key(entry.question)
                if not key or entry.expires_at.tzinfo or entry.expires_at > utcnow() + timedelta(days=30):
                    raise ValueError("Invalid FAQ key or expiration")
                self.verify(entry, key, entry.locale)
                payload = entry.model_dump(mode="json")
                current = session.get(ApprovedFAQ, (key, entry.locale))
                if current:
                    if not current.revoked and current.payload == payload and hmac.compare_digest(
                        current.signature, self.signature(payload)
                    ):
                        continue
                    if entry.revision <= FAQEntry.model_validate(current.payload).revision:
                        raise ValueError("FAQ revision must increase")
                    current.payload, current.signature, current.revoked = payload, self.signature(payload), False
                else:
                    session.add(ApprovedFAQ(key=key, locale=entry.locale, payload=payload,
                                            signature=self.signature(payload), revoked=False))

    def revoke(self, key, locale):
        with self.db.session() as session:
            row = session.get(ApprovedFAQ, (key, locale), with_for_update=True)
            if row and hmac.compare_digest(row.signature, self.signature(row.payload, row.revoked)):
                row.revoked = True
                row.signature = self.signature(row.payload, True)
