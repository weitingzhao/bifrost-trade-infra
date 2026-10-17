# 切法：Gitea 做主仓库，GitHub 只收 main 和标签，Agent 分支进同一仓库的 `agent/**`

**待你过目**，2026-10-17 上午只读调研写成（统筹线程 `local_accccb4e…` 交给一个子任务写、统筹方审过并补了合并白名单与 9.12），**还没有独立复核**；什么都没改：没动任何仓库、集群、Gitea、GitHub。你过目、定了第 9 节之后，第 0 步的代码和第 5 节的脚本各过一轮独立复核再给你跑。
读的版本：infra `9398c21`（本机 main 与 origin/main 一致）；platform 按 `origin/main` = `f69e8c6` 读（本机 main 落后 24 个提交）；Gitea 行为按 `go-gitea/gitea` 的 `v1.21.11` 源码读，没在我们的实例上实测。
行号都是这两个提交里的行号。

**一段话**：今天 Gitea 的 `bifrost/*` 是 GitHub 的拉取镜像，所以 Agent 分支只能放另一个组织 `bifrost-agents`，每接一个仓库就要手工建一套。目标是把 11 个仓库在 Gitea 上转成普通仓库、人和 Agent 都往 Gitea 推，GitHub 只接收 main 和标签。分四步走：先把所有依赖「镜像」的地方改成两种状态都能用（这一步上线后什么都不变），再按仓库分三批转换，最后撤掉 `bifrost-agents`。每批开发布窗口、停 agentd，前后都有核对，可以回退。我约 3 天，你约 2 小时，分 5 次做。

---

## 1. 你定的和为什么

**10-17 10:0x 你说的**（`agent-config/WORK.md:486`）：

> 「每次加了新项目、建了新 Repo，都要在 Gitea 的 Agent 组织下建镜像，麻烦死」

**10-17 10:2x 你定 A**：把 10-08 定的「Gitea 做主」做掉，Agent 分支进同一仓库受保护的 `agent/*`，新项目＝从模板建一个 Gitea 仓库（同一行；B 是先做平台动作「接入一个仓库」，没选）。同一行写明「和 06 切换分开做；切法由你过目后再落地」。

**这一步和你已定方向的关系：终点，不是过渡**（教训 136，`work/multi-agent/LESSONS-from-practice.md:152`）：

- 10-08 方案甲：「Gitea 做主……公开仓库镜像到 GitHub……Argo 的源改成 Gitea，deliver 里的镜像同步步骤去掉。每个 Agent 一个 Gitea 用户，配分支保护（Agent 只能推分支）。GitHub 只做次要备份，CI/CD 尽量不用它」（`work/multi-agent/DESIGN-agent-runtime-2026-10-08.md:290`；ADR `agent-config/ADR-ops-architecture.md:320-326`）。
- 10-15 12:08 你回「时机甲」：Gate A 先用 `bifrost-agents` 过渡，「Gate A 一过做方案甲……GitHub 只同步 main、不同步 agent 分支；发布脚本改推 Gitea；之后 AGENTRT_GIT_ORG 改 bifrost、去掉推送地址」（`WORK.md:459`）。
- `bifrost-agents` 就是那次的过渡（`WORK.md:459`、`work/multi-agent/OWNER-NEXT-gate-a.md:51-66`）。

**不在这一刀里的方案甲条目**（设计 v5 已经说过第 2 轮不做，`work/multi-agent/DESIGN-agent-runtime-v5-2026-10-14.md:928`）：Gitea 从 01 搬到 05、热备 06、元数据进 CNPG、版本升级、`bifrost-private` 与 design 仓库、gitea-mq 合并队列。这些以后单独切。

---

## 2. 今天的样子

### 2.1 代码在哪，谁写

| 事实 | 出处 |
|---|---|
| 12 个 GitHub 仓库全部公开（含已归档的 socket） | `AGENT_FACTS.md:354` |
| 本机 11 个检出的 `origin` 都是 `git@github.com:weitingzhao/<repo>.git`（SSH，用你的钥匙）；200 来个 worktree 共用这些配置；另外 `~/agent-work` 下有 62 个独立克隆的 origin 也指向 GitHub | 2026-10-17 本机 `git remote -v` 与扫描 |
| Gitea `bifrost/*` 是 GitHub 的**拉取镜像**，由 `bootstrap-gitea-mirrors.sh` 建：`mirror: True`、`private: True`，11 个仓库 | `scripts/k3s/bootstrap-gitea-mirrors.sh:22`、`:127-152` |
| 「Gitea 镜像只由 deliver 流水线的 mirror-sync 写入，不手工 push」 | `AGENT_FACTS.md:358-359` |
| 镜像只读：推送被拒；同步时删掉 GitHub 没有的分支 | `WORK.md:459`（10-15 10:07 查的） |
| Gitea 自己每 8 小时拉一次 | `bifrost-platform/api/internal/lineage/mirrors.go:12-15` |
| GitHub 上的分支：platform 76 个（47 个 `w31/…`、28 个 `cursor/…`、main），infra 63 个（38 + 24 + main），其余各 1–6 个；标签：core 50 个，platform、platform-plugin 各 1 个 | 2026-10-17 `gh api` 只读 |
| 仓库里没有 GitHub Actions（11 个仓库都没有 `.github/workflows`） | 同上 |

### 2.2 谁让镜像同步

| 入口 | 做什么 | 出处 |
|---|---|---|
| Tekton Task `bifrost-gitea-mirror-sync` | 用 `gitea-bootstrap/gitea_admin_token` 对每个仓库 `POST …/mirror-sync`，**非 2xx 就退出 1**；给了 `expectSha` 就轮询 `git/commits/<sha>` 最多 120 秒 | `bifrost-trade-infra/k8s/cicd/tekton/task-gitea-mirror-sync.yaml:28-34`、`:45-57`、`:58-87` |
| 用它的流水线 | deliver-stg（7 个仓库）、deliver-prod（7 个）、deliver-platform / -platform-prod（platform、ui）、deliver-research、build-research-dagster、build-research-pine（research）、build-ib-gateway（platform-plugin）；插件仓库自己的 `k8s/cicd/pipeline-build.yaml:48` 也用 | `pipeline-deliver-stg.yaml:43-51`、`pipeline-deliver-prod.yaml:104-112`、`pipeline-deliver-platform.yaml:37-45`、`pipeline-deliver-platform-prod.yaml:69-77`、`pipeline-deliver-research.yaml:91-99`、`pipeline-build-research-dagster.yaml:57-65`、`pipeline-build-research-pine.yaml:42-50`、`pipeline-build-ib-gateway.yaml:53-61`；`bifrost-platform-plugin/k8s/cicd/pipeline-build.yaml:48` |
| 平台 `POST /api/v1/delivery/mirrors/sync` | 允许清单内的仓库逐个 `POST mirror-sync`（只认 200/201），再轮询提交最多 90 秒 | `bifrost-platform/api/internal/server/server.go:524`；`api/internal/delivery/mirrors.go:14`、`:52-95`、`:149-168`；允许清单 `k8s/overlays/platform-prod/config/actuation-policy.yaml:216-229` |
| 起 run 前的修订号预检 | 修订号不在镜像上就调同一个 `SyncMirrors` | `bifrost-platform/api/internal/delivery/ref_preflight.go:358-365` |
| `release.sh stg/prod` | 等 CI 之前调上面的平台接口（`BIFROST_RELEASE_MIRROR=0` 可跳过）；读本机 `origin/main` 作 CI 核对的 SHA | `bifrost-trade-infra/scripts/release/release.sh:29-31`、`:327-334`、`:353-377`、`:386-393`、`:813-819`、`:857-861` |
| 提交血缘刷新 | 每次扫描前，对 `mirror: true` 的仓库各 `POST mirror-sync`（每 2 分钟最多一次，最多等 10 秒）；**只碰镜像仓库** | `bifrost-platform/api/internal/lineage/gitea.go:74-94`；`lineage/mirrors.go:16-20`、`:58-70`；`lineage/service.go:95` |
| Console「Sync mirrors」按钮 | 起一次上面那个 Task | `bifrost-platform/api/internal/delivery/supply_chain.go:405-406`、`server.go:525` |

