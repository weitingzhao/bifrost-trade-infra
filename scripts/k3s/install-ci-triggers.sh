#!/usr/bin/env bash
# CI gate activation — Tekton Triggers + the three CI pipelines + code-health ratchet.
#
# Context: the CI pipelines had existed as YAML in git for months but were never
# applied, and Tekton Triggers was never installed, so Gitea push webhooks had
# nothing listening. This script closes that gap.
#
# Requires:
#   - Tekton Pipelines (make k3s-install-cicd-stack)
#   - Gitea mirrors + gitea-git-credentials secret (make k3s-bootstrap-gitea-mirrors)
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-ci-triggers.sh
#   make k3s-install-ci-triggers
#
# Verify: make k3s-verify-ci-triggers
#
# After install, each repo needs a Gitea push webhook pointing at
#   http://el-bifrost-ci.cicd.svc.cluster.local:8080  (type: application/json, event: Push)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
TRIGGERS_VERSION="${TRIGGERS_VERSION:-latest}"
SKIP_TRIGGERS_INSTALL="${SKIP_TRIGGERS_INSTALL:-0}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl get deploy tekton-pipelines-controller -n tekton-pipelines >/dev/null 2>&1; then
  echo "Tekton Pipelines not installed — run 'make k3s-install-cicd-stack' first" >&2
  exit 1
fi

# ── 1. Tekton Triggers ────────────────────────────────────────────────────────
if [[ "${SKIP_TRIGGERS_INSTALL}" != "1" ]]; then
  base="https://storage.googleapis.com/tekton-releases/triggers/${TRIGGERS_VERSION}"
  echo "==> Tekton Triggers (${base}/release.yaml)"
  kubectl apply --server-side --force-conflicts -f "${base}/release.yaml"

  # The CEL interceptor referenced by trigger-trade-ci.yaml ships separately;
  # without it every trigger fails to resolve and no PipelineRun is created.
  echo "==> Tekton Triggers core interceptors"
  kubectl apply --server-side --force-conflicts -f "${base}/interceptors.yaml"

  echo "==> Waiting for tekton-triggers controllers"
  kubectl rollout status deployment/tekton-triggers-controller -n tekton-pipelines --timeout=300s
  kubectl rollout status deployment/tekton-triggers-webhook -n tekton-pipelines --timeout=300s
  kubectl rollout status deployment/tekton-triggers-core-interceptors -n tekton-pipelines --timeout=300s
fi

kubectl get crd eventlisteners.triggers.tekton.dev >/dev/null
kubectl get crd clusterinterceptors.triggers.tekton.dev >/dev/null

# ── 2. Trigger RBAC ───────────────────────────────────────────────────────────
echo "==> Trigger RBAC (ServiceAccount tekton-trigger)"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-trigger.yaml"

# ── 3. CI gate tasks + pipelines ──────────────────────────────────────────────
# Order matters: pipelines reference bifrost-code-health by taskRef.
echo "==> Code-health ratchet Task"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-code-health.yaml"

echo "==> CI pipelines"
for p in pipeline-ci-frontend pipeline-ci-platform pipeline-ci-python; do
  kubectl apply -f "${ROOT}/k8s/cicd/tekton/${p}.yaml"
done

# ── 4. EventListener + triggers ───────────────────────────────────────────────
echo "==> Trigger bindings / templates / EventListener"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/trigger-trade-ci.yaml"

echo "==> Waiting for EventListener el-bifrost-ci"
kubectl wait --for=condition=Ready eventlistener/bifrost-ci -n "${CICD_NAMESPACE}" --timeout=180s || {
  echo "WARN: EventListener not Ready yet — check 'kubectl describe el bifrost-ci -n ${CICD_NAMESPACE}'" >&2
}

echo
echo "==> Installed. Remaining manual step: add the Gitea push webhook per repo"
echo "    URL:   http://el-bifrost-ci.cicd.svc.cluster.local:8080"
echo "    Type:  application/json   Event: Push"
echo "    Repos: bifrost-trade-{core,api,worker,socket,frontend}, bifrost-ui, bifrost-platform, bifrost-research"
echo
echo "    Then: make k3s-install-ci-webhooks"
