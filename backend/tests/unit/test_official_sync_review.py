"""Regression tests: statistic filtering keeps facts, review pack, manual import, bundle transfer,
and preservation of existing approved knowledge. Synthetic data, isolated databases, no network."""

from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import select

from app.db.models import KnowledgeRevision, OfficialRecord, OfficialSource
from app.db.session import Database, utcnow
from app.sync import job as J
from app.sync.extract import extract_html
from app.sync.policy import assess, strip_statistics
from app.sync.review import apply_sheet, build_groups, write_report
from app.sync.sources import SOURCES
from app.sync.transfer import export_bundle, import_bundle
from tests.conftest import DEPLOY, RAW, make_settings
from tests.unit.test_official_sync import (
    MOCA,
    MOCA_HTML,
    PIB,
    PIB_HTML,
    TRIAL,
    TRIAL_HTML,
    Site,
    make_pdf,
    records,
    run,
    validator_ok,
)


@pytest.fixture
def env(tmp_path):
    from app.db.migrate import upgrade

    settings = make_settings(tmp_path, sync_host_interval_s=0, knowledge_auto_publish_enabled=True,
                             index_dir=tmp_path / "data" / "lancedb")
    upgrade(settings.database_url)
    db = Database(settings.database_url)
    yield settings, db
    db.engine.dispose()


def second_db(tmp_path, name, **overrides):
    from app.db.migrate import upgrade

    s = make_settings(tmp_path / name, index_dir=tmp_path / name / "idx", sync_host_interval_s=0, **overrides)
    (tmp_path / name).mkdir(exist_ok=True)
    upgrade(s.database_url)
    return s, Database(s.database_url)


# --------------------------------------------------------------------------- statistics vs facts
@pytest.mark.parametrize("text,keep,drop", [
    ("The platform has over 26.5 million users and has enabled more than 110 million journeys across 39 domestic "
     "airports, serving domestic airlines.", ["39 domestic airports", "serving domestic airlines"], ["million", "26.5"]),
    ('He said, "I congratulate the team for the 10-crore usage milestone." Digi Yatra is active at 38 airports.',
     ["active at 38 airports"], ["10-crore", '"']),
    ("Annual passenger traffic is projected to reach 50 crores by 2030. Keep your passport.", ["Keep your passport."],
     ["50 crores"]),
    ("Digi Yatra crosses 10 crore usage across 38 airports", ["38 airports"], ["10 crore"]),
    ("With over 1.1 crore downloads and 5 crore+ Indians onboard, Digi Yatra is transforming travel.", [], ["crore"]),
    ("डिजी यात्रा के 2.65 करोड़ उपयोगकर्ता हैं और 39 घरेलू हवाई अड्डों पर यात्राएँ हुईं। पासपोर्ट रखें।",
     ["39 घरेलू हवाई अड्डों", "पासपोर्ट रखें।"], ["करोड़"]),
])
def test_statistics_removed_but_coverage_facts_kept(text, keep, drop):
    cleaned, n = strip_statistics(text)
    assert n >= 1
    assert all(k in cleaned for k in keep), cleaned
    assert all(d not in cleaned for d in drop), cleaned


def test_sentences_without_usage_statistics_are_untouched():
    text = "Passengers must carry passports. A further 25 domestic airports are planned to be covered by 2027."
    assert strip_statistics(text) == (text, 0)


def test_pib_record_keeps_airport_count_and_flags_the_restatement(env):
    settings, db = env
    run(settings, db, Site({PIB: PIB_HTML}), ["pib-2331200"])
    rows = records(db, source_id="pib-2331200")
    body = " ".join(r.body for r in rows)
    assert "39 domestic airports" in body and "million" not in body
    assert any("coverage fact restated" in (r.review_reason or "") for r in rows)
    assert {r.status for r in rows} == {"pending_review"}  # consequential: never auto-approved


