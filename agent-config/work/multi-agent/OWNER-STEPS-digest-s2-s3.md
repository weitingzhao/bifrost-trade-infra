# 护栏 ⑤ 第 2 片和收口片：发布后按摘要核对 Pod（要你动手的四条命令）

写给 Owner。四条命令，每条之间统筹方用只读身份核对，核对过了才在线程里说「可以做下一条」。每条做完都不用回话，输出也不用你判断。

2026-10-13 写成。全部取自 infra 主线提交 `b9ec3786f381`（第 2 片 `f5ab877` 加收口片）。实现经独立复核（Claude 的子代理两次：可以合并）；**这张清单**另经 Codex 只读核对（核对 151：第一稿要求改 8 处，本稿已全部改入，见文末）。

## 这四步合起来是什么

平台每次发布（测试环境和正式环境）在重启三个服务之后，多做一步核对：三个 Deployment 的 Pod 跑的镜像摘要，等于这次发布自己刚构建的那一对；不等就算发布失败。以前真出过发布成功而 Pod 还停在旧镜像上的事，这一步管这一类。

它**不改**镜像怎么来：正式环境照旧重新构建（⑤ 收口，你 2026-10-13 13:03 定的）。它说的是「核对读到的那一刻」，之后的事不在保证内（之后的同步、别人改标签、Pod 以后重启拉到什么：TD-330、TD-331、TD-335）。

## 做之前（统筹方核对后在线程里说「可以做第 1 条」）

- 没有平台发布在跑；没有未结的正式环境发布单（#15 已在 2026-10-13 18:15 发完）。
- 第 1 片已应用（2026-10-13 13:15，已核对）：两个构建任务会记下 `digest`。
- 线上现状（2026-10-13 14:10 只读量到）：正式环境流水线等于 `0e3d33b`（同 `79c8088`）的文件；测试环境流水线等于 `d5154ea` 的文件；两个 Role 都只有 Deployment 的规则；核对任务还不存在；Tekton 是 v1.6.0。
- 统筹方在这四步期间占着平台的发布窗口。

**不要用** `scripts/k3s/install-stack-tekton.sh`、`scripts/k3s/apply-cicd-platform-pipeline.sh`、`scripts/k3s/run-deliver-platform.sh`：它们会整批应用，跳过下面的试跑。

每条命令的输出：下面写的是**预计**看到的，实际可能不同（例如重复执行会显示 `unchanged`）。你不用判断；出现警告、报错或和预计不一样的输出，原样留着、不要再试，告诉统筹方，由统筹方读回线上状态来核对。服务端试算通过也不保证随后的真应用一定成功；每条命令都不是一个整体，中途失败不会自动撤回。

## 第 1 条：两个 Role 的只读权限，和新的核对任务

```bash
( set -o pipefail; cd ~/Desktop/stocks/bifrost-trade-infra && git fetch -q origin && export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml" && r=k8s/cicd/tekton/rbac-deliver-platform.yaml && t=k8s/cicd/tekton/task-rollout-verify-platform.yaml && git show "b9ec3786f381:$r" | kubectl apply --dry-run=server -f - && git show "b9ec3786f381:$t" | kubectl apply --dry-run=server -f - && git show "b9ec3786f381:$r" | kubectl apply -f - && git show "b9ec3786f381:$t" | kubectl apply -f - )
```

- 被应用的对象共五个：`bifrost-platform-stg` 和 `bifrost-platform-prod` 里的 Role `tekton-deliver-rollout`（各加两条**只读**：读 Pod、读 ReplicaSet）和同名的 RoleBinding（期望的内容不变，但仍是应用的对象，元数据可能被更新）；`cicd` 里新建 Task `bifrost-rollout-verify-platform`。
- 这一条不改变任何发布的行为：还没有流水线用这个新任务。
- 预计看到：先五行带 `(server dry run)` 的（两个 `role… configured`、两个 `rolebinding…`、一个 `task… created`），再五行不带的。两个 RoleBinding 可能是 `unchanged`，也可能是 `configured`。
- 中途失败会留下一部分已应用（例如两个 Role 已更新而任务没建出来）。留下的都是只读权限或没人用的任务，不影响发布。

