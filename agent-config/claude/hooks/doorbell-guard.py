#!/usr/bin/env python3
"""A seat does not go idle without its doorbell armed (Station, ISSUE-2 / LAW-6 eight, 2026-11-25; Owner approved in the Station thread 11-25).

On Stop: if this session is a seat with mailbox: registered in seats.yaml and no doorbell.ts runs
under this session's claude process, block this stop once and say how to arm it.
Never loops (stop_hook_active lets go). Fail-soft: any error prints nothing and exits 0.
"""
import json
import os
import pathlib
import subprocess
import sys

AGENT_CONFIG = pathlib.Path(__file__).resolve().parents[2]
SEATS = AGENT_CONFIG / 'charters' / 'seats.yaml'
ARM = ('npx --prefix bifrost-platform/mcp/platform tsx '
       'bifrost-platform/mcp/platform/src/doorbell.ts --minutes 1440')
REASON = (
    '门铃没挂：你停下以后，平台信箱里的来信和审批结果都叫不醒你（ISSUE-2，LAW-6 八）。\n'
    '先在工作区根用 Bash 的 run_in_background 起它（不要用 &）：\n  ' + ARM + '\n'
    '起了再停。响了以后读信、处理，再挂一次；这个钩子每次停之前都会查。'
)


def seat_with_mailbox(session_id):
    if not session_id or not SEATS.is_file():
        return False
    import yaml
    for s in (yaml.safe_load(SEATS.read_text()) or {}).get('seats', []):
        if s.get('session') == session_id and s.get('mailbox') == 'registered':
            return True
    return False


def process_table():
    out = subprocess.run(['ps', '-axo', 'pid=,ppid=,command='],
                         capture_output=True, text=True, timeout=5).stdout
    table = {}
    for line in out.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 2:
            table[int(parts[0])] = (int(parts[1]), parts[2] if len(parts) > 2 else '')
    return table


def claude_ancestor(table, pid):
    seen = set()
    while pid in table and pid not in seen:
        seen.add(pid)
        ppid, cmd = table[pid]
        exe = os.path.basename(cmd.split()[0]) if cmd else ''
        if exe == 'claude' or '/claude ' in cmd + ' ' or 'claude-code' in cmd:
            return pid
        pid = ppid
    return None


def doorbell_under(table, root):
    children = {}
    for pid, (ppid, _) in table.items():
        children.setdefault(ppid, []).append(pid)
    stack = list(children.get(root, []))
    while stack:
        pid = stack.pop()
        if 'doorbell.ts' in table[pid][1]:
            return True
        stack.extend(children.get(pid, []))
    return False


def decide(payload, session_id, table, my_pid):
    if payload.get('stop_hook_active'):
        return None
    if not seat_with_mailbox(session_id):
        return None
    root = claude_ancestor(table, my_pid)
    if root is None or doorbell_under(table, root):
        return None
    return {'decision': 'block', 'reason': REASON}


def main():
    try:
        payload = json.loads(sys.stdin.read() or '{}')
        out = decide(payload, os.environ.get('CLAUDE_CODE_HOST_SESSION_ID', ''),
                     process_table(), os.getpid())
        if out:
            print(json.dumps(out, ensure_ascii=False))
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
