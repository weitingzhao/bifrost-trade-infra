# 切法：第 2 轮计划进运行时（W-31，2026-10-19）

**一句话**：把 `WORK.md`「第 2 轮逐项」一次性导入成运行时的计划树 `R2`（10-19 01:20 时 7 项 74 步，02:4x 已是 75 步；以冻结那一刻为准，§5），编号照看板现在用的「项-行序」固定下来；做完的 53 步带着 `WORK.md` 原话和提交号作为证据进来；导入后运行时是这张表唯一的事实来源，`WORK.md` 只留指针。**首次导入要一个新入口**（现有的计划变更路由建不了根、发不出 `2.0` 和 `2.2b` 这样的号），按 CLAUDE.md §5 列在 §4 等定；入口以外的部分（生成导入请求的工具、存储层的导入函数、端到端测试）已在分支 `w31/plan-import` 实现，没有新路由、没改公开接口、没加表列。

**范围**：只有第 2 轮的轮、项、步。「架构对照」不在这一次（§8）。不往 STG、PROD 写任何东西。

## 1. 现状（10-19 实测与读代码）

| 事实 | 出处 |
|---|---|
| PROD、STG 的 `GET /api/v1/agentrt/plan` 都是 `{"roots": []}`：计划从没进过运行时 | 10-19 02:0x 经 MCP `get_plan` 两个环境各读一次 |
| 计划栏和「设计 → 现在」仍由本机 `~/agent-work/status/roadmap.py` 解析 `WORK.md` 生成，`board2.py` 每 15 秒推到 PROD；Console 的 `AgentsPlan`、`ProgressPlan` 读的是推上来的文档里的 `roadmap.round` / `roadmap.arch` | `roadmap.py:58-108`、`board2.py:376-388`；Console `src/api/agentProgressBoard.ts:138-151` |
| 写计划的唯一路由是 `POST /plan/proposals`：只能在**已有的根**下加项、加步、改标题、设完成规则、改绑、搬任务；一次最多 20 条；新节点的号由程序发（项 = 父标签 + `.` + 最大号加一，步 = 项标签 + `-` + 最大号加一）；常备授权只有「给在做的项加步」「改没开始的步的标题」，其余都要 Owner 的决策卡 | `store/planchange.go:36-56`、`:121-136`、`:303-351`、`:523-529` |
| 没有任何入口能建根节点；`CreatePlanNode` 只在测试里用 | `store/write.go:177`，调用方只有 `*_test.go` |
| 步骤的状态只能经 `plan_node_state_changed` 改（触发器），唯一的写入方是控制器对完成规则的求值（`EvaluateStep`）：规则成立 → `done`（只靠 `manual` 原子成立的，原因记 `done_rule_manual`，Progress 单列「人工」）；持续条件失效 → 回 `active` | `migrations/0002_guards.sql:276-283`；`store/facts.go:345-388`；`store/progress.go:434`、`:629` |
| `manual` 原子 = 「人工补记，要附证据产物」：步上一条 `note` 事件，带 `manual` 和 `evidence`（产物号）才算成立 | v5 §5.1.2；`store/facts.go:180-196`、`:307-310` |
| 数据库已为一次性导入留了 `legacy_imported`：这类事件可以写任何状态表 | `migrations/0002_guards.sql:134-153`、`:205`；v5 §5.3「一次性导入成 `plan_node`（`legacy_imported`）」 |
| 没有路由能记 `manual` 的证据、能记 Owner 签收（`main` 上 `RecordManual`、`SignOff` 只有测试调用；本分支的导入函数是 `RecordManual` 第一个非测试调用方，也不经路由）；也没有任何东西把步从 `planned` 改成 `active` | `grep` 调用方 |

所以只用现有接口导不进去：第一个项会被编成 `2.1` 而不是 `2.0`，`2.2b` 编不出来，74 步要拆成 4 张以上的 Owner 卡，做完的步也标不成做完。

## 2. 编号：照看板现在的号，导入后不再变

| 层 | `plan_node_id` | `label` | `ordinal` | 来源 |
|---|---|---|---|---|
| 轮 | `R2` | `2` | `2`（轮号；根的序号全局唯一） | 「第 2 轮逐项」这一行 |
| 项 | `R2:2.0` … `R2:2.5`，含 `R2:2.2b` | 行首的项号 | 0–6，按行序 | 缩进 6 格的 `- 2.x 名称（出处）` |
| 步 | `R2:2.1-3` 这样：`R2:<项号>-<n>` | `<项号>-<n>` | `n-1` | 项下第 n 行 `- [x] …`（n 从 1 起），和看板 `roadmap.finish` 的 `x["id"]` 完全相同 |

