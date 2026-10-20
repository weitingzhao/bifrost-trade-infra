# TD-383 收下即合并、agent/ 分支清理：薄版做了什么，哪些要你定（2026-10-20）

Owner 10-19 23:1x：「TD-383 排进主线：……接着做「收下即合并 + 运行时自动清理 agent/ 分支」，按停线规矩复核，PROD 合进下一张发布单」。
本页是这件的交回：第 1 节是不越线、已经做完的；第 2 节四件要你定，每件写了我的建议、在哪办、怎么回。

## 1. 已做（不加权限、不加路由、不碰 PROD）

工具 `bifrost-trade-infra/scripts/agentrt/merge_accepted.py`，把 10-19 统筹线程手工合 M-9、M-12、M-30、M-31 的做法写成一条命令：

| 子命令 | 做什么 |
|---|---|
| `list` | 列出已收下、还没落到所在仓库 main 上、且改动不为空的实现；有就退出 1（TD-383 防线里的「列出没进 main 的已收下任务」）。「落到 main」：main 上有提交带它的 `Agentrt-Task`，或带收下那次提交的 `Change-Id`（手工合时丢了任务尾注也认得），且之后没有提交 revert 它 |
| `plan <task>` | 只读：哪个 mission、哪件任务、收下的是第几次尝试、谁写的、谁评审的、提交和改了哪些文件、能不能推、合进去的提交说明 |
| `apply <task> [--push]` | 在 main 的新 worktree 上（CI 一样把 infra、bifrost-ui 放在旁边）cherry-pick 收下的提交：作者仍是 agentd，`Agentrt-Task`、`Change-Id` 原样（值要对得上这件任务），`Work` 加 TD-383，说明里写清 mission、任务、尝试、执行者、评审者、收下时间；跑 CI 的整套（go test 且数据库测试必须跑、Console 四项、spine、ops-context，外加 MCP）和 code-health，没配测试库和 Redis 就不开始；加 `--push` 才经 `push-main.sh` 推（窗口、快进、code-health 再查一次）。建不成就把自己建的 worktree 删掉，同一目录可以重跑 |
| `prunable` | 只读：按 TD-383 的规则列出 `agent/` 分支哪些可删、为什么；不删任何东西 |

越线的地方它不做：

- **只推 bifrost-platform 的 main**：推它只启动它自己的 CI，不启动发布（STG 由 Agent 发、PROD 由你批单）。其它仓库 `apply` 只建提交，`--push` 拒绝并说明：bifrost-ui 的 main 是 Console 和 Trade 前端编译时用的，它们的检查这里不跑；推 infra 的 main 会让 Argo 把 `k8s/overlays/platform-*` 自动同步到 STG、PROD，`agent-config/` 是规则本身；别的仓库不在这次的范围，照各自的发布规矩。这里没有检查的仓库（今天除 platform 外都是）只建不验，退出码 4，不算通过。
- **它是统筹线程的助手**：统筹线程本来就能推 main，这个工具不给任何人新权限，也不是挡别人的闸门。
- **「已合」不另记**：合进 main 的提交带 `Agentrt-Task` 和 `Change-Id`，`list`、`plan`、`prunable` 都按它们判断（被 revert 的不算）；运行时不加记录路由。
- **TD-387**（运行时的检查里还没有 code-health）：`apply` 推之前跑 code-health，被拒会在推之前说清，不会推红 main。

测试：`scripts/agentrt/test_merge_accepted.py` 33 条，用临时目录里的 git 仓库和假运行时，不联网、不碰回环，运行时的 infra 检查会跑它。

端到端演练（10-20，只读运行时、不推）：M-3 `t_01M55AN78GPF9V6NFZFS4KJP8N` 在今天的 platform main 上建成，作者 agentd、说明和尾注与 10-19 手工合的格式一致，整套（73 个 Go 包含数据库测试、Console、spine、ops-context、MCP）和 code-health 全过；M-2 `t_01M51EHZ92V5F2PRB7JCZVHTQ3` 在今天的 main 上冲突（repos.go 改动太多），工具拒绝并说明，什么也没推。

实测（10-20 白天，只读，viewer 令牌）：

- **PROD 已收下、不在 main 的实现 10 件**：M-1 `t_01M511RV9S41AEW9CDA76024Q3`（GoalRepos 注释）、M-2 `t_01M51EHZ92V5F2PRB7JCZVHTQ3`（store.Repos 注释）、M-3 `t_01M55AN78GPF9V6NFZFS4KJP8N`（safego 边界测试）、M-3 `t_01M55AN78M1MX9NF9Q958T96Z3`（statefile 边界测试）、M-4 `t_01M56J5QPAAQQP53KV4MQYCW5Q`（safego.Go 注释）、M-13 `t_01M5BSTGPP9FC3PCF4NF5PM7GD`（Gate B 实测写环境变量名）、M-15 四道基准题（Q04、Q06、Q07、Q18 的回放）。我的看法：M-1～M-4 五件可以用 `plan` 看过再 `apply`；M-13、M-15 五件是实测和基准回放，不该合——但运行时里没有地方写「这件不合、为什么」，见 2.3。
- **agent/ 分支 53 条**（都在 bifrost-platform，bifrost-ui 没有）：按规则今天可删 0 条——PROD 10 条、STG 9 条的任务已收下但不在 main；8 条已在 main、但不满 7 天；2 条被后来的尝试取代、不满 7 天；其余的任务还开着（PROD 4 条 ready，含 M-9 第五件；STG 4 条 ready、16 条 verifying）。（复核 433 之后的新版——7 天从任务结束、被取代或落到 main 时算，两边运行时都问——10-20 重跑，数字相同。）

