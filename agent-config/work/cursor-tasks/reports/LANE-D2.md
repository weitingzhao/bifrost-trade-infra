# LANE-D2 报告（准备，未执行）

日期 2026-10-07。本道只把 SQL / 清单 / 脚本推到分支。没有 kubectl apply / delete、没有数据库写入、没有 DDL 执行、没有改 `TECH_DEBT.md` / `RATCHETS.md`、没有 deliver。

只读查询用的是 `data` 命名空间副本 `bifrost-postgres-3`，`PGOPTIONS='-c default_transaction_read_only=on'`。主库对照用 `bifrost-postgres-1`。

并行道文件碰撞：

- `docs/DATABASE.md`：LANE-T 的 `/tmp/cursor-t-bifrost-trade-core` 已改这一文件（changelog 加了 0.58.0 一行）。本道写好的两句注记**没有提交**，原文在 TD-148。
- `accounts.py`、core / flex 的 `pyproject.toml`、flex 的 `orchestration/transactions.py`：LANE-T 在改。本道没碰。TD-103 的 writer `ON CONFLICT` 因此留在脚本注释里。
- 提交前再看过 `/tmp/cursor-r2-md`（空）、`/tmp/cursor-s2-bifrost-trade-infra`（当时 worktree 已不在）。`wave8_migrations.py`、`schema/ddl.py`、`k8s/data/cluster.yaml`、`k8s/monitoring/kustomization.yaml` 都没有被别的道占住。
- `k8s/monitoring/bifrost-alerting-rules.yaml` 仍提到 data-warehouse / minio。LANE-P 已在别的分支改过这个文件，本道没动它。新规则在单独的 `td-d2-postgres-rules.yaml`。

## DROP / TRUNCATE 扫描

对本道新建的每个 DDL / SQL 文件跑了 `grep -niE 'drop|truncate'`。没有 `TRUNCATE`。命中如下（TD-160 的两条 `DROP INDEX` 是预期的）：

| 文件 | 行 | 内容 |
|---|---|---|
| `bifrost-research/scripts/oneoff/2026-10-07-td160-drop-event-radar-dup-indexes.sql` | 2、10、13 | 注释里的 drop（第 10 行写明不要 drop `event_radar_pkey`） |
| 同上 | 15–16 | `DROP INDEX CONCURRENTLY`：`features.event_radar_batch_collected`、`features.event_radar_importance`（预期） |
| `…/2026-10-07-td160-event-radar-index-check.sql` | 1 | 注释 “before the DROP”。文件本身是只读 SELECT |
| `…/2026-10-07-td160-drop-event-radar-dup-indexes-rollback.sql` | 无 | 回滚是 `CREATE INDEX CONCURRENTLY` |
| `bifrost-platform-plugin-market-data/scripts/ddl/2026-10-07-td107-period-date-symbol.sql` | 无 | 只有 `CREATE INDEX CONCURRENTLY` |
| `…/2026-10-07-td107-period-date-symbol-rollback.sql` | 6–11 | 六条 `DROP INDEX CONCURRENTLY`（回滚） |
| `bifrost-trade-core/scripts/db/2026-10-07-td148-strategy-plan-source-kind.sql` | 18 | `DROP CONSTRAINT strategy_plan_source_kind_check`（放宽 CHECK 必须先丢掉旧约束，不是 TRUNCATE） |
| `…/2026-10-07-td148-strategy-plan-source-kind-rollback.sql` | 18 | 同上，收回到五个值 |
| `…/2026-10-07-td103-flex-transaction-id.sql` | 无 | 只读 SELECT；UPDATE 和建索引在注释里 |
| `…/2026-10-07-td103-flex-transaction-id-apply.sql` | 无 | 只有 UPDATE |
| `…/2026-10-07-td103-flex-transaction-id-index.sql` | 无 | `CREATE UNIQUE INDEX CONCURRENTLY` |
| `…/2026-10-07-td103-flex-transaction-id-index-rollback.sql` | 4 | `DROP INDEX CONCURRENTLY`（回滚索引，不清列） |
| `bifrost-research/scripts/oneoff/2026-10-07-td142-td172-scope.sql` | 无 | 只读 SELECT |

## TD-134

