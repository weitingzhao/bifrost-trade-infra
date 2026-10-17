#!/usr/bin/env bash
# check-agent-06.sh — what the agent host looks like, for the coordinator to
# read (agent-config/work/multi-agent/CUT-agent-host-06-2026-10-17.md). Read
# only, apart from two short-lived test listeners. It prints no credential:
# credential files by owner, mode and size only; MCP configuration by count
# only; the services by their state, not their logs. Run by agent-06-owner.sh
# `host-check <stage>`:
#
#   sudo bash ~/agent-host/check-agent-06.sh base|creds|running
#
# base: after prepare-agent-06.sh. creds: also every credential in place and
# each CLI logged in. running: also both agentd services up. Exit 0 only when
# every check of the stage passed; each failure is a line with FAIL.
set -uo pipefail

prod=bifrost-agentd
stg=bifrost-agentd-stg
stage=${1:-}
case "$stage" in base | creds | running) ;; *)
  echo "usage: check-agent-06.sh base|creds|running" >&2
  exit 2
  ;;
esac
[ "$(id -u)" = 0 ] || {
  echo "run it with sudo" >&2
  exit 2
}
fails=0
fail() {
  echo "FAIL $*"
  fails=$((fails + 1))
}
ok() { echo "ok   $*"; }

as() {
  local u=$1
  sudo -u "$u" -H env -i HOME="/home/$u" USER="$u" LOGNAME="$u" LANG=C.UTF-8 \
    PATH="/home/$u/.local/bin:/usr/local/go/bin:/usr/local/lib/nodejs/current/bin:/usr/local/bin:/usr/bin:/bin" \
    bash -c "cd \"\$HOME\" && $2"
}

probe_py=$(mktemp /tmp/probe.XXXXXX.py)
chmod 644 "$probe_py"
listener_pid=""
cleanup() {
  [ -n "$listener_pid" ] && kill "$listener_pid" 2>/dev/null
  rm -f "$probe_py"
}
trap cleanup EXIT
cat > "$probe_py" <<'EOF'
# probe.py <tcp|udp-dns> <host> <port>: open / refused / timeout / error:<name>
import errno, socket, sys
proto, host, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
fam = socket.AF_INET6 if ":" in host else socket.AF_INET
try:
    addr = socket.getaddrinfo(host, port, fam, socket.SOCK_STREAM if proto == "tcp" else socket.SOCK_DGRAM)[0][4]
except OSError:
    print("error:resolve"); sys.exit()
s = socket.socket(fam, socket.SOCK_STREAM if proto == "tcp" else socket.SOCK_DGRAM)
s.settimeout(5)
try:
    s.connect(addr)
    if proto == "udp-dns":
        # A query for "." NS: any answer means the packet got through.
        s.send(b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x01")
        s.recv(512)
    print("open")
except ConnectionRefusedError:
    print("refused")
except socket.timeout:
    print("timeout")
except OSError as e:
    print("error:" + errno.errorcode.get(e.errno, str(e.errno)))
EOF

# counters: the packets counted by the reject rules (every counter in the
# common chain is on a reject rule); 0 when the table cannot be read, so a
# missing table fails every "blocked" below.
counters() { nft list chain inet bifrost_agent common 2> /dev/null | grep -o 'packets [0-9]*' | awk '{s += $2} END {print s + 0}'; }

# reach <user> <proto> <host> <port> <open|blocked>: run the probe as the
# user. Wanted open passes only on "open". Wanted blocked passes only when the
# probe ran, did not get through, sent a packet (a name that does not resolve
# sends none), and a reject rule counted a packet while it ran: a reject rule
# drops what it counts. What the probe then reports depends on the kernel,
# not on the rule: refused for TCP, EPERM for UDP, a timeout for TCP over
# IPv6 (all three seen on 06, 2026-10-17). A target that is down without a
# rule counting anything is not proof. The probes run
# only while neither agent user has any other process (no agentd, no CLI
# left over), and one at a time, so the packets the reject counters gain
# during a probe are that probe's own. Root's result (the rules do not touch
# root) is shown alongside.
reach() {
  local u=$1 proto=$2 host=$3 port=$4 want=$5 got base rc before after what
  before=$(counters)
  rc=0
  got=$(as "$u" "python3 -I $probe_py $proto $host $port" 2> /dev/null) || rc=$?
  after=$(counters)
  base=$(python3 -I "$probe_py" "$proto" "$host" "$port" 2> /dev/null)
  what=$(printf '%-19s %-8s %-30s user=%-14s root=%s' "$u" "$proto" "$host:$port" "${got:-?}" "${base:-?}")
  case "$got" in
    open | refused | timeout | error:*) ;;
    *) rc=1 ;;
  esac
  if [ "$rc" != 0 ]; then
    fail "$what (the probe did not run as $u, or said something unexpected)"
  elif [ "$want" = open ]; then
    [ "$got" = open ] && ok "$what (want open)" || fail "$what (want open)"
  elif [ "$got" != error:resolve ] && [ "$after" -gt "$before" ]; then
    ok "$what (want blocked; a reject rule counted it, counts $before -> $after)"
  else
    fail "$what (want blocked; needs a reject rule's count to rise, got $got with counts $before -> $after)"
  fi
}

