# 切法：4.1 交房——验收通过的活由运行时自己合进 main（2026-10-24，第 3 稿）

**实施记录（Work 564，2026-10-24）**：Owner 已将 §5 的 13 点全部按推荐定下；下文“待定”表保留方案讨论历史，不再重复询问。
S0 仓库准备见 `P0-landing-s0-2026-10-24.md`、`OWNER-STEPS-landing-s0-2026-10-24.md`；
vet、实际 clone SHA 结果、最终 RBAC 与离线防线已准备。线上 P0、推送者、D-L5 仍待实证，未开启 S2/S3。

**协议修订（Work 574，2026-10-26，v1.1）**：按统筹 Q1–Q3 决定增加 `retry`、`discarded`、`rehearsed`，仍是 `note.landing`，不加 DDL。旧 v1 事件继续可读。此次只完成 S2 代码和本机验证，不启用演练；P0 与 S3 的边界不变。

**2026-10-27 夜班统筹（proceed-on-recommendation，Owner 事后审计）**：把 §2.7 里「未了结的保持 active」的**持住**部分提前到 S2。原因：STG 上不挂计划步骤的 mission 在任务全部 accepted 后同一轮就被 `CloseMissions` 关成 done（M-114：review 通过后 34 毫秒），而每一道落地闸都要求 mission 是 active，演练会在 CI 跑完前记成 `failed{stale}`，S2 到不了 `rehearsed`。platform `89722fd8`、`a504b8b4`、`51ebc966`（分支 `w31/s2-landing-holds-mission`，后两个回应复核 638、640）：mission 的实现任务最新一次落地操作未结束、或以 `discarded` 结束（k+1 待开）时不关，最长持到首次领取后 6 小时 15 分；从没被领取过的，在已启用落地的仓库里 accepted 后留 2 分钟首次领取宽限；`ClaimLandingDrill` 先以 FOR SHARE 锁任务、再锁其 mission、再锁仓库流。已知限制：繁忙的一轮仍可能错过首次领取，演练一次只起一件。S3 前还要补的见 TD-447。按结局分「已交付 / 已处置」关 mission 仍属 S3。另：演练 mission 不能带 `no_merge`（领取闸判 stale）。详见 `REPORT-landing-s2-2026-10-27.md`。

**S2 实跑结果（2026-10-27，统筹线程）**：正常路径、①、③、④ 在 STG 实跑通过，② 只由测试覆盖；时间线见 `REPORT-landing-s2-2026-10-27.md` §7。③（窗口持满六小时 → `failed{bound}`）只做这一次：今后六小时 / 八次总上限只靠测试守住，不再在 STG 上持窗口演练（Owner 2026-10-27）。

**这份文档回答什么**：Owner 10-23 23:3x 定了「D4 A」：验收通过的活由运行时自动进 main，先接 bifrost-platform、bifrost-trade-infra 两个仓库；PROD 仍按发版策略走，规则由 Owner 签。本文分三部分：
- §1：今天一件活从 agentd 推分支到进 main，实际怎么走（带 `文件:行`）；
- §2：运行时自己合、自己发 STG，需要哪些前置条件、步骤和记录，出错怎么办；
- §3：分几片做，每片怎么验收，哪几片要 Owner 出手。

**Owner 要定什么**：见 §5 的表，已按「先定哪个才能开工」排序。最先要定的是 P0 的证明范围和信任假设，其次是状态怎么存、第一片做多大。

**来历**：第 1 稿 `047ea5ca`；第 2 稿 `71b235d7`（回应 Codex 复核 533 和 4.6 复核 534 的 B1）；第 3 稿回应窄复核 538，逐条回应写在 `~/agent-work/codex-review-538/RESPONSE.md`。第 3 稿按复核 538 改了这些（括号里是复核的节号）：
- 资格按阶段分开（§3.1）；
- 状态改用现有 `note` 加一个有版本的子协议，不加 DDL，写清折叠函数、合法转移和断点对账（§3.2）；
- 幂等接管和有意重试分开；第一片就接上 mission 的关闭（§3.3）；
- 最后一道闸接上规则锁，按租户、按 UTC 日预留额度（§4）；
- 第一片的硬底线扩到整个 `api/**`（§5）；
- 窗口读取不再删除别人的窗口（§6）；
- STG 改用平台自己的健康证据；坏落地由现有入口恢复（§7）；
- P0 扩成完整的「身份 → 凭证 → 间接入口」清单（§2）。

**读的版本**：
- infra `639edc9`；platform `origin/main` = `82b3e9d7`；
- PROD 和 STG 的运行时库，10-24 05:xxZ 只读查询（`agent_reader`）；
- 集群只做了只读的 `kubectl get`。

---

## 0. 一段话

今天运行时把活做到 `accepted` 就停了：要统筹线程手工 cherry-pick、跑整套检查、经 `push-main.sh` 推（TD-383）。

**推荐的做法**：PROD 的 platform-workers 加一个「落地」循环。每件落地是一次有编号的操作，每一步先记意图，记在运行时库现有的 `note` 事件里。流程五步：
1. 在 main 最新提交上，用固定的时间戳重放收下的提交，得到候选提交 R；
2. 把 R 推到 `land/prod/<任务>/<k>`，CI 随推送自动起；
3. 推 main 之前，持规则、计划、额度三把锁，按「推 main 前」的资格重判一次；
4. CI 绿、窗口不挡、main 没动，才把同一个 R 快进推到 main；
5. 发 STG 时，按「发 STG 前」的资格判定，钉死 platform 和 ui 两个提交号，核对发布差异的权限、镜像摘要，以及平台自己的健康检查。

**第一片**只开放 platform 的 Console 文案和纯展示组件，同一时间只有一件在途。冲突、检查失败都开成明确的落地问题，不自动修。

**前置条件 P0**：先把所有能拿到 main 写权限或 Gitea 管理员权限的路列全并切断，只留专用落地身份这一个例外。

---

## 1. 现状实读

### 1.1 一件 implement 任务今天怎么走到 main

| 步 | 谁 | 实读 |
|---|---|---|
| 建任务 | 控制器 | base 取当时 main 的头：`store/planresult.go:247-249`；来源写进 `off_plan_reason`「planned by task …」 |
| 采用计划 | 控制器 | 计划任务以「plan used: …」为理由转 `accepted`：`planresult.go:279-287`；此时持 mission 行锁：`:104-111` |
| 提交、推分支 | agentd（06） | 尾注 `Agentrt-Task`、`Change-Id`、`Work`：`agentd/workspace.go:343-350`；只许推 `refs/heads/agent/`：`:355-358` |
| 验收 | 控制器 | 确定性检查 → 异家评审 → `accepted`：`store/accept.go:13-21`、`:398-407`；检查命令写死在 `store/repos.go:68-95` |
| 状态 | — | `accepted` 之后没有任何转移：`kernel.go:132-143`；`failWork` 也用这张表：`:180-192` |
| 依赖 | 控制器 | 依赖的任务 `accepted` 就放行，不看进没进 main：`store/propose.go:754-777` |
| 撤计划步骤 | 计划变更 | `dropStep` 只改步骤；步骤上已经 `accepted` 的任务原样留着：`store/planchange.go:540-570` |
| mission 结束 | 控制器 | 任务全部 `accepted` 就关：`store/close.go:40-45`、`:74-90` |
| 进 main | **统筹线程手工** | `merge_accepted.py apply --push` |
| 补记 | 控制器 | 每 5 分钟读一次 main，写 `note{landed}`；被 revert 的不算：`controller.go:426-442`、`store/prune.go:364-437`、`lineage/mainresults.go:55-59` |

### 1.2 事件库的约束（复核 538 §3.2）

- **事件类型不能随便加。** `event_type` 受数据库 CHECK `event_type_closed` 约束：`migrations/0009_issues.sql:44-63`。Go 侧词表必须和它一致：`store/vocab.go:33-35`，测试在 `vocab_test.go:13-26`。新增事件类型就要做 migration。
- **`note` 可以扩字段。** `note` 的字段是封闭的：`vocab.go:160-174`。但字段可以声明成 `kAny`，再由 `fieldValues` 按字段校验取值：`vocab.go:419-420`、`:515`。`card` 字段就是这么用的（「ids and enums only」）。
- **流名不受约束。** `event_stream` 只有主键：`migrations/0001_core.sql:197-202`。`lockStream` 允许先锁、后检查：`store/event.go:136-144`。
- **规则写入的锁序**：writer → capability 锁（排他）→ `pg_advisory_xact_lock(ruleLock, hashtext(rule_id))`，见 `store/rules.go:239-252`。读规则时持该规则锁的共享模式，已有先例：`store/cardauto.go:136`。

### 1.3 `merge_accepted.py`、TD-383、TD-387、TD-432

- **`merge_accepted.py`**：
  - 只接「base 上的一个提交」：`:391-400`；
  - 能认出标准格式的 revert：`:329-384`；
  - `plan` 丢掉了「曾落地后被撤销」这个理由：`:464-466`；
  - 提交信息写死「Until the release queue…」，还给 `Work` 加 `TD-383`：`:410-445`；
  - `--push` 只对 platform 生效：`:71-75`。
- **TD-383**（`TECH_DEBT.md:2706-2717`）、**TD-387**（`:2653-2664`）：同第 2 稿。
- **TD-432**（统筹线程记，P1）：平台身份能读到 Gitea 管理员令牌，见 §1.5。

### 1.4 Gitea、`push-main.sh`、CI

**Gitea**
- `main` 只许 `maintainers` 和 Owner 推送、合 PR；不能删，不能强推：`protect-repo.sh:5-7`、`:205-218`。
- `agent/**` 的保护已去掉：`:8-12`、`:243-256`。
- 标签规则只能在页面上设：`:13`、`:258`。

**`push-main.sh` 的门槛**，依次是：
1. 窗口关着：`:182-190`；
2. 只快进：`:275-277`；
3. 提交带 `Change-Id` 和 `Claude-Session`：`:290-316`；
4. CI 绿：`:452-505`（`CI_REPOS` 不含 infra：`:117`）；
5. code-health：`:113`、`:534-540`；
6. 快测，platform 部分含 `go vet ./...`：`:375-398`；
7. 推之前再查一次窗口：`:558`。

**CI**
- 推任何分支都起 CI：`trigger-trade-ci.yaml:221-225`。
- 只有三条 CI 流水线：`delivery/ci_run.go:11-17`。
- ci-platform 不跑 `go vet`：`pipeline-ci-platform.yaml:175-176`。
- CI 结果按「仓库@提交」索引，有过一次成功就算成功：`release_policy_facts.go:241-244`、`:283-302`。
- 外部起 CI 时只能指定 `revision`：`ci_run.go:21-53`。
- 克隆任务会输出一个 `commit` 结果：`task-git-clone-gitea.yaml:22-26`、`:83-85`。
- 实测（10-17～10-24）：ci-platform 跑了 146 次，成功 128 次；成功的那些用时中位数 6.3 分钟。

### 1.5 凭证与间接入口（复核 538 §2）

