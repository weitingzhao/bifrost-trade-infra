# 切法：W-68 B4 ① 集群外机器的主机监控与失联告警（第 4 轮 4.9）

起草 2026-10-23 23:45–10-24 00:30 CDT（统筹线程派出的子代理）；按 Codex 复核 537（`~/agent-work/codex-review-537/REPORT.md`，结论「先改」）10-24 00:50 起改第 2 版，逐条回应在同目录 `RESPONSE.md`。
只读调研后写：没有 apply，没有在任何主机上装东西，没有建审批单。清单和脚本在 infra 分支 `w31/r4-w68-b4`（未推送）。Owner 要跑的命令在 `OWNER-STEPS-w68-b4-2026-10-24.md`。

## 1. 要做的事（Owner 2026-10-17 定）

- B4 = 集群外机器的统一监控与管控，分五片；本切法只做 **① 06、NAS、两台 mini 报数，加「主机失联」和硬盘告警，配一个全机房面板**。
- 监控就用现有的 kube-prometheus-stack（Prometheus / Alertmanager / Grafana，`monitoring` 命名空间）加社区报数程序，不另起第二套。
- 验收（台账 B4 行）：**集群外任何一台坏了 3 分钟内手机知道；NAS 坏盘当天知道；Gitea 不可用也有告警**。台账写 Owner 的部分「在 06、NAS、两台 mini 上装包，约 45 分钟」。**本切片做完，这三条不是全部达标**，哪几条能做到、哪几条要靠 B3 和装 SSD 那次实测补，见第 7 节。
- 依据：台账 Claude Doc（`https://claude.ai/artifact/Kb5jJTGhoSJCtdvs4ZKMJM`，B4、B3 两行，10-24 读）、`agent-config/WORK.md` W-68 节和下面的实测。
  咨询线程笔记 `PLAN-w68-redundancy-2026-10-17.md` / `redundancy-map-draft.md` **本机已找不到**：`side-session-notes/` 下没有 `local_728a47ff-…` 目录（10-24 00:05 查；按文件名全盘 find 也没找到，macOS 受保护的目录除外）。

## 2. 现状（2026-10-24 实测，全部只读）

### 2.1 Prometheus 怎么发现抓取目标

| 项 | 实测 |
|---|---|
| 栈 | helm `kube-prometheus-stack` chart 88.1.3（`scripts/k3s/values-kube-prometheus.yaml`），operator v0.93.0（CRD 0.92.1），Prometheus v3.13.2 单副本在 ubt-k3s-04，`scrapeInterval` / `evaluationInterval` 都是 30s |
| 选择器 | Prometheus CR 的 ServiceMonitor / PodMonitor / Probe / **ScrapeConfig** / PrometheusRule 选择器都是 `release: kube-prometheus-stack`，命名空间不限；**没有 additionalScrapeConfigs** |
| 集群外目标 | 只有一个：ScrapeConfig `bifrost-minio-nas`（NAS 上 MinIO 的 `:9000`，静态目标，`job="scrapeConfig/monitoring/bifrost-minio-nas"`，up=1） |
| 节点报数 | node-exporter DaemonSet `v1.12.1-distroless`，5 个目标：01/02/04/05 up，gpu-server（.60，睡眠）up=0。06 出集群前最后一个样本 10-17（还读得到它的磁盘：一块 SATA SSD `sda`，LVM ext4 根 500 GB） |
| 现成规则 / 面板 | 图表自带的 node-exporter 规则和面板「Node Exporter / Nodes」「Node Exporter / MacOS」都按 `job="node-exporter"` 选。其中 `NodeRAIDDegraded` critical、等 15 分钟；`NodeFilesystemAlmostOutOfSpace` critical 是剩 3% **持续 30 分钟** |
| 谁管这些清单 | `k8s/monitoring/` **不归 Argo**：7 个 Application 的路径（`overlays/platform-{stg,prod}`、`overlays/{stg,prod}`、research `k8s`、finance 两个）都不含它，kustomization 头注释也这么写。过去由 Owner 用管理员 kubeconfig 单文件 `kubectl apply`；W33B 以后也能走平台 `plan_manifest` / `apply_manifest`（actuation-policy 允许 `k8s/monitoring`；ScrapeConfig 是 TD-275 专门加的种类；monitoring 是 C 级，Owner 在 Console 批） |
| 告警怎么到手机 | `severity="critical"` 和几条备份告警走 `owner-ntfy`（.50 的 operator-plane `:8783`，`ALERT_RELAY=on` 只在 .50），同时进 PROD webhook；warning 只进 webhook。根路由 `group_by: [alertname, namespace]`、`group_wait 30s`、`group_interval 5m`。推送标题是 `CRITICAL <summary>` / `RESOLVED <summary>`，中转对同一告警同一状态 30 分钟内只推一次。Watchdog 每 5 分钟送一次心跳，.50 从最后一次心跳起 15 分钟没新心跳就呼叫 |
| 监控自己的数据 | **Prometheus 和 Alertmanager 的卷都在 `nfs-hot`，即 NAS 上的 NFSv3、`hard` 挂载** |

