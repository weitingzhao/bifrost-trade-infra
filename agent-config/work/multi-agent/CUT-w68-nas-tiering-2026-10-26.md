# 切法：NAS 存储冷热分层（W-68 方案 B）与 SMART 盲区

起草 2026-10-26 21:50–22:10 CDT（统筹线程派出的子会话）。只读调研后写：没有登 NAS，没有改集群，没有改 Time Machine。
数据来源：Prometheus（NAS 的 node_exporter 自 10-24 起有数据，本文用 10-24 16:30 至 10-26 21:50 CDT，约 2.2 天，5 分钟和 2 分钟步长），
集群只读 kubeconfig（PV 列表、Pod 位置、CronJob 时间、`plugin-market-data` 里只读 `du`），本机 `tmutil` 和文件修改时间（只统计目录级大小，不读文件内容）。
SMART 那一半已经修好代码，等 Owner 推 infra 后在 NAS 重跑一步（第 3 节、TD-443）；分层这一半等 Owner 选（第 5 节、TD-444）。

## 0. 先说结论

1. **NAS 机械盘的 IO 八成来自本机的 Time Machine，不是集群。** 每小时一次、每次约 15 分钟（起始分钟逐次后移，正是 3600 秒备份间隔的样子），
   每次本机发过去中位 3.5 GB；这些突发占 RAID5 全部写入的 82%、盘忙时间的 79%。两次突发之间，集群自己让盘忙 3–5%。
2. **突发期间集群确实受害**：md1 的写延迟中位数从约 0.1 秒升到 **1.2 秒**（p90 1.4 秒），每个盘读等待从 20 ms 升到 82 ms，持续约 15 分钟、每小时一次。
   Prometheus 的 WAL、MinIO 的 WAL 归档、registry 拉镜像都在这块阵列上。
3. 所以「把集群的热数据挪到 SSD」（10-24 的方案 B 字面做法）只能让集群躲开噪声，噪声还在、Owner 听到的响声还在；
   **把 Time Machine 挪到 SSD，RAID5 的负载直接降到约 5%，集群零停机。** 推荐 A（第 5 节），分层的精神不变：热写放 SSD，冷数据留 RAID5，只是热的东西换了。
4. **SMART 看不见是 smartctl_exporter 0.14.0 的 bug**：建 SSD 存储池那一分钟起，exporter 读 NVMe 的「已写字节」时用了一个没注册的指标，整页 `/metrics` 返回 500，
   三块机械盘也跟着看不见。0.15.0 修了这个（上游 #329）。代码已改，Owner 推 infra 后在 NAS 重跑一次 `host-exporters.sh nas`（约 5 分钟，不停任何服务）。

## 1. 要做的事和边界

- 任务：`agent-config/WORK.md` 第 4 轮 4.9 与 W-68：NAS 装 SSD（`/volume2`，pool2，Btrfs，约 984 GB，10-24 装好），存储按方案 B 分层（Owner 10-24 定，承诺先出设计再动；第二块同款 SSD 以后可买，到时 SSD 池改镜像）；
  W-68「硬件到货」一条：装完写每晚把行情归档备份到新池的任务。
- 只出设计和诊断。NAS 上的操作由 Owner 做；集群上的改动按平时的规矩（清单进仓库、平台动作或 Owner 用管理员 kubeconfig）。
- 不在本文：异地副本（TD-218，SSD 和 RAID5 在同一台 NAS 里，不算异地）；Prometheus 在 NAS 整机停时卡住的问题（B4 切法 §6 已记）。

## 2. 实测

### 2.1 盘和卷

| 项 | 实测 |
|---|---|
| RAID5 `md1` | sda/sdb/sdc，3 × ST12000NM0127 12 TB；LVM 上 Btrfs `/volume1`，22 TB，**已用 1.35 TB**，两天净增约 14 GB |
| SSD `nvme0n1` | KINGSTON SNV3S1000G（NV3 1 TB，无 DRAM 的消费级盘），`md2` → `dm-1` → Btrfs `/volume2`，984 GB，已用 2.2 GB；pool2 建于 10-24 17:07:27 CDT（设备名里的时间戳 `1792879647`） |
| 网卡 | 只有 `eth0` 在用（`eth1` 0 流量），即 1 GbE 一条 |
| 本机 Mac | 数据卷已用 580 GiB；Time Machine 目标是 NAS 的 `TimeMachine` 共享（Network，配额 1.2 TB），间隔 3600 秒，不要求接电源 |

