"""Shared fixtures. Everything here is offline: the Sarvam API is replaced by an
httpx.MockTransport, and the index is built from the REAL knowledge files into a
temporary directory."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.clients.sarvam import SarvamChatClient
from app.config import PROJECT_DIR, Settings
from app.rag.embeddings import LexicalEmbedder
from app.rag.retriever import Retriever
from app.rag.store import KnowledgeIndex
from ingestion.pipeline import run_pipeline

# Optional: run DB tests against PostgreSQL. Set DY_TEST_PG_URL to an admin URL (e.g. the project-isolated
# server: postgresql+psycopg://postgres@/postgres?host=<project>/.cache/pgsock&port=55432). Each test then
# gets its own throwaway database, dropped at the end of the session.
PG_ADMIN_URL = os.environ.get("DY_TEST_PG_URL")
_CREATED_PG_DBS: list[str] = []


def new_database_url(tmp_path: Path, name: str = "test-analytics") -> str:
    if not PG_ADMIN_URL:
        return f"sqlite:///{tmp_path / (name + '.db')}"
    from sqlalchemy import create_engine
    from sqlalchemy.engine import make_url

    db = f"dy_t_{uuid.uuid4().hex[:12]}"
    eng = create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{db}"')
    eng.dispose()
    _CREATED_PG_DBS.append(db)
    return make_url(PG_ADMIN_URL).set(database=db).render_as_string(hide_password=False)


def pytest_sessionfinish(session, exitstatus):  # runs after every fixture teardown
    if PG_ADMIN_URL and _CREATED_PG_DBS:
        from sqlalchemy import create_engine

        eng = create_engine(PG_ADMIN_URL, isolation_level="AUTOCOMMIT")
        with eng.connect() as conn:
            for db in _CREATED_PG_DBS:
                conn.exec_driver_sql(f'DROP DATABASE IF EXISTS "{db}" WITH (FORCE)')
        eng.dispose()


RAW = PROJECT_DIR / "knowledge" / "raw"
MANIFEST = PROJECT_DIR / "knowledge" / "approval_manifest.json"
FAKE_KEY = "sk_test_FAKE_KEY_0123456789abcdef"


HAS_RAW = RAW.is_dir() and any(RAW.iterdir())
DEPLOY = PROJECT_DIR / "knowledge" / "deploy"


@pytest.fixture(scope="session")
def pipeline(tmp_path_factory):
    if not HAS_RAW:
        pytest.skip("knowledge/raw not present (private originals are not in the repository)")
    out = tmp_path_factory.mktemp("curated")
    return run_pipeline(RAW, out, MANIFEST, write=True), out


@pytest.fixture(scope="session")
def chunks(request) -> list[dict]:
    """Approved chunks: from a fresh ingestion of knowledge/raw when available, else the deploy corpus."""
    if HAS_RAW:
        return [c.to_dict() for c in request.getfixturevalue("pipeline")[0].chunks]
    from ingestion.corpus import load_corpus

    return load_corpus(DEPLOY)[0]


@pytest.fixture(scope="session")
def index(tmp_path_factory, chunks) -> KnowledgeIndex:
    idx = KnowledgeIndex(tmp_path_factory.mktemp("lancedb"), "knowledge_chunks")
    idx.build(chunks, LexicalEmbedder())
    return idx


@pytest.fixture(scope="session")
def retriever(index) -> Retriever:
    return Retriever(index, index.load_embedder())


def make_settings(tmp_path: Path, **overrides) -> Settings:
    """Every test app gets its OWN migrated SQLite database (isolated synthetic data)."""
    base = dict(
        SARVAM_API_KEY=FAKE_KEY,
        sarvam_max_retries=2,
        rate_limit_requests=1000,
        index_dir=tmp_path / "unused-index",
        database_url=new_database_url(tmp_path),
    )
    base.update(overrides)
    if base.get("environment") == "production":
        base.setdefault("staging_basic_auth", "c3ludGhldGljOnRlc3Q=")
    return Settings(_env_file=None, **base)


class FakeSarvam:
    """Scriptable stand-in for POST /v2/chat/completions. Records every request body."""

    def __init__(self, responder: Callable[[dict], httpx.Response] | None = None) -> None:
        self.requests: list[dict] = []
        self.headers: list[dict] = []
        self.responder = responder or self.cite_first

    @staticmethod
    def evidence_files(body: dict) -> list[str]:
        user = body["messages"][-1]["content"]
        return re.findall(r"^\[S\d+\] source: ([^|]+?) \|", user, re.M)

    @staticmethod
    def ok(content: str) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": "sarvam-105b",
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    def cite_first(self, body: dict) -> httpx.Response:
        n = len(self.evidence_files(body))
        cites = "[S1]" + ("[S2]" if n > 1 else "")
        return self.ok(f"Here is what the approved Digi Yatra information says. {cites}")

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(dict(request.headers))
        return self.responder(body)

    def client(self, **kw) -> SarvamChatClient:
        return SarvamChatClient(FAKE_KEY, transport=httpx.MockTransport(self.handler), backoff_base_s=0.0, **kw)


@pytest.fixture
def fake_sarvam() -> FakeSarvam:
    return FakeSarvam()


@pytest.fixture
def app_factory(tmp_path, retriever):
    from fastapi.testclient import TestClient

    from app.main import create_app

    def _make(fake: FakeSarvam | None = None, llm=None, **settings_overrides):
        settings = make_settings(tmp_path, **settings_overrides)
        from app.db.migrate import upgrade

        upgrade(settings.database_url)  # idempotent
        llm = llm or (fake or FakeSarvam()).client(max_retries=settings.sarvam_max_retries)
        app = create_app(settings, retriever=retriever, llm=llm)
        headers = {"Authorization": "Basic " + settings.staging_basic_auth.get_secret_value()} if settings.staging_basic_auth else {}
        return TestClient(app, headers=headers)

    return _make
