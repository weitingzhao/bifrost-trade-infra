#!/usr/bin/env bash
# P5A — Prod Celery data pipeline restore (daemon stays 0 per R-DV3 until P5B).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATEWAY_HOST="${PROD_GATEWAY_HOST:-trade.bifrost.lan}"
GATEWAY_IP="${PROD_GATEWAY_IP:-192.168.10.70}"
GATEWAY="${PROD_GATEWAY_URL:-http://${GATEWAY_IP}/}"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
NS="${PROD_NAMESPACE:-bifrost-prod}"

export KUBECONFIG

fail=0
pass() { echo "OK $*"; }
die() { echo "FAIL $*" >&2; fail=1; }

gateway_curl() {
  curl -sf -H "Host: ${GATEWAY_HOST}" --connect-timeout 8 "$@"
}

echo "==> P5A prod Celery verify (@ ${GATEWAY_HOST})"

echo "==> [1/5] daemon still scaled to 0 (R-DV3 / P5B gate)"
daemon_rep="$(kubectl get deployment/daemon -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo missing)"
if [[ "${daemon_rep}" != "0" ]]; then
  die "daemon replicas=${daemon_rep} (want 0 until P5B)"
else
  pass "daemon replicas=0"
fi

echo "==> [2/5] celery-worker rollout (replicas>=1)"
celery_rep="$(kubectl get deployment/celery-worker -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)"
if [[ "${celery_rep}" -lt 1 ]]; then
  die "celery-worker replicas=${celery_rep} (want >=1 after P5A)"
else
  pass "celery-worker replicas=${celery_rep}"
fi
if ! kubectl rollout status deployment/celery-worker -n "${NS}" --timeout=300s >/dev/null 2>&1; then
  die "celery-worker rollout not ready"
else
  ready="$(kubectl get deployment/celery-worker -n "${NS}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  pass "celery-worker ready=${ready}"
fi

echo "==> [3/5] flower rollout"
if ! kubectl rollout status deployment/flower -n "${NS}" --timeout=120s >/dev/null 2>&1; then
  die "flower rollout not ready"
else
  pass "flower ready"
fi

echo "==> [4/5] api-ops health (kubernetes executor)"
ops_json="$(gateway_curl "${GATEWAY}/api/ops/health" 2>/dev/null || echo '{}')"
if echo "${ops_json}" | grep -q '"executor_mode"[[:space:]]*:[[:space:]]*"kubernetes"'; then
  pass "api-ops executor_mode=kubernetes"
else
  die "api-ops health missing executor_mode=kubernetes"
fi
if echo "${ops_json}" | grep -q '"k8s_reachable"[[:space:]]*:[[:space:]]*true'; then
  pass "api-ops k8s_reachable=true"
else
  die "api-ops k8s_reachable not true"
fi

echo "==> [5/5] P3 cutover invariants (daemon=0, Traefik entry)"
if ! "${ROOT}/scripts/k3s/verify-p3-prod-cutover.sh"; then
  die "P3 prod cutover verify regressed"
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "P5A prod Celery verify: FAIL" >&2
  exit 1
fi
echo "P5A prod Celery verify: PASS"