- Claim：成立。2026-10-07 在主库 `SHOW`：`checkpoint_timeout=5min`，`max_wal_size=1GB`，`wal_compression=off`。origin/main 的 `k8s/data/cluster.yaml` 参数段没有这三项。主库 pod `bifrost-postgres-1` 的 `sum(increase(cnpg_collector_wal_bytes[7d]))/7` = 18.01 GiB/天（台账 19.48 是前一天的七日均值）。副本 `bifrost-postgres-3` 的 1 日增量为 0。这三项在 PostgreSQL 17 都是 SIGHUP，reload 即可。
- 改动：bifrost-trade-infra · `cursor/d2-infra` · `c0e5d13f928101796fbf628b0ff7b34c7ff88e9c`。`k8s/data/cluster.yaml` 加上 `checkpoint_timeout: 15min`、`max_wal_size: 4GB`、`wal_compression: lz4`。告警在 `k8s/monitoring/td-d2-postgres-rules.yaml`（`BifrostPostgresWalDailyHigh`，主库 1 日 WAL > 12884901888 字节即 12 GiB，持续 2h）。**没有 apply。**
- 防线：告警规则文件本身。现在不能 apply：当前日均约 18 GiB，规则一上去就会响。写成「参数进清单 + 告警等满一天再挂」是因为没有能在 CI 里 `SHOW` 集群参数的测试。
- 门禁：infra 没有对应的 Python 套件。`bash -n` 三个新脚本退出码 0；`scripts/check-no-k8s-secrets.sh` 退出码 0（`PASS`）；PyYAML `safe_load` 新清单退出码 0。
- 验收：`git grep -n 'checkpoint_timeout: 15min' origin/cursor/d2-infra -- k8s/data/cluster.yaml` 有一行。apply 之后在主库 `SHOW` 三值分别为 `15min`、`4GB`、`lz4`。
- 要 Owner 批：把 `k8s/data/cluster.yaml` 的参数变更应用到 `data/bifrost-postgres`（这是生产 Cluster）。告警文件等参数生效满一天再 apply。
- 后续：`k8s/overlays/platform-stg/config/clusters.yaml`、`k8s/overlays/platform-prod/config/clusters.yaml`、`bifrost-platform/config/clusters.yaml` 仍把 `data-warehouse` 列在命名空间里（与 TD-237 一起，本道没改 Argo 会同步的 overlay）。

### Owner 执行步骤

1. 合并 `cursor/d2-infra` 之后，按现有 CNPG 发布方式应用 `k8s/data/cluster.yaml`（本道不代跑）。CNPG 对这三项是 reload。
2. 预期（只读）：

```bash
KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-1 -c postgres -- \
  env PGOPTIONS='-c default_transaction_read_only=on' \
  psql -U postgres -d postgres -X -At \
  -c "SHOW checkpoint_timeout; SHOW max_wal_size; SHOW wal_compression;"
```

输出三行：`15min`、`4GB`、`lz4`。

3. 观察一周。每天记一次：

```promql
sum(increase(cnpg_collector_wal_bytes{pod="bifrost-postgres-1"}[1d]))
```

预期降到台账 19.48 GiB 的一半附近（约 9.74 GiB/天）或更低。12 GiB 是告警线，高于预算、低于改前的量。

4. 满一个完整日、且上面的值低于 12 GiB 之后，再 `kubectl apply -f k8s/monitoring/td-d2-postgres-rules.yaml`。同一小时挂上会按改前的量告警。这个文件里还有 TD-217 的演练告警，见该项：演练成功之前不要挂。
5. 回滚：从 `cluster.yaml` 去掉这三行再应用，回到默认 `5min` / `1GB` / `off`。不要为了回滚去重启 pod，除非 CNPG 自己滚动。

## TD-217

- Claim：成立。2026-10-07 只读：Cluster `data/bifrost-postgres` phase healthy，instances 2，镜像 `ghcr.io/cloudnative-pg/postgresql:17.9`，对象存储 `http://minio.data.svc.cluster.local:9000`，目标 `s3://bifrost-postgres-backup/`，`serverName` 空（默认就是集群名 `bifrost-postgres`），WAL 和 data 压缩 gzip。`firstRecoverabilityPoint=2026-09-07T03:08:25Z`（台账写的 2026-09-06，以实测为准）。`lastSuccessfulBackup=2026-10-07T04:15:50Z`。主库 pod 在 `ubt-k3s-02`（prod-pool），副本在 `ubt-k3s-04`（data-primary）。PVC 各 30Gi。库大小：`bifrost_golden_source` 34 GB，stg 20 MB，prod 19 MB，dev 17 MB。`general` 池是 `ubt-k3s-05` / `06`。节点 allocatable ephemeral 约 442 GiB，那不是空闲磁盘，apply 前必须 `df -h`。
- 改动：同一 infra 提交 `c0e5d13f928101796fbf628b0ff7b34c7ff88e9c`。`k8s/data/recovery-drill/`：Namespace `pg-recovery-drill`、1 实例 Cluster、`render-cluster.sh`（macOS `date -u -v-1H` 填 `__TARGET_TIME__`）、`compare.sh`（只读，三张表按时间戳 ≤ targetTime 对行数）、`README.md`。没有 `spec.backup`，避免演练集群往同一桶归档。凭证是 Owner 在集群里建的 Secret `minio-backup-readonly`（`s3:GetObject` + `ListBucket`），不进 git，也不复制 `data/minio-backup`（那是写凭证，写一次可以毁掉 PITR）。
- 防线：`compare.sh` 退出码 0 表示三行输出一致，1 表示不一致，2 表示演练 pod 不是 Running。告警 `BifrostPostgresRecoveryDrillStale`（35 天 / 3024000 秒，或 `absent()`）。**没有 CronJob**：一个会创建 80Gi Cluster 的 CronJob 要单独审 RBAC，不在本道交付里。告警在 CronJob 从未成功时会立刻响，所以现在不能 apply。已有的 `logical-backup-drill` 是另一件事（emptyDir，不是 Barman）。
- 门禁：同 TD-134。`render-cluster.sh` 试跑把 targetTime 收成一小时前的 UTC 时间，注释里的占位符没有被 sed 改掉。
- 验收：`bash k8s/data/recovery-drill/render-cluster.sh` 的 stdout 里 `targetTime` 是 `YYYY-MM-DDTHH:MM:SSZ`，且晚于 `2026-09-07T03:08:25Z`；`serverName: bifrost-postgres`；没有 `backup:` 段。
- 要 Owner 批：建只读 Secret、apply Namespace 和渲染后的 Cluster、演练完删除。80Gi local-path 只放 `bifrost.io/workload-pool=general`，不要放到 prod-pool 或 data-primary。
- 后续：无后续。演练是手工的，告警要等第一次成功（或 Owner 接受立刻告警）再挂。

