# LANE-W33 — 第 5 阶段收口，第一批（mini 清场 · patrol 回 PROD · 待重启信号 · ⑤ 版本 · Grafana）

登记：`agent-config/WORK.md` 的 W-33。依据：同目录 `W33-credentials-2026-10-08.md`。Owner 2026-10-08 定了「〇」节的七件，全部按推荐。

本道只做方案 A 的**第 1 步**，外加 ③④⑤。第 2 步（通用动作）和第 3 步（Agent 换只读）依赖本道，之后另派，见文末「不在本道」。

仓库与分支（都从最新 origin/main 开独立 worktree）：

- bifrost-platform · `cursor/w33-platform`
- bifrost-trade-infra · `cursor/w33-infra`

先读：`W33-credentials-2026-10-08.md`（现状、发现、Owner 决定），`README.md` 的「范围」「给 Cursor 派道」「Cursor 共用规则」，`reports/LANE-W32.md`「Claude 验收与收尾」。

## 事实（2026-10-08 晚实测，platform main `3d3ea8a`，PROD 同版本）

- 两台 mini 的 `~/bifrost-agent/config/env.sh` 全局导出 `KUBECONFIG=$HOME/.kube/bifrost-k3s.yaml`（集群管理员），runner、operator-plane、.52 hermes-gateway 都继承它。这份 kubeconfig 由 `scripts/agent/deploy_mac_mini.sh` 每次部署时 scp 过去。
- `config/.env` 由部署脚本整份重写，来源是本机 `bifrost-platform/.env` 按键名过滤：`CURSOR_API_KEY`、本机 api 的 operator 和 admin 令牌、`GIT_BRIDGE_URL`、`NTFY_URL`、`NTFY_TOPIC`、`ALERT_RELAY_TOKEN`、`REMEDIATION_RUNNER_TOKEN`，再加 infra `.env` 的 PROD viewer（写成 `PLATFORM_VIEWER_TOKEN`，platform `2052182`）。
- **runner**（两台，:8781）30 天只有 1 个作业。**.52 hermes-gateway** 定时跑 `stale-pipeline-triage`，会 POST runner `/run` 起修复 Agent。**.50 Nous Hermes**（`ai.hermes.gateway`、`ai.hermes.dashboard`）30 天 0 次会话。
- **peer-watchdog**（`scripts/agent/peer_watchdog.sh`）探的是对端 runner `:8781`，不通就经 SSH `launchctl kickstart` runner；另外 .52 还盯着 .50 的告警中转。撤 runner 时必须改成探对端 operator-plane `:8783/health`、重启 `com.bifrost.operator-plane`，中转监视保持不变。
- **patrol 不依赖 runner**：PROD workers 用 `PATROL_DISPATCH=local`、`PATROL_MODE=report`，直接调 platform-api 路由。patrol 的运行记录经 `statefile` 存进平台共享状态。PROD api 设了 `OPERATOR_PLANE_URL=http://192.168.10.50:8783`（infra `k8s/overlays/platform-prod/platform-api-operator-plane.patch.yaml`），于是 `/patrol/*` 被转发到 .50，而 .50 的 autopilot 是关的，Console 看到的是空状态。
- platform 里 runner 的读者：`api/internal/agentbridge`（⑥ mini 卡片上的 runner 心跳）、`/remediation/*` 路由、MCP 的 remediation 工具、`probe/verify_mission_snapshot.go`、`agentgovernance/skillrun.go`；Console 里 `api/remediation.ts`、`api/remediationTypes.ts`、`components/cluster/Remediation*.tsx`、control-room 的几个面板、`hooks/useAgentJobLiveSession.ts` 等。PROD workers 的环境变量里有 `REMEDIATION_RUNNER_URL`、`REMEDIATION_RUNNER_STANDBY_URL`、`REMEDIATION_RUNNER_TOKEN`（infra overlay `platform-runner-token.patch.yaml`）。
- **⑤ Releases**：Research、Plugins、Mac mini agent 三行 STG / PROD 两列都是「—」。Research（`research` 命名空间）和插件（`data` 命名空间的 market-data、flex-query、ib-gateway）只有一套部署，集群里能读到它们正在跑的镜像。
- **Grafana**：kube-prometheus-stack 的 Grafana 只有 NodePort `30883`（http），已开 `allow_embedding` 和匿名 Viewer（`scripts/k3s/values-kube-prometheus.yaml`）。Console 的 iframe 地址来自 `PLATFORM_GRAFANA_URL` / clusters 配置，没配时落到 `console/src/lib/architecture/opsToolRackCatalog.ts:42` 的 `http://192.168.10.73:30883`，在 https 页面里被浏览器当作混合内容拦掉。Traefik 已开 `allowCrossNamespace: true`（`k8s/system/traefik-helmchartconfig.yaml:70`）。ops 网关是 `k8s/overlays/platform-{prod,stg}/ops-ingressroute.yaml`，只有一条 Host 规则。
- **待重启**：5 台节点 `/var/run/reboot-required` 从 09-11 起一直存在，集群里没有任何信号。滚动重启脚本是 infra `scripts/k3s/rolling-reboot.sh`（工作日拒绝 `--execute`，周日 10-11 Owner 会跑一次）。

