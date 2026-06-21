#!/usr/bin/env bash
# Verify Phase ⑥ data NS Redis targets (before env cutover).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
export KUBECONFIG
FAIL=0

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }

check_policy() {
  local dep="$1"
  local want="$2"
  local got
  got="$(kubectl exec -n "${DATA_NAMESPACE}" "deploy/${dep}" -- \
    redis-cli CONFIG GET maxmemory-policy 2>/dev/null | tail -1 || true)"
  if [[ "${got}" == "${want}" ]]; then
    pass "${dep} maxmemory-policy=${got}"
  else
    fail "${dep} maxmemory-policy=${got:-<missing>} (want ${want})"
  fi
}

echo "==> verify data layer phase ⑥ data NS Redis (KUBECONFIG=${KUBECONFIG})"

for dep in redis-live-stg redis-queue-stg redis-live-prod redis-queue-prod redis-dev; do
  if kubectl get deployment "${dep}" -n "${DATA_NAMESPACE}" >/dev/null 2>&1; then
    ready="$(kubectl get deployment "${dep}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
    if [[ "${ready}" == "1" ]]; then
      pass "${dep} ready"
      if kubectl exec -n "${DATA_NAMESPACE}" "deploy/${dep}" -- redis-cli ping 2>/dev/null | grep -q PONG; then
        pass "${dep} PING"
      else
        fail "${dep} PING failed"
      fi
    else
      fail "${dep} not ready (readyReplicas=${ready})"
    fi
  else
    fail "deployment/${dep} missing in ${DATA_NAMESPACE}"
  fi
done

check_policy redis-live-stg noeviction
check_policy redis-queue-stg allkeys-lru
check_policy redis-live-prod noeviction
check_policy redis-queue-prod allkeys-lru
check_policy redis-dev noeviction

echo ""
if [[ "${FAIL}" -ne 0 ]]; then
  echo "verify-data-layer-phase5-data: FAILED" >&2
  exit 1
fi
echo "verify-data-layer-phase5-data: OK"