### Owner 执行步骤

按 `k8s/data/recovery-drill/README.md`：

1. 在将要落盘的节点（`ubt-k3s-05` 或 `06`）上 `df -h`，空闲至少 80 GiB。
2. 在 `pg-recovery-drill` 建 Secret `minio-backup-readonly`，键 `ACCESS_KEY_ID`、`SECRET_ACCESS_KEY`。策略只有 `s3:GetObject` 和 `s3:ListBucket`，桶 `bifrost-postgres-backup`。不要复制 `data/minio-backup`。
3. `kubectl apply -f k8s/data/recovery-drill/namespace.yaml`
4. `bash k8s/data/recovery-drill/render-cluster.sh | kubectl apply -f -`。预期 Cluster `Healthy`、一个 pod `Running`。约 34 GB 加 WAL 回放，用 `kubectl -n pg-recovery-drill describe cluster pg-recovery-drill` 看。
5. `bash k8s/data/recovery-drill/compare.sh <同一个 targetTime>`。预期 `PASS`，`stock_daily`、`atm_iv`、`transactions` 三行与主库一致。这是追加型时间戳的近似，不是可变行的真正 AS OF。
6. 记下成功时间。`td-d2-postgres-rules.yaml` 等这次成功之后再 apply，否则 `absent()` 立刻告警。

清理（失败的演练用同一套）：

```bash
kubectl -n pg-recovery-drill delete cluster pg-recovery-drill
kubectl delete ns pg-recovery-drill
```

预期：Cluster、pod、PVC、只读 Secret 都没了。local-path 回收策略是 Delete，卷跟着 PVC 走。不碰 `data/bifrost-postgres`，也不写备份桶（Secret 只读且演练 Cluster 没有 backup 段）。

## TD-237

- Claim：成立。只读 `kubectl get`（没有读 Secret 的值）：
  - Namespace `data-warehouse` Active，创建于 2026-06-19T09:13:12Z。
  - `deploy/minio` 0/0，镜像 `minio/minio:RELEASE.2024-12-18T13-15-44Z`，109 天。`rs/minio-87ff6fbf7` 副本 0。
  - `svc/minio` ClusterIP 10.43.240.36，端口 9000/9001。
  - `pvc/minio-data` Pending，local-path，109 天。
  - `secret/minio-root` Opaque，2 个键，109 天。值没有打印。git 里原来的清单有占位口令，删除即从树里消失，报告不复述。
  - 还有 `cm/kube-root-ca.crt`、`sa/default`。
  - 台账点名、但不在 `k8s/compute/warehouse` 里的：`data/svc/np-redis-fresh` ClusterIP 10.43.35.102，创建于 2026-06-30，endpoints 为空。两个 Released PV：`pvc-5e40cfd0-72f8-49f1-a013-c2c57cd3ab62`（2026-10-05，default/test-nfs-hot，nfs-hot，1Gi）、`pvc-9135d1fc-7a6f-4d3f-ad77-69efc2ddf331`（2026-06-20，同样）。
