# LANE-W32 — 第 3 阶段之后的清理道（删留复核落地）

登记：`agent-config/WORK.md` 的 W-32。Owner 2026-10-08 确认：`PHASE3-review-2026-10-08.md` 第四节 A 全部删除，四件待定事按推荐。

仓库与分支（都从最新 origin/main 开独立 worktree）：

- bifrost-platform · `cursor/w32-platform`（第一到第四节的代码）
- bifrost-trade-infra · `cursor/w32-infra`（第三节 B3 的治理文字、RATCHETS 跟改）

先读：同目录 `PHASE3-review-2026-10-08.md`（第三、四节是本道的依据），`README.md` 的「范围」「给 Cursor 派道」「Cursor 共用规则」。

## 事实（2026-10-08，platform main `2052182`，PROD `f9f696f`）

- 删留判据（ADR §1）：Agent 经 API / MCP 用吗？Owner 用来批、签、看吗？有维护循环依赖吗？三个都答「否」就删。下面每一项 Owner 都已过目。
- 两台 mini 的 operator-plane 和 platform-api 同源（`api/cmd/operator-plane`）。删 operator-plane 路由以后，mini 要重部署才生效，这一步由 Claude 做，本道不部署。
- 信任覆盖现在存在 PROD 的 ConfigMap `bifrost-platform-prod/platform-trust-overrides`，只有一条：`research-loop-batch` → `L0`，reason `Owner manual actuation level`，2026-10-07 设置。写接口是 `PUT /api/v1/agent/governance/trust-overrides/{skill_id}`，只要 operator 角色，不经审批。Research 的 `trust_gate.py:28` 每天读 `GET /api/v1/agent/governance/trust-matrix`。
- `join_cluster_node`：30 天转录里真实调用 0 次。所有节点加入（04、05、06，06-19 的 GPU 服务器）都走 infra 的 `scripts/k3s/join-*.sh` 和 Makefile；10-06 起这些脚本按控制面版本钉版本（infra `b417e14`）。

## 要做

### 一、删除（第四节 A，十项全部）

连同端点、MCP 工具、测试、调用方一起删。删完后同步 `mcp/platform` 的 stdio 清单数和对应测试。

1. Hermes readiness、`hermes-tooling` 探针、MCP `get_hermes_readiness`；operator-plane 的 `/agent/skills`、`/agent/schedules`、`/agent/executions`、`PUT …/actuation-level`。**保留** ⑥ 的 Hermes health 那一行（报的是 .52 的 bifrost 网关）。删完后核对 `quiet_success_streak` 不再被 `hermes-tooling` 卡在 0。
2. checklist 的 `POST /checklist/signals`、`POST /checklist/husbandry-sync`、`GET /checklist/kpis`，以及 MCP `get_checklist_kpis`、`report_checklist_signals`。**保留** autopilot 读的 `GET /checklist/signals`。`husbandry-sync` 删掉后：`server/console_auth_test.go` 里它那一项改成在 `TestRetiredRoutesAre404` 里断言 404；`checklist/no_dispatch_test.go` 保留。
3. retrospective 的 report / defects（含 `server.go` 里两条 GET 路由）。
4. agent smoke、agent-tasks、capability-map、flight-director snapshot、performance，以及 MCP `get_agent_performance`、`get_flight_director_snapshot`。**保留** `agent/bridge` 和 `get_agent_bridge`；**保留** trust-matrix 的 HTTP 端点。
5. promote release-cycles（两条 GET）、写它的 hook（`server.go` 里调用处），以及 `/context` 里过时的 `last_gate`。
6. 夜间报告：读、触发、MCP `get_agent_nightly_report`。
7. `POST /agent/deploy`。**保留** GET（⑥ 的 mini 卡片在用）。
8. escape-hatch（② 页的「最近一次演练」），连同它的 emptyDir 数据路径。
9. MCP 工具：`stack_install_addon`、`stack_upgrade_addon`、`get_stack_addons`、`ensure_kubeconfig_secret`、`ensure_metrics_server`、`ensure_kube_prometheus_stack`、`platform_mcp_capabilities`。背后的 HTTP 端点如果只有这些工具在用，一起删。
10. Console 的静态目录与提示词：`businessAgentLoopCatalog`、`consoleNavConfig`、两个 Prompt 文件、`dailyOpsChecklistCatalog`。**注意**：第三节 C2 要把检查清单信号放进 ①，如果展示需要 `dailyOpsChecklistCatalog` 里的标签，只留那一部分，并在报告里写明。

