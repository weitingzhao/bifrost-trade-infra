# 4.3 每个应用自己的发布节奏：发布操作、应用车道与按应用的发版策略（设计稿，2026-10-24）

> 状态：**第 3 稿**，回应 Codex 复核 571 的 B1–B3、C1–C3、N；逐条回应在 `~/agent-work/codex-review-571/RESPONSE.md`。保留复核 532 已补的约束。第 4 轮 4.3（W-31；Owner 2026-10-23 23:3x「D2 A」），含 W-56 剩下的门槛。本文是待定案设计，不是无人值守上线许可。
> 本稿源码核对：2026-10-26，`~/Desktop/stocks/` 下 infra HEAD / origin/main 均为 `833a2461fdea78b9f7ed6841ba0587b47fed009b`；platform HEAD `ed8bb2276d423085014d80fddebfe2937c60f3be`，origin/main `ca4f814998d335db45aebf40f721f2e2408e0fd3`，未 fetch。当前事实按本地源码核对，不代表已部署。§1.2 的集群数量、Finance 和 §1.3 数字仍是第二稿 2026-10-24 04:4x UTC 的历史快照（infra `8f0e51f`、platform `82b3e9d7`、Finance `0698265`），本稿未复验。
> 简写：`P/` = `~/Desktop/stocks/bifrost-platform/`（本地 HEAD），`I/` = `~/Desktop/stocks/bifrost-trade-infra/`，`T/` = `I/k8s/cicd/tekton/`，`R/` = `I/scripts/release/`，`F/` = `~/agent-work/bifrost-finance/`，`W56/` = `I/agent-config/work/multi-agent/PLAN-w56-unattended-prod-2026-10-10.md`。本稿新增证据见 §1.6；未刷新的第二稿行号沿用历史快照，实施前须重新定位。

## 0. 这份文档回答什么、要你定什么

D2 A 的承诺是：同一个应用串行，不同应用并行，只有共用的东西才互斥。第 1 稿把锁挂在一份 5 分钟的租约上。复核指出，这扛不住几种情况：平台挂掉；run 已经结束而 Argo 还在同步；一次授权被拿去启动另一份输入；只改共用底座的提交；还没接进来的侧门。

第 2 稿换了一个根：**锁挂在一次持久的「发布操作」上**。一个操作的输入（逐仓提交、参数、资源集合）在建立时定死，并且只能被一个代次执行。锁一直占着，直到这件部署真正结束：核对过、观察过、必要时回滚完。租约只用来判断执行方还活着。各应用之间什么时候真正开始并行，按应用逐个开：一个应用的每个副作用入口都接进来、验收过，才打开它的并发开关；在那之前，它的操作照旧按全局互斥走，也就是今天的并发 1。

第 3 稿补上这个模型的执行条件：**换代次不等于旧副作用已失效**。接管必须完成目标端屏障并排空旧执行，之后才能恢复；计划绑定完整 CI/STG/产物证据；迁移先暂停受控发布、排空旧 run、替换旧判定，再切权威。上述「并发 1」只适用于受控入口，不约束 Owner 裸管理员命令。目标不变：同应用串行、不同应用并行、仅共用可变资源互斥；满足证据和恢复条件的小型 PROD 改动无人值守且失败自动回滚。

文档回答：
- §1：现状，按复核改正过的事实。
- §2：操作模型、登记表、锁与调度、副作用入口表、推即部署、和 4.1 的衔接、发版策略、冻结、迁移、审计、失败模式、Console、与 W-56 的对照、ADR 怎么改。
- §3：存放位置的选项。
- §4：切片与验收。每一条复核意见都落成一条「只有它能拦住的用例」。

**你要定的**在 §5。复核 B 项涉及的新增选择单列在「待 Owner 定」：替代写入器的执行边界、迁移切换方式。下文给推荐方案的完整合同以便复核，不将推荐视为已批准；CI/STG 证据等既有安全责任不因选项改变而省略。

## 1. 现状实读（按复核 532 改正）

### 1.1 窗口本身

| 部件 | 位置 | 实读 |
|---|---|---|
| 数据 | `P/api/internal/delivery/release_window.go:18-19`、`window_store.go:46-55` | ConfigMap `cicd/bifrost-release-window`，只有一个键 `window.json` |
| 写 | `P/api/internal/server/server.go:520-521`、`window_handler.go:28-98` | PUT 本身在 create / update 冲突时会重试（`window_store.go:108-179`）。但**同一个 who 再写就算续期，并且能把 what 换掉**（`:145-163`）。409 拒绝不写审计（`window_handler.go:49-61`） |
| 删（已修） | `P/api/internal/delivery/window_store.go:190-247` | TD-430（`7fe719fa`）已给 GET 清理和显式 DELETE 加上 resourceVersion / UID 前提，GET 冲突后重读。第二稿所述无前提删除是旧快照问题，不能再计为本计划待修项；新权威的 GET 改纯读属于模型迁移 |
| 判定（三份） | Go `release_window.go:22,30`；Python `R/window_decision.py:12,28`；Tekton `T/task-release-window.yaml:39,55` | 三份都写死了 Trade 的仓库名。漂移检查只比对 Python 和 Tekton 这两份（`I/scripts/check-release-chain.py:137,148`）。三份的语义也不同：Tekton 只比 what（`:128`），Go 的 API 还比 who（`release_window.go:172-181`） |
| 持有者身份 | `R/release.sh:746,772` | **默认** `who=${USER}@$(hostname -s)`，可以用 `BIFROST_RELEASE_WHO` 或 `--who` 覆盖。不覆盖时，同一台机器上的会话是同一个 who。历史上是否真有同机重叠，审计分不出来 |

### 1.2 入口（改正处标「正」）

| # | 入口 | 现状 |
|---|---|---|
| 1 | `release.sh`（Trade） | 开窗口（`R/release.sh:809-817`）。另有一把全局忙碌锁：任何 `bifrost-deliver-*` 在跑，或 2 分钟内新建过，就拒绝（`R/release_tool.py:91-111`，在 `release.sh:831` 调用） |
| 2 | `release.sh hold` | 只开窗口（`:743-765`） |
| 3 | `push-main.sh` | 「有任何窗口」就拒推（`R/push-main.sh:182-189,273,558`）。不比 what，也不比 who |
| 4 | Tekton 窗口任务 | research `T/pipeline-deliver-research.yaml:76`、dagster `:46`、market-data `:48`、ib-gateway `:42`、flex-query（兄弟仓库）`k8s/cicd/pipeline-build.yaml:30`（正：第 1 稿写的是 :27）。只比 what |
| 5 | Trade / platform 的四条 deliver | 只有冻结检查（`T/pipeline-deliver-stg.yaml:42` 等）。Trade 的 prepare guard 按 STG / PROD 分组，只看 Trade 自己（`T/task-prepare-deliver-stg.yaml:23-33`） |
| 6 | 审批单执行（正） | 执行器不会自己开窗口。Trade 和 platform 的 deliver 在没有窗口时放行（`release_window.go:146-153`）。动作本身接受 who（`actions/catalog.go:90`，转发在 `actions_wire.go:248`），Trade 的 PROD 单由 `release.sh:554` 写入 who。**实测近 14 天：deliver-platform-prod 的 56 张单里 35 张没有 who，deliver-prod 的 8 张都有。** research deliver 属于必须持窗的表（`release_window.go:23`），没有窗口会被拒；这 14 天里没有 research 的 PROD 单。「missing who」这种拒绝不在暂时性拒绝的前缀里（`actions_wire.go:442-446`），不会重试。另据我读到的 10-23 审计，有 4 次 platform PROD run 在无人持窗时建立（16:44:11、16:49:23、17:01:34、23:28:00 UTC）；复核没能复验 |
| 7 | Argo | `bifrost-platform-prod` 读 infra main 的 `k8s/overlays/platform-prod`，自动同步并开着 selfHeal（`I/k8s/cicd/applications/bifrost-platform-prod.yaml:13-22`）。这个 overlay 引入 `../../base-platform`（`I/k8s/overlays/platform-prod/kustomization.yaml:8`），后者又引入 `manifest.yaml`（`I/k8s/base-platform/kustomization.yaml:13`）。`bifrost-research` 递归读 `k8s/`，**排除 `orchestration/**`**（`bifrost-research.yaml:23`），自动同步但不 prune。另有 `gitops_sync_app`、`gitops_rollback_app` 两个动作（`actions/catalog.go:173-188`，接线在 `actions_wire.go:278-290`） |
| 8 | 插件、Dagster 部署（正） | 插件：Owner 在终端里 `kubectl apply` 加 rollout（`I/agent-config/claude/auto-mode/release-permissions.json:2-5`）。Dagster：只有构建（`T/pipeline-build-research-dagster.yaml:3-6`），部署走 `apply_manifest`（research-release skill 第 4 步） |
| 9 | Finance | CI 流水线的源码在 `F/ci/pipeline.yaml`，平台不认它是 CI（`P/api/internal/delivery/ci_run.go:11-17`）。发 STG 由 Owner 运行 `F/deploy/owner-release.sh` → `release.py`：开共享窗口 → 只查一次冻结（`:303`）→ 用 Owner 的 kubectl 给 Application 打带 resourceVersion 的 patch（`:302-360`） |
| 10 | 迁移 Job（正，新增） | platform PROD 的 agentrt 迁移是 Owner 跑的 Job，deliver 只核对迁移是否已应用（`T/pipeline-deliver-platform-prod.yaml:526-533`，TD-411）；STG 的迁移在 deliver-platform 里跑（`T/pipeline-deliver-platform.yaml:143-148`）。Trade 的 `db-init-{stg,prod}`、research 的 `k8s/jobs/ddl-apply.yaml`（手工 `kubectl create`）、market-data 的 `k8s/migrate/job-wave8-schema-migrate.yaml`，都在 deliver 之外 |
| 11 | 其他写动作 | `apply_manifest`（`catalog.go:397`）、`rollout_restart_deployment`、`owner_run_command`（`:451`，参数只有 command、reason、runner，没有应用或资源范围） |

