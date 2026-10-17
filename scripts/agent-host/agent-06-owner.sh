#!/usr/bin/env bash
# agent-06-owner.sh — the Owner's steps, from his Mac, to take ubt-k3s-06 out
# of the cluster and make it the agent host (Owner 2026-10-17;
# agent-config/work/multi-agent/OWNER-STEPS-agent-host-06.md). It uses the
# admin kubeconfig and the node key, so only the Owner runs it.
#
#   bash agent-06-owner.sh <step>
#
#   check                 read only: what is on 06 and what leave would do
#   leave                 cordon, back up the event-radar volume, delete 06's
#                         local-path claims, restart the two zero-budget
#                         Deployments, drain
#   uninstall             uninstall k3s on 06 and reboot it
#   delete-node           delete the node object (after uninstall)
#   copy                  scp this directory and the agentd binary to 06
#   prepare               run prepare-agent-06.sh on 06
#   codex-login prod|stg  log codex in as that agent user (device code)
#   vendor-creds          copy Claude's and Cursor's credentials from this Mac
#   git-token prod|stg    read a Gitea token (hidden) and install it on 06
#   host-check base|creds|running   run check-agent-06.sh on 06
#   secret prod|stg       put that agentd's platform token into its Secret
#   start                 enable and start both agentd services
#   retire-mac            stop the agentd on this Mac
#
# Every step stops at its first error and exits non-zero. No step prints a
# credential. Each step but codex-login keeps its output in
# /tmp/agent-06-<step>.txt as well, for the coordinator to read.
set -euo pipefail

NODE=ubt-k3s-06
ADDR=192.168.10.79
NODE_KEY=/Users/vision-mac-trader/.bifrost-owner/ssh/node
WORKSPACE=/Users/vision-mac-trader/Desktop/stocks
HERE=$(cd "$(dirname "$0")" && pwd -P)
BINARY=/Users/vision-mac-trader/agent-work/agentd-build/agentd-f69e8c6-linux-amd64
BACKUP_DIR=/Users/vision-mac-trader/bifrost-backups/event-radar-input/2026-10-17_node06_pvc-6bf6eca6
EVENT_RADAR_PV=pvc-6bf6eca6-5968-4874-ae93-22b8a2a23fab
EVENT_RADAR_DIR=pvc-6bf6eca6-5968-4874-ae93-22b8a2a23fab_research_event-radar-input-pvc
# `check` reads only, so it may run with another kubeconfig (AGENT06_KUBECONFIG).
export KUBECONFIG=${AGENT06_KUBECONFIG:-/Users/vision-mac-trader/.bifrost-owner/kube/admin.yaml}

die() {
  echo "agent-06-owner: $*" >&2
  exit 1
}
# Written for the macOS system bash (3.2) as well: no arrays under set -u.
TMPD=$(mktemp -d)
on_exit() {
  local rc=$?
  rm -rf "$TMPD"
  [ "${LOGGING:-}" = 1 ] && echo "exit=$rc"
  return 0
}
trap on_exit EXIT
say() { echo "==> $*"; }

node_ssh() { ssh -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -o ConnectTimeout=15 -i "$NODE_KEY" "vision@$ADDR" "$@"; }
node_ssh_tty() { ssh -t -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -o ConnectTimeout=15 -i "$NODE_KEY" "vision@$ADDR" "$@"; }

user_of() {
  case "$1" in
    prod) echo bifrost-agentd ;;
    stg) echo bifrost-agentd-stg ;;
    *) die "say prod or stg" ;;
  esac
}

# active_runs: PipelineRuns that have not finished (no Succeeded condition
# with status True or False), one per line. A failed read stops the script.
active_runs() {
  local json
  json=$(kubectl get pipelineruns -n cicd -o json) || die "cannot list PipelineRuns"
  printf '%s' "$json" | python3 -I -c '
import json, sys
for r in json.load(sys.stdin)["items"]:
    c = [c for c in (r.get("status") or {}).get("conditions") or [] if c.get("type") == "Succeeded"]
    if not c or c[0].get("status") not in ("True", "False"):
        print(r["metadata"]["name"])
'
}

