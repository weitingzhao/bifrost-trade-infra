# 箭8 Coordination / 沟通 · 章程（2026-11-16，11-19 更新合约和现状；原 8.2 沟通台面，含 11-15 对重叠的裁决）

标记：【量】= 读 `bifrost-platform` main 或实测；【推】= 推断。
一句话：各家 Agent 之间**能递话、递得省、闲着能被叫醒**；发布窗口**排队叫号**；把**别的线的状态直接给做事的人看**。

## 1. 管哪块（坏了叫我）
- 平台 MCP 的通讯部分（`mcp/platform/src/`）：`doorbell.ts`（等信命令）、`messageEnvelope.ts`、`messageTools.ts`、`registerMessages.ts`、`windowTools.ts`；`presence.ts` 是**代管**（线程在线归领域 2，它转正前由我管）。
- 窗口的排队、通知、接续：`delivery/window_queue.go`、`window_notify.go`、`server/window_notify.go`。其余窗口代码归 CI 线；改 `window_store.go` 两边互相复核。
- 等信协议和等信命令归我；Codex 机器上怎么常驻归算力线。
- **下一代沟通层**（主统筹 11-16 派，整件归本线）：交规和登记表在 platform `api/internal/bus/`（底座子领域 0.2 总线，本线建）；席位记录、信箱、调度器归领域 8。
- 「发布现场」只读口子 `GET /api/v1/delivery/context` 和 MCP `get_release_context`（在做）：STG/PROD 跑的提交、main 头、在跑的运行、同仓库待批、窗口、Owner 最后一次批卡或答题的时间、还没变成机器检查的教训。主统筹和值班说状态也读它。
- 在线和能不能被叫醒的数归我出；席位现状归值班台账。席位地址不手抄：`list_sessions`（`linked: true`）给标题和会话号，地址是 `thread:<会话号>`；派给 Codex 的活，地址写在派活说明里。
- 不管：信箱的表和存储（`agentrt.message`、`store/coord.go`，底座）；把教训做成拒建检查（领域 5）。

## 2. 对外合约（Owner 2026-11-16 OWNER_LAW #28：评我这块只对着这一节做黑盒测试）

合约栏改了要升 version 并告知使用方；只加不改的直接过。设计：共享笔记 `duty/from-agent-tool-comm-2026-11-16-subscriptions-and-contract.md`。

| 形式 | 开放的东西 | 合约里承诺什么 | 谁在用 |
|---|---|---|---|
| 存储（文件） | 主题登记表 `platform api/internal/bus/registry/<tenant>.yaml` | 主题名、address、subject 形状、key、guarantee、ref 形状、lane、retention | 各门（发方）、所有订阅方 |
| 存储（文件） | 订阅表 `bus/registry/subscriptions/<tenant>.yaml` | 一行 = 哪类事件、match/change、交付方式（wake/action/notify）、交给谁；只决定谁被叫，不带授权 | 分发器（workers） |
| 事件格式 | 信封：CloudEvents 1.0，扩展 tenant/env/cursor/ref/actor/causeid/traceparent/change/key，不带数据、≤2 KiB | 字段名和语义 | 所有订阅方 |
| 事件流 | NATS `ev.<tenant>.<env>.<type>`；回执 `rcpt.<tenant>.<env>` | subject 形状、回执头 `Bifrost-Event-Id`/`Bifrost-Consumer` | 平台进程（api、workers） |
| 接口 | `GET /api/v1/bus/events`（types、match、after、wait、client）、`/bus/stream`（SSE）、`/bus/trace` | 参数、返回 `{events, next}`、长轮询最长 25 秒 | Console Bus 页、MCP `wait_for_event`、`bifrost-bus wait`、门铃 |
| 接口 | MCP `send_message`、`wait_for_messages`、`read_message`、`ack_messages`；`get_release_window`、`hold_release_window`、`release_release_window`；`get_release_context` | 参数和返回形状 | 各席位、值班、主统筹 |
| 指令 | ~~门铃 `scripts/bus/doorbell.mjs`~~ **停用（2026-11-16）**：另起平台 MCP 进程读令牌，踩「席位不另起进程调平台、不读令牌」的边界 | — | 无 |
| 指令 | 等信命令（平台信箱）`mcp/platform/src/doorbell.ts`（`--minutes N`） | 来信就退出，打印信号、发件人、种类、字节数 | 各席位 |
| 事件 | 窗口通知 `window.your_turn`、`missed`、`queue_timeout`、`still_held` | 种类名 | 排窗口的席位 |
| 存储（文件） | 订阅表的行字段（11-19 起）：`on`、`match`、**`except`**（subject 含它就不算本行，只增）、`change`（一个值或 `!值`）、`deliver`、`to`、`params`（`ask_verdict`、`always_namespaces` 等）、`envs` | 不写 `except` 的行照旧匹配 | 分发器、alert-letters |
| 接口 | 问题闭环 `GET /api/v1/bus/problems`；去向表现算 `/bus/nextgen`；谁在听 `/bus/observe`、`/bus/clients`；效果 `/bus/effect`；合约 `/bus/contract` | Bus 页读的都是现算，不手抄（法 30） | Console Bus 页、主统筹简报 |
| 指令 | 问题判断：给 `controller` 发 `kind: note`，正文 `{"v":1,"type":"problem_verdict","summary":"…","text":"{\"event\":\"ev-N\",\"verdict\":\"real｜false\",\"outcome\":\"handled｜source_fixed｜open\",\"ref\":\"…\"}"}`；summary 一行、≤300 字节 | 格式不对的在 Bus 页列为 Not counted，不计入闭环 | 收到问题信的席位 |
| 接口（Console 内） | 实时刷新 `console/src/domains/foundation/bus/liveRefresh.ts`：每个标签页一条 `/bus/stream?client=console-live`；`LIVE_REFRESH` 表（事件类型 → 查询键前缀）；页面用 `useLiveInterval(原毫秒)`（流连着放慢到 5 分钟，断了回原值）、`useLiveRefreshConnected()` | 事件只做失效通知，数据仍读原路由；表里的类型由测试对照登记表 | 箭10 的 Command 页（11-19 起），其他页逐个接 |

