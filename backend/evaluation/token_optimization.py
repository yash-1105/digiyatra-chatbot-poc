"""Aggregate-only replay. Offline captures first prompts. Live spend requires explicit caps."""

import argparse
import asyncio
import json
import math
import re
import secrets
import tempfile
import time
import uuid
from collections import defaultdict
from pathlib import Path

from app.clients.base import ProviderError
from app.config import Settings
from app.db.migrate import upgrade
from app.main import create_app
from app.schemas.chat import ChatRequest, HistoryItem
from app.services.chat_service import AssistantUnavailable
from app.services.usage import estimate_tokens
from evaluation.bilingual import checks


class PromptCaptured(Exception):
    pass


def cases():
    seen = set()
    for file in ("reliability_questions.json", "bilingual_questions.json", "questions.json"):
        for item in json.loads(Path(__file__).with_name(file).read_text()):
            key = (item["question"], item.get("locale", "en"))
            if key not in seen:
                seen.add(key)
                yield {"locale": "en"} | item
    for question in (
        "Is Digi Yatra optional?", "Is Digi Yatra mandatory?",
        "Can minors use Digi Yatra?", "Can adults use Digi Yatra?",
        "Can I use Digi Yatra for domestic flights?", "Can I use Digi Yatra for international flights?",
        "Are Delhi e-gates working right now?", "Is the Delhi Airport Digi Yatra queue long right now?",
        "Where can I download Digi Yatra?", "Where can I download Digi Yatra in 2024?",
        "Can I use Digi Yatra on Android?", "Can I not use Digi Yatra on Android?",
        "Is Digi Yatra only for iOS?", "Is Digi Yatra available on both iOS and Android?",
        "What does a draft Digi Yatra policy say about the age limit?",
        "What does the superseded Digi Yatra manual say about airport retention?",
        "Is Digi Yatra's saved face data deleted from my personal account?",
        "Can Digi Yatra share my phone number with the airport?",
        "Does Digi Yatra delete airport data 24 hours after departure or registration?",
        "Which airlines support Digi Yatra and which airports are listed?",
        "Which documents establish the operator and airport retention policy?",
        "Can I use a boarding-pass screenshot and how do I delete it?",
        "Can I use a foreign passport for Digi Yatra?",
        "क्या डिजी यात्रा अनिवार्य है?", "क्या डिजी यात्रा वैकल्पिक है?",
        "क्या दिल्ली के ई-गेट अभी काम कर रहे हैं?",
        "Does Digi Yatra work on Android 9?", "Does Digi Yatra work on iOS 17?",
        "Does the app work without an internet connection?",
        "Where can I get Digi Yatra support for an app crash?",
        "What is Digi Yatra's documented data deletion policy for an airport?",
        "When exactly does airport biometric retention start?",
        "Can a 17-year-old use Digi Yatra?", "Can an 18-year-old use Digi Yatra?",
        "Can two people share a Digi Yatra account?",
        "Where do I find the Digi Yatra data policy?",
        "Can I register for Digi Yatra without a phone?",
        "Does Digi Yatra sell facial images?",
        "What airports are planned for Digi Yatra?",
        "List the documented Digi Yatra airports with IATA codes.",
        "Can I use Digi Yatra for a connecting flight?",
        "Where can I find a copy of an excluded document?",
        "Where do I upload my boarding pass?", "Where do I upload my passport?",
        "How do I use DigiLocker during Digi Yatra registration?",
        "Do I need to scan my face every time?",
        "How do I revoke consent in the Digi Yatra app?",
        "सभी दस्तावेज़ित डिजी यात्रा हवाई अड्डों की सूची दें।",
        "Digi Yatra se mera boarding pass kaise hataun?",
    ):
        if (question, "en") not in seen:
            yield dict(question=question, locale="hi" if re.search("[\u0900-\u097f]", question) else "en")