- 改动：同一 infra 提交。删了 `k8s/compute/warehouse/minio.yaml` 和 `minio-pvc.yaml`，从 `k8s/compute/kustomization.yaml` 去掉这两行，从 `k8s/compute/namespaces.yaml` 去掉 `data-warehouse` Namespace。`scripts/k3s/gpu-workload.sh` 的 `warehouse-up|warehouse-down` 改为打印拒绝并退出 1；`install-compute-stack.sh` 不再安装或宣传它。`Makefile` 的 `gpu-warehouse-*` 仍调用该脚本，所以也会失败。
- AGENT_FACTS：parity-id `agent-facts-v8` → `agent-facts-v9`。origin/main 上命名空间名单原来在第 202 行，含 `data-warehouse`；「第二个 MinIO」那句在 origin/main 已经删掉（LANE-G）。本道把名单改成第 201–204 行：活动命名空间不再包含 `data-warehouse`，括号写明清单已删、集群里的 namespace 等 Owner 删。第 207 行和第 364 行从「待删」改成「清单已删，namespace 等 Owner 删」。worktree 里没有别的文件钉 `agent-facts-v8`。共享 checkout 的 `AGENT_FACTS.md` 是旧的，本道没有改它。
- 防线：`scripts/check-no-k8s-secrets.sh`（`git grep -l '^kind: Secret' -- k8s ':!*.example.yaml' ':!*.example'`，本分支退出码 0）。`gpu-warehouse-up` 退出 1，避免有人把已删的 Deployment 再拉起来。
- 门禁：同 TD-134。秘密检查在删除 minio Secret 清单之后是 PASS。
- 验收：`git grep -n 'kind: Namespace' origin/cursor/d2-infra -- k8s/compute/namespaces.yaml` 没有 `data-warehouse`；`git grep -l '^kind: Secret' origin/cursor/d2-infra -- k8s ':!*.example.yaml' ':!*.example'` 无输出。
- 要 Owner 批：删除集群里的 namespace 和两个 Released PV、以及 `np-redis-fresh`。git 回滚是 revert 这个分支；活对象删了不要重建（Deployment 一直是 0/0，PVC 一直 Pending，重建会把占位口令再放进清单）。
- 后续：三个 clusters.yaml 仍列出 `data-warehouse`（见 TD-134）。`bifrost-alerting-rules.yaml` 仍提到 data-warehouse/minio，留给已经改过该文件的道，或合并后再单开一条。

### Owner 执行步骤

分支合并进会同步的路径之后，并且 Owner 明确要删活对象时：

```bash
kubectl delete deploy,svc -n data-warehouse minio
kubectl delete pvc -n data-warehouse minio-data
kubectl delete secret -n data-warehouse minio-root
kubectl delete ns data-warehouse
```

可选：`kubectl -n data delete svc np-redis-fresh`，以及按上面两个 PV 名字删除 Released 卷。

预期：`kubectl get ns data-warehouse` 报 NotFound。`gpu-warehouse-up` 退出码 1。

回滚 git：revert `c0e5d13f`。不要用旧清单把 MinIO 建回来。

## TD-103

- Claim：成立。origin/main 的 `flex_client.py` 只通过子元素读 `transactionID`，别的字段有 attribute 回退，这个没有。没有日期的行用 `datetime.now()`。只读 GS `raw_broker.transactions`（2026-10-07，副本）：rows=171，id_null=171，raw 里 transactionID 在的 171，would_fill=171，still_null=0，重复 `(account_id, id)` 组=0。台账写 121 行，行数长了，但「列全 NULL、raw 里有 id」仍然成立。唯一键仍是 `(account_id, ts, amount, type, report_date)`。
- 改动：
  - bifrost-platform-plugin-flex-query · `cursor/d2-flex` · `36fa1d93a81adeee6755b1edd0193cf2bf236d11`。`flex_client.py` 在子元素为空时读 `transactionID` / `TransactionID` 属性（约第 337–341 行）。没有可解析日期的行跳过并记 warning（约第 377、431 行），不再写成 `now()`。公开函数签名没变，没有 bump 0.12.0（LANE-T 占着 flex 的 `pyproject.toml`）。
  - bifrost-trade-core · `cursor/d2-core` · `c55d591465f858ab349b33a29fe5d804b5d8125f`。四个 SQL：dry-run、UPDATE、部分唯一索引、索引回滚。索引名 `transactions_account_flex_tx_uidx`，`(account_id, flex_transaction_id) WHERE flex_transaction_id IS NOT NULL`，`CONCURRENTLY`，不能放进事务（不要 `psql -1`）。
