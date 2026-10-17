#!/usr/bin/env bash
# agent-06-owner.sh — the Owner's steps, from his Mac, to take ubt-k3s-06 out
# of the cluster and make it the agent host (Owner 2026-10-17;
# agent-config/work/multi-agent/OWNER-STEPS-agent-host-06.md). It uses the
# admin kubeconfig and the node key, so only the Owner runs it.
#
#   bash agent-06-owner.sh <step>
#
#   check                 read only: what is on 06 and what leave would do
#   leave                 hold the release window; cordon; back up the
#                         event-radar volume; delete the five volumes on 06
#                         named below; restart the two zero-budget
#                         Deployments; drain
#   uninstall             uninstall k3s on 06 and reboot it (after leave)
#   delete-node           delete the node object (after uninstall)
#   copy                  scp this directory and the agentd binary to 06
#   prepare               run prepare-agent-06.sh on 06
#   codex-login prod|stg  log codex in as that agent user (device code)
#   vendor-creds          copy Claude's and Cursor's credentials from this Mac
#   git-token prod|stg    read a Gitea token (hidden) and install it on 06
#   host-check base|creds|running   run check-agent-06.sh on 06
#   secret prod|stg       put that agentd's platform token into its Secret
#   stop                  stop both agentd services (before prepare runs again)
#   start                 enable and start both agentd services
#   retire-mac            stop the agentd on this Mac
#   probe-protection      run probe-gitea-protection.sh on 06 as the STG agentd
#                         user against bifrost/primary-probe (Gitea-primary cut,
#                         step 1)
#
# Every step stops at its first error and exits non-zero. No step prints a
# credential. Each step but codex-login also keeps its output in
# ~/agent-work/agent-06-logs/, for the coordinator to read.
set -euo pipefail

NODE=ubt-k3s-06
NODE_UID=f8cd0884-6b5d-4006-abbc-e065c7f48a3c
ADDR=192.168.10.79
NODE_KEY=$HOME/.bifrost-owner/ssh/node
WORKSPACE=$HOME/Desktop/stocks
HERE=$(cd "$(dirname "$0")" && pwd -P)
BINARY=$HOME/agent-work/agentd-build/agentd-1a339e1-linux-amd64
STATE_DIR=$HOME/bifrost-backups/event-radar-input/2026-10-17_node06_pvc-6bf6eca6
BACKUP=$STATE_DIR/event-radar-input-pvc.tar.gz
EVENT_RADAR_DIR=pvc-6bf6eca6-5968-4874-ae93-22b8a2a23fab_research_event-radar-input-pvc
LOG_DIR=$HOME/agent-work/agent-06-logs
# The only volumes leave deletes (read 2026-10-17 01:20): "<namespace>
# <claim> <claim uid>"; the volume of each is pvc-<claim uid>. The event-radar
# claim (Owner 2026-10-17: back up, then delete) and the workspaces of four
# CI runs that had finished. One that is gone already is fine; any other
# volume bound to 06 stops leave before it deletes anything.
VOLUMES='research event-radar-input-pvc 6bf6eca6-5968-4874-ae93-22b8a2a23fab
cicd pvc-728cfe4d54 1a759b5b-64c3-4775-ab38-0fc6f6165882
cicd pvc-1eb38440a3 1bbcc303-db24-455e-abd7-e9a52ef4d828
cicd pvc-8935c75ca7 8fb63e9e-a222-4b7c-812f-19c4fa5767ef
cicd pvc-fb889204fe d794fb12-c015-4771-bb94-7dc59f7849df'
# `check` reads only, so it may run with another kubeconfig (AGENT06_KUBECONFIG).
export KUBECONFIG=${AGENT06_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}

die() {
  echo "agent-06-owner: $*" >&2
  exit 1
}
say() { echo "==> $*"; }
# Written for the macOS system bash (3.2) as well: no arrays under set -u.
TMPD=$(mktemp -d)
trap 'rm -rf "$TMPD"' EXIT

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
  kubectl get pipelineruns -n cicd -o json > "$TMPD/runs.json" || die "cannot list PipelineRuns"
  python3 -I -c '