### 2.2 四台机器

| 机器 | 系统 | 磁盘 | 现在有没有报数 | 谁能登、能做什么 |
|---|---|---|---|---|
| agent-06 `192.168.10.79` | Ubuntu 24.04（内核 6.8.0-146），x86_64 | 1 块 SATA SSD（型号 `SSD_512GB`），无 RAID | 没有：9100 没在听（10-24 从 Mac Pro 测，22 通） | `vision` 免密 sudo，只认 Owner 的节点钥匙（Agent 登不上）。nftables 只有出站链（管两个 agent 用户），**没有入站过滤** |
| nas `192.168.10.20` | UGOS（Debian 12），内核 6.18.15，8 核，7.4 GB | **RAID 5 `md1` = sda2+sdb2+sdc2**，3 × Seagate ST12000NM0127 12 TB，`[3/3] [UUU]`；LVM 上 btrfs `/volume1` 22 TB 用了 6%；系统在 58 GB eMMC，根是 overlay | 只有 MinIO 的 :9000。没有 snmpd；`/sbin/smartctl` 在（要 root）；Docker Engine 29.6.2，数据目录 `/volume1/@docker` | `k8s_admin`（Agent 的 `~/.ssh/id_ed25519` 能登，只读查了上面这些）：sudo 要口令，免口令只有 minio 的 4 条 compose 命令。权限：`/`、`/volume1` 是 root 755；`@` 开头的系统目录 root 专用；共享目录（`docker`、`k3s-hot` 等）777；**`/home/k8s_admin` 777**（TD-433），里面没有 `.bashrc` / `.profile` |
| mini-50 `192.168.10.50` | macOS 26.5.1，arm64，16 GB | 一块板载 SSD（251 GB） | 没有 | `vision` 是 admin，Agent 能只读 SSH。Homebrew 在；系统防火墙关；**FileVault 开、自动登录被禁**；operator-plane 和 peer-watchdog 是 `gui` 域的 LaunchAgent；`pmset autorestart 1` |
| mini-52 `192.168.10.52` | 同上 | 同上 | 没有 | 同上；**`pmset autorestart 0`**（停电来电后不会自己开机）。peer-watchdog 配了 `PEER_RELAY_URL`（看 .50 的中转）和 `PEER_AGENT_SSH`（.50 不通时去重启它） |

### 2.3 网络

四台和集群节点都在 `192.168.10.0/24`，Pod 出集群走节点地址（flannel masquerade），是同一网段内的二层流量，不经过 UniFi 的区间防火墙，按现有配置不用加规则。
依据：Prometheus 抓 NAS `:9000` 是 up；Alertmanager 能送到 `.50:8783`；从 Mac Pro（有线口同在 Server 网段）连 `.79:22` 通，9100 / 9633 不通只因为还没人在听。
**这是推断**：没有核实 Prometheus 所在节点发出去的实际源地址，也没有逐个端口从节点上测。真正的证据是装好后 Prometheus 里这些目标 `up=1`（第 7 节第 6 步），本机 `curl` 通不能代替。
以后 06 搬进单独的 Agent VLAN（`CUT-agent-host-06-2026-10-17.md` 第 3 节 C 段）时，要加一条 Server → Agent 的 tcp 9100、9633 放行。

## 3. 每台用什么报数

版本统一钉在 `scripts/host-exporters/versions.env`（NAS 用镜像 digest）：node_exporter 跟集群 DaemonSet 同一版 **1.12.1**；smartctl_exporter **0.14.0**（0.15.0 是 10-07 才出的）。

