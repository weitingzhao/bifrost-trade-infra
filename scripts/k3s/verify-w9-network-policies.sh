#!/usr/bin/env bash
# W9 trade-k8s-native — NetworkPolicy smoke (env Redis isolation + IB socket egress).
#
# Requires: kubectl + live cluster (K3s kube-router network policy controller).
# Live probes (RUN_NETPOL_PROBE=1): kube-router ipsets need ~15s to propagate after
# policy apply or new pods — set NETPOL_WARMUP_SECS (default 15) before probing.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
STG_NS="${STG_NAMESPACE:-bifrost-stg}"
PROD_NS="${PROD_NAMESPACE:-bifrost-prod}"
DATA_NS="${DATA_NAMESPACE:-data}"
IB_HOST_PRIMARY="${IB_HOST_PRIMARY:-192.168.10.30}"
IB_HOST_SECONDARY="${IB_HOST_SECONDARY:-192.168.10.32}"
IB_PORT="${IB_PORT:-7496}"
NETPOL_WARMUP_SECS="${NETPOL_WARMUP_SECS:-15}"

export KUBECONFIG

fail=0

echo "==> NetworkPolicy objects (data NS — Redis env isolation)"
for pol in redis-live-stg-ingress redis-queue-stg-ingress redis-live-prod-ingress redis-queue-prod-ingress redis-dev-ingress; do
  if kubectl get networkpolicy "${pol}" -n "${DATA_NS}" >/dev/null 2>&1; then
    echo "OK data/${pol}"
  else
    echo "FAIL missing data/${pol}" >&2
    fail=1
  fi
done

echo "==> NetworkPolicy objects (${STG_NS} — legacy IB socket egress)"
if kubectl get networkpolicy ib-socket-egress -n "${STG_NS}" >/dev/null 2>&1; then
  echo "WARN ${STG_NS}/ib-socket-egress still present (legacy trade-socket retired — optional cleanup)" >&2
else
  echo "OK ${STG_NS}/ib-socket-egress absent (legacy IB retired)"
fi

redis_probe() {
  local ns=$1 host=$2 expect=$3 label=$4
  local probe_pod="netpol-probe-${RANDOM}"
  local out
  out="$(kubectl run "${probe_pod}" -n "${ns}" --rm -i --restart=Never \
    --image=redis:7-alpine --command -- \
    sh -c "sleep ${NETPOL_WARMUP_SECS}; redis-cli -h ${host} -t 5 ping; echo EXIT=\$?" 2>&1 || true)"
  if [[ "${expect}" == "allow" ]]; then
    if echo "${out}" | grep -q PONG; then
      echo "OK ${label}"
    else
      echo "FAIL ${label} (expected PONG): ${out}" >&2
      fail=1
    fi
  else
    if echo "${out}" | grep -q PONG; then
      echo "FAIL ${label} (env isolation broken)" >&2
      fail=1
    else
      echo "OK ${label} (blocked)"
    fi
  fi
}

if [[ "${RUN_NETPOL_PROBE:-0}" == "1" ]]; then
  echo "==> Live probes (warmup ${NETPOL_WARMUP_SECS}s for kube-router ipset sync)"
  redis_probe "${STG_NS}" "redis-live-stg.${DATA_NS}.svc.cluster.local" allow \
    "${STG_NS} → redis-live-stg"
  redis_probe "${STG_NS}" "redis-live-prod.${DATA_NS}.svc.cluster.local" deny \
    "${STG_NS} → redis-live-prod (cross-env)"
  redis_probe "${PROD_NS}" "redis-live-prod.${DATA_NS}.svc.cluster.local" allow \
    "${PROD_NS} → redis-live-prod"

  echo "==> Live probe: legacy IB socket (retired — Platform ib-gateway @ data NS)"
  socket_pod=""
  for app in ib-market-gateway ib-account-agent ib-operator; do
    socket_pod="$(kubectl get pods -n "${STG_NS}" -l "app.kubernetes.io/name=${app}" \
      --field-selector=status.phase=Running \
      -o jsonpath='{.items[?(@.status.containerStatuses[0].ready==true)].metadata.name}' 2>/dev/null \
      | awk '{print $1}')"
    [[ -n "${socket_pod}" ]] && break
  done
  if [[ -n "${socket_pod}" ]]; then
    echo "WARN legacy IB socket pod still running in ${STG_NS}: ${socket_pod} (expect absent after cutover)" >&2
  else
    echo "OK no legacy IB socket pods in ${STG_NS}"
  fi
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "W9 network policy verify FAILED" >&2
  exit 1
fi

echo "W9 network policy verify PASS (set RUN_NETPOL_PROBE=1 for live probes)"