import json, sys
for r in json.load(open(sys.argv[1]))["items"]:
    c = [c for c in (r.get("status") or {}).get("conditions") or [] if c.get("type") == "Succeeded"]
    if not c or c[0].get("status") not in ("True", "False"):
        print(r["metadata"]["name"])
' "$TMPD/runs.json"
}

# node06_volumes: every PersistentVolume bound to 06, one line each:
# "<volume> <namespace> <claim> <claim uid> <state> [why]". State is
#   delete   one of VOLUMES, checked: claim uid, volume name and both
#            directions of the binding match, local-path, bound to 06 alone
#   waiting  one of VOLUMES whose claim is deleted or being deleted (the same
#            uid, with a deletion timestamp) and whose volume the provisioner
#            has not removed yet: not to delete, not done
#   BAD      anything else
# Exit 0 when there is no BAD line, 3 when there is; a failed read stops the
# script.
node06_volumes() {
  kubectl get pv -o json > "$TMPD/pv.json" || die "cannot list PersistentVolumes"
  kubectl get pvc -A -o json > "$TMPD/pvc.json" || die "cannot list PersistentVolumeClaims"
  printf '%s\n' "$VOLUMES" > "$TMPD/allowed.txt"
  python3 -I -c '
import json, sys
node, d = sys.argv[1], sys.argv[2]
pvs, pvcs = json.load(open(d + "/pv.json")), json.load(open(d + "/pvc.json"))
allowed = {}
for line in open(d + "/allowed.txt"):
    if line.strip():
        ns, claim, uid = line.split()
        allowed[(ns, claim)] = uid
claims = {(c["metadata"]["namespace"], c["metadata"]["name"]): c for c in pvcs["items"]}
bad = 0
for pv in pvs["items"]:
    spec, meta = pv["spec"], pv["metadata"]
    terms = ((spec.get("nodeAffinity") or {}).get("required") or {}).get("nodeSelectorTerms") or []
    if node not in json.dumps(terms):
        continue
    name, ref = meta["name"], spec.get("claimRef") or {}
    ns, claim = ref.get("namespace", "-"), ref.get("name", "-")
    uid = allowed.get((ns, claim))
    pvc = claims.get((ns, claim))
    fixed = {
        "named": uid is not None,
        "claimref-uid": uid is not None and ref.get("uid") == uid,
        "volume-name": uid is not None and name == "pvc-" + uid,
        "local-path": (meta.get("annotations") or {}).get("pv.kubernetes.io/provisioned-by") == "rancher.io/local-path",
        "only-06": terms == [{"matchExpressions": [{"key": "kubernetes.io/hostname", "operator": "In", "values": [node]}]}],
    }
    failed = [k for k, v in fixed.items() if not v]
    going = pvc is not None and pvc["metadata"].get("uid") == uid and pvc["metadata"].get("deletionTimestamp")
    if not failed and (pvc is None or going):
        state = "waiting"
    elif not failed and pvc["metadata"].get("uid") == uid and pvc["spec"].get("volumeName") == name:
        state = "delete"
    else:
        if pvc is not None:
            failed.append("claim-binding")
        state = "BAD " + ",".join(failed)
        bad += 1
    print(name, ns, claim, uid or "-", state)
sys.exit(3 if bad else 0)
' "$NODE" "$TMPD"
}

# volumes_ok: node06_volumes, stopping the script unless every volume is one
# of VOLUMES. Prints the listing and keeps it in $TMPD/listing.txt.
volumes_ok() {
  local listing rc
  listing=$(node06_volumes) && rc=0 || rc=$?
  [ -z "$listing" ] || printf '%s\n' "$listing"
  [ "$rc" != 3 ] || die "a volume on $NODE is not one of the five named in this script; nothing was deleted"
  [ "$rc" = 0 ] || die "could not read the volumes on $NODE"
  if [ -n "$listing" ]; then printf '%s\n' "$listing" > "$TMPD/listing.txt"; else : > "$TMPD/listing.txt"; fi
}

