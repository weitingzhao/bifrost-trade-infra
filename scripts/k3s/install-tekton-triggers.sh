#!/usr/bin/env bash
# Install Tekton Triggers controller + Interceptors (CI gate prerequisite).
# Idempotent — safe to re-run. Requires Tekton Pipelines already installed.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
TRIGGERS_VERSION="${TRIGGERS_VERSION:-latest}"
INTERCEPTORS_VERSION="${INTERCEPTORS_VERSION:-latest}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl get crd pipelines.tekton.dev >/dev/null 2>&1; then
  echo "Tekton Pipelines CRD not found — install Pipelines first (install-stack-tekton.sh)" >&2
  exit 1
fi

TRIGGERS_URL="https://storage.googleapis.com/tekton-releases/triggers/${TRIGGERS_VERSION}/release.yaml"
echo "==> Tekton Triggers (${TRIGGERS_URL})"
kubectl apply --server-side --force-conflicts -f "${TRIGGERS_URL}" || {
  echo "WARN: Triggers apply had conflicts; continuing if controller exists" >&2
}

echo "==> Waiting for tekton-triggers-controller"
kubectl rollout status deployment/tekton-triggers-controller -n tekton-pipelines --timeout=300s

echo "==> Waiting for tekton-triggers-webhook"
kubectl rollout status deployment/tekton-triggers-webhook -n tekton-pipelines --timeout=300s

INTERCEPTORS_URL="https://storage.googleapis.com/tekton-releases/triggers/${INTERCEPTORS_VERSION}/interceptors.yaml"
echo "==> Tekton Interceptors (${INTERCEPTORS_URL})"
kubectl apply --server-side --force-conflicts -f "${INTERCEPTORS_URL}" || {
  echo "WARN: Interceptors apply had conflicts; continuing if interceptor exists" >&2
}

echo "==> Waiting for tekton-triggers-core-interceptors"
kubectl rollout status deployment/tekton-triggers-core-interceptors -n tekton-pipelines --timeout=120s

echo "==> Verifying CRDs"
for crd in eventlisteners.triggers.tekton.dev triggertemplates.triggers.tekton.dev triggerbindings.triggers.tekton.dev; do
  kubectl get crd "${crd}" >/dev/null
  echo "  ${crd} ✓"
done

echo "Tekton Triggers ready."
