# LANE-S2 报告

起点：platform `origin/main` `2727eb0294c62f697a00bd51ffc455a924027171`，infra `origin/main` `54d8147caeaae12b32f89da67c9ae7a60c04cfd9`。只推了分支，没有推 main，没有 deliver / kubectl apply / 写库 / 改台账。没有改 `api/internal/remediation`，没有改 `api/internal/delivery`。

## TD-222
- Claim：成立（`bifrost-platform/api/internal/cluster/actuation.go:149` 在改前是 `req.Name == "daemon" && current == 0 && req.Replicas > 0`，只拦 0→n；PROD overlay `daemon-observe-safe.patch.yaml` 仍是 `replicas: 2`）
- 改动：bifrost-platform · `cursor/s2-platform` · `3f0408fd113c1f6b8a900b279ba453870d2a7bb6`。Deployment 名 `daemon` 的任何 replicas 增加（requested > current）在 spine `decisions[id=D10].status` 不是 `UNLOCKED` 时拒绝；状态每次从 `ops-context.yaml` 读（`NewHandler` 写入 `Config.OpsContextPath`，与 platform-api 加载 spine 的路径相同，也就是 preflight 读的那个字段），文件缺失、解析失败或没有 D10 都当成 BLOCKED。缩容和原副本数放行。D10 为 UNLOCKED 时 0→1、1→2、2→3 放行。没有改下单路径、`ib:operator:cmd`、`POST /control/*`，也没有放宽已有拦截。
- 防线：`api/internal/cluster/actuation_scale_test.go` · `TestScaleDaemonUpFromNonZeroBlocked`（bifrost-prod 2→3）、`TestScaleDaemonReplicaChanges`（dev/stg/prod 的 0→1、1→2、2→3 与缩容）、`TestScaleDaemonUpAllowedWhenD10Unlocked`、`TestScaleDaemonUpBlockedWhenSpineMissingD10`、`TestScaleDaemonDownAllowedWhenSpineUnreadable`
- 门禁：在 platform worktree 的 `api/`：`go build ./...` → exit 0；`go vet ./...` → exit 0；`go test ./... -count=1` → exit 1。失败的两处都不在本提交里，origin/main 上已如此：`internal/safego` `TestNoUnguardedGoroutines`（`checklist/prober.go:83` 裸 `go func`）、`internal/tradevocab` `TestTradeVocabularyOnlyShrinks`（`probe/probe.go` 预算 0）。`internal/cluster` 为 ok。
- 验收：`cd bifrost-platform && git fetch -q origin && git checkout 3f0408fd113c1f6b8a900b279ba453870d2a7bb6 -- api && cd api && go test ./internal/cluster -run 'TestScaleDaemon' -count=1 -v | grep -E 'NonZero|PASS|FAIL'`。预期：`TestScaleDaemonUpFromNonZeroBlocked` PASS，表测里 0→1 / 1→2 / 2→3 为 PASS（拒绝），缩容 PASS，整段最终 PASS。
- 要 Owner 批：代码进集群要等这条分支合并后再做 platform deliver。本道没有发版。
- 后续：无后续（本项）。`go test ./...` 的两处既有失败见上，不是本项引入的。

## TD-131
- Claim：成立（改前 `RepairPostgresWalStore` 调用 `deleteStuckBackupCRs`，`pickStuckBackupNames` 把 phase `failed` 和 `walArchivingFailing` 的 `bifrost-postgres-*` Backup 全部删掉）
- 改动：同一 platform 提交 `3f0408fd113c1f6b8a900b279ba453870d2a7bb6`。修复路径不再删除任何 Backup。新方法 `SweepExpiredFailedBackupCRs` 只删除创建时间严格早于 30 天、phase 为 failed / walArchivingFailing、名字匹配 `bifrost-postgres-*` 的 Backup；没有 creationTimestamp 的留下。HTTP：`POST /api/v1/cluster/postgres/backups/sweep-failed`（operator）。`PLATFORM_BACKUP_CR_SWEEP=1` 时 workers 进程每天跑一次，并在启动时跑一次。infra 分支 `cursor/s2-infra` · `da9376a8b2c334d25cf73817582923392989e9af` 只在 PROD `platform-workers` 上设这个环境变量。没有新的 Kubernetes verb：list 已在 `bifrost-platform-observer`，delete 已在 `bifrost-platform-data-actuator`（仅 PROD）。`00-clusterroles.yaml` 只加了注释，没有新规则，所以没有重跑 `gen_platform_rbac.py`。
- 防线：`api/internal/cluster/postgres_wal_repair_test.go` · `TestRepairPostgresWalStoreDoesNotDeleteFailedBackup`（40 天前的 failed Backup，repair 的 dynamic client 动作里没有 delete）、`TestSweepExpiredFailedBackupsKeepsRecentFailures`、`TestPickExpiredFailedBackupNames`（刚好 30 天留下，超过 1 秒才删）
- 门禁：与 TD-222 同一次 `go build` / `go vet` / `go test`（exit 0 / 0 / 1，cluster 包 ok）。infra：`KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_platform_rbac.py` → exit 0，`ok: 82 permission answers match`。
- 验收：`cd bifrost-platform && git checkout 3f0408fd113c1f6b8a900b279ba453870d2a7bb6 -- api && cd api && go test ./internal/cluster -run 'TestRepairPostgresWalStoreDoesNotDeleteFailedBackup|TestSweepExpiredFailedBackupsKeepsRecentFailures|TestPickExpiredFailedBackupNames' -count=1`。预期全部 PASS。集群上的 `kubectl -n data get backups` 要等镜像和 PROD env 上去之后才能看；本道没有对集群做 repair。
- 要 Owner 批：合并 infra 后 Argo 会给 PROD platform-workers 加上 `PLATFORM_BACKUP_CR_SWEEP=1`（`bifrost-platform-prod` 是 automated + selfHeal）。合并 platform 并发版之后，修复才不再删失败记录，清扫才会跑。本道没有 apply、没有发版。
- 后续：清扫没有单独的 MCP 工具名（避免再改 `catalog.go` 的工具表和 stdio 名单）。`repair_cnpg_wal_store` 的描述已改成「不删除 Backup」。LANE-R1 的 `cursor/r1-platform` 若改 `api/internal/mcp/catalog.go`，冲突应只在这一行描述，不是 `start_pipeline_run`。`api/internal/server/server.go` 加了清扫路由和 `StartFailedBackupSweep` 调用，与 delivery 路由不在同一段。

