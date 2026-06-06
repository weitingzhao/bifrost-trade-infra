#!/usr/bin/env bash
# Phase 2B Owner sign-off — Mac backend prep (run in Terminal 1).
# Frontend: Terminal 2 → cd bifrost-trade-frontend && ./dev.sh
# Compare: http://localhost:4000  vs  http://192.168.10.70/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="${ROOT}/../bifrost-trade-frontend"
SESSION="${1:-1}"

cd "$ROOT"

echo "=== Phase 2B sign-off prep (session ${SESSION}) ==="
echo "Prod Legacy UI:  http://192.168.10.70/"
echo "New UI (you):    http://localhost:4000  (run ./dev.sh in bifrost-trade-frontend)"
echo ""

./scripts/switch_cutover_domain.sh all-new
echo "OK  .env.development → all New API (8765–8773)"
echo ""

make sync-dev-config
docker compose -f docker-compose.dev.yml up -d
echo "Waiting for APIs (pip cache may skip reinstall)..."
sleep 5
make dev-health
make verify-wave-a-sessions

case "$SESSION" in
  1)
    echo ""
    echo "--- Session 1: docs ---"
    echo "  New:  http://localhost:4000/settings/api"
    echo "  Prod: http://192.168.10.70/settings/api"
    echo "  Check: 5 tabs, OpenAPI merge, Shutdown actions"
    echo "  Sign:  bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md → Domain 1"
    ;;
  2)
    echo ""
    echo "--- Session 2: portfolio ---"
    echo "  /portfolio/accounts → /positions → /performance → /model-analysis"
    echo "  Sign: PHASE2B_SIGNOFF_MASTER → Domain 5"
    ;;
  3)
    echo ""
    echo "--- Session 3: trading ---"
    echo "  /portfolio/ledger"
    echo "  Sign: Domain 4"
    ;;
  4)
    echo ""
    echo "--- Session 4: strategy ---"
    echo "  /strategy/instances + 6 strategy sub-routes"
    echo "  Sign: Domain 6"
    ;;
  5)
    echo ""
    echo "--- Session 5: research ---"
    echo "  /research/* (8 routes) + Stock Inspector"
    echo "  Sign: Domain 9"
    ;;
  6)
    echo ""
    echo "--- Session 6: massive ---"
    echo "  /settings/coverage/*  /settings/feed/*"
    echo "  Sign: Domain 8"
    ;;
  7)
    echo ""
    echo "--- Session 7: monitor (Wave B) ---"
    echo "  Global strip · /operations/daemon · /settings/api Monitor tab"
    echo "  /strategy/allocations (active strategy from monitor)"
    echo "  Sign: Domain 2 — degraded OK if IB/ingestor offline (note in Remarks)"
    ;;
  8)
    echo ""
    echo "--- Session 8: market (Wave B) ---"
    echo "  /market/live — quotes table + SSE"
    echo "  Sign: Domain 3 — needs ib-ingestor → Redis for live quotes"
    ;;
  9)
    echo ""
    echo "--- Session 9: ops (Wave B) ---"
    echo "  /operations/celery · /settings/socket"
    echo "  Sign: Domain 7 — celery-worker + ingest health"
    ;;
  *)
    echo "Unknown session: $SESSION (use 1–9)"
    exit 1
    ;;
esac

echo ""
echo "Terminal 2:"
echo "  cd ${FRONTEND} && ./dev.sh"
echo ""
echo "After UI pass: check Pass + Owner date in PHASE2B_SIGNOFF_MASTER.md"
