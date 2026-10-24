# 切法：4.1 交房——验收通过的活由运行时自己合进 main（2026-10-24）

**这份文档回答什么**：Owner 10-23 23:3x 定「D4 A」（验收通过的活由运行时自动进 main，先 bifrost-platform、bifrost-trade-infra，PROD 仍按发版策略，规则由 Owner 签）。这里写：今天一件活从 agentd 推分支到进 main 实际怎么走（§1，带 `文件:行`）；运行时自己合要做哪些步骤、谁来做、出错怎么退回（§2）；分几片做、每片怎么验收、哪几片要 Owner（§3）。
**Owner 要定什么**：五个架构级选择（§4，各有推荐）和规则 `landing:dev` 的内容（§2.8）；动手的有三类——签规则、在 Gitea 建身份并加进 main 的推送名单、批发布单（§3 末列）。全部待定点在 §5。

读的版本：infra `639edc9`（含第 4 轮逐项），platform `origin/main` = `82b3e9d7`；PROD 运行时库 `bifrost_platform` 2026-10-24 04:52Z 只读查询（`agent_reader`）；集群只读 `kubectl get`。切法本身**还没有独立复核**（4.1 第二步）。

---

## 0. 一段话

今天运行时把活做到 `accepted` 就停了：结果留在 `agent/<任务>/a<n>`，要统筹线程用 `merge_accepted.py` 手工 cherry-pick、跑整套、经 `push-main.sh` 推（TD-383）；运行时只在别人合进去之后补记一笔。推荐的做法：**PROD 的 platform-workers 控制器多一个「落地」循环**，在 main 最新提交上重放收下的那个提交，推到 `land/prod/<任务>/<k>` 让 CI 按推送自己起，CI 绿、窗口关着、main 没动，才把**同一个提交**快进推到 main；冲突、重放改了评审过的差异、或 CI 红，就在同一个 mission 里开一个「落地」任务退回给执行者，不找 Owner。合进 platform 后由同一循环持窗口发 STG。凭证是一个只在 platform、infra 两个仓库 main 推送名单里的新 Gitea 用户，令牌只进 PROD 的 platform-workers；那个 Pod 只跑 Owner 批过的 PROD 代码，执行者写的代码进不去。

---

## 1. 现状实读

### 1.1 一件 implement 任务今天怎么走到 main

| 步 | 谁 | 实读 |
|---|---|---|
| 建任务 | 控制器（计划结果） | base 取当时 main 的头：`store/planresult.go:247-249` `BaseCommit: baseOf(pt.Repo)` |
| 执行、提交 | agentd（06） | 提交带三个尾注 `Agentrt-Task`、`Change-Id`、`Work`，**没有 `Claude-Session`**：`agentd/workspace.go:343-350` |
| 推分支 | agentd | 只许推 `refs/heads/agent/`：`agentd/workspace.go:355-358`；分支名固定 `agent/<task>/a<n>`：`store/kernel.go:78-81` |
| 验收 | 控制器 | 确定性检查 → 异家评审 → 评审通过即 `accepted`：`store/accept.go:13-21`、`:398-407`；检查的命令写死在 `store/repos.go:68-95`（只有 platform、infra 两个仓库） |
| 状态 | — | `accepted` 是终态，表里没有从它出去的边：`store/kernel.go:132-143`；库里 `task.state` 有 CHECK 约束：`migrations/0001_core.sql:135-136` |
| mission 结束 | 控制器 | 任务全部 `accepted` 就关成 done，**不看进没进 main**：`store/close.go:40-45` |
| 进 main | **统筹线程手工** | `merge_accepted.py apply --push`（§1.2），或手工 cherry-pick + `push-main.sh` |
| 补记 | 控制器 | 每 5 分钟读 main，见到收下的那个提交（或它的 cherry-pick 行）就记一条 `note{landed}`：`controller/controller.go:426-442`、`store/prune.go:364-437`；main 经 Gitea API 读：`server/agentrt_prune.go:39-59` |
| 删分支 | agentd（用自己的 Gitea 身份） | 规则 `store/prune.go:16-47`，`PruneAfter` 24 小时（`:50`），从 `landed` 那条 note 起算 |

实测（PROD，10-24 04:52Z）：`accepted` 的 implement 任务 20 件（platform 17、infra 3），有 `landed` note 的 10 件；没有的 10 件全在 M-1～M-15（演练、门槛实测，其中 M-13、M-15 没有 `no_merge` 标记，TD-383 原文已记）。`pruned` note 23 条，最后一条 `landed` 在 10-21 19:15Z。

### 1.2 `merge_accepted.py` 做了什么（infra `scripts/agentrt/merge_accepted.py`）

