#!/usr/bin/env bash
# Configure K3s containerd to pull from the in-cluster HTTP registry (Session S4).
# Required on every node that runs bifrost-stg pods (server + agents).
#
# Usage (on each Linux node as root):
#   sudo bash configure-insecure-registry.sh
#
# Remote (from Mac with SSH):
#   K3S_SSH_HOSTS="vision@192.168.10.73 vision@192.168.10.54 vision@192.168.10.56" \
#     ./scripts/k3s/configure-insecure-registry.sh
#
# After apply, restart k3s (server) or k3s-agent (workers).
set -euo pipefail

REGISTRY_HOSTS="${REGISTRY_HOSTS:-registry.cicd.svc.cluster.local:5000 registry.cicd.svc:5000 192.168.10.73:30500}"
K3S_SSH_HOSTS="${K3S_SSH_HOSTS:-}"
REGISTRY_CLUSTER_IP="${REGISTRY_CLUSTER_IP:-}"

write_registries() {
  local path="/etc/rancher/k3s/registries.yaml"
  echo "==> Writing ${path}"
  mkdir -p /etc/rancher/k3s
  {
    echo "mirrors:"
    for host in ${REGISTRY_HOSTS}; do
      echo "  \"${host}\":"
      echo "    endpoint:"
      # NodePort / LAN IP uses host:port; cluster DNS uses http://host
      if [[ "${host}" == *":"* && "${host}" != *".svc"* ]]; then
        echo "      - \"http://${host}\""
      else
        echo "      - \"http://${host}\""
      fi
    done
  } > "${path}"
  cat "${path}"

  # Kubelet image pulls use the node host resolver — cluster DNS names often fail.
  if [[ -n "${REGISTRY_CLUSTER_IP}" ]]; then
    echo "==> Ensuring /etc/hosts entries for in-cluster registry DNS"
    grep -q 'registry.cicd.svc.cluster.local' /etc/hosts 2>/dev/null || \
      echo "${REGISTRY_CLUSTER_IP} registry.cicd.svc.cluster.local registry.cicd.svc" >> /etc/hosts
  fi

  if systemctl is-active --quiet k3s 2>/dev/null; then
    echo "==> Restarting k3s (server)"
    systemctl restart k3s
  elif systemctl is-active --quiet k3s-agent 2>/dev/null; then
    echo "==> Restarting k3s-agent"
    systemctl restart k3s-agent
  else
    echo "WARN: neither k3s nor k3s-agent active — configure manually" >&2
  fi
}

if [[ "${EUID}" -ne 0 ]]; then
  if [[ -n "${K3S_SSH_HOSTS}" ]]; then
    for target in ${K3S_SSH_HOSTS}; do
      echo "==> Remote configure: ${target}"
      scp "$0" "${target}:/tmp/configure-insecure-registry.sh"
      ssh "${target}" "sudo REGISTRY_HOSTS='${REGISTRY_HOSTS}' bash /tmp/configure-insecure-registry.sh"
    done
    exit 0
  fi
  echo "Run as root on each K3s node, or set K3S_SSH_HOSTS for remote apply." >&2
  exit 1
fi

write_registries
