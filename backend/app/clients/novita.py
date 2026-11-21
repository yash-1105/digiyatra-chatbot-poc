"""Novita Qwen3.8 Flash via the fixed Chat Completions endpoint."""

from __future__ import annotations

import asyncio
import re

import httpx
from anyio import CapacityLimiter, WouldBlock

from app.clients.base import ChatResult, ErrorKind, ProviderError

_THINK = re.compile(r"<think\b[^>]*>.*?(?:</think\s*>|$)", re.I | re.S)
_THINK_END = re.compile(r"</think\s*>", re.I)
_TRANSIENT = {"rate_limited", "unavailable"}


class NovitaChatClient:
    model = "qwen/qwen3.8-flash"

    def __init__(
        self,
        api_key: str | None,
        *,
        max_tokens: int = 1200,
        timeout_s: float = 25,
        max_retries: int = 1,
        max_concurrency: int = 8,
        enable_thinking: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._key = (api_key or "").strip()
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self._timeout_s = timeout_s
        self.enable_thinking = enable_thinking
        self._capacity = CapacityLimiter(max_concurrency)
        self._client = httpx.AsyncClient(
            base_url="https://api.novita.ai/openai/",
            timeout=httpx.Timeout(timeout_s, connect=min(timeout_s, 5)),
            limits=httpx.Limits(max_connections=max_concurrency, max_keepalive_connections=max_concurrency),
            transport=transport,
            trust_env=False,
        )

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def chat(self, messages: list[dict], *, session_id: str | None = None) -> ChatResult:
        if not self.configured:
            raise ProviderError("not_configured")
        try:
            self._capacity.acquire_nowait()
        except WouldBlock:
            raise ProviderError("rate_limited") from None
        try:
            async with asyncio.timeout(self._timeout_s):
                return await self._complete(messages)
        except TimeoutError:
            raise ProviderError("timeout") from None
        finally:
            self._capacity.release()

    async def _complete(self, messages: list[dict]) -> ChatResult:
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.2,
            "stream": False,
            "enable_thinking": self.enable_thinking,
            "separate_reasoning": True,
        }
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.post(
                    "v1/chat/completions", json=payload, headers={"Authorization": f"Bearer {self._key}"}
                )
            except httpx.TimeoutException:
                # A read timeout can occur after billed inference starts.
                raise ProviderError("timeout") from None
            except httpx.TransportError:
                raise ProviderError("unavailable") from None
            try:
                decoded = response.json()
            except ValueError:
                decoded = {}
            data = decoded if isinstance(decoded, dict) else {}
            if response.status_code == 200 and not data.get("error"):
                return self._parse(data)
            kind = self._error_kind(response.status_code, data)
            if kind not in _TRANSIENT or attempt == self.max_retries:
                raise ProviderError(kind, response.status_code)
            try:
                delay = float(response.headers.get("Retry-After", ""))
            except ValueError:
                delay = 0.25 * 2 ** attempt
            if not 0 <= delay <= 2:
                raise ProviderError(kind, response.status_code)
            await asyncio.sleep(delay)
        raise ProviderError("unavailable")

    @staticmethod
    def _error_kind(status: int, data: dict) -> ErrorKind:
        error = data.get("error")
        if not isinstance(error, dict):
            error = data
        # Match codes and known message fragments without retaining upstream text.
        detail = " ".join(str(error.get(field, "")) for field in ("code", "type", "message")).lower()
        if status == 402 or any(word in detail for word in (
            "balance", "insufficient credit", "quota_exceeded", "billing", "budget",
        )):
            return "quota"
        if status == 404 or any(word in detail for word in (
            "model_not_found", "model_not_available", "model access", "access_deny",
        )):
            return "model_access"
        if status in (401, 403) or any(code in detail for code in (
            "invalid_api_key", "missing_api_key", "failed_to_auth",
        )):
            return "auth"
        if status == 429:
            return "rate_limited"
        if status == 408:
            return "timeout"
        if status in (400, 413, 422):
            return "bad_request"
        return "unavailable"

    def _parse(self, data: dict) -> ChatResult:
        usage = self._usage(data.get("usage"))
        try:
            choice = data["choices"][0]
            message = choice["message"]
            raw = message["content"]
            finish = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError("empty", 200, usage=usage) from None
        if (data.get("model") != self.model or message.get("role") != "assistant"
                or not isinstance(raw, str) or finish != "stop"):
            raise ProviderError("empty", 200, usage=usage)
        # Read only visible content. A compatibility backend may embed thinking tags there.
        content = _THINK_END.split(_THINK.sub("", raw))[-1].strip()
        if not content:
            raise ProviderError("empty", 200, usage=usage)
        return ChatResult(content, finish, self.model, usage)

    @staticmethod
    def _usage(raw) -> dict:
        if not isinstance(raw, dict):
            return {}
        usage = {k: raw[k] for k in ("prompt_tokens", "completion_tokens")
                 if type(raw.get(k)) is int and raw[k] >= 0}
        for key, metrics in (
            ("prompt_tokens_details", ("cached_tokens", "cache_read_Prompt_tokens", "cache_creation_Prompt_tokens")),
            ("completion_tokens_details", ("reasoning_tokens",)),
        ):
            detail = raw.get(key)
            if isinstance(detail, dict):
                usage[key] = {metric: detail[metric] for metric in metrics
                              if type(detail.get(metric)) is int and detail[metric] >= 0}
        return usage
