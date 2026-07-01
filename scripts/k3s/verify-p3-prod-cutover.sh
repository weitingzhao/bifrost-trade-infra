#!/usr/bin/env bash
# P3 — Compose→K8s prod cutover acceptance: K8s Traefik is the sole Trade entry; no legacy NodePort.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATEWAY_HOST="${PROD_GATEWAY_HOST:-trade.bifrost.lan}"
GATEWAY_IP="${PROD_GATEWAY_IP:-192.168.10.70}"
LEGACY_PORT="${PROD_LEGACY_NODEPORT:-30881}"
PROD_HOST="${PROD_SSH_HOST:-vision@${GATEWAY_IP}}"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
NS="${PROD_NAMESPACE:-bifrost-prod}"

export KUBECONFIG

fail=0
pass() { echo "OK $*"; }
warn() { echo "WARN $*"; }
die() { echo "FAIL $*" >&2; fail=1; }

echo "==> P3 prod cutover verify (K8s native @ ${GATEWAY_HOST})"

echo "==> [1/5] Full stack smoke (PROD_VERIFY_FULL=1)"
if ! PROD_VERIFY_FULL=1 "${ROOT}/scripts/k3s/verify-phase-b-prod.sh"; then
  die "phase-b-prod full smoke"
fi

echo "==> [2/5] Legacy NodePort :${LEGACY_PORT} must be down (W1 Traefik only)"
legacy_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 "http://${GATEWAY_IP}:${LEGACY_PORT}/" 2>/dev/null || echo 000)"
if [[ "${legacy_code}" == "200" ]]; then
  die "legacy nginx NodePort still serving HTTP 200 on :${LEGACY_PORT}"
else
  pass "legacy :${LEGACY_PORT} not serving (code=${legacy_code})"
fi

echo "==> [3/5] No legacy IB Deployments in ${NS}"
for dep in ib-ingestor; do
  if kubectl get "deployment/${dep}" -n "${NS}" >/dev/null 2>&1; then
    die "legacy deployment/${dep} still exists"
  fi
done
pass "no legacy ib-ingestor Deployment"

echo "==> [4/5] Cutover safety replicas (daemon/celery=0 until R-DV3 / P5)"
for dep in daemon celery-worker; do
  replicas="$(kubectl get "deployment/${dep}" -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo missing)"
  if [[ "${replicas}" != "0" ]]; then
    die "${dep} replicas=${replicas} (want 0 for cutover window)"
  else
    pass "${dep} replicas=0"
  fi
done

echo "==> [5/5] Optional: Compose absent on prod host (${PROD_HOST})"
if ssh -o ConnectTimeout=5 -o BatchMode=yes "${PROD_HOST}" 'command -v docker >/dev/null 2>&1 && docker ps --format "{{.Names}}" | grep -qi bifrost && exit 1 || exit 0' 2>/dev/null; then
  pass "no bifrost compose containers on prod host (or docker absent)"
else
  rc=$?
  if [[ "${rc}" -eq 255 ]]; then
    warn "ssh to ${PROD_HOST} skipped — verify compose manually"
  else
    die "bifrost docker containers still running on ${PROD_HOST}"
  fi
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "P3 prod cutover verify: FAIL" >&2
  exit 1
fi
echo "P3 prod cutover verify: PASS"
