#!/usr/bin/env bash
# Install internal container registry in cicd namespace (P4 stack wizard).
# Idempotent — safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

kubectl cluster-info >/dev/null

echo "==> Registry (namespace: ${CICD_NAMESPACE})"
kubectl create namespace "${CICD_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "${ROOT}/k8s/cicd/registry/deployment.yaml"
kubectl rollout status deployment/registry -n "${CICD_NAMESPACE}" --timeout=180s
echo "Registry ready."
