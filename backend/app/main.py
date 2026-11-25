"""FastAPI application factory."""

from __future__ import annotations

import json
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import admin, chat, health
from app.clients.anthropic import AnthropicChatClient
from app.clients.novita import NovitaChatClient
from app.clients.sarvam import SarvamChatClient
from app.config import Settings, get_settings
from app.db.session import Database
from app.logging_config import configure_logging
from app.rag.factory import build_retriever
from app.rag.retriever import Retriever
from app.rag.store import IndexNotBuilt, KnowledgeIndex
from app.security.body_limit import BodySizeLimitMiddleware
from app.security.rate_limit import RateLimiter
from app.services.analytics import AnalyticsService
from app.services.auth import AuthService, LoginThrottle
from app.services.chat_service import AssistantUnavailable, ChatDeps, ChatService
from app.services.conversation import ConversationStore
from app.services.usage import UsageService

log = logging.getLogger(__name__)


def _error(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers=headers)


def _conflict_guidance(settings: Settings) -> dict[str, str]:
    """Conflict guidance ships with the deployment corpus; the manifest is a local-development fallback."""
    for path, key in ((settings.knowledge_corpus_dir / "corpus.json", "conflicts"),
                      (settings.approval_manifest, "known_conflicts")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {c["id"]: c["guidance"] for c in data.get(key, [])}
        except (OSError, ValueError, KeyError):
            continue
    return {}


def create_app(
    settings: Settings | None = None,
    *,
    retriever: Retriever | None = None,
    llm: SarvamChatClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    problems = settings.production_problems()
    if problems:
        raise RuntimeError("Refusing to start with insecure production configuration: " + "; ".join(problems))
    production = settings.environment == "production"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        for client in app.state.providers.values():
            await client.aclose()
        app.state.db.engine.dispose()

    app = FastAPI(
        title="Digi Yatra Chatbot POC API",
        version=__version__,
        lifespan=lifespan,
        # No public API explorer / schema in production.
        docs_url=None if production else "/api/docs",
        openapi_url=None if production else "/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.rate_limiter = RateLimiter(settings.rate_limit_requests, settings.rate_limit_window_s)
    app.state.llm = llm or SarvamChatClient(
        settings.sarvam_api_key.get_secret_value() if settings.sarvam_api_key else None,
        base_url=settings.sarvam_base_url,
        model=settings.sarvam_chat_model,
        timeout_s=settings.sarvam_timeout_s,
        max_retries=settings.sarvam_max_retries,
        max_tokens=settings.sarvam_max_tokens,
        temperature=settings.sarvam_temperature,
        reasoning_effort=settings.sarvam_reasoning_effort,
    )
    app.state.providers = {"sarvam": app.state.llm, "anthropic": AnthropicChatClient(
        settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None,
        max_tokens=settings.anthropic_max_tokens, timeout_s=settings.anthropic_timeout_s,
        prompt_cache=settings.anthropic_prompt_cache, workspace_id=settings.anthropic_workspace_id)}
    app.state.anthropic_rate_limiter = RateLimiter(settings.anthropic_rate_limit_requests, settings.rate_limit_window_s)
    app.state.providers["novita"] = NovitaChatClient(
        settings.novita_api_key.get_secret_value() if settings.novita_api_key else None,
        max_tokens=settings.novita_max_tokens, timeout_s=settings.novita_timeout_s,
        max_retries=settings.novita_max_retries, max_concurrency=settings.novita_max_concurrency,
        enable_thinking=settings.novita_enable_thinking,
    )
    app.state.novita_rate_limiter = RateLimiter(settings.novita_rate_limit_requests, settings.rate_limit_window_s)
    # Database (analytics + admin). The schema is created by Alembic (`python -m app.cli db-upgrade`),
    # never implicitly at startup.
    app.state.db = Database(settings.database_url)
    migrated = app.state.db.is_migrated()
    if not migrated:
        log.error("Database schema missing: run `python -m app.cli db-upgrade`. Analytics and admin are disabled.")
    app.state.analytics = AnalyticsService(app.state.db) if migrated else None
    app.state.ai_usage = UsageService(app.state.db, settings) if migrated else None
    app.state.auth = (
        AuthService(app.state.db, settings.admin_session_ttl_minutes, settings.admin_session_idle_minutes)
        if migrated else None
    )
    app.state.admin_login_capacity = threading.BoundedSemaphore(2)
    app.state.login_throttle = LoginThrottle(settings.admin_login_max_failures, settings.admin_login_window_minutes)
    app.state.index_meta = None
    app.state.retriever = None
    app.state.published_knowledge = None
    try:
        if retriever is None:
            index = KnowledgeIndex(settings.index_dir, settings.index_table)
            retriever = build_retriever(settings, index)
            app.state.index_meta = index.meta()
        else:
            app.state.index_meta = retriever.index.meta()
        app.state.retriever = retriever
        app.state.evaluation_conversations = ConversationStore(max_conversations=50, ttl_s=300, max_turns=10)
        reviewed_faqs = None
        if settings.faq_cache_enabled and migrated:
            from app.services.faq import ReviewedFAQs

            try:
                reviewed_faqs = ReviewedFAQs(app.state.db, settings, retriever)
            except Exception as exc:  # noqa: BLE001 - a broken cache must not block startup
                log.warning("faq unavailable error=%s", type(exc).__name__)
        from app.services.knowledge import Knowledge

        knowledge = Knowledge(app.state.db) if migrated and settings.knowledge_enrichment_enabled else None
        app.state.chat_service = ChatService(
            ChatDeps(settings, retriever, app.state.llm, ConversationStore(), _conflict_guidance(settings),
                     analytics=app.state.analytics, providers=app.state.providers, usage=app.state.ai_usage, faqs=reviewed_faqs, knowledge=knowledge)
        )
        log.info("Knowledge index loaded: %d approved chunks", retriever.chunk_count)
        app.state.published_knowledge = None
        if settings.official_knowledge_serving_enabled and migrated:
            from app.sync.publish import PublishedKnowledge

            def swap(new_retriever, meta):
                # One attribute assignment per object: requests see the old or the new complete index.
                faqs = None
                if settings.faq_cache_enabled:
                    from app.services.faq import ReviewedFAQs

                    try:
                        faqs = ReviewedFAQs(app.state.db, settings, new_retriever)
                    except Exception as exc:  # noqa: BLE001 - stale cache entries simply stop matching
                        log.warning("faq unavailable after publication error=%s", type(exc).__name__)
                service = app.state.chat_service
                service.d.faqs = faqs
                service.d.retriever = new_retriever
                app.state.retriever, app.state.index_meta = new_retriever, meta

            app.state.published_knowledge = PublishedKnowledge(settings, app.state.db, swap, app.state.index_meta)
    except (IndexNotBuilt, RuntimeError) as exc:
        log.error("Knowledge index unavailable: %s", exc)
        app.state.chat_service = None

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        allow_credentials=False,
        max_age=600,
    )

    @app.middleware("http")
    async def require_index(request: Request, call_next):
        if request.url.path.startswith("/api/v1/chat") and request.app.state.chat_service is None:
            return _error(503, "index_unavailable", "The knowledge base is not available. Please try again later.")
        if request.url.path == "/api/v1/chat" and request.app.state.published_knowledge is not None:
            # Lazy, rate-limited version check (reads PostgreSQL only; never an external source).
            request.app.state.published_knowledge.maybe_refresh()
        response = await call_next(request)
        cookie = getattr(request.state, "anonymous_cookie_header", None)
        if cookie and "set-cookie" not in response.headers:
            response.headers.append("set-cookie", cookie)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    @app.exception_handler(AssistantUnavailable)
    async def _assistant_unavailable(_: Request, exc: AssistantUnavailable):
        code = "upstream_timeout" if exc.status_code == 504 else "assistant_unavailable"
        return _error(exc.status_code, code, exc.user_message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        fields = sorted({".".join(str(p) for p in e.get("loc", [])[1:]) or "body" for e in exc.errors()})
        return _error(422, "validation_error", f"Invalid request ({', '.join(fields)}).")

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            return _error(exc.status_code, exc.detail["code"], exc.detail["message"], getattr(exc, "headers", None))
        return _error(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error: %s", type(exc).__name__)
        return _error(500, "internal_error", "Something went wrong. Please try again.")

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(admin.router)
    return app