- 防线：`tests/test_cash_transaction_id.py::test_attribute_transaction_id_is_kept_and_dateless_rows_are_skipped`（夹具账户 `U00011111`，编造）。`tests/test_cash_parser.py::test_attribute_transaction_id_is_kept` 去掉了 strict xfail（注释写明修复落地后拿掉）。core `tests/test_td148_source_kind_prepare.py::test_td103_index_is_concurrent_and_partial` 锁住 CONCURRENTLY、部分谓词、以及 dry-run 里有 `would_fill` / `duplicate_id_groups`。
- 门禁：flex `make lint` 退出码 0；`make test` 退出码 0，159 passed，3 deselected。core `make lint` 退出码 0；`PYTHONPATH=/tmp/cursor-d2-core/src make test` 退出码 0，13462 passed，2 skipped，111 deselected，2 xfailed，2 xpassed。不设 PYTHONPATH 时 core 的 venv 可编辑安装指向共享 checkout，收集阶段 20 个 ImportError（共享树落后于 origin/main），那不是这个分支的失败。
- 验收：`PYTHONPATH=src pytest -q tests/test_cash_parser.py::test_attribute_transaction_id_is_kept tests/test_cash_transaction_id.py` → 2 passed。dry-run SELECT 的 `duplicate_id_groups` 为 0。
- 要 Owner 批：GS 上的 UPDATE。**不要**在 writer 改完之前建唯一索引。`upsert_account_transactions` 仍冲突在旧键；索引先建的话，同一 id 的第二次插入会报错而不是更新。writer 在 `accounts.py`，LANE-T 的 `cursor/t-core` 正在改这个文件，本道停在该文件上。
- 后续：writer 的 `ON CONFLICT` 要等 LANE-T 合并后再做，并随之 bump core（公开接口）。在那之前不要执行索引 SQL。

### Owner 执行步骤

1. 先发 flex 分支，让新行带上 id。
2. 再跑 dry-run（文件里的 SELECT，只读）。`duplicate_id_groups` 不是 0，或 `would_fill` 和预期差一截，就停。2026-10-07 是 171 / 171 / 0 组重复。
3. 对 `bifrost_golden_source` 跑 `scripts/db/2026-10-07-td103-flex-transaction-id-apply.sql`（只有 UPDATE）。不要和索引放在同一次 `psql -1`。预期：raw 里有 transactionID 的行，`flex_transaction_id` 不再是 NULL。
4. 等 `accounts.py` 把有 id 的行改到这个部分唯一索引上，没 id 的行仍用旧键。然后单独跑 `…-index.sql`（不要 `-1`）。
5. 回滚索引：`…-index-rollback.sql`（`DROP INDEX CONCURRENTLY`）。回滚文件不清列。若要撤回回填，把 `flex_transaction_id` 等于 `raw_extra->>'transactionID'` 的行设回 NULL；本道没有准备这条 UPDATE。

## TD-107

- Claim：成立。`migrate_stock_financials_split` 在 `stock_financials` 的 relkind 为 `v` 时直接 return（`wave8_migrations.py:184`），已部署环境都是 view，所以 `create_financials_entity_tables` 里的索引不会再建。只读 GS `pg_indexes`：六张表（income_statement、balance_sheet、cash_flow、ratios、short_interest、short_volume）只有主键和 `*_filing_date`，外加 short_volume 上已有的 `short_volume_period_date_symbol`。没有 `symbol_period_date`。代码里声明过、库里没有的那 11 个索引与台账一致。`symbol_period_date` 的前缀就是主键 `(symbol, period_date, period_type)`，是多余的。
- 改动：bifrost-platform-plugin-market-data · `cursor/d2-md` · `2eca12f0c300a12bb38550219f5277c5bdf9e593`。从 `create_financials_entity_tables` 去掉两个 CREATE INDEX。新函数 `ensure_financials_period_date_symbol`（`wave8_migrations.py:76`）对六张表 `CREATE INDEX IF NOT EXISTS {table}_period_date_symbol (period_date, symbol)`。`apply_ddl` 在 `migrate_stock_financials_split` 之后无条件调用它（`ddl.py:147`），包括 migrate 提前返回的情况。`apply_wave8_migrations` **不**调用它：schema Job 以插件角色跑 `--wave8-only`，表属主是 postgres（和 `add_financials_filing_date` 不走这条路是同一原因）。活库用单独的 SQL：`scripts/ddl/2026-10-07-td107-period-date-symbol.sql`，六条 `CREATE INDEX CONCURRENTLY IF NOT EXISTS`。Python 路径不用 CONCURRENTLY，因为 `apply_ddl` 在超级用户事务里，给新装用；short_volume 约 5 GB，事务里建索引会锁，所以活库必须走 SQL 文件。short_volume 那条因 IF NOT EXISTS 是空操作。
- 防线：`tests/test_td107_financials_period_index.py`：不再声明 `symbol_period_date`；`apply_ddl` 调用该步骤且 `apply_wave8_migrations` 的源码里没有这个名字；Owner 脚本对每张表是 CONCURRENTLY，键是 `(period_date, symbol)`。
- 门禁：`make lint` 退出码 2。ruff 0.16.4 报 805 errors。仓库 pin 是 `ruff>=0.8`，没有 `select`；ruff 0.16 把默认规则从 59 条扩到 413 条。origin/main 的 `ddl.py` 同样有 I001 和两处 ISC004（对 HEAD 文件用 stdin 复现过），不是本道引入。本道新文件不在这 805 里。`PYTHONPATH=/tmp/cursor-d2-md/src make test` 退出码 0，1284 passed，10 skipped。不设 PYTHONPATH 时 venv 指向共享 checkout，收集失败（其中一条就是共享树没有 `ensure_financials_period_date_symbol`）。
- 验收：`PYTHONPATH=src pytest -q tests/test_td107_financials_period_index.py` → 3 passed。Owner SQL 跑完后六张表都有 `*_period_date_symbol`，没有 `*_symbol_period_date`。
- 要 Owner 批：对 `bifrost_golden_source` 跑那份 SQL，**不要** `psql -1`。
- 后续：无后续。`apply_ddl` 在集群上并不作为活路径（现有注释），活路径就是这份 SQL。

