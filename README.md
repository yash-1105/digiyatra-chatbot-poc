# Digi Yatra AI Chatbot — Proof of Concept

An informational website about Digi Yatra, styled after the DGCA digigov portal, with a floating AI assistant and an admin entry point.

> **POC notice:** this is an unofficial demonstration. It is not a website of the Digi Yatra Foundation, MoCA, DGCA or the Government of India.

This PUBLIC repository contains application source and approved frontend content. The retrieval corpus, raw documents and approval manifest are intentionally private; obtain them through the authorized private deployment channel before running corpus-dependent backend commands or tests. See `docs/PRODUCTION_DEPLOYMENT_REPORT.md` for live staging URLs and verification status. Production remains access-restricted while content-owner approval is pending.

| Milestone | Scope | Status |
|---|---|---|
| 1 | Frontend: website, chatbot UI, admin login UI | ✅ Done |
| 2 | Backend: knowledge ingestion, LanceDB retrieval, FastAPI, Sarvam-105B RAG chatbot | ✅ Done. Live-tested with Sarvam; uses lexical vectors because `embeddinggemma-2` is not enabled for the key |
| 3 | Admin authentication + analytics dashboard (SQLAlchemy/Alembic, Argon2id, server-side sessions) | ✅ Done |
| 4 | Production readiness: PostgreSQL verified, Docker/Railway/Vercel config, deploy corpus, sentence-level citation grounding | ✅ Ready for deployment from the laptop — see `docs/DEPLOYMENT_HANDOFF.md` |

## Quick start (full stack, local only)

```bash
# 1. Backend (Python 3.12) — everything stays inside the project
cd ~/Yash/digiyatra-chatbot-poc/backend
python3 -m venv .venv
PIP_CACHE_DIR=../.cache/pip .venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env      # then edit .env and set SARVAM_API_KEY
.venv/bin/python -m app.cli reindex         # ingest knowledge/raw -> curated -> LanceDB
.venv/bin/python -m app.cli db-upgrade      # create/upgrade the analytics + admin database (Alembic)
.venv/bin/python -m app.cli create-admin    # admin@gmail.com — prompts for the password privately
.venv/bin/uvicorn app.asgi:app --host 127.0.0.1 --port 8000

# 2. Frontend (another terminal)
cd ~/Yash/digiyatra-chatbot-poc/frontend
npm install && npm run build && npm start   # http://127.0.0.1:3000 (proxies /api/v1 -> :8000)
```

Knowledge-base commands (in `backend/`):

| Command | Purpose |
|---|---|
| `.venv/bin/python -m app.cli ingest` | Parse `knowledge/raw` → `knowledge/curated` and write the QC report |
| `.venv/bin/python -m app.cli reindex` | Ingest and fully rebuild the LanceDB index. Run after editing `knowledge/approval_manifest.json`. |
| `.venv/bin/python -m app.cli reindex-file about_us.md` | Re-ingest and replace one document |
| `.venv/bin/python -m app.cli delete visa_fees.md` | Remove a document's chunks from the index |
| `.venv/bin/python -m app.cli query "How do I register?"` | Inspect retrieval scores |
| `.venv/bin/python -m app.cli probe-embeddings` | Check whether the key can use Sarvam `embeddinggemma-2` |

Tests (in `backend/`): `.venv/bin/python -m pytest` runs the offline suite with a mocked Sarvam API. `.venv/bin/python -m pytest -m live tests/live` and `.venv/bin/python scripts/live_eval.py` call the real Sarvam API (key required).

Reports:
- `knowledge/curated/ingestion_report.md`: inventory, contradictions, review queue
- `docs/API.md`: API, guardrails and environment
- `docs/live_eval_report.md`: real Sarvam answers, written by `live_eval.py`

## Quick start (frontend only)