### 2.2 谁在写

| 来源 | 落在哪 | 量（实测） | IO 特点 |
|---|---|---|---|
| **本机 Time Machine** | `/volume1` 的 `TimeMachine` 共享（SMB） | 每小时一次，每次约 15 分钟，中位收 3.5 GB、最大 13 GB；按网卡算约 **115 GB/天收、84 GB/天发** | 突发时 md1 写 8–10 MB/s、450 次/秒、每次约 20 KB，队列 500–700，盘忙 50–57% |
| MinIO（Postgres 的 WAL 归档与每晚基础备份，跑在 NAS 本机 Docker） | `/volume1/k3s-hot/data-minio-data-pvc-871b…`（README：接管了原 NFS 目录） | 共 322 GB；收 0.1 MB/s；基础备份 03:00 UTC（22:00 CDT 那一小时网卡收 2.8 MB/s，全天最高） | 16 MB 段，顺序写为主 |
| Prometheus TSDB（04 上的 Pod，NFS） | `nfs-hot` 30Gi PV | 块 9.8 GB + WAL 0.39 GB；8.3k 样本/秒 | 04 的 NFS：每秒 0.4 次 Write、0.3 次 Commit、1.2 次 GetAttr |
| Alertmanager（02 上，NFS） | `nfs-hot` 1Gi | 很小 | — |
| registry（04 上，`registry:2`，NFS） | `nfs-cold` 200Gi PV | **大小没量到**（集群里不能进 `cicd` 的 Pod；要 NAS 上 `du`，只有方案 B 需要） | 约 30 个容器 `pull Always`，读为主 |
| 行情归档（`plugin-market-data/market-data-archive`） | `nfs-cold` 200Gi PV | **350 MB**，期权快照的 parquet，每天 02:15 UTC 追加一个文件，`_ledger.jsonl` 每行带 sha256 | 每天一次小写 |
| 逻辑备份、Gitea 备份、集群状态备份、Finance 备份 | `nfs-hot` / `nfs-cold` | 未单独量 | 每天一次，03:10–05:15 UTC |
| 01/02/05 的其余 NFS | — | 合计每秒不到 0.1 次 RPC | — |

两次突发之间（5 分钟窗口盘忙 ≤ 25% 的 462 个窗口）：盘忙 4.7%，md1 写 0.68 MB/s，网卡收 0.30 MB/s。这就是集群加 NAS 自身的全部常态负载。

为什么认定突发是 Time Machine：① 2.2 天里 52 次，每小时 0.97 次，间隔中位 60 分钟（40–85），起始分钟从 :00 逐小时后移到 :35 附近再回落，正是「上次结束后 3600 秒」的样子；
② 突发里网卡既收又发（收 3–5 MB/s，发 2–3 MB/s），是 SMB 上 sparsebundle 的读改写，集群的 NFS 和 S3 没有这么大的发；③ 统筹线程 10-26 21:32 现场看到 `tmutil` 在跑，同一时刻这里是一次突发的起点；
④ 21:56 突发结束时 `tmutil status` 是 `Running = 0`。没做的验证：暂停 Time Machine 一小时看突发消失（要 Owner 点，第 5.2 节 A1 之后自然就验证了）。

本机家目录 2 小时里改了 2.2 GB（不含已排除的 `~/agent-work`、`~/Library/Caches`、Docker 磁盘镜像），即每小时约 1.1 GB，大头：
`~/.codex` 1.1 GB（其中 `thread_history_1.sqlite` 489 MB 整份重写、`plugins` 362 MB、`computer-use` 75 MB、`cache` 51 MB）、
Chrome 资料 346 MB（`Service Worker/CacheStorage`、`Safe Browsing` 等）、Codex 应用 269 MB（`artifact-sessions/runtime-generations` 236 MB）、Grok 140 MB（`sand-update-kept`）、Claude 会话记录约 100 MB。
另有 `~/.cache` 7.4 GB、`~/.npm` 1.1 GB、各 worktree 的 `node_modules`（每份 80–336 MB）都在备份范围内。