# node06_volumes: the PersistentVolumes bound to 06, each checked against what
# leave may delete: the event-radar volume, and local-path workspaces of
# PipelineRuns that have finished. Prints "<pv> <namespace> <claim> <why>"
# per volume; exits non-zero (after printing) if any volume is not one of
# those, so nothing is deleted.
node06_volumes() {
  kubectl get pv -o json > "$TMPD/pv.json" || die "cannot list PersistentVolumes"
  kubectl get pvc -A -o json > "$TMPD/pvc.json" || die "cannot list PersistentVolumeClaims"
  kubectl get pipelineruns -n cicd -o json > "$TMPD/runs.json" || die "cannot list PipelineRuns"
  python3 -I -c '
import json, sys
node, event_radar, d = sys.argv[1], sys.argv[2], sys.argv[3]
pvs, pvcs, runs = (json.load(open(d + "/" + f)) for f in ("pv.json", "pvc.json", "runs.json"))
claims = {(c["metadata"]["namespace"], c["metadata"]["name"]): c for c in pvcs["items"]}
finished = {}
for r in runs["items"]:
    c = [c for c in (r.get("status") or {}).get("conditions") or [] if c.get("type") == "Succeeded"]
    finished[r["metadata"]["name"]] = bool(c) and c[0].get("status") in ("True", "False")
bad = 0
for pv in pvs["items"]:
    spec, meta = pv["spec"], pv["metadata"]
    terms = ((spec.get("nodeAffinity") or {}).get("required") or {}).get("nodeSelectorTerms") or []
    if node not in json.dumps(terms):
        continue
    name, ref = meta["name"], spec.get("claimRef") or {}
    ns, claim = ref.get("namespace", "-"), ref.get("name", "-")
    exact = terms == [{"matchExpressions": [{"key": "kubernetes.io/hostname", "operator": "In", "values": [node]}]}]
    local = (meta.get("annotations") or {}).get("pv.kubernetes.io/provisioned-by") == "rancher.io/local-path"
    pvc = claims.get((ns, claim))
    same = pvc is not None and pvc["metadata"].get("uid") == ref.get("uid")
    why = None
    if exact and local and same:
        if name == event_radar and (ns, claim) == ("research", "event-radar-input-pvc"):
            why = "event-radar (backed up first)"
        elif ns == "cicd":
            owners = [o for o in pvc["metadata"].get("ownerReferences") or [] if o.get("kind") == "PipelineRun"]
            # A run the janitor has already deleted counts as finished.
            if len(owners) == 1 and finished.get(owners[0]["name"], True):
                why = "workspace of finished PipelineRun " + owners[0]["name"]
    if why is None:
        bad += 1
        why = "NOT EXPECTED (local-path=%s, hostname-only=%s, claim-matches=%s)" % (local, exact, same)
    print(name, ns, claim, why)
sys.exit(3 if bad else 0)
' "$NODE" "$EVENT_RADAR_PV" "$TMPD"
}

backup_volume() {
  mkdir -p "$BACKUP_DIR"
  local f=$BACKUP_DIR/event-radar-input-pvc.tar.gz
  if [ -s "$f" ] && gzip -t "$f" && tar -tzf "$f" | grep -q "^$EVENT_RADAR_DIR/"; then
    say "backup already there: $f"
    return
  fi
  node_ssh "sudo test -d /var/lib/rancher/k3s/storage/$EVENT_RADAR_DIR && sudo tar -C /var/lib/rancher/k3s/storage -czf - $EVENT_RADAR_DIR" > "$f.part" ||
    die "the backup did not come through"
  gzip -t "$f.part" || die "the backup is not a whole gzip file"
  tar -tzf "$f.part" | grep -q "^$EVENT_RADAR_DIR/" || die "the backup does not hold $EVENT_RADAR_DIR"
  mv "$f.part" "$f"
  shasum -a 256 "$f" > "$f.sha256"
  say "backed up: $f ($(tar -tzf "$f" | wc -l | tr -d ' ') entries, $(du -h "$f" | cut -f1))"
}

