#!/usr/bin/env bash
# Phase ⑤ — PROD cutover: apps → bifrost-postgres-rw.data.svc; retire .80 for K3s prod stack.
#
# Usage:
#   make k3s-cutover-prod-data-layer-phase4
#   SKIP_MIGRATE=1 make k3s-cutover-prod-data-layer-phase4
#
# Prerequisite: make k3s-verify-data-layer-phase3-dev
# Rollback: legacy .80 decommissioned 2026-06-29 — no live fallback. Recover from the
#           final dump (db-backups/final-legacy-2026-06-29/options_db.dump) into CNPG.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

PROD_NAMESPACE="${PROD_NAMESPACE:-bifrost-prod}"
SKIP_MIGRATE="${SKIP_MIGRATE:-0}"
SKIP_DEV_VERIFY="${SKIP_DEV_VERIFY:-0}"
PAUSE_ARGO="${PAUSE_ARGO:-1}"

pause_argo_prod() {
  if [[ "${PAUSE_ARGO}" != "1" ]]; then
    return 0
  fi
  if kubectl get application bifrost-prod -n cicd >/dev/null 2>&1; then
    echo "==> Pause Argo CD auto-sync for bifrost-prod"
    kubectl patch application bifrost-prod -n cicd --type merge \
      -p '{"spec":{"syncPolicy":{"automated":null}}}' >/dev/null
  fi
}

remove_embedded_postgres() {
  echo "==> Remove in-cluster postgres objects (deployment/service/PVC)"
  kubectl delete deployment/postgres service/postgres pvc/postgres-data \
    -n "${PROD_NAMESPACE}" --ignore-not-found --wait=true
}

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Phase ⑤ PROD cutover (CNPG @ data NS)"
pause_argo_prod

echo "==> 1/6 Verify DEV phase ④ (prerequisite)"
if [[ "${SKIP_DEV_VERIFY}" == "1" ]]; then
  echo "    SKIP_DEV_VERIFY=1 — skip (dev PG already on CNPG)"
else
  "${ROOT}/scripts/k3s/verify-data-layer-phase3-dev.sh"
fi

if [[ "${SKIP_MIGRATE}" != "1" ]]; then
  echo "==> 2/6 Migrate legacy .80 postgres → CNPG bifrost_prod"
  "${ROOT}/scripts/k3s/migrate-prod-postgres-to-cnpg.sh"
else
  echo "==> 2/6 SKIP_MIGRATE=1 — skip data copy"
fi

echo "==> 3/6 Sync prod overlay config (IB/massive from .env; postgres stays CNPG)"
if [[ -f "${ROOT}/.env" ]]; then
  "${ROOT}/scripts/sync_prod_overlay_config.sh"
else
  echo "No .env — using k8s/overlays/prod/config/config.prod.yaml as-is"
fi

echo "==> 4/6 Apply bifrost-prod overlay"
kubectl apply -k "${ROOT}/k8s/overlays/prod"
remove_embedded_postgres
kubectl apply -k "${ROOT}/k8s/overlays/prod"

echo "==> 5/6 Rollout restart (reload bifrost-config → CNPG)"
kubectl rollout restart deployment -n "${PROD_NAMESPACE}"
kubectl rollout status deployment/nginx -n "${PROD_NAMESPACE}" --timeout=900s
kubectl rollout status deployment/api-monitor -n "${PROD_NAMESPACE}" --timeout=900s
kubectl rollout status deployment/daemon -n "${PROD_NAMESPACE}" --timeout=900s

if [[ "${SKIP_MIGRATE}" == "1" ]]; then
  echo "==> Fix CNPG ownership + light schema touch (SKIP_MIGRATE path)"
  "${ROOT}/scripts/k3s/fix-cnpg-db-ownership.sh" bifrost_prod
  kubectl exec -n "${PROD_NAMESPACE}" deploy/api-monitor -- \
    python /build/bifrost-trade-core/scripts/db/db_refresh_schema.py \
    || echo "WARN: db_refresh_schema partial failure (stock_day timeout is OK post-migrate)"
fi

echo "==> 6/6 Verify phase ⑤"
"${ROOT}/scripts/k3s/verify-data-layer-phase4-prod.sh"

echo ""
echo "Phase ⑤ PROD cutover complete."
echo "  PG RW: bifrost-postgres-rw.data.svc.cluster.local:5432/bifrost_prod"
echo "  Gateway: http://192.168.10.70:30881"
echo "  verify: make k3s-verify-data-layer-phase4-prod"
echo ""
echo "Rollback (if needed): legacy .80 decommissioned 2026-06-29 — no live fallback."
echo "  1. Restore db-backups/final-legacy-2026-06-29/options_db.dump into a fresh CNPG database"
echo "  2. Patch config.prod.yaml postgres.database to that restored DB; kubectl apply -k k8s/overlays/prod"
echo "  3. kubectl rollout restart deployment -n bifrost-prod"
echo ""
echo "IMPORTANT: Push bifrost-trade-infra to GitHub, then re-enable Argo auto-sync:"
echo "  kubectl patch application bifrost-prod -n cicd --type merge \\"
echo "    -p '{\"spec\":{\"syncPolicy\":{\"automated\":{\"prune\":true,\"selfHeal\":true}}}}'"
