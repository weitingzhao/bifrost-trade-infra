#!/usr/bin/env bash
# Apply Tekton manifests for bifrost-deliver-platform (tasks, RBAC, pipeline).
# Idempotent — does not start a PipelineRun.
#
# Usage:
#   make k3s-apply-cicd-platform-pipeline
#   APPLY_OVERLAY=0 make k3s-apply-cicd-platform-pipeline   # Tekton only
#   SYNC_CONFIG=0 make k3s-apply-cicd-platform-pipeline     # skip config sync
#
# Ensures gitops-sync runs before rollout in the pipeline and refreshes
# platform-stg overlay (PLATFORM_GRAFANA_URL, clusters.yaml) when APPLY_OVERLAY=1.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
SYNC_CONFIG="${SYNC_CONFIG:-1}"
APPLY_OVERLAY="${APPLY_OVERLAY:-1}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "Cannot reach cluster via ${KUBECONFIG}" >&2
  exit 1
fi

if [[ "${SYNC_CONFIG}" == "1" ]]; then
  echo "==> Sync platform overlay config from bifrost-platform"
  "${ROOT}/scripts/sync_platform_k8s_config.sh"
fi

echo "==> Apply Tekton platform deliver pipeline (namespace: ${CICD_NAMESPACE})"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-git-clone-gitea.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-gitea-mirror-sync.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-platform-api-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-kaniko-platform-console-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/task-deliver-platform.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-stg.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/rbac-deliver-platform.yaml"
kubectl apply -f "${ROOT}/k8s/cicd/tekton/pipeline-deliver-platform.yaml"

if [[ "${APPLY_OVERLAY}" == "1" ]]; then
  echo "==> Apply bifrost-platform-stg overlay (ConfigMap + PLATFORM_GRAFANA_URL)"
  kubectl create namespace bifrost-platform-stg --dry-run=client -o yaml | kubectl apply -f -
  kubectl apply -k "${ROOT}/k8s/overlays/platform-stg"
  kubectl apply -f "${ROOT}/k8s/cicd/applications/bifrost-platform-stg.yaml"
fi

echo ""
echo "==> Verify pipeline task order (rollout must runAfter gitops-sync)"
kubectl get pipeline bifrost-deliver-platform -n "${CICD_NAMESPACE}" -o json \
  | python3 -c "
import json, sys
p = json.load(sys.stdin)
order = {t['name']: t.get('runAfter', []) for t in p['spec']['tasks']}
rollout_after = order.get('rollout', [])
if 'gitops-sync' not in rollout_after:
    raise SystemExit('FAIL: rollout runAfter must include gitops-sync; got %r' % rollout_after)
print('OK bifrost-deliver-platform: rollout runAfter=%s' % rollout_after)
"

echo ""
echo "Platform CICD apply complete."
echo "  pipeline: kubectl get pipeline bifrost-deliver-platform -n ${CICD_NAMESPACE}"
echo "  deliver:  make k3s-deliver-platform"
echo "  grafana:  curl -s http://192.168.10.73:30878/api/v1/cluster/observability | python3 -c \"import json,sys; print(json.load(sys.stdin).get('grafana_url'))\""
