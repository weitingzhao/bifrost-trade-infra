# 4.3 每个应用自己的发布节奏：发布操作、应用车道与按应用的发版策略（设计稿，2026-10-24）

> 状态：**第 2 稿**，回应 Codex 复核 532（「先改」）；逐条回应在 `~/agent-work/codex-review-532/RESPONSE.md`。第 4 轮 4.3（W-31；Owner 2026-10-23 23:3x「D2 A」），含 W-56 剩下的门槛。
> 依据：infra main `8f0e51f`，platform main `82b3e9d7`，Finance 检出 `~/agent-work/bifrost-finance`（Gitea `bifrost/bifrost-finance`，`0698265`）。只读实测时间 2026-10-24 04:4x UTC。
> 简写：`P/` = `bifrost-platform/`（读 `origin/main`），`I/` = `bifrost-trade-infra/`，`T/` = `I/k8s/cicd/tekton/`，`R/` = `I/scripts/release/`，`F/` = `~/agent-work/bifrost-finance/`，`W56/` = `I/agent-config/work/multi-agent/PLAN-w56-unattended-prod-2026-10-10.md`。

## 0. 这份文档回答什么、要你定什么

D2 A 的承诺是：同一个应用串行，不同应用并行，只有共用的东西才互斥。第 1 稿把锁挂在一份 5 分钟的租约上。复核指出，这扛不住几种情况：平台挂掉；run 已经结束而 Argo 还在同步；一次授权被拿去启动另一份输入；只改共用底座的提交；还没接进来的侧门。

第 2 稿换了一个根：**锁挂在一次持久的「发布操作」上**。一个操作的输入（逐仓提交、参数、资源集合）在建立时定死，并且只能被一个代次执行。锁一直占着，直到这件部署真正结束：核对过、观察过、必要时回滚完。租约只用来判断执行方还活着。各应用之间什么时候真正开始并行，按应用逐个开：一个应用的每个副作用入口都接进来、验收过，才打开它的并发开关；在那之前，它的操作照旧按全局互斥走，也就是今天的并发 1。

文档回答：
- §1：现状，按复核改正过的事实。
- §2：操作模型、登记表、锁与调度、副作用入口表、推即部署、和 4.1 的衔接、发版策略、冻结、迁移、审计、失败模式、Console、与 W-56 的对照、ADR 怎么改。
- §3：存放位置的选项。
- §4：切片与验收。每一条复核意见都落成一条「只有它能拦住的用例」。

**你要定的**在 §5（11 项，每项写明了选择的代价）。最要紧的四项：存放位置（推荐 A，实现上复用 k8sstate）；登记表的签名范围；普通使用共用库时要不要拿共享锁；W-56 第 4 步的「写入器」是否按 3.4 的 Argo 钉摘要路线作废。

## 1. 现状实读（按复核 532 改正）

### 1.1 窗口本身

| 部件 | 位置 | 实读 |
|---|---|---|
| 数据 | `P/api/internal/delivery/release_window.go:18-19`、`window_store.go:46-55` | ConfigMap `cicd/bifrost-release-window`，只有一个键 `window.json` |
| 写 | `P/api/internal/server/server.go:520-521`、`window_handler.go:28-98` | PUT 本身在 create / update 冲突时会重试（`window_store.go:108-179`）。但**同一个 who 再写就算续期，并且能把 what 换掉**（`:145-163`）。409 拒绝不写审计（`window_handler.go:49-61`） |
| 删 | `window_store.go:183-197`、`:199-216` | GET 读到过期的窗口会删掉它（`:193`），显式 DELETE 也删（`:211`），两处都用空的 DeleteOptions、不带前提。于是可能出现：GET 读到旧的过期值 → 新持有者 Update 成功 → GET 把新窗口删掉 |
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

**流水线清单**：集群里有 19 条（`get_delivery_pipelines`，04:47Z）：
- infra 里 17 条（`T/pipeline-*.yaml` 16 个文件，加 `T/apply-manifest/pipeline.yaml`）；
- flex-query 1 条（在兄弟仓库）；
- `bifrost-ci-finance` 1 条（`F/ci/pipeline.yaml`）。

