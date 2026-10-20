#!/usr/bin/env bash
# exam-on-06.sh <executor> <build> <sha256> — on the agent host, as root:
# install the agentd build as agentd-exam (beside the daemons' agentd, which
# keeps running) and the exam unit, then start the chief's exam with that
# executor (W-31 2.4 chief exam S4). agent-06-owner.sh exam sends this
# directory and runs it. Nothing is stopped before the sitting starts; the
# unit stops the STG agentd when it starts and starts it again when it ends.
# A start while the paper this host keeps is open goes on with it.
set -euo pipefail

die() {
  echo "exam-on-06: $*" >&2
  exit 1
}
ex=${1:-} build=${2:-} sum=${3:-}
[ "$(id -u)" = 0 ] || die "run it as root"
case "$ex" in claude) ;; *) die "only claude sits the chief's exam (the chief of staff's seat), not ${ex:-nothing}" ;; esac
[[ $build =~ ^agentd-[0-9a-f]{7,40}-linux-amd64$ ]] || die "$build is not an agentd build"
[[ $sum =~ ^[0-9a-f]{64}$ ]] || die "the build's sha256 is not 64 hex characters"
here=$(cd "$(dirname "$0")" && pwd -P)
unit=bifrost-agentd-exam@$ex.service
echo "$sum  $here/$build" | sha256sum --quiet -c - || die "$build does not match its sha256; nothing changed"
! systemctl is-active --quiet "$unit" || die "a sitting with $ex is going already; nothing changed"
# agentd's write wall needs Landlock with ABI 3 or later; without it the
# sitting refuses to start, so say so before anything is stopped.
abi=$(python3 -I -c 'import ctypes; l = ctypes.CDLL(None, use_errno=True); print(l.syscall(444, None, 0, 1))' 2> /dev/null || echo -1)
[ "$abi" -ge 3 ] 2> /dev/null || die "this kernel's Landlock ABI is ${abi}, not 3 or later: no run proves its pins here; nothing changed"
install -d -m 755 /usr/local/libexec/bifrost
install -m 755 "$here/$build" /usr/local/libexec/bifrost/agentd-exam
install -m 644 "$here/bifrost-agentd-exam@.service" /etc/systemd/system/bifrost-agentd-exam@.service
systemctl daemon-reload
systemd-analyze verify "$unit"
systemctl start --no-block "$unit"
sleep 15
if ! systemctl is-active --quiet "$unit"; then
  journalctl -u "$unit" -n 20 --no-pager -o cat >&2 || true
  die "$unit did not stay up (its last lines are above); the STG agentd starts again by itself"
fi
echo "sitting: $unit with $build (the STG agentd is stopped until it ends)"
