#!/usr/bin/env bash
# W5 legacy prune — remove orphan IB Deployments / StatefulSets after IB Gateway cutover.
#
# Usage:
#   NS=bifrost-dev ./scripts/k3s/cleanup-legacy-ib-deployments.sh
#   RETIRE_STS=1 ./scripts/k3s/cleanup-legacy-ib-deployments.sh  # all trade NS, delete STS
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
NS="${NS:-bifrost-dev}"
RETIRE_STS="${RETIRE_STS:-0}"
LEGACY_IB_DEPLOYMENTS=(ib-ingestor ib-account-agent ib-operator)
LEGACY_IB_STS=(ib-market-gateway ib-account-agent ib-operator)

export KUBECONFIG

if [[ "${RETIRE_STS}" == "1" ]]; then
  exec "$(dirname "$0")/retire-legacy-ib-socket.sh"
fi

removed=0
for dep in "${LEGACY_IB_DEPLOYMENTS[@]}"; do
  if kubectl get "deployment/${dep}" -n "${NS}" >/dev/null 2>&1; then
    echo "==> Deleting legacy deployment/${dep} in ${NS}"
    kubectl delete "deployment/${dep}" -n "${NS}" --wait=true --timeout=120s
    removed=$((removed + 1))
  fi
done

if [[ "${removed}" -eq 0 ]]; then
  echo "OK no legacy IB Deployments in ${NS}"
else
  echo "OK removed ${removed} legacy IB Deployment(s) from ${NS}"
fi

for sts in "${LEGACY_IB_STS[@]}"; do
  if kubectl get "statefulset/${sts}" -n "${NS}" >/dev/null 2>&1; then
    reps="$(kubectl get "statefulset/${sts}" -n "${NS}" -o jsonpath='{.spec.replicas}')"
    if [[ "${reps}" == "0" ]]; then
      echo "OK legacy statefulset/${sts} replicas=0 in ${NS}"
    else
      echo "WARN statefulset/${sts} still active replicas=${reps} in ${NS} — run retire-legacy-ib-socket.sh" >&2
      exit 1
    fi
  else
    echo "OK legacy statefulset/${sts} absent in ${NS}"
  fi
done
