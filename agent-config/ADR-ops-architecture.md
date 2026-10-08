# ADR — Ops 维护与 Ops Platform 的目标架构

- **状态**：已采纳（Owner 2026-10-07）。**落地顺序还没定**，由后续计划另写；本文只定「应该是什么样」。
- **适用**：新增、搬动或删除任何维护者（会自动运行、会改东西的程序）、Ops Platform 的功能与界面、Agent 的凭证与审批、备份、网络分区。冲突时以本文为准，并修正冲突的一方。
- **不在本文**：TWS 与两台 Win11 的维护（放在所有优化最后单独处理）；D10 交易冻结不变。

## 1. 定位

业务终极目标不变：Ops 让 Trade 跑得更快更稳，AI 承担大部分工作。变的是实现方式（Owner 2026-10-08 改写本节）：

**AI Agent（Claude Code、Cursor、Codex 等，不绑定一家）是执行者。Ops Platform 是它们共用的仪器、护栏和调度底座。**
它提供三样东西：

- **事实**：探测、版本、血缘、维护者存活；
- **护栏**：动作目录、审批、发布队列、D10；
- **调度**：任务与租约、交互总线、推理网关、额度账本，对开发和业务两个租户通用。

平台不启动 Agent，也不替 Agent 做判断：Agent 主机上的守护进程主动来领任务，规划者席位提出计划，控制器只在 Owner 批准的范围内校验、记账、放行。UI 只给 Owner 用于看状态、审批和追溯。设计见 §12 与 `work/multi-agent/DESIGN-agent-runtime-2026-10-08.md`（讨论稿）。

Ops Platform 收成四层，全部只在 PROD 一份：

| 层 | 内容 |
|---|---|
| 事实层 | 带时间与来源的探测信号、维护者清单与存活、各环境运行的版本、工作项与提交血缘 |
| 动作层 | 具名、确定性、有审计的写操作（API / MCP 调用），外加护栏：发布窗口与发布队列、D10、审批 |
| 调度层 | 多 Agent 运行时：mission、任务与租约、交互总线、产物与验收、推理网关、额度账本（§12） |
| 呈现层 | Console：回答 Owner 的 7 个问题（§6） |

保留还是删除平台上的一项功能，按三个问题判断：Agent 经 API / MCP 用它吗？Owner 用它来批、签、看吗？有维护循环依赖它吗？三个都答「否」，就删（删除前 Owner 过目）。

## 2. 四条判据

1. **按「什么坏了它还得活着」放置。** 维护集群和数据的在集群里；看守集群的在集群外（Mac mini）；看守 mini 的是集群与两台 mini 互看。
2. **动手权按信任分级，级别决定位置与凭证**（§5）。确定性修复只在 PROD 集群里；Agent 不常驻写凭证、只提议或申请。
3. **每件维护事只有一个修复者**，其他人只看。
4. **每个维护者都登记、有存活信号、坏了能呼到 Owner**（§7）。

## 3. 机器放置

| 机器 | 定位 | 应该跑 | 不该跑 |
|---|---|---|---|
| Linux k8s 节点 | 生产底座，确定性修复的唯一所在 | Trade dev/stg/prod；Postgres、Redis；Dagster（数据养护唯一调度者）；插件；PROD platform-workers；备份；监控告警；交付（Argo、Tekton、registry） | LLM Agent 执行面；任何依赖笔记本的东西 |
| NAS | 存储与备份第二份 | MinIO（物理备份）、nfs-hot / nfs-cold、归档、逻辑 dump、各机器的备份 | 计算、调度 |
| 4090（.60） | 可唤醒算力池 | 本地 LLM 推理、重型回测与构建；PROD 按需唤醒、用完关机 | 常驻服务；维护关键路径 |
| Mac mini .50 / .52 | 带外层 + Agent 层（A 方案） | 宿主（独立系统账户）：operator-plane、告警中转、互看 watchdog、集群外拨测、应急手册。虚拟机：Claude Code 线程、Agent SDK harness、沙箱 | 常驻集群管理员凭证；定时 LLM「修复」；带外与 Agent 共用账户和配置 |
| Mac Pro | 开发 + Owner 驾驶舱 | IDE、Vite、bdev 本地服务、kubectl / MCP 客户端、Claude 线程 | 任何维护；任何被 PROD 依赖的服务 |
| Win11 ×2 | 交易设备 | 只有 TWS（Owner 手工登录 + 2FA），从外面观测 | 其他软件（以后可加维保进程，单独决定） |