- **平台身份读得到管理员令牌。** STG、PROD 的平台身份都能 get `cicd/gitea-bootstrap`：`platform-rbac/10-stg.yaml:137-143`、`00-clusterroles.yaml:98-104`。代码把它当管理员令牌用：`delivery/service.go:1292-1306`。
- **CI 的测试读得到克隆凭证。** CI 克隆任务把 `gitea-git-credentials` 注入环境：`task-git-clone-gitea.yaml:32-42`；再把带用户名和密码的地址写成 origin：`:58-80`。同一个工作目录随后交给候选代码的测试：`pipeline-ci-platform.yaml:40-86`、`:169-176`。所以测试读 `.git/config` 就能拿到凭证。这份凭证历史上和管理员令牌是同一个：`scripts/gitea/rotate-admin-token.sh:2-8`。
- **镜像同步任务用的是管理员令牌。** 它注入并使用 `gitea-bootstrap` 的令牌：`task-gitea-mirror-sync.yaml:35-40`、`:60-78`；`bifrost-deliver-platform` 会调它：`pipeline-deliver-platform.yaml:39-47`。PROD 平台能建 PipelineRun 和 TaskRun：`00-clusterroles.yaml:162-172`；准入只限定「必须引用具名任务、不许内联」：`40-admission.yaml:121-135`。
- **只挂进 workers 不等于别的进程拿不到。** PROD 平台身份能 patch 本命名空间的 Deployment：`00-clusterroles.yaml:115-117`、`20-prod.yaml:181-188`。所以「Secret 只挂进 workers」证明不了同一个 SA 下的其他平台进程用不到它。
- **06 上同用户可读。** 执行者和 agentd 是同一个系统用户，读不受限：`CUT-agentd-confine-2026-10-19.md:15`。
- workers 只有 1 个副本，更新方式是 Recreate：`base-platform/manifest.yaml:83-108`；镜像里没有 git。

### 1.6 窗口、发布、健康

**窗口**
- 只有一个 ConfigMap：`release_window.go:14-19`。写入时只按 `who` 认持有者：`window_store.go:155-163`。
- 读到过期的会无条件删：`:191-194`。主动释放也是无条件删：`:199-211`。
- PROD 对这一个具名对象有 delete 权限：`platform-rbac/45-release-window.yaml:12-28`。

**发布**
- `bifrost-deliver-platform` 的 `revision` 和 `uiRevision` 默认都是 `main`：`pipeline-deliver-platform.yaml:15-23`。
- 同一个操作号对应同一个 run 名。已存在就报「已存在」；失败了的 run 也不会重跑：`delivery/service.go:282-285`、`:332-363`。
- `Deployed("stg")` 读 platform 车道的提交，并核对三个镜像摘要：`server/agentrt_sources.go:20-34`、`:87-98`、`:186-218`。
- 发布任务会等 rollout：`task-rollout-verify-platform.yaml:55-62`。
- STG 发布时，会用新镜像、以 `agentrt_owner_stg` 身份跑迁移：`task-agentrt-migrate-stg.yaml:99-120`。

**健康**
- `get_stg_smoke` 查的是 **Trade** 的前端和 API：`delivery/service.go:678-703`、`:720-730`。它不是 platform 的健康检查。

### 1.7 规则与历史结果

- 常备授权只有 `none`、`branch` 两档：`rules/rules.go:81`。
- 规则收紧要逐项比较：`rules/tighten.go:16-23`。
- 「问题的回答不是批准」：工作区 `CLAUDE.md:230-231`。
- 收下了、没进 main、也没标 `no_merge` 的：PROD 10 件，STG 10 件，合计 20 件，就是 D-L5 那 20 条。

---

## 2. 设计

### 2.0 前置条件 P0：除专用落地身份外，没有任何身份能拿到 main 写权限或管理员能力（A1，TD-432）

**交付物**：一份清单，不含任何凭证内容。每一行写一个身份，四列：身份、它能读或能挂载的凭证、这个凭证在 Gitea 上的权限（读、推 main、合 PR、建标签、改保护）、它能间接执行的入口。要覆盖：
- STG、PROD 的平台 SA；
- 06 上执行任务、评审任务用的身份；
- CI 实际用的 SA，以及 CI 克隆目录里存下的凭证；
- 克隆任务、镜像同步任务、发布任务；
- PROD 平台经「建 run」「patch Deployment」能间接用到的凭证。

**要改的**：
1. 删 STG 的 `bifrost-platform-gitea-creds-stg`。平台读 Gitea 改用只读用户，每个环境一份；PROD 也一起换。
2. CI 克隆改用只读的克隆身份。凭证不再写进 `.git/config`，改为每条 git 命令用 `http.extraHeader` 环境变量传，克隆完不留下。
3. 镜像同步任务不再用管理员令牌，只给它完成同步所需的最小权限。Gitea 做主之后，这个任务对已转换的仓库是空操作；最小权限的细节在 S0 实测后定。
4. STG 演练身份只有两个仓库的代码写权限，不进 main 和标签的白名单。

**信任假设**（§5 第 1 项，要 Owner 明确）：推荐写成「受信主体是经发布单批准的 PROD 平台代码整体（同一个 SA）」。专用落地令牌是唯一例外，挂在 workers 上；同一个 SA 下的其他平台进程理论上也能间接用到它，这一点如实写明并接受。如果要求平台进程之间也做机械隔离，就得另建 SA、RBAC 和准入，另外算成本。

**验收**（全部实测；不过就不开 S2、S3）：
- 清单逐行实测读、推 main、合 PR、建标签、改保护五项：只有专用落地身份能推 main。
- STG、PROD 的平台 SA 读 `gitea-bootstrap` 都回 no。
- CI 的测试读工作目录的 `.git/config`，读不到凭证。
- 镜像同步任务拿不到管理员令牌。
- STG 平台代码调 Gitea 改保护，回 401 或 403。

06 上只按文件名和环境变量名做的检查，只算辅助证据。

### 2.1 谁执行合入（X1）

| | A. PROD platform-workers 的控制器 | B. 06 上的 agentd | C. Tekton 流水线 |
|---|---|---|---|
| 令牌放哪 | `bifrost-platform-prod/agentrt-lander`，以文件挂进 workers | agentd 家目录 | `cicd/agentrt-lander` |
| 执行者写的代码能不能碰到令牌 | 不能：这个 Pod 只跑发布单批过的 PROD 代码（前提是 P0 和信任假设成立） | **能读**（同一系统用户） | cicd 里能建 Pod 的都能挂载它；而 CI 就在 cicd 里跑执行者写的测试 |
| 离线时 | workers 停了就不合；状态记在库里，恢复后对账 | 06 停了就不合 | Tekton 停了就不合 |

**推荐 A**。做法：
- 每次操作用新克隆的干净目录，remote 固定；
- `core.hooksPath=/dev/null`，`GIT_CONFIG_NOSYSTEM=1`，`GIT_CONFIG_GLOBAL=/dev/null`；
- 协议只放 http，不读 `.gitattributes` 里的 filter 和 `.gitmodules`；
- 令牌用单个 git 子进程的 `http.extraHeader` 环境变量传；
- **这个进程里不跑候选代码，也不跑测试**。

### 2.2 资格按阶段分开（A3、534 B1、复核 538 §3.1）

**共用一份事实读取 `facts(task)`。** 每次判定都现读；读失败一律按「不合格，下一轮再判」处理。读这八项：
1. 环境和落地模式（PROD 真推、STG 演练）。模式由部署时的环境决定，领取前就已确定。
2. mission 的状态、scope 版本、有没有 `no_merge`。
3. 计划节点的状态和版本。如果是目标拆出来的任务，还要读产生它的那个计划任务，以及这个 mission 最后一次被采用的计划——按 `plan used` 的 `accepted` 判，不按创建时间判。
4. 任务状态、收下的那次尝试和它的提交 A，以及 A 是不是「base 上的一个提交」。
5. **main 历史三态**：从未有过 / 曾有过且仍有效 / 曾有过已撤销。按 `Agentrt-Task` 和 `Change-Id` 查；读不到就算「未知」。
6. 依赖的有效落地状态。
7. 当前规则：路径、底线、上限、`stg_release`。
8. 本仓库的启用时刻 `landing_enabled.at`：落地循环第一次看到已签规则生效时记下的真实时间，不是规则里写的零点。

**四个阶段**

**`eligibleToClaim`**（领取和第一道闸）。以下全部满足才合格：
- 模式与本环境一致；
- A 收下的时间、mission 创建的时间都不早于启用时刻；
- mission 是 active，没有 `no_merge`；
- 计划还要它：所在节点不是 dropped 或 stopped；如果是目标拆出来的任务，产生它的就是最后一次被采用的计划；
- A 是 base 上的单个提交；
- **main 历史是「从未有过」**；
- 没有阻挡领取的终结记录：`landed/reverted` 和未被明确 retry 解除的 `failed` 阻挡；`discarded` 不阻挡；`rehearsed` 不阻挡后续 PROD 领取（STG 扫描不重复已完成的演练）。`retry` 只解除指定最新失败对一个新操作的阻挡，不绕过其余资格；
- 依赖都已有效落地；
- 规则允许这次改动。

**`eligibleToPush`**（第二道闸，持锁，§2.5 第 6 步）：条件同领取。唯一的差别是，如果 main 历史里那个「曾有过且仍有效」的提交正是本操作的 R，就不推，转入对账。

**`eligibleToDeploy`**（发 STG 前，按每个待发布的 R 判定）。以下全部满足才合格：
- 本操作已经记下 R 落地过；
- R 在快照 P 里仍有效；
- mission 没被叫停，没有 `no_merge`；
- 计划还要它；
- 规则还在，且 `stg_release` 开着；
- 从上一次 STG 发布到 P 的整个差异都在允许范围内，不碰底线。

注意这一阶段**不要求**「main 上从未有过」。

**`reconcile`**（对账，任何时候都可以跑）：不看资格。规则撤了、过期了，照样核实已经发生的外部动作：落地过没有、现在是否仍有效、分支删了没有、run 有没有被接管、核验做了没有。

**和计划变更怎么排先后**：第二道闸在同一个事务里拿锁（锁序见 §2.5 第 6 步），对计划节点和 mission 行加 FOR SHARE。计划变更改节点时要锁同一行，所以两者一定有先后：
- 在它之前提交的撤步骤、加 `no_merge`、叫停 mission，会挡住这次推送；
- 在它之后提交的，按「已经落地」处理，要撤就走 §2.9。

**STG 演练**：STG 的落地循环固定在演练模式，只看 STG 自己收下的任务，按同样的四个阶段判定。它用的身份没有 main 写权限（P0），也不为演练放宽任何生产条件。

**旧的 20 件**：领取条件里的「启用时刻」和「mission 创建时间」两条，已经把它们排除在外。D-L5 按 mission 逐件确认后再标 `no_merge`，用来解释和清理，不是靠它挡住它们。Owner 2026-10-26 选 A：新增正式 runtime 动作 `mark_missions_no_merge`，经 D 级审批、`mission_amended` 事件和同一事务更新；随平台版本发布，在 S3 打开前完成。

### 2.3 规则 `landing:<租户>`：可判定的契约（A2、B3、复核 538 §5）

**第一片的第 1 版**：

```yaml
rule_id: landing:dev
rule_version: 1
direction: initial                 # Owner 签；真实启用时间见 §2.2 的 landing_enabled.at
effective_at: <签名当天>T00:00:00Z
expires_at: <生效后 30 天>
tenant: dev                        # 租户，不是环境；只有 PROD 控制器凭它推 main
repos:
  - repo: bifrost-platform
    allow: ["console/src/components/**/*.tsx", "console/src/components/**/*.css",
            "console/src/pages/**/*.tsx", "console/src/styles/**/*.css"]
    deny: []
    stg_release: bifrost-deliver-platform
limits:                            # 按租户、按 UTC 日
  max_files: 10
  max_changed_lines: 300
  max_landings_per_day: 5          # 当天推过 main 的不同根任务数（§2.5 第 6 步）
  max_in_flight_per_repo: 1
```

**路径语义**：
- 路径从仓库根锚定，区分大小写；
- `*` 不跨 `/`，`**` 可以匹配零层到多层；
- 改名时，新旧两个路径都要过检查；删除也算改动；
- 符号链接、子模块、只改模式位、二进制文件，一律拒；
- 行数 = 增加 + 删除。

