# LANE-P 报告（Cursor · 2026-10-06）

分支：
- bifrost-platform `cursor/td-platform`（基于 `origin/td-l6`），4 个提交，已推分支，未动 main
- bifrost-trade-infra `cursor/td-platform`（基于 `origin/main` 4aa275c），3 个提交，已推分支，未动 main

最终门禁（platform 分支 HEAD `2899d9372030b45627536d954e2647b1d5931127`）：
- Go：`go build ./...` → 0 · `go vet ./...` → 0 · `go test ./...` → 54 个包 ok，0 FAIL
- Console：`npx tsc -b` → 0 · `npm run lint` → 0 errors（20 条已有 warning）· `npx vitest run` → 118 files / 801 passed · `npm run build` → 0
- `mcp/platform`：`npx tsc --noEmit` → 0

---

## TD-220
- Claim：成立。`origin/td-l6:api/internal/server/server.go:528` `POST /cluster/sync-kubeconfig` 在 Require 组之外，匿名可调；`api/internal/operatorplane/plane.go:132` `POST /hermes/run-first-task` 的 operator 标志为 `false`。husbandry-sync 已由 TD-208 收口，这部分不再成立。另一处：LoadAuth 失败时只是静默，所有受保护路由都回 401，没人看得到。
- 改动：bifrost-platform · `cursor/td-platform` · `014ec77fffcd60a9e2abec36ffffaff124287c8b`
  - sync-kubeconfig 移进 `/cluster` operator 组；功能关闭时回 409（以前回 200），上游失败回 502；写 audit `sync_kubeconfig`
  - run-first-task 改为 `operator=true`
  - auth 没加载时：`slog.Error`，`/health` 多出 `auth_loaded`，新增 gauge `bifrost_platform_auth_loaded`
  - Console：`syncClusterKubeconfig` 改走 `authedFetch`；ClusterPage 只在 `canOperate` 时显示按钮
  - bifrost-trade-infra · `cursor/td-platform` · `2291bbaf095de90b986de93a428eda2e4895ca08`：`k8s/monitoring/bifrost-alerting-rules.yaml` 新增告警 `BifrostPlatformAuthNotLoaded`（`min by (namespace)(bifrost_platform_auth_loaded) == 0`，持续 10m，critical）
- 防线：
  - `api/internal/server/auth_routes_test.go` · `TestEveryMutatingRouteRequiresARole`：用 chi.Walk 遍历所有路由，把每条路由的中间件链套在一个哨兵 handler 上，发一个不带 token 的请求，哨兵被调到就判失败。不是按函数名判断。白名单 `anonymousWrites` 为空，`ticketAuthenticated` 只有 `GET /api/v1/console/ws`；遍历到的路由少于 50 条也判失败。手工放进一条不加保护的路由，测试确实会失败。
  - 同文件 `TestConsoleWebSocketRefusesWithoutTicket`、`TestHealthReportsAuthNotLoaded`
  - `api/internal/operatorplane/route_table_test.go` · `TestPlaneWritesRequireOperator`
  - `api/internal/cluster/sync_handler_test.go` · `TestSyncKubeconfigDisabledIsNotSuccess`
  - infra：告警规则已通过 `check_alert_routing.py` 和 `check_http_metrics_coverage.py`
- 门禁：`go build/vet/test ./...` → 0 / 0 / 全部 ok；Console 四项全过（见顶部）。结果：83 条写路由，83 条都有保护。
- 验收：`cd bifrost-platform/api && go test ./internal/server ./internal/operatorplane ./internal/cluster -run 'TestEveryMutatingRouteRequiresARole|TestHealthReportsAuthNotLoaded|TestPlaneWritesRequireOperator|TestSyncKubeconfigDisabledIsNotSuccess' -count=1` → 3 个包 ok；上线后执行 `curl -s -o /dev/null -w '%{http_code}' -X POST <platform>/api/v1/cluster/sync-kubeconfig` → 401
- 要 Owner 批：
  - platform 发版（deliver / release.sh）
  - 合并 infra 分支：monitoring 规则由 Argo 同步，合并后就生效
- 后续：无后续。白名单为空，没有遗留的匿名写路由。

## TD-225
- Claim：成立。
  - `origin/td-l6:mcp/platform/src/focusBridges.ts:88`：focus 拼错（例如 `postgress`）时返回 null，桥会退化成全量工具的 server，并且带着 operator 权限。
  - `mcp/platform/src/platformClient.ts:42`：即使设置了 `PLATFORM_TOKEN_ENV_KEY`，仍然先读 `PLATFORM_OPERATOR_TOKEN`。
  - `.mcp.json` 里三座只读桥（redis / postgres / prometheus）传的也是 operator token。
