#!/usr/bin/env bash
# Phase B prod — HTTP + deployment readiness smoke (P1 Native K8s).
# W1 Traefik Ingress — gateway on K3s Traefik :80 with Host header (trade-ingressroute.yaml).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATEWAY_HOST="${PROD_GATEWAY_HOST:-trade.bifrost.lan}"
GATEWAY_IP="${PROD_GATEWAY_IP:-192.168.10.70}"
GATEWAY="${PROD_GATEWAY_URL:-http://${GATEWAY_IP}/}"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
NS="${PROD_NAMESPACE:-bifrost-prod}"

export KUBECONFIG

gateway_curl() {
  curl -sf -H "Host: ${GATEWAY_HOST}" --connect-timeout 8 "$@"
}

DOMAINS="monitor massive docs ops trading strategy portfolio market research"
# P1: gateway + APIs only. Set PROD_VERIFY_FULL=1 after deliver-prod refreshes :prod images.
WORKER_DEPLOY="daemon account-sync celery-worker flower"
SOCKET_DEPLOY="massive-ws"
FULL_VERIFY="${PROD_VERIFY_FULL:-0}"

fail=0

echo "==> Prod node (mini-pc-a pool)"
kubectl get nodes -l bifrost.io/host-id=mini-pc-a -o wide 2>/dev/null || true

echo "==> Deployments (${NS})"
kubectl get deploy -n "${NS}" -o wide 2>/dev/null || true
echo "==> StatefulSets (${NS})"
kubectl get sts -n "${NS}" -o wide 2>/dev/null || true

if ! kubectl get ingressroute trade-gateway -n "${NS}" >/dev/null 2>&1; then
  echo "FAIL missing IngressRoute trade-gateway (W1 Traefik gateway)" >&2
  fail=1
else
  echo "OK IngressRoute: trade-gateway (host=${GATEWAY_HOST})"
fi

for dep in frontend; do
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

for dep in ${WORKER_DEPLOY}; do
  if [[ "${FULL_VERIFY}" != "1" ]] && [[ "${dep}" != "daemon" ]] && [[ "${dep}" != "celery-worker" ]]; then
    desired="$(kubectl get deployment "${dep}" -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")"
    echo "SKIP rollout: ${dep} (P1 — refresh via deliver-prod; replicas=${desired})"
    continue
  fi
  if ! kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
    echo "FAIL rollout: ${dep}" >&2
    fail=1
  else
    desired="$(kubectl get deployment "${dep}" -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")"
    echo "OK rollout: ${dep} (replicas=${desired})"
  fi
done

if [[ "${FULL_VERIFY}" == "1" ]]; then
for sts in ib-market-gateway ib-account-agent ib-operator; do
  if kubectl get "statefulset/${sts}" -n "${NS}" >/dev/null 2>&1; then
    if ! kubectl rollout status "statefulset/${sts}" -n "${NS}" --timeout=120s >/dev/null 2>&1; then
      echo "FAIL rollout: statefulset/${sts}" >&2
      fail=1
    else
      echo "OK rollout: statefulset/${sts}"
    fi
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
else
  echo "SKIP socket/worker rollouts (P1 mode — PROD_VERIFY_FULL=1 after deliver-prod)"
fi

echo "==> Redis aliases (${NS})"
for svc in redis redis-queue; do
  if kubectl get "service/${svc}" -n "${NS}" >/dev/null 2>&1; then
    echo "OK service: ${svc}"
  else
    echo "FAIL missing service/${svc} (data NS alias)" >&2
    fail=1
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
  echo "Phase B prod smoke: PASS"
  exit 0
fi
echo "Phase B prod smoke: FAIL" >&2
exit 1