**纯展示**（三条都满足才算）：
1. 改到的文件全在 `allow` 里；
2. 新增的行里没有指向 `api/`、`lib/`、`hooks/` 的 `import … from`；
3. 新增的行里没有 `fetch(`、`XMLHttpRequest`、`useQuery`、`useMutation`、`window.location`。

语义上是否真的「纯展示」靠评审，剩余风险交给 Owner。

**硬底线**：写在代码里，规则、决定卡、例外单都放不开。
- **platform（第一片）**：
  - `api/**` 全部；
  - 任意深度的 `go.mod`、`go.sum`、`package.json`、`package-lock.json`；
  - `console/{vite.config.*,tsconfig*,index.html}`、`console/src/{main.tsx,App.tsx}`、`console/src/{api,lib,hooks,pwa}/**`；
  - `mcp/**`、`agent/**`、`scripts/**`、`config/**`、`Makefile`、`.husky/**`；
  - 任意深度的 `.env*`。
- **S5 起才放开 `api/` 的一部分**：先按代码清单重审。底线至少保留 `api/cmd/**`，以及 `api/internal/` 下的 `server`、`actuation`、`actuationpolicy`、`actions`（`actions/tier.go:26-29` 决定审批级别）、`approvals`（`approvals/handler.go:122-147` 处理批准）、`releasepolicy`、`delivery`、`agentrt`、`agentd`，还有迁移执行器。
- **infra（S6）**：
  - `k8s/**`、`agent-config/**`、`scripts/{release,gitea,agent-host}/**`、`scripts/agentrt/rule.sh`、任意深度的 `.env*`；
  - 外加一条测试：允许目录不能被别处按路径或模块名引用。

**碰底线**：直接拒，开一个落地问题，写明正规入口；不给「合」这个选项。

**软上限**：第 1 版不设例外（X7）。

**收紧还是放宽**：以下几种算收紧，其余全算放宽、要签名。停合的开关就是一次收紧。
- 仓库只减；
- `allow` 只删条目；
- `deny` 只增；
- 上限只降；
- `stg_release` 只能改到 `none`；
- 到期时间只能提前。

**续期、换版、过期**：
- 在途操作记下领取时的规则版本，到每一道闸都按新版重判；
- 不再被允许的转为 `parked{rule}`，之后若又允许，就接着走；
- 过期只停新的领取和推送，对账照常进行。

**权限分批发**：platform main 的推送权在 S3 发，infra 的在 S6 发。标签规则在 S3 之前核对。

**令牌泄露后**：
1. 先把这个用户移出推送白名单，再换令牌；
2. 按 Gitea 的推送记录，核查泄露期间该用户全部的 ref 变更和权限变更。

集群内访问 Gitea 走 HTTP 明文，这一点接受。

### 2.4 状态协议：现有 `note` 加一个有版本的子协议，不加 DDL（X3、A10、复核 538 §3.2）

**载体**：
- 事件类型仍用 `note`，数据库的 CHECK 本来就允许它。
- `note` 增加一个可选字段 `landing`（`kAny`），在 `fieldValues["note"]["landing"]` 里配一个专门的校验器，做法照 `card` 字段。
- `text` 仍然必填，写给人看。
- 只改 Go 代码，不加 DDL，不加表。

**子协议 v1.1**：`landing` 必须有 `v`、`kind`、`op`。旧版整数 `v: 1` 及其 kind 保持可读；新写入用字符串 `v: "1.1"`（事件的 canonical JSON 禁止小数，故不用数值 1.1）。每个 kind 的字段封闭，未知版本、kind、额外字段拒收；三个新 kind 只接受 v1.1。`retry` 的 `op` 等于 `after_op`，它是解除旧失败阻挡的记录，不改变旧操作的失败事实，也不原地重启。`reason` 为非空文字（最多 1000 字节），`by` 为答复者标识；只由控制器在读取明确答复后写入。

**写到哪些流**：
- `landing:<仓库>`：落地操作和 STG 操作。Append 时持流锁，同一仓库的写入因此串行。
- `landing-quota:<租户>:<UTC 日期>`：额度预留。
- 所属 mission 的流：只写一条带 `text` 的镜像，给 Console 和人看。

**`kind` 的封闭集合**：

| 分组 | kind |
|---|---|
| 落地 | `enabled{repo, rule_version}`、`claimed{task, attempt, A, rule_version}`、`prepared{R, M0, committer_date, dry_run}`、`branch_intent{ref, R}`、`branch_pushed{ref, R}`、`ci_kick{try}`、`ci_seen{run, status}`、`ci_rerun{try}`、`main_intent{R, M0}`、`main_result{outcome: ok\|non_ff\|denied\|unknown}`、`landed{R}`、`reverted{R, by}`、`parked{why, retry_at}`、`unparked`、`failed{why}`、`discarded{why}`、`rehearsed{R}`、`retry{root, after_op, reason, by}` |
| 额度 | `reserved{root, op}` |
| STG | `stg_pending{R[]}`、`stg_snapshot{P, U, try}`、`stg_started{run, try}`、`stg_result{run, outcome}`、`stg_verified{P, U, digests}`、`stg_failed{why}` |
| S4 再加 | `replaces{root, follow_up}` |

`why` 的取值也是封闭的：`stale`、`conflict`、`patch_changed`、`overlap`、`ci_failed`（v1 历史保留）、`ci_red`、`floor`、`limit`、`denied`、`bound`、`declined`、`rule`、`main_red`、`ci_stuck`、`window`。

`discarded.why` 只接受 `main_changed`、`branch_collision`，不与失败原因混用。

**折叠函数**：一个纯函数，把一个流按 `op` 折叠成每个操作的当前状态。写入时在流锁下先折叠，再检查这次转移是否合法；不合法就拒写。

**落地操作的合法转移**：

| 从 | 可以到 |
|---|---|
| （无） | `claimed`；若最新同根 k 是 `discarded`、k+1 因 `bound` 拒领，由控制器直接用一条事件写 k+1 的 `failed{bound}`（2026-10-26 统筹决策） |
| `claimed` | `prepared`、`parked`、`failed` |
| `prepared` | `branch_intent`、`parked`、`failed` |
| `branch_intent` | `branch_pushed`、`failed`、`discarded` |
| `branch_pushed` | `ci_kick`、`ci_seen`、`ci_rerun`、`parked`、`failed`、`main_intent`、`discarded`、`rehearsed` |
| `parked` | `unparked`（回到停之前的状态）、`failed`、`discarded` |
| `discarded` | 操作结束、释放活动位且不可改写；控制器自动开 k+1，重新过资格和预算；若断点恢复时预算已到限，k+1 按上行出生即失败 |
| `rehearsed` | 演练成功终态、释放活动位；不转 landed 或发布 |
| 最新 `failed{bound\|stale\|ci_red}` | 明确答复后追加一次 `retry`（原操作仍 failed），或 `failed{declined}` |
| 最新其他 `failed` | 不可 retry；“不合”可补 `failed{declined}`，declined 后不可重试 |
| `main_intent` | `main_result` |
| `main_result{ok}` | `landed` |
| `main_result{unknown}` | `landed`，或 `main_result{non_ff}` |
| `main_result{non_ff}` | 操作结束（不算失败，下一个操作 `k+1`） |
| `main_result{denied}` | `failed{denied}` |
| `landed` | `reverted`（只改当前状态，历史上的 landed 保留） |

补充约束：
- 终态另含 `discarded`、`rehearsed`；不占活动位。终态不原地复活；`landed` 之后只允许 `reverted`，失败后的 retry/declined 按上表。
- `rehearsed{R}` 只用于 STG dry_run：当前 main 必须仍为 M0，R 在 prepared 后创建的最新 CI 必须 Succeeded。若重跑，以持久化的操作号及 `try:2` 导出的确定 run 名确认本次尝试，适配器核对 pipeline、精确 R 和演练来源标记；创建时间不能早于意图所在秒，不跨精度比较同秒先后（2026-10-26，修复 review 578 B1）。当前规则下第二道资格闸通过且窗口不挡。控制器在规则及相关行锁下重读并写入。它不是 landed，不占生产额度，不加入发布队列；可按精确 SHA 删除演练分支。
- 2026-10-26 统筹决策（review 578 B2）：出生即终态只允许 v1.1 `failed{bound}`，操作号必须是最新同根 discarded 的确定 k+1，且根任务预算确已到限；同一事件建立归属和失败状态，不先写 claimed，不占活动位。归属从前序记录恢复，不扩字段；重复扫描不得再造 k+2，旧 discarded 永久保留。
- retry 只绑定同根任务最新操作的 `bound/stale/ci_red`，同一失败只解除一次；新 claimed 消耗它，旧失败仍保留。6 小时从 retry 事件时间重新算，累计 8 次重放不清零。过期答复或旧操作答复不能解除新失败。
- `ci_kick`、`ci_rerun` 在一个操作里各最多一次。
- 写 `main_intent` 之前，必须已经有同一个 R 的成功 `ci_seen`，而且那次 run 是在 `prepared` 之后建的。

**v1.1 转移测试清单**（纯折叠与真实迁移 PG 两层）：
- Q2：branch_intent、branch_pushed、parked 分别到 discarded，两种 why；其他源状态、非法 why、v1 冒用新 kind 拒写；终态无活动位、可领取 k+1；碰撞不删他人的 SHA。
- Q3：成功最新 CI + 当前 main + 第二闸 + 窗口放行才 rehearsed；拒绝 PROD、错误 R、缺 CI、旧成功后新失败/运行/未知、重跑前成功、main 漂移、规则收紧、窗口阻挡；不可转 landed/额度/发布，可精确 SHA 清理且不重复演练，PROD 领取不受阻。
- Q1：三种可重试失败，各允许一次最新根任务匹配的 retry；其他失败、declined、旧操作、错根、重复、非控制器拒写；不原地复活；新 claimed 消耗一次；六小时重启但第九次禁止；“不合”只改最新操作且不可再 retry；旧 v1 整链继续折叠。

**STG 操作的合法转移**：
- 第一步是 `stg_snapshot{try:1}`；
- `stg_snapshot` → `stg_started` → `stg_result`；
- `stg_result{ok}` → `stg_verified` 或 `stg_failed`；
- `stg_result{failed}` → 用同一个 P、U 再记一次 `stg_snapshot{try:n+1}`（n ≤ 3），或 `stg_failed`。

**断点对账**：重启后，按折叠出来的状态处理。原则是先查外部、再补记录，不重复执行。

| 断在 | 查什么 | 补什么 |
|---|---|---|
| `prepared` 之后 | — | R 能按记下的提交时间和提交信息重建，SHA 不变 |
| `branch_intent` 之后 | `ls-remote` 看分支 | 指向 R → 补 `branch_pushed`；分支不存在 → 重推同一个 R；指向别的提交 → `discarded{branch_collision}`，开 `k+1`，旧分支按 SHA 条件删 |
| CI 期间 | 按 R 现读 CI | 照常继续 |
| `main_intent` 之后 | main 历史里有没有 R | 有 → 记 `main_result{unknown}`，再记 `landed`；R 若已被撤销，再记 `reverted`。没有、且 main 头仍是 M0 → 视为没发出去，不重推，转 `failed{bound}`，由新操作重来。没有、且 main 已经动了 → 记 `main_result{non_ff}` |
| `stg_snapshot` 之后 | 按确定的 run 名（操作号 + 尝试号）去查 | run 存在 → 补 `stg_started`；不存在 → 起 run |
| `stg_started` 之后 | run 的终态 | 补 `stg_result`，继续核验 |

