#!/usr/bin/env bash
# Phase B stg v2 — HTTP + deployment readiness smoke (Tier A).
# W11 trade-k8s-native: IB socket workloads are StatefulSets (W5); Flower added (W10).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# W1 Traefik Ingress — gateway on K3s Traefik :80 with Host header (see trade-ingressroute.yaml).
GATEWAY_HOST="${STG_GATEWAY_HOST:-trade-stg.bifrost.lan}"
GATEWAY_IP="${STG_GATEWAY_IP:-192.168.10.73}"
GATEWAY="${STG_GATEWAY_URL:-http://${GATEWAY_IP}/}"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
NS="${STG_NAMESPACE:-bifrost-stg}"

export KUBECONFIG

gateway_curl() {
  curl -sf -H "Host: ${GATEWAY_HOST}" --connect-timeout 8 "$@"
}

DOMAINS="monitor massive docs ops trading strategy portfolio market research"
WORKER_DEPLOY="daemon account-sync celery-worker flower"
SOCKET_STS="ib-market-gateway ib-account-agent ib-operator"
SOCKET_DEPLOY="massive-ws"

fail=0

echo "==> Deployments (${NS})"
kubectl get deploy -n "${NS}" -o wide 2>/dev/null || true
echo "==> StatefulSets (${NS})"
kubectl get sts -n "${NS}" -o wide 2>/dev/null || true

for dep in frontend; do
  if ! kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
    echo "FAIL rollout: ${dep}" >&2
    fail=1
  else
    echo "OK rollout: ${dep}"
  fi
done

if ! kubectl get ingressroute trade-gateway -n "${NS}" >/dev/null 2>&1; then
  echo "FAIL missing IngressRoute trade-gateway (W1 Traefik gateway)" >&2
  fail=1
else
  echo "OK IngressRoute: trade-gateway (host=${GATEWAY_HOST})"
fi

for d in ${DOMAINS}; do
  dep="api-${d}"
  if ! kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
    echo "FAIL rollout: ${dep}" >&2
    fail=1
  else
    echo "OK rollout: ${dep}"
  fi
done

for dep in ${WORKER_DEPLOY}; do
  if ! kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
    echo "FAIL rollout: ${dep}" >&2
    fail=1
  else
    echo "OK rollout: ${dep}"
  fi
done

for sts in ${SOCKET_STS}; do
  if ! kubectl rollout status "statefulset/${sts}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
    echo "FAIL rollout: statefulset/${sts}" >&2
    fail=1
  else
    echo "OK rollout: statefulset/${sts}"
  fi
done

for dep in ${SOCKET_DEPLOY}; do
  if ! kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
    echo "FAIL rollout: ${dep}" >&2
    fail=1
  else
    echo "OK rollout: ${dep}"
  fi
done

echo "==> Gateway ${GATEWAY} (Host: ${GATEWAY_HOST})"
fe_code="$(gateway_curl -s -o /dev/null -w '%{http_code}' "${GATEWAY}/" || echo 000)"
echo "  frontend → HTTP ${fe_code}"
if [[ "${fe_code}" != "200" ]]; then fail=1; fi

for d in ${DOMAINS}; do
  path="health"
  if [[ "${d}" == "monitor" ]]; then path="status"; fi
  code="$(gateway_curl -s -o /dev/null -w '%{http_code}' "${GATEWAY}/api/${d}/${path}" || echo 000)"
  echo "  api-${d} → HTTP ${code}"
  if [[ "${code}" != "200" ]]; then fail=1; fi
done

if [[ "${fail}" -eq 0 ]]; then
  echo "Phase B stg v2 smoke: PASS"
  exit 0
fi
echo "Phase B stg v2 smoke: FAIL" >&2
exit 1
