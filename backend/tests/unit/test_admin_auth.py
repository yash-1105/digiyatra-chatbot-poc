"""Admin authentication & authorization (isolated test databases, synthetic credentials)."""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.cli import create_admin
from app.db.models import AdminSession, AdminUser
from app.db.session import Database, utcnow
from app.services.auth import AuthService
from tests.conftest import make_settings

EMAIL = "admin@gmail.com"
ORIGIN = {"Origin": "http://127.0.0.1:3000"}


@pytest.fixture
def pw() -> str:
    return "synthetic-" + secrets.token_urlsafe(12)  # random per test; never the real admin password


@pytest.fixture
def client(app_factory, pw):
    c = app_factory()
    c.app.state.auth.create_or_reset_admin(EMAIL, pw)
    return c


def login(c, email, password, headers=ORIGIN):
    return c.post("/api/v1/admin/auth/login", json={"email": email, "password": password}, headers=headers)


def test_password_stored_only_as_argon2id_hash(client, pw):
    with client.app.state.db.session() as s:
        user = s.scalar(select(AdminUser))
    assert user.email == EMAIL and user.password_hash.startswith("$argon2id$")
    assert pw not in user.password_hash


def test_admin_initialisation_rules(client, pw):
    auth = client.app.state.auth
    with pytest.raises(ValueError, match="already exists"):
        auth.create_or_reset_admin(EMAIL, pw)
    with pytest.raises(ValueError, match="at least"):
        auth.create_or_reset_admin("other@example.com", "short")


def test_cli_create_admin_prompts_privately(tmp_path):
    from app.db.migrate import upgrade

    settings = make_settings(tmp_path)
    out: list[str] = []
    assert create_admin(settings, EMAIL, False, prompt=lambda _: "x", out=out.append) == 2  # not migrated
    upgrade(settings.database_url)
    secret = "cli-synthetic-" + secrets.token_urlsafe(8)
    answers = iter(["short", secret, "mismatch", secret, secret])
    assert create_admin(settings, EMAIL, False, prompt=lambda _: next(answers), out=out.append) == 0
    assert not any(secret in line for line in out)
    assert any("at least" in line for line in out) and any("did not match" in line for line in out)
    db = Database(settings.database_url)
    with db.session() as s:
        assert s.scalar(select(AdminUser.email)) == EMAIL
    assert AuthService(db, 60, 60).authenticate(EMAIL, secret) is not None


def test_successful_login_sets_secure_session_cookies(client, pw):
    r = login(client, EMAIL, pw)
    assert r.status_code == 200 and r.json()["email"] == EMAIL and r.json()["csrf_token"]
    cookies = r.headers.get_list("set-cookie")
    sess = next(c for c in cookies if c.startswith("dy_admin_session="))
    csrf = next(c for c in cookies if c.startswith("dy_admin_csrf="))
    assert "HttpOnly" in sess and "samesite=strict" in sess.lower() and "Max-Age=" in sess
    assert "HttpOnly" not in csrf
    assert "Secure" not in sess  # development over http://127.0.0.1
    assert client.get("/api/v1/admin/session").status_code == 200
    assert client.get("/api/v1/admin/analytics?days=7").status_code == 200
    with client.app.state.db.session() as s:
        row = s.scalar(select(AdminSession))
    token = sess.split(";")[0].split("=", 1)[1]
    assert token not in (row.token_hash, row.csrf_hash)  # only hashes stored


def test_secure_flag_in_production(app_factory, pw):
    origin = "https://digiyatra-poc.vercel.app"
    c = app_factory(environment="production", admin_allowed_origins=[origin], cors_origins=[], allow_sqlite_in_production=True)
    c.app.state.auth.create_or_reset_admin(EMAIL, pw)
    r = login(c, EMAIL, pw, headers={"Origin": origin})
    sess = next(x for x in r.headers.get_list("set-cookie") if x.startswith("dy_admin_session="))
    assert "Secure" in sess and "HttpOnly" in sess and "samesite=strict" in sess.lower()


def test_wrong_password_and_unknown_email_rejected_identically(client, pw):
    a, b = login(client, EMAIL, pw + "x"), login(client, "nobody@example.com", pw)
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json() == {"error": {"code": "invalid_credentials", "message": "The email or password is incorrect."}}
    assert "dy_admin_session" not in client.cookies


@pytest.mark.parametrize("path", ["/api/v1/admin/session", "/api/v1/admin/analytics?days=7", "/api/v1/admin/analytics?days=30"])
def test_unauthenticated_access_denied(app_factory, path):
    c = app_factory()
    assert c.get(path).status_code == 401
    c.cookies.set("dy_admin_session", "forged-token-value")
    assert c.get(path).status_code == 401


def test_invalid_filter_rejected(client, pw):
    login(client, EMAIL, pw)
    assert client.get("/api/v1/admin/analytics?days=365").status_code == 422