- 定位收下的尝试：任务最后一次 `verification_recorded{method: review, verdict: pass}` 指的那次尝试（`:246-292`）；mission 有 `no_merge` 就拒绝（`:458-459`）。
- 只接「任务 base 上的一个提交」，否则让人手工合（`:391-400`）；按任务尾注和 Change-Id 查是否已在 main、是否被 `git revert` 撤掉（`:329-384`）。
- 在 main 的干净 worktree 里 cherry-pick，改写提交信息：保留 `Agentrt-Task`、`Change-Id`，`Work` 加 `TD-383`，正文加一段「哪个 mission / 任务 / 尝试 / 评审方」和 `(cherry picked from commit …)` 行（`:410-445`、`:472-513`）。
- 跑该仓库 CI 的整套（只有 platform 有，`SUITES` `:83-98`，数据库测试必须不跳过 `:99-101`）加 code-health（`:526-540`）；`--push` 只对 `PUSHABLE = {"bifrost-platform"}`（`:71`），infra 不推，理由是 Argo 同步它的 `k8s/`、`agent-config/` 放规则（`:72-75`）；推用 `push-main.sh`（`:552-553`）。
- `list` 列出收下而没进 main 的（`:558-598`）；`prunable` 只报不删（`:601-702`）。

### 1.3 TD-383 原文（`agent-config/TECH_DEBT.md:2706-2717`）

标题「an attempt's branch has no lifecycle: accepted work never reaches main, and nothing deletes the branches」。Fix 原文：「until the release queue, an accepted implementation's branch is merged into main through `push-main.sh` by the coordinator (fast-forward after a rebase, the suite and code-health on the merged tree), recorded on the task; a runtime pass deletes an attempt branch …」。验收：「on PROD every accepted implementation's attempt commit is in main or its task says why not, and no `agent/` branch is older than 7 days without an open task」。状态「在做」，剩 PROD 上第一条 `pruned` note（已有 23 条，可以进签收）。同组的 TD-387（`TECH_DEBT.md:2653-2664`）：platform 任务的检查不跑 code-health，10-20 M-31 收下的修复在 `push-main.sh` 被拒（文件超 800 行），统筹线程手工拆文件。

### 1.4 Gitea 的分支保护（1.21.11，`k8s/cicd/gitea/deployment.yaml:60`）

- `main`：推送白名单和合并白名单都只有团队 `maintainers`（Owner、`bifrost-mbp`）和 Owner 本人（`scripts/gitea/protect-repo.sh:5-7`、`:205-218`；切法目标 `CUT-gitea-primary-2026-10-17.md:140`）。1.21 管理员不例外；不开合并白名单时有写权限就能合 PR，所以两样都开（同文 `:117-118`）。受保护分支谁都不能删、不能强推（`:119`）。
- `agent/**`：10-20 14:38 由 Owner 去掉（TD-383「分支 B 用 agentd」，`protect-repo.sh:8-12`、`:243-256`），agentd 才能删尝试分支。现在 `agentd-write` 团队能推、强推、删任何非 main 分支。
- `protect-repo.sh` 只比对 main 规则和基线、不改（`:13-17`）：给某个仓库加一个推送用户，脚本会报 DIFFERS，要给基线加「按仓库的额外用户」。

### 1.5 推 main 的现行门槛（infra `scripts/release/push-main.sh`）

窗口关着（`:182-190`、`:273`）→ 只快进（`:275-277`）→ 新增的每个提交都有 `Change-Id` **和 `Claude-Session`**（`:290-316`，运行时的提交没有后者，只能 `--no-lineage`）→ 该提交有 Succeeded 的 `ci-*`（`:452-505`；`CI_REPOS` `:117` 不含 infra，infra「has no CI of its own」）→ code-health 扫这个提交的干净 worktree（`GATED` `:113`，不含 infra；`:534-540`）→ 快测（infra pytest `scripts/{release,agentrt,agent-host}`，platform `go vet` + 改到的包，`:318-402`）→ **再查一次窗口**（`:558`）→ `git push origin <c>:refs/heads/main`（`:559`）。preflight 拦直接 `git push` 到 main。

### 1.6 CI