## 4. Ops Platform 的环境角色

| | 本机 Mac Pro | STG | PROD | Mac mini |
|---|---|---|---|---|
| 角色 | 只开发 Ops Platform 本身 | 发布彩排 | **唯一的运行控制面** | 带外应急 + Agent |
| Owner 日常 Console | 只在改 Console 时 | 不用 | `ops.bifrost.lan` | PROD 挂了才用 |
| MCP / Claude 线程连接 | 不连 | 不连 | **全部** | 应急子集 |
| 动手与审计 | 无 | 无（RBAC 只读） | 全部 | 只有应急子集 |
| 后台维护 | 无 | 无 | 全部 | 只看守 PROD |
| 状态 | 临时 | 可丢 | 唯一真相 | 自己的心跳 |

只属于 Owner 笔记本的功能（dev-sessions、git-bridge）不是 PROD 的功能，留成本机工具；PROD 不依赖它们。
PROD platform 坏了时的应急路径：mini 上的 operator-plane，或 Owner 手动 kubectl / Argo 回滚。

## 5. 动作分级与审批

| 级 | 例子 | 谁能直接做 | 批准 |
|---|---|---|---|
| A 只读 | 状态、日志、指标、只读 SQL | 所有 Agent | 不需要 |
| B 可逆、低风险 | 重启无状态服务、IB 重连、补采某日数据、重跑失败 CI、发 STG、克隆数据到 DEV | Agent；autopilot 试运行期后 | 不需要，事后可查 |
| C 生产变更 | 发 PROD、Argo 同步 PROD、STG / DEV DDL | Agent 发起 | Owner 逐次批 |
| D 不可逆或对外 | PROD DDL、删数据、删备份、节点关机 / drain / 重启、UniFi 改动、Secret 变更、对外发消息 | Agent 只能申请 | Owner 逐次批，必要时亲手做 |
| X 禁止 | 下单、daemon 扩容、写 `ib:operator:cmd` | 无人 | 只有 D10 解锁 |

- 写操作都是 PROD 平台上的具名动作，由平台用自己的受限身份执行；目录外的写操作走兜底动作「Owner 批准执行这条命令」，命令全文进审计。
- **凭证**：Agent（Mac Pro、mini、Cursor）只拿只读令牌、申请令牌与只读 kubeconfig；集群管理员身份只在 Owner 手里应急用。分阶段收：先把写操作收进动作目录，最后换只读。
- **审批交互（形式从简，不用 Face ID）**：PROD 平台一张申请单列表（谁申请、动作、参数、理由、回滚、谁在哪批的）。三个入口看同一张表：
  - 聊天：Claude 应用弹出的「允许」点击即批准（C、D 级都可）；签收同样在聊天里点一下；
  - 手机：ntfy 推送，点开进 Console 审批页（在外用 UniFi VPN）；
  - Console：「待你批 / 待你签」页。
- 审批规则：批的是什么就只执行什么（参数签进审批）；一次批准执行一次；过期作废。聊天文字「批了」与其他线程转述都不构成审批，以审批记录为准。
- Agent 不得用浏览器工具访问审批页（preflight 拦截）。
- **发版策略（Owner 2026-10-08 选择，实现中：`cursor-tasks/LANE-RP-release-policy.md`）**：C 级的**发版**动作若命中 Owner 签过的发版策略（ConfigMap `cicd/bifrost-release-policy`：允许的流水线、条件——main 或 tag、该 SHA 的 CI 通过、持有发布窗口、无待办 DB 步骤、不含 DDL、不触 D10——与有效期），平台自动批准并执行，审计记下命中的策略条款；不命中照旧等人批。**失败即关**：策略缺失、过期、读不出来或设了冻结位，一律不自动批。D 级永远不自动。策略不设次数上限；到期前 48 / 24 / 2 小时手机推送 + Console 横幅提醒 Owner 重签。依据：`agent-config/work/release-approval/PROPOSAL-2026-10-08.md` §3、§7。
- **已知的接受风险（Owner 2026-10-07 选择）**：聊天里批准靠 MCP 工具 `bifrost-approve` + Claude 的「允许」弹窗，工具需要的 admin 令牌在本机进程可读。同一台机器上的 Agent 理论上能读到它、绕过弹窗直接调审批接口；目前只靠 preflight 的文本拦截挡一挡。Owner 的取舍是先简单快，「今后感觉不行，再收权」——收权的做法是把 admin 令牌只留在手机与 Console 浏览器里，聊天只展示申请与链接。

