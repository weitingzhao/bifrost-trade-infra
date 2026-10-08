## LANE-E1R

- 返工改了什么：
  - 三条维护者存活告警改名，避开呼人路由 `Bifrost(PostgresBackup.*|…)`：`BifrostMaintainerBackupRetryStale`、`BifrostMaintainerBackupRetryJobFailed`、`BifrostMaintainerBackupSweepStale`。`agent-config/MAINTAINERS.yaml` 与 `k8s/monitoring/maintainer-reconcile/MAINTAINERS.yaml` 的 `detected_by` 同步（两份逐字节相同）。真正的备份失败告警名字没动，仍走现有呼人路由。
  - `scripts/check_alert_routing.py` 增加断言：`k8s/monitoring/bifrost-maintainer-rules.yaml` 里每条告警都不得匹配呼人正则，也不得走到集群外接收者。文件里没有告警则失败。
  - platform：`PLATFORM_ROLE=workers` 时 `/metrics` 只写维护者指标（以后 LANE-RP 的发版策略循环只要调用 `maintainer.Success` 就从这里出去）、`bifrost_platform_auth_loaded` 和 HTTP 进程指标，不调用四个插件探测。`api` 与默认 `all` 仍探测。测试用四支假探测计数：workers 为 0，api 为 4。
  - Secret 不再用 `--from-literal`。`reports/LANE-E1.md` 和 `k8s/monitoring/maintainer-reconcile/cronjob.yaml` 开头的注释改成从标准输入读令牌。
- 分支（先 rebase 到各自 `origin/main`，再提交这次返工）：
  - bifrost-platform · `cursor/e1-platform` · `b291a09b9af1d4bdeff1ccfd50e23e8f4700906c`（rebase 后的 E1 是 `3eceb80`，本返工在其上）
  - bifrost-trade-infra · `cursor/e1-infra` · 本报告提交是分支 tip（rebase 后的 E1 报告是 `d1feabb`）
- 派发 / 审批：没有碰。`internal/checklist` 的派发代码和审批代码都没改。
- 门禁：
  - platform `api/`：`go build ./... && go vet ./... && go test ./...` → exit 0。
  - `make check-maintainers` → `ok 42 maintainers; static; no-alert 15`。
  - `PATH=/usr/bin:$PATH python3 scripts/check_alert_routing.py` → exit 0，`Watchdog and 11 paged alert kinds`。
  - `kubectl kustomize k8s/monitoring` 与 `kubectl kustomize k8s/monitoring/maintainer-reconcile` → exit 0。没有 apply，没有 `--live`。
  - 没有改 `reconcile.py`，没有重跑 `--self-test`。
- platform 钩子：新 worktree 里没有 `.husky/_`，husky 的 pre-commit（会去扫主检出的超长文件）没有执行。没有改主检出，没有改基线，没有 `--no-verify`。`Change-Id` 由 `lineage.sh commit-msg` 在推送前写进这条尚未推送的提交。infra 的 `core.hooksPath` 正常。
- 要 Owner 批（本道没有执行）：

```bash
# 监控清单不在 Argo 里。从含本分支的 bifrost-trade-infra 检出。
kubectl apply -f k8s/monitoring/bifrost-platform-workers.yaml
kubectl apply -f k8s/monitoring/bifrost-maintainer-rules.yaml
kubectl apply -k k8s/monitoring/maintainer-reconcile

# 令牌从标准输入读，不出现在进程参数里。
# 不建这张 Secret 时，任务仍对账集群，并把 launchd 记成未读（算漂移）。
kubectl -n bifrost-platform-prod get secret bifrost-platform-reporter-token \
  -o jsonpath='{.data.PLATFORM_PROD_REPORTER_TOKEN}' | base64 -d \
  | kubectl -n monitoring create secret generic maintainer-reconcile-auth \
    --from-file=token=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
```

operator-plane 的新只读端点 `GET /api/v1/agent/launchd` 要在两台 mini 上重新部署 operator-plane 才生效。用已修好的 `deploy_mac_mini.sh`，从干净的 main 检出跑。没部署前，夜间对账会把 launchd 记成未读。

platform 镜像要先发到 PROD/STG workers，维护者 gauge 才会出现，workers 的 `/metrics` 也才会停止探插件。在那之前，PROD 循环的 `absent()` 以 warning 记账，不再因为名字匹配 `BifrostPostgresBackup*` 而呼人。
- 没做到的：
  - 没有发版、没有 apply、没有写数据库、没有 `release.sh`、没有起 pipeline、没有推 main。
  - `reconcile.py` 自测夹具里仍有字符串 `BifrostPostgresBackupRetryStale`。那是脚本内的样本，不是 PrometheusRule，也不是清单的 `detected_by`。任务书没有要求改它。
- 后续：第 3 阶段合并 `prober.go` 时保留 `maintainer.Success` / `Failure`。不要和 D1 的分支一起推。无新的技术债条目。
