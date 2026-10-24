#!/usr/bin/env bash
# host-exporters.sh — W-68 B4 ①: put the exporters on the four hosts outside the cluster,
# and the scrape configs, rules and dashboard that read them into the cluster. Run from
# the Mac Pro. agent-config/work/multi-agent/OWNER-STEPS-w68-b4-2026-10-24.md says who
# runs which step and what each prints.
#
#   bash host-exporters.sh mini 50      Mac mini .50 (mini 52 for .52), as vision, no sudo,
#                                       ~/.ssh/id_ed25519 (no passphrase): the coordinator
#                                       can run this one if the Owner says so
#   bash host-exporters.sh agent-06     ubt-k3s-06: the Owner's node key (passphrase asked
#                                       once), passwordless sudo there
#   bash host-exporters.sh nas          the NAS as k8s_admin: sudo asks for its password once
#   bash host-exporters.sh cluster      the admin kubeconfig: server dry-run of the four
#                                       monitoring files, then apply them
#   bash host-exporters.sh check        read only, anyone: every endpoint answers with its
#                                       key metric
#
# Every step takes its files from origin/main (git fetch, then git archive / git show),
# never from the working tree, so what runs is what was merged. Files reach a host in the
# same ssh session that runs them, into a fresh mktemp directory (root's own on 06 and
# the NAS), so nothing waits in a writable place between copy and run. Each step stops at
# its first error with a non-zero exit, and none prints a credential.
set -euo pipefail

# The infra checkout whose origin/main is used. The Owner's commands run a copy of this
# script taken with `git show origin/main:…` (outside any checkout); it then falls back
# to the workspace checkout.
REPO=${HOST_EXPORTERS_REPO:-}
if [[ -z $REPO ]]; then
  here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  REPO=$(git -C "$here" rev-parse --show-toplevel 2>/dev/null) || REPO=$HOME/Desktop/stocks/bifrost-trade-infra
fi
[[ -d $REPO/.git || -f $REPO/.git ]] || { echo "host-exporters: no git checkout at $REPO" >&2; exit 1; }
REF=${HOST_EXPORTERS_REF:-origin/main}
NODE_KEY=${HOST_EXPORTERS_NODE_KEY:-$HOME/.bifrost-owner/ssh/node}
ADMIN_KUBECONFIG=${HOST_EXPORTERS_KUBECONFIG:-$HOME/.bifrost-owner/kube/admin.yaml}
LAN_KEY=${HOST_EXPORTERS_LAN_KEY:-$HOME/.ssh/id_ed25519}
MONITORING=(bifrost-hosts-external.yaml bifrost-blackbox.yaml bifrost-host-rules.yaml grafana-dashboard-hosts.yaml)
ENDPOINTS=(
  "agent-06 192.168.10.79:9100 node_exporter_build_info"
  "agent-06 192.168.10.79:9633 smartctl_device_smart_status"
  "nas 192.168.10.20:9100 node_md_disks"
  "nas 192.168.10.20:9633 smartctl_device_smart_status"
  "mini-50 192.168.10.50:9100 node_exporter_build_info"
  "mini-52 192.168.10.52:9100 node_exporter_build_info"
)

die() { echo "host-exporters: $*" >&2; exit 1; }

usage() {
  sed -n '7,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
  exit 2
}

# The ref must exist and hold every path this step uses.
need_ref() {
  git -C "$REPO" fetch -q origin || die "git fetch origin failed"
  git -C "$REPO" rev-parse -q --verify "${REF}^{commit}" >/dev/null || die "no ${REF}"
  local p
  for p in "$@"; do
    git -C "$REPO" cat-file -e "${REF}:${p}" 2>/dev/null || die "${p} is not on ${REF} yet (merged?)"
  done
  echo "==> files from ${REF} $(git -C "$REPO" rev-parse --short "${REF}")"
}

# One line of base64 holding a tar of the given paths at REF.
archive_b64() { git -C "$REPO" archive --format=tar "$REF" "$@" | base64 | tr -d '\n'; }

lan_ssh() { ssh -o IdentitiesOnly=yes -i "$LAN_KEY" -o ConnectTimeout=15 "$@"; }

