# 切法：第 3 轮 3.4 发版提速 ①②（2026-10-22）

> Owner 10-21 23:2x 定「D3 A」：先做 ①「PROD 直接部署 STG 核对过的镜像摘要，不再从源码重建」（TD-335）和 ②「CI 在分支上先跑，绿了才合 main」。第 3 轮计划 3.4-1 到 3.4-5。
> 依据 infra main `ca6a157`，platform main `2c406dd0`。线 local_6f3ef5b9。
> 简写：`T/` = `k8s/cicd/tekton/`，`R/` = `scripts/release/`。

## 0. 验收（3.4-5）

1. 一次小修复从合 main 到 PROD 上线，用时比 10-21 少一半（约 1 小时降到约 30 分钟）。
2. PROD 跑的镜像摘要等于 STG 核对过的摘要。

第 2 条由 ① 的结构保证，每次 PROD 发版都会自己核对，见 §1.5。第 1 条要在一次真发布里量，见 §4。

## 1. ① PROD 按 STG 核对过的摘要部署

### 1.1 为什么这次不走前两次的路

TD-335 记了两条被叫停的路：
- 把摘要钉进 PROD 清单（三稿）：要流水线往 git 推提交，绕不开 TD-330。
- 按 tag 提升（两稿，`DESIGN-guard5-tag-route-stopped.md`）：registry 不鉴权，也没有比较后再写，`:prod` 写完之后谁都能再改；Deployment 写的是 tag，Pod 重启拉到什么由 tag 当时指向什么决定。

两条的共同毛病是，部署的东西是一个可改写的名字。

这次部署的东西是**摘要本身**：
- 流水线把摘要写进 Argo 应用的 `spec.source.kustomize.images`。Argo 渲染时在 overlay 上执行 `kustomize edit set image`，Deployment 的镜像就成了 `…@sha256:<摘要>`。
- 摘要按内容寻址，没有人能让它指向别的字节。tag 被谁改写都不影响正在跑的 Pod，也不影响以后的重启（TD-331）。
- 不往 git 推任何东西，所以 TD-330 不受影响。

已量（只读，2026-10-22）：
- 两个 platform 应用 `bifrost-platform-stg`、`bifrost-platform-prod` 都由 Owner 手工应用，不归任何上层应用管（没有 tracking-id），现在没有 `kustomize` 字段。
- `tekton-deliver` 在 `cicd` 对应用已有 get、patch、list（`T/rbac-deliver-stg.yaml:15-17`），不用加权限。
- **漏量了一处**：准入策略 `bifrost-platform-application`（`k8s/platform-rbac/40-admission.yaml`，TD-271）不许平台身份和 `tekton-deliver` 改 `spec.source.kustomize`。第一次 STG 真跑（2026-10-22，run `bifrost-deliver-platform-1792708927`）的钉镜像 patch 就是被它拒的，见 §1.8。
- 本机 kustomize v5.7.1 渲染 PROD overlay：镜像项加上摘要后，三个容器都是 `192.168.10.73:30500/bifrost-platform-{api,console}…@sha256:…`。overlay 原有的 `newTag: prod` 保留时得到 `:prod@sha256:…`，清掉时得到 `@sha256:…`，两种都按摘要拉取。

### 1.2 STG 流水线（顺带解决 TD-419）

次序不变：构建 → `agentrt-migrate` → `promote-images` → `gitops-sync` → `rollout`。改两处：
- `gitops-sync` 改引新任务 `bifrost-argocd-pin-sync-platform`（任务名不变，平台按这个名字给它 `tekton-deliver` 身份：platform `api/internal/delivery/service.go` 的 `platformTaskRunSpecs`）。它做三件事：
  1. 一次合并 patch，同时写两样：把应用的镜像钉到本次构建的两个摘要，并发出同步请求；
  2. 等这一次同步完成；
  3. 核对应用报告的镜像里有这两个摘要。
- `rollout` 的 `requireSpecDigest` 改成 `true`：Deployment 的 spec 必须写着这个摘要，Pod 也必须跑着它。spec 改了 Argo 自己会滚动，所以这一步只等滚动完成，不再 `rollout restart`。