- 推任何分支都起 CI（Owner 10-21「D3 A」，`k8s/cicd/tekton/trigger-trade-ci.yaml:221-225`）；删分支不起。按仓库分三条：python、frontend、platform；**没有 infra 的 CI**（`:227-305` 各条的仓库名单）。
- Gitea 做主后推送当即起 CI（TD-155，`TECH_DEBT.md:16`，10-23 实测推分支 3 秒就有 `ci-platform-*`，待签收）。
- CI 的 code-health 用的是**现克隆的 infra main** 上的 `scan.sh` 和基线（`task-code-health.yaml:54`）；ci-platform 还跑 infra 的 `check_ops_context_parity.py`。所以 infra 的部分脚本改了，所有仓库的闸门跟着变。
- 实测（10-17～10-24，`kubectl get pipelineruns`）：`bifrost-ci-platform` 146 次，Succeeded 128、Failed 18；成功的中位 6.3 分钟、p90 8.3、最长 9.7。
- 运行时已能按「仓库 + 提交」读 CI 结果（`controller.go:200-209`，来自 `delivery.PolicyFacts().CIRun`，`delivery/release_policy_facts.go:241`）。

### 1.7 STG 发版的现行规则

工作区 `CLAUDE.md` §5（`agent-config/CLAUDE.md:220-224`）：STG 两个环境的发版和清单改动由 Agent 做、不用问，三个前提——该提交 `ci-*` Succeeded（不用 `--allow-red`）、先持窗口且一次一个会话、发完自己核对 Pod 跑的提交和启动日志并报结果。窗口只有一个（ConfigMap `cicd/bifrost-release-window`，`delivery/release_window.go:14-19`）；`bifrost-deliver-platform` 要求窗口的 `what` 含 platform 或 ui、`who` 等于持有者（`:37`、`:141-183`）。只有 PROD 的平台身份能建 PipelineRun（`k8s/platform-rbac/00-clusterroles.yaml:7-16`、`:167-171`），STG 发版也经 PROD 的 platform-api。STG 发布流水线会先跑 agentrt 的库迁移（`task-agentrt-migrate-stg.yaml:1-10`）。

### 1.8 常备授权 `standing-envelope:dev`

PROD 版 `agentrt-rules/prod/standing-envelope-dev.yaml:1-12`：`max_action: branch`、预算 40 次尝试 / 48 小时、四家执行者、主机 `agent-06`。解析器只认 `none`、`branch`，注释写「C-class actions are never in an envelope」（`rules/rules.go:81`）。规则种类与「收紧不签名、放宽要签」见 `agentrt-rules/README.md:22-35`。**合进 main 不在任何现有规则里**——这就是 D4 说的「放宽规则由 Owner 签」。

### 1.9 读到的另外几条事实

- platform-workers 的镜像是只装 Go 程序的 alpine，**没有 git**（`k8s/cicd/docker/Dockerfile.platform-api-stg`）；PROD 的 platform-workers 1 个副本，内存上限 512Mi。两个仓库的 pack 只有 11 MiB、9 MiB。
- STG 和 PROD 的平台身份都能读 `cicd/gitea-bootstrap`（`00-clusterroles.yaml:98-104`），里面是 Gitea 管理员令牌（`delivery/service.go:1292-1308`）。也就是说，platform-api 被攻破时，攻击者本来就能改分支保护；加一个只能推两个仓库 main 的令牌，不增加这个 Pod 已有的权限范围，只是多一个审计上分得清的身份。
- 06 上的执行者和 agentd 同一系统用户，**读不受限**（`CUT-agentd-confine-2026-10-19.md:15`「同一用户下令牌文件仍可读」）。
- Argo 的 `bifrost-platform-{stg,prod}` 自动同步 infra main 的 `k8s/overlays/platform-{stg,prod}`（`k8s/cicd/applications/bifrost-platform-*.yaml:13-22`，`AGENT_FACTS.md:414`）；两个 overlay 和 `k8s/base-platform` 里没有指向 `k8s/` 外的链接（`find -type l` 为空），所以 infra 里 `k8s/` 以外的改动不会经 Argo 改运行时。
- platform main 近 7 天 387 个一线提交（`git log --first-parent`；提交时间不是推送时间，只能说明 main 动得很勤）。

---

## 2. 设计

### 2.1 谁执行合入