## 6. Console：7 个问题

| 问题 | 动作 |
|---|---|
| ① 现在一切正常吗？（一句结论 + 红项） | 只看 |
| ② 今天的数据到齐了吗？（行情、Flex、Research、备份） | 补采、Doctor 修复 |
| ③ 和 IB 的连接正常吗？ | 重连 |
| ④ 维护者在做什么、要我批 / 签什么？ | 批准、驳回、签收、打回 |
| ⑤ 发布到哪了？（只读：各环境版本、在途、失败、血缘） | 至多一个回滚应急 |
| ⑥ 集群与机器（节点、网络、mini、NAS、4090、TWS 主机、待重启节点） | 只留应急与经审批的动作 |
| ⑦ 项目进度（§8） | 签收 |

- 健康类页面只看 PROD；STG / DEV 只在⑤里作为一列出现。
- 退场：Console 内的 Agent 派发（runner 派发、Operate Queue、决策简报、Hermes 工作台、各页「AI Fix」）、Vision 关卡与 Tier-B 签字、发布驾驶舱（改为⑤的只读视图）、Guides 静态页（回到仓库文档；Vision 的终极目标并入本文 §1）。删除前由 Owner 过目。
- CI/CD 的流水线与 API / MCP 能力保留；发版只走 Claude / MCP / `release.sh`。

## 7. 维护者清单与存活

- `agent-config/MAINTAINERS.yaml`：每个维护者一行——维护什么、在哪跑、何时跑、最高动作级（A–D）、靠哪条告警发现它坏了。
- 每晚在集群里对账：清单 vs 实际（CronJob、Dagster schedule、platform 后台循环、mini 的 launchd），多出或缺少都告警。**新增维护者必须先进清单。**
- 存活信号用现有 Prometheus / Alertmanager；清单每行必须对应一条存在的告警；platform 后台循环导出「上次成功时间」。
- 告警只分两档：**呼 Owner**（critical → ntfy）与**记账**（warning → PROD Console ④）。STG 不在告警链路里。
- 节点补丁：Console ⑥ 显示待重启节点；重启是 D 级「滚动重启」，Owner 周末批，一次一台（不用 kured）。

## 8. 工作项与进度

- 进度是算出来的，不人工维护。
- 一个工作项登记（infra `agent-config/`，沿用 TECH_DEBT 的五种状态、验收命令、待你签收），覆盖全部工作线：债、计划、Cursor LANE。
- 计划、评审、申请、LANE 任务与报告都放进 infra `agent-config/`（版本控制），不放在工作区根目录。
- 每个提交带 `Work: <编号>` 尾注（git hook 补，防线保证不漏）；线程标题带编号。
- 进度视图按工作项拼出：状态与验收 → 线程 → 提交 → 到达的环境 → 是否待签；顶部为待你签收、在途、本周上线、卡住。PROD Console ⑦ 为主，claude.ai 页面为导出版。

## 9. 备份

副本原则：线上（Linux 节点盘）+ NAS；不用云。NAS hot / cold 同在一台 NAS，防误删、不防 NAS 本身损坏（Owner 接受，以后可能再加一台 NAS）。

| 级 | 包含 | 能丢多少 | 恢复用时 | 副本与留存 |
|---|---|---|---|---|
| 1 手工 / 状态 | Trade 三库；GS 的 journal、research、ops_feedback、raw_broker；Secret；集群状态 | 几乎 0（WAL）；逻辑 dump 最多 1 天 | 1 小时内 | 线上 + NAS（物理 + 每日逻辑 + etcd 快照与 Secret 加密件）；cold 每月一份留 12 个月 |
| 2 不可再生行情 | option_snapshot、option_open_interest | ≤ 1 天 | 1 天内 | 线上 + NAS 物理 30 天 + cold 归档（不删） |
| 3 可再生 | 其余行情、features、dw_stock、作业日志 | 不在乎 | 重拉重算，几天 | 线上 + 物理 30 天，不做长期留存 |

