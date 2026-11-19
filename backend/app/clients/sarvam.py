"""Sarvam AI Chat Completions V2 client (POST {base}/v2/chat/completions).

* Key is read from settings (SARVAM_API_KEY) and sent only in the
  `api-subscription-key` header; it is never logged or echoed.
* Retries 429/502/503 and transport timeouts with exponential backoff,
  honouring Retry-After (capped).
* Raises SarvamError with a coarse `kind` so the API can show a clear,
  non-technical message without leaking upstream details.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

import httpx

log = logging.getLogger(__name__)

ErrorKind = Literal["not_configured", "auth", "quota", "rate_limited", "bad_request", "unavailable", "timeout", "empty"]
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SarvamError(RuntimeError):
    def __init__(self, kind: ErrorKind, status: int | None = None, request_id: str | None = None) -> None:
        super().__init__(f"Sarvam API error: {kind}" + (f" (HTTP {status})" if status else ""))
        self.kind = kind
        self.status = status
        self.request_id = request_id


@dataclass
class ChatResult:
    content: str
    finish_reason: str | None
    model: str
    usage: dict = field(default_factory=dict)
    request_id: str | None = None


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)


class SarvamChatClient:
    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.sarvam.ai",
        model: str = "sarvam-105b",
        timeout_s: float = 60.0,
        max_retries: int = 2,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        reasoning_effort: str | None = "low",
        transport: httpx.AsyncBaseTransport | None = None,
        backoff_base_s: float = 1.0,
    ) -> None:
        self._key = api_key
        self.model = model
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.reasoning_effort = reasoning_effort
        self.backoff_base_s = backoff_base_s
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_s, connect=10.0),
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _payload(self, messages: list[dict]) -> dict:
        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.reasoning_effort:
            body["reasoning_effort"] = self.reasoning_effort
        return body

    async def chat(self, messages: list[dict], *, session_id: str | None = None) -> ChatResult:
        if not self._key:
            raise SarvamError("not_configured")
        headers = {"api-subscription-key": self._key, "Content-Type": "application/json"}
        if session_id:
            headers["x-session-affinity"] = session_id
        payload = self._payload(messages)

        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.post("/v2/chat/completions", json=payload, headers=headers)
            except httpx.TimeoutException:
                if attempt <= self.max_retries:
                    await asyncio.sleep(self.backoff_base_s * 2 ** (attempt - 1))
                    continue
                raise SarvamError("timeout") from None
            except httpx.TransportError:
                if attempt <= self.max_retries:
                    await asyncio.sleep(self.backoff_base_s * 2 ** (attempt - 1))
                    continue
                raise SarvamError("unavailable") from None

            if resp.status_code == 200:
                try:
                    return self._parse(resp)
                except SarvamError as exc:
                    # Reasoning used the whole token budget (finish_reason=length, empty content):
                    # retry once with reasoning disabled rather than failing the user.
                    if exc.kind == "empty" and payload.get("reasoning_effort") not in (None, "none"):
                        log.warning("Sarvam returned empty content (reasoning budget); retrying with reasoning off")
                        payload = {**payload, "reasoning_effort": "none"}
                        continue
                    raise

            req_id = self._request_id(resp)
            log.warning("Sarvam API returned HTTP %s (attempt %d, request_id=%s)", resp.status_code, attempt, req_id)
            if resp.status_code in RETRYABLE_STATUS and attempt <= self.max_retries:
                await asyncio.sleep(self._retry_after(resp, attempt))
                continue
            raise SarvamError(self._kind_for(resp.status_code), resp.status_code, req_id)

    # ---------------------------------------------------------------- helpers
    def _retry_after(self, resp: httpx.Response, attempt: int) -> float:
        try:
            ra = float(resp.headers.get("retry-after", ""))
            return max(0.0, min(ra, 10.0))
        except ValueError:
            return self.backoff_base_s * 2 ** (attempt - 1)

    @staticmethod
    def _request_id(resp: httpx.Response) -> str | None:
        try:
            return resp.json().get("error", {}).get("request_id")
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _kind_for(status: int) -> ErrorKind:
        if status in (401, 403):
            return "auth"
        if status == 402:
            return "quota"
        if status == 429:
            return "rate_limited"
        if status in (400, 404, 413, 422):
            return "bad_request"
        return "unavailable"

    def _parse(self, resp: httpx.Response) -> ChatResult:
        try:
            data = resp.json()
            choice = data["choices"][0]
            content = (choice.get("message") or {}).get("content") or ""
        except (ValueError, KeyError, IndexError, TypeError):
            raise SarvamError("empty", resp.status_code) from None
        content = _THINK.sub("", content).strip()
        if not content:
            raise SarvamError("empty", resp.status_code)
        return ChatResult(
            content=content,
            finish_reason=choice.get("finish_reason"),
            model=data.get("model", self.model),
            usage=data.get("usage") or {},
            request_id=data.get("id"),
        )
