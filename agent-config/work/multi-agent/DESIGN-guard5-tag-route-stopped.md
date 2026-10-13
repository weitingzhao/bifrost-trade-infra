# 设计：平台发正式环境不再构建，把测试环境验过的那一对镜像挂到 `:prod`（护栏 ⑤ 第 3 片 · 标签路线）

> **这份设计没有实现，留给第 3 轮参考。** Owner 2026-10-13 13:05 定：护栏 ⑤ 收口，标签这一片不做。两次独立复核（149、150）的结论都是「先改」：第 2 稿仍有两处会答错——① 上一次被取消或删除的发布残余的写入，可能落在结尾核对标签的两次读取之间，或在节点失联后才启动；② 核对之后 Pod 被删掉或替换，只重读 Deployment 的几个字段查不出来。复核另指出：等同步完成的判定认不出「自己这一次」；单个请求的超时管不住 registry 已经收到的写入。根子是这个 registry 没有写保护、也不能比较后再写，集群的读不是原子的；要「结束时一定」得先有写保护或把摘要写进清单（TD-331、TD-335）。教训见 `LESSONS-from-practice.md` 第 119 行。

> 第 1 稿 2026-10-13 11:45 CDT（Claude 的子代理，只读）。**第 2 稿 2026-10-13 12:09 CDT，统筹方按复核 149 改**；改了什么见 §0。
> 依据 infra main `f69baf1`（所引文件自 `a50c515` 起没变）；platform `origin/main` `bf39f96`。
> 简写：`T/` = `bifrost-trade-infra/k8s/cicd/tekton/`，`R/` = `bifrost-trade-infra/scripts/release/`，`I/` = `bifrost-trade-infra/`，`P/` = `bifrost-platform/api/internal/delivery/`。
> 范围：只动 infra 里的一条流水线、两个任务（一个新增）、一个 Role、发布脚本、测试和文档。路线是 Owner 2026-10-13 定的；它做不到的两样已记为 TD-330、TD-331（`I/agent-config/TECH_DEBT.md:2064-2090`）。

## 0. 第 2 稿改了什么（对应复核 149 的四条）

1. **149-①（会答错：同步没等完就核对；核对器每个 Deployment 只读一次）**：PROD 的 `gitops-sync` 改引一个新任务，发出同步请求后**等这次操作完成**才结束（§3、§4.5）；核对器在三组都通过之后**把三个 Deployment 再读一遍**，和第一次读到的不一样就整套重来（§4.5）。
2. **149-②（会答错：被取消或删除的 run 残余的写入；结束时没再核对标签）**：流水线最后加一个只读任务 `confirm`，重新 `HEAD` 两个 `:prod`，不等于这一对就失败（§3）；门禁加一条「刚失败结束、并且已经走到 `promote` 的 run，10 分钟内不放行下一次」（§4.3）；`promote` 自己有总时限（§4.1）；删除记录的情形写进恢复办法，并写明这一种只有文字（§4.3）。
3. **149-③（没说清：部分失败、重跑、「旧的一对」）**：§4.1 把三种留下的状态写全；§4.2 把那两个结果改叫「写入前的标签状态」，和「上一次成功发布的一对」分开。
4. **149-④（没说清：退回的前提）**：§4.2 写明只适用于含 `check-source` 身份接线的平台提交、界面库用哪个修订、重新构建不保证同一份。
5. 统筹方已定的一处写进正文：读阶段对每份清单里的 config 和每一层各 `HEAD` 一次（§4.4）。

第 2 稿新量到的两样（只读，2026-10-13 12:05）：`tekton-deliver` 在 `cicd` 对 Argo 应用已有 `get`、`patch`、`list`（`T/rbac-deliver-stg.yaml:15-17`），等同步完成不用加权限；线上两个应用（`bifrost-platform-stg`、`bifrost-platform-prod`）都开着自动同步（`prune`、`selfHeal`），操作完成后对象上没有 `.operation` 字段，`status.operationState` 里有 `phase`、`startedAt`、`finishedAt`，最近两次由流水线发起的操作各用了 1 秒。

## 1. 验收（三条）和发布后只读怎么查

| # | 要成立的 | 怎么查 |
|---|---|---|
| 1 | 正式环境的发布不构建 | 线上 `bifrost-deliver-platform-prod` 的任务名里没有 `clone-*`、`stage-*`、`build-*`，`taskRef` 里没有 kaniko 和 git-clone |
| 2 | 挂到 `:prod` 的是 `check-source` 认定的那一次 STG 发布核对过的一对 | 这次 PROD run 的 `check-source` 结果里的一对 = 那条 STG run 的 `rollout` 结果里的一对 = 这次 run 最后的 `confirm` 读到的两个 `:prod` |
| 3 | 发布结束时 PROD 的 Pod 跑的就是这一对 | 这次 PROD run 的 `rollout` 结果里的一对 = 上一行那一对 = PROD 三个 Deployment 的 Pod 的 `imageID` 里的摘要 |

