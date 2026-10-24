#!/usr/bin/env bash
# install-linux.sh — node_exporter and smartctl_exporter on ubt-k3s-06 (W-68 B4 ①).
#
#   sudo bash install-linux.sh 192.168.10.79
#
# Runs on 06 as root (the Owner's `vision`, passwordless sudo there). The Owner streams
# this directory from origin/main with `git archive` and runs it in the same ssh call:
# agent-config/work/multi-agent/OWNER-STEPS-w68-b4-2026-10-24.md, step 3.
#
# What it does:
#   - installs smartmontools from Ubuntu if smartctl is missing;
#   - downloads node_exporter and smartctl_exporter release tarballs from github.com and
#     refuses them unless they match the checksums in versions.env;
#   - installs both to /usr/local/bin, and two systemd units:
#       node-exporter.service      user node-exporter (system user, no shell), :9100
#       smartctl-exporter.service  root (SMART needs raw device access), :9633,
#                                  capabilities limited to CAP_SYS_RAWIO + CAP_SYS_ADMIN
#     both listening only on the address given;
#   - starts them and checks that each answers with its key metric.
#
# Re-running is safe: with the same versions nothing changes and nothing restarts; with
# new versions in versions.env the binaries are replaced and the services restarted.
# It stops at the first problem with a non-zero exit. It prints no credential (there is
# none: the endpoints are unauthenticated on the LAN, like the cluster's node-exporter).
set -euo pipefail

die() { echo "install-linux: $*" >&2; exit 1; }

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=versions.env
. "$HERE/versions.env"

ADDR=${1:-}
[[ $ADDR =~ ^192\.168\.10\.[0-9]{1,3}$ ]] || die "usage: install-linux.sh <this host's 192.168.10.x address>"
[[ $(id -u) == 0 ]] || die "run as root: sudo bash $0 $ADDR"
[[ "$(uname -s)/$(uname -m)" == Linux/x86_64 ]] || die "expects Linux x86_64, found $(uname -s)/$(uname -m)"
command -v systemctl >/dev/null || die "systemd not found"
ip -4 -o addr show | grep " inet ${ADDR}/" >/dev/null || die "this host does not own ${ADDR}"

BIN=/usr/local/bin
UNITS=/etc/systemd/system
tmp=$(mktemp -d)
trap 'rm -r "$tmp"' EXIT
changed=0

# Same filesystem filters as the cluster DaemonSet (kube-prometheus-stack-prometheus-node-exporter).
MOUNTS_EXCLUDE='^/(dev|proc|sys|run/containerd/.+|var/lib/docker/.+|var/lib/kubelet/.+)($|/)'
FSTYPES_EXCLUDE='^(autofs|binfmt_misc|bpf|cgroup2?|configfs|debugfs|devpts|devtmpfs|fusectl|hugetlbfs|iso9660|mqueue|nsfs|overlay|proc|procfs|pstore|rpc_pipefs|securityfs|selinuxfs|squashfs|sysfs|tracefs|erofs)$'
# systemd expands $ in ExecStart; $$ is a literal dollar.
unit_escape() { printf '%s' "${1//\$/\$\$}"; }

echo "==> smartmontools"
if ! command -v smartctl >/dev/null; then
  DEBIAN_FRONTEND=noninteractive apt-get update -q
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends smartmontools
fi
SMARTCTL=$(command -v smartctl) || die "smartctl still missing after apt-get install"
echo "    $SMARTCTL ($("$SMARTCTL" --version | head -1))"

# fetch <name> <version> <sha256> <github repo>: prints the path of the extracted binary.
fetch() {
  local name=$1 version=$2 sha=$3 repo=$4
  local tarball="${name}-${version}.linux-amd64.tar.gz"
  curl -fsSL --retry 3 --max-time 180 -o "$tmp/$tarball" \
    "https://github.com/${repo}/releases/download/v${version}/${tarball}"
  echo "${sha}  $tmp/$tarball" | sha256sum -c --quiet - >&2 || die "checksum mismatch for ${tarball}"
  tar -C "$tmp" -xzf "$tmp/$tarball"
  [[ -x "$tmp/${name}-${version}.linux-amd64/${name}" ]] || die "${tarball} has no ${name} binary"
  echo "$tmp/${name}-${version}.linux-amd64/${name}"
}