按类别分：
- 发布类 12 条：build-* 7 条（flex-query、frontend-stg、ib-gateway、market-data、research-dagster、research-pine、stg），deliver-* 5 条（platform、platform-prod、prod、research、stg）；
- CI 4 条：ci-platform、ci-frontend、ci-python（按仓库分派）、ci-finance；
- 共享写 1 条：apply-manifest；
- 测试 2 条：smoke、clone-frontend-smoke。

### 1.3 实测数字

- **现在的状态**：没有窗口；`cicd/bifrost-release-policy` 是空壳（DATA 0），没有任何签过的策略，所以什么都不会自动批准；冻结是 `false`；信任锚已经编进平台（`P/api/internal/releasepolicy/anchor.go:14`）。
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
  - `steps[]`：每一步的类型、流水线名或动作、规范化参数的哈希、流水线 spec 的哈希；
  - `targets[]`；
  - `resources{res: s|x}`：已经规范化；
  - `registry{ver, hash}`：只取本次涉及的应用子集；
  - `authority`：审批单号，或策略 id 加命中的条款，或「STG 自动」；
  - `recovery`：PROD 必填，回滚到哪一条发布记录、它的摘要、配置所在的提交、期限、谁有权回滚。
- `steps[k]`：`{run_name, state: pending|claimed|running|done|failed|uncertain, gen}`。同一个操作同一时刻最多只有一步处在 claimed 或 running。
- `phase`：`active` → `verifying` → `observing` → 终态。另有三种非终态：`orphaned`（租约过期，等人接管）、`uncertain`（结果不明）、`stuck`（超过总期限）。

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
- 接管 = 对操作做一次 CAS：`gen+1`、换持有者。接管方先核对现场（在跑的 run、Argo、Pod 摘要），再决定继续、回滚还是停下。
- 旧代次的续租、认领、写终态都因为代次不符而被拒；带着旧代次注解的 run 被车道任务拒绝。

**一次授权只对应一个确定的操作**（沿用 `W56/:92` 的一次性消费）：
- 认领一步 = CAS 把这一步从 pending 改成 claimed，写下 run 名和代次。
- run 名由操作号和步号确定地得出（`<pipeline>-<op短号>-<k>`），同名的第二次创建被 apiserver 拒绝。重试时取回已有的那条 run，不会再起一条。
- 创建超时 → 这一步记成 `uncertain`，按 run 名去查。

**车道任务核对什么**（Tekton；放在冻结检查之后、第一个副作用之前；跑在 `tekton-deliver` 身份下，和 W-56 护栏 ② 的 check-source 同一个身份）：
1. 读自己的 PipelineRun：名字、`spec.params`、代次注解。
2. 读车道对象，逐项核对：
   - 操作存在且不在终态；
   - 代次一致；
   - 自己就是当前 claimed 的那一步；
   - 参数的规范化哈希等于计划里这一步的哈希；
   - 计划里的修订等于自己要克隆的修订。
3. 按冻结协议 §3.3「先写自己的、再读对方的」，LIST 冻结记录。

任何一项不符就拒绝。不经平台创建的 run 跑在 `default` 身份下，读不到自己的 run，按故障即拒处理。

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
- `ui`；
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

这就是按冲突关系排的先来先到：seq 最小的那个等待只会被持有者挡住，而持有者都有总期限，所以不会互相锁死，也不会饿死。复核举的交叉例子（A 要 X 独占加 Y 共享，B 要 X 共享加 Y 独占）按 seq 依次放行。

**容量**：同时活动的操作最多约 8 个（应用数），每分钟各续租一次，再加上等待的刷新，每分钟十几次写。这个量用一个对象做 CAS 就够。

**STG 和 PROD 用同一条车道**：同一个应用的 STG 发布和 PROD 发布不并行。STG 做完到 PROD 开始之间不持锁，因为 PROD 钉的是 STG 克隆的提交。

### 2.4 副作用入口表与并发开关（A4）