- **为什么是这套号**：Owner 和各线程两周来都按看板上的号说话（「2.1-10 在等你批」）；运行时的编号程序对之后新加的节点接着这套号发：给 `2.1` 加一步得到 `R2:2.1-12`，给轮加一项得到 `R2:2.6`（`2.2b` 不是纯数字，算最大号时跳过）。这一点在端到端测试里验（§9 `TestPlanImportNumberingContinues`）。
- **以后不变**：触发器挡改号、改父节点、改序号、删节点（`0002_guards.sql:269-274`）。`WORK.md` 现在允许「还没开始的步骤可以改写、后移」，导入后这条不再适用：没开始的步改标题走常备授权；**挪位置、去掉一步、改标记现在都没有操作**——计划变更只有加节点、改标题、设完成规则、改绑、搬任务五种（`store/planchange.go:36-51`、`:104-105`），没有「丢弃」（虽然 `SetStepState` 认 `dropped`，`store/write.go:199-204`，但没有任何经授权的路径调它），也改不了 `owner_step` / `effect_step`。所以导入之后结构上的错不能原地改（§5「导错了怎么办」、§10 第 6 条）。
- **标题**：步的标题 = 看板显示的那段（第一个「｜」之前，去掉开头的 ★），一字不改，所以计划栏和今天逐字相同。项的标题 = 名称，括号里的出处只进证据。
- **标记**：「（你）」→ `owner_step`；「★」→ `effect_step`。Owner 步完全照看板的规则（去掉开头的 ★ 后标题以「（你）」开头；「（补强）（你）…」不算，和看板一样）。★ 比看板认得多一种：看板只认标题以 ★ 开头，导入按标题开头那一串标记（★、「（你）」、「（补强…）」任意顺序）找 ★，所以 `（补强）★ …` 这样的步会标成 ★——10-19 02:4x 的 `WORK.md` 上是 7 步（2.1-11、2.2-31、2.3-6、2.3-7、2.4-4、2.4-5、2.5-4），看板认不出。这是唯一和看板不同的地方，测试里单独列出（复核 310 A2 后改）。
- **空白**：缩进、首尾空白都按 Python `str.isspace` 认（含不换行空格、全角空格），和看板的 `strip()`、`\s` 一样，所以用 Unicode 空白缩进的行不会被当成表的结尾（复核 310 A1）。比看板严的两处是拒收而不是读成别的：既不是项也不是步的行、标题为空或含控制字符的步。
- **`step_kind`**（现在只用于显示，没有逻辑读它）：「（你）」→ `owner`；标题里有「复核」→ `review`；其余 `agent`。
- **`work_id`**：每个节点都写 `W-31`。

## 3. 状态和证据：做完的步怎么带着证据进来

导入在**一个事务**里写完，要么全进、要么什么都没留下：

1. 存两类产物（`artifact_kind = 'other'`，`application/json`，按内容寻址）：整份导入请求（含每一步在 `WORK.md` 里的原行）；每个做完的步一份证据（原行、行号、请求的产物号、从原行里抽出的标记时间、提交号、审批单号、复核编号）。
2. 一条 `legacy_imported`（`source = "plan-import sha256:<请求的规范 JSON 摘要>"`、`count = 节点数`），作为这次导入的头。
3. 每个节点一条 `plan_node_created`（`cause_event_id` 指向上面那条），再插节点行。
4. `[x]` 的步：插入时完成规则就是 `{"manual": "imported from WORK.md: R2:2.1-3"}`；记一条带 `manual` 和 `evidence`（该步证据和整份请求两个产物号）的 `note`；然后**在同一个事务里**跑控制器用的同一个求值函数，得到 `plan_node_state_changed`（`planned → done`，原因 `done_rule_manual`）。
5. `[~]` 的步：`plan_node_state_changed`（`planned → active`，原因 `legacy_imported`）。完成规则留空。
6. `[ ]` 的步：`planned`，完成规则留空。

**请求自己要说得通**（复核 310 A3）：将来请求会经路由从线程交来（§4），所以校验时把每个节点的原行按 §2 的规则重读一遍，标题、状态、两个标记、`step_kind`、勾、标记时间、提交号、审批单号、复核编号都必须和原行读出来的一样，节点按行号递增、每条原行都在这一轮的表里（缩进比表头深）、每一步挂在它的原行前面最近的那一项下（复核 311 A1：否则可以把第二项的步挂到第一项、编成别的号）、`work_id` 都等于根的；不一致整份拒掉、什么都不写。引用（提交号、审批单号、复核编号）只认完整的号：审批单号 1–6 位，复核编号 3–4 位（「复核 18 次」是次数），复核的列表只认「、」「和」，逗号结束列表（台账里逗号后面是下一句，例如日期 10-14 不是复核 10–14）；每种最多留 20 个，复核的范围超过 20 个只留两头；凡是没留全的，证据里 `cut` 写明是哪一种（复核 311 B2；10-19 02:4x 的台账有两步提交号超过 20 个）。这只保证请求自洽；它的原行是不是真在 `WORK.md` 那个提交里，靠的是请求里的摘要和 §5 的对账，不是这一步。

