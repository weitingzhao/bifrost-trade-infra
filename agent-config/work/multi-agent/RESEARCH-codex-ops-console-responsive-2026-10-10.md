# Bifrost Ops Console 手机和平板适配审查

2026-10-10，第一阶段，只读审查与实施建议。Owner补充要求后，方案主线已修订为[Owner业务价值与UI方案](/Users/vision-mac-trader/agent-work/ops-console-responsive-review/BUSINESS-VALUE.md)，以目标、规则、不可逆判断及处理结果为核心。本文保留响应式测量和文件重叠作为工程依据；下文适配顺序以新方案为准。适配保留 Owner 已定的 Needs you 首页、八个问题、Verdict → Body → Actions，以及 Needs you / In progress / History 的业务结构；新业务定义继续由 W-31 统筹。

## 代码与运行基线

| 对象 | 核对结果 |
|---|---|
| 共享 platform main 与本地 origin/main | `7cda6cb`；未提交项 `agent/governance/`，本任务未触碰 |
| 本地 w31/console-int | `58928a3`，落后最新集成线，不能用作实施基线 |
| 已保存的 origin/w31/console-int | `11ebb8c32fabf7d1f49ce3d1a4f5260d9df2f0f3` |
| STG 运行 Console | Releases 实测 Platform STG = `11ebb8c`，ui = `9b635b2`；与计划 0.7 的 run `bifrost-deliver-platform-1791643757` 一致 |
| PROD 运行版本 | STG Releases 的 PROD 列显示 platform `efeaf69`、ui `9b635b2`；未直接打开 PROD 审批界面 |
| 静态源码依据 | `origin/w31/console-int`；现有 `~/agent-work/s9-console-int` 的 `5101ba3` 与 `11ebb8c` 的 console 树经 git diff 核对相同，下面行号可在该目录阅读 |

已完整阅读工作区 AGENTS / CLAUDE / AGENT_FACTS、platform CLAUDE、Codex 接入 README、STEP0-PLAN、UI-ASSESSMENT、STEP9-REMOVED-UI；最新顺序以 STEP0 0.11 为准。STG 已发，等 Owner 过目，后面还有 W-48/49/51/54 批次。当前不应把响应式改动插进正在等待过目的发布批次。

## 实测范围与限制

浏览器只打开 STG `#status`、`#data`、`#ib`、`#releases`、`#infrastructure`、`#progress`。未打开 Needs you、Maintenance、Approvals、Records 中的审批标签，未操作任何审批、请求、静音、刷新扫描或运行控件。Needs you 与审批详情只审源码。匿名会话显示 GUEST；受保护的窗口、策略、审批数据显示 Unknown，未读取或配置令牌。

浏览器 viewport 接口的输入与页面 CSS 宽度有 1.3 的换算，先用 `innerWidth` 校准，再测量；以下均是页面确认的 CSS 像素，不是设备物理像素。测试后已恢复视口。

| Status CSS 视口 | 页头状态可用宽度 | 表格宽于直接父容器的数量 |
|---|---:|---:|
| 360 × 900 | 33px | 7 |
| 390 × 900 | 63px | 2 |
| 430 × 900 | 103px | 0 |
| 600 × 900 | 273px | 0 |
| 800 × 900 | 217px | 0 |
| 960 × 900 | 377px | 0 |
| 1280 × 900 | 697px | 0 |

表格没越界不等于内容可读：430px 以后列被压缩，截断仍存在。600px 到 800px 状态反而变窄，是默认展开侧栏占去空间。另核对平板600×960/960×600、800×1280/1280×800横竖屏，页面没有全局横向溢出，800px竖屏状态区域仍只有217px。Fire Silk、手机 Safari、系统字体放大和 VPN 故障尚未真机验收。Fire HD 10 的 1920×1200 物理分辨率不能直接作为 CSS 断点。

## 按优先级处理

