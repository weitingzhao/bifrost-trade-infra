#!/usr/bin/env bash
# install-node-key.sh — put the Owner's node key (its public half) into
# vision's ~/.ssh/authorized_keys on the cluster's nodes, through one short
# pod per node, with the admin kubeconfig. For when SSH reaches no node: on
# 2026-10-17 the node key's passphrase was lost and the key file was
# replaced by a new one (agent-config/work/multi-agent/OWNER-STEPS-agent-host-06.md).
# Only the Owner runs it.
#
#   bash install-node-key.sh                 every Ready node but gpu-server
#   bash install-node-key.sh <node>…         just these
#
# On each node it appends the key only if that exact line is not there yet,
# after a dated copy of the file; it removes nothing and changes no owner or
# mode. It prints the key's fingerprint first (compare it with the one
# ssh-keygen printed), then per node the key count before and after. It stops
# at the first node that fails; a second run is harmless.
set -euo pipefail

PUB=/Users/vision-mac-trader/.bifrost-owner/ssh/node.pub
export KUBECONFIG=${INSTALL_NODE_KEY_KUBECONFIG:-/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml}
NS=kube-system
# busybox 1.36, by digest (already on the nodes; read 2026-10-17).
IMAGE=docker.io/library/busybox@sha256:73aaf090f3d85aa34ee199857f03fa3a95c8ede2ffd4cc2cdb5b94e566b11662
STAMP=$(date +%Y%m%dT%H%M%S)

die() {
  echo "install-node-key: $*" >&2
  exit 1
}
say() { echo "==> $*"; }
TMPD=$(mktemp -d)
POD=""
cleanup() {
  [ -z "$POD" ] || kubectl -n "$NS" delete pod "$POD" --ignore-not-found --wait=false > /dev/null 2>&1 || true
  rm -rf "$TMPD"
}
trap cleanup EXIT

# The script the pod runs: the key comes in $PUBKEY, the node's
# /home/vision/.ssh is mounted at /host-ssh.
NODE_SCRIPT='set -eu
f=/host-ssh/authorized_keys
[ -f "$f" ] && [ ! -L "$f" ] || { echo "no regular authorized_keys file"; exit 3; }
before=$(grep -c . "$f" || true)
if grep -qxF "$PUBKEY" "$f"; then
  echo "the key is already there"
else
  cp -p "$f" "$f.before-$STAMP"
  # A last line without its newline would run into the new one.
  [ -z "$(tail -c 1 "$f")" ] || printf "\n" >> "$f"
  printf "%s\n" "$PUBKEY" >> "$f"
  grep -qxF "$PUBKEY" "$f" || { echo "the key did not land"; exit 4; }
fi
echo "keys: $before -> $(grep -c . "$f"); file $(stat -c "%u:%g %a" "$f")"'

check_pub() {
  [ -f "$PUB" ] || die "no $PUB"
  [ "$(grep -c . "$PUB")" = 1 ] || die "$PUB is not one line"
  grep -qE '^ssh-ed25519 [A-Za-z0-9+/]+=* ?' "$PUB" || die "$PUB is not an ed25519 public key"
  say "the key to install: $(ssh-keygen -l -f "$PUB")"
}

ready_nodes() {
  kubectl get nodes -o json > "$TMPD/nodes.json" || die "cannot list the nodes"
  python3 -I -c '
import json, sys
for n in json.load(open(sys.argv[1]))["items"]:
    ready = [c for c in n["status"].get("conditions") or [] if c["type"] == "Ready"]
    name = n["metadata"]["name"]
    if ready and ready[0]["status"] == "True" and name != "gpu-server":
        print(name)
' "$TMPD/nodes.json"
}

install_on() {
  local node=$1 phase i
  POD=owner-node-key-$node-$STAMP
  python3 -I -c '
import json, sys
pod, ns, node, image, script, stamp, pub = sys.argv[1:8]
print(json.dumps({
    "apiVersion": "v1", "kind": "Pod",
    "metadata": {"name": pod, "namespace": ns, "labels": {"bifrost.io/purpose": "owner-node-key"}},
    "spec": {
        "nodeName": node,
        "restartPolicy": "Never",
        "automountServiceAccountToken": False,
        "tolerations": [{"operator": "Exists"}],
        "containers": [{
            "name": "key", "image": image, "imagePullPolicy": "IfNotPresent",
            "command": ["/bin/sh", "-c", script],
            "env": [{"name": "PUBKEY", "value": pub}, {"name": "STAMP", "value": stamp}],
            "securityContext": {"runAsUser": 0, "allowPrivilegeEscalation": False},
            "volumeMounts": [{"name": "ssh", "mountPath": "/host-ssh"}],
        }],
        "volumes": [{"name": "ssh", "hostPath": {"path": "/home/vision/.ssh", "type": "Directory"}}],
    },
}))
' "$POD" "$NS" "$node" "$IMAGE" "$NODE_SCRIPT" "$STAMP" "$(cat "$PUB")" > "$TMPD/pod.json"
  kubectl apply -f "$TMPD/pod.json" > /dev/null || die "$node: could not create the pod"
  phase=""
  for i in $(seq 1 60); do
    phase=$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.status.phase}') || die "$node: cannot read the pod"
    case "$phase" in Succeeded | Failed) break ;; esac
    sleep 2
  done
  kubectl -n "$NS" logs "$POD" 2>&1 | sed "s/^/   $node: /" || true
  [ "$phase" = Succeeded ] || die "$node: the pod ended $phase; nothing more was done"
  kubectl -n "$NS" delete pod "$POD" --wait=false > /dev/null || true
  POD=""
}

# Sourced (by a test), stop here.
[ "${BASH_SOURCE[0]}" = "$0" ] || return 0

check_pub
if [ "$#" -gt 0 ]; then
  nodes="$*"
else
  nodes=$(ready_nodes | tr '\n' ' ')
fi
[ -n "$nodes" ] || die "no node to install on"
say "nodes: $nodes"
for node in $nodes; do
  install_on "$node"
done
say "installed on: $nodes"
