#!/usr/bin/env bash
# Print the k3s version every new node must be installed at: the version the
# control plane runs. Join scripts pass it to install-agent.sh as
# INSTALL_K3S_VERSION, so a joining node never picks up whatever the "stable"
# channel points at that day.
#
# 2026-06-29: ubt-k3s-06 joined from the stable channel and came up at
# v1.36.2+k3s1 while the control plane ran v1.35.5+k3s1 — a kubelet newer than
# the API server, outside the Kubernetes version-skew policy, unnoticed for
# three months.
#
# Run from a host with the cluster kubeconfig (MacBook).
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"

versions="$(kubectl --kubeconfig "${KUBECONFIG}" get nodes \
  -l node-role.kubernetes.io/control-plane \
  -o jsonpath='{range .items[*]}{.status.nodeInfo.kubeletVersion}{"\n"}{end}' | sort -u)"

if [[ -z "${versions}" ]]; then
  echo "ERROR: no control-plane node found (kubeconfig ${KUBECONFIG})" >&2
  exit 1
fi
if [[ "$(printf '%s\n' "${versions}" | wc -l | tr -d ' ')" -ne 1 ]]; then
  echo "ERROR: control-plane nodes disagree on version — settle that first:" >&2
  printf '  %s\n' ${versions} >&2
  exit 1
fi

printf '%s\n' "${versions}"
