#!/bin/sh
# Give HEAD the lineage trailers it lacks: a Change-Id (made from the commit id,
# so the same commit always gets the same one) and, when the session is known
# (CLAUDE_CODE_HOST_SESSION_ID, else CLAUDE_CODE_SESSION_ID), a Claude-Session.
# Unlike agent-config/scripts/git-hooks/lineage.sh it works inside a rebase, so push-main.sh can hand a pusher
# one command for a whole branch (walls review [79], 2026-11-25):
#
#   git -C <checkout> rebase -q origin/main --exec 'sh <this file>'
#
# A commit that has both trailers is left as it is.
set -eu
msg="$(git rev-parse --git-dir)/LINEAGE_MSG"
git log -1 --format=%B HEAD >"$msg"
before=$(cat "$msg")
if ! git interpret-trailers --parse "$msg" | grep -q '^Change-Id:'; then
  git interpret-trailers --in-place --trailer "Change-Id: I$(git rev-parse HEAD)" "$msg"
fi
session=${CLAUDE_CODE_HOST_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-}}
if [ -n "$session" ] && ! git interpret-trailers --parse "$msg" | grep -q '^Claude-Session:'; then
  git interpret-trailers --in-place --trailer "Claude-Session: $session" "$msg"
fi
if [ "$(cat "$msg")" != "$before" ]; then
  git commit -q --amend --allow-empty --no-verify -F "$msg"
fi
rm -f "$msg"
