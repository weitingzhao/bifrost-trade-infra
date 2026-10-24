# 第 4 轮 4.6 切法：分支、工作目录、磁盘的生命周期（2026-10-24，第 2 稿）

> 状态：第 2 稿，按复核 534（`~/agent-work/codex-review-534/REPORT.md`，结论「先改」）改写；逐条回应在该复核目录的 `RESPONSE.md`。
> 一次只读盘点在同目录 `INVENTORY-lifecycle-2026-10-24.md`，原始数据与脚本在 `INVENTORY-lifecycle-2026-10-24.data/`。（原始数据与脚本不进公开仓库：其中有本机临时目录和一个不在公开清单里的仓库的 SHA，复核 539 C4；留在统筹机器的 `~/agent-work/r4-lifecycle/agent-config/work/multi-agent/INVENTORY-lifecycle-2026-10-24.data/`，提交 db3d14d9。）**这一步没有删任何东西。**
> 依据：第 4 轮草案 4.6（Claude Doc「小牛牛包工队全面盘点」第二个标签页；Owner 10-23 23:3x「D2 A、D3 A、D4 A，其余按推荐，开第 4 轮第一波」）；
> Owner 10-23 原话「版本分支的清理和保持，之前发生过我本地的硬盘全部占满的情况」；TD-415、TD-383、TD-299；
> `CUT-gitea-primary-2026-10-17.md` §6、§9.2、§9.6；infra `15271dd`；4.1 的 `CUT-landing-2026-10-24.md`（`r4-landing` 线，`047ea5c`）。
>
> **做完标准**（草案原文的意思，按复核 C3 改正了方向）：一周不手工清理，每台跑 Agent 的机器上**磁盘占用不持续增长（可用空间不持续下降），分支数不涨**。
> 第 4 轮之后统筹可能搬到 Mac mini（4.4），所以规则按「每台跑 Agent 的机器」写：同一份脚本、同一份配置，机器之间只差根目录和调度方式。
>
> 单位：本文的 GB 一律指 GiB（2^30 字节）。`df -g`、`du -k` ÷ 1048576、Go 的 `15 << 30`、Kubernetes 的 `Gi` 都是这个单位。

---

## 0. 第 2 稿改了什么

第 1 稿把「这件活已经进了 main」（同 Change-Id、同标题）当成「这个对象在别处有副本」，把「24 小时没写、没有进程」当成「会话已结束」，
缓存按名字认。复核 534 用实例证明这三条都会丢东西：一个 detached HEAD（`merge-accepted/t_01M5D3K2…`，`8d5135fd`）不在任何引用上，
main 上同 Change-Id 的是拆分后的另一个提交；一批 worktree 的旧提交只在它们自己的 HEAD reflog 里；共享 `.cache` 里有手写的 `.go` 和 `.md`。

按新判据重算后的三类计数（详见 INVENTORY §1）：

| 类 | 第 1 稿 可自动清 | 第 2 稿 可自动清 / 只报不删 / 要 Owner 定 |
|---|---|---|
| 本机 worktree 334 | 295 | **0 / 252 / 76**（另 5 个在用、1 个本线） |
| 本地分支 489 | 437 | **132 / 111 / —**（另 246 条跟着 worktree） |
| Gitea `agent/**` 27 | 7 | **1 / 7 / 19** |
| Gitea 人的分支 53 | — | **— / — / 53**（29 条分支头是 main 祖先，24 条不是） |
| GitHub 157 | — | **— / — / 157**（38 个分支头不在任何 Gitea 引用上） |
| 复核缓存 | 16.3 GiB | **10.05 GiB / 6.27 GiB / —**；记录 2.11 GiB 全部 D-L4 |
| 分支备份 30 个包 | （90 天后删） | **— / 30 / —**：168 个引用的提交已不在 Gitea，这些包是最后的副本 |

---

## 1. 现状（实测：引用快照 2026-10-24 05:24Z，本机 00:25–00:35 CDT，集群 00:3x；只读）

### 1.1 分支

- **Gitea `agent/**` 27 条**（platform 25、infra 2）。10-23 23:02 时 infra 还有 15 条，到 23:50 只剩 2 条：13 条在这一小时内没了，剩下的正是规则要留的那类，
  所以很可能是 agentd 按 `store/prune.go` 删的（删除记录没读）。27 条逐条查了任务状态（PROD / STG `get_task`）：19 条是「收下但没进 main」（几乎都是演练和基准题）；
  按规则早该删的 7 条里只有 `t_01M50FZ…/a2` 的分支头在 main 上，其余 6 条的提交只在自己的分支上；M-27 Q07 的两次尝试分不清哪次被收下。
  规则内到期却没删，多半是 `store/prune.go:204-205` 要求尝试、ref、提交与 Gitea 上的分支完全对得上，被叫停的尝试没记下推送的提交，于是静默保留（没读库核实）。
- **Gitea 人的分支 53 条**：分支头是 main 祖先的 29 条；24 条有提交不在 main 上，其中 12 条第 1 稿按 Change-Id / 标题算成了「已合入」。
- **Gitea `land/**`**：0 条（4.1 还没上线）。
- **GitHub（公开）157 条**，没有一条 `agent/`。119 个分支头能从 Gitea 的引用走到；**38 个不能**：GitHub 上那个确切的提交在 Gitea 上没有副本。
- **本机本地分支 489 条**：132 条的分支头和分支 reflog 全在 Gitea 引用上、没有检出；111 条有提交不在 Gitea 引用上（87 条分支头就是，24 条只在 reflog 里）；246 条检出在 worktree 里。