delete_volumes() {
  local listing pv ns claim left i rc
  listing=$(node06_volumes) && rc=0 || rc=$?
  printf '%s\n' "$listing"
  [ "$rc" != 3 ] || die "a volume on $NODE is not one leave may delete; nothing was deleted"
  [ "$rc" = 0 ] || die "could not read the volumes on $NODE; nothing was deleted"
  [ -n "$listing" ] || {
    say "no volume on $NODE"
    return
  }
  if printf '%s\n' "$listing" | grep -q '^'"$EVENT_RADAR_PV"' '; then
    [ -s "$BACKUP_DIR/event-radar-input-pvc.tar.gz" ] || die "event-radar is not backed up"
  fi
  while read -r pv ns claim _; do
    kubectl -n "$ns" delete pvc "$claim" --wait=false || die "could not delete $ns/$claim"
  done <<<"$listing"
  for i in $(seq 1 30); do
    left=$(node06_volumes) || die "while waiting: could not read the volumes on $NODE, or one that leave may not delete appeared"
    [ -z "$left" ] && {
      say "all volumes on $NODE are gone"
      return
    }
    sleep 10
  done
  printf '%s\n' "$left"
  die "volumes on $NODE are still there after 5 minutes"
}

pods_left_on_node() { # pods on 06 that are neither DaemonSet pods nor finished
  kubectl get pods -A --field-selector "spec.nodeName=$NODE" -o json | python3 -I -c '
import json, sys
for p in json.load(sys.stdin)["items"]:
    kinds = [o.get("kind") for o in p["metadata"].get("ownerReferences") or []]
    if "DaemonSet" in kinds or p["status"].get("phase") in ("Succeeded", "Failed"):
        continue
    print(p["metadata"]["namespace"] + "/" + p["metadata"]["name"])
'
}

step_check() {
  say "release window"
  "$WORKSPACE/bifrost-trade-infra/scripts/release/release.sh" window || true
  say "PipelineRuns not finished"
  active_runs
  say "volumes on $NODE"
  local rc
  node06_volumes && rc=0 || rc=$?
  case $rc in 0) ;; 3) echo "(leave would stop here: a volume above is not expected)" ;; *) die "could not read the volumes" ;; esac
  say "pods on $NODE (not DaemonSet, not finished)"
  pods_left_on_node
}

step_leave() {
  say "no release window, no PipelineRun in flight"
  "$WORKSPACE/bifrost-trade-infra/scripts/release/release.sh" window || die "a release window is open; run leave again when it has closed"
  local active
  active=$(active_runs)
  [ -z "$active" ] || die "PipelineRuns still running: $(echo "$active" | tr '\n' ' ')"
  say "cordon"
  kubectl cordon "$NODE"
  # A run that started between the check and the cordon: its pods may be on
  # 06. Nothing new lands there now; wait for those to finish.
  active=$(active_runs)
  [ -z "$active" ] || die "a PipelineRun started meanwhile ($(echo "$active" | tr '\n' ' ')); $NODE stays cordoned, run leave again when it has finished"
  say "back up the event-radar volume"
  backup_volume
  say "delete the local-path claims on $NODE"
  delete_volumes
  say "restart the two Deployments whose PodDisruptionBudget allows no eviction"
  kubectl -n plugin-market-data rollout restart deployment/polygon-worker-options deployment/polygon-worker-stocks
  kubectl -n plugin-market-data rollout status deployment/polygon-worker-options --timeout=15m
  kubectl -n plugin-market-data rollout status deployment/polygon-worker-stocks --timeout=15m
  say "drain"
  kubectl drain "$NODE" --ignore-daemonsets --delete-emptydir-data --timeout=15m
  local left
  left=$(pods_left_on_node) || die "cannot list the pods on $NODE"
  [ -z "$left" ] || die "pods still on $NODE: $(echo "$left" | tr '\n' ' ')"
  say "drained: only DaemonSet pods are left on $NODE"
}

step_uninstall() {
  [ "$(kubectl get node "$NODE" -o jsonpath='{.spec.unschedulable}')" = true ] || die "$NODE is not cordoned: run leave first"
  local left
  left=$(pods_left_on_node) || die "cannot list the pods on $NODE"
  [ -z "$left" ] || die "pods still on $NODE: run leave first"
  say "uninstall k3s on $NODE"
  node_ssh 'sudo /usr/local/bin/k3s-agent-uninstall.sh'
  say "reboot $NODE (the connection drops)"
  node_ssh 'sudo systemctl reboot' || true
}

step_delete_node() {
  local ready
  ready=$(kubectl get node "$NODE" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}') || die "cannot read $NODE"
  [ "$ready" != True ] || die "$NODE still reports Ready: its agent is running (run uninstall, or wait a minute after it)"
  kubectl delete node "$NODE"
}

