#!/usr/bin/env bash
# install-mac.sh — node_exporter on a Mac mini (W-68 B4 ①), as the login user, no sudo.
#
#   bash install-mac.sh 192.168.10.50      (on .50; 192.168.10.52 on .52)
#
# Streamed from origin/main with `git archive` and run in the same ssh call as `vision`
# (agent-config/work/multi-agent/OWNER-STEPS-w68-b4-2026-10-24.md, step 2). Everything it
# writes is in that user's home:
#   ~/bifrost-agent/node-exporter/<version>/node_exporter   (release tarball from github.com,
#                                                            refused unless it matches versions.env)
#   ~/bifrost-agent/node-exporter/current -> <version>
#   ~/Library/LaunchAgents/com.bifrost.node-exporter.plist   (RunAtLoad + KeepAlive)
#   ~/bifrost-agent/logs/node-exporter.log
# The job lives in the user's gui domain, like com.bifrost.operator-plane: with FileVault
# on, nothing in that domain runs after a reboot until the user logs in, and the
# BifrostHostDown alert says so. node_exporter listens only on the address given.
#
# Re-running is safe: the same version restarts the job once; a new version in
# versions.env lands beside the old one and `current` moves. Stops at the first problem.
#
# Remove: launchctl bootout gui/$(id -u)/com.bifrost.node-exporter
#         rm ~/Library/LaunchAgents/com.bifrost.node-exporter.plist
set -euo pipefail

die() { echo "install-mac: $*" >&2; exit 1; }

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=versions.env
. "$HERE/versions.env"

ADDR=${1:-}
[[ $ADDR =~ ^192\.168\.10\.[0-9]{1,3}$ ]] || die "usage: install-mac.sh <this Mac's 192.168.10.x address>"
[[ $(id -u) != 0 ]] || die "run as the login user (vision), not root"
[[ "$(uname -s)/$(uname -m)" == Darwin/arm64 ]] || die "expects macOS arm64, found $(uname -s)/$(uname -m)"
ifconfig | grep "inet ${ADDR} " >/dev/null || die "this Mac does not own ${ADDR}"

LABEL=com.bifrost.node-exporter
ROOT=$HOME/bifrost-agent/node-exporter
DEST=$ROOT/$NODE_EXPORTER_VERSION
PLIST=$HOME/Library/LaunchAgents/$LABEL.plist
LOG=$HOME/bifrost-agent/logs/node-exporter.log
tarball="node_exporter-${NODE_EXPORTER_VERSION}.darwin-arm64.tar.gz"
tmp=$(mktemp -d)
trap 'rm -r "$tmp"' EXIT

echo "==> node_exporter ${NODE_EXPORTER_VERSION} (darwin-arm64)"
if [[ ! -x "$DEST/node_exporter" ]]; then
  curl -fsSL --retry 3 --max-time 180 -o "$tmp/$tarball" \
    "https://github.com/prometheus/node_exporter/releases/download/v${NODE_EXPORTER_VERSION}/${tarball}"
  echo "${NODE_EXPORTER_SHA256_DARWIN_ARM64}  $tmp/$tarball" | shasum -a 256 -c --quiet - \
    || die "checksum mismatch for ${tarball}"
  tar -C "$tmp" -xzf "$tmp/$tarball"
  mkdir -p "$DEST"
  install -m 0755 "$tmp/node_exporter-${NODE_EXPORTER_VERSION}.darwin-arm64/node_exporter" "$DEST/node_exporter"
  echo "    installed $DEST/node_exporter"
fi
ln -sfn "$NODE_EXPORTER_VERSION" "$ROOT/current"
"$ROOT/current/node_exporter" --version 2>&1 | head -1 | sed 's/^/    /'

echo "==> launchd job $LABEL"
mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
cat > "$tmp/$LABEL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- Installed by bifrost-trade-infra scripts/host-exporters/install-mac.sh (W-68 B4 ①). -->
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${ROOT}/current/node_exporter</string>
    <string>--web.listen-address=${ADDR}:9100</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>10</integer>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>${LOG}</string>
  <key>StandardErrorPath</key>
  <string>${LOG}</string>
</dict>
</plist>
EOF
plutil -lint -s "$tmp/$LABEL.plist" || die "generated plist does not parse"
install -m 0644 "$tmp/$LABEL.plist" "$PLIST"
uid=$(id -u)
launchctl bootout "gui/$uid/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$uid" "$PLIST" || die "launchctl bootstrap failed (is $USER logged in on this Mac?)"

echo "==> check"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS --max-time 5 "http://${ADDR}:9100/metrics" 2>/dev/null | grep '^node_uname_info' >/dev/null; then
    curl -fsS --max-time 5 "http://${ADDR}:9100/metrics" | grep -E '^node_exporter_build_info' | sed 's/^/    /'
    echo "install-mac: OK on ${ADDR}:9100"
    exit 0
  fi
  sleep 2
done
tail -20 "$LOG" >&2 || true
die "node_exporter does not answer on ${ADDR}:9100"