| 机器 | 选的做法 | 为什么，放弃了什么 |
|---|---|---|
| agent-06 | 官方 release 包（校验 sha256）装到 `/usr/local/bin`，两个 systemd 服务：`node-exporter`（专用系统用户，`:9100`）、`smartctl-exporter`（root、能力只留 `CAP_SYS_RAWIO`/`CAP_SYS_ADMIN`，`:9633`）；`smartmontools` 从 Ubuntu 装 | Ubuntu 自带的 `prometheus-node-exporter` 是 1.7.x，和集群不同版，升级跟着发行版走、谁升级说不清 |
| nas | UGOS 的 Docker：`/volume1/@bifrost/host-exporters/compose.yaml` 起两个容器（node_exporter 只读挂 `/proc`、`/sys`、`/`；smartctl_exporter 特权、root），镜像按 digest 钉死。**从 `/` 到这个文件每一级都只有 root 能写**，`secure-dir.sh` 在写文件前、compose 读文件前各查一次（复核 537 A1）。不放 `/volume1/docker/`：那个共享目录 777，任何 NAS 账户都能把里面的 root 目录改名、换成自己的 compose 文件，再由 root 跑起来 | **SNMP**：UGOS 上没有 snmpd，要另配 snmp_exporter 和 MIB，RAID / SMART 也不一定报，放弃；**直接装在系统里**：根是 overlay，UGOS 升级可能抹掉，放弃；**cron 跑 smartctl 写文本文件**：同一个问题。MinIO 从 10-06 起就是这样跑在 NAS 的 Docker 里 |
| mini ×2 | 官方 darwin-arm64 包装到 `~/bifrost-agent/node-exporter/<版本>/`，用户级 LaunchAgent `com.bifrost.node-exporter`，**不要 sudo** | `brew install node_exporter` 也不要 sudo，但版本跟着 `brew upgrade` 走，钉不住。mini 不做 SMART：板载单盘，坏了就是整机 HostDown，磨损慢，以后再看 |

放在哪里听：每个报数程序只绑本机局域网地址（`192.168.10.x:9100` / `:9633`），和集群 DaemonSet 绑 `HOST_IP` 一样。

`/volume1/@bifrost` 是新建的目录。UGOS 怎么对待 `/volume1` 下它自己不认识的 `@` 目录没有核实；就算被清掉，正在跑的容器不受影响（容器的定义在 Docker 自己的 `/volume1/@docker` 里，compose 文件只在 up / down 时读），重跑第 4 步即可。

## 4. SMART 与 RAID 怎么报

- **RAID**：node_exporter 读 `/proc/mdstat`（`node_md_disks{device="md1",state=…}`、`node_md_disks_required`），图表自带的 `NodeRAIDDegraded`（critical，15 分钟）和 `NodeRAIDDiskFailure`（warning）直接覆盖 NAS，因为 job 标签就是 `node-exporter`（复核 537 用同版 chart 离线渲染核对过标签能接上）。不另写重复的规则。
- **SMART**：smartctl_exporter 每 60 秒跑一次 `smartctl --json`；NAS 用自动扫描，M.2 SSD 装上之后自己出现。**每次都读每块盘（`--smartctl.powermode-check=never`）**：默认会跳过休眠的盘，而被跳过的盘和读不出来的盘看起来一样。NAS 那三块盘本来就不会休眠（Prometheus、Alertmanager、MinIO、registry 一直往上写；第 7 节第 6 步用 `node_disk_io_time_seconds_total` 核对）。以后要让盘休眠，先把这一项改回 `standby`，并让 `BifrostNasSmartBlind` 认得休眠状态。
- **看不见盘也要报**（复核 537 A3）：`BifrostNasSmartBlind` 要求三块 RAID 盘都报出健康值。exporter 不通或没配上、看到的盘少于 3 块（包括从一开始就是 0 块）、某块盘没有健康值、smartctl 读不了某块盘，任何一种持续 2 小时就推手机；NAS 整机不在时不报（HostDown 已经推过）。
- 「NAS 坏盘当天知道」由这些一起兑现：SMART 判定失败 5 分钟、读不出的扇区 10 分钟、阵列少盘 15 分钟、盘从系统里消失 25 分钟、SMART 看不见盘 2 小时，都是 critical，都推手机（时间是规则的 `for:`，到手机还要加抓取、评估和 30 秒分组等待）。

## 5. 抓取配置、告警和面板

### 5.1 文件（都在分支里，未应用）