node_is_ours() {
  local uid
  uid=$(kubectl get node "$NODE" -o jsonpath='{.metadata.uid}') || die "cannot read $NODE"
  [ "$uid" = "$NODE_UID" ] || die "$NODE is not the node this script was written for (uid differs)"
}

backup_ok() { # the backup is a whole gzip file holding the event-radar directory, and its checksum matches
  [ -s "$BACKUP" ] && [ -s "$BACKUP.sha256" ] || return 1
  (cd "$STATE_DIR" && shasum -a 256 -c "$BACKUP.sha256" >/dev/null 2>&1) || return 1
  gzip -t "$BACKUP" 2>/dev/null || return 1
  tar -tzf "$BACKUP" > "$TMPD/backup.check" 2>/dev/null || return 1
  grep -q "^$EVENT_RADAR_DIR/" "$TMPD/backup.check"
}

backup_volume() {
  mkdir -p "$STATE_DIR"
  if backup_ok; then
    say "backup already there: $BACKUP"
    return
  fi
  watched node_ssh "sudo test -d /var/lib/rancher/k3s/storage/$EVENT_RADAR_DIR && sudo tar -C /var/lib/rancher/k3s/storage -czf - $EVENT_RADAR_DIR" > "$BACKUP.part"
  gzip -t "$BACKUP.part" || die "the backup is not a whole gzip file"
  tar -tzf "$BACKUP.part" > "$TMPD/backup.list" || die "the backup cannot be listed"
  grep -q "^$EVENT_RADAR_DIR/" "$TMPD/backup.list" || die "the backup does not hold $EVENT_RADAR_DIR"
  mv "$BACKUP.part" "$BACKUP"
  (cd "$STATE_DIR" && shasum -a 256 "$(basename "$BACKUP")" > "$BACKUP.sha256") || die "could not write the backup's checksum"
  backup_ok || die "the backup does not check after it was written"
  local entries
  entries=$(wc -l < "$TMPD/backup.list" | tr -d ' ')
  say "backed up: $BACKUP ($entries entries)"
}

delete_volumes() {
  local pv ns claim uid state
  volumes_ok
  if [ ! -s "$TMPD/listing.txt" ]; then
    say "no volume left on $NODE"
    return
  fi
  if grep -q ' research event-radar-input-pvc ' "$TMPD/listing.txt"; then
    backup_ok || die "event-radar is not backed up"
  fi
  # Only the claims this listing has just checked, each deleted with its uid
  # as a precondition: if the claim by that name is another object by now,
  # the API server refuses (409) and the script stops.
  grep ' delete$' "$TMPD/listing.txt" > "$TMPD/to-delete.txt" || true
  while read -r pv ns claim uid state; do
    [ -n "$pv" ] || continue
    need_window
    printf '{"kind":"DeleteOptions","apiVersion":"v1","preconditions":{"uid":"%s"}}' "$uid" > "$TMPD/delete-options.json"
    kubectl delete --raw "/api/v1/namespaces/$ns/persistentvolumeclaims/$claim" -f "$TMPD/delete-options.json" > /dev/null ||
      die "could not delete $ns/$claim with uid $uid (another object by that name now, or the API refused); nothing more was deleted"
    say "deleted $ns/$claim (uid $uid)"
  done < "$TMPD/to-delete.txt"
}

