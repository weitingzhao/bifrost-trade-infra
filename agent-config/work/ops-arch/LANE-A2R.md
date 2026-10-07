# LANE-A2R — A2 返工：etcd 快照也必须加密

在 `cursor/a2-infra`（`2e4f4172`）基础上继续，分支仍是 `cursor/a2-infra`（先 rebase 到 origin/main）。

## 为什么返工（Claude Code 验收，2026-10-07）

这台 k3s **没有开 Secret 静态加密**（`/etc/rancher/k3s/config.yaml` 无 `secrets-encryption`，k3s 进程参数也没有）。所以 etcd 快照里的 Secret 是明文。A2 把快照逐字节复制到 NAS（`backup.sh:147` 的 `cp`），等于把全部密码和令牌明文放上 NAS；NAS 对 Family 网段开放。「sha256 要和源一致，所以不能包 age」不成立：完整性可以在加密前核对。

## 要做

1. 快照与 Secret / ConfigMap / server token 一样，经 `age -r <公钥>` 加密后才落盘，文件名 `etcd-snapshot-…age`。NAS 上任何时候都不能出现未加密的快照，包括中间文件——加密直接从只读 hostPath 读、写到目标目录的临时名，校验通过后再改名。
2. 完整性：加密前算源文件 sha256 与大小，写进同目录的 `MANIFEST`（明文，只有文件名、大小、sha256、时间）；加密后校验 age 头。恢复手册改为「解密 → 对照 MANIFEST 的 sha256 → 再按 k3s 步骤恢复」。
3. 月度副本同样只复制密文 + MANIFEST。
4. 防线 `check_cluster_state_backup.py`：
   - 静态：脚本里任何写到目标目录的快照路径都必须经过 `age`；`--self-test` 加一例「明文 cp 快照到目标」必须失败；
   - `--live`：目标目录（只读）里不存在不以 `.age` 结尾的 `etcd-snapshot-*` 文件，且当天有 `MANIFEST`。
5. 运行时下载 age / kubectl 的 init 容器可以保留（报告里写明风险）；如果改为固定镜像更简单，也可以。

## 验收

- 分支上 `make check-cluster-state-backup` 与 `python3 scripts/check_cluster_state_backup.py --self-test` 通过；
- `grep -n "cp " k8s/data/cluster-state-backup/backup.sh` 里没有把快照写到目标目录的明文复制。

## 要 Owner 批

不变（apply + 手动触发一次），等这道验收通过后由 Claude Code 统一提交给 Owner。