- 改动：
  - bifrost-platform · `cursor/td-platform` · `7676d6aa414184889dda74d520b7d0ac734a1aea`
    - focus 未知时抛错，进程 `exit 1`
    - 新文件 `tokenResolve.ts`：设置了 pin 时只读 pin 指定的 key
    - `config/cursor-mcp-bridges.json` 中三座只读桥改用 viewer token 加 pin
    - 更新 `mcp/README.md`
  - bifrost-trade-infra · `cursor/td-platform` · `bcd36b42bf82c3eb8ca28ffa12135820585f1164`
    - `agent-config/.mcp.json` 三座只读桥的键改为 `PLATFORM_VIEWER_TOKEN`；值仍是 `${PLATFORM_VIEWER_TOKEN:-}` 引用，没有碰任何真实值
    - 同步更新 README
  - 两边先后哪个落地都兼容。
- 防线：`console/src/lib/architecture/__tests__/mcpFocusBridges.test.ts`，describe「MCP focus bridge (TD-225)」，共 4 个用例：
  - 未知 focus 抛错
  - 空 focus 返回 null（全量 server）
  - 除 kubernetes 外，每个 focus 的工具在 `api/internal/mcp/catalog.go` 里都是 `read` 级
  - 设置了 pin 的桥忽略 operator 和 admin token
- 门禁：vitest 从 117 files / 797 tests 增加到 118 / 801，全部通过；`mcp/platform` 的 `tsc --noEmit` → 0；实跑 `MCP_BRIDGE_FOCUS=postgress node …` → exit 1。
- 验收：`cd bifrost-platform/console && npx vitest run src/lib/architecture/__tests__/mcpFocusBridges.test.ts` → 4 passed
- 要 Owner 批：
  - 合并 infra 分支（`.mcp.json`）
  - 本机 `.env` 或 shell 里需要有 `PLATFORM_VIEWER_TOKEN`，否则这三座桥没有 token，读取会得到 401。这是 Owner 本机的动作，Agent 不碰真实值。
- 后续：Console 的 vitest 已经覆盖 MCP 代码，但 `mcp/platform` 自身没有测试脚本；如果 ci-platform 还没跑 console vitest，需要接成阻断项（见 TD-229 后续）。

## TD-229
- Claim：成立。`origin/td-l6:api/internal/agentgovernance/trust_override_store.go`：
  - `:31`：集群内落到 `$HOME/.bifrost-platform/governance`，这个目录不在任何挂载卷上，Pod 一重启就丢（09-07 Owner 的 L0 授权就是这样丢的）
  - `:34`、`:57`、`:70`：mkdir、读、写的错误全部用 `_ =` 吞掉，读不到时返回空 `{}`，写失败时仍回 200
- 改动：bifrost-platform · `cursor/td-platform` · `315c382c9ede40b2b5b969a5f4470eef9f91eba1`
  - `TrustOverrideStore` 改为接口
  - 集群内（`PLATFORM_GOVERNANCE_NAMESPACE`，或 SA 的 namespace）存到 ConfigMap `platform-trust-overrides` / `overrides.json`，冲突时重试。实现放在新包 `internal/trustoverrides`，是为了遵守 operatorplane 的 cluster-free 分层测试。
  - 集群外的文件 store 按 `GOVERNANCE_DIR` → `PROJECT_ROOT/agent/governance` → `DATA_DIR/governance` → `./data/governance` 的顺序找目录，不再用 HOME
  - 读失败回 503，写失败回 500，响应体都带 `store` 位置
  - Console 的 Governance 页显示「Overrides stored in: …」
  - 不需要新增 RBAC：集群客户端用的是 kubeconfig Secret
  - research 的 `trust_gate.py` 在取数失败时已经按非 L0 处理（fail-safe），不用改
- 防线：
  - `api/internal/agentgovernance/trust_override_store_test.go` · `TestTrustOverridePutWriteFailIsServerError` / `TestTrustOverrideListReadFailIsServiceUnavailable` / `TestTrustOverrideFileReadFailSurfaces` / `TestTrustOverrideFileStoreNeverUsesHome`
  - `api/internal/trustoverrides/configmap_test.go` · `TestTrustOverrideConfigMapRoundTrip` / `TestTrustOverrideConfigMapWriteFailAndReadFail`（fake client 加 reactor）
  - 新防线 platform-store-durability：`api/internal/storedurability/home_paths_test.go` · `TestNoNewStoreUnderHome`。白名单列出 20 个从 HOME 推导路径的文件，每个都写明原因，名单只能减少。其中 7 个是 TD-196 积压的 store。
- 门禁：Go 53 个包 ok（当时）；Console tsc / lint / vitest（118 / 801）/ build 全过。
- 验收：`cd bifrost-platform/api && go test ./internal/agentgovernance ./internal/trustoverrides ./internal/storedurability -count=1` → 3 个包 ok；上线后执行 `GET /api/v1/agent/governance/trust-overrides`，响应里 `store` 应为 `configmap <ns>/platform-trust-overrides`
- 要 Owner 批：
  - platform 发版
  - PROD 发版后重新授予一次 research-loop-batch 的 L0：`PUT /api/v1/agent/governance/trust-overrides/research-loop-batch`。旧授权在 HOME 文件里，不会迁移进 ConfigMap。
- 后续：
  - TD-196 的 7 个 store 仍然落在 HOME（见白名单）
  - 本机 bdev 读到 `{}` 的原因没有追根，现在响应的 `store` 字段会直接显示读的是哪里

