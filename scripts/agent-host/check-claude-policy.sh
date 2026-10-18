#!/usr/bin/env bash
# check-claude-policy.sh [<dir>]: the managed claude policy on this host turns
# every hook off, or there is none. agentd runs claude with no settings source
# and its hooks off, but a managed policy still applies, hooks and all
# (reviews 282-284, TD-371). <dir> is /etc/claude-code; tests give another.
# Prints a line per check; exits 1 when one fails.
set -u
root=${1:-/etc/claude-code}
rc=0
ok() { echo "ok   $*"; }
fail() {
  echo "FAIL $*"
  rc=1
}
f=$root/managed-settings.json
if [ ! -e "$f" ] && [ ! -L "$f" ]; then
  ok "no $f"
elif python3 -c 'import json,sys; sys.exit(0 if json.load(open(sys.argv[1])).get("disableAllHooks") is True else 1)' "$f" 2>/dev/null; then
  ok "$f turns every hook off"
else
  fail "$f is there and does not set disableAllHooks true"
fi
# claude reads the drop-ins through a link to a directory: a link there is
# refused outright (review 284 A), and so is any policy file inside.
d=$root/managed-settings.d
if [ -L "$d" ]; then
  fail "$d is a symbolic link (claude follows it): remove it"
elif [ ! -e "$d" ]; then
  ok "no $d"
elif ! found=$(find "$d" -mindepth 1 -maxdepth 1 ! -name '.*' -name '*.json' -print -quit 2>&1); then
  fail "$d could not be read: $found"
elif [ -n "$found" ]; then
  fail "$d holds $found: remove the drop-ins (they can add hooks back)"
else
  ok "$d holds no policy file"
fi
m=$root/managed-mcp.json
if [ -e "$m" ] || [ -L "$m" ]; then
  fail "$m is there: remove it"
else
  ok "no $m"
fi
exit $rc
