#!/usr/bin/env bash
# prepare-agent-06.sh — make ubt-k3s-06 (192.168.10.79), once it has left the
# cluster, the agent host: the PROD and the STG agentd, each as its own system
# user, behind per-user egress rules (Owner 2026-10-17;
# agent-config/work/multi-agent/CUT-agent-host-06-2026-10-17.md).
#
# Run on 06 with sudo, by agent-06-owner.sh `prepare`, from the directory scp
# put it in, with the agentd binary scp put beside that directory:
#
#   sudo bash ~/agent-host/prepare-agent-06.sh
#
# It downloads: Ubuntu packages (apt), Go 1.25 from go.dev and Node 22 from
# nodejs.org (each checked against the publisher's SHA-256), codex and claude
# from npm, cursor-agent from cursor.com's installer (Owner 2026-10-17: agreed).
# claude and cursor-agent are installed as the agent users after the egress
# rules are on, so they come through the rules the agents will run under.
# codex is installed once, by root, under /opt/bifrost/codex, at a pinned
# version, because its sandbox needs user namespaces and the AppArmor rule
# that allows them (bifrost-codex.apparmor) must name a directory the agents
# cannot write (Owner 2026-10-17, option A).
#
# A second run installs only what is missing: it does not upgrade Go, Node or
# a CLI, and it keeps the platform tokens. It reloads the egress rules in
# place (one atomic nft transaction, no window without them). It refuses to
# run while either agentd is running. It turns on only the egress rules; the
# two agentd services are installed but not started. It prints no credential.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd -P)
binary=agentd-f69e8c6-linux-amd64
codex_version=0.163.0
codex_prefix=/opt/bifrost/codex
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
if [ -e /usr/local/bin/k3s ] || systemctl list-unit-files k3s-agent.service --no-legend 2>/dev/null | grep -q .; then
  die "k3s is still installed: after the drain, uninstall it and reboot (agent-06-owner.sh uninstall), then delete the node (agent-06-owner.sh delete-node)"
fi
for s in bifrost-agentd bifrost-agentd-stg; do
  ! systemctl is-active --quiet "$s" || die "$s is running: stop it first (systemctl stop $s), then run this again"
done
# The egress rules let the agent users resolve names only through the local
# stub; another resolver on the LAN would be refused.
[ "$(readlink -f /etc/resolv.conf)" = /run/systemd/resolve/stub-resolv.conf ] ||
  die "/etc/resolv.conf is not systemd-resolved's stub (it is $(readlink -f /etc/resolv.conf))"
systemctl is-active --quiet systemd-resolved || die "systemd-resolved is not running"
[ -f "$here/../$binary" ] || die "missing $here/../$binary (scp it beside this directory)"
(cd "$here/.." && sha256sum --quiet -c "$here/agentd.sha256") || die "$binary does not match agentd.sha256"

step "packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends nftables git ca-certificates curl xz-utils openssl python3

step "users $prod, $stg"
for u in "$prod" "$stg"; do
  if id "$u" >/dev/null 2>&1; then
    # An existing user must be the one this script made: its own home and
    # group only, a locked password, no SSH keys. Anything else stops here;
    # nothing is pruned without a person looking at it.
    [ "$(getent passwd "$u" | cut -d: -f6)" = "/home/$u" ] || die "$u's home is not /home/$u"
    [ "$(id -nG "$u")" = "$u" ] || die "$u is in groups other than its own: $(id -nG "$u")"
  else
    useradd --create-home --user-group --shell /bin/bash "$u"
  fi
  [ "$(passwd -S "$u" | awk '{print $2}')" = L ] || die "$u's password is not locked"
  [ ! -e "/home/$u/.ssh" ] || die "/home/$u/.ssh exists: nobody logs in as $u"
  chown "$u:$u" "/home/$u"
  chmod 700 "/home/$u"
done

step "egress rules"
install -d -m 755 /etc/bifrost
nft -c -f "$here/agent-egress.nft"
install -m 644 "$here/agent-egress.nft" /etc/bifrost/agent-egress.nft
install -m 644 "$here/bifrost-agent-egress.service" /etc/systemd/system/bifrost-agent-egress.service
systemctl daemon-reload
systemctl enable --quiet bifrost-agent-egress.service
if systemctl is-active --quiet bifrost-agent-egress.service; then
  # In place: the file replaces the table in one transaction.
  systemctl reload bifrost-agent-egress.service
