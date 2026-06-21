#!/usr/bin/env bash
# Label the dedicated PostgreSQL K3s node (phase ① data layer).
# Enables platform-api postgres-role capability (node-role=postgres).
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

NODE="${POSTGRES_NODE_NAME:-ubt-k3s-04}"
HOST_ID="${POSTGRES_HOST_ID:-ubt-k3s-04}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found in PATH" >&2
  exit 1
fi

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl get node "${NODE}" >/dev/null 2>&1; then
  echo "Node ${NODE} not found in cluster. Set POSTGRES_NODE_NAME to a Ready worker." >&2
  kubectl get nodes -o wide >&2
  exit 1
fi

echo "==> Label postgres primary node ${NODE} (host-id=${HOST_ID})"
kubectl label node "${NODE}" \
  bifrost.io/host-id="${HOST_ID}" \
  bifrost.io/postgres-role=primary \
  bifrost.io/workload-pool=data-primary \
  node-role=postgres \
  --overwrite

echo "OK postgres labels on ${NODE}"
kubectl get node "${NODE}" --show-labels | tr ',' '\n' | grep -E 'node-role=postgres|host-id|workload-pool' || true
