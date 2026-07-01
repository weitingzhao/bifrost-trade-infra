#!/usr/bin/env bash
# W5 legacy prune — remove orphan IB Deployments after StatefulSet + Lease migration.
# Kustomize/Argo no longer manage these names; manual apply left them running in bifrost-dev.
#
# Usage:
#   NS=bifrost-dev ./scripts/k3s/cleanup-legacy-ib-deployments.sh
#   make k3s-cleanup-legacy-ib-deployments NS=bifrost-dev
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
NS="${NS:-bifrost-dev}"
LEGACY_IB_DEPLOYMENTS=(ib-ingestor ib-account-agent ib-operator)

export KUBECONFIG

removed=0
for dep in "${LEGACY_IB_DEPLOYMENTS[@]}"; do
  if kubectl get "deployment/${dep}" -n "${NS}" >/dev/null 2>&1; then
    echo "==> Deleting legacy deployment/${dep} in ${NS}"
    kubectl delete "deployment/${dep}" -n "${NS}" --wait=true --timeout=120s
    removed=$((removed + 1))
  fi
done

if [[ "${removed}" -eq 0 ]]; then
  echo "OK no legacy IB Deployments in ${NS} (StatefulSet-only)"
else
  echo "OK removed ${removed} legacy IB Deployment(s) from ${NS}"
fi

for sts in ib-market-gateway ib-account-agent ib-operator; do
  if ! kubectl get "statefulset/${sts}" -n "${NS}" >/dev/null 2>&1; then
    echo "WARN statefulset/${sts} missing in ${NS}" >&2
    exit 1
  fi
done
echo "OK IB StatefulSets present in ${NS}"
