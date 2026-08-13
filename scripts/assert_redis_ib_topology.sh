#!/usr/bin/env bash
# P9 — Assert Trade DEV uses ExternalName redis-ib → data NS.
# Forbids redis-live-prod → redis-dev clone as a Live path (D-IL3).
set -euo pipefail

DRY_RUN=0
NS="${TRADE_DEV_NS:-bifrost-dev}"
KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="${ROOT}/../bifrost-platform-plugin/k8s/external-names/bifrost-dev/redis-ib.yaml"
EXPECTED_EXTERNAL="redis-ib.data.svc.cluster.local"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'
fail=0
ok() { echo -e "${GREEN}OK${NC}  $*"; }
warn() { echo -e "${YELLOW}WARN${NC}  $*"; }
bad() { echo -e "${RED}FAIL${NC}  $*"; fail=1; }

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --help|-h)
      echo "Usage: $0 [--dry-run]"
      echo "  Asserts ExternalName redis-ib for ${NS}; refuses redis-live-prod dump guidance."
      exit 0
      ;;
  esac
done

echo "=== assert redis-ib topology (ns=${NS} dry_run=${DRY_RUN}) ==="
echo "FORBIDDEN: clone/dump redis-live-prod → redis-dev for Market Live (D-IL3)."

if [[ -f "$MANIFEST" ]]; then
  if grep -q "externalName:[[:space:]]*${EXPECTED_EXTERNAL}" "$MANIFEST"; then
    ok "manifest ExternalName → ${EXPECTED_EXTERNAL}"
  else
    bad "manifest missing externalName ${EXPECTED_EXTERNAL}: ${MANIFEST}"
  fi
  if grep -qiE 'redis-live-prod.*(redis-dev|clone|dump)|dump.*redis-live-prod' "$MANIFEST"; then
    bad "manifest must not describe redis-live-prod → redis-dev clone"
  else
    ok "manifest has no redis-live-prod → redis-dev clone path"
  fi
else
  bad "manifest not found: ${MANIFEST}"
fi

# Contract doc must state the forbid rule
CONTRACT="${ROOT}/docs/TRADE_DEV_INNER_LOOP.md"
if [[ -f "$CONTRACT" ]] && grep -qiE 'Forbidden:.*redis-live-prod|do not dump.*redis-live-prod|Forbidden.*clone.*redis-live-prod' "$CONTRACT"; then
  ok "contract forbids redis-live-prod → redis-dev dump"
else
  bad "contract missing redis-live-prod forbid clause: ${CONTRACT}"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  warn "dry-run: skipping live kubectl checks"
  if [[ "$fail" -ne 0 ]]; then
    echo "assert_redis_ib_topology dry-run FAILED"
    exit 1
  fi
  echo "assert_redis_ib_topology dry-run PASSED"
  exit 0
fi

if [[ ! -f "$KUBECONFIG" ]]; then
  warn "kubeconfig missing (${KUBECONFIG}) — live Service check skipped"
else
  if ! command -v kubectl >/dev/null 2>&1; then
    warn "kubectl not found — live Service check skipped"
  else
    typ=$(kubectl --kubeconfig="$KUBECONFIG" -n "$NS" get svc redis-ib -o jsonpath='{.spec.type}' 2>/dev/null || true)
    ext=$(kubectl --kubeconfig="$KUBECONFIG" -n "$NS" get svc redis-ib -o jsonpath='{.spec.externalName}' 2>/dev/null || true)
    if [[ "$typ" == "ExternalName" && "$ext" == "$EXPECTED_EXTERNAL" ]]; then
      ok "live ${NS}/svc/redis-ib ExternalName → ${ext}"
    elif [[ -z "$typ" ]]; then
      bad "live ${NS}/svc/redis-ib not found (apply external-names)"
    else
      bad "live ${NS}/svc/redis-ib type=${typ} externalName=${ext} (want ExternalName ${EXPECTED_EXTERNAL})"
    fi
  fi
fi

if [[ "$fail" -ne 0 ]]; then
  echo "assert_redis_ib_topology FAILED"
  exit 1
fi
echo "assert_redis_ib_topology PASSED"
exit 0
