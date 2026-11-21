"""Novita wire, shared chat, and accounting checks. All completions are synthetic."""

import asyncio
import json
import re
from datetime import date

import httpx
import pytest

from app.clients.base import ProviderError
from app.clients.novita import NovitaChatClient
from app.services.knowledge import SOURCES, Knowledge
from app.services.usage import usage_values
from tests.conftest import FakeSarvam
from tests.unit.test_knowledge_enrichment import source_html

MODEL = "qwen/qwen3.8-flash"
KEY = "synthetic-novita-test-key"
MESSAGES = [{"role": "system", "content": "Shared rules"}, {"role": "user", "content": "Synthetic query"}]
USAGE = {
    "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
    "prompt_tokens_details": {"cached_tokens": 80},
    "completion_tokens_details": {"reasoning_tokens": 4},
}


def completion(answer, finish="stop"):
    return httpx.Response(200, json={
        "model": MODEL,
        "choices": [{"message": {"role": "assistant", "content": answer, "reasoning_content": "private trace"},
                     "finish_reason": finish}],
        "usage": USAGE,
    })


def request_completion(handler, **kwargs):
    async def request():
        client = NovitaChatClient(KEY, transport=httpx.MockTransport(handler), **kwargs)
        try:
            return await client.chat(MESSAGES, session_id="do-not-forward")
        finally:
            await client.aclose()

    return asyncio.run(request())


@pytest.mark.parametrize("thinking", [False, True])
def test_wire_contract_and_no_reasoning_leak(thinking):
    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "https://api.novita.ai/openai/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {KEY}"
        assert json.loads(request.content) == {
            "model": MODEL, "messages": MESSAGES, "max_tokens": 450, "temperature": 0.2,
            "stream": False, "enable_thinking": thinking, "separate_reasoning": True,
        }
        return completion("<think>internal deliberation</think>Visible response")

    result = request_completion(handler, max_tokens=450, enable_thinking=thinking)
    assert result.content == "Visible response"
    assert result.model == MODEL
    assert result.usage == {k: v for k, v in USAGE.items() if k != "total_tokens"}


@pytest.mark.parametrize(("status", "body", "kind", "attempts"), [
    (401, {"error": {"message": KEY}}, "auth", 1),
    (402, {}, "quota", 1),
    (403, {"code": "NOT_ENOUGH_BALANCE"}, "quota", 1),
    (403, {}, "auth", 1),
    (404, {}, "model_access", 1),
    (400, {}, "bad_request", 1),
    (408, {}, "timeout", 1),
    (429, {}, "rate_limited", 2),
    (500, {}, "unavailable", 2),
    (503, {}, "unavailable", 2),
    (200, {}, "empty", 1),
])
def test_error_classes_and_retry_policy(status, body, kind, attempts):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(status, json=body, headers={"retry-after": "0"})

    with pytest.raises(ProviderError) as error:
        request_completion(handler)
    assert error.value.kind == kind
    assert KEY not in str(error.value)
    assert len(requests) == attempts


@pytest.mark.parametrize("reason", ["length", "content_filter", "tool_calls", ["unexpected"]])
def test_incomplete_responses_are_rejected_with_usage(reason):
    with pytest.raises(ProviderError) as error:
        request_completion(lambda _: completion("Incomplete info", reason))
    assert error.value.kind == "empty"
    assert error.value.usage["completion_tokens"] == 20


