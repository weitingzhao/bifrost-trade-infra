# W-66 派工流水线第二版规格：只判定和记账，不管进程

状态：规格，2026-10-11。待 Codex 复核，待 Owner 定第 12 节。没有代码，还没有派实现。
输入：`WORK.md` 的 W-66；`work/multi-agent/reviews/` 里的复核 16、17、20（第一版 `lane.py`，三次「先修」，没有合并）；复核 21（第二版设计，结论 `sound with changes`，要求先把约束写成状态转换表和失败场景验收清单）；`ADR-ops-architecture.md` §12.2 第 13 条。
已定、本文不重新讨论：lane 只判定和记账，不结束进程、不处理进程组、不接续旧进程、不自动重跑，没有 `retry`，没有会发信号的 `stop`。判词只增不改，复核过的轮不再复核；「先修」和有效的验收 FAIL 只能经下一轮出去。`max_rounds` 默认 2，统筹方每条 lane 只能延一次，再延只能 Owner 在终端做。

## 1. 范围与不做的事

- **做**：一条 lane 把一件事按固定顺序走 `implement → verify → review`。每一步只做三件事：起一个进程、等它结束、记下退出码和产物。一个纯函数按记录判定这一轮。预算、队列、看板都从事件算出来。
- **不做**：不发任何信号；不读、不信、不等待磁盘上记的旧 PID；不重跑任何步骤；不合并、不看主线 CI、不发布（第 11 节）。
- **接受的边界（只说这一次）**：所有进程是同一个 Unix 用户，都能改写 lane 目录里的任何文件。本设计防的是失误、陈旧或半写的文件、以及统筹方悄悄绕开判词；不防恶意进程。真正的边界要等 Agent 换用户或进沙箱（ADR §12.3 的 `agentd`）。
- **不管进程的代价**：① 失控的实现者、挂住的复核者没有程序去结束，额度会一直消耗到人来；② 驱动死掉的那一步只能判未成功，哪怕它其实做完了，代价是一轮；③ 额度用尽、断网这类失败同样消耗一轮；④ 每次执行一份全新检出，多花磁盘和依赖安装时间。

## 2. 身份与产物协议

```
~/agent-work/lanes/<lane_id>/                 # 根目录可用 --root 改
  lane.json   lock   events.jsonl             # 创建参数（只写一次）· flock · 只追加
  r<round>/brief.md                           # 开轮时复制的任务书（独占创建）
  r<round>/<step>-<attempt_id>/               # 独占 mkdir；已存在就拒绝启动
    rec/intent.json   rec/manifest.json       # lane 自己的记录，路径不传给子进程
    out/stdout   out/stderr   out/report      # 产物
    work/<repo>/                              # 这次执行独占的检出，也是子进程的 cwd
```

- **身份**：`exec = {lane_id, round, step, step_index, attempt_id}`，`attempt_id = <UTC 时间>-<8 位随机十六进制>`。每轮每步只有一次 attempt；`attempt_id` 的用处是让目录和引用不能被复用，不是给重试留位置。
- **事件**：`events.jsonl` 每行一条 JSON，带 `seq` 和上一行的 `sha256`（与 DESIGN 7.3 的哈希链同形），在 lane 锁内追加并 fsync。最后一行不完整算没写；中间任何一行坏了或链断了，整条 lane 是 `unknown`。没有可改写的状态文件：状态由 `lane_state(事件, 证据, 驱动是否在)` 这一个函数算出，所有命令和只读视图都调它。
- **锁**：改状态的命令从读事件之前到最后一次写之后独占 `lock`；`run` 整个驱动期间持有。锁的文件描述符不传给子进程。只读命令用共享锁探测「驱动是否在」。
- **配置固定**：`lane-config.json` 和它 `pinned_files` 里列的脚本（例如 `~/agent-work/verify-branch.sh`）在 `new` 时记 `sha256`，每一步启动前重算；变了就拒绝启动（`<file> changed since the lane was created`）。

| 时点 | 做什么（前一项落盘后才做后一项） |
|---|---|
| 启动前 1 | 建 attempt 目录；按第 3 节建 `work/` 检出并做预检查 |
| 启动前 2 | 独占创建 `rec/intent.json` 并 fsync（文件和目录）：`exec`、步骤顺序、`argv`（数组，占位符只在元素内替换，`shell=False`）、`cwd`、任务书的路径 / 长度 / `sha256`、配置和固定文件的 `sha256`、仓库清单、本步消费的 SHA 集合及其来源 manifest 的摘要、预检查快照、工具链版本、`limit_seconds`、环境变量名（不记值）、驱动 pid |
| 启动前 3 | 追加 `step_intent{exec, intent_sha256}`。预检查不过就不启动，直接走到「结束后 3」，manifest 里 `not_started` 写明原因 |
| 启动 | `out/` 必须为空；`out/stdout`、`out/stderr` 各用 `O_CREAT\|O_EXCL` 打开，不追加、不合流；子进程在新会话里启动，环境加 `LANE_EXEC=<exec>`；随后追加 `step_started{exec, pid, lstart}` |
| 结束后 1 | 退出码只取 `wait()` 的返回值（负值记成信号）。没有任何 `done` 文件被读回来做判定 |
| 结束后 2 | 关闭并 fsync 输出；做后检查快照；对 `stdout`、`stderr`、`report`（只有 review 有；必须是普通文件）记长度和 `sha256`；取出判定字段：verify 的 stdout 最后一条非空行；review 报告按 `utf-8-sig` 读，取第一条和最后一条非空行（去首尾空白）；P1/P2/P3 计数只作展示 |
| 结束后 3 | 写 `rec/manifest.json.tmp-<随机>` → fsync → rename → fsync 目录（macOS 上用 `F_FULLFSYNC`）。内容：`exec`、`intent_sha256`、`exit{code, signal}`、`termination`（本片恒为 `exited`）、起止时间、产物表、前后快照、判定字段；implement 另有它固定下来的 SHA 集合 |
| 结束后 4 | 追加 `step_recorded{exec, manifest_sha256}`。manifest 最后发布，并且只有被这条事件引用才算数 |