**流水线清单（历史快照）**：第二稿 10-24 的 `get_delivery_pipelines`（04:47Z）记录 19 条，本稿未查询集群，不作为当前固定数量：
- infra 里 17 条（`T/pipeline-*.yaml` 16 个文件，加 `T/apply-manifest/pipeline.yaml`）；
- flex-query 1 条（在兄弟仓库）；
- `bifrost-ci-finance` 1 条（`F/ci/pipeline.yaml`）。

按类别分：
- 发布类 12 条：build-* 7 条（flex-query、frontend-stg、ib-gateway、market-data、research-dagster、research-pine、stg），deliver-* 5 条（platform、platform-prod、prod、research、stg）；
- CI 4 条：ci-platform、ci-frontend、ci-python（按仓库分派）、ci-finance；
- 共享写 1 条：apply-manifest；
- 测试 2 条：smoke、clone-frontend-smoke。

### 1.3 实测数字

- **10-24 的运行态快照**：没有窗口；`cicd/bifrost-release-policy` 是空壳（DATA 0），没有任何签过的策略，所以当时不会自动批准；冻结是 `false`；信任锚已经编进平台（`P/api/internal/releasepolicy/anchor.go:14`）。不据此判断今天可发布。
- **近 14 天的审批单**：起算条件是 `created_at ≥ 2026-10-10T04:47Z`，窗口内最早一张是 10-10 05:04Z。共 161 张（盘点的 174 张起算更早）。`start_pipeline_run` 64 张，其中 platform-prod 56、deliver-prod 8；`owner_run_command` 88 张，其中 Finance 76 张。Finance 这 76 张里约 11 张是跑 CI，其余多是恢复演练、探针、安装。10-23（CDT）一天 55 张。
- **审计**（10-23 03:25Z – 10-24 04:46Z，作者读取）：持有 55 次、释放 24 次。Finance 的持有和 platform 的持有交错发生在 19:02:53 到 19:05:03 之间。
- 以上数字都由作者读取，复核没有复验。

### 1.4 应用、仓库、共用资源（改正：platform 的迁移、渲染依赖、Dagster）

| 应用 | 仓库（及路径） | 部署 | 自有库 / 迁移入口 | 共用 |
|---|---|---|---|---|
| platform | `bifrost-platform`；infra 中由 `k8s/overlays/platform-{stg,prod}` 渲染所用到的全部文件，包括 `k8s/base-platform/**` | Argo 自动同步 + 流水线钉摘要（3.4） | `bifrost_platform{,_stg,_dev}`：STG 的迁移在 deliver 里，PROD 的迁移是 Owner 的 Job | ui |
| trade | core / api / worker / frontend；infra 中 `k8s/overlays/{dev,stg,prod}` 的渲染闭包（含 `k8s/base/**`），以及 `scripts/release/db-steps.d/**` | 流水线重建 + 手动 Argo | `bifrost_{dev,stg,prod}`：db-init Job | ui；GS（ops_feedback、raw_broker）；redis-ib |
| research | `bifrost-research`；`k8s/` 去掉排除项之后的部分；`k8s/orchestration/**` 单独算一个目标 | Argo 自动同步；Dagster 走 `apply_manifest` | ddl-apply Job | GS |
| market-data | plugin-market-data | Owner apply | wave 迁移 Job | GS |
| flex-query | plugin-flex-query | Owner apply | `schema/ddl.py`（具体写哪些 schema 没核实） | GS |
| ib-gateway | bifrost-platform-plugin | Owner apply | — | redis-ib |
| finance | bifrost-finance | Owner 脚本 patch Argo 应用 | `finance_*`（发布脚本拒绝自动执行 DDL：`F/deploy/release.py:162`） | Postgres 集群 |
| ui（组件） | bifrost-ui | 不部署 | — | — |

不属于任何应用、但会影响所有发布的东西，统一记成资源 `cicd`：
- `k8s/cicd/**`；
- 信任路径（`I/agent-config/release-policy/paths.json:140-146` 所列的 `agent-config/release-policy/**`、`agent-config/scripts/agent-guard/**`、`agent-config/claude/auto-mode/**`、`scripts/release/release.sh` 等）。

`k8s/data/**`（唯一的 CNPG 集群）记成资源 `pg-cluster`。

### 1.5 问题（不变，表述收紧）

1. **跨应用互相等**：窗口、`deliver-busy`、push-main 三处都是全局的。
2. **同一个应用挡不严**：
   - 默认身份在同机会话之间相同；
   - Tekton 不比 who；
   - 审批单执行在没有窗口时直接放行。
3. **推即部署的路径**（包括 platform 的共用底座）只靠 push-main 的全局检查。
4. **侧门**：迁移 Job、插件 apply、手动同步 / 回退、`owner_run_command` 都不经窗口。
5. **应用知识写死在平台里**；拒绝不进审计。

### 1.6 第三稿新增源码核对（571 B1/B2/B3、C1/C2/C3、N2）

| 事实 | 当前源码证据与设计缺口 |
|---|---|
| 真正的 Argo 写点 | `T/task-argocd-pin-sync-platform.yaml:206-244` 先读再普通 merge patch 两项摘要，sync 用 `HEAD`，无代次或 resourceVersion 前提；`I/k8s/cicd/applications/bifrost-platform-prod.yaml:15-22` 仍跟踪 main 且自动同步。现有代码不能提供 §2.1.1 的接管保证 |
| 旧绿能盖住新红 | `R/ci_gate.py:63-77`、`P/api/internal/delivery/release_policy_facts.go:296-302`、`T/pipeline-deliver-platform-prod.yaml:209-223` 都偏向任一次成功，不是最新尝试成功 |
| PROD 已复用 STG 摘要，但 CI 输入对未闭合 | `T/pipeline-deliver-platform-prod.yaml:481-510` 先只按 platform SHA 判 CI，再核对 STG platform/ui 与 rollout 两项摘要；不能把 P+U1 的旧绿用于 P+U2。不得再称 platform PROD 仍重建 |
| 构建依赖不只 Pipeline 外壳 | `T/pipeline-deliver-platform.yaml:84-119` 从 ConfigMap 拷 Dockerfile，`:123-148` 引外部 Task；同文件 `:21-23`、`pipeline-deliver-stg.yaml:22-24`、`pipeline-ci-platform.yaml:43-45` 的 uiRevision 仍可为 main。新协议须解析固定 SHA 并验证实际 Task / 镜像 / 文件内容 |
| 旧任务不能识别权威代次 | `T/task-release-window.yaml:128,139` 只比 what 交集并读旧 ConfigMap；镜像残留可放行晚启动的旧 run，`*` 不能补这个洞 |
| 身份接线有部署顺序 | `P/api/internal/delivery/service.go:1498-1524` 按已安装 Pipeline 声明附加特定任务的 `tekton-deliver` 身份；`I/k8s/platform-rbac/40-admission.yaml:121-154` 是固定任务白名单，尚无车道任务。新 Task 必须配 API、RBAC、准入共同验收 |
| 冻结不是加标签即可 | `I/k8s/release-freeze/admission.yaml:13-18` 禁 UPDATE、CREATE 带标签等元数据；`crd.yaml:25-44` 尚无 scope。旧 `T/task-release-freeze-check.yaml:301-333` 只读冻结并拒绝，无恢复认领入口 |

## 2. 设计

### 2.1 发布操作：锁挂在它上面（A1、A2）

**操作记录**放在车道对象里（§3），字段：
- `id`：平台发号，形如 `op-<12hex>`。
- `protocol`：1 = 旧窗口适配，2 = 新协议。
- `gen`：代次，从 1 开始，每次接管加一。
- `holder`：`{kind: session|runtime|approval|owner|supervisor, ref, who}`。
- `lease_until`。
- `plan`：建立后不能改。内容如下：
  - `apps[]`、`env`；
  - `revisions{repo: 40 位 SHA}`；
  - `steps[]`：每一步的类型、流水线名或动作、规范化参数哈希、实际解析的 Pipeline/Task 规格与执行输入清单哈希（§2.7.1）；
  - `targets[]`；
  - `resources{res: s|x}`：已经规范化；
  - `registry{ver, hash}`：只取本次涉及的应用子集；
  - `authority`：审批单号，或策略 id 加命中的条款，或「STG 自动」；
  - `candidate`：PROD 晋升或复用产物的部署必填不可变发布记录 id/UID/hash、CI/STG run UID、逐仓实际克隆 SHA、镜像仓库与摘要、配置完整 SHA；构建操作建立时只固定批准输入和来源 SHA，产物在执行后写入不可变结果回执，再由记录器生成供后续晋升使用的候选记录，不能事后改计划输入；
  - `evidence`：证据 id/hash、取得及失效时间、规则/构建输入清单版本与哈希、实际规格哈希；
  - `expected_current_release`：当前部署基线的记录与配置 SHA、目标 UID、摘要组合；
  - `recovery`：PROD 必填，回滚到哪一条发布记录、它的摘要、配置所在的提交、期限、谁有权回滚。
- `steps[k]`：`{run_name, state: pending|claimed|running|done|failed|uncertain, gen}`。同一个操作同一时刻最多只有一步处在 claimed 或 running。
- `phase`：`active` → `verifying` → `observing` → 终态。另有非终态：`orphaned`（租约过期，等人接管）、`taking_over`（接管屏障未完成）、`uncertain`（结果不明）、`stuck`（超过总期限）。

**终态有四种，只有它们释放锁**：
- `succeeded`：最后一步做完，核对和观察都通过。
- `rolled_back`：回滚这一步做完，并核对过。
- `stopped_clean`：要么还没有任何副作用步被认领过，要么每个副作用都已核对收敛。
- `abandoned`：计划建立了，但第一次认领之前就过期或撤回。

**占用规则：只要操作不在终态，就占着计划里的全部车道和资源，不管租约过没过期。**
- 租约过期只把操作标成 `orphaned`。
- 平台和 workers 重启不改变占用。
- 运行时的发布记录器跳过不成功的 run（`P/api/internal/releases/service.go:165`），所以操作的跟踪不能依赖它，要由操作的驱动方自己读 run、Argo 的 operationState 和 Pod。
- run 的终态不等于操作的终态。pin-sync 超时的时候，Application 可能已经钉上新摘要、正在同步（`T/task-argocd-pin-sync-platform.yaml:251-256`）。这时那一步记成 `uncertain`，等核对到 Argo 收敛之后再定。

