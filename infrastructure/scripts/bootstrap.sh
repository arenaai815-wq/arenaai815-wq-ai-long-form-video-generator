#!/usr/bin/env bash
# One-time developer setup: Python venv + deps, Node deps, .env, migrations, seed data.
# Requires: Python 3.11+, Node 20+, PostgreSQL 14+ and Redis 6+ reachable at the URLs in .env
# (or run `make infra` to start them with Docker first).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

[ -f .env ] || { cp .env.example .env; echo "created .env from .env.example - edit it if needed"; }

echo "==> backend"
cd backend
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
export PYTHONPATH="$ROOT:$ROOT/backend"
.venv/bin/python - <<'PY'
import imageio_ffmpeg, shutil
print("ffmpeg:", shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe())
PY
.venv/bin/alembic upgrade head
.venv/bin/python -m scripts.seed
cd ..

echo "==> frontend"
cd frontend
npm install --no-audit --no-fund
cd ..

cat <<MSG

Done. Start everything with:
  ./infrastructure/scripts/dev.sh
Then open http://localhost:3000  (API docs: http://localhost:8000/api/v1/docs)
Default admin: admin@longform.local / admin12345
MSG
