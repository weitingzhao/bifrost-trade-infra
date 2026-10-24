# Review 540 — W-68 B4 ① 第二轮限定复核

审查对象：`w31/r4-w68-b4` 的 `a6cb8010429b719de099aff910023b30ef28d967`，相对第一版变基后的 `bb12194`。受审工作树是 `~/agent-work/r4-b4`。下列仓库路径、行号均指新提交。本轮只复核 537 已提出的问题及这次修订产生的问题。

**结论：先改。** 新路径解决了原来的 `/volume1/docker` 可替换父目录问题；但 A1 的拒绝条件没有在所有写入之前执行，新加的 NAS 第 4a 步也不能安全地完成它声称的检查。A2、A3 的规则修法在静态分析上成立；promtool 运行复验仍欠证据。G1–G3 继续是未完成的验收条件。

| 项目 | 判定 | 依据 |
|---|---|---|
| A1 | **未关闭**：旧路径已修，新增的 4a 有安全问题，安装器还会先接管不可信目录再检查 | 见下面两项 |
| A2 | **已关闭（规则代码层）**；测试闭环有欠项 | `k8s/monitoring/bifrost-host-rules.yaml:196`、`:266` |
| A3 | **已关闭（当前三盘场景的规则代码层）**；未独立完成 promtool 复验 | 同文件 `:219` |

## 需要先改的地方

### A1 · P1：第 4a 步通过可能已被植入启动代码的账户来检查自身

证据：`agent-config/work/multi-agent/OWNER-STEPS-w68-b4-2026-10-24.md:72`、`:75`、`:78`；随后输入 sudo 口令见 `:82`、`:90`。

新加的流程先 SSH 登录家目录为 777 的 `k8s_admin`，再执行 `chmod 700 ~`，最后用 `ls -A ~` 判断是否已有 shell 启动文件。然而 SSH 的用户 shell 可以在执行这条命令之前运行 `.bashrc`；SSH 的用户 rc 也属于需要排查的入口。其他 NAS 用户在收紧权限前放进去的代码，此时已经有机会以 `k8s_admin` 执行。后面的 chmod 不会撤销这次执行，也不会清除已植入的内容。

本轮在本目录离线复现了 Bash 的这条启动路径：设置临时 HOME 和 SSH_CLIENT，放入一个只写标记、随后删除自身的 `.bashrc`，再执行等价的「chmod、stat、ls」命令。结果退出 0，显示家目录已是 700，列表只剩 `.ssh`，但启动代码已运行。因此 `:78` 的“列表中没有那四个文件就继续”不能作为 4b 输入 sudo 口令的安全依据。复现脚本：`checks/reproduce_home_bootstrap.py`；结果：`checks/repros/home-bootstrap.log`。这是本地启动行为复现，没有连接 NAS，也没有证明 NAS 已遭植入。

最小修法：把收紧权限和排查已有启动内容的步骤移到可信的 NAS 控制台或独立管理会话中完成，核对家目录、启动文件和 `.ssh` 的所有权及内容，再开新的 k8s_admin 会话做安装。在原 SSH 命令里再套一层 `bash --noprofile --norc` 仍晚于 sshd 启动用户 shell，不能单靠它修复。切法已披露“Agent 本来就能以 k8s_admin 登录”的残余风险；这里的问题是**其他普通 NAS 用户在 777 窗口留下的内容**，与那项披露不同。

### A1 · P2：现有目录先被 chown／chmod，随后才检查，和“遇到不可信目录即停”的承诺不符

证据：`scripts/host-exporters/nas/install-nas.sh:36`–`:48`；操作单的承诺见 `agent-config/work/multi-agent/OWNER-STEPS-w68-b4-2026-10-24.md:84`。

`secure /volume1` 确实先检查了 `/` 和 `/volume1`。但对已经存在的 `@bifrost`、`host-exporters`，循环只先拒绝链接，然后在 `:42`、`:43` 无条件改属主和权限，到 `:45` 才检查整个目录链。所以原先非 root 所有、组可写或其他人可写的目录会被接管，检查看到的是修改后的状态。`compose.yaml` 同样只在安装前查链接，所有权和写权限在安装后才检查。它并未实现 BRIEF 所问的“每一级在写之前拒绝非 root 属主或其他人可写”。

