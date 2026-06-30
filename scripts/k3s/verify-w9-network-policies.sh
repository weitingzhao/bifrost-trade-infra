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
IB_HOST_SECONDARY="${IB_HOST_SECONDARY:-192.168.10.33}"
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

echo "==> NetworkPolicy objects (${STG_NS} — IB socket egress)"
if kubectl get networkpolicy ib-socket-egress -n "${STG_NS}" >/dev/null 2>&1; then
  echo "OK ${STG_NS}/ib-socket-egress"
else
  echo "FAIL missing ${STG_NS}/ib-socket-egress" >&2
  fail=1
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

  echo "==> Live probe: IB socket → ${IB_HOST_PRIMARY}:${IB_PORT} (or secondary)"
  socket_pod=""
  for app in ib-market-gateway ib-account-agent ib-operator; do
    socket_pod="$(kubectl get pods -n "${STG_NS}" -l "app.kubernetes.io/name=${app}" \
      --field-selector=status.phase=Running \
      -o jsonpath='{.items[?(@.status.containerStatuses[0].ready==true)].metadata.name}' 2>/dev/null \
      | awk '{print $1}')"
    [[ -n "${socket_pod}" ]] && break
  done
  if [[ -n "${socket_pod}" ]]; then
    container="$(kubectl get pod -n "${STG_NS}" "${socket_pod}" -o jsonpath='{.spec.containers[0].name}')"
    if kubectl exec -n "${STG_NS}" "${socket_pod}" -c "${container}" -- \
      python -c "
import socket, sys
ok = False
for host in ('${IB_HOST_PRIMARY}', '${IB_HOST_SECONDARY}'):
    try:
        s = socket.create_connection((host, ${IB_PORT}), timeout=5)
        s.close()
        print(f'OK tcp {host}:${IB_PORT}')
        ok = True
        break
    except OSError as e:
        print(f'WARN tcp {host}:${IB_PORT} {e}', file=sys.stderr)
if not ok:
    sys.exit(1)
" 2>&1; then
      echo "OK IB socket LAN egress (at least one TWS host reachable)"
    else
      echo "WARN IB socket TCP probe failed (TWS may be down — check manually)" >&2
    fi
  else
    echo "SKIP no IB socket pod in ${STG_NS}"
  fi
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "W9 network policy verify FAILED" >&2
  exit 1
fi

echo "W9 network policy verify PASS (set RUN_NETPOL_PROBE=1 for live probes)"