两个 STG run 交叠时，后写的那个把应用钉成自己的摘要。先跑的那个的核对器读到的就不是自己的摘要，于是失败，不会把别人的构建记成自己发出的。TD-419 的验收「两个先后起的 STG run 各自发出各自的摘要」由此成立：要么各自成功、各自发自己的，要么失败。

`:stg` 照旧由 `promote-images` 挪：Owner 的迁移 Job、开发脚本、registry 保留规则还按 tag 读它。

### 1.3 PROD 流水线

| 任务 | 之前 | 之后 |
|---|---|---|
| `check-source` | 核对 CI、最新的 STG run 和它 `clone-platform` 的提交 | 另外读同一条 STG run 的 `rollout` 结果里那两个核对过的摘要，并核对这条 run 的 `clone-ui` 提交等于请求里 uiRevision 解析出的提交；多两个结果 `api-digest`、`console-digest` |
| `clone-platform` | 克隆，给构建用 | 保留，只给 `agentrt-schema` 读迁移文件；克隆的是 `check-source` 认定的那个提交 |
| `clone-ui`、两个 `stage-*`、两个 `build-*` | 从源码重建两份镜像 | 删除 |
| `agentrt-schema` | 用本次构建的 api 摘要 | 用 `check-source` 的 api 摘要（打印的迁移 Job 命令也用它） |
| `promote-images` | 把本次构建挪到 `:prod` | 把 `check-source` 那一对挪到 `:prod`。只给 tag 读者看，部署不靠它 |
| `gitops-sync` | 只发同步请求，排在 `rollout` 之后 | 改引 `bifrost-argocd-pin-sync-platform`，把应用钉到这一对、同步、等完成；排在 `rollout` 之前 |
| `rollout` | 重启后核对，`requireSpecDigest=false` | 等滚动完成后核对，`requireSpecDigest=true`，摘要取自 `check-source` |

省下的：两次 kaniko 构建、两次克隆中的一次、两份 Dockerfile。10-21 量到的 PROD 构建约 4 分钟。

「确实来自同一个提交」这样核：
- 这一对摘要来自 `check-source` 认定的那条 STG run 的 `rollout` 结果。核对器只在 Pod 真跑着它们之后才写这两个结果（`R/platform_digest_verify.py`），而它们的参数取自同一条 run 的构建结果。
- 同一条 run 的 `clone-platform` 提交等于请求的提交（原有核对），`clone-ui` 提交等于请求的 uiRevision（新增）。

### 1.4 新任务 `bifrost-argocd-pin-sync-platform`

参数：`application`（只认 `bifrost-platform-stg`、`bifrost-platform-prod`）、`apiDigest`、`consoleDigest`、`deliverRun`（流水线传 `$(context.pipelineRun.name)`：Tekton 只在 Pipeline 里替换它，写在 Task 里拿到的是字面文本，10-22 01:45Z TD-411 第一次真跑就栽在这上面）。步骤：

1. 校验参数。读应用，核对它的 path 是对应的 overlay、目的命名空间对得上。
2. 应用上已经有 `.operation`（别的同步在排队或在跑），就等它消失，有上限。
3. 一次合并 patch：
   - `spec.source.kustomize.images` = `registry.cicd.svc.cluster.local:5000/bifrost-platform-api=192.168.10.73:30500/bifrost-platform-api@<api>` 和 console 的同样一项；
   - `operation.sync`，`initiatedBy.username` = `tekton-deliver-platform:<本次 run 名>`。
   钉镜像和同步请求在同一次写里，Argo 处理的同步就是这份新 spec。
4. 每 2 秒读一次应用，直到这三样同时成立：
   - `status.operationState.operation.initiatedBy.username` 是这一次的名字；
   - `phase` 是 `Succeeded`；
   - `status.summary.images` 里有这两个钉住的镜像。
   `Failed` 或 `Error` 立刻拒绝；总共等 180 秒，到时拒绝。认「自己这一次」用的是这个名字，不比较秒级时间戳（前一稿复核 149 指出过后者的毛病）。
