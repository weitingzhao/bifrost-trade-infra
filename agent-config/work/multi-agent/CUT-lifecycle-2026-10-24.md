# 第 4 轮 4.6 切法：分支、工作目录、磁盘的生命周期（2026-10-24）

> 状态：切法草案 + 一次只读盘点（清单在同目录 `INVENTORY-lifecycle-2026-10-24.md`）。**这一步没有删任何东西。**
> 依据：第 4 轮草案 4.6（Claude Doc「小牛牛包工队全面盘点」第二个标签页；Owner 10-23 23:3x「D2 A、D3 A、D4 A，其余按推荐，开第 4 轮第一波」）；
> Owner 10-23 原话「版本分支的清理和保持，之前发生过我本地的硬盘全部占满的情况」；TD-415、TD-383、TD-299；
> `CUT-gitea-primary-2026-10-17.md` §6、§9.2、§9.6；infra `15271dd`（`prune-merged-branches.sh` 不碰 `agent/**`）。
>
> **做完标准**（草案原文）：一周不手工清理，磁盘余量和分支数不涨。第 4 轮之后统筹可能搬到 Mac mini（4.4），
> 所以下面的规则按「每台跑 Agent 的机器」写：同一份脚本、同一份配置，机器之间只差根目录和调度方式。

---

## 1. 现状（2026-10-23 23:44 – 10-24 00:00 CDT 实测，只读）

数字的命令和逐条清单见 `INVENTORY-lifecycle-2026-10-24.md`。和 10-23 盘点不同的地方用 **粗体** 标出。

### 1.1 分支

| 位置 | 数量（不含 main） | 说明 |
|---|---|---|
| Gitea `agent/**` | **27**（platform 25、infra 2） | 10-23 23:02 时 infra 还有 15 条，**到 23:50 只剩 2 条**：13 条在这一小时内没了，剩下的正是规则要留的那类，所以很可能是 agentd 按 `store/prune.go` 删的（删除记录没读）。27 条逐条查了任务状态（PROD / STG `get_task`）：**20 条是「收下但没进 main」**（规则保留，几乎都是演练和基准题），**7 条按规则早该删了却还在**（任务取消超过 24 小时 5 条；被取代的尝试 2 条） |
| Gitea 人的分支 | 53（platform 24、infra 22、插件 4、worker 3） | 已合入 41（其中 31 条超过 24 小时）、未合入 12（10-10 – 10-12 停线留作材料的 `w31/w56-*`、`w31/w66-*` 等，和 10-22 的 `w31/td-411-dryrun`） |
| GitHub（公开） | **157**，没有一条 `agent/` | 切换那刻冻结（9.2）。130 条已在 main（祖先或同 Change-Id），27 条不在 main，**其中 16 条 Gitea 上也没有**：GitHub 是它们唯一的远端副本 |
| 本机本地分支 | 489（platform 231、infra 181，其余 77） | 可从 git 恢复的 437，只在本地有提交的 37，检出在正在用的 worktree 里的 15 |

### 1.2 工作目录

| 位置 | 数量 | 说明 |
|---|---|---|
| 本机 worktree（不含 11 个主 checkout） | 334：platform 178、infra 117、ui 25、frontend 5、research 5、插件 4 | `~/agent-work` 下 314；工作区根 13 + `.worktrees/` 6；`$TMPDIR` 里 1 个（`push-main.sh` 被杀时漏下的；显示 12 处删除，多半是 macOS 清掉了 `$TMPDIR` 里的旧文件，推测） |
| 其中可从 git 恢复、干净、24 小时没动、没有进程在用 | **295**（8.8 GB） | 285 个 HEAD 已合入 main，10 个 HEAD 的提交都在 Gitea 现有分支上 |
| 有未提交改动或只在本地的提交 | 21（5.5 GB） | 其中 5 个只是多了能再生成的东西（`.cache/`、`.venv`、`.husky/_`、`*.tsbuildinfo`），td-329、td-333 两个里各有 1–2 GB 的 Go 缓存 |
| 正在用（24 小时内有改动或有进程） | 17 | 第 4 轮各线（`r4-*`）、BI-1、r3-35 等 |
| 工作区根下 14 个旧目录 | 13 个 worktree + `bifrost-platform-phase3-notes`（48 KB 笔记，不是 git） | 可清 10；`phase3-int`、`phase3-s1` 只多了生成文件；`bifrost-platform-d1` 有 1 个只在本地的提交（`a7b86813`） |