| 文件 | 内容 |
|---|---|
| `k8s/monitoring/bifrost-hosts-external.yaml` | ScrapeConfig `bifrost-hosts-node`（4 个 `:9100`，`jobName: node-exporter`，标签 `scope="external"`、`host=agent-06/nas/mini-50/mini-52`，30s）和 `bifrost-hosts-smartctl`（06、NAS 的 `:9633`，`jobName: smartctl`，60s） |
| `k8s/monitoring/bifrost-blackbox.yaml` | Gitea 探针：blackbox_exporter v0.28.0（digest 钉死，非 root、只读根、去掉全部能力，**优先**不放控制面节点，不保证）+ ConfigMap + Service + ScrapeConfig `bifrost-gitea-probe`（每 30 秒 GET `/api/healthz`，走 NodePort `.73:30300` 和 Service 两条路） |
| `k8s/monitoring/bifrost-host-rules.yaml` | PrometheusRule，三组 14 条（见 5.2） |
| `k8s/monitoring/grafana-dashboard-hosts.yaml` | 面板「Bifrost Hosts」（uid `bifrost-hosts`）：所有机器的可达、开机时长、文件系统、内存、CPU、RAID 缺盘数、SMART 表、Gitea 探针；链到两个自带的主机面板（链接带 `/grafana/` 子路径，复核 537 C2） |
| `k8s/monitoring/rule-tests/host-rules.test.yaml` | promtool 单测 10 组：失联时序、集群节点不触发、少一台目标、少一个 SMART 目标、少一条 Gitea 路、SMART 失败 / 坏扇区 / 掉盘 / 预失效位、SMART 正常应答但零盘、只有读错误位、健康与整机不在时不误报、Gitea 一条路失败 |
| `k8s/monitoring/kustomization.yaml` | 加上面 4 个文件 |
| `scripts/host-exporters/` | `versions.env`、`install-linux.sh`（06）、`install-mac.sh`（mini）、`nas/compose.yaml` + `nas/install-nas.sh` + `nas/secure-dir.sh`、`host-exporters.sh`（Owner / 统筹线程的入口，子命令 `mini 50|52`、`agent-06`、`nas`、`cluster`、`check`）、`test_host_exporters.py`（18 项） |
| `Makefile` | `check-host-exporters` |

`jobName: node-exporter` 是有意的：图表自带的文件系统、RAID、时钟规则和两个主机面板不用复制就能看到这四台；`scope="external"` 把它们和 DaemonSet 的目标分开。

### 5.2 告警

| 告警 | 级别 | 等多久 | 条件 |
|---|---|---|---|
| `BifrostHostDown` | critical（推手机） | 1m | `up{job="node-exporter",scope="external"} == 0` |
| `BifrostHostTargetsMissing` | warning | 10m | 四台里某一台没有抓取目标（按 `host` 各一个 `absent`，告警带出是哪台） |
| `BifrostHostDiskSpaceLow` | warning | 30m | 外部主机可写文件系统剩余 < 15%（自带规则在剩 3% 持续 30 分钟时推手机） |
| `BifrostHostDiskSmartFailing` | critical | 5m | `smart_status == 0`，或 smartctl 退出码第 4 位（预失效属性到阈值） |
| `BifrostHostDiskBadSectors` | critical | 10m | `Current_Pending_Sector` 或 `Offline_Uncorrectable` > 0 |
| `BifrostHostDiskMissing` | critical | 25m | 看到的盘数少于过去一天的最大值 |
| `BifrostHostDiskReallocatedGrowing` | warning | — | 重映射扇区一天内增加 |
| `BifrostHostNvmeCriticalWarning` | critical | 5m | NVMe critical warning ≠ 0 |
| `BifrostHostNvmeMediaErrors` | warning | — | NVMe 介质错误一天内增加 |
| `BifrostHostSmartReadFailing` | warning | 1h | smartctl 退出码低 3 位（读不了盘），任何主机 |
| `BifrostHostSmartExporterDown` | warning | 15m | smartctl 目标 `up == 0`，或 06 / NAS 某一个的目标不存在（按 `host` 各一个 `absent`） |
| `BifrostNasSmartBlind` | **critical** | 2h | NAS 三块 RAID 盘的 SMART 没看全（见第 4 节），NAS 整机不在时除外 |
| `BifrostGiteaUnavailable` | critical | 2m | 任一路 `probe_success == 0` |
| `BifrostGiteaProbeDown` | warning | 10m | 探针 `up == 0`，或 NodePort / Service 某一条路的目标不存在（按 `via` 各一个 `absent`） |