### 二、Console 里直接启动修复 Agent 的入口（B1）

删掉所有不经动作目录、直接调 `POST /api/v1/remediation/start` 的 Console 入口：

- ⑥ 的「AI Auto-Check / Auto-Remediate」按钮（`components/cluster/ClusterOpsIssuesPanel.tsx` 和 `ClusterPage` 的 `handleAutoRemediate`）；
- `ControlRoomPage` 里的 `aiRelease`；
- `satellite-bus/useSatelliteBusQueries.tsx` 里的 `aiIngestTriage`；
- 没有调用方之后的 `hooks/useAmbientAgentTask.ts` 和 `api/remediation.ts` 的 `startRemediation`。

remediation 后端（runner、`/remediation/*` 路由）**不动**，第 5 阶段凭证收口时再定。

### 三、待定事按推荐落地（B2–B4）

- **B2 信任覆盖**：
  - 覆盖值改由 platform 仓库里纳入版本控制的 `config/trust-overrides.yaml` 提供，初始内容是上面「事实」里那一条（skill、level、reason、设置日期，`applied_by: owner`）。platform-api 启动时读这个文件；以后改信任等级就是改这个文件，经 Owner 批准随 platform 发布上线；
  - 删除 `PUT /agent/governance/trust-overrides/{skill_id}` 和 `trustoverrides` 的 ConfigMap 存储；
  - `GET trust-overrides` 和 `GET trust-matrix` 保留，返回的 `store` 写成文件路径；
  - 测试要覆盖：文件里的覆盖会出现在 trust-matrix 里；文件缺失或解析失败时，trust-matrix 照常返回，不带覆盖，并给出 `store_error`（不能 500，Research 每天在读）；
  - 报告的「要 Owner 批」里写上删除 PROD / STG 旧 ConfigMap 的命令，等新版本上线以后再执行。
- **B3 `agentProtocolCatalog.ts`**（infra 分支）：
  - 把 `AGENT_MODES` 和 `FORBIDDEN_ACTIONS` 原样搬进新文件 `agent-config/AGENT_MODES.md`；
  - 把下面几处的权威源改成指向它：`agent-config/CLAUDE.md:52`、`agent-config/AGENT_FACTS.md:186` 与 `:454`、`agent-config/cursor/rules/bifrost-agent-modes.mdc:20`、`agent-config/cursor/rules/trade-execution-freeze.mdc:37`；
  - 两侧的 parity-id 都要升：`agent-modes` v3 → v4，`trade-execution-freeze` v3 → v4，CLAUDE.md 第 2 行与对应 `.mdc` 同步；之后跑 `bash agent-config/scripts/check-agent-config-parity.sh`；
  - 然后在 platform 分支删掉 `console/src/lib/architecture/agentProtocolCatalog.ts`，`tsc` 要过；
  - `preflight.js` 不改。如果发现它的注释也引用了这个文件，在报告「后续」里列出 `文件:行`，由 Claude 处理。
- **B4 `join_cluster_node`**：
  - 删 MCP 工具（`api/internal/mcp/catalog.go` 和 `mcp/platform` 的 stdio 清单）、动作目录条目（`api/internal/actions/catalog.go`）、`actions_wire.go` 里的注册、路由 `POST /cluster/nodes/join` 与 `GET /cluster/join-profiles`、只被它们用到的 handler 和服务代码；
  - 删 Console 的入口：`api/clusterActuation.ts` 的 join、`api/cluster.ts` 的 `fetchJoinProfiles`，以及渲染它们的组件；
  - infra 的 `scripts/k3s/join-*.sh` 和 Makefile 不动，它们是加节点的唯一路径；
  - 动作目录的条目数和相关测试跟着改。

