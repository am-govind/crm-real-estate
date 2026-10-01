# LandForge CRM — Local Setup

## Prerequisites

Install Docker Desktop, Node.js, pnpm, and Python 3.11+.

```bash
brew install node python@3.11 pnpm
brew install --cask docker
open -a Docker
```

Verify with `docker --version`, `docker compose version`, `node --version`, `pnpm --version`, and `python3 --version`.

PostgreSQL, PostGIS, Redis, and Keycloak are downloaded by Docker and do not need separate installation.

## Download and install

```bash
git clone https://github.com/am-govind/crm-real-estate.git
cd crm-real-estate
pnpm install
python3 -m venv apps/api/.venv
source apps/api/.venv/bin/activate
pip install --upgrade pip
pip install -e "apps/api[postgres]"
pip install -e apps/worker
chmod +x scripts/run-local.sh
```

For an existing checkout, use `cd /Users/govindmishra/Development/CRM_Real_Estate` and `git pull origin main`.

## Start the complete project

Run from the repository root:

```bash
./scripts/run-local.sh
```

The script starts Docker services, waits for PostgreSQL and Redis, applies migrations, creates the global development administrator, creates a demo company and sample CRM records, and starts the API, worker, and web application.

Keep the terminal open. Press `Ctrl+C` to stop API, worker, and web. Docker services remain running.

## URLs

```text
Web CRM:   http://localhost:5173
API:       http://localhost:8000
API docs:  http://localhost:8000/api/v1/docs
Keycloak:  http://localhost:8080
```

Check the API:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

## Login and demo data

```bash
open "http://localhost:8000/auth/login?return_to=http://localhost:5173/"
```

Use development user `developer@example.com`. The seeded workspace is `Demo Land Company` with slug `demo-land`.

## Mobile app

The runner starts the web app but not Expo. In another terminal:

```bash
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000 pnpm dev:mobile
```

For a physical phone, replace `localhost` with the Mac IP from `ipconfig getifaddr en0`.

## Verify services

```bash
docker compose ps
docker exec -it landcrm-redis redis-cli ping
docker exec -it landcrm-postgres psql -U landcrm -d landcrm -c "SELECT PostGIS_Version();"
```

Redis should return `PONG`.

## Logs and reset

Logs are written to `.local-logs/api.log`, `.local-logs/worker.log`, and `.local-logs/web.log`. Watch one with `tail -f .local-logs/api.log`.

Stop Docker services while preserving data:

```bash
docker compose stop
```

Reset local database and Redis data:

```bash
docker compose down -v
```

Use `down -v` only when intentionally resetting development data.

## Common fixes

If Docker is not running, use `open -a Docker` and wait for `docker info` to succeed. If pnpm is missing, run `brew install pnpm`. If `psql` is missing on macOS, use the Docker command above. If the browser cannot connect to port 5173, run `pnpm dev:web`. If `background_jobs` is missing, run `alembic -c migrations/alembic.ini upgrade head` from an activated virtual environment.

