#!/usr/bin/env bash
# Verify phase ④ — DEV apps on CNPG; no embedded postgres in bifrost-dev.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

DEV_NAMESPACE="${DEV_NAMESPACE:-bifrost-dev}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
DEV_DB="${DEV_DB:-bifrost_dev}"
GATEWAY="${DEV_GATEWAY_URL:-http://192.168.10.73:30882}"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

echo "==> verify data layer phase ④ DEV (KUBECONFIG=${KUBECONFIG})"

if kubectl get deployment postgres -n "${DEV_NAMESPACE}" >/dev/null 2>&1; then
  reps="$(kubectl get deployment postgres -n "${DEV_NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)"
  if [[ "${reps}" != "0" ]]; then
    fail "embedded postgres still deployed in ${DEV_NAMESPACE} (replicas=${reps})"
  else
    pass "embedded postgres scaled to 0 (prefer postgres-remove.patch)"
  fi
else
  pass "no embedded postgres deployment in ${DEV_NAMESPACE}"
fi

if kubectl get deployment redis -n "${DEV_NAMESPACE}" >/dev/null 2>&1; then
  redis_ready="$(kubectl get deployment redis -n "${DEV_NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  if [[ "${redis_ready}" == "1" ]]; then
    pass "embedded redis still active (expected until phase ⑥)"
  else
    fail "embedded redis not ready in ${DEV_NAMESPACE}"
  fi
else
  redis_host="$(kubectl get configmap bifrost-config -n "${DEV_NAMESPACE}" -o jsonpath='{.data.config\.dev\.yaml}' 2>/dev/null \
    | awk '/^redis:/{p=1;next} p&&/^[a-z_]+:/{exit} p&&/host:/{print $2; exit}' || true)"
  if [[ "${redis_host}" == *".data.svc"* ]]; then
    pass "no embedded redis; config uses data NS (${redis_host})"
  else
    fail "embedded redis missing in ${DEV_NAMESPACE} (dev stack expects in-ns redis until phase ⑥)"
  fi
fi

pg_host="$(kubectl get configmap bifrost-config -n "${DEV_NAMESPACE}" -o jsonpath='{.data.config\.dev\.yaml}' 2>/dev/null \
  | awk '/^postgres:/{p=1;next} p&&/^[a-z_]+:/{exit} p&&/host:/{print $2; exit}' || true)"
if [[ "${pg_host}" == *"bifrost-postgres-rw"* ]]; then
  pass "config postgres.host=${pg_host}"
else
  fail "config postgres.host=${pg_host:-<missing>} (want bifrost-postgres-rw.data.svc...)"
fi

primary="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
if [[ -z "${primary}" ]]; then
  fail "CNPG cluster ${CLUSTER_NAME} missing"
else
  pass "CNPG primary=${primary}"
fi

if kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${DEV_DB}" -tAc "SELECT 1" >/dev/null 2>&1; then
  pass "CNPG psql ${DEV_DB} on ${primary}"
else
  fail "CNPG cannot query ${DEV_DB}"
fi

if kubectl exec -n "${DEV_NAMESPACE}" deploy/api-monitor -- \
  grep -q 'bifrost-postgres-rw' /app/config/config.stg.yaml 2>/dev/null; then
  pass "api-monitor pod config points at CNPG"
else
  fail "api-monitor pod config not on CNPG endpoint"
fi

tables="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${DEV_DB}" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo -1)"
if [[ "${tables}" =~ ^[0-9]+$ ]] && [[ "${tables}" -gt 0 ]]; then
  pass "CNPG ${DEV_DB} has public tables (count=${tables})"
else
  fail "CNPG ${DEV_DB} schema empty or unreadable"
fi

mon_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${GATEWAY}/api/monitor/status" || echo 000)"
if [[ "${mon_code}" == "200" ]]; then
  pass "Vision V1 gateway ${GATEWAY}/api/monitor/status HTTP 200"
else
  fail "gateway /api/monitor/status HTTP ${mon_code}"
fi

fe_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${GATEWAY}/" || echo 000)"
if [[ "${fe_code}" == "200" ]]; then
  pass "Vision V1 frontend ${GATEWAY}/ HTTP 200"
else
  fail "frontend HTTP ${fe_code}"
fi

echo ""
if [[ "${FAIL}" -ne 0 ]]; then
  echo "verify-data-layer-phase3-dev: FAILED" >&2
  exit 1
fi
echo "verify-data-layer-phase3-dev: OK"
