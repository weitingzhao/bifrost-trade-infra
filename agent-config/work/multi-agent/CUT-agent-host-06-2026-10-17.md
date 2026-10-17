# 切法：06 出集群，当 Agent 主机（W-31 2.3 第一件）

起草 2026-10-17 00:50（统筹线程），按复核 230–234 改过；234 剩下的一角按 Owner 01:5x 的话照改、只用测试证明（`scripts/agent-host/test-k3s-on-06.sh`），不再复核。命令在 `OWNER-STEPS-agent-host-06.md`，都是 `scripts/agent-host/agent-06-owner.sh` 的子命令（每步出错即停、不打印凭证）；装到 06 上的文件也在 `bifrost-trade-infra/scripts/agent-host/`。

## 1. Owner 定的（2026-10-17 00:20）

> 照这个分配做：06 拿出集群当 Agent 主机（PROD + STG 两个 agentd），mini 管带外和参谋长，Mac Pro 只做开发；作为 2.3 第一件。

| 机器 | 以前 | 以后 |
|---|---|---|
| ubt-k3s-06（192.168.10.79，16 核 / 31 GB / 约 240 GB 空闲） | k3s 通用池节点 | **Agent 主机**：不再是 k8s 节点。两个 agentd，各用一个系统用户：`bifrost-agentd` 连 PROD 平台（主机号 `agent-06`），`bifrost-agentd-stg` 连 STG 平台（主机号 `agent-06-stg`） |
| Mac mini .50 / .52 | 带外层 + 虚拟机里跑 Agent（ADR §3） | 带外层 + 参谋长常驻（形态以后定）。不跑 Agent 的执行面 |
| Mac Pro | 开发 + 驾驶舱，过渡期跑着 PROD 的 agentd（`mbp-dev`） | 只做开发和驾驶舱。切换做完后它的 agentd 停掉 |

为什么是 06（10-16 实测）：它上面的请求只占 1.9 核 / 4.2 GB；没有 Postgres 实例（两个在 02、04）；不在 kube-vip 的节点亲和里（01/02/04/05）；搬走的负载其它节点放得下（各有 12–19 GB 空闲）。

## 2. 改了哪些已签的条文

这一项改 ADR 三处，按 Owner 这句话记进 ADR（同一个提交）：

- §3 位置表：mini 一行去掉「虚拟机：Claude Code 线程、Agent SDK harness、沙箱」，改成「参谋长常驻」；新增「Agent 主机（06）」一行；Mac Pro 一行写明过渡期的 agentd 在切换后停掉。
- §10 Agent 区：成员从「mini 上的沙箱虚拟机」改成「Agent 主机上 agentd 用户的进程」；第一步用主机上的出站规则（按用户），专门的 VLAN 是第三段。
- §12.3 执行：「第 3 轮迁到 mini 的虚拟机」改成「迁到 Agent 主机 06」。

不变的：k8s 节点上不跑 Agent 的执行面（06 先出集群，才装 agentd）；任何状态都不能只在 Agent 主机上（agentd 的检查点和产物照旧交给平台）；Agent 主机上不放集群管理员凭证、节点 root、子系统管理员密码。

## 3. 三段

| 段 | 谁做 | 多久 | 什么时候 |
|---|---|---|---|
| A 出集群 | Owner 跑命令，我在每步之间核对集群 | 约 40 分钟 | 周末，US 休市（平台和插件的写入不停，只是行情侧没有实时流量） |
| B 变成 Agent 主机 | Owner 在 06 上跑一个准备脚本、登录三家命令行、建两个 Gitea 账号、把令牌放进两个 Secret；我接平台配置、起草规则、做切换演练 | Owner 约 1 小时，分三次；我这边约半天 | A 做完以后；B 的脚本要先过一轮独立复核（我在线程里说过了再跑） |
| C 以后 | Owner（网络是 D 级） | 另定 | Agent 区专门的 VLAN；外网白名单（经代理）；参谋长搬到 mini |

### A 出集群：会发生什么

顺序：确认没有发布、没有在跑的流水线 → cordon → 备份 event-radar 的卷 → 删掉 06 上的 local-path 卷 → 两个零预算 PDB 的 Deployment 滚动重启 → drain → 我核对 → 06 上卸 k3s 并重启 → 删节点对象 → 我核对。

06 上现在的东西和各自的去向（10-17 00:40 读的，DaemonSet 不列）：

