#!/usr/bin/env bash
# Label gpu-server (4090) for warehouse + compute + GPU scheduling.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
NODE="${GPU_NODE_NAME:-gpu-server}"

kubectl --kubeconfig "${KUBECONFIG}" label node "${NODE}" \
  bifrost.io/host-id=gpu-server \
  bifrost.io/workload-pool=compute \
  bifrost.io/wol=enabled \
  node-role=warehouse \
  workload=gpu \
  --overwrite

echo "OK labels on ${NODE}"
