# LANE-P2 — 插件新鲜度改走插件 HTTP，不再 exec 进主库（TD-256，platform）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不 apply）。报告写到 `cursor-tasks/reports/LANE-P2.md`。
分支：`cursor/p2-platform`（bifrost-platform，从最新 `origin/main` 新开；main 已含 phase 2 `e6b825b`）。

## 背景（台账 `### TD-256`）

- `api/internal/marketdata/service.go` 的 `probeFreshness`（约 :293–305）和 `api/internal/flexquery/service.go` 的同名函数，
  用 `s.cluster.ExecSQLOnPrimary` 以 postgres 身份 exec 进 `bifrost-postgres` 读 `ops_jobs.ingest_freshness` / `flex_ingest_freshness`。
- TD-204 之后 STG platform 是只读 ServiceAccount，没有 `pods/exec`，这两个探测在 STG 失败；PROD 为了这一条读还留着 data 命名空间的 exec（等同超级用户）。
- 同文件已有走插件 HTTP 的现成路径：`fetchPluginJSON`（`MARKET_DATA_API_URL` 或 K8s service proxy `ProxyGet`，observer 角色已有 `services/proxy`）。注意 :373 的注释：`ProxyGet` 会把 `?` 转义进路径，带查询参数的请求按现有写法处理。

## 要做

1. 先实测两个插件各自有哪个 HTTP 端点能给出同样的新鲜度数据（market-data 与 flex-query 的 API，读 DEV/PROD 只用 GET）。
   把端点、响应形状、和 SQL 版本逐字段对照写进报告。没有等价端点就停下写报告，不要去插件仓库加端点（那是另一道）。
2. 两个 `probeFreshness` 改用插件 HTTP；返回的 `FreshnessInfo` / reachability 语义不变（插件不可达 → unreachable，不是 0 行）。
3. `ExecSQLOnPrimary` 之后只剩 data clone 使用。防线：code-health 指标或 Go 测试——`cluster/data_clone*.go` 以外的 `ExecSQLOnPrimary` 调用点数为 0（基线 2 → 0，只降不升）。
4. infra（另开分支 `cursor/p2-infra`，只推分支）：确认 `k8s/platform-rbac` 生成器里 PROD 的 `pods/exec`（data）除 data clone 外再无用途；若可以收窄，在 `scripts/gen_platform_rbac.py` 改并重生成，`make check-platform-rbac` 的期望同步改。若 data clone 仍要 exec，保持不动并在报告里写明。
5. 门禁：`cd api && go build ./... && go vet ./... && go test ./...`，退出码分开记录。

## 边界（和另一个会话约好的）

- **不要碰** `api/internal/checklist/dispatch.go` 和 `handler.go` 里的派发代码（TD-208 归 ops-arch 第 3 阶段）。若必须改 checklist 包，停下写进报告。
- 不 apply RBAC、不发 platform、不推 main。
