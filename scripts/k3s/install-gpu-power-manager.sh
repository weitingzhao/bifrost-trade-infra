#!/usr/bin/env bash
# Install gpu-node-power-manager as systemd service on bootstrap (192.168.10.73).
#
# Run from Mac (interactive — will prompt sudo on bootstrap once):
#   make gpu-install-power-manager
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTROLLER_HOST="${CONTROLLER_HOST:-vision@192.168.10.73}"
REMOTE_DIR="/home/vision/bifrost-k3s"
ENV_SRC="${GPU_POWER_ENV:-${ROOT}/config/gpu-node-power.env}"
ENV_EXAMPLE="${ROOT}/config/gpu-node-power.env.example"

echo "== Install gpu-node-power-manager on ${CONTROLLER_HOST} =="

if [[ ! -f "${ENV_SRC}" ]]; then
  echo "Creating ${ENV_SRC} from example (review WOL_MAC / IDLE_MINUTES)"
  cp "${ENV_EXAMPLE}" "${ENV_SRC}"
fi

echo "==> Copying files to ${CONTROLLER_HOST}:${REMOTE_DIR}/ ..."
ssh "${CONTROLLER_HOST}" "mkdir -p ${REMOTE_DIR}"
scp \
  "${ROOT}/scripts/k3s/gpu-node-power-manager.sh" \
  "${ROOT}/scripts/k3s/install-gpu-power-manager-remote.sh" \
  "${CONTROLLER_HOST}:${REMOTE_DIR}/"
scp "${ENV_SRC}" "${CONTROLLER_HOST}:${REMOTE_DIR}/gpu-node-power.env"

echo ""
echo "==> Running remote install on bootstrap"
echo "    Enter sudo password on ${CONTROLLER_HOST} when prompted."
echo ""

ssh -t "${CONTROLLER_HOST}" "bash ${REMOTE_DIR}/install-gpu-power-manager-remote.sh"

echo ""
echo "PASS power manager installed on ${CONTROLLER_HOST}"
echo "  ssh -t ${CONTROLLER_HOST} 'journalctl -u bifrost-gpu-power-manager -f'"
