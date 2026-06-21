#!/usr/bin/env bash
# Run bifrost-deliver-platform Tekton pipeline (Kaniko build + rollout + Argo sync).
#
# Usage:
#   make sync-platform-k8s-config   # copy bifrost-platform config into overlay
#   make k3s-deliver-platform       # mirror sync + build + rollout
#   SYNC_GITEA=0 make k3s-deliver-platform
#   APPLY_OVERLAY=1 make k3s-deliver-platform
#   APPLY_ARGO=1 make k3s-deliver-platform
#
# Ops Console: Operate → Platform → Platform Release → Run deliver-platform
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
PLATFORM_NAMESPACE="${PLATFORM_NAMESPACE:-bifrost-platform-stg}"
DELIVER_TIMEOUT="${DELIVER_TIMEOUT:-3600}"
REVISION="${REVISION:-main}"
TRIGGER="${TRIGGER:-deliver-platform}"
SYNC_GITEA="${SYNC_GITEA:-1}"
APPLY_OVERLAY="${APPLY_OVERLAY:-0}"
APPLY_ARGO="${APPLY_ARGO:-0}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl get secret gitea-git-credentials -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing gitea-git-credentials in ${CICD_NAMESPACE}" >&2
  exit 1
fi

echo "==> Sync platform overlay config from bifrost-platform"
"${ROOT}/scripts/sync_platform_k8s_config.sh"

if [[ "${SYNC_GITEA}" == "1" ]]; then
  echo "==> Sync Gitea mirrors (bifrost-platform + bifrost-ui)"
  MIRROR_REPOS="bifrost-platform bifrost-ui" \
    "${ROOT}/scripts/k3s/bootstrap-gitea-mirrors.sh"
fi

if [[ "${APPLY_OVERLAY}" == "1" ]]; then
  echo "==> Apply bifrost-platform-stg overlay"
  kubectl apply -k "${ROOT}/k8s/overlays/platform-stg"
fi

if [[ "${APPLY_ARGO}" == "1" ]]; then
  echo "==> Apply Argo CD Application bifrost-platform-stg"
  kubectl apply -f "${ROOT}/k8s/cicd/applications/bifrost-platform-stg.yaml"
fi

echo "==> Platform Dockerfile ConfigMaps"
kubectl create configmap bifrost-platform-api-stg-dockerfile \
  --from-file=Dockerfile.platform-api-stg="${ROOT}/k8s/cicd/docker/Dockerfile.platform-api-stg" \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap bifrost-platform-console-stg-dockerfile \
  --from-file=Dockerfile.platform-console-stg="${ROOT}/k8s/cicd/docker/Dockerfile.platform-console-stg" \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap bifrost-remediation-runner-stg-dockerfile \
  --from-file=Dockerfile.remediation-runner-stg="${ROOT}/k8s/cicd/docker/Dockerfile.remediation-runner-stg" \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> Register Tekton platform deliver pipeline"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-git-clone-gitea.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-gitea-mirror-sync.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-platform-api-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-platform-console-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-deliver-platform.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-platform.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-deliver-platform.yaml"

RUN_NAME="bifrost-deliver-platform-$(date +%s)"
echo "==> PipelineRun ${RUN_NAME} (revision=${REVISION}, timeout=${DELIVER_TIMEOUT}s)"
kubectl apply -f - <<EOF
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${RUN_NAME}
  namespace: ${CICD_NAMESPACE}
  labels:
    tekton.dev/pipeline: bifrost-deliver-platform
    bifrost.io/trigger: ${TRIGGER}
spec:
  pipelineRef:
    name: bifrost-deliver-platform
  params:
    - name: revision
      value: "${REVISION}"
  taskRunTemplate:
    podTemplate:
      nodeSelector:
        kubernetes.io/arch: amd64
      tolerations:
        - key: node-role.kubernetes.io/control-plane
          operator: Exists
          effect: NoSchedule
  taskRunSpecs:
    - pipelineTaskName: rollout
      serviceAccountName: tekton-deliver
    - pipelineTaskName: gitops-sync
      serviceAccountName: tekton-deliver
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

echo "==> Waiting for PipelineRun (timeout ${DELIVER_TIMEOUT}s)"
kubectl wait --for=condition=Succeeded --timeout="${DELIVER_TIMEOUT}s" \
  "pipelinerun/${RUN_NAME}" -n "${CICD_NAMESPACE}" || {
  echo "PipelineRun failed or timed out — fetch logs:" >&2
  echo "  kubectl describe pipelinerun/${RUN_NAME} -n ${CICD_NAMESPACE}" >&2
  exit 1
}

echo "==> Platform deliver complete"
echo "Console: http://192.168.10.73:30879"
echo "API:     http://192.168.10.73:30878/health"
