"""PostgreSQL-specific behaviour of the synchronisation pipeline.

Runs only when DY_TEST_PG_URL points to a LOCAL isolated server (enforced in conftest); each test
gets a throwaway database that is dropped afterwards. Never run against production PostgreSQL.

    DY_TEST_PG_URL='postgresql+psycopg://postgres@/postgres?host=<project>/.cache/pgsock&port=55432' \\
        .venv/bin/python -m pytest tests/unit/test_official_sync_postgres.py
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.models import KnowledgePublication, OfficialRecord
from app.db.session import Database, utcnow
from app.sync import job as J
from app.sync.publish import active_publication, publish
from tests.conftest import PG_ADMIN_URL, make_settings
from tests.unit.test_official_sync import MOCA, MOCA_HTML, TRIAL, TRIAL_HTML, Site, records, run, validator_ok

pytestmark = pytest.mark.skipif(not PG_ADMIN_URL, reason="DY_TEST_PG_URL (local isolated PostgreSQL) not set")


@pytest.fixture
def pg(tmp_path):
    from app.db.migrate import upgrade

    settings = make_settings(tmp_path, sync_host_interval_s=0, knowledge_auto_publish_enabled=True,
                             index_dir=tmp_path / "data" / "lancedb")
    assert settings.database_url.startswith("postgresql")
    upgrade(settings.database_url)
    db = Database(settings.database_url)
    yield settings, db
    db.engine.dispose()


def test_migration_0005_round_trip(pg):
    from app.db.migrate import downgrade, upgrade

    settings, db = pg
    downgrade(settings.database_url, "0004_supplemental_knowledge")
    with db.engine.connect() as c:
        assert c.execute(text("select to_regclass('official_record')")).scalar() is None
    upgrade(settings.database_url)
    with db.engine.connect() as c:
        assert c.execute(text("select to_regclass('official_record')")).scalar() == "official_record"


def test_concurrent_lease_has_exactly_one_holder(pg):
    _, db = pg
    tokens, barrier = [], threading.Barrier(8)

    def grab():
        barrier.wait()
        tokens.append(J.acquire_lease(db, 60))

    threads = [threading.Thread(target=grab) for _ in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sum(1 for t in tokens if t) == 1


def test_partial_unique_index_allows_one_active_publication(pg):
    _, db = pg
    with pytest.raises(IntegrityError):
        with db.session() as s:
            for _ in range(2):
                s.add(KnowledgePublication(created_at=utcnow(), status="active", digest="d", record_ids=[],
                                           record_count=0, run_id=None))


def test_concurrent_publish_under_table_lock(pg):
    settings, db = pg
    run(settings, db, Site({MOCA: MOCA_HTML}), ["moca-digital-initiatives"])
    errors, barrier = [], threading.Barrier(4)

    def go():
        barrier.wait()
        try:
            publish(db, None, validator_ok)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=go) for _ in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    with db.session() as s:
        active = list(s.scalars(select(KnowledgePublication).where(KnowledgePublication.status == "active")))
    assert len(active) == 1 and active[0].record_count == 1
    assert all(isinstance(e, IntegrityError) for e in errors)  # a racing duplicate is refused, never doubled


def test_full_cycle_and_row_locked_review(pg):
    settings, db = pg
    code, _ = run(settings, db, Site({TRIAL: TRIAL_HTML, MOCA: MOCA_HTML}), ["dyf-international-trial", "moca-digital-initiatives"])
    assert code == 0
    pending = records(db, source_id="dyf-international-trial")[0]
    results, barrier = [], threading.Barrier(2)

    def review():
        barrier.wait()
        try:
            J.review_record(db, pending.id, "verified", "reviewer")
            results.append("ok")
        except ValueError:
            results.append("refused")

    threads = [threading.Thread(target=review) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["ok", "refused"]
    J.SyncJob(settings, db, index_validator=validator_ok).run(trigger="manual", publish_only=True)
    assert active_publication(db).record_count == 2
    with db.session() as s:
        assert s.scalar(select(OfficialRecord.status).where(OfficialRecord.id == pending.id)) == "verified"