## 2. 现状（事实）

- PROD 今天：`check-source` 之后克隆两个仓库、放两份 Dockerfile、kaniko 构建两次推 `:prod`，再重启、再同步（`T/pipeline-deliver-platform-prod.yaml:474-586`；六个构建相关的任务是 `:474-570`）。
- `check-source` 的结果只有 `commit`、`ui-commit`（同文件 `:97-99`）。它选创建时间最新、成功、与别的 run 不交叠的那条 STG run，并核对那条 run 的 `clone-platform` 子任务的提交（`R/platform_prod_gate.py:165-187,227-248`）。
- 第 2 片：STG 的 `rollout` 引 `bifrost-rollout-verify-platform`，两个摘要来自两次构建的结果（`T/pipeline-deliver-platform.yaml:144-158`）；整套核对通过之后才写 `api-digest`、`console-digest`、`verified-at`（`T/task-rollout-verify-platform.yaml:21-26,339-344`）。这个任务现在只接受 STG 的命名空间，共两处（`:45`、`:320-323`，后一处的源是 `R/platform_digest_verify.py:238-242`）。核对器对每个 Deployment 只读一次（`R/platform_digest_verify.py:107`），失败时在预算内整套重来（`:247-254`）。
- 同步任务只发请求不等完成（`T/task-deliver-platform.yaml:51-53`）；STG 和 PROD 的流水线引的是同一个任务。
- PROD 的 Role 只有 Deployment 的读和 patch，没有 Pod、ReplicaSet（`T/rbac-deliver-platform.yaml:37-40`；STG 的有，`:10-15`）。
- 平台起 run 时按任务名把 `tekton-deliver` 接给 `rollout`、`gitops-sync`，流水线里有 `check-source` 时也接给它；注释写明 Tekton 拒绝点名不存在的任务（`P/service.go:1516-1534`）。调用方只能给修订号（`P/params.go:15-22`）；平台总是绑定工作区 `build-context`（`P/service.go:606-610`）。
- PROD 的 Deployment 写的是 `192.168.10.73:30500/bifrost-platform-{api,console}:prod`，`Always`（`I/k8s/overlays/platform-prod/kustomization.yaml:57-63`、`images-pull-always.patch.yaml:10,21,36`）；api 是 Recreate（`platform-api-recreate.patch.yaml:13-14`），console 两副本（`replicas-ha.patch.yaml:27`）。
- 推镜像不带凭证（`T/task-kaniko-platform-api-stg.yaml:37-42`）。同一个 registry 里「取清单 → 原样放到另一个标签 → 比摘要」已有先例（`I/scripts/registry/dev-sync-backend-images.sh:22-40`）。
- run 记录留 7 天；步骤日志经集群接口只留 2 天（`T/pipelinerun-ttl.yaml:3-11`）。

## 3. 改成什么

次序：`freeze-check` → `preflight-stg` → `mirror-sync` → `check-source` → **`promote`** → `gitops-sync` → `rollout` → **`confirm`**。删掉六个任务和两个镜像参数（`T/pipeline-deliver-platform-prod.yaml:27-32`）；保留 `revision`、`uiRevision`、`giteaBase` 和工作区声明（平台照旧会发、会绑）；`check-source`、`gitops-sync`、`rollout` 三个任务名原样保留（平台按名字接身份）。

| 任务 | 做什么 | 身份 |
|---|---|---|
| `check-source` | 现有检查不变，加两样只读的：① 交叠和冷却判定（§4.3）；② 从它认定的那条 STG run 读 `rollout` 子任务的 `api-digest`、`console-digest`，核对办法和现在读 `clone-platform` 的提交相同（子任务恰好一个、名字和所属 run 对得上、已成功、每个结果恰好一个且整串是 `sha256:` 加 64 位十六进制），写成自己的两个新结果 | `tekton-deliver`（已有） |
| `promote`（新） | 只碰 registry，按 §4.1 把这一对挂到 `:prod` | 默认身份，不调集群接口 |
| `gitops-sync` | 任务名不变，改引**新任务** `bifrost-argocd-sync-wait-platform`：发出和今天一样的同步请求，然后等这次操作完成（§4.5）。挪到 `rollout` 之前（和 STG 的次序一样：`T/pipeline-deliver-platform.yaml:138-145`）。旧的同步任务和 STG 流水线不动 | `tekton-deliver`（已有，读应用的权限已有） |
| `rollout` | 改引第 2 片的 `bifrost-rollout-verify-platform`：重启三个 Deployment，再做同一套核对（多一步末尾重读，§4.5）。两个摘要取 `check-source` 的两个新结果，`requireSpecDigest=false`、`recordApplication=none` | `tekton-deliver`（已有） |
| `confirm`（新） | 只读：用 `promote` 的同一个脚本的检查模式，`HEAD` 两个 `:prod`，各自必须等于 `check-source` 的那一对；不等就失败，拒绝句点名哪个标签指向了别处。不写任何东西 | 默认身份，不调集群接口 |

