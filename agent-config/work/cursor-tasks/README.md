# Cursor 还债任务 — 共用规则（Claude Code 写，2026-10-07）

Owner 把 Trade 技术债的**实现**交给 Cursor，Claude Code 只做**验收和台账**。
每个任务文件（`LANE-*.md`）是一条道；一个 Cursor 会话做一条道，做完写报告，停。

## 开工前

1. 读工作区根的 `CLAUDE.md`（§3 D10、§5 共享工作树与发布窗口）和 `AGENT_FACTS.md` §8c。Cursor 侧规则在 `.cursor/rules/workspace.mdc`，preflight 钩子照常生效——被拦就停下写进报告，**不要绕过、不要改 guard 文件**。
2. 每一项的完整内容（Claim / Evidence / Fix / Ratchet）在台账里：
   `git -C bifrost-trade-infra fetch -q origin && git -C bifrost-trade-infra show origin/main:agent-config/TECH_DEBT.md`，找 `### TD-n` 一节。
   已有防线：同目录 `RATCHETS.md`。
3. **先核实 Claim 在当前代码上还成立**（读 `文件:行`），不成立就在报告里写「不成立 + 证据」，不改代码。

## 硬规则

- **不在共享 checkout 里改**（`/Users/vision-mac-trader/Desktop/stocks/<repo>` 是多会话共用的）。每个仓库自己开 worktree：
  `git -C <repo> fetch -q origin && git -C <repo> worktree add -b <分支> /tmp/cursor-<道>-<repo> <起点>`，做完 `git worktree remove`。
- 暂存与提交同一步、只列自己的文件：`git commit -F msg -- <file>…`（新文件先单独 `git add <file>`）。
  **禁止** `git add -A / . / -u`、`git commit -a`、`git stash`。
- 提交信息末尾带 `Change-Id`：worktree 里 husky 不执行，跑
  `sh /Users/vision-mac-trader/Desktop/stocks/scripts/git-hooks/lineage.sh commit-msg <msgfile>` 补尾注。
- 门禁（每个退出码单独看，不要 `| tail` 之后再 `&&` 提交）：
  Python `make lint && make test` · TS `npx tsc -b && npm run lint && npx vitest run && npm run build` · Go `go build ./... && go vet ./... && go test ./...`。
  console worktree 先 `ln -s /Users/vision-mac-trader/Desktop/stocks/bifrost-platform/console/node_modules console/node_modules`。
- **每一项都要一条防线**（测试 / lint / CI 检查），或在报告里写明为什么做不了。
- 不打印、不提交任何秘密；12 个仓库都是 PUBLIC。测试夹具一律编造。
- D10：不碰下单路径、daemon 扩容、`ib:operator:cmd`、`POST /control/*`。

## 推到哪里（不发版）

| 改动 | 推送 |
|---|---|
| bifrost-platform、bifrost-ui | **只推分支**（各道文件写了分支名），不推 main |
| bifrost-trade-infra 的 `k8s/`、`monitoring` 等会被 Argo 同步的路径 | **只推分支**（推 main 等于改集群） |
| bifrost-trade-infra 的纯文档 / 脚本 | 可以推 main：`bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`（同一条命令） |

**一律不做**：起任何 deliver / PipelineRun、`kubectl apply / delete / rollout`、`release.sh stg|prod|dev`、
任何数据库写入（DEV 也不写）、改 `agent-config/TECH_DEBT.md` / `RATCHETS.md`（台账归 Claude Code 管；要改的事实写进报告）。
需要这些的，准备好分支或脚本，写进报告「要 Owner 批」一栏，停。

## 第 2 轮（2026-10-07 起）的变更 —— 优先于上面的表

- **所有代码一律只推分支** `cursor/<道名小写>-<仓库简称>`（例如 `cursor/r2-research`），**任何仓库都不推 main**（包括 Trade 仓库）。Claude Code 验收后负责 rebase 和合并。
  例外：bifrost-trade-infra 的**纯文档**改动仍可推 main（`release.sh window && git push …` 同一条命令）。
- Owner 10-07 批准的是「实现」：改公开接口（TD-91、TD-102、TD-123）已获批，照常 bump 版本并列出受影响的下游。
- 数据库：可以**只读**查询 DEV / GS / PROD（`PGOPTIONS=-cdefault_transaction_read_only=on`）来列范围、做 dry-run 统计；**任何写入（包括 DEV）、DDL、kubectl apply / delete、发版都不做**，准备好 SQL / 清单 / 脚本写进报告「要 Owner 批」。
- 跨道依赖写在各道文件里；碰到别的道正在改的文件，停下写进报告，不要去改。

## 报告（做完写这个文件，然后停）

`cursor-tasks/reports/<道名>.md`，每一项一节：

```
## TD-n
- Claim：成立 / 不成立（证据 文件:行）
- 改动：仓库 · 分支 · 完整 SHA
- 防线：文件路径 + 测试名
- 门禁：命令 → 结果（passed 数）
- 验收：一条命令 + 预期结果（Claude Code 会照跑）
- 要 Owner 批：没有 / 具体动作
- 后续：新发现的债（文件:行 + 一句话）或「无后续」
```

报告写完后，Owner 告诉 Claude Code「Cursor 做完了 <道名>」，Claude Code 会照报告重跑验收、写台账。