### 2.3 突发对集群的影响

| 指标（6 小时，2 分钟步长） | 空闲时中位 | 突发时中位 | 突发时 p90 |
|---|---|---|---|
| md1 每次写的等待（所有客户端看到的） | 107 ms | **1216 ms** | 1376 ms |
| 单盘每次读的等待 | 20 ms | 82 ms | 95 ms |
| 单盘每次写的等待 | 4 ms | 7 ms | 8 ms |

`NodeDiskIOSaturation`（md1、dm-0 队列 > 10 持续 30 分钟）每晚都在 pending，10-26 21:52 时队列 351。

## 3. SMART 为什么一整天看不见（TD-443）

| 事实 | 读法 |
|---|---|
| `up{job="smartctl",host="nas"}` 自 10-24 17:07:00 CDT 起一直 0；06 的同一 exporter 正常 | 不是抓取配置的问题 |
| Prometheus 的错误：`server returned HTTP status 500`，8 毫秒返回 | 能连上、容器在跑，是采集时出错 |
| 直接读 `http://192.168.10.20:9633/metrics`：`collected metric smartctl_device_bytes_written label:{name:"device" value:"nvme0"} counter:{value:1.2288e+07} with unregistered descriptor` | 0.14.0 给 NVMe 报「已写字节」时用了没注册的描述；`promhttp` 默认 `HTTPErrorOnError`，一个指标出错整页 500 |
| NAS 16:26 开机（装 SSD），16:26–17:07 exporter 正常且已经报出 nvme0；17:07:27 建 pool2 | SSD 写了第一笔数据（12 288 000 字节）之后才触发；写入量为 0 时那条指标不出 |
| 上游 v0.15.0（2026-10-06 发布，已满两周）`[BUGFIX] Fix some 5xx errors from metrics endpoint #329`：PR 描述就是这条报错，改法是预先声明所有描述 | 升级可修 |

改动（本提交）：`scripts/host-exporters/nas/compose.yaml` 镜像改为 `quay.io/prometheuscommunity/smartctl-exporter:v0.15.0@sha256:a76e08db…`（quay 的 manifest list，10-26 读），
`versions.env` 同步到 0.15.0 和 linux-amd64 校验和 `32ff269f…`（06 下次重跑 `host-exporters.sh agent-06` 时也升，不急）。参数名 0.15.0 都还在（`--smartctl.interval`、`--smartctl.powermode-check`、`--web.listen-address`）。
`make check-host-exporters` 33 个测试通过。

剩下的风险：0.15.0 仍用 `HTTPErrorOnError`，以后再有一个指标出错照样整页 500。这一次 `BifrostNasSmartBlind`（critical）两小时后报了警，防线起了作用；
慢在没人去读 500 的正文。告警说明里已经写了去看日志的命令，这次补一句「先 `curl` 这个地址看正文」不值得单独改规则，等下次改 `bifrost-host-rules.yaml` 时顺带。

**Owner 步骤**（先推 infra main，再跑这一条；在终端面板里跑，sudo 会问一次 Wzhao 的 NAS 口令）：

```bash
git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra fetch -q origin && git -C /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra show origin/main:scripts/host-exporters/host-exporters.sh > /tmp/b4-host-exporters.sh && bash /tmp/b4-host-exporters.sh nas
```

做完会看到：`install-nas: OK (node_exporter :9100, smartctl_exporter :9633, N disks)`，N 至少 3，前面列出每块盘一行 `smartctl_device_smart_status`（三块机械盘，nvme0 报的话是 4 行）。只重建 smartctl-exporter 一个容器，node-exporter 定义没变不会动。
下一次抓取（1 分钟内）起 `up` 回到 1，`BifrostHostSmartExporterDown` 和 `BifrostNasSmartBlind` 随后几分钟内恢复（`for` 只管触发，不管恢复）。

