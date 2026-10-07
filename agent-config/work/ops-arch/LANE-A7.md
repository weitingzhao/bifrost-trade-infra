# LANE-A7 — 节点补丁调查（只读）+ 滚动重启脚本（不执行）

ADR §7（节点补丁有主人）。仓库：bifrost-trade-infra，分支 `cursor/a7-infra`。

## 事实（10-07 抽查 .73、.75）

- `unattended-upgrades` 已启用（`APT::Periodic::Unattended-Upgrade "1"`），但 dpkg 日志里 **6 月底以后没有安装过任何包**；
- 两台都有 `/var/run/reboot-required`，时间是 09-11；已连续运行 8 周；
- 另外 3 台（.70、.77、.79）没查；gpu-server（.60）平时关机，跳过并注明。

## 要做

1. 只读调查 5 个 k3s 节点（`ssh -o IdentitiesOnly=yes -i ~/.ssh/bifrost_deploy vision@<ip>`，不用 sudo 写任何东西）：
   `/var/log/unattended-upgrades/` 日志、`/var/log/apt/history.log*`、`apt-mark showhold`、`apt list --upgradable` 数量（含安全更新数）、`/var/run/reboot-required.pkgs`、内核版本、k3s 版本、uptime、磁盘余量。
2. 查清自动更新为什么不装包（配置、origins、锁、被 hold 的包、网络），给出修法（配置 diff），**不执行**。
3. 滚动重启脚本 `scripts/k3s/rolling-reboot.sh`（默认 `--dry-run`，只打印计划）：
   - 一次一台：cordon → drain（遵守 PDB）→ 重启 → 等 Ready → uncordon → 核对该节点上的工作负载恢复；
   - 顺序：general 节点先，`ubt-k3s-02`（PROD）其次，`ubt-k3s-04`（数据库主库）最后；主库所在节点重启前先做 CNPG 主备切换；`ubt-k3s-01`（唯一控制面）单独一步，说明 API 中断约 10 秒；
   - 只在周末窗口运行（脚本检查美东时间，非周末拒绝执行，可用显式参数覆盖并打印警告）；
   - 任何一步失败就停，不继续下一台。
4. 防线：脚本的 `--dry-run` 计划有测试（给定节点清单，断言顺序与「主库最后」）。

## 不做

不改节点、不重启、不装包、不 cordon。

## 验收

- 报告里每个节点一行的调查表；
- 分支上 `bash scripts/k3s/rolling-reboot.sh --dry-run` 打印出 5 个节点的顺序计划，主库节点在最后、切换步骤在它之前。

## 要 Owner 批

自动更新的配置修复，以及第一次周末滚动重启（D 级）。
