#!/usr/bin/env bash
# Local Vero workspace. No imports, downloads, inference or approval on startup.
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
pg_bin="${VERO_PG_BIN:-/opt/homebrew/opt/postgresql@17/bin}"
runtime_dir="$project_dir/backend/storage/runtime"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://vero@127.0.0.1:55433/vero}"
if [[ ! -f "$runtime_dir/postgres/PG_VERSION" ]]; then
  echo 'Local database missing. See docs/local-workspace.md; startup never overwrites or restores a database automatically.' >&2
  exit 1
fi
if ! "$pg_bin/pg_ctl" -D "$runtime_dir/postgres" status >/dev/null 2>&1; then
  "$pg_bin/pg_ctl" -D "$runtime_dir/postgres" -l "$runtime_dir/postgres.log" -o '-h 127.0.0.1 -p 55433' start
fi
cd "$project_dir/backend"
.venv/bin/alembic upgrade head
api_pid=''
web_pid=''
cleanup() {
  [[ -z "$api_pid" ]] || kill "$api_pid" 2>/dev/null || true
  [[ -z "$web_pid" ]] || kill "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
if ! curl --silent --fail http://127.0.0.1:8000/api/health/ready >/dev/null; then
  .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
  api_pid=$!
fi
cd "$project_dir/frontend"
if ! curl --silent --fail http://127.0.0.1:5173/ >/dev/null; then
  npm run dev &
  web_pid=$!
fi
echo 'Vero: http://127.0.0.1:5173 — leave this terminal running. PostgreSQL persists locally.'
wait
