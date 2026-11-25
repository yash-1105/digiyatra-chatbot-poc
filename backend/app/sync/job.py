"""Pipeline A — short-lived official-knowledge synchronisation job.

    sources due -> fetch (conditional) -> extract -> validate -> deduplicate -> persist
                -> build + validate index -> publish (atomic) -> close -> exit

Designed for one Railway cron execution per week (``30 21 * * 6`` = Sunday 03:00 IST).
State lives in PostgreSQL, so restarts/redeploys never reset schedules, and a failed or
partial fetch never deletes or replaces previously verified knowledge.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import resource
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.db.models import JobLease, KnowledgePublication, OfficialRecord, OfficialSource, SyncRun
from app.db.session import Database, utcnow
from app.sync import extract as X
from app.sync import policy as P
from app.sync.fetcher import FetchError, SecureFetcher
from app.sync.pdf import extract_pdf
from app.sync.publish import build_index, publish
from app.sync.sources import CHILD_LINKS, SOURCES, SourceSpec, accept_child, child_id, child_type, interval_days

log = logging.getLogger(__name__)
INDIA = ZoneInfo("Asia/Kolkata")
LEASE = "official-knowledge-sync"
ACTIVE = ("verified", "pending_review", "conflict", "historical")
_PROVENANCE = {"topic", "risk", "historical_after_days", "organization", "authority", "source_kind", "platform",
               "external_id", "account_id", "account_name", "start_s"}
# Railway list prices (docs.railway.com/reference/pricing/plans, checked 2026-11-25).
VCPU_MINUTE_USD, GB_MINUTE_USD = 0.000463, 0.000231


# --------------------------------------------------------------------------- lease
def acquire_lease(db: Database, ttl_s: int, name: str = LEASE) -> str | None:
    token, now = uuid.uuid4().hex, utcnow()
    try:
        with db.session() as s:
            row = s.get(JobLease, name, with_for_update=True)
            if row is not None and row.expires_at > now:
                return None
            if row is None:
                s.add(JobLease(name=name, holder=token, acquired_at=now, expires_at=now + timedelta(seconds=ttl_s)))
            else:
                row.holder, row.acquired_at, row.expires_at = token, now, now + timedelta(seconds=ttl_s)
    except IntegrityError:
        return None  # another process inserted the lease first
    return token


def release_lease(db: Database, token: str, name: str = LEASE) -> None:
    with db.session() as s:
        row = s.get(JobLease, name, with_for_update=True)
        if row is not None and row.holder == token:
            s.delete(row)


# --------------------------------------------------------------------------- registry
def spec_for(row: OfficialSource) -> SourceSpec:
    """Static spec, or a spec for a discovered child that inherits its parent's policy."""
    if row.source_id in SOURCES:
        return SOURCES[row.source_id]
    parent = SOURCES.get((row.parent_id or "").split(":")[0])
    return SourceSpec(
        row.source_id, row.canonical_url, row.organization, row.source_type, row.language, row.trust,
        "weekly" if row.refresh_days <= 7 else "fortnightly", row.topic, row.risk,
        discovery=CHILD_LINKS if row.source_type == "discovery_links" else None,
        historical_after_days=parent.historical_after_days if parent else None,
    )


def sync_registry(db: Database, settings) -> None:
    now = utcnow()
    with db.session() as s:
        for spec in SOURCES.values():
            row = s.get(OfficialSource, spec.source_id)
            days = interval_days(spec.cadence, settings)
            if row is None:
                s.add(OfficialSource(
                    source_id=spec.source_id, parent_id=None, canonical_url=spec.url, organization=spec.organization,
                    source_type=spec.source_type, language=spec.language, trust=spec.trust, topic=spec.topic,
                    risk=spec.risk, enabled=spec.enabled, refresh_days=days, next_due_at=now, content_version=0,
                    verification_status="never_synced", consecutive_failures=0, created_at=now,
                ))
            else:  # code-defined attributes follow the registry; enablement stays operator-controlled
                row.canonical_url, row.source_type, row.topic, row.risk = spec.url, spec.source_type, spec.topic, spec.risk
                row.organization, row.language, row.trust, row.refresh_days = spec.organization, spec.language, spec.trust, days


def set_enabled(db: Database, source_id: str, enabled: bool) -> None:
    with db.session() as s:
        row = s.get(OfficialSource, source_id)
        if row is None:
            raise ValueError("Unknown source")
        row.enabled = enabled


