# W-66 派工流水线第二版规格：只判定和记账，不管进程

状态：规格第二稿，2026-10-11。Owner 已同意做第二版；无人值守由统筹方定为方案 A（第 12 节）。本稿并入复核 23（`change first`：四条 P1、五条 P2）的全部意见。没有代码；第 13 节的前置条件逐条核对、结果写回本文之后才派第一片的实现。
输入：`WORK.md` 的 W-66；`work/multi-agent/reviews/` 里的复核 16、17、20（第一版 `lane.py`，三次「先修」，没有合并）；复核 21（第二版设计，`sound with changes`）；复核 23（本规格第一稿）；`ADR-ops-architecture.md` §12.2 第 13 条。
已定、本文不重新讨论：lane 只判定和记账，不结束进程、不处理进程组、不接续旧进程、不自动重跑，没有 `retry`，没有会发信号的 `stop`。判词只增不改，复核过的轮不再复核；「先修」和有效的验收 FAIL 只能经下一轮出去。`max_rounds` 默认 2，统筹方每条 lane 只能延一次，再延只能 Owner 在终端做。

## 1. 范围与不做的事

- **做**：一条 lane 把一件事按固定顺序走 `implement → verify → review`。每一步只做三件事：起一个进程、等它结束、记下退出码和产物。一个纯函数按记录判定这一轮。预算、队列、看板都从事件算出来。
- **不做**：不发任何信号；不读、不信、不等待磁盘上记的旧 PID；不重跑任何步骤；不合并、不看主线 CI、不发布（第 11 节）。
- **接受的边界（只说这一次）**：所有进程是同一个 Unix 用户，都能改写 lane 目录里的任何文件。本设计防的是失误、陈旧或半写的文件、以及统筹方悄悄绕开判词；不防恶意进程。真正的边界要等 Agent 换用户或进沙箱（ADR §12.3 的 `agentd`）。
- **不管进程的代价**：① 失控的实现者、挂住的复核者没有程序去结束，额度会一直消耗到人来；② 驱动死掉的那一步只能判未成功，哪怕它其实做完了，代价是一轮；③ 额度用尽、断网、复核报告被截断这类失败同样消耗一轮；④ 每次执行一份全新检出，多花磁盘和依赖安装时间。

## 2. 身份与产物协议

```
~/agent-work/lanes/<lane_id>/                 # 根目录可用 --root 改
  lane.json   lock   events.jsonl             # 创建参数（只写一次）· flock · 只追加
  events.torn-<UTC>-<随机>                     # 修复时挪出来的残尾（见下）
  r<round>/brief-<随机>.md                     # 开轮时复制的任务书
  r<round>/<step>-<attempt_id>/               # 独占 mkdir；已存在就拒绝启动
    rec/intent.json   rec/manifest.json       # lane 自己的记录，路径不传给子进程
    out/stdout   out/stderr   out/report      # 产物
    work/<repo>/                              # 这次执行独占的检出，也是子进程的 cwd
```

- **身份**：`exec = {lane_id, round, step, step_index, attempt_id}`，`attempt_id = <UTC 时间>-<8 位随机十六进制>`。每轮每步只有一次 attempt；`attempt_id` 的用处是让目录和引用不能被复用，不是给重试留位置。
- **事件**：`events.jsonl` 每行是 `<正文的 sha256> <正文 JSON>` 加换行，正文带 `seq` 和上一行的 `sha256`（与 DESIGN 7.3 的哈希链同形），在 lane 锁内一次写入并 fsync。一行算完整，要以换行结尾、且行首的摘要与正文相符。没有可改写的状态文件：状态由 `lane_state(事件, 证据, 驱动是否在)` 这一个函数算出，所有命令和只读视图都调它。
- **残尾修复**：只有最后一行可以不完整（追加到一半时崩溃）。改状态的命令拿到锁之后、做任何别的事之前：① 把残尾原样写进 `events.torn-<UTC>-<随机>`（独占创建，fsync）；② 把 `events.jsonl` 截到最后一条完整行的末尾并 fsync；③ 对每个还没有被事件提到的 `events.torn-*` 追加一条 `tail_repaired{file, bytes, sha256}`。在任何一步之后崩溃，重做一遍结果相同。残缺的那条事件算没有写过，状态落回它之前的边界（下面的边界表）。不是最后一行的坏行、`seq` 跳号、链对不上，程序不修：整条 lane 是 `unknown`（`event log invalid at seq <n>`）。
- **锁与读取**：改状态的命令从读事件之前到最后一次写之后独占 `lock`；`run` 整个驱动期间持有；锁的文件描述符不传给子进程。只读命令（`status`、`queue`、`pass-set`）读的时候不拿锁，也从不修复：事件文件只追加，它们读到最后一条完整行为止；manifest 发布后不再改，只读被事件引用的。判断驱动在不在，只做一次不等待的共享锁尝试，拿到立刻放掉。所以驱动持锁几个小时也不挡读。改状态的命令遇到锁被占，重试 2 秒再报被占，避开读取方那一瞬间的探测。
- **持久创建的顺序**：`new`：独占建 lane 目录 → 建 `r1/`，任务书经临时文件 fsync 后 rename，fsync `r1/` → `lane.json` 同样发布 → `events.jsonl` 带 `lane_created`、`round_opened` 两行，经临时文件 fsync 后 rename → fsync lane 目录 → fsync 根目录。`events.jsonl` 出现之前这条 lane 不存在。`next-round`：建 `r<n>/`（已存在不算错）→ 任务书发布，fsync `r<n>/` 和 lane 目录 → 追加 `round_opened`。attempt：独占建目录及 `rec/`、`out/`、`work/` → fsync 该目录和 `r<n>/` → 之后照下表。intent 和 manifest 都经临时文件发布，只有被事件引用且摘要相符才算数；没有被 `step_intent` 引用的 attempt 目录是孤儿：不读、不复用、不删除。macOS 上 fsync 用 `F_FULLFSYNC`。
- **配置固定**：`lane-config.json` 和它 `pinned_files` 里列的脚本（例如 `~/agent-work/verify-branch.sh`）在 `new` 时记 `sha256`，每一步启动前重算；变了就拒绝启动（`<file> changed since the lane was created`）。后果见第 12 节第 2 条。

| 时点 | 做什么（前一项落盘后才做后一项） |
|---|---|
| 启动前 1 | 建 attempt 目录；按第 3 节建 `work/` 检出并做启动前检查 |
| 启动前 2 | 发布 `rec/intent.json`：`exec`、步骤顺序、`argv`（数组，占位符只在元素内替换，`shell=False`）、`cwd`、任务书的路径 / 长度 / `sha256`、配置和固定文件的 `sha256`、仓库清单、本步消费的 SHA 集合及其来源 manifest 的摘要、启动前检查的结果、工具链版本、`limit_seconds`、环境变量名（不记值）、驱动 pid |
| 启动前 3 | 追加 `step_intent{exec, intent_sha256}`。启动前检查不过就不启动，直接到「结束后 3」，manifest 写成「未启动」形状 |
| 启动 | `out/` 必须为空；`out/stdout`、`out/stderr` 各用 `O_CREAT\|O_EXCL` 打开，不追加、不合流；子进程在新会话里启动，环境加 `LANE_EXEC=<exec>`；随后追加 `step_started{exec, pid, lstart, started_at, limit_seconds}` |
| 结束后 1 | 退出码只取 `wait()` 的返回值（负值记成信号）。没有任何 `done` 文件被读回来做判定 |
| 结束后 2 | 关闭并 fsync 输出；implement 做固定，verify / review 做结束后的不变性检查（第 3 节）；`stdout`、`stderr` 记长度和 `sha256`；`report` 只有 review 有：此刻不存在就记 `present: false`，存在则必须是普通文件并记长度和 `sha256`；取出判定字段：verify 的 stdout 最后一条非空行；review 报告按 `utf-8-sig` 读，取第一条和最后一条非空行（去首尾空白）；P1/P2/P3 计数只作展示 |
| 结束后 3 | 发布 `rec/manifest.json`（临时文件 → fsync → rename → fsync `rec/`） |
| 结束后 4 | 追加 `step_recorded{exec, manifest_sha256}`；随后求一次判定，有终局结果就追加 `verdict`（第 4 节） |

