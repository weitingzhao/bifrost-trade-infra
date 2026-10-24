#!/usr/bin/env bash
# install-disk-guard.sh — schedule disk-guard.sh sweep on this machine (W-31 4.6 S1).
#
#   macOS, as the user who runs the agents:
#     install-disk-guard.sh [--apply] [--dry-run]
#       copies disk-guard.sh, disk_guard*.py and cache-roots.tsv to $AGENT_WORK/bin/disk-guard/,
#       points $AGENT_WORK/bin/disk-guard.sh (what the dispatch checks call) at that copy, and
#       loads the LaunchAgent com.bifrost.disk-guard (hourly) in place of the old one
#   Linux, as root, once per agent user:
#     install-disk-guard.sh --user <name> [--apply] [--dry-run]
#       copies the same files to /usr/local/libexec/bifrost/disk-guard/, installs
#       bifrost-disk-guard@.service and .timer, enables bifrost-disk-guard@<name>.timer
#   Either:
#     install-disk-guard.sh --render-plist <file> [--apply]
#       only writes the filled-in LaunchAgent plist to <file> (to read before installing)
#
# Without --apply the scheduled sweep only writes its report ($AGENT_WORK/status/
# lifecycle.json); with it, it removes what the report says can go. Run it again without
# --apply to go back to report only. --dry-run prints each step instead of doing it.
# A file it replaces is kept beside it as <name>.pre-repo-<UTC time>.
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
label=com.bifrost.disk-guard
modules="disk_guard.py disk_guard_base.py disk_guard_layout.py disk_guard_roots.py disk_guard_items.py disk_guard_apply.py disk_guard_state.py disk_guard_inventory.py disk_guard_host.py"
apply=0 dry=0 user="" render=""
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) apply=1 ;;
    --dry-run) dry=1 ;;
    --user) user=${2:?--user needs a name}; shift ;;
    --render-plist) render=${2:?--render-plist needs a file}; shift ;;
    -h|--help) sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "install-disk-guard: unknown argument $1" >&2; exit 2 ;;
  esac
  shift
done

die() { echo "install-disk-guard: $*" >&2; exit 1; }
do_() { if [ "$dry" = 1 ]; then printf 'would run:'; printf ' %q' "$@"; echo; else "$@"; fi; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
keep_old() { # keep_old <file>: move an existing file aside, never over another
  [ -e "$1" ] || return 0
  do_ mv -n "$1" "$1.pre-repo-$stamp"
}

# render_plist <disk-guard.sh path> <agent work> <log> <out>
render_plist() {
  python3 - "$here/$label.plist" "$1" "$2" "$3" "$apply" > "$4" <<'PY'
import sys
from xml.sax.saxutils import escape
tpl, script, work, log, apply = sys.argv[1:]
s = open(tpl, encoding="utf-8").read()
s = s.replace("@APPLY@", "\n    <string>--apply</string>" if apply == "1" else "")
for k, v in (("@DISK_GUARD@", script), ("@AGENT_WORK@", work), ("@LOG@", log)):
    s = s.replace(k, escape(v))
assert "@" not in s.split("-->", 1)[1], "a placeholder is left"
sys.stdout.write(s)
PY
}

# copy_files <dest>: the entry point, the modules and the shipped registry
copy_files() {
  do_ install -d -m 755 "$1"
  do_ install -m 755 "$here/disk-guard.sh" "$1/disk-guard.sh"
  for f in $modules; do do_ install -m 644 "$here/$f" "$1/$f"; done
  do_ install -m 644 "$here/cache-roots.tsv" "$1/cache-roots.tsv"
}

for f in disk-guard.sh $modules cache-roots.tsv; do
  [ -f "$here/$f" ] || die "missing $here/$f"
done

if [ -n "$render" ]; then
  work=${AGENT_WORK:-$HOME/agent-work}
  render_plist "$work/bin/disk-guard/disk-guard.sh" "$work" "$work/disk-guard.log" "$render"
  exit 0
fi

case "$(uname -s)" in
  Darwin)
    [ -z "$user" ] || die "--user is for Linux; on macOS run it as the user who runs the agents"
    [ "$(id -u)" != 0 ] || die "run it as the user who runs the agents, not root"
    work=${AGENT_WORK:-$HOME/agent-work}
    [ -d "$work" ] || die "AGENT_WORK=$work is not a directory"
    dest=$work/bin/disk-guard
    copy_files "$dest"
    shim=$work/bin/disk-guard.sh
    if [ -e "$shim" ] && ! grep -q 'install-disk-guard.sh' "$shim" 2>/dev/null; then keep_old "$shim"; fi
    if [ "$dry" = 1 ]; then
      echo "would write $shim (exec bash $dest/disk-guard.sh)"
    else
      printf '#!/usr/bin/env bash\n# Written by install-disk-guard.sh: the copy from bifrost-trade-infra scripts/agent-host.\nexec bash %q "$@"\n' "$dest/disk-guard.sh" > "$shim"
      chmod 755 "$shim"
    fi
    plist=$HOME/Library/LaunchAgents/$label.plist
    tmp=$(mktemp "${TMPDIR:-/tmp}/disk-guard-plist.XXXXXX")
    trap 'rm -f "$tmp"' EXIT
    render_plist "$dest/disk-guard.sh" "$work" "$work/disk-guard.log" "$tmp"
    plutil -lint "$tmp" > /dev/null || die "the rendered plist does not parse"
    if [ -e "$plist" ] && ! cmp -s "$tmp" "$plist"; then keep_old "$plist"; fi
    do_ install -m 644 "$tmp" "$plist"
    do_ launchctl bootout "gui/$(id -u)/$label" 2> /dev/null || true
    do_ launchctl bootstrap "gui/$(id -u)" "$plist"
    ;;
  Linux)
    [ -n "$user" ] || die "on Linux name the agent user: --user <name>"
    [ "$(id -u)" = 0 ] || die "run it as root (sudo)"
    id "$user" > /dev/null 2>&1 || die "no user $user"
    [ -d "/home/$user/agent-work" ] || die "/home/$user/agent-work is not a directory"
    dest=/usr/local/libexec/bifrost/disk-guard
    copy_files "$dest"
    for u in bifrost-disk-guard@.service bifrost-disk-guard@.timer; do
      do_ install -m 644 "$here/$u" "/etc/systemd/system/$u"
    done
    dropin=/etc/systemd/system/bifrost-disk-guard@$user.service.d
    if [ "$apply" = 1 ]; then
      do_ install -d -m 755 "$dropin"
      if [ "$dry" = 1 ]; then echo "would write $dropin/mode.conf (DISK_GUARD_ARGS=--apply)"
      else printf '[Service]\nEnvironment=DISK_GUARD_ARGS=--apply\n' > "$dropin/mode.conf"; fi
    elif [ -e "$dropin/mode.conf" ]; then
      keep_old "$dropin/mode.conf"
    fi
    do_ systemctl daemon-reload
    do_ systemctl enable --now "bifrost-disk-guard@$user.timer"
    ;;
  *) die "unsupported system $(uname -s)" ;;
esac

mode="report only"; [ "$apply" = 1 ] && mode="apply"
if [ "$dry" = 1 ]; then echo "install-disk-guard: dry run, nothing changed ($mode)"
else echo "install-disk-guard: installed ($mode)"; fi
