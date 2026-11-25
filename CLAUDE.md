# Digi Yatra AI Chatbot — POC

## 1. Workspace restrictions (MUST follow)

- The ONLY authorised workspace is `/home/claudeuser/Yash/digiyatra-latest`. Run `pwd -P` to confirm before working.
- Do not inspect, search, read, modify or delete other projects on this server. Never follow symlinks out of this directory.
- No `sudo`, no system-wide installs, no system maintenance or cleanup commands.
- Keep everything project-local: dependencies, npm cache (`.cache/npm`, set in `frontend/.npmrc`), Python venvs (`backend/.venv`), temp files (`.cache/`).
- Already-installed runtimes (Python 3.12, Node 20) and the pre-existing Playwright Chromium in `~/.cache/ms-playwright` may be *invoked* (read-only); never install into or modify them.
- Never print, hardcode or commit credentials. Secrets live only in untracked `.env*` files. Never put secrets in `NEXT_PUBLIC_*` variables.
- Provider keys (`SARVAM_API_KEY`, `ANTHROPIC_API_KEY`, `NOVITA_API_KEY`, and the optional sync-only `YOUTUBE_API_KEY`) live ONLY in `backend/.env` (chmod 600) locally and in Railway variables in production. Never echo them, never `cat` that file, never put them in frontend code, logs, test output, screenshots or Git, and never copy production keys to this server. Check presence only (e.g. `grep -c '^SARVAM_API_KEY=.\+' backend/.env`).
- Exactly three user-selectable generative providers exist: **Sarvam AI `sarvam-105b`** (default), **Anthropic `claude-haiku-5-5`** (Haiku 5.5) and **Novita `qwen/qwen3.8-flash`** (Qwen3.8 Flash). Do not add, remove or substitute providers or change their model IDs, keys or tuned settings without explicit owner approval. All three share the same guardrails, local retrieval/knowledge base and grounding checks; a provider failure never silently falls back to another provider.
- Git/GitHub from this server is ALLOWED for the existing repo `yash-1105/digiyatra-chatbot-poc` only: develop, test, commit and push. Never create new GitHub repositories.
  - Use the project-local GitHub CLI only: `.tools/bin/gh` (config/token in `.tools/gh-config`, chmod 700, excluded via `.git/info/exclude`). Repo-local credential helper + identity live in `.git/config`; never change global Git config, shell profiles or PATH. Never print or commit the token.
  - Push only after local tests pass, `git status`/`git diff --cached` show no private files, and `git push --dry-run` succeeds. The local `.git/hooks/pre-push` guard blocks `.env*`, `.tools/`, `knowledge/{raw,curated,deploy}/`, `knowledge/approval_manifest.json`, databases and keys — never bypass it (`--no-verify`).
  - Never commit private knowledge documents (`knowledge/raw`, `knowledge/curated`, `knowledge/deploy`, the approval manifest, `design/dgca-reference.png`), API keys, `.env*` files or credentials.
- Do NOT deploy to production (Railway/Vercel) from this (Hostinger) server until the existing deployment mechanisms are verified and the owner explicitly approves. No new Railway/Vercel projects, no billing changes. A GitHub push must not be treated as a deployment; see `docs/DEPLOYMENT_HANDOFF.md` (Railway needs the private knowledge corpus, which is NOT in GitHub).
- Development servers bind to `127.0.0.1` only — never `0.0.0.0` or a public port. Preview via SSH port-forwarding.
- No administrator password is ever hardcoded; auth is delegated to the backend (Milestone 3).

## 2. Content rules

- Site content comes from `knowledge/raw/` and is curated in `frontend/src/content/site.ts` (source file noted per block).
- Do NOT present as current fact: the DY-IPT international trial (draft doc), the India AI Summit 2026 event FAQ (historical), or download/journey/usage statistics. Publicly published official trial information is a separate source: it is served only as reviewed `verified` official records within their effective/expiry dates (sync strips usage statistics automatically).
- Do NOT invent announcements, airport availability, contact details or statistics. Dynamic sections (announcements, airports) must show empty states or clearly-labelled snapshots when approved data is unavailable.
- The site must stay clearly marked as an unofficial POC. No government insignia, no official Digi Yatra logo, no implied endorsement.
- Chat mock responses must always be labelled as mock — never pass them off as AI output. Normal chat flow uses the real API (`NEXT_PUBLIC_CHAT_MODE=api`, default).
- `knowledge/approval_manifest.json` is the ONLY place content is approved for indexing. Never index draft (DY-IPT), historical (AI Summit, events), irrelevant (visa fees, careers) or review_required files. Never edit `knowledge/raw/`.
- NEVER store chat text or passenger identifiers in the analytics DB — only topic slugs, allow-listed keywords, statuses and timestamps. Resolution counts ONLY explicit Yes/No feedback.
- Never hardcode or print the admin password; only `python -m app.cli create-admin` (getpass) may set it. Tests/E2E use synthetic random passwords in isolated databases; never write test traffic into `backend/data/app.db`.
- Browser E2E that sends chats (`frontend/scripts/chat-e2e.mjs`, `admin-e2e.mjs`) refuse to run unless `/api/v1/health` reports `database.label == "synthetic"`: start a separate backend with `DATABASE_URL=sqlite:///…/backend/data/acceptance-synthetic.db`, create a random synthetic admin, run, then delete that DB.
- Content-owner approval of `knowledge/approval_manifest.json` is still PENDING (POC curation only).
- Lexical (TF-IDF) vectors must never be described as neural/semantic embeddings. As of 2026-11-19 the key has NO access to `embeddinggemma-2` (Provisioned Throughput not enabled), so the index is lexical. To migrate later, run `python -m app.cli probe-embeddings`, then `reindex` with `EMBEDDING_PROVIDER=auto`.
- Keep `SARVAM_REASONING_EFFORT=none` unless `SARVAM_MAX_TOKENS` is raised a lot: with reasoning on, sarvam-105b can spend the whole budget and return empty content.

