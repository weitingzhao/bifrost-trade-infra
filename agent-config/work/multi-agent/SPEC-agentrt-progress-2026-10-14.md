# `GET /api/v1/agentrt/progress`：进展投影的接口（2.2 定，2.5 照它做界面）

**版本**：第 4 版（2026-10-21，加 `owner_next`：W-31 2.5 缺口 1，Owner 10-21「缺口 1、2 照推荐加」，复核 477）。第 1–3 版各自的问题见文末「改了什么」。

**为什么现在写**：设计 v5 §5.2 把 `GET /progress` 列在 2.2 的路由里（viewer 读；「计划、架构对照、现场、需要你」），2.5 的 Console 照「已定接口」写（§5.5）。字段和状态判定设计没写全，统筹方先定在这里；要求出处是 v4 §20.2–20.3 和 `OWNER-SURFACE-2026-10-11.md`（下称 A1…D3）。你要改就说。

## 1. 原则

- **读时现算，不存**（v4 §20.1）：每次请求在一个只读、可重复读的快照里从运行时的表和事件算一份，带 `generated_at`（数据库时钟，整份用同一个时刻判时间）和 `as_of_event_id`（快照里最大的事件号，客户端拿它做「自上次以来」的基线，A17）。
- **读不到就是未知**（A5）：数据库读失败整条路由回 **503** `unavailable`，不回旧的、不回半份。某一项算不出，就给 `unknown` 和原因，不填一个看起来正常的值。
- **按「事」组织**（v4 §20.2）：一件事 = 一个 mission。
- **片是计划里的步，不是任务**（A20）：一件事的片 = 绑在这个 mission 上的计划步骤，按 5.1.2 唯一的计数规则算（`dropped` 不进分母、`stopped` 不算做完、靠人工原子做完的单列）。任务是片里的尝试：一轮实现、一次验收、一次评审都是步里的动作，不另算片。
- **「需要你」只放他能动手的**（A15 ②、A7）：每一条都有一个真实的入口（他能回答的决策卡、能批的审批单）；没有入口的等待不进这一栏，放在那件事的状态里，写明在等什么、谁能解开。运行时这一份只是**候选**：卡此刻开没开着归问题库说了算，这条读路径不碰问题库（不联网、不写决定），所以不声称「现在能办」；Console 合成时按问题库的事实留下仍开着的（§5）。运行时的 `needs_you.count` 只是这一份候选的小计。

## 2. 形状

```json
{
  "generated_at": "2026-10-14T19:40:00Z",
  "as_of_event_id": 1234,
  "needs_you": { "count": 1, "items": [ … ], "truncated": false },
  "work":      { "missions": [ … ], "truncated": false },
  "owner_next": { "state": "estimated", … },
  "live":      [ … ],
  "plan":      [ … ],
  "hosts":     [ … ],
  "controls":  [ … ],
  "recent":    { "tasks": [ … ], "failed_attempts": [ … ] }
}
```

### 2.1 `needs_you.items[]`

只收有入口的条目。第 2 轮的入口只有一种：运行时发给他的决策卡（计划变更授权外、以后的 mission 授权等），他在 Console 的问题页回答。收的是**挂着卡、还没有记下决定**（`plan_change_decided`）的提议，最近 8 天（卡最多活 7 天，加一遍决定），按提议时间、事件号排，最多 50 条，多了 `truncated: true`。

| 字段 | 内容 |
|---|---|
| `id` | 去重用的统一编号：`question:<问题号>`。一张卡一条：两个提议挂同一张卡时只出一条，后来的提议事件号放进 `also_refs`（正常不会发生：卡按提议的幂等键建，一个提议一张卡）。同一张卡在问题列表里也会出现，Console 以它去重 |
| `kind` | `plan_change` |
| `ref` / `also_refs` | 提议事件号；挂同一张卡的其他提议事件号（通常为空） |
| `title` | 一句话 |
| `since` / `waiting_min` | 从几点起等他、已等多少分钟（提议事件的时间） |
| `action` | `{"where": "console", "question_id": "q_…", "options": ["Apply the change", "Do not apply it"]}` |
| `can_act_now` | `null`，附 `can_act_now_reason`：卡此刻是否还开着归问题库（已回答、撤回、过期但控制器还没来得及记下决定的，这里看不出来）。Console 按问题库的事实定：开着就能办，否则这条不显示 |
| `deadline` | 卡的到期时间未接入运行时时为 `null`，Console 从问题本身读（B2） |
| `blocks` | 有证据的影响，按下面「影响集合」算；判断不了写 `{"unknown": "…原因"}`，不写空数组 |
| `after` | 办完之后发生什么：「Apply → 控制器在下一遍（约 15 秒内）落地变更；Do not apply → 计划不变」 |

