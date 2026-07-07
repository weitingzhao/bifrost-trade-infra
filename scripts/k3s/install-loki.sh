#!/usr/bin/env bash
# Install Grafana Loki (SingleBinary + Promtail) in monitoring NS. Idempotent.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

RELEASE_NAME="${RELEASE_NAME:-loki}"
MONITORING_NAMESPACE="${MONITORING_NAMESPACE:-monitoring}"
CHART_REF="${CHART_REF:-grafana/loki}"
VALUES_FILE="${VALUES_FILE:-$(dirname "$0")/values-loki.yaml}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found in PATH" >&2
  exit 1
fi

if ! command -v helm >/dev/null 2>&1; then
  echo "helm not found in PATH" >&2
  exit 1
fi

if [[ ! -f "${KUBECONFIG}" ]]; then
  echo "kubeconfig not found: ${KUBECONFIG}" >&2
  exit 1
fi

echo "==> Loki (Layer B log aggregation) using KUBECONFIG=${KUBECONFIG}"
echo "    namespace=${MONITORING_NAMESPACE} release=${RELEASE_NAME}"

helm repo add grafana https://grafana.github.io/helm-charts >/dev/null
helm repo update grafana >/dev/null

HELM_ARGS=(
  upgrade
  --install
  "${RELEASE_NAME}"
  "${CHART_REF}"
  --namespace "${MONITORING_NAMESPACE}"
  --create-namespace
  --wait
  --timeout 10m
)

if [[ -f "${VALUES_FILE}" ]]; then
  echo "    applying values from ${VALUES_FILE}"
  HELM_ARGS+=(--values "${VALUES_FILE}")
fi

helm "${HELM_ARGS[@]}"

echo "==> Promtail (log shipper → Loki)"
PROMTAIL_VALUES="${PROMTAIL_VALUES:-$(dirname "$0")/values-promtail.yaml}"
helm upgrade --install promtail grafana/promtail \
  --namespace "${MONITORING_NAMESPACE}" \
  --wait \
  --timeout 8m \
  --values "${PROMTAIL_VALUES}"

echo "==> waiting for Loki workloads"
for kind_name in \
  "statefulset/${RELEASE_NAME}" \
  "daemonset/promtail"
do
  kind="${kind_name%%/*}"
  name="${kind_name#*/}"
  if kubectl get "${kind}" "${name}" -n "${MONITORING_NAMESPACE}" >/dev/null 2>&1; then
    kubectl rollout status "${kind}/${name}" -n "${MONITORING_NAMESPACE}" --timeout=300s
  fi
done

echo "Loki ready"
