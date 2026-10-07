#!/usr/bin/env bash
# Rolling reboot of the Bifrost k3s nodes. Prints the plan and exits unless
# --execute is given. A live run is refused outside Saturday/Sunday US Eastern
# unless --allow-weekday is set, which prints a warning and continues.
# Any failed step stops the run; later nodes are not touched.
#
# Order: general nodes (name order), then the sole control plane (ubt-k3s-01,
# its own step: the API drops for about 10s), then ubt-k3s-02 (PROD), then a
# CNPG switchover off the database primary, then ubt-k3s-04 last.
# gpu-server (192.168.10.60) is usually powered off and is not in the plan.
#
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

DRY_RUN=1
ALLOW_WEEKDAY=0
NODES_SPEC=""

usage() {
  cat <<'EOF'
Usage: rolling-reboot.sh [--dry-run] [--execute] [--allow-weekday]
                         [--nodes name:role[:ip],...]

  --dry-run         Print the plan and exit (default).
  --execute         Perform the plan. Refused on Mon-Fri US Eastern.
  --allow-weekday   With --execute, run outside the weekend and print a warning.
  --nodes           Override the node list. Roles: general, control-plane,
                    prod, data-primary. Optional third field is the SSH address.

Default nodes: ubt-k3s-05 and ubt-k3s-06 (general), ubt-k3s-01 (control-plane),
ubt-k3s-02 (prod), ubt-k3s-04 (data-primary).
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

# Default catalog. gpu-server is intentionally absent.
if [ -z "${NODES_SPEC// /}" ]; then
  NODES_SPEC="ubt-k3s-05:general:192.168.10.77 ubt-k3s-06:general:192.168.10.79 ubt-k3s-01:control-plane:192.168.10.73 ubt-k3s-02:prod:192.168.10.70 ubt-k3s-04:data-primary:192.168.10.75"
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
    general|control-plane|prod|data-primary) ;;
    *)
      echo "ERROR: unknown role '${role}' for ${name} (want general, control-plane, prod, data-primary)" >&2
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

lookup_field() {
  # lookup_field <name> <2=role|3=ip>
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
    prod) echo 3 ;;
    data-primary) echo 4 ;;
    *) echo 9 ;;
  esac
}

# rank name, so generals sort by name and the primary group is last.
ORDERED=""
ranked=""
for pair in $PAIRS; do
  n="${pair%%:*}"
  r="${pair#*:}"
  role="${r%%:*}"
  rank="$(role_rank "$role")"
  ranked="${ranked}${rank} ${n}"$'\n'
done
ORDERED="$(printf '%s' "$ranked" | sed '/^$/d' | sort | awk '{print $2}')"

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
  dow="$(eastern_dow)"
  [ "$dow" = "6" ] || [ "$dow" = "7" ]
}

primary_names() {
  for pair in $PAIRS; do
    n="${pair%%:*}"
    r="${pair#*:}"
    role="${r%%:*}"
    if [ "$role" = "data-primary" ]; then
      printf '%s ' "$n"
    fi
  done
}

print_steps() {
  node="$1"
  echo "  - cordon ${node}"
  echo "  - drain ${node} (respect PodDisruptionBudgets)"
  echo "  - reboot ${node}"
  echo "  - wait until ${node} is Ready"
  echo "  - uncordon ${node}"
  echo "  - verify workloads on ${node} are Ready"
}

print_plan() {
  day="$(eastern_day)"
  count="$(printf '%s\n' "$ORDERED" | sed '/^$/d' | wc -l | tr -d ' ')"
  order_line="$(printf '%s\n' "$ORDERED" | paste -sd ' ' -)"
  primaries="$(primary_names | sed 's/ *$//')"
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
  echo "order: ${order_line}"
  if [ -n "$primaries" ]; then
    echo "switchover-before: ${primaries}"
  else
    echo "switchover-before: none"
  fi
  echo
  i=0
  switched=0
  for node in $ORDERED; do
    i=$((i + 1))
    role="$(lookup_field "$node" role)"
    if [ "$role" = "data-primary" ] && [ "$switched" = "0" ]; then
      echo "switchover: CNPG promote a replica so ${primaries} is not the primary (cluster ${CNPG_CLUSTER}, namespace ${DATA_NAMESPACE}) before that node reboots"
      switched=1
    fi
    echo "node ${i}/${count} ${node} role=${role}"
    if [ "$role" = "control-plane" ]; then
      echo "  note: sole control plane; reboot interrupts the Kubernetes API for about 10s"
    fi
    print_steps "$node"
  done
}