manifest 只有两种合法形状，判定函数不用猜。**已运行**：`not_started` 为 null；`exit` 必有，`code` 和 `signal` 恰好一个非空；`termination`（本片恒为 `exited`）、起止时间、产物表、检查结果、判定字段齐全；implement 另有它固定下来的 SHA 集合和 `notes`。**未启动**：`not_started{check, repo, reason}` 非空；`exit`、`termination`、`started_at`、结束后的检查、判定字段全是 null，产物表为空（输出文件没有创建过）。两种都不是，就是证据无效。

发布边界：在某一步之后、下一步之前崩溃，看到的是这一格。每一格都有崩溃测试（T47）。

| 边界 | 崩溃的位置 | 之后看到的 |
|---|---|---|
| B1 | `new`：`events.jsonl` rename 之前 | lane 不存在；目录是残留：`new` 同名拒绝，`status` 显示 `incomplete lane directory` |
| B2 | `next-round`：任务书已发布，`round_opened` 未追加 | 状态不变，轮次没有消耗；重跑 `next-round` |
| B3 | attempt 目录或 intent 已建，`step_intent` 未追加 | `ready`；目录是孤儿；没有启动过任何进程 |
| B4 | `step_intent` 已追加，`step_started` 未追加 | `start_ambiguous` |
| B5 | `step_started` 之后，等待中 | `unknown` |
| B6 / B7 | `wait()` 返回后 manifest 未发布 / manifest 已发布而 `step_recorded` 未追加 | `unknown`（只有临时文件 / 没有被事件引用） |
| B8 | `step_recorded` 已追加，`verdict` 或下一步的 `step_intent` 未追加 | 判定是「继续」：`ready`；有终局结果：`verdict_pending`（第 5 节） |
| B9 | 任何一条事件追加到一半 | 残尾被下一条改状态的命令修复；等同于那条事件之前的边界 |
| B10 | 修复中：副本已写未截断 / 已截断未记 `tail_repaired` | 重做修复；日志有效 |

判定函数只读被事件引用的 manifest，不读日志正文、不读工作目录、不找「最新的一份报告」。未知和无效永远不通过；摘要用来发现错配和事后变动，不是防伪。「记录时就没有」和「记录后丢了」是两回事：

| 看到的 | 含义 | 怎么关（第 6 节） |
|---|---|---|
| 有 `step_intent`，没有 `step_recorded`，锁空着（B4–B7） | 结果未知：`unknown` 或 `start_ambiguous` | `resolve --kind failed\|cancelled` |
| 已有 `step_recorded`，但 intent 或 manifest 丢了、摘要与事件不符、形状不合法、`exec` 对不上；或 manifest 记着存在的产物后来缺失、长度或摘要不符 | 判词之前：`unknown`，`evidence invalid: <step> <which>`。判词之后：判词不改，否定判词照旧，`passed` 不再可用（`pass-set` 拒绝，`evidence changed after the verdict`） | 判词之前：`resolve --kind evidence-lost`。之后不需要 |
| manifest 记着报告在结束时就不存在（`present: false`） | 不是未知，是记下来的事实：判定表第 12 行，`step_failed` | 不需要 |
| 事件日志中段无效 | `unknown`，`event log invalid at seq <n>` | 程序关不了，只能 `abandon` |

## 3. 验收和复核的对象

- **仓库清单与基线**：`lane.json` 列出验收会读到的每个仓库，各标 `change`（会有改动）或 `context`（只被依赖）。每个仓库的目标基线是 `new` 时把 `target_ref` 解析出来的提交号，记进 `lane_created`，整条 lane 不再变。
- **检出的做法（三步都一样）**：每个 `work/<repo>` 是 `git init --template=<lane 建的空目录>`，再 `git fetch --no-tags <来源目录> <完整提交号>`，再 `git checkout --detach <提交号>`（implement 另建 lane 分支）。来源：implement 第一轮是 `lane.json` 登记的来源仓库，以后各轮是最近一次固定出 SHA 集合的那一轮的 implement `work/<repo>`；verify 和 review 是本轮 implement 的 `work/<repo>`。fetch 走打包传输：对象按内容校验后存进这份检出自己的对象库，没有硬链接，没有 `alternates`（建好后检查 `objects/info/alternates` 不存在）。不用 `git clone`：本地克隆会硬链接对象、继承 `alternates`、复制并运行模板里的 hooks（第 13 节第 1 条实测）。
- **git 的调用环境（lane 的每一次 git 调用）**：环境从空表建起，只带 `PATH`、`LC_ALL=C`、指向空目录的 `HOME` 和 `XDG_CONFIG_HOME`，加上 `GIT_CONFIG_GLOBAL=/dev/null`、`GIT_CONFIG_SYSTEM=/dev/null`、`GIT_CONFIG_NOSYSTEM=1`、`GIT_NO_REPLACE_OBJECTS=1`、`GIT_TERMINAL_PROMPT=0`。因此 `GIT_DIR`、`GIT_WORK_TREE`、`GIT_INDEX_FILE`、`GIT_OBJECT_DIRECTORY`、`GIT_ALTERNATE_OBJECT_DIRECTORIES`、`GIT_COMMON_DIR`、`GIT_NAMESPACE`、`GIT_TEMPLATE_DIR`、`GIT_EXEC_PATH`、`GIT_CONFIG_COUNT`、`GIT_CONFIG_KEY_*`、`GIT_CONFIG_VALUE_*`、`GIT_CONFIG_PARAMETERS`、`GIT_GRAFT_FILE`、`GIT_SHALLOW_FILE`、`GIT_REPLACE_REF_BASE` 一个都不继承。每次调用带 `-c core.hooksPath=/dev/null -c core.fsmonitor=false -c core.excludesFile=/dev/null -c core.attributesFile=/dev/null -c gc.auto=0 -c maintenance.auto=false -c fetch.fsckObjects=true`。任何一条 git 命令非零退出都算检查失败。
- **替换对象和嫁接**：读来源仓库之前先查三项：`refs/replace/` 下有引用、存在 `info/grafts`、是浅仓库（`rev-parse --is-shallow-repository`）。任何一项成立就拒绝，原因 `<repo> has replace refs or grafts`（implement 固定时是 `step_failed`，建检出时是未启动）。固定时的树号在禁用替换的环境里读；检出建好后，在它自己的对象库里再读一次 `<提交号>^{tree}`，必须等于记下的树号，否则未启动（`tree of <sha> differs from the pinned tree`）。

