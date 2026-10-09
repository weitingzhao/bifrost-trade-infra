# LANE-W33B 报告

日期：2026-10-09。道文件以当时 `origin/main` `aea94a77a42c3a1e5c791231ddacf655253b2d8a` 为准。代码只在分支上，没有合并，没有 apply，没有写数据库。

## 改动

- bifrost-platform · `cursor/w33b-platform` · `2de35b9179c09cdcbfbac2218b4d2eac1036af27` · Change-Id `I53a2d66e080a547a509a0a4793ced5afafc2747a` · 已推送
- bifrost-trade-infra · `cursor/w33b-infra` · `e5b04b45f5feb5da6c0342d0a007371fbf09ca54` · Change-Id `I0dea8204dcadf5128563bf544ad680ca3465bd8d` · 已推送

〇节五件，都按 2026-10-09 的推荐做了：

1. `owner_run_command` 只把命令和 sha256 记进审批结果，平台不执行。批准后的消息是 `Run: bash scripts/owner/owner-run.sh <id>`。`scripts/owner/owner-run.sh` 只给 Owner 用，文件头写明 Agent 不得运行。
2. `apply_manifest` 只启动固定流水线 `bifrost-apply-manifest`，任务身份是 `bifrost-applier`。平台自己的 ServiceAccount 没有因此加宽。Research 与两个插件在策略里是 C，只在 PROD 维护侧生效。没有放宽 W-31。
3. 探针是 Job。`env_from` 只允许策略里列出的三个命名空间。没有做第 3 步的只读 kubeconfig。
4. 没有改 `release.sh`。发布链留给 LANE-W33C。
5. TD-271 的 ValidatingAdmissionPolicy 和收窄后的 AppProject `bifrost` 已写进 `k8s/platform-rbac`，未 apply。`tekton-trigger` 未修，记在后面。

白名单只在 `config/actuation-policy.yaml`。Go 的新包不引用具体命名空间、仓库或镜像名（`TestGoSourcesDoNotNameAllowList`）。同步脚本、两个 overlay 的 configMapGenerator、Tekton 副本、`check_ops_context_parity.py` 一起改了。

动作：`plan_manifest`（B）、`apply_manifest`（计划里最高的命名空间；名为 daemon 的 Deployment 是 X）、`create_job_from_cronjob`、`delete_finished_jobs`（B）、`run_probe_pod`、`owner_run_command`（D，无直接路由）。C/D 走现有审批。没有改 `api/internal/approvals/`。MCP 增加四个 B 级工具。审批卡对 `owner_run_command` 显示命令原文，对 `apply_manifest` 拉取计划摘要。

`code-health` 提示 platform 超长文件 12，基线 13，exit 0。没有降低 `OVERSIZED_PLATFORM_BASELINE`。

## 防线

- `RATCHETS.md` 新增四条：白名单不进 Go、TD-270 两进程 Update、owner-run 不执行、Job/applier/准入文件的静态检查。
- TD-270 状态改为待你签收，条目未删。验收结果：PASS 2026-10-09 `2de35b9179c09cdcbfbac2218b4d2eac1036af27`。
- TD-271 状态改为在做。`--live` 要等 apply，没有把它放进待你签收。

## 门禁

测的是 `/tmp/cursor-w33b/w33b-platform` 与 `/tmp/cursor-w33b/w33b-infra`，不是工作区共享 checkout。

