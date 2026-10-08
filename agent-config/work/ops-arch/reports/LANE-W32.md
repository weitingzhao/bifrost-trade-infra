# LANE-W32 报告

删留复核落地。代码在两条功能分支，未推 main、未合并、未发版、未 apply。

与 `cursor-tasks/README.md` 的两处冲突按 Owner 本次指令处理：`RATCHETS.md` 的 husbandry-sync 一行已改成「已删、404」（台账 `TECH_DEBT.md` 未动）；报告写在本路径，三个 worktree 保留。

## B4 join_cluster_node

### 改动

- bifrost-platform · `cursor/w32-platform` · `b6e9fc629cfed986bb9bc18672b470d6c3d8d0c0`
  - 删除 MCP 工具 `join_cluster_node` 与 `api/internal/cluster/node_join.go`。节点加入仍走 infra 脚本与 Makefile。

### 防线

- `api/internal/server/server_test.go` · `TestRetiredRoutesAre404`（对应 HTTP 路径 404）。
- `mcp/platform` 的 stdio 名单与 `catalog_test.go` 对齐（本提交后 63）。

### 门禁

- `cd api && go build ./... && go vet ./... && go test ./...` → exit 0
- `cd mcp/platform && npm test` → 20 passed

### 验收

```bash
git -C .worktrees/w32-platform grep -n join_cluster_node mcp/platform/src/catalog.go api/internal/cluster/node_join.go
```

预期：无匹配（`catalog.go` 与 `node_join.go` 已不存在该工具 / 文件）。`mcp/platform/src/focusBridges.ts` 的 kubernetes 名单仍留着这个名字，见后续。

### 要 Owner 批

无。

### 后续

- `mcp/platform/src/focusBridges.ts:42`：kubernetes 允许名单仍写 `join_cluster_node`，工具已不注册。三个按领域筛工具的服务器本道不改名单设计，这一条留给合并时清掉。

## A 十项退场

### 改动

- bifrost-platform · `cursor/w32-platform` · `0993c36dfe4f69e6b2e55546cdf55f0672e91a22`
  - 十项退场面从 HTTP、MCP、动作目录、Console 目录里去掉。stdio 工具 64 → 50。
  - 保留：GET trust-matrix、GET trust-overrides、GET checklist/signals、`/remediation/*`、metrics-server / kube-prometheus / kubeconfig-secret 的 HTTP、GET bridge、GET deploy、GET hermes/health。
  - 第 10 项：删了 `consoleNavConfig.ts` 与 `businessAgentLoopCatalog.ts`。`dailyOpsChecklistCatalog.ts` 仍被 Status 使用，保留。带 importer 的 Prompt 模块保留。

### 防线

- `api/internal/server/server_test.go` · `TestRetiredRoutesAre404`。仍有 GET 的路径（POST `/checklist/signals`、POST `/agent/deploy`）期望 405。
- `api/internal/server/auth_routes_test.go` 与 `coverage_test.go`：变更路由巡检下限 50 → 40（删除后实测 49；下限是巡检坏掉的探测器，不是功能计数）。
- `mcp/platform/src/focusBridges.ts`：`ALWAYS` 只剩 `platform_mcp_health`。`platform_mcp_capabilities` 删除后，`mcpFocusBridges.test.ts` 要求非 kubernetes 名单里的名字都在 catalog 里，所以这条是对齐，不是改三个领域桥的设计。
- `config/actions-catalog.json` 去掉 `stack_install_addon` / `stack_upgrade_addon`。`ensure_metrics_server`、`ensure_kube_prometheus_stack`、`ensure_kubeconfig_secret` 仍在动作目录与 HTTP，因为 Console 与 remediation runner 还在调。它们的 MCP 工具与 `WRITE_SPECS` 已去掉。

### 门禁

- `cd api && go build ./... && go vet ./... && go test ./...` → exit 0
- `cd mcp/platform && npm test` → 20 passed
- `cd console && npm run lint && npm test && npm run build` → lint 0 errors（3 条既有 flex-query warning），vitest 108 files / 695 tests，vite build exit 0

### 验收

```bash
git -C .worktrees/w32-platform grep -n platform_mcp_capabilities mcp/platform/src/catalog.go
```

预期：无匹配。stdio 名单与 `stdioToolNames.ts` 都是 50。

### 要 Owner 批

无。

### 后续

