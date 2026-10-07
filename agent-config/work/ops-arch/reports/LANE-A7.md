# LANE-A7 报告

调查时间：2026-10-07 18:57 UTC。只读 SSH（`IdentitiesOnly` + `~/.ssh/bifrost_deploy`）。没有改节点、没有重启、没有装包、没有 cordon。gpu-server（192.168.10.60）SSH 返回 `Host is down`，按车道跳过，下面不计入 5 台。

## LANE-A7

- Claim：车道里「dpkg 日志 6 月底以后没有装过任何包」**不成立**。5 台的 `/var/log/apt/history.log` 都有 10 月的 `Commandline: /usr/bin/unattended-upgrade`（最近一次：.70 / .73 / .79 为 2026-10-07，.75 / .77 为 2026-10-03 的 libxpm4）。「已启用但更新口袋的包不装、重启旗标从 09-11 一直留着」**成立**。证据是节点上的 `/etc/apt/apt.conf.d/50unattended-upgrades`（Allowed-Origins 没有 `-updates`）和 `/var/run/reboot-required`（mtime 09-11 / .70 为 09-12，内容是 libc6）。仓库里没有对应行号。
- 改动：bifrost-trade-infra · `cursor/a7-infra` · `d1ec0f3dad7c088c8c1a81492b211fc80426bcb1`
  - 新增 `scripts/k3s/rolling-reboot.sh`
  - 新增 `scripts/k3s/test_rolling_reboot_plan.py`
- 防线：`scripts/k3s/test_rolling_reboot_plan.py` 的 `RollingRebootPlanTests.test_default_dry_run_order_primary_last`、`test_scrambled_node_list_keeps_primary_last`（打乱清单后主库仍最后、切换在它之前）。另有工作日 `--execute` 拒绝且不调用 kubectl、`--allow-weekday` 先警告且第一步失败就停。
- 门禁：`python3 -m unittest scripts/k3s/test_rolling_reboot_plan.py` → 5 passed。`bash -n scripts/k3s/rolling-reboot.sh` → 通过。preflight 未拦截。本仓库没有覆盖这段 shell 的 `make lint` / `make test`。
- 验收：在该分支上 `bash scripts/k3s/rolling-reboot.sh --dry-run`。预期退出码 0，并打印 `order: ubt-k3s-05 ubt-k3s-06 ubt-k3s-01 ubt-k3s-02 ubt-k3s-04`，`switchover-before: ubt-k3s-04`，`switchover:` 出现在 `node 5/5 ubt-k3s-04 role=data-primary` 之前；`ubt-k3s-01` 那一步注明 API 中断约 10 秒。今天是美东周三，输出里 `live-window: closed`，这是 dry-run，不拒绝。
- 要 Owner 批：
  1. **自动更新配置（未应用）**。5 台 `/etc/apt/apt.conf.d/50unattended-upgrades` 的 Allowed-Origins 相同，建议加上 `-updates`。不要打开 `Automatic-Reboot`（ADR §7：重启是 D 级周末滚动，不是无人值守重启）。

```diff
 Unattended-Upgrade::Allowed-Origins {
 	"${distro_id}:${distro_codename}";
 	"${distro_id}:${distro_codename}-security";
+	"${distro_id}:${distro_codename}-updates";
 	"${distro_id}ESMApps:${distro_codename}-apps-security";
 	"${distro_id}ESM:${distro_codename}-infra-security";
 };
```

  2. **第一次周末滚动重启（D 级）**。分支合并后，美东周六或周日跑 `bash scripts/k3s/rolling-reboot.sh --execute`。非周末会被拒绝；`--allow-weekday` 会打印警告再继续，不要在没点头的情况下用。不要用 `make k3s-switchover-postgres-primary`：那个脚本默认把主库提升到 ubt-k3s-04，方向相反。
