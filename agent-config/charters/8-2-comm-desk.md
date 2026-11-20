# 箭8 Coordination / 沟通 · 章程（2026-11-16 起，11-20 按 Owner 定的边界重写）

标记：【量】= 读 `bifrost-platform` main 或实测；【推】= 推断。
一句话：模块之间「发生了什么」都能被发出来、被送到、被看见、有人判；闲着的席位能被叫醒；发布窗口排队叫号。

## 0. 边界（Owner 2026-11-20 在本线线程里定）

- **管**：模块之间的事件、信、叫醒；各模块的**状态变化**（起来了、挂了、被 cordon、版本变了、备份成败），按法 37「要保留的模块都和总线连通」逐类补上总线。
- **不管指标**：CPU、内存、延迟这类连续采样的读数，告警规则，系统定时记下的评估读数，归 coordination 下的**指标线**（11-20 提议开线，主统筹在开）。交界：读数越过门槛，规则归指标线写；变成 `alert.rule.fired` 送到人、闭环，归本线。
- **不管模块清单**：系统一共有多少模块、各属哪个领域，归**解耦线**的模块总清单。本线只读它当分母，不自己定（裁判和运动员分开）。
- **原则**（Owner 2026-11-20）：单独分出来的模块都要有和别的模块沟通的需求，否则并入或删。本线出事实（每个模块发什么、听什么、谁在读），由解耦线和各领域判。

## 1. 管哪块（坏了叫我）

- 总线：`platform api/internal/bus/`（登记表、订阅表、中继、门·集群、门·git、门·库、去向表、问题闭环、Bus 页的读口）。NATS 本体在 infra `k8s/bus/`（data 命名空间）。
- Console 实时层：`console/src/domains/foundation/bus/`（`liveRefresh.ts` 一个标签页一条流、`useBusStream.ts` Bus 页的流、Bus 页各区）。
- 平台信箱和等信：`mcp/platform/src/` 的 `doorbell.ts`、`messageEnvelope.ts`、`messageTools.ts`、`registerMessages.ts`、`busWait.ts`；`presence.ts` 代管（线程在线归领域 2）。信箱的表和存储归底座。
- 发布窗口的排队、通知、接续：`delivery/window_queue.go`、`window_notify.go`。其余窗口代码归 CI 线；改 `window_store.go` 两边互相复核。
- 发布现场只读口 `GET /api/v1/delivery/context`、MCP `get_release_context`。

## 2. 对外合约（OWNER_LAW #28：评本线只对着这一节做黑盒测试）

合约字段改了要升 version 并告诉使用方；只加不改的直接过。`registry/contract.lock.json` 守着：合约字段变了版本没升，`contract_test.go` 红。

| 形式 | 开放的东西 | 承诺什么 | 谁在用 |
|---|---|---|---|
| 存储（文件） | 事件登记表 `bus/registry/<tenant>.yaml`（AsyncAPI 3.0） | 每类事件的 version、address、subject、key、guarantee、ref、retention、domain、发布方 | 各门、所有订阅方 |
| 存储（文件） | 订阅表 `bus/registry/subscriptions/<tenant>.yaml` | 一行 = 哪类事件、`match`／`except`／`change`、交付方式（wake／action／notify）、交给谁；只决定谁被叫，不带授权 | 分发器、alert-letters |
| 事件格式 | CloudEvents 1.0 信封，扩展 tenant／env／cursor／ref／actor／change／key；不带数据，≤2 KiB | 字段名和语义 | 所有订阅方 |
| 事件流 | NATS `ev.<tenant>.<env>.<type>`；回执 `rcpt.<tenant>.<env>`；只在 API 后面 | subject 形状、回执头 | 平台进程 |
| 接口 | `GET /api/v1/bus/events`（长轮询 ≤25 秒，游标续读）、`/bus/stream`（SSE，`Last-Event-ID` 续读，15 秒心跳）、`/bus/trace`、`/bus/contract`、`/bus/clients`、`/bus/observe`、`/bus/nextgen`、`/bus/problems`、`/bus/effect` | 参数和返回形状；Bus 页读的都是现算（法 30） | Console、MCP `wait_for_event`、门铃 |
| 接口（Console 内） | `liveRefresh.ts`：`LIVE_REFRESH`（事件类型 → 查询键）、`useLiveInterval(原毫秒)`、`useLiveRefreshConnected()`；流 45 秒无字节就重连（`LIVE_IDLE_MS`，Bus 页的流同样） | 事件只做失效通知，数据照旧读原路由；表里的类型由测试对照登记表 | Console 各页、City |
| 接口（MCP） | `send_message`、`wait_for_messages`、`read_message`、`ack_messages`；窗口 `get/hold/release_release_window`；`get_release_context` | 参数和返回形状 | 各席位 |
| 指令 | 等信命令 `doorbell.ts --minutes N` | 来信就退出，打印发件人、种类、字节数 | 各席位 |
| 指令 | 问题判断：给 `controller` 发 note，正文 `{"v":1,"type":"problem_verdict","summary":"一行 ≤300 字节","text":"{\"event\":\"ev-N\",\"verdict\":\"real｜false\",\"outcome\":\"handled｜source_fixed｜open\",\"ref\":\"…\"}"}` | 格式不对的列为 Not counted | 收到问题信的席位 |

