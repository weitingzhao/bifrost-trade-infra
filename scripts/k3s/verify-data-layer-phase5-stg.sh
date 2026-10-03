#!/usr/bin/env bash
# Verify phase ⑥ — STG apps on redis-live @ data NS; no embedded redis.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
GATEWAY="${STG_GATEWAY_URL:-http://192.168.10.73:30880}"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

echo "==> verify data layer phase ⑥ STG (KUBECONFIG=${KUBECONFIG})"

if kubectl get deployment redis -n "${STG_NAMESPACE}" >/dev/null 2>&1; then
  reps="$(kubectl get deployment redis -n "${STG_NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)"
  if [[ "${reps}" != "0" ]]; then
    fail "embedded redis still deployed in ${STG_NAMESPACE} (replicas=${reps})"
  else
    pass "embedded redis scaled to 0"
  fi
else
  pass "no embedded redis deployment in ${STG_NAMESPACE}"
fi

for dep in redis-live-stg; do
  ready="$(kubectl get deployment "${dep}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  if [[ "${ready}" == "1" ]]; then
    pass "data NS ${dep} ready"
  else
    fail "data NS ${dep} not ready"
  fi
done

live_host="$(kubectl get configmap bifrost-config -n "${STG_NAMESPACE}" -o jsonpath='{.data.config\.stg\.yaml}' 2>/dev/null \
  | awk '/^redis:/{p=1;next} p&&/^[^[:space:]]/{exit} p&&/host:/{print $2; exit}' || true)"

if [[ "${live_host}" == *"redis-live-stg"* ]]; then
  pass "config redis.host=${live_host}"
else
  fail "config redis.host=${live_host:-<missing>} (want redis-live-stg.data.svc...)"
fi

if kubectl exec -n "${STG_NAMESPACE}" deploy/api-monitor -- \
  grep -q 'redis-live-stg.data.svc' /app/config/config.stg.yaml 2>/dev/null; then
  pass "api-monitor config has redis-live host"
else
  fail "api-monitor config missing data NS redis-live host"
fi

mon_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 30 "${GATEWAY}/api/monitor/status" || echo 000)"
if [[ "${mon_code}" == "200" ]]; then
  pass "gateway /api/monitor/status HTTP 200"
else
  fail "gateway /api/monitor/status HTTP ${mon_code}"
fi

echo ""
if [[ "${FAIL}" -ne 0 ]]; then
  echo "verify-data-layer-phase5-stg: FAILED" >&2
  exit 1
fi
echo "verify-data-layer-phase5-stg: OK"
