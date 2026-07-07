#!/usr/bin/env bash
# Phase 5 observability acceptance — Loki, alerting, dashboard, Layer B Loki probe.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
PLATFORM_API="${PLATFORM_API:-http://192.168.10.73:30878}"
MONITORING_NS="${MONITORING_NS:-monitoring}"
export KUBECONFIG

fail=0

echo "==> Loki workload (monitoring NS)"
loki_ok=0
for kind_name in statefulset/loki daemonset/promtail; do
  kind="${kind_name%%/*}"
  name="${kind_name#*/}"
  if kubectl get "${kind}" "${name}" -n "${MONITORING_NS}" >/dev/null 2>&1; then
    ready="$(kubectl get "${kind}" "${name}" -n "${MONITORING_NS}" -o jsonpath='{.status.readyReplicas}{.status.numberReady}' 2>/dev/null || echo 0)"
    if [[ "${ready}" != "0" && -n "${ready}" ]]; then
      echo "OK ${kind}/${name} ready"
      loki_ok=1
    else
      echo "FAIL ${kind}/${name} not ready" >&2
      fail=1
    fi
  fi
done
if [[ "${loki_ok}" -eq 0 ]]; then
  echo "FAIL no Loki workload found in ${MONITORING_NS}" >&2
  fail=1
fi

echo "==> Layer B Loki component (no longer planned-only)"
obs_json="$(curl -sf "${PLATFORM_API}/api/v1/cluster/observability" || echo '{}')"
python3 - <<'PY' "${obs_json}" || fail=1
import json, sys
d = json.loads(sys.argv[1])
components = d.get("components") or []
loki = next((c for c in components if c.get("id") == "loki"), None)
if not loki:
    raise SystemExit("FAIL loki component missing from observability probe")
phase = loki.get("phase", "")
status = loki.get("status", "")
ready_like = status.lower() in ("ready", "degraded")
if not ready_like:
    raise SystemExit(f"FAIL loki not detected as ready (phase={phase} status={status})")
print(f"OK loki detected status={status} phase={phase}")
PY

echo "==> PrometheusRule bifrost-alerting-rules"
if kubectl get prometheusrule bifrost-alerting-rules -n "${MONITORING_NS}" >/dev/null 2>&1; then
  rule_count="$(kubectl get prometheusrule bifrost-alerting-rules -n "${MONITORING_NS}" -o jsonpath='{.spec.groups[0].rules}' | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))')"
  if [[ "${rule_count}" -ge 6 ]]; then
    echo "OK prometheusrule bifrost-alerting-rules (${rule_count} rules)"
  else
    echo "FAIL prometheusrule has ${rule_count} rules, want >=6" >&2
    fail=1
  fi
else
  echo "FAIL missing prometheusrule bifrost-alerting-rules" >&2
  fail=1
fi

echo "==> Alertmanager bifrost-ops-agent receiver"
am_secret=""
for s in \
  alertmanager-kube-prometheus-stack-alertmanager-generated \
  alertmanager-kube-prometheus-stack-generated \
  alertmanager-kube-prometheus-stack
do
  if kubectl get secret "${s}" -n "${MONITORING_NS}" >/dev/null 2>&1; then
    am_secret="${s}"
    break
  fi
done
if [[ -z "${am_secret}" ]]; then
  echo "WARN alertmanager secret not found — skipping receiver check" >&2
else
  am_cfg="$(kubectl get secret "${am_secret}" -n "${MONITORING_NS}" -o jsonpath='{.data}' 2>/dev/null | python3 -c "
import json,sys,base64,gzip,io
d=json.load(sys.stdin)
raw=base64.b64decode(d.get('alertmanager.yaml.gz') or d.get('alertmanager.yaml') or b'')
try:
  print(gzip.decompress(raw).decode())
except Exception:
  print(raw.decode())
" 2>/dev/null || echo "")"
  if echo "${am_cfg}" | grep -q 'bifrost-ops-agent'; then
    echo "OK alertmanager config contains bifrost-ops-agent receiver"
  else
    echo "FAIL alertmanager config missing bifrost-ops-agent receiver" >&2
    fail=1
  fi
  if echo "${am_cfg}" | grep -q 'bearer_token_file'; then
    echo "OK alertmanager webhook bearer_token_file configured"
  else
    echo "FAIL alertmanager webhook missing bearer_token_file" >&2
    fail=1
  fi