为此放开两处：核对任务的命名空间从「只许 STG」改成「只许 STG 和 PROD 这两个名字」；PROD 的 Role 加两条**只读**，和 STG 的 Role 相同——核心组 `pods` 的 `get`、`list`，`apps` 组 `replicasets` 的 `get`（核对用的三种读法：`T/task-rollout-verify-platform.yaml:188,228,252`）。不加任何写权限。

这次发布的身份是这一对摘要，不是提交号：同一个提交再发一次 STG 会得到另一对，门禁认的是最新那条 STG run 的那一对；记录和比较一律用摘要（复核 148 第 1 条）。`uiRevision` 仍被解析、解析失败仍会拒绝，但不再决定产物；不动它。

保留下来、可能挡住一对本来能提升的镜像的条件（都是关着的一侧）：只认最新那条 STG run；同秒交叠一律拒绝；记录缺失或不完整；`uiRevision` 解析失败；平台照旧先做的构建前检查；§4.3 的 10 分钟冷却。

## 4. 必须写清的

### 4.1 先读后写；时限；一个成功一个失败

`promote` 的输入是两个摘要、一个标签名、一个模式（`write` 或 `check`）：流水线里标签写死 `prod`，脚本只认 `prod` 和试跑用的 `promote-trial`。registry 地址和两个镜像名写死在脚本里（kaniko 推的同一处：`T/task-kaniko-platform-api-stg.yaml:13`）。`write` 模式次序固定：

1. **读，两个镜像都读完才往下。** 按摘要 `GET` 清单：状态 200，响应头的摘要等于它，正文的 sha256 等于它；正文和 Content-Type 留在内存里。对正文里的 config 和每一层各 `HEAD` 一次（§4.4）。再 `HEAD` 现在的两个 `:prod`，得到写入前的标签状态（§4.2）：确定的 404 记 `none`，超时、别的状态码、畸形的响应一律拒绝。打印一行：目标一对、写入前的一对。
2. **写，先 api 后 console。** 把留着的正文按原 Content-Type `PUT` 到 `:prod`，随即 `HEAD` 核对它指向目标摘要；api 核对通过才写 console。
3. 每个请求超时 20 秒，不重试，从不 `DELETE`（推断：registry 只能按摘要删清单，删了会让指向同一摘要的 `:stg` 一起失效）。没有「已经相等就跳过」的分支：重跑就是把同样两次 `PUT` 再做一遍。
4. **总时限**：脚本从启动起计时，发每一次 `PUT` 之前已过 90 秒就拒绝、不再写；任务步骤的超时设 3 分钟。所以一个 `promote` 进程最晚的一次写入落在它启动后约 2 分钟之内（90 秒加一次请求的 20 秒）。§4.3 的冷却靠这个上限。

**失败时可能留下的三种状态**（这次 run 都还没有重启任何东西，但此后自己重启的 Pod 会拉到标签此刻指向的）：
- 两个都没变：读阶段失败，或 api 的 `PUT` 没有生效。
- api 新、console 旧：api 写成功之后任何一步失败。先写 api 是因为「新 api 配旧 console」比反过来更可能兼容（推断）。
- 两个都新而 run 失败：console 的 `PUT` 已经生效，但它的响应丢了或随后的 `HEAD` 失败。
api 的 `PUT` 报了错但其实写进去了，落在第一种或第二种。首次发布时某个 `:prod` 可能本来不存在。

**怎么发现**：run 停在 `promote`，拒绝句点名是哪个镜像的哪一步；日志里有目标一对和写入前的一对；统筹方只读 `HEAD` 两个 `:prod`，对照这两对就知道是三种里的哪一种。查不到就写「未知」，不猜。
**怎么收场**（不自动往回写）：registry 恢复后重跑同一次发布（先过 §4.3 的冷却），两次 `PUT` 重做，标签收敛到目标，再重启、核对。门禁若已不认（期间又起过 STG 发布），就再成功发一次 STG，再提升。失败报告里写明两个标签此刻各指向什么。

### 4.2 上一版怎么留 —— 只记下来，不设 `:prod-prev`

