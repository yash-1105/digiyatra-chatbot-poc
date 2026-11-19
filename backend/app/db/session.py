"""Engine / session management."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def utcnow() -> datetime:
    """Naive UTC timestamp (portable between SQLite and PostgreSQL)."""
    return datetime.now(UTC).replace(tzinfo=None)


def make_engine(url: str) -> Engine:
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _):  # enforce FKs, better concurrency
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return engine


class Database:
    def __init__(self, url: str) -> None:
        self.url = url
        self.engine = make_engine(url)
        self._factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self._factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def is_migrated(self) -> bool:
        from sqlalchemy import inspect

        try:
            return "alembic_version" in inspect(self.engine).get_table_names()
        except Exception:  # noqa: BLE001 - any connection problem means "not ready"
            return False
