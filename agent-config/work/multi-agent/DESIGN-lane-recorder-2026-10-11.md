# W-66 第一半：记录事件，由事件生成状态（不裁决，不放行）

**2026-10-11 14:16 停线。** 第三稿经复核 76（`work/multi-agent/reviews/codex-2026-10-11-review76-w66-lane-recorder-design-r3.md`）：必须改的还剩 1 处——第 7 节的 V7 说 Unknown 不再变化，第 4 节的时钟规则说读的一方时钟追上之后要恢复，两者对序列 `open → declare(process) → start(at=300) → note(at=240)` 在 `now=240` 和 `now=440` 给出相反的答案；另有 4 处应该改的（逐工作判球用哪一份 ref 状态、`record_created` 要新鲜确认、`commands` 不发布与「原样保留」冲突、`after` 和 `usual_s` 的派生影响）。按事先写下的条件，这条设计线停，本文不作为实现的依据。重开要 Owner 一句话；重开后先改这 5 处。

状态：设计第三稿，2026-10-11。第一稿经独立复核 68，第二稿经复核 73（`work/multi-agent/reviews/` 下的 `codex-2026-10-11-review68-w66-lane-recorder-design.md` 和 `…review73-w66-lane-recorder-design-r2.md`），两次结论都是「先改」；对照在第 11 节。本稿是设计预算里记了账的唯一一次延长，停线条件事先写定：下一次复核还有必须改的，这条设计线停下。所以这一稿以删和简化为主（第 2 节）。Owner 当天已定把 W-66 拆成两半，本文只设计第一半：它不放行任何东西、不做任何裁决，输出不是判词；判通过和放行另出设计，第 9 节只列约束。没有代码。
输入：`WORK.md` 的 W-66；`DESIGN-lane-v2-2026-10-11.md`（已停的设计）；复核 35、38、43、62、65、68、73；`LESSONS-from-practice.md` 第 18、52、55、70、72、73、76、77、80 行；`OWNER-SURFACE-2026-10-11.md` 的 A5、A7、A8、B2、B5、D1 和 P6；本机看板 `~/agent-work/status/` 的 `board2.py`、`tasks.json`、`index.html`；平台源码 `bifrost-platform/api/internal/` 下的 `agentprogress/`、`approvals/`、`questions/`、`actions/objectname.go`、`actuation/auth.go`（只读了源码，没有调用任何接口，没有读任何凭证）；分支 `w31/w66-lane-v2`（`0a54279`，不合并）。

## 1. 缺口

今天的进展看板有两个来源，都不是事件。**手抄的**：`tasks.json` 由统筹线程逐条维护——有哪些事、每件事有哪些步骤、手工步骤的状态和起止时间、每步的结果说明、要 Owner 做的事和它的标记。**从文件推的**：其余步骤的状态由 `board2.py` 的 `step_status` 每 2 秒现读——开始取进度文件的创建时间，在跑取 `pgrep -f <pattern>`，卡住取文件多久没变，结束取 `done` 文件里的 `exit=`；一步的身份是进度文件路径、完成文件路径、进程匹配串，三样都能被下一轮复用。2026-10-11 这一天，这两个来源出了四次错：

| # | Owner 看到的 | 原因 | 当天的补丁 |
|---|---|---|---|
| 事故 1 | 等他批 #7 的那一步显示「发布已跑 70 分钟 / 预计 10」 | 监视脚本在等审批：进程活着，日志在长，于是这一步被算成已经开始 | `starts_when`：在日志里找一行字，找到才算开始 |
| 事故 2 | 三条重开的线，各自上一轮的步骤显示在跑 | 新一轮沿用了上一轮的进度文件名和进程匹配串（推断，依据是 `step_status` 对 `since` 的处理） | 旧文件改名，旧匹配串改成不存在的 |
| 事故 3 | 他在 Console 上批了 #8，看板上「需要你做的」那一条没有消失 | 这一条是手工状态，不读审批记录 | `closes_when`：在发布日志里找一行字，找到就合上 |
| 事故 4 | 正式环境的 Progress 页从夜里某个时候起不再更新，11:40 才发现 | 文档越积越大，服务端先回 400（某件事超过 20 步），后回 413（超过 256 KiB）；推送脚本永远安静、永远退出 0 | `slim_for_publish` 瘦身；`publish-result.js` 记下服务端的回答 |

**第五类，Owner 2026-10-11 13:10–13:20 看着这块手工维护的看板指出的**（已记为 `OWNER-SURFACE` 的 A7、A8、B5 和教训第 80 行）：要他办的事在页面上有三个手抄的数，互相对不上——顶部写 1 件，下面是另一份清单，还有一处「3 件在等我」，那个「我」其实是统筹线程。他的话：这些对不上，是因为一切靠手工维护；用系统维护的东西替掉手工，就是多 Agent 框架的价值。由此三条要求，是这件工具存在的理由：

- **要他办的事只有一份清单、一个数**。折叠只输出一份 `owner_all`；页面上那个数只由它得出（第 4 节）。
- **每件事写明怎么办**。在原有四个标记（现在能不能办、最晚什么时候、不办会卡住什么、办完之后）之外，再带 `advice`（统筹方的建议）、`where`（三个地方之一：线程里回一句 / Console 的 Needs you 里决定 / 他自己的终端里贴一条命令）、`reply`（怎么告诉统筹方，或者不用告诉）。
- **停着不是一种状态**。没有步骤在跑时，折叠要说球在谁脚下：`owner`、`coordinator`、`nobody` 或 `unknown`。

出处：事故 1、2 是 `OWNER-SURFACE` 的 A5，事故 3 是 D1，事故 4 是教训第 76 行；四个补丁仍然在读日志里的字和文件的时间，只留在本机看板。W-66 原本要一次补上这个缺口，同时做裁决和放行；五次独立复核（35、38、43、62、65）每次都在「证据不支持却能通过」上找到新的口子。教训第 70、77 行的诊断：一个程序同时是记录者、裁判和放行口，证据又是被检查的一方写的可改文件。看板要的只是第一样。

## 2. 范围与不做的事

- **做**：一份只追加的事件日志；一个把事件算成看板文档的纯函数 `fold`；一个把文档压进平台上限的纯函数 `publish_view`。消费方只有两个：本机看板，以及以后 Console 的 Progress 页（P6）。
- **从已停的设计留下的**（`DESIGN-lane-v2-2026-10-11.md`，这里不重述）：第 2 节的事件行格式和哈希链、残尾修复、不等待的 `flock`；状态由一个函数算出，没有可改写的状态文件；子进程用参数数组启动，不经 shell；源码里没有发信号的调用；每种事件的字段是闭合集合。分支上的 `events.py`、`fsutil.py`、`locks.py`、`repair.py` 连同测试可以拣过来（只细读了 `events.py`，另三个按文件名和复核 38 推断）。分支不合并。
- **丢掉的**：判定函数和判词、`passed` 和 `pass-set`、轮次预算、`resolve` / `abandon` / `confirm-ended`、intent 和 manifest、检出和 bundle、配置固定、`run.lock`、六关和转换表。轮次只剩一个显示用的数字。
- **两次复核之后删掉的**。第二稿：记录类步骤的开始和结束事件；绑定记录的等待的关闭事件；「名字前缀加创建时间」找运行；折叠里跨日志取中位数；监视脚本作为步骤；合上的 Owner 事项留 24 小时；`rec.py wait` 的退出码保证。这一稿：对样本日志做删改、把差异归成四种影响的测试（换成每个字段一条有名字的测试，第 7 节第 2 条）；`dead` 是终态的说法；观测事件里「读失败」的那一种写法和各项计数（失败和确认都只记在每轮的 `observer_round` 里）；`owner-open` 自己读到的状态（`first_seen`）；按审批 id 和尝试次数推算运行名的定位办法（只认给定的名字）；多匹配这种情形（按确切名字读，不会有）。

这一半永远不做的事：

| 不做 | 说明 |
|---|---|
| 不出判词 | 状态里没有「通过」。步骤结束后发布的字是 `Exited 0`（进程退出码为 0）、`Reported finished by coordinator`（统筹方报完成）或 `Record: Succeeded`（记录自己说成功），三种分开写。机器值 `done` 只因为 Console 现在按它上色才保留，它一定带 `ended_how`。验收和复核说了什么，只原样引用一行。怎么防别人把它当判词、防不住什么，见第 6 节 |
| 不出「通过集合」 | 不输出任何可以拿去合并或发布的提交号集合。`work_closed` 的 `claim: landed` 是统筹方的声明，文档里写成 `Coordinator declared: landed`；这一半不核对提交在不在主线 |
| 不管进程 | 不发信号、不结束、不重跑、不接续、不限制输出。包装器只做三件事：起进程、等它结束、记退出码。因为日志的状态记不成账（日志无效、写满、取不到锁）时照样起命令，退出码原样传回，stderr 写明没有记上；参数本身不合规（例如 `kind` 与 `watch` 不对应）是用法错误，什么都不起 |
| 不合并、不推送、不发布 | 没有任何 git 写操作 |
| 不写集群、不写平台 | 对真实记录只读：读审批、提问、流水线运行。向外的写只有现有的那一条「把看板文档推给平台」 |
| 不拦任何事 | 被拒的只有不合规的记账；没有哪条命令因为状态不对而不能运行。轮次预算照旧由统筹方按 ADR §12.2 第 15 条执行 |

## 3. 事件

```
~/agent-work/events/                              # 根目录可用 --root 改
  <work_id>/events.jsonl  lock                    # 一件事一份日志：只追加 · 一把 flock
  <work_id>/events.torn-<repair_id>               # 修复时挪出来的残尾
  <work_id>/runs/<run_id>/stdout stderr alive.lock  # 包装器独占新建，从不复用
  _observer/<UTC 日期>.jsonl  lock                 # 观测日志：每轮一条；lock 整轮持有
```

**写入**：只有 `rec.py` 的命令入口追加事件。一次追加：不等待地取这份日志的 `lock`（被占就重试 2 秒，再不行报错）→ 修复残尾 → 校验日志前缀 → 对着前缀折叠出的状态校验这条事件 → 写一行并 fsync → 放锁。锁只在一次追加期间持有。`seq`、`prev_sha256`、`at`（UTC，追加时的系统时钟）、`v`（恒为 1）由记录器填。`step_id`、`run_id`、`wait_id`、`round_id` 是记录器生成的随机 8 位十六进制，命令行不接受调用方给的值。

