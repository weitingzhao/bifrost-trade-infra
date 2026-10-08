# LANE-D1 — 第 4 阶段（后台部分）：工作项登记 + 提交自带工作项编号 + 进度接口

ADR §8。仓库：bifrost-trade-infra（分支 `cursor/d1-infra`）、bifrost-platform（分支 `cursor/d1-platform`，从最新 origin/main 开）。**本道不做 Console 页面**——⑦ Progress 页面等第 3 阶段（`cursor/phase3-platform`）合并后另开一道；本道只提供接口。

## 已定的规则（Owner 2026-10-07）

- 进度是**算出来的**，不人工维护。
- 工作项登记覆盖全部工作线：债（`agent-config/TECH_DEBT.md`，已有）+ 计划与 Cursor 任务（新）。五种状态、验收命令、待你签收沿用 TECH_DEBT 的格式。
- 每个提交带 `Work: <编号>` 尾注。

## 要做

1. **工作项登记（infra）**：新文件 `agent-config/WORK.md`，条目 `### W-<n>`，字段与 TECH_DEBT 一致（标题、状态、现在、下一步、验收、关联：LANE 文件 / 计划文件 / TD 编号）。首批登记（只读现有文件整理，不改它们）：
   - ops-arch 各阶段（`agent-config/work/ops-arch/README.md` 的 1–7 阶段，各一条）；
   - 正在进行或未验收的 Cursor 道：`agent-config/work/ops-arch/LANE-*.md` 与 `agent-config/work/cursor-tasks/LANE-*.md` 中报告未写或未验收的（对照 `reports/`）；
   - `agent-config/work/` 下的 PLAN / REVIEW / REQUEST / LEDGER 文件里仍未完成的计划（例如 `PLAN-phase0-foundation-2026-10-05.md` 的各工作线）。
   每条写清来源文件。`render-tech-debt-page.py` 能否顺带渲染 WORK.md：能就加一个分区，不能就写进报告。
2. **`Work:` 尾注（infra，`agent-config/scripts/git-hooks/lineage.sh`）**：在现有三个尾注之外，`commit-msg` 阶段从提交标题与正文里提取工作项编号（`TD-\d+`、`W-\d+`、`LANE-[A-Z0-9]+`，可多个、去重），写成 `Work: TD-253, LANE-C`；提取不到就写 `Work: unassigned`。已有 `Work:` 的不改（amend、rebase、cherry-pick 不动）。这是共用 hook，按根 `CLAUDE.md` §7 同步双轨说明与 parity-id。测试：用现有 hook 测试方式覆盖「多编号」「没有编号」「已有不改」。
3. **只读检查（infra）**：`scripts/check_work_trailers.py --since 7d`：12 个仓库最近 N 天提交里 `Work:` 缺失 / `unassigned` 的比例，按仓库列出；只报告，不做门禁（报告里给出当前基线）。
4. **进度接口（platform）**：`GET /api/v1/progress`（viewer 及以上）：
   - 从 Gitea 镜像读 infra main 的 `TECH_DEBT.md` 与 `WORK.md`（沿用 `internal/lineage` 读 Gitea 的方式）解析工作项；
   - 与提交血缘（`internal/lineage`：`Work:` 尾注、标题里的编号、`Claude-Session` 线程）和发布记录（`/api/v1/releases`）拼接；
   - 每个工作项返回：编号、标题、类别（债 / 计划 / 道）、状态、最近验收结果、线程列表、提交数、到达的环境（STG / PROD）、最近活动时间、是否待签收、是否「卡住」（状态为在做且 N 天没有新提交，N 默认 3）；
   - 顶层汇总四栏：待你签收、在途、本周上线、卡住；另给 `unassigned` 提交的计数。
   - 测试：用编造的 TECH_DEBT / WORK 片段与提交清单做单测；不要抄真实数据（`test_fixtures_copied_from_dev` 教训）。
5. MCP：在全量 server 加只读工具 `get_progress`（同步 `config/actions-catalog.json` 无关——它是读工具；`api/internal/mcp/catalog_test.go` 的镜像清单要同步）。

## 门禁与验收

infra：hook 测试、`check_work_trailers.py`、parity 检查；platform：`go build ./... && go vet ./... && go test ./...`、`mcp/platform` 的 `npx tsc -b && npm test`。报告给出 `curl` 进度接口的示例输出形状（用测试数据，不用真实数据）。

## 不做

不改 Console、不推 main、不发版。与第 3 阶段可能在 `api/internal/server/server.go` 的路由注册处冲突，合并由 Claude Code 处理。
