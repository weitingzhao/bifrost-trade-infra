# 4.1 S2 STG 落地演练：能做什么、做了什么、还差什么（2026-10-27 夜班）

**一句话**：今晚在 STG 上一个用例都跑不起来，原因有两个，都已查实：
1. STG 上没有签过的 `landing:dev` 规则，演练循环不领取任何任务（要 Owner 的签名私钥）；
2. 就算有规则，现在的代码也会把每次演练记成 `failed{stale}`：不挂计划步骤的 mission 在任务全部 accepted 后同一轮就被关成 done，而每一道落地闸都要求 mission 是 active。

第 2 条已在 platform 分支 `w31/s2-landing-holds-mission` 修好（`89722fd8`，复核 638 后的 `a504b8b4`，复核 640 后的 `51ebc966`，见 §3），本机真库测试通过。第 1 条做成了可直接签的规则文件。剩下的按 `OWNER-STEPS-landing-s2-2026-10-27.md` 走：Owner 推送 → 夜班/统筹发 STG → Owner 签规则 → 统筹在 STG 起演练任务。

读的版本：platform `origin/main` = PROD = STG 的 `ae21a15e`；infra `01584b6`。STG 与 PROD 的运行时库用 `agent_reader` 只读查询（2026-10-27 01:10–02:30 CDT）。集群只用了只读 `kubectl get/logs`。

---

## 1. STG 现场（只读核对）

| 项 | 实读 | 结论 |
|---|---|---|
| workers 部署 | `platform-workers` 1/1 Running，镜像 `bifrost-platform-api@sha256:170a3642…`；env `AGENTRT_LANDING_DRILL=on`、`AGENTRT_ENV=stg`、`AGENTRT_LANDING_{USERNAME,PASSWORD}_FILE=/etc/bifrost/landing-drill/*`；挂 Secret 卷 `landing-drill` | S2 开关和凭证都在 |
| 演练接线 | workers 日志里没有 `agentrt landing drill disabled` | `wireLandingDrill` 接上了（`server/agentrt_landing.go:14`） |
| 规则 | STG 运行时库没有 `rule:landing:dev` 流（13 条规则流里没有它） | **循环每轮在 `CurrentRule` 处返回，不领取**（`controller/landing_scan.go`） |
| 落地记录 | PROD、STG、DEV 三库都没有任何 `note.landing` | 从没跑过一次 |
| 候选 | STG 有 12 件 accepted 的 platform implement 任务，最晚 10-22 | 全部早于启用时刻，会被 `before_enable` 拒（`landing/eligibility.go`），这是设计如此 |
| 执行主机 | `host:agent-06-stg` 在 06:07Z 还在跑 gate 验证 | 新建的 implement 任务会有人做 |
| CI 触发 | `trigger-trade-ci.yaml`：Gitea 任意分支推送都起 `bifrost-ci-platform` | 推 `land/stg/**` 会自动起 CI；最近 8 次 8.5–12.7 分钟 |
| 窗口 | 读 ConfigMap `cicd/bifrost-release-window`，任何持有都挡（`delivery/landing_drill.go:133`） | 和 PROD、Research、插件发布共用一个窗口 |

## 2. 演练从哪里拿候选

`store.LandingCandidates`：`repo='bifrost-platform' AND role='implement' AND state='accepted'`，按 accepted 事件时间排。每个候选再过 `EligibleToClaim`（`landing/eligibility.go:79`）：

- 环境 stg、模式 dry_run；
- **任务 accepted 时间和 mission 创建时间都不早于启用时刻**（启用时刻 = 循环第一次读到已签规则的时间，`ObserveLandingEnabled`）——所以演练任务只能在规则签好之后新建；
- **mission 是 active、没有 `no_merge`**——演练 mission 不能按惯例带 `no_merge`，否则判 stale；
- 计划还要它（不挂步骤的临时任务不算目标任务，直接过）；
- 收下的 attempt 是 base 上的单个提交；main 历史「从未有过」；没有阻挡领取的终结记录；依赖都已落地；
- 规则允许这次改动（第一片只许 `console/src/{components,pages}/**/*.tsx`、`components/**/*.css`、`styles/**/*.css`，≤10 个文件、≤300 行，不碰硬底线）。

`EligibleToPush` 就是 `EligibleToClaim`（`eligibility.go:110`），每一轮等 CI 时都重判一次。

## 3. 发现并修好的：mission 被关后演练必然 stale

**现象**（STG M-114，10-22 实测）：实现任务 03:43:32 accepted；随后 review 任务跑了 2.5 分钟，03:46:02.556 accepted；03:46:02.590 mission 被 `CloseMissions` 关成 done（`every task is accepted (3)`）。

