# 切法：W-68 B4 ① 集群外机器的主机监控与失联告警（第 4 轮 4.9）

起草 2026-10-24 00:00–01:30（统筹线程派出的子代理）。只读调研后写：没有 apply、没有在任何主机上装东西、没有建审批单。
清单和脚本在 infra 分支 `w31/r4-w68-b4`（未推送）。Owner 要跑的命令在 `OWNER-STEPS-w68-b4-2026-10-24.md`。

## 1. 要做的事（Owner 2026-10-17 定）

- B4 = 集群外机器的统一监控与管控，分五片；本切法只做 **① 06、NAS、两台 mini 报数，加「主机失联」和硬盘告警，配一个全机房面板**。
- 监控就用现有的 kube-prometheus-stack（Prometheus / Alertmanager / Grafana，`monitoring` 命名空间）加社区报数程序，不另起第二套。
- 验收（台账 B4 行）：**集群外任何一台坏了 3 分钟内手机知道；NAS 坏盘当天知道；Gitea 不可用也有告警**。台账写 Owner 的部分「在 06、NAS、两台 mini 上装包，约 45 分钟」。
- 依据：台账 Claude Doc（`https://claude.ai/artifact/Kb5jJTGhoSJCtdvs4ZKMJM`，B4、B3 两行，10-24 读）、`agent-config/WORK.md` W-68 节和下面的实测。
  咨询线程笔记 `PLAN-w68-redundancy-2026-10-17.md` / `redundancy-map-draft.md` **本机已找不到**：`side-session-notes/` 下没有 `local_728a47ff-…` 目录（10-24 00:05 查；按文件名全盘 find 也没找到，macOS 受保护的目录除外）。

## 2. 现状（2026-10-24 实测，全部只读）

### 2.1 Prometheus 怎么发现抓取目标

| 项 | 实测 |
|---|---|
| 栈 | helm `kube-prometheus-stack` chart 88.1.3（`scripts/k3s/values-kube-prometheus.yaml`），operator v0.93.0（CRD 0.92.1），Prometheus v3.13.2 单副本在 ubt-k3s-04，`scrapeInterval` / `evaluationInterval` 都是 30s |
| 选择器 | Prometheus CR 的 ServiceMonitor / PodMonitor / Probe / **ScrapeConfig** / PrometheusRule 选择器都是 `release: kube-prometheus-stack`，命名空间不限；**没有 additionalScrapeConfigs** |
| 集群外目标 | 只有一个：ScrapeConfig `bifrost-minio-nas`（NAS 上 MinIO 的 `:9000`，静态目标，`job="scrapeConfig/monitoring/bifrost-minio-nas"`，up=1） |
| 节点报数 | node-exporter DaemonSet `v1.12.1-distroless`，5 个目标：01/02/04/05 up，gpu-server（.60，睡眠）up=0。06 出集群前最后一个样本 10-17（Prometheus 保留 10 天，还读得到它的磁盘：一块 SATA SSD `sda`，LVM ext4 根 500 GB） |
| 现成规则 / 面板 | 图表自带的 node-exporter 规则和 Grafana 面板「Node Exporter / Nodes」「Node Exporter / MacOS」都按 `job="node-exporter"` 选（包括 `NodeRAIDDegraded` critical 15m、`NodeFilesystemAlmostOutOfSpace` critical 3%） |
| 谁管这些清单 | `k8s/monitoring/` **不归 Argo**：7 个 Application 的路径（`overlays/platform-{stg,prod}`、`overlays/{stg,prod}`、research `k8s`、finance 两个）都不含它，kustomization 头注释也这么写。过去由 Owner 用管理员 kubeconfig 单文件 `kubectl apply`；W33B 以后也能走平台 `plan_manifest` / `apply_manifest`（actuation-policy 允许 `k8s/monitoring`；ScrapeConfig 是 TD-275 专门加的种类；monitoring 是 C 级，Owner 在 Console 批） |
| 告警怎么到手机 | `severity="critical"` 和几条备份告警走 `owner-ntfy`（.50 的 operator-plane `:8783`，`ALERT_RELAY=on` 只在 .50），同时进 PROD webhook；warning 只进 webhook。推送标题是 `CRITICAL <summary>` / `RESOLVED <summary>`，同一告警同一状态 30 分钟内只推一次。Watchdog 每 5 分钟送心跳，15 分钟没心跳 .50 自己呼叫 |
| Prometheus 自己的数据 | Prometheus 和 Alertmanager 的卷都在 `nfs-hot`，即 **NAS 上的 NFSv3、`hard` 挂载** |

