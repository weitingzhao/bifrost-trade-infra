# 4.3 每个应用自己的发布节奏：发布车道与按应用的发版策略（设计稿，2026-10-24）

> 状态：第 1 稿，还没有复核。第 4 轮 4.3（W-31；Owner 2026-10-23 23:3x「D2 A」）。含 W-56 剩下的门槛。
> 依据：infra main `8f0e51f`，platform main `82b3e9d7`，bifrost-finance `0698265`。只读实测时间 2026-10-24 04:4x UTC（10-23 23:4x CDT）。
> 简写：`P/` = `bifrost-platform/`，`I/` = `bifrost-trade-infra/`，`T/` = `I/k8s/cicd/tekton/`，`R/` = `I/scripts/release/`，`F/` = `bifrost-finance/`。

## 0. 这份文档回答什么、要你定什么

回答三件事：
1. 现在的全局发布窗口挡住了什么、漏了什么。每个发布入口逐一读代码，并用审批单和审计实测（§1）。
2. 改成「每个应用一条车道，只有共用的东西才互斥」之后：
   - 「应用」怎么登记；
   - 锁怎么拿；
   - 每个入口怎么接；
   - 和 4.1（运行时自动合入、自动发 STG）怎么衔接；
   - 旧窗口怎么过渡（§2）。
3. 每个应用一份发版策略：STG 自动；PROD 小改动在你签的策略内无人值守；不过就自动回滚；事后通知。它怎么挂在车道上，和 W-56 门槛是什么关系（§2.5）。

**你要定的**：
- §3 的存放选项。推荐 A：在 `cicd` 里放一个对象，装下全部车道和资源锁。
- §5 的待定点。最要紧的四个是：bifrost-ui 怎么互斥、「小改动」的口径、第一个无人值守的应用、Finance 和插件的部署要不要改由平台执行（要新增一个窄动作，属于架构级）。

你定之前不开工。ADR §12.7 的改法在 §2.10，随设计一起定。

## 1. 现状实读

### 1.1 窗口本身

| 部件 | 位置 | 实读 |
|---|---|---|
| 数据 | `P/api/internal/delivery/release_window.go:18-19`、`window_store.go:46-55` | ConfigMap `cicd/bifrost-release-window`，只有一个键 `window.json`，字段：who、what（仓库名，逗号分隔）、env、started_at、expires_at |
| 写 | `P/api/internal/server/server.go:520-521`；`window_handler.go:28-98` | 由 `PUT` / `DELETE /api/v1/delivery/release-window` 写（B 级动作 `release_window_hold` / `release`，`actions/catalog.go:101-115`）。别人持有时回 409。**同一个 who 再 PUT 一次算续期，而且能把 what 改掉**（`window_store.go:155-163`）。只有成功的写进审计，409 拒绝不进（`window_handler.go:49-61`） |
| 读 | `window_store.go:183-197` | GET 读到过期的窗口会顺手删掉，删的时候不带 resourceVersion 前提。如果别人刚好在这一刻写入新窗口，新窗口会被删掉（竞态） |
| 判定（三份副本） | Go `release_window.go:21-39,141-183`；Python `R/window_decision.py:12-33,75-126`；Tekton 内联 `T/task-release-window.yaml:39-134` | 三份都写死了 Trade 的五个仓库名和四条 deliver 流水线名。按 CLAUDE.md §1 的验证测试，把 platform 指向别的应用，这张表就全错了 |
| 规则 | 同上，`release_window.go:146-181` | ① research 和插件的构建流水线**必须**持有窗口，并且 what 里有本仓库。② Trade 与 platform 的四条 deliver：没有窗口就放行；窗口在别的仓库手里就拒绝。③ 表外的流水线（`bifrost-build-stg`、`build-frontend-stg`、`build-research-pine`、`ci-finance`）：只要有窗口开着就拒绝。④ Tekton 任务只比 what，不比 who。只有 platform-api 的 `start_pipeline_run` 比 who（`service.go:249`） |
| 持有者身份 | `R/release.sh:746,772` | 默认 `who=${USER}@$(hostname -s)`，**同一台机器上的所有会话是同一个 who**。10-23 的审计里，platform 的持有者只有两个名字（`vision-mac-trader@Visions-MBP` / `@Visions-MacBook-Pro`），而同一天审批单的申请方有 6 个以上不同的会话。Finance 用 `finance-stg-<pid>`（`F/deploy/release.py:167-202`），按进程区分 |

### 1.2 发布入口逐个看：遵守，还是绕过

