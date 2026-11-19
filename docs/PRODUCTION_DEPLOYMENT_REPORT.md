# Production deployment report

Date: 2026-11-19 (Asia/Kolkata)

**Status: PUBLIC PORTAL AND CHATBOT DEPLOYED; ADMINISTRATION REMAINS SESSION-PROTECTED.**

## Live deployment

| Component | URL / identity |
|---|---|
| Frontend | https://digiyatra-chatbot-poc.vercel.app |
| Administrator login | https://digiyatra-chatbot-poc.vercel.app/admin/login |
| Backend | https://backend-production-ab8a175f.up.railway.app |
| Public GitHub repository | https://github.com/yash-1105/digiyatra-chatbot-poc — PUBLIC |
| Railway project | https://railway.com/project/d3e6f900-46b4-401b-a165-c5b0aba6718a |
| Backend deployment | `f8a17f0b-70a5-425f-9860-ad3830bd5802`, SUCCESS |
| Frontend deployment | Existing Vercel frontend retained; no frontend runtime change required |

The authentication-fix sections below describe the earlier release. The latest conversational-quality deployment and its separate verification results are recorded at the end.

## Authentication fix

The native browser popup was caused by custom HTTP Basic gates in `frontend/src/middleware.ts` and `backend/app/main.py`. Both emitted `WWW-Authenticate` challenges before public content could load. Vercel SSO protection additionally covered generated production deployment URLs and previews.

Removed the global Basic/staging-cookie checks and their obsolete configuration. Disabled Vercel SSO deployment protection for this public project. Removed the staging credential variables from Vercel Production/Preview and Railway. Obsolete Vercel automation-bypass access was revoked; the platform reports zero bypass entries. No replacement Basic gate is present.

The current access policy is:

| Route / feature | Access |
|---|---|
| Homepage, information pages, navigation, FAQs, POC disclaimer | Public |
| Chat, conversational follow-ups, citations and Yes/No feedback | Public |
| `/admin/login` | Public login form |
| `/admin/dashboard` | Valid administrator session required |
| Admin session and analytics APIs | Valid administrator session required |
| Admin logout | Existing session revocation with CSRF checks; anonymous logout is idempotent |

The existing Argon2id password hashing, administrator identity, server-side sessions, Secure/HttpOnly/SameSite=Strict admin-cookie implementation, allowed-origin checks, logout CSRF protection and protected Next.js layout are preserved. The deployed `admin@gmail.com` password hash was compared privately before and after the change and is unchanged. No password was read or reset.

## Architecture and private inputs

```text
Anonymous browser -> Vercel Next.js 15.5.29 / Node 24.x
                     -> existing same-origin /api/v1/* rewrite
                     -> Railway FastAPI Docker service (1 replica, 1 worker)
                          -> private PostgreSQL
                          -> private-corpus-derived ephemeral LanceDB
                          -> Sarvam API: sarvam-105b only
```

Railway uses the existing Dockerfile and startup script: Alembic upgrade, automatic index initialization, then one Uvicorn worker. The current database uses migration `0001_initial`; the index contains 119 lexical chunks from 26 approved-for-retrieval documents. Startup/indexing remain idempotent. The new deployment reused the production PostgreSQL service and did not reset or replace any database.

The retrieval corpus, raw documents, review artifacts, approval manifest, reference screenshot, databases, logs, caches, transfer archives and credentials remain excluded from public GitHub. Corpus delivery continues through the separate authenticated private Railway build context in `.cache/railway-context`, with a SHA-256 inventory. The corpus was not edited or re-ingested. The international-trial draft remains excluded. Content-owner sign-off metadata remains pending; the owner's latest instructions explicitly authorize a public portal and chatbot, without authorizing public redistribution of the corpus files.

`SARVAM_API_KEY` remains only in Railway backend variables. The server-only `PROXY_SHARED_SECRET` remains configured in Vercel and Railway. Vercel signs its platform client IP, and the backend accepts that identity only with a valid HMAC; direct unsigned requests use their network peer. No API key, database URL, session token or proxy secret is exposed in browser code or this report.

## Actual live verification after the fix