### 1.2 工作目录

- **本机 worktree 334 个**（不含 11 个主 checkout）：platform 178、infra 117、ui 25、frontend 5、research 5、插件 4。位置：`~/agent-work` 314，工作区根 13 + `.worktrees/` 6，`$TMPDIR` 1（`push-main.sh` 被杀时漏下的）。
- 252 个只报不删，第一道拦住它们的条件：只有被忽略的内容（`node_modules`、`dist`、`.venv`、`__pycache__`……，都没有登记为缓存）93；只有 reflog 里的提交不在 Gitea 引用上 73；
  HEAD 就有提交不在 Gitea 引用上 54；有未跟踪内容 28；有未提交改动（含删除）4。
- 76 个内容全在 Gitea 引用上（HEAD 与 reflog）、没有任何未跟踪或被忽略的内容、没有进程在用，但**没有会话已结束的正面证据**（D-L8）；其中 3 个 24 小时内、9 个 72 小时内有文件改动（全深度遍历）。
- 5 个有进程打开着（`codex-ops-ui`、`r4-b4`、`rules-symbols`、`data-integrity-main-research`、`td-172-142-research`）。
- 工作区根下 14 个旧目录：13 个 worktree 里只有 `bifrost-trade-infra-a6r-report` 进 D-L8，其余 12 个都有 HEAD 独有、reflog 独有、未跟踪或被忽略的内容；`bifrost-platform-phase3-notes` 不是 git。

### 1.3 `~/agent-work` 与缓存

- `~/agent-work` 868 项、58.1 GiB（10-23 23:4x 测）。
- 复核目录 495 个（00:3x）：缓存候选子目录 33 个、16.32 GiB。按布局（Go 构建缓存：`README` 写着 Go build、只有两位十六进制目录和 `trim.txt`；Go 模块缓存：`cache/download`；npm：`_cacache`）
  确认、并且有 `run.done` 的 20 个、10.05 GiB；没有 `run.done` 的 9 个（4.07 GiB，布局都对）和布局对不上的 4 个只报。复核记录（缓存以外）2.11 GiB。
  只有 132 个复核号的报告抄进了仓库 `work/multi-agent/reviews/`；仓库文档按 `~/agent-work/codex-review-<n>/` 路径引用的有 31 个（TECH_DEBT 里 268、277、278、286、288、290、292–294 等只在本机）。
- 共享 `.cache`：`go-build` 18.64、`go-mod` 0.25、`npm` 0.07 GiB 是 BRIEF 模板约定的共享缓存根，布局确认；另外 40 项不是缓存（`api-new.go`、`pools-new.go`、`cut25.md`、`gates-*`、`paints-*`、各种 `.log`）。
  引号目录 `go-build GOMODCACHE=` 1.12 GiB 是一串单子目录 `Users/…/go-mod AGENTRT_TEST_PG='…' AGENTRT_TEST_REQUIRED=1`，末端才是 Go 构建缓存——某次把整串环境变量赋值写进了 `GOCACHE`。
- `disk-guard.sh` 只认 `gocache tmp .tmp .check-tmp` 四个名字、只清有 `run.done` 的复核，而它认得的那 0.63 GiB 都在没有 `run.done` 的目录里，所以一样清不掉；
  它**只在 `~/agent-work/bin`，不在任何仓库**，`KEEP` 是写死的名字。
- 分支备份 `~/bifrost-backups/git-branches`：4 个日期、30 个包，都能 `git bundle verify`；**其中 168 个引用的提交已不在 Gitea 上**——以前按 Change-Id / 标题判「已合入」删掉的分支，这些包是最后的副本。
  `prune-merged-branches.sh:73` 只按日期建目录，`:169-170` 同一天再跑就覆盖。

### 1.4 这台 Mac 的其余部分

数据卷 926 GiB，可用 363 GiB（00:3x）；默认 Go 缓存约 12 GiB；Docker 构建缓存 21.3 GiB（328 项，每周只删 7 天前的）；Cursor `state.vscdb` 51.4 GiB；
会话 scratchpad 3.35 GiB；本地 Time Machine 快照 22 个。Prometheus 只抓集群 5 个节点的 node-exporter：**这台 Mac、两台 mini、06 都没有主机指标**。

### 1.5 06（agentd 主机）与两台 mini

- agentd 已有：交接完成、进程组确认清掉、检查点完整之后才清工作目录（`agentd/disk.go:132-145`、`deliver.go:562-578`、`:749-757`）；按平台规则删 `agent/**`（`agentd/prune.go`，
  每 10 分钟最多 50 条，在一个空的 bare 仓库里用带 SHA 的 lease 推删除，**删前不做任何对象备份**，`:126-155`）；领活带剩余磁盘，低于下限（默认 15 GiB）不派新活、记 `policy_alert`。
- 平台的检查点补丁（`agentd/checkpoint.go`，运行中每 5 分钟、≤1 MiB 的 `git diff`）不是最终提交对象，不能当归档；平台的删除记录是任务、ref、提交和原因，也不是对象备份。
- 平台只在剩余磁盘跨过下限时记一条事件（`store/hostdisk.go:55-112`），没有最新读数可看。
- **没查到**：06 现在剩多少盘、`AGENTD_ROOT` 下工作区以外的残留、06 上 agentd 的版本；两台 mini 的磁盘与工作目录——Agent 登不上这些机器，也没有主机指标。

