#!/usr/bin/env bash
# Install Gitea + internal Registry + Tekton + smoke Pipeline (P3 / Session S3).
# Idempotent — safe to re-run.
#
# Usage (MacBook with kubeconfig):
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-cicd-stack.sh
#   make k3s-install-cicd-stack
#
# Verify via Ops Console → Program → Delivery → CI/CD stack + Pipeline runs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
TEKTON_VERSION="${TEKTON_VERSION:-latest}"
SKIP_TEKTON="${SKIP_TEKTON:-0}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  echo "Run: make k3s-fetch-kubeconfig" >&2
  exit 1
fi

if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "Cannot reach cluster via ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> CI/CD stack install (namespace: ${CICD_NAMESPACE})"
kubectl create namespace "${CICD_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

echo "==> Internal Registry"
kubectl apply -f "${ROOT}/k8s/cicd/registry/deployment.yaml"
kubectl rollout status deployment/registry -n "${CICD_NAMESPACE}" --timeout=180s

echo "==> Gitea (persistent PVC — Session S7.5)"
chmod +x "${ROOT}/scripts/k3s/install-gitea-persistent.sh"
"${ROOT}/scripts/k3s/install-gitea-persistent.sh"

if [[ "${SKIP_TEKTON}" != "1" ]]; then
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
fi

# Tekton build pipeline manifests (applied fully in install-bifrost-stg.sh Session S4)
  if [[ -f "${ROOT}/k8s/cicd/tekton/pipeline-build-stg.yaml" ]]; then
  echo "==> Registering bifrost-build-stg + bifrost-deliver-stg pipelines"
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-api-monitor.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-frontend.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-frontend-real.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-build-stg.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-build-frontend-stg.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-prepare-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-verify-stg-deliver.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-stg.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-deliver-stg.yaml" 2>/dev/null || true
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-deliver-stg.yaml" 2>/dev/null || true
fi

echo ""
echo "CI/CD stack install complete."
echo "  registry: kubectl get deploy registry -n ${CICD_NAMESPACE}"
echo "  gitea:    kubectl get deploy gitea -n ${CICD_NAMESPACE}"
echo "  tekton:   kubectl get deploy -n tekton-pipelines | grep tekton"
echo "  pipeline: kubectl get pipeline bifrost-smoke -n ${CICD_NAMESPACE}"
echo ""
echo "Ops Console: Program → Delivery → CI/CD stack + Pipeline runs (refresh after ~30s)"