三步的检查不是同一种。「干净」指 `git status --porcelain=v1 --untracked-files=all --ignore-submodules=none` 为空；「隐藏标记」指 `git ls-files -v` 首列出现小写字母或 `S`（`assume-unchanged`、`skip-worktree`）。

| 步骤 | 启动前 | 结束后 |
|---|---|---|
| implement | **基线检查**：每个仓库 `HEAD` 等于期望的起点（`change`：第一轮是目标基线，以后是上一次固定的提交；`context`：目标基线）；工作树干净；没有隐藏标记 | **固定**：读每个仓库 `HEAD` 的提交号和树号，这就是本轮的 SHA 集合，写进 manifest。`change` 仓库有新提交是正常结果。`context` 仓库的 `HEAD` 不是目标基线 → `step_failed`（`context repository <repo> moved`）。所有 `change` 仓库都还在目标基线 → `step_failed`（`implement produced no commit`）。结束后**不查**工作树是否干净 |
| verify、review | **不变性**：本步消费的集合就是本轮 implement 固定的集合（按 manifest 摘要引用）；每个仓库 `HEAD` 等于固定的提交、树号相符、工作树干净、没有隐藏标记 | **不变性**：同样几项再查一次；`work/PINNED.json`（在仓库之外，列出提交和目标基线，供复核者取 diff）不算在内 |

- **没提交的改动只是提示（全文只有这一个说法）**：implement 结束时工作树里没提交的改动、未跟踪的文件、被忽略的文件、隐藏标记都不属于本轮，也进不了后面的检出（那里只取提交）。manifest 记 `notes`：`uncommitted changes in <repo> are not part of this round`，`status` 显示，判定不看它。一个提交都没有的情况由上表「没有新提交」那条拦住。
- **子模块**：规则是递归固定：固定提交的树里每个 gitlink（mode 160000）按它记录的提交检出、记进 SHA 集合、按同样的规则检查。工作区各仓库今天都没有 `.gitmodules`（2026-10-11 查过），所以第一片只做检测：固定时发现树里有 gitlink，判 `step_failed`（`submodule at <path>: recursive pinning is not implemented`）。
- **被忽略但构建需要的输入**：检出建好时不存在任何被忽略的文件。依赖由验收命令在检出里按已跟踪的锁文件重建（`verify-branch.sh` 用 `npm ci`；Go 按 `go.sum`）。工具链版本（`git`、`go`、`node`、`npm`、`python3` 的版本输出）记进 intent。其余必须的被忽略文件要在配置的 `inputs` 里逐个声明来源和 `sha256`，由 lane 复制并记录；第一片 `inputs` 只允许为空，缺文件时验收自己会失败，这是看得见的失败。主机上共享的 npm、Go 缓存不在检出内，靠锁文件里的校验和约束；这一点接受。
- **通过绑定的是提交**：`passed` 记的是 SHA 集合。amend、rebase、cherry-pick 之后即使树相同也是另一个提交，没有通过记录，要走新一轮。
- **否决过的 SHA 集合不再复核**：一个集合记为「已否决」，当且仅当有一份已记账的 review manifest 消费了它，并且 `report_first_line` 恰好是 `VERDICT: fix first`。不看退出码，也不看报告是否完整：否定的文字从宽采信，肯定的文字只在完整契约下采信。之后任何一轮固定出这个集合，判 `step_failed`（`no new commit since round <n> said fix first`）。其余没有判词的复核不登记：崩溃、被限流、没有报告、报告被截断而首行不是否决。下一轮可以固定出同一个集合再复核一次，代价是一轮，受预算约束。验收 FAIL 之后同一集合同样可以在下一轮再验。
- **给合并闸门的接口**：`lane.py pass-set <id> --json` 只在状态是 `passed`、且全部证据此刻重算摘要仍相符时输出 `{lane_id, round, verdict_seq, config_sha256, repos: {<repo>: {commit, tree, target_ref, target_sha}}, manifests, events_head}`，否则非零退出并给出原因。合并闸门只能用这里的提交号，不读分支头；合并当时再调一次。目标基线没动、并且是快进到固定的提交，合并结果就是验过的树；否则（基线动了、产生合并提交、rebase、squash）合并结果是新的提交，要自己先过一次验收。**合并闸门不在第一片**：第一片里从 `passed` 到合并之间的窗口没有被程序封住，由统筹方照这一条手工做。

## 4. 判定函数

`decide(round_evidence) → (结果, 原因)`，没有读写、没有子进程、没有时钟；它只在没有驱动持有这一步时求值。输入只有：三步各自的证据（`absent` / `invalid(which)` / manifest 的字段，形状见第 2 节）、本轮步骤上的人工补记、以及从事件和已记账的 review manifest 里取的「已否决的 SHA 集合」。按步骤顺序求值，每一步自上而下取第一条命中的；执行失败排在任何成功文本之前。

| # | 条件 | 结果 | 原因文本 |
|---|---|---|---|
| 1 | 人工补记 `failed`、`cancelled` 或 `evidence-lost` | `step_failed` | `<step> closed as <kind> by <operator>: <reason>` |
| 2 | 证据 `absent`（步骤已有 `step_intent`；驱动还在时不求值，状态是进行中） | `unknown` / `start_ambiguous` | `<step> result is unknown` / `started or not is unknown; no pid recorded` |
| 3 | 证据 `invalid` | `unknown` | `evidence invalid: <step> <which>` |
| 4 | `not_started` 非空（启动前检查不过、取不到提交、来源有替换对象或嫁接、树号对不上） | `step_failed` | `<step> did not start: <not_started.reason>` |
| 5 | `termination` 不是 `exited` | `step_failed` | `<step> <timed_out\|cancelled> by the executor` |
| 6 | `exit.signal` 非空 | `step_failed` | `<step> ended by signal <n>` |
| 7 | implement、review 的 `exit.code ≠ 0`；verify 的不在 {0, 1} | `step_failed` | `<step> exited <n>` |
| 8 | verify、review：结束后的不变性检查不过，或消费的集合不是本轮 implement 固定的集合 | `step_failed` | `snapshot of <repo> changed during <step>` / `hidden index flag in <repo>` / `<step> ran on a different SHA set` |
| 9 | implement 的固定：读不出提交号或树号；来源有替换对象或嫁接；树里有 gitlink；`context` 仓库动了；没有任何 `change` 仓库离开目标基线；集合已否决 | `step_failed` | `cannot pin <repo>: <git error>` / `<repo> has replace refs or grafts` / `submodule at <path>: …` / `context repository <repo> moved` / `implement produced no commit` / `no new commit since round <n> said fix first` |
| 10 | verify：`stdout_last_line` 等于 `VERDICT: FAIL` 或以 `VERDICT: FAIL (` 开头 | `verify_failed` | 那一行原文 |
| 11 | verify：`exit.code = 1` 而没有 FAIL 行；或 `exit.code = 0` 而末行不是恰好 `VERDICT: pass` | `step_failed` | `verify exited 1 without a FAIL verdict` / `verify produced no verdict` |
| 12 | review：记录时报告不存在（`present: false`）或 0 字节；末行不是恰好 `END OF REPORT`；首行不是两种判词之一 | `step_failed` | `review produced no report` / `review report is truncated` / `review produced no verdict` |
| 13 | review：首行恰好 `VERDICT: fix first` | `changes_requested` | `fix first (P1 <a>, P2 <b>, P3 <c>)` |
| 14 | 三步都没有命中 1–13，且 review 首行恰好 `VERDICT: safe to merge` | `passed` | `round <n> passed for <短 SHA 集合>` |
| 15 | 当前步没有命中，后面还有步骤 | 继续下一步 | — |