### 1.3 `~/agent-work`（868 项，58.1 GB）

| 类 | 数量 | 大小 | 说明 |
|---|---|---|---|
| `.cache`（共享缓存） | 1 | 20.2 GB | `go-build` 18.6 GB；**一个名叫 `go-build GOMODCACHE=` 的目录 1.1 GB**（某次 `GOCACHE="… GOMODCACHE=…"` 引号写错，缓存写进了这个名字）；另有 lane 把 `.cache` 当草稿目录用（`gates-*`、`paints-*` 等） |
| `codex-review-*` | 472 | 18.2 GB | **10-23 写的「472 个约各 1.1 GB」不对**：10-21 清过之后 425 个小于 10 MB；**35 个目录里有 16.3 GB 可再生成的缓存，目录名有 7 种**（`go-cache`、`cache`、`.cache`、`.review-cache`、`.gocache`、`go-build`、`review-cache`），`disk-guard.sh` 只认 `gocache tmp .tmp .check-tmp`，**认得的只有 0.63 GB**；**52 个没有 `run.done`**（中途停的复核，合计 4.1 GB，几乎全是其中 9 个目录里的缓存），`disk-guard.sh` 只清有 `run.done` 的，所以连认得名字的那 0.63 GB 也清不掉 |
| 复核记录 | — | 约 2 GB 以内 | 约 447 个复核编号里只有 132 个的报告抄进了仓库 `work/multi-agent/reviews/`；仓库文档按 `~/agent-work/codex-review-<n>/REPORT.md` 路径引用的有 31 个。**直接删复核目录会丢记录** |
| 含 worktree 的 lane 目录 | 228 | 14.2 GB | 其中 196 个里的 worktree 全部可清 |
| 普通目录 / 文件 | 75 / 69 | 5.2 GB / 0 | 72 个目录 14 天内动过（`r3-35-scratch` 1.6 GB、`bi1-*-scratch`、`merge-accepted` 0.8 GB 等）；主人只能从名字猜 |
| 软链接 | 7 | — | 指回工作区的仓库；`bifrost-finance` 是真克隆（第 13 个仓库，只在这里，`prune-merged-branches.sh` 只扫工作区兄弟目录，扫不到它） |

### 1.4 这台 Mac 的其余部分

- 数据卷 926 GB，可用 357–365 GB（60% 已用）；默认 Go 缓存 12 GB；Docker 构建缓存 **21.3 GB**（328 项，每周只删 7 天前的）；
  Cursor `state.vscdb` 51.4 GB（`disk-guard.sh` 每小时报一次，要 Cursor 关着才能压缩）；会话 scratchpad 3.35 GB（`/private/tmp`，系统自己清）；
  `~/bifrost-backups/git-branches` 104 MB（4 天的分支备份，没有保留期）；本地 Time Machine 快照 22 个。
- `disk-guard.sh` **只在 `~/agent-work/bin`，不在任何仓库**：搬到 mini 时会丢；它的 `KEEP` 是写死的名字（`chief-exam.*`、`w31-25-slice5.*`……），新线不在名单里也不会被保护，只靠「24 小时没动」。
- 只写日志，不进 Prometheus、不进 Console。Prometheus 只抓集群 5 个节点的 node-exporter：**这台 Mac、两台 mini、06 都没有主机指标**。

### 1.5 06（agentd 主机）与两台 mini

- agentd 已有三样（代码在 `bifrost-platform/api/internal/agentd/`）：尝试结束后清工作目录（`disk.go` `removeWorkspace`）；
  按平台规则删 `agent/**` 分支（`prune.go`，每 10 分钟，每次最多 50 条，`store/prune.go` 的 `PruneAfter` 24 小时）；
  每次领活带剩余磁盘，低于下限（默认 15 GiB，`AGENTRT_DISK_FLOOR_GIB`）不派新活、记 `policy_alert` 并推送给 Owner（`store/hostdisk.go`）。
