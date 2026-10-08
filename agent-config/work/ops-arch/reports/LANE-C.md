# LANE-C 报告 — 第 3 阶段 Console 七页重组

日期：2026-10-08。未推 `main`，未发版，未 apply，未 kubectl，未写数据库，未跑 `release.sh`，未起 pipeline，未改 k8s，未改 `MAINTAINERS.yaml`。

## 分支

集成分支 **`cursor/phase3-platform`**，最终 SHA **`4f52663c7081ba6bea901ea3666083356c245999`**。已推送 `origin/cursor/phase3-platform`。

Worktree：`/Users/vision-mac-trader/Desktop/stocks/bifrost-platform-phase3-int`（本次新建，从 `origin/main` `67b63cf8738988c27102a9b72641f1a01c2a36bb` 开出）。主检出 `bifrost-platform` 未改。

| 分支 | SHA | 怎么进集成 |
|---|---|---|
| `origin/cursor/phase3-s1` | `188f0611a9a455d77e5693863f77a0d025ecd286` | 快进 |
| `origin/cursor/phase3-s2` | `abba2f2461426e2c9e2fb0ce62bccb93e3981857` | s3/s4/s5 的父，合 s3 时带入 |
| `origin/cursor/phase3-s3` | `c5eee58e5e227756b8241413bf27df3310a94f2a` | merge |
| `origin/cursor/phase3-s4` | `2e86b38d54c3e396c0420ac88464983c6118a356` | merge |
| `origin/cursor/phase3-s5` | `4949b92a45ffb460725172f9be3e6408f2ab7493` | merge |
| S6（同一条集成分支） | `e63ec329ea28255b6ee8e678afee7f8b258162c7` | 提交 `Remove the retired Ops Console pages…` |
| 补删未挂载旧页 | `4f52663c7081ba6bea901ea3666083356c245999` | 提交 `Remove the unmounted bus, operator-plane, and patrol-log pages.`，Change-Id `I5675a1d4e0860288ffa515b79e44526d2a6a9830` |

`shellPages.tsx` 三边各自把占位函数换成 re-export，ort 自动合并后七个 re-export 都在：Status、Data、IB、Maintenance、Releases、Infrastructure、Progress。S6 删掉了已经没人用的占位函数 `ShellQuestion`。

## Console 行数与构建产物

`console/src` 下 `.ts` / `.tsx`，按换行计。改前用 `67b63cf` 的 `git archive` 重数，与 S2 笔记的 165556 一致。

| | 文件数 | 行数 |
|---|---|---|
| 改前 `origin/main` `67b63cf` | 883 | 165556 |
| 改后 `4f52663` | 685 | 116426 |

构建产物只测了集成分支这次 `npm run build`（vite 6.4.3）。没有在 `origin/main` 上重编，没有改前体积。

| 产物 | 体积 | gzip |
|---|---|---|
| `dist/assets/index-B6awvTcn.js` | 2166.53 kB | 634.06 kB |
| `dist/assets/index-CJo1qPLd.css` | 378.99 kB | 53.21 kB |

chunk 超过 500 kB 的警告是既有的。S3 / S5 各自 worktree 的体积不能和这次比：那些构建没有把另外几页的面板打进同一个入口。

## 删除的 HTTP 端点

S1 删除，`TestRetiredRoutesAre404`（`api/internal/server/server_test.go`）覆盖代表路径，本集成 `go test` 通过。前缀 `/api/v1`。

Operate Queue：

- GET/POST `/operate/queue`
- POST `/operate/queue/{id}/execution`
- POST `/operate/queue/{id}/close`
- POST `/operate/queue/{id}/dismiss`
- GET `/operate/briefs`
- POST `/operate/briefs/{id}/decide`
- GET `/operate/drain/status`
- POST `/operate/sweep`

Vision：

- GET/POST `/vision/{v1,s3,v2,v3,v4,v5}/gate`
- POST `/vision/{v1,s3,v2,v3,v4,v5}/signoff`

