#!/usr/bin/env bash
# install-secret.sh — put one credential, read from stdin, into an agent user's
# ~/.config/bifrost on the agent host. Run by agent-06-owner.sh over SSH:
#
#   sudo bash ~/agent-host/install-secret.sh <user> <name> <bytes> <sha256>
#
# The sender reads the whole value first and sends its length and SHA-256
# along (neither is secret). Here the value goes into a temporary file in the
# target directory; only when its length and checksum match, and it has the
# shape of that kind of credential, does it replace the old one (owned by the
# user, mode 0600, one rename). Anything else leaves the old value as it was.
# It never prints the value.
set -euo pipefail

die() {
  echo "install-secret: $*" >&2
  exit 1
}
[ "$(id -u)" = 0 ] || die "run it with sudo"
[ "$#" -eq 4 ] || die "usage: install-secret.sh <user> <name> <bytes> <sha256>"
user=$1 name=$2 bytes=$3 sum=$4
case "$user" in bifrost-agentd | bifrost-agentd-stg) ;; *) die "not an agent user: $user" ;; esac
case "$user:$name" in
  bifrost-agentd:agentd-git.token | bifrost-agentd:cursor-api.key | bifrost-agentd:claude-oauth.token) ;;
  bifrost-agentd-stg:agentd-git.token) ;;
  *) die "$user does not take $name" ;;
esac
[[ $bytes =~ ^[0-9]{1,4}$ ]] || die "bad length"
[[ $sum =~ ^[0-9a-f]{64}$ ]] || die "bad checksum"
dir=/home/$user/.config/bifrost
[ -d "$dir" ] && [ ! -L "$dir" ] || die "$dir is missing (run prepare-agent-06.sh first)"
[ "$(stat -c %U "$dir")" = "$user" ] || die "$dir is not owned by $user"

tmp=$(sudo -u "$user" mktemp "$dir/.incoming.XXXXXX")
trap 'rm -f "$tmp"' EXIT
cat > "$tmp"
[ "$(stat -c %s "$tmp")" = "$bytes" ] || die "refused: the value did not arrive whole (length differs); the old one is kept"
[ "$(sha256sum "$tmp" | cut -d' ' -f1)" = "$sum" ] || die "refused: the value did not arrive whole (checksum differs); the old one is kept"
# The same shapes as agent-06-owner.sh checks before it sends.
python3 -I -c '
import re, sys
shapes = {
    "agentd-git.token": rb"[0-9a-f]{40}",
    "claude-oauth.token": rb"sk-ant-[A-Za-z0-9_-]{20,500}",
    "cursor-api.key": rb"[\x21-\x7e]{20,500}",
}
sys.exit(0 if re.fullmatch(shapes[sys.argv[2]], open(sys.argv[1], "rb").read()) else 1)
' "$tmp" "$name" || die "refused: the value does not look like a $name; the old one is kept"
chown "$user:$user" "$tmp"
chmod 600 "$tmp"
mv -f "$tmp" "$dir/$name"
trap - EXIT
echo "installed $dir/$name ($(stat -c '%U %a %s' "$dir/$name") bytes)"
