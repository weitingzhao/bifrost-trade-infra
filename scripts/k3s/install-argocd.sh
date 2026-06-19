#!/usr/bin/env bash
# Install minimal Argo CD into the cicd namespace (P1 / Session S1).
# Idempotent — safe to re-run (kubectl apply).
#
# Usage (MacBook with kubeconfig):
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-argocd.sh
#   make k3s-install-argocd
#
# Verify via Ops Console → Program → Delivery → GitOps — Argo CD probe.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
ARGOCD_NAMESPACE="${ARGOCD_NAMESPACE:-cicd}"
ARGOCD_VERSION="${ARGOCD_VERSION:-stable}"
	APPLY_HELLO_APP="${APPLY_HELLO_APP:-1}"
	RBAC_FIX="${ROOT}/k8s/cicd/argocd/rbac-cicd-namespace-bindings.yaml"

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

echo "==> Argo CD install (namespace: ${ARGOCD_NAMESPACE}, version: ${ARGOCD_VERSION})"
kubectl create namespace "${ARGOCD_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

MANIFEST_URL="https://raw.githubusercontent.com/argoproj/argo-cd/${ARGOCD_VERSION}/manifests/install.yaml"
echo "==> Applying ${MANIFEST_URL} (server-side apply)"
kubectl apply --server-side --force-conflicts -n "${ARGOCD_NAMESPACE}" -f "${MANIFEST_URL}" || {
  echo "WARN: server-side apply had errors; continuing if argocd-server exists" >&2
}

echo "==> Waiting for argocd-server Deployment"
kubectl rollout status deployment/argocd-server -n "${ARGOCD_NAMESPACE}" --timeout=300s

echo "==> Waiting for Application CRD"
for i in $(seq 1 60); do
  if kubectl get crd applications.argoproj.io >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
kubectl get crd applications.argoproj.io >/dev/null

if [[ -f "${RBAC_FIX}" ]]; then
  echo "==> Patch ClusterRoleBindings for cicd namespace ServiceAccounts"
  kubectl apply -f "${RBAC_FIX}"
else
  echo "WARN: missing ${RBAC_FIX} — Argo controllers may lack cluster RBAC" >&2
fi

if [[ "${APPLY_HELLO_APP}" == "1" ]]; then
  APP_MANIFEST="${ROOT}/k8s/cicd/applications/hello-stg.yaml"
  if [[ -f "${APP_MANIFEST}" ]]; then
    echo "==> Applying dummy Application hello-stg"
    kubectl apply -f "${APP_MANIFEST}"
  else
    echo "Skip hello-stg (missing ${APP_MANIFEST})" >&2
  fi
fi

echo ""
echo "Argo CD install complete."
echo "  namespace: ${ARGOCD_NAMESPACE}"
echo "  server:    kubectl get deploy argocd-server -n ${ARGOCD_NAMESPACE}"
echo "  apps:      kubectl get applications.argoproj.io -n ${ARGOCD_NAMESPACE}"
echo ""
echo "Ops Console: Program → Delivery → GitOps — Argo CD probe (refresh after ~30s)"
