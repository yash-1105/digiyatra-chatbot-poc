"""Move reviewed official knowledge between databases (e.g. local dev -> production) safely.

Deploying application code does NOT copy any local database. This bundle is the only path:

* ``export_bundle``: official sources + records (no ids, no chat/analytics data), with a SHA-256
  digest over the canonical payload; written 0600.
* ``import_bundle``: INSERT-ONLY. Existing production sources, records, schedules, reviews and
  publications are never updated or deleted. Identical records are skipped (idempotent). A record
  whose key already has a different *verified* production version is imported as ``pending_review``
  (never superseding production automatically). ``as_pending=True`` re-queues every imported record
  for production review. Publication remains a separate, validated ``sync-publish`` step.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

from app.db.models import OfficialRecord, OfficialSource
from app.db.session import Database, utcnow

FORMAT = "dy-official-knowledge-bundle/1"
SOURCE_FIELDS = ("source_id", "parent_id", "canonical_url", "organization", "source_type", "language", "trust",
                 "topic", "risk", "refresh_days")
RECORD_FIELDS = ("source_id", "record_key", "version", "content_hash", "status", "record_type", "title", "category",
                 "question", "body", "url", "anchor", "organization", "language", "authority", "topic", "risk",
                 "published_on", "updated_on", "effective_from", "expires_on", "review_reason", "reviewer")
EXPORTABLE = ("verified", "pending_review", "conflict", "historical")


def _digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def export_bundle(db: Database, path: Path, statuses=EXPORTABLE) -> dict:
    with db.session() as s:
        recs = list(s.scalars(select(OfficialRecord).where(OfficialRecord.status.in_(statuses))
                              .order_by(OfficialRecord.source_id, OfficialRecord.record_key, OfficialRecord.version)))
        ids = {r.source_id for r in recs}
        srcs = [x for x in s.scalars(select(OfficialSource).order_by(OfficialSource.source_id)) if x.source_id in ids
                or x.parent_id is None]
        payload = {
            "format": FORMAT,
            "sources": [{f: getattr(x, f) for f in SOURCE_FIELDS} for x in srcs],
            "records": [{**{f: getattr(r, f) for f in RECORD_FIELDS},
                         "extracted_at": r.extracted_at.isoformat(timespec="seconds"),
                         "reviewed_at": r.reviewed_at.isoformat(timespec="seconds") if r.reviewed_at else None}
                        for r in recs],
        }
    bundle = {**payload, "created_at": datetime.now(UTC).isoformat(timespec="seconds"), "sha256": _digest(payload)}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n")
    path.chmod(0o600)
    return {"path": str(path), "sources": len(payload["sources"]), "records": len(payload["records"]),
            "sha256": bundle["sha256"]}


def import_bundle(db: Database, path: Path, *, dry_run: bool = False, as_pending: bool = False) -> dict:
    bundle = json.loads(Path(path).read_text())
    payload = {k: bundle[k] for k in ("format", "sources", "records")}
    if bundle.get("format") != FORMAT or bundle.get("sha256") != _digest(payload):
        raise ValueError("Bundle format or SHA-256 digest is invalid (tampered or truncated)")
    from app.sync.sources import canonical_url

    summary = {"sources_added": 0, "sources_kept": 0, "records_added": 0, "records_skipped_identical": 0,
               "records_as_pending_due_to_production_version": 0, "records_by_status": {}}
    now = utcnow()
    with db.session() as s:
        for src in payload["sources"]:
            if not canonical_url(src["canonical_url"]):
                raise ValueError(f"Bundle source URL is not allow-listed: {src['source_id']}")
            if s.get(OfficialSource, src["source_id"]) is not None or s.scalar(
                    select(OfficialSource.source_id).where(OfficialSource.canonical_url == src["canonical_url"])):
                summary["sources_kept"] += 1  # production schedule/state is authoritative
                continue
            summary["sources_added"] += 1
            if not dry_run:
                s.add(OfficialSource(**src, enabled=True, next_due_at=now, content_version=0,
                                     verification_status="imported_bundle", consecutive_failures=0, created_at=now))
        if not dry_run:
            s.flush()
        for rec in payload["records"]:
            exists = s.scalar(select(OfficialRecord.id).where(
                OfficialRecord.source_id == rec["source_id"], OfficialRecord.record_key == rec["record_key"],
                OfficialRecord.content_hash == rec["content_hash"]))
            if exists is not None:
                summary["records_skipped_identical"] += 1
                continue
            status, note = rec["status"], f"imported from bundle {bundle['sha256'][:12]}"
            prod_verified = s.scalar(select(OfficialRecord.id).where(
                OfficialRecord.source_id == rec["source_id"], OfficialRecord.record_key == rec["record_key"],
                OfficialRecord.status == "verified"))
            if status in ("verified", "pending_review", "conflict") and (as_pending or prod_verified is not None):
                if prod_verified is not None:
                    summary["records_as_pending_due_to_production_version"] += 1
                    note += "; differs from the verified production version (production kept)"
                status = "pending_review" if status != "conflict" else "conflict"
            elif status == "verified" and not rec.get("reviewer"):
                status = "pending_review"  # an approval without a named reviewer is not carried over
            if rec["status"] == "verified" and status == "verified":
                note += f"; reviewed by {rec['reviewer']} on {rec.get('reviewed_at') or 'unknown date'} before transfer"
            version = (s.scalar(select(func.max(OfficialRecord.version)).where(
                OfficialRecord.source_id == rec["source_id"], OfficialRecord.record_key == rec["record_key"])) or 0) + 1
            summary["records_added"] += 1
            summary["records_by_status"][status] = summary["records_by_status"].get(status, 0) + 1
            if dry_run:
                continue
            fields = {f: rec[f] for f in RECORD_FIELDS if f not in ("status", "version", "review_reason", "reviewer")}
            s.add(OfficialRecord(
                **fields, version=version, status=status,
                review_reason=("; ".join(filter(None, [rec.get("review_reason"), note])))[-300:],
                reviewer=rec.get("reviewer") if status == "verified" else None,
                reviewed_at=datetime.fromisoformat(rec["reviewed_at"]) if status == "verified" and rec.get("reviewed_at") else None,
                extracted_at=datetime.fromisoformat(rec["extracted_at"]),
            ))
        if dry_run:
            s.rollback()
    summary["dry_run"] = dry_run
    return summary
