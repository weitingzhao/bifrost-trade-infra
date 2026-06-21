#!/usr/bin/env bash
# Label CNPG standby node (phase ② — HA; default replica on ubt-k3s-02).
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

NODE="${POSTGRES_STANDBY_NODE_NAME:-ubt-k3s-02}"
HOST_ID="${POSTGRES_STANDBY_HOST_ID:-mini-pc-a}"

if ! kubectl get node "${NODE}" >/dev/null 2>&1; then
  echo "Node ${NODE} not found. Set POSTGRES_STANDBY_NODE_NAME." >&2
  kubectl get nodes -o wide >&2
  exit 1
fi

echo "==> Label postgres standby node ${NODE} (host-id=${HOST_ID})"
kubectl label node "${NODE}" \
  bifrost.io/host-id="${HOST_ID}" \
  bifrost.io/postgres-role=standby \
  bifrost.io/workload-pool=prod-pool \
  node-role=postgres \
  --overwrite

echo "OK postgres standby labels on ${NODE}"
