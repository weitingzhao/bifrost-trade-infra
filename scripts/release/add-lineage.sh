#!/bin/sh
# Give HEAD the lineage trailers it lacks: a Change-Id in its last paragraph
# (made from the commit id, as the landing makes it) and, when the session is known
# (CLAUDE_CODE_HOST_SESSION_ID, else CLAUDE_CODE_SESSION_ID), a Claude-Session.
# Unlike agent-config/scripts/git-hooks/lineage.sh it works inside a rebase, so push-main.sh can hand a pusher
# one command for a whole branch (walls review [79], 2026-11-25):
#
#   git -C <checkout> rebase -q origin/main --exec 'sh <this file>'
#
# A commit that has both trailers is left as it is.
set -eu
msg="$(git rev-parse --git-dir)/LINEAGE_MSG"
session=${CLAUDE_CODE_HOST_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-}}
git log -1 --format=%B HEAD >"$msg.before"
# The landing's own rules (scripts/landing/trailers.py, walls review [79]).
python3 -I "$(dirname "$0")/../landing/trailers.py" fix --sha "$(git rev-parse HEAD)" --session "$session" <"$msg.before" >"$msg"
if ! cmp -s "$msg" "$msg.before"; then
  git commit -q --amend --allow-empty --no-verify -F "$msg"
fi
rm -f "$msg" "$msg.before"
