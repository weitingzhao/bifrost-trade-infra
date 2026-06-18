#!/usr/bin/env bash
# verify-placement-governance.sh — G5 closure checks for workload placement.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/config}"
PLATFORM_API="${PLATFORM_API:-http://127.0.0.1:8780}"
CICD_NS="${CICD_NS:-cicd}"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

echo "== Placement governance verify =="
echo "KUBECONFIG=$KUBECONFIG"
echo "PLATFORM_API=$PLATFORM_API"

# Tekton pipelines present
for p in bifrost-deliver-stg bifrost-build-stg bifrost-build-frontend-stg; do
  kubectl --kubeconfig "$KUBECONFIG" get pipeline "$p" -n "$CICD_NS" >/dev/null 2>&1 \
    || fail "Pipeline $p not found in $CICD_NS"
done
echo "OK Tekton Kaniko pipelines registered"

# Placement API — amd64 pool and violations
placement_json="$(curl -sf "${PLATFORM_API}/api/v1/cluster/placement")" || fail "GET /cluster/placement unreachable"
amd64_ready="$(echo "$placement_json" | python3 -c "
import json,sys
d=json.load(sys.stdin)
pool=next((p for p in d.get('pools',[]) if p.get('id')=='amd64_ci'),{})
print(pool.get('nodes_ready',0))
")"
critical="$(echo "$placement_json" | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(sum(1 for v in d.get('violations',[]) if v.get('severity')=='critical'))
")"

if [[ "$amd64_ready" -lt 1 ]]; then
  fail "amd64_ci pool has 0 Ready nodes (need amd64 for Kaniko)"
fi
echo "OK amd64_ci Ready nodes: $amd64_ready"

if [[ "$critical" -gt 0 ]]; then
  echo "$placement_json" | python3 -c "
import json,sys
d=json.load(sys.stdin)
for v in d.get('violations',[]):
  if v.get('severity')=='critical':
    print('  -', v.get('message',''))
" >&2
  fail "$critical critical placement violation(s)"
fi
echo "OK placement violations: 0 critical"

# Deliver-stg preflight
preflight_json="$(curl -sf "${PLATFORM_API}/api/v1/delivery/pipelines/bifrost-deliver-stg/preflight")" \
  || fail "GET delivery preflight unreachable"
build_ready="$(echo "$preflight_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('build_ready',False))")"
if [[ "$build_ready" != "True" ]]; then
  reason="$(echo "$preflight_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('reason',''))")"
  fail "deliver-stg preflight blocked: $reason"
fi
echo "OK bifrost-deliver-stg preflight build_ready"

echo "PASS placement governance verify"