| 命名空间 | 东西 | 去向和副作用 |
|---|---|---|
| plugin-market-data | polygon-worker-options（8 个里 2 个在 06）、polygon-worker-stocks（3 个里 1 个） | PDB 不许驱逐（maxUnavailable 0），所以先 `rollout restart` 整个 Deployment，新 Pod 落到别处。重启时正在跑的抓取会重试 |
| plugin-market-data、plugin-flex-query | market-data-api（NFS 卷）、flex-query-api | drain 时换节点，几秒到几十秒不可用 |
| data | redis-live-prod、redis-dev（各 1 个、没有持久卷） | **缓存清空**，由写入方重新填。redis-ib 不在 06 上 |
| kube-system | coredns（只有 1 个）、local-path-provisioner、metrics-server、traefik（2 个里 1 个） | **coredns 换节点时全集群 DNS 断几秒**；traefik 另一个副本一直在 |
| bifrost-platform-prod | platform-console（1 个） | 换节点 |
| bifrost-platform-stg | platform-api、platform-workers（Recreate，emptyDir）、platform-console | STG 平台重启一次；运行时的状态在 PG，不丢 |
| bifrost-dev | api-account、daemon | 换节点（副本数不变，不碰 D10） |
| cicd | argocd 六个组件；四条已经结束的 CI 的 TaskRun Pod | argocd 换节点；那几条 CI 的日志随 Pod 消失，结果（Succeeded）留在 PipelineRun 上，发布闸门照样认 |
| monitoring | grafana、loki-results-cache | 换节点 |
| tekton | 三个控制器 | 换节点 |

06 上的 local-path 卷有 5 个：4 个是那几条结束了的 CI 的工作区，1 个是 `research/event-radar-input-pvc`（它的 CronJob 随 TD-190 删了，卷留着等你定）。节点一走这些卷就没法用了，而且以后删它们时清理用的辅助 Pod 会卡在一个不存在的节点上，所以在节点还在时删：**event-radar 那个先备份到 Mac Pro**（`~/bifrost-backups/event-radar-input/2026-10-17_node06_pvc-6bf6eca6/`），再删。只删卷，不删 PipelineRun（TD-357：发布闸门读它们）。

不受影响：kube-vip 的 VIP（不在 06 上）、两个 Postgres 实例、redis-ib、ib-gateway、PROD 的 Trade 负载（在 02）。

卸 k3s 用 06 上自带的 `/usr/local/bin/k3s-agent-uninstall.sh`：停掉 agent、删 `/etc/rancher`、`/var/lib/rancher`、`/var/lib/kubelet`、容器镜像和网络接口。入网令牌在 `/etc/systemd/system/k3s-agent.service.env`，随它删掉；两个 agent 用户在卸完之后才建，从没机会读到它，不用换令牌。卸完重启一次，再删节点对象（先删对象的话，还在跑的 agent 会把节点重新注册回来）。

### B 变成 Agent 主机：装什么

**两个系统用户**：`bifrost-agentd`、`bifrost-agentd-stg`。家目录 700，不在 sudo / adm / docker 组，没有密码（锁定），没有 `~/.ssh`，从没配过 MCP 服务器（A8 的理由照旧：任务里的 codex / cursor 会加载运行它的用户配的全部 MCP，包括平台的写工具）。

**出站规则**（`agent-egress.nft`，nftables 按发起连接的用户匹配，只管这两个用户；主机上别的进程不受影响）：

| | PROD agentd | STG agentd |
|---|---|---|
| PROD 平台 `192.168.10.100:30876` | 通 | 不通 |
| STG 平台 `192.168.10.73:30878` | 不通 | 通 |
| Gitea `192.168.10.73:30300` | 通 | 通 |
| 回环地址 127.0.0.0/8、::1（DNS 走 127.0.0.53；检查时起的测试服务） | 通 | 通 |
| 06 自己的 LAN 地址（192.168.10.79 上的任何服务） | 拒 | 拒 |
| 外网 IPv4 TCP 80 / 443（各家 API、npm、Go 代理、GitHub） | 通 | 通 |
| IPv6（::1 以外，包括 LAN 上的全局地址） | 拒 | 拒 |
| 内网其它一切：数据库、Redis、NAS、K8s API、节点 SSH、UniFi、TWS、别的 NodePort | 拒 | 拒 |
| 任何地方的 22 端口（包括 06 自己的 sshd）、其它端口和协议 | 拒 | 拒 |

