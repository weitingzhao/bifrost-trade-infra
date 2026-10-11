# W-56 — PROD 发布不再逐次由 Owner 批准：门槛、顺序，以及先做的两条

决策线程，2026-10-10 晚。状态：方案，等 Owner 过目；G1、G2 的代码先在分支上做，不改任何线上环境。

## Owner 定的三件事（2026-10-10）

1. 不做「沉默即同意」。没人处理的单到期作废。
2. 放行只来自事先签过名的规则；符合规则的立刻自动放行。
3. 目标：他逐次批准发布的次数降到零，只签规则、只看例外。

## 现状（当天实测）

- PROD 流水线 `bifrost-deliver-platform-prod`（`k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml`）：第一步 `preflight-stg` 只看 STG 的 API 和 Console 是否回 200；然后按 `revision`（main）重新克隆、重新构建 `:prod` 镜像，`rollout restart`，Argo sync。
- 它**不查**该提交的 CI，**不查** STG 上跑的是不是同一个提交，部署的也**不是** STG 验过的那一份产物（当天 api 镜像的摘要 STG 与 PROD 不同；Console 的构建恰好是确定的，三处同一个文件名）。
- 当天的证据：`e5a0703` 在 CI 红的情况下发了 PROD，唯一的检查是 Owner 的那一下批准（LESSONS 第 38 行）。
- 平台仓库没有合并前的 CI；CI 只在 main 上触发（第 40 行）。
- STG 没有审批数据和通知配置，演练不了审批链路（第 36 行）。

## 六个门槛

| # | 门槛 | 现状 | 怎么验收 |
|---|---|---|---|
| G1 | 发布门：流水线自己确认「这个提交的 CI 成功，且 STG 上跑的就是它」 | 没有 | 四个演练：CI 红、CI 还没跑完、STG 是别的提交、STG 刚发不到观察时间，各自被拒并写明原因 |
| G2 | 同一份产物：PROD 部署 STG 验过的镜像摘要，不重新构建 | 没有（每次重建） | 发布后 PROD Pod 的镜像摘要等于 STG 的；流水线里没有构建步骤 |
| G3 | 回滚不重建：上一版的摘要留着，一步切回 | 没有（要重建旧提交） | 演练：发一版、回滚，全程不构建，用时在一分钟量级 |
| G4 | 发布后自动核对，不过就自动回滚并通知 | 没有（靠执行的线程手工核对） | 演练：发一个起不来的版本，系统自己回滚并推一条 `Check` |
| G5 | 冻结对每个入口生效，Agent 改不了冻结开关 | 部分（TD-293、TD-294） | 冻结期间从每个入口发起都被拒；平台账号改冻结 ConfigMap 被拒 |
| G6 | 平台自己升级失败，由带外的手段拉回 | 没有（W-50） | 演练：新版 platform 起不来，带外执行器把它切回上一版 |

G1–G4 过了，规则里才列 PROD 的两条流水线；G5、G6 过了，才谈无人值守。规则本身由 Owner 用签名密钥签（W-42 已有引擎）。

## 先做的两条

### G1 发布门

流水线第一步 `release-gate`（替换现在的 `preflight-stg`，保留它的两个健康检查）：

1. 把 `revision`、`uiRevision` 解析成两个仓库的完整 SHA（Gitea）。
2. 要求 platform 的 SHA 有一个 `Succeeded` 的 `bifrost-ci-platform` run（`spec.params.revision` 等于该 SHA）。复用并扩展 `scripts/release/ci_gate.py` 的判定（它现在只认 `bifrost-ci-python` 和 `bifrost-ci-frontend`）：成功放行；失败拒绝；还没有终态的，等到超时再拒绝。
3. 要求最近一次成功的 STG 发布（`bifrost-deliver-platform` 的发布记录，或它的 `clone-platform` / `clone-ui` 结果）就是这两个 SHA，并且完成已经超过观察时间（起点 10 分钟）。
4. 任一条不满足：失败，日志第一行写明差在哪（「CI 是红的：<run>」「STG 上是 <sha>，不是要发的 <sha>」「STG 才发了 3 分钟」）。

判定逻辑放在一个带单测的脚本里，Tekton 只负责调用。流水线的账号需要能读 `cicd` 里的 PipelineRun / TaskRun（或发布记录的 ConfigMap）；这是 RBAC 变更，平台的自动应用不能写，要 Owner 执行一次。

没有「放行红的」参数。确实要带着红发，走 Owner 手批的旧流水线，并在单子里写明。

### G2 同一份产物

新流水线 `bifrost-promote-platform-prod`，先和旧的并存，旧的不动：