## 4. 放哪里：判据

| 数据 | 丢了怎么办 | 对延迟敏感吗 | 放 SSD（目前单盘）合适吗 |
|---|---|---|---|
| Time Machine | 本机还在，只丢历史版本 | 不敏感，但它是 RAID5 噪声的来源 | **合适**：它本身就是副本；SSD 坏了重做一次全量 |
| Prometheus / Alertmanager | 丢监控历史，可接受 | 敏感（WAL fsync） | 合适，但单盘坏了监控也一起停 |
| registry | PROD 钉的镜像摘要拉不到，要重建、重核 | 拉镜像时敏感 | 只有带每晚回拷 RAID5 才合适 |
| MinIO（Postgres 备份） | 它就是备份；丢了要等下一次基础备份，期间没有 PITR | 不敏感（异步归档） | **不合适**：备份不该落到没冗余的盘上 |
| 逻辑备份、Gitea / 集群状态 / Finance 备份 | 同上 | 不敏感 | 不合适，留 RAID5 |
| 行情归档 | 期权快照从 Postgres 修剪后**唯一一份** | 不敏感 | 主份留 RAID5；**SSD 放每晚副本**（不同介质的第二份） |

SSD 寿命：NV3 1 TB 标称写入量是消费级水平（几百 TB 量级，具体以 `smartctl_device_percentage_used` 为准）。按 Time Machine 每天约 115 GB 收、写放大按 1.5 倍估，约 60 TB/年；
排除项做完会明显少于这个数。修好 SMART 后用 `percentage_used` 每月看一次，不靠估。

## 5. 选项

### 5.1 三个选项

| | A（推荐）：Time Machine 换到 SSD | B：集群热数据上 SSD（10-24 方案 B 字面） | C：A 加 Prometheus 上 SSD |
|---|---|---|---|
| 做什么 | 在 `/volume2` 建新的 Time Machine 共享（配额 600 GB），本机改备份到它；加排除项；集群数据全部不动；SSD 另放行情归档的每晚副本 | 在 `/volume2` 建 NFS 共享，Prometheus、Alertmanager、registry 搬过去；registry 每晚回拷 RAID5；Time Machine 留 RAID5，只加排除项 | A 全部，加上 B 里 Prometheus 和 Alertmanager 那一段 |
| RAID5 噪声 | 降到约 5% 忙度，小时一次的突发消失 | 还在（排除项能减一部分，量不准） | 同 A |
| 集群受的影响 | 写延迟回到约 0.1 秒（突发没了） | 搬走的三样不再受影响；MinIO 和备份仍受 | 同 A，Prometheus 还和机械盘彻底隔开 |
| 停机 | 集群 0；本机首次全量备份约 1.5–3 小时（期间最新的备份是切换前那一次） | Prometheus 约 15 分钟没监控；registry 约 5 分钟拉不了镜像（要持发布窗口） | Prometheus 约 15 分钟 |
| 风险落在哪 | Time Machine 历史在单盘上（本机是主份）；旧共享留着做回退 | registry 在单盘上，靠每晚回拷；Prometheus 单盘坏了监控停 | Prometheus 与 Time Machine 共用一块消费级 SSD |
| Owner 要做的 | UGOS 建共享约 10 分钟；本机设置约 5 分钟；2–4 周后决定删不删旧共享 | UGOS 建 NFS 共享；NAS 上拷数据两次；集群清单改动要批 | A 加 B 的 Prometheus 部分 |
| 能回退吗 | 能：本机把旧共享加回为备份盘，历史都在 | 能：旧 PV 是 Retain，数据留在原处 | 能 |

**推荐 A**：IO 的来源就是 Time Machine，挪走它，问题本身就没了；集群不停机、不改清单，回退只是在本机设置里换回备份盘。
B 只解决「集群被噪声拖慢」，代价是两次停机和把 registry 放上单盘。C 的增量（Prometheus 和机械盘隔离）在 A 之后收益很小；A 做完一周如果 md1 仍有成片的高延迟再考虑。
第二块 SSD 买来改镜像后，B / C 的单盘风险才消失，那时可以重新看要不要把 Prometheus 和 registry 挪上去。