| # | 入口 | 怎么对待窗口 | 结论 |
|---|---|---|---|
| 1 | `release.sh stg/prod/dev`（Trade） | 开窗口，what 默认是 Trade 五个仓库（`R/release.sh:58,809-817`）。另有一把全局锁：任何 `bifrost-deliver-*` 在跑或 2 分钟内新建，就拒绝（`R/release_tool.py:91-111`，在 `release.sh:831` 调用）。所以 platform 和 research 的 deliver 也会挡住 Trade | 遵守，而且是两层全局锁 |
| 2 | `release.sh hold --what <repo>`（research、插件、platform 的发布、Finance） | 只开窗口；之后调用方自己 `start_pipeline_run` 并带上 who（`release.sh:743-765`） | 遵守 |
| 3 | `push-main.sh` | 推之前查一次、真正推的前一刻再查一次「有没有任何窗口」（`R/push-main.sh:182-189,273,558`）。不比 what，也不比 who：Finance 在发 STG 的时候，platform 推不了 main；连持有者自己也推不了 | 过严，跨应用互相挡 |
| 4 | Tekton 第一个任务：research deliver `T/pipeline-deliver-research.yaml:76`、dagster `:46`、market-data `:48`、ib-gateway `:42`；flex-query 在兄弟仓库 `k8s/cicd/pipeline-build.yaml:27` | 读窗口，只比 what | 遵守，但同一个仓库的第二个会话能过 |
| 5 | Trade 与 platform 的四条 deliver（`T/pipeline-deliver-stg.yaml:42`、`-prod.yaml:61`、`-platform.yaml:38`、`-platform-prod.yaml:44`） | 流水线里只有冻结检查，没有窗口任务。只有经 platform-api 起的 run 才判窗口。Trade 另有 `bifrost-prepare-deliver-stg` 的 concurrency-guard（`T/task-prepare-deliver-stg.yaml:23`），只看同环境的 Trade deliver | 部分遵守 |
| 6 | 审批单执行。PROD 的三条是 C 级：deliver-prod、deliver-platform-prod、deliver-research（`P/api/internal/actions/classify.go:75-79`） | 执行时用的是单里存下的参数，里面没有 who。没有窗口就放行；窗口在别人手里，就当暂时性拒绝稍后重试（TD-267，`P/api/internal/server/actions_wire.go:442-459`）。10-23 审计实测：platform 的 PROD run 在 16:44:11、16:49:23、17:01:34、23:28:00 建立，每次都是前一个窗口已经释放、下一次持有还没开始。**PROD run 是在没有任何人持有窗口时起跑的** | 不持锁 |
| 7 | Argo 自动同步 | `bifrost-platform-{stg,prod}` 读 infra main 的 `k8s/overlays/platform-*`，开着 prune 和 selfHeal（`I/k8s/cicd/applications/bifrost-platform-prod.yaml:13-22`）。`bifrost-research` 读 research main 的 `k8s/`，自动同步，不 prune（`bifrost-research.yaml:18-30`）。所以**往这些路径推 main 就等于发 PROD**，唯一的闸是第 3 条的全局检查。`bifrost-stg` / `bifrost-prod` 是手动同步（`bifrost-prod.yaml:31`）。实测 `finance-stg`、`finance-prod` 也是手动 | 推上去就是发布 |
| 8 | 插件部署 | 构建流水线只出镜像。部署是 Owner 在终端里 `kubectl -n plugin-* apply -f` 加 rollout（放行规则在 `agent-config/claude/auto-mode/release-permissions.json`） | 不查窗口 |
| 9 | Finance | CI 流水线 `bifrost-ci-finance` 有冻结检查，没有窗口任务。平台不把它当 CI（`P/api/internal/delivery/ci_run.go:11-17`），所以经平台起的时候，只要有窗口开着就被拒；实际上一直由 Owner 跑 `ci/owner-run-ci.sh`。发 STG 走 `deploy/owner-release.sh` → `release.py`：开共享窗口（what=bifrost-finance）→ 查冻结 → 用 Owner 的 kubectl 对 Application 打一个带 resourceVersion 的 JSON patch，换 targetRevision 并同步 → 核对 Pod 摘要（`F/deploy/release.py:302-360`） | 遵守窗口，但每次发都是一张 owner_run_command |
| 10 | `gitops_sync_app`、`apply_manifest`、`rollout_restart_deployment`、`owner_run_command` | 都不查窗口。`git grep release-window` 在平台代码里只命中 delivery 和 actions 两处 | 绕过 |

### 1.3 实测数字（只读）

**现在的状态**
- 没有窗口：ConfigMap 不存在。
- `cicd/bifrost-release-policy` 是空壳（DATA 0）。**现在没有任何签过的策略，所以什么都不会自动批准。**
- 冻结是 `frozen:false`。
- 信任锚已经编进平台（`P/api/internal/releasepolicy/anchor.go:14`）。

**近 14 天的审批单**（`list_requests all`，按 created_at，截到 10-10 04:47Z）
- 共 161 张。
- `start_pipeline_run` 64 张：deliver-platform-prod 56，deliver-prod 8。
- `owner_run_command` 88 张，其中 Finance 76 张（申请方 `Visions-MBP.bifrost.lan`，共 78 张）。Finance 的 76 张里约 11 张是跑 CI，其余多是恢复演练、探针和安装，不是发布本身。
- 10-23（CDT）一天 55 张：Finance 的 owner_run_command 47 张，发布 7 张。
- 统筹线程给的数字是 174 / 71 / 60 / 89，差别来自 14 天从哪天算起，不影响结论。

**审计**（10-23 03:25Z – 10-24 04:46Z，共 500 条）
- 持有 55 次，释放 24 次。
- Finance 持有 10 次，和 platform 的持有交错发生：19:02:53 platform 释放，19:03:49 Finance 拿到又放掉，19:03:56 platform 的 PROD run 起跑，19:05:03 platform 再次持有。两个不相干的应用被全局窗口串在一起，这次只是时间刚好错开。

### 1.4 应用、仓库、共用资源

