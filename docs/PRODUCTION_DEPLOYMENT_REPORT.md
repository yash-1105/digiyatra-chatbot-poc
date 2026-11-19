# Production deployment report

Date: 2026-11-19 (Asia/Kolkata)

**Status: DEPLOYED AS ACCESS-RESTRICTED STAGING; ADMINISTRATOR PASSWORD ENTRY AND FINAL ADMIN VERIFICATION PENDING.**

The public GitHub repository, Railway backend/PostgreSQL and Vercel frontend exist. Actual live Sarvam calls, citations, feedback, staging access denial and responsive browser rendering have been tested. This is not a declaration of full production readiness: the owner must create the administrator through the hidden interactive password prompt before authenticated dashboard/cookie/logout checks can be completed. Knowledge content-owner sign-off remains pending.

## Live URLs and resources

| Component | URL / identity |
|---|---|
| GitHub | https://github.com/yash-1105/digiyatra-chatbot-poc — **PUBLIC**, verified through GitHub CLI |
| Frontend | https://digiyatra-chatbot-poc.vercel.app — access-restricted |
| Backend | https://backend-production-ab8a175f.up.railway.app — access-restricted except health probes |
| Backend health | https://backend-production-ab8a175f.up.railway.app/api/v1/health |
| Railway project | https://railway.com/project/d3e6f900-46b4-401b-a165-c5b0aba6718a |
| Railway backend service | `backend`, ID `9d1eae9f-706a-4617-845e-8a4d7b257818` |
| Railway PostgreSQL service | `Postgres`, ID `46a36660-0cf7-4566-9477-7993cf507400` |
| Railway environment | `production`, ID `5ff97f70-d9b6-4e31-9513-75ae59a9eda6` |
| Vercel project | `digiyatra-chatbot-poc`, ID `prj_YVLqq1gMcMF2jlt2n8SGvmvicvFS` |

## Architecture and deployment

```text
Authorized reviewer over HTTPS
  -> Vercel Next.js 15.5.29, Node 24.x
     -> whole-site staging access challenge and secure staging cookie
     -> existing same-origin /api/v1/* rewrite
  -> Railway FastAPI (existing Dockerfile, non-root, 1 replica / 1 worker)
     -> private Railway PostgreSQL: administrators, hashed sessions, anonymous analytics
     -> ephemeral LanceDB: rebuilt from private approved-for-retrieval corpus
     -> Sarvam API, sarvam-105b only for generated responses
```

The existing startup script ran Alembic migration `0001_initial`, built 119 lexical chunks from 26 approved-for-retrieval documents, and started Uvicorn on Railway's injected port 8080. PostgreSQL is a new service on private networking. No local analytics database, local admin hash or session store was transferred. LanceDB is derived from the private corpus and needs no persistent volume. An authenticated `ensure-index` run subsequently reported `Index OK: 119 chunks ... (no rebuild)`.

Railway initially selected Railpack despite the transferred configuration. The service now explicitly sets `RAILWAY_DOCKERFILE_PATH=backend/Dockerfile` and the matching Dockerfile path, startup command, health-check path, timeout, replica count and retry count in service settings. The existing Dockerfile and startup sequence are retained. The Docker context allow-list now includes its configuration and parent directories. Runtime ownership covers `/app` and `/data`, so the non-root user can read privately packaged files. The successful Railway build used the pinned runtime lockfile and existing Dockerfile.

## Security and publication

