#!/usr/bin/env bash
# Phase ③ — STG cutover: apps → bifrost-postgres-rw.data.svc; remove in-ns postgres.
#
# Usage:
#   make k3s-cutover-stg-data-layer-phase2
#   SKIP_MIGRATE=1 make k3s-cutover-stg-data-layer-phase2  # config-only (empty CNPG DB)
#
# Prerequisite: make k3s-verify-data-layer-phase1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
SKIP_MIGRATE="${SKIP_MIGRATE:-0}"
RUN_DB_INIT="${RUN_DB_INIT:-0}"
PAUSE_ARGO="${PAUSE_ARGO:-1}"

pause_argo_stg() {
  if [[ "${PAUSE_ARGO}" != "1" ]]; then
    return 0
  fi
  if kubectl get application bifrost-stg -n cicd >/dev/null 2>&1; then
    echo "==> Pause Argo CD auto-sync for bifrost-stg (local cutover; push git + re-enable after)"
    kubectl patch application bifrost-stg -n cicd --type merge \
      -p '{"spec":{"syncPolicy":{"automated":null}}}' >/dev/null
  fi
}

remove_embedded_postgres() {
  echo "==> Remove embedded postgres (deployment/service/PVC)"
  kubectl delete deployment/postgres service/postgres pvc/postgres-data \
    -n "${STG_NAMESPACE}" --ignore-not-found --wait=true
}

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Phase ③ STG cutover (CNPG @ data NS)"
pause_argo_stg

echo "==> 1/6 Verify CNPG phase ②"
"${ROOT}/scripts/k3s/verify-data-layer-phase1.sh"

if [[ "${SKIP_MIGRATE}" != "1" ]]; then
  echo "==> 2/6 Migrate embedded postgres → CNPG"
  "${ROOT}/scripts/k3s/migrate-stg-postgres-to-cnpg.sh"
else
  echo "==> 2/6 SKIP_MIGRATE=1 — skip data copy"
fi

echo "==> 3/6 Sync stg config (IB from .env; postgres host stays CNPG)"
if [[ -f "${ROOT}/.env" ]]; then
  "${ROOT}/scripts/sync_stg_config.sh"
else
  cp "${ROOT}/config/config.stg.yaml" "${ROOT}/k8s/overlays/stg/config/config.stg.yaml"
fi

echo "==> 4/6 Apply bifrost-stg overlay (CNPG config; no embedded postgres)"
kubectl apply -k "${ROOT}/k8s/overlays/stg"
remove_embedded_postgres
kubectl apply -k "${ROOT}/k8s/overlays/stg"

echo "==> 5/6 Rollout restart (reload bifrost-config → CNPG endpoint)"
kubectl rollout restart deployment -n "${STG_NAMESPACE}"
kubectl rollout status deployment/nginx -n "${STG_NAMESPACE}" --timeout=600s
kubectl rollout status deployment/api-monitor -n "${STG_NAMESPACE}" --timeout=600s

echo "==> Ensure CNPG schema (db_refresh_schema via api-monitor)"
kubectl exec -n "${STG_NAMESPACE}" deploy/api-monitor -- \
  python /build/bifrost-trade-core/scripts/db/db_refresh_schema.py

if [[ "${RUN_DB_INIT}" == "1" ]]; then
  echo "==> db-init against CNPG"
  kubectl delete job db-init-stg -n "${STG_NAMESPACE}" --ignore-not-found
  kubectl apply -k "${ROOT}/k8s/overlays/stg" --selector app.kubernetes.io/name=db-init 2>/dev/null || \
    kubectl apply -f "${ROOT}/k8s/base/jobs/db-init.yaml" -n "${STG_NAMESPACE}"
  kubectl wait --for=condition=complete job/db-init-stg -n "${STG_NAMESPACE}" --timeout=600s
fi

echo "==> 6/6 Verify phase ③"
"${ROOT}/scripts/k3s/verify-data-layer-phase2-stg.sh"

echo ""
echo "Phase ③ STG cutover complete."
echo "  PG RW: bifrost-postgres-rw.data.svc.cluster.local:5432/bifrost_stg"
echo "  verify: make k3s-verify-data-layer-phase2-stg"
echo "  smoke:  make k3s-verify-phase-b-stg-v2"
echo ""
echo "IMPORTANT: Push bifrost-trade-infra to GitHub (k8s/overlays/stg) and re-enable Argo auto-sync:"
echo "  kubectl patch application bifrost-stg -n cicd --type merge \\"
echo "    -p '{\"spec\":{\"syncPolicy\":{\"automated\":{\"prune\":true,\"selfHeal\":true}}}}'"
