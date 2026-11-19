"""Shared-provider regressions against approved private evidence; synthetic DBs only.

Mocked model responses exercise transport/routing/validation, not model quality.
The same question set is separately evaluated with real provider calls.
"""

import hashlib
import hmac
import json
import re
import time
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.clients.anthropic import AnthropicChatClient
from app.db.models import AIUsage, InteractionEvent
from app.rag.query import intent_match, query_intent
from app.security.grounding import ground_answer
from app.services.answering import general_topic, restricted_request
from app.services.prompts import SYSTEM_PROMPT
from tests.conftest import FakeSarvam

CASES = json.loads((Path(__file__).parents[2] / 'evaluation/reliability_questions.json').read_text())


def grounded_mock(payload):
    turn = payload['messages'][-1]['content']
    if '<evidence>' not in turn:
        return 'An OTP is a one-time password.'
    evidence = re.search(r'<<<\n(.*?)\n>>>', turn, re.S)[1]
    body = re.sub(r'^Q:.*?\nA:\s*', '', evidence, flags=re.S)
    sentence = next(line for line in body.splitlines() if line.strip())
    return sentence + ' [S1]'


@pytest.mark.parametrize('provider', ['sarvam', 'anthropic'])
@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_shared_answering_rules_for_both_providers(app_factory, provider, case):
    fake = FakeSarvam(lambda p: FakeSarvam.ok(grounded_mock(p)))
    with app_factory(fake, faq_cache_ttl_s=0) as c:
        def handler(request):
            payload = json.loads(request.content)
            assert payload['model'] == 'claude-haiku-5-5'
            assert ('Hindi (Devanagari)' if case['locale'] == 'hi' else 'English') in payload['system'][0]['text']
            return httpx.Response(200, json={'model': 'claude-haiku-5-5', 'content': [{'type': 'text', 'text': grounded_mock(payload)}], 'usage': {'input_tokens': 10, 'output_tokens': 5}})
        c.app.state.providers['anthropic'] = AnthropicChatClient('fake', transport=httpx.MockTransport(handler))
        r = c.post('/api/v1/chat', json=dict(message=case['question'], locale=case['locale'], provider=provider, conversation_id='regression-'+case['id']))
        assert r.status_code == 200
        b = r.json()
        assert b['answer_mode'] == case['mode'], b
        if case['mode'] == 'knowledge':
            assert b['sources'] and re.search(r'\[\d+\]', b['answer'])
        if provider == 'anthropic':
            assert not fake.requests


@pytest.mark.parametrize('case', [c for c in CASES if c.get('intent')], ids=lambda c: c['id'])
def test_new_intents_have_direct_approved_evidence(retriever, case):
    assert query_intent(case['question']) == case['intent']
    assert restricted_request(case['question']) is None
    hits = retriever.search(case['question'])
    assert hits and intent_match(case['intent'], {'text': hits[0].text}) >= .9
    assert all(retriever.lookup(h.chunk_id)['approval_status'] == 'approved' for h in hits)


def test_fragmented_faq_includes_count_names_and_official_link(retriever):
    hits = retriever.search('Which airports support Digi Yatra?')
    catalog = hits[0]
    assert catalog.source_file == 'available_airports.md'
    assert len(re.findall(r'^\d+\.\s*\([A-Z]{3}\)', catalog.text, re.M)) == 24
    assert len(catalog.extra['source_chunks']) == 3
    assert 'digi-yatra-implementation-current/' in catalog.text and catalog.time_sensitive
    assert 'planned' not in catalog.question.lower()
    assert all(retriever.lookup(cid)['approval_status'] == 'approved' for cid in catalog.extra['source_chunks'])


def test_citation_paraphrases_and_catalog_identity_remain_grounded():
    e = 'Q: Supported airports?\nA: 1. (ABC) Example International Airport\n2. (DEF) Sample Airport'
    assert ground_answer('Example International Airport (ABC) [1].', {1: 0}, [e]).text
    for claim in ('Sydney International Airport (ABC)', 'Example International Airport (XYZ)', 'Sample Airport (ABC)', 'Sydney International Airport'):
        assert not ground_answer(claim+' [1].', {1: 0}, [e]).text
    assert ground_answer('The airport deletes biometric data within 24 hours of flight departure [1].', {1: 0}, ['The airport purges biometric data within 24 hours of flight departure.']).text
    assert not ground_answer('The airport deletes biometric data within 72 hours [1].', {1: 0}, ['The airport purges biometric data within 24 hours of flight departure.']).text


