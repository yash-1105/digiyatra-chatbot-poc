#!/bin/sh
# Build the Hostinger -> laptop transfer archive (download it via SFTP). Allow-list based:
# only source, docs, templates, the approved deploy corpus and (local-only) knowledge originals.
# Excludes secrets, virtual envs, node_modules, builds, caches, logs, screenshots and ALL databases.
set -eu
cd "$(dirname "$0")/.."
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=transfer/digiyatra-chatbot-poc-$STAMP.tar.gz
mkdir -p transfer
umask 077

tar -czf "$OUT" \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' --exclude='.env.local' --exclude='.env.*.local' \
  --exclude='node_modules' --exclude='.next' --exclude='.venv' --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' \
  --exclude='*.log' --exclude='*.tsbuildinfo' --exclude='.pytest_cache' --exclude='.ruff_cache' \
  CLAUDE.md README.md .gitignore .dockerignore railway.toml \
  docs design scripts \
  knowledge/approval_manifest.json knowledge/deploy knowledge/raw \
  backend/app backend/ingestion backend/migrations backend/tests backend/scripts \
  backend/alembic.ini backend/pyproject.toml backend/requirements.txt backend/requirements.lock \
  backend/Dockerfile backend/.env.example \
  frontend/src frontend/public frontend/scripts \
  frontend/package.json frontend/package-lock.json frontend/next.config.ts frontend/tsconfig.json \
  frontend/postcss.config.mjs frontend/eslint.config.mjs frontend/.npmrc frontend/.env.example

# Audit: refuse to leave a package that contains anything sensitive.
LIST=$(tar -tzf "$OUT")
BAD=$(printf '%s\n' "$LIST" | grep -E '(^|/)\.env$|\.db$|node_modules/|\.venv/|/\.next/|backend/data/|knowledge/curated/|\.cache/|screenshots/|pgdata' || true)
if [ -n "$BAD" ]; then echo "ABORT: forbidden paths in package:"; echo "$BAD"; rm -f "$OUT"; exit 1; fi
TMP=$(mktemp -d); tar -xzf "$OUT" -C "$TMP"
if grep -rIlE 'sk_[A-Za-z0-9]{6,}_[A-Za-z0-9]{12,}' "$TMP" >/dev/null 2>&1; then
  echo "ABORT: something that looks like a Sarvam key is inside the package"; rm -rf "$TMP" "$OUT"; exit 1
fi
rm -rf "$TMP"
sha256sum "$OUT" > "$OUT.sha256"
echo "Created $OUT ($(du -h "$OUT" | cut -f1), $(printf '%s\n' "$LIST" | grep -vc '/$') files)"
echo "SHA-256: $(cut -d' ' -f1 "$OUT.sha256")"
echo "Contains knowledge/raw (private originals): keep it OUT of git (already in .gitignore)."