**测试**：
- S1 在**真实迁移过的数据库**上做写入和折叠测试，确认 CHECK 能接受；
- 每个非法转移都要被拒写；
- 每个断点重启一次，不能重复执行，也不能误退回。

### 2.5 合入步骤（PROD；每个仓库同时最多一件「活动」）

1. **领取**：`eligibleToClaim` 为真的，按收下时间排；在流锁下写 `claimed`。处于 `parked` 的不占活动位。
2. **第一道闸**：按当前规则完整判一遍。
   - 碰底线 → 开问题；
   - 不再合格 → `failed{stale}` 并开问题；
   - 规则变了 → `parked{rule}`。
3. **重放**：在干净目录里，把 A cherry-pick 到 `M0` 上，写 `prepared`。
   - 冲突，或 patch-id 变了 → 失败；
   - base..M0 改过的文件和 A 有交集 → `failed{overlap}`（第一片如此）；
   - 没有交集 → 接受剩余风险（X6）。
   - 提交信息照第 2 稿写，另加 `Landed-By: agentrt-prod/<操作号>`。
4. **推落地分支**：先写 `branch_intent`，再推，再写 `branch_pushed`。
5. **等 CI**：每一轮先看 main 头、规则和资格；main 已经不是 `M0` 了，先记 `discarded{main_changed}` 释放活动位，控制器自动开 k+1 重放；不因旧 main 红而继续停放旧候选。按 CI 状态处理：
   - **Missing**：10 分钟后补建一次（`ci_kick`）；
   - **Unknown**：重读；
   - **Running**：超过 30 分钟 → `parked{ci_stuck}` 并开问题；
   - **Succeeded**：要求是「这个 R、在 `prepared` 之后建的、最新一次」，旧的成功不算；
   - **Failed**：看 `M0` 自己的 CI：
     - `M0` 绿 → 重跑一次（`ci_rerun`）；重跑仍失败记 `failed{ci_red}`；
     - `M0` 红 → `parked{main_red}`；
     - `M0` 的状态不明 → 只等。

   **总上限**：每个根任务最长 6 小时、最多重放 8 次。等窗口、等 main 变绿也算在内，到了就记 `failed{bound}`（§5 第 6 项）；只有明确 retry 重启六小时，累计八次不重置。第八次仍可完成，但若需要第九次则在当前操作记 failed{bound}，总上限优先于自动 k+1。演练成功写 `rehearsed` 收尾。
6. **第二道闸**：在**一个事务**里，按全局固定的锁序做完下面的事。
   - **锁序**：
     1. capability 锁（共享）；
     2. `ruleLock` + `hashtext('landing:dev')`（共享，照 `cardauto.go:136`，与规则写入互斥）；
     3. 计划节点，FOR SHARE；
     4. 任务，FOR SHARE；
     5. mission，FOR SHARE；
     6. 流 `landing-quota:<租户>:<当天 UTC>`；
     7. 流 `landing:<仓库>`。

     这与内核的锁序一致（`kernel.go:19-27`：steps → tasks → mission → streams）。规则写入也是先 capability 再 rule，所以不会死锁。
   - **持锁后依次**：重读当前规则 → `eligibleToPush` → main 头仍是 `M0`、窗口不挡 → 预留额度 → 写 `main_intent`。
   - **额度怎么算**：
     - 按「当天 UTC 配额流里不同根任务的 `reserved` 条数」计；同一个根任务同一天重放多次，只占一份；
     - 一旦写下就不返还，不管推送结果是成功、`non_ff`、`denied` 还是 `unknown`；
     - 跨过 UTC 午夜才恢复的操作，算在写 `main_intent` 的那一天；
     - 额度用完 → `parked{limit}`，第二天恢复。
7. **推 main**：不带 force。
   - `ok` → 确认 R 已在 main 历史里，再写 `landed`；
   - `non_ff` → 本次操作结束，回第 3 步，开 `k+1`；
   - `denied` → 停掉这个仓库的落地，开问题；
   - `unknown` → 按 §2.4 的断点对账处理。
8. **收尾**：按 SHA 条件删掉落地分支；把 R 加进 `stg_pending`。

### 2.6 和人手抢 main；窗口（A9、复核 538 §6）

**抢 main**：两边都只能快进，抢输的一方会被拒。
- D2（4.3）上线之前：落地不持窗口。抢输就重放，受第 5 步的总上限约束。
- D2 上线之后：连续抢输两次，第三次从重放到推 main 都持应用车道。

**接口**：按 4.3 的租约约定四个操作——`Acquire`、`Check`、`Renew`、`Release`。参数带操作号、目标 SHA、路径和令牌。自己持有的不挡自己。

**第一版仍用现在那个 ConfigMap，S3 顺带改共享的窗口代码**：
- `who` 带上操作号；
- 不再有无条件删除：读到过期的只返回「空闲」，不删（改 `window_store.go:191-194`）；主动释放和强制清除都改成带 resourceVersion 前提的 Update，把 `expires_at` 设成现在（替换 `:199-211`）；
- 读失败一律算「挡」。

**租约断了、run 还在跑**：
- 记 `parked{window}`；
- 继续盯这个 run 到结束，跑完核验才算 `stg_verified`；
- 不把「租约没了」当成「外部已经停了」；开问题。
- 4.3 之前，这段时间里别人可能拿到窗口。这是残余风险；缓解办法是每分钟续租，ttl 5 分钟。

**TOCTOU**：第 6 步读窗口和第 7 步推送之间有几秒空档。运行时自己起的 STG 发布都钉了 SHA，不受影响；人手用 `main` 起的发布仍可能撞上这几秒，交给 Owner 接受（§5）。这和前面「误删别人的新窗口」是两件事。

### 2.7 失败怎么办，mission 怎么关（A4、A5、复核 538 §3.3）

**2026-10-26 统筹决策（review 578 B2）**：若在 `discarded` 与领取 k+1 之间崩溃，恢复时 k+1 因六小时或累计次数到限（`bound`）拒领，控制器在仓库流锁下直接用一条 `failed{bound}` 事件建立 k+1。该操作出生即终态；k 的 discarded 不变。最新 k+1 按 v1.1 的明确 retry 规则处理：答复必须绑定它，后续新 claimed 消耗 retry、重启六小时，累计操作次数不清零。恢复收尾只依赖库内记录，不依赖当前规则或 Git/CI 可用。

**扫描顺序（2026-10-26，review 578 B3）**：每轮先完成所有无需外部来源的预算到限和终态收尾，再执行外部恢复与 Git 清理；清理有独立预算，待处理项分配各自剩余时间份额并逐项访问。旧分支全部超时也不能挡住本轮其他操作写入 `failed{bound}`。

**第一片只开问题，不自动修**：
- 一个根任务只开一个落地问题，去重键 `landing:<根任务>`；
- 不动任务状态，不调 `failWork`，不计进执行者成绩；
- 问题上有两个动作：
  - **「再试一次」**：控制器针对最新 `failed{bound|stale|ci_red}` 写 `retry{root, after_op, reason, by}` 后新开操作；其他失败不可重试，declined 永不可重试。照样重走资格和底线，不能借此绕过 A2；六小时重启，八次计数不清零；
  - **「不合」**：在该根任务最新操作写 `failed{declined}`（遵守 failed 的合法来源；已经 failed 时补记 declined），不另建操作；旧答复不能改写新操作。问题卡实际接线仍属 S3。

**S3 就改 `close.go`。** 落地范围内的每个根任务，结局分三种：
- **已交付**：`stg_release` 开着的，要 `stg_verified`；为 `none` 的，要 `landed` 且仍有效。
- **已处置、未交付**：`declined`、`stale`，或者 mission 标了 `no_merge`。
- **未了结**：其余一切，包括 `parked{rule}`（推荐：撤规则只是暂停，不算了结）。

mission 怎么关：
- 全部根任务都已交付或已处置，且至少一个已交付 → `done`；
- 全部只是已处置、一个都没交付 → `stopped`；
- 还有未了结的 → 保持 active。

Console 上把「已交付」和「已处置、未交付」分开显示。不在落地范围内的 mission，关闭规则不变。

**S4 才做自动修（R3）**：替代关系、原子创建、依赖解析、分支起算点，以及五个用例，都照第 2 稿。

### 2.8 发 STG（A7、A8、复核 538 §3.3、§7）

1. **什么时候发**：每个仓库一条待发布记录。没有活动的落地，或者最老的待发布已经等了 20 分钟，就开一个 STG 操作 `stg:<仓库>:<n>`。
2. **定快照**：持到窗口后定。P = 当时的 main 头；U = P 那次成功的 CI 实际克隆的 ui 提交，从克隆任务的 `commit` 结果读（S0 把它接进审计）。
3. **发前检查**：
   - 每个待发布的 R 都要过 `eligibleToDeploy`；
   - 对「上次 STG 发布 → P」的整个差异判权限；
   - P 的最新一次 CI 成功，且用的就是 U。

   有一项不过就不自动发，开问题，写明原因，例如「STG 要人发：差异含 X」或「P 含已撤步骤的结果」。
4. **尝试与接管要分开**：
   - run 名 = 操作号 + 尝试号 `try`。
   - 创建时结果不明 → 用同一个名字去查，查到就接管，不多建。
   - 确认失败、决定重试时，才在流锁下写新的 `stg_snapshot{try:n+1}`：P、U 不变，`not_before` 记退避后的时间。这样得到一个新的 run 名。
   - 最多 3 次，两次退避分别是 10 分钟、30 分钟；次数和退避都记在事件里，重启不清零。
   - CI 的补建、重跑也照这个办法。
5. **起 run**：`bifrost-deliver-platform`，`revision=P`、`uiRevision=U`，都是完整 SHA。
6. **核验**，四项都要过：
   - run 成功，且克隆的头就是 P；
   - `Deployed("stg")` 等于 P，三个镜像摘要都对；
   - rollout 已完成；
   - STG 的 platform-api `/health` 正常，报出的版本对得上 P（读法在 S3 接，网络是否通还没核实）。

   不用 `get_stg_smoke`，它查的是 Trade。
7. **收尾**：逐个确认待发布的 R 在 P 里仍有效，写 `stg_verified`，再放窗口。
8. **三次都失败**：写 `stg_failed`，开问题；待发布照旧显示；main 不回退。

### 2.9 被撤销的落地、坏落地（A11、复核 538 §7）

- `landed{R}` 记「曾经落地」，永久保留；`reverted{R}` 记「当前已撤销」。
- 推 main 成功之后、补记之前就被撤销的，两条都要记。不能因为 `MainResults` 排除了撤销的提交，就当作没推过。
- 依赖、STG 核验、「已上 STG」都按「当前仍有效」判。
- 已撤销的成果，要再落地就要一个新的明确决定。

**坏落地手册（第一片）**：
1. 收紧规则，停掉这个仓库的落地和发布；
2. 在最新的 main 上，经 `push-main.sh` 提交受检的 revert 或修复；
3. 由 Owner 或现有的发布入口，按固定 SHA 把它发到 STG，并核实；
4. 再决定要不要恢复规则。

第一片不做自动恢复。禁止 reset 和强推 main。PROD 照原来的审批政策。

### 2.10 `push-main.sh` 门槛的逐项替代（B4）

| 现有门槛 | 落地怎么做 |
|---|---|
| 只快进 | 保留；把 `non_ff`、`denied`、`unknown` 分开处理 |
| 血缘尾注 | `Agentrt-Task` 必须恰好等于收下的任务，`Change-Id` 恰好一个 |
| 确切提交的 CI | 只认 R 在 `prepared` 之后最新的那次 run；改掉「有过一次成功就算」的索引；补测试：旧的成功、新的失败或还在跑，都不能放行 |
| code-health | ci-platform 里已有；基线以那次 run 实际用的 infra 提交为准 |
| `go vet` | S0 加进 ci-platform |
| infra 快测 | S6 的 ci-infra 用同一份清单 |
| 窗口 | 读失败就挡；TOCTOU 已写明 |