| # | 入口 | 副作用 | 接法 | 负责切片 |
|---|---|---|---|---|
| 1 | 全部 build 流水线 | 推镜像 | 操作的一步，前面加车道任务 | S3 |
| 2 | 全部 deliver 流水线 | 部署 | 同上；平台执行的审批单由平台建立操作（持有者 = 审批单） | S3 |
| 3 | 推 main 时改到渲染闭包 | 经 Argo 部署 | §2.5 推即部署操作 | S4 |
| 4 | `gitops_sync_app`、`gitops_rollback_app`（任何环境） | 换目标版本 | 对登记过的应用，必须是某个操作的一步 | S3 |
| 5 | `apply_manifest` | 写对象 | 计划里的对象属于登记目标 → 必须是该应用操作的一步；碰 `cicd` / `data` 命名空间 → `cicd` 或 `pg-cluster` 独占 | S1 记影子，S3 强制 |
| 6 | Dagster（`apply_manifest` 加 `orchestration/dagster.yaml`） | 部署 | research 的目标 `research/dagster`，走第 5 行 | S3 |
| 7 | 迁移 Job：agentrt PROD Job、`db-init-*`、`ddl-apply`、market-data wave、迁移类 CronJob 的 `create_job_from_cronjob` | 改库 | 登记在 `migrations[].jobs`；必须在一个持有 `db:<库>` 独占锁的操作内创建 | S3 |
| 8 | `owner_run_command` | 任意 | 新增可选参数 `op`（已有操作的 id）或 `scope{apps, resources}`。`owner-run.sh` 执行时认领这一步。不带范围的命令包成一个 `*` 独占的维护操作，永远不进自动策略。不靠解析 shell 去猜范围 | S3 |
| 9 | 插件的 Owner apply | 部署、改配置 | 平台管不到 Owner 终端里的命令。插件的 `parallel` 保持 false，它的操作都按 `*` 独占，直到部署改成窄动作或 Argo | S6 |
| 10 | 对登记命名空间的 `rollout_restart_deployment`、`delete_pod`、`scale` | 可变 tag 时可能换镜像；会打断观察期 | 这个应用有在途操作时，只允许该操作自己做；用可变 tag 的应用（research、插件、trade），重启算部署，要求操作 | S3 |
| 11 | Finance 的 `owner-release.sh` | 部署 | 改用 `--app finance` 的操作，审批单带上 `op`；之后换成窄动作（待定 8） | S3、S6 |
| 12 | ci-*、smoke | 不部署 | 类别是 ci / test，不拿车道 | — |
| 13 | Owner 自己终端里的集群管理员命令 | 任意 | 不在防范模型之内（冻结协议 D1）。仓库里的 Owner 脚本改成先调 `release.sh op` 包装 | 文档 |

**并发开关**：一个应用的 `parallel` 只有在上表里属于它的每一行都过了验收之后，才改成 true。改它就是改登记表，要复核。在那之前，这个应用的操作一律拿 `*` 独占。因此**跨应用并行是逐个应用打开的**：第一批是 platform 和 trade，research 要等 Dagster 和 ddl-apply 接进来，插件要等第 9 行。

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

**STG**：B 级，自动跑。条件：已登记、操作已建立、CI 是绿的、没冻结。

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

**其他条件照旧**：CI 最近一次是绿的；PROD 钉的正是 STG 核对过的提交和摘要；STG 观察满 M 分钟；没有待办的 DB 步骤；没冻结；策略有效；登记表子集的哈希一致。

**恢复**：
- 恢复目标在操作开始前锁定：上一条成功的发布记录、它的摘要、配置所在的提交；对应镜像要有保留标签。
- 回滚是操作自己的一步：把应用钉回登记的摘要，再核对。
- 还不过，就停下、冻结这个应用、带外通知你。

**独立监督器**（继承 `W56/:139` 第 6 步）：
- 写入之前，必须确认监督器已经把这次的意图持久化；
- api 和 workers 同时坏掉时，监督器能直接接管并恢复；
- 应用自己的健康接口、Finance 自己的告警，都不能代替它。

**事后通知**：每次自动上 PROD 推一条；自动回滚推一条高优先级的。都不算进你的决定数。

