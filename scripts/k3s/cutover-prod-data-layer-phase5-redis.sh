#!/usr/bin/env bash
# Phase ⑥ — PROD Redis cutover: apps → redis-live/queue @ data NS; remove embedded redis.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

PROD_NAMESPACE="${PROD_NAMESPACE:-bifrost-prod}"
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

remove_embedded_redis() {
  kubectl delete deployment/redis service/redis -n "${PROD_NAMESPACE}" --ignore-not-found --wait=true
}

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Phase ⑥ PROD Redis cutover"
pause_argo_prod

"${ROOT}/scripts/k3s/verify-data-layer-phase5-data.sh"

if [[ -f "${ROOT}/.env" ]]; then
  echo "    (skip sync_prod_overlay_config — preserves redis @ data NS; run manually for IB-only sync)"
fi

kubectl apply -k "${ROOT}/k8s/overlays/prod"
remove_embedded_redis
kubectl apply -k "${ROOT}/k8s/overlays/prod"

kubectl rollout restart deployment -n "${PROD_NAMESPACE}"
kubectl rollout status deployment/nginx -n "${PROD_NAMESPACE}" --timeout=600s
kubectl rollout status deployment/api-monitor -n "${PROD_NAMESPACE}" --timeout=600s
kubectl rollout status deployment/api-ops -n "${PROD_NAMESPACE}" --timeout=600s

"${ROOT}/scripts/k3s/verify-data-layer-phase5-prod.sh"

echo ""
echo "Phase ⑥ PROD Redis cutover complete."
echo "  live:  redis-live-prod.data.svc.cluster.local:6379"
echo "  queue: redis-queue-prod.data.svc.cluster.local:6379"
echo "  verify: make k3s-verify-data-layer-phase5-prod"
