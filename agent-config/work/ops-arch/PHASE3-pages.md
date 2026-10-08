# 第 3 阶段：Console 每页去向表（草案，待 Owner 过目）

依据：ADR §1（仪器与护栏）、§4（PROD 是唯一运行控制面）、§6（7 个问题）。盘点基于 platform `origin/main` `e6b825b9`：44 个页面 + 41 个子组件、约 45 个导航项、三种视角，Console 共 17.4 万行。
**删除由 Owner 过目决定**——本表只给去向建议；Owner 点头的行才进 Cursor 任务。

## 新导航：7 个问题，一层，没有视角切换

| # | 导航名 | 回答的问题 | 动手 |
|---|---|---|---|
| ① | Status | 现在一切正常吗？一句结论 + 红项 + 正在响的告警 | 只看（静音 2 小时保留） |
| ② | Data | 今天的数据到齐了吗？行情、Flex、Research、备份与演练 | 补采、Doctor 修复（B 级直调） |
| ③ | IB | 和 IB 的连接正常吗？ | 重连（B）；模式切换、维护（C，走审批） |
| ④ | Maintenance | 维护者在做什么、要我批 / 签什么？ | 批准、驳回（以后加签收） |
| ⑤ | Releases | 每个应用在各环境是什么版本、在途、失败 | 只读；至多「申请回滚」（C，走审批） |
| ⑥ | Infrastructure | 集群、节点、网络、mini、NAS、4090、TWS 主机 | B 级直调；C / D 一律「申请」 |
| ⑦ | Progress | 项目做到哪了：工作项 → 线程 → 提交 → 环境 → 待签 | 第 4 阶段建成；本阶段先放 Commit Lineage |

全站规则：
- **健康类只看 PROD**（Console 所在环境），去掉各页的环境选择器；STG / DEV 只在 ⑤ 作为一列出现。
- **C / D 级按钮一律变成「申请」**：点了先建申请单，你在 ④ 或手机上批；B 级照旧直调。Owner 在 Console 里点 C / D 时，建单后直接弹出批准确认（一次多点一下），审计照样完整。
- **外壳不再每页轮询约 60 个接口**：每页只取自己的数据，顶栏只取 ① 的一句结论。
- 退场的功能，**后端端点与 MCP 工具一并删除**（不留死路由）；仍被别处使用的除外，表里注明。

## 逐页去向

