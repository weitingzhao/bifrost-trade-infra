#!/usr/bin/env bash
# Verify phase ② — CNPG HA (2 instances), MinIO backup, ScheduledBackup, cross-node anti-affinity.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

PRIMARY_NODE="${POSTGRES_NODE_NAME:-ubt-k3s-04}"
STANDBY_NODE="${POSTGRES_STANDBY_NODE_NAME:-ubt-k3s-02}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

echo "==> verify data layer phase ② (KUBECONFIG=${KUBECONFIG})"

for node in "${PRIMARY_NODE}" "${STANDBY_NODE}"; do
  role="$(kubectl get node "${node}" -o jsonpath='{.metadata.labels.node-role}' 2>/dev/null || true)"
  if [[ "${role}" == "postgres" ]]; then
    pass "node ${node} node-role=postgres"
  else
    fail "node ${node} node-role=postgres (got: ${role:-<missing>})"
  fi
done

if kubectl get deployment minio -n "${DATA_NAMESPACE}" >/dev/null 2>&1; then
  ready="$(kubectl get deployment minio -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  if [[ "${ready}" == "1" ]]; then
    pass "minio deployment ready"
  else
    fail "minio deployment readyReplicas=${ready}"
  fi
else
  fail "minio deployment missing in ${DATA_NAMESPACE}"
fi

if kubectl get secret minio-backup -n "${DATA_NAMESPACE}" >/dev/null 2>&1; then
  pass "secret minio-backup"
else
  fail "secret minio-backup missing"
fi

INSTANCES="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.spec.instances}' 2>/dev/null || true)"
if [[ "${INSTANCES}" == "2" ]]; then
  pass "cluster/${CLUSTER_NAME} spec.instances=2"
else
  fail "cluster/${CLUSTER_NAME} spec.instances=${INSTANCES:-<missing>} (want 2)"
fi

READY_INSTANCES="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyInstances}' 2>/dev/null || echo 0)"
if [[ "${READY_INSTANCES}" == "2" ]]; then
  pass "cluster readyInstances=2/2"
else
  fail "cluster readyInstances=${READY_INSTANCES}/2"
fi

if kubectl get scheduledbackup bifrost-postgres-daily -n "${DATA_NAMESPACE}" >/dev/null 2>&1; then
  pass "scheduledbackup/bifrost-postgres-daily"
else
  fail "scheduledbackup/bifrost-postgres-daily missing"
fi

BACKUP_EP="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.spec.backup.barmanObjectStore.endpointURL}' 2>/dev/null || true)"
if [[ "${BACKUP_EP}" == *"minio"* ]]; then
  pass "barmanObjectStore endpoint configured (${BACKUP_EP})"
else
  fail "barmanObjectStore endpoint missing or unexpected (${BACKUP_EP:-<empty>})"
fi

PRIMARY_POD="$(kubectl get pods -n "${DATA_NAMESPACE}" -l "cnpg.io/cluster=${CLUSTER_NAME},cnpg.io/instanceRole=primary" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
REPLICA_POD="$(kubectl get pods -n "${DATA_NAMESPACE}" -l "cnpg.io/cluster=${CLUSTER_NAME},cnpg.io/instanceRole=replica" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

if [[ -n "${PRIMARY_POD}" ]]; then
  primary_node="$(kubectl get pod "${PRIMARY_POD}" -n "${DATA_NAMESPACE}" -o jsonpath='{.spec.nodeName}' 2>/dev/null || true)"
  pass "primary pod ${PRIMARY_POD} on ${primary_node}"
  if [[ "${primary_node}" == "${PRIMARY_NODE}" ]]; then
    pass "primary on expected node ${PRIMARY_NODE}"
  else
    fail "primary on ${primary_node} (want ${PRIMARY_NODE}) — run make k3s-switchover-postgres-primary"
  fi
else
  fail "no primary pod for ${CLUSTER_NAME}"
fi

if [[ -n "${REPLICA_POD}" ]]; then
  replica_node="$(kubectl get pod "${REPLICA_POD}" -n "${DATA_NAMESPACE}" -o jsonpath='{.spec.nodeName}' 2>/dev/null || true)"
  pass "replica pod ${REPLICA_POD} on ${replica_node}"
  if [[ -n "${primary_node:-}" && "${primary_node}" == "${replica_node}" ]]; then
    fail "primary and replica on same node (${primary_node}) — anti-affinity broken"
  fi
else
  fail "no replica pod for ${CLUSTER_NAME}"
fi

echo ""
kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o wide 2>/dev/null || true
kubectl get pods -n "${DATA_NAMESPACE}" -l "cnpg.io/cluster=${CLUSTER_NAME}" -o wide 2>/dev/null || true

if [[ "${FAIL}" -ne 0 ]]; then
  echo ""
  echo "verify-data-layer-phase1: FAILED" >&2
  exit 1
fi

echo ""
echo "verify-data-layer-phase1: OK"
