## LANE-A2

- 事实：成立。k3s 只有 `ubt-k3s-01`（实测标签 `kubernetes.io/hostname=ubt-k3s-01`，kubelet `v1.35.5+k3s1`，**当前没有 taint**）。etcd 快照只在该节点本地。开工时的任务书要求 ConfigMap 用占位 `AGE_RECIPIENT`。创建 worktree 时 `origin/main` 已是 `470a14e197b68bacc39a062f7867bf5461e39097`（`agent-config: LANE-A2 gets the Owner's age public key`），车道文件改为「已用占位的分支请换成」公钥 `age10s4l6p55wh22gsmr3ga40lad7269hn8yt356m5kuhcyg67c80ayqutqxkf`。清单里写的是这把公钥，不是占位。私钥没有生成、没有读取、没有进仓库。
- 改动：`bifrost-trade-infra` · 分支 `cursor/a2-infra` · `2e4f4172fbeb0920c8e0a07147f1a8d2289ad36e`（父提交 `470a14e197b68bacc39a062f7867bf5461e39097`）。已推 `origin/cursor/a2-infra`，没有推 main。worktree `/tmp/cursor-a2-infra` 已删除。
  - `k8s/data/cluster-state-backup/`：CronJob `kube-system/cluster-state-backup`，`15 5 * * *`（Etc/UTC），`nodeSelector kubernetes.io/hostname=ubt-k3s-01`，control-plane 与 master 的 NoSchedule toleration；只读 hostPath `/var/lib/rancher/k3s/server/db/snapshots` 与 `/var/lib/rancher/k3s/server/token`；PVC `cluster-state-backup`（`nfs-cold`，30Gi，RWX）；ServiceAccount + ClusterRole 只有 secrets 与 configmaps 的 get/list；ConfigMap `cluster-state-backup-recipient` 的 `data.recipient` 是上面的公钥。`backup.sh` 把 Secret YAML、`platform-state-*` ConfigMap YAML、server token 经管道送进 `age -o`，失败或头不合法就删掉半成品；快照是逐字节副本（大小 > 0 且 sha256 与源一致）。每日目录留 30 份，每月目录留 12 份。
  - `k8s/monitoring/bifrost-cluster-state-rules.yaml`（新文件）：`BifrostClusterStateBackupStale`，`kube_cronjob_status_last_successful_time{namespace="kube-system",cronjob="cluster-state-backup"}` 超过 129600 秒（36h）。没有改 `bifrost-alerting-rules.yaml`，没有改 LANE-A1 的 `scripts/k3s/values-kube-prometheus.yaml` 和 `scripts/check_alert_routing.py`。
  - `docs/runbooks/cluster-state-restore.md`：`--cluster-reset --cluster-reset-restore-path` 的步骤和风险；换盘时解密 `server-token.age`；Secret 解密后按命名空间 / 名字选择性恢复。
  - `scripts/check_cluster_state_backup.py`。`Makefile` 只加了一行 `check-cluster-state-backup`（没有改 `.PHONY`）。`k8s/monitoring/kustomization.yaml` 加了一行资源。
- 防线：`scripts/check_cluster_state_backup.py`（`make check-cluster-state-backup`）。静态：CronJob 在、用 age、PVC 是 `nfs-cold`、脚本里没有把 Secret/ConfigMap YAML 或 token 重定向落盘、公钥是车道公布的那一把、告警表达式含 36h 指标、恢复手册含两条 k3s flag。`--self-test` 会抓住「kubectl 重定向到 .yaml」和出现 key 生成字样。`--live` 只读：最新成功 Job < 36h，且 backup 容器日志里有当天 UTC 的 `verified daily/<date> snapshot_sha256=ok age_header=ok`（这行只在 sha256 与 age 头都通过、目录已经就位之后打印）。不打印日志正文。
- 门禁（退出码分开记；infra 没有 `lint` / `test` 目标）：
  - `make lint` → 退出码 2（`No rule to make target 'lint'`）
  - `make test` → 退出码 2（`No rule to make target 'test'`）
  - `make check-cluster-state-backup` → 退出码 0，`cluster-state-backup: cronjob, age, nfs-cold, no plaintext-to-disk step`
  - `python3 scripts/check_cluster_state_backup.py --self-test` → 退出码 0，`self-test ok`
  - `python3 scripts/check_cluster_state_backup.py` → 退出码 0（同上；本机 Homebrew python3 没有 PyYAML，脚本会改用 `/usr/bin/python3`）
  - `sh -n k8s/data/cluster-state-backup/backup.sh` → 退出码 0
  - `sh -n k8s/data/cluster-state-backup/fetch-tools.sh` → 退出码 0
  - `ruff check scripts/check_cluster_state_backup.py` → 退出码 0
  - `kubectl kustomize k8s/data/cluster-state-backup` → 退出码 0（PVC `nfs-cold`，ClusterRole 只有 get/list，recipient 长度 62）
  - 本地用假的 kubectl/age 跑过 `backup.sh`：占位收件人在调用 kubectl 之前退出；age 把明文写进 `-o` 时头校验会删文件，磁盘上不留 `PLAINTEXT`；合法头则写出当日目录和当月目录，快照 sha256 与源一致。用官方 age 1.3.2（darwin arm64，只加密、不生成私钥）对这把公钥加密一行测试文本，文件头是 `age-encryption.org/v1`。
  - `KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_cluster_state_backup.py --live` → 退出码 1，`no successful cluster-state-backup Job`。集群里还没有这个 CronJob，这是 apply 之前的预期。