def test_timeout_and_long_retry_after_do_not_repeat():
    calls = []

    async def slow(request):
        calls.append(request)
        await asyncio.sleep(1)
        return completion("too late")

    with pytest.raises(ProviderError, match="timeout"):
        request_completion(slow, timeout_s=0.01)
    assert len(calls) == 1

    def busy(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    with pytest.raises(ProviderError, match="rate_limited"):
        request_completion(busy)
    assert len(calls) == 2


@pytest.fixture
def install_novita(monkeypatch):
    def install(client, responder):
        provider = client.app.state.providers["novita"]
        transport = httpx.MockTransport(responder)

        async def send(_path, *, json, headers):
            request = httpx.Request("POST", "https://api.novita.ai/openai/v1/chat/completions",
                                    json=json, headers=headers)
            return await transport.handle_async_request(request)

        monkeypatch.setattr(provider._client, "post", send)

    return install


def ask(client, question, *, provider="novita", locale="en", thread="test-novita-123", **extra):
    return client.post("/api/v1/chat", json={
        "message": question, "provider": provider, "locale": locale, "conversation_id": thread, **extra,
    })


def test_http_credential_failure_is_a_provider_error(app_factory, install_novita, caplog):
    fake = FakeSarvam()
    with app_factory(fake, NOVITA_API_KEY=KEY) as client:
        install_novita(client, lambda _: httpx.Response(401, json={"message": KEY}))
        assert client.app.state.providers["novita"].configured
        response = ask(client, "What is DigiLocker?", locale="hi")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "assistant_unavailable"
        assert "provider=novita kind=auth status=401" in caplog.text
        assert KEY not in caplog.text
        assert KEY not in response.text
        assert not fake.requests
        assert ask(client, "What is DigiLocker?", provider="other").status_code == 422
        assert ask(client, "What is DigiLocker?", model="arbitrary/model").status_code == 422
        row = next(r for r in client.app.state.ai_usage.report(1)["providers"] if r["provider"] == "novita")
        assert (row["requests"], row["errors"], row["estimated_usd"]) == (1, 1, 0)


def test_missing_key_reports_safe_configuration_error(app_factory, caplog):
    with app_factory(NOVITA_API_KEY=None) as client:
        response = ask(client, "What is DigiLocker?")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "assistant_unavailable"
        assert "provider=novita kind=not_configured" in caplog.text


def test_novita_reviewed_current_source_and_expiry(app_factory, install_novita, monkeypatch):
    with app_factory(NOVITA_API_KEY=KEY, knowledge_enrichment_enabled=True,
                     conversational_answers_enabled=True) as client:
        db = client.app.state.db
        knowledge = Knowledge(db)
        revision = knowledge.verify("pib-2331200", snapshot=source_html("pib-2331200"))
        knowledge.review(revision, "published", "synthetic reviewer")
        outgoing = client.app.state.chat_service.d.knowledge
        monkeypatch.setattr(outgoing, "lookup", lambda topic: knowledge.lookup(topic, date(2026, 11, 21)))
        calls = []

        def respond(request):
            calls.append(request)
            prompt = json.loads(request.content)["messages"][-1]["content"]
            assert "supplement:pib-2331200" in prompt
            return completion("Digi Yatra is available for selected international flights in a limited November–December 2026 trial [S1].")

        install_novita(client, respond)
        question = "Can I use Digi Yatra for an international flight from Delhi?"
        result = ask(client, question).json()
        assert result["status"] == "answered" and result["model"] == MODEL and len(calls) == 1
        assert "selected international flights" in result["answer"]
        assert result["sources"][0]["url"] == SOURCES["pib-2331200"].url
        assert result["sources"][0]["verification_status"] == "verified"
        monkeypatch.setattr(outgoing, "lookup", lambda topic: knowledge.lookup(topic, date(2027, 1, 1)))
        result = ask(client, question, thread="expired-supplement").json()
        assert result["status"] == "insufficient_evidence" and not result["cached"] and len(calls) == 1


def test_novita_usage_and_cost_no_double_count(app_factory, install_novita):
    with app_factory(NOVITA_API_KEY=KEY) as client:
        install_novita(client, lambda _: completion("DigiLocker is a digital document wallet."))
        result = ask(client, "What is DigiLocker?").json()
        assert result["answer_mode"] == "general" and "document wallet" in result["answer"]
        assert result["model"] == MODEL and result["sources"] == []
        dimensions = client.app.state.ai_usage.report(1)["provider_language"]
        row, = dimensions
        cost = (20 * 0.15 + 80 * 0.016 + 20 * 0.47) / 1e6
        assert row["model"] == MODEL and row["currency"] == "USD"
        assert row["reported_input_tokens"] == 100 and row["reported_output_tokens"] == 20
        assert row["reasoning_tokens"] == 4 and row["cache_read_tokens"] == 80
        assert 0 <= row["p50_ms"] <= row["p95_ms"]
        assert row["reported_usage_cost"] == {"2026-11-21-list": pytest.approx(cost)}
        estimated = usage_values("novita", {}, client.app.state.settings, fallback_input=100)
        assert estimated["tokens_estimated"] and estimated["priced_amount"] is None


def test_bilingual_and_hinglish_corpus_preserves_shared_rules_outside_scoped_improvements(app_factory, install_novita, chunks):
    from pathlib import Path

    from app.rag.query import query_intent
    from app.services.answering import qwen_answer_focus

    catalog = json.loads((Path(__file__).resolve().parents[2] / "evaluation" / "novita_questions.json").read_text())
    assert len(catalog) == len({row[0] for row in catalog}) == 30
    assert sum(len(row) == 4 for row in catalog) == 10
    # A controlled refusal makes the same real retrieval and repair branches observable on both
    # clients, without using a mock to claim model accuracy.
    baseline = FakeSarvam(lambda _: FakeSarvam.ok("INSUFFICIENT_EVIDENCE"))
    requests = []
    approved = {chunk["source_file"] for chunk in chunks if chunk["approval_status"] == "approved"}

    def respond(request):
        payload = json.loads(request.content)
        assert payload["model"] == MODEL
        assert set(FakeSarvam.evidence_files(payload)) <= approved
        requests.append(payload["messages"])
        return completion("INSUFFICIENT_EVIDENCE")

    with app_factory(baseline, NOVITA_API_KEY=KEY, novita_rate_limit_requests=60,
                     rate_limit_window_s=1, rag_context_optimization_enabled=True,
                     conversational_answers_enabled=True) as client:
        install_novita(client, respond)
        for case, *questions in catalog:
            for variant, question in zip(("en", "hi", "hinglish"), questions, strict=False):
                locale = "en" if variant == "en" else "hi"
                history = []
                if case == "followup":
                    history = [{"role": "user", "content": "Can I use Digi Yatra on iPhone?"}]
                metadata = {"locale": locale, "history": history}
                previous = len(baseline.requests)
                current = len(requests)
                base = ask(client, question, provider="sarvam", thread=f"base-{case}-{variant}", **metadata)
                result = ask(client, question, thread=f"novita-{case}-{variant}", **metadata)
                assert base.status_code == result.status_code == 200, (case, locale, result.text)
                focus = qwen_answer_focus(question, query_intent(question))[0]
                if focus == "introduction":
                    assert result.json()["status"] == "answered" and result.json()["sources"]
                else:
                    assert result.json()["status"] == base.json()["status"], (case, locale)
                    assert result.json()["answer_mode"] == base.json()["answer_mode"], (case, locale)
                assert result.json()["provider"] == "novita" and result.json()["locale"] == locale
                compare = [payload["messages"] for payload in baseline.requests[previous:]]
                if focus:
                    assert requests[current:]
                    if compare:
                        assert requests[current:][0][0] != compare[0][0]
                else:
                    assert requests[current:] == compare, (case, locale)
                if case == "cost_service" or (case in {"gate_live", "injection"} and locale == "en"):
                    assert not compare, (case, locale)
                if case == "digilocker":
                    lang = "Hindi (Devanagari)" if locale == "hi" else "English"
                    assert compare and f"RESPONSE LANGUAGE: {lang}" in compare[0][0]["content"]
                if case == "all_airports" and locale == "en":
                    assert compare
                    prompt = compare[0][-1]["content"]
                    assert len(re.findall(r"(?m)^\d+\.\s*\([A-Z]{3}\)", prompt)) == 24


@pytest.mark.parametrize(("locale", "question", "answer", "concepts"), [
    ("en", "Can I use Digi Yatra on Android?", "Digi Yatra is available on Android [S1].", ("Android",)),
    ("hi", "क्या डिजी यात्रा एंड्रॉयड पर उपलब्ध है?", "डिजी यात्रा Android पर उपलब्ध है [S1]।", ("उपलब्ध", "Android")),
    ("hi", "Digi Yatra Android par bhi hai?", "डिजी यात्रा Android पर उपलब्ध है [S1]।", ("उपलब्ध", "Android")),
    ("en", "What is DigiLocker?", "DigiLocker is a digital wallet for official documents.", ("digital wallet", "documents")),
    ("hi", "डिजीलॉकर क्या है?", "डिजीलॉकर आधिकारिक दस्तावेज़ रखने वाला डिजिटल बटुआ है।", ("दस्तावेज़", "डिजिटल")),
])
def test_mocked_answers_language_claims_and_citations(app_factory, install_novita, locale, question, answer, concepts):
    with app_factory(NOVITA_API_KEY=KEY, conversational_answers_enabled=True) as client:
        prompts = []

        def respond(request):
            payload = json.loads(request.content)
            prompts.append(payload)
            if "[S1]" in answer:
                assert FakeSarvam.evidence_files(payload)
            return completion(answer)

        install_novita(client, respond)
        response = ask(client, question, locale=locale)
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "answered" and result["model"] == MODEL and len(prompts) == 1
        assert all(word in result["answer"] for word in concepts)
        assert "[1]" not in result["answer"]
        if "[S1]" in answer:
            assert result["sources"][0]["source_file"] in FakeSarvam.evidence_files(prompts[0])
        else:
            assert result["answer_mode"] == "general" and result["sources"] == []


def test_unexpected_model_is_not_attributed_to_qwen():
    def handler(_):
        data = completion("Unrelated response").json()
        data["model"] = "another-model"
        return httpx.Response(200, json=data)

    with pytest.raises(ProviderError, match="empty"):
        request_completion(handler)


def test_transient_response_can_recover_once():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, headers={"Retry-After": "0"})
        return completion("Recovered")

    assert request_completion(handler).content == "Recovered"
    assert len(calls) == 2


def test_concurrency_limit_does_not_queue_more_upstream_calls():
    async def check():
        started = asyncio.Event()
        ready = asyncio.Event()

        async def handler(_):
            started.set()
            await ready.wait()
            return completion("One response")

        client = NovitaChatClient(KEY, max_concurrency=1, transport=httpx.MockTransport(handler))
        first = asyncio.create_task(client.chat(MESSAGES))
        try:
            await started.wait()
            with pytest.raises(ProviderError, match="rate_limited"):
                await client.chat(MESSAGES)
        finally:
            ready.set()
            assert (await first).content == "One response"
            await client.aclose()

    asyncio.run(check())