# wait_volumes_gone: after the drain. A claim that finished pods still name
# stays in deletion (pvc-protection) until those pods are gone, and the
# drain removes them; then the provisioner removes each volume.
wait_volumes_gone() {
  local pod
  # The drain normally takes the finished pods too; any finished pod on the
  # node that still names one of the named claims is deleted here (its log
  # goes with it; the run's result stays on its PipelineRun).
  kubectl get pods -A --field-selector "spec.nodeName=$NODE" -o json > "$TMPD/pods.json" || die "cannot list the pods on $NODE"
  printf '%s\n' "$VOLUMES" > "$TMPD/allowed.txt"
  python3 -I -c '
import json, sys
named = {tuple(l.split()[:2]) for l in open(sys.argv[2]) if l.strip()}
for p in json.load(open(sys.argv[1]))["items"]:
    ns = p["metadata"]["namespace"]
    claims = {v["persistentVolumeClaim"]["claimName"] for v in p["spec"].get("volumes") or [] if v.get("persistentVolumeClaim")}
    if p["status"].get("phase") in ("Succeeded", "Failed") and any((ns, c) in named for c in claims):
        print(ns + "/" + p["metadata"]["name"])
' "$TMPD/pods.json" "$TMPD/allowed.txt" > "$TMPD/finished.txt"
  while read -r pod; do
    [ -n "$pod" ] || continue
    need_window
    kubectl -n "${pod%%/*}" delete pod "${pod#*/}" --wait=false > /dev/null || die "could not delete the finished pod $pod"
    say "deleted the finished pod $pod (it held a named claim)"
  done < "$TMPD/finished.txt"
  for _ in $(seq 1 30); do
    need_window
    volumes_ok > /dev/null
    if [ ! -s "$TMPD/listing.txt" ]; then
      say "all named volumes on $NODE are gone"
      return
    fi
    if grep -q ' delete$' "$TMPD/listing.txt"; then
      cat "$TMPD/listing.txt"
      die "a named claim on $NODE is there again after it was deleted"
    fi
    sleep 10
  done
  cat "$TMPD/listing.txt"
  die "volumes on $NODE are still there after 5 minutes"
}

pods_left_on_node() { # pods on 06 that are neither DaemonSet pods nor finished
  kubectl get pods -A --field-selector "spec.nodeName=$NODE" -o json > "$TMPD/pods.json" || die "cannot list the pods on $NODE"
  python3 -I -c '
import json, sys
for p in json.load(open(sys.argv[1]))["items"]:
    kinds = [o.get("kind") for o in p["metadata"].get("ownerReferences") or []]
    if "DaemonSet" in kinds or p["status"].get("phase") in ("Succeeded", "Failed"):
        continue
    print(p["metadata"]["namespace"] + "/" + p["metadata"]["name"])
' "$TMPD/pods.json"
}

# The release window, held for the whole of leave so that no release starts
# while 06 is being emptied. kill_tree stops the hold and every sleep under it
# (release.sh hold nests subshells; killing only the top one leaves the
# window open).
kill_tree() {
  local c
  for c in $(pgrep -P "$1" 2> /dev/null); do kill_tree "$c"; done
  kill "$1" 2> /dev/null || true
}
HOLD_PID=""
WHO=${BIFROST_RELEASE_WHO:-${USER}@$(hostname -s)}
# release_window: stop the hold and show that the window is closed; returns
# 1 when it is still open (it then closes by itself when its lease runs out).
release_window() {
  [ -n "$HOLD_PID" ] || return 0
  kill_tree "$HOLD_PID"
  wait "$HOLD_PID" 2> /dev/null || true
  HOLD_PID=""
  if "$WORKSPACE/bifrost-trade-infra/scripts/release/release.sh" window > /dev/null 2>&1; then
    say "release window closed"
  else
    echo "agent-06-owner: the release window is still open; it closes by itself within 5 minutes" >&2
    return 1
  fi
}
# window_ours: the hold is alive and the platform shows the window as ours
# (who, what) with more than a minute of lease left. Returns 1 otherwise.
window_ours() {
  local out rc=0
  [ -n "$HOLD_PID" ] && kill -0 "$HOLD_PID" 2> /dev/null || return 1
  out=$("$WORKSPACE/bifrost-trade-infra/scripts/release/release.sh" window 2>&1) || rc=$?
  [ "$rc" = 1 ] || return 1
  printf '%s\n' "$out" | python3 -I -c '
import datetime, re, sys
who, text = sys.argv[1], sys.stdin.read()
m = re.search(r"who=(\S+) what=(\S+) .*expires_at=(\S+)", text)
if not m or m.group(1) != who or m.group(2) != "ubt-k3s-06":
    sys.exit(1)
left = datetime.datetime.fromisoformat(m.group(3).replace("Z", "+00:00")) - datetime.datetime.now(datetime.timezone.utc)
sys.exit(0 if left.total_seconds() > 60 else 1)
' "$WHO"
}
need_window() { window_ours || die "the release window is no longer held for ubt-k3s-06; leave stops here ($NODE stays cordoned)"; }
# watched <command…>: run a long step only while the window is ours: checked
# before it starts, every 15 seconds while it runs (if lost, the step is
# stopped and leave with it), and once more after it ends.
watched() {
  need_window
  "$@" &
  local pid=$! rc=0
  while kill -0 "$pid" 2> /dev/null; do
    sleep 15
    kill -0 "$pid" 2> /dev/null || break
    if ! window_ours; then
      kill_tree "$pid"
      wait "$pid" 2> /dev/null || true
      die "the release window was lost while running: $*; it was stopped ($NODE stays cordoned)"
    fi
  done
  wait "$pid" || rc=$?
  [ "$rc" = 0 ] || die "failed (exit $rc): $*"
  need_window
}
hold_window() {
  "$WORKSPACE/bifrost-trade-infra/scripts/release/release.sh" hold --what ubt-k3s-06 > "$TMPD/hold.log" 2>&1 &
  HOLD_PID=$!
  for _ in $(seq 1 30); do
    if grep -q '^holding ConfigMap' "$TMPD/hold.log"; then
      say "release window held for ubt-k3s-06"
      return
    fi
    if ! kill -0 "$HOLD_PID" 2> /dev/null; then
      HOLD_PID=""
      cat "$TMPD/hold.log"
      die "could not take the release window (another release holds it, or the platform did not answer)"
    fi
    sleep 1
  done
  die "the release window was not taken within 30 seconds"
}