## TD-231
- Claim：成立。在 `api/internal` 的非测试 Go 代码里，正则 `NVDA|"ib:|ws_ib_|auto_status|"bifrost-(prod|stg|dev)"` 命中 53 行。例如：
  - `origin/td-l6:api/internal/ibgateway/config.go:21` `tradeCutoverNamespaces`
  - `ibgateway/service.go:78` `ib:ingester:tick:NVDA|STK|||`
  - `ibgateway/service.go:574` `"no sample tick (NVDA)"`
  - `cluster/service_readiness.go:131`、`cluster/postgres_status.go:109-110, 395-397` 各自写死了一份 bifrost-{dev,stg,prod}
- 改动：
  - bifrost-platform · `cursor/td-platform` · `2899d9372030b45627536d954e2647b1d5931127`
    - `config/environments.yaml` 给 dev / stg / prod 加上 `namespace` 和 `database`
    - 新增 `config.AppEnvs()`，作为唯一的环境列表。readiness 的 deployments、IngressRoute、postgres、daemon、redis、applications，Postgres 数据库列表，redis / postgres 内嵌探针，IB cutover 检查，都改为遍历它。
    - 没有声明任何环境时，cutover 返回 unknown，而不是「all retired」
    - IB 样本合约的来源按顺序是：`OPS_IB_SAMPLE_CONTRACT`，然后 `ib-gateway-config` 的 `sample_contract`，最后是 `gateway.yaml` 的第一个 `watchlist_symbols`
    - 响应新增 `sample_contract`；`sample_tick_nvda` 保留原有字段名以兼容旧 Console
    - Console 文案改为显示配置里的合约
  - 命中从 53 行降到 32 行；`grep -c NVDA api/internal/ibgateway/service.go` → 0
  - 显示顺序从 stg / dev / prod 变成文件顺序 dev / stg / prod
  - bifrost-trade-infra · `cursor/td-platform` · `29283193503379f6bd4c1dd4f26d236a4b8c8f4e`：`k8s/overlays/platform-{prod,stg}/config/environments.yaml` 同样加上 `namespace` 和 `database`
- 防线：新防线 platform-trade-vocab：`api/internal/tradevocab/literals_test.go` · `TestTradeVocabularyOnlyShrinks`
  - 按文件给出 Trade 词汇的行数预算，只能下降：超预算、新文件出现、低于预算没下调，都会失败
  - 手工加一行 `"bifrost-prod"`，测试确实失败
  - 另有 `api/internal/config/app_envs_test.go` · `TestShippedEnvironmentsDeclareNamespaces`，保证随仓库发布的配置里有 namespace 和 database
  - `TestAppEnvsKeepFileOrderAndSkipUndeclared`、`cluster` 包的 `TestReadinessProbesCoverNoNamespaceWithoutConfig` / `TestPostgresDatabasesComeFromEnvironments`、`ibgateway` 包的 `TestSampleContractFollowsGatewayConfig`
- 门禁：`go build` 0 · `go vet` 0 · `go test ./...` 54 个包 ok；Console tsc 0 / lint 0 errors / vitest 118 files 801 passed / build 0。
- 验收：`cd bifrost-platform/api && go test ./internal/tradevocab ./internal/config ./internal/cluster ./internal/ibgateway -count=1` → 4 个包 ok；`rg --glob '!*_test.go' -e 'NVDA|"ib:|ws_ib_|auto_status|"bifrost-(prod|stg|dev)"' internal | wc -l` → 32
- 要 Owner 批：
  - **发布顺序**：infra 的 `platform-{prod,stg}/config/environments.yaml` 必须先于或与 platform 发版一起落地（合并 infra 分支，Argo 同步）。否则 `AppEnvs` 为空，readiness、cutover、DB 列表都会是空的（cutover 显示 unknown）。
  - platform 发版
- 后续：剩余 32 行词汇按文件列在预算表里。主要包括：
  - `ibgateway/operator_cmd.go`、`ibgateway/service.go` 的 `ib:` Redis 键
  - `telemetry/queries.go` 的 `allowedNamespaces`：这是 PromQL 注入白名单，改由 cfg 驱动需要改包级函数的签名，本次没有动
  - `delivery/supply_chain.go`、`patrol/autopilot.go` 的 namespace
  - `sample_tick_nvda` 这个 wire 名（需要 Console 和 API 协同改名）
  - 建议另立一条 TD 逐文件清掉

---

## 汇总：要 Owner 批
1. 合并 infra 分支 `cursor/td-platform`（含 monitoring 告警、`.mcp.json`、platform overlays；都由 Argo 同步）。它要先于或与 platform 发版一起落地。
2. platform 分支 `cursor/td-platform` 合并后发版（deliver / release.sh）。
3. PROD 发版后重新 PUT research-loop-batch 的 L0 trust override。
4. 本机提供 `PLATFORM_VIEWER_TOKEN`，三座只读 MCP 桥会用到。
5. 如果 ci-platform 还没把 `api` 的 `go test ./...` 和 console vitest 设为阻断项，需要接上；本 lane 的防线都依赖这两项。

阻塞：无。preflight 没有拦截任何步骤。
