#!/usr/bin/env bash
# W11 trade-k8s-native — STG Tier A/B readiness + deliver-prod gate sign-off bar.
#
# Tier A HTTP (required): 9 APIs + frontend via Traefik Host header — user-facing stack.
# Tier A rollouts (report): native Deployment + StatefulSet kinds; may WARN pending deliver-stg.
# Native manifests: kustomize + W9/W10 object presence.
# deliver-prod gate: in-cluster Traefik preflight (same path as Tekton preflight-stg).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
NS="${STG_NAMESPACE:-bifrost-stg}"
GATEWAY_HOST="${STG_GATEWAY_HOST:-trade-stg.bifrost.lan}"
GATEWAY_IP="${STG_GATEWAY_IP:-192.168.10.73}"
TRAEFIK_URL="${STG_TRAEFIK_URL:-http://traefik.kube-system.svc.cluster.local}"

export KUBECONFIG

fail=0
warn=0

echo "==> W11 [1/4] kustomize build (dev|stg|prod)"
for o in dev stg prod; do
  if kubectl kustomize "${ROOT}/k8s/overlays/${o}" >/dev/null 2>&1; then
    echo "OK kustomize ${o}"
  else
    echo "FAIL kustomize ${o}" >&2
    fail=1
  fi
done

echo "==> W11 [2/4] Tier A HTTP smoke (Traefik Host: ${GATEWAY_HOST})"
gateway_curl() {
  curl -sf -H "Host: ${GATEWAY_HOST}" --connect-timeout 8 "$@"
}
http_fail=0
fe_code="$(gateway_curl -s -o /dev/null -w '%{http_code}' "http://${GATEWAY_IP}/" || echo 000)"
echo "  frontend → HTTP ${fe_code}"
[[ "${fe_code}" == "200" ]] || http_fail=1
for d in monitor massive docs ops trading strategy portfolio market research; do
  path="health"
  [[ "${d}" == "monitor" ]] && path="status"
  code="$(gateway_curl -s -o /dev/null -w '%{http_code}' "http://${GATEWAY_IP}/api/${d}/${path}" || echo 000)"
  echo "  api-${d} → HTTP ${code}"
  [[ "${code}" == "200" ]] || http_fail=1
done
if [[ "${http_fail}" -eq 0 ]]; then
  echo "OK Tier A HTTP"
else
  echo "FAIL Tier A HTTP" >&2
  fail=1
fi

echo "==> W11 [3/4] Native wave manifests (W9/W10)"
if [[ -x "${ROOT}/scripts/k3s/verify-w9-network-policies.sh" ]]; then
  if "${ROOT}/scripts/k3s/verify-w9-network-policies.sh" 2>&1 | grep -q "verify PASS"; then
    echo "OK W9 netpol objects"
  else
    echo "WARN W9 netpol objects missing (apply overlay or skip live probe)" >&2
    warn=1
  fi
fi
if [[ -x "${ROOT}/scripts/k3s/verify-w10-observability.sh" ]]; then
  if "${ROOT}/scripts/k3s/verify-w10-observability.sh" 2>&1 | grep -q "verify PASS"; then
    echo "OK W10 observability objects"
  else
    echo "WARN W10 observability objects missing" >&2
    warn=1
  fi
fi

echo "==> W11 [4/4] deliver-prod STG preflight gate (in-cluster Traefik)"
preflight_fail=0
if kubectl run "w11-preflight-${RANDOM}" -n "${NS}" --rm -i --restart=Never \
  --image=curlimages/curl:8.5.0 --command -- sh -c "
    set -eu
    trf='${TRAEFIK_URL}'
    host='${GATEWAY_HOST}'
    check() { id=\$1; path=\$2
      code=\$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 10 -H \"Host: \${host}\" \"\${trf}\${path}\" || echo 000)
      echo \"  \${id} → HTTP \${code}\"
      case \${code} in 200|503) ;; *) exit 1 ;; esac
    }
    check frontend /
    check api-monitor /api/monitor/status
    for d in massive docs ops trading strategy portfolio market research; do
      check api-\${d} /api/\${d}/health
    done
    echo OK preflight
  " 2>&1 | tee /tmp/w11-preflight.out; then
  if grep -q "OK preflight" /tmp/w11-preflight.out; then
    echo "OK deliver-prod would proceed (STG preflight pass)"
  else
    preflight_fail=1
  fi
else
  preflight_fail=1
fi
if [[ "${preflight_fail}" -ne 0 ]]; then
  echo "FAIL deliver-prod preflight gate" >&2
  fail=1
fi

echo "==> W11 rollout summary (informational — legacy IB STS should be absent)"
rollout_warn=0
for dep in frontend daemon celery-worker flower massive-ws; do
  kubectl rollout status "deployment/${dep}" -n "${NS}" --timeout=30s >/dev/null 2>&1 \
    && echo "OK rollout deployment/${dep}" \
    || { echo "WARN rollout deployment/${dep}" >&2; rollout_warn=1; }
done
for sts in ib-market-gateway ib-account-agent ib-operator; do
  if kubectl get statefulset "${sts}" -n "${NS}" >/dev/null 2>&1; then
    reps="$(kubectl get statefulset "${sts}" -n "${NS}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)"
    if [[ "${reps}" == "0" ]]; then
      echo "OK legacy statefulset/${sts} retired (replicas=0)"
    else
      echo "WARN legacy statefulset/${sts} still active replicas=${reps}" >&2
      rollout_warn=1
    fi
  else
    echo "OK legacy statefulset/${sts} absent"
  fi
done

if [[ "${fail}" -ne 0 ]]; then
  echo "W11 trade-k8s-native verify FAILED" >&2
  exit 1
fi
if [[ "${warn}" -ne 0 || "${rollout_warn}" -ne 0 ]]; then
  echo "W11 trade-k8s-native verify PASS (with WARN — Tier A HTTP + prod gate OK; rollouts/manifests need deliver-stg)"
  exit 0
fi
echo "W11 trade-k8s-native verify PASS"