### 四、review 第三节的清理项

- **C1** 就是上面第二节。
- **C2** ① Status 减少轮询：
  - 现在一个页面打 21 个接口；只留 ① 回答「现在健康吗」所需的那些，其余删掉或改成按需加载；
  - 没有令牌时**不要**轮询 `/remediation/`（现在每 3.5 分钟至少 57 次 401）；
  - 去向表要求检查清单信号进 ①：在 7 页的 ① 里渲染 `GET /checklist/signals` 的摘要（不再藏在 `!statusSurface` 分支里）。
- **C3** 零引用代码：
  - 删掉没有任何 import 的文件（review 估计约 45 个文件、5200 行，例如 `AgentExecutionDock.tsx`、`GitOpsProbePanel.tsx`、`TaskModeIconRail.tsx`）；
  - 删掉 `ControlRoomPage` 里关着的分支（LaunchPad、OperateQueueStrip）；
  - 删掉已删接口的调用方（`api/promote.ts` 的 gate / tier-b、operateQueue、hermes insights）；
  - 每删一个文件，都要先用 grep 确认没有 import，删完后 `tsc` 能过。
- **C4** ① 的 Grafana iframe：只调查，不改。现在是 http 嵌在 https 页里，被浏览器当作混合内容拦掉（`lib/observability/grafanaUrlBuilder.ts`）。在报告里给出两三个修法和推荐（例如经 Traefik 用 https 暴露 Grafana，或改成链接），等 Owner 定。

## 防线

- `TestRetiredRoutesAre404` 扩到本道删除的每一条路由，包括 operator-plane 路由表；
- MCP 的 stdio 清单数测试跟着改；
- B2 的文件存储测试，见上；
- `code-health`：超长文件数如果下降，`baselines.env` 只许往下改，不许往上；
- infra：`RATCHETS.md` 里「platform 终端与修复派发鉴权」那一行，把 `husbandry-sync` 从「无令牌必须 401」改成「已删、404」；`TestChecklistNeverImportsRemediation` 保留。

## 门禁

- platform `api/`：`go build ./... && go vet ./... && go test ./...`
- platform `mcp/platform`：`npm test`
- platform `console/`：`npm run lint && npm test && npm run build`（`build` 里含 `tsc -b`）
- infra：`bash agent-config/scripts/check-agent-config-parity.sh`、`make check-maintainers`

## 报告

写 `agent-config/work/ops-arch/reports/LANE-W32.md`，格式按 README：

- 每项写改动（仓库 · 分支 · 完整 SHA）、防线（文件 + 测试名）、门禁（命令 → 结果）、验收（一条命令 + 预期）、要 Owner 批（原样可执行的命令）、后续（`文件:行` + 一句话）；
- 附一张删除清单：路由、MCP 工具、文件，以及 Console 删减前后的文件数和行数。

报告从 origin/main 另开 worktree 提交，推 main 用同一条命令：
`bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`

## 不做

- 多 Agent 运行时：任务与租约、Agent 主机守护进程、交互总线、推理网关、额度账本；
- 发布队列；
- RP 发版策略（`cursor/rp-*` 两条分支不合）；
- 认领与待办箱；
- 工作项编号规则；
- Grok Bot 相关的任何事（它暂停中：不验收 LANE-N / LANE-M2，不收尾它的台账）。
- 不改 `api/internal/approvals/` 的审批语义（删除已退场功能的调用方除外）。
- 不发版、不部署 mini、不 apply、不写数据库、代码不推 main。
- remediation 后端、`/remediation/*` 路由、两台 mini 上的 runner 不动（第 5 阶段再定）。
- `bifrost-kubernetes`、`bifrost-redis`、`bifrost-postgres` 三个 MCP 服务器和 `.mcp.json` 不动。