- etcd 快照与 Secret 加密件每天复制到 NAS。
- 物理备份每月一份全量放 cold，保留 3 个月。
- 恢复演练：逻辑备份每月；时间点恢复每季度（恢复到临时库、核对 1、2 级行数、删除），第一次尽快；etcd 写好恢复步骤，复制后检查可读。
- Mac Pro 与 mini 上只存在本机的重要文件也备份到 NAS。

## 10. 网络

Server 区一分为四，其余网段（Work、Family、Home/IoT）不变：

| 分区 | 成员 | 能访问 | 不能访问 |
|---|---|---|---|
| 交易区 | Win11 ×2 | 只出到 IB | 内网一切；入站只放 k8s 节点→TWS API 端口与 Owner 工作站远程桌面 |
| 集群与存储区 | k3s 节点、VIP、NAS、4090 | 彼此；出互联网 | — |
| Agent 区 | mini 上的沙箱虚拟机 | 平台 API、GitHub、外网白名单 | 数据库、Redis、TWS、NAS 共享、K8s API、节点 SSH |
| 运维区 | Mac Pro 有线口、mini 宿主 | 集群全部（靠凭证收口） | — |

- UniFi：平台保留可写权限，凭证只在 PROD；任何改动是 D 级、Owner 审批；目标规则在 git 里。
- 交易区迁移（TWS 换 IP、IB Gateway 配置跟改）与 TWS 问题一起最后做。
- 手机外出审批走 UniFi 自带 VPN（届时单独审批）。

## 11. 起点（2026-10-07 实测，用于衡量差距）

- Owner 日常用本机 Console；`.mcp.json` 6 个 MCP server 全连本机 platform（集群管理员 kubeconfig、本地状态，检查信号停在 09-29）；当天发布动作全经本机，PROD 审计 0 条；STG platform 7 天无人访问。
- Console 17.4 万行、约 45 个导航项、三种视角；两个任务中枢重叠；「Trade 健康吗」5 处回答、默认环境各不同；Console 内 Agent 派发自 8 月后基本停用。
- 维护者散在 8 种运行时、无清单；.50 每晚以集群管理员身份跑 LLM 检查并静默失败；PROD 依赖本机 git-bridge。
- 所有 warning 告警送往 STG platform，无人查看；.73 / .75 自动更新 6 月后未装包、09-11 起待重启；时间点恢复从未演练；etcd 快照只在 .73 本机盘。
- 计划、评审、LANE 文件在工作区根目录，无版本控制。
- UniFi Super Admin 凭证只在本机 `.env`；Server 区内部无隔离。

## 12. 多 Agent 协作

- **状态**：方向已定（Owner 2026-10-08，见 12.7）。来源：`work/multi-agent/BRIEF-2026-10-08.md`。
- **正在改写（2026-10-08）**：Owner 把议题扩成一个多 Agent 运行时，同时服务开发和业务两个租户（§1 已改写）。讨论稿是 `work/multi-agent/DESIGN-agent-runtime-2026-10-08.md`，已定的部分列在它的第 12 节。
  - 12.3 的认领与待办箱，将由运行时的任务租约和交互总线取代；
  - 12.4 的发布队列保留，作为对外副作用的闸门；
  - 下面 12.1–12.7 是改写前的版本，讨论定稿后整体替换。
- **范围移交（Owner 2026-10-08）**：ops-arch 线程（「Ops Platform 瘦身」）只做瘦身。下面两项从它那里移交给多 Agent 协作线程（W-31），因为它们会由运行时的任务数据与 Agent 主机层给出：
  - 第 4 阶段剩下的部分：D1 的 platform 部分（`/api/v1/progress`、MCP `get_progress`）不合并，Console ⑦ 的进度视图也不做；
  - 第 6 阶段：mini A 方案、Agent 虚拟机、网络分区。
  
  ops-arch 也不碰下面这些：运行时、发布队列、RP 发版策略、认领 / 待办箱、工作项编号规则。