| Check | Observed result |
|---|---|
| Fresh Playwright browser context, no cookies/credentials/bypass headers | Homepage HTTP 200 immediately; zero Basic challenges |
| Existing DGCA-style homepage and POC disclaimer | Visible; no layout/style changes |
| Anonymous real chat | HTTP 200 `answered`, model `sarvam-105b`, source citations returned |
| Anonymous conversational follow-up | HTTP 200 `answered`, real Sarvam response and citations |
| Browser source list | Expanded and visible |
| Anonymous Yes feedback | HTTP 204 |
| Anonymous No feedback | HTTP 204 |
| `/admin/login` | Existing email/password form visible without outer authentication |
| Anonymous `/admin/dashboard` | Redirects to `/admin/login` |
| Anonymous admin session/analytics, through Vercel and directly on Railway | HTTP 401 without `WWW-Authenticate` |
| Incorrect admin password | HTTP 401 `invalid_credentials`, no native browser challenge |
| Cross-origin admin login | HTTP 403 |
| Existing administrator session after redeploy | Accepted by the real session API |
| Authenticated browser admin navigation | Login page redirects to dashboard; dashboard renders and loads analytics |
| Analytics after a new answered question and Yes vote | Question and resolved totals each increase by one |
| Repeated identical feedback | Accepted without double-counting |
| Missing/wrong logout CSRF, or disallowed Origin | HTTP 403 |
| Browser Logout | Returns to the existing login form |
| Replaying the logged-out session | HTTP 401 |
| Existing administrator Argon2id hash | Unchanged; comparison performed without printing the hash |
| Private `/.env` and `/knowledge/deploy/chunks.jsonl`, both origins | HTTP 404 |
| Production `/api/docs` and `/api/openapi.json`, both origins | HTTP 404 |
| Public rate limiting with forged forwarding headers | 21 anonymous valid requests: 19 HTTP 200, then 2 HTTP 429; supplied X-Forwarded-For, platform-IP and signature headers did not evade the cap |
| Browser errors | None in the public browser test |

Public browser checks: **10/10 passed**. Post-deployment administrator preservation/session/browser checks: **11/11 passed**. Direct/proxied administrative and private-path checks: **14/14 passed**.

Password-login evidence is distinct from session verification: the owner's earlier private, getpass-based production run passed **15/15** checks, including successful password login, cookie flags, analytics and browser logout. This fix did not change that login implementation or the stored password hash. After redeployment, incorrect-password rejection and all session/dashboard/logout checks were repeated live. For the latter, a short-lived deployment-test session for the existing administrator was inserted over authenticated SSH using a random token sent through private stdin; it was revoked through normal logout. The owner's password was never requested, extracted or modified. The actual password-login exchange was not repeated by the agent after this fix.

Live tests added only anonymous test interactions/feedback and the revoked verification session. No passenger information was supplied. Analytics retain no chat text or passenger identifiers; the schema's 25 analytics columns were inspected during deployment.

## Local validation and source controls

- Backend: **196 passed**, 15 live tests deselected; Ruff passes.
- Added production public-access regression checks for anonymous chat/follow-ups/feedback, session-only admin APIs, and obsolete staging-cookie rejection.
- Existing authentication, CSRF, session expiry/revocation, analytics and signed-proxy tests continue to pass.
- Frontend: local and Vercel production builds, type checking and lint pass.
- No frontend visual component or stylesheet was changed.
- Prior dependency remediation remains: FastAPI 0.136.0, Starlette 1.3.1, annotated-doc 0.0.7 and PostCSS 8.5.33. Dependency audit results from deployment were clean; these are time-specific results.
- Source and staged changes are audited before push; actual generated deployment-secret values are checked without printing them. Private build inputs and local verification artifacts are not committed.

## Billing, operations and limitations

Railway billing settings and spending limits were neither checked nor changed. Existing services, databases and real administrator records were not deleted or reset. No paid Vercel plan upgrade was requested.

Retrieval and sentence grounding remain lexical rather than neural embeddings or semantic entailment. Rate limiting, login throttling and conversation memory are in-process, requiring one replica/worker and resetting on restart. PostgreSQL remains persistent; LanceDB is rebuilt from the private corpus after ephemeral disk replacement. The public repository intentionally cannot build the backend without the authorized private corpus input.

Railway's CLI warns that legacy `railway.toml` support ends on 2026-12-01; explicit service settings and the Dockerfile-path variable are applied. A configuration migration should be scheduled before that date. Hindi answer quality, load capacity and disaster-recovery restoration were not validated during this authentication fix.

Private screenshots and sanitized verification files are in `.cache/`; no administrator credentials, tokens or corpus files are published with this report.


## Conversational quality release — 2026-11-19

Implementation commits: `8e4898a` and `8fb6aa1`. Railway backend deployment: `f8a17f0b-70a5-425f-9860-ad3830bd5802` (SUCCESS). Public portal: https://digiyatra-chatbot-poc.vercel.app. Backend: https://backend-production-ab8a175f.up.railway.app.

The architecture, Sarvam-105B model, credentials, PostgreSQL schema, administrator account, DGCA-inspired design and approved private corpus are preserved. The corpus still has 119 chunks from 26 documents. Railway startup continues to run migrations and automatic index initialization. No billing settings, infrastructure resources, secrets or production account passwords were changed. Only the backend required deployment; the frontend already supports line breaks, numbered instructions and clickable URLs. Its sole source change is a browser acceptance-test adjustment for the intentionally cautious current-airport-list policy and the installed browser path.