# --------------------------------------------------------------------------- job
@dataclass
class RunStats:
    sources_due: int = 0
    sources_processed: int = 0
    fetches: int = 0
    unchanged: int = 0
    not_modified: int = 0
    changed_sources: int = 0
    failed_sources: int = 0
    discovered: int = 0
    new_records: int = 0
    updated_records: int = 0
    withdrawn_records: int = 0
    pending_review: int = 0
    historical_records: int = 0
    stripped_statistics: int = 0
    duplicates: int = 0
    social_posts_seen: int = 0
    videos_seen: int = 0
    failures: dict = field(default_factory=dict)
    publication: dict = field(default_factory=dict)
    resources: dict = field(default_factory=dict)


class SyncJob:
    def __init__(self, settings, db: Database, *, fetcher: SecureFetcher | None = None, today: date | None = None,
                 index_validator=None):
        self.s, self.db = settings, db
        self.today = today or datetime.now(INDIA).date()
        self.stats = RunStats()
        self._fetcher = fetcher
        self.started = time.monotonic()
        self.deadline = self.started + settings.sync_max_runtime_s
        self.index_validator = index_validator or self._validate_index
        self.run_id: int | None = None

    # ------------------------------------------------------------------ orchestration
    def run(self, trigger: str = "schedule", force: list[str] | None = None, publish_only: bool = False) -> int:
        sync_registry(self.db, self.s)
        token = acquire_lease(self.db, self.s.sync_lock_ttl_s)
        if token is None:
            log.warning("sync skipped: another synchronisation holds the lease")
            return 2
        stop = threading.Event()
        watchdog = threading.Thread(target=self._watchdog, args=(stop,), daemon=True)
        watchdog.start()
        status = "failed"
        try:
            self._recover_interrupted()
            with self.db.session() as s:
                run = SyncRun(started_at=utcnow(), status="running", trigger=trigger[:24], stats={})
                s.add(run)
                s.flush()
                self.run_id = run.id
            if not publish_only:
                fetcher = self._fetcher or SecureFetcher(self.s, deadline=self.deadline)
                try:
                    self._process_due(fetcher, force)
                finally:
                    self.stats.fetches = fetcher.stats.requests
                    self.stats.not_modified = fetcher.stats.not_modified
                    if self._fetcher is None:
                        fetcher.close()
            try:
                pub, changed = publish(self.db, self.run_id, self.index_validator)
                self.stats.publication = {"id": pub.id if pub else None, "changed": changed,
                                          "records": pub.record_count if pub else 0}
                status = "partial" if self.stats.failed_sources else "ok"
            except Exception as exc:  # noqa: BLE001 - previous publication stays active
                self.stats.publication = {"error": type(exc).__name__, "changed": False}
                status = "index_validation_failed"
            return 0 if status == "ok" else 1
        finally:
            stop.set()
            self._finish(status)
            release_lease(self.db, token)

    def _watchdog(self, stop: threading.Event) -> None:
        # Hard stop: a hung parser or socket can never keep a paid container alive.
        if not stop.wait(self.s.sync_max_runtime_s + 60):
            log.error("sync exceeded maximum runtime; terminating")
            os._exit(4)

    def _recover_interrupted(self) -> None:
        cutoff = utcnow() - timedelta(seconds=self.s.sync_lock_ttl_s)
        with self.db.session() as s:
            s.execute(update(SyncRun).where(SyncRun.status == "running", SyncRun.started_at < cutoff)
                      .values(status="interrupted", finished_at=utcnow()))

    def _finish(self, status: str) -> None:
        own, kids = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
        runtime = time.monotonic() - self.started
        cpu = own.ru_utime + own.ru_stime + kids.ru_utime + kids.ru_stime
        rss_mb = max(own.ru_maxrss, kids.ru_maxrss) / 1024
        with self.db.session() as s:
            storage = s.execute(select(func.count(OfficialRecord.id), func.coalesce(func.sum(func.length(OfficialRecord.body)), 0))).one()
        self.stats.resources = {
            "runtime_s": round(runtime, 1), "cpu_s": round(cpu, 1), "max_rss_mb": round(rss_mb, 1),
            "records_total": storage[0], "record_text_bytes": int(storage[1]),
            # Usage-based estimate: CPU seconds actually used + peak memory held for the runtime.
            "estimated_usd": round(cpu / 60 * VCPU_MINUTE_USD + rss_mb / 1024 * runtime / 60 * GB_MINUTE_USD, 6),
        }
        if self.run_id is not None:
            with self.db.session() as s:
                run = s.get(SyncRun, self.run_id)
                run.status, run.finished_at, run.stats = status, utcnow(), self.stats.__dict__
        log.info("sync finished status=%s %s", status, self.stats.resources)

    # ------------------------------------------------------------------ sources
    def _due(self, force: list[str] | None) -> list[str]:
        now = utcnow()
        with self.db.session() as s:
            q = select(OfficialSource.source_id).where(OfficialSource.enabled.is_(True))
            q = q.where(OfficialSource.source_id.in_(force)) if force else q.where(OfficialSource.next_due_at <= now)
            ids = list(s.scalars(q.order_by(OfficialSource.parent_id.is_not(None), OfficialSource.refresh_days,
                                            OfficialSource.source_id)))
        if force and (unknown := set(force) - set(ids)):
            raise ValueError(f"Unknown or disabled source(s): {', '.join(sorted(unknown))}")
        return ids

    def _process_due(self, fetcher: SecureFetcher, force: list[str] | None) -> None:
        queue = self._due(force)
        self.stats.sources_due = len(queue)
        seen: set[str] = set()
        while queue:
            if time.monotonic() > self.deadline - 5 or fetcher.stats.requests >= self.s.sync_max_fetches_per_run:
                self.stats.failures["budget_exhausted_remaining"] = len(queue)
                break  # remaining sources stay due for the next run
            sid = queue.pop(0)
            if sid in seen:
                continue
            seen.add(sid)
            with self.db.session() as s:
                row = s.get(OfficialSource, sid)
            if row is None or not row.enabled:
                continue
            self.stats.sources_processed += 1
            new_children = self._process(fetcher, row)
            queue.extend(c for c in new_children if c not in seen)

    def _process(self, fetcher: SecureFetcher, row: OfficialSource) -> list[str]:
        spec = spec_for(row)
        try:
            if spec.source_type.startswith("discovery_"):
                return self._discover(fetcher, row, spec)
            if spec.source_type in ("youtube_channel", "account_registry", "transcript", "social_import"):
                from app.sync import media

                media.process(self, fetcher, row, spec)
                return []
            kind = "pdf" if spec.source_type == "pdf" else "html"
            res = fetcher.get(row.canonical_url, kind, etag=row.etag, last_modified=row.last_modified)
            if res.not_modified:
                self._unchanged(row, 304, res.etag, res.last_modified)
                return []
            digest = hashlib.sha256(res.body).hexdigest()
            if digest == row.content_hash:
                self._unchanged(row, 200, res.etag, res.last_modified)
                return []
            self._ingest(row, spec, kind, [res.body], digest, res.etag, res.last_modified)
            return []
        except FetchError as exc:
            self._failed(row, exc)
            return []

    def _ingest(self, row: OfficialSource, spec: SourceSpec, kind: str, bodies: list[bytes], digest: str,
                etag=None, modified=None, *, capture_flags: list[str] | None = None) -> None:
        """Extract -> validate -> persist. Several bodies (operator captures of one page, e.g. one file
        per FAQ tab) are merged into one extraction before validation."""
        ex = X.merge([self._extract(spec, kind, b) for b in bodies])
        assessment = P.assess(row.source_id, spec, ex, row.canonical_url)
        self.stats.stripped_statistics += assessment.stripped_statistics
        if not assessment.complete:
            raise FetchError(assessment.reason or "incomplete_extraction", 200)
        if capture_flags is not None:
            for c in assessment.candidates:
                c.flags.extend(capture_flags)
        self._persist(row, spec, assessment.candidates, digest, etag, modified,
                      operator_capture=capture_flags is not None)

    def _extract(self, spec: SourceSpec, kind: str, body: bytes) -> X.Extraction:
        if kind == "pdf":
            pdf = extract_pdf(body, max_pages=self.s.sync_max_pdf_pages)
            if not pdf.ok:
                raise FetchError(f"pdf_{pdf.reason}", 200)
            ex = X.Extraction(title=pdf.title or spec.organization, language=X.language_of("\n".join(pdf.pages)))
            ex.sections = [X.Section(f"Page {i}", text, f"page={i}") for i, text in enumerate(pdf.pages, 1) if text.strip()]
            ex.text_chars = sum(len(p) for p in pdf.pages)
            return ex
        return X.extract_html(body.decode("utf-8", "replace"), spec.section_filter)

    def _discover(self, fetcher: SecureFetcher, row: OfficialSource, spec: SourceSpec) -> list[str]:
        assert spec.discovery
        urls: list[tuple[str, str]] = []
        pages = (row.canonical_url, *spec.discovery.pages)
        errors = []
        for page in pages:
            candidates = (page, *spec.fallbacks) if page == row.canonical_url else (page,)
            for url in candidates:
                try:
                    kind = "xml" if spec.source_type in ("discovery_rss", "discovery_sitemap") else "html"
                    res = fetcher.get(url, kind)
                except FetchError as exc:
                    errors.append(exc)
                    continue
                if spec.source_type == "discovery_rss":
                    urls += [(link, text) for link, text, _ in X.parse_feed(res.body)]
                elif spec.source_type == "discovery_sitemap":
                    urls += [(u, "") for u in X.parse_sitemap(res.body)]
                else:
                    ex = X.extract_html(res.body.decode("utf-8", "replace"))
                    if ex.blocked:
                        errors.append(FetchError("blocked_page_returned", 200))
                        continue
                    base = res.url
                    urls += [(urljoin(base, h), t) for h, t in ex.links]
                    if spec.source_type == "discovery_links" and b"twitter-tweet" in res.body:
                        from app.sync import media

                        media.persist_embedded_posts(self, row, spec, res.body.decode("utf-8", "replace"))
                break
        if not urls and errors:
            raise errors[0]
        accepted: list[str] = []
        for link, text in urls:
            canon = accept_child(spec, link, text)
            if canon and canon not in accepted and canon != row.canonical_url:
                accepted.append(canon)
            if len(accepted) >= spec.discovery.max_children:
                break
        children = self._register_children(row, spec, accepted)
        digest = hashlib.sha256("\n".join(sorted(accepted)).encode()).hexdigest()
        with self.db.session() as s:
            r = s.get(OfficialSource, row.source_id)
            changed = digest != r.content_hash
            r.http_status, r.last_attempt_at, r.last_success_at = 200, utcnow(), utcnow()
            r.content_hash, r.consecutive_failures, r.failure_reason = digest, 0, None
            r.content_version += int(changed)
            r.verification_status = "discovery_ok"
            r.next_due_at = utcnow() + timedelta(days=r.refresh_days)
        return children

    def _register_children(self, row: OfficialSource, spec: SourceSpec, urls: list[str]) -> list[str]:
        disc = spec.discovery
        due: list[str] = []
        now = utcnow()
        with self.db.session() as s:
            for url in urls:
                existing = s.scalar(select(OfficialSource).where(OfficialSource.canonical_url == url))
                if existing is not None:
                    if existing.enabled and existing.next_due_at <= now:
                        due.append(existing.source_id)
                    continue
                ctype = child_type(url)
                sid = child_id(row.source_id.split(":")[0], url)
                s.add(OfficialSource(
                    source_id=sid, parent_id=row.source_id, canonical_url=url, organization=spec.organization if
                    "civilaviation" not in url and "pib.gov.in" not in url else
                    ("Press Information Bureau" if "pib.gov.in" in url else "Ministry of Civil Aviation"),
                    source_type=ctype, language="hi" if "/hi/" in url else spec.language,
                    trust="official_press" if "pib.gov.in" in url else spec.trust,
                    topic=disc.child_topic if ctype != "pdf" else "policy", risk=disc.child_risk, enabled=True,
                    refresh_days=interval_days(disc.child_cadence, self.s), next_due_at=now, content_version=0,
                    verification_status="never_synced", consecutive_failures=0, created_at=now,
                ))
                due.append(sid)
                self.stats.discovered += 1
        return due

    # ------------------------------------------------------------------ persistence
    def _unchanged(self, row: OfficialSource, status: int, etag, modified) -> None:
        self.stats.unchanged += 1
        with self.db.session() as s:
            r = s.get(OfficialSource, row.source_id)
            r.http_status, r.last_attempt_at, r.last_success_at = status, utcnow(), utcnow()
            r.etag, r.last_modified = etag or r.etag, modified or r.last_modified
            r.consecutive_failures, r.failure_reason = 0, None
            r.next_due_at = utcnow() + timedelta(days=r.refresh_days)

    def _failed(self, row: OfficialSource, exc: FetchError) -> None:
        self.stats.failed_sources += 1
        self.stats.failures[exc.reason] = self.stats.failures.get(exc.reason, 0) + 1
        withdraw = exc.status == 410 or (exc.status == 404 and row.consecutive_failures >= 1)
        with self.db.session() as s:
            r = s.get(OfficialSource, row.source_id)
            r.http_status, r.last_attempt_at = exc.status, utcnow()
            r.consecutive_failures += 1
            r.failure_reason = exc.reason[:160]
            r.verification_status = "withdrawn" if withdraw else "failed_last_known_good"
            # Retry at the next scheduled run; previously verified records are kept as-is.
            r.next_due_at = utcnow()
            if withdraw:
                n = s.execute(update(OfficialRecord).where(OfficialRecord.source_id == r.source_id,
                                                           OfficialRecord.status.in_(ACTIVE))
                              .values(status="withdrawn", review_reason=f"source {exc.reason}")).rowcount
                self.stats.withdrawn_records += n or 0

    def _persist(self, row: OfficialSource, spec: SourceSpec, cands: list[P.Candidate], digest: str,
                 etag, modified, *, operator_capture: bool = False, keep_keys: set[str] | None = None,
                 replace_missing: bool = False) -> None:
        now = utcnow()
        with self.db.session() as s:
            src = s.get(OfficialSource, row.source_id, with_for_update=True)
            # Current record per key: the verified version if any (last-known-good), else the newest.
            latest: dict[str, OfficialRecord] = {}
            for rec in s.scalars(select(OfficialRecord).where(OfficialRecord.source_id == src.source_id,
                                                              OfficialRecord.status.in_(ACTIVE))
                                 .order_by(OfficialRecord.version)):
                cur = latest.get(rec.record_key)
                if cur is None or rec.status == "verified" or cur.status != "verified":
                    latest[rec.record_key] = rec
            verified_counts: dict[int, str | None] = {}
            for rec in s.scalars(select(OfficialRecord).where(OfficialRecord.status == "verified",
                                                              OfficialRecord.topic == spec.topic,
                                                              OfficialRecord.source_id != src.source_id)):
                for n in P.airport_counts(rec.body):
                    verified_counts[n] = rec.published_on
            changed = False
            seen_keys = set()
            for c in cands:
                seen_keys.add(c.record_key)
                cspec = replace(spec, topic=c.extra.get("topic", spec.topic), risk=c.extra.get("risk", spec.risk),
                                historical_after_days=c.extra.get("historical_after_days", spec.historical_after_days))
                prev = latest.get(c.record_key)
                if prev is not None and prev.content_hash == c.content_hash:
                    continue
                dup = s.scalar(select(OfficialRecord.id).where(OfficialRecord.source_id == src.source_id,
                                                               OfficialRecord.record_key == c.record_key,
                                                               OfficialRecord.content_hash == c.content_hash))
                if dup is not None:
                    continue  # identical content already stored (e.g. rejected earlier); never re-queue
                same_text = s.scalar(select(OfficialRecord.id).where(
                    OfficialRecord.source_id != src.source_id, OfficialRecord.status.in_(ACTIVE),
                    OfficialRecord.body == c.body[:20000],
                    (OfficialRecord.question == c.question) if c.question else OfficialRecord.question.is_(None)).limit(1))
                same_post = c.extra.get("external_id") and s.scalar(select(OfficialRecord.id).where(
                    OfficialRecord.source_id != src.source_id, OfficialRecord.status.in_(ACTIVE),
                    OfficialRecord.platform == c.extra.get("platform"),
                    OfficialRecord.external_id == c.extra["external_id"],
                    OfficialRecord.record_type == c.record_type).limit(1))
                if same_text is not None or same_post:
                    self.stats.duplicates += 1  # same text / same post ID published under another official URL
                    seen_keys.add(c.record_key)
                    continue
                changed = True
                if P.is_historical(cspec, c.published_on, self.today):
                    status, reason = "historical", "dated announcement older than the historical threshold"
                    self.stats.historical_records += 1
                else:
                    status, reason = P.review_decision(cspec, c, first_version=prev is None,
                                                       auto_publish=self.s.knowledge_auto_publish_enabled and not operator_capture,
                                                       conflicts=P.detect_conflicts(c, verified_counts) if cspec.topic in
                                                       {"airport_coverage", "announcements", "international_trial"} else [])
                    if operator_capture:
                        reason = "operator capture: " + (reason or "requires review")
                if c.flags:
                    reason = "; ".join([reason or "", *c.flags]).strip("; ")[:300]
                if spec.source_type == "pdf" and "Vatra" in c.body:
                    reason = ((reason or "") + "; OCR text layer with recognition errors").strip("; ")
                if status in ("pending_review", "conflict"):
                    self.stats.pending_review += 1
                # Only one unreviewed version per record is ever queued.
                s.execute(update(OfficialRecord).where(OfficialRecord.source_id == src.source_id,
                                                       OfficialRecord.record_key == c.record_key,
                                                       OfficialRecord.status.in_(("pending_review", "conflict")))
                          .values(status="superseded"))
                s.add(OfficialRecord(
                    source_id=src.source_id, record_key=c.record_key, version=(prev.version + 1) if prev else 1,
                    content_hash=c.content_hash, status=status, record_type=c.record_type, title=c.title[:300],
                    category=(c.category or None) and c.category[:200], question=c.question and c.question[:600],
                    body=c.body[:20000], url=(c.url or src.canonical_url)[:700], anchor=c.anchor and c.anchor[:120],
                    organization=c.extra.get("organization") or src.organization, language=c.language,
                    authority=c.extra.get("authority") or src.trust, topic=cspec.topic,
                    risk=cspec.risk, published_on=c.published_on, updated_on=c.updated_on,
                    effective_from=c.effective_from, expires_on=c.expires_on, extracted_at=now,
                    review_reason=reason, source_kind=c.extra.get("source_kind"), platform=c.extra.get("platform"),
                    external_id=c.extra.get("external_id"), account_id=c.extra.get("account_id"),
                    account_name=c.extra.get("account_name"), start_s=c.extra.get("start_s"),
                    media={k: v for k, v in c.extra.items() if k not in _PROVENANCE} or None,
                ))
                if prev is None:
                    self.stats.new_records += 1
                else:
                    self.stats.updated_records += 1
                    # A verified version stays served (last-known-good) until its replacement is
                    # reviewed; an older unreviewed version is simply replaced in the queue.
                    if status == "verified":
                        prev.status = "superseded"
            # Withdrawn content: only when the new extraction is complete and not suspiciously small.
            active_keys = {k for k, r in latest.items() if r.status in ("verified", "pending_review", "conflict")}
            missing = active_keys - seen_keys - (keep_keys or set())
            if missing and replace_missing:
                # A complete replacement (e.g. a corrected transcript file): older passages are superseded.
                for key in missing:
                    s.execute(update(OfficialRecord).where(OfficialRecord.source_id == src.source_id,
                                                           OfficialRecord.record_key == key,
                                                           OfficialRecord.status.in_(ACTIVE))
                              .values(status="superseded", review_reason="replaced by a corrected transcript"))
                changed = True
            elif missing and operator_capture:
                pass  # a capture may cover part of a page (one tab); it never withdraws records
            elif missing and len(seen_keys & active_keys) >= 0.5 * len(active_keys):
                for key in missing:
                    s.execute(update(OfficialRecord).where(OfficialRecord.source_id == src.source_id,
                                                           OfficialRecord.record_key == key,
                                                           OfficialRecord.status.in_(ACTIVE))
                              .values(status="withdrawn", review_reason="no longer present on the official page"))
                    self.stats.withdrawn_records += 1
                changed = True
            elif missing:
                self.stats.failures["suspicious_shrink_kept_previous"] = self.stats.failures.get(
                    "suspicious_shrink_kept_previous", 0) + 1
            self.stats.changed_sources += int(changed)
            if not changed:
                self.stats.unchanged += 1
            src.http_status, src.last_attempt_at, src.last_success_at = 200, now, now
            src.etag, src.last_modified, src.content_hash = etag, modified, digest
            src.content_version += int(changed)
            src.consecutive_failures, src.failure_reason = 0, None
            src.verification_status = "operator_capture" if operator_capture else "extracted"
            src.next_due_at = now + timedelta(days=src.refresh_days)

    # ------------------------------------------------------------------ manual import / review
    def import_capture(self, source_id: str | None, files: list[bytes], url: str | None = None) -> dict:
        """Operator-saved HTML/PDF of an official page that blocks automated access.

        * ``source_id`` must be registered, or ``url`` must be an allow-listed Foundation page that
          passes the Foundation sitemap discovery rules (it is then registered as a child source).
        * A URL embedded in the saved file (canonical / og:url / "saved from") must match the page.
        * Never auto-verified and never withdraws records: every record requires human review.
        """
        sync_registry(self.db, self.s)
        if url:
            spec = SOURCES["dyf-sitemap"]
            canon = accept_child(spec, url)
            if not canon:
                raise ValueError("URL is not an allow-listed official page eligible for manual import")
            with self.db.session() as s:
                existing = s.scalar(select(OfficialSource.source_id).where(OfficialSource.canonical_url == canon))
            source_id = existing or self._register_children(self._row("dyf-sitemap"), spec, [canon])[0]
        if not source_id:
            raise ValueError("A registered source ID or an eligible URL is required")
        row = self._row(source_id)
        if row is None:
            raise ValueError("Unknown source")
        if row.source_type.startswith("discovery_"):
            raise ValueError("Captures are accepted for content sources only")
        if not files:
            raise ValueError("No capture files supplied")
        flags = []
        for data in files:
            flags.append(P.capture_provenance(data, row.canonical_url))
        token = acquire_lease(self.db, self.s.sync_lock_ttl_s)
        if token is None:
            raise RuntimeError("A synchronisation is running")
        try:
            kind = "pdf" if files[0].startswith(b"%PDF-") else "html"
            if any(f.startswith(b"%PDF-") != (kind == "pdf") for f in files):
                raise ValueError("Do not mix PDF and HTML captures of one page")
            digest = hashlib.sha256(b"".join(hashlib.sha256(f).digest() for f in files)).hexdigest()
            try:
                self._ingest(row, spec_for(row), kind, files, digest,
                             capture_flags=["operator capture: " + "; ".join(sorted(set(flags)))])
            except FetchError as exc:
                raise ValueError(f"Capture rejected: {exc.reason}") from exc
            return {"source_id": row.source_id, "url": row.canonical_url, "new_records": self.stats.new_records,
                    "updated_records": self.stats.updated_records, "provenance": sorted(set(flags))}
        finally:
            release_lease(self.db, token)

    def locked(self, fn, *args, **kwargs):
        """Run an operator import under the job lease (never concurrently with a sync)."""
        sync_registry(self.db, self.s)
        token = acquire_lease(self.db, self.s.sync_lock_ttl_s)
        if token is None:
            raise RuntimeError("A synchronisation is running")
        try:
            return fn(self, *args, **kwargs)
        finally:
            release_lease(self.db, token)

    def _row(self, source_id: str) -> OfficialSource | None:
        with self.db.session() as s:
            return s.get(OfficialSource, source_id)

    def _validate_index(self, records) -> None:
        from ingestion.corpus import load_corpus

        chunks, corpus = load_corpus(self.s.knowledge_corpus_dir)
        tmp = Path(tempfile.mkdtemp(prefix="pubcheck-", dir=self.s.index_dir.parent if self.s.index_dir.parent.exists() else None))
        try:
            pub = KnowledgePublication(id=0, digest="validation", record_ids=[r.id for r in records])
            build_index(self.s, tmp, chunks, corpus, records, pub)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def review_source(db: Database, source_id: str, decision: str, reviewer: str) -> int:
    """Bulk decision for every pending/conflict record of one source (e.g. a reviewed PDF)."""
    with db.session() as s:
        ids = list(s.scalars(select(OfficialRecord.id).where(OfficialRecord.source_id == source_id,
                                                             OfficialRecord.status.in_(("pending_review", "conflict")))))
    for rid in ids:
        review_record(db, rid, decision, reviewer)
    return len(ids)


