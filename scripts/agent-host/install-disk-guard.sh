#!/usr/bin/env bash
# install-disk-guard.sh — schedule disk-guard.sh sweep on this machine (W-31 4.6 S1).
#
#   macOS, first step — a trial beside the old disk-guard, which keeps cleaning as today:
#     install-disk-guard.sh --alongside [--dry-run]
#       copies disk-guard.sh, disk_guard*.py and cache-roots.tsv to $AGENT_WORK/bin/disk-guard-next/
#       and loads the LaunchAgent com.bifrost.disk-guard.next: hourly, report only (--apply is
#       refused), log $AGENT_WORK/disk-guard-next.log, report and journal under
#       $AGENT_WORK/status/disk-guard-next/, lock $AGENT_WORK/.lifecycle-next.lock. The old
#       $AGENT_WORK/bin/disk-guard.sh, its plist and its Label com.bifrost.disk-guard are not touched.
#     install-disk-guard.sh --uninstall-alongside [--dry-run]
#       unloads com.bifrost.disk-guard.next and removes its plist and $AGENT_WORK/bin/disk-guard-next/
#       only (the report directory stays, to read)
#   macOS, later, in place of the old one, as the user who runs the agents:
#     install-disk-guard.sh [--apply] [--dry-run]
#       copies the files to $AGENT_WORK/bin/disk-guard/, points $AGENT_WORK/bin/disk-guard.sh
#       (what the dispatch checks call) at that copy, and loads com.bifrost.disk-guard (hourly)
#       in place of the old one; a file it replaces is kept as <name>.pre-repo-<UTC time>
#   Linux, as root, once per agent user:
#     install-disk-guard.sh --user <name> [--apply] [--dry-run]
#       copies the same files to /usr/local/libexec/bifrost/disk-guard/, installs
#       bifrost-disk-guard@.service and .timer, enables bifrost-disk-guard@<name>.timer
#   Either:
#     install-disk-guard.sh --render-plist <file> [--apply | --alongside]
#       only writes the filled-in LaunchAgent plist to <file> (to read before installing)
#
# Without --apply the scheduled sweep only writes its report; with it, it removes what the
# report says can go. --dry-run prints every file it would write, the exact plist, and each
# command, and changes nothing.
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
template=$here/com.bifrost.disk-guard.plist
main_label=com.bifrost.disk-guard
next_label=$main_label.next
modules="disk_guard.py disk_guard_base.py disk_guard_layout.py disk_guard_roots.py disk_guard_items.py disk_guard_apply.py disk_guard_state.py disk_guard_inventory.py disk_guard_host.py"
marker=INSTALLED-BY
apply=0 dry=0 user="" render="" alongside=0 uninstall=0
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) apply=1 ;;
    --dry-run) dry=1 ;;
    --alongside) alongside=1 ;;
    --uninstall-alongside) uninstall=1 ;;
    --user) user=${2:?--user needs a name}; shift ;;
    --render-plist) render=${2:?--render-plist needs a file}; shift ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "install-disk-guard: unknown argument $1" >&2; exit 2 ;;
  esac
  shift
done

die() { echo "install-disk-guard: $*" >&2; exit 1; }
if [ "$alongside" = 1 ] && [ "$apply" = 1 ]; then
  die "--alongside is report only: --apply is refused (the old disk-guard keeps cleaning)"
fi
if [ "$uninstall" = 1 ] && { [ "$alongside" = 1 ] || [ "$apply" = 1 ] || [ -n "$render" ]; }; then
  die "--uninstall-alongside takes only --dry-run"
fi

do_() { if [ "$dry" = 1 ]; then printf 'would run:'; printf ' %q' "$@"; echo; else "$@"; fi; }
stamp=$(date -u +%Y%m%dT%H%M%SZ)
keep_old() { # keep_old <file>: move an existing file aside, never over another
  [ -e "$1" ] || return 0
  do_ mv -n "$1" "$1.pre-repo-$stamp"
}