5. 只说固定的句子，不打印对象内容。

### 1.5 每次发布核对什么，之后成立什么

- **发布那一刻**：`rollout` 的核对器逐个读三个 Deployment：spec 写着这一对摘要、Pod 跑着它（`imageID`）、ReplicaSet 是当前版本。核对通过才写 `verified-at`。三个是先后读的，不是原子快照（原有限定）。
- **之后**：Deployment 写的是摘要，Pod 重启拉到的还是这一对。tag 被改写、开发脚本推 `:prod`，都不改变 PROD 跑什么。
- **能改它的**：
  - 下一次发布；
  - 有 `cicd` 写权限、去 patch 应用的人；
  - 有人用 `kubectl replace` 换掉整个应用对象，钉子就丢了，Deployment 回到写 tag，跑那一刻 tag 指着的东西。那不一定是钉着的一对：回滚钉回旧的一对不挪 tag，一次发布挪了 `:prod` 却没钉成，都会让两者不一致（复核 513 C1）。恢复办法是从最后一次成功 run 的结果取两个摘要再钉回去，并重新核对，不靠 tag。
  - 用 `kubectl apply`（客户端或服务端）重新应用 git 里的应用定义，钉子不会丢：那个字段不在 git 的定义里，`apply` 不会删它。
- **registry 里那一份被删掉**：现在没有清理作业。`R/../registry/keepset.py` 只是分析脚本，按计划将来按摘要删除保留集以外的镜像。这次让它把按摘要的引用也算进保留集。PROD 发布照旧把 `:prod` 挪到部署的那一对，所以正在跑的那一对始终有 tag。
- **TD-330 不变**：有人推 infra main 改了 platform overlay，Argo 照旧马上同步，但镜像仍钉在这一对上。

### 1.6 回滚

把上一次成功发布的那一对再钉回去。台账、run 结果、`:prod` 被挪动前打印的那一对都可以作为依据。两种做法：
- 再成功发一次旧提交的 STG，再提升。这条路已有，只是不再重建 PROD。
- Owner 直接 patch 应用的 `kustomize.images`，命令写在 `docs/RELEASE.md`。

W-56 门槛里的「回滚不重建」由此成立：被删掉的只会是没有引用的摘要。

### 1.7 不改的

- 平台仓库不用改：任务名不变，身份接线照旧。
- Console 的 PROD 步骤条按任务名分组，`Build` 那一段从此没有任务（`api/internal/delivery/pipeline_steps.go`）。这只影响显示，记为 platform 的后续。
- Trade 的发版流水线不在这一片。

### 1.8 准入策略的例外（第一次 STG 真跑之后补）

第一次 STG 真跑的 `gitops-sync` 退出码 1，日志只有「a cluster call failed」。
- 证据（只读）：apiserver 的计数 `apiserver_validating_admission_policy_check_total{policy="bifrost-platform-application",enforcement_action="deny"}` 在 22:45:23Z 第一次出现，值为 1；这次 `gitops-sync` 跑在 22:45:05–22:45:10Z。应用的 `kustomize.images` 是空的，同一次 patch 里的同步请求也没落下：被拒的 patch 什么都没写。
- 原因：策略要求 `spec.source.kustomize` 前后不变，`tekton-deliver` 也在它管的身份里。准入拒绝回的是 422「is invalid」，不含「forbidden」，任务把它归成了「a cluster call failed」。