### 1.6 集群 `cicd`

| 对象 | 数量 | 说明 |
|---|---|---|
| PipelineRun | 306 | 已有清理：CronJob `tekton-pipelinerun-ttl`（`k8s/cicd/tekton/pipelinerun-ttl.yaml`，建于 2026-08-10，infra `73e181f`；10-24 04:20Z 最近一次成功）删 7 天前结束的 PipelineRun，删 2 天前结束的 TaskRun 的 Pod。TD-299 正文「`kubectl -n cicd get cronjob` 什么都没有」与此不符（原因没查），要改。Owner 10-10 定的保留规则还没实现 |
| PVC | 285（local-path 282） | 随 PipelineRun 的 ownerReference 级联删；4 个属于 06-19 的单独 TaskRun；3 个数据卷 `gitea-backup`、`gitea-data`、`registry-data` |
| TaskRun | 3030 | 475 个单独的（`github-sync-*`、`gitea-mirror-sync`……）**没有东西在清**；近 7 天每天新增 34–94 个，423 个超过 2 天、122 个超过 7 天 |
| 发布记录 ConfigMap | 550 | 发布证据，留着 |
| 节点根盘可用 | 01 407、02 132、04 132、05 227 GiB | 只有 `BifrostPostgresNodeDiskLow`（.70、.75 低于 50 GB）一条盘告警；Tekton 的卷大多落在 04、05 |

---

## 2. 原则（第 2 稿）

1. **「工作已落地」和「原对象有副本」分开记。** Change-Id、标题、patch-id 只用来定位，说明这件活大概进了 main；放行删除只看第 2 条。
2. **副本 = 对象可达。** 一个提交（连同它的历史）算有副本，当且仅当它能从一个**不在本轮删除集合里的持久引用**走到——Gitea 上现在存在的 main、其他分支、标签
   （`git merge-base --is-ancestor <提交> <引用>`，或 `git rev-list <提交…> --not <引用…>` 为 0）——或者它已经进了一个打好包、`git bundle verify` 过、
   放在持久位置、记了位置和校验值的归档。只记 SHA 不算副本。
3. **reflog 一起算。** 删 worktree 会连它的 HEAD reflog 一起删，删本地分支会连分支 reflog 一起删。里面的提交不可达的，先进归档并验证，否则只报。
4. **缓存只认登记过的缓存根或类型确认的布局。** 登记：建它的工具写下的缓存根与用途（§4.2）。类型确认：Go 构建缓存、Go 模块缓存、npm 缓存的已知布局，不跟随软链接，没有嵌套 `.git`。
   名字只用来找候选；名字带空格或 `=` 的不做通配删除。`git status --porcelain --ignored` 有任何未跟踪或被忽略的内容，这个目录就不算干净。
5. **有未提交的改动（包括删除）一律只报，没有例外**——工具自己的临时 checkout 也一样。
6. **结束要有正面证据**：登记的会话已结束（§4.2 的结束记录）、复核目录有 `run.done`、运行时任务进了终态。「24 小时没写」「没有进程 cwd」只是活动的旁证，不能当结束；读取失败、`lsof` 失败一律保留。
7. **检查与删除之间有保护。** 一次清扫持一把机器级的互斥锁；删前对每个对象再查一次身份、HEAD、改动、占用和归档；
   worktree 先 `git worktree lock --reason lifecycle:<run-id>` 再复查再删；本地分支用 `git update-ref -d refs/heads/<b> <旧 sha>`；
   远端用 `git push --force-with-lease=refs/heads/<b>:<旧 sha> origin :refs/heads/<b>`，重试时期望值不变，分支变了就跳过、下一轮重新判。
8. **备份不覆盖，最后的副本不按期限删。** 每次运行写 `<备份根>/<机器>/<仓库>/<run-id>/`（bundle + `名字 → sha` 清单），写完 verify 再删；
   只有「里面每个提交都还在持久引用上」的冗余包才能 90 天后删，含独有对象的是归档，按 D-L4 放持久存储，不按期限删。
9. **一份实现，每台机器一样**：脚本进 infra 仓库，参数是 `AGENT_WORK`（根目录）、备份根、阈值；macOS 用 LaunchAgent，Linux 用 systemd timer；agentd 主机上 agentd 自己管它的根目录。

---

## 3. 规则：每样东西属于哪件活、什么时候可以清、谁来清

