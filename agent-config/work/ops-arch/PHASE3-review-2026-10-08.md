# 第 3 阶段：STG 验收与删留复核（2026-10-08）

本文件只记事实和待 Owner 定的事。进度见 `STATUS-2026-10-08.md` 顶部「交接」一节。

## 一、上了什么

- platform main `f9f696f`：
  - Cursor 的阶段 3 集成分支 `4f52663`，合进当时的 main `634e305`；
  - E1 的 platform 部分 `b291a09`；
  - 删掉 E1 里给 RP 发版策略预留的空常量 `LoopReleasePolicy`（「不预留挂载点」）。
- 冲突 3 处：
  - `console/src/api/approvals.ts` 的 import，两边都留；
  - operator-plane 路由表及其测试：用阶段 3 的列表，补上 E1 的 viewer 字段和 `/agent/launchd`。
- 门禁（干净 worktree）：
  - Go：build、vet、test 都是 0；
  - MCP：20 个测试通过；
  - Console：tsc 0，lint 0 error（3 个 flex-query 旧 warning），vitest 110 files / 714 tests，build 通过；
  - 超 800 行文件 16 个，infra 基线已从 23 降到 16（`7152f18`）。
- 随发布推的 infra 改动（`7152f18`）：
  - 两侧的 Agent 模式表、promote agent、research-release 技能不再指向已删的 Promote / Launch Desk / release gate / Tier-B；
  - parity 版本号：agent-modes 升到 v3，research-release 升到 v3。
  - LANE-C 报告已拿进 main（`dbbbd33`、`2885d4d`）。

## 二、STG 验收（Owner 10-08 回「STG 通过」）

- STG run `bifrost-deliver-platform-1791489152` Succeeded，clone 的是 platform `f9f696f`、ui `9b635b2`。
- 已删接口，11 条抽查都返回 404：
  - `operate/queue`、`operate/briefs`
  - `promote/release-gate`、`promote/tier-b`
  - `vision/v1/gate`、`build-phase`、`migrate-streams/catalog`
  - `hermes/insights`、`agent/hermes/first-task`
  - `agent/drift-proposals`、`agent/retrospective/patterns`
- 保留接口 9 条照常：`self-health`、`releases`、`agent/hermes/readiness`、`checklist/signals`、`promote/release-cycles`、`patrol/skills`、`audit`、`context` 返回 200，`approvals` 在没有令牌时返回 401。
- workers `/metrics` 有 `bifrost_maintainer_*` 的 HELP / TYPE 声明。STG 的维护循环本来就关着（B4），所以没有数据点；PROD 上线后要看到数据点。
- 7 页导航顺序：Status / Data / IB / Maintenance / Releases / Infrastructure / Progress。每页都能渲染，没有 JS 异常。
- STG bundle `index-D8fXPjaC.js` 与本地构建是同一个。

## 三、验收时发现的问题

这几项在现在的 PROD（`634e305`）上也有，不是阶段 3 引入的，所以不挡 PROD。打算并入下一条清理道。

1. **⑥ Infrastructure 的「AI Auto-Check / Auto-Remediate」按钮**
   - 位置：`console/src/components/cluster/ClusterOpsIssuesPanel.tsx:337-374`。
   - 它直接调 `POST /api/v1/remediation/start`，经 runner 在 mini 上启动 Agent。
   - 这个动作不在动作目录里，不走审批。
   - 按钮说明写「进度在 Operator Dock」，但 Dock 已经删了。
2. **① Status 仍然大量轮询**
   - 一个页面就打 21 个接口。
   - `/remediation/?limit=80` 没有令牌时一直 401，约 3.5 分钟至少 57 次（resource timing 缓冲有上限，这个数只是下界）。
   - 请求来自 `ControlRoomPage` 等。
3. **检查清单信号没有进 ①**
   - 去向表要求进 ①，实际只在 `!statusSurface` 分支里（`ControlRoomPage.tsx:451`），7 页都不渲染。
4. **零引用代码**
   - 约 45 个文件、约 5200 行没有任何 import，例如 `AgentExecutionDock.tsx`（1247 行）、`GitOpsProbePanel.tsx`、`TaskModeIconRail.tsx`。
   - `ControlRoomPage` 里关着的分支（LaunchPad、OperateQueueStrip）仍被打进包里。
   - 代码里还有已删接口的调用方（`api/promote.ts` 的 gate / tier-b、operateQueue、hermes insights）。渲染它们的分支已关，不会真的发出请求。

## 四、删留复核（ADR §1 三问；删除要 Owner 过目）

实测口径：
- **MCP30**：本机 Claude 转录 30 天里的调用次数。Cursor 转录同期对这些工具都是 0。
- **PROD7**：Loki 里 7 天的请求数。日志里没有 user-agent 和令牌名，只能按 Host 分调用方。
- **审计**：只有 10-07 19:33 以后的 53 条。

