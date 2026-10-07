# LANE-B1 报告

## 改动
- 仓库：bifrost-platform
- 分支：`cursor/b1-platform`（已推 origin，未推 main）
- 完整 SHA：`d61fc70d7bd95fe947c64d1851761df0bf7d764d`
- Change-Id：`Ib3a177402a3c6ddac6e5a4720be3bdd8106a8231`

新增 `api/internal/actions`（动作目录、参数规范化、`params_hash`、写路由豁免清单）和 `api/internal/approvals`（statefile key `approvals`，未结全留、已结留最近 500 条）。PROD 落 ConfigMap `platform-state-approvals`。

共享文件（只做接线，未改 go.mod）：
- `api/internal/server/server.go`：注册 `GET /api/v1/actions` 与审批路由；C/D 直调包进审批闸；CORS 放行 `X-Bifrost-Session`
- `api/internal/server/actions_wire.go`（新）：批准时用存下来的参数调用原 handler；daemon 副本数查询只用于定级

未改 `console/`、`mcp/`、`agent/`、`alertrelay/`。直调端点都还在。

## 防线
- `api/internal/actions/coverage_test.go` `TestWriteRoutesAreCataloguedOrExempt`：遍历 chi 路由表，每个写方法路由必须在目录里或在 `api/internal/actions/coverage.go` 的豁免清单里；豁免项必须仍是活路由
- `api/internal/actions/catalog_test.go` `TestScaleTierDoesNotWeakenDaemonScaleUp`：daemon 扩容（以及读不到当前副本且请求大于 0）定为 X，直调仍进原 handler 的 D10 闸，不换成「approval required」
- `api/internal/approvals/http_test.go` `TestDirectCDRequiresApproval`：C/D 直调 403 `{"error":"approval required","action":…}`；B 级 wake 与 daemon 扩容都不走这道 403
- `api/internal/approvals/service_test.go` `TestApproveRejectAuthAndAudit`：operator 批准被拒（401，沿用 `Require(admin)`）；admin 批准写入 channel
- `api/internal/approvals/service_test.go` `TestCreateTiersAndStoredExecution`、`TestTamperedParamsDoNotRun`、`api/internal/approvals/http_test.go` `TestExecutedApprovalUsesStoredParamsOnce`：执行的是创建时存下的参数；批准请求里另带的 params 无效；改磁盘上的参数但不改 hash 则拒绝执行
- `api/internal/approvals/service_test.go` `TestCreateTiersAndStoredExecution` 与 http 测试：同一次申请批准两次，执行函数只跑一次
- `api/internal/approvals/service_test.go` `TestExpiredCannotBeApproved`：超过 24h 不能批，状态变为 expired
- `api/internal/approvals/http_test.go` `TestXTierCreateForbidden` 与 service 测试：X 级创建 403
- 审计：`approval.create` / `approval.approve`（detail 含 `channel=`）/ `approval.reject` / `approval.expire` / `approval.execute`，走 `actuation.AuditLog`。`requester` 取 `X-Bifrost-Session`，没有该头时用令牌主体名

## 门禁
- `cd api && go build ./...` → exit 0
- `cd api && go vet ./...` → exit 0
- `cd api && go test ./...` → exit 0（58 个包 ok；`cmd/platform-api` 与 `cmd/operator-plane` 无测试。相对 origin/main 的 56 个包，多了 `actions` 和 `approvals`）

## 验收
```bash
cd bifrost-platform/api && go test ./internal/actions/... ./internal/approvals/...
```
预期：两个包都 `ok`。其中 `TestWriteRoutesAreCataloguedOrExempt`、`TestDirectCDRequiresApproval`、`TestExecutedApprovalUsesStoredParamsOnce`、`TestExpiredCannotBeApproved`、`TestXTierCreateForbidden` 通过。

## 要 Owner 批
发版 bifrost-platform（Claude Code 申请并执行）。本道只推了分支 `cursor/b1-platform`，没有 deliver、kubectl、helm、release.sh，也没有改 TECH_DEBT.md / RATCHETS.md。

