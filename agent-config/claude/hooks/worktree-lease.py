#!/usr/bin/env python3
"""Claude Code hook: worktree end records (W-31 round 4, 4.6 S3; CUT-lifecycle-2026-10-24.md §4.2).

    SessionEnd    ended_at on every worktree registered to this session (new-worktree.sh
                  --session, which defaults to CLAUDE_CODE_SESSION_ID), or to its host
                  session (CLAUDE_CODE_HOST_SESSION_ID, the Desktop thread). Not on reason
                  "clear": the thread goes on in a new session, so the work has not ended.
    SessionStart  first the session's "active since" marker, then renew those records: a
                  resumed session (or the one that follows a /clear in the same thread) voids
                  an earlier end before it uses anything, and the marker keeps the worktree
                  in use for the sweep even if a renewal fails. A record of another session
                  whose worktree holds the hook's cwd is marked as foreign use (kept until
                  new-worktree.sh --take). See scripts/agent-host/worktree_sessions.py.

A sweep removes a worktree only when its record says ended (worktree_owner.py), so a session
that dies without SessionEnd leaves its worktrees in use: the safe direction.

Not wired into any settings.json yet; the proposed wiring is in
agent-config/work/multi-agent/S3-hook-wiring-proposal-2026-10-24.md.

Cursor's sessionEnd / sessionStart payloads (conversation_id) are read the same way.
Claude Code gives all SessionEnd hooks 1.5 s unless a hook sets "timeout"; the proposal sets one.

Never blocks a session (SessionStart cannot be blocked by any hook output; exit 2 only shows
stderr to the user). It exits 0 and prints nothing on stdout when all went well. When a
SessionStart could not publish the session's marker, left worktrees that nothing protects,
or failed outright, it prints one JSON object: "systemMessage" for the user and
hookSpecificOutput.additionalContext for the session, the same text, which starts with the
instruction to use none of the worktrees before new-worktree.sh --renew succeeds for them
(reviews 552 A2, 553 D2). SessionEnd output is discarded by
Claude Code; a failed end only leaves worktrees in use, so it reports on stderr. The record
code lives in <infra>/scripts/agent-host/worktree_sessions.py, found from this file's real path.
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
        import worktree_sessions as ws
    except ImportError as e:
        return warn(what, f"cannot load worktree_sessions from {infra}: {e}", [])
    env = dict(os.environ)
    session = str(payload.get("session_id") or payload.get("conversation_id") or "")
    host = env.get("CLAUDE_CODE_HOST_SESSION_ID", "")
    reason = str(payload.get("reason") or payload.get("source") or "")
    try:
        changed, problems, unsafe, published = ws.session_event(env, what, session, host, reason, cwd=str(payload.get("cwd") or ""))
    except Exception as e:  # never break a session over its records
        return warn(what, f"{type(e).__name__}: {e}", [])
    for p in problems:
        print(f"worktree-lease: {p}", file=sys.stderr)
    if changed and what == "end":
        print(f"worktree-lease: ended {len(changed)} worktree record(s) of session {session}", file=sys.stderr)
    if what == "start" and (unsafe or not published):
        return warn(what, "; ".join(problems[:3]) or "the session marker was not published", unsafe)
    return 0


MAX_PATHS = 20
MAX_WHY = 400


def warn(what: str, why: str, unsafe: list) -> int:
    """A SessionStart that could not record the resume: say so to the user and the session.
    The instruction comes first, then the worktrees (at most MAX_PATHS, with how many more),
    then the error (at most MAX_WHY characters), so a cut never loses the instruction
    (review 553 D2). Printed when the marker could not be published, when worktrees were left
    with nothing protecting them, or when the hook failed outright."""
    print(f"worktree-lease: {why}", file=sys.stderr)
    if what != "start":
        return 0
    head = ("Use none of these worktrees before bifrost-trade-infra/scripts/agent-host/new-worktree.sh --renew <dir> "
            "succeeds for it: the lifecycle sweep may remove them, because this session's resume could not be recorded.")
    if unsafe:
        shown = list(unsafe[:MAX_PATHS])
        more = len(unsafe) - len(shown)
        names = "Worktrees: " + ", ".join(shown) + (f" (and {more} more)" if more else "") + "."
    else:
        names = "Worktrees: every worktree registered to this session."
    detail = why if len(why) <= MAX_WHY else why[:MAX_WHY] + "..."
    text = f"{head} {names} Cause: {detail}"
    print(json.dumps({"systemMessage": text, "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