**路由不用改**：critical 自动走 `owner-ntfy` 并继续进 webhook。`make check-alert-routing` 照样过。

**单机失联到手机约 2 分 40 秒，有前提**：最后一次成功抓取之后，下一次抓取在 +30s 失败（超时 10s），规则最迟 +70s 看到，`for: 1m` 之后 +130s 触发，Alertmanager 新组 `group_wait` 30s，约 160 秒，再加中转和 ntfy 的几秒。promtool 单测按 30 秒评估间隔核过规则这一段。前提：Prometheus、Alertmanager 和 .50 的中转都在工作，并且当时没有别的 `BifrostHostDown` 正在推（否则见 G3）。这不是四台整机故障的共同上界：.50 和 NAS 整机坏另算（G1、G2）。

**Gitea**：规则等 2 分钟；从最后一次成功探测算，下一次失败的探测 +30s（超时 5s），评估最迟 +65s，再等 2 分钟、加 30 秒分组等待，**约 3 分半**到手机。用 blackbox 是因为 Gitea 的 `/metrics` 没开（404），开要改 Deployment 并重启 Gitea（Recreate）；kube-state-metrics 的就绪数在 01 整机挂掉时会停在最后的值（API server 也在 01 上）。blackbox 从别的节点按用户实际用的两条路去取 `/api/healthz`。`for: 2m` 跨过一次正常的重启。blackbox 只是**优先**不放控制面节点，装好后核对它实际在哪个节点（第 7 节第 6 步）。

## 6. 已知缺口（要 Owner 定，都不算已验收）

**G1 .50 自己整机坏：约 5.5–8 分钟，达不到 3 分钟。** 中转就在 .50 上，`BifrostHostDown{host="mini-50"}` 送不出去。兜底是 .52 的 peer-watchdog（`bifrost-platform` 的 `scripts/agent/peer_watchdog.sh`，launchd 每 60 秒起一次）：先查 `.50:8783/api/v1/alerts/relay` 三次（每次最多 8 秒、之间睡 5 秒，最多约 39 秒），从第一次失败那轮的开始时刻算，满 `RELAY_DOWN_MIN` 分钟（.52 没设，默认 5）的那一轮才直接发 ntfy；同一轮接着还要探 .50 的 operator-plane 三次、再 ssh 去重启它，.50 整机不在时一轮要跑约 100 秒，launchd 不会在上一轮没跑完时再起一轮，轮距变成约 100–120 秒。按这个推算：第一次失败的那一轮在 .50 坏后 0–60 秒内开始，第 3 轮（距它 300–360 秒）才满 5 分钟，再加这一轮自己探中转的 24–39 秒，**约 5.5–8 分钟**。实测只有两次「中转不可用、主机还在」（10-06 22:27→22:32:57、10-07 13:18→13:23:27），都是第一次失败那轮之后约 5.5 分钟，比整机不在要快。手工改 .52 的 `env.local.sh` 没用：`deploy_mac_mini.sh` 每次部署都重写它。
- A（建议）：放进 B3「告警转发成对」：.52 跟着 .50、.50 坏了自动接手。在那之前 B4 ① 对 .50 整机坏不算达标。
- B：现在就把看门狗的默认等待从 5 分钟改成 1 分钟。按同样的推算是第 2 轮就发：**约 2 分–3 分 40 秒，不保证 3 分钟**（轮距被重启探测拖长的问题还在）；要稳定 3 分钟，得把「看中转」拆成单独、更频繁的一个 launchd 任务，这已经是 B3 的范围。没实测过。
- C：一直接受。
- 演练：只停 .50 的 node_exporter **验证不了**这条兜底（中转还活着，推送照常从 .50 发出）。要验得让 .50 的中转不可达，放在 B3。