| # | 东西 | 属于哪件活（怎么认） | 什么时候可以清 | 谁来清 | 只报不删 |
|---|---|---|---|---|---|
| R1 | agentd 尝试工作区 | 任务 + 尝试（`tasks/<task>/a<n>`） | 已有实现的条件：交接完成、进程组已清、检查点完整（`disk.go:132-145`、`deliver.go:562-578`、`:749-757`） | agentd | 条件不全时留着；平台按下限停派 |
| R2 | Gitea `agent/<task>/a<n>` | 任务 | 平台规则（`store/prune.go`）的终态满 24 小时，**并且**分支头可达于 main，或已归档（S5：agentd 删前把该提交打包到持久存储、平台记下位置与校验值） | agentd，用它自己的 Gitea 身份 | 任务还开着；收下没进 main 也没标 `no_merge`；运行时记的尝试、ref、提交与 Gitea 对不上（缺推送提交的继续只报，先补交接证据，**不按「放弃」删**） |
| R3 | Gitea 人的分支（`w31/`、`cursor/`、`codex/`、`fix/`、`night/`） | 工作项（分支名、`Work:` 与 `Claude-Session:` 尾注） | 分支头是 Gitea main 的祖先（D-L1）；不是的先归档，按 D-L2 | D-L1 定（S4 单独一片，不和本地清扫一起跑） | 没归档的、不是 main 祖先的 |
| R3b | Gitea `land/**` | 4.1 的落地循环 | 4.1 自己的规则（落地或退回后即删；`prune.go` 兜底） | 4.1 | 4.6 只计数，不删 |
| R4 | GitHub 上冻结的分支 | 同 R3 | 确切的分支头能从 Gitea 引用走到 | D-L3（要 Owner 的 GitHub 凭证或他亲手） | 38 个头不在 Gitea 上：先按 SHA 推进 Gitea 的归档引用或进归档包，验证后再说 |
| R5 | 本地 worktree | 登记（§4.2）；没登记的看分支名和 `Claude-Session` 尾注 | 原则 2–7 全部成立：HEAD 与 reflog 可达、没有任何未跟踪或被忽略内容（登记的缓存根除外）、没有改动、没有占用、**登记的会话已结束** | 定时任务，先 `worktree lock`，复查后不加 `--force` 删 | 其余一律只报；历史未登记、内容全可达的进 D-L8 |
| R6 | 本地分支 | 同 R5 | 没有检出；分支头与分支 reflog 全可达 | 定时任务，`update-ref -d <旧 sha>` | 有不可达提交的（今天 111 条） |
| R7 | 工作区根的旧目录、`.worktrees/` | 同 R5 | 同 R5 | 同 R5；以后不在工作区根建 worktree（只建在 `$AGENT_WORK/<线>/`） | 同 R5；`phase3-notes` 这类非 git 目录只报 |
| R8 | 复核目录 | 复核号 | **缓存**：子目录布局确认、有 `run.done`、没有进程打开。**记录**（`BRIEF`、`REPORT`、`LAST`、日志、草稿）按 D-L4 | 定时任务 | 没有 `run.done` 的、布局对不上的 |
| R9 | 共享缓存 `$AGENT_WORK/.cache` | 共享缓存约定（`go-build`、`go-mod`、`npm` 三个根） | 只按上限修剪（建议 `go-build` 20 GiB），超上限时经目录句柄删除整个根：只删第二次检查清点过的条目，整根都会删掉。npm 根里的 `_logs` 和 `_update-notifier-last-checked` 也一起删，而 `npm cache clean` 只删 `_cacache`、会留下这两样。前提是根下没有进程打开着文件。不调这些工具：它们按路径操作，会重新打开复核 543 A2 的口子（初查后路径被换成软链接就删到根外） | 定时任务 | 其余 40 项；引号目录在 S1 对它的单子目录链和末端布局专门校验之前只报 |
| R10 | lane 目录里 git 以外的剩余、普通目录和文件 | 登记；没登记的只能猜 | 跟 R8 的记录同一规则（D-L4） | 定时任务 | 没登记的一律只报 |
| R11 | 工具自己的临时 checkout（`$TMPDIR/push-main.*`、`merge-accepted/<task>/`） | 建它的工具 | **与 R5 完全相同的门槛**（`merge_accepted.py:485-503` 会在 detached checkout 上 cherry-pick、amend，不能假定它们都是 main 的祖先） | 定时任务；工具自己的 `trap` 照旧 | `push-main` 残留（12 处未提交删除）只报，除非完整归档了差异 |
| R12 | 分支备份 | `prune-merged-branches.sh` | 冗余包（每个提交都还在持久引用上）90 天；含独有对象的包不按期限删 | 定时任务 | 现有 30 个包里有 168 个引用是最后的副本 |
| R13 | Docker、默认 Go 缓存、Time Machine 本地快照 | 这台 Mac | 照 `disk-guard.sh` 现有规则（Owner 10-21 定的） | 定时任务 | Cursor `state.vscdb`：只报（要 Cursor 关着，他自己做） |
| R14 | Tekton PipelineRun 与它的卷 | 流水线 | Owner 10-10 已定：成功 24 小时、失败 7 天、每条流水线至少留 5 个、交付类有该 run / 仓库 / 提交的发布记录才删；只删终态对象；PVC 按真实 ownerReference 级联；数据卷不碰 | `tekton-pipelinerun-ttl`（改它，不新建）；`cicd` 写入由 Owner 批 apply（D-L7） | 没有发布记录的交付 run |
| R15 | 单独的 TaskRun 与它们的 PVC | 建它的触发器 | 成功 2 天、失败 7 天；失败 run 的 Pod 也留 7 天（现在的第 2 遍 2 天就删 Pod，要一起改） | 同 R14 | — |
| R16 | 发布记录 ConfigMap | 发布 | 不清 | — | — |

### 3.1 与 4.1「交房」的衔接（复核 B1、C1；统筹线程同时转告 4.1 的作者）

- **落地资格是一条判定，入队和最后推 main 之前各跑一次**，两次之间有版本比较：环境；mission scope（`no_merge` 是 mission 级的）；任务、收下的尝试、提交 SHA；
  **这件活在当前计划里是否仍然有效**——所属的计划步骤没被 `drop_step` 撤掉、没被取代，计划版本与入队时一致；没有 returned / declined；main 上没有对它的 revert
  （`merge_accepted.py:464-466` 丢掉了 `landed()` 返回的「曾落地后被撤销」理由，要接上）；收下时间不早于规则生效时间。哪一条不成立就停止自动落地、记原因。
  已经被 revert 的结果需要新的显式落地决定。
  现有代码里 `dropStep`（`store/planchange.go:540-570`）把 accepted 排除在未完成之外、只把 plan_node 改成 dropped，不动任务——所以「计划里是否仍然有效」这一条非加不可。