**完整的放行契约**就是第 14 行的前提：三份 manifest 都在、都有效、都是「已运行」形状；三步 `termination = exited`、没有信号、退出码为 0；implement 的基线检查通过，固定出的集合完整，`context` 仓库都在目标基线，至少一个 `change` 仓库有新提交，集合没有被否决过；verify 和 review 消费的正是这个集合，启动前和结束后的不变性检查都通过；verify 的 stdout 末行恰好 `VERDICT: pass`；review 的报告在记录时存在且完整，首行 `VERDICT: safe to merge`，末行 `END OF REPORT`；没有任何人工补记。implement 结束时工作树是否干净不在契约里（第 3 节）。

**落判词**：`unknown`、`start_ambiguous` 和「继续」之外的结果追加成 `verdict{round, 结果, 原因, SHA 集合, 各 manifest 摘要}`。求值没有副作用，同样的证据永远得到同样的结果，所以谁来落、什么时候落都一样；本轮已有判词就不再落。

## 5. 状态与转换表

| 状态 | 含义（都由事件、证据和锁算出） |
|---|---|
| `ready` | 本轮已开，下一步还没有 `step_intent`，已记账的步骤判定是「继续」 |
| `implementing` / `verifying` / `reviewing` | 有一步开着（有 `step_intent`、没有 `step_recorded`），驱动持有锁。`overdue` 是读取方加的标记（第 8 节），状态不变 |
| `start_ambiguous` / `unknown` | 有一步开着、锁空着；或证据无效；或事件日志无效（第 2 节）。只能由人处理（第 6 节） |
| `verdict_pending` | 本轮没有判词，没有开着的步骤，而判定对已记账的步骤已有终局结果：驱动死在 `step_recorded` 之后、`verdict` 之前（B8）。显示为 `verdict_pending (<结果>)` |
| `verify_failed` / `changes_requested` / `step_failed` | 本轮已有否定判词，预算还有 |
| `over_budget` | 本轮已有否定判词，且 `已开轮数 ≥ max_rounds + 延期次数`。第一片没有 `extend`：lane 停在这里，队列标 `needs: owner`，只接受 `abandon` 和 `confirm-ended` |
| `passed` | 本轮判词是通过。终态 |
| `abandoned` | 记了放弃。终态。不表示进程已经停了。事件日志中段无效时，末尾这条完整的 `abandoned` 仍然算数 |

**每条改状态的命令按同一个顺序过六关，前一关拒绝就不看后面的**：① 环境里有 `LANE_EXEC` → `a lane step cannot change a lane`；② 拿不到 lane 锁 → `lane <id> is being driven by pid <n>`（退出码 3）；③ 修复残尾，再检查事件日志，无效 → `event log invalid at seq <n>; a person must inspect it`（只有 `abandon` 例外）；④ **补落判词**：状态是 `verdict_pending` 就先追加那条 `verdict`；⑤ 按补落之后的状态查下表；⑥ 表里没有的组合 → `<command> is not allowed in state <state>`。日志是否有效排在锁之后，因为残尾要拿到锁才能判断和修复。

| 当前状态 | 命令或事件 | 结果 | 谁可以 | 拒绝时的文案 |
|---|---|---|---|---|
| （无） | `new` | `ready`，第 1 轮，计入预算 | 统筹方 | id 已存在：`lane <id> exists` |
| `ready` | `run` | 从本轮还没有开始的那一步起，依次进入 `implementing` → `verifying` → `reviewing` | 统筹方、夜跑循环 | 任务书或配置变了：`<file> changed since …` |
| 三个进行中状态 | 步骤结束（驱动记账） | 按第 4 节：下一步，或 `passed` / `verify_failed` / `changes_requested` / `step_failed` | 只有持锁的驱动 | — |
| 三个进行中状态 | 驱动死亡 | 没有记账：`unknown` 或 `start_ambiguous`。已记账：`ready` 或 `verdict_pending` | 无（算出来的） | — |
| `verdict_pending` | 任何改状态的命令，包括 `run` | 第 ④ 关追加判词，状态变成 `passed` 或某个否定状态；命令再按新状态查本表，`run` 不启动任何步骤 | 发命令的一方 | — |
| `unknown`、`start_ambiguous` | `resolve --kind failed\|cancelled\|evidence-lost` | `step_failed`，本轮关闭 | 人，记名 | 见第 6 节 |
| `unknown`、`start_ambiguous` | `resolve --kind still-unknown` | 不变 | 人，记名 | — |
| `unknown`、`start_ambiguous` | `run`、`next-round` | 不变 | — | `round <n> <step> result is unknown; a person must resolve it` |
| 三个否定状态 | `next-round --brief <file>` | `ready`，轮次加一 | 统筹方 | — |
| 三个否定状态、`over_budget` | `run`、`resolve` | 不变 | — | `round <n> is closed (<result>); the only way on is next-round` / `round <n> already has a verdict` |
| `over_budget` | `next-round` | 不变 | — | `over budget: <used>/<budget>; the Owner decides` |
| `over_budget`（第二片） | `extend --by coordinator\|owner --reason` | 回到原否定状态，多一轮 | 统筹方每条 lane 一次；Owner 要终端并打回 lane id | `the coordinator has used its one extension; the Owner decides at a terminal` / `owner extensions need a terminal`；其他状态：`budget is not exhausted` |
| `passed` | `confirm-ended` 以外的改状态命令 | 不变 | — | `lane <id> passed in round <n>; it is closed` |
| 除 `passed`、`abandoned`、进行中以外（含事件日志无效） | `abandon --operator --reason` | `abandoned` | 统筹方或人 | — |
| `abandoned` | `confirm-ended` 以外的改状态命令 | 不变 | — | `lane <id> was abandoned` |
| 任何状态 | `confirm-ended --attempt` | 状态不变，只标记那次执行已确认结束 | 人，记名 | 它已有退出记录：`attempt has a recorded exit` |

`passed` 只有两个来源：「步骤结束」那一行和第 ④ 关的补落。两者都只在本轮还没有判词时发生，用同一个判定函数和同一份证据；已有否定判词的轮，没有任何一行通向本轮的 `passed`。有效的验收 FAIL 走「三个否定状态 → `next-round`」，没有死路。六关和这张表实现为同一份数据，所有命令入口都查它。

## 6. 人工补记 `unknown`

`lane.py resolve <id> --attempt <attempt_id> --kind … --operator <名字> --reason <文字> --evidence <看了什么>`，四项缺一拒绝；`--attempt` 必须是当前结果未知的那次执行。能追加的只有：