| 优先级 | 问题与证据 | 建议和边界 |
|---|---|---|
| P0 | Status 同屏出现 Failing（3 critical alerts）、Checklist all ok、Room posture nominal、System verdict critical。源码多个面板并列，旧评估 0.5 已登记。 | 保留现有同源系统结论，其他结论明确标注范围并放入证据区。红项摘要置前。不修改告警级别、抑制规则或系统 verdict 算法，不抢运行时阶段的 Status 重写。 |
| P0 | `ConsoleHeader.tsx:79` breadcrumb 宽度上限 28vw；`:103` 状态采用 truncate。360/390/430px 状态只有 33/63/103px。 | 手机第一行只放 Menu、完整页名、环境、User；第二行显示可换行的系统结论与更新时间。Tools 和 Help 收进明确菜单，仍可发现。页面身份只保留在 header，不加另一套页标题。 |
| P0 | 浏览器测得 Toggle Sidebar / Tools 28px、About Status 20px。共享侧栏小号项 h-7；触控依赖小按钮。 | Console 局部触控样式使交互目标至少 44×44px，平板 coarse pointer 同样适用；不是简单放大整站字号。审批详情源码已有 h-11 手机按钮（`ApprovalsPage.tsx:164,174`），保留。 |
| P0 | Needs you `ApprovalRow.tsx` 对 reason truncate；动作名、长 id 与标签混在一行。 | 一条单子显示动作/摘要、环境与级别、等待/到期、Open request。摘要换行且可展开，完整字段始终可查。编号和 summary 等待 W-48 接入，不能自造编号或丢弃命令参数。首页继续仅链接详情。 |
| P0 | `useShellStatusLine.ts` 20/30/60秒轮询；`api/core.ts`、`telemetry.ts`、`checklist.ts` 的相关 fetch 无显式 timeout/signal。SW network-first 导航无超时；API 不缓存。 | 加页面读取状态呈现：Connecting、Refreshing、Connection lost、Last updated、Data may be out of date；保留最后成功只读快照并标旧，不当作实时健康。读取超时和取消策略限于本轮触及的请求，不统一重写全站 fetch。写动作遇网络失败不自动重试，状态核对沿用现有业务协议。 |
| P1 | 390px Releases 的 Versions 每列约116px，13px文字，多仓 SHA 字段被截断；完整值仅 title。Needs you 约 y=370，In progress y=588，History y=778。`ReleasesPage.tsx:150,153` truncate。 | 手机 Versions 用应用卡片：应用名，STG/PROD 两个标注块，短版本可见，Built from 点击展开全仓 SHA；按现有数据模型呈现。Needs you 摘要进入页顶，在途卡按状态/环境/开始时间组织，历史继续收起。桌面保留表格。 |
| P1 | `denseTableClasses.ts:2` 固定表布局且 min-width 320px；Status attention 七列，Releases request 六列、history 七列，Infrastructure 有八列。 | 新增 Console ResponsiveRecordList，在窄屏渲染标签和值，宽屏保留既有 DenseDataTable。不能删关键列；完整明细在展开区。真正二维矩阵局部横滑并显示提示，不把全页变为横向滚动。 |
| P1 | Data 多个管理页纵向堆叠；Infrastructure 是 Cluster/Network/Runtime map/Mini。共享正文13px、meta11px、caption10px、micro9px（`bifrost-ui.css:45–51`）。 | 手机上关键正文14–16px、辅助信息至少12px作为适配目标；摘要入口+分区锚点，按既有异常展开/正常收起。保持所有业务数据可达，不按“美观”删除插件、备份、集群详情。 |
| P1 | OpsSection 的 details 只隐藏，不卸载；该组件已提供 onOpenChange，注释记录隐藏内容曾取数52秒。Releases 对每个 pipeline 启动轮询查询。 | 能用现有 enabled 的详情/图表在展开后取数，保持首屏健康与需要 Owner 的查询活跃。仅减少不显示的深层证据请求，不改变监控节拍的业务规则。 |
| P2 | 图表/Runtime map/网络流表密集；外部 Grafana 链接已有入口。 | 手机先显示关键值、单位、时间范围与异常，图表在全宽详情；保留外部 Grafana 链接。大拓扑用可操作的列表入口与局部滚动，不缩成微型图。真机检查横屏和触摸缩放。 |