导入完：`GET /plan?root=R2` 每步的 `state` 与 `WORK.md` 的勾一一对应（`x→done`、`~→active`、空→`planned`），`state_event` 写明它从哪来（`done_rule_manual` / `legacy_imported` / `plan_node_created`）；`GET /plan/{id}` 的事件里有那条证据 `note`；`GET /progress` 的计数与看板相同（01:20 那份是 7 项 53/74，02:4x 那份 53/75），其中 53 步计为「人工」。

**为什么做完的步走 `manual` 原子**：v5 定的不变式是「步做完只因为它的完成规则成立」，写 `done` 的只有控制器的求值；`manual` 原子正是为「人工补记、附证据」留的。导入前做完的事运行时没看见，标「人工」是实话。备选是直接把行以 `done` 插进去（`legacy_imported` 允许）：数据库不拦，但这些步就没有状态事件、也没有能重验的规则，`GET /plan` 的 `state_event` 是空的。不取。是否接受 Progress 上 53 步标「人工」见 §10 第 2 条。

**重复导入**：同一份请求再导一次，返回「已导入」和第一次的事件号，不写任何东西（按请求摘要认）；根已经存在、而请求不同（哪怕只差一个字），整个拒掉、什么都不写——导入之后改计划只走 `/plan/proposals`。运行时已经往前走了（新加了步、步做完了），同一份请求再来仍然只回「已导入」，不会把状态拉回去。

## 4. 首次导入的入口（要定：新路由）

| | A. `POST /plan/imports` + 一张决策卡（**推荐**） | B. 只给 admin 的 `POST /plan/imports`，同步导入 | C. `platform-api agentrt-plan-import` 子命令，作业里跑 |
|---|---|---|---|
| 做法 | 线程（reporter 令牌）交导入请求；平台校验、在保存点里试导一遍（所有触发器和延期约束当场跑）再回滚，然后给 Owner 发**一张**卡（「导入计划 R2：7 项 74 步，53 步按人工做完、10 步在做；来源 WORK.md@提交、摘要」）；他点 Apply，控制器现有的计划决定那一遍调导入函数落地，事件链上记 `plan_change_proposed → plan_change_decided → legacy_imported` | Owner 用自己的 admin 令牌在终端发一次请求，当场导入 | 请求放进 ConfigMap，挂起的 CronJob 模板（同 `agentrt-migrate`）用 `create_job_from_cronjob` 起一次 |
| 新增 | 一条路由；计划变更的决定那一遍认得「导入」这种提议（`plan_change_proposed` 的正文加一个产物号字段）；导入函数加一个参数，让 `legacy_imported` 的 `cause_event_id` 指向那条 `plan_change_decided`，决定和导入在同一个事务里（复核 310 指出现在的导入头没有这条因果）；卡片正文按导入写摘要（不逐条列每一步） | 一条路由 | 一个子命令；每个环境两份集群清单（CronJob 模板、ConfigMap），PROD 那份要 Owner 批 |
| Owner 要做 | STG、PROD 各回一张卡（一张卡定一件不可逆的事，属他的三件事） | 在他的终端跑两次带 admin 令牌的命令 | 批清单、批作业，每个环境各一次 |
| 好处 | 和计划变更同一条授权链（提议、卡、决定、落地都有事件）；线程不碰 admin 令牌；卡在 Console 和手机上都能回 | 代码最少 | 不增加 HTTP 面 |
| 坏处 | 代码比 B 多一截（试导、卡、决定分支），要复核 | 要他在终端跑命令、碰 admin 令牌；没有决策记录 | 清单和 ConfigMap 要发布、要批；改一次请求就要重发 ConfigMap；最慢 |

**推荐 A**：首次导入是整个第 2 轮最大的一次计划变更，本来就该落在「授权外的计划变更 → 决策卡」这条已有的链上；B 违背「不让他在终端跑命令」（W-31 多次教训），C 为一次性的事加两份集群清单不值。三者用的是同一个存储层导入函数（已实现，§9），所以选哪个只影响入口那一层。估：A 约半天写 + 一轮 Codex 复核；B 约 1 小时；C 约半天 + 清单发布。

**执行记录（10-19 22:5x–23:4x）**：冻结点 infra `a9fb2e4`；请求 `sha256:ebbf8723…61e9`（7 项 75 步）；本机测试库演练过（只差 7 个看板认不出的 ★）；STG 卡 `q_c3e173b6451f8be0`、PROD 卡 `q_0828de54f8d8d189` Owner 都选 Import；`diff` 两边都没有差异。第 6 步（看板改读接口）没做，表留作快照、不再更新，看板改读或退役并进 2.5 ⑤ / T24；第 7 步改为在表前加指针。

## 5. 导入后谁是事实来源、过渡期怎么对账

