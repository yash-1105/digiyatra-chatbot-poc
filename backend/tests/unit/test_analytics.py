"""Analytics accuracy: counting, resolution maths, idempotent feedback, filters, privacy, persistence."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect, text

from app.db.migrate import upgrade
from app.db.session import Database, utcnow
from app.services import analytics as analytics_mod
from app.services.analytics import AnalyticsService
from app.services.topics import classify, keywords
from tests.conftest import FakeSarvam, new_database_url

EMAIL = "admin@gmail.com"


@pytest.fixture
def svc(tmp_path) -> AnalyticsService:
    url = new_database_url(tmp_path, "a")
    upgrade(url)
    return AnalyticsService(Database(url))


def rec(svc, conv, msg, at, text="How do I register with Aadhaar?", status="answered"):
    svc.record_interaction(conversation_id=conv, message_id=msg, asked_at=at, classification_text=text,
                           answer_status=status, source_count=2, pii_detected=False, latency_ms=100)


def feedback_at(monkeypatch, svc, when, conv, msg, resolved):
    monkeypatch.setattr(analytics_mod, "utcnow", lambda: when)
    return svc.record_feedback(conversation_id=conv, message_id=msg, resolved=resolved)


def test_empty_database_report(svc):
    r = svc.report(7)
    assert r["totals"] == {"conversations": 0, "questions": 0}
    assert r["resolution"]["rate_percent"] is None and r["resolution"]["avg_resolution_seconds"] is None
    assert r["top_topics"] == [] and r["unanswered"] == [] and r["recent"] == []
    assert len(r["daily"]) == 7 and all(d["conversations"] == 0 for d in r["daily"])


def test_resolution_rate_time_and_unconfirmed(svc, monkeypatch):
    t0 = utcnow().replace(microsecond=0) - timedelta(hours=2)
    # A: 2 questions, Yes 5 minutes after the FIRST question -> resolved, 300 s
    rec(svc, "conv-aaaaaaaa", "a1", t0)
    rec(svc, "conv-aaaaaaaa", "a2", t0 + timedelta(minutes=2), "Which airports support it?")
    assert feedback_at(monkeypatch, svc, t0 + timedelta(minutes=5), "conv-aaaaaaaa", "a2", True).recorded
    # B: Yes after 15 minutes -> resolved, 900 s
    rec(svc, "conv-bbbbbbbb", "b1", t0)
    feedback_at(monkeypatch, svc, t0 + timedelta(minutes=15), "conv-bbbbbbbb", "b1", True)
    # C: No -> unresolved (excluded from average time)
    rec(svc, "conv-cccccccc", "c1", t0)
    feedback_at(monkeypatch, svc, t0 + timedelta(minutes=1), "conv-cccccccc", "c1", False)
    # D, E: no feedback -> unconfirmed (never counted as resolved)
    rec(svc, "conv-dddddddd", "d1", t0)
    rec(svc, "conv-eeeeeeee", "e1", t0, "Does it work for train travel?", status="insufficient_evidence")

    r = svc.report(7, now=t0 + timedelta(hours=1))
    res = r["resolution"]
    assert (res["resolved"], res["unresolved"], res["unconfirmed"], res["confirmed"]) == (2, 1, 2, 3)
    assert res["rate_percent"] == round(2 / 3 * 100, 1) == 66.7
    assert res["avg_resolution_seconds"] == 600.0  # (300 + 900) / 2
    assert r["totals"] == {"conversations": 5, "questions": 6}
    recent = {x["conversation"]: x for x in r["recent"]}
    assert sorted(x["resolution_seconds"] for x in recent.values() if x["resolution_seconds"]) == [300.0, 900.0]


def test_duplicate_feedback_does_not_inflate(svc, monkeypatch):
    t0 = utcnow() - timedelta(minutes=30)
    rec(svc, "conv-dup00001", "m1", t0)
    first = feedback_at(monkeypatch, svc, t0 + timedelta(minutes=1), "conv-dup00001", "m1", True)
    again = feedback_at(monkeypatch, svc, t0 + timedelta(minutes=2), "conv-dup00001", "m1", True)
    flip = feedback_at(monkeypatch, svc, t0 + timedelta(minutes=3), "conv-dup00001", "m1", False)
    assert first.recorded and (again.reason, flip.reason) == ("duplicate", "duplicate")
    with svc.db.session() as s:
        assert s.execute(text("select count(*) from resolution_feedback")).scalar() == 1
    res = svc.report(7)["resolution"]
    assert (res["resolved"], res["unresolved"], res["avg_resolution_seconds"]) == (1, 0, 60.0)


def test_latest_explicit_feedback_sets_conversation_status_once(svc, monkeypatch):
    t0 = utcnow() - timedelta(minutes=30)
    rec(svc, "conv-multi001", "x1", t0)
    rec(svc, "conv-multi001", "x2", t0 + timedelta(minutes=1))
    feedback_at(monkeypatch, svc, t0 + timedelta(minutes=2), "conv-multi001", "x1", False)
    feedback_at(monkeypatch, svc, t0 + timedelta(minutes=4), "conv-multi001", "x2", True)
    res = svc.report(7)["resolution"]
    assert (res["resolved"], res["unresolved"], res["confirmed"]) == (1, 0, 1)  # one conversation, counted once
    assert res["avg_resolution_seconds"] == 240.0


def test_feedback_validation(svc, monkeypatch):
    t0 = utcnow() - timedelta(minutes=5)
    rec(svc, "conv-valid001", "v1", t0)
    rec(svc, "conv-valid001", "g1", t0, "hello", status="greeting")
    assert svc.record_feedback(conversation_id="conv-other999", message_id="v1", resolved=True).reason == "unknown_message"
    assert svc.record_feedback(conversation_id="conv-valid001", message_id="nope", resolved=True).reason == "unknown_message"
    assert svc.record_feedback(conversation_id="conv-valid001", message_id="g1", resolved=True).reason == "unknown_message"
    assert feedback_at(monkeypatch, svc, t0 + timedelta(days=2), "conv-valid001", "v1", True).reason == "expired"
    assert svc.report(7)["resolution"]["resolved"] == 0


def test_filters_daily_series_topics_and_unanswered(svc):
    now = utcnow()
    rec(svc, "conv-old00001", "o1", now - timedelta(days=12), "Which airports support Digi Yatra?")
    rec(svc, "conv-new00001", "n1", now - timedelta(days=1), "My boarding pass upload fails")
    rec(svc, "conv-new00001", "n2", now - timedelta(days=1), "How much is the registration fee?",
        status="insufficient_evidence")
    rec(svc, "conv-new00002", "n3", now, "what is the capital of France", status="out_of_scope")
    rec(svc, "conv-greet001", "g1", now, "hello", status="greeting")

    week, month = svc.report(7, now=now), svc.report(30, now=now)
    assert week["totals"] == {"conversations": 2, "questions": 3}  # greeting-only conversation excluded
    assert month["totals"] == {"conversations": 3, "questions": 4}
    assert len(week["daily"]) == 7 and len(month["daily"]) == 30
    assert sum(d["conversations"] for d in month["daily"]) == 3
    assert {t["topic"] for t in month["top_topics"]} >= {"airport_availability", "boarding_pass_upload"}
    assert "greeting" not in {t["topic"] for t in month["top_topics"]}
    assert week["unanswered"] == [{"topic": "aadhaar_registration", "label": "Aadhaar registration", "count": 1,
                                   "keywords": ["fees"]}]
    assert week["out_of_scope_count"] == 1


@pytest.mark.parametrize(
    "question,topic",
    [
        ("How do I register with Aadhaar?", "aadhaar_registration"),
        ("DigiLocker verification is failing", "digilocker_verification"),
        ("My boarding pass PDF won't upload", "boarding_pass_upload"),
        ("Which airports support Digi Yatra?", "airport_availability"),
        ("How do I delete my data?", "privacy_deletion"),
        ("Getting a Forbidden error at login", "app_errors"),
        ("Can I use it on international flights?", "international_travel"),
        ("Can I add my child?", "minors_family"),
        ("What happens at the e-gate?", "airport_journey"),
        ("Tell me a joke", "other"),
    ],
)
def test_topic_classification(question, topic):
    assert classify(question) == topic


def test_keywords_only_from_allow_list():
    assert keywords("my aadhaar 2345 6789 0123 and OTP 482913, name Ravi Kumar, boarding pass") == "aadhaar, otp, boarding pass"
    assert keywords("completely unrelated words") is None


def test_chat_integration_counts_and_feedback_changes_stats(app_factory):
    c = app_factory(FakeSarvam())
    c.app.state.auth.create_or_reset_admin(EMAIL, (pw := "synthetic-" + secrets.token_urlsafe(10)))
    ask = lambda m, cid: c.post("/api/v1/chat", json={"message": m, "conversation_id": cid}).json()  # noqa: E731

    m1 = ask("How do I register for Digi Yatra?", "conv-int-0001")["message_id"]
    ask("Which airports support Digi Yatra?", "conv-int-0001")
    m3 = ask("How do I delete my account?", "conv-int-0002")["message_id"]
    ask("hello", "conv-int-0003")
    ask("What is the capital of France?", "conv-int-0004")

    c.post("/api/v1/admin/auth/login", json={"email": EMAIL, "password": pw})
    before = c.get("/api/v1/admin/analytics?days=7").json()
    assert before["totals"] == {"conversations": 3, "questions": 4}
    assert before["resolution"] == {"resolved": 0, "unresolved": 0, "unconfirmed": 3, "confirmed": 0,
                                    "rate_percent": None, "avg_resolution_seconds": None}

    fb = lambda cid, mid, ok: c.post("/api/v1/chat/feedback", json={"conversation_id": cid, "message_id": mid, "resolved": ok})  # noqa: E731
    assert fb("conv-int-0001", m1, True).status_code == 204
    assert fb("conv-int-0001", m1, True).status_code == 204  # duplicate accepted but not counted
    assert fb("conv-int-0002", m3, False).status_code == 204
    after = c.get("/api/v1/admin/analytics?days=7").json()["resolution"]
    assert (after["resolved"], after["unresolved"], after["unconfirmed"], after["rate_percent"]) == (1, 1, 1, 50.0)
    assert after["avg_resolution_seconds"] is not None and after["avg_resolution_seconds"] >= 0


def test_no_sensitive_data_stored(app_factory):
    c = app_factory(FakeSarvam())
    secrets_in_msgs = ["2345 6789 0123", "482913", "K1234567", "9876543210", "ravi.kumar@example.com"]
    c.post("/api/v1/chat", json={"message": "My aadhaar is 2345 6789 0123 and OTP 482913, passport K1234567",
                                 "conversation_id": "conv-pii-00001"})
    c.post("/api/v1/chat", json={"message": "Call 9876543210 or mail ravi.kumar@example.com about boarding pass upload",
                                 "conversation_id": "conv-pii-00001"})
    engine = c.app.state.db.engine
    dump = []
    with engine.connect() as conn:
        for table in inspect(engine).get_table_names():
            dump += [str(row) for row in conn.execute(text(f"select * from {table}"))]  # noqa: S608
    blob = "\n".join(dump)
    for s in secrets_in_msgs + ["conv-pii-00001", "My aadhaar is", "about boarding pass upload"]:
        assert s not in blob
    assert "aadhaar" in blob  # only allow-listed keyword survives


def test_analytics_failure_never_breaks_chat(app_factory, monkeypatch):
    c = app_factory(FakeSarvam())

    def boom(**_):
        raise RuntimeError("db down")

    monkeypatch.setattr(c.app.state.analytics, "record_interaction", boom)
    r = c.post("/api/v1/chat", json={"message": "How do I register?", "conversation_id": "conv-fail-0001"})
    assert r.status_code == 200 and r.json()["status"] == "answered"


def test_upstream_error_is_recorded_not_resolved(app_factory):
    import httpx

    c = app_factory(FakeSarvam(lambda b: httpx.Response(503)), sarvam_max_retries=0)
    assert c.post("/api/v1/chat", json={"message": "How do I register?", "conversation_id": "conv-err-0001"}).status_code == 503
    r = c.app.state.analytics.report(7)
    assert r["totals"]["questions"] == 1 and r["resolution"]["resolved"] == 0


def test_restart_preserves_analytics(tmp_path, retriever):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import make_settings

    settings = make_settings(tmp_path)
    upgrade(settings.database_url)
    c1 = TestClient(create_app(settings, retriever=retriever, llm=FakeSarvam().client()))
    mid = c1.post("/api/v1/chat", json={"message": "How do I register?", "conversation_id": "conv-keep-001"}).json()["message_id"]
    c1.post("/api/v1/chat/feedback", json={"conversation_id": "conv-keep-001", "message_id": mid, "resolved": True})
    before = c1.app.state.analytics.report(30)
    c1.app.state.db.engine.dispose()
    upgrade(settings.database_url)  # re-running migrations is a no-op
    c2 = TestClient(create_app(settings, retriever=retriever, llm=FakeSarvam().client()))
    after = c2.app.state.analytics.report(30)
    assert before["totals"] == after["totals"] == {"conversations": 1, "questions": 1}
    assert after["resolution"]["resolved"] == 1


def test_migrations_match_models(tmp_path):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.db.migrate import downgrade
    from app.db.models import Base

    url = new_database_url(tmp_path, "m")
    upgrade(url)
    db = Database(url)
    with db.engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
    downgrade(url, "base")
    assert set(inspect(Database(url).engine).get_table_names()) == {"alembic_version"}


def test_timestamps_are_real_utc(svc):
    before = datetime.utcnow() if hasattr(datetime, "utcnow") else None
    rec(svc, "conv-time0001", "t1", utcnow())
    started = svc.report(7)["recent"][0]["started_at"]
    assert started.endswith("Z")
    if before:
        assert abs((datetime.fromisoformat(started[:-1]) - before).total_seconds()) < 60
