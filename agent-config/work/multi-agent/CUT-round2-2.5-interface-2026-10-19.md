# 切法：2.5 界面——Console 完全由接口生成，本机看板退役（W-31，2026-10-19 设计稿）

**一句话**：PROD Console 现在有两个数据来源——运行时和平台自己的接口（Crew、参谋长对话、目标卡、叫停、主机、额度池、审批、提问、线程心跳），以及本机看板 `~/agent-work/status/board2.py` 每 15 秒推上去的一份文档（`PUT /api/v1/agent/progress`）。后者还撑着 9 块：计划栏、架构对照、统筹方留言、统筹方的活与步骤、需要你里的「统筹方的条目」、最近、动态、额度读数（Claude 窗口）、手写标记。2.5 把这 9 块逐一换到运行时，分 5 片，终点是 v5 的 T24：停掉本机看板程序，PROD 页面照样对。今天只出设计，不写代码。

**依据**：v5 §5.5、§9；`SPEC-agentrt-progress-2026-10-14.md`（第 3 版）；Owner 10-16 采纳的驾驶舱方向（For you / Chief of staff / Work / System，复杂性收进详情页）；`CUT-plan-import-2026-10-19.md`（计划进运行时，已上 PROD `2b101cd` #47，PROD 还没导入）。代码读的是 `bifrost-platform` `origin/main` `b40867a`（10-19 11:45）。

## 1. 现状：每块读的是什么

两个来源的读法：

- **运行时与平台接口**：`useNeedsYou` 每 5 秒读 `GET /api/v1/agentrt/progress`（`console/src/pages/shell/needs-you/useNeedsYou.ts:49`，`AGENT_RUNTIME_POLL_MS`），另有 `/agentrt/messages/thread`、`/agentrt/pools`、`/agentrt/attempts/{id}/actions`、`/agentrt/goals`、`/agentrt/missions/{id}`、`/agentrt/tasks`、`/agentrt/events`、`/agentrt/artifacts`、`/agentrt/controls`；平台自己的审批、提问、线程心跳（`/api/v1/agent/threads`）、告警、节点、发布记录。
- **本机看板文档**：同一个 hook 每 15 秒读 `GET /api/v1/agent/progress`（`useNeedsYou.ts:50`）。写方是 `board2.py` 的 `publish()`（`board2.py:817-835`）：`node publish-result.js` 把整份文档 `PUT` 到 PROD，再推一份到 STG（`192.168.10.73:30876`）；平台只存最近一份（`api/internal/agentprogress/handler.go:31`），超过 5 分钟页面标「过期」（`console/src/api/agentProgress.ts:22`）。文档约 490 KB，顶层键：`works`、`owner_now`、`recent`、`feed`、`coordinator`、`roadmap`（`round`、`arch`、`stages`、`groups`、`exit`、`goal`、`note`…）、`usage`、`queue` 等；输入是 `tasks.json`（统筹方手写）、`coordinator.json`、`roadmap-groups.json`（`roadmap.py` 解析 WORK.md 生成）、`usage.json`（本机 `usage.py`）、`feed.json`、派工记录。

逐块（✎ = 看板文档，● = 运行时或平台接口）：