def signed(body, stamp=None):
    stamp = str(int(time.time()) if stamp is None else stamp)
    digest = hashlib.sha256(body).hexdigest()
    signature = hmac.new(b'test-operator-secret', f'evaluation:v1\n{stamp}\n{digest}'.encode(), hashlib.sha256).hexdigest()
    return {'content-type': 'application/json', 'x-dy-evaluation': stamp+'.'+signature}


def test_live_evaluation_is_authenticated_bounded_and_never_writes_analytics(app_factory):
    fake = FakeSarvam(lambda p: FakeSarvam.ok(grounded_mock(p)))
    with app_factory(fake, proxy_shared_secret='test-operator-secret') as c:
        body = json.dumps(dict(message='Who operates Digi Yatra?', conversation_id='eval-isolated')).encode()
        r = c.post('/api/v1/chat', content=body, headers=signed(body))
        assert r.status_code == 200 and r.headers['x-dy-evaluation'] == 'synthetic'
        with c.app.state.db.session() as db:
            assert db.scalar(select(func.count()).select_from(InteractionEvent)) == 0
            assert db.scalar(select(func.count()).select_from(AIUsage)) == 0
        assert c.app.state.chat_service.d.conversations.history('eval-isolated') is None
        assert c.app.state.evaluation_conversations.history('eval-isolated')
        for wrong_body, headers in [(body, signed(body, 1)), (body+b' ', signed(body)), (body, {'content-type': 'application/json', 'x-dy-evaluation': 'invalid'})]:
            assert c.post('/api/v1/chat', content=wrong_body, headers=headers).status_code == 403
        # An unsigned eval-looking name has no privileges and records normal analytics.
        assert c.post('/api/v1/chat', content=body, headers={'content-type':'application/json'}).status_code == 200
        with c.app.state.db.session() as db:
            assert db.scalar(select(func.count()).select_from(InteractionEvent)) == 1
            assert db.scalar(select(func.count()).select_from(AIUsage)) == 1
        assert c.post('/api/v1/chat/feedback', json=dict(conversation_id='eval-isolated', message_id=r.json()['message_id'], resolved=True)).status_code == 404


def test_synthetic_requests_do_not_bypass_public_rate_limits(app_factory):
    with app_factory(proxy_shared_secret='test-operator-secret', rate_limit_requests=1) as c:
        body = json.dumps(dict(message='Hello', conversation_id='eval-rate')).encode()
        assert c.post('/api/v1/chat', content=body, headers=signed(body)).status_code == 200
        assert c.post('/api/v1/chat', content=body, headers=signed(body)).status_code == 429


def test_general_mode_remains_narrow_and_both_providers_share_prompt():
    assert general_topic('What is an OTP?') == 'otp'
    assert general_topic('What is an OTP and can I skip Digi Yatra verification?') is None
    assert 'documented airport list or retention policy IS answerable' in SYSTEM_PROMPT


def test_second_retrieval_recovers_new_approved_evidence_without_recording_twice(app_factory, retriever, monkeypatch):
    wrong = retriever.search('How do I upload a boarding pass PDF?')
    correct = retriever.search('Who operates Digi Yatra?')
    attempts = []
    monkeypatch.setattr(retriever, 'search', lambda *_: wrong)
    def retry(*args):
        attempts.append(True)
        return correct
    monkeypatch.setattr(retriever, 'retry_search', retry)
    def respond(payload):
        text = payload['messages'][-1]['content']
        return FakeSarvam.ok(grounded_mock(payload) if 'Who operates Digi Yatra?' in text.split('</evidence>')[0] else 'INSUFFICIENT_EVIDENCE')
    fake = FakeSarvam(respond)
    with app_factory(fake) as c:
        r = c.post('/api/v1/chat', json=dict(message='Who operates Digi Yatra?', conversation_id='retry-recovery'))
        assert r.json()['status'] == 'answered' and attempts == [True]
        assert len(fake.requests) == 2
        with c.app.state.db.session() as db:
            assert db.scalar(select(func.count()).select_from(InteractionEvent)) == 1


def test_retry_with_unchanged_evidence_avoids_repeating_paid_calls(app_factory, retriever, monkeypatch, caplog):
    hits = retriever.search('Who operates Digi Yatra?')
    monkeypatch.setattr(retriever, 'retry_search', lambda *_: hits)
    fake = FakeSarvam(lambda _: FakeSarvam.ok('INSUFFICIENT_EVIDENCE'))
    with app_factory(fake) as c:
        body = c.post('/api/v1/chat', json=dict(message='Who operates Digi Yatra?', conversation_id='retry-unchanged')).json()
        assert body['status'] == 'insufficient_evidence' and len(fake.requests) == 1
    assert 'retry_no_new_evidence' in caplog.text
