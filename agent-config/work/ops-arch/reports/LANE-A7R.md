## LANE-A7R

- Claim：成立。返工前 `cursor/a7-infra` 的 `scripts/k3s/rolling-reboot.sh` 在默认 `NODES_SPEC` 里把 `ubt-k3s-04` 写成 `data-primary`（rebase 后的上一笔 `46e4a7f`，原 tip `d1ec0f3`）。节点标签只表示偏好。实测 `kubectl -n data get cluster bifrost-postgres -o jsonpath='{.status.currentPrimary}'` 为 `bifrost-postgres-1`，该 Pod 的 `spec.nodeName` 是 `ubt-k3s-02`。按旧顺序，第 4 步会在没有切换的情况下重启真正的主库节点。
- 改动：bifrost-trade-infra · `cursor/a7-infra` · `37016cb973b83d860332cf8484b59d16156b7038`。分支已 rebase 到 `origin/main`（`0074ea3`），因此相对远端旧 tip `d1ec0f3` 是一次 force-with-lease 更新。上一笔计划脚本现为 `46e4a7fa2049ebe1fbee184d450f0cdbf90c780c`。
- 防线：`scripts/k3s/test_rolling_reboot_plan.py`（假 kubectl，不连集群、不 SSH）
  - `test_primary_on_02_is_last_and_switchover_is_before_it`
  - `test_primary_on_04_is_last`
  - `test_primary_moves_mid_run_and_the_remaining_order_is_recomputed`
  - `test_replica_not_caught_up_stops_before_the_primary_node`
  - 同文件另有 `test_single_instance_stops_before_the_primary_node`：只剩一个实例时停，不重启主库节点
- 门禁：`python3 -m unittest scripts/k3s/test_rolling_reboot_plan.py` → 12 passed。`ruff check scripts/k3s/test_rolling_reboot_plan.py` → All checks passed。`bash -n scripts/k3s/rolling-reboot.sh` → exit 0。infra 没有 `make lint` / `make test`。本机没有 shellcheck。
- 验收：在该 SHA 上 `bash scripts/k3s/rolling-reboot.sh --dry-run`（只读 kubectl）。已观察到：
  - `order: ubt-k3s-05 ubt-k3s-06 ubt-k3s-01 ubt-k3s-04 ubt-k3s-02`
  - `primary-pod: bifrost-postgres-1`
  - `primary-node: ubt-k3s-02`
  - `switchover-before: ubt-k3s-02`
  - 实际 kubectl 只有 `get cluster … currentPrimary` 和 `get pod bifrost-postgres-1 … nodeName`。没有 cordon、drain、promote。
  - 切换用 `kubectl cnpg promote`（CNPG 1.27 的 `status.targetPrimary`）。不调用 `make k3s-switchover-postgres-primary`。执行前再次读主库；主库所在节点最后；轮到它之前，把主库切到本轮已经重启过的节点上、且 `pg_stat_replication` 里 streaming、`replay_lag` ≤ 1 秒的副本，确认 `currentPrimary == targetPrimary`、phase 为 healthy、副本追平后再继续。中途主库换节点则重算剩余顺序。只剩一个实例或副本没追平则停止。
- 要 Owner 批：没有新增。仍是：5 台自动更新加 `-updates`，以及第一次周末滚动重启。等这道验收通过后由 Claude Code 统一提交。
- 后续：本机 `kubectl-cnpg` 是 1.25.1，集群 operator 是 `ghcr.io/cloudnative-pg/cloudnative-pg:1.27.4`。`kubectl cnpg status` 现在拿不到实例的 LSN（pods/proxy 失败），所以追平不用插件 status，而用主库上的只读 `pg_stat_replication`。`scripts/k3s/switchover-postgres-primary.sh:17` 仍把插件钉在 1.25.1，且方向固定，本道没有改它。周末真跑之前把插件对齐到 1.27；若 promote 因插件过旧失败，脚本会停，不会重启当时的主库节点。
