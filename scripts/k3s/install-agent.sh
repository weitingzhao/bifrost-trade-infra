#!/usr/bin/env bash
# Join a Linux host as K3s agent. Run on the target as root (one-time bootstrap).
#
# Required env:
#   K3S_URL   — e.g. https://192.168.10.73:6443
#   K3S_TOKEN — from bootstrap: sudo cat /var/lib/rancher/k3s/server/node-token
#   K3S_NODE_IP — LAN IP of this node
#   INSTALL_K3S_VERSION — e.g. v1.35.5+k3s1; must equal the control plane
#
# Optional:
#   K3S_NODE_NAME — default: hostname -s
#   K3S_NODE_LABELS — comma-separated key=value (applied from server after Ready)
#
# Example (gpu-server):
#   sudo K3S_URL=https://192.168.10.73:6443 K3S_TOKEN=... K3S_NODE_IP=192.168.10.XX \
#     INSTALL_K3S_VERSION=v1.35.5+k3s1 \
#     K3S_NODE_NAME=gpu-server K3S_NODE_LABELS=workload=gpu bash install-agent.sh
set -euo pipefail

K3S_URL="${K3S_URL:?set K3S_URL (https://bootstrap:6443)}"
K3S_TOKEN="${K3S_TOKEN:?set K3S_TOKEN (server node-token)}"
K3S_NODE_IP="${K3S_NODE_IP:?set K3S_NODE_IP}"
K3S_NODE_NAME="${K3S_NODE_NAME:-$(hostname -s)}"
# Pin the version: the "stable" channel moves, and a node that joins from it can
# come up newer than the API server (ubt-k3s-06, 2026-06-29: v1.36.2 against a
# v1.35.5 control plane). The join wrappers pass control-plane-version.sh.
INSTALL_K3S_VERSION="${INSTALL_K3S_VERSION:?set INSTALL_K3S_VERSION to the control-plane version (scripts/k3s/control-plane-version.sh)}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo K3S_URL=... K3S_TOKEN=... K3S_NODE_IP=... bash $0" >&2
  exit 1
fi

if systemctl is-active --quiet k3s-agent 2>/dev/null || systemctl is-active --quiet k3s 2>/dev/null; then
  echo "k3s already running on this host — skipping install" >&2
  exit 0
fi

if swapon --show | grep -q .; then
  echo "==> Disabling swap"
  swapoff -a
fi

AGENT_ARGS=(--node-name "${K3S_NODE_NAME}" --node-ip "${K3S_NODE_IP}")
if [[ -n "${K3S_NODE_LABELS:-}" ]]; then
  IFS=',' read -ra PAIRS <<< "${K3S_NODE_LABELS}"
  for pair in "${PAIRS[@]}"; do
    key="${pair%%=*}"
    val="${pair#*=}"
    AGENT_ARGS+=(--node-label "${key}=${val}")
  done
fi

export INSTALL_K3S_VERSION
curl -sfL https://get.k3s.io | K3S_URL="${K3S_URL}" K3S_TOKEN="${K3S_TOKEN}" sh -s - agent \
  "${AGENT_ARGS[@]}"

echo ""
echo "Agent install complete: ${K3S_NODE_NAME} @ ${K3S_NODE_IP}"
echo "Verify from bootstrap or MacBook:"
echo "  kubectl get nodes -o wide"
if [[ -n "${K3S_NODE_LABELS:-}" ]]; then
  echo ""
  echo "Apply labels from a host with kubeconfig (one-time):"
  IFS=',' read -ra PAIRS <<< "${K3S_NODE_LABELS}"
  for pair in "${PAIRS[@]}"; do
    key="${pair%%=*}"
    val="${pair#*=}"
    echo "  kubectl label node ${K3S_NODE_NAME} ${key}=${val} --overwrite"
  done
fi
