# 回应复核 537 — W-68 B4 ①

回应人：写这份交付的子代理，2026-10-24 00:50–01:50 CDT。
新提交：`a6cb8010429b719de099aff910023b30ef28d967`，分支 `w31/r4-w68-b4`。先变基到 origin/main `639edc9`；第一版变基后是 `bb12194`。未推送、未 apply、没在任何主机上装东西。
每条修复都配了一条单测，这条单测只有修复之后才能过。阳性对照两种：用旧规则（`bb12194` 的 `bifrost-host-rules.yaml`）跑新单测；把修复从新规则 / 新脚本里单独拿掉再跑。两种都必须失败，结果见第 4 节。

## A — 会出问题的地方

### A1 · NAS 的 root 配置在普通用户可替换的父目录下 —— 改了

- compose 文件挪到 `/volume1/@bifrost/host-exporters/compose.yaml`。`/` 和 `/volume1` 都是 root 755（10-24 只读核对）；`@bifrost` 和 `host-exporters` 由脚本建成 root 0755。`/volume1/docker` 和 minio-backup 一样都没碰（照你说的，不改别的容器共用目录的权限）。
- 新增 `scripts/host-exporters/nas/secure-dir.sh <uid> <path>`。它检查路径本身和往上每一级目录：不能是链接，属主必须是 root（或给定的 uid），不能被组或其他人写（带 sticky 位的也拒）。
- `install-nas.sh` 调它四次：写文件前查 `/volume1` 和目录，写完查文件本身，再用 `cmp` 核对内容是不是这次带来的，然后才 `docker compose -f <绝对路径>`。目录或文件是链接就停。
- 安装、重跑、撤销都改用新路径（compose 头注释、`install-nas.sh`、操作单「撤销」、规则描述）。
- `/home/k8s_admin` 777 的修法写进了操作单 4a（TD-433）：`chmod 700 ~`。家目录归 k8s_admin 自己，不用 sudo。改完列出家目录内容；发现 shell 启动文件就先别做 4b，因为 4b 要在这个会话里输 sudo 口令。切法第 8 节写明了两点：700 挡得住其他 NAS 账户，挡不住本来就能以 k8s_admin 登录的 Agent；minio-backup 也在 777 目录下，属于同一类问题，建议另记一条债。
- **只有它能拦住的单测**（`test_host_exporters.py` 的 `SecureDir`，6 项）：
  - 父目录 777 被拒；
  - 文件组可写被拒；
  - 路径中有一级是链接被拒；
  - 文件缺失被拒；
  - 私有路径通过；
  - `install-nas.sh` 的检查顺序：先查 `/volume1` 和目录，再写文件，再查文件，最后 compose；而且不再出现 `DIR=/volume1/docker`。

### A2 · 少一个 SMART / Gitea 目标时采集器失联告警不响 —— 改了

- `BifrostHostSmartExporterDown`：`up{job="smartctl"} == 0`，或 `absent(up{job="smartctl",host="agent-06"})`，或 `absent(up{job="smartctl",host="nas"})`。
- `BifrostGiteaProbeDown`：`up == 0`，或 `via="nodeport"`、`via="service"` 各一个 `absent`。
- `BifrostHostTargetsMissing` 也一起改了：原来是 `count < 4`，现在按四台各一个 `absent`，告警直接带出缺的是哪台。
- **只有它能拦住的单测**：
  - 只剩 agent-06 的 SMART 目标：16 分钟时触发 `{job: smartctl, host: nas}`，14 分钟时不触发；
  - 只剩 Service 那条路：11 分钟时触发 `{job: gitea-probe, via: nodeport}`，9 分钟时不触发；
  - 少一台 node 目标：断言告警带 `host: agent-06`。
- 「全部目标缺失」也覆盖到了：每个 `absent` 各自触发。

### A3 · SMART 接口正常但读盘失效，长期到不了手机 —— 改了

- 新增 `BifrostNasSmartBlind`（critical，`for: 2h`，到手机）。下面任何一项成立就算：
  - `up == 0`，或 NAS 的 SMART 目标 `absent`；
  - `smartctl_devices < 3`，包括从启动起就是 0 块；
  - 报出 `smart_status` 的盘少于 3 块，或一块都没有（`absent`）；
  - 任何一块盘的退出码低 3 位有读错误。