**哈希链证明什么，不证明什么**：每行带上一行的摘要。文件中间被改、被删、被调换顺序而没有重新封好，读的一方看得出来，从那一行起不再采信。它不是签名：同一个 Unix 用户可以把整份日志重写再封好，也可以从末尾整行截掉几条，这两种都查不出来。链也不说明内容是真的。它防的是失误和半写，不防有意的改写。

**字段通则**：每条事件都有 `type`、`v`、`seq`、`prev_sha256`、`at`、`by`；字段是闭合集合。`by` 是入口自己填的标签（`coordinator` / `wrapper` / `observer`），说的是从哪个入口进来，不是身份。观测类事件另有 `sampled_at`。事件里没有链接字段。**上限**：名字 80 个码点，其余文字 200 个码点，`commands` 至多 5 条、每条 400 个码点，都拒绝控制字符和 U+2028 / U+2029；一份日志至多 20,000 条、16 MiB；一件事至多 200 步、20 条没了结的等待。超了的写入被拒并说明原因；日志满了，这件事带 `log_full`。折叠至多读 200 份日志：超过时按日志文件的修改时间取最近的 200 份，其余的份数作为 `logs_unread` 交给折叠（第 4 节「折叠不完整」）。子进程的输出文件多大，这一半不限制（限制它就是管进程）；超过 1 GiB 时那一步带 `output_large`。`kind` 与 `watch` 的对应是闭合的：`implement`、`verify`、`review`、`merge`、`other` 只能是 `process` 或 `none`；`release` 只能是 `record`；`ci` 是 `record` 或 `none`。**监视脚本不是步骤**：等审批、等运行出现、持有发布窗口的脚本不声明成步骤，它活没活不上看板；发布这一步的真相只有那次运行的记录。

**四个词，第 3、4、5、7 节都按这里的意思用**：

- **结束事件**：`process`、`none` 类是一条有效的 `step_finished`；`record` 类是一条有效的、`condition` 为 `True` 或 `False` 的 `record_seen`。有结束事件的步骤是**结束了的**，状态只能是 `done` 或 `failed`。
- **开着的步骤**：状态是 `waiting`、`running`、`slow`、`quiet`、`unknown` 的步骤。`dead` 既不是结束了的，也不是开着的：它只说明最近一次探测时包装器不在了。它不挡关闭，否则包装器一死，这件事就再也关不掉。
- **没了结的等待**（按这份日志自己的事件判断）：`declared` 的（`ref.kind` 是 `none`）还没有 `owner_wait_closed`；绑定记录的还没有观测到权威终态（审批 `executed` / `failed` / `rejected` / `expired`，提问 `answered` / `withdrawn` / `expired`），也没有被撤回。
- **确认过**：一个要读真实记录的对象（一条绑定记录的等待，或一个有名字的记录类步骤），在最近完成的那一轮观测里被列进了 `confirmed`，而且那一轮的 `ended_at` 距 `now` 不超过 180 秒、也不在 `now` 之后 2 秒以上。

| 事件 | 字段（可选的另列） | 从哪个入口写 | 无效的情形 |
|---|---|---|---|
| `work_opened` | `work_id`、`title`；可选 `goal`、`work_ref`（台账编号） | 统筹方 `rec.py open` | 不是日志的第一条；`work_id` 与目录名不同 |
| `work_closed` | `claim`（`landed` / `stopped` / `dropped`，都是声明） | 统筹方 `rec.py close` | 已关闭；这件事还有开着的步骤或没了结的等待（原因代码 `closed_with_open_items`） |
| `step_declared` | `step_id`、`name`、`kind`、`who`、`watch`；`record` 类必填 `locator{cluster, namespace}`，其中 `name` 可以先不写；可选 `round`、`after`（`step_id`）、`usual_s` 加 `usual_basis`（`measured` / `declared`，由入口在声明时算好）；`record`、`none` 类可选 `waiting_on`（`wait_id` 列表） | 统筹方 `rec.py declare`；包装器（`rec.py run` 把声明和开始写在同一次追加里） | `step_id` 已存在；`kind` 与 `watch` 不对应；`process` 类带 `waiting_on`；`record` 类没有 `locator`；指向不存在的 id |
| `step_superseded` | `step_id`；可选 `by_step`（取代它的那一步；没有就是撤回）、`text` | 统筹方：`declare` / `run` 带 `--replaces <旧 step_id>` 时与新声明同一次追加；或 `rec.py withdraw` | `by_step` 不存在；没有 `by_step` 而这一步开始过（`process`、`none`：有 `step_started`；`record`：有过找到记录的观测） |
| `step_started` | `step_id`、`run_id`；可选 `command`、`pid`（只给人看） | `process`：只有包装器，写完紧接着创建子进程。`none`：统筹方 `rec.py start` | 没有声明；已开始过；已被取代或撤回；`record` 类；`by` 与 `watch` 不相配；`none` 类而 `waiting_on` 里还有没了结的等待 |
| `step_seen` | `step_id`、`run_id`、`sampled_at`、`alive`；可选 `output_bytes`、`text` | 只对 `process` 类。包装器每 60 秒一条（它正等着子进程，`alive: true` 是第一手的）；观测入口探到 `alive.lock` 空着，写一条 `alive: false` | 不是 `process` 类；没有开始；`run_id` 不符；这一步结束了；已有 `alive: false`；`output_bytes` 变小；`sampled_at` 不合规 |
| `step_finished` | `step_id`、`run_id`；`process`：`exit{code, signal}` 恰好一个非空；`none`：`reported`（`finished` / `failed`）；可选 `quote`（原样引用的一行） | `process`：只有包装器，值取自 `wait()`。`none`：统筹方 | 没有开始；`run_id` 不符；这一步结束了；`record` 类；`by` 与 `watch` 不相配。**已有 `alive: false` 不使它无效**：包装器自己记下的结束比观测方的探测权威 |
| `record_seen` | `step_id`、`sampled_at`、`found`；找到时另有 `uid`，可选 `started_at`、`ended_at`（记录自己的时间）、`condition`（`True` / `False` / `Unknown`）、`reason_quote`（记录自己写的原因） | 只有观测入口，只对 `record` 类：读成功、结果和上一条不同才写 | 不是 `record` 类；这一步结束了；这一步有 `step_superseded` 而此前从没找到过记录；`uid` 与这一步第一次找到时记下的不同；`sampled_at` 不合规 |
| `owner_wait_opened` | `wait_id`、`title`、`ref{kind, id}`（`approval` / `question` / `none`）；`none` 的必填 `can_act`（`yes` / `not_yet`），可选 `where`（`thread` / `console` / `terminal`）、`reply` 或 `reply_needed: false`、`reply_words`（线程里要回的原话）、`commands[]`（终端里要贴的命令，纯文字）、`deadline` 或 `no_deadline: true`、`blocks_nothing: true`、`not_before_text`；两种都可选 `advice`、`blocks_text`、`after_text`、`after`（`step_id`） | 统筹方 `rec.py owner-open`。绑定记录的：这条命令先读一次那条记录，只为挡住写错的 id——读到 404，或读到的记录的 `work_id` 与这件事的 `work_ref` 不同，就不写；读失败照样写。读到的状态不进事件 | `id` 不合格式（审批 `appr_` 加 16 位十六进制，提问 `q_` 加 16 位）；同一个 `ref` 在这份日志里已有没了结的等待；绑定记录的带 `where`、`reply`、`reply_words`、`commands`、`can_act`、`deadline`（这些来自记录和页面，不由 Agent 写）；`where` 不是 `terminal` 而带 `commands` |
| `owner_wait_seen` | `wait_id`、`sampled_at`、`ref_state`（平台的原词）；可选 `expires_at`、`number` | 只有观测入口，只对绑定记录的等待：读成功、状态和上一条不同才写 | 等待不存在；`ref.kind` 是 `none`；这条等待已了结；`ref_state` 不是平台那几个词；`sampled_at` 不合规 |
| `owner_wait_ready`；`owner_wait_closed` | `wait_id`；后者另有 `how`（`done` / `withdrawn`） | 统筹方，只对 `none`：声明这一条现在可以办了；合上它 | 已合上；`ready` 而已是 `yes`；绑定记录的等待（它的开合只由观测决定），唯一的例外是从没有过有效观测的那一条可以 `withdrawn`（写错了 id） |
| `note` | `text`；可选 `step_id` | 任何入口 | `step_id` 不存在 |
| `observer_round` | `round_id`、`started_at`、`ended_at`、`confirmed[]`（对象的键）、`failed[]`（`{key, error}`）；可选 `truncated: true` | 观测入口，每轮结束时一条，只进观测日志 | 出现在别的日志；`ended_at` 早于 `started_at`；两个列表合计超过 400 项；`error` 不在固定清单里 |

另有 `tail_repaired`，由残尾修复自己写，形状照已停设计的第 2 节。工作关闭之后，这份日志里只有给 `dead` 步骤补的 `step_finished`、`note` 和 `tail_repaired` 还有效，别的一律无效。一条事件有效不有效，只取决于同一份日志里它之前的事件，不取决于 `now` 和观测日志。**两层校验**：写入时拒绝（什么都不写，非零退出，说明原因）；折叠时再校验一遍，不假定写的一方校验过。**无效事件一律当作不存在**：必填字段缺了、类型不对、取值在闭合集合之外、多出字段、不认识的 `type`、或落在上表「无效的情形」里的，折叠跳过它，记进这件事的 `defects`（`seq` 和原因代码；代码的清单在任务书里列全），文档等于日志里没有这条事件时的文档。后果都按这一条推：无效的 `step_started` 让这一步留在 `waiting`，随后引用它的心跳和结束也跟着无效；无效的 `work_closed` 让这件事继续算没关闭，照旧参与 `ball` 和 `owner_all`。有 `defects` 的工作，页面在这件事上标 `Has ignored events`。链断了或行的格式坏了是另一回事：这件事标 `log_invalid_at: <seq>`，不按第 4 节的表取状态——有效前缀里已经关闭的工作不变；否则结束了的步骤照旧显示，**其余步骤一律是 `unknown`**（`log_invalid`），记录器拒绝再往这份日志追加。坏了或满了的日志、卡在 `unknown` 出不来的记录类步骤（记录被清掉了），没有事件能了结：统筹方把那份日志的目录挪出事件根目录，另开一份；挪走是手工动作，不是事件。

