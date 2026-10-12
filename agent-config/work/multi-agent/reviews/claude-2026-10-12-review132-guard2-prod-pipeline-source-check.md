VERDICT: fix first
A SEQUENCE FOR (a)–(e): found
RULES THAT ONLY LACK A TEST: 6

（本文件由统筹方按复核子代理交回的全文存盘：子代理的工具拒绝写报告文件，它没有绕过。对象：infra `3ebabb5`（w31/guard-2）、platform `8fea559`（w31/guard-2-platform）。证据在 `~/agent-work/claude-review-132/`：`mutate.py`、`experiments.py`（E1–E5）、`infra/`、`platform/` 两个副本。）

一问的答案：**(d) 找到**；(a) 只在一种读法下成立（P2-2）；(b)、(c)、(e) 没找到。最小序列：两处都上线后，platform 的 main 从 X 前进到 X′；Owner 走仓库写明的钉住路径 `platform-prod-pinned-from-stg.sh <stg-run>` + `kubectl create -f`；生成的 run 照抄 STG run 的 taskRunSpecs（只有 rollout、gitops-sync），check-source 落在 `default` 下；X 有成功的 CI，STG 最近一次成功发布构建的正是 X，仍被拒：`REFUSED: CI cannot be shown for X: identity cannot read PipelineRuns/TaskRuns in cicd`。这时经平台也发不了 X：`revision=main` 解析成 X′ 被正确拒绝，整 SHA 被建 run 前的预检拒绝（`service.go:239`、`ref_preflight.go:85`，即 TD-295）。X 没有任何路径能上 PROD。
范围：两个 worktree 只读；没碰集群、网络、凭证，没提交。合并本身不会构建任何东西（Pipeline 要 Owner apply 才生效）。platform 那一半 `8fea559` 没有找到问题，可以先合。「fix first」指 infra `3ebabb5`：apply 前必须改的几处都在它动的文件和同目录里。第二轮的决定（跑在 `tekton-deliver` 下、不改 RBAC）站得住；它的代价是每一个不经平台的发起方都要自己点名这个任务，否则被拒，P2-1 就是漏掉的那一个。

**P1**：无。没有找到构建错提交、检查的提交与构建的提交不一致、或查询出错仍放行的路径。
**P2-1（d）** `scripts/release/release_tool.py:279`（`platform-prod-pinned-from-stg.sh:8-12`）：序列见上。实测（`experiments.py` E3）生成的 run 的 taskRunSpecs 是 `['rollout','gitops-sync']`。最小修法：`platform_pinned_run` 在线上 PROD Pipeline 有 check-source 时追加 `{check-source → tekton-deliver}`（和平台同一个条件），加一条测试。
**P2-2（a，取决于「最近一次」怎么读）** `scripts/release/platform_prod_gate.py:131-137`（YAML:324）按创建时间选。序列：STG run A 10:00 创建（提交 X），B 10:01 创建（提交 Y）；B 10:09 成功；A 的镜像推送和滚动都落在 B 之后，10:12 成功，STG 实际跑 X；PROD 对 Y 通过并构建 Y（E1，rc=0）。同类、但属于任务书规则 3 的字面、不算实现错：更新的一条 STG 发布还在跑，或滚动之后才失败，检查照样放行旧提交（E2）。最小修法：按创建和按完成选出的不是同一条就拒。「有更新的 STG run 未结束就拒」要不要，请统筹方定。
**P2-3** `k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:101-105` 用 `$(params.revision / uiRevision / giteaBase)`，但 taskSpec 没声明、任务处也没传。全仓库另外 9 个用到参数的内嵌任务都是先声明再显式传（如 `pipeline-deliver-prod.yaml` 的 preflight-stg）。这是唯一靠 Tekton 参数下传的一处，仓库不钉 Tekton 版本，无法证实。不下传时 REVISION 是字面量，每次发布都被拒。最小修法：声明三个 params 并显式传入，加一条结构测试。
**P2-4** YAML:88 `alpine/k8s:1.31.4` 里有没有 python3（脚本要 ≥3.9）和 git，仓库里没有证据：现有 Python 任务全用 `python:3.11-slim-bookworm`；这个镜像里唯一用 git 的那步先 `apk add git`（`apply-manifest/pipeline.yaml:150`）。缺 git → 每次拒；缺 python3 → 步骤起不来，连那一行拒绝都没有。按复核方对上游 Dockerfile 的记忆两者都有；本机没有这个镜像，没验证。另：夹具里的 PipelineRun / TaskRun 形状是自编的，这段脚本没有对着真对象跑过。
**P2-test（6 条规则只缺测试；在副本上种的违规全部存活）**：① CI 只比 SHA 前 7 位（`ci_gate.py:70`）；② STG 只比前 7 位（`platform_prod_gate.py:188`）——夹具只有 `a×40` 和 `b×40`；③ 还在跑的 CI 当成功（`ci_gate.py:73`）；④ clone TaskRun 没有 commit 结果时放行（`:188`）；⑤ `bifrost-deliver-platform-prod` 的 run 被当成 STG（`:125`）；⑥ 给整 SHA 时镜像回了别的 SHA（`:68`）。另有两处防御检查也没有测试（TaskRun 名字 `:179`、child kind `:172`）。修法：各补一个夹具。
**P3**（各一句）：`test_platform_prod_gate.py:147-156` 拿工作区和 HEAD 比，提交之后恒真，规则 7 被一次提交改掉时测不出来——改成比固定摘要。`:259` 超时用例把所有子进程的预算缩成 1 秒，假 git 也是一次 Python 启动；13 次运行里它红了 1 次（当时种的违规与它无关，重跑通过）。`platform_prod_gate.py:47`（YAML:235）ls-remote 的裸名是尾匹配：镜像上有 `wip/main` 这类分支时 `main` 被判歧义而拒（E4c），clone 自己能解析——去掉裸名那一个参数。`:155,163` 列出 cicd 里全部 PipelineRun（保留 7 天）并逐条校验：任何一条无关 run 形状异常就拒（E5）；体积和耗时没量过，预算 20 秒——改用标签选择器。没有 allow-red，也没有给同一 SHA 重跑 CI 的正规入口（平台起的 CI run 不带 repo 标签和 SHA）；CI 偶发失败或 run 满 7 天被清后，只能重投 webhook 或推新提交。UI 提交只解析不检查，PROD Console 用的 bifrost-ui 可以不是 STG 构建的那个（实现报告已声明不在范围）。`docs/RELEASE.md` 没有这道检查、上线次序、回退的任何文字。

