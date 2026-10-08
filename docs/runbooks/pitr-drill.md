# 时间点恢复演练（每季度，手工）

把生产 CNPG 集群 `data/bifrost-postgres` 的 Barman 备份恢复到临时集群 `pg-recovery-drill/pg-recovery-drill`，核对 1 级和 2 级表，然后删掉临时集群，留下命名空间和只读 Secret。恢复停在传入的 `targetTime`（`k8s/data/drills/render-cluster.sh` 填进清单）。

这是唯一的演练件。临时集群没有 `backup` 段，也没有 `plugins` 段，用的是只读对象存储凭证，不会往 `s3://bifrost-postgres-backup/` 里写。清单不在 `k8s/data/kustomization.yaml` 里，Argo 不会创建它。

## 规模（2026-10-07 只读测量）

| 项 | 值 |
|---|---|
| `bifrost_golden_source` | 36567004851 字节（约 34 GB） |
| `bifrost_dev` / `bifrost_stg` / `bifrost_prod` | 17 MB / 20 MB / 19 MB |
| 清单里的卷 | 80Gi（约为数据的 2.3 倍，留给 WAL 回放） |
| 最近一次全量备份耗时 | `bifrost-postgres-daily-20261007030000`：03:00:00Z–04:15:50Z，约 76 分钟 |
| `archive_timeout` | 300 秒。演练点最多比线上落后一个归档周期 |

节点根文件系统剩余（kubelet `node.fs.availableBytes`，不是 allocatable ephemeral-storage）：

| 节点 | 池 | 剩余 | 演练 |
|---|---|---|---|
| ubt-k3s-02 | prod-pool，主库 | 133.9 GiB | 避开 |
| ubt-k3s-04 | data-primary，副本 | 160.0 GiB | 避开 |
| ubt-k3s-05 | general | 160.4 GiB | 可以 |
| ubt-k3s-06 | general | 239.8 GiB | 优先 |

2026-10-07 那次实际恢复约 23 分钟（34 GB，全量加 WAL 回放到 18:37:26Z）。按 76 分钟的全量加 WAL 回放来排时间，上限按 3 小时等。核对脚本 15–25 分钟（大头是 `option_snapshot` 约 3.1 GiB、`option_open_interest` 约 1.2 GiB，两边各扫一次）。80Gi 落在 ubt-k3s-06 上之后，该节点大约还剩 160 GiB。

## 节奏

手工，每季度一次：一月、四月、七月、十月的第一个周一。没有 CronJob。下一次是 2027 年 1 月的第一个周一。

全部通过时，`scripts/drills/pitr_verify.sh` 先删再建 ConfigMap `data/pg-recovery-drill-last-pass`，让 `kube_configmap_created` 变成这次通过的时间。内容只有四项：日期、恢复点、表数、耗时。

告警 `BifrostPostgresRecoveryDrillStale`（severity `warning`，记账，不呼人）在下面任一情况成立、并持续 1 小时后响起：

- 这个 ConfigMap 不存在；
- `time() - kube_configmap_created{namespace="data",configmap="pg-recovery-drill-last-pass"}` 大于 100 天（8640000 秒）。

规则在 `k8s/monitoring/bifrost-postgres-recovery-drill-rules.yaml`，不依赖 TD-134 的 WAL 规则。

## 步骤

在 `bifrost-trade-infra` 仓库根目录执行。`KUBECONFIG=~/.kube/bifrost-k3s.yaml`。

### 1. 看磁盘

```bash
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
python3 - <<'PY'
import json, subprocess
for name in ("ubt-k3s-05", "ubt-k3s-06"):
    raw = subprocess.check_output(["kubectl", "get", "--raw", f"/api/v1/nodes/{name}/proxy/stats/summary"], text=True)
    avail = json.loads(raw)["node"]["fs"]["availableBytes"]
    print(f"{name} {avail/1024**3:.1f} GiB free")
PY
```

优先节点至少要有 80Gi 空闲。不够就停，不要改亲和性把卷调度到 ubt-k3s-02 或 ubt-k3s-04。

### 2. 只读凭证

Secret `pg-recovery-drill/minio-backup-readonly` 已经在集群里，不在 git 里。策略只有 `s3:GetObject` 和 `s3:ListBucket`，桶是 `bifrost-postgres-backup`（list 可以，put 是 AccessDenied）。不要复制 `data/minio-backup`，那份能写，写进备份桶会破坏时间点恢复。不要删这个命名空间，Secret 跟它在一起。

```bash
kubectl -n pg-recovery-drill get secret minio-backup-readonly -o jsonpath='{.metadata.name}{"\n"}'
```

