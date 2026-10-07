# ADR — Ops 维护与 Ops Platform 的目标架构

- **状态**：已采纳（Owner 2026-10-07）。**落地顺序还没定**，由后续计划另写；本文只定「应该是什么样」。
- **适用**：新增、搬动或删除任何维护者（会自动运行、会改东西的程序）、Ops Platform 的功能与界面、Agent 的凭证与审批、备份、网络分区。冲突时以本文为准，并修正冲突的一方。
- **不在本文**：TWS 与两台 Win11 的维护（放在所有优化最后单独处理）；D10 交易冻结不变。

## 1. 定位

业务终极目标不变：Ops 让 Trade 跑得更快更稳，AI 承担大部分工作。变的是实现方式——
**AI Agent（Claude Code 线程、Cursor）是执行者，Ops Platform 是 Agent 的仪器和护栏，UI 是给 Owner 的状态、审批与追溯。**
Ops Platform 不再托管或派发 Agent。

Ops Platform 收成三层，全部只在 PROD 一份：

| 层 | 内容 |
|---|---|
| 事实层 | 带时间与来源的探测信号、维护者清单与存活、各环境运行的版本、工作项与提交血缘 |
| 动作层 | 具名、确定性、有审计的写操作（API / MCP 调用），外加护栏：发布窗口、D10、审批 |
| 呈现层 | Console：回答 Owner 的 7 个问题（§6） |

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
