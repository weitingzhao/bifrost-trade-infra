#!/usr/bin/env bash
# Rolling reboot of the Bifrost k3s nodes. Prints the plan and exits unless
# --execute is given. A live run is refused outside Saturday/Sunday US Eastern
# unless --allow-weekday is set, which prints a warning and continues.
# Any failed step stops the run; later nodes are not touched.
#
# Order is not taken from the data-primary label. That label is only a
# preference. At plan time, and again before each node, the script reads the
# CNPG primary from .status.currentPrimary, then that pod's spec.nodeName.
# General nodes (name order), then the sole control plane (ubt-k3s-01; the API
# drops for about 10s), then the other non-primary nodes. The node that hosts
# the current primary is last.
#
# Before that node's turn, promote a Ready replica that is already streaming
# and caught up on a node this run has rebooted. Promotion is `kubectl cnpg
# promote` (CNPG operator 1.27 sets status.targetPrimary). If the primary moves
# while the run is in progress, the remaining order is computed again. If only
# one instance remains, or no replica on an already-rebooted node is caught up,
# the run stops and does not reboot the primary node.
#
# gpu-server (192.168.10.60) is usually powered off and is not in the plan.
# This script does not change apt. Unattended-upgrade config is an Owner
# action, separate from a weekend reboot.
#
# Bash 3.2 compatible (macOS /bin/bash).
set -euo pipefail

SSH_KEY="${BIFROST_SSH_KEY:-${HOME}/.ssh/bifrost_deploy}"
SSH_USER="${BIFROST_SSH_USER:-vision}"
DATA_NAMESPACE="${DATA_NAMESPACE:-data}"
CNPG_CLUSTER="${CNPG_CLUSTER:-bifrost-postgres}"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-600}"
READY_POLL_SECONDS="${READY_POLL_SECONDS:-5}"
DRAIN_TIMEOUT="${DRAIN_TIMEOUT:-15m}"
# A replica counts as caught up when replay_lag is at most this many seconds.
# PostgreSQL reports NULL lag when there is nothing left to replay; that is 0.
REPLICA_LAG_MAX_SECONDS="${REPLICA_LAG_MAX_SECONDS:-1}"

DRY_RUN=1
ALLOW_WEEKDAY=0
NODES_SPEC=""

usage() {
  cat <<'EOF'
Usage: rolling-reboot.sh [--dry-run] [--execute] [--allow-weekday]
                         [--nodes name:role[:ip],...]

  --dry-run         Print the plan and exit (default). Reads the CNPG primary.
  --execute         Perform the plan. Refused on Mon-Fri US Eastern.
  --allow-weekday   With --execute, run outside the weekend and print a warning.
  --nodes           Override the node list. Roles: general, control-plane,
                    prod, data. Optional third field is the SSH address.
                    The current primary is read from CNPG, not from the role.

Default nodes: ubt-k3s-05 and ubt-k3s-06 (general), ubt-k3s-01 (control-plane),
ubt-k3s-02 (prod), ubt-k3s-04 (data).
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --execute) DRY_RUN=0 ;;
    --allow-weekday) ALLOW_WEEKDAY=1 ;;
    --nodes)
      shift
      [ $# -gt 0 ] || { echo "ERROR: --nodes needs a value" >&2; exit 2; }
      NODES_SPEC="${NODES_SPEC} ${1}"
      ;;
    --nodes=*)
      NODES_SPEC="${NODES_SPEC} ${1#--nodes=}"
      ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

# Default catalog. gpu-server is intentionally absent. "data" means the node
# hosts a database instance; it does not mean it is the current primary.
if [ -z "${NODES_SPEC// /}" ]; then
  NODES_SPEC="ubt-k3s-05:general:192.168.10.77 ubt-k3s-06:general:192.168.10.79 ubt-k3s-01:control-plane:192.168.10.73 ubt-k3s-02:prod:192.168.10.70 ubt-k3s-04:data:192.168.10.75"
fi