**后果**：演练循环每 15 秒一轮，能在这 2.5 分钟里领到任务；但 CI 要 10 分钟左右，review 一过 mission 就 done，下一轮 `EligibleToPush` 判 `stale`，操作记 `failed{stale}`。S2 的四个用例都到不了，连正常路径的 `rehearsed` 也到不了。本地的演练数据库测试没暴露，因为它们的任务都挂在计划步骤上，而 `CloseMissions` 不关挂步骤的 mission（`store/close.go` 的 `closable`）。

**修法**（platform `89722fd8`，分支 `w31/s2-landing-holds-mission`；属于 CUT §2.7 已定方案「未了结的保持 active」里的持住部分，提前到 S2）：
- `CloseMissions` 在 mission 锁下多查一步 `landingInFlight`：mission 的某个实现任务，最新一次落地操作还没结束，或以 `discarded` 结束（k+1 重放待开；六小时上限会由 `SettleLandingDrillBounds` 补一条 `failed{bound}`），就先不关。没被领取过的任务、已经结束的落地都不挡。
- `ClaimLandingDrill` 先 `FOR SHARE` 锁 mission，再锁仓库流（内核锁序 mission → 流）。领取和关闭因此有先后：关闭先做，领取读到 done 就拒（stale）；领取先提交，关闭就看得见它。
- 按结局分「已交付 / 已处置」再关 mission，仍在 S3。

**第二轮**（Codex 复核 638 在真库上证实 1 项阻断、2 项应修后，`a504b8b4`）：
- B1 首次领取仍会输给关闭：`Conclude` 在一个事务里同时接受 review 和实现，随后 `Close` 就跑，没有可见的空档。改为：从没被领取过的根任务，在 accepted 后 **2 分钟内**持住 mission（循环每 15 秒一轮），只在该仓库有当前落地规则、记下了启用时刻、mission 和任务都在启用之后时生效。循环错过宽限就错过这次演练，mission 照旧关闭，不会永久持住。PROD 没有落地规则，不受影响。
- R1 演练开关关掉后没人记 `failed{bound}`，持住会永远持续。改为：从根任务首次领取（或 retry）起 **6 小时 15 分**后不再持住，不依赖循环在跑。
- R2 领取锁的是经 join 读到的 mission，没锁任务，计划的 rebind 能在领取中途把任务挪到别的 mission。改为先 `FOR SHARE` 锁任务、再锁它所属的 mission。
- 读落地流出错只持住那一个 mission（savepoint），其余照常关闭，错误合并返回。
- R3（`non_ff` 也该等 k+1）、R4（v1 生产中间态不能统一记 `failed{bound}`）、N1（每个 mission 重折叠整条流）属于 S3，登记为 TD-447。
- 复核的探针收进仓库做回归（`store/close_landing_review_test.go`）；去掉任务锁的变异体上，rebind 探针变红。复核的并发关闭探针在新旧代码上都没观察到等待，结论不成立，没收进来。第二轮复核 Work 640。

**第三轮**（Codex 复核 640：无阻断，`51ebc966`）：提前返回时把已收集的落地读取错误一起返回；`no_merge` 的 mission 不给宽限。**已知限制**（R640-1，写进验收）：繁忙的一轮（旧操作的外部读取，或 `max_in_flight_per_repo` 被占超过 2 分钟）仍可能错过新任务的首次领取——演练一次只起一件；可落库的首次领取交接放进 TD-447。复核 640 的探针收进 `store/close_landing_review2_test.go`：到限计时不因 k+1 重置、retry 才重置；关闭会等领取的后端（用 `pg_blocking_pids`；旧探针查 `pg_stat_activity.query`，被 `track_activity_query_size = 1kB` 截断，所以两个版本都看不到）——去掉 mission 的 `FOR SHARE` 就变红；错误隔离与合并。

**证据**：
- 新测试 `TestCloseMissionsWaitsForLandingInFlight`：claimed → prepared → branch_pushed → discarded 各阶段都不关，六小时上限给出 `failed{bound}` 后才关。旧代码上失败：`closed under a claimed operation: [M-3]`。
- `TestLandingClaimAfterCloseIsRefused`：先关后领，领取被拒，理由 stale。
- 本机 Postgres 17 / Redis 7：`go build ./... && go vet ./...`，`go test ./internal/agentrt/...` 全过；`89722fd8` 的分支 CI `ci-platform-zj984` Succeeded。
- 对现有数据零影响：三个环境都没有落地记录。

## 4. 四个用例分别需要什么

