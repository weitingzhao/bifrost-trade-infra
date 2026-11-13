#!/usr/bin/env bash
# Install Rancher's system-upgrade-controller: the controller that carries out
# k3s's own rolling upgrade when a Plan object asks for one.
#
# NOT installed as of 2026-11-13, on purpose. Installing it changes nothing by
# itself (no Plan, no upgrade), but it is a standing controller with
# cluster-wide rights, and its first real use restarts the only control plane.
# The Owner runs it as part of the next k3s upgrade, not before. The version
# is pinned in versions.env and watched by Renovate like the others.
set -euo pipefail
# shellcheck source=scripts/k3s/versions.env
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/versions.env"

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG
VERSION="${SYSTEM_UPGRADE_CONTROLLER_VERSION}"
BASE="https://github.com/rancher/system-upgrade-controller/releases/download/${VERSION}"

[[ -f "${KUBECONFIG}" ]] || { echo "kubeconfig not found: ${KUBECONFIG}" >&2; exit 1; }
kubectl cluster-info >/dev/null

echo "==> system-upgrade-controller ${VERSION}"
kubectl apply --server-side -f "${BASE}/crd.yaml"
kubectl apply --server-side -f "${BASE}/system-upgrade-controller.yaml"
kubectl -n system-upgrade rollout status deployment/system-upgrade-controller --timeout=300s
echo "==> installed. No Plan exists, so nothing is upgraded until one is applied."
