"""ORM models. Portable across SQLite (development) and PostgreSQL (production).

Privacy design: no chat text is stored. Conversations are keyed by a SHA-256 hash
of the browser's random conversation id; questions are stored only as a topic
category plus allow-listed keywords (never free text).
All timestamps are naive UTC.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # Argon2id PHC string
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Only SHA-256 hashes of the session and CSRF tokens are stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    admin: Mapped[AdminUser] = relationship()


class QuestionTopic(Base):
    """Fixed, privacy-safe question categories (seeded by migration)."""

    __tablename__ = "question_topics"
    slug: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)  # first question received
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    question_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    primary_topic: Mapped[str | None] = mapped_column(ForeignKey("question_topics.slug"))
    # unconfirmed | resolved | unresolved — set ONLY by explicit passenger feedback.
    resolution_status: Mapped[str] = mapped_column(String(12), nullable=False, default="unconfirmed")
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_seconds: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        Index("ix_conversations_started_at", "started_at"),
        Index("ix_conversations_status", "resolution_status"),
    )


class InteractionEvent(Base):
    """One chatbot question/answer exchange — metadata only, never message text."""

    __tablename__ = "interaction_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # assistant reply id
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    asked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    topic: Mapped[str] = mapped_column(ForeignKey("question_topics.slug"), nullable=False)
    # Allow-listed vocabulary only (e.g. "aadhaar, otp"), never user-written text.
    keywords: Mapped[str | None] = mapped_column(String(200))
    # answered | insufficient_evidence | out_of_scope | refused | greeting | live_status | error
    answer_status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pii_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        Index("ix_events_asked_at", "asked_at"),
        Index("ix_events_conversation", "conversation_id"),
    )


class ResolutionFeedback(Base):
    """Explicit Yes/No feedback. One row per assistant message (duplicates rejected)."""

    __tablename__ = "resolution_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    message_id: Mapped[str] = mapped_column(ForeignKey("interaction_events.message_id"), nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    __table_args__ = (UniqueConstraint("message_id", name="uq_feedback_message"),)


class AIUsage(Base):
    """Provider accounting only: no prompts, answers, IPs, passenger or conversation IDs."""
    __tablename__ = 'ai_usage'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(12), nullable=False)
    model: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_write_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    estimated_usd: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    locale: Mapped[str | None] = mapped_column(String(2))
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_1h_tokens: Mapped[int | None] = mapped_column(Integer)
    retrieval_tokens_estimated: Mapped[int | None] = mapped_column(Integer)
    priced_amount: Mapped[float | None] = mapped_column(Float)
    pricing_version: Mapped[str | None] = mapped_column(String(24))
    error_kind: Mapped[str | None] = mapped_column(String(24))
    optimized_context: Mapped[bool | None] = mapped_column(Boolean)


class FAQUsage(Base):
    __tablename__ = "faq_usage"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(12))
    locale: Mapped[str] = mapped_column(String(2))
    outcome: Mapped[str] = mapped_column(String(24))
    latency_ms: Mapped[int] = mapped_column(Integer)


class ApprovedFAQ(Base):
    """Manually published public questions and reviewed answers."""
    __tablename__ = "approved_faq"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    locale: Mapped[str] = mapped_column(String(2), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    signature: Mapped[str] = mapped_column(String(64), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False)


class KnowledgeRevision(Base):
    """Operator-reviewed evidence. Chat requests cannot write source revisions."""
    __tablename__ = "knowledge_revision"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[str] = mapped_column(String(64))
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    risk: Mapped[str] = mapped_column(String(16))
    metadata_json: Mapped[dict] = mapped_column(JSON)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewer: Mapped[str | None] = mapped_column(String(80))
    __table_args__ = (
        UniqueConstraint("source_id", "digest"),
        Index("uq_knowledge_published_topic", "topic", unique=True,
              sqlite_where=text("status = 'published'"), postgresql_where=text("status = 'published'")),
    )


class KnowledgeGap(Base):
    """Aggregate topic candidates without a question, identity or model output."""
    __tablename__ = "knowledge_gap"
    topic: Mapped[str] = mapped_column(String(40), primary_key=True)
    observations: Mapped[int] = mapped_column(Integer)
    last_seen: Mapped[datetime] = mapped_column(DateTime)


# ---------------------------------------------------------------------------
# Official-source synchronisation (Pipeline A). Written only by the operator CLI /
# scheduled job; the chat API reads published versions and never fetches sources.
# ---------------------------------------------------------------------------


class OfficialSource(Base):
    """Registry state for one allow-listed source (static or discovered child page)."""
    __tablename__ = "official_source"
    source_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(96), index=True)
    canonical_url: Mapped[str] = mapped_column(String(600), unique=True)
    organization: Mapped[str] = mapped_column(String(80))
    source_type: Mapped[str] = mapped_column(String(24))
    language: Mapped[str] = mapped_column(String(8))
    trust: Mapped[str] = mapped_column(String(32))
    topic: Mapped[str] = mapped_column(String(48))
    risk: Mapped[str] = mapped_column(String(8))
    enabled: Mapped[bool] = mapped_column(Boolean)
    refresh_days: Mapped[int] = mapped_column(Integer)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_due_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    http_status: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(200))
    last_modified: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    content_version: Mapped[int] = mapped_column(Integer)
    verification_status: Mapped[str] = mapped_column(String(24))
    consecutive_failures: Mapped[int] = mapped_column(Integer)
    failure_reason: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    # Task 2: social/YouTube sources (nullable for web sources).
    platform: Mapped[str | None] = mapped_column(String(16))
    account_id: Mapped[str | None] = mapped_column(String(96))
    ownership_evidence: Mapped[dict | None] = mapped_column(JSON)
    cursor: Mapped[str | None] = mapped_column(String(200))   # incremental watermark (e.g. newest post time)
    quota_note: Mapped[str | None] = mapped_column(String(160))


class OfficialRecord(Base):
    """One versioned FAQ / section / document record extracted from an official source."""
    __tablename__ = "official_record"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(96), index=True)
    record_key: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    # verified | pending_review | conflict | superseded | withdrawn | rejected | historical
    status: Mapped[str] = mapped_column(String(16), index=True)
    record_type: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(300))
    category: Mapped[str | None] = mapped_column(String(200))
    question: Mapped[str | None] = mapped_column(String(600))
    body: Mapped[str] = mapped_column(String(20000))
    url: Mapped[str] = mapped_column(String(700))
    anchor: Mapped[str | None] = mapped_column(String(120))
    organization: Mapped[str] = mapped_column(String(80))
    language: Mapped[str] = mapped_column(String(8))
    authority: Mapped[str] = mapped_column(String(32))
    topic: Mapped[str] = mapped_column(String(48))
    risk: Mapped[str] = mapped_column(String(8))
    published_on: Mapped[str | None] = mapped_column(String(10))
    updated_on: Mapped[str | None] = mapped_column(String(10))
    effective_from: Mapped[str | None] = mapped_column(String(10))
    expires_on: Mapped[str | None] = mapped_column(String(10))
    extracted_at: Mapped[datetime] = mapped_column(DateTime)
    review_reason: Mapped[str | None] = mapped_column(String(300))
    reviewer: Mapped[str | None] = mapped_column(String(80))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Task 2: platform provenance. source_kind: website|government|press|faq|social_post|video|
    # transcript|account_profile. media: duration, playlist, languages, transcript status/type,
    # referenced URLs, timestamps, claim_type (announced|proposed|future|pilot|operational).
    source_kind: Mapped[str | None] = mapped_column(String(24))
    platform: Mapped[str | None] = mapped_column(String(16))
    external_id: Mapped[str | None] = mapped_column(String(96))
    account_id: Mapped[str | None] = mapped_column(String(96))
    account_name: Mapped[str | None] = mapped_column(String(120))
    start_s: Mapped[int | None] = mapped_column(Integer)
    media: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("source_id", "record_key", "content_hash"),
                      Index("ix_official_record_key", "source_id", "record_key"),
                      Index("ix_official_record_external", "platform", "external_id"))


class SyncRun(Base):
    """History of synchronisation executions (aggregate counters only)."""
    __tablename__ = "sync_run"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(24))
    trigger: Mapped[str] = mapped_column(String(24))
    stats: Mapped[dict] = mapped_column(JSON)


class KnowledgePublication(Base):
    """An immutable, atomically activated set of verified official records."""
    __tablename__ = "knowledge_publication"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(12))  # active | superseded
    digest: Mapped[str] = mapped_column(String(64))
    record_ids: Mapped[list] = mapped_column(JSON)
    record_count: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (Index("uq_knowledge_publication_active", "status", unique=True,
                            sqlite_where=text("status = 'active'"), postgresql_where=text("status = 'active'")),)


class JobLease(Base):
    """Cross-process lease preventing overlapping synchronisation jobs (PostgreSQL or SQLite)."""
    __tablename__ = "job_lease"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    holder: Mapped[str] = mapped_column(String(64))
    acquired_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
