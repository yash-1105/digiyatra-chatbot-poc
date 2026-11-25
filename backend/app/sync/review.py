"""Consolidated, private review report for pending official records (operator use only).

Groups pending/conflict records by source document (PDFs: contiguous page ranges of similar
relevance), lists deterministic factual claims, relevance and numeric conflicts against the
approved corpus, the reviewed supplements and other official records, and emits a decision
sheet that ``apply_sheet`` applies group by group. Nothing is approved automatically.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db.models import KnowledgeRevision, OfficialRecord, OfficialSource
from app.db.session import Database

PASSENGER = re.compile(
    r"passenger|register|registration|enrol|aadhaar|digilocker|boarding pass|consent|face|facial|selfie|e-?gate|"
    r"privacy|personal data|purge|delet|retention|wallet|credential|airport|airline|child|minor|mandatory|voluntary|"
    r"immigration|e-?passport|international|trial|helpline|support|grievance|"
    r"यात्री|पंजीकरण|आधार|सहमति|चेहरे|गोपनीयता|हवाई अड्डा|अनिवार्य|स्वैच्छिक", re.I)
TECHNICAL = re.compile(
    r"\bapi\b|interface|schema|protocol|pki|certificate|hsm|latency|throughput|server|database|architecture|"
    r"specification|vendor|bidder|sla|uptime|encryption key|json|xml|sdk|version \d|table of contents|annexure", re.I)
CLAIM = re.compile(r"\d|mandatory|voluntary|not\s+(?:required|mandatory|replace)|only|must|cannot|will not|"
                   r"purge|delet|retain|eligible|अनिवार्य|स्वैच्छिक", re.I)
NUMERIC_FACTS = {
    "airport count": re.compile(r"\b(\d{1,3})\s+(?:\w+\s+){0,2}airports\b", re.I),
    "retention hours": re.compile(r"(?:purg|delet|retain|stored)[^.]{0,80}?\b(\d{1,3})\s*hours?|\b(\d{1,3})\s*hours?[^.]{0,80}?(?:purg|delet|retain)", re.I),
    "language count": re.compile(r"\b(\d{1,2})\s+(?:\w+\s+)?languages\b", re.I),
    "child age": re.compile(r"(?:child|minor)[^.]{0,60}?\b(\d{1,2})\s*years?|\b(\d{1,2})\s*years?[^.]{0,40}?(?:child|minor)", re.I),
}


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?।])\s+|\n+", text)
    return [" ".join(p.split()) for p in parts if 25 <= len(p.strip()) <= 400]


def claims(text: str, limit: int = 12) -> list[str]:
    out = [s for s in _sentences(text) if CLAIM.search(s) and PASSENGER.search(s)]
    return list(dict.fromkeys(out))[:limit]


def facts(text: str) -> dict[str, set[int]]:
    found: dict[str, set[int]] = defaultdict(set)
    for name, rx in NUMERIC_FACTS.items():
        for m in rx.finditer(text):
            n = next((int(g) for g in m.groups() if g), None)
            if n is not None:
                found[name].add(n)
    return found


def relevance(text: str) -> tuple[str, int, int]:
    p, t = len(PASSENGER.findall(text)), len(TECHNICAL.findall(text))
    label = "high" if p >= 6 and p >= 2 * t else ("low" if p < 3 or t > p else "medium")
    return label, p, t


def _references(db: Database, corpus_dir: Path) -> list[tuple[str, str, dict[str, set[int]]]]:
    """(label, date, facts) for approved corpus chunks, reviewed supplements and verified records."""
    refs = []
    chunks_path = corpus_dir / "chunks.jsonl"
    if chunks_path.exists():
        for line in chunks_path.open():
            row = json.loads(line)
            f = facts(row["text"])
            if f:
                refs.append((f"approved corpus `{row['source_file']}`", row.get("as_of") or "undated", f))
    with db.session() as s:
        for rev in s.scalars(select(KnowledgeRevision).where(KnowledgeRevision.status == "published")):
            f = facts(rev.metadata_json.get("claim", ""))
            if f:
                refs.append((f"reviewed supplement `{rev.source_id}`", rev.metadata_json.get("published") or "undated", f))
        for rec in s.scalars(select(OfficialRecord).where(OfficialRecord.status == "verified")):
            f = facts(rec.body)
            if f:
                refs.append((f"verified official `{rec.source_id}`", rec.published_on or "undated", f))
    return refs


def _conflicts(group_facts: dict[str, set[int]], refs) -> list[str]:
    out = []
    for name, values in sorted(group_facts.items()):
        for label, when, f in refs:
            other = f.get(name)
            if other and other != values and not (other & values):
                out.append(f"{name} {sorted(values)} vs {label} ({when}): {sorted(other)}")
    return list(dict.fromkeys(out))[:8]


def _page(rec: OfficialRecord) -> int | None:
    m = re.fullmatch(r"page=(\d+)", rec.anchor or "")
    return int(m.group(1)) if m else None


def build_groups(db: Database, corpus_dir: Path) -> list[dict]:
    with db.session() as s:
        recs = list(s.scalars(select(OfficialRecord).where(OfficialRecord.status.in_(("pending_review", "conflict")))
                              .order_by(OfficialRecord.source_id, OfficialRecord.id)))
        sources = {r.source_id: r for r in s.scalars(select(OfficialSource))}
    refs = _references(db, corpus_dir)
    by_source: dict[str, list[OfficialRecord]] = defaultdict(list)
    for r in recs:
        by_source[r.source_id].append(r)
    groups = []
    for sid, rows in by_source.items():
        src = sources.get(sid)
        if src is not None and src.source_type == "pdf":
            # Fixed 10-page windows keep a long document to a handful of decisions.
            windows: dict[int, list[OfficialRecord]] = defaultdict(list)
            for r in sorted(rows, key=lambda r: (_page(r) or 0, r.id)):
                windows[((_page(r) or 1) - 1) // 10].append(r)
            parts = [windows[k] for k in sorted(windows)]
        else:
            parts = [rows]
        for part in parts:
            text = "\n".join(filter(None, [*(r.question or "" for r in part), *(r.body for r in part)]))
            label, p, t = relevance(text)
            pages = [n for r in part if (n := _page(r))]
            groups.append({
                "source_id": sid, "url": part[0].url, "organization": part[0].organization,
                "title": part[0].title, "topic": part[0].topic, "risk": part[0].risk, "language": part[0].language,
                "authority": part[0].authority, "published_on": part[0].published_on,
                "effective_from": part[0].effective_from, "expires_on": part[0].expires_on,
                "pages": f"{min(pages)}–{max(pages)}" if pages else None,
                "record_ids": [r.id for r in part],
                "record_hashes": {str(r.id): r.content_hash for r in part},
                "statuses": sorted({r.status for r in part}),
                "flags": sorted({x.strip() for r in part for x in (r.review_reason or "").split(";") if x.strip()}),
                "relevance": {"label": label, "passenger_terms": p, "technical_terms": t},
                "claims": claims(text),
                "conflicts": _conflicts(facts(text), refs),
                "chars": len(text),
                "low_relevance_ids": [r.id for r in part if relevance(r.body)[0] == "low"] if len(part) > 1 else [],
            })
    for i, g in enumerate(sorted(groups, key=lambda g: (g["source_id"], g["record_ids"][0])), 1):
        g["group_id"] = f"G{i:03d}"
    return sorted(groups, key=lambda g: g["group_id"])


def _suggest(g: dict) -> str:
    """A non-binding triage hint for the reviewer (never applied automatically)."""
    if g["relevance"]["label"] == "low":
        return "likely reject (low passenger relevance)"
    if g["low_relevance_ids"]:
        return f"review claims; consider rejecting {len(g['low_relevance_ids'])} low-relevance record(s)"
    if g["conflicts"]:
        return "verify conflicts against the newest authoritative source before deciding"
    if "OCR" in " ".join(g["flags"]):
        return "check OCR wording against the original PDF before approving"
    return "review claims; approve if accurate and current"


def write_report(groups: list[dict], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.chmod(0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    md, sheet = out_dir / f"official-review-{stamp}.md", out_dir / f"official-review-{stamp}.decisions.json"
    total = sum(len(g["record_ids"]) for g in groups)
    lines = [
        "# PRIVATE — official-source review pack (not for the public repository)", "",
        f"Generated {stamp}. {total} pending/conflict records in {len(groups)} review groups.",
        "Decisions are made per group in the decision sheet; nothing here is approved. Content-owner sign-off of the",
        "original approval manifest remains PENDING and is not represented by any decision in this pack.", "",
        "| Group | Source | Topic / risk | Pages | Records | Relevance | Conflicts | Triage hint |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for g in groups:
        lines.append(f"| {g['group_id']} | `{g['source_id']}` | {g['topic']} / {g['risk']} | {g['pages'] or '—'} | "
                     f"{len(g['record_ids'])} | {g['relevance']['label']} | {len(g['conflicts'])} | {_suggest(g)} |")
    for g in groups:
        lines += ["", f"## {g['group_id']} — {g['title']}", "",
                  f"- Source: `{g['source_id']}` · {g['organization']} ({g['authority']}) · {g['url']}",
                  f"- Topic/risk: {g['topic']} / {g['risk']} · language {g['language']} · published {g['published_on'] or 'undated'}"
                  + (f" · effective {g['effective_from']}–{g['expires_on']}" if g["effective_from"] or g["expires_on"] else ""),
                  f"- Records: {', '.join(map(str, g['record_ids']))}" + (f" (pages {g['pages']})" if g["pages"] else ""),
                  f"- Relevance: {g['relevance']['label']} (passenger terms {g['relevance']['passenger_terms']}, "
                  f"technical terms {g['relevance']['technical_terms']})",
                  f"- Flags: {'; '.join(g['flags']) or 'none'}",
                  f"- Low-relevance records (suggestion only): {', '.join(map(str, g['low_relevance_ids'])) or 'none'}",
                  "", "Extracted factual claims:"]
        lines += [f"  - {c}" for c in g["claims"]] or ["  - (no passenger-facing factual claims detected)"]
        lines += ["", "Potential conflicts:"] + ([f"  - {c}" for c in g["conflicts"]] or ["  - none detected"])
    md.write_text("\n".join(lines) + "\n")
    md.chmod(0o600)
    sheet.write_text(json.dumps({
        "instructions": "Set each group's decision to verified, rejected or defer. Optionally list record IDs in "
                        "reject_ids (rejected) or defer_ids (left pending) to override the group decision for them. Apply "
                        "with: python -m app.cli sync-review-apply <this file> --reviewer 'Name'. Records changed since "
                        "this pack was generated are skipped, never decided.",
        "generated_at": stamp,
        "groups": {g["group_id"]: {"decision": "defer", "reject_ids": [], "defer_ids": [],
                                   "suggested_reject_ids": g["low_relevance_ids"], "source_id": g["source_id"],
                                   "pages": g["pages"], "title": g["title"][:120], "record_hashes": g["record_hashes"]}
                   for g in groups},
    }, indent=2, ensure_ascii=False) + "\n")
    sheet.chmod(0o600)
    return md, sheet


def apply_sheet(db: Database, sheet_path: Path, reviewer: str) -> dict[str, int]:
    from app.sync.job import review_record

    data = json.loads(Path(sheet_path).read_text())
    done = {"verified": 0, "rejected": 0, "deferred": 0, "skipped_changed": 0}
    for gid, g in data["groups"].items():
        group_decision = g.get("decision", "defer")
        if group_decision not in {"verified", "rejected", "defer"}:
            raise ValueError(f"{gid}: invalid decision {group_decision!r}")
        rejects = {str(i) for i in g.get("reject_ids", [])}
        defers = {str(i) for i in g.get("defer_ids", [])}
        if (rejects | defers) - set(g["record_hashes"]):
            raise ValueError(f"{gid}: reject_ids/defer_ids must belong to the group")
        with db.session() as s:
            current = {str(r.id): (r.content_hash, r.status) for r in s.scalars(
                select(OfficialRecord).where(OfficialRecord.id.in_([int(i) for i in g["record_hashes"]])))}
        for rid, digest in g["record_hashes"].items():
            decision = "rejected" if rid in rejects else ("defer" if rid in defers else group_decision)
            if decision == "defer":
                done["deferred"] += 1
                continue
            if current.get(rid) is None or current[rid][0] != digest or current[rid][1] not in ("pending_review", "conflict"):
                done["skipped_changed"] += 1  # changed or already decided since the pack was generated
                continue
            review_record(db, int(rid), decision, reviewer)
            done[decision] += 1
    return done


def sheet_digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