判定函数只读被事件引用的 manifest。它不读日志正文、不读工作目录、不找「最新的一份报告」。未知和无效永远不通过；摘要用来发现错配和事后变动，不是防伪。两者的含义：

| 看到的 | 含义 |
|---|---|
| 有 `step_intent`，没有 `step_recorded`，锁空着 | 这一步结果未知：有 `step_started` 是 `unknown`，没有是 `start_ambiguous`（启动了没有、PID 是多少都不知道） |
| 只有 `manifest.json.tmp-*`，或 manifest 没有被事件引用，或摘要与事件不符 | 等于没有 manifest：`unknown` |
| manifest 解析失败、缺字段、`exec` 或 `intent_sha256` 与 intent 不符 | `unknown`，原因 `evidence invalid: <step> <which>` |
| 产物缺失，或长度、摘要与 manifest 不符 | 判词之前：`unknown`。判词之后：判词不改；否定判词照旧，`passed` 不再可用（`pass-set` 拒绝，看板标 `evidence changed`） |

## 3. 验收和复核的对象

- **固定提交集合**：implement 的 `wait()` 返回后，对仓库清单里每个仓库在它的 `work/<repo>` 读 `HEAD` 的提交号和树号，连同目标基线（`lane.json` 里 `target_ref` 当时的提交号）写进 implement 的 manifest。这就是本轮的 SHA 集合。清单包含验收会读到的每个仓库：有改动的（`change`）和只被依赖的（`context`，固定在目标基线）。
- **独立快照**：verify 和 review 各有自己全新的 `work/`：每个仓库从本轮 implement 的 `work/<repo>` 执行 `git clone --no-checkout`，再 `git checkout --detach <sha>`；`work/PINNED.json`（在仓库之外）列出提交和目标基线，供复核者取 diff。实现者的工作目录从不被验收或复核：它里面没提交的改动、被忽略的文件、隐藏的索引标记都进不了快照，只记一条提示 `uncommitted changes in <repo> are not part of this round`。implement 的 `work/` 同样每轮新克隆：第一轮从 `lane.json` 登记的来源仓库按目标基线检出到 lane 分支；以后各轮从最近一次固定出 SHA 集合的那一轮的 `work/<repo>` 克隆并检出该集合，一次都没有固定过就同第一轮。
- **快照检查**（步骤前后各一次，任何一条 git 命令非零退出都算检查失败）：`HEAD` 等于固定的提交；`git status --porcelain=v1 --untracked-files=all --ignore-submodules=none` 为空；`git ls-files -v` 首列没有小写字母或 `S`（`assume-unchanged`、`skip-worktree`）。所有查询用固定环境：`GIT_CONFIG_GLOBAL=/dev/null`、`GIT_CONFIG_SYSTEM=/dev/null`、`-c core.excludesFile=/dev/null -c core.fsmonitor=false`。
- **子模块**：规则是递归固定：固定提交的树里每个 gitlink（mode 160000）按它记录的提交检出、记进 SHA 集合、按同样的规则检查。工作区各仓库今天都没有 `.gitmodules`（2026-10-11 查过），所以第一片只做检测：树里出现 gitlink 就不启动 verify，判 `step_failed`（`submodule at <path>: recursive pinning is not implemented`）。
- **被忽略但构建需要的输入**：快照建好时不存在任何被忽略的文件。依赖由验收命令在快照里按已跟踪的锁文件重建（`verify-branch.sh` 用 `npm ci`；Go 按 `go.sum`）。工具链版本（`git`、`go`、`node`、`npm`、`python3` 的版本输出）记进 intent。其余必须的被忽略文件要在配置的 `inputs` 里逐个声明来源和 `sha256`，由 lane 复制并记录；第一片 `inputs` 只允许为空，缺文件时验收自己会失败，这是看得见的失败。主机上共享的 npm、Go 缓存不在快照内，靠锁文件里的校验和约束；这一点接受。
- **通过绑定的是提交**：`passed` 记的是 SHA 集合。amend、rebase、cherry-pick 之后即使树相同也是另一个提交，没有通过记录，要走新一轮。
- **一个 SHA 集合只复核一次**：某个集合进过复核后，下一轮又固定出同一个集合，判 `step_failed`（`no new commit since the review in round <n>`）。唯一的例外是上一次复核的 manifest 证明报告不存在或是 0 字节。验收 FAIL 之后同一集合可以在下一轮再验，照样耗一轮。
- **给合并闸门的接口**：`lane.py pass-set <id> --json` 只在状态是 `passed`、且全部证据此刻重算摘要仍相符时输出 `{lane_id, round, verdict_seq, config_sha256, repos: {<repo>: {commit, tree, target_ref, target_sha}}, manifests, events_head}`，否则非零退出并给出原因。合并闸门只能用这里的提交号，不读分支头；合并当时再调一次。目标基线没动、并且是快进到固定的提交，合并结果就是验过的树；否则（基线动了、产生合并提交、rebase、squash）合并结果是新的提交，要自己先过一次验收。**合并闸门不在第一片**：第一片里从 `passed` 到合并之间的窗口没有被程序封住，由统筹方照这一条手工做。

