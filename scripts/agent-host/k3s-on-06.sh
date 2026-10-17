#!/usr/bin/env bash
# k3s-on-06.sh — run on ubt-k3s-06 as root, fed over SSH on stdin by
# agent-06-owner.sh (it is not on 06 yet when it is needed):
#
#   ssh … 'sudo bash -s -- gone' < k3s-on-06.sh
#       exit 0: k3s is gone; 1: some of it is still there (each part named);
#       2: could not tell
#   ssh … 'sudo bash -s -- uninstall' < k3s-on-06.sh
#       uninstall k3s if it is still installed, show that it is gone, then
#       schedule a reboot in 5 seconds (so this returns cleanly first)
#
# "Gone" is decided from what is there, never from a query that failed: the
# binary, the two units by their load state, and every process by the file
# it runs (/proc/<pid>/exe, which also names a deleted binary) and by its
# name, so a k3s started without a path is found as well.
set -uo pipefail

[ "$(id -u)" = 0 ] || {
  echo "k3s-on-06: run as root" >&2
  exit 2
}
[ "$(hostname)" = ubt-k3s-06 ] || {
  echo "k3s-on-06: this is $(hostname), not ubt-k3s-06" >&2
  exit 2
}

gone() {
  local left=0 seen=0 u state p exe comm
  if [ -e /usr/local/bin/k3s ] || [ -L /usr/local/bin/k3s ]; then
    echo "still there: /usr/local/bin/k3s"
    left=1
  fi
  for u in k3s-agent.service k3s.service; do
    state=$(systemctl show -p LoadState --value "$u") || {
      echo "k3s-on-06: cannot ask systemd about $u" >&2
      return 2
    }
    case "$state" in
      not-found) ;;
      "")
        echo "k3s-on-06: systemd gave no load state for $u" >&2
        return 2
        ;;
      *)
        echo "still there: $u ($state)"
        left=1
        ;;
    esac
  done
  for p in /proc/[0-9]*; do
    seen=$((seen + 1))
    # A process that ended meanwhile, or a kernel thread, has no exe link.
    exe=$(readlink "$p/exe" 2> /dev/null) || exe=""
    comm=$(cat "$p/comm" 2> /dev/null) || comm=""
    case "$exe" in
      /usr/local/bin/k3s* | /var/lib/rancher/k3s/*)
        echo "still running: pid ${p#/proc/} runs $exe"
        left=1
        continue
        ;;
    esac
    case "$comm" in
      k3s | k3s-agent | k3s-server | k3s-init)
        echo "still running: pid ${p#/proc/} named $comm"
        left=1
        ;;
    esac
  done
  [ "$seen" -gt 10 ] || {
    echo "k3s-on-06: cannot read /proc" >&2
    return 2
  }
  [ "$left" = 0 ] && echo "k3s is gone from $(hostname)"
  return "$left"
}

case "${1:-}" in
  gone)
    gone
    exit $?
    ;;
  uninstall)
    if [ -x /usr/local/bin/k3s-agent-uninstall.sh ]; then
      /usr/local/bin/k3s-agent-uninstall.sh || {
        echo "k3s-on-06: the uninstall script failed" >&2
        exit 1
      }
    fi
    gone
    rc=$?
    [ "$rc" = 0 ] || exit "$rc"
    systemd-run --quiet --on-active=5 --unit=agent06-reboot systemctl reboot || {
      echo "k3s-on-06: could not schedule the reboot" >&2
      exit 1
    }
    echo "rebooting in 5 seconds"
    ;;
  *)
    echo "usage: k3s-on-06.sh gone|uninstall" >&2
    exit 2
    ;;
esac