改法：
- **策略**：`kustomize` 的规则拆成单独一条。前后不变照旧放行；另外只放行一种改动——`tekton-deliver` 改 `bifrost-platform-stg` 或 `bifrost-platform-prod`，改完的 `kustomize` 只有 `images` 一个键，正好两项，第一项是 api、第二项是 console，都是 `registry.cicd.svc.cluster.local:5000/bifrost-platform-<x>=192.168.10.73:30500/bifrost-platform-<x>@sha256:<64 位十六进制>`。平台身份照旧不能改；别的应用、按 tag、别的仓库、多带字段都不行。其余字段的规则不变。
- **任务**：失败的调用按固定类别报出，策略或 webhook 只报名字（名字先过正则），kubectl 的其余输出不进日志。类别只看 kubectl 最后报出的那条 API 应答：它明确拒了 patch（准入、403、422、404）时，日志说「application is left as it was」；没有应答（连接断了、读不到）或应答是服务器错误时，说「may be pinned」。前面的警告和发现请求的报错不算数：patch 可能已经写入，只是应答丢了（复核 514 B1）。
- **Owner 的应用脚本**：准入文件排第一个；应用完之后，以 `tekton-deliver` 身份对两个平台应用各做一次 `--dry-run=server` 的钉镜像 patch（不落库），必须通过；再试一次按 tag 钉，必须被这条策略拒。`check` 时也做，策略还没应用时如实报告「仍被拒」，不算失败。
- **`scripts/check_admission_guards.py --live`** 多六种：`tekton-deliver` 钉 STG（放行）、换仓库、按 tag、多带 `namePrefix`、钉 research（都拒），平台身份去钉（拒）。

别的走法（没选）：给两个应用加 `ignoreDifferences`、由流水线直接改 Deployment 的镜像。那会让 Argo 不再管镜像这一字段，回滚和自愈都要另做，改动更大。

## 2. ② CI 在分支上先跑，绿了才合 main

### 2.1 触发（`T/trigger-trade-ci.yaml`）

EventListener `bifrost-ci` 的五个 CI 触发（python、frontend、frontend-ui、platform、platform-ui）现在过滤的是 `body.ref == 'refs/heads/main'`，改成：

```
body.ref.startsWith('refs/heads/') && body.after != '0000000000000000000000000000000000000000'
```

也就是任何分支的推送都跑 CI，删除分支的推送不跑。`github-sync` 不改，照旧只跟 main 和 tag。CI 模板不改：`revision` 本来就绑的是 `body.after`，所以 `ci_gate.py` 按提交号认得出这次运行。

代价：每次推分支跑一次 CI；同一个提交合进 main 后会再跑一次。重复的这次不挡发布（发布认的是「这个提交有一次成功的 CI」）。去重留作后续。

### 2.2 push-main.sh

在窗口、快进、血缘检查之后，测试之前，加一步：

- 对有 ci-* 流水线的仓库，用 `R/ci_gate.py` 按 `仓库=提交号` 核对 cicd 里的运行：
  - 仓库：bifrost-platform、bifrost-trade-frontend，以及 python CI 触发列出的那几个；
  - `succeeded`：放行；
  - `failed`：拒绝，点名那次运行；
  - 还没有结果：等，最多 `PUSH_MAIN_CI_WAIT` 秒（默认 900），每 20 秒查一次，到时拒绝；
  - 一直是 `missing`：拒绝，提示先把分支推到 Gitea（`git push origin <分支>`），CI 由那次推送触发。
- 读不到集群（没有 KUBECONFIG、读失败）：拒绝，说明原因。
- 新开关 `--allow-red <原因>`：照样推，并打印原因。和 `release.sh --allow-red` 同义，给 Owner 或急修用。
- 没有 CI 的仓库（infra、bifrost-ui 等）：说明不检查，照旧放行。
- `ci_gate.py` 不在 `push-main.sh` 旁边：拒绝。它的退出码 2 表示「还没跑完」，python 找不到文件时也退出 2，不能把这两种混为一谈。
- 只改了 Markdown 的推送：不检查 CI，与测试的规则一致。

窗口照旧在推之前再查一次；code-health 和测试照旧。

## 3. 改哪些文件

infra（分支 `w31/release-speedup`）：

