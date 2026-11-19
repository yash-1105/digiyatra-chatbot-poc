# Transfer Checklist — Hostinger → Laptop (SFTP)

**Goal:** move the complete, working source to the laptop **without** secrets, runtime data, caches or build output. Deployment then happens from the laptop (see `docs/DEPLOYMENT_HANDOFF.md`).

## Recommended: one audited archive

On Hostinger:
```bash
cd ~/Yash/digiyatra-chatbot-poc
./scripts/make_transfer_package.sh
#   -> transfer/digiyatra-chatbot-poc-<UTC timestamp>.tar.gz  (+ .sha256)
```
The script packages an **allow-list** of paths, then **aborts** if the archive contains any of:
- `.env`, `*.db`;
- `node_modules`, `.venv`, `.next`;
- `backend/data`, `knowledge/curated`, `.cache`;
- screenshots or PostgreSQL test data;
- anything that looks like a Sarvam key.

Download it with SFTP:
```bash
sftp <user>@<hostinger-host>
sftp> get ~/Yash/digiyatra-chatbot-poc/transfer/digiyatra-chatbot-poc-<stamp>.tar.gz
sftp> get ~/Yash/digiyatra-chatbot-poc/transfer/digiyatra-chatbot-poc-<stamp>.tar.gz.sha256
```
On the laptop:
```bash
shasum -a 256 -c digiyatra-chatbot-poc-<stamp>.tar.gz.sha256      # Linux: sha256sum -c
mkdir digiyatra-chatbot-poc && tar -xzf digiyatra-chatbot-poc-<stamp>.tar.gz -C digiyatra-chatbot-poc
```

## INCLUDE (what the archive contains)

| Path | Why |
|---|---|
| `CLAUDE.md`, `README.md`, `.gitignore`, `.dockerignore`, `railway.toml` | Rules, overview, ignore rules, Railway config |
| `docs/` | API, handoff, transfer checklist, knowledge inventory, live evaluation report |
| `design/dgca-reference.png` | Primary visual reference |
| `scripts/make_transfer_package.sh` | Reproducible packaging |
| `knowledge/approval_manifest.json` | Explicit approval list (sign-off pending) |
| `knowledge/deploy/` (`chunks.jsonl`, `corpus.json`) | **Private deployable corpus.** Do not commit to public GitHub; upload only in a private Railway build context |
| `knowledge/raw/` (37 files) | Private originals for future re-ingestion. **Keep locally only; git-ignored; never deployed** |
| `backend/app`, `backend/ingestion`, `backend/migrations`, `backend/tests`, `backend/scripts` | Backend source, migrations, tests, start script |
| `backend/alembic.ini`, `pyproject.toml`, `requirements.txt`, `requirements.lock`, `Dockerfile`, `.env.example` | Build and configuration |
| `frontend/src`, `frontend/public`, `frontend/scripts` | Frontend source and E2E scripts |
| `frontend/package.json`, `package-lock.json`, `next.config.ts`, `tsconfig.json`, `postcss.config.mjs`, `eslint.config.mjs`, `.npmrc`, `.env.example` | Build and configuration |

## EXCLUDE (never transfer)

| Path | Reason |
|---|---|
| `backend/.env` (and any `.env`, `.env.local`) | **Secrets** (Sarvam key). Re-create from `.env.example`. Rotate the key; it was once pasted in chat. |
| `backend/data/app.db*` | Local analytics and admin database. It holds the dev admin hash and dev analytics. Production uses Railway PostgreSQL. |
| `backend/data/lancedb/` | Derived index; rebuilt by `ensure-index` |
| `backend/.venv/`, `.cache/` (npm/pip caches, pgtools, local PostgreSQL test cluster) | Environment-specific; reinstall from lockfiles |
| `frontend/node_modules/`, `frontend/.next/`, `*.tsbuildinfo`, `next-env.d.ts` | Build output and dependencies; regenerated |
| `knowledge/curated/` | Review artefacts that include sanitised records of **unapproved** files. Regenerate with `app.cli ingest` if needed. |
| `frontend/screenshots/`, `*.log`, `.pytest_cache`, `.ruff_cache`, `__pycache__` | Generated output, logs and caches |
| `transfer/` | The archives themselves |

## After extracting on the laptop

```bash
# Backend
cd backend && python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && chmod 600 .env      # put the NEW (rotated) SARVAM_API_KEY here
.venv/bin/python -m app.cli db-upgrade && .venv/bin/python -m app.cli ensure-index
.venv/bin/python -m pytest                   # expect 189 passed (offline; live tests excluded by default)
.venv/bin/python -m app.cli create-admin     # local admin for testing the dashboard

# Frontend
cd ../frontend && npm ci && npm run typecheck && npm run lint && npm run build
```
Then follow `docs/DEPLOYMENT_HANDOFF.md` §13 (GitHub), §11 (Railway) and §12 (Vercel).

## Final pre-push checks (laptop)

- [ ] `git status` shows no `.env`, `knowledge/raw`, `knowledge/curated`, `*.db`, `node_modules`, `.venv`, `.next`.
- [ ] `grep -rI "sk_" --exclude-dir=node_modules --exclude-dir=.venv .` finds no key.
- [ ] The repository is **PUBLIC**, as required by the current deployment request; every staged file has been audited and approved for publication.
- [ ] No retrieval corpus, raw-source manifest, evaluation report, inventory or reference screenshot is staged.
- [ ] Knowledge-derived frontend text has explicit publication approval.
- [ ] A new Sarvam key is set only as a Railway variable.