**期限**：
- 租约每分钟续一次，单次续期最长 60 分钟（给 Owner 手工步骤这类场景）。
- 操作有总期限，写在应用策略里，默认 STG 2 小时、PROD 3 小时。到期进入 `stuck`：锁照旧占着，冻结这个应用，通知你。**到期的操作不会被当成不存在。**

**接管**：
- 能接管的有：同一会话的新进程、运行时的新尝试、平台 workers、W-56 的监督器、Owner（应急）。
- 接管先 CAS `gen+1`、换持有者，阶段为 `taking_over`，仍占全部锁。它只授予建立执行屏障和核对现场的权利；§2.1.1 的屏障未完成，不能发候选或恢复副作用。
- 旧代次的续租、认领、写终态被拒；已通过车道任务的 run 还可能继续，必须由最终执行边界拒绝其写入，或确认它已停止且结果收敛。不能把前置任务当成最终 fencing。

**一次授权只对应一个确定的操作**（沿用 `W56/:92` 的一次性消费）：
- 认领一步 = CAS 把这一步从 pending 改成 claimed，写下 run 名和代次。
- run 名由操作号和步号确定地得出（`<pipeline>-<op短号>-<k>`），同名的第二次创建被 apiserver 拒绝。重试时取回已有的那条 run，不会再起一条。
- 创建超时 → 这一步记成 `uncertain`，按 run 名去查。

**车道任务核对什么**（Tekton 正常发布；放在普通冻结检查之后、第一个副作用之前；身份按 S2a/S3a 安装并验收为 `tekton-deliver`。恢复用 §2.8 的独立窄入口，不经过普通冻结任务）：
1. 读自己的 PipelineRun：名字、`spec.params`、代次注解。
2. 读车道对象，逐项核对：
   - 操作存在且不在终态；
   - 代次一致；
   - 自己就是当前 claimed 的那一步；
   - 参数的规范化哈希等于计划里这一步的哈希；
   - 计划里的修订等于自己要克隆的修订。
   - PipelineRun/TaskRun UID 与计划绑定，已解析 Pipeline、每个 Task、执行镜像摘要、Dockerfile 内容与批准清单相符；尚未解析的 Task 在调度执行前再验，不允许验证后换定义。
3. 按冻结协议 §3.3「先写自己的、再读对方的」，完整 LIST 冻结记录；正常发布有冻结即撤回未发出的认领。

任何一项不符就拒绝。S2a 的创建准入必须拒绝未绑定操作的发布 run，不能仅假设手工 run 一定用 default。读权限失败同样拒绝。首个任务通过只证明入口检查通过；每个副作用仍受下面的最终合同约束。

### 2.1.1 最终执行边界与接管屏障（571 B1；推荐方案，待 Owner 定 11）

**共同合同**：每个写请求绑定 `{op, gen, step, claim_id, kind, target UID, candidate/recovery record hash, image repos+digests, config SHA, expected_current_release, deadline}`。`kind` 只允许登记的晋升或恢复；恢复不能携带任意目标。平台和监督器使用同一合同，但监督器不依赖待恢复的 API/worker。计划、身份和证据的最终重验见 §2.7.1。

推荐将 Argo 写权限收至独立的窄执行器；Pipeline、平台动作和监督器提交受约束的意图，不能直接 patch Application。**它不能仅在客户端读 gen 再 patch**：目标端保存单调的执行序号（操作 seq、gen、step）及该次允许的意图哈希；apiserver 以目标对象的 resourceVersion/UID 条件更新，准入限制写者、序号不得倒退、字段只可匹配所装载意图。普通调用者无权安装序号或意图。这是执行屏障的目标端副本，授权仍只有车道对象一份；无匹配认领的副本不能授权任何操作。

目标端意图在副作用的同一次条件写里记为已消费；准入不允许同一序号重新装载意图或清掉消费回执。执行器冲突后不能拿新 resourceVersion 盲重试旧意图，必须重新核对车道认领；已消费的请求只返回已有结果。这样 Argo 操作结束后，也不能重放同一认领再同步一次。S3a 必须测量旧身份无直接写权限、同序号重放拒绝，而不是只部署一个新服务名。

| 副作用 | 最后执行处、强制方 | 接管后能继续的条件 |
|---|---|---|
| Argo 晋升 / 恢复 / 手动 sync / rollback | 窄执行器重验后，以目标 UID/resourceVersion 和执行序号条件，一次写两项摘要、`spec.source.targetRevision=<40位配置SHA>` 与 `operation.sync.revision=<同一SHA>`；apiserver 的条件写和准入强制。禁 `HEAD`、main 和任意历史 revision。等待还核对意图/操作标识、同步 SHA、所有 Deployment/Pod 摘要及探针 | 先 CAS 提升每个目标的执行序号，旧请求若晚到会冲突或被准入拒绝；若旧请求先落地，新方读回实际结果，终止或等旧 Argo operation 收敛并核对，才装载恢复意图。不能只看 initiatedBy，也不能只请求取消就当作停止 |
| 镜像构建 / push | 受控构建步骤验证实际输入；产物仓库固定、tag 带 op/step、部署只按摘要。registry 的无条件 push 不能用车道 gen 撤销 | 旧构建进程和上传结束、摘要核对后才判该步收敛；接管期间不重用 tag，也不以标签代表候选。旧上传结果不能替换计划的摘要 |
| Job、apply、重启、缩放 | 创建/变更的最终 API 边界按操作和目标限制，Job 记录确定名称及 UID，准入/RBAC 禁不经此边界的受控写者；Task 前置检查不覆盖 Job 内部 SQL | 已发的 Job 及其 Pod/数据库事务必须证明结束或停止；创建超时先按名称/UID查。取消 Job 不等于 SQL 已停止，不能据此发相反迁移或恢复 |
| 推即部署、Owner shell | Git 受控推送带确定旧 head 条件；Owner 脚本登记命令/进程与目标。普通 shell、任意 SQL 不承诺可被远端 gen 撤销 | 未确认旧进程及已发请求收敛即 `uncertain`，持锁、冻结并人工处理；无可验证停止机制的步骤不得进入无人值守恢复范围 |

**接管次序**：① CAS 进入 `taking_over`，封住旧方的新认领；② 逐目标提升执行屏障并持久化结果，任一失败保持持锁；③ 枚举已登记 run/TaskRun/Argo operation/Job UID，阻断旧方再次写入，确认所有旧副作用停止或收敛；④ 记录核对结果，才允许当前 gen 认领恢复或继续。权威 CAS 和目标 CAS 不是跨对象事务：两者之间旧写可能先成功，必须按③处理，不能宣告已恢复。响应丢失不重发盲写，按目标序号和意图哈希查询；目标被重建（UID 变）或发现未登记写者就拒绝。

目标端屏障只挡未来请求，不撤销已接收的 Argo 操作、Pod、SQL 或 shell。恢复成功的定义是：旧写者不会再落地，且**登记的配置 SHA + 全部镜像摘要组合**已收敛并核对。配置 main 后续移动不影响它；配置不兼容同样须转人工。S3 各类入口必须证明其边界，S5c/S5d 演练「车道任务已通过后暂停 → 接管/恢复 → 旧任务醒来」的两种先后次序。无法满足就保持 `uncertain`，不以安全接管记终态。

### 2.2 应用登记表（B3、A3）

**字段**：`id`、`parallel`（并发开关，默认 false）、`repos[{repo, paths}]`、`targets[]`、`pipelines[]`、`uses[{resource, mode}]`、`migrations[{paths, jobs, db}]`、`images[]`、`policy`。其中：
- `targets[]` 的每一项是 `{name, env, deploy: pipeline|argo-auto|argo-manual|apply|owner-apply, render: {tool: kustomize|directory, root, exclude}}`；
- `pipelines[]` 的每一项是 `{name, env, class: release|ci|shared|test}`。

**路径归属看真实的渲染依赖，不看目录前缀**：
- kustomize 目标：平台从 root 出发，沿 `resources`、`components`、`patches`、生成器引用的文件，一路闭包到本地文件。遇到远程引用，就按 `*` 处理。
- directory 目标：root 递归，去掉 exclude。
- CI 里对照 `kustomize build`，证明闭包没有漏文件。

**受保护路径优先**：`paths.json` 中 `no_trust_anchor_change` 和 `no_d10_paths` 列的路径，归资源 `cicd`（独占），不会被任何「文档」规则豁免。只有受保护路径之外、渲染闭包之外的 `*.md` 才算不部署。

**读写语义**：
- 一个应用的普通发布，对它 `uses` 里的每个库拿共享锁（待定 3）。
- 计划里含有这个库的迁移路径或迁移 Job，就拿独占锁。
- 一次迁移涉及两个库，就在一次获取里同时拿两个独占锁。

**变更怎么审、怎么生效**：
- 登记表本身算信任路径：加进 `no_trust_anchor_change`，所以带登记表改动的发布永远不会自动放行，并且要独立复核。
- CI 做语义校验：
  - 集群流水线清单里的每一条都有类别，发布类的都有应用；
  - 每个 `no_ddl` 路径都有库归属；
  - 每个自动同步的目标都有 render；
  - 每个镜像名只属于一个应用；
  - 文档豁免不遮住受保护路径；
  - 资源名来自一张固定的词表。
- 操作在建立时把用到的资源写成明确的名字，所以登记表换版以后，在途的操作照旧持有原来那几把锁。资源**改名或删除**要等持有旧名字的操作全部结束，CI 会标出这类改动。

### 2.3 锁与调度（A7）

**资源**：
- `lane:<app>`（只有独占）；
- `db:<库>`；
- `ui` 仅为备选资源，是否存在取决于 §5 第 9 项点名的共享可变副作用；固定源码 SHA 本身不需要锁；
- `cicd`；
- `pg-cluster`；
- `redis-ib`；
- `*`（全局）。

**规范化**：同一个资源同时出现 s 和 x，取 x。`*` 和一切冲突。每个操作都拿 `cicd` 和 `pg-cluster` 的共享锁（待定 4）。

**获取**：车道、资源和步骤认领在一次 CAS 里完成，要么全拿到，要么全拿不到。不会留下半把锁，也不会死锁。

