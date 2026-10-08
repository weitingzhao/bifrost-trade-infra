# LANE-C — 第 3 阶段：Console 按 7 个问题重组 + 退场功能连后端一起清理

仓库：bifrost-platform，集成分支 **`cursor/phase3-platform`**（从最新 origin/main 开）。可以在各自的 worktree 里并行做子步骤，最后都合进这一条分支；**只有一条分支、一次全量门禁、一次发版**。

必读：`agent-config/work/ops-arch/PHASE3-pages.md`（逐页去向表，Owner 2026-10-08 已批准——**表里没有的改动不要做，表里写「退场」的才删**）、`agent-config/ADR-ops-architecture.md` §1、§4、§5、§6。

## 原则

- **业务优先**（根 `CLAUDE.md` §5）：Massive、IB Flex、Research Engine、Cluster 的业务能力一项都不能少，只是换位置。
- 健康类只看 PROD（Console 所在环境，即 `self-health.viewer_env`）；去掉环境选择器。STG / DEV 只在 ⑤ 作为一列出现。
- C / D 级动作的按钮一律变成「申请」（`POST /api/v1/approvals`）；B 级照旧直调。级别以 `GET /api/v1/actions` 与申请返回为准，不要在前端再抄一份。
- 退场功能的后端端点与 MCP 工具一并删除；被别处仍在用的保留并在报告里说明。
- UI 字符串用英文。

## 步骤（S1 与 S2 可并行；S3–S5 在 S2 之上并行；S6、S7 最后）

**S1 后端清理（只动 `api/`、`mcp/`）**
1. TD-208：`checklist` 的 `husbandry-sync` 只更新信号，删除 `executeDispatch` 及检查清单驱动的派发路径（`checklist/dispatch.go` 中启动 remediation 的部分）。
2. 删除端点与 MCP 工具：Operate Queue（含 drain 循环、决策简报、漂移提议）、Vision 关卡、build-phase、migrate-streams、发布门（release gate）与 Tier-B 签字、Hermes insights / first task、Agent Capability 专用端点、Defects / retrospective 专用端点。**保留** remediation（runner）后端；**保留**信任覆盖后端若 patrol 仍读取它（只删页面）。
3. 探测器 argo-apps 信号：忽略已跑完被 TTL 回收的一次性 Job 造成的 OutOfSync（例如 `db-init-*`）；其余 OutOfSync 照报。
4. 同步更新：`api/internal/actions` 目录与豁免清单、`config/actions-catalog.json`、MCP 的工具注册与映射、`api/internal/mcp/catalog_test.go` 的镜像清单；所有相关测试。

**S2 外壳与导航（只动 `console/` 的外壳、导航、共享组件）**
1. 新导航：一层 7 项 `Status`、`Data`、`IB`、`Maintenance`、`Releases`、`Infrastructure`、`Progress`（顺序与名称照去向表）；删除 System / Ops / Analysis 三种视角。
2. 旧 hash 全部重定向到新位置（含 `LEGACY_RUNTIME_HASHES` 已有的），防止书签失效；退场页面的 hash 重定向到最接近的新页面。
3. 外壳不再每页轮询约 60 个接口：顶栏只取 ① 的一句结论；其余数据由各页自己取。
4. 共享组件 `RequestActionButton`：B 级直调；C / D 级建申请，Console 持有审批令牌时紧接着弹出批准确认（`channel: "console"`），没有令牌时显示「已提交申请，等待批准」。
5. Dev Sessions（顶栏指示器、Dock 面板、页面）只在本机 Console 出现（按 `viewer_env` 或构建标记判断），PROD / STG 不显示。

**S3 ①、④、⑦（在 S2 之上）**
- ① Status：Control Room 的结论条、红项与状态卡 + Observability 的告警与 PROD 黄金信号（含静音 2 小时）+ 平台自身卡（Rocket Health）+ Trade 卡（Satellite Health 的探针与运行时，可下钻）+ Grafana 链接。
- ④ Maintenance：Approvals 为首页；「Autopilot」页签（Patrol 技能 + 运行记录，含 REPORT-ONLY 记录，可手动运行一次）；「History」页签（Audit）。
- ⑦ Progress：Commit Lineage 原样迁入 + Code Health 卡片。

**S4 ②、③、⑥（在 S2 之上）**
- ② Data：顶部插件状态条（原 Plugin Gallery）+ Massive + IB Flex + Research Engine + 备份与演练状态（`/cluster/postgres/backup-status`，以及集群状态备份 / 演练最近一次 PASS 的展示，数据源已有的就放，没有的写进报告）。
- ③ IB：IB Client 为主；Bus Status 只看 PROD；模式切换 / 维护走 `RequestActionButton`。
- ⑥ Infrastructure：Cluster（C / D 按钮改「申请」，新增「待重启节点」：读节点是否有 reboot-required 的可得信号，没有就写进报告）、Network（apply 改「申请」）、Runtime Map 拓扑、两台 mini 卡片（operator-plane、告警中转、互看、runner 版本心跳、Hermes 健康一行）。

**S5 ⑤ Releases（在 S2 之上）**
- 只读：每个应用（platform、Trade、Research、插件、Mac mini agent）在 STG / PROD 的版本、在途与失败的 run、STG 冒烟、最近发布记录（`/api/v1/releases`）；「申请回滚」（Argo rollback，PROD 为 C）是唯一动作。
- 删除起流水线、删 run、镜像同步、Dockerfile 刷新、Argo sync、发布门、Tier-B、add-on 安装、逃生演练、AI Deploy 等按钮。

**S6 删除退场页面**：TCC、Defects、Queue、Agent Capability、Trust & Autonomy、Analysis Workspace、Insight Log、Hermes Status、Guides 9 页、5 个 Launch 页的旧实现、只为它们服务的组件与 `lib/`（含 `lib/architecture/` 中只被这些页面使用的静态目录；`agentProtocolCatalog.ts` **保留**，它是 Agent 模式与禁止动作的权威源）。删干净：无死 import、无死路由。

**S7 全量门禁与报告**

## 防线

- 导航测试：导航恰好 7 项、顺序固定；每个旧 hash 都有重定向目标（遍历清单）。
- `RequestActionButton` 测试：B 直调、C / D 建申请、有令牌时弹批准、无令牌时提示。
- 「健康只看 PROD」：① / ③ 的数据请求不带环境参数或只带 `viewer_env`（测试断言）。
- 后端：被删端点 404；`TestWriteRoutesAreCataloguedOrExempt` 仍通过；MCP 清单一致性测试仍通过。

## 门禁与验收

- `api`：`go build ./... && go vet ./... && go test ./...`
- `console`：`npx tsc -b && npm run lint && npx vitest run && npm run build`（worktree 里先把 `console/node_modules` 链到共享检出，`../../bifrost-ui` 同理）
- `mcp/platform`：`npx tsc -b && npm test`
- 报告必须给出：Console 行数与构建产物大小（前 / 后）、删除的端点与 MCP 工具清单、每个新页面的组成（来自哪些旧页面）、去向表每一行的落实情况（做到 / 没做到及原因）、写不进去的数据源清单。

## 不做

不推 main、不发版、不 apply、不改 infra（`MAINTAINERS.yaml` 里 Operate Queue drain 循环的登记由 Claude Code 合并时更新——报告里列出被删除的后台循环）。报告写到 `agent-config/work/ops-arch/reports/LANE-C.md`。

## 发布方式（Claude Code 执行，供参考）

验收后先只发 STG，Owner 在 STG Console（`stg.ops.bifrost.lan`）上过一遍再发 PROD。