| 删除候选（三问都答「否」） | 依据 |
|---|---|
| Hermes readiness、`hermes-tooling` 探针、MCP `get_hermes_readiness`；operator-plane 的 `/agent/skills`、`/agent/schedules`、`/agent/executions`、`PUT …/actuation-level` | .50 的 Nous Hermes 没有 LLM key，可用的 MCP 工具是 0 个。`hermes-tooling` 是现在唯一不正常的信号，所以「连续平稳」天数（quiet_success_streak）一直是 0。⑥ 里 Hermes health 那一行**保留**，但它报的是 .52 的 bifrost 网关 |
| checklist 的 `POST signals`、`husbandry-sync`、`kpis`，以及 MCP `get_checklist_kpis`、`report_checklist_signals` | MCP30 都是 0；PROD7 只有 0 到 1 次。autopilot 读的 `GET signals` **保留** |
| retrospective report / defects | PROD7 都是 0。数据来自 runner 作业，30 天只有 1 个 |
| agent smoke、agent-tasks、capability-map、flight-director snapshot、performance，以及 MCP `get_agent_performance`、`get_flight_director_snapshot` | 都是 0。`agent/bridge` 和 `get_agent_bridge` **保留**；trust-matrix 的 HTTP 端点 Research 在用，**保留** |
| promote release-cycles、写它的 hook（`server.go:696`），以及 `/context` 里过时的 `last_gate` | 没有读者 |
| 夜间报告：读、触发、MCP `get_agent_nightly_report` | .50 的夜间任务 10-07 已停 |
| `POST /agent/deploy`（GET **保留**，⑥ mini 卡片在用） | 功能关着，从来没有作业 |
| escape-hatch（② 页的「最近一次演练」） | 从来没记录过演练，只有 `overdue: true`。数据放在 emptyDir（`TECH_DEBT.md` 已记）。A6 时间点恢复演练有自己的记录 |
| MCP：`stack_install_addon`、`stack_upgrade_addon`、`get_stack_addons`、`ensure_kubeconfig_secret`、`ensure_metrics_server`、`ensure_kube_prometheus_stack`、`platform_mcp_capabilities` | MCP30 和 PROD7 都是 0，审计里也没有。metrics-server 是 k3s 自带，kube-prometheus 已经用 Helm 装好 |
| Console 静态目录与提示词：`businessAgentLoopCatalog`、`consoleNavConfig`、两个 Prompt 文件、`dailyOpsChecklistCatalog` | 运行时没有任何引用 |

### 待 Owner 定的四件事

1. **⑥ Auto-Remediate 按钮与 remediation 后端**
   - 建议：先删按钮。
   - 后端等第 5 阶段凭证收口时一起定。runner 30 天只有 1 个作业；.50 主 runner 的作业目录指向一个没挂载的卷。
2. **信任覆盖要保留**
   - Cursor 报告只核了 patrol，漏了 Research：`bifrost-research` 的 `trust_gate.py:28` 读 trust-matrix，research-harness 每天都在读。
   - 页面删掉后，Owner 没有入口改信任等级。建议改成 git 配置加 Owner 审批。
3. **`agentProtocolCatalog.ts`**
   - 规则文件都把它写成权威源：CLAUDE.md §2、AGENT_FACTS、Cursor 规则、`preflight.js` 的注释。
   - 但运行时没有读者；preflight 运行时读的是 spine。
   - 建议：把 `AGENT_MODES` 和 `FORBIDDEN_ACTIONS` 迁进 agent-config（要同步两侧版本号）之后再删。
4. **`join_cluster_node`**
   - 拿不准，缺「最近一次加节点是怎么做的」这条证据。

另外（只记录，不在本线程处理）：bifrost-kubernetes、bifrost-redis、bifrost-postgres 三个按领域筛工具的 MCP 服务器，30 天都是 0 次调用。实际在用的主要是 `start_pipeline_run`（293 次）、`gitops_sync_app`（88 次）和 Prometheus 查询（47 次）。

## 五、下一条清理道（Owner 定完上面四件事后写）

- 编号按 README「给 Cursor 派道」：先在 `WORK.md` 登记 W-32（以当时的最大号为准）。
- 内容：
  - 第三节的 1–4；
  - 第四节里 Owner 点头的删除项，连同端点、MCP 工具、测试、调用方一起删；
  - 删除后同步 `mcp/platform` 的 stdio 清单数和对应测试。
- 道文件的「不做」：原样抄 README「明确不做」的清单，再加一句：不改 `api/internal/approvals/` 的审批语义（删除已退场功能的调用方除外）。