## 布局草案

### 手机 360 至 430 CSS 像素

```text
[Menu 44] Needs you                 [STG] [User 44]
● Failing — 3 critical alerts               [Status]
Last updated 10:56 · Connected

2 waiting for you
Approve · 2
┌ Request #n · PROD · D ───────────────────┐
│ Action summary, wraps across lines      │
│ Waited … · Expires …                    │
│ Open request                        →   │
└─────────────────────────────────────────┘
Decide · …                  Sign off · …
Records →
```

数字和时间是布局占位，不能当成实测待批数据；当前 `#n` 等 W-48，Decide/Sign off 未接入时继续明确显示现有 Not connected yet。连接文字从真实读取状态推导，`navigator.onLine` 不能证明 VPN 可用。环境一直可见，审批动作不放首页。

Status：系统 verdict → 当前红项卡（信号/范围/原因/自何时/Inspect）→ In progress（W-54 提供后接入）→ 按域的完整证据。Health 和 Room posture 不再与系统结论争夺首屏，仍能展开阅读。

审批详情只做源码规划：Back → Request identity/环境/级别 → 完整摘要和参数/命令 → 现有批准与驳回区。D级命令全文保持可读且可选择，不能因卡片化而截断。是否增加确认步骤由现有 lane 的批准方案决定。本任务不调整审批语义。键盘、底部安全区和页面滚动需后续授权环境验证。

Releases：需要 Owner 的摘要 → 版本卡片 → 在途与失败卡 → 默认收起的历史 → smoke / rollback 原有入口。显式比较 STG/PROD，无 title 才能查看的信息。

### 平板

以实际 CSS 宽度和输入方式决定布局。建议 <768px 单列；768–1023px 默认收起导航，用 Menu 打开现有抽屉或短 rail，正文可放两张摘要卡；≥1024px 可保留侧栏，内容不足时仍允许收起。coarse pointer 保持44px触控目标。断点在首次独立预览时按实际组件空间调整，不改共享 @bifrost/ui 的全站默认值。

```text
[Menu] Needs you                   [STG] [Tools] [User]
System verdict                         Last updated
┌ Approve cards (main column) ┐  ┌ System summary ┐
│ request identity + summary │  │ current scope  │
│ readable params via detail │  │ Status link    │
└────────────────────────────┘  └────────────────┘
Decide / Sign off (existing state)         Records →
```

横屏 Releases 可保留应用×环境比较表；在途详细列表若关键列仍不足就转卡片。Fire 真机要记录 CSS viewport、系统缩放和 Silk 版本；不承诺安装、push 或 badge 支持，显示与触控不依赖这些能力。

### 桌面

保留现有侧栏、密集表格、字段与快捷入口。新增响应式组件通过页面 opt-in，桌面呈现沿用当前逻辑。统一旧数据提示同时适用于桌面；不全局覆盖 dense tokens。

## 与 W31 lane 的文件重叠