最小修法：已存在的路径先验证，失败即停；只在已验证的父目录下创建缺失目录，创建后复查。现有 compose 路径也先验证类型与可信性，再决定替换。补实际执行顺序的测试，覆盖“预置非 root／可写目录时不发生任何接管写入”；现有测试主要检查字符串顺序。

需要明确肯定已修好的部分：`secure-dir.sh:25`–`:35` 会逐级拒绝链接、不允许的属主和组／其他人写权限；最终配置已迁到 `/volume1/@bifrost/host-exporters/`，安装后还有文件检查和 `cmp`，Compose 使用绝对路径。对于从可信 `/volume1` 开始新建的路径，父目录逐级锁定后普通用户不能再改名替换；**本轮没有复现最终安全目录检查通过后、普通用户仍能替换 Compose 路径的窗口**。不能把上述“先接管再检查”直接夸大为已经证明的新 root 执行漏洞。

## A2、A3 的规则判断与证据边界

**A2：按预期身份检查缺失，修法正确。** SMART 分别检查 `host="agent-06"`、`host="nas"`；Gitea 分别检查 `via="nodeport"`、`via="service"`。只剩另一个健康目标时，对应的 `absent` 仍返回带缺失身份的向量；全部目标缺失时，各身份也分别成立。等待时间分别为 15m、10m。四台 node 目标也改成了逐台检查，见 `k8s/monitoring/bifrost-host-rules.yaml:59`。

但作者回应中的“全部目标缺失也覆盖到了”不能算已提交测试证据：`k8s/monitoring/rule-tests/host-rules.test.yaml:191`、`:212` 分别断言 NAS SMART、NodePort 单独缺失，文件没有针对 SMART／Gitea **全部目标缺失**的告警断言。其他测试中没有提供这些输入，不等于断言过这些告警。请补上第一轮要求的全部缺失场景，核对两条告警身份及 for 边界。

**A3：当前三盘场景的分支覆盖合理。** `k8s/monitoring/bifrost-host-rules.yaml:222`–`:232` 覆盖 exporter down／目标缺失、扫描不足三盘、健康指标不足三盘或全无、退出码低三位读错误。各分支收敛到 `host`，分支变化本身不会因为设备标签不同而重建另一条告警；`for: 2h`、critical 及现有路由能让持续失明进入手机中转。离线路由检查确认 `BifrostNasSmartBlind` 同时到 `owner-ntfy` 和审计 webhook。

`:234`–`:235` 的 `unless on(host)` 会在 NAS node 目标仍配置、抓取结果为 `up=0` 时抑制这条 critical。它不抑制原有的 SMART exporter warning；文档也没有承诺所有 warning 都消失。NAS 的 node 目标本身也被删除时，规则无法再据此认定整机 down，这不属于已验证的整机失联抑制场景。

新测试在 `host-rules.test.yaml:236`、`:264`、`:304` 分别覆盖零盘／无健康指标、仅读错误位、健康及整机 down；2h 前后的断言和 3h20m 的抑制断言都在。NAS 与 06 的 `powermode-check=never`、安装时要求至少三条健康指标也已加入（`scripts/host-exporters/nas/compose.yaml:61`、`nas/install-nas.sh:75`、`install-linux.sh:134`）。休眠策略及现场确认仍需按切法执行。

**本轮没有独立跑通上述 promtool 单测或作者的 PromQL 移除分支对照。** 运行分支的 `check_alert_rules.py` 时，已使用禁止拉镜像、禁止容器网络的本地 Docker 包装；执行在访问 Docker socket 时被权限拒绝，尚未进入规则检查。本机 PATH 和所查本地缓存也未找到可执行 promtool。日志见 `checks/alert-rules.log`。作者所述旧规则 5 处失败、逐项移除分支失败，仍是作者的证据，不能计作本轮复验。补齐全部缺失测试后，应在可用的离线 promtool 环境把这些检查一起跑完。

## G1–G3 与操作单的等待时间

