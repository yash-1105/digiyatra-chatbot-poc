"""Chat orchestration: guardrails -> retrieval -> Sarvam -> output validation -> citations."""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from fastapi.concurrency import run_in_threadpool

from app.clients.sarvam import SarvamChatClient, SarvamError
from app.config import Settings
from app.db.session import utcnow
from app.rag.retriever import RetrievedChunk, Retriever
from app.schemas.chat import ChatRequest, ChatResponse, Source
from app.security.grounding import ground_answer
from app.security.guardrails import assess_input, check_output, pii_notice
from app.services.analytics import AnalyticsService
from app.services.conversation import ConversationStore, Turn
from app.services.prompts import (
    CANARY,
    CITATION_REPAIR,
    INSUFFICIENT,
    SYSTEM_PROMPT,
    build_user_turn,
    format_evidence,
)

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
    "I couldn't find this in the approved Digi Yatra information available to me, so I won't guess. "
    f"For further help, please contact Digi Yatra customer care at {SUPPORT_EMAIL} or visit "
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
    r"(?i)^(and|also|what about|how about|then|so|but|ok|okay)\b|\b(it|this|that|they|them|those|these|there|same|above)\b"
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
    llm: SarvamChatClient
    conversations: ConversationStore
    conflict_guidance: dict[str, str]
    analytics: AnalyticsService | None = field(default=None)