step_copy() {
  (cd "$(dirname "$BINARY")" && shasum -a 256 -c "$HERE/agentd.sha256") || die "$BINARY does not match agentd.sha256"
  scp -F /dev/null -o IdentityAgent=none -o IdentitiesOnly=yes -o ConnectTimeout=15 -i "$NODE_KEY" -r "$HERE" "$BINARY" "vision@$ADDR:"
}

step_prepare() { node_ssh 'sudo bash ~/agent-host/prepare-agent-06.sh'; }

step_codex_login() {
  local u
  u=$(user_of "${1:-}")
  node_ssh_tty "sudo -u $u -H env -i HOME=/home/$u USER=$u LOGNAME=$u PATH=/home/$u/.local/bin:/usr/local/lib/nodejs/current/bin:/usr/bin:/bin bash -c 'cd ~ && codex login --device-auth'"
}

step_vendor_creds() {
  local f src
  sudo -v
  for f in claude-oauth.token cursor-api.key; do
    src=/Users/bifrost-agentd/.config/bifrost/$f
    sudo test -s "$src" || die "$src is missing or empty on this Mac"
    sudo cat "$src" | node_ssh "sudo bash ~/agent-host/install-secret.sh bifrost-agentd $f"
  done
}

step_git_token() {
  local u gitea tok
  u=$(user_of "${1:-}")
  gitea=agentd-agent-06
  [ "$1" = stg ] && gitea=agentd-agent-06-stg
  read -rs -p "Gitea token of $gitea, for $u on 06 (not shown): " tok
  echo
  [ -n "$tok" ] || die "no token given"
  printf '%s' "$tok" | node_ssh "sudo bash ~/agent-host/install-secret.sh $u agentd-git.token"
  unset tok
}

step_host_check() {
  case "${1:-}" in base | creds | running) ;; *) die "say base, creds or running" ;; esac
  node_ssh "sudo bash ~/agent-host/check-agent-06.sh $1"
}

step_secret() {
  local env=${1:-} u ns key tok
  u=$(user_of "$env")
  if [ "$env" = prod ]; then
    ns=bifrost-platform-prod key=PLATFORM_PROD_AGENTD_AGENT_06_TOKEN
  else
    ns=bifrost-platform-stg key=PLATFORM_AGENTD_AGENT_06_STG_TOKEN
  fi
  tok=$(node_ssh "sudo cat /home/$u/.config/bifrost/agentd.token") || die "could not read $u's token on 06"
  [[ $tok =~ ^[0-9a-f]{64}$ ]] || die "$u's token on 06 is not 64 hex characters; nothing was written"
  printf '%s' "$tok" | python3 -I -c 'import json, sys; print(json.dumps({"stringData": {sys.argv[1]: sys.stdin.read()}}))' "$key" > "$TMPD/patch.json"
  unset tok
  kubectl -n "$ns" patch secret bifrost-platform-role-tokens --type merge --patch-file "$TMPD/patch.json"
  rm -f "$TMPD/patch.json"
}

step_start() {
  node_ssh 'sudo systemctl enable --now bifrost-agentd.service bifrost-agentd-stg.service && sleep 20 && sudo bash ~/agent-host/check-agent-06.sh running'
}

step_retire_mac() {
  local rc
  sudo launchctl bootout system/com.bifrost.agentd || true
  for _ in $(seq 1 60); do
    rc=0
    sudo launchctl print system/com.bifrost.agentd >/dev/null 2>&1 || rc=$?
    [ "$rc" = 113 ] && {
      say "the agentd on this Mac is stopped"
      return
    }
    sleep 1
  done
  die "launchd still has com.bifrost.agentd (launchctl print exit $rc)"
}

# Sourced (by a test), stop here: only the functions are wanted.
[ "${BASH_SOURCE[0]}" = "$0" ] || return 0

step=${1:-}
[ -n "$step" ] || {
  sed -n '2,35p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}
shift
case "$step" in
  check | leave | uninstall | delete-node | copy | prepare | codex-login | vendor-creds | git-token | host-check | secret | start | retire-mac) ;;
  *) die "unknown step: $step" ;;
esac
if [ "$step" != codex-login ]; then
  exec > >(tee "/tmp/agent-06-$step${1:+-$1}.txt") 2>&1
  LOGGING=1
fi
"step_${step//-/_}" "$@"