**G1：未验收的披露已改正。** 切法 `agent-config/work/multi-agent/CUT-w68-b4-host-monitoring-2026-10-24.md:110`–`:114`、操作单 `:10`、`:162` 明确写出默认约 **5.5–8 分钟**，把阈值改为 1 分钟也只是约 **2 分–3 分 40 秒**，均不保证三分钟；两次约 5.5 分钟的旧实测只属于“中转不可用、主机仍在”。这与 watchdog 串行执行重试、SSH 重启及后续探测的代码相容，属于推算而非运行上界。切法 `:110` 中“第 3 轮（距它 300–360 秒）”有计数笔误：若首轮为第 1 轮、轮距 100–120 秒，这应是第 4 轮。该笔误不改变“尚未达标”的结论。

**G2：未验收的披露已改正。** 切法 `:116`–`:118`、操作单 `:163` 现在同时指出 Prometheus 和 Alertmanager 依赖 NAS，整机故障的通知时间未知；“最后一次心跳后 15 分钟”不再当作故障发生后的严格上界。只停 node-exporter 不能验证 NFS 共同故障，也已写明。装 SSD 时的整机演练完成前，继续待验收。

**G3：决策门已改正，逐台演练的三分钟判定还需收紧表述。** 切法 `:121`–`:125`、操作单 `:164` 已改成 Owner 明确选 A 或接受 B，不回复不算接受；values 未改，所以仍有 5m 的同组更新间隔。A 的草稿保留了手机与审计两条去向。

操作单 `:119`–`:122` 已给出 CRITICAL 约三分钟／分组情况下约八分钟、恢复后十分钟排障、同机三十分钟内不重复演练的说明，明显比上一版可执行。但“收到上一台 RESOLVED 后再等 1 分钟，就用三分钟判断下一台”不能仅由当前 values 或 promtool 单测推出：RESOLVED 通知本身不证明旧聚合组已经清空并销毁。若旧组仍保留，RESOLVED 后 1 分钟停下一台，下一条可能仍等到该组下一个 5 分钟刻度，从停机算约 4 分钟。本轮未运行 Alertmanager 验证组回收及 resolved 重送的具体时序，不能把这项条件计为通过。

最小处理：Owner 选 A 后按每台独立分组演练；若接受 B，操作单应允许后续不同主机仍按约八分钟的分组预算判定，把三分钟仅用于已确认的新组，或补充能够证明“一分钟隔离足够”的 Alertmanager 离线／现场时序证据。不要让 Owner 因照单等了一分钟仍晚于三分钟而误判安装失败。

## 537 其余项目与本轮检查

G4 没有扩大范围：仍保留 FileVault／登录后的 LaunchAgent 生命周期说明，没有顺带改开机设置。上一轮“其他覆盖判断”涉及的网络证据、容量等待时间、systemd 沙箱、mini 指标、blackbox 调度及现场待验项，修订版已补充或继续明确待验，本轮不重新开题。

C1–C3 的文字／链接修正已完成：切法 `:144` 分别核对 4 个 node、2 个 SMART、2 条 Gitea 路；面板四处链接已带 `/grafana/d/`（`k8s/monitoring/grafana-dashboard-hosts.yaml:41`、`:52`、`:62`）；操作单开头分开披露 G1、G2，并将 Gitea 写为约三分半。逐台等待说明的剩余边界见上面的 G3。

本轮独立完成的离线检查：

- 提交快照副本上的脚本测试 **18 项通过、0 跳过**，见 `checks/host-exporters.log`。SSH、kubectl、curl 为测试替身；临时 Git 仓库是测试夹具，没有对受审仓库提交。
- SecureDir 原版 6 项通过；移除权限检查后 2 项失败，移除链接检查后 1 项失败，与作者所述对照吻合。另验证 uid=0 时拒绝本机非 root 属主。见 `checks/secure-mutations-summary.log`、`checks/secure-*.log`。
- 五个 shell 脚本的 `bash -n` 通过；`check_alert_routing.py`、`check_http_metrics_coverage.py`、`check_monitoring_persistence.py` 默认离线检查通过；dashboard JSON 解析通过。
- 第 4a 步的本地启动行为反例复现成功，见上文。

未检查：promtool 规则语法／规则单测及 PromQL 对照的实际执行、真实 NAS 权限与 ACL、实际 root 安装及 GNU install 行为、systemd／launchd／Docker 运行、Alertmanager 聚合组时序、现场抓取及手机通知。没有联网、访问集群、调用 MCP 或 SSH；没有修改受审工作树，没有创建实际代码提交，所有本轮输出都在本审查目录内。

先改

END OF REPORT