step_check() {
  say "release window"
  "$WORKSPACE/bifrost-trade-infra/scripts/release/release.sh" window || echo "(leave would wait: a release window is open)"
  say "PipelineRuns not finished"
  active_runs
  say "volumes on $NODE"
  local listing rc
  listing=$(node06_volumes) && rc=0 || rc=$?
  [ -z "$listing" ] || printf '%s\n' "$listing"
  case $rc in 0) ;; 3) echo "(leave would stop here: a volume above is not one of the five)" ;; *) die "could not read the volumes" ;; esac
  say "pods on $NODE (not DaemonSet, not finished)"
  pods_left_on_node
}

step_leave() {
  node_is_ours
  # This step runs in its own subshell (the pipeline into tee), so this trap
  # is its own: the window is released on every way out, and a window that
  # could not be shown closed fails the step.
  trap 'rc=$?; release_window || { [ "$rc" != 0 ] || rc=1; }; rm -rf "$TMPD"; exit $rc' EXIT
  hold_window
  need_window
  local active left
  active=$(active_runs)
  [ -z "$active" ] || die "PipelineRuns still running: $(echo "$active" | tr '\n' ' ')"
  say "cordon"
  kubectl cordon "$NODE"
  active=$(active_runs)
  [ -z "$active" ] || die "a PipelineRun started meanwhile ($(echo "$active" | tr '\n' ' ')); $NODE stays cordoned, run leave again when it has finished"
  say "check the volumes on $NODE before anything is deleted"
  volumes_ok
  say "back up the event-radar volume"
  if grep -q ' research event-radar-input-pvc ' "$TMPD/listing.txt"; then
    backup_volume
  else
    backup_ok || die "the event-radar volume is gone but its backup does not check"
    say "event-radar volume already deleted; its backup checks"
  fi
  need_window
  say "delete the named volumes on $NODE (the CI workspaces go once the drain has taken their finished pods)"
  delete_volumes
  need_window
  say "restart the two Deployments whose PodDisruptionBudget allows no eviction"
  kubectl -n plugin-market-data rollout restart deployment/polygon-worker-options deployment/polygon-worker-stocks
  watched kubectl -n plugin-market-data rollout status deployment/polygon-worker-options --timeout=15m
  watched kubectl -n plugin-market-data rollout status deployment/polygon-worker-stocks --timeout=15m
  need_window
  say "drain"
  watched kubectl drain "$NODE" --ignore-daemonsets --delete-emptydir-data --timeout=15m
  need_window
  left=$(pods_left_on_node)
  [ -z "$left" ] || die "pods still on $NODE: $(echo "$left" | tr '\n' ' ')"
  say "wait for the named volumes on $NODE to go"
  wait_volumes_gone
  printf '%s drained %s\n' "$NODE_UID" "$(date -u +%FT%TZ)" > "$STATE_DIR/leave-done"
  say "drained: only DaemonSet pods are left on $NODE; volumes gone; backup at $BACKUP"
  # Released here, not left to the trap: bash 3.2 runs an EXIT trap set in a
  # piped function only when it exits, not when it returns (10-17: the window
  # stayed held after a successful leave).
  release_window || die "leave is done, but the release window could not be shown closed"
}

