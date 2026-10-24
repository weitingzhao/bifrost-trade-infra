# Review 537 — W-68 B4 ①

审查对象：`w31/r4-w68-b4`，`8f0e51f..5c6782edd1f012dd51e40ae629a7e06a23b8e0fc`。以下路径、行号均指该提交。只读审查；检查在本目录的 `snapshot/` 副本运行，未修改受审工作树，未连接网络、集群、MCP 或 SSH，未提交代码。

结论：有 3 项需先修的问题；G1–G3 也仍然限制原定的三分钟验收，不能算已经完成。

## A — 会出问题的地方

### A1 · P1：NAS 的 root 配置仍在普通用户可替换的父目录下

证据：`scripts/host-exporters/nas/install-nas.sh:17`、`:26`、`:29`、`:31`、`:35`；`scripts/host-exporters/nas/compose.yaml:58`。切法 `agent-config/work/multi-agent/CUT-w68-b4-host-monitoring-2026-10-24.md:34` 明确记录 `/volume1/docker` 权限为 `777`。

脚本只把 `/volume1/docker/host-exporters` 及配置文件设成 root 所有，没有保护父目录。在无 sticky bit 的可写父目录中，普通用户仍能重命名这个 root 子目录，再放入同名目录或链接。配置安装与后面的 `cd`／Compose 操作之间存在替换窗口；日后的按路径撤销操作也会重新解析这条路径。恶意 Compose 一旦被 Owner 以 root 执行，就能启动特权容器。root 自己的临时目录保护了传输阶段，未保护最终配置的位置。

最小修法：将配置迁到持久卷上祖先目录均不可被普通用户改名或写入的位置，并拒绝不可信链接；安装、重跑、撤销统一使用新路径。若保留当前路径，必须先解决父目录的写权限，而不是只 `chown` 最末一级。不要未经核对就修改其他 NAS 容器共用目录的权限。

### A2 · P2：丢掉一个 SMART／Gitea 目标时，采集器失联告警不会触发

证据：`k8s/monitoring/bifrost-host-rules.yaml:186`、`:217`；目标分别见 `bifrost-hosts-external.yaml:74`、`bifrost-blackbox.yaml:161`。

`absent(up{job="smartctl"})` 只检测整个 job 消失。若 NAS 的 SMART 目标从配置里漏掉，而 06 仍然 `up=1`，`up == 0` 和 `absent(...)` 都返回空，NAS 的 SMART 监控永久消失也没有提醒。Gitea 两条路径中的一条被漏掉时完全相同。四台 node-exporter 的数量守卫不能发现这两类遗漏。

最小修法：按预期身份检查缺失——SMART 的 `host=nas/agent-06`，Gitea 的 `via=nodeport/service`；可分别使用带身份选择器的 `absent(...)`，或将预期清单与实际目标作差。补上“仅剩一个正常目标”和“全部目标缺失”的规则测试，断言告警身份和等待时间。

### A3 · P2：SMART HTTP 正常但读盘失效时，可以长期没有手机通知

证据：`k8s/monitoring/bifrost-host-rules.yaml:158`、`:174`、`:186`；`scripts/host-exporters/nas/install-nas.sh:52`；手机路由见 `scripts/k3s/values-kube-prometheus.yaml:168`。

当前只用 HTTP `up` 判断 exporter 是否可用；盘数告警只比较一天内的历史最大值；明确表示“SMART 告警已经看不见盘”的读错误规则却是 warning。场景：NAS 仍在线，SMART 端点仍返回 200，但读盘持续失败、健康指标缺失；若扫描数量不变，盘数规则也不触发。此时至多一小时后进 webhook，不到手机。若 exporter 从启动起就扫描到零盘，零对零的历史比较还会一直正常。安装检查只要求存在任意一块盘的健康指标，不能代替持续的三盘覆盖检查。

这会让“NAS 坏盘当天知道”在监控已失明时没有保障；单测注入一条失败 SMART 指标，证明不了这种路径。