- **导入那一刻起，运行时是第 2 轮计划唯一的事实来源**（结构、编号、状态）。Owner 10-14 已对 v5 §7 第 4 条选 A：计划表导入后从 `WORK.md` 移出，只在 Console 和 MCP 看，`WORK.md` 留 `W-n` 索引和指向。
- **过渡期压在同一个工作时段内**（几小时，不是几天），按这个顺序，前一步不过不做下一步：
  1. 冻结：从第 2 步开始到第 7 步，谁都不改 `WORK.md`「第 2 轮逐项」（在线程里说一句，统筹线程执行）。
  2. 在冻结那一刻的 infra 提交上生成请求：`agentrt-plan-import generate -ledger …/WORK.md -commit <该提交> -o ~/agent-work/plan-import/r2.json`（工具只生成文件，不联网；MCP 的 `propose_plan_import` 只从这个目录读）；同时用看板自己的解析器读出 `board.json`（`roadmap.round_of` 的项和步，按 `planimport.View` 的形状；命令见文末「实现记录」），作为不依赖本工具的另一份读法。
  3. **先导进本机测试库**：`AGENTRT_PLAN_LEDGER=…/WORK.md AGENTRT_PLAN_BOARD=board.json AGENTRT_PLAN_EXTRA_STARS=<步号> go test ./internal/agentrt/agentrtapi/ -run PlanImportRealLedger`——同一份台账导入测试库，经真实路由读回，与工具和看板两份读法逐步相同。因为导错了在 STG、PROD 都改不回来（下面「导错了怎么办」），这一步不过不导 STG。
  4. STG 导入（§4 的入口）；读 STG `GET /plan?root=R2` 存成文件，`agentrt-plan-import diff -ledger …/WORK.md -plan stg-plan.json -board board.json` 必须没有差异（只有「看板看不到的 ★」那几行提示）。
  5. PROD 导入同一份 `r2.json`；同样 `diff` 没有差异。
  6. 看板改读接口（§6 第一段）；看板上的计划栏和改之前逐步相同（按 §2 的号、标题、状态比；★ 多出那几步）。
  7. 同一个 infra 提交里把「第 2 轮逐项」换成一行指针（「第 2 轮的计划在运行时：Console，或 `GET /api/v1/agentrt/plan?root=R2`；导入于 <时间>，请求摘要 <摘要>」），冻结解除。
- **对账工具**：`diff` 子命令把一份 `GET /plan` 的回应和 `WORK.md` 按 §2 逐步比（缺的、多的、位置、标题、状态、两个标记），带 `-board` 时再和看板自己的读法比一遍；它也核对回应本身是一棵树（根只出现一次、每个节点的号是「根:标签」、没有重复，复核 310 B3）。有差异退出码 1。第 7 步之后 `WORK.md` 里没有这张表了，它就不再用。
- **导错了怎么办**（复核 310 A5 后改）：节点删不掉（设计如此），而现在的计划变更里没有「丢弃」「改标记」（§2）。所以：导入前错 → 改台账或解析器、重新生成，什么都没写；STG 导入后才发现错 → STG 的 `R2` 只能留着，没开始的步可以改标题，别的错改不了，PROD 照样用修好的请求导（两个环境各自独立）；PROD 导入后才发现错 → 等 §10 第 6 条的操作上线再改，在那之前计划栏照实显示。第 3 步（本机测试库）就是为了让这三种情况尽量只发生在第一种。

## 6. 看板和 Console 计划栏改读接口的切法

两段，第一段随导入当天做，第二段是 2.5 本身：

