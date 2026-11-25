"""Expanded answer-quality matrix (Task 3): 90+ intents x {sarvam, anthropic, novita} x {en, hi, hinglish}.

Offline (default, no network, no keys):
    PYTHONPATH=. .venv/bin/python -m evaluation.expanded --out ../.cache/eval/expanded-offline.json
  Runs the REAL chat pipeline in-process with deterministic *grounded mock* providers (they echo the
  first evidence sentence). It validates routing, retrieval/evidence selection, follow-up resolution,
  provider/language switching, video/link provenance, refusals and redaction. It does NOT measure
  model wording quality; claims_any/forbidden and Hindi answer language are checked only live.

Live (after deployment; signed synthetic route keeps analytics clean; spending caps enforced):
    PROXY_SHARED_SECRET=... PYTHONPATH=. .venv/bin/python -m evaluation.expanded --live \\
        --url https://digiyatra-chatbot-poc.vercel.app --inr 900 --usd 20 [--provider novita] [--only id ...]
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import tempfile
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

CASES = json.loads(Path(__file__).with_name("expanded_cases.json").read_text())["cases"]
PROVIDERS = ("sarvam", "anthropic", "novita")
LANES = ("en", "hi", "hinglish")
OFFICIAL_VIDEOS = {  # verified via oEmbed against @DigiYatraFoundation (2026-11-25); metadata only
    "-nlJBCwg0nM": "Enrol on the Digi Yatra App in 3 Simple Steps | Seamless Airport Travel Experience",
    "y6xTGrpfAGs": "Enrol on the Digi Yatra App using Aadhaar for a hassle-free airport journey",
    "7z7iLNSkFg4": "Enrol on the Digi Yatra App using DigiLocker | Seamless Airport Travel in Minutes",
    "j2lw7LljME0": "HOW TO ADD A DEPENDENT/MINOR | DIGI YATRA MOBILE APP",
    "apjRDn3pkZ4": "DIGI YATRA MOBILE APP  |  HOW TO DELETE CREDENTIAL",
    "jdb1Ph-QH9g": "How to Smart Share on Digi Yatra App",
    "Wlc6iqgwQDU": "SELF-SOVEREIGN IDENTITY | DATA SAFETY WITH DIGI YATRA",
}
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LINK = re.compile(r"https://(?:www\.youtube\.com|youtu\.be|x\.com|twitter\.com)/[^\s)”\"<>]+")


def lane_locale(lane: str) -> str:
    return "hi" if lane == "hi" else "en"


def question(case: dict, lane: str) -> str:
    return case[lane]


# --------------------------------------------------------------------------- checks
def check(case: dict, lane: str, resp: dict, *, live: bool, verified_links: set[str]) -> dict[str, bool]:
    e = case["expect"]
    answer = resp.get("answer", "")
    sources = resp.get("sources", [])
    files = {s.get("source_file", "") for s in sources}
    r: dict[str, bool] = {"status": resp.get("status") in e["status"]}
    if "sources_any" in e and resp.get("status") == "answered":
        r["evidence"] = any(f in files or any(f.startswith(x) for x in e["sources_any"] if x.endswith(":"))
                            for f in e["sources_any"]) or bool(files & set(e["sources_any"]))
    links = set(LINK.findall(answer)) | {s["url"] for s in sources if s.get("url") and LINK.match(s["url"])}
    r["links_verified"] = all(link.rstrip(".,") in verified_links for link in links)
    video = e.get("video")
    offered = {s["url"].split("v=")[1][:11] for s in sources if s.get("source_type") == "video" and "v=" in (s.get("url") or "")}
    if isinstance(video, list):
        r["video"] = bool(offered & set(video)) or any(v in answer for v in video)
    elif video == "none_metadata":
        r["video"] = not offered
    elif video == "no_timestamp":
        r["video"] = "&t=" not in answer and not any(s.get("timestamp_s") for s in sources)
    if e.get("pii_redacted"):
        r["pii_redacted"] = resp.get("pii_redacted") is True and "8765" not in (resp.get("redacted_message") or "")
    if lane == "hi" and resp.get("status") != "answered":
        r["hindi_fallback"] = len(DEVANAGARI.findall(answer)) >= 10
    if live:
        low = answer.lower()
        if resp.get("status") == "answered" and lane == "hi":
            r["hindi_answer"] = len(DEVANAGARI.findall(answer)) >= 20
        if resp.get("status") == "answered" and e.get("claims_any"):
            r["claims"] = all(any(w.lower() in low for w in group) for group in e["claims_any"])
        if e.get("forbidden"):
            r["no_forbidden_claim"] = not any(f.lower() in low for f in e["forbidden"])
    return r


# --------------------------------------------------------------------------- offline stack
def _offline_app(tmp: Path):
    import httpx

    from app.clients.anthropic import AnthropicChatClient
    from app.clients.novita import NovitaChatClient
    from app.clients.sarvam import SarvamChatClient
    from app.config import PROJECT_DIR, Settings
    from app.db.migrate import upgrade
    from app.db.models import OfficialRecord
    from app.main import create_app
    from app.rag.embeddings import LexicalEmbedder
    from app.rag.retriever import Retriever
    from app.rag.store import KnowledgeIndex
    from app.services.knowledge import SOURCES, Knowledge
    from app.sync import social as S
    from app.sync.publish import record_chunk
    from ingestion.corpus import load_corpus

    chunks, _ = load_corpus(PROJECT_DIR / "knowledge" / "deploy")
    now = datetime(2026, 11, 25)
    records = []
    for i, (vid, title) in enumerate(OFFICIAL_VIDEOS.items(), 1):
        records.append(OfficialRecord(
            id=50_000 + i, source_id="yt-channel-digiyatrafoundation", record_key=f"v{i}", version=1, content_hash=f"{i:064d}",
            status="verified", record_type="video", title=title, category="YouTube video", question=None,
            body=f'Official Digi Yatra Foundation YouTube video: "{title}".', url=S.watch_url(vid), anchor=None,
            organization="Digi Yatra Foundation", language="en", authority="official_social", topic="video_resources",
            risk="low", published_on=None, updated_on=None, effective_from=None, expires_on=None, extracted_at=now,
            review_reason=None, source_kind="video", platform="youtube", external_id=vid,
            account_id=S.YOUTUBE_CHANNEL_ID, account_name="Digi Yatra Foundation", start_s=None, media={}))
    for i, acc in enumerate([a for a in S.ACCOUNTS.values() if S.ingestible(a)], 1):
        kind = "official government account" if acc.status == "verified_government" else "official channel"
        records.append(OfficialRecord(
            id=51_000 + i, source_id="official-accounts", record_key=f"a{i}", version=1, content_hash=f"{100 + i:064d}",
            status="verified", record_type="account_profile", title=f"Official {acc.platform} — {acc.name}",
            category="Official channels", question=None,
            body=f"{acc.name} ({acc.handle}) is the {kind} of {acc.owner} on {acc.platform}: {acc.profile_url}. "
                 "Follow it for official Digi Yatra announcements and updates.",
            url=acc.profile_url, anchor=None, organization=acc.owner, language="en", authority="official_social",
            topic="official_channels", risk="low", published_on=None, updated_on=None, effective_from=None,
            expires_on=None, extracted_at=now, review_reason=None, source_kind="account_profile",
            platform=acc.platform, external_id=acc.account_id, account_id=acc.account_id, account_name=acc.name,
            start_s=None, media={}))
    index = KnowledgeIndex(tmp / "index")
    index.build(list(chunks) + [record_chunk(r, i) for i, r in enumerate(records)], LexicalEmbedder())
    retriever = Retriever(index, index.load_embedder())
    settings = Settings(_env_file=None, SARVAM_API_KEY="sk_test_offline_eval", ANTHROPIC_API_KEY="offline-eval",
                        NOVITA_API_KEY="offline-eval", database_url=f"sqlite:///{tmp / 'eval-synthetic.db'}",
                        index_dir=tmp / "index", rate_limit_requests=100_000, anthropic_rate_limit_requests=60,
                        novita_rate_limit_requests=60, knowledge_enrichment_enabled=True,
                        conversational_answers_enabled=True)
    upgrade(settings.database_url)
    calls = defaultdict(int)

    def grounded(prompt: str) -> str:
        m = re.search(r"\[S1\][^\n]*\n<<<\n(.+?)\n>>>", prompt, re.S)
        if not m:
            return "INSUFFICIENT_EVIDENCE"
        body = re.sub(r"^Q:.*?\nA:\s*", "", m.group(1), flags=re.S)
        return re.split(r"(?<=[.!?।])\s", body.strip())[0] + " [S1]"

    def sarvam(request):
        calls["sarvam"] += 1
        body = json.loads(request.content)
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "model": "sarvam-105b",
                                         "choices": [{"index": 0, "finish_reason": "stop", "message": {
                                             "role": "assistant", "content": grounded(body["messages"][-1]["content"])}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}})

    def anthropic(request):
        calls["anthropic"] += 1
        body = json.loads(request.content)
        return httpx.Response(200, json={"model": "claude-haiku-5-5", "stop_reason": "end_turn",
                                         "usage": {"input_tokens": 10, "output_tokens": 5},
                                         "content": [{"type": "text", "text": grounded(body["messages"][-1]["content"])}]})

    def novita(request):
        calls["novita"] += 1
        body = json.loads(request.content)
        return httpx.Response(200, json={"model": "qwen/qwen3.8-flash", "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                                         "choices": [{"message": {"role": "assistant", "content": grounded(
                                             body["messages"][-1]["content"])}, "finish_reason": "stop"}]})

    app = create_app(settings, retriever=retriever,
                     llm=SarvamChatClient("sk_test_offline_eval", transport=httpx.MockTransport(sarvam), backoff_base_s=0.0, max_retries=0))
    app.state.providers["anthropic"] = AnthropicChatClient("offline", transport=httpx.MockTransport(anthropic))
    app.state.providers["novita"] = NovitaChatClient("offline", transport=httpx.MockTransport(novita))
    from app.security.rate_limit import RateLimiter

    # The harness sends ~800 requests in minutes; production per-provider limits are tested elsewhere.
    app.state.anthropic_rate_limiter = app.state.novita_rate_limiter = RateLimiter(10**6, 60)
    # The reviewed PIB supplements, seeded through the normal verification + review path.
    knowledge = Knowledge(app.state.db)
    for sid in ("pib-2331200", "pib-2331200-domestic"):
        policy = SOURCES[sid]
        html = "<p>Posted On: 01 NOV 2026</p>" + "".join(f"<p>{' '.join(b)}</p>" for b in policy.checks)
        knowledge.review(knowledge.verify(sid, snapshot=html), "published", "offline-evaluation")
    verified = {S.watch_url(v) for v in OFFICIAL_VIDEOS} | {a.profile_url for a in S.ACCOUNTS.values() if S.ingestible(a)}
    verified |= {u.rstrip(").,") for c in chunks for u in re.findall(r"https://\S+", c["text"] + " " + " ".join(c.get("urls") or []))}
    return app, calls, verified


def offline(args) -> list[dict]:
    from fastapi.testclient import TestClient

    rows = []
    with tempfile.TemporaryDirectory(prefix="expanded-eval-") as tmp:
        app, calls, verified = _offline_app(Path(tmp))
        with TestClient(app) as client:
            for case in [c for c in CASES if not args.only or c["id"] in args.only]:
                for pi, provider in enumerate(PROVIDERS if not args.provider else (args.provider,)):
                    for lane in LANES:
                        cid = "eval-" + uuid.uuid4().hex[:20]
                        prior_provider = PROVIDERS[(pi + 1) % 3] if case.get("switch") == "provider" else provider
                        prior_locale = "en" if case.get("switch") == "language" else lane_locale(lane)
                        for turn in case.get("turns", []):
                            client.post("/api/v1/chat", json={"message": turn, "conversation_id": cid,
                                                              "provider": prior_provider, "locale": prior_locale})
                        locale = "hi" if case.get("switch") == "language" else lane_locale(lane)
                        before = dict(calls)
                        start = time.perf_counter()
                        r = client.post("/api/v1/chat", json={"message": question(case, lane), "conversation_id": cid,
                                                              "provider": provider, "locale": locale})
                        resp = r.json() if r.status_code == 200 else {"status": f"http_{r.status_code}"}
                        verdict = check(case, lane, resp, live=False, verified_links=verified)
                        called = {p for p in PROVIDERS if calls[p] > before.get(p, 0)}
                        verdict["provider_routing"] = called <= {provider} and resp.get("provider", provider) == provider
                        rows.append({"case": case["id"], "category": case["category"], "provider": provider, "lane": lane,
                                     "critical": bool(case.get("critical")), "seconds": time.perf_counter() - start,
                                     "status": resp.get("status"), "checks": verdict})
    return rows


def live(args) -> list[dict]:
    import httpx

    secret = os.environ.get("PROXY_SHARED_SECRET", "").encode()
    if not secret:
        raise SystemExit("PROXY_SHARED_SECRET is required for analytics-isolated (synthetic) requests")
    cases = [c for c in CASES if not args.only or c["id"] in args.only]
    providers = (args.provider,) if args.provider else PROVIDERS
    calls = sum(1 + len(c.get("turns", [])) for c in cases) * len(providers) * len(LANES)
    # Conservative retry-inclusive caps (two generations + citation repair per request at list prices).
    if args.inr < calls * 3 or args.usd < calls * 0.06:
        raise SystemExit(f"Refusing: {calls} requests exceed the --inr/--usd spending caps")
    verified = set(OFFICIAL_VIDEOS and {f"https://www.youtube.com/watch?v={v}" for v in OFFICIAL_VIDEOS})
    rows, last = [], defaultdict(float)
    with httpx.Client(timeout=90) as client:
        def post(payload):
            gap = {"anthropic": 6.5, "novita": 6.5}.get(payload["provider"], 3.4)
            time.sleep(max(0.0, last[payload["provider"]] + gap - time.monotonic()))
            last[payload["provider"]] = time.monotonic()
            body = json.dumps(payload).encode()
            stamp = str(int(time.time()))
            sig = hmac.new(secret, f"evaluation:v1\n{stamp}\n{hashlib.sha256(body).hexdigest()}".encode(), "sha256").hexdigest()
            res = client.post(args.url.rstrip("/") + "/api/v1/chat", content=body,
                              headers={"content-type": "application/json", "x-dy-evaluation": f"{stamp}.{sig}"})
            if res.is_success and res.headers.get("x-dy-evaluation") != "synthetic":
                raise SystemExit("Synthetic isolation was not acknowledged; stopping")
            return res
        for case in cases:
            for pi, provider in enumerate(providers):
                for lane in LANES:
                    cid = "eval-live-" + uuid.uuid4().hex[:20]
                    for turn in case.get("turns", []):
                        post({"message": turn, "conversation_id": cid, "locale": "en" if case.get("switch") == "language" else lane_locale(lane),
                              "provider": providers[(pi + 1) % len(providers)] if case.get("switch") == "provider" else provider})
                    start = time.monotonic()
                    res = post({"message": question(case, lane), "conversation_id": cid, "provider": provider,
                                "locale": "hi" if case.get("switch") == "language" else lane_locale(lane)})
                    resp = res.json() if res.is_success else {"status": f"http_{res.status_code}"}
                    verdict = check(case, lane, resp, live=True, verified_links=verified | {
                        s["url"] for s in resp.get("sources", []) if s.get("url")})
                    verdict["provider_routing"] = resp.get("provider") == provider or resp.get("cached") is True
                    rows.append({"case": case["id"], "category": case["category"], "provider": provider, "lane": lane,
                                 "critical": bool(case.get("critical")), "seconds": time.monotonic() - start,
                                 "status": resp.get("status"), "checks": verdict})
    return rows


def summarise(rows: list[dict]) -> dict:
    lanes = defaultdict(list)
    failures = []
    for row in rows:
        ok = all(row["checks"].values())
        lanes[f"{row['provider']}:{row['lane']}"].append((ok, row["seconds"], row["status"]))
        if not ok:
            failures.append({"case": row["case"], "provider": row["provider"], "lane": row["lane"],
                             "critical": row["critical"], "failed": [k for k, v in row["checks"].items() if not v],
                             "status": row["status"]})
    out = {}
    for key, values in sorted(lanes.items()):
        times = sorted(t for _, t, _ in values)
        refusals = sum(1 for _, _, st in values if st in ("insufficient_evidence", "out_of_scope"))
        out[key] = {"pass": sum(ok for ok, _, _ in values), "total": len(values),
                    "pass_rate": round(sum(ok for ok, _, _ in values) / len(values), 4),
                    "non_answer_statuses": refusals,
                    "p50_s": round(median(times), 3), "p95_s": round(times[(95 * len(times) - 1) // 100], 3)}
    total = sum(v["total"] for v in out.values())
    passed = sum(v["pass"] for v in out.values())
    return {"intents": len({r["case"] for r in rows}), "requests": total, "pass": passed,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "critical_failures": [f for f in failures if f["critical"]], "lanes": out, "failures": failures}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--live", action="store_true")
    p.add_argument("--url")
    p.add_argument("--provider", choices=PROVIDERS)
    p.add_argument("--only", nargs="+")
    p.add_argument("--inr", type=float, default=0)
    p.add_argument("--usd", type=float, default=0)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.live and not args.url:
        p.error("--live requires --url")
    rows = live(args) if args.live else offline(args)
    summary = {"mode": "live" if args.live else "offline-mocked-providers", **summarise(rows)}
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1))
        os.chmod(args.out, 0o600)
    print(json.dumps({k: v for k, v in summary.items() if k != "failures"}, ensure_ascii=False, indent=1))
    if summary["failures"]:
        print(json.dumps(summary["failures"][:40], ensure_ascii=False))
    raise SystemExit(1 if summary["critical_failures"] or summary["pass_rate"] < 0.95 else 0)


if __name__ == "__main__":
    main()
