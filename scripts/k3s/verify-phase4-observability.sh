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
ok = sum(1 for m in metrics if m.get("status") == "ok")
print(f"metrics ok: {ok}/{len(metrics)}")
for m in metrics:
    print(f"  {m['id']}: {m['status']}")
if ok < len(metrics):
    raise SystemExit(1)
PY

echo "==> API /metrics (in-cluster sample)"
for dep in api-monitor api-market; do
  code="$(kubectl exec -n bifrost-stg "deploy/${dep}" -- python -c "
import urllib.request
port = {'api-monitor':8765,'api-market':8772}['${dep}']
print(urllib.request.urlopen(f'http://127.0.0.1:{port}/metrics').status)
" 2>/dev/null || echo FAIL)"
  if [[ "${code}" == "200" ]]; then echo "OK ${dep} /metrics"; else echo "FAIL ${dep} /metrics=${code}" >&2; fail=1; fi
done

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
