"""Chat orchestration: guardrails -> retrieval -> Sarvam -> output validation -> citations."""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field

import anyio
from fastapi.concurrency import run_in_threadpool

from app.clients.base import ChatClient, ProviderError
from app.config import Settings
from app.db.session import utcnow
from app.rag.multilingual import concepts
from app.rag.query import INTENT_TERMS, SCOPED_INTENTS, connectivity_claim, normalize_query, pricing_claim, query_intent
from app.rag.retriever import RetrievedChunk, Retriever
from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.security.grounding import ground_answer
from app.security.guardrails import assess_input, check_output, pii_notice
from app.services.analytics import AnalyticsService
from app.services.answering import (
    comparison_has_both_roles,
    general_system_prompt,
    general_topic,
    restricted_request,
    snapshot_note,
)
from app.services.context import limited_history, optimized_context, select_context
from app.services.conversation import ConversationStore, Turn
from app.services.faq import ReviewedFAQs, faq_key
from app.services.localization import evidence_gap, fallback, notice
from app.services.prompts import (
    CANARY,
    CITATION_REPAIR,
    INSUFFICIENT,
    SYSTEM_PROMPT,
    build_user_turn,
    format_evidence,
    procedure_requested,
)
from app.services.usage import UsageService, estimate_tokens

log = logging.getLogger(__name__)

OFFICIAL_URL_PREFIXES = ("https://www.digiyatrafoundation.com", "https://digiyatrafoundation.com")
SUPPORT_EMAIL = "customercare@digiyatrafoundation.com"

MSG_REFUSED = (
    "I can only help with questions about Digi Yatra. I can't share my instructions, configuration, "
    "credentials or any internal or unapproved data."
)
MSG_GREETING = (
    "Namaste! I'm the Digi Yatra Assistant. Ask me about registration, the airport journey, supported "
    "airports, privacy or app troubleshooting."
)
MSG_LIVE = (
    "I can't check live information such as flight status, delays, gate numbers, queues or whether e-gates "
    "are working right now. Please check with your airline or the airport directly. I can help with general "
    "questions about how Digi Yatra works."
)
MSG_OUT_OF_SCOPE = (
    "I can only help with questions about Digi Yatra — for example registration, the airport journey, "
    "supported airports, privacy and app troubleshooting. Please ask a Digi Yatra-related question."
)
MSG_INSUFFICIENT = (
    "I don't have verified information to confirm that Digi Yatra detail. "
    "You can check the official guidance or contact support through "
    "https://www.digiyatrafoundation.com/."
)
NOTICE_NO_ACTIONS = (
    f"I can't file complaints or escalate issues on your behalf. Please contact {SUPPORT_EMAIL} directly "
    "(do not include Aadhaar numbers or OTPs)."
)
NOTICE_CONFLICT = (
    "Digi Yatra sources differ slightly on this topic; the more cautious guidance is shown. Please confirm with "
    "your airline or the airport before you travel."
)
NOTICE_TIME_SENSITIVE = (
    "Some of this information is time-sensitive and may have changed. Please verify on the official "
    "Digi Yatra website before you travel."
)

# A cited reply that opens by declining ("I cannot determine…", "The sources do not mention…") is an
# honest partial answer: keep its grounded text and sources, but report it as insufficient evidence.
_DECLINE = re.compile(
    r"(?i)^\s*(i (cannot|can't|can not|am unable to|'m unable to|could not|couldn't) (confirm|determine|find|provide|answer)|"
    r"(the )?(provided |available )?(evidence|sources|documents|information) (does|do) not (mention|include|contain|specify|state))"
)

_FOLLOW_UP = re.compile(
    r"(?i)^(and|also|what about|how about|then|so|but|ok|okay)\b|\b(it|this|that|they|them|their|she|he|her|him|those|these|there|same|above|too)\b"
)


