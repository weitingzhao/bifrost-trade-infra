#!/usr/bin/env bash
# Phase ④ — DEV cutover: apps → bifrost-postgres-rw.data.svc; remove in-ns postgres.
#
# Usage:
#   make k3s-cutover-dev-data-layer-phase3
#   SKIP_MIGRATE=1 make k3s-cutover-dev-data-layer-phase3
#
# Prerequisite: make k3s-verify-data-layer-phase2-stg
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

DEV_NAMESPACE="${DEV_NAMESPACE:-bifrost-dev}"
SKIP_MIGRATE="${SKIP_MIGRATE:-0}"
RUN_DB_INIT="${RUN_DB_INIT:-0}"

remove_embedded_postgres() {
  echo "==> Remove embedded postgres (deployment/service/PVC)"
  kubectl delete deployment/postgres service/postgres pvc/postgres-data \
    -n "${DEV_NAMESPACE}" --ignore-not-found --wait=true
}

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Phase ④ DEV cutover (CNPG @ data NS)"

echo "==> 1/6 Verify STG phase ③ (prerequisite)"
"${ROOT}/scripts/k3s/verify-data-layer-phase2-stg.sh"

if [[ "${SKIP_MIGRATE}" != "1" ]]; then
  echo "==> 2/6 Migrate embedded postgres → CNPG"
  "${ROOT}/scripts/k3s/migrate-dev-postgres-to-cnpg.sh"
  primary="$(kubectl get cluster bifrost-postgres -n data -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
  if [[ -n "${primary}" ]]; then
    echo "==> Grant bifrost role on ${DEV_NAMESPACE} database (post-restore)"
    kubectl exec -n data "${primary}" -- psql -U postgres -d bifrost_dev -c \
      "GRANT ALL ON ALL TABLES IN SCHEMA public TO bifrost; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO bifrost; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO bifrost;" \
      >/dev/null
  fi
else
  echo "==> 2/6 SKIP_MIGRATE=1 — skip data copy"
fi

echo "==> 3/6 Sync dev overlay config (IB from .env; postgres host stays CNPG)"
if [[ -f "${ROOT}/.env" ]]; then
  "${ROOT}/scripts/sync_dev_overlay_config.sh"
else
  echo "No .env — using k8s/overlays/dev/config/config.dev.yaml as-is"
fi

echo "==> 4/6 Apply bifrost-dev overlay (CNPG config; no embedded postgres)"
kubectl apply -k "${ROOT}/k8s/overlays/dev"
remove_embedded_postgres
kubectl apply -k "${ROOT}/k8s/overlays/dev"

echo "==> 5/6 Rollout restart (reload bifrost-config → CNPG endpoint)"
kubectl rollout restart deployment -n "${DEV_NAMESPACE}"
kubectl rollout status deployment/nginx -n "${DEV_NAMESPACE}" --timeout=600s
kubectl rollout status deployment/api-monitor -n "${DEV_NAMESPACE}" --timeout=600s

echo "==> Ensure CNPG schema (db_refresh_schema via api-monitor)"
kubectl exec -n "${DEV_NAMESPACE}" deploy/api-monitor -- \
  python /build/bifrost-trade-core/scripts/db/db_refresh_schema.py

if [[ "${RUN_DB_INIT}" == "1" ]]; then
  echo "==> db-init-dev Job against CNPG"
  kubectl delete job db-init-dev -n "${DEV_NAMESPACE}" --ignore-not-found
  kubectl apply -k "${ROOT}/k8s/overlays/dev"
  kubectl wait --for=condition=complete job/db-init-dev -n "${DEV_NAMESPACE}" --timeout=600s
fi

echo "==> 6/6 Verify phase ④"
"${ROOT}/scripts/k3s/verify-data-layer-phase3-dev.sh"

echo ""
echo "Phase ④ DEV cutover complete."
echo "  PG RW: bifrost-postgres-rw.data.svc.cluster.local:5432/bifrost_dev"
echo "  Gateway: http://192.168.10.73:30882"
echo "  verify: make k3s-verify-data-layer-phase3-dev"
echo ""
echo "NOTE: bifrost-dev is not Argo-managed; commit k8s/overlays/dev to git."
