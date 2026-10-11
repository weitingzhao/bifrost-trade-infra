# W-66 第一半：记录事件，由事件生成状态（不裁决，不放行）

状态：**输入处理一节按条件停线**（2026-10-11 17:58 CDT）。第 12 节和它改到的第 2、3、4、5、7、8 节是第三稿，三次复核（92、94、97），必须改的 3 → 3 → 1；复核 97 剩的一处见 `reviews/codex-2026-10-11-review97-w66-recorder-input-design-r3.md`（被取代而没有有效开始的步骤，它的活运行没有计入 `unrecorded_runs`，已关闭的工作上会得到 `nobody`）。这几节**不可照着实现**；重开要 Owner 一句话。2026-10-11 14:32 通过四次复核（68、73、76、77）的那一版在提交 `20077b3`（`git show 20077b3:agent-config/work/multi-agent/DESIGN-lane-recorder-2026-10-11.md`）。
输入：`WORK.md` 的 W-66；`DESIGN-lane-v2-2026-10-11.md`（已停的设计）；复核 35、38、43、62、65、68、73、76；`LESSONS-from-practice.md` 第 18、52、55、70、72、73、76、77、80 行；`OWNER-SURFACE-2026-10-11.md` 的 A5、A7、A8、B2、B5、D1 和 P6；本机看板 `~/agent-work/status/` 的 `board2.py`、`tasks.json`、`index.html`；平台源码 `bifrost-platform/api/internal/` 下的 `agentprogress/`、`approvals/`、`questions/`、`actions/objectname.go`、`actuation/auth.go`（只读了源码，没有调用任何接口，没有读任何凭证）；分支 `w31/w66-lane-v2`（`0a54279`，不合并）；这一稿另读了片 1 的实现（分支 `w31/w66-recorder` 的 `agent-config/scripts/recorder/`，只读源码、跑了不写盘的探测）、实现报告、复核 81、88、92、94 的报告、platform main 的 `AgentWorkBoard.tsx` 和本机 `index.html`（核对空清单怎么显示）、`DESIGN-console-progress-v2-2026-10-11.md` 第 3 节。

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

- **做**：一份只追加的事件日志；一个把事件算成看板文档的纯函数 `fold`；一个把文档压进平台上限的纯函数 `publish_view`；对外只有包着这两步的两个全函数入口 `fold_total`、`publish_total`（第 12 节）。消费方只有两个：本机看板，以及以后 Console 的 Progress 页（P6）。
- **从已停的设计留下的**（`DESIGN-lane-v2-2026-10-11.md`，这里不重述）：第 2 节的事件行格式和哈希链、残尾修复、不等待的 `flock`；状态由一个函数算出，没有可改写的状态文件；子进程用参数数组启动，不经 shell；源码里没有发信号的调用；每种事件的字段是闭合集合。分支上的 `events.py`、`fsutil.py`、`locks.py`、`repair.py` 连同测试可以拣过来（只细读了 `events.py`，另三个按文件名和复核 38 推断）。分支不合并。
- **丢掉的**：判定函数和判词、`passed` 和 `pass-set`、轮次预算、`resolve` / `abandon` / `confirm-ended`、intent 和 manifest、检出和 bundle、配置固定、`run.lock`、六关和转换表。轮次只剩一个显示用的数字。
- **复核之后删掉的**。第二稿：记录类步骤的开始和结束事件；绑定记录的等待的关闭事件；「名字前缀加创建时间」找运行；折叠里跨日志取中位数；监视脚本作为步骤；合上的 Owner 事项留 24 小时；`rec.py wait` 的退出码保证。第三稿：对样本日志做删改、把差异归成四种影响的测试（换成每个字段一条有名字的测试，第 7 节第 2 条）；`dead` 是终态的说法；观测事件里「读失败」的那一种写法和各项计数（失败和确认都只记在每轮的 `observer_round` 里）；`owner-open` 自己读到的状态（`first_seen`）；按审批 id 和尝试次数推算运行名的定位办法（只认给定的名字）；多匹配这种情形（按确切名字读，不会有）。第四稿没有删东西，只改复核 76 的五处。

| 不做 | 说明 |
|---|---|
| 不出判词 | 状态里没有「通过」。步骤结束后发布的字是 `Exited 0`（进程退出码为 0）、`Reported finished by coordinator`（统筹方报完成）或 `Record: Succeeded`（记录自己说成功），三种分开写。机器值 `done` 只因为 Console 现在按它上色才保留，它一定带 `ended_how`。验收和复核说了什么，只原样引用一行。怎么防别人把它当判词、防不住什么，见第 6 节 |
| 不出「通过集合」 | 不输出任何可以拿去合并或发布的提交号集合。`work_closed` 的 `claim: landed` 是统筹方的声明，文档里写成 `Coordinator declared: landed`；这一半不核对提交在不在主线 |
| 不管进程 | 不发信号、不结束、不重跑、不接续、不限制输出。包装器只做三件事：起进程、等它结束、记退出码。记录器只旁观，不当闸门：记不成账（日志无效、写满、取不到锁，或那次追加只写成了声明、没写成开始）时照样起命令，退出码原样传回，stderr 写明没有记上；看板这时怎么说，只在表 A 的 `step_started` 一行。参数本身不合规（例如 `kind` 与 `watch` 不对应）是用法错误，什么都不起 |
| 不合并、不推送、不发布 | 没有任何 git 写操作 |
| 不写集群、不写平台 | 对真实记录只读：读审批、提问、流水线运行。向外的写只有现有的那一条「把看板文档推给平台」 |
| 不拦任何事 | 被拒的只有不合规的记账；没有哪条命令因为状态不对而不能运行。轮次预算照旧由统筹方按 ADR §12.2 第 15 条执行 |

## 3. 事件

```
~/agent-work/events/                              # 根目录可用 --root 改
  <work_id>/events.jsonl  lock                    # 一件事一份日志：只追加 · 一把 flock
  <work_id>/events.torn-<repair_id>               # 修复时挪出来的残尾
  <work_id>/runs/<step_id>-<run_id>/stdout stderr alive.lock  # 包装器在记账之前独占新建，从不复用；目录怎么对上 step_id 归片 2 的适配层，折叠不看目录名
  _observer/<UTC 日期>-<四位序号>.jsonl  lock      # 观测日志：每轮一条；一个文件到 4 MiB 换下一个序号，每个文件自己起链；lock 整轮持有
```

**写入**：只有 `rec.py` 的命令入口追加事件。一次追加：不等待地取这份日志的 `lock`（被占就重试 2 秒，再不行报错）→ 修复残尾 → 校验日志前缀 → 对着前缀折叠出的状态校验这条事件 → 封好的这一行先过一遍读入（12.1），得回同一条事件才往下 → 写一行并 fsync → 放锁。锁只在一次追加期间持有。`seq`、`prev_sha256`、`at`（UTC，追加时的系统时钟）、`v`（恒为 2；写着别的值的旧日志整份不读，见 12.1「旧日志」）由记录器填。`step_id`、`run_id`、`wait_id`、`round_id` 是记录器生成的随机 8 位十六进制，命令行不接受调用方给的值。

**哈希链证明什么，不证明什么**：每行带上一行的摘要。文件中间被改、被删、被调换顺序而没有重新封好，读的一方看得出来，从那一行起不再采信。它不是签名：同一个 Unix 用户可以把整份日志重写再封好，也可以从末尾整行截掉几条，这两种都查不出来。链也不说明内容是真的。它防的是失误和半写，不防有意的改写。

**字段通则**：每条事件都有 `type`、`v`、`seq`、`prev_sha256`、`at`、`by`；字段是闭合集合。`by` 是入口自己填的标签（`coordinator` / `wrapper` / `observer`），说的是从哪个入口进来，不是身份。观测类事件另有 `sampled_at`。事件里没有链接字段。**上限**：名字 80 个码点，其余文字 200 个码点，`commands` 至多 5 条、每条 400 个码点；哪些字符、哪些数字收，null 怎么算，格式怎么匹配，都在 12.2 的第 8–10 条；一份日志至多 20,000 条、16 MiB；一件事至多 200 步、20 条没了结的等待。超了的写入被拒并说明原因；日志满了，这件事带 `log_full`。折叠至多读 200 份日志：留下最近在动的那些是调用方的事——超过时它按日志文件的修改时间取最近的 200 份，其余的份数作为 `logs_unread` 交给折叠；入口自己读哪些、按什么次序、没读的怎么计，只在表 C。子进程的输出文件多大，这一半不限制（限制它就是管进程）；超过 1 GiB 时那一步带 `output_large`。`kind` 与 `watch` 的对应是闭合的：`implement`、`verify`、`review`、`merge`、`other` 只能是 `process` 或 `none`；`release` 只能是 `record`；`ci` 是 `record` 或 `none`。**监视脚本不是步骤**：等审批、等运行出现、持有发布窗口的脚本不声明成步骤，它活没活不上看板；发布这一步的真相只有那次运行的记录。

**四个词，第 3、4、5、7 节都按这里的意思用**：

- **结束事件**：`process`、`none` 类是一条有效的 `step_finished`；`record` 类是一条有效的、`condition` 为 `True` 或 `False` 的 `record_seen`。有结束事件的步骤是**结束了的**，状态只能是 `done` 或 `failed`。
- **开着的步骤**：状态是 `waiting`、`running`、`slow`、`quiet`、`unknown` 的步骤。`dead` 既不是结束了的，也不是开着的：它只说明最近一次探测时包装器不在了。它不挡关闭，否则包装器一死，这件事就再也关不掉。
- **没了结的等待**（按这份日志自己的事件判断）：`declared` 的（`ref.kind` 是 `none`）还没有 `owner_wait_closed`；绑定记录的还没有观测到权威终态（审批 `executed` / `failed` / `rejected` / `expired`，提问 `answered` / `withdrawn` / `expired`），也没有被撤回。
- **确认过**：一个要读真实记录的对象（一条绑定记录的等待，或一个有名字的记录类步骤），在最近完成的那一轮观测里被列进了 `confirmed`，而且那一轮的 `ended_at` 距 `now` 不超过 180 秒、也不在 `now` 之后 2 秒以上。

**表 A：每种事件的字段、入口、什么时候无效、无效时发生什么。** 一条事件或一行不能用时的后果只在这张表的最后一栏和末三行，别处只引用它。

| 事件 | 字段（可选的另列） | 从哪个入口写 | 无效的情形（字段不合规之外） | 无效时：这一行不存在，进 `defects`；之后的结果 |
|---|---|---|---|---|
| `work_opened` | `work_id`、`title`；可选 `goal`、`work_ref`（台账编号） | 统筹方 `rec.py open` | 不是日志的第一条；`work_id` 与目录名不同 | 这件事没有 `title`、`goal`（条目的 `work_id` 取目录名）；别的事件照常作数，它是一件没关闭的工作 |
| `work_closed` | `claim`（`landed` / `stopped` / `dropped`，都是声明） | 统筹方 `rec.py close` | 已关闭；这件事还有开着的步骤或没了结的等待（原因代码 `closed_with_open_items`） | 这件事仍算没关闭，照旧参与 `ball` 和 `owner_all` |
| `step_declared` | `step_id`、`name`、`kind`、`who`、`watch`；`record` 类必填 `locator{cluster, namespace}`，其中 `name` 可以先不写；可选 `round`、`after`（`step_id`）、`usual_s` 加 `usual_basis`（`measured` / `declared`，由入口在声明时算好）；`record`、`none` 类可选 `waiting_on`（`wait_id` 列表）；可选 `replaces`（这份日志里被它取代的那一步的 `step_id`）加 `replaces_text` | 统筹方 `rec.py declare`；包装器（`rec.py run` 把声明和开始写在同一次追加里；只写成第一行时怎么算，见 `step_started` 一行的最后一栏） | `step_id` 已存在；`kind` 与 `watch` 不对应；`process` 类带 `waiting_on`；`record` 类没有 `locator`；指向不存在的 id；`replaces` 指的步骤不存在、已被取代或已撤回 | 这一步不存在；指向它的事件和引用（开始、心跳、结束、观测、`after`、`replaces`）各自因为指向不存在的 id 而无效；它自己带的 `replaces` 不生效，旧步骤不变 |
| `step_superseded` | `step_id`；可选 `text`。**只表示撤回**。取代不再是另一条事件，而是新声明上的 `replaces`（`declare` / `run` 带 `--replaces <旧 step_id>`）：一条事件，没有写了一半的批次；`replaces` 只能指向已经声明的步骤，所以指不到自己，也成不了环（复核 88） | 统筹方 `rec.py withdraw` | 这一步开始过（`process`、`none`：有 `step_started`；`record`：有过找到记录的观测）；已被取代或已撤回 | 那一步照旧在列表里，状态不变 |
| `step_started` | `step_id`、`run_id`；`process` 类必填 `command`（命令行的摘要）；可选 `pid`（只给人看） | `process`：只有包装器，在创建子进程之前写；没写成也照样创建（第 5 节 `run`）。`none`：统筹方 `rec.py start` | 没有声明；已开始过；已被取代或撤回；`record` 类；`by` 与 `watch` 不相配；`none` 类而 `waiting_on` 里还有没了结的等待 | 这条开始不存在。**一步没有有效的 `step_started` 时**（这条事件无效，或根本没写上——`run` 只写成了声明——都是这一格）：声明的 `by` 是 `coordinator` → `waiting`；是 `wrapper` → `unknown`（`start_not_recorded`），因为日志分不出命令起没起（包装器在两行之间被杀，没起；写到一半磁盘满，起了）。后一种是开着的步骤，挡着关闭；它带最近一轮 `unrecorded[]` 给的 `last_seen{alive: true, at}`（那一轮的期限同样是 180 秒，没有就不带）；它只能被撤回或取代，不会变成别的状态 |
| `step_seen` | `step_id`、`run_id`、`sampled_at`、`alive`；可选 `output_bytes`、`text` | 只对 `process` 类。包装器每 60 秒一条（它正等着子进程，`alive: true` 是第一手的）；观测入口探到 `alive.lock` 空着，写一条 `alive: false` | 不是 `process` 类；没有开始；`run_id` 不符；这一步结束了；已有 `alive: false`；`output_bytes` 变小；`sampled_at` 不合规 | 这条观测不存在，状态不变。一条有效的 `alive: false` 把一步改成 `dead`、一条有效的 `step_finished` 把它结束，都只对有有效 `step_started` 的运行成立：没有有效开始的步骤上，这两种事件一律无效（没有开始） |
| `step_finished` | `step_id`、`run_id`；`process`：`exit{code, signal}` 恰好一个非空；`none`：`reported`（`finished` / `failed`）；可选 `quote`（原样引用的一行） | `process`：只有包装器，值取自 `wait()`。`none`：统筹方 | 没有开始；`run_id` 不符；这一步结束了；`record` 类；`by` 与 `watch` 不相配。**已有 `alive: false` 不使它无效**：包装器自己记下的结束比观测方的探测权威 | 这一步没有结束事件，状态照旧。没有有效开始的 `step_finished` 现在一律无效；要接受它得另定语义和验收（复核 94 裁定 ②） |
| `record_seen` | `step_id`、`sampled_at`、`found`；找到时另有 `uid`，可选 `started_at`、`ended_at`（记录自己的时间）、`condition`（`True` / `False` / `Unknown`）、`reason_quote`（记录自己写的原因） | 只有观测入口，只对 `record` 类：读成功、结果和上一条不同才写 | 不是 `record` 类；这一步结束了；这一步被取代或撤回而此前从没找到过记录；`uid` 与这一步第一次找到时记下的不同；`sampled_at` 不合规 | 这条观测不存在，这一步按它之前的有效观测取状态 |
| `owner_wait_opened` | `wait_id`、`title`、`ref{kind, id}`（`approval` / `question` / `none`）；`none` 的必填 `can_act`（`yes` / `not_yet`），可选 `where`（`thread` / `console` / `terminal`）、`reply` 或 `reply_needed: false`、`reply_words`（线程里要回的原话）、`commands[]`（终端里要贴的命令，纯文字）、`deadline` 或 `no_deadline: true`、`blocks_nothing: true`、`not_before_text`；两种都可选 `advice`、`blocks_text`、`after_text`、`after`（`step_id`）、`replaces`（这份日志里一条没了结的 `declared` 等待的 `wait_id`；这条事件有效时那一条同时记成 `withdrawn`，仍是一条事件） | 统筹方 `rec.py owner-open`。绑定记录的：这条命令先读一次那条记录，只为挡住写错的 id——读到 404，或读到的记录的 `work_id` 与这件事的 `work_ref` 不同，就不写；读失败照样写。读到的状态不进事件 | `id` 不合格式（审批 `appr_` 加 16 位十六进制，提问 `q_` 加 16 位）；同一个 `ref` 在这份日志里已有没了结的等待；绑定记录的带 `where`、`reply`、`reply_words`、`commands`、`can_act`、`deadline`（这些来自记录和页面，不由 Agent 写）；`where` 不是 `terminal` 而带 `commands`；`replaces` 指的等待不存在、已了结或不是 `declared` 的 | 这条等待不存在，不出项；指向它的观测、`ready`、`closed`、`waiting_on` 各自无效；它自己带的 `replaces` 不生效，原来那条不变 |
| `owner_wait_seen` | `wait_id`、`sampled_at`、`ref_state`（平台的原词）；可选 `expires_at`、`number` | 只有观测入口，只对绑定记录的等待：读成功、状态和上一条不同才写 | 等待不存在；`ref.kind` 是 `none`；这条等待已了结；`ref_state` 不是平台那几个词；`sampled_at` 不合规 | 这条观测不存在，这一项按它之前的有效观测 |
| `owner_wait_ready`；`owner_wait_closed` | `wait_id`；后者另有 `how`（`done` / `withdrawn`） | 统筹方，只对 `none`：声明这一条现在可以办了；合上它 | 已合上；`ready` 而已是 `yes`；绑定记录的等待（它的开合只由观测决定），唯一的例外是从没有过有效观测的那一条可以 `withdrawn`（写错了 id） | 这条等待不变 |
| `note` | `text`；可选 `step_id` | 任何入口 | `step_id` 不存在 | 没有这行 `feed` |
| `observer_round` | `round_id`、`started_at`、`ended_at`、`confirmed[]`（对象的键）、`failed[]`（`{key, error}`）；可选 `truncated: true`、`unrecorded[]`（`{work_id, step_id, run_id}`：锁还被持有而日志里没有开始事件的运行，算在 400 项之内） | 观测入口，每轮结束时一条，只进观测日志 | 出现在别的日志；`ended_at` 早于 `started_at`；三个列表合计超过 400 项；`error` 不在固定清单里；键不是下文三种格式之一；同一个键出现两次——一个列表里重复，或在 `confirmed`、`failed`、`unrecorded` 之间跨列表出现（`unrecorded` 的一项按 `step:<work_id>/<step_id>` 算键），这一轮自相矛盾；`unrecorded` 的项形状不对 | 进 `observer.defects`（`{file, seq, reason}`），这一轮不存在：不刷新任何对象的确认和 `last_seen`，「最近一轮」仍是它之前那条有效的轮。有效的一轮里 `unrecorded` 的一项这样用：`step_id` 在那份日志里声明过、没有有效开始 → 给那一步 `last_seen`（`step_started` 一行）；`step_id` 没声明过（两行都没写成）→ 计进这件事的 `unrecorded_runs`（表 B 第 5 行）；它的 `run_id` 在那份日志里已有有效开始，或它的 `work_id` 没被读进来 → 这一项不起作用，以日志为准，不算缺陷 |
| 任何一行（读不出来时连类型都不知道） | — | — | 读不出来：过不了 12.2 第 2–6 条 | **断链**，不是「这一行不存在」：这份日志在这一行标 `log_invalid_at`（行号，从 1 起，不从坏行里读 `seq`），`log_invalid_why` 是 12.2 那一条的代码。之前的行照常作数，这一行和之后的都不作数，记录器拒绝再往里追加。结束了的步骤照旧，其余步骤是 `unknown`（`log_invalid`）；有效前缀里已经关闭的工作不变。观测文件同样：标 `observer.log_invalid_at`（文件名和行号），只丢这个文件断点之后的轮，别的文件照常。标记的后果在表 B 第 2、6、10 行 |
| 任何一行 | — | — | 链字段不对：12.2 第 7 条（`seq`、`prev_sha256`、`v`） | 同上，代码是 `bad_chain` 或 `bad_version` |
| 任何一行 | — | — | 读入的小保护捕到了没分类的异常 | 同上，`log_invalid_why: internal`，`internal_errors` 加一（12.4）。不按「这一行不存在」：这时不知道它本来是不是有效事件，当它不存在可能丢掉一条真实的 Owner 事项 |