**G2 NAS 整机坏：时间未知，未验收。** Prometheus 和 Alertmanager 的数据都在 NAS 的 NFS（`hard`）上，NAS 不在时写入可能一直阻塞，抓取、评估、发通知可能都停，`BifrostHostDown{host="nas"}` 就发不出来；这是推断，没实测（页缓存可能让它们多撑几分钟）。兜底是 Watchdog 心跳：Prometheus 停了就不再发 Watchdog，.50 从最后一次收到的心跳起 15 分钟呼叫，推送说的是「心跳没了」而不是「NAS 坏了」。**15 分钟不是严格上界**：最后一次心跳可能比 NAS 坏的时刻早（平时每 5 分钟一次），Alertmanager 对已发出的 Watchdog 还会按有效期再送一阵，中转每分钟才检查一次。只停 NAS 的 node_exporter 时 NFS 还在，**也验证不了**这个共同故障。
- A（建议）：NAS 装 M.2 SSD 本来就要关机（W-68 10-19 定，等小主机到货一起排），那次就是现成的演练：看 3 分钟内是否收到 `CRITICAL Host nas … is not answering`，Prometheus 和 Alertmanager 有没有停住。在那之前「NAS 整机坏」只能标「待验收」。
- B：给 .52 的看门狗加一项「直接探 NAS、直接发 ntfy」，不经过 NAS 上的监控存储。platform 仓库的小改动；时序和 G1-B 一样不保证 3 分钟，除非做成单独的快任务。
- C：把 Prometheus / Alertmanager 的数据挪出 NFS。这推翻 TD-289 你选的「放 NAS」，不建议。

**G3 两台接连坏、以及逐台演练：第二台可能再晚 5 分钟。** 根路由 `group_by: [alertname, namespace]`，外部主机的 `BifrostHostDown` 都没有 namespace，同名进同一组。组里第一条推出后，同组新告警要等下一个 `group_interval`（5 分钟）；恢复的 `RESOLVED` 也是在下一个 5 分钟刻度才推。这会影响连续停不同主机的演练（等多久算正常写在操作单第 7 步）。**需要你明确选一个，不回不算接受**：
- A：给 `BifrostHostDown` 单独一条按 `host` 分组的路由（Alertmanager 配置，helm upgrade，你来跑）。手机和审计 webhook 两条去向都要保住，草稿如下（只写在这里，没改 values）：在 `routes:` 里 Watchdog、InfoInhibitor 之后加
  `- {receiver: owner-ntfy, matchers: ['alertname="BifrostHostDown"'], group_by: [alertname, host], group_interval: 1m, continue: true}`，
  并把现有 `severity="critical"` 那条改成 `matchers: ['severity="critical"', 'alertname!="BifrostHostDown"']`（否则手机收两条）；webhook 那条兜底路由不动。改完跑 `make check-alert-routing`，再 helm upgrade。
- B（建议）：明确接受例外：「同一段时间里第一台 3 分钟内到，后面几台最多再晚 5 分钟」。理由：多台同时坏多半是同一个原因（停电、交换机），第一条推送已经让你知道出事了；改全局路由要动整个 Alertmanager 配置。

**G4 mini 重启以后。** FileVault 开着、自动登录被禁，mini 重启后停在解锁界面，operator-plane、中转、node_exporter 都不跑，直到有人登录。告警会一直响到那时，这是对的，但要知道「mini 重启 = 要人去登录一次」。.52 `pmset autorestart 0`，停电来电后不会自己开机（`sudo pmset -a autorestart 1` 能改，Owner；属于 B3 / B5，本脚本不改）。

## 7. 切片和验收

| 步 | 谁 | 多久 | 做什么 |
|---|---|---|---|
| 0 | 统筹线程 | — | 复核本分支，按发布窗口和 `push-main.sh` 合进 infra main（这一步不改任何运行中的东西：清单不归 Argo） |
| 1 | 任何人 | 几秒 | 确认文件已在 origin/main |
| 2 | mini 两台：**统筹线程可代做（待 Owner 定）**，不用 sudo | 各约 2 分钟 | `host-exporters.sh mini 50` / `mini 52` |
| 3 | Owner（节点钥匙，问一次口令） | 约 5 分钟 | `host-exporters.sh agent-06` |
| 4 | Owner：先收紧 `/home/k8s_admin`（TD-433，几秒，不用 sudo），再装（k8s_admin 的 NAS 口令问一次） | 约 9 分钟 | `chmod 700 ~`；`host-exporters.sh nas` |
| 5 | 第 2–4 步做完后（脚本先查 6 个端点都在，缺一个就停）。Owner 在终端跑 `host-exporters.sh cluster`；**或**统筹线程先跑 `host-exporters.sh check` 全 ok，再对 4 个文件各做一次 `plan_manifest` + `apply_manifest`，Owner 在 Console 批 4 张 C 级单 | 约 3 分钟 | 抓取、规则、探针、面板进集群 |
| 6 | 统筹线程 | 约 15 分钟 | 核对，见下 |
| 7 | 演练（操作单第 7 步） | 每台约 8 分钟（含等 RESOLVED） | 一次一台：停 node_exporter，记推送时间，恢复。mini 两台统筹线程可做；06、NAS 要 Owner |

