#!/usr/bin/env bash
# Verify phase ⑥ — STG apps on redis-live/queue @ data NS; no embedded redis.
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

for dep in redis-live-stg redis-queue-stg; do
  ready="$(kubectl get deployment "${dep}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  if [[ "${ready}" == "1" ]]; then
    pass "data NS ${dep} ready"
  else
    fail "data NS ${dep} not ready"
  fi
done

live_host="$(kubectl get configmap bifrost-config -n "${STG_NAMESPACE}" -o jsonpath='{.data.config\.stg\.yaml}' 2>/dev/null \
  | awk '/^redis:/{p=1;next} p&&/^redis_queue:/{exit} p&&/host:/{print $2; exit}' || true)"
queue_host="$(kubectl get configmap bifrost-config -n "${STG_NAMESPACE}" -o jsonpath='{.data.config\.stg\.yaml}' 2>/dev/null \
  | awk '/^redis_queue:/{p=1;next} p&&/host:/{print $2; exit}' || true)"

if [[ "${live_host}" == *"redis-live-stg"* ]]; then
  pass "config redis.host=${live_host}"
else
  fail "config redis.host=${live_host:-<missing>} (want redis-live-stg.data.svc...)"
fi

if [[ "${queue_host}" == *"redis-queue-stg"* ]]; then
  pass "config redis_queue.host=${queue_host}"
else
  fail "config redis_queue.host=${queue_host:-<missing>} (want redis-queue-stg.data.svc...)"
fi

if kubectl exec -n "${STG_NAMESPACE}" deploy/api-monitor -- \
  grep -q 'redis-live-stg.data.svc' /app/config/config.stg.yaml 2>/dev/null && \
  kubectl exec -n "${STG_NAMESPACE}" deploy/api-monitor -- \
  grep -q 'redis-queue-stg.data.svc' /app/config/config.stg.yaml 2>/dev/null; then
  pass "api-monitor config has redis-live + redis-queue hosts"
else
  fail "api-monitor config missing data NS redis hosts"
fi

if kubectl exec -n "${STG_NAMESPACE}" deploy/api-monitor -- \
  python -c "from bifrost_core.core.redis_url import celery_redis_url_from_config" 2>/dev/null; then
  if kubectl exec -n "${STG_NAMESPACE}" deploy/api-monitor -- \
    python -c "
from bifrost_core.config.startup import read_config
from bifrost_core.core.redis_url import redis_url_from_config, celery_redis_url_from_config
c,_=read_config()
live=redis_url_from_config(c) or ''
queue=celery_redis_url_from_config(c)
assert 'redis-live-stg' in live, live
assert 'redis-queue-stg' in queue, queue
print('ok')
" 2>/dev/null; then
    pass "celery_redis_url_from_config OK (bifrost-core >= 0.2.6)"
  else
    fail "redis_queue URL resolution failed — run make k3s-deliver-stg after core/worker bump"
  fi
else
  echo "WARN: bifrost-core < 0.2.6 — Celery still uses redis db=1 on live host until image deliver"
  pass "config-only check (image deliver pending for celery split)"
fi

mon_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${GATEWAY}/api/monitor/status" || echo 000)"
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