**八点**
1. 是同一份代码：`platform_prod_gate.py:12` 引 `ci_gate.classify`，内嵌副本由 `test_shared_ci_definition` 逐字比对；差别只有没有 allow-red、不等待。对 Trade：集合多了 `bifrost-ci-platform`，`release.sh:403` 多读一个列表；该流水线的 run 标签固定是 `bifrost.io/repo=bifrost-platform`（`trigger-trade-ci.yaml`），所以 Trade 仓库的判定结果不变；平台 `release_policy_facts.go:49` 本来就是这三条。
2. 有：`test_platform_prod_gate.py:131-144` 要求逐字相等（从两个 .py 重新生成一遍，和提交的 YAML 逐字节相同）。镜像 `alpine/k8s:1.31.4`，与 rollout 相同（有测试）。运行时不安装任何东西，比 preflight-stg（`apk add curl`）还少；它访问 Gitea（ls-remote，两个仓库各一次 depth=1 fetch）和 apiserver。
3. 只在流水线名是 `bifrost-deliver-platform-prod` 且线上 Pipeline 的 `spec.tasks` 里有名为 check-source 的任务时加（`service.go:1545-1561`），依据是建 run 之前本来就有的那次 Pipeline GET（`:252`）。GET 失败 → 不建 run（原有行为）；tasks 读不出 → 不加 → 检查在 default 下拒绝。Tekton 怎么对待指向不存在任务的 override：仓库不钉版本（安装脚本取 latest，注释里提到 v1.6），没有源码，**无法从仓库证实**；按复核方对上游的记忆是 run 以 InvalidTaskRunSpecs 失败。条件式写法让两种次序都不依赖它，只剩「GET 之后、Tekton 解析之前 Pipeline 被换」这一瞬间。
4. `tekton-deliver` 还能：patch cicd 里的 Argo Application；cicd 里**所有** ConfigMap 的 get/create/patch/update（含 Dockerfile、发布窗口、冻结那几个）；patch bifrost-stg、bifrost-prod 的 Deployment / StatefulSet 和 platform-stg、platform-prod、research 的 Deployment；读 IngressRoute、列 freezes（`rbac-deliver-{stg,prod,platform,research}.yaml`）。脚本是 Pipeline 里的静态文本，三个参数经 env 进来、不拼进脚本，只跑 git 的四个子命令和 `kubectl get`，不执行拉回来的内容：不是实质的新暴露面。剩两点：这一步同时拿着 Gitea 凭证和这个身份的令牌；手建的 run 可以改 giteaBase，凭证头会发到那个地址（clone 任务本来就这样）。
5. 会，而且是一行（假 kubectl 实测；RBAC 文件里 default 只有两个 ConfigMap 的 get 和 freezes 的 list；没在真集群上验证）。引用这条 Pipeline 的 run 没有跳过的办法：没有 when，两个 clone 吃它的结果。它管不到的（原本就有）：内联 pipelineSpec 的手建 run；手建 STG 流水线并把 `platformApiImage` 指到 `:prod`。
6. 被杀死：收下失败的 CI → `test_ci_refuses[failed]` 和 `test_ci_gate.py::test_failed_run_reads_failed`；集群里没有 STG run 也放行 → `test_stg_refuses[missing]`；STG 不看成功与否 → `test_latest_stg_selects_newest`；平台侧不管有没有任务都加 override → `TestPlatformSourceGateIdentity/old_prod`。存活：只比 SHA 前缀（CI、STG 各一）、STG 的 TaskRun 没有 commit 结果也放行，以及 P2-test 的其余三条。
7. Owner 的次序：① 含 `8fea559` 的 platform 照常发到 PROD（走旧流水线，Console 上批一张单）；② 确认 PROD 跑的是它；③ 没有平台发布在跑、没有未结的 PROD 发布单时，在 infra 主线根目录、他自己的终端：`kubectl apply -f k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml`；④ 回退是把旧版本的同一个文件再 apply 一次。次序反了：每次平台 PROD 发布都被拒，包括带来另一半的那一次，只能由他回退 Pipeline。这条命令是仓库自己的做法（`docs/RELEASE.md:202-204,253`：Pipeline 由 Owner 按文件 apply，不走 bifrost-apply-manifest；`scripts/k3s/install-stack-tekton.sh:76`）。
8. **合并前**：a. 钉住路径生成器补上 check-source 的身份并加测试（P2-1）；b. STG「最近一次」在创建序和完成序不一致时拒绝（P2-2）；c. 三个参数显式声明并传入（P2-3）；d. 补 6 条缺的测试，超时用例去抖，health 测试改成比固定摘要。**apply 前**：a. platform 那一半已在 PROD；b. 用探针 Pod 确认镜像里有 python3 ≥3.9 和 git；c. 把 check-source 单独放进一条只含它的内联 PipelineRun（身份指到 tekton-deliver），对 STG 当前提交跑一次应通过、对一个没有 CI 的旧 SHA 跑一次应拒——不含 clone 和构建，不会发布任何东西，却把真对象形状、身份、镜像、Gitea 凭证都验了；d. 量一次 `kubectl -n cicd get pipelineruns -o json` 的耗时和体积；e. RELEASE.md 写上这道检查、次序、回退、没有 allow-red。

