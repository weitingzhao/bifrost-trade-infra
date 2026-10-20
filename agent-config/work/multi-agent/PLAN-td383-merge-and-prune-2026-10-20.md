# TD-383 收下即合并、agent/ 分支清理：薄版做了什么，哪些要你定（2026-10-20）

Owner 10-19 23:1x：「TD-383 排进主线：……接着做「收下即合并 + 运行时自动清理 agent/ 分支」，按停线规矩复核，PROD 合进下一张发布单」。
本页是这件的交回：第 1 节是不越线、已经做完的；第 2 节四件要你定，每件写了我的建议、在哪办、怎么回。

## 1. 已做（不加权限、不加路由、不碰 PROD）

工具 `bifrost-trade-infra/scripts/agentrt/merge_accepted.py`，把 10-19 统筹线程手工合 M-9、M-12、M-30、M-31 的做法写成一条命令：

| 子命令 | 做什么 |
|---|---|
| `list` | 列出已收下、但所在仓库 main 上没有它的 `Agentrt-Task` 尾注、且改动不为空的实现；有就退出 1（TD-383 防线里的「列出没进 main 的已收下任务」） |
| `plan <task>` | 只读：哪个 mission、哪件任务、收下的是第几次尝试、谁写的、谁评审的、提交和改了哪些文件、能不能推、合进去的提交说明 |
| `apply <task> [--push]` | 在 main 的新 worktree 上（CI 一样把 infra、bifrost-ui 放在旁边）cherry-pick 收下的提交：作者仍是 agentd，`Agentrt-Task`、`Change-Id` 原样，`Work` 加 TD-383，说明里写清 mission、任务、尝试、执行者、评审者、收下时间；跑整套（与 CI 同：go test、Console 四项、spine、ops-context、MCP）和 code-health；加 `--push` 才经 `push-main.sh` 推（窗口、快进、code-health 再查一次） |
| `prunable` | 只读：按 TD-383 的规则列出哪些 `agent/` 分支可删、为什么；不删任何东西 |

越线的地方它不做：

- **只推 bifrost-platform、bifrost-ui 的 main**：推这两个不启动任何发布（STG 由 Agent 发、PROD 由你批单）。其它仓库 `apply` 只建提交、跑检查，`--push` 拒绝并说明：推 infra 的 main 会让 Argo 把 `k8s/overlays/platform-*` 自动同步到 STG、PROD，`agent-config/` 是规则本身；其它仓库的 main 直接进交付或钉版本。
- **「已合」不另记**：合进 main 的提交带 `Agentrt-Task`，`list` 和 `prunable` 都按它判断；运行时不加记录路由。
- **TD-387**（运行时的检查里还没有 code-health）：`apply` 推之前跑 code-health，被拒会在推之前说清，不会推红 main。

测试：`scripts/agentrt/test_merge_accepted.py` 19 条，用临时目录里的 git 仓库和假运行时，不联网、不碰回环，运行时的 infra 检查会跑它。

实测（10-20 白天，只读，viewer 令牌）：

- **PROD 已收下、不在 main 的实现 10 件**：M-1 `t_01M511RV9S41AEW9CDA76024Q3`（GoalRepos 注释）、M-2 `t_01M51EHZ92V5F2PRB7JCZVHTQ3`（store.Repos 注释）、M-3 `t_01M55AN78GPF9V6NFZFS4KJP8N`（safego 边界测试）、M-3 `t_01M55AN78M1MX9NF9Q958T96Z3`（statefile 边界测试）、M-4 `t_01M56J5QPAAQQP53KV4MQYCW5Q`（safego.Go 注释）、M-13 `t_01M5BSTGPP9FC3PCF4NF5PM7GD`（Gate B 实测写环境变量名）、M-15 四道基准题（Q04、Q06、Q07、Q18 的回放）。我的看法：M-1～M-4 五件可以用 `plan` 看过再 `apply`；M-13、M-15 五件是实测和基准回放，不该合——但运行时里没有地方写「这件不合、为什么」，见 2.3。
- **agent/ 分支 53 条**（都在 bifrost-platform，bifrost-ui 没有）：按规则今天可删 0 条——PROD 10 条、STG 9 条的任务已收下但不在 main；8 条已在 main、但不满 7 天；2 条被后来的尝试取代、不满 7 天；其余的任务还开着（PROD 4 条 ready，含 M-9 第五件；STG 4 条 ready、16 条 verifying）。

## 2. 要你定的四件

### 2.1 收下即合并由谁执行

