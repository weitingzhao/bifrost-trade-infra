# W3 · 不可再生数据先归档再删 — 上线计划（2026-10-05）

> 线程：「[Trade System·还债] 期权快照先归档再删」。repo：`bifrost-platform-plugin-market-data`，
> 分支 `claude/w3-archive-before-delete`（基于 origin/main 40fe0e1，4 个提交，版本 0.77.0）。
> 不涉及任何 DDL（PROD 或 GS 都没有）。D10 不涉及。

## 1. 原值（改之前记录，2026-10-05 19:30 UTC 实测线上 ConfigMap 与 main 一致）

| 键（`scheduler.slots.trim`） | 原值 | 暂停后 |
|---|---|---|
| `option_snapshot_keep_sessions` | 90 | 36500 |
| `option_snapshot_keep_days` | 未设（代码默认 90） | 36500 |
| `option_snapshot_intraday_keep_days` | 30 | 36500 |
| option_daily / short_volume 窗口 | 730 天，来自 `contracts.retention_days`，**不是配置** | 0.77.0 起用 `retention_hold` 暂停 |

## 2. 真正的删除时间表（实测）

| 数据 | 现存最早 | 下一次真删除 | 每次删多少 |
|---|---|---|---|
| option_snapshot 盘中行 | 2026-09-08 | **约 10-08 02:15 UTC**（30 天窗口） | 每晚约一个 session，约 35 万行 |
| option_daily | 2024-10-01 | **11-01 02:15 UTC**（截止日按月取整） | 2024 年 10 月整月，约 180 万行 |
| short_volume | 2024-10-01 | **11-01 02:15 UTC** | 约 30 万行 |
| option_snapshot EOD | 2026-08-05（42 个 session） | 约 12 月中（90 session） | 每晚一个 session |

所以步骤 A 要在 10-08 之前做；步骤 B 要在 11-01 之前上线。

## 3. 步骤

### A · 暂停 option_snapshot 删除（你 10-05 已批，只改配置）

```bash
cd /Users/vision-mac-trader/Desktop/stocks/bifrost-platform-plugin-market-data && git fetch -q origin claude/w3-archive-before-delete && git show origin/claude/w3-archive-before-delete:k8s/base/configmap-schedule.yaml | KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n plugin-market-data apply -f - && KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n plugin-market-data rollout restart deploy/market-data-api
```

分支上的 ConfigMap 还带着 `retention_hold` / `retention_archive` 两个新键；0.76.0 不认识它们，直接忽略。

- **验证**：下一次 trim 的结果里 `option_snapshot_keep_days` = 36500。
- **回滚**：把 origin/main 的同一文件 apply 回去，再 restart。

### B · 发 0.77.0（需要你点头）：`retention_hold` + 归档代码 + NAS 卷，上线后不删任何东西

改动：

- `retention_hold`：trim 对列出的表不删行、不 drop 分区。配置里三张全列上。
- `retention_archive`：新模块。按「整天组成的区间，不跨月」逐段处理，每段一个 REPEATABLE READ 事务：
  1. 用服务端游标导出成 Parquet（zstd）；
  2. 读回文件，行数要对上；
  3. 用同一谓词、同一快照 DELETE，rowcount 也要对上；
  4. 改名、提交，再写 manifest（sha256、逐日行数、谓词）和 `_ledger.jsonl`。

  任何不一致或 I/O 错误都回滚，行留在库里。`/archive` 不是挂载点时，拒绝归档，也不删。归档的表跳过整月 drop。
- **hold 优先于 archive**，所以 0.77.0 上线后行为与步骤 A 相同：什么都不删。
- k8s：
  - 新 PVC `market-data-archive`（StorageClass `nfs-cold`，RWX，200Gi 只是登记值，provisioner 不强制；Retain，删 PVC 不删文件），挂到 market-data-api 的 `/archive`；
  - api 内存上限 512Mi → 768Mi（pyarrow）。
- 新依赖 `pyarrow>=17`。

步骤（插件不归 Argo；一次发布只由一个会话执行，先查 registry 没有 0.77.0）：

1. 把分支合进 main 并推送。
2. `make -C bifrost-trade-infra k3s-sync-gitea-mirrors`。
3. 用 `pipelinerun-build-market-data.yaml` 建 0.77.0，确认 registry tags 里有 0.77.0。
4. 先单独 apply `k8s/base/pvc-archive.yaml`，确认 `Bound`，NAS 上出现 `/volume1/k3s-cold/plugin-market-data-market-data-archive-pvc-…`。
5. kustomization pin 0.77.0（deploy 提交），`kubectl apply -k k8s/base`，最后 `make verify-market-data`。

验证：

- api pod 里 `python -c "import os;print(os.path.ismount('/archive'))"` → True；
- 下一次 trim 结果 `retention_held` 有三张表，`retention_archive` 为 `{}`。

回滚：apply 0.76.0 的 kustomization。PVC 留着无害。

避开 21:05–23:15 UTC 采集窗口和 02:15 UTC trim。

### C · 逐表解除 hold，转为「先归档后删」（需要你点头，每张表一次）

每次只删 ConfigMap 里 `retention_hold` 的一行，然后 restart api。不用发版。

1. **option_snapshot**：最先解除，只有它每天都有到期行。第二天核对：
   - trim 结果 `retention_archive["raw_market.option_snapshot:intraday"].rows` > 0，且 `error` 为空；
   - NAS 上有 `raw_market/option_snapshot/intraday/2026/*.parquet` 和对应的 `.json`；
   - 抽一个文件，用 pyarrow 读出的行数等于 manifest 的 `rows`。
2. **short_volume**、**option_daily**：在 11-01 之前解除。11-01 那晚会一次处理一整月（option_daily 约 180 万行、一个事务），trim 的 HTTP 调用会比平时长。`dated_budget_sec` 是 60 秒；超时的话分几晚做完，没做完的行留在库里。

解除 hold 后，option_snapshot 的三个数值要改回原值（90 / 删掉 keep_days / 30），否则窗口一直是 100 年，什么都不会到期。

## 4. 已知的风险和遗留

- **归档跑在 market-data-api 进程里**（trim 由 Dagster 经 HTTP 触发，在 api 里同步执行）。CPU 上限 500m；整月的 option_daily 压缩可能让 `/health` 变慢。上线后看 11-01 那晚的 restartCount。
- **option_daily_default 没有以 bar_date 开头的索引**，每段归档要整扫一遍默认分区。现行删除本来也这样扫。所以按段一次扫描，不按天扫。
- **归档后留下的空分区**（option_daily 月分区从 2027-08 才开始到期）不会被 drop，以后另行决定。
- **同一台 NAS**：k3s-cold 与 PG 备份在同一台 NAS 上，异地副本归 W5 之后再定（见阶段 0 计划）。
- 读取归档：`pyarrow.dataset.dataset("/archive/raw_market/option_daily", format="parquet")`，按主键去重。崩溃在「改名之后、提交之前」时，同一行可能出现两次，但不会缺。

## 状态（2026-10-05 22:45 UTC）

- A、B、C 全部完成：0.77.0 已上线（main b6baf08），三表的 hold 全部解除（main dbc4338），全部走「先归档后删」；option_snapshot 窗口已恢复 90 session / 盘中 30 天。
- 真数据只读演练（各表最早一天，同一路径导出后回滚）：读出 = 文件 = 库内行数。
- 首次真归档：盘中快照 10-09 02:15 UTC；option_daily / short_volume 11-01 02:15 UTC。核对由桌面应用定时任务 `w3-verify-first-snapshot-archive`、`w3-verify-monthly-archive-2026-11` 执行。