**排队顺位**：
- 一个请求被拒时，登记一条等待：`{seq, op, resources, until}`。`seq` 在车道对象里单调递增，同一个操作重试时保留原来的 seq。
- 一个请求能被批，当且仅当：没有和它冲突的持有者，**并且**没有和它冲突、seq 比它小的等待。
- 一个请求不会挡住它自己；后来的请求挡不住先来的。
- 等待在 `until` 之前没有刷新就清掉；操作进入终态时，它的等待也一并清掉。

这保证等待图不因顺位形成循环；只有在冲突持有者最终经恢复或人工处置进入终态时，先到的等待才有进展保证。总期限会转 `stuck` 并继续持锁，不能推出无条件不饿死或有界等待。交叉例子（A 要 X 独占加 Y 共享，B 要 X 共享加 Y 独占）在持有者收敛的前提下按 seq 依次放行；长期 stuck 要告警和人工处置，不能为可用性释放未收敛的锁。

**容量**：同时活动的操作最多约 8 个（应用数），每分钟各续租一次，再加上等待的刷新，每分钟十几次写。这个量用一个对象做 CAS 就够。

**STG 和 PROD 用同一条车道**：同一个应用的 STG 发布和 PROD 发布不并行。STG 做完到 PROD 开始之间不持锁，因为 PROD 钉的是 STG 克隆的提交。

### 2.4 副作用入口表与并发开关（A4）

| # | 入口 | 副作用 | 接法 | 负责切片 |
|---|---|---|---|---|
| 1 | 全部 build 流水线 | 推镜像 | 操作的一步，前面加车道任务，最终副作用受 §2.1.1 约束 | S3b 逐族 |
| 2 | 全部 deliver 流水线 | 部署 | 同上；平台执行的审批单由平台建立操作（持有者 = 审批单） | S3b 逐族 |
| 3 | 推 main 时改到渲染闭包 | 经 Argo 部署 | §2.5 推即部署操作 | S3d；S4 才开并发 |
| 4 | `gitops_sync_app`、`gitops_rollback_app`（任何环境） | 换目标版本 | 对登记过的应用，必须是某个操作的一步 | S3c 逐类 |
| 5 | `apply_manifest` | 写对象 | 计划里的对象属于登记目标 → 必须是该应用操作的一步；碰 `cicd` / `data` 命名空间 → `cicd` 或 `pg-cluster` 独占 | S1 记影子，S3c 强制 |
| 6 | Dagster（`apply_manifest` 加 `orchestration/dagster.yaml`） | 部署 | research 的目标 `research/dagster`，走第 5 行 | S3c 逐类 |
| 7 | 迁移 Job：agentrt PROD Job、`db-init-*`、`ddl-apply`、market-data wave、迁移类 CronJob 的 `create_job_from_cronjob` | 改库 | 登记在 `migrations[].jobs`；必须在一个持有 `db:<库>` 独占锁的操作内创建 | S3c 逐类 |
| 8 | `owner_run_command` | 任意 | 新增可选参数 `op`（已有操作的 id）或 `scope{apps, resources}`。`owner-run.sh` 执行时认领这一步。不带范围的命令包成一个 `*` 独占的维护操作，永远不进自动策略。不靠解析 shell 去猜范围 | S3c 逐类 |
| 9 | 插件的 Owner apply | 部署、改配置 | 平台管不到 Owner 终端里的命令。插件的 `parallel` 保持 false，受控脚本的操作都按 `*` 独占，直到部署改成窄动作或 Argo | S3c 包装、S6 窄化 |
| 10 | 对登记命名空间的 `rollout_restart_deployment`、`delete_pod`、`scale` | 可变 tag 时可能换镜像；会打断观察期 | 这个应用有在途操作时，只允许该操作自己做；用可变 tag 的应用（research、插件、trade），重启算部署，要求操作 | S3c 逐类 |
| 11 | Finance 的 `owner-release.sh` | 部署 | 改用 `--app finance` 的操作，审批单带上 `op`；之后换成窄动作（待定 8） | S3c 包装、S6 窄化 |
| 12 | ci-*、smoke | 不部署 | 类别是 ci / test，不拿车道 | — |
| 13 | Owner 自己终端里的集群管理员命令 | 任意 | 不在防范模型之内（冻结协议 D1）。仓库里的 Owner 脚本改成先调 `release.sh op` 包装 | 文档 |

**并发开关**：一个应用的 `parallel` 只有在上表里属于它的每一行都过了验收之后，才改成 true。改它就是改登记表，要复核。在那之前，经过操作接口的请求一律拿 `*` 独占；这不会给裸 apply 自动补锁。仓库内日常 Owner 脚本必须包装并验收，不能用第 13 行的管理员例外掩盖未迁移路径。因此**跨应用并行是逐个应用打开的**：第一批是 platform 和 trade，research 要等 Dagster 和 ddl-apply 接进来，插件要等第 9 行。

### 2.5 推即部署（A3）

- **什么时候一次推送算部署**：只要推送改到了某个自动同步目标的渲染闭包，它就是一次部署操作，计划里写明目标提交。这个操作有三步：
  1. 推送；
  2. 等同步：Argo 的 `status.sync.revision` 等于目标提交，这个修订的 operationState 是 Succeeded，健康；
  3. 核对。

  锁一直占到这三步走完。同步迟迟不发生、重试、selfHeal，都发生在这个操作的生命周期里；超时进入 `stuck`。
- **一个提交影响几个应用**：在一个操作里一次拿齐所有受影响的车道和资源。
- **冻结和授权一样覆盖它**：推送这一步也要先认领、再 LIST 冻结。
- **无人值守 PROD 的前提**（继承 `W56/:88` 的 E）：目标先做到「只同步到完整提交」，再关掉 `automated`，同步交给操作执行。在那之前，改到 `platform-prod` 或 research `k8s/` 渲染闭包的推送一律算 R2，等你批。
- **没核实**：Gitea 的 main 分支保护能不能只允许经过这道判定的推送者。如果不能，绕开 push-main 和运行时、直接推 Gitea 的路径就还开着，记进 §6。

### 2.6 和 4.1（运行时自动合入后自动发 STG）的衔接

- **同一个判定**：4.1 的合入调用和 push-main 相同的平台判定接口，用同一份渲染闭包、同一张受保护路径表。
- **自动合入排除什么**：渲染闭包碰到 PROD 目标的、碰到受保护路径的，都不进自动合入。一个提交影响几个应用时，按 §2.5 处理。
- **合入后发 STG**：运行时建立一个 STG 操作，持有者是运行时的发布操作，带这次尝试的代次，然后起流水线、核对、写终态。
- **车道被占时**：按 seq 等，上限 30 分钟，到了就交回任务队列。
- **自然攒批**：同一个应用排着几次合入时，下一个 STG 操作发的是 main 的头，一次覆盖。
- 这几条要回写给 `CUT-landing-2026-10-24.md`。

### 2.7 按应用的发版策略（A6）

**结构**：
- 每个应用一份签名策略 `cicd/bifrost-release-policy-<app>`。
- 策略授权的是「操作计划类型」，不是「流水线」（继承 `W56/:148`）。
- 每个计划类型写明：恢复条款、各阶段超时、API 中断上限、观察时长、谁有权回滚。

**STG**：B 级，自动跑。条件：已登记、操作已建立、完整实际输入对应的最新 CI 尝试成功、没冻结；不是任一次旧绿（见 §2.7.1）。

**PROD 无人值守，必须同时满足下面两条**：

**① 风险分类允许**：只有 R0 和 R1 可能放行。
- R0：只改文档或测试。
- R1：只改应用代码，不碰迁移路径或 Job、D10、受保护路径、渲染闭包里的清单、RBAC / Secret / 准入、流水线定义。
- R2：清单、配置、只增的 DDL。
- R3：破坏性 DDL、信任根、凭证，属于 D 级。
- R2 和 R3 照旧找你。

**② 能证明可以自动恢复**（继承 `W56/:130,263` 的未决 4 A）：
- 改动不碰「状态格式路径清单」，每个应用一份，签进策略；
- CI 的契约测试通过：新 API 对上一版的 Console，新版读旧状态、旧版读新状态都不丢字段；
- 逐仓 diff 完整，没有未知路径或未知输入，有基线可比；
- 有一条证明不了就转人工，并且不自动恢复。

`max_changed_files` 和行数都不能代替这一条。

**其他条件照旧**：CI 最近一次是绿的；PROD 钉的正是 STG 核对过的提交和摘要；STG 观察满 M 分钟；没有待办的 DB 步骤；没冻结；策略有效；登记表子集的哈希一致。每一项按 §2.7.1 绑定并在最后执行处重验，不能以已有代码等价满足来跳过 S5a/S5b/S5c。

**恢复**：
- 恢复目标在操作开始前锁定：上一条成功的发布记录、它的摘要、配置所在的提交；对应镜像要有保留标签。
- 回滚是操作自己的独立恢复分支：完成旧写者屏障后，按 §2.1.1 同时钉回登记的配置 SHA 与所有摘要，再核对；不经过普通发布冻结 DAG。
- 还不过，就停下、冻结这个应用、带外通知你。

**独立监督器**（继承 `W56/:139` 第 6 步）：
- 无人值守写入之前，必须确认监督器已经把这次的意图持久化；S5c 人工试发期的值守边界见 §4；
- api 和 workers 同时坏掉时，监督器能直接接管并恢复；
- 应用自己的健康接口、Finance 自己的告警，都不能代替它。

**事后通知**：每次自动上 PROD 推一条；自动回滚推一条高优先级的。都不算进你的决定数。

**W-56 门槛按应用**（第 1 稿的表保留，Finance 一列改正）：
- **platform**：PROD source gate 已核对 STG platform/ui SHA 并复用其摘要；普通 STG/CI 的 uiRevision 仍可为 main，Argo 同步仍是 HEAD。完整证据、最终写入屏障、冻结入口测量和独立监督器均须按 S5 验收，不能写成整条链已钉 SHA。
- **finance**：按摘要部署和回到旧 revision 已经做到（#67 验过）；冻结只查一次；没有独立监督器；它的告警是否可以算作独立检测，复核没法读源码核对，不据此排序。
- **trade、research、插件**：要先改成按摘要部署。

第一个候选是 platform。

### 2.7.1 候选、证据和最终消费合同（571 B2）