- Public source and frontend publication were explicitly approved by the owner. The exact initial staged set was scanned before publishing. The only Sarvam-key-shaped source string was the explicitly synthetic test key; example database URLs were reviewed as placeholders. No actual credentials were found in those checks.
- Git tracks no `knowledge/` files and no credential-bearing environment files. The retrieval corpus, raw documents, review artifacts, manifest, inventory, evaluation report, reference screenshot, databases, logs, caches, virtual environments, transfer archives, SSH private key and local deployment metadata remain excluded. Only example environment configurations are published.
- Retrieval approval is POC curation, not public redistribution permission. The private corpus contains 119 chunks from 26 documents, with a matching SHA-256. Content-owner sign-off remains **PENDING**. The international-trial draft remains excluded; no ingestion or corpus modification occurred.
- Railway received a separate authenticated private upload of `.cache/railway-context`. It contains 61 allow-listed runtime/build/corpus files, with a local SHA-256 inventory. It was not published on GitHub or in a public container registry. GitHub-only backend deployment must not be enabled while the corpus remains private.
- Both frontend and direct backend enforce a temporary whole-site staging credential. Production fails closed if it is absent. A successful browser challenge establishes an HttpOnly, Secure, SameSite=Strict staging cookie to support browser API requests. Backend health is the sole unauthenticated application exception, and exposes readiness metadata without credentials or document text. Vercel SSO protects preview and generated production deployment URLs as an additional platform control; authorized automation uses a private bypass credential.
- Staging credentials and the automation bypass are local ignored files with owner-only access. Neither value is recorded here. Authorized local operators can inspect `.cache/staging-access.json` privately to obtain the reviewer login; do not paste it into chat or commit it. Rotating the shared staging credential invalidates derived staging cookies.
- `SARVAM_API_KEY` is present only in Railway backend variables and successfully authenticates real `sarvam-105b` requests. Its value was not printed, committed, copied to frontend variables or written into this report. Revocation/rotation of the earlier exposed key remains an owner responsibility; successful API authentication alone cannot prove revocation.
- Production admin origins are restricted to `https://digiyatra-chatbot-poc.vercel.app`. The production origin check was hardened against Host/forwarded-host bypass. Production cookies are Secure, HttpOnly for the admin session, and SameSite=Strict. Live authenticated admin-cookie verification remains pending the administrator password.
- Frontend variables use the backend URL server-side, API mode, same-origin API base by default, and a 120000 ms chat timeout. Development mocks are disabled. The staging secret is absent from local client JavaScript checks. No frontend design component or stylesheet was changed. Chat and feedback requests now include same-origin credentials so staging authorization works in browsers.
- Dependency fixes pin FastAPI 0.136.0, Starlette 1.3.1 and annotated-doc 0.0.7, and override PostCSS to 8.5.33. Preflight runtime and frontend dependency audits reported no known vulnerabilities. These results are time-specific, not a guarantee against future advisories.

## Observed verification

| Check | Observed result |
|---|---|
| Backend offline tests after staging-cookie fix | **196 passed**, 15 live tests deselected |
| Backend Ruff and dependency consistency | Passed during preflight; Ruff passes after staging changes |
| Frontend production build, types and lint | Passed locally and on Vercel |
| Docker build on Railway | Passed using `backend/Dockerfile` |
| PostgreSQL migrations | Startup log confirms `PostgresqlImpl` and `0001_initial`; DB query confirms revision |
| Fresh LanceDB initialization | Startup log confirms 119 chunks from 26 documents |
| Existing index initialization | `ensure-index` reports no rebuild needed |
| Backend and Vercel-proxied health | HTTP 200, `status: ok`, index loaded, `sarvam-105b`, database migrated and primary |
| Anonymous frontend / backend access | HTTP 401; authorized portal request returns 200 |
| Logged-out admin dashboard | Redirects to `/admin/login` |
| Admin analytics without admin session | HTTP 401 `not_authenticated` |
| Forged cross-origin login | HTTP 403 even with matching forged forwarded-host |
| Production API documentation | HTTP 404 when staging-authorized |
| Real question: “Is Digi Yatra mandatory?” | HTTP 200 `answered`, model `sarvam-105b`, source `general_01_introduction.md`; 1.33 seconds in final API smoke test |
| Real registration question | HTTP 200 `answered`, model `sarvam-105b`, multiple source files; 1.01 seconds in final API smoke test |
| Injection / system-prompt extraction | HTTP 200 `refused`, no generative model reported |
| Off-topic weather question | HTTP 200 `out_of_scope`, no generative model reported |
| Explicit Yes feedback | HTTP 204 |
| Repeated identical feedback | HTTP 204; DB had exactly two feedback rows for the two initial answered smoke questions |
| Request-size limit | HTTP 413 for a 17000-byte request |
| Throttling with changing forged forwarded headers | Passed: the final 21-request greeting probe returned 10 HTTP 200 and 11 HTTP 429 responses, after earlier smoke requests consumed part of the 20/60s allowance |
| Staging cookie security | Live response confirms HttpOnly, Secure and SameSite=Strict; no internal client-IP signature in the response |
| HTTPS headers | HSTS, nosniff, DENY framing, referrer policy and noindex observed on Vercel |
| Responsive browser layout | Desktop 1440px, tablet 820px and mobile 390px: HTTP 200, zero horizontal overflow, chat opens, no page errors |
| Visual design | Live desktop screenshot inspected: navy utility/header bands, blue navigation, hero/highlights, orange accents, bilingual headings, original section layout and floating assistant preserved |
| Analytics privacy schema | 25 columns inspected across analytics tables; no chat text or passenger-identifier columns |
| Browser chat submission and Yes feedback | Passed on the live widget: real `sarvam-105b` answer, source list expanded, confirmation displayed |
| Administrator account | Last inspected count: zero; owner password entry pending |
| Authenticated admin dashboard, session-cookie forwarding, logout CSRF and replay | Pending owner interactive setup and verification helper |
| Analytics dashboard totals increment after feedback | Pending authenticated verification; underlying PostgreSQL interaction and feedback inserts observed |