- 验收三例都不能推 main：规则生效后收下、随后 `drop_step`；CI 等待期间 mission 被标 `no_merge`；人手合入并 revert、尚未写 `landed` note。
- **D-L5 只处理历史演练**（解释和清理），不是 4.1 的闸门；4.1 的 `accepted_at ≥ effective_at` 才是历史屏障。
- **落地提交的消息要同时带 `Agentrt-Task` 和 `(cherry picked from commit <原 SHA>)`**：`lineage/mainresults.go:55-69` 按任务加原结果 SHA 认落地，只有 `Agentrt-Task` 认不出来，分支就永远不会被 R2 清掉。
  （第 1 稿说「cherry-pick 时 Change-Id 会变」，那是 10-20 手工合 M-9 时的一次观察，不是 cherry-pick 的必然。）
- `land/**` 归 4.1 的落地循环删；4.6 的计数里单独一类，不进 D-L1。
- 4.1 Pod 里的克隆「每次用完即删」与 R1 同口径：先确认交接与记录完整。

---

## 4. 机制

### 4.1 清扫脚本（S1）

把 `~/agent-work/bin/disk-guard.sh` 搬进 infra `scripts/agent-host/disk-guard.sh`（连同 LaunchAgent plist、systemd timer 和安装脚本），改成：

- 参数从环境读：`AGENT_WORK`、备份根、`WARN_GB`（30）、`STOP_GB`（15），默认值就是今天这台 Mac 的；
- 缓存：只处理登记的缓存根（§4.2）和布局确认的候选（R8、R9）；遍历不跟随软链接、不跨出登记根，遇到嵌套 `.git`、手写文件、不认识的条目，整个候选只报；
- 每次运行先取机器级锁（`mkdir $AGENT_WORK/.lifecycle.lock`，写 run-id 与 pid；拿不到就退出），结束释放；实现为锁目录里 `lock` 文件上的 flock，持有者死掉时内核自动释放（复核 544）；
- 跑完写 `status/lifecycle.json`：剩余空间、各类计数、只报不删的清单、跳过的原因。这只是报告，停派闸门不读它（§4.5）；
- 删除的保护范围（复核 547 A1，统筹 10-24 定）：防的是误删，不防故意和清扫对着干的进程。清扫和所有生产者是同一个用户，那样的进程自己就能删掉自己的材料。
  - 保护的：只有三件事同时成立才删——根已离开登记名、lsof 没看到其中有打开的文件、每个删掉的条目在最后一次比对时和第二次检查的清单对上。
  - 不保护的：
    - 某个名字在最后一次比对之后、名称操作（unlink，或 rmdir）之前被换成别的材料。目录的 rmdir 要等它下面的东西全部删完才做，所以这段时间可能不短。
    - 删除进行中把某个目录搬出 quarantine（已打开的句柄会跟着它走）。
  - 中途停下或进程死掉的删除，要等剩下的条目和清单对得上、其余检查也都通过，下一轮才会删完。
  - journal、清单和 chmod 记录是可信状态，没有认证：能改它们的同用户进程不在防护范围内（复核 549）。
- 本地 worktree / 分支部分调 `prune-merged-branches.sh --local-only`（S2），**不碰远端**。

### 4.2 登记与会话结束（S3）

- 新增 `scripts/agent-host/new-worktree.sh <repo> <dir> <branch|--detach sha> --work <W-n|TD-n> --session <id>`：
  做 `git worktree add`，把 `{work, session, purpose, created_at, cache_roots}` 写进 `<repo>/.git/worktrees/<名字>/bifrost-owner`（git 给每个 worktree 的管理目录，不进工作树、不会被提交，worktree 删掉时一起删）。
- **结束记录**：`ended_at` 由正面事件写入，不由时间推断——
  Claude Code 的 `SessionEnd` 钩子按会话 id 给它登记的 worktree 写 `ended_at`（治理层钩子在 `agent-config/claude/hooks/`，Cursor 侧用它的结束钩子，parity）；
  复核与 lane 的包装脚本在退出时写 `run.done`；运行时的工作目录看任务终态；也可以手工 `new-worktree.sh --end <dir>`。
  会话再次用到它（钩子在会话开始和每次工具调用时续一次 `lease_until`），`ended_at` 作废。
- 没有 `ended_at` 的一律不自动清；历史上没登记的 334 个不补登记，走 D-L8。
- `preflight.js` 对不经这个脚本的 `git worktree add` 提示（不拦），Cursor 侧同步。

### 4.3 `prune-merged-branches.sh` 要改的（S2 本地、S4 远端）