| 入口 | 块 | 文件 | 来源 | 读的字段 |
|---|---|---|---|---|
| For you | 判断条（Verdict） | `pages/shell/owner/OwnerConsolePage.tsx:27`；`ownerModel.ownerVerdict` | ●，但「Yours」数里含 ✎ | Yours 数、审批数、运行中、发布通道、节点 |
| For you | 全部叫停 / 恢复 | `owner/OwnerStop.tsx` | ● | `/progress` `controls` |
| For you | Yours（要你做的） | `owner/OwnerYou.tsx:45`；`needs-you/useNeedsYou.ts:109-126` | ● + ✎ | 审批（待批 / 到终端跑 / 待核对）、提问、静默线程、主机失联、运行时 `needs_you`，**加看板 `owner_now`**（`useNeedsYou.ts:110` 的 `coordinatorWaiting`） |
| For you | 值得一看 | `owner/OwnerYou.tsx:59` | ● | 告警 |
| Chief of staff | 对话 | `owner/ChiefConversation.tsx`；`api/agentRuntimeBus.ts:55-58` | ● | `/messages/thread?with=seat:chief_of_staff`、`POST /messages` |
| Work | Now（运行中 / 卡住 / 未结目标、上一件结果） | `owner/OwnerWork.tsx:19-32` | ● | `/progress` `work.missions`、`/missions/{id}` |
| Work | Now 卡里的「Coordinator」一行（统筹方在做 / 下一步） | `owner/OwnerWork.tsx:35-39` | ✎ | `coordinator.doing`、`coordinator.next` |
| Work | Crew（每台主机在做什么、动作流） | `owner/OwnerCrew.tsx`、`AttemptActionLine.tsx` | ● | `/progress` `hosts`、`live`、`missions`；`/attempts/{id}/actions` |
| Work | 计划（The plan） | `owner/OwnerWork.tsx:45-59`；`ownerModel.planRows` | ✎ | `roadmap.round` |
| Work | 额度（Quota，Work 上那张） | `owner/OwnerWork.tsx:61-69`；`ownerModel.quotaRows` | ✎ | `usage.pools` |
| System | 健康、发布通道、节点、数据 | `owner/OwnerSystem.tsx`、`OwnerData.tsx` | ● | 告警、发布窗口与记录、节点、数据新鲜度 |
| System | 额度池（含 Owner 录读数） | `owner/OwnerQuota.tsx` | ● | `GET /agentrt/pools`、`POST /pools/{id}/reading` |
| 详情 Progress | 需要你预览 | `progress/ProgressPage.tsx:69`、`ProgressNeedsPreview.tsx` | ● + ✎ | 同 Yours |
| 详情 Progress | 目标卡（Goals） | `progress/GoalCard.tsx`、`agents/GoalForm.tsx` | ● | `/goals`、`/missions`、`/tasks`、`/events`、动作流 |
| 详情 Progress | 概览（Overview） | `progress/ProgressOverview.tsx` | ● + ✎ | 运行时 `live`；看板 `works`、`roadmap.round`、`roadmap.arch`、`usage` |
| 详情 Progress | 统筹方的活（Coordinator 区） | `progress/ProgressPage.tsx:76-81`、`AgentWorkBoard.tsx` | ✎ | `coordinator`、`works`（统筹方派的活和每一步）、`queue`、`owner_next` |
| 详情 Progress | 计划与架构对照 | `agents/AgentsPlan.tsx` | ✎ | `roadmap.round`、`roadmap.arch` |
| 详情 Progress | 主机 | `progress/ProgressPage.tsx:83` | ● | `/progress` `hosts` |
| 详情 Progress | 历史（今天做完的、已结束的活、动态） | `progress/ProgressPage.tsx:84-86`、`ProgressActivity.tsx` | ✎ | `recent`、`works`（已结束）、`feed` |
| 详情 Progress | 提交血缘、代码健康 | `ProgressPage.tsx:94-95` | ● | 平台 |
| 详情 Needs you | 统筹方的条目 | `progress/ProgressNeedsYou.tsx:111`、`:287`；`progressPart.ts:11` | ✎ | `owner_now`（建议、在哪办、怎么回） |

看板文档里推上去但 Console 不读的：`owner_items`、`owner_all`、`graph`、`events`、`standing_items`、`verdict`、`watchers`、`published` 等——退役时一起消失，不用迁。

## 2. 新框架下每块改由哪个接口生成

| 入口 | 块 | 2.5 的来源 | 缺什么 |
|---|---|---|---|
| For you | Yours | 只来自**有入口**的条目：审批（含「到终端跑」）、提问（含运行时的决策卡）、静默线程、主机失联、运行时 `needs_you`；去掉看板 `owner_now` | 无新接口；改规矩（§3 第 1 行） |
| For you | 判断条 | 同上，口径不变 | 无 |
| Chief | 对话 | 不变 | 无 |
| Work | Now、Crew | 不变 | 无 |
| Work | 计划 | `GET /plan?root=R2`（树、每步状态和状态事件）+ `GET /progress` 的 `plan`（项的计数，同一条计数规则）+ 一次读导入请求产物取每步原行的标记时间（`planimport.FromPlanWithRequest` 的规则，TS 照写） | 无新接口。前提：PROD 导入 R2（Owner 回导入卡，排在 T26 之后） |
| Work | 统筹方在做 / 下一步 | **G3** | 见下 |
| Work | 额度 | 只用 System 那张（`GET /pools`），Work 上这张删掉或改读 `/pools` | **G7** |
| Work | 预计时间 | `GET /progress` 每件事的 `eta`（现在固定 `unknown`） | **G8** |
| System | 额度池 | 不变；加能力成绩 | **G9** |
| 详情 | 架构对照 | 运行时的 `ARCH` 根（v5 §5.1.2：每行的勾按门禁测试对照当前部署算） | **G2** |
| 详情 | 统筹方的活（works / steps / queue） | 退役：活由运行时的 mission、任务、尝试表达（v5 §9 第 2 行）；统筹线程自己在线程里做的活只经线程心跳（`/agent/threads`：标题、最后活动）露面，不算计划步骤 | 无新接口；按设计删掉这一区 |
| 详情 | 历史：最近、动态 | 运行时事件（步骤做完、任务收下、尝试失败、决定、导入）+ 平台发布记录 | **G6** |
| 全站 | 「✎ 手写」标记、「看板过期」提示 | 随看板一起去掉 | 无 |

