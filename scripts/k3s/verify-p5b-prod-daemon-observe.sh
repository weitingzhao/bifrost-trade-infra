#!/usr/bin/env bash
# P5B — Prod daemon observe mode: daemon runs with HARD_NO_ORDERS (no live IB orders).
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

daemon_has_hard_no_orders() {
  kubectl get deployment/daemon -n "${NS}" -o json \
    | grep -q '"name"[[:space:]]*:[[:space:]]*"BIFROST_DAEMON_HARD_NO_ORDERS"'
}

echo "==> P5B prod daemon observe verify (@ ${GATEWAY_HOST})"

echo "==> [1/6] daemon scaled up (replicas>=1) with HARD_NO_ORDERS env"
daemon_rep="$(kubectl get deployment/daemon -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)"
if [[ "${daemon_rep}" -lt 1 ]]; then
  die "daemon replicas=${daemon_rep} (want >=1 after P5B)"
else
  pass "daemon replicas=${daemon_rep}"
fi
if ! daemon_has_hard_no_orders; then
  die "daemon missing env BIFROST_DAEMON_HARD_NO_ORDERS"
else
  pass "daemon has BIFROST_DAEMON_HARD_NO_ORDERS"
fi
hard_val="$(kubectl get deployment/daemon -n "${NS}" -o jsonpath='{.spec.template.spec.containers[?(@.name=="daemon")].env[?(@.name=="BIFROST_DAEMON_HARD_NO_ORDERS")].value}' 2>/dev/null || echo "")"
if [[ "${hard_val}" != "1" ]]; then
  die "BIFROST_DAEMON_HARD_NO_ORDERS value=${hard_val:-<empty>} (want 1)"
else
  pass "BIFROST_DAEMON_HARD_NO_ORDERS=1"
fi

echo "==> [2/6] daemon rollout ready"
if ! kubectl rollout status deployment/daemon -n "${NS}" --timeout=300s >/dev/null 2>&1; then
  die "daemon rollout not ready"
else
  ready="$(kubectl get deployment/daemon -n "${NS}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  pass "daemon ready=${ready}"
fi

echo "==> [3/6] daemon pod logs show HARD_NO_ORDERS latch"
log_snip=""
for p in $(kubectl get pods -n "${NS}" -l app.kubernetes.io/name=daemon -o name 2>/dev/null); do
  log_snip+="$(kubectl logs -n "${NS}" "${p}" -c daemon --tail=300 2>/dev/null || true)"$'\n'
done
if echo "${log_snip}" | grep -qi 'BIFROST_DAEMON_HARD_NO_ORDERS'; then
  pass "daemon logs mention HARD_NO_ORDERS"
else
  die "daemon logs missing HARD_NO_ORDERS (worker image may need rebuild with order_safety)"
fi

echo "==> [4/6] monitor API reports daemon heartbeat"
mon_json="$(gateway_curl "${GATEWAY}/api/monitor/status" 2>/dev/null || echo '{}')"
if echo "${mon_json}" | grep -qE '"daemon_|"state"|"fsm"'; then
  pass "monitor /status responds with daemon fields"
else
  die "monitor /status missing expected daemon payload"
fi

echo "==> [5/6] P5A Celery invariants still hold"
celery_rep="$(kubectl get deployment/celery-worker -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)"
if [[ "${celery_rep}" -lt 1 ]]; then
  die "celery-worker replicas=${celery_rep} (want >=1)"
else
  pass "celery-worker replicas=${celery_rep}"
fi

echo "==> [6/6] P3 cutover invariants (Traefik entry, legacy port down)"
if ! PROD_VERIFY_FULL=0 "${ROOT}/scripts/k3s/verify-p3-prod-cutover.sh"; then
  die "P3 prod cutover verify regressed"
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "P5B prod daemon observe verify: FAIL" >&2
  exit 1
fi
echo "P5B prod daemon observe verify: PASS"
