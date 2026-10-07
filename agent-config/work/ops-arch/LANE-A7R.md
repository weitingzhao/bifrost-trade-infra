# LANE-A7R — A7 返工：主库位置要实时读，不能写死

在 `cursor/a7-infra`（`d1ec0f3d`）基础上继续，分支仍是 `cursor/a7-infra`。

## 为什么返工（Claude Code 验收，2026-10-07）

`rolling-reboot.sh` 把 `ubt-k3s-04` 写死成 `data-primary`（第 71 行的 `NODES_SPEC`）。实测：`kubectl -n data get cluster bifrost-postgres -o jsonpath='{.status.currentPrimary}'` → `bifrost-postgres-1`，它在 **ubt-k3s-02**。按现在的计划，第 4 步会在没有主备切换的情况下重启真正的主库节点。节点标签 `data-primary` 只表示偏好，不代表当前主库。

## 要做

1. 主库位置在**计划时**和**每台节点动手前**都从 CNPG 实时读：`.status.currentPrimary` → Pod → `spec.nodeName`。不再依赖 `data-primary` 角色或标签。
2. 规则：当前主库所在节点排最后；轮到它之前，先把主库切到一台**已经重启完**的节点上的副本，确认切换完成、副本追平后再继续。中途主库位置变了（例如 drain 触发了切换），重新计算剩余顺序。
3. 切换用 CNPG 的标准做法（`kubectl cnpg promote` 或等价的 `status.targetPrimary` 方式，按集群里 CNPG 的版本选）。**不要**调用 `make k3s-switchover-postgres-primary`（报告已指出它方向固定）。
4. 只剩一个实例或副本没追平时停止，不重启主库节点。
5. 防线 `test_rolling_reboot_plan.py`：用假的 kubectl 输出，覆盖「主库在 02 → 02 最后、切换在它之前」「主库在 04 → 04 最后」「执行中主库移动 → 重新计算」「副本未追平 → 停止」。

## 验收

- 分支上 `python3 -m unittest scripts/k3s/test_rolling_reboot_plan.py` 全部通过；
- `bash scripts/k3s/rolling-reboot.sh --dry-run` 在当前集群上把 **ubt-k3s-02** 排在最后，`switchover-before: ubt-k3s-02`。

## 要 Owner 批

不变：自动更新加 `-updates`（5 台），以及第一次周末滚动重启。等这道验收通过后由 Claude Code 统一提交。