**缺口与选项**（按 CLAUDE.md §5；凡改公开接口、加路由或表列的都要定）：

- **G2 架构对照**。运行时有 `arch_root` / `arch_row`（v5 §5.1.2），`GET /progress` 已为它留了位置但一律 `tick: unknown`（`store/progress.go` `planView`）；今天的 14 行没有一行指定了门禁测试和钉住的规格摘要，「现在实际是什么」那段文字也没有列可放。
  - A（推荐）：导入 `ARCH` 根和 14 行；每行的完成规则按 v5 写成 `gates_passed`（逐行定测试编号和规格 sha256，定不了的行先写「未接测试」，勾显示 unknown 并写原因）；「现在实际是什么」写成这一行上的 `note` 事件，页面显示最新一条。要一条新路由 `POST /plan/{id}/notes`（只收 `arch_row`、只追加、propose 角色），以及 `GET /progress` 的 `plan` 每行带最新一条 note 的文字（改公开接口）。
  - B：只导入行和规则，不放文字；文字留在 WORK.md，页面链过去。不改接口，但页面看不到「现在是什么」，Owner 用它核对理解（10-13）。
  - C：架构对照整段放一个按版本更新的产物（`handover` 类），统筹线程每次改就传一份新的，页面读最新那份。不改接口，但勾仍是手写，和 v5「勾由测试算」相反。
- **G3 统筹方在做 / 下一步**（`coordinator.json`）。
  - A（推荐）：统筹线程用现有的 `send_message` 给 `owner` 发 `note`；Work 卡显示「最近一条来自统筹线程的 note」和它的时间。不加路由、不改鉴权：Owner 在 Console 用的 admin 令牌在运行时就是 `owner`（`agentrtapi/propose.go:33-34`），`GET /messages/thread?with=thread:<统筹线程>` 对 owner 放行（`agentrtapi/messages.go:230-233`）。页面要知道哪个线程是统筹线程：Console 的一个配置值（统筹线程的会话 id），换线程时改一次。
  - B：交给参谋长：Work 卡显示参谋长最新一份简报（`brief` 任务的产物）。不加路由，但简报是定时生成，不是统筹方此刻在做什么。
  - C：删掉这张卡，Work 只显示运行时的事实。
- **G6 最近与动态**（`recent` 手写行、`feed`）。
  - A（推荐）：`GET /events` 允许不带 `stream`、按 `after_event_id` 跨流读，可按类型过滤（改公开接口，小）；页面把步骤做完、任务收下 / 拒、尝试失败、决定、导入、叫停合成一条时间线，发布记录从平台已有的发布接口并进来。
  - B：Console 自己按已知的流（`plan:R2`、进行中的 mission）逐个轮询、在前端合并。不改接口，但流一多就是 N 个请求，看不到新出现的流。
  - C：新开 SSE 路由订阅 `agrt:events`（v5 §5.5 写了「可选」）。实时，但要新路由和 Redis 读，第一版不值。
- **G7 额度读数**。今天 Claude 的窗口和各池用量来自本机 `usage.py`（看板 `usage`）；运行时的 `vendor_pool` 读数只有 Owner 在 System 页手录（`POST /pools/{id}/reading`，admin）。看板一停，自动读数就停。
  - A（推荐，第一版）：页面只读 `GET /pools`，每池显示读数时间，过期就标「旧」；不改接口。自动读数放到 2.4 补强。
  - B：`agentd` 在心跳里带它在 Agent 主机上读得到的用量（改 agentd 协议，算改公开接口）。
  - C：Agent 主机上一个小作业用新的 `measure` 角色令牌定时 `POST /pools/{id}/reading`（新鉴权角色）。
