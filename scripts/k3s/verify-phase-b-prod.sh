#!/usr/bin/env bash
# HTTP smoke for bifrost-prod @ mini-pc-a (.70) NodePort 30881.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
GW="${PROD_GATEWAY:-http://192.168.10.70:30881}"
export KUBECONFIG

echo "==> Prod node"
kubectl get nodes -l bifrost.io/workload-pool=prod -o wide

echo "==> bifrost-prod deployments"
kubectl get deploy -n bifrost-prod

echo "==> Gateway ${GW}"
curl -sf -o /dev/null -w "frontend %{http_code}\n" "${GW}/"
curl -sf -o /dev/null -w "monitor %{http_code}\n" "${GW}/api/monitor/status"
for d in massive docs ops trading strategy portfolio market research; do
  curl -sf -o /dev/null -w "${d} %{http_code}\n" "${GW}/api/${d}/health" || echo "${d} FAIL"
done
echo "Prod verify complete."