echo "== host ($stage)"
hostnamectl --static
. /etc/os-release && echo "$PRETTY_NAME, kernel $(uname -r)"
df -h / | tail -1
free -g | sed -n 2p
lan=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')
echo "LAN address: $lan"
[ "$(readlink -f /etc/resolv.conf)" = /run/systemd/resolve/stub-resolv.conf ] && ok "resolv.conf is the systemd-resolved stub" || fail "resolv.conf is $(readlink -f /etc/resolv.conf)"
[ ! -e /usr/local/bin/k3s ] && ! systemctl list-unit-files k3s-agent.service --no-legend 2>/dev/null | grep -q . && ok "k3s is gone" || fail "k3s is still installed"
ip -br link | grep -qE 'flannel|cni0|veth' && fail "flannel, cni or veth interfaces are still there" || ok "no flannel, cni or veth interface"

echo "== logins into this host"
for f in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do
  [ -f "$f" ] || continue
  echo "$f: $(grep -c . "$f") keys, $(grep -c '^command=' "$f") with a forced command; comments: $(awk '{print $NF}' "$f" | tr '\n' ' ')"
done
grep -rhE '^[^#]*NOPASSWD' /etc/sudoers /etc/sudoers.d 2>/dev/null | sed 's/^/sudoers: /'

echo "== agent users"
for u in "$prod" "$stg"; do
  if ! id "$u" >/dev/null 2>&1; then
    fail "$u does not exist"
    continue
  fi
  [ "$(getent passwd "$u" | cut -d: -f6)" = "/home/$u" ] && ok "$u home /home/$u" || fail "$u home is $(getent passwd "$u" | cut -d: -f6)"
  [ "$(id -nG "$u")" = "$u" ] && ok "$u groups: $u only" || fail "$u groups: $(id -nG "$u")"
  [ "$(passwd -S "$u" | awk '{print $2}')" = L ] && ok "$u password locked" || fail "$u password not locked"
  [ ! -e "/home/$u/.ssh" ] && ok "$u has no ~/.ssh" || fail "$u has ~/.ssh"
  grep -rqsw "$u" /etc/sudoers /etc/sudoers.d && fail "$u is named in sudoers" || ok "$u not in sudoers"
  for d in "/home/$u" "/home/$u/.config/bifrost" "/home/$u/agent-work/agentd"; do
    [ "$(stat -c '%U %a' "$d" 2>/dev/null)" = "$u 700" ] && ok "$d $u 700" || fail "$d is $(stat -c '%U %a' "$d" 2>&1)"
  done
done

