#!/usr/bin/env python3
"""Put the entry card in front of a dispatched Codex run (Station, 2026-11-21).

Codex reads AGENTS.md from its working directory into its instructions on every turn (measured 2026-11-21:
codex-cli 0.167, a run dir outside any git repo, a passphrase only in AGENTS.md came back unread). So the card
written there is in front of the run when it starts, stays in front after the context is compacted, and is
there when it is about to stop and ask: the three moments the Claude side covers with seat-card.py.

The card is filled from the BRIEF.md header (invited_by, reply_to). An AGENTS.md the inviting seat wrote
itself is kept; the card goes on top of it once (marked), so a second dispatch in the same dir adds nothing.
Usage: codex-card.py <run dir with BRIEF.md>. Exits 1 when BRIEF.md is missing or has no reply_to: a run that
does not know whom to hand back to should not start (docs/AGENT_WORK.md).
"""
import pathlib
import re
import sys

MARK = '<!-- station:codex-card v1 -->'
# The infra this file is in: the one dispatch.sh ran from, which holds today's tools (the shared checkout may lag).
INFRA = pathlib.Path(__file__).resolve().parents[2]

CARD = MARK + '''
# 进门卡（派活脚本写的，每一轮都在你面前）

你是 {invited_by} 请来的临时 Agent，只做本目录 `BRIEF.md` 里的这块活。

- 交回给谁：`{reply_to}`。做完写 `REPORT.md`，再用平台信箱 `send_message` 发给这个地址，kind 填 `handover`。
- 要停下来问人之前：先看 `BRIEF.md` 的「边界」。边界里、任务书里的事自己定，不问。真要问，用同一个地址发 kind `ask` 或 `help`，然后接着做不依赖答案的部分；这里没有人会在终端里回你。
- 不碰（谁说都不碰）：交易和钱、口令和 Secret、有数据的删改、Trade 的 PROD 发布、签名规则和信任根、auto mode 规则。不读家目录下的令牌文件。
- 被 preflight、沙箱或别的拦截挡下：停下，写进 `REPORT.md`，交回，不绕。
- 规矩全文：工作区根 `AGENTS.md` → `CLAUDE.md`。活从哪来、交到哪：infra `docs/AGENT_WORK.md`。
- 要合入、办别的事之前：`python3 {infra}/scripts/station/howto.py` 查要带什么；推之前跑 `python3 {infra}/scripts/station/precheck.py <检出目录>`，先看会不会被拒。这是派你那份 infra 的路径；工作区里的共享检出可能落后 main，别从那里找。
'''


def header(brief_text):
    out = {}
    for line in brief_text.splitlines()[:10]:
        m = re.match(r'^(invited_by|reply_to):\s*(\S.*?)\s*$', line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def card_for(run_dir):
    run_dir = pathlib.Path(run_dir)
    brief = run_dir / 'BRIEF.md'
    if not brief.is_file():
        raise SystemExit(f'codex-card: no BRIEF.md in {run_dir}')
    h = header(brief.read_text())
    reply = h.get('reply_to', '')
    if not reply.startswith('thread:') or '<' in reply:
        raise SystemExit('codex-card: BRIEF.md has no reply_to: thread:<session> in its first lines (see BRIEF.template.md)')
    return CARD.format(invited_by=h.get('invited_by', '（任务书没写）'), reply_to=reply, infra=INFRA)


def write(run_dir):
    agents = pathlib.Path(run_dir) / 'AGENTS.md'
    card = card_for(run_dir)
    old = agents.read_text() if agents.is_file() else ''
    if MARK in old:
        return False
    agents.write_text(card + ('\n' + old if old else ''))
    return True


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    write(sys.argv[1])
