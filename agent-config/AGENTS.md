# AGENTS.md — Bifrost 工作区（`/stocks`）

Instructions for **Claude Code, Cursor Agent, Codex**, and other coding agents working in this workspace.

本文件只是入口，不写规则正文。规则只有一份，在下面列出的文件里；和本文件不一致时以它们为准。

## 先读什么

| 你是 | 已经自动加载 | 开工前还要读 |
|------|-------------|-------------|
| Claude Code | `CLAUDE.md` | 无 |
| Cursor Agent | `.cursor/rules/*.mdc` | 无 |
| Codex 和其他 Agent | 只有本文件 | `CLAUDE.md` 全文、`AGENT_FACTS.md` |

- **规则**：`CLAUDE.md`（Cursor 侧对等的是 `.cursor/rules/`）。
- **事实**：`AGENT_FACTS.md`：仓库清单、端口、已退役实体、运行环境、权威源链。

## 硬边界在哪里

| 边界 | 位置 |
|------|------|
| 语言（对话用中文，UI 字符串和代码标识符用英文） | `CLAUDE.md` 开头 |
| D10 交易执行冻结 | `CLAUDE.md` §3 |
| 集群写操作走平台动作 | `CLAUDE.md` §3「集群写操作」 |
| Dev 服务只用 `bdev` 管 | `CLAUDE.md` §4 |
| 共享工作树：只逐个暂存自己改过的文件 | `CLAUDE.md` §5「共享工作树」 |
| 发布窗口：推 Trade 仓库 main 或起 deliver 之前先看 | `CLAUDE.md` §5「发布窗口」 |
| 发版和 PROD DDL 要 Owner 先点头 | `CLAUDE.md` §5「放行规则只省『复制到终端』」 |

这些边界由 `scripts/agent-guard/preflight.js` 机械拦截。被拦下时不要绕过，也不要改 guard 文件，直接报告 Owner。

## 各家的接线

| Agent | 闸门接在哪里 | 说明 |
|-------|-------------|------|
| Claude Code | `.claude/settings.json` 的 `PreToolUse` | `CLAUDE.md` §7 |
| Cursor Agent | `.cursor/hooks.json` | `.cursor/rules/workspace.mdc` §4 |
| Codex | `~/.codex/hooks.json` 的 `PreToolUse` | `bifrost-trade-infra/agent-config/codex/README.md` |

## 子仓库

子仓库可能有自己的 `CLAUDE.md` 或 `AGENTS.md`（例如 `bifrost-trade-frontend/AGENTS.md`），在那个仓库里工作时一并读。

## 维护

实体文件是 `bifrost-trade-infra/agent-config/AGENTS.md`，工作区根的 `AGENTS.md` 是指向它的链接（重建命令见 `agent-config/README.md`）。这里只放指针；规则改在 `CLAUDE.md` 和 `.cursor/rules/`，两侧 parity 不变。
