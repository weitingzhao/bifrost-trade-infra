#!/usr/bin/env bash
# Step 2 — Install ai + data-warehouse stacks on gpu-server (scale-to-zero defaults).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
GPU_NODE="${GPU_NODE:-gpu-server}"
WOL_MAC="${WOL_MAC:-c8:7f:54:5b:b8:33}"
WOL_IFACE="${WOL_IFACE:-eno1}"

export KUBECONFIG

echo "== Step 2: compute stack (ai + data-warehouse) =="

if ! kubectl get node "${GPU_NODE}" >/dev/null 2>&1; then
  echo "ERROR: node ${GPU_NODE} not in cluster. Run make k3s-join-gpu-server first." >&2
  exit 1
fi

echo "==> Applying k8s/compute (Ollama + MinIO, replicas=0)..."
kubectl apply -k "${ROOT}/k8s/compute"

echo "==> Annotating ${GPU_NODE} for WOL / power manager..."
kubectl annotate node "${GPU_NODE}" \
  bifrost.io/wol-mac="${WOL_MAC}" \
  bifrost.io/wol-interface="${WOL_IFACE}" \
  bifrost.io/power-policy=on-demand \
  --overwrite

echo ""
"${ROOT}/scripts/k3s/gpu-workload.sh" status
echo ""
echo "PASS compute stack installed (idle at replicas=0)."
echo "  make gpu-ollama-up      — start Ollama on gpu-server"
echo "  make gpu-warehouse-up   — start MinIO warehouse"
echo "  make gpu-workloads-status"