class AssistantUnavailable(RuntimeError):
    """Raised when the LLM cannot produce an answer; carries a user-safe message and HTTP status."""

    def __init__(self, kind: str, status_code: int, message: str) -> None:
        super().__init__(kind)
        self.kind = kind
        self.status_code = status_code
        self.user_message = message


_ERROR_MAP = {
    "not_configured": (503, "The AI assistant is not configured on this server yet."),
    "auth": (503, "The AI assistant is temporarily unavailable. Please try again later."),
    "workspace": (503, "The selected AI provider is temporarily unavailable. Please try again later."),
    "model_access": (503, "The selected AI model is temporarily unavailable. Please try again later."),
    "quota": (503, "The AI assistant is temporarily unavailable. Please try again later."),
    "rate_limited": (503, "The assistant is receiving too many requests. Please wait a moment and try again."),
    "bad_request": (502, "The assistant could not process this request. Please rephrase and try again."),
    "unavailable": (503, "The AI assistant is temporarily unavailable. Please try again shortly."),
    "timeout": (504, "The assistant took too long to respond. Please try again."),
    "empty": (502, "The assistant returned an empty response. Please try again."),
}


@dataclass
class ChatDeps:
    settings: Settings
    retriever: Retriever
    llm: ChatClient
    conversations: ConversationStore
    conflict_guidance: dict[str, str]
    analytics: AnalyticsService | None = field(default=None)
    providers: dict[str, ChatClient] | None = field(default=None)
    usage: UsageService | None = field(default=None)
    faqs: ReviewedFAQs | None = field(default=None)


def _is_follow_up(text: str) -> bool:
    if general_topic(text):
        return False
    return bool(_FOLLOW_UP.search(concepts(text))) and len(text.split()) <= 20


def _strip_markers(text: str) -> str:
    return re.sub(r"\[\d+\]", "", text).strip()


def _source(i: int, c: RetrievedChunk) -> Source:
    body = (f"Q: {c.question} — " if c.question else "") + re.sub(r"^Q: .*?\nA: ", "", c.text, flags=re.S)
    body = re.sub(r"\s+", " ", body).strip()
    title = c.doc_title if c.section in (c.doc_title, "") else f"{c.doc_title} — {c.section}"
    return Source(
        id=i,
        title=title[:160],
        source_file=c.source_file,
        section=c.section,
        snippet=body[:240] + ("…" if len(body) > 240 else ""),
        url=next((u for u in c.urls if u.startswith(("https://", "http://"))), None),
        score=c.score,
        time_sensitive=c.time_sensitive,
        verification_status=c.verification_status,
    )


