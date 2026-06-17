#!/usr/bin/env bash
# Join a second K3s server to an existing --cluster-init bootstrap (HA path).
# Run on the joining server as root. Requires bootstrap server token + URL.
#
# Required env:
#   K3S_URL   — e.g. https://192.168.10.73:6443
#   K3S_TOKEN — bootstrap node-token
#   K3S_NODE_IP — LAN IP of this server
#
# Optional:
#   K3S_NODE_NAME — default: hostname -s
#
# Example (mini-pc-b):
#   sudo K3S_URL=https://192.168.10.73:6443 K3S_TOKEN=... K3S_NODE_IP=192.168.10.80 \
#     K3S_NODE_NAME=mini-pc-b bash install-server-join.sh
set -euo pipefail

K3S_URL="${K3S_URL:?set K3S_URL}"
K3S_TOKEN="${K3S_TOKEN:?set K3S_TOKEN}"
K3S_NODE_IP="${K3S_NODE_IP:?set K3S_NODE_IP}"
K3S_NODE_NAME="${K3S_NODE_NAME:-$(hostname -s)}"
INSTALL_K3S_CHANNEL="${INSTALL_K3S_CHANNEL:-stable}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo K3S_URL=... K3S_TOKEN=... K3S_NODE_IP=... bash $0" >&2
  exit 1
fi

if systemctl is-active --quiet k3s 2>/dev/null; then
  echo "k3s already running — skipping install" >&2
  exit 0
fi

if swapon --show | grep -q .; then
  swapoff -a
fi

export INSTALL_K3S_CHANNEL
curl -sfL https://get.k3s.io | K3S_URL="${K3S_URL}" K3S_TOKEN="${K3S_TOKEN}" sh -s - server \
  --server "${K3S_URL}" \
  --node-name "${K3S_NODE_NAME}" \
  --node-ip "${K3S_NODE_IP}" \
  --tls-san "${K3S_NODE_IP}" \
  --tls-san "${K3S_NODE_NAME}" \
  --write-kubeconfig-mode 644

echo ""
echo "Server join complete: ${K3S_NODE_NAME} @ ${K3S_NODE_IP}"
echo "Verify: kubectl get nodes -o wide"
