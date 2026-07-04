#!/usr/bin/env bash
# Retire legacy trade-socket IB StatefulSets after IB Gateway Plugin cutover.
#
# ArgoCD (bifrost-stg / bifrost-prod) selfHeal will recreate STS until k8s changes
# are pushed to main. This script:
#   1. Optionally suspends Argo automated sync (SUSPEND_ARGO=1, default)
#   2. Deletes legacy IB STS (+ orphan headless Services)
#   3. Applies local kustomize overlays (APPLY_OVERLAYS=1, default)
#
# After git push to bifrost-trade-infra main, re-enable Argo sync — prune removes orphans.
#
# Usage:
#   ./scripts/k3s/retire-legacy-ib-socket.sh
#   SUSPEND_ARGO=0 APPLY_OVERLAYS=0 ./scripts/k3s/retire-legacy-ib-socket.sh  # delete only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
SUSPEND_ARGO="${SUSPEND_ARGO:-1}"
APPLY_OVERLAYS="${APPLY_OVERLAYS:-1}"
TRADE_NS=(bifrost-dev bifrost-stg bifrost-prod)
LEGACY_STS=(ib-market-gateway ib-account-agent ib-operator)
ARGO_APPS=(bifrost-stg bifrost-prod)

export KUBECONFIG

if [[ "${SUSPEND_ARGO}" == "1" ]]; then
  echo "==> Suspend ArgoCD automated sync (until infra git push)"
  for app in "${ARGO_APPS[@]}"; do
    if kubectl get application "${app}" -n cicd >/dev/null 2>&1; then
      kubectl patch application "${app}" -n cicd --type merge \
        -p '{"spec":{"syncPolicy":{"automated":null}}}' >/dev/null
      echo "  suspended ${app}"
    fi
  done
fi

echo "==> Delete legacy IB StatefulSets"
for NS in "${TRADE_NS[@]}"; do
  for sts in "${LEGACY_STS[@]}"; do
    if kubectl get "statefulset/${sts}" -n "${NS}" >/dev/null 2>&1; then
      kubectl delete "statefulset/${sts}" -n "${NS}" --wait=false
      echo "  deleted ${NS}/${sts}"
    fi
  done
  for svc in "${LEGACY_STS[@]}"; do
    kubectl delete "service/${svc}" -n "${NS}" --ignore-not-found --wait=false >/dev/null 2>&1 || true
  done
done

if [[ "${APPLY_OVERLAYS}" == "1" ]]; then
  echo "==> Apply local kustomize overlays (dev|stg|prod)"
  for o in dev stg prod; do
    kubectl apply -k "${ROOT}/k8s/overlays/${o}" >/dev/null
    echo "  applied overlay/${o}"
  done
fi

echo "==> Legacy IB socket retirement applied"
echo "Next: commit + push bifrost-trade-infra k8s changes, then:"
echo "  kubectl patch application bifrost-stg -n cicd --type merge -p '{\"spec\":{\"syncPolicy\":{\"automated\":{\"prune\":true,\"selfHeal\":true}}}}'"
echo "  kubectl patch application bifrost-prod -n cicd --type merge -p '{\"spec\":{\"syncPolicy\":{\"automated\":{\"prune\":true,\"selfHeal\":true}}}}'"
