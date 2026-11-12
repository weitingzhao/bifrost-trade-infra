#!/usr/bin/env python3
"""Session hooks feed the heartbeat (R5:5.5-12 §4.3); check-governance-consistency.sh §5 calls this.

Claude: SessionStart, PreCompact, SessionEnd and StopFailure (§12 D4) each run
thread-heartbeat.js, and the SessionEnd one names its own timeout (§12 D11).
Without a collector token these hooks send nothing; the check is about the
wiring only. The workspace-level Cursor side was deleted in cleanup wave 2
(2026-11-12), so there is no Cursor hooks file to check.

    python3 check_session_hooks.py <claude settings.json>
"""
import json
import sys
from pathlib import Path

HEARTBEAT = "thread-heartbeat.js"
CLAUDE_EVENTS = ("SessionStart", "PreCompact", "SessionEnd", "StopFailure")
# §12 D11: without its own timeout a SessionEnd hook is cancelled; 10 seconds is the
# calibrated value that lets it finish (the hook gives up after 5 s, plus process start).
MIN_SESSION_END_TIMEOUT = 10


def heartbeat_hooks(entries, nested):
    """The hook entries of one event that run the heartbeat script."""
    found = []
    for entry in entries if isinstance(entries, list) else []:
        for hook in (entry.get("hooks", []) if nested else [entry]) if isinstance(entry, dict) else []:
            if isinstance(hook, dict) and HEARTBEAT in str(hook.get("command", "")):
                found.append(hook)
    return found


def valid_timeout(value):
    # A whole number of seconds: not a bool (True is an int in Python), not a float, not below the floor.
    return type(value) is int and value >= MIN_SESSION_END_TIMEOUT


def problems(claude_settings):
    out = []
    claude = (claude_settings or {}).get("hooks", {})
    for event in CLAUDE_EVENTS:
        if not heartbeat_hooks(claude.get(event), True):
            out.append(f".claude/settings.json 未接线 thread-heartbeat.js 到 {event}")
    for hook in heartbeat_hooks(claude.get("SessionEnd"), True):
        if not valid_timeout(hook.get("timeout")):
            out.append(f".claude/settings.json 的 SessionEnd 心跳 timeout 须为不小于 {MIN_SESSION_END_TIMEOUT} 的整数秒（§12 D11），现为 {json.dumps(hook.get('timeout'))}")
    return out


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1].strip(), file=sys.stderr)
        return 2
    found = problems(json.loads(Path(argv[1]).read_text()))
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