# --------------------------------------------------------------------------- preservation
def test_sync_never_touches_reviewed_supplements_or_approved_corpus(env):
    settings, db = env
    with db.session() as s:
        s.add(KnowledgeRevision(topic="international_trial", source_id="pib-2331200", digest="d" * 64, status="published",
                                risk="high", metadata_json={"claim": "reviewed", "published": "2026-11-01"},
                                retrieved_at=utcnow(), reviewer="operator"))
    files = sorted(p for d in (RAW, DEPLOY) if d.is_dir() for p in d.iterdir() if p.is_file())
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    run(settings, db, Site({PIB: PIB_HTML, MOCA: MOCA_HTML}), ["pib-2331200", "moca-digital-initiatives"])
    J.SyncJob(settings, db, index_validator=validator_ok).run(trigger="manual", publish_only=True)
    with db.session() as s:
        rev = s.scalar(select(KnowledgeRevision))
        assert (rev.status, rev.reviewer, rev.metadata_json["claim"]) == ("published", "operator", "reviewed")
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files} == before


# --------------------------------------------------------------------------- review lifecycle
def test_revoke_returns_to_queue_and_newer_pending_supersedes_older(env):
    settings, db = env
    site = Site({MOCA: [MOCA_HTML, MOCA_HTML.replace("voluntary.", "voluntary for everyone."),
                        MOCA_HTML.replace("voluntary.", "voluntary for every passenger.")]})
    run(settings, db, site, ["moca-digital-initiatives"])
    first = records(db, source_id="moca-digital-initiatives")[0]
    J.review_record(db, first.id, "revoked", "reviewer")
    assert records(db, source_id="moca-digital-initiatives")[0].status == "pending_review"
    J.review_record(db, first.id, "verified", "reviewer")
    run(settings, db, site, ["moca-digital-initiatives"])
    run(settings, db, site, ["moca-digital-initiatives"])
    statuses = [r.status for r in records(db, source_id="moca-digital-initiatives")]
    assert statuses == ["verified", "superseded", "pending_review"]  # one queued version per key


def test_review_pack_groups_pdf_windows_reports_conflicts_and_applies_per_group(env, tmp_path):
    settings, db = env
    pdf_url = "https://www.civilaviation.gov.in/sites/default/files/2024-01/test.pdf"
    with db.session() as s:
        s.add(OfficialSource(source_id="moca-guidelines:t", parent_id="moca-guidelines", canonical_url=pdf_url,
                             organization="Ministry of Civil Aviation", source_type="pdf", language="en",
                             trust="official_government", topic="policy", risk="high", enabled=True, refresh_days=14,
                             next_due_at=utcnow(), content_version=0, verification_status="x", consecutive_failures=0,
                             created_at=utcnow()))
        for page in range(1, 26):
            body = ("Passenger registration requires Aadhaar consent and a selfie for face verification at the airport. "
                    f"Digi Yatra now covers {24 if page == 3 else 30} airports for passengers.") if page % 2 else \
                "API interface schema specification for server latency and PKI certificate handling by the vendor."
            s.add(OfficialRecord(source_id="moca-guidelines:t", record_key=f"k{page}", version=1,
                                 content_hash=f"{page:064d}", status="pending_review", record_type="section",
                                 title="Guidelines", category=f"Page {page}", question=None, body=body, url=pdf_url,
                                 anchor=f"page={page}", organization="Ministry of Civil Aviation", language="en",
                                 authority="official_government", topic="policy", risk="high", published_on=None,
                                 updated_on=None, effective_from=None, expires_on=None, extracted_at=utcnow(),
                                 review_reason="consequential topic requires human review"))
    groups = build_groups(db, DEPLOY)
    assert [g["pages"] for g in groups] == ["1–10", "11–20", "21–25"]
    assert all(g["low_relevance_ids"] for g in groups)  # technical pages suggested, not decided
    md, sheet = write_report(groups, tmp_path / "review")
    assert oct(md.stat().st_mode)[-3:] == "600" and "PRIVATE" in md.read_text()
    data = json.loads(sheet.read_text())
    assert {g["decision"] for g in data["groups"].values()} == {"defer"}  # nothing approved by default
    g1, g2 = data["groups"]["G001"], data["groups"]["G002"]
    g1["decision"], g1["reject_ids"] = "verified", g1["suggested_reject_ids"]
    g2["decision"], g2["defer_ids"] = "rejected", [next(iter(g2["record_hashes"]))]
    sheet.write_text(json.dumps(data))
    with db.session() as s:  # a record changed after the pack was generated is skipped, never decided
        changed = s.get(OfficialRecord, int(sorted(set(g1["record_hashes"]) - {str(i) for i in g1["reject_ids"]})[0]))
        changed.content_hash = "f" * 64
    done = apply_sheet(db, sheet, "content reviewer")
    assert done["skipped_changed"] == 1 and done["verified"] == 4 and done["rejected"] == len(g1["reject_ids"]) + 9
    assert done["deferred"] == 1 + len(data["groups"]["G003"]["record_hashes"])
    data["groups"]["G003"]["decision"] = "approve-all"
    sheet.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        apply_sheet(db, sheet, "content reviewer")