def test_logout_requires_csrf_and_revokes_session(client, pw):
    csrf = login(client, EMAIL, pw).json()["csrf_token"]
    stolen = client.cookies.get("dy_admin_session")
    assert client.post("/api/v1/admin/auth/logout", headers=ORIGIN).status_code == 403  # missing CSRF header
    assert client.post("/api/v1/admin/auth/logout", headers={**ORIGIN, "X-CSRF-Token": "wrong"}).status_code == 403
    r = client.post("/api/v1/admin/auth/logout", headers={**ORIGIN, "X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert client.get("/api/v1/admin/session").status_code == 401
    client.cookies.set("dy_admin_session", stolen)  # replaying the old cookie must fail
    assert client.get("/api/v1/admin/session").status_code == 401


@pytest.mark.parametrize("field", ["expires_at", "last_seen_at"])
def test_session_expiry_absolute_and_idle(client, pw, field):
    login(client, EMAIL, pw)
    assert client.get("/api/v1/admin/session").status_code == 200
    with client.app.state.db.session() as s:
        s.execute(update(AdminSession).values({field: utcnow() - timedelta(days=2)}))
    assert client.get("/api/v1/admin/analytics?days=7").status_code == 401


def test_password_reset_revokes_existing_sessions(client, pw):
    login(client, EMAIL, pw)
    client.app.state.auth.create_or_reset_admin(EMAIL, pw + "-new", reset=True)
    assert client.get("/api/v1/admin/session").status_code == 401


def test_login_rate_limited(client, pw):
    for _ in range(5):
        assert login(client, EMAIL, "wrong-password").status_code == 401
    r = login(client, EMAIL, pw)  # even the correct password is refused while throttled
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_attempts"


def test_cross_site_login_blocked(client, pw):
    assert login(client, EMAIL, pw, headers={"Origin": "https://evil.example"}).status_code == 403


@pytest.mark.parametrize("host_header", ["Host", "X-Forwarded-Host"])
def test_production_origin_allowlist_cannot_be_bypassed_by_host(app_factory, pw, host_header):
    origin = "https://digiyatra-poc.vercel.app"
    c = app_factory(environment="production", admin_allowed_origins=[origin], cors_origins=[],
                    allow_sqlite_in_production=True)
    c.app.state.auth.create_or_reset_admin(EMAIL, pw)
    response = login(c, EMAIL, pw, headers={"Origin": "https://evil.example", host_header: "evil.example"})
    assert response.status_code == 403


def test_passwords_never_logged(client, pw, caplog):
    caplog.set_level(logging.DEBUG)
    login(client, EMAIL, pw + "-wrong")
    login(client, EMAIL, pw)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "admin login failed" in text and "admin login succeeded" in text
    assert pw not in text and EMAIL not in text


def test_admin_unavailable_when_database_not_migrated(tmp_path, retriever):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.conftest import FakeSarvam

    c = TestClient(create_app(make_settings(tmp_path / "x"), retriever=retriever, llm=FakeSarvam().client()))
    assert c.get("/api/v1/admin/analytics?days=7").status_code == 503
    assert c.post("/api/v1/chat", json={"message": "hello", "conversation_id": "conv-nodb-0001"}).status_code == 200


def test_production_configuration_is_validated(tmp_path):
    from app.config import Settings

    bad = Settings(_env_file=None, environment="production", cors_origins=["*"], cookie_secure=False,
                   database_url=f"sqlite:///{tmp_path}/x.db")
    problems = " ".join(bad.production_problems())
    assert "CORS_ORIGINS" in problems and "COOKIE_SECURE" in problems and "ADMIN_ALLOWED_ORIGINS" in problems
    assert "PostgreSQL" in problems
    good = Settings(_env_file=None, environment="production", cors_origins=[],
                    admin_allowed_origins=["https://digiyatra-poc.vercel.app"], database_url="postgres://u:p@db.internal:5432/app")
    assert good.production_problems() == [] and good.secure_cookies
    assert good.database_url == "postgresql+psycopg://u:p@db.internal:5432/app"


def test_production_hides_api_docs_and_stack_traces(app_factory):
    c = app_factory(environment="production", admin_allowed_origins=["https://digiyatra-poc.vercel.app"], cors_origins=[],
                    allow_sqlite_in_production=True)
    assert c.get("/api/docs").status_code == 404 and c.get("/api/openapi.json").status_code == 404

    def boom(*a, **k):
        raise RuntimeError("secret internal detail /srv/app/thing.py")

    c.app.state.chat_service.handle = boom
    from fastapi.testclient import TestClient
    r = TestClient(c.app, raise_server_exceptions=False, headers=dict(c.headers)).post(
        "/api/v1/chat", json={"message": "How do I register?", "conversation_id": "conv-prod-0001"})
    assert r.status_code == 500 and r.json() == {"error": {"code": "internal_error", "message": "Something went wrong. Please try again."}}
    assert "Traceback" not in r.text and "secret internal detail" not in r.text


def test_rate_limit_uses_rightmost_trusted_hop(app_factory):
    c = app_factory(trusted_proxy_hops=2, rate_limit_requests=2)
    hdr = lambda xff: {"X-Forwarded-For": xff}  # noqa: E731
    body = {"message": "hello", "conversation_id": "conv-hops-0001"}
    # Client spoofs a fresh IP each time in the left-most slot; the proxy-appended entries stay the same.
    codes = [c.post("/api/v1/chat", json=body, headers=hdr(f"10.0.0.{i}, 203.0.113.7, 198.51.100.1")).status_code
             for i in range(3)]
    assert codes == [200, 200, 429]
    assert c.post("/api/v1/chat", json=body, headers=hdr("203.0.113.99, 198.51.100.1")).status_code == 200