- `mcp/platform/src/focusBridges.ts:44-46`：kubernetes 名单仍写 `ensure_kubeconfig_secret`、`ensure_metrics_server`、`ensure_kube_prometheus_stack`，工具已不注册。
- `config/vision_v4_gate.json:14` 与 `config/vision_v5_gate.json:105` 仍把 `businessAgentLoopCatalog.ts` 标成历史闸门标签。签过的历史快照本道不动。
- `console/scripts/verify-escape-hatch-wave4c.mjs:18` 仍断言已删的 escapehatch 包与路由。该脚本不在 `npm test` 与 Makefile 门禁里。
- 未挂路由但仍编译的处理函数：`api/internal/agentgovernance/handler.go:44` `HandlePerformance`，同文件的任务列表 / capability map / snapshot；`api/internal/agentbridge/handler.go:206` `HandleSmoke`；`api/internal/agentdeploy/handler.go:77` `HandleStart`；`api/internal/promote/handler.go:95` `HandleListReleaseCycles`。

## B1 Console 绕过动作目录的修复按钮

### 改动

- bifrost-platform · `cursor/w32-platform` · `413d6e73f720bb0a92f81878cf3744b6bdc22513`
  - 去掉 Cluster Auto-Check / Auto-Remediate、Control Room 的发布修复入口、satellite ingest triage，以及 `useAmbientAgentTask` 与其测试。
  - `startRemediation()` 保留：playbook fix 与 Observability 的 attention 仍在调用。`/remediation/*` 后端未动。

### 防线

- 删除 `console/src/hooks/useAmbientAgentTask.ts` 后，`npm run build`（含 `tsc -b`）通过。没有新增测试名；调用点用类型检查卡住。

### 门禁

- `cd console && npm run lint && npm test && npm run build` → 与 A 相同计数，exit 0

### 验收

```bash
git -C .worktrees/w32-platform grep -n useAmbientAgentTask console/src
```

预期：无匹配。

### 要 Owner 批

无。

### 后续

- `console/src/pages/ControlRoomPage.tsx:197`、`console/src/pages/ObservabilityPage.tsx:139`、`console/src/pages/cluster/useClusterRemediationMutations.ts:34` 仍 POST `/api/v1/remediation/start`。这三处是动作目录之外的入口，本道只删了任务点名的按钮。

## B2 trust overrides 改读版本化文件

### 改动

- bifrost-platform · `cursor/w32-platform` · `64cc47529d95b042a496fc209a850210657d2d25`
  - 新增 `config/trust-overrides.yaml`：`research-loop-batch` → L0，reason `Owner manual actuation level`，`applied_by: owner`，`applied_at: "2026-10-07"`。
  - 删除 PUT trust-overrides 与 ConfigMap store（`api/internal/trustoverrides`）。GET trust-overrides 与 GET trust-matrix 保留。文件缺失或解析失败返回 200 加 `store_error`，不返回 500。

### 防线

- `api/internal/agentgovernance/trust_override_store_test.go` · `TestYAMLTrustOverrideAppliesResearchLoopBatch`、`TestTrustOverrideMissingOrBadFileIs200`
- `api/internal/server/server_test.go` · `TestTrustMatrixMissingFileIs200`、`TestRetiredRoutesAre404`（PUT 路径 404）

### 门禁

- `cd api && go build ./... && go vet ./... && go test ./...` → exit 0（此后的提交不再改 api）

### 验收

```bash
git -C .worktrees/w32-platform show 64cc47529d95b042a496fc209a850210657d2d25:config/trust-overrides.yaml
```

预期：文件里有 `skill_id: research-loop-batch` 与 `level: L0`。

### 要 Owner 批

新版本上线之后再删旧 ConfigMap。本道不执行：

```bash
KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n bifrost-platform-prod delete configmap platform-trust-overrides
KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n bifrost-platform-stg delete configmap platform-trust-overrides
```

### 后续

- 集群里的 ConfigMap `platform-trust-overrides` 在上面两条命令执行前一直在。新版本读的是镜像里的 yaml，不再读 ConfigMap。

## B3 治理文字迁出 Console

### 改动