### 2.11 分支去留

- `land/<环境>/<任务>/<k>`：落地、失败、discarded 或 rehearsed 后，按 SHA 条件删除（碰撞指向别的 SHA 不删）。`prune.go` 兜底：超过 24 小时、又没有活动操作的，也删掉。
- `agent/**`：规则不变。
- 工作目录用完即删，口径与 4.6 对齐。

### 2.12 Owner 看到什么，「零写入」怎么量（B5）

**Console**：
- 每件任务显示：根任务；A、base、R、`M0`；规则版本；CI run；待发布状态；P、U 和镜像摘要；发布失败；是否已撤销；下一次重试的时间。
- 「已交付」和「已处置、未交付」分开显示。
- 主动开问题的两条线：`parked` 超过 2 小时；待发布超过 1 小时。

**★ 怎么量**：取一个 mission 的完整事件链，从目标、授权、实现、检查、评审，一直到落地操作、Gitea 推送者、CI、STG run 和镜像摘要。在这段时间里核对：
- 推这两个仓库 main 的，除了落地身份之外的**所有**推送者，都要对上是哪个人或哪个线程；
- 所有不是运行时建的 PipelineRun；
- 统筹线程会话的全部写动作。

协调线程的写动作必须为 0。Owner 自己提目标、批正式审批单，单列，不算在内。S0 如果拿不到推送者，★ 就标「未验证」，不退回去只数尾注。

**占比**：数推送者是落地身份、且有对应 `landed` 记录的 main 提交。

### 2.13 与 `RecordLandings`、`merge_accepted.py`

- `RecordLandings` 不改，只给人手合进去的补记。
- `merge_accepted.py list` 当审计用。
- `plan` 丢掉「曾落地后被撤销」理由的问题，在 S7 修。

---

## 3. 切片

| 片 | 做什么 | 只有它能拦住的用例 | 要 Owner |
|---|---|---|---|
| **S0 前置** | P0 清单和改动；ci-platform 加 vet，接上 ui 的 `commit` 结果；实测 Gitea 推送者；D-L5 归档已完成，标记经新动作在 S3 打开前完成 | ① 只有落地身份能推 main（A1）<br>② CI 测试读 `.git/config` 拿不到凭证（538 §2）<br>③ 镜像同步任务拿不到管理员令牌（538 §2）<br>④ 只有 vet 能抓到的错误会让 CI 变红（B4） | 定信任假设；应用 RBAC 和 Tekton 改动；建只读用户、克隆身份、演练用户和对应 Secret；新动作随平台版本发布后批 D-L5 的 D 级单（S3 打开前） |
| **S1 规则、资格、状态协议**（不碰 git） | 规则解析和收紧判断；底线；路径和纯展示判定；`facts` 和四个阶段；`note.landing` v1 的校验器、折叠函数、转移表 | ① **推 main 成功的结果，`eligibleToDeploy` 为真，`eligibleToClaim` 为假（已经在 main 上），不会被再领一次**（538 §3.1）<br>② **在真实迁移过的数据库上，写入并折叠全部 kind，CHECK 都接受**（538 §3.2）<br>③ 非法转移被拒写<br>④ 规则允许 `api/internal/actions/tier.go`，仍被底线拒（538 §5）<br>⑤ 旧 mission 里启用后才收下的被拒；签名当天零点之后、真实启用之前收下的被拒（538 §3.1）<br>⑥ 目标计划被替代、未被替代，各有正反用例<br>⑦ main 历史读失败，不判成「从未有过」<br>⑧ 第 2 稿 S1 的 ①–⑥ 保留 | 无 |
| **S2 STG 演练** | git 卫生；推 `land/stg/**`；按状态等 CI；断点恢复 | ① 旧 main 一直红、新 main 已绿 → 丢掉候选重放<br>② 旧的成功、新的失败 → 不放行（B4）<br>③ 等窗口用满 6 小时 → `failed{bound}`，让出活动位（538 §4）<br>④ 第 2 稿 S2 的 ③④ | 镜像加 git；演练令牌的 Secret |
| **S3 PROD 第一片**（B6） | 第 1 版规则；推 main；落地问题；改 `close.go`；钉 SHA 的 STG 发布和尝试号；窗口代码 | ① **并发收紧的两种次序**：规则写在第二道闸之前，挡住推送；写在之后，算已落地（538 §4）<br>② CI 期间加 `no_merge` 或撤步骤 → 不推<br>③ 人手合进去又撤销、还没补记 → 不推<br>④ **STG 第一次 run 失败，第二次真的重新执行；创建结果不明时不多建**（538 §3.3）<br>⑤ **只有已处置的 mission 关成 stopped；有已交付的关成 done；撤了规则的不关**（538 §3.3）<br>⑥ P、U 定下后 main 又前进，发出去的仍是 P、U；定快照前混进了人手迁移 → 拒绝自动发（538 §7）<br>⑦ **读到过期窗口、另一操作随即抢到新窗口，旧的读取方不会把新窗口删掉**（538 §6）<br>⑧ 租约断了、run 还在跑 → 不算 verified，开问题<br>⑨ Trade 的 smoke 绿、platform 健康失败 → 不算 verified（538 §7）<br>⑩ 推了 main、人手又推了后继 → 记成已落地<br>⑪ 推成功后、补记之前就被撤销 → 两条记录都写（538 §7）<br>⑫ 落地身份推 infra、建标签都被拒 | **签第 1 版规则**；建 `agentrt-lander`，加进 platform main 的推送白名单，配 Secret；核对标签规则；**批发布单** |
| **★** | Owner 提一句改 Console 文案的小目标，一路走到 STG；按 §2.12 量 | — | 提目标 |
| S4 自动修（R3） | 照第 2 稿 | 照第 2 稿的五个用例 | 批发布单 |
| S5 放宽 `api/` 的一部分 | 按代码清单重审底线；第 2 版规则；X6 | 规则允许 `approvals/**`，仍被拒 | 签第 2 版 |
| S6 infra | ci-infra 全套接线；允许目录的引用测试 | 两个仓库抢当天最后一份额度，只有一个拿到（538 §4）；碰 `k8s/**` 的永远不自动合 | 应用流水线；签第 3 版；加 infra 的推送白名单 |
| S7 | `push-main.sh` 认 `Agentrt-Task`；占比脚本；修 `merge_accepted.py` 的 `plan` | 尾注伪造的提交不算进占比 | 无 |

**粗估**：S0–S3 加 ★，约 6–8 个工作日；Owner 约 2.5 小时，分 4 次。把握低：P0 要改克隆凭证和镜像同步任务，S0 实测之后再估。

---

## 4. 架构级选择

| # | 选项 | 推荐 |
|---|---|---|
| X1 谁执行 | A：workers 控制器 / B：agentd / C：Tekton | **A**（前提是 P0 和信任假设成立） |
| X2 第一片的失败 | 只开问题，S4 再做 R3 / 现在就做 R3 | **只开问题** |
| X3 状态存储 | `note` + 子协议 v1，不加 DDL / 新的顶层事件类型（要 migration、词表一致性测试、STG→PROD 的库发布和审批；S0–S3 估计各加约 1 天） | **note + 子协议** |
| X4 STG 演练 | 只推 `land/stg/**` / 用探针仓库真推 | **只推 `land/stg/**`** |
| X5 infra 的 CI | 新建 ci-infra 并全套接线 / 在 06 上跑检查 | **新建** |
| X6 base 漂移后的评审 | 接受剩余风险，有交集就不合 / M0≠base 一律做集成复核 | **第一片接受**；S5 起有交集的做集成复核 |
| X7 软上限的例外 | 不设 / 独立的 C 级单 | **不设** |

---

## 5. 待 Owner 定的点（按「先定哪个才能开工」排序）

| 序 | 定什么 | 推荐 | 另一选项与代价 | 卡住哪一片 |
|---|---|---|---|---|
| 1 | P0 证明到什么范围、信任假设（§2.0） | 做完整的「身份 → 凭证 → 间接入口」清单，只留落地身份一个例外；信任主体是「已批准的 PROD 平台代码整体」 | 只承诺 STG 隔离、信任整个 PROD SA：P0 的保证要重写，残余权限要写明。或者平台进程之间也做机械隔离：要另建 SA、RBAC、准入 | S0，进而全部 |
| 2 | X1 谁执行 | A | B：执行者读得到令牌；C：多两条流水线 | S1 起 |
| 3 | X3 状态存储 | `note` + 子协议 v1，不加 DDL | 新事件类型：要 migration、库发布和审批，S0–S3 估计各加约 1 天 | S1 |
| 4 | 第一片范围（X2） | B6：Console 窄范围、一件在途、失败开问题；S3 就接关闭和对账 | 第一片同时做 R3：S4 的五样前移，估算另算 | S1–S3 |
| 5 | 资格、关闭、撤规则的语义（§2.2、§2.7） | 资格分四个阶段；撤规则只暂停、mission 不关；declined 和 stale 算已处置、未交付 | 撤规则即终结：恢复规则不复活旧的根任务，要另定重启流程和界面 | S1、S3 |
| 6 | 最后一道闸、额度、总上限（§2.5 第 6 步） | 接规则锁；按租户、UTC 日、根任务去重预留，不返还；6 小时 / 8 次的总上限把等窗口也算进去 | 等窗口不计入总上限：要写清暂停计时和最长实际历时，并补用例 | S1、S3 |
| 7 | 硬底线与恢复（§2.3、§2.9） | 第一片 `api/**` 全拒；S5 按代码清单重审；坏落地由现有入口按固定 SHA 修复 | 现在就支持自动恢复：要新增有明确授权的恢复操作，以及失败后的对账 | S1、S3 |
| 8 | X4、X6、X7 | 照 §4 | 照 §4 | S2、S3 |
| 9 | 接受的剩余风险 | 逐项接受：无交集时的语义漂移、纯展示只靠字符串加评审、窗口 TOCTOU、集群内 HTTP、4.3 之前租约断了别人可能进来 | 加最终集成复核 / 把文案文件逐个点名 / 提前做 4.3：分别增加评审工作、缩小适用范围、增加实现成本 | S3 签名前 |
| 10 | 第 1 版规则的内容（§2.3） | 照稿 | 改条目 | S3 签名时 |
| 11 | `push-main.sh` 的替代、Owner 看到什么、★ 怎么量 | 照 §2.10、§2.12 | — | S3、★ |
| 12 | 旧的 20 件（D-L5） | 资格规则本身就排除它们；D-L5 按 mission 逐件确认后，经新动作 `mark_missions_no_merge` 标 `no_merge`（Owner 2026-10-26 选 A）；D 级审批 + runtime 事件，同批全成或全退，随平台版本发布 | 归档 2026-10-25 完成；#165 于 2026-10-26 16:01Z 执行，被事件 guard 拒绝，未改状态；不用裸 SQL 补写 | S3 打开前 |
| 13 | X5 infra 的 CI | 新建 ci-infra 并全套接线 | 在 06 上跑检查，更弱 | S6 |

## 6. 没核实的

- 线上 RBAC、准入规则是否与仓库里的清单一致；各 Gitea 凭证的实际权限范围；CI 实际挂了哪些东西。这些在 S0 实测。
- Gitea 能否给出推送者。S0 实测。
- 镜像同步任务最少需要什么权限。S0 实测。
- STG 的 platform-api `/health` 从 workers 能不能连上、会不会报版本。S3 接线时核实。
- 复核 533 的两个探针我没有重跑。

---

