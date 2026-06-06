#!/usr/bin/env bash
# Probe production compose stack: LAN PG/Redis + 9 APIs via nginx same-origin paths.
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

NGINX_BASE="${PROD_NGINX_URL:-http://127.0.0.1}"
PG_HOST="${POSTGRES_HOST:-192.168.10.80}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-bifrost}"
PG_DB="${POSTGRES_DB:-bifrost_prod}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"

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

API_WAIT_SECS="${API_WAIT_SECS:-300}"
API_RETRY_INTERVAL="${API_RETRY_INTERVAL:-10}"

wait_for_nginx() {
  local elapsed=0
  while [[ "$elapsed" -lt "$API_WAIT_SECS" ]]; do
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "${NGINX_BASE}/" 2>/dev/null) || code="000"
    if [[ "$code" == "200" ]]; then
      [[ "$elapsed" -gt 0 ]] && echo "nginx ready after ${elapsed}s."
      return 0
    fi
    if [[ "$elapsed" -eq 0 ]]; then
      echo "Waiting for prod stack (nginx + API containers)..."
    fi
    sleep "$API_RETRY_INTERVAL"
    elapsed=$((elapsed + API_RETRY_INTERVAL))
  done
  echo "nginx still not ready after ${API_WAIT_SECS}s."
  return 1
}

check_http() {
  local name="$1"
  local url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" 2>/dev/null) || code="000"
  if [[ "$code" == "200" || "$code" == "503" ]]; then
    ok "${name} ${url} (${code})"
  else
    bad "${name} ${url} (${code})"
  fi
}

if ! wait_for_nginx; then
  bad "nginx ${NGINX_BASE}/"
fi

check_http "nginx-spa"      "${NGINX_BASE}/"
check_http "api-monitor"    "${NGINX_BASE}/api/monitor/status"
check_http "api-massive"    "${NGINX_BASE}/api/massive/research/massive/health"
check_http "api-docs"       "${NGINX_BASE}/api/docs/research/docs/health"
check_http "api-ops"        "${NGINX_BASE}/api/ops/health"
check_http "api-trading"    "${NGINX_BASE}/api/trading/health"
check_http "api-strategy"   "${NGINX_BASE}/api/strategy/health"
check_http "api-portfolio"  "${NGINX_BASE}/api/portfolio/health"
check_http "api-market"     "${NGINX_BASE}/api/market/health"
check_http "api-research"   "${NGINX_BASE}/api/research/health"

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "Hint: start prod stack:"
  echo "  cd bifrost-trade-infra && make prod-preflight"
  echo "Inspect: docker compose ps -a && docker compose logs nginx api-monitor --tail=40"
  echo "Prod stack health check failed."
  exit 1
fi
echo "Prod stack health check passed."
