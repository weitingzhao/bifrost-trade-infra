# LANE-A6 — 第一次时间点恢复（PITR）演练：清单、核对脚本、手册

ADR §9。仓库：bifrost-trade-infra，分支 `cursor/a6-infra`。

## 事实

- CNPG 集群 `data/bifrost-postgres`（2 实例），库 `bifrost_dev` / `bifrost_stg` / `bifrost_prod`（各约 20 MB）+ `bifrost_golden_source`（约 34 GB）。
- 物理备份：每天 03:00 全量 + WAL 持续归档到 `s3://bifrost-postgres-backup/`（NAS 上的 MinIO，`http://minio.data.svc.cluster.local:9000`），保留 30 天。**从没做过恢复演练。**
- 1 级数据：Trade 三库的 `public`；GS 的 `journal`、`research`、`ops_feedback`、`raw_broker`。2 级：`raw_market.option_snapshot`、`raw_market.option_open_interest`。
- 节点：`ubt-k3s-04` 是 data-primary，`ubt-k3s-02` 是 PROD 首选；`ubt-k3s-05` / `ubt-k3s-06` 是 general。

## 要做

1. 清单 `k8s/data/drills/pitr-drill-cluster.yaml`：CNPG `Cluster` `bifrost-postgres-pitr-drill`，1 实例，`bootstrap.recovery` 从 `externalClusters` 的 barmanObjectStore（同一桶，`serverName: bifrost-postgres`）恢复到最新。
   - **必须没有 `backup` 段、不归档 WAL**，绝不能往生产备份桶里写；
   - 放在 general 节点（避开 `ubt-k3s-04` 与 `ubt-k3s-02`）；先只读查各节点可用磁盘，存储大小按 GS 实际大小留余量；
   - 资源限制适中，不抢 PROD。
2. 核对脚本 `scripts/drills/pitr_verify.sh`（只读，`PGOPTIONS=-cdefault_transaction_read_only=on`）：对 1 级与 2 级的每张表，比较演练库与线上库的行数和最大时间戳；输出一张表，差异超出「恢复时刻之后的新写入」才算失败。
3. 手册 `docs/runbooks/pitr-drill.md`：apply → 等待恢复完成（预计耗时）→ 核对 → 删除（`kubectl delete cluster` 与 PVC）→ 记录结果（日期、耗时、核对表）。每季度一次。
4. 防线：`scripts/check_pitr_drill_manifest.py`（`make check-pitr-drill`）——演练清单没有 `backup` 段、名字不是 `bifrost-postgres`、recovery 的 serverName 指向生产。防的是以后有人改清单后往生产桶里写。

## 不做

不 apply、不建库、不删任何东西。

## 验收

- 分支上 `make check-pitr-drill` 通过；
- Owner 批准执行演练后：`scripts/drills/pitr_verify.sh` 的核对表全部通过，结果写进手册的记录段。

## 要 Owner 批

apply、核对、删除的完整命令，以及预计占用的磁盘与时长。