## 要做

### 一、mini 清场（第 1 步）

1. **部署脚本**（`scripts/agent/deploy_mac_mini.sh`）：
   - 不再 scp kubeconfig；每次部署时在远端**删除** `~/.kube/bifrost-k3s.yaml`，并从 `env.sh` 删掉 `export KUBECONFIG=` 那一行（幂等，已删就跳过）。`env.sh` 模板也不再写这一行；
   - `config/.env` 的同步清单只保留 `NTFY_URL`、`NTFY_TOPIC`、`ALERT_RELAY_TOKEN`，以及 PROD viewer（现有的 `prod_viewer_export`）。**不再同步** `CURSOR_API_KEY`、本机 operator 和 admin 令牌、`REMEDIATION_RUNNER_TOKEN`、`GIT_BRIDGE_URL`；
   - **不再安装 runner**：两台都 `launchctl bootout` 并删掉 `com.bifrost.remediation-runner` 的 plist，不再 rsync `agent/remediation`，不再 `npm install` runner；
   - **.52 hermes-gateway**：bootout 并删掉 `com.bifrost.hermes-gateway` 的 plist（`scripts/agent/deploy_hermes_gateway.sh` 不再被任何流程调用；如果只剩这个用途，删掉它）；
   - **.50 Nous Hermes**：bootout `ai.hermes.gateway` 和 `ai.hermes.dashboard`，不再装 dashboard plist，不再 rsync `mcp/platform` 到 mini，不再改 Hermes 配置。`~/.hermes` 里的文件不删（里面的 key 由 Owner 决定怎么处理），在报告里写一句；
   - 部署后的冒烟改成只查 operator-plane `/health` 和 .50 的告警中转。删掉 runner 冒烟和 `tool_smoke`（如果 `tool_smoke.sh` / `tool_smoke_test.sh` 只服务 runner，一起删）；
   - 脚本头注释改成现在的职责：operator-plane、peer-watchdog、通知用的令牌。
2. **peer-watchdog**（`scripts/agent/peer_watchdog.sh`）：探对端 operator-plane `:8783/health`，不通就经 SSH `launchctl kickstart -k gui/<uid>/com.bifrost.operator-plane`；中转监视逻辑原样保留。部署脚本里传给它的 `PEER_URL` 改成 plane 地址（参数名可以保留，注释写清楚）。
3. **platform 侧撤 runner**：
   - 删 `api/internal/remediation` 包、`/remediation/*` 路由、MCP 的 remediation 工具和 stdio 清单项；
   - `agentbridge` 的 runner 探测改成探两台 mini 的 operator-plane `/health`（⑥ mini 卡片显示 plane 状态）；
   - `probe/verify_mission_snapshot.go`、`agentgovernance/skillrun.go` 里对 runner 的依赖删掉或改成 plane；
   - Console 删掉 remediation 的全部界面和 API 客户端（W-32 留下的查看 / 停止抽屉、`Remediation*.tsx`、相关 control-room 面板、`useAgentJobLiveSession.ts`、`DockRecentAgentTasks.tsx` 等），以及 W-32 报告「留到以后」里随之变成零引用的导出、样式和注释；
   - `hermesgateway` 包、`/agent/hermes/health` 路由和 ⑥ 的 Hermes health 行：.52 网关撤了，一起删；
   - `TestRetiredRoutesAre404` 加上本道删掉的每条路由。
4. **infra 跟改**：
   - 两个 overlay 删掉 `platform-runner-token.patch.yaml` 和 workers 的 `REMEDIATION_RUNNER_*` 环境变量（kustomization 里的引用一起删）；
   - `agent-config/MAINTAINERS.yaml` 和它在 `k8s/monitoring/maintainer-reconcile/` 里的副本（两份逐字节一致）：删掉 `launchd/.50/com.bifrost.remediation-runner`、`launchd/.52/com.bifrost.remediation-runner`、`launchd/.52/com.bifrost.hermes-gateway`；两条 peer-watchdog 的 `what` 改成「看对端 operator-plane」；
   - 指向 runner 的告警或检查脚本（`grep -rn 8781\|remediation-runner k8s scripts`）跟着删或改。