**W-56 门槛按应用**（第 1 稿的表保留，Finance 一列改正）：
- **platform**：钉 SHA、按摘要部署已经做到；冻结入口（TD-293 / 294 / 314）、独立监督器、状态兼容的契约测试还没有。
- **finance**：按摘要部署和回到旧 revision 已经做到（#67 验过）；冻结只查一次；没有独立监督器；它的告警是否可以算作独立检测，复核没法读源码核对，不据此排序。
- **trade、research、插件**：要先改成按摘要部署。

第一个候选是 platform。

### 2.8 冻结（B4 第 9 项）

- **冻结记录**沿用冻结协议：一类只能新建的集群级记录，只有 Owner 能删。新增一个作用域标签：`global` 或 `app:<id>`。
- **某个应用算冻结**，当且仅当：存在一条 global 记录，**或者**存在一条作用域是这个应用的记录。LIST 失败、记录残缺，都按冻结处理。两种冻结同时在时，取更严的结果。
- **切点**（继承冻结协议 §3.3 给 W-56 第 4 步的方向）：
  - 执行方先 CAS 写下步骤认领，再 LIST 冻结，有冻结就撤回认领，什么都不发；
  - 冻结方先建记录，再读出在途的认领，写进回执。
- **冻结之下**：已经认领、已经发出的步骤，走到核对为止；这个操作自己的恢复步骤可以执行，但只能回到 `plan.recovery` 登记的目标。冻结本身不放行任何其他版本。

### 2.9 兼容迁移（A5、B2）

| 阶段 | 做什么 | 保证 |
|---|---|---|
| M0（S1） | 只上影子判定和登记表；拒绝开始写审计；修掉 GET 和 DELETE 不带前提的删除（改成带 resourceVersion，读路径不删） | 行为不变；影子出错不影响原调用（独立的 goroutine，有超时，只写日志） |
| M1（S2） | 车道对象成为**唯一的权威**。旧接口变成适配层：`PUT /release-window` = 建立或续期一个 protocol 1 操作，拿 `*` 独占；DELETE = 结束它（只有持有者能结束，强制要走审批）；GET 从权威推出来。protocol 2 的操作此时**也拿 `*` 独占**，所以权威里同时最多一个操作。旧 ConfigMap 由平台作为派生的镜像来写：先写权威，再写镜像；镜像写失败，就在续租循环里重试 | 对旧读者的保证**和今天完全一样**，不更强也不更弱：旧 Tekton 任务仍然不比会话（今天就有的洞），镜像缺失时必须持窗的流水线拒绝（故障即拒）；允许在没有窗口时放行的旧判定只在 platform-api 里，而它在 M1 已经切换。不宣称「只会偏严」 |
| M2（S3） | 全部流水线换成车道任务；审批执行、push-main、release.sh、Finance 改用 protocol 2；三份硬编码的表删掉 | 退出条件：集群流水线里没有任何地方再引用 `bifrost-release-window`；没有用旧定义起的在途 run；连续 7 天没有 protocol 1 的操作（或者你接受提前） |
| M3（S4 起） | 各应用按 §2.4 打开 `parallel` | 一个应用一个应用地开 |
| M4（S7） | 旧接口回 410；停止写镜像；旧 ConfigMap 写成一块永远「被已退役者持有」的墓碑，还在读它的旧程序只会拒绝 | 退役前，§2.4 的每一行都已经接入 |

**回退**：
1. 停止接受新的认领（权威里的一个开关）；
2. 让在途的操作走到终态，或者接管它们；
3. 把各应用的 `parallel` 改回 false。