另有 `tail_repaired`，由残尾修复自己写，形状照已停设计的第 2 节。工作关闭之后，这份日志里只有给 `dead` 步骤补的 `step_finished`、`note` 和 `tail_repaired` 还有效，别的一律无效。一条事件有效不有效，只取决于同一份日志里它之前的事件，不取决于 `now` 和观测日志。**两层校验**：写入时拒绝（什么都不写，非零退出，说明原因）；折叠时再校验一遍，不假定写的一方校验过。「字段不合规」指必填字段缺了、类型不对、取值在闭合集合之外、多出字段、不认识的 `type`（12.2 第 8–10 条）；`defects` 的一项是 `seq` 和原因代码（代码的清单在任务书里列全），有 `defects` 的工作页面标 `Has ignored events`。坏了或满了的日志、卡在 `unknown` 出不来的记录类步骤（记录被清掉了），没有事件能了结：统筹方把那份日志的目录挪出事件根目录，另开一份；挪走是手工动作，不是事件。观测日志按大小轮转（目录结构见上）：哪些文件读、按什么次序接成一列在表 C，坏行和无效的轮在表 A，各个标记的后果在表 B。

**记录类步骤的定位条件**只有一种：`locator{cluster, namespace, name}`，声明时写下，之后不改。声明时还不知道名字的可以先不写 `name`，这一步是 `waiting`；名字出来后用 `declare --replaces` 带名字重新声明（旧声明没开始过，从列表里消失）。记录器不猜名字：审批建出来的运行，名字由平台按审批 id 和尝试次数定（`api/internal/actions/objectname.go`），发布脚本看到运行出现时把名字补上。观测入口按名字 `get`，第一次找到时在 `record_seen` 里记下 `uid`；此后同名而 `uid` 不同的对象不算它，那一轮把它记成 `failed`（`uid_changed`）。`ci` 类按提交号找那次运行的办法没有核对：片 3 开工时核对，找不到唯一的名字，`ci` 步骤就声明成 `none`，如实显示为统筹方报的。

- **采样时间**：`sampled_at` 是探测或读取之前那一刻的系统时钟，`at` 是追加时的。`sampled_at` 晚于 `at`、比 `at` 早 30 秒以上（等锁等久了的样本不写）、或早于同一对象上一条观测的 `sampled_at`，都无效。
- **互斥范围**：`rec.py observe` 整轮持有 `_observer/lock`（不等待，拿不到就退出并说明，不排队），采样和追加都在这把锁里，所以两个观测方不会交错。包装器不是观测方：它只写自己那次运行的第一手事件。
- **逐对象的确认**：一轮里每个对象读一次（同一个 `ref` 被几件事绑定也只读一次）。对象的键是 `approval:<id>`、`question:<id>`、`step:<work_id>/<step_id>`。读成功、并且结果已经在每一份有关的日志里（没变，或变化的那条事件追加成功），这个键进 `confirmed`；读失败、`uid` 变了、或变化的事件没能追加，进 `failed`，`error` 取固定清单：`unreachable`、`forbidden`、`timeout`、`bad_reply`、`not_found`、`uid_changed`、`no_credential`、`append_failed`。一轮的各个列表合计至多 400 项，放不下的不列并带 `truncated`。**没被确认过的对象一律是 `unknown`**：读失败的当轮就是，观测方停了的 180 秒后是，新声明、新开的在下一轮之前（至多 15 秒）也是。变化的事件和这一轮的 `observer_round` 两处追加都失败时，旧状态最多再显示 180 秒，然后因为没有新的一轮而成为 `unknown`。看板循环每 15 秒起一轮。
- **时钟异常**有三种。记号：一份日志的 `max_at` 是它有效事件里最大的 `at`；一个 `process` 步骤的**参照事件**是它最近一条有效观测，还没有观测就是它的 `step_started`，**参照时间**是前者的 `sampled_at` 或后者的 `at`。① 读的一方落后（`reader_clock_behind`，只取决于 `now`）：`now` 比这份日志的 `max_at` 早 2 秒以上；对要读真实记录的对象，是最近一轮的 `ended_at` 在 `now` 之后 2 秒以上。`now` 变大、越过这一点，这个原因就消失，状态按表重新取；这是唯一一种只靠 `now` 变大就能离开 `unknown` 的情形。② 回拨（`clock_backwards`，只取决于事件）：一条有效事件的 `at` 比它之前的 `max_at` 早 2 秒以上，从它起、到第一条 `at` 不早于那个 `max_at` 的事件之前，是不可信区间；参照事件落在区间里的 `process` 步骤是 `unknown`，跨区间的用时不显示。参照事件在区间之前的步骤不受影响，它的时间差最多少算回拨的那一段。③ 缺口（只取决于事件；本机夜里会睡）：同一次运行相邻两个参照时间隔了 180 秒以上，这次运行带 `gap`，此后不再算 `slow` 和 `overdue`；缺口期间它因为没有新鲜观测而是 `unknown`（`no_observation`）。前两种只通过第 4 节两张步骤表的第 5 行和绑定等待表的第 2 行起作用；结束了的步骤、`dead`、还没开始的 `process` / `none` 步骤、没有名字的记录类步骤、`declared` 的和了结的等待都不受时钟异常影响。**哪些运行不是估算的样本**：带 `gap` 的；从它的 `step_started` 到 `step_finished`（按日志里的位置，含两端）之间有任何一条有效事件落在回拨区间里的，不管那条事件属于哪一步；用时不大于 0 的。

## 4. 状态怎么从事件来

`fold(logs, observer_log, now, logs_unread) → 文档`。输入是各件事日志和观测日志的有效事件、调用方给的 `now` 和没读进来的日志份数；字节怎么变成有效事件、入口 `fold_total` 怎么把这一步和折叠一起包住，在第 12 节。函数不读文件、不看进程、不取时钟、不访问网络；同样的输入永远得到同样的文档。本机看板、`rec.py wait`、推给平台的那一份都经 `fold_total` 调它，没有第二个算状态的地方。形状：`{at, observations_valid_s: 180, fold_complete, logs_unread, logs_unread_names[], internal_errors, internal[], observer{last_round_at, defects[], log_invalid_at, files_unread}, clock, ball, owner_all[], works[{work_id, title, source, steps[], defects[], withdrawn, closed_claim, log_invalid_at, log_invalid_why, log_full, torn_tail, unrecorded_runs}], feed[]}`。`works[]` 按 `work_id` 排，`feed[]` 按 `(at, work, step, text, who, state)` 排：交换输入日志的次序，文档逐字节不变。

**文档里的字分两类**。折叠自己写的是代码：`state`、`label`、`ended_how`、`reason`、`can_act`、`ball.holder`、`ball.why`，以及第 12 节的 `log_invalid_why` 和 `recorder_failed` 的 `stage`、`reason`、`argument`，值恰好是固定清单里的词（`error_class` 是第三种：一个形状受限的类名，12.1），数字、时间、id 放在旁边各自的字段里（`exit_code`、`signal`、`since`、`seq`、`silent_s`），不拼进代码。`reason` 的清单：`exited_nonzero`、`ended_by_signal`、`reported_failed`、`record_failed`、`wrapper_gone`、`no_observation`、`no_output`、`clock_backwards`、`reader_clock_behind`、`log_invalid`、`not_confirmed`、`no_match`、`conflicting_observations`、`start_not_recorded`，加上第 3 节 `error` 的那八个。引语是别人写的字：工作的 `title`、`goal`；步骤的 `name`、`who`、`note`、`quote`、`command`、`superseded_text`、`reason_quote`（记录自己写的原因）；Owner 事项的 `title`、`advice`、`reply`、`reply_words`、`commands`、`blocks_text`、`after_text`、`not_before_text`；`feed[].text`。折叠从不把引语拼进代码；页面把引语当引语显示并署名（其中的「我」是写它的 Agent），页面自己的句子只用代码来写。

**步骤有八种状态**：`waiting`、`running`、`slow`、`quiet`、`unknown`、`dead`、`failed`、`done`。`unknown` 是「现在说不出它怎么样」，页面显示 Unknown 和原因；`quiet` 只表示「看得到它活着，但 420 秒没有输出」。`process` 和 `none` 类自上而下取第一条命中的：

| # | 条件 | 状态 | 附带 |
|---|---|---|---|
| 1 | 有 `step_finished`（结束事件） | `exit.code` 为 0 或 `reported: finished` → `done`；否则 `failed` | `ended` 是那条事件的 `at`。`done` 带 `ended_how`：`exit_0`（标签 `Exited 0`）或 `reported`（标签 `Reported finished by coordinator`）。`failed` 的 `reason`：`exited_nonzero`（另带 `exit_code`）、`ended_by_signal`（另带 `signal`）、`reported_failed`。之前有过 `alive: false` 的带 `was_seen_dead: true` |
| 2 | 被取代（新声明的 `replaces`）或撤回（`step_superseded`），这一步没有开始过 | 不进步骤列表，计入 `withdrawn` | — |
| 3 | 没有有效的 `step_started` | `waiting` 或 `unknown`：按表 A 的 `step_started` 一行 | `waiting_on` 里没了结的等待、`after` 指的那一步，对这一步的状态只是背景 |
| 4 | 最近一条观测是 `alive: false` | `dead` | `reason: wrapper_gone`，另带 `since`。页面的话：包装器不在了，没有记下退出，命令也许还在跑 |
| 5 | `process` 类，依次看三条：读的一方落后；参照事件落在回拨区间里；`now` 距参照时间超过 180 秒（定义都在第 3 节「时钟异常」） | `unknown` | `reason` 依次是 `reader_clock_behind`、`clock_backwards`、`no_observation`；另带 `last_seen{alive, output_bytes, at}`：最近一条有效 `step_seen` 的原始观测，`at` 取它的 `sampled_at`；一条都没有就是 `{started: true, at}`，取 `step_started` 的 `at`。它是原始观测，不是「上一次的状态」：折叠不保存也不读取上一次生成的文档（复核 77） |
| 6 | `process` 类：有 `output_bytes`，静默超过 420 秒。静默从最近一次 `output_bytes` 变大的那条 `step_seen` 的 `sampled_at` 算起；一次都没变大过（包括每次心跳都是 0 字节），从 `step_started` 的 `at` 算起（复核 77） | `quiet` | `reason: no_output`，另带 `silent_s` |
| 7 | 有 `usual_s`，这次运行没有 `gap`，`now − started` 超过它的 1.5 倍 | `slow` | `overdue` 秒数 |
| 8 | 其余 | `running` | `none` 类带 `started_how: reported`，标签 `Reported started, not watched` |

