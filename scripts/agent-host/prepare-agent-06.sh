#!/usr/bin/env bash
# prepare-agent-06.sh — make ubt-k3s-06 (192.168.10.79), once it has left the
# cluster, the agent host: the PROD and the STG agentd, each as its own system
# user, behind per-user egress rules (Owner 2026-10-17;
# agent-config/work/multi-agent/CUT-agent-host-06-2026-10-17.md).
#
# The Owner runs it on 06 with sudo, from the directory scp put it in, with the
# agentd binary scp put beside that directory:
#
#   sudo bash ~/agent-host/prepare-agent-06.sh
#
# It downloads: Ubuntu packages (apt), Go 1.25 from go.dev and Node 22 from
# nodejs.org (each checked against the publisher's SHA-256), codex and claude
# from npm, cursor-agent from cursor.com's installer. Running it is the Owner's
# consent to those downloads. The vendor CLIs are installed as the agent users,
# after the egress rules are on, so they come through the same rules the agents
# will run under.
#
# A second run changes nothing that is already in place (the CLIs are not
# upgraded; the egress rules and the units are rewritten from this directory).
# It turns on only the egress rules. The two agentd services are installed but
# not started: they need their credentials and their tokens on the platforms
# first. It prints no credential.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
binary=agentd-f69e8c6-linux-amd64
prod=bifrost-agentd
stg=bifrost-agentd-stg

die() {
  echo "prepare-agent-06: $*" >&2
  exit 1
}
step() { echo "==> $*"; }

[ "$(id -u)" = 0 ] || die "run it with sudo"
[ "$(hostname)" = ubt-k3s-06 ] || die "this is $(hostname), not ubt-k3s-06"
. /etc/os-release
[ "${ID:-}" = ubuntu ] && [ "${VERSION_ID:-}" = 24.04 ] || die "expected Ubuntu 24.04, found ${PRETTY_NAME:-unknown}"
[ ! -e /usr/local/bin/k3s ] && ! systemctl list-unit-files k3s-agent.service --no-legend 2>/dev/null | grep -q . ||
  die "k3s is still installed: drain and delete the node, then run /usr/local/bin/k3s-agent-uninstall.sh"
# The egress rules let the agent users resolve names only through the local
# stub; another resolver on the LAN would be refused.
[ "$(readlink -f /etc/resolv.conf)" = /run/systemd/resolve/stub-resolv.conf ] ||
  die "/etc/resolv.conf is not systemd-resolved's stub (it is $(readlink -f /etc/resolv.conf))"
[ -f "$here/../$binary" ] || die "missing $here/../$binary (scp it beside this directory)"
(cd "$here/.." && sha256sum --quiet -c "$here/agentd.sha256") || die "$binary does not match agentd.sha256"

step "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends nftables git ca-certificates curl xz-utils openssl python3

step "users $prod, $stg"
for u in "$prod" "$stg"; do
  id "$u" >/dev/null 2>&1 || useradd --create-home --user-group --shell /bin/bash "$u"
  chmod 700 "/home/$u"
  if id -nG "$u" | tr ' ' '\n' | grep -qxE 'sudo|adm|admin|wheel|lxd|docker|systemd-journal'; then
    die "$u is in an administrative group: $(id -nG "$u")"
  fi
  [ ! -e "/home/$u/.ssh" ] || die "/home/$u/.ssh exists: nobody logs in as $u"
done

step "egress rules"
install -d -m 755 /etc/bifrost
nft -c -f "$here/agent-egress.nft"
install -m 644 "$here/agent-egress.nft" /etc/bifrost/agent-egress.nft
install -m 644 "$here/bifrost-agent-egress.service" /etc/systemd/system/bifrost-agent-egress.service
systemctl daemon-reload
systemctl enable bifrost-agent-egress.service
systemctl restart bifrost-agent-egress.service
nft list chain inet bifrost_agent common >/dev/null || die "the egress table did not load"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

