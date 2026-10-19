#!/usr/bin/env bash
# bench-on-06.sh <executor> <build> <sha256> — on the agent host, as root:
# install the agentd build as agentd-bench (beside the daemons' agentd, which
# keeps running), the bench unit and the question set that came with it, then
# start a benchmark run with that executor (W-31 2.4 slice ⑤; review 287 B8,
# B13). agent-06-owner.sh bench sends this directory and runs it. Nothing is
# stopped before the run starts; the unit stops the STG agentd when it starts
# and starts it again when it ends.
set -euo pipefail

die() {
  echo "bench-on-06: $*" >&2
  exit 1
}
ex=${1:-} build=${2:-} sum=${3:-}
[ "$(id -u)" = 0 ] || die "run it as root"
case "$ex" in codex) ;; *) die "only codex runs the benchmark for now, not ${ex:-nothing}" ;; esac
[[ $build =~ ^agentd-[0-9a-f]{7,40}-linux-amd64$ ]] || die "$build is not an agentd build"
[[ $sum =~ ^[0-9a-f]{64}$ ]] || die "the build's sha256 is not 64 hex characters"
here=$(cd "$(dirname "$0")" && pwd -P)
unit=bifrost-agentd-bench@$ex.service
echo "$sum  $here/$build" | sha256sum --quiet -c - || die "$build does not match its sha256; nothing changed"
python3 -I -c 'import json, sys; q = json.load(open(sys.argv[1])); sys.exit(0 if isinstance(q, list) and q else 1)' "$here/questions.json" ||
  die "the question set that came is not one; nothing changed"
! systemctl is-active --quiet "$unit" || die "a run with $ex is going already; nothing changed"
if ! dpkg -s python3-venv > /dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends python3-venv
fi
install -d -m 755 /usr/local/libexec/bifrost
install -m 755 "$here/$build" /usr/local/libexec/bifrost/agentd-bench
install -m 644 "$here/bifrost-agentd-bench@.service" /etc/systemd/system/bifrost-agentd-bench@.service
install -D -m 644 "$here/questions.json" /usr/local/share/bifrost/benchmark/questions.json
systemctl daemon-reload
systemd-analyze verify "$unit"
systemctl start --no-block "$unit"
sleep 15
if ! systemctl is-active --quiet "$unit"; then
  journalctl -u "$unit" -n 20 --no-pager -o cat >&2 || true
  die "$unit did not stay up (its last lines are above); the STG agentd starts again by itself"
fi
echo "running: $unit with $build (the STG agentd is stopped until it ends)"