1. 判据换成可达性（原则 2）；Change-Id / 标题匹配只写进报告当线索；
2. 删 worktree、本地分支前，把 HEAD reflog、分支 reflog 里不可达的提交打进本次归档（打包时给它们临时起名 `refs/lifecycle-archive/<run-id>/<n>`，`git bundle verify` 通过才删），否则只报；detached HEAD 一样进包；
3. `--local-only` 与 `--remote-only` 互斥、必须二选一。今天的 `--local` 是「远端之外**再**清本地」，挂上定时器就会在 D-L1 定之前删远端（复核 B2）。两种模式各有测试证明碰不到另一侧；
4. 本地删除用 `update-ref -d <旧 sha>`，远端用 `--force-with-lease=<ref>:<旧 sha>`，重试不刷新期望值；worktree 先 lock 再复查；
5. 备份目录 `<备份根>/<机器>/<仓库>/<run-id>/`，不覆盖；包分「冗余」与「含独有对象」两类写进清单（R12）；
6. 仓库清单从 `agent-config/gitea-primary.txt` 读，加上 `$AGENT_WORK` 里的真克隆（`bifrost-finance`）；独立克隆只检查、不按 R10 整个删；
7. `gh pr list` 对着 Gitea 地址没有意义，改成读 Gitea 的 PR 接口，或明写「Gitea 上不开 PR」后删掉这一条；
8. 工具临时 checkout 与普通 worktree 同一套门槛，不加 `--force`。

### 4.4 由谁跑

| 机器 | 跑什么 | 怎么调度 |
|---|---|---|
| 统筹机器（今天这台 MacBook；4.4 之后可能是 .52） | `disk-guard.sh sweep`（R5–R13 的本地部分） | LaunchAgent `com.bifrost.disk-guard`，每小时（已有，换成仓库里的版本） |
| agentd 主机（06；以后 mini 接活时同样） | R1、R2 由 agentd 做；主机级的 `disk-guard.sh`（同一份脚本，`AGENT_WORK=/home/<agentd 用户>/agent-work`，只清 agentd 根目录以外的登记缓存） | agentd + systemd timer（新，Owner 在 06 上装一次） |
| 远端人的分支 | R3（D-L1 定了之后） | 统筹机器上的 `--remote-only`，单独的定时任务 |
| 集群 | R14、R15 | `cicd/tekton-pipelinerun-ttl`（已有，改规则）；Owner 批 apply |

### 4.5 磁盘余量进监控、低了停派（复核 B4）

- **停派闸门读实时余量**：`preflight.js` 在拦截点当场 `statfs` 目标卷（Node 的 `fs.statfsSync`，毫秒级），不读每小时的状态文件。分级沿用 Owner 10-21 定的语义：
  低于 **30 GiB** 不起新的复核、`npm ci`、新 worktree；低于 **15 GiB** 什么新活都不起，先清扫并告诉 Owner。读不到（卷不对、调用失败）按低于 15 GiB 处理，并写明原因。
- **并发预算**：余量先减去在跑的活的预留再比阈值——复核每个预留 2 GiB、lane 每个 3 GiB（盘点里单个复核的缓存最大 1.15 GiB、单个 worktree 最大 2.3 GiB）；预留数记在登记里。
- **agentd 主机**：平台已从每次领活拿到剩余磁盘，但只存跨线事件。要存最近一个样本（主机、卷、读数、采样时间），由 platform 导出 `bifrost_agentrt_host_free_bytes{host,volume}`
  与样本年龄；告警：低于下限，或样本超过 15 分钟（agentd 每次领活都报，15 分钟没报就是失联）。这要加表或列，归 D-L6 一起定。
- **统筹机器**（会睡）：上报方式归 D-L6。Mac 睡着时的「没数据」在 Console 和告警里显示为「未观测」，不能显示成「磁盘充足」，也不算通过验收。
- **集群节点**：把 `BifrostPostgresNodeDiskLow` 扩成所有节点（低于 15% 或 30 GiB）。

### 4.6 一次性清理：步骤与回退

前提：S1、S2、S3 已合进 main 并在这台 Mac 上空跑过一次（复核 B2：登记要先接线）。不推 main 以外的东西，不碰集群。

| 步 | 内容 | 谁 | 回退 |
|---|---|---|---|
| 0 | 重跑本盘点（脚本空跑），与 10-24 的数据对比，变动的条目当场再判 | Agent | — |
| 1 | 打归档：73 个只差 reflog 的 worktree、24 条只差 reflog 的本地分支、30 个旧备份里的 168 个最后副本，打进本次 run 的归档包，verify | Agent | 归档只加不删 |
| 2 | 本地：132 条本地分支（`update-ref -d <旧 sha>`）；复核缓存 20 个（10.05 GiB）；第 1 步归档验证过、其余条件也满足的 worktree 与分支 | Agent（规则内） | 分支 `git fetch <bundle> <ref>:<ref>` 或从 Gitea 重建；worktree 按记下的 `路径 → HEAD` 重建；缓存自己重建 |
| 3 | D-L8 的 76 个 | 按 D-L8 | 内容全在 Gitea 上，重建即可 |
| 4 | `agent/**`：S5 上线后 agentd 自己删（先归档） | agentd | 归档包 |
| 5 | 远端人的分支、GitHub、历史演练 | 按 D-L1、D-L2、D-L3、D-L5 | 归档包 / `refs.tsv` |
| 6 | 集群 | Owner 批 apply（D-L7） | 回退清单；日志 Loki 留 30 天，发布证据在 ConfigMap |
| 7 | 只报不删的：每日清单列出 | 不动 | — |

预计腾出：第 2 步约 10 GiB；其余取决于 D-L8 与归档（只差被忽略内容的 93 个 worktree 要等它们的缓存根登记，或它们的会话结束后由主人清）。
这台 Mac 现在有 363 GiB 空余，第一次清理不是救急；要紧的是之后不涨。

---

## 5. 切片与验收

