"""Check verified knowledge, source boundaries and general answers against both providers."""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import median

from app.rag.query import evidence_tokens, normalize_query
from evaluation.bilingual_reliability import deployed

CATALOG = json.loads(Path(__file__).with_name("knowledge_cases.json").read_text())


def checks(row):
    case, provider, locale = row["case"], row["provider"], row["locale"]
    response = row.get("response", {})
    answer = response.get("answer", "")
    q, words = normalize_query(answer), evidence_tokens(answer)
    sources = response.get("sources", [])
    model = "sarvam-105b" if provider == "sarvam" else "claude-haiku-5-5"
    result = {
        "answer": response.get("status") == "answered",
        "provider": response.get("provider") == provider and response.get("model") == model,
        "language": (len(re.findall(r"[\u0900-\u097f]", answer)) >= 20) == (locale == "hi"),
        "uncached": response.get("cached") is False,
    }
    if case in {"digilocker", "passport"}:
        result["general"] = response.get("answer_mode") == "general" and not sources and not re.search(r"\[\d+\]", answer)
        result["concept"] = bool({"chip", "चिप"} & words) if case == "passport" else (
            "document" in words and bool({"wallet", "platform", "cloud", "store", "प्लेटफ़ॉर्म", "मंच"} & words)
        )
        return result
    if case == "comparison":
        result["comparison"] = "digilocker" in words and ("airport" in q or "gate" in q) and bool({"document", "aadhaar", "register"} & words)
        result["source_panel"] = bool(sources) and not re.search(r"\[\d+\]", answer)
        return result
    result["authority"] = any(
        item.get("source_file") == "supplement:pib-2331200" and "2331200" in (item.get("url") or "")
        and item.get("verification_status") == "verified" for item in sources
    ) and "[1]" in answer
    result["no_stale_snapshot"] = "undated" not in q and "स्नैपशॉट" not in answer
    if case in {"international", "epassport", "delhi", "eligibility"}:
        result["scope"] = "2026" in q and "indian" in words and "passport" in words
        result["airlines"] = "air india" in q and "indigo" in q
        result["checks"] = "immigration" in q
    elif case == "immigration":
        result["checks"] = "immigration" in q and any(w in q for w in ("must", "required", "still", "not", "नहीं", "होगा", "होंगी", "ज़रूरी"))
    elif case == "after_trial":
        result["no_extension"] = "2026" in answer and (
            re.search(r"\b(no|not|cannot|can't)\b", q) is not None or "पुष्टि" in answer or "not" in q
        )
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("replay", type=Path, nargs="?")
    p.add_argument("--url")
    p.add_argument("--rounds", type=int, default=1, choices=(1, 2))
    p.add_argument("--provider", choices=("sarvam", "anthropic"))
    p.add_argument("--locale", choices=("en", "hi"))
    p.add_argument("--only", nargs="+", choices=[item[0] for item in CATALOG])
    p.add_argument("--inr", type=float, default=0)
    p.add_argument("--usd", type=float, default=0)
    args = p.parse_args()
    if bool(args.replay) == bool(args.url):
        p.error("Provide a private replay file or --url")
    rows = json.loads(args.replay.read_text()) if args.replay else deployed(args, CATALOG)
    groups = defaultdict(list)
    fails = []
    for row in rows:
        verdict = checks(row)
        missing = [key for key, ok in verdict.items() if not ok]
        groups[f"{row['provider']}:{row['locale']}"].append((not missing, row["seconds"]))
        if missing:
            fails.append([row["provider"], row["locale"], row["case"], missing])
    totals = {key: {"pass": sum(ok for ok, _ in values), "total": len(values),
                    "p50_seconds": round(median(t for _, t in values), 3),
                    "p95_seconds": sorted(t for _, t in values)[(95 * len(values) - 1) // 100]}
              for key, values in groups.items()}
    print(json.dumps({"lanes": totals, "failures": fails}, ensure_ascii=False))
    raise SystemExit(bool(fails))


if __name__ == "__main__":
    main()
