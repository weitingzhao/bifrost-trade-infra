# LANE-E1R — E1 返工：存活告警不呼人、workers 指标接口不探插件

在 `cursor/e1-platform`（`5c4040ee`）与 `cursor/e1-infra`（`247af1be`）上继续（先 rebase 到各自 origin/main）。

## 为什么（Claude Code 验收 E1，2026-10-08）

1. **会误呼 Owner**：`k8s/monitoring/bifrost-maintainer-rules.yaml` 里 `BifrostPostgresBackupRetryStale`、`BifrostPostgresBackupRetryJobFailed`、`BifrostPostgresBackupSweepStale` 的名字匹配呼人路由 `Bifrost(PostgresBackup.*|…)`，`check_alert_routing.py` 的呼人种类从 11 变成 14。其中 Sweep 的 `absent()` 在新镜像上线前就会触发——apply 当晚推到 Owner 手机。ADR §7：维护者存活只记账；真正的备份失败已有现成的呼人告警。
2. **探测量翻倍**：报告写明 workers 的 `/metrics` 每次被抓都顺带探四个插件，而 platform-api 的 ServiceMonitor 已经这样做；TD-256 之后 market-data 新鲜度一次 4–5 秒。
3. Secret 建法把令牌放进了命令行参数（`--from-literal=token="$(…)"`），进程列表里可见。

## 要做

1. 三条规则改名为 `BifrostMaintainer…`（例如 `BifrostMaintainerBackupRetryStale`、`BifrostMaintainerBackupRetryJobFailed`、`BifrostMaintainerBackupSweepStale`），同步 `MAINTAINERS.yaml`（含 `k8s/monitoring/maintainer-reconcile/` 的逐字节副本）的 `detected_by`。`check_alert_routing.py` 加断言：`bifrost-maintainer-rules.yaml` 里的任何告警都**不得**被呼人路由命中；呼人种类回到 11。
2. platform：`PLATFORM_ROLE=workers` 时 `/metrics` 只出进程指标、维护者指标（以及以后 LANE-RP 的发版策略指标），**不触发插件探测**；api 角色不变。测试：workers 角色的 `/metrics` 不调用插件探测（用假探测计数）。
3. 报告里的 Secret 命令改为从标准输入读：`kubectl … get secret … -o jsonpath=… | base64 -d | kubectl -n monitoring create secret generic maintainer-reconcile-auth --from-file=token=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -`。
4. 报告补一条「要 Owner 批」：operator-plane 的新只读端点 `GET /api/v1/agent/launchd` 要在两台 mini 上重新部署 operator-plane 才生效（用已修好的 `deploy_mac_mini.sh`，从干净的 main 检出跑）；没部署前夜间对账会把 launchd 记成未读。

## 门禁与验收

platform `go build ./... && go vet ./... && go test ./...`；infra `make check-maintainers`、`PATH=/usr/bin:$PATH python3 scripts/check_alert_routing.py`（预期 `Watchdog and 11 paged alert kinds`）、`kubectl kustomize k8s/monitoring`。报告写到 `reports/LANE-E1R.md`。不推 main、不发版、不 apply。
