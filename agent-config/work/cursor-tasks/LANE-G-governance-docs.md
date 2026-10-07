# LANE-G — 治理文档更正落地（TD-241，Owner 10-07 选 A）

先读 `cursor-tasks/README.md`。报告写到 `cursor-tasks/reports/LANE-G.md`。
更正表：`cursor-tasks/reports/LANE-D.md` 的 TD-241 一节（第 1–10d 行）。本道**例外地允许**改 `RATCHETS.md` / `TECH_DEBT.md`，但只改表里列的那些行。

## 要改的
1. **RATCHETS.md**：第 1、1b、2、3、4、5、6、7 行，按「应改为」一栏。
2. **TECH_DEBT.md**：TD-196 的「验收」行加 data-clone 那一条（第 9 行）。**不要**动别的条目和状态字段（台账由 Claude Code 管）。
3. **D-IB-Heal 措辞，方案 A**（第 10a 行）：
   - `agent-config/CLAUDE.md` §3 禁止项改为「**Agent** 不得写 `ib:operator:cmd`（任何模式）。系统内合法写入方：Daemon；platform-api 只发 `op=reconnect_all`（D-IB-Heal L1，SIGNED 2026-08-27）。其余 op 只能由 Daemon 发出」。
   - Cursor 侧 `agent-config/cursor/rules/trade-execution-freeze.mdc` 同步同一句；**两侧 parity-id 都 bump**，跑 `bash scripts/check-agent-config-parity.sh`。
   - `scripts/agent-guard/preflight.js` 只改注释（81、85 行附近），**不改任何匹配逻辑**。
   - `bifrost-platform/console/src/lib/architecture/agentProtocolCatalog.ts:105` → `'ib:operator:cmd write by an agent (platform-api reconnect_all is D-IB-Heal L1)'`；`bifrost-platform/api/internal/probe/probe.go:31` 的 Detail 同步。platform 改动**只推分支** `cursor/td-241`（另一个会话在发 platform）。
4. **AGENT_FACTS.md**：第 10b′ 行补 Grafana `.73:30883`、Dagster webserver `.73:30301`；第 10c 行按建议处理 data-warehouse MinIO 的三处（:202 的 namespace 清单不动，等 TD-237）。
5. **bifrost-trade-worker/CLAUDE.md:62**：按第 10d 行改。

## 推送
- infra（agent-config 与 scripts）、worker：可以推 main，`release.sh window && git push origin <sha>:refs/heads/main` 同一条命令；推之前 `git fetch` 并 rebase 到最新 origin/main（Claude Code 也在改 TECH_DEBT.md，冲突时只保留双方的改动、不覆盖）。
- platform：只推分支 `cursor/td-241`。

## 验收（写进报告）
`git -C bifrost-trade-infra show origin/main:agent-config/RATCHETS.md | grep -n 'namespace=~"bifrost-\.\*"\|0 error / 65\|ci-python-bifrost-trade-api-j5d4v'` → 无输出；parity 脚本 exit 0；platform 分支 `cd console && npx vitest run` 与 `cd api && go test ./internal/probe` 通过。