**批准清单 → 实际执行 → 发布记录 → 不可变计划 → 最后写入**必须能逐项相互核对，哈希只标识输入，不能替代核对。下列交付物是 S5e 签无人值守策略之前的硬依赖，沿用 `W56/:99-110,118` 的责任：

| 交付物 / 生产方 | 必填和校验 | 消费方 / 切片 |
|---|---|---|
| 受批准构建输入清单 / Owner 签名，infra 管文件 | 固定来源与目标仓库、每个执行及基础镜像摘要、Pipeline 和外部/内联 Task 规格哈希、Dockerfile 字节哈希、构建参数及依赖锁文件；输入变化要重签对应清单，不允许请求指定别的仓库/镜像目标 | API 解析器、Task 启动校验、记录器、最终执行器；S5a |
| 实际执行证明 / 受控构建与 Tekton 状态 | run UID、子 TaskRun UID/owner UID、实际克隆结果、解析后的 Pipeline/TaskSpec、容器实际 imageID、挂载/复制后 Dockerfile 内容与参数。必须在每个 Task 真正运行前比批准清单；使用不可变内容或按摘要解析的快照，ConfigMap 刷新不能改变已核验字节。拒未解析依赖、标签镜像及注入的规格；不能只比较计划和当前集群定义 | 记录器回查 run 本体及 status；S3a 接线、S5a 强制 |
| 不可变候选记录 / PROD 记录器 | 实际 platform/ui（其他应用为完整逐仓元组）SHA、构建与部署 run UID、仓库+摘要、构建输入哈希、配置 SHA、STG 全部工作负载收敛时刻。准入只准可信身份创建，拒更新/删标签/同名替换，Task 状态只由控制器写；旧格式不能参与自动晋升 | API 闸门和最终执行器以 UID 回查，比较批准清单与 registry 摘要/架构；S5a |
| 最新证据 / 唯一发布闸门 | 按下面规则计算，含证据 id/hash、CI/STG UID、基线、规则及清单版本、观察窗口、签发/失效时间。请求只给 record_id/request_id/expected_current_release，不能直接给摘要或旁路布尔值 | `plan.candidate/evidence` 固定引用；S5b |
| 最终重验 / 窄执行器 | 独立读取上述证据与原始来源，校验签名、有效期、当前 gen/step/目标、冻结、意图持久化确认（自动路径必须由独立监督器确认）及当前 PROD 实况等于基线；候选写只取计划的配置 SHA 与摘要。批准后证据过期要重新计算；新证据不改变候选/基线，若输入变了就重新建计划和授权 | Argo 最后条件写；S5c，恢复则按登记恢复合同，不因候选 CI 变红而阻断已授权恢复 |

**CI 判定**：按 `pipelineRef` 及受批准规格识别流水线，标签与本体冲突即拒；按实际 clone 结果及全部构建输入建立键，不按 `revision` 参数的字面。对这一完整输入取最新创建的尝试（时间、UID可核对，顺序有歧义就拒）；最新红就拒，运行中最多等 15 分钟，不能回落旧绿。P+U1 的绿不证明 P+U2；相同 P/U 而 Task/Dockerfile/基础镜像不同也不复用证据。新尝试尚无 clone 结果但可能覆盖本输入时，不能忽略为不匹配，先等待/拒绝。

**STG 判定**：先找该应用最新部署尝试，不论结果；其 UID 必须等于候选记录且终态成功。新尝试运行中、失败、时间缺失/歧义均拒。再核对全部 Deployment 的 observedGeneration、期望副本、所有非终止 Pod 的 Ready 与摘要（platform workers 与 api 同摘要）、配置修订及只读探针。M 默认 10 分钟，期间换版、重启、探针失败重置观察。证据默认 10 分钟有效；最终写前重验，即使未过期也不能忽略 STG 新尝试或 PROD 基线变化。

**保留与信任**：按 run UID 保留原始执行证据；run 清理到无法回查则拒绝并重跑 STG。registry 校验仓库白名单、摘要可拉取、index 与节点架构匹配；当前及上一份成功组合的镜像/配置保留，GC 前校验保留标签。标签检查只是合作方防错，不提供防覆盖保证。记录缺字段、被伪造或和 run/registry 不一致均拒。CI 与 STG 不共用的规格分别与同一批准清单中的对应角色比较，不能要求两种流水线的整个 hash 相等。

证据重验以追加的不可变核对回执表示，写入步骤认领绑定它的哈希，并明确替代哪条已过期证据；不覆写 plan。回执只能重证同一候选、基线和原授权条款，不能延长操作/恢复期限；变化超出这些值就重建计划、重新授权。只有完整重验通过的回执才能被最终写入消费。

S5b 的必拒矩阵包括：旧绿新红（两种列表顺序）、P+U1 绿/P+U2 红、相同 SHA 更换 Task/Dockerfile/镜像、STG 新失败/运行中、观察重置、过期证据、错仓库/错摘要/错配置、run UID 被替换或消失、批准后 PROD 基线变化。S5a–S5d 的退出条件分别完成后才做五次影子对照和签策略；五次本身不能替代这些合同。

### 2.8 冻结协议修订（571 C2）

- **记录仍只增不改、仅 Owner 能删**，但作用域是协议修订，不能直接加标签。推荐扩展 CRD `spec.scope` 为 `global` 或 `app:<登记id>`；无 scope 的旧记录始终按 global，未知 scope、残缺、LIST 不完整或失败均按全局冻结。准入继续拒 UPDATE、任意元数据与非 Owner 删除，并验证新字段；写入、读取和回执的 schema/version 一起升级。选择 scope 形状见 §5 第 10 项。
- **安装顺序（S3a）**：先让已部署的 API、worker、带外监督器、Task 和命令读取器兼容旧记录与新 scope（后续新装读者也必须先过同一兼容测试），旧读者至多把任意 app 冻结当 global；再安装/实测 CRD 与准入；最后才允许创建 app 记录。新客户端对旧 schema 禁写 scope，避免字段被裁掉；新记录存在时回退旧读者仅允许已证明保守的版本，否则停发布。不能删除旧 global 记录来迁移，也不能先启新写者再等读取器更新。
- **正常晋升入口**：普通冻结预检 → CAS 一次性认领 → 完整 LIST → 匹配冻结即撤回未发出的认领 → §2.1.1 最终执行检查。冻结方先创建记录，再读取认领并写回执；认领先过切点的已发步骤可收敛核对，回执必须覆盖它。冻结阻断随后晋升，不将已发步骤当成已撤销。
- **恢复入口**：由当前操作/监督器调用独立的恢复窄动作（不接到普通 freeze-check DAG 后面）。先确认旧副作用屏障完成，CAS 取得一次 `kind=recovery` 认领；比对当前 gen、op、登记目标 UID/配置 SHA/摘要、恢复期限和授权；完整读取冻结以记录回执，再由执行器及目标端约束做最后检查。global/app 冻结都不阻断这一已授权的有界恢复；读取失败不发写、保持 uncertain。没有 `ignore_freeze` 通用参数，不能新建发布来冒充恢复。
- **期限与重试**：恢复认领与计划期限逐项相等，执行器和监督器检查当前时间；过期拒绝，不能续期扩大授权。同一 claim_id 的网络重试只查询/续接原副作用，不创建第二次恢复。换目标、换 op、旧 gen、复用已消费认领均拒绝。恢复后核对失败则冻结/告警，不第三次自动写。
- **验收**：无 scope/未知 scope/分页失败/新旧读取器矩阵；冻结落下后候选失败，监督器仍恢复登记组合且冻结不被删除；同操作换目标、换配置、过期认领拒绝；恢复后旧执行者醒来仍被目标屏障拒绝。以上都过后，按应用冻结才可在 S4 启用。

### 2.9 兼容迁移（A5、B2）

| 阶段 | 做什么 | 保证 |
|---|---|---|
| M0（S1） | 影子判定、登记表、拒绝审计；保留 TD-430 删除条件保护并回归 | 影子不改变授权，失败不影响旧调用；不重算已修的删除竞态 |
| M1（S2a → S2b） | 先装兼容读者/身份/准入，再暂停受控发布、排空旧运行，切到单一车道权威（下述屏障）。旧 PUT/DELETE/GET 是适配层；protocol 1/2 均拿 `*`；不再让旧镜像参与授权 | 兼容 Task 直接读同一权威，验证绑定的 run UID 与操作；旧客户端可通过新版 API 适配，旧二进制直读 ConfigMap 的执行路径关闭 |
| M2（S3a–S3e） | 分族迁移 protocol 2，push-main/运行时在 S3d 接入，S3e 排空并删除三份旧判定表 | 保持所有应用 `parallel=false`。§2.4 每行有迁移归属；未迁移的受控入口使用 S2 的全局兼容操作或拒绝，不能无锁放行 |
| M3（S4 起） | 单独逐应用打开 `parallel` | S3e 退出且该应用全部日常路径验收后才开 |
| M4（S7） | 旧接口回 410，旧 ConfigMap 保留不可用墓碑（仅诊断，不授权） | 无旧定义在途 run、无旧对象授权读者、连续 7 天无 protocol 1（提前须 Owner 明示并保留全部排空证明） |

**M1 切换屏障（571 B3；推荐停发排空方案，待 Owner 定 12）**：
1. S2a 先安装兼容能力但不启用新权威。列出所有发布/构建/部署/迁移入口和运行 UID，连同 Owner 脚本、已批准未执行的单、已创建未运行的 Task 一起记录；CI/test 只读路径可继续。
2. S2b 进入持久维护态：API/审批执行/脚本暂停新副作用，创建准入拒未绑定新协议的发布 run（包括直接创建、内联规格及旧已批准单）。排空旧 run、子 TaskRun/Pod、Argo operation、Job/命令及响应不明请求；已终态 run 仍有同步也不能算排空。不能可靠认领的旧运行不按 who/what 猜归属，保持维护态人工核对。
3. 在所有旧执行者排空、创建入口封住之后，安装到**全部发布族**的兼容任务或保持该族禁用：直接读车道权威、精确绑定 op/gen/step/run UID，缺失拒绝；不能继续读镜像。API 只向已安装并验过身份/规格的族创建 run。然后旧 ConfigMap 写墓碑并验证不可放行；失败不退出维护态。
4. CAS 标记权威切换完成，再开放兼容调用。旧 `PUT --what` 建立 protocol 1 的全局操作，who 只是展示值；新版适配器为 run 预分配名称并在创建后绑定 UID，同 who 不能把已开始操作的 what 换掉。旧 DELETE 只提出结束请求，先封住新认领，再确认登记的全部副作用收敛后终态；TTL 仅 orphaned。无 run 绑定能力的旧客户端收到明确拒绝，不回落镜像。

