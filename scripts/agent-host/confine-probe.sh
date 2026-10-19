#!/usr/bin/env bash
# confine-probe.sh <user> — run agentd's write-wall probe (TD-371, platform
# 35eafb7) as that agent user, under the same systemd confinement as its
# agentd unit: the installed agentd proves, as it does when it starts, that
# an attempt writes nothing outside its own directories, for every executor,
# codex's own sandbox included. No model is called and no credential is read
# or printed. Run as root by agent-06-owner.sh confine-probe (see
# CUT-agentd-confine-2026-10-19.md §8). Exits 0 only when the wall holds for
# every executor.
set -euo pipefail

u=${1:-}
case "$u" in bifrost-agentd | bifrost-agentd-stg) ;; *)
  echo "confine-probe: not an agent user: ${u:-none}" >&2
  exit 2
  ;;
esac
[ "$(id -u)" = 0 ] || {
  echo "confine-probe: run as root" >&2
  exit 2
}
agentd=/usr/local/libexec/bifrost/agentd
[ -x "$agentd" ] || {
  echo "confine-probe: $agentd is not installed" >&2
  exit 1
}
echo "kernel $(uname -r); lsm: $(cat /sys/kernel/security/lsm 2> /dev/null || echo unreadable)"
# The unit's confinement (bifrost-agentd*.service), as a transient service,
# with the agentd directory the unit gives it (AGENTD_ROOT).
systemd-run --quiet --wait --pipe --collect \
  --uid="$u" --gid="$u" \
  -p NoNewPrivileges=yes -p PrivateTmp=yes -p ProtectSystem=strict \
  -p ProtectHome=tmpfs -p BindPaths="/home/$u" -p ReadWritePaths="/home/$u" \
  -p ProtectKernelTunables=yes -p ProtectKernelModules=yes -p ProtectKernelLogs=yes \
  -p ProtectControlGroups=yes -p ProtectClock=yes -p ProtectHostname=yes \
  -p RestrictSUIDSGID=yes -p RestrictRealtime=yes -p LockPersonality=yes -p UMask=0077 \
  -p WorkingDirectory="/home/$u" \
  -E HOME="/home/$u" -E USER="$u" -E LOGNAME="$u" -E LANG=C.UTF-8 \
  -E PATH="/opt/bifrost/codex/bin:/home/$u/.local/bin:/usr/local/go/bin:/usr/local/lib/nodejs/current/bin:/usr/local/bin:/usr/bin:/bin" \
  "$agentd" confine-probe --root "/home/$u/agent-work/agentd"