uninstall_guard() { # the node is ours, leave finished, nothing is left on it
  node_is_ours
  [ -s "$STATE_DIR/leave-done" ] && [ "$(cut -d' ' -f1 "$STATE_DIR/leave-done")" = "$NODE_UID" ] || die "leave has not finished for this node: run leave first"
  [ "$(kubectl get node "$NODE" -o jsonpath='{.spec.unschedulable}')" = true ] || die "$NODE is not cordoned: run leave first"
  local left
  left=$(pods_left_on_node)
  [ -z "$left" ] || die "pods still on $NODE: run leave first"
  volumes_ok > /dev/null
  [ ! -s "$TMPD/listing.txt" ] || die "volumes still bound to $NODE: run leave first"
  backup_ok || die "the event-radar backup does not check"
}

step_uninstall() {
  [ -f "$HERE/k3s-on-06.sh" ] || die "missing $HERE/k3s-on-06.sh"
  uninstall_guard
  say "uninstall k3s on $NODE, show that it is gone, and reboot it in 5 seconds"
  node_ssh 'sudo bash -s -- uninstall' < "$HERE/k3s-on-06.sh" || die "the uninstall on $NODE did not finish; k3s may still be there (run uninstall again)"
  printf '%s uninstalled %s\n' "$NODE_UID" "$(date -u +%FT%TZ)" > "$STATE_DIR/uninstall-done"
}

step_delete_node() {
  local rc
  node_is_ours
  [ -s "$STATE_DIR/uninstall-done" ] && [ "$(cut -d' ' -f1 "$STATE_DIR/uninstall-done")" = "$NODE_UID" ] || die "uninstall has not finished for this node: run uninstall first"
  uninstall_guard
  say "check on $NODE itself that k3s is gone"
  [ -f "$HERE/k3s-on-06.sh" ] || die "missing $HERE/k3s-on-06.sh"
  rc=0
  node_ssh 'sudo bash -s -- gone' < "$HERE/k3s-on-06.sh" || rc=$?
  case $rc in
    0) ;;
    1) die "k3s is still on $NODE; nothing was deleted" ;;
    *) die "could not tell whether k3s is gone from $NODE (still rebooting? wait a minute and run this again); nothing was deleted" ;;
  esac
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
  node_ssh_tty "sudo -u $u -H env -i HOME=/home/$u USER=$u LOGNAME=$u PATH=/opt/bifrost/codex/bin:/home/$u/.local/bin:/usr/local/lib/nodejs/current/bin:/usr/bin:/bin bash -c 'cd ~ && codex login --device-auth'"
}

# normalize <in> <out> <kind>: one line, no surrounding newline, the shape of
# that kind of credential (install-secret.sh checks the same); never printed.
normalize() {
  python3 -I -c '
import re, sys
src, dst, kind = sys.argv[1:]
data = open(src, "rb").read()
if data.endswith(b"\n"):
    data = data[:-1]
if data.endswith(b"\r"):
    data = data[:-1]
shapes = {
    "agentd-git.token": rb"[0-9a-f]{40}",
    "claude-oauth.token": rb"sk-ant-[A-Za-z0-9_-]{20,500}",
    "cursor-api.key": rb"[\x21-\x7e]{20,500}",
}
if not re.fullmatch(shapes[kind], data):
    sys.exit("does not look like a " + kind)
open(dst, "wb").write(data)
' "$1" "$2" "$3"
}

