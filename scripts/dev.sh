#!/usr/bin/env bash
# Starts Postgres, the API, the LiveKit worker, and the dashboard.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND="$ROOT/backend"
WEB="$ROOT/web"

PIDS=()

cleanup() {
  local pid
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

docker_ok() {
  docker info >/dev/null 2>&1
}

stop_port_listener() {
  local port=$1
  local pids
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti:"$port" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      # shellcheck disable=SC2086
      kill -9 $pids 2>/dev/null || true
    fi
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

# --- Docker / Postgres ---
docker=false
for _ in $(seq 1 30); do
  if docker_ok; then
    docker=true
    break
  fi
  sleep 2
done
if [[ "$docker" != true ]]; then
  echo "Docker is not running. Start the Docker daemon, then run this script again." >&2
  exit 1
fi

docker compose up -d

deadline=$((SECONDS + 120))
until docker compose exec -T postgres pg_isready -U helpline -d helpline >/dev/null 2>&1; do
  if (( SECONDS > deadline )); then
    echo "Postgres did not become ready." >&2
    exit 1
  fi
  sleep 2
done

# --- Preflight ---
if [[ ! -f "$BACKEND/.env" ]]; then
  echo "Missing backend/.env — copy backend/.env.example and fill in your keys." >&2
  exit 1
fi

if [[ ! -d "$WEB/node_modules" ]]; then
  echo "Installing web dependencies..."
  (cd "$WEB" && npm install)
fi

stop_port_listener 8000
stop_port_listener 5173
sleep 1

echo "Starting API..."
(cd "$BACKEND" && uv run uvicorn helpline.api:app --host 127.0.0.1 --port 8000) &
PIDS+=($!)

echo "Starting LiveKit worker..."
(cd "$BACKEND" && uv run python -m helpline.worker dev) &
PIDS+=($!)

echo "Starting dashboard..."
(cd "$WEB" && npm run dev -- --host 127.0.0.1 --port 5173) &
PIDS+=($!)

echo ""
echo "Dashboard  http://127.0.0.1:5173"
echo "API        http://127.0.0.1:8000/api/health"
echo "Press Ctrl+C to stop all services."
echo ""

wait "${PIDS[@]}"