两样东西，名字分开：
- **写入前的标签状态**：§4.1 第 1 步在写任何标签之前读到的两个 `:prod`，打印进日志，并写成这次 run 的两个结果 `prior-api-digest`、`prior-console-digest`。它只说明这次写之前标签指向什么。一新一旧之后重跑，读到的就是那份混合状态；目标已经相等时读到的就是目标本身。**它不是「上一次成功发布的一对」，不能拿它挑退回的版本。**
- **上一次成功发布的一对**：统筹方每次**成功**发布后记进台账的一行——平台提交、界面库修订、STG run、PROD run、这一对（取自 `check-source` 的结果）、`confirm` 通过的时间。run 记录只留 7 天，所以以台账为准。失败的发布不记这一行，另记留下的状态。

发布单的回退说明写：**退回 = 把上一次成功发布的那个平台提交、配它当时的界面库修订，再成功发一次 STG，然后再提升**。这是今天文档里的第二条路（`I/docs/RELEASE.md:140`），只是 PROD 这一半不用再构建。限定和代价：
- 只适用于**含 `check-source` 身份接线的平台提交**（`I/docs/RELEASE.md:140` 的原有限定）。退回到更老的提交会把不含这段接线的接口放回正式环境，之后的 PROD 门禁按现在的流程走不通；那种情形不走这条路，先停下交 Owner。
- 退回的是**旧的两个修订重新构建出的一对**，不是原来那一对：Dockerfile、基础镜像、依赖在这期间都可能变了。
- 耗时是一次 STG 发布加一次提升（没量过）；旧提交的 CI 记录超过 7 天要先重跑 CI（门禁要整 SHA 的成功 CI：`R/platform_prod_gate.py:223-225`）；registry 或构建依赖不可用时，退回本身也可能失败。
- W-56 门槛里的「回滚不重建」（`I/docs/RELEASE.md:229`）这一片**没有做到**，台账上保持未结。

不设 `:prod-prev` 的理由：它每次发布多两次不能一起成败的写入，中途失败的状态更多；用得上它的只有一个绕过门禁、直接写 `:prod` 的退回动作，这一片不做。标签被改写不会删掉旧清单（推断：仓库的 registry 目录里只有一个部署文件，没有清理作业；计划里那一步是 `I/docs/REGISTRY_PERSISTENCE_PLAN.md:182-189`），所以台账里记下的摘要已经够以后任何做法取回旧的一对。

### 4.3 两次正式环境发布交叠，和失败之后的冷却

放在 `check-source` 里：它是写标签之前唯一带 `tekton-deliver` 的任务，这个身份在 `cicd` 能列 PipelineRun（`T/rbac-deliver-stg.yaml:38-49`）。`promote` 排在它后面，所以后到的那一次在写任何标签之前就停下。Trade 的先例同样拦在构建之前（`T/task-prepare-deliver-stg.yaml:15-22,57-60`）；复核 148 第 3 条指出的第一个洞就是拦得太晚。

用门禁现有的列法列出 `tekton.dev/pipeline=bifrost-deliver-platform-prod` 的全部 run（`R/platform_prod_gate.py:190-208`；列表读不到、不完整、形状不对都拒绝）。两条判据，都只用这一次列表里的内容：

- **交叠。** 在途 = `Succeeded` 条件不存在或是 `Unknown`（`T/pipeline-deliver-platform-prod.yaml:185-195`）。除自己之外，只要有一条在途、并且它的创建时间**不晚于**自己的，就拒绝并点名那一条。列表里找不到自己（试跑、手工建的 run）时，任何一条在途的都拒绝。同一秒创建的不按名字分先后，一律算「不晚于」（Trade 按名字分，`T/task-prepare-deliver-stg.yaml:49-52`，复核 148 指出同秒后到而名字更小的那条也会过）：同秒的两条要么都停、要么只过先检查的那一条；都停时重发一次。
- **冷却（新）。** 除自己之外，一条 run 的 `Succeeded` 是 `False`（失败、超时、被取消都是），它的 `status.childReferences` 里有 `promote` 这个任务的子项，并且它的 `completionTime` 距现在不到 10 分钟——拒绝，点名那一条和可以再发的时刻。`completionTime` 缺失或读不懂、`childReferences` 形状不对，也拒绝。没走到 `promote` 就失败的 run（被门禁拒绝的那些）不挡后面的。
  理由：run 的状态结束不等于它的 `promote` 进程已经停了（被取消时 Pod 还有一段收尾时间）。§4.1 的总时限保证这个进程最晚约 2 分钟内不再写；10 分钟留了余量。假设：`promote` 的进程是在它的 run 结束之前启动的（被取消的 run 会删掉还没启动的 Pod）；节点失联时这个假设可能不成立，那种情形由 `confirm` 和下一条兜着。