# put <src> <dst> <mode>: install when the content differs; marks a change.
put() {
  if ! cmp -s "$1" "$2"; then
    install -m "$3" -o root -g root "$1" "$2"
    changed=1
    echo "    wrote $2"
  fi
}

echo "==> binaries (node_exporter ${NODE_EXPORTER_VERSION}, smartctl_exporter ${SMARTCTL_EXPORTER_VERSION})"
ne=$(fetch node_exporter "$NODE_EXPORTER_VERSION" "$NODE_EXPORTER_SHA256_LINUX_AMD64" prometheus/node_exporter)
se=$(fetch smartctl_exporter "$SMARTCTL_EXPORTER_VERSION" "$SMARTCTL_EXPORTER_SHA256_LINUX_AMD64" prometheus-community/smartctl_exporter)
put "$ne" "$BIN/node_exporter" 0755
put "$se" "$BIN/smartctl_exporter" 0755

echo "==> user node-exporter"
if ! id -u node-exporter >/dev/null 2>&1; then
  useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin node-exporter
  echo "    created"
fi

echo "==> systemd units"
cat > "$tmp/node-exporter.service" <<EOF
# Installed by bifrost-trade-infra scripts/host-exporters/install-linux.sh (W-68 B4 ①).
[Unit]
Description=Prometheus node_exporter (Bifrost host monitoring)
After=network-online.target
Wants=network-online.target

[Service]
User=node-exporter
Group=node-exporter
ExecStart=$BIN/node_exporter \\
  --web.listen-address=${ADDR}:9100 \\
  --collector.filesystem.mount-points-exclude=$(unit_escape "$MOUNTS_EXCLUDE") \\
  --collector.filesystem.fs-types-exclude=$(unit_escape "$FSTYPES_EXCLUDE")
Restart=always
RestartSec=5
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

cat > "$tmp/smartctl-exporter.service" <<EOF
# Installed by bifrost-trade-infra scripts/host-exporters/install-linux.sh (W-68 B4 ①).
# Root, because reading SMART needs raw access to the disks; capabilities are cut to the
# two smartctl uses (ATA pass-through, NVMe admin commands).
[Unit]
Description=Prometheus smartctl_exporter (Bifrost host monitoring)
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$BIN/smartctl_exporter \\
  --web.listen-address=${ADDR}:9633 \\
  --smartctl.path=${SMARTCTL} \\
  --smartctl.interval=60s
Restart=always
RestartSec=5
CapabilityBoundingSet=CAP_SYS_RAWIO CAP_SYS_ADMIN
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
put "$tmp/node-exporter.service" "$UNITS/node-exporter.service" 0644
put "$tmp/smartctl-exporter.service" "$UNITS/smartctl-exporter.service" 0644

systemctl daemon-reload
systemctl enable --quiet node-exporter.service smartctl-exporter.service
if [[ $changed == 1 ]]; then
  systemctl restart node-exporter.service smartctl-exporter.service
else
  systemctl start node-exporter.service smartctl-exporter.service
fi

echo "==> host firewall (information only)"
if command -v nft >/dev/null && nft list chains 2>/dev/null | grep 'hook input' >/dev/null; then
  echo "    an nftables input chain exists: tcp 9100 and 9633 from 192.168.10.0/24 must be accepted"
else
  echo "    no nftables input chain: 9100 and 9633 are reachable on ${ADDR}"
fi

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
wait_for "http://${ADDR}:9100/metrics" '^node_uname_info' 30 \
  || die "node_exporter does not answer on ${ADDR}:9100 (journalctl -u node-exporter -n 50)"
# smartctl_exporter scans the disks after it starts; the first SMART read can take a while.
wait_for "http://${ADDR}:9633/metrics" '^smartctl_device_smart_status' 90 \
  || die "smartctl_exporter answers no SMART status on ${ADDR}:9633 (journalctl -u smartctl-exporter -n 50)"
curl -fsS --max-time 5 "http://${ADDR}:9100/metrics" | grep -E '^node_exporter_build_info' | sed 's/^/    /'
curl -fsS --max-time 5 "http://${ADDR}:9633/metrics" | grep -E '^smartctl_device_smart_status' | sed 's/^/    /'
echo "install-linux: OK on ${ADDR} (node_exporter :9100, smartctl_exporter :9633)"
