#!/usr/bin/env bash
# Phase 4 observability acceptance — STG cluster smoke.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
PLATFORM_API="${PLATFORM_API:-http://192.168.10.73:30878}"
export KUBECONFIG

fail=0

echo "==> Layer B"
layer_b="$(curl -sf "${PLATFORM_API}/api/v1/cluster/observability" | python3 -c "import json,sys; print(json.load(sys.stdin).get('layer_b_status',''))")"
if [[ "${layer_b}" == "ready" ]]; then echo "OK layer_b_status=ready"; else echo "FAIL layer_b_status=${layer_b}" >&2; fail=1; fi

echo "==> Telemetry overview (bifrost-stg)"
telemetry="$(curl -sf "${PLATFORM_API}/api/v1/telemetry/overview?ns=bifrost-stg")"
python3 - <<'PY' "${telemetry}" || fail=1
import json, sys
d = json.loads(sys.argv[1])
metrics = d.get("metrics") or []

def acceptable(metric):
    status = metric.get("status")
    if status == "ok":
        return True
    # Single-primary CNPG has no replication peers — empty lag is expected.
    if metric.get("id") == "pg_replication_lag" and status == "empty":
        return True
    return False

ok = sum(1 for m in metrics if acceptable(m))
print(f"metrics ok: {ok}/{len(metrics)}")
for m in metrics:
    print(f"  {m['id']}: {m['status']}")
if ok < len(metrics):
    raise SystemExit(1)
PY

echo "==> API /metrics (in-cluster sample)"
metrics_ok=0
check_metrics() {
  local dep="$1"
  local port="$2"
  local ready
  ready="$(kubectl get deploy "${dep}" -n bifrost-stg -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"
  if [[ "${ready}" != "1" ]]; then
    echo "SKIP ${dep} /metrics (deployment not ready)"
    return 0
  fi
  local code
  code="$(kubectl exec -n bifrost-stg "deploy/${dep}" -- python -c "
import urllib.request
print(urllib.request.urlopen('http://127.0.0.1:${port}/metrics').status)
" 2>/dev/null || echo FAIL)"
  if [[ "${code}" == "200" ]]; then
    echo "OK ${dep} /metrics"
    metrics_ok=1
  else
    echo "WARN ${dep} /metrics=${code}" >&2
  fi
}
check_metrics api-monitor 8765
check_metrics api-market 8772
check_metrics api-trading 8769
check_metrics api-ops 8768
if [[ "${metrics_ok}" -ne 1 ]]; then
  echo "FAIL no ready API deployment returned /metrics HTTP 200" >&2
  fail=1
fi

echo "==> Monitoring scrape CRDs"
check_crd() {
  if kubectl get "$1" "$2" -n "$3" >/dev/null 2>&1; then echo "OK $2 ($3)"; else echo "FAIL missing $2 in $3" >&2; fail=1; fi
}
check_crd servicemonitor.monitoring.coreos.com bifrost-trade-apis monitoring
check_crd servicemonitor.monitoring.coreos.com bifrost-redis monitoring
check_crd podmonitor.monitoring.coreos.com bifrost-postgres monitoring

if [[ "${fail}" -ne 0 ]]; then
  echo "Phase 4 observability verify FAILED" >&2
  exit 1
fi
echo "Phase 4 observability verify PASS"
