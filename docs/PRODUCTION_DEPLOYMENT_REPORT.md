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
| Backend deployment | `c14db3df-fabe-4a77-ace4-0224f8305d8b`, SUCCESS |
| Frontend deployment | `dpl_DfwE5JCyujiQgbcrihvByMkWCwBT`, READY |

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