| `--kind` | 用在哪种未知上 | 之后 |
|---|---|---|
| `failed` / `cancelled` | 没有 `step_recorded` 的执行（B4–B7，退出码没有记下来）：这一步没有成功 / 是人把它结束的 | 本轮判 `step_failed`；再做只能 `next-round`，照常查预算 |
| `evidence-lost` | 已有 `step_recorded`、但证据在判词之前丢了或变了的执行。记着的退出码不被替换，照旧留在事件里；这一轮只是关成未成功 | 同上 |
| `still-unknown` | 任何一种：看过了，仍无法确认 | 保持阻塞，留在队列里 |
| `exit-code --code <n>` | 有证据的真实退出码。证据只能是调用了 `wait` 的一方为这个 `attempt_id` 写下的退出记录；这样的一方只有驱动（那就已有 manifest）和将来的执行器（第 8 节） | 执行器出现之前一律拒绝：`no wait-based exit record exists for attempt <id>`。日志里的一行字不是退出码。将来接受时结果仍走第 4 节整张表：非零就是失败，零也要满足全部放行契约 |

`evidence-lost` 是选出来的做法，另一个做法是这种 lane 只能 `abandon`。选它的理由：关成未成功是收紧，什么都放不过去；只因为一个产物文件出了意外就废掉整条 lane 和它的轮次记录不值得；原来「退出码已记下就拒绝」要防的是替换退出码，它不替换。事件日志无效造成的未知过不了第 ③ 关，只能 `abandon`。

拒绝的：没有 `passed` 这个取值；对已记账的执行用 `failed` / `cancelled`（`exit code is recorded (<n>); use --kind evidence-lost`）；对没有记账的执行用 `evidence-lost`（`attempt has no recorded exit; use failed or cancelled`）；本轮已有判词（`round <n> already has a verdict`），所以「先修」和验收 FAIL 改不成通过，复核过的轮也开不回来。证据不能证明成功，就只有两条路：保持阻塞，或者关成未成功。

## 7. 旧的执行与下一轮

- **规则**：`unknown`、`abandoned`、人工关闭都只是记账，不表示进程结束了；lane 锁空着也不表示目录可以再用；lane 不声称回收过任何东西。因此 lane 只在它刚刚独占创建的目录里启动步骤，任何一次执行用过的 `work/`、`out/` 都不再交给后来的步骤。所以「旧执行可能还在写的目录」里不可能推进：每轮、每步都是新目录，新检出按提交号从旧目录取对象并逐个校验，旧进程之后再写什么都进不来。旧进程后来的推送也不影响判定，因为固定的是本地提交号，不是分支头。
- **启动歧义**：先落 `step_intent`，再启动，`step_started` 紧跟在启动返回之后。两者之间驱动死掉就是 `start_ambiguous`，如实显示，不关成失败，也不说已回收。子进程的参数里带着含 `attempt_id` 的路径，人可以用 `pgrep -f <attempt_id>` 找它。
- 没有 manifest 的执行在有人用 `confirm-ended`（记名、写明怎么确认的）之前，一直列在队列里：`execution not confirmed ended: <attempt_id>`。正常退出后留下的后台后代 lane 看不见，这部分只靠隔离，以及「记账后产物再变就失效」（第 2 节）。

## 8. 无人值守

复核 21 给了两个做法：(a) 时限由 lane 之外的执行器或宿主边界强制，lane 只收到「这次执行被取消 / 超时」这个事实；(b) lane 只标记「超时，等人」，这条 lane 的夜跑停在这里。

**已定：第一片用 (b)**（第 12 节第 1 条）。每步的 `limit_seconds` 写在 `step_started` 里。驱动阻塞在 `wait()` 里，不追加事件，也不做任何事；`overdue` 由 `status` 和 `queue` 在读的时候算：这一步还开着，且 `现在 − started_at > limit_seconds`。队列标 `needs: person`。理由：① 第一版的问题几乎都出在管进程的代码上，执行器就是这类代码，应该单独设计、单独复核；② 现在的宿主是会睡眠的笔记本（ADR §12.9 第 9 条记过一轮被冻住 5 小时），按墙上时钟强制超时会在唤醒时结束本来正常的步骤，而一个算出来的标记最多是多叫一次人；③ 判定表已经留了 `termination` 一行，以后接 (a) 不用改判定。代价：一步挂住，这条 lane 就停到人来，失控的实现者继续耗额度；别的 lane 只要由各自的 `run` 进程驱动就不受影响（每条 lane 一把锁，没有共用的文件）。驱动还在时，人按记录的 pid 核对启动时间后手工结束进程，驱动的 `wait()` 会如实记成 `ended by signal <n>`。

**(a) 需要的东西**：一个 lane 之外的执行器（最终是 `agentd`，ADR §12.3）：它是子进程的父进程，用不计睡眠的时钟计时，只结束自己还没收尸的那个孩子所在的组，从不按磁盘上的 PID 发信号；它独占写一份带 `attempt_id` 的退出记录（真实的 `wait` 结果和 `termination`）；取消入口在步骤里调用时拒绝，也不能指向已经关闭的执行。不论 (a) 还是 (b)：停止不改判词、不重开步骤、不返还预算、不触发任何重跑。

## 9. 预算、队列和看板

- **一处检查**：轮次只在 `new` 和 `next-round` 里产生，两处调同一个 `may_open_round`：`已开轮数 < max_rounds + 延期次数`（第一片延期次数恒为 0）。`run` 不开轮。一轮里每步只有一次执行，失败、取消、未知都算用掉这一轮，没有别的入口能再跑一次。
- **队列（第一片是最小的）**：`lane.py queue` 列出每条不是 `passed`、也不是正常在跑的 lane，以及任何还有「未确认结束的执行」的 lane（包括 `abandoned` 的）。每行 `{id, title, state, round, budget, why_waiting, needs, since}`。`needs`：`coordinator`（`ready`、`verdict_pending`、预算内的否定状态）、`person`（`unknown`、`start_ambiguous`、带 `overdue` 的、未确认结束的执行）、`owner`（`over_budget`）。`queue --check` 在有 `person` 或 `owner` 项时退出码非零，供看守脚本叫醒人，不靠模型记着去看。
- **延期（第二片）**：只在 `over_budget` 时受理，每次加一轮，记 `extension{by, reason, at, new_budget}`。`coordinator` 每条 lane 一次；`owner` 要终端加打回 lane id。同用户可以伪造终端，这不是安全边界（第 1 节）；状态迁到平台后，Owner 的延期改成一张审批单。延期显示在 `status`、`queue` 和看板上：`budget 2+1 (coordinator, <时间>: <原因>)`。
- **看板（第二片）**：每条改状态的命令结束时由事件重新生成，形状沿用 TASK.md：`{"works": [{"title", "short", "goal", "round", "steps": [{"name", "who", "progress", "done", "pattern", "usual_min"}]}]}`。`progress` 是 `out/stdout`；`done` 是 manifest 发布后写的 `rec/done`（`exit=<code>`，只给看板，lane 从不读回）；`pattern` 是 `attempt_id`。另加 `state`、`reason`、`budget`、`needs`；没有值的字段不出现，不写空值。没有任何命令读看板文件。

## 10. 验收清单

每一行对应复核报告里的一条发现。「不可能」表示这个缺陷在本设计里没有存在的位置；测试写成「输入 → 期望的状态和原因」；只回答了一部分的写明。测试编号不重排；标「第二片」的不在第一片验收。