只有第 1 行来自结束事件：到了之后，这一步的 `state`、`started`、`ended` 不再变。第 3–8 行都只是当时看到的样子，之后的事件可以改变它；`dead` 之后，能改变它的只有同一 `run_id` 的 `step_finished`。`process` 步骤在文档里一定带 `watch`、`kind`，页面在这一行上总是显示「进程 · 类别 · 命令行」；`command` 来自 `step_started`，所以没有有效开始的那一种（表 A）没有这个字段，页面在命令行的位置写 `Not recorded`，折叠不补造。**被取代不是状态**：对一个开始过的步骤，新声明的 `replaces` 只给它加 `superseded_by`（和 `superseded_text`），它的状态照旧按上表取；旧的一轮没结束，就如实显示它还在跑。重开一步不保证上一轮已经结束。

**记录类步骤**没有开始、结束事件，自上而下取第一条命中的。`started_at`、`ended_at`、`condition` 对应 Tekton v1 的 `status.startTime`、`completionTime` 和 `Succeeded` 条件，平台自己也这样读（`api/internal/delivery/service.go`、`pipeline_steps.go`）；它们是集群的时钟，`now` 是本机的，两者可能差几十秒，`slow` 的阈值是分钟级，不另处理：

| # | 情形 | 状态 |
|---|---|---|
| 1 | 有 `condition: True` 的观测（结束事件） | `done`，`ended_how: record`，标签 `Record: Succeeded`；`ended` 取 `ended_at` |
| 2 | 有 `condition: False` 的观测（结束事件） | `failed`，`reason: record_failed`，记录自己的原因在 `reason_quote`；`ended` 取 `ended_at` |
| 3 | 被取代或撤回，从没有过找到记录的观测 | 不进步骤列表，计入 `withdrawn` |
| 4 | `locator` 里还没有名字（没有东西可读） | `waiting` |
| 5 | 有名字，没被确认过 | `unknown`。`reason` 依次看：最近一轮的 `ended_at` 在 `now` 之后 2 秒以上 → `reader_clock_behind`；那一轮的 `failed` 里有它 → 那个 `error`；否则 `not_confirmed`。带 `last_seen{ref_state, at}`：最近一条有效观测里记录的原始状态和那一轮的 `ended_at`，没有就不带 |
| 6 | 确认过，最近一条观测是 `found: false`（或还没有观测） | `waiting_on` 里有没了结的等待 → `waiting`；否则 `unknown`（`no_match`） |
| 7 | 确认过，找到了，没有 `started_at` | `waiting`。记录存在不等于开始 |
| 8 | 确认过，有 `started_at`，`condition` 是 `Unknown` 或没有 | `running`（超过 `usual_s` 的 1.5 倍是 `slow`）；`started` 取 `started_at`，不取事件的时间 |

**`unknown` 怎么离开**（步骤的状态和事项的 `can_act` 都按这张表，V7 引用它）。`process` 步骤另有两条出路——一条有效的 `alive: false` 让它成为 `dead`，一条有效的 `step_finished` 让它结束；这两种事件什么时候有效，只在表 A：

| `reason` | 只靠 `now` 变大 | 靠事件 |
|---|---|---|
| `reader_clock_behind` | 会：`now` 追上之后按表重新取，可以是任何状态 | 不需要 |
| `no_observation` | 不会 | 这次运行一条新的有效 `step_seen`（此后带 `gap`） |
| `clock_backwards` | 不会 | 区间结束之后写下的、这次运行的一条有效 `step_seen` |
| `not_confirmed`、八个 `error` | 不会 | 新的一轮 `observer_round` 把这个对象列进 `confirmed` |
| `no_match`、`conflicting_observations` | 不会离开 `unknown`；确认过期时 `reason` 换成 `not_confirmed` | `no_match`：一条找到记录的 `record_seen`；`conflicting_observations`：一条 `sampled_at` 更晚的有效观测 |
| `log_invalid` | 不会 | 没有；只能手工把日志挪走（第 3 节） |
| `start_not_recorded` | 不会 | 表 A 的 `step_started` 一行 |

**时间与估算**：`process`、`none` 类的 `started`、`ended` 只取对应事件的 `at`；没有那条事件，字段就不出现。估算在声明那一刻定下：`rec.py declare` / `run` 读各份日志里同一 `kind` 最近 20 次退出码为 0、算得上样本的运行（第 3 节「时钟异常」末句），取用时的中位数写进 `usual_s`（`usual_basis: measured`）；不足 3 次用 `tasks.json` 里手写的数（`declared`；记录类步骤没有进程样本，只用它；这个数过 12.2 的数字规则，不合规当没写）；再没有就不写，这一步没有预计，也不会是 `slow`。折叠只读这一步自己的 `usual_s`，所以一件事的步骤状态只取决于它自己的日志和观测日志。预计结束是 `started` 加 `usual_s`，没有 `usual_s` 的步骤没有预计；这件事里有没结束而没有预计的步骤，或有 `quiet`、`unknown`、`dead`、`failed` 的步骤时，整件事不给时间，标 `eta_unsure`。

**`owner_all`：要他办的事只有这一份清单**。今天的「Owner 步骤」和「常设事项」在事件里是同一种东西：等待。`declared` 的等待按 `(work_id, wait_id)` 各出一项，从不合并（`wait_id` 只在一份日志里唯一，两件事的可以相同；判球时也按这一对认）。绑定记录的等待按 `ref`（种类加 id）至多出一项，几件事绑定同一条记录时这样合：任何一份日志里有过这个 `ref` 的权威终态观测，它就不出项；否则记录一级的字段（`ref_state`、`can_act`、最晚时间）取各份日志里 `sampled_at` 最晚的那条有效观测，最晚的有两条而 `ref_state`、`expires_at`、`number` 有一样不同，就是 `can_act: unknown`（`conflicting_observations`；各份日志自己的 `seq` 互不相干，不拿来分先后）；各件事自己写的字和 `holds_up` 按件分列在这一项的 `works[]` 里。次序：绑定记录的在前，其次按 `can_act`（`yes`、`unknown`、`not_yet`），再按最晚时间。折叠不输出 `needs_you`、`owner_now`、`owner_items`、`owner_next`，步骤上没有 `needs_owner`。**页面上只有一个数**：清单的长度；发布时清单被截过，就是长度加 `owner_all_cut`（第 5 节），页面只显示这一个和；它是确切的数还是「至少 n」，只在表 B。办完的事项从清单里消失，进 `feed` 一行；四步回执归 `OWNER-SURFACE` 的 P4。

每一项带 `source`：`record`（绑定一条真实记录）或 `declared`（Agent 声明的，没有记录可对）。七个标记里，建议 `advice` 两种都是 Agent 写的、可缺；其余六个这样来：

| 标记 | `record` | `declared` |
|---|---|---|
| 现在能不能办 `can_act` | 只看记录（下一张表）。步骤做没做完不参与 | 统筹方声明的 `yes` / `not_yet`（`owner_wait_ready` 改成 `yes`），带 `can_act_basis: declared` 和 `not_before_text` |
| 最晚什么时候 | 记录的 `expires_at`，`deadline_source: record` | `deadline` 或 `no_deadline`；都没写就没有这个字段 |
| 不办会卡住什么 | `holds_up[]`（步骤的 id，算出来的）：先是 `waiting_on` 含这条等待的步骤，按声明顺序；再是沿 `after` 一层层接在它们后面的步骤。另附 `blocks_text` | 同左；`blocks_nothing` 是统筹方的声明 |
| 办完之后 | `effect_s`：`holds_up` 第一项的 `usual_s`（算出来的）；另附 `after_text` | 同左 |
| 在哪办 `where` | 恒为 `console`，由种类推出；去那条记录的链接由页面按校验过的 `ref` 拼 | Agent 写的三选一，可缺。`terminal` 的另带 `commands[]`，页面逐条显示成可复制的文字，不执行、不做成链接（发布的那一份不带命令的正文，见第 5 节）；`thread` 的另带 `reply_words`。`declared` 的事项没有链接 |
| 怎么回 `reply` | 恒为 `reply_needed: false`：记录变了页面自己变 | Agent 写的，或 `reply_needed: false`，可缺 |

`declared` 的字段缺了就是缺了：文档里没有这个字段，页面显示 `Not written`，折叠不补默认值。`declared` 的事项在两个页面上、展开或收起，都带着 `Declared by coordinator, not a record` 这行字；它的 `can_act: yes` 是统筹方的说法，不是权威的可办判断。将来才会有记录的事（一张还没建的发布单）先开成 `declared` 的 `not_yet`；记录建出来后，`owner-open --approval <id> --replaces <wait_id>` 用一条带 `replaces` 的 `owner_wait_opened` 开出绑定的那一条，原来那条同时记成 `withdrawn`。

**绑定记录的等待，开合只由记录决定**。自上而下取第一条命中的；状态名是平台的原词（`approvals/types.go`、`questions/types.go`）：

| # | 看到的 | 这一项 |
|---|---|---|
| 1 | 有过权威终态的观测（审批 `executed`、`failed`、`rejected`、`expired`；提问 `answered`、`withdrawn`、`expired`），或从没有过有效观测而被撤回 | 了结，不在清单里，记原词。之后读不到、读失败都不会让它回到清单；每份有关的日志都记下终态之后，观测方不再读它 |
| 2 | 没被确认过（读失败、404、没有凭证、观测方停了、刚开出来还没轮到），或还没有一条有效观测 | 在清单里，`can_act: unknown`，`reason` 的取法同记录类步骤那张表的第 5 行；带 `last_seen{ref_state, at}`。页面显示 `Unknown, last read <时间>`，不显示成待批 |
| 3 | 确认过，审批 `pending`；提问 `open` | 在清单里，`can_act: yes` |
| 4 | 确认过，审批 `unknown`（平台的原词：执行结果不明，等他在 Console 上 resolve） | 在清单里，`can_act: yes`，`ref_state: unknown`。页面用「执行结果不明」这句话，不和 Unknown 状态混 |
| 5 | 确认过，审批 `approved`、`running` | 不在清单里：他那一步办了，记录还在走。等待还没了结，观测方继续读它，为的是接住平台的 `unknown` |

**`ball`：没有步骤在跑时，球在谁脚下**。判球时，等待一律用**合并后的结果**：`declared` 的等待用它自己的；绑定记录的等待用它那个 `ref` 按 `owner_all` 的合并规则和上表得出的那一行（了结、`can_act: unknown`、`yes`、还在走），不用这份日志自己那一条。关闭的校验相反，仍按这份日志自己的事件（第 3 节）。先给每件没关闭的工作（没有有效的 `work_closed`）判一个归属，自上而下取第一条命中的；已关闭的工作只在表 B 第 5 行那一种情形下也判：

| # | 这件事 | 归属和 `why` |
|---|---|---|
| 1 | 有步骤是 `running`、`slow`、`quiet`（`step_running`）；或有记录类步骤现在是 `waiting`、而且落在记录类那张表的第 7 行（确认过、找到了、还没开始；`record_created`）；或它有一条等待的合并结果是上表第 5 行（`record_in_flight`） | `agents` |
| 2 | 有步骤是 `unknown`（`step_unknown`）；或日志无效（`log_invalid`）；或它带表 B 第 5 行的标记（`run_unrecorded`）；或它有一条等待的合并结果是 `can_act: unknown`（`owner_item_unknown`） | `unknown` |
| 3 | 有 `waiting` 的步骤，它没有 `waiting_on`、或 `waiting_on` 里的等待按合并结果都了结了，`after` 指的那一步也结束了或没有（`next_not_sent`） | `coordinator` |
| 4 | 它有一条等待的合并结果是 `can_act: yes`（这一条就在 `owner_all` 里） | `owner`（`owner_can_act`）；只凭 `declared` 的事项得出时带 `basis: declared` |
| 5 | 它有合并结果没了结的等待、而且都是 `not_yet`（`owner_item_not_ready`）；其余情形一律是 `ended_awaiting_check`，例如没有开着的步骤而工作没关闭，或步骤在等一个 `dead` 的步骤 | `coordinator` |

再合成一个 `{holder, why, since}`：`logs_unread` 大于 0 → `unknown`（`fold_incomplete`）；否则有一件是 `agents` → `agents`；否则有一件是 `unknown` → `unknown`；否则有一件是 `coordinator` → `coordinator`（琥珀色：做完的在等它看，或下一步没派出去）；否则有一件是 `owner` → `owner`（红色）；没有一件工作被判了归属（没有没关闭的工作，也没有表 B 第 5 行那一种）→ `nobody`（绿色，`queue_done`）。关闭的工作里没有开着的步骤，也没有没了结的等待（`work_closed` 的有效条件），所以绿色不会盖住一件还开着的事。折叠完整不完整、清单和各种数确切不确切，由文档带的标记决定，只在下面的表 B。

**表 B：每个降级标记做什么。** `fold_complete` 和 `ball` 由折叠定，发布原样带着，任何一级缩减、任何上限都不重算：折叠出的文档里第 1–4 行有一行成立 ⇔ `fold_complete` 为假。「下界」是说：页面把清单的数写成「至少 n」并写明原因，`works_total`、`steps_total` 也只是下界；一个数是确切还是下界，只看顶层的 `fold_complete`，不看哪件事的标记还在不在。第 1–5 行的标记在发布的每一级（0 到 ⑥，第 5 节）都原样在，字节缩减从不去掉它们。工作一级的标记跟着它的工作走：这件事被 30 件的上限截掉时（第 5 节），它的标记随它进 `omitted_works` 的计数，顶层的 `fold_complete`、`ball` 照旧——所以没有哪一级能因为截掉了带标记的工作，把下界变成确切的数。别的标记可以随所在的步骤缩成计数，不会一点不剩。最后一栏是这个标记在场时，折叠出的文档和最终发布的字节都不许给出的结论（F1–F4 的定义在第 12 节开头）。

