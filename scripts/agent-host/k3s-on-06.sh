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
# name, so a k3s started without a path is found as well. A process whose
# file or name cannot be read is skipped only when it has ended meanwhile, is
# a zombie or is a kernel thread; any other one makes the answer "cannot tell".
set -uo pipefail

[ "$(id -u)" = 0 ] || {
  echo "k3s-on-06: run as root" >&2
  exit 2
}
[ "$(hostname)" = ubt-k3s-06 ] || {
  echo "k3s-on-06: this is $(hostname), not ubt-k3s-06" >&2
  exit 2
}

PROC=${K3S_ON_06_PROC:-/proc} # another directory only in the tests (sudo drops the variable)

# unreadable_ok <proc dir>: the exe link could not be read; true when the
# process has ended, is a zombie, or is a kernel thread (PF_KTHREAD).
unreadable_ok() {
  local st rest
  [ -d "$1" ] || return 0
  st=$(cat "$1/stat" 2> /dev/null) || { [ -d "$1" ] && return 1; return 0; }
  rest=${st##*) }
  set -- $rest
  [ "${1:-}" = Z ] && return 0
  [ -n "${7:-}" ] && [ $((${7} & 0x00200000)) != 0 ]
}

# proc_field <proc dir> exe|comm: print what the process runs, or its name.
# Exit 0: printed. 3: the process may be skipped (it ended, is a zombie or a
# kernel thread). 2: a live process whose field could not be read, after one
# retry; the caller cannot tell then.
proc_field() {
  local try out
  for try in 1 2; do
    if [ "$2" = exe ]; then
      out=$(readlink "$1/exe" 2> /dev/null) && {
        printf '%s' "$out"
        return 0
      }
    else
      out=$(cat "$1/comm" 2> /dev/null) && {
        printf '%s' "$out"
        return 0
      }
    fi
    unreadable_ok "$1" && return 3
    [ "$try" = 2 ] || sleep 0.2
  done
  return 2
}

gone() {
  local left=0 seen=0 u state p exe comm rc
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
  for p in "$PROC"/[0-9]*; do
    seen=$((seen + 1))
    rc=0
    exe=$(proc_field "$p" exe) || rc=$?
    case $rc in
      0) ;;
      3) continue ;;
      *)
        echo "k3s-on-06: cannot read what pid ${p##*/} runs" >&2
        return 2
        ;;
    esac
    case "$exe" in
      /usr/local/bin/k3s* | /var/lib/rancher/k3s/*)
        echo "still running: pid ${p##*/} runs $exe"
        left=1
        continue
        ;;
    esac
    # Its name catches a k3s that runs from anywhere else; a name that cannot
    # be read is "cannot tell", the same as an unreadable exe.
    rc=0
    comm=$(proc_field "$p" comm) || rc=$?
    case $rc in
      0) ;;
      3) continue ;;
      *)
        echo "k3s-on-06: cannot read the name of pid ${p##*/}" >&2
        return 2
        ;;
    esac
    case "$comm" in
      k3s | k3s-agent | k3s-server | k3s-init)
        echo "still running: pid ${p##*/} named $comm (runs $exe)"
        left=1
        ;;
    esac
  done
  [ "$seen" -gt 10 ] || {
    echo "k3s-on-06: cannot read $PROC" >&2
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
