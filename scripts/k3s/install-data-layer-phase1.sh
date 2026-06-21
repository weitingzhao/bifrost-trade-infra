#!/usr/bin/env bash
# Phase ② — HA (instances=2) + MinIO backup target + CNPG barman WAL archive.
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml make k3s-install-data-layer-phase1
#   MINIO_ACCESS_KEY=bifrost MINIO_SECRET_KEY='...' make k3s-install-data-layer-phase1
#
# Prerequisite: phase ① (make k3s-install-data-layer-phase0)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-bifrost_backup}"
MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-bifrost_backup_secret_change_me}"
CLUSTER_READY_TIMEOUT="${CLUSTER_READY_TIMEOUT:-900}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Phase ② data layer (CNPG HA + MinIO backup)"

echo "==> 1/5 Label postgres primary + standby nodes"
"${ROOT}/scripts/k3s/label-postgres-node.sh"
"${ROOT}/scripts/k3s/label-postgres-standby-node.sh"

echo "==> 2/5 MinIO backup credentials (minio-backup secret)"
kubectl create namespace "${DATA_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic minio-backup \
  --namespace="${DATA_NAMESPACE}" \
  --from-literal=ACCESS_KEY_ID="${MINIO_ACCESS_KEY}" \
  --from-literal=SECRET_ACCESS_KEY="${MINIO_SECRET_KEY}" \
  --type=Opaque \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> 3/5 Apply k8s/data (MinIO + CNPG cluster instances=2 + ScheduledBackup)"
kubectl apply -k "${ROOT}/k8s/data"

echo "==> 4/5 Wait for MinIO ready"
kubectl rollout status deployment/minio -n "${DATA_NAMESPACE}" --timeout=300s

echo "==> 5/5 Wait for CNPG cluster ${CLUSTER_NAME} (2 instances Ready)"
kubectl wait --for=condition=Ready "cluster/${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" --timeout="${CLUSTER_READY_TIMEOUT}s"

READY_INSTANCES="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyInstances}' 2>/dev/null || echo 0)"
echo ""
echo "Phase ② complete."
echo "  RW service: ${CLUSTER_NAME}-rw.${DATA_NAMESPACE}.svc.cluster.local:5432"
echo "  RO service: ${CLUSTER_NAME}-ro.${DATA_NAMESPACE}.svc.cluster.local:5432"
echo "  instances:  ${READY_INSTANCES}/2 ready"
echo "  backup:     s3://bifrost-postgres-backup/ @ minio.${DATA_NAMESPACE}.svc:9000"
echo "  verify:     make k3s-verify-data-layer-phase1"
echo ""
echo "Next (phase ③): STG cutover — make k3s-cutover-stg-data-layer-phase2"