## 4. 判定函数

`decide(round_evidence) → (结果, 原因)`，没有读写、没有子进程、没有时钟。它只在没有驱动持有这一步时求值。输入只有：三步各自的证据（`absent` / `invalid(which)` / manifest 的字段 `not_started`、`termination`、`exit.code`、`exit.signal`、前后快照的 `valid` 与各仓库提交号、implement 的 SHA 集合、verify 的 `stdout_last_line`、review 的 `report.bytes` / `report_first_line` / `report_last_line`）、本轮步骤上的人工补记、以及从事件里取的「已经进过复核的 SHA 集合」。按步骤顺序求值，每一步自上而下取第一条命中的；执行失败排在任何成功文本之前。

| # | 条件 | 结果 | 原因文本 |
|---|---|---|---|
| 1 | 人工补记 `failed` 或 `cancelled` | `step_failed` | `<step> closed as <kind> by <operator>: <reason>` |
| 2 | 证据 `absent`（步骤已有 `step_intent`；驱动还在时不求值，状态是进行中） | `unknown` / `start_ambiguous` | `<step> result is unknown` / `started or not is unknown; no pid recorded` |
| 3 | 证据 `invalid` | `unknown` | `evidence invalid: <step> <which>` |
| 4 | `not_started`（预检查不过、有 gitlink） | `step_failed` | `snapshot of <repo> <what> before <step>` / `submodule at <path>: …` |
| 5 | `termination` 不是 `exited` | `step_failed` | `<step> <timed_out\|cancelled> by the executor` |
| 6 | `exit.signal` 不为空，或 `exit.code` 为空 | `step_failed` | `<step> ended by signal <n>` / `<step> has no exit code` |
| 7 | implement、review 的 `exit.code ≠ 0`；verify 的不在 {0, 1} | `step_failed` | `<step> exited <n>` |
| 8 | 后检查快照无效或提交号变了；或本步消费的 SHA 集合不等于本轮 implement 固定的集合 | `step_failed` | `snapshot of <repo> changed during <step>` / `hidden index flag in <repo>` / `<step> ran on a different SHA set` |
| 9 | implement：SHA 集合不完整；或该集合已进过复核（第 3 节的例外除外） | `step_failed` | `cannot pin <repo>: <git error>` / `no new commit since the review in round <n>` |
| 10 | verify：`stdout_last_line` 等于 `VERDICT: FAIL` 或以 `VERDICT: FAIL (` 开头 | `verify_failed` | 那一行原文 |
| 11 | verify：`exit.code = 1` 而没有 FAIL 行；或 `exit.code = 0` 而末行不是恰好 `VERDICT: pass` | `step_failed` | `verify exited 1 without a FAIL verdict` / `verify produced no verdict` |
| 12 | review：报告不存在或 0 字节；末行不是恰好 `END OF REPORT`；首行不是两种判词之一 | `step_failed` | `review produced no report` / `review report is truncated` / `review produced no verdict` |
| 13 | review：首行恰好 `VERDICT: fix first` | `changes_requested` | `fix first (P1 <a>, P2 <b>, P3 <c>)` |
| 14 | 三步都没有命中 1–13，且 review 首行恰好 `VERDICT: safe to merge` | `passed` | `round <n> passed for <短 SHA 集合>` |
| 15 | 当前步没有命中，后面还有步骤 | 继续下一步 | — |

**完整的放行契约**就是第 14 行的前提：三份 manifest 都在、都有效；三步 `termination = exited`、没有信号、退出码为 0；verify 和 review 消费的 SHA 集合等于本轮 implement 固定的集合，前后快照都有效；verify 的 stdout 末行恰好 `VERDICT: pass`；review 的报告完整，首行允许通过，末行 `END OF REPORT`；没有任何否定的人工补记。除 `unknown` / `start_ambiguous` 外的结果作为判词追加（`verdict{round, 结果, 原因, SHA 集合, 各 manifest 摘要}`）。驱动在两步之间死掉时，下一条命令照同样的输入重算一遍，结果相同。

## 5. 状态与转换表