1. **看板改读接口（导入当天，不改接口；Console 只改读失败的显示，见本段最后一条）**，下面几处一起改，少一处运行时就不是唯一来源（复核 310 A4、311 A3）：
   - `roadmap.py` 的 `round` 改为读 PROD `GET /plan?root=R2`（树）和 `GET /progress` 的 `plan`（项的计数，与运行时同一条计数规则），换成今天的形状：项 `key = label`、`name = title`、`done/total/state` 取计数；步 `id = label`、`t = title`、`state`（`done→done`、`active→doing`、`planned→todo`，`stopped`、`dropped` 原样）、`owner = owner_step`、`star = effect_step`。
   - `board2.py` 对来自运行时的 `round` **不再**跑 `overlay_events`、`overlay_probes`、`plan_lag` 和 `roadmap.finish`（`board2.py:492-531`、`:535-549`）：它们按本机派工记录和探针改步骤状态、再按数组位置重编号重算，会把运行时的状态盖掉（复核 310 的复现：本机一条旧的 `2.0-1` 派工记录能把运行时的 `planned` 勾成 `done`）。号和计数只取接口的。
   - 读失败时推 `{"unknown": "<原因>"}` 并**清掉**上一份 `round`：现在 `board2.py:384` 只在读到时才替换，读失败会留着旧的那份。也不退回读 `WORK.md`（SPEC §1：读不到就是未知）。
   - `when`（复核 310 A6、311 A2 后改）：从 `after_seq=0` 起分页读 `GET /events?stream=plan:R2`（每页 500 条），找第一条 `legacy_imported` 且 `source` 是 `plan-import sha256:…` 的（`planimport.ImportHead`；按 §4 A 导入时它前面还有提议和决定，前面也可能有别的事件，所以不能取第一条），按 `source` 得到请求的产物号，`GET /artifacts/<号>` 读一次请求（按号缓存，内容寻址不会变）；某步还停在导入给它的状态（`done` 且规则是导入写的 manual、`active` 且原因 `legacy_imported`、`planned` 且状态事件是创建）就显示原行的标记时间，否则显示状态事件的时间。这条规则就是 `planimport.FromPlanWithRequest`，Python 版照它写，端到端测试证明导入的步显示的是原行的时间、不是导入的时间。
   - `round_texts`（`board2.py:393-408`，每次生成都调）读的 `moved`、`day`、`guards`、`item["guard"]` 原来都由 `finish` 生成，运行时的 `round` 里没有，读失败的 `{"unknown": …}` 更没有；不改它，整份看板生成在这里抛 `KeyError`（复核 311 A3 实测）。对运行时的 `round`：「今天做完几步」「最近动的」从计划流的 `plan_node_state_changed` 事件按时间算，`guards` 和退出条件这两段第 2 轮不用、清掉；`unknown` 时这几段都不出。不能为了补字段再调 `finish`（它会重编号、重算计数）。
   - 改完要有三条整链测试再解除冻结，每条都穿过 `build` → `round_texts` → 推送的整份文档：本机旧派工记录与运行时冲突时以运行时为准；读失败显示未知、不留旧的；`dropped` 的步保留编号、不进分母。
   - **Console 也要改一处**（复核 311 A4，原稿写「一行不改」不对）：`parseRuntimeRound`（`console/src/api/agentRuntimePlan.ts:8-14`）把任何对象都读成一轮，`{"unknown": "PG unavailable"}` 会变成「没有项」，原因丢掉，`AgentsPlan` 显示「No round items published.」，把读不到说成了没有计划。要让解析保留 `unknown` 和原因，`AgentsPlan` / `ProgressPlan` 显示「Plan unavailable: <原因>」；测试 `parseRuntimeRound` 保留 `unknown`、`AgentsPlan` 读失败时的显示，输入就是这个占位对象。这是 Console 的一处小改，和看板改动同一天上（STG 先）。
2. **Console 直接读接口（2.5）**：`AgentsPlan` / `ProgressPlan` 加一个从 `GET /agentrt/plan` + `GET /agentrt/progress` 组 `RuntimeRound` 的适配（类型不变，`src/api/agentRuntimePlan.ts`），看板停止推 `roadmap.round`；T24 停掉看板程序验计划栏照常。

**原话放哪**：今天每步的 `when` 一栏里有大段原话（时间、提交、Owner 的话）。导入后**每一步**（不论状态）的原行都在整份请求的产物里（上面的读法一次读到）；做完的步另有一份单步证据产物和 `GET /plan/{id}` 里的那条证据 `note`，在做、没开始的步没有（复核 310 A6 指出原稿把这句写成了每步都有）。计划栏列表上显示标记时间或状态事件的时间；要在列表上直接看原话，适配从同一份请求里取 `evidence.line` 即可，不用改接口。

## 7. 导入后步骤怎么往前走（要定：这是 2.5 能不能结束的前提）

导入只解决「进来」。之后要让计划栏在没有看板的情况下照样对（T24），剩下 21 步必须由事件推进，而现在：

- 设完成规则（绑任务、绑审批单、绑门禁测试）不在常备授权里，要 Owner 的卡（一张卡最多 20 条变更，可以几步一起，但规则要等那一步的任务号、单号出来才写得出，实际是随工作推进一批一张）；
- 没有路由能记 `manual` 证据或 Owner 签收；
- 没有任何东西把步改成「在做」（`active` 现在只来自持续条件失效）。

不处理的话，导入之后计划栏会停在导入那一刻。选项（都要另批，这次不写代码）：

| | 做法 | 改什么 |
|---|---|---|
| **甲（推荐）** | 常备授权加一条：给**没做完**的步设完成规则，只要规则引用的都是这一步上的任务、绑在这一步上的审批或提问、门禁测试，且不含 `manual`，就自动决定；控制器在一步上第一个任务领到租约时把它改成 `active`（原因 `task_leased`） | 规则正文（Owner 签）；控制器加一个转移；计划变更的常备判定 |
| 乙 | 维持现状：完成规则都走 Owner 卡 | 不改；按活排出来的节奏一批一张，估 5–10 张（复核 310 指出原稿「每步一张、21 张」高估了） |
| 丙 | 导入时给每个没做完的步都设 `manual` 规则，再加一条记证据的路由，线程做完就记 | 一条新路由；剩下的步也都成「人工」，和 v5「由事件推进」的方向相反 |

推荐甲：剩下的步都能落到已有的事实上（补强实现 → 任务验收；独立复核 → 评审任务验收；「（你）批发布单」→ 审批单执行；★ → 门禁测试），规则只是把这些对象绑上去，绑错由存储层拒（T32），不值得每步打扰他。

## 8. 「架构对照」不在这一次

