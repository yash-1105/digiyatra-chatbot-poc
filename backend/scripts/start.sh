#!/bin/sh
# Container start-up (Railway). Idempotent: safe on every restart/redeploy.
set -eu
echo "[start] applying database migrations"
python -m app.cli db-upgrade
echo "[start] ensuring knowledge index (rebuilds from the bundled approved corpus if missing/stale)"
python -m app.cli ensure-index
echo "[start] serving on ${HOST:-0.0.0.0}:${PORT:-8000}"
# HOST defaults to 0.0.0.0 inside the container; set HOST=127.0.0.1 when running this script on a shared machine.
# Single worker: rate limiting and conversation memory are in-process (see DEPLOYMENT_HANDOFF.md).
exec uvicorn app.asgi:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}" --workers 1 --no-server-header --timeout-keep-alive 75