**卡住不结束的 run** 会一直挡着后面的。恢复办法：**取消它，不要删**（取消后记录还在，冷却那一条会自己管住后面的发布）。取消是对 `cicd` 里对象的写，由 Owner 做，命令由统筹方准备。
**记录被删掉了（`delete_pipeline_run`，或 7 天到期）**：门禁看不到它，冷却不起作用。这一种**只有文字**：删除之后统筹方用只读身份确认 `cicd` 里带 `tekton.dev/pipelineRun=<那条 run>` 标签的 Pod 一个都不剩，并且从删除起满 10 分钟，才建下一张发布单；不删走到过 `promote`、结束不到 10 分钟的 PROD run。
**兜底**：下一次发布的 `confirm` 在它结束前再读一次两个标签——残余的写入如果落在这之前，那次发布失败，不会带着错的标签成功。落在 `confirm` 之后的写入这一片防不住，和「提升之后标签被别人改写」是同一件事（TD-331，实现时把这个触发条件补进那一条）。

### 4.4 registry 里拉不到那一对

读阶段对每份清单做三样：按摘要 `GET` 清单并核对摘要；对清单里的 config 和**每一层**各 `HEAD` 一次，必须都是 200。任何一样不过（404、非 200、超时、摘要对不上、清单不是能读出 config 和层的单份镜像清单）：`promote` 拒绝，**一个标签都不写**，**不在正式环境重建**。办法只有一个：再成功发一次 STG（新的一对，在 STG 核对过），再提升。
查层的原因：api 是 Recreate，清单在而某一层丢了的话，重启时拉不下来，接口会停到修好为止。`HEAD` 只证明那一刻层在；之后被删掉仍会让重启失败——那是一次失败的发布，不是一次错的成功。

### 4.5 同步等完成、末尾重读、时间边界，和这一片证明不了的

- **等同步完成（新任务 `bifrost-argocd-sync-wait-platform`，脚本 `R/platform_sync_wait.py` 嵌进去）。** ① 读应用：对象上有 `.operation`（有操作在排队或在跑）就等它消失；记下此刻的 `status.operationState.startedAt` 和 `finishedAt`。② 发出和今天一字不差的同步请求（`T/task-deliver-platform.yaml:51-52`）。③ 每 2 秒读一次，直到：对象上没有 `.operation`，并且 `startedAt`、`finishedAt` 这一对和第 ① 步记下的不同，并且 `phase` 是 `Succeeded`——通过。`phase` 是 `Failed` 或 `Error`：立刻拒绝。总共等 120 秒，到时拒绝。读不到、形状不对：拒绝。
  依据：线上记录的形状是今天只读量到的（§0）。「请求被处理完之前 `.operation` 一直留在对象上」是按 Argo 的行为推断的，由试跑 d 量。时间戳只到秒：上一次操作和这一次落在同一秒时会等到超时而拒绝，是误拒，不会放行。
- **写完标签到重启之间**：标签已新，Pod 未必新。同步这一步结束时，这次请求的操作已经完成；它如果改了 Deployment，引出的滚动由 `rollout` 的重启和等待接着走完。
- **末尾重读（改核对器，STG 和 PROD 用的是同一份）。** 三个 Deployment 各自的核对都通过之后，把三个 Deployment 再各读一遍：UID、`generation`、revision 注解、`spec.replicas` 必须和第一次读到的相同，并且 `observedGeneration` 等于 `generation`；任何一个不同就算这一遍失败，在现有预算内整套重来（3 遍、55 秒），仍不过就拒绝。对 STG 只是多一道检查，不放宽任何东西。
- **成功说的是什么**：三个 Deployment 各自被读到的那一刻就绪、跑着这一对，并且从各自第一次被读到末尾重读之间没有被改过。`verified-at` 是全部读完的时刻；三个是先后读的，不是原子快照（`I/docs/RELEASE.md:146`）。
- **门禁那一刻**：认定的是最新、成功、不交叠的那条 STG run 和它核对过的一对。之后再起的 STG 发布不改变这次提升的内容（按摘要取，不读 `:stg`）；上线的是门禁那一刻认定的，不一定是 STG 此刻在跑的，和今天对提交的含义相同（`I/docs/RELEASE.md:93`）。
- **这一片不改 STG 的流水线**：STG 的同步仍然不等完成。它影响的是 STG 那次核对有多严（末尾重读已经收紧了一部分），不影响提升的是哪一对——那一对来自构建的结果。
- **证明不了的**：① `confirm` 之后 `:prod` 被改写（registry 没有鉴权，另有一个默认推 `:prod` 的开发脚本：`I/agent-config/TECH_DEBT.md:2083-2085`；§4.3 说的残余写入也在这里），以及 Pod 以后重启拉到什么——Deployment 写的仍是标签。这就是 TD-331。② 两个应用都开着自动同步：发布结束之后有人推 infra 主线，Argo 会自己再改正式环境的清单（TD-330）。③ 手工建一条不引线上流水线的 run、或直接改 TaskRun 记录的人，不在这一片防的范围内。

