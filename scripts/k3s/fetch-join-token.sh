#!/usr/bin/env bash
# Fetch K3s agent join token from bootstrap — run alone if join-gpu-server hangs.
# Saves to ~/.bifrost-k3s-node-token (chmod 600). Then:
#   export K3S_TOKEN=$(cat ~/.bifrost-k3s-node-token)
#   make k3s-join-gpu-server
set -euo pipefail

BOOTSTRAP_HOST="${BOOTSTRAP_HOST:-vision@192.168.10.73}"
OUT="${HOME}/.bifrost-k3s-node-token"
REMOTE="/home/vision/.bifrost-k3s-node-token"
SSH_OPTS=(-o ConnectTimeout=15)

echo "SSH to ${BOOTSTRAP_HOST} — enter sudo password when prompted."
ssh -t "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}" \
  "sudo bash -c 'cat /var/lib/rancher/k3s/server/node-token > ${REMOTE} && chown vision:vision ${REMOTE} && chmod 600 ${REMOTE}'"

scp "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}:${REMOTE}" "${OUT}"
chmod 600 "${OUT}"
ssh "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}" "rm -f ${REMOTE}" || true

echo "Saved: ${OUT} ($(wc -c < "${OUT}") bytes)"
echo "Next:  export K3S_TOKEN=\$(cat ${OUT}) && make k3s-join-gpu-server"