| # | 标记 | 来自 | `fold_complete` | `owner_all` 和各种数 | `ball` | 发布各级 | 禁止的结论 |
|---|---|---|---|---|---|---|---|
| 1 | 顶层 `logs_unread`（和 `logs_unread_names`） | 工作日志没读（表 C） | 假 | 下界 | 合成的第一条 | 每级都在 | F1–F4 |
| 2 | 工作的 `log_invalid_at`（和 `log_invalid_why`），这件事没关闭 | 工作日志断链（表 A 末三行） | 假 | 下界：断点之后可能有没读到的事项 | 逐件表第 2 行 | 每级都在，摘要里也带 | F1–F4 |
| 3 | 工作的 `torn_tail`，这件事没关闭 | 工作日志最后一个换行之后还有字节（12.2） | 假 | 下界：残尾可能是一条没写完的事项 | 不改逐件判定（这件事没关闭，所以不会是 `nobody`） | 每级都在，摘要里也带 | F1–F4 |
| 4 | 顶层 `recorder_failed` | 回退文档（12.3） | 假 | 清单为空并列在 `incomplete` 里，没有任何数 | 12.3 的表 | 回退文档不缩减，原样发 | F1–F4 |
| 5 | 工作的 `unrecorded_runs` | 最近一轮观测（期限同确认，180 秒）的 `unrecorded[]`（表 A 的 `observer_round` 一行） | 不变 | 清单确切；步骤只数记下的，这次运行不在其中，页面写 `A run was not recorded` | 这件事判给 `unknown`（`run_unrecorded`），关没关闭都判：有东西在跑而记录不知道，所以合成的结果不会是 `nobody` | 每级都在，摘要里也带 | F2 |
| 6 | 第 2、3 行的标记落在已关闭的工作上；工作的 `log_full` | 同第 2、3 行；日志写到上限 | 不变 | 确切 | 不变 | 每级都在，摘要里也带 | — |
| 7 | 工作的 `defects`（摘要里是 `defects_count`） | 工作日志里的无效事件（表 A） | 不变 | 确切：无效事件不是事件（V5） | 不变 | 没换成摘要时是列表，摘要里是个数 | — |
| 8 | 步骤的 `unknown` 和它的 `reason`、`last_seen` | 两张步骤表、表 A | 不变 | 确切 | 逐件表第 2 行 | 留下的步骤原样带；被截的步骤进 `omitted` 的计数；摘要里是 `state_counts`、`unknown_reasons`、`unknown_reasons_omitted` | — |
| 9 | 事项的 `can_act: unknown` 和它的 `reason`、`last_seen` | 绑定等待的表 | 不变 | 这一项在清单里，数确切 | 逐件表第 2 行 | 留下的项原样带；被截的计进 `owner_all_cut` | — |
| 10 | `observer` 的 `defects`、`log_invalid_at`、`files_unread`；`clock` | 观测文件（表 A、表 C）；读的一方落后（第 3 节「时钟异常」） | 不变 | 清单的成员不变 | 不直接改；要确认的对象照第 3 节「逐对象的确认」过期，变成第 8、9 行 | 每级都在（`observer.defects` 发布成 `defects_count`） | — |
| 11 | 顶层 `internal_errors`（和 `internal[]`） | 保护（12.4） | 不变（读入时捕到的另有第 2 行） | 不变 | 不变 | 每级都在 | — |
| 12 | 发布加的 `incomplete`、`reduced`、`omitted_works`、`omitted`、`owner_all_cut`、`feed_cut`、`full_at`、`commands_at` | 第 5 节 | 不变 | 列出的加省略的等于折叠出的数；那个数确切还是下界，照表头那一段 | 不变 | 从产生它的那一级起都带 | — |
| 13 | 只是说明、不算降级：`gap`、`output_large`、`was_seen_dead`、`eta_unsure`、`superseded_by`、`withdrawn` | 各自的规则 | 不变 | 不变 | 不变 | 跟着所在的步骤或工作；摘要里不保证带 | — |

**`since`：当前原因的证据从哪条事件起成立**（复核 81、88 两次指出它跟着重复观测漂移）。几件事判到同一个 `holder` 时，`why` 取逐件判定表里先出现的那一个；`since` 取现在让这个 `why` 成立的各条证据的起点里最早的一个。同一事实的再次确认——状态相同的又一次观测、心跳、笔记、修尾——不移动它。起点：`step_running` 是在跑的步骤的 `started`；`record_created` 是第一条找到这条记录的 `record_seen` 的 `at`；`record_in_flight` 是这个 `ref` 连续处于 `approved` / `running` 的第一条观测的 `sampled_at`；`next_not_sent` 是那一步的声明、它等的最后一条等待了结、`after` 那一步结束，三者里最晚的；`owner_item_not_ready` 是那条等待打开的 `at`；`ended_awaiting_check` 是这件事最后一步结束或最后一条等待了结的时间，都没有就是 `work_opened` 的 `at`（连这条也没有，就不带 `since`）；`owner_can_act` 对 `declared` 的是写下 `yes` 的那条事件（打开时，或 `owner_wait_ready`）的 `at`，对绑定记录的是它连续处于可办状态的第一条观测的 `sampled_at`；`queue_done` 是最晚一条 `work_closed` 的 `at`。等待了结的时间：`declared` 的取 `owner_wait_closed` 的 `at`，绑定记录的取最早一条权威终态观测的 `sampled_at`。**`holder` 是 `unknown` 的球不带 `since`**（`step_unknown`、`log_invalid`、`run_unrecorded`、`owner_item_unknown`、`fold_incomplete`、`recorder_failed`）：它多半是时间过去造成的，没有一条事件可以当起点，这时有用的时间是各对象的 `last_seen`。**不保证**：`since` 说的是这条证据成立了多久，不是球一直在这儿——他的事项可办之后有一步跑过又结束，`since` 仍是事项可办的那一刻。页面把它叫「当前原因的证据起点」，话照此写（`Could act since`、`Nothing running since`、`Running since`），从不写成「球在这儿多久了」；要后一个量得逐前缀重放整份历史，折叠不做（复核 92 的裁定：片 1 这样就够）。

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
- `run [声明用的参数] -- <命令>`：独占新建 `runs/<step_id>-<run_id>/`，取 `alive.lock`（不传给子进程），把 `step_declared` 和 `step_started` 写在同一次追加里，然后起子进程——这次追加和别的追加一样，取锁至多重试 2 秒（起命令之前的重试是有界的，就是这一条；复核 94 裁定 ②），写成了、只写成一行、或整个没写成，都起（第 2 节「不管进程」；后两种在 stderr 写明，此后不再为这次运行记账，看板怎么说只在表 A 的 `step_started` 一行）；每 60 秒写一条 `step_seen`（输出文件的长度，和末尾 4 KiB 里的最后一行）；`wait()` 返回后写 `step_finished`，再用同样的退出码退出。子进程创建失败时补一条 `step_finished`（`exit.code` 127，`quote` 是系统的错误文字）。
- `observe`：一轮做三件事再退出——对每次没有结束事件的 `process` 运行探测 `alive.lock`（不读 PID，不发信号；锁随持有进程死亡释放、不被子进程继承，已停设计第 13 节第 2 条核对过），顺带把运行目录在、锁被持有、日志里却没有开始事件的运行列进 `unrecorded[]`（锁已经放开的不报；运行目录怎么对上 `step_id` 归这一片的适配层）；对每个在某份日志里还没了结的 `ref` 读一次平台；对每个有名字、没结束、没被撤回的记录类步骤读一次集群；有变化的写进各份有关的日志，最后写 `observer_round`（`confirmed` 和 `failed`）。看板循环每 15 秒起一轮 `observe`，每 2 秒 `fold` 一次。
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

- **`publish_view` 留工作至多 30 件**，按这个次序留：有 Owner 事项或有 `unknown` / `dead` / `failed` / `quiet` 步骤的未关闭工作 → 有在跑步骤的 → 其余未关闭的（最近有事件的在前）→ 已关闭的（最近关闭的在前，按那条 `work_closed` 的 `at`；拿到一份没带关闭时间的旧文档时退回这件事最后一条有效事件的时间）。留不下的记进顶层 `omitted_works{open, closed}`；有未关闭的被截时，`incomplete` 里有 `works`。总量也发：顶层 `works_total{open, closed}`，每件事 `steps_total`。凡是有东西被截或被减，文档带 `full_at: local_board`，页面写明全量在本机看板（`host`）。
- **每件事至多 20 步**，按这个次序留：`unknown` → `dead` → `failed` → `quiet` → `slow` → `running` → `waiting`（按声明顺序）→ 最近的 `done`；被取代且结束了的排最后；不认识的状态值按 `unknown` 的次序留。留不下的记进这件事的 `omitted`，八种状态各有计数。`feed` 至多 25 条。
- **`owner_all` 只有一条截断规则**：按清单的次序从头留，至多 30 项；字节放不下时（下一条的第 ⑥ 级）从末尾再往前截。两种截法截掉的都是排在最后的整项，条数都加进同一个 `owner_all_cut`，`incomplete` 里有 `owner_all`。留下的每一项字段原样保留，只有一个例外：`commands` 的正文不发（照 `slim_for_publish` 现在的做法，命令只在本机看板上），那一项改带 `commands_at: local_board` 和 `commands_count`（条数）。文档里没有另一个总数字段：页面的那个数是留下的条数加 `owner_all_cut`，只显示一次，旁边写「这里列出 m 件，全量在本机看板（`host`）」。**被截的清单，文档只说「本文档省略了 n 项」**（`owner_all_cut`、`omitted`、`omitted_works`、`feed_cut`），从不给跨来源的总数：文档数不到平台自己的记录，页面按 Console Progress 设计第 3 节把「列出的」和「本文档没列出的」分开写。`works_total`、`steps_total` 只是发布方截之前自己手里的数；它们确切还是下界，只在表 B。
- **字节**：目标 204,800 字节（200 KiB），量的是推送脚本实际发出去的那串字节：UTF-8 编码的紧凑 JSON，`host` 已经在里面，推送方原样发送、不再解析重排。量的是编码后的实际长度（转义、嵌套列表、`defects` 都在内），不拿字数乘系数。留出的 56 KiB 给服务端的重新编码、脱敏改写和外壳。**附加块先并进来，再量**：`roadmap`、`graph`、`queue`、`usage`、`coordinator`、`recent`、在跑步骤的 `events[]`（每步至多 30 条）和并读期间来源是 `hand` 的工作不是折叠的产物，由发布方作为 `blocks` 交给 `publish_total`，在任何缩减之前并进文档，一起算进这 204,800 字节。它们逐块（`hand` 的工作逐件）过 12.2 的字符、数字、深度规则和平台对已知字段的类型、长度限制，不合的那一块不发。字节放不下时先整块去掉附加块（次序 `events[]` → `recent` → `usage` → `graph` → `queue` → `roadmap` → `coordinator`，去一块量一次；状态先于附加块，因为附加块缺了页面有带名字的缺失块可显示），再走 ①–⑥。没发的每一块都在 `incomplete` 里点名。超了就按固定次序减，每减一级重新量：① 去掉结束了的步骤的 `note`、`quote`、`command` → ② `feed` 留 10 条 → ③ 已关闭的工作换成摘要 → ④ 每件事只留没结束的步骤，至多 5 步，不带 `note` → ⑤ 每件事都换成摘要 → ⑥ `owner_all` 从末尾整项截掉，一项一项量着往第 ⑤ 级的骨架里加，所以一定放得下（骨架本身不超过目标，测试用顶格输入核对）。到了哪一级，文档带 `reduced: <级别>`，两个页面都显示「内容已缩减」。**摘要**里每件事恰好这些字段：`work_id`、`title`、`state_counts`（八种状态各几步）、`unknown_reasons`（至多 3 个 `reason` 代码）、`unknown_reasons_omitted`（没列出的个数）、`defects_count`，以及有的话 `closed_claim` 和表 B 里写着「摘要里也带」的标记。**每一级都留着的**：表 B 里写着「每级都在」的标记；另外是顶层的 `at`、`ball`、`fold_complete`、`observer.last_round_at`、`works_total`，和每件事八种状态的步数（没换成摘要的是留下的步骤加 `omitted`，换成摘要的是 `state_counts`）。没换成摘要的工作里，留下的每一步都带 `state`、`reason`、`last_seen`，没结束的 `process` 步骤还带 `kind` 和 `command`（没有 `command` 的那一种见第 4 节进程表后一段）。
- **Console 读哪一份**：Console 的 Progress 页从 W-62 第四片第 3 轮起读 `owner_all`，没有这个字段才退回旧字段（`console/src/pages/shell/progress/`）。本文的发布形状只在五样都成立之后启用。三样要到了 PROD 并验收：读 `owner_all` 的那一版；Console 自己配的状态字改成第 2 节的三种写法；第 4 节那条 180 秒的过期覆盖。第四样，**两页各自过三类夹具**：回退文档、不完整的文档（`fold_complete` 为假、`incomplete` 不空）、有日志没读的文档——Console 和本机看板哪一页没过，哪一页就不切到这份文档，因为今天这两页都会把这些读成没事（12.3）。第五样：**发布方把附加块和 `events[]` 交给了 `publish_total`**——Console Progress 设计把它列为切换的条件，少了 `events[]`，逐条动作退成每步一行，就不切；某一次因为缩减或不合规而没发的块在 `incomplete` 里点名，页面显示带名字的缺失块，这不算条件不成立。片 1 不切换任何一页，也不推送这种形状。所以 `publish_view` 不输出 `owner_now`，也不输出任何第二份投影：文档里列他的事项的字段只有 `owner_all` 一个。在那之前，片 2 不切换推送来源，`board2.py` 照旧推它现在那份。服务端的校验今天不认识 `owner_all`，把它当未知键放过，只受总字节数约束；所以清单自己的上限由 `publish_view` 定，就是上面那一条截断规则。推送仍用现有脚本；服务端每次的回答（状态码、原因、字节数）照 `publish-result.js` 现在的做法记下，显示在本机看板上；`scripts/progress-publish.js` 改成返回状态，归 TD-308。

## 6. 信任与滥用

每一条事件都是某个 Agent 或它启动的脚本写的，写的一方和读的一方是同一个 Unix 用户。对折叠和渲染来说，事件是不可信的输入：只校验形状，不执行、不解析里面的文字。入口的分工是约定，由命令行的入口执行；手工拼一行封好的事件可以绕过它，包括伪造一条 `by: observer` 的观测或一轮 `observer_round`。

- **一条错的或恶意的事件能造成什么**：一块说错话的本机看板。没跑的步骤显示 `Exited 0`；在跑的显示失败或 Unknown；伪造的观测让一张待批的单在本机看板上显示成已批，或让一张不存在的单显示成待批；凭空多出一条「需要你」；估算被写歪；大量事件把日志写满、把发布的文档挤到缩减级别。统筹线程和 Owner 都看这块看板，所以会被它带偏；验收脚本、独立复核、CI、审批这些闸门不读它。**它造成不了什么**：没有东西因为它被合并、发布或批准。记录器不持有能写的凭证，不调平台的写接口，不写集群。
- **页面把 Agent 的声明和权威记录分开**：每个 Owner 事项带 `source`。本机看板上绑定记录的事项写的是 `Read by observer at <时间>`，旁边是去 Console 的链接；它是 Agent 一侧读了之后写的事件，不是权威。**权威只有 Console**：P6 的要求是 Console 拿 `ref.id` 去对平台自己的审批和提问记录，状态用平台自己的；推上来的文档里有、平台里找不到的 id，显示成 `Unknown record`，不显示成待批。`declared` 的事项始终带着 `Declared by coordinator, not a record`，没有链接；它的命令和要回的原话只是给人看的文字。链接只给 `source: record` 的事项，由页面按校验过的 `ref`（种类、id、编号）拼出，主机名是页面自己的常数；id 的格式在写入和折叠时各校验一遍。
- **「不当判词」能做到哪一步**：词表里没有通过。防线在片 1 交付，登记进 `RATCHETS.md`。受保护的入口：`bifrost-trade-infra` 的 `scripts/release/`、`k8s/cicd/`、`agent-config/scripts/git-hooks/`、`agent-config/scripts/agent-guard/`；平台的 `approvals`、`actions`、`delivery`、`releasepolicy`、`gitops`、`promote` 这几个包。检查两样：前四个目录的文本里不出现 `agent-work/events`、`agent-work/status`、`recorder/`、`rec.py`、`board2`、`status.publish`、`agent/progress`（写本文时这七个词在那里一处都没有）；后几个包不依赖 `agentprogress`（平台仓库里一条依赖测试，照 `questions/deps_test.go` 的写法；现在只有 `server` 包引用它）。**它挡不住的**：别名和软链接；这些目录之外的包装脚本（`~/agent-work/` 下统筹方自己的脚本不在任何仓库里）；把文档复制成别的名字再读；以后新加的消费者；以及人和 Agent 看了看板之后自己做的判断。`done`、`landed`、`can_act`、`rec.py wait` 的退出码都可能被人或新工具当成判词；`wait && 合并` 这样的命令写得出来、也会执行合并。这条防线只保护列出的入口，不是普遍的放行保证。第二半若要读事件，只能当线索（第 9 节）。
- **对着真实记录核对的**：审批和提问的状态、过期时间，读平台的只读接口；流水线运行的状态和起止时间，读集群。进程的退出码是包装器从 `wait()` 取的第一手数，但它仍是 Agent 一侧写的事件，只用于显示。提交有没有进主线、有没有发到某个环境，这一半不核对，也不显示成事实。给 Owner 看的文字：页面按纯文本插入引语，不当 HTML，加引号并署名，不按它上色。
- **没有处理的**：同用户重写整份日志或伪造观测（上面已说）；`declared` 的事项完全靠统筹方，它可以一直开着（第 10 节）；子进程输出占多少磁盘；把坏日志挪出根目录这个手工动作有没有被正确使用。折叠的耗时由日志条数和份数的上限界定：片 1 用顶格夹具量一次，本机上一轮超过 2 秒就调小上限，不调慢看板。

