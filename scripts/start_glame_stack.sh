#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-/root/glame-platform}"
FRONTEND_DIR="${FRONTEND_DIR:-$ROOT_DIR/frontend}"
BACKEND_DIR="${BACKEND_DIR:-$ROOT_DIR/backend}"
STOREFRONT_APP_DIR="${STOREFRONT_APP_DIR:-$ROOT_DIR/mobile/glame_app}"

ADMIN_PORT="${ADMIN_PORT:-3000}"
BACKEND_HOST="${BACKEND_HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
STOREFRONT_PORT="${STOREFRONT_PORT:-9092}"
API_BASE_URL="${API_BASE_URL:-https://portal.glamejewelry.ru}"
DATABASE_URL="${DATABASE_URL:-}"
QDRANT_URL="${QDRANT_URL:-}"
REDIS_URL="${REDIS_URL:-}"
ML_INFERENCE_URL="${ML_INFERENCE_URL:-http://127.0.0.1:8010}"
START_ML_INFERENCE="${START_ML_INFERENCE:-true}"
ML_INFERENCE_COMPOSE_FILE="${ML_INFERENCE_COMPOSE_FILE:-infra/docker-compose.yml}"
ML_INFERENCE_ENV_FILE="${ML_INFERENCE_ENV_FILE:-infra/.env}"
START_INFRA_SERVICES="${START_INFRA_SERVICES:-false}"
INFRA_COMPOSE_FILE="${INFRA_COMPOSE_FILE:-infra/docker-compose.yml}"
INFRA_ENV_FILE="${INFRA_ENV_FILE:-infra/.env}"
INFRA_SERVICES="${INFRA_SERVICES:-postgres qdrant redis ml_inference}"
WAIT_FOR_INFRA="${WAIT_FOR_INFRA:-true}"
INFRA_WAIT_TIMEOUT_SECONDS="${INFRA_WAIT_TIMEOUT_SECONDS:-120}"
PWA_STRATEGY="${PWA_STRATEGY:-none}"
STOREFRONT_DIR="${STOREFRONT_DIR:-$STOREFRONT_APP_DIR/build/web}"
BUILD_STOREFRONT="${BUILD_STOREFRONT:-true}"
STOREFRONT_BUILD_ID="${STOREFRONT_BUILD_ID:-$(date +%Y%m%d%H%M%S)}"

PIDS=()

log() {
  printf '[glame-stack] %s\n' "$*"
}