**影响集合**（`blocks` 只从这一个集合算，mission 和任务数同源）：
- 动到的步骤：每个变更的节点（`add_node` 是父节点，`retitle`、`set_done_rule`、`rebind_step` 是节点本身，`move_task` 是目标节点）；节点是步就是它自己，是项就是它下面所有的步。
- 动到的任务：`move_task` 搬的任务。
- `missions` = 这些步所属的 mission ∪ 被搬任务原来的 mission ∪ 变更要绑上的 mission（`rebind_step`、`add_node` 的 `mission_id`）。步上的任务与步同属一个 mission（数据库约束），不另算。
- `unfinished_tasks` = 这些步上未结束的任务 + 被搬的未结束任务。
- 集合里一个 mission 都没有（例如给轮加一项）：`{"unknown": "the change touches no step a mission's work sits on"}`。

`count` = `items` 的条数。

### 2.2 `work.missions[]`（每件事）

mission 的 `mission_id`、`title`、`goal`、`state`、`deadline_at`、`work_id`，以及：

| 字段 | 内容 |
|---|---|
| `slices` | 按计数规则：`{done, total, manual, stopped, state}`，只数 `plan_node.mission_id` 是这件事的步骤 |
| `status` / `reason` / `since` | 这件事的状态（§3.2）、一句原因、从几点起（§3.4） |
| `waiting_on` | 在等谁：`owner`（`reason` 写在等什么、谁能解开）、`coordinator`、`role`（等哪个岗位，见 `waiting_roles`）、`none`。`external`（等外部系统或外部责任方）留着这个值，第 2 轮没有任何运行时事实记录外部等待，所以不出现（§4） |
| `waiting_roles` | `waiting_on: role` 时等的岗位（取自状态被选中的那个任务的 `waiting_roles`），否则空数组 |
| `tasks` | 没结束的任务：`task_id`、`title`、`role`、`plan_node_id`、`off_plan`、`off_plan_reason`、`round_no`、`max_rounds`、`state`、`status`、`reason`、`since`（§3.4）、`depends_on`（未接受的依赖任务号）、`waiting_roles`（`waiting_role` 时：`rework` 是它自己的岗位，`submitted` / `verifying` 是它未结束的验收、评审任务的岗位；还一个都没提出时为空，`reason` 写「none is proposed yet」）、`attempt`、`usual_s`（算不出不给）、`computed_not_persisted`（最近一次尝试算完了但结果还没落到平台）| 另有 `lost_attempt`：最近一次丢掉、之后没有被别的尝试的持久化结果取代的尝试，字段同 live（§2.3），外加 `ended_at`，没有 `status`；任务没有在跑的尝试、而这次尝试没持久化时，任务的 `reason` 也加上「result not persisted」那一句（TD-352）。
| `next_steps` | 这件事里还没开始的下一两步（步骤号、标题、`owner_step`），从计划的顺序取 |
| `eta` | 第一版固定 `{"state": "unknown", "reason": "no history of slice times yet; the runtime gives times once Gate A has run"}`（v4 §20.3 第 7 条：估不准就说估不准，不给数字） |

只列 `state ∈ {proposed, awaiting_owner, active, paused}` 的 mission；最多 100 件，多了 `truncated: true`。

### 2.3 `live[]`