build-phase：

- GET `/build-phase`
- GET/POST `/build-phase/{phase}/gate`
- POST `/build-phase/{phase}/signoff`

migrate-streams：

- GET `/migrate-streams/catalog`
- POST `/migrate-streams/{streamId}/waves/{waveId}/deliver`
- POST `/migrate-streams/{streamId}/waves/{waveId}/signoff`

发布门 / Tier-B：

- GET/POST `/promote/release-gate`
- GET `/promote/release-state`
- GET `/promote/gate-history`
- GET `/promote/tier-b`
- POST `/promote/tier-b/signoff`

Hermes insights / first task：

- GET `/hermes/insights`
- POST `/hermes/run-first-task`
- GET `/agent/hermes/first-task`

漂移提议：

- GET/POST `/agent/drift-proposals`（含 trailing slash）
- GET `/agent/drift-proposals/{id}`
- POST `/agent/drift-proposals/{id}/approve`
- POST `/agent/drift-proposals/{id}/reject`

retrospective 专用：

- GET `/agent/retrospective/patterns`
- GET `/agent/retrospective/insights`

## 删除的 MCP 工具（11）

`get_hermes_first_task`、`get_hermes_insights`、`get_release_state`、`get_release_gate`、`get_gate_history`、`run_release_gate`、`sign_tier_b`、`get_operate_queue`、`record_operate_queue_execution`、`close_operate_queue_item`、`dismiss_operate_queue_item`

stdio 镜像清单 75 → 64（`catalog_test.go` 断言 `len == 64`）。`mcp/platform/src/stdioToolNames.ts` 与 `index.ts` 已同步。本集成 `npx tsc -b && npm test` 通过（18 tests）。

S6 从仍会在运行时打到这些名字的调用方拿掉了：

- `agent/remediation` 的 `get_operate_queue`、`get_hermes_first_task`、`get_release_state`、`run_release_gate`，以及 prompt / scoped prompt 里让 runner 去调它们的步骤
- Console 清单 `dailyOpsChecklistCatalog` 的 `run_release_gate`
- `platformReleaseAgentPrompt` 里的 `get_release_state`
- Status 表面不再请求 Operate Queue 与决策简报（`useOperateQueue` / `usePendingDecisionBriefs` 在 `surface="status"` 时 `enabled: false`）
- 顶栏 User 菜单的 Guides 入口

`agentProtocolCatalog.ts` 保留。里面仍有这些工具的说明文字，页面已删，不发请求。

## 保留的后端及原因

- remediation runner：`GET/POST /api/v1/remediation/*` 与 MCP `get_remediation_health`、`list_remediation_jobs`。表要求保留，第 5 阶段再收权。
- 信任覆盖：`GET /api/v1/agent/governance/trust-overrides`、`PUT .../trust-overrides/{skill_id}`，包 `api/internal/trustoverrides`。patrol 不读它（只用 skill.TrustLevel）。按表「若 patrol 仍读则留后端、只删页面」；patrol 不读也按指令留着。页面 `AgentGovernancePage` 已删。
- Hermes 健康：`GET /api/v1/agent/hermes/readiness`、`GET /api/v1/agent/hermes/health`，MCP `get_hermes_readiness`。checklist 探针 `hermes-tooling` 仍读 readiness。Infrastructure 的 mini 卡片用 health 画一行。
- checklist：`POST /api/v1/checklist/signals`、`POST /api/v1/checklist/husbandry-sync`、KPI，MCP `get_checklist_signals`、`get_checklist_kpis`、`report_checklist_signals`。`husbandry-sync` 只合并信号。`executeDispatch` 与 `checklist/dispatch.go` 已删。`auto_dispatch` 仍接受并忽略。
- retrospective report / defects：`GET /api/v1/agent/retrospective/report`（Cluster 失败面板等仍读）、`GET /api/v1/agent/retrospective/defects`。patterns / insights 已删。Defects 页已删，defects 端点按 S1 保留。
- Agent Capability 没有专用端点。`GET /api/v1/agent/bridge` 仍给 checklist 与 plane。`GET /api/v1/agent-tasks`、`GET /api/v1/agent/governance/capability-map` 未删。治理 MCP `get_agent_performance`、`get_trust_matrix`、`get_flight_director_snapshot` 保留。
- `GET /api/v1/promote/release-cycles` 仍挂载。gate / tier-b 的 HTTP 与 MCP 已摘。`api/internal/promote` 里未挂路由的 service 方法还在。
- 其它未动且仍在用：`get_stg_smoke`、patrol、escape-hatch、delivery pipelines、agent deploy/bridge、Massive、IB Flex、Research、Cluster、Network、Approvals、Audit、Commit Lineage、Code Health、IB Client、Runtime Map。