async def run(args, folder):
    from app.cli import cmd_ensure_index

    settings = Settings(_env_file=None,
        index_dir=Path(args.index) if args.index else folder / "index",
        database_url=f"sqlite:///{folder / 'eval.db'}",
        embedding_provider="lexical",
        **({"faq_cache_enabled": True, "faq_cache_signing_key": secrets.token_urlsafe(32)} if args.faq_bundle else {}),
        **({"rag_context_optimization_enabled": True} if args.optimized else {}),
        **({"anthropic_prompt_cache": args.prompt_cache} if args.prompt_cache is not None else {}),
        log_chat_content=False,
        log_level="ERROR",
        environment="development",
    )
    if not args.index:
        cmd_ensure_index(settings)
    upgrade(settings.database_url)  # temporary synthetic database only
    app = create_app(settings)
    service = app.state.chat_service
    if not service:
        raise SystemExit("Evaluation index unavailable")
    if args.faq_bundle:
        from pydantic import TypeAdapter

        from app.services.faq import FAQEntry

        if not service.d.faqs:
            raise SystemExit("Reviewed FAQ cache unavailable")
        service.d.faqs.publish(TypeAdapter(list[FAQEntry]).validate_json(Path(args.faq_bundle).read_bytes()))
    app.state.chat_service.d.analytics = None
    app.state.chat_service.d.usage = None
    groups = defaultdict(list)
    provider = app.state.providers[args.provider]
    current = {}
    spent_bound = 0.0
    transport_request = provider._client._transport.handle_async_request

    async def capped(request):
        nonlocal spent_bound
        body = json.loads(request.content)
        # Breakpoint writes, all request bytes, full output and retries reserved per HTTP attempt.
        # Deliberately above published rates for the configured providers and short prompts.
        rate = 100 if args.provider == "sarvam" else 5
        reserve = (len(request.content) + body["max_tokens"] + 256) * rate / 1e6
        if spent_bound + reserve > args.cap:
            raise ProviderError("evaluation_cap")
        spent_bound += reserve
        return await transport_request(request)

    async def observed(messages, **kwargs):
        current["input_estimate"].append(sum(estimate_tokens(m["content"]) + 10 for m in messages))
        evidence = re.search(r"<evidence>(.*?)</evidence>", messages[-1]["content"], re.S)
        if evidence:
            current["evidence_estimate"].append(estimate_tokens(evidence[1]))
            current["evidence_blocks"] = len(re.findall(r"(?m)^\[S\d+\]", evidence[1]))
            current["expected_source"] = not case.get("sources") or any(
                f"source: {source} |" in evidence[1] for source in case["sources"]
            )
            current["list_codes"] = len(set(re.findall(r"\(([A-Z]{3})\)", evidence[1])))
        if not args.live:
            raise PromptCaptured
        result = await chat(messages, **kwargs)
        from app.services.usage import usage_values

        current["reported"].append(usage_values(args.provider, result.usage, settings))
        return result

    chat = provider.chat
    provider.chat = observed
    if args.live:
        provider._client._transport.handle_async_request = capped
    selected = list(cases())
    if args.only:
        selected = [c for c in selected if c.get("id") in args.only]
    if args.limit:
        selected = selected[:args.limit]
    previous = defaultdict(list)
    try:
        for case in selected:
            locale = case["locale"]
            current = dict(input_estimate=[], evidence_estimate=[], reported=[], case_id=case.get("id"))
            group = case.get("group")
            start = time.perf_counter()
            try:
                result = await service.handle(ChatRequest(
                    message=case["question"], conversation_id=("evaluation-" + case["group"]) if case.get("group") else uuid.uuid4().hex,
                    locale=locale, provider=args.provider,
                    history=previous[group] if group and not args.live else [],
                ))
            except PromptCaptured:
                pass
            except AssistantUnavailable as exc:
                current["error"] = exc.kind
            else:
                current["status"] = result.status
                current["cached"] = result.cached
                if args.live and "mode" in case:
                    terms = case.get("concepts", [])
                    if all(isinstance(term, str) for term in terms):
                        current["checks"] = checks(case, result.model_dump())
                    else:
                        current["checks"] = checks(dict(case, concepts=[]), result.model_dump())
                        current["checks"]["concepts"] = all(
                            any(term.lower() in result.answer.lower() for term in alternatives)
                            for alternatives in terms
                        )
            if group and not args.live:
                previous[group].append(HistoryItem(role="user", content=case["question"]))
            current["ms"] = (time.perf_counter() - start) * 1000
            groups[locale].append(current)
    finally:
        for client in app.state.providers.values():
            await client.aclose()
        app.state.db.engine.dispose()
    for locale, rows in sorted(groups.items()):
        times = sorted(r["ms"] for r in rows)
        reported = [u for r in rows for u in r["reported"]]
        totals = {key: sum(u.get(key) or 0 for u in reported)
                  for key in ("input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens",
                              "cache_write_tokens", "estimated_usd", "priced_amount")}
        print(json.dumps(dict(
            provider=args.provider, locale=locale, cases=len(rows),
            prepared_calls=sum(len(r["input_estimate"]) for r in rows),
            input_estimate=sum(sum(r["input_estimate"]) for r in rows),
            retrieval_estimate=sum(sum(r["evidence_estimate"]) for r in rows),
            validated_faq_hits=sum(r.get("cached", False) for r in rows),
            evidence_blocks=sum(r.get("evidence_blocks", 0) for r in rows),
            expected_source_matches=sum(r.get("expected_source", False) for r in rows if "expected_source" in r),
            airport_list_max_codes=max(r.get("list_codes", 0) for r in rows),
            p50_ms=round(times[math.ceil(len(times) * .5)-1], 2),
            p95_ms=round(times[math.ceil(len(times) * .95)-1], 2),
            live=args.live, successful_provider_calls=len(reported), totals=totals if reported else None,
            provider_reasoning_reports=sum(u.get("reasoning_tokens") is not None for u in reported),
            evaluation_total_reserved=round(spent_bound, 6) if args.live else None,
            errors={kind: sum(r.get("error") == kind for r in rows) for kind in sorted({r["error"] for r in rows if "error" in r})},
            checks_failed={str(r["case_id"]): sorted(k for k, ok in r["checks"].items() if not ok)
                           for r in rows if r.get("case_id") and "checks" in r and not all(r["checks"].values())},
            checks={key: [sum(r["checks"][key] for r in rows if "checks" in r),
                          sum("checks" in r for r in rows)]
                    for key in next((r["checks"] for r in rows if "checks" in r), {})},
        )))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("sarvam", "anthropic"), required=True)
    parser.add_argument("--index")
    parser.add_argument("--faq-bundle", help="private reviewed fixture used only in the temporary evaluation DB")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--optimized", action="store_true")
    parser.add_argument("--prompt-cache", action=argparse.BooleanOptionalAction)
    parser.add_argument("--cap", type=float, help="maximum reserved list cost, INR for Sarvam and USD for Anthropic")
    args = parser.parse_args()
    if args.live and (args.cap is None or not math.isfinite(args.cap) or args.cap <= 0):
        parser.error("--live requires a positive finite --cap")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    with tempfile.TemporaryDirectory() as temp:
        asyncio.run(run(args, Path(temp)))