| 发现 | 处置 |
|---|---|
| 16-P1 失败或崩溃仍可通过 | **T01** verify 末行 `VERDICT: pass`、退出码 7 → `step_failed`，`verify exited 7`，review 没有 intent。**T02** review 报告完整写着 `safe to merge`、退出码 9 → `step_failed`，`review exited 9` |
| 16-P1 没有同轮、同提交及报告来源约束 | 追加打开、复用目录、读共享 `verify.txt`、接受预先写好的报告都不可能（独占创建，`out/` 启动时必须为空，只读被引用的 manifest）；每条判词带 SHA 集合和各 manifest 的摘要。**T03** attempt 目录已存在 → 拒绝启动，无新事件。**T04** `work/verify.txt` 里放一份旧的 `VERDICT: pass`，本次 stdout 没有判词 → `step_failed`，`verify produced no verdict`。review 只在本轮 verify 对同一 SHA 集合通过后才有 intent（第 4 节第 15 行）。来源绑定另见 T44–T46 |
| 16-P1 同一 lane 没有互斥锁 | **T05** 两个真实进程同时 `run` → 后一个退出码 3，`lane <id> is being driven by pid <n>`，事件数不变。临时文件名带随机后缀 |
| 16-P1 预算授权可自签 | **T06** 环境里有 `LANE_EXEC` 时调 `run` / `next-round` / `resolve` / `confirm-ended` / `abandon` → 全部拒绝（`extend` 那一格在第二片）。**T07**（第二片）第二次 `extend --by coordinator`、非终端的 `--by owner`、未超预算的 `extend` → 各自拒绝。**T08** 预算用尽时 `next-round` → 拒绝，`over budget: 2/2; the Owner decides`，状态 `over_budget`，队列 `needs: owner`；`run` 在任何状态都不产生开轮事件。**T09** 手改事件日志中间一行 → `unknown`，`event log invalid at seq <n>`。只回答了一部分：同用户重写整条链查不出来（第 1 节） |
| 16-P1 路径能注入 shell 命令 | 不可能：没有 shell。**T10** 工作路径含 `$(touch X)`、反引号、双引号、空格 → 子进程收到一个参数，`X` 不存在；字符串形式的模板在加载时被拒绝 |
| 16-P2 崩溃恢复不能可靠接续 | 接续不存在：没有恢复、没有等待旧 PID。**T11** 驱动在 `step_intent` 之后、`step_started` 之前被杀 → `start_ambiguous`；`run` 拒绝。**T12** 驱动在等待中被杀、孩子继续跑 → `unknown`；`run` 拒绝，没有第二个子进程。已记账之后的崩溃见 T48 |
| 16-P2 stall / abandon 留下继续运行的实现者 | 只回答了一部分：lane 不结束它（已定）。lane 不再说它停了：**T13** T12 之后旧孩子继续在旧 `work/` 里写和提交；`resolve --kind failed`、`next-round`、`run` → 新一轮的 SHA 集合和检出里没有旧孩子后来写的东西。**T14** `abandon` 一条有未知步骤的 lane → `abandoned`，队列仍列出 `execution not confirmed ended`，`confirm-ended` 之后才消失 |
| 16-P2 queue 隐藏最需要处理的 lane；status 只回显磁盘 | **T15** 每种状态各建一条 lane → 队列列出除 `passed` 和正常在跑以外的全部，`needs` 逐条正确；`over_budget` → `needs: owner`（「统筹方的延期是否已用」的区分在第二片）。T12 里 `status` 显示 `unknown`，不显示 `implementing`。运行中的读取见 T51 |
| 16-P2 判词解析误收也误拒 | **T16** verify stdout 中间的代码块里有 `VERDICT: pass`、末行是别的 → `step_failed`，`verify produced no verdict`。**T17** review 报告带 BOM 和前导空行 → 正常识别；缺 `END OF REPORT` → `step_failed`，`review report is truncated`。只回答了一部分：没有改成结构化的结果文件，沿用「退出码 + 恰好的首尾行」，完成标记是 `END OF REPORT` |
| 17-P1 `done` 覆盖真实退出码 | 不可能：没有被读回的完成文件。**T18** 孩子在 `out/`、`work/` 里写 `done` 和 `manifest.json` 声称 0，实际退出码 9 → `step_failed`，`implement exited 9` |
| 17-P1 HEAD 一致不保证验收的是该提交内容 | 验收的不再是实现者的目录。**T19** verify 在检出里改已跟踪文件不提交 / 留下未跟踪文件 / review 改文件 → `step_failed`，`snapshot of <repo> changed during <step>`。**T20** 实现者目录里有未提交改动和被忽略的构建产物 → 后面的检出里都没有，记一条提示，判定不受影响。内容绑定另见 T44–T46 |
| 17-P2 运行时无法 `stop` / `abandon` | `stop` 已删；驱动在跑时 `abandon` 被拒绝（退出码 3）。只回答了一部分：结束失控进程的能力没有了，见第 8 节和 T38 |
| 17-P2 只确认组长死亡，可能留下子进程 | lane 不回收、也不记「已回收」，这个错误的断言不可能出现。残留的后代只靠隔离（T13）和 T27；只回答了一部分 |
| 17-P2 启动崩溃窗口留下无法回收的进程 | 窗口消除不了，改成如实命名：T11。不再关成 `failed`。只回答了一部分 |
| 17-P2 queue 仍隐藏崩溃后待处理的 lane | T12、T15：驱动死后队列列出，`needs: person` |
| 17-P2 verify 判词并非取自 stdout | **T21** `VERDICT: pass` 只出现在 stderr → `step_failed`，`verify produced no verdict` |
| 20-P1 `stop → retry` 绕过复核结论和轮次限制 | 不可能：没有这两个命令，每轮每步一次执行。**T22** 表驱动：第 5 节每个（状态 × 命令）组合各调一次，结果与表逐格相同；从任何已有否定判词的轮出发，穷举长度不超过 4 的命令序列，到不了本轮 `passed`。**T23** review 写出首行 `VERDICT: fix first` 后被人手工结束（驱动还在）→ `step_failed`，`review ended by signal 15`，该集合记为已否决；下一轮固定出同一集合 → `step_failed`，`no new commit since round 1 said fix first`。没有判词的复核怎么再来一次见 T50 |
| 20-P1 恢复可能误杀复用 PGID 的无关任务 | 不可能：程序里没有发信号的调用。**T24** 静态检查：源码里没有 `os.kill`、`killpg`、`send_signal`、`terminate`、`.kill(`，也没有读回 PID 再等待的代码 |
| 20-P1 未跟踪文件检查受 Git 配置影响 | **T25** 全局和仓库配置都写 `status.showUntrackedFiles=no`，全局 ignore 写 `*` → 检出里的未跟踪文件仍被发现 |
| 20-P2 启动崩溃窗口仍存在（延迟注册的 runner 仍会执行） | runner 和握手已删。「阻止已关闭的执行继续跑」做不到；它只能写自己的旧目录（T13），状态如实是 `start_ambiguous`（T11）。只回答了一部分 |
| 20-P2 验收 FAIL 无法进入下一轮 | **T26** verify 退出码 1、末行 `VERDICT: FAIL (2 checks failed or produced no result)` → `verify_failed`；`next-round` 接受，进入第 2 轮 `ready` |
| 20-P2 正常退出留下的组员无法再被停止 | 只回答了一部分：lane 不停任何进程。**T27** 记账后往 `out/stdout` 追加一个字节（模拟残留后代）→ 判词之前 `unknown`，`evidence invalid`；`passed` 之后 `pass-set` 拒绝，`evidence changed after the verdict`。写旧 `work/` 的情况见 T13 |
| 21-P1 人工补记不能成为改判入口 | **T28** `--kind passed` → 参数被拒；对已有判词的轮 `resolve` → 拒绝；缺 `--operator` / `--reason` / `--evidence` / `--attempt`，或 attempt 不是结果未知的那个 → 拒绝；对已记账（退出码 9）而证据无效的执行用 `failed` → 拒绝，`exit code is recorded (9); use --kind evidence-lost`。**T29** `--kind exit-code --code 0` → 拒绝，`no wait-based exit record exists`。**T30** 对没有记账的执行 `--kind failed` → `step_failed`，`implement closed as failed by <operator>: <reason>`；`still-unknown` → 仍是 `unknown`；之后 `next-round` 在预算用尽时被拒 |
| 21-P1 纯函数还缺完整放行契约 | 第 4 节。**T31** 对放行契约的每一项逐一置缺或置坏 → 没有一个是 `passed`，原因是表里最靠前命中的那一条：缺 manifest 或形状不合法 → `unknown`；信号、非零退出码、`termination` 非 `exited`、判词多一个字符、报告截断、记录时没有报告、不变性检查里 git 非零退出、`context` 仓库动了 → `step_failed`。FAIL 的推进见 T26，正常新增提交见 T41 |
| 21-P1 新目录不能证明产物归属和完整性 | 第 2 节。**T32** 只有 `manifest.json.tmp-*`、或 manifest 没有被事件引用 → `unknown`，用 `failed` 关；已记账的 manifest 被改（`exec`、`intent_sha256` 或摘要不符）→ `unknown`，`evidence invalid: …`，用 `evidence-lost` 关。另见 T03、T04、T18、T27、T47、T49 |
| 21-P1 四次 HEAD＋clean 仍不足 | 第 3 节。**T33** 检出里对一个文件设 `assume-unchanged` 或 `skip-worktree` 后修改 → `step_failed`，`hidden index flag in <repo>`。**T34** 固定提交的树里有 gitlink → implement 判 `step_failed`，`submodule at <path>: …`，verify 没有 intent。另见 T19、T20、T25、T44–T46。只回答了一部分：子模块在第一片是拒绝而不是递归固定；验收命令自己在检出里「改了又改回」查不出来，接受（它是统筹方的脚本，已按摘要固定）；主机共享的依赖缓存不在检出内 |
| 21-P1 通过必须绑定提交集合，合并还需要独立闸门 | **T35** 通过之后 amend 出树相同的新提交 → `pass-set` 给的仍是原提交号，新提交号没有通过记录。`pass-set` 在证据变动后拒绝（T27）。只回答了一部分：合并闸门不在第一片，通过到合并之间的窗口没有被程序封住（第 3 节末） |
| 21-P2 防止旧执行与下一轮重叠 | 第 7 节；T11、T13、T14。**T36** 驱动被杀、孩子还在 → 另一个进程拿得到 lane 锁（锁没有被孩子继承），状态是 `unknown` |
| 21-P2 无人值守需要明确取舍 | 第 8 节，已定 (b)。**T37** 步骤超过 `limit_seconds`、驱动阻塞在 `wait()` → `status` 和 `queue` 显示 `overdue`，`queue --check` 非零，事件文件没有新行，进程没有收到信号。**T38** 人手工 TERM 掉超时的孩子（驱动还在）→ `step_failed`，`review ended by signal 15`；没有新的执行，预算没有返还。只回答了一部分：整夜持续推进在第一片不满足（已定，第 12 节第 1 条） |
| 21-P2 预算和待处理队列由程序持有 | 第 9 节；T08、T15、T30。**T39**（第二片）删掉生成的看板文件后重新生成 → 内容相同，形状符合 TASK.md，没有空值。**T40**（第二片）夜跑循环的示例脚本只调用 `run`、`queue`、`status`、`board`（静态检查）。只回答了一部分：延期和看板在第二片；Owner 的终端入口挡不住同用户冒充（已接受） |
| 21 旧问题归类里「仍存在或转化」的六项 | 启动登记窗口 T11；残留孩子 T13、T27；挂起的步骤 T37、T38；队列遗漏 T15、T51；预算授权 T08（延期部分 T07，第二片）；验收 FAIL 的推进 T26 |
| 21 新风险：补记洗白失败；记录关闭被读成执行结束；不可变判词引用可变产物 | T28–T30、T49；T14；T27 和 `pass-set` 的重算 |
| 21 结语：记录器和所有命令入口执行同一套约束 | T22、T52：所有入口过同样的六关、查同一张表；所有视图调同一个 `lane_state` |
| 23-P1a 通用快照规则会拒绝正常实现 | 第 3 节拆成基线检查、固定、不变性三种；判定表第 8、9 行和放行契约随之重写；未提交的改动全文只有「提示」一个说法。**T41** implement 在 `change` 仓库正常新增两个提交，并留下未提交的改动 → 固定出新集合，只记 `notes`，verify 的 intent 消费这个集合，流程继续。**T42** implement 期间 `context` 仓库多了一个提交 → `step_failed`，`context repository <repo> moved`；一个提交都没有 → `step_failed`，`implement produced no commit` |
| 23-P1b 克隆隔离不能保证证据对应原始提交内容 | 第 3 节「检出的做法」「git 的调用环境」「替换对象和嫁接」；补全 16-P1 来源绑定、17-P1 内容绑定、21-P1 独立快照三行。**T44** 来源仓库有一条 replace 引用，把固定的提交换成树不同的提交 → 固定时 `step_failed`，`<repo> has replace refs or grafts`；固定之后才加上 → verify 未启动，同一原因；`info/grafts`、浅仓库同样。**T45** 来源仓库带 `objects/info/alternates` → 检出里没有 `alternates`，没有硬链接的对象文件；把来源目录挪走后 `git fsck --connectivity-only` 仍通过。**T46** 全局配置的 `init.templateDir` 和环境里的 `GIT_TEMPLATE_DIR` 指向带 `post-checkout` 的模板，另设 `GIT_DIR`、`GIT_ALTERNATE_OBJECT_DIRECTORIES` → 检出的 `hooks/` 为空，hook 没有运行，这些变量没有传到 lane 的 git。只回答了一部分：取对象时来源一侧的 git 仍读来源仓库自己的 `.git/config`（来源目录是 lane 建的；同用户恶意改写不在范围内） |
| 23-P1c 事件尾部半写没有恢复协议 | 第 2 节「残尾修复」「持久创建的顺序」和边界表。**T47** 在 B1–B10 每个边界各杀一次进程 → 状态是边界表里的那一格；随后一条改状态的命令之后日志有效、`seq` 连续，残尾进了 `events.torn-*` 并有一条 `tail_repaired`；半写的 intent 所在目录成为孤儿，`run` 另建 attempt |
| 23-P1d 已记账但未裁决的崩溃状态没有转换 | `verdict_pending` 和第 ④ 关。**T48** 在 implement、verify、review 的 `step_recorded` 之后各杀一次驱动：implement 正常 → `ready`，`run` 从 verify 接着走，implement 没有第二次执行；implement 退出码 9 → `verdict_pending`，下一条改状态的命令先落 `step_failed`（`implement exited 9`）再办自己的事；review 完整通过 → `run` 落 `passed`，不启动任何步骤；同一命令再跑一次不产生第二条判词 |
| 23-P2a 缺报告、无效证据和人工关闭互相冲突 | 第 2 节 manifest 的两种形状和「怎么关」一栏；第 6 节 `evidence-lost`；T28、T30–T32 已按此统一。**T43** 来源仓库里取不到期望的提交 → 步骤未启动，manifest 是「未启动」形状（`exit`、`termination` 为 null，产物表为空），`step_failed`，`implement did not start: cannot fetch <sha>`。**T49** 记录时报告不存在 → `step_failed`，`review produced no report`，不是 `unknown`；记账后、判词前删掉报告 → `unknown`，`evidence invalid: review report missing`，此时 `--kind failed` 被拒、`--kind evidence-lost` → `step_failed`；对没有记账的执行用 `evidence-lost` → 拒绝 |
| 23-P2b 复核的登记点和无判词失败的出口未定义 | 第 3 节「否决过的 SHA 集合不再复核」；T23 已改。**T50** review 崩溃（退出码 1，没有报告）→ `step_failed`；下一轮固定出同一集合 → 照常进入 verify 和 review，耗一轮。报告非空但被截断、首行不是判词 → `step_failed`，`review report is truncated`，下一轮同一集合可以再复核；首行是 `VERDICT: fix first` 的截断报告 → 记为已否决。只回答了一部分：驱动死掉的那次复核没有 manifest，不登记，哪怕它的报告文件里已经写了否决；这条路要一次记名的 `resolve` 和一轮预算，不是悄悄的 |
| 23-P2c 运行中队列可读、重叠拒绝规则的优先级 | 第 2 节「锁与读取」、第 5 节六关、第 8 节 `overdue` 由读取方算。**T51** 驱动持锁并阻塞在一个不结束的步骤里 → `status`、`queue` 一秒内返回并显示进行中；事件文件末尾有半行时读取方忽略它、不修复。**T52** 同时满足 `LANE_EXEC`、驱动在跑、日志无效、状态不允许 → 文案是最靠前那一关的；逐个去掉条件，文案依次变成下一关的 |
| 23-P2d 还有别的事在悄悄决定 | 第 12 节把这些写成政策；第 13 节改成第一片的前置条件并带结果栏；`overdue` 怎么产生已定（T37、T51） |
| 23-P2e 第一片仍过大 | 第 11 节：第一片九个命令；`board`、`extend`、夜跑示例连同 T07、T39、T40 以及 T06、T15 里与延期有关的格子移到第二片 |