所有活着的尝试（`leased` / `running` / `stale`），按开始时间（时间值，不按字符串）排：`attempt_id`、`attempt_no`、`task_id`、`mission_id`、`host_id`、`executor`、`model`、`state`、`started_at`、`elapsed_s`、`heartbeat_age_s`、`status`；另有 `persisted`（`persisted_at` 有值）、`last_checkpoint_seq` 和 `last_checkpoint_at`（这次尝试最后一条 `attempt_checkpointed`，走任务索引读）、`unpersisted_for_s`（结果没持久化时，从最后检查点、没有就从开始，到现在的秒数）。尝试 stale、主机失联（3.5 起：沉默超过 30 秒，口径见下文 `hosts`）或从没轮询过、且结果没持久化时，`reason` 后面加「; result not persisted (last checkpoint N at …, nothing persisted for M min)」（TD-352，platform `w31/td-352-t36`）。动作流水等 2.3 交互总线（不在这里扫事件表）。

### 2.4 `plan[]`

每个根一项：`plan_node_id`、`kind`（`round` / `arch_root`）、`title`。

- 轮：`count`（计数规则）和它的项：每项 `plan_node_id`、`label`、`title`、`count`、`active_steps`。
- 架构根：它的行：每行 `plan_node_id`、`title`、`tick`。`tick` 是这一行完成规则按**当前部署**的求值：`true` / `false` / `unknown`，附 `reason`。第一版没有接部署读数，一律 `{"tick": "unknown", "reason": "not evaluated against the current deployment yet"}`；不拿存储的状态充当当前结论。

### 2.5 `hosts[]`、`controls[]`

`hosts` 与 `GET /hosts` 是**同一段 SQL**（`store.HostsSQL`），只是时刻不同：本路由用快照的时刻，`GET /hosts` 用语句时刻。主机含 `poll_age_s`、`online`、`live_attempts`、`controls`；`online` = 主机沉默 **不超过** 30 秒（恰好 30 秒算在线，超过才算失联，与 §3.1 的 `host_lost` 同一口径；3.5 起，原为 3 分钟）。沉默从这几个时刻里最晚的那个算起：主机最后一次联系（agentd 主循环的领活或删分支调用，或它在跑的尝试的心跳）、读取方的恢复点（API 自己：agentrt 路由就绪的时刻；控制器：自己启动、平台重新接调用、探测看到的停服结束）。删分支轮次开着时，最多 165 秒内也算在线。另有 `claiming`（主循环 30 秒内调用过或删分支轮次开着；启动宽限内为 null）：执行者只在 `claiming` 的主机上算可用。切法与落地见 `CUT-online-status-2026-10-23.md`。
`controls` 是所有未解除的控制，字段与 `GET /controls` 相同（不分页：未解除的控制只有几条，见 §4）。

### 2.6 `recent`

- `tasks`：最近结束的 20 个任务（`accepted` / `rejected` / `cancelled`），`ended_at` 取进入终态的事件时间（计划迁移不改它），`ended_event_id` 是那个事件的号，带最后一次尝试的结论和报告产物号。
- `failed_attempts`：最近 20 次结论为 `failed` 的尝试（不论任务后来成没成），`attempt_id`、`task_id`、`mission_id`、`ended_at`、`ended_event_id`、`report_artifact_id`。T06：失败的实验看得到、不被后来的成功盖掉。
- 两张表的「最近」都按（事件时间，事件号）从新到旧，选候选、取前 20、输出顺序都用这同一个键：同一时刻结束的多于 20 个时，结果仍是确定的那 20 个。

### 2.7 `owner_next`：下一次需要 Owner（第 4 版）

回答 v4 §20.2 最上面那一行「下一次需要你：哪件事、预计几点」。**不含眼下正等他的**（那是 Console 合成的「需要你」：审批、问题、卡，§5）。

```json
"owner_next": {
  "state": "estimated",            // estimated | unknown | none
  "reason": "M-1's next step is yours once its unfinished work is done; work not proposed yet is not counted",
  "mission_id": "M-1",             // 以下五项只在 estimated 时有：最先轮到他的那件
  "step": { "plan_node_id": "R2:2.1-1", "title": "…" },
  "earliest": "2026-10-21T18:34:03Z", "latest": "2026-10-21T18:35:43Z",   // RFC3339，UTC
  "after": [], "ready": false,
  "candidates": [                  // 每件下一步是他的事，能估的按 earliest、latest 在前，估不出的在后
    { "mission_id": "M-1", "step": { … }, "state": "estimated", "earliest": "…", "latest": "…", "reason": "…", "after": [], "ready": false },
    { "mission_id": "M-2", "step": { … }, "state": "estimated", "earliest": "…", "latest": "…", "reason": "…, after M-1", "after": ["M-1"], "ready": false }
  ]
}
```