| | A. PROD platform-workers 的控制器（git 在 Pod 里做） | B. 06 上的 agentd，用专用 Gitea 身份 | C. Tekton 流水线（控制器起 run） |
|---|---|---|---|
| 怎么做 | 新循环 `Land`，复用 agentd 的 git 封装（`runGit`、`isolatedGit`），镜像加 `git` | 平台把「落地」当一种新活派给 agentd，像今天的删分支 | `bifrost-land-replay` 与 `bifrost-land-promote` 两条流水线，控制器按步起、读结果 |
| 令牌放哪 | 新 Secret `bifrost-platform-prod/agentrt-lander`，只挂进 platform-workers | 06 上 agentd 的家目录 | 新 Secret `cicd/agentrt-lander` |
| 谁的代码能碰到令牌 | 只有 Owner 批过的 PROD 平台代码（执行者写的代码要经发布单才进这个 Pod） | **执行者能读**（同一用户，读不受限，§1.9）：执行者可以绕过 CI 和评审直接推 main | cicd 里能建 Pod 的都能挂任意 Secret；PROD 平台本来就能建 PipelineRun；CI 也在 cicd 跑执行者写的测试（它的 SA 能做什么没查） |
| 爆炸半径（令牌泄露） | 两个仓库的 main，只能快进，不能强推、删、建标签 | 同左，但泄露面是跑模型代码的主机 | 同 A |
| 离线时 | workers 停 → 不合；已收下的排着，不丢（状态在库里） | 06 停 → 不合（也不派活） | Tekton 停 → 不合（CI 也停） |
| 改动面 | 平台代码 + 镜像一行 + 一个 Secret | agentd + 新活类型 + 06 单元；要么接受执行者可读，要么在 06 另起一个系统用户和服务 | 两条流水线（Owner 应用）+ 控制器编排 + Secret |
| 状态机在哪 | 运行时库里，和收下、删分支在一处 | 平台派、agentd 报，和删分支同一个模式 | 一半在 PipelineRun，一半在运行时 |

**推荐 A**。理由：令牌所在的 Pod 只跑 Owner 批过的代码，这是三者里唯一能断开「写代码的执行者」和「推 main 的凭证」的；B 的读权限问题在第 2 轮被明确接受为例外，不能拿来扛推 main。C 可行，但多两条要 Owner 应用的流水线，多一层状态同步，换来的只是 git 不在 workers 里跑。只用 Gitea API、不在 Pod 里跑 git 的做法不推荐：1.21 的合并接口改写不了提交信息（除 squash 外），也给不出「先在确切的那个提交上跑 CI、再动 main」——合并结果在合并之前不存在。

### 2.2 合入步骤（PROD，一次一件、每个仓库同时最多一件在途）

1. **入队**：`accepted` 的 implement 任务，仓库在规则里；mission 没有 `no_merge`、状态是 active 或 done；**收下时间不早于规则生效时间**（M-1～M-15 那 10 件不会被自动合）；没有 `landed` note、没有终结的落地 note（§2.9）；它依赖的任务都已落地。按收下时间排。
2. **预检**：收下的提交必须是任务 base 上的一个提交（沿用 `merge_accepted.py:391-400`）；改到的文件全部落在规则允许的路径、不碰规则和代码里的禁止路径（§2.8），行数、文件数不超上限。不满足的不自动合，开一张「这件要合吗」的卡（§2.4 末）。
3. **重放**：取 main 头 `M0`，在干净的工作目录 `git cherry-pick <收下的提交>`；冲突 → 退回（§2.4）。再比较 `git patch-id --stable`：重放前后差异的 patch-id 不同（三方合并自动改了评审过的内容）→ 也按冲突退回。提交信息按 `merge_accepted.py:410-445` 的规则写，另加尾注 `Landed-By: agentrt-prod`；作者保持原执行者，提交者是落地身份。
4. **推落地分支**：推到 `refs/heads/land/prod/<任务>/<k>`（`k` 是这件第几次重放），推送当即起 CI；记 note `landing{phase: replayed, replay, main: M0, k}`。
5. **等 CI**：按「仓库 + 重放提交」读（§1.6）。Succeeded → 第 6 步。Failed → 先看 `M0` 自己的 CI：不是 Succeeded 就是 main 红、不怪这件，等；main 绿就以同一个提交重跑一次（PROD 平台能直接建 `ci-*` 的 PipelineRun），还红再退回。15 分钟没有 run → 直接建一个；45 分钟还没有 → 记 note，接着等。
6. **推之前再查**：规则仍有效且仍含这个仓库、mission 不是 stopped / paused、窗口不挡这个仓库（§2.6）、main 的头仍是 `M0`。main 动了 → 回第 3 步（记一次「抢输」）。
7. **推 main**：`git push origin <重放提交>:refs/heads/main`，不带 force。被拒（不是快进）→ 回第 3 步。推成功后 `ls-remote` 确认 main 就是这个提交，再写 `note{landed}`（文字格式与 `prune.go:425-427` 相同）和 `landing{phase: landed}`。
8. **收尾**：删 `land/prod/<任务>/<k>`（只在它仍指向这个提交时）；该仓库排队空了就发 STG（§2.6）。

CI 只认「这个仓库在这个提交上的 run」，所以别人往 `land/**` 推什么都没用：第 7 步推的永远是第 3 步自己做出来、记在 note 里的那个提交。

### 2.3 和人手 `push-main.sh` 抢 main

两边都只快进、Gitea 不许任何人强推 main，所以**抢输的一方只会被拒，不会覆盖**，安全靠服务端。代价是重放和 CI 白跑一轮（约 6–8 分钟）。规矩：