### 2.2 四台机器

| 机器 | 系统 | 磁盘 | 现在有没有报数 | 谁能登、能做什么 |
|---|---|---|---|---|
| agent-06 `192.168.10.79` | Ubuntu 24.04（内核 6.8.0-146），x86_64 | 1 块 SATA SSD（型号 `SSD_512GB`），无 RAID | 没有：9100 没在听（10-24 从 Mac Pro 测，22 通） | `vision` 免密 sudo，只认 Owner 的节点钥匙（Agent 登不上）。nftables 只有出站链（管两个 agent 用户），**没有入站过滤** |
| nas `192.168.10.20` | UGOS（Debian 12），内核 6.18.15，8 核，7.4 GB | **RAID 5 `md1` = sda2+sdb2+sdc2**，3 × Seagate ST12000NM0127 12 TB，`[3/3] [UUU]`；LVM 上 btrfs `/volume1` 22 TB 用了 6%；系统在 58 GB eMMC，根是 overlay | 只有 MinIO 的 :9000。没有 snmpd；`/sbin/smartctl` 在（要 root）；Docker Engine 29.6.2，数据目录 `/volume1/@docker` | `k8s_admin`（Agent 的 `~/.ssh/id_ed25519` 能登，只读查了上面这些）：sudo 要口令，免口令只有 minio 的 4 条 compose 命令。`/volume1/docker` 和 `/home/k8s_admin` 都是 777 |
| mini-50 `192.168.10.50` | macOS 26.5.1，arm64，16 GB | 一块板载 SSD（251 GB） | 没有 | `vision` 是 admin，Agent 能只读 SSH。Homebrew 在；系统防火墙关；**FileVault 开、自动登录被禁**；operator-plane 和 peer-watchdog 是 `gui` 域的 LaunchAgent；`pmset autorestart 1` |
| mini-52 `192.168.10.52` | 同上 | 同上 | 没有 | 同上；**`pmset autorestart 0`**（停电来电后不会自己开机） |

### 2.3 网络

四台和集群节点都在 `192.168.10.0/24`，Pod 出集群走节点地址（flannel masquerade），是同一网段内的二层流量，**不经过 UniFi 的区间防火墙，不用加规则**。
证据：Prometheus 抓 NAS `:9000` 是 up；Alertmanager 能送到 `.50:8783`；从 Mac Pro（有线口同在 Server 网段）连 `.79:22` 通，9100 / 9633 不通只因为还没人在听。
以后 06 搬进单独的 Agent VLAN（`CUT-agent-host-06-2026-10-17.md` 第 3 节 C 段）时，要加一条 Server → Agent 的 tcp 9100、9633 放行。

## 3. 每台用什么报数

版本统一钉在 `scripts/host-exporters/versions.env`（NAS 用镜像 digest）：node_exporter 跟集群 DaemonSet 同一版 **1.12.1**；smartctl_exporter **0.14.0**（0.15.0 是 10-07 才出的）。