- 后续：
  - ubt-k3s-01 根盘 83%（剩 78G / 466G），不是这次不装包的原因，但控制面节点最紧。
  - ubt-k3s-05 正在跑的内核最旧（6.8.0-134）；5 台已安装的内核元包都是 6.8.0-142，候选 6.8.0-146 在 `noble-updates`，所以没装上、也没重启进 142。
  - .75 / .77 今早日志是 “No packages found”，下午 `apt list` 仍有带 `noble-security` 的行（4 与 5）。日志里没有 phased 字样，更像候选版本被记在 `-updates` 上，或列表在早间运行之后才更新。主因仍是 origins 不含 `-updates`。

### 调查表（一行一台）

| 节点 | IP | 内核（正在跑） | k3s | uptime | 根盘剩余 | reboot-required | pkgs | hold | 可升级 | 其中安全源 |
|---|---|---|---|---|---|---|---|---|---|---|
| ubt-k3s-02 | 192.168.10.70 | 6.8.0-139-generic | v1.35.5+k3s1 | 31 天 | 134G / 466G（70%） | 有，2026-09-12 06:40 UTC | libc6 | 无 | 61 | 1 |
| ubt-k3s-01 | 192.168.10.73 | 6.8.0-137-generic | v1.35.5+k3s1 | 55 天 | 78G / 466G（83%） | 有，2026-09-11 06:25 UTC | libc6 | 无 | 60 | 0 |
| ubt-k3s-04 | 192.168.10.75 | 6.8.0-137-generic | v1.35.5+k3s1 | 55 天 | 161G / 466G（64%） | 有，2026-09-11 06:34 UTC | libc6 | 无 | 64 | 4 |
| ubt-k3s-05 | 192.168.10.77 | 6.8.0-134-generic | v1.35.5+k3s1 | 55 天 | 161G / 466G（64%） | 有，2026-09-11 06:17 UTC | libc6（文件里两行） | 无 | 65 | 5 |
| ubt-k3s-06 | 192.168.10.79 | 6.8.0-137-generic | v1.35.5+k3s1 | 55 天 | 240G / 466G（46%） | 有，2026-09-11 06:48 UTC | libc6 | 无 | 60 | 0 |

gpu-server（192.168.10.60）未查：平时关机，本次 SSH `Host is down`。

安全源计数 = `apt list --upgradable` 里套件名含 `-security` 的行。`/boot` 各台约 1.6G 空闲（11%）。dpkg / apt 锁均无人持有。`apt-daily.timer` 与 `apt-daily-upgrade.timer` 都是 enabled，2026-10-07 都触发过。软件源列表是当天或前一天更新的（`us.archive.ubuntu.com`、`security.ubuntu.com`）。

### 为什么安全源以外的包不装

定时器在跑，网络通，没有 hold，没有锁。`20auto-upgrades` 里 `Unattended-Upgrade "1"` 也成立。日志写明允许的源只有：

`o=Ubuntu,a=noble`、`o=Ubuntu,a=noble-security`、`o=UbuntuESMApps,a=noble-apps-security`、`o=UbuntuESM,a=noble-infra-security`。

没有 `noble-updates`。`apt list` 里那大约 60 个包（含 `linux-generic` / `linux-image-generic` 6.8.0-146，from 6.8.0-142）全部来自 `noble-updates`。安全口袋清空时，日志就是 “No packages found that can be upgraded unattended”，同时更新口袋继续堆积。`Automatic-Reboot` 仍是注释掉的默认关闭，所以 09-11 的 libc6 重启旗标不会被自己清掉。这和 ADR §7 一致：重启留给周末滚动，不交给 unattended-upgrades。

### 滚动重启计划（dry-run，未执行）

1. ubt-k3s-05（general）
2. ubt-k3s-06（general）
3. ubt-k3s-01（唯一控制面，注明 API 中断约 10 秒）
4. ubt-k3s-02（PROD）
5. CNPG 把主库从 ubt-k3s-04 切走（`bifrost-postgres` / `data`）
6. ubt-k3s-04（数据库主库）最后

每台：cordon → drain（遵守 PDB，不用 `--disable-eviction` / `--force`）→ reboot → 等 Ready → uncordon → 核对该节点上的 Pod Ready。任一步失败即停。非美东周末 `--execute` 直接拒绝。