def test_review_pack_flags_numeric_conflicts_against_approved_corpus(env):
    if not (DEPLOY / "chunks.jsonl").exists():
        pytest.skip("private deploy corpus not present")
    settings, db = env
    run(settings, db, Site({PIB: PIB_HTML}), ["pib-2331200"])
    group = next(g for g in build_groups(db, DEPLOY) if g["source_id"] == "pib-2331200")
    assert any("airport count [39]" in c and "approved corpus" in c for c in group["conflicts"])


# --------------------------------------------------------------------------- manual import (blocked Foundation)
def test_manual_import_by_url_multi_file_merge_and_review_publication(env):
    settings, db = env
    tab1 = TRIAL_HTML.replace('<div role="tabpanel" id="panel-eligibility"', '<div hidden role="tabpanel" id="x"').replace(
        "Who can participate?", "Is there an age limit?")
    tab2 = TRIAL_HTML.replace("<head>", '<head><link rel="canonical" href="https://digiyatrafoundation.com/international-passenger-trial">')
    job = J.SyncJob(settings, db, index_validator=validator_ok)
    result = job.import_capture(None, [tab1.encode(), tab2.encode()], url=TRIAL)
    assert result["source_id"] == "dyf-international-trial"
    rows = records(db, source_id="dyf-international-trial")
    questions = {r.question for r in rows}
    assert {"Who can participate?", "Is there an age limit?", "What is DY-IPT?"} <= questions
    assert {r.status for r in rows} == {"pending_review"} and all("operator capture" in r.review_reason for r in rows)
    assert "embedded page URL matches" in rows[0].review_reason
    # A later partial capture (one tab) never withdraws the other tab's records.
    J.SyncJob(settings, db, index_validator=validator_ok).import_capture("dyf-international-trial", [tab1.encode()])
    assert "withdrawn" not in {r.status for r in records(db, source_id="dyf-international-trial")}
    for r in records(db, source_id="dyf-international-trial"):
        J.review_record(db, r.id, "verified", "content reviewer")
    J.SyncJob(settings, db, index_validator=validator_ok).run(trigger="manual", publish_only=True)
    from app.sync.publish import active_publication
    assert active_publication(db).record_count == len(records(db, source_id="dyf-international-trial"))


def test_manual_import_registers_eligible_foundation_pages_only(env):
    settings, db = env
    faq = ('<html><head><link rel="canonical" href="https://digiyatrafoundation.com/faqs/"></head><body><main>'
           "<details><summary>How do I register for Digi Yatra?</summary><p>Register in the Digi Yatra app using Aadhaar "
           "or DigiLocker.</p></details></main></body></html>")
    result = J.SyncJob(settings, db, index_validator=validator_ok).import_capture(
        None, [faq.encode()], url="https://digiyatrafoundation.com/faqs/")
    assert result["source_id"].startswith("dyf-sitemap:") and result["new_records"] == 1
    for bad in ("https://evil.example/faqs/", "https://digiyatrafoundation.com/careers/", "https://www.pib.gov.in/x"):
        with pytest.raises(ValueError):
            J.SyncJob(settings, db).import_capture(None, [faq.encode()], url=bad)