1. `T/task-argocd-pin-sync-platform.yaml`（新）＋ `R/platform_pin_sync.py`（新，嵌进任务）＋ 生成器 `R/embed_platform_pin_sync.py`。
2. `T/pipeline-deliver-platform.yaml`：`gitops-sync` 改引新任务、传摘要；`rollout` 的 `requireSpecDigest` 改为 `true`。
3. `T/pipeline-deliver-platform-prod.yaml`：删掉 `clone-ui`、两个 `stage-*`、两个 `build-*`；`check-source` 多两个结果；`agentrt-schema`、`promote-images`、`rollout` 的摘要改取自 `check-source`；`gitops-sync` 改引新任务，排到 `rollout` 之前。
4. `R/platform_prod_gate.py`：读 STG `rollout` 的一对摘要和 `clone-ui` 的提交；重新嵌入（`R/embed_platform_prod_gate.py`）。
5. `T/task-rollout-verify-platform.yaml`：`requireSpecDigest=true` 时不重启、只等滚动完成；接受 `true`。
6. `T/trigger-trade-ci.yaml`：五个 CI 触发的过滤条件。
7. `R/push-main.sh`：CI 检查、`--allow-red`。
8. `scripts/registry/keepset.py`：认得 `@sha256:` 的引用。
9. `R/release-speedup-apply.sh`（新）：Owner 的应用命令，见 §5。`scripts/k3s/apply-cicd-platform-pipeline.sh`（STG 平台流水线的引导脚本）补上 STG 流水线引用的任务：TD-411 的迁移任务、提升任务、迁移 RBAC，以及这次的钉镜像任务。
10. 测试：上面每一处各有一组，旧测试里钉住结构和哈希的地方随之改。
11. `docs/RELEASE.md`：PROD 不再构建、按摘要部署、回滚命令、`push-main.sh` 的 CI 一步。
12. `k8s/platform-rbac/40-admission.yaml`：§1.8 的例外；`scripts/check_admission_guards.py` 的 `--live` 多六种情况。

## 4. 量用时（3.4-5）

应用之后的第一次小修复照这样记下各段的起止时间：合 main → STG 发布结束 → PROD 审批单建成 → Owner 批 → PROD 发布结束。对照 10-21 那一次（约 1 小时）。
② 省掉的是「合 main 之后等 CI」：CI 已经在分支上跑过。① 省掉的是 PROD 的构建（约 4 分钟）。等 Owner 批单的时间不在这两项里。

## 5. Owner 怎么应用

一条命令，在 main 的检出目录里、用他自己的管理员 kubeconfig 跑：

```bash
bash /Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/scripts/release/release-speedup-apply.sh apply
```

先 `check`（只读）也可以。脚本照 `agentrt-migrate-pipelines.sh` 的做法：
- 提交必须在 origin/main 上，文件从这个提交取快照；
- can-i 初筛；
- 每个文件先 server dry-run，再 diff，全部通过才写；
- 出错即停，重跑安全。

应用次序：准入策略（§1.8）→ 两个 Task（新的钉镜像任务、改过的核对任务）→ 两条流水线 → CI 的 EventListener。
不写应用（Application）对象：第一次 STG 发版时由流水线自己钉。脚本只以 `tekton-deliver` 身份试一次钉镜像（`--dry-run=server`，不落库），确认准入放行它、拒掉按 tag 钉。

应用之后的第一次 STG 发版就是 ① 的真跑。核对四件事：
1. `gitops-sync` 日志有「pinned」那一行；
2. STG 应用的 `kustomize.images` 写着这次的两个摘要；
3. 三个 Deployment 的镜像是 `@sha256:…`；
4. `rollout` 通过。

之后第一次 PROD 发版没有构建任务，PROD 的三个 Deployment 写着同一对摘要。

## 6. 这一片证明不了的

- 准入策略的 CEL 在本机没有引擎可跑：测试只核对例外的每一部分，并拿任务自己的 patch 去匹配其中的镜像正则。它在 API 服务器上的行为由 Owner 应用脚本里的 dry-run 核实（§5），`check_admission_guards.py --live` 再覆盖拒绝的几种。

- 发布结束之后，有人手工 patch 应用或 `kubectl replace` 它（§1.5）。
- registry 将来的清理作业是否照 keepset 的保留集删除：那个作业还不存在。
- 等同步完成：「操作名对上、`Succeeded`、镜像在 summary 里」是按 Argo 的行为读的，由第一次真跑核实。核对器的 `requireSpecDigest` 不依赖它：同步没落地，核对就失败，不会错着成功。