前提（四个都要）：上面的修复在 STG 运行；STG 签好 `landing:dev`（`agent-config/agentrt-rules/stg/landing-dev.yaml`，`stg_release: none`，S2 不发 STG）；规则签好之后新建的、不带 `no_merge` 的 mission 和一件只改允许路径的 implement 任务。

| 用例 | 要造的情形 | 能否在 STG 权限内做 | 怎么做 |
|---|---|---|---|
| 正常路径（四个用例的底） | 领取 → prepared → 推 `land/stg/<task>/1` → CI 绿 → 窗口空 → `rehearsed`，分支删除 | 能，Agent 做（建 mission/任务走 standing envelope 自动激活，不出 Owner 卡片） | 操作单第 4 步 |
| ① 旧 main 红、新 main 绿 → 丢候选重放 | 候选在等 CI 时 main 前进 | **main 前进要 Owner 推**（推送冻结期）。「旧 main 红」不能在真 main 上造 | 操作单第 5 步：候选 CI 在跑时 Owner 推第二批 → `discarded{main_changed}` → k+1 在新 main 上重放。红 main 的先后顺序由 `TestDrillMainMovementPrecedesOldMainRed`、`TestDrillScanMainMovementOpensNextOperation` 覆盖 |
| ② 旧的成功、新的失败 → 不放行 | 同一个 R 先有绿 CI、后有红 CI | **不能故意造**：要一个能过 STG 验证、却过不了 CI 的候选，而第一次绿 CI 一出现演练就收尾了 | 只靠 `TestDrillLatestCIFailureCannotRelease`、`TestLatestCIFences`、`TestDrillFinalGateAndRehearsalDatabase/latest_ci`（今晚在真库上全过）。现场遇到自然发生的红候选时补记 |
| ③ 等窗口满 6 小时 → `failed{bound}` | 候选 CI 绿后，窗口被持住 6 小时以上 | 技术上 Agent 能 `release.sh hold`，但**窗口挡住所有仓库的发布（含 PROD）6 小时**，要 Owner 定时间 | 操作单第 6 步：建议某个晚上 22:00–04:30 CDT，夜班持窗口；期间 `parked{window}` → 6 小时到 `failed{bound}`，活动位释放 |
| ④ 断点恢复 | 操作进行中 workers 重启 | 能：①之后的 STG 发布本来就会重启 workers（STG 发布在 Agent 的 STG 范围内） | 操作单第 5 步末：k+1 在等 CI 时发 STG；重启后从 note 状态接着走，不重放、不多建 CI。intent 与推送之间那几毫秒的断点由 `TestDrillControllerRecoversBranchIntentWithoutReplaying` 覆盖 |

## 5. 读回核对什么（每个用例）

`note.landing` 读法（`agent_reader`，STG 库 `bifrost_platform_stg`）：

```sql
SELECT seq, at, body_json->'landing'->>'kind' AS kind, body_json->'landing'->>'op' AS op, body_json->'landing'->>'why' AS why
FROM agentrt.event WHERE event_stream_id='landing:bifrost-platform' AND event_type='note' ORDER BY seq;
```

- 正常路径：`claimed → prepared → branch_intent → branch_pushed → ci_seen(Running…) → ci_seen(Succeeded) → rehearsed`；Gitea 上 `land/stg/<task>/1` 先出现后被删；mission 在 `rehearsed` 之前保持 active、之后变 done。
- ①：`k=1` 一行 `discarded`、`why=main_changed`；随后 `land:<task>:2` 的 `claimed`，其 `prepared.M0` 等于新 main。
- ③：`parked`、`why=window`，6 小时后 `failed`、`why=bound`；活动位释放（之后的任务能领取）。
- ④：重启前后 op 号不变，没有新的 `prepared`，CI run 名同一个（`landing-ci-<24hex>-1`）。

## 6. 没做的检查

- STG 上一个用例都没跑（缺规则；修复也还没部署）。
- 修复没上 STG；上了之后要先看 workers 启动日志和第一轮演练日志。
- 落地身份能否推 `land/stg/**`、不能推 main：P0 已在 10-27 由 Owner 实证（`P0-landing-s0-2026-10-24.md` §6），今晚没重测。
- 镜像里有 git：只看了 Dockerfile 和 infra `01584b6` 的说明，没进容器（STG 平台命名空间不许 exec）。
- 规则文件只用平台自己的解析器离线核对（`rules.Parse` 通过，正文规范化输出见夜班记录），没跑 `rule.sh check`（它要读运行令牌）。

## 7. 2026-10-27 白天在 STG 的实跑（统筹线程）