## 删除的后台循环

供以后改 `MAINTAINERS.yaml`（本步没改那个文件）：

- **Operate Queue drain**：`api/internal/operatequeue/drain.go` 的 `Kick()`（`safego.Go` 跑 `operatequeue.drain.loop`），由 `NewHandler` 创建 DrainWorker。包已整包删除，决策简报与 sweep 一起去掉。patrol autopilot 循环还在。

## 每个新页面的组成

导航顺序：Status、Data、IB、Maintenance、Releases、Infrastructure、Progress。空 hash 与认不出的 hash 落到 `#status`。

### ① Status `#status`

`console/src/pages/shell/status/StatusPage.tsx` 自己取 `fetchContext` 与 `fetchMatrix()`（不带 env）。

| 区块 | 旧页 | 保留 |
|---|---|---|
| Control room | `ControlRoomPage` `surface="status"` | 结论条、红项、mission + health 状态卡 |
| Observability | `ObservabilityPage` `lockToViewer` `hideAgentActions` | 告警、PROD 黄金信号、Grafana、静音 2 小时 |
| Platform | `RocketHealthPage` `lockToViewer` | platform-api / console / Argo |
| Trade | `SatelliteHealthPage` `lockToViewer` | 按 console 环境的 HTTP / 鉴权 / D10 写路径探针与 Runtime 下钻 |

去掉：LaunchPad / Promote / PipelineFlow、Agent 派发、Governance、环境选择器、Agent Fix / Diagnose。mission 正文不渲染（会打 `bus-deep?env=stg`，并带着发布/Agent 操作）。状态卡还在。

### ② Data `#data`

- 插件状态条：`PluginGalleryPage` `variant="strip"`
- Massive：`MarketDataManagePage`（覆盖、就绪、Doctor、入队、source-void）
- IB Flex：`FlexQueryManagePage`（不传 `onOpenAgentDesk`）
- Research Engine：`ResearchEnginePage`（同样不传打开 Agent Desk）
- 备份与演练：`BackupStatusPanel`

### ③ IB `#ib`

- 主体：`IbGatewayManagePage`（连接、重连 B、自愈 B 仍直调；模式切换 / 维护走 `RequestActionButton`）
- Bus：`IbBusStatus`。先 `GET /api/v1/self-health` 取 `viewer_env`，再 `GET /api/v1/satellite/bus-deep?env=<viewer_env>`。没有 viewer 时不发 bus-deep。旧 `SatelliteBusPage.tsx` 已删。IB 仍用的 `TradeDaemonOperatePanel.tsx` 与 `useSatelliteBusQueries.tsx` 留下。

### ④ Maintenance `#maintenance`

| 页签 | 旧页 |
|---|---|
| Approvals（默认） | `ApprovalsPage`；`#maintenance?id=` 打开对应申请 |
| Autopilot | `AutonomousSkillsPage`：技能、运行记录（含 REPORT-ONLY）、手动运行一次 |
| History | `AuditPage` + Download JSON |

`ExecutionLogPage.tsx` 已删，避免两份运行历史。

