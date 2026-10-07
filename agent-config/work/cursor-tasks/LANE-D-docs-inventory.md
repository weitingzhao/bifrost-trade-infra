# LANE-D — 文档事实更正 + 孤儿模块清单（2 项，几乎只读）

先读 `cursor-tasks/README.md`。报告写到 `cursor-tasks/reports/LANE-D.md`。

## TD-241 — 治理文档里已经不成立的事实

台账 `### TD-241` 列了要改的行。**本道不直接改** `RATCHETS.md` / `TECH_DEBT.md`（Claude Code 管）和 `CLAUDE.md` / `AGENT_FACTS.md` / `agentProtocolCatalog.ts`（治理层，双轨 parity）。
做法：逐条实测（读代码 / 只读 GET / `kubectl get` 只读），在报告里给出「原文 → 应改为 → 证据」表。
其中 D-IB-Heal 的规则措辞要 Owner 定，写进「要 Owner 批」。

## TD-243 — 42 个前端孤儿模块（Owner 10-07 已批准删，但**按目录分批、每批先给 Owner 过目**）

在 `bifrost-trade-frontend` 的干净 worktree（起点 origin/main，分支 `cursor/td-orphans`）里：
1. 用仓库现有的孤儿检测（`KNOWN_ORPHANS`，`grep -rn KNOWN_ORPHANS src`）重新算一遍当前孤儿名单；
2. 按目录分批（每批 ≤ 10 个），每个文件写：路径、行数、最后一次有意义提交（`git log -1 --format='%h %s'`）、有没有被测试引用、看起来是「被替换了」还是「没建完」；
3. **只写报告，不删文件**。Owner 在报告上逐批勾选后，再开一次 Cursor 会话按勾选删除并从 `KNOWN_ORPHANS` 移除。