# Normalized pairs: "name:role:ip" (ip may be empty).
PAIRS=""
for raw in $(printf '%s' "$NODES_SPEC" | tr ',' ' '); do
  [ -n "$raw" ] || continue
  name="${raw%%:*}"
  rest="${raw#*:}"
  if [ "$name" = "$raw" ] || [ -z "$name" ] || [ -z "$rest" ]; then
    echo "ERROR: node spec must be name:role[:ip], got: ${raw}" >&2
    exit 2
  fi
  role="${rest%%:*}"
  if [ "$role" = "$rest" ]; then
    ip=""
  else
    ip="${rest#*:}"
  fi
  case "$role" in
    general|control-plane|prod|data) ;;
    *)
      echo "ERROR: unknown role '${role}' for ${name} (want general, control-plane, prod, data)" >&2
      exit 2
      ;;
  esac
  case " ${PAIRS} " in
    *" ${name}:"*)
      echo "ERROR: duplicate node ${name}" >&2
      exit 2
      ;;
  esac
  PAIRS="${PAIRS} ${name}:${role}:${ip}"
done
PAIRS="${PAIRS# }"
if [ -z "$PAIRS" ]; then
  echo "ERROR: empty node list" >&2
  exit 2
fi

ALL_NAMES=""
for pair in $PAIRS; do
  ALL_NAMES="${ALL_NAMES} ${pair%%:*}"
done
ALL_NAMES="${ALL_NAMES# }"

lookup_field() {
  # lookup_field <name> <role|ip>
  local want which n r role ip pair
  want="$1"
  which="$2"
  for pair in $PAIRS; do
    n="${pair%%:*}"
    if [ "$n" = "$want" ]; then
      r="${pair#*:}"
      role="${r%%:*}"
      ip="${r#*:}"
      if [ "$which" = "role" ]; then
        printf '%s\n' "$role"
      else
        if [ -n "$ip" ] && [ "$ip" != "$role" ]; then
          printf '%s\n' "$ip"
        else
          case "$n" in
            ubt-k3s-01) printf '%s\n' "192.168.10.73" ;;
            ubt-k3s-02) printf '%s\n' "192.168.10.70" ;;
            ubt-k3s-04) printf '%s\n' "192.168.10.75" ;;
            ubt-k3s-05) printf '%s\n' "192.168.10.77" ;;
            ubt-k3s-06) printf '%s\n' "192.168.10.79" ;;
            *) printf '\n' ;;
          esac
        fi
      fi
      return 0
    fi
  done
  return 1
}

role_rank() {
  case "$1" in
    general) echo 1 ;;
    control-plane) echo 2 ;;
    prod|data) echo 3 ;;
    *) echo 9 ;;
  esac
}

# Names on stdout, primary last when it is one of them. When the primary is
# absent (already rebooted, or failed over onto a finished node), the names
# stay in base order.
order_names() {
  local primary ranked found n role rank ordered out
  primary="$1"
  shift
  ranked=""
  found=0
  for n in "$@"; do
    [ -n "$n" ] || continue
    if [ "$n" = "$primary" ]; then
      found=1
    fi
    role="$(lookup_field "$n" role)"
    rank="$(role_rank "$role")"
    ranked="${ranked}${rank} ${n}"$'\n'
  done
  ordered="$(printf '%s' "$ranked" | sed '/^$/d' | LC_ALL=C sort | awk '{print $2}')"
  out=""
  for n in $ordered; do
    if [ "$found" = "1" ] && [ "$n" = "$primary" ]; then
      continue
    fi
    out="${out} ${n}"
  done
  if [ "$found" = "1" ]; then
    out="${out} ${primary}"
  fi
  printf '%s\n' "${out# }"
}

remove_name() {
  local drop out n
  drop="$1"
  shift
  out=""
  for n in "$@"; do
    [ "$n" = "$drop" ] && continue
    [ -n "$n" ] || continue
    out="${out} ${n}"
  done
  printf '%s\n' "${out# }"
}

eastern_dow() {
  if [ -n "${ROLLING_REBOOT_DOW:-}" ]; then
    case "$ROLLING_REBOOT_DOW" in
      1|2|3|4|5|6|7) printf '%s\n' "$ROLLING_REBOOT_DOW" ;;
      *)
        echo "ERROR: ROLLING_REBOOT_DOW must be 1-7" >&2
        exit 2
        ;;
    esac
    return
  fi
  TZ=America/New_York date +%u
}

