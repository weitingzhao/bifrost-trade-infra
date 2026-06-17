#!/usr/bin/env bash
# Session S7.5 — Gitea PVC + persistent deployment (repos survive pod restart).
#
# Storage:
#   GITEA_STORAGE_CLASS=local-path   (K3s default — data on the scheduled node disk)
#   GITEA_STORAGE_CLASS=nfs-gitea    (after configuring NAS — see pv-nfs.example.yaml)
#   GITEA_STORAGE_SIZE=20Gi
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-gitea-persistent.sh
#   make k3s-install-gitea-persistent
#
# LAN UI: http://<node-ip>:30300 (default control-plane 192.168.10.73)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
GITEA_STORAGE_CLASS="${GITEA_STORAGE_CLASS:-local-path}"
GITEA_STORAGE_SIZE="${GITEA_STORAGE_SIZE:-20Gi}"
GITEA_NODE_PORT="${GITEA_NODE_PORT:-30300}"
NODE_IP="${GITEA_NODE_IP:-192.168.10.73}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

kubectl create namespace "${CICD_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -

if kubectl get deploy gitea -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  if kubectl get deploy gitea -n "${CICD_NAMESPACE}" -o yaml | grep -q 'emptyDir: {}'; then
    echo "WARN: Migrating Gitea from emptyDir → PVC. In-repo data on old pod will not migrate."
    echo "      After this script, run: make k3s-bootstrap-gitea-mirrors"
  fi
fi

echo "==> PVC gitea-data (${GITEA_STORAGE_CLASS}, ${GITEA_STORAGE_SIZE})"
if kubectl get pvc gitea-data -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  echo "  PVC already exists — skipping create"
else
  kubectl apply -f - <<EOF
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: gitea-data
  namespace: ${CICD_NAMESPACE}
  labels:
    app: gitea
    bifrost.io/component: gitea
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: ${GITEA_STORAGE_CLASS}
  resources:
    requests:
      storage: ${GITEA_STORAGE_SIZE}
EOF
fi

echo "==> Gitea Deployment + NodePort ${GITEA_NODE_PORT}"
kubectl apply -f "${ROOT}/k8s/cicd/gitea/deployment.yaml"
kubectl rollout status deployment/gitea -n "${CICD_NAMESPACE}" --timeout=300s

echo ""
echo "Gitea persistent install complete."
echo "  In-cluster: http://gitea.cicd.svc.cluster.local:3000"
echo "  LAN UI:     http://${NODE_IP}:${GITEA_NODE_PORT}"
echo "  PVC:        gitea-data (${GITEA_STORAGE_CLASS})"
echo ""
echo "Next:"
echo "  1. Complete Gitea first-run in UI (if fresh volume) + create admin API token"
echo "  2. kubectl apply -f k8s/cicd/gitea/secret.yaml"
echo "  3. make k3s-bootstrap-gitea-mirrors   # seed from GitHub (one-time / resync)"
echo "  4. make k3s-install-ci-frontend-git   # Session S7 Tekton clone smoke"