def test_manual_import_rejects_mismatched_partial_and_mixed_captures(env):
    settings, db = env
    wrong = TRIAL_HTML.replace("<head>", '<head><meta property="og:url" content="https://digiyatrafoundation.com/other-page">')
    saved_from = "<!-- saved from url=(0063)https://digiyatrafoundation.com/international-passenger-trial -->" + TRIAL_HTML
    partial = TRIAL_HTML.replace('<div class="accordion-body">\n     <ul><li>Indian nationals holding an ePassport</li>'
                                 '<li>Travelling on participating flights</li></ul></div>', "")
    job = J.SyncJob(settings, db, index_validator=validator_ok)
    with pytest.raises(ValueError, match="does not match"):
        job.import_capture("dyf-international-trial", [wrong.encode()])
    with pytest.raises(ValueError, match="partial_faq_extraction"):
        job.import_capture("dyf-international-trial", [partial.encode()])
    with pytest.raises(ValueError, match="mix"):
        job.import_capture("dyf-international-trial", [TRIAL_HTML.encode(), make_pdf(["Digi Yatra"] * 40)])
    assert job.import_capture("dyf-international-trial", [saved_from.encode()])["new_records"] == 4
    src = J.SyncJob(settings, db)._row("dyf-international-trial")
    assert src.consecutive_failures == 0  # rejected captures never mark the automated source as failed


def test_capture_extraction_for_foundation_faq_is_complete():
    a = assess("dyf-international-trial", SOURCES["dyf-international-trial"], extract_html(TRIAL_HTML), TRIAL)
    assert a.complete and len(a.candidates) == 4


# --------------------------------------------------------------------------- transfer bundle
def test_bundle_transfer_is_insert_only_idempotent_and_tamper_evident(env, tmp_path):
    settings, db = env
    run(settings, db, Site({MOCA: MOCA_HTML, PIB: PIB_HTML}), ["moca-digital-initiatives", "pib-2331200"])
    reviewed = records(db, source_id="pib-2331200")[0]
    J.review_record(db, reviewed.id, "verified", "content reviewer")
    bundle = tmp_path / "exports" / "bundle.json"
    info = export_bundle(db, bundle)
    assert oct(bundle.stat().st_mode)[-3:] == "600" and info["records"] == len(records(db)) >= 2

    prod_settings, prod = second_db(tmp_path, "prod", knowledge_auto_publish_enabled=True)
    # Production already has its own verified version of the MoCA record: it must be kept.
    run(prod_settings, prod, Site({MOCA: MOCA_HTML.replace("voluntary.", "voluntary (production text).")}),
        ["moca-digital-initiatives"])
    prod_before = [(r.id, r.status, r.content_hash) for r in records(prod)]
    dry = import_bundle(prod, bundle, dry_run=True)
    assert dry["records_added"] == info["records"] and len(records(prod)) == len(prod_before)
    summary = import_bundle(prod, bundle)
    assert summary["records_as_pending_due_to_production_version"] == 1
    after = {r.id: r for r in records(prod)}
    for rid, status, digest in prod_before:  # existing production rows untouched
        assert (after[rid].status, after[rid].content_hash) == (status, digest)
    imported = [r for r in after.values() if r.id not in {x[0] for x in prod_before}]
    assert {r.status for r in imported if r.source_id == "pib-2331200" and r.reviewer} == {"verified"}
    assert all("imported from bundle" in r.review_reason for r in imported)
    assert import_bundle(prod, bundle)["records_skipped_identical"] == info["records"]  # idempotent
    tampered = json.loads(bundle.read_text())
    tampered["records"][0]["body"] = "Digi Yatra is mandatory for everyone."
    bundle.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="digest"):
        import_bundle(prod, bundle)
    prod.engine.dispose()


def test_bundle_as_pending_requeues_every_approval(env, tmp_path):
    settings, db = env
    run(settings, db, Site({MOCA: MOCA_HTML}), ["moca-digital-initiatives"])
    bundle = tmp_path / "b.json"
    export_bundle(db, bundle)
    _, prod = second_db(tmp_path, "prod2")
    import_bundle(prod, bundle, as_pending=True)
    assert {r.status for r in records(prod)} == {"pending_review"}
    prod.engine.dispose()