else
  systemctl start bifrost-agent-egress.service
fi
nft list chain inet bifrost_agent common >/dev/null || die "the egress table did not load"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

step "Go 1.25 (go.dev)"
if /usr/local/go/bin/go env GOVERSION 2>/dev/null | grep -qE '^go1\.25\.[0-9]+$'; then
  echo "already there"
else
  curl -fsSL --proto '=https' -o "$tmp/go.json" 'https://go.dev/dl/?mode=json&include=all'
  read -r go_file go_sha < <(python3 -c '
import json, sys
for r in json.load(open(sys.argv[1])):
    if r.get("stable") and r["version"].startswith("go1.25."):
        for f in r["files"]:
            if f["os"] == "linux" and f["arch"] == "amd64" and f["kind"] == "archive":
                print(f["filename"], f["sha256"])
                sys.exit(0)
sys.exit("no stable go1.25 linux-amd64 archive listed")
' "$tmp/go.json")
  [ -n "${go_file:-}" ] && [ -n "${go_sha:-}" ] || die "could not read the Go 1.25 release from go.dev"
  curl -fsSL --proto '=https' -o "$tmp/$go_file" "https://go.dev/dl/$go_file"
  echo "$go_sha  $tmp/$go_file" | sha256sum --quiet -c -
  rm -rf /usr/local/go
  tar -C /usr/local -xzf "$tmp/$go_file"
fi
/usr/local/go/bin/go version

step "Node 22 (nodejs.org)"
if [ -x /usr/local/lib/nodejs/current/bin/node ] && /usr/local/lib/nodejs/current/bin/node -v | grep -qE '^v22\.'; then
  echo "already there"
else
  curl -fsSL --proto '=https' -o "$tmp/SHASUMS256.txt" https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt
  node_file=$(awk '$2 ~ /^node-v22\.[0-9]+\.[0-9]+-linux-x64\.tar\.xz$/ {print $2}' "$tmp/SHASUMS256.txt")
  [ -n "$node_file" ] || die "no Node 22 linux-x64 archive in SHASUMS256.txt"
  curl -fsSL --proto '=https' -o "$tmp/$node_file" "https://nodejs.org/dist/latest-v22.x/$node_file"
  (cd "$tmp" && grep "  $node_file\$" SHASUMS256.txt | sha256sum --quiet -c -)
  install -d -m 755 /usr/local/lib/nodejs
  tar -C /usr/local/lib/nodejs -xJf "$tmp/$node_file"
  ln -sfn "/usr/local/lib/nodejs/${node_file%.tar.xz}" /usr/local/lib/nodejs/current
fi
/usr/local/lib/nodejs/current/bin/node -v

# as <user> <command>: run one command string as that user, in its home, with
# only its own environment (none of root's or sudo's), stopping at the first
# error of any part of a pipeline.
as() {
  local u=$1
  sudo -u "$u" -H env -i HOME="/home/$u" USER="$u" LOGNAME="$u" SHELL=/bin/bash LANG=C.UTF-8 \
    PATH="$codex_prefix/bin:/home/$u/.local/bin:/usr/local/go/bin:/usr/local/lib/nodejs/current/bin:/usr/local/bin:/usr/bin:/bin" \
    bash -euo pipefail -c "cd \"\$HOME\" && umask 077 && $2"
}

step "directories"
for u in "$prod" "$stg"; do
  as "$u" 'mkdir -p .config/bifrost agent-work/agentd .local/bin && chmod 700 .config .config/bifrost agent-work agent-work/agentd'
done

step "codex $codex_version under $codex_prefix (root-owned) and the AppArmor rule for its sandbox"
if [ "$("$codex_prefix/bin/codex" --version 2> /dev/null || true)" != "codex-cli $codex_version" ]; then
  install -d -m 755 /opt/bifrost "$codex_prefix"
  PATH="/usr/local/lib/nodejs/current/bin:$PATH" npm install -g --prefix "$codex_prefix" --ignore-scripts --no-audit --no-fund "@openai/codex@$codex_version"
fi
chown -R root:root "$codex_prefix"
chmod -R go-w "$codex_prefix"
[ "$("$codex_prefix/bin/codex" --version)" = "codex-cli $codex_version" ] || die "codex under $codex_prefix is not $codex_version"
[ -d "$codex_prefix/lib/node_modules/@openai/codex/node_modules/@openai/codex-linux-x64/vendor" ] ||
  die "codex's Linux binaries are not where bifrost-codex.apparmor expects them"
install -m 644 "$here/bifrost-codex.apparmor" /etc/apparmor.d/bifrost-codex
apparmor_parser -r /etc/apparmor.d/bifrost-codex
grep -q '^bifrost-codex ' /sys/kernel/security/apparmor/profiles || die "the AppArmor profile bifrost-codex did not load"
# The agent users used to have their own codex; theirs would bypass the rule
# (and fail in the sandbox), so it goes.
for u in "$prod" "$stg"; do
  as "$u" '[ ! -e .local/lib/node_modules/@openai/codex ] || npm uninstall -g --prefix "$HOME/.local" --no-audit --no-fund @openai/codex'
  as "$u" '[ ! -e .local/bin/codex ]' || die "$u still has its own codex in ~/.local/bin"
  # One command in codex's own sandbox, no model: it fails with
  # "RTM_NEWADDR: Operation not permitted" when the rule is not in force.
  as "$u" "out=\$(codex sandbox -C \"\$HOME\" -- /bin/true 2>&1) || { printf '%s\\n' \"\$out\" >&2; exit 1; }" ||
    die "$u: codex cannot run a command in its sandbox"
done

step "vendor CLIs (as the agent users, through the egress rules)"
npm_cli() { # npm_cli <user> <binary> <package>
  as "$1" "[ -x .local/bin/$2 ] || npm install -g --prefix \"\$HOME/.local\" --no-audit --no-fund $3"
}
npm_cli "$prod" claude @anthropic-ai/claude-code
# cursor-agent: the installer is downloaded first and run only if the
# download succeeded, so a failed or cut-off download changes nothing.
as "$prod" '[ -x .local/bin/cursor-agent ] || { t=$(mktemp) && curl -fsS --proto "=https" -o "$t" https://cursor.com/install && bash "$t"; rc=$?; rm -f "$t"; exit $rc; }'
for c in claude cursor-agent; do
  as "$prod" "[ -x .local/bin/$c ] && .local/bin/$c --version >/dev/null 2>&1" || die "$prod: $c is not installed or does not run"
done
for u in "$prod" "$stg"; do
  as "$u" '[ "$(command -v codex)" = /opt/bifrost/codex/bin/codex ]' || die "$u: codex on its PATH is not the one under $codex_prefix"
done

step "agentd platform tokens (made here, kept here; agent-06-owner.sh copies each into its platform's Secret)"
for u in "$prod" "$stg"; do
  f=/home/$u/.config/bifrost/agentd.token
  if [ -e "$f" ] || [ -L "$f" ]; then
    # The whole file is the token: 64 bytes, all hex, no other line.
    { [ -f "$f" ] && [ ! -L "$f" ] && [ "$(stat -c '%U %a %s' "$f")" = "$u 600 64" ] && grep -qxE '[0-9a-f]{64}' "$f"; } ||
      die "$f is there but is not a 64-hex token owned by $u with mode 600; look at it before running this again"
  else
    as "$u" 't=$(mktemp .config/bifrost/.token.XXXXXX) && openssl rand -hex 32 | tr -d "\n" > "$t" && grep -qxE "[0-9a-f]{64}" "$t" && chmod 600 "$t" && mv "$t" .config/bifrost/agentd.token'
  fi
done

step "agentd binary and units (installed, not started)"
install -d -m 755 /usr/local/libexec/bifrost
install -m 755 "$here/../$binary" /usr/local/libexec/bifrost/agentd
install -m 644 "$here/bifrost-agentd.service" /etc/systemd/system/bifrost-agentd.service
install -m 644 "$here/bifrost-agentd-stg.service" /etc/systemd/system/bifrost-agentd-stg.service
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/bifrost-agent-egress.service /etc/systemd/system/bifrost-agentd.service /etc/systemd/system/bifrost-agentd-stg.service

echo "prepared: egress rules on; $binary installed as /usr/local/libexec/bifrost/agentd; both agentd services installed and stopped"
