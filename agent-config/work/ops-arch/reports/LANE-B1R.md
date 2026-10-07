# LANE-B1R

## 改动

- bifrost-platform · `cursor/phase2-platform` · `816a80390c5a113484f253f94460888030c1401a`
- 起点：`origin/main` `46464410bf841f6865eda3daabea60ab181a9940`
- 已推 `refs/heads/cursor/phase2-platform`。没有推 main（远端 main 仍是 `46464410bf841f6865eda3daabea60ab181a9940`）。没有发版。
- 四条历史分支未改：
  - `cursor/b1-platform` `d61fc70d7bd95fe947c64d1851761df0bf7d764d`
  - `cursor/b2-platform` `ccdf2005727a7990d1b2fbc57533e64badd7cb3a`
  - `cursor/b3-platform` `40187953eb7c2e4754259316d091ce2ec15fb466`
  - `cursor/b4-platform` `388d43118a2a6f10e732fa3ed25b95d324d7564b`

合入顺序：

1. `cursor/b1-platform`：fast-forward，无冲突。
2. `cursor/b2-platform`：merge，无冲突。
3. `cursor/b3-platform`：merge，无冲突。
4. `cursor/b4-platform`：`api/internal/server/server.go` 冲突。保留 B4 的 reporter 路由（Alertmanager 只挂在 reporter 组，operator 组里的重复 `POST /ops-agent/alertmanager` 删掉），保留 B1 对 `unifi_firewall_apply` 和 IB control 的 `guard`。合并提交 `7592cdff2d6993a4da0c1a0f9cd26eb68c39a6c4`。

然后在尖端提交上做了下面 8 项。

### 1. 护栏漏洞（成立，已改）

`actions_wire.go` 原先用 `HasExecuted(action, hash)` 放行直调：同一参数批准执行一次后，直调永久通过。现已删掉 `HasExecuted`。C/D 直调一律 403。审批执行器经 `invokeAction` 调用 handler，上下文带未导出的 `executorContextKey`；HTTP 头和请求体写不进这个键。X（daemon 扩容）仍直接进原 handler，TD-222 D10 闸门没动。

### 2. 流水线定级

`ProdPipeline` 改为显式集合，不再用「名字以 `-prod` 结尾」。

### 3. IB 级别

`ib_self_heal` → B。`ib_mode`、`ib_maintenance` → C。`Provisional` 字段已删除。

### 4. 豁免清单移进目录

| 路由 | id | 级别 |
|---|---|---|
| `POST /api/v1/cluster/postgres/backups/sweep-failed` | `sweep_failed_backups` | C |
| `POST /api/v1/cluster/addons/metrics-server/ensure` | `ensure_metrics_server` | D |
| `POST /api/v1/cluster/addons/kube-prometheus-stack/ensure` | `ensure_kube_prometheus_stack` | D |
| `POST /api/v1/cluster/sync-kubeconfig` | `sync_kubeconfig` | D |
| `POST /api/v1/cluster/kubeconfig-secret/ensure` | `ensure_kubeconfig_secret` | D |
| `PUT /api/v1/cluster/data-clone/schedule` | `update_data_clone_schedule` | C |
| `DELETE /api/v1/plugins/market-data/api/*` | `market_data_delete` | C |

发布门、vision、build-phase、migrate-streams 的 gate/signoff，以及 namespace ensure、POST 插件通配、flex-query POST，仍在豁免清单。

### 5. B2 接线

`POST /api/v1/approvals` 落库之后、写 201 之前调用 `approvalnotify.NotifyCreated`。错误丢掉。批准、拒绝、过期不调用。

### 6. MCP 令牌文件

进程环境没有被钉的那一个键时，读 `~/.config/bifrost/mcp-tokens.env`，且只在权限位正好是 `0600` 时读。只认 `PLATFORM_VIEWER_TOKEN` / `PLATFORM_OPERATOR_TOKEN` / `PLATFORM_ADMIN_TOKEN`。`PLATFORM_TOKEN_ENV_KEY` 仍只读它钉住的那一个键。日志和错误不含令牌。环境优先于文件。回环地址上，文件没有值时才回落到仓库 `.env`。

### 7. stdio 工具对齐

`stdioMirroredTools` 与 `mcp/platform/src/stdioToolNames.ts` 一致，75 个。三个 dev-sessions 工具只留在 `bifrost-local`（目录里 `Implemented=false`）。`request_action`、`get_request`、`list_requests`、`wait_for_request` 在全量 server，目录 `Implemented=true`。

### 8. 目录计数

`GET /api/v1/actions` 返回静息级别（`View.Tier`），不是按参数分类后的级别。实际 **31** 条（B1 报告 24，汇总 35，以代码为准）。

## ProdPipeline

只读 `kubectl --kubeconfig ~/.kube/bifrost-k3s.yaml -n cicd get pipelines`（2026-10-07）。看每条流水线末尾是不是对生产命名空间做 rollout 或 gitops-sync。

C（在清单里）：