- bifrost-trade-infra · `cursor/w32-infra` · `07d19dd1eeb0319a8b5b4c5812c489bc98e4960a`
  - 新增 `agent-config/AGENT_MODES.md`（`AGENT_MODES` 四行、`FORBIDDEN_ACTIONS` 十四行，从原 catalog 原文抄出）。
  - `CLAUDE.md`、`AGENT_FACTS.md`、`cursor/rules/bifrost-agent-modes.mdc`、`cursor/rules/trade-execution-freeze.mdc` 改指向该文件。parity-id：`agent-modes-v3` → `agent-modes-v4`，`trade-execution-freeze-v3` → `trade-execution-freeze-v4`，成对修改。
  - `RATCHETS.md`：POST `/checklist/husbandry-sync` 改为已删、404。POST `/console/ws-ticket` 与 GET `/console/ws` 无令牌仍须 401。
- bifrost-platform · `cursor/w32-platform` · `d917f162094e585fce4c9b06f2f8acec2d63eee9`
  - 删除 `console/src/lib/architecture/agentProtocolCatalog.ts`。Console 运行时没有 import 它。

### 防线

- `agent-config/scripts/check-agent-config-parity.sh`：工作区符号链接树上 Cursor 20 / Claude 20，spine D10 = BLOCKED，exit 0。该脚本从自身目录向上找到工作区根，读的是主 checkout 的符号链接，不是本 worktree。worktree 里的 v4 与 `AGENT_MODES.md` 要等 `cursor/w32-infra` 合并后才会出现在符号链接上。worktree 内两对 parity-id 已一起抬高。
- `make check-maintainers` → ok 45 maintainers；static；no-alert 15。

### 门禁

- `bash agent-config/scripts/check-agent-config-parity.sh` → exit 0（范围见上）
- `make check-maintainers` → exit 0
- 删除 catalog 之后：`cd console && npm run lint && npm test && npm run build` → lint exit 0，vitest 108 files / 695 tests，vite build exit 0

### 验收

```bash
git -C .worktrees/w32-infra grep -n 'agent-config/AGENT_MODES.md' agent-config/CLAUDE.md agent-config/AGENT_FACTS.md
```

预期：`CLAUDE.md` 权威源与 `AGENT_FACTS.md` 两处都指向 `agent-config/AGENT_MODES.md`。

### 要 Owner 批

无。合并 `cursor/w32-infra` 之后，符号链接上的权威源才会换成新文件。

### 后续

- `scripts/agent-guard/preflight.js:12` 与 `:81` 仍引用 `agentProtocolCatalog.ts`。本道不改 `preflight.js`。合并治理文字后应改指向 `agent-config/AGENT_MODES.md`。
- `console/scripts/verify-three-desks.mjs` 与 `console/scripts/governance-active-pack-test.ts` 仍读已删的 catalog。两者都不在 `npm test` 里。

## C2 Status 页减轮询

### 改动

- bifrost-platform · `cursor/w32-platform` · `d13675215cfdd520074a1bed48095ef101fdafe9`
  - Status 上不再请求 `/api/v1/remediation/?`、`/api/v1/context`、cluster metrics、code-health。
  - 页面 ① 渲染 GET `/checklist/signals` 摘要（`ChecklistSignalsSummary`）。Control Room 的 jobs 查询只在 `canOperate && !statusSurface` 时开启。
  - Observability 在 viewer 锁定下默认不拉 evidence，按钮为 `Load evidence`。

### 防线

- `console/src/pages/shell/status/__tests__/StatusPage.test.tsx`：断言请求了 checklist/signals，且没有 remediation/?、context、cluster/metrics、code-health。

### 门禁

- `cd console && npm run lint && npm test && npm run build` → 108 files / 695 tests，exit 0

### 验收

```bash
git -C .worktrees/w32-platform grep -n checklist/signals console/src/pages/shell/status/__tests__/StatusPage.test.tsx
```

预期：测试文件断言该路径被请求。

### 要 Owner 批

无。

### 后续

- Cluster、Spoke、Mission timeline、`RemediationHistoryBar` 挂载时仍会 GET `/remediation/?`。它们不在 Status 上，本道没有全局关掉。

## C3 零引用与已退场客户端

### 改动

- bifrost-platform · `cursor/w32-platform` · `fbd3826943314908233076c99207abc8ba87522c`
  - 删零引用模块（含 LaunchPad、OperateQueueStrip）以及已退场 HTTP 的客户端函数。`vite-env.d.ts` 与 `fleetSnapshot.type-test.ts` 是编译期契约，保留。
  - GET `/api/v1/mcp/tools` 仍在。`console/src/api/mcp.ts` 零引用，已删。
  - `useOperateQueue.ts` 与 `api/operateQueue.ts` 仍在，生产 Control Room 不再调用；钩子自己的测试还在用。