最小修法：为 NAS 的预期盘覆盖、零盘和健康指标缺失增加守卫，并让持续丢失 NAS SMART 可观测性的告警在当天内推到手机；读错误可保留短期 warning，再增加长时间持续失效的 critical。明确休眠盘的处理，避免把正常休眠当坏盘。测试至少覆盖 `up=1` 但零盘／无健康指标，以及只有读错误位、没有 SMART 失败指标的情况。

## B — 切法的缺口与未验证项

### G1：诚实披露了 .50 的单点，但还不满足三分钟

切法 `:105`–`:108` 正确指出：.50 整机失联时，Prometheus 即使产生 HostDown，也无法经 .50 自己送出；.52 的独立推送才是兜底。延期到 B3 是可供 Owner 决定的范围调整，不是现有验收已达标。

方案 B 的方向合理，但“默认等待改成 1 分钟”仍需验证完整时序。旁证只读查看了本机 platform 源码 `scripts/agent/peer_watchdog.sh:54`、`:73`、`:98`：除了阈值，还包含三次请求、重试睡眠和后续重启探测。不能直接将阈值换算成可靠的 2 分 40 秒上限。演练须覆盖 .50 整机／中转不可达，停止它的 node_exporter 不会验证这条兜底。

### G2：NAS 同时承载监控存储，推迟实测不能当作已验收

切法 `:110`–`:113` 对 NFS `hard` 挂载阻塞的风险说明正确，也明确写了未实测；还应强调 Alertmanager 的数据也在同一个 NAS 上，见 values 文件 `:108`，不只是 Prometheus。停止 NAS 的 node-exporter 会保留 NFS，不能验证这个共同故障。

利用计划中的 NAS 停机做演练是合理的；在那之前只能标“整机失联验收待完成”。若必须立即兑现三分钟，建议采用已有 .52 看门狗直接探 NAS、直接发 ntfy 的路径，使告警不依赖 NAS 上的监控存储。

“最迟约 15 分钟”也不应作为严格上界：它是从最后一次实际收到的 Watchdog 心跳起算，尚有 Alertmanager 对旧告警的有效期／重复发送、relay 的轮询和外发时间。这里只读核对了 `.50` relay 的本机源码 `api/internal/alertrelay/relay.go:344`、`:382`，没有测量运行时上限。

### G3：分组延迟确实存在，且直接影响逐台演练

切法 `:115` 的分析与仓库配置一致：`group_by: [alertname, namespace]`、`group_interval: 5m`。外部 HostDown 的 namespace 都为空，第二台主机会进入同一组。它不只影响“两台同时坏”，还会影响操作单连续停不同主机的测试。

最小处理是给 HostDown 配置按 `host` 分组的路由，同时保持手机和审计 webhook 两条去向；或者由 Owner 明确接受多主机事件的例外。操作单 `OWNER-STEPS-w68-b4-2026-10-24.md:135` 的“不回就按不改”不足以证明 Owner 接受了三分钟要求的例外。现有 `check-alert-routing` 只证明接收者可达，不检查通知时间。

### G4：披露充分，处理边界合理

切法 `:117` 记录了 FileVault、GUI LaunchAgent、登录前服务不运行，以及 .52 来电后不自动开机。用户级 node-exporter 与现有带外服务采用相同生命周期，没有为采集额外索取 root 权限，处理合理。重启后的告警本应持续；.50 重启期间仍受 G1 限制。是否改自动开机可留给 B3／B5，不应由本安装脚本顺带改变。

### 其他覆盖判断与待验项