| 状态 | 含义（都由事件、证据和锁算出） |
|---|---|
| `ready` | 本轮已开，下一步还没有 `step_intent` |
| `implementing` / `verifying` / `reviewing` | 有一步开着（有 intent、没有 `step_recorded`），驱动持有锁。超过 `limit_seconds` 时加标记 `overdue`，状态不变 |
| `start_ambiguous` / `unknown` | 有一步开着、锁空着（第 2 节）；或证据无效；或事件日志无效。只能由人处理（第 6 节） |
| `verify_failed` / `changes_requested` / `step_failed` | 本轮已有否定判词，预算还有 |
| `over_budget` | 本轮已有否定判词，且 `已开轮数 ≥ max_rounds + 延期次数` |
| `passed` | 本轮判词是通过。终态 |
| `abandoned` | 记了放弃。终态。不表示进程已经停了 |

| 当前状态 | 命令或事件 | 结果 | 谁可以 | 拒绝时的文案 |
|---|---|---|---|---|
| （无） | `new` | `ready`，第 1 轮，计入预算 | 统筹方 | id 已存在：`lane <id> exists` |
| `ready` | `run` | 从本轮还没有开始的那一步起，依次进入 `implementing` → `verifying` → `reviewing` | 统筹方、夜跑循环 | 任务书或配置变了：`<file> changed since …` |
| 三个进行中状态 | 步骤结束（驱动记账） | 按第 4 节：下一步，或 `passed` / `verify_failed` / `changes_requested` / `step_failed` | 只有持锁的驱动 | — |
| 三个进行中状态 | 任何改状态的命令 | 不变 | — | `lane <id> is being driven by pid <n>`（退出码 3） |
| 三个进行中状态 | 驱动死亡 / 超过时限 | `unknown` 或 `start_ambiguous` / 加 `overdue` 标记 | 无（算出来的） | — |
| `unknown`、`start_ambiguous` | `resolve --kind failed\|cancelled` | `step_failed`，本轮关闭 | 人，记名 | 见第 6 节 |
| `unknown`、`start_ambiguous` | `resolve --kind still-unknown` | 不变 | 人，记名 | — |
| `unknown`、`start_ambiguous` | `run`、`next-round`、`extend` | 不变 | — | `round <n> <step> result is unknown; a person must resolve it` |
| 三个否定状态 | `next-round --brief <file>` | `ready`，轮次加一 | 统筹方 | — |
| 三个否定状态、`over_budget` | `run`、`resolve` | 不变 | — | `round <n> is closed (<result>); the only way on is next-round` / `round <n> already has a verdict` |
| `over_budget` | `next-round` | 不变 | — | `over budget: <used>/<budget>; extend first` |
| `over_budget` | `extend --by coordinator --reason` | 回到原否定状态，多一轮 | 统筹方，每条 lane 一次 | `the coordinator has used its one extension; the Owner decides at a terminal` |
| `over_budget` | `extend --by owner --reason` | 同上 | Owner：标准输入是终端，并照提示打回 lane id | `owner extensions need a terminal` |
| 其他状态 | `extend` | 不变 | — | `budget is not exhausted` |
| `passed` | `confirm-ended` 以外的改状态命令 | 不变 | — | `lane <id> passed in round <n>; it is closed` |
| 除 `passed`、`abandoned`、进行中以外 | `abandon --operator --reason` | `abandoned` | 统筹方或人 | — |
| `abandoned` | `confirm-ended` 以外的改状态命令 | 不变 | — | `lane <id> was abandoned` |
| 任何状态 | `confirm-ended --attempt` | 状态不变，只标记那次执行已确认结束 | 人，记名 | 有驱动在跑它，或它已有退出记录 |
| 任何状态 | 环境里有 `LANE_EXEC` 时的任何改状态命令 | 不变 | — | `a lane step cannot change a lane` |
| 事件日志无效 | 只读命令和 `abandon` 以外 | 不变 | — | `event log invalid at seq <n>; a person must inspect it` |
| 表里没有列出的组合 | 任何改状态的命令 | 不变 | — | `<command> is not allowed in state <state>` |

`passed` 只出现在「步骤结束」那一行，而那一行只在本轮还没有判词时发生；已有否定判词的轮，表里没有任何一行通向本轮的 `passed`。有效的验收 FAIL 走「三个否定状态 → `next-round`」，没有死路。所有命令入口查同一张表（实现为数据），不各写各的条件。

## 6. 人工补记 `unknown`

`lane.py resolve <id> --attempt <attempt_id> --kind … --operator <名字> --reason <文字> --evidence <看了什么>`，四项缺一拒绝；`--attempt` 必须是当前结果未知的那次执行。能追加的只有：

| `--kind` | 含义 | 之后 |
|---|---|---|
| `failed` / `cancelled` | 这一步没有成功 / 是人把它结束的 | 本轮判 `step_failed`；再做只能 `next-round`，照常查预算 |
| `still-unknown` | 看过了，仍无法确认 | 保持阻塞，留在队列里 |
| `exit-code --code <n>` | 有证据的真实退出码 | 证据只能是调用了 `wait` 的一方为这个 `attempt_id` 写下的退出记录。这样的一方只有两个：驱动（那就已经有 manifest，不会是未知）和将来的执行器（第 8 节）。所以第一片里这一种一律拒绝：`no wait-based exit record exists for attempt <id>`。日志里的一行字不是退出码。将来接受时，lane 补做第 2 节「结束后 2–4」，结果仍走第 4 节整张表：非零就是失败，零也要满足全部放行契约 |

