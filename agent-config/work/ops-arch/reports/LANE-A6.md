## LANE-A6

- Claim：成立。生产集群只有 `data/bifrost-postgres`（2 实例，主在 ubt-k3s-02，副本在 ubt-k3s-04）。`firstRecoverabilityPoint=2026-09-07T03:08:25Z`，最近一次成功全量是 `bifrost-postgres-daily-20261007030000`（03:00:00Z–04:15:50Z）。没有任何 Cluster 做过 `bootstrap.recovery`（`kubectl get cluster.postgresql.cnpg.io -A` 只有这一份）。main 上已有 TD-217 的 `k8s/data/recovery-drill/`（定点约一小时前、只对三张表），注释写明 Prepared, not applied，和本道不是同一份清单。
- 改动：bifrost-trade-infra · `cursor/a6-infra` · `711ad9c0523ebfc0f522e5b993dc0955d007eb90`
- 防线：`scripts/check_pitr_drill_manifest.py`（`make check-pitr-drill`）。演练清单不得出现 `backup:` 键、Cluster 名不得是 `bifrost-postgres`、`bootstrap.recovery` 指向的 `externalClusters.barmanObjectStore.serverName` 必须是 `bifrost-postgres` 且桶是 `s3://bifrost-postgres-backup/`。另外拒绝 `archive_mode=on/always` 和 `archive_command`。脚本自带 `--self-test`（好清单、`spec.backup`、单行 flow 形式的 `backup:`、改成生产名字、改错 serverName）。
- 门禁：infra 没有 `make lint` / `make test`。
  - `make check-pitr-drill` → exit 0，打印 `ok …/k8s/data/drills/pitr-drill-cluster.yaml`
  - `python3 scripts/check_pitr_drill_manifest.py --self-test` → `self-test ok`
  - `bash -n scripts/drills/pitr_verify.sh` → exit 0
  - `bash scripts/drills/pitr_verify.sh --self-test` → `self-test ok`
  - `ruff check scripts/check_pitr_drill_manifest.py` → All checks passed
  - 只读在副本 `bifrost-postgres-3` 上跑了目录 SQL：105 张表（dev/stg/prod 的 public 各 20，GS 45）。`journal.note` 的核对语句返回一行 11 列。`option_snapshot` 的 `EXPLAIN` 能解析（并行扫分区，规划行数约 530 万）。没有 apply、没有建库、没有删除。
- 验收：在该 SHA 上 `make check-pitr-drill`，预期 exit 0 且输出以 `ok ` 开头。`bash scripts/drills/pitr_verify.sh --self-test` 预期 `self-test ok`。`git grep -n 'backup:' k8s/data/drills/pitr-drill-cluster.yaml` 预期没有命中。Owner 批准演练之后：`bash scripts/drills/pitr_verify.sh` 的表全部 PASS，把输出贴进 `docs/runbooks/pitr-drill.md` 的记录表。
- 要 Owner 批：整次演练（apply、等恢复、核对、删除）。预计磁盘：PVC **80Gi**（Golden Source 实测 36567004851 字节 / 约 34 GB，三份 Trade 库 17/20/19 MB，80Gi 约为数据的 2.3 倍）。优先落在 **ubt-k3s-06**（2026-10-07 kubelet 根盘剩余 239.8 GiB，放下 80Gi 后大约还剩 160 GiB）；ubt-k3s-05 剩 160.4 GiB 也可以。不要落在 ubt-k3s-02（133.9 GiB，PROD 主库）或 ubt-k3s-04（160.0 GiB，data 副本）。预计耗时：恢复 **约 2 小时**（最近一次全量备份写入用了约 76 分钟，再加从 04:15Z 到演练开始的 WAL 回放；`archive_timeout` 300 秒），`wait` 上限 **3 小时**。核对 **15–25 分钟**。

```bash
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
cd bifrost-trade-infra   # 用含该 SHA 的检出

# 磁盘（只读）。优先节点至少 80Gi 空闲，否则停。
python3 - <<'PY'
import json, subprocess
for name in ("ubt-k3s-05", "ubt-k3s-06"):
    raw = subprocess.check_output(["kubectl", "get", "--raw", f"/api/v1/nodes/{name}/proxy/stats/summary"], text=True)
    avail = json.loads(raw)["node"]["fs"]["availableBytes"]
    print(f"{name} {avail/1024**3:.1f} GiB free")
PY

# 只读凭证。不要复制 data/minio-backup（那份能写）。
# MinIO 策略只有 s3:GetObject 和 s3:ListBucket，桶 bifrost-postgres-backup。
kubectl create namespace pitr-drill --dry-run=client -o yaml | kubectl apply -f -
kubectl -n pitr-drill create secret generic minio-backup-readonly \
  --from-literal=ACCESS_KEY_ID='<read-only access key>' \
  --from-literal=SECRET_ACCESS_KEY='<read-only secret key>'
kubectl apply -f k8s/data/drills/pitr-drill-cluster.yaml

# 第一行应为空，第二行是 bifrost-postgres。
kubectl -n pitr-drill get cluster bifrost-postgres-pitr-drill \
  -o jsonpath='{.spec.backup}{"\n"}{.spec.externalClusters[0].barmanObjectStore.serverName}{"\n"}'

# 等恢复。预期约 2 小时，上限 3 小时。Pod 应在 ubt-k3s-06（其次 05）。
kubectl -n pitr-drill wait --for=condition=Ready cluster/bifrost-postgres-pitr-drill --timeout=180m

# 核对。预期退出码 0，表里全部 PASS。
bash scripts/drills/pitr_verify.sh

# 删除。只碰 pitr-drill，不动 data/bifrost-postgres，也不动备份桶。
kubectl -n pitr-drill delete cluster bifrost-postgres-pitr-drill --wait=true
kubectl -n pitr-drill delete pvc -l cnpg.io/cluster=bifrost-postgres-pitr-drill --wait=true
kubectl delete namespace pitr-drill
```

- 后续：分支基于开工时的 `origin/main`（`470a14e`），推送时 main 又进了 4 个提交（头 `56a877a`），和本道文件没有交集，rebase 应能干净套上。不要和 TD-217 的 `pg-recovery-drill` 同时跑，两份各要 80Gi。清单不在 `k8s/data/kustomization.yaml` 里，Argo 不会自动创建它。无新的技术债。
