#!/bin/sh
# Bifrost commit lineage trailers.
#
#   Claude-Session:    sidebar thread id (CLAUDE_CODE_HOST_SESSION_ID, e.g. local_…);
#                      falls back to the CLI session id when there is no desktop host
#   Claude-Transcript: CLI session id (CLAUDE_CODE_SESSION_ID) — names the transcript
#                      file and the scratchpad directory; only when it differs from the above
#   Change-Id:         Gerrit-style stable id; survives rebase, cherry-pick and amend, so a
#                      lane re-landed under a new version number still matches main
#   Work:              work-item ids drawn from the subject and body (TD-n, W-n, LANE-…)
#                      at commit-msg; "unassigned" when none are present. An existing
#                      Work trailer is left as-is (amend, rebase, cherry-pick).
#
# Usage: lineage.sh <prepare-commit-msg|commit-msg> <msg-file> [source [sha]]
# Every trailer is added only when that key is absent, so amends keep the original
# session and Change-Id. Replays (rebase, cherry-pick, revert) are left untouched.
hook=$1
msg=$2
source=${3-}
[ -n "$msg" ] && [ -f "$msg" ] || exit 0

git_dir=$(git rev-parse --git-dir 2>/dev/null) || exit 0
for f in rebase-merge rebase-apply CHERRY_PICK_HEAD REVERT_HEAD; do
  [ -e "$git_dir/$f" ] && exit 0
done

# Editor commits are handled at commit-msg, after the user has written the message.
if [ "$hook" = prepare-commit-msg ]; then
  case "$source" in message|commit|merge|squash) ;; *) exit 0 ;; esac
fi

# An empty message aborts the commit; trailers would turn it into a real one.
grep -qv -e '^[[:space:]]*$' -e '^#' "$msg" || exit 0

add() {
  git interpret-trailers --in-place --if-exists doNothing --trailer "$1: $2" "$msg"
}

host=${CLAUDE_CODE_HOST_SESSION_ID-}
cli=${CLAUDE_CODE_SESSION_ID-}
if [ -n "$host" ]; then
  add Claude-Session "$host"
  [ -n "$cli" ] && [ "$cli" != "$host" ] && add Claude-Transcript "$cli"
elif [ -n "$cli" ]; then
  add Claude-Session "$cli"
fi

if ! git interpret-trailers --parse "$msg" | grep -q '^Change-Id:'; then
  id=$( { date +%s; echo $$; od -An -N16 -tx1 /dev/urandom; cat "$msg"; } | git hash-object --stdin)
  add Change-Id "I$id"
fi

# Work is stamped only at commit-msg, after the message is final. prepare-commit-msg
# runs too early for editor commits, and a second pass must not rewrite an existing value.
if [ "$hook" = commit-msg ] && ! git interpret-trailers --parse "$msg" | grep -qi '^Work:'; then
  ids=$(awk '
    {
      line = $0
      while (match(line, /TD-[0-9]+|W-[0-9]+|LANE-[A-Z0-9]+/)) {
        id = substr(line, RSTART, RLENGTH)
        pre = (RSTART > 1) ? substr(line, RSTART - 1, 1) : ""
        if (pre !~ /[A-Za-z0-9]/ && !seen[id]) {
          seen[id] = 1
          ids[++n] = id
        }
        line = substr(line, RSTART + RLENGTH)
      }
    }
    END {
      for (i = 1; i <= n; i++) printf "%s%s", (i == 1 ? "" : ", "), ids[i]
    }
  ' "$msg")
  if [ -n "$ids" ]; then
    add Work "$ids"
  else
    add Work unassigned
  fi
fi
exit 0