拒绝的：没有 `passed` 这个取值；步骤已有有效的 manifest 时拒绝（`exit code is recorded (<n>); a resolution cannot replace it`）；本轮已有判词时拒绝（`round <n> already has a verdict`），所以「先修」和验收 FAIL 改不成通过，复核过的轮也开不回来；有驱动在跑时拒绝；在步骤里调用时拒绝。证据不能证明成功，就只有两条路：保持阻塞，或者关成未成功。

## 7. 旧的执行与下一轮

- **规则**：`unknown`、`abandoned`、人工关闭都只是记账，不表示进程结束了；lane 锁空着也不表示目录可以再用；lane 不声称回收过任何东西。因此 lane 只在它刚刚独占创建的目录里启动步骤，任何一次执行用过的 `work/`、`out/` 都不再交给后来的步骤。所以「旧执行可能还在写的目录」里不可能推进：每轮、每步都是新目录，下一轮的检出按提交号从旧目录克隆出来，旧进程之后再写什么都进不来。旧进程后来的推送也不影响判定，因为固定的是本地提交号，不是分支头。
- **启动歧义**：先落 `step_intent`，再启动，`step_started` 紧跟在启动返回之后。两者之间驱动死掉就是 `start_ambiguous`，如实显示，不关成失败，也不说已回收。子进程的参数里带着含 `attempt_id` 的路径，人可以用 `pgrep -f <attempt_id>` 找它。
- 没有 manifest 的执行在有人用 `confirm-ended`（记名、写明怎么确认的）之前，一直列在队列里：`execution not confirmed ended: <attempt_id>`。正常退出后留下的后台后代 lane 看不见，这部分只靠隔离，以及「记账后产物再变就失效」（第 2 节）。

## 8. 无人值守

复核 21 给了两个做法：(a) 时限由 lane 之外的执行器或宿主边界强制，lane 只收到「这次执行被取消 / 超时」这个事实；(b) lane 只标记「超时，等人」，这条 lane 的夜跑停在这里。

**第一片选 (b)。** 每步的 `limit_seconds` 记在 intent 里；超过后驱动追加一条 `step_overdue`，队列标 `needs: person`，此外什么都不做。理由：① 第一版的问题几乎都出在管进程的代码上，执行器就是这类代码，应该单独设计、单独复核，不该夹在这一片里；② 现在的宿主是会睡眠的笔记本（ADR §12.9 第 9 条记过一轮被冻住 5 小时），按墙上时钟强制超时会在唤醒时结束本来正常的步骤；③ 判定表已经留了 `termination` 一行，以后接 (a) 不用改判定。代价：一步挂住，这条 lane 就停到人来，失控的实现者继续耗额度；别的 lane 只要由各自的 `run` 进程驱动就不受影响（每条 lane 一把锁，没有共用的文件）。驱动还在时，人按记录的 pid 核对启动时间后手工结束进程，驱动的 `wait()` 会如实记成 `ended by signal <n>`。

**(a) 需要的东西**：一个 lane 之外的执行器（最终是 `agentd`，ADR §12.3）：它是子进程的父进程，用不计睡眠的时钟计时，只结束自己还没收尸的那个孩子所在的组，从不按磁盘上的 PID 发信号；它独占写一份带 `attempt_id` 的退出记录（真实的 `wait` 结果和 `termination`）；取消入口在步骤里调用时拒绝，也不能指向已经关闭的执行。不论 (a) 还是 (b)：停止不改判词、不重开步骤、不返还预算、不触发任何重跑。

## 9. 预算、队列和看板

- **一处检查**：轮次只在 `new` 和 `next-round` 里产生，两处调同一个 `may_open_round`：`已开轮数 < max_rounds + 延期次数`。`run` 不开轮。一轮里每步只有一次执行，失败、取消、未知都算用掉这一轮，没有别的入口能再跑一次。
- **延期**：只在 `over_budget` 时受理，每次加一轮，记 `extension{by, reason, at, new_budget}`。`coordinator` 每条 lane 一次；`owner` 要终端加打回 lane id。同用户可以伪造终端，这不是安全边界（第 1 节）；状态迁到平台后，Owner 的延期改成一张审批单。延期显示在 `status`、`queue` 和看板上：`budget 2+1 (coordinator, <时间>: <原因>)`。
- **队列**：`lane.py queue` 列出每条不是 `passed`、也不是正常在跑的 lane：`ready`、三个否定状态、`over_budget`、`unknown`、`start_ambiguous`、带 `overdue` 的，以及任何还有「未确认结束的执行」的 lane（包括 `abandoned` 的）。每行 `{id, title, state, round, budget, why_waiting, needs, since}`，`needs` 是 `coordinator` / `person` / `owner`（超预算且统筹方的延期已用）。`queue --check` 在有 `person` 或 `owner` 项时退出码非零，供看守脚本叫醒人，不靠模型记着去看。
- **看板**：每条改状态的命令结束时由事件重新生成，形状沿用 TASK.md：`{"works": [{"title", "short", "goal", "round", "steps": [{"name", "who", "progress", "done", "pattern", "usual_min"}]}]}`。`progress` 是 `out/stdout`；`done` 是 manifest 发布后写的 `rec/done`（`exit=<code>`，只给看板，lane 从不读回）；`pattern` 是 `attempt_id`。另加 `state`、`reason`、`budget`、`needs`；没有值的字段不出现，不写空值。没有任何命令读看板文件。