### 防线

- `cd console && npx tsc -b` 与 `npm test`。删文件后的类型错误（Spoke 分数、未使用的打开回调）已在同一提交里修掉。

### 门禁

- `cd console && npm run lint && npm test && npm run build` → 108 files / 695 tests，build exit 0

### 验收

```bash
git -C .worktrees/w32-platform ls-tree -r --name-only fbd3826943314908233076c99207abc8ba87522c -- console/src/api/mcp.ts console/src/pages/shell/LaunchPad.tsx
```

预期：无输出。

### 要 Owner 批

无。

### 后续

- `console/src/hooks/useOperateQueue.ts` 仍请求已退场的 operate queue。生产路径不再挂它，测试还在。
- `agent/remediation` 仍点已删的 MCP 工具名。本道不改 remediation 后端。

## C4 Grafana iframe（只调查，未改代码）

### 改动

无提交。

iframe 的 base 来自 `resolveOpsToolUrl('grafana', observability.grafana_url)`（`console/src/lib/architecture/opsToolRackCatalog.ts:61`）。live 值为空时落到目录里的 `http://192.168.10.73:30883`（同文件第 42 行）。API 侧 `GrafanaURL()`（`api/internal/config/clusters.go:173`）读 `PLATFORM_GRAFANA_URL`，否则读 clusters 配置。`grafanaUrlBuilder.ts` 接受 http 与 https，不改 scheme。Console 页是 https 时，http iframe 被浏览器按 mixed content 拦住。

三个修法：

1. 用现有入口把 Grafana 暴露成 https，把 `PLATFORM_GRAFANA_URL`（或 clusters 里的 grafana URL）指到那个 https origin。builder 原样拼接。同时打开 Grafana 的 embed 允许，cookie 用 Secure。推荐这一条：iframe 保留，不改 builder。
2. 不再嵌 iframe，同一 URL 用新标签打开。顶层导航不受 mixed content 限制，页内面板没了。
3. 由 platform-api 在 Console 的 https origin 上反代 solo panel。iframe 同源，但要另做认证、子路径和 Grafana 的 websocket。

### 防线

无新测试。现有 builder 测试使用 `http://grafana.example:30883`，测的是路径拼接，不是 scheme。

### 门禁

无代码变更，未单跑。

### 验收

```bash
git -C .worktrees/w32-platform grep -n "lanUrl: 'http://192.168.10.73:30883'" console/src/lib/architecture/opsToolRackCatalog.ts
```

预期：第 42 行仍是该 http URL。本道没有改它。

### 要 Owner 批

选定上面第 1 条之后再改配置。本道不改。

### 后续

- `console/src/lib/architecture/opsToolRackCatalog.ts:42`：Grafana 目录 URL 是 http。在它换成 https 之前，https 页面里的 iframe 继续被浏览器拦住。

## 删除清单

路由（完全删除的为 404；GET 仍在的 POST 为 405）：

- `join_cluster_node` 对应的加入节点 HTTP
- performance、capability-map、snapshot、retrospective、escape-hatch 与 drill、checklist/kpis、agent-tasks、POST husbandry-sync、release-cycles、stack install/upgrade、stack/addons、nightly-report、smoke、hermes readiness/skills/schedules/executions、POST nightly-run、PUT actuation-level、PUT trust-overrides
- POST `/api/v1/checklist/signals`、POST `/api/v1/agent/deploy`（GET 仍在，405）

MCP 工具（stdio 64 → 50）：

`join_cluster_node`、`platform_mcp_capabilities`、`get_stack_addons`、`stack_install_addon`、`stack_upgrade_addon`、`ensure_kubeconfig_secret`、`ensure_metrics_server`、`ensure_kube_prometheus_stack`、`get_hermes_readiness`、`get_agent_performance`、`get_flight_director_snapshot`、`get_agent_nightly_report`、`report_checklist_signals`、`get_checklist_kpis`

文件（按提交）：