fi

echo "==> Alertmanager webhook auth secret"
if kubectl get secret alertmanager-webhook-auth -n "${MONITORING_NS}" >/dev/null 2>&1; then
  echo "OK secret alertmanager-webhook-auth"
else
  echo "FAIL missing secret alertmanager-webhook-auth" >&2
  fail=1
fi

echo "==> Ops Agent webhook closed loop (Alertmanager → platform-api → Audit)"
webhook_token=""
if kubectl get secret alertmanager-webhook-auth -n "${MONITORING_NS}" >/dev/null 2>&1; then
  webhook_token="$(kubectl get secret alertmanager-webhook-auth -n "${MONITORING_NS}" -o jsonpath='{.data.token}' | base64 -d)"
fi
if [[ -z "${webhook_token}" ]]; then
  echo "FAIL cannot read alertmanager-webhook-auth token" >&2
  fail=1
else
  test_payload='{"status":"firing","receiver":"bifrost-ops-agent","alerts":[{"status":"firing","labels":{"alertname":"BifrostPhase5AcceptanceTest","namespace":"bifrost-stg"},"annotations":{"summary":"Phase 5 webhook acceptance"},"startsAt":"2026-07-07T00:00:00Z"}]}'
  webhook_code="$(curl -s -o /tmp/bifrost-webhook-test.json -w '%{http_code}' -X POST \
    "${PLATFORM_API}/api/v1/ops-agent/alertmanager" \
    -H "Authorization: Bearer ${webhook_token}" \
    -H "Content-Type: application/json" \
    -d "${test_payload}" || echo FAIL)"
  if [[ "${webhook_code}" == "200" ]]; then
    echo "OK ops-agent webhook HTTP 200"
  else
    echo "FAIL ops-agent webhook HTTP ${webhook_code}" >&2
    cat /tmp/bifrost-webhook-test.json 2>/dev/null >&2 || true
    fail=1
  fi
  if curl -sf "${PLATFORM_API}/api/v1/audit" | python3 -c "
import json,sys
d=json.load(sys.stdin)
rows=d.get('records', d if isinstance(d,list) else [])
hits=[r for r in rows if isinstance(r,dict) and r.get('action')=='ops-agent.alertmanager']
if not hits:
    raise SystemExit('no ops-agent.alertmanager audit rows')
print(f'OK audit log has ops-agent.alertmanager ({len(hits)} row(s))')
" 2>&1; then
    :
  else
    fail=1
  fi
fi

echo "==> Grafana dashboard ConfigMap"
if kubectl get configmap bifrost-trade-dashboards -n "${MONITORING_NS}" >/dev/null 2>&1; then
  echo "OK configmap bifrost-trade-dashboards"
else
  echo "FAIL missing configmap bifrost-trade-dashboards" >&2
  fail=1
fi

echo "==> Alertmanager webhook NetworkPolicy"
if kubectl get networkpolicy alertmanager-webhook-egress -n "${MONITORING_NS}" >/dev/null 2>&1; then
  echo "OK networkpolicy alertmanager-webhook-egress"
else
  echo "FAIL missing networkpolicy alertmanager-webhook-egress" >&2
  fail=1
fi

echo "==> Grafana deep link (Console Open Grafana)"
obs_grafana="$(curl -sf "${PLATFORM_API}/api/v1/cluster/observability" | python3 -c "import json,sys; print(json.load(sys.stdin).get('grafana_url',''))")"
if [[ -n "${obs_grafana}" ]]; then
  echo "OK grafana_url=${obs_grafana}"
  code="$(curl -s -o /dev/null -w '%{http_code}' "${obs_grafana}/login" || echo FAIL)"
  if [[ "${code}" == "200" || "${code}" == "302" ]]; then
    echo "OK grafana HTTP ${code}"
  else
    echo "FAIL grafana unreachable HTTP ${code}" >&2
    fail=1
  fi
else
  echo "FAIL grafana_url empty in observability API" >&2
  fail=1
fi

echo "==> Phase 4 baseline (Layer B + Telemetry)"
if ! PLATFORM_API="${PLATFORM_API}" KUBECONFIG="${KUBECONFIG}" "$(dirname "$0")/verify-phase4-observability.sh"; then
  fail=1
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "Phase 5 observability verify FAILED" >&2
  exit 1
fi
echo "Phase 5 observability verify PASS"
