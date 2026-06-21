#!/usr/bin/env bash
# Promote CNPG primary to the instance running on POSTGRES_NODE_NAME (default ubt-k3s-04).
#
# Requires kubectl-cnpg plugin (v1.25.x matches operator). Installs to ~/.local/bin if missing.
#
# Usage:
#   make k3s-switchover-postgres-primary
#   POSTGRES_NODE_NAME=ubt-k3s-04 make k3s-switchover-postgres-primary
set -euo pipefail

KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}}"
export KUBECONFIG

DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CLUSTER_NAME="${CLUSTER_NAME:-bifrost-postgres}"
TARGET_NODE="${POSTGRES_NODE_NAME:-ubt-k3s-04}"
CNPG_VERSION="${CNPG_VERSION:-1.25.1}"
CNPG_BIN="${CNPG_PLUGIN:-${HOME}/.local/bin/kubectl-cnpg}"
SWITCHOVER_TIMEOUT="${SWITCHOVER_TIMEOUT:-300}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl not found in PATH" >&2
  exit 1
fi

install_cnpg_plugin() {
  local os arch url tmp
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  arch="$(uname -m)"
  case "${arch}" in
    x86_64) arch="amd64" ;;
    arm64|aarch64) arch="arm64" ;;
    *) echo "unsupported arch: ${arch}" >&2; exit 1 ;;
  esac
  url="https://github.com/cloudnative-pg/cloudnative-pg/releases/download/v${CNPG_VERSION}/kubectl-cnpg_${CNPG_VERSION}_${os}_${arch}.tar.gz"
  tmp="$(mktemp -d)"
  echo "==> Installing kubectl-cnpg ${CNPG_VERSION} to ${CNPG_BIN}"
  curl -fsSL "${url}" | tar -xz -C "${tmp}" kubectl-cnpg
  mkdir -p "$(dirname "${CNPG_BIN}")"
  mv "${tmp}/kubectl-cnpg" "${CNPG_BIN}"
  chmod +x "${CNPG_BIN}"
  rm -rf "${tmp}"
}

if [[ ! -x "${CNPG_BIN}" ]]; then
  install_cnpg_plugin
fi

current_primary="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
if [[ -z "${current_primary}" ]]; then
  echo "Cluster ${CLUSTER_NAME} not found in ${DATA_NAMESPACE}" >&2
  exit 1
fi

primary_node="$(kubectl get pod "${current_primary}" -n "${DATA_NAMESPACE}" -o jsonpath='{.spec.nodeName}' 2>/dev/null || true)"
if [[ "${primary_node}" == "${TARGET_NODE}" ]]; then
  echo "OK primary ${current_primary} already on ${TARGET_NODE}"
  exit 0
fi

target_pod="$(kubectl get pods -n "${DATA_NAMESPACE}" -l "cnpg.io/cluster=${CLUSTER_NAME}" -o json \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
node = sys.argv[1]
for item in data.get('items', []):
    if item.get('spec', {}).get('nodeName') == node:
        print(item['metadata']['name'])
        break
" "${TARGET_NODE}" 2>/dev/null || true)"

if [[ -z "${target_pod}" ]]; then
  echo "No ${CLUSTER_NAME} pod on node ${TARGET_NODE}" >&2
  kubectl get pods -n "${DATA_NAMESPACE}" -l "cnpg.io/cluster=${CLUSTER_NAME}" -o wide >&2
  exit 1
fi

echo "==> Promote ${target_pod} on ${TARGET_NODE}"
"${CNPG_BIN}" promote -n "${DATA_NAMESPACE}" "${CLUSTER_NAME}" "${target_pod}"

deadline=$((SECONDS + SWITCHOVER_TIMEOUT))
while (( SECONDS < deadline )); do
  phase="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  primary="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
  ready="$(kubectl get cluster "${CLUSTER_NAME}" -n "${DATA_NAMESPACE}" -o jsonpath='{.status.readyInstances}' 2>/dev/null || echo 0)"
  node="$(kubectl get pod "${primary}" -n "${DATA_NAMESPACE}" -o jsonpath='{.spec.nodeName}' 2>/dev/null || true)"
  echo "  phase=${phase} primary=${primary}@${node} ready=${ready}/2"
  if [[ "${primary}" == "${target_pod}" && "${node}" == "${TARGET_NODE}" && "${ready}" == "2" && "${phase}" == "Cluster in healthy state" ]]; then
    echo "OK switchover complete — primary ${primary} on ${TARGET_NODE}"
    exit 0
  fi
  sleep 5
done

echo "Switchover timed out after ${SWITCHOVER_TIMEOUT}s" >&2
"${CNPG_BIN}" status -n "${DATA_NAMESPACE}" "${CLUSTER_NAME}" >&2 || true
exit 1
