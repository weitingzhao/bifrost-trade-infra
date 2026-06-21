#!/usr/bin/env bash
# Verify phase ⑥ — DEV apps on redis-dev @ data NS.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

DEV_NAMESPACE="${DEV_NAMESPACE:-bifrost-dev}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
GATEWAY="${DEV_GATEWAY_URL:-http://192.168.10.73:30882}"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

echo "==> verify data layer phase ⑥ DEV"

if kubectl get deployment redis -n "${DEV_NAMESPACE}" >/dev/null 2>&1; then
  fail "embedded redis still in ${DEV_NAMESPACE}"
else
  pass "no embedded redis in ${DEV_NAMESPACE}"
fi

ready="$(kubectl get deployment redis-dev -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
[[ "${ready}" == "1" ]] && pass "redis-dev ready" || fail "redis-dev not ready"

if kubectl exec -n "${DEV_NAMESPACE}" deploy/api-monitor -- \
  sh -c 'grep -q redis-dev.data.svc /app/config/config.dev.yaml || grep -q redis-dev.data.svc /app/config/config.stg.yaml' 2>/dev/null; then
  pass "api-monitor config points at redis-dev"
else
  fail "api-monitor config not on redis-dev"
fi

mon_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${GATEWAY}/api/monitor/status" || echo 000)"
[[ "${mon_code}" == "200" ]] && pass "gateway HTTP 200" || fail "gateway HTTP ${mon_code}"

echo ""
if [[ "${FAIL}" -ne 0 ]]; then
  echo "verify-data-layer-phase5-dev: FAILED" >&2
  exit 1
fi
echo "verify-data-layer-phase5-dev: OK"
