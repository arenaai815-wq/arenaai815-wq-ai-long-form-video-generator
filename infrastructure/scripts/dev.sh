#!/usr/bin/env bash
# Local development without Docker: runs the API, a Celery worker (+beat) and the Next.js dev
# server against PostgreSQL/Redis from .env (start those with `make infra` or your own).
#
#   ./infrastructure/scripts/dev.sh            # start everything, Ctrl-C stops all
#   ./infrastructure/scripts/dev.sh api        # only the API
#   ./infrastructure/scripts/dev.sh worker     # only the worker
#   ./infrastructure/scripts/dev.sh web        # only the frontend
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
[ -f .env ] || { echo "No .env found - copying .env.example"; cp .env.example .env; }
export PYTHONPATH="$ROOT:$ROOT/backend"
PY="$ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || PY=python

pids=()
cleanup() { echo; echo "stopping..."; for p in "${pids[@]}"; do kill "$p" 2>/dev/null || true; done; wait 2>/dev/null || true; }
trap cleanup EXIT INT TERM

start_api() {
  (cd backend && "$PY" -m alembic upgrade head && exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload) &
  pids+=($!)
}
start_worker() {
  (cd backend && exec "$PY" -m celery -A workers.celery_app:celery_app worker -Q generation,render,maintenance -c "${WORKER_CONCURRENCY:-2}" -B --loglevel INFO) &
  pids+=($!)
}
start_web() {
  (cd frontend && [ -d node_modules ] || npm install; cd frontend && exec npm run dev -- -H 0.0.0.0 -p "${WEB_PORT:-3000}") &
  pids+=($!)
}

case "${1:-all}" in
  api) start_api ;;
  worker) start_worker ;;
  web) start_web ;;
  all) start_api; start_worker; start_web ;;
  *) echo "usage: $0 [all|api|worker|web]"; exit 1 ;;
esac
wait
