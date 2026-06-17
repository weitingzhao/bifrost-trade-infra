#!/usr/bin/env bash
# Local Prod Final — mechanical gate (L1 in Ops Console → Program → Deploy Mainline)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

fail=0
ok() { echo -e "${GREEN}OK${NC}  $*"; }
bad() { echo -e "${RED}FAIL${NC}  $*"; fail=1; }
skip() { echo -e "${YELLOW}SKIP${NC}  $*"; }

echo "=== Local Prod Final gate ==="

chmod +x scripts/check_prod_stack.sh
if ./scripts/check_prod_stack.sh; then
  ok "make prod-health / check_prod_stack"
else
  bad "prod stack health"
fi

if make verify-2c-a1; then
  ok "verify-2c-a1"
else
  bad "verify-2c-a1"
fi

code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://127.0.0.1/ 2>/dev/null) || code="000"
if [[ "$code" == "200" ]]; then
  ok "SPA http://127.0.0.1/ ($code)"
else
  bad "SPA http://127.0.0.1/ ($code)"
fi

PLATFORM_URL="${PLATFORM_API_URL:-http://127.0.0.1:8780}"
if curl -sf "${PLATFORM_URL}/health" >/dev/null 2>&1; then
  ok "bifrost-platform-api ${PLATFORM_URL}/health"
  if curl -sf "${PLATFORM_URL}/api/v1/topology?env=prod" >/dev/null 2>&1; then
    ok "platform topology (prod)"
  else
    bad "platform topology (prod)"
  fi
else
  skip "bifrost-platform-api not running (${PLATFORM_URL}) — start: cd ../bifrost-platform && ./scripts/run_platform.py"
fi

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "Local Prod Final gate FAILED. See Ops Console → Program → Deploy Mainline"
  exit 1
fi

echo ""
echo "Local Prod Final gate PASSED (Owner L2/L3/L4 still required)."