规则由 `bifrost-agent-egress.service` 在开机早期加载；两个 agentd 服务绑在它上面（`BindsTo`），规则没加载就不会起。重跑准备脚本时规则原地替换（一次 nft 事务，中间没有空窗）；两个 agentd 在跑时准备脚本拒绝运行。核对脚本对每一项「应拒」要三样都成立才算过：探测确实以那个用户跑起来了、得到的正是规则给的「refused」、并且探测期间拒绝规则的计数涨了（对面本来就不通、名字解析不了、或探测自己出错，都不算过）；探测只在两个 agent 用户都没有任何进程时做（agentd 停着、也没有留下的命令行），一次一个，计数涨的只能是这次探测自己的包；IPv6 用链路本地地址测（不需要路由）；root（不受规则约束）的结果并排列出。

**工具链**：Go 1.25（和 CI 同一个大版本，从 go.dev 下、按官方 SHA-256 校验）、Node 22（nodejs.org，同样校验；CI 是 Node 20，已过维护期，所以这里用 22）、git。各家命令行装在各自用户的 `~/.local`：PROD 用户装 codex、claude、cursor-agent，STG 用户只装 codex。装的时候已经在出站规则之后，等于顺便验证了规则不挡正常工作。

**凭证**（都在各自用户的 `~/.config/bifrost/`，属主是该用户，权限 600）：

| 文件 | PROD | STG | 从哪来 |
|---|---|---|---|
| `agentd.token` | 有 | 有 | 准备脚本在 06 上生成；Owner 从 Mac Pro 经 SSH 读一次写进对应平台的 Secret，不经过对话和屏幕 |
| `agentd-git.token` | 有 | 有 | 两个新 Gitea 账号 `agentd-agent-06`、`agentd-agent-06-stg`，各生成一个令牌 |
| `claude-oauth.token`、`cursor-api.key` | 有 | 无 | 从 Mac Pro 上 `bifrost-agentd` 现有的两份原样拷过去（同一个账号，不重新生成） |
| codex 登录 | 各登一次 | 各登一次 | `codex login --device-auth`，各用户各自的登录（同一账号；共用一份 auth.json 会互相把刷新令牌顶掉） |

**两个 systemd 服务**（`bifrost-agentd.service`、`bifrost-agentd-stg.service`）：取代 Mac 上的 launchd 那份。环境和 Mac Pro 上现在那份一样（平台地址、Gitea 地址、执行者列表），另加 Linux 上能做的隔离：除了自己的家目录，别的家目录都看不见（`ProtectHome=tmpfs` + 只把自己的绑进来，所以 PROD 和 STG 的 agentd 互相看不到对方的凭证）；系统目录只读；不能提权（`NoNewPrivileges`）；内存上限 PROD 14 GB、STG 8 GB；停服务时连带它起的所有执行者一起停。日志进 journald。

**平台侧**（我做 STG，PROD 的提交要你点头）：`platform-auth.yaml` 加 `agentd:agent-06`（PROD）和 `agentd:agent-06-stg`（STG）；两个 overlay 的 `platform-api-role-tokens.patch.yaml` 加对应的环境变量（引用都是 `optional: true`）。你先把令牌放进 Secret，我再推配置，platform-api 滚动时就读到了。

**规则**：`standing-envelope:dev` 的 `hosts` 只能写已登记的主机，所以等两个 agentd 各连上一次（第一次领活时自动登记）再签放宽：PROD `[agent-06, mbp-dev]`、STG `[agent-06-stg, gate-b, mbp-dev]`，你用 `rule.sh sign` 签。切换做完后收紧去掉 `mbp-dev`（和 STG 上验收用完的 `gate-b`）：收紧不用签名，我交。

**切换顺序**：STG 上让 `agent-06-stg` 走一件确定性任务和一件 codex 任务 → PROD 上让 `agent-06` 走一件只改 Console 的目标（同时验证 2.2 的 Console 检查在 Linux 上也跑得起来）→ Mac Pro 上停掉 agentd（`launchctl bootout`）→ 收紧规则 → Mac Pro 合盖 30 分钟，看 PROD 上的活还在走。

### C 以后

- Agent 区专门的 VLAN 或 UniFi 分区（ADR §10），作为主机规则之外的第二层。UniFi 改动是 D 级。
- 外网白名单：ADR §10 写的是「外网白名单」，第一步放开了外网 80/443 全部（比 Mac Pro 上现在的 agentd 已经窄：那边内网外网全通）。要做到白名单，得加一个按域名放行的出站代理。
- 参谋长搬到 mini（RUNTIME-PLACEMENT 第 6 节第 5 步），形态比较后请你定。
- 一个通用的 Linux 安装脚本（像 macOS 的 `install-agentd.sh`）：这次两台 agentd 的服务文件是写死值的，第三台主机来的时候再抽出来。

## 4. 挡住了什么，没挡住什么

