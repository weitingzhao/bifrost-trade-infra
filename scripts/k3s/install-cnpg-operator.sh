#!/usr/bin/env bash
# Install CloudNativePG operator (cluster-scoped, cnpg-system namespace). Idempotent.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

CNPG_VERSION="${CNPG_VERSION:-1.25.1}"
CNPG_MANIFEST="${CNPG_MANIFEST:-https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/v${CNPG_VERSION}/releases/cnpg-${CNPG_VERSION}.yaml}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-300}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found in PATH" >&2
  exit 1
fi

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> CloudNativePG operator v${CNPG_VERSION}"
echo "    manifest: ${CNPG_MANIFEST}"

kubectl apply --server-side -f "${CNPG_MANIFEST}"

echo "==> waiting for cnpg-controller-manager rollout"
kubectl rollout status deployment/cnpg-controller-manager -n cnpg-system --timeout="${ROLLOUT_TIMEOUT}s"

echo "CloudNativePG operator ready"
