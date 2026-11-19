"""Real Sarvam evaluation against a synthetic local database, never production analytics.

Run from backend: .venv/bin/python evaluation/run.py --label before
Private answers are written under .cache, never to public docs or stdout.
Uses the existing Railway backend key in memory; does not alter any variables.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient

from app.cli import cmd_ensure_index
from app.config import PROJECT_DIR, Settings
from app.db.migrate import upgrade
from app.main import create_app


def score(case, response):
    answer = response.get("answer", "").lower()
    mode = response.get("answer_mode") or ("knowledge" if response.get("status") == "answered" else "insufficient")
    sources = {s["source_file"] for s in response.get("sources", [])}
    return {
        "mode": mode == case["mode"],
        "concepts": all(any(term.lower() in answer for term in group) for group in case.get("concepts", [])),
        "retrieval": not case.get("sources") or bool(sources & set(case["sources"])),
        "citations": bool(sources) and bool(re.search(r"\[\d+\]", answer)) if sources else mode != "knowledge",
        "instructions": not case.get("steps") or len(re.findall(r"(?m)^\s*\d+[.)]\s", answer)) >= 2,
        "concise": len(answer.split()) <= 220,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_name("questions.json").read_text())
    railway = shutil.which("railway")
    if not railway:
        raise SystemExit("Railway CLI unavailable")
    p = subprocess.run(  # noqa: S603 - resolved authenticated CLI; fixed arguments, no shell
        [railway, "variable", "list", "--service", "backend", "--json"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
    )
    if p.returncode:
        raise SystemExit("Unable to obtain evaluation credential privately")
    key = json.loads(p.stdout).get("SARVAM_API_KEY")
    if not key:
        raise SystemExit("Sarvam credential unavailable")
    folder = PROJECT_DIR / ".cache" / "conversation-eval"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    database = f"sqlite:///{folder / (args.label + '-synthetic.db')}"
    settings = Settings(
        _env_file=None,
        SARVAM_API_KEY=key,
        index_dir=folder / "index",
        embedding_provider="lexical",
        database_url=database,
        rate_limit_requests=10000,
        log_level="WARNING",
    )
    upgrade(database)
    cmd_ensure_index(settings)
    rows = []
    output = folder / (args.label + ".json")
    with TestClient(create_app(settings)) as client:
        print("Synthetic evaluation ready: " + args.label, flush=True)
        for case in cases:
            cid = f"eval-{args.label}-" + case.get("group", case["id"])
            start = time.monotonic()
            r = client.post("/api/v1/chat", json={"message": case["question"], "conversation_id": cid})
            response = r.json()
            row = {
                "id": case["id"],
                "question": case["question"],
                "http_status": r.status_code,
                "seconds": round(time.monotonic() - start, 2),
                "response": response,
                "checks": score(case, response),
            }
            rows.append(row)
            output.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
            output.chmod(0o600)
            print(
                json.dumps(
                    {
                        "id": case["id"],
                        "status": response.get("status"),
                        "mode": response.get("answer_mode"),
                        "checks": row["checks"],
                    }
                ),
                flush=True,
            )
    summary = {name: sum(row["checks"][name] for row in rows) for name in rows[0]["checks"]}
    print(json.dumps({"label": args.label, "cases": len(rows), "summary": summary}), flush=True)


if __name__ == "__main__":
    main()
