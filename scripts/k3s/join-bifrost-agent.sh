#!/usr/bin/env bash
# Join this host as K3s agent + configure registry for bifrost-stg/prod pulls.
# Prereq: install-agent.sh, configure-insecure-registry.sh, .join-env in same dir.
#
# On target (.70):
#   echo 'K3S_TOKEN=<from bootstrap>' > ~/.join-env && chmod 600 ~/.join-env
#   ssh -t vision@192.168.10.70 'bash ~/join-bifrost-agent.sh'
set -euo pipefail

VISION_HOME="${VISION_HOME:-/home/vision}"
# shellcheck disable=SC1091
[[ -f "${VISION_HOME}/.join-env" ]] && source "${VISION_HOME}/.join-env"

K3S_URL="${K3S_URL:-https://192.168.10.73:6443}"
K3S_TOKEN="${K3S_TOKEN:?set K3S_TOKEN in ${VISION_HOME}/.join-env}"
K3S_NODE_IP="${K3S_NODE_IP:?set K3S_NODE_IP}"
K3S_NODE_NAME="${K3S_NODE_NAME:-$(hostname -s)}"

if [[ "${EUID}" -ne 0 ]]; then
  exec sudo K3S_URL="${K3S_URL}" K3S_TOKEN="${K3S_TOKEN}" K3S_NODE_IP="${K3S_NODE_IP}" K3S_NODE_NAME="${K3S_NODE_NAME}" \
    VISION_HOME="${VISION_HOME}" bash "${VISION_HOME}/join-bifrost-agent.sh"
fi

export K3S_URL K3S_TOKEN K3S_NODE_IP K3S_NODE_NAME
bash "${VISION_HOME}/install-agent.sh"

REGISTRY_HOSTS="${REGISTRY_HOSTS:-192.168.10.73:30500 registry.cicd.svc.cluster.local:5000}"
export REGISTRY_HOSTS
bash "${VISION_HOME}/configure-insecure-registry.sh"

echo ""
echo "Done. Verify: kubectl get nodes -o wide"
echo "Label prod pool: kubectl label node ${K3S_NODE_NAME} bifrost.io/host-id=mini-pc-a bifrost.io/workload-pool=prod --overwrite"
