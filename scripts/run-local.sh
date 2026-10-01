#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Starting PostgreSQL/PostGIS, Redis, and Keycloak..."
docker compose up -d

echo "Waiting for PostgreSQL..."
until docker exec landcrm-postgres pg_isready -U landcrm -d landcrm >/dev/null 2>&1; do sleep 2; done

echo "Waiting for Redis..."
until docker exec landcrm-redis redis-cli ping 2>/dev/null | grep -q PONG; do sleep 2; done

if [[ ! -x apps/api/.venv/bin/python ]]; then
  echo "Creating Python environment..."
  python3 -m venv apps/api/.venv
  apps/api/.venv/bin/pip install --upgrade pip
  apps/api/.venv/bin/pip install -e "apps/api[postgres]" -e apps/worker
fi

export LANDCRM_ENV=development
export LANDCRM_AUTH_MODE=dev
export LANDCRM_DATABASE_URL="postgresql+psycopg://landcrm:landcrm_dev_password@localhost:5432/landcrm"
export LANDCRM_QUEUE_BACKEND=redis
export LANDCRM_REDIS_URL="redis://localhost:6379/0"
export LANDCRM_PUBLIC_API_URL="http://localhost:8000"
export LANDCRM_WEB_APP_URL="http://localhost:5173"
export LANDCRM_CORS_ORIGINS='["http://localhost:5173"]'
export LANDCRM_STORAGE_BACKEND=local
export LANDCRM_STORAGE_LOCAL_ROOT="$ROOT_DIR/.storage"

echo "Applying database migrations..."
apps/api/.venv/bin/alembic -c migrations/alembic.ini upgrade head

echo "Seeding global admin and demo company..."
PYTHONPATH="$ROOT_DIR/apps/api:$ROOT_DIR/apps/worker" apps/api/.venv/bin/python scripts/bootstrap_demo.py

mkdir -p .local-logs

cleanup() {
  trap - EXIT INT TERM
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  [[ -n "${WORKER_PID:-}" ]] && kill "$WORKER_PID" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting API, worker, and web app..."
PYTHONPATH="$ROOT_DIR/apps/api" apps/api/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 >.local-logs/api.log 2>&1 & API_PID=$!
PYTHONPATH="$ROOT_DIR/apps/api:$ROOT_DIR/apps/worker" apps/api/.venv/bin/python -m landcrm_worker.main >.local-logs/worker.log 2>&1 & WORKER_PID=$!
VITE_API_BASE_URL="http://localhost:8000" pnpm --filter @landcrm/web dev --host 0.0.0.0 >.local-logs/web.log 2>&1 & WEB_PID=$!

sleep 3
echo
echo "LandForge CRM is running:"
echo "  Web:      http://localhost:5173"
echo "  API:      http://localhost:8000"
echo "  API docs: http://localhost:8000/api/v1/docs"
echo "  Keycloak: http://localhost:8080"
echo
echo "Development login: developer@example.com"
echo "Demo tenant:       Demo Land Company (demo-land)"
echo
echo "Logs: .local-logs/api.log, .local-logs/worker.log, .local-logs/web.log"
echo "Press Ctrl+C to stop API, worker, and web. Docker services remain running."
wait
