#!/usr/bin/env bash
# codex-sandbox-probe.sh <user> — run one command in codex's own sandbox as
# that agent user, under the same systemd confinement as its agentd unit, and
# show that the command ran in a network namespace of its own: the step that
# failed on 06 before the AppArmor rule bifrost-codex (2026-10-17, STG walk
# M-6, "bwrap: loopback: Failed RTM_NEWADDR"). No model is called. Run as
# root by prepare-agent-06.sh and check-agent-06.sh (review 235 B1). The
# permission profile is :workspace, the one agentd's `codex exec -s
# workspace-write` runs under; codex 0.163 on Linux requires one by name.
set -euo pipefail

u=${1:-}
case "$u" in bifrost-agentd | bifrost-agentd-stg) ;; *)
  echo "codex-sandbox-probe: not an agent user: ${u:-none}" >&2
  exit 2
  ;;
esac
[ "$(id -u)" = 0 ] || {
  echo "codex-sandbox-probe: run as root" >&2
  exit 2
}
host_ns=$(readlink /proc/1/ns/net 2> /dev/null || true)
case "$host_ns" in net:\[[0-9]*\]) ;; *)
  echo "codex-sandbox-probe: cannot read the host's network namespace from /proc/1/ns/net" >&2
  exit 1
  ;;
esac
rc=0
# The unit's confinement (bifrost-agentd*.service), as a transient service.
out=$(systemd-run --quiet --wait --pipe --collect \
  --uid="$u" --gid="$u" \
  -p NoNewPrivileges=yes -p PrivateTmp=yes -p ProtectSystem=strict \
  -p ProtectHome=tmpfs -p BindPaths="/home/$u" -p ReadWritePaths="/home/$u" \
  -p ProtectKernelTunables=yes -p ProtectKernelModules=yes -p ProtectKernelLogs=yes \
  -p ProtectControlGroups=yes -p ProtectClock=yes -p ProtectHostname=yes \
  -p RestrictSUIDSGID=yes -p RestrictRealtime=yes -p LockPersonality=yes -p UMask=0077 \
  -p WorkingDirectory="/home/$u" \
  -E HOME="/home/$u" -E USER="$u" -E LOGNAME="$u" -E LANG=C.UTF-8 \
  -E PATH="/opt/bifrost/codex/bin:/home/$u/.local/bin:/usr/local/go/bin:/usr/local/lib/nodejs/current/bin:/usr/local/bin:/usr/bin:/bin" \
  /opt/bifrost/codex/bin/codex sandbox --permission-profile :workspace --cd "/home/$u" -- /bin/sh -c 'readlink /proc/self/ns/net' 2>&1) || rc=$?
if [ "$rc" != 0 ]; then
  printf '%s\n' "$out" | tail -5 >&2
  echo "codex-sandbox-probe: $u: codex's sandbox could not run a command under the unit's confinement (exit $rc)" >&2
  exit 1
fi
inner=$(printf '%s\n' "$out" | grep -E '^net:\[[0-9]+\]$' | tail -1 || true)
if [ -z "$inner" ]; then
  printf '%s\n' "$out" | tail -5 >&2
  echo "codex-sandbox-probe: $u: no network namespace in the output" >&2
  exit 1
fi
if [ "$inner" = "$host_ns" ]; then
  echo "codex-sandbox-probe: $u: the command ran in the host's network namespace, so the sandbox did not isolate the network and this proves nothing" >&2
  exit 1
fi
echo "$u: codex's sandbox ran a command in its own network namespace ($inner; host $host_ns) under the unit's confinement"
