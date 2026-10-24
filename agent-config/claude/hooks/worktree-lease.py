#!/usr/bin/env python3
"""Claude Code hook: worktree end records (W-31 round 4, 4.6 S3; CUT-lifecycle-2026-10-24.md §4.2).

    SessionEnd    ended_at on every worktree registered to this session (new-worktree.sh
                  --session, which defaults to CLAUDE_CODE_SESSION_ID), or to its host
                  session (CLAUDE_CODE_HOST_SESSION_ID, the Desktop thread). Not on reason
                  "clear": the thread goes on in a new session, so the work has not ended.
    SessionStart  renew those records: a resumed session (or the session that follows a
                  /clear in the same thread) voids an earlier end before it uses anything.

A sweep removes a worktree only when its record says ended (worktree_owner.py), so a session
that dies without SessionEnd leaves its worktrees in use: the safe direction.

Not wired into any settings.json yet; the proposed wiring is in
agent-config/work/multi-agent/S3-hook-wiring-proposal-2026-10-24.md.

Cursor's sessionEnd / sessionStart payloads (conversation_id) are read the same way.
Claude Code gives all SessionEnd hooks 1.5 s unless a hook sets "timeout"; the proposal sets one.

Never blocks a session: it always exits 0, prints nothing on stdout (SessionStart stdout would
become context), and reports problems on stderr. The record code lives in
<infra>/scripts/agent-host/worktree_owner.py, found from this file's real path.
"""

import json
import os
import sys


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        print("worktree-lease: hook input is not JSON; nothing done", file=sys.stderr)
        return 0
    if not isinstance(payload, dict):
        return 0
    event = payload.get("hook_event_name")
    if event in ("SessionEnd", "sessionEnd"):  # Claude Code, Cursor
        if payload.get("reason") == "clear":
            return 0
        what = "end"
    elif event in ("SessionStart", "sessionStart"):
        what = "start"
    else:
        return 0
    infra = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
    sys.path.insert(0, os.path.join(infra, "scripts", "agent-host"))
    try:
        import worktree_owner as wo
    except ImportError as e:
        print(f"worktree-lease: cannot load worktree_owner from {infra}: {e}", file=sys.stderr)
        return 0
    env = dict(os.environ)
    session = str(payload.get("session_id") or payload.get("conversation_id") or "")
    host = env.get("CLAUDE_CODE_HOST_SESSION_ID", "")
    reason = str(payload.get("reason") or payload.get("source") or "")
    try:
        changed, problems = wo.session_event(env, what, session, host, reason)
    except Exception as e:  # never break a session over its records
        print(f"worktree-lease: {type(e).__name__}: {e}", file=sys.stderr)
        return 0
    for p in problems:
        print(f"worktree-lease: {p}", file=sys.stderr)
    if changed and what == "end":
        print(f"worktree-lease: ended {len(changed)} worktree record(s) of session {session}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