step_mini() {
  local n=${1:-}
  [[ $n == 50 || $n == 52 ]] || die "usage: mini 50|52"
  local addr=192.168.10.$n
  need_ref scripts/host-exporters/install-mac.sh scripts/host-exporters/versions.env
  local b64
  b64=$(archive_b64 scripts/host-exporters/install-mac.sh scripts/host-exporters/versions.env)
  echo "==> mini-$n ($addr) as vision"
  lan_ssh "vision@${addr}" \
    "t=\$(mktemp -d) && trap 'rm -r \"\$t\"' EXIT && printf '%s' '$b64' | base64 -d | tar -C \"\$t\" -xf - && bash \"\$t/scripts/host-exporters/install-mac.sh\" $addr"
}

step_agent06() {
  [[ -r $NODE_KEY ]] || die "node key ${NODE_KEY} not found"
  need_ref scripts/host-exporters/install-linux.sh scripts/host-exporters/versions.env
  local b64
  b64=$(archive_b64 scripts/host-exporters/install-linux.sh scripts/host-exporters/versions.env)
  echo "==> agent-06 (192.168.10.79): ssh asks for the node key's passphrase once; type it within 2 minutes"
  ssh -F /dev/null -o IdentitiesOnly=yes -o IdentityAgent=none -o PreferredAuthentications=publickey \
    -o ConnectTimeout=15 -i "$NODE_KEY" vision@192.168.10.79 \
    "printf '%s' '$b64' | base64 -d | sudo -n bash -c 't=\$(mktemp -d) && trap \"rm -r \$t\" EXIT && tar -C \"\$t\" -xf - && bash \"\$t/scripts/host-exporters/install-linux.sh\" 192.168.10.79'"
}

step_nas() {
  need_ref scripts/host-exporters/nas/install-nas.sh scripts/host-exporters/nas/compose.yaml \
    scripts/host-exporters/nas/secure-dir.sh
  local b64
  b64=$(archive_b64 scripts/host-exporters/nas)
  echo "==> nas (192.168.10.20) as k8s_admin: sudo asks for k8s_admin's NAS password once"
  lan_ssh -t k8s_admin@192.168.10.20 \
    "printf '%s' '$b64' | base64 -d | sudo bash -c 't=\$(mktemp -d) && trap \"rm -r \$t\" EXIT && tar -C \"\$t\" -xf - && bash \"\$t/scripts/host-exporters/nas/install-nas.sh\"'"
}

step_cluster() {
  [[ -r $ADMIN_KUBECONFIG ]] || die "admin kubeconfig ${ADMIN_KUBECONFIG} not found"
  # The rules page for a host whose exporter is not there yet (BifrostNasSmartBlind after
  # 2 hours, the absent() guards after 10-15 minutes), so the hosts come first.
  echo "==> the six endpoints answer (steps 2-4 done)"
  step_check || die "an endpoint is missing: finish steps 2-4 first; nothing applied"
  local f paths=()
  for f in "${MONITORING[@]}"; do paths+=("k8s/monitoring/$f"); done
  need_ref "${paths[@]}"
  # Global, not local: the EXIT trap runs after this function has returned.
  tmp=$(mktemp -d)
  trap 'rm -r "$tmp"' EXIT
  for f in "${MONITORING[@]}"; do
    git -C "$REPO" show "${REF}:k8s/monitoring/$f" > "$tmp/$f"
  done
  export KUBECONFIG=$ADMIN_KUBECONFIG
  echo "==> server dry-run (nothing changes yet)"
  for f in "${MONITORING[@]}"; do
    kubectl apply --dry-run=server -f "$tmp/$f" || die "dry-run of $f failed: nothing applied"
  done
  echo "==> apply"
  for f in "${MONITORING[@]}"; do
    kubectl apply -f "$tmp/$f" || die "apply of $f failed (the files before it are applied)"
  done
  kubectl -n monitoring rollout status deployment/bifrost-blackbox-exporter --timeout=180s \
    || die "the Gitea prober did not become ready"
  echo "host-exporters: cluster OK (Prometheus loads the new targets and rules within about a minute)"
}

step_check() {
  local line host hp metric bad=0
  for line in "${ENDPOINTS[@]}"; do
    read -r host hp metric <<<"$line"
    if curl -fsS --max-time 5 "http://${hp}/metrics" 2>/dev/null | grep "^${metric}" >/dev/null; then
      echo "ok       ${host} ${hp} (${metric})"
    else
      echo "MISSING  ${host} ${hp} (${metric})"
      bad=1
    fi
  done
  return "$bad"
}

case "${1:-}" in
  mini) step_mini "${2:-}" ;;
  agent-06) step_agent06 ;;
  nas) step_nas ;;
  cluster) step_cluster ;;
  check) step_check ;;
  *) usage ;;
esac
