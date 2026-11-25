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
    general_system_prompt,
    general_topic,
    missing_minor_facts,
    qwen_answer_focus,
    qwen_general_fallback,
    qwen_scope_score,
    restricted_request,
    scoped_answer_complete,
    snapshot_note,
    verified_introduction,
    verified_retention,
)
from app.services.context import limited_history, optimized_context, select_context
from app.services.conversation import ConversationStore, Turn
from app.services.faq import ReviewedFAQs, faq_key
from app.services.knowledge import AIRPORT_TOPIC, TRIAL_TOPIC, Knowledge, historical_airport_catalog, supplemental_topic
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


VIDEO_REQUEST = re.compile(r"\b(?:videos?|tutorials?|youtube|watch|walkthrough|demo)\b|वीडियो|विडियो|ट्यूटोरियल|dikhao|dikha", re.I)
PROCEDURE = re.compile(r"\bhow (?:do|can|to)\b|\bsteps?\b|\b(?:register|enrol|enroll|upload|add|delete|share)\b|"
                       r"कैसे|kaise", re.I)


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
    knowledge: Knowledge | None = field(default=None)
    track_gaps: bool = True


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
        source_type=c.extra.get("source_kind") if c.extra else None,
        platform=c.extra.get("platform") if c.extra else None,
        published_on=c.as_of if c.extra and c.extra.get("source_kind") else None,
        timestamp_s=int(c.extra["start_s"]) if c.extra and str(c.extra.get("start_s") or "").isdigit() else None,
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

    def _airport_coverage(self, req: ChatRequest, coverage: RetrievedChunk | None, notices: list[str]) -> ChatResponse:
        # The archived list comes from the existing approval-filtered, reassembled catalogue.
        historical = historical_airport_catalog(req.message)
        sources = []
        answer = ""
        if historical:
            hits = self.d.retriever.search("Which airports support Digi Yatra?", 3)
            archive = next((hit for hit in hits if hit.source_file == "available_airports.md"), None)
            if archive:
                entries = re.findall(r"(?m)^\d+\.\s*(\([A-Z]{3}\)[^\n]+)", archive.text)
                if entries:
                    lead = ("यह पुरानी सूची है। इससे आज की उपलब्धता की पुष्टि नहीं होती।" if req.locale == "hi"
                            else "This is the older documented list. Check with your airline or airport for current availability.")
                    answer = lead + " [1]\n\n" + "\n".join(f"{i}. {name.strip()}" for i, name in enumerate(entries, 1))
                    sources.append(_source(1, archive))
        elif coverage and coverage.as_of and coverage.extra.get("airport_count"):
            count = coverage.extra["airport_count"]
            date = coverage.as_of
            answer = (f"नागर विमानन मंत्रालय ने {date} को बताया कि डिजी यात्रा का इस्तेमाल {count} घरेलू हवाई अड्डों पर हुआ था [1]। "
                      "घोषणा में सभी हवाई अड्डों के नाम नहीं दिए गए हैं। पुरानी 24 हवाई अड्डों की सूची आज की पूरी सूची नहीं है। "
                      "अपनी उड़ान के लिए एयरलाइन या हवाई अड्डे से पुष्टि करें।" if req.locale == "hi" else
                      f"On {date}, the Ministry of Civil Aviation reported Digi Yatra journeys across {count} domestic airports [1]. "
                      "The announcement does not name all the airports. The older 24-airport list is historical. "
                      "Check with your airline or airport for your departure.")
            sources.append(_source(1, coverage))
        if not answer:
            response = self._response(req, "I can't verify the current supported-airport list. Check with your airline or airport.",
                                      "insufficient_evidence", notices=notices)
            return response
        self.d.conversations.append(req.conversation_id, assess_input(req.message).redacted_text, _strip_markers(answer))
        return self._response(req, answer, "answered", sources=sources, notices=notices)

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
            {"role": "user", "content": f"Define {topic} in plain language."},
        ], req)
        keys = [self.d.settings.sarvam_api_key, self.d.settings.anthropic_api_key, self.d.settings.novita_api_key, self.d.settings.faq_cache_signing_key]
        checked = check_output(result.content, n_sources=0, secrets=[key.get_secret_value() for key in keys if key],
                               canary=CANARY, allowed_urls=set(), allowed_url_prefixes=())
        # Never allow a definition to turn into an uncited Digi Yatra policy or invented source.
        forbidden = r"digi\s*yatra|eligibility|retention|fees?|mandatory|immigration requirements"
        if topic not in {"e-passport", "boarding pass QR code", "digilocker"}:
            forbidden += r"|aadhaar|airport|boarding|passport"
        policy = re.search(rf"(?i)\b({forbidden})\b", concepts(checked.text))
        if checked.leaked:
            return self._response(req, MSG_REFUSED, "refused", notices=notices, model=result.model)
        fallback_text = qwen_general_fallback(topic, req.locale) if req.provider == "novita" else None
        incomplete = fallback_text and not (
            re.search(r"(?i)chip|चिप", checked.text) and re.search(r"(?i)identit|पहचान", checked.text)
        )
        if not checked.text or policy or checked.invalid_citations or checked.removed_urls or checked.removed_actions or incomplete:
            if not fallback_text:
                return self._response(req, MSG_INSUFFICIENT, "insufficient_evidence", notices=notices, model=result.model)
            checked.text = fallback_text
        answer = ("सामान्य जानकारी (डिजी यात्रा की नीति नहीं):\n\n" if req.locale == "hi" else "General explanation (not Digi Yatra policy):\n\n") + checked.text
        self.d.conversations.append(req.conversation_id, assess_input(req.message).redacted_text, checked.text)
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

    def _recommend_video(self, req: ChatRequest, a, resp: ChatResponse) -> ChatResponse:
        """Attach one verified official video (metadata-only) when the user asks for a video, or a
        procedural answer would benefit from one. Never changes the grounded answer's claims; links come
        only from verified records; nothing is fetched."""
        if resp.status not in ("answered", "insufficient_evidence") or a.pii_types or a.injection or a.action_request:
            return resp
        q = normalize_query(req.message)
        explicit = bool(VIDEO_REQUEST.search(q) or VIDEO_REQUEST.search(req.message))
        procedural = bool(PROCEDURE.search(q) or PROCEDURE.search(req.message))
        if not (explicit or (procedural and resp.status == "answered")):
            return resp
        try:
            videos = self.d.retriever.related_videos(req.message, 1)
        except Exception as exc:  # noqa: BLE001 - recommendations are optional
            log.warning("video recommendation failed error=%s", type(exc).__name__)
            return resp
        known = {s.url for s in resp.sources}
        videos = [v for v in videos if v.urls and v.urls[0] not in known]
        if not videos:
            return resp
        v = videos[0]
        src = _source(len(resp.sources) + 1, v)
        url = v.urls[0]
        if req.locale == "hi":
            line = f"आधिकारिक डिजी यात्रा फ़ाउंडेशन वीडियो देखें: “{v.doc_title}” — {url}"
        else:
            line = f"You can also watch the official Digi Yatra Foundation video “{v.doc_title}”: {url}"
        if resp.status == "insufficient_evidence" and explicit:
            # Recommend the verified video without claiming anything about its spoken content.
            line = (f"यह आधिकारिक डिजी यात्रा फ़ाउंडेशन वीडियो इस विषय से जुड़ा है: “{v.doc_title}” — {url}" if req.locale == "hi"
                    else f"This official Digi Yatra Foundation video covers this topic: “{v.doc_title}”: {url}")
            return resp.model_copy(update={"answer": line, "status": "answered", "sources": [*resp.sources, src],
                                           "answer_mode": "knowledge"})
        if explicit:  # the user asked for a video: lead with it, then the grounded answer
            lead = (f"हाँ — {line}" if req.locale == "hi" else
                    f"Yes — the official Digi Yatra Foundation video “{v.doc_title}”: {url}")
            return resp.model_copy(update={"answer": f"{lead}\n\n{resp.answer.strip()}", "sources": [*resp.sources, src]})
        return resp.model_copy(update={"answer": f"{resp.answer.rstrip()}\n\n{line}", "sources": [*resp.sources, src]})

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
            elif self.d.knowledge and supplemental_topic(a.redacted_text, query_intent(a.redacted_text)):
                cache_outcome = "supplemental_scope"
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
            resp = self._recommend_video(req, a, resp)
        except AssistantUnavailable:
            await self._faq_metric(req, cache_outcome, started)
            await self._record(req, uuid.uuid4().hex, asked_at, classify_text, "error", 0, bool(a.pii_types), started)
            raise
        if (self.d.knowledge and self.d.track_gaps and resp.status == "insufficient_evidence"
            and a.domain_related and not (a.pii_types or a.injection or a.live_status or a.action_request)
            and not restricted_request(a.redacted_text)):
            intent = query_intent(a.redacted_text)
            topic = supplemental_topic(a.redacted_text, intent) or intent or "other_digi_yatra"
            try:
                with anyio.move_on_after(0.35):
                    await anyio.to_thread.run_sync(self.d.knowledge.gap, topic, abandon_on_cancel=True)
            except Exception as exc:  # noqa: BLE001
                log.warning("knowledge gap write failed error=%s", type(exc).__name__)
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
        focus, guidance = qwen_answer_focus(question, intent) if req.provider == "novita" else ("", "")
        reason = "answered"
        hits: list[RetrievedChunk] = []

        async def insufficient(why: str, top: float = 0.0, model=None):
            nonlocal reason
            reason = why
            log.info("chat fallback_decision provider=%s locale=%s intent=%s reason=%s retry=%s", req.provider, req.locale, intent or "none", why, retrieval_retry)
            if focus == "introduction" and (intro := verified_introduction(hits, req.locale)):
                source, text = intro
                self.d.conversations.append(req.conversation_id, question, _strip_markers(text))
                return done(self._response(req, text, "answered", sources=[_source(1, source)],
                                           notices=notices, model=model), top)
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
        normalized = normalize_query(question)
        gate_status = (
            self.d.knowledge and re.search(r"\bgates?\b|गेट", normalized)
            and re.search(r"\b(?:now|today|abhi|aaj)\b|अभी|आज", normalized)
            and re.search(r"\b(?:open|working|closed|down|chalu)\b|चालू|खुल[ाे]|बंद|काम कर", normalized)
        )
        if a.live_status or gate_status:
            reason = "live_operation_request"
            return done(self._response(req, MSG_LIVE, "live_status", notices=notices))
        supplemental = None
        expired = None
        topic_key = supplemental_topic(question, intent)
        if self.d.knowledge and topic_key and not a.pii_types and not a.action_request:
            try:
                with anyio.move_on_after(0.35):
                    supplemental, expired = await anyio.to_thread.run_sync(
                        self.d.knowledge.lookup, topic_key, abandon_on_cancel=True,
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("supplemental lookup failed error=%s", type(exc).__name__)
        trial = bool(supplemental and topic_key == TRIAL_TOPIC)
        if restriction := restricted_request(question, published_trial=trial or bool(expired)):
            reason = "restricted_account_or_policy_request"
            return done(self._response(req, restriction, "insufficient_evidence", notices=notices))

        if self.d.knowledge and topic_key == AIRPORT_TOPIC and not a.pii_types and not a.action_request:
            reason = "dated_airport_coverage"
            return done(self._airport_coverage(req, supplemental, notices))
        if expired and topic_key == TRIAL_TOPIC:
            reason = "trial_source_expired"
            text = (f"The published trial window ended on {expired}. I can't confirm an extension or wider availability. "
                    "Check with your airline for your flight." if req.locale == "en" else
                    f"घोषित ट्रायल की अवधि {expired} को समाप्त हुई। इसकी अवधि बढ़ने या व्यापक उपलब्धता की पुष्टि नहीं है। "
                    "अपनी उड़ान के लिए एयरलाइन से जाँचें।")
            response = no_evidence()
            response.answer = text
            return done(response)

        topic = general_topic(question, qwen=req.provider == "novita")
        if topic and s.general_knowledge_enabled and not a.pii_types:
            # Definition requests are distinct from nearby troubleshooting FAQs.
            # If no approved source actually defines the term, use the narrow general mode.
            stable_extension = topic in {"digilocker", "e-passport", "boarding pass QR code", "biometric verification"}
            definition_hits = [] if stable_extension else self.d.retriever.search(question, s.retrieval_top_k)
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
        if focus in {"introduction", "children"}:
            targets = {
                "introduction": (
                    ("general_01_introduction.md", {"question": "What is Digi Yatra?"}),
                    ("general_02_how_it_works.md", {"section": "At the Airport"}),
                ),
                "children": (
                    ("allowed_passengers.md", {"question": "Are passengers with infants allowed to use DigiYatra?"}),
                    ("support_02_registration_profile.md", {"question": "How do I add my child or other family members?"}),
                    ("support_05_usage_eligibility.md", {"question": "Traveling with Infants/Children without Aadhaar"}),
                ),
            }[focus]
            preferred = [hit for source, fields in targets if (hit := self.d.retriever.approved_passage(source, **fields))]
            ordinary_search = search

            def search(query, top_k):
                if len(preferred) >= top_k:
                    return preferred[:top_k]
                pinned = {hit.chunk_id for hit in preferred}
                return (preferred + [hit for hit in ordinary_search(query, top_k) if hit.chunk_id not in pinned])[:top_k]
        if trial:
            candidates = hits = [supplemental]
        elif s.rag_context_optimization_enabled:
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
        if supplemental and not trial:
            hits = select_context([supplemental, *hits], s.context_token_budget, s.context_top_k)
        log.info("chat retrieval provider=%s locale=%s retry=%s candidates=%d selected=%d",
                 req.provider, req.locale, retrieval_retry, len(candidates), len(hits))
        same_evidence = retrieval_retry and {h.chunk_id for h in hits} == (previous_evidence or set())
        if same_evidence and (not hits or intent not in SCOPED_INTENTS and focus not in {"airport_retention", "children"}):
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
        prompt = SYSTEM_PROMPT + ("\n" + guidance if guidance else "")
        messages: list[dict] = [{"role": "system", "content": prompt}]
        if summary:
            messages.append({"role": "user", "content": "Earlier topic hints only, not evidence: " + summary})
        for t in bounded_history:
            messages.append({"role": t.role, "content": t.content})
        turn = build_user_turn(question, evidence, compact=s.rag_context_optimization_enabled, trial=trial)
        if s.conversational_answers_enabled:
            turn += "\nLead with the answer in everyday language. Use 1–4 sentences for simple questions. Avoid source narration."
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

        secrets_list = [key.get_secret_value() for key in (s.sarvam_api_key, s.anthropic_api_key, s.novita_api_key, s.faq_cache_signing_key) if key]
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
            checked.text, {k: hit - 1 for k, hit in enumerate(checked.cited, 1)}, [h.text for h in hits],
            verified_current=frozenset({0}) if trial else frozenset(),
        )
        if grounded.dropped or grounded.reattributed or grounded.removed_markers:
            log.info("chat grounding dropped=%d reattributed=%d removed_markers=%d",
                     grounded.dropped, grounded.reattributed, grounded.removed_markers)
        if focus == "introduction" and not qwen_scope_score(focus, grounded.text):
            return await insufficient("introduction_missing_purpose", top, result.model)
        if not grounded.cited_hits or not grounded.text:
            log.warning("chat ungrounded_after_sentence_check")
            return await insufficient("all_claims_unsupported", top, result.model)
        checked.text = grounded.text
        if focus == "airport_retention":
            precise = normalize_query(checked.text)
            if re.search(r"(?i)\b(?:for|at least|exactly)\s+24\s*hours?\b", precise) or not (
                re.search(r"within.{0,15}24|24.{0,25}(?:भीतर|अंदर)", precise)
                and re.search(r"scheduled departure|निर्धारित.{0,35}(?:प्रस्थान|रवानगी)", precise)
            ):
                if retention := verified_retention(hits, req.locale):
                    source, text = retention
                    self.d.conversations.append(req.conversation_id, question, _strip_markers(text))
                    return done(self._response(req, text, "answered", sources=[_source(1, source)],
                                               notices=notices, model=result.model), top)
                return await insufficient("retention_missing_deadline_or_event", top, result.model)
        verified_wallet = (focus == "digilocker_comparison" and supplemental is not None
                           and supplemental.source_file == "supplement:digilocker-overview")
        scope_target = 3 if focus == "connectivity" else int(focus == "digilocker_comparison" and not verified_wallet)
        scope_score = qwen_scope_score(focus, checked.text)
        scoped_complete = scoped_answer_complete(intent, checked.text, question)
        if not trial and not retrieval_retry and (not scoped_complete or scope_score < scope_target):
            log.info("chat fallback_decision provider=%s locale=%s intent=%s reason=missing_documented_scope retry=False",
                     req.provider, req.locale, intent)
            try:
                retry = await self._handle(req, retrieval_retry=True, previous_evidence={h.chunk_id for h in hits})
            except AssistantUnavailable:
                pass  # A failed second attempt does not erase the first grounded answer.
            else:
                if retry.status == "answered" and (not scope_target or qwen_scope_score(focus, retry.answer) >= scope_score):
                    return retry
        if procedure_requested(question) and not re.search(r"(?m)^\d+[.)]\s", checked.text):
            sentences = re.split(r"(?<=[.!?।])\s+", checked.text)
            if len(sentences) >= 2:
                # Format only already-validated sentences; never generate extra actions.
                checked.text = "\n".join(f"{i}. {sentence}" for i, sentence in enumerate(sentences, 1))
        cited_chunks = [hits[i] for i in grounded.cited_hits]
        if verified_wallet and supplemental and not qwen_scope_score(focus, checked.text):
            if supplemental not in cited_chunks:
                cited_chunks.append(supplemental)
            marker = cited_chunks.index(supplemental) + 1
            definition = ("डिजीलॉकर आधिकारिक दस्तावेज़ रखने और साझा करने का डिजिटल वॉलेट है" if req.locale == "hi"
                          else "DigiLocker is a digital wallet for accessing and sharing official documents")
            checked.text += f"\n\n{definition} [{marker}]" + ("।" if req.locale == "hi" else ".")
        if focus == "children" and intent is None:
            for hit, fact in missing_minor_facts(checked.text, hits, req.locale):
                if hit not in cited_chunks:
                    cited_chunks.append(hit)
                marker = cited_chunks.index(hit) + 1
                punctuation = fact[-1]
                checked.text += f"\n\n{fact[:-1]} [{marker}]{punctuation}"
        if any(c.conflict_ids for c in cited_chunks):
            notices.append(NOTICE_CONFLICT)
        sources = [_source(k, c) for k, c in enumerate(cited_chunks, 1)]
        if checked.removed_actions or a.action_request:
            notices.append(NOTICE_NO_ACTIONS)
        if any(c.time_sensitive for c in cited_chunks):
            notices.append(NOTICE_TIME_SENSITIVE)

        gap = "" if trial else evidence_gap(intent, req.locale)
        if intent in {"download_cost", "service_cost"} and any(
            pricing_claim(h.text.partition("\nA: ")[2] if h.question else h.text) for h in cited_chunks
        ):
            gap = ""
        if intent == "connectivity" and any(connectivity_claim(h.text) for h in cited_chunks):
            gap = ""
        if gap:
            checked.text += "\n\n" + gap
        qualification = "" if trial else snapshot_note(cited_chunks, req.locale, documented_policy=intent in {
            "airport_retention", "international_scope", "epassport_scope",
        })
        if qualification:
            if intent in {"international_scope", "epassport_scope"}:
                checked.text = qualification + "\n\n" + checked.text
            else:
                checked.text += "\n\n" + qualification
        reason = "documented_snapshot" if qualification else "grounded_answer"
        self.d.conversations.append(req.conversation_id, question, _strip_markers(checked.text))
        # A lead qualification can coexist with useful, grounded partial guidance.
        partial = intent in {"download_cost", "connectivity", "epassport_scope"}
        status = "insufficient_evidence" if _DECLINE.match(checked.text) and not partial else "answered"
        if trial and supplemental:
            normalized_answer = normalize_query(checked.text)
            conditions = []
            hindi = req.locale == "hi"
            if eligibility := supplemental.extra.get("eligibility"):
                if not all(term in normalized_answer for term in ("indian", "passport")):
                    conditions.append(eligibility[hindi])
            if ends := supplemental.extra.get("ends"):
                if ends[:4] not in normalized_answer:
                    conditions.append(f"घोषित ट्रायल {ends} तक है।" if hindi else f"The announced trial runs through {ends}.")
            if travel_checks := supplemental.extra.get("travel_checks"):
                if "immigration" not in normalized_answer:
                    conditions.append(travel_checks[hindi])
            if conditions:
                checked.text += "\n\n" + " ".join(conditions)
        if trial and s.conversational_answers_enabled:
            # One primary citation is enough in the visible reply. All sentences were grounded above.
            first = re.search(r"\[\d+\]", checked.text)
            if first:
                checked.text = checked.text[:first.end()] + re.sub(r"[ \t]*\[\d+\]", "", checked.text[first.end():])
        if (s.conversational_answers_enabled and status == "answered"
            and intent in {"app_download", "boarding_upload", "boarding_scan", "boarding_pdf", "digilocker_comparison"}
            and all(not h.time_sensitive and not h.conflict_ids for h in cited_chunks)):
            checked.text = re.sub(r"[ \t]*\[\d+\](?:[ \t]*\[\d+\])*", "", checked.text)
        return done(self._response(req, checked.text, status, sources=sources, notices=notices, model=result.model), top)