Gitea 1.21.11 对非镜像仓库的 `POST mirror-sync` 回 **400 "Repository is not a mirror"**（`routers/api/v1/repo/mirror.go` 的 `MirrorSync`）。所以只要有一个仓库转成普通仓库，上表里前四个入口都会失败——Trade 的 deliver 也会，因为它的清单里有 platform 和 ui。**这是先做第 0 步的原因。**

### 2.3 CI 怎么起

- EventListener `cicd/bifrost-ci` 收 Gitea 的 push 网页钩子，CEL 只放行 `body.ref == 'refs/heads/main'`，按仓库名分到 python / frontend / platform 三条 CI；PipelineRun 带标签 `bifrost.io/trigger: gitea-webhook`（`k8s/cicd/tekton/trigger-trade-ci.yaml:208-295`，过滤条件在 `:228`、`:247`、`:261`、`:275`、`:290`；标签 `:75`、`:126`、`:178`）。集群里在跑（`kubectl get eventlistener -n cicd`，Ready）。
- 钩子由 `install-ci-webhooks.sh` 建在 7 个仓库上（core、api、worker、frontend、ui、platform、research），payload 没有 secret；要管理员令牌和 port-forward，所以只有你能跑（`scripts/k3s/install-ci-webhooks.sh:18-24`、`:28-38`、`:49`）。EventListener 也不验签（`trigger-trade-ci.yaml:218-235` 只有 cel 拦截器）——这是现状，不是这一刀引入的。
- 今天钩子是**镜像同步**触发的（`trigger-trade-ci.yaml:3`）。所以推了 GitHub 不一定马上有 CI：10-17 00:14 推平台主线后「CI 没起，因为 Gitea 镜像没同步（读一次提交血缘就会同步）」（`WORK.md:467`）。
- Gitea 投递到集群内地址靠 `GITEA__webhook__ALLOWED_HOST_LIST`（`k8s/cicd/gitea/deployment.yaml:72-77`）。

### 2.4 推 main

- `push-main.sh`：查发布窗口 → `git fetch origin main` 并要求快进 → 对 CI 有 code-health 的 6 个仓库在干净 worktree 上跑 `scan.sh` → 再查一次窗口 → `git push origin <commit>:refs/heads/main`。仓库名取自 `origin` 地址的末段，**哪个服务器都行**（`bifrost-trade-infra/scripts/release/push-main.sh:40-44`、`:46-56`、`:58-64`、`:66-79`、`:81-83`）。今天 `origin` 是 GitHub，所以推的是 GitHub。
- `preflight.js` 拦直接 `git push` 到 main、以及看不出目标分支的推送；**不看远端是谁**（`agent-config/scripts/agent-guard/preflight.js:283-293`、`:317-345`、`:348-359`，接线 `:626-627`）。推标签不拦。
- 打 core 的版本标签：`tag_core_release.sh --push` 推到 `origin`，注释写着「default: origin, i.e. GitHub」（`scripts/release/tag_core_release.sh:18`、`:115`）。
- 另有一条绕过 push-main 的路：本机 git-bridge 的 `POST /push` 把当前分支推到 `origin`（`bifrost-platform/agent/git-bridge/src/server.ts:419-458`）。谁在调它我没查。

### 2.5 agentd、平台读分支、血缘