挡住：Agent 进程连内网（只剩自己的平台和 Gitea 两个端口）、SSH 到任何地方、平台的 MCP 写工具（新用户没配 MCP）、读别的用户的家目录（包括另一个 agentd 的凭证）、提权。

没挡住（都写明了是哪一段补）：

- 外网 80/443 全开（C）。
- 任务里的 Agent 和 agentd 是同一个用户，能读到 agentd 自己的平台令牌和 Git 令牌（TD-359；设计 §6.2、§7 第 7 条接受，第 3 轮做）。
- 06 和集群在同一个网段，主机规则只管 agent 用户；06 的 root（`vision` 免密 sudo）照旧只有你能用（C 的 VLAN 补第二层）。
- 规则按「谁的 socket」匹配，管不到 Unix socket，也管不到别的用户的本机服务替它转发（复核 230 B6）。卸掉 k3s 后 06 上应当没有这类服务；核对脚本列出全部监听端口和 Unix socket，B 里我逐个看，有不需要的就清掉。
- 各家命令行在 systemd 隔离下能不能真跑起来（codex 的 Linux 沙箱、Ubuntu 24.04 的 AppArmor 对非特权 user namespace 的限制、Go 和 npm 的真实构建）只有演练能证明（复核 230 B4）：STG 两件、PROD 一件演练里任何一件因此失败，切换就停，先修。
- 三家额度按账号算，加主机不加额度（RUNTIME-PLACEMENT 第 10 节）。

## 5. 要你定的（Owner 2026-10-17 01:0x：「六条照建议」）

| # | 事 | 建议 |
|---|---|---|
| 1 | event-radar 的卷：A 里备份到 Mac Pro 后删掉 | 删（节点走了它就不能用了；内容在备份里） |
| 2 | Agent 主机上用 Node 22，CI 是 Node 20 | 用 22（20 已过维护期）；CI 换 22 另记一项 |
| 3 | STG 的 agentd 只提供 codex 和确定性检查 | 照这样（STG 只为验收运行时本身） |
| 4 | B 的准备脚本会下载：Ubuntu 包、go.dev、nodejs.org、npm 上的 codex 和 claude、cursor.com 的安装脚本 | 同意（跑脚本就算同意；不想装 cursor 就告诉我，我把那一行拿掉） |
| 5 | PROD overlay 加 `agentd:agent-06`（推 infra 主线后 PROD 的 platform-api 滚动一次） | 到 B 第 4 步时你回「推 PROD 接线」 |
| 6 | 放宽规则加两台主机 | 到时你跑 `rule.sh sign` |

已定：1–4 照建议（event-radar 的卷备份后删；Node 22；STG 只有 codex 和确定性检查；同意准备脚本的下载）。5、6 是到那一步时的动作：第 5 条仍等你在 B4 回「推 PROD 接线」才推（批准按动作算），第 6 条由你跑签名。

## 6. 验收

1. A 之后：集群 5 个节点（gpu-server 照旧待机），所有 Deployment 和 StatefulSet 就绪，`kubectl get pv` 里没有 06；06 上没有 k3s 的进程和接口。
2. B 的准备之后：`host-check base`、`host-check creds` 退出码 0（每项「应拒」有 root 对照；两个用户只在自己的组、密码锁定、没有 `~/.ssh`；三家命令行能跑、codex 已登录；MCP 服务器数为 0；凭证文件属主对、600、非空）。
3. 两个 agentd 起来后：PROD Console 上 `agent-06` 在线，STG 上 `agent-06-stg` 在线。
4. STG 演练两件、PROD 一件只改 Console 的目标全部走完；PROD 那件的 `verify.json` 里有 Console 的 lint、test、build。
5. Mac Pro 的 agentd 停掉、规则收紧之后，Mac Pro 合盖 30 分钟，PROD 上的任务照常领、照常交。

## 7. 随后要改的仓库文件（A 做完我改，PROD 的那份等你点头）

- `k8s/overlays/platform-{prod,stg}/config/topology.yaml`、`bifrost-platform/config/topology.yaml`：06 改成不在集群里、角色是 Agent 主机。
- `AGENT_FACTS.md` 节点表；`scripts/k3s/rolling-reboot.sh` 的默认节点；`k8s/data/drills/pitr-drill-cluster.yaml` 偏好的节点（现在写的是 06）；`Makefile` 的 `k3s-join-ubt-k3s-06` 和 `scripts/k3s/join-ubt-k3s-06.sh`（删）。
- auto mode 的描述文字（`claude/auto-mode/project.autoMode.json` 里的节点列表）：我改 payload，你用 `apply-auto-mode.sh` 应用。
- `RUNTIME-PLACEMENT-2026-10-11.md` 第 4、5 节。
