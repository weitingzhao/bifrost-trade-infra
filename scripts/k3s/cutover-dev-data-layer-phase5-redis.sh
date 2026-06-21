#!/usr/bin/env bash
# Phase ⑥ — DEV Redis cutover: apps → redis-dev @ data NS (live db=0 · queue db=1).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

DEV_NAMESPACE="${DEV_NAMESPACE:-bifrost-dev}"
PAUSE_ARGO="${PAUSE_ARGO:-1}"

pause_argo_dev() {
  if [[ "${PAUSE_ARGO}" != "1" ]]; then
    return 0
  fi
  if kubectl get application bifrost-dev -n cicd >/dev/null 2>&1; then
    echo "==> Pause Argo CD auto-sync for bifrost-dev"
    kubectl patch application bifrost-dev -n cicd --type merge \
      -p '{"spec":{"syncPolicy":{"automated":null}}}' >/dev/null
  fi
}

remove_embedded_redis() {
  kubectl delete deployment/redis service/redis -n "${DEV_NAMESPACE}" --ignore-not-found --wait=true
}

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Phase ⑥ DEV Redis cutover"
pause_argo_dev

"${ROOT}/scripts/k3s/verify-data-layer-phase5-data.sh"

if [[ -f "${ROOT}/.env" ]]; then
  echo "    (skip sync_dev_overlay_config — preserves redis @ data NS; run manually for IB-only sync)"
fi

kubectl apply -k "${ROOT}/k8s/overlays/dev"
remove_embedded_redis
kubectl apply -k "${ROOT}/k8s/overlays/dev"

kubectl rollout restart deployment -n "${DEV_NAMESPACE}"
kubectl rollout status deployment/nginx -n "${DEV_NAMESPACE}" --timeout=600s
kubectl rollout status deployment/api-monitor -n "${DEV_NAMESPACE}" --timeout=600s

"${ROOT}/scripts/k3s/verify-data-layer-phase5-dev.sh"

echo ""
echo "Phase ⑥ DEV Redis cutover complete."
echo "  redis: redis-dev.data.svc.cluster.local (live db=0 · queue db=1)"