| 事实 | 出处 |
|---|---|
| agentd 配置：`AGENTD_GIT_BASE`（克隆）、可选的 `AGENTD_GIT_PUSH_BASE`（「仓库是只读镜像时」分支推到哪），git 令牌经 `http.extraHeader` 环境变量给；推送地址必须和克隆地址同主机 | `bifrost-platform/api/cmd/agentd/main.go:13-16`、`:168-169`、`:187-193`、`:213-225` |
| 06 上两个服务：克隆 `…:30300/bifrost`、推 `…:30300/bifrost-agents` | `bifrost-trade-infra/scripts/agent-host/bifrost-agentd.service:28-29`、`bifrost-agentd-stg.service:29-30`；Mac 的安装脚本 `bifrost-platform/agent/deploy/install-agentd.sh:52`、`:93` |
| 克隆：全新 `git clone --no-checkout`（会带上所有分支），检出 base；检查类任务的 base 不在克隆里时，只从推送地址取被检查任务的 `agent/<任务>/*` | `api/internal/agentd/workspace.go:56-89`；`api/internal/agentd/run.go:86-96` |
| 没配推送地址时，推送和检查都用克隆地址（`PushRemote` 为空 → `Remote`；检查走普通 `Prepare`） | `run.go:47-50`、`:72-77`、`:87-89`；`main.go:91`、`:95` |
| 分支名只有 `refs/heads/agent/<任务号>/a<n>`；agentd 拒推别的 ref；同一尝试重推同一个提交 | `api/internal/agentrt/store/kernel.go:78-81`；`workspace.go:286-301`；`deliver.go:267-290` |
| 平台核对分支：读 `<AGENTRT_GIT_ORG>/<repo>.git/info/refs`（不用分支 API：10-15 刚推的分支 API 回 404）；分支不在而仓库在 → 409 拒收；看不到仓库 → 平台的错，agentd 重试 | `api/internal/server/agentrt_heads.go:22-36`、`:62-133` |
| 任务的 base 从交付组织 `bifrost` 的 main 读 | `agentrt_heads.go:38-55` |
| STG、PROD 都配 `AGENTRT_GIT_ORG=bifrost-agents`，注释写「bifrost/* are pull mirrors of GitHub and take no push」 | `k8s/overlays/platform-stg/platform-agentrt-env.patch.yaml:8-10`、`:23-24`；`platform-prod/platform-agentrt-env.patch.yaml:8-11`、`:24-25` |
| 血缘页：`AgentOrg` 来自同一个环境变量；**AgentOrg 等于交付组织时不扫 Agent 组织**；Agent 组织的分支按任务归属，落到 main 的同一 Change-Id 仍保留任务和分支（复核 210 A1）；交付仓库里的普通分支若 Change-Id 已在 main，直接跳过 | `server/server.go:272-276`；`lineage/service.go:168-218`（`:177`）；`collect` `:240-314`（`:298-306`） |
| 血缘列分支最多 10 页 × 50 = **500 个**，再多就截断、不报 | `lineage/gitea.go:128-151`（`:131`） |
| Console 血缘页的「Mirror fetched」列与说明文字按「镜像从 GitHub 拉」写 | `console/src/pages/CommitLineagePage.tsx:79-91`、`:626`、`:642-659` |

### 2.6 `bifrost-agents` 和账号

- 10-15 你建了组织 `bifrost-agents`、空私有仓库 `bifrost-platform`；`agentd-mbp-dev` 对它「写」、对镜像「读」；规则：`main` 禁推，标签 `*` 不许任何人建（`work/multi-agent/OWNER-NEXT-gate-a.md:55-59`）。14:5x 设好、统筹方在页面上核对过（`WORK.md:463`）。
- 06 的两个账号 `agentd-agent-06`、`agentd-agent-06-stg` 同样加成 `bifrost-agents/bifrost-platform` 的写协作者、`bifrost/bifrost-platform` 和 `bifrost/bifrost-ui` 的读协作者（`work/multi-agent/OWNER-STEPS-agent-host-06.md:110-113`）。
- 更早的 STG 操作单按「Gitea 做主」写过（直接在 `bifrost/bifrost-platform` 设 main 禁推），推不上去才改成 A（`work/multi-agent/OWNER-STEPS-gate-a-stg.md:66-80`）。
- 10-17 已建团队 `bifrost/agentd-read`（读全部仓库）；`bifrost-agents/agentd-write`（只 bifrost-platform、写）待建（`WORK.md:486`）。**本切法建议不再建后者。**
- 设计 v5 对 agentd 的 Gitea 身份的要求：「只能推 `agent/*`」要在它能写的每个仓库上验出来：推 main 被拒、推标签被拒、改分支保护被拒（`DESIGN-agent-runtime-v5-2026-10-14.md:918`）；它能推任何 `agent/*`、同主机的尝试之间不隔离，是第 2 轮接受的例外（`:891`、`:920`）。

### 2.7 Argo 读 GitHub

- 5 个 Application 全读 GitHub：`bifrost-platform-{stg,prod}`、`bifrost-{stg,prod}` 读 infra，`bifrost-research` 读 research（`k8s/cicd/applications/bifrost-platform-prod.yaml:13`、`bifrost-platform-stg.yaml:12`、`bifrost-prod.yaml:11`、`bifrost-stg.yaml:19`、`bifrost-research.yaml:18`）。集群里实读一致，五个都同步在 GitHub 的最新提交上（2026-10-17 只读 `kubectl get applications`）。
- platform 两个是 automated + prune + selfHeal，「推 infra main = 立即改 Ops STG/PROD 运行时」（`AGENT_FACTS.md:409`）；ADR 把「推 GitHub main 会触发 Argo 自动同步」记为已知接受风险、归 W-31（`ADR-ops-architecture.md:111`）。
- AppProject 只允许两个 GitHub 地址（`k8s/platform-rbac/42-appproject-bifrost.yaml:13-15`）；准入策略不许平台和 tekton-deliver 的身份改 Application 的 `repoURL`（`k8s/platform-rbac/40-admission.yaml:223-236`），所以改源只能你用管理员身份做。
- deliver 的 Argo 同步一律是 `sync revision: HEAD`（`k8s/cicd/tekton/task-deliver-stg.yaml:104`）。
- repo-server 的网络策略只管入站（实读 `policyTypes: [Ingress]`），读集群内 Gitea 不受挡。

### 2.8 Gitea 本身

- 1 个副本、`Recreate`、SQLite、local-path 卷钉在控制面节点 ubt-k3s-01，镜像 `gitea/gitea:1.21.11`（`k8s/cicd/gitea/deployment.yaml:29-31`、`:41-57`、`:60`、`:64-65`）；Pod 在 01 上（实读）。cicd 里没有限制 Gitea 出站的网络策略（实读，只有 `gitea-backup-deny-all` 管备份 Pod）。
- 每晚 03:10 UTC 加密备份到 NAS，先在副本上起临时 Gitea 逐仓 clone 比对、全对才写出，留最近 14 份；你 10-13 用私钥解过一次（`work/multi-agent/OWNER-STEPS-gitea-backup.md:1-40`；`WORK.md:808-809`；`k8s/cicd/gitea-backup/cronjob-backup.yaml:16`）。恢复步骤 `docs/runbooks/gitea-restore.md`。
- 告警只有「26 小时没有成功备份」（`k8s/monitoring/bifrost-alerting-rules.yaml:350-369`）；**没有 Gitea 不可用的告警**。

### 2.9 Gitea 1.21.11 能做什么、不能做什么（读的源码）

| 能力 | 1.21.11 的行为 | 源码位置（v1.21.11） |
|---|---|---|
| 推送镜像到 GitHub | 有，可以「推送时同步」。但它对 `refs/heads/*` 和 `refs/tags/*` 做 `git push --mirror --force`：**所有分支和标签都推，GitHub 上 Gitea 没有的分支和标签会被删掉**；**没有分支筛选**（上游 main 至今也没有；Forgejo 2025 年加了，Gitea 没有） | `services/mirror/mirror_push.go`（`remote add --mirror=push`、两条 refspec、`Mirror: true, Force: true`）；`modules/structs/mirror.go`（无 branch_filter） |
| 镜像转普通仓库 | 有，只在页面上（设置 → 危险操作 → 转换），要仓库属主；单向，转回去只能删库重建镜像 | `routers/web/repo/setting/setting.go` 的 `convert` |
| 按通配符保护分支 | 有，`gobwas/glob`、分隔符 `/`（`*` 不跨 `/`，`**` 跨）；**先匹配不带通配的规则，带通配的按创建时间，第一条命中就用**，没有优先级字段 | `models/git/protected_branch.go`（`glob.Compile(RuleName, '/')`）；`models/git/protected_branch_list.go`（`sort`、`GetFirstMatched`） |
| 只许某个团队推某类分支 | 有：规则开「白名单推送」，名单里放用户或团队；**管理员不例外**（你的管理员账号也要在名单里才能推） | `protected_branch.go` 的 `CanUserPush` |
| 经 PR 合进受保护分支 | **合并另走一道检查**：规则不开「合并白名单」时，对仓库有 Code 写权限的人就能合 PR（推送白名单管不到合并）。所以只开推送白名单时，agentd 开一个 `agent/…` → `main` 的 PR 再自己合，main 就进了它的提交。**每条规则都要同时开合并白名单**（统筹方审稿时补，10-17 按 v1.21.11 源码核过；实例上在第 1 步的探针核对里实测） | `routers/private/hook_pre_receive.go`：推送白名单不放行且是 PR 合并时，改问 `pull_service.IsUserAllowedToMerge`；`services/pull/merge.go` 的 `IsUserAllowedToMerge` 调 `IsUserMergeWhitelisted`；`models/git/protected_branch.go` 的 `IsUserMergeWhitelisted`：不开合并白名单时 `return permissionInRepo.CanWrite(unit.TypeCode)` |
| 受保护分支能不能删、能不能强推 | **都不能**，对谁都不行（推送删除回「protected from deletion」，强推回「protected from force push」） | `routers/private/hook_pre_receive.go` 的 `preReceiveBranch` |
| 不受保护的分支 | 有写权限就能推、强推、删 | 同上；非分支非标签的 ref 只查写权限（`default: AssertCanWriteCode`） |
| 标签保护 | 有，按 glob 或 `/正则/`，名单用户或团队，管理员不例外；**1.21 没有 API，只能在页面上设**（API 1.23 才有） | `models/git/protected_tag.go`；`routers/api/v1/api.go` 在 1.23.0 才出现 `tag_protections` |
| 分支保护 API | 有：`rule_name`、`enable_push`、`enable_push_whitelist`、`push_whitelist_usernames`、`push_whitelist_teams` 等 | `modules/structs/repo_branch.go` |
| 仓库模板 | 有，建库时可选复制：Git 内容、主题、Git 钩子、**网页钩子**、头像、标签、**受保护分支**；**不复制标签保护**；复制的分支规则创建时间全部一样（批量插入），所以两条重叠的通配规则谁先谁后不确定 | `modules/structs/repo.go` 的 `GenerateRepoOption`；`services/repository/template.go` 的 `GenerateProtectedBranch`（`CreatedUnix = 0` 后批量插入） |
| 团队覆盖全部仓库 | 有（新仓库自动包含）；你 10-17 已用它建了 `agentd-read` | `WORK.md:486` |
| 组织级的默认分支保护 | **没有**：规则只挂在单个仓库上；模板只在建库那一刻复制一次，之后改规则要逐仓改 | `ProtectedBranch` 只有 `RepoID`（同上文件） |
| 规则优先级、强推白名单、标签保护 API | 1.23 起才有（我只做了关键字核对） | v1.23.0 的 `protected_branch_list.go`、`protected_branch.go` |

---

## 3. 目标

| | 今天 | 切完 |
|---|---|---|
| 主仓库 | GitHub | Gitea `bifrost/*`（普通私有仓库） |
| 人和会话推到哪 | GitHub（SSH，你的钥匙） | Gitea（HTTP，新的非管理员账号 `bifrost-mbp` 的令牌，存钥匙串）；`push-main.sh` 不变，`origin` 换成 Gitea |
| GitHub | 主仓库 | 下游副本：只收 `main` 和标签，只快进，不强推、不删（见 9.1 为什么不用 Gitea 自带的推送镜像） |
| CI 怎么起 | 镜像同步后才有钩子 | 推到 Gitea main 就有钩子（同一个 EventListener、同一条过滤） |
| deliver 的 `mirror-sync` | 每个仓库都要 200 | 镜像仓库照旧同步；普通仓库跳过同步、只等提交在 |
| Agent 分支 | `bifrost-agents/<repo>` | 同一个 `bifrost/<repo>` 的 `agent/**`，受保护：只有 `agentd-write` 团队（和你）能建，谁都不能删、不能强推 |
| main | 镜像（不能推） | 受保护：只有 `maintainers` 团队（你、`bifrost-mbp`）能推、能合 PR（推送白名单加合并白名单）；Agent 推不了、合不了 |
| 标签 | — | 受保护 `*`：只有 `maintainers` 能建、改、删 |
| agentd | 推送地址 `bifrost-agents` | 不配推送地址，克隆和推送同一个 `bifrost` |
| 平台读分支、血缘 | `AGENTRT_GIT_ORG=bifrost-agents` | `AGENTRT_GIT_ORG=bifrost`；血缘把 `agent/` 分支当 Agent 分支归属 |
| Argo | 读 GitHub | 读集群内 Gitea（第 C 批） |
| 新仓库 | 镜像 + Agent 组织里的推送仓库 + 保护 + 每个 agentd 账号加协作者 | 从模板 `bifrost/repo-template` 建（带两条分支规则和 CI 钩子）+ 页面上加一条标签规则 + 名单 `gitea-primary.txt` 加一行（我做）；要公开的再在 GitHub 建空库（9.12 选 B 就不用再改令牌）。团队 `agentd-read`、`agentd-write`、`maintainers` 都是 All repositories，新仓库自动包含 |
| `bifrost-agents` | 在用 | 归档，之后删 |

---

## 4. 分阶段

**顺序的道理**：第 0 步先让「镜像」和「普通仓库」两种状态都能跑（上线后行为不变）；之后每批只转几个仓库，转完那一刻，CI、deliver、release.sh、agentd、平台读分支都已经认得新状态。每批开发布窗口、停 agentd，批内顺序是「核对两边一致 → 转换 → 设保护 → 换本机远端 → 开 agentd」。任何一批做到一半停下，已转的和没转的仓库可以并存。

### 第 0 步：两种状态都能跑的代码（我写；上线后什么都不变）

| 件 | 改什么 | 怎么核对 | 怎么回退 |
|---|---|---|---|
| 0a Tekton `bifrost-gitea-mirror-sync` | 每个仓库先 `GET /repos/bifrost/<repo>`，`"mirror":true` 才 `POST mirror-sync`，否则打一行「primary, nothing to fetch」；`expectSha` 轮询照旧 | 你在 Gitea 建一个普通的探针仓库 `bifrost/primary-probe`（第 1 步），用这个 Task 对「一个镜像 + 探针」各跑一次（带 expectSha）都过；之后 STG 发一次 platform 照常 | 重新 apply 旧文件 |
| 0b 平台 `SyncMirrors` | 同样：普通仓库不发同步、只等提交（release.sh、修订号预检都走它） | 单测加改坏版本；STG 发版里 `release.sh stg` 的 mirror 步照常 | 回滚平台版本 |
| 0c 平台血缘 | `AgentOrg == Org` 时，交付仓库里 `agent/` 开头的分支按 Agent 分支处理（保留任务、仓库、分支，按 Change-Id 认落地）；列分支的上限从 500 提高并在截断时报错，不再静默 | 单测：同组织的 Agent 分支归到任务；超过上限时 Coverage 有错误 | 回滚平台版本 |
| 0d Console 血缘页 | 普通仓库不显示「Mirror fetched」，说明文字改成「Gitea 是主仓库」 | Console 四项（lint、test、build、code-health） | 同上 |
| 0e `bifrost-github-sync`（新） | Tekton Task：仓库是镜像就什么都不做（GitHub 还是上游）；是普通仓库就把 `main` 和推来的标签**不加 force** 推到 GitHub。EventListener 加一个触发器（main 或 `refs/tags/` 的 push、11 个仓库），另加每 15 分钟一次的对账 CronJob（比两边的 main 和标签，Gitea 领先就补推，GitHub 领先或分叉就失败）；告警「GitHub 落后 Gitea 超过 30 分钟」与「Gitea 不可用」；维护者清单加两项。令牌从 Secret `cicd/github-sync` 经环境变量给 git，不进命令行和日志；TaskRun 用自己的标签，不带 `bifrost.io/trigger: gitea-webhook` | 只要 Secret 还没建，任务失败、告警指向「没令牌」；Secret 建好后对一个镜像仓库跑是空操作；再对一个真仓库的现有 main 用 `git push --dry-run` 验一次令牌（不改 GitHub）。探针仓库在 GitHub 上没有对应的库，测不了同步本身，第一次真同步在第 A 批 | 删触发器和 CronJob |
| 0f 换本机远端的脚本、比对两边引用的脚本、搬 Agent 分支的脚本、设保护的脚本（新，`scripts/gitea/`） | 见第 5 节 | 先过一轮独立复核再给你跑 | 不涉及 |
| 0g 一份名单 `agent-config/gitea-primary.txt` | 已转成主仓库的仓库名，每批加几行；`push-main.sh` 遇到名单里的仓库而 `origin` 还是 GitHub 就拒绝；`preflight.js` 拦向名单里仓库的 GitHub 地址或 `github` 远端推送（推送镜像只该由集群做） | `test.js` 加用例；`check-agent-config-parity.sh` | 清空名单 |

0a、0e 要你 apply 到 `cicd`（cicd 的写入是你的事，`CLAUDE.md` 发布条款）；0b–0d 随平台一版发 STG（我）、PROD（一张发布单，你在 Console 批）。

### 第 1 步：Gitea 和 GitHub 上的准备（你；不影响任何流程）

建账号、团队、探针仓库、模板仓库、GitHub 令牌、Secret（逐条见第 5 节）。镜像仓库不接受推送，所以这时给 `agentd-write` 团队写权限不会让 agentd 碰到任何东西。

**核对**（在探针仓库上做，不碰真仓库）：在 06 上以 `agentd-agent-06-stg` 的令牌跑一个核对脚本：推 main 被拒、推标签被拒、建 `agent/_probe/1` 成功、删它被拒、强推它被拒、经 API 改分支保护回 403、**经 API 开一个 `agent/_probe/1` → `main` 的 PR 并合并被拒**、经 API 建 release（会建标签）被拒；以 `bifrost-mbp` 推 main 和标签成功。之后删掉探针仓库（带受保护分支的仓库可以整个删）。
**回退**：删掉新账号、团队、Secret。

### 第 A 批：`bifrost-platform`、`bifrost-ui`，加上 agentd 的切换（约 40 分钟）

先做这两个，因为 Agent 只在这两个仓库上干活（目标只能选 bifrost-platform，Console 检查要克隆 ui，`WORK.md:467`）。Argo 不读它们。

1. 我：`release.sh hold --what bifrost-platform,bifrost-ui`；确认没有在跑的 deliver / CI。
2. 你：停 06 上两个 agentd（Mac Pro 的 `mbp-dev` 还在跑也停）。我在 Progress 上确认没有进行中的尝试、本地没有待交的结果。
3. 你跑比对脚本：两个仓库先同步一次镜像，GitHub 与 Gitea 的分支、标签逐条相同才往下走。
4. 你：两个仓库在页面上「转换为普通仓库」。
5. 你：设保护脚本加两条分支规则（`main`、`agent/**`）；页面上各加一条标签规则 `*`。
6. 你：搬 Agent 分支脚本把 `bifrost-agents/bifrost-platform` 的 `refs/heads/agent/*` 复制到 `bifrost/bifrost-platform`（只复制，不删原处），这样旧尝试的保全、检查类任务的 base 和血缘都还找得到。
7. 我：名单加这两个仓库；STG overlay 改 `AGENTRT_GIT_ORG=bifrost`（STG 清单我按 STG 规矩发）；PROD overlay 同样改，**等你回「推 PROD 接线」**（和 06 那次一样）。这一刻 infra 还是 GitHub 做主，Argo 照常同步。
8. 我改两个服务文件去掉 `AGENTD_GIT_PUSH_BASE`；你在 06 上装服务文件、启动 agentd（命令在操作单里）。STG 那个在 STG 平台换好后就开；PROD 那个等 PROD 平台换好再开——一边读 `bifrost`、另一边推 `bifrost-agents` 时交来的结果会被 409 永久拒收。
9. 我：两个本机检出换远端（`origin` → Gitea，加只读的 `github` 远端）；你先把 `bifrost-mbp` 的令牌存进钥匙串，并加两行全局 `insteadOf`，让 `~/agent-work` 那些独立克隆也改走 Gitea。
10. 核对：STG 派一件确定性的小任务，分支落在 `bifrost/bifrost-platform` 的 `agent/<任务>/a1`、平台记了 persisted、血缘页把它归到任务；我经 `push-main.sh` 推下一个平台提交，CI 由钩子直接起、`bifrost-github-sync` 把它推到 GitHub（`gh api` 读 GitHub main 等于这个提交）；起一次 `bifrost-deliver-platform`（STG），mirror 步对这两个仓库打「primary」行、克隆到的是刚推的提交。
11. 放窗口。

**回退**（按做到哪）：Gitea main 还没有新提交时——你删掉这两个仓库、对它们重跑 `bootstrap-gitea-mirrors.sh` 和 `install-ci-webhooks.sh`，`AGENTRT_GIT_ORG` 和服务文件改回 `bifrost-agents`（那边的分支一直没删），本机远端改回 GitHub、名单删两行。有了新提交以后——先确认它们已经同步到 GitHub（快进推送保证 GitHub 不会领先），再照上面做。要点：`bifrost-agents` 在第 D 批之前一直原样留着。

### 第 B 批：Trade 四个仓库和三个插件（core、api、worker、frontend、platform-plugin、-market-data、-flex-query；约 30 分钟）

同 A 的 1–5、9–11，不改 agentd 和平台的配置。仍然先停 agentd：`agentd-write` 团队覆盖全部仓库，新转的仓库在转换后、设好保护之前有一两分钟没有规则，保护设好再开。
**核对**：`release.sh stg` 发一次 Trade（deliver-stg 克隆 7 个仓库，这时 infra 还是镜像、其余已是普通仓库，正好验混合状态）；标签同步第一次真跑要等 core 下一次到 PROD 打标签（`tag_core_release.sh --push`，标签只打到达 PROD 的提交）；钩子漏了的话，对账任务 15 分钟内补上。
**回退**：同 A。

### 第 C 批：infra、research，加上 Argo 改读 Gitea（约 40 分钟；建议周末、休市）

1. 窗口、停 agentd、比对、转换、保护，同上。
2. 你按顺序 apply：AppProject 先**加上**两个 Gitea 地址（GitHub 的先留着）→ Argo 读 Gitea 用的凭证 Secret（只读账号）→ 5 个 Application 的 `repoURL` 改成 `http://gitea.cicd.svc.cluster.local:3000/bifrost/<repo>.git`。改之前我先确认 Gitea 与 GitHub 的 infra、research main 是同一个提交，这样改源时 Argo 比对出来没有差异，不会动运行时。
3. 我：名单加两行、两个检出换远端；研究发布的 skill（两侧）改成推 Gitea。
4. **核对**：`kubectl get applications -n cicd` 五个的源都是 Gitea、同步在 Gitea main；经 `push-main.sh` 推一个 infra 提交（STG 范围内的小改动），`bifrost-platform-stg` 自动同步到它；research 按 skill 发一次。
5. 一周后：AppProject 去掉 GitHub 地址。

**回退**：Argo 改源的回退是 apply 上一个提交里的 5 个 Application（GitHub 地址）——只要 `bifrost-github-sync` 在正常同步，GitHub 上就是同一个提交。仓库转换的回退同 A。

### 第 D 批：撤掉 `bifrost-agents`（第 C 批后一周）

- 平台 `AGENTRT_GIT_ORG` 已经等于交付组织，血缘不再扫它（`lineage/service.go:177`），平台也不再读它。
- 你：把三个 agentd 账号从 `bifrost-agents/bifrost-platform` 和 `bifrost/*` 的协作者里拿掉、移出 `agentd-read`（权限都由 `agentd-write` 给）；归档那个仓库；至少再过一次每晚备份后删除组织（删除不可逆，你来做）。
- 我：删掉 `bootstrap-gitea-mirrors.sh` 与 Makefile 里的镜像目标（或改成「建主仓库」），`AGENT_FACTS`、`RELEASE.md`、`DELIVER_STG.md` 写成新样子；`AGENTD_GIT_PUSH_BASE` 的代码要不要删见 9.8。

---

## 5. 你亲手做的

页面路径按 1.21 的英文界面写，可能和你看到的名字稍有不同。带脚本的几条，脚本还没写，写完先过一轮独立复核，再给你可以原样运行的命令（不留占位符）。令牌一律用 `read -rs` 读入，不上屏、不进对话。

### 第 1 步（约 30 分钟，一次做完）

1. **推送账号**：Site Administration → User Accounts → Create User Account，用户名 `bifrost-mbp`（不是管理员）。在无痕窗口用它登录 → Settings → Applications → Generate New Token，名字 `mbp-sessions`，权限只给 repository 的 Read and Write。令牌先放剪贴板，第 A 批第 9 步用。
2. **团队 `maintainers`**：组织 `bifrost` → Teams → New Team：Repository access 选 All repositories；Code 单元 Write，其它 Read 或 No Access；不给 Administrator。成员：你的账号、`bifrost-mbp`。
3. **团队 `agentd-write`**：同上，Code 单元 Write，其它 No Access；成员：`agentd-agent-06`、`agentd-agent-06-stg`（`agentd-mbp-dev` 若还要用也加）。不要再建 `bifrost-agents/agentd-write`。
4. **探针仓库**：组织 `bifrost` → New Repository，名字 `primary-probe`，私有，勾「Initialize」生成 main。Settings → Branches → Add New Rule：
   - 规则 `main`：Push 选 Enable Whitelist-restricted Push，团队 `maintainers`，用户：你；**再勾 Enable Merge Whitelist，同样只放 `maintainers` 和你**。保存。
   - 规则 `agent/**`：同样白名单推送，团队 `agentd-write`，用户：你；合并白名单只放 `maintainers` 和你。保存。
   - Settings → Tags → 新规则：Tag name `*`，Allowed：团队 `maintainers`、你。
   然后告诉我「探针好了」，我给你在 06 上跑的核对命令。
5. **模板仓库**（以后建新仓库用）：同第 4 条建 `repo-template`，设好同样两条分支规则；Settings → Webhooks 加一个 Gitea 钩子，地址 `http://el-bifrost-ci.cicd.svc.cluster.local:8080`、JSON、只要 Push；Settings 里勾「Template Repository」。
6. **GitHub 同步令牌**：github.com → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token：名字 `bifrost-github-sync`，过期一年，Resource owner `weitingzhao`，Repository access 选 Only select repositories，勾这 11 个：bifrost-trade-core、bifrost-trade-worker、bifrost-trade-api、bifrost-trade-frontend、bifrost-trade-infra、bifrost-ui、bifrost-platform、bifrost-research、bifrost-platform-plugin、bifrost-platform-plugin-market-data、bifrost-platform-plugin-flex-query；Repository permissions → Contents: Read and write（Metadata 自动只读）。生成后马上做第 7 条。
7. **放进集群**（你的终端；令牌用 `read -rs` 读入、不上屏，建成后只打印键名、应为 `token`）：原样命令在操作单 `OWNER-STEPS-gitea-primary.md` 里，复核后给，这里不写可运行的命令（教训 158）。
8. **apply 第 0 步的两件**（0a、0e）：等我说「可以 apply」再做，命令在操作单里（`kubectl apply --dry-run=server` 过了才真 apply）。

### 每一批（A 约 25 分钟、B 约 20 分钟、C 约 30 分钟）

1. 停 agentd：06 上 `systemctl stop` 两个服务（操作单给原样命令）。
2. 跑比对脚本（`scripts/gitea/compare-refs.sh <仓库…>`，用你的管理员令牌读 Gitea，GitHub 是公开读），全部「same」才往下。
3. 每个仓库：Settings → 页面底部 Danger Zone → Convert to Regular Repository → 输入仓库名确认。
4. 跑设保护脚本（`scripts/gitea/protect-repo.sh <仓库…>`：经 API 加 `main` 与 `agent/**` 两条规则，每条都带推送白名单和合并白名单，再读回逐项比对）；然后每个仓库在页面上 Settings → Tags 加 `*` 规则（1.21 没有 API）。
5. 只在 A：跑搬分支脚本（`scripts/gitea/copy-agent-branches.sh bifrost-platform`）。
6. 只在 A：钥匙串里存 `bifrost-mbp` 的令牌（`git credential approve`，令牌用 `read -rs` 读入；之后 git 自动用）。命令在操作单里。
7. 每批：加这一批仓库的全局 `insteadOf`（改你的 `~/.gitconfig`，是长期配置，所以由你跑；命令在操作单里，每个仓库两行：SSH 和 HTTPS 两种 GitHub 地址都改写到 Gitea）。
8. 只在 A：在 06 上装新服务文件、启动两个 agentd；只在 A：回「推 PROD 接线」。
9. 只在 C：apply AppProject → Argo 读 Gitea 的凭证 Secret（账号 `argocd-reader`，只读团队，第 C 批前建）→ 5 个 Application。
10. 开 agentd。

### 第 D 批（约 10 分钟）

拿掉旧协作者、归档 `bifrost-agents/bifrost-platform`；至少一次每晚备份之后删组织 `bifrost-agents`。

---

## 6. 改哪些文件

| 仓库 | 文件 | 改什么 |
|---|---|---|
| bifrost-platform | `api/internal/delivery/mirrors.go`（`:52-95`、`:116-168`）及测试 | 普通仓库不发同步、只等提交 |
| | `api/internal/delivery/ref_preflight.go:358-365` | 文案（「镜像没同步」对普通仓库不成立） |
| | `api/internal/lineage/service.go`（`scanRepo` `:134-166`、`scanAgents` `:177`、`collect` `:298-306`）及测试 | 同组织 `agent/` 分支按 Agent 分支归属 |
| | `api/internal/lineage/gitea.go:131` | 分支上限提高、截断报错 |
| | `api/internal/server/agentrt_heads.go:22-27`、`agentrt_wire.go:50-52` | 只改注释（行为不变：读哪个组织由环境变量定） |
| | `api/internal/agentd/run.go` 的测试 | 补一条：不配推送地址时，检查类任务的 base 在同仓库的 `agent/` 分支上能找到 |
| | `console/src/pages/CommitLineagePage.tsx:79-91`、`:626`、`:642-659` | 主仓库不显示镜像时间 |
| | （第 D 批后，见 9.8）`api/cmd/agentd/main.go:14-15`、`:213-225`，`agent/deploy/install-agentd.sh:19`、`:52`、`:93` | 可选：删掉推送地址 |
| bifrost-trade-infra | `k8s/cicd/tekton/task-gitea-mirror-sync.yaml` | 0a |
| | `k8s/cicd/tekton/task-github-sync.yaml`（新）、`trigger-trade-ci.yaml`（加触发器）、`k8s/cicd/github-sync/`（对账 CronJob、`secret.yaml.example`） | 0e |
| | `k8s/monitoring/bifrost-alerting-rules.yaml`、`k8s/monitoring/maintainer-reconcile/MAINTAINERS.yaml` | 两条告警、两项维护者 |
| | `scripts/k3s/install-ci-webhooks.sh:24` | 仓库清单扩到 11 个（GitHub 同步要所有仓库的钩子） |
| | `scripts/gitea/{compare-refs,protect-repo,copy-agent-branches,switch-local-remotes,onboard-repo}.sh`（新） | 第 5 节用的脚本；`onboard-repo.sh` 取代 `scripts/k3s/bootstrap-gitea-mirrors.sh` |
| | `agent-config/gitea-primary.txt`（新）、`scripts/release/push-main.sh:40-44`、`scripts/release/tag_core_release.sh:18` | 名单；GitHub 远端拒推；注释 |
| | `agent-config/scripts/agent-guard/preflight.js`、`test.js` | 拦向名单仓库的 GitHub 推送 |
| | `k8s/overlays/platform-stg/platform-agentrt-env.patch.yaml:8-10`、`:23-24`；`platform-prod/…:8-11`、`:24-25` | `AGENTRT_GIT_ORG=bifrost`（PROD 那份等你点头） |
| | `scripts/agent-host/bifrost-agentd.service:29`、`bifrost-agentd-stg.service:30` | 去掉 `AGENTD_GIT_PUSH_BASE` |
| | `k8s/cicd/applications/*.yaml`（5 个）、`k8s/platform-rbac/42-appproject-bifrost.yaml:13-15`、`k8s/cicd/argocd/repo-secret.yaml.example` | 第 C 批 |
| | `scripts/prune-merged-branches.sh:152` | 跳过 `agent/` 分支（受保护，删会失败） |
| | `scripts/k3s/run-deliver-{stg,prod,platform}.sh`（`SYNC_GITEA`）、`Makefile:346-348`、`:494-512` | 镜像相关的老入口改说明或删 |
| | 文档：`docs/RELEASE.md:196-215`、`docs/DELIVER_STG.md:9`、`:19`、`:70`、`:80`、`docs/runbooks/gitea-restore.md`（主仓库后的恢复与应急）；`AGENT_FACTS.md:266`、`:358-359`、`:409-411`（bump `parity-id`）；`agent-config/claude/skills/research-release/SKILL.md:23`、`:26`、`:45`、`:61`、`:103`、`:129`、`:133` 和 Cursor 侧同名 skill（parity）；ADR `:111`、`:320-326` 的状态；`WORK.md:486` | 写成新样子 |
| | `work/multi-agent/OWNER-STEPS-gitea-primary.md`（新） | 第 5 节的原样命令 |
| bifrost-platform-plugin | `k8s/cicd/pipeline-build.yaml:48` | 不用改（共用的 Task 已兼容） |
| 其余仓库 | — | 不改代码，只换本机远端 |

---

## 7. 风险

| 风险 | 怎么挡 | 剩下的 |
|---|---|---|
| **12 个仓库是公开的** | GitHub 只收 main 和标签，内容和今天公开的一样；Agent 分支和人的工作分支只在私有的 Gitea | 若改用 Gitea 自带的推送镜像，Agent 分支会自动公开（9.1） |
| **两边都有人推，历史分叉** | 每批开发布窗口、比对两边引用逐条相同才转；转完立刻换本机远端，并用 `insteadOf` 盖住 62 个独立克隆；`preflight.js` 和 `push-main.sh` 拒推名单仓库的 GitHub；同步只快进，GitHub 那边多出东西时同步失败、告警，不会被覆盖 | 别的机器上的克隆（Mac mini .50 / .52 等）我没盘点；GitHub 网页上改文件、在 GitHub 合 PR 都会造成分叉（规矩：不在 GitHub 上改） |
| **发布窗口** | 每批 `release.sh hold --what <这批仓库>`，确认没有在跑的 deliver；批与批之间窗口放开，发版照常 | 窗口被别的会话持有就等 |
| **Agent 碰 main 和标签** | `main` 白名单推送和合并白名单都只有 `maintainers`（只开推送白名单时，有 Code 写权限就能经 PR 合进 main）；标签 `*` 只有 `maintainers`；`agentd-write` 只有 Code 写、不是管理员，改不了保护；agentd 自己只推 `refs/heads/agent/`（`workspace.go:289`），平台只认 `agent/<任务>/a<n>`（`kernel.go:79-80`）；每批在探针仓库实测、在真仓库读回规则比对 | **偏离 v5 的一句话**：v5 写「只能推 `agent/*`」（`DESIGN v5:918`）。1.21 要做到这一点得加一条兜底的 `**` 规则，而受保护的分支谁都不能删、不能强推（人的 `w31/…`、`cursor/…` 也就没法变基后强推、没法清理）。所以建议只保护 `main` 和 `agent/**`：agentd 推不了 main、标签，改不了保护，删不了、改写不了任何 `agent/**`；但它**能推别的未受保护的分支名**（含人的 `w31/…`），和 v5 §7 第 7 条 ② 已接受的例外同类。要你定（9.3） |
| Agent 分支删不掉 | 受保护分支在 1.21 不能删 | 分支会越积越多：血缘列分支有上限（0c 提高并报截断），克隆变大。保留策略见 9.6 |
| 切换时还有尝试在半路 | 每批停 agentd、确认没有进行中的尝试；A 批把旧分支复制过来 | 平台读一个组织、agentd 推另一个的那几分钟若有结果交来，会被 409 永久拒收，所以平台和 agentd 必须在 agentd 停着时一起换 |
| **Gitea 变成单点** | 今天 CI、deliver、agentd 已经全靠它；新增的依赖是人的推送、标签和（C 批后）Argo。main 和标签几十秒内就在 GitHub 上有一份；人的分支在本机；每晚加密备份、验收过解密（`OWNER-STEPS-gitea-backup.md`）；0e 加「Gitea 不可用」告警 | Gitea 在 01 的本地盘上、SQLite、单副本；01 整机重启过。Agent 分支和人的分支只有每晚备份（最多丢一天，Agent 的工作另有平台里的补丁检查点）。Gitea 挂了就不推；真要推 GitHub，恢复后先把 GitHub 的提交快进进 Gitea，同步才会恢复（快进同步保证不会被覆盖）。搬 05、热备、进 CNPG 仍是方案甲的后续项 |
| GitHub 同步令牌 | 细粒度、只这 11 个仓库、只 Contents；Secret 不进仓库；日志不打令牌 | 能在 cicd 建 Pod 的身份能挂载它，和 `gitea-bootstrap` 的管理员令牌是同一类暴露；令牌一年到期，要提醒 |
| 钥匙串里的 Gitea 令牌 | 账号不是管理员，只有 Code 写 | 本机任何会话都能用它推（和今天用你的 GitHub 钥匙推一样）；main 仍只经 `push-main.sh`（`preflight.js` 拦） |
| git-bridge 的 `/push` | 切完它推到 Gitea | 它绕过 `push-main.sh`（现有问题）；它跑在 tmux 里，读钥匙串是否顺畅没验 |
| 云端 Agent 只走 GitHub 分支（`ADR:257`） | 同步不再把 GitHub 的分支拉回来 | 云端 Agent 的分支要人手工引进 Gitea（9.7） |
| Argo 改源 | 先确认两边同一提交；AppProject 先加后减；读不到新源时 Argo 报比对错误、不会按空清单删东西（这是我对 Argo 的理解，没实测） | 第 C 批建议周末、休市 |
| GitHub 的 PR 引用 | 拉取镜像会把 GitHub 的 `refs/pull/*` 一起带进 Gitea；转换后留着，无害 | 以后在 Gitea 开 PR 会覆盖同号的旧引用 |

---

## 8. 不变的

- **D10 交易执行冻结**：`daemon-scale-zero` / `daemon-observe-safe` 补丁、`ib:operator:cmd`、`place_order` 都不碰。
- **PROD 发布的批准**：照旧，Console 上批单、W-56 门槛、发布策略签名都不变；`release.sh` 的步骤和 CI 门禁不变，只是 mirror 那一步对普通仓库不再请求同步。
- **发布窗口**：规则不变，`push-main.sh` 照样两次查窗口、只快进、跑 code-health。
- `preflight.js` 的「推 main 只经 push-main.sh」不变（它本来就不看远端）。
- CI 的过滤条件、三条 CI 流水线、kaniko 构建、镜像仓库不变。
- 集群身份不变：Agent 仍是只读 kubeconfig；cicd 的写入、Argo 改源、PROD overlay 都由你做或你点头。
- 平台不认识 Trade：同步到 GitHub 放在 infra 的 Tekton，平台代码只是不再假设「交付组织是镜像」。

---

## 9. 待你定（每条带我的建议）

| # | 事 | 选项 | 建议 |
|---|---|---|---|
| 9.1 | GitHub 怎么同步 | **A** 自写的 `bifrost-github-sync`：只推 main 和标签、只快进；**B** Gitea 自带的推送镜像：零代码，但所有分支（含 `agent/**`）都推到公开的 GitHub，并且强推、删掉 GitHub 上 Gitea 没有的分支（云端 Agent 推的分支会被删） | **A**。它就是你 10-15 说的「GitHub 只同步 main、不同步 agent 分支」；B 在 1.21 做不到筛选，强推还会把分叉悄悄抹掉。代价约多半天 |
| 9.2 | 人的工作分支（`w31/…`、`cursor/…`）还要不要上 GitHub | 要 / 不要 | **不要**：Gitea、本机、每晚备份三份；GitHub 上现有的分支冻结在切换那一刻，以后再清 |
| 9.3 | Agent 能不能推别的分支名（见第 7 节第 4 行） | **A** 只保护 `main`、`agent/**`，接受 agentd 能推别的未受保护分支名；**B** 加兜底 `**` 规则，Agent 真正只能推 `agent/**`，代价是所有分支都删不掉、不能强推 | **A**，并把 v5 那句改成「推不了 main 和标签、改不了保护、删不了也改写不了 `agent/**`」，例外记进 v5 §7 第 7 条 ②。升到 Gitea 1.23（有规则优先级和强推白名单）或第 3 轮虚拟机时再收紧 |
| 9.4 | 本机会话用哪个 Gitea 账号推 | **A** 新的非管理员 `bifrost-mbp`；**B** 你的管理员账号 | **A**。管理员令牌放在钥匙串里，任何会话都能拿它改保护、删仓库 |
| 9.5 | Argo 什么时候改读 Gitea | **A** 第 C 批同一次；**B** 先留在 GitHub，`push-main.sh` 推完等 GitHub 追上 | **A**（方案甲本来就有这一条，`ADR:326`）；不改的话，同步一慢，deliver 的 `sync HEAD` 会同步到旧的 infra |
| 9.6 | Agent 分支留多久 | **A** 全留（1.21 删不掉），血缘上限提高；**B** 每季度由你临时去掉规则、删旧分支 | **A**，等升级 Gitea 时再定保留策略 |
| 9.7 | 云端 Agent 的 GitHub 分支 | **A** 用到时手工引进（`git fetch github <分支>` 再推到 Gitea）；**B** 同步任务反向拉 `claude/**` | **A**，现在很少用 |
| 9.8 | `AGENTD_GIT_PUSH_BASE` 的代码 | 第 D 批后删 / 留着 | 留一版后删（少一个配置项，也少一条「令牌发给另一个地址」的路） |
| 9.9 | 分几次做 | **A** 第 0 步后分 A、B、C 三批；**B** 一次全转 | **A**：每批都能单独核对和回退，Agent 的那批最先 |
| 9.10 | 什么时候开始 | 06 的 B 段收尾之后 | 按 `WORK.md:486`「和 06 切换分开做」：06 的剩余几件（STG 两件演练、PROD 一件 Console 小目标、停 Mac Pro 的 agentd）做完再开第 0 步；第 C 批放周末 |
| 9.11 | Gitea 的备份频率 | 每晚 / 每 6 小时 | 每晚：main 和标签已有 GitHub 一份；先加「Gitea 不可用」告警，频率以后看 |
| 9.12 | GitHub 同步令牌管哪些仓库（统筹方补） | **A** Only select repositories，列这 11 个：每加一个公开仓库，你要回 GitHub 改一次令牌；**B** All repositories（你账号下全部，含以后新建的），只 Contents 读写 | **B**，你不想每个新仓库都手工加一处（10-17 原话「麻烦死」）。代价：令牌也能写你账号下与 Bifrost 无关的仓库；它只在 `cicd/github-sync` Secret 里，同步任务只推名单 `gitea-primary.txt` 里的仓库。你账号下若有不想让它碰的私人仓库，选 A |

---

## 10. 工作量

| 块 | 我 | 你 |
|---|---|---|
| 第 0 步平台（0b–0d） | 半天写 + 两轮复核约半天；STG 我发 | 一张 PROD 发布单（Console 批） |
| 第 0 步 infra（0a、0e–0g、脚本、告警） | 一天 + 一轮复核 | apply 一次，约 10 分钟 |
| 第 1 步 | 写探针核对脚本、读回核对 | 约 30 分钟 |
| 第 A 批 | 约 1 小时（含核对） | 约 25 分钟 + 回一句「推 PROD 接线」 |
| 第 B 批 | 约 30 分钟 | 约 20 分钟 |
| 第 C 批 | 约 1 小时 | 约 30 分钟（周末） |
| 第 D 批与文档 | 半天 | 约 10 分钟 |
| **合计** | **约 3 天**（含复核和每批核对） | **约 2 小时，分 5 次** |

日历上约一周（第 C 批到第 D 批之间观察一周）。把握：中——Gitea 1.21 的几处关键行为（转换、保护、标签规则、钩子对标签推送的投递）我只读了源码，要先在探针仓库上实测。

---

## 附：没核实的

- Gitea 实例上的实际状态：`bifrost-agents/bifrost-platform` 里有多少 Agent 分支、各团队的成员、你的管理员账号名（没调 Gitea 管理接口，也没有 Agent 能用的 Gitea 凭证）。
- 1.21 的页面名称、镜像仓库能不能先设分支保护（所以计划在转换之后才设）、转换后仓库里的远端配置怎么清理——只读了源码。
- 推标签时 Gitea 1.21 发不发 push 钩子（对账任务兜底）。
- GitHub 上 11 个仓库有没有分支保护（当前 `gh` 令牌读回 403；规则集读回空）。
- 别的机器上有没有往 GitHub 推的克隆（Mac mini .50 / .52、维护者任务）。
- git-bridge `/push` 谁在调、在 tmux 里读钥匙串会不会弹窗失败。
- Argo 读不到新源时不按空清单删东西、repo-server 能连集群内 Gitea——按理解和网络策略推断，没实测。
- 1.23 的规则优先级、强推白名单、标签保护 API——只做了关键字核对。
- 每晚备份对转换后的仓库照常（它逐仓 clone 比对，预计没问题）。
- `kubectl create secret … --from-file=token=/dev/stdin` 在你的 kubectl 版本上能用（常见写法，没跑）。
- 平台代码按我本机最后一次 fetch 的 `origin/main`（`f69e8c6`）读，GitHub 上之后若有新提交没看到。
