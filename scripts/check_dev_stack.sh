#!/usr/bin/env bash
# Probe local dev stack health (postgres, redis, 9 API domains).
set -euo pipefail

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

if command -v pg_isready >/dev/null 2>&1; then
  if pg_isready -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" >/dev/null 2>&1; then
    ok "postgres ${PG_HOST}:${PG_PORT}/${PG_DB}"
  else
    bad "postgres ${PG_HOST}:${PG_PORT}/${PG_DB}"
  fi
else
  echo "SKIP postgres (pg_isready not installed)"
fi

if command -v redis-cli >/dev/null 2>&1; then
  if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null | grep -q PONG; then
    ok "redis ${REDIS_HOST}:${REDIS_PORT}"
  else
    bad "redis ${REDIS_HOST}:${REDIS_PORT}"
  fi
else
  echo "SKIP redis (redis-cli not installed)"
fi

check_http() {
  local name="$1"
  local url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 3 "$url" || echo "000")
  if [[ "$code" == "200" || "$code" == "503" ]]; then
    ok "${name} ${url} (${code})"
  else
    bad "${name} ${url} (${code})"
  fi
}

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
  echo "Dev stack health check failed."
  exit 1
fi
echo "Dev stack health check passed."