| 应用 | 仓库（及路径） | 流水线 | 部署方式 | 自有库 | 共用 |
|---|---|---|---|---|---|
| platform | `bifrost-platform`；infra 的 `k8s/overlays/platform-{stg,prod}/**` | deliver-platform、deliver-platform-prod、ci-platform | Argo 自动同步，流水线按摘要钉镜像（3.4） | `bifrost_platform{,_stg,_dev}`（agentrt 迁移在 deliver 里跑） | ui（uiRevision） |
| trade | core、api、worker、frontend；infra 的 `k8s/overlays/{dev,stg,prod}/**`、`k8s/base/**`、`scripts/release/db-steps.d/**` | deliver-stg、deliver-prod、build-stg、build-frontend-stg | 流水线从源码重建，Argo 手动同步 | `bifrost_{dev,stg,prod}`（db-init） | ui；GS（trade-api 的 `src/bifrost_api/research/feedback_schema.py` 建 ops_feedback，core 的 raw_broker 脚本）；redis-ib（只读） |
| research | `bifrost-research` | deliver-research、build-research-dagster、build-research-pine | 构建出 tag，推 main 钉版本，Argo 自动同步 | — | GS（dw_stock / features / research / journal，ddl-apply Job） |
| market-data | `bifrost-platform-plugin-market-data` | build-market-data | Owner 用 kubectl apply | — | GS（raw_market：`schema/ddl.py`、wave 迁移 Job） |
| flex-query | `bifrost-platform-plugin-flex-query` | build-flex-query | Owner 用 kubectl apply | — | GS（`schema/ddl.py`） |
| ib-gateway | `bifrost-platform-plugin` | build-ib-gateway | Owner apply | — | redis-ib（Trade 读） |
| finance | `bifrost-finance`（Gitea 私有） | ci-finance | Owner 的脚本 patch Argo 应用 | `finance_{dev,stg,test,prod_validation,restore}` | Postgres 集群 |
| ui（组件，本身不部署） | `bifrost-ui` | — | platform 和 trade 的构建按 SHA 引用 | — | — |

**不属于任何应用的东西**
- infra 的 `k8s/cicd/**`：Tekton 共享任务、Argo 应用、registry。
- infra 的 `k8s/data/**`：只有一个 CNPG 集群 `bifrost-postgres`，实测 13 个库都在它上面。
- `agent-config/**`：治理文档，不部署。

**已有的种子**：platform 的 `config/release-rules.yaml:16-62` 已经按「车道」（trade / platform / research / market-data）记录发布。它是配置不是代码，只是还缺 flex-query、ib-gateway、finance 三条。

### 1.5 归纳：五个问题

1. **跨应用互相等**。全局锁有三层：窗口、`deliver-busy`、push-main 的「有任何窗口就拒」。
2. **同一个应用反而挡不严**：
   - 同一台机器上的会话是同一个 who；
   - Tekton 任务不比 who；
   - 审批单执行的 PROD run 不持锁。
3. **推上去就发布的路径没有专门的闸**（platform 的 overlay、research 的 `k8s/`），只有 push-main 的全局检查。
4. **应用知识写死在平台里**：Go、Python、Tekton 三份副本。
5. **拒绝不进审计**，Console 上只看得到一个窗口。

## 2. 设计

### 2.1 「应用」的定义和登记

**判据**：两次发布能各自独立回滚，就是两个应用。一个应用 = 一组一起发、一起回滚的东西：仓库（或仓库里的某些路径）、它的流水线、它的部署目标（Argo 应用或命名空间）、它独占的库。

**登记表 `release-apps` 的字段**
- `id`
- `repos[{repo, paths?}]`
- `pipelines[{name, env, kind: ci|build|deliver}]`
- `targets[{argo_app|namespace, env, deploy: pipeline|argo-auto|argo-pin|owner-apply}]`
- `owns[库]`
- `uses[{resource, when: always|on_change(paths)}]`
- `migrations[{paths, db}]`
- `images[镜像名]`

**路径归属**
- 一个仓库可以分给几个应用（infra 就是这样），规则是最长前缀胜出。
- 「不部署」名单（`agent-config/**`、`docs/**`、`*.md`）不进任何车道。
- **哪个应用都不属于、又不在「不部署」名单上的改动，按全局资源 `*` 处理**，也就是今天的并发 1。这是安全的默认。

**存放**：和 `release-rules.yaml` 放在一起。平台只知道仓库、路径、流水线、资源这些名字，不知道它们在业务上是什么，符合双飞轮的验证测试。第一版的内容就是 §1.4 那张表。

**签不签名**（待定 2）：互斥用登记表本身，不签名。登错的后果只是多等，或者因为路径没登记而落到全局锁。放权用签名策略：策略里记登记表的哈希，两边对不上时只互斥、不放权。这样就没法靠改登记表，把一处改动挪进宽松的应用。

### 2.2 车道与互斥规则

**键**
- `lane:<app>`：同一时刻只有一个持有者，同一个应用并发为 1。
- `res:<id>`：资源锁，两种模式。共享（s）可以多个持有者同时拿；独占（x）排斥其他一切持有者。
- 资源有：`db:golden_source`、`db:<各应用的库>`、`pg-cluster`、`ui`、`cicd`、`redis-ib`、`*`（全局）。自有库也登记成资源，以后多个应用共用一个库时不用改规则。

**一次获取 = 车道 + 一组资源，原子地一起拿到或一起拿不到。** 在一个对象上做一次比较交换，不分步拿，所以不会死锁，也不会留下半把锁。

