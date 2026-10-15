# `GET /api/v1/agentrt/progress`：进展投影的接口（2.2 定，2.5 照它做界面）

**为什么现在写**：设计 v5 §5.2 把 `GET /progress` 列在 2.2 的路由里（viewer 读；「计划、架构对照、现场、需要你」），2.5 的 Console 照「已定接口」写（§5.5）。字段和状态判定设计没写全，统筹方先定在这里；要求出处是 v4 §20.2–20.3 和 `OWNER-SURFACE-2026-10-11.md`（下称 A1…D3）。你要改就说。

## 1. 原则

- **读时现算，不存**（v4 §20.1）：每次请求从运行时的表和事件算一份，带 `generated_at`（数据库时钟）。没有第二份手写的状态。
- **读不到就是未知**（A5）：数据库读失败整条路由回 503，不回一份旧的；某一项算不出（例如没有往常用时）就不给那个字段，不填一个看起来正常的数。
- **按「事」组织**（v4 §20.2）：一件事 = 一个 mission。任务挂在它的事下面，一个动作只记在它所属的那件事下（A20 ③）。
- **「需要你」只有一处、一个数**（A7）：`needs_you.count`；页面别处不再出现可以读成「要你办」的数。只放有他能做的动作的条目（A15）；当前没有动作入口的，写明在等什么、谁能解开。
- 第一版只用运行时自己的数据（PG）；审批和问题的总表照旧在它们自己的路由，运行时只列和它有关的那几张（它发的决策卡、计划里绑的审批与提问）。合成一个总数是 2.5 的事（见 §5）。

## 2. 形状

```json
{
  "generated_at": "2026-10-14T19:40:00Z",
  "needs_you": { "count": 2, "items": [ … ] },
  "work":      [ … ],
  "live":      [ … ],
  "plan":      [ … ],
  "hosts":     [ … ],
  "controls":  [ … ],
  "recent":    [ … ]
}
```

### 2.1 `needs_you.items[]`

| 字段 | 内容 |
|---|---|
| `kind` | `plan_change`（授权外的计划变更，等他回答决策卡）、`mission`（提议的 mission 等授权）、`task_blocked`（任务挡住，例如 external 类接管后）、`owner_step`（计划里轮到他的一步） |
| `ref` | 对象编号：提议事件号、`M-n`、`t_…`、步骤号 |
| `title` | 一句话，取自对象 |
| `since` | 从几点起等他（对象进入这个状态的事件时间） |
| `waiting_min` | 已等多少分钟（A17 ②、A18） |
| `action` | 他能做的动作和地方：`{"where": "console", "question_id": "q_…"}`（回答决策卡）；没有动作入口的写 `{"where": "none", "why": "…"}`，例如 mission 在等常备授权规则签名 |
| `blocks` | 不办会卡住什么：这件事的 mission 编号和挡住的任务数；不挡别的写空数组 |

`count` = `items` 里 `action.where ≠ "none"` 的条数；没有动作入口的照列，但不计数（A15 ②：它们不是「要他办」，是「在等什么」）。

### 2.2 `work[]`（每件事）

mission 的 `mission_id`、`title`、`goal`、`state`、`deadline_at`、`work_id`，以及：

| 字段 | 内容 |
|---|---|
| `slices` | `{done, total}`：做完的片 / 共几片。片 = 这件事里 `role ∈ {implement, plan, brief, other}` 的任务（验收和评审是片里的步，不另算片，A20）；做完 = `accepted` |
| `tasks` | 没结束的任务（不是 `accepted` / `rejected` / `cancelled`）：`task_id`、`title`、`role`、`plan_node_id`、`round_no`、`state`、`status`（§3）、`attempt`（在跑的那次尝试：`attempt_id`、`attempt_no`、`host_id`、`executor`、`model`、`started_at`、`elapsed_s`、`heartbeat_age_s`、`checkpoint_seq`）、`usual_s`（同类往常用时，§3.2；算不出不给）|
| `status` | 这件事的状态：任务里最该看的那个（顺序：`host_lost` > `maybe_stuck` > `waiting_owner` > `blocked` > `slow` > `working` > `waiting_role` > `queued`；没有未结束的任务时，mission 是 `done` 就是 `done`，否则 `idle`） |

只列 `state ∈ {proposed, awaiting_owner, active, paused}` 的 mission。

### 2.3 `live[]`

所有活着的尝试（`leased` / `running` / `stale`），按开始时间排：尝试的字段同上，加 `task_id`、`mission_id`、`status`。这是「现在在跑什么」（A10 的数据底座；动作流水在 2.3 交互总线之后才有，这里不给）。

### 2.4 `plan[]`

每个根（轮、架构根）一项：`plan_node_id`、`title`、`count`（按 5.1.2 计数规则：`{done, total, manual, stopped, state}`），以及它的项：每项 `plan_node_id`、`label`、`title`、`count`、`active_steps`（在做的步骤编号）。步骤明细照旧读 `GET /plan?root=`。

### 2.5 `hosts[]`、`controls[]`

同 `GET /hosts`、`GET /controls`（生效中的）。

### 2.6 `recent[]`

最近结束的 20 个任务（`accepted` / `rejected` / `cancelled`，按结束时间倒序）：`task_id`、`mission_id`、`title`、`role`、`state`、`ended_at`、`conclusion`（最后一次尝试的结论，含 `failed`，T06：失败的实验看得到、不被后来的成功覆盖），`report_artifact_id`（证据在哪）。

## 3. 状态判定

### 3.1 一个任务的 `status`

| 状态 | 条件（按顺序，第一个成立的） |
|---|---|
| `host_lost` | 有活着的尝试，它的主机 3 分钟没有轮询（同 `GET /hosts` 的在线口径，T24） |
| `maybe_stuck` | 有活着的尝试，尝试是 `stale`（租约过期还没续上；由租约循环判，120 秒） |
| `waiting_owner` | 任务 `awaiting_owner`，或它的 mission 是 `proposed` / `awaiting_owner` |
| `blocked` | 任务 `blocked`（例如 external 类接管后），或 `paused` |
| `slow` | 有活着的尝试，`elapsed_s` > 1.5 × `usual_s`（有往常用时时） |
| `working` | 有活着的尝试 |
| `waiting_role` | `submitted` / `verifying`（等验收或评审）、`rework`（等下一轮实现） |
| `queued` | `ready`，或 `proposed`（等依赖或派发） |

「慢」和「卡」由运行时判，不由人猜（v4 §20.3 第 2 条）；「有上报但超时」是慢，「租约断了」是可能卡住，「主机不轮询」是宿主失联。

### 3.2 往常用时

同一 `role` 和 `task_class` 的任务，最近 30 天里被 `accepted` 的那次尝试从开始到提交的用时中位数；少于 3 个样本不给（宁可不知道）。

## 4. 不做的（第一版）

- **预计时间**（A4 的「还要多久」、v4 §20.3 第 6、7 条）：要按片的历史速率和等他的时间算，样本到 Gate A 之后才有；第一版不给数字，不给比给一个错的好。
- **动作流水**（A10、A13）：等 2.3 交互总线。
- **架构对照的勾**按当前部署现算（§5.1.2）：读路径要接部署读数，第一版给存储的状态，并在 2.5 前补。
- 审批、问题的总表合成一个数：见下。

## 5. 2.5 要接的

Console 的「需要你」= 本路由的 `needs_you` + 审批的待批单 + 问题的未答问题，去重（运行时发的决策卡在两边都出现，以问题号去重）。合成在 Console 的读取层做，不在运行时里复制审批和问题的状态。