def review_record(db: Database, record_id: int, decision: str, reviewer: str) -> None:
    if decision not in {"verified", "rejected", "revoked"} or not re.fullmatch(r"[\w .@-]{1,80}", reviewer):
        raise ValueError("Invalid review decision")
    with db.session() as s:
        rec = s.get(OfficialRecord, record_id, with_for_update=True)
        # "revoked" withdraws an approval: the record stops being served and returns to the review queue.
        allowed = {("pending_review", "verified"), ("conflict", "verified"), ("pending_review", "rejected"),
                   ("conflict", "rejected"), ("verified", "revoked"), ("historical", "rejected")}
        if rec is None or (rec.status, decision) not in allowed:
            raise ValueError("Invalid record transition")
        if decision == "verified":
            s.execute(update(OfficialRecord).where(OfficialRecord.source_id == rec.source_id,
                                                   OfficialRecord.record_key == rec.record_key,
                                                   OfficialRecord.status == "verified",
                                                   OfficialRecord.id != rec.id).values(status="superseded"))
        if decision == "revoked":
            rec.status, rec.review_reason = "pending_review", ((rec.review_reason or "") + f"; approval revoked by {reviewer}")[-300:]
        else:
            rec.status = decision
        rec.reviewer, rec.reviewed_at = reviewer, utcnow()