## 7. 验收

每条写成「输入 → 期望的文档」。断言的对象是看板和推送实际拿到的东西，即 `fold` 和 `publish_view` 的输出，不是内部的中间量（教训第 77 行）。

1. **折叠是纯函数，穷举短序列**。字母表在任务书里列全：一件事；一个 `process` 步骤、一个 `record` 步骤、一个 `none` 步骤；一条绑定审批的等待、一条 `declared` 的等待；每种事件，含带错 `run_id` 的心跳、`by` 不相配的开始、平台每一种审批状态的观测、`at` 回拨的事件、带 `confirmed` 和带 `failed` 的 `observer_round`、`work_closed`。穷举长度不超过 5 的全部序列（默认跑到长度 3：33 个字母、37,060 条，带 `by_step` 的取代换成带 `replaces` 的声明，个数不变；长度 4、5 由 `RECORDER_ENUM_LEN` 打开，受第 8 条的时间预算约束），`now` 各取三个值：序列里最后一条事件的 `at`、之后 200 秒、之后 2000 秒。序列里有 `at` 回拨的事件，所以 `now` 可以早于前面某条事件的 `at`：这就是读的一方落后的情形，V7 把它写成例外。静态检查：读入、折叠和 `publish_view` 所在的模块不导入 `os`、`time`、`subprocess`、`socket`、`pathlib`，不调用 `open`。对每个前缀断言：
   - V1 不抛异常，而且 `internal_errors` 为 0、没有 `recorder_failed`（穷举的参数都合规，属于第 8 条的甲族和丙族；没抛不能是保护吞掉的结果）；`publish_view` 的输出满足第 5 节的每一条限制。V2 一步是 `running` / `slow` / `quiet` ⇒ 它没有结束事件，并且：`process` 类有有效的 `step_started`，读的一方不落后，参照事件不是 `alive: false`、不在回拨区间里，参照时间距 `now` 不超过 180 秒；`none` 类有有效的 `step_started`；`record` 类确认过，最近一条有效观测找到了记录、带 `started_at`。V3 只有结束事件定下的状态不再变：一步有了结束事件，更长的前缀、更大的 `now` 下，它的 `state`、`started`、`ended` 不变；`waiting`、`running`、`slow`、`quiet`、`unknown`、`dead` 都可以被之后的事件改变，`dead` 之后能改变它的只有同一 `run_id` 的 `step_finished`。V4 `started`、`ended` 等于对应事件的 `at`（记录类等于观测里的 `started_at`、`ended_at`）；没有来源就没有这个字段。V5 表 A 里结果是「这一行不存在」的事件：把它们全部从序列里删掉、用同一个 `now` 再折叠，除 `defects` 外文档逐字节相同（断链的行不在此列）。V6 绑定记录的等待了结 ⇔ 有过一条权威终态的有效观测，或从没有过有效观测而被 `withdrawn`；一个 `ref` 有过权威终态的有效观测之后，任何更长的前缀、任何 `now` 下它都不在清单里；除了那一种 `withdrawn`，统筹方的事件改变不了它的开合。
   - V7 没有新事件、只有 `now` 变大。唯一的回头路：`reason` 是 `reader_clock_behind` 的 `unknown`（步骤的状态或事项的 `can_act`），`now` 追上之后按表重新取，可以变成任何状态；其余 `reason` 的 `unknown` 不会只因为 `now` 变大而离开 `unknown`，只有 `reason` 可以换（第 4 节「`unknown` 怎么离开」）。除了这条回头路，按类别：`process`——`waiting`、`dead`、`done`、`failed` 不变；`running` 可以变成 `slow`、`quiet`、`unknown`，`slow` 可以变成 `quiet`、`unknown`，`quiet` 只能变成 `unknown`。`none`——只有 `running → slow`，别的不变。`record`——`done`、`failed` 和 `locator` 里没有名字的 `waiting` 不变；其余的 `waiting`、`running`、`slow` 在确认过期（最近一轮的 `ended_at` 距 `now` 超过 180 秒）时变成 `unknown`，之前 `running` 可以先变成 `slow`。Owner 事项——`declared` 的和了结的不变；其余绑定记录的在确认过期时成为清单里的 `can_act: unknown`（包括原先落在第 5 行、不在清单里的）。
   - V8 两条。**置换**：交换输入日志（和观测文件）的次序，输出逐字节不变，没有例外——选哪些来读、重名怎么办都不看次序（表 C），所以超过上限、有重名时也成立。**局部**：一件被读进来的事，它的 `works[]` 条目只取决于它自己的日志和观测日志；增删改别的日志，只要它仍被读进来，这一条逐字节不变，变的只有 `owner_all`、`ball`、`logs_unread`（别的日志把它挤出上限时，它不在 `works[]` 里而在 `logs_unread` 里，不算这一条的反例）。V9 一份清单：每条 `declared` 的没了结的等待（按 `(work_id, wait_id)` 认）恰好出一项；每个 `ref` 至多出一项；`fold` 输出的键里没有 `needs_you`、`owner_now`、`owner_items`、`owner_next`、`needs_owner`，也没有别的数他的事项的字段。V10 代码取自固定清单：`state`、`label`、`ended_how`、`reason`、`can_act`、`ball.holder`、`ball.why` 的值恰好是清单里的词；改任何引语，这些值逐字节不变。V11 `ball`：`agents` ⇔ `logs_unread` 为 0 且有一件没关闭的工作判给 `agents`；`nobody` ⇔ `logs_unread` 为 0 且没有一件工作被判了归属（哪些工作判，只在第 4 节 `ball` 开头一段和表 B 第 5 行）；`owner` ⇒ 清单里有 `can_act: yes`，且没有一件工作判给 `agents`、`unknown`、`coordinator`。V12 关闭：一件事算关闭 ⇔ 有一条有效的 `work_closed`；关闭的工作里没有开着的步骤，也没有没了结的等待，之后的事件也不会让它再有。
2. **每个字段的效果，各有一条有名字的测试**。原来对样本日志做删改、把差异归类的测试删了：它的规则和合法的事件序列互相矛盾（复核 73）。换成三部分：
   - (a) **只管展示的字段**：`work_opened` 的 `title`、`goal`、`work_ref`；`step_declared` 的 `name`、`who`、`round`；`step_started` 的 `command`；`step_seen` 的 `text`（进 `note`）；`step_finished` 的 `quote`；`step_declared` 的 `replaces_text`（进旧步骤的 `superseded_text`）；`record_seen` 的 `reason_quote`；`owner_wait_opened` 的 `title`、`advice`、`reply`、`reply_needed`、`reply_words`、`commands`、`blocks_text`、`blocks_nothing`、`after_text`、`not_before_text`、`after`；`owner_wait_seen` 的 `number`；`work_closed` 的 `claim`（进 `closed_claim`）；`note` 的 `text`（进 `feed` 的那一行）。对每一个：换成另一个合法的值，`fold` 出的两份文档只在原样带着这个值的字段上不同（它自己的输出字段，和 `feed` 里引用它的行），别处逐字节相同。`step_started` 的 `pid` 和 `step_superseded` 的 `text`（撤回的步骤不在列表里）不进文档：改它们，文档逐字节不变。
   - (b) **其余字段**，每个一条测试，名字里带字段名。表里写的是这条测试必须看到的效果；由步骤的状态和等待的开合再派生出来的变化——`ball`、`owner_all` 的次序和 `holds_up`、所在工作的 `eta_unsure`、`publish_view` 的保留次序和计数——都允许跟着变，测试不把它们当成错：

   | 字段 | 测试断言的效果（规则在第 3、4 节） |
   |---|---|
   | `step_declared` 的 `kind`、`watch` | 不对应 → 无效；`watch` 决定这一步按哪张表取状态 |
   | `step_declared` 的 `waiting_on` | `process` 类带它 → 无效；`none` 类在等待没了结时 `step_started` 无效；记录类没找到记录时是 `waiting` 还是 `unknown`；等待的 `holds_up`；`ball` 的 `next_not_sent` |
   | `step_declared` 的 `after` | 这一步和别的步骤的 `state` 不变；变的是 `ball`（逐件判定表第 3、5 行）和 Owner 事项的 `holds_up` |
   | `step_declared` 的 `locator.name` | 没有 `name` → `waiting`、不读 |
   | `step_declared` 的 `usual_s` | 这一步的 `state` 只在 `running` 和 `slow` 之间变；另外变的是 `overdue`、预计结束、所在工作的 `eta_unsure`、Owner 事项的 `effect_s` |
   | `step_declared` 的 `replaces`；`step_superseded`（整条） | 前者：旧步骤开始过 → 加 `superseded_by`、状态不变，没开始过 → 离开列表、计入 `withdrawn`；指向不存在或已被取代的步骤 → 整条声明无效，新旧两步都不变。后者：撤回，开始过的无效 |
   | `step_seen` 的 `alive`、`output_bytes`、`sampled_at` | `false` → `dead`；420 秒没变大 → `quiet`；`sampled_at` 定 180 秒的期限和 `gap` |
   | `step_finished` 的 `exit`、`reported` | `done` / `failed`、`ended_how`、`reason` 代码；在 `alive: false` 之后仍然生效并带 `was_seen_dead` |
   | `record_seen` 的 `found`、`uid`、`started_at`、`ended_at`、`condition` | 记录类那张表的每一行；`uid` 不同 → 无效 |
   | `owner_wait_opened` 的 `ref`、`can_act`、`deadline`、`no_deadline`、`where`；`owner_wait_ready`；`owner_wait_closed` 的 `how` | `source`；同一个 `ref` 出一项；`declared` 的 `yes` / `not_yet`；清单的次序；`where` 不在三选一里 → 无效；合上；`owner_wait_opened` 的 `replaces` 把原来那条记成 `withdrawn` |
   | `owner_wait_seen` 的 `ref_state`、`expires_at`、`sampled_at` | 绑定等待那张表的每一行；最晚时间；几份日志里取 `sampled_at` 最晚的一条，同时而不同 → `unknown` |
   | `observer_round` 的 `ended_at`、`confirmed`、`failed`、`unrecorded` | 确认与否；`unknown` 的 `reason` 代码；超过 180 秒 → 不算确认；`unrecorded` 的效果按表 A 的 `step_started`、`observer_round` 两行和表 B 第 5 行 |
   | `work_closed`（整条） | 有开着的步骤或没了结的等待 → 无效（`closed_with_open_items`）；有效时这件事不再参与 `ball` |
   | 包络：`at`、`by`、`run_id`、`step_id`、`wait_id` | `at` 定 `started`、`ended`、`ball.since` 和时钟回拨；`by` 与入口不相配、id 指向不存在的东西、`run_id` 不符 → 无效 |

   - (c) **无效输入，一律经封好的字节**（复核 88：上一轮的 1,980 个变异体全部断链，测的是退回去的原始字典）。每个变异体重建成一份封好的日志——被改的那一行和它后面的每一行重新算摘要、接好 `prev_sha256`——以字节交给 `fold_total`；封不成、或读入就断链，算测试失败，不许退回去折原始字典。分两组，互不混用。**事件字段**：对每种事件的每个字段（含嵌套，照字段表走，不手写名单；`observer_round` 在观测日志里变异，不放进工作日志），逐个删掉、换成别的类型、换成闭合取值之外的值、加一个多余字段、把 `type` 换成不认识的，再逐个换成第 8 条 C 族的叶子池（其中让整行过不了 12.2 第 3–7 条的 `NaN` 和深数组归下一组）→ 按换上去的值分两支。对这个字段**合法**的（`-0` 等于 0，处处合法；`1.0` 只在收浮点的字段合法；空串、`0`、布尔只在收它们的字段合法——名单锁在测试里，只许有事件字段的合法值）：这就是一份有效的日志，那条事件没有 `defects`，断言走第 8 条的甲族。**不合法**的：结果按表 A 里那种事件的一行（就是 V5；状态因此可以变），断言走丙族。**链字段**：改 `seq`、`prev_sha256`、`v`、行首的摘要、行的外形、深度、长度 → 结果按表 A 末三行，断言走丙族。三处都要 `internal_errors` 为 0、没有 `recorder_failed`。
