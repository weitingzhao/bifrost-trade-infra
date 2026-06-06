#!/usr/bin/env bash
# Phase 2B acceptance preflight — LAN PG/Redis, dev stack, celery-worker.
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
warn() { echo -e "${YELLOW}WARN${NC}  $*"; }

echo "=== Phase 2B dev preflight ==="

if [[ ! -f .env ]]; then
  bad ".env missing — run: make ensure-env"
else
  ok ".env present"
fi

echo ""
echo "--- sync config + start stack ---"
make sync-dev-config
make dev

echo ""
echo "--- infrastructure ---"
chmod +x scripts/check_dev_stack.sh
if ./scripts/check_dev_stack.sh; then
  ok "dev-health passed"
else
  bad "dev-health failed (APIs may still be pip-installing — retry in 2–3 min)"
fi

echo ""
echo "--- celery-worker (ops / massive / research) ---"
if docker compose -f docker-compose.dev.yml ps celery-worker --format '{{.Status}}' 2>/dev/null | grep -qi up; then
  ok "celery-worker Up"
else
  bad "celery-worker not Up"
fi

echo ""
echo "--- optional: frontend dev server ---"
# --max-time: avoid hang when :5173 accepts TCP but Vite/Docker frontend does not respond
if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 http://127.0.0.1:5173/ 2>/dev/null | grep -qE '200|304'; then
  ok "Vite http://127.0.0.1:5173"
else
  warn "Vite not responding on 5173 (optional) — use host dev server: cd ../bifrost-trade-frontend && npm run dev"
  warn "Ignore if backend checks above passed; Docker compose frontend container is not required for Phase 2B."
fi

echo ""
echo "--- BIFROST_DEV_INFRA ---"
if [[ -f .env ]]; then
  # shellcheck disable=SC1090
  source .env
  mode="${BIFROST_DEV_INFRA:-host}"
  if [[ "$mode" == "host" ]]; then
    ok "BIFROST_DEV_INFRA=host (PG ${POSTGRES_HOST:-?} / Redis ${REDIS_HOST:-?})"
  else
    warn "BIFROST_DEV_INFRA=${mode} — ensure this is intentional"
  fi
fi

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "Preflight failed. See hints above."
  exit 1
fi
echo ""
echo "Preflight passed. Owner: open Legacy + New UI for strict single-domain cutover."
echo "  ./scripts/switch_cutover_domain.sh <domain> legacy|new"
exit 0