- 整机不在时用 `unless` 去掉（那时 HostDown 已经推过）。各分支先 `max by (host)` / `count by (host)` 收成同一个身份。
- 读错误的 warning（`BifrostHostSmartReadFailing`，1 小时）保留，NAS 再由上面这条在 2 小时时推到手机。
- **休眠盘的处理**：NAS 和 06 都改成 `--smartctl.powermode-check=never`，每次都读每块盘，被跳过的盘不会冒充健康的盘。NAS 那三块盘有 Prometheus、Alertmanager、MinIO、registry 持续写入，本来就不会休眠；切法第 7 节第 6 步用 `node_disk_io_time_seconds_total` 核对。以后要让盘休眠，先改回 standby，并让这条告警认得休眠状态。
- 安装检查也改了：`install-nas.sh` 现在要求 3 块盘都报出健康值，不再是有一块就算过。
- **只有它能拦住的单测**：
  - `up=1`、`smartctl_devices=0`、没有任何健康指标：2h1m 时触发，1h59m 时不触发，`BifrostHostDiskMissing` 不触发（零对零）；
  - 3 块盘都是 `smart_status=1`、sdb 退出码 2：2h1m 时触发，`BifrostHostDiskSmartFailing` 不触发；
  - 三块盘都健康，以及 61 分钟后 NAS 整机不在：都不误报，一直测到 3h20m（不加 `unless` 的话它会在 3h1m 触发）。

## B — 缺口

### G1 —— 不算已验收，时序改写

- 读了 `peer_watchdog.sh` 的完整流程：先看中转（3 次，每次最多 8 秒，之间睡 5 秒），再探 .50 的 operator-plane（3 次），不通就 ssh 去重启、睡 5 秒再探。.50 整机不在时一轮约 100 秒，launchd 不会在上一轮没跑完时再起一轮，轮距变成约 100–120 秒。
- 推算：默认等 5 分钟，**约 5.5–8 分钟**到手机；把阈值改成 1 分钟，约 2 分–3 分 40 秒，**也不保证 3 分钟**。要稳定 3 分钟，得把「看中转」拆成单独的快任务，这是 B3 的范围。
- 实测只有两次，都是「中转不可用、主机还在」：10-06、10-07 各约 5.5 分钟。
- 切法、操作单都写明：这一条在 B3 之前不算验收通过；只停 .50 的 node_exporter 验证不了这条兜底。

### G2 —— 不算已验收

- 写明了 Alertmanager 的数据也在 NAS 上，不只是 Prometheus。
- 「最迟约 15 分钟」改成「15 分钟以上，不是严格上界」，列了三个原因：最后一次心跳可能早于 NAS 坏的时刻、Alertmanager 对已发出的 Watchdog 还会按有效期再送一阵、中转每分钟才检查一次。
- 写明只停 NAS 的 node_exporter 时 NFS 还在，验证不了这个共同故障。在装 SSD 那次关机实测之前，这一条标「待验收」。
- 备选 B（.52 直接探 NAS）写了：时序和 G1-B 一样，不保证 3 分钟。

### G3 —— 改成必须明确回答

- 去掉了「不回就按不改」，改成：Owner 回「G3 按 A」或「G3 接受 B」，不回不算接受。
- A 的路由草稿写在切法里：只在 `routes:` 里加一条 `alertname="BifrostHostDown"`、按 `[alertname, host]` 分组、`continue: true` 的 owner-ntfy 路由，并在现有 critical 路由里排除 `BifrostHostDown`，免得手机收两条；webhook 那条兜底路由不动，所以审计去向保住。values 里没改。
- 逐台演练的「等多久算正常」写进了操作单第 7 步：
  - 一次只演一台，等上一台的 RESOLVED 到了、再过 1 分钟才停下一台；
  - 没等够就停下一台，这一台最多再晚 5 分钟，不算失败，但不计入 3 分钟；
  - RESOLVED 在 CRITICAL 之后约 5 分钟到；
  - 同一台 30 分钟内别演第二次（中转去重）。

### G4 —— 不变

照你的意见，本脚本不改开机设置。

### 其他覆盖判断与待验项 —— 能并进的都并进了

- 「单机约 160 秒」现在写明了前提：Prometheus、Alertmanager、中转都在工作，当时没有别的 HostDown 正在推；并写明这不是四台整机故障的共同上界。规则注释、切法 5.2 节、操作单开头都改了。
- critical 容量告警是剩 3% **持续 30 分钟**才推，切法和规则描述都改了。
- 网络部分改成「推断」：以装好后 Prometheus 里 `up=1` 为准，本机 `curl` 不能代替。
- 第 6 步核对清单补了：
  - 06 根分区 `node_filesystem_readonly == 0`（systemd 沙箱）；
  - 两台 mini 登录状态下指标齐全；
  - blackbox Pod 实际所在节点（只是「优先」避开控制面）；
  - NAS 三块盘一直有读写；
  - NAS 家目录还是 700。
- 另加了一道闸：`host-exporters.sh cluster` 先查 6 个端点都在，缺一个就一个文件都不应用，免得规则先上、主机还没装，导致 2 小时后误推 `BifrostNasSmartBlind`。有单测。

