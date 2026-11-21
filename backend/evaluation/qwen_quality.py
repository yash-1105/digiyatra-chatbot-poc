"""Evaluate the nine content regressions without printing private answers or evidence."""

import argparse
import json
import re
from pathlib import Path

from app.rag.query import normalize_query
from app.services.answering import qwen_scope_score

FAILED_BASELINE = {
    ("en", "basics"), ("hi", "basics"), ("en", "airports"), ("hi", "airports"),
    ("en", "minors"), ("hi", "minors"), ("en", "offline"),
    ("en", "privacy_retention"), ("hi", "passport_definition"),
}


def failed_assertions(row: dict) -> list[str]:
    reply = row.get("reply", {})
    answer = reply.get("answer", "")
    q = normalize_query(answer)
    sources = reply.get("sources", [])
    files = {s.get("source_file") for s in sources}
    inline = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    checks = {
        "answered": reply.get("status") == "answered",
        "correct_provider_and_language": reply.get("provider") == "novita" and reply.get("locale") == row["locale"],
        "response_language": bool(re.search(r"[\u0900-\u097f]", answer)) == (row["locale"] == "hi"),
        "citation_integrity": inline <= {s["id"] for s in sources},
    }
    case = row["id"]
    if case == "basics":
        checks.update(
            defines_purpose=bool(re.search(r"face|facial|biometric|चेहरे|चेहरा", q))
            and bool(re.search(r"air travel|airport|flight|हवाई (?:यात्रा|travel)", q)),
            approved_source=bool({"general_01_introduction.md", "general_02_how_it_works.md"} & files),
            no_misleading_details=not bool(re.search(r"health data|health checks?|स्वास्थ्य", q)),
        )
    elif case == "airports":
        checks.update(dated_count="2026-11-01" in q and "39" in q, authority="supplement:pib-2331200-domestic" in files,
                      no_invented_directory=not re.search(r"\b24\s+(?:current|operational)\b|\([A-Z]{3}\)", answer))
    elif case == "minors":
        checks.update(under18_consent_aadhaar_under5_manual=qwen_scope_score("children", answer) == 5,
                      sourced=bool(files))
    elif case == "offline":
        checks.update(three_stages="otp" in q and "boarding pass" in q and bool(re.search(r"facial|face|biometric", q)),
                      scoped_uncertainty="does not specify" in q and "internet" in q, sourced=bool(files))
    elif case == "privacy_retention":
        checks.update(deadline=bool(re.search(r"(?:within|up to|no more than).{0,15}24\s+hours", q)) and "scheduled departure" in q,
                      not_exact_duration=not re.search(r"\b(?:for|at least|exactly)\s+24\s+hours", q),
                      storage_distinguished=bool(re.search(r"mobile device|phone|wallet", q)) and "airport" in q,
                      sourced="airport_data_sharing.md" in files or "linkedin_privacy_security.md" in files)
    elif case == "passport_definition":
        checks.update(chip_and_purpose=bool(re.search(r"chip|चिप", q)) and bool(re.search(r"identity|पहचान", q)),
                      stable_definition=reply.get("answer_mode") == "general" and not files and not inline)
    return [name for name, passed in checks.items() if not passed]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.replay.read_text().splitlines() if line.startswith("{")]
    actual = {(r.get("lane"), r.get("id")): r for r in rows}
    results = {f"{lane}:{case}": failed_assertions(actual[lane, case]) if (lane, case) in actual else ["missing"]
               for lane, case in sorted(FAILED_BASELINE)}
    print(json.dumps(results, indent=2))
    raise SystemExit(any(results.values()))


if __name__ == "__main__":
    main()
