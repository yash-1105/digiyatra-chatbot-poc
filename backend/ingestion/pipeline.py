"""Knowledge ingestion pipeline.

    raw files --(manifest)--> parse --> sanitise --> dedupe --> classify --> chunk --> curated/*

Originals in knowledge/raw are only ever read. Outputs (all regenerated each run):
    curated/inventory.json        every discovered file with status and counts
    curated/records.jsonl         sanitised records (all statuses, for review)
    curated/chunks.jsonl          retrieval chunks — APPROVED content only (index input)
    curated/documents/<file>.md   human-readable sanitised rendition per document
    curated/review_queue.json     items needing a content owner's decision
    curated/qc_report.json        machine-readable QC results
    curated/ingestion_report.md   human-readable ingestion & QC report
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from ingestion.chunker import chunk_record
from ingestion.manifest import Manifest, load_manifest
from ingestion.models import Chunk, ParsedRecord, Record
from ingestion.parsers.csv_parser import parse_csv
from ingestion.parsers.docx_parser import parse_docx
from ingestion.parsers.markdown import parse_markdown
from ingestion.qc import find_metric_conflicts, find_shared_passages, time_markers
from ingestion.sanitize import apply_drop_patterns, normalise_for_hash, sanitize_text

SUPPORTED = {".md": "markdown", ".docx": "docx", ".csv": "csv"}


@dataclass
class FileReport:
    file: str
    extension: str
    size_bytes: int
    sha256: str
    status: str
    category: str
    reason: str
    in_manifest: bool
    records: int = 0
    faq_pairs: int = 0
    chunks: int = 0
    dropped_lines: int = 0
    dropped_records: int = 0
    duplicate_records_removed: int = 0
    redactions: dict[str, int] = field(default_factory=dict)
    duplicate_of: str | None = None


@dataclass
class IngestionResult:
    files: list[FileReport]
    records: list[Record]
    chunks: list[Chunk]
    review_queue: list[dict]
    qc: dict

    @property
    def approved_files(self) -> list[FileReport]:
        return [f for f in self.files if f.status == "approved"]


def discover(raw_dir: Path) -> list[Path]:
    """Regular files inside raw_dir only (symlinks and anything resolving outside are skipped)."""
    root = raw_dir.resolve()
    found = []
    for p in sorted(raw_dir.rglob("*")):
        if p.is_symlink() or not p.is_file() or p.name.startswith("."):
            continue
        if root not in p.resolve().parents:
            continue
        found.append(p)
    return found


def _doc_title(path: Path, parsed: list[ParsedRecord], raw_text: str) -> str:
    m = re.search(r"^#{1,6}\s+(.+)$", raw_text, re.M)
    if m and path.suffix == ".md":
        return re.sub(r"^\d+\.\s+", "", m.group(1).replace("**", "")).strip()
    for r in parsed:
        if r.record_type == "note" and r.section_path == ["Title"]:
            return r.text.splitlines()[0]
    stem = re.sub(r"^(general|support|linkedin)_\d*_?", "", path.stem)
    return stem.replace("_", " ").replace("-", " ").strip().title() or path.name


def _parse(path: Path, rule_patterns: list[str]) -> tuple[list[ParsedRecord], str, int]:
    kind = SUPPORTED[path.suffix.lower()]
    if kind == "docx":
        parsed = parse_docx(path)
        return parsed, "\n\n".join((r.question or "") + "\n" + r.text for r in parsed), 0
    raw = path.read_text(encoding="utf-8-sig")
    dropped = 0
    if rule_patterns:
        lines, dropped = apply_drop_patterns(raw.splitlines(), rule_patterns)
        raw = "\n".join(lines)
    if kind == "markdown":
        return parse_markdown(raw), raw, dropped
    tmp_path = path  # CSV is parsed from file; drop patterns not used for CSV in this manifest
    return parse_csv(tmp_path), raw, dropped


def _redact_terms(text: str, terms: list[str]) -> tuple[str, int]:
    total = 0
    for term in terms:
        # Also catch "Siddharth sharma" style casing and a bare first+last name.
        text, n = re.subn(re.escape(term), "[name removed]", text, flags=re.I)
        total += n
    return text, total


def _render_document(fr: FileReport, title: str, recs: list[Record]) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Source file: `{fr.file}`",
        f"- Status: **{fr.status}** ({fr.category})",
    ]
    if fr.reason:
        lines.append(f"- Reason: {fr.reason}")
    lines.append("")
    for r in recs:
        if r.section_path:
            lines.append(f"## {' > '.join(r.section_path)}")
        if r.question:
            lines.append(f"**Q: {r.question}**\n")
        lines.append(r.text)
        flags = []
        if r.time_sensitive:
            flags.append(f"time-sensitive ({', '.join(r.time_markers[:4]) or 'manifest'}) — {r.verification_status}")
        if r.conflict_ids:
            flags.append("conflicts: " + ", ".join(r.conflict_ids))
        if flags:
            lines.append(f"\n> QC: {'; '.join(flags)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_pipeline(raw_dir: Path, curated_dir: Path, manifest_path: Path, write: bool = True) -> IngestionResult:
    manifest: Manifest = load_manifest(manifest_path)
    files: list[FileReport] = []
    all_records: list[Record] = []
    review: list[dict] = []
    seen_raw_hash: dict[str, str] = {}
    seen_doc_hash: dict[str, str] = {}
    seen_record_hash: dict[str, str] = {}
    qc_texts: dict[str, tuple[str, str]] = {}
    approved_texts: dict[str, str] = {}
    titles: dict[str, str] = {}
    order = 0

    for path in discover(raw_dir):
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        rule = manifest.rule_for(path.name)
        fr = FileReport(
            file=path.name,
            extension=path.suffix.lower(),
            size_bytes=len(data),
            sha256=sha,
            status=rule.status,
            category=rule.category,
            reason=rule.reason,
            in_manifest=rule.in_manifest,
        )
        files.append(fr)
        if not rule.in_manifest:
            review.append({"file": path.name, "reason": "Not listed in approval manifest; not indexed."})

        if sha in seen_raw_hash:
            fr.status, fr.duplicate_of = "duplicate", seen_raw_hash[sha]
            fr.reason = f"Byte-identical to {seen_raw_hash[sha]}."
            continue
        seen_raw_hash[sha] = path.name

        if rule.status == "non_knowledge":
            continue
        if path.suffix.lower() not in SUPPORTED:
            fr.status = "review_required"
            fr.reason = f"Unsupported file type {path.suffix!r}."
            review.append({"file": path.name, "reason": fr.reason})
            continue

        parsed, raw_text, dropped_lines = _parse(path, rule.drop_patterns)
        # QC scans the ORIGINAL content (before manifest drops) so removed claims are still compared.
        original = raw_text if not dropped_lines else path.read_text(encoding="utf-8-sig")
        qc_texts[path.name] = (fr.status, original)
        fr.dropped_lines = dropped_lines
        title = _doc_title(path, parsed, raw_text)
        titles[path.name] = title

        doc_norm = normalise_for_hash(raw_text)
        doc_hash = hashlib.sha256(doc_norm.encode()).hexdigest()
        if doc_hash in seen_doc_hash and doc_norm:
            fr.status, fr.duplicate_of = "duplicate", seen_doc_hash[doc_hash]
            fr.reason = f"Same normalised content as {seen_doc_hash[doc_hash]}."
            continue
        seen_doc_hash[doc_hash] = path.name

        if rule.drop_sections:
            keep = [r for r in parsed if not any(s in rule.drop_sections for s in r.section_path)]
            fr.dropped_records = len(parsed) - len(keep)
            parsed = keep

        doc_records: list[Record] = []
        redactions: Counter = Counter()
        for idx, pr in enumerate(parsed):
            if pr.record_type == "note" and pr.section_path == ["Title"]:
                continue
            text, urls, red = sanitize_text(pr.text)
            question = None
            if pr.question:
                question, q_urls, q_red = sanitize_text(pr.question)
                urls += q_urls
                red += q_red
            text, n_names = _redact_terms(text, manifest.redact_terms)
            if question:
                question, q_names = _redact_terms(question, manifest.redact_terms)
                n_names += q_names
            if n_names:
                red["personal_name"] += n_names
            redactions += red
            if not text:
                continue
            section_path = [_redact_terms(sanitize_text(s)[0], manifest.redact_terms)[0] for s in pr.section_path if s]
            markers = time_markers(f"{question or ''} {text}")
            time_sensitive = rule.time_sensitive or bool(markers)
            verification = rule.verification_status or ("unverified" if time_sensitive else "not_applicable")
            lowered = f"{question or ''} {text}".lower()
            conflict_ids = [
                c.id for c in manifest.conflicts if path.name in c.files and any(k in lowered for k in c.keywords)
            ]
            rec_status = fr.status
            rec_hash = hashlib.sha256(normalise_for_hash(f"{question or ''} {text}").encode()).hexdigest()
            if rec_status == "approved":
                if rec_hash in seen_record_hash:
                    fr.duplicate_records_removed += 1
                    review.append(
                        {
                            "file": path.name,
                            "reason": f"Exact duplicate record removed (also in {seen_record_hash[rec_hash]}).",
                            "excerpt": text[:120],
                        }
                    )
                    continue
                seen_record_hash[rec_hash] = path.name
            order += 1
            rec = Record(
                record_id=f"{re.sub(r'[^a-z0-9]+', '-', path.stem.lower()).strip('-')}-{idx:03d}",
                source_file=path.name,
                doc_title=title,
                section_path=section_path,
                record_type=pr.record_type,
                question=question,
                text=text,
                approval_status=rec_status,
                category=rule.category,
                time_sensitive=time_sensitive,
                time_markers=markers,
                as_of=rule.as_of,
                verification_status=verification,
                conflict_ids=conflict_ids,
                urls=sorted(set(urls)),
                redactions=dict(red),
                order=order,
            )
            doc_records.append(rec)

        fr.records = len(doc_records)
        fr.faq_pairs = sum(1 for r in doc_records if r.record_type == "faq")
        fr.redactions = dict(redactions)
        all_records.extend(doc_records)
        joined = "\n".join(f"{r.question or ''} {r.text}" for r in doc_records)
        if fr.status == "approved":
            approved_texts[path.name] = joined

        if fr.status == "review_required" and rule.in_manifest:
            review.append({"file": path.name, "reason": rule.reason or "Marked review_required in manifest."})
        if fr.status == "approved":
            ts = [r for r in doc_records if r.time_sensitive and not r.as_of]
            if ts:
                review.append(
                    {
                        "file": path.name,
                        "reason": "Approved content contains time-sensitive claims without an as-of date; "
                        "verify before production.",
                        "records": [r.record_id for r in ts],
                        "markers": sorted({m for r in ts for m in r.time_markers})[:12],
                    }
                )
            if redactions:
                review.append({"file": path.name, "reason": f"Sanitiser redactions applied: {dict(redactions)}"})

    # Chunk approved records; suppress exact duplicate chunks.
    chunks: list[Chunk] = []
    seen_chunk: set[str] = set()
    for rec in all_records:
        if rec.approval_status != "approved":
            continue
        for ch in chunk_record(rec):
            if ch.content_hash in seen_chunk:
                continue
            seen_chunk.add(ch.content_hash)
            chunks.append(ch)
    per_file = Counter(c.source_file for c in chunks)
    for fr in files:
        fr.chunks = per_file.get(fr.file, 0)

    metric_conflicts = find_metric_conflicts(qc_texts)
    shared = find_shared_passages(approved_texts)
    for mc in metric_conflicts:
        review.append({"metric": mc["metric"], "reason": "Potential contradiction: differing values across documents.", "values": mc["values"]})
    for c in manifest.conflicts:
        review.append({"conflict": c.id, "reason": f"Known conflict ({c.topic}): {c.description}", "files": c.files})

    qc = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "approval_authority": manifest.approval_authority,
        "metric_conflicts": metric_conflicts,
        "known_conflicts": [c.__dict__ for c in manifest.conflicts],
        "shared_passages": shared,
        "time_sensitive_approved_records": sum(1 for r in all_records if r.approval_status == "approved" and r.time_sensitive),
    }
    result = IngestionResult(files=files, records=all_records, chunks=chunks, review_queue=review, qc=qc)
    if write:
        _write_outputs(result, curated_dir, titles)
    return result


def _write_outputs(result: IngestionResult, curated_dir: Path, titles: dict[str, str]) -> None:
    curated_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = curated_dir / "documents"
    if docs_dir.exists():
        shutil.rmtree(docs_dir)
    docs_dir.mkdir()

    (curated_dir / "inventory.json").write_text(
        json.dumps([f.__dict__ for f in result.files], indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    with (curated_dir / "records.jsonl").open("w", encoding="utf-8") as fh:
        for r in result.records:
            fh.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    with (curated_dir / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for c in result.chunks:
            fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
    (curated_dir / "review_queue.json").write_text(
        json.dumps(result.review_queue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (curated_dir / "qc_report.json").write_text(json.dumps(result.qc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    by_file: dict[str, list[Record]] = {}
    for r in result.records:
        by_file.setdefault(r.source_file, []).append(r)
    for fr in result.files:
        if fr.file in by_file:
            name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(fr.file).stem) + ".md"
            (docs_dir / name).write_text(_render_document(fr, titles.get(fr.file, fr.file), by_file[fr.file]), encoding="utf-8")

    (curated_dir / "ingestion_report.md").write_text(render_report(result), encoding="utf-8")


def render_report(result: IngestionResult) -> str:
    status_counts = Counter(f.status for f in result.files)
    ext_counts = Counter(f.extension for f in result.files)
    approved = result.approved_files
    lines = [
        "# Knowledge Ingestion & QC Report",
        "",
        f"Generated: {result.qc['generated_at']}  ",
        f"Approval authority: {result.qc['approval_authority']}",
        "",
        "## Summary",
        "",
        f"- Files discovered in `knowledge/raw/`: **{len(result.files)}** "
        f"({', '.join(f'{n} {e}' for e, n in sorted(ext_counts.items()))})",
        "- By status: " + ", ".join(f"{s}: **{n}**" for s, n in sorted(status_counts.items())),
        f"- Approved documents indexed: **{len(approved)}**",
        f"- Records extracted (all statuses): **{len(result.records)}** "
        f"(approved: {sum(1 for r in result.records if r.approval_status == 'approved')})",
        f"- FAQ question/answer pairs (approved): **{sum(f.faq_pairs for f in approved)}**",
        f"- Retrieval chunks (approved only): **{len(result.chunks)}**",
        f"- Duplicate records removed: **{sum(f.duplicate_records_removed for f in result.files)}**; "
        f"duplicate files: **{status_counts.get('duplicate', 0)}**",
        f"- Approved records with time-sensitive claims: **{result.qc['time_sensitive_approved_records']}**",
        f"- Review-queue items: **{len(result.review_queue)}**",
        "",
        "## File inventory",
        "",
        "| File | Type | Status | Category | Records | FAQ pairs | Chunks | Notes |",
        "|---|---|---|---|---:|---:|---:|---|",
    ]
    for f in result.files:
        note = f.reason or ""
        if f.dropped_records or f.dropped_lines:
            note += f" Dropped {f.dropped_records} section record(s), {f.dropped_lines} line(s) per manifest."
        if f.redactions:
            note += f" Redactions: {f.redactions}."
        if f.duplicate_records_removed:
            note += f" {f.duplicate_records_removed} duplicate record(s) removed."
        lines.append(
            f"| `{f.file}` | {f.extension} | {f.status} | {f.category} | {f.records} | {f.faq_pairs} | {f.chunks} | {note.strip()} |"
        )
    lines += ["", "## Contradictions", "", "### Known conflicts (manifest)", ""]
    for c in result.qc["known_conflicts"]:
        lines.append(f"- **{c['id']} — {c['topic']}** ({', '.join(c['files'])}): {c['description']}  \n  Guidance: {c['guidance']}")
    lines += ["", "### Automatically detected differing values", ""]
    if not result.qc["metric_conflicts"]:
        lines.append("_None detected._")
    for mc in result.qc["metric_conflicts"]:
        vals = "; ".join(f"`{v}` ← {', '.join(fs)}" for v, fs in mc["values"].items())
        lines.append(f"- **{mc['metric']}**: {vals}")
    lines += ["", "### Passages repeated across approved documents", ""]
    if not result.qc["shared_passages"]:
        lines.append("_None._")
    for sp in result.qc["shared_passages"]:
        lines.append(f"- {', '.join(sp['files'])}: “{sp['passage']}”")
    lines += [
        "",
        "## Review queue",
        "",
        "See `review_queue.json` for full details.",
        "",
    ]
    for item in result.review_queue:
        key = item.get("file") or item.get("metric") or item.get("conflict")
        lines.append(f"- `{key}` — {item['reason']}")
    return "\n".join(lines) + "\n"
