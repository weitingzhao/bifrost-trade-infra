#!/usr/bin/env bash
# secure-dir.sh <uid> <path> — is <path> safe to keep configuration that root runs?
#
# Exit 0 when <path> and every directory above it, up to /, exists, is not a symbolic
# link, is owned by root or by <uid>, and cannot be written by its group or by others.
# Otherwise print the first component that fails and exit 1. install-nas.sh calls it with
# uid 0 (root only) before it writes and again before it runs compose, so no other
# account can rename a directory on the way to the compose file and put its own in its
# place (review 537 A1: /volume1/docker is 777). The tests call it with their own uid.
#
# Strict on purpose: a sticky world-writable directory (like /tmp) is refused too.
set -euo pipefail

uid=${1:-}
path=${2:-}
[[ $uid =~ ^[0-9]+$ && $path == /* ]] || { echo "usage: secure-dir.sh <uid> <absolute path>" >&2; exit 2; }

# owner uid and mode bits of $1 without following a link (GNU stat on the NAS, BSD stat on a Mac)
owner_mode() {
  if stat -c '%u %a' / >/dev/null 2>&1; then stat -c '%u %a' "$1"; else stat -f '%u %Lp' "$1"; fi
}

p=$path
while :; do
  if [[ -L $p ]]; then echo "secure-dir: $p is a symbolic link" >&2; exit 1; fi
  if [[ ! -e $p ]]; then echo "secure-dir: $p does not exist" >&2; exit 1; fi
  read -r owner mode <<<"$(owner_mode "$p")"
  if [[ $owner != 0 && $owner != "$uid" ]]; then
    echo "secure-dir: $p is owned by uid $owner (allowed: 0 or $uid)" >&2; exit 1
  fi
  if (( (8#$mode & 8#022) != 0 )); then
    echo "secure-dir: $p (mode $mode) can be written by its group or by others" >&2; exit 1
  fi
  [[ $p == / ]] && break
  p=$(dirname "$p")
done
