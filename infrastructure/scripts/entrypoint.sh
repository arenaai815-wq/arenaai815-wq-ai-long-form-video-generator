#!/usr/bin/env bash
# Container entrypoint for the backend image.
#   api        -> run DB migrations (unless SKIP_MIGRATIONS=1) then start uvicorn
#   worker     -> Celery worker; queues via WORKER_QUEUES (default: all)
#   beat       -> Celery beat scheduler (periodic maintenance: stale jobs, heartbeats, cleanup)
#   migrate    -> run migrations and exit
#   seed       -> create the default plans/admin user and exit
#   <anything> -> exec as-is
set -euo pipefail
cd /app/backend

wait_for_db() {
  python - <<'PY'
import os, time, sys
from sqlalchemy import create_engine, text
url = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql+psycopg://")
if not url:
    sys.exit(0)
for attempt in range(60):
    try:
        with create_engine(url, pool_pre_ping=True).connect() as c:
            c.execute(text("select 1"))
        print("database reachable"); sys.exit(0)
    except Exception as exc:  # noqa: BLE001
        print(f"waiting for database ({attempt + 1}/60): {exc.__class__.__name__}"); time.sleep(2)
sys.exit("database not reachable")
PY
}

case "${1:-api}" in
  api)
    wait_for_db
    if [ "${SKIP_MIGRATIONS:-0}" != "1" ]; then alembic upgrade head; fi
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
      --workers "${WEB_CONCURRENCY:-2}" --proxy-headers --forwarded-allow-ips="*" \
      --timeout-keep-alive 75 --log-level "${UVICORN_LOG_LEVEL:-info}"
    ;;
  worker)
    wait_for_db
    exec celery -A workers.celery_app:celery_app worker \
      -Q "${WORKER_QUEUES:-generation,render,maintenance}" \
      -c "${WORKER_CONCURRENCY:-2}" \
      -n "${WORKER_NAME:-worker}@%h" \
      --loglevel "${CELERY_LOG_LEVEL:-INFO}" --max-tasks-per-child "${WORKER_MAX_TASKS_PER_CHILD:-50}"
    ;;
  beat)
    wait_for_db
    exec celery -A workers.celery_app:celery_app beat --loglevel "${CELERY_LOG_LEVEL:-INFO}" \
      --schedule /tmp/celerybeat-schedule
    ;;
  migrate)
    wait_for_db; exec alembic upgrade head ;;
  seed)
    wait_for_db; exec python -m scripts.seed ;;
  *)
    exec "$@" ;;
esac