- 第 4 轮之前（D2 没做完、窗口只有一个）：不持窗口，抢输就重放，同一件一小时最多重放 6 次，超过就停一小时、记 note。持全局窗口会连带挡住 Trade 和 research 的发布，不值。
- D2 的按应用窗口上线后：同一件连续抢输两次，第三次从重放到推 main 持「这个仓库所属应用」的窗口（ttl 5 分钟、每分钟续），`push-main.sh` 遇到它就等。
- `push-main.sh` 不改抢的逻辑；只改一处：`Agentrt-Task` 也算血缘（今天它要求 `Claude-Session`，`:290-316`），这样人手补合运行时的活不用 `--no-lineage`。

### 2.4 冲突、CI 红怎么退回原任务

`accepted` 是终态（§1.1），退回有两条路，见 §4 X2。推荐 **在同一个 mission 里开一个「落地」任务**：

- 新 implement 任务，标题「落地：<原标题>」，`parent_task_id` 指原任务，base 是当前 main 的头，说明书 = 原说明书 + 退回原因 + 收下的那个差异（产物）。原因三类，都带证据：冲突（文件清单、`M0`）；重放改了评审过的差异（两个 patch-id）；CI 红（run 名、失败的 TaskRun、最后 40 行，按平台现有的脱敏）。
- 它照常过确定性检查和异家评审，收下后由同一个循环落地。原任务记 `landing{phase: returned, reason, follow_up}`。
- 一条链最多退回两次；第三次走现有的卡住卡（`failWork` → blocked card），这时才到人手上。
- 预算照常记在 mission 上；预算用完照现有规矩卡住。
- **mission 不再在「全部收下」时就关**：`close.go:40-45` 多一条——规则覆盖的仓库里，收下而既没落地、也没被退回的 implement 任务，让 mission 保持 active。这样「done」就等于「进了 main」，退回的新任务也能被派出去（只派 active 的 mission）。

预检不过的（禁止路径、超上限、依赖或迁移改动）不退回，开一张决定卡：推荐项「合」（Owner 点了就按第 3 步起照常走，记成 Owner 批的落地），另一项「不合」（记 `landing{phase: declined}`，`merge_accepted.py list` 不再报它）。这是唯一会找 Owner 的情形，按 Owner 定的规则内容出现得少。

### 2.5 代码健康扫描放哪

- **权威在 CI**：ci-platform 本来就有 code-health 任务，第 5 步等的就是它；不另跑。
- **提前在验收**：做掉 TD-387——platform 任务的确定性检查加 `scan.sh --repo bifrost-platform`（对 main 的基线），超了在验收阶段就退给执行者，不等到落地才发现。
- 落地循环自己不跑任何测试和扫描，Pod 里只有 git。
- infra 没有 CI（§1.6），见 X5。

### 2.6 合入后发 STG，窗口怎么持，怎么接 D2

- 只对 platform：该仓库没有在途和排队的落地、且最近一次落地满 5 分钟（一阵子落几件只发一次）；main 头的 `ci-*` 是 Succeeded（§1.7 第一个前提）。
- 持窗口：以 `who=agentrt-prod`、`what=bifrost-platform` 经 delivery 服务写窗口（ttl 5 分钟、每分钟续）；窗口被别人持着就等，30 分钟记一条 note，**从不清别人的窗口**（清窗口是 C 级）。持到后起 `bifrost-deliver-platform`（`revision=main`），看 run 结束，再读 STG 实际跑的提交（`Sources.Deployed`，`server/agentrt_sources.go:87-99`），确认落地的提交是它的祖先，才记 `landing{phase: stg, run, deployed}`；最后放窗口。三个前提和 §1.7 一一对应。
- 发失败：放窗口、记 note、开一个运行时问题（issue）；main 不回退（往前修）；下一次落地再发。
- 接 D2：落地和发 STG 只通过两个函数碰窗口——`blocks(repo)`（今天：任何窗口开着都挡，和 `push-main.sh` 一样；D2 后：只看「从这个仓库构建的应用」的窗口）和 `hold(app)`（今天：那一个 ConfigMap；D2 后：应用自己的窗口）。4.3 换实现，这边不动。
- infra：规则允许的路径不进任何运行时（§2.8），没有 STG 可发。
- PROD 不变：照「STG 同一提交、CI 绿、没有未结发布单」建审批单，Owner 在 Console 批。由运行时自己建这张单可以放 S7 或并进 4.3。

### 2.7 尝试分支、落地分支的去留

