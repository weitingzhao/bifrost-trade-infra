#!/usr/bin/env bash
# install-nas.sh — start node_exporter and smartctl_exporter on the NAS (W-68 B4 ①).
#
# Runs on the NAS as root, from the root-owned mktemp directory that
# `host-exporters.sh nas` unpacks this directory into (same ssh session, sudo asked once).
# Pulls the two pinned images from quay.io, starts them, and checks that each answers
# with its key metric. Re-running is safe: compose only recreates a container whose
# definition changed. Stops at the first problem with a non-zero exit.
#
# Where the compose file lives: /volume1/@bifrost/host-exporters/. Every directory from /
# down to it is root's and writable by root alone, which secure-dir.sh checks before the
# file is written and again before compose reads it. Not /volume1/docker/: that shared
# folder is 777, so any NAS account could rename a root directory inside it and put its
# own compose file in its place, which root would then run (review 537 A1). Only the
# directory and the file this script creates are touched; /volume1/docker and the
# minio-backup files in it are left as they are.
#
# Remove: sudo docker compose -f /volume1/@bifrost/host-exporters/compose.yaml down
set -euo pipefail

die() { echo "install-nas: $*" >&2; exit 1; }

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BASE=/volume1/@bifrost
DIR=$BASE/host-exporters
COMPOSE=$DIR/compose.yaml
ADDR=192.168.10.20

[[ $(id -u) == 0 ]] || die "run as root"
[[ -f $HERE/compose.yaml && -f $HERE/secure-dir.sh ]] || die "compose.yaml and secure-dir.sh must be beside this script"
ip -4 -o addr show | grep " inet ${ADDR}/" >/dev/null || die "this host does not own ${ADDR}"
command -v docker >/dev/null || die "docker not found"
secure() { bash "$HERE/secure-dir.sh" 0 "$1" || die "refusing: $1 is not root's alone (see above)"; }

echo "==> $DIR (root's alone, from / down)"
secure /volume1
for d in "$BASE" "$DIR"; do
  [[ -L $d ]] && die "$d is a symbolic link"
  if [[ ! -d $d ]]; then
    mkdir -m 0755 "$d"
  fi
  chown root:root "$d"
  chmod 0755 "$d"
done
secure "$DIR"
[[ -L $COMPOSE ]] && die "$COMPOSE is a symbolic link"
install -o root -g root -m 0644 "$HERE/compose.yaml" "$COMPOSE"
secure "$COMPOSE"
cmp -s "$HERE/compose.yaml" "$COMPOSE" || die "$COMPOSE is not the file this run brought"

cd "$DIR"
echo "==> compose"
docker compose -f "$COMPOSE" config --quiet || die "compose.yaml does not parse"
docker compose -f "$COMPOSE" pull
docker compose -f "$COMPOSE" up -d
docker compose -f "$COMPOSE" ps

# wait_for <url> <pattern> <seconds>
wait_for() {
  local i
  for ((i = 0; i < $3; i += 3)); do
    if curl -fsS --max-time 5 "$1" 2>/dev/null | grep "$2" >/dev/null; then return 0; fi
    sleep 3
  done
  return 1
}

echo "==> check"
wait_for "http://${ADDR}:9100/metrics" '^node_md_disks' 30 \
  || die "node_exporter answers no RAID metrics on ${ADDR}:9100 (docker compose -f $COMPOSE logs node-exporter)"
# The first SMART read of three 12 TB disks takes a while. All three must answer: the
# BifrostNasSmartBlind alert pages when fewer than 3 report health for 2 hours.
n=0
for _ in $(seq 1 40); do
  n=$(curl -fsS --max-time 5 "http://${ADDR}:9633/metrics" 2>/dev/null | grep -c '^smartctl_device_smart_status{' || true)
  [[ $n -ge 3 ]] && break
  sleep 3
done
[[ $n -ge 3 ]] || die "smartctl_exporter reports health for ${n} disks, not 3 (docker compose -f $COMPOSE logs smartctl-exporter)"
curl -fsS --max-time 5 "http://${ADDR}:9100/metrics" | grep -E '^node_md_(disks|disks_required)\{' | sed 's/^/    /'
curl -fsS --max-time 5 "http://${ADDR}:9633/metrics" | grep -E '^smartctl_device_smart_status' | sed 's/^/    /'
echo "install-nas: OK (node_exporter :9100, smartctl_exporter :9633, ${n} disks)"