## 7. TD-447 第 4 项：首次领取的持久交接（2026-10-28 夜班统筹，设计稿 v1）

### 7.1 问题（实读 platform `c3cb9e76`）

- `store/close.go` `landingHolds`：从没被领取过的根任务（`implement`，仓库已启用落地，mission 不是 `no_merge`，mission 创建与任务 accepted 都不早于 `EnabledAt`），只在 accepted 后 `landingClaimGrace = 2 分钟` 内持住 mission。
- `store/landing_drill.go` `ClaimLandingDrill`（830c40a3 起）：第一段短事务读绑定 → **不持锁**读 Git（Result、根 History、各依赖 History）→ 第二段事务按同锁序重读、核证据键、按第二次读判资格。读 Git 期间不持 mission 锁，Close 可以在这时关 mission。
- 结果（复核 646 §5）：读取跨过 2 分钟宽限的那一次领取，在第二段读到 mission 已 `done`，返回 stale/changed、不写记录；`LandingCandidates` 只列 active mission 的任务，这件活从此不再被扫描——**演练永久错过它，且没有任何记录说明它被错过**。繁忙的一轮（其他操作的外部读取、`max_in_flight_per_repo` 被占超过 2 分钟）同样会错过（复核 640 R640-1）。
- 宽限是一个**无记录的计时器**：持住与否只取决于「现在离 accepted 多久」，与领取有没有发生、有没有被拒、为什么被拒无关。

### 7.2 目标

1. 只要扫描器在运行，一个进入落地范围的根任务**必然**以一条落地流上的记录结束：被领取（`claimed`），或被明确拒绝（带原因），或到限（`bound`）。
2. 在它结束之前，Close 不关它的 mission；但持住**有界**：沿用现有 6 小时 / 8 次的根预算，Close 自己再留 15 分钟余量作兜底（扫描器不运行时 mission 也一定会被放开）。
3. 不加 DDL、不加表，仍是 `note.landing` 子协议；不放宽已有操作的转移；不把 Git 读取放回锁内。

### 7.3 选项

**A. 接受时写「排队」记录。** 任务 accepted 的同一事务里，若仓库启用落地，在 `landing:<仓库>` 写 `queued{task}`；Close 持住「已排队、未领取、未拒绝」的根。
- 优：从 accepted 那一刻就有持久记录。
- 缺：把落地规则读取接进内核的接受路径（`MoveTask` 一类的事务），耦合两个子系统；被拒的根仍要另记一条才能放开，等于要两种新记录；接受路径一旦写落地流失败，任务接受也失败。

**B. 默认持住，终局拒绝落成记录（推荐）。** 不写排队记录：「在落地范围内、从没领取」本身就是由库内事实推出来的排队状态（`landingHolds` 今天已经在算这些条件）。改两处：
1. `landingHolds` 对「从没领取」的根，把 2 分钟宽限换成**有界持住**：直到该根在落地流里有了第一条操作记录，或 `accepted + landingHoldLimit`（6 小时 15 分）为止。删除 `landingClaimGrace`。
2. 领取被**终局性**原因拒绝时，第二段事务（持 task → mission → 仓库流锁）在落地流写一条**出生即终态**的操作 `failed{why}`，操作号 `land:<task>:1`，于是 `RootPending` 为假、Close 放开、`unsettled` 以 `BlocksClaim` 过滤、不再读 Git。到限同理：第一段事务发现「从没领取且 `now ≥ accepted + 6h`」时写 `failed{bound}`（只读库，不读 Git）。
- 终局 / 暂时的划分（`landing.EligibleToClaim` 的原因）：
  | 原因 | 处理 | 理由 |
  |---|---|---|
  | `stale`（mission 非 active、`no_merge`、计划不合格） | 记 `failed{stale}` | 已处置（§2.7）；可经 retry 再开（retry 本来就接受 stale） |
  | `result`（未 accepted、无 attempt、A/Base 非法、非单提交） | 记 `failed{result}` | 接受后这些事实不变；不可 retry |
  | `history`，且 History 为 `effective` / `reverted` | 记 `failed{history}` | A 已经在 main 上出现过；不可 retry |
  | `history` 且 `unknown`、`dependencies`、`rule`、`limit`、`changed` | 不记，下一轮再试（带退避，见 4） | 会自己变；最终由 6 小时到限收尾 |
  | `before_enable`、`mode`、`terminal` | 不记 | 候选 SQL 和 `unsettled` 已排除，从没领取的根到不了这里 |
3. 协议：`failed` 出生即终态目前只允许 `bound` 的 k+1 后继（复核 578 B2）。新增**第二种**出生即终态，条件全部满足才合法：v1.1；`op == land:<task>:1`；该 task 在流里没有任何操作；`why ∈ {stale, result, history, bound}`。`result`、`history` 只对这种出生即终态的 `failed` 合法（`parked` 等其他 kind 的 `why` 集合不变）。已有转移一条不动。这条操作没有 attempt/A/ref，`Task` 由操作号解出；`DryRun` 记为 true（只由 STG 扫描器写）。它计入根预算（第 1 次），retry 之后的领取是 k=2，与 §2.5 的「八次不清零」一致。
4. 暂时性拒绝的退避：B 让暂时被拒的根在 6 小时内持续是候选（原来 2 分钟后 mission 关掉就不再是），若每 15 秒都重读一次 Git，就是复核 641 §3 说的「拒绝没有退避」被放大。控制器内存里按任务记退避：`changed` 不退避；其余暂时原因 1、2、4、8 分钟递增，封顶 15 分钟；领取成功或任务离开候选清单即清除。只放内存：重启后最多早试一次，不影响正确性。
- 优：没有接受路径的耦合；只有一种新记录，且复用现有的 Terminal / BlocksClaim / RootPending / retry / Close 机制；S3 的「一个根任务一个落地问题」直接覆盖它（落地问题按 `failed` 开）；§2.7 的结局分类里 `stale` 已是「已处置」，`result`、`history` 一并归「已处置、未交付」。
- 缺：扫描器在运行而规则一直把某根判为暂时不合格时，这个 mission 会被持满 6 小时；在 PROD 有落地规则但没有扫描器的时段，每个 mission 都会被持 6 小时 15 分（今天 PROD 没有落地规则；S3 接线时扫描器与规则同时上）。
- 风险：把出生即终态从一种扩到两种。缓解：合法性条件写死在 `Apply`，测试覆盖「已有操作的 task 不能出生即终态」「op 号不是 1 不行」「why 不在集合里不行」「旧 v1 不行」。

**C. 缩小时间窗：Close 读到「领取正在进行」就不关。** 用 advisory lock 或 Redis 标记表示「某根的领取在读 Git」，Close 见到就跳过。
- 缺：不持久，崩溃即丢；依旧没有「被拒/错过」的记录；advisory lock 在连接池里易错（复核 646 的连接问题）。不推荐。

**D. 加大宽限（例如 30 分钟）。** 最小改动，但仍是无记录的计时器，控制器停摆超过宽限就照样错过。不推荐，复核 646 §5 已明确否定。

### 7.4 推荐 B 的细节

- **Close 的条件**（`landingHolds` 中「从没领取」一支）：`enabled && accepted != nil && !accepted.Before(EnabledAt) && now.Before(accepted + landingHoldLimit)`。「从没领取」= 流里没有该 task 的任何操作（含出生即终态的 `failed`）。规则被撤回时 `enabled` 为假、照旧放开（与今天一致；「撤规则只暂停」仍是 §5 第 5 项待定）。
- **领取**（`ClaimLandingDrill`）：
  - 第一段（库内）：`n == 0` 且 `now ≥ facts.AcceptedAt + 6h` → 写 `failed{bound}`（`land:<task>:1`），settled。
  - 第二段：资格判定为上表「记」的原因时，在同一事务里写出生即终态的 `failed{why}`，返回的 decision 不变（调用方看见的原因与今天相同）。证据键变了（`changed`）不记。
  - 第二段读到 mission 已非 active（规则撤回后被关、或过了 6 小时 15 分兜底）同样记 `failed{stale}`：给错过的根留下记录。
- **扫描**（`LandingDrillPass`）：`unsettled` 已因 `BlocksClaim` 跳过这些根，不再读 Git；新增内存退避。
- **时间**：持住按 `accepted` 计、领取到限按 `accepted + 6h` 计，都用调用方传入的同一个 `now`；「两段共用一个 now」的整体时间策略仍是 S3 必做 ②，本项不改。
- **不变的**：`claimed` 之后的持住（`RootPending`、`AtMain`、6 小时 15 分）、到限收尾、retry 的锁序（复核 647）、缓存折叠（第 3 项）。

### 7.5 测试（PostgreSQL；旧代码上必须红）

1. 慢读不再错过：根的 Result 回调阻塞；另一连接把事件时钟推过 2 分钟后跑 `CloseMissions` → mission 保持 active；放开回调后领取成功写 `claimed`。旧代码：mission 被关、领取返回 stale/changed、无记录。（现有 `TestConcurrentCloseDuringClaimReads` 的「past the grace」分支把这种错过当期望值，要改成新期望。）
2. 终局拒绝落记录、放开 mission：History 返回 `effective` → 领取返回 `history`，流里有 `failed{history}` 的 `land:<task>:1`；随后 `CloseMissions` 立刻关掉 mission；下一轮扫描不再调 Result/History。
3. 暂时拒绝持住：依赖不生效 → 无记录；时钟过 2 分钟、过 1 小时，Close 都不关；过 6 小时 15 分放开。
4. 从没领取到限：时钟过 accepted + 6h → 领取第一段写 `failed{bound}`，不调任何 Git 回调，Close 放开。
5. 协议单测：出生即终态的合法 / 非法组合（见 7.3 B 的风险一条）；`result`、`history` 对 `parked` 不合法；retry 可作用于出生即终态的 `failed{stale}`，不可作用于 `failed{result}`。
6. 退避：被 `dependencies` 拒绝后，紧接着的一轮不调 Git 回调；退避到期后再调。

### 7.6 不在本项

- S3 必做 ①（答复结果记录、先落库再 Ack）、②（各道闸的时间策略）、③（main 对账器与 `failed{denied}`）。
- 「撤规则只暂停」（§5 第 5 项，Owner 待定）。
- 拒绝原因在 Console 的展示（S3 的落地问题）。

### 7.7 设计稿 v2（2026-10-28 00:xx，回应复核 651 的 3 个阻断、5 个应修）

复核 651 认可方向（库内推导排队 + 终局拒绝落记录），判 v1 三个阻断。v2 采用它推荐的「B + E（关闭前数据库结算）」，并把契约写窄、写准。v1 中与下文冲突处以 v2 为准。

**契约（替换 §7.2）**