**迁移失败/恢复矩阵**：

| 情况 | 必须的结果 |
|---|---|
| 旧 Research run 在切换前创建、Task 晚启动 | 它属于排空集合；不允许在它尚能执行时激活新 Platform 操作。已取消 run 的子 Pod/请求仍要核对；切换后再试旧定义被创建/执行准入拒绝 |
| 权威已选 Platform、旧镜像还显示 Research | 新授权入口绝不读镜像；若发现仍有这样的读者，切换未达标，保持维护态。不得用「权威只有一把 `*`」证明安全 |
| 墓碑/兼容写失败、旧镜像仍可放行 | 不授权下一操作的副作用，不等续租重试期间放行；修复、重读验证、重跑旧运行清点后才开放 |
| DELETE/TTL 与旧 run 晚启动竞争 | DELETE 不能释放未收敛操作，TTL 不释放；未归属运行使迁移屏障保持关闭，强制清除也不能伪造收敛证据 |
| 切换中 API/worker 重启、旧客户端或旧 API 实例回归 | 从持久维护态恢复，先复查排空及已安装能力；旧 API 无新创建/写入权限，不得访问旧镜像继续执行 |
| 必须临时保留镜像的替代方案 | 只有 Owner 选择 §5 的替代方案并独立证明后可用：旧运行全绑定且排空、镜像更新成功并核验之前不开放副作用，失写立即封住后继操作。第二稿的异步镜像方案作废 |

**回退**：
1. 停止接受新的认领（权威里的一个开关）；
2. 让在途操作走到终态；接管本身不算排空，要完成 §2.1.1 屏障和核对；
3. 把各应用的 `parallel` 改回 false。

不在多个操作还在写的时候直接切回旧的单窗口。
回退服务版本只退到支持同一权威及兼容任务的版本。回到 M0 必须重新维护停发、排空所有副作用、实测旧入口约束后由 Owner 决定；不能删除车道状态或移除新准入来让旧程序恢复运行。

### 2.10 审计

- **操作和锁**：`delivery.op.<动作>` 和 `delivery.lane.<动作>`。动作包括建立、认领、续租、接管、终态、拒绝、等待、强制。记录带上操作 id、代次、资源、持有者、计划的哈希。
- **每次 PROD**：发布记录里加上应用、授权来源、风险等级和「可恢复证明」的结论、核对、回滚。保留不少于 90 天。
- **每周统计**：每个应用发了几次、几次自动、几次找你、等锁一共多久、各资源挡了几次、几次落到 `*`。

### 2.11 失败模式

| 情况 | 唯一的结果 |
|---|---|
| research 持有 GS 独占时，平台和 workers 都停了，等过了租约期 | 操作变成 `orphaned`，GS 的独占锁照旧占着，market-data 拿不到；由监督器或重启后的 workers 用 `gen+1` 接管 |
| run 已失败或成功，但 Argo 还在同步 | 那一步记成 `uncertain`，锁照旧占着，直到 Argo 收敛并核对过 |
| 同一个操作被重试启动两次 | 确定的 run 名让第二次创建得到 AlreadyExists，取回已有的那条 |
| 拿到操作以后改了 revision 或参数再起 run | 车道任务比对计划哈希，拒绝 |
| 被接管之后，旧执行者又醒过来 | 新认领被拒；已通过前置任务的写请求在目标屏障被拒。屏障前已经接收的副作用必须先收敛，未确认则 uncertain，不发并行恢复 |
| 冻结刚落下时，旧持有者还持着有效的锁 | 正常晋升下一次认领在 LIST 冻结处撤回；已发步骤核对；有界恢复走独立窄入口，仍只允许登记目标 |
| 两个请求交叉要 s / x | 按 seq 先后放行 |
| 登记表漏了一个文件 | 渲染闭包的 CI 对照会发现；在那之前这个文件不属于任何应用，按 `*` 处理 |
| 有人用 kubectl 直接起 run | 读不到自己的 run，或者没有操作，拒绝 |
| 自动回滚也失败 | 停下，冻结这个应用，带外通知，不做第三次写 |
| 平台自己的修复发布 | 走带外操作面或监督器；你可以用自己的凭证 CAS 写操作（应急，写审计） |

### 2.12 你在 Console 上看到什么（只做数据和接口，样子留给 Design 专轮）

- **每个应用一行**：
  - 在途的操作：阶段、第几步、代次、已用多久、预计还要多久；
  - 等待的人（按 seq 排）；
  - `parallel` 开没开；
  - 上一次 PROD 及其授权来源、有没有回滚；
  - 策略到期日；
  - 冻结（全局 / 应用）。
- **每个资源一行**。
- **For you 里只出**：策略之外的 PROD；`stuck` 或 `orphaned` 超过 15 分钟；回滚失败；策略快到期。
- 现在读窗口的卡片（`P/console/src/pages/shell/owner/useOwnerConsole.ts:43,84`）改成读操作列表。

### 2.13 与 W-56 旧设计逐项对照（B5）

**单一权威**：车道对象里的操作记录，**取代** W-56 第 4 步设想的「代次对象」。`op.gen` 就是代次，不另建第二套租约。

**谁能写操作**：PROD 平台（api 和 workers 共用 `Update` CAS）、W-56 的监督器（自己的身份，只能做「接管」和「写恢复结果」）、Owner（应急）。STG 平台不写。

| W-56 项 | 处理 |
|---|---|
| 第 1 步 A 写入矩阵测量 | 继承：一个应用打开无人值守之前，它目标的写入矩阵测量要通过 |
| B 故障即拒的冻结任务 | 正常发布继承；恢复走 §2.8 独立窄入口，不排在普通冻结任务后面；S3a 修协议兼容，S5c 演练 |
| C 收紧谁能写冻结和窗口 | 继承，换对象：resourceNames 改成车道对象的名字 |
| D 一次性批准、封住 run 的绕路 | 继承并推广到所有应用：用确定的 run 名加计划哈希实现（§2.1） |
| E 同步到完整提交，再关自动同步 | 继承：这是推即部署的目标打开无人值守的前提 |
| F 封住对 PROD 工作负载的直接修改 | 继承，按应用的目标命名空间做 |
| 冻结的串行边界（`W56/:90`） | 继承，改成冻结协议的「先写自己的、再读对方的」 |
| 解冻的签名 | 已由冻结协议替代（Owner 删记录）；scope 涉及 schema/准入/读写者/旧记录兼容，见 §2.8，S3a |
| 第 2 步 可信的发布记录 | 完整继承 §2.7.1 批准清单、记录/run UID/registry 四方比对；候选和 recovery 都引用；S5a 独立退出 |
| 第 3 步 闸门先影子、再强制 | 完整输入的最新 CI、STG 最新尝试和实况、观察重置、有效期由 S5b 交付；影子五次在合同完成之后 |
| 第 4 步 `promote_platform_prod` 动作 | S5c，输入只接记录与基线，执行器最终重验，不从请求提供的仓库版本加载判定代码 |
| 第 4 步 写入器（推摘要提交到 Git） | **待 Owner 定 11 的是实现替换**：遵守 D3 A 的 Argo 钉摘要方向，保留最终授权/证据/代次/冻结/基线/完整配置 SHA 的全部责任；不能以作废 Git 写入器取消这些责任 |
| 第 5 步 有界撤回、恢复条款 | §2.1.1/§2.8；S5c 人工授权试发并核对完整配置+摘要组合及旧执行排空 |
| 第 6 步 带外监督器 | S5d 独立持久意图、接管屏障、冻结下恢复和失败通知；不只授予 gen 写权限 |
| 第 7 步 规则授权的是动作 | 继承 |
| 未决 4 A 可自动恢复的判据 | 继承（§2.7 ②） |
| ADR §12.7 并发为 1 | 被 D2 A 替代（§2.15） |

### 2.14 两次事故

- **09-27 两个会话同时发 core 0.24.0**：两个会话发同一个应用，第一个的操作还没到终态，第二个的建立请求排在后面。同机也分得开，因为持有者是操作，不是 user@host。
- **09-28 market-data 0.61.0 的 tag 被覆盖**：同一个插件有在途操作，另一次 `rev=main` 的构建不属于这个操作，被车道任务拒绝；插件在 `parallel=false` 期间还拿着 `*`。
- **tag 检查的定位**（改正）：「推送前查 tag 是否已存在」只是防合作方误用的补充措施。registry 不鉴权、写入不带条件，所以它不能保证 tag 不被覆盖。真正的保证是两条：按摘要部署；每个操作的产物名唯一（tag 里带操作号）。这道检查放在受控的构建步骤里、同一个操作之内执行。

### 2.15 ADR 和代码里要一起改的地方（C4）

**ADR**：
- §12.7（`ADR-ops-architecture.md:303-308`）的第一条子项改成：
  - 发布操作和应用车道：权威在平台，放在 cicd 的一个状态对象里；
  - 同一个应用并发为 1，不同应用在各自的入口都接入之后并行；
  - 共用资源按读写锁互斥；
  - 锁一直占到操作进入终态；
  - 拒绝按冲突关系排先来先到，24 小时过期。
- §12.3（`:256`）：「发布窗口和队列」改成「发布操作与车道」，仍然不迁 PG。
- §5（`:90`）：「持有发布窗口」改成「持有绑定本次计划的发布操作」，发版策略按应用签。
- §12.10（`:353`）：W-56 一行加上「按应用判」。