架构对照的每一行在运行时是 `arch_row`，勾由它的门禁测试按**当前部署**算（v5 §5.1.2），不存手写的勾；而今天的 14 行没有一行指定了门禁测试编号和钉住的规格摘要，「现在实际是什么」那段文字也没有列可放。现在导入只会得到 14 个 `tick: unknown`，比看板差。所以：架构对照在 2.5 里随「按当前部署求值」一起做，到时候每行先定测试编号和规格；在那之前看板继续从 `WORK.md` 读这一块（§6 第一段只换 `round`）。

## 9. 已实现的部分（分支 `w31/plan-import`，没有新路由、没改公开接口、没加表列）

见文末「实现记录」（提交号、测试结果、复核结论随实现补上）。

| 件 | 位置 | 做什么 |
|---|---|---|
| 解析与请求格式 | `api/internal/agentrt/planimport/` | 读 `WORK.md` 的「第 N 轮逐项」，按 §2、§3 生成导入请求（`agentrt.plan_import/v1`）；校验请求；请求 ↔ 看板形状的视图；视图之间逐步比 |
| 生成工具 | `api/cmd/agentrt-plan-import/` | `generate`（写出请求 JSON）、`diff`（`WORK.md` 对一份 `GET /plan` 回应，`-board` 再对看板自己的读法）；只读文件、只写文件，不联网 |
| 存储层导入 | `api/internal/agentrt/store/planimport.go` | §3 的事务；按请求摘要幂等；根已存在且请求不同就拒。内部函数，没有路由调它（入口等 §4） |
| 端到端测试 | `api/internal/agentrt/agentrtapi/planimport_test.go`、`store/planimport_test.go` | 测试库上导入后经真实路由读 `GET /plan`、`GET /plan/{id}`、`GET /events`、`GET /artifacts`、`GET /progress`，与解析结果、与看板解析器（`roadmap.py`）的输出逐步相同，每步的 `when` 是原行的时间；导两次节点和事件数不变；不同请求、自相矛盾的请求被拒且什么都没写；两个导入同时来只有一个落地；中途失败（已写了做完的步的证据之后）什么都不留；导入后用 `/plan/proposals` 加的步和项接着这套号 |

## 10. 要定的事

| # | 问题 | 推荐 | 谁定 |
|---|---|---|---|
| 1 | 首次导入的入口（§4）：A 路由 + 一张卡 / B admin 路由 / C 子命令作业 | **A** | **Owner 10-19 03:3x 定 A**，已实现（§11） |
| 2 | 做完的 53 步按 `manual` 原子进、Progress 上标「人工」（§3）；备选：不标人工、直接写 `done` | **manual** | 统筹线程（按推荐走并留痕即可，除非 Owner 不想在页面上看到「人工 53」） |
| 3 | 导入后步骤怎么推进（§7）：甲 / 乙 / 丙 | **甲** | **Owner 10-19 03:3x 定甲**；代码已实现、受规则门控，规则草案待他导入后签（§11） |
| 4 | 计划栏要不要在列表上直接显示每步原话（§6）：适配从请求产物里取（不改接口）/ `GET /plan` 加 `evidence` | **不改接口**，适配一次读请求产物 | 统筹线程 |
| 5 | 架构对照随 2.5 的部署求值一起做（§8） | 照此 | 统筹线程 |
| 6 | 计划变更加两种操作：丢弃一步（`drop_step`，写 `plan_node_state_changed` → `dropped`）、改一步的标记（`set_marks`，`owner_step` / `effect_step`）；都在常备授权外、走 Owner 卡（§2、§5「导错了怎么办」） | **加**，随 §4 的入口一起做；不加的话导入后的结构错只能留着 | **Owner 10-19 03:3x 定加**，已实现（§11） |

## 11. 第二片：Owner 10-19 03:3x「三件照建议」之后

分支 `w31/plan-import` 变基到 `origin/main` `35eafb7`（含决策卡与 TD-370）之后，提交 `e8ee5e9` → `120f5ac`（复核 313：4 A 1 B）→ `9322934`（复核 314：2 A 1 B）→ `695107e`（确认复核 315：0 A 1 B，收线）：