3. **回归**：
   - 事故 1，三条：(a) `declare --kind release --watch process` 被拒；给 `process` 步骤带 `waiting_on` 被拒；于是「绑定待批等待的发布步骤被 `run` 包住」写不出来。(b) 发布步骤（`record`）→ 确认过、找到了运行、没有 `started_at` → `waiting`，没有 `started`；观测到 `started_at` 之后才是 `running`，`started` 等于它；找到了、没开始、确认过时 `ball` 是 `agents`（`record_created`），确认过期之后这一步是 `unknown`，`ball` 也是 `unknown`。(c) 4000 秒里只有 `owner_wait_seen` 和 `observer_round` → 发布步骤一直 `waiting`；对它写 `step_started`、`step_seen` 被拒。另：`kind: other` 的进程步骤在文档里带 `watch`、`kind`、`command`。
   - 事故 2，三条：(a) 第 1 轮结束 → 第 2 轮声明、开始、心跳 → 第 1 轮那一步逐字节不变；拿第 2 轮的 `run_id` 给第 1 轮写心跳被拒。(b) 旧步骤开始 → 新步骤声明并开始，不带 `--replaces`，旧包装器继续心跳 → 两步都是 `running`。(c) 同上但带 `--replaces` → 旧的仍是 `running`，带 `superseded_by`；旧包装器被杀后旧的成为 `dead`，新的不受影响。端到端：两轮用同一条命令行跑。
   - 没有有效开始的步骤（复核 92、94），每条逐格对表 A 的 `step_started`、`step_seen`、`step_finished`、`observer_round` 四行和表 B 第 5、8 行：只有包装器的 `step_declared`；包装器的声明后接一条字段不合规的 `step_started`，再接观测方的 `step_seen(alive: false)`，再接一条 `step_finished`；统筹方声明、从没开始、没有任何观测数据；最近一轮的 `unrecorded[]` 里有它；`unrecorded[]` 里的 `step_id` 不在日志里；同一步同时出现在 `unrecorded` 和 `confirmed` 里的一轮；撤回它之后。每条另核对 `rec.py close` 被不被拒、文档里有没有 `command`。
   - `dead` 之后的结束：`step_started → step_seen(alive: false) → step_finished(exit 0)` → 三个前缀依次是 `running`、`dead`、`done`（`Exited 0`，`was_seen_dead: true`）；之后再来的 `step_seen` 无效。
   - 关闭，复核 73 的三条序列：(a) `open → owner-open（审批，待批）→ close`：`rec.py close` 被拒；手工拼的 `work_closed` 进 `defects`（`closed_with_open_items`），这件事仍没关闭，清单里有这一项，确认过时 `ball` 是 `owner`，不是 `nobody`。(b) `record` 步骤在跑时关闭 → 同样无效，`ball` 是 `agents`。(c) `none` 步骤报了开始、没报结束时关闭 → 同样无效，`ball` 是 `agents`。另三条：审批 `approved`（还在走）时关闭无效；只剩 `dead` 的步骤时关闭有效，之后补来的 `step_finished` 把它改成 `done` 或 `failed`，工作仍是关闭的；关闭之后的 `step_declared`、`owner_wait_opened` 无效。
   - 事故 3：绑定审批的等待 → 假平台把单子依次改成平台的八种状态 → 每一轮 `observe` 之后这一项的有无和 `can_act` 逐行对上第 4 节的表；全程没有调用统筹方的命令；`rec.py owner-close` 对它被拒。`approved` 之后变成平台的 `unknown` → 这一项回到清单。`executed` 之后观测方不再读它；此后伪造一轮把它列进 `failed` → 这一项不回到清单。假平台回 500、403、404、超时各一次 → 当轮进 `failed`，这一项是 `can_act: unknown`，带上一次读到的状态和时间。没有令牌 → 全部 `unknown`。观测停 181 秒 → `unknown`。变化的事件追加失败（日志的锁被占）→ 这个键进 `failed`（`append_failed`），这一项是 `unknown`，不是旧状态。
   - 事故 4：31 件事；一件事 21 个活跃步骤；100 件事、一件事 200 步、每个文字字段顶到上限（含四字节字符、引号、反斜杠、`<>&`、形如 `token=x` 的字）；31 条和多到字节放不下的 Owner 事项 → `publish_view` 的输出不超过 204,800 字节、满足每一条数组上限、没有 null；每个被截的类别都有计数；留下的条数加 `owner_all_cut` 等于折叠出的清单长度；第 ⑤ 级的每件事恰好是摘要那几个字段。带 3 条 `commands` 的 `declared` 事项 → 发布的那一项没有 `commands`，有 `commands_at: local_board` 和 `commands_count: 3`，其余字段和本机文档里的逐字节相同。假服务端回 413 → 本机文档的推送结果一栏是失败和原因。
   - Owner 的三条：三件事各有一条绑定的和一条 `declared` 的等待，两件事绑定同一张单 → `owner_all` 里那张单只有一项、带两件事的 `works[]`，绑定的在前；两份日志对同一张单一份见到 `approved`、一份还是 `pending` → 取 `sampled_at` 晚的；同时而不同 → 这一项是 `can_act: unknown`（`conflicting_observations`），只有这两件事时 `ball` 是 `unknown`。部分传播（只有两件事，绑定同一张单，各只有这一条等待，只有一份日志记下了 `executed`）→ 清单里没有这一项，`ball` 是 `coordinator`，不是 `owner`；对还没记下的那件事 `rec.py close` 仍被拒（它自己的日志里这条等待还没了结）。两条标题相同的 `declared` 等待 → 两项；两件事各有一条 `wait_id` 相同的 `declared` 等待，一条 `yes`、一条 `not_yet` → 两项，`ball` 是 `owner`（复核 88）。缺 `advice`、`where`、`reply` 的 `declared` 事项，文档里就没有这三个字段。`ball` 逐件判定表的每一行和合成的每一种结果各一条，含 `since`（同一条运行记录、同一张待批的单再观测一次，或加一条笔记，`since` 不变；`unknown` 的球没有 `since`）；复核 73 的五个例子各一条（都结束了而没关闭 → `coordinator`；一件等他、另一件等统筹方 → `coordinator`；只有 `declared` 的等待 → `owner` 带 `basis: declared`；观测方停了 → `unknown`；快照过期 → 页面覆盖成 Unknown）。多文件输入（复核 92、94；结果按表 C 和表 B 第 1、10 行），每一条正着、倒着各交一次，输出逐字节相同：201 份日志；201 份日志而调用方另给 `logs_unread=3`（怎么相加在表 C 最后一栏）；两份同名而内容不同的工作日志；两个同名的观测文件，一个把某个键放在 `confirmed`、一个放在 `failed`；名字里有落单代理码的一份。
   - 时钟与观测方：睡眠（两条心跳隔 3 小时）→ 期间 `unknown`，恢复后 `running`、带 `gap`、没有 `slow`，这次的用时不进下一次声明的 `usual_s`；回拨：一步的心跳写在回拨区间里 → `unknown`（`clock_backwards`），区间结束后它的下一条心跳让它回到 `running`；参照事件在区间之前的另一步不受影响；两个 `observe` 同时起 → 只有一个写事件，另一个退出，日志里没有交错的样本；观测方不在 → 记录类步骤和绑定的事项在 181 秒后是 `unknown`，进程类步骤仍由包装器的心跳决定；复核 76 的序列 `work_opened(at=0) → step_declared(process, at=1) → step_started(at=300) → note(at=240)`，没有估算、没有心跳：`now=240` → `unknown`（`reader_clock_behind`）；`now=440` → `running`；`now=2240` → `unknown`（`no_observation`）。记录这一侧同样三段：最近一轮的 `ended_at=300`，`now=240` → 记录类步骤和绑定的事项是 `unknown`（`reader_clock_behind`）；`now=440` → 按表；`now=500` → `unknown`（`not_confirmed`）。复核 88 的三条：`start@100 → note@90 → finish(exit 0)@120` 不是样本；确认过（`ended_at=100`）之后的一轮（`ended_at=150`）把同一个键同时放进 `confirmed` 和 `failed`，以及观测日志里 `failed=[{key: [], error: timeout}]` 的一轮 → 都按表 A 的 `observer_round` 一行（前一条的 `last_seen.at` 仍是 100）。
4. **发布的上限，过真实的校验**。每一级缩减各一条。平台仓库 `api/internal/agentprogress/` 加一条测试：读环境变量指的目录，把每份夹具走一遍真实的 `HandlePut`（校验、脱敏、重新编码、外壳大小都在这条路上），要求 202，并回读核对 `owner_all` 的条数和各步的 `state` 没有被服务端改掉。记录器这边的测试生成上一条里的夹具，在同级的 platform 检出里跑它；同一条测试把记录器里的上限常数和 `schema.go`、`document.go` 源码里的常数逐个比对。没有 platform 检出时这条测试报「没有跑」，验收不算通过。它不在 infra 的 CI 里：平台改了上限，要到下一次在工作区里跑验收才发现，这是已知的缺口。本文写的时候这条测试还不存在，上面的限制表是读源码得来的，不是跑出来的结果。
5. **发事件的一侧，端到端**（教训第 73 行）：`rec.py run` 包住五种假命令（退出 0、退出 9、被 TERM、长时间不出声——出过声之后安静的和从头到尾 0 字节的各一种、包装器自己被 `kill -9`）→ 真实日志 → 折叠出 `done`（`Exited 0`）/ `failed` / `failed` / `quiet` / `dead`。**故障注入：记不上账也不拦命令**——`run` 的那次追加在第二行失败（写到一半返回错误）和整个失败（锁被占）各一次 → 命令照样跑完，退出码原样传回，stderr 写明没记上；日志里没有这次运行的 `step_started`、心跳和结束；折叠的结果按表 A 的 `step_started` 一行（前一种）和表 B 第 5 行（后一种），命令还在跑时 `observe` 一轮之后再对一遍；文档里没有一处说这条命令没开始或已结束。`observe` 对着会核对请求的假平台和假 `kubectl`：只许出现读请求（HTTP 只有 GET，`kubectl` 只有 `get`），请求头里的令牌只发给配置的那个主机，出现别的即失败。静态检查：源码里没有 `os.kill`、`killpg`、`send_signal`、`terminate`、`.kill(`、`pgrep`，没有读 `pid` 字段的代码，没有 `mcp-tokens`。
6. **链和残尾**：改中间一行不重封 → 表 A 末三行的结果，追加被拒；一条有效的 `work_opened` 后接没有换行的 `owner_wait_opened` → 表 B 第 3 行，在每一级缩减的发布字节上都核对（复核 94）；残尾修复沿用拣过来的测试；两个进程同时追加 → 两条都在，`seq` 连续；日志写到上限 → 追加被拒，`log_full`。
7. **防线**：第 6 节的文本扫描和依赖测试各有一条会让它失败的反例；`scripts/release/` 现有的离线测试在三种环境下各跑一遍（事件根目录和看板文档原样、不存在、换成伪造的「全部 `Exited 0`」），输出逐字节相同。
8. **全函数（第 12 节）**。断言都对着 `fold_total` 和 `publish_total`，日志一律以字节交进去。输入分四族，一个用例只属于一族，各有各的预期——「没有回退」和「保护没被用到」不是对所有输入说的（复核 92）：

   | 族 | 输入 | 必须得到 | 断言 |
   |---|---|---|---|
   | 甲 必须算出来 | 参数合规，每一行都读得出来、形状合规（过 12.2 第 2–9 条，字段集合和类型也对）：回归集里这类用例、穷举（37,060 条 × 三个 `now`）、变异和模糊里换成合法值的。事件之间的关系可以不合规（穷举里有带错 `run_id` 的心跳），那归 V5 | 正常文档 | 没有 `recorder_failed`；`internal_errors` 为 0；没有 `log_invalid_at`，`defects` 里只有关系类的代码；V1–V12；T2 |
   | 乙 参数回退 | 参数不合规：回归集里的 `now = 10**400`、`NaN`、布尔、字符串；`logs_unread = -1`；D 族的 Python 对象；不是折叠形状的 `document` | 回退文档，`reason: invalid_argument`——这是**正确的结果**，不是失败 | `internal_errors` 为 0；12.3 的表逐字段；对象的自定义方法一次也没被调用；日志非空也照样整份回退，T2 对这一族不适用，单独按这一行验收 |
   | 丙 逐行降级 | 参数合规，有行不合规、有残尾、有文件没读或被拒读：变异和 C 族里换成不合法值的、A 族、B 族、复核 81 和 88 里封好的坏行、超过上限的日志、重名或名字不合的文件；E 族不合规的 `host`、`blocks` | 正常文档，带降级标记 | 没有 `recorder_failed`；`internal_errors` 为 0；每一处的结果按表 A、表 C；它在表 B 里的标记，在折叠出的文档上、在每一级缩减的发布字节上都在，那一行「禁止的结论」一条都不成立；E 族 → 那一块在 `incomplete` 里点名；T2 |
   | 丁 保护的对照 | 往读入的一行、折叠、发布、回退的构造里各注入 `RecursionError`、`MemoryError` 和一个自定义异常；另注入 `KeyboardInterrupt` | 依次是 `log_invalid_why: internal`、`caught` 回退、`caught` 回退、最后一档的常量；`KeyboardInterrupt` 照常传出 | `internal_errors` 按 12.4（最后一档只要求不小于 1）；类名对得上，异常的消息不在文档里；最后一档的常量过 `HandlePut` |

   - (a) **模糊，生成器自己写**（`random.Random(种子)`，不加依赖；种子固定并打印，失败时打印种子、序号和输入的十六进制），默认 20,000 例，每例生成时就定下它属于哪一族。A 4,000：任意字节当日志（换行、合法摘要前缀后接垃圾、超长行、深括号）。B 5,000：任意 JSON 值正确封成行（深到 12 层、各种数字记号、带代理码转义和控制字符的字符串、重复键、非对象）。C 8,000：合法事件序列换一个叶子再重封，叶子池是 `10**400`、`1e309`、`NaN`、`-0`、`1.0`、布尔、null、落单的代理码、U+202E、一万字符、深数组、空对象。D 1,500：Python 层的参数对象——重写了 `__eq__`、`__hash__`、`__iter__`、`__len__`、`__str__` 的 `list` / `dict` / `str` / `int` 子类、生成器、藏在合规容器里的这类对象，以及池里的坏 `now`、坏 `logs_unread`。E 1,500：发布的输入——坏 `host`（末尾换行、代理码、65 个字符）、坏 `blocks`（叶子池、深度、超大、平台已知字段的类型不对、键名带那九个敏感词）。每例都断言：两个入口返回而不抛；发布的字节是恰好一个 JSON 对象、过出口那道形状检查、不超过 204,800 字节、没有 null；再加它那一族的断言。
   - (b) **预扫的夹具和真实的校验**。预扫（12.1 的三行规则）：`\"`、`\\"`、`\\\"` 之后跟括号各一条（转义的奇偶）、字符串里的括号、没收尾的字符串、括号前后夹着不合法的 UTF-8 字节（单独的 0x80、0xC0、截断的多字节序列）、恰好 8 层和 9 层——每条的结论写死在夹具里；另对 B 族每一行断言：预扫放行的行，解码不抛 `RecursionError`。校验：四份回退夹具（参数不合规、折叠被捕、发布被捕、最后一档的常量）和从模糊输出里按固定种子抽的 200 份，走第 4 条那条 `HandlePut` 测试，都要 202；形状检查的常数与 `schema.go`、`document.go` 逐个比对；每种事件顶格的合法行不超过 12.2 的行上限。
   - (c) **时间是估的，要量**：模糊 25 秒、整套 120 秒（两个 CPU）是按穷举的速率估的，重封、解码、编码加进来之后未必成立。实现那一轮要报两个 CPU 上的实测时间、各族的例数、最大的那个输入有多大。超了就减默认例数（各族按比例，不删族），全量放到 `RECORDER_FUZZ_N` 后面，和 notice 语料的做法一样，报告里写明默认跑了多少；`RECORDER_FUZZ_SEED` 换种子。静态检查：解码 JSON 的调用只出现在读入模块和发布出口的形状检查里；记录器目录之外只导入两个入口和记账命令；没有超过 800 行的文件。

## 8. 分片

一片是一次实现、统筹方验收、独立复核直到通过；统筹方给的实测数是约 3 小时一片，本文没有另行核对。每片开工前写下停线条件：同一类必须改的问题在第二轮复核里又出现，就停下改形状，不加第三轮（教训第 70、72 行）。`WORK.md` 里 W-66 的估算写的是「记录和状态那一半约 2 片」。这里是 4 片：多出来的是把发事件的一侧、读真实记录各自单独成片（复核 68 和教训第 73 行）。四片之间没有要 Owner 做的事。片 1 在平台仓库加两个只有测试的文件（夹具测试、依赖测试），不带发版。

| 片 | 交付 | 验收 | 不含 |
|---|---|---|---|
| 1 记录、折叠、发布形状、防线 | `agent-config/scripts/recorder/`：事件文件、锁、残尾修复（拣自 `w31/w66-lane-v2`）；记账入口（`open`、`close`、`declare`、`withdraw`、`start`、`finish`、`note`，和 `declared` 事项的 `owner-open` / `owner-ready` / `owner-close`）和写入校验；`fold`；`publish_view` 和上限常数；第 6 节的防线（`RATCHETS.md`、文本扫描、平台的依赖测试）；平台仓库里走 `HandlePut` 的那条夹具测试。纯本机：不起子进程，不访问网络 | 第 7 节第 1、2、3（全部用合成日志）、4、6、7 条 | **任何真实读取**（绑定记录的 `owner-open` 和它对平台的那一次读、`observe` 读平台和集群）；包装器 `run` 和任何命令的改接；看板的改动；**启用向 Console 发布新形状**（`publish_view` 在这一片只对夹具跑） |
| 2 一种本机命令贯通 | `run`、`observe`（只有锁探测和 `observer_round`）、`wait`；只接 `verify-branch.sh` 这一种命令；`board2.py` 对有 `step_id` 的步骤读折叠，标 `source`；`index.html` 加 180 秒的过期覆盖；第 5 节「Console 读哪一份」的前提都成立之后才切换推送 | 第 7 节第 5 条的进程部分；第 3 条里事故 2、`dead` 之后的结束、时钟的端到端部分；一次真实的验收运行，折叠出的和实际发生的逐项对一遍 | 读真实记录；Owner 事项；删旧代码 |
| 3 真实记录 | 三个只读适配：审批、提问（reporter 令牌）、流水线运行（集群只读身份）；绑定记录的 `owner-open`；记录类步骤的观测；`owner_all` 和 `ball` 改由折叠给，`tasks.json` 里的 `needs_you` 和 Owner 步骤迁走。开工先做三次真实的只读读取（一张审批、一个提问、一次运行），核对凭证、字段名、`ci` 运行怎么按提交号找到；有一样对不上，先改本文 | 第 7 节第 3 条的事故 1(b)(c)、关闭、事故 3、Owner 的三条的端到端部分；第 5 条的观测部分 | Console 的改动；删旧代码 |
| 4 其余命令改接，删旧代码 | 实现、复核两条命令改接（只换命令行，不改记录器）；第 5 节列的补丁和函数删掉，`tasks.json` 只留目标和估算 | 观察一个晚上的实际使用：第 1 节的五类错误零次；删掉 `status.json` 重算，内容相同；PROD 的 Progress 页一直显示已同步 | Console 读新字段（`OWNER-SURFACE` 的 P6，在 platform 仓库，带发版单） |