### Owner 执行步骤

```bash
# 不要 -1。CONCURRENTLY 不能在事务块里。
psql "$GS_URL" -v ON_ERROR_STOP=1 -f scripts/ddl/2026-10-07-td107-period-date-symbol.sql
```

预期：`pg_indexes` 里六张表都有 `{table}_period_date_symbol`。short_volume 上原来就有，这条是空操作。没有 `symbol_period_date`。

回滚：`…-rollback.sql` 会丢掉全部六个，**包括 short_volume 上原本就有、四轴读取在用的那个**。若只想撤掉新建的五个，不要对 short_volume 执行那一行。

## TD-160

- Claim：成立。只读 GS `features.event_signal_radar_daily`：`event_radar_batch_collected` 160 kB，键 `(batch_id, collected_at DESC)`，与 `event_signal_radar_daily_batch_collected` 相同；`event_radar_importance` 160 kB，键 `(collected_at DESC, importance DESC)`，与 `event_signal_radar_daily_importance` 相同。台账写 152 kB，现为 160 kB，仍是重复。`event_radar_pkey` 1040 kB，UNIQUE `(event_id)`，保留。`ddl.py` 只建新名字（`ddl.py:1572` 起），本道没改这个文件（LANE-R2 的 research worktree 动的是 deployment 和 daemon manifest 测试，不是 schema）。
- 改动：bifrost-research · `cursor/d2-research` · `6696fccb34974dc61ce12cf1901e350b2fdce182`。`scripts/oneoff/2026-10-07-td160-drop-event-radar-dup-indexes.sql` 两条 `DROP INDEX CONCURRENTLY`。检查 SQL 读 `pg_index` 的 indkey、谓词和大小。回滚按 2026-10-07 的 `pg_get_indexdef` 重建旧索引，CONCURRENTLY。
- 防线：`tests/schema/test_td160_duplicate_indexes.py`：`ddl.py` 不再创建旧名字；Owner 脚本的 DROP 恰好是这两个，不含主键，没有顶格的 `BEGIN`；`event_signal_radar_daily` 上没有两个索引共享同一组键。CI 看不见 GS，所以防线是这条单测，不是对活库的断言。
- 门禁：`make lint` 退出码 0（ruff 与 sqlfluff，`All Finished`）。`make test` 退出码 0，2146 passed，29 skipped。提交时仓库自己的 code-health 钩子 OK（重复函数名 25/25，超 800 行 5/5，镜像 tag 2/2）。
- 验收：`pytest -q tests/schema/test_td160_duplicate_indexes.py` → 3 passed。活库跑检查 SQL：丢之前 5 个索引、两对 indkey 相同；丢之后旧的两个消失，新的两个和 `event_radar_pkey` 还在。
- 要 Owner 批：在 GS 上跑 DROP。不要 `psql -1`。不要丢主键。
- 后续：无后续。

### Owner 执行步骤

1. 跑 `scripts/oneoff/2026-10-07-td160-event-radar-index-check.sql`（只读）。预期 5 行，两对定义相同。
2. 不要 `-1`，跑 `…-drop-event-radar-dup-indexes.sql`。
3. 再跑检查 SQL。预期旧的两个不在，`event_signal_radar_daily_batch_collected`、`event_signal_radar_daily_importance`、`event_radar_pkey` 还在。
4. 回滚：`…-rollback.sql`（两条 `CREATE INDEX CONCURRENTLY`，定义是 2026-10-07 抓的）。

## TD-148