- **G8 预计时间**（SPEC 缺的第一样，另一半「动作流水」2.3 已经做了）。运行时已经按岗位和任务类型算「往常用时」（30 天里被采纳的尝试，至少 3 个样本，`store/progress.go:264` `usualTimes`），只用来判「慢」。
  - A（推荐）：`GET /progress` 每件事的 `eta` 从固定 `unknown` 改成：每个没结束的任务按往常用时估，样本不足的算不出就整件 `unknown` 并写哪一个缺；给的是区间（中位到 1.5 倍），附依据（改公开接口：字段含义变了）。
  - B：Console 用已有的 `usual_s` 自己算。不改接口，但口径分到两处。
  - C：维持 unknown。
- **G9 能力成绩**（SPEC 缺的第三样）。`capability_score` 有表、没有读路由。
  - A（推荐）：新路由 `GET /capabilities`（viewer）：每个执行者 × 任务类型的成绩、样本数，和在用的能力事实；System 的额度池旁边一张卡。
  - B：并进 `GET /pools` 的回应（改公开接口，但池和能力不是一回事）。
  - C：页面不放，只经 MCP 看。
- **要 Owner 在终端跑命令的事**（SPEC 缺的第二样）：平台已有 `owner_run_command`（D 级，Runner Owner，`api/internal/actions/catalog.go:440`），批了之后出现在 Needs you 的「到终端跑」一组（`needs-you/needsYouGroups.ts:63-79`）。所以不缺接口，缺的是规矩：统筹线程要 Owner 跑命令时建这种单，不再写进 `tasks.json`。代价是每条命令先批再跑两步；要更轻，另做一种「只要跑、不用批」的提问（改提问的公开接口）——推荐先用现有的。

## 3. 只有手写才有的东西，各落到哪

| 手写在哪 | 内容 | 落到运行时的哪里 |
|---|---|---|
| `tasks.json` 每步的 `needs_owner` 和 `advice` / `where` / `reply` / `urgency` / `deadline` / `blocks` | 要他做的事：建议、在哪办、怎么回 | 每一件都必须是一张决策卡（提问：正文 = 建议，选项 = 怎么回，`recommended`、`meanwhile` = 不回会怎样、`owner_duty`、截止）或一张审批单（待批 / 到终端跑 / 待核对）。「在哪办」由条目种类决定（问题页 / 审批页 / 终端），不再写文字。没有入口的等待不进「要你做」，写在那件事的状态里（SPEC §1 A15②）。计划里的「（你）」步骤：挂着卡或单的随卡出现；没挂的只在 Work 的计划里标「（你）」 |
| `coordinator.json` | 统筹方在做 / 下一步 / 给你的话 | G3 |
| `tasks.json` 的 `recent` | 手写的「最近」行 | G6：从事件生成 |
| `tasks.json` 的 `works` / `steps` / `queue` | 统筹方派的活、每一步、排队原因 | 运行时的 mission、任务（`proposed` 的依赖和等待原因在 `GET /progress` 每个任务的 `status` / `reason` 里）、尝试；统筹线程在线程里自己做的不再列 |
| `feed.json` | 每一步的状态变化和备注 | G6 |
| `usage.json`（`usage.py`） | Claude 窗口、各池用量 | G7 |
| `roadmap-groups.json` 的 `groups`、`stages`、`exit`、`goal`、`note` | W-n 的分组、阶段条、退出条件 | `round` 换成运行时计划（G 无）；W-n 分组和阶段条按 v5 §7 第 4 条留在 WORK.md，页面不再显示（或只放一个链接）；退出条件就是各项的 ★ 步骤 |
| `roadmap.arch` | 架构对照 | G2 |

## 4. 切片

每片照旧：核心 Claude 写、Codex 复核；Console 部分可交 Codex 照接口写、Claude 验收；STG 先，PROD 走发布单。估时只算写和复核，不含等 Owner。

