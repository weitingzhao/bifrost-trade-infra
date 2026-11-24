#!/usr/bin/env bash
# Install nfs-common on amd64 K3s worker/control nodes (required for NFS PV mounts).
# Run once interactively — sudo password needed on each node unless NOPASSWD is configured.
#
# Usage:
#   ./scripts/k3s/install-nfs-common-nodes.sh
#   K3S_NFS_NODES="vision@192.168.10.73 vision@192.168.10.70 vision@192.168.10.75" ./scripts/k3s/install-nfs-common-nodes.sh
#
# Verify mount (on any node):
#   sudo mount -t nfs 192.168.10.20:/volume1/k3s-hot /mnt/test-nas
set -euo pipefail

NFS_SERVER="${NFS_SERVER:-192.168.10.20}"
NFS_HOT_PATH="${NFS_HOT_PATH:-/volume1/k3s-hot}"
NFS_TEST_MOUNT="${NFS_TEST_MOUNT:-/mnt/test-nas-k3s}"

# Default: every amd64 node the cluster knows, read with the caller's kubectl
# (TD-517: a hand-written list missed 07 and 06).
mapfile -t DEFAULT_NODES < <(kubectl get nodes -l kubernetes.io/arch=amd64 \
  -o jsonpath='{range .items[*]}{.status.addresses[?(@.type=="InternalIP")].address}{"\n"}{end}' | sed 's/^/vision@/')
[[ ${#DEFAULT_NODES[@]} -gt 0 ]] || { echo "no nodes from kubectl; set K3S_NFS_NODES" >&2; exit 1; }

if [[ -n "${K3S_NFS_NODES:-}" ]]; then
  # shellcheck disable=SC2206
  NODES=(${K3S_NFS_NODES})
else
  NODES=("${DEFAULT_NODES[@]}")
fi

echo "==> Installing nfs-common on ${#NODES[@]} node(s)"
for node in "${NODES[@]}"; do
  echo "---- ${node}"
  ssh -t "${node}" "sudo apt-get update -qq && sudo apt-get install -y nfs-common"
done

echo "==> NFS mount smoke test via ${NODES[0]}"
ssh -t "${NODES[0]}" "sudo mkdir -p ${NFS_TEST_MOUNT} && \
  sudo mount -t nfs ${NFS_SERVER}:${NFS_HOT_PATH} ${NFS_TEST_MOUNT} && \
  echo nfs-common-ok | sudo tee ${NFS_TEST_MOUNT}/.k3s-nfs-smoke && \
  cat ${NFS_TEST_MOUNT}/.k3s-nfs-smoke && \
  sudo umount ${NFS_TEST_MOUNT}"
echo "nfs-common + mount test OK (${NFS_SERVER}:${NFS_HOT_PATH})"