- **没查到**：06 现在剩多少盘、`AGENTD_ROOT` 下有没有工作区以外的残留（基准、考试、测试库）、06 上跑的 agentd 是否已含 `removeWorkspace`——Agent 登不上 06；
  平台只在跨过下限时记一条事件，没有指标可读。两台 mini 同理没查。

### 1.6 集群 `cicd`（只读 get）

| 对象 | 数量 | 说明 |
|---|---|---|
| PipelineRun | 305（最早 10-17） | **已有清理**：CronJob `tekton-pipelinerun-ttl`（`k8s/cicd/tekton/pipelinerun-ttl.yaml`，每小时）删 7 天前结束的 PipelineRun，删 2 天前结束的 TaskRun 的 Pod；CronJob 建于 2026-08-10（infra `73e181f`），10-24 04:20Z 最近一次成功。TD-299 写的「`kubectl -n cicd get cronjob` 什么都没有」和这对不上（原因没查），正文要改。Owner 10-10 定的规则（成功 24 小时、失败 7 天、每条流水线至少留 5 个、有发布记录才删）**没实现**，现在是一刀切 7 天 |
| PVC | 284（local-path 282） | 277 个属于 PipelineRun（`volumeClaimTemplate`），随 PipelineRun 一起删；4 个属于 06-19 的单独 TaskRun（`bifrost-refresh-dockerfile-cms`）；3 个是 Gitea、registry 的数据卷。请求合计 950 Gi，169 个在 04、93 个在 05（local-path 不限额，实际占用要上节点看，没看） |
| TaskRun | 3021 | 2546 个属于 PipelineRun；**475 个单独的 TaskRun 没人清**（`github-sync-*` 353 个、`gitea-mirror-sync` 61 个……），其中 122 个超过 7 天。Gitea 做主后每次推送起一个 `github-sync`，这一类每天涨几十个 |
| 发布记录 ConfigMap | 550 | 发布证据，留着 |
| 节点根盘可用 | 04 132 GB（28%）、02 132 GB（28%）、05 227 GB（49%）、01 407 GB（87%） | 只有 `BifrostPostgresNodeDiskLow`（.70、.75 低于 50 GB）一条盘告警 |

---

## 2. 原则

1. **能从 git 恢复的自动清**：分支已合入 main（同 Change-Id，没有 Change-Id 时同标题，和 `prune-merged-branches.sh` 同一条判据），或提交都在 Gitea 现有的分支上；
   worktree 干净（只多了能再生成的东西也算干净）、24 小时没有文件改动、没有进程以它为 cwd。
2. **只报不删**：有未提交的改动；有只在本地的提交；`locked`；认不出主人。报的东西进每日清单，不进 Owner 的待办——除非有一个具体要他定的动作（见 §6）。
3. **删之前留回退**：远端分支删前打 bundle 并记 `名字 → sha`（`prune-merged-branches.sh --apply` 已经这样做）；本地分支同样；worktree 删前记 `路径 → HEAD`；复核记录删前归档。
4. **主人是登记出来的，不是猜出来的**：从现在起每个工作目录在建的时候登记属于哪件活；历史上没登记的按 §3 的判据走，判不了就只报。
5. **一份实现，每台机器一样**：脚本进 infra 仓库，参数是 `AGENT_WORK`（根目录）、数据卷、阈值；macOS 用 LaunchAgent，Linux 用 systemd timer；agentd 主机上 agentd 自己管它的根目录。

---

## 3. 规则：每样东西属于哪件活、什么时候可以清、谁来清

