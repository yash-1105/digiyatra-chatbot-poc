# Production deployment report

Date: 2026-11-19 (Asia/Kolkata)

**Status: DEPLOYMENT IN PROGRESS — LIVE VERIFICATION PENDING.**
The owner authorized deployment under the existing Railway settings and explicitly instructed that spending limits must not be checked or changed. The earlier budget gate is superseded. Public source and frontend publication are approved; knowledge corpus redistribution and unrestricted public access remain unapproved. Railway project, PostgreSQL service and Vercel project have been created. No live application success is claimed.

## Deployment URLs

| Component | URL / state |
|---|---|
| Public GitHub repository `digiyatra-chatbot-poc` | Publication in progress |
| Railway FastAPI backend | Provisioned; deployment/configuration in progress |
| Railway PostgreSQL | Provisioned; deployment/configuration in progress |
| Vercel Next.js frontend | Project created; deployment in progress |

## Intended architecture

```text
Authorized staging users
  -> HTTPS / protected Vercel Next.js frontend
  -> same-origin /api/v1/* proxy
  -> access-restricted Railway FastAPI backend (1 replica, 1 worker)
       -> Railway PostgreSQL: administrators, hashed sessions, anonymous analytics
       -> ephemeral LanceDB: rebuilt from the private, hashed retrieval corpus
       -> Sarvam sarvam-105b: sole generative provider
```

The existing startup script applies Alembic migrations, ensures the knowledge index, and starts one Uvicorn worker. `railway.toml` specifies one replica. Production must use a new PostgreSQL database, never local analytics data. Frontend rewrites require `BACKEND_URL` before the Vercel build; admin origins must match the final HTTPS frontend origin. Existing admin session cookies use HttpOnly, Secure in production, and SameSite=Strict, with CSRF protection on logout and origin checks on login/logout.

## Security and publication findings

1. The corpus records content-owner sign-off as **PENDING**. Retrieval approval is POC curation and does not establish public redistribution rights. Its 119 chunks from 26 documents match the recorded SHA-256 and all have retrieval status `approved`. The international-trial draft is excluded. The corpus was neither edited nor regenerated.
2. `frontend/src/content/site.ts` and `frontend/src/content/mock-answers.ts` contain knowledge-derived text. `docs/live_eval_report.md` reproduces responses. The owner subsequently explicitly approved public application source and frontend content. That resolves the frontend publication approval; the retrieval corpus and evaluation report remain private. Publication is proceeding under the latest authorization.
3. Git exclusions now cover the deployment corpus, raw-source approval manifest, knowledge inventory, evaluation report, reference screenshot, database backups, archives, private keys, and Railway/Vercel local metadata, in addition to the existing secret/runtime exclusions. Private originals remain untouched.
4. A secret-pattern scan covered all 167 then-visible source candidates before this report was added. The three matches were reviewed: a template database URL, a database URL example in a code comment, and the explicitly synthetic Sarvam test key. No actual secret was identified by those checks. Pattern scans are not proof that all content has redistribution approval; the final staged-file review is still required before publishing.
5. No actual `.env`, analytics database, session store or credential-bearing transfer archive was found in the initial file scan. The handoff states that a previous Sarvam key was exposed in chat. It must be revoked and replaced, regardless of whether it was copied here.
6. Production origin enforcement could accept an origin matching a supplied Host/forwarded-host value outside the allow-list. The production branch now requires an exact configured origin. Two regression cases cover those bypass attempts.
7. Dependency audits found a vulnerable nested PostCSS and vulnerable Starlette. PostCSS is overridden to 8.5.33. FastAPI is pinned to 0.136.0 and Starlette to 1.3.1, with annotated-doc 0.0.7 added to the runtime lockfile. Both dependency audits pass after remediation. No frontend layout, style, or product component was changed.
8. Added temporary HTTP Basic staging access protection across the frontend and direct backend. Production fails closed if the staging credential is missing. Backend health remains available for platform probes. Credentials are server-side environment variables, generated privately and never committed. Authorized browser requests use the existing API rewrite; server-side session validation adds the staging authorization header. Live denial checks are pending.

## Local verification results