eastern_day() {
  if [ -n "${ROLLING_REBOOT_DOW:-}" ]; then
    case "$ROLLING_REBOOT_DOW" in
      1) echo Monday ;;
      2) echo Tuesday ;;
      3) echo Wednesday ;;
      4) echo Thursday ;;
      5) echo Friday ;;
      6) echo Saturday ;;
      7) echo Sunday ;;
    esac
    return
  fi
  TZ=America/New_York date +%A
}

is_weekend() {
  local dow
  dow="$(eastern_dow)"
  [ "$dow" = "6" ] || [ "$dow" = "7" ]
}

kube() {
  kubectl "$@"
}

cluster_field() {
  local jp val
  jp="$1"
  val="$(kube get cluster "$CNPG_CLUSTER" -n "$DATA_NAMESPACE" -o "jsonpath=${jp}" 2>/dev/null | tr -d '\n\r' || true)"
  printf '%s' "$val" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
}

valid_k8s_name() {
  case "$1" in
    ""|*[!A-Za-z0-9._-]*) return 1 ;;
    *) return 0 ;;
  esac
}

current_primary_pod() {
  local pod
  pod="$(cluster_field '{.status.currentPrimary}')"
  if ! valid_k8s_name "$pod"; then
    echo "ERROR: CNPG cluster ${CNPG_CLUSTER} has no currentPrimary in ${DATA_NAMESPACE}" >&2
    return 1
  fi
  printf '%s\n' "$pod"
}

resolve_primary_node() {
  local pod node
  pod="$(current_primary_pod)" || return 1
  node="$(kube get pod "$pod" -n "$DATA_NAMESPACE" -o jsonpath='{.spec.nodeName}' 2>/dev/null | tr -d '\n\r' || true)"
  node="$(printf '%s' "$node" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  if [ -z "$node" ]; then
    echo "ERROR: CNPG primary pod ${pod} has no spec.nodeName" >&2
    return 1
  fi
  printf '%s\n' "$node"
}

require_primary_in_catalog() {
  local node
  node="$1"
  case " ${ALL_NAMES} " in
    *" ${node} "*) return 0 ;;
  esac
  echo "ERROR: CNPG primary is on ${node}, which is not in this reboot list" >&2
  return 1
}

lag_within_limit() {
  max_lag="$1"
  python3 -c '
import sys
max_lag = float(sys.argv[1])
rows = [ln.strip() for ln in sys.stdin.read().splitlines() if ln.strip()]
if not rows:
    sys.exit(1)
for line in rows:
    state, sep, lag = line.partition("|")
    try:
        lag_s = float(lag)
    except ValueError:
        sys.exit(1)
    if (not sep) or state != "streaming" or lag_s > max_lag:
        sys.exit(1)
' "$max_lag"
}

replica_is_caught_up() {
  local app primary_pod sql line
  app="$1"
  valid_k8s_name "$app" || return 1
  primary_pod="$(current_primary_pod)" || return 1
  sql="SELECT COALESCE(state, ''), COALESCE(EXTRACT(EPOCH FROM replay_lag), 0) FROM pg_stat_replication WHERE application_name = '${app}'"
  line="$(kube exec -n "$DATA_NAMESPACE" -c postgres "$primary_pod" -- psql -q -w -U postgres -d postgres -v ON_ERROR_STOP=1 -tA -c "$sql" 2>/dev/null || true)"
  printf '%s\n' "$line" | lag_within_limit "$REPLICA_LAG_MAX_SECONDS"
}

replicas_are_caught_up() {
  local primary_pod sql text
  primary_pod="$(current_primary_pod)" || return 1
  sql="SELECT COALESCE(state, ''), COALESCE(EXTRACT(EPOCH FROM replay_lag), 0) FROM pg_stat_replication ORDER BY application_name"
  text="$(kube exec -n "$DATA_NAMESPACE" -c postgres "$primary_pod" -- psql -q -w -U postgres -d postgres -v ON_ERROR_STOP=1 -tA -c "$sql" 2>/dev/null || true)"
  printf '%s\n' "$text" | lag_within_limit "$REPLICA_LAG_MAX_SECONDS"
}

