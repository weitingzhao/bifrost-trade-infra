#!/usr/bin/env bash
# Phase ① — data layer: postgres node label + CNPG operator + bifrost-postgres cluster (data NS).
#
# Usage:
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml make k3s-install-data-layer-phase0
#   BIFROST_PG_APP_PASSWORD='bifrost_stg' make k3s-install-data-layer-phase0
#
# Verify: make k3s-verify-data-layer-phase0
# Authority: bifrost-platform dataLayerCatalog.ts DATA_LAYER_MIGRATION_PHASES[0]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
SECRET_NAME="${SECRET_NAME:-bifrost-postgres-app}"
BIFROST_PG_APP_USER="${BIFROST_PG_APP_USER:-bifrost}"
BIFROST_PG_APP_PASSWORD="${BIFROST_PG_APP_PASSWORD:-bifrost_stg}"
CLUSTER_READY_TIMEOUT="${CLUSTER_READY_TIMEOUT:-600}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl cluster-info >/dev/null 2>&1; then
  echo "Cannot reach cluster via ${KUBECONFIG}" >&2
  exit 1
fi

if [[ "${BIFROST_PG_APP_PASSWORD}" == "CHANGE_ME" || -z "${BIFROST_PG_APP_PASSWORD}" ]]; then
  echo "Set BIFROST_PG_APP_PASSWORD (app role for CNPG cluster)." >&2
  exit 1
fi

echo "==> Phase ① data layer (CNPG @ ${DATA_NAMESPACE})"

echo "==> 1/4 Label postgres node"
"${ROOT}/scripts/k3s/label-postgres-node.sh"

echo "==> 2/4 Install CloudNativePG operator"
"${ROOT}/scripts/k3s/install-cnpg-operator.sh"

echo "==> 3/4 App credentials secret ${SECRET_NAME}"
kubectl create namespace "${DATA_NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic "${SECRET_NAME}" \
  --namespace="${DATA_NAMESPACE}" \
  --from-literal=username="${BIFROST_PG_APP_USER}" \
  --from-literal=password="${BIFROST_PG_APP_PASSWORD}" \
  --type=kubernetes.io/basic-auth \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl label secret "${SECRET_NAME}" -n "${DATA_NAMESPACE}" \
  app.kubernetes.io/part-of=bifrost \
  app.kubernetes.io/component=postgres \
  --overwrite

echo "==> 4/4 Apply k8s/data (Cluster + Database CRs)"
kubectl apply -k "${ROOT}/k8s/data"

echo "==> Waiting for CNPG cluster ${CLUSTER_NAME} Ready"
kubectl wait --for=condition=Ready "cluster/${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" --timeout="${CLUSTER_READY_TIMEOUT}s"

echo ""
echo "Phase ① complete."
echo "  RW service: ${CLUSTER_NAME}-rw.${DATA_NAMESPACE}.svc.cluster.local:5432"
echo "  databases:  bifrost_dev · bifrost_stg · bifrost_prod (R-DV1)"
echo "  verify:     make k3s-verify-data-layer-phase0"
echo ""
echo "Next (phase ②): MinIO + barman WAL on nfs-hot — do not cutover apps until stg validation plan is ready."
