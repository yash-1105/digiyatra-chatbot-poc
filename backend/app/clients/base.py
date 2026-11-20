"""Shared provider contract. Browser requests select a provider, never a model or URL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

ErrorKind = Literal["not_configured", "auth", "workspace", "model_access", "quota", "rate_limited", "bad_request", "unavailable", "timeout", "empty"]


class ProviderError(RuntimeError):
    def __init__(self, kind: ErrorKind, status: int | None = None, request_id: str | None = None, usage: dict | None = None) -> None:
        super().__init__(f"AI API error: {kind}")
        self.kind, self.status, self.request_id = kind, status, request_id
        self.usage = usage or {}


@dataclass
class ChatResult:
    content: str
    finish_reason: str | None
    model: str
    usage: dict = field(default_factory=dict)
    request_id: str | None = None


class ChatClient(Protocol):
    model: str
    max_tokens: int

    @property
    def configured(self) -> bool: ...
    async def chat(self, messages: list[dict], *, session_id: str | None = None) -> ChatResult: ...
    async def aclose(self) -> None: ...