## 11. 分片

- **第一片**：记录器（第 2–3 节）、判定表和转换表（第 4–6 节），命令 `new`、`run`、`next-round`、`resolve`（`failed`、`cancelled`、`evidence-lost`、`still-unknown`）、`confirm-ended`、`abandon`、`status`、`pass-set` 和最小的 `queue`（含 `--check`）。`confirm-ended` 留在第一片：没有它，未确认结束的执行永远清不出队列，`queue --check` 会一直非零。测试：T01–T06、T08–T38、T41–T52（T06、T15 里与延期有关的格子除外）。Python 标准库，一个命令行，放 `agent-config/scripts/lane/`，从空目录写起，不在 `w31/w66-lane` 上改。按表和测试验收，不拿行数当验收。链停在 `passed`；超预算就停，等 Owner。
- **第二片**：`board`、`extend`（两种）、夜跑循环的示例；T07、T39、T40，以及 T06、T15 里与延期有关的格子。
- **以后**：合并闸门及其后的主线 CI、测试环境、台账状态（W-66 ③④）；执行器强制的时限和取消（随 `agentd`）；`exit-code` 补记；子模块递归固定；`inputs`；状态迁到平台（事件 → `agentrt.event`，manifest 和产物 → 按内容哈希的 `artifact`，判词 → `verification`，轮次预算 → `budget_ledger`，lane 锁 → 租约，Owner 延期 → 审批单；DESIGN 7.2–7.5）。