- **主机活着、node-exporter 死了：有覆盖。** `up{job="node-exporter",scope="external"} == 0` 同样触发 critical，描述也解释了两种情况。主机与采集器的故障尚未区分，但不会因此漏报。
- **标签衔接基本正确。** 使用离线缓存的同版 chart 88.1.3 核对：ScrapeConfig 的 `jobName` 设置抓取后 `job` 标签，Operator 自行保证内部 `job_name` 唯一；不会因与 DaemonSet 同名而生成重复 job。chart 的 RAID／容量规则直接选择 `job="node-exporter"`，两侧指标同时携带 `scope/host` 时可以匹配，`md1` 也在设备正则内。没有发现 scope 导致这些规则无法关联。critical 容量告警另有 `for: 30m`，并非达到 3% 就立即推送。
- **常规单机失联的时间预算合理，但有前提。** 30s 抓取、10s 超时、30s 评估、`for: 1m` 加首次新组 30s，约 160s 的估算可成立；前提是 Prometheus／Alertmanager／relay 正常且没有现存分组延迟。这不是四台整机故障的共同上界。
- **安装的基本限制合理。** Linux node-exporter 用专用用户；mini 用用户 LaunchAgent；06 和 NAS 的 SMART 才用高权限。主机监听地址均限定为指定 LAN IP。下载包有固定 SHA256，容器有固定 digest。未发现脚本修改现有 agentd、中转或带外服务的动作。NAS 最终配置的权限问题见 A1。
- **网络说明有证据边界。** 同一 Server 子网加节点 SNAT 的推断与现有配置相容；本次没有验证实际源地址、主机防火墙或每个端口的可达性。迁到 Agent VLAN 后补放行的要求已经写出。不能将本机 `curl` 成功代替 Prometheus 所在节点的抓取验证。
- **切法 §9 的未验证项总体诚实。** 未声称已安装、已发送到手机或通过服务端 dry-run。UGOS 的 SMART 三盘覆盖、06 SSD 的 SMART 支持、下载／拉镜像、blackbox 配置真实启动、UGOS 升级后的存活性，均仍需后续证据。还应补验 Linux systemd 沙箱下实际的文件系统可写标记、mini 登录后的采集完整性、blackbox 实际调度位置；其 `bifrost-blackbox.yaml:75` 只是优先避开控制面，并非保证分离。

## C — 小项

1. 切法 `:129` 要求 `up{scope="external"}` 有 4 个 1，但 node-exporter 4 个加 SMART 2 个，一共应有 6 个。改为 `up{job="node-exporter",scope="external"}` 检查四台，再单独检查两个 SMART。
2. `k8s/monitoring/grafana-dashboard-hosts.yaml:39`、`:50`、`:60` 的链接使用 `/d/...`，会离开实际的 `/grafana` 子路径。`k8s/overlays/platform-prod/ops-ingressroute.yaml:20` 仅把 `/grafana` 转给 Grafana，根路径会进 Console。补上 `/grafana/d/...`，或使用能保留部署子路径的链接。
3. 操作单 `:5` 的“任何一台约 2 分 40 秒”“Gitea 两分钟……推手机”过于确定。前者需在开头同时列明 G1–G3；后者的两分钟是规则 `for:`，还要加抓取、评估、Alertmanager 等待和传送时间。

## 离线检查与限制

已通过：

- `scripts/host-exporters/test_host_exporters.py`：11 项。SSH、kubectl 均为测试替身；测试临时目录限定在本审查目录内。日志：`checks/host-exporters.log`。
- 四个安装／入口脚本的 `bash -n`。
- `kubectl kustomize snapshot/k8s/monitoring`：渲染成功，输出 4,410 行，保存在 `checks/monitoring-rendered.yaml`。
- 四份新增监控清单的 YAML 解析，以及 dashboard JSON 解析。
- 分支自带 `check_alert_routing.py`、`check_monitoring_persistence.py`、`check_http_metrics_coverage.py` 的默认离线模式。
- 使用本机已有 chart 88.1.3 缓存离线渲染 node-exporter 规则，与新指标标签作静态核对；输出在 `checks/chart-node-rules.yaml`。

未检查：本机没有可执行的 `promtool` 和 `shellcheck`；没有下载工具，也没有启动可能拉镜像的 Docker fallback。因此没有独立重跑 PromQL 语法／规则单测，以上规则反例属于表达式静态分析。脚本测试只覆盖入口、传输和失败传播，未验证真实 root 安装、systemd／launchd、sudo 交互、Docker 容器或二进制运行行为。未独立核对远端发布包 checksum、镜像 digest 的内容；未运行 blackbox `--config.check`、服务端 dry-run、现场抓取或手机端演练。切法中作者声称已通过的线上／离线检查，不自动计作本次已复验。

先改

END OF REPORT