1. **交接范围**只由持久事实决定，与当前规则无关：`implement` 根任务，仓库落地流有 `enabled` 记录（`EnabledAt`），mission 创建与任务 accepted 都不早于 `EnabledAt`，mission 不是 `no_merge`。规则撤回或到期**不让根退出范围**（§5 第 5 项已定「撤规则只暂停」，v1 写成待定是错的，N651-1）：撤回只停领取、不读 Git，记账义务不变。
2. **不变量**：`CloseMissions` 绝不在范围内的根「没有任何操作记录」时关掉它的 mission。到 `accepted + 6h` 仍没有记录的根，由 Close 在关闭事务里自己先写 `failed{bound}`（`land:<root>:1`）再关——记录与关闭同一事务（B651-1、B651-2 的兜底，不依赖扫描器在跑）。
3. **扫描器的数据库阶段**（新，`SettleUnclaimed`）：每轮在 `SettleLandingDrillBounds` 之后、任何外部读取之前，不看当前规则、不受退避与工作预算影响，枚举范围内、没有操作的根，按 task → mission → 仓库流的锁序逐根重查后幂等追加：mission 已是 done/stopped/expired → `failed{stale}`；`now ≥ accepted + 6h` → `failed{bound}`。被 Owner 叫停的 mission、被饿死的扫描，都在这里留下记录（B651-2）。
4. **时间契约**（B651-3，选「两段预算、明说」）：首次交接最多 `accepted + 6h`；领取后沿用现有六小时 / 八次预算，从首次领取（或 retry）起算。所以一个根从 accepted 到终局最长约 12 小时（再加 retry 另计、`AtMain` 等对账不限时、mission 里其他任务没完时本来不归 Close 管）。不统一起点：统一需要把 accepted 时间写进 `claimed`（协议加字段），不值得在 S2 做。
5. **重绑出范围**：合法 `rebind_step` 把 accepted 根移到 `EnabledAt` 之前创建的 mission，按第 1 条定义它就不在范围内，不持、不记（它在新 mission 里本来就永远不合格）。这是明说的契约，不是遗漏；若以后要求「曾进入范围」可追溯，再上选项 A 的入队凭据。

**终局 / 暂时（替换 §7.3 B 的表，R651-2、R651-4）**

| 领取时的事实 | 记录 | 说明 |
|---|---|---|
| mission done/stopped/expired、`no_merge`、步骤 dropped、目标任务的产出计划已被新计划取代 | `failed{stale}` | 不会自己恢复 |
| mission paused、步骤 stopped、其他计划不合格 | 不记，等 | 可恢复；到 6h 记 bound |
| Result 非单提交 / A、Base 非法 | `failed{result}` | 已 accepted 的结果不变 |
| History = effective | `failed{in_main}` | A 已在 main 上（人手合入）；**不是「未交付」**，S3 按 main 与 STG 证据对账 |
| History = reverted | `failed{reverted}` | 曾在 main 上后被撤销；与上一行分开 |
| History unknown、依赖未生效、规则不放行、额度、证据键变了（changed）、外部读取报错 | 不记，等（带退避） | 到 6h 记 bound |

新增的 `why` 只有 `result`、`in_main`、`reverted`，**只**对出生即终态的 `land:<root>:1` 合法（Parse 只对 `failed` 放行，Apply 对已有操作的 `failed` 转移拒绝）；`stale`、`bound` 沿用。retry 仍只接受 stale / bound（协议已如此）；对已关闭 mission 的 retry 会被 `ErrLandingMissionClosed` 拒绝——即「某次 stale 后自动尝试停止，要人工重启」，重启已关闭 mission 的流程不在本项（R651-2 的策略选择，明写）。

**出生即终态的形状（R651-1）**：v1.1；`op` 精确为 `land:<合法 task id>:1`；流里没有该 task 的任何操作；折叠后 `Task`、`ClaimNumber=1`、`ClaimedAt=LastAt=事件时间`、`Phase=failed`、`Outcome=why`、`Retried=false`，其余为空。领取只在第二段锁内读到 `n == 0` 时写它，返回空 op（不触发「一轮只领一件」的 break）。已有 born-bound 后继（discarded、non_ff、已 retry 未领取）一条不动。

**读取顺序（R651-3）**：领取路径里，Result 已判非单提交就不再读 History 和依赖；根 History 已是 effective / reverted 就不再读依赖——确定的拒绝不被后面的读取错误盖住。外部读取报错照旧不记，进入退避。

**退避（R651-5）**：只放内存；1、2、4 分钟，封顶 5 分钟；领取成功、`changed`、仓库流的操作数或 retry 数变化时清空；读取报错也退避。到限记账（第 2、3 条）完全不经过退避。明说代价：退避期间资格短暂恢复又消失，可能错过一次本可成功的领取，最终记 bound。

**测试（补 §7.5）**：协议正反矩阵（三个新 why 与 stale/bound、v1、错号、已有操作、普通 failed/parked 拒新 why、retry 后 k=2、result/in_main/reverted 拒 retry）；Close 在慢读期间（3 分钟、1 小时）不关；Close 到 6h 自己写 bound 再关、同一事务；Owner 叫停的 mission 由数据库阶段记 stale；数据库阶段在没有规则、没有 Git 来源时仍记 bound；Result=false 后 History 报错仍记 result；History effective → in_main、mission 立即可关；退避的单测。

### 7.8 复核 652 结论与落地（2026-10-28 夜班）

复核 652（gpt-6-astra，xhigh）：**B651-1/2/3 均解除，无新阻断**；B651-1 是按 v2 收窄后的「当前绑定范围」解除（重绑出范围不持不记，见 §7.7 第 5 条）。应修与小问题的处理：

- R652-1（Close 写流后的折叠缓存）：Close 的折叠在本事务追加**之前**从已提交行读出，追加后（成功或失败）立即把该流移出缓存，下一个 mission 重新折叠；不在缓存里发布未提交状态。代码注释写明；没有加「保存点回滚后同 seq 被别的连接占用」的专门测试。
- R652-2（确定性错误分类）：领取路径对数据库已能判定的结果（无 attempt、A/Base 非 SHA）不读 Git（Base 另有表约束）；Result 非单提交不读 History，History 终局不读依赖——确定拒绝不被后续读取错误盖住。适配器把「血缘非法」报成普通 error 的类型化分流**没做**（仍会退避、到 6h 记 bound），列为后续。短路只在领取专用读取里，push / deploy 走原来的完整读取。
- R652-3（历史证据）：`in_main` / `reverted` 的记录正文写 attempt、A、base、mission 状态，以及 main 上命中的提交和读取时的 main 快照（来自那一次 History 读取）。
- R652-4（退避失效信号）：世代改为每个操作的 phase/outcome 加每个 retry 的 after_op/consumed_by/时间；规则新版本、配额复位只在等待结束时被看到（最多 5 分钟），任何一根的新记录会清空全部等待（粗，但不错），注释写明代价。
- N652-1：新生的出生即终态操作 `DryRun=false`、Attempt/A/Ref 为空，表示「从未运行」，不是生产执行证据；retry 集合仍是 bound/stale/ci_red（新增的 result/in_main/reverted 不可 retry），§7.7 那句「只接受 stale / bound」指新增的首次失败。
- N652-2：「6 小时」是到限判定，不是墙钟提交保证：两段领取仍共用调用时的 `now`（S3 必做 ②），T+5h59m 开始的领取可能在 T+6h01m 写下 claimed；记录在下一次成功的数据库结算或 Close 提交时出现。
- N652-3：测试已按 v2 重写（见提交说明）。

## 8. S3 必做 ①：落地答复的处理结果先落库、再 Ack（2026-10-28 统筹，设计稿 v1）

### 8.1 问题（实读 platform main `6ea51e0e`）

- `controller/landing_answer.go` `LandingAnswer` 读绑定到「根 + 操作」的问题卡；只要是 answered、console 渠道、有答复者，就在一个事务里调 `store.ApplyLandingAnswer`，把错误原样返回。它不 Ack，也不记录这张卡被怎么处理过（复核 647）。
- `ApplyLandingAnswer` 的「不适用」全部是普通 error：不是最新操作、答复早于操作、retry 但操作不是 failed 或答复早于失败；mission 不是 active 时是 `ErrLandingMissionClosed`。错误让事务回滚，所以**拒绝不留痕**；S3 若每轮扫描 answered 卡，同一张卡每轮报同一个错，永远不 Ack；若提前 Ack，Owner 只看到「已回答」，不知道 retry 没生效。
- 今天 `LandingAnswer` 只有测试调用（S3 才接线），所以这是接线前的语义修正，生产无行为变化。

### 8.2 目标

1. 一张答复卡（question id）**恰好被处理一次**：结果持久记录，进程重启、Ack 失败、重复扫描都不会再执行第二次。
2. 结果分三类，记录里写明：`applied`（写了 retry 或 `failed{declined}`）、`moot`（没什么可做，Owner 不用管：已 retry、已 declined、卡绑定的操作已不是最新、卡被晚答到失败之前、未知选项）、`refused`（Owner 要知道：mission 已不是 active，retry 没生效）。
3. 先落库、后 Ack：记录与 retry 同一事务提交之后才 Ack；Ack 失败下一轮重试 Ack，不重做业务。
4. 临时错误（数据库、读卡超时）不记录、不 Ack，下一轮重来；它与业务拒绝分开，不进入「每轮同一个错」的循环。
5. 不新增事件类型、表或列（避免改 `event_type` 约束的迁移）。

### 8.3 设计

**记录**：落地流 `landing:<repo>` 上一条 `note`，body 没有 `landing` 键（`LandingState` 只折叠 `body ? 'landing'` 的 note，见 `store/landing.go:17`，所以协议状态不受影响），而是：

```
{"text": "Landing answer <outcome>: <一句话>",
 "landing_answer": {"question_id", "root", "op", "choice", "outcome": "applied|moot|refused",
                    "why", "by", "answered_at", "mission_state"}}
```

事件的 `MissionID`、`TaskID` 填根的 mission 与根任务，所以它出现在 mission 时间线上。`why` 是封闭词表：`retry`、`declined`（applied）；`already_retried`、`already_declined`、`superseded`、`not_failed`、`answered_before`、`unknown_choice`（moot）；`mission_not_active`、`not_retryable`、`not_declinable`（refused）。

**实现时补的（v1.1）**：协议只允许对 `bound`、`stale`、`ci_red` 的失败 retry（`landing/protocol.go` `Apply`），其他失败上的 retry、协议不收的 `failed{declined}` 原来都是 Append 报错、整个事务回滚；现在先用 `landing.State.Check`（复制状态后试 Apply，不改原状态）判断，协议不收就记 `refused{not_retryable|not_declinable}`。`landing_answer` 是 `note` 的新可选字段，在 `store/vocab.go` 登记并校验封闭词表；这是 Go 侧字段表，不是数据库约束，不需要迁移。

**`store.HandleLandingAnswer(ctx, db, q, root, op) (Handled, error)`** 取代 controller 里直接调 `ApplyLandingAnswer`：

1. 一个事务，锁序不变：task `FOR SHARE` → mission `FOR SHARE` → 仓库流（`lockStream`）。
2. 锁下先查去重：同一流上已有 `body_json->'landing_answer'->>'question_id' = q.ID` 的 note → 返回已记录的结果（`Handled{Outcome, Recorded: false}`），不写任何东西。
3. 否则按现有判断得出 outcome / why；`applied` 时照旧追加 retry 或 `failed{declined}`，紧接着追加记录 note；`moot` / `refused` 只追加记录 note。**这些都不再是 error**，事务正常提交。
4. 只有数据库错误、锁超时等返回 error（事务回滚，什么都不记录）。

**`controller.LandingAnswer`**：读卡（有超时）→ 卡不满足条件（未答、非 console、缺答复者或时间）照旧什么都不做 → `HandleLandingAnswer` → 成功提交后调 `c.ack()(q.ID)`；Ack 失败只返回 error，下一轮第 2 步去重后再 Ack。`refused` 额外返回一个可识别的结果（不是 error），S3 接线层据此在 For you 给 Owner 一张说明卡（文案与是否给「开新 mission」按钮由 S3 定；本项不自动重开，按复核 647：非 active 包括 paused，不能当成重开授权）。

**去重键**只用 question id：卡与（根，操作）的绑定由读卡回调负责（`read(ctx, root, op)`，S3 提供），一张卡只绑定一个（根，操作）。`store.Question` 不带根与操作，所以本项不另做核对；同一 question id 若被不同（根，操作）调用，第 2 步按流上已有记录返回，不会二次执行。

### 8.4 锁序与并发

