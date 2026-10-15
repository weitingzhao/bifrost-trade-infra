# `GET /api/v1/agentrt/progress`：进展投影的接口（2.2 定，2.5 照它做界面）

**版本**：第 2 版（2026-10-14 晚，按复核 181 改）。第 1 版的五处与来源冲突或缺失，见文末「改了什么」。

**为什么现在写**：设计 v5 §5.2 把 `GET /progress` 列在 2.2 的路由里（viewer 读；「计划、架构对照、现场、需要你」），2.5 的 Console 照「已定接口」写（§5.5）。字段和状态判定设计没写全，统筹方先定在这里；要求出处是 v4 §20.2–20.3 和 `OWNER-SURFACE-2026-10-11.md`（下称 A1…D3）。你要改就说。

## 1. 原则

- **读时现算，不存**（v4 §20.1）：每次请求在一个只读、可重复读的快照里从运行时的表和事件算一份，带 `generated_at`（数据库时钟，整份用同一个时刻判时间）和 `as_of_event_id`（快照里最大的事件号，客户端拿它做「自上次以来」的基线，A17）。
- **读不到就是未知**（A5）：数据库读失败整条路由回 **503** `unavailable`，不回旧的、不回半份。某一项算不出，就给 `unknown` 和原因，不填一个看起来正常的值。
- **按「事」组织**（v4 §20.2）：一件事 = 一个 mission。
- **片是计划里的步，不是任务**（A20）：一件事的片 = 绑在这个 mission 上的计划步骤，按 5.1.2 唯一的计数规则算（`dropped` 不进分母、`stopped` 不算做完、靠人工原子做完的单列）。任务是片里的尝试：一轮实现、一次验收、一次评审都是步里的动作，不另算片。
- **「需要你」只放他能动手的**（A15 ②、A7）：每一条都有一个真实的入口（他能回答的决策卡、能批的审批单）；没有入口的等待不进这一栏，放在那件事的状态里，写明在等什么、谁能解开。运行时的 `needs_you.count` 只是运行时这一份的小计（见 §5）。

## 2. 形状

```json
{
  "generated_at": "2026-10-14T19:40:00Z",
  "as_of_event_id": 1234,
  "needs_you": { "count": 1, "items": [ … ] },
  "work":      { "missions": [ … ], "truncated": false },
  "live":      [ … ],
  "plan":      [ … ],
  "hosts":     [ … ],
  "controls":  [ … ],
  "recent":    { "tasks": [ … ], "failed_attempts": [ … ] }
}
```

### 2.1 `needs_you.items[]`

只收有入口的条目。第 2 轮的入口只有一种：运行时发给他的决策卡（计划变更授权外、以后的 mission 授权等），他在 Console 的问题页回答。

| 字段 | 内容 |
|---|---|
| `id` | 去重用的统一编号：`question:<问题号>`（同一张卡在问题列表里也会出现，Console 以它去重） |
| `kind` | `plan_change` |
| `ref` | 提议事件号 |
| `title` | 一句话 |
| `since` / `waiting_min` | 从几点起等他、已等多少分钟（提议事件的时间） |
| `action` | `{"where": "console", "question_id": "q_…", "options": ["Apply the change", "Do not apply it"]}` |
| `can_act_now` | `true`（卡已在他面前）|
| `deadline` | 卡的到期时间未接入运行时时为 `null`，Console 从问题本身读（B2） |
| `blocks` | 有证据的影响：变更动到的步骤所属的 mission 和那些步骤上未结束的任务数；判断不了写 `{"unknown": "…原因"}`，不写空数组 |
| `after` | 办完之后发生什么：「Apply → 控制器在下一遍（约 15 秒内）落地变更；Do not apply → 计划不变」 |

`count` = `items` 的条数。

### 2.2 `work.missions[]`（每件事）

mission 的 `mission_id`、`title`、`goal`、`state`、`deadline_at`、`work_id`，以及：

| 字段 | 内容 |
|---|---|
| `slices` | 按计数规则：`{done, total, manual, stopped, state}`，只数 `plan_node.mission_id` 是这件事的步骤 |
| `status` / `reason` / `since` | 这件事的状态（§3.2）、一句原因、从几点起 |
| `waiting_on` | 在等谁：`owner`（附「在等什么、谁能解开」）、`coordinator`、`role`（等哪个岗位）、`external`、`none` |
| `tasks` | 没结束的任务：`task_id`、`title`、`role`、`plan_node_id`、`off_plan`、`off_plan_reason`、`round_no`、`max_rounds`、`state`、`status`、`reason`、`since`（进入当前状态的事件时间）、`depends_on`（未接受的依赖任务号）、`attempt`、`usual_s`（算不出不给）、`computed_not_persisted`（最近一次尝试算完了但结果还没落到平台）|
| `next_steps` | 这件事里还没开始的下一两步（步骤号、标题、`owner_step`），从计划的顺序取 |
| `eta` | 第一版固定 `{"state": "unknown", "reason": "no history of slice times yet; the runtime gives times once Gate A has run"}`（v4 §20.3 第 7 条：估不准就说估不准，不给数字） |

只列 `state ∈ {proposed, awaiting_owner, active, paused}` 的 mission；最多 100 件，多了 `truncated: true`。

### 2.3 `live[]`

所有活着的尝试（`leased` / `running` / `stale`），按开始时间（时间值，不按字符串）排：`attempt_id`、`attempt_no`、`task_id`、`mission_id`、`host_id`、`executor`、`model`、`state`、`started_at`、`elapsed_s`、`heartbeat_age_s`、`status`。最近一次检查点、动作流水等 2.3 交互总线（不在这里扫事件表）。

