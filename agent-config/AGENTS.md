# AGENTS.md — Bifrost 工作区（`/stocks`）

Instructions for **Claude Code, Codex**, and other coding agents working in this workspace.

本文件只是入口，不写规则正文。规则只有一份，在下面列出的文件里；和本文件不一致时以它们为准。

## 先读什么

| 你是 | 已经自动加载 | 开工前还要读 |
|------|-------------|-------------|
| Claude Code | `CLAUDE.md` | 无 |
| Codex、Cursor 和其他 Agent | 只有本文件 | `CLAUDE.md` 全文、`AGENT_FACTS.md` |

- **规则**：`CLAUDE.md`（工作区级的 Cursor 规则副本已在 2026-11-12 删除，规则只有这一份）。
- **事实**：`AGENT_FACTS.md`：仓库清单、端口、已退役实体、运行环境、权威源链。
- **活从哪来、交到哪**：`bifrost-trade-infra/docs/AGENT_WORK.md`。活由请你的主人席位用任务书 `BRIEF.md` 给，做完交回给它；计划树不是领活入口。
- **要办一件事，找谁、怎么办**：能力目录 `bifrost-trade-infra/agent-config/CAPABILITIES.md`，按事查 `python3 bifrost-trade-infra/scripts/station/howto.py find <关键词>`（例：`find 叫醒 4090`、`find 发信`）。查不到的找工坊（`roster:11-station`）。
- **办一件事要带什么**（合入 main 等）：`python3 bifrost-trade-infra/scripts/station/howto.py`；推之前跑同目录的 `precheck.py <检出目录>`。
- **Owner 的吐槽、痛点、需求**：在一个领域开工前先读自己领域的议题（MCP `get_owner_issues`，`to` 填领域 id）；收集是自动的，不用手抄。见 `CLAUDE.md` §5「Owner 的吐槽、痛点、需求」。
- **你坐哪个席位**：`bifrost-trade-infra/agent-config/charters/seats.yaml` 按会话号对；不在表里，就是被某个主人席位请来的临时 Agent，照它的任务书做。

## 硬边界在哪里

| 边界 | 位置 |
|------|------|
| 语言（对话用中文，UI 字符串和代码标识符用英文） | `CLAUDE.md` 开头 |
| D10 交易执行冻结 | `CLAUDE.md` §3 |
| 集群写操作走平台动作 | `CLAUDE.md` §3「集群写操作」 |
| Dev 服务只用 `bdev` 管 | `CLAUDE.md` §4 |
| 共享工作树：只逐个暂存自己改过的文件 | `CLAUDE.md` §5「共享工作树」 |
| 发布窗口：推 Trade 仓库 main 或起 deliver 之前先看 | `CLAUDE.md` §5「发布窗口」 |
| 发版和 PROD DDL 要 Owner 批准：先点头，或在 Console 上批审批单；platform 的 PROD 在签名规则覆盖时除外 | `CLAUDE.md` §5「放行规则只省『复制到终端』」 |

这些边界由 `scripts/agent-guard/preflight.js` 机械拦截。被拦下时不要绕过，也不要改 guard 文件，直接报告 Owner。

## 各家的接线

| Agent | 闸门接在哪里 | 说明 |
|-------|-------------|------|
| Claude Code | `.claude/settings.json` 的 `PreToolUse` | `CLAUDE.md` §7 |
| Codex | `~/.codex/hooks.json` 的 `PreToolUse` | `bifrost-trade-infra/agent-config/codex/README.md` |

## 子仓库

子仓库可能有自己的 `CLAUDE.md` 或 `AGENTS.md`（例如 `bifrost-trade-frontend/AGENTS.md`），在那个仓库里工作时一并读。

## 维护

实体文件是 `bifrost-trade-infra/agent-config/AGENTS.md`，工作区根的 `AGENTS.md` 是指向它的链接（重建命令见 `agent-config/README.md`）。这里只放指针；规则改在 `CLAUDE.md`。