step "Go 1.25 (go.dev)"
read -r go_file go_sha < <(curl -fsSL --proto '=https' 'https://go.dev/dl/?mode=json&include=all' | python3 -c '
import json, sys
for r in json.load(sys.stdin):
    if r.get("stable") and r["version"].startswith("go1.25."):
        for f in r["files"]:
            if f["os"] == "linux" and f["arch"] == "amd64" and f["kind"] == "archive":
                print(f["filename"], f["sha256"])
                sys.exit(0)
sys.exit("no stable go1.25 linux-amd64 archive listed")
')
[ -n "${go_file:-}" ] && [ -n "${go_sha:-}" ] || die "could not read the Go 1.25 release from go.dev"
go_version=${go_file%.linux-amd64.tar.gz}
if [ "$(/usr/local/go/bin/go env GOVERSION 2>/dev/null || true)" != "$go_version" ]; then
  curl -fsSL --proto '=https' -o "$tmp/$go_file" "https://go.dev/dl/$go_file"
  echo "$go_sha  $tmp/$go_file" | sha256sum --quiet -c -
  rm -rf /usr/local/go
  tar -C /usr/local -xzf "$tmp/$go_file"
fi
/usr/local/go/bin/go version

step "Node 22 (nodejs.org)"
curl -fsSL --proto '=https' -o "$tmp/SHASUMS256.txt" https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt
node_file=$(awk '$2 ~ /^node-v22\.[0-9]+\.[0-9]+-linux-x64\.tar\.xz$/ {print $2}' "$tmp/SHASUMS256.txt")
[ -n "$node_file" ] || die "no Node 22 linux-x64 archive in SHASUMS256.txt"
node_dir=/usr/local/lib/nodejs/${node_file%.tar.xz}
if [ ! -x "$node_dir/bin/node" ]; then
  curl -fsSL --proto '=https' -o "$tmp/$node_file" "https://nodejs.org/dist/latest-v22.x/$node_file"
  (cd "$tmp" && grep "  $node_file\$" SHASUMS256.txt | sha256sum --quiet -c -)
  install -d -m 755 /usr/local/lib/nodejs
  tar -C /usr/local/lib/nodejs -xJf "$tmp/$node_file"
fi
ln -sfn "$node_dir" /usr/local/lib/nodejs/current
/usr/local/lib/nodejs/current/bin/node -v

# as <user> <command>: a login-free shell as that user, in its home, with only
# its own environment (none of root's or sudo's).
as() {
  local u=$1
  shift
  sudo -u "$u" -H env -i HOME="/home/$u" USER="$u" LOGNAME="$u" SHELL=/bin/bash LANG=C.UTF-8 \
    PATH="/home/$u/.local/bin:/usr/local/go/bin:/usr/local/lib/nodejs/current/bin:/usr/local/bin:/usr/bin:/bin" \
    bash -c 'cd "$HOME" && umask 077 && eval "$1"' bash "$*"
}

step "directories"
for u in "$prod" "$stg"; do
  as "$u" 'mkdir -p -m 700 .config/bifrost agent-work/agentd && mkdir -p .local/bin && chmod 700 .config .config/bifrost agent-work agent-work/agentd'
done

step "vendor CLIs (as the agent users, through the egress rules)"
as "$prod" '[ -x .local/bin/codex ] && [ -x .local/bin/claude ] || npm install -g --prefix "$HOME/.local" --no-audit --no-fund @openai/codex @anthropic-ai/claude-code'
as "$prod" '[ -x .local/bin/cursor-agent ] || curl -fsS --proto "=https" https://cursor.com/install | bash'
as "$stg" '[ -x .local/bin/codex ] || npm install -g --prefix "$HOME/.local" --no-audit --no-fund @openai/codex'

step "agentd platform tokens (generated here, kept here; the Owner copies each into its platform's Secret)"
for u in "$prod" "$stg"; do
  as "$u" '[ -s .config/bifrost/agentd.token ] || openssl rand -hex 32 | tr -d "\n" > .config/bifrost/agentd.token'
done

step "agentd binary and units (installed, not started)"
install -d -m 755 /usr/local/libexec/bifrost
install -m 755 "$here/../$binary" /usr/local/libexec/bifrost/agentd
install -m 644 "$here/bifrost-agentd.service" /etc/systemd/system/bifrost-agentd.service
install -m 644 "$here/bifrost-agentd-stg.service" /etc/systemd/system/bifrost-agentd-stg.service
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/bifrost-agent-egress.service /etc/systemd/system/bifrost-agentd.service /etc/systemd/system/bifrost-agentd-stg.service

echo "prepared: egress rules on; $binary installed as /usr/local/libexec/bifrost/agentd; both agentd services installed and stopped"