- `b6e9fc62`：`api/internal/cluster/node_join.go`
- `0993c36d`：hermesreadiness、agentreport、escapehatch、retrospective、stack 等包，以及 `consoleNavConfig.ts`、`businessAgentLoopCatalog.ts`
- `413d6e73`：`useAmbientAgentTask.ts` 与其测试
- `64cc4752`：`api/internal/trustoverrides`；新增 `config/trust-overrides.yaml`
- `fbd38269`：零引用 Console 模块与已退场客户端（含 LaunchPad、OperateQueueStrip、`console/src/api/mcp.ts`）
- `d917f162`：`agentProtocolCatalog.ts`

Console 树（`console/` 全部文件，`console/src` 行数）：

| | 文件 | src 行 |
|---|---|---|
| origin/main | 729 | 125748 |
| `cursor/w32-platform` HEAD | 681 | 117752 |

其中 ts/tsx：690 文件 / 116643 行 → 642 文件 / 108647 行。

## 门禁汇总

| 命令 | 结果 |
|---|---|
| platform `cd api && go build ./... && go vet ./... && go test ./...` | exit 0（B2 之后 api 未再改） |
| platform `cd mcp/platform && npm test` | 20 passed（A 之后 mcp 未再改） |
| platform `cd console && npm run lint && npm test && npm run build` | exit 0；vitest 108 files / 695 tests；最后一次在删除 catalog 之后 |
| infra `bash agent-config/scripts/check-agent-config-parity.sh` | exit 0；读的是工作区符号链接，不是 worktree |
| infra `make check-maintainers` | exit 0；ok 45 maintainers |

## Claude 验收与收尾（2026-10-08）

验收（独立复跑，不引用 Cursor 的结果）：

- **diff 范围**：platform 分支 7 个提交、161 个文件，都在本道范围内；infra 分支 1 个提交、6 个文件，都没有带进别人的在制品。三处敏感文件逐行看过：`config/ops-context.yaml` 只改了权威源路径，D10 仍是 BLOCKED；`actuation/auth.go` 只改注释；`config/clusters.yaml` 只删 join profiles。
- **删除清单与代码一致**：stdio 工具 50 个；`TestRetiredRoutesAre404` 覆盖 53 条 404 和 2 条 405；`AGENT_MODES.md` 有 4 个模式和 14 条禁止动作，与原 TS 一致。
- **infra rebase**：分支当时落后 main 12 个提交，两边都改过的只有 `RATCHETS.md`，rebase 无冲突。
- **门禁**：
  - Go build、vet、test 都是 0；
  - MCP 20/20；
  - Console lint 0 个错误（3 个原有警告），vitest 108 个文件 / 695 个测试，build 通过；
  - parity **测的是分支内容**：搭了一个临时工作区根，infra 和 platform 指向本道分支，结果两侧一致；`check-maintainers` 45 项通过。

收尾（platform `3d3ea8a`，已与本道 7 个提交一起快进进 main）：

- **B1 补漏**：Console 还有三处直接 POST `/api/v1/remediation/start`：Cluster 每行的 Fix、Control Room、Observability 的 attention Fix 和批量 Fix。都删了。查看和停止运行中 job 的抽屉留着，W-33 撤 runner 时一起删。
- `focusBridges.ts` 去掉四个已退役的工具名。
- 删掉路由已去掉的 handler：agentgovernance 的 performance / tasks / capability-map / snapshot、agentbridge 的 smoke、agentdeploy 的 start、promote 的 release-cycles 读取链路。
- 删掉 12 个没人读的 `config/vision_*_gate*.json`，3 个引用已删目录的 console 脚本，以及 `test:governance-pack`。
- 收尾后门禁同上，全部通过。code-health：platform 超过 800 行的文件 16 → 13，基线跟着降到 13（infra，本提交）。
- `preflight.js` 第 12、81 行的文字引用由 Owner 手改（Agent 不得改闸门文件），infra `2db250b`；闸门测试 85/0。

留到 W-33 或以后（不在本道）：

- promote 其余没有路由的 handler（release-gate、gate-history、release-state、tier-b）；cycle store 现在只写不读。
- `remediation.RunnerClient.ActiveURL` 包外没有调用方。W-33 撤 runner 时一起处理。
- Console 里只有测试在用的导出、过时的注释、`.cluster-remediation-session-chip*` 样式，以及改动前就没人引用的 `useAgentJobLiveSession.ts`、`DockRecentAgentTasks.tsx`。
- Grafana（C4）：Owner 选 A，走 ops 网关子路径，并入 W-33 第 ⑤ 项。

