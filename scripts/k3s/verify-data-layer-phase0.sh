#!/usr/bin/env bash
# Verify phase ① data layer — postgres node, CNPG operator, bifrost-postgres cluster.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

POSTGRES_NODE="${POSTGRES_NODE_NAME:-ubt-k3s-02}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

echo "==> verify data layer phase ① (KUBECONFIG=${KUBECONFIG})"

role="$(kubectl get node "${POSTGRES_NODE}" -o jsonpath='{.metadata.labels.node-role}' 2>/dev/null || true)"
if [[ "${role}" == "postgres" ]]; then
  pass "node ${POSTGRES_NODE} node-role=postgres"
else
  fail "node ${POSTGRES_NODE} node-role=postgres (got: ${role:-<missing>})"
fi

if kubectl get deployment cnpg-controller-manager -n cnpg-system >/dev/null 2>&1; then
  pass "cnpg-controller-manager deployment"
else
  fail "cnpg-controller-manager not found in cnpg-system"
fi

if kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" >/dev/null 2>&1; then
  pass "cluster/${CLUSTER_NAME} in ${DATA_NAMESPACE}"
else
  fail "cluster/${CLUSTER_NAME} missing"
fi

if kubectl get secret bifrost-postgres-app -n "${DATA_NAMESPACE}" >/dev/null 2>&1; then
  pass "secret bifrost-postgres-app"
else
  fail "secret bifrost-postgres-app missing"
fi

for db in bifrost-dev bifrost-stg bifrost-prod; do
  if kubectl get database "${db}" -n "${DATA_NAMESPACE}" >/dev/null 2>&1; then
    pass "database/${db}"
  else
    fail "database/${db} missing"
  fi
done

PRIMARY_POD="$(kubectl get pods -n "${DATA_NAMESPACE}" -l "cnpg.io/cluster=${CLUSTER_NAME},role=primary" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -n "${PRIMARY_POD}" ]]; then
  phase="$(kubectl get pod "${PRIMARY_POD}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [[ "${phase}" == "Running" ]]; then
    pass "primary pod ${PRIMARY_POD} Running"
  else
    fail "primary pod ${PRIMARY_POD} phase=${phase:-unknown}"
  fi
else
  fail "no primary pod for cluster ${CLUSTER_NAME}"
fi

RW="${CLUSTER_NAME}-rw.${DATA_NAMESPACE}.svc.cluster.local"
echo ""
echo "Connection (in-cluster): host=${RW} port=5432 user=bifrost db=bifrost_stg|bifrost_dev|bifrost_prod"
kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o wide 2>/dev/null || true
kubectl get pods -n "${DATA_NAMESPACE}" -l "cnpg.io/cluster=${CLUSTER_NAME}" -o wide 2>/dev/null || true

if [[ "${FAIL}" -ne 0 ]]; then
  echo ""
  echo "verify-data-layer-phase0: FAILED" >&2
  exit 1
fi

echo ""
echo "verify-data-layer-phase0: OK"
