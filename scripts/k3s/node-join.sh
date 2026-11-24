#!/usr/bin/env bash
# node-join.sh — add one machine to the cluster as a K3s agent, in one run.
#
#   bash scripts/k3s/node-join.sh <node-name> <ip> [pool]
#   e.g. bash scripts/k3s/node-join.sh ubt-k3s-06 192.168.10.79 general
#
# Run on the Owner's computer, from the bifrost-trade-infra root. The new
# machine must already run Ubuntu with user vision and SSH.
#
# Why one script (2026-11-24): re-adding ubt-k3s-06 stopped at "whose key
# reaches 01 and how is the token fetched", found only by asking around; the
# per-node join-ubt-k3s-0X.sh copies also still read the server token, which
# install-agent.sh refuses since TD-450. This script checks both SSH paths
# first and names the one that is missing, then does the whole join.
#
# The token (the agent token, TD-450) goes 01 -> this computer's memory -> the
# new machine's install-agent.sh. It is never printed or written to a file here.
# Labels are set at join (install-agent.sh --node-label), so no label card.
set -euo pipefail

NAME="${1:?usage: node-join.sh <node-name> <ip> [pool]}"
IP="${2:?usage: node-join.sh <node-name> <ip> [pool]}"
POOL="${3:-general}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP_HOST="${BOOTSTRAP_HOST:-vision@192.168.10.73}" # ubt-k3s-01, the first server
TARGET="vision@${IP}"
K3S_URL="${K3S_URL:-https://192.168.10.73:6443}"
KUBECONFIG="${KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}"
SSH_OPTS=(-o ConnectTimeout=15 -o ServerAliveInterval=30)
LABELS="bifrost.io/host-id=${NAME},bifrost.io/workload-pool=${POOL}"

[[ "${NAME}" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || { echo "node name ${NAME} is not a valid Kubernetes name" >&2; exit 2; }
[[ "${IP}" =~ ^192\.168\.10\.[0-9]{1,3}$ ]] || { echo "${IP} is not on 192.168.10.0/24" >&2; exit 2; }

echo "== join ${NAME} (${IP}) pool=${POOL} =="

# 1. Preconditions, all read-only. Each failure says what to do.
step() { echo; echo "==> $*"; }
step "1/6 checks"
if kubectl --kubeconfig "${KUBECONFIG}" get node "${NAME}" >/dev/null 2>&1; then
  echo "STOP: a node named ${NAME} already exists. Remove it first (scripts/k3s/node-leave.sh ${NAME})." >&2
  exit 1
fi
INSTALL_K3S_VERSION="${INSTALL_K3S_VERSION:-$(KUBECONFIG="${KUBECONFIG}" "${ROOT}/scripts/k3s/control-plane-version.sh")}"
echo "    k3s version (control plane): ${INSTALL_K3S_VERSION}"
for pair in "01|${BOOTSTRAP_HOST}" "new machine|${TARGET}"; do
  label="${pair%%|*}" host="${pair#*|}"
  if ! ssh "${SSH_OPTS[@]}" -o BatchMode=yes "${host}" true 2>/dev/null; then
    echo "STOP: this computer's SSH key does not reach ${label} (${host})." >&2
    echo "  Put this computer's public key there first:  ssh-copy-id ${host}" >&2
    echo "  (asks for ${host%@*}'s password once). Or run this script from a computer whose key already reaches both." >&2
    exit 1
  fi
  echo "    ssh ${label} (${host}): ok"
done
remote_host="$(ssh "${SSH_OPTS[@]}" "${TARGET}" hostname -s)"
[[ "${remote_host}" == "${NAME}" ]] || { echo "STOP: ${IP} calls itself ${remote_host}, not ${NAME}. Set its hostname first." >&2; exit 1; }

# 2. Token: sudo on 01 needs a terminal for its password, and with a terminal
#    the prompt would land in captured output. So: one terminal session copies the
#    token into a 600 file owned by vision; a second session without a terminal
#    reads it into memory and deletes it.
step "2/6 agent token from 01 (sudo password on 01 if asked)"
REMOTE_TOKEN=/home/vision/.bifrost-join-token
ssh -t "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}" "sudo install -m 600 -o vision -g vision /var/lib/rancher/k3s/server/agent-token ${REMOTE_TOKEN}"
K3S_TOKEN="$(ssh "${SSH_OPTS[@]}" "${BOOTSTRAP_HOST}" "cat ${REMOTE_TOKEN}; rm -f ${REMOTE_TOKEN}" | tr -d '\r\n')"
case "${K3S_TOKEN}" in
  K10*::node:*) echo "    ok (${#K3S_TOKEN} chars, not shown)" ;;
  *) echo "STOP: what came back from 01 is not an agent token." >&2; exit 1 ;;
esac

# 3. Scripts onto the new machine.
step "3/6 copy install scripts"
scp "${SSH_OPTS[@]}" "${ROOT}/scripts/k3s/install-agent.sh" "${ROOT}/scripts/k3s/configure-insecure-registry.sh" "${TARGET}:~/"

# 4. Join, labels included. The token goes over the ssh channel into a 600 file
#    (never on this computer's command line), then the terminal session that runs
#    sudo reads and deletes it.
step "4/6 install k3s agent (sudo password on ${NAME} if asked)"
printf '%s\n' "${K3S_TOKEN}" | ssh "${SSH_OPTS[@]}" "${TARGET}" 'umask 077; cat > ~/.bifrost-join-token'
unset K3S_TOKEN
ssh -t "${SSH_OPTS[@]}" "${TARGET}" "t=\$(cat ~/.bifrost-join-token); rm -f ~/.bifrost-join-token; sudo K3S_URL='${K3S_URL}' K3S_TOKEN=\"\$t\" \\
  K3S_NODE_IP='${IP}' K3S_NODE_NAME='${NAME}' K3S_NODE_LABELS='${LABELS}' \\
  INSTALL_K3S_VERSION='${INSTALL_K3S_VERSION}' bash ~/install-agent.sh"

# 5. Registry mirror config (same hosts as every node).
step "5/6 registry"
ssh -t "${SSH_OPTS[@]}" "${TARGET}" 'sudo REGISTRY_HOSTS="192.168.10.73:30500 registry.cicd.svc.cluster.local:5000" bash ~/configure-insecure-registry.sh'

# 5b. NFS client: CI and data volumes mount NFS from the NAS. ubt-k3s-06 rejoined
#     without it on 2026-11-24 and CI pods there failed FailedMount x20 ("might need a
#     /sbin/mount.nfs helper") until nfs-common was installed (card #746).
step "5b/6 nfs-common"
ssh -t "${SSH_OPTS[@]}" "${TARGET}" 'sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nfs-common && test -x /sbin/mount.nfs'

# 6. Ready.
step "6/6 wait for Ready"
ready=""
for _ in $(seq 1 60); do
  ready="$(kubectl --kubeconfig "${KUBECONFIG}" get node "${NAME}" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)"
  [[ "${ready}" == True ]] && break
  sleep 5
done
kubectl --kubeconfig "${KUBECONFIG}" get node "${NAME}" -o wide || true
[[ "${ready}" == True ]] || { echo "FAIL: ${NAME} not Ready after 5 minutes; on it: sudo journalctl -u k3s-agent -n 50" >&2; exit 1; }
echo
echo "PASS ${NAME} joined at ${INSTALL_K3S_VERSION}, labels ${LABELS}."
echo "Tell the compute line \"${NAME} joined\": it registers the node (topology, node table, CI home)."
