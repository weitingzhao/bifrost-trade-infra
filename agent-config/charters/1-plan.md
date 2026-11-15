# 领域 1「需求与计划」章程（2026-11-14，占位席位）

读的是 `bifrost-platform` 的 `origin/main`。「量」= 读代码得到；「推」= 推断。眼下没有活，只立章程。

## 1. 管哪块代码和表
- **量**：计划那组在 `api/internal/agentrt/store/` 里，`plan*.go` 17 个文件约 3,300 行（planchange.go 549 行最大；另有 planimport、planview*、planpace、plannote、plandecide、planproposal）。进展投影 `progress*.go` 7 个文件约 1,300 行。合计约 4,600 行，和 domains-review 里的「计划（含进度）5,779 行」大体对得上（后者按前缀多算了测试等）。
- **量**：「要做什么」只剩计划树，没有任务表。建表在 `api/internal/agentrt/migrations/0001_core.sql`：`agentrt.plan_node`（:88）、`agentrt.plan_node_binding`（:233）、`agentrt.mission`（:66，旧的，只留着）。计划的状态变化是写进 `agentrt.event` 的事件（`plan_node_created`、`plan_node_state_changed`、`plan_change_proposed`、`legacy_imported`），不是单独表（`store/planimport.go:88,127`）。
- **量**：导入命令 `api/cmd/agentrt-plan-import`；HTTP 层 `agentrtapi/plan.go`、`planview.go`、`planpace.go`。
- **推**：`missiondecide.go`（280 行）算旧流程残留，归「旧流程残留」那一小块，不算本领域。

## 2. 对外露的口子
- **路由（量）**，`agentrtapi/api.go:147-167`：读 `GET /plan`、`/plan/{id}`、`/plan-view`、`/plan-pace`、`/progress`；写 `POST /plan/proposals`、`/plan/{id}/notes`、`/plan/imports`、`/plan/{id}/signoff`（签收走 `gate("signoff")`，只有 Owner）。
- **MCP 工具（量）**，`mcp/platform/src/index.ts:728,758`、`registerPlanImport.ts:13`：`get_plan`、`get_plan_view`、`post_plan_note`、`propose_plan_change`、`propose_plan_import`。
- **别的包在用的函数（量）**：`store.SetStepState`、`store.PlanStream` 等被 `agentrtapi/plan.go`、`planview.go` 用；`controller` 和 `server` 只在测试里碰计划函数，生产代码里没找到调用（只做了 grep，未逐个核）。
- **推**：Console 的计划页和进展页读 `plan-view`、`progress`，具体页面没逐个核。

## 3. 用户与依赖
- **用户（推）**：Agent 席位（读计划、提计划变更、记笔记）、Owner（签收、批计划变更决策卡）、Console。工坊要的「一张单子」就是计划树的一步，领单是 external-work 登记挂在这一步上（domains-review 的推断，尚未有人这么用）。
- **它用了谁（量，来自 domains-review 的统计）**：计划组用别的组 38 个东西——找你类 10、登记 10、规则 7、证据 6；另外依赖底座（事件追加、事务、写入者）。计划变更要发决策卡给 Owner（`plandecide.go`），所以和领域 5 缠得最深。
- 被别的组用 38 个、store 外用 20 个（量，同上）。

## 4. 现状、缺口、没人管的地方
- **量**：`planview.go` 的快照里 ETA 写死「Unknown，没有容量和时长观测」；没有采纳视图的旧计划标「Unclassified」，旧的勾选不算完成（`planviewsnapshot.go:66`）。
- **量**：「覆盖」一栏写明 `reconciled:false`——没登记的工作看不见（同文件 :134）。
- **量/推**：没有领单这个动作的专用路由，现在靠 register_external_work，计划页是否显示「谁领了这一步」未核。
- **推**：mission 表 408 行是旧的，计划节点 PROD 418 个；两者关系要搞清再删，别误删。
- **推**：目前没有人专管。第一刀（技术债搬出 store 并抽底座包）动完以后，本领域才轮到拆；拆之前先别动 `plan*.go`。
- **待核**：业务问题记录（BI）归谁、是否和计划同属本领域，domains-review 说 Owner 定了冻着。

接活时先做的事：确认上面「未核」三条，再决定是否拆出自己的包。
