#!/usr/bin/env bash
# Agent-side API smoke per Phase 2B domain (curl health endpoints on New stack).
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
fail=0
ok() { echo -e "${GREEN}OK${NC}  $*"; }
bad() { echo -e "${RED}FAIL${NC}  $*"; fail=1; }

check() {
  local name="$1" url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$url" 2>/dev/null) || code="000"
  if [[ "$code" == "200" || "$code" == "503" ]]; then
    ok "${name} ${url} (${code})"
  else
    bad "${name} ${url} (${code})"
  fi
}

echo "=== Phase 2B New API domain smoke ==="
check "2B.1 docs"     "http://127.0.0.1:8767/research/docs/health"
check "2B.2 monitor"  "http://127.0.0.1:8765/status"
check "2B.2 market"   "http://127.0.0.1:8772/health"
check "2B.3 trading"  "http://127.0.0.1:8769/health"
check "2B.3 portfolio" "http://127.0.0.1:8771/health"
check "2B.3 strategy" "http://127.0.0.1:8770/health"
check "2B.4 ops"      "http://127.0.0.1:8768/health"
check "2B.4 massive"  "http://127.0.0.1:8766/research/massive/health"
check "2B.4 research" "http://127.0.0.1:8773/health"

if [[ "$fail" -ne 0 ]]; then
  echo "Domain API smoke failed — ensure: make dev && make dev-health"
  exit 1
fi
echo "All domain API smoke checks passed."
