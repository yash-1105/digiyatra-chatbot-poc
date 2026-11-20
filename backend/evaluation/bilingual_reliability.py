"""Grade private bilingual replay records without printing answers or source passages."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import time
import uuid
from collections import defaultdict
from pathlib import Path

import httpx

from app.rag.query import evidence_tokens, normalize_query

SCREENSHOT_CASES = json.loads(Path(__file__).with_name("bilingual_reliability_cases.json").read_text())
EXPECTED_SOURCES = {
    "download_cost": {"registration_details.md"},
    "international": {"general_04_app_eligibility.md", "support_04_general_information.md"},
    "international_repeat": {"general_04_app_eligibility.md", "support_04_general_information.md"},
    "face": {"support_01_app_troubleshooting.md", "general_02_how_it_works.md"},
    "offline": {"end_to_end_process.md"},
    "digilocker": {"end_to_end_process.md", "general_02_how_it_works.md"},
    "epassport": {"general_04_app_eligibility.md"},
}


def grade(case, provider, locale, response, *, require_snapshot_lead=False):
    answer = response.get("answer", "")
    q = normalize_query(answer)
    words = evidence_tokens(answer)
    sources = response.get("sources") or []
    markers = {int(k) for k in re.findall(r"\[(\d+)\]", answer)}
    hindi = len(re.findall(r"[\u0900-\u097f]", answer))
    model = {"sarvam": "sarvam-105b", "anthropic": "claude-haiku-5-5"}[provider]
    results = {
        "routing": response.get("provider") == provider and response.get("locale") == locale,
        "language": hindi >= 20 if locale == "hi" else hindi == 0 and len(answer) >= 25,
        "uncached": response.get("cached") is False,
    }
    if case == "service_cost":
        results.update(gap=response.get("status") == "insufficient_evidence" and not sources and not markers
                       and "fee" in words and (" not " in q or "नहीं" in answer),
                       model=response.get("model") is None)
        return results

    results.update(
        model=response.get("model") == model,
        status=response.get("status") == "answered",
        citation=bool(markers) and markers == {s["id"] for s in sources}
        and EXPECTED_SOURCES[case].intersection(s["source_file"] for s in sources) != set(),
    )
    if case == "download_cost":
        results["claims"] = "store" in words and {"android", "ios"} <= words and (
            "download price" in q and "not specify" in q or "शुल्क नहीं बताया" in answer
        )
    elif case in {"international", "international_repeat", "epassport"}:
        results["claims"] = "domestic" in words and ("airport" in words or "airport" in q)
        results["freshness"] = "not live verification" in q or "स्वतंत्र पुष्टि" in answer
        if response.get("status") == "answered" and require_snapshot_lead:
            results["snapshot_lead"] = answer.startswith(("The document snapshot", "Document snapshot", "दस्तावेज़ के स्नैपशॉट", "दस्तावेज़ का स्नैपशॉट"))
        if case == "epassport":
            results["roadmap"] = bool({"roadmap", "future", "plan", "proposed"} & words) and re.search(
                r"\be[-‐‑ ]?passport", q
            ) is not None
    elif case == "face":
        results["capture"] = sum(bool(chunk & words) for chunk in (
            {"camera", "steady"}, {"light", "lighting", "lit", "welllit"}, {"background"}, {"glass", "cover"},
        )) >= 2
        results["manual"] = "manual" in words and "system" in words and ("down" in words or "unavailable" in words)
    elif case == "offline":
        results["stages"] = bool({"otp", "aadhaar", "selfie"} & words) and "register" in words and "board" in words and (
            {"face", "verification"} <= words or {"facial", "verification"} <= words
        )
        results["gap"] = "not specify" in q or "नहीं बताया" in answer
    elif case == "digilocker":
        results["claims"] = {"digilocker", "register"} <= words and "airport" in q and (
            "aadhaar" in words or "identity" in words
        )
    return results


def deployed(args, catalog=SCREENSHOT_CASES):
    """Drive the signed route within the deployed rate limits and a conservative list-price budget."""
    if not (math.isfinite(args.inr) and math.isfinite(args.usd) and args.inr > 0 and args.usd > 0):
        raise SystemExit("Live matrix requires positive --inr and --usd caps")
    cases = [case for case in catalog if not args.only or case[0] in args.only]
    # Production limits as of this release. Includes two generations, citation repair after
    # each, HTTP retries, byte ceiling and full output allowance at published rates.
    estimate = len(cases) * 2 * args.rounds
    if args.inr < estimate * 3 or args.usd < estimate * 0.06:
        raise SystemExit("Live matrix exceeds the conservative retry-inclusive spending cap")
    secret = os.environ.get("PROXY_SHARED_SECRET", "").encode()
    if not secret:
        raise SystemExit("PROXY_SHARED_SECRET is required for analytics-isolated requests")
    rows = []
    providers = (args.provider,) if args.provider else ("sarvam", "anthropic")
    locales = [(idx, loc) for idx, loc in ((1, "en"), (2, "hi")) if not args.locale or args.locale == loc]
    last = 0.0
    last_for_provider = defaultdict(float)
    with httpx.Client(timeout=90) as client:
        for run in range(args.rounds):
            for idx, locale in locales:
                conversations = {p: "eval-matrix-" + uuid.uuid4().hex for p in providers}
                for case in cases:
                    for provider in providers:
                        # Production has both a global bucket and a ten-per-minute Anthropic bucket.
                        wait_until = max(last + 3.4, last_for_provider[provider] + (6.5 if provider == "anthropic" else 0))
                        time.sleep(max(0, wait_until - time.monotonic()))
                        body = json.dumps(dict(message=case[idx], conversation_id=conversations[provider],
                                               locale=locale, provider=provider)).encode()
                        stamp = str(int(time.time()))
                        digest = hashlib.sha256(body).hexdigest()
                        sig = hmac.new(secret, f"evaluation:v1\n{stamp}\n{digest}".encode(), "sha256").hexdigest()
                        start = time.monotonic()
                        last = last_for_provider[provider] = start
                        response = client.post(args.url.rstrip("/") + "/api/v1/chat", content=body,
                                               headers={"content-type": "application/json",
                                                        "x-dy-evaluation": stamp + "." + sig})
                        if response.is_success and response.headers.get("x-dy-evaluation") != "synthetic":
                            raise SystemExit("Synthetic isolation was not acknowledged")
                        rows.append(dict(case=case[0], provider=provider, locale=locale, run=run,
                                         status=response.status_code, seconds=time.monotonic() - start,
                                         response=response.json()))
                        print(f"{provider} {locale} round={run+1} {case[0]} HTTP={response.status_code}",
                              flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path, nargs="?")
    parser.add_argument("--url")
    parser.add_argument("--require-snapshot-lead", action="store_true")
    parser.add_argument("--provider", choices=("sarvam", "anthropic"))
    parser.add_argument("--locale", choices=("en", "hi"))
    parser.add_argument("--rounds", type=int, default=2, choices=(1, 2))
    parser.add_argument("--inr", type=float, default=0)
    parser.add_argument("--usd", type=float, default=0)
    parser.add_argument("--only", nargs="+", choices=[case[0] for case in SCREENSHOT_CASES])
    args = parser.parse_args()
    if bool(args.replay) == bool(args.url):
        parser.error("Provide a private replay file or --url")
    rows = json.loads(args.replay.read_text()) if args.replay else deployed(args)
    groups = defaultdict(lambda: [0, 0])
    failures = []
    for row in rows:
        provider, locale, case = row["provider"], row["locale"], row["case"]
        result = grade(case, provider, locale, row.get("response", {}), require_snapshot_lead=args.require_snapshot_lead)
        missing = [key for key, passed in result.items() if not passed]
        group = groups[f"{provider}:{locale}"]
        group[0] += not missing
        group[1] += 1
        if missing:
            failures.append([provider, locale, row["run"], case, missing])
    timings = {}
    for group in groups:
        values = sorted(r["seconds"] for r in rows if f'{r["provider"]}:{r["locale"]}' == group and "seconds" in r)
        if values:
            timings[group] = dict(p50=round(values[(len(values) - 1) // 2], 3),
                                  p95=round(values[(95 * len(values) - 1) // 100], 3))
    print(json.dumps({"passed_total": dict(groups), "latency_seconds": timings, "failures": failures},
                     ensure_ascii=False))
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