测试运行：pytest 13 次（基线 1 次 54 passed；种违规 12 次，其中 1 次是重跑），go test 3 次（基线 1、种违规后编译失败 1、种违规 1）。另跑了一次不是测试的实验脚本（`experiments.py`，E1–E5）。都是一次一个。
END OF REPORT

---

## 第三轮确认（同一位复核方，2026-10-12，对象 `git diff 3ebabb5 816ef33`）

VERDICT: safe to merge。合并前的四条 a–d 全部 closed；复核方自己种的八处错全部被测试拦住；(b)(c)(e) 没找到。留给应用之前的四处：① 试跑生成器补上 amd64 的 taskRunTemplate（否则试跑验的可能不是正式 run 用的镜像变体）；② 两条 STG 发布交叠、旧的在新的完成之前结束时仍会放行新的提交——改成其它 run 必须在最新那条创建之前结束；③ RELEASE.md 补 Owner 动手时要的命令、试跑各应看到什么、各条拒绝怎么办；④ 选择器检查的后半句补夹具，去掉 pipelineRef 的默认值。另记：一条永远拿不到 completionTime 的 STG run 会让每次发布被拒，直到有人删掉它（拒绝行会点名）；试跑读的是检出目录里的定义，要在将要应用的那个提交上生成；内联 spec 只有 Owner 的身份建得了。

统筹方的处理：四处都改了（`6f77bde`），Codex 只读确认（复核 135，同目录）代码三处通过、文档两处不对，文档已改并加了一条测试（`6e92bad`、其后一个提交把手工创建命令挪进脚本自己的帮助——已有防线 `test_release_docs_do_not_create_pipelineruns_by_hand` 不改）。合并：infra `667b758`。