- **候选**：未结的事里，`next_steps[0]`（还没开始的第一步，计划顺序）是 Owner 步（`owner_step`）的。第二步才是他的不算：之前那一步的时间算不出。
- **到期**：这件事的 `eta`（§2.2，往常用时累加）；`active` 且没有未完成的任务时是「现在」，并标 `ready: true`——按计划轮到他了，有没有单或卡让他动手，看「需要你」。`eta` 只计现在已提出的工作，后来才提的验收、评审不算，`reason` 写明这是下限。
- **跨事依赖**（v4 §20.5 场景 8：「取两者里晚的那个」）：这件事的任务依赖别的事的任务时，到期取自己和那些事的 `earliest`、`latest` 各自的较晚值，沿依赖一路追下去；`after` 列出这些事。依赖的任务不在列出的事里，或那件事估不出，这件事就估不出，原因写明。
- **估不准就说估不准**（v4 §20.3 第 7 条）：任一候选估不出（`reason` 取第一件的），或未结的事超过 100 件没读全，`state` 就是 `unknown`，不报一个最早时间；候选仍全部列出。区间倒置、时间读不出都算估不出。
- **没有**：没有一件事的下一步是他的，`state: none`。
- 实现 `store/progressnext.go`；测试 `TestOwnerNext`（纯逻辑，每个分支）、`TestProgressSaysWhenTheOwnerIsNextNeeded`（真库，两件事一件等另一件），Console 夹具 `agentrt-progress-owner-next.testdb.json`。Console 在 For you 的 Yours 卡里显示一行「Next time you are needed」。

## 3. 状态判定

### 3.1 一个任务的 `status`（每条带 `reason` 和 `since`）

| 状态 | 条件（按顺序，第一个成立的） |
|---|---|
| `unknown` | 有活着的尝试，但它记的主机运行时不认识：主机在干什么无从判断，所以排在所有条件之前（包括尝试是 `stale` 时） |
| `host_lost` | 有活着的尝试，它的主机从没轮询过，或沉默超过 30 秒（3.5 起；与 `GET /hosts` 同一段 SQL、同一比较口径，T24） |
| `maybe_stuck` | 有活着的尝试，尝试是 `stale` |
| `waiting_owner` | 任务 `awaiting_owner`，或它的 mission 是 `proposed` / `awaiting_owner`（任务本身是 `blocked` 也是这个） |
| `blocked` | 任务 `blocked` 或 `paused`（`reason` 写原因事件里的说明） |
| `slow` | 有活着的尝试，用时**超过**往常的 1.5 倍（恰好 1.5 倍不算；有往常用时时） |
| `working` | 有活着的尝试（mission 暂停时已在跑的尝试照样是 `working`） |
| `blocked` | mission 是 `paused`（`reason`：「the mission is paused: 暂停事件里的原因」） |
| `waiting_role` | `submitted` / `verifying`（等验收或评审）、`rework`（等下一轮实现） |
| `queued` | `ready`；`proposed` 时 `reason` 写在等依赖还是等派发 |
| `unknown` | 以上都判断不了（任务状态没有对应的状态） |

### 3.2 一件事的 `status`

有未结束任务时取最该看的那个（顺序：`host_lost` > `maybe_stuck` > `unknown` > `waiting_owner` > `blocked` > `slow` > `working` > `waiting_role` > `queued`；这是**展示的轻重**，与 §3.1 判定一个任务时条件的先后是两回事），`reason`、`since`、`waiting_roles` 取自这个状态的第一个任务。`waiting_on`：`waiting_owner` → `owner`；`waiting_role` → `role`（还没有验收、评审任务可等时 → `coordinator`）；`host_lost`、`maybe_stuck`、`unknown`、`blocked`、`queued` → `coordinator`（第 2 轮任务被挡住只有一个来源：最后一轮验收或评审失败，由控制器挡住，接下来改计划或取消由统筹方定）；其余 `none`。没有未结束任务时：

