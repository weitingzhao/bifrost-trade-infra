#!/usr/bin/env bash
# Step 3 — gpu-server on-demand power: WOL when compute pods Pending, poweroff when idle.
#
# Run foreground:  make gpu-power-manager
# Install on .73:   make gpu-install-power-manager
#
# Requires: kubectl, wakeonlan (or etherwake), SSH to gpu-server for poweroff.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${GPU_POWER_ENV:-${ROOT}/config/gpu-node-power.env}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

GPU_NODE_NAME="${GPU_NODE_NAME:-gpu-server}"
GPU_SSH_HOST="${GPU_SSH_HOST:-vision@192.168.10.60}"
WOL_MAC="${WOL_MAC:-}"
POLL_INTERVAL="${POLL_INTERVAL:-60}"
IDLE_MINUTES="${IDLE_MINUTES:-30}"
WAKE_TIMEOUT="${WAKE_TIMEOUT:-600}"
AUTO_POWEROFF="${AUTO_POWEROFF:-1}"
KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
export KUBECONFIG

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

send_wol() {
  local mac="$1"
  if command -v wakeonlan >/dev/null 2>&1; then
    wakeonlan "${mac}"
  elif command -v etherwake >/dev/null 2>&1; then
    sudo etherwake "${mac}"
  else
    log "ERROR: install wakeonlan or etherwake" >&2
    return 1
  fi
  log "WOL sent to ${mac}"
}

resolve_wol_mac() {
  if [[ -n "${WOL_MAC}" ]]; then
    echo "${WOL_MAC}"
    return
  fi
  kubectl get node "${GPU_NODE_NAME}" -o jsonpath='{.metadata.annotations.bifrost\.io/wol-mac}' 2>/dev/null || true
}

node_ready() {
  local status
  status="$(kubectl get node "${GPU_NODE_NAME}" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "False")"
  [[ "${status}" == "True" ]]
}

# Pending pods targeting gpu-server node pools
pending_compute_count() {
  kubectl get pods -A -o json | python3 -c "
import json, sys
data = json.load(sys.stdin)
selectors = [
    ('workload', 'gpu'),
    ('node-role', 'warehouse'),
    ('bifrost.io/workload-pool', 'compute'),
]
count = 0
for pod in data.get('items', []):
    if pod.get('status', {}).get('phase') != 'Pending':
        continue
    spec = pod.get('spec') or {}
    ns = spec.get('nodeSelector') or {}
    matched = any(ns.get(k) == v for k, v in selectors)
    if matched or spec.get('nodeName') == '${GPU_NODE_NAME}':
        count += 1
print(count)
"
}

log_pending_compute_pods() {
  kubectl get pods -A -o json | python3 -c "
import json, sys
data = json.load(sys.stdin)
selectors = [
    ('workload', 'gpu'),
    ('node-role', 'warehouse'),
    ('bifrost.io/workload-pool', 'compute'),
]
for pod in data.get('items', []):
    if pod.get('status', {}).get('phase') != 'Pending':
        continue
    spec = pod.get('spec') or {}
    ns = spec.get('nodeSelector') or {}
    matched = any(ns.get(k) == v for k, v in selectors)
    if matched or spec.get('nodeName') == '${GPU_NODE_NAME}':
        meta = pod.get('metadata') or {}
        print(f\"  pending {meta.get('namespace')}/{meta.get('name')}\")
" 2>/dev/null || true
}

# Non-DaemonSet pods running on gpu-server (user workloads)
user_pods_on_node() {
  kubectl get pods -A --field-selector "spec.nodeName=${GPU_NODE_NAME}" -o json | python3 -c "
import json, sys
data = json.load(sys.stdin)
n = 0
for pod in data.get('items', []):
    if pod.get('metadata', {}).get('namespace') == 'kube-system':
        continue
    owner = pod.get('metadata', {}).get('ownerReferences') or []
    if any(o.get('kind') == 'DaemonSet' for o in owner):
        continue
    phase = pod.get('status', {}).get('phase')
    if phase in ('Running', 'Pending', 'ContainerCreating'):
        n += 1
print(n)
"
}

wait_node_ready() {
  local deadline=$((SECONDS + WAKE_TIMEOUT))
  while (( SECONDS < deadline )); do
    if node_ready; then
      log "Node ${GPU_NODE_NAME} is Ready"
      return 0
    fi
    sleep 10
  done
  log "WARN: timeout waiting for ${GPU_NODE_NAME} Ready"
  return 1
}

power_off_node() {
  log "Draining ${GPU_NODE_NAME}..."
  kubectl drain "${GPU_NODE_NAME}" --ignore-daemonsets --delete-emptydir-data --force --grace-period=60 2>/dev/null || true
  log "Powering off ${GPU_SSH_HOST}..."
  if [[ "$(id -un)" == "root" && -n "${SUDO_USER:-}" ]]; then
    sudo -u "${SUDO_USER}" ssh -o ConnectTimeout=15 -o BatchMode=yes "${GPU_SSH_HOST}" 'sudo -n systemctl poweroff' 2>/dev/null || \
      sudo -u "${SUDO_USER}" ssh -t "${GPU_SSH_HOST}" 'sudo systemctl poweroff' || true
  else
    ssh -o ConnectTimeout=15 -o BatchMode=yes "${GPU_SSH_HOST}" 'sudo -n systemctl poweroff' 2>/dev/null || \
      ssh -t "${GPU_SSH_HOST}" 'sudo systemctl poweroff' || true
  fi
  log "Poweroff command sent"
}

IDLE_SECONDS=$((IDLE_MINUTES * 60))
idle_since=0
wake_in_progress=0

log "gpu-node-power-manager started (node=${GPU_NODE_NAME}, idle=${IDLE_MINUTES}m, poll=${POLL_INTERVAL}s)"

while true; do
  mac="$(resolve_wol_mac)"
  pending="$(pending_compute_count | tr -d '[:space:]' || echo 0)"
  pending="${pending:-0}"

  if node_ready; then
    wake_in_progress=0
    users="$(user_pods_on_node | tr -d '[:space:]' || echo 0)"
    users="${users:-0}"

    if [[ "${pending}" -gt 0 && "${users}" -eq 0 ]]; then
      log "Node Ready but ${pending} Pending compute pod(s) — waiting for scheduler"
    fi

    if [[ "${AUTO_POWEROFF}" == "1" && "${users}" -eq 0 && "${pending}" -eq 0 ]]; then
      if (( idle_since == 0 )); then
        idle_since=$SECONDS
        log "Idle timer started (${IDLE_MINUTES}m until poweroff)"
      elif (( SECONDS - idle_since >= IDLE_SECONDS )); then
        power_off_node
        idle_since=0
        sleep 120
      fi
    else
      idle_since=0
    fi
  else
    idle_since=0
    if [[ "${pending}" -gt 0 && "${wake_in_progress}" -eq 0 ]]; then
      if [[ -z "${mac}" ]]; then
        log "ERROR: ${pending} pending compute pod(s) but no WOL MAC (set WOL_MAC or node annotation)"
      else
        wake_in_progress=1
        log "${pending} pending compute pod(s), node not Ready — sending WOL to ${mac}"
        log_pending_compute_pods
        send_wol "${mac}" || true
        wait_node_ready || wake_in_progress=0
      fi
    fi
  fi

  sleep "${POLL_INTERVAL}"
done
