# LANE-A3 报告

## LANE-A3 维护者清单

- 改动：bifrost-trade-infra · `cursor/a3-infra` · `769b78760a1e58b0a0330c4147be471dae0f21f8`
- 防线：`scripts/check_maintainers.py`。静态检查字段齐全，且 `detected_by` 里的告警名必须出现在本仓库的 PrometheusRule 文件里；`--live` 用只读 kubectl、Dagster GraphQL、两台 mini 的 `launchctl list` 加 `com.bifrost.*` plist 对账，多一条或少一条都退出 1。Makefile 只加了一行 `check-maintainers`。
- 门禁：`make check-maintainers` → `ok 45 maintainers; static; no-alert 32`（退出码 0）。`python3 scripts/check_maintainers.py --live` → 同上，再加 `live drift 0 (cronjobs=11 scheduledbackups=1 schedules=39 sensors=2 launchd=10)`（退出码 0）。本仓库没有针对这个脚本的 pytest；这两条就是验收。
- 验收：在分支 `cursor/a3-infra` 上跑
  - `make check-maintainers` → 退出码 0，打印 `ok 45 maintainers; static; no-alert 32`
  - `python3 scripts/check_maintainers.py --live` → 退出码 0，打印 `live drift 0`，括号里是 cronjobs=11、scheduledbackups=1、schedules=39、sensors=2、launchd=10
- 要 Owner 批：没有要本道去改集群、停任务或推 main 的动作。下面两件和书面设计不一致，要不要处理由你定：
  - `.50` 与 `.52` 的 operator-plane `/health` 都是 `autopilot: false`、`alert_relay: false`。AGENT_FACTS 写的是告警中继只开在 `.50`。2026-10-07 实测两边都没开。
  - `.52` 的 `com.bifrost.nightly-drift.plist` 在磁盘上，`launchctl list` 里没有这个 label，所以不会在 03:00 跑。
- 后续：
  - `--live` 只对账 CronJob、CNPG ScheduledBackup、Dagster schedule/sensor、两台 mini 的 launchd。platform 后台循环、插件内部定时器、Mac Pro 的 bdev 和 Claude 定时任务在清单里，但加一个新的不会让 `--live` 失败。
  - PROD platform-workers 上实际在跑的循环：IB 自动 rollout（30 秒，`OPS_IB_AUTOREPAIR_ENABLED=true`）、数据克隆调度（每小时，调度 ConfigMap 不存在，默认关）、失败 Backup 清扫（每天，会删 30 天以上的失败 Backup）、patrol（`PATROL_MODE=report`）、checklist prober（10 分钟）、release recorder（5 分钟）。STG 只启动了后两者里的克隆调度和 patrol；prober、recorder、IB 自动修复、Backup 清扫都没开。STG 的 patrol 没有技能目录，而且 `PATROL_MODE` 没设成 report（默认是动手）。
  - 线程标题同步只在集群外且 workers 角色时跑。两套 platform-workers 都在集群里，这个循环没启动。
  - 盘点时往 dagster-webserver 的 `/tmp` 写过一个 GraphQL 查询文件，随后已删。没有改任何维护者。

计数：条目 45，无告警 32，env 不是 prod 却碰到生产数据 3，两套修复者 2。阻塞：无。

## 没有 detected_by 的维护者（32）

告警名写的是 `none:`，静态检查认这个写法。

- 六个 position-snapshot CronJob（prod / stg / dev 的 capture 与 enrich）。没有一条 PrometheusRule 点名它们。
- `cronjob/data/backup-retry`。备份失败本身有 `BifrostPostgresBackupFailed`，这个重试 CronJob 停了没有自己的规则。
- `cronjob/cicd/tekton-pipelinerun-ttl`。
- 八个 platform 循环（PROD 六个、STG 两个）。ADR §7 要求它们导出上次成功时间；现在没有对应规则。
- `plugin/market-data-api-queue-sampler`。线程死了、进程还在时，`BifrostMarketDataScrapeDown` 不会响。
- 十个 mini launchd（`.50` 五个、`.52` 五个）。
- Mac Pro 五个：本机 platform-api、git-bridge、event-radar-watch、其余 bdev 会话、Claude scheduled-tasks。

有告警的 13 条：逻辑备份、逻辑备份演练、research-harness、CNPG ScheduledBackup、五组 Dagster schedule、一组 sensor、flex worker、两个 polygon worker。

## env 不是 prod，却碰到生产数据（3）

- `mac-pro/bdev/event-radar-watch`（dev-only）。bdev 在跑。丢文件进本机投放目录时，它把内容写进 research 自己的 schema。SEC 8-K 已经改由集群里的 `research_event_radar_schedule` 写，这条只剩本机投放。
- `mac-pro/bdev/git-bridge`（dev-only）。PROD platform-workers 的 `GIT_BRIDGE_URL` 是 `http://192.168.10.40:8785`，`.40` 是这台 Mac。生产控制面在调用它。没有证据表明它写行情库或交易库。
- `mac-pro/claude-scheduled-tasks`（dev-only）。目录在。其中 `ratios-arrival-narrow-cron-2026-09-29` 的说明是收窄 Dagster cron 并发布 Research；`avb-wbs-post-monday-purge-check` 的说明是条件成立就重跑 purge。其余大多写明只读。这些任务现在是否仍被 Claude 触发，本道只看到目录，没有再核调度器。

没有算进去、但是武装着的：`platform/stg/data-clone-scheduler`。循环在 STG workers 里每小时醒一次，调度 ConfigMap 不存在，默认 `enabled: false`，所以今天不复制。默认 source 写的是 `bifrost_prod`。一旦有人在 STG 把调度打开，它会去读生产库。

STG 的 position-snapshot 只写 `bifrost_stg`。DEV 的只写 `bifrost_dev`。

## 同一件事有两个修复者（2）

1. Massive / polygon 不健康时，Dagster `market_self_heal_schedule` 与 `market_self_heal_late_schedule`，和 PROD patrol 的 `massive-polygon`，都是修复者，动作不一样。
   - Dagster 调插件 `POST /market/doctor/heal`，处方是重新入队（enqueue-slot / enqueue / retry-jobs）。Doctor 里「worker 不可达 → rollout-restart polygon-worker-*」标了 `auto_fixable: false`，heal 不会执行 rollout。
   - PROD patrol 对 `massive-polygon` 的代码路径是 rollout restart `plugin-market-data/polygon-worker-stocks`。2026-10-07 `PATROL_MODE=report`，它只记下会做什么，不发请求。
   - 所以今天没有两套 rollout 同时在滚 polygon-worker。report 一关，同一条 feed 上就会同时有「重新入队」和「重启 stocks worker」。
2. Flex 早班入队有两个写入者。Dagster `research_flex_morning_schedule`（06:30 America/New_York，周一到周六）入队；flex-query-worker 在宽限时间过后用 `config/schedule.yaml` 的同一组 slot（flex-trades、flex-transactions）再补一次。补队是故意的后手，按 ADR「一件事一个修复者」它仍是第二个写入者。

不算第二套 autopilot：两台 mini 的 operator-plane 健康检查都是 `autopilot: false`。PROD workers 里那一个 patrol 是唯一在扫技能的。`.50` 的 runner 是 primary，`.52` 是 standby，这是一对，不是两套同职修复。

## 清单规模（便于对账）

45 条 = CronJob 11 + ScheduledBackup 1 + Dagster 组 6（schedule 成员 39，sensor 成员 2，全部 RUNNING）+ platform 循环 8 + 插件 4 + launchd 10 + Mac Pro 5。
