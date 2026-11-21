"""Opt-in Novita API and signed deployment smoke tests. Prints only verdicts and aggregate usage."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import math
import os
import re
import time
import uuid

import httpx

from app.clients.base import ProviderError
from app.clients.novita import NovitaChatClient
from app.config import Settings
from app.services.usage import usage_values


async def probe(settings, key):
    # Start with one tiny authentication and generation check, with zero retries.
    for language, question, thinking, match in (
        ("en", "What does NFC stand for? Reply in one short English sentence.", False, r"near.field communication"),
        ("hi", "एनएफ़सी का मतलब एक छोटे हिन्दी वाक्य में बताइए।", False, r"[\u0900-\u097f]{3}"),
        ("en", "What does NFC stand for? Reply in one short English sentence.", True, r"near.field communication"),
    ):
        client = NovitaChatClient(key, max_tokens=256, max_retries=0, enable_thinking=thinking)
        started = time.monotonic()
        try:
            result = await client.chat([{"role": "user", "content": question}])
        except ProviderError as exc:
            raise SystemExit(f"Novita probe {language}: {exc.kind} (HTTP {exc.status})") from None
        finally:
            await client.aclose()
        usage = usage_values("novita", result.usage, settings)
        ok = bool(re.search(match, result.content, re.I)) and not usage["tokens_estimated"]
        print(json.dumps({"probe": language, "thinking": thinking, "passed": ok,
                          "seconds": round(time.monotonic() - started, 3), "usage": usage}))
        if not ok:
            raise SystemExit("Live generation or usage check failed")


async def deployment(url, secret):
    rows = (
        ("en", "Can I use Digi Yatra on Android?", r"android"),
        ("en", "And what about iPhone?", r"ios|iphone|app store"),
        ("hi", "डिजी यात्रा एंड्रॉयड पर भी उपलब्ध है?", r"android|एंड्रॉयड"),
        ("hi", "Digi Yatra Android par bhi hai?", r"android|एंड्रॉयड"),
    )
    async with httpx.AsyncClient(timeout=110) as client:
        thread = "eval-novita-" + uuid.uuid4().hex
        for index, (locale, question, expected) in enumerate(rows):
            if index >= 2:
                thread = "eval-novita-" + uuid.uuid4().hex
            body = json.dumps(dict(provider="novita", locale=locale, message=question, conversation_id=thread)).encode()
            timestamp = str(int(time.time()))
            digest = hashlib.sha256(body).hexdigest()
            signature = hmac.digest(secret, f"evaluation:v1\n{timestamp}\n{digest}".encode(), "sha256").hex()
            started = time.monotonic()
            result = await client.post(url.rstrip("/") + "/api/v1/chat", content=body, headers={
                "Content-Type": "application/json", "X-DY-Evaluation": timestamp + "." + signature,
            })
            parsed = result.json()
            answer = parsed.get("answer", "")
            hindi = len(re.findall(r"[\u0900-\u097f]", answer))
            ok = (result.is_success and result.headers.get("x-dy-evaluation") == "synthetic"
                  and parsed.get("model") == NovitaChatClient.model and parsed.get("provider") == "novita"
                  and parsed.get("status") == "answered" and parsed.get("locale") == locale
                  and bool(re.search(expected, answer, re.I)) and (hindi >= 12 if locale == "hi" else hindi == 0)
                  and any(s["source_file"] in {"registration_details.md", "general_04_miscellaneous.md"}
                          for s in (parsed.get("sources") or [])))
            print(json.dumps({"case": index + 1, "locale": locale, "passed": ok, "http": result.status_code,
                              "seconds": round(time.monotonic() - started, 3)}))
            if not ok:
                raise SystemExit("Deployed answer or provenance check failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cap-usd", type=float, required=True)
    parser.add_argument("--url", help="Approved deployment URL, using signed nonpersisted chat requests")
    args = parser.parse_args()
    settings = Settings(_env_file=None)
    fresh_rate = max(settings.novita_input_usd_million, settings.novita_cache_write_usd_million,
                     settings.novita_cached_usd_million)
    # Reserve three 512-input/256-output probes. For the deployment reserve the system's
    # maximum valid input byte budget, output cap, four RAG calls, and three attempts each.
    reserved = 3 * (512 * fresh_rate + 256 * settings.novita_output_usd_million) / 1e6
    if args.url:
        reserved += 4 * 4 * 3 * (48000 * fresh_rate + 4096 * settings.novita_output_usd_million) / 1e6
    if not math.isfinite(args.cap_usd) or args.cap_usd < reserved:
        parser.error(f"Spending cap is below the conservative ${reserved:.4f} list-price reserve")
    key = os.environ.get("NOVITA_API_KEY", "").strip()
    secret = os.environ.get("PROXY_SHARED_SECRET", "").encode()
    if not key or (args.url and not secret):
        parser.error("Set the required credentials through the secure backend environment")
    asyncio.run(probe(settings, key))
    if args.url:
        asyncio.run(deployment(args.url, secret))


if __name__ == "__main__":
    main()
