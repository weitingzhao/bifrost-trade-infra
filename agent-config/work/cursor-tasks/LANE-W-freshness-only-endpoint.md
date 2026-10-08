# LANE-W — 给插件加只返回新鲜度的端点（TD-259，market-data 插件 + platform）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不 apply）。报告写到 `cursor-tasks/reports/LANE-W.md`。
分支：`cursor/w-market-data`（bifrost-platform-plugin-market-data）、`cursor/w-platform`（bifrost-platform）。各从 `origin/main` 新开。

## 背景（台账 `### TD-259`）

TD-256（已上 STG）把 platform 的 market-data 新鲜度探测从 `pods/exec` 改成了
`GET /market/coverage/db-summary`。那个端点除了探测要的 29 行 `freshness`，还会算**全库 counts**，实测 DEV 5.46s / PROD 4.35s。
Console 每 30s 拉一次 `/plugins/market-data/status`，该 handler 内联调用这个探测。

不是正确性问题（`proxyTimeout` 60s，platform-api 没设 HTTP `WriteTimeout`，不会被切断），是每 30s 付一次 5 秒和一份用不到的全库统计。

`GET /market/status` 的 `freshness_summary` 只要 0.04s，但它是 `ORDER BY last_run_at DESC LIMIT 20`，少 9 个维度（`financials`、`job_trim`、`ratios`、`sec_filings`、`short_interest`、`short_volume`、`slot:fundamentals-rotate`、`slot:ticker-details`、`stock_daily_unadjusted`），**不等价，不要拿它顶替**。

## 要做

1. **插件**（`cursor/w-market-data`）：加 `GET /market/coverage/freshness`，只返回 `db-summary` 里那份 `freshness` 数组，不算 counts。
   字段与现在逐字一致：`dimension`、`last_run_at`、`rows_written`、`status`（允许为 null，platform 侧按 COALESCE 的老默认补 `''` / `0` / `unknown`）、`updated_at`。按 `dimension` 排序。
   复用 `db-summary` 现有的那段查询，不要另写一份 SQL（两份会漂移）。bump 插件版本，报告里写清。
2. **插件测试**：新端点返回的行集合与 `db-summary` 的 `freshness` **完全相同**（同一套夹具，逐字段比对）。这条是防漂移的关键。
3. **platform**（`cursor/w-platform`）：`api/internal/marketdata/service.go` 的 `probeFreshness` 改打 `/market/coverage/freshness`。
   解析、reachability 规则、verdict 口径**一个都不要改**——`parseFreshnessJSON` 与 `freshnessInfoFromParts` 原样复用。
   扩 `api/internal/marketdata/freshness_http_test.go`：断言探测打的是只返回新鲜度的那个路径（不是 `db-summary`）。
4. **flex-query 不动**。它的 `GET /flex/coverage/freshness` 本来就只返回新鲜度，0.018s。
5. 门禁：插件 `make lint && make test`；platform `cd api && go build ./... && go vet ./... && go test ./...`。退出码分开记录。

## 要先量的

改之前先实测新端点的耗时，和 `db-summary` 并排写进报告（同一网关、同一时间窗、各打 3 次取中位数 —— 共享集群的单次计时有噪声）。没有把 5 秒降下来的话，这道就没有意义，停下写报告。

## 边界

- **不要碰** `api/internal/checklist/`（TD-208 / ops-arch 第 3 阶段归另一个会话）。
- 插件发布链与 platform 不同（Tekton 构建 → registry → `kubectl apply -k`），**本道都不做**，准备好分支写进报告。
- 不推 main、不发版、不 apply。
