# 集群状态恢复（etcd 快照 + Secret 加密件）

这份备份是 ADR §9 的 1 级副本：k3s 唯一 server `ubt-k3s-01` 上的 etcd 快照，外加全部 Secret、`platform-state-*` ConfigMap、以及 k3s server token 的 age 密文。CronJob `kube-system/cluster-state-backup` 每天 05:15 UTC 把**当时最新的一份**快照复制到 PVC `cluster-state-backup`（`nfs-cold`）。

目录：

| 路径 | 内容 |
|------|------|
| `daily/<UTC 日期>/` | 当天成功的那一份。保留最新 30 天 |
| `monthly/<YYYY-MM>/` | 该月最后一次成功。保留最新 12 个月 |
| `<快照原文件名>` | etcd 快照的逐字节副本。`SHA256SUMS` 是它和源文件的 sha256 |
| `secrets.yaml.age` | 全部 Secret 的 YAML，写盘前已 age 加密 |
| `platform-state.yaml.age` | 名字匹配 `platform-state-*` 的 ConfigMap，同样加密 |
| `server-token.age` | `/var/lib/rancher/k3s/server/token` 的密文。换盘恢复时要它 |
| `MANIFEST` `STATUS` | 文件名、字节数、快照 sha256。没有 Secret 内容 |

RPO：k3s 默认每 12 小时在节点本地打一次快照（00:00 与 12:00，节点系统时区）。本作业每天只复制当时最新的那份。错过一天，NAS 上的副本最多旧约 36 小时。数据库的分钟级恢复仍走 Barman，不在这里。

私钥只在 Owner 自己的机器上。下面的 `IDENTITY` 是那份私钥文件的路径。不要把它拷进仓库、不要做成 Secret、不要放进集群。

## 风险（先读）

- **etcd 恢复是替换，不是合并。** `--cluster-reset --cluster-reset-restore-path` 会把当前 etcd 挪到 `${data-dir}/server/db/etcd-old-<时间>/`，再用快照里的内容启动。快照之后的集群变更（新 Secret、新发布、新 PV 对象）都没了。
- **只写 `--cluster-reset`、不写 restore path，不会恢复快照。** 它只把 etcd 成员重置成单节点。两条 flag 必须一起出现。
- 恢复过程中 API 不可用。这是单 server 集群，没有第二台 etcd。
- 节点上会留下 `/var/lib/rancher/k3s/server/db/reset-flag`。k3s 正常启动后会删掉它。它还在时，再跑一次 reset 会被拒绝。
- **NAS 上的快照文件本身没有 age 加密**（副本必须和源文件 sha256 一致）。k3s 文档写明：拿到快照就能抽出未加密的资源；快照再加 server token，可以抽出加密的 bootstrap 数据和集群 CA 私钥。NAS 上的这份和节点本地那份一样敏感。
- Secret / ConfigMap 的 YAML 才是密文。解密只在 Owner 的机器或正在恢复的那台主机上做，做完删掉明文。不要把明文写回 NAS。
- 快照里的版本不能比当前 k3s 老到无法直接升级（Kubernetes 版本偏差）。本集群实测 kubelet 为 `v1.35.5+k3s1`（2026-10-07）。
- PVC / PV 对象在 etcd 里，文件在 NAS 上（`nfs-cold` 是 Retain）。恢复到「这份 PVC 还不存在」的快照后，重新 apply 会得到一个**新**目录；旧目录还在 NAS 上，用下面的命令找路径，不要假设名字没变。
- 恢复到这份 CronJob 尚未 apply 的快照后，CronJob 会消失，需要再 apply 一次。
- 不要把整份 Secret 列表盲写回一个还在跑的集群。ServiceAccount token、helm release secret 会覆盖现在的值。先 `--dry-run=server`，再按命名空间和名字挑。

## 找到 NAS 上的目录

只读。PVC 还在时：

```bash
KUBECONFIG=~/.kube/bifrost-k3s.yaml
PV=$(kubectl -n kube-system get pvc cluster-state-backup -o jsonpath='{.spec.volumeName}')
kubectl get pv "$PV" -o jsonpath='{.spec.nfs.server}{" "}{.spec.nfs.path}{"\n"}'
```

`nfs-subdir` 的路径一般是 `192.168.10.20:/volume1/k3s-cold/kube-system-cluster-state-backup-<pv名>`。etcd 已经没了、PVC 对象也没了的时候，到 NAS 的 `/volume1/k3s-cold/` 下找这个前缀，进 `daily/` 或 `monthly/` 里日期最新且 `STATUS` 为 `OK` 的目录。

把要用的那份快照拷回 server 的快照目录（在 `ubt-k3s-01` 上，root）。拷的是快照文件，不是 `.age` 文件。

```bash
# 在 ubt-k3s-01 上。SRC 是 NAS 上那个日期目录，NAME 是目录里 etcd 快照的原文件名。
cp "$SRC/$NAME" /var/lib/rancher/k3s/server/db/snapshots/"$NAME"
( cd "$SRC" && sha256sum -c SHA256SUMS )
```

