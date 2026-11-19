"""Real-provider bilingual benchmark. Credentials stay in memory; all analytics are synthetic.

Run from backend: .venv/bin/python evaluation/bilingual.py --label optimized
Use --baseline-prompt /private/path/to/prior-prompt.txt for a full-context comparison.
The baseline file is captured from the prior release, never downloaded or executed.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import PROJECT_DIR, Settings
from app.db.migrate import upgrade
from app.db.models import AIUsage
from app.main import create_app
from app.rag.query import evidence_tokens
from app.services import chat_service


def checks(case, response):
    answer = response.get("answer", "")
    sources = response.get("sources", [])
    meaningful = answer.split(":", 1)[-1] if response.get("answer_mode") == "general" else answer
    hindi = len(re.findall(r"[\u0900-\u097f]", meaningful))
    english = len(re.findall(r"[a-zA-Z]", meaningful))
    return dict(
        mode=response.get("answer_mode") == case["mode"],
        language=(hindi > 12 if case["locale"] == "hi" else english > 20 and hindi == 0),
        concepts=all(evidence_tokens(term) <= evidence_tokens(answer) for term in case.get("concepts", [])),
        citations=(bool(sources) and bool(re.search(r"\[\d+\]", answer)))
        if case["mode"] == "knowledge"
        else not sources,
        steps=not case.get("steps") or len(re.findall(r"(?m)^\s*\d+[.)]\s", answer)) >= case.get("min_steps", 2),
        relevant=not case.get("sources") or bool({s["source_file"] for s in sources} & set(case["sources"])),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--baseline-prompt", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    cli = shutil.which("railway")
    if not cli:
        raise SystemExit("Railway CLI required")
    p = subprocess.run(  # noqa: S603 - resolved authenticated CLI, fixed arguments
        [cli, "variable", "list", "--service", "backend", "--json"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    variables = json.loads(p.stdout)
    cases = json.loads(Path(__file__).with_name("bilingual_questions.json").read_text())
    if args.limit:
        cases = cases[: args.limit]
    folder = PROJECT_DIR / ".cache" / "bilingual-eval"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = folder / (args.label + ".json")
    settings = Settings(
        _env_file=None,
        SARVAM_API_KEY=variables["SARVAM_API_KEY"],
        ANTHROPIC_API_KEY=variables["ANTHROPIC_API_KEY"],
        embedding_provider="lexical",
        index_dir=PROJECT_DIR / ".cache/conversation-eval/index",
        database_url="sqlite:///" + str(folder / (args.label + "-synthetic.db")),
        faq_cache_ttl_s=0,
        anthropic_prompt_cache=not bool(args.baseline_prompt),
        rate_limit_requests=10000,
        anthropic_rate_limit_requests=60,
    )
    # The benchmark's private instance can exceed production request rate, never production tokens.
    if args.baseline_prompt:
        settings = settings.model_copy(
            update=dict(
                context_top_k=5,
                context_token_budget=12000,
                history_token_budget=2000,
                prompt_token_budget=16000,
                sarvam_max_tokens=1200,
                anthropic_max_tokens=1200,
            )
        )
    upgrade(settings.database_url)
    prompt = args.baseline_prompt.read_text() if args.baseline_prompt else chat_service.SYSTEM_PROMPT
    rows = []
    with patch.object(chat_service, "SYSTEM_PROMPT", prompt), TestClient(create_app(settings)) as client:
        for provider in ("sarvam", "anthropic"):
            for case in cases:
                with client.app.state.db.session() as db:
                    previous = set(db.scalars(select(AIUsage.id)))
                start = time.monotonic()
                r = client.post(
                    "/api/v1/chat",
                    json=dict(
                        message=case["question"],
                        locale=case["locale"],
                        provider=provider,
                        conversation_id=f"eval-{args.label}-{provider}-" + case.get("group", case["id"]),
                    ),
                )
                response = r.json()
                with client.app.state.db.session() as db:
                    usage = [
                        dict(
                            provider=u.provider,
                            model=u.model,
                            input_tokens=u.input_tokens,
                            output_tokens=u.output_tokens,
                            cache_read_tokens=u.cache_read_tokens,
                            cache_write_tokens=u.cache_write_tokens,
                            estimated_usd=u.estimated_usd,
                            tokens_estimated=u.tokens_estimated,
                        )
                        for u in db.scalars(select(AIUsage))
                        if u.id not in previous
                    ]
                row = dict(
                    id=case["id"],
                    provider=provider,
                    locale=case["locale"],
                    question=case["question"],
                    http_status=r.status_code,
                    seconds=round(time.monotonic() - start, 3),
                    response=response,
                    usage=usage,
                    checks=checks(case, response),
                )
                rows.append(row)
                output.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
                output.chmod(0o600)
                print(json.dumps({k: row[k] for k in ("id", "provider", "http_status", "checks")}), flush=True)
    for provider in ("sarvam", "anthropic"):
        group = [r for r in rows if r["provider"] == provider]
        calls = [u for r in group for u in r["usage"]]
        print(
            json.dumps(
                dict(
                    provider=provider,
                    cases=len(group),
                    checks={k: sum(r["checks"][k] for r in group) for k in group[0]["checks"]},
                    input_tokens=sum(u["input_tokens"] for u in calls),
                    output_tokens=sum(u["output_tokens"] for u in calls),
                    estimated_usd=sum(u["estimated_usd"] for u in calls),
                )
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