**记录类步骤的定位条件**只有一种：`locator{cluster, namespace, name}`，声明时写下，之后不改。声明时还不知道名字的可以先不写 `name`，这一步是 `waiting`；名字出来后用 `declare --replaces` 带名字重新声明（旧声明没开始过，从列表里消失）。记录器不猜名字：审批建出来的运行，名字由平台按审批 id 和尝试次数定（`api/internal/actions/objectname.go`），发布脚本看到运行出现时把名字补上。观测入口按名字 `get`，第一次找到时在 `record_seen` 里记下 `uid`；此后同名而 `uid` 不同的对象不算它，那一轮把它记成 `failed`（`uid_changed`）。`ci` 类按提交号找那次运行的办法没有核对：片 3 开工时核对，找不到唯一的名字，`ci` 步骤就声明成 `none`，如实显示为统筹方报的。

**时钟与观测方**：

- **采样时间**：`sampled_at` 是探测或读取之前那一刻的系统时钟，`at` 是追加时的。`sampled_at` 晚于 `at`、比 `at` 早 30 秒以上（等锁等久了的样本不写）、或早于同一对象上一条观测的 `sampled_at`，都无效。
- **互斥范围**：`rec.py observe` 整轮持有 `_observer/lock`（不等待，拿不到就退出并说明，不排队），采样和追加都在这把锁里，所以两个观测方不会交错。包装器不是观测方：它只写自己那次运行的第一手事件。
- **逐对象的确认**：一轮里每个对象读一次（同一个 `ref` 被几件事绑定也只读一次）。对象的键是 `approval:<id>`、`question:<id>`、`step:<work_id>/<step_id>`。读成功、并且结果已经在每一份有关的日志里（没变，或变化的那条事件追加成功），这个键进 `confirmed`；读失败、`uid` 变了、或变化的事件没能追加，进 `failed`，`error` 取固定清单：`unreachable`、`forbidden`、`timeout`、`bad_reply`、`not_found`、`uid_changed`、`no_credential`、`append_failed`。两个列表合计至多 400 项，放不下的不列并带 `truncated`。**没被确认过的对象一律是 `unknown`**：读失败的当轮就是，观测方停了的 180 秒后是，新声明、新开的在下一轮之前（至多 15 秒）也是。变化的事件和这一轮的 `observer_round` 两处追加都失败时，旧状态最多再显示 180 秒，然后因为没有新的一轮而成为 `unknown`。看板循环每 15 秒起一轮。
- **时钟异常**：① 回拨：一条事件的 `at` 比它之前最大的 `at` 早 2 秒以上，从它起到 `at` 追上之前的最大值为止是不可信区间；最近一条观测落在区间里的 `process` 步骤是 `unknown`（`clock_backwards`），跨区间的用时不显示。② 前跳或睡眠（本机夜里会睡）：同一次运行相邻两条观测隔了 180 秒以上，这次运行带 `gap`；缺口期间它因为没有新鲜观测而是 `unknown`，观测恢复后按规则重新取状态，但不再算 `slow` 和 `overdue`。③ 读的一方时钟落后：`now` 比这份日志里最大的 `at` 早 2 秒以上，在跑的 `process` 步骤是 `unknown`（`reader_clock_behind`）；观测日志同理，按「确认过」的定义不算确认。回拨和读方落后只通过第 4 节两张表的第 5 行起作用，缺口另外让 `slow` 不成立；结束了的步骤、`dead`、还没开始的 `process` / `none` 步骤、没有名字的记录类步骤都不受时钟异常影响。有回拨或缺口的运行，用时不计入估算。

## 4. 状态怎么从事件来

`fold(logs, observer_log, now, logs_unread) → 文档`。输入是各件事日志和观测日志的有效前缀、调用方给的 `now` 和没读进来的日志份数。函数不读文件、不看进程、不取时钟、不访问网络；同样的输入永远得到同样的文档。本机看板、`rec.py wait`、推给平台的那一份都调它，没有第二个算状态的地方。形状：`{at, observations_valid_s: 180, fold_complete, logs_unread, observer{last_round_at}, clock, ball, owner_all[], works[{work_id, title, source, steps[], defects[], withdrawn, closed_claim, log_invalid_at, log_full}], feed[]}`。

**文档里的字分两类**。折叠自己写的是代码：`state`、`label`、`ended_how`、`reason`、`can_act`、`ball.holder`、`ball.why`，值恰好是固定清单里的词，数字、时间、id 放在旁边各自的字段里（`exit_code`、`signal`、`since`、`seq`、`silent_s`），不拼进代码。`reason` 的清单：`exited_nonzero`、`ended_by_signal`、`reported_failed`、`record_failed`、`wrapper_gone`、`no_observation`、`no_output`、`clock_backwards`、`reader_clock_behind`、`log_invalid`、`not_confirmed`、`no_match`、`conflicting_observations`，加上第 3 节 `error` 的那八个。引语是别人写的字：工作的 `title`、`goal`；步骤的 `name`、`who`、`note`、`quote`、`command`、`superseded_text`、`reason_quote`（记录自己写的原因）；Owner 事项的 `title`、`advice`、`reply`、`reply_words`、`commands`、`blocks_text`、`after_text`、`not_before_text`；`feed[].text`。折叠从不把引语拼进代码；页面把引语当引语显示并署名（其中的「我」是写它的 Agent），页面自己的句子只用代码来写。

**步骤有八种状态**：`waiting`、`running`、`slow`、`quiet`、`unknown`、`dead`、`failed`、`done`。`unknown` 是「现在说不出它怎么样」，页面显示 Unknown 和原因；`quiet` 只表示「看得到它活着，但 420 秒没有输出」。`process` 和 `none` 类自上而下取第一条命中的：

| # | 条件 | 状态 | 附带 |
|---|---|---|---|
| 1 | 有 `step_finished`（结束事件） | `exit.code` 为 0 或 `reported: finished` → `done`；否则 `failed` | `ended` 是那条事件的 `at`。`done` 带 `ended_how`：`exit_0`（标签 `Exited 0`）或 `reported`（标签 `Reported finished by coordinator`）。`failed` 的 `reason`：`exited_nonzero`（另带 `exit_code`）、`ended_by_signal`（另带 `signal`）、`reported_failed`。之前有过 `alive: false` 的带 `was_seen_dead: true` |
| 2 | 有 `step_superseded`，这一步没有开始过 | 不进步骤列表，计入 `withdrawn` | — |
| 3 | 没有 `step_started` | `waiting` | `waiting_on` 里没了结的等待、`after` 指的那一步，对这一步的状态只是背景 |
| 4 | 最近一条观测是 `alive: false` | `dead` | `reason: wrapper_gone`，另带 `since`。页面的话：包装器不在了，没有记下退出，命令也许还在跑 |
| 5 | `process` 类：时钟不可信（第 3 节），或 `now` 距最近一条观测的 `sampled_at`（没有就取 `step_started` 的 `at`）超过 180 秒 | `unknown` | `reason`：`no_observation` / `clock_backwards` / `reader_clock_behind`；另带 `last_seen{state, at}` |
| 6 | `process` 类：有 `output_bytes`，它最近一次变大距 `now` 超过 420 秒 | `quiet` | `reason: no_output`，另带 `silent_s` |
| 7 | 有 `usual_s`，这次运行没有 `gap`，`now − started` 超过它的 1.5 倍 | `slow` | `overdue` 秒数 |
| 8 | 其余 | `running` | `none` 类带 `started_how: reported`，标签 `Reported started, not watched` |

只有第 1 行来自结束事件：到了之后，这一步的 `state`、`started`、`ended` 不再变。第 3–8 行都只是当时看到的样子，之后的事件可以改变它；`dead` 之后，能改变它的只有同一 `run_id` 的 `step_finished`。`process` 步骤在文档里一定带 `watch`、`kind` 和 `command`，页面在这一行上总是显示「进程 · 类别 · 命令行」。**被取代不是状态**：对一个开始过的步骤，`step_superseded` 只给它加 `superseded_by`，它的状态照旧按上表取；旧的一轮没结束，就如实显示它还在跑。重开一步不保证上一轮已经结束。

**记录类步骤**没有开始、结束事件，自上而下取第一条命中的。`started_at`、`ended_at`、`condition` 对应 Tekton v1 的 `status.startTime`、`completionTime` 和 `Succeeded` 条件，平台自己也这样读（`api/internal/delivery/service.go`、`pipeline_steps.go`）；它们是集群的时钟，`now` 是本机的，两者可能差几十秒，`slow` 的阈值是分钟级，不另处理：

| # | 情形 | 状态 |
|---|---|---|
| 1 | 有 `condition: True` 的观测（结束事件） | `done`，`ended_how: record`，标签 `Record: Succeeded`；`ended` 取 `ended_at` |
| 2 | 有 `condition: False` 的观测（结束事件） | `failed`，`reason: record_failed`，记录自己的原因在 `reason_quote`；`ended` 取 `ended_at` |
| 3 | 有 `step_superseded`，从没有过找到记录的观测 | 不进步骤列表，计入 `withdrawn` |
| 4 | `locator` 里还没有名字（没有东西可读） | `waiting` |
| 5 | 有名字，没被确认过 | `unknown`，`reason` 取那一轮 `failed` 里的 `error`，没有就是 `not_confirmed`；带 `last_seen` |
| 6 | 确认过，最近一条观测是 `found: false`（或还没有观测） | `waiting_on` 里有没了结的等待 → `waiting`；否则 `unknown`（`no_match`） |
| 7 | 确认过，找到了，没有 `started_at` | `waiting`。记录存在不等于开始 |
| 8 | 确认过，有 `started_at`，`condition` 是 `Unknown` 或没有 | `running`（超过 `usual_s` 的 1.5 倍是 `slow`）；`started` 取 `started_at`，不取事件的时间 |

**时间与估算**：`process`、`none` 类的 `started`、`ended` 只取对应事件的 `at`；没有那条事件，字段就不出现。估算在声明那一刻定下：`rec.py declare` / `run` 读各份日志里同一 `kind` 最近 20 次退出码为 0、没有时钟异常的运行，取用时的中位数写进 `usual_s`（`usual_basis: measured`）；不足 3 次用 `tasks.json` 里手写的数（`declared`）；再没有就不写，这一步没有预计，也不会是 `slow`。折叠只读这一步自己的 `usual_s`，所以一件事的步骤状态只取决于它自己的日志和观测日志。预计结束是 `started` 加 `usual_s`；这件事里有 `quiet`、`unknown`、`dead`、`failed` 的步骤时不给时间，标 `eta_unsure`。