Requires Node.js 20+. Every cache stays inside the project (`frontend/.npmrc` points npm's cache at `.cache/npm`).

```bash
cd ~/Yash/digiyatra-chatbot-poc/frontend
cp .env.example .env.local      # optional — defaults use the real backend via the proxy
npm install
npm run dev                     # http://127.0.0.1:3000 (hot reload)
```

Production build:

```bash
npm run typecheck && npm run lint && npm run build
npm start                       # serves the build on http://127.0.0.1:3000
```

Visual/interaction check (with the server running):

```bash
npm run screenshots             # writes frontend/screenshots/*.png
```

It uses the existing Playwright Chromium in `~/.cache/ms-playwright`; set `CHROMIUM_PATH` to use a different browser.

## Previewing from the Hostinger server (without exposing it publicly)

The server binds only to `127.0.0.1:3000`. From your laptop, open an SSH tunnel:

```bash
ssh -N -L 3000:127.0.0.1:3000 <user>@<hostinger-server>
```

Then open http://localhost:3000 on your laptop. Chat requests go through the Next.js proxy, so only port 3000 needs forwarding. The backend stays on `127.0.0.1:8000`. Use a different local port (e.g. `-L 3300:127.0.0.1:3000`) if 3000 is busy locally. Don't open firewall ports or bind to `0.0.0.0`.

## Environment variables (`frontend/.env.example`)

| Variable | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_CHAT_MODE` | `api` | `api` = FastAPI + Sarvam backend; `mock` = explicit dev-only, labelled canned answers |
| `NEXT_PUBLIC_API_BASE_URL` | empty | Empty = same origin via the Next.js proxy |
| `BACKEND_URL` | `http://127.0.0.1:8000` | Server-side proxy target for `/api/v1/*` |
| `NEXT_PUBLIC_CHAT_TIMEOUT_MS` | `120000` | Chat request timeout |

## Admin dashboard (Milestone 3)

- **Setup** (once, in an interactive terminal; the password is never echoed or stored in plain text):
  ```bash
  cd backend && .venv/bin/python -m app.cli db-upgrade && .venv/bin/python -m app.cli create-admin
  .venv/bin/python -m app.cli create-admin --reset-password   # change it later (signs out all sessions)
  ```
- **Sign in** at `/admin/login`. The dashboard is at `/admin/dashboard` and shows only real data from the database.
- **Database:** SQLite by default (`backend/data/app.db`); set `DATABASE_URL` for PostgreSQL. Schema and metric definitions are in `docs/API.md`.
- **Privacy:** no chat text, Aadhaar numbers, OTPs, passport details or boarding-pass contents are stored. Conversations are anonymous hashes; questions are stored only as a fixed topic plus allow-listed keywords.

## Features

- **DGCA-style layout**: navy utility bar, bilingual branding header, red POC notice line, blue nav with home icon, carousel + "Key Highlights" panel, "What's New?" tabs, light-grey bands, white cards and a navy footer.
- **Sections**: Welcome (mission/vision panels + announcements), About, How It Works, Registration Guide, Airport Journey, Supported Airports (searchable, labelled as an unverified snapshot), Privacy & Security, FAQ (categories + search), Support & Contact.
- **Accessibility**: skip links, Screen Reader Access page, high contrast mode, text size controls (+A/A/-A), English/Hindi navigation and headings, keyboard-operable tabs/accordions/carousel/chat, reduced-motion support, and live regions.
- **Chatbot**: floating launcher, animated panel (full-screen on mobile), welcome message, starter questions, message bubbles, typing indicator, error + retry, collapsible source citations, clear conversation (with confirmation), "Did this resolve your issue?" feedback, and session persistence. Mock mode is labelled in the header, in a banner and on every reply.
- **Admin**: `/admin/login` with validation, show/hide password, and loading/error states. `/admin/*` is protected by middleware plus a server-side layout guard that fails closed. No passwords are stored in the frontend.

See `CLAUDE.md` for architecture, rules and the backend API contract.