本线发的主题：`seat.mail.arrived`（信箱写信同一事务）、`approval.card.*`（审批流）、`alert.rule.fired`（Alertmanager webhook）、`ci.verdict.changed`（证据账，代 CI 线发）。git、ci.run、release.window 由门·git、门·集群发。别的领域登记的主题（例如计划的 `plan.tree.changed`，11-19）由各自领域发，本线只管登记表的规矩。

标准（11-19，`nextgen/step4-standards.md`）：浏览器推送用 SSE（`id`／`retry`／`Last-Event-ID`），信封 CloudEvents 1.0，NATS 只在 API 后面，页面「事件只做失效通知」。Console 用 bearer 令牌，所以用 fetch 读流而不用原生 EventSource，线上格式仍是标准 SSE。

## 3. 谁用它，它用谁
- 用户：每个席位（收发信、等信、排窗口、看现场）、值班、主统筹、Codex 工人（算力线在接）。
- 它用：信箱存储和事件日志（底座）；平台认身份（`X-Bifrost-Session` → `thread:`）；窗口 ConfigMap（CI 线）；发布记录（`releases`，CI 线）；审批与问题；workers 进程（只有它推进队列）。

## 4. 权限
- 自己定、做到底、事后评（Owner 11-15）：上面代码的改动和合入（`ready/<名字>`）；只读口子；不碰信任锚的 platform 发布，`check_release_policy` 覆盖就直发；替别的线做非作者复核。
- 机器拦着的：auto mode 分类器（旧会话另起进程记复核被拦过两次；复核改由新开的会话做）；`preflight.js`；平台 422「not a registered actor」；碰信任锚的 platform 发布在新条款重签前只走卡，各线攒进同一张卡（CI 线牵头）。
- 硬边界不碰：交易和钱（D10）、Trade 五个仓库；令牌、口令、Secret、Owner 凭证；kubectl 写集群；改规则本身和 auto mode；`seat:` 身份防线。
- 想在窗口、信箱上加环节：先写三问，答不出不加，加了写什么时候撤（Owner 11-15）。

## 5. 目标和读数
目标：问题发得出来、被看到、有人判、真问题处理、假问题修源头（法 36）；信不丢、闲着的能叫醒、收信省 token；Console 不靠轮询追新（第 4 步，Owner 11-19 定做）；排窗口不用盯。
读数都在 Ops → System → Bus 现算（法 30），这里只记读的时间和数：
- 问题渠道：48 接入 / 48，待定 0；真实证据 30、只靠演练 18（11-19 08:0xZ 宣布换代）【量】。
- 闭环（7 天）：发出 18、判断 18、关闭 8；到看到中位 41 分钟、到判断 1 小时、到关闭 2 小时（11-19 14:0xZ）【量】。
- 换代步骤：第 3 步 42/42 已切（11-19 15:3xZ PROD）【量】。
- 已量：只给摘要时收信从 2881 字符降到 646；叫醒约 7 秒（各量一次）【量】。
- 还没有数：丢信数、your_turn 延迟、叫醒成功率；Console 改推送后读口请求数的前后对比（等 PROD 后按 `http_request_duration_seconds_count` 同口径量）。

## 6. 现状和缺口
- 在 PROD：总线（NATS + 账本）、去向表现算、问题渠道全接、闭环、问题信发主统筹、info 告警一天一封；服务端各连接共用读库、空闲连接不读库（222142ad，11-19）【量】。
- 在 main、待发版：Console 一条流和对照表（b6819618 起）；箭10 的 Command 页接入在 ready。
- 缺口：闭环开着的 10 条等各自源头；只靠演练的 18 条渠道等真实故障；Trade 发布路径 5 条等 Trade 恢复发布；`/bus/observe` 偶尔两秒多（一次扫 6 万条回执，法 41 要修）；等信命令不重试 429、505–599；窗口全平台一个（v2）；Codex 叫不醒。

## 和谁有重叠（主统筹 11-15 已裁）
- 窗口按文件分（见第 1 节）；线程在线归领域 2，`presence.ts` 我代管；等信协议归我、Codex 常驻归算力线；席位现状归值班台账、在线的数归我；教训的机器检查归领域 5，读口只放还没变成检查的，一条变成检查就从读口撤掉。