## C — 小项

1. 核对清单改成 `up{job="node-exporter",scope="external"}` 4 个、`up{job="smartctl"}` 2 个、`up{job="gitea-probe"}` 2 个。
2. 面板里指向两个自带主机面板的链接都改成 `/grafana/d/<uid>`：顶部链接两个，文字面板里两处。别的现有面板（例如 data-layer 的 `/d/bifrost-ib-gateway/…`）有同样的问题，不在本切片，没改。
3. 操作单开头改了：先分开列「能推到的」和「还做不到的」（G1、G2），并写明 G3 的前提；Gitea 改成「规则等 2 分钟，加上抓取、评估和推送，约 3 分半」。

## 4. 离线检查（全部在新提交的树上重跑）

| 检查 | 结果 |
|---|---|
| `python3 scripts/check_alert_rules.py`（promtool 3.13.2，本机已有的镜像） | `ok: 4 rule file(s), 4 promtool test file(s) pass`；`host-rules.test.yaml` 10 组 |
| 阳性对照：旧规则（`bb12194`）跑新单测 | 5 处失败，都是新增或改过期望的：SmartExporterDown@16m、GiteaProbeDown@11m、TargetsMissing@11m、NasSmartBlind 零盘@2h1m、NasSmartBlind 读错误@2h1m |
| 阳性对照：在新规则里单独拿掉一项 | 拿掉 nas 的 `absent` → SMART 那组失败；拿掉 nodeport 的 `absent` → Gitea 那组失败；拿掉读错误分支 → 读错误那组失败；同时拿掉「少于 3 块盘」和「健康指标缺失」 → 零盘那组失败；拿掉 `unless` → 「整机不在」那组在 3h20m 失败 |
| 阳性对照：`secure-dir.sh` 关掉权限检查 / 关掉链接检查 | 分别有 2 项 / 1 项 SecureDir 单测失败；恢复后全过 |
| `python3 -m unittest scripts/host-exporters/test_host_exporters.py` | 18 项 OK（原 11 项、`SecureDir` 6 项、`cluster` 等端点 1 项） |
| `check_alert_routing.py`、`check_http_metrics_coverage.py`、`check_maintainers.py`、`check_monitoring_persistence.py` | 都是 ok |
| `kubectl kustomize k8s/monitoring` | 渲染成功，4439 行 |
| 对集群 OpenAPI 的客户端严格校验（`kubectl apply --dry-run=client --validate=strict`，只读身份） | 4 个文件、8 个对象都过 |
| `apply-manifest-check.sh`，用 PROD 的 actuation-policy | 4 个文件都判 C 级，都过 |
| 5 个脚本各自 `bash -n`；`docker compose config --quiet`；面板 JSON 解析 | 都过 |
| `BifrostNasSmartBlind` 的表达式在 PROD Prometheus 上只读执行 | 语法通过；现在返回 `{host="nas"} 1`，这是对的：NAS 还没有 SMART 目标 |

没做的还是没做：服务端 dry-run（只读身份没有权限）、blackbox `--config.check`、真实 root / systemd / launchd / Docker 运行、现场抓取、手机演练。

## 5. code-health（回统筹线程的问题）

- **仓库**：`bifrost-trade-infra`。
- **命令**：`bash agent-config/scripts/code-health/scan.sh --root <ws> --repo bifrost-trade-infra`。`<ws>` 是 scratchpad 里的一个目录，里面两个符号链接：`bifrost-trade-infra` 指向 origin/main 的一个分离 worktree（这次是 `639edc9`，量完已用 `git worktree remove` 删掉），`bifrost-platform` 指向工作区检出。分支用同样的办法另量了一次。
- **三个指标**（origin/main `639edc9` 和分支 `a6cb801` 读数完全相同）：
  - `code.duplication.rocket.infra`（infra 里重复的 shell 函数名）：7，基线 `DUP_FUNCS_INFRA_SH_BASELINE=3`；
  - `code.duplication.rocket.infra-py`（infra 里重复的 Python 函数名）：24，基线 `DUP_FUNCS_INFRA_PY_BASELINE=1`；
  - `code.oversized.rocket.infra`（infra 里超过 500 行的文件）：41，基线 `OVERSIZED_INFRA_BASELINE=3`。
- **更正上次的说法**：上次我说 `push-main.sh` 可能会拦，这不对。`push-main.sh` 的 `GATED` 名单（第 113 行）里没有 infra，推 infra 时它打印 `has no code-health task in CI; not scanned`；CI 里也没有 infra 的 code-health 任务。所以这三个超标不挡推送，只是基线早就跟不上了。