**资源集合由平台算，调用方只能加、不能减。** 平台按登记表看这次发布的 diff（从本环境上一条发布记录到这次的 SHA，和发版策略算 diff 用同一个算法）：
- 改到某个库的迁移路径 → `db:<库>` 独占。
- 这次的 uiRevision 和本应用上次发布的不同 → `ui` 共享。ui 推 main → `ui` 独占。只用旧 ui SHA 的发布不拿 ui（待定 8）。
- 改了 `k8s/cicd/**` 的共享任务或 Argo 配置 → `cicd` 独占；改了 `k8s/data/**` → `pg-cluster` 独占。每一次发布都拿 `cicd` 和 `pg-cluster` 的共享锁，于是改这两处要等所有在发的发布结束（待定 3）。
- 登记不到的 → `*` 独占。

**持有者是一份租约**，字段：
- `token`：平台发的随机 128 位，只回给拿锁的一方；
- `who`：显示用；
- `session`：Claude-Session、运行时尝试 id 或审批单 id；
- `env`、`resources`、`started_at`；
- `expires_at`：默认 5 分钟，持有期间续期，最长 60 分钟；
- `reason`；
- `run`：起了 run 之后写上。

同一个 token 才算续期，token 不同一律算别人。所以同一台机器上的两个会话也分得开。

**在跑的 run 也算占着车道。** 车道空闲 = 没有未过期的租约，**并且**这个应用的 deliver / build 流水线没有不属于当前租约的 run 在跑。也就是把 `deliver-busy` 和 concurrency-guard 从全局改成按应用，并保留下来：租约过期了而 run 还在跑，第二个人仍然进不来。

**排队**：v1 不建队列（待定 6）。
- 拿不到就回 409，写明谁持有、在做什么、预计什么时候放。预计时间 = run 的开始时间 + 这个应用最近 5 次的中位耗时。
- 平台执行的发布（审批单、运行时）沿用 TD-267，按暂时性拒绝重试，上限 24 小时，和 ADR「排队超过 24 小时自动过期」一致。
- 写者优先：独占请求被拒时登记一个 5 分钟有效的「等待中」。在它有效期内，同一个资源不再发新的共享锁，免得 GS 的迁移一直被 research 的共享锁饿着。

**STG 和 PROD 用同一条车道**：同一个应用的 STG 发布和 PROD 发布不并行。09-27 那次，STG 和 PROD 各撞了一次。STG 发完到 PROD 开始之间不持车道，今天也不持，因为 PROD 钉的是 STG 克隆的提交。

### 2.3 每个入口怎么接

| # | 入口 | 新行为 |
|---|---|---|
| 1 | `release.sh`（Trade） | 加 `--app trade`，拿 `lane:trade` 和算出来的资源；起 run 时带 laneToken；`deliver-busy` 只看 Trade 自己的流水线 |
| 2 | `release.sh hold` | 改用 `--app <id>`。`--what` 再保留一版：按登记表把仓库名翻成应用，翻不出来就拿 `*`。token 写进权限 600 的文件，不打印到终端（token 不是秘密，但不进日志） |
| 3 | `push-main.sh` | 按 `origin/main..<sha>` 改到的路径找应用：① 路径属于「推即部署」的目标（platform overlay、research 的 `k8s/`）→ 推的人必须自己持有这条车道，推送成了发布的一步。② 其他路径 → 只有这条车道被**别人**持有时才拒绝，去掉今天的「有任何窗口就拒」。③ 只改「不部署」名单里的 → 不看车道 |
| 4 | Tekton 车道任务（替换 `bifrost-release-window`） | 所有 deliver / build 流水线在冻结检查之后都跑它，Trade 和 platform 的四条也补上。应用名写在 Pipeline 定义的 task 参数里，run 改不了；laneToken 是流水线参数。判定：车道有人持有、token 相等、没过期，三条都满足才放行，否则拒绝 |
| 5 | platform `start_pipeline_run` | 不再比 who，改比 laneToken。审批单执行、运行时发布、策略自动放行这几种，由平台自己拿车道，持有者是那张单或那次操作 |
| 6 | 审批单执行 | 执行时平台用单号作持有者去拿车道；拿不到就按暂时性拒绝重试。run 结束（发布记录器看到终态）后释放。run 在跑期间，平台 workers 负责续租 |
| 7 | Argo 自动同步、手动 `gitops_sync_app` | 自动同步只从第 3 条进来。对登记过的 PROD 应用，手动同步也要求持有车道（在平台动作里加判定） |
| 8 | 插件的 Owner apply | 过渡期照旧。目标是改成 `argo-pin` 或流水线部署（待定 7）；在那之前，Console 上把这类发布标成「不经车道」 |
| 9 | Finance | `release.py` 改成 `hold --app finance`，只改一处。`ci-finance` 加进平台的 CI 名单，之后由平台按 B 级直接起。STG 部署改由平台执行（待定 7）之后，才谈 STG 自动 |
| 10 | 其他写动作 | 重启、扩缩容、apply 不属于应用的清单，都不经车道。`apply_manifest` 碰到登记过的应用目标时要求持有车道：第一步只记审计，第二波再拦 |

### 2.4 和 4.1（运行时自动合入、自动发 STG）的衔接

- **合入用同一个判定**。4.1 合进 main 那一步走 §2.3 第 3 条的判定；运行时不调 push-main 这个 shell 脚本时，就调平台的同一个判定接口。
- **推即部署的路径不能当普通合入**。research `k8s/**`、infra `k8s/overlays/platform-prod/**` 一合进去就是发 PROD，按 PROD 策略属于 R2，要等你。4.1 的切法必须把这些路径排除在自动合入之外。这一条要回写进 `CUT-landing-2026-10-24.md`。
- **合入后发 STG**：
  1. 运行时为这个应用拿车道，持有者是运行时的发布操作，带这次尝试的 fencing 号；
  2. 起这个应用的 STG 流水线，等到终态；
  3. 核对，释放车道，写发布记录。
  车道被占着就等，上限 30 分钟，到了就交回任务队列。
