"""Official Anthropic Messages API; no SDK dependency and no provider fallback."""

from __future__ import annotations

import asyncio

import httpx

from app.clients.base import ChatResult, ProviderError
from app.services.prompts import CANARY


class AnthropicChatClient:
    model = "claude-haiku-5-5"

    def __init__(
        self,
        api_key: str | None,
        *,
        max_tokens: int = 900,
        timeout_s: float = 45,
        prompt_cache: bool = False,
        workspace_id: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._key = api_key
        self.max_tokens = max_tokens
        self.prompt_cache = prompt_cache
        self.workspace_id = workspace_id.strip() if workspace_id else None
        self._client = httpx.AsyncClient(base_url="https://api.anthropic.com", timeout=timeout_s, transport=transport)

    @property
    def configured(self) -> bool:
        return bool(self._key)

    async def aclose(self) -> None:
        await self._client.aclose()

    def _payload(self, messages: list[dict]) -> dict:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        # The random leak marker stays authoritative in a later, uncached block.
        cacheable = system.replace(f" [{CANARY}]", "")
        blocks = [{"type": "text", "text": system}]
        # Stable instructions only: no passenger messages in the shared cache prefix.
        # Haiku 5.5's minimum is 512 tokens. No padding to manufacture cache eligibility.
        if self.prompt_cache and len(cacheable.encode("utf-8")) >= 2048:
            blocks = [{"type": "text", "text": cacheable,
                       "cache_control": {"type": "ephemeral", "ttl": "5m"}}]
            if CANARY in system:
                blocks.append({"type": "text", "text": f"Leak detection marker [{CANARY}]."})
        return {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "output_config": {"effort": "low"},
            # This client produces short evidence-grounded text without tools.
            # Adaptive thinking can consume the whole output allowance before visible text.
            "thinking": {"type": "disabled"},
            "system": blocks,
            "messages": [m for m in messages if m["role"] != "system"],
        }

    async def chat(self, messages: list[dict], *, session_id: str | None = None) -> ChatResult:
        if not self._key:
            raise ProviderError("not_configured")
        for attempt in range(2):
            try:
                r = await self._client.post(
                    "/v1/messages",
                    json=self._payload(messages),
                    headers={
                        "x-api-key": self._key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                        **({"anthropic-workspace-id": self.workspace_id} if self.workspace_id else {}),
                    },
                )
            except httpx.TimeoutException:
                raise ProviderError("timeout") from None
            except httpx.TransportError:
                raise ProviderError("unavailable") from None
            if r.status_code == 200:
                try:
                    data = r.json()
                    text = "\n".join(b["text"] for b in data["content"] if b.get("type") == "text").strip()
                    if not text or data.get("stop_reason") == "refusal":
                        raise ProviderError("empty", r.status_code, usage=data.get("usage") or {})
                    return ChatResult(
                        text, data.get("stop_reason"), self.model, data.get("usage") or {}, data.get("id")
                    )
                except (ValueError, KeyError, TypeError):
                    raise ProviderError("empty", r.status_code) from None
            if r.status_code in (429, 500, 502, 503, 529) and attempt == 0:
                await asyncio.sleep(0.5)
                continue
            # Insufficient prepaid credit is an availability/quota issue, not a
            # browser request error. Do not expose the upstream billing message.
            if r.status_code in (400, 402, 403, 404):
                try:
                    message = str(r.json().get("error", {}).get("message", "")).lower()
                except (ValueError, AttributeError):
                    message = ""
                if r.status_code == 402 or "credit balance" in message or "billing" in message:
                    raise ProviderError("quota", r.status_code)
                if "workspace" in message:
                    raise ProviderError("workspace", r.status_code)
                if r.status_code in (403, 404) and "model" in message:
                    raise ProviderError("model_access", r.status_code)
            kind = (
                "auth"
                if r.status_code in (401, 403)
                else "rate_limited"
                if r.status_code == 429
                else "bad_request"
                if r.status_code in (400, 404, 413, 422)
                else "unavailable"
            )
            raise ProviderError(kind, r.status_code)
        raise ProviderError("unavailable")