| Lane | 重叠文件或能力 | 处理方式 |
|---|---|---|
| W-44 shell / Needs you | ConsolePage、ConsoleHeader、ConsoleSidebar、ConsoleNavSlotItem、needs-you/*、useShellStatusLine、shellStatusLine、路由与 badges | 从最终集成树分支；适配只改布局/触控，不重新定义导航、count 或 verdict。路由和状态模型原则上不改。 |
| W-45 Releases + 集成 W-42 | shell/releases/*、ReleasePolicyBanner、useReleasePolicy | 卡片共享 releaseView 派生结果；保留策略 Unknown、14/3/1天窗口和计数逻辑。 |
| W-43a / W-43b 清理 | index.css、旧组件和孤儿 | 不复活删除的 catalog/旧 ControlRoom 面板，不从 main 复制旧文件；局部新 CSS 文件。 |
| W-46 清理 | ControlRoomPage、ObservabilityPage、ClusterPage、各插件管理页、BackupStatusPanel | 保留已清理的业务内容与删除结果；用页面新增 wrapper / 摘要接入，避免重新改旧 Agent 逻辑。 |
| W-48 / W-49 编号与通知 | api/approvals、ApprovalsPage、ApprovalRow 的 number/env/summary/deliveries 接入 | 依最终返回类型，等待其集成；不改审批状态机、令牌处理或通知协议。 |
| W-54 / W-57 线程健康 | StatusPage、useNeedsYou、api/approvals 的 viewerRead、新线程列表组件 | 响应式呈现真实线程状态，静默/等待授权由 lane 规则决定，不自行计数。 |
| W-40 进度过渡 | ProgressPage、NeedsYouPage、决定/签收计数 | 第一批不重写进度业务；组件留可复用呈现，W-n 数据集成后再适配。 |
| W-47 / W-52 设计与推送 | Needs you / 详情视觉、manifest、public/sw.js、pwa/* | 沿用已有PWA骨架。SW导航超时属于共享文件，须放单独小提交并对齐W-52；不重做推送、认证或证书。 |

## 实施阶段与验收

1. **A 外壳与读取状态**：在 `~/agent-work/` 独立 platform worktree 和独立分支，新建 `components/responsive/` 与局部样式，接入页头、导航触控、读取时间/失联表达。先不动审批与后端。选基线时再次核对 main、console-int、S0-0/W-54 最新集成树。
2. **B Needs you 与 Releases**：卡片化、新字段可读、版本明细点击展开，桌面沿用表格；依 W-48/49/54 的实际集成结果。审批详情仅源码评审；浏览器验收遵守 guard，由 Owner 或已授权审批专用流程执行。
3. **C Status、Data、IB、Infrastructure、Progress**：逐页接入摘要/明细适配；图表与隐藏详情按现有能力延迟取数。不抢团队/规则、发布队列、进度业务和 Status 架构重写。

每阶段 `tsc`、lint、build，加有意义的卡片字段完整性/状态测试和现有相关业务回归。视口：360×780、390×844、430×932；600×960、800×1280及其横屏；1280×800、1440×900。实测 innerWidth，验证页面不横向滚动、长命令/SHA/错误可读、44px触控、键盘安全区、字体放大200%、明暗主题、桌面信息完整。

网络验收：普通读取、5秒延迟、请求超时、VPN断开/恢复、401/403、首次离线与已访问后离线、页面切换中取消读取。区分 Connecting / unknown权限 / Failed读取 / Stale快照；错误不显示 Nothing needs you；不自动重发写动作。不修改VPN/UniFi/认证设置，不用断开共享网络模拟故障。

独立预览应先准备 bdev 的明确配置：只启动 worktree Console，建议候选端口5182（启动前核对 sessions 与占用，不认定当前空闲），API保持已有目标，禁止使用共享5180预览分支；不能裸起长期Vite或重启共享bdev。本阶段没有新建session。

合并前先更新最终集成基线与冲突，保留业务模型，再回归手机/平板/桌面。仅推独立分支；main/发布由W31既定流程推进，具体发布动作仍需Owner授权。本阶段到方案报告为止，不开始实施。

## 第一阶段结果

只有本报告新增于 `~/agent-work/ops-console-responsive-review/`。产品代码、现有计划文件、服务、认证、网络与集群均未改动；未发消息给Claude或Cursor。此次没有产品变更，未重跑构建或测试，也未声称Fire真机/VPN故障已通过。后续实施从上述阶段A开始。