| Check | Result |
|---|---|
| Required project and deployment documents | Read |
| Python runtime | Python 3.12.14, project-local virtual environment |
| Node runtime | Node 24.16.0; original handoff used Node 20 |
| GitHub / Railway / Vercel authentication | Confirmed through CLI identity checks; no token values recorded |
| Backend offline suite after all backend changes | **193 passed**, 15 live tests deselected |
| Backend Ruff | Passed |
| Backend `pip check` | Passed |
| Runtime lockfile `pip-audit` | No known vulnerabilities across 43 runtime dependencies |
| Frontend clean dependency install | Passed (`npm ci --ignore-scripts`) |
| Frontend typecheck and ESLint | Passed |
| Frontend production build after PostCSS patch | Passed |
| Frontend `npm audit` | Zero known vulnerabilities |
| Client JavaScript checks | Synthetic Sarvam key and `MockChatClient` identifier absent; production mock disabling also confirmed in existing implementation |
| Corpus SHA-256 / retrieval approval / draft exclusion | Passed |
| Required private-path Git exclusions | All 12 representative paths ignored |
| Local Git | Initialized on `main`; no commits, staged files or remote |
| Private Railway context | Prepared locally, 61 allow-listed files; hashes match current source |
| Docker image build | Not run: Docker daemon unavailable on this Mac |
| New PostgreSQL / migrations on Railway | PostgreSQL provisioned; backend migrations pending |
| Live Sarvam responses and source citations | Not run; rotated credential unavailable |
| Production administrator creation | Not run; requires deployed database and private password entry |
| Vercel-to-Railway proxy, cookies and CSRF | Not live-tested |
| Live analytics, resolution feedback, logout/replay | Not run |
| Unauthenticated staging access denial | Not run; access controls pending |

Offline tests use temporary synthetic databases under the ignored project cache. No local development analytics database was used as production data. These results do not replace live PostgreSQL, proxy, browser, or Sarvam verification. Test output includes deprecation warnings for the existing httpx TestClient path, AnyIO alias and a test's UTC helper; all tests pass.

## Private Railway delivery method

The reviewed build context is `.cache/railway-context`; its SHA-256 file inventory is `.cache/railway-context-inventory.json`. The context and inventory remain local and Git-ignored. The context is restricted to the local owner and contains only Docker build inputs and the private approved-for-retrieval corpus. No raw documents, secrets, databases, logs, frontend or test files are included.

After resource approval, staging protection and service configuration, upload only this context through the authenticated Railway CLI, as documented in `DEPLOYMENT_HANDOFF.md` section 13. Never upload the project root with `--no-gitignore`. GitHub-only backend auto-deployment cannot build this image because the public checkout will intentionally omit the private corpus. Recreate and re-audit the context whenever backend code or corpus changes.

## Railway cost configuration

The owner acknowledged the existing $10 hard limit and authorized deployment under those settings. The prior $5 enforceable-cap condition is superseded. No spending-limit checks or changes are being performed in this deployment run. One backend replica and one PostgreSQL service are authorized; no Railway Agent or paid Vercel upgrade is needed.

## Outstanding deployment work

Publish the audited source to PUBLIC GitHub, privately upload the corpus, deploy the backend, run migrations/index initialization, enter the rotated Sarvam key privately, create the administrator with the interactive CLI, deploy Vercel, and verify actual live behavior before marking completion. Keep whole-site staging restrictions in place until content-owner approval.

## Remaining readiness limits

Content-owner sign-off is pending. Retrieval and output grounding are lexical, not neural embeddings or semantic entailment. In-process limits and conversation state require one replica/worker and reset on restart. The real proxy-header chain, per-client throttling, external rewrite cookie forwarding, Vercel middleware behavior, response timeouts and HTTPS security controls require live verification. Existing handoff PostgreSQL results are historical evidence, not results reproduced on this Mac. No unrestricted public launch is authorized.

Reference documentation checked during preflight: [PostCSS advisory](https://github.com/postcss/postcss/security/advisories/GHSA-fxqj-rqcc-2cmp), [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/), [Railway CLI](https://docs.railway.com/cli), [Vercel Deployment Protection](https://vercel.com/docs/deployment-protection).