def _is_follow_up(text: str) -> bool:
    return len(text.split()) <= 4 or bool(_FOLLOW_UP.search(text)) and len(text.split()) <= 14


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
        return ChatResponse(
            message_id=uuid.uuid4().hex,
            conversation_id=req.conversation_id,
            answer=answer,
            status=status,  # type: ignore[arg-type]
            sources=sources or [],
            notices=notices or [],
            model=model,
        )

    def _history(self, req: ChatRequest) -> list[Turn]:
        server = self.d.conversations.history(req.conversation_id)
        if server is not None:
            return server
        # Unknown conversation (e.g. after restart): recover only the user's own past questions.
        return [Turn("user", h.content[:1000]) for h in req.history if h.role == "user"]

    async def _call_llm(self, messages: list[dict], session_id: str):
        try:
            return await self.d.llm.chat(messages, session_id=session_id)
        except SarvamError as exc:
            code, msg = _ERROR_MAP.get(exc.kind, (503, "The AI assistant is temporarily unavailable."))
            log.warning("chat upstream_error kind=%s status=%s", exc.kind, exc.status)
            raise AssistantUnavailable(exc.kind, code, msg) from None

    async def handle(self, req: ChatRequest) -> ChatResponse:
        """Answer the question, then record privacy-safe analytics (failures never affect the reply)."""
        asked_at = utcnow()  # time the question was received = start of resolution timing
        started = time.perf_counter()
        a = assess_input(req.message)
        history = self._history(req)
        prev_user = next((t.content for t in reversed(history) if t.role == "user"), None)
        classify_text = a.redacted_text if not (prev_user and _is_follow_up(a.redacted_text)) else f"{prev_user} {a.redacted_text}"
        try:
            resp = await self._handle(req)
        except AssistantUnavailable:
            await self._record(req, uuid.uuid4().hex, asked_at, classify_text, "error", 0, bool(a.pii_types), started)
            raise
        await self._record(req, resp.message_id, asked_at, classify_text, resp.status, len(resp.sources),
                           bool(a.pii_types), started)
        return resp

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

    async def _handle(self, req: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        s = self.d.settings
        a = assess_input(req.message)
        notices: list[str] = [pii_notice(a.pii_types)] if a.pii_types else []
        question = a.redacted_text

        def done(resp: ChatResponse, top: float = 0.0) -> ChatResponse:
            log.info(
                "chat status=%s sources=%d top_score=%.3f pii=%s latency_ms=%d",
                resp.status, len(resp.sources), top, ",".join(a.pii_types) or "-",
                (time.perf_counter() - started) * 1000,
            )
            if s.log_chat_content:
                log.info("chat content q=%r a=%r", question, resp.answer)
            return resp

        if a.injection:
            return done(self._response(req, MSG_REFUSED, "refused", notices=notices))
        if a.greeting:
            return done(self._response(req, MSG_GREETING, "greeting", notices=notices))
        if a.live_status:
            return done(self._response(req, MSG_LIVE, "live_status", notices=notices))

        history = self._history(req)
        retrieval_query = question
        prev_user = next((t.content for t in reversed(history) if t.role == "user"), None)
        if prev_user and _is_follow_up(question):
            retrieval_query = f"{prev_user} {question}"

        hits = self.d.retriever.search(retrieval_query, s.retrieval_top_k)
        top = hits[0].score if hits else 0.0
        if not hits or (not a.domain_related and top < 0.35):
            status = "insufficient_evidence" if a.domain_related else "out_of_scope"
            msg = MSG_INSUFFICIENT if a.domain_related else MSG_OUT_OF_SCOPE
            if a.action_request:
                notices.append(NOTICE_NO_ACTIONS)
            return done(self._response(req, msg, status, notices=notices), top)

        evidence = format_evidence(hits, self.d.conflict_guidance)
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for t in history[-s.max_history_turns :]:
            messages.append({"role": t.role, "content": t.content})
        messages.append({"role": "user", "content": build_user_turn(question, evidence)})

        result = await self._call_llm(messages, req.conversation_id)
        if INSUFFICIENT not in result.content.upper() and not re.search(r"\[\s*S?\s*\d+", result.content):
            # Observed live: the model occasionally answers correctly but omits [S#] markers.
            # Ask once for a cited rewrite instead of showing an unverifiable answer.
            log.info("chat citation_repair_attempt")
            repair = [*messages, {"role": "assistant", "content": result.content}, {"role": "user", "content": CITATION_REPAIR}]
            result = await self._call_llm(repair, req.conversation_id)

        raw = result.content.strip()
        if INSUFFICIENT in raw.upper():
            # Live testing showed the model sometimes appends the token after a complete, cited answer.
            # The token alone (or with no substantive text) means "no evidence"; otherwise strip it and
            # let citation validation below decide whether the remaining answer is grounded.
            raw = re.sub(re.escape(INSUFFICIENT), "", raw, flags=re.I).strip()
            if len(raw) < 40:
                return done(
                    self._response(req, MSG_INSUFFICIENT, "insufficient_evidence", notices=notices, model=result.model),
                    top,
                )

        secrets_list = [s.sarvam_api_key.get_secret_value()] if s.sarvam_api_key else []
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
            return done(self._response(req, MSG_INSUFFICIENT, "insufficient_evidence", notices=notices, model=result.model), top)

        # Sentence-level grounding: every factual sentence must be supported by the evidence it cites.
        grounded = ground_answer(
            checked.text, {k: hit - 1 for k, hit in enumerate(checked.cited, 1)}, [h.text for h in hits]
        )
        if grounded.dropped or grounded.reattributed or grounded.removed_markers:
            log.info("chat grounding dropped=%d reattributed=%d removed_markers=%d",
                     grounded.dropped, grounded.reattributed, grounded.removed_markers)
        if not grounded.cited_hits or not grounded.text:
            log.warning("chat ungrounded_after_sentence_check")
            return done(self._response(req, MSG_INSUFFICIENT, "insufficient_evidence", notices=notices, model=result.model), top)
        checked.text = grounded.text
        cited_chunks = [hits[i] for i in grounded.cited_hits]
        if any(c.conflict_ids for c in cited_chunks):
            notices.append(NOTICE_CONFLICT)
        sources = [_source(k, c) for k, c in enumerate(cited_chunks, 1)]
        if checked.removed_actions or a.action_request:
            notices.append(NOTICE_NO_ACTIONS)
        if any(c.time_sensitive for c in cited_chunks):
            notices.append(NOTICE_TIME_SENSITIVE)

        self.d.conversations.append(req.conversation_id, question, _strip_markers(checked.text))
        status = "insufficient_evidence" if _DECLINE.match(checked.text) else "answered"
        return done(self._response(req, checked.text, status, sources=sources, notices=notices, model=result.model), top)