| 片 | 内容 | 仓库 | 验收（每条反例在改之前的代码上失败） |
|---|---|---|---|
| S1 | `disk-guard.sh` 进仓库：参数化、布局确认、`run.done`、机器级锁、`status/lifecycle.json`；plist、timer、安装脚本 | infra `scripts/agent-host/` | 在临时 `AGENT_WORK` 里种：每种布局的真缓存（应删）；同名目录里放一个手写 `.go`（留）；被忽略的手写材料（留）；名字带空格的普通草稿目录（留）；缓存候选里嵌一个 `.git`（留）；软链接指出根外（不跟随）；没有 `run.done` 的复核（留）；引号目录形状（S1 认得才删，认不得就留） |
| S2 | `prune-merged-branches.sh --local-only`：可达性、reflog 归档、`update-ref -d <旧 sha>`、worktree lock、不覆盖的 run 目录、冗余与独有两类包、finance 克隆、工具临时 checkout 同门槛 | infra `scripts/` | `test_prune_merged_branches.py` 加：HEAD 在 main、旧提交只在该 worktree reflog → 先进包，能用包恢复那个旧提交；detached HEAD 不在任何引用上（同 Change-Id 的拆分版本在 main）→ 不删；有未提交删除 → 不删；检查后另一会话 commit → 不删；`--local-only` 不发任何 push；同一天两轮不同删除集 → 两个包都在；含独有对象的包超过 90 天 → 还在 |
| S3 | 登记与结束记录：`new-worktree.sh`、`bifrost-owner`、`SessionEnd` 钩子写 `ended_at`、续租作废；`preflight.js` 提示（两侧 parity） | infra | 建、结束、再续的 worktree 状态依次正确；没有 `ended_at` 的不被 S2 删；`bash scripts/check-agent-config-parity.sh` 过 |
| S4 | 远端人的分支（**D-L1 定了才做**）：`--remote-only`，只删 main 祖先，`--force-with-lease=<ref>:<旧 sha>` | infra `scripts/` | `--remote-only` 不碰本地；检查后有人推了新头 → 不删，重试不刷新期望值；不是 main 祖先的 → 不删 |
| S5 | agentd 删前归档：删前把该提交 fetch 进本机归档仓库、打包到持久存储、平台记位置与校验值；查明 6 条到期未删的原因 | platform `agentd/prune.go`、`store/prune.go` | 假 Gitea 里到期的取消任务、被取代尝试：没有归档记录时不删，有归档且验证过的才删；缺推送提交的不删 |
| S6 | 停派闸门与指标：`preflight.js` 实时 `statfs`、30/15 GiB、预留预算、读不到即停；platform 存最近样本并导出指标（形状按 D-L6） | infra、platform | 测试里把卷换成 10 GiB 的假卷 → `codex exec` 被拦；`statfs` 抛错 → 被拦并写明原因；STG 上一台报低于下限的主机拿不到新尝试、告警到手机（TD-415 第二层原验收）；样本过期显示「未观测」 |
| S7 | Tekton：按 Owner 10-10 的规则改 `tekton-pipelinerun-ttl`，加单独 TaskRun 一遍，失败 run 的 Pod 留 7 天，Role 加 `configmaps` get/list；TaskRun 数量告警；TD-299 正文更新 | infra `k8s/cicd/tekton/`、`k8s/monitoring/` | 先 `DRY_RUN=1` 跑一遍给 Owner 看清单；只删终态对象、数据卷不在清单里、交付 run 只在有对应发布记录时进清单 |
| S8 | 一次性清理（§4.6） | — | 清理报告：每类删了几个、归档了几个、腾出多少、回退清单在哪 |
| S9 | 观察一周（复核 B3） | — | 见下 |

**一周观察（S8 之后立即建基线，每台机器各一份）**

- 每天记一次，按机器：已用空间分四类——在做的活（登记着、没结束）、可再生成的缓存、待处置的独有材料（只报不删的）、持久归档；
  各类分支按种类（`agent/**`、人的、`land/**`）和仓库的净变化；自动处理数、因证据不足拒绝的数、人工处理数。
- 通过条件：除「在做的活」外，已用空间的 7 天线性增长不超过 1 GiB/天，且第 7 天不超过基线加 5 GiB（缓存的短期波动允许，周末要回落）；
  每种分支第 7 天不高于基线（`land/**` 的在途数另有上限，由 4.1 定）；人工处理数为 0。
- 机器范围：这台 Mac、06、以后接活的 mini；4.1 的 `land/**`。**没有观测数据的机器不算通过**——06 和 mini 先要有 4.9 的 B4 ① 主机监控或 D-L6 的上报。
- 不允许用一次性清理腾出的空间抵消新的增长：基线取清理之后那一天。

估时：S1–S3 一天半，S4–S7 一天半，S8 半天，S9 等一周。核心代码 Claude 写、Codex 复核。

---

## 6. 要 Owner 定（每条带建议；回「D-L1 A、D-L2 A……」即可）

D-L1、D-L2、D-L3、D-L5 要删远端或公开的东西、写 PROD 库，D-L6 是新接口与新表，都等你回再做；D-L7 你 10-10 已经定了，只差批一次 apply；
D-L4 没回时我只把记录拷到 NAS、本机不删；D-L8 由统筹线程按 A 做，你不用管。