### 二、patrol 回 PROD（②）

- PROD api 继续把其余 operator-plane 路由转发给 .50，**但 `/patrol/*` 不再转发**：由 api 自己提供，读 workers 写进共享状态（`statefile`）的 patrol 记录，api 进程里**不启动** patrol 循环（循环只在 workers）。
- W-32 之后 plane 上只剩这三条 operator 级路由：`PUT /patrol/skills/{id}/enable`、`POST /patrol/trigger/{id}`、`POST /patrol/webhook/{event}`。它们也改由 PROD 处理，plane 上删掉。所以 mini **不需要** PROD operator 令牌。
- 测试：设了 `OPERATOR_PLANE_URL` 时，`GET /api/v1/patrol/skills` 不发往代理，返回的是共享状态里的记录。

### 三、待重启信号（③）

- **信号**：infra 加一个很小的 DaemonSet（`monitoring` 命名空间），hostPath 只读挂 `/var/run`，每 5 分钟检查 `/var/run/reboot-required`，导出 `bifrost_node_reboot_required{node}`（1 / 0）和 `bifrost_node_reboot_required_since_seconds{node}`（文件 mtime），再配一个 PodMonitor。镜像只用 busybox 或同等的小镜像。不在节点上装任何东西，也不改节点配置。
- **告警**：`BifrostNodeRebootPending`，同一节点待重启超过 14 天，warning（记账，不呼人）。登记进 MAINTAINERS 时说明它是信号，不是维护者。
- **Console ⑥**：节点列表显示「待重启（自 某日）」，数据经 platform-api 现有的 Prometheus 查询路径读取。
- **滚动重启做成审批动作——推荐做法，Owner 过目时可以改**：
  - 动作目录加 `rolling_reboot`，D 级，**只记录审批、不由平台执行**（平台不拿节点 root）。批准后返回「请执行 `bash scripts/k3s/rolling-reboot.sh --execute --approval <id>`」。
  - `rolling-reboot.sh --execute` 新增必填的 `--approval <id>`：开跑前用 viewer 令牌读 `GET /api/v1/approvals/<id>`，要求 action 是 `rolling_reboot`、状态是 executed、没过期，否则拒绝。工作日规则保持不变。
  - 执行者照旧是持有节点 SSH 的人：今天是 Agent 或 Owner；第 3 步之后只有 Owner。
  - 测试：脚本的计划测试加上缺少 `--approval`、审批不对时都拒绝；动作目录测试覆盖新条目。

### 四、⑤ Releases 补上 Research、插件和 mini（④）

- Research、Plugins 两行显示**正在跑的镜像版本**：从集群读 Deployment 的容器镜像 tag。读哪些应用、哪个命名空间、哪个 Deployment，要**写在配置里**，不要写死在代码里：platform 不认识具体应用，应用清单放 `config/`（比如 `clusters.yaml` 或新的小文件，随 `sync_platform_k8s_config.sh` 同步，按 W-32 的教训把同步清单和两个 overlay 的 `configMapGenerator` 一起改，`check_ops_context_parity.py` 跟着扩）。
- 没有 STG 部署的应用，STG 列写「无 STG」，不要写「—」（「—」读起来像缺数据）。
- **Mac mini agent** 行改成显示两台 operator-plane 的版本：plane 的 `/health` 加 `version`（构建时注入 git SHA），部署脚本构建时传进去。

### 五、Grafana 走 ops 网关子路径（⑤，Owner 选 A）

- `scripts/k3s/values-kube-prometheus.yaml`：Grafana `server.root_url = https://ops.bifrost.lan/grafana/`、`serve_from_sub_path = true`；`allow_embedding` 和匿名 Viewer 维持现状。NodePort 保留，访问路径会多一层 `/grafana/`，在报告里写明。
- PROD ops 网关 IngressRoute 加一条 `Host(ops.bifrost.lan) && PathPrefix(/grafana)`，指向 `monitoring/kube-prometheus-stack-grafana:80`，优先级高于 Console 那条。STG 网关不加。
- platform-api：PROD 和 STG 都设 `PLATFORM_GRAFANA_URL=https://ops.bifrost.lan/grafana`（overlay 的 env patch）。`opsToolRackCatalog.ts:42` 的兜底地址改成同一个 https 地址。builder 测试加一个 https 用例。
- 报告里写 helm upgrade 命令，**要 Owner 批**；本道不执行。