| 现在的页面（导航） | 去向 | 保留 | 去掉 | 依据 |
|---|---|---|---|---|
| Approvals（Mission Control） | ④ 首页 | 全部 | — | 第 2 阶段新建 |
| Control Room（默认首页） | 并入 ① | 结论条、红项、各系统状态卡 | 发布区（LaunchPad / Promote 条 / PipelineFlow，去 ⑤）、Agent 派发按钮、Governance 区 | 与 TCC 重复回答「现在该干什么」 |
| Task Control Center（Ops / Analysis 视角） | **退场**，有用部分并入 ① / ④ | 检查清单信号（→ ①） | 整页（约 3.5 万行含依赖）、Discover→Remediate→Deploy 流程、Sweep、提交提议、Hermes 嵌入 | 与 Control Room 重复；派发机制已停用 |
| Observability | 并入 ① | 告警列表、PROD 黄金信号、Grafana 链接、静音 2 小时 | 环境选择器、Agent Fix / Diagnose | 健康只看 PROD |
| Rocket Health | 并入 ①（平台自身一张卡） | platform-api / console / Argo 状态 | 独立页面、All / Stg / Prod 选择器 | 同一份 self-health 有 6 处读 |
| Satellite Health（含 Probes、Runtime 两段） | 并入 ①（Trade 一张卡，可下钻） | PROD 的 HTTP / 鉴权 / D10 写路径探针、黄金信号 | 环境选择器 | 「Trade 健康吗」5 处回答、默认环境各不同 |
| Runtime Map（Control Room 抽屉） | 并入 ⑥（拓扑图） | 硬件 / 软件拓扑 | 环境选择器 | 属于「机器」问题 |
| Code Health | **待你定**：A 并入 ⑦ 一张卡；B 退场（`make check-code-health` 照跑） | 推荐 A | — | 工程健康也是「进度」的一部分 |
| Defects | **退场** | — | 整页（修复失败模式，来自 Agent 派发） | 派发已停用；数据源随之消失 |
| Audit | 并入 ④（历史页签） | 审计列表、下载 JSON | 独立页面 | 审批与执行的追溯 |
| Rocket（platform-release） | 并入 ⑤ | platform STG / PROD 版本、在途与失败的 run | 起流水线、发布门、Tier-B、add-on 安装、逃生演练记录、Agent 发版 | 发版只走 Claude / MCP / release.sh |
| Satellite › Trade（trade-release） | 并入 ⑤ | Trade 各环境版本、在途、失败、STG 冒烟 | 起 / 删 run、镜像同步、Dockerfile 刷新、Argo sync / rollback 按钮、发布门、Tier-B 签字、AI Deploy | 同上（回滚改成「申请回滚」） |
| Satellite › Research（research-release） | 并入 ⑤ | Research 版本、run 状态 | 起流水线、Agent | 同上 |
| Plugin（plugin-release） | 并入 ⑤ | 插件版本 | 发布按钮、IB 模式切换（去 ③）、Agent | 同上 |
| Agent（agent-release） | 并入 ⑥（mini 卡片） | runner 版本与心跳 | 「Update primary / standby」按钮、Agent | mini 部署走部署脚本 |
| Commit Lineage | 移到 ⑦ | 全部（第 4 阶段在它上面做进度视图） | — | Owner：看它其实是想看进度 |
| Queue（Agent Desk / Operate Queue） | **退场**（含后端 operate queue 与决策简报、漂移提议） | — | 整页与派发、批准 RUN、简报 | 最后一次关闭在 09-27，0 未结；简报 0 |
| Patrol + Patrol Log | 合并进 ④（「Autopilot」页签） | 技能列表、运行记录（含 REPORT-ONLY 记录）、手动运行一次 | 两页重复的运行历史 | ADR §7：autopilot 是 PROD 维护者之一 |
| Operator Plane | 并入 ⑥（mini 卡片） | 两台 mini 的 operator-plane、告警中转、互看状态 | AI Fix、nightly-run 按钮 | 夜间 LLM 已退役 |
| Trust & Autonomy | **待你定**：A 退场（autopilot 逐项放开用 git 配置 + 你批）；B 留在 ④ 当「放开哪几项」的开关 | 推荐 A | — | 形式从简 |
| Agent Capability | **退场** | — | 整页 | runner scope 就绪度，派发已停用 |
| Analysis Workspace / Insight Log / Hermes Status | **退场**；Hermes 网关健康放 ⑥ mini 卡片一行 | Hermes 健康 | 三页、首个任务按钮、insights | Hermes 网关未运行、无 LLM key；insights 0 |
| Bus Status（satellite-bus） | 并入 ③ | PROD 的 IB Gateway → redis-ib → daemon 总线 | 默认 STG 的环境选择器、跨环境对比表（去 ⑤ 不需要）、重启 / 扩容按钮改「申请」 | 健康只看 PROD |
| IB Client（ib-gateway-manage） | ③ 首页 | 连接状态、重连（B）、自愈（B） | 模式切换 / 维护改「申请」（C） | B1R 定级 |
| Research Engine | 并入 ② | 管线健康、信号健康、预测结算、token 成本 | Diagnose（打开 Agent Desk） | 数据问题 |
| Plugin Gallery | 并入 ②（顶部插件状态条） | 三个插件的状态 | 独立页面 | 插件状态 5 处读 |
| Massive（market-data-manage，约 1.26 万行） | ② 主体之一 | **全部业务能力**（覆盖、就绪、Doctor、入队、source-void） | — | 业务优先：行情是核心数据 |
| IB Flex（flex-query-manage） | ② 主体之一 | 全部业务能力 | — | 同上 |
| Cluster（含 10 个子组件） | ⑥ 主体 | 节点、工作负载、数据服务、Pod 日志、待重启节点（新增） | C / D 按钮改「申请」：cordon / drain / 关机 / 加入节点 / scale / 数据克隆 / 装组件 / 同步 kubeconfig | 机器问题；动作分级 |
| Network | 并入 ⑥ | UniFi 设备、客户端、SLA、异常 | 「apply 防火墙」改「申请」（D） | Owner：UniFi 改动要审批 |
| Dev Sessions（顶栏指示器 / Dock） | **只在本机 Console 出现** | 本机 bdev 会话管理 | PROD Console 里的入口 | ADR §4：笔记本的事不是 PROD 的功能 |
| Guides：Vision / Blueprint / Roadmap / Platform / Agent Protocol / Agent System / MCP Contract / Design System / AI Compute Strategy | **退场**，内容回仓库文档 | 终极目标已写进 ADR §1；Agent 模式与禁止动作仍以 `agentProtocolCatalog.ts` 为准（代码保留，页面删） | 9 个页面、Vision 关卡签字、`lib/architecture/` 中只为这些页面服务的静态目录 | Owner：只有终极目标有价值；关卡不再用 |
| 三种视角（System / Ops / Analysis） | **退场** | — | 视角切换与按视角隐藏的规则 | 一层导航 |

## 后端与 MCP 一起清理（随页面退场）

| 功能 | 处理 | 说明 |
|---|---|---|
| 检查清单驱动的派发（`checklist` 的 `executeDispatch`、`husbandry-sync` 的派发） | 删除派发；`husbandry-sync` 只更新信号 | 关闭 TD-208 剩余一半 |
| Operate Queue、决策简报、漂移提议 | 删除端点与 MCP 工具 | 停用证据见上 |
| Vision 关卡、build-phase、migrate-streams、发布门、Tier-B 签字 | 删除端点与 MCP 工具（`run_release_gate`、`sign_tier_b` 等） | Owner：不再用 |
| Hermes insights / first task | 删除端点；Hermes 健康探针保留 | — |
| remediation（runner 派发） | **保留**后端 | runner 还在 .50 / .52；第 5 阶段一起收权时再定 |
| 探测器的 argo-apps 信号 | 忽略已跑完被回收的一次性 Job（如 `db-init-*`） | 还债会话核实的误报 |

## 需要 Owner 定的

1. Code Health：A 并入 ⑦（推荐）/ B 退场。
2. Trust & Autonomy：A 退场（推荐）/ B 留作 autopilot 逐项放开的开关。
3. Guides 9 页连同 Vision 关卡一起删（推荐），还是先只从导航隐藏。
4. 其余各行是否同意；有想保留的页面直接点名。