- **自然攒批**：同一个应用有几次合入排着时，下一次 STG 发的是 main 的头，一次覆盖前面几次合入，不为每次合入各发一版。
- **两个应用互不等**：各自的合入各发各的 STG（★ 验收）。

### 2.5 按应用的发版策略

**结构**
- 每个应用一份签名策略：`cicd/bifrost-release-policy-<app>`。签名、过期、提醒都沿用现在这一套。
- 现在 `P/api/internal/releasepolicy/policy.go:47-59` 里的 `allow` 是一张流水线名单，改成这个应用的 `stg` / `prod` 两节。
- 全局冻结保留，另加按应用冻结。冻结是收紧，谁都能设；解冻沿用冻结协议（待定 9）。
- 全局策略在过渡期保留；一个应用有了自己的策略，就以它的为准。

**STG**：每个应用的 STG 发布都是 B 级，直接跑（platform 和 Trade 今天已经如此）。条件只有四条：已登记、持有车道、CI 是绿的、没冻结。Finance 和插件要先有由平台执行的部署（§2.3 第 8、9 条）。

**PROD 小改动无人值守**，下面四条全部满足才放行：
1. 这个应用已经过了 W-56 的门槛（见下表）。
2. 风险等级是 R0 或 R1：
   - R0：只改文档或测试；
   - R1：只改应用代码，不碰 DDL 和迁移路径、D10 路径、信任根、部署清单和 overlay、RBAC / Secret / 准入、流水线定义；
   - R2（清单、配置、只增的 DDL）和 R3（破坏性 DDL、信任根、凭证）照旧找你，R3 是 D 级；
   - 另有一个可选上限 `max_changed_files`（待定 4）。
3. 现有的条件照旧：
   - CI 最近一次是绿的；
   - PROD 钉的正是 STG 核对过的提交和摘要；
   - STG 观察满 M 分钟，期间没换版、没重启；
   - 没有待办的 DB 步骤；
   - 没冻结，策略没过期；
   - 登记表哈希一致。
4. 有回滚目标：上一次成功的 PROD 记录里的摘要有保留标签，并且拉得下来。

**自动回滚**：是发布操作自己的一部分，即 W-56 第 5 步说的「有界撤回」。
- 核对什么：Argo 同步到的提交；每个工作负载的 generation 和就绪状态；每个 Pod 的摘要；功能探针；观察期内的告警。
- 不过：把应用钉回上一条记录的摘要（不重建）→ 再核对 → 还不过就停下，设这个应用的冻结，带外通知你。
- R1 以上不做通用的迁移回滚，所以只有 R0 和 R1 走自动。

**事后通知**：每次自动上 PROD 推一条通知（应用、提交、命中的条款、核对结果、耗时），Console 上加一行；自动回滚另推一条高优先级的。这些不算进你的决定数。

**W-56 的门槛，按应用实读**

| 门槛 | platform | trade | research | finance | 插件 |
|---|---|---|---|---|---|
| 每个入口都遵守冻结 | 没满足：TD-293 / 294 / 314 还开着，平台身份能改 `cicd` 里的 ConfigMap | 同左 | 同左 | 冻结只在开头查一次（`release.py:303`） | Owner apply 不查冻结 |
| 每个仓库钉固定 SHA | 是（platform + ui） | 是（6 个 SHA） | 是（revision 是 40 位 SHA） | 是（revision） | 只有 ib-gateway 是 |
| 按镜像摘要部署 | 是（3.4；TD-335 待你签收） | 否：PROD 从源码重建，`T/pipeline-deliver-prod.yaml` 里有三个 kaniko 任务 | 否（按 tag） | 是（`release.py` 核对 Pod 摘要） | 否：按 tag，09-28 被覆盖过 |
| 回滚不用重建 | 做得到（钉回上一对摘要），但还没做成自动 | 否 | 否 | 是（回到旧 revision，#67 验过） | 否 |
| 独立的失败检测 | 否：W-56 第 6 步的监督器没建 | 否 | 否 | 部分有：Finance 自己的告警（#71） | 否 |

第一个能放开的是 platform，其次是 Finance，但这两个都还差「每个入口遵守冻结」和「独立的失败检测」。Trade、research、插件要先改成按摘要部署，才轮得到。

**你在这件事上要做的**：每个应用签一次策略，有效期 90 天。之后只有四种情况会找你：改动在策略之外、检查没过、发布卡住、在冻结中。

### 2.6 兼容迁移