Final API smoke checks after deployment fixes: **16/16 passed**. Browser testing subsequently found that the initial Basic-only staging gate did not authorize browser chat POSTs reliably. The shared chat/feedback HTTP client explicitly omitted all credentials, so it was changed to same-origin credentials. A secure staging cookie was added with a backend regression test and redeployed; the real browser widget subsequently returned a cited Sarvam answer and accepted Yes feedback. The final rate-limit probe used valid greetings and confirmed HTTP 429 even when supplied forwarded headers changed.

Live smoke and rate-limit tests intentionally created anonymous verification interactions in the new production database, including greeting-only interactions without LLM calls for throttling checks. No passenger information was supplied; text is not stored in analytics. The standard synthetic-database E2E suites were not pointed at production.

## Railway cost settings

The owner acknowledged the existing $10 hard limit and explicitly authorized deployment under their existing settings, instructing that spending limits must not be checked or changed. **No spending-limit checks or modifications were performed in this deployment run.** One backend replica and one PostgreSQL service were provisioned; no Railway Agent usage or paid Vercel plan upgrade was requested. No guarantee of a particular monthly bill is made.

## Essential remaining owner action

In the owner's own Mac Terminal, run:

```sh
/Users/yashsingh/Desktop/digiyatra-complete/.cache/finish-admin-setup.sh
```

This private helper uses the registered project-local SSH key to run the existing `python -m app.cli create-admin --email admin@gmail.com` command against the deployed backend. It prompts twice without echo, then runs a local verification helper that prompts once more for the same password. The password remains in memory; the verification helper checks login, session cookies, CSRF rejection, authenticated analytics, resolved-count increments, duplicate-feedback idempotency, logout/replay and the browser dashboard. Only sanitized results are written to `.cache/admin-verification-results.json`. The local SSH key is ignored and must remain private. Do not paste the administrator password into chat.

After this action, inspect the sanitized results, resolve any failure, update this report, and push the report update. Until then, the deployed app is staging with incomplete administrator verification.

## Known limitations and operations

- Content-owner sign-off is pending; retain whole-site staging restrictions. No unrestricted public launch is authorized.
- Retrieval and sentence grounding are lexical, not neural embeddings or semantic entailment. Subtle unsupported paraphrases remain possible.
- Rate limiting, login throttling and conversation memory are in-process. One replica/worker is configured; these states reset on restart.
- Proxy-hop assumptions failed live spoofing checks. Added a separate server-only `PROXY_SHARED_SECRET`: Vercel middleware signs its platform-provided client IP, and the backend accepts that identity only with a valid HMAC. Unsigned direct requests use their network peer. Header-spoofing regression tests and live throttling with changing supplied forwarded headers pass. No raw IP addresses or signing secret are published.
- Railway CLI warns that legacy `railway.toml` configuration is supported only until 2026-12-01. Explicit service settings are applied; deployment configuration should be migrated before that date. No application rewrite is needed.
- Backend auto-deployment from the public GitHub checkout cannot work without the privately supplied corpus. Refresh, hash-check and upload the private build context after backend/corpus changes.
- Screenshots and private verification artifacts are under `.cache/`; none are published. Hindi body answers, load capacity and disaster-recovery restoration were not validated in this run.

References: [Railway custom Dockerfile path](https://docs.railway.com/builds/dockerfiles), [Vercel Deployment Protection](https://vercel.com/docs/deployment-protection), [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/).