def status_report(db: Database, settings) -> dict:
    now = utcnow()
    with db.session() as s:
        sources = list(s.scalars(select(OfficialSource).order_by(OfficialSource.parent_id.is_not(None), OfficialSource.source_id)))
        counts = dict(s.execute(select(OfficialRecord.status, func.count()).group_by(OfficialRecord.status)).all())
        last_ok = s.scalar(select(func.max(SyncRun.finished_at)).where(SyncRun.status.in_(("ok", "partial"))))
        runs = list(s.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(5)))
        pub = s.scalar(select(KnowledgePublication).where(KnowledgePublication.status == "active"))
    return {
        "generated_at": now.isoformat(timespec="seconds") + "Z",
        "last_successful_sync": last_ok.isoformat(timespec="seconds") + "Z" if last_ok else None,
        "active_publication": {"id": pub.id, "records": pub.record_count, "created_at": pub.created_at.isoformat(timespec="seconds") + "Z",
                               "digest": pub.digest[:16]} if pub else None,
        "records_by_status": counts,
        "sources_total": len(sources),
        "sources_due": sum(1 for r in sources if r.enabled and r.next_due_at <= now),
        "sources_failed": [{"source_id": r.source_id, "reason": r.failure_reason, "http_status": r.http_status,
                            "consecutive_failures": r.consecutive_failures} for r in sources if r.consecutive_failures],
        "next_scheduled_refresh": min((r.next_due_at for r in sources if r.enabled), default=None) and
        min(r.next_due_at for r in sources if r.enabled).isoformat(timespec="seconds") + "Z",
        "sources": [{"source_id": r.source_id, "parent": r.parent_id, "url": r.canonical_url, "type": r.source_type,
                     "organization": r.organization, "language": r.language, "trust": r.trust, "topic": r.topic,
                     "enabled": r.enabled, "refresh_days": r.refresh_days, "http_status": r.http_status,
                     "last_attempt": r.last_attempt_at and r.last_attempt_at.isoformat(timespec="seconds") + "Z",
                     "last_success": r.last_success_at and r.last_success_at.isoformat(timespec="seconds") + "Z",
                     "next_due": r.next_due_at.isoformat(timespec="seconds") + "Z", "etag": bool(r.etag),
                     "last_modified": r.last_modified, "content_version": r.content_version,
                     "content_hash": (r.content_hash or "")[:12] or None, "status": r.verification_status,
                     "failures": r.consecutive_failures, "failure_reason": r.failure_reason} for r in sources],
        "recent_runs": [{"id": r.id, "status": r.status, "trigger": r.trigger, "started": r.started_at.isoformat(timespec="seconds") + "Z",
                         **{k: r.stats.get(k) for k in ("sources_processed", "fetches", "unchanged", "new_records",
                                                        "updated_records", "pending_review", "failed_sources",
                                                        "publication", "resources")}} for r in runs],
        "schedule": {"cron_utc": "30 21 * * 6", "weekly_days": settings.sync_weekly_days,
                     "fortnightly_days": settings.sync_fortnightly_days},
    }


def pending_records(db: Database, limit: int = 200) -> list[dict]:
    with db.session() as s:
        rows = s.scalars(select(OfficialRecord).where(OfficialRecord.status.in_(("pending_review", "conflict")))
                         .order_by(OfficialRecord.source_id, OfficialRecord.id).limit(limit))
        return [{"id": r.id, "source_id": r.source_id, "status": r.status, "topic": r.topic, "language": r.language,
                 "title": r.title, "category": r.category, "question": r.question, "published_on": r.published_on,
                 "effective_from": r.effective_from, "expires_on": r.expires_on, "reason": r.review_reason,
                 "url": r.url, "body": r.body} for r in rows]

