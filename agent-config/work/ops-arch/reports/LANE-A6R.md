# LANE-A6R

代码在 `cursor/a6r-infra`，父提交 `730e6200060f5db9d390b98b8e61e962e6664b4e`。写本报告时 `origin/main` 是 `8504fcd9c74cbca62a9bf40eb499a43db111601b`；本道碰过的路径在这两点之间没有改动。没有 apply，没有建集群，没有改 MinIO，没有写数据库，代码没有推 main。

## 合成一套

- 改动：bifrost-trade-infra · `cursor/a6r-infra` · `8d37a16a64417fd1765182614a51ae4e5486394e`（已推该分支）。演练清单改为命名空间 / Cluster `pg-recovery-drill`，Secret 仍是 `minio-backup-readonly`，`targetTime` 由 `k8s/data/drills/render-cluster.sh` 填入。删掉 `k8s/data/recovery-drill/`。`docs/runbooks/pitr-drill.md` 是唯一手册：手工、每季度一次（一月、四月、七月、十月的第一个周一），下一次是 2027 年 1 月的第一个周一；删集群时不删命名空间。
- 防线：`scripts/check_pitr_drill_manifest.py` 的 `self_test`（好清单、`spec.backup`、flow 形式的 `backup:`、生产名字、错误 serverName、`spec.plugins`、错误命名空间、缺少 `targetTime`、错误 Secret、注释里的 backup）。`make check-pitr-drill` 同时检查仓库里的新清单：无 `backup` / `plugins`、名字不是 `bifrost-postgres`、`serverName` 指向生产、凭证是 `minio-backup-readonly`、`targetTime` 仍是占位符。
- 门禁：`make check-pitr-drill` → exit 0，`ok …/k8s/data/drills/pitr-drill-cluster.yaml`。
- 验收：`test ! -e k8s/data/recovery-drill && bash k8s/data/drills/render-cluster.sh 2026-10-07T18:37:26Z | grep -n 'targetTime: "2026-10-07T18:37:26Z"'` → exit 0，且有一行 `targetTime: "2026-10-07T18:37:26Z"`。
- 要 Owner 批：没有。下次演练按手册渲染后再 apply，本次没有创建集群。
- 后续：`agent-config/RATCHETS.md:162` 仍指向已删除的 `k8s/data/recovery-drill/`，台账未改。

## 核对脚本三处修复

- 改动：同上 SHA。`scripts/drills/pitr_verify.sh`：① 不再用 `archived_count != 0` 拒绝，改为演练 Cluster 没有 `.spec.backup` 与 `.spec.plugins`，`archive_command` 含 barman / `s3://` / 桶名仍拒绝；② 恢复点顺序是 `PITR_RECOVERY_POINT`、`targetTime`、日志、最后才估，估计时打出醒目警告；③ `raw_market.option_open_interest` 以及带更新时间列的表：总行数一致，且目标时间之后被改写的行数等于两边「时间戳 ≤ 目标」的行数差。全部 PASS 时先删再建 `data/pg-recovery-drill-last-pass`（日期、恢复点、表数、耗时）。
- 防线：`pitr_verify.sh --self-test` 里的 `cluster_archive_block`（空规格不因归档计数拒绝、backup、plugins、barman、s3、桶名、noop 命令）、`choose_recovery`（targetTime 优先、日志其次、占位符不当恢复点、估计垫底）、`judge` / `render` 的 `10-07 option_open_interest`（6,548,559 行里 125,860 行改写为通过；`option_snapshot` 仍走严格时间戳）、`pass_record`（只有那四个键，未全过不记录）。
- 门禁：`bash scripts/drills/pitr_verify.sh --self-test` → exit 0，`self-test ok`。没有对集群执行脚本。
- 验收：`bash scripts/drills/pitr_verify.sh --self-test` → 打印 `self-test ok`，exit 0。
- 要 Owner 批：没有。ConfigMap 只在实跑全部 PASS 时写入，本次没有跑。
- 后续：`scripts/drills/pitr_verify.sh:68` 只把 `option_open_interest` 标成主键冲突更新；别的表要靠更新时间列才会走这条规则。

## 演练过期告警（TD-258）

- 改动：同上 SHA。`BifrostPostgresRecoveryDrillStale` 移到 `k8s/monitoring/bifrost-postgres-recovery-drill-rules.yaml` 并放回 monitoring kustomization。表达式是 `time() - kube_configmap_created{namespace="data",configmap="pg-recovery-drill-last-pass"} > 8640000`（100 天），或该 ConfigMap `absent`；severity `warning`。`td-d2-postgres-rules.yaml` 里的 WAL 规则原文未改，文件仍不在 kustomization。没有改 `bifrost-maintainer-rules.yaml` 和 `maintainer-reconcile/`。
- 防线：`scripts/check_alert_routing.py` 的 `drill_stale`（缺席与超过 8640000 秒为真，等于 100 天为假）和 `assert_drill_stale_unpaged`（名字、warning、8640000、`absent`、不匹配呼人正则、不到集群外接收者）。
- 门禁：
  - `PATH="/usr/bin:$PATH" python3 scripts/check_alert_routing.py` → exit 0，`ok (values-kube-prometheus.yaml): Watchdog and 11 paged alert kinds reach a receiver outside the cluster; default receiver is platform-api.bifrost-platform-prod.svc.cluster.local`。呼人种类仍是 11，这条规则没有加进去。
  - `kubectl kustomize k8s/monitoring` → exit 0。渲染结果含 `BifrostPostgresRecoveryDrillStale` 与 `8640000`，不含 `BifrostPostgresWalDailyHigh`。没有 apply。
  - `make check-maintainers` → exit 0，`ok 45 maintainers; static; no-alert 15`。
- 验收：`PATH="/usr/bin:$PATH" python3 scripts/check_alert_routing.py` → exit 0，且输出里的 paged alert kinds 仍是 11。
- 要 Owner 批：先补记 10-07 的 PASS，再 apply 规则，避免 `absent()` 在空窗里响起。`kube_configmap_created` 会是执行下面命令的时间，不能写成 2026-10-07；`date` 字段仍是演练日。`duration=23m` 是那次恢复耗时。表数 105 是 104 张直接通过加上当时手工判过的那张 upsert。在含该 SHA 的 `bifrost-trade-infra` 检出根目录执行：

```bash
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/bifrost-k3s.yaml}"
kubectl -n data delete configmap pg-recovery-drill-last-pass --ignore-not-found=true
kubectl -n data create configmap pg-recovery-drill-last-pass \
  --from-literal=date=2026-10-07 \
  --from-literal=recovery_point=2026-10-07T18:37:26Z \
  --from-literal=table_count=105 \
  --from-literal=duration=23m
kubectl apply -f k8s/monitoring/bifrost-postgres-recovery-drill-rules.yaml
```

不要 `kubectl apply -k k8s/monitoring`，也不要 apply `k8s/monitoring/td-d2-postgres-rules.yaml`。
- 后续：无后续。WAL 规则继续等 TD-134，不在本道。