| 阶段 | 做什么 | 旧东西怎么办 |
|---|---|---|
| M0 影子 | 新的判定纯函数和登记表上线。platform 在每次窗口写入和每次 `start_pipeline_run` 时，顺带算一遍「换成车道会怎么判」，写进审计，不拦。窗口的拒绝也开始写审计 | 行为完全不变 |
| M1 双写 | 新接口 `/api/v1/delivery/lanes`。旧的 `PUT /release-window` 变成别名，等于拿 `*` 独占，旧脚本、旧流水线的语义原样不变。任何车道被持有时，平台同时写旧的 ConfigMap（who 写持有者，what 写所有被持车道的仓库并集） | 旧的 Tekton 任务和旧 push-main 读到的仍然是「有窗口」：旧读者只会偏严，不会偏松 |
| M2 换读者 | 用 Tekton 车道任务替换窗口任务（Owner 应用一次流水线定义）。push-main、release.sh、Finance 的 `release.py` 改用车道。Go、Python、Tekton 三份写死的表删掉，改读登记表这一份 | `check-release-chain.py` 改成检查两件事：每条登记过的流水线都有车道任务；Pipeline 定义里写的应用名和登记表一致 |
| M3 退役 | 不再写旧 ConfigMap；旧接口回 410，并给出新命令 | 同步改文档：RELEASE.md「发布窗口」、工作区 CLAUDE.md §5 和 Cursor 的 `workspace.mdc`（两侧 parity-id 都 bump），以及 ADR（§2.10） |

**回退**：M1 或 M2 的任何一步要回退，就把车道判定切回别名（全部按 `*` 处理），等于回到今天。

### 2.7 审计

- **车道的每一次动作**：拿到、续期、释放、拒绝、过期、强制清除，都记 `delivery.lane.<动作>`，带上应用、资源、持有者（who / session）、token 的哈希（不记 token 本身）、原因。
- **每一次 PROD 发布**：在发布记录（`P/api/internal/releases`）里加上：
  - 应用；
  - 批准来自哪里：审批单号、策略 id 加命中的条款，或运行时的操作 id；
  - 风险等级、核对结果、回滚结果。
  发布记录的保留期不短于策略有效期（90 天）。
- **每周统计**：每个应用发了几次、几次自动放行、几次找你、等车道一共等了多久、被共用资源挡了几次、几次落到 `*`。最后两项用来看互斥是不是过严、登记表有没有漏。

### 2.8 失败模式

| 情况 | 结果 | 怎么处理 |
|---|---|---|
| platform-api 挂了 | 拿不了新车道；已有的租约不再续，到期失效 | 在跑的 run 仍然占着车道（按应用的在跑检查兜住）。修平台的那一次发布：你用自己的凭证写车道对象（应急，写审计），或者 platform 自己的发布走带外操作面（W-56 第 6 步） |
| 持有者进程死了 | 5 分钟后租约过期 | 如果 run 还在跑，在跑检查挡住第二个人 |
| 两个请求同时拿同一条车道 | 比较交换只让一个成功 | — |
| 要拿的几把锁里有一把冲突 | 整体失败，不留半把锁 | — |
| 清理过期租约和新写入撞在一起（今天 `window_store.go:192-193` 的删除不带前提） | 新租约不会丢 | 清理只在带 resourceVersion 的写里做 |
| 登记表漏了一个路径 | 落到 `*` 独占 | 结果只是多等，不会并发出错。周统计列出「落到 `*`」的次数，据此补登记 |
| 登记表被改错（迁移路径被挪走） | 可能少拿一把库锁 | 登记表哈希进签名策略，对不上就不放权。CI 检查 `paths.json` 里每个 `no_ddl` 路径都有库归属 |
| 同一台机器上的两个会话 | token 不同，第二个被拒 | — |
| Tekton 任务读不到车道对象 | 故障即拒 | — |
| Owner 用 kubectl 直接起 run | 没有 token，车道任务拒绝 | 应急时用 `release.sh lane --break-glass` 写车道对象，写审计 |
| 共享锁饿死独占请求 | 写者优先（§2.2） | — |
| 全局冻结 / 应用冻结 | 全局冻结拒绝一切新的拿锁；应用冻结只拒这个应用 | 撤回在冻结下照常进行（W-56 第 5 步） |
| 自动回滚也没过 | 停下，冻结这个应用，带外通知 | 不做第三次写 |
| 运行时的租约被接管（换了一次尝试） | 旧尝试的 fencing 号拿不到续期 | 车道的持有者绑定在发布操作上，不绑在尝试上；接管时由新尝试续期 |

### 2.9 你在 Console 上看到什么

这一轮只做数据和接口，页面的样子留给 Design 专轮。

- **每个应用一行**：
  - 车道是空的，还是谁在发（会话标题、环境、第几步、已用多久、预计还要多久）；
  - 最近被拒的请求，也就是谁在后面等；
  - 上一次 PROD：什么时候、自动放行还是你批的、有没有回滚；
  - 策略：手动还是无人值守、哪天到期；
  - 冻结状态。
- **每个共用资源一行**：谁持有、什么模式、谁在等。
- **For you 里只出四种**：策略之外的 PROD、自动回滚失败、策略快到期、某个改动长时间落在 `*` 上。
- 现在的单窗口卡片（`P/console/src/pages/shell/owner/useOwnerConsole.ts:43,84`）改成读车道列表。

### 2.10 ADR 怎么改（随你定设计一起改）

- **§12.7「发布队列」一条（`ADR-ops-architecture.md:303-308`）**，第一条子项「窗口的权威迁进平台，并改成队列，并发为 1」换成：
  - 发布车道：权威在平台。每个应用一条车道，同一个应用并发为 1，不同应用并行。
  - 只有共用资源按读写锁互斥：同一个库的迁移、bifrost-ui、集群级的 `cicd` / Postgres 改动。
  - 登记表外的改动按全局互斥处理，等于原来的并发 1。
  - 持有者是按会话或操作发的租约，不按主机。
  - v1 不建队列；平台执行的发布被拒时，按暂时性拒绝重试，24 小时过期。
  - 其余子项不变。