| 机器 | 选的做法 | 为什么，放弃了什么 |
|---|---|---|
| agent-06 | 官方 release 包（校验 sha256）装到 `/usr/local/bin`，两个 systemd 服务：`node-exporter`（专用系统用户，`:9100`）、`smartctl-exporter`（root、能力只留 `CAP_SYS_RAWIO`/`CAP_SYS_ADMIN`，`:9633`）；`smartmontools` 从 Ubuntu 装 | Ubuntu 自带的 `prometheus-node-exporter` 是 1.7.x，和集群不同版，升级跟着发行版走、谁升级说不清 |
| nas | UGOS 的 Docker：`/volume1/docker/host-exporters/compose.yaml` 起两个容器（node_exporter 只读挂 `/proc`、`/sys`、`/`；smartctl_exporter 特权、root），镜像按 digest 钉死 | **SNMP**：UGOS 上没有 snmpd，要另配 snmp_exporter 和 MIB，RAID / SMART 也不一定报，放弃；**直接装在系统里**：根是 overlay，UGOS 升级可能抹掉，放弃；**cron 跑 smartctl 写文本文件**：同一个问题。MinIO 从 10-06 起就是这样跑在 NAS 的 Docker 里 |
| mini ×2 | 官方 darwin-arm64 包装到 `~/bifrost-agent/node-exporter/<版本>/`，用户级 LaunchAgent `com.bifrost.node-exporter`，**不要 sudo** | `brew install node_exporter` 也不要 sudo，但版本跟着 `brew upgrade` 走，钉不住。mini 不做 SMART：板载单盘，坏了就是整机 HostDown，磨损慢，以后再看 |

放在哪里听：每个报数程序只绑本机局域网地址（`192.168.10.x:9100` / `:9633`），和集群 DaemonSet 绑 `HOST_IP` 一样。

## 4. SMART 与 RAID 怎么报

- **RAID**：node_exporter 读 `/proc/mdstat`（`node_md_disks{device="md1",state=…}`、`node_md_disks_required`），图表自带的 `NodeRAIDDegraded`（critical，15 分钟）和 `NodeRAIDDiskFailure`（warning）直接覆盖 NAS，因为 job 标签就是 `node-exporter`。不另写重复的规则。
- **SMART**：smartctl_exporter 每 60 秒跑一次 `smartctl --json`，默认不唤醒休眠的盘（`--smartctl.powermode-check standby`）；NAS 用自动扫描，M.2 SSD 装上之后自己出现。
- 「NAS 坏盘当天知道」由下面几条一起兑现：SMART 判定失败 5 分钟、读不出的扇区 10 分钟、阵列少盘 15 分钟、盘从系统里消失 25 分钟，都是 critical，都推到手机。

## 5. 抓取配置、告警和面板

### 5.1 文件（都在分支里，未应用）

| 文件 | 内容 |
|---|---|
| `k8s/monitoring/bifrost-hosts-external.yaml` | ScrapeConfig `bifrost-hosts-node`（4 个 `:9100`，`jobName: node-exporter`，标签 `scope="external"`、`host=agent-06/nas/mini-50/mini-52`，30s）和 `bifrost-hosts-smartctl`（06、NAS 的 `:9633`，`jobName: smartctl`，60s） |
| `k8s/monitoring/bifrost-blackbox.yaml` | Gitea 探针：blackbox_exporter v0.28.0（digest 钉死，非 root、只读根、去掉全部能力，优先不放控制面节点）+ ConfigMap + Service + ScrapeConfig `bifrost-gitea-probe`（每 30 秒 GET `/api/healthz`，走 NodePort `.73:30300` 和 Service 两条路） |
| `k8s/monitoring/bifrost-host-rules.yaml` | PrometheusRule，三组 13 条（见 5.2） |
| `k8s/monitoring/grafana-dashboard-hosts.yaml` | 面板「Bifrost Hosts」（uid `bifrost-hosts`）：所有机器的可达、开机时长、文件系统、内存、CPU、RAID 缺盘数、SMART 表、Gitea 探针；链到两个自带的主机面板 |
| `k8s/monitoring/rule-tests/host-rules.test.yaml` | promtool 单测：失联时序、集群节点不触发、目标少一个、SMART 失败 / 坏扇区 / 掉盘 / 预失效位、Gitea 一条路失败 |
| `k8s/monitoring/kustomization.yaml` | 加上面 4 个文件 |
| `scripts/host-exporters/` | `versions.env`、`install-linux.sh`（06）、`install-mac.sh`（mini）、`nas/compose.yaml` + `nas/install-nas.sh`、`host-exporters.sh`（Owner / 统筹线程的入口，子命令 `mini 50|52`、`agent-06`、`nas`、`cluster`、`check`）、`test_host_exporters.py` |
| `Makefile` | `check-host-exporters` |

`jobName: node-exporter` 是有意的：图表自带的文件系统、RAID、时钟规则和两个主机面板不用复制就能看到这四台；`scope="external"` 把它们和 DaemonSet 的目标分开。

