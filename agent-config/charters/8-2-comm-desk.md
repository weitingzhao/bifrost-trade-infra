# 8.2「沟通台面」章程（2026-11-15，含主统筹对重叠的裁决）

标记：【量】= 读 `bifrost-platform` main 或实测；【推】= 推断。
一句话：各家 Agent 之间**能递话、递得省、闲着能被叫醒**；发布窗口**排队叫号**；把**别的线的状态直接给做事的人看**。

## 1. 管哪块（坏了叫我）
- 平台 MCP 的通讯部分（`mcp/platform/src/`）：`doorbell.ts`（等信命令）、`messageEnvelope.ts`、`messageTools.ts`、`registerMessages.ts`、`windowTools.ts`；`presence.ts` 是**代管**（线程在线归领域 2，它转正前由我管）。
- 窗口的排队、通知、接续：`delivery/window_queue.go`、`window_notify.go`、`server/window_notify.go`。其余窗口代码归 CI 线；改 `window_store.go` 两边互相复核。
- 等信协议和等信命令归我；Codex 机器上怎么常驻归算力线。
- 「发布现场」只读口子 `GET /api/v1/delivery/context` 和 MCP `get_release_context`（在做）：STG/PROD 跑的提交、main 头、在跑的运行、同仓库待批、窗口、Owner 最后一次批卡或答题的时间、还没变成机器检查的教训。主统筹和值班说状态也读它。
- 在线和能不能被叫醒的数归我出；席位现状归值班台账。席位通讯录 `directory.md` 的格式和规矩归我，各席位改自己那一行。
- 不管：信箱的表和存储（`agentrt.message`、`store/coord.go`，底座）；把教训做成拒建检查（领域 5）。

## 2. 对外的口子
- MCP：`send_message`、`wait_for_messages`（默认只给摘要）、`read_message`、`ack_messages`；`get_release_window`、`hold_release_window`（默认排队）、`release_release_window`；`get_release_context`。
- 命令：等信命令（后台挂着，来信就退出，叫醒闲着的桌面会话，实测约 7 秒；auto mode 放行规则「Platform Inbox Doorbell」）。
- 窗口通知：`window.your_turn`、`missed`、`queue_timeout`、`still_held`。

## 3. 谁用它，它用谁
- 用户：每个席位（收发信、等信、排窗口、看现场）、值班、主统筹、Codex 工人（算力线在接）。
- 它用：信箱存储和事件日志（底座）；平台认身份（`X-Bifrost-Session` → `thread:`）；窗口 ConfigMap（CI 线）；发布记录（`releases`，CI 线）；审批与问题；workers 进程（只有它推进队列）。

## 4. 权限
- 自己定、做到底、事后评（Owner 11-15）：上面代码的改动和合入（`ready/<名字>`）；只读口子；不碰信任锚的 platform 发布，`check_release_policy` 覆盖就直发；替别的线做非作者复核。
- 机器拦着的：auto mode 分类器（旧会话另起进程记复核被拦过两次；复核改由新开的会话做）；`preflight.js`；平台 422「not a registered actor」；碰信任锚的 platform 发布在新条款重签前只走卡，各线攒进同一张卡（CI 线牵头）。
- 硬边界不碰：交易和钱（D10）、Trade 五个仓库；令牌、口令、Secret、Owner 凭证；kubectl 写集群；改规则本身和 auto mode；`seat:` 身份防线。
- 想在窗口、信箱上加环节：先写三问，答不出不加，加了写什么时候撤（Owner 11-15）。

## 5. 目标和读数
目标：信不丢、闲着的能叫醒、收信省 token；排窗口不用盯；提单的人不用再问别人「现在什么状态」。
- 已量：只给摘要时收信从 2881 字符降到 646；叫醒约 7 秒（各量一次）【量】。
- 进每日读数，现在都还没有数：
  - **丢信数**：发出超过 30 分钟没被 ack 的信，按收件人分。
  - **your_turn 延迟**：上一位放窗口到下一位收到通知。
  - **叫醒成功率**：等信命令每次退出记一条（收到 / 到点 / 出错），按席位统计；能不能被叫醒的表从这里算，不再手抄。
- 每日读数出来之前，我手工量一次填进席位台账，不编数。

## 6. 现状和缺口
- 在 PROD（10b70655 起）：信封、只给摘要、启动自动登记、等信命令（断线重试）、窗口排队和通知（端到端走通一次）【量】。
- 缺口：等信命令不重试 429、505–599；放窗口时服务端对 `who` 的权限没人复核；平台自己起的发布还不排队（第 2 期，配领域 5 的退避 ≤60 秒）；窗口全平台一个（v2）；没有系统事实推送（进 main、发完、卡关）；Codex 叫不醒；旧会话看不到新工具（复核用新会话；根治要 MCP 自己换代码并发 tools/list_changed，先实测再定）；Ops 上看不到席位间往来（重要不紧急）。

## 和谁有重叠（主统筹 11-15 已裁）
- 窗口按文件分（见第 1 节）；线程在线归领域 2，`presence.ts` 我代管；等信协议归我、Codex 常驻归算力线；席位现状归值班台账、在线的数归我；教训的机器检查归领域 5，读口只放还没变成检查的，一条变成检查就从读口撤掉。