### ⑤ Releases `#releases`

只读版本、在途与失败的 run、STG 冒烟（`StgSmokePanel`）、最近发布记录（`GET /api/v1/releases`）。唯一动作是 `RequestActionButton` `gitops_rollback_app`，只渲染目录判成 PROD（C）的应用名。没有起流水线、删 run、镜像同步、Dockerfile 刷新、Argo sync、直接 Rollback、发布门、Tier-B、add-on、逃生演练、AI Deploy。

### ⑥ Infrastructure `#infrastructure`

- Cluster：`ClusterPage`。C/D（cordon / drain / 关机 / 加入 / scale / rollout restart / kubeconfig / metrics-server / kube-prometheus / 数据克隆 / 周同步）走 `RequestActionButton`
- Network：`NetworkPage`。防火墙 apply 走申请
- Runtime Map：`RuntimeMapSection`，拓扑在 `viewer_env` 返回后请求
- 两台 mini：`MiniCards`（operator-plane 字符串、互看 `peer_ssh` / `peer_url`、runner 心跳）。Hermes：`GET /api/v1/agent/hermes/health` 一行
- B 级仍直调：`ib_reconnect`、`ib_self_heal`、`wake_compute_node`、`delete_pod`、Massive 补采与 Doctor。daemon Start 仍是禁用按钮（D10）。Ensure namespaces 不在动作目录里，保持直调

### ⑦ Progress `#progress`

- `CommitLineagePage` 原样
- `CodeHealthPage` 整块（指标、历史、Live Re-scan）。没有收成更小的卡片，也没有做第 4 阶段进度视图

## 去向表每一行