| 片 | 做什么 | 验收 | 估 |
|---|---|---|---|
| ① 计划进 PROD | 按 `CUT-plan-import` §5：冻结 WORK.md 第 2 轮表 → 生成请求 → 本机测试库试导 → STG 导入卡 → PROD 导入卡（T26 之后）→ WORK.md 换成指针；Owner 签 `plan-standing`（导入后） | 两个环境 `diff` 0 处；`GET /plan?root=R2` 与冻结时的台账逐步相同 | 我 2 小时；Owner 2 张卡 + 2 份规则签名 |
| ② 计划栏改读接口 | Console 的 `AgentsPlan`、Work 的「The plan」、概览的轮进度改读 `GET /plan` + `/progress`（TS 版 `FromPlanWithRequest`）；看板停推 `roadmap.round`（只留 `arch` 到 ⑤） | 停掉 `board2.py` 推 `round` 后三处照常；Console 测试用真实 PROD `GET /plan` 回应做夹具（教训：验收要拿真实接口形状） | 半天到 1 天 |
| ③ 要你做的只来自有入口的条目 | 去掉看板 `owner_now`；统筹线程的要求改成卡或 `owner_run_command`；Needs you 里「统筹方的条目」一组删掉 | 停掉看板，同一组种下的卡和单，Yours 数和列表不变；每一条都有能点的入口 | 半天 |
| ④ Work 与历史来自运行时 | G3、G6、G7（A）、G8；删掉「统筹方的活」区和 Work 上的手写额度卡；最近 / 动态改成事件时间线 | 停掉看板，Work、Progress、历史都由接口生成；没有 ✎ 标记 | 1–1.5 天 + 复核两到三轮 |
| ⑤ 架构对照与 T24 | G2；看板四件退役（`board2.py`、`roadmap.py`、`index.html`、`publish-result.js`）；`PUT /api/v1/agent/progress` 和主机心跳路由并排一周后删 | **T24**：停掉 Agent 主机上的看板程序和 `agentd`（或合盖）后，PROD 的计划和架构对照与 `GET /plan` 一致，那台主机 3–4 分钟内显示「宿主失联」，它上面的尝试不显示「在做」；v4 §20.5 十个场景各一遍；「结果未持久化」「计划外」「人工」三种标记各一例 | 1–1.5 天 + Owner 批发布单 |

合计约 4–5 天（不含等 Owner）。②③可以并行（文件不重叠：② 在计划栏三处，③ 在 needs-you）；④ 依赖 G3 / G6 / G8 的决定；⑤ 依赖 G2 的决定和 ① 的 PROD 导入。

## 5. 要定的事

**已定（Owner 2026-10-19 12:2x「2.5 八条照建议」）**：1–8 全部按推荐——G2 A、G3 A（信箱 note）、G6 A（`GET /events` 跨流）、G7 A、G8 A、G9 A（`GET /capabilities`）、要他在终端跑的事先用 `owner_run_command`、统筹方的活和 W-n 分组从页面去掉。

| # | 问题 | 推荐 | 属 |
|---|---|---|---|
| 1 | G2 架构对照：A 导入 + 门禁规则 + 每行 note（新路由、改 `/progress`）/ B 只导入行和规则 / C 整段产物 | A | 新路由、改公开接口 |
| 2 | G3 统筹方在做什么：A 信箱 note / B 参谋长简报 / C 删卡 | A | 无新接口（Console 加一个配置值） |
| 3 | G6 最近与动态：A `GET /events` 跨流 / B 前端逐流 / C SSE | A | 改公开接口 |
| 4 | G7 额度读数：A 只读 `/pools`、标读数时间 / B agentd 带读数 / C measure 角色 | A（自动读数放 2.4 补强） | 无（A） |
| 5 | G8 预计时间：A `/progress` 给区间和依据 / B 前端算 / C 维持 unknown | A | 改公开接口 |
| 6 | G9 能力成绩：A `GET /capabilities` / B 并进 `/pools` / C 不放 | A | 新路由 |
| 7 | 要他在终端跑的事：先用现有 `owner_run_command`（先批再跑）/ 另做「只要跑」的提问 | 先用现有的 | 规矩 |
| 8 | 统筹方的活和 W-n 分组从页面去掉（活只由运行时表达，W-n 留在 WORK.md） | 照此 | 规矩 |

## 6. 不在这一次

- 搬 mini 虚拟机（第 3 轮）；推理网关、业务租户。
- 台账（`TECH_DEBT.md`、`RATCHETS.md`）进运行时（v5 §8，第 3 轮或以后）。
- 设计系统 v2 的视觉改动：本稿只定数据从哪来，外观照现有组件。