## 3. Architecture

```
digiyatra-latest/   (GitHub: yash-1105/digiyatra-chatbot-poc)
├── frontend/      Next.js 15 (App Router) + TypeScript + Tailwind CSS v4   ← Milestone 1 (done)
├── backend/       FastAPI + Sarvam 105B / Anthropic Haiku 5.5 / Novita Qwen3.8 Flash + LanceDB RAG
├── knowledge/     raw/ originals (read-only) · approval_manifest.json · curated/ (generated)
├── design/        dgca-reference.png — PRIMARY visual reference
├── docs/, tests/
```

### Frontend layout (`frontend/src`)
- `app/` — routes: `/`, `/accessibility`, `/admin/login`, `/admin/(protected)/dashboard`; `middleware.ts` guards `/admin/*`.
- `components/layout/` — UtilityBar (navy top bar + accessibility controls), SiteHeader, SiteFooter, PublicShell.
- `components/ui/` — design system: Container, Section, SectionHeading (bilingual), Card, Tabs (ARIA), Accordion, Button, EmptyState, ExternalLink.
- `components/home/` — one component per homepage section.
- `components/chat/` — ChatWidget, useChat (state machine), MessageBubble, SourceList, FeedbackControls, ChatComposer.
- `components/admin/` — AdminLoginForm, AdminHeader.
- `lib/api/` — `ChatClient` interface; `HttpChatClient` (FastAPI) and `MockChatClient` (dev); `auth-client.ts`.
- `lib/accessibility/preferences.tsx` — contrast, text size, locale (persisted; mirrored to `<html data-*>`).
- `lib/i18n/dictionary.ts` — English/Hindi UI chrome strings.
- `content/` — curated site content and mock chat answers.
- Design tokens: CSS variables in `app/globals.css` (`--navy`, `--brand`, `--accent`, `--band`, …) exposed as Tailwind colours; high-contrast mode overrides them.

### Backend layout (`backend/`) — full API docs in `docs/API.md`
- `ingestion/` — pipeline: discover → manifest → parse (markdown / docx / csv) → sanitise → dedupe → QC → chunk → `knowledge/curated/*`.
- `app/sync/` — Pipeline A: `sources.py` (allow-listed registry), `fetcher.py` (SSRF-safe HTTP), `extract.py` (HTML/FAQ/feeds), `pdf.py` (sandboxed pypdf), `policy.py` (validation/review), `job.py` (scheduler/lease/versioning), `publish.py` (atomic publication + API hot swap).
- `app/rag/` — `embeddings.py` (LexicalEmbedder, SarvamEmbedder), `store.py` (LanceDB index: build/upsert/delete/lookup), `retriever.py` (hybrid vector + BM25), `factory.py`.
- `app/clients/` — `sarvam.py` (Chat Completions V2), `anthropic.py` (Messages API), `novita.py` (OpenAI-compatible); shared `base.py` protocol, timeouts, retries, typed errors.
- `app/security/` — `guardrails.py` (input/output), `rate_limit.py`, `body_limit.py`.
- `app/services/` — `chat_service.py` (orchestration), `prompts.py`, `conversation.py`.
- `app/api/routes/` — `chat.py` (`POST /api/v1/chat`, `/feedback`), `health.py`, `admin.py` (login/logout/session/analytics). `app/main.py` = app factory.
- `app/db/` — SQLAlchemy models (`admin_users`, `admin_sessions`, `question_topics`, `conversations`, `interaction_events`, `resolution_feedback`), session, Alembic helpers; migrations in `backend/migrations/`.
- `app/services/analytics.py` (record + report), `topics.py` (fixed categories + allow-listed keywords), `auth.py` (Argon2id, sessions, CSRF, login throttle); `app/security/admin_auth.py` (access control).
- `tests/unit` (offline, all three providers mocked — default) and `tests/live` (`-m live`, real providers, needs development keys).
- Frontend calls `/api/v1/*` same-origin; Next.js rewrites proxy to `BACKEND_URL` (default `http://127.0.0.1:8000`).
- Admin auth: FastAPI `/api/v1/admin/*`; Next.js middleware + `(protected)/layout.tsx` validate the `dy_admin_session` cookie server-side via `GET /api/v1/admin/session` (fail closed). Dashboard: `/admin/dashboard`.