## 5. 改哪些文件

1. `R/platform_prod_gate.py`：交叠和冷却判定；读 STG `rollout` 的一对；两个新结果；新的拒绝句。
2. `T/pipeline-deliver-platform-prod.yaml`：删六个任务和两个镜像参数；加 `promote`、`confirm`；`gitops-sync` 改引新任务并挪到 `rollout` 之前；`rollout` 改引核对任务；`check-source` 多两个结果。
3. 新 `R/platform_promote.py`（`write`、`check` 两个模式），嵌进流水线的办法照 `R/embed_platform_prod_gate.py:24-39`；那个生成器现在拿 `- name: clone-platform` 当锚点（`:28,37`），要换。
4. 新 `R/platform_sync_wait.py` 和新任务文件 `T/task-argocd-sync-wait-platform.yaml`（嵌入办法同上）。`T/task-deliver-platform.yaml` 不动。
5. `R/platform_digest_verify.py` 和由它生成的 `T/task-rollout-verify-platform.yaml`（连同重启那一步里手写的同一个判断，`:45`）：多认 PROD 这一个命名空间；加末尾重读。
6. `T/rbac-deliver-platform.yaml`：PROD 的 Role 加两条只读。
7. 试跑生成器：`R/platform_digest_verify_trial.py` 加命名空间参数（现在写死 STG：`:19`）；新增 `promote` 的和等同步的试跑生成器；`R/platform_prod_gate_trial.py` 不用改（它直接取流水线里的 `check-source`：`:13`）。
8. 测试和夹具：`R/test_platform_prod_gate.py`、`R/test_platform_digest_verify.py`、`R/test_platform_digest.py:158-161`（PROD 不再引 kaniko）、`R/test_freeze_chain.py:179-194`、`R/freeze_effects.json:68-77`、`R/fixtures/freeze-unmodified/pipeline-deliver-platform-prod.yaml`、两个种错文件；新增 `promote` 和等同步的测试文件。
9. `I/docs/RELEASE.md`：`:93`、`:99`、`:140`、`:148`、`:361` 这几段按新流程改写；每句新拒绝各一行；恢复办法（取消不删、删除之后的两样确认）。
10. `I/agent-config/TECH_DEBT.md` 的 TD-331：补「被删记录的 run 残余写入落在 `confirm` 之后」这个触发条件。

不动的：平台仓库（它仍把这条流水线当构建流水线：`P/preflight.go:16`，后果是照旧先做构建前检查、任务照旧钉在 amd64，不影响三条验收）；`T/task-deliver-platform.yaml`；两个 kaniko 任务；STG 流水线。

## 6. 测什么