应打印 `minio-backup-readonly`。没有就停，不要现造一份写凭证。

### 3. 渲染并创建

不要直接 apply 仓库里的清单：`targetTime` 还是占位符。把目标时间传进去（UTC，`YYYY-MM-DDTHH:MM:SSZ`）。不传则是一小时前。

```bash
bash k8s/data/drills/render-cluster.sh '2026-10-08T15:00:00Z' | kubectl apply -f -
```

确认没有被改成会归档，并且目标时间就是刚才传入的那个：

```bash
kubectl -n pg-recovery-drill get cluster pg-recovery-drill -o jsonpath='{.spec.backup}{"\n"}{.spec.plugins}{"\n"}{.spec.externalClusters[0].barmanObjectStore.serverName}{"\n"}{.spec.bootstrap.recovery.recoveryTarget.targetTime}{"\n"}'
```

前两行应为空，第三行是 `bifrost-postgres`，第四行是传入的 `targetTime`。

### 4. 等恢复完成

```bash
kubectl -n pg-recovery-drill wait --for=condition=Ready cluster/pg-recovery-drill --timeout=180m
```

Ready 之前可以看：

```bash
kubectl -n pg-recovery-drill get cluster,pods,pvc -o wide
kubectl -n pg-recovery-drill describe cluster pg-recovery-drill
```

Pod 应落在 `ubt-k3s-06`（其次 `ubt-k3s-05`）。卷是 80Gi `local-path`。

### 5. 核对

```bash
bash scripts/drills/pitr_verify.sh
```

脚本对演练库和线上库都带 `PGOPTIONS=-c default_transaction_read_only=on`。线上查询走副本，没有副本才走主库。退出码 0 是全部通过，并且已经重建 `data/pg-recovery-drill-last-pass`。退出码 1 是有表对不上、演练库在归档 WAL，或 ConfigMap 没写上。退出码 2 是演练库还没恢复完。

归档防护看的是演练 Cluster 没有 `.spec.backup`、没有 `.spec.plugins`，以及 `archive_command` 不含 `barman`、`s3://` 或桶名。`pg_stat_archiver.archived_count` 不为 0 本身不算失败：没配备份时归档命令空跑也会计数。

恢复点按这个顺序取：环境变量 `PITR_RECOVERY_POINT`、Cluster 的 `targetTime`、Pod 日志里的 `last completed transaction was at log time`，最后才是「postmaster 启动前 7 分钟」的估计。估计时会打出醒目警告，不要把它当成这次演练的结论。

通过规则：这个时间点及之前的行数和最大时间戳必须一致。线上在恢复点之后的新写入只打在表里，不算失败。没有时间列的表（例如 `public.settings`、`journal.source_setting`）行数不一致就算失败。会被 upsert 的表（更新时间列，以及 `raw_market.option_open_interest`，它的 `fetched_at` 会在主键冲突时被改写）改为：总行数一致，且目标时间之后被改写的行数等于线上与演练「时间戳 ≤ 目标」的行数差。

把整段输出贴进下面的记录表。

### 6. 删除集群，留下命名空间

```bash
kubectl -n pg-recovery-drill delete cluster pg-recovery-drill --wait=true
kubectl -n pg-recovery-drill delete pvc -l cnpg.io/cluster=pg-recovery-drill --wait=true
```

不要 `kubectl delete namespace pg-recovery-drill`。只读 Secret 在这个命名空间里，下次演练还要用。

`local-path` 的回收策略是 Delete，PVC 删除后节点上的目录一起走。这两条只碰 `pg-recovery-drill` 里的 Cluster 和它的 PVC，不会动 `data/bifrost-postgres`，也不会动备份桶。

失败的恢复用同一步删除。不要在演练集群上执行 `kubectl cnpg backup`，也不要给它补 `backup` 或 `plugins` 段。

## 记录

| 日期 | 恢复耗时 | 核对 | 节点 | 备注 |
|---|---|---|---|---|
| 2026-10-07 | 约 23 分钟（34 GB，全量 + WAL 回放到 18:37:26Z） | 104/105 PASS；`option_open_interest` 的 125,860 行被目标时间之后 19:30Z 的 upsert 改了 `fetched_at`，两边总行数相同（6,548,559），差数恰为目标后更新的行数，判为通过 | ubt-k3s-06 | 用的就是 `pg-recovery-drill/pg-recovery-drill`（只读凭证 `minio-backup-readonly`，无 backup 段）。核对点 `2026-10-07T18:37:26Z`。这次的三条核对结论已经写进 `scripts/drills/pitr_verify.sh`。 |