第 6 步核对的内容（都在 Prometheus 里看，本机 `curl` 只作参考）：
- `host-exporters.sh check` 全 ok。
- `up{job="node-exporter",scope="external"}` 4 个、`up{job="smartctl"}` 2 个、`up{job="gitea-probe"}` 2 个，全是 1（复核 537 C1：上一版写成 `up{scope="external"}` 4 个，实际是 6 个）。
- `node_md_disks{host="nas",device="md1",state="active"} == 3`；`count(smartctl_device_smart_status{host="nas"} == 1) == 3`；`smartctl_device_smart_status{host="agent-06"} == 1`。
- NAS 三块盘一直有读写：`rate(node_disk_io_time_seconds_total{host="nas",device=~"sd[abc]"}[1h]) > 0` 三条都有（`powermode-check=never` 的前提）。
- 06 的 systemd 沙箱没让根分区报成只读：`node_filesystem_readonly{host="agent-06",mountpoint="/"} == 0`。
- 两台 mini 登录状态下指标齐全：`node_filesystem_avail_bytes{host=~"mini-.*",mountpoint="/System/Volumes/Data"}`、`node_memory_total_bytes{host=~"mini-.*"}` 各 2 条。
- blackbox 的 Pod 不在 ubt-k3s-01：`kubectl -n monitoring get pod -l app.kubernetes.io/name=bifrost-blackbox-exporter -o wide`。落在 01 上就记下来（01 整机坏时探针跟着没，`BifrostGiteaProbeDown` 会报，但 `BifrostGiteaUnavailable` 不会）。
- 面板「Bifrost Hosts」每块都有数，两个链接能打开。
- `ALERTS{alertname=~"BifrostHost.*|BifrostNas.*|BifrostGitea.*"}` 为空。

两条应用做法二选一，别混用：第 5 步用 Owner 的 `kubectl apply`（客户端合并），以后改这些文件也用它；用 `apply_manifest` 就是服务端合并（字段管理者 `bifrost-applier`），以后也一直用它。

**验收按现实拆开**

| 情形 | 本切片做完能到哪 | 怎么证明 | 缺的靠什么补 |
|---|---|---|---|
| 06、mini-52 报数停或整机坏；NAS、mini-50 只是报数停 | ≤ 约 2 分 40 秒（第 5.2 节的前提下） | 第 7 步逐台演练，每次从停到推送 ≤ 3 分钟 | — |
| mini-50 整机坏 | 约 5.5–8 分钟（推算） | 本切片不演 | **B3**（G1） |
| NAS 整机坏 | 未知：Prometheus 不卡就和上一行一样，卡住则靠心跳，15 分钟以上 | 装 M.2 SSD 那次关机 | **那次实测**，必要时 G2-B |
| 几台在同一段时间坏 | 第一台同上；后面几台最多再晚 5 分钟 | 演练里分开做 | G3：你选 A 或明确接受 B |
| NAS 坏盘 | SMART 失败 5 分钟、坏扇区 10 分钟、阵列少盘 15 分钟、掉盘 25 分钟、看不见盘 2 小时，再加几十秒到手机 | 不能真弄坏一块盘：第 6 步看到三块盘的 SMART 和 `md1`；promtool 单测证明规则在这些数变坏时触发；推送通路由第 7 步证明 | — |
| Gitea 不可用 | 约 3 分半 | 第 6 步两条路都是 1；单测证明一条路失败 2 分钟后触发 | 实网演练等 Gitea 本来要停的时候（例如 01 维护），不为演练停 Gitea |

所以本切片做完可以说：「06、mini-52 和所有报数程序的失联 3 分钟内到手机；NAS 坏盘当天到；Gitea 不可用约 3 分半到」。「.50 整机坏」等 B3，「NAS 整机坏」等装 SSD 那次实测，「几台一起坏」等你对 G3 的回答。

## 8. 风险