| 件 | 做法 | 测试 |
|---|---|---|
| `POST /api/v1/agentrt/plan/imports`（propose 角色，登记在 `actions/coverage.go`） | 校验请求 → 树锁 → 已导入过同一份就回「已导入」、不发卡；同一棵树已有一张未决的导入卡：同一份回那张卡，别的一份拒 → 在保存点里整份试导并 `SET CONSTRAINTS ALL IMMEDIATE`、回滚 → 存请求产物 → 一张卡（选项「Import the plan / Do not import it」，`owner_duty` irreversible，正文写几项几步、来源、摘要、两个答案各做什么）→ 记 `plan_change_proposed`（一条变更 `op: import`，带请求的产物号）。控制器现有的计划决定那一遍认出导入：Owner 选 Import，就在记 `plan_change_decided` 的同一个事务里从产物读回请求、重新校验摘要、落地，`legacy_imported` 的 `cause_event_id` 指向这条决定；导入时根已被别的方式建了，决定记 `failed` 和原因。`needs_you` 把它显示成「Import plan R2: …」和这两个选项。MCP 新工具 `propose_plan_import`：只从请求目录（`AGENTRT_PLAN_IMPORT_DIR`，默认 `~/agent-work/plan-import`）读请求文件——只打开一次、末级不跟随符号链接，检查的就是打开的那个文件（普通文件、不超 1 MiB、按设备号和 inode 确认它就是这个路径在目录里指的文件），从同一个描述符读、最多多读一个字节；目录外、经链接出目录、检查后被换掉或变大、FIFO 等非普通文件（以非阻塞方式打开，不会卡住 MCP）、不是请求格式的都拒、不发送（复核 313 A1、314 B1）。**挡不住的一种**（复核 314 A1，要定，见「要定」）：同一用户的另一个本机进程在两次路径解析之间把目录本身来回换成链接——Node 不能相对一个已打开的目录去打开文件；这样的进程本来就能直接读这些文件，所以这里防的是调用方把工具指向别的文件 | HTTP 端到端：viewer 401；提议后 `GET /plan` 404；同 key、换 key 同一份都回同一张卡、不再发卡；另一份在等时 422；`/progress` 的 needs_you 一条；回 Import 后 `GET /plan` 与台账逐步一致、导入头因果 = 决定、`ImportHead` 越过前面的提议和决定找到它；之后同一份回「已导入」、另一份 422；回 Do not import 什么都不写、可以再提；晚到的失败；提议时就被数据库拒（不发卡、不记提议）。MCP 7 种拒收和正常发送 |
| `drop_step`、`set_marks` | 都在常备授权外，走 Owner 卡。丢弃：最后执行，写自己的 `plan_node_state_changed`（→ `dropped`，原因 `plan_changed`，因果 = 那条 `plan_changed`），编号保留、出分母；这一步上还有未结束的任务、已经丢弃过、不是步骤都拒；丢弃之后这一步不再接活：新建任务挂到它、`move_task` 搬到它都拒（存储层在步骤锁下读状态；复核 313 A3。数据库触发器层的同一保证要一个新迁移，见下「另」）。改标记：只对步骤，至少给一个。MCP `propose_plan_change` 认这两种 | 丢弃后因果对得上、下一步编号越过它（`2.1-4`）；五种拒收在提议时就拒、不发卡；重复丢弃拒 |
| 规则种类 `plan-standing` | 两个开关：`done_rules`（规则生效且为 true 时，给**没做完、还没有完成规则**的步设第一条完成规则，在提议时自动决定，决定记「standing authorization (plan-standing vN)」；只限：同一提议里**不新绑**任何东西（新绑定是 Owner 的事）、只引用运行时自己记着的事实——这一步自己的任务、Owner 在这一步上的签收；**不含**审批和提问（它们是外部记录，运行时可能还没读到，证明不了「还没成立」；复核 314 A2）、manual、CI 结果（全局事实，任何一步都能拿来用）、门禁测试；并且规则在决定那一刻**还不成立**——不能拿已经成立的事实让一步当场做完；复核 313 A2 和自查）。所以要绑审批单、提问的完成规则（如「（你）批发布单」→ 审批单执行）仍走 Owner 卡，一批最多 20 条；`active_on_lease`（为 true 时，控制器每一遍把「有任务领过租约」的未开始步改成在做，原因 `task_leased`，因果 = 这一步的任务第一次 `attempt_leased`）。关掉一个开关算收紧（不用签），打开算放宽（要签）。没有这条规则生效时行为和今天完全一样。两处都先拿计划流的锁、再按当时的数据库时钟读规则，规则在等锁期间过期就什么都不放行（复核 313 A4） | 解析（闭合：非布尔、缺字段、多字段、带参数都拒）、收紧比较；有无规则两种情况下的放行与不放行（已有规则、含 manual、已做完的步都仍走卡）；领过租约的步变在做、没领过的不变、第二遍不再动 |
| Console | 看板发来的 `round` 是 `{"unknown": "<原因>"}` 时，Agents 页计划栏、首页 Work 的「The plan」卡、Progress 概览都显示「Plan unavailable: <原因>」，不再显示成「没有项」；`round.source` 是 `runtime` 时不再挂「✎ by hand（WORK.md）」 | 解析保留 `unknown` / `source`；三处显示各一条测试；Console lint、类型检查、全部测试、构建都过 |

**已签（Owner 10-19 23:5x，STG 与 PROD 都是 v1，读回核对过，签名指纹 `SHA256:HQBmsF…1M7k`）；原文：规则草案（给 Owner 导入后签，我没签）**：`bifrost-trade-infra/agent-config/agentrt-rules/stg/plan-standing.yaml` 和 `prod/plan-standing.yaml`（两份相同：`done_rules: true`、`active_on_lease: true`，有效期 2026-10-20 到 2027-01-20，未提交），已用平台的解析器读通。注意：签之前对应环境要先跑带这个提交的平台，旧平台不认这种规则会拒。签法同 `OWNER-STEPS-rules-o18-o19.md` 第 2 步（`rule.sh sign <文件>`，PROD 加 `--env prod`）。