| 现在的页面 | 结果 | 说明 |
|---|---|---|
| Approvals | 做到 | ④ 首页，批准 / 驳回还在 |
| Control Room | 做到 | 并入 ①。发布区、Agent 派发、Governance 不在 status 表面渲染。mission 正文不渲染，见上 |
| Task Control Center | 做到 | 退场。页、task-mode 主体、只为它服务的组件已删 |
| Observability | 做到 | 并入 ①。环境选择器与 Agent Fix / Diagnose 在 status 上关掉。静音 2 小时保留 |
| Rocket Health | 做到 | ① 平台卡。独立路由已重定向 |
| Satellite Health | 做到 | ① Trade 卡，可下钻 Runtime。环境选择器去掉 |
| Runtime Map | 做到 | ⑥ 拓扑。没有环境选择器 |
| Code Health | 做到 | ⑦ 一整块，含 Live Re-scan。版式没改成「一张小卡」 |
| Defects | 做到 | 页与 `pages/defects/` 已删。`/agent/retrospective/defects` 端点按 S1 保留 |
| Audit | 做到 | ④ History |
| Rocket（platform-release） | 做到 | ⑤ 只读版本与 run。起流水线、发布门、Tier-B、add-on、逃生演练、Agent 发版不在新页。旧页已删 |
| Satellite › Trade | 做到 | ⑤ 版本、在途、失败、STG 冒烟。「申请回滚」是唯一动作。旧页已删 |
| Satellite › Research | 部分 | ⑤ 有这一行，run 出现在最近发布。STG/PROD 版本列没有数据源，见下节 |
| Plugin | 部分 | ⑤ 有这一行。规则只有 `market-data` / `image` / `deploys: false`，两列是 — |
| Agent（agent-release） | 做到 | ⑥ mini 卡片：runner 版本与心跳。没有 Update primary / standby。旧页已删 |
| Commit Lineage | 做到 | ⑦ 原样 |
| Queue | 做到 | 页、后端、MCP、drain 循环已删。Status 不再打这些端点 |
| Patrol + Patrol Log | 做到 | ④ Autopilot 用技能页（含 REPORT-ONLY 与手动跑一次）。`ExecutionLogPage.tsx` 已删 |
| Operator Plane | 做到 | ⑥ mini 卡片。没有 AI Fix、nightly-run。`OperatorPlanePage.tsx` 已删。`operatorPlaneFixPrompt.ts` 留下：检查清单仍引用 `OPERATOR_PLANE_FIX_SCOPE` |
| Trust & Autonomy | 做到 | 页已删。信任覆盖后端保留，见上 |
| Agent Capability | 做到 | 页与 view model 已删。没有专用端点 |
| Analysis Workspace / Insight Log / Hermes Status | 做到 | 三页已删。Hermes 健康在 ⑥ 一行。insights / first task 端点已删 |
| Bus Status | 做到 | ③ 只看 viewer 环境。旧 `SatelliteBusPage.tsx` 已删。`SatelliteApiHealthPage.tsx` 与 `SatelliteTelemetryPage.tsx` 留下：`SatelliteHealthPage` 仍 import 它们，Status 仍 import `SatelliteHealthPage` |
| IB Client | 做到 | ③ 首页。重连 / 自愈直调。模式 / 维护走申请 |
| Research Engine | 做到 | ②。打开 Agent Desk 的 Diagnose 不传。健康页里标题叫 Diagnose 的发现列表还在 |
| Plugin Gallery | 做到 | ② 顶部状态条 |
| Massive | 做到 | ② 原页嵌入，业务块没重写 |
| IB Flex | 做到 | ② 原页嵌入 |
| Cluster | 部分 | ⑥ 主体在。C/D 改申请。待重启节点没有信号，没做假面板 |
| Network | 做到 | ⑥。防火墙 apply 改申请 |
| Dev Sessions | 做到 | 只在本机：Vite dev，或生产构建且 `viewer_env` 为 `dev` / `dev-local`。PROD/STG 不显示，`#dev-sessions` 改写成 `#status`。不在 7 项导航里 |
| Guides 9 页 | 做到 | 页与只为它们服务的 `lib/architecture/` 目录已删。`agentProtocolCatalog.ts` 保留。顶栏 Guides 入口已删 |
| 三种视角 | 做到 | 外壳不再按视角过滤。`navLens` 已删。`consoleNavConfig.ts` 还在：`systemDomainCatalog` / `consoleSeatCatalog` 仍引用它的类型，删文件会拆掉保留的 `agentProtocolCatalog` 依赖 |

后端清理行：

| 功能 | 结果 |
|---|---|
| 检查清单驱动的派发 | 做到。`executeDispatch` 已删，`husbandry-sync` 只更新信号 |
| Operate Queue、决策简报、漂移提议 | 做到。端点、MCP、页面、runner 工具都去掉 |
| Vision 关卡、build-phase、migrate-streams、发布门、Tier-B | 做到 |
| Hermes insights / first task | 做到。健康探针保留 |
| remediation | 做到（保留） |
| argo-apps 忽略已回收的 `db-init-*` Job | 做到。`onlyReclaimedJobDrift`：仅当 OutOfSync、Health 为 Healthy/Progressing/空、且全部非 Synced 资源都是 Kind=Job 且名前缀 `db-init-` 时忽略 |

Owner 2026-10-08：Code Health 并入 ⑦、Trust 退场、Guides 连关卡删除，其余照表。做到。

## 写不进去的数据源

- **待重启节点**：仓库里没有 reboot-required 信号，`ClusterNode` 无该字段。⑥ 没有这块面板。
- **集群状态备份**：没有单独端点。页面不放。
- **演练最近一次 PASS**：`GET /api/v1/platform/escape-hatch` 只有 `quarterly.last_drill_at`、`last_drill_by`、`overdue`、`days_since_last_drill`。② 标成 “Last recorded escape-hatch drill”，不写成 PASS。
- **告警中转**：只在 mini 上 operator-plane 的 `:8783 /health`，console 没有这条接口。Mini 卡片用平台 `/health` 的 `operator_plane` 字符串。互看用 deploy target 的 `peer_ssh` / `peer_url`。
- **Research / 插件 / Mac mini agent 的 STG/PROD 版本**：发布规则里 Research 与插件 `deploys: false`，没有两列版本。Mac mini agent 不在 `/api/v1/releases` 里；runner 版本在 ⑥ 心跳，⑤ 两列是 —。没有 DEV 列。
- **选择性克隆「补被引用的表」**：旧逻辑靠直调 POST 的 `DataCloneRefusedError` 当场补表。改成申请之后浏览器拿不到那次拒绝，这段修复 UI 去掉了。选表和申请同步还在。