# send_secret <user> <name> <file>: <file> holds the value, already checked.
# Its length and SHA-256 go with it (neither is secret), and the far end
# replaces the old value only when both match and the value has the right
# shape for its kind.
send_secret() {
  local len sum
  len=$(wc -c < "$3" | tr -d ' ')
  sum=$(shasum -a 256 "$3" | cut -d' ' -f1)
  node_ssh "sudo bash ~/agent-host/install-secret.sh $1 $2 $len $sum" < "$3"
}

step_vendor_creds() {
  local f src
  sudo -v
  for f in claude-oauth.token cursor-api.key; do
    src=~bifrost-agentd/.config/bifrost/$f # the Mac's agentd user's home
    # Read whole first: a read that fails part way sends nothing.
    sudo cat "$src" > "$TMPD/$f.raw" || die "could not read $src on this Mac"
    normalize "$TMPD/$f.raw" "$TMPD/$f" "$f" || die "$src on this Mac does not look like a $f; nothing was sent"
    send_secret bifrost-agentd "$f" "$TMPD/$f"
    rm -f "$TMPD/$f.raw" "$TMPD/$f"
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
  printf '%s' "$tok" > "$TMPD/git.raw"
  unset tok
  normalize "$TMPD/git.raw" "$TMPD/git" agentd-git.token || die "that is not a Gitea token (40 hex characters); nothing was sent"
  send_secret "$u" agentd-git.token "$TMPD/git"
  rm -f "$TMPD/git.raw" "$TMPD/git"
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

step_stop() {
  node_ssh 'sudo systemctl stop bifrost-agentd.service bifrost-agentd-stg.service && ! systemctl is-active --quiet bifrost-agentd.service && ! systemctl is-active --quiet bifrost-agentd-stg.service && echo "both agentd stopped"'
}

step_start() {
  node_ssh 'sudo systemctl enable --now bifrost-agentd.service bifrost-agentd-stg.service && sleep 20 && sudo bash ~/agent-host/check-agent-06.sh running'
}

step_retire_mac() {
  local rc=0
  # disable first: bootout alone stops it until the next boot, when launchd
  # would load /Library/LaunchDaemons/com.bifrost.agentd.plist again.
  sudo launchctl disable system/com.bifrost.agentd
  sudo launchctl bootout system/com.bifrost.agentd || true
  for _ in $(seq 1 60); do
    rc=0
    sudo launchctl print system/com.bifrost.agentd > /dev/null 2>&1 || rc=$?
    if [ "$rc" = 113 ]; then
      say "the agentd on this Mac is stopped"
      return
    fi
    sleep 1
  done
  die "launchd still has com.bifrost.agentd (launchctl print exit $rc)"
}

# The probe reads that user's own Gitea token on 06 and prints none.
step_probe_protection() {
  node_ssh 'sudo -u bifrost-agentd-stg -H bash -s' < "$HERE/probe-gitea-protection.sh"
}

# Sourced (by a test), stop here: only the functions are wanted.
[ "${BASH_SOURCE[0]}" = "$0" ] || return 0

step=${1:-}
if [ -z "$step" ]; then
  sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
shift
case "$step" in
  check | leave | uninstall | delete-node | copy | prepare | codex-login | vendor-creds | git-token | host-check | secret | stop | start | retire-mac | probe-protection) ;;
  *) die "unknown step: $step" ;;
esac
fn=step_$(echo "$step" | tr - _)
if [ "$step" = codex-login ]; then
  "$fn" "$@"
  exit
fi
# The step runs in a pipeline into tee, with errexit on, so it stops at its
# first error; the script waits for tee, and a log that could not be written
# fails the step as well (pipefail). The exit status goes into the log.
mkdir -p "$LOG_DIR"
chmod 700 "$LOG_DIR"
LOG=$LOG_DIR/$step${1:+-$1}-$(date +%Y%m%dT%H%M%S)-$$.txt
trap 'rc=$?; echo "exit=$rc" >> "$LOG" 2> /dev/null; rm -rf "$TMPD"; exit $rc' EXIT
"$fn" "$@" 2>&1 | tee "$LOG"
echo "(log: $LOG)"