**片 1 的第三轮：输入处理按第 12 节重做。** 前两轮的停线条件是「又有一个输入让折叠或发布抛异常」，复核 88 触发了它。这一轮的验收：第 7 节第 8 条全部；第 2 条 (c) 按封好的字节重做；带 `replaces` 的声明和 `owner_wait_opened` 各是一条事件；复核 88 的八条 P2、第 3 条和第 6 条里标了复核 92、94 的用例各有一条有名字的测试；报告里有两个 CPU 上的实测时间、各族例数和最大的输入；platform 那个只有测试的提交补上 `Change-Id`，带着 `RECORDER_FIXTURES` 实跑的夹具测试输出进报告。这一轮不切换任何页面，不推送这种形状；`run`、`observe` 和运行目录归片 2，但片 1 的折叠已经要接收并校验 `unrecorded`（表 A；复核 94 裁定 ③）。**停线条件（开工前写下；抛异常已由结构排除，它针对的是还会出错的三处）**——下一次复核在提交的代码上给出下面任何一种输入，这条线停下，不加第四轮：(a) 甲、乙、丙三族里测试收进去的输入（回归集、穷举、变异、模糊种子；丁族故意触发保护，不在此列），有一个使 `internal_errors` 大于 0——保护被用到了；或者有一个属于甲族、丙族的——本该算出来——得到了回退文档。乙族的输入得到 `invalid_argument` 回退是正确的结果，不在此列；它没得到这个回退，才算。(b) 任何参数、任何字节、任何 `now`，使两个入口之一抛出 `Exception` 的子类，或返回的字节 `HandlePut` 不回 202。(c) 一个按表 A、表 C 该留下标记的输入，或一份带残尾的日志——工作日志一侧是表 B 第 1–3、6、7 行，观测一侧是第 5、10 行，回退是第 4 行——在**最终发布的字节**上（任何一级缩减）缺了那一行的标记（表 B 开头写明的那一种——工作整个被 30 件的上限截进 `omitted_works`——不算缺）；或者标记在，而那一行「禁止的结论」栏里有一条成立。两样分开判，有标记不等于没说假话。测试没收的合规输入走进了回退，是必须改的缺陷，改完进回归集；同一类第二次出现照本节开头的规矩停线。**给复核方的一句话**：找一个输入——任何参数、任何字节、任何 `now`——让这两个入口抛异常、交出平台不收的字节、在本该算出来的输入上用到保护或走进回退，或者在发布出去的字节上丢了表 B 的一个标记、说出它那一行禁止的一句。

## 9. 第二半（判通过与放行）要满足的约束

本文不设计它。以后任何一份设计至少要满足五条：① 证据不由被检查的一方保管——裁决读的东西（提交内容、验收输出、复核报告）要么由裁决方自己重新取得，要么存在被检查方写不到的地方（另一个用户、沙箱、平台），同一个 Unix 用户名下的文件不算。② 没有自己写的豁免清单——哪些字段可以不查、哪些变化仍算通过，由设计文档给出并逐项过复核，实现者和被检查方都不能加。③ 测试断言用户实际走的出口，即放行时真正被调用的那条命令或接口；放行时重算，不读已经盖上的判词（复核 65）。④ 记录、裁决、放行不在同一个程序里（教训第 77 行）；能问权威的就问，不重算（教训第 69 行）；本文的事件对它只是线索，不是证据。⑤ 它要有自己的设计，先复核设计再实现（教训第 53、62 行），开工前写下停线条件。

## 10. Owner 要定的事

只有一件：**没有记录可对的 Owner 事项怎么处理**。怎么回应是他的工作方式，所以留给他定；其余的选择都是实现上的，按 ADR §12.2 第 15 条由统筹方定并留痕。本设计在两种选法下都能用；他没定之前按 A，对他来说什么都不变。选项 A：允许 `declared` 的事项存在，页面上标明 `Declared by coordinator, not a record`，由统筹线程合上；他照旧可以在线程里回一句。选项 B：能变成记录的就变成记录，他在 Console 或手机上办，页面自己变。**推荐：B 只用于提问和反馈，其余按 A**。原来「在线程里回一句」的问题和反馈，在提问入口可用之后（`OWNER-SURFACE` C1：Agent 侧要新线程才有）改成提问入口的一个问题。**PROD 发布的批准不走这条路**：它仍是审批单；提问的回答不增加任何授权（工作区规则，W-65），把「线程里批一句」改成一个问题等于绕开审批。没有权威记录可对的事——换凭证、在他自己的终端里贴一条命令——保留为 A，明确标成 Agent 声明的。

## 11. 三次复核逐条

只列各条现在的出处；规则本身只在出处那里，这里不复述。

**复核 68**（16 条：8 条必须改、8 条次要；复核 73 判 8 条已解决、7 条部分解决、1 条没解决，没解决完的并进了复核 73 的条目）：1 事故 1 仍可重现 → 第 3 节 `kind` 与 `watch` 的对应、第 4 节记录类的表和事故表第 1 行；2 重开时旧步骤的去向 → 表 A 的 `step_declared` 一行（`replaces`）、第 4 节「被取代不是状态」；3 锁探测误伤记录类 → 表 A 的 `step_seen`、`record_seen` 两行；4 Unknown 与停更 → 第 4 节的 `unknown` 状态和「读的一方自己查快照」、表 B；5 时钟与两个观测方 → 第 3 节的采样时间、互斥范围、逐对象的确认、时钟异常四条；6 真实记录绑定 → 第 3 节「记录类步骤的定位条件」、第 4 节绑定等待的表；7 事故 3 与凭证 → 第 5 节「读取凭证」、第 3 节「逐对象的确认」；8 平台上限没列全 → 第 5 节的限制表、第 7 节第 4 条；9 缩减时有类别没计数 → 第 5 节的保留次序和截断规则、表 B 第 12 行；10 `done`、`landed` 像判词 → 第 2 节「不出判词」、第 5 节「Console 读哪一份」；11 防线的保证写反了 → 第 6 节、第 7 节第 7 条；12 V8 与共享中位数矛盾 → 第 4 节「时间与估算」、V7；13 豁免要逐项 → 第 7 节第 2 条；14 伪造与洪泛 → 第 6 节、第 3 节的上限；15 分片 → 第 8 节；16 Owner 的决定 → 第 10 节。

**复核 73**（13 条：3 条必须改、9 条次要、1 条提示）：1 有事还开着工作却能关闭、`ball` 显示绿色 → 表 A 的 `work_closed` 一行、第 3 节「四个词」、第 4 节 `ball` 逐件判定、V12、第 7 节第 3 条「关闭」；2 `dead → done` 违反 V3 → 表 A 的 `step_finished` 一行、第 4 节进程表后一段、V3；3 删改测试的表和 V7 自相矛盾 → 第 7 节第 2 条、表 A、V7；4 同一个 `ref` 被几件事绑定 → 第 4 节 `owner_all`；5 逐对象的新鲜度 → 第 3 节「逐对象的确认」；6 执行中与终态分开 → 第 4 节绑定等待的表第 1、5 行；7 Console 的 `age_seconds` 不是距生成时间 → 第 4 节「读的一方自己查快照」、第 5 节「Console 读哪一份」；8 `owner_all_cut` 也是计数 → 第 5 节 `owner_all` 的截断规则；9 超过 200 份日志 → 表 C、表 B 第 1 行；10 缩减第 ⑤ 级的契约 → 第 5 节「字节」一条的摘要、表 B 的「发布各级」一栏；11 `declared` 的标签和办理字段 → 第 4 节 Owner 事项的表和它后面一段、第 6 节；12 `reason` 原样输出与固定词表冲突 → 第 4 节「文档里的字分两类」、V10；13 片 1 的边界 → 第 8 节片 1 的「不含」；附注（`other` 包监视脚本）→ 第 4 节事故表第 1 行。

**复核 76**（5 条：1 条必须改、4 条次要；它判复核 73 的 13 条里 10 条已解决、3 条部分解决，剩下的就是这 5 条）：1 V7 与时钟规则 → 第 3 节「时钟异常」、第 4 节两张步骤表的第 5 行和「`unknown` 怎么离开」、V7、第 7 节第 3 条「时钟与观测方」；2 逐件判球用哪一份 `ref` 状态 → 第 4 节 `ball` 开头一段、第 7 节第 3 条「Owner 的三条」；3 `record_created` 没要求确认 → 第 4 节逐件判定表第 1 行；4 `commands` 不发布与「原样保留」冲突 → 第 5 节 `owner_all` 的截断规则、第 7 节第 3 条「事故 4」；5 `after`、`usual_s` 的派生影响 → 第 4 节 Owner 事项的表和「时间与估算」、第 7 节第 2 条 (b)。

## 12. 输入处理：两个全函数入口（复核 88 之后改形状；复核 92、94 之后每条规则只留一处）

片 1 的两轮实现里，复核 81 找到一个、复核 88 又找到三个让折叠或发布抛异常的输入（封好的 `note(by=[])`；`now = 10**400`；标题里一个落单的代理码；一行里一万层数组）。四个是同一类——没人列过的输入——所以这一节不接着列，改形状，让下面这句话由结构保证：**对每一份日志里的任意字节序列和任意 `now`，记录器都返回一份平台的校验接受的文档。坏输入可以让结果说 `unknown`；不能让它抛异常，不能让东西悄悄消失，不能让它说假话（全清、`ball = nobody`、一个数）。** 拆成可以检验的说法。**T1**：两个入口不抛 `Exception`，`publish_total` 返回的字节平台收。**T2**（对折叠出的正常文档；回退文档整份标成没算出来，另按 12.3 验收；发布时被截的工作另有 `omitted_works`）：交进来的每份日志在 `works[]` 里恰好一项，或按表 C 计进 `logs_unread`；每一个完整的行要么是有效事件，要么按表 A 留下 `defects` 或 `log_invalid_at`；残尾按表 B 第 3 行。**四条禁止的结论**——哪个标记在场时禁止哪几条，只在表 B 的最后一栏；折叠出的文档和最终发布的字节都算：**F1** 全清（`owner_all` 为空而 `fold_complete` 为真）；**F2** `ball.holder` 是 `nobody`；**F3** 清单被截而 `incomplete` 里没有 `owner_all`；**F4** 一个确切的数（`fold_complete` 为真，页面就把清单的长度当确切的数；回退文档里另指带了 `works_total` 或 `owner_all_cut`）。

**12.1 两个入口，从第一行到最后一行都在保护里。** 对外只有 `fold_total(logs, observer, now, logs_unread=0) → 文档` 和 `publish_total(document, host=None, blocks=None) → 字节`（推送方原样发出的那一串）；第 4 节的 `fold`、第 5 节的 `publish_view` 是里面的两步，不再对外。读文件、取时钟仍是调用方的事，纯函数的约束不变。**参数只收确切的内建类型**：`logs`、`observer` 是 `list`，每项是 `(str, bytes)` 的 `tuple`（目录名或文件名，字节）；`now` 是 `int` 或 `float`；`logs_unread` 是 `int`；`document`、`blocks` 是整棵树都由 `dict`（键是 `str`）、`list`、`str`、`int`、`float`、`bool` 组成的值；`host` 是 `str` 或 `None`。检查只用 `type(x) is T`，在碰这个值的任何别的操作之前做：子类、生成器、自己带 `__eq__` / `__hash__` / `__iter__` / `__str__` 的对象，在被比较、哈希、迭代、转成字符串之前就被拒，它们的方法一次也不会被调用。结构只从记录器自己的严格解码器来。保护有三档：正文在一个 `try` 里；回退的构造和编码在第二个 `try` 里；再失败就交出**最后一档**——导入时定好的常量，`LAST_FOLD()` 是只含字面量的函数，`LAST_PUBLISH` 是已经编码好的字节，失败的那一刻不用再编码；内容固定（`at` 0、`reason: caught`、没有类名、`internal_errors` 写 1——这个 1 是什么意思，在 12.4）。**捕什么**：`except Exception`，`RecursionError`、`MemoryError`、`OverflowError`、`UnicodeError` 都在内；不拦 `KeyboardInterrupt`、`SystemExit`、`GeneratorExit`，它们来自操作的人和宿主进程，拦了工具就停不下来。异常只留类名：`type(e).__name__` 是 `str` 且整串匹配 `[A-Za-z_][A-Za-z0-9_]{0,63}` 才写进 `error_class`，否则写 `Other`；消息、参数、回溯不进文档，消息里可能带着 Agent 写的字。**保证不了的**：进程因内存被系统杀掉、解释器在 C 层崩溃、断电，没有异常可捕；内存紧到连最后一档的字面量都建不出来，同样没有办法。12.2 的总量、深度、数字三条上限让输入触不到这些。读入时每行另有一个小保护（`read_log` 里），它捕到什么、一行不能用时怎么算，只在表 A。

```
def fold_total(logs, observer, now, logs_unread=0):
    n = 0                                                         # 保护捕到的次数
    try:                                                          # ← 保护从这里起，下面每一行都在里面
        bad = exact_types(logs, observer, now, logs_unread) or bad_number(now) or bad_count(logs_unread)
        if bad: return fallback("fold", "invalid_argument", argument=bad, at=at_or_0(now), n=0)
        read, unread, names = select(logs, observer); views = []   # 表 C：读哪些、按什么次序，与传入的次序无关
        for name, data in read: v = read_log(name, data); views.append(v); n += v.catches   # 每行一个小保护；n 随读随加；列表当场建完，不把生成器带到保护之外
        doc = fold(views, now, logs_unread + unread, names); doc["internal_errors"] = n; encode_strict(doc); return doc   # 编码一次，只为确认本机看板写得出去
    except Exception as e:                                        # ← 到这里止；KeyboardInterrupt、SystemExit、GeneratorExit 不拦
        try: return fallback("fold", "caught", error_class=class_name(e), at=at_or_0(now), n=n + 1)
        except Exception: return LAST_FOLD()
def publish_total(document, host=None, blocks=None):
    n = 0
    try:
        if not exact_tree(document) or not fold_shape(document): return encode(fallback("publish", "invalid_argument", argument="document", n=0))
        n = document["internal_errors"]
        view = with_host(document, ok_host(host)) if "recorder_failed" in document else publish_view(document, ok_host(host), ok_blocks(blocks)); data = encode(view)   # 回退文档只加 host，别的不动；不合规的 host、块不发，在 incomplete 里点名
        if len(data) > 204800 or not shape_ok(data): return encode(fallback("publish", "too_large" 或 "shape", at=document["at"], n=n))   # 这里没有异常；计数的规则在 12.4
        return data
    except Exception as e:
        try: return encode(fallback("publish", "caught", error_class=class_name(e), at=at_or_0(document), n=n + 1))
        except Exception: return LAST_PUBLISH
预扫（12.2 第 5 条）：对正文的每个字节 b 带三个量 in_string、escaped、depth，初值 假、假、0
    in_string 为真：escaped 为真 → escaped = 假；否则 b 是 \ → escaped = 真；b 是 " → in_string = 假；别的字节不动
    in_string 为假：b 是 " → in_string = 真；b 是 [ 或 { → depth 加 1，超过 8 就判 limit_depth 并停下；b 是 ] 或 } → depth 减 1（不低于 0）
```

