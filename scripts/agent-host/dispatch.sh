#!/usr/bin/env bash
# dispatch.sh — start a Codex run through the PV1 dispatch wrapper, so it is registered in the PROD runtime
# (visible on ops.bifrost.lan) before it starts; registration failure means it does not start.
# Usage: dispatch.sh <work dir with BRIEF.md> <plan node, e.g. R4:4.1> <task text (Chinese ok)> <repo> <branch> [extra codex exec args...]
# The token is the coordinator's reporter token, read here and passed only through the environment.
# Lives in infra since 2026-11-21 (Station, from ~/agent-work/dispatch.sh, which was on one machine only).
# Run it from any infra checkout; the wrapper is still read from origin/main, so a stale checkout runs today's wrapper.
# Session: the dispatch session is its own (local_accccb4e-dispatch): a runtime session belongs to the first
# token that wrote with it, and the thread's own session belongs to the MCP operator token.
set -euo pipefail
infra="$(cd "$(dirname "$0")/../.." && pwd)"
dir="$(cd "$1" && pwd)"; node="$2"; task="$3"; repo="$4"; branch="$5"; shift 5
run_key="${RUN_KEY:-$(basename "$dir")}"
# Entry card (Station, 2026-11-21): Codex reads AGENTS.md in its working dir on every turn, so the card is in
# front of the run at start, after compaction and before it asks. Refuses when BRIEF.md has no reply_to.
# The card needs PyYAML. After the 11-22 reboot the first python3 on PATH was Homebrew's, without it, and the
# card step failed (Station, 11-23). Take the first python3 that has it; fail with that sentence otherwise.
py=""
for cand in python3 /opt/anaconda3/bin/python3 /usr/bin/python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import yaml' 2>/dev/null; then py="$cand"; break; fi
done
[[ -n "$py" ]] || { echo "dispatch.sh: no python3 with PyYAML (the entry card needs it)" >&2; exit 2; }
"$py" "$infra/scripts/agent-host/codex-card.py" "$dir"
python3 - "$dir/desc.json" "$task" "$repo" "$branch" "$node" <<'PY'
import json, sys
path, task, repo, branch, node = sys.argv[1:6]
json.dump({"v": 1, "kind": "agentrt.external_work/v1", "task": task, "executor": "codex", "provider": "openai",
           "repo": repo, "branch": branch, "acceptance_refs": [node], "estimate_minutes": [20, 120]},
          open(path, "w"), ensure_ascii=False)
open(path, "a").write("\n")
PY
cd "$dir"
# Shared caches (TD-415, 2026-11-02): Codex's sandbox cannot write the default Go cache, so without these
# every run made its own .gocache in its work dir (206 dirs, 211 GB from 10-24 to 10-30). The same three
# dirs the review BRIEFs name; --add-dir below makes them writable in the sandbox.
cache="$HOME/agent-work/.cache"
mkdir -p "$cache/go-build" "$cache/go-mod" "$cache/npm"
export GOCACHE="$cache/go-build" GOMODCACHE="$cache/go-mod" npm_config_cache="$cache/npm"
# Network on (Station, 2026-11-22): a run pushes its ready/ branch and fetches main from Gitea, which the
# workspace-write sandbox blocks by default. Until now it came from extra args some callers passed, written
# nowhere (the 11-13 runs logged "network access enabled"; the 11-22 entry test, started without them, got
# "Couldn't connect to server" on its first fetch). agent-config/codex/README.md describes it as on.
# The wrapper comes from infra's origin/main on every run, copied into the run dir (2026-11-02: the old
# ~/agent-work/dispatch-wrapper checkout was removed as a clean pushed checkout; tools must not live in one).
wrapper="$dir/.dispatch-codex.py"
git -C "$infra" fetch -q origin main
git -C "$infra" show origin/main:scripts/agent-host/dispatch-codex.py > "$wrapper"
# Flight-2 (2026-11-14, coordinator-approved): the platform MCP refuses every write without a session id
# (mcp/platform/src/sessionId.ts). Give each codex run its own fresh id, codex-prefixed; never a Claude session id.
export CLAUDE_CODE_HOST_SESSION_ID="codex-${run_key}-$(date -u +%Y%m%dT%H%M%SZ)-$RANDOM"
# U01 (2026-11-14): lineage.sh writes Claude-Transcript from CLAUDE_CODE_SESSION_ID, which the run inherited from
# the launching Claude session. Set it equal to the host id: lineage.sh adds no transcript trailer when they match.
export CLAUDE_CODE_SESSION_ID="$CLAUDE_CODE_HOST_SESSION_ID"
# Seat profile by default (Station, 2026-11-22; Crew's first visit, r1): ~/.codex/bifrost-seat.config.toml gives
# a non-login shell (its python3 has PyYAML and pytest), forwards the session id to the platform MCP, and opens
# the network; dispatch-codex.README.md named "-p bifrost-seat" but nothing passed it unless the caller did.
profile=()
if [[ -f "$HOME/.codex/bifrost-seat.config.toml" && " $* " != *" -p "* && " $* " != *" --profile "* ]]; then
  profile=(-p bifrost-seat)
fi
BIFROST_DISPATCH_TOKEN="$(cat "$HOME/.config/bifrost/lineage-reporter.token")" \
python3 "$wrapper" \
  --url http://192.168.10.100:30876 --session local_accccb4e-dispatch --run-key "$run_key" \
  --root "${node%%:*}" --node "$node" --description "$dir/desc.json" --report "$dir/REPORT.md" \
  --state-dir "$dir/.dispatch-$run_key" --repo "$dir" \
  -- --skip-git-repo-check --add-dir "$cache" -c sandbox_workspace_write.network_access=true -m gpt-6-astra -c model_reasoning_effort="high" ${profile[@]+"${profile[@]}"} "$@" -C "$dir" "Read BRIEF.md in this directory and do what it says."