- Claim：成立，但证据路径变了。台账写 `ddl.py:533`；origin/main 上 CREATE 在 `trade_ddl.py`（本分支第 124 行）。`_SOURCE_KINDS` 在 `strategy_plan.py:610`（台账写 :593）。`SourceKind` 在 `monitor/schemas/strategy_plans.py:17`。只读 `pg_constraint`，DEV / STG / PROD 三个库约束名都是 `strategy_plan_source_kind_check`，定义都是 `CHECK (source_kind = ANY (ARRAY['manual','symbol','hypothesis','inbox_draft','roll']))`。计划行数：DEV 3，STG 0，PROD 0。只放宽，现有行都过。
- 改动：同一 core 提交 `c55d591465f858ab349b33a29fe5d804b5d8125f`。`trade_ddl.py` 的新建 CHECK 加上 `'lens'`、`'backtest_run'`，让新装和准备好的 DDL 一致。`scripts/db/2026-10-07-td148-strategy-plan-source-kind.sql` 一份，三个库共用（不是 GS）：`DROP CONSTRAINT` 再 `ADD` 同名约束。回滚在事务里，若已有行用了 `lens` 或 `backtest_run` 就 `RAISE EXCEPTION`，否则收回五个值。表很小，ACCESS EXCLUSIVE 可以接受。
- 运行时白名单**没有**放宽：`_SOURCE_KINDS` 和 `SourceKind` 仍是五个活值。原因：那是公开接口，要 bump core；第 2 轮只预批了 TD-91 / TD-102 / TD-123 的公开接口改动；LANE-T 已在 `cursor/t-core` 上为一次版本 bump 改着 `pyproject.toml`。DDL 落地之后，API 仍会拒绝 `lens` / `backtest_run`，直到白名单、trade-api 和前端枚举一起动。这是故意的。
- `docs/DATABASE.md` **没有提交**。LANE-T 的 worktree 正在改这个文件。准备好、未写入的两句（英文，与该文件一致）：
  - 策略计划表那一行：Live CHECK（2026-10-07 从 DEV、STG、PROD 的 `pg_constraint` 读到，都叫 `strategy_plan_source_kind_check`）仍是 `manual` · `symbol` · `hypothesis` · `inbox_draft` · `roll`。准备好的放宽加上 `lens` 和 `backtest_run`（`scripts/db/2026-10-07-td148-strategy-plan-source-kind.sql`）；`source_ref` 带 lens id 或 backtest run id。`_SOURCE_KINDS` 和 `SourceKind` 保持五个活值，直到 DDL 跑完并且 core bump。
  - 附录 `source_kind` 行：live CHECK 是这五个值。新的 `trade_ddl.py` 和 Owner DDL 还允许 `lens` · `backtest_run`。API 白名单在 DDL 落地前不允许。
- 防线：`tests/test_td148_source_kind_prepare.py`。`test_fresh_ddl_and_owner_script_share_the_widened_set`：`trade_ddl.py` 与 SQL 的 IN 列表都是七个值。`test_runtime_allowlist_matches_the_live_check`：`_SOURCE_KINDS` 和 `get_args(SourceKind)` 仍是五个。一边动了另一边没动，测试会失败。
- 门禁：同 TD-103 的 core 数字。`make lint` 退出码 0；带 PYTHONPATH 的 `make test` 退出码 0，13462 passed。
- 验收：`PYTHONPATH=src pytest -q tests/test_td148_source_kind_prepare.py` → 3 passed。三个库跑完 DDL 后 `pg_get_constraintdef` 含 `lens` 和 `backtest_run`，约束名不变。DEV 的 3 行、STG/PROD 的 0 行仍然合法。
- 要 Owner 批：对 `bifrost_dev`、`bifrost_stg`、`bifrost_prod` 各跑一次这份 SQL。不要对 Golden Source 跑。
- 后续：白名单、trade-api、前端枚举要在 DDL 之后、下一次 core bump 时放宽。`DATABASE.md` 的两句等 LANE-T 合并后再贴（停在该文件上）。

### Owner 执行步骤

对三个库各一次（不是 `bifrost_golden_source`）：

```bash
psql "$URL" -v ON_ERROR_STOP=1 -f scripts/db/2026-10-07-td148-strategy-plan-source-kind.sql
```

预期：约束名仍是 `strategy_plan_source_kind_check`，定义里有 `lens` 和 `backtest_run`。现有行不用改。

回滚：`…-rollback.sql`。若已有行的 `source_kind` 是 `lens` 或 `backtest_run`，事务中止，五个值的 CHECK 不会被装回去。

DDL 之后插入这两个值，API 仍会 400，直到 `_SOURCE_KINDS` 和 `SourceKind` 放宽。

## TD-142