| 流水线 | 证据 |
|---|---|
| `bifrost-deliver-prod` | rollout 参数 `namespace=bifrost-prod`；gitops-sync 参数 `application=bifrost-prod` |
| `bifrost-deliver-platform-prod` | rollout 参数 `namespace=bifrost-platform-prod`；gitops-sync 参数 `application=bifrost-platform-prod` |
| `bifrost-deliver-research` | gitops-sync 参数 `application=bifrost-research`；`bifrost-rollout-research` 默认 `namespace=research`。Research 只有这一个环境，就是生产 |

B（不在清单里；只构建镜像、CI，或只动 STG）：

- `bifrost-deliver-platform`：rollout / gitops 任务默认 `bifrost-platform-stg`，流水线没有改写命名空间
- `bifrost-deliver-stg`：默认 `bifrost-stg`
- `bifrost-build-flex-query`、`bifrost-build-frontend-stg`、`bifrost-build-ib-gateway`、`bifrost-build-market-data`、`bifrost-build-research-dagster`、`bifrost-build-research-pine`、`bifrost-build-stg`：kaniko / 构建，没有生产 rollout
- `bifrost-ci-frontend`、`bifrost-ci-platform`、`bifrost-ci-python`、`bifrost-clone-frontend-smoke`、`bifrost-smoke`：检查或 echo

`gitea-mirror-sync` 只同步 git 镜像，不算改生产工作负载。名字以 `-prod` 结尾但没进清单的（测试用 `not-a-pipeline-prod`）是 B。

## GET /api/v1/actions

静息级别：A 0，B 10，C 10，D 11，X 0。合计 31。

按参数还会变的（JSON 里仍是静息级别）：

- `start_pipeline_run` 静息 B；名字在 `ProdPipeline` 里则 C
- `gitops_sync_app`、`gitops_rollback_app` 静息 B；`ProdApp` 则 C
- `rollout_restart_deployment` 静息 B；命名空间 `data`、`bifrost-prod`、`bifrost-platform-prod` 则 C
- `scale_deployment` 静息 C；Deployment `daemon` 的扩容是 X，直调仍进 D10，不能走审批

| 级别 | id | 方法与路径 |
|---|---|---|
| B | `delete_pipeline_run` | DELETE `/api/v1/delivery/runs/{id}` |
| B | `delete_pod` | DELETE `/api/v1/cluster/workloads/pods/{namespace}/{name}` |
| B | `gitops_rollback_app` | POST `/api/v1/gitops/apps/{name}/rollback` |
| B | `gitops_sync_app` | POST `/api/v1/gitops/apps/{name}/sync` |
| B | `ib_reconnect` | POST `/api/v1/plugins/ib-gateway/control/{action}` |
| B | `ib_self_heal` | POST `/api/v1/plugins/ib-gateway/control/{action}` |
| B | `market_data_heal` | 目录项，直调路径是 POST `/api/v1/plugins/market-data/api/market/doctor/heal`（通配 POST 仍豁免） |
| B | `rollout_restart_deployment` | POST `/api/v1/cluster/workloads/rollout-restart` |
| B | `start_pipeline_run` | POST `/api/v1/delivery/pipelines/{name}/runs` |
| B | `wake_compute_node` | POST `/api/v1/cluster/nodes/{name}/wake` |
| C | `cordon_node` | POST `/api/v1/cluster/nodes/{name}/cordon` |
| C | `ib_maintenance` | POST `/api/v1/plugins/ib-gateway/control/{action}` |
| C | `ib_mode` | POST `/api/v1/plugins/ib-gateway/control/{action}` |
| C | `market_data_delete` | DELETE `/api/v1/plugins/market-data/api/*` |
| C | `scale_deployment` | POST `/api/v1/cluster/workloads/scale` |
| C | `sweep_failed_backups` | POST `/api/v1/cluster/postgres/backups/sweep-failed` |
| C | `trigger_cnpg_backup` | POST `/api/v1/cluster/postgres/backup` |
| C | `trigger_data_clone` | POST `/api/v1/cluster/data-clone` |
| C | `uncordon_node` | POST `/api/v1/cluster/nodes/{name}/uncordon` |
| C | `update_data_clone_schedule` | PUT `/api/v1/cluster/data-clone/schedule` |
| D | `drain_node` | POST `/api/v1/cluster/nodes/{name}/drain` |
| D | `ensure_kube_prometheus_stack` | POST `/api/v1/cluster/addons/kube-prometheus-stack/ensure` |
| D | `ensure_kubeconfig_secret` | POST `/api/v1/cluster/kubeconfig-secret/ensure` |
| D | `ensure_metrics_server` | POST `/api/v1/cluster/addons/metrics-server/ensure` |
| D | `join_cluster_node` | POST `/api/v1/cluster/nodes/join` |
| D | `poweroff_compute_node` | POST `/api/v1/cluster/nodes/{name}/poweroff` |
| D | `repair_cnpg_wal_store` | POST `/api/v1/cluster/postgres/wal-store/repair` |
| D | `stack_install_addon` | POST `/api/v1/stack/addons/{name}/install` |
| D | `stack_upgrade_addon` | POST `/api/v1/stack/addons/{name}/upgrade` |
| D | `sync_kubeconfig` | POST `/api/v1/cluster/sync-kubeconfig` |
| D | `unifi_firewall_apply` | POST `/api/v1/network/firewall/apply` |