- mission 是 `proposed` / `awaiting_owner`：`waiting_owner`，`waiting_on: owner`，`reason` 写在等什么（第 2 轮：常备授权规则还没签，没有他能点的入口）；
- mission 是 `paused`：`blocked`，`waiting_on: coordinator`，`reason`：「the mission is paused by 谁: 原因」（取自暂停事件）；
- 计划里这件事还有没做完的步：`idle`，`reason: "no task proposed for the next step"`，`waiting_on: coordinator`；
- 步都做完：`done`。

### 3.4 `since`：从几点起

- 任务：进入当前状态的事件时间（`task_proposed` / `task_state_changed`，不是 `updated_at`）；但状态是 mission 定的（任务不是 `awaiting_owner` 却因 mission 等授权而 `waiting_owner`，任务不是 `blocked` / `paused` 却因 mission 暂停而 `blocked`），就取 mission 进入当前状态的事件时间（`mission_proposed` / `mission_state_changed`）。
- 一件事：有未结束任务时取被选中那个任务的 `since`；没有时，`waiting_owner` 和 `blocked`（暂停）取 mission 进入当前状态的事件时间，`idle` 和 `done` 取这件事最后一个事件的时间（从那以后没有动静）。

### 3.3 往常用时

同一 `role` 和 `task_class` 的任务，最近 30 天里**被采纳的那次尝试**（`verification.accepts_attempt`）从开始到提交（`attempt_submitted` 事件）的用时中位数；少于 3 个样本不给。

## 4. 不在这一版的（写明归属）

「负责」写的是谁去补：**统筹方** = W-31 的统筹线程（Claude，写核心代码；Codex 复核）；Owner 只在要他定目标时出现。

| 项 | 为什么不在 | 什么时候 | 负责 |
|---|---|---|---|
| 预计时间（A4、v4 §20.3 第 6、7 条） | 片的历史用时要到 Gate A 之后才有样本 | 2.5 前；现在给 `eta.state = unknown` 和原因 | 统筹方 |
| ~~下一次需要 Owner 的时间（v4 §20.3）~~ | 第 4 版已做：§2.7 `owner_next`（2.5 缺口 1，2026-10-21） | — | — |
| 计划里等 Owner 签收（`owner_signoff`）的步骤进「需要你」 | 2026-10-21 起签收有了入口（计划页的 Sign off，`POST /plan/{id}/signoff`，设计 v5 §5.5），但本路由的 `needs_you` 仍只收决策卡，`owner_next` 也只看 `owner_step` 标记、不看规则里有没有签收；要不要把「规则等签收、还没签」的步骤列进来（A1：有入口才进），没定 | 2.5 之后，统筹方定 | 统筹方 |
| 等待累计（一件事前后一共等了多久，A5） | 要按事件回放每段等待再相加；现在每条只给当前这段从几点起（§3.4） | 2.5 前，Gate A 的事件够了再定口径 | 统筹方 |
| 外部责任方（`waiting_on: external`） | 第 2 轮没有任何运行时事实记录「在等外部」：外部类任务第 2 轮不派发，任务被挡住只有验收失败一个来源 | 2.3（交互总线带上外部等待的事件）之后 | 统筹方 |
| 动作流水、最近检查点（A10、A13） | 等交互总线 | 2.3 | 统筹方 |
| 架构行按当前部署求值 | 读路径要接部署读数，且不能调会写状态的求值函数 | 2.5 前；现在 `tick: unknown` | 统筹方 |
| 「这条不该找我」（A14、A15 ①）、误报率 | 要一个反馈写入口 | 2.5，复用 W-65 的反馈入口 | 统筹方 |
| 主机负载、孤儿巡检（A16、A19） | agentd 还没上报 | 2.3 / 2.4 | 统筹方 |
| 业务成果阶梯（A12） | 他还没定五项成果 | 他定了之后 | Owner 定成果，统筹方接 |
| 读的成本：分页、索引、实测计划 | 现在只有 `needs_you`（50）、`work`（100 件）、`recent`（20 + 20）有条数上限；`live`、`plan`、`hosts`、`controls`、每件事的步和任务、30 天往常用时、mission 的状态事件没有上限。往常用时按采纳时间筛，没有 `verification(created_at)` 索引；决定事件按提议反查没有 `proposal_event_id` 的表达式索引；`recent` 稀疏命中时会多扫事件。这一版适用的规模：进行中的事 ≤ 100 件、每件事任务 ≤ 数百、活着的尝试和主机各 ≤ 数十、事件 ≤ 10⁵ 量级（Gate A 在 STG 上远低于此）。 | Gate A 跑完、2.5 动工前：在 STG 上用 Gate A 的真实数据跑 `EXPLAIN (ANALYZE, BUFFERS)`，超出上述规模或计划不对再加分页、摘要和完整性标记、两个索引（新索引走迁移，按库表变更流程） | 统筹方 |

