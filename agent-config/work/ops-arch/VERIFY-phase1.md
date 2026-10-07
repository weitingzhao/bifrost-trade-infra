# 第 1 阶段验收（Claude Code，2026-10-07）

| 道 | 结论 | 分支 · SHA | 验收（重跑） | 状态 |
|---|---|---|---|---|
| A1 告警改道 | PASS | infra `cursor/a1-infra` `53b527bb` | `PATH=/usr/bin:$PATH make check-alert-routing` → ok，默认 receiver 为 PROD | **已上线**（Owner 10-07 批）：main 128036e，网络策略 + webhook 令牌 + helm rev 15；`LIVE=1` 通过；PROD 审计出现 `ops-agent.alertmanager` |
| A2 集群状态第二份 | PASS（A2R 返工后） | 已合入 main `f7dcccc` | `make check-cluster-state-backup` → snapshot ciphertext only；`--self-test` ok；快照从 hostPath 直接经 age 写出，NAS 上只有密文 + MANIFEST | 等 Owner 批 apply + 手动触发一次 |
| A3 维护者清单 | PASS | 已合入 main `ebd019d` | `make check-maintainers` ok 45；`--live` drift 0 | 完成 |
| A4 文件进版本控制 | PASS | main `16b9716` | 38 个文件、根上符号链接全部有效；复扫无密钥 / 金额 | 完成（3 个命中金额规则的文件按规矩留在根上） |
| A5 停夜间 LLM / 不依赖笔记本 | PASS | platform `cursor/a5-platform` `894a88f4`；infra `cursor/a5-infra` `8da7b1ed` | 两条 grep 无输出；checklist、agentbridge 测试 ok | **已上线**（Owner 10-07 批）：.50 / .52 夜间任务已卸载（plist 与脚本移到 `~/bifrost-agent/backup/launchd-nightly-20261007/`）；platform 894a88f 发到 STG / PROD；infra 3013bea（Argo 已去掉 GIT_BRIDGE_URL，git-bridge 读 local-only）；STG `AGENT_DEPLOY_*` 已删；清单去掉 3 个退役任务，对账 drift 0 |
| A6 PITR 演练材料 | PASS | 已合入 main `b0a7f2e` | `make check-pitr-drill` ok；`pitr_verify.sh --self-test` ok；清单无 `backup:` | Owner 定 **10-10（周六）** 演练；前提：Owner 在 NAS MinIO 建只读账号（只读备份桶） |
| A7 节点补丁 | PASS（A7R 返工后） | 已合入 main `f737faa` | unittest 12 OK；集群上 dry-run：`order … ubt-k3s-04 ubt-k3s-02`、`primary-node: ubt-k3s-02`、`switchover-before: ubt-k3s-02` | 等 Owner 批：5 台加 `-updates`、升级本机 kubectl-cnpg（1.25.1→1.27）、首次周末滚动重启 |
| A8 部署脚本保留告警中转 | PASS | platform main `4646441`（快进） | 6 个测试 OK；`bash -n` ok；只改部署脚本与测试 | 完成（不进镜像，无需发版） |

## 验收中处理的事故

13:18–14:17（.50 本地时间）.50 告警中转关闭：S1 的 Mac mini 重新部署把 `ALERT_RELAY` 写成 `off`。.52 互看 watchdog 13:23 呼了 Owner。Claude Code 改回 `on` 并重启，心跳恢复、Alertmanager 0 失败。根因修复见 LANE-A8。

## 报告带出的后续（不在第 1 阶段做）

- A1：`k8s/monitoring/bifrost-alerting-rules.yaml:486` 注解仍指向 STG；`RATCHETS.md:34` 的 `LIVE=1` 描述过时；Alertmanager 用 PROD operator 令牌调审计 webhook，第 2 阶段改成专用的告警写入角色。
- A3：32 个维护者没有告警（第 5 阶段补存活信号）；STG platform-workers 里数据克隆调度已武装（默认源是 `bifrost_prod`，调度 ConfigMap 不存在所以没跑），STG 的 patrol `PATROL_MODE` 不是 report（STG 无技能目录）——两者按 ADR 应在 STG 关掉；两处双修复者：Dagster `market_self_heal*` 与 autopilot 对 polygon-worker 的 rollout，Flex 早班入队（Dagster + worker 补队）。
- A5：`config/ops-context.yaml` 与 infra overlay 副本里还有夜间 stream；`driftproposal` 仍发原 autofix scope；mini 上的夜间脚本文件还在（runner `/nightly/run` 能调到）。
- A6：TD-217 另有一份 `k8s/data/recovery-drill/`，两份各要 80Gi，不要同时跑，之后合并成一份。
- A7：ubt-k3s-01（唯一控制面）根盘 83%。
