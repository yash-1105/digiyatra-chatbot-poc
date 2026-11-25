#!/bin/sh
# Project-local, socket-only PostgreSQL for DESTRUCTIVE tests (never production).
#   scripts/pg_test_server.sh start|stop|status|url
# Binaries: pgserver wheel in .cache/pgtools (project-local venv). Data: .cache/pgdata. Socket: .cache/pgsock.
# listen_addresses='' => no TCP listener at all; trust auth is therefore reachable only via the 0700 socket dir.
set -eu
cd "$(dirname "$0")/.."
ROOT=$(pwd -P)
umask 077
TOOLS="$ROOT/.cache/pgtools"; DATA="$ROOT/.cache/pgdata"; SOCK="$ROOT/.cache/pgsock"; PORT=55432
if [ ! -x "$TOOLS/bin/python" ]; then
  python3.12 -m venv "$TOOLS"
  PIP_CACHE_DIR="$ROOT/.cache/pip" "$TOOLS/bin/pip" install -q pgserver==0.1.4
fi
BIN=$(ls -d "$TOOLS"/lib/python3*/site-packages/pgserver/pginstall/bin | head -1)  # path only; never imported
case "${1:-status}" in
  start)
    mkdir -p "$SOCK"; chmod 700 "$SOCK"
    [ -d "$DATA" ] || "$BIN/initdb" -D "$DATA" -U postgres --auth=trust -E UTF8 >/dev/null
    "$BIN/pg_ctl" -D "$DATA" -l "$ROOT/.cache/pg.log" -o "-c listen_addresses='' -k $SOCK -p $PORT" -w start ;;
  stop) "$BIN/pg_ctl" -D "$DATA" -m fast stop ;;
  status) "$BIN/pg_ctl" -D "$DATA" status || true ;;
  url) echo "postgresql+psycopg://postgres@/postgres?host=$SOCK&port=$PORT" ;;
  *) echo "usage: $0 start|stop|status|url" >&2; exit 2 ;;
esac