**已定（Owner 2026-10-19 04:2x「314 A1 记为已知接受风险」，写进 ADR §5）**（复核 314 A1）：上面那一种竞态要不要关死。A（推荐）记为已知接受风险（同 ADR §5「同一系统用户」那一类：同用户进程本来就能读这些文件），代码里已写明；B 加一个原生 openat 小助手（新依赖），把「在这个目录里打开」做成一次调用；C 去掉读文件，改成工具只收已上传的请求产物号（请求得先经 `put_artifact` 整段传一次，约 160 KB 要经模型）。

**另**（不在这一片，交统筹线程定）：「丢弃的步不再接活」现在由存储层保证（两条写路径都改了）；要像其它计划约束一样由数据库触发器兜底，需要一个新迁移（改 `guard_task`，属 PROD DDL，随发版由 Owner 批）。

**看板（`board2.py` / `roadmap.py`）的改法是下一片**：它们不在这个仓库里（`~/agent-work/status`，没有版本控制，而且正在每 15 秒往 PROD 推），改法和要的三条整链测试见 §6 第 1 段；在导入当天、按 §5 的顺序做，Console 这半已经在这个分支上。

## 实现记录

- **分支** `w31/plan-import`（`bifrost-platform`，worktree `~/agent-work/w31-plan-import`，基于 `origin/main` `d788296`；没有上游、没推送）。提交：`32b1815`（第一版）→ `f459767`（复核 310：7 A 4 B）→ `1a59b05`（复核 311：4 A 2 B）→ `0fd9663`（确认复核 312：0 A 1 B，照改；另修了它的测试暴露的复核编号误读）。尾注手补（husky 仓库的 worktree 不跑钩子）。
- **测试**：本机 `AGENTRT_TEST_PG='host=127.0.0.1 port=55432 user=postgres sslmode=disable' AGENTRT_TEST_REDIS=redis://127.0.0.1:56379/0 AGENTRT_TEST_REQUIRED=1 go test ./...` 每轮都全过；`golangci-lint run --new-from-rev=origin/main ./...` 0 处（整仓 `make lint` 在 `main` 上本来就有 108 处旧问题，本分支没加）；code-health 在每个提交的干净检出上 OK（单文件不超 800 行）。
- **真实台账**：10-19 02:4x 的 `WORK.md`（7 项 75 步：53 做完、10 在做、12 没开始，第 420–503 行，摘要 `fd41807f…6376`）导入测试库后，经 `GET /plan` 与台账、与 `roadmap.round_of` 逐步相同，只差 7 个看板认不出的 ★；`/progress` 53/75、53 人工；每步 `when` 是原行的时间。
- **差分模糊**：3000 份随机台账（Unicode 缩进和空白、标记任意顺序、竖线位置）对 `roadmap.round_of`，项号、项名、步号、标题、状态、Owner 标记零差异；本工具只在标题为空或含控制字符时拒收（看板会照收）。
- **看板自己的读法**（§5 第 2 步要的 `board.json`），统筹线程在本机跑：

  ```bash
  python3 -c 'import json,sys; sys.path.insert(0, "/Users/vision-mac-trader/agent-work/status"); import roadmap; r = roadmap.round_of(open(sys.argv[1], encoding="utf-8").read()); json.dump({"items": [{"key": i["key"], "name": i["name"], "steps": [{"id": x["id"], "t": x["t"], "state": x["state"], "owner": x["owner"], "star": x["star"]} for x in i["steps"]]} for i in r["items"]]}, sys.stdout, ensure_ascii=False)' /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/WORK.md
  ```

- **第二片的复核**：313（4 A、1 B）、314（2 A、1 B）照改；315 是两轮之后的确认复核，没有 A，收线，那条 B（FIFO 测试没有截止时间）照改。每条 A 都配了在上一个提交上会失败的测试。314 A1（同用户进程来回替换目录的竞态）没有关，写明了，交统筹线程定（§11「要定」）。报告在 `~/agent-work/codex-review-31{3,4,5}/REPORT.md`。
- **第一片的复核**：310（7 A、4 B）、311（4 A、2 B），按停线规矩照改；312 是两轮之后的确认复核，只看改动：311 的 A1、A2 由代码关闭，A3、A4 由本方案 §6 关闭（看板和 Console 的改动属切换当天，尚未实施），B1 关闭，B2 剩一处（单步证据漏了 `cut`）。确认轮没有 A，这条线收；那处 B 照改，并修了它的测试暴露的一处误读（「复核 100–120，10-14」把逗号后的日期读成复核 10–14、「复核 18 次」读成复核 18），两处各配一条在上一个提交上会失败的测试。报告在 `~/agent-work/codex-review-31{0,1,2}/REPORT.md`。
