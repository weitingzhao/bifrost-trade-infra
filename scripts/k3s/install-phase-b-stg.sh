#!/usr/bin/env bash
# Phase B — stg v2: full stack — PG/Redis/nginx/9 APIs/frontend + worker + socket (Live TWS + Massive).
#
# Usage:
#   make sync-stg-config   # optional: refresh IB from .env
#   KUBECONFIG=~/.kube/bifrost-k3s.yaml ./scripts/k3s/install-phase-b-stg.sh
#   make k3s-install-phase-b-stg
#
# Prereq: kubectl apply -f k8s/base/secrets/bifrost-stg-secrets.yaml -n bifrost-stg (from .example)
#
# Verify: make k3s-verify-phase-b-stg-v2
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
CICD_NAMESPACE="${CICD_NAMESPACE:-cicd}"
STG_NAMESPACE="${STG_NAMESPACE:-bifrost-stg}"
RUN_DELIVER="${RUN_DELIVER:-1}"
DELIVER_TIMEOUT="${DELIVER_TIMEOUT:-7200}"
STG_GATEWAY_HOST="${STG_GATEWAY_HOST:-trade-stg.bifrost.lan}"
STG_GATEWAY_IP="${STG_GATEWAY_IP:-192.168.10.73}"
STG_GATEWAY_URL="${STG_GATEWAY_URL:-http://${STG_GATEWAY_IP}/}"
STG_API_URL="${STG_API_URL:-http://${STG_GATEWAY_IP}/api/monitor/status}"
GITEA_ORG="${GITEA_ORG:-bifrost}"

export KUBECONFIG

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

if ! kubectl get secret gitea-git-credentials -n "${CICD_NAMESPACE}" >/dev/null 2>&1; then
  echo "Missing gitea-git-credentials — complete Gitea secret setup first." >&2
  exit 1
fi

echo "==> Phase B: Gitea mirrors (Trade repos for API + frontend builds)"
MIRROR_REPOS="bifrost-trade-core bifrost-trade-worker bifrost-trade-socket bifrost-trade-api bifrost-trade-frontend bifrost-trade-infra bifrost-ui bifrost-platform" \
  "${ROOT}/scripts/k3s/bootstrap-gitea-mirrors.sh"

echo "==> Sync stg config into kustomize overlay"
if [[ -f "${ROOT}/.env" ]]; then
  "${ROOT}/scripts/sync_stg_config.sh"
else
  mkdir -p "${ROOT}/k8s/overlays/stg/config"
  cp "${ROOT}/config/config.stg.yaml" "${ROOT}/k8s/overlays/stg/config/config.stg.yaml"
fi

if [[ -f "${ROOT}/k8s/base/secrets/bifrost-stg-secrets.yaml" ]]; then
  echo "==> Apply bifrost-stg-secrets"
  kubectl apply -f "${ROOT}/k8s/base/secrets/bifrost-stg-secrets.yaml" -n "${STG_NAMESPACE}"
else
  echo "WARN: no k8s/base/secrets/bifrost-stg-secrets.yaml — copy from .example for Massive API key" >&2
fi

echo "==> Apply bifrost-stg overlay (full stack: infra + APIs + worker + socket + frontend)"
kubectl apply -k "${ROOT}/k8s/overlays/stg"

echo "==> Wait for infra (redis, nginx; postgres only if embedded)"
if kubectl get deployment postgres -n "${STG_NAMESPACE}" >/dev/null 2>&1; then
  pg_replicas="$(kubectl get deployment postgres -n "${STG_NAMESPACE}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)"
  if [[ "${pg_replicas}" != "0" ]]; then
    kubectl rollout status deployment/postgres -n "${STG_NAMESPACE}" --timeout=600s || true
  else
    echo "  skip postgres (replicas=0 — CNPG cutover)"
  fi
else
  echo "  skip postgres (removed — CNPG @ data NS)"
fi
kubectl rollout status deployment/redis -n "${STG_NAMESPACE}" --timeout=300s
kubectl rollout status deployment/nginx -n "${STG_NAMESPACE}" --timeout=300s || true

echo "==> Tekton ConfigMaps (Dockerfiles) + deliver pipeline"
if [[ "${RUN_DELIVER}" != "1" ]]; then
  echo "RUN_DELIVER=0 — manifests applied, skip PipelineRun."
  exit 0
fi

TRIGGER=install-phase-b-stg SYNC_GITEA=0 APPLY_OVERLAY=0 RUN_DB_INIT=1 \
  "${ROOT}/scripts/k3s/run-deliver-stg.sh"

STG_GATEWAY_HOST="${STG_GATEWAY_HOST:-trade-stg.bifrost.lan}"
STG_GATEWAY_IP="${STG_GATEWAY_IP:-192.168.10.73}"
STG_GATEWAY_URL="${STG_GATEWAY_URL:-http://${STG_GATEWAY_IP}/}"
STG_API_URL="${STG_API_URL:-http://${STG_GATEWAY_IP}/api/monitor/status}"

echo "==> Stg gateway smoke"
api_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${STG_API_URL}" || echo 000)"
fe_body="$(curl -sf --connect-timeout 8 "${STG_GATEWAY_URL}" || true)"
fe_code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 8 "${STG_GATEWAY_URL}" || echo 000)"

echo "  gateway   ${STG_GATEWAY_URL} → HTTP ${fe_code}"
echo "  monitor   ${STG_API_URL} → HTTP ${api_code}"

if [[ "${fe_code}" != "200" ]]; then
  echo "FAIL: stg gateway not HTTP 200" >&2
  exit 1
fi
if [[ "${api_code}" != "200" ]]; then
  echo "WARN: /api/monitor/status not HTTP 200 (DB or API warming up — check pods)" >&2
fi
if echo "${fe_body}" | grep -q 'K3s smoke'; then
  echo "FAIL: still serving smoke HTML" >&2
  exit 1
fi
if echo "${fe_body}" | grep -q 'Bifrost Trade'; then
  echo "  SPA check: HTML contains 'Bifrost Trade'"
fi

echo ""
echo "Phase B stg v2 complete."
echo "  Gateway:  ${STG_GATEWAY_URL} (Host: ${STG_GATEWAY_HOST:-trade-stg.bifrost.lan} · Traefik :80)"
echo "  Monitor:  ${STG_API_URL}"
echo "  Worker:   daemon · account-sync · celery-worker"
echo "  Socket:   ib-market-gateway · ib-account-agent · ib-operator · massive-ws"
echo "  Verify:   make k3s-verify-phase-b-stg-v2"
echo "  Console:  Delivery → bifrost-deliver-stg; Promote stg smoke via gateway URLs"