## 10. 验收清单

每一行对应复核报告里的一条发现。「不可能」表示这个缺陷在本设计里没有存在的位置；测试写成「输入 → 期望的状态和原因」；只回答了一部分的写明。

| 发现 | 处置 |
|---|---|
| 16-P1 失败或崩溃仍可通过 | **T01** verify 末行 `VERDICT: pass`、退出码 7 → `step_failed`，`verify exited 7`，review 没有 intent。**T02** review 报告完整写着 `safe to merge`、退出码 9 → `step_failed`，`review exited 9` |
| 16-P1 没有同轮、同提交及报告来源约束 | 追加打开、复用目录、读共享 `verify.txt`、接受预先写好的报告都不可能（独占创建，`out/` 启动时必须为空，只读被引用的 manifest）；每条判词带 SHA 集合和各 manifest 的摘要。**T03** attempt 目录已存在 → 拒绝启动，无新事件。**T04** `work/verify.txt` 里放一份旧的 `VERDICT: pass`，本次 stdout 没有判词 → `step_failed`，`verify produced no verdict`。review 只在本轮 verify 对同一 SHA 集合通过后才有 intent（第 4 节第 15 行） |
| 16-P1 同一 lane 没有互斥锁 | **T05** 两个真实进程同时 `run` → 后一个退出码 3，`lane <id> is being driven by pid <n>`，事件数不变。临时文件名带随机后缀 |
| 16-P1 预算授权可自签 | **T06** 环境里有 `LANE_EXEC` 时调 `run` / `next-round` / `extend` / `resolve` / `abandon` → 全部拒绝。**T07** 第二次 `extend --by coordinator`、非终端的 `--by owner`、未超预算的 `extend` → 各自拒绝。**T08** 预算用尽时 `next-round` → 拒绝，`over budget: 2/2`；`run` 在任何状态都不产生开轮事件。**T09** 手改事件日志中间一行 → `unknown`，`event log invalid at seq <n>`。只回答了一部分：同用户重写整条链查不出来（第 1 节） |
| 16-P1 路径能注入 shell 命令 | 不可能：没有 shell。**T10** 工作路径含 `$(touch X)`、反引号、双引号、空格 → 子进程收到一个参数，`X` 不存在；字符串形式的模板在加载时被拒绝 |
| 16-P2 崩溃恢复不能可靠接续 | 接续不存在：没有恢复、没有等待旧 PID。**T11** 驱动在 `step_intent` 之后、`step_started` 之前被杀 → `start_ambiguous`；`run` 拒绝。**T12** 驱动在等待中被杀、孩子继续跑 → `unknown`；`run` 拒绝，没有第二个子进程 |
| 16-P2 stall / abandon 留下继续运行的实现者 | 只回答了一部分：lane 不结束它（已定）。lane 不再说它停了：**T13** T12 之后旧孩子继续在旧 `work/` 里写和提交；`resolve --kind failed`、`next-round`、`run` → 新一轮的 SHA 集合和快照里没有旧孩子后来写的东西。**T14** `abandon` 一条有未知步骤的 lane → `abandoned`，队列仍列出 `execution not confirmed ended`，`confirm-ended` 之后才消失 |
| 16-P2 queue 隐藏最需要处理的 lane；status 只回显磁盘 | **T15** 每种状态各建一条 lane → 队列列出除 `passed` 和正常在跑以外的全部，`needs` 逐条正确；超预算且统筹延期已用 → `needs: owner`。T12 里 `status` 显示 `unknown`，不显示 `implementing` |
| 16-P2 判词解析误收也误拒 | **T16** verify stdout 中间的代码块里有 `VERDICT: pass`、末行是别的 → `step_failed`，`verify produced no verdict`。**T17** review 报告带 BOM 和前导空行 → 正常识别；缺 `END OF REPORT` → `step_failed`，`review report is truncated`。只回答了一部分：没有改成结构化的结果文件，沿用「退出码 + 恰好的首尾行」，完成标记是 `END OF REPORT` |
| 17-P1 `done` 覆盖真实退出码 | 不可能：没有被读回的完成文件。**T18** 孩子在 `out/`、`work/` 里写 `done` 和 `manifest.json` 声称 0，实际退出码 9 → `step_failed`，`implement exited 9` |
| 17-P1 HEAD 一致不保证验收的是该提交内容 | 验收的不再是实现者的目录。**T19** verify 在快照里改已跟踪文件不提交 / 留下未跟踪文件 / review 改文件 → `step_failed`，`snapshot of <repo> changed during <step>`。**T20** 实现者目录里有未提交改动和被忽略的构建产物 → 快照里都没有，记一条提示，判定不受影响 |
| 17-P2 运行时无法 `stop` / `abandon` | `stop` 已删；驱动在跑时 `abandon` 被拒绝（退出码 3）。只回答了一部分：结束失控进程的能力没有了，见第 8 节和 T38 |
| 17-P2 只确认组长死亡，可能留下子进程 | lane 不回收、也不记「已回收」，这个错误的断言不可能出现。残留的后代只靠隔离（T13）和 T27；只回答了一部分 |
| 17-P2 启动崩溃窗口留下无法回收的进程 | 窗口消除不了，改成如实命名：T11。不再关成 `failed`。只回答了一部分 |
| 17-P2 queue 仍隐藏崩溃后待处理的 lane | T12、T15：驱动死后队列列出，`needs: person` |
| 17-P2 verify 判词并非取自 stdout | **T21** `VERDICT: pass` 只出现在 stderr → `step_failed`，`verify produced no verdict` |
| 20-P1 `stop → retry` 绕过复核结论和轮次限制 | 不可能：没有这两个命令，每轮每步一次执行。**T22** 表驱动：第 5 节每个（状态 × 命令）组合各调一次，结果与表逐格相同；从任何已有否定判词的轮出发，穷举长度不超过 4 的命令序列，到不了本轮 `passed`。**T23** review 写出 `VERDICT: fix first` 后被人手工结束 → `step_failed`；下一轮固定出同一 SHA 集合 → `step_failed`，`no new commit since the review in round 1` |
| 20-P1 恢复可能误杀复用 PGID 的无关任务 | 不可能：程序里没有发信号的调用。**T24** 静态检查：源码里没有 `os.kill`、`killpg`、`send_signal`、`terminate`、`.kill(`，也没有读回 PID 再等待的代码 |
| 20-P1 未跟踪文件检查受 Git 配置影响 | **T25** 全局和仓库配置都写 `status.showUntrackedFiles=no`，全局 ignore 写 `*` → 快照里的未跟踪文件仍被发现 |
| 20-P2 启动崩溃窗口仍存在（延迟注册的 runner 仍会执行） | runner 和握手已删。「阻止已关闭的执行继续跑」做不到；它只能写自己的旧目录（T13），状态如实是 `start_ambiguous`（T11）。只回答了一部分 |
| 20-P2 验收 FAIL 无法进入下一轮 | **T26** verify 退出码 1、末行 `VERDICT: FAIL (2 checks failed or produced no result)` → `verify_failed`；`next-round` 接受，进入第 2 轮 `ready` |
| 20-P2 正常退出留下的组员无法再被停止 | 只回答了一部分：lane 不停任何进程。**T27** 记账后往 `out/stdout` 追加一个字节（模拟残留后代）→ 判词之前 `unknown`，`evidence invalid`；`passed` 之后 `pass-set` 拒绝，`evidence changed after the verdict`。写旧 `work/` 的情况见 T13 |
| 21-P1 人工补记不能成为改判入口 | **T28** `--kind passed` → 参数被拒；对已有 manifest（退出码 9）的步骤 `resolve` → 拒绝，`exit code is recorded (9)`；对已有判词的轮 → 拒绝；缺 `--operator` / `--reason` / `--evidence` / `--attempt`，或 attempt 不是结果未知的那个 → 拒绝。**T29** `--kind exit-code --code 0` → 拒绝，`no wait-based exit record exists`。**T30** `--kind failed` → `step_failed`，`implement closed as failed by <operator>: <reason>`；`still-unknown` → 仍是 `unknown`；之后 `next-round` 在预算用尽时被拒 |
| 21-P1 纯函数还缺完整放行契约 | 第 4 节。**T31** 对放行契约的每个字段逐一置缺或置坏（缺 manifest、`exit.code` 为空、有信号、`termination` 非 `exited`、判词多一个字符、报告截断、快照检查里 git 非零退出）→ 没有一个是 `passed`，原因是表里最靠前命中的那一条。FAIL 的推进见 T26 |
| 21-P1 新目录不能证明产物归属和完整性 | 第 2 节。**T32** manifest 的 `exec` 与 intent 不同 / `intent_sha256` 不符 / 只有 `manifest.json.tmp-*` / manifest 没有被事件引用 → `unknown`，`evidence invalid: …`。另见 T03、T04、T18、T27 |
| 21-P1 四次 HEAD＋clean 仍不足 | 第 3 节。**T33** 快照里对一个文件设 `assume-unchanged` 或 `skip-worktree` 后修改 → `step_failed`，`hidden index flag in <repo>`。**T34** 固定提交的树里有 gitlink → verify 不启动，`step_failed`，`submodule at <path>: …`。另见 T19、T20、T25。只回答了一部分：子模块在第一片是拒绝而不是递归固定；验收命令自己在快照里「改了又改回」查不出来，接受（它是统筹方的脚本，已按摘要固定）；主机共享的依赖缓存不在快照内 |
| 21-P1 通过必须绑定提交集合，合并还需要独立闸门 | **T35** 通过之后 amend 出树相同的新提交 → `pass-set` 给的仍是原提交号，新提交号没有通过记录。`pass-set` 在证据变动后拒绝（T27）。只回答了一部分：合并闸门不在第一片，通过到合并之间的窗口没有被程序封住（第 3 节末） |
| 21-P2 防止旧执行与下一轮重叠 | 第 7 节；T11、T13、T14。**T36** 驱动被杀、孩子还在 → 另一个进程拿得到 lane 锁（锁没有被孩子继承），状态是 `unknown` |
| 21-P2 无人值守需要明确取舍 | 第 8 节选 (b)。**T37** 步骤超过 `limit_seconds` → 一条 `step_overdue`，状态不变，队列 `needs: person`，进程没有收到信号。**T38** 人手工 TERM 掉超时的孩子（驱动还在）→ `step_failed`，`review ended by signal 15`；没有新的执行，预算没有返还。只回答了一部分：整夜持续推进这一目标在第一片不满足，等 Owner 定第 12 节 |
| 21-P2 预算和待处理队列由程序持有 | 第 9 节；T07、T08、T15、T30。**T39** 删掉生成的看板文件后重新生成 → 内容相同，形状符合 TASK.md，没有空值。**T40** 夜跑循环的示例脚本只调用 `run`、`queue`、`status`、`board`（静态检查）。只回答了一部分：Owner 的终端入口挡不住同用户冒充（已接受） |
| 21 旧问题归类里「仍存在或转化」的六项 | 启动登记窗口 T11；残留孩子 T13、T27；挂起的步骤 T37、T38；队列遗漏 T15；预算授权 T07、T08；验收 FAIL 的推进 T26 |
| 21 新风险：补记洗白失败；记录关闭被读成执行结束；不可变判词引用可变产物 | T28–T30；T14；T27 和 `pass-set` 的重算 |
| 21 结语：记录器和所有命令入口执行同一套约束 | T22：所有入口查同一张转换表；所有视图调同一个 `lane_state` |