- **适用**：任何 Agent（Claude Code 线程、Cursor、Grok Bot，以后的 Codex），不论在哪台主机，认领工作、发版、交接、请 Owner 批或签。

### 12.1 问题

Agent 工具多、线程多、主机多，争用的是同样四样东西：代码、发布通道（一个窗口、一个 PROD）、台账，以及 Owner 的注意力（批准与签收）。现有的协调手段有本机 `SendMessage`、Mac Pro 上的窗口文件、Grok 的提示词和 Owner 转话，全都要求 Mac Pro 开着、对方线程还活着。2026-10-08 一天内出了这些事：

- 一次批准被窗口冲突作废（TD-267）；
- 同一个 Console bug 修了两遍（TD-261）；
- Grok 起的 Claude 轮次结束后，消息发不过去；
- Owner 只能用 curl 批 PROD 的单子；
- 两个协调者各自起道号，撞了名（12.5）。

### 12.2 原则

1. **靠共享状态协调，不靠互相发消息。** 所有 Agent 只读写同一处 24 小时在线的事实，不需要知道别人是谁、是否还活着。
2. **这一处是 PROD platform-api，不另起服务。** 它已有鉴权、审批、审计和状态备份；§4 定它为唯一的运行控制面；这些内容不涉及 Trade 业务，过得了克隆测试。STG 与本机的 platform 都不承载协调状态。
3. **平台不启动 Agent，也不替 Agent 做判断**（按 2026-10-08 改写后的 §1）：计划由规划者席位提出，控制器只在 Owner 批准的范围内校验、记账、放行租约，Agent 主机上的守护进程主动来领。
4. **强制只有一处：发布队列。** 认领只提示，不拦截。
5. **不做**：平台内的派发与调度；汇总各主机的对话记录；Agent 之间的聊天总线。

### 12.3 四样东西

| | 内容 | 强制 | 期 |
|---|---|---|---|
| ⓪ 身份 | 每个「工具 × 主机」一个令牌（`claude@pro`、`cursor@pro`、`grok@mini50` 等），最高到 operator，不给 admin。平台按令牌主体记录调用方，不信请求体里自报的名字；同一令牌下的多个线程用会话头区分。提交带 `Agent:` 尾注：有钩子的工具由钩子补，没有钩子的由 CI 标「无归属」 | 写操作必须带自己的令牌 | 令牌第 1 期；尾注第 2 期 |
| ① 认领 | 开工前认领一个工作项（编号见 12.5），带心跳续约，过期自动释放。谁都能看到「X 从几点起在做 Y」 | 只提示 | 2 |
| ② 发布队列 | 见 12.4 | **强制**：所有发版的唯一通道 | 1 |
| ③ 待办箱 | 交接和「需要 Owner」的事项（批准、签收、验收报告）发给角色或工作项，不发给某个线程。发给 Owner 的走 ntfy 推送到手机 | 只提示 | 2 |

### 12.4 发布队列

- **权威迁进平台**：发布窗口的权威从 Mac Pro 的 `~/.bifrost-release/window.json` 迁进 PROD platform；`release.sh window / hold` 改为调平台。流水线与 `start_pipeline_run` 读到的窗口由平台写出。
- **窗口变成队列，并发为 1。** 任何身份都能提单，排到队首且前提满足才执行。单子有两种：
  - 平台能执行的发版动作（起流水线、Argo 同步），由 platform-workers 里的执行器按顺序执行；
  - 在主机上跑的发布（`release.sh stg|prod`、推 main），排到队首时领到窗口租约，由主机自己执行。
- **批准与执行分开**（TD-267 并入）：
  - C 级发版需要批准，来源是 Owner 点（聊天、手机、Console），或命中 §5 的发版策略。策略里「持有发布窗口」一条改为「单子在队首，由队列持有窗口」。
  - 批准只表示单子可以执行。窗口被占、CI 没跑完、有 run 在途都是暂时的前提，单子继续排队，不消耗批准；只有永久错误才判失败。
  - B 级（发 STG 等）不需要批准，但照样排队。
