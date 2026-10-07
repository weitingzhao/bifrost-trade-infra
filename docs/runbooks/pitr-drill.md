# 时间点恢复演练（每季度）

把生产 CNPG 集群 `data/bifrost-postgres` 的 Barman 备份恢复到一个临时集群，核对 1 级和 2 级表，然后删掉临时集群。恢复目标是归档 WAL 的最新点（清单里不写 `recoveryTarget`）。

临时集群没有 `backup` 段，用的是只读对象存储凭证，不会往 `s3://bifrost-postgres-backup/` 里写。不要把它和 TD-217 的 `pg-recovery-drill` 同时跑：两份各要一块 80Gi 的 local-path 盘。

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

预计：恢复 **约 2 小时**（按 76 分钟的全量加上从上次备份到演练开始的 WAL 回放），上限按 **3 小时** 等。核对脚本 **15–25 分钟**（大头是 `option_snapshot` 约 3.1 GiB、`option_open_interest` 约 1.2 GiB，两边各扫一次）。80Gi 落在 ubt-k3s-06 上之后，该节点大约还剩 160 GiB。

## 节奏

每季度一次：一月、四月、七月、十月的第一个周一。第一次在 Owner 批准后尽快做。

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

Secret `pitr-drill/minio-backup-readonly` 不在 git 里。策略只有 `s3:GetObject` 和 `s3:ListBucket`，桶是 `bifrost-postgres-backup`。不要复制 `data/minio-backup`，那份能写，写进备份桶会破坏时间点恢复。

```bash
kubectl create namespace pitr-drill --dry-run=client -o yaml | kubectl apply -f -
kubectl -n pitr-drill create secret generic minio-backup-readonly \
  --from-literal=ACCESS_KEY_ID='<read-only access key>' \
  --from-literal=SECRET_ACCESS_KEY='<read-only secret key>'
kubectl apply -f k8s/data/drills/pitr-drill-cluster.yaml
```

Secret 要在 Cluster 之前建好。清单里的 Namespace 再 apply 一次是幂等的。

确认清单没有被改成会归档：

```bash
kubectl -n pitr-drill get cluster bifrost-postgres-pitr-drill -o jsonpath='{.spec.backup}{"\n"}{.spec.externalClusters[0].barmanObjectStore.serverName}{"\n"}'
```

第一行应为空，第二行是 `bifrost-postgres`。

### 3. 等恢复完成

```bash
kubectl -n pitr-drill wait --for=condition=Ready cluster/bifrost-postgres-pitr-drill --timeout=180m
```

Ready 之前可以看：

```bash
kubectl -n pitr-drill get cluster,pods,pvc -o wide
kubectl -n pitr-drill describe cluster bifrost-postgres-pitr-drill
```

Pod 应落在 `ubt-k3s-06`（其次 `ubt-k3s-05`）。卷是 80Gi `local-path`。

### 4. 核对

```bash
bash scripts/drills/pitr_verify.sh
```

脚本对演练库和线上库都带 `PGOPTIONS=-c default_transaction_read_only=on`。线上查询走副本，没有副本才走主库。退出码 0 是全部通过，1 是有表对不上或演练库在归档 WAL，2 是演练库还没恢复完。

通过规则：恢复点取演练 Pod 日志里的 `last completed transaction was at log time`。这个时间点及之前的行数和最大时间戳必须一致。线上在恢复点之后的新写入只打在表里，不算失败。没有时间列的表（例如 `public.settings`、`journal.source_setting`）行数不一致就算失败，因为没法把差额算成恢复之后的写入。只有 `updated_at` 一类列的表，允许「旧行被更新后时间戳越过恢复点」，但消失的行数不能多于恢复点之后被碰过的行数。

把整段输出贴进下面的记录表。

### 5. 删除

```bash
kubectl -n pitr-drill delete cluster bifrost-postgres-pitr-drill --wait=true
kubectl -n pitr-drill delete pvc -l cnpg.io/cluster=bifrost-postgres-pitr-drill --wait=true
kubectl delete namespace pitr-drill
```

`local-path` 的回收策略是 Delete，PVC 删除后节点上的目录一起走。这几条只碰 `pitr-drill`，不会动 `data/bifrost-postgres`，也不会动备份桶。

失败的恢复用同一步删除。不要在演练集群上执行 `kubectl cnpg backup` 或给它补 `backup` 段。

## 记录

| 日期 | 恢复耗时 | 核对 | 节点 | 备注 |
|---|---|---|---|---|
| 2026-10-07 | 约 23 分钟（34 GB，全量 + WAL 回放到 18:37:26Z） | 104/105 PASS；`option_open_interest` 的 125,860 行被目标时间之后 19:30Z 的 upsert 改了 `fetched_at`，两边总行数相同（6,548,559），差数恰为目标后更新的行数，判为通过 | ubt-k3s-06 | 借用 TD-217 的演练库 `pg-recovery-drill/pg-recovery-drill`（只读凭证 `minio-backup-readonly`，无 backup 段）。核对用 `PITR_RECOVERY_POINT=2026-10-07T18:37:26Z`。脚本三处要修，见 `agent-config/work/ops-arch/VERIFY-phase1.md` |
