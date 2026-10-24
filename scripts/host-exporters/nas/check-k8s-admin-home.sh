#!/usr/bin/env bash
# check-k8s-admin-home.sh <expected key fingerprint> check|fix [home] [user]
#
# TD-433 / review 540 A1: /home/k8s_admin has been 777, so any NAS account could have
# left a shell or ssh startup file there, or replaced .ssh. Logging in as k8s_admin
# would run such a file before any command. So this runs as root from the Owner's own
# admin session (Wzhao, whose home is 700), via `host-exporters.sh nas-home`, and never
# loads anything from the home it inspects.
#
#   check  read only: list the home, its startup files and .ssh (owner, mode, time),
#          the authorized keys' fingerprints; exit 3 at anything suspicious
#   fix    the same check; only when it is clean, chmod 700 the home, then check again
#          (a file planted between the check and the chmod is caught there)
#
# Suspicious, and nothing is changed: the home or .ssh is a link or not a directory; an
# entry in the home is not owned by the user; any of .bashrc .bash_profile .bash_login
# .profile .bash_logout .inputrc .pam_environment .ssh/rc .ssh/environment
# .ssh/authorized_keys2 exists; .ssh or authorized_keys is not the user's, or is
# writable by group or others; a key other than the expected one is authorized, or a
# key line carries options (command=..., environment=...).
# Exit 0 clean (fix: and now 700), 3 suspicious, 2 usage, 1 other error.
# home and user default to /home/k8s_admin and k8s_admin; the tests pass their own.
set -euo pipefail

fp_expected=${1:-}
mode=${2:-}
home=${3:-/home/k8s_admin}
user=${4:-k8s_admin}
[[ $fp_expected == SHA256:* && ( $mode == check || $mode == fix ) ]] \
  || { echo "usage: check-k8s-admin-home.sh SHA256:<fingerprint> check|fix [home] [user]" >&2; exit 2; }

# owner name, octal mode, modification time; GNU stat on the NAS, BSD stat in the tests
if stat -c '%U' / >/dev/null 2>&1; then
  owner() { stat -c '%U' "$1"; }; perm() { stat -c '%a' "$1"; }; when() { stat -c '%y' "$1"; }
else
  owner() { stat -f '%Su' "$1"; }; perm() { stat -f '%Lp' "$1"; }; when() { stat -f '%Sm' "$1"; }
fi
show() { printf '    %s %s %s  %s\n' "$(perm "$1")" "$(owner "$1")" "$(when "$1")" "$1"; }

suspicious=0
flag() { echo "SUSPICIOUS: $*"; suspicious=1; }
writable_by_others() { (( (8#$(perm "$1") & 8#022) != 0 )); }

STARTUP=(.bashrc .bash_profile .bash_login .profile .bash_logout .inputrc .pam_environment
         .ssh/rc .ssh/environment .ssh/authorized_keys2)

inspect() {
  if [[ -L $home || ! -d $home ]]; then flag "$home is a link or not a directory"; return; fi
  echo "==> $home"
  show "$home"
  [[ $(owner "$home") == "$user" ]] || flag "$home is owned by $(owner "$home"), not $user"

  echo "==> every entry in it (none may belong to another account)"
  local e
  shopt -s nullglob dotglob
  for e in "$home"/*; do
    show "$e"
    [[ $(owner "$e") == "$user" ]] || flag "$e is owned by $(owner "$e"), not $user"
  done
  shopt -u nullglob dotglob

  echo "==> startup files (none expected)"
  local f any=0
  for f in "${STARTUP[@]}"; do
    if [[ -e $home/$f || -L $home/$f ]]; then any=1; show "$home/$f"; flag "$home/$f exists: it runs at login"; fi
  done
  [[ $any == 1 ]] || echo "    none"

  echo "==> .ssh"
  local ssh=$home/.ssh keys=$home/.ssh/authorized_keys
  if [[ -L $ssh || ! -d $ssh ]]; then flag "$ssh is a link or not a directory"; return; fi
  show "$ssh"
  [[ $(owner "$ssh") == "$user" ]] || flag "$ssh is owned by $(owner "$ssh")"
  writable_by_others "$ssh" && flag "$ssh can be written by its group or others"
  if [[ -L $keys || ! -f $keys ]]; then flag "$keys is a link or not a file"; return; fi
  show "$keys"
  [[ $(owner "$keys") == "$user" ]] || flag "$keys is owned by $(owner "$keys")"
  writable_by_others "$keys" && flag "$keys can be written by its group or others"
  echo "==> authorized keys (expected: $fp_expected only)"
  local line fp n=0
  while read -r line; do
    [[ -n $line ]] || continue
    n=$((n + 1))
    fp=$(awk '{print $2}' <<<"$line")
    echo "    $line"
    [[ $fp == "$fp_expected" ]] || flag "authorized key $fp is not the expected one"
  done < <(ssh-keygen -lf "$keys" 2>&1 || true)
  [[ $n -ge 1 ]] || flag "no key could be read from $keys"
  # A key line with options (command="...", environment=...) runs something at login.
  if grep -v -E '^[[:space:]]*(#|$)' "$keys" | grep -v -E '^(ssh-|ecdsa-|sk-)' >/dev/null; then
    flag "$keys has a key line with options in front of it"
  fi
  return 0
}

inspect
if [[ $suspicious == 1 ]]; then
  echo "stop: something above is suspicious; nothing was changed. Do not log in as $user; tell the coordinator."
  exit 3
fi
if [[ $mode == check ]]; then
  echo "clean: nothing suspicious (read only, nothing changed)"
  exit 0
fi

echo "==> chmod 700 $home"
chmod 700 "$home"
show "$home"
echo "==> check again"
inspect
if [[ $suspicious == 1 ]]; then
  echo "stop: something appeared between the check and the chmod; the home is 700 now, nothing else was changed. Do not log in as $user; tell the coordinator."
  exit 3
fi
[[ $(perm "$home") == 700 ]] || { echo "check-k8s-admin-home: $home is $(perm "$home") after chmod" >&2; exit 1; }
echo "check-k8s-admin-home: OK ($home is 700, nothing suspicious)"