### 5.2 告警

| 告警 | 级别 | 等多久 | 条件 |
|---|---|---|---|
| `BifrostHostDown` | critical（推手机） | 1m | `up{job="node-exporter",scope="external"} == 0` |
| `BifrostHostTargetsMissing` | warning | 10m | 外部目标不足 4 个或一个都没有 |
| `BifrostHostDiskSpaceLow` | warning | 30m | 外部主机可写文件系统剩余 < 15%（自带规则在 3% 时推手机） |
| `BifrostHostDiskSmartFailing` | critical | 5m | `smart_status == 0`，或 smartctl 退出码第 4 位（预失效属性到阈值） |
| `BifrostHostDiskBadSectors` | critical | 10m | `Current_Pending_Sector` 或 `Offline_Uncorrectable` > 0 |
| `BifrostHostDiskMissing` | critical | 25m | 看到的盘数少于过去一天的最大值 |
| `BifrostHostDiskReallocatedGrowing` | warning | — | 重映射扇区一天内增加 |
| `BifrostHostNvmeCriticalWarning` | critical | 5m | NVMe critical warning ≠ 0 |
| `BifrostHostNvmeMediaErrors` | warning | — | NVMe 介质错误一天内增加 |
| `BifrostHostSmartReadFailing` | warning | 1h | smartctl 退出码低 3 位（读不了盘，SMART 告警会瞎） |
| `BifrostHostSmartExporterDown` | warning | 15m | smartctl 目标不通或没配上 |
| `BifrostGiteaUnavailable` | critical | 2m | 任一路 `probe_success == 0` |
| `BifrostGiteaProbeDown` | warning | 10m | 探针本身不通或没配上 |

**路由不用改**：critical 自动走 `owner-ntfy` 并继续进 webhook。`make check-alert-routing` 照样过。

**3 分钟怎么来的**：最后一次成功抓取之后，下一次抓取在 +30s 失败（超时 10s），规则最迟 +70s 看到，`for: 1m` 之后 +130s 触发，Alertmanager 新组 `group_wait` 30s，约 **2 分 40 秒**，再加中转和 ntfy 的几秒。promtool 单测按 30 秒评估间隔核过这个时序。

**Gitea 为什么用 blackbox**：Gitea 的 `/metrics` 没开（404），开要改 Deployment 并重启 Gitea（Recreate）；kube-state-metrics 的就绪数在 01 整机挂掉时会停在最后的值（API server 也在 01 上）。blackbox 从别的节点按用户实际用的两条路去取 `/api/healthz`，这几种情况都能看到。`for: 2m` 跨过一次正常的重启。

## 6. 已知缺口（要 Owner 定）

**G1 .50 自己坏了。** 中转就在 .50 上，`BifrostHostDown{host="mini-50"}` 送不出去。现在兜底的是 .52 的 peer-watchdog（每 60 秒查 `.50:8783/api/v1/alerts/relay`，连续失败 `RELAY_DOWN_MIN` 分钟就直接发 ntfy；.52 没设这个值，默认 5 分钟），**约 5–6 分钟**，达不到 3 分钟。手工改 .52 的 `env.local.sh` 没用：`deploy_mac_mini.sh` 每次部署都重写它。
- A（建议）：在 B3「告警转发成对」里一起解决：.52 跟着 .50、.50 坏了自动接手。B4 ① 先接受 .50 这一台是 5–6 分钟。
- B：现在就在 platform 仓库把 `peer_watchdog.sh` 的默认值从 5 改成 1（算下来最坏约 2 分 40 秒），重新部署 .52。小改动，统筹线程能做；代价是 .50 上 operator-plane 重启超过一分钟也会推一条。
- C：一直接受 5–6 分钟。