- **门禁**（假 kubectl，执行真正嵌进去的脚本）。读一对：正例；`rollout` 子任务缺失或有两个、未成功、属于别的 run、结果缺失、重复、畸形，各自拒绝；第 2 片之前的 STG run（`rollout` 没有结果）拒绝。交叠：更早的在途拒绝；更晚的在途通过；同秒的在途拒绝；已结束的不算；没有 `Succeeded` 条件的算在途；列表不完整拒绝；列表里没有自己而有在途的拒绝。冷却：失败结束 9 分钟、有 `promote` 子项的拒绝；满 10 分钟的通过；没有 `promote` 子项的失败 run 不挡；成功结束的不挡；被取消的同样按失败算；`completionTime` 缺失或畸形拒绝；`childReferences` 形状不对拒绝。调用数和列表种类的断言（`R/test_platform_prod_gate.py:542-548,564,572-575`）按实际改。
- **`promote`**（进程内起一个假 registry，执行真正嵌进去的脚本）。正常；任一清单 404；响应头摘要不符；正文 sha256 不符；第二个镜像读失败时**一次 `PUT` 都没有**；**第二份镜像缺任何一个 config 或层时一次 `PUT` 都没有**；api 的 `PUT` 失败；console 的 `PUT` 失败（状态一新一旧，拒绝句点名 console）；console 的 `PUT` 生效而随后的 `HEAD` 失败（两个都新，run 失败）；`PUT` 后 `HEAD` 不符；失败后重跑同一目标收敛；`:prod` 确定不存在时写入前的值是 `none`；查旧标签超时或回了别的状态码时拒绝且没有 `PUT`；标签名不在那两个之内拒绝；单个请求超时；已过 90 秒不再发 `PUT`；任何情形下没有 `DELETE`。`check` 模式：两个都对通过；任一个不对、不存在、读不到，拒绝；任何情形下没有 `PUT`。
- **等同步**（假 kubectl）。正常（请求之后 `.operation` 消失、时间戳变了、`Succeeded`）；`Failed`、`Error` 立刻拒绝；一直不完成到时拒绝；时间戳没变（读到的还是上一次的结果）不放行；开始时已有操作在跑，先等它；读不到或形状不对拒绝；发出的请求和旧任务的一字不差。
- **核对器的末尾重读**（交错）。读完 api 的 Deployment 之后把它的 `generation` 加一、别的照旧：这一遍失败并重来；重来之后稳定则通过；三遍都在变则拒绝。复核 149 给的那个情形（generation 8、observedGeneration 7、后来 Pod 的摘要也变了）必须拒绝。revision 注解变了、UID 变了、副本数变了，各一条。
- **结构**。PROD 流水线里没有克隆和 kaniko 的 `taskRef`，没有任务用工作区；`promote`、`rollout`、`confirm` 的两个摘要都来自 `check-source` 的结果；`promote` 和 `confirm` 的标签是字面值 `prod`，模式分别是 `write`、`check`；次序如 §3，`confirm` 是最后一个、在 `rollout` 之后，`gitops-sync` 在 `rollout` 之前并且引的是等完成的那个任务；三个任务名都在；这几个任务上没有 `when`、`onError`、`retries`；冻结检查压着 `promote`。
- **核对任务和 Role**。PROD 命名空间被接受，第三个名字仍拒绝（`R/test_platform_digest_verify.py:616-626,850-864` 现在断言 PROD 被拒，要改）；PROD 的 Role 恰好多这两条只读（`:726-744`）；两个文件的哈希钉（`:710-723`）在同一个提交里更新。
- **种错**，各自必须有用例失败：去掉正文 sha256 的比较；去掉层的检查；读完第一个镜像就写；先写 console；交叠判定把「不晚于」改成「早于」（同秒放行）；判定方向反过来；把没有 `Succeeded` 条件的当成已结束；去掉冷却；冷却不看 `promote` 子项（会误拒）和把 10 分钟改成 0；摘要改从 STG run 的构建任务读；`rollout` 的摘要不取自 `check-source`；等同步不比较时间戳；等同步把 `Failed` 当通过；去掉末尾重读；去掉 `confirm` 或把它排到 `rollout` 之前；`check` 模式里出现 `PUT`。
- **文档**。每句新拒绝在 `I/docs/RELEASE.md` 里各有一行（`R/test_platform_prod_gate.py:713-733` 守着门禁那一份）。

## 7. 谁应用、应用前量什么、试跑、撤回

集群里的流水线、任务、Role 只由 Owner 亲手应用，在 infra 主线的检出目录里。

**前提**（缺一条就不应用）：第 1、2 片已应用；此后至少成功发过一次 STG（否则那条 STG run 没有可读的一对，每次 PROD 发布都被拒——关着，发一次 STG 就恢复）；没有平台发布在途，没有未结的 PROD 发布单（`I/docs/RELEASE.md:103`）。
注意：第 5、6 项改的两个文件若在第 2 片应用之前就进了主线，会随第 2 片一起被应用（同一个文件；整批应用的脚本也是按文件：`I/scripts/k3s/apply-cicd-platform-pipeline.sh:44-45`）。多两条只读、任务多认一个命名空间而没有流水线用它，无害；但核对器的末尾重读会随之在 STG 生效——要事先告诉 Owner，并在第 2 片的试跑里一起量。

**应用前先量**（统筹方，只读身份）：
1. 线上的 PROD 流水线、核对任务、PROD 的 Role 各自等于哪个提交里的文件：决定应用会盖掉什么、撤回用哪一份。
2. 第 1 片的三个值相等：kaniko 记下的摘要、registry 对 `:stg` 回的摘要、STG 的 Pod 的 `imageID` 里的摘要。不等就停，回设计。
3. PROD 三个 Deployment 的 Pod 的真实形状：容器名、有没有 init 或临时容器、`imageID` 的格式、Pod→ReplicaSet→Deployment 的属主链和 revision 注解、副本数。和核对任务的假设（`T/task-rollout-verify-platform.yaml:101-105,269-279`）不一样，先改规则和测试。
4. 两个 `:prod` 现在的摘要，和 PROD 的 Pod 现在在跑的一对（试跑 c 要用）。
5. 除这条流水线之外，还有谁写这两个镜像的 `:prod`。

