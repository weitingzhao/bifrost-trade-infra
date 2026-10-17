#!/usr/bin/env bash
# install-secret.sh — put one credential, read from stdin, into an agent user's
# ~/.config/bifrost on the agent host: written to a temporary file there, owned
# by that user, mode 0600, checked non-empty, then moved into place. Run by
# agent-06-owner.sh over SSH (`sudo bash ~/agent-host/install-secret.sh <user>
# <name>`); it never prints the value.
set -euo pipefail

die() {
  echo "install-secret: $*" >&2
  exit 1
}
[ "$(id -u)" = 0 ] || die "run it with sudo"
[ "$#" -eq 2 ] || die "usage: install-secret.sh <user> <name>"
user=$1 name=$2
case "$user" in bifrost-agentd | bifrost-agentd-stg) ;; *) die "not an agent user: $user" ;; esac
case "$user:$name" in
  bifrost-agentd:agentd-git.token | bifrost-agentd:cursor-api.key | bifrost-agentd:claude-oauth.token) ;;
  bifrost-agentd-stg:agentd-git.token) ;;
  *) die "$user does not take $name" ;;
esac
dir=/home/$user/.config/bifrost
[ -d "$dir" ] && [ ! -L "$dir" ] || die "$dir is missing (run prepare-agent-06.sh first)"
[ "$(stat -c %U "$dir")" = "$user" ] || die "$dir is not owned by $user"

tmp=$(sudo -u "$user" mktemp "$dir/.incoming.XXXXXX")
trap 'rm -f "$tmp"' EXIT
# The value goes from stdin straight into the file; a trailing newline from a
# paste or from `cat` of a file that ends in one is dropped.
python3 -c '
import sys
data = sys.stdin.buffer.read()
if data.endswith(b"\n"):
    data = data[:-1]
if data.endswith(b"\r"):
    data = data[:-1]
if not data.strip():
    sys.exit("empty")
if b"\n" in data:
    sys.exit("more than one line")
sys.stdout.buffer.write(data)
' > "$tmp" || die "refused: the value was empty or more than one line"
chown "$user:$user" "$tmp"
chmod 600 "$tmp"
mv -f "$tmp" "$dir/$name"
trap - EXIT
echo "installed $dir/$name ($(stat -c '%U %a %s' "$dir/$name") bytes)"