- `cd bifrost-platform/api && go build ./... && go vet ./...` → 通过
- `go test ./...` 第一次只有 `TestProbeAndJobClassify` 失败（map 迭代顺序）。改成按「不在 env_from 里」挑选之后，`go test ./internal/actions/ ./internal/actuationpolicy/ ./internal/cluster/ ./internal/server/ ./internal/mcp/` → 通过。其余包在第一次全量里已经通过。
- `cd bifrost-platform/api && go test ./internal/cluster -run 'DataClone.*(Share|Reload|Survives)' -count=1 -v` → 3 passed
- `cd mcp/platform && npm test` → 20 passed
- `cd console && npm run lint` → 0 error，3 条原有 warning（Flex 面板，本道未改）
- `cd console && npm test` → 107 files，683 passed
- `cd console && npm run build` → 通过（旁边的 `bifrost-ui` worktree 是 detached `origin/main` `9b635b2`，已 `npm ci && npm run build`）
- `PLATFORM_ROOT=<w33b-platform> python3 scripts/check_ops_context_parity.py` → `ok: 55 decisions match … (D10=BLOCKED)`
- `kubectl kustomize k8s/platform-rbac`、`k8s/overlays/platform-prod`、`k8s/overlays/platform-stg`、`k8s/cicd/tekton/apply-manifest` → 通过
- `cd k8s/data/role-matrix && python3 -m unittest test_check_role_matrix.py` → 11 passed。从 infra 根直接 `python3 -m unittest k8s/data/role-matrix/test_check_role_matrix.py` 会因导入路径失败，这是原有跑法，本道未改这个测试。
- `KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_platform_rbac.py` → `ok: 138 permission answers match`。新的 can-i 在 `--live`，默认路径只做 YAML 静态断言，所以未 apply 也能过。
- `python3 scripts/check_admission_guards.py` → `ok: admission files match the actuation policy`。没有跑 `--live`。
- `bash scripts/owner/owner-run_test.sh` → 拒绝错误状态、过期、哈希不符
- 临时根 `/tmp/w33b-parity.16R7`（`bifrost-platform` 与 `bifrost-trade-infra` 指向上述 worktree，`.cursor` / `.claude` / `CLAUDE.md` / `AGENT_FACTS.md` 指向工作区根）上 `bash scripts/check-agent-config-parity.sh` → exit 0。新鲜度警告两条：worktree 的 `.git` 是文件，脚本写成「从未 fetch」。不算失败。

## 验收

```bash
cd bifrost-platform/api && go test ./internal/cluster -run 'DataClone.*(Share|Reload|Survives)' -count=1 -v
```

预期：三个测试 PASS。已在 platform `2de35b9179c09cdcbfbac2218b4d2eac1036af27` 上看到 PASS。

准入的活体验收还不能跑：

```bash
python3 scripts/check_admission_guards.py --live
```

预期：apply `k8s/platform-rbac` 之后才全部 PASS。现在未 apply，所以没有把 TD-271 标成待你签收。

## 数据库实测

只读。登录角色 `bifrost`，经 `192.168.10.73:30432`，会话 `default_transaction_read_only=on`。四个库都能 CONNECT：`bifrost_dev`、`bifrost_stg`、`bifrost_prod`、`bifrost_golden_source`。没有打印列里的值。

列名匹配 `token|secret|password|api_key|apikey|passwd|private_key|access_key|credential`：

| 库 | 表 | 列 | 类型 | 判定 |
|---|---|---|---|---|
| bifrost_golden_source | research.copilot_bridge_event | input_tokens | integer | 列名含 token。整数，是用量计数，不是存下来的凭证 |
| bifrost_golden_source | research.copilot_bridge_event | output_tokens | integer | 同上 |

另外三个库没有命中。

按道文件，有命中就停下这一节。没有建 `agent_reader`，没有改授权，没有改 `expected.yaml`，没有往 `AGENT_FACTS.md` 加连接说明。上线顺序里的数据库步骤因此未准备。

## 要 Owner 批

合并两个分支之后，在那棵 infra 树上：

```bash
kubectl apply -k k8s/platform-rbac
kubectl apply -k k8s/cicd/tekton/apply-manifest
```

五个 Application 已经改成 `project: bifrost`，但要等上面的 AppProject 存在之后再同步。同步完成后再清空 default（不要删这个项目）：

```bash
kubectl apply -f k8s/cicd/appprojects/default-empty.yaml
```

然后：

```bash
KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_platform_rbac.py --live
python3 scripts/check_admission_guards.py --live
```

STG / PROD 的平台发版另一次批准。STG 能看见新动作，执行器会因为 STG 没有新的 Job 与 applier 绑定而失败。PROD 才真正执行。

数据库账号这一节没有准备出可执行的 DDL。不要按道文件原稿去建 `agent_reader`。

`owner-run.sh` 由 Owner 在批准之后自己跑。Agent 不跑。

## 上线顺序