# render_plist <label> <disk-guard.sh path> <agent work> <log> <out> [NAME=VALUE ...]
render_plist() {
  local label=$1 script=$2 work=$3 log=$4 out=$5
  shift 5
  python3 - "$template" "$label" "$script" "$work" "$log" "$apply" "$@" > "$out" <<'PY'
import sys
from xml.sax.saxutils import escape
tpl, label, script, work, log, apply, *extra = sys.argv[1:]
s = open(tpl, encoding="utf-8").read()
s = s.replace("@APPLY@", "\n    <string>--apply</string>" if apply == "1" else "")
env = "".join(f"\n    <key>{escape(k)}</key>\n    <string>{escape(v)}</string>" for k, v in (e.split("=", 1) for e in extra))
s = s.replace("@EXTRA_ENV@", env)
for k, v in (("@LABEL@", label), ("@DISK_GUARD@", script), ("@AGENT_WORK@", work), ("@LOG@", log)):
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

work=${AGENT_WORK:-$HOME/agent-work}
next_dest=$work/bin/disk-guard-next
next_log=$work/disk-guard-next.log
# The trial's own report and journal, and its own lock; the machine's registry is the one a
# later install in place of the old disk-guard reads too.
next_env=("LIFECYCLE_STATUS_DIR=$work/status/disk-guard-next" "LIFECYCLE_LOCK=$work/.lifecycle-next.lock"
          "LIFECYCLE_MACHINE_ROOTS=$work/status/cache-roots.tsv")

if [ -n "$render" ]; then
  if [ "$alongside" = 1 ]; then
    render_plist "$next_label" "$next_dest/disk-guard.sh" "$work" "$next_log" "$render" "${next_env[@]}"
  else
    render_plist "$main_label" "$work/bin/disk-guard/disk-guard.sh" "$work" "$work/disk-guard.log" "$render"
  fi
  exit 0
fi

if [ "$alongside" = 1 ] || [ "$uninstall" = 1 ]; then
  [ "$(uname -s)" = Darwin ] || die "--alongside and --uninstall-alongside are for macOS"
  [ "$(id -u)" != 0 ] || die "run it as the user who runs the agents, not root"
  [ -d "$work" ] || die "AGENT_WORK=$work is not a directory"
  plist=$HOME/Library/LaunchAgents/$next_label.plist
  if [ "$uninstall" = 1 ]; then
    if [ -e "$next_dest" ] && [ ! -f "$next_dest/$marker" ]; then
      die "$next_dest has no $marker file: not this installer's, not removed"
    fi
    do_ launchctl bootout "gui/$(id -u)/$next_label" 2> /dev/null || true
    if [ -e "$plist" ]; then do_ rm -f -- "$plist"; fi
    if [ -d "$next_dest" ]; then do_ rm -rf -- "$next_dest"; fi
    if [ "$dry" = 1 ]; then echo "install-disk-guard: dry run, nothing changed"
    else echo "install-disk-guard: removed $next_label ($plist, $next_dest/); $work/status/disk-guard-next/ is left to read"; fi
    exit 0
  fi
  tmp=$(mktemp "${TMPDIR:-/tmp}/disk-guard-plist.XXXXXX")
  trap 'rm -f "$tmp"' EXIT
  render_plist "$next_label" "$next_dest/disk-guard.sh" "$work" "$next_log" "$tmp" "${next_env[@]}"
  plutil -lint "$tmp" > /dev/null || die "the rendered plist does not parse"
  if [ "$dry" = 1 ]; then
    echo "install-disk-guard: --alongside --dry-run: nothing is written"
    echo "would write (directory) $next_dest/"
    for f in disk-guard.sh $modules cache-roots.tsv $marker; do echo "would write $next_dest/$f"; done
    echo "would write $plist:"
    sed 's/^/    /' "$tmp"
    echo "would run: launchctl bootout gui/$(id -u)/$next_label   (when it is loaded)"
    echo "would run: launchctl bootstrap gui/$(id -u) $plist"
    echo "not touched: $work/bin/disk-guard.sh, $HOME/Library/LaunchAgents/$main_label.plist, Label $main_label"
    exit 0
  fi
  copy_files "$next_dest"
  printf 'install-disk-guard.sh --alongside %s\n' "$stamp" > "$next_dest/$marker"
  install -d -m 755 "$HOME/Library/LaunchAgents"
  install -m 644 "$tmp" "$plist"
  launchctl bootout "gui/$(id -u)/$next_label" 2> /dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$plist"
  echo "install-disk-guard: installed alongside the old disk-guard, report only"
  echo "  files:     $next_dest/ (disk-guard.sh, $(echo $modules | wc -w | tr -d ' ') modules, cache-roots.tsv, $marker)"
  echo "  plist:     $plist"
  echo "  Label:     $next_label, every 3600 s, first run in an hour: sweep (no --apply)"
  echo "  log:       $next_log"
  echo "  report:    $work/status/disk-guard-next/lifecycle.json    lock: $work/.lifecycle-next.lock"
  echo "  registry:  $next_dest/cache-roots.tsv, then $work/status/cache-roots.tsv if it exists"
  echo "  untouched: $work/bin/disk-guard.sh, $HOME/Library/LaunchAgents/$main_label.plist (Label $main_label)"
  echo "  remove:    bash $here/install-disk-guard.sh --uninstall-alongside"
  exit 0
fi

case "$(uname -s)" in
  Darwin)
    [ -z "$user" ] || die "--user is for Linux; on macOS run it as the user who runs the agents"
    [ "$(id -u)" != 0 ] || die "run it as the user who runs the agents, not root"
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
    plist=$HOME/Library/LaunchAgents/$main_label.plist
    tmp=$(mktemp "${TMPDIR:-/tmp}/disk-guard-plist.XXXXXX")
    trap 'rm -f "$tmp"' EXIT
    render_plist "$main_label" "$dest/disk-guard.sh" "$work" "$work/disk-guard.log" "$tmp"
    plutil -lint "$tmp" > /dev/null || die "the rendered plist does not parse"
    if [ -e "$plist" ] && ! cmp -s "$tmp" "$plist"; then keep_old "$plist"; fi
    do_ install -m 644 "$tmp" "$plist"
    do_ launchctl bootout "gui/$(id -u)/$main_label" 2> /dev/null || true
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
