#!/usr/bin/env bash
# Session S9 — bifrost-deliver-stg with real frontend build + rollout + stg SPA smoke check.
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-ci-deliver-stg.sh
#   make k3s-install-ci-deliver-stg
#
# Verify: Ops Console → Delivery → bifrost-deliver-stg (Succeeded)
#         Browser http://192.168.10.73:30780 — title "Bifrost Trade" (not K3s smoke HTML)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
RUN_DELIVER="${RUN_DELIVER:-1}"
DELIVER_TIMEOUT="${DELIVER_TIMEOUT:-3600}"
STG_FRONTEND_URL="${STG_FRONTEND_URL:-http://192.168.10.73:30780/}"
STG_API_URL="${STG_API_URL:-http://192.168.10.73:30765/status}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl get secret gitea-git-credentials -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing gitea-git-credentials — complete S7 secret setup first." >&2
  exit 1
fi

echo "==> Apply stg overlay (imagePullPolicy Always on frontend)"
kubectl apply -k "${ROOT}/k8s/overlays/stg"

echo "==> ConfigMap Dockerfile.frontend-stg"
kubectl create configmap bifrost-frontend-stg-dockerfile \
  --from-file=Dockerfile.frontend-stg="${ROOT}/k8s/cicd/docker/Dockerfile.frontend-stg" \
  -n "${CICD_NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> Tekton deliver + build tasks/pipelines (S8/S9)"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-git-clone-gitea.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-api-monitor.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-frontend-real.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-deliver-stg.yaml"

if [[ "${RUN_DELIVER}" != "1" ]]; then
  echo "RUN_DELIVER=0 — manifests applied."
  exit 0
fi

RUN_NAME="bifrost-deliver-stg-$(date +%s)"
echo "==> Starting PipelineRun ${RUN_NAME} (timeout ${DELIVER_TIMEOUT}s)"
kubectl apply -f - <<EOF
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: ${RUN_NAME}
  namespace: ${CICD_NAMESPACE}
  labels:
    tekton.dev/pipeline: bifrost-deliver-stg
    bifrost.io/trigger: install-ci-deliver-stg
spec:
  pipelineRef:
    name: bifrost-deliver-stg
  taskRunSpecs:
    - pipelineTaskName: rollout
      serviceAccountName: tekton-deliver
    - pipelineTaskName: gitops-sync
      serviceAccountName: tekton-deliver
  workspaces:
    - name: api-source
      emptyDir: {}
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
    kubectl describe pipelinerun "${RUN_NAME}" -n "${CICD_NAMESPACE}" | tail -40 >&2 || true
    exit 1
  fi
  if (( SECONDS > deadline )); then
    echo "Timed out waiting for PipelineRun ${RUN_NAME}" >&2
    exit 1
  fi
  sleep 15
done

echo "==> Stg HTTP smoke"
api_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "${STG_API_URL}" || echo 000)"
fe_body="$(curl -sf --connect-timeout 5 "${STG_FRONTEND_URL}" || true)"
fe_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "${STG_FRONTEND_URL}" || echo 000)"

echo "  api-monitor ${STG_API_URL} → HTTP ${api_code}"
echo "  frontend  ${STG_FRONTEND_URL} → HTTP ${fe_code}"

if [[ "${api_code}" != "200" ]]; then
  echo "WARN: stg api-monitor not HTTP 200" >&2
fi
if [[ "${fe_code}" != "200" ]]; then
  echo "FAIL: stg frontend not HTTP 200" >&2
  exit 1
fi
if echo "${fe_body}" | grep -q 'K3s smoke'; then
  echo "FAIL: frontend still serving smoke HTML (expected real SPA)" >&2
  exit 1
fi
if ! echo "${fe_body}" | grep -q 'Bifrost Trade'; then
  echo "WARN: title Bifrost Trade not found in HTML — verify browser manually" >&2
else
  echo "  SPA check: HTML contains 'Bifrost Trade' (not smoke placeholder)"
fi

echo ""
echo "Session S9 complete."
echo "  Ops Console: Delivery → bifrost-deliver-stg → ${RUN_NAME}"
echo "  Browser:     ${STG_FRONTEND_URL}"
echo "  Promote:     release gate should still pass stg-api-monitor (required) + stg-frontend"
