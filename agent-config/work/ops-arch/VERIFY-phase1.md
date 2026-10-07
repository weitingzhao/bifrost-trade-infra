# 第 1 阶段验收（Claude Code，2026-10-07）

| 道 | 结论 | 分支 · SHA | 验收（重跑） | 状态 |
|---|---|---|---|---|
| A1 告警改道 | PASS | infra `cursor/a1-infra` `53b527bb` | `PATH=/usr/bin:$PATH make check-alert-routing` → ok，默认 receiver 为 PROD | 等 Owner 批 apply，合并与 apply 同步做 |
| A2 集群状态第二份 | **返工** | infra `cursor/a2-infra` `2e4f4172` | 静态检查通过，但快照明文复制到 NAS（k3s 未开 Secret 静态加密） | 见 `LANE-A2R.md` |
| A3 维护者清单 | PASS | 已合入 main `ebd019d` | `make check-maintainers` ok 45；`--live` drift 0 | 完成 |
| A4 文件进版本控制 | PASS | main `16b9716` | 38 个文件、根上符号链接全部有效；复扫无密钥 / 金额 | 完成（3 个命中金额规则的文件按规矩留在根上） |
| A5 停夜间 LLM / 不依赖笔记本 | PASS | platform `cursor/a5-platform` `894a88f4`；infra `cursor/a5-infra` `8da7b1ed` | 两条 grep 无输出；checklist、agentbridge 测试 ok | 等 Owner 批：卸载、合并（会改集群）、发版、STG `set env` |
| A6 PITR 演练材料 | PASS | 已合入 main `b0a7f2e` | `make check-pitr-drill` ok；`pitr_verify.sh --self-test` ok；清单无 `backup:` | 等 Owner：建只读 MinIO 账号 + 定演练时间 |
| A7 节点补丁 | **返工** | infra `cursor/a7-infra` `d1ec0f3d` | dry-run 与报告一致，但主库写死为 04；实测主库在 02 | 见 `LANE-A7R.md` |
| A8 部署脚本保留告警中转 | 新增 | — | — | 见 `LANE-A8.md` |

## 验收中处理的事故

13:18–14:17（.50 本地时间）.50 告警中转关闭：S1 的 Mac mini 重新部署把 `ALERT_RELAY` 写成 `off`。.52 互看 watchdog 13:23 呼了 Owner。Claude Code 改回 `on` 并重启，心跳恢复、Alertmanager 0 失败。根因修复见 LANE-A8。

## 报告带出的后续（不在第 1 阶段做）

- A1：`k8s/monitoring/bifrost-alerting-rules.yaml:486` 注解仍指向 STG；`RATCHETS.md:34` 的 `LIVE=1` 描述过时；Alertmanager 用 PROD operator 令牌调审计 webhook，第 2 阶段改成专用的告警写入角色。
- A3：32 个维护者没有告警（第 5 阶段补存活信号）；STG platform-workers 里数据克隆调度已武装（默认源是 `bifrost_prod`，调度 ConfigMap 不存在所以没跑），STG 的 patrol `PATROL_MODE` 不是 report（STG 无技能目录）——两者按 ADR 应在 STG 关掉；两处双修复者：Dagster `market_self_heal*` 与 autopilot 对 polygon-worker 的 rollout，Flex 早班入队（Dagster + worker 补队）。
- A5：`config/ops-context.yaml` 与 infra overlay 副本里还有夜间 stream；`driftproposal` 仍发原 autofix scope；mini 上的夜间脚本文件还在（runner `/nightly/run` 能调到）。
- A6：TD-217 另有一份 `k8s/data/recovery-drill/`，两份各要 80Gi，不要同时跑，之后合并成一份。
- A7：ubt-k3s-01（唯一控制面）根盘 83%。
