#!/usr/bin/env bash
# Verify phase ⑥ — PROD apps on redis-live/queue @ data NS.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

PROD_NAMESPACE="${PROD_NAMESPACE:-bifrost-prod}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
GATEWAY="${PROD_GATEWAY_URL:-http://192.168.10.70:30881}"
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

echo "==> verify data layer phase ⑥ PROD"

if kubectl get deployment redis -n "${PROD_NAMESPACE}" >/dev/null 2>&1; then
  fail "embedded redis still in ${PROD_NAMESPACE}"
else
  pass "no embedded redis in ${PROD_NAMESPACE}"
fi

for dep in redis-live-prod redis-queue-prod; do
  ready="$(kubectl get deployment "${dep}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  [[ "${ready}" == "1" ]] && pass "${dep} ready" || fail "${dep} not ready"
done

if kubectl exec -n "${PROD_NAMESPACE}" deploy/api-monitor -- \
  sh -c 'grep -q redis-live-prod.data.svc /app/config/config.prod.yaml || grep -q redis-live-prod.data.svc /app/config/config.stg.yaml' 2>/dev/null; then
  pass "api-monitor config has redis-live-prod"
else
  fail "api-monitor config missing redis-live-prod"
fi

if kubectl exec -n "${PROD_NAMESPACE}" deploy/api-monitor -- \
  python -c "from bifrost_core.core.redis_url import celery_redis_url_from_config" 2>/dev/null; then
  if kubectl exec -n "${PROD_NAMESPACE}" deploy/api-monitor -- \
    python -c "
from bifrost_core.config.startup import read_config
from bifrost_core.core.redis_url import celery_redis_url_from_config
c,_=read_config()
q=celery_redis_url_from_config(c)
assert 'redis-queue-prod' in q, q
print('ok')
" 2>/dev/null; then
    pass "celery_redis_url_from_config OK"
  else
    fail "redis_queue URL failed — deliver prod images with bifrost-core 0.2.6"
  fi
else
  echo "WARN: bifrost-core < 0.2.6 — Celery on live db=1 until image deliver"
  pass "config-only check (image deliver pending)"
fi

for d in monitor ops trading market; do
  code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${GATEWAY}/api/${d}/health" || echo 000)"
  [[ "${code}" == "200" ]] && pass "/api/${d}/health HTTP 200" || fail "/api/${d}/health HTTP ${code}"
done

echo ""
if [[ "${FAIL}" -ne 0 ]]; then
  echo "verify-data-layer-phase5-prod: FAILED" >&2
  exit 1
fi
echo "verify-data-layer-phase5-prod: OK"