| # | 东西 | 属于哪件活（怎么认） | 什么时候可以清 | 谁来清 | 只报不删 |
|---|---|---|---|---|---|
| R1 | agentd 尝试工作区（06；以后 mini） | 任务 + 尝试（`tasks/<task>/a<n>`） | 尝试结束、结果已交平台 | agentd（已有：`removeWorkspace`） | agentd 起不来时留着；平台按下限停派 |
| R2 | Gitea `agent/<task>/a<n>` | 任务（分支名就是任务号） | 规则已有：任务取消 / 驳回、被取代、收下且已进 main、收下且标了 `no_merge`，满 24 小时（`store/prune.go`）。**补一条**：尝试没有记下推送的提交（被叫停、主机被停）的分支，任务结束 7 天后按「放弃」删 | agentd，用它自己的 Gitea 身份（已有） | 任务还开着；收下但没进 main 也没标 `no_merge`（4.1 上线后这类会自己进 main 再被删；**历史的 20 条要先定，见 D-L5**） |
| R3 | Gitea 人的分支（`w31/`、`cursor/`、`codex/`、`fix/`、`night/`） | 工作项（分支名、提交的 `Work:` 与 `Claude-Session:` 尾注） | 已合入 main 且分支头超过 24 小时 | 统筹机器上的定时任务跑 `prune-merged-branches.sh --apply`（删前打 bundle）——**要不要他点头见 D-L1** | 没合入的：每日清单列出；按 D-L2 处理 |
| R4 | GitHub 上冻结的分支 | 同 R3 | 已在 main 且 Gitea 有同名分支或已合入 | 见 D-L3（要 Owner 的 GitHub 凭证或他亲手） | 只在 GitHub 有的 16 条：先拷进 Gitea 再说 |
| R5 | 本地 worktree（统筹机器） | 登记文件（§4.2）；没登记的看分支名和 `Claude-Session` 尾注 | 原则 1 成立 | 定时任务（`git worktree remove`，不加 `--force`；只多了生成文件的先删生成文件） | 原则 2 |
| R6 | 本地分支 | 同 R5 | 已合入或提交都在 Gitea 现有分支上，且没有检出在要留的 worktree 里 | 定时任务（`branch -D`，删前 bundle + `refs.tsv`） | 有只在本地的提交（37 条，清单里逐条） |
| R7 | 工作区根的旧目录、`.worktrees/` | 同 R5 | 同 R5 | 同 R5；**以后不在工作区根建 worktree**（只建在 `$AGENT_WORK/<线>/`） | 同 R5；`phase3-notes` 这类非 git 目录只报 |
| R8 | 复核目录 `codex-review-<n>`、`claude-review-*`、`cursor-review-*` | 复核号（目录名） | **缓存**：`run.done` 后 2 小时，或 24 小时没动（中途停的复核），删全部可再生成的子目录（§4.1 的名单）。**记录**（`BRIEF.md`、`REPORT.md`、`LAST.md`、日志）按 D-L4 | 定时任务 | 记录按 D-L4 定之前一律留 |
| R9 | 共享缓存 `$AGENT_WORK/.cache` | 所有线共用 | `go-build` 超过上限（建议 20 GB）且没有 Go 构建在跑时 `go clean -cache`；名字里带空格或 `=` 的目录（引号写错的产物）直接删 | 定时任务 | 不是缓存的草稿目录（`gates-*`、`paints-*`）：每日清单列出，交给建它的线 |
| R10 | lane 目录里 git 以外的剩余、普通目录和文件 | 登记文件；没登记的只能猜 | 跟 R8 的记录同一规则（D-L4） | 定时任务 | 没登记且 14 天内动过的一律只报 |
| R11 | 工具自己的临时 checkout：`$TMPDIR/push-main.*`、`$AGENT_WORK/merge-accepted/<task>/` | 建它的工具 | HEAD 在 main 上（这两类都是 main 上的 detached checkout）、超过 1 天 | 定时任务；工具自己的 `trap` 照旧 | — |
| R12 | 分支备份 `~/bifrost-backups/git-branches/<日期>` | `prune-merged-branches.sh` | 90 天 | 定时任务 | — |
| R13 | Docker、默认 Go 缓存、Time Machine 本地快照 | 这台 Mac | 照 `disk-guard.sh` 现有规则（Owner 10-21 定的） | 定时任务 | Cursor `state.vscdb`：只报（要 Cursor 关着，他自己做） |
| R14 | Tekton PipelineRun 与它的工作区卷 | 流水线（`pipelineRef`） | 按 Owner 10-10 的规则：成功 24 小时、失败 7 天、每条流水线至少留 5 个、交付类有发布记录才删 | `tekton-pipelinerun-ttl` CronJob（改它，不新建）；改动由 Owner 批 apply（`cicd` 写入） | 没有发布记录的交付 run |
| R15 | 单独的 TaskRun（`github-sync-*`、`gitea-mirror-sync-*`……）与它们的 PVC | 建它的触发器 | 结束 2 天 | 同 R14，CronJob 加第三遍 | 失败的留 7 天 |
| R16 | 发布记录 ConfigMap | 发布 | 不清（发布证据） | — | — |