## 防线

- 部署脚本：新测试断言同步清单里没有 `CURSOR_API_KEY`、operator、admin、`REMEDIATION_RUNNER_TOKEN`；脚本里没有 scp kubeconfig 的步骤；清理 `KUBECONFIG` 那一步是幂等的。现有 `test_deploy_mac_mini_relay.py` 和 `test_deploy_mac_mini_viewer.py` 照旧通过。
- `TestRetiredRoutesAre404` 覆盖本道删掉的路由；patrol 不转发的测试；plane 路由表里没有 operator 级路由（测试断言）。
- `check_maintainers.py --live`（报告里写预期：mini 重部署之前会报 runner 和 hermes-gateway 两类漂移，重部署之后为 0）。
- 待重启告警和 DaemonSet 进 `check_alert_routing.py` 与 kustomize 渲染；`rolling-reboot.sh` 的审批检查测试。
- `check_ops_context_parity.py` 覆盖新加的应用清单配置文件（如果有）。
- RATCHETS.md 登记以上新增防线。

## 门禁

- platform `api/`：`go build ./... && go vet ./... && go test ./...`
- platform `mcp/platform`：`npm test`
- platform `console/`：`npm run lint && npm test && npm run build`
- platform `scripts/agent`：`python3 scripts/agent/test_deploy_mac_mini_*.py`
- infra：`make check-maintainers`、`PATH="/usr/bin:$PATH" python3 scripts/check_alert_routing.py`、`kubectl kustomize k8s/monitoring`、`kubectl kustomize k8s/overlays/platform-prod`、`kubectl kustomize k8s/overlays/platform-stg`、`python3 -m unittest scripts/k3s/test_rolling_reboot_plan.py`、`PLATFORM_ROOT=<w33-platform worktree> python3 scripts/check_ops_context_parity.py`
- infra parity：`bash agent-config/scripts/check-agent-config-parity.sh`（注意它读工作区根的链接；报告里写明测的是哪个树）

## 报告

写 `agent-config/work/ops-arch/reports/LANE-W33.md`，格式按 README：

- 每节写改动（仓库 · 分支 · 完整 SHA）、防线、门禁、验收（一条命令加预期）、要 Owner 批（原样可执行的命令）、后续；
- 附一张「上线顺序」清单，供 Claude 执行，每一步注明要不要 Owner 批。参考顺序：
  1. 合并；
  2. STG 发布，Owner 过目；
  3. PROD 发布（审批）；
  4. 重部署两台 mini（撤 runner、hermes、kubeconfig）；
  5. apply 待重启 DaemonSet、PodMonitor、告警；
  6. helm upgrade Grafana（Owner 批）；
  7. 删 runner 令牌 Secret（Owner 批）；
  8. 跑对账确认 drift 0。

报告从 origin/main 另开 worktree 提交，推 main 用同一条命令：
`bifrost-trade-infra/scripts/release/release.sh window && git push origin <sha>:refs/heads/main`

## 不在本道（之后另派）

- 第 2 步：动作目录加通用动作（`apply_manifest`、`create_job_from_cronjob`、清理类、`run_probe_pod`、兜底的 `owner_run_command`），以及新建一个只读数据库账号（新增角色，DDL 要 Owner 逐次批）。
- 第 3 步：Mac 上的 Agent 换只读 kubeconfig；管理员 kubeconfig 和 `bifrost_deploy` 搬到 Owner 专用目录，preflight 按路径拦。

## 不做

- 多 Agent 运行时：任务与租约、Agent 主机守护进程、交互总线、推理网关、额度账本；
- 发布队列；
- RP 发版策略（`cursor/rp-*` 两条分支不合）；
- 认领与待办箱；
- 工作项编号规则；
- Grok Bot 相关的任何事（它暂停中：不验收 LANE-N / LANE-M2，不收尾它的台账）。
- 不改 `api/internal/approvals/` 的审批语义（删除已退场功能的调用方除外；新增 `rolling_reboot` 条目只走现有的审批流程）。
- 不发版、不部署 mini、不 apply、不 helm upgrade、不写数据库、代码不推 main。
- 不碰 `scripts/agent-guard/`（preflight 闸门）。
- 暂缓、不在瘦身范围：TWS 自动重启、交易区迁移、网络分区。
