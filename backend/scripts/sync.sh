#!/bin/sh
# Railway cron entrypoint for the official-knowledge synchronisation (Pipeline A).
# Schedule (service setting): 30 21 * * 6  (UTC) = every Sunday 03:00 IST.
# Short-lived: applies migrations (idempotent), runs due sources, publishes, closes connections, exits.
# Needs only DATABASE_URL (+ OFFICIAL_SOURCE_LOOKUP_ENABLED=true); no LLM provider keys.
set -eu
python -m app.cli db-upgrade
exec python -m app.cli sync-run --trigger schedule
