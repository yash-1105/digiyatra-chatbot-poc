"""Knowledge publication: verified official records -> versioned, validated LanceDB index.

PostgreSQL is the durable source of truth (records + immutable publications). Each API
process builds its own local index for the active publication in a fresh directory and
swaps its retriever only after the build validated, so a request is always served by one
complete index (old or new) and multiple instances never see a partially published index.
The API reads PostgreSQL only; it never contacts an external source.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
from pathlib import Path

from sqlalchemy import select, text, update

from app.db.models import KnowledgePublication, OfficialRecord
from app.db.session import Database, utcnow
from app.rag.embeddings import LexicalEmbedder
from app.rag.multilingual import normalize_question
from app.rag.store import KnowledgeIndex

log = logging.getLogger(__name__)

OFFICIAL_PREFIX = "official:"
INDEX_SCHEMA = "2026-11-25-official-v1"
SERVABLE = "verified"
TIME_SENSITIVE_TOPICS = {"international_trial", "airport_coverage", "announcements", "policy"}


def record_chunk(r: OfficialRecord, order: int) -> dict:
    body = r.body
    text = f"Q: {r.question}\nA: {body}" if r.question else body
    # Hindi records also carry the shared English concept normalisation so the ASCII
    # lexical index (and BM25) can match English, Hindi and Hinglish questions alike.
    embed = " ".join(x for x in (r.title, r.category or "", r.question or "", body) if x)
    if r.language == "hi":
        embed = f"{embed}\n{normalize_question(embed)}"
    return {
        "chunk_id": f"official-{r.id}-{r.content_hash[:12]}",
        "record_id": f"official-record-{r.id}",
        "source_file": f"{OFFICIAL_PREFIX}{r.source_id.split(':')[0]}",
        "doc_title": r.title[:300],
        "section": (r.category or r.title)[:200],
        "record_type": "faq" if r.question else "section",
        "question": r.question,
        "text": text,
        "embed_text": embed,
        "approval_status": "approved",          # verified official evidence (category B), not manifest-approved
        "category": r.topic,
        "as_of": r.published_on or r.updated_on or r.extracted_at.date().isoformat(),
        "verification_status": "verified",
        "content_hash": r.content_hash,
        "time_sensitive": r.topic in TIME_SENSITIVE_TOPICS or bool(r.expires_on),
        "conflict_ids": [],
        "urls": [r.url + (f"#{r.anchor}" if r.anchor and re.fullmatch(r"[\w-]{1,80}", r.anchor) else "")],
        "order": 1_000_000 + order,
        "effective_from": r.effective_from,
        "expires_on": r.expires_on,
        "language": r.language,
    }


def digest_of(rows: list[OfficialRecord]) -> str:
    return hashlib.sha256(json.dumps(sorted([r.id, r.content_hash] for r in rows)).encode()).hexdigest()


def servable_records(db: Database) -> list[OfficialRecord]:
    with db.session() as s:
        return list(s.scalars(select(OfficialRecord).where(OfficialRecord.status == SERVABLE)
                              .order_by(OfficialRecord.source_id, OfficialRecord.id)))


def active_publication(db: Database) -> KnowledgePublication | None:
    with db.session() as s:
        return s.scalar(select(KnowledgePublication).where(KnowledgePublication.status == "active"))


def publication_records(db: Database, pub: KnowledgePublication | None) -> list[OfficialRecord]:
    if pub is None or not pub.record_ids:
        return []
    with db.session() as s:
        rows = list(s.scalars(select(OfficialRecord).where(OfficialRecord.id.in_(pub.record_ids))
                              .order_by(OfficialRecord.source_id, OfficialRecord.id)))
    if digest_of(rows) != pub.digest:
        raise ValueError("Publication digest mismatch (records changed after publication)")
    return rows


def build_index(settings, index_dir: Path, base_chunks: list[dict], corpus: dict,
                records: list[OfficialRecord], pub: KnowledgePublication | None) -> KnowledgeIndex:
    """Build base corpus + published records into ``index_dir`` and validate the result."""
    chunks = list(base_chunks) + [record_chunk(r, i) for i, r in enumerate(records)]
    index = KnowledgeIndex(index_dir, settings.index_table)
    index.build(chunks, LexicalEmbedder(), extra_meta={
        "embedder_reason": "lexical (official publication build)", "corpus_sha256": corpus["corpus_sha256"],
        "requested_provider": settings.embedding_provider, "index_schema": INDEX_SCHEMA,
        "publication_id": pub.id if pub else None, "publication_digest": pub.digest if pub else None,
        "official_records": len(records), "base_chunk_count": len(base_chunks),
    })
    meta = index.meta()
    if meta["chunk_count"] != len(chunks):
        raise ValueError("Index validation failed (chunk count)")
    return index


def publish(db: Database, run_id: int | None, validate) -> tuple[KnowledgePublication | None, bool]:
    """Create a new active publication if the verified set changed. ``validate(records)`` must
    build a complete index (raises on failure) BEFORE the publication becomes active."""
    records = servable_records(db)
    digest = digest_of(records)
    current = active_publication(db)
    if current and current.digest == digest:
        return current, False
    validate(records)
    with db.session() as s:
        if s.get_bind().dialect.name == "postgresql":
            s.execute(text("LOCK TABLE knowledge_publication IN EXCLUSIVE MODE"))
        s.execute(update(KnowledgePublication).where(KnowledgePublication.status == "active")
                  .values(status="superseded"))
        s.flush()
        pub = KnowledgePublication(created_at=utcnow(), status="active", digest=digest,
                                   record_ids=[r.id for r in records], record_count=len(records), run_id=run_id)
        s.add(pub)
    return pub, True


class PublishedKnowledge:
    """API-side, version-aware index refresh. Checks the active publication at most every
    ``official_knowledge_refresh_check_s`` seconds, triggered lazily by chat traffic (no
    background polling loop), and rebuilds in a worker thread."""

    def __init__(self, settings, db: Database, swap, current: dict | None):
        self.s, self.db, self.swap = settings, db, swap
        self.version = (current or {}).get("publication_digest")
        self._checked = time.monotonic()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self.last_error: str | None = None

    def maybe_refresh(self) -> None:
        now = time.monotonic()
        if now - self._checked < self.s.official_knowledge_refresh_check_s:
            return
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._checked = now
            self._worker = threading.Thread(target=self.refresh, name="knowledge-refresh", daemon=True)
            self._worker.start()

    def refresh(self) -> bool:
        from app.rag.factory import build_retriever
        from ingestion.corpus import load_corpus

        try:
            pub = active_publication(self.db)
            digest = pub.digest if pub else None
            if digest == self.version:
                return False
            records = publication_records(self.db, pub)
            chunks, corpus = load_corpus(self.s.knowledge_corpus_dir)
            parent = self.s.index_dir.parent
            target = parent / f"{self.s.index_dir.name}-pub{pub.id if pub else 0}-{(digest or 'base')[:8]}-{os.getpid()}"
            if target.exists():
                shutil.rmtree(target)
            index = build_index(self.s, target, chunks, corpus, records, pub)
            retriever = build_retriever(self.s, index)
            self.swap(retriever, index.meta())
            self.version = digest
            self.last_error = None
            self._prune(parent, keep={target.name, self.s.index_dir.name})
            log.info("Knowledge publication %s active: %d official records", pub.id if pub else None, len(records))
            return True
        except Exception as exc:  # noqa: BLE001 - keep serving the last complete index
            self.last_error = type(exc).__name__
            log.warning("knowledge refresh failed error=%s (serving previous index)", type(exc).__name__)
            return False

    def _prune(self, parent: Path, keep: set[str]) -> None:
        prefix = f"{self.s.index_dir.name}-pub"
        olds = sorted((p for p in parent.glob(f"{prefix}*-{os.getpid()}") if p.name not in keep),
                      key=lambda p: p.stat().st_mtime)
        for p in olds[:-1]:  # keep one previous version for in-flight requests
            shutil.rmtree(p, ignore_errors=True)