- **钉住提交号**：提单时解析出 SHA，批准针对这个 SHA。执行前若目标分支已不在这个 SHA 上，就不执行，单子转为「需重批」并推送给 Owner。
- **租约**：持有窗口的主机进程定时续约。续约断了（进程死了，或 Mac 睡了），平台收回窗口；收回前先看它起的 run 是否还在跑，在跑就等 run 结束再放。残留锁不再需要 Owner 清，TD-269 的根因也就没有了。
- **过期**：排队超过 24 小时的单子自动过期，并推送通知。
- **不变的**：哪些动作要 Owner 批（§5）、D10、PROD DDL 规则都不变，队列只是通道。
- **平台不可用时**：由 Owner 手动走旧路径（本机窗口文件 + kubectl），属于 §4 的应急路径。Agent 不走这条路。

### 12.5 工作项编号全局唯一

- **现状**：TD-n 由 `TECH_DEBT.md` 发号，W-n 由 `WORK.md` 发号，两者各自唯一。`LANE-<字母>` 却是各个计划目录自己起的，两个协调者撞了名：Grok 在 `work/cursor-tasks/` 派的 `LANE-A2`、`LANE-C`，与 `work/ops-arch/` 里的同名道重复。`Work:` 尾注和进度接口都按字面匹配，提交会被算到别人的道上。例如，还债台账的提交 92b4b0f 带 `LANE-C`，会被并进 W-9（Console 重组）。
- **规则**：只用一个编号空间、只有一个发号处，两个方案待 Owner 选（`PHASE1-OPTIONS` 第 5 节）。推荐的做法：
  - 新工作项（含 Cursor 道）一律用 `W-n`，在 `WORK.md` 发号；第 2 期起改由平台原子发号；
  - 已有的 `LANE-*` 冻结为别名，只在唯一时有效，撞了名的作废。

### 12.6 接入方式与机器分工

- **统一接口用 MCP**：四样东西做成 `bifrost-platform` MCP server 的几个工具（大致是 `whoami`、`request_release` / `get_release_queue`、`claim_work` / `release_claim`、`post_handover` / `list_inbox`）。不支持 MCP 的工具直接打 HTTP。
- **同一段约定写进每个工具的规则文件**：Claude 是 `CLAUDE.md`，Cursor 是 `.cursor` 规则，Codex 是 `AGENTS.md`，Grok 是它的提示词。约定只有三句：先认领再开工；发版只提单，不占窗口；交接写进待办箱。
- **能用钩子的就用钩子**：Claude 的 SessionStart / Stop、Cursor 的 `hooks.json`，用来自动续约和释放认领。
- **Mac Pro**：Owner 的驾驶舱和交互线程所在。它睡了，协调照常；只是跑在它上面的线程会停。
- **Mac mini 的 Agent 虚拟机**（§3 的 A 方案）：放 Grok Bot 和 headless 的 claude / cursor / codex。每个 Agent 有自己的 git 克隆和令牌，不再共用 Mac Pro 上的单一工作树。
- **看状态**：PROD Console 的 ④（待批 / 待签）、⑤（发布与队列）、⑦（工作项、认领、提交、到了哪个环境），不另开页面。
- **8787 看板**（`~/der-relay/dashboard`）冻结，不再加功能，以后只当本机的对话记录查看器。

### 12.7 分期、决定与待定

| 期 | 内容 |
|---|---|
| 1 | 发布队列：窗口迁进平台、队列、钉提交号、TD-267；每个工具的令牌；Console ⑤ 显示队列；本机 Console 审批页标明「本机环境」并给出跳到 PROD 的链接；编号规则（12.5）及其防线 |
| 2 | 认领、待办箱、`Agent:` 尾注；钩子；三句约定写进各工具的规则文件；Console ④⑦ |
| 3 | Grok Bot 迁到 mini 的 Agent 虚拟机（与 ops-arch 第 6 阶段一起做）；Codex 按同一套约定接入；8787 冻结为查看器 |

**Owner 已定（2026-10-08）**：

1. 协调状态放在 PROD platform-api，不另起服务。
2. 8787 冻结，协调与发布状态进 Console。
3. 认领先只提示、不拦截，强制只在发布队列。
4. 本议题单开一个线程，ops-arch 线程不分心。

Grok Bot 暂停中，恢复条件是第 1 期上 PROD。

**待定**：

- 第 1 期的接口与存储；
- 编号方案；
- Grok Bot 在 Mac Pro 上靠什么执行命令（它决定迁到 mini 的难度）。
