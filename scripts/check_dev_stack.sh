#!/usr/bin/env bash
# Probe local dev stack health (postgres, redis, 9 API domains).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "${ROOT}/.env" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${ROOT}/.env"
  set +a
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

fail=0
ok() { echo -e "${GREEN}OK${NC}  $*"; }
bad() { echo -e "${RED}FAIL${NC}  $*"; fail=1; }

PG_HOST="${POSTGRES_HOST:-127.0.0.1}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-bifrost}"
PG_DB="${POSTGRES_DB:-bifrost_dev}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"

# host.docker.internal / compose service names → probe from Mac host via loopback
resolve_probe_host() {
  local h="$1"
  case "$h" in
    host.docker.internal|postgres|redis|127.0.0.1|localhost) echo "127.0.0.1" ;;
    *) echo "$h" ;;
  esac
}
PG_PROBE_HOST="$(resolve_probe_host "$PG_HOST")"
REDIS_PROBE_HOST="$(resolve_probe_host "$REDIS_HOST")"

if command -v pg_isready >/dev/null 2>&1; then
  if pg_isready -h "$PG_PROBE_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
    ok "postgres ${PG_HOST}:${PG_PORT}/${PG_DB}"
  else
    bad "postgres ${PG_HOST}:${PG_PORT}/${PG_DB}"
  fi
else
  echo "SKIP postgres (pg_isready not installed)"
fi

if command -v redis-cli >/dev/null 2>&1; then
  if redis-cli -h "$REDIS_PROBE_HOST" -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; then
    ok "redis ${REDIS_HOST}:${REDIS_PORT}"
  else
    bad "redis ${REDIS_HOST}:${REDIS_PORT}"
  fi
else
  echo "SKIP redis (redis-cli not installed)"
fi

api_down_hint=0
API_WAIT_SECS="${API_WAIT_SECS:-300}"
API_RETRY_INTERVAL="${API_RETRY_INTERVAL:-10}"

wait_for_first_api() {
  local elapsed=0
  while [[ "$elapsed" -lt "$API_WAIT_SECS" ]]; do
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "http://127.0.0.1:8765/status" 2>/dev/null) || code="000"
    if [[ "$code" == "200" || "$code" == "503" ]]; then
      [[ "$elapsed" -gt 0 ]] && echo "APIs ready after ${elapsed}s (pip install on first start can take 1–3 min)."
      return 0
    fi
    if [[ "$elapsed" -eq 0 ]]; then
      echo "Waiting for API containers (editable pip install on first start)..."
    fi
    sleep "$API_RETRY_INTERVAL"
    elapsed=$((elapsed + API_RETRY_INTERVAL))
  done
  echo "APIs still not listening after ${API_WAIT_SECS}s."
  return 1
}

check_http() {
  local name="$1"
  local url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$url" 2>/dev/null) || code="000"
  if [[ "$code" == "200" || "$code" == "503" ]]; then
    ok "${name} ${url} (${code})"
  else
    bad "${name} ${url} (${code})"
    if [[ "$code" == "000" || "$code" == "000000" ]]; then
      api_down_hint=1
    fi
  fi
}

if ! wait_for_first_api; then
  api_down_hint=1
fi

# monitor uses /status; others use /health or prefixed health
check_http "api-monitor"   "http://127.0.0.1:8765/status"
check_http "api-massive"   "http://127.0.0.1:8766/research/massive/health"
check_http "api-docs"      "http://127.0.0.1:8767/research/docs/health"
check_http "api-ops"       "http://127.0.0.1:8768/health"
check_http "api-trading"   "http://127.0.0.1:8769/health"
check_http "api-strategy"  "http://127.0.0.1:8770/health"
check_http "api-portfolio" "http://127.0.0.1:8771/health"
check_http "api-market"    "http://127.0.0.1:8772/health"
check_http "api-research"  "http://127.0.0.1:8773/health"

if [[ "$fail" -ne 0 ]]; then
  if [[ "$api_down_hint" -eq 1 ]]; then
    echo ""
    echo "Hint: API ports not listening. Start the dev stack first:"
    echo "  cd bifrost-trade-infra && make dev-build && make dev"
    echo "Then inspect failures: docker compose -f docker-compose.dev.yml ps -a"
    echo "                      docker compose -f docker-compose.dev.yml logs api-monitor --tail=50"
  fi
  echo "Dev stack health check failed."
  exit 1
fi
echo "Dev stack health check passed."
