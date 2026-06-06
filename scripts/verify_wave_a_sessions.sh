#!/usr/bin/env bash
# Agent preflight for Phase 2B Wave A Owner sessions (key HTTP endpoints per domain).
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
fail=0
ok() { echo -e "${GREEN}OK${NC}  $*"; }
bad() { echo -e "${RED}FAIL${NC}  $*"; fail=1; }

check() {
  local label="$1" url="$2" expect="${3:-200}"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 8 "$url" 2>/dev/null) || code="000"
  if [[ "$code" == "$expect" || ( "$expect" == "2xx" && "$code" =~ ^2 ) ]]; then
    ok "${label} (${code}) ${url}"
  elif [[ "$expect" == "2xx_or_422" && ( "$code" =~ ^2 || "$code" == "422" ) ]]; then
    ok "${label} (${code}) ${url}"
  elif [[ "$expect" == "exists" && ( "$code" =~ ^2 || "$code" == "405" || "$code" == "422" ) ]]; then
    ok "${label} (${code}) ${url}"
  else
    bad "${label} (${code}) ${url}"
  fi
}

echo "=== Wave A session API preflight ==="

echo ""
echo "--- Session 1: docs ---"
check "docs health" "http://127.0.0.1:8767/research/docs/health"
check "docs swagger" "http://127.0.0.1:8767/research/docs/docs" "2xx"

echo ""
echo "--- Session 2: portfolio (monitor cross-read for accounts/positions) ---"
check "monitor status" "http://127.0.0.1:8765/status"
check "portfolio health" "http://127.0.0.1:8771/health"
check "position-categories" "http://127.0.0.1:8771/position-categories" "2xx"

echo ""
echo "--- Session 3: trading ---"
check "trading health" "http://127.0.0.1:8769/health"
check "executions list" "http://127.0.0.1:8769/executions?limit=10" "2xx"

echo ""
echo "--- Session 4: strategy ---"
check "strategy health" "http://127.0.0.1:8770/health"
check "strategy instances" "http://127.0.0.1:8770/strategies/instances?limit=5" "2xx"

echo ""
echo "--- Session 5: research ---"
check "research health" "http://127.0.0.1:8773/health"
check "data readiness" "http://127.0.0.1:8773/research/data/readiness/summary" "2xx"
check "sepa phase1 route" "http://127.0.0.1:8773/research/screening/sepa/phase1" "exists"

echo ""
echo "--- Session 6: massive ---"
check "massive health" "http://127.0.0.1:8766/research/massive/health"
check "contracts-coverage" "http://127.0.0.1:8766/research/massive/contracts-coverage" "2xx_or_422"

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "Wave A API preflight had failures."
  exit 1
fi
echo ""
echo "Wave A API preflight passed."
