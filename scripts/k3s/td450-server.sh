#!/usr/bin/env bash
# TD-450, runs on ubt-k3s-01 as root (td450-rotate-token.sh copies and starts it). Prints no token.
#   check   what the server holds, read-only
#   rotate  snapshot, rotate the server token, set a separate agent token, restart k3s, verify
#   list    bootstrap tokens still valid
#   forget-old  (7 days later) delete the pre-td450 snapshot and the old token copy
set -euo pipefail
d=/var/lib/rancher/k3s/server
drop=/etc/rancher/k3s/config.yaml.d/50-td450-tokens.yaml
umask 077

# The server's own join check: basic auth "server:<password>" on the server bootstrap route.
probe() { curl -sk -o /dev/null -w '%{http_code}' -u "server:${1##*:}" https://127.0.0.1:6443/v1-k3s/server-bootstrap; }

case "${1:-}" in
  check)
    k3s --version | head -1
    if [ -L $d/agent-token ]; then echo "agent-token: link to the server token (no separate agent token yet)"; else echo "agent-token: separate file"; fi
    ls /etc/rancher/k3s/config.yaml.d/ 2>/dev/null | sed 's/^/config.yaml.d: /' || true
    grep -c '^K3S_TOKEN=' /etc/systemd/system/k3s.service.env 2>/dev/null | sed 's/^/k3s.service.env K3S_TOKEN lines: /' || true
    grep -nE '^(token|agent-token):' /etc/rancher/k3s/config.yaml 2>/dev/null | cut -d: -f1-2 | sed 's/^/config.yaml has: /' || true
    echo "probe with the current token: $(probe "$(cat $d/token)") (want 200)"
    # Only each token's id: a live bootstrap token printed whole would land in a pasted transcript.
    k3s token list | awk 'NR==1{print;next}{sub(/\.[^ ]*/, ".<hidden>", $1); print}' || true ;;
  rotate)
    [ -e "$drop" ] && { echo "STOP: $drop exists: rotation already ran"; exit 1; }
    if grep -qE '^(token|agent-token):' /etc/rancher/k3s/config.yaml 2>/dev/null || grep -q '^K3S_TOKEN=' /etc/systemd/system/k3s.service.env 2>/dev/null; then
      echo "STOP: the server already sets a token in config.yaml or k3s.service.env; OWNER-STEPS §5"; exit 1
    fi
    old=$(cat $d/token)
    case "$old" in K10*::server:*) ;; *) echo "STOP: $d/token is not in the secure server format"; exit 1 ;; esac
    [ "$(probe "$old")" = 200 ] || { echo "STOP: the probe does not accept the current token (no positive control)"; exit 1; }
    k3s etcd-snapshot save --name pre-td450 >/dev/null
    printf '%s\n' "$old" > /root/k3s-old-server-token
    echo "snapshot pre-td450 saved; snapshots up to now restore only with the OLD token: /root/k3s-old-server-token (600)"
    new=$(openssl rand -hex 32)
    agent=$(openssl rand -hex 32)
    K3S_TOKEN="$old" k3s token rotate --new-token "$new"
    mkdir -p /etc/rancher/k3s/config.yaml.d
    printf 'token: "%s"\nagent-token: "%s"\n' "$new" "$agent" > "$drop"
    chmod 600 "$drop"
    unset new agent
    echo "restarting k3s (the API is away about 10 s)"
    systemctl restart k3s
    for _ in $(seq 1 90); do [ "$(curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:6443/cacerts)" = 200 ] && break; sleep 2; done
    cur=$(cat $d/token)
    echo "old token -> $(probe "$old") (want 401); current token -> $(probe "$cur") (want 200)"
    [ "$(probe "$old")" = 401 ] || { echo "STOP: the old token is not refused; OWNER-STEPS §5"; exit 1; }
    [ -L $d/agent-token ] && { echo "STOP: agent-token is still a link to the server token"; exit 1; }
    case "$(cat $d/agent-token)" in K10*::node:*) echo "agent token: separate, secure format" ;; *) echo "STOP: agent-token is not K10...::node:"; exit 1 ;; esac
    echo "server done" ;;
  list)
    # Only each token's id: a live bootstrap token printed whole would land in a pasted transcript.
    k3s token list | awk 'NR==1{print;next}{sub(/\.[^ ]*/, ".<hidden>", $1); print}' || true ;;
  forget-old)
    for name in $(k3s etcd-snapshot ls 2>/dev/null | awk '$1 ~ /^pre-td450/ {print $1}'); do k3s etcd-snapshot delete "$name"; done
    rm -f /root/k3s-old-server-token
    echo "old token copy and pre-td450 snapshot removed" ;;
  *) echo "usage: $0 check | rotate | list | forget-old"; exit 2 ;;
esac