## 11. 分片

- **第一片**：Python 标准库，一个命令行，放 `agent-config/scripts/lane/`，从空目录写起，不在 `w31/w66-lane` 上改。内容：`new`、`run`、`next-round`、`extend`、`resolve`（三种）、`confirm-ended`、`abandon`、`status`、`queue`、`board`、`pass-set`；第 2–9 节的协议、判定表、转换表；T01–T40。按表和测试验收，不拿行数当验收。链停在 `passed`。
- **以后**：合并闸门及其后的主线 CI、测试环境、台账状态（W-66 ③④）；执行器强制的时限和取消（随 `agentd`）；`exit-code` 补记；子模块递归固定；`inputs`；状态迁到平台（事件 → `agentrt.event`，manifest 和产物 → 按内容哈希的 `artifact`，判词 → `verification`，轮次预算 → `budget_ledger`，lane 锁 → 租约，Owner 延期 → 审批单；DESIGN 7.2–7.5）。

## 12. 需要 Owner 定的

只有一项：**第一片是否接受夜跑会停在挂住的步骤上。** 这会改 W-66 的验收句：统筹线程除了「先修」和「超预算」，还会在「结果未知」和「超时」时被叫醒，而后两种要人到场。推荐 A；第 13 节第 3 条核对出有上限就按 C；B 作为下一片，和 `agentd` 一起做。