## 4. Commands

Backend (inside `backend/`; venv is `backend/.venv`, pip cache `.cache/pip`):
- `PIP_CACHE_DIR=../.cache/pip .venv/bin/pip install -r requirements.txt`
- Deployment: `docs/DEPLOYMENT_HANDOFF.md`, `docs/TRANSFER_CHECKLIST.md`; `backend/Dockerfile` + `railway.toml` + `backend/scripts/start.sh` (db-upgrade → ensure-index → uvicorn). Production knowledge = `knowledge/deploy/` ONLY (approved, hashed); `ensure-index` rebuilds LanceDB from it at start. Never ship `knowledge/raw` or `knowledge/curated`.
- PostgreSQL tests: start the project-isolated, socket-only server in `.cache/pgdata` (pgserver binaries in `.cache/pgtools`), then `DY_TEST_PG_URL='postgresql+psycopg://postgres@/postgres?host=<abs>/.cache/pgsock&port=55432' .venv/bin/python -m pytest tests/unit/test_admin_auth.py tests/unit/test_analytics.py tests/unit/test_api.py`. Never use the shared Docker daemon or system databases.
- Any server started on this host binds 127.0.0.1 (for `scripts/start.sh` set `HOST=127.0.0.1`).
- `.venv/bin/python -m app.cli db-upgrade` (Alembic) · `create-admin [--reset-password]` (interactive)
- Official-source sync (Pipeline A, never from chat; see `docs/OFFICIAL_SOURCE_SYNC_REPORT.md`): `sync-run [--source ID]` (needs `OFFICIAL_SOURCE_LOOKUP_ENABLED=true`) · `sync-status` · `sync-pending` · `sync-review RECORD|source:ID verified|rejected|revoked --reviewer NAME` · `sync-publish` · `sync-enable|sync-disable ID` · `sync-import [ID|--url URL] --file F [--file F2]` (blocked Foundation pages: `docs/MANUAL_IMPORT_FOUNDATION.md`; captures live in git-ignored `knowledge/imports/`) · `sync-review-report` / `sync-review-apply SHEET --reviewer NAME` (private pack in `.cache/review/`) · `sync-export --out F` / `sync-import-bundle F [--dry-run] [--as-pending]` (insert-only transfer to production; deploying code never copies a local DB). PostgreSQL tests: `scripts/pg_test_server.sh start|url|stop` (local socket only). Task 2 imports (see `docs/SOCIAL_MEDIA_YOUTUBE_SYNC_REPORT.md`): `sync-import-videos --file urls.txt` · `sync-import-transcript VIDEO_ID --file F.vtt --kind human|auto` · `sync-import-social --platform x|linkedin --file export.json`. Never scrape YouTube pages/feeds/captions or social sites; never ingest comments, DMs, personal or unverified accounts. Task 3: `ops-report` (knowledge + usage aggregates), `sync-rollback [--to ID]`; expanded eval `PYTHONPATH=. .venv/bin/python -m evaluation.expanded` (offline, mocked) / `--live --url … --inr … --usd …` (later, signed synthetic route); browser E2E `frontend/scripts/history-e2e.mjs` against the test-only `backend/scripts/e2e_stack.py` (synthetic DB, loopback ports 18731/18732 — port 8100 belongs to another service). Chat history is browser-local (`localStorage` `dy-chat-history-v1`, 7 days, redacted); never add a server-side chat archive. Local runs use their own DB (e.g. `DATABASE_URL=sqlite:///…/backend/data/official-sync-dev.db`), never `app.db`.
- `.venv/bin/python -m app.cli reindex` (ingest + rebuild index) · `ingest` · `index` · `reindex-file FILE` · `delete FILE` · `query "text"` · `stats` · `probe-embeddings`
- `.venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000`
- `.venv/bin/python -m pytest` (offline) · `.venv/bin/python -m pytest -m live tests/live` · `.venv/bin/python scripts/live_eval.py` · `.venv/bin/ruff check .`

Frontend (inside `frontend/`):
- `npm install` · `npm run dev` · `npm run typecheck` · `npm run lint` · `npm run build` · `npm start`
- `npm run screenshots` (server must be running) — renders desktop/laptop/tablet/mobile + interaction checks into `frontend/screenshots/`.

## 5. Design
The DGCA digigov portal screenshot (`design/dgca-reference.png`) is the primary reference: slim navy utility bar, white branding header with pipe-separated top links + red notice line + blue nav with home icon, carousel + "Highlights" panel, large centred "What's New?" heading with text tabs and orange underline, light-grey bands, white cards, round navy chat launcher bottom-right. Keep new UI consistent with this; avoid generic SaaS styling.
