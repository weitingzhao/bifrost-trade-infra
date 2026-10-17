#!/usr/bin/env bash
# check-agent-06.sh — what the agent host looks like, for the coordinator to
# read (agent-config/work/multi-agent/CUT-agent-host-06-2026-10-17.md). Read
# only; prints no credential (file modes and sizes, never contents). The Owner
# runs it from his Mac and keeps the output in a file:
#
#   ssh … vision@192.168.10.79 'sudo bash ~/agent-host/check-agent-06.sh' > /tmp/agent-06-check.txt 2>&1
set -uo pipefail

prod=bifrost-agentd
stg=bifrost-agentd-stg
[ "$(id -u)" = 0 ] || {
  echo "run it with sudo" >&2
  exit 2
}

as() {
  local u=$1
  shift
  sudo -u "$u" -H env -i HOME="/home/$u" USER="$u" LOGNAME="$u" LANG=C.UTF-8 \
    PATH="/home/$u/.local/bin:/usr/local/go/bin:/usr/local/lib/nodejs/current/bin:/usr/local/bin:/usr/bin:/bin" \
    bash -c 'cd "$HOME" && eval "$1"' bash "$*"
}
# tcp <user> <host> <port> <want>: can that user open a TCP connection?
tcp() {
  local got=closed
  as "$1" "timeout 5 bash -c 'exec 3<>/dev/tcp/$2/$3'" 2>/dev/null && got=open
  printf '%-20s %-26s %-6s want %-6s %s\n' "$1" "$2:$3" "$got" "$4" "$([ "$got" = "$4" ] && echo ok || echo MISMATCH)"
}

echo "== host"
hostnamectl --static
. /etc/os-release && echo "$PRETTY_NAME, kernel $(uname -r)"
df -h / | tail -1
free -g | sed -n 2p
echo "resolv.conf -> $(readlink -f /etc/resolv.conf)"

echo "== k3s is gone"
ls /usr/local/bin/k3s* 2>&1
systemctl is-active k3s-agent 2>&1
ip -br link | grep -E 'flannel|cni|veth' || echo "no flannel, cni or veth interface"

echo "== logins into this host"
for f in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do
  [ -f "$f" ] || continue
  echo "$f: $(grep -c . "$f") keys, $(grep -c '^command=' "$f") forced-command; comments: $(awk '{print $NF}' "$f" | tr '\n' ' ')"
done
grep -rhE '^[^#]*NOPASSWD' /etc/sudoers /etc/sudoers.d 2>/dev/null | sed 's/^/sudoers: /'

echo "== agent users"
for u in "$prod" "$stg"; do
  id "$u"
  passwd -S "$u"
  stat -c '%n %U:%G %a' "/home/$u" "/home/$u/.config/bifrost" "/home/$u/agent-work/agentd" 2>&1
  ls -A "/home/$u/.ssh" 2>/dev/null && echo "MISMATCH: $u has ~/.ssh"
  for f in agentd.token agentd-git.token cursor-api.key claude-oauth.token; do
    p="/home/$u/.config/bifrost/$f"
    [ -e "$p" ] && stat -c "%n %U %a %s bytes" "$p"
  done
done

echo "== egress rules"
systemctl is-enabled bifrost-agent-egress.service
systemctl is-active bifrost-agent-egress.service
nft list table inet bifrost_agent
echo "-- probes (each as the user)"
for u in "$prod" "$stg"; do
  if [ "$u" = "$prod" ]; then
    tcp "$u" 192.168.10.100 30876 open
    tcp "$u" 192.168.10.73 30878 closed
  else
    tcp "$u" 192.168.10.73 30878 open
    tcp "$u" 192.168.10.100 30876 closed
  fi
  tcp "$u" 192.168.10.73 30300 open
  tcp "$u" 192.168.10.73 6443 closed
  tcp "$u" 192.168.10.73 22 closed
  tcp "$u" 192.168.10.70 22 closed
  tcp "$u" 127.0.0.1 22 closed
  tcp "$u" 192.168.10.100 443 closed
  tcp "$u" 192.168.10.73 30500 closed
  tcp "$u" 192.168.10.20 445 closed
  tcp "$u" 192.168.10.20 2049 closed
  tcp "$u" 192.168.10.1 443 closed
  tcp "$u" 1.1.1.1 53 closed
  tcp "$u" github.com 443 open
  tcp "$u" registry.npmjs.org 443 open
  tcp "$u" api.openai.com 443 open
  tcp "$u" github.com 22 closed
done

echo "== tools"
/usr/local/go/bin/go version 2>&1
/usr/local/lib/nodejs/current/bin/node -v 2>&1
git --version
sha256sum /usr/local/libexec/bifrost/agentd 2>&1
as "$prod" 'for c in codex claude cursor-agent; do printf "%s: " "$c"; "$c" --version 2>&1 | head -1; done'
as "$stg" 'printf "codex: "; codex --version 2>&1 | head -1'

echo "== vendor logins and MCP (none wanted)"
as "$prod" 'codex login status 2>&1 | head -2; printf "codex mcp: "; codex mcp list --json 2>&1 | head -c 200; echo; printf "claude mcp: "; claude mcp list 2>&1 | head -3; ls -A .cursor 2>/dev/null | sed "s/^/.cursor: /"'
as "$stg" 'codex login status 2>&1 | head -2; printf "codex mcp: "; codex mcp list --json 2>&1 | head -c 200; echo'

echo "== agentd services"
for s in bifrost-agentd bifrost-agentd-stg; do
  echo "$s: $(systemctl is-enabled "$s" 2>&1) $(systemctl is-active "$s" 2>&1)"
  # Long runs of letters and digits are cut, in case a line ever carries one.
  journalctl -u "$s" -n 15 --no-pager -o short-iso 2>&1 | sed -E 's/[A-Za-z0-9_-]{32,}/<cut>/g'
done
echo "== end"