不在多个操作还在写的时候直接切回旧的单窗口。

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
| 被接管之后，旧执行者又醒过来 | 它的续租、认领、终态，以及它起的 run，都因为代次不符被拒 |
| 冻结刚落下时，旧持有者还持着有效的锁 | 它的下一次认领在 LIST 冻结那一步撤回；已经发出的步骤走到核对 |
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
| B 故障即拒的冻结任务 | 继承：车道任务排在它后面 |
| C 收紧谁能写冻结和窗口 | 继承，换对象：resourceNames 改成车道对象的名字 |
| D 一次性批准、封住 run 的绕路 | 继承并推广到所有应用：用确定的 run 名加计划哈希实现（§2.1） |
| E 同步到完整提交，再关自动同步 | 继承：这是推即部署的目标打开无人值守的前提 |
| F 封住对 PROD 工作负载的直接修改 | 继承，按应用的目标命名空间做 |
| 冻结的串行边界（`W56/:90`） | 继承，改成冻结协议的「先写自己的、再读对方的」 |
| 解冻的签名 | 已由冻结协议替代（Owner 删记录）；本设计只加作用域 |
| 第 2 步 可信的发布记录 | 继承：`plan.recovery` 引用它 |
| 第 3 步 闸门先影子、再强制 | 继承，推广到每个应用（S5 影子五次） |
| 第 4 步 `promote_platform_prod` 动作 | 继承，作为 platform 的 PROD 操作计划类型 |
| 第 4 步 写入器（推摘要提交到 Git） | **待你确认作废**：3.4（你 10-21 定的 D3 A）已经改成流水线把摘要钉到 Argo 应用上，不写 Git |
| 第 5 步 有界撤回、恢复条款 | 继承（`plan.recovery`） |
| 第 6 步 带外监督器 | 继承；它有接管操作的写权限 |
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

**顺序**：S1 → S2 → S3 → S4。S5 依赖 W-56 剩下的门槛，S6、S7 在后。

**S2 结束之前，所有操作都拿 `*`**，并发一个都不开。每一片实现完都要独立复核。

**S1：影子判定与登记表**（一版 platform）
- 做什么：
  - 纯函数（一份 Go）：渲染闭包、资源规范化、seq 调度；
  - 影子结论写审计；
  - 拒绝写审计；
  - 修掉不带前提的删除。
- 验收：
  - 合成的、答案已知的并发用例：交叉 s/x；双库迁移对单库迁移；`base-platform` 单文件改动；同一个操作两次启动；
  - 登记表的语义校验，并对上集群 19 条流水线的清单（§1.2）；
  - 历史回放只作辅助证据，并写明它缺什么：被拒的请求、会话 id、资源集合，历史里都没有。
- 只有它能拦住的用例：
  - 只改 `k8s/base-platform/manifest.yaml`，影子判成「platform-prod 部署」（A3）；
  - 交叉 s/x 的两个请求按 seq 都被放行，不会互相等到过期（A7）。
- 要你：批一张发布单。

**S2：操作与权威，旧接口改成适配层**（仍然全局互斥）
- 做什么：
  - 操作的建立、认领、续租、接管、终态；
  - 确定的 run 名；
  - 旧接口改成适配层，按派生镜像写旧 ConfigMap；
  - `release.sh op` / `hold --app`。
- 验收：
  - 新旧版本混用的矩阵：旧客户端对新服务；新客户端对旧任务；protocol 1 和 protocol 2 争用；镜像写失败的间隙；
  - 过期清理和新写入并发跑 1000 次，没有一次丢掉新持有者。
- 只有它能拦住的用例：
  - 同机两个会话发同一个应用，第二个排队（A2）；
  - 平台和 workers 同时停掉，等过了 TTL，另一个应用再请求同一个库的独占锁，被拒（A1）；
  - 被接管以后，旧代次的续租和终态被拒（A2）；
  - M1 期间，一个会话经新接口持有 research 的操作，另一个会话用旧的 `hold --what bifrost-research` 申请：被拒，因为适配层走的是同一个权威；同一时刻 market-data 的任何请求也被拒，因为仍是 `*`。旧任务那个「what 有交集就放行」的判定，在权威里只有一个操作时，碰不到第二个持有者（A5）。
- 要你：批一张发布单。

**S3：入口接入**（§2.4 第 1、2、4–8、10、11 行）
- 做什么：
  - 车道任务进入全部流水线；
  - 审批执行改成建立操作；
  - 同步和回退、`apply_manifest`、迁移 Job、`owner_run_command` 带范围、重启这几条接入；
  - 删掉三份硬编码的表。
