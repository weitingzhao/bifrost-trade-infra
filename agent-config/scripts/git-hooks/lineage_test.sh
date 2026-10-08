#!/bin/sh
# lineage.sh commit-msg: Work trailer. Three cases the hook must get right:
# several ids, no ids, an existing Work trailer left untouched.
# Also: rebase / cherry-pick do not rewrite the message.
set -eu
hooks=$(cd "$(dirname "$0")" && pwd)
lineage=$hooks/lineage.sh
unset CLAUDE_CODE_HOST_SESSION_ID CLAUDE_CODE_SESSION_ID || true

fail=0
say() { printf '%s\n' "$*"; }
bad() { say "FAIL: $*"; fail=1; }

workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT
git -C "$workdir" init -q
git -C "$workdir" config user.email "lineage-test@example.com"
git -C "$workdir" config user.name "lineage-test"

run() {
  # $1 name, $2 message, $3 hook (default commit-msg)
  name=$1
  hook=${3:-commit-msg}
  msg=$workdir/msg
  printf '%s\n' "$2" > "$msg"
  (cd "$workdir" && sh "$lineage" "$hook" "$msg")
}

work_of() {
  git -C "$workdir" interpret-trailers --parse "$workdir/msg" | awk -F': ' 'tolower($1)=="work" { print substr($0, index($0, ": ")+2); exit }'
}

# Several ids, first-seen order, duplicates dropped. A glued token must not match.
run multi "$(printf '%s\n' 'LANE-C fix TD-253' '' 'also TD-253 and W-4, not NOTD-8' 'LANE-A6R')"
got=$(work_of)
want='LANE-C, TD-253, W-4, LANE-A6R'
[ "$got" = "$want" ] || bad "multi: got [$got] want [$want]"
git -C "$workdir" interpret-trailers --parse "$workdir/msg" | grep -q '^Change-Id: I' || bad "multi: missing Change-Id"

# No ids.
run none "$(printf '%s\n' 'fix a typo' '' 'nothing to track')"
got=$(work_of)
[ "$got" = "unassigned" ] || bad "none: got [$got] want [unassigned]"

# Existing Work is kept, even when the subject names another id (amend).
run keep "$(printf '%s\n' 'amend TD-99' '' 'Work: LANE-C')"
got=$(work_of)
[ "$got" = "LANE-C" ] || bad "keep: got [$got] want [LANE-C]"
# exactly one Work line
n=$(grep -c '^Work:' "$workdir/msg" || true)
[ "$n" = "1" ] || bad "keep: Work lines=$n want 1"

# prepare-commit-msg does not add Work (commit-msg does).
run early "$(printf '%s\n' 'LANE-D1 early')" prepare-commit-msg
if git -C "$workdir" interpret-trailers --parse "$workdir/msg" | grep -qi '^Work:'; then
  bad "prepare-commit-msg added Work"
fi

# rebase and cherry-pick leave the file byte-for-byte.
plain=$(printf '%s\n' 'wip TD-1' '')
for marker in rebase-merge CHERRY_PICK_HEAD; do
  printf '%s' "$plain" > "$workdir/msg"
  before=$(cksum "$workdir/msg")
  touch "$workdir/.git/$marker"
  (cd "$workdir" && sh "$lineage" commit-msg "$workdir/msg")
  after=$(cksum "$workdir/msg")
  rm -rf "$workdir/.git/$marker"
  [ "$before" = "$after" ] || bad "$marker rewrote the message"
done

if [ "$fail" = 0 ]; then
  say "ok lineage_test"
  exit 0
fi
say "---- last message ----"
cat "$workdir/msg"
exit 1
