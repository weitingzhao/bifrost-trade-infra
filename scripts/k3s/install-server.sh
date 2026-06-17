#!/usr/bin/env bash
# Bootstrap K3s server (single-node with --cluster-init for future HA join).
# Run on the Linux host as root: sudo bash install-server.sh
#
# Defaults match ubt-k3s-01 @ 192.168.10.73 (first bootstrap node).
set -euo pipefail

NODE_IP="${K3S_NODE_IP:-192.168.10.73}"
NODE_NAME="${K3S_NODE_NAME:-ubt-k3s-01}"
K3S_VERSION="${K3S_VERSION:-}"
INSTALL_K3S_CHANNEL="${INSTALL_K3S_CHANNEL:-stable}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo K3S_NODE_IP=${NODE_IP} bash $0" >&2
  exit 1
fi

echo "==> K3s server bootstrap"
echo "    node: ${NODE_NAME} @ ${NODE_IP}"
echo "    channel: ${INSTALL_K3S_CHANNEL}"

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  echo "==> Opening UFW ports for K3s"
  ufw allow 6443/tcp comment 'k3s API' || true
  ufw allow 10250/tcp comment 'kubelet' || true
  ufw allow 8472/udp comment 'flannel VXLAN' || true
  ufw allow 51820/udp comment 'flannel Wireguard' || true
  ufw allow 51821/udp comment 'flannel Wireguard' || true
  ufw allow 2379:2380/tcp comment 'k3s etcd' || true
fi

if swapon --show | grep -q .; then
  echo "==> Disabling swap (recommended for Kubernetes)"
  swapoff -a
  if grep -q swap /etc/fstab; then
    sed -i.bak-k3s '/swap/s/^/# disabled for k3s /' /etc/fstab
  fi
fi

if systemctl is-active --quiet k3s 2>/dev/null; then
  echo "k3s already running — skipping install. Run: kubectl get nodes" >&2
  exit 0
fi

export INSTALL_K3S_CHANNEL
if [[ -n "${K3S_VERSION}" ]]; then
  export INSTALL_K3S_VERSION="${K3S_VERSION}"
fi

curl -sfL https://get.k3s.io | sh -s - server \
  --cluster-init \
  --node-name "${NODE_NAME}" \
  --node-ip "${NODE_IP}" \
  --tls-san "${NODE_IP}" \
  --tls-san "${NODE_NAME}" \
  --write-kubeconfig-mode 644 \
  --kube-apiserver-arg="feature-gates=KubeletInUserNamespace=false"

echo "==> Waiting for node Ready"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
for i in $(seq 1 60); do
  if kubectl get nodes "${NODE_NAME}" --no-headers 2>/dev/null | grep -q Ready; then
    break
  fi
  sleep 2
done

kubectl get nodes -o wide
kubectl get pods -A

echo "==> Creating Bifrost namespaces"
for ns in cicd data monitoring ai bifrost bifrost-stg; do
  kubectl create namespace "${ns}" --dry-run=client -o yaml | kubectl apply -f -
done

kubectl label node "${NODE_NAME}" bifrost.io/bootstrap=first-server --overwrite
kubectl label node "${NODE_NAME}" bifrost.io/host-id=mini-pc-c --overwrite

echo ""
echo "Bootstrap complete."
echo "  API: https://${NODE_IP}:6443"
echo "  kubeconfig: /etc/rancher/k3s/k3s.yaml"
echo "  join token (for agents): sudo cat /var/lib/rancher/k3s/server/node-token"