统筹方随后只读核对：两个 Role 各有三条规则；线上的任务两个步骤里都认 `bifrost-platform-prod`（试跑内联的是本地文件里的步骤，证明不了线上任务是这一版，所以要读回）。

## 第 2 条：四条只核对的试跑（两个环境各一正一反）

试跑会在 `cicd` 里创建四个 PipelineRun（控制器随后为每个建一个 TaskRun 和一个执行 Pod，并写状态和结果）。其中的核对步骤对两个环境**只读**：不重启任何东西，不碰镜像。正例给当前在跑的那一对摘要，应成功；反例把接口镜像的摘要改掉最后一位（格式仍然合法、Console 的摘要保持正确），应被拒绝。

```bash
( set -o pipefail; cd ~/Desktop/stocks/bifrost-trade-infra && git fetch -q origin && export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml" && d="$(mktemp -d)" && mkdir -p "$d/scripts/release" "$d/k8s/cicd/tekton" && for f in scripts/release/platform_digest_verify_trial.py scripts/release/embed_platform_digest_verify.py k8s/cicd/tekton/task-rollout-verify-platform.yaml; do git show "b9ec3786f381:$f" > "$d/$f" || exit 1; done && g() { /opt/anaconda3/bin/python3 "$d/scripts/release/platform_digest_verify_trial.py" "$@"; } && SA=sha256:6f5993fa0735b2ca255814b674b478c92f00984b7c57556c24ab50ab3883ea78 && SC=sha256:24fa444a4093bdcb75eedc92402c7b65ee766c7f57c33963ea3e1b3121712376 && SX=sha256:6f5993fa0735b2ca255814b674b478c92f00984b7c57556c24ab50ab3883ea79 && PA=sha256:71258ff9e75ffe2f91c6f756395584390915982ef0ba57775c09e3057bab74da && PC=sha256:a65a75f8c6fc8895829a3a109d93e04dc565df0c153a3c14a492c0ee25373ada && PX=sha256:71258ff9e75ffe2f91c6f756395584390915982ef0ba57775c09e3057bab74db && g "$SA" "$SC" > "$d/stg-ok.yaml" && g "$SX" "$SC" > "$d/stg-bad.yaml" && g "$PA" "$PC" --namespace bifrost-platform-prod > "$d/prod-ok.yaml" && g "$PX" "$PC" --namespace bifrost-platform-prod > "$d/prod-bad.yaml" && for y in stg-ok stg-bad prod-ok prod-bad; do test -s "$d/$y.yaml" || exit 1; done && for y in stg-ok stg-bad prod-ok prod-bad; do kubectl create -f "$d/$y.yaml" || exit 1; done )
```

- **上面的摘要是 2026-10-13 18:16 量的（两个环境 Pod 在跑的那一对；正式环境的是 #15 发完之后的）。摘要可能随发布改变，每次试跑前要重新量。统筹方说「可以做第 2 条」时会在线程里给出当时量到的完整命令，以线程里的为准。**
- 生成试跑用的三个文件先从主线提交取到一个临时目录，再从那里生成：共享检出目录里别的会话没提交的改动进不来。四份清单都生成出来、都不为空之后，才开始创建。
- 预计看到四行 `pipelinerun.tekton.dev/platform-digest-trial-… created`。某一条创建失败时停在那里，之前已经创建的试跑会继续跑完，不会被撤销（它们只读，留着无害）。
- 试跑用的身份是 `tekton-deliver`（流水线里重启和核对用的同一个），所以它同时证明第 1 条加的只读权限接通了。
- 试跑的 run 带的流水线标签是它自己的名字（量过：内联定义的 run 都是这样），正式环境的源检查不会把它当成一次测试环境发布。