- **§12.3（`:256`）**：「发布窗口和队列」改成「发布车道」，留在 statefile 一类，不迁 PG。
- **§5（`:90`）**：「持有发布窗口」改成「持有该应用的发布车道」；发版策略改成按应用签。
- **§12.10 门槛表的 W-56 一行（`:353`）**：加一句「按应用判，先 platform、Finance」。
- **`agent-config/release-policy/template.json`**：去掉 `limits.concurrency: 1`。

### 2.11 两次事故，在新设计下怎样仍被挡住

- **09-27 两个会话同时发 core 0.24.0**：两个会话发的是同一个应用，于是落在同一条车道上，第二个拿不到。token 按会话发，同一台机器上也分得开。今天的窗口在同机同 who 时其实分不开，当时是靠 `deliver-busy` 和 concurrency-guard 兜住的。按应用的在跑检查保留下来。
- **09-28 插件 0.61.0 的 registry tag 被覆盖**：同一个插件的两次构建也落在同一条车道上。当时 Cursor 那次 `rev=main` 的构建没有 token，会被车道任务拒绝。另外加一道不靠车道的检查：推版本 tag 的构建在推送之前，先查 registry 里有没有同名 tag、摘要是否不同，有就拒绝。registry 不鉴权，tag 能被覆盖；现在的构建流水线里没查到这道检查（`grep tags/list` 在四条构建流水线里都是空的）。
- **新出现的风险是两个不同的应用同时发**：
  - 各自的镜像名不同：登记表 `images` 写明每个应用能推哪些镜像名；构建任务的推送目标写死在流水线里，不收参数（W-56 第 2 步已经对 platform 这样做了），CI 检查两者一致。
  - 共用的库由资源锁管。

## 3. 架构选项：车道数据放哪、谁是权威

**A（推荐）**：在 `cicd` 里放一个对象 `bifrost-release-lanes`。全部车道和资源锁写在一份 JSON 里，按 resourceVersion 比较交换；PROD 的 platform-api 是唯一的写入方，Tekton 车道任务直接读。登记表随平台配置。
- 好处：
  - 原子地拿多把锁天然成立；
  - 平台挂了照样能读，你能用自己的凭证应急写；
  - 和 ADR §12.3「修复链状态不依赖 PG、不依赖 Redis」一致；
  - 改动最小：今天的窗口就是这个形状，只是换了键。
- 代价：
  - 历史只在审计里；
  - 所有写都落在同一个对象上会有竞争，但实测一天几十次写，可以忽略；
  - TD-293 没关之前，平台身份和 `tekton-deliver` 都能改这个对象。和今天的窗口一样，防的是合作执行者误用，不防有意为之。
- 以后真需要队列，就在同一个对象里加一个等待列表，不换存放位置。

**B**：平台自己的 statefile（`k8sstate`，每个键一个 ConfigMap），再给 Tekton 镜像一份到 `cicd`。
- 好处：和平台的其他状态放在一处。
- 代价：
  - `k8sstate` 按 Pod 所在的命名空间存（`P/api/internal/statefile/k8sstate/k8sstate.go:1-4`），STG、PROD 两个平台各有一份，而车道必须全集群只有一份；
  - Tekton 要么经 HTTP 去问平台，平台一挂所有发布都停；要么读镜像，就有两份数据。

**C**：agentrt 库。运行时已有租约和 fencing（`P/api/internal/agentrt/migrations/0001_core.sql:177`）。
- 好处：和 4.1 的运行时发布操作是同一套机制，有历史，好做队列。
- 代价：
  - 和 ADR §12.3 冲突：修 PG 的那一次发布会拿不到车道；
  - 人和 Finance 的脚本都要经运行时；
  - 要新增表，是 DDL，属于架构级。

## 4. 切片与验收

顺序是 S1 → S2 → S3 → S4；S5 等 W-56 剩下的门槛；S6 在 S4 之后。每一片单独上线、单独回退。实现交给包工队，独立复核由不是作者的一方做。

**S1 登记表、判定纯函数、影子**（一版 platform）
- 做什么：
  - 登记表，内容即 §1.4；
  - 一份 Go 纯函数 `decideLane`；
  - 窗口写入和起 run 时算影子结论，写审计；
  - 窗口的拒绝也写审计。
- 验收：
  - 拿近 14 天的审计和 PipelineRun 回放：每一对被串行的跨应用发布，影子都判「可以并行」；每一对同应用的重叠，都判「拒」。
  - 表驱动的单测覆盖 §2.2 的每一条规则。
  - CI 检查：19 条流水线都有归属，每个 `no_ddl` 路径都有库归属。
- 只有它能拦住的用例：一条还没登记的新流水线（比如以后的 `bifrost-build-screening`）被判 `*` 独占，不会悄悄地和别人并行。
- 要你：批一张 platform 发布单。

**S2 车道接口、租约 token、旧接口别名、写旧对象**；`release.sh` / `hold`、Finance 的 `release.py` 改用 `--app`
- 验收（在真的 STG 平台上）：
  - ① 同一台机器上的两个会话发同一个应用，第二个被拒（今天会放行，因为 who 相同）；
  - ② platform 和 finance 同时拿车道，都成功；
  - ③ research 和 market-data 都带 DDL 改动、同时发，后到的拒在 `db:golden_source` 上；都不带 DDL，就都放行；
  - ④ 旧的 `hold --what` 照旧拿全局锁，所有应用都等它，旧行为不变；
  - ⑤ 清理过期租约和新持有者写入并发跑 1000 次，新租约一次都没丢。