require_live_window() {
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

kube() {
  kubectl "$@"
}

node_ssh() {
  ip="$1"
  shift
  ssh -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new \
    -i "$SSH_KEY" "${SSH_USER}@${ip}" "$@"
}

wait_ready_after_reboot() {
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

switchover_off() {
  # Move the CNPG primary off this node before it reboots. If it is already
  # elsewhere, do nothing. Failure here must not fall through to the reboot.
  node="$1"
  primary="$(kube get cluster "$CNPG_CLUSTER" -n "$DATA_NAMESPACE" -o jsonpath='{.status.currentPrimary}')"
  if [ -z "$primary" ]; then
    echo "ERROR: CNPG cluster ${CNPG_CLUSTER} has no currentPrimary in ${DATA_NAMESPACE}" >&2
    return 1
  fi
  primary_node="$(kube get pod "$primary" -n "$DATA_NAMESPACE" -o jsonpath='{.spec.nodeName}')"
  if [ "$primary_node" != "$node" ]; then
    echo "CNPG primary ${primary} is on ${primary_node}, not ${node}; switchover not required"
    return 0
  fi
  target="$(kube get pods -n "$DATA_NAMESPACE" -l "cnpg.io/cluster=${CNPG_CLUSTER},cnpg.io/instanceRole=replica" -o json \
    | python3 -c '
import json, sys
avoid = sys.argv[1]
data = json.load(sys.stdin)
for pod in data.get("items", []):
    if (pod.get("spec") or {}).get("nodeName") == avoid:
        continue
    print((pod.get("metadata") or {}).get("name", ""))
    break
' "$node")"
  if [ -z "$target" ]; then
    echo "ERROR: no CNPG replica scheduled off ${node}; refusing to reboot the primary node" >&2
    return 1
  fi
  echo "promoting ${target} so ${node} is not the CNPG primary"
  if [ -x "${HOME}/.local/bin/kubectl-cnpg" ]; then
    "${HOME}/.local/bin/kubectl-cnpg" promote -n "$DATA_NAMESPACE" "$CNPG_CLUSTER" "$target"
  else
    kube cnpg promote -n "$DATA_NAMESPACE" "$CNPG_CLUSTER" "$target"
  fi
  deadline=$(( $(date +%s) + READY_TIMEOUT_SECONDS ))
  while [ "$(date +%s)" -lt "$deadline" ]; do
    now="$(kube get cluster "$CNPG_CLUSTER" -n "$DATA_NAMESPACE" -o jsonpath='{.status.currentPrimary}' 2>/dev/null || true)"
    now_node=""
    if [ -n "$now" ]; then
      now_node="$(kube get pod "$now" -n "$DATA_NAMESPACE" -o jsonpath='{.spec.nodeName}' 2>/dev/null || true)"
    fi
    if [ -n "$now_node" ] && [ "$now_node" != "$node" ]; then
      echo "CNPG primary is ${now} on ${now_node}"
      return 0
    fi
    sleep "$READY_POLL_SECONDS"
  done
  echo "ERROR: CNPG primary still on ${node} after switchover" >&2
  return 1
}

run_node() {
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
  require_live_window
  export KUBECONFIG="${KUBECONFIG:-${PLATFORM_KUBECONFIG:-${HOME}/.kube/bifrost-k3s.yaml}}"
  switched=0
  for node in $ORDERED; do
    role="$(lookup_field "$node" role)"
    if [ "$role" = "data-primary" ] && [ "$switched" = "0" ]; then
      echo "==> CNPG switchover off ${node}"
      switchover_off "$node"
      switched=1
    fi
    run_node "$node" "$role"
  done
  echo "rolling-reboot: complete"
}

print_plan
if [ "$DRY_RUN" = "1" ]; then
  exit 0
fi
execute_plan