统筹方随后只读核对：两条正例成功、结果里的一对等于给进去的一对、核对步骤用时（超过约 15 秒就先不往下做）；两条反例失败，日志里是 `REFUSED: platform digest verification: container imageID digest differs or is invalid`。**任何一条不符合预期，后面两条都不做。**

## 第 3 条：测试环境的流水线

```bash
( set -o pipefail; cd ~/Desktop/stocks/bifrost-trade-infra && git fetch -q origin && export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml" && p=k8s/cicd/tekton/pipeline-deliver-platform.yaml && git show "b9ec3786f381:$p" | kubectl apply --dry-run=server -f - && git show "b9ec3786f381:$p" | kubectl apply -f - )
```

- 被应用的对象：`cicd` 里的 Pipeline `bifrost-deliver-platform`。相对线上今天的定义，改的只有 `rollout` 这一个任务：改用新的核对任务，并把两个构建任务记下的摘要传给它。
- 预计看到：`pipeline… configured (server dry run)`，再一行 `pipeline… configured`。真应用报错时不能认定旧定义还在，由统筹方读回确认。
- 从这一刻起，测试环境的平台发布会在重启后核对 Pod。

统筹方随后**真发一次测试环境**（重发当前主线提交），看重启加核对在真流水线里走通：`rollout` 成功，结果里的一对等于两个构建任务记下的一对。

**如果那一次测试环境发布失败**：正式环境的源检查只认「创建时间最新的那一次测试环境发布」，并要求它成功；它不会退回去找上一次成功的。所以一次失败的测试环境发布会一直挡住之后的正式环境发布，光把流水线撤回也解不开。这时：不做第 4 条；按下面的办法撤回测试环境流水线；**正式环境发布保持暂停**，直到统筹方再完成一次成功的测试环境发布，并核对它的提交等于要发正式环境的提交。

## 第 4 条：正式环境的流水线

```bash
( set -o pipefail; cd ~/Desktop/stocks/bifrost-trade-infra && git fetch -q origin && export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml" && p=k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml && git show "b9ec3786f381:$p" | kubectl apply --dry-run=server -f - && git show "b9ec3786f381:$p" | kubectl apply -f - )
```

- 被应用的对象：`cicd` 里的 Pipeline `bifrost-deliver-platform-prod`。改的只有 `rollout` 这一个任务；源检查（check-source）、六个构建相关的任务、次序都不变。
- 预计看到：`pipeline… configured (server dry run)`，再一行 `pipeline… configured`。真应用报错时同样由统筹方读回确认。
- 这一条不发布任何东西。下一次正式环境发布（照常由你批一张单）会多这一步核对；那一次发完，统筹方只读核对结果并写回台账。
- 做这一条时必须没有未结的正式环境发布单、没有发布在跑。

## 撤回（各自独立；都要在没有平台发布在跑、受影响的环境没有未结发布单的时候做；做完由统筹方读回确认后才放行新的发布）

正式环境的流水线恢复成今天的定义（`0e3d33b`，与 `79c8088` 逐字节相同；**不是** `docs/RELEASE.md` 里另一处写的 `27e4467`，那一条会连源检查一起撤掉）：

```bash
( set -o pipefail; cd ~/Desktop/stocks/bifrost-trade-infra && export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml" && git show "0e3d33b:k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml" | kubectl apply -f - )
```

测试环境的流水线恢复成今天的定义（`d5154ea`）：

```bash
( set -o pipefail; cd ~/Desktop/stocks/bifrost-trade-infra && export KUBECONFIG="$HOME/.bifrost-owner/kube/admin.yaml" && git show "d5154ea:k8s/cicd/tekton/pipeline-deliver-platform.yaml" | kubectl apply -f - )
```

