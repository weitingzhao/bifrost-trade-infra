#!/usr/bin/env bash
# Join ubt-k3s-05 (192.168.10.77) as K3s agent.
#
# Run from MacBook (bifrost-trade-infra root):
#   make k3s-join-ubt-k3s-05
#
# Token: export K3S_TOKEN=... OR let Step 1 prompt sudo on bootstrap.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP_HOST="${BOOTSTRAP_HOST:-vision@192.168.10.73}"
AGENT_HOST="${AGENT_HOST:-vision@192.168.10.77}"
K3S_URL="${K3S_URL:-https://192.168.10.73:6443}"
K3S_NODE_IP="${K3S_NODE_IP:-192.168.10.77}"
K3S_NODE_NAME="${K3S_NODE_NAME:-ubt-k3s-05}"
KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=30)

K3S_NODE_LABELS="${K3S_NODE_LABELS:-bifrost.io/host-id=ubt-k3s-05,bifrost.io/workload-pool=general}"

REMOTE_TOKEN_PATH="/home/vision/.bifrost-k3s-node-token"

echo "== ubt-k3s-05 K3s agent join =="
echo "Bootstrap: ${BOOTSTRAP_HOST}"
echo "Target:    ${AGENT_HOST} (${K3S_NODE_IP}) node name ${K3S_NODE_NAME}"
echo "Labels:    ${K3S_NODE_LABELS}"
echo ""

ensure_token() {
  if [[ -n "${K3S_TOKEN:-}" ]]; then
    echo "==> Using K3S_TOKEN from environment (${#K3S_TOKEN} chars)"
    return 0
  fi

  if [[ -f "${HOME}/.bifrost-k3s-node-token" ]]; then
    K3S_TOKEN="$(tr -d '\r\n' < "${HOME}/.bifrost-k3s-node-token")"
    if [[ "${#K3S_TOKEN}" -ge 50 ]]; then
      echo "==> Using K3S_TOKEN from ~/.bifrost-k3s-node-token (${#K3S_TOKEN} chars)"
      return 0
    fi
  fi

  echo "==> Step 1/4: Join token from bootstrap"
  echo "    Next: SSH to ${BOOTSTRAP_HOST} — type sudo password when prompted."
  echo ""

  ssh -t "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}" \
    "sudo bash -c 'cat /var/lib/rancher/k3s/server/node-token > ${REMOTE_TOKEN_PATH} && chown vision:vision ${REMOTE_TOKEN_PATH} && chmod 600 ${REMOTE_TOKEN_PATH}'"

  scp "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}:${REMOTE_TOKEN_PATH}" "${TMP_TOKEN:=$(mktemp)}"
  K3S_TOKEN="$(tr -d '\r\n' < "${TMP_TOKEN}")"
  rm -f "${TMP_TOKEN}"
  ssh "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}" "rm -f ${REMOTE_TOKEN_PATH}" || true

  if [[ -z "${K3S_TOKEN}" ]] || [[ "${#K3S_TOKEN}" -lt 50 ]]; then
    echo "ERROR: Invalid K3S_TOKEN. Fetch manually:" >&2
    echo "  make k3s-fetch-join-token" >&2
    exit 1
  fi
  echo "    OK token fetched (${#K3S_TOKEN} chars)"
  echo ""
}

ensure_token

echo "==> Step 2/4: Copying k3s scripts to ${AGENT_HOST}..."
scp "${SSH_OPTS[@]}" \
  "${ROOT}/scripts/k3s/install-agent.sh" \
  "${ROOT}/scripts/k3s/configure-insecure-registry.sh" \
  "${AGENT_HOST}:~/"

echo ""
echo "==> Step 3/4: Installing k3s-agent on ${K3S_NODE_NAME}"
echo "    Enter sudo password for ${AGENT_HOST} when prompted (may take 1–2 min)..."
ssh -t "${SSH_OPTS[@]}" "${AGENT_HOST}" "sudo K3S_URL='${K3S_URL}' K3S_TOKEN='${K3S_TOKEN}' \
  K3S_NODE_IP='${K3S_NODE_IP}' K3S_NODE_NAME='${K3S_NODE_NAME}' \
  K3S_NODE_LABELS='${K3S_NODE_LABELS}' bash ~/install-agent.sh"

echo ""
echo "==> Step 4/4: Registry on ${K3S_NODE_NAME}..."
ssh -t "${SSH_OPTS[@]}" "${AGENT_HOST}" 'sudo REGISTRY_HOSTS="192.168.10.73:30500 registry.cicd.svc.cluster.local:5000" bash ~/configure-insecure-registry.sh'

echo ""
echo "==> Waiting for node Ready..."
for _ in $(seq 1 36); do
  if kubectl --kubeconfig "${KUBECONFIG}" get node "${K3S_NODE_NAME}" >/dev/null 2>&1; then
    ready="$(kubectl --kubeconfig "${KUBECONFIG}" get node "${K3S_NODE_NAME}" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)"
    if [[ "${ready}" == "True" ]]; then
      break
    fi
  fi
  sleep 5
done

echo ""
kubectl --kubeconfig "${KUBECONFIG}" get node "${K3S_NODE_NAME}" -o wide
kubectl --kubeconfig "${KUBECONFIG}" get node "${K3S_NODE_NAME}" --show-labels
echo ""
echo "PASS ubt-k3s-05 joined."