## TD-109
- Claim：成立。`k8s/overlays/platform-prod/config/ops-context.yaml:41` 仍是 `headline: "TIBM W3 signed — STG read-path complete (D10 BLOCKED)"`。decision id：platform `config/ops-context.yaml` 55 个，PROD 副本 22 个（少 33 个，没有多出来的），STG 副本 28 个。D10 在三份里都是 BLOCKED。
- 改动：选了同步 + CI 对齐，没有删副本。理由：`bifrost-platform-stg` / `bifrost-platform-prod` 的源是 infra `main`，同步策略是 automated + prune + selfHeal（AGENT_FACTS §8c）。ConfigMap `bifrost-platform-config` 由 overlay 里的文件生成。副本一旦从 git 拿掉，下一次 Argo sync 会剪掉或建不出这个 ConfigMap；交付流水线另 apply 一份会被 selfHeal 盖回去。所以副本留在 git 里。`scripts/sync_platform_k8s_config.sh` 现在把 `ops-context.yaml` 拷进 STG 和 PROD（其它 PROD 配置文件仍不覆盖）。两份副本已换成 platform `2727eb0` 的 spine，字节相同，D10 仍是 BLOCKED。infra · `cursor/s2-infra` · `da9376a8b2c334d25cf73817582923392989e9af`。
- 防线：`scripts/check_ops_context_parity.py`（`--self-test` 检查只解析 `decisions:` 块、D10 状态不一致和缺 id 都会失败；默认比较两份 overlay 与 `PLATFORM_ROOT/config/ops-context.yaml` 的字节，并打印 decision id→status 差）。`Makefile` 目标 `check-ops-context-parity`。`k8s/cicd/tekton/pipeline-ci-platform.yaml` 新 task `check-ops-context`（`runAfter: [clone, clone-infra]`）。
- 门禁：`python3 scripts/check_ops_context_parity.py --self-test` → exit 0（`self-test ok`）。`PLATFORM_ROOT=/tmp/cursor-s2-bifrost-platform python3 scripts/check_ops_context_parity.py` → exit 0（`ok: 55 decisions match … (D10=BLOCKED)`）。`PLATFORM_ROOT=… make check-ops-context-parity` → exit 0。
- 验收：在 infra 检出 `da9376a8b2c334d25cf73817582923392989e9af`、旁边有对应的 bifrost-platform 后：`PLATFORM_ROOT=<bifrost-platform> python3 scripts/check_ops_context_parity.py`。预期 exit 0，且输出含 `D10=BLOCKED` 与 `55 decisions`。platform 的 spine 若再改，在 infra 副本同步之前这条检查失败。
- 要 Owner 批：合并 infra `main` 会让 Argo 立刻换掉 STG 和 PROD 挂载的 ops-context（Console 会看到补上的 33 个 decision；D10 仍是 BLOCKED），并带上 TD-131 的 sweep 环境变量。`bifrost-ci-platform` 这个 Pipeline 对象要另外 apply 之后，新 task 才会在集群里跑。本道两样都没做。
- 后续：这条 CI 步和现有 ci-platform 一样，不挡 release.sh（见台账里「闸门本身不挡发布」）。要它挡住发布，得靠那类总闸，不是本项能单独做成的。STG 副本同样陈旧，一并同步了，否则对齐检查过不了。

## Owner 批准（2026-10-07）

1. 同意合并 infra 分支 cursor/s2-infra（da9376a8b2c334d25cf73817582923392989e9af）到 main（经 Argo 换掉 STG/PROD 的 ops-context，并打开 PROD 的 30 天 Backup 清扫）。
2. 同意 deliver platform 分支 cursor/s2-platform（3f0408fd113c1f6b8a900b279ba453870d2a7bb6），让扩容闸门和「修复不再删 Backup」在集群生效。
3. 同意 apply bifrost-ci-platform 的 Pipeline，让新 task check-ops-context 跑起来。

以上三项由 Claude Code 在 Owner 说「Cursor 做完了 LANE-S2」后执行。
