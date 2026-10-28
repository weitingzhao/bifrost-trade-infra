#!/usr/bin/env bash
# TD-450: install-agent.sh takes a bootstrap token or the agent token, never the server token.
# Runs as a normal user: an accepted token gets past the token check and stops at the root check.
set -uo pipefail
script="$(cd "$(dirname "$0")" && pwd)/install-agent.sh"
hash=K10$(printf 'a%.0s' $(seq 1 64))
fail=0
run() { # run <want: accept|refuse> <token>
  local out
  out=$(K3S_URL=https://192.168.10.73:6443 K3S_TOKEN="$2" K3S_NODE_IP=192.168.10.99 INSTALL_K3S_VERSION=v1.35.5+k3s1 \
    bash "$script" 2>&1 </dev/null)
  if [[ $EUID -eq 0 ]]; then echo "run this test as a normal user" >&2; exit 2; fi
  case "$1:$out" in
    accept:*"Run as root"*|refuse:*"refusing"*|refuse:*"Refusing"*) echo "ok   $1 ${2:0:24}…" ;;
    *) echo "FAIL want $1 for ${2:0:24}…: $out"; fail=1 ;;
  esac
}
run accept "${hash}::node:0123456789abcdef0123456789abcdef"
run accept "${hash}::abcdef.0123456789abcdef"
run accept "abcdef.0123456789abcdef"
run refuse "${hash}::server:0123456789abcdef0123456789abcdef"
run refuse "0123456789abcdef0123456789abcdef"
run refuse "${hash}::node:"
exit $fail
