#!/usr/bin/env bash
# Copy kubeconfig from K3s server to local machine for kubectl on MacBook.
# Usage: ./fetch-kubeconfig.sh [user@host]
set -euo pipefail

REMOTE="${1:-vision@192.168.10.73}"
NODE_IP="${K3S_NODE_IP:-192.168.10.73}"
OUT="${KUBECONFIG_OUT:-$HOME/.kube/bifrost-k3s.yaml}"

mkdir -p "$(dirname "${OUT}")"
ssh "${REMOTE}" 'cat /etc/rancher/k3s/k3s.yaml' >"${OUT}.tmp"
# Replace 127.0.0.1 with LAN IP for remote kubectl
sed "s/127.0.0.1/${NODE_IP}/g" "${OUT}.tmp" >"${OUT}"
chmod 600 "${OUT}"
rm -f "${OUT}.tmp"

echo "Wrote ${OUT}"
echo "  export KUBECONFIG=${OUT}"
echo "  kubectl get nodes"
