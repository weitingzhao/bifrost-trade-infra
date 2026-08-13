#!/usr/bin/env bash
# P6 — Post-clone consumer bounce guidance for bifrost-dev api-* only.
# Default: print MCP/Console steps (safe). Use --execute only with explicit intent.
set -euo pipefail

EXECUTE=0
NS="${TRADE_DEV_NS:-bifrost-dev}"
PLATFORM_BASE="${PLATFORM_API_BASE:-http://127.0.0.1:8780}"

DEPLOYMENTS=(
  api-monitor
  api-market
  api-trading
  api-strategy
  api-portfolio
  api-ops
  api-docs
  api-research
)

for arg in "$@"; do
  case "$arg" in
    --execute) EXECUTE=1 ;;
    --dry-run)
      EXECUTE=0
      ;;
    --help|-h)
      echo "Usage: $0 [--dry-run|--execute]"
      echo "  Documents / optionally restarts DEV Trade API deployments after data clone."
      echo "  Prefer Platform MCP: rollout_restart_deployment (namespace=${NS})."
      exit 0
      ;;
  esac
done

echo "=== post-clone bounce (ns=${NS} execute=${EXECUTE}) ==="
echo "Scope: DEV only. Never bounce bifrost-prod / bifrost-stg from this script."
echo
echo "Recommended (MCP / Console):"
for d in "${DEPLOYMENTS[@]}"; do
  echo "  - rollout_restart_deployment name=${d} namespace=${NS}"
done
echo
echo "Or: Ops Console Cluster → select ${NS} → Restart deployment (api-*)."
echo "Platform API base (local): ${PLATFORM_BASE}"

if [[ "$EXECUTE" -eq 0 ]]; then
  echo
  echo "dry-run / guidance-only complete (no restart). Pass --execute to call kubectl rollout restart."
  exit 0
fi

KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
if [[ ! -f "$KUBECONFIG" ]]; then
  echo "ERROR: kubeconfig missing: ${KUBECONFIG}" >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "ERROR: kubectl not found" >&2
  exit 1
fi

# Safety: refuse non-dev namespaces
if [[ "$NS" != "bifrost-dev" ]]; then
  echo "ERROR: refusing execute outside bifrost-dev (got ${NS})" >&2
  exit 1
fi

for d in "${DEPLOYMENTS[@]}"; do
  if kubectl --kubeconfig="$KUBECONFIG" -n "$NS" get deploy "$d" >/dev/null 2>&1; then
    echo "rollout restart deploy/${d}"
    kubectl --kubeconfig="$KUBECONFIG" -n "$NS" rollout restart "deploy/${d}"
  else
    echo "skip missing deploy/${d}"
  fi
done

echo "bounce_dev_apis_after_clone execute complete"
exit 0
