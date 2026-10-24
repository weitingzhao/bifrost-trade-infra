#!/usr/bin/env bash
# prepare-dir.sh <uid> <trusted root> <dir> — make sure <dir> exists and is safe, without
# taking over anything that is already there (review 540 A1 P2).
#
# <trusted root> must already pass secure-dir.sh. Then each directory from below it down
# to <dir>, in order:
#   - exists: it must pass secure-dir.sh as it is. If not, stop with exit 1 and change
#     nothing: no chown, no chmod, nothing below it is created.
#   - missing: mkdir with mode 0755 (owned by whoever runs this: root on the NAS), and
#     check it with secure-dir.sh right after.
# install-nas.sh calls it as root with uid 0, /volume1 and /volume1/@bifrost/host-exporters;
# the tests call it with their own uid under a private temp directory.
set -euo pipefail

uid=${1:-}
root=${2:-}
dir=${3:-}
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
[[ $uid =~ ^[0-9]+$ && $root == /* && $dir == "$root"/* ]] \
  || { echo "usage: prepare-dir.sh <uid> <absolute trusted root> <dir below it>" >&2; exit 2; }
secure() { bash "$HERE/secure-dir.sh" "$uid" "$1"; }

secure "$root" || { echo "prepare-dir: the trusted root $root is not safe; nothing changed" >&2; exit 1; }

p=$root
IFS=/ read -r -a parts <<<"${dir#"$root"/}"
for part in "${parts[@]}"; do
  [[ -n $part ]] || continue
  p=$p/$part
  if [[ -e $p || -L $p ]]; then
    if ! secure "$p"; then
      echo "prepare-dir: $p already exists and is not safe; refusing, nothing changed" >&2
      exit 1
    fi
    [[ -d $p ]] || { echo "prepare-dir: $p exists and is not a directory; refusing, nothing changed" >&2; exit 1; }
  else
    mkdir -m 0755 "$p"
    secure "$p" || { echo "prepare-dir: $p was just created but does not check out" >&2; exit 1; }
    echo "prepare-dir: created $p"
  fi
done
