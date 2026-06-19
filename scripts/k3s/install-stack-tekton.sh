#!/usr/bin/env bash
# Install Tekton Pipelines + Bifrost smoke/deliver manifests (P4 stack wizard).
# Idempotent — safe to re-run.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
TEKTON_VERSION="${TEKTON_VERSION:-latest}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

kubectl cluster-info >/dev/null
kubectl create namespace "${CICD_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

TEKTON_URL="https://storage.googleapis.com/tekton-releases/pipeline/${TEKTON_VERSION}/release.yaml"
echo "==> Tekton Pipelines (${TEKTON_URL})"
kubectl apply --server-side --force-conflicts -f "${TEKTON_URL}" || {
  echo "WARN: Tekton apply had conflicts; continuing if controller exists" >&2
}

echo "==> Waiting for tekton-pipelines-controller"
kubectl rollout status deployment/tekton-pipelines-controller -n tekton-pipelines --timeout=300s

echo "==> Waiting for tekton-pipelines-webhook"
kubectl rollout status deployment/tekton-pipelines-webhook -n tekton-pipelines --timeout=300s

echo "==> Waiting for Pipeline CRD"
for i in $(seq 1 60); do
  if kubectl get crd pipelines.tekton.dev >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
kubectl get crd pipelines.tekton.dev >/dev/null

echo "==> Bifrost smoke Pipeline + Task"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-smoke.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-smoke.yaml"

if [[ -f "${ROOT}/k8s/cicd/tekton/pipeline-build-stg.yaml" ]]; then
  echo "==> Registering bifrost-build-stg + bifrost-deliver-stg pipelines"
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-api-monitor.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-frontend.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-frontend-real.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-build-stg.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-build-frontend-stg.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-prepare-deliver-stg.yaml"
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-verify-stg-deliver.yaml"
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-gitea-mirror-sync.yaml"
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-refresh-dockerfile-cms.yaml"
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-stg.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-deliver-stg.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-deliver-stg.yaml" 2>/dev/null || true
fi

echo "Tekton stack ready."