**试跑**（生成器只打印清单，由 Owner 创建；都不碰 `:prod`，不重启任何东西）：
- a. `check-source` 一正一反，现有生成器自动带上新脚本。正例的结果里多出的一对等于那条 STG run 的 `rollout` 结果；反例照旧拒绝。
- b. `promote` 先反后正，标签 `promote-trial`，默认身份，照平台的样子绑上那个没有任务用的工作区。反例给一个格式对但不存在的摘要：应拒绝，并且 `promote-trial` 没有出现。正例给 a 得到的一对：应成功，两个 `promote-trial` 指向这一对，两个 `:prod` 前后没变；再用 `check` 模式对 `promote-trial` 跑一正一反。留下两个没人读的标签，不删。
- c. 对着 PROD 的只核对试跑（没有重启那一步：`R/platform_digest_verify_trial.py:15`）：给第 4 项量到的一对应通过，给错的一对应拒绝。它证明 PROD 的 Role 新加的两条只读接通了，PROD 的 Pod 形状过得了核对，末尾重读在真实对象上不误拒。
- d. 等同步的任务对着 **STG 的应用**跑一次（每次 STG 发布本来就发这个请求）：应在几秒内通过，日志里前后两对时间戳不同。它量的是 §4.5 那条推断。

**次序**：PROD 的 Role → 核对任务 → 等同步的任务 → 试跑 c、a、b、d → 流水线（先 `--dry-run=server`）。任何一条试跑不符合预期，就不应用流水线。第一次真发布之后，统筹方只读把 §1 三行查一遍，结果写回台账。

**撤回**：Owner 重新应用今天的 PROD 流水线定义，即提交 `79c8088` 里的同一个文件（`I/docs/RELEASE.md:91`；它和主线今天的文件是同一份，sha256 `09dbb199…` 由 `R/test_platform_digest_verify.py:715` 钉着；线上是不是它，看上面第 1 项）。撤回之前要清场，和发布同一套条件：没有 PROD run 在途；没有走到过 `promote`、失败结束不到 10 分钟的 run；没有未结的 PROD 发布单（在另一份定义下建的单子要重建）。撤回之后下一次 PROD 发布照今天的样子重新构建。撤回不改已经挂上的标签，也不改正在跑的 Pod；Role 多出的两条只读、任务多认的命名空间、等同步的那个任务可以留着。

## 8. 没能确认的

| 没确认的 | 应用前怎么量 |
|---|---|
| 集群现状：线上定义是否等于主线，第 1、2 片是否已应用 | §7 先量 1 |
| kaniko 的摘要、registry 的摘要、`imageID` 三者相等；清单是单份还是多架构索引（是索引的话 §4.4 的读法要拒绝，回设计） | §7 先量 2。PROD 节点上的情形由第一次真发布的核对把关：不符就失败，关着 |
| registry 接受把按摘要取出的正文原样 `PUT` 到同一个镜像名下的另一个标签，并在 `HEAD` 里回摘要；对 config 和层的 `HEAD` 回 200（先例是 Trade 镜像的同步脚本，最近有没有成功跑过没查） | 试跑 b |
| `alpine/k8s:1.31.4` 的 python3 带 `urllib`、`hashlib`（推断：标准库）；默认身份的任务 Pod 连得上 registry（推断：kaniko 的 Pod 能推） | 试跑 b |
| Argo 在请求被处理完之前一直把 `.operation` 留在对象上；处理完之后 `operationState` 的时间戳会变 | 试跑 d |
| Tekton 的五个行为：声明了但没有任务用的工作区；失败的任务是否保留已写的结果（不保留时以日志那一行为准）；把 run 名传进任务的上下文变量；钉住路径建的 run 带不带 `tekton.dev/pipeline` 标签；失败和被取消的 run 的 `status.childReferences` 里有没有已经建出来的 `promote` 子项、`completionTime` 有没有 | 试跑 a、b；流水线的 `--dry-run=server`；后两项读已有的钉住 run 和一条失败的 run |
| PROD 的补丁没有逐个读全（名字带 token 的四个和 kubeconfig 那个没打开），所以「PROD 的 Pod 只有一个预期容器」是推断 | §7 先量 3，试跑 c |
| 旧清单在标签改写之后一直取得到（没人手工跑过垃圾回收） | 试跑 b 之后隔一次 STG 发布，按旧的 `:stg` 摘要再 `GET` 一次 |
| 退回（再发旧提交的 STG，再提升）要多久 | 第一次 STG 加 PROD 走完后记下两段耗时，写进发布单的回退说明 |
| 被取消的 run 的 `promote` 进程到底多久停（冷却的 10 分钟是按总时限 2 分钟加余量定的，没量过） | 不单独量。冷却宁长勿短；节点失联的情形见 §4.3 的假设 |
