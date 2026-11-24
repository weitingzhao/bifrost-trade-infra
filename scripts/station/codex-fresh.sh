#!/bin/zsh -l
# codex-fresh.sh — start a fresh Codex on this machine so it can use the platform mailbox (Station, 2026-11-24).
#
# Usage: codex-fresh.sh <work dir with BRIEF.md> [prompt]
#
# Why two steps: Codex sets CODEX_THREAD_ID for its own shell tools but not for the MCP servers it starts,
# so a fresh `codex exec` reaches the platform MCP with no session id and every write (send_message, the
# handover) is refused. Found by the B6 entry test on mini-02 and A9 on mini-01 (2026-11-24): both did the
# work and could not hand it back. Step 1 runs a one-line turn to get the thread id; step 2 resumes that
# thread with CODEX_THREAD_ID exported, which the seat profile forwards to the MCP (env_vars).
set -eu
dir=${1:?usage: codex-fresh.sh <work dir> [prompt]}
prompt=${2:-"Read BRIEF.md in this directory and do what it says."}
C=${CODEX_BIN:-$(command -v codex || echo /Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex)}
opts=(--skip-git-repo-check -c sandbox_mode='"workspace-write"' -c sandbox_workspace_write.network_access=true)
cd "$dir"
tid=$("$C" --profile bifrost-seat exec --json "${opts[@]}" -C "$dir" "Reply with the word ready. Do nothing else." < /dev/null 2>/dev/null \
  | sed -n 's/.*"thread_id":"\([^"]*\)".*/\1/p' | head -1)
[ -n "$tid" ] || { echo "codex-fresh: no thread id from step 1" >&2; exit 1; }
echo "codex-fresh: thread $tid" >&2
export CODEX_THREAD_ID=$tid
exec "$C" --profile bifrost-seat exec resume "${opts[@]}" "$tid" "$prompt" < /dev/null