echo "== credentials (owner, mode, size; never contents)"
cred() { # cred <user> <file> <required|optional>
  local p=/home/$1/.config/bifrost/$2
  if [ ! -e "$p" ] && [ ! -L "$p" ]; then
    [ "$3" = required ] && fail "$p missing" || echo "-    $p not yet"
    return
  fi
  if [ -f "$p" ] && [ ! -L "$p" ] && [ "$(stat -c '%U %a' "$p")" = "$1 600" ] && [ -s "$p" ]; then
    ok "$(stat -c '%n %U %a %s' "$p") bytes"
  else
    fail "$(stat -c '%n %U %a %s %F' "$p")"
  fi
}
cred "$prod" agentd.token required
cred "$stg" agentd.token required
need=optional
[ "$stage" = base ] || need=required
for f in agentd-git.token cursor-api.key claude-oauth.token; do cred "$prod" "$f" "$need"; done
cred "$stg" agentd-git.token "$need"

echo "== egress rules"
systemctl is-enabled --quiet bifrost-agent-egress.service && ok "egress unit enabled" || fail "egress unit not enabled"
systemctl is-active --quiet bifrost-agent-egress.service && ok "egress unit active" || fail "egress unit not active"
nft list table inet bifrost_agent >/dev/null 2>&1 && ok "table inet bifrost_agent loaded" || fail "table inet bifrost_agent not loaded"
cmp -s <(nft -f /etc/bifrost/agent-egress.nft -c 2>&1) /dev/null && ok "/etc/bifrost/agent-egress.nft checks" || fail "/etc/bifrost/agent-egress.nft does not check"
nft list table inet bifrost_agent

echo "-- reachability, each user against root"
if [ "$stage" = running ]; then
  echo "-    not probed in this stage (both agentd run now); the rules are probed by host-check base and creds, which need both stopped"
else
quiet=1
for s in bifrost-agentd bifrost-agentd-stg; do
  st=$(systemctl is-active "$s" 2> /dev/null) || true
  case "$st" in
    inactive | failed | unknown) ;;
    *)
      fail "$s is $st: stop it before this check, or the probes cannot be told from its traffic"
      quiet=0
      ;;
  esac
done
for u in "$prod" "$stg"; do
  rc=0
  pids=$(pgrep -u "$u") || rc=$?
  case $rc in
    1) ;;
    0)
      fail "$u has process(es) running ($(echo "$pids" | tr '\n' ' ')): none may run during the probes"
      quiet=0
      ;;
    *)
      fail "cannot tell whether $u has processes (pgrep exit $rc)"
      quiet=0
      ;;
  esac
done
if [ "$quiet" != 1 ]; then
  echo "-    reachability not probed (see the failures above)"
else
dev=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "dev") print $(i + 1)}')
port=$((20000 + RANDOM % 20000))
python3 -I -c "
import socket, time
s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('0.0.0.0', $port)); s.listen(8); s.settimeout(1)
end = time.time() + 120
while time.time() < end:
    try: s.accept()[0].close()
    except OSError: pass
" &
listener_pid=$!
sleep 1
for u in "$prod" "$stg"; do
  if [ "$u" = "$prod" ]; then
    reach "$u" tcp 192.168.10.100 30876 open
    reach "$u" tcp 192.168.10.73 30878 blocked
  else
    reach "$u" tcp 192.168.10.73 30878 open
    reach "$u" tcp 192.168.10.100 30876 blocked
  fi
  reach "$u" tcp 192.168.10.73 30300 open
  reach "$u" tcp 127.0.0.1 "$port" open
  reach "$u" tcp "$lan" "$port" blocked
  reach "$u" tcp 127.0.0.1 22 blocked
  reach "$u" tcp "$lan" 22 blocked
  reach "$u" tcp 192.168.10.73 22 blocked
  reach "$u" tcp 192.168.10.73 6443 blocked
  reach "$u" tcp 192.168.10.73 30500 blocked
  reach "$u" tcp 192.168.10.100 443 blocked
  reach "$u" tcp 192.168.10.20 445 blocked
  reach "$u" tcp 192.168.10.20 2049 blocked
  reach "$u" tcp 192.168.10.1 443 blocked
  reach "$u" udp-dns 127.0.0.53 53 open
  reach "$u" udp-dns 1.1.1.1 53 blocked
  if [ "$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6 2> /dev/null)" = 1 ]; then
    ok "$u IPv6 is switched off on this host"
  else
    # A link-local address needs no route, so the packet always reaches the
    # output hook (a global one would fail at route lookup on a host without
    # an IPv6 route, and prove nothing).
    reach "$u" tcp "fe80::1%$dev" 443 blocked
  fi
  reach "$u" tcp github.com 443 open
  reach "$u" tcp github.com 22 blocked
  reach "$u" tcp registry.npmjs.org 443 open
  reach "$u" tcp proxy.golang.org 443 open
  reach "$u" tcp api.openai.com 443 open
  reach "$u" tcp chatgpt.com 443 open