**与 4.1「交房」的衔接**：4.1 让收下的结果自动进 main；进 main 后平台的 `RecordLandings` 记下落地，R2 的规则 24 小时后由 agentd 删分支，4.6 不另写删除。
4.1 必须保证落地能被认出来：手工 cherry-pick 时 Change-Id 会变（10-20 合 M-9 的 TD-378 就是：分支上的 `Ib1c84f…` 到了 main 成了 `I1ae317…`），平台靠 `Agentrt-Task` 尾注认，所以自动合入要保留 `Agentrt-Task`。
**还有一个要 4.1 先挡住的坑**：历史上 20 条「收下没合」的结果里绝大多数是演练和基准题，4.1 一打开，若按「所有收下的都合」去扫，会把这些演练合进 main。4.1 只合打开之后收下的，或者先按 D-L5 给它们标 `no_merge`。

---

## 4. 机制

### 4.1 一个清扫脚本，每台机器一样

把 `~/agent-work/bin/disk-guard.sh` 搬进 infra `scripts/agent-host/disk-guard.sh`（连同 LaunchAgent 的 plist 和一个安装脚本），改成：

- `AGENT_WORK`、数据卷、`WARN_GB`（30）、`STOP_GB`（15）都从环境读，默认值就是今天这台 Mac 的；
- 可再生成的目录名一份名单，复核、lane、worktree 共用：`gocache go-cache go-build .gocache cache .cache .review-cache review-cache tmp .tmp .check-tmp node_modules .venv .husky/_ *.tsbuildinfo`；
- 复核目录不再要求 `run.done`：`run.done` 后 2 小时，或整个目录 24 小时没动；
- 写死的 `KEEP` 换成登记文件（§4.2）：登记着、活还没结束的不碰；
- 每次跑完写一份状态 `$AGENT_WORK/status/lifecycle.json`（剩余空间、各类计数、只报不删的清单），并按 §4.4 上报；
- 调 `prune-merged-branches.sh --apply --local`（本地部分），远端部分按 D-L1。

`prune-merged-branches.sh` 要补的（都在 infra，有测试）：

1. worktree 的「干净」用同一份可再生成名单（今天只认 `node_modules`，所以 td-329、td-333 这种只多了 `.cache/` 的被当成有改动）；
2. HEAD 的提交都在 Gitea 现有分支上的 worktree 也可以删（分支本身留着，由 R3 管），今天只删已合入的；
3. 仓库清单从 `agent-config/gitea-primary.txt` 读，再加 `$AGENT_WORK` 里的真克隆（`bifrost-finance`），不只扫工作区兄弟目录；
4. `gh pr list` 对着 Gitea 的地址没有意义（切换后 `origin` 是 Gitea），「有未合 PR 就留」这条要改成读 Gitea 的 PR 接口，或者明写「Gitea 上不开 PR」后删掉；
5. 备份目录加 90 天保留期（R12）。

### 4.2 登记：工作目录建的时候就写上属于哪件活

新增 `scripts/agent-host/new-worktree.sh <repo> <dir> <branch|--detach sha> --work <W-n|TD-n> --session <local_…>`：

- 做 `git worktree add`，再把 `{work, session, purpose, created_at, ends_when}` 写进 `<repo>/.git/worktrees/<名字>/bifrost-owner`——这是 git 自己给每个 worktree 的管理目录，
  不在工作树里、不会被提交，worktree 删掉时 git 一起删；
- `ends_when` 三种：`merged`（分支进 main 即结束）、`task:<t_…>`（运行时任务结束即结束）、`until:<日期>`；
- 复核目录和普通草稿目录同理写一个 `.bifrost-owner`（目录里，复核本来就不提交）。
- `preflight.js` 对不经这个脚本的 `git worktree add` **提示**（不拦），Cursor 侧同步（parity）。拦不拦以后看一周的数再定。

历史上没登记的 334 个 worktree 不补登记：按 §3 的判据走，判不了的进只报清单。

### 4.3 由谁跑

