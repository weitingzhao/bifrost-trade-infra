# 存储的真实上限（2026-09-25 实测）

> 这份文档回答一个问题：**哪个数字真的会拦住我们？** 写它的起因是 Research 转来的 O2
> —— CNPG 上写着 `spec.storage: 30Gi`，而那个数字不生效。查下去发现真正贴着上限的
> 既不是数据库也不是构建工作区。

## 结论先说

| 声明的限额 | 生效吗 | 真实上限 |
|---|---|---|
| CNPG `spec.storage: 30Gi` | **不生效** | 节点根分区 465 GB |
| 构建工作区 PVC `5Gi` ×N | **不生效** | 同上 |
| `nfs-hot` / `nfs-cold` 的 PVC size | **不生效** | NFS 导出的可用空间 |

三个 storage class 没有一个强制配额：

- **`local-path`**（`rancher.io/local-path`）：hostPath provisioner，`allowVolumeExpansion` 未开，
  **PVC 的 size 只是一个数字**。所以 `kubelet_volume_stats_*` 报的是**整个节点根分区**而不是这个 PVC
  —— 拿它当「库卷用了多少」会差两个数量级。
- **`nfs-cold` / `nfs-hot`**（nfs-subdir-external-provisioner）：只是在 NFS 导出上建一个子目录，
  size 同样是建议值。`allowVolumeExpansion: true` 是真的，但没有配额可扩。
- **没有任何 CSI 驱动**（`kubectl get csidrivers` 返回空）。

硬件：`.70` / `.75` 各一块 512 GB NVMe，`/dev/mapper/ubuntu--vg-lv--0` 一个 465 GB 逻辑卷挂 `/`，
加 `/boot` 2 GB 与 `/boot/efi` 1.1 GB 基本分完 —— **没有第二块盘、没有独立数据分区、VG 里没有可切的空闲 extent**。

## 实际占盘的是容器镜像缓存，不是数据

2026-09-25 在 `ubt-k3s-04`（Postgres 副本节点）干读：

```
/                                          465 GB 总 · 343 GB 已用 · 78%
  containerd 镜像缓存                       283.8 GB   ← 已用的 83%
  local-path 全部卷                          32.4 GB   ← 其中 Postgres 副本约 29 GB
    └ 37 个构建工作区实际合计                 约 3 GB   ← 而它们请求了 135 Gi
  /var/log                                   1.2 GB
```

**593 个镜像在一个节点上**：`bifrost-research` 167 个 tag、`bifrost-market-data` 134 个、
worker 46、platform-api 40、console 33、frontend 31……每个构建过的版本都还留着。
k3s 的 kubelet image GC 默认 85% 触发、降到 80% 停，所以节点会稳定停在 78% 上下晃，
**剩余空间的锯齿形状就是这个**，不是数据库在长。

`crictl --timeout=10m rmi --prune` 之后五个节点共回收约 **924 GB**（按剩余空间前后差）：

| 节点 | 已用（前 → 后） | 剩余（前 → 后） | 镜像 |
|---|---|---|---|
| **ubt-k3s-02（PG 主库）** | 310 → 72 GB（71% → 17%） | 142 → **398 GB** | 570 → 29 |
| ubt-k3s-04（PG 副本） | 343 → 102 GB（78% → 23%） | 100 → **363 GB** | 593 → 43 |
| ubt-k3s-05 | 284 → 50 GB（65% → 12%） | 159 → **392 GB** | 645 → 43 |
| ubt-k3s-01（registry） | 287 → 183 GB（65% → 42%） | 156 → **259 GB** | 294 → 22 |
| ubt-k3s-06 | 85 → 17 GB（20% → 4%） | 357 → **426 GB** | 300 → 20 |

主库在 2026-09-26 13:53 UTC 的安静窗口做（夜跑批次已结束、当天的排程报告已跑完、
`node_load5` 0.92、复制延迟 0.003 s）。**prune 期间复制延迟 0.003 → 0.020 s**，
`load5` 瞬时升到 4.17 后回落；零异常 pod、零 ImagePullBackOff、CNPG 全程 healthy 2/2。
**运行中的容器不受影响** —— `rmi --prune` 只删没有任何容器引用的镜像。

⚠️ 副作用：副本数为 0 的 Deployment（例如 `workers`、STG 的 `daemon`）其镜像没有容器引用，
会被删掉，**下次扩容时要从 registry 重拉**，首次启动慢一些。

⚠️ `crictl rmi --prune` 的输出里会刷一批 `DeadlineExceeded` —— 那是**客户端**等不下去，
containerd 在后台把删除做完了。**不要据此以为失败**，过一会儿再量 `df`。
默认单次调用超时是 2 秒，所以要带 `--timeout`。

### 两个衍生发现

1. **`Deployment/registry` 没有任何持久卷** —— 19 个 repo 的镜像全在 pod 的可写层里
   （containerd snapshotter），pod 自 2026-06-17 起没重启过。这既是 `ubt-k3s-01` 上
   prune 后仍有 158 GB 的原因，也意味着**这个 pod 一旦重建，所有 tag 全部消失**。待处理。
2. **Tekton 没有 pruner**（`config-defaults` 还是出厂示例块，没有 TektonConfig CRD）。
   2026-09-25 有 115 个 PipelineRun、其中 81 个是当天建的。对象会无界堆积（etcd），
   但**它们占的磁盘极小**（工作区实际约 3 GB）—— 清它们是为了对象卫生，不是为了空间。

## O2 的决定（2026-09-25，Owner）

**降级为文档与待办。** 理由：库 29 GB 在 465 GB 盘上，离任何上限都很远；
而配额防的是「数据库涨爆卷」，实际发生的是「镜像缓存吃掉节点」，**方向不一样**。
为一个没发生的风险做一次活库迁移不值得。

**以后加存储时再做**，那时一起做完这三件：

1. 换一个真有配额、可扩容的 storage class。当前硬件上没有可换的目标 ——
   TopoLVM / OpenEBS-LVM 需要 VG 里有空闲 extent（现在没有，要加盘）；
   Longhorn 的副本仍落在同一个 465 GB 根分区且要 2–3 倍空间；
   **NFS 不要用于 Postgres 数据**（fsync 语义与锁，且这个库一天产约 15 GB WAL）。
2. 把 WAL 拆到独立的 `walStorage`（现在 `walStorage: null`，WAL 与数据同卷）。
   在 local-path 上拆没有意义 —— 两边都不强制限额；等换了 class 一起做。
3. CNPG 不支持原地改 `spec.storage.storageClass`，要走「新 Cluster 从备份 bootstrap 再切换」
   或逐个副本重建，**需要一个切换窗口**。

## 现在靠什么兜底

`k8s/monitoring/bifrost-alerting-rules.yaml` 里 2026-09-25 加的四条（全部实测过表达式）：
`BifrostPostgresNodeDiskLow`（根分区 < 50 GB）、`BifrostPostgresDatabaseGrowth`（7 天涨 > 8 GB）、
`BifrostPostgresWalArchiveStalled`、`BifrostPostgresWalRetainedBySlot`。

⚠️ **Alertmanager 的 `default` receiver 没有配置**，路由只有 `alertname=~"Bifrost.*"` 一条。
所以 kube-prometheus-stack 自带的 `NodeFilesystemAlmostOutOfSpace` 等**全部被静默丢弃** ——
不要把它们当兜底。新规则必须以 `Bifrost` 开头才会被路由。