replicas_on_done_nodes() {
  local done_nodes
  done_nodes="$1"
  kube get pods -n "$DATA_NAMESPACE" -l "cnpg.io/cluster=${CNPG_CLUSTER}" -o json \
    | python3 -c '
import json, sys
done = set(sys.argv[1].split())
data = json.load(sys.stdin)
rows = []
for pod in data.get("items") or []:
    meta = pod.get("metadata") or {}
    labels = meta.get("labels") or {}
    if labels.get("cnpg.io/instanceRole") != "replica":
        continue
    name = meta.get("name") or ""
    node = (pod.get("spec") or {}).get("nodeName") or ""
    conds = (pod.get("status") or {}).get("conditions") or []
    ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conds)
    if name and node and ready and node in done:
        rows.append("%s %s" % (name, node))
for row in sorted(rows):
    print(row)
' "$done_nodes"
}

# Wait until one Ready replica on an already-rebooted node is streaming and
# caught up. Prints "pod node" on stdout. Times out without promoting.
pick_caught_up_replica() {
  local node done_nodes saw_candidate deadline candidates rest row pod rnode
  node="$1"
  done_nodes="$2"
  saw_candidate=0
  deadline=$(( $(date +%s) + READY_TIMEOUT_SECONDS ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    candidates="$(replicas_on_done_nodes "$done_nodes" || true)"
    if [ -n "$candidates" ]; then
      saw_candidate=1
      rest="$candidates"
      while [ -n "$rest" ]; do
        row="${rest%%$'\n'*}"
        if [ "$rest" = "$row" ]; then
          rest=""
        else
          rest="${rest#*$'\n'}"
        fi
        [ -n "$row" ] || continue
        pod="${row%% *}"
        rnode="${row#* }"
        if replica_is_caught_up "$pod"; then
          printf '%s %s\n' "$pod" "$rnode"
          return 0
        fi
      done
    fi
    sleep "$READY_POLL_SECONDS"
  done
  if [ "$saw_candidate" = "1" ]; then
    echo "ERROR: CNPG replica on an already-rebooted node is not caught up; refusing to reboot primary node ${node}" >&2
  else
    echo "ERROR: no Ready CNPG replica on an already-rebooted node; refusing to reboot primary node ${node}" >&2
  fi
  return 1
}

wait_switchover() {
  local target target_node deadline cur tgt phase inst ready node
  target="$1"
  target_node="$2"
  deadline=$(( $(date +%s) + READY_TIMEOUT_SECONDS ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    cur="$(cluster_field '{.status.currentPrimary}')"
    tgt="$(cluster_field '{.status.targetPrimary}')"
    phase="$(cluster_field '{.status.phase}')"
    inst="$(cluster_field '{.status.instances}')"
    ready="$(cluster_field '{.status.readyInstances}')"
    node="$(kube get pod "$cur" -n "$DATA_NAMESPACE" -o jsonpath='{.spec.nodeName}' 2>/dev/null | tr -d '\n\r' || true)"
    if [ "$cur" = "$target" ] && [ "$tgt" = "$target" ] && [ "$node" = "$target_node" ] \
      && [ "$phase" = "Cluster in healthy state" ] && [ "${inst:-0}" -ge 2 ] && [ "${ready:-0}" = "${inst:-0}" ]; then
      if replicas_are_caught_up; then
        echo "CNPG primary is ${cur} on ${node}; replicas caught up"
        return 0
      fi
    fi
    sleep "$READY_POLL_SECONDS"
  done
  return 1
}

switchover_off_primary() {
  local node done_nodes inst ready picked target target_node
  node="$1"
  done_nodes="$2"
  echo "switchover-before: ${node}"
  inst="$(cluster_field '{.status.instances}')"
  ready="$(cluster_field '{.status.readyInstances}')"
  if [ "${inst:-0}" -lt 2 ]; then
    echo "ERROR: only ${inst:-0} CNPG instance remains; refusing to reboot primary node ${node}" >&2
    return 1
  fi
  if [ "${ready:-0}" -lt 2 ]; then
    echo "ERROR: CNPG readyInstances=${ready:-0} of ${inst}; refusing to reboot primary node ${node}" >&2
    return 1
  fi
  picked="$(pick_caught_up_replica "$node" "$done_nodes")" || return 1
  target="${picked%% *}"
  target_node="${picked#* }"
  if [ -z "$target" ] || [ "$target" = "$picked" ]; then
    echo "ERROR: internal: bad switchover target '${picked}'" >&2
    return 1
  fi
  echo "promoting ${target} on ${target_node} so ${node} is not the CNPG primary"
  if ! kube cnpg promote -n "$DATA_NAMESPACE" "$CNPG_CLUSTER" "$target"; then
    echo "ERROR: kubectl cnpg promote ${target} failed; refusing to reboot primary node ${node}" >&2
    return 1
  fi
  if ! wait_switchover "$target" "$target_node"; then
    echo "ERROR: switchover to ${target} on ${target_node} did not finish with replicas caught up; refusing to reboot primary node ${node}" >&2
    return 1
  fi
  return 0
}

print_steps() {
  local node
  node="$1"
  echo "  - cordon ${node}"
  echo "  - drain ${node} (respect PodDisruptionBudgets)"
  echo "  - reboot ${node}"
  echo "  - wait until ${node} is Ready"
  echo "  - uncordon ${node}"
  echo "  - verify workloads on ${node} are Ready"
}

print_plan() {
  local day count _n i node role
  day="$(eastern_day)"
  count=0
  for _n in $ORDERED; do
    count=$((count + 1))
  done
  if [ "$DRY_RUN" = "1" ]; then
    echo "rolling-reboot: dry-run"
  else
    echo "rolling-reboot: execute"
  fi
  if is_weekend; then
    echo "live-window: open (${day}, US/Eastern)"
  else
    echo "live-window: closed (${day}, US/Eastern). A live run is refused outside Saturday and Sunday. Override: --allow-weekday (prints a warning)."
  fi
  echo "failure-policy: stop at the first failed step; do not continue to the next node"
  echo "skipped: gpu-server (192.168.10.60) is usually powered off and is not in this plan"
  echo "order: ${ORDERED}"
  echo "primary-pod: ${primary_pod}"
  echo "primary-node: ${primary_node}"
  echo "switchover-before: ${primary_node}"
  echo
  i=0
  for node in $ORDERED; do
    i=$((i + 1))
    role="$(lookup_field "$node" role)"
    if [ "$node" = "$primary_node" ]; then
      echo "switchover: before ${node}, kubectl cnpg promote a Ready replica that is streaming and caught up (replay_lag <= ${REPLICA_LAG_MAX_SECONDS}s) on a node this run has already rebooted (cluster ${CNPG_CLUSTER}, namespace ${DATA_NAMESPACE}); stop if only one instance remains or no replica is caught up"
    fi
    echo "node ${i}/${count} ${node} role=${role}"
    if [ "$role" = "control-plane" ]; then
      echo "  note: sole control plane; reboot interrupts the Kubernetes API for about 10s"
    fi
    print_steps "$node"
  done
}

require_live_window() {
  local day
  if is_weekend; then
    return 0
  fi
  day="$(eastern_day)"
  if [ "$ALLOW_WEEKDAY" = "1" ]; then
    echo "WARNING: --allow-weekday set; rolling reboot is running outside the weekend window (${day}, US/Eastern)." >&2
    return 0
  fi
  echo "REFUSED: rolling reboot runs only on Saturday and Sunday US Eastern (today is ${day}). Pass --allow-weekday to override; that prints a warning and continues." >&2
  exit 1
}

node_ssh() {
  local ip
  ip="$1"
  shift
  ssh -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new \
    -i "$SSH_KEY" "${SSH_USER}@${ip}" "$@"
}

wait_ready_after_reboot() {
  local node deadline saw_down status
  node="$1"
  # A stale Ready from before the reboot does not count. Wait until the node
  # has been observed not Ready (or the API is unreachable), then Ready again.
  deadline=$(( $(date +%s) + READY_TIMEOUT_SECONDS ))
  saw_down=0
  while [ "$(date +%s)" -lt "$deadline" ]; do
    status="$(kube get node "$node" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || true)"
    if [ "$status" != "True" ]; then
      saw_down=1
    elif [ "$saw_down" = "1" ]; then
      echo "node ${node} is Ready"
      return 0
    fi
    sleep "$READY_POLL_SECONDS"
  done
  echo "ERROR: timed out waiting for ${node} to leave Ready and come back Ready" >&2
  return 1
}

verify_workloads() {
  local node
  node="$1"
  kube get pods -A --field-selector "spec.nodeName=${node}" -o json | python3 -c '
import json, sys
node = sys.argv[1]
data = json.load(sys.stdin)
bad = []
seen = 0
for pod in data.get("items", []):
    seen += 1
    phase = (pod.get("status") or {}).get("phase", "")
    if phase in ("Succeeded",):
        continue
    conds = (pod.get("status") or {}).get("conditions") or []
    ready = any(c.get("type") == "Ready" and c.get("status") == "True" for c in conds)
    if not ready:
        meta = pod.get("metadata") or {}
        bad.append("%s/%s phase=%s" % (meta.get("namespace"), meta.get("name"), phase))
if bad:
    sys.stderr.write("workloads not recovered on %s:\n%s\n" % (node, "\n".join(bad)))
    sys.exit(1)
print("workloads recovered on %s (%d pods)" % (node, seen))
' "$node"
}

run_node() {
  local node role ip rc
  node="$1"
  role="$2"
  ip="$(lookup_field "$node" ip)"
  if [ -z "$ip" ]; then
    echo "ERROR: no SSH address for ${node}; refusing to cordon it" >&2
    return 1
  fi
  if [ "$role" = "control-plane" ]; then
    echo "note: ${node} is the sole control plane; reboot interrupts the Kubernetes API for about 10s"
  fi
  echo "==> cordon ${node}"
  kube cordon "$node"
  echo "==> drain ${node}"
  # Default eviction honors PodDisruptionBudgets. Do not pass --force or
  # --disable-eviction. DaemonSets stay; a drain that cannot honor a PDB fails
  # and stops the whole run.
  kube drain "$node" \
    --ignore-daemonsets \
    --delete-emptydir-data \
    --grace-period=120 \
    --timeout="$DRAIN_TIMEOUT"
  echo "==> reboot ${node} (${ip})"
  set +e
  node_ssh "$ip" "sudo -n systemctl reboot"
  rc=$?
  set -e
  if [ "$rc" -ne 0 ] && [ "$rc" -ne 255 ]; then
    echo "ERROR: reboot ssh to ${node} failed (exit ${rc})" >&2
    return 1
  fi
  echo "==> wait Ready ${node}"
  wait_ready_after_reboot "$node"
  echo "==> uncordon ${node}"
  kube uncordon "$node"
  echo "==> verify workloads ${node}"
  verify_workloads "$node"
}

execute_plan() {
  local remaining done_nodes node role
  require_live_window
  remaining="$ALL_NAMES"
  done_nodes=""
  while [ -n "${remaining// /}" ]; do
    primary_node="$(resolve_primary_node)" || exit 1
    require_primary_in_catalog "$primary_node" || exit 1
    remaining="$(order_names "$primary_node" $remaining)" || exit 1
    echo "remaining-order: ${remaining}"
    node="${remaining%% *}"
    if [ "$node" = "$primary_node" ]; then
      switchover_off_primary "$node" "$done_nodes" || exit 1
      primary_node="$(resolve_primary_node)" || exit 1
      if [ "$primary_node" = "$node" ]; then
        echo "ERROR: CNPG primary is still on ${node} after switchover; refusing to reboot it" >&2
        exit 1
      fi
      require_primary_in_catalog "$primary_node" || exit 1
      remaining="$(order_names "$primary_node" $remaining)" || exit 1
      echo "remaining-order: ${remaining}"
      node="${remaining%% *}"
      if [ "$node" = "$primary_node" ]; then
        echo "ERROR: CNPG primary moved to ${primary_node}, which is still waiting to reboot; refusing to continue" >&2
        exit 1
      fi
    fi
    role="$(lookup_field "$node" role)"
    run_node "$node" "$role"
    done_nodes="${done_nodes} ${node}"
    remaining="$(remove_name "$node" $remaining)" || exit 1
  done
  echo "rolling-reboot: complete"
}

export KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}}"
if ! command -v kubectl >/dev/null 2>&1; then
  echo "ERROR: kubectl not found in PATH" >&2
  exit 1
fi

primary_pod="$(current_primary_pod)" || exit 1
primary_node="$(resolve_primary_node)" || exit 1
require_primary_in_catalog "$primary_node" || exit 1
ORDERED="$(order_names "$primary_node" $ALL_NAMES)" || exit 1

print_plan
if [ "$DRY_RUN" = "1" ]; then
  exit 0
fi
execute_plan