**代码里所有的全局并发点，都要迁到操作上**：
- 模板 `limits.concurrency`（引擎并不执行它，只在 `template.json` 和 `rptest` 里出现）；
- 引擎条款 `window_held_by_requester`（`P/api/internal/releasepolicy/engine.go:332-339`，事实来源 `delivery/release_policy_facts.go:309-321`），改成 `op_bound`；
- `deliver-busy`（`R/release_tool.py:91`）；
- prepare guard（`T/task-prepare-deliver-stg.yaml:23`）；
- push-main 的 `window()`；
- `release.sh` 的 `window_open`；
- Go 和 Python 的 decide；
- Tekton 的窗口任务；
- 暂时性拒绝的前缀（`actions_wire.go:442`）；
- Console 的卡片；
- Finance 的 `release_window()`（`F/deploy/release.py:167-202`）。

**文档**：RELEASE.md、工作区 CLAUDE.md §5、Cursor 的 `workspace.mdc`（两侧的 parity-id 都要 bump）。

**协议版本**（C3）：
- protocol 1 = `--what` 和 `/release-window`，永远拿 `*`，不把仓库名翻译成应用；
- protocol 2 = `--app` 和 `/lanes`。
- 同一条命令在不同切片里的语义不变。

## 3. 架构选项：操作和车道放哪（B1）

**A1（推荐）**：用 platform 现成的 `k8sstate.Backend`，在 `cicd` 命名空间里只开一个键 `release-lanes`，即 ConfigMap `cicd/platform-state-release-lanes`。
- 怎么用：
  - `k8sstate.New` 本来就接受命名空间参数（`P/api/internal/statefile/k8sstate/k8sstate.go:43`）；
  - 写只用 `Update`：冲突后重读、重跑 mutate，最多 5 次（`:118-135`）；
  - 不能用 `Write`：它是用旧字节重试的「最后写入者胜」（`:6,78`），加一条测试禁止对这个键调用它；
  - PROD 平台写，Tekton 直接读同一个对象，不给 STG 建第二份，也不做镜像。
- 好处：原子的多锁获取天然成立；平台挂了也能读；符合 ADR §12.3「不依赖 PG / Redis」；有现成的 CAS 实现。
- 代价：
  - 历史只在审计里；
  - 单个对象有大小上限：在途操作、等待、计划哈希加起来是几十 KB 量级，终态的操作只保留最近 N 条，其余写进审计；
  - TD-293 关闭之前，平台身份和 `tekton-deliver` 都能改这个对象，防的是合作方误用；
  - 存储独立不等于执行独立：续租和接管靠 workers 与监督器，这一点 W-56 第 6 步仍然要做。

**A2**：第 1 稿的 A，同样是 `cicd` 里的一个对象，但手写 CAS。拓扑和 A1 一样，只是不复用现成代码，没有理由选它。

**C**：agentrt 库。现成有租约和 fencing（`0001_core.sql:177`），也有历史。但违反 ADR §12.3：修 PG 的那一次发布会拿不到锁。不推荐。

（第 1 稿的 B「平台 statefile 加镜像」，被 A1 取代：A1 就是不带镜像的 B。）

## 4. 切片与验收

**顺序**：S1 → S2a → S2b → S3a → S3b（逐族）→ S3c（逐类）→ S3d → S3e → S4。S5a → S5b → S5c → S5d → S5e 是无人值守的独立依赖链；S5a/b 可提前开发，但不能提前签策略。S6 逐应用，S7 最后。

**S1–S3e 全程 `parallel=false`**。每个子片独立部署、复核和验收；未接入入口只能在 S2 兼容合同下全局串行，或明确禁用。每片产出能力清单 `{API protocol, Pipeline/Task spec hash, SA, admission version, entry enabled}`；运行时按实装能力判断，不按客户端自报版本放行。涉及 PROD、准入/凭证的安装仍按现行 Owner 授权执行，本设计不提前授权。

| 切片 | 工作与独立退出条件 | 混合版本及回退边界 |
|---|---|---|
| S1 影子与登记表 | 一份 Go 纯判定：渲染闭包、资源规范化、seq、拒绝审计。合成测试含 base-platform、双库迁移、交叉 s/x、重复启动；stuck 持锁的等待不能被判成必有进展。保留 TD-430 回归。用实施当天机器清单逐条对照登记表，不断言固定 19 条；历史缺拒绝/会话/资源，只作辅助 | 旧平台/Task 不变；新平台影子超时不影响旧授权。回退影子无状态迁移 |
| S2a 兼容能力先装 | 新平台支持持久操作、确定 run 名/UID 绑定、旧 API 适配和能力协商；公共兼容 Task 直接读同一权威。先装读取 RBAC、精确任务 SA 准入白名单，再上能识别已安装任务的 API，最后旁路安装带版本的新任务/流水线定义但不接入生产 DAG、不切权威；S2b 屏障内才替换调用。每族逐条验证读 run/权威成功、default/未绑定/内联冒充拒绝；不将 tekton-deliver 授给所有 Task | 保持 M0 旧权威。新客户端遇旧平台拒绝 protocol 2；新 API 不给不存在的任务填 taskRunSpecs。未装完的族仍旧协议或停用，不尝试运行新 Task。回退新能力前不启用 M1 |
| S2b 停发、排空、权威切换 | 执行 §2.9 四步屏障及全部失败矩阵；兼容守卫覆盖每个可开放的发布族，或该族保持禁用。PUT/DELETE/TTL、同机争用、1000 次并发 CAS 回归、失联持锁均验收；复现 Research 旧 run 晚启动和镜像失写反例，必须不能与 Platform 新副作用重叠 | 旧客户端只经新版适配 API；旧平台、旧执行 Task 和直读镜像脚本不得执行。回退只能停发排空后恢复兼容权威版本，不能直接恢复旧 ConfigMap 授权 |
| S3a 公共 protocol 2 / 冻结 / 执行边界 | 给新任务、动作、恢复入口做版本协商；实现 §2.1.1 通用意图与目标屏障合同，先不开自动恢复。按 §2.8 升级读取器、schema、准入，旧 scope=global 回归；验证 scope 写入不被裁剪。发布物顺序仍是 RBAC/准入兼容 → API → 新 Task；必须现场验证身份/拒绝矩阵 | protocol 1 仍经兼容守卫，全局串行；未宣称支持协议的 Task/动作拒绝 protocol 2。scope 读者没齐不启新写者；回退只到能保守读新记录的版本 |
| S3b 逐流水线族 | 每族一片：platform STG/PROD、trade build/deliver、research、Dagster build、各插件 build，审批创建同步接入。各族逐 Task 校验实际规格和输入、run UID、最后副作用边界；测试已过车道检查再暂停的旧任务、创建响应丢失、run 终态但 Argo 未终态。无新边界的族维持兼容/禁用，不删除旧判定表 | 新 API+兼容任务走 protocol 1；新 API+新 Task 才走 protocol 2；旧 API+新 Task 拒绝。每族回退先停新认领并排空，再回兼容定义，状态和屏障不回退 |
| S3c 逐非 Tekton 类别 | 每类一片：Argo sync/rollback；apply（含 Dagster）；迁移 Job/CronJob；Owner 命令；重启/删 Pod/scale；Finance 脚本包装。覆盖 §2.4 第 4–11 行。每类测正常、错目标、未绑定、接管中、已发请求不明；GS 迁移互斥；普通命令不可撤销时保持 uncertain。Finance/插件若未窄化部署仍 `*` | 旧客户端只能用全局兼容维护操作，不支持可靠登记/排空则拒绝。回退包装前停用对应入口，不能移除强制再放旧脚本 |
| S3d push-main / 4.1 运行时 | 提前到 S4 之前：共用渲染判定，推送→等完整 SHA 同步→核对，仓库日常 Owner 脚本接入。测 base-platform 单改、跨应用原子取锁、信任路径不能文档豁免、推完未同步仍持锁；核对受控推送身份和分支保护，未知旁路阻止并发开放 | 旧 push-main 只能在兼容维护操作中用，无法绑定全生命周期就拒绝；新客户端遇旧 API 不回落本地判定。回退运行时自动合入需先停并排空，不能恢复裸推 |
| S3e 旧调用排空与三表退役 | 入口机器清单零未归属，S3b/c/d 每族证据齐；无旧定义在途 run/命令/Argo 操作、无旧镜像授权读者，再删除三份硬编码表。protocol 1 适配仍可保留，但只能映射全局操作，不能带旧判定。S7 才删 API | 各中间版本的测试必须重跑；回退至兼容单权威版本，不能退到三表独立授权 |
| S4 单独开放并发 | platform、trade 各一片：全部受控入口和仓库 Owner 脚本已验收，登记表签名与 scope 冻结通过，才改该应用 parallel。测同应用 STG/PROD 串行、platform/trade STG 同时运行、共享库迁移仍互斥 | 出问题先停新认领、排空后设 false；不把持锁 TTL 当回退完成。未开放应用继续 `*` |

**贯穿 S2–S3 的通过矩阵**（每片用实装组合重跑）：

| 客户端 / 平台 / 执行端 | 结果 |
|---|---|
| 旧 / 旧 / 旧 | 只准 M0 既有受控路径；M1 切换后封住 |
| 旧 / 新 / 兼容 Task 或兼容维护入口 | protocol 1，精确绑定 run/命令，`*`；不认识的入口拒绝 |
| 新 / 旧 / 任意 | 明确不支持 protocol 2，无副作用、无镜像回落 |
| 新 / 新 / 旧 Task | 拒绝新执行；M1 不得留下可执行的旧 Task，不能因 API 先升级就放行 |
| 新 / 新 / 兼容 Task | 只有显式选择 protocol 1 的全局操作可用，不能把 protocol 2 偷降级 |
| 新 / 新 / 已验证的新 Task/动作 | protocol 2，S4 前仍 `*`；SA、准入、规格任一不匹配即拒 |
| 旧平台实例或未绑定者直接创建新 run | 创建/执行准入拒绝；不能靠默认 SA 假设保证 |

**S5：platform PROD 无人值守，先交付再放权**

