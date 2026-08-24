#!/usr/bin/env bash
# C4 — Assert api-ops is Kubernetes-only (legacy docker/local/agent executors removed).
# Prefer the Phase B cluster verify scripts for full STG/PROD checks.
set -euo pipefail

OPS_BASE="${OPS_BASE:-http://127.0.0.1:8768}"
ok() { echo "OK  $*"; }
bad() { echo "FAIL $*" >&2; exit 1; }

echo "== C4 ops executor K8s-only =="
echo "OPS_BASE=${OPS_BASE}"

health_json="$(curl -sf "${OPS_BASE}/ops/health" || curl -sf "${OPS_BASE}/health" || true)"
if [[ -z "${health_json}" ]]; then
  bad "ops health unreachable at ${OPS_BASE}"
fi

executor_mode="$(echo "${health_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('executor_mode',''))" 2>/dev/null || echo "")"
if [[ "${executor_mode}" != "kubernetes" ]]; then
  bad "executor_mode=${executor_mode:-<missing>} — expected kubernetes (C4 retired local/docker/agent)"
fi
ok "executor_mode=kubernetes"

k8s_reachable="$(echo "${health_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('k8s_reachable',''))" 2>/dev/null || echo "")"
if [[ "${k8s_reachable}" == "True" || "${k8s_reachable}" == "true" ]]; then
  ok "k8s_reachable=true"
else
  echo "WARN k8s_reachable=${k8s_reachable:-<missing>} — api-ops may lack cluster credentials"
fi

# Hard-fail if legacy docker control-plane fields reappear
if echo "${health_json}" | python3 -c "import sys,json; d=json.load(sys.stdin); raise SystemExit(0 if 'docker_reachable' in d or d.get('local_control') in ('docker','systemd','subprocess') else 1)" 2>/dev/null; then
  bad "legacy docker/local_control fields still present on /ops/health"
fi
ok "no legacy docker/local_control health fields"

echo "C4 verify passed"