### 2.4 `plan[]`

每个根一项：`plan_node_id`、`kind`（`round` / `arch_root`）、`title`。

- 轮：`count`（计数规则）和它的项：每项 `plan_node_id`、`label`、`title`、`count`、`active_steps`。
- 架构根：它的行：每行 `plan_node_id`、`title`、`tick`。`tick` 是这一行完成规则按**当前部署**的求值：`true` / `false` / `unknown`，附 `reason`。第一版没有接部署读数，一律 `{"tick": "unknown", "reason": "not evaluated against the current deployment yet"}`；不拿存储的状态充当当前结论。

### 2.5 `hosts[]`、`controls[]`

与 `GET /hosts`、`GET /controls` 同字段（主机含 `poll_age_s`、`online`、`live_attempts`、`controls`）。

### 2.6 `recent`

- `tasks`：最近结束的 20 个任务（`accepted` / `rejected` / `cancelled`），`ended_at` 取进入终态的事件时间（计划迁移不改它），带最后一次尝试的结论和报告产物号。
- `failed_attempts`：最近 20 次结论为 `failed` 的尝试（不论任务后来成没成），`attempt_id`、`task_id`、`mission_id`、`ended_at`、`report_artifact_id`。T06：失败的实验看得到、不被后来的成功盖掉。

## 3. 状态判定

### 3.1 一个任务的 `status`（每条带 `reason` 和 `since`）

| 状态 | 条件（按顺序，第一个成立的） |
|---|---|
| `host_lost` | 有活着的尝试，它的主机超过 3 分钟没有轮询（与 `GET /hosts` 用同一个时刻、同一比较口径，T24） |
| `maybe_stuck` | 有活着的尝试，尝试是 `stale` |
| `waiting_owner` | 任务 `awaiting_owner`，或它的 mission 是 `proposed` / `awaiting_owner` |
| `blocked` | 任务 `blocked` 或 `paused`（`reason` 写原因事件里的说明） |
| `slow` | 有活着的尝试，用时超过往常的 1.5 倍（有往常用时时） |
| `working` | 有活着的尝试 |
| `waiting_role` | `submitted` / `verifying`（等验收或评审）、`rework`（等下一轮实现） |
| `queued` | `ready`；`proposed` 时 `reason` 写在等依赖还是等派发 |
| `unknown` | 以上都判断不了（例如尝试的主机记录读不到） |

### 3.2 一件事的 `status`

有未结束任务时取最该看的那个（顺序：`host_lost` > `maybe_stuck` > `unknown` > `waiting_owner` > `blocked` > `slow` > `working` > `waiting_role` > `queued`）。没有未结束任务时：

- mission 是 `proposed` / `awaiting_owner`：`waiting_owner`，`waiting_on: owner`，`reason` 写在等什么（第 2 轮：常备授权规则还没签，没有他能点的入口）；
- 计划里这件事还有没做完的步：`idle`，`reason: "no task proposed for the next step"`，`waiting_on: coordinator`；
- 步都做完：`done`。

### 3.3 往常用时

同一 `role` 和 `task_class` 的任务，最近 30 天里**被采纳的那次尝试**（`verification.accepts_attempt`）从开始到提交（`attempt_submitted` 事件）的用时中位数；少于 3 个样本不给。

## 4. 不在这一版的（写明归属）

| 项 | 为什么不在 | 归属 |
|---|---|---|
| 预计时间（A4、v4 §20.3 第 6、7 条） | 片的历史用时要到 Gate A 之后才有样本 | 2.5 前补；现在给 `eta.state = unknown` 和原因 |
| 动作流水、最近检查点（A10、A13） | 等交互总线 | 2.3 |
| 架构行按当前部署求值 | 读路径要接部署读数，且不能调会写状态的求值函数 | 2.5 前补；现在 `tick: unknown` |
| 「这条不该找我」（A14、A15 ①）、误报率 | 要一个反馈写入口 | 2.5，复用 W-65 的反馈入口 |
| 主机负载、孤儿巡检（A16、A19） | agentd 还没上报 | 2.3 / 2.4 |
| 业务成果阶梯（A12） | 他还没定五项成果 | 他定了之后 |

## 5. 2.5 要接的

Console 的「需要你」是唯一的那个数：本路由的 `needs_you.items` + 审批的待批单 + 问题的未答问题，按 `id`（`question:<号>`、`approval:<号>`）去重；任一来源读失败，总数显示「未知」并写哪一来源。运行时的 `count` 只是它这一份的小计，页面不单独显示它。

## 改了什么（第 1 → 第 2 版，复核 181）

- A1：「需要你」不再列没有入口的条目（第 1 版照列不计数，违背 A15 ②）；mission 等授权、任务挡住改为「每件事」里的状态和原因；计划里的 Owner 步骤没有可回答的绑定时不进这一栏。
- A2：最近结束加按尝试列的失败实验，不再只取最后一次尝试。
- A3：片改为计划步骤，不再拿任务数代替。
- A4：加 `unknown` 和每条状态的 `reason` / `since` / `waiting_on`；没活的事写清原因；架构行不再拿存储状态充当当前结论。
- A5：加 `as_of_event_id`、依赖、计划外标记、未持久化标记、下一两步、`eta` 的明确「估不准」；「需要你」的去重编号和合成口径。