**G2 NAS 坏了，Prometheus 可能先卡住。** Prometheus 的 WAL 写在 NAS 的 NFS（`hard`）上，NAS 不在时写入可能一直阻塞，抓取和规则评估跟着停，`BifrostHostDown{host="nas"}` 就发不出来。兜底是 Watchdog 心跳：Prometheus 停了就不再发 Watchdog，Alertmanager 随即不再送心跳（平时每 5 分钟一次），.50 从最后一次心跳算起 15 分钟呼叫，**最迟约 15 分钟**，推送说的是「心跳没了」而不是「NAS 坏了」。这是推断，没实测（页缓存可能让 Prometheus 多撑几分钟）。
- A（建议）：先测再定。NAS 装 M.2 SSD 本来就要关机（W-68 10-19 定，等小主机到货一起排），那次就是现成的演练：看 3 分钟内是否收到 `CRITICAL Host nas … is not answering`、Prometheus 有没有停住。停住了再做 B。
- B：在 .52 的 peer-watchdog 加一项「直接探 NAS」（和探 .50 中转同一个机制，同样直接发 ntfy），不经过 Prometheus。platform 仓库的小改动。
- C：把 Prometheus 的数据挪出 NFS。这推翻 TD-289 你选的「放 NAS」，不建议。

**G3 两台接连坏。** 根路由 `group_by: [alertname, namespace]`，同名告警进同一组：第一台推完后 5 分钟内第二台坏，要等 `group_interval` 5 分钟才推。要改得给 `BifrostHost.*` 单独一条按 `host` 分组的路由（helm upgrade，Owner）。建议现在不改，少见。

**G4 mini 重启以后。** FileVault 开着、自动登录被禁，mini 重启后停在解锁界面，operator-plane、中转、node_exporter 都不跑，直到有人登录。告警会一直响到那时，这是对的，但要知道「mini 重启 = 要人去登录一次」。另外 .52 `pmset autorestart 0`，停电来电后不会自己开机（`sudo pmset -a autorestart 1` 能改，Owner；属于 B3 / B5 的范围，这里只记下）。

## 7. 切片和验收

| 步 | 谁 | 多久 | 做什么 |
|---|---|---|---|
| 0 | 统筹线程 | — | 复核本分支，按发布窗口和 `push-main.sh` 合进 infra main（这一步不改任何运行中的东西：清单不归 Argo） |
| 1 | 任何人 | 几秒 | 确认文件已在 origin/main |
| 2 | mini 两台：**统筹线程可代做（待 Owner 定）**，不用 sudo | 各约 2 分钟 | `host-exporters.sh mini 50` / `mini 52` |
| 3 | Owner（节点钥匙，问一次口令） | 约 5 分钟 | `host-exporters.sh agent-06` |
| 4 | Owner（NAS 的 k8s_admin 口令，问一次） | 约 8 分钟 | `host-exporters.sh nas` |
| 5 | Owner 在终端跑 `host-exporters.sh cluster`；**或**统筹线程对 4 个文件各做一次 `plan_manifest` + `apply_manifest`，Owner 在 Console 批 4 张 C 级单 | 约 3 分钟 | 抓取、规则、探针、面板进集群 |
| 6 | 统筹线程 | 约 10 分钟 | 核对：`host-exporters.sh check` 全 ok；Prometheus 里 `up{scope="external"}` 4 个 1、`up{job="smartctl"}` 2 个 1、`probe_success{job="gitea-probe"}` 2 个 1；`node_md_disks{host="nas",state="active"} == 3`；`smartctl_device_smart_status` NAS 3 块、06 1 块都是 1；面板「Bifrost Hosts」每块都有数；`ALERTS{alertname=~"BifrostHost.*|BifrostGitea.*"}` 为空 |
| 7 | 演练（见 OWNER-STEPS 第 7 步） | 每台约 5 分钟 | 停一台的 node_exporter，3 分钟内手机收到 `CRITICAL Host … is not answering`，恢复后收到 `RESOLVED`。mini 两台统筹线程可做；06、NAS 要 Owner。同一台 30 分钟内别演第二次（中转去重） |

两条做法二选一，别混用：第 5 步用 Owner 的 `kubectl apply`（客户端合并），以后改这些文件也用它；用 `apply_manifest` 就是服务端合并（字段管理者 `bifrost-applier`），以后也一直用它。

**验收怎么算过**

