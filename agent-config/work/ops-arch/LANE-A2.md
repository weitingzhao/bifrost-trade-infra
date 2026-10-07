# LANE-A2 — 集群状态的第二份：etcd 快照 + Secret 加密件每天到 NAS

ADR §9（1 级数据）。仓库：bifrost-trade-infra，分支 `cursor/a2-infra`。

## 事实

- k3s 只有一个 server 节点：`ubt-k3s-01`（192.168.10.73）。etcd 快照每 12 小时一次，**只在本机** `/var/lib/rancher/k3s/server/db/snapshots/`（root 可读，单个约 170 MB）。
- 所有 Secret（数据库密码、各类令牌）与 platform 状态 ConfigMap（`platform-state-*`，TD-196）只存在于 etcd。
- NAS 存储类：`nfs-cold`（`/volume1/k3s-cold`）、`nfs-hot`。参考已有的逻辑备份：`data/logical-backup` CronJob 与 PVC `logical-backup-cold`。
- 加密用 [age](https://age-encryption.org)。**公钥**由 Owner 生成后交给 Claude Code，写进 ConfigMap（公钥不是秘密）；私钥只在 Owner 手里。清单里先用占位 `AGE_RECIPIENT`。

## 要做

1. CronJob（建议 `kube-system`，每天 UTC 05:15，避开 03:00 物理备份与 04:30 逻辑备份）：
   - nodeSelector `ubt-k3s-01` + 控制面 toleration，hostPath 只读挂快照目录，复制**最新一份**快照；
   - 导出全部 Secret 与 `platform-state-*` ConfigMap（YAML），**写盘前**用 age 加密；任何明文不得落盘、不得进日志；
   - 目标：新 PVC（`nfs-cold`，如 `cluster-state-backup`）下按日期分目录；保留每日 30 份、每月 1 份 12 个月；
   - 专用 ServiceAccount，ClusterRole 只给 secrets 与 configmaps 的 get / list；
   - 写完校验：快照文件大小 > 0 且与源一致（sha256），加密件能被 `age` 识别为合法头。
2. 告警 `BifrostClusterStateBackupStale`：用 kube-state-metrics 的 `kube_cronjob_status_last_successful_time`，超过 36 小时报警。放在**新文件** `k8s/monitoring/bifrost-cluster-state-rules.yaml`（不要改 `bifrost-alerting-rules.yaml`，避免和其他道冲突）。呼人路由由 LANE-A1 加。
3. 恢复手册 `docs/runbooks/cluster-state-restore.md`：etcd 快照恢复（k3s `--cluster-reset --cluster-reset-restore-path`）的步骤与风险；Secret 解密后按命名空间选择性恢复。
4. 防线：`scripts/check_cluster_state_backup.py`（`make check-cluster-state-backup`）——静态：CronJob 存在、用 age、目标是 nfs-cold、没有明文落盘的步骤；`--live`：上次成功 < 36 小时、目标目录有当天文件（只读）。

## 不做

不 apply、不创建 Secret、不生成或触碰私钥。

## 验收

- 分支上 `make check-cluster-state-backup` 通过；
- Owner 批准 apply、手动触发一次后：`python3 scripts/check_cluster_state_backup.py --live` 通过。

## 要 Owner 批

apply 的完整命令（含把公钥写进 ConfigMap 的那一步）与手动触发一次的命令。
