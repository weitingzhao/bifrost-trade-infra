# LANE-A3 — 维护者清单 v1 + 对账检查

ADR §7。仓库：bifrost-trade-infra，分支 `cursor/a3-infra`。

「维护者」= 会自动运行、会读写系统或数据的程序（定时任务、后台循环、守护进程）。

## 要做

1. `agent-config/MAINTAINERS.yaml`，每个维护者一行，字段：
   `id`、`what`（维护什么，一句话）、`runs_on`（如 `cluster:data/CronJob`、`cluster:research/dagster`、`cluster:bifrost-platform-prod/platform-workers`、`mini:.50/launchd`、`mac-pro:bdev`）、`schedule`、`env`（`prod` / `shared` / `dev-only`）、`max_tier`（ADR §5 的 A–D）、`detected_by`（坏了靠哪条告警发现；没有就写 `none: <原因>`）、`status`（`active` / `retiring`）。
   Dagster 的 schedule 很多，允许一行写成组：`members: [<schedule 名>, …]`。
2. 实测枚举后填写（只读）：
   - 集群：所有 CronJob、CNPG ScheduledBackup；
   - Dagster：在 `research/dagster-webserver` 里查 GraphQL 的 schedules 与 sensors（当前 39 + 2，全开）；
   - platform 后台循环：读 bifrost-platform `origin/main` 的 `api/internal/server/server.go` 里由 `role.RunsWorkers()` 与环境变量门控的循环，再对照 PROD / STG platform-workers 的环境变量判断哪些真在跑；
   - 插件自带调度：flex-query-worker（`config/schedule.yaml`）、market-data 的 worker 与 API 里有没有内部定时器；
   - Mac mini：`launchctl list` 与 `~/Library/LaunchAgents/com.bifrost.*`；
   - Mac Pro：`bdev list`、`~/.claude/scheduled-tasks/*/`（这类标 `dev-only`，列出来，不算生产维护者）。
3. `scripts/check_maintainers.py` + Makefile `check-maintainers`：
   - 静态：字段齐全；`detected_by` 的告警名在仓库的 PrometheusRule 文件里确实存在；
   - `--live`（只读）：拿清单对账实际（kubectl、Dagster GraphQL、ssh 到两台 mini 的 `launchctl list`），**多出或缺少**都列出并退出码 1。
4. 报告里单列：没有 `detected_by` 的维护者、`env` 不是 `prod` 却在动生产数据的维护者、同一件事有两个修复者的（10-07 的疑点：Dagster `market_self_heal*` 与 patrol autopilot 对 massive-polygon 的 rollout）。

## 不做

不改任何维护者本身，不停任何任务；只登记与报告。

## 验收

分支上 `make check-maintainers` 与 `python3 scripts/check_maintainers.py --live` 都通过（0 漂移）。