关于 Time Machine 另外两种方式（评估了，不推荐）：
- **只降频率**（系统设置里改成每天一次）：RAID5 每天还是会响一次、一次更久；而且丢失窗口从 1 小时变 24 小时。A 做完后频率可以保持每小时。
- **改用本机外接的 USB 盘**：NAS 完全没负载，但盘要一直插着，本机移动时就断；且离开了 NAS 的快照与集中管理。

### 5.2 A 的步骤

| 步 | 谁、在哪 | 做什么 | 停多久 | 回退 |
|---|---|---|---|---|
| A0 | Owner，终端面板 | 先修 SMART（第 3 节的命令），这样搬过去之后能看到 SSD 的健康和磨损 | 不停 | `compose.yaml` 改回 0.14.0 重跑同一步 |
| A1 | Owner，本机终端面板 | 加排除项（下面的命令，不用 sudo，作用在目录属性上） | 不停 | `tmutil removeexclusion <路径>` |
| A2 | Owner，UGOS 网页 | 控制面板 → 共享文件夹 → 新建 `TimeMachine-SSD`，位置选**存储空间 2**；只给你自己的账户读写；在 SMB 设置里把它设为 Time Machine 目标，配额 **600 GB**（菜单名以 UGOS 实际为准，和现在的 `TimeMachine` 共享同样设置） | 不停 | 删掉这个新共享 |
| A3 | Owner，本机 系统设置 → 通用 → 时间机器 | 「添加备份磁盘」选 `TimeMachine-SSD`；首次全量开始后，把旧的 `TimeMachine` 从列表里**移除**（只是不再往那里备份，NAS 上的数据不动）。两个都留着时 macOS 会轮流备份，RAID5 一半时间还会响 | 本机首次全量约 1.5–3 小时（580 GiB 减排除项，1 GbE），集群不停 | 在同一页把旧 `TimeMachine` 加回、移除新的；旧历史接着用 |
| A4 | Agent，Prometheus | 首次全量结束 24 小时后按第 7 节核对，把结果写进 TD-444 | — | — |
| A5 | Owner，UGOS | 新盘上连续两周有每小时的备份、至少一次从新盘恢复过一个文件之后，再决定删不删旧 `TimeMachine` 共享（删了不可恢复，约释放 0.9 TB） | — | 删之前随时可回退 |
| A6 | Agent 写清单，Owner 在 UGOS 建共享 | 行情归档每晚副本（第 6 节） | 不停 | 删 CronJob |

A1 的命令（先跑第一条看清单，确认后再跑第二条）：

```bash
cd ~ && ls -d .cache .npm .codex/plugins .codex/computer-use .codex/cache .codex/.tmp .codex/logs_2.sqlite "Library/Application Support/Codex/artifact-sessions/runtime-generations" "Library/Application Support/Grok Bot/sand-update-kept" "Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage" "Library/Application Support/Google/Chrome/Safe Browsing" 2>/dev/null; find ~/Desktop/stocks -maxdepth 4 -type d -name node_modules -prune
```

```bash
cd ~ && for p in .cache .npm .codex/plugins .codex/computer-use .codex/cache .codex/.tmp .codex/logs_2.sqlite "Library/Application Support/Codex/artifact-sessions/runtime-generations" "Library/Application Support/Grok Bot/sand-update-kept" "Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage" "Library/Application Support/Google/Chrome/Safe Browsing"; do [ -e "$p" ] && tmutil addexclusion "$p" && echo "excluded $p"; done; find ~/Desktop/stocks -maxdepth 4 -type d -name node_modules -prune -exec tmutil addexclusion {} \; -exec echo "excluded {}" \;
```

没放进去、要你定的：`~/.codex/thread_history_1.sqlite`（489 MB，Codex 的会话历史，每次改动整份重备）。它在 SSD 上每小时重备不伤 RAID5，A 之后可以留着；
不想要这段历史的备份就单独 `tmutil addexclusion ~/.codex/thread_history_1.sqlite`。`node_modules` 被重新创建后排除会失效（属性跟着目录走），影响不大。