| 机器 | 跑什么 | 怎么调度 |
|---|---|---|
| 统筹机器（今天这台 MacBook；4.4 之后可能是 .52） | `disk-guard.sh sweep`（含 R5–R13）、`check` 作派活闸门 | LaunchAgent `com.bifrost.disk-guard`，每小时（已有，换成仓库里的版本） |
| agentd 主机（06；以后 mini 接活时同样） | R1、R2 由 agentd 自己做；主机级的 `disk-guard.sh`（同一份脚本，`AGENT_WORK=/home/<agentd 用户>/agent-work`，只清 agentd 根目录以外的缓存）| agentd（已有）+ systemd timer（新，Owner 在 06 上装一次） |
| 集群 | R14、R15 | `cicd/tekton-pipelinerun-ttl`（已有，改规则）；Owner 批 apply |

### 4.4 磁盘余量进监控、低了停派

- **agentd 主机**：平台已经从每次领活里拿到剩余磁盘，只缺把它导出成指标。在 platform-api 的 `/metrics` 上加
  `bifrost_agentrt_host_free_bytes{host,volume}` 和「多久没报」两个量，不改接口；Prometheus 告警：低于下限、或 15 分钟没报。停派已有。
- **统筹机器**：今天没有任何指标。选项见 D-L6。停派用机械闸门：`disk-guard.sh` 把状态写进 `status/lifecycle.json`，
  `preflight.js` 在剩余低于 `STOP_GB` 时拦新的 `codex exec`、`git worktree add`、`npm ci`（只收紧，不放宽），低于 `WARN_GB` 时提示。
- **集群节点**：沿用 node-exporter；把 `BifrostPostgresNodeDiskLow` 扩成所有节点（低于 15% 或 30 GB），因为 Tekton 的卷落在 04、05。
- Console：Ops 的主机卡片读同一组指标（样子等 Design 专轮，这里只把数据给到）。

### 4.5 一次性清理：步骤与回退

前提：§5 的 S1、S2 已合进 main 并在这台 Mac 上跑过一次空跑；发布窗口与此无关（不推 main 以外的东西，不碰集群）。

| 步 | 内容 | 谁 | 回退 |
|---|---|---|---|
| 0 | 重跑本盘点（脚本的空跑输出），和 10-24 的清单对比，变动的条目当场再判 | Agent | — |
| 1 | 可自动清的本地部分：约 295 个 worktree（S2 之后再加 5 个只多了生成文件的和 1 个 `push-main` 残留）、约 437 条本地分支、复核目录里的缓存约 16 GB、`.cache` 里引号写错的 1.1 GB | Agent（规则内，不问） | worktree：按记下的 `路径 → HEAD` 再 `git worktree add`；分支：从 bundle `git fetch <bundle> refs/heads/<b>:refs/heads/<b>`；缓存会自己重建 |
| 2 | 远端人的分支里已合入、超过 24 小时的 31 条 | 按 D-L1 | `git push origin <sha>:refs/heads/<name>`（`refs.tsv` 里有） |
| 3 | agentd 早该删却没删的 7 条：查清原因（尝试有没有记推送的提交、规则有没有发出、Gitea 有没有拒），修了让 agentd 删，不手删 | Agent 查，修在 platform（S5） | agentd 删前也打了 sha |
| 4 | GitHub 冻结分支 | 按 D-L3 | 同 2，推回 GitHub |
| 5 | 历史 20 条「收下没合」 | 按 D-L5 | 标记可撤；删前有 sha |
| 6 | 集群：改 `tekton-pipelinerun-ttl` | Owner 批 apply（D-L7） | 回退清单；删掉的 run 的步骤日志 Loki 留 30 天，发布证据在 ConfigMap |
| 7 | 只报不删的 21 个 worktree、37 条本地分支、12 条远端未合入：每日清单列出 | 不动 | — |

预计腾出：本机约 26 GB（worktree 8.8 + 复核缓存 16.3 + 引号目录 1.1），共享 `go-build` 封顶后再少几 GB。
这台 Mac 现在有 357 GB 空余，所以第一次清理不是救急；要紧的是**之后不涨**。

---

## 5. 切片与验收

