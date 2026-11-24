#!/usr/bin/env python3
"""Put the seat's identity card in front of the agent (Station, Owner law 90, 2026-11-21).

The card itself is Crew's (charters/seats.yaml + charters/cards/<id>.yaml, rendered by
scripts/render-card.py). Station only delivers it, at three moments:

  SessionStart (startup / resume / clear / compact): the whole card, so a fresh session and a
      session that has just been compacted both start from the same boundaries.
  PreToolUse on the ask-a-person tools: a short reminder (what I decide alone, my walls)
      before the agent stops to ask someone. It never blocks and never allows: no
      permissionDecision is returned, so the normal permission flow is unchanged.

Which seat: CLAUDE_CODE_HOST_SESSION_ID (the sidebar id, local_...) matched against the
`session` column of seats.yaml. A session that is not in the table gets the way in instead
(AGENTS.md -> CLAUDE.md -> charters/README.md), which is what a temporary seat needs.

Fail-soft: any error prints nothing and exits 0. A broken card must not break a session.
"""
import json
import os
import pathlib
import subprocess
import sys

AGENT_CONFIG = pathlib.Path(__file__).resolve().parents[2]
SEATS = AGENT_CONFIG / 'charters' / 'seats.yaml'
CARDS = AGENT_CONFIG / 'charters' / 'cards'
RENDER = AGENT_CONFIG / 'scripts' / 'render-card.py'

WAY_IN = (
    '本会话不在席位表里（agent-config/charters/seats.yaml 的 session 栏，侧栏号 {sid}）。\n'
    '进门：AGENTS.md → CLAUDE.md（规矩和硬边界）→ agent-config/charters/README.md（各线管什么）。\n'
    '活从哪来、交到哪：bifrost-trade-infra/docs/AGENT_WORK.md（任务书 BRIEF.md 由请你的主人席位给，交回给它）。\n'
    '你若是被某个主人席位请来的临时席位：照它给的任务书做，交回给它；边界以 CLAUDE.md §3、§5 为准。'
)
ASK_HEAD = '你正要停下来找人。先对一下自己的身份卡（法 90：权限内的事自己定，不问别人）：'
ASK_TAIL = '要问的是权限外的事，先过 .claude/skills/owner-decision-check/。'


def seat_for(session_id):
    if not session_id or not SEATS.is_file():
        return None
    import yaml  # only needed once a seats table exists
    for s in (yaml.safe_load(SEATS.read_text()) or {}).get('seats', []):
        if s.get('session') == session_id and (CARDS / f"{s.get('id')}.yaml").is_file():
            return s.get('id')
    return None


def full_card(seat):
    r = subprocess.run([sys.executable, str(RENDER), seat], capture_output=True, text=True, timeout=5)
    return r.stdout.strip() if r.stdout.strip() else None


def ask_reminder(seat):
    import yaml
    c = yaml.safe_load((CARDS / f'{seat}.yaml').read_text()) or {}
    lines = [ASK_HEAD, '我自己定、不用问：'] + ['  - ' + x for x in c.get('decide_alone', [])]
    lines += ['墙：'] + ['  - ' + x for x in c.get('walls', [])]
    return '\n'.join(lines + [ASK_TAIL])


def context_for(payload, session_id):
    event = payload.get('hook_event_name', '')
    seat = seat_for(session_id)
    if event == 'SessionStart':
        card = full_card(seat) if seat else None
        return card or WAY_IN.format(sid=session_id or '无')
    if event == 'PreToolUse':
        return ask_reminder(seat) if seat else None
    return None


def main():
    try:
        payload = json.loads(sys.stdin.read() or '{}')
        text = context_for(payload, os.environ.get('CLAUDE_CODE_HOST_SESSION_ID', ''))
        if text:
            print(json.dumps({'hookSpecificOutput': {
                'hookEventName': payload.get('hook_event_name'), 'additionalContext': text}}, ensure_ascii=False))
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