## 12. 已定的事和随设计定下的政策

没有待 Owner 定的事。下面第 1 条是已定的决定；其余是这份设计带来的政策，写在明处，不让它们藏在条文里。

1. **无人值守用方案 A**（Owner 同意做第二版；统筹方 2026-10-11 定）：挂住的步骤等人。W-66 的验收句相应变成：统筹线程在「先修」「超预算」「结果未知」「超时」四种情况被叫醒，后两种要人到场。第 13 节第 3 条核对出两个命令行自带时长或额度上限，就再配上它们（原选项 C）；执行器（原选项 B）随 `agentd` 做。
2. **配置固定的后果**：验收脚本或 `lane-config.json` 要改，只能另建一条 lane，旧的 `abandon`；已用的轮次不带过去。
3. **没有判词的复核耗一轮**：崩溃、被限流、报告截断都算；同一集合可以在下一轮再复核。写出否决首行的复核，不论完整与否，都算否决，要有新提交才能再复核。
4. **未提交的改动是提示，不是失败**；一个提交都没有才是失败。
5. **基础设施失败和驱动死亡都耗一轮**；第一片没有 `extend`，超预算就停在那里等 Owner。
6. **`resolve` 和 `confirm-ended` 由人记名执行**；夜跑不调用它们。程序分不出人和模型，这一条靠记名和队列可见，不是技术上的拦截。

## 13. 第一片的前置条件

第 2–6 条的结果写回「结果」一栏之前不派第一片的实现；哪一条不成立，先改规格。

| # | 条件 | 怎么核对 | 结果 |
|---|---|---|---|
| 1 | `git init` 加 `git fetch <目录> <提交号>` 取得到不在任何分支上的提交；检出没有硬链接、没有 `alternates`、没有 hooks；来源的 replace 引用不改变检出里的树；`ls-files -v` 的标记是 `h` / `S`；固定环境不受全局配置和全局 ignore 影响 | 在临时目录里按第 3 节的命令试 | **成立**（2026-10-11，本机 git 2.50.1）。对照：普通本地克隆硬链接了对象、继承了 `alternates`、复制并运行了模板里的 `post-checkout` |
| 2 | `verify-branch.sh` 能在这种检出组成的目录里跑通，包括它调用的 `check_hardcoded_paths.py --worktree` 和 `code-health/scan.sh --root` | 同一提交在这种布局和现有任务目录里各跑一遍，对比结果 | 未核对 |
| 3 | `cursor-agent -p`、`codex exec` 在失败、被限流、额度用尽时退出码非零；两者有没有自带的时长或额度上限；`codex exec --output-last-message` 是否只在结束时写报告、是否总是新建文件 | 读两者的 `--help`，各做一次故意失败的调用 | 未核对 |
| 4 | `fcntl.flock` 在 macOS 上随进程死亡释放、默认不被子进程继承；读取方的共享锁探测不会让改状态的命令等过 2 秒 | 写第一片时最先落的两个测试（T36、T51） | 未核对 |
| 5 | 每次执行一份检出加依赖安装的耗时和磁盘占用可以接受 | 对 `bifrost-platform` 量一次，写进 `usual_min` | 未核对 |
| 6 | 夜间本机是否保持唤醒（不保持时 `overdue` 会在唤醒时集中出现；它只是标记，不影响判定） | 看电源设置和一夜的看守日志 | 未核对 |
| 7 | （第二片）看板读取方 `~/agent-work/status/board.py` 接受多出来的字段和省略的字段 | 读它的解析代码；服务端校验见 LESSONS 第 55 行 | 未核对 |