| 片 | 内容 | 仓库 | 验收 |
|---|---|---|---|
| S1 | `disk-guard.sh` 进仓库：参数化、可再生成名单、不要求 `run.done`、`KEEP` 换登记、引号目录、写 `status/lifecycle.json`；LaunchAgent plist + 安装脚本 | infra `scripts/agent-host/` | 测试脚本在临时 `AGENT_WORK` 里种：7 种名字的缓存各一个、一个没有 `run.done` 但 25 小时没动的复核、一个登记着且没结束的目录、一个 `go-build GOMODCACHE=` 目录、一个 `REPORT.md`；跑 `sweep` 后缓存都没了、登记的和 `REPORT.md` 还在。**种的每一处都要有测试拦住**（停线规矩：缺测试补上再复核） |
| S2 | `prune-merged-branches.sh` 补 §4.1 的 5 条；定时调用 | infra `scripts/` | `test_prune_merged_branches.py` 加：只多 `.cache/` 的 worktree 被删；HEAD 在远端分支上的 worktree 被删而分支留着；有本地提交的留；`bifrost-finance` 这种 `$AGENT_WORK` 里的真克隆被扫到；`push-main.*` 残留被删；90 天前的备份被删。每条在改之前的脚本上失败 |
| S3 | 登记：`new-worktree.sh`、`bifrost-owner`；`preflight.js` 提示（Cursor 同步，bump 两侧 `parity-id`） | infra | 建、删一个 worktree 后登记文件随之出现与消失；`bash scripts/check-agent-config-parity.sh` 过；`preflight.js` 的测试覆盖「不经脚本时提示、经脚本时不提示」 |
| S4 | 指标与闸门：platform 导出 agentd 主机磁盘指标与告警；统筹机器按 D-L6；`preflight.js` 低于 `STOP_GB` 拦新复核与新 worktree | platform、infra | store/server 测试：报了磁盘的主机出现在 `/metrics`；STG 上一台报低于下限的主机拿不到新尝试、告警到手机（TD-415 第二层原验收）；在测试里把状态文件写成 10 GB，`codex exec` 被拦 |
| S5 | agentd 分支规则的缺口：查明 7 条为什么没删并修；没记推送提交的尝试分支 7 天后按放弃删 | platform `store/prune.go` | store 测试：取消的任务、被取代的尝试、没记推送提交的尝试三种在假 Gitea 里到期都被发出；PROD 上这 7 条在修复上线后一天内没了，并各有一条 `pruned` 记录 |
| S6 | Tekton：`tekton-pipelinerun-ttl` 按 Owner 10-10 的规则，加单独 TaskRun 一遍；TaskRun 数量告警；TD-299 正文更新 | infra `k8s/cicd/tekton/`、`k8s/monitoring/` | 先 `DRY_RUN=1` 跑一遍，列出要删的给 Owner，上限按空跑后的稳态数定（估计 1500 上下）；apply 后一周 `kubectl -n cicd get taskrun --no-headers \| wc -l` 不超过它 |
| S7 | 一次性清理（§4.5 的 0、1、3、7 步） | — | 清理报告：每类删了几个、腾出多少、回退清单在哪 |
| S8 | 观察一周 | — | 下表每天记一次，7 天后对比 |

**一周观察的基线**（10-24 00:00，本盘点）与要求：

| 量 | 基线 | 一周后 |
|---|---|---|
| Mac 数据卷可用 | 357 GB | 不低于基线减 10 GB（日常构建缓存的波动） |
| `~/agent-work` | 58.1 GB | 不高于清理后的值加 5 GB |
| 本机 worktree（不含主 checkout） | 334 | 不高于清理后的值加正在跑的线数 |
| 本机本地分支 | 489 | 同上 |
| Gitea 非 main 分支 | 80（agent 27、人 53） | `agent/**` 里没有超过规则期限的；人的分支不高于基线 |
| `cicd` TaskRun / PVC | 3021 / 284 | TaskRun 不超过上限；PVC 跟 PipelineRun 走 |
| 手工清理次数 | — | 0 |

估时：S1–S3 一天，S4–S6 一天，S7 半天，S8 等一周。核心代码 Claude 写、Codex 复核（Owner 10-13 定的分工）。

---

## 6. 要 Owner 定（每条带建议；回「D-L1 A、D-L2 A……」即可）