**`owner_all`：要他办的事只有这一份清单**。今天的「Owner 步骤」和「常设事项」在事件里是同一种东西：等待。`declared` 的等待按 `wait_id` 各出一项，从不合并。绑定记录的等待按 `ref`（种类加 id）至多出一项，几件事绑定同一条记录时这样合：任何一份日志里有过这个 `ref` 的权威终态观测，它就不出项；否则记录一级的字段（`ref_state`、`can_act`、最晚时间）取各份日志里 `sampled_at` 最晚的那条有效观测，最晚的有两条而状态不同就是 `can_act: unknown`（`conflicting_observations`）；各件事自己写的字和 `holds_up` 按件分列在这一项的 `works[]` 里。次序：绑定记录的在前，其次按 `can_act`（`yes`、`unknown`、`not_yet`），再按最晚时间。折叠不输出 `needs_you`、`owner_now`、`owner_items`、`owner_next`，步骤上没有 `needs_owner`。**页面上只有一个数**：清单的长度；发布时清单被截过，就是长度加 `owner_all_cut`（第 5 节），页面只显示这一个和。办完的事项从清单里消失，进 `feed` 一行；四步回执归 `OWNER-SURFACE` 的 P4。

每一项带 `source`：`record`（绑定一条真实记录）或 `declared`（Agent 声明的，没有记录可对）。七个标记里，建议 `advice` 两种都是 Agent 写的、可缺；其余六个这样来：

| 标记 | `record` | `declared` |
|---|---|---|
| 现在能不能办 `can_act` | 只看记录（下一张表）。步骤做没做完不参与 | 统筹方声明的 `yes` / `not_yet`（`owner_wait_ready` 改成 `yes`），带 `can_act_basis: declared` 和 `not_before_text` |
| 最晚什么时候 | 记录的 `expires_at`，`deadline_source: record` | `deadline` 或 `no_deadline`；都没写就没有这个字段 |
| 不办会卡住什么 | `holds_up[]`：`waiting_on` 含这条等待的步骤和同一件事里声明在它们后面的步骤（算出来的）；另附 `blocks_text` | 同左；`blocks_nothing` 是统筹方的声明 |
| 办完之后 | `effect_s`：被卡住的第一步的 `usual_s`（算出来的）；另附 `after_text` | 同左 |
| 在哪办 `where` | 恒为 `console`，由种类推出；去那条记录的链接由页面按校验过的 `ref` 拼 | Agent 写的三选一，可缺。`terminal` 的另带 `commands[]`，页面逐条显示成可复制的文字，不执行、不做成链接；`thread` 的另带 `reply_words`。`declared` 的事项没有链接 |
| 怎么回 `reply` | 恒为 `reply_needed: false`：记录变了页面自己变 | Agent 写的，或 `reply_needed: false`，可缺 |

`declared` 的字段缺了就是缺了：文档里没有这个字段，页面显示 `Not written`，折叠不补默认值。`declared` 的事项在两个页面上、展开或收起，都带着 `Declared by coordinator, not a record` 这行字；它的 `can_act: yes` 是统筹方的说法，不是权威的可办判断。将来才会有记录的事（一张还没建的发布单）先开成 `declared` 的 `not_yet`；记录建出来后，`owner-open --approval <id> --replaces <wait_id>` 在同一次追加里开出绑定的那一条、把原来那条记成 `withdrawn`。

**绑定记录的等待，开合只由记录决定**。自上而下取第一条命中的；状态名是平台的原词（`approvals/types.go`、`questions/types.go`）：

| # | 看到的 | 这一项 |
|---|---|---|
| 1 | 有过权威终态的观测（审批 `executed`、`failed`、`rejected`、`expired`；提问 `answered`、`withdrawn`、`expired`），或从没有过有效观测而被撤回 | 了结，不在清单里，记原词。之后读不到、读失败都不会让它回到清单；每份有关的日志都记下终态之后，观测方不再读它 |
| 2 | 没被确认过（读失败、404、没有凭证、观测方停了、刚开出来还没轮到），或还没有一条有效观测 | 在清单里，`can_act: unknown`，`reason` 取那一轮 `failed` 里的 `error`，没有就是 `not_confirmed`；带 `last_seen{ref_state, at}`。页面显示 `Unknown, last read <时间>`，不显示成待批 |
| 3 | 确认过，审批 `pending`；提问 `open` | 在清单里，`can_act: yes` |
| 4 | 确认过，审批 `unknown`（平台的原词：执行结果不明，等他在 Console 上 resolve） | 在清单里，`can_act: yes`，`ref_state: unknown`。页面用「执行结果不明」这句话，不和 Unknown 状态混 |
| 5 | 确认过，审批 `approved`、`running` | 不在清单里：他那一步办了，记录还在走。等待还没了结，观测方继续读它，为的是接住平台的 `unknown` |

**`ball`：没有步骤在跑时，球在谁脚下**。先给每件没关闭的工作（没有有效的 `work_closed`）判一个归属，自上而下取第一条命中的：

| # | 这件事 | 归属和 `why` |
|---|---|---|
| 1 | 有步骤是 `running`、`slow`、`quiet`（`step_running`）；或有记录类步骤找到了记录、还没开始（`record_created`）；或有一条等待落在上表第 5 行（`record_in_flight`） | `agents` |
| 2 | 有步骤是 `unknown`（`step_unknown`）；或日志无效（`log_invalid`）；或它的事项里有 `can_act: unknown`（`owner_item_unknown`） | `unknown` |
| 3 | 有 `waiting` 的步骤，它不等任何没了结的等待，`after` 指的那一步也结束了或没有（`next_not_sent`） | `coordinator` |
| 4 | 它的事项里有 `can_act: yes` | `owner`（`owner_can_act`）；只凭 `declared` 的事项得出时带 `basis: declared` |
| 5 | 它有事项、而且都是 `not_yet`（`owner_item_not_ready`）；其余情形一律是 `ended_awaiting_check`，例如没有开着的步骤而工作没关闭，或步骤在等一个 `dead` 的步骤 | `coordinator` |

再合成一个 `{holder, why, since}`：`logs_unread` 大于 0 → `unknown`（`fold_incomplete`）；否则有一件是 `agents` → `agents`；否则有一件是 `unknown` → `unknown`；否则有一件是 `coordinator` → `coordinator`（琥珀色，`since` 是让它成立的最后一条有效事件的 `at`：做完的在等它看，或下一步没派出去）；否则有一件是 `owner` → `owner`（红色）；一件没关闭的工作都没有 → `nobody`（绿色，`queue_done`）。关闭的工作里没有开着的步骤，也没有没了结的等待（`work_closed` 的有效条件），所以绿色不会盖住一件还开着的事。**折叠不完整**：`logs_unread` 大于 0 时 `fold_complete` 是假，`ball` 是 `unknown`，清单可能缺项：页面把那个数写成「至少 n」，并写明有几份日志没读。

**读的一方自己查快照有多旧**，不靠折叠再算一遍：循环停了、本机睡了，就不会有新的 `fold(now)`，旧文档里的 `running` 不会自己变。两个页面用同一个期限 180 秒（`observations_valid_s`）：文档的生成时间 `at` 距读的一方的现在超过它，所有没结束的步骤的状态、`can_act` 和 `ball` 一律显示 Unknown，并写「这是 <时间> 的情况」。本机看板已有类似的检查（`index.html` 对 `status.json` 超过 15 秒就标旧），片 2 加上这条覆盖。Console 看的是生成时间，不只是收到时间：服务端回答里的 `age_seconds`（距收到）加 `generation_lag_seconds`（收到时距生成）超过 180 秒，或后者小于 −30 秒（生成时间在服务端的将来），就按上面覆盖；这样反复推一份旧文档不会显得新鲜。两台机器的时钟差会直接算进去，差得多了页面就一直是 Unknown。

**四起事故各由哪条规则挡住**：

| 事故 | 规则 | 为什么不会再出现；不保证什么 |
|---|---|---|
| 1 等审批的监视被算成在跑 | `kind` 与 `watch` 的对应；`process` 类不能带 `waiting_on`；记录类的 `started` 取记录的 `started_at` | 发布步骤不能声明成 `process`，包装器也就包不住它；记录存在而没有开始时间时是 `waiting`。**不保证**：有人把监视脚本包成一个 `kind: other` 的进程步骤并起名「发布」。页面在这一行上总是显示「进程 · other · 命令行」，读出来就是一条在跑的命令；真正的发布步骤仍是 `waiting` |
| 2 上一轮的步骤被算成在跑 | id 由记录器生成；`step_seen` 要对上 `run_id`；折叠不读文件；取代是显式事件 | 新一轮的心跳落不到旧步骤上，结束了的旧步骤不会被改。旧的一轮真的还在跑时，页面如实显示两轮都在跑，旧的带 `superseded_by`。**不保证**上一轮已经结束 |
| 3 批了之后那一条不消失 | 绑定记录的等待只由观测开合；统筹方没有命令能合上它或让它开着；没被确认过就是 `unknown` | 观测在跑而且读得到时，他批完之后下一轮（15 秒）这一项消失。**不保证**观测一定在跑：停了的时候这一项是 `Unknown, last read <时间>`，不是一个看起来新鲜的「待批」 |
| 4 推上去的文档超限，没人知道 | 第 5 节「发布的文档有界」 | 每一条上限都在 `publish_view` 里；夹具过平台真实的校验；服务端每次的回答被记下并显示 |

## 5. 和现在的接法

