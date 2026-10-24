#!/usr/bin/env bash
# install-nas.sh — start node_exporter and smartctl_exporter on the NAS (W-68 B4 ①).
#
# Runs on the NAS as root, from the root-owned mktemp directory that
# `host-exporters.sh nas` unpacks this directory into (same ssh session, sudo asked once).
# Puts compose.yaml in /volume1/docker/host-exporters/ (root-owned, like minio-backup),
# pulls the two pinned images from quay.io, starts them, and checks that each answers
# with its key metric. Re-running is safe: compose only recreates a container whose
# definition changed. Stops at the first problem with a non-zero exit.
#
# Remove: sudo docker compose -f /volume1/docker/host-exporters/compose.yaml down
set -euo pipefail

die() { echo "install-nas: $*" >&2; exit 1; }

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DIR=/volume1/docker/host-exporters
ADDR=192.168.10.20

[[ $(id -u) == 0 ]] || die "run as root"
[[ -f $HERE/compose.yaml ]] || die "compose.yaml is not beside this script"
ip -4 -o addr show | grep " inet ${ADDR}/" >/dev/null || die "this host does not own ${ADDR}"
command -v docker >/dev/null || die "docker not found"

echo "==> $DIR (root-owned)"
install -d -m 0755 "$DIR"
chown root:root "$DIR"
chmod 0755 "$DIR"
install -o root -g root -m 0644 "$HERE/compose.yaml" "$DIR/compose.yaml"

cd "$DIR"
echo "==> compose"
docker compose config --quiet || die "compose.yaml does not parse"
docker compose pull
docker compose up -d
docker compose ps

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
  || die "node_exporter answers no RAID metrics on ${ADDR}:9100 (docker compose logs node-exporter)"
# The first SMART read of three 12 TB disks takes a while.
wait_for "http://${ADDR}:9633/metrics" '^smartctl_device_smart_status' 120 \
  || die "smartctl_exporter answers no SMART status on ${ADDR}:9633 (docker compose logs smartctl-exporter)"
curl -fsS --max-time 5 "http://${ADDR}:9100/metrics" | grep -E '^node_md_(disks|disks_required)\{' | sed 's/^/    /'
curl -fsS --max-time 5 "http://${ADDR}:9633/metrics" | grep -E '^smartctl_device_smart_status' | sed 's/^/    /'
echo "install-nas: OK (node_exporter :9100, smartctl_exporter :9633)"