### 5.3 B 的步骤（选 B 或 C 时用）

1. **盘点（Owner，终端面板，只读，约 3–10 分钟）**：`ssh -t -o IdentitiesOnly=yes -i ~/.ssh/id_ed25519 Wzhao@192.168.10.20 'sudo du -xsh /volume1/k3s-hot/* /volume1/k3s-cold/* 2>/dev/null | sort -h'`，回贴最后 10 行（只有大小和目录名）。
2. **UGOS（Owner）**：在存储空间 2 建共享 `k3s-fast`，NFS 规则与 `k3s-hot` 相同（只给 `192.168.10.0/24`，读写，root 映射同 `k3s-hot`），确认 `/volume2/k3s-fast` 可以用 NFSv3 挂（`install-nfs-provisioner.sh` 的教训：每个挂载都写 `nfsvers=3,hard`）。
3. **预拷（Owner，NAS，服务照跑）**：`sudo rsync -aHAX --info=progress2 /volume1/k3s-hot/<prometheus 目录>/ /volume2/k3s-fast/<同名>/`，registry、Alertmanager 同样。约 10 GB + registry 实际大小，按 NAS 内部 100–150 MB/s 估。
4. **切换（每样一次，Owner 持发布窗口；Prometheus 先，registry 最后）**：
   ① 停：Prometheus 改 CR `replicas: 0`（helm values），registry `scale --replicas=0`；
   ② NAS 上同一条 rsync 再跑一次补差（加 `--delete`，只对目标目录）；
   ③ 删旧 PVC（PV 是 `Retain`，数据留在 `/volume1`，这就是回退的底）；
   ④ 建静态 PV：`nfs.server 192.168.10.20`、`path /volume2/k3s-fast/<同名>`、`mountOptions [nfsvers=3, hard]`、`storageClassName` 与 StatefulSet 模板里的相同（`nfs-hot` / `nfs-cold`，这样不用改不可变的 `volumeClaimTemplates`）、`claimRef` 指向原来的 PVC 名；
   ⑤ 起：控制器按模板重建同名 PVC，绑到预绑的 PV；核对 Pod 起来、`up` 恢复、TSDB 头块与 WAL 没报损坏。
   停的时间 = 补差 rsync + 起 Pod：Prometheus 约 10–15 分钟，registry 约 5 分钟。
5. **回退**：停 → 删新 PVC 与新 PV → 把旧 PV 的 `claimRef.uid` 清掉让它回到 Available、`claimRef` 指回原 PVC → 起。切换后新写的数据回退时丢（监控可接受；registry 回退前把新镜像 rsync 回去）。
6. **registry 的回拷**：NAS 上每晚把 `/volume2/k3s-fast/<registry 目录>` rsync 回 `/volume1/k3s-cold/registry-replica/`（不加 `--delete`），同第 6 节一样用 CronJob 核对。
7. 清单：静态 PV 进 `k8s/`（Prometheus 的放 `k8s/monitoring/`，registry 的放 `k8s/cicd/`），提交前 server dry-run。

## 6. 行情归档的每晚副本（W-68「硬件到货」那条）

Owner 10-17 定的是「每晚 UGOS 备份行情归档到新池」。实测后有一个更好核对的做法，两种都列：