- 验收：
  - 每一行都有一正一反两个用例；
  - M2 的退出条件。
- 只有它能拦住的用例：
  - run 已经终态，Argo 还在同步，第二次发布被拒，直到 Argo 收敛（A1）；
  - 用同一个操作号但不同的 revision 起 run，被车道任务拒绝（A2）；
  - 手动 STG 同步和 `gitops_rollback_app` 没有操作就被拒（A4）；
  - 不带范围的 `owner_run_command` 被包成 `*` 独占（A4）；
  - 先跑 GS 迁移 Job 时，另一个应用的 GS 迁移排队（A4、A7）。
- 要你：应用流水线定义（一次）；`owner_run_command` 加新参数时批一张平台发布单；决定冻结演练要不要重做。

**S4：推即部署的操作，以及 platform、trade 打开 `parallel`**
- 做什么：
  - push-main 和运行时的合入走同一个判定；
  - 推送、等同步、核对三步；
  - 按应用签名的 STG 策略；
  - 按应用的冻结。
- 只有它能拦住的用例：
  - 不持 platform 的操作就推一个只改 `base-platform` 的提交，被拒（A3）；
  - 同时影响 trade 和 platform 的提交，要么一次拿齐两条车道，要么一条都拿不到（A3）；
  - 推送之后、Argo 同步之前，这条车道一直被占（A3）；
  - `agent-config/release-policy/template.json` 的改动不按文档豁免（A3）；
  - ★ platform 和 trade 在同一时间各发一次 STG，谁也不等谁；
  - app 冻结和 global 冻结组合，取更严的那个。
- 要你：签 platform 和 trade 的 STG 策略；把 `parallel` 的改动连同复核一起批。

**S5：platform 的 PROD 无人值守**
- 前提：W-56 第 1 步的 A–F（至少覆盖 platform 的目标）、第 6 步的监督器、状态格式路径清单和契约测试。
- 做什么：先影子跑五次，再改成强制。
- 只有它能拦住的用例：
  - 只改普通的 Go 代码、但写出了新的状态格式的版本，被判成「证明不了能自动恢复」，转人工（A6）；
  - 新版写入状态以后健康检查失败：回滚后旧版能读这份状态（契约测试的反例要能挡住）（A6）；
  - api 和 workers 同时失联：监督器接管并恢复到登记的目标（A6、B5）；
  - ★ 一次 R1 改动没人点就上了 PROD，你只收到一条通知。
- 要你：签 platform 的 PROD 策略；批发布单；演练时在场一次。

**S6：Finance 和插件的部署改由平台执行**（待定 8）
- 做什么：
  - Finance 用 `pin_argo_app`；
  - 每个插件列出它的配置、Deployment、迁移、探针、回滚目标，分别迁移；
  - 各自过了验收以后打开 `parallel`。
- 要你：定待定 8，签各自的策略。

**S7：旧接口退役**
- 前提：§2.4 每一行都已接入，M2 的退出条件仍然成立。
- 做什么：旧接口回 410，旧 ConfigMap 写成墓碑；文档、ADR 和 parity 一起改。

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
| 9 | ui 的范围 | 各应用的构建已经钉住 ui 的 SHA，ui 推 main 不会改变在途的构建。所以要互斥的只是「发布一个改了 ui SHA 的应用」这一个阶段：拿 `ui` 共享，ui 推 main 拿独占。也可以完全不对 ui 设锁 | 按发布阶段的共享 / 独占 |
| 10 | 冻结的作用域 | global 加 app，取更严；读失败算冻结 | 照此 |
| 11 | W-56 第 4 步的写入器 | 作废（3.4 已经走 Argo 钉摘要）；或者保留，作为 Git 留痕 | 作废 |

## 6. 没能核实的

- flex-query 写哪些 GS schema。
- Gitea 的 main 分支保护能不能只放行经过判定的推送者。
- 同机两个会话真正重叠持窗的历史实例。
- 审批单和审计的数字由作者读取，复核没有复验。
- `owner-run.sh` 的内部：复核被 preflight 拦住，本稿也没有读，只按动作目录设计「执行时认领」。