- 记账入口：`open`、`close`、`declare`、`withdraw`、`start`、`finish`、`owner-open`、`owner-ready`、`owner-close`（只对 `none`）、`note`。读的入口：`fold`（本机文档）、`fold --publish`（先 `fold` 再 `publish_view`）、`wait`。
- `run [声明用的参数] -- <命令>`：独占新建 `runs/<run_id>/`，取 `alive.lock`（不传给子进程），把 `step_declared` 和 `step_started` 写在同一次追加里，紧接着起子进程；每 60 秒写一条 `step_seen`（输出文件的长度，和末尾 4 KiB 里的最后一行）；`wait()` 返回后写 `step_finished`，再用同样的退出码退出。子进程创建失败时补一条 `step_finished`（`exit.code` 127，`quote` 是系统的错误文字）。
- `observe`：一轮做三件事再退出——对每次没有结束事件的 `process` 运行探测 `alive.lock`（不读 PID，不发信号；锁随持有进程死亡释放、不被子进程继承，已停设计第 13 节第 2 条核对过）；对每个在某份日志里还没了结的 `ref` 读一次平台；对每个有名字、没结束、没被撤回的记录类步骤读一次集群；有变化的写进各份有关的日志，最后写 `observer_round`（`confirmed` 和 `failed`）。看板循环每 15 秒起一轮 `observe`，每 2 秒 `fold` 一次。
- **读取凭证**：审批和提问用现有的非管理员 reporter 令牌，取法和推送脚本一样：环境变量 `PLATFORM_REPORTER_TOKEN`，或 `~/.config/bifrost/lineage-reporter.token` 的第一行（`scripts/thread-heartbeat.js` 现在的读法）。`GET /api/v1/approvals/{id}` 和 `GET /api/v1/questions/{id}` 要的是 viewer，reporter 的等级够（`approvals/handler.go`、`questions/handler.go` 的 `Mount`，`actuation/auth.go` 的 `roleLevel`）；这是按源码说的，没有对真实服务调用过，片 3 的第一件事是一次真实的只读读取。永远不用管理员令牌，不读 `mcp-tokens.env`；令牌不打印、不进事件。没有令牌时，每个 `ref` 每轮都进 `failed`（`no_credential`），绑定记录的事项全部是 `can_act: unknown`。流水线运行用集群的只读身份 `bifrost-agent`，只有 `kubectl get`。

| 现在的做法 | 改成 |
|---|---|
| `~/agent-work/verify-branch.sh <目录> …`，结果在 `verify.txt`、`verify.done` | `rec.py run --work <id> --kind verify --who Claude --name … -- ~/agent-work/verify-branch.sh …`。记下的是退出码；stdout 的末行作为 `quote` 原样引用。片 2 只接这一种 |
| 实现：`node scripts/thread-heartbeat.js run cursor -- …`，输出进 `cursor.json`，结束写 `cursor.done`。复核：`~/agent-work/codex-review-<n>/` 下的 `BRIEF.md`、`run.log`、`run.done`、`REPORT.md`，启动命令是手敲的（两处都是推断） | `rec.py run --kind implement --who Cursor --name … -- node scripts/thread-heartbeat.js run cursor -- …`，平台的线程心跳照旧；`rec.py run --kind review --who Codex --quote-first-line <REPORT.md> -- codex exec …`，报告的首行只引用，不解析 |
| `release-stg-next.sh`、`release-prod-next.sh`：等运行出现、盯它、持有发布窗口 | 脚本照旧做它自己的事，不是步骤。发布步骤声明成 `record` 类；运行出现时脚本用 `declare --replaces` 把名字补上，此后它的状态由 `observe` 读集群得出。脚本死了，表现为审批了结了而步骤一直 `waiting`，球判给 `coordinator` |
| `watch-agents.sh name=进度=完成=匹配串 …` | `rec.py wait --step <id> …`：先 `observe` 一轮，再折叠；所列步骤都结束了，或其中一步是 `dead`、`quiet`、`unknown`，或到了时间上限，就打印状态并退出。叫醒统筹线程用的和 Owner 看到的是同一个状态 |
| `mark.py` 给手工步骤盖时间；手改 `tasks.json` 的 `needs_you`、Owner 步骤、`closes_when` | `rec.py start` / `finish`（`none` 类）；`rec.py owner-open --approval <id>`、`--question <id>`，或不带记录的 `--where … --advice … --reply …` |

**迁移**按第 8 节的四片走。并读期间按步标来源：有记录器 `step_id` 的步骤来自折叠，其余照旧来自 `tasks.json`，每步带 `source: events` 或 `hand`，看板上标出来。`owner_all` 和 `ball` 在片 3 结束时改由折叠给；在那之前仍是 `board2.py` 的手工清单，标 `hand`。片 4 之后 `tasks.json` 只留每件事的 `goal`、`risk` 和每类步骤手写的往常用时（全局计划和排队归 `OWNER-SURFACE` 的 P5）；删掉步骤清单、`needs_you`、`starts_when`、`closes_when`、`since`、`closed-steps.json`、`mark.py`，以及 `board2.py` 的 `step_status`、`started_line_time`、`alive`、`owner_all`、`slim_for_publish`。

**发布的文档有界**。`publish_view(文档, host) → 文档` 是纯函数，片 2 起整份看板文档（两种来源的工作都在内）都经过它。平台对这份文档的全部限制，读自 `agentprogress/` 的 `schema.go`、`document.go`、`handler.go`、`recorder.go`：