- 与 Close：二者都先拿 mission 行锁（答复 SHARE，Close NO KEY UPDATE），在 mission 行上串行；答复后追加的记录只写仓库流，Close 的 bound 写入也是 mission → 流，不成环（与 §7.7 同一锁序）。
- 两个进程同时处理同一张卡：流锁串行化；后到的在第 2 步看到记录，返回已处理。
- 记录与 retry 同一事务：不会出现「retry 写了、记录没写」或反过来。

### 8.5 测试（PostgreSQL；旧代码上必须红）

1. mission 已关后答复 try_again → 记录 `refused{mission_not_active}`、无 retry、事务提交；再处理一次 → 返回同一结果、不再写；旧代码返回 error 且什么都不留（红）。
2. Ack 失败：处理成功、Ack 返回错误 → 第二轮不再写 retry、只 Ack 一次成功；计数 retry 恰为 1。
3. 「重启」：新 Controller 实例处理同一张卡 → 去重命中。
4. 临时错误：用测试钩子让事务在写记录前失败 → 无记录、无 Ack；下一轮正常 applied。
5. moot 各 why 一例（已 retry、已 declined、不再是最新操作、答复早于失败、未知选项），每例只写一条记录。
6. 并发：两个连接同时处理同一张卡 → 恰好一条记录、一条 retry。
7. `LandingState` 折叠结果不受记录 note 影响（与不写记录时相同）。

### 8.6 不在本项

- For you 上的说明卡与文案（S3 接线）；mission 关闭后是否允许 Owner 重开或开新 mission（S3 政策）。
- ②（时间策略）、③（main 对账器与 `failed{denied}`）。

### 8.7 复核 655 与落地（v2）

复核 655（gpt-6-astra xhigh）：1 阻断、5 应修、2 小问题；锁序与单事务方案通过，没有新锁环。处理：

- **B1 协议拒绝**：先用 `landing.State.Check` 判断，协议不收记 `refused{not_retryable|not_declinable}`；只有数据库或流解析错误返回 error。
- **R1 分类**：moot 只剩「什么都不用做」：`already_retried`、`already_declined`、`superseded`（真实后继）。`not_failed`、`answered_before`、`unknown_choice` 改为 **refused**：旧答复不适用，Owner 在新卡上重新确认（新失败要新 question id，S3 契约）。卡绑定的操作不存在或不属于该根 → `ErrLandingAnswerBinding`，不记录（S3 的绑定错误）。已 retry 的判定在 mission 状态之前；`do_not_merge` 不看 mission 状态。
- **R2 原文**：记录加 `answer_text`（可为空）、`channel`。
- **R3 测试**：v11 夹具每张卡用不同 id；新增「已存结果优先于再判断」（成功后出现后继 / 被拒后 mission 恢复，均返回原结果）、两次 Append 之间失败（钩子 `landing answer: business appended`）、提交失败、Ack 回调用另一连接核对已提交、绑定不符。
- **R4 Ack**：结果加 `Acked`；没有 Ack 来源时不调用、`Acked=false`，下一轮仍返回已存结果；S3 的说明卡以存储的 refused 记录（按 question id）为来源，不依赖一次返回值。
- **R5 词表**：`landing_answer` 登记为 `note` 的可选字段，`badLandingAnswer` 校验必填字段、outcome/why 配对与时间；去重读到的记录先校验，并核对 root / op，不符返回绑定错误。
- **N1**：记录 note 让 Close 的同轮折叠缓存失效一次（按流 head），判定不变；接受，不搬到 mission 流。**N2**：去重范围是单仓库流，今天只有 `landing:bifrost-platform`；扩仓库前另定。

变异：去掉去重（6 个测试红）、去掉已存记录的绑定核对（1 个红）、`not_failed` 改回 moot（1 个红）。

## 9. S3 必做 ②：各道闸的时间策略（2026-10-28 统筹，设计稿 v1）

### 9.1 问题（实读 platform main `6ea51e0e`，复核 646 §1、N652-2）

- 扫描在一轮开头取一次 `now`（`controller/landing_scan.go:23`），整轮的到限收尾、未领取结算、恢复、领取、分支、CI、最终闸都用它。
- `ClaimLandingDrill` 两次 bind 和资格判断共用这个 `now`（`store/landing_drill.go:37`、`:48`、`:66`）。中间不持锁读 Git 可能要几分钟：t0 有效的规则在读取期间被一个 `effective_at > t0` 的新版本取代，第二次 `CurrentRule(..., t0)` 选不到它；`accepted + 6h` 在读取期间到期，也照样领取（N652-2：T+5h59m 开始的领取在 T+6h01m 写下 claimed）。
- 唯一已经「锁内读时钟」的是 Close：`landingHolds(..., eventClock())`（`store/close.go:94`）。

### 9.2 规则（一句话）

**在锁内做决定的地方，用锁拿到之后读的时钟做决定；一轮开头的 `now` 只用于排程**（这一轮试哪些候选、退避是否到期、`RetryAt` 是否到）。

决定时间 `decisionAt(now) = max(now, eventClock())`，在该事务拿到它的锁之后读。用 `eventClock` 是因为写下的记录也用它（`store/event.go:129`），决定与记录的时间同源；取 `max` 只为测试：测试冻结 `eventClock`、另传更晚的 `now` 时语义不变，生产上 `eventClock()` 总不早于一轮开头的 `now`。

### 9.3 各道闸

| 闸 | 现在 | 改为 |
|---|---|---|
| 领取第 1 步 bind（短事务，预读） | `now` | `decisionAt`（只决定要不要去读 Git；早返回的 bound / settled 照常） |
| 领取第 3 步 rebind + 资格 + 写 claimed | 同一个 `now` | 第 3 步事务锁后新读的 `decisionAt`；`CurrentRule`、`Bound`、窗口、`EligibleToClaim` 都用它 |
| `LandingDecision`（恢复路径的 claim / push 判断） | `now` | 锁后 `decisionAt` |
| `FinishLandingDrill` 最终闸 | `now` | 锁后 `decisionAt` |
| `SettleLandingDrillBounds`、`failAwaitingBound` | `now` | 锁后 `decisionAt`（时间更晚只会更早收尾，不会把未到限的写成到限） |
| `SettleUnclaimed` | `now`（查询与逐根重查） | 逐根重查的事务锁后 `decisionAt`；第一段只读筛选仍可用 `now`（它只决定去重查谁） |
| Close `landingHolds` | 已是 `eventClock()` | 不变 |
| 退避 `due` / `record`、`RetryAt` 判断 | `now` | 不变（排程） |

### 9.4 后果

- 读取期间生效的新规则：第 3 步选到它，按它判资格；与第 1 步不同的版本不需要另外比较——资格只按第二次的事实判（§7 已定）。
- 读取期间到期的窗口：第 3 步判 `Bound`，按 §7 写 `failed{bound}` 并 settled，不再写 claimed。
- 「6 小时」从此是锁内判定的上限：claimed 记录的时间与判定时间同源，差毫秒级。N652-2 关闭。

### 9.5 测试（PostgreSQL；旧代码上必须红）

1. 领取第 2 步读 Git 期间（测试钩子 `drill: external read`）插入一条 `effective_at` 在 t0 之后、读取结束之前的收紧规则 → 第 3 步按新规则拒绝；旧代码领取成功（红）。
2. 根在 `accepted + 6h - 1s` 开始领取，读 Git 期间把 `eventClock` 推过 6 小时 → 写 `failed{bound}`、不写 claimed；旧代码写 claimed（红）。
3. 最终闸：同 1 的形状，读取期间生效的新规则使最终闸拒绝。
4. 退避与排程不变：一轮开头的 `now` 仍决定退避到期（回归）。

### 9.6 不在本项

- 规则表本身加锁（复核 646 提到「未加规则锁」）：新版本是追加的、按 `effective_at` 选，第 3 步锁内重选已足够；规则撤回的语义归 §5 第 5 项。

## 10. S3 必做 ③：main 对账器与 `failed{denied}`（2026-10-28 统筹，设计稿 v1）

### 10.1 问题（复核 645 §2，实读 `6ea51e0e`）

最新操作停在 `main_intent`、`main_result{ok|unknown|denied}`（`AtMain`）时，Close 无限持住 mission（`store/close.go`，按设计不限时），但没有任何代码把它往下推：STG 恢复路径对这些 phase 直接返回（`controller/landing_branch.go:86`），PROD 没有恢复循环。§2.4「断点对账」表和 §2.3 `reconcile`（任何时候都跑、不看资格）早已写好，没有实现。今天 STG 是 dry_run，走不到 `main_intent`，所以不可达；S3 接真推送前必须有。

### 10.2 设计

**新阶段 `ReconcileMain`**：扫描每轮在 `SettleLandingDrillBounds` 之后、规则观察与资格之前跑；**不读规则、不看资格**（规则撤了、过期了照常对账，§2.3）。逐个 `AtMain` 的最新操作处理：

| 最新 | 外部证据（不持锁读） | 写（锁内） |
|---|---|---|
| `main_result{denied}` | 不需要 | `failed{denied}` |
| `main_intent{R, M0}` | main 头；R 是否在 main 历史里（`merge-base --is-ancestor R main`） | R 在 → `main_result{unknown}` + `landed{R}`；不在且头 = M0 → `main_result{unknown}` + `failed{bound}`（视为没发出去，不重推，由新操作重来）；不在且头 ≠ M0 → `main_result{non_ff}` |
| `main_result{unknown}` | 同上 | R 在 → `landed{R}`；不在且头 = M0 → `failed{bound}`；不在且头 ≠ M0 → `main_result{non_ff}` |
| `main_result{ok}` | R 是否在 main 历史里 | 在 → `landed{R}`；不在 → **不写**，记一条 `note` 说明（推送报成功却不在 main，只能人看），每个操作只记一次 |

- 外部读用新接口 `MainEvidence func(ctx, repo, R, M0) (head string, hasR bool, err error)`，实现放 `landinggit`（同一个只读克隆：`fetch main` 后 `rev-parse` 与 `merge-base --is-ancestor`）。读失败：这个操作本轮跳过、按原因退避（照 §7 领取的退避），不写任何记录，不影响其他操作。
- **锁内**：锁仓库流 → 重新折叠 → 核对该操作的最新 phase / outcome / R / M0 与读证据前一致，不一致就丢弃本次证据（别人已推进）→ 按表追加。决定时间用 §9 的 `decisionAt`。
- `reverted`（R 已在 main 后被撤销）不在本项：`landed` 已是终态、不再持住 mission；撤销检测归 S4。
- `failed{denied}` 之后「停掉这个仓库的落地、开问题」（§2.5 第 7 步）：本项只写记录；开问题与停仓库由 S3 接线（问题卡），记为 S3 接线项。

### 10.3 与 Close 的关系

对账写下终态后，下一次 Close 读到非 `AtMain`，按现有规则放开或继续持住；对账器不碰 mission。锁序：只拿仓库流（与 `SettleLandingDrillBounds`、appendDrill 相同），不拿 task / mission，不成环。

### 10.4 测试（PostgreSQL + 假 Git；旧代码上必须红）

1. 表里每一行一个用例：种入该最新状态，给定证据，跑一轮 → 写下的记录与表一致；再跑一轮不重复写。
2. 规则已撤回时照常对账（旧代码：没有对账，mission 一直 active —— 红）。
3. 读证据期间另一个写入推进了该操作 → 证据丢弃、不写。
4. 证据读失败 → 不写、退避；其他操作照常。
5. 对账后 Close：mission 从持住变为可关（`main_result{denied}` 七小时后的 mission 在旧代码上一直 active —— 红）。

### 10.5 不在本项

- 真推 main 的路径（S3 本体）；`reverted` 检测（S4）；`denied` 的问题卡与停仓库（S3 接线）。