## 5. 2.5 要接的

Console 的「需要你」是唯一的那个数：本路由的 `needs_you.items` + 审批的待批单 + 问题的未答问题，按 `id`（`question:<号>`、`approval:<号>`）去重；任一来源读失败，总数显示「未知」并写哪一来源。

运行时的条目是候选，**问题库说了算**：一条 `question:<号>` 只有在问题库里这个问题还开着时才显示（这时 `can_act_now` 当作 `true`）；问题库里它已回答、撤回或过期，这条就不显示（控制器下一遍会记下决定，之后它也不再出现在本路由）；问题库里找不到它，这条显示为「状态未知」并写原因，不算进能办的数。不能只按编号去重就把运行时的条目留下。运行时的 `count` 只是它这一份候选的小计，页面不单独显示它。

## 改了什么（第 1 → 第 2 版，复核 181）

- A1：「需要你」不再列没有入口的条目（第 1 版照列不计数，违背 A15 ②）；mission 等授权、任务挡住改为「每件事」里的状态和原因；计划里的 Owner 步骤没有可回答的绑定时不进这一栏。
- A2：最近结束加按尝试列的失败实验，不再只取最后一次尝试。
- A3：片改为计划步骤，不再拿任务数代替。
- A4：加 `unknown` 和每条状态的 `reason` / `since` / `waiting_on`；没活的事写清原因；架构行不再拿存储状态充当当前结论。
- A5：加 `as_of_event_id`、依赖、计划外标记、未持久化标记、下一两步、`eta` 的明确「估不准」；「需要你」的去重编号和合成口径。

## 改了什么（第 2 → 第 3 版，复核 184）

- 状态顺序只有一套（184 A4-1）：主机认不出的 `unknown` 写在 §3.1 第一行（代码一直如此），与 §3.2 展示的轻重分开说；补 mission 暂停这一条。
- `since` 有了完整的规则（§3.4，184 A4-2）：状态是 mission 定的就取 mission 的状态事件时间；没有任务的事也有起点；暂停写明谁、为什么。
- 等谁（184 A4-3）：加 `waiting_roles`，写清 `waiting_on` 每个值从哪来；`external` 第 2 轮不出现，原因与负责写进 §4。
- §4 每一项写了负责的人（184 A5）；补「等待累计」「下一次需要 Owner 的时间」「外部责任方」「读的成本」四项，读的成本写了适用规模、什么时候实测、谁做（184 B7）。代码里「每个查询都有上限、走索引」那句不成立，已改成指向 §4。
- `needs_you`（184 B4）：`can_act_now` 改为 `null` 加原因，Console 以问题库为准（§5）；一张卡一条（`also_refs`）；最多 50 条加 `truncated`；`blocks` 按影响集合算，mission 和任务数同源。
- `recent`（184 B3）：选候选、取前 20、输出用同一个键（时间，事件号），加 `ended_event_id`。
- `hosts`（184 B5）：与 `GET /hosts` 用同一段 SQL，恰好 30 秒两边都算在线（3.5 起）。

## 改了什么（第 3 → 第 4 版，2026-10-21）

- 加 `owner_next`（§2.7）：Owner 10-21「缺口 1、2 照推荐加：/progress 加 owner_next」。只加字段，其余不变（`missionDoc` 改成用同一次算出的 `eta`）。
- 复核 477 B1：过了预计时间不等于轮到他，也不等于有单可批；加 `ready`，`reason` 写明时间是下限。C1：区间倒置算估不出。
