# LANE-E1 — 第 5 阶段（一）：维护者存活信号 + 每晚集群内对账

ADR §7。仓库：bifrost-platform（分支 `cursor/e1-platform`）、bifrost-trade-infra（分支 `cursor/e1-infra`），从最新 origin/main 开。

## 事实（2026-10-08 实测）

- Prometheus 只抓 **platform-api**（ServiceMonitor `monitoring/bifrost-platform-api`；`up` 里只有 STG / PROD 的 platform-api Pod）。**platform-workers 没有被抓**，而所有后台循环都跑在 workers 里：IB 自动修复、数据克隆调度、失败 Backup 清扫、patrol autopilot、检查探测器、发布记录、（即将合入的）发版策略到期检查 `release_policy_expiry_check`（指标 `bifrost_release_policy_expires_in_seconds`、`bifrost_release_policy_reminders_sent_total`）。
- `agent-config/MAINTAINERS.yaml` 42 个维护者，其中 29 个 `detected_by: none:…`。`scripts/check_maintainers.py --live` 现在只能在 Owner 笔记本上手动跑（读 kubectl、Dagster GraphQL、ssh 到两台 mini）。

## 要做

1. **workers 进监控（infra）**：为 STG / PROD 的 platform-workers 加 PodMonitor（或给 workers 加一个 metrics Service + ServiceMonitor），让 `up{pod=~"platform-workers.*"}` 出现。`kubectl kustomize` 渲染验证；报告给出 apply 命令（监控清单不归 Argo，手工 apply，要 Owner 批）。
2. **后台循环存活指标（platform）**：统一导出 `bifrost_maintainer_last_success_timestamp_seconds{maintainer="<MAINTAINERS.yaml 的 id>"}` 与 `bifrost_maintainer_runs_total{maintainer, result}`，覆盖 workers 里所有后台循环（含 patrol 每个技能、检查探测器、IB 自动修复、Backup 清扫、数据克隆调度、发布记录、发版策略检查）。用一个小的共享辅助（例如 `internal/maintainer`），各循环成功一次调用一次。测试：每个循环都注册了这个指标（遍历启动清单）。
3. **告警（infra）**：给 `MAINTAINERS.yaml` 里现在 `none` 的维护者补 `detected_by`，能补的都补：
   - platform 循环：`time() - bifrost_maintainer_last_success_timestamp_seconds > 2 × 周期`（按各自周期），外加 `absent`；
   - CronJob（position-snapshot ×6、backup-retry、tekton-pipelinerun-ttl）：用 kube-state-metrics 的 `kube_cronjob_status_last_successful_time` 与 `kube_job_status_failed`；
   - mini 的 launchd 服务：已有互看 watchdog 的就写它；没有的写清原因；
   - Mac Pro（`dev-only`）：保持 `none`，写明「开发机，不是生产维护者」。
   新规则放新文件 `k8s/monitoring/bifrost-maintainer-rules.yaml`，severity 一律 warning（记账，进 PROD 平台），备份类沿用现有呼人路由。同步 `MAINTAINERS.yaml` 的 `detected_by`，`make check-maintainers` 的静态检查（告警名必须存在）要过。
4. **每晚集群内对账（infra）**：把 `check_maintainers.py --live` 的集群部分（CronJob、ScheduledBackup、Dagster schedule / sensor、platform 循环——后者改读新指标）做成 PROD 里的 CronJob（建议 `cicd` 或 `monitoring`，只读 ServiceAccount，每天 UTC 07:00），结果导出为指标（例如推到 Pushgateway 若已有；没有就写 ConfigMap 并由 kube-state-metrics 暴露其创建时间，参照 TD-258 的做法），漂移 > 0 就告警（warning）。mini 的 launchd 部分在集群里做不到——改为向 .50 / .52 的 operator-plane 读一个只读清单：如需在 operator-plane 加 `GET /api/v1/agent/launchd`（只列 `com.bifrost.*` 的 label 与状态，viewer 级），一并做在 platform 分支。
5. 报告列出：仍无法有存活信号的维护者与原因。

## 门禁与验收

platform：`go build ./... && go vet ./... && go test ./...`；infra：`make check-maintainers`、`kubectl kustomize k8s/monitoring`、新 CronJob 的渲染、`check_alert_routing.py`（新规则走记账路由）。报告给出 apply 命令（PodMonitor、规则、CronJob 与其 RBAC），**不执行**。

## 不做

不改 `internal/checklist` 的派发代码（第 3 阶段在改）、不改审批代码（LANE-RP 在改）、不推 main、不发版、不 apply。与第 3 阶段在 `prober.go` 可能有小冲突（第 3 阶段改 argo-apps 信号），合并由 Claude Code 处理。
