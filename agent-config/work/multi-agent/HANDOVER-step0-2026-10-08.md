# 交接简报：W-31 第 0 步执行线程

- **写给**：Owner 在「Ops Platform 瘦身」完成后新开的执行线程（建议标题：「W-31 第 0 步」）。
- **来自**：多 Agent 协作线程（2026-10-08，CLI 会话 f316b296）。这个线程继续负责讨论和决策；执行交给你。
- **你的角色**：第 0 步期间暂代「参谋长」：拆道、派给 Cursor、照报告验收、整理要 Owner 决定的事。运行时建好之前，这个角色由线程人工担任。

## 开工前先读（按顺序）

1. 工作区根的 `CLAUDE.md`、`AGENT_FACTS.md` §8c。
2. `agent-config/ADR-ops-architecture.md`：§1（Owner 只做三件事）、§5（规则集与发版策略）、§12（多 Agent 协作，整节）。
3. `agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md`（v4），重点读第 10 节（第 0 步）。
4. `agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md`：本次要执行的计划（Owner 审过的版本以 git 为准）。
5. `agent-config/work/ops-arch/STATUS-*.md`：瘦身线程最后一版的状态，是第 1 天差异盘点的基线。
6. 记忆 `multi_agent_coordination_2026_10_08.md`：每个决定背后的来龙去脉。

## Owner 的工作方式（必须遵守）

- 一律用中文回复；UI 字符串和代码标识符用英文。
- **先讨论透，再落地**：方案选项里的「推荐」不等于落地许可；Owner 明说确认之后，才写任务、合分支、改配置（记忆 `feedback_discuss_before_landing`）。
- **Owner 只做三件事**：定目标、定规则、处理不可逆的事。送到他面前的每件事都要标明属于哪一件，并附上选项、推荐、以及不回复时会怎样。不要拿可以自动化的事去打扰他。
- **可见性**：要 Owner 知道的事，最终都要出现在 Console 上。在 D1 过渡层上线之前，先写进 WORK.md。
- 实现交给 Cursor（每条道一个会话，只推分支，写报告）；你照报告重跑验收，再合并（记忆 `feedback_cursor_implements_claude_verifies`）。

## 推送纪律（10-08 吃过亏）

- infra 的纯文档改动：在临时 worktree 里提交，用 `release.sh window && git push origin <sha>:refs/heads/main` 推送，推完把共享 checkout 用 `git merge --ff-only` 快进。**不要**先提交到共享 checkout 再推：一旦和远端分叉，`reset --keep` 会被 auto mode 拦下，只能让 Owner 手动对齐。
- 提交时只列自己改过的文件；新的 W-n 编号先在 WORK.md 登记，再派活。

## 第 1 天要做的

1. 按 `STEP0-PLAN` 第 1 节做差异盘点：只读，结果写回计划，标明哪些和 10-08 的数字不一样。
2. 按盘点结果修订计划，把修订点交给 Owner 确认。
3. Owner 确认后，在 WORK.md 里给 S0-1 … S0-9 分配 W-n 编号，写第 1 波的 Cursor 道：S0-1、S0-2、S0-8 的代码 rebase、S0-7 的代码 rebase、S0-4a。

## 不要碰的

- ops-arch 的范围：Console 的删减、W-32、W-33。
- Grok 留下的 LANE-N、LANE-M2，以及还债台账里观察中的项：这些归「还债试点」的第一个 mission，在运行时第 2 阶段处理，第 0 步不处理。
- D10，以及任何实盘交易相关的路径。
- 不在工作区根目录新建任何东西（S0-6 的守卫上线之前，靠自觉遵守）。

## 第 0 步做完之后

按 v4 第 12 节进入运行时第 0 阶段（单 Agent 基线）。开工前先和 Owner 确认，因为那时要建 `agentrt` 的表（属于架构级改动，要按 database-design 规范来）。