| # | 要定的 | A（建议） | B | 在哪办 / 怎么回 |
|---|---|---|---|---|
| D-L1 | 远端「人的分支」里分支头是 main 祖先的（今天 29 条）：谁删 | S2、S4 合进去之后由定时任务删，带 lease、删前写不覆盖的包，一条命令能恢复；每天的清单列出删了哪些。范围只有人的分支：`agent/**` 归 agentd，`land/**` 归 4.1 | 每周出清单，你回一句再删（今天的做法是你手跑 `--apply`） | 统筹线程里回 |
| D-L2 | 远端有提交不在 main 上的人的分支（今天 24 条，其中 12 条第 1 稿误算成已合入） | 先全部打进归档包（验证、存 NAS），每条写一句保留理由（谁引用它、是停线材料还是在做）；现在不删。以后要删，按清单你逐条点 | 不归档，原样留着 | 统筹线程里回；清单在 INVENTORY §3.2 |
| D-L3 | GitHub 上冻结的 157 条公开分支 | 先把 38 个不在 Gitea 上的确切分支头按 SHA 推进 Gitea 的 `refs/heads/archive/github/<name>`（或进归档包），按 SHA 验收；再删 GitHub 上那 119 个已在 Gitea 引用上的；剩下 38 个在 GitHub 上留到 D-L2 同类定了再说。要你的 GitHub 凭证：我给能原样跑的命令，你在终端面板里跑 | 不动，留到以后 | 统筹线程里回 |
| D-L4 | 复核与 lane 的记录（约 2.11 GiB）和含独有对象的备份包放哪、留多久 | NAS 上一个持久归档，配一份仓库里的索引（`复核号 → 归档位置 + 校验值`），仓库文档里的 `~/agent-work/codex-review-<n>/` 引用改指索引；每份归档校验并试读一次；有引用的、标了保留的、归档失败的在本机留着；含独有对象的包永久留在归档里 | 全部永远留在本机，只清缓存 | 统筹线程里回 |
| D-L5 | 历史演练里「收下没合」的结果（19 条分支，按 mission：PROD M-1、M-2、M-3、M-4、M-13、M-15；STG M-2、M-16、M-23、M-24、M-26、M-27、M-103） | 我先出一张清单：环境、mission、任务、收下的尝试、SHA、放弃理由、归档位置；归档完成后再标 `no_merge`。注意 `no_merge` 是 mission 级的，影响整个 mission 的所有任务；计时从收下那刻算（`store/prune.go:225-227`），**标完下一轮 agentd 就可能删**，不会再等 24 小时 | 不标，留着（4.1 的 `accepted_at ≥ effective_at` 已经挡住它们，留着不出事，只是分支不清） | 写 PROD / STG 库是你的事：我出单子，你在 Console 批 |
| D-L6 | 非 agentd 机器（统筹 Mac、以后的 mini）的磁盘怎么进 Prometheus（新接口、新表，架构题） | platform-api 加一个主机上报口，一次定全：身份（每台机器一个只能报磁盘的令牌）、机器 id 与卷 id（挂载点 + 文件系统 UUID）、采样时间、过期规则（agentd 主机 15 分钟；会睡的机器标「未观测」）、安装方式（LaunchAgent / systemd）；platform 存每台机器每个卷的最近样本，和 agentd 主机共用一套指标名 | 每台机器装 node-exporter，Prometheus 越过网段来抓（要改 `monitoring` 的抓取配置；Mac 睡着时同样要处理成「未观测」） | 统筹线程里回；选 A 时接口与表的设计稿另给你签 |
| D-L7 | Tekton 保留期 | 不是新选择：你 10-10 已定（成功 24 小时、失败 7 天、每条流水线至少留 5 个、交付有发布记录才删）。**10-24 更正**：清单应用流水线在 `cicd` 不许写 CronJob，这份由你用管理员 kubeconfig 应用（`OWNER-STEPS-s7-tekton-ttl-2026-10-24.md`）；第一步只加单独 TaskRun 的清理和失败 Pod 留 7 天；「成功 24 小时」会删掉 push-main、release.sh、PROD 发布单要读的 CI run 和审批要读回的 plan run，先不做，见 TD-299 | — | 终端里跑操作单 |
| D-L8 | 历史上没登记、内容全在 Gitea 上的 76 个 worktree（没有会话已结束的证据；3 个 24 小时内、9 个 72 小时内有改动） | 统筹线程按 HEAD 提交的 `Claude-Session` 尾注和自己的线程记录逐个核对会话已结束，核对到的转可自动清、核对不了的留着；不占你的时间 | 你一次性确认清单 | 统筹线程定；你不回就按 A |

不列进待办的：Cursor `state.vscdb` 51 GiB（只有 Cursor 关着时你能压缩，`disk-guard.sh` 照旧每小时提醒）；只报不删的条目（每日清单里有，不需要你动作）。

---

## 附：没查到的与原因

- 06 的剩余磁盘、`AGENTD_ROOT` 下工作区以外的残留、06 上 agentd 的版本：Agent 登不上 06，平台只在跨过下限时记事件。
- 两台 mini 的磁盘与工作目录：同上，且没有 node-exporter。
- 集群 local-path 卷的实际占用（PVC 只有请求值）：要上节点 `du /var/lib/rancher/k3s/storage`。
- `agent/**` 到期未删的确切原因、M-27 Q07 收下的是哪次尝试：要读 PROD / STG 的事件流和 `verification`，归 S5。
- 13 条 infra `agent/` 分支是谁删的：时间窗口和剩下的两条都指向 agentd，删除记录没读。
- NAS 上有没有可用的归档、远端标签是否都推过：没访问 NAS，没核对远端标签。
- 「在用」只是一次 `lsof` 快照（只看得到本用户的进程），不是清理时的租约。
