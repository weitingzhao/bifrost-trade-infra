#!/usr/bin/env bash
# Install CloudNativePG operator (cluster-scoped, cnpg-system namespace). Idempotent.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

# >=1.26 supports declarative offline major-version upgrades (bump cluster imageName → operator runs pg_upgrade).
# The version is pinned in the kustomization's upstream manifest URL; upgrade by bumping it there.
# The kustomization also sizes the manager (upstream 100m / 200Mi crash-loops once the cluster
# holds a few thousand Pods; see manager-resources.patch.yaml).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CNPG_KUSTOMIZE_DIR="${CNPG_KUSTOMIZE_DIR:-${SCRIPT_DIR}/../../k8s/system/cnpg-operator}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-300}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found in PATH" >&2
  exit 1
fi

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

CNPG_MANIFEST="$(grep -oE 'https://[^ ]+/releases/cnpg-[0-9.]+\.yaml' "${CNPG_KUSTOMIZE_DIR}/kustomization.yaml")"
echo "==> CloudNativePG operator"
echo "    manifest:  ${CNPG_MANIFEST}"
echo "    kustomize: ${CNPG_KUSTOMIZE_DIR}"

kubectl apply --server-side -k "${CNPG_KUSTOMIZE_DIR}"

echo "==> waiting for cnpg-controller-manager rollout"
kubectl rollout status deployment/cnpg-controller-manager -n cnpg-system --timeout="${ROLLOUT_TIMEOUT}s"

echo "CloudNativePG operator ready"
