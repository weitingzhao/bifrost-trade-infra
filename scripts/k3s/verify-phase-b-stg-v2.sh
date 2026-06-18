#!/usr/bin/env bash
# Phase B stg v2 — HTTP + deployment readiness smoke (Tier A).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATEWAY="${STG_GATEWAY_URL:-http://192.168.10.73:30880}"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
NS="${STG_NAMESPACE:-bifrost-stg}"

export KUBECONFIG

DOMAINS="monitor massive docs ops trading strategy portfolio market research"
WORKER="daemon account-sync celery-worker"
SOCKET="ib-ingestor ib-account-agent ib-operator massive-ws"

fail=0

echo "==> Deployments (${NS})"
kubectl get deploy -n "${NS}" -o wide

for dep in nginx frontend; do
  if ! kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
    echo "FAIL rollout: ${dep}" >&2
    fail=1
  else
    echo "OK rollout: ${dep}"
  fi
done

for d in ${DOMAINS}; do
  dep="api-${d}"
  if ! kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
    echo "FAIL rollout: ${dep}" >&2
    fail=1
  else
    echo "OK rollout: ${dep}"
  fi
done

for dep in ${WORKER// / } ${SOCKET// / }; do
  if ! kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
    echo "FAIL rollout: ${dep}" >&2
    fail=1
  else
    echo "OK rollout: ${dep}"
  fi
done

echo "==> Gateway ${GATEWAY}"
fe_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${GATEWAY}/" || echo 000)"
echo "  frontend → HTTP ${fe_code}"
if [[ "${fe_code}" != "200" ]]; then fail=1; fi

for d in ${DOMAINS}; do
  path="health"
  if [[ "${d}" == "monitor" ]]; then path="status"; fi
  code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${GATEWAY}/api/${d}/${path}" || echo 000)"
  echo "  api-${d} → HTTP ${code}"
  if [[ "${code}" != "200" ]]; then fail=1; fi
done

if [[ "${fail}" -eq 0 ]]; then
  echo "Phase B stg v2 smoke: PASS"
  exit 0
fi
echo "Phase B stg v2 smoke: FAIL" >&2
exit 1
