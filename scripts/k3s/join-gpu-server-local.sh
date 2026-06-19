#!/usr/bin/env bash
# Run ON gpu-server (192.168.10.60) after copying scripts via scp.
# Obtain token on bootstrap: sudo cat /var/lib/rancher/k3s/server/node-token
set -euo pipefail

K3S_URL="${K3S_URL:-https://192.168.10.73:6443}"
K3S_NODE_IP="${K3S_NODE_IP:-192.168.10.60}"
K3S_NODE_NAME="${K3S_NODE_NAME:-gpu-server}"
K3S_NODE_LABELS="${K3S_NODE_LABELS:-workload=gpu,node-role=warehouse,bifrost.io/host-id=gpu-server,bifrost.io/workload-pool=compute,bifrost.io/wol=enabled}"

: "${K3S_TOKEN:?export K3S_TOKEN from bootstrap node-token}"

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo K3S_URL="${K3S_URL}" K3S_TOKEN="${K3S_TOKEN}" K3S_NODE_IP="${K3S_NODE_IP}" \
    K3S_NODE_NAME="${K3S_NODE_NAME}" K3S_NODE_LABELS="${K3S_NODE_LABELS}" \
    bash "$0"
fi

VISION_HOME="${VISION_HOME:-/home/vision}"
cd "${VISION_HOME}"

bash install-agent.sh
REGISTRY_HOSTS="192.168.10.73:30500 registry.cicd.svc.cluster.local:5000" bash configure-insecure-registry.sh

IF=eno1
if ip link show "${IF}" >/dev/null 2>&1; then
  cp wol-eno1.service /etc/systemd/system/wol-eno1.service
  systemctl daemon-reload
  systemctl enable --now wol-eno1.service
  ethtool "${IF}" wol g || true
fi

echo "Done. From MacBook: make k3s-label-gpu-server && kubectl get nodes -o wide"
