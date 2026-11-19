"""Public portal APIs stay anonymous; administrator data still requires a session."""


def production_client(app_factory):
    client = app_factory(environment="production", cors_origins=[],
                       admin_allowed_origins=["https://digiyatra-chatbot-poc.vercel.app"],
                       allow_sqlite_in_production=True)
    client.base_url = "https://testserver"  # production cookies must travel over HTTPS
    return client


def test_public_chat_followup_and_feedback_need_no_login(app_factory):
    client = production_client(app_factory)
    for question in ("Is Digi Yatra mandatory?", "How do I register for Digi Yatra?"):
        response = client.post("/api/v1/chat", json={"message": question, "conversation_id": "public-access-0001"})
        assert response.status_code == 200
        assert "www-authenticate" not in response.headers
        data = response.json()
        assert data["status"] == "answered" and data["sources"]
        vote = {"conversation_id": data["conversation_id"], "message_id": data["message_id"], "resolved": True}
        assert client.post("/api/v1/chat/feedback", json=vote).status_code == 204


def test_admin_apis_require_session_without_basic_challenge(app_factory):
    client = production_client(app_factory)
    for path in ("/api/v1/admin/session", "/api/v1/admin/analytics"):
        response = client.get(path)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "not_authenticated"
        assert "www-authenticate" not in response.headers
    assert client.get("/api/docs").status_code == 404


def test_obsolete_staging_cookie_never_grants_admin_access(app_factory):
    client = production_client(app_factory)
    client.cookies.set("dy_staging_session", "obsolete-staging-cookie")
    assert client.get("/api/v1/admin/analytics").status_code == 401
    assert client.get("/api/v1/health").status_code == 200
