#!/usr/bin/env bash
# Phase B — stg v2: full stack — PG/Redis/nginx/9 APIs/frontend + worker + socket (Live TWS + Massive).
#
# Usage:
#   make sync-stg-config   # optional: refresh IB from .env
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-phase-b-stg.sh
#   make k3s-install-phase-b-stg
#
# Prereq: kubectl apply -f k8s/base/secrets/bifrost-stg-secrets.yaml -n bifrost-stg (from .example)
#
# Verify: make k3s-verify-phase-b-stg-v2
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
RUN_DELIVER="${RUN_DELIVER:-1}"
DELIVER_TIMEOUT="${DELIVER_TIMEOUT:-7200}"
STG_GATEWAY_URL="${STG_GATEWAY_URL:-http://192.168.10.73:30880/}"
STG_API_URL="${STG_API_URL:-http://192.168.10.73:30880/api/monitor/status}"
GITEA_ORG="${GITEA_ORG:-bifrost}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl get secret gitea-git-credentials -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing gitea-git-credentials — complete Gitea secret setup first." >&2
  exit 1
fi

echo "==> Phase B: Gitea mirrors (Trade repos for API + frontend builds)"
MIRROR_REPOS="bifrost-trade-core bifrost-trade-worker bifrost-trade-socket bifrost-trade-api bifrost-trade-frontend bifrost-trade-infra bifrost-ui" \
  "${ROOT}/scripts/k3s/bootstrap-gitea-mirrors.sh"

echo "==> Sync stg config into kustomize overlay"
if [[ -f "${ROOT}/.env" ]]; then
  "${ROOT}/scripts/sync_stg_config.sh"
else
  mkdir -p "${ROOT}/k8s/overlays/stg/config"
  cp "${ROOT}/config/config.stg.yaml" "${ROOT}/k8s/overlays/stg/config/config.stg.yaml"
fi

if [[ -f "${ROOT}/k8s/base/secrets/bifrost-stg-secrets.yaml" ]]; then
  echo "==> Apply bifrost-stg-secrets"
  kubectl apply -f "${ROOT}/k8s/base/secrets/bifrost-stg-secrets.yaml" -n "${STG_NAMESPACE}"
else
  echo "WARN: no k8s/base/secrets/bifrost-stg-secrets.yaml — copy from .example for Massive API key" >&2
fi

echo "==> Apply bifrost-stg overlay (full stack: infra + APIs + worker + socket + frontend)"
kubectl apply -k "${ROOT}/k8s/overlays/stg"

echo "==> Wait for infra (postgres, redis, nginx)"
kubectl rollout status deployment/postgres -n "${STG_NAMESPACE}" --timeout=600s || true
kubectl rollout status deployment/redis -n "${STG_NAMESPACE}" --timeout=300s
kubectl rollout status deployment/nginx -n "${STG_NAMESPACE}" --timeout=300s || true

echo "==> Tekton ConfigMaps (Dockerfiles)"
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

echo "==> Tekton Phase B v2 deliver pipeline"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-git-clone-gitea.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-all-apis-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-worker-socket-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-frontend-real.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-deliver-stg.yaml"

if [[ "${RUN_DELIVER}" != "1" ]]; then
  echo "RUN_DELIVER=0 — manifests applied, skip PipelineRun."
  exit 0
fi

RUN_NAME="bifrost-deliver-stg-$(date +%s)"
echo "==> Starting PipelineRun ${RUN_NAME} (timeout ${DELIVER_TIMEOUT}s — 9 API builds + frontend)"
kubectl apply -f - <<EOF
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${RUN_NAME}
  namespace: ${CICD_NAMESPACE}
  labels:
    tekton.dev/pipeline: bifrost-deliver-stg
    bifrost.io/trigger: install-phase-b-stg
spec:
  pipelineRef:
    name: bifrost-deliver-stg
  # Pin ALL tasks to amd64 control-plane (arm64 workers cannot run RUN commands for amd64 images).
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
              storage: 10Gi
EOF

deadline=$((SECONDS + DELIVER_TIMEOUT))
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
    exit 1
  fi
  if (( SECONDS > deadline )); then
    echo "Timed out waiting for PipelineRun ${RUN_NAME}" >&2
    exit 1
  fi
  sleep 20
done

echo "==> DB schema init (one-shot Job)"
kubectl delete job db-init-stg -n "${STG_NAMESPACE}" --ignore-not-found
kubectl apply -k "${ROOT}/k8s/overlays/stg"
kubectl wait --for=condition=complete job/db-init-stg -n "${STG_NAMESPACE}" --timeout=600s

echo "==> Stg gateway smoke"
api_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${STG_API_URL}" || echo 000)"
fe_body="$(curl -sf --connect-timeout 8 "${STG_GATEWAY_URL}" || true)"
fe_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${STG_GATEWAY_URL}" || echo 000)"

echo "  gateway   ${STG_GATEWAY_URL} → HTTP ${fe_code}"
echo "  monitor   ${STG_API_URL} → HTTP ${api_code}"

if [[ "${fe_code}" != "200" ]]; then
  echo "FAIL: stg gateway not HTTP 200" >&2
  exit 1
fi
if [[ "${api_code}" != "200" ]]; then
  echo "WARN: /api/monitor/status not HTTP 200 (DB or API warming up — check pods)" >&2
fi
if echo "${fe_body}" | grep -q 'K3s smoke'; then
  echo "FAIL: still serving smoke HTML" >&2
  exit 1
fi
if echo "${fe_body}" | grep -q 'Bifrost Trade'; then
  echo "  SPA check: HTML contains 'Bifrost Trade'"
fi

echo ""
echo "Phase B stg v2 complete."
echo "  Gateway:  ${STG_GATEWAY_URL} (nginx NodePort :30880)"
echo "  Monitor:  ${STG_API_URL}"
echo "  Worker:   daemon · account-sync · celery-worker"
echo "  Socket:   ib-ingestor · ib-account-agent · ib-operator · massive-ws"
echo "  Verify:   make k3s-verify-phase-b-stg-v2"
echo "  Console:  Delivery → ${RUN_NAME}; Promote stg smoke via gateway URLs"
