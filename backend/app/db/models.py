"""ORM models. Portable across SQLite (development) and PostgreSQL (production).

Privacy design: no chat text is stored. Conversations are keyed by a SHA-256 hash
of the browser's random conversation id; questions are stored only as a topic
category plus allow-listed keywords (never free text).
All timestamps are naive UTC.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
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