## 2. 要你定的四件

### 2.1 收下即合并由谁执行

- **建议 A**：第 2 轮维持「统筹线程每收下一件，跑一次 `merge_accepted.py --env prod apply <task> --push`」，每轮再跑一次 `list` 补漏。和你 10-19 21:4x「核对后合」是同一授权，不加任何权限。
- B：运行时自己合：控制器在验收通过的同一轮建一件「合并」任务（用现有的 `other` 角色即可，专门加一个角色更清楚但要迁移），06 的 agentd 领去跑 `apply` 并推 main。新东西是给 06 一个能推 bifrost-platform main 的 Gitea 身份（今天 main 只许 maintainers 团队和你推）。等于把「核对后合」改成「合后可查」；`apply` 的检查是整套和 code-health，不等于统筹线程的核对。
- C：Ops 动作目录里加一个具名动作「合并已收下的结果」，用平台自己的受限身份推（ADR §5 的形态）。平台 Pod 里没有 Go 和 npm，跑整套仍要借 06。

在哪办：统筹线程。怎么回：「TD-383 合并 A」（或 B、C）。

### 2.2 infra 以及其它仓库的收下结果

- **建议 A**：继续由统筹线程手工合、合之前给你看（今天的做法）；工具对这些仓库只建只查、不推。按路径放行要一张手写的允许清单，容易漏。
- B：签一条「infra 可自动合的路径」规则（例如只有 `scripts/**/test_*.py`），全部命中才推，其余照 A。

在哪办：统筹线程。怎么回：「TD-383 infra A」（或 B，写上路径）。

### 2.3 「这件不合」记在哪

TD-383 的验收要「PROD 上每件已收下的实现要么在 main，要么写明为什么不合」。今天能写（比如挂在任务上的消息），但没有工具能认出来的结构化约定。

- **建议 A**：提议 mission 时可选写一个不合并的标记（演练、基准题、门槛实测这类 mission 写上），`list` 跳过并显示原因。要改 mission 提议的公开接口（`propose_mission` / `POST /agentrt/missions` 多一个可选字段），属架构级。
- B：infra 里一张「不合清单」（任务号 + 原因），统筹线程维护，`list` 读它。不改接口，但是手抄的表。
- C：统筹线程给这件任务发一条挂在任务上的消息（现有 `POST /agentrt/messages`），`list` 认固定开头。不改接口，但靠文字约定。

在哪办：统筹线程。怎么回：「TD-383 不合 A」（或 B、C）。

### 2.4 agent/ 分支由谁删、保护规则怎么改

现状：Gitea 1.21 上受保护的分支不能删，你的身份也不例外（`CUT-gitea-primary-2026-10-17.md` 与保护探针都这样记）；`agent/**` 的保护规则只许 agentd-write 团队和你推（`scripts/gitea/protect-repo.sh`）。10-19 你那次 `--apply` 只删掉 17 条，就是撞上了它。删的规则 TD-383 已写：任务已收下且落到 main、被拒、被取消，或这次尝试已被后来的尝试取代，满 7 天就删（从那件事发生时算）；还开着的任务、收下了但没落到 main 或落了又被 revert 的结果、两边运行时都不认识或都认识的分支，都不删。PROD 和 STG 推到同一个 Gitea 仓库，所以清理要两边都问（`prunable` 已经这样做）。

先说清分支对结果有多重要：结果写入时，平台核对分支头就是 agentd 报的提交；之后的验收按提交号检出（agentd detach 到那个提交），合并也按提交号 cherry-pick——所以分支被改，验收不会验到别的代码。但这些都要能从 Gitea 取到那个提交：分支删了，提交可能取不到（也可能被 Gitea 回收），验收失败、合并做不成。所以收下了但还没落到 main 的结果，它的分支必须留着。

- A：保留保护，暂不删；或者由你在 Gitea 上临时去掉保护、按 `prunable` 的清单删、再恢复（你的管理员动作，期间 agent/ 分支没有保护）。不算自动。
- **建议 B**：去掉 `agent/**` 的保护规则（main 的保护不动），清理在运行时的一轮里按上面的规则做。代价：仓库上有写权限的人和身份（agentd-write 团队、maintainers）都能强推或删任何 agent/ 分支，包括还没落到 main 的结果；规则保证清理本身不删这些，但挡不住别的写入方。删的身份二选一：06 的 agentd（已在 agentd-write 团队，不新增凭证，但平台要给 06 派「清理」这种新活）；或新建一个 Gitea 用户（令牌由你做成 Secret 给平台）——Gitea 的令牌管不到「只能删清单里的分支」，它能写就能删任何没保护的分支。
- C：把 agent 分支挪回单独的组织（10-17 之前的 `bifrost-agents`），那里不设保护、只给 agentd-write 和清理身份写权限。代码已支持（`AGENTRT_GIT_ORG`），但要改 STG、PROD 的接线和 agentd 的推送地址，撤回 10-17 的一部分做法。

在哪办：统筹线程（选定后 Gitea 的规则和身份由你在 Gitea 上改，或给我一张 `owner_run_command` 单）。怎么回：「TD-383 分支 B，用 agentd」（或别的组合）。

## 3. 不在这次范围

- TD-387：把 code-health 放进运行时对 platform 的检查，让「收下」和「能合」一致。`apply` 只是在推之前拦住。
- STG 上 16 条分支的任务停在 verifying，值得看一眼是否卡住（本次没查）。
- `ensureCheck` 把旧的 salvage 检查也算作「还有检查开着」，因此不补新检查（TD-384 之前就是这样；复核 430 第 4 节）。