**写入一侧用同一个读入函数；旧日志不读。** 一条事件写之前过两道：先按 12.2 第 8–10 条查每个字段的值（命令行参数里落单的代理码在这里被拒，不是在编码时抛）；封好之后这一行字节再过一遍读入，得回的必须是同一条事件。哪一道不过都是拒绝并说明原因。`commands.py`、`repair.py`、`estimate.py` 只拿读入函数给的视图（`finish` 的 `run_id` 取自视图里的步骤，已记下的 `repair_id` 取自有效的 `tail_repaired`），原始字典不出读入模块；模块按读入、逐事件校验与归约、步骤状态、清单与球、发布分开，每个文件不超过 800 行。**旧日志**：分支上的实现写的是 `v: 1`，取代是 `declare B` 加 `step_superseded(A, by_step=B)` 两条事件。不迁移，也不按新语义去读：新事件的 `v` 是 2，读入遇到 `v` 不是 2 的行，就是表 A 的「链字段不对」（`bad_version`），页面写 `Log written by an older recorder`，`rec.py` 拒绝往里追加，统筹方照第 3 节把目录挪走另开——旧的取代事件不会被默默当成撤回。依据是还没有要保的日志：实现只到片 1，没有 `run`、没有 `observe`、没接看板；2026-10-11 核对，本机 `~/agent-work/events/` 不存在，`~/agent-work/` 和实现的工作树里除测试的临时目录外没有任何 `events.jsonl`。

**12.2 上限：解码之前，对字节查。** 先定读哪些文件（表 C）。读进来的每一份按换行切成行；最后一个换行之后的字节是残尾，不算日志（原有），它留下的标记在表 B 第 3 行。每一行自上而下查下表第 2–10 条，第一条不合的定代码；这一行因此怎么算，只在表 A。

**表 C：多文件输入的身份和次序**（V8 的置换靠它成立）。名字是调用方给的 `str`（不是的话整个调用是参数回退，12.1）。先拿名字整串去匹配格式，不合的当场拒读——在任何解码、排序、比较之前，也不拿「把坏字符替换掉之后」的名字去比。

| 输入 | 键：完整的合法名字 | 重名 | 次序和上限 | 没读的记在哪 |
|---|---|---|---|---|
| 工作日志 | 目录名，整串匹配 `work_id` 的格式（实现里的 `[A-Za-z0-9][A-Za-z0-9._-]{0,79}`） | 同名的几项**全部**拒读，每一项计一份；从不留「先遇到的」那一个 | 按名字的字节序升序，读最长的一段前缀：不超过 200 份，连同观测文件合计不超过 64 MiB | 顶层 `logs_unread` = 调用方给的份数 + 名字不合的 + 重名的每一项 + 排在前缀之后的。能点名的（重名的、前缀之后的）按同一个次序进 `logs_unread_names`，至多 20 个；调用方那几份和名字不合的只有数 |
| 观测文件 | 文件名，整串匹配 `<UTC 日期>-<四位序号>.jsonl` | 同上：全部拒读，每一项计一份 | 先于工作日志算；按名字从新到旧读，合计至多 16 MiB；读进来的按名字升序把有效的轮接成一列，「最近一轮」是这一列的最后一个 | `observer.files_unread` = 名字不合的 + 重名的每一项 + 16 MiB 之外的。调用方没有预选观测文件的参数，目录里的都交进来 |

| # | 查什么 | 值 | 不合时的代码 |
|---|---|---|---|
| 1 | 读哪些文件、按什么次序、没读的记在哪 | 表 C | 表 C |
| 2 | 一份日志 | 16 MiB、20,000 行 | `limit_log`，落在第一条没读的行上 |
| 3 | 一行的长度 | 131,072 字节（顶格的 `observer_round` 约 52 KiB） | `limit_line` |
| 4 | 行的外形：64 位小写十六进制、一个空格、正文；摘要等于正文的 SHA-256 | — | `bad_line`、`bad_digest` |
| 5 | 嵌套深度：按 12.1 的三行规则扫一遍正文的字节 | 8 层（合法事件最深 3 层） | `limit_depth`，不解码 |
| 6 | UTF-8；严格的 JSON（`NaN`、`Infinity` 不是 JSON）；没有重复的键；值是一个对象 | — | `bad_utf8`、`bad_json`、`dup_key`、`not_object` |
| 7 | 链字段：`seq` 是整数、等于行号；`prev_sha256` 在第一行是空串，其余是上一行的摘要（64 位小写十六进制）；`v` 恰好是整数 2（`true`、`2.0` 不算） | — | `bad_chain`、`bad_version` |
| 8 | 每一个数 | 整数记号 \|n\| ≤ 2^53；带小数点或指数的记号有限且 \|x\| ≤ 2^53；超过 17 个字符的整数记号和 `1e309` 这样溢出的记号不做转换，直接算超范围；`-0`、`-0.0` 当 0；布尔不是数；要整数的字段不收 `1.0` | `bad_number`、`bad_type` |
| 9 | 每一个字符串，键也算 | 只含 Unicode 标量值（没有落单的 U+D800–U+DFFF）；不含 U+0000–U+001F、U+007F–U+009F、U+2028、U+2029、U+202A–U+202E、U+2066–U+2069；码点数不超过第 3 节的上限 | `limit_text` |
| 10 | 字段集合、类型、闭合取值、与之前事件的关系（第 3 节）。null 不是任何字段的合法值：`exit.code`、`exit.signal` 写成 null 无效，`signal` 是空串当没写。格式（`work_id`、各种 id、观测的键）一律整串匹配，末尾多一个换行不算匹配 | — | 各自的代码 |

**为什么这样就够，不靠再列一种输入。** 表 C 为什么用名字：它是入口手里唯一不属于内容的键——整串校验过，不用解码任何一行，日志里写什么都抬不高它（事件里的时间可以写到将来，文件可以灌大）。留下哪一批不影响真话（表 B 第 1 行），只影响有用；「留下的是最近在动的」是调用方的事（第 3 节；复核 94 裁定 ①：入口保持无序，不加修改时间的参数），入口这一层是不信调用方时的兜底，正常运行时截不到东西。深度：预扫数到的层数不少于解码器会递归的层数——解码器只在字符串之外遇到 `[`、`{` 才往下一层，在第一个语法错处停下；`"`、`\` 和括号这几个字节在 UTF-8 里不会是多字节字符的一部分，所以预扫对不合法的 UTF-8 也给出同一个上界。过了第 5 条，解码最多递归 8 层，与解释器的递归上限和调用时的栈深无关；折叠里沿 `after`、`replaces` 的走法用循环，不用递归。选预扫、不选「交给保护去捕 `RecursionError`」：后者让同一行字节在不同的递归上限下得到不同的文档，而且每一次都算进 `internal_errors`。数字：过了第 8 条，事件里的数和 `now` 都是 \|x\| ≤ 2^53 的整数或有限浮点；折叠只做加、减、比较、乘 1.5、两数取平均，不溢出，不出 NaN。字符串：文档里的字符串只有两个来源，过了第 9 条的引语和折叠自己写的固定代码，编码不会失败；`host` 和附加块在发布里过同样的规则（第 5 节）。这几条论证各自漏了什么，由保护接住并计数，不会变成异常。

**12.3 回退文档：记录器说「我没算出来」。** 两种，分清。**参数回退**（`reason: invalid_argument`）：调用方给了不合规的 `now` 或别的参数，回退就是这次调用的正确结果。**记录器自己的失败**：`caught`（整体保护捕到了异常）、`too_large`、`shape`（出口自检不过，没有异常）。哪一种计进 `internal_errors`，只在 12.4。形状固定，下表之外没有别的字段；四份夹具过平台真实的校验（复核 92 按 `schema.go`、`document.go`、`recorder.go` 的源码核对过这个形状会被接受，`HandlePut` 还没有实跑）。**今天的两个读者都不认得它，会读成没事**（复核 92 核对；上一稿说旧读者会读成「至少 0」，是错的）：platform main 的 Console 仍读 `owner_now`，`AgentWorkBoard.tsx:84` 会写 `Nothing is waiting for you`；本机 `index.html` 约第 400 行把空清单写成「现在没有，后面也没有排到你的事」，约第 721 行在没有未关闭的工作时写「都做完了」。所以回退文档、不完整的文档、有日志没读的文档只能交给过了这三类夹具的页面（第 5 节的第四样）；片 1 不切换任何一页。页面认得之后：Console 上绑定记录的事项照旧读平台自己的记录（第 6 节、P6），回退期间待批的单照样看得到，看不到的只有 `declared` 的事项，页面写明；回退文档照常推送，不推的话 Console 会把上一份好的文档显示到 180 秒过期，却说不出原因。`recorder_failed` 加进 `ball.why` 的固定清单。

| 字段 | 值 | 认得它的页面怎么读 |
|---|---|---|
| `recorder_failed` | `{stage, reason, argument, error_class}`：`stage` 是 `fold` / `publish`；`reason` 是 `invalid_argument` / `caught` / `too_large` / `shape`；`argument`（`now` / `logs_unread` / `logs` / `observer` / `document`）只在 `invalid_argument` 时有，`error_class` 只在 `caught` 时有 | 最上面写 `The recorder could not compute the board`，带原因；下面各块一律不当作现状 |
| `at`、`ball`、`fold_complete` | `now` 合规就是它，否则 0（不取时钟）；`{holder: unknown, why: recorder_failed}`，没有 `since`；`false` | 不写「这是 <时间> 的情况」；球是 Unknown |
| `owner_all`、`works`、`feed`，和各种数 | 三个都是 `[]`，名字都在 `incomplete` 里；`works_total`、`omitted_works`、`owner_all_cut`、`logs_unread`、`observer`、`clock` 都不出现 | 那个数显示 `Unknown`，不显示 0；列表处写 `Not computed`，不写「没有工作」 |
| `internal_errors`、`observations_valid_s`、`full_at`、`host` | 次数（12.4）；180；`local_board`；合规才带 | 大于 0 标 `Recorder internal error` |

**12.4 保护不是借口；与原有约束的交界。** `internal_errors` 是保护捕到的**次数**：读入的小保护每捕一次加一，整体保护捕到加一，发布把折叠给的数带过去再加自己的（两份日志各捕一次、发布再被捕一次，是 3）；参数回退和 `too_large`、`shape` 没有捕获，不加。**唯一的例外**是最后一档的常量：它写 1，意思是「至少一次」——这一档连次数也给不出——验收只要求它不小于 1，不要求等于累计的次数。正常文档里它大于 0 时另有 `internal[]`，至多 5 项 `{stage, work_id, line, error_class}`（没有的不写）；回退文档不带这个列表，类名在 `recorder_failed.error_class`。它在发布各级怎么留，在表 B 第 11 行。每一次都是边界漏分类的一个输入或折叠里的一个错，是缺陷，不是正常路径：第 7 节第 8 条在甲、乙、丙三族上都断言它为 0，丁族断言保护确实接得住。三处交界。**纯函数**：被保护捕到的失败可能取决于环境（内存、递归上限），所以「同样的输入得到同样的文档」和 V2–V12 对 `internal_errors` 为 0 的文档成立；12.2 的上限就是为了让输入碰不到环境。**V5**：只对表 A 里结果是「这一行不存在」的行成立，末三行（断链）不在内。**V1**：「不抛异常」加强为本节开头那句话（T1），对任何输入成立；V1 里「没有 `recorder_failed`」那半句只对参数合规的输入说。回退文档没有工作和清单，不在 V2–V9、V11、V12 的范围内，只受 12.3 的表、T1、V10 和表 B 第 4 行约束；`now` 仍是唯一的时间来源，取不到合规的 `now` 就写 0。

## 13. 复核 94 逐条（`~/agent-work/codex-review-94/REPORT.md`，结论「先改」；三条 P1 都出在同一条规则在几节里各说一遍）

| # | 复核 94 说的 | 去了哪 |
|---|---|---|
| P1-1 | 包装器声明之后开始事件的字段无效：第 3 节说留在 `waiting`，第 4 节说 `unknown`；「`alive: false` 把 `unknown` 改成 `dead`」没有限定在有有效开始的运行上 | 表 A 的 `step_started`、`step_seen`、`step_finished` 三行是唯一的出处。第 3 节原来那句「无效的 `step_started` 让这一步留在 `waiting`」和「没记上开始的运行」一条删了；第 4 节进程表第 3 行、「`unknown` 怎么离开」的开头和 `start_not_recorded` 一行改成引用 |
| P1-2 | 重名拒读只写在工作日志的规则里；两个同名的观测文件交换次序会改变最后一轮 | 表 C，工作日志和观测文件同一条规则。12.2 第 1 条、第 3 节上限一句和观测日志一句、V8、伪代码的注释都改成引用；置换夹具在第 7 节第 3 条 |
| P1-3 | 有效的 `work_opened` 后接没换行的 `owner_wait_opened`：残尾丢了，`fold_complete` 仍为真、清单确切为 0；摘要里连 `torn_tail` 都不留 | 表 B 第 3 行。第 4 节「折叠不完整」一段、第 5 节摘要的字段和「每一级都留着的」、F1–F4 的适用范围、停线条件 (c) 都改成引用表 B；用例在第 7 节第 6 条 |
| P2-1 | 最后一档常量的 `internal_errors: 1` 与「恒为次数」冲突 | 12.4（次数的定义和那一个例外）；12.1、12.3、丁族改成引用 |
| P2-2 | 工作日志重名要「全部拒读」；坏名字先拒再排；缺置换测试 | 表 C；第 7 节第 3 条的五个置换夹具（含调用方的 `logs_unread` 与入口拒读数相加） |
| P2-3 | 停线 (a) 没排除丁族；(c) 的标记清单缺观测一侧 | 第 8 节：(a) 写明丁族不在此列；(c) 按工作日志、观测、回退三个来源引用表 B 的行 |
| P2-4 | 没记下开始的 `process` 步骤没有 `command` 的来源 | 第 4 节进程表后一段里 `command` 的那一句；第 5 节引用它 |
| 裁定 | ① 入口保持无序，近期归调用方，它的遗漏数要保留；② 起命令前有界重试，不接受没有开始的结束；③ 目录名归适配层，片 1 的折叠就要校验 `unrecorded` | ① 表 C 最后一栏、12.2 表后；② 第 5 节 `run`、表 A 的 `step_finished` 一行；③ 第 3 节目录结构的注释、第 5 节 `observe`、表 A 的 `observer_round` 一行（三个列表之间的冲突规则）、第 8 节 |

复核 88（十六条）和复核 92（P1 三条、P2 七条、P3 一条、裁定三条）的每一条都已采纳，或并进了后来的修改：复核 94 判 92 的 P1-1 关闭，P1-2、P1-3 部分关闭（并进上表的 P1-2、P1-1），P2-3、P2-7 部分采纳（并进上表的 P2-1、P1-3），其余采纳。
那两次复核的逐条对照不再单列：它们指向的规则，现在的出处是表 A、表 B、表 C 和第 12 节。