| | ① 集群 CronJob 复制并核对（推荐） | ② UGOS「同步与备份」本地任务（10-17 定的） |
|---|---|---|
| 怎么做 | `plugin-market-data` 里一个每天 07:00 UTC 的 CronJob：只读挂归档 PVC，读写挂一个指向 `/volume2/archive-replica/market-data-archive` 的静态 PV；按 `_ledger.jsonl` 逐行，目标没有的文件就复制，然后两边都算 sha256 和账本比；**只加不删**；任何一个文件缺失或不符就退出 1 | Owner 在 UGOS 建每晚任务，源 `/volume1/k3s-cold/plugin-market-data-market-data-archive-pvc-f22ead15…`，目标 `/volume2/archive-replica/`，保留多版本、不同步删除 |
| 怎么知道它坏了 | `KubeJobFailed`，加一条「最近一次成功超过 30 小时」的告警（`kube_cronjob_status_last_successful_time`），走 `owner-ntfy`；平台动作 `create_job_from_cronjob` 能手动补跑 | 只在 UGOS 里看得到；Prometheus 不知道；副本是不是普通文件、能不能直接读，要试过才知道 |
| Owner 要做的 | UGOS 建共享 `archive-replica`（存储空间 2），开 NFSv3 给 `192.168.10.0/24` 读写；之后不用管 | 建共享和任务，之后每次看 UGOS |
| 时间 | 02:15 UTC 归档写完、03:00–05:15 UTC 各种备份之后 | 同左，按 NAS 本地时间设（11-01 起 CST，注意换算） |

清单放 `bifrost-platform-plugin-market-data/k8s/base/`（归档 PVC 在那里，CronJob 要在同一命名空间才能挂）；镜像用插件已有的镜像或一个钉摘要的小镜像，不新增外部依赖则用前者。
副本和主份在同一台 NAS 里，不解决 TD-218 的异地问题，但解决「唯一一份在一组盘上」。

## 7. 搬完怎么验证（A）

首次全量完成后 24 小时，Agent 用 Prometheus 只读查，结果写进 TD-444：

| 看什么 | PromQL | 现在 | 目标 |
|---|---|---|---|
| 一天里盘忙超 30% 的 5 分钟窗口数 | `count_over_time((rate(node_disk_io_time_seconds_total{host="nas",device="sda"}[5m]) > 0.3)[1d:5m])` | 约 80 | ≤ 5 |
| md1 一天里最差的写等待 | `max_over_time((rate(node_disk_write_time_seconds_total{host="nas",device="md1"}[5m]) / rate(node_disk_writes_completed_total{host="nas",device="md1"}[5m]))[1d:5m])` | 约 1.4 秒 | < 0.3 秒 |
| 突发换到了 SSD | `rate(node_disk_written_bytes_total{host="nas",device="nvme0n1"}[1h])` | 约 0 | 每小时有一段 |
| SSD 健康与磨损 | `smartctl_device_smart_status{host="nas",device="nvme0"}`、`smartctl_device_percentage_used{host="nas"}` | 看不到（TD-443） | 1；每月记一次 |
| md1 不再饱和 | `NodeDiskIOSaturation{host="nas"}` 不再每小时 pending | 每晚 pending | 无 |

Owner 那边：本机「时间机器」页显示最近一次备份在 `TimeMachine-SSD`、每小时一次；NAS 不再每小时响一阵。A5 之前从新盘恢复一个文件试一次。

## 8. 风险与没做到的

- 突发归因于 Time Machine 有四条旁证，没有做「暂停一小时看突发消失」的直接对照；A3 做完那一刻就是对照。
- registry 和几份备份的实际大小没量（只影响 B）。
- 消费级 QLC 类 SSD 连续大写超出缓存后会降速；首次全量 500 GB 级别可能遇到，降到几百 MB/s 仍快过 1 GbE，只影响时长。
- SSD 是单盘：A 下坏了只丢 Time Machine 历史和归档副本（主份都在），本机和 RAID5 不受影响。买第二块后改镜像（UGOS 存储池加盘转 RAID1，以 UGOS 实际支持为准，可能要重建池，那时再出步骤）。
- 0.15.0 仍然一错整页 500（第 3 节）；`BifrostNasSmartBlind` 兜底。

## 9. 要你定的

1. **分层选 A、B 还是 C**（推荐 A）。
2. **行情归档副本用 ① 集群 CronJob 还是 ② UGOS 任务**（推荐 ①；② 是 10-17 定的，选 ② 就按原定）。
3. `~/.codex/thread_history_1.sqlite` 要不要继续备份（推荐留着，A 之后不伤机械盘）。

回复格式：「NAS 分层 A，归档 ①，thread_history 留」之类即可。