- `land/<env>/<任务>/<k>`：落地或退回后由落地循环立刻删（它只是让 CI 起来的把手，记录在运行时和 PipelineRun 里）；`prune.go` 的规则加一条兜底：没有在途落地、超过 `PruneAfter` 的 `land/` 分支也删。今天的正则不认 `land/`（`prune.go:58`），不加就会一直留着。
- `agent/<任务>/a<n>`：规则不变（`landed` 起 24 小时）；被退回的原任务，收下的那个尝试分支留到它的落地任务落地之后再起算。
- 工作目录（Pod 里的克隆）每次用完即删；和 4.6 的生命周期盘点对一下口径。

### 2.8 新规则 `landing:<租户>` 的形状

```yaml
rule_id: landing:dev
rule_version: 1
direction: initial            # 第 1 版要 Owner 签
effective_at: 2026-10-2xT00:00:00Z
expires_at: 2027-01-22T00:00:00Z   # 建议 90 天，过期即停合
tenant: dev
repos:
  - repo: bifrost-platform
    allow: ["**"]
    deny: ["api/internal/agentrt/migrations/**", "api/go.mod", "api/go.sum",
           "console/package.json", "console/package-lock.json", "mcp/*/package*.json"]
    core: true                # api/internal/agentrt、agentd 的改动是否也自动合
    stg_release: bifrost-deliver-platform   # 或 none
  # infra 在 S6 用第 2 版（放宽、要签）加进来，例如：
  # - repo: bifrost-trade-infra
  #   allow: ["scripts/agentrt/**", "scripts/benchmark/**"]
  #   deny: ["scripts/agentrt/rule.sh"]
  #   stg_release: none
max_files: 30
max_changed_lines: 1500
max_landings_per_day: 30
```

- **代码里的底线，规则改不动**：`k8s/**`、`agent-config/**`、`scripts/release/**`、`scripts/gitea/**`、`.env*`，以及 `k8s/cicd/tekton` 里任何 Task 会执行的 infra 路径（由一条测试从 YAML 里抽出来，抽不到就失败）。理由：前三类是 Argo 同步的清单、治理与守卫、发布闸门；CI 的 code-health 用 infra main 的脚本和基线（§1.6），自动合它们等于自己放宽闸门。
- 迁移和依赖放进 platform 的 `deny`：新表、新列、新外部依赖是架构级决策（工作区 `CLAUDE.md` §5），而 STG 发布会自动跑迁移（§1.7）。
- 收紧的判断（接 `rules/tighten.go`）：仓库只减、`allow` 只删条目、`deny` 只增、上限只降、`core` 只从 true 到 false、`stg_release` 只到 none、到期只提前；别的都算放宽，要签。**停合的开关就是收紧**：去掉一个仓库不用签名，下一轮即生效。
- 不动 `standing-envelope` 的 `max_action`：任务本身仍然只推分支，合进 main 是控制器在收下之后、按另一条签过的规则做的事。

### 2.9 事件、审计、Owner 在 Console 上看到什么

- 记录：都是 mission 流上的 `note`，新键 `landing{phase, …}`，phase 取 `replayed / ci / waiting / landed / returned / declined / owner / stg`，`waiting` 带等什么（窗口持有者、main 红、CI 没起）。要改 `store/vocab.go` 的封闭词表（`:155-160`），不改库结构。`landed` 仍用今天的键，删分支和 `RecordLandings` 都照旧读它。
- Work 页每件 implement 任务多一行落地状态：排队 / 在 main@… 上重放 / CI `ci-platform-…` 在跑 / 等窗口（谁）/ 已进 main `…` / STG 已跑到 `…` / 退回（原因）→ 落地任务 `t_…`。For you 只在两种时候出现：预检不过的决定卡、退回两次后的卡住卡。
- Commit Lineage：落地提交带 `Agentrt-Task`、`Change-Id`、`Landed-By: agentrt-prod`，推送者是落地身份。第 4 轮的做完标准「进 main 的代码提交里由运行时自己合的过半」就数这个尾注；4.1 的验收「统筹线程零写入」数这个 mission 期间 actor 为 `thread:…` 的事件和 `bifrost-mbp` 往这两个仓库 main 的推送，都应为 0。

### 2.10 与 `RecordLandings`、`merge_accepted.py` 的关系

- `RecordLandings` 不改：落地循环自己写 `landed`，它查询时跳过已有 `landed` 的（`prune.go:383`），只给人手合的那些补记，并继续当兜底（例如推成功后 Pod 重启、note 没写上，下一轮它从 main 的 cherry-pick 行认出来）。
- `merge_accepted.py`：`list` 变成审计——规则覆盖的仓库里收下超过 2 小时还没落地也没退回的，就是落地循环的毛病；`apply` 留给规则之外的活（Owner 在决定卡上选了「不合」以外、又要手工合的少数情形）。

### 2.11 失败模式