- **建议 A**：第 2 轮维持「统筹线程每收下一件，跑一次 `merge_accepted.py --env prod apply <task> --push`」，每轮再跑一次 `list` 补漏。和你 10-19 21:4x「核对后合」是同一授权，不加任何权限。
- B：运行时自己合：控制器在验收通过的同一轮建一件「合并」任务，06 的 agentd 领去跑 `apply` 并推 main。要两样新东西：给 06 一个能推 bifrost-platform、bifrost-ui main 的 Gitea 身份（今天 main 只许 maintainers 团队和你推），和任务 `role` 的一个新取值（数据库迁移）。等于把「核对后合」改成「合后可查」。
- C：Ops 动作目录里加一个具名动作「合并已收下的结果」，用平台自己的受限身份推（ADR §5 的形态）。平台 Pod 里没有 Go 和 npm，跑整套仍要借 06。

在哪办：统筹线程。怎么回：「TD-383 合并 A」（或 B、C）。

### 2.2 infra 以及其它仓库的收下结果

- **建议 A**：继续由统筹线程手工合、合之前给你看（今天的做法）；工具对这些仓库只建只查、不推。按路径放行要一张手写的允许清单，容易漏。
- B：签一条「infra 可自动合的路径」规则（例如只有 `scripts/**/test_*.py`），全部命中才推，其余照 A。

在哪办：统筹线程。怎么回：「TD-383 infra A」（或 B，写上路径）。

### 2.3 「这件不合」记在哪

TD-383 的验收要「PROD 上每件已收下的实现要么在 main，要么写明为什么不合」。今天没有地方写后半句。

- **建议 A**：提议 mission 时可选写一个不合并的标记（演练、基准题、门槛实测这类 mission 写上），`list` 跳过并显示原因。要改 mission 提议的公开接口（`propose_mission` / `POST /agentrt/missions` 多一个可选字段），属架构级。
- B：infra 里一张「不合清单」（任务号 + 原因），统筹线程维护，`list` 读它。不改接口，但是手抄的表。
- C：统筹线程给这件任务发一条挂在任务上的消息（现有 `POST /agentrt/messages`），`list` 认固定开头。不改接口，但靠文字约定。

在哪办：统筹线程。怎么回：「TD-383 不合 A」（或 B、C）。

### 2.4 agent/ 分支由谁删、保护规则怎么改

现状：Gitea 1.21 上受保护的分支谁都删不了；`agent/**` 的保护规则只许 agentd-write 团队和你推（`scripts/gitea/protect-repo.sh`）。10-19 你那次 `--apply` 只删掉 17 条，就是撞上了它。删的规则 TD-383 已写：任务已收下且在 main、被拒、被取消，或这次尝试已被后来的尝试取代，满 7 天就删；还开着的任务、两边运行时都不认识的分支不删。PROD 和 STG 推到同一个 Gitea 仓库，所以清理要两边都问（`prunable` 已经这样做）。

- A：保留保护；`prunable` 出清单，你用自己的身份定期删（不算自动）。
- **建议 B**：去掉 `agent/**` 的保护规则（main 的保护不动），清理在运行时的一轮里做。代价是 agent/ 分支不再只有 agentd 能写；但收下和合并都按提交号（`pushed_commit`）取，分支事后被改或删不影响已收下的结果，收下前被改则结果核对对不上、这次尝试作废。删的身份二选一：06 的 agentd（已在 agentd-write 团队，不新增凭证，但平台要给 06 派「清理」这种新活）；或新建一个只在 agentd-write 团队里的 Gitea 用户，令牌由你做成 Secret 给平台。
- C：把 agent 分支挪回单独的组织（10-17 之前的 `bifrost-agents`），那里不设保护、只给 agentd-write 和清理身份写权限。代码已支持（`AGENTRT_GIT_ORG`），但要改 STG、PROD 的接线和 agentd 的推送地址，撤回 10-17 的一部分做法。

在哪办：统筹线程（选定后 Gitea 的规则和身份由你在 Gitea 上改，或给我一张 `owner_run_command` 单）。怎么回：「TD-383 分支 B，用 agentd」（或别的组合）。

## 3. 不在这次范围

- TD-387：把 code-health 放进运行时对 platform 的检查，让「收下」和「能合」一致。`apply` 只是在推之前拦住。
- STG 上 16 条分支的任务停在 verifying，值得看一眼是否卡住（本次没查）。
- `ensureCheck` 把旧的 salvage 检查也算作「还有检查开着」，因此不补新检查（TD-384 之前就是这样；复核 430 第 4 节）。
