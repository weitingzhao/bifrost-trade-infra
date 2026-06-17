#!/usr/bin/env bash
# Local Prod Final — Owner session guide (browser sign-off on http://localhost/)
# Usage:
#   ./scripts/local_prod_final_owner.sh prep     # ensure stack + L1 gate
#   ./scripts/local_prod_final_owner.sh 0        # Session 0 final
#   ./scripts/local_prod_final_owner.sh 1|2|3|8  # Sessions 1,2,3,8 final
#   ./scripts/local_prod_final_owner.sh platform # optional bifrost-platform
#   ./scripts/local_prod_final_owner.sh all      # print full order
#
# Sign rows in: Ops Console → Program → Deploy Mainline (L2.x) + PHASE2C_SIGNOFF_MASTER.md (reference)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${SIGNOFF_BASE_URL:-http://localhost}"
LEGACY="${LEGACY_BASE_URL:-http://192.168.10.70}"
SESSION="${1:-all}"

open_url() {
  local path="$1"
  if command -v open >/dev/null 2>&1; then
    open "${BASE}${path}" 2>/dev/null || true
  fi
  echo "  New:    ${BASE}${path}"
  echo "  Legacy: ${LEGACY}${path}  (read-only compare)"
}

prep() {
  cd "$ROOT"
  echo "=== Local Prod Final — prep (L1) ==="
  echo "If stack is down, run: make prod-preflight-local  (or make prod-up-local)"
  echo ""
  docker compose ps 2>/dev/null | head -20 || true
  echo ""
  ./scripts/local_prod_final_gate.sh
}

session_0() {
  echo "=== Session 0 (Final) — Stack + API Health → L2.7 ==="
  echo "Checks: SPA loads; /settings/api 5 tabs; Network uses /api/* (not :8765 direct)"
  echo ""
  open_url "/"
  open_url "/settings/api"
  echo ""
  echo "Optional curls:"
  echo "  curl -s ${BASE}/api/monitor/status | head -c 120"
  echo "  curl -s ${BASE}/api/ops/health | head -c 120"
  echo ""
  echo "Sign: Deploy Mainline (deployMainlineCatalog.ts) → L2.7 (Dev/Prod dual-column red = known gap, OK)"
}

session_1() {
  echo "=== Session 1 (Final) — Monitor → L2.1 + L2.2 (daemon overview) ==="
  echo "Checks: Global strip lamps; sidebar nav lamps; daemon FSM visible"
  echo ""
  open_url "/"
  open_url "/operations/daemon"
  open_url "/strategy/allocations"
  echo ""
  echo "Sign: Deploy Mainline (deployMainlineCatalog.ts) → L2.1, L2.2 (partial)"
}

session_2() {
  echo "=== Session 2 (Final) — Market Live → L2.5 ==="
  echo "Checks: quotes table; SSE EventStream in Network tab; category groups"
  echo ""
  open_url "/market/live"
  echo ""
  echo "Sign: Deploy Mainline (deployMainlineCatalog.ts) → L2.5"
}

session_3() {
  echo "=== Session 3 (Final) — Portfolio → L2.6 ==="
  echo "Checks: positions table loads; optional accounts / performance spot-check"
  echo ""
  open_url "/portfolio/positions"
  open_url "/portfolio/accounts"
  echo ""
  echo "Sign: Deploy Mainline (deployMainlineCatalog.ts) → L2.6"
}

session_8() {
  echo "=== Session 8 (Final) — Ops Celery + Socket + Daemon control → L2.2–L2.4 ==="
  echo "Checks: Celery 8 tables + worker instances; Socket ingest + Connection; Daemon process control"
  echo "Needs: Ops token on Celery/Socket pages (operator/admin from config.dev.yaml)"
  echo ""
  open_url "/operations/celery"
  open_url "/settings/socket"
  open_url "/operations/daemon"
  echo ""
  echo "Optional:"
  echo "  cd bifrost-trade-infra && make verify-2c-a1"
  echo ""
  echo "Sign: Deploy Mainline (deployMainlineCatalog.ts) → L2.2, L2.3, L2.4"
}

session_platform() {
  echo "=== Optional — bifrost-platform Console → L2.8 ==="
  echo "  cd ../bifrost-platform && ./scripts/run_platform.py"
  echo "  open http://127.0.0.1:5180  (Topology + Matrix dev/prod)"
  echo ""
  echo "Sign: Deploy Mainline (deployMainlineCatalog.ts) → L2.8"
}

print_all() {
  cat <<'EOF'
=== Local Prod Final — recommended Owner order ===

1) prep
   ./scripts/local_prod_final_owner.sh prep

2) Sessions (browser on http://localhost/)
   ./scripts/local_prod_final_owner.sh 0
   ./scripts/local_prod_final_owner.sh 1
   ./scripts/local_prod_final_owner.sh 2
   ./scripts/local_prod_final_owner.sh 3
   ./scripts/local_prod_final_owner.sh 8

3) Optional platform
   ./scripts/local_prod_final_owner.sh platform

4) Decisions L3 (D1–D5) + L4 sign in docs/Deploy Mainline (deployMainlineCatalog.ts)

5) Next phase: PHASE2C_SIGNOFF_MASTER.md §2C-B (Linux .70)

EOF
}

case "$SESSION" in
  prep) prep ;;
  0) session_0 ;;
  1) session_1 ;;
  2) session_2 ;;
  3) session_3 ;;
  8) session_8 ;;
  platform) session_platform ;;
  all) print_all ;;
  *)
    echo "Unknown session: $SESSION"
    echo "Use: prep | 0 | 1 | 2 | 3 | 8 | platform | all"
    exit 1
    ;;
esac