done
reach "$prod" tcp api.anthropic.com 443 open
reach "$prod" tcp api2.cursor.sh 443 open
kill "$listener_pid" 2>/dev/null
listener_pid=""
fi
fi

echo "== listeners on this host (for B6: local services the agent users could reach over loopback or a Unix socket)"
ss -H -ltnup | awk '{print $1, $5, $7}'
echo "unix sockets listening: $(ss -H -lx | wc -l); paths:"
ss -H -lx | awk '{print $5}' | sort -u | head -60

echo "== tools"
/usr/local/go/bin/go version 2>&1
/usr/local/lib/nodejs/current/bin/node -v 2>&1
git --version
[ "$(sha256sum /usr/local/libexec/bifrost/agentd 2>/dev/null | cut -d' ' -f1)" = "$(cut -d' ' -f1 "$(dirname "$0")/agentd.sha256")" ] && ok "agentd matches agentd.sha256" || fail "agentd does not match agentd.sha256"
for c in codex claude cursor-agent; do
  v=$(as "$prod" ".local/bin/$c --version 2>/dev/null | head -1") && [ -n "$v" ] && ok "$prod $c $v" || fail "$prod $c does not run"
done
v=$(as "$stg" ".local/bin/codex --version 2>/dev/null | head -1") && [ -n "$v" ] && ok "$stg codex $v" || fail "$stg codex does not run"

echo "== vendor logins and MCP (none wanted; counts only)"
for u in "$prod" "$stg"; do
  if as "$u" ".local/bin/codex login status >/dev/null 2>&1"; then
    ok "$u codex logged in"
  elif [ "$stage" = base ]; then
    echo "-    $u codex not logged in yet"
  else
    fail "$u codex not logged in"
  fi
  n=$(as "$u" ".local/bin/codex mcp list --json 2>/dev/null" | python3 -I -c 'import json, sys; print(len(json.load(sys.stdin)))' 2>/dev/null)
  [ "$n" = 0 ] && ok "$u codex MCP servers: 0" || fail "$u codex MCP servers: ${n:-unreadable} (look at it on the host)"
done
if as "$prod" ".local/bin/claude mcp list 2>/dev/null" | grep -q 'No MCP servers configured'; then
  ok "$prod claude MCP servers: none"
else
  fail "$prod claude MCP servers: not none (look at it on the host)"
fi
for u in "$prod" "$stg"; do
  [ ! -e "/home/$u/.cursor/mcp.json" ] && ok "$u has no ~/.cursor/mcp.json" || fail "$u has ~/.cursor/mcp.json"
done

echo "== agentd services"
for s in bifrost-agentd bifrost-agentd-stg; do
  echo "$s: enabled=$(systemctl is-enabled "$s" 2>&1) $(systemctl show "$s" -p ActiveState -p SubState -p NRestarts -p ExecMainStatus | tr '\n' ' ')"
  if [ "$stage" = running ]; then
    pid=$(systemctl show "$s" -p MainPID --value)
    want=$prod
    [ "$s" = bifrost-agentd-stg ] && want=$stg
    systemctl is-active --quiet "$s" && [ "$(ps -o uid= -p "$pid" 2>/dev/null | tr -d ' ')" = "$(id -u "$want")" ] && ok "$s running as $want" || fail "$s not running as $want"
  fi
done

echo "== summary: $fails failed"
[ "$fails" -eq 0 ]