## 接口形状（B2 / B3 直接用）
- `GET /api/v1/actions` → JSON 数组 `[{id, tier, description, params}]`。`tier` 是静息级别；参数升级写在 `description` 里。创建申请时的 `tier` 才是这次参数的级别。
- `POST /api/v1/approvals`（operator+）→ 201 `{id, action, tier, params_hash, status:"pending", requester, expires_at}`。B 级 400 `{"error":"call directly","action","tier":"B"}`。X 级 403 `{"error":"forbidden","action","tier":"X"}`。
- `GET /api/v1/approvals?status=pending|all` → `{"approvals":[...]}`（缺省 `pending`）。`GET /api/v1/approvals/{id}` 返回整张申请单。viewer+。
- `POST /api/v1/approvals/{id}/approve`（admin）`{channel: chat|phone|console}` → 200 `{status:"executed"|"failed", result|error}`。operator 是 401 `admin token required`。
- `POST /api/v1/approvals/{id}/reject`（admin）`{reason}` → 200 `{id, status:"rejected"}`。
- C/D 直调：没有相同 `action` + `params_hash` 的 **executed** 申请 → 403 `{"error":"approval required","action":…}`。原来就是 admin 的路由（drain、关机、加入节点、rollback、addon、data-clone），operator 仍先被角色中间件 401，admin 才看到这道 403。

## 目录（id → 级别）

级别列里的箭头是按参数升级，不是第二条动作。`C（暂定）` 是细则没有点名、本道按生产变更先收紧的，请 Claude Code 改级或确认。

| id | 级别 |
|---|---|
| start_pipeline_run | B（名字以 `-prod` 结尾 → C） |
| delete_pipeline_run | B |
| gitops_sync_app | B（应用名是 prod / 以 prod- 开头 / 以 -prod 结尾 / 含 -prod- → C） |
| gitops_rollback_app | B（同上，PROD 应用 → C） |
| rollout_restart_deployment | B（namespace 为 data、bifrost-prod、bifrost-platform-prod → C） |
| scale_deployment | C（Deployment 名 daemon 且是扩容 → X；读不到当前副本且 replicas>0 也按 X，直调仍进 TD-222） |
| delete_pod | B |
| cordon_node | C |
| uncordon_node | C |
| drain_node | D |
| poweroff_compute_node | D |
| wake_compute_node | B |
| join_cluster_node | D |
| trigger_cnpg_backup | C |
| repair_cnpg_wal_store | D |
| trigger_data_clone | C |
| market_data_heal | B（路径固定为 `POST /api/v1/plugins/market-data/api/market/doctor/heal`；通配代理本身在豁免清单） |
| ib_reconnect | B |
| ib_mode | C（暂定） |
| ib_maintenance | C（暂定） |
| ib_self_heal | C（暂定） |
| unifi_firewall_apply | D |
| stack_install_addon | D |
| stack_upgrade_addon | D |

计数（24 条目录，按 GET 返回的静息级别）：**B 9，C 8（其中 3 条暂定），D 7，A 0，X 0**。X 只出现在 `scale_deployment` 的 daemon 扩容参数上，不能建申请。

## 后续
- 暂定级别请拍板：`ib_mode`、`ib_maintenance`、`ib_self_heal`（`api/internal/actions/catalog.go`，`Provisional: true`）。细则只把 IB 重连定为 B，模式切换写在覆盖范围里但没有级别。
- 名字不以 `-prod` 结尾、但实际发 PROD 的流水线（例如 `bifrost-deliver-platform`）按字面规则仍是 B。若要收成 C，改 `ProdPipeline`。
- 批准已经执行过一次之后，参数哈希相同的直调仍会再进原 handler（契约写的是「有已执行申请才放行」）。一次批准本身不会执行两次。若要避免 drain / 防火墙 / scale 被打两次，把「放行」改成消耗这张申请。
- 未定级、因此只进豁免清单、没有改行为的写路由（`api/internal/actions/coverage.go` 的 `exempt(...)`）。优先看这几类：`POST /cluster/postgres/backups/sweep-failed`（删失败备份，像 D）；`POST /cluster/sync-kubeconfig` 与 `POST /cluster/kubeconfig-secret/ensure`；`POST /cluster/addons/metrics-server/ensure` 与 `kube-prometheus-stack/ensure`（像 stack addon，可能是 D）；`PUT /cluster/data-clone/schedule`；`POST /dev-sessions/{name}/control`（D10 仍在该 handler 里，本道没动）；`POST /delivery/supply-chain/mirror-sync` 与 `dockerfile-configmaps/refresh`；`POST /plugins/market-data/api/*` 与 `DELETE` 同路径、`POST /plugins/flex-query/api/*`（heal 以外的插件写）；`POST /ops-agent/alertmanager`；发布门 / vision / build-phase / migrate-streams 的 gate 与 signoff；remediation、operate queue、checklist、lineage、code-health、trust-overrides、operator-plane 的 L-1 写。新写端点不进目录也不进这份清单时，`TestWriteRoutesAreCataloguedOrExempt` 会失败。
- 无 preflight 拦截。