本线发的事件：`seat.mail.arrived`、`approval.card.*`、`alert.rule.fired`（Alertmanager webhook）、`ci.verdict.changed`（代 CI 线）；门·集群发 `ci.run.*`、`release.window.changed`、`release.gitops.changed`、`git.mirror.settled`、`data.job.finished`，2026-11-20 起加 `cluster.node.changed`（节点 Ready、cordon 变化）。别的领域登记的事件（如计划的 `plan.tree.changed`）由各自领域发，本线只管登记规矩。

标准：SSE（Console 用 bearer 令牌，所以用 fetch 读流，线上格式仍是标准 SSE）、CloudEvents 1.0、AsyncAPI 3.0、NATS JetStream 在 API 后面、页面「事件只做失效通知」。

## 3. 谁用它，它用谁

- 用户：每个席位、值班、主统筹、Console 各页（Command、Bus、City）。
- 它用：平台库的事件账和信箱（底座）；集群只读 watch（平台身份的 observer 角色：节点、工作负载、CNPG、Tekton、Argo）；解耦线的模块清单（分母）；指标线的告警（经 Alertmanager）。

## 4. 权限

- 自己定、做到底：上面代码的改动和合入（`ready/<名字>`）；登记新事件类型（只加不改，带只增迁移，按法 32 由 `run_agentrt_migration` 跑）。
- 要 Owner 的：删有数据的东西、写 data 命名空间（例：卡 #656 把 NATS 挪出 05）；改裁判规则（领域墙、CI 检查）。
- 硬边界不碰：交易和钱（D10）、令牌和 Secret、kubectl 写集群、auto mode 规则。
- 想在窗口、信箱上加环节：先写三问，答不出不加，加了写什么时候撤（Owner 11-15）。

## 5. 目标和读数（读数在 Ops → System → Bus 现算，这里只记最近一次）

- 换代：153 条通道里该切的已切，旧路已拆 31 条，剩 X-C6（等算力冻结台账）、X-B3（判留：删它要改治理检查）【量，11-20】。
- Console 不靠轮询追新：PROD 8 个读口 30 分钟 860 → 约 108（11-19 22:10Z，系统存档）；每个客户端 30 分钟读动作记录 9–10 次，原先 30 次（11-20 03:2xZ，临时读数）。
- 问题闭环（7 天）：发出 33、判断 20、关闭 10（11-20 03:5xZ，Bus 页）【量】。
- 应收尽收：接上总线的模块 / 全部模块。分母等解耦线的清单；在那之前按集群里实际在跑的 107 个负载算【量，11-20】。

## 6. 缺口（按顺序）

1. 状态变化事件：节点（已推 ready）→ 关键负载就绪 → 数据库和备份 → Redis、IB、行情 → 硬件（告警挂到主机）。
2. 统一的模块状态读口：每个模块在不在、版本、最后变化时间、在总线上有没有事件；Bus 页的「根本没接」和 City 都读它。
3. 黑盒隔离没做到：总线以外 12 个包（17 个文件）直接 import 总线内部包。收成对外 SDK 是加领域墙（改裁判），写成提议交解耦线和 Owner。
4. 总线中继报错、NATS 不可用没有告警（11-20 停了约 75 分钟没有专门告警），交指标线第一周补。