| 情形 | 结果 | 谁处理 |
|---|---|---|
| 重放冲突 | 退回：落地任务带冲突文件 | 执行者 |
| 重放干净但 patch-id 变了 | 同上，原因写「重放改了评审过的差异」 | 执行者 |
| CI 红、main 绿 | 重跑一次，还红就退回，带 run 和最后 40 行 | 执行者 |
| main 自己红 | 不退回，等；记 `waiting{main_red}` | 推红 main 的人 |
| CI 没起（钩子丢了） | 15 分钟后直接建 run；45 分钟记 note 接着等 | 落地循环 |
| main 在 CI 期间动了 / 推被拒 | 回到重放；一小时上限 6 次（§2.3） | 落地循环 |
| 窗口被别人持着 | 等，30 分钟记 note，不清别人的窗口 | 持窗口的人 |
| Gitea 连不上 | 退避重试；main 只有最后一步一次快进，不会半截 | 落地循环 |
| workers 在推之后、记之前重启 | 下一轮按 note 续：main 已含这个提交就补 `landed`；`RecordLandings` 兜底 | 落地循环 |
| 规则过期 / 被收紧、mission 被停 | 第 6 步拦下，不推；已推的 `land/` 删掉 | — |
| 改动碰禁止路径、超上限 | 决定卡 | Owner |
| 退回两次还不过 | 卡住卡 | Owner / 统筹 |
| 已落地又被人 `revert` | 不再自动重合（有 `landed`）；删分支照今天的规则留着 | 人 |
| 规则生效前收下的 | 永不自动合，`list` 照报 | 统筹 |
| 落地令牌泄露 | 只能快进两个仓库的 main；推送者可查；Owner 换令牌 | Owner |
| 落地改了落地循环自己 | 进 main 不生效；随 STG 发布先在 STG 生效（那边只演练、不推 main），PROD 要发布单 | — |
| STG 发布失败 | 放窗口、开问题；main 不退；下次落地再发 | 落地循环 / 统筹 |

---

## 3. 切片

| 片 | 做什么 | 验收 | 只有它能拦住的用例 | 要 Owner |
|---|---|---|---|---|
| S1 规则与入队（不写 git） | `landing:<租户>` 的解析、收紧判断、底线路径；入队与预检；Console 显示「会合 / 规则外」 | store 与 rules 的测试；STG 上一件演练显示正确的入队结果 | ① 规则生效前收下的不入队；② 改了 `migrations/**` 的进决定卡；③ 规则加一个仓库被判为放宽；④ `no_merge` 的 mission 不入队；⑤ Tekton 执行的 infra 路径进底线（YAML 里新加一处，测试先红） | 无（随下一张发布单） |
| S2 STG 演练（推 `land/stg/**`，不推 main） | 镜像加 git；STG 的落地身份；第 3–5 步与 §2.7 的分支删除；STG 上把第 7 步换成「记一条 would_land」 | STG 上一件确定性任务：重放、CI 绿、记 would_land、分支删掉 | ① 三方合并改了评审过的差异 → 退回而不是 would_land；② CI 期间 main 动了 → 重放；③ 别人改了 `land/` 分支的头 → 不认；④ main 红 → 等而不退回 | 建 Gitea 用户 `agentrt-lander-stg`（两个仓库写权限，**不进** main 名单）、令牌做成 STG 的 Secret；刷新 Dockerfile 的 ConfigMap |
| S3 退回 | 落地任务；`close.go` 等落地；最多退回两次；TD-387 | STG 上制造一次冲突，落地任务被派出、收下、再落地（演练） | ① 冲突 → 新任务的 base 是 main 头且说明书带原因；② 收下没落地的 mission 不关；③ 第三次失败出卡住卡；④ CI 红一次、重跑绿 → 照常落地 | 无 |
| S4 PROD 真合 platform | 第 6–8 步打开；`Landed-By`；`protect-repo.sh` 基线支持按仓库的额外用户 | PROD 上第一件真落地：main 上的提交带尾注、推送者是落地身份、有 `landed`、分支已删 | ① 窗口开着 → 不推；② CI 后规则过期 → 不推；③ 落地令牌推 infra main、建标签被拒（照 `check-step1.sh` 的探针）；④ 非快进被拒后重放 | **签 `landing:dev` 第 1 版**；建 `agentrt-lander`、加进 platform main 的推送名单、令牌做成 PROD 的 Secret；**批发布单** |
| S5 自动发 STG | §2.6 全部 | **4.1 的 ★**：Owner 在 Console 提一句小目标，到进 main、上 STG，统筹线程零写入（§2.9 的两个数） | ① 窗口被别人持着 → 等、不清；② STG 实际跑的提交不含落地提交 → 不报「已上 STG」；③ main 头 CI 不绿 → 不发 | 批发布单（`stg_release` 已在 S4 的规则里签） |
| S6 infra | `bifrost-ci-infra` 流水线（push-main 的 infra 快测 + 运行时的 infra 检查）；规则第 2 版加 infra | 一件 infra 任务（`scripts/agentrt/` 下）自动落地 | ① 碰 `k8s/**` 或 `agent-config/**` 的永不自动合，即使规则写了允许；② 改 `scripts/agentrt/rule.sh` 的进决定卡 | 应用流水线；**签第 2 版**；把落地身份加进 infra main 的推送名单 |
| S7（可并进 4.3） | `push-main.sh` 认 `Agentrt-Task` 为血缘；运行时自建 PROD 审批单；「运行时自己合的占比」脚本 | 占比脚本对近 7 天跑出数 | 人手合运行时的提交不再需要 `--no-lineage` | 无 |

