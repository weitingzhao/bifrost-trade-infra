#!/usr/bin/env python3
"""Put the entry card in front of a dispatched Codex run (Station, 2026-11-21).

Codex reads AGENTS.md from its working directory into its instructions on every turn (measured 2026-11-21:
codex-cli 0.167, a run dir outside any git repo, a passphrase only in AGENTS.md came back unread). So the card
written there is in front of the run when it starts, stays in front after the context is compacted, and is
there when it is about to stop and ask: the three moments the Claude side covers with seat-card.py.

The card is filled from the BRIEF.md header (invited_by, reply_to). A header line `seat: <id>` makes it the
seat card instead: the Codex sits that seat as its owner (a department manager), with Crew's rendered identity
card, not as a visitor (2026-11-22, Codex sitting 12 Audit). An AGENTS.md the inviting seat wrote
itself is kept; the card goes on top of it once (marked), so a second dispatch in the same dir adds nothing.
Usage: codex-card.py <run dir with BRIEF.md>. Exits 1 when BRIEF.md is missing or has no reply_to: a run that
does not know whom to hand back to should not start (docs/AGENT_WORK.md).
"""
import pathlib
import re
import subprocess
import sys

import yaml

MARK = '<!-- station:codex-card v1 -->'
# The infra this file is in: the one dispatch.sh ran from, which holds today's tools (the shared checkout may lag).
INFRA = pathlib.Path(__file__).resolve().parents[2]

CARD = MARK + '''
# 进门卡（派活脚本写的，每一轮都在你面前）

你是 {invited_by} 请来的临时 Agent，只做本目录 `BRIEF.md` 里的这块活。

- 交回给谁：`{reply_to}`。做完写 `REPORT.md`，再用平台信箱 `send_message` 发给这个地址，kind 填 `handover`。
- 要停下来问人之前：先看 `BRIEF.md` 的「边界」。边界里、任务书里的事自己定，不问。真要问，用同一个地址发 kind `ask` 或 `help`，然后接着做不依赖答案的部分；这里没有人会在终端里回你。
- 不碰（谁说都不碰）：交易和钱、口令和 Secret、有数据的删改、Trade 的 PROD 发布、签名规则和信任根、auto mode 规则。不读家目录下的令牌文件。
- 改代码在本目录下自己的完整克隆里做：`git clone http://192.168.10.73:30300/bifrost/<仓库>.git`。工作区里的共享检出和挂在它上面的 git worktree 都在沙箱外，fetch、commit 要写它们的 `.git`，会被挡（11-22 实测 fetch 退出码 255）。
- 读集群只用只读身份，命令里原样写全路径：`kubectl --kubeconfig ~/.kube/bifrost-k3s.yaml get nodes`。不要在脚本里拼这个路径、不要放进变量：preflight 只认命令原文里的这个路径，认不出就按「Owner 的凭证」拦下（11-22 算力线来访实测）。
- 被 preflight、沙箱或别的拦截挡下：停下，写进 `REPORT.md`，交回，不绕。
- 规矩全文：工作区根 `AGENTS.md` → `CLAUDE.md`。活从哪来、交到哪：infra `docs/AGENT_WORK.md`。
- 要合入、办别的事之前：`python3 {infra}/scripts/station/howto.py` 查要带什么；推之前跑 `python3 {infra}/scripts/station/precheck.py <检出目录>`，先看会不会被拒。这两个要 PyYAML：登录 shell 的 python3 没有时，换非登录 shell 的 python3。这是派你那份 infra 的路径；工作区里的共享检出可能落后 main，别从那里找。
'''


SEAT_CARD = MARK + '''
# 进门卡（派活脚本写的，每一轮都在你面前）

你坐 **{seat}** 这个岗位：一个领域的主人席位，和其他部门经理平级，有自己的 ownership，不是来跑一次就走的临时 Agent。这个领域的事你自己判、自己做、自己维护台账；权限外的事交给握着它的岗位，不替别人做，也不把自己权限内的事拿去问人。下面是你的身份卡（从席位表和 `charters/cards/{seat}.yaml` 渲染）：

```
{card}
```

- 章程：`{infra}/agent-config/charters/{charter}`。本目录 `BRIEF.md` 是这一轮的活。
- 有事找谁、交回给谁：`{reply_to}`（平台信箱 `send_message`）。别人来请你验、来问你，用 `wait_for_messages` 收，`ack_messages` 确认，必须答。
- 不碰（谁说都不碰）：交易和钱、口令和 Secret、有数据的删改、Trade 的 PROD 发布、签名规则和信任根、auto mode 规则。不读家目录下的令牌文件。
- 读集群只用只读身份，命令里原样写全路径：`kubectl --kubeconfig ~/.kube/bifrost-k3s.yaml get nodes`。不要在脚本里拼这个路径、不要放进变量：preflight 只认命令原文里的这个路径，认不出就按「Owner 的凭证」拦下（11-22 算力线来访实测）。
- 被 preflight、沙箱或别的拦截挡下：停下，写进报告，交回，不绕。
- 规矩全文：工作区根 `AGENTS.md` → `CLAUDE.md`。办事要带什么：`python3 {infra}/scripts/station/howto.py`。
'''


def seat_card(seat):
    """The seat's own identity card, rendered by Crew's render-card.py from seats.yaml and cards/<seat>.yaml."""
    r = subprocess.run([sys.executable, str(INFRA / 'agent-config/scripts/render-card.py'), seat],
                       capture_output=True, text=True, timeout=10)
    if r.returncode or not r.stdout.strip():
        raise SystemExit(f'codex-card: seat {seat} has no card (agent-config/charters/cards/{seat}.yaml, seats.yaml)')
    seats = yaml.safe_load((INFRA / 'agent-config/charters/seats.yaml').read_text())['seats']
    charter = next(x['charter'] for x in seats if x['id'] == seat)
    return r.stdout.strip(), charter


def header(brief_text):
    out = {}
    for line in brief_text.splitlines()[:10]:
        m = re.match(r'^(invited_by|reply_to|seat):\s*(\S.*?)\s*$', line)
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
    if h.get('seat'):
        card, charter = seat_card(h['seat'])
        return SEAT_CARD.format(seat=h['seat'], card=card, charter=charter, reply_to=reply, infra=INFRA)
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