cleanup() {
  local exit_code=$?
  if ((${#PIDS[@]} > 0)); then
    log "Stopping services..."
    kill "${PIDS[@]}" 2>/dev/null || true
    wait "${PIDS[@]}" 2>/dev/null || true
  fi
  exit "$exit_code"
}

start_service() {
  local name="$1"
  shift

  log "Starting $name"
  (
    exec "$@"
  ) &
  PIDS+=("$!")
  log "$name PID: ${PIDS[-1]}"
}

require_dir() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    log "Directory not found: $dir"
    exit 1
  fi
}

parse_host_port() {
  local url="$1"
  local default_port="$2"
  python3 - "$url" "$default_port" <<'PY'
from urllib.parse import urlparse
import sys

url = (sys.argv[1] or "").strip()
default_port = int(sys.argv[2])

if not url:
    sys.exit(1)

parsed = urlparse(url)
host = parsed.hostname
port = parsed.port or default_port

if not host:
    sys.exit(1)

print(f"{host} {port}")
PY
}

wait_for_tcp() {
  local name="$1"
  local host="$2"
  local port="$3"
  local timeout="$4"
  local start_ts
  start_ts=$(date +%s)

  log "Waiting for $name on $host:$port"
  while true; do
    if bash -lc "exec 3<>/dev/tcp/$host/$port" >/dev/null 2>&1; then
      log "$name is ready on $host:$port"
      return 0
    fi

    if (( $(date +%s) - start_ts >= timeout )); then
      log "Timeout waiting for $name on $host:$port"
      return 1
    fi
    sleep 2
  done
}

wait_for_infra() {
  local parsed
  if [[ -n "$DATABASE_URL" ]]; then
    if parsed=$(parse_host_port "$DATABASE_URL" 5432); then
      wait_for_tcp "postgres" ${parsed} "$INFRA_WAIT_TIMEOUT_SECONDS"
    fi
  fi

  if [[ -n "$QDRANT_URL" ]]; then
    if parsed=$(parse_host_port "$QDRANT_URL" 6333); then
      wait_for_tcp "qdrant" ${parsed} "$INFRA_WAIT_TIMEOUT_SECONDS"
    fi
  fi

  if [[ -n "$REDIS_URL" ]]; then
    if parsed=$(parse_host_port "$REDIS_URL" 6379); then
      wait_for_tcp "redis" ${parsed} "$INFRA_WAIT_TIMEOUT_SECONDS"
    fi
  fi

  if [[ -n "$ML_INFERENCE_URL" ]]; then
    if parsed=$(parse_host_port "$ML_INFERENCE_URL" 8010); then
      wait_for_tcp "ml_inference" ${parsed} "$INFRA_WAIT_TIMEOUT_SECONDS"
    fi
  fi
}

trap cleanup EXIT INT TERM

require_dir "$FRONTEND_DIR"
require_dir "$BACKEND_DIR"
require_dir "$STOREFRONT_APP_DIR"

if ! command -v npm >/dev/null 2>&1; then
  log "npm not found in PATH"
  exit 1
fi

if ! command -v flutter >/dev/null 2>&1; then
  log "flutter not found in PATH"
  exit 1
fi

if [[ "$START_ML_INFERENCE" == "true" ]] && ! command -v docker >/dev/null 2>&1; then
  log "docker not found in PATH, ml_inference won't be started automatically"
  START_ML_INFERENCE="false"
fi

if ! command -v uvicorn >/dev/null 2>&1 && [[ ! -x "$BACKEND_DIR/venv/bin/uvicorn" ]]; then
  log "uvicorn not found in PATH and backend venv uvicorn is missing"
  exit 1
fi

if [[ "$BUILD_STOREFRONT" == "true" ]]; then
  log "Building storefront web app"
  (
    cd "$STOREFRONT_APP_DIR"
    flutter build web --release --pwa-strategy="$PWA_STRATEGY" --dart-define=API_BASE_URL="$API_BASE_URL"
    python3 "$ROOT_DIR/scripts/postprocess_flutter_web.py" "$STOREFRONT_APP_DIR/build/web" "$STOREFRONT_BUILD_ID"
  )
fi

if [[ "$START_INFRA_SERVICES" == "true" ]]; then
  log "Ensuring infra services are running: $INFRA_SERVICES"
  (
    cd "$ROOT_DIR"
    docker compose --env-file "$INFRA_ENV_FILE" -f "$INFRA_COMPOSE_FILE" up -d $INFRA_SERVICES
  )
elif [[ "$START_ML_INFERENCE" == "true" ]]; then
  log "Ensuring ml_inference container is running"
  (
    cd "$ROOT_DIR"
    docker compose --env-file "$ML_INFERENCE_ENV_FILE" -f "$ML_INFERENCE_COMPOSE_FILE" up -d ml_inference
  )
fi

if [[ "$WAIT_FOR_INFRA" == "true" ]]; then
  wait_for_infra
fi

start_service "backend" bash -c "cd '$BACKEND_DIR' || exit 1; source venv/bin/activate 2>/dev/null || true; exec env DATABASE_URL='$DATABASE_URL' QDRANT_URL='$QDRANT_URL' REDIS_URL='$REDIS_URL' ML_INFERENCE_URL='$ML_INFERENCE_URL' uvicorn app.main:app --host '$BACKEND_HOST' --port '$BACKEND_PORT'"
start_service "admin frontend" bash -c "cd '$FRONTEND_DIR' && exec env PORT='$ADMIN_PORT' npm run start"
start_service "storefront" bash -c "cd '$STOREFRONT_APP_DIR' && exec env STOREFRONT_PORT='$STOREFRONT_PORT' STOREFRONT_DIR='$STOREFRONT_DIR' python3 '$STOREFRONT_APP_DIR/web/serve_storefront.py'"

log "Admin frontend: http://0.0.0.0:$ADMIN_PORT"
log "Backend:        http://$BACKEND_HOST:$BACKEND_PORT"
log "DATABASE_URL:   ${DATABASE_URL:-<from env file>}"
log "QDRANT_URL:     ${QDRANT_URL:-<from env file>}"
log "REDIS_URL:      ${REDIS_URL:-<from env file>}"
log "ML inference:   $ML_INFERENCE_URL"
log "ML compose:     $ML_INFERENCE_COMPOSE_FILE"
log "ML env file:    $ML_INFERENCE_ENV_FILE"
log "Infra compose:  $INFRA_COMPOSE_FILE"
log "Infra env file: $INFRA_ENV_FILE"
log "Wait infra:     $WAIT_FOR_INFRA (${INFRA_WAIT_TIMEOUT_SECONDS}s)"
log "Storefront:     http://0.0.0.0:$STOREFRONT_PORT"
log "Press Ctrl+C to stop all services."

wait -n "${PIDS[@]}" || true
log "One of the services stopped; shutting down the rest."
exit 1