`sha256sum -c` 必须通过。对不上就不要恢复。

## 同一台机器上恢复 etcd

磁盘还在，`/var/lib/rancher/k3s/server/token` 还是打快照时的那把 token。不需要解密 `server-token.age`。

API 如果还活着，先手动留一份本地快照，这样这次恢复可以反悔：

```bash
k3s etcd-snapshot save --name before-restore
```

然后：

```bash
systemctl stop k3s
k3s server \
  --cluster-reset \
  --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<快照文件名>
```

等到这句再继续：`Managed etcd cluster membership has been reset, restart without --cluster-reset flag now.`

```bash
systemctl start k3s
```

确认 API 回来、节点 Ready 之后，再决定要不要从 `.age` 里补回快照之后才改过的个别 Secret。不要为了「保险」把整份 Secret 列表 apply 上去。

## 换一台机器（原盘没了）

快照里的加密 bootstrap 数据要用**打快照时的 server token** 才能解开。token 在 `server-token.age`。在新机器上解密到一个 600 的文件，用完就删。这是恢复过程里唯一应该出现明文 token 的地方，并且不在 NAS 上。

```bash
install -m 600 /dev/null /root/k3s-server-token
age --decrypt -i "$IDENTITY" -o /root/k3s-server-token "$SRC/server-token.age"
# 头一行必须是 age 密文被解开后的 token 文件。不要把这个文件拷走。
k3s server \
  --cluster-reset \
  --cluster-reset-restore-path=/var/lib/rancher/k3s/server/db/snapshots/<快照文件名> \
  --token="$(cat /root/k3s-server-token)"
```

看到 reset 完成的那句之后 `systemctl start k3s`（或按新机器的安装方式启动）。k3s 会把 token 写回 `/var/lib/rancher/k3s/server/token`。然后：

```bash
shred -u /root/k3s-server-token 2>/dev/null || rm -f /root/k3s-server-token
```

快照里还记着旧的 Node 对象。新机器的名字如果不是 `ubt-k3s-01`，API 回来之后删掉已经不存在的 Node。worker 用原来的 token 重新加入。

## 按命名空间恢复个别 Secret

在 Owner 的机器上做。明文只出现在管道里。`secrets.yaml.age` 解开后是一条 `kind: List`。

先看会碰到哪个对象（只打印 kind / namespace / name，不打印 data）：

```bash
age --decrypt -i "$IDENTITY" secrets.yaml.age | python3 -c '
import sys, yaml
for d in yaml.safe_load_all(sys.stdin):
    if not d:
        continue
    items = d.get("items") if d.get("kind") == "List" else [d]
    for item in items:
        if not item or item.get("kind") != "Secret":
            continue
        meta = item.get("metadata") or {}
        print("%s\t%s\t%s" % (item.get("type") or "", meta.get("namespace") or "", meta.get("name") or ""))
'
```

确认名字之后，只把一个 Secret 送进 API。先 dry-run：

```bash
NS=bifrost-prod
NAME=bifrost-postgres-app
age --decrypt -i "$IDENTITY" secrets.yaml.age | python3 -c '
import sys, yaml
ns, name = sys.argv[1], sys.argv[2]
for d in yaml.safe_load_all(sys.stdin):
    if not d:
        continue
    items = d.get("items") if d.get("kind") == "List" else [d]
    for item in items:
        if not item or item.get("kind") != "Secret":
            continue
        meta = item.get("metadata") or {}
        if meta.get("namespace") == ns and meta.get("name") == name:
            yaml.safe_dump(item, sys.stdout)
' "$NS" "$NAME" | kubectl apply --dry-run=server -f -
```

dry-run 的结果符合预期，再把同一条管道末尾换成 `kubectl apply -f -`。

不要恢复 `type: kubernetes.io/service-account-token`。那种 Secret 由控制器重新签发，旧值 apply 回去会把现在的 token 盖掉。

`platform-state.yaml.age` 是多份 ConfigMap 用 `---` 拼起来的，不是 List。把上面的过滤器里 `Secret` 换成 `ConfigMap` 即可。platform 状态 ConfigMap 可以按名字恢复；同样先 dry-run。

解密如果失败，先确认用的是 Owner 的那把私钥，以及文件头是 `age-encryption.org/v1`。头不对就不要当明文打开。

## 恢复之后

- `kubectl get node`，`ubt-k3s-01` Ready。
- 抽一个你刚恢复的 Secret，看它的 key 是否还在（不要把值打到终端历史里）。
- 若这份快照早于 CronJob：再跑一遍 `kubectl apply -k k8s/data/cluster-state-backup` 和告警那条 `kubectl apply -f`。公钥已经在清单的 ConfigMap 里。
- 告警 `BifrostClusterStateBackupStale` 看的是 CronJob **调度成功**的时间，手动 Job 不会清掉它。等次日 05:15 UTC 的调度成功，或接受它在第一次调度成功之前没有序列。
