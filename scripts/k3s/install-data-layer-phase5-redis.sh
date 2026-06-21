#!/usr/bin/env bash
# Phase ⑥ — Deploy redis-live/queue targets @ data NS.
#
# Usage:
#   make k3s-install-data-layer-phase5-redis
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
export KUBECONFIG

TARGETS=(
  redis-live-stg
  redis-queue-stg
  redis-live-prod
  redis-queue-prod
  redis-dev
)

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Phase ⑥ install — Redis live/queue @ ${DATA_NAMESPACE} NS"
kubectl apply -k "${ROOT}/k8s/data/redis"

for dep in "${TARGETS[@]}"; do
  echo "==> Wait rollout ${dep}"
  kubectl rollout status "deployment/${dep}" -n "${DATA_NAMESPACE}" --timeout=300s
done

echo ""
echo "Phase ⑥ data NS Redis deploy complete."
echo "  verify: make k3s-verify-data-layer-phase5-data"
echo "  next:   make k3s-cutover-stg-data-layer-phase5-redis"