- 撤回恢复的是流水线的定义：之后的发布照今天的样子，重启后不核对。它不恢复已有的发布记录、镜像和正在跑的服务。
- 核对任务和两个 Role 多出的只读权限可以留着；只要还有一条流水线引着核对任务，就不能删它。
- **只要还有一条新流水线在引用 `digest`，第 1 片的撤回（`OWNER-STEPS-digest-s1.md` 里把两个构建任务恢复成 `d5154ea`）就不能单独用**：结果引用会没有来源，发布会因此失败。要撤第 1 片，先把所有引用摘要的新流水线撤回。

## 应用之后会怎样

- 重启的做法和今天相同（先接口、再 Console、再后台，各等最多 300 秒）；多出的是重启之后的核对，最多 3 遍、总共 55 秒。
- 核对不过时，发布记为失败，而三个服务已经走完重启这一步；它们实际跑的是哪一份镜像，以读回为准（这正是核对要发现的）。正式环境那一次随后的显式同步不跑；Argo 的自动同步是否补上、运行状态如何，由统筹方核对。这是一次要人看的失败，不会自己退回。
- 两种少见的误拒（关着失败，不是错的成功）：Argo 恰好在核对的几十秒里改了 Deployment；集群接口很慢。统筹方确认原因和稳定状态之后再决定是否重发。

## 统筹方已有的证据

- 第 1 片量过的三个值：2026-10-13 13:20 的测试环境发布里，两个镜像各自的「构建记下的摘要 = registry 回的摘要 = Pod 在跑的摘要」；清单是单份，不是多架构索引。
- 两个环境 Pod 的真实形状（2026-10-13 13:10 只读量到）：每个 Pod 一个容器、没有 init 和临时容器、属主是 ReplicaSet、`imageID` 带 `@sha256:`；正式环境 Console 是两个副本。和核对任务的假设一致。
- 收口片：Codex 实现；独立复核两次，结论都是可以合并、没有必须改的；合并后的树上整套测试 483 条通过。
- 第 2 条的命令用假的 `kubectl` 在 zsh 里演练过：生成四份清单、依次创建；提交不存在时在创建之前停下。
- 没有在集群上跑过的：重启那一步的新写法（第 3 条之后的那次测试环境发布是第一次）；正式环境里核对的真实用时（第 2 条的正例试跑是第一次测量）。

## 核对 151（Codex，只读）要求改的 8 处（都已改入）

1. 第 3 条之后那次测试环境发布如果失败，会一直挡住正式环境发布，光撤回流水线解不开：补上了恢复步骤。
2. 第 2 条的守卫挡不住守卫通过之后别的会话改文件：改成把三个文件从主线提交取到临时目录再生成，并且先生成、检查、再创建。
3. 反例从「两个摘要对调」改成「接口摘要改一位、Console 摘要保持正确」：对调在两个摘要相同时不是反例。
4. 预期的拒绝句补全了前缀。
5. 被应用和被创建的对象列全（两个 RoleBinding；四个 PipelineRun 以及它们带出的 TaskRun 和 Pod）。
6. 输出写成预计值，并写明实际可能不同、不用你判断。
7. 核对失败之后的镜像状态、自动同步、重发，不再写成保证。
8. 「每发一次版摘要就变」改成「可能改变，每次试跑前重新量」。

另按它的建议：撤回前也要求受影响的环境没有未结发布单，撤回后由统筹方读回确认；「发布起步就失败」收窄成「因摘要结果引用无法满足而失败」。实现复核的「可以合并」不等于这张清单可以交付——清单以本节的核对为准。

**复核 151b（2026-10-13 18:15）：可以给 Owner。8 处都改对了，没有必须改的；第 1、3、4 条和两条撤回命令与第一稿逐字相同，只有第 2 条命令改过。** 它之后统筹方只把第 2 条里正式环境的三个摘要换成了 #15 发完后量到的值（格式和位置不变）。
