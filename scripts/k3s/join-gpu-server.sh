#!/usr/bin/env bash
# P5a — Join gpu-server (4090 @ 192.168.10.60) as K3s agent.
#
# Roles: data warehouse · solution compute · GPU / AI (not trade socket/celery).
#
# Run from MacBook:
#   make k3s-join-gpu-server
#
# Token: export K3S_TOKEN=... OR let Step 1 prompt sudo on bootstrap (no subshell — avoids hang).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP_HOST="${BOOTSTRAP_HOST:-vision@192.168.10.73}"
GPU_HOST="${GPU_HOST:-vision@192.168.10.60}"
K3S_URL="${K3S_URL:-https://192.168.10.73:6443}"
K3S_NODE_IP="${K3S_NODE_IP:-192.168.10.60}"
K3S_NODE_NAME="${K3S_NODE_NAME:-gpu-server}"
KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=30)

K3S_NODE_LABELS="${K3S_NODE_LABELS:-workload=gpu,node-role=warehouse,bifrost.io/host-id=gpu-server,bifrost.io/workload-pool=compute,bifrost.io/wol=enabled}"

REMOTE_TOKEN_PATH="/home/vision/.bifrost-k3s-node-token"

echo "== P5a gpu-server K3s agent join =="
echo "Bootstrap: ${BOOTSTRAP_HOST}"
echo "Target:    ${GPU_HOST} (${K3S_NODE_IP}) node name ${K3S_NODE_NAME}"
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

  echo "==> Step 1/5: Join token from bootstrap"
  echo "    Next: SSH to ${BOOTSTRAP_HOST} — type your sudo password when [sudo] prompts."
  echo "    (If nothing happens, Ctrl+C and run: make k3s-fetch-join-token)"
  echo ""

  # Foreground ssh -t WITHOUT command substitution or pipe — sudo TTY works.
  ssh -t "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}" \
    "sudo bash -c 'cat /var/lib/rancher/k3s/server/node-token > ${REMOTE_TOKEN_PATH} && chown vision:vision ${REMOTE_TOKEN_PATH} && chmod 600 ${REMOTE_TOKEN_PATH}'"

  scp "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}:${REMOTE_TOKEN_PATH}" "${TMP_TOKEN:=$(mktemp)}"
  K3S_TOKEN="$(tr -d '\r\n' < "${TMP_TOKEN}")"
  rm -f "${TMP_TOKEN}"
  ssh "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}" "rm -f ${REMOTE_TOKEN_PATH}" || true

  if [[ -z "${K3S_TOKEN}" ]] || [[ "${#K3S_TOKEN}" -lt 50 ]]; then
    echo "ERROR: Invalid K3S_TOKEN. Fetch manually:" >&2
    echo "  make k3s-fetch-join-token" >&2
    echo "  export K3S_TOKEN=\$(cat ~/.bifrost-k3s-node-token)" >&2
    exit 1
  fi
  echo "    OK token fetched (${#K3S_TOKEN} chars)"
  echo ""
}

ensure_token

echo "==> Step 2/5: Copying k3s scripts to gpu-server..."
scp "${SSH_OPTS[@]}" \
  "${ROOT}/scripts/k3s/install-agent.sh" \
  "${ROOT}/scripts/k3s/configure-insecure-registry.sh" \
  "${ROOT}/scripts/k3s/wol-eno1.service" \
  "${GPU_HOST}:~/"

echo ""
echo "==> Step 3/5: Installing k3s-agent on gpu-server"
echo "    Enter sudo password for ${GPU_HOST} when prompted (may take 1–2 min)..."
ssh -t "${SSH_OPTS[@]}" "${GPU_HOST}" "sudo K3S_URL='${K3S_URL}' K3S_TOKEN='${K3S_TOKEN}' \
  K3S_NODE_IP='${K3S_NODE_IP}' K3S_NODE_NAME='${K3S_NODE_NAME}' \
  K3S_NODE_LABELS='${K3S_NODE_LABELS}' bash ~/install-agent.sh"

echo ""
echo "==> Step 4/5: Registry + WOL on gpu-server..."
ssh -t "${SSH_OPTS[@]}" "${GPU_HOST}" 'sudo REGISTRY_HOSTS="192.168.10.73:30500 registry.cicd.svc.cluster.local:5000" bash ~/configure-insecure-registry.sh'

ssh -t "${SSH_OPTS[@]}" "${GPU_HOST}" 'IF=eno1; if ip link show "$IF" >/dev/null 2>&1; then \
  sudo cp ~/wol-eno1.service /etc/systemd/system/wol-eno1.service; \
  sudo systemctl daemon-reload; \
  sudo systemctl enable --now wol-eno1.service; \
  sudo ethtool -s "$IF" wol g 2>/dev/null || true; \
  ethtool "$IF" 2>/dev/null | grep -i wake-on || true; \
else echo "WARN: eno1 not found — skip WOL unit"; fi'

echo ""
echo "==> Step 5/5: Waiting for node Ready + labels..."
for _ in $(seq 1 36); do
  if kubectl --kubeconfig "${KUBECONFIG}" get node "${K3S_NODE_NAME}" >/dev/null 2>&1; then
    ready="$(kubectl --kubeconfig "${KUBECONFIG}" get node "${K3S_NODE_NAME}" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)"
    if [[ "${ready}" == "True" ]]; then
      break
    fi
  fi
  sleep 5
done

"${ROOT}/scripts/k3s/label-gpu-server.sh"

echo ""
kubectl --kubeconfig "${KUBECONFIG}" get node "${K3S_NODE_NAME}" -o wide
kubectl --kubeconfig "${KUBECONFIG}" get node "${K3S_NODE_NAME}" --show-labels
echo ""
echo "PASS gpu-server joined. P5a complete."