1. `release-gate`（同上）。
2. 从 STG 的两个 Deployment 读出正在跑的镜像摘要（api 和 console；workers 与 api 同一个镜像）。
3. 在 registry 里：把现在的 `:prod` 摘要另存为 `:prod-prev`，再把 STG 的摘要打成 `:prod`。不拉取、不构建，只动标签。
4. `rollout`（沿用现有任务），然后核对 PROD 每个 Pod 的 `imageID` 等于第 2 步的摘要，不等就失败。
5. Argo sync（沿用）。

回滚（G3 的前半）：`bifrost-rollback-platform-prod`，把 `:prod-prev` 打回 `:prod`，rollout，核对摘要。

注意 registry 的垃圾回收：被标签指着的摘要不能被回收；`:prod-prev` 就是为此而留。

## 谁做、怎么上线

- Cursor 实现脚本、任务、两个新流水线文件和离线测试；决策线程重跑验收；Codex 复核（这是放权的前置，必须有第三方复核）。
- 上线分三次，每次都能单独回退：① 脚本与测试进 main（不改集群）；② RBAC（Owner 执行，D 级）；③ 新流水线和任务进集群（`k8s/cicd/tekton` 走 plan / apply，C 级，Owner 在 Console 批）。旧流水线保留到新流水线演练通过。
- 演练在 STG→PROD 的真实链路上做，G1 的四个拒绝场景可以不发布任何东西就演练。
- Owner 要做的：批 ②、③ 两次；之后生成签名密钥、签第一份规则。

## 不在这一步里

- Trade 的两条 PROD 流水线同样的改造（先在平台自己身上做完、演练过再搬）。
- G4–G6。
- 平台仓库合并前的 CI（单独一条；G1 上线后，红的提交至少发不出去）。

## What is on the branch

分支 `w31/w56-gates`。只加了文件、脚本和离线测试，没有对任何集群 apply，没有起流水线，没有写 registry。

| 文件 | 做什么 |
|------|--------|
| `scripts/release/ci_gate.py` | `CI_PIPELINES` 加上 `bifrost-ci-platform`，发布门复用它的匹配函数 |
| `scripts/release/test_ci_gate.py` | 平台 CI 只在 `bifrost.io/repo` 标签上时也能对上 |
| `scripts/release/release_gate.py` | G1 判定。无网络。没有放行红 CI 的参数 |
| `scripts/release/test_release_gate.py` | 通过、CI 红、CI 还在跑、没有 CI、STG 的 platform SHA 不同、UI SHA 不同、浸泡不够、更新的失败 STG 不算、坏输入 |
| `scripts/release/registry_retag.py` | G2 `promote(repo, source, target, keep_as)`：Registry v2 上按原字节改标签 |
| `scripts/release/test_registry_retag.py` | 假 registry：单 manifest、index、源不存在、目标第一次不存在、再跑是空操作、PUT 字节与摘要一致 |
| `k8s/cicd/tekton/task-release-gate-platform.yaml` | 解析两个 SHA、两个 STG 健康检查、`kubectl get` 后跑判定脚本 |
| `k8s/cicd/tekton/rbac-release-gate.yaml` | `tekton-deliver` 只读 cicd 的 PipelineRun/TaskRun，以及两个平台命名空间的 Deployment 和 Pod。Owner 自己 apply |
| `k8s/cicd/tekton/pipeline-promote-platform-prod.yaml` | `bifrost-promote-platform-prod`：门 → STG 摘要 → 打成 `:prod` → rollout → 核对三个 Deployment → Argo sync |
| `k8s/cicd/tekton/pipeline-rollback-platform-prod.yaml` | `bifrost-rollback-platform-prod`：`:prod-prev` 打回 `:prod`（旧 `:prod` 留在 `:prod-next`）→ rollout → 核对 → Argo sync |
| `docs/RELEASE.md` | 「Platform PROD: promote instead of rebuild」一节 |

还没做：

- 演练（G1 的四个拒绝、G2 发布后摘要一致、G3 发一版再回滚且不构建、用时在一分钟量级）。回滚流水线只是 G3 的前半。
- G3 的后半：真实链路上的回滚演练，以及确认 `:prod-prev` 挡得住 registry 垃圾回收。
- G4、G5、G6。
- Trade 的两条 PROD 流水线同样的改造。
- 平台仓库合并前的 CI。
- 平台 catalog / 发布策略 / `window_decision.py` 还没有这两条流水线（本任务不改那些文件）。旧的 `bifrost-deliver-platform-prod` 还在。
- `k8s/cicd/tekton` 没有目录级 `kustomization.yaml`（只有 `apply-manifest/`）。新文件和旁边的 Task、Pipeline 一样是散的清单，这样 `check_apply_paths` 不会因为新的 kustomization 漏掉原有文件。
