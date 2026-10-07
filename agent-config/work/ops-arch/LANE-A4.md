# LANE-A4 — 工作区根的计划 / 评审 / 任务文件进版本控制

ADR §8。仓库：bifrost-trade-infra，**直接推 main**（纯文档）。

> **开工前提已满足**：Owner 2026-10-07 确认这些文件可以放进公开仓库。扫描（第 1 步）照做，命中的仍然不搬。

## 事实

工作区根 `/Users/vision-mac-trader/Desktop/stocks` 不是 git 仓库。以下文件放在根上，没有版本控制，只存在于 Mac Pro：
`PLAN-*.md`、`REVIEW-*.md`、`REQUEST-*`（含一个目录）、`LEDGER-*.md`，以及整个 `cursor-tasks/`（含 `reports/`）。
根上的 `CLAUDE.md`、`AGENT_FACTS.md` 等已经是指向 `bifrost-trade-infra/agent-config/` 的符号链接（见 `agent-config/README.md`）。

## 要做

1. **先扫描**每个文件，不能进公开仓库的内容一律不搬：令牌、密码、带密码的连接串、kubeconfig、ntfy topic、账户内容与金额（`\$[0-9,]+`、余额、持仓数量）。命中的文件留在原处，报告里列出文件与行。
2. 搬到 `bifrost-trade-infra/agent-config/work/`（保持原名），原位置换成同名符号链接，所有现有引用路径不变。`cursor-tasks/` 整个目录最后一步搬，用一条命令完成 `mv` 与 `ln -s`。
3. `agent-config/README.md` 的「布局与链接」表与「重建符号链接」命令补上这些项。
4. 只提交搬进来的文件（逐个列出路径），不要顺带提交别人在这些目录里新写的文件。

## 不做

不改文件内容（扫描命中的只报告，不改写）。不动 `agent-config/work/ops-arch/`。

## 验收

- `ls -l /Users/vision-mac-trader/Desktop/stocks/PLAN-phase0-foundation-2026-10-05.md` 显示符号链接指向 `bifrost-trade-infra/agent-config/work/`；
- `git -C bifrost-trade-infra ls-files agent-config/work | wc -l` 等于报告里列的文件数（不含 ops-arch）。