- **报数端口在局域网上没有鉴权。** 能连到 Server 网段的（Server 区本身、Work 区，按 UniFi 规则）都能读：主机名、挂载点、CPU / 内存、磁盘型号和序列号。没有凭证。集群节点的 `:9100` 一直就是这样，MinIO 的 `:9000` 指标也是公开的。要加 TLS / basic auth 可以用 exporter-toolkit 的 web-config，但要多管一份口令；建议现在不加。
- **smartctl_exporter 是 root。** NAS 上是特权容器，06 上是 root 进程（能力收窄到两项）。它的 HTTP 面很小，版本钉死、只在局域网；被打穿就是 root。
- **版本钉死、谁升级。** 版本只在 `versions.env` 和 compose 的 digest 里，主机上不会自己变（06 不走 apt，NAS 不跟 latest，mini 不走 brew）。由统筹线程升级：图表升级让 DaemonSet 的 node-exporter 换版时，同一个提交改 `versions.env` 和 compose，然后重跑第 2–4 步（脚本可重跑，只替换二进制、重启服务）。smartmontools 在 06 上跟 Ubuntu 的安全更新走。还没有自动核对两边版本一致的检查，可以作为后续一条防线（比如 `check-host-exporters` 加一个读 DaemonSet 镜像的 LIVE 模式）。
- **UGOS 升级。** 可能重置 `/etc/sudoers.d`（MinIO 的免口令规则就有这个提示），也可能把家目录权限改回去（第 6 步复查）。compose 文件在 `/volume1` 上，容器 `restart: unless-stopped`。没经历过一次 UGOS 升级，没核实。
- **NAS 上谁能改 root 跑的东西。** host-exporters 的 compose 文件放在只有 root 能写的路径上（A1）。但两件旧事不在本切片改：① `minio-backup` 的 compose 和 `.env` 还在 777 的 `/volume1/docker/` 下，是同一类问题（任何 NAS 账户都能改名替换那个目录），建议另记一条债，修法同样是挪到 root 专用的路径；② Owner 在第 4 步是在 **k8s_admin 的会话里**输 sudo 口令，而 Agent 的钥匙本来就能以 k8s_admin 登 NAS，能改这个账户的家目录和 shell 启动文件。家目录收成 700（第 4 步，TD-433）挡住的是**其他** NAS 账户，挡不住 Agent。要彻底分开，Owner 在 NAS 上要有一个只认他带口令钥匙的管理账户，sudo 只在那里输。这超出本切片，记在这里。
- **图表自带规则的噪音。** 这四台加进 `job="node-exporter"` 后，自带的 warning 也会作用于它们（例如 `TargetDown` 会和 HostDown 重复报一条 warning、`NodeSystemSaturation`），只进 webhook，不推手机。
- **macOS 防火墙。** 现在关着；以后打开，未签名的 node_exporter 进来的连接会被拦，表现为 HostDown（能看到，不会静默）。

## 9. 没核实的

- 咨询线程的方案笔记（找不到，见第 1 节）。
- G1 的 5.5–8 分钟（和 B 的 2 分–3 分 40 秒）是按脚本和 launchd 的行为推算的；G2 里 Prometheus / Alertmanager 会不会卡住是推断。
- smartctl_exporter 在 UGOS 的特权容器里能扫到 3 块盘；06 那块 `SSD_512GB` 是否给出完整的 SMART；NAS 三块盘确实不休眠（都要装好后看，第 7 节第 6 步）。
- UGOS 怎么对待新建的 `/volume1/@bifrost`；家目录改成 700 以后 UGOS 自己的功能（个人文件夹）是否正常。
- NAS 能从 quay.io 拉镜像（DNS 能解析，没拉过）；06 能从 github.com 下载（root 不受 agent 出站规则限制，没试）。
- 06 上 systemd 沙箱下文件系统的只读标记、mini 登录后指标齐全、blackbox 实际被调度到哪个节点（第 7 节第 6 步）。
- 网络是推断（第 2.3 节）：节点实际源地址、主机防火墙、逐端口可达，都以装好后 Prometheus 里 `up=1` 为准。
- 服务端 dry-run：Agent 的身份做不了。做过的离线检查和结果见 `~/agent-work/codex-review-537/RESPONSE.md` 第 4 节。
- blackbox 的配置没用 `--config.check` 跑过（没下载二进制），键名按 v0.28.0 的 CONFIGURATION.md 核对。
