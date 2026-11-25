"""Typed request/response schemas for the public API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ConversationId = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class HistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)
    conversation_id: str = ConversationId
    history: list[HistoryItem] = Field(default_factory=list, max_length=20)
    locale: Literal["en", "hi"] = "en"
    provider: Literal["sarvam", "anthropic", "novita"] = "sarvam"

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message must not be blank")
        return v


AnswerStatus = Literal["answered", "insufficient_evidence", "out_of_scope", "refused", "greeting", "live_status"]


class Source(BaseModel):
    id: int
    title: str
    source_file: str
    section: str
    snippet: str
    url: str | None = None
    score: float
    time_sensitive: bool = False
    verification_status: str = "not_applicable"
    # Task 2: website | government | faq | social_post | video | transcript | account_profile (None = approved document)
    source_type: str | None = None
    platform: str | None = None
    published_on: str | None = None
    timestamp_s: int | None = None


class ChatResponse(BaseModel):
    message_id: str
    conversation_id: str
    answer: str
    status: AnswerStatus
    sources: list[Source]
    notices: list[str] = Field(default_factory=list)
    model: str | None = None
    provider: Literal["sarvam", "anthropic", "novita"] = "sarvam"
    locale: Literal["en", "hi"] = "en"
    cached: bool = False
    answer_mode: Literal["knowledge", "general", "insufficient"] = "knowledge"


class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversation_id: str = ConversationId
    message_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    resolved: bool


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    index: dict
    llm: dict
    database: dict = {}
