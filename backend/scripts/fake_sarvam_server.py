"""OFFLINE E2E STUB of POST /v2/chat/completions — for UI wiring tests only.

It is NOT Sarvam and produces no AI output: it simply echoes the first evidence
item's question with citation markers so the UI path (sources, follow-ups,
errors) can be exercised without an API key. Never used in normal operation.

    .venv/bin/python scripts/fake_sarvam_server.py   # listens on 127.0.0.1:8999
"""

import re

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()


@app.post("/v2/chat/completions")
async def completions(request: Request):
    body = await request.json()
    user = body["messages"][-1]["content"]
    question = user.rsplit("Passenger question:", 1)[-1].strip()
    if "#fail" in question:
        return JSONResponse({"error": {"message": "stub failure", "code": "model_overloaded"}}, status_code=503)
    files = re.findall(r"^\[S(\d+)\] source: ([^|]+?) \|", user, re.M)
    if not files:
        return {"choices": [{"message": {"content": "INSUFFICIENT_EVIDENCE"}, "finish_reason": "stop"}], "model": "stub"}
    n_hist = len(body["messages"]) - 2
    content = (f"[OFFLINE STUB — not AI] Evidence found for: {question} [S1]"
               + (" Additional context. [S2]" if len(files) > 1 else "")
               + (f" (conversation turns so far: {n_hist // 2})" if n_hist else ""))
    return {"choices": [{"message": {"content": content}, "finish_reason": "stop"}], "model": "offline-stub"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8999, log_level="warning")
