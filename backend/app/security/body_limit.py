"""ASGI middleware enforcing a maximum request-body size (with or without Content-Length)."""

from __future__ import annotations

import json


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _reject(self, send) -> None:
        body = json.dumps(
            {"error": {"code": "request_too_large", "message": "The request is too large."}}
        ).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    if int(value) > self.max_bytes:
                        return await self._reject(send)
                except ValueError:
                    return await self._reject(send)
        received = 0
        too_large = False

        async def limited_receive():
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, limited_receive, tracking_send)
        if too_large and not started:
            await self._reject(send)