## 防线

- `api/internal/approvals/http_test.go` `TestExecutedApprovalUsesStoredParamsOnce`：同一参数批准执行一次后，直调仍是 403；执行器只跑一次
- `api/internal/approvals/http_test.go` `TestDirectCDRequiresApproval`：C/D 直调 403；`ib_mode` 403；`ib_self_heal` 不进审批门；daemon 扩容不进审批门
- `api/internal/approvals/http_test.go` `TestCreateNotifiesAndSurvivesRelayFailure`：创建会 notify；中转 502 仍返回 201；令牌不进正文
- `api/internal/server/actions_wire_test.go` `TestDirectCDStaysForbiddenWithoutExecutorMarker`：伪造头和别的 context 键仍是 403；带执行器标记的内部调用会执行
- `api/internal/server/actions_wire_test.go` `TestDaemonScaleUpStillReachesHandler`：未知副本数的 daemon 扩容仍到达 handler
- `api/internal/actions/catalog_test.go` `TestPipelineAndAppTiers`、`TestIBTiersAreAssigned`、`TestCatalogIDsUniqueAndLeveled`
- `api/internal/actions/catalog_test.go` `TestScaleTierDoesNotWeakenDaemonScaleUp`（D10 分类未改）
- `api/internal/actions/coverage_test.go` `TestWriteRoutesAreCataloguedOrExempt`
- `api/internal/mcp/catalog_test.go` `TestCatalogImplementedAllHaveStdioMirror`（75，与 `stdioToolNames.ts` 逐名一致）
- `mcp/platform/src/tokenResolve.test.ts`：环境优先、0600 文件兜底、非 0600 拒绝、只读被钉的键
- `console/src/pages/__tests__/ApprovalsPage.test.tsx`（本道未改页面；全量 vitest 含这 3 个）

## 门禁

在 `/tmp/cursor-b1r-platform`，退出码分开看。console 的 `node_modules` 是指向共享 checkout 的符号链接。

- `api` `go build ./...` → 0
- `api` `go vet ./...` → 0
- `api` `go test ./...` → 0（列出的包全部 ok）
- `console` `npx tsc -b` → 0
- `console` `npm run lint` → 0（19 条既有 warning，0 error）
- `console` `npx vitest run` → 0，119 files，804 passed
- `console` `npm run build` → 0
- `mcp/platform` `npx tsc -b` → 0
- `mcp/platform` `npm test` → 0，14 passed

## 验收

```bash
cd bifrost-platform/api && go test ./internal/actions/... ./internal/approvals/... ./internal/server/...
cd bifrost-platform/console && npx vitest run src/pages/__tests__/ApprovalsPage.test.tsx
cd bifrost-platform/mcp/platform && npm test
```

预期：三组都是退出码 0。第一组覆盖「执行一次后直调仍 403」「内部路径仍执行」「daemon 扩容不进审批门」「ProdPipeline 清单」「IB 级别」。页面测试 3 个通过。`npm test` 含令牌文件三例（环境优先、0600 兜底、非 0600 拒绝）。

本次已跑过：`go test ./internal/actions/ ./internal/approvals/ ./internal/server/ ./internal/mcp/ ./internal/approvalnotify/` 退出码 0；全量 `go test ./...` 退出码 0；vitest 804 通过（含 Approvals 页）；`mcp/platform` `npm test` 14 通过。

## 要 Owner 批

发版这一条分支 `cursor/phase2-platform`（`816a80390c5a113484f253f94460888030c1401a`），由 Claude Code 申请。本道不推 main，不起 deliver，不跑 `release.sh`。

## 后续

- `mcp/platform/src/actionTiers.ts:202` 把所有 `start_pipeline_run` 标成 C。对 B 流水线，MCP 会去建审批，API 会回「call directly」。
- `actionTiers.ts:234` 和 `:242` 把 `ensure_metrics_server`、`ensure_kube_prometheus_stack` 标成 C；目录里是 D。MCP 仍会建审批，落库级别以 API 的 D 为准。
- `sweep_failed_backups`、`sync_kubeconfig`、`update_data_clone_schedule`、`market_data_delete` 不在 `WRITE_SPECS` 里。经 `decideWrite` 会变成 `unlisted_write`，API 不认这个 action。
- `api/internal/server/actions_wire.go:50`：参数抽不出来或缺必填项时，C/D 仍会落到原 handler（原有行为）。空 body 且没有必填项的新路由会 403。
- 无其他阻塞。preflight 没有拦截。没有改 bifrost-trade-infra，没有改共享 checkout，没有打印或提交令牌。
