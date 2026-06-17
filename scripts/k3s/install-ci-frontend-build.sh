#!/usr/bin/env bash
# Session S8 — real bifrost-trade-frontend image: Gitea clone → npm build → Kaniko → registry :stg
#
# Requires:
#   - S7 Gitea mirrors (bifrost-trade-frontend + bifrost-ui)
#   - gitea-git-credentials secret
#   - Registry + Tekton (make k3s-install-cicd-stack)
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-ci-frontend-build.sh
#   make k3s-install-ci-frontend-build
#
# Verify: Ops Console → Delivery → Pipeline runs → bifrost-build-frontend-stg
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
RUN_BUILD="${RUN_BUILD:-1}"
BUILD_TIMEOUT="${BUILD_TIMEOUT:-2400}"
GITEA_ORG="${GITEA_ORG:-bifrost}"

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
  echo "Missing gitea-git-credentials. See k8s/cicd/gitea/secret.yaml.example" >&2
  exit 1
fi

if [[ "${SKIP_GITEA_BOOTSTRAP:-0}" != "1" ]]; then
  echo "==> Ensure Gitea mirrors (includes bifrost-ui for file:../bifrost-ui)"
  MIRROR_REPOS="bifrost-trade-frontend bifrost-trade-infra bifrost-ui" \
    "${ROOT}/scripts/k3s/bootstrap-gitea-mirrors.sh"
fi

echo "==> ConfigMap Dockerfile.frontend-stg"
kubectl create configmap bifrost-frontend-stg-dockerfile \
  --from-file=Dockerfile.frontend-stg="${ROOT}/k8s/cicd/docker/Dockerfile.frontend-stg" \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> Applying Tekton tasks + bifrost-build-frontend-stg pipeline"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-git-clone-gitea.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-frontend-real.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-build-frontend-stg.yaml"

if [[ "${RUN_BUILD}" != "1" ]]; then
  echo "RUN_BUILD=0 — manifests applied, skip PipelineRun."
  exit 0
fi

RUN_NAME="bifrost-build-frontend-stg-$(date +%s)"
echo "==> Starting PipelineRun ${RUN_NAME} (timeout ${BUILD_TIMEOUT}s — npm build may take several minutes)"
kubectl apply -f - <<EOF
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${RUN_NAME}
  namespace: ${CICD_NAMESPACE}
  labels:
    tekton.dev/pipeline: bifrost-build-frontend-stg
    bifrost.io/trigger: install-ci-frontend-build
spec:
  pipelineRef:
    name: bifrost-build-frontend-stg
  workspaces:
    - name: build-context
      volumeClaimTemplate:
        spec:
          accessModes:
            - ReadWriteOnce
          storageClassName: local-path
          resources:
            requests:
              storage: 5Gi
EOF

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
    kubectl describe pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" | tail -50 >&2 || true
    echo "Task pod logs (last clone/kaniko):" >&2
    kubectl get pods -n "${CICD_NAMESPACE}" -l "tekton.dev/pipelineRun=${RUN_NAME}" -o name 2>/dev/null | tail -3 | while read -r pod; do
      echo "--- ${pod} ---" >&2
      kubectl logs -n "${CICD_NAMESPACE}" "${pod}" --all-containers 2>&1 | tail -30 >&2 || true
    done
    exit 1
  fi
  if (( SECONDS > deadline )); then
    echo "Timed out waiting for PipelineRun ${RUN_NAME}" >&2
    exit 1
  fi
  sleep 10
done

echo ""
echo "Session S8 complete."
echo "  Image: registry.cicd.svc.cluster.local:5000/bifrost-frontend:stg"
echo "  Node:  curl -s http://192.168.10.73:30500/v2/bifrost-frontend/tags/list"
echo "  Ops Console: Delivery → Pipeline runs → bifrost-build-frontend-stg"
echo "  Next S9: wire bifrost-deliver-stg to real frontend build + rollout + browser smoke"