- 验收：
  - 分支上：`make check-cluster-state-backup` → 退出码 0，输出含 `cronjob, age, nfs-cold, no plaintext-to-disk step`
  - Owner apply 且手动 Job 成功之后：`KUBECONFIG=~/.kube/bifrost-k3s.yaml python3 scripts/check_cluster_state_backup.py --live` → 退出码 0，输出含 `live success is under 36h and today's files were verified`
- 要 Owner 批：下面这组是 apply（含把公钥写进 ConfigMap）和手动触发。不要跑 `age-keygen`，不要把私钥放进集群或仓库。在 `bifrost-trade-infra` 的 `cursor/a2-infra`（或合并之后的树）里执行。**不要** `kubectl apply -k k8s/monitoring`：本分支的 kustomization 仍列入 `td-d2-postgres-rules.yaml`，而 `origin/main` 的 `3791768` 已把它移出 kustomization（告警会立刻响）。告警只用单文件 apply。

```bash
export KUBECONFIG=~/.kube/bifrost-k3s.yaml

kubectl apply -k k8s/data/cluster-state-backup

kubectl -n kube-system create configmap cluster-state-backup-recipient \
  --from-literal=recipient='age10s4l6p55wh22gsmr3ga40lad7269hn8yt356m5kuhcyg67c80ayqutqxkf' \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f k8s/monitoring/bifrost-cluster-state-rules.yaml

JOB=cluster-state-backup-manual-$(date +%s)
kubectl -n kube-system create job --from=cronjob/cluster-state-backup "$JOB"
kubectl -n kube-system wait --for=condition=complete "job/$JOB" --timeout=1800s
kubectl -n kube-system logs "job/$JOB" -c backup
```

  第一条 `apply -k` 已经带上同一把公钥；第二条是显式再写一次 ConfigMap，值和清单相同。`wait` 成功之后日志里应有 `verified daily/<UTC 日期> snapshot_sha256=ok age_header=ok`，且没有 Secret YAML。
- 后续：
  - 合并时 `k8s/monitoring/kustomization.yaml` 会和 `origin/main` `3791768` 冲突（本分支在 `td-d2-postgres-rules.yaml` 那一行后面加了 `bifrost-cluster-state-rules.yaml`；main 把 td-d2 那一行换成了注释）。解法：保留 main 的注释，不要把 `td-d2-postgres-rules.yaml` 加回去，只保留 `bifrost-cluster-state-rules.yaml`。分支基线是 `470a14e`，当前 `origin/main` 是 `56a877a65e429a7c1bc477631c5afb8a4c24cda8`。Makefile 那一行在 main 上没有改过。
  - `BifrostClusterStateBackupStale` 用的是 CronJob **调度**成功时间。`kubectl create job --from=cronjob` 不会更新这个指标。第一次 05:15 UTC 调度成功之前，这条告警没有序列、不会响；手动成功只能让 `--live` 通过。
  - init 容器每次从 GitHub 拉 age v1.3.2、从 `dl.k8s.io` 拉 kubectl v1.35.5（校验 sha256 之后才留下 `age` 二进制，不留下 key 生成器）。节点出网被掐时 Job 会在 init 失败。
  - 快照文件在 NAS 上是明文副本（sha256 必须和源一致，不能再包一层 age）。Secret YAML 才是密文。k3s 文档：快照加 server token 可以解开 CA 私钥，所以 token 也经 age 再落盘；这是车道原文「复制快照 + 导出 Secret/ConfigMap」之外多出来的，换盘恢复需要它。hostPath 类型是 File，路径若不是 `/var/lib/rancher/k3s/server/token`，Pod 起不来。
  - `ubt-k3s-01` 实测无 taint；toleration 是为了以后加上 control-plane:NoSchedule 仍然能调度。
  - 无新的技术债编号。台账未改。
