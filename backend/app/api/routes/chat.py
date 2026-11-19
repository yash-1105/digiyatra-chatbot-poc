from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool

from app.api.deps import rate_limited
from app.schemas.chat import ChatRequest, ChatResponse, ErrorResponse, FeedbackRequest
from app.security.evaluation import synthetic_request
from app.security.rate_limit import client_key
from app.services.chat_service import ChatService

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

_ERRORS = {
    413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 429: {"model": ErrorResponse},
    502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}, 504: {"model": ErrorResponse},
}


@router.post("", response_model=ChatResponse, responses=_ERRORS, dependencies=[Depends(rate_limited)])
async def chat(body: ChatRequest, request: Request, response: Response) -> ChatResponse:
    st = request.app.state
    if body.provider == "anthropic":
        key = client_key(request, st.settings.trusted_proxies, st.settings.trusted_proxy_hops)
        allowed, wait = st.anthropic_rate_limiter.check(key)
        if not allowed:
            raise HTTPException(429, detail={"code": "rate_limited", "message": "Please wait before using this provider again."}, headers={"Retry-After": str(wait)})
    service = st.chat_service
    if await synthetic_request(request, body.conversation_id):
        service = ChatService(replace(service.d, analytics=None, usage=None, conversations=st.evaluation_conversations))
        response.headers["x-dy-evaluation"] = "synthetic"
    return await service.handle(body)


@router.post("/feedback", status_code=204, responses=_ERRORS, dependencies=[Depends(rate_limited)])
async def feedback(body: FeedbackRequest, request: Request) -> Response:
    """Explicit "Did this resolve your issue?" feedback. Idempotent: one vote per assistant message;
    repeated submissions are accepted (204) but never counted twice. Stores no message content."""
    analytics = request.app.state.analytics
    if analytics is None:
        raise HTTPException(503, detail={"code": "database_unavailable", "message": "Feedback is temporarily unavailable."})
    outcome = await run_in_threadpool(
        analytics.record_feedback, conversation_id=body.conversation_id, message_id=body.message_id, resolved=body.resolved
    )
    if outcome.reason == "unknown_message":
        raise HTTPException(404, detail={"code": "unknown_message", "message": "This answer can no longer receive feedback."})
    if outcome.reason == "expired":
        raise HTTPException(410, detail={"code": "feedback_expired", "message": "Feedback for this answer has expired."})
    return Response(status_code=204)