- 要你：批一张 platform 发布单。Finance 那一处改动在 Finance 仓库里，由 Finance 线自己发。

**S3 Tekton 车道任务、所有 deliver / build 流水线接上（含 Trade、platform 的四条）、按应用的在跑检查、push-main 按路径判、审批单执行时拿车道**
- 验收：
  - ⑥ 用 kubectl 直接起一条 research deliver，没有 token，拒在车道任务上；
  - ⑦ platform 的 PROD 审批单执行时 Finance 正在发 STG，PROD 照常执行（今天会当作暂时性拒绝而推迟）；
  - ⑧ 不持 platform 车道就往 infra 的 `k8s/overlays/platform-prod/` 推提交，push-main 拒绝；只改 `agent-config/`，不看车道；
  - ⑨ Trade deliver 在跑时起 platform deliver，两条都跑（今天 `deliver-busy` 会挡住后起的 Trade）。
- 要你：
  - 应用流水线定义（Tekton，走 `apply_manifest` 审批或亲手应用）；
  - 车道任务放在冻结检查之后，冻结演练要不要重做，由你定。

**S4 按应用签名的策略、按应用冻结、STG 自动（接上 4.1）**
- 验收：
  - ⑩ 两个应用在同一时间各自自动发 STG，谁也不等谁（★）；
  - ⑪ 一个应用冻结时，另一个照发；
  - ⑫ 登记表改了而策略没重签：只互斥、不放权。
- 要你：每个应用签一次 STG 策略。

**S5 第一个应用（推荐 platform）的 PROD 无人值守**
- 做什么：在发布操作里做核对、观察期、自动回滚和事后通知。先影子跑五次（结论和你实际批的单逐次对比），再改成强制。
- 前提：W-56 第 1 步的冻结入口（TD-293 / 294 / 314）和第 6 步的独立检测，至少 platform 这一份要做完。这些就是 W-56 剩下的门槛，本片不绕过。
- 验收：
  - ⑬ 一次 R1 改动没人点就上了 PROD，你只收到一条通知（★）；
  - ⑭ 注入一个起不来的版本：自动钉回上一对摘要，核对通过，通知你；
  - ⑮ 再让回滚也失败：停下，冻结 platform，带外通知，没有第三次写；
  - ⑯ R2 改动（overlay）：不放行，建单等你。
- 要你：签 platform 的 PROD 策略；批这一片的发布单；在场看一次 ⑭⑮ 的演练（约 20 分钟）。

**S6 Finance 跟上，旧窗口退役，文档和 ADR 更新**
- 做什么：Finance 改用平台执行的部署（待定 7）；退役旧窗口；改文档和 ADR。
- 验收：
  - Finance 发 STG 不再需要 owner_run_command；
  - 旧接口回 410；
  - `git grep bifrost-release-window` 只剩历史文档。
- 要你：定待定 7，签 Finance 的策略。

**你要参与的事，合起来**：
- 定这份设计和 §5 的待定点；
- 每个应用签一次策略（STG 一次，PROD 在 S5、S6）；
- 应用流水线定义：S3 一次，S5 可能再一次；
- S1–S5 每片批一张 platform 发布单；
- S5 的演练在场一次。

## 5. 待定点（每条都附推荐）

1. **存放**：A / B / C。推荐 A。
2. **登记表放哪、签不签名**：推荐和 `release-rules.yaml` 放在一起，不签名；它的哈希进每个应用的签名策略，对不上时只互斥、不放权。另一个选项是整张表随策略签名，代价是每接一个新应用，你都要签一次。
3. **每次发布都拿 `cicd` / `pg-cluster` 的共享锁吗**：推荐拿。代价是改共享任务或改集群时，要等在发的发布结束。
4. **「小改动」的口径**：推荐 R0 / R1 按路径类别判，不设行数上限；`max_changed_files` 先不设，看 S5 影子期的数据再定。
5. **第一个无人值守的应用、STG 观察时长 M、通知方式**：推荐 platform，M = 10 分钟（W-56 的起点值），通知走 ntfy 加 Console 一行；Finance 第二个。
6. **队列**：推荐 v1 不建，只靠写者优先和平台侧重试；周统计显示等待时长偏高时再加。
7. **Finance 和插件的部署改由平台执行**：要新增一个窄动作，比如 `pin_argo_app`：只认登记表里的 Argo 应用，只改 revision 或摘要。这是新动作，属于架构级。推荐做，否则这两类的 STG 永远要你在终端里跑。
8. **ui 的互斥口径**：推荐 ui 推 main 时独占，带着 ui 变化的应用发布拿共享，只用旧 ui SHA 的发布不拿。依据是各应用的构建已经按 SHA 钉住 ui，ui 的 main 中途移动不会改变正在发的那一版。
9. **按应用冻结怎么解**：推荐和全局冻结同一个协议，由你用自己的凭证解；设冻结谁都可以。
10. **4.1 切法的回写**：推即部署的路径（research `k8s/**`、infra `k8s/overlays/platform-prod/**`）不进自动合入。这一条需要 4.1 那边确认。

**没能核实的事实**
- flex-query 实际写哪些 GS schema：只看到它有 `schema/ddl.py`，没细读。
- 插件构建有没有别的地方检查「tag 已存在」：只 grep 了四条流水线。
- 同一台机器上两个会话同时持有窗口，在历史上有没有真的发生过：代码证明会发生，审计里分不出会话。
