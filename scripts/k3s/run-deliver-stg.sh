#!/usr/bin/env bash
# Run bifrost-deliver-stg Tekton pipeline (Kaniko build + rollout + Argo sync).
#
# Prerequisites:
#   - K3s + Gitea + Tekton + registry (make k3s-install-cicd-stack)
#   - gitea-git-credentials secret in cicd namespace
#   - Trade repos pushed to GitHub; Gitea mirrors synced (SYNC_GITEA=1 default)
#
# Usage:
#   make sync-stg-config                    # optional: refresh IB + overlay config
#   make k3s-deliver-stg                    # mirror sync + build + rollout
#   SYNC_GITEA=0 make k3s-deliver-stg       # skip Gitea mirror-sync (already fresh)
#   APPLY_OVERLAY=1 make k3s-deliver-stg   # also kubectl apply -k overlays/stg
#   REVISION=main TRIGGER=manual make k3s-deliver-stg
#
# Ops Console: Delivery → bifrost-deliver-stg → Run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
DELIVER_TIMEOUT="${DELIVER_TIMEOUT:-7200}"
REVISION="${REVISION:-main}"
TRIGGER="${TRIGGER:-deliver-stg}"
SYNC_GITEA="${SYNC_GITEA:-1}"
APPLY_OVERLAY="${APPLY_OVERLAY:-0}"
RUN_DB_INIT="${RUN_DB_INIT:-0}"
GITEA_ORG="${GITEA_ORG:-bifrost}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl get secret gitea-git-credentials -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing gitea-git-credentials in ${CICD_NAMESPACE}" >&2
  exit 1
fi

if [[ "${SYNC_GITEA}" == "1" ]]; then
  echo "==> Sync Gitea mirrors from GitHub (${REVISION} on upstream)"
  MIRROR_REPOS="bifrost-trade-core bifrost-trade-worker bifrost-trade-socket bifrost-trade-api bifrost-trade-frontend bifrost-trade-infra bifrost-ui" \
    "${ROOT}/scripts/k3s/bootstrap-gitea-mirrors.sh"
fi

if [[ -f "${ROOT}/.env" ]]; then
  echo "==> sync-stg-config (IB from .env)"
  "${ROOT}/scripts/sync_stg_config.sh"
elif [[ "${APPLY_OVERLAY}" == "1" ]]; then
  mkdir -p "${ROOT}/k8s/overlays/stg/config"
  cp "${ROOT}/config/config.stg.yaml" "${ROOT}/k8s/overlays/stg/config/config.stg.yaml"
fi

if [[ "${APPLY_OVERLAY}" == "1" ]]; then
  echo "==> Apply bifrost-stg overlay"
  kubectl apply -k "${ROOT}/k8s/overlays/stg"
fi

echo "==> Tekton Dockerfile ConfigMaps (from infra repo — not Gitea)"
kubectl create configmap bifrost-frontend-stg-dockerfile \
  --from-file=Dockerfile.frontend-stg="${ROOT}/k8s/cicd/docker/Dockerfile.frontend-stg" \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap bifrost-api-stg-dockerfile \
  --from-file=Dockerfile.api-stg="${ROOT}/k8s/cicd/docker/Dockerfile.api-stg" \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap bifrost-worker-stg-dockerfile \
  --from-file=Dockerfile.worker-stg="${ROOT}/k8s/cicd/docker/Dockerfile.worker-stg" \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap bifrost-socket-stg-dockerfile \
  --from-file=Dockerfile.socket-stg="${ROOT}/k8s/cicd/docker/Dockerfile.socket-stg" \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> Register Tekton deliver pipeline"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-git-clone-gitea.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-all-apis-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-worker-socket-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-frontend-real.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-prepare-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-verify-stg-deliver.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-deliver-stg.yaml"

RUN_NAME="bifrost-deliver-stg-$(date +%s)"
echo "==> PipelineRun ${RUN_NAME} (revision=${REVISION}, timeout=${DELIVER_TIMEOUT}s)"
kubectl apply -f - <<EOF
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${RUN_NAME}
  namespace: ${CICD_NAMESPACE}
  labels:
    tekton.dev/pipeline: bifrost-deliver-stg
    bifrost.io/trigger: ${TRIGGER}
spec:
  pipelineRef:
    name: bifrost-deliver-stg
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
    - pipelineTaskName: prepare
      serviceAccountName: tekton-deliver
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
              storage: 10Gi
EOF

deadline=$((SECONDS + DELIVER_TIMEOUT))
while true; do
  reason="$(kubectl get pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" -o jsonpath='{.status.conditions[0].reason}' 2>/dev/null || true)"
  status="$(kubectl get pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" -o jsonpath='{.status.conditions[0].status}' 2>/dev/null || true)"
  if [[ "${status}" == "True" && "${reason}" == "Succeeded" ]]; then
    echo "PipelineRun succeeded: ${RUN_NAME}"
    break
  fi
  if [[ "${status}" == "False" ]]; then
    echo "PipelineRun failed (reason=${reason})." >&2
    kubectl describe pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" | tail -60 >&2 || true
    exit 1
  fi
  if (( SECONDS > deadline )); then
    echo "Timed out waiting for ${RUN_NAME}" >&2
    exit 1
  fi
  sleep 20
done

if [[ "${RUN_DB_INIT}" == "1" ]]; then
  echo "==> DB schema init (one-shot Job)"
  kubectl delete job db-init-stg -n "${STG_NAMESPACE}" --ignore-not-found
  kubectl apply -k "${ROOT}/k8s/overlays/stg"
  kubectl wait --for=condition=complete job/db-init-stg -n "${STG_NAMESPACE}" --timeout=600s
fi

echo ""
echo "Deliver complete."
echo "  PipelineRun: ${RUN_NAME} (namespace ${CICD_NAMESPACE})"
echo "  Gateway:     http://192.168.10.73:30880/"
echo "  Verify:      make k3s-verify-phase-b-stg-v2"