1. 合并 `cursor/w33b-platform` 与 `cursor/w33b-infra`。先合 infra 会把主检出的旧超长文件计数顶破 platform 新基线的问题本道没有发生：没有改基线。
2. Owner：`kubectl apply -k k8s/platform-rbac`（applier、Job 权限、ValidatingAdmissionPolicy、AppProject `bifrost`）。
3. 同步五个 Application 到 `project: bifrost`。
4. Owner：`kubectl apply -f k8s/cicd/appprojects/default-empty.yaml`。
5. Owner：上面的两条 `--live` 检查。
6. Owner：`kubectl apply -k k8s/cicd/tekton/apply-manifest`。
7. Owner 看过之后发 STG。新动作可见，直接调用被拒绝。
8. Owner 批准后发 PROD。
9. PROD 冒烟：对 `bifrost-dev` 里一份无害 ConfigMap 做 plan 再 apply；从 `monitoring/maintainer-reconcile` 拉一个 Job；用允许列表里的 curl 镜像跑一个探针；删掉这些已结束的 Job；提一条 `owner_run_command` 然后拒绝，确认平台没有执行。
10. 数据库步骤未准备。四个库的列名扫描有两处命中，账号和授权都没有做。

## 后续

- TD-270 等 Owner 回「签收 TD-270」。不要在那之前删条目。
- TD-271 等 apply 和 `--live` 通过后再进待你签收。
- `tekton-trigger`（`cicd/tekton-trigger-runs` 可以创建 PipelineRun）和本道修的是同一类能力，本道没有改它。
- 只读数据库账号停在列名命中上。要换授权方式需要 Owner 另定，本道没有换。
- 旧文字没有清完。`agentTaskCatalog.ts` 零引用，已删。`agentScopes.ts` 仍被 checklist 与 fleet snapshot 引用，没有删。下面这些文件仍能被 `grep -rniE 'remediation runner|remediation-runner|hermes|:8781|:8782' console/src api/internal mcp` 命中，不完全是「已退役」测试：

```
api/internal/mcp/catalog.go
api/internal/agentbridge/handler.go
api/internal/agentbridge/handler_test.go
api/internal/server/server.go
api/internal/server/server_test.go
api/internal/server/layering_test.go
api/internal/agentgovernance/skillrun.go
api/internal/agentgovernance/outcome.go
api/internal/delivery/supply_chain.go
api/internal/checklist/prober_test.go
api/internal/operatorplane/plane.go
api/internal/launchd/list_test.go
console/src/pages/AutonomousSkillsPage.tsx
console/src/api/agentTypes.ts
console/src/api/opsContextTypes.ts
console/src/lib/standards/designSystemCatalog.ts
console/src/lib/task-mode/taskModeCatalog.ts
console/src/lib/task-mode/taskModeVisual.ts
console/src/lib/observability/attentionRemediationCatalog.ts
console/src/lib/observability/observabilityViewModel.ts
console/src/lib/observability/__tests__/observabilityViewModel.test.ts
console/src/lib/cluster/clusterFailureTriage.ts
console/src/lib/observability/alertMapping.ts
console/src/lib/shell/consoleRoutes.ts
console/src/lib/observability/signalRegistry.ts
console/src/lib/delivery/deliverPlatformPhases.ts
console/src/lib/control-room/__tests__/missionSignals.test.ts
console/src/lib/control-room/controlRoomOperatePack.ts
console/src/lib/agent/__tests__/macHostRole.test.ts
console/src/lib/control-room/fleetSnapshot/buildVendorCell.ts
console/src/lib/control-room/__tests__/fleetSnapshot.test.ts
console/src/lib/agent/operatorPlaneFixPrompt.ts
console/src/lib/agent/playbookAgentPrompts.ts
console/src/lib/agent/macHostRole.ts
console/src/lib/control-room/fleetSnapshot/types.ts
console/src/lib/architecture/consoleSeatCatalog.ts
console/src/lib/architecture/cicdBootstrapCatalog.ts
console/src/lib/architecture/postQaOwnerGatePack.ts
console/src/lib/architecture/systemDomainCatalog.ts
console/src/lib/architecture/blueprintCatalog.ts
console/src/lib/architecture/dualFlywheelVisionCatalog.ts
```

用户可见的几处已经改成 operator plane / .50 告警中转（environments catalog、Rocket 子系统、每日检查里原来的 Hermes 行）。其余命中还在。

- 没有开始 LANE-W33C。
