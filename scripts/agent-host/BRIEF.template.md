invited_by: <请它的主人席位 id，见 agent-config/charters/seats.yaml>
reply_to: thread:<那个主人的会话号>

# <这块活的名字>

<!-- Station 模板（2026-11-21）。主人席位复制到工作目录，改名 BRIEF.md，填尖括号里的内容；用不上的节删掉。
     一份任务书就是一块活：写不出「做完了怎么验」，说明切成了工序，先重切。只写目标、边界和怎么验，不写步骤。 -->

## 目标
<一两句：做完以后，什么东西变了、谁能用上>

## 边界
- 能碰的：<仓库、目录、环境>
- 不碰的：交易和钱、口令和 Secret、有数据的删改、Trade 的 PROD 发布、签名规则和信任根、auto mode 规则；<这块活另外不碰的>
- 规矩和硬边界在根 `CLAUDE.md`（Codex 从 `AGENTS.md` 进去）。被 preflight 或别的拦截挡下就停下，按下面「交回」报告，不绕。

## 做完了怎么验
- <可以自己重数的条件：测试、run 名、页面上看得到的东西>

## 交单要什么
- 做成了什么，证据（提交号、run 名）
- 没验什么
- 花了多少（时间、token）

## 交回
1. 报告写成本目录的 `REPORT.md`，按「交单要什么」写。
2. 平台信箱 `send_message`：`to` 填上面的 `reply_to`，kind 填 `handover`，正文一屏以内，写上 `REPORT.md` 的路径。
3. 中途卡住：同一个地址，kind 填 `ask` 或 `help`。
完整说明见 infra `docs/AGENT_WORK.md`。
