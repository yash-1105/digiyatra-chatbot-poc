"""Source and output boundary regressions with mocked providers."""

import asyncio
import json

import httpx
import pytest

from app.clients.anthropic import AnthropicChatClient
from app.clients.base import ProviderError
from app.rag.query import query_intent, scoped_match
from app.security.grounding import ground_answer
from app.services.answering import restricted_request
from app.services.context import optimized_context, select_context
from app.services.faq import faq_key
from evaluation.bilingual_reliability import SCREENSHOT_CASES
from evaluation.token_optimization import cases

INTENTS = dict(
    download_cost="download_cost", service_cost="service_cost", international="international_scope",
    international_repeat="international_scope", face="face_verification", offline="connectivity",
    digilocker="digilocker_comparison", epassport="epassport_scope",
)


@pytest.mark.parametrize("case,english,hindi", SCREENSHOT_CASES, ids=[item[0] for item in SCREENSHOT_CASES])
def test_equivalent_bilingual_evidence(retriever, case, english, hindi):
    intent = INTENTS[case]
    assert query_intent(english) == query_intent(hindi) == intent
    for question in (english, hindi):
        assert not faq_key(question) and not restricted_request(question)
        hits = retriever.search(question)
        if case == "service_cost":
            assert not hits
            continue
        assert hits
        for selected in (select_context(hits, 1800, 3), optimized_context(hits, question, 1800, 3, {})):
            assert selected
            assert all(retriever.lookup(h.chunk_id)["approval_status"] == "approved" for h in selected)
            assert all(scoped_match(intent, h.text) for h in selected)
        if case == "face":
            assert any("system is down" in h.text for h in hits)
            assert any("camera steady" in h.text for h in hits)


@pytest.mark.parametrize("english,hindi,expected", [
    ("Digi Yatra app muft hai download karne ke liye?", "क्या डिजी यात्रा ऐप डाउनलोड करना मुफ़्त है?", "download_cost"),
    ("Face verification fail ho jaye to kya karun?", "चेहरे का सत्यापन असफल हो तो क्या करें?", "face_verification"),
    ("Digi Yatra bina internet connection chalega?", "बिना इंटरनेट कनेक्शन डिजी यात्रा इस्तेमाल कर सकते हैं?", "connectivity"),
    ("Digi Yatra aur DigiLocker mein farak?", "डिजी यात्रा और डिजी लॉकर में फ़र्क़ क्या है?", "digilocker_comparison"),
])
def test_hinglish_and_hindi_aliases(english, hindi, expected):
    assert query_intent(english) == query_intent(hindi) == expected


def test_draft_and_personal_travel_keep_pre_model_guard():
    for question in (
        "What does the unpublished international pilot say?",
        "Can I use my ePassport on my international flight?",
        "How do I join the international e-passport trial?",
        "क्या मैं अपने ई-पासपोर्ट से अंतरराष्ट्रीय पायलट में शामिल हो सकता हूँ?",
    ):
        assert restricted_request(question)


def test_pricing_connectivity_and_proposed_features_cannot_be_inferred():
    for assertion, evidence in (
        ("Digi Yatra is free to download [1].", "Digi Yatra is available to download from two stores."),
        ("The app works offline [1].", "The app has an Offline Aadhaar option."),
        ("International e-passport travel is supported today [1].", "International e-passport use is on the future roadmap."),
        ("[1]", "A trusted approved passage."),
    ):
        assert not ground_answer(assertion, {1: 0}, [evidence]).cited_hits
    assert ground_answer("Use the camera in good lighting.\n[1]", {1: 0},
                         ["Use the camera in good lighting."]).cited_hits == [0]


@pytest.mark.parametrize("status,message,kind", [
    (400, "Select a workspace using the anthropic-workspace-id header", "workspace"),
    (404, "Unknown model", "model_access"),
    (402, "Insufficient balance", "quota"),
    (401, "Invalid credentials", "auth"),
])
def test_anthropic_classifies_provider_failures(status, message, kind):
    async def run():
        def handler(request):
            assert request.headers["anthropic-workspace-id"] == "workspace-test"
            return httpx.Response(status, content=json.dumps({"error": {"message": message}}))

        client = AnthropicChatClient("test-key", workspace_id="workspace-test", transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderError) as error:
                await client.chat([{"role": "user", "content": "Synthetic question"}])
            assert error.value.kind == kind
        finally:
            await client.aclose()
    asyncio.run(run())


def test_broad_replay_corpus_covers_distinct_questions():
    assert len({row["question"].casefold() for row in cases()}) >= 80
