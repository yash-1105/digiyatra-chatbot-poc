"""Whole-site staging protection also covers direct backend requests."""


def test_staging_blocks_unauthorized_chat_and_admin(app_factory):
    client = app_factory(staging_basic_auth="c3ludGhldGljOnRlc3Q=")
    client.headers.pop("authorization")
    for path in ("/api/v1/chat", "/api/v1/admin/session"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers["www-authenticate"].startswith("Basic ")
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/admin/session", headers={"Authorization": "Basic wrong"}).status_code == 401
    assert client.get("/api/v1/admin/session", headers={"Authorization": "Basic c3ludGhldGljOnRlc3Q="}).json()["error"]["code"] == "not_authenticated"


def test_production_without_staging_credential_fails_closed(app_factory):
    client = app_factory(environment="production", staging_basic_auth=None,
                         admin_allowed_origins=["https://example.vercel.app"], cors_origins=[],
                         allow_sqlite_in_production=True)
    assert client.get("/api/v1/admin/session").status_code == 503
