#!/usr/bin/env bash
# TD-450: rotate the K3s server token (the returned old 07 disk holds the old one) and give agents a
# separate agent token, so no agent keeps a credential that is cluster-admin. The Owner runs this on
# the MacBook, one subcommand at a time, in the order of
# agent-config/work/multi-agent/OWNER-STEPS-td450-2026-10-28.md. Tokens never print: they move
# through ssh stdin into 600 files that each step deletes.
#
#   check                 read-only: what 01 and each agent hold (the kind of token, never the value)
#   server                01: snapshot, rotate, separate agent token, restart k3s, old 401 / new 200
#   agent <node> <ip>     one agent: put the agent token in k3s-agent.service.env, restart, wait Ready
#   finish                01: bootstrap tokens left; agents: drop env backups and old ~/.join-env
#   forget-old            7 days later, 01: delete the pre-td450 snapshot and the old token copy
set -euo pipefail

CP_IP=192.168.10.73
NODES=("ubt-k3s-05 192.168.10.77" "ubt-k3s-04 192.168.10.75" "ubt-k3s-07 192.168.10.80" "ubt-k3s-02 192.168.10.70" "gpu-server 192.168.10.60")
HERE="$(cd "$(dirname "$0")" && pwd)"
KUBE=(kubectl --kubeconfig "$HOME/.kube/bifrost-k3s.yaml")
# Cluster nodes take the Owner node key (LANE-W33D), as join-07 and host-exporters.sh do.
NODE_KEY="${NODE_KEY:-$HOME/.bifrost-owner/ssh/node}"
SSHO=(-F /dev/null -o IdentitiesOnly=yes -o IdentityAgent=none -o PreferredAuthentications=publickey
  -o UserKnownHostsFile="$HOME/.ssh/known_hosts" -o ConnectTimeout=15 -i "$NODE_KEY")

die() { echo "STOP: $*" >&2; exit 1; }
ready() { "${KUBE[@]}" get node "$1" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true; }

# remote <ip> <script> <mode>: copy a helper and run it under sudo with a tty for the password.
remote() {
  local ip=$1 script=$2 mode=$3
  scp -q "${SSHO[@]}" "$HERE/$script" "vision@$ip:~/$script"
  ssh -t "${SSHO[@]}" "vision@$ip" "sudo bash ~/$script $mode; rc=\$?; rm -f ~/$script ~/.td450-agent-token; exit \$rc"
}

case "${1:-}" in
  check)
    echo "== ubt-k3s-01 (server)"
    remote "$CP_IP" td450-server.sh check
    for n in "${NODES[@]}"; do
      set -- $n
      echo "== $1 ($2): Ready=$(ready "$1")"
      remote "$2" td450-node.sh check || echo "   (no ssh to $1: off, or it does not take the node key)"
    done
    [[ -f "$HOME/.bifrost-k3s-node-token" ]] && echo "== MacBook: ~/.bifrost-k3s-node-token holds the old server token (fetch-join-token.sh); 'server' deletes it"
    true ;;
  server)
    "${KUBE[@]}" get nodes
    remote "$CP_IP" td450-server.sh rotate
    echo "== cluster after the restart (read-only)"
    for _ in $(seq 1 30); do "${KUBE[@]}" get --raw /readyz >/dev/null 2>&1 && break; sleep 2; done
    "${KUBE[@]}" get nodes
    rm -f "$HOME/.bifrost-k3s-node-token" ;;
  agent)
    name=${2:?usage: agent <node> <ip>}; ip=${3:?usage: agent <node> <ip>}
    [[ $name != ubt-k3s-01 ]] || die "01 is the server; use 'server'"
    echo "== $name: Ready before = $(ready "$name")"
    echo "== ubt-k3s-01: read the agent token (sudo password for 01)"
    tok="$(ssh -t "${SSHO[@]}" "vision@$CP_IP" 'sudo cat /var/lib/rancher/k3s/server/agent-token' | tr -d '\r' | tail -1)"
    case "$tok" in K10*::node:*) echo "agent token ok (not shown)" ;; *) die "no agent token came back (run 'server' first)" ;; esac
    printf '%s\n' "$tok" | ssh "${SSHO[@]}" "vision@$ip" 'umask 077; cat > ~/.td450-agent-token'
    unset tok
    echo "== $name: write the env and restart k3s-agent (sudo password for $name); running pods keep running"
    remote "$ip" td450-node.sh apply
    for _ in $(seq 1 45); do [[ "$(ready "$name")" == True ]] && break; sleep 4; done
    echo "== $name: Ready after = $(ready "$name")"
    [[ "$(ready "$name")" == True ]] || die "$name is not Ready: OWNER-STEPS §5" ;;
  finish)
    echo "== ubt-k3s-01: bootstrap tokens still valid"
    remote "$CP_IP" td450-server.sh list
    for n in "${NODES[@]}"; do
      set -- $n
      [[ "$(ready "$1")" == True ]] || { echo "== $1 not Ready: skipped"; continue; }
      echo "== $1: drop the env backup and any ~/.join-env (both hold the old token)"
      remote "$2" td450-node.sh cleanup
    done ;;
  forget-old) remote "$CP_IP" td450-server.sh forget-old ;;
  *) die "usage: $0 check | server | agent <node> <ip> | finish | forget-old" ;;
esac