- Claim：成立（数字有漂移，结论不变）。`DTE_MAX = 90` 在 `engines/volatility/iv_solver.py:54`。`MIN_SESSIONS = 60` 在 `repositories/iv_cone.py:49`。只读 GS（副本，`statement_timeout` 180s）：已有 `features.option_metric_atm_iv_daily` 且 DTE>90、`atm_iv` 非空：10633 行，230 个标的，43 个交易日，29 个到期日，2026-08-05..2026-10-06。按名字：NVDA 39 个交易日，AAPL 32，SPY 27（台账 SPY 是 31）。90 天历史仍低于 60 个交易日的门槛，没有 180 天。
- `option_daily` 上 `expiry - bar_date` 在 (90, 220]、`bar_date >= 2025-11-10`：20953 根 bar，307 个标的，227 个交易日，4548 个 (symbol, session, expiry)，3883 个 symbol-day，第一根 2025-11-10，最后一根 2026-10-06。2026-08-05 之前的三元组 1795（特征表里没有）。2026-08-05 及之后 2753，其中 1177 缺特征行。缺的特征行合计 2972。若每个缺的三元组写一行 ATM IV，新增 2972 行。这一趟应访问已经有远期 bar 的 3883 个 symbol-day，只把这一趟的 `DTE_MAX` 抬到 220。没有计时。
- 改动：同一 research 提交里的 `scripts/oneoff/2026-10-07-td142-td172-scope.sql`（注释是这次的数，文件里的 SELECT 可重跑）。**没有改 research 的求解代码。**
- 防线：做不了锥对 DTE 的测试。那样就是开始设计回填，本道只列范围。工件是这份只读 SQL。
- 门禁：同 TD-160。`make test` 2146 passed。这份 SQL 不进 sqlfluff 的 `models/` 路径。
- 验收：重跑文件里 TD-142 的 SELECT。行数、标的数、交易日数与上面同一数量级；若漂移超过一小截，回填前停。
- 要 Owner 批：真正的回填（把 `DTE_MAX` 临时抬到 220，只覆盖那 3883 个 symbol-day）。本道不做。
- 后续：回填是下一条债，不在本道。

### Owner 执行步骤

没有 DDL。回填之前重跑 scope SQL 里 TD-142 的 SELECT。预期仍是大约一万行已有的 >90 DTE 特征、约 2972 行可补。回滚：这一项没有写入。

## TD-172

- Claim：成立。`research.option_universe` = 718。2026-07-06..09-25 有任意 ATM IV 行的 name-day：37687，684 个名字，59 个交易日（SPY 也是 59）。没有 50–100 DTE 到期日的 name-day：29229。按周、`bool_or(50–100)` 的份额：07-06 0.15（3194）、07-13 0.12（3134）、07-20 0.16（3204）、07-27 0.14（3181）、08-03 0.02（3222）、08-10 0.02（3157）、08-17 0.24（3233）、08-24 0.35（3257）、08-31 0.17（3232）、09-07 0.33（2612）、09-14 0.43（3064）、09-21 0.59（3197）。与台账的 0.15 / 0.12 / 0.02 / 0.02 / 0.35 / 0.43 / 0.59 同形，每周都远低于 0.85。
- 窗口里已经落在 50–90 DTE 的 `option_daily`：114748 根 bar，26311 个 ticker，634 个名字，59 个交易日。健康参照周 2026-06-22..26：74485 根，23526 个 ticker，684 个名字（约 14897 根/交易日，约 34 个 ticker/名字）。若这个速率撑满 59 个交易日：74485/5*59 = 878923 根。缺口约 764000 根。
- 供应商调用是每个 `option_ticker` 一次 `fetch_stock_aggs` 的 from/to，不是每个交易日一次（`ingest/option_daily.py` 的 `handle_option_daily`）。一张 50–90 的合约在带内大约 29 个交易日，所以独立 ticker ≈ 23526 × (59/29) ≈ 48000 次区间请求。上界：2026-09-28 及之后仍挂牌、到期日落在 2026-08-25..2026-12-24 的合约 86361 个 ticker、690 个名字；实测最早到期日是 2026-09-28，最晚 2026-12-18。2026-09-28 之前到期的不在这个数里。Starter 软顶 8 req/s：48000/8 ≈ 100 分钟，86361/8 ≈ 3 小时，只是排队时间，没有实测运行时长。
- 改动：同一份 scope SQL 里的周份额 SELECT。没有改 market-data 拉取。
- 防线：做不了 doctor 的广度告警。那是 market-data / research 的行为改动，会把回填设计提前做掉。本项只有只读统计。
- 门禁：同 TD-160。
- 验收：重跑 scope SQL 里的周份额查询。每一周的 `share_50_100` 仍明显低于 0.85；若某一周已经到 0.85 附近，先停下来再决定要不要重拉。
- 要 Owner 批：按上面的请求量向供应商重拉 50–90 DTE。本道不做。
- 后续：重拉是下一条债。到期日早于 2026-09-28 的合约不在 86361 里，上界是偏低的。

### Owner 执行步骤

没有 DDL。重拉之前重跑周份额 SELECT。预期仍是每周远低于 0.85，缺口仍是几十万根 bar 这个量级。排队时间用 8 req/s 估算，不要当成已经计过时。回滚：这一项没有写入。