## 旧 hash 里去向表没写死、实现时选定的映射

来自 S2 `LEGACY_HASH_REDIRECTS`。完整表在 `console/src/lib/shell/consoleRoutes.ts`。下面是表没写死、S2 选定的那些：

| 旧 hash | 新 hash | 选定理由 |
|---|---|---|
| `defects` | `#maintenance` | 修复失败的回顾，靠近 Audit |
| `queue`、`agent-desk` | `#maintenance` | 操作收件箱 |
| `agent-capability` | `#infrastructure` | runner 就绪度跟 mini 卡片 |
| `agent-governance` | `#maintenance` | 巡逻的信任策略 |
| `analysis-workspace`、`hermes-status` | `#infrastructure` | 留下的是 Hermes 健康一行 |
| `insight-log` | `#maintenance` | 历史，和 Audit 同层 |
| Guides 9 页 + `agent-system` | `#progress` | 项目方向 |
| `console` | `#infrastructure` | 旧 hash 打开的是 Network |

`#dev-sessions` 不是重定向：本机 Console 打开本机页，PROD/STG 改写成 `#status`。

## 防线

随 `npx vitest run` 一起过了（109 files，723 tests）：

- 导航恰好 7 项，顺序 Status → Data → IB → Maintenance → Releases → Infrastructure → Progress；旧 hash 都有目标（`consoleRoutes` 测试）
- `RequestActionButton`：B 直调、C/D 建申请、有令牌弹 “Approve this request?”、无令牌显示 “Request submitted, waiting for approval”
- ① / ③ 健康请求不带环境选择器。Status 断言 self-health 查询串为空、matrix 无 `env`、`env` 只等于 viewer、`ns` 等于该 viewer 的 trade namespace。IB 断言 gateway 路径不带环境参数，bus-deep 只在有 `viewer_env` 之后且等于它
- 被删端点：`TestRetiredRoutesAre404`
- `TestWriteRoutesAreCataloguedOrExempt` 与 MCP 清单一致性（stdio 64）随 `go test ./...` 与 `mcp/platform` 的 catalog ratchet 通过

## 门禁

在集成 worktree，第一次通过，没有重试。

| 命令 | 结果 |
|---|---|
| `api/`：`go build ./... && go vet ./... && go test ./...` | exit 0。各包 ok，无 FAIL |
| `console/`：`npx tsc -b && npm run lint && npx vitest run && npm run build` | tsc 通过。lint 0 error、3 warning（flex-query 原有）。vitest 109 files / 723 tests 通过。build 通过，体积见上 |
| `mcp/platform`：`npx tsc -b && npm test` | tsc 通过。18 tests，0 fail |

补删三个旧页之后，在同一 worktree 的 `console/` 重跑 `npx tsc -b && npm run lint && npx vitest run && npm run build`，第一次通过：tsc 通过，lint 仍是 0 error / 3 条 flex-query warning，vitest 108 files / 708 tests，build 通过（JS 2166.53 kB / gzip 634.06 kB，CSS 376.66 kB / gzip 52.92 kB）。api 与 mcp 没有再跑。

`node_modules` 用硬链接指到主检出，未入库。