| 选项 | 内容 | 代价 |
|---|---|---|
| A（推荐） | 第一片用 (b)，验收句照上面改 | 一步挂住，那条 lane 停到早上；失控的实现者继续耗额度 |
| B | 先做执行器 (a)，再允许无人值守 | 多一个管进程的程序和一轮设计复核；第一片推迟 |
| C | A，再加上给实现者和复核者的命令行配它们自带的时长或额度上限 | 取决于这两个命令行有没有这种上限（第 13 节第 3 条）；有就几乎没有成本 |

## 13. 实现前要核对的假设

1. 从一个执行目录 `git clone --no-checkout` 再按提交号 `checkout --detach`，能取到没有推送的提交：在 `~/agent-work/` 下拿任意两个仓库试一次。
2. `verify-branch.sh` 能在普通克隆（不是 `git worktree`）组成的目录里跑通，包括它调用的 `check_hardcoded_paths.py --worktree` 和 `code-health/scan.sh --root`：在快照布局里跑一遍，对照同一提交在现有任务目录里的结果。
3. `cursor-agent -p` 和 `codex exec` 失败、被限流或额度用尽时的退出码是否非零，以及有没有自带的时长或额度上限：读两者的 `--help`，各做一次故意失败的调用。`codex exec --output-last-message` 是否总是新建报告文件，同样确认。
4. `GIT_CONFIG_GLOBAL` / `GIT_CONFIG_SYSTEM` 在本机 Git 上生效（`git --version` 是 2.50.1；T25 就是这条的检查）；Python 的 `fcntl.flock` 在 macOS 上随进程死亡释放，且默认不被子进程继承（T36）。
5. 看板的读取方（`~/agent-work/status/board.py`）接受多出来的字段和省略的字段：读它的解析代码；服务端的校验见 LESSONS 第 55 行。
6. 每次执行一份克隆加依赖安装的耗时和磁盘占用：对 `bifrost-platform` 量一次，写回 `usual_min`。
7. 夜间本机是否保持唤醒；不保持的话 `limit_seconds` 的 `overdue` 标记会在唤醒时集中出现，只是标记，不影响判定。
