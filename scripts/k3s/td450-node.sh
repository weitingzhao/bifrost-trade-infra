#!/usr/bin/env bash
# TD-450, runs on one K3s agent as root (td450-rotate-token.sh copies and starts it). Prints no token.
#   check    the kind of token k3s-agent starts with, and leftover join files
#   apply    replace K3S_TOKEN with the agent token from ~vision/.td450-agent-token, restart k3s-agent
#   cleanup  remove the env backup and leftover ~/.join-env files (they hold the old token)
# Restarting k3s-agent leaves running containers alone (the unit kills only the k3s process).
set -euo pipefail
f=/etc/systemd/system/k3s-agent.service.env
src=/home/vision/.td450-agent-token
umask 077

kind() {
  case "$1" in
    "") echo "none" ;;
    K10*::server:*) echo "SERVER token (cluster-admin)" ;;
    K10*::node:*) echo "agent token" ;;
    *.*) echo "bootstrap token" ;;
    *) echo "other format" ;;
  esac
}
current() { sed -n 's/^K3S_TOKEN=["'"'"']*\([^"'"'"']*\)["'"'"']*$/\1/p' "$f" 2>/dev/null | head -1; }

case "${1:-}" in
  check)
    [ -f "$f" ] || { echo "no $f (not a k3s agent)"; exit 0; }
    echo "k3s-agent starts with: $(kind "$(current)")"
    systemctl is-active k3s-agent | sed 's/^/k3s-agent: /'
    grep -lsE '^token:' /etc/rancher/k3s/config.yaml /etc/rancher/k3s/config.yaml.d/*.yaml 2>/dev/null | sed 's/^/config sets a token: /' || true
    for h in /home/*/.join-env /root/.join-env; do [ -f "$h" ] && echo "leftover: $h"; done
    true ;;
  apply)
    [ -f "$f" ] || { echo "STOP: no $f"; exit 1; }
    t=$(head -1 "$src")
    rm -f "$src"
    case "$t" in K10*::node:*) ;; *) echo "STOP: what came over is not an agent token"; exit 1 ;; esac
    if grep -lsqE '^token:' /etc/rancher/k3s/config.yaml /etc/rancher/k3s/config.yaml.d/*.yaml 2>/dev/null; then
      echo "STOP: a k3s config file sets token: on this node; OWNER-STEPS §5"; exit 1
    fi
    [ -e "$f.bak-td450" ] || cp -p "$f" "$f.bak-td450"
    grep -v '^K3S_TOKEN=' "$f" > "$f.new" || true
    printf 'K3S_TOKEN="%s"\n' "$t" >> "$f.new"
    unset t
    chmod 600 "$f.new"
    mv "$f.new" "$f"
    echo "k3s-agent now starts with: $(kind "$(current)")"
    systemctl restart k3s-agent
    for _ in $(seq 1 30); do systemctl is-active --quiet k3s-agent && break; sleep 2; done
    systemctl is-active k3s-agent | sed 's/^/k3s-agent: /' ;;
  cleanup)
    rm -f "$f.bak-td450"
    for h in /home/*/.join-env /root/.join-env; do rm -f "$h"; done
    echo "cleaned" ;;
  *) echo "usage: $0 check | apply | cleanup"; exit 2 ;;
esac