| 子片 | W-56 责任、生产方/消费方 | 必须独立通过的退出条件 |
|---|---|---|
| S5a 可信记录和构建输入 | W-56 第 2 步；infra 构建与准入、PROD 记录器 → API 闸门与最终执行器，§2.7.1 | 三次 STG 完整记录；批准清单↔记录↔run UID↔registry 四方机器比对；伪记录/改 status/换 Task/Dockerfile/错仓库拒绝；当前及恢复组合可按摘要拉取，GC 演练通过 |
| S5b 完整闸门 | W-56 第 3 步；唯一引擎 → 不可变计划与执行器 | §2.7.1 全部反例矩阵通过，实际输入元组最新 CI、STG 最新尝试/实况/观察重置、证据有效期和基线变化均有独立预期。未知状态格式、双向状态/Console 契约失败必须转人工 |
| S5c 最终写入及有界恢复 | W-56 第 4、5 步，§2.1.1/§2.8；依赖对应目标的第 1 步 A–F 测量、完整 SHA 同步且关闭自动同步，Owner 定 11 | 先人工授权试发：执行器重验全部证据及基线；车道通过后暂停、目标写前暂停、写后响应丢失、Argo 部分完成分别接管，旧方先/后到两序都验。main 移动仍只恢复登记配置 SHA+摘要；冻结后失败可恢复，错目标/过期拒绝。未完成屏障的 Job/shell 必须 uncertain，不能假成功 |
| S5d 独立监督器 | W-56 第 6 步；独立身份直接读写受限目标，不依赖 API/worker | 意图持久化确认缺失不写；同时停 API+worker 仍能完成屏障与恢复。监督器在写前/写后/核对中重启、接管后旧任务醒来、结论冲突、集群不可读、恢复超时/失败全部演练；冲突或不可判只冻结告警，不第三次写 |
| S5e 影子对照、强制和签策略 | W-56 第 7 步；依赖 S5a–d 各自退出及独立复核 | 新路径五次人工授权真实发布均完成独立核对，闸门至少五次影子对照且最近三次无差异；重跑 W-56 写入矩阵、冻结、证据、恢复用例，量出各段超时及 API 中断。再强制闸门并由 Owner 签策略；第一次合规 R1 无人点击上 PROD、失败按登记组合自动回滚且发事后通知 |

S5c 先验人工授权路径：每次明确登记 Owner 带外值守、应急恢复通道和已持久化的意图回执；不得把还未交付的监督器写成已确认。人工值守不能满足自动入口。S5d 上线后，由独立监督器提供确认，并重跑 S5c 相同故障矩阵；S5e 才能验无人值守。五次不能代替反例矩阵或监督器实测。S5a–d 未退出前照旧逐次批准；本稿只完成设计，不申请这些动作。

**S6：Finance 和插件的部署改由平台执行**（待定 8）
- 做什么：
  - Finance 用 `pin_argo_app`；
  - 每个插件列出它的配置、Deployment、迁移、探针、回滚目标，分别迁移；
  - 各自过了验收以后打开 `parallel`。
- 要你：定待定 8，签各自的策略。

**S7：旧接口退役**
- 前提：§2.4 每一行都已接入，S3e 排空证明仍有效，连续 7 天无 protocol 1（缩短须 Owner 明示）。
- 做什么：旧接口回 410，验证旧 ConfigMap 墓碑不能放行；文档、ADR 和 parity 一起改。退役回退仍只能恢复兼容单权威适配层。

## 5. 待定点（附选择的代价）

| # | 待定 | 选项与代价 | 推荐 |
|---|---|---|---|
| 1 | 存放 | A1：复用 k8sstate，单对象；对象大小要控制，历史在审计里。C：违反 §12.3 | A1 |
| 2 | 登记表的签名范围 | 整表哈希：给 Finance 加一项，所有应用的策略都对不上，全部停止自动放行，要全量重签。按应用的规范化子集（本应用的条目加它引用的共享规则）：只影响相关的应用，但实现要定义规范化；不签名不可取（B3） | 按应用的子集 |
| 3 | 普通使用共用库时要不要拿共享锁 | 拿：迁移要等所有用这个库的应用的发布结束，迁移期间它们也发不了；不会有代码部署到一个正在变的 schema 上。不拿：迁移和别的应用的部署可以交错，破坏性迁移虽然是 D 级，只增的迁移也可能和旧代码交错 | 拿 |
| 4 | 每个操作都拿 `cicd` / `pg-cluster` 的共享锁 | 拿：改共享任务或集群要等在途的发布结束。直接改集群的 SQL 没有 Git diff，也要显式声明 `pg-cluster` 独占 | 拿 |
| 5 | 「小改动」的口径 | 风险分类和可恢复证明分开判，两条都要过；行数上限不能代替证明 | 两条都要，不设行数上限 |
| 6 | 第一个无人值守的应用、M | platform，M = 10 分钟；前提是监督器、恢复权限、冻结切点都验收过。Finance 的就绪程度不据它自己的告警来排 | platform |
| 7 | 队列 | 不做完整队列，只用 seq 顺位：等待记录要维护，但没有互相锁死。做完整队列：多一套出队和过期的逻辑 | seq 顺位 |
| 8 | Finance、插件由平台执行部署 | `pin_argo_app` 适合 Finance。插件目前没有 Argo 应用，要逐个列出配置、Deployment、迁移、探针、回滚目标，每个插件一片。不做：它们的 `parallel` 永远是 false | 做，先 Finance |
| 9 | ui 的范围 | A：新协议解析并固定 ui SHA、校验实际 clone 后，不为纯 Git 源码推送加锁。B：若另有可覆盖的共用包/tag/cache 发布，则只对那个点名资源设共享/独占；当前没有核实这样的副作用。当前普通 STG/CI 仍可传 main，不能宣称已经全部钉住 | A；先完成输入固定，不凭源码依赖设置跨应用互斥 |
| 10 | 冻结的作用域表示 | A：CRD 可选 spec.scope，旧记录 global，沿用不许元数据的准入；需读写者兼容部署。B：受限制的 scope 标签，需要放开并严格校验这一个标签，旧 schema 风险不同。两者都要完整 LIST 和旧读者保守性测试 | A，按 §2.8 修订协议 |
| 11 | W-56 替代写入器 | 见下方待 Owner 定，替换实现而不是删责任 | A |
| 12 | M1 切换屏障 | 见下方待 Owner 定；异步镜像授权方案作废 | A |

### 待 Owner 定（571 的 B 项）

- **11 / B1：最后副作用在哪里被强制约束。** A（推荐）：独立窄 Argo 执行器 + 目标端单调序号/条件写/准入，平台和 Task 不再直写，按 §2.1.1 排空在途副作用；成本是执行器身份、准入和监督器接线要专门测量。B：不建新目标屏障，但每次接管先停用并撤销旧执行权限、证明所有旧进程/请求和 Argo 操作排空，之后才恢复；实现较少，无法证实排空时必须人工，可能无法达到小改动无人值守目标。两项都保留完整配置 SHA、CI/STG 最终重验、冻结下有界恢复；不重新讨论已定 D3 A 的 Argo 钉摘要方向。
- **12 / B3：切权威是否接受一次停发。** A（推荐）：§2.9 的停发排空、兼容守卫替换、墓碑核验后重开，代价是维护窗口。B：保留临时镜像桥，但每个旧 run 先绑定、所有写入者受控，镜像读回成功且旧运行排空后才准后继副作用；失写关闭整个迁移入口，成本是额外跨对象状态机和故障演练。B 不是异步重试时继续放行。

**B2 不增设弱化证据的选项**：最新完整输入 CI、最新 STG 尝试、可信记录、最终重验是 W-56 已有责任，已落到 S5a–c；M/证据有效期按现有默认值起步，最终随策略由 Owner 签。以上待定不妨碍交付本设计修订；实施相应新边界前才需要决策。

## 6. 回归核对与未核实项（571 N）

**532 已补内容的保留检查（N1）**：本稿不能因新增接管/证据/迁移合同而回退以下约束。实施每片复核时逐组核对：

| 532 项 | 本稿保留位置与新增验收 |
|---|---|
| A1/A2 生命周期、一次授权 | §2.1、§2.1.1：TTL 不释放、终态需收敛、确定 run 名和 UID、计划固定；S2b 与 S5c 的旧执行者反例 |
| A3/A4 渲染闭包和侧门 | §2.2、§2.4–2.6：闭包、受保护路径优先、多应用一次拿齐、迁移/Dagster/重启/Owner 包装；S3d 先于 S4 |
| A5/A6 迁移和可恢复性 | §2.9 的无镜像授权屏障；§2.7/2.7.1 的状态契约与完整证据、§2.8 有界恢复；S5a–e 不能合成一次上线 |
| A7、B1/B3 存储、登记和顺位 | §2.2/2.3/§3：登记表信任输入、固定资源词表、改名排空、通用 cicd 锁；专用 k8sstate 仅 Update CAS；等待进展以前持有者收敛为条件 |
| B2/B4/B5 切片、选择和 W-56 | §4 逐片兼容与回退；§5 有代价的选择；§2.13 将 W-56 各条接到生产方、消费方和退出条件 |
| C1–C5 与四项事实收紧 | platform STG 迁移/PROD 只查的归属；流水线数量为快照、按类别实时盘点；protocol 1 永远全局；§2.15 全局并发点逐一迁移；tag 查重不提供防覆盖；who/审批统计不过度推断，删除竞态已修 |

**N2 的证据边界**：本稿新增源码事实集中在 §1.6，基线是页首本地 HEAD；TD-430 已核对提交和当前条件删除，k8sstate 的重读 mutate 见 `P/api/internal/statefile/k8sstate/k8sstate.go:123-155`，Owner 命令仍只有 command/reason/runner 见 `P/api/internal/actions/catalog.go:461-466`。不把源码声明视为集群准入已经生效；流水线清单必须在实施时重新采集。

**N3 的承诺边界**：顺位没有循环不等于 stuck 持有者会自动消失；parallel=false 不约束裸管理员命令。两项已在 §2.3/§2.4 改正文，并作为 S1/S3d/S4 的验收条件，不以脚注例外替代日常脚本接入。

**未核实**：

- flex-query 写哪些 GS schema。
- Gitea 的 main 分支保护能不能只放行经过判定的推送者。
- 同机两个会话真正重叠持窗的历史实例。
- 审批单和审计的数字由作者读取，复核没有复验。
- `owner-run.sh` 的内部：复核被 preflight 拦住，本稿也没有读，只按动作目录设计「执行时认领」。
- 当前集群流水线/身份/准入版本、冻结运行态和新协议的任何实测结果；本次只改设计，S2–S5 的反例演练尚未执行。
