#!/usr/bin/env bash
# Ensure MinIO backup bucket directory exists for CNPG barmanObjectStore (idempotent).
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
BUCKET="${MINIO_BACKUP_BUCKET:-bifrost-postgres-backup}"

export KUBECONFIG

kubectl rollout status deployment/minio -n "${DATA_NAMESPACE}" --timeout=120s

if kubectl exec -n "${DATA_NAMESPACE}" deploy/minio -- test -d "/data/${BUCKET}" 2>/dev/null; then
  echo "OK MinIO bucket /data/${BUCKET} exists"
else
  echo "==> Creating MinIO bucket directory /data/${BUCKET}"
  kubectl exec -n "${DATA_NAMESPACE}" deploy/minio -- mkdir -p "/data/${BUCKET}"
  echo "OK MinIO bucket /data/${BUCKET} created"
fi