粗估：S1–S5 约 3–4 个工作日的实现加复核，Owner 约 1 小时、分三次（S2、S4、S6 前）。把握低：取决于复核轮数和 S4 发布单什么时候批。S1 与 S3 可以并行。

---

## 4. 架构级选择（各列选项和推荐，等 Owner 定）

- **X1 谁执行合入**：A 控制器（推荐）/ B 06 上的 agentd / C Tekton。见 §2.1。
- **X2 怎么退回**：
  - R3 同一 mission 里开落地任务（推荐）：不改状态机、不动库，复用派活、检查、评审、预算、卡住卡；代价是 Console 上多一行任务、mission 关闭条件多一条。
  - R2 在 `verifying` 和 `accepted` 之间加 `landing` 状态，退回走现成的 `rework`：语义最直（收下 = 进了 main），但要改 `task.state` 的 CHECK（PROD DDL），所有按状态列举的地方都要改（例如 `accept.go:439`、`blockedclose.go:70`）。
- **X3 落地状态记在哪**：mission 流上的 `note`（推荐，不动库）/ 新表 `agentrt.landing`（查询方便，新表是架构级、要 PROD DDL）。
- **X4 STG 怎么演练**：STG 运行时只推 `land/stg/**`、不推 main（推荐）/ 建一个受同样保护的探针仓库让 STG 真推（`store/repos.go` 写死仓库，要等 4.2 把接入挪进运行时记录）。
- **X5 infra 的「CI」**：新建 `bifrost-ci-infra`（推荐，人手推 infra 也受益，补上 RATCHETS 里多处「infra 没有 CI」）/ 在 06 上对重放提交跑一次运行时的 infra 检查（`repos.go:154-170` 的清单不含 `scripts/release`，比 `push-main.sh` 弱）。

---

## 5. 待 Owner 定的点

1. X1–X5 五个选择（推荐 A、R3、note、只推 `land/stg/**`、新建 ci-infra）。怎么回：「4.1 切法照推荐」，或逐条写字母。
2. 规则内容（§2.8）：`core` 是否自动合（推荐是：PROD 仍要发布单，STG 先吃到）；platform 的 `deny` 清单；三个上限；到期（推荐 90 天）；`stg_release` 开不开（推荐开）。在 S4 签名时定。
3. D2 之前抢 main 不持窗口、只限次重放（§2.3）——推荐照此；D2 后改持应用窗口。
4. PROD 上规则生效前收下、没进 main 的 10 件（M-1～M-15）：推荐不动，落地循环不碰它们；要清掉的话给 M-13、M-15 补 `no_merge`，要写 PROD 库，由 Owner 决定。
5. 要 Owner 动手的（到那一片时带具体步骤）：S2 建 `agentrt-lander-stg` 和 Secret；S4 签第 1 版规则、建 `agentrt-lander`、改 platform main 名单、Secret、批发布单；S5 批发布单；S6 应用 ci-infra、签第 2 版、改 infra main 名单。

## 6. 没核实的

- Gitea 1.21.11 有没有 `fast-forward-only` 合并方式、PR「按 rebase 更新」会不会保留提交号：没读源码（印象里前者 1.22 才有）。推荐的 A 不依赖它们。
- platform-workers 里的 delivery 服务能不能直接写窗口、起 PipelineRun：读到 workers 用它读 CI（`agentrt_wire.go:425-427`），写的那条路没读。
- `Sources.Deployed("stg")` 对 platform 报的是哪一个提交（`agentrtDeployLane` 的定义没读）。
- CI 的 Pod 在 cicd 里用的 SA 能不能读 Secret：没查，所以 C 的风险写成「没查」。
- Gitea 的推送记录里能不能按用户查推送者：没实测。
- 收下的尝试提交在 `agent/**` 上自己的 CI 是不是都绿：没统计。
