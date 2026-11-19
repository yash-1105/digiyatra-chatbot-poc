"""Ingestion against the REAL knowledge/raw files."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile

import docx
import pytest

from ingestion.parsers.csv_parser import parse_csv
from ingestion.parsers.docx_parser import parse_docx
from ingestion.parsers.markdown import parse_markdown
from ingestion.pipeline import run_pipeline
from ingestion.sanitize import sanitize_text
from tests.conftest import HAS_RAW, MANIFEST, RAW

pytestmark = pytest.mark.skipif(not HAS_RAW, reason="knowledge/raw not present (private originals not in repo)")

IPT = RAW / "FAQ_DY-IPT_Draft_26102026 1.docx"
EXCLUDED = {"draft", "historical", "irrelevant", "non_knowledge", "review_required", "duplicate"}


def test_every_raw_file_is_inventoried_and_classified(pipeline):
    result, _ = pipeline
    on_disk = sorted(p.name for p in RAW.iterdir() if p.is_file())
    assert sorted(f.file for f in result.files) == on_disk
    assert len(on_disk) == 37  # NOTE: the brief said 38; the directory actually holds 37 files.
    manifest = json.loads(MANIFEST.read_text())["files"]
    for f in result.files:
        assert f.in_manifest, f"{f.file} missing from approval manifest"
        assert f.status in EXCLUDED | {"approved"}
        assert f.status == manifest[f.file]["status"]


def test_status_counts(pipeline):
    result, _ = pipeline
    counts: dict[str, int] = {}
    for f in result.files:
        counts[f.status] = counts.get(f.status, 0) + 1
    assert counts == {"approved": 26, "draft": 1, "historical": 3, "irrelevant": 4, "non_knowledge": 1, "review_required": 2}


def test_raw_files_are_not_modified(tmp_path):
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW.iterdir()}
    run_pipeline(RAW, tmp_path / "out", MANIFEST)
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in RAW.iterdir()}
    assert before == after


def test_markdown_faq_table_preserves_question_answer_pairs():
    recs = parse_markdown((RAW / "support_02_registration_profile.md").read_text())
    faqs = [r for r in recs if r.record_type == "faq"]
    assert len(faqs) == 9
    mismatch = next(r for r in faqs if r.question.startswith("My name on Aadhaar"))
    assert "contact your airline" in mismatch.text


def test_markdown_question_headings_and_freeform_qa():
    intro = parse_markdown((RAW / "general_01_introduction.md").read_text())
    q = {r.question: r.text for r in intro if r.question}
    assert q["Is Digi Yatra mandatory?"].startswith("No, using Digi Yatra is purely voluntary")
    sharing = parse_markdown((RAW / "airport_data_sharing.md").read_text())
    qs = [r.question for r in sharing if r.record_type == "faq"]
    assert len(qs) == 3
    assert any("How long will the Biometric data" in q for q in qs)
    assert "24 hours" in next(r.text for r in sharing if "How long" in (r.question or ""))


def test_markdown_strips_embedded_video_html():
    recs = parse_markdown((RAW / "airport_guide.md").read_text())
    joined = " ".join(r.text for r in recs)
    assert "<video" not in joined and "newdelhiairport" not in joined
    assert "Scan your Boarding Pass" in joined


def test_docx_paragraphs_and_tables_in_document_order():
    recs = parse_docx(IPT)
    routes_q = next(r for r in recs if r.question == "Which airlines and routes are eligible?")
    body = routes_q.text
    # Paragraph text precedes the table rows, which appear in table order.
    assert body.index("listed below") < body.index("Airline: Air India; Origin Airport: BLR")
    assert body.index("Origin Airport: BLR (Bengaluru)") < body.index("Origin Airport: HYD (Hyderabad); Destination Airport: KWI")
    rows = [r for r in recs if r.record_type == "table_row"]
    assert len(rows) == 14
    assert rows[0].text.startswith("Airline: Air India; Origin Airport: BLR (Bengaluru)")
    # The 1x1 "Important" call-out table becomes a note, before the first section.
    assert recs[1].record_type == "note" and recs[1].text.startswith("Important: DY-IPT")
    # Heading 1 sections are tracked.
    assert routes_q.section_path == ["B. Eligibility, airports, airlines and routes"]


def test_docx_comments_and_properties_are_not_ingested(pipeline):
    result, _ = pipeline
    with zipfile.ZipFile(IPT) as z:
        comments_xml = z.read("word/comments.xml").decode()
    comment_texts = [t for t in re.findall(r"<w:t[^>]*>([^<]{12,})</w:t>", comments_xml)]
    assert comment_texts, "fixture sanity: draft should contain reviewer comments"
    props = docx.Document(str(IPT)).core_properties
    corpus = "\n".join(f"{r.question or ''} {r.text}" for r in result.records)
    for t in comment_texts:
        assert t.strip() not in corpus
    for meta in (props.author, props.last_modified_by):
        if meta:
            assert meta not in corpus


def test_csv_rows_use_field_names():
    recs = parse_csv(RAW / "privacy_policy.csv")
    assert len(recs) == 17
    dyf = next(r for r in recs if r.section_path == ["About Digi Yatra Foundation (DYF)"])
    assert "Section 8" in dyf.text
    assert "keywords" in dyf.extra


def test_sanitizer_redacts_pii_and_non_allowlisted_links():
    text, urls, red = sanitize_text(
        "Mail john.doe@gmail.com or customercare@digiyatrafoundation.com, call 9876543210, "
        "Aadhaar 2345 6789 0123. ![x](https://evil.example/img.png) [Docs](https://digiyatrafoundation.com/news/) "
        "[tracker](https://tracker.example.com/a) <video><source src='https://x.example/v.mp4'></video>"
    )
    assert "john.doe" not in text and "customercare@digiyatrafoundation.com" in text
    assert "9876543210" not in text and "2345 6789 0123" not in text
    assert "evil.example" not in text and "tracker.example.com" not in text and "<video" not in text
    assert urls == ["https://digiyatrafoundation.com/news/"]
    assert red["email"] == 1 and red["phone"] == 1 and red["aadhaar_like_number"] == 1


def test_manifest_drops_and_name_redaction(pipeline):
    result, out = pipeline
    about = [r for r in result.records if r.source_file == "about_us.md"]
    assert not any("Our Team" in r.section_path or "Our Shareholders" in r.section_path for r in about)
    li = next(r for r in result.records if r.source_file == "linkedin_service_information.md")
    assert "15.52" not in li.text and "64.54" not in li.text
    for path in out.rglob("*"):
        if path.is_file():
            content = path.read_text(encoding="utf-8")
            for name in ("Khadakbhavi", "Kunchur", "Siddharth"):
                assert name not in content, f"{name} leaked into {path.name}"


def test_only_approved_content_is_chunked(pipeline):
    result, _ = pipeline
    approved = {f.file for f in result.files if f.status == "approved"}
    assert result.chunks and all(c.approval_status == "approved" for c in result.chunks)
    assert {c.source_file for c in result.chunks} == approved
    text = " ".join(c.text for c in result.chunks)
    for banned in ("DY-IPT", "ePassport", "AI Impact Summit", "Schengen", "15.52 million", "CISO"):
        assert banned not in text


def test_deduplication(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    shutil.copy(RAW / "general_01_introduction.md", raw / "a.md")
    shutil.copy(RAW / "general_01_introduction.md", raw / "b.md")
    (raw / "c.md").write_text("## Is Digi Yatra mandatory?\nNo, using Digi Yatra is purely voluntary for air passengers. "
                              "Data is collected only with their consent.\n")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": {n: {"status": "approved"} for n in ("a.md", "b.md", "c.md")}}))
    res = run_pipeline(raw, tmp_path / "out", manifest)
    status = {f.file: f for f in res.files}
    assert status["b.md"].status == "duplicate" and status["b.md"].duplicate_of == "a.md"
    assert status["c.md"].duplicate_records_removed == 1
    hashes = [c.content_hash for c in res.chunks]
    assert len(hashes) == len(set(hashes))


def test_contradictions_and_time_sensitivity_are_flagged(pipeline):
    result, out = pipeline
    metrics = {m["metric"] for m in result.qc["metric_conflicts"]}
    assert {"infants_supported", "app_downloads_million", "journeys_million"} <= metrics
    infants = next(r for r in result.records if r.source_file == "allowed_passengers.md")
    assert "C1" in infants.conflict_ids
    airports = [c for c in result.chunks if c.source_file == "available_airports.md"]
    assert airports and all(c.time_sensitive and c.verification_status == "unverified" for c in airports)
    review = json.loads((out / "review_queue.json").read_text())
    assert any(i.get("file") == "support_06_feature_requests.md" for i in review)
    assert (out / "ingestion_report.md").read_text().count("| `") == 37
