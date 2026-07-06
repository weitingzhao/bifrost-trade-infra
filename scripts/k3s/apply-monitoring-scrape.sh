#!/usr/bin/env bash
# Apply Bifrost Prometheus Operator scrape configs (ServiceMonitor / PodMonitor) in monitoring NS.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

echo "==> Apply k8s/monitoring (ServiceMonitor + PodMonitor)"
kubectl apply -k "${ROOT}/k8s/monitoring"

echo "==> Prune duplicate monitors outside monitoring NS (legacy overlays)"
for kind in servicemonitor podmonitor; do
  for ns in bifrost-stg bifrost-prod data; do
    kubectl delete "${kind}.monitoring.coreos.com" bifrost-trade-apis -n "${ns}" --ignore-not-found 2>/dev/null || true
    kubectl delete "${kind}.monitoring.coreos.com" bifrost-redis -n "${ns}" --ignore-not-found 2>/dev/null || true
    kubectl delete podmonitor.monitoring.coreos.com bifrost-postgres -n "${ns}" --ignore-not-found 2>/dev/null || true
  done
done

echo "Monitoring scrape configs applied."