超长文件：本 worktree 17，基线 23。钩子打印 “lower OVERSIZED_PLATFORM_BASELINE”，exit 0（低于基线不失败）。基线在 infra `scripts/code-health/baselines.env`，本阶段不改。合并进 main 之前需要有人把这条基线降到 17，否则下一次在主检出上提交会先看到旧的 24（主检出 `ConsolePage.tsx` 仍是 1190 行）。

## Change-Id

| 提交 | Change-Id |
|---|---|
| s1 `188f061` | 没有 |
| s2 `abba2f2` | `Ie2b976a6c81cfec75d5a9ab6363afa9b64dc7763` |
| s3 `c5eee58` | 没有 |
| s4 `2e86b38` | `I27b2cb8754a43ab8edbb84e8ad31199ca15e47ef` |
| s5 `4949b92` | 没有 |
| S6 `e63ec32` | `I4c200bbbf82a81138c9dca72a090ea00d06ce71c` |
| 补删 `4f52663` | `I5675a1d4e0860288ffa515b79e44526d2a6a9830` |

s1 / s3 / s5 没有 Change-Id 的原因：worktree 第一次提交时没有 gitignore 的 `.husky/_`，`core.hooksPath` 仍是 `.husky/_`，hook 没跑。补上指向主检出的 shim 后再 amend，pre-commit 的 `scan.sh` 向上找到主检出 `bifrost-platform`（`ConsolePage.tsx` 1190 行，超 800 行的文件 24，基线 23），本 worktree 自己是 23。没有 `--no-verify`，没有 force push，已推送的提交不能改。

S6 把 `.husky/pre-commit` 改成：用临时目录把 **当前** `git rev-parse --show-toplevel` 链成 `bifrost-platform`，再 `--root` 交给 `scan.sh`。这次提交因此带上了 Change-Id，并且扫的是集成分支自己的树（17 / 23，警告，exit 0）。

## S6 删了什么

退场页：TCC、Defects、Queue（Agent Desk）、Agent Capability、Trust & Autonomy、Analysis Workspace、Insight Log、Hermes Status、Guides 9 页（Vision / Blueprint / Roadmap / Platform / Agent Protocol / Agent System / MCP Contract / Design System / AI Compute Strategy）、5 个 Launch 旧页（Platform / Trade / Research / Plugin / Agent release）。

以及只被它们引用的组件与 `lib/`（task-mode 主体、发布门 / Tier-B / Vision 面板、Operate Queue 客户端的一部分调用方、对应 architecture 目录）。`agentProtocolCatalog.ts` 与 `businessAgentLoopCatalog.ts` 留下：后者被 Trade gateway 前缀对账测试使用。

新 7 页仍引用的实现留着：Massive、IB Flex、Research Engine、Cluster、Approvals、Patrol（Autonomous Skills）、Audit、Commit Lineage、Code Health、IB Client、Network、Runtime Map、Control Room、Observability、Rocket Health、Satellite Health。

补删（`4f52663`）：零引用的 `SatelliteBusPage.tsx`、`OperatorPlanePage.tsx`、`ExecutionLogPage.tsx` 已删，连带只被它们引用的表体、inspect、`contextSectionSignal`、`BusActuationStrip`、`AgentMcpPanel`。`SatelliteApiHealthPage.tsx` 与 `SatelliteTelemetryPage.tsx` 留下，因为 `SatelliteHealthPage` 仍 import 它们，而 Status 的 `StatusPage.tsx` import 了 `SatelliteHealthPage`。

## 未完成

- 没有开始第 4 阶段。没有推 main。
- 上表「部分」的行：Research / 插件没有 STG/PROD 版本源；待重启节点没有信号；选择性克隆补表在申请之后修不了。
- `MAINTAINERS.yaml` 里的 Operate Queue drain 登记没有改。
- 超长文件基线仍是 23，本树已是 17。
- 五份并入旧页里，三个零引用的已删（`SatelliteBusPage`、`OperatorPlanePage`、`ExecutionLogPage`）。`SatelliteApiHealthPage` 与 `SatelliteTelemetryPage` 因 Status 仍在用而留。