D-L1、D-L2、D-L3、D-L5、D-L7 要删远端或公开的东西、写 PROD 库或 `cicd`，D-L6 是新接口，都等你回再做；D-L4 没回时我只把记录拷到 NAS、本机不删。

| # | 要定的 | A（建议） | B | 在哪办 / 怎么回 |
|---|---|---|---|---|
| D-L1 | 远端「人的分支」已合入、超过 24 小时：谁删 | 定时任务自动删，删前打 bundle，一条命令能恢复；每天的清单里列出删了哪些 | 每周出清单，你回一句再删（今天的做法是你手跑 `--apply`） | 统筹线程里回 |
| D-L2 | 远端没合入的人的分支（今天 12 条，多是 10-10 – 10-12 停线后留作材料的） | 删前我逐条核对 WORK.md、TECH_DEBT、教训台账里还有没有引用它的；没有引用的打 bundle 后删，有引用的留并在清单里写明是谁引用；以后没合入、30 天没动、不在任何未结工作项里的照此办 | 只报，你逐条定 | 统筹线程里回；清单在 INVENTORY §2.2 |
| D-L3 | GitHub 上冻结的 157 条公开分支 | 先把只在 GitHub 有的 16 条拷进 Gitea，再删掉已在 main 的 130 条；剩下 27 条跟 D-L2 同规则。要你的 GitHub 凭证：我给一条能原样跑的命令，你在终端面板里跑 | 不动，留到以后 | 统筹线程里回 |
| D-L4 | 复核与 lane 的记录（`BRIEF`/`REPORT`/日志，合计约 2 GB 以内）留多久、放哪 | 30 天后打包到 NAS 的归档（同样的相对路径，文档里的引用还能找到），本机删；统筹搬 mini 后两边都能读 | 永远留在本机，只清缓存 | 统筹线程里回 |
| D-L5 | 历史 20 条「收下没合」的 `agent/` 分支（演练、基准题、几件小注释） | 全部标 `no_merge`（写 PROD、STG 的运行时库），agentd 24 小时后自己删；4.1 打开前做完，免得自动合入把演练合进 main | 逐条看有没有值得合的 | 写 PROD 库是你的事：我出一张单子（任务号 + 理由），你在 Console 批 |
| D-L6 | 统筹机器的磁盘指标怎么进 Prometheus（新接口，架构题） | platform-api 加一个主机上报口（非 agentd 主机每次清扫后报一次剩余空间和计数），由 platform 导出指标；和 agentd 主机的指标同一套名字 | 每台 Mac 装 node-exporter，Prometheus 越过网段来抓（要改 `monitoring` 的抓取配置；Mac 睡着时会误报失联） | 统筹线程里回；选 A 时新路由的设计稿再给你签 |
| D-L7 | Tekton 保留期 | 按你 10-10 定的：成功 24 小时、失败 7 天、每条流水线至少留 5 个、交付有发布记录才删；单独的 TaskRun 2 天（失败 7 天） | 维持现在的一刀切 7 天，只加单独 TaskRun 那一遍 | 改动是 `cicd` 写入：我出 `plan_manifest` 和空跑清单，你批 apply |

不列进待办的：Cursor `state.vscdb` 51 GB（只有 Cursor 关着时你能压缩，`disk-guard.sh` 照旧每小时提醒）；只报不删的条目（每日清单里有，不需要你动作）。

---

## 附：没查到的与原因

- 06 的剩余磁盘、`AGENTD_ROOT` 下工作区以外的残留、06 上 agentd 的版本是否含 `removeWorkspace`：Agent 登不上 06，平台只在跨过下限时记事件、没有指标。
- 两台 mini 的磁盘与工作目录：同上，且它们没有 node-exporter。
- 集群 local-path 卷的实际占用（PVC 只有请求值）：要上节点 `du /var/lib/rancher/k3s/storage`，Agent 不登节点。
- agentd 早该删的 7 条为什么还在：要读 PROD / STG 的事件流或库（`prune_refused` / `prune_failed` 记录、尝试的 `pushed_ref`），这次没读，归 S5。
- 13 条 infra `agent/` 分支是谁删的：时间窗口和剩下的两条都指向 agentd，删除记录没读。
