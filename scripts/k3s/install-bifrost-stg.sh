#!/usr/bin/env bash
# Session S4 — build stg smoke images, bootstrap bifrost-stg workloads, register GitOps Application.
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-bifrost-stg.sh
#   make k3s-install-bifrost-stg
#
# Requires: cicd stack (registry + tekton) from make k3s-install-cicd-stack
# Verify: Ops Console → Delivery (bifrost-build-stg pipeline, bifrost-stg Application)
#         Runtime → Cluster → bifrost-stg namespace workloads
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
LOCAL_BOOTSTRAP="${LOCAL_BOOTSTRAP:-1}"
REMOVE_HELLO_STG="${REMOVE_HELLO_STG:-0}"
BUILD_TIMEOUT="${BUILD_TIMEOUT:-900}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "Cannot reach cluster via ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Session S4: bifrost-stg (build → deploy → GitOps Application)"

if [[ "${CONFIGURE_REGISTRY:-0}" == "1" && -n "${K3S_SSH_HOSTS:-}" ]]; then
  echo "==> Configuring insecure registry on K3s nodes (CONFIGURE_REGISTRY=1)"
  "${ROOT}/scripts/k3s/configure-insecure-registry.sh" || {
    echo "WARN: registry node config failed — run configure-insecure-registry.sh on each node manually" >&2
  }
fi

if ! kubectl get deploy registry -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing registry in ${CICD_NAMESPACE}. Run: make k3s-install-cicd-stack" >&2
  exit 1
fi
if ! kubectl get deploy tekton-pipelines-controller -n tekton-pipelines >/dev/null 2>&1; then
  echo "Tekton not installed. Run: make k3s-install-cicd-stack" >&2
  exit 1
fi

echo "==> Applying Tekton build + deliver tasks/pipelines"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-api-monitor.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-frontend.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-build-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-deliver-stg.yaml"

RUN_NAME="bifrost-build-stg-$(date +%s)"
echo "==> Starting PipelineRun ${RUN_NAME}"
kubectl apply -f - <<EOF
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${RUN_NAME}
  namespace: ${CICD_NAMESPACE}
  labels:
    tekton.dev/pipeline: bifrost-build-stg
    bifrost.io/trigger: install-bifrost-stg
spec:
  pipelineRef:
    name: bifrost-build-stg
  workspaces:
    - name: api-source
      emptyDir: {}
    - name: frontend-source
      emptyDir: {}
EOF

echo "==> Waiting for PipelineRun ${RUN_NAME} (timeout ${BUILD_TIMEOUT}s)"
deadline=$((SECONDS + BUILD_TIMEOUT))
while true; do
  reason="$(kubectl get pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" -o jsonpath='{.status.conditions[0].reason}' 2>/dev/null || true)"
  status="$(kubectl get pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" -o jsonpath='{.status.conditions[0].status}' 2>/dev/null || true)"
  if [[ "${status}" == "True" && "${reason}" == "Succeeded" ]]; then
    echo "PipelineRun succeeded."
    break
  fi
  if [[ "${status}" == "False" ]]; then
    echo "PipelineRun failed (reason=${reason})." >&2
    kubectl describe pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" | tail -30 >&2 || true
    exit 1
  fi
  if (( SECONDS > deadline )); then
    echo "Timed out waiting for PipelineRun ${RUN_NAME}" >&2
    exit 1
  fi
  sleep 5
done

if [[ "${LOCAL_BOOTSTRAP}" == "1" ]]; then
  echo "==> Bootstrap apply k8s/overlays/stg (LOCAL_BOOTSTRAP=1)"
  kubectl apply -k "${ROOT}/k8s/overlays/stg"
  echo "==> Waiting for stg Deployments"
  kubectl rollout status deployment/api-monitor -n "${STG_NAMESPACE}" --timeout=300s
  kubectl rollout status deployment/frontend -n "${STG_NAMESPACE}" --timeout=300s
fi

echo "==> Applying Argo CD Application bifrost-stg"
kubectl apply -f "${ROOT}/k8s/cicd/applications/bifrost-stg.yaml"

if [[ "${REMOVE_HELLO_STG}" == "1" ]]; then
  echo "==> Removing dummy Application hello-stg"
  kubectl delete application hello-stg -n "${CICD_NAMESPACE}" --ignore-not-found
fi

echo ""
echo "bifrost-stg install complete."
echo "  images:  registry.cicd.svc.cluster.local:5000/bifrost-api-monitor:stg"
echo "           registry.cicd.svc.cluster.local:5000/bifrost-frontend:stg"
echo "  pods:    kubectl get pods -n ${STG_NAMESPACE}"
echo "  argo:    kubectl get application bifrost-stg -n ${CICD_NAMESPACE}"
echo ""
echo "If pods are ImagePullBackOff, on each K3s node run (once):"
echo "  sudo bash scripts/k3s/configure-insecure-registry.sh"
echo "Or set CONFIGURE_REGISTRY=1 K3S_SSH_HOSTS=\"user@node ...\" before this script."
echo ""
echo "Ops Console:"
echo "  Delivery → Pipeline runs → bifrost-deliver-stg (real frontend build + rollout + GitOps sync)"
echo "  Delivery → Stg smoke (api-monitor NodePort :30765)"
echo "  Delivery → GitOps → Application bifrost-stg"
echo "  Pulse     → Stg smoke KPI"
echo "  Cluster  → namespace ${STG_NAMESPACE} workloads"
echo ""
echo "Note: push k8s/ to github.com/weitingzhao/bifrost-trade-infra main for Argo CD sync from Git."
