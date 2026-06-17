#!/usr/bin/env bash
# Session S7 — Gitea primary Git + Tekton clone smoke for bifrost-trade-frontend.
#
# Flow:
#   1. bootstrap Gitea mirrors (GitHub → Gitea pull mirror)
#   2. apply Tekton git-clone task + clone smoke pipeline
#   3. optional PipelineRun + wait
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-ci-frontend-git.sh
#   make k3s-install-ci-frontend-git
#
# Verify: Ops Console → Delivery → Pipeline runs → bifrost-clone-frontend-smoke
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
RUN_SMOKE="${RUN_SMOKE:-1}"
SMOKE_TIMEOUT="${SMOKE_TIMEOUT:-600}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl get deploy tekton-pipelines-controller -n tekton-pipelines >/dev/null 2>&1; then
  echo "Tekton not installed. Run: make k3s-install-cicd-stack" >&2
  exit 1
fi

if ! kubectl get secret gitea-git-credentials -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing secret gitea-git-credentials in ${CICD_NAMESPACE}." >&2
  echo "Copy k8s/cicd/gitea/secret.yaml.example → secret.yaml, fill Gitea CI user/token, then:" >&2
  echo "  kubectl apply -f k8s/cicd/gitea/secret.yaml -n ${CICD_NAMESPACE}" >&2
  exit 1
fi

if [[ "${SKIP_GITEA_PERSISTENT:-0}" != "1" ]]; then
  echo "==> Gitea persistent volume (Session S7.5)"
  "${ROOT}/scripts/k3s/install-gitea-persistent.sh"
fi

if [[ "${SKIP_GITEA_BOOTSTRAP:-0}" != "1" ]]; then
  echo "==> Bootstrap Gitea mirrors (GitHub → Gitea)"
  "${ROOT}/scripts/k3s/bootstrap-gitea-mirrors.sh"
fi

echo "==> Applying Tekton git-clone task + clone smoke pipeline"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-git-clone-gitea.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-clone-frontend-smoke.yaml"

if [[ "${RUN_SMOKE}" != "1" ]]; then
  echo "Skip RUN_SMOKE=0 — apply complete."
  exit 0
fi

RUN_NAME="bifrost-clone-frontend-smoke-$(date +%s)"
echo "==> Starting PipelineRun ${RUN_NAME}"
kubectl apply -f - <<EOF
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${RUN_NAME}
  namespace: ${CICD_NAMESPACE}
  labels:
    tekton.dev/pipeline: bifrost-clone-frontend-smoke
    bifrost.io/trigger: install-ci-frontend-git
spec:
  pipelineRef:
    name: bifrost-clone-frontend-smoke
  workspaces:
    - name: source
      volumeClaimTemplate:
        spec:
          accessModes:
            - ReadWriteOnce
          storageClassName: local-path
          resources:
            requests:
              storage: 1Gi
EOF

echo "==> Waiting for PipelineRun ${RUN_NAME} (timeout ${SMOKE_TIMEOUT}s)"
deadline=$((SECONDS + SMOKE_TIMEOUT))
while true; do
  reason="$(kubectl get pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" -o jsonpath='{.status.conditions[0].reason}' 2>/dev/null || true)"
  status="$(kubectl get pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" -o jsonpath='{.status.conditions[0].status}' 2>/dev/null || true)"
  if [[ "${status}" == "True" && "${reason}" == "Succeeded" ]]; then
    echo "PipelineRun succeeded."
    break
  fi
  if [[ "${status}" == "False" ]]; then
    echo "PipelineRun failed (reason=${reason})." >&2
    kubectl describe pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" | tail -40 >&2 || true
    exit 1
  fi
  if (( SECONDS > deadline )); then
    echo "Timed out waiting for PipelineRun ${RUN_NAME}" >&2
    exit 1
  fi
  sleep 5
done

echo ""
echo "Session S7 install complete."
echo "  Gitea primary: http://gitea.cicd.svc.cluster.local:3000/bifrost/bifrost-trade-frontend.git"
echo "  Ops Console: Delivery → Pipeline runs → bifrost-clone-frontend-smoke"
echo "  Next session S8: Kaniko build real frontend image from this workspace"
