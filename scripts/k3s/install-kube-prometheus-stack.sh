#!/usr/bin/env bash
# Install kube-prometheus-stack (Layer B observability). Idempotent — safe to re-run.
# Used by platform-api POST /cluster/addons/kube-prometheus-stack/ensure.
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

RELEASE_NAME="${RELEASE_NAME:-kube-prometheus-stack}"
MONITORING_NAMESPACE="${MONITORING_NAMESPACE:-monitoring}"
CHART_REF="${CHART_REF:-prometheus-community/kube-prometheus-stack}"
VALUES_FILE="${VALUES_FILE:-$(dirname "$0")/values-kube-prometheus.yaml}"

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

echo "==> kube-prometheus-stack (Layer B) using KUBECONFIG=${KUBECONFIG}"
echo "    namespace=${MONITORING_NAMESPACE} release=${RELEASE_NAME}"

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null
helm repo update prometheus-community >/dev/null

# Do not --wait on the full chart: prometheus-node-exporter DaemonSet stays
# Updated/Ready < DESIRED while elastic WOL standby (e.g. gpu-server) is off,
# which previously left the Helm release STATUS=failed despite Grafana/Prom OK.
HELM_ARGS=(
  upgrade
  --install
  "${RELEASE_NAME}"
  "${CHART_REF}"
  --namespace "${MONITORING_NAMESPACE}"
  --create-namespace
  --timeout 10m
)

if [[ -f "${VALUES_FILE}" ]]; then
  echo "    applying values from ${VALUES_FILE}"
  HELM_ARGS+=(--values "${VALUES_FILE}")
fi

helm "${HELM_ARGS[@]}"

echo "==> waiting for core workloads"
for deployment in \
  "${RELEASE_NAME}-operator" \
  "${RELEASE_NAME}-grafana" \
  "${RELEASE_NAME}-kube-state-metrics"
do
  if kubectl get deployment "${deployment}" -n "${MONITORING_NAMESPACE}" >/dev/null 2>&1; then
    kubectl rollout status "deployment/${deployment}" -n "${MONITORING_NAMESPACE}" --timeout=240s
  fi
done

for statefulset in \
  "prometheus-${RELEASE_NAME}-prometheus" \
  "alertmanager-${RELEASE_NAME}-alertmanager"
do
  if kubectl get statefulset "${statefulset}" -n "${MONITORING_NAMESPACE}" >/dev/null 2>&1; then
    kubectl rollout status "statefulset/${statefulset}" -n "${MONITORING_NAMESPACE}" --timeout=240s
  fi
done

# Soft-check node-exporter: Ready may be DESIRED-1 with elastic standby offline.
if kubectl get daemonset "${RELEASE_NAME}-prometheus-node-exporter" -n "${MONITORING_NAMESPACE}" >/dev/null 2>&1; then
  ready="$(kubectl get daemonset "${RELEASE_NAME}-prometheus-node-exporter" -n "${MONITORING_NAMESPACE}" -o jsonpath='{.status.numberReady}')"
  desired="$(kubectl get daemonset "${RELEASE_NAME}-prometheus-node-exporter" -n "${MONITORING_NAMESPACE}" -o jsonpath='{.status.desiredNumberScheduled}')"
  echo "    node-exporter Ready ${ready:-0}/${desired:-0} (elastic standby may leave 1 NotReady)"
  if [[ "${ready:-0}" -lt 1 ]]; then
    echo "node-exporter has zero Ready pods" >&2
    exit 1
  fi
fi

echo "kube-prometheus-stack ready (helm STATUS should be deployed; node-exporter soft-checked)"