| 限制 | 值 |
|---|---|
| PUT 的正文 | 不超过 262,144 字节（256 KiB），按收到的字节算；超了 413 |
| 服务端存的那一份 | 文档经脱敏、重新编码，再包上 `received_at`、`host` 的外壳之后，同样不超过 256 KiB；超了 413，保留上一份 |
| 数组长度 | `works` 30；`works[].steps` 20；`owner_now` 10；`owner_now[].actions` 10；`needs_you` 30；`feed` 50；`recent` 30。超了 400 |
| 正文的形状 | 恰好一个 JSON 对象，后面不能有别的；`at` 必须有，是有限的数字 |
| `host` | 匹配 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`，或者不写 |
| 已知字段的类型 | `schema.go` 里逐个列着（例如步骤的 `name`、`who`、`state`、`label`、`note`、`doing` 是字符串，`started`、`ended`、`last`、`usual_min`、`eta_start`、`eta_end`、`overdue` 是数字）。类型不对 400；值是 null 现在按没有这个字段算，本设计仍然不发 null |
| 不认识的字段 | 原样保留，没有个数上限，只受字节上限约束。`owner_all`、`ball`、`omitted` 都属于这一类，上限由 `publish_view` 自己定 |
| 字符串和键名 | 全部经过服务端脱敏，长度可能变。键名含 `token`、`secret`、`password`、`passwd`、`authorization`、`api_key`、`apikey`、`credential`、`cookie`（不分大小写）的，整个值被换成 `[redacted]`：文档的键名不许含这九个词 |
| 多旧算旧 | 收到超过 5 分钟，读的一方得到 `stale: true`；回答里另有 `age_seconds`、`generated_at`、`generation_lag_seconds` |

- **`publish_view` 留工作至多 30 件**，按这个次序留：有 Owner 事项或有 `unknown` / `dead` / `failed` / `quiet` 步骤的未关闭工作 → 有在跑步骤的 → 其余未关闭的（最近有事件的在前）→ 已关闭的（最近关闭的在前）。留不下的记进顶层 `omitted_works{open, closed}`；有未关闭的被截时，`incomplete` 里有 `works`。总量也发：顶层 `works_total{open, closed}`，每件事 `steps_total`。凡是有东西被截或被减，文档带 `full_at: local_board`，页面写明全量在本机看板（`host`）。
- **每件事至多 20 步**，按这个次序留：`unknown` → `dead` → `failed` → `quiet` → `slow` → `running` → `waiting`（按声明顺序）→ 最近的 `done`；被取代且结束了的排最后；不认识的状态值按 `unknown` 的次序留。留不下的记进这件事的 `omitted`，八种状态各有计数。`feed` 至多 25 条。`commands` 的正文不发，照 `slim_for_publish` 现在的做法只留 `commands_at: local_board`。
- **`owner_all` 只有一条截断规则**：按清单的次序从头留，至多 30 项；字节放不下时（下一条的第 ⑥ 级）从末尾再往前截。两种截法截掉的都是排在最后的整项，条数都加进同一个 `owner_all_cut`，`incomplete` 里有 `owner_all`。留下的每一项全部字段原样保留。文档里没有另一个总数字段：页面的那个数是留下的条数加 `owner_all_cut`，只显示一次，旁边写「这里列出 m 件，全量在本机看板（`host`）」。
- **字节**：目标 204,800 字节（200 KiB），量的是推送脚本实际发出去的那串字节：UTF-8 编码的紧凑 JSON，`host` 已经在里面，推送方原样发送、不再解析重排。量的是编码后的实际长度（转义、嵌套列表、`defects` 都在内），不拿字数乘系数。留出的 56 KiB 给服务端的重新编码、脱敏改写和外壳。超了就按固定次序减，每减一级重新量：① 去掉结束了的步骤的 `note`、`quote`、`command` → ② `feed` 留 10 条 → ③ 已关闭的工作换成摘要 → ④ 每件事只留没结束的步骤，至多 5 步，不带 `note` → ⑤ 每件事都换成摘要 → ⑥ `owner_all` 从末尾整项截掉，一项一项量着往第 ⑤ 级的骨架里加，所以一定放得下（骨架本身不超过目标，测试用顶格输入核对）。到了哪一级，文档带 `reduced: <级别>`，两个页面都显示「内容已缩减」。**摘要**里每件事恰好这些字段：`work_id`、`title`、`state_counts`（八种状态各几步）、`unknown_reasons`（至多 3 个 `reason` 代码）、`unknown_reasons_omitted`（没列出的个数）、`defects_count`，以及有的话 `log_invalid_at`、`log_full`、`closed_claim`。**每一级都留着的**：顶层的 `at`、`observer`、`clock`、`ball`、`fold_complete`、`logs_unread`、`reduced`、`incomplete`、`omitted_works`、`works_total`、`full_at`；每件事的 `log_invalid_at`、`log_full` 和八种状态的步数（没换成摘要的是留下的步骤加 `omitted`，换成摘要的是 `state_counts`）。没换成摘要的工作里，留下的每一步都带 `state`、`reason`、`last_seen`，没结束的 `process` 步骤还带 `kind` 和 `command`。
- **Console 读哪一份**：Console 的 Progress 页从 W-62 第四片第 3 轮起读 `owner_all`，没有这个字段才退回旧字段（`console/src/pages/shell/progress/`）。本文的发布形状只在三样都到了 PROD 并验收之后启用：读 `owner_all` 的那一版；Console 自己配的状态字改成第 2 节的三种写法；第 4 节那条 180 秒的过期覆盖。所以 `publish_view` 不输出 `owner_now`，也不输出任何第二份投影：文档里列他的事项的字段只有 `owner_all` 一个。在那之前，片 2 不切换推送来源，`board2.py` 照旧推它现在那份。服务端的校验今天不认识 `owner_all`，把它当未知键放过，只受总字节数约束；所以清单自己的上限由 `publish_view` 定，就是上面那一条截断规则。推送仍用现有脚本；服务端每次的回答（状态码、原因、字节数）照 `publish-result.js` 现在的做法记下，显示在本机看板上；`scripts/progress-publish.js` 改成返回状态，归 TD-308。

## 6. 信任与滥用

每一条事件都是某个 Agent 或它启动的脚本写的，写的一方和读的一方是同一个 Unix 用户。对折叠和渲染来说，事件是不可信的输入：只校验形状，不执行、不解析里面的文字。入口的分工是约定，由命令行的入口执行；手工拼一行封好的事件可以绕过它，包括伪造一条 `by: observer` 的观测或一轮 `observer_round`。

- **一条错的或恶意的事件能造成什么**：一块说错话的本机看板。没跑的步骤显示 `Exited 0`；在跑的显示失败或 Unknown；伪造的观测让一张待批的单在本机看板上显示成已批，或让一张不存在的单显示成待批；凭空多出一条「需要你」；估算被写歪；大量事件把日志写满、把发布的文档挤到缩减级别。统筹线程和 Owner 都看这块看板，所以会被它带偏；验收脚本、独立复核、CI、审批这些闸门不读它。**它造成不了什么**：没有东西因为它被合并、发布或批准。记录器不持有能写的凭证，不调平台的写接口，不写集群。
- **页面把 Agent 的声明和权威记录分开**：每个 Owner 事项带 `source`。本机看板上绑定记录的事项写的是 `Read by observer at <时间>`，旁边是去 Console 的链接；它是 Agent 一侧读了之后写的事件，不是权威。**权威只有 Console**：P6 的要求是 Console 拿 `ref.id` 去对平台自己的审批和提问记录，状态用平台自己的；推上来的文档里有、平台里找不到的 id，显示成 `Unknown record`，不显示成待批。`declared` 的事项始终带着 `Declared by coordinator, not a record`，没有链接；它的命令和要回的原话只是给人看的文字。链接只给 `source: record` 的事项，由页面按校验过的 `ref`（种类、id、编号）拼出，主机名是页面自己的常数；id 的格式在写入和折叠时各校验一遍。
- **「不当判词」能做到哪一步**：词表里没有通过。防线在片 1 交付，登记进 `RATCHETS.md`。受保护的入口：`bifrost-trade-infra` 的 `scripts/release/`、`k8s/cicd/`、`agent-config/scripts/git-hooks/`、`agent-config/scripts/agent-guard/`；平台的 `approvals`、`actions`、`delivery`、`releasepolicy`、`gitops`、`promote` 这几个包。检查两样：前四个目录的文本里不出现 `agent-work/events`、`agent-work/status`、`recorder/`、`rec.py`、`board2`、`status.publish`、`agent/progress`（写本文时这七个词在那里一处都没有）；后几个包不依赖 `agentprogress`（平台仓库里一条依赖测试，照 `questions/deps_test.go` 的写法；现在只有 `server` 包引用它）。**它挡不住的**：别名和软链接；这些目录之外的包装脚本（`~/agent-work/` 下统筹方自己的脚本不在任何仓库里）；把文档复制成别的名字再读；以后新加的消费者；以及人和 Agent 看了看板之后自己做的判断。`done`、`landed`、`can_act`、`rec.py wait` 的退出码都可能被人或新工具当成判词；`wait && 合并` 这样的命令写得出来、也会执行合并。这条防线只保护列出的入口，不是普遍的放行保证。第二半若要读事件，只能当线索（第 9 节）。
- **对着真实记录核对的**：审批和提问的状态、过期时间，读平台的只读接口；流水线运行的状态和起止时间，读集群。进程的退出码是包装器从 `wait()` 取的第一手数，但它仍是 Agent 一侧写的事件，只用于显示。提交有没有进主线、有没有发到某个环境，这一半不核对，也不显示成事实。给 Owner 看的文字：页面按纯文本插入引语，不当 HTML，加引号并署名，不按它上色。
- **没有处理的**：同用户重写整份日志或伪造观测（上面已说）；`declared` 的事项完全靠统筹方，它可以一直开着（第 10 节）；子进程输出占多少磁盘；把坏日志挪出根目录这个手工动作有没有被正确使用。折叠的耗时由日志条数和份数的上限界定：片 1 用顶格夹具量一次，本机上一轮超过 2 秒就调小上限，不调慢看板。

## 7. 验收

每条写成「输入 → 期望的文档」。断言的对象是看板和推送实际拿到的东西，即 `fold` 和 `publish_view` 的输出，不是内部的中间量（教训第 77 行）。

1. **折叠是纯函数，穷举短序列**。字母表在任务书里列全：一件事；一个 `process` 步骤、一个 `record` 步骤、一个 `none` 步骤；一条绑定审批的等待、一条 `declared` 的等待；每种事件，含带错 `run_id` 的心跳、`by` 不相配的开始、平台每一种审批状态的观测、`at` 回拨的事件、带 `confirmed` 和带 `failed` 的 `observer_round`、`work_closed`。穷举长度不超过 5 的全部序列，`now` 各取三个值（末条事件当时、之后 200 秒、之后 2000 秒；V7 只在这个范围里说话）。静态检查：折叠和 `publish_view` 所在的模块不导入 `os`、`time`、`subprocess`、`socket`、`pathlib`，不调用 `open`。对每个前缀断言：
   - V1 不抛异常；`publish_view` 的输出满足第 5 节的每一条限制。V2 一步是 `running` / `slow` / `quiet` ⇒ 它没有结束事件，并且：`process` 类有有效的 `step_started`，最近一条观测（还没有就取 `step_started`）距 `now` 不超过 180 秒、不是 `alive: false`；`none` 类有有效的 `step_started`；`record` 类确认过，最近一条有效观测找到了记录、带 `started_at`。V3 只有结束事件定下的状态不再变：一步有了结束事件，更长的前缀、更大的 `now` 下，它的 `state`、`started`、`ended` 不变；`waiting`、`running`、`slow`、`quiet`、`unknown`、`dead` 都可以被之后的事件改变，`dead` 之后能改变它的只有同一 `run_id` 的 `step_finished`。V4 `started`、`ended` 等于对应事件的 `at`（记录类等于观测里的 `started_at`、`ended_at`）；没有来源就没有这个字段。V5 无效事件当作不存在：把折叠判无效的事件全部从序列里删掉再折叠，除 `defects` 外文档逐字节相同。V6 绑定记录的等待了结 ⇔ 有过一条权威终态的有效观测，或从没有过有效观测而被 `withdrawn`；一个 `ref` 有过权威终态的有效观测之后，任何更长的前缀、任何 `now` 下它都不在清单里；除了那一种 `withdrawn`，统筹方的事件改变不了它的开合。
   - V7 没有新事件、只有 `now` 变大，按类别：`process`——`waiting`、`dead`、`done`、`failed` 不变；`running` 可以变成 `slow`、`quiet`、`unknown`，`slow` 可以变成 `quiet`、`unknown`，`quiet` 只能变成 `unknown`，`unknown` 不再变。`none`——只有 `running → slow`，别的不变。`record`——`done`、`failed` 不变；`locator` 里没有名字的 `waiting` 不变；其余的 `waiting`、`running`、`slow` 在确认过期（最近一轮的 `ended_at` 距 `now` 超过 180 秒）时变成 `unknown`，之前 `running` 可以先变成 `slow`；`unknown` 不再变。Owner 事项——`declared` 的不变；绑定记录的，了结的不变，其余的在确认过期时成为清单里的 `can_act: unknown`（包括原先落在第 5 行、不在清单里的）。
   - V8 一件事的 `works[]` 条目只取决于它自己的日志和观测日志：增删改别的日志，这一条逐字节不变，变的只有 `owner_all` 和 `ball`。V9 一份清单：每条 `declared` 的没了结的等待恰好出一项；每个 `ref` 至多出一项；`fold` 输出的键里没有 `needs_you`、`owner_now`、`owner_items`、`owner_next`、`needs_owner`，也没有别的数他的事项的字段。V10 代码取自固定清单：`state`、`label`、`ended_how`、`reason`、`can_act`、`ball.holder`、`ball.why` 的值恰好是清单里的词；改任何引语，这些值逐字节不变。V11 `ball`：`agents` ⇔ `logs_unread` 为 0 且有一件没关闭的工作判给 `agents`；`nobody` ⇔ `logs_unread` 为 0 且没有没关闭的工作；`owner` ⇒ 清单里有 `can_act: yes`，且没有一件没关闭的工作判给 `agents`、`unknown`、`coordinator`。V12 关闭：一件事算关闭 ⇔ 有一条有效的 `work_closed`；关闭的工作里没有开着的步骤，也没有没了结的等待，之后的事件也不会让它再有。
2. **每个字段的效果，各有一条有名字的测试**。原来对样本日志做删改、把差异归类的测试删了：它的规则和合法的事件序列互相矛盾（复核 73）。换成三部分：
   - (a) **只管展示的字段**：`work_opened` 的 `title`、`goal`、`work_ref`；`step_declared` 的 `name`、`who`、`round`；`step_started` 的 `command`；`step_seen` 的 `text`（进 `note`）；`step_finished` 的 `quote`；`step_superseded` 的 `text`（进 `superseded_text`）；`record_seen` 的 `reason_quote`；`owner_wait_opened` 的 `title`、`advice`、`reply`、`reply_needed`、`reply_words`、`commands`、`blocks_text`、`blocks_nothing`、`after_text`、`not_before_text`、`after`；`owner_wait_seen` 的 `number`；`work_closed` 的 `claim`（进 `closed_claim`）；`note` 的 `text`（进 `feed` 的那一行）。对每一个：换成另一个合法的值，文档里只有对应的那一个输出字段不同，别处逐字节相同。`step_started` 的 `pid` 不进文档：改它，文档逐字节不变。
   - (b) **其余字段**，每个一条测试，名字里带字段名，断言下表写的效果：

   | 字段 | 测试断言的效果（规则在第 3、4 节） |
   |---|---|
   | `step_declared` 的 `kind`、`watch` | 不对应 → 无效；`watch` 决定这一步按哪张表取状态 |
   | `step_declared` 的 `waiting_on` | `process` 类带它 → 无效；记录类没找到记录时是 `waiting` 还是 `unknown`；等待的 `holds_up`；`ball` 的 `next_not_sent` |
   | `step_declared` 的 `after`、`locator.name`、`usual_s` | `after` 只影响 `ball`；没有 `name` → `waiting`、不读；`usual_s` 只影响 `slow`、`overdue`、预计结束、`effect_s` |
   | `step_superseded` 的 `by_step` | 有 → `superseded_by`，状态不变；没有 → 撤回，开始过的无效 |
   | `step_seen` 的 `alive`、`output_bytes`、`sampled_at` | `false` → `dead`；420 秒没变大 → `quiet`；`sampled_at` 定 180 秒的期限和 `gap` |
   | `step_finished` 的 `exit`、`reported` | `done` / `failed`、`ended_how`、`reason` 代码；在 `alive: false` 之后仍然生效并带 `was_seen_dead` |
   | `record_seen` 的 `found`、`uid`、`started_at`、`ended_at`、`condition` | 记录类那张表的每一行；`uid` 不同 → 无效 |
   | `owner_wait_opened` 的 `ref`、`can_act`、`deadline`、`no_deadline`、`where`；`owner_wait_ready`；`owner_wait_closed` 的 `how` | `source`；同一个 `ref` 出一项；`declared` 的 `yes` / `not_yet`；清单的次序；`where` 不在三选一里 → 无效；合上 |
   | `owner_wait_seen` 的 `ref_state`、`expires_at`、`sampled_at` | 绑定等待那张表的每一行；最晚时间；几份日志里取 `sampled_at` 最晚的一条，同时而不同 → `unknown` |
   | `observer_round` 的 `ended_at`、`confirmed`、`failed` | 确认与否；`unknown` 的 `reason` 代码；超过 180 秒 → 不算确认 |
   | `work_closed`（整条） | 有开着的步骤或没了结的等待 → 无效（`closed_with_open_items`）；有效时这件事不再参与 `ball` |
   | 包络：`at`、`by`、`run_id`、`step_id`、`wait_id` | `at` 定 `started`、`ended`、`ball.since` 和时钟回拨；`by` 与入口不相配、id 指向不存在的东西、`run_id` 不符 → 无效 |

   - (c) **无效输入**：对每种事件，逐个删掉必填字段、把字段换成别的类型、换成闭合取值之外的值、加一个多余字段、把 `type` 换成不认识的 → 这条事件进 `defects`，文档等于从日志里删掉这条事件后折叠出的文档（就是 V5；状态因此可以变，例如一步回到 `waiting`）。
3. **回归**：
   - 事故 1，三条：(a) `declare --kind release --watch process` 被拒；给 `process` 步骤带 `waiting_on` 被拒；于是「绑定待批等待的发布步骤被 `run` 包住」写不出来。(b) 发布步骤（`record`）→ 确认过、找到了运行、没有 `started_at` → `waiting`，没有 `started`；观测到 `started_at` 之后才是 `running`，`started` 等于它。(c) 4000 秒里只有 `owner_wait_seen` 和 `observer_round` → 发布步骤一直 `waiting`；对它写 `step_started`、`step_seen` 被拒。另：`kind: other` 的进程步骤在文档里带 `watch`、`kind`、`command`。
   - 事故 2，三条：(a) 第 1 轮结束 → 第 2 轮声明、开始、心跳 → 第 1 轮那一步逐字节不变；拿第 2 轮的 `run_id` 给第 1 轮写心跳被拒。(b) 旧步骤开始 → 新步骤声明并开始，不带 `--replaces`，旧包装器继续心跳 → 两步都是 `running`。(c) 同上但带 `--replaces` → 旧的仍是 `running`，带 `superseded_by`；旧包装器被杀后旧的成为 `dead`，新的不受影响。端到端：两轮用同一条命令行跑。
   - `dead` 之后的结束：`step_started → step_seen(alive: false) → step_finished(exit 0)` → 三个前缀依次是 `running`、`dead`、`done`（`Exited 0`，`was_seen_dead: true`）；之后再来的 `step_seen` 无效。
   - 关闭，复核 73 的三条序列：(a) `open → owner-open（审批，待批）→ close`：`rec.py close` 被拒；手工拼的 `work_closed` 进 `defects`（`closed_with_open_items`），这件事仍没关闭，清单里有这一项，确认过时 `ball` 是 `owner`，不是 `nobody`。(b) `record` 步骤在跑时关闭 → 同样无效，`ball` 是 `agents`。(c) `none` 步骤报了开始、没报结束时关闭 → 同样无效，`ball` 是 `agents`。另三条：审批 `approved`（还在走）时关闭无效；只剩 `dead` 的步骤时关闭有效，之后补来的 `step_finished` 把它改成 `done` 或 `failed`，工作仍是关闭的；关闭之后的 `step_declared`、`owner_wait_opened` 无效。
   - 事故 3：绑定审批的等待 → 假平台把单子依次改成平台的八种状态 → 每一轮 `observe` 之后这一项的有无和 `can_act` 逐行对上第 4 节的表；全程没有调用统筹方的命令；`rec.py owner-close` 对它被拒。`approved` 之后变成平台的 `unknown` → 这一项回到清单。`executed` 之后观测方不再读它；此后伪造一轮把它列进 `failed` → 这一项不回到清单。假平台回 500、403、404、超时各一次 → 当轮进 `failed`，这一项是 `can_act: unknown`，带上一次读到的状态和时间。没有令牌 → 全部 `unknown`。观测停 181 秒 → `unknown`。变化的事件追加失败（日志的锁被占）→ 这个键进 `failed`（`append_failed`），这一项是 `unknown`，不是旧状态。
   - 事故 4：31 件事；一件事 21 个活跃步骤；100 件事、一件事 200 步、每个文字字段顶到上限（含四字节字符、引号、反斜杠、`<>&`、形如 `token=x` 的字）；31 条和多到字节放不下的 Owner 事项 → `publish_view` 的输出不超过 204,800 字节、满足每一条数组上限、没有 null；每个被截的类别都有计数；留下的条数加 `owner_all_cut` 等于折叠出的清单长度；第 ⑤ 级的每件事恰好是摘要那几个字段。假服务端回 413 → 本机文档的推送结果一栏是失败和原因。
   - Owner 的三条：三件事各有一条绑定的和一条 `declared` 的等待，两件事绑定同一张单 → `owner_all` 里那张单只有一项、带两件事的 `works[]`，绑定的在前；两份日志对同一张单一份见到 `approved`、一份还是 `pending` → 取 `sampled_at` 晚的；同时而不同 → `unknown`。两条标题相同的 `declared` 等待 → 两项。缺 `advice`、`where`、`reply` 的 `declared` 事项，文档里就没有这三个字段。`ball` 逐件判定表的每一行和合成的每一种结果各一条，含 `since`；复核 73 的五个例子各一条（都结束了而没关闭 → `coordinator`；一件等他、另一件等统筹方 → `coordinator`；只有 `declared` 的等待 → `owner` 带 `basis: declared`；观测方停了 → `unknown`；快照过期 → 页面覆盖成 Unknown）。201 份日志 → `fold_complete` 为假，`ball` 是 `unknown`。
   - 时钟与观测方：睡眠（两条心跳隔 3 小时）→ 期间 `unknown`，恢复后 `running`、带 `gap`、没有 `slow`，这次的用时不进下一次声明的 `usual_s`；`at` 回拨 60 秒 → 区间内 `unknown`；两个 `observe` 同时起 → 只有一个写事件，另一个退出，日志里没有交错的样本；观测方不在 → 记录类步骤和绑定的事项在 181 秒后是 `unknown`，进程类步骤仍由包装器的心跳决定；读的一方的时钟比日志早 → `unknown`。
4. **发布的上限，过真实的校验**。每一级缩减各一条。平台仓库 `api/internal/agentprogress/` 加一条测试：读环境变量指的目录，把每份夹具走一遍真实的 `HandlePut`（校验、脱敏、重新编码、外壳大小都在这条路上），要求 202，并回读核对 `owner_all` 的条数和各步的 `state` 没有被服务端改掉。记录器这边的测试生成上一条里的夹具，在同级的 platform 检出里跑它；同一条测试把记录器里的上限常数和 `schema.go`、`document.go` 源码里的常数逐个比对。没有 platform 检出时这条测试报「没有跑」，验收不算通过。它不在 infra 的 CI 里：平台改了上限，要到下一次在工作区里跑验收才发现，这是已知的缺口。本文写的时候这条测试还不存在，上面的限制表是读源码得来的，不是跑出来的结果。
5. **发事件的一侧，端到端**（教训第 73 行）：`rec.py run` 包住五种假命令（退出 0、退出 9、被 TERM、长时间不出声、包装器自己被 `kill -9`）→ 真实日志 → 折叠出 `done`（`Exited 0`）/ `failed` / `failed` / `quiet` / `dead`。`observe` 对着会核对请求的假平台和假 `kubectl`：只许出现读请求（HTTP 只有 GET，`kubectl` 只有 `get`），请求头里的令牌只发给配置的那个主机，出现别的即失败。静态检查：源码里没有 `os.kill`、`killpg`、`send_signal`、`terminate`、`.kill(`、`pgrep`，没有读 `pid` 字段的代码，没有 `mcp-tokens`。
6. **链和残尾**：改中间一行不重封 → `log_invalid_at`，没结束的步骤是 `unknown`，追加被拒；残尾修复沿用拣过来的测试；两个进程同时追加 → 两条都在，`seq` 连续；日志写到上限 → 追加被拒，`log_full`。
7. **防线**：第 6 节的文本扫描和依赖测试各有一条会让它失败的反例；`scripts/release/` 现有的离线测试在三种环境下各跑一遍（事件根目录和看板文档原样、不存在、换成伪造的「全部 `Exited 0`」），输出逐字节相同。

## 8. 分片

一片是一次实现、统筹方验收、独立复核直到通过；统筹方给的实测数是约 3 小时一片，本文没有另行核对。每片开工前写下停线条件：同一类必须改的问题在第二轮复核里又出现，就停下改形状，不加第三轮（教训第 70、72 行）。

| 片 | 交付 | 验收 | 不含 |
|---|---|---|---|
| 1 记录、折叠、发布形状、防线 | `agent-config/scripts/recorder/`：事件文件、锁、残尾修复（拣自 `w31/w66-lane-v2`）；记账入口（`open`、`close`、`declare`、`withdraw`、`start`、`finish`、`note`，和 `declared` 事项的 `owner-open` / `owner-ready` / `owner-close`）和写入校验；`fold`；`publish_view` 和上限常数；第 6 节的防线（`RATCHETS.md`、文本扫描、平台的依赖测试）；平台仓库里走 `HandlePut` 的那条夹具测试。纯本机：不起子进程，不访问网络 | 第 7 节第 1、2、3（全部用合成日志）、4、6、7 条 | **任何真实读取**（绑定记录的 `owner-open` 和它对平台的那一次读、`observe` 读平台和集群）；包装器 `run` 和任何命令的改接；看板的改动；**启用向 Console 发布新形状**（`publish_view` 在这一片只对夹具跑） |
| 2 一种本机命令贯通 | `run`、`observe`（只有锁探测和 `observer_round`）、`wait`；只接 `verify-branch.sh` 这一种命令；`board2.py` 对有 `step_id` 的步骤读折叠，标 `source`；`index.html` 加 180 秒的过期覆盖；第 5 节「Console 读哪一份」的三个前提成立之后才切换推送 | 第 7 节第 5 条的进程部分；第 3 条里事故 2、`dead` 之后的结束、时钟的端到端部分；一次真实的验收运行，折叠出的和实际发生的逐项对一遍 | 读真实记录；Owner 事项；删旧代码 |
| 3 真实记录 | 三个只读适配：审批、提问（reporter 令牌）、流水线运行（集群只读身份）；绑定记录的 `owner-open`；记录类步骤的观测；`owner_all` 和 `ball` 改由折叠给，`tasks.json` 里的 `needs_you` 和 Owner 步骤迁走。开工先做三次真实的只读读取（一张审批、一个提问、一次运行），核对凭证、字段名、`ci` 运行怎么按提交号找到；有一样对不上，先改本文 | 第 7 节第 3 条的事故 1(b)(c)、关闭、事故 3、Owner 的三条的端到端部分；第 5 条的观测部分 | Console 的改动；删旧代码 |
| 4 其余命令改接，删旧代码 | 实现、复核两条命令改接（只换命令行，不改记录器）；第 5 节列的补丁和函数删掉，`tasks.json` 只留目标和估算 | 观察一个晚上的实际使用：第 1 节的五类错误零次；删掉 `status.json` 重算，内容相同；PROD 的 Progress 页一直显示已同步 | Console 读新字段（`OWNER-SURFACE` 的 P6，在 platform 仓库，带发版单） |

`WORK.md` 里 W-66 的估算写的是「记录和状态那一半约 2 片」。这里是 4 片：多出来的是把发事件的一侧、读真实记录各自单独成片（复核 68 和教训第 73 行）。四片之间没有要 Owner 做的事。片 1 在平台仓库加两个只有测试的文件（夹具测试、依赖测试），不带发版。

## 9. 第二半（判通过与放行）要满足的约束

本文不设计它。以后任何一份设计至少要满足五条：① 证据不由被检查的一方保管——裁决读的东西（提交内容、验收输出、复核报告）要么由裁决方自己重新取得，要么存在被检查方写不到的地方（另一个用户、沙箱、平台），同一个 Unix 用户名下的文件不算。② 没有自己写的豁免清单——哪些字段可以不查、哪些变化仍算通过，由设计文档给出并逐项过复核，实现者和被检查方都不能加。③ 测试断言用户实际走的出口，即放行时真正被调用的那条命令或接口；放行时重算，不读已经盖上的判词（复核 65）。④ 记录、裁决、放行不在同一个程序里（教训第 77 行）；能问权威的就问，不重算（教训第 69 行）；本文的事件对它只是线索，不是证据。⑤ 它要有自己的设计，先复核设计再实现（教训第 53、62 行），开工前写下停线条件。

## 10. Owner 要定的事

只有一件：**没有记录可对的 Owner 事项怎么处理**。怎么回应是他的工作方式，所以留给他定；其余的选择都是实现上的，按 ADR §12.2 第 15 条由统筹方定并留痕。本设计在两种选法下都能用；他没定之前按 A，对他来说什么都不变。

选项 A：允许 `declared` 的事项存在，页面上标明 `Declared by coordinator, not a record`，由统筹线程合上；他照旧可以在线程里回一句。选项 B：能变成记录的就变成记录，他在 Console 或手机上办，页面自己变。**推荐：B 只用于提问和反馈，其余按 A**。原来「在线程里回一句」的问题和反馈，在提问入口可用之后（`OWNER-SURFACE` C1：Agent 侧要新线程才有）改成提问入口的一个问题。**PROD 发布的批准不走这条路**：它仍是审批单；提问的回答不增加任何授权（工作区规则，W-65），把「线程里批一句」改成一个问题等于绕开审批。没有权威记录可对的事——换凭证、在他自己的终端里贴一条命令——保留为 A，明确标成 Agent 声明的。

## 11. 两次复核逐条

**复核 68**（16 条：8 条必须改、8 条次要）。复核 73 对这 16 条的结论是 8 条已解决、7 条部分解决、1 条没解决；没解决完的都落进下一张表。

| # | 复核 68 说的 | 在哪解决 |
|---|---|---|
| 1 | P1 事故 1 仍可重现 | 第 3 节 `kind` 与 `watch` 的对应；第 4 节记录类的表。不保证有人把监视脚本包成 `other` |
| 2 | P2 重开时旧步骤的去向 | 第 3、4 节：取代是显式事件，只是标记；不保证上一轮已结束 |
| 3 | P1 锁探测误伤记录类 | 第 3 节：`step_seen` 只对 `process`；记录类用 `record_seen` |
| 4 | P1 Unknown 与停更 | 第 4 节：`unknown` 状态、读的一方查快照；第 5 节每一级留着的字段 |
| 5 | P2 时钟与两个观测方 | 第 3 节「时钟与观测方」 |
| 6 | P1 真实记录绑定 | 第 3 节 `locator` 只认确切的名字和 `uid`；第 4 节审批八种状态的表 |
| 7 | P2 事故 3 与凭证 | 第 5 节「读取凭证」；第 4 节没被确认过就是 `unknown` |
| 8 | P1 平台上限没列全 | 第 5 节的限制表；第 7 节第 4 条走真实的 `HandlePut`（测试还没有，表是读源码得来的） |
| 9 | P1 缩减时有类别没计数 | 第 5 节：八种状态的计数、保留次序、总量、`owner_all` 的截断规则 |
| 10 | P1 `done`、`landed` 像判词 | 第 2、4 节三种写法和 `closed_claim`；Console 的字改完之前不启用新形状（第 5 节） |
| 11 | P2 防线的保证写反了 | 第 6 节：受保护的入口、挡不住什么；第 7 节第 7 条 |
| 12 | P1 V8 与共享中位数矛盾 | 第 4 节估算写进事件；第 7 节 V7 按类别重写 |
| 13 | P2 豁免要逐项 | 第 7 节第 2 条改成每个字段一条测试 |
| 14 | P2 伪造与洪泛 | 第 6 节声明与权威分开；第 3 节 id 格式和本机上限 |
| 15 | P2 分片 | 第 8 节四片；片 1 的「不含」写明 |
| 16 | P2 Owner 的决定 | 第 10 节：B 只用于提问和反馈 |

**复核 73**（13 条：3 条必须改、9 条次要、1 条提示），按报告的顺序：

| # | 复核 73 说的 | 在哪解决，怎么解决；不保证什么 |
|---|---|---|
| 1 | P1 有事还开着，工作却能关闭，`ball` 显示绿色 | 第 3 节 `work_closed` 的无效情形（写入时拒绝，折叠时当作不存在）；第 4 节 `ball` 逐件判定；V12；三条序列进第 7 节第 3 条。`dead` 的步骤不算开着，不挡关闭 |
| 2 | P1 `dead → done` 违反 V3 | 第 3 节 `step_finished` 在 `alive: false` 之后仍有效；第 4 节只有结束事件定下的状态不变；V3 同样的说法 |
| 3 | P1 删改测试的表和 V7 自相矛盾 | 第 7 节第 2 条：删了归类测试，换成展示字段、每字段一条、无效输入三部分；无效事件一律当作不存在（第 3 节）；V7 按 `process`、`none`、`record`、Owner 事项分开写 |
| 4 | P2 同一个 `ref` 被几件事绑定 | 第 4 节 `owner_all`：有过权威终态的不出项，否则取 `sampled_at` 最晚的有效观测，同时而不同是 `unknown`；`declared` 按 `wait_id`，从不合并 |
| 5 | P2 逐对象的新鲜度 | 第 3 节「逐对象的确认」：`observer_round` 的 `confirmed` 和 `failed`；追加失败进 `failed` |
| 6 | P2 执行中与终态分开 | 第 4 节绑定等待的表第 1、5 行：`approved`、`running` 继续读；权威终态不重开 |
| 7 | P2 Console 的 `age_seconds` 不是距生成时间 | 第 4 节「读的一方」：加上 `generation_lag_seconds`，同一个 180 秒；第 5 节三个前提成立才启用新形状 |
| 8 | P2 `owner_all_cut` 也是计数 | 第 5 节：一条截断规则，那个数是留下的条数加 `owner_all_cut`，只显示一次 |
| 9 | P2 超过 200 份日志 | 第 3 节 `logs_unread`；第 4 节「折叠不完整」：`ball` 是 `unknown`，那个数写成「至少 n」 |
| 10 | P2 缩减第 ⑤ 级的契约 | 第 5 节「字节」那一条里的「摘要」和「每一级都留着的」 |
| 11 | P2 `declared` 的标签和办理字段 | 第 3、4 节 `commands`、`reply_words`；标签始终可见；链接只按校验过的 `ref`（第 6 节）。不保证 `declared` 的 `can_act: yes` 是真的 |
| 12 | P2 `reason` 原样输出与固定词表冲突 | 第 4 节 `reason` 的固定清单；记录的原话进 `reason_quote`；V10 |
| 13 | P3 片 1 的边界 | 第 8 节片 1 的「不含」：真实读取、命令改接、启用发布都不在 |
| — | 第 1 条的附注：`other` 包监视脚本 | 第 4 节：`process` 步骤总是显示「进程 · 类别 · 命令行」 |