Root causes, retrieval changes, explicit knowledge/general/insufficient modes, grounding protections and before/after examples are detailed in [CONVERSATION_QUALITY_REPORT.md](CONVERSATION_QUALITY_REPORT.md). The 40-question evaluation is committed under `backend/evaluation/`.

### Before/after comparison

The final local real-Sarvam comparison uses the same questions and scoring rules as the baseline:

| Automated check | Before | Final |
|---|---:|---:|
| Intended answer mode | 27/40 | 40/40 |
| Expected key concepts | 30/40 | 40/40 |
| Relevant expected source retrieved/cited, or not applicable | 36/40 | 40/40 |
| Citation structure and no fabricated general sources | 40/40 | 40/40 |
| Numbered instructions where requested | 0/11 | 11/11 |
| Concise answer, at most 220 words | 40/40 | 40/40 |

These are regression indicators, not a semantic-correctness guarantee. In particular, the citation score tests marker/source structure rather than proving every fact correct. Earlier iteration runs exposed and led to fixes for unsupported NFC conclusions, irrelevant device troubleshooting, PDF instructions substituted for scan questions, and numbering gaps after claim removal.

### Validation

- Backend offline suite: **240 passed**; all **15 existing live Sarvam tests passed**. Ruff passes.
- Frontend type checking, ESLint and production build pass.
- Existing chat browser acceptance script passes. Existing admin browser acceptance script passes **27/27** checks, covering password login, cookies, dashboard analytics, navigation, feedback, filters and logout against an isolated synthetic database.
- Existing screenshot suite captures desktop, laptop, tablet and mobile layouts; it reports a pre-existing **404 `/favicon.ico`**. No layout overflow or interaction failures were reported. The favicon was not changed as part of this backend task.
- Live deployed-runtime and public-browser verification results follow below.

All automated question/feedback evaluations use separate synthetic databases, including the deployed-container run. No synthetic question or resolution vote from this release was written to the production PostgreSQL analytics database. Full model answers, passages, local test credentials and screenshots remain private ignored artifacts.


### Final live deployment verification

The final Railway image was checked against SHA-256 hashes of all seven affected runtime modules. Forty requests were exercised through FastAPI's ASGI test client **inside that deployed container**, using the real Railway Sarvam credential and unchanged production index, but an explicitly isolated temporary synthetic database. This did not alter the running service configuration or production database. **30 responses came from real Sarvam-105B calls**; the remaining requests used the intended deterministic safety fallbacks.

| Final deployed-runtime check | Result |
|---|---:|
| HTTP success | 40/40 |
| Expected answer mode | 40/40 |
| Expected concepts | 39/40 |
| Relevant sources / not applicable | 40/40 |
| Valid citation structure / no general citations | 40/40 |
| Numbered procedural answers | 11/11 |
| Concise answers | 40/40 |
| Synthetic resolution feedback | HTTP 204 |
| Anonymous admin analytics | HTTP 401 |

The single concept-keyword miss is the boarding-pass answer's use of “share” rather than the probe's “upload/scan” wording. Manual inspection confirms that it identifies Digi Yatra in the phone's Share menu and provides four cited PDF-sharing steps. It does not indicate a refusal or missing instructions. International travel, live Delhi gate status, unsupported NFC requirements and account-access requests remain cautious fallbacks; basic technology definitions have no fabricated KB citations.

Public URL checks through Vercel and directly on Railway confirm healthy APIs with 119 indexed chunks, HTTP 401 for anonymous analytics, and HTTP 404 for private corpus paths, `/.env` and the production OpenAPI schema. Homepage and administrator login load without an HTTP Basic challenge; anonymous dashboard access redirects to login.

Fresh desktop and mobile browser contexts loaded the real Vercel website and rendered the final deployed-container responses using browser request interception: **20/20 checks passed**, including numbered instructions, source expansion, general-knowledge labelling without fake sources, unofficial-site disclosure, admin redirects and page-width checks. This is a rendering/integration check, **not a claim that 30 public HTTP chatbot requests traversed Vercel**. The public proxy was checked separately through health and security endpoints. This separation keeps synthetic questions and feedback out of primary production analytics.

Live administrator preservation checks: **7/7 passed**, including unchanged Argon2id hash, accepted authenticated session, protected analytics, rejected missing/wrong CSRF and cross-origin logout, authenticated dashboard rendering, normal browser logout and rejected replay of the revoked session. The short-lived verification session was revoked through normal logout. The production password was not obtained or reset; actual password-login behavior was exercised in the isolated browser acceptance test instead.

No Vercel redeploy was necessary because no frontend runtime code changed. No Railway billing settings, credentials, production data, knowledge approval rules or unrelated infrastructure were changed. Remaining operational issues are the existing missing favicon and the previously documented Railway legacy-configuration migration deadline. Generative language and lexical validation remain imperfect; the evaluation is a bounded regression sample, not a guarantee for every possible passenger question.