1. 集群外任何一台 3 分钟内到手机：第 7 步四台各演一次，每次从停掉到收到推送 ≤ 3 分钟。.50 的整机失联按 G1 的决定另算；NAS 的整机失联在装 SSD 那次关机时验（G2）。
2. NAS 坏盘当天知道：不能真弄坏一块盘。由三样一起证明：第 6 步看到 3 块盘的 SMART 和 `md1` 的盘数；promtool 单测证明规则在这些数变坏时触发；推送通路由第 7 步证明。
3. Gitea 不可用有告警：第 6 步看到两条路都是 1；单测证明一条路失败 2 分钟后触发。实网演练只在 Gitea 本来就要停的时候做（例如 01 维护），不为演练停 Gitea。

## 8. 风险

- **报数端口在局域网上没有鉴权。** 能连到 Server 网段的（Server 区本身、Work 区，按 UniFi 规则）都能读：主机名、挂载点、CPU / 内存、磁盘型号和序列号。没有凭证。集群节点的 `:9100` 一直就是这样，MinIO 的 `:9000` 指标也是公开的。要加 TLS / basic auth 可以用 exporter-toolkit 的 web-config，但要多管一份口令；建议现在不加。
- **smartctl_exporter 是 root。** NAS 上是特权容器，06 上是 root 进程（能力收窄到两项）。它的 HTTP 面很小，版本钉死、只在局域网；被打穿就是 root。
- **版本钉死、谁升级。** 版本只在 `versions.env` 和 compose 的 digest 里，主机上不会自己变（06 不走 apt，NAS 不跟 latest，mini 不走 brew）。由统筹线程升级：图表升级让 DaemonSet 的 node-exporter 换版时，同一个提交改 `versions.env` 和 compose，然后重跑第 2–4 步（脚本可重跑，只替换二进制、重启服务）。smartmontools 在 06 上跟 Ubuntu 的安全更新走。还没有自动核对两边版本一致的检查，可以作为后续一条防线（比如 `check-host-exporters` 加一个读 DaemonSet 镜像的 LIVE 模式）。
- **UGOS 升级。** 可能重置 `/etc/sudoers.d`（MinIO 的免口令规则就有这个提示）。compose 文件在 `/volume1` 上不受影响，容器 `restart: unless-stopped`。没经历过一次 UGOS 升级，没核实。
- **NAS 上谁能改配置。** 目录和 compose 文件是 root 的；但 `/home/k8s_admin` 是 777，而 Agent 的钥匙能以 k8s_admin 登 NAS。脚本因此不在那里中转文件（文件随 ssh 会话进 root 自己的临时目录、当场执行）。家目录 777 本身是个旧问题，建议 Owner 以后改成 700（`sudo chmod 700 /home/k8s_admin`），不在本切片做。
- **图表自带规则的噪音。** 这四台加进 `job="node-exporter"` 后，自带的 warning 也会作用于它们（例如 `TargetDown` 会和 HostDown 重复报一条 warning、`NodeSystemSaturation`），只进 webhook，不推手机。
- **macOS 防火墙。** 现在关着；以后打开，未签名的 node_exporter 进来的连接会被拦，表现为 HostDown（能看到，不会静默）。

## 9. 没核实的

- 咨询线程的方案笔记（找不到，见第 1 节）。
- NAS 不在时 Prometheus 会不会卡住（G2，推断）。
- smartctl_exporter 在 UGOS 的特权容器里能扫到 3 块盘；06 那块 `SSD_512GB` 是否给出完整的 SMART（都没跑过）。
- NAS 能从 quay.io 拉镜像（DNS 能解析，没拉过）；06 能从 github.com 下载（root 不受 agent 出站规则限制，没试）。
- 服务端 dry-run：Agent 的身份做不了。做过的是：客户端严格校验（集群的 OpenAPI）全部通过；`apply-manifest-check.sh` 按 PROD 的 actuation-policy 对 4 个文件都判为 C 级、通过；`kubectl kustomize k8s/monitoring` 能渲染；`make check-alert-rules`（含新单测，另做了一次改错期望必失败的阳性对照）、`check-alert-routing`、`check-http-metrics-coverage`、`check-maintainers`、`check-monitoring-persistence`、`check-host-exporters` 都过。
- blackbox 的配置没用 `--config.check` 跑过（没下载二进制），键名按 v0.28.0 的 CONFIGURATION.md 核对。
