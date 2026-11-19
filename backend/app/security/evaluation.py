"""Operator-authenticated synthetic requests: real inference without analytics writes.

Uses the existing server-only proxy secret with a separate HMAC purpose, body
binding and a 60-second lifetime. Public clients cannot opt out of analytics.
All normal chat validation, provider limits and guardrails still apply.
"""

import hashlib
import hmac
import time

from fastapi import HTTPException, Request


async def synthetic_request(request: Request, conversation_id: str) -> bool:
    header = request.headers.get("x-dy-evaluation")
    if header is None:
        return False
    secret = request.app.state.settings.proxy_shared_secret
    stamp, _, signature = header.partition(".")
    valid = False
    if secret and stamp.isascii() and stamp.isdigit() and len(stamp) <= 12:
        digest = hashlib.sha256(await request.body()).hexdigest()
        message = f"evaluation:v1\n{stamp}\n{digest}".encode()
        expected = hmac.new(secret.get_secret_value().encode(), message, hashlib.sha256).hexdigest()
        valid = abs(time.time() - int(stamp)) <= 60 and hmac.compare_digest(signature.encode(), expected.encode())
    if not valid or not conversation_id.startswith("eval-"):
        raise HTTPException(403, detail={"code": "forbidden", "message": "Invalid evaluation authorization."})
    return True
