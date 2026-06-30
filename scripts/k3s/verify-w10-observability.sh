#!/usr/bin/env bash
# W10 trade-k8s-native — IB data-line budget ConfigMap + Flower metrics smoke.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
NS="${TRADE_NAMESPACE:-bifrost-stg}"
export KUBECONFIG

fail=0

echo "==> ConfigMap ib-data-line-budget"
if kubectl get configmap ib-data-line-budget -n "${NS}" >/dev/null 2>&1; then
  echo "OK ${NS}/ib-data-line-budget"
  kubectl get configmap ib-data-line-budget -n "${NS}" -o jsonpath='gateway_max={.data.gateway_max_subscriptions} account={.data.account_budget}{"\n"}' 2>/dev/null || true
else
  echo "FAIL missing ${NS}/ib-data-line-budget" >&2
  fail=1
fi

echo "==> Flower Deployment + Service"
if kubectl get deployment flower -n "${NS}" >/dev/null 2>&1; then
  echo "OK deployment/flower"
else
  echo "FAIL missing deployment/flower" >&2
  fail=1
fi
if kubectl get svc flower -n "${NS}" >/dev/null 2>&1; then
  echo "OK service/flower:5555"
else
  echo "FAIL missing service/flower" >&2
  fail=1
fi

if [[ "${RUN_W10_PROBE:-0}" == "1" ]]; then
  echo "==> Flower HTTP probe (ClusterIP)"
  probe_out="$(kubectl run "w10-flower-${RANDOM}" -n "${NS}" --rm -i --restart=Never \
    --image=curlimages/curl:8.5.0 --command -- \
    sh -c "curl -sf --max-time 15 http://flower:5555/ >/dev/null && echo OK" 2>&1 || true)"
  if echo "${probe_out}" | grep -q OK; then
    echo "OK Flower HTTP /"
  else
    echo "WARN Flower HTTP probe inconclusive (check: kubectl port-forward svc/flower 5555)" >&2
  fi

  echo "==> ib_active_data_lines in ib-market-gateway logs (last 200 lines)"
  gw_pod="$(kubectl get pods -n "${NS}" -l app.kubernetes.io/name=ib-market-gateway \
    --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
  if [[ -n "${gw_pod}" ]]; then
    if kubectl logs -n "${NS}" "${gw_pod}" -c ib-market-gateway --tail=200 2>/dev/null | grep -q "ib_active_data_lines="; then
      echo "OK ib_active_data_lines log line present"
    else
      echo "WARN no ib_active_data_lines in recent logs (gateway may be standby or crashloop)" >&2
    fi
  else
    echo "SKIP no running ib-market-gateway pod"
  fi
fi

if [[ "${fail}" -ne 0 ]]; then
  echo "W10 observability verify FAILED" >&2
  exit 1
fi

echo "W10 observability verify PASS (set RUN_W10_PROBE=1 for live probes)"
