#!/usr/bin/env bash
# Phase ⑥ — STG Redis cutover: apps → redis-live/queue @ data NS; remove embedded redis.
#
# Usage:
#   make k3s-cutover-stg-data-layer-phase5-redis
#
# Prerequisite:
#   make k3s-install-data-layer-phase5-redis
#   Images include bifrost-core >= 0.2.6 (redis_queue + celery_redis_url_from_config)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
PAUSE_ARGO="${PAUSE_ARGO:-1}"

pause_argo_stg() {
  if [[ "${PAUSE_ARGO}" != "1" ]]; then
    return 0
  fi
  if kubectl get application bifrost-stg -n cicd >/dev/null 2>&1; then
    echo "==> Pause Argo CD auto-sync for bifrost-stg"
    kubectl patch application bifrost-stg -n cicd --type merge \
      -p '{"spec":{"syncPolicy":{"automated":null}}}' >/dev/null
  fi
}

remove_embedded_redis() {
  echo "==> Remove embedded redis (deployment/service)"
  kubectl delete deployment/redis service/redis -n "${STG_NAMESPACE}" --ignore-not-found --wait=true
}

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Phase ⑥ STG Redis cutover"
pause_argo_stg

echo "==> 1/5 Verify data NS Redis targets"
"${ROOT}/scripts/k3s/verify-data-layer-phase5-data.sh"

echo "==> 2/5 Overlay config (redis-live/queue — k8s/overlays/stg/config/config.stg.yaml)"
# Do not run sync_stg_config here — it copies config/config.stg.yaml and can revert redis hosts.

echo "==> 3/5 Apply bifrost-stg overlay (redis-remove.patch)"
kubectl apply -k "${ROOT}/k8s/overlays/stg"
remove_embedded_redis
kubectl apply -k "${ROOT}/k8s/overlays/stg"

echo "==> 4/5 Rollout restart (reload bifrost-config → data NS Redis)"
kubectl rollout restart deployment -n "${STG_NAMESPACE}"
kubectl rollout status deployment/nginx -n "${STG_NAMESPACE}" --timeout=600s
kubectl rollout status deployment/api-monitor -n "${STG_NAMESPACE}" --timeout=600s
kubectl rollout status deployment/api-ops -n "${STG_NAMESPACE}" --timeout=600s

echo "==> 5/5 Verify phase ⑥ STG"
"${ROOT}/scripts/k3s/verify-data-layer-phase5-stg.sh"

echo ""
echo "Phase ⑥ STG Redis cutover complete."
echo "  live:  redis-live-stg.data.svc.cluster.local:6379"
echo "  queue: redis-queue-stg.data.svc.cluster.local:6379"
echo "  verify: make k3s-verify-data-layer-phase5-stg"
echo ""
echo "Re-enable Argo after git push:"
echo "  kubectl patch application bifrost-stg -n cicd --type merge \\"
echo "    -p '{\"spec\":{\"syncPolicy\":{\"automated\":{\"prune\":true,\"selfHeal\":true}}}}'"
