# LANE-A6R — 恢复演练合成一套 + 核对脚本三处修复 + 演练过期告警（含 TD-258）

仓库：bifrost-trade-infra，分支 `cursor/a6r-infra`（从最新 origin/main 开）。ADR §9：时间点恢复每季度手工演练一次（Owner 10-07）。

## 事实（2026-10-07）

- 现在有两套演练件：
  - D2 / TD-217：`k8s/data/recovery-drill/`（`cluster.yaml`、`render-cluster.sh` 填 `__TARGET_TIME__`、`compare.sh` 只比三张表、`README.md`），命名空间 `pg-recovery-drill`，只读 Secret `minio-backup-readonly`（MinIO 只读用户 `pg-recovery-drill`，保留）。
  - A6：`k8s/data/drills/pitr-drill-cluster.yaml`、`scripts/drills/pitr_verify.sh`（105 张表）、`scripts/check_pitr_drill_manifest.py`、`docs/runbooks/pitr-drill.md`。
- 10-07 的首次演练用的是 D2 的集群 + A6 的核对脚本：恢复 23 分钟，104/105 + 1 条 upsert 已解释，记录在 `docs/runbooks/pitr-drill.md`。
- `pitr_verify.sh` 实跑发现三处问题：
  ① 「已归档计数 ≠ 0 就拒绝」误伤：CNPG 没配备份时归档命令空跑也计数；
  ② 找不到恢复日志就按「启动前 7 分钟」估恢复点，误差大；
  ③ 按时间戳数行，对会被 upsert 的表（`raw_market.option_open_interest`）不成立。
- TD-258：`k8s/monitoring/td-d2-postgres-rules.yaml:43` 的 `BifrostPostgresRecoveryDrillStale` 假设有一个每月的 CronJob（不存在），整份文件已移出 monitoring kustomization（infra `3791768`）；同文件的 WAL 规则 `BifrostPostgresWalDailyHigh` 等 TD-134 有一天数据后再启用。

## 要做

1. **合成一套**，以 A6 为准：
   - 演练集群清单支持传入目标时间（吸收 `render-cluster.sh` 的做法），命名空间与 Secret 沿用 `pg-recovery-drill` / `minio-backup-readonly`（Owner 已建、已验证只读：list 可、put AccessDenied）；
   - 删除 `k8s/data/recovery-drill/`；`docs/runbooks/pitr-drill.md` 成为唯一手册，写清季度节奏；
   - `check_pitr_drill_manifest.py` 跟着新清单更新（仍要求无 `backup` 段、名字不是 `bifrost-postgres`、serverName 指向生产）。
2. **核对脚本三处修复**：
   ① 归档防护改为检查演练 Cluster 没有 `.spec.backup` 与 `.spec.plugins`（归档命令不得含 barman / s3 / 桶名的检查保留）；
   ② 恢复点优先读 `.spec.bootstrap.recovery.recoveryTarget.targetTime`，其次日志，最后才估；估的时候打印醒目警告；
   ③ 会被 upsert 的表（至少 `raw_market.option_open_interest`；其余按「有更新时间列 / 主键冲突更新」识别）改为：总行数一致，且「目标时间之后被改写的行数」等于线上与演练「时间戳 ≤ 目标」的行数差——即 10-07 手工判过的规则，写成代码。
3. **演练过期告警（TD-258）**：
   - `pitr_verify.sh` 全部 PASS 时，重建 ConfigMap `data/pg-recovery-drill-last-pass`（先删后建，让 `kube_configmap_created` 变成这次通过的时间；内容只写日期、恢复点、表数、耗时）；
   - 规则改为：`time() - kube_configmap_created{namespace="data",configmap="pg-recovery-drill-last-pass"} > 100 天`，以及 ConfigMap 不存在（`absent`）也报；severity warning（记账，不呼人），名字保持 `BifrostPostgresRecoveryDrillStale`；
   - 把这条规则移到不依赖 TD-134 的文件里（或拆分），放回 monitoring kustomization；WAL 规则维持现状；
   - 报告给出**补记 10-07 那次 PASS** 的命令（建 ConfigMap；要 Owner 批，因为是集群写）。
4. 防线：`check_pitr_drill_manifest.py` 覆盖新清单；`pitr_verify.sh --self-test` 加三处修复的用例；`check_alert_routing.py` 覆盖这条规则；100 天表达式的自测。

## 门禁与验收

`make check-pitr-drill`、`bash scripts/drills/pitr_verify.sh --self-test`、`make check-alert-routing`、`kubectl kustomize k8s/monitoring`。报告给出验收命令与补记命令。

## 不做

不 apply、不建集群、不改 MinIO、不推 main。
