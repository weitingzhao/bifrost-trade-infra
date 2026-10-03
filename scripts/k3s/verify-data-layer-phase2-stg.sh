#!/usr/bin/env bash
# Verify phase ③ — STG apps on CNPG; no embedded postgres in bifrost-stg.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
STG_DB="${STG_DB:-bifrost_stg}"
PG_USER="${PG_USER:-bifrost}"
GATEWAY="${STG_GATEWAY_URL:-http://192.168.10.73:30880}"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

echo "==> verify data layer phase ③ STG (KUBECONFIG=${KUBECONFIG})"

if kubectl get deployment postgres -n "${STG_NAMESPACE}" >/dev/null 2>&1; then
  reps="$(kubectl get deployment postgres -n "${STG_NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)"
  if [[ "${reps}" != "0" ]]; then
    fail "embedded postgres still deployed in ${STG_NAMESPACE} (replicas=${reps})"
  else
    pass "embedded postgres scaled to 0 (prefer postgres-remove.patch)"
  fi
else
  pass "no embedded postgres deployment in ${STG_NAMESPACE}"
fi

pg_host="$(kubectl get configmap bifrost-config -n "${STG_NAMESPACE}" -o jsonpath='{.data.config\.stg\.yaml}' 2>/dev/null \
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
  psql -U postgres -d "${STG_DB}" -tAc "SELECT 1" >/dev/null 2>&1; then
  pass "CNPG psql ${STG_DB} on ${primary}"
else
  fail "CNPG cannot query ${STG_DB}"
fi

if kubectl exec -n "${STG_NAMESPACE}" deploy/api-monitor -- \
  grep -q 'bifrost-postgres-rw' /app/config/config.stg.yaml 2>/dev/null; then
  pass "api-monitor pod config points at CNPG"
else
  fail "api-monitor pod config not on CNPG endpoint"
fi

dc_count="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${STG_DB}" -tAc "SELECT count(*) FROM daemon_control" 2>/dev/null || echo -1)"
if [[ "${dc_count}" =~ ^[0-9]+$ ]] && [[ "${dc_count}" -ge 0 ]]; then
  pass "daemon_control readable (rows=${dc_count})"
else
  fail "daemon_control query failed"
fi

mon_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${GATEWAY}/api/monitor/status" || echo 000)"
if [[ "${mon_code}" == "200" ]]; then
  pass "gateway /api/monitor/status HTTP 200"
else
  fail "gateway /api/monitor/status HTTP ${mon_code}"
fi

echo ""
if [[ "${FAIL}" -ne 0 ]]; then
  echo "verify-data-layer-phase2-stg: FAILED" >&2
  exit 1
fi
echo "verify-data-layer-phase2-stg: OK"
