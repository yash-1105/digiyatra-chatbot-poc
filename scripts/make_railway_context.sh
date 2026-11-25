#!/bin/sh
# Rebuild the PRIVATE Railway build context in .cache/railway-context (see docs/DEPLOYMENT_HANDOFF.md §13).
# Allow-list = exactly what backend/Dockerfile COPYs, plus the Dockerfile, railway.toml and .dockerignore.
# Contains the private approved corpus (knowledge/deploy): never commit, publish or upload it anywhere except
# `railway up .cache/railway-context --path-as-root --no-gitignore ...` to the existing private service.
# This script does NOT deploy anything.
#   scripts/make_railway_context.sh          API service context (includes railway.toml)
#   scripts/make_railway_context.sh --job    sync-job context WITHOUT railway.toml, so the API's start
#                                            command/health check can never be applied to the cron service
set -eu
cd "$(dirname "$0")/.."
umask 077
JOB=0
[ "${1:-}" = "--job" ] && JOB=1
if [ "$JOB" = 1 ]; then
  OUT=.cache/railway-context-sync
  INV=.cache/railway-context-sync-inventory.json
else
  OUT=.cache/railway-context
  INV=.cache/railway-context-inventory.json
fi
PY=backend/.venv/bin/python

# Refuse to package a corpus that fails its own integrity checks.
"$PY" -I - <<'EOF'
import hashlib, json, pathlib
d = pathlib.Path("knowledge/deploy")
meta = json.loads((d / "corpus.json").read_text())
assert hashlib.sha256((d / "chunks.jsonl").read_bytes()).hexdigest() == meta["corpus_sha256"], "corpus hash mismatch"
rows = [json.loads(l) for l in (d / "chunks.jsonl").open()]
assert len(rows) == meta["chunk_count"], "chunk count mismatch"
assert all(r.get("approval_status") == "approved" for r in rows), "non-approved chunk in corpus"
EOF

rm -rf "$OUT"
mkdir -p "$OUT/backend/scripts" "$OUT/knowledge"
cp .dockerignore "$OUT/"
[ "$JOB" = 1 ] || cp railway.toml "$OUT/"
cp backend/Dockerfile backend/requirements.lock backend/alembic.ini "$OUT/backend/"
cp backend/scripts/start.sh backend/scripts/sync.sh "$OUT/backend/scripts/"
for d in migrations ingestion app; do cp -R "backend/$d" "$OUT/backend/$d"; done
cp -R knowledge/deploy "$OUT/knowledge/deploy"
find "$OUT" \( -name __pycache__ -o -name '*.pyc' -o -name '.env*' -o -name '*.db' -o -name '*.log' \) -prune -exec rm -rf {} +

# Audit: nothing outside the allow-list may be present.
BAD=$(cd "$OUT" && find . -type f | grep -vE '^\./(railway\.toml|\.dockerignore|backend/(Dockerfile|requirements\.lock|alembic\.ini|scripts/(start|sync)\.sh|(migrations|ingestion|app)/.*)|knowledge/deploy/(chunks\.jsonl|corpus\.json))$' || true)
if [ -n "$BAD" ]; then echo "ABORT: unexpected files in context:"; echo "$BAD"; rm -rf "$OUT"; exit 1; fi
if grep -rIlE 'sk_[A-Za-z0-9]{6,}_[A-Za-z0-9]{12,}' "$OUT" >/dev/null 2>&1; then echo "ABORT: key-like string found"; rm -rf "$OUT"; exit 1; fi

"$PY" -I - "$OUT" "$INV" <<'EOF'
import hashlib, json, pathlib, subprocess, sys, datetime
out, inv = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
files = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob("*")) if p.is_file()}
meta = json.loads((out / "knowledge/deploy/corpus.json").read_text())
commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
dirty = subprocess.run(["git", "status", "--porcelain", "--", "backend", "railway.toml", ".dockerignore"], capture_output=True, text=True).stdout.strip()
inv.write_text(json.dumps({
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "git_commit": commit, "backend_worktree_clean": not dirty,
    "corpus_sha256": meta["corpus_sha256"], "chunk_count": meta["chunk_count"], "document_count": meta["document_count"],
    "file_count": len(files), "files": files}, indent=1) + "\n")
print(f"{out}: {len(files)} files, corpus {meta['corpus_sha256'][:12]}… ({meta['chunk_count']} chunks), commit {commit[:7]}, clean={not dirty}")
EOF
chmod -R go= "$OUT" "$INV"