class ChatService:
    def __init__(self, deps: ChatDeps) -> None:
        self.d = deps

    def _response(self, req: ChatRequest, answer: str, status: str, sources=None, notices=None, model=None) -> ChatResponse:
        if req.locale == "hi":
            if status != "answered" and not sources:
                answer = fallback(status, answer)
            notices = [notice(n) for n in (notices or [])]
        return ChatResponse(
            message_id=uuid.uuid4().hex,
            conversation_id=req.conversation_id,
            answer=answer,
            status=status,  # type: ignore[arg-type]
            sources=sources or [],
            notices=notices or [],
            model=model,
            provider=req.provider, locale=req.locale,
            answer_mode="knowledge" if status == "answered" else "insufficient",
        )

    def _history(self, req: ChatRequest) -> list[Turn]:
        server = self.d.conversations.history(req.conversation_id)
        if server is not None:
            return server
        # Unknown conversation (e.g. after restart): recover only the user's own past questions.
        return [Turn("user", assess_input(h.content[:1000]).redacted_text)
                for h in req.history if h.role == "user" and not assess_input(h.content).injection]

    async def _general_answer(self, req: ChatRequest, topic: str, notices: list[str]) -> ChatResponse:
        result = await self._call_llm([
            {"role": "system", "content": general_system_prompt(topic, CANARY)},
            {"role": "user", "content": req.message},
        ], req)
        keys = [self.d.settings.sarvam_api_key, self.d.settings.anthropic_api_key, self.d.settings.faq_cache_signing_key]
        checked = check_output(result.content, n_sources=0, secrets=[key.get_secret_value() for key in keys if key],
                               canary=CANARY, allowed_urls=set(), allowed_url_prefixes=())
        # Never allow a definition to turn into an uncited Digi Yatra policy or invented source.
        policy = re.search(r"(?i)\b(digi\s*yatra|aadhaar|airport|boarding|eligibility|retention|passport)\b", concepts(checked.text))
        if checked.leaked:
            return self._response(req, MSG_REFUSED, "refused", notices=notices, model=result.model)
        if not checked.text or policy or checked.invalid_citations or checked.removed_urls or checked.removed_actions:
            return self._response(req, MSG_INSUFFICIENT, "insufficient_evidence", notices=notices, model=result.model)
        answer = ("सामान्य जानकारी (डिजी यात्रा की नीति नहीं):\n\n" if req.locale == "hi" else "General explanation (not Digi Yatra policy):\n\n") + checked.text
        self.d.conversations.append(req.conversation_id, req.message, checked.text)
        response = self._response(req, answer, "answered", notices=notices, model=result.model)
        response.answer_mode = "general"
        return response

    async def _usage(self, req, client, usage, status, elapsed, input_estimate=0, *, error=None, retrieval=0):
        if self.d.usage is None:
            return
        try:
            await run_in_threadpool(self.d.usage.record, req.provider, client.model, usage,
                                    status=status, latency_ms=elapsed, fallback_input=input_estimate,
                                    locale=req.locale, error_kind=error, retrieval_tokens_estimated=retrieval,
                                    optimized_context=self.d.settings.rag_context_optimization_enabled)
        except Exception as exc:  # noqa: BLE001 - accounting must not break responses
            log.error("ai_usage record_failed error=%s", type(exc).__name__)

    async def _call_llm(self, messages: list[dict], req: ChatRequest, *, retrieval=0):
        clients = self.d.providers or {"sarvam": self.d.llm}
        client = clients.get(req.provider)
        if client is None:
            raise AssistantUnavailable("not_configured", 503, "The selected AI provider is not configured.")
        language = "Hindi (Devanagari)" if req.locale == "hi" else "English"
        messages = [dict(m) for m in messages]
        messages[0]["content"] += f"\nRESPONSE LANGUAGE: {language}. This overrides the question/history language."
        if req.locale == "hi" or not self.d.settings.rag_context_optimization_enabled:
            messages[-1]["content"] += ("\nउत्तर केवल देवनागरी हिन्दी में दें, रोमन हिन्दी या Hinglish में नहीं। सामान्य शब्द हिन्दी में रखें (पंजीकरण, सहमति, सत्यापन); ऐप के बटन के सटीक नाम और लिंक मूल रूप में रखें।" if req.locale == "hi" else "\nAnswer in English, even if the question/history uses Hindi or Hinglish.")
        estimate = sum(estimate_tokens(m["content"]) + 10 for m in messages)
        # Byte-count ceiling is deliberately conservative across both tokenizers.
        ceiling = sum(len(m["content"].encode()) + 64 for m in messages)
        if estimate > self.d.settings.prompt_token_budget or ceiling > self.d.settings.prompt_token_budget * 3:
            raise AssistantUnavailable("input_budget", 413, "Please shorten your question or start a new conversation.")
        started = time.perf_counter()
        try:
            result = await client.chat(messages, session_id=req.conversation_id)
        except ProviderError as exc:
            await self._usage(req, client, exc.usage, "error", int((time.perf_counter()-started)*1000),
                              0 if exc.kind in {"auth", "workspace", "model_access", "quota", "not_configured", "bad_request"} else estimate,
                              error=exc.kind, retrieval=retrieval)
            code, msg = _ERROR_MAP.get(exc.kind, (503, "The selected AI provider is temporarily unavailable."))
            if req.locale == "hi":
                msg = "चुने गए AI प्रदाता की सेवा अभी उपलब्ध नहीं है। कृपया थोड़ी देर बाद फिर प्रयास करें।"
            log.warning("chat upstream_error provider=%s kind=%s status=%s", req.provider, exc.kind, exc.status)
            raise AssistantUnavailable(exc.kind, code, msg) from None
        await self._usage(req, client, result.usage, "ok", int((time.perf_counter()-started)*1000), estimate, retrieval=retrieval)
        return result

    async def handle(self, req: ChatRequest) -> ChatResponse:
        """Answer the question, then record privacy-safe analytics (failures never affect the reply)."""
        asked_at = utcnow()  # time the question was received = start of resolution timing
        started = time.perf_counter()
        a = assess_input(req.message)
        history = self._history(req)
        prev_user = next((t.content for t in reversed(history) if t.role == "user"), None)
        classify_text = normalize_query(a.redacted_text if not (prev_user and _is_follow_up(a.redacted_text)) else f"{prev_user} {a.redacted_text}")
        cache_outcome, answer, hits = "disabled", None, []
        if self.d.settings.faq_cache_enabled:
            key = faq_key(req.message)
            if not self.d.faqs:
                cache_outcome = "unavailable"
            elif history or req.history:
                cache_outcome = "context"
            elif a.pii_types or a.injection or a.live_status or a.action_request or a.greeting:
                cache_outcome = "safety_or_dynamic"
            elif not key:
                cache_outcome = "unlisted"
            else:
                cache_outcome = "timeout"
                try:
                    with anyio.move_on_after(0.4):
                        cache_outcome, answer, hits = await anyio.to_thread.run_sync(
                            self.d.faqs.lookup, key, req.locale, abandon_on_cancel=True
                        )
                except Exception as exc:  # noqa: BLE001 - cache is optional and fails to ordinary RAG
                    cache_outcome = "invalid_or_error"
                    log.warning("faq lookup failed error=%s", type(exc).__name__)
        try:
            if answer is not None:
                resp = self._response(req, answer, "answered", sources=[_source(i, h) for i, h in enumerate(hits, 1)])
                resp.cached = True
                self.d.conversations.append(req.conversation_id, a.redacted_text, _strip_markers(resp.answer))
            else:
                resp = await self._handle(req)
        except AssistantUnavailable:
            await self._faq_metric(req, cache_outcome, started)
            await self._record(req, uuid.uuid4().hex, asked_at, classify_text, "error", 0, bool(a.pii_types), started)
            raise
        await self._faq_metric(req, cache_outcome, started)
        await self._record(req, resp.message_id, asked_at, classify_text, resp.status, len(resp.sources),
                           bool(a.pii_types), started)
        return resp

    async def _faq_metric(self, req, outcome, started):
        if self.d.usage and self.d.settings.faq_cache_enabled:
            try:
                await run_in_threadpool(self.d.usage.record_faq, req.provider, req.locale, outcome,
                                        int((time.perf_counter() - started) * 1000))
            except Exception as exc:  # noqa: BLE001
                log.warning("faq metric failed error=%s", type(exc).__name__)

    async def _record(self, req, message_id, asked_at, text, status, n_sources, pii, started) -> None:
        if self.d.analytics is None:
            return
        try:
            await run_in_threadpool(
                self.d.analytics.record_interaction,
                conversation_id=req.conversation_id, message_id=message_id, asked_at=asked_at,
                classification_text=text, answer_status=status, source_count=n_sources, pii_detected=pii,
                latency_ms=int((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 - analytics must never break the chatbot
            log.error("analytics record_failed error=%s", type(exc).__name__)

    async def _handle(self, req: ChatRequest, *, retrieval_retry: bool = False, previous_evidence: set[str] | None = None) -> ChatResponse:
        started = time.perf_counter()
        s = self.d.settings
        a = assess_input(req.message)
        notices: list[str] = [pii_notice(a.pii_types)] if a.pii_types else []
        question = a.redacted_text
        intent = query_intent(question)
        reason = "answered"
        hits: list[RetrievedChunk] = []

        async def insufficient(why: str, top: float = 0.0, model=None):
            nonlocal reason
            reason = why
            log.info("chat fallback_decision provider=%s locale=%s intent=%s reason=%s retry=%s", req.provider, req.locale, intent or "none", why, retrieval_retry)
            if not retrieval_retry:
                return await self._handle(req, retrieval_retry=True, previous_evidence={h.chunk_id for h in hits})
            return done(no_evidence(model), top)

        def no_evidence(model=None):
            response = self._response(req, MSG_INSUFFICIENT, "insufficient_evidence", notices=notices, model=model)
            gap = evidence_gap(intent, req.locale)
            if gap:
                response.answer = gap
            return response

        def done(resp: ChatResponse, top: float = 0.0) -> ChatResponse:
            log.info(
                "chat status=%s sources=%d top_score=%.3f pii=%s latency_ms=%d",
                resp.status, len(resp.sources), top, ",".join(a.pii_types) or "-",
                (time.perf_counter() - started) * 1000,
            )
            log.info("chat decision provider=%s locale=%s intent=%s reason=%s retry=%s", req.provider, req.locale, intent or "none", reason, retrieval_retry)
            return resp

        if a.injection:
            reason = "input_injection"
            return done(self._response(req, MSG_REFUSED, "refused", notices=notices))
        if a.greeting:
            reason = "greeting"
            return done(self._response(req, MSG_GREETING, "greeting", notices=notices))
        if a.live_status:
            reason = "live_operation_request"
            return done(self._response(req, MSG_LIVE, "live_status", notices=notices))
        if restriction := restricted_request(question):
            reason = "restricted_account_or_policy_request"
            return done(self._response(req, restriction, "insufficient_evidence", notices=notices))

        topic = general_topic(question)
        if topic:
            # Definition requests are distinct from nearby troubleshooting FAQs.
            # If no approved source actually defines the term, use the narrow general mode.
            definition_hits = self.d.retriever.search(question, s.retrieval_top_k)
            definition = re.compile(rf"(?i)\b{re.escape(topic)}\b.{{0,30}}\b(is|means|stands for|refers to)\b")
            if not any(definition.search(re.sub(r"^Q:.*?\nA:\s*", "", h.text, flags=re.S)) for h in definition_hits):
                reason = "allowlisted_general_definition"
                return done(await self._general_answer(req, topic, notices))

        history = self._history(req)
        retrieval_query = question
        prev_user = next((t.content for t in reversed(history) if t.role == "user"), None)
        if prev_user and _is_follow_up(question):
            previous = [t.content for t in history if t.role == "user"][-3:]
            # Explicit new subjects take precedence over stale conversational anchors.
            if not query_intent(question) or query_intent(question) == "aadhaar_requirement":
                retrieval_query = " ".join([*previous, question])

        bounded_history = limited_history(history, s.history_token_budget, s.max_history_turns)
        discarded = history[:len(history) - len(bounded_history)]
        old_topics = list(dict.fromkeys(query_intent(t.content) for t in discarded if t.role == "user"))
        summary = "; ".join([self.d.conversations.summary(req.conversation_id),
                             *(INTENT_TERMS[t] for t in old_topics[-4:] if t)])
        if summary and _is_follow_up(question) and not query_intent(question):
            retrieval_query = summary + " " + retrieval_query
        search = self.d.retriever.retry_search if retrieval_retry else self.d.retriever.search
        if s.rag_context_optimization_enabled:
            expand = retrieval_retry or intent in {"airport_catalog", "airport_planned"}
            requested = max(s.retrieval_top_k, s.rag_expanded_top_k) if expand else s.retrieval_top_k
            candidates = search(retrieval_query, requested)
            budget = s.rag_expanded_context_token_budget if expand else s.context_token_budget
            fixed = sum(estimate_tokens(t.content) + 10 for t in bounded_history)
            fixed += estimate_tokens(SYSTEM_PROMPT + summary + build_user_turn(question, "", compact=True)) + 240
            top_k = requested if expand else s.context_top_k
            hits = optimized_context(candidates, retrieval_query, min(budget, s.prompt_token_budget - fixed),
                                     top_k, self.d.conflict_guidance)
        else:
            candidates = search(retrieval_query, s.retrieval_top_k)
            hits = select_context(candidates, s.context_token_budget, s.context_top_k)
        log.info("chat retrieval provider=%s locale=%s retry=%s candidates=%d selected=%d",
                 req.provider, req.locale, retrieval_retry, len(candidates), len(hits))
        same_evidence = retrieval_retry and {h.chunk_id for h in hits} == (previous_evidence or set())
        if same_evidence and (not hits or intent not in SCOPED_INTENTS):
            reason = "retry_no_new_evidence"
            return done(no_evidence())
        if not hits and intent == "service_cost":
            reason = "no_approved_service_pricing"
            return done(no_evidence())
        top = hits[0].score if hits else 0.0
        # Absence of evidence for a named requirement is not evidence that it
        # is unnecessary. In particular, general NFC definitions cannot answer
        # questions about Digi Yatra's device requirements.
        if any(not any(re.search(rf"(?i)\b{term}\b", h.text) for h in hits)
               for term in ("nfc", "lounge") if re.search(rf"(?i)\b{term}\b", question)):
            return await insufficient("unsupported_named_subject", top)
        if not hits or (not a.domain_related and not query_intent(retrieval_query) and top < 0.35):
            status = "insufficient_evidence" if a.domain_related else "out_of_scope"
            msg = MSG_INSUFFICIENT if a.domain_related else MSG_OUT_OF_SCOPE
            if a.action_request:
                notices.append(NOTICE_NO_ACTIONS)
            if status == "insufficient_evidence":
                return await insufficient("no_relevant_context", top)
            reason = "out_of_scope"
            return done(self._response(req, msg, status, notices=notices), top)

        evidence = format_evidence(hits, self.d.conflict_guidance)
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if summary:
            messages.append({"role": "user", "content": "Earlier topic hints only, not evidence: " + summary})
        for t in bounded_history:
            messages.append({"role": t.role, "content": t.content})
        turn = build_user_turn(question, evidence, compact=s.rag_context_optimization_enabled)
        if same_evidence:
            turn += (
                "\nGive the applicable supported facts first, one short sentence per point with the matching source marker. "
                "Leave unsupported details to the application when the documents give useful partial guidance."
            )
        messages.append({"role": "user", "content": turn})

        result = await self._call_llm(messages, req, retrieval=estimate_tokens(evidence))
        if INSUFFICIENT not in result.content.upper() and not re.search(r"\[\s*S?\s*\d+", result.content):
            # Observed live: the model occasionally answers correctly but omits [S#] markers.
            # Ask once for a cited rewrite instead of showing an unverifiable answer.
            log.info("chat citation_repair_attempt")
            repair = [*messages, {"role": "assistant", "content": result.content}, {"role": "user", "content": CITATION_REPAIR}]
            result = await self._call_llm(repair, req, retrieval=estimate_tokens(evidence))

        raw = result.content.strip()
        if INSUFFICIENT in raw.upper():
            # Live testing showed the model sometimes appends the token after a complete, cited answer.
            # The token alone (or with no substantive text) means "no evidence"; otherwise strip it and
            # let citation validation below decide whether the remaining answer is grounded.
            raw = re.sub(re.escape(INSUFFICIENT), "", raw, flags=re.I).strip()
            if len(raw) < 40:
                return await insufficient("model_insufficient_evidence", top, result.model)

        secrets_list = [key.get_secret_value() for key in (s.sarvam_api_key, s.anthropic_api_key, s.faq_cache_signing_key) if key]
        allowed_urls = {u for h in hits for u in h.urls}
        checked = check_output(
            raw,
            n_sources=len(hits),
            secrets=secrets_list,
            canary=CANARY,
            allowed_urls=allowed_urls,
            allowed_url_prefixes=OFFICIAL_URL_PREFIXES,
        )
        if checked.leaked:
            log.warning("chat output_blocked reason=leak")
            return done(self._response(req, MSG_REFUSED, "refused", notices=notices, model=result.model), top)
        if checked.invalid_citations:
            log.warning("chat invalid_citations_removed=%d", checked.invalid_citations)
        if not checked.cited or not checked.text:
            # Ungrounded answer: never show it without verifiable citations.
            log.warning("chat ungrounded_answer_blocked")
            return await insufficient("no_valid_citations", top, result.model)

        # Sentence-level grounding: every factual sentence must be supported by the evidence it cites.
        grounded = ground_answer(
            checked.text, {k: hit - 1 for k, hit in enumerate(checked.cited, 1)}, [h.text for h in hits]
        )
        if grounded.dropped or grounded.reattributed or grounded.removed_markers:
            log.info("chat grounding dropped=%d reattributed=%d removed_markers=%d",
                     grounded.dropped, grounded.reattributed, grounded.removed_markers)
        if not grounded.cited_hits or not grounded.text:
            log.warning("chat ungrounded_after_sentence_check")
            return await insufficient("all_claims_unsupported", top, result.model)
        checked.text = grounded.text
        if intent == "digilocker_comparison" and not retrieval_retry and not comparison_has_both_roles(checked.text):
            log.info("chat fallback_decision provider=%s locale=%s intent=%s reason=missing_comparison_role retry=False",
                     req.provider, req.locale, intent)
            try:
                retry = await self._handle(req, retrieval_retry=True, previous_evidence={h.chunk_id for h in hits})
            except AssistantUnavailable:
                pass  # A failed second attempt does not erase the first grounded answer.
            else:
                if retry.status == "answered":
                    return retry
        if procedure_requested(question) and not re.search(r"(?m)^\d+[.)]\s", checked.text):
            sentences = re.split(r"(?<=[.!?।])\s+", checked.text)
            if len(sentences) >= 2:
                # Format only already-validated sentences; never generate extra actions.
                checked.text = "\n".join(f"{i}. {sentence}" for i, sentence in enumerate(sentences, 1))
        cited_chunks = [hits[i] for i in grounded.cited_hits]
        if any(c.conflict_ids for c in cited_chunks):
            notices.append(NOTICE_CONFLICT)
        sources = [_source(k, c) for k, c in enumerate(cited_chunks, 1)]
        if checked.removed_actions or a.action_request:
            notices.append(NOTICE_NO_ACTIONS)
        if any(c.time_sensitive for c in cited_chunks):
            notices.append(NOTICE_TIME_SENSITIVE)

        gap = evidence_gap(intent, req.locale)
        if intent in {"download_cost", "service_cost"} and any(
            pricing_claim(h.text.partition("\nA: ")[2] if h.question else h.text) for h in cited_chunks
        ):
            gap = ""
        if intent == "connectivity" and any(connectivity_claim(h.text) for h in cited_chunks):
            gap = ""
        if gap:
            checked.text += "\n\n" + gap
        qualification = snapshot_note(cited_chunks, req.locale, documented_policy=intent in {
            "airport_retention", "international_scope", "epassport_scope",
        })
        if qualification:
            checked.text += "\n\n" + qualification
        reason = "documented_snapshot" if qualification else "grounded_answer"
        self.d.conversations.append(req.conversation_id, question, _strip_markers(checked.text))
        # A lead qualification can coexist with useful, grounded partial guidance.
        partial = intent in {"download_cost", "connectivity", "epassport_scope"}
        status = "insufficient_evidence" if _DECLINE.match(checked.text) and not partial else "answered"
        return done(self._response(req, checked.text, status, sources=sources, notices=notices, model=result.model), top)