时间均为 CDT。读回：`agent_reader` 查 `bifrost_platform_stg` 的 `landing:bifrost-platform` 流；Gitea `git ls-remote`。

| 时间 | 事件 |
|---|---|
| 11:05 | Owner 推 platform main → `51ebc966`（S2 持住修复）；11:09 STG 发布 `bifrost-deliver-platform-1793117155` 成功 |
| 11:07 | Owner 签 `landing:dev` v1（STG，`rule_signed` 11:07:59）；11:08:03 `enabled` |
| 11:08–11:18 | workers 每 15 秒 `landing git init failed`：STG 运行镜像没有 git。原因是 `bifrost-deliver-platform` 从 cicd 的 Dockerfile ConfigMap 构建，infra `01584b6` 的改动没进副本（TD-448）。Owner 用管理员 kubeconfig 刷新副本后 11:19 重发 STG 成功 |
| 11:20 | 起 M-153。第一件任务的说明漏了 `siblings`（bifrost-ui），准备阶段 `npm ci` 失败，3 分钟内耗尽 40 次尝试（prepare_failed 立即重试）；停掉，换 `t_01M5Z33A8KR0Q42XQMRNM0NWHY` |
| 11:22–12:30 | 运行时几乎停滞：演练每轮为 12 件启用前的旧任务各读一次 Git，读的时候在持锁事务里占着 STG 池仅有的 2 个连接之一。presence 超时，派活、验收慢到分钟级，workers CPU 0.04→0.7。修复 platform `28119cb1`（候选查询先按库内条件筛），复核 641 SHOULD-FIX 补测试 `2ba2b6eb`（6 个变异体全红） |
| 12:16 | 正常路径：`claimed → prepared → branch_intent → branch_pushed`，`land/stg/<task>/1`，R `5da89abe`，M0 `51ebc966` |
| 12:22 | Owner 推 platform main → `2ba2b6eb` |
| 12:24 | **用例 ①**：k=1 `discarded{main_changed}` |
| 12:26 | k=2 `claimed → prepared`（M0 = `2ba2b6eb`，R `e9f87c25`）→ `branch_pushed`（`/2`） |
| 12:28 | k=2 `ci_seen` `ci-platform-fffm8` Running |
| 12:30:18 | **用例 ④**：STG 发布 `2ba2b6eb`，workers 重启 |
| 12:35 | 同一 run `ci-platform-fffm8` Succeeded → `rehearsed`；重启后没有新的 `prepared`、没有新 CI run |
| 12:36 | `land/stg/…/1`、`/2` 都已从 Gitea 删除；mission 在 rehearsed 之前一直 active |
| 13:21 | **用例 ③** 开始（Owner「现在就可以做」，白天跑，选项 A）：统筹 `release.sh hold --what bifrost-platform` 持住窗口；起 M-158（任务 `t_01M5Z9GG3G550KNZNX06TQZVJ5`，带 bifrost-ui siblings，基准 main `0a170bb8`） |
| 13:27 | 任务 accepted → `claimed → prepared → branch_intent → branch_pushed`（`land/stg/t_01M5Z9GG3G550KNZNX06TQZVJ5/1`）→ `ci_seen` Running → Succeeded → `parked{window}` |
| 13:27–19:27 | 一直停在 `parked{window}`，mission 保持 active；窗口挡住所有仓库发布，期间没有发版 |
| 19:28:06 | 六小时到：`failed{bound}`；M-158 关成 done；统筹随后放开窗口（`no release window open`）；Gitea 上没有 `land/**` 分支 |

**结论**：正常路径、①、③、④ 在 STG 实跑通过；② 只由测试覆盖（无法故意造）。③ 读回里「活动位释放」没有被下一次领取直接证明（当时没有排队的任务），由 `failed` 是终态、`TestCloseMissionsWaitsForLandingInFlight` 与 mission 已关佐证。

**以后不再做长演练（Owner 2026-10-27）**：六小时上限只靠测试守住（假时钟、秒级），不再在 STG 上持窗口六小时。原因：持窗口期间所有仓库都不能发版，代价是整整一个白天。上限或计时逻辑改动时，改的人补测试，不补演练。

**遗留**：M-153 在 rehearsed 后仍 active：被替换的旧任务停在 ready（任务级 stop 只拦领取，不改状态），Agent 没有正当途径关这个 mission；演练因此每轮为已 rehearsed 的任务重读 Git（CPU 约 0.35 核，复核 641 §3）。跟进：候选在读 Git 前按本轮已读的落地流跳过 rehearsed / 在途的任务（platform 跟进提交）；根治见 TD-447 第 5 项。prepare_failed 无退避地烧光尝试预算另记。
