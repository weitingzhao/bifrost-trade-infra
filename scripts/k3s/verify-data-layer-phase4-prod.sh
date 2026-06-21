#!/usr/bin/env bash
# Verify phase ⑤ — PROD K3s apps on CNPG; legacy .80 no longer required for bifrost-prod.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

PROD_NAMESPACE="${PROD_NAMESPACE:-bifrost-prod}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
PROD_DB="${PROD_DB:-bifrost_prod}"
GATEWAY="${PROD_GATEWAY_URL:-http://192.168.10.70:30881}"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

echo "==> verify data layer phase ⑤ PROD (KUBECONFIG=${KUBECONFIG})"

if kubectl get deployment postgres -n "${PROD_NAMESPACE}" >/dev/null 2>&1; then
  reps="$(kubectl get deployment postgres -n "${PROD_NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)"
  if [[ "${reps}" != "0" ]]; then
    fail "embedded postgres still deployed in ${PROD_NAMESPACE} (replicas=${reps})"
  else
    pass "embedded postgres scaled to 0 or pending removal"
  fi
else
  pass "no embedded postgres deployment in ${PROD_NAMESPACE}"
fi

pg_host="$(kubectl get configmap bifrost-config -n "${PROD_NAMESPACE}" -o jsonpath='{.data.config\.prod\.yaml}' 2>/dev/null \
  | awk '/^postgres:/{p=1;next} p&&/^[a-z_]+:/{exit} p&&/host:/{print $2; exit}' || true)"
pg_db="$(kubectl get configmap bifrost-config -n "${PROD_NAMESPACE}" -o jsonpath='{.data.config\.prod\.yaml}' 2>/dev/null \
  | awk '/^postgres:/{p=1;next} p&&/^[a-z_]+:/{exit} p&&/database:/{print $2; exit}' || true)"

if [[ "${pg_host}" == *"bifrost-postgres-rw"* ]]; then
  pass "config postgres.host=${pg_host}"
else
  fail "config postgres.host=${pg_host:-<missing>} (want bifrost-postgres-rw.data.svc...)"
fi

if [[ "${pg_db}" == "${PROD_DB}" ]]; then
  pass "config postgres.database=${pg_db}"
else
  fail "config postgres.database=${pg_db:-<missing>} (want ${PROD_DB})"
fi

primary="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
if [[ -z "${primary}" ]]; then
  fail "CNPG cluster ${CLUSTER_NAME} missing"
else
  pass "CNPG primary=${primary}"
fi

if kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${PROD_DB}" -tAc "SELECT 1" >/dev/null 2>&1; then
  pass "CNPG psql ${PROD_DB} on ${primary}"
else
  fail "CNPG cannot query ${PROD_DB}"
fi

if kubectl exec -n "${PROD_NAMESPACE}" deploy/api-monitor -- \
  grep -q 'bifrost-postgres-rw' /app/config/config.stg.yaml 2>/dev/null; then
  pass "api-monitor pod config points at CNPG"
else
  fail "api-monitor pod config not on CNPG endpoint"
fi

tables="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${PROD_DB}" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo -1)"
if [[ "${tables}" =~ ^[0-9]+$ ]] && [[ "${tables}" -gt 0 ]]; then
  pass "CNPG ${PROD_DB} public tables (count=${tables})"
else
  fail "CNPG ${PROD_DB} schema empty or unreadable"
fi

dc_count="$(kubectl exec -n "${DATA_NAMESPACE}" "${primary}" -- \
  psql -U postgres -d "${PROD_DB}" -tAc "SELECT count(*) FROM daemon_control" 2>/dev/null || echo -1)"
if [[ "${dc_count}" =~ ^[0-9]+$ ]] && [[ "${dc_count}" -ge 0 ]]; then
  pass "daemon_control readable (rows=${dc_count})"
else
  fail "daemon_control query failed"
fi

mon_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "${GATEWAY}/api/monitor/status" || echo 000)"
if [[ "${mon_code}" == "200" ]]; then
  pass "prod gateway ${GATEWAY}/api/monitor/status HTTP 200"
else
  fail "gateway /api/monitor/status HTTP ${mon_code}"
fi

fe_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "${GATEWAY}/" || echo 000)"
if [[ "${fe_code}" == "200" ]]; then
  pass "prod frontend ${GATEWAY}/ HTTP 200"
else
  fail "frontend HTTP ${fe_code}"
fi

for d in trading portfolio market ops; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 "${GATEWAY}/api/${d}/health" || echo 000)"
  if [[ "${code}" == "200" ]]; then
    pass "api/${d}/health HTTP 200"
  else
    fail "api/${d}/health HTTP ${code}"
  fi
done

echo ""
if [[ "${FAIL}" -ne 0 ]]; then
  echo "verify-data-layer-phase4-prod: FAILED" >&2
  exit 1
fi
echo "verify-data-layer-phase4-prod: OK"
