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

### 9.7 复核 656 与 v2（2026-10-28 下午，已实现）

复核 656：B 部分 1 阻断（B-B1）、3 应修、2 小问题。v2：

- **一个时钟**（B-R2）：`DecisionAt()` 就是事件时钟 `eventClock`，不再取 `max(now, …)`。决定与记录同源（Append 也用它），`failAwaitingBound` 这类「决定时到限、Apply 再按 e.At 验到限」的两次判定不再可能不一致。测试推进时间只能拨这个时钟；三个原先「传一个未来的 now、不拨时钟」的测试改为同时拨时钟（`TestSettleUnclaimed`、`TestClaimPastTheWindowRecordsBoundWithoutGit`、`TestDrillWindowBoundFreesActiveSlotInDatabase`）。一轮的 `now` 只排程。**不防时钟回拨**：墙钟回拨（NTP）时，一个已到限的窗口在那一轮里可能看起来又没到；接受并记在台账。
- **最终闸读完再选**（B-B1）：`FinishLandingDrill` 拿齐锁后取一次时间读事实，`observe`（读 CI、main、窗口）之后再取一次 `final`，用它重选规则、重读数据库一半事实（外部证据沿用，其键被锁住），`NextDrill` 也用 `final`。测试 `TestDrillFinalGateSelectsTheRuleAfterItsReads`：事先装好 effective 在两次时间之间的收紧版本 → 拒绝；变异「final 用拿锁时的时间」→ 红。
- **补漏的闸**（B-R1）：`ObserveLandingEnabled` 先锁流、再按锁内时间选规则（不在已过期的规则上写启用栅栏）；`LandingDrillCI` 的到限、`NextDrill`（10 分钟补建、30 分钟卡住）、CI 创建时间核对、`parked.retry_at` 都用读完外部之后的时间；`LandingDrillBranch` 的到限同。`LandingDecision` 不持锁，是可重试的预判（每次新事务读时钟），不是最终授权闸。
- **S3 的 PROD 最终闸**（`main_intent`、UTC 配额、预留）：按同一条规则——最后一次外部读之后取一次时间，规则、到限、配额日期、资格都用它；接线时照做，本项不含。
- **退避**（B-N1）：§9.3 表写错了：退避的 `due` / `record` 本来就用新鲜的 `c.clock()`（慢失败后不立即重试），v2 不动它。
- 测试钩子（B-N2）：没有新增钩子，测试直接在 `LandingSource.Result` / `observe` 回调里推进时钟，并断言回调确实被调用。

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

### 10.6 设计稿 v2（2026-10-28 下午；Owner 定 1A、2A；回应复核 656 C）

**Owner 决定（13:4x CDT）**：
- **1A**：协议新增结局 `failed{main_lost}`，只能从 `main_result{ok}` 转入，只由 Owner 在问题卡上确认后写入（答复选项 `confirm_main_lost`，走 §8 的 `HandleLandingAnswer`，记录、去重、先落库后 Ack 同 §8）。在此之前对账器每轮低频重查：后来在 main 上找到 R 就补 `landed`。
- **2A**：按时间隔开。推送有硬超时 `T = 2 分钟`；对账器只在 `main_intent` 写下超过 `T + 10 分钟` 之后才把「main 上没有 R」当作没发出去。另加「迟到落地」检测：一个曾有 `main_intent`、后被判 `failed{bound}` 的操作，若之后 R 出现在 main 上，开一次异常记录交 Owner。不建租约。

**对复核 656 C 的处理**：
- **C-B1**：由 1A 解决。`ok` 而 R 不在 → 每轮重查 + 一次性异常记录（`landing_anomaly{kind: ok_missing}`）；Owner 确认后 `failed{main_lost}`，它是 failed、未 retry，不再持住 mission，也挡住同根再领（与其他非重试失败相同）。
- **C-B2**：由 2A 解决：负证据只在时间栅栏之后才用；栅栏内一律不写。推送实现（S3 本体）必须保证单次推送在 T 内结束或放弃（客户端超时 + 不重试），这是 S3 接线的验收项；迟到落地检测兜底。
- **C-R1 证据**：`MainEvidence(ctx, repo, R) (head, hasR, err)`：完整（非浅）fetch main，固定 head SHA；`cat-file -e R^{commit}` 不存在 → hasR=false（完整历史里没有它）；存在则 `merge-base --is-ancestor R head`：退出 0 → true、1 → false、其他 → error。任何 fetch / 命令故障 → error，不当 false。记录写下 head、R、M0。
- **C-R1 去重**：异常记录用 note 新字段 `landing_anomaly{op, root, kind, R, head}`，在流锁内按 `(op, kind)` 查重，最多一条；与协议记录分开（无 `landing` 键）。
- **C-R2 顺序与退避**：扫描里先做数据库收尾（到限、未领取），再做 `denied → failed{denied}`（不读 Git），最后逐个操作读证据；每个操作的读取有超时，失败只退避这个操作（键 = op + 期望状态，用新鲜排程时钟），不影响其他操作；规则为空 / 过期 / 撤回都照常对账。
- **C-R3 交接**：`landed` 后加入 STG 发布队列、`failed{denied}` 后停仓库与问题卡：仍是 S3 接线的验收项（本项只写协议终态）；已在 §10.5 列出，S3 开门前必须做。
- **C-R4 测试**：每个证据分支各一例（含 R 在 / 不在 × head = M0 / ≠ M0 × 栅栏前 / 后）；ok 缺失的异常记录与重查后 landed；`confirm_main_lost`；denied 不调 Git；并发推进后证据作废；证据错误不写、其他操作照常；迟到落地；变异：省略 `main_intent → unknown`、去掉锁后状态比较、错误当 false、只比 head 是否等于 R、去掉栅栏。

### 10.7 复核 657、658 与落地（2026-10-28 下午）

- **657（①②代码）**：B657-1 校验器误拒合法记录 → 按 why 的规则表重写（可跟随的选项、mission 必须 active / 非 active / 不限），接受全部 mission 状态与空选项；R657-4 `not_retryable` 要求 active；R657-1 最终闸的记录改用最终事实里的规则版本（原来可能空指针）；R657-2 / N657-1 分支步骤读完后再判到限、`retry_at` 用新时钟；R657-3 补测：真等锁的双连接、提交成功但回包丢失、S2 各阶段 decline、每条决定后的记录可复读。platform `3752318d`。
- **658（③代码）**：B1 证据改为 `rev-list` 遍历 main 完整历史（拒浅克隆），只有遍历完成且不含 R 才是 false；B2 负证据只认在栅栏之后开始的读取（`MainEvidence.ReadAt` 由对账器在读前打上）；B3 `main_lost` 只在 v1.1 `failed`、只从 `main_result{ok}`、只由 controller 写；R1 迟到落地锁内去重；R2 Owner 回「不合」后仍监测迟到落地；R4 每个终态同事务写 `landing_main` 证据（head、has_r、read_at）；N1 异常 / 证据记录校验 SHA 与根。platform `eb85778a`。
- **仍留给 S3 接线（开门前必须）**：对账读取按操作退避与公平调度（658 R3）；landed 进 STG 队列、denied 停仓库与问题卡（656 C-R3）；ok_missing / late_landing 的 Owner 问题卡从持久异常记录生成并走 `confirm_main_lost`；推送 2 分钟硬超时；PROD 最终闸（main_intent / 配额）按 §9.7 取时间；中间闸（CI、分支）写新意图前按同一时点刷新规则（657 R657-2 的剩余部分）；读卡回调的超时（657 N657-3）。

## 11. S3 本体：拆分与顺序（2026-10-28 15:xx 统筹，设计稿 v1）

前提（已上 PROD `9d611d54`）：答复处理（§8）、决定时间（§9）、main 对账器（§10）。S3 接线 A 部分已在 platform 分支 `w31/s3-wiring-a`（`f07e0f35`：对账独立循环、按操作退避、中间闸刷新；`aa30a556`：窗口读不删、释放用带版本的更新）。

S3 真推 main **只在 PROD 跑**（规则 `landing:dev` 只在 PROD 签；STG 继续 S2 演练）。所以落地问题卡开在 PROD 的问题库（ops.bifrost.lan），符合「人批的只在 PROD」。

### 11.1 五块与依赖

| 块 | 内容 | 依赖 | 对应 §3 S3 用例 |
|---|---|---|---|
| **B1 真推 main** | PROD 的落地循环 `LandingLivePass`（与 STG 演练平行，mode=live）：领取 → 第一道闸 → 重放（`Landed-By: agentrt-prod/<op>`）→ 推 `land/prod/<root>/<k>`（落地身份）→ 等 CI（同演练）→ **第二道闸**（§2.5 第 6 步：一个事务、固定锁序含当天 UTC 配额流；锁内重读规则 → `EligibleToPush` → main 头仍是 M0 → 窗口不挡 → 预留额度 → 写 `main_intent`；按 §9.7 读完外部后取时间）→ **推 main**（不带 force；单次硬超时 `PushTimeout` 2 分钟；不自动重推）→ `main_result{ok|non_ff|denied|unknown}` → ok 后确认 R 在 main 再写 `landed` → 按 SHA 删落地分支 → `stg_pending{R}`。`landinggit` 加 PROD 的身份与 `land/prod/**`、`refs/heads/main` 的推送（只快进）。 | 落地身份（Owner 建 `agentrt-lander`、加白名单、配 Secret） | ①②③⑩⑪⑫ |
| **B6 denied 停仓库** | `failed{denied}` 写下的同一事务里写持久停止条件（note `landing_stopped{repo, op}`）；领取和第二道闸都先查它，有就拒（新 ClaimRefusal 不需要——拒在资格前、不写记录）；只有 Owner 在卡上「恢复」才解除（`landing_resumed`）。 | B1、B3 | — |
| **B3 落地问题卡** | 每个根任务一张（去重键 `landing:<root>`），由持久记录驱动生成：最新操作 `failed{bound|stale|ci_red}`（选项「再试一次 / 不合」）、其他 `failed`（「不合」）、`ok_missing`（「确认已丢失 / 继续等」）、`late_landing`（只读说明 + 「知道了」）、`landing_stopped`（「恢复 / 保持停止」）、`parked` 超过 2 小时（只读说明）。卡与（根，操作，种类）的绑定写在仓库流 note `landing_card{question_id, root, op, kind}`；读答复走 §8 的 `LandingAnswer`（选项字母 → 语义选项由绑定种类决定）。卡在操作前进后作废（新卡换新 id）。 | §8 | §2.7 |
| **B5 STG 发布接力** | §2.8 全部：`stg_pending` 汇总 → 无活动落地或最老等 20 分钟 → 持窗口 → 定 P、U（U 读 P 那次成功 CI 克隆的 ui 提交）→ 发前检查（每个 R 过 `EligibleToDeploy`；上次 STG → P 整个差异判权限；P 最新 CI 成功且用 U）→ `stg_snapshot{try}` → 起 `bifrost-deliver-platform`（revision=P、uiRevision=U）→ `stg_started` → 读 run 终态 `stg_result` → 核验四项（run 克隆头 = P；Deployed("stg") = P 且三个摘要对；rollout 完成；STG `/health` 版本 = P）→ `stg_verified` / 重试（同 P、U，try ≤ 3，退避 10 / 30 分钟）/ `stg_failed` + 卡。创建结果不明时按 run 名接管、不多建。 | B1、窗口（A 部分已改） | ④⑥⑦⑧⑨ |
| **B4 收尾分类** | §2.7：落地范围内的根任务分已交付（规则 `stg_release` 开着的要 `stg_verified`；`none` 的要 `landed` 且仍有效）/ 已处置未交付（declined、stale、main_lost、mission no_merge）/ 未了结（其余，含 `parked{rule}` 和未答复的失败）；全部交付或处置且至少一个交付 → done，全部只处置 → stopped，有未了结 → 保持 active。替换现在 `landingHolds` 的「失败即放」。 | B3（未了结要有出口）、B5（已交付要 stg_verified） | ⑤ |

### 11.2 顺序

B1 + B6 → B3 → B5 → B4，每块：设计细节 → Codex 设计复核 → 实现 + PostgreSQL 测试（§3 的 S3 用例逐条一个测试，旧代码上必须红）→ Codex 代码复核 → 推分支 CI。全部做完再一起发 STG / PROD，然后 Owner 做 S3 开门的事（签第 1 版规则、建落地身份并加白名单配 Secret、核对标签规则、批 D-L5 的 D 级单、批发布单）。

### 11.3 待复核的设计点

1. B1 第二道闸与推 main 是两个事务：`main_intent` 提交后再推；推送结果不明（超时、断连）记 `main_result{unknown}`，交给 §10 的对账器。这样「推送进行中」由 `main_intent` + 2 分钟硬超时 + §10 的栅栏覆盖，不需要租约（Owner 2A）。
2. 落地身份推 main 的 Gitea 权限：只在 platform main 白名单；`land/prod/**` 也只给它；它不能推 infra、不能建标签（用例 ⑫）。
3. B3 选项字母到语义的映射放在绑定记录里（kind 决定），`LandingAnswer` 的 read 回调由绑定适配器提供，不改 §8 的处理。
4. B5 的 U 来源：`ci-platform` 的 `clone-ui` 任务结果 `commit`（S0 已接进审计）——需要核实 PROD 的 platform-api 能读到 ci run 的 task 结果。
5. B4 改变现行行为：今天 `failed`（未 retry）放开 mission；改后要等 Owner 在卡上「不合」才算处置。B3 必须先上，否则 mission 卡在 active。

### 11.4 设计稿 v2（2026-10-28 15:xx；回应复核 660 的 B-01..B-06、R-01..R-06、N-01..N-02）

**已有 / 需扩展 / 新增**（N-02）：已有并需 live 装配与回归——独立对账循环、按操作退避与公平预算、中间闸刷新、读卡超时、窗口读不删与带版本释放（`f07e0f35`、`aa30a556`）；落地身份与推 main 的 Git 层（`3a76c622`，按 R-04 再收窄接口）。本片新增——live 循环与最终闸、推送的绝对期限、撤销检测前移、发布交接、问题卡 v2、停仓库、STG 接力、live 收尾分类。

**开门契约**（R-06）：代码可以先发布，live 默认关（PROD 的 `AGENTRT_LANDING_LIVE` 不开，就不起写循环）；对账、停止标记、已存在 run 的观察、答复处理、数据库补齐照常跑。开门前置：P0 证据、D-L5 完成、落地身份阴阳性探针（R-04 表）、同提交 STG 验证、PROD 运行提交、正式规则——**审批在发布之前**。

**B1 v2（B-01、R-03、R-04、N-01）**
- 三段：**授权事务**（最终闸：按预期 UTC 日按序锁配额流 → 仓库流；外部读完取 final；final 跨日则整笔回滚从头按新日期锁；同事务写 `reserved` 与 `main_intent`，记规则版本、决定时间、配额日、精确 CI run）→ **外部动作**（推 main）→ **结果事务**（锁下重读；对账器已推进则接受，不覆盖、不重推）。
- 推送只由**刚在本进程提交了该 intent 的调用方**发起（返回的 intent 事件序号即令牌）；重启读到已有 intent、提交回包丢失，都只对账。推送前再读一次：操作仍在该 intent、`main_intent.at + PushTimeout` 未到；Git 用同一绝对期限，不重新计时。
- 进程树：Git 子进程独立进程组，到期杀整组并设 `WaitDelay`；回收余量计入 `PushTimeout` 预算。客户端放弃不证明服务端停止——2A 的残余风险写明，迟到落地检测保留（不是强 fencing，不提租约）。
- `non_ff`、`denied` 只在服务端明确拒绝时用；其余一律 `unknown`。
- 接口收窄（R-04）：`PushLandingBranch(root,k,R)`、`PushMain(R,M0,intentSeq)`、`DeleteLandingBranch(root,k,R)`；main 不进删除接口；只在 PROD live 装配提供 MainPusher；推 main 只一个显式 `R:refs/heads/main`，不用 `+`、force、tags、follow-tags（`--force-with-lease=main:M0` 换成「推前读 main 头 = M0 + 服务端只快进」两层：lease 本质是 force 家族，按 R-04 去掉）；R 必须是 prepared 的 R、父为 M0。argv/env 捕获测试。
- 措辞（N-01）：第二道闸之后收紧「不追溯撤销已取得的授权」；是否落地、是否有效由外部证据定。

**撤销检测前移（B-02，⑪）**：`MainEvidence` 增加当前有效性：在同一固定 head 上用 `EvaluateHistory`（补返回撤销提交 SHA）判 有效 / 已撤销 / 未知。对账（直接路径与断点路径同一函数）在 R 在历史里时：有效 → `landed`；已撤销 → `landed` + `reverted{R, by}`（同事务、此顺序）；未知 → 只 `landed`，不算交付、不发 STG。已 landed 的操作在其 mission 关闭前每 30 分钟重查一次有效性，后来撤销的补 `reverted`。已撤销的不自动重领。

**发布交接（B-03）**：不靠成功路径的尾调用。「待发布」是**派生的**：已 landed、当前有效、且不在任何 STG 操作的 `stg_pending` 集合里的 R。B5 的批次器在仓库流锁下从折叠结果算出它、建新 STG 操作并冻结集合；直接推送与对账补记都只写 `landed`，同一机制接手。分支清理独立，失败不挡交接。

**B6 停仓库 v2**：`landing_stopped{repo, op, generation}` 写在**所有** `failed{denied}` 写路径的同一事务（含 `ReconcileDenied`）。领取与最终闸在仓库流锁下检查。恢复只由 Owner 在「仓库已停止」卡上答「恢复」：锁下核对当前 stop generation 才写 `landing_resumed{repo, generation}`；旧恢复答复不解除新停止；恢复不重试原 denied 根。

**B3 问题卡 v2（B-04）**
- 逻辑上一根一个落地问题；物理卡幂等键 = `repo/root/op/kind/generation`（仓库停止卡 = `repo/stop-generation`，发布失败卡 = `stg-op`）。
- 三步：先写 `landing_card_intent{key, kind, template_version, options:[字母→语义]}`（不可变映射）→ 用该 key 调 Ask（问题库按 key 幂等，`SameByKey`）→ 写 `landing_card{question_id, key}`。断点：有 intent 没绑定时，按 key 查询接管并核对 kind、选项、generation；不猜。
- 答复按 kind 分派：`try_again`、`do_not_merge`、`confirm_main_lost` 走 §8；`repo_resume` 走 B6；`ack`、`wait`、`keep_stopped` 只写处理记录（§8 的记录词表扩展这几个 why）。一律先落库后 Ack。
- 生成器输入 = 持久触发记录 + 当前适用性 + 已处理记录：已解决的撤卡（`ok_missing` 后来 landed）；`late_landing` 独立到确认；§8 的 refused 说明卡、发前拒绝、`stg_failed`、待发布超过 1 小时、`parked` 超过 2 小时都有卡。
- 不调 `failWork`、不计执行者成绩（§2.7）。

**B5 STG 接力 v2（R-01、R-02）**：仓库同时只有一个未终结 STG 操作，批次在流锁下冻结（后到的 R 下一批）；P、U 从**同一次**最新且 Succeeded 的 `ci-platform` run 的 `platform-commit`、`ui-commit` 结果读（缺失、矛盾、旧成功后有新 run 都拒，不回退 main；存 run 名、UID）；try 只在确认 run 终态失败后加；同名 run 创建不明 → GET 同名并核对 UID / pipeline / P / U / 来源，碰撞不接管；新 try 或首次创建前重验规则、no_merge、整段差异、精确 CI、窗口；已有 run 的观察不看当前授权；窗口 who = `stg-op/try`，每分钟续、TTL 5 分钟，丢失写诊断记录（扩 STG 协议一个 `stg_lease_lost`）并继续观察；四项核验 + 每个 R 当前有效才 `stg_verified`；三次失败 `stg_failed` + 卡；人工发布后按 P/U/R 与四项证据补核验。协议扩展：`stg_lease_lost`。

**B4 收尾 v2（B-06）**：只在 PROD 且 live 模式启用；STG 保持 S2 的演练终态规则。分类器返回 已交付数 / 已处置数 / 未了结数，替换 PROD 的 6h15m 计时放行。已交付：`stg_release` 开着的要 `stg_verified` 且 R 当前有效；`none` 的要 `landed` 且有效（规则缺失或过期不等于 none）。已处置：Owner 已答「不合」（declined）、`main_lost`、mission `no_merge`。**`stale` 不再即时算处置**：未答复前算未了结，卡上可选「再试一次」或「不合」（避免 Close 与答复竞争）。`failed{in_main|reverted|result}` 按实际发布证据判。AtMain 先对账，`no_merge` 不当作外部动作已停止。分支不受 B4 影响（B-05 已定不自动删）。

**B-05（统筹按推荐定，Owner 可推翻）**：`land/prod/**` 保持只有落地身份能写的保护；**不自动删除**这些分支（偏离 §2.11），分支保留并在 Console 显示数量与最老一条，由 Owner 定期按受控流程清理。若要自动删，另加服务端策略，约 8–16 小时。

**工作量与日期**（按 660）：68–107 小时；Claude + Codex 并行、夜班不停，开门估 **11-05 到 11-10**。最大风险：B5（跨系统最多）、B1（推送授权与期限）。

**顺序**：B1 + 撤销检测 → B6 → B3 → B5 → B4；每块 设计细化 → 复核 → 实现 → 测试（分层：纯协议、PG、假 Git / 临时 Git、假 K8s、实际 Gitea / STG）→ 复核。

### 11.5 复核 661 结论与执行清单（2026-10-28 15:2x）

661：v2 可作为继续细化、实现的基础。B-01、B-03、B-05 设计层解除；B-02、B-04、B-06 部分解除；新增 B-07。各块开工前在本节下补「细化」小节并送一轮设计复核（报告 `~/agent-work/codex-work-661/REPORT.md`）。

**已完成**（platform 分支 `w31/s3-wiring-a`，基于 main `9d611d54`）：`f07e0f35` 对账独立循环与退避、中间闸刷新、读卡超时；`aa30a556` 窗口读不删、释放带版本；`3a76c622` 落地身份与推 main Git 层；`49d5ac23` 推送绝对期限、进程组回收、R 必须在 M0 上、去 lease；`8f4023a4` live 第二道闸（锁序、读后决定、跨日回滚、ci_seen → reserved → main_intent）、推送结果记录、B6 停仓库（denied 同事务写 stop，领取查 stop）。全套 PG 测试绿。

**待做（按顺序）**：
1. **B1 收尾**：661 R-03 两个 Append 之间跨午夜（核对 reserved、main_intent 的实际事件时间与配额日一致，否则整笔回滚）；R-04 推送结果分类细化（本地 non_ff、远端非快进、明确权限拒绝、其余 unknown；不用 stderr 子串判 denied）；「唯一父为 M0」；第二道闸也查 stop（已做）。
2. **撤销检测（B-02）**：`MainHistory` 加撤销者；有效性证据版本化写入（扩展 `landing_main`：observed head、状态、读取时间、撤销者），与 landed / reverted 同事务；未知不沿用旧结论；B4、B5 在作决定时现读、不用缓存。
3. **live 编排**：`LandingLivePass`（PROD、`AGENTRT_LANDING_LIVE=on` 且整组能力齐全才起写循环）：领取（live）→ 分支（落地身份、`land/prod`、`dry_run:false`、提交信息加 `Landed-By: agentrt-prod/<op>`）→ CI → `AuthorizeLandingPush` → 本进程立即 `PushMain`（期限 = intent.at + 2 分钟）→ `RecordPushResult`。重启只对账。`land/prod` 分支不删（B-05）。
4. **B3 问题卡**（661 B-04）：卡的代际与过期补卡；唯一绑定（同 key 两张卡只认一个）；已处理 / 已解决 / 暂缓三态，`wait`、`keep_stopped` 之后有再次决策的入口且限频；B6 的 resume。
5. **B5 STG 接力**（661 B-07、R-01、R-02）：无外部执行的批次处置与成员交接；人工发布证据结算；run 身份先存指纹后绑 UID；租约丢失只是诊断；P 为选定 main 头的精确 CI。
6. **B4 收尾**（661 B-06）：按持久 enabled 栅栏与模式记录选政策，live 开关不改变已纳入 live 的 mission；无人答的失败持久待办 + 补卡 + 限频提醒，不恢复计时放行。
7. 每块：细化 → 复核 → 实现 + 分层测试（旧代码上红、关键变异）→ 代码复核 → 分支 CI；全部完成后整批发 STG / PROD（live 关），再由 Owner 做开门事项。

### 11.6 B3 问题卡细化（2026-10-28 16:5x 统筹，设计稿 v1；回应复核 661 B-04）

实读 platform `w31/s3-wiring-a` `34c8f430`：建卡的现成做法是 `askBlocked`（`store/blockedcard.go:167`）：**在持锁事务里调 Ask，同一事务写绑定**；卡的 key 是规范输入的 sha256 十六进制（`blockedCardKey`，64 位，符合 `questions/canonical.go` 的 16–64 位规则）；问题库 `LookupKey` 只认受保护的卡（open，或已答未读 7 天内，`questions/types.go:164`）。B3 沿用这个做法，不另起「先写 intent、再 Ask、再绑定」三步，从而去掉 661 反例 1 的根源：**只有已提交的绑定算数**。

**1. 触发与代际**
- 触发 = 仓库流上一条不可变的持久记录，触发标识 = 该事件的 `seq`（天然代际，不另分配）：
  | 种类 `kind` | 触发记录 | 仍适用的条件（折叠仓库流时判） | 选项（语义） |
  |---|---|---|---|
  | `root_failed` | 根的最新操作 `failed{why}`（why ≠ declined、main_lost） | 该操作仍是根的最新操作、未 retry、未 declined | `try_again`（仅 why 在可重试集合时）、`do_not_merge` |
  | `ok_missing` | `landing_anomaly{ok_missing}` | 操作仍是 `main_result{ok}` | `confirm_main_lost`、`wait` |
  | `late_landing` | `landing_anomaly{late_landing}` | 始终（直到答复） | `ack` |
  | `repo_stopped` | `landing_stop{generation}` | 当前 stop generation = 该 generation 且未 resume | `repo_resume`、`keep_stopped` |
  | `parked_long` | 操作进入 `parked` 的记录 | 仍 parked 且已超过 2 小时 | `ack` |
  | （B5 补）`stg_failed`、`pending_long` | — | — | — |
- 硬底线失败（规则硬拒绝、`result` 等 ClaimRefusals）只给 `do_not_merge`，不给「合」或放宽底线的选项（660 §2.5）。

**2. 卡的物理 key 与唯一绑定**
- 同一触发可以有多张卡（过期、暂缓后再问），序号 `n` = 该触发已提交绑定数 + 1。key = `sha256(canon{route:"landing", repo, kind, root, op, trigger_seq, n, template_version})` 的 64 位十六进制。模板升级 → 新 key，不撞 `KeyReused`。
- 建卡事务：锁卡片流 `landing-cards:<repo>`（**不锁仓库流**，Ask 期间不挡最终闸）→ 读仓库流折叠（不加锁的快照）判触发仍适用 → 读该触发已有绑定（求 n、确认没有未结的卡）→ `Ask(key, SameByKey)`（有界超时）→ 同事务写卡片流 note `landing_card{v, key, question_id, kind, root, op, trigger_seq, n, template_version, options:{字母→语义}}`。
- 唯一性：追加校验在卡片流锁下拒绝同 `(trigger_seq, n)` 的第二条 `landing_card`，也拒绝同 `question_id` 的第二条。
- 断点：Ask 成功而事务失败 → 卡是孤儿、没有绑定。下一轮同 key 再 Ask：卡仍受保护（open 或已答未读）就拿回同一张并绑定；已过期 / 撤回 → 问题库建新卡，绑定新卡；孤儿卡已不可答，不会产生第二个答案来源。已答未读的孤儿在 7 天内一定被绑回。
- 接管核对（661 改法 2）：拿回的卡要核对 requester、task、选项标签与映射一致（`SameByKey` 只比 task 与标签，落地另在绑定前比 `kind`、模板版本与 key 本身——key 已编码其余字段）。

**3. 读答复与分派**（新 `store.HandleLandingCard`，§8 的处理不改）
- 每轮读「每个触发的最新绑定」对应的卡；只认 console 答复、有 by / at。按绑定里的映射把字母转成语义，再按 `kind` 分派：
  - `try_again`、`do_not_merge`、`confirm_main_lost` → 原 `HandleLandingAnswer(root, op)`（§8，处理与 Ack 顺序不变）。
  - `repo_resume` → 仓库流锁下核对当前 stop generation = 卡的 generation，才写 `landing_resume{generation}`；不等则 `moot`。恢复不重试原 denied 根。
  - `wait`、`keep_stopped` → 写处理记录 `held`，带 `remind_at = 答复时间 + 24 小时`。
  - `ack` → 写处理记录 `acknowledged`。
  - 自由文本 / 未知选项 → `refused{unknown_choice}`，卡结束；触发仍适用就按限频补一张 n+1。
- 处理记录扩展 §8 的 `landing_answer` 词表：choice 加 `repo_resume / keep_stopped / wait / ack`，outcome 加 `held / acknowledged`；仓库停止卡没有 root / mission，记录改为可选 root，校验按 kind 分支（`repo_stopped` 不要求 mission 状态）。一律先落库、后 Ack；Ack 失败下一轮重试，不重复处理。
- 处理记录写在**仓库流**（与 §8 相同），卡片流只放 `landing_card` 绑定与 `landing_card_closed`。

**4. 已处理、已解决、暂缓三态**（661 反例 2）
- **已处理**：绑定的卡有了处理记录 → 这张卡结束。
- **已解决**：触发不再适用（ok_missing 后来 landed、stop 已 resume、失败根已 retry 或 declined、parked 已离开）→ 撤回该触发未结的卡（`Withdraw`，原因写明），写 `landing_card_closed{key, why:"resolved"}`，不再补卡。
- **暂缓**：`held` 记录的 `remind_at` 未到 → 不补卡；到了且触发仍适用 → 补 n+1（暂缓不吃掉决策入口）。
- `acknowledged` 结束该触发的提醒，不再补卡（`late_landing`、`parked_long` 只需知道一次）。
- 限频：同一触发同时最多一张未结卡；卡过期后补卡至少隔 6 小时；每个触发每天最多 4 张。refused 不派生说明卡（只在下一张卡正文里写上次为什么没生效）。

**5. 循环与范围**
- 独立循环 `agentrt-landing-cards`（每 15 秒，有界预算，按触发轮转起点），PROD 在 `Sources.Ask` 与 `Sources.Question` 都有时运行，**不受 live 开关限制**（关开关后 stop / ok_missing 仍要有人决定）。STG 不开（演练失败不发卡，STG 的人批不在 STG，§「人批唯一入口」）。
- 不调 `failWork`、不计执行者成绩（§2.7）。
- Console 卡片正文（英文）：仓库、根任务标题、操作、触发原因、可选项的后果；不放 R / M0 以外的内部 id。

**6. 测试（PG，旧代码上必须红）**：Ask 成功回包丢失（事务失败）后同 key 拿回并绑定；绑定前卡过期 → n 不变的新卡；两个建卡者交错只有一个绑定；旧代际卡晚答（stop generation 已变）→ moot；`wait` 后 24 小时仍适用 → 补卡，期间不补；暂缓期间解决 → 撤回、不补；Ack 失败 → 不重复处理；模板升级 → 新 key；自由文本 → refused 且限频补卡；`repo_resume` 不重试原根；关 live 开关时 stop 卡照常。

**7. 本片不做**：B5 的 `stg_failed`、`pending_long` 卡（随 B5）；Console 新页面（卡走现有问题页）。

### 11.7 B5 STG 发布接力细化（2026-10-28 17:0x 统筹，设计稿 v1；回应复核 661 B-07、R-01、R-02，660 R-01）

实读 platform `34c8f430`：协议已有 `stg_pending{R} → stg_snapshot{P,U,try,not_before} → stg_started{run,try} → stg_result{run,outcome} → stg_verified{P,U,digests} | stg_failed{why}`（`landing/protocol.go:468–513`，try ≤ 3、退避 10 / 30 分钟已在协议里）。infra `pipeline-ci-platform.yaml:22–26` 已产出结果 `platform-commit`、`ui-commit`。本节补：批次归属、无执行的处置、run 身份、租约、P/U 的精确来源、发前检查、人工发布的证据结算、卡。

**1. 待发布与批次**
- 「待发布」是派生集合（§11.4）：landed、最新有效性证据为 effective、且不属于任何**未释放**批次的 R。批次 = 仓库流上的操作 `stg:<repo>:<n>`，`stg_pending{R:[…], roots:[…]}` 在仓库流锁下冻结成员。
- 同仓库同时只有一个未终结批次（终结 = `stg_verified`、`stg_failed`、新增的 `stg_abandoned`）。
- 开批条件：live 开、没有活动落地（claimed 到 main_result 之间的操作），或最老的待发布已等 20 分钟。
- **尝试账跟着 R 走**（661 B-07：换批次不清零）：每个 R 的已用自动尝试 = 它所在批次中到达 `stg_started` 的 try 数之和。已用满 3 次的 R 不进自动批次，只等卡上 Owner 的决定或人工发布的证据。

**2. 尚无外部执行的批次处置**（661 B-07 反例 1）
- 新记录 `stg_abandoned{why, members:{R: release|no_merge|reverted|ineligible}}`：只允许从 `stg_pending`，或 `stg_snapshot` 且该 try 没有 `stg_started` 时写入。写了 `stg_started` 就不能放弃：create 结果可能已生效，只能走 run 观察。
- `release` 的成员回到待发布（尝试账不变）；其余成员带处置原因离开自动发布，由 B4 按处置原因分类（`no_merge`、`reverted` 算已处置未交付；`ineligible` 算未了结，发卡）。
- 触发：发前检查发现永久性不合格（成员 mission `no_merge`、R 已撤销、规则禁止该差异）；暂时性问题（CI 未完成、窗口被占、规则读不到）只等待，不放弃。

**3. 快照 P、U 的来源**（661 R-02）
- 持窗口后读 main 头 → P。找 `ci-platform` 中 revision 参数**恰为 P** 的最新一次 run：
  - 必须 Succeeded，且结果 `platform-commit` = P、`ui-commit` 是完整 SHA → U；
  - 还在跑：等，30 分钟不出结果就发卡；
  - 失败或结果缺失：不回退到更早的提交，发卡「P 的 CI 未过」；
  - 不存在：等 webhook 触发的 CI，30 分钟仍没有就发卡。
- `stg_snapshot` 增记 `ci_run`、`ci_uid`、`ci_created_at`。重试沿用同一 P、U（协议已强制）。同一 P 的新 CI 用了另一个 U：拒绝，不替换快照。

**4. 发前检查**（每个 try 在写 `stg_started` 前、持窗口时现读，不用缓存）
- 每个成员 R：`EligibleToDeploy`（规则 `stg_release`、mission 不是 `no_merge`、最新有效性 = effective）。
- 上次 STG 部署（`Deployed("stg")` 的提交）→ P 的整段差异按规则判权限。
- P 的精确 CI 仍是快照里那一次。
- 任何一项不过，按第 2 条区分永久性（放弃该成员）与暂时性（等待）。

**5. run 身份与创建**（660 R-01、661 R-01）
- 先写意图，再动外部：`stg_started{run, try, namespace, pipeline, P, U, fingerprint}`，其中 `fingerprint = sha256(pipeline + 完整参数)`；然后创建 PipelineRun `bifrost-deliver-platform`（`revision=P`、`uiRevision=U`），run 名 = `landing-stg-<op 摘要>-<try>`。
- 观察：GET 同名 run。
  - 404：确认未创建，用同名重建；
  - 403 或超时：等，不等同于 404；
  - 找到：参数指纹相符就写 `stg_bound{run, uid}`（只记一次，不改变阶段）；之后 UID 变了即为碰撞，写 `stg_result{outcome: collision}`，按失败的 try 计。
  - 指纹不符：不接管，按碰撞处理。
- 终态：PipelineRun Succeeded → 进核验；Failed → `stg_result{failed}`；运行中 → 继续观察（没有超时放弃，只发卡提醒，跑超过 90 分钟发一张）。

**6. 窗口与租约**
- 持窗口：`who = stg:<repo>:<n>/<try>`，从快照前一刻起持到核验写完；每分钟续一次，ttl 5 分钟。
- 续不上：写诊断记录 `stg_lease_lost{try, at}`。它是附注，不改变阶段（协议允许它出现在 `stg_snapshot`、`stg_started`、`stg_result`）。继续观察已起的 run；放弃尚未 `stg_started` 的 try 的创建，下一轮重新持窗口。
- 核验前若发现租约丢失期间 STG 被别人改过（`Deployed("stg")` ≠ P），按失败的 try 计（`stg_result{superseded}`）。
- 释放：用读到的版本做带版本的更新（已实现，`aa30a556`）。

**7. 核验与收尾**
- 四项都要过：
  1. run Succeeded，且克隆结果的头 = P；
  2. `Deployed("stg")` = P，三个镜像摘要与 run 结果一致；
  3. rollout 完成；
  4. STG platform-api `/health` 报出的版本 = P。
- 都过 → `stg_verified{P, U, digests, effective:[…], ineffective:[…]}`：逐个现读成员 R 在 P 的有效性，已撤销的成员记进 `ineffective`，不算交付。
- 有一项不过 → `stg_result{failed, why}` → 按退避写新的 `stg_snapshot{try+1}`；第 3 次失败写 `stg_failed`。
- **需要实测**：PROD workers 能否访问 STG 的 `/health`（网络通不通），以及 PROD platform-api 能否读到 ci run 的结果。在实现时用探针确认；访问不了就改为经 STG 平台 MCP 读，并在本节补记。

**8. 人工发布的证据结算**（661 B-07 反例 2）
- 不改已有批次的记录。新的观察操作 `stg-ext:<repo>:<m>`：在不持窗口的只读循环里，看到 STG 部署了某个 P2（任何 `bifrost-deliver-platform` run，含 Owner 或统筹手动发的），且对那次 run 四项核验都过时，写 `stg_external_verified{run, uid, P, U, digests, covers:[{root, op, R}]}`。
- `covers` 只列「仍未交付、R 在 P2 的历史里、且在 P2 有效」的成员。一次人工发布可以覆盖多个历史批次；无效的成员不影响其他成员结算。
- B4 把被 `covers` 覆盖的 R 视为已交付（STG 已验证）。

**9. 卡**（接 B3 的种类表）
- `stg_failed`：选项「再发一次」（`retry_release`，Owner 授权给这些 R 新的 3 次尝试，写授权记录）、「不发」（`do_not_release`：成员算已处置未交付）。人工发布后由第 8 条自动结算，卡随之撤回（已解决）。
- `stg_blocked`：发前检查有暂时性问题且超过 2 小时，或 CI 30 分钟未出结果。
- `pending_long`：待发布超过 1 小时仍未开批。
- `stg_ineligible`：有成员被以 `ineligible` 放弃时发卡，说明原因。

**10. 范围与开关**
- 新开批次和创建 run 只在 PROD 且 live 开。
- 已有批次的 run 观察、核验、`stg-ext` 结算、卡，不受开关限制。
- STG 平台不跑本循环。

**11. 测试（PG，加假 K8s 与假 HTTP；旧代码上红）**
- 批次与处置：冻结后单个成员 `no_merge` 或被撤销 → 放弃，其余成员 release 后重新成批；后到的合法 R 继续处理；三次失败不能靠换批次清零。
- run 身份：create 回包丢失 → 同名接管；UID 变化 → 碰撞；403 不当 404；指纹不符不接管。
- 租约丢失期间别人发了 STG → 记为 superseded；P 的 CI 换了 U → 拒绝。
- 人工发布：同 P/U 与新的 P2/U2 两种都能结算。
- 关 live 开关时，已起的 run 照常观察到终态。

**12. 工作量**：按 660 估 20–30 小时；第 7 条两项网络与权限实测不通时另计。

### 11.8 B4 收尾分类细化（2026-10-28 17:1x 统筹，设计稿 v1；回应复核 661 B-06）

实读 platform `34c8f430`：`store/close.go` 的 `landingHolds` 用 `landingHoldLimit = ClaimWindow + 15 分钟` 计时放行，`RootPending` 之外的终态（landed、failed）一律不持住。B4 在 PROD live 范围内把它换成按证据分类。

**1. 政策由持久事实决定，不看当前开关**（661 B-06 反例）
- live 第一次装配成功时（workers 启动、`Controller.Live` 为真），在仓库流写一次 `landing_mode{mode:"live", at}`（已写过不重复）。
- 一个 mission 属于 **live 范围** 的条件：仓库流有 `landing_mode{live}`，mission 创建时间不早于它，且 mission 的 implement 任务属于该仓库。
- 一旦属于 live 范围，就永远按 B4 分类。关开关、撤规则、凭证缺失都不会让它退回旧的计时放行。
- 不在 live 范围的 mission、STG 演练、只有 brief 的 mission，照旧用现有规则。

**2. 每个根任务分三类**（读仓库流折叠、STG 操作、最新有效性证据；数据库内完成，不读外部）

| 类 | 条件 |
|---|---|
| **已交付** | 规则 `stg_release` 开着：R 出现在某个 `stg_verified.effective` 或 `stg_external_verified.covers` 里。规则**明确**设为 `none`：`landed` 且最新证据 = effective。规则缺失或过期 ≠ none |
| **已处置未交付** | 最新操作 `failed{declined}`（Owner 答了「不合」）、`failed{main_lost}`、`failed{reverted}`；STG 卡上答了 `do_not_release`；`stg_abandoned` 的成员处置为 `no_merge` 或 `reverted`；mission 是 `no_merge` 且该根没有 AtMain 操作、也没有运行中的 STG run |
| **未了结** | 其余全部：操作进行中、AtMain、parked、`failed{bound\|stale\|ci_red\|denied\|conflict\|…}` 未答复、`failed{result}` 未答复、landed 但未完成 STG 核验、STG run 运行中、`stg_failed` 未答复、`ineligible` |

- `failed{in_main}`（A 已被手工合进 main）：用 §10 对 H（A 在 main 里的那个提交）的有效性证据判：规则为 none 且有效 → 已交付；`stg_release` 开着时，`stg-ext` 覆盖 H 才算已交付；否则未了结。
- `stale` 未答复算未了结（661：避免 Close 与答复竞争）。

**3. mission 关闭**
- 原有任务级条件（全部任务 accepted 或被丢弃）满足后，再看落地分类：
  - 有一个未了结 → 保持 active，没有计时放行；
  - 全部已交付或已处置，且至少一个已交付 → done；
  - 全部只是已处置 → stopped。
- 关闭记录写分类计数，不写「外部动作已停止」。

**4. 无人答复**
- 永远保持 active 是预期行为（661）。出口只有：合法的 retry、「不合」、`main_lost`、mission `no_merge`、STG 卡上的处置，或人工发布后的 `stg-ext` 结算。
- B3 的过期补卡与限频提醒保证入口一直在。
- mission 详情接口加 `landing_status{delivered, disposed, unresolved, oldest_wait, reasons, last_reminded}`，供 Console 显示（页面改版跟 Design 专轮，本片只出接口）。

**5. 与其他块的接口**
- B3：未了结的根一定有卡或在暂缓期。
- B5：交付的证据来自 `stg_verified` 或 `stg-ext`。
- §10：有效性来自最新 `landing_main` 证据；AtMain 先等对账。

**6. 测试（PG；旧代码上红）**
- live on→off→on，关开关时分别处于：未领取、retry 待领、landed 未发布、stg_started、failed 未答。
- 七小时、数日未答 → 仍 active。
- 全部答「不合」→ stopped；有真实交付 → done。
- 规则 none 与 `stg_release` 两种交付判定；规则缺失不当 none。
- `in_main` 的两种结果。
- 非 live 范围的 mission 行为不变（现有测试全绿）。

**7. 工作量**：按 660 估 10–16 小时。

**§11.7 补记（17:0x 实测）**
- PROD 读 CI 结果：可以。`kubectl -n cicd get pipelinerun bifrost-ci-platform-1793222718` 的 `status.results` 有 `platform-commit`、`ui-commit`、`infra-commit`。delivery 服务本来就在 List 同一批 PipelineRun（`delivery/landing_drill.go:21`），多读 `status.results` 即可，不需要新权限。
- PROD workers 到 STG：`bifrost-platform-prod` 与 `bifrost-platform-stg` 只有 `redis-agents-ingress` 两条网络策略，`platform-api.bifrost-platform-stg.svc:8780` 不受限。
- **核验第 4 项改法**：平台 `/health`（`server/server.go:609`）不报版本，STG 部署按镜像摘要拉取、没有提交号环境变量。第 4 项改为：STG 上 `platform-api`、`platform-workers` 运行中 Pod 的 `containerStatuses[].imageID` 摘要都等于该 run 为 P 构建的摘要，且 `/health` 为 ok。与「版本 = P」等价（摘要由 run 从 P 构建），不改镜像构建。

### 11.6 v2 B3 问题卡（2026-10-28 17:2x 统筹；回应复核 665 的 B-01..B-04、R-01..R-05、N-01..N-02；**取代 §11.6 v1 与 §11.1 / §11.4 中 B3 的旧条款**）

**覆盖清单**（665 N-01）：§11.1 B3 行、§11.4「B3 问题卡 v2」、§11.6 v1 中与本节冲突的全部以本节为准。统一用词：停止记录是 `landing_stop{generation}` / `landing_resume{generation}`（§11.1 的 `landing_stopped/resumed` 作废）；refused 不派生说明卡（§11.1 作废）；「触发身份」= 仓库流事件 `(repo, seq)`；「stop generation」= `landing_stop` 正文里 B6 的编号；「n」= 同一触发的第几张物理卡；「模板版本」= 建卡请求的模板号。四者不互相赋值。

**1. 触发（665 B-04）**——每个触发都有唯一的持久事件和写入者：

| kind | 触发事件（写入者） | 仍适用（消费前在业务锁下重判） | 选项 |
|---|---|---|---|
| `root_failed` | 根的最新操作的 `failed{why}`（落地循环 / 对账 / 领取） | 该操作仍是根的最新操作且仍是这条 failed；未 retry、未 declined；mission 不是 `no_merge`、未结束 | why 可重试：`try_again`、`do_not_merge`；否则只有 `do_not_merge` |
| `floor` | **新**：领取时变更碰到不可变底线（`rules.LandingFloor` 或尺寸上限，`CheckChanges` 返回 `floor:`）→ 领取写出生即终态的 `failed{floor}`（加入 `ClaimRefusals`）；已领取的操作在闸里碰到 → `failed{floor}` | 同 root_failed | 只有 `do_not_merge` |
| `ok_missing` | `landing_anomaly{ok_missing}`（对账） | 绑定的操作仍是根的最新操作且处于 `main_result{ok}` | `confirm_main_lost`、`wait` |
| `late_landing` | `landing_anomaly{late_landing}`（对账） | 直到 `acknowledged`（原根有后继、mission 已结束也保留） | `ack` |
| `repo_stopped` | `landing_stop{generation}`（B6） | 当前最新 stop 是这条事件、尚未 resume | `repo_resume`、`keep_stopped` |
| `ci_stuck` | `parked{why:ci_stuck}`（CI 运行满 30 分钟时写，§2.5）——**立即**发卡 | 操作当前仍 parked，且它最近一次进入 parked 的事件就是这条 | `ack` |
| `parked_long` | 其他 `parked{why}` 进入事件 | 同上，且该区间已持续 2 小时 | `ack` |

可规则暂停（`rule` 不是 floor）不发卡，留给 B4 作为未了结显示。park → unpark → park 是两个区间、两个触发；旧区间离开即永久不适用。

**2. 建卡：先写准备记录，再 Ask，再绑定（665 B-01）**
- 卡片流 `landing-cards:<repo>`（**不锁仓库流**）。三个独立事务：
  1. 卡片流锁下：重判适用（快照）、查限频（第 4 条）、写 `landing_card_prepared{v, prep, repo, kind, trigger_seq, stop_generation?, n, template_version, key, request:{完整规范请求}, options:{字母→语义}}`。`key = sha256(规范 request)` 的 64 位十六进制；同一 `(trigger_seq, n)` 只能有一条准备记录（追加校验）。
  2. 锁外：`Ask(request)`，用**存下的请求原样**（模板升级不影响已准备的请求）。
  3. 卡片流锁下：写 `landing_card{prep, question_id}`；同一 prep、同一 question_id 只能绑一次。
- **恢复**：每轮先处理所有「有准备、无绑定」的记录：按存下的请求原样再 Ask。问题库返回仍受保护的同 key 卡（open，或已答未读 7 天内）就绑定它；已过期或撤回就建新卡并绑定。**触发已不适用也照样恢复并绑定**，以便收尾旧卡（第 3 条），不跳过。
- **保留期限（明确限制）**：问题库只保护已答未读的卡 7 天（`questions/types.go:164`）。控制器整体中断超过 7 天，未绑定的已答卡可能被裁剪：恢复时同 key 查不到、且准备时间已超过 7 天 → 写 `landing_card_closed{why:"lost"}` 和一条可见异常（Console 落地页可查），触发仍适用就按限频重新问。不做跨库永久交接（本片不改问题库）。
- 适配器核对（665 R-01）：新增落地专用的读卡接口，返回 requester、task、key、状态、过期时间、答案字母、自由文本、by / at / channel，区分「读失败」与「确实不存在」。绑定前核对 requester、key 与准备记录一致。

**3. 每张已绑定的卡都要走到终点（665 B-02）**
- 卡的生命周期由持久记录推出：
  - 未答（open 且未过期）；
  - 已答待处理；
  - 已处理待 Ack（有处理记录、无 `landing_card_acked`）；
  - 待撤回（触发已不适用、卡仍 open）；
  - 已结束：`landing_card_acked`，或 `landing_card_closed{why: expired|withdrawn|lost|resolved}`。
- 每轮扫描**所有未结束的绑定**，不只是每个触发的最新一张：
  - 已答 → 处理（第 5 条）→ Ack → 写 `landing_card_acked`；Ack 失败下一轮重试，处理不重复。
  - 待撤回 → Withdraw。返回 409 时重读：已答就走处理（结果多为 moot），确实已过期或已撤回才写 closed。
  - 过期判定同时看状态和 `ExpiresAt`，已答优先。读失败不当作不存在，不写 closed、不补卡。
- 锁序：卡片流只做准备、绑定、关闭、Ack 记账；业务处理沿用 task → mission → 仓库流（§8），两者分开事务，不同时持两条流锁。

**4. 限频与调度（665 R-02）**
- 卡 TTL 显式 72 小时。
- 同一触发同时最多一张未结束的卡。
- 自动补卡（过期、撤回、lost、refused）至少间隔 6 小时；滚动 24 小时内每个触发最多 4 张。计数按**准备记录**（包括建了卡但事务回滚的情况），同一 key 重放不重复计数，模板升级不清零。
- 到上限只延后，不永久关闭触发；`held` 的提醒时间与这些限制取较晚者。
- 顺序：先收尾旧卡（处理、Ack、撤回），再建新卡；决定类（root_failed、floor、ok_missing、repo_stopped）先于通知类（late_landing、ci_stuck、parked_long）。
- 问题库返回配额或容量错误时，该触发退避 30 分钟。不换 requester，不用 `ByRule`。

**5. 处理与记录（665 R-01、R-03、B-03）**
- 处理记录 `landing_answer` 加版本 `v:2` 与 `kind`。旧记录（无 kind）按 §8 原规则校验；新记录按下表校验，根卡的约束不放宽：

| kind / choice | outcome / why | 约束 |
|---|---|---|
| root_failed、floor / `try_again`、`do_not_merge`；ok_missing / `confirm_main_lost` | 沿用 §8 | 走 §8 原有的锁序、判定与协议校验；floor 只能 `do_not_merge` |
| repo_stopped / `repo_resume` | applied / repo_resumed；moot / stop_superseded、already_resumed | 无 root / mission 的专用分支；仓库流锁下核对当前最新 stop 的 seq 与 generation 都等于卡上记的、尚未 resume，才在**同一事务**写 `landing_resume{repo, generation}` 和处理记录 |
| ok_missing / `wait`；repo_stopped / `keep_stopped` | held / wait、keep_stopped | 在业务锁下重判仍适用，否则 moot；`remind_at` = 答复时间 + 24 小时 |
| late_landing、ci_stuck、parked_long / `ack` | acknowledged / ack | 只结束这个触发的通知，不代表业务已解决 |
| 该 kind 不认的字母或自由文本 | refused / unknown_choice | 保存原文，不执行别的 kind 的动作 |

- 已有处理记录的卡，重复读到就直接返回已存结果。
- 新的 note 都注册进词表（`landing_card_prepared`、`landing_card`、`landing_card_acked`、`landing_card_closed`），只允许 controller 写在 `landing-cards:<repo>` 上，键严格校验。不新增 DDL。
- 读触发用一个新的、带 seq 的持久记录读取器，不靠现有 `LandingState`（它只折叠 `body.landing`）。

**6. 反馈去向（665 R-04）**：refused、moot 的原因记在处理记录里，并按 question_id 接到现有问题详情接口（新增 `landing_outcome` 字段：是否执行、为什么、下一步）；仓库停止卡没有 mission，也从这个接口查。不派生说明卡。

**7. 运行范围与接口（665 R-05）**
- PROD workers 独立装配卡循环：只要有 Question 读取就收尾和处理已有答案；有 Ask 才建新卡；有 Ack、Withdraw 才做对应收尾。缺哪一项都在 `/health` 的 agentrt 段可见。
- 卡循环不依赖 live、MainPusher 或 Git 写身份。STG、DEV 不建、不处理这些卡。
- mission `no_merge` 或已结束 → 该 mission 的 root_failed、floor 卡进入待撤回；late_landing 不受影响。
- 与 B4 的接口：held、acknowledged、expired、refused 都**不是**业务处置。B4 只看处理结果中的 declined、main_lost 和协议终态。live 关时到限结算由谁跑，放在 B4 细化里定。
- 与 B5：`stg_failed`、`stg_blocked`、`pending_long`、`stg_ineligible` 卡随 B5 实现，复用本节的准备、绑定、收尾机制；批次身份另成一个 kind，不塞进 root 卡。

**8. 卡文案（665 N-02）**：英文。写仓库、任务标题、第几次操作、原因与发生时间、各选项的后果、下次提醒时间；`repo_resume` 写明「解除停止，不重试原失败，不自动发布」。审计 id 放详情，不塞正文；只有真正的 WorkID 才放链接。

**9. 测试（PG，旧代码上红）**：
- 建卡与恢复：Ask 成功但绑定事务失败 × 同模板 / 升级模板；回滚后触发已解决；孤儿已答未绑定；超过 7 天且已裁剪 → lost 与异常。
- 收尾：Q1 已处理、Ack 失败、Q2 已绑定后 Q1 仍能 Ack；处理提交后回包丢失；答复与撤回在两个连接上竞争；扫描到已过期仍 open 的卡；读超时与真正 404。
- B6：stop 的 seq 与 generation 故意不同；stop1 → resume1 → stop2 后旧卡的答复；重复 `repo_resume`；resume 写后处理记录失败整笔回滚。
- 触发：首次领取碰底线（无操作）、已领取后碰底线；ci_stuck 满 30 分钟；park / unpark / repark 后旧卡晚答；late_landing 的原根已 declined 或已有后继。
- 限频：自由文本连答、跨日、模板升级。
- 范围：live on→off→on；缺 Ask / Ack / Withdraw 各一；STG 零卡。

**10. 工作量**（665）：B3 27–41 小时（原 12–20）。

### 11.9 Owner 决定：B5 放到开门之后（2026-10-28 17:1x，线程里点选「放到开门之后」）

- S3 开门范围 = B1 真推 main + B6 停仓库 + B3 问题卡 + B4 收尾分类 + 跨块验收。**B5 STG 自动发布在开门之后做**，设计 §11.7 与复核 666 的意见留作 B5 的起点。
- 开门时第 1 版规则对 `bifrost-platform` 写 **`stg_release: none`**（Owner 签字时确认）。STG 照旧由统筹按「STG 发布 A」手动发（持窗口、CI 绿、发后核对），不进 S3 的自动流程，也不算 B4 的交付证据。
- 连带：B3 不做 STG 类卡（`stg_failed`、`stg_blocked`、`pending_long`、`stg_ineligible`）；B4 的「已交付」只走「规则明确 none + landed + 关闭时当前有效」一条路径。
- 剩余工时（按复核 665、667 的数，去掉 B5）：B3 27–41 + B4 约 20–32 + 验收 8–12 ≈ 55–85 小时；开门估 **11-05 至 11-08**。

### 11.8 v2 B4 收尾分类（2026-10-28 17:0x；回应复核 667 B-01..B-05、R-01..R-05、N-01..N-02；按 §11.9 不含 B5；**取代 §2.7、§11.1、§11.4 中 B4 与「stale 算处置」的旧条款，及 §11.8 v1**）

**1. 根的归属（667 B-01）**——按根判定，再聚合到 mission：
- `liveFence` = 仓库流上 `landing_enabled` 与 `landing_mode{live}` 两个事件时间中较晚者（都要有）。`landing_mode{live}` 在 workers 首次以 live 装配时、于任何 PROD 领取之前写入（仓库流锁下幂等；`ClaimLanding(prod)` 要求它已存在，否则拒绝领取）。
- 一个 implement 根属于 **live 落地范围**，当且仅当：
  (a) 仓库流里它有 PROD live 操作（`claimed` 且 `dry_run` 不是 true；出生即失败的根以记录里的环境与 `v` 判定，不靠 `DryRun` 零值）；或
  (b) 它的 repo 是 `bifrost-platform`，accepted 时间与当前 mission 创建时间都不早于 `liveFence`，mission 不是 `no_merge`。
- (a) 一旦成立永久成立：rebind、规则撤回、凭证缺失、关开关都不改变。
- 不在范围的根（早于栅栏、别的仓库、brief / verify / review）照旧按现行规则，B4 不持住它们。
- 一个 mission 只要有一个范围内的根，就由 B4 决定关闭；范围外的任务只参与原任务级条件。

**2. 每根恰好一类，按优先级判（667 B-03）**——在关闭事务里、仓库流锁下读：

| 优先级 | 条件 | 类 | 原因码 |
|---|---|---|---|
| 1 | 最新操作 AtMain（main_intent、main_result 非 non_ff 且尚未 landed） | 未了结 | `at_main` |
| 2 | 最新操作 landed、其后没有 `reverted`，且最新 `landing_main` 证据 = effective 且读取时间晚于本 mission 的 `close_ready`（第 4 条），且关闭时的规则对该仓库**明确** `stg_release: none` | **已交付** | `landed` |
| 3 | 最新操作 landed 且其后有 `reverted{R,by}`（独立撤销记录） | 已处置 | `reverted` |
| 4 | 最新操作 `failed{declined}`、`failed{main_lost}`、`failed{reverted}`（领取前发现已撤销） | 已处置 | 同 why |
| 5 | Owner 在卡上处置：`landing_disposed{root, op, why:"owner"}`（第 5 条的新记录） | 已处置 | `owner` |
| 6 | 根任务是 Owner 在阻塞卡上丢弃的（cancelled + `owner_wait_closed{outcome:dropped}`），且它没有 AtMain 操作 | 已处置 | `dropped` |
| 7 | `failed{in_main}` 且结构化外部合入证据（第 3 条）显示 H 当前有效（同第 2 条的新鲜度与规则要求） | 已交付 | `in_main` |
| 8 | 其余全部：进行中、parked、discarded / non_ff / retry 待领（AwaitsNext、Retried）、`failed{stale|bound|ci_red|denied|floor|result|conflict|…}` 未处置、landed 但证据不是 effective 或不够新、规则不是明确 none、`in_main` 没有结构化证据或 H 不有效 | 未了结 | 具体原因 |

- 同一根的事实冲突时，按表的优先级取第一条。较新的撤销胜过较旧的有效。mission `no_merge` 不覆盖已交付（事实保留，关闭记录两者都写）。
- `failed{stale}` 未处置一律未了结（作废 §2.7、§11.1 的「stale 算处置」）。refused、moot、Ack、卡过期都不改变分类，只有已应用的处理记录才会。

**3. `in_main` 的结构化证据（667 B-04）**
- 领取写 `failed{in_main}` 的同一事务里，另写 `landing_external{root, op, attempt, A, H, head, validity, read_at}`。H 取自领取时读到的 History.Commit；H ≠ A 是常态，不伪造 prepared / landed。
- 对账器的候选加上「open mission 里 `failed{in_main}` 的根」，用 `MainEvidence(r=H, task, a=A)` 定期刷新，写新的 `landing_external` 观察（与 §10 的 landed 观察同样按读取时间排序、不去重）。
- 旧的 `in_main` 没有结构化记录：对账器补读一次 History 写入，再按上面判定；补读之前算未了结。
- 一旦根被判为已交付或已处置，B3 撤回它的 `root_failed` 卡。

**4. 关闭时的新鲜证据（667 B-02）**
- 一个范围内的 mission 第一次「任务级条件都满足、且没有第 2 条以外的未了结原因」时，Close 写 `landing_close_ready{mission, at}`（mission 流）。
- 对账器优先读这些 mission 的 landed 与 in_main 根。Close 只在每个要算交付的根都有一条读取时间晚于 `close_ready.at`、且为 effective 的证据时才关闭。
- 剩余风险写明：证据读取到关闭之间仍有几分钟窗口。关闭后对账器继续看这些根 24 小时；后来出现的撤销记为事实，并发一张 `late_revert` 卡（B3 的通知类），不重开 mission。

**5. 每个未了结原因都有推进者和 Owner 出口（667 B-05）**

| 原因 | 谁推进 | Owner 能做什么 |
|---|---|---|
| `at_main` | §10 对账（与开关无关） | 等；ok_missing 走 B3 卡 |
| 进行中、parked、retry 待领 | 落地循环；**到限结算（6 小时 / 8 次）搬进独立对账循环，与 live 开关无关** | 到限后变成 `failed{bound}` → root_failed 卡 |
| failed 各类未处置 | — | B3 root_failed / floor 卡：`try_again`（可重试时）、`do_not_merge` |
| landed 但证据不是 effective（unknown / absent / unreadable）满 2 小时 | 对账继续读 | **新** B3 kind `landed_unverified`：`wait`（暂缓 24 小时）或 `confirm_not_delivered` → 写 `landing_disposed{why:"owner"}` |
| 规则不是明确 none | — | Owner 签新规则版本；不提供卡上绕过 |
| `in_main` 无证据或 H 不有效满 2 小时 | 对账补读 | 同 `landed_unverified` |

- 不新增 mission 级 no_merge 修改入口；逐根处置足够覆盖所有非 AtMain 的情况。

**6. 规则取值时点（667 R-01）**：用关闭决定时的现行 `landing:<tenant>` 版本；对该仓库必须明确 `stg_release: none`。缺失、过期、仓库条目被移除、读取失败分别记原因，都算未了结，不从旧版本里找有利的 none。关闭记录保存 rule id / version 与取值。

**7. 一致性（667 R-02）**：Close 的事务按 mission（现有 `FOR NO KEY UPDATE`）→ 各相关仓库流（固定字典序 `lockStream`）的顺序加锁，再折叠分类并 `MoveMission`。对账器与答复处理写仓库流时都持流锁，所以与 Close 串行。坏流只持住本 mission（沿用 savepoint）。

**8. 关闭条件与其他入口（667 R-03）**
- 保留原候选条件（mission active、没有绑定 plan_node、任务都 accepted 或 Owner 丢弃）。
- 有范围内根的 mission：没有未了结的根时，「已交付的根 ≥ 1，或有 accepted 的 brief」→ done，否则 → stopped。旧的 `drops == 0 → done` 对这类 mission 不再适用。
- blocked 卡上的「关闭 mission」是 Owner 的明确决定，照旧允许；关闭记录写分类计数，不写成已交付。AtMain 的对账不受 mission 状态影响。

**9. 状态接口与卡的适用性（667 R-04）**
- mission 详情接口加 `landing_status`：逐根给出 {root, op, class, reason, since, question_id, actions}，以及最老等待时间、最后提醒时间（都从持久记录推出）。
- B3 各 kind 的「仍适用」判断直接用这里的分类：已交付或已处置的根，卡进入待撤回。
- Console 接入：在现有 mission 详情加一个最小的落地状态表。改 Console 前先登记 `design/codex/ops/COORDINATION.md`。这是业务入口，开门前验收，不等 Design 专轮。

**10. 关闭文案（667 N-01）**：英文，单位是落地根，例如 `Closed from landing evidence at <time>: 1 root delivered, 1 disposed, 0 unresolved (rule landing:dev v<n>, stg_release none).`。任务计数另列；不写 `all work delivered`、`external actions stopped`。

**11. 测试（667 R-05 矩阵，去掉 B5 行）**：
- 归属：mode 与 enabled 的先后、等时；rebind；混合仓库；出生即失败。
- 优先级表：每行一个例子，再加冲突组合（较新撤销胜过较旧有效、no_merge 加已交付、refused 不改变分类）。
- 关闭：
  - 1 交付 + 1 未答 → active；1 交付 + 1 dropped → done；全部 dropped 或处置 → stopped；
  - live on→off→on（真正销毁、重建控制器；撤规则；去掉凭证）；
  - 七小时、数日未答 → active，到限结算在开关关闭时也跑。
- 新鲜度：landed 后、Close 前撤销；有效后读失败；旧观察晚提交。
- `in_main`：H ≠ A；重启；H 后来被撤销；旧记录的补读。
- 并发：答复、retry、对账写入与 Close 在两个连接上交错。
- 非 live 回归：STG 演练、旧 mission、brief-only、plan_node mission、暂停的 mission 行为不变（旧测试保持绿，新测试在旧实现上红）。

**12. 工作量**：约 20–32 小时。复核 667 估的 23–37 小时里含 B5 接口的部分，这里去掉了；新增了 `landed_unverified` 卡和 `in_main` 证据刷新。

### 11.6 v3 B3 问题卡收口（2026-10-28 17:1x；回应复核 668 的 B-01..B-04、R-01..R-05、N-01..N-02；**在 §11.6 v2 基础上修订，冲突处以本节为准**）

按「每条线最多两次」：B3 已经过 665、668 两轮设计复核，本节收口后直接实现，余下问题在代码复核里查。

**1. 建卡与恢复串行化（668 B-01）**
- 准备记录照旧先独立提交，并且算进「同一触发最多一个待决策请求」：已有未终结的准备或未结束的待决策卡时，不再准备 n+1。
- Ask 和绑定都在**持卡片流锁的同一事务**里完成（同 `askBlocked`），只锁卡片流、不锁仓库流。两个恢复者因此串行：后来者在锁内重读，发现已绑定就跳过。
- Ask 有超时上限。超时后迟到返回的卡没有绑定，按同一个 key 由下一轮恢复找回（见第 2 条）。
- 幂等 key = `sha256(canon{route, repo, kind, trigger_seq, n, template_version})`，不含正文。完整请求另存，并存 `request_fp`。

**2. 恢复状态表（668 B-02）**——在卡片流锁内按持久前态逐条处理：

| 前态 | 处理 |
|---|---|
| 有准备、无 `ask_started` | 写 `ask_started{prep, at}` 并提交；然后在锁内 Ask、绑定 |
| 有 `ask_started`、无绑定 | 先**无副作用**地 `LookupKey(key)`：找到 → 核对完整请求后绑定。找不到且 `now − ask_started.at < 7 天` → 重新 Ask、绑定。原因：若卡被答过，从答复时起受保护 7 天，而答复不早于 ask_started，所以这里找不到就说明从未建成，或建成后未答就已过期 / 撤回。找不到且 ≥ 7 天 → 写 `landing_card_closed{prep, why:"unconfirmed"}` 与一条可见异常，准备终结、不再 Ask；触发仍适用就按限频准备 n+1。读失败 → 什么都不写 |
| 已绑定、未处理 | 用会触发过期清扫的权威读取（同 `Get` 持久化过期）：已答 → 处理；open 且未到期 → 等；问题库确认 expired / withdrawn → `closed{expired\|withdrawn}`，触发仍适用就按限频补卡；确实 404 → 有处理记录就 `closed{gone_after_handled}`，没有就 `closed{lost}` 并记异常、按限频补卡；读失败 → 不写 |
| 已处理、未 Ack | Ack：成功或「已 Ack」→ `landing_card_acked`；404 → `closed{gone_after_handled}`（不重做业务、不伪造 Ack） |
| 待撤回 | 调落地专用的 Withdraw（返回实际状态）：withdrawn → `closed{withdrawn}`；已答 → 走处理（多为 moot）；其他 → 下一轮重读 |
| 已结束 | 不再处理 |

- 本地时间过了 `ExpiresAt` 只是触发一次权威读取，不据此关闭。
- 7 天限制针对「某张卡持续没被消费」，不只是整体停机。

**3. floor 的协议与原因链（668 B-03）**——已实现于 platform `6e3303dd`：
- floor 不加入 `ClaimRefusals`（那是「只许出生时使用」的原因）。它加入的是「允许出生即失败」的原因集合，并且照旧可以用于 claimed / prepared / branch_pushed / parked → `failed{floor}`。
- 类型化原因：`rules.FloorViolation` 只覆盖**不可变**底线（底线路径、非普通文件、二进制或不支持的差异、无路径）。尺寸上限由签名规则定义，可以由新版本放宽，所以归 `rule`（停放）；当天配额、并发配额仍是 `limit`（停放）。领取、中间闸、最终闸用同一判断。
- floor 卡只有 `do_not_merge` 与 `wait`（第 4 条）；`try_again` 不提供，处理器对 floor 拒绝 retry。

**4. 每张卡至少两个选项（668 B-04）**：问题库只接受 2–4 个选项（`questions/canonical.go:361`），不改问题库。原来只有一个选项的 kind 加一个有业务含义的第二选项：
- floor、不可重试的 root_failed：`do_not_merge`，或 `wait`（暂缓 24 小时，届时再问）；
- late_landing、ci_stuck、parked_long：`ack`，或 `remind_later`（暂缓 24 小时，届时再提醒）；
- 两者都写 `held`。

**5. 记录矩阵与适配器（668 R-01）**
- 处理记录 v2 的公共字段：repo、prep、question_id、kind、trigger_seq、原始字母、语义 choice、原文、channel、by、answered_at。
- 根卡另带 root、op、mission_state；仓库卡不带这三项，另带 stop_generation。
- 失效时的 why：`wait` / `remind_later` / `keep_stopped` 遇到触发已不适用 → moot / `trigger_gone`；`ack` 遇到旧区间 → moot / `trigger_gone`。先判 unknown_choice，再判是否适用。
- 落地专用的问题库适配器：`AskRaw(request)` 显式带 TTL 72 小时、允许自由文本、选项顺序冻结，返回 question_id 与 key；另有 `LookupKey`、`Lookup`（权威、清扫过期）、`Withdraw`（返回实际状态）、`Ack`。不走 `SameByKey` 的宽松回退。绑定时核对 `request_fp`、requester、task、key 与准备里的映射。

**6. 限频与调度（668 R-02）**
- 冷却从**真实建卡**时间算（`ask_started` 之后绑定成功的时间，或找回时卡的 `CreatedAt`），不从准备时间算。每个触发持久记 `next_ask_at`。
- 同一准备因原卡过期而重新 Ask、生成新的 question_id，也计一次。
- 每轮顺序：处理 → Ack → 撤回 → 有界恢复 → 新建。恢复与新建共享本轮预算，类别内按触发轮转，按等待时间提升优先级。
- 通知卡占满 open 配额时：先撤回已超 24 小时未答的通知类卡（`remind_later` 语义），为决定类腾位；仍不够就在 `landing_status` 里显示「等待配额」。

**7. 触发互斥与区间变化（668 R-03）**
- 同一 `(repo, trigger_seq)` 至多对应一个 kind：root_failed 排除 declined、main_lost 与 floor；parked_long 排除 ci_stuck 与 rule。
- 已经 parked 的操作原因变了（例如 limit 停放期间 CI 转为运行超 30 分钟），落地循环在同一仓库事务里写 `unparked` 再写 `parked{ci_stuck}`，开一个新区间、新触发；旧区间永久不适用。这是 CI 步骤要补的写入（实现时改 `LandingDrillCI` 的 parked 分支）。

**8. 现有页面接线（668 R-04）**
- 现有问题详情页（`console/src/pages/QuestionPage.tsx`）显示 `landing_outcome`：待处理、已执行、已暂缓、已知悉、moot 与 refused 分开显示。
- 按 question_id 查结果走独立接口：问题记录被裁剪后，结果仍可从仓库流查到。`lost` 和 `unconfirmed` 按 prep 查。
- 任务卡链接到任务详情，仓库卡链接到仓库停止状态（由详情根据绑定推出），不伪造 WorkID。改 Console 前先登记 `design/codex/ops/COORDINATION.md`。

**9. 开门能力与到限结算（668 R-05）**
- 恢复可以降级：缺什么就停什么，其余照跑。
- **新的 live 执行**要求卡的四项能力（Ask、Question、Ack、Withdraw）都在，否则 live 循环不领取新根，`/health` 写明缺了哪项。
- 关开关后，纯数据库的到限结算由独立对账循环负责（§11.8 v2 第 5 条），只覆盖持久的 live 范围，仍走协议与锁，不碰 Git 写。
- B4 读的处置是 applied 处理记录的 why 和协议记录，不是 Ack 或 closed。「未了结一定有卡」放宽为：一定有卡、暂缓中、或在 `landing_status` 里写明「等待规则 / 等待配额 / 已通知」。

**10. 术语与测试前提（668 N-01、N-02）**：§8、§11.4 的 B6 行、§11.1 加「以 §11.6 v3 为准」。采用「一个待决策卡，允许多个待收尾的历史卡」。历史 Ack 的测试用预置数据构造。

**11. 工作量**：按 668 估 30–45 小时（含 floor 协议，已完成）。S3 开门剩余：B3 30–45 + B4 20–32 + 验收 8–12 ≈ 58–89 小时，开门估 11-05 至 11-08 不变（Codex 估的是单人有效工时，统筹与 Codex 并行）。

### 11.8 v3 B4 收口（2026-10-28 17:2x；回应复核 669 的 B-01..B-04、R-01..R-04；在 §11.8 v2 基础上修订，冲突处以本节为准；B4 两轮设计复核已满，收口后直接实现）

**1. 一个归属函数，领取与收尾共用（669 B-01）**
- `landing_mode{v:"1", repo, env:"prod", mode:"live"}`：controller 在仓库流锁下写一次（已有则不写），只在 PROD 的 workers 以 live 装配时写；STG 的库里永远没有它。`ClaimLanding(prod)` 在同一把锁下先确认它已提交，否则拒绝领取。
- `liveFence = max(enabled.at, mode.at)`，等时算在内。PROD 的 `EligibleToClaim`、`inHandoff`、`SettleUnclaimed` 与 Close 都用同一个 `landingScope` 函数做时间比较（替换只看 `EnabledAt` 的比较）。
- 「根有 live 历史」的持久证明：仓库流上它有一条 seq 大于 `landing_mode` 事件 seq 的操作记录（claimed 或出生失败）。PROD 的库里，mode 之后的每个操作都是 live；这一点由库归属与流序号证明，不靠 `dry_run` 零值。没有 mode 记录的流（STG、旧数据）一律走旧政策。
- Close 在 mission 锁之后、仓库流锁之下选择新旧政策，与 mode 的写入串行。

**2. 关闭取证轮次（669 B-02）**
- 当一个范围内的 mission 满足任务级条件，且每个根要么已处置、要么**只差新鲜证据**（landed 或 `in_main` 且没有其他未了结原因）时，Close 在 mission 流写 `landing_close_round{round, roots:[{root, op}], at, deadline: at + 30 分钟}`。round 号递增；根集合或处置变化后，旧轮次作废。
- 对账器见到未过期的轮次，就绕过 30 分钟重查等待，优先读这些根（公平预算不变）。
- Close 只在以下都成立时关闭：本轮次未过期；每个要算交付的根，都有读取时间晚于 `round.at` 的最新证据，且为 effective；决定时间早于 `deadline`。轮次过期就开新一轮，不挪旧轮。
- 全部只是处置的 mission 不需要取证，直接关闭。
- 剩余窗口写明：最多是「证据读取到关闭」的这几十秒到 30 分钟。关闭后 24 小时内对账器继续看交付的根，撤销记为事实，并发 `late_revert` 通知卡（第 4 条）。不在 Close 事务里读 Git。

**3. 决定表（取代 v2 第 2 条；669 B-03、R-01）**

| 优先级 | 条件 | 类 |
|---|---|---|
| 1 | 最新操作 AtMain | 未了结 `at_main` |
| 2 | **平台合入**（`EverLanded && !Reverted`）或**外部合入**（`failed{in_main}` 且最新 `landing_external` 显示 H 有效），满足第 2 条的新鲜度，且关闭时规则明确 `stg_release: none` | **已交付** |
| 3 | 平台撤销（`EverLanded && Reverted`），或外部撤销（最新 `landing_external` 确认 H 已撤销，带 `reverted_by`） | 已处置 `reverted` |
| 4 | 最新操作 `failed{declined｜main_lost｜reverted}` | 已处置 |
| 5 | `landing_disposed{why:"owner"}`（第 4 条） | 已处置 `owner` |
| 6 | Owner 在阻塞卡上丢弃的根，且没有 AtMain | 已处置 `dropped` |
| 7 | 其余全部 | 未了结（具体原因） |

- 平台合入与外部合入同一优先级、同一冲突政策：有新鲜、有效的交付，就算交付；Owner 的处置只表示不再等，不抹掉合入事实（两者都写进关闭记录）。
- `failed{in_main}` 一出现，B3 的触发就把它排除在 `root_failed` 之外（不提供 try_again / do_not_merge），改由外部证据路径接管。旧卡在消费时锁内重判，记 moot / `trigger_gone`。
- `landing_external{v:"1", repo, root, op, attempt, A, H, head, read_at, validity, reverted_by}`：validity ∈ effective、reverted、unknown、absent、unreadable，字段组合同 `landing_main` v2；`read_at` 取外部读取开始前的 DecisionAt；与 §10 一样按读取时间排序、不去重。首次由领取写（与 `failed{in_main}` 同事务）；旧记录由对账器从已接受 attempt 的记录重建身份后补读。重建不了就保持未了结，并在 `landing_status` 写明原因。不解析说明文本。

**4. 两张新卡接进 B3 生命周期（669 B-04）**

| kind | 触发与等待区间 | 仍适用 | 选项 → 处理 |
|---|---|---|---|
| `landed_unverified` | 根是平台或外部合入，且最近一次 effective 观察之后（或合入之后，如果从未 effective）出现的**第一条非 effective 观察**；trigger_seq = 该观察事件的 seq；满 2 小时才发 | 自该观察起所有观察都非 effective，根不在 AtMain、未处置 | `confirm_not_delivered`：在 task → mission → 仓库流锁下重判仍适用，同事务写 `landing_disposed{v:"1", root, op, trigger_seq, question_id}` 和 `landing_card_outcome{applied, not_delivered}`；`wait`：held 24 小时 |
| `late_revert` | mission 已关闭 24 小时内，交付的根出现撤销（平台 `reverted` 记录或外部 reverted 观察）；trigger_seq = 该事件 seq | 直到 ack | `ack`、`remind_later` |

- 一次恢复 effective 就结束当前区间；再次失效会开新的区间、新的触发。重启不清零。
- 只有**需要业务决定**的根卡（root_failed、floor、ok_missing、landed_unverified）在根被分类为已交付或已处置时进入待撤回。late_landing、late_revert 只以自己的 ack 结束；repo_stopped 按 stop generation 结束。
- 处理结果词表加 `applied/not_delivered`（仅 landed_unverified）。

**5. 规则取值的决定点（669 R-02）**：Close 不在 mission 锁之后反向取规则锁（会违反全局锁序）。决定点 = 取齐 mission 锁与仓库流锁之后，用 DecisionAt 读 `CurrentRule`；关闭记录保存这个时间与 rule id / version / 取值。规则写入与关闭不串行，接受这个窗口：关闭依据的是决定点那一刻的生效版本，事后可追溯。规则读失败只持住这个 mission。

**6. 数据库结算的循环（669 R-03）**：独立对账循环每轮先做两件纯数据库的事，再碰 Git，都在 live、写身份、Git reader、规则检查之前：
- 已有操作与 AwaitsNext 的预算结算（`SettleLandingDrillBounds` 的 PROD 版本）；
- 范围内从未领取的根的到限结算（`SettleUnclaimed`，用第 1 条的归属函数）。
- 两者分开事务，各自按原锁序，AtMain 排除。
- 出口口径改为「逐根处置或规则修正」：规则不是明确 none 时，出口是 Owner 签新规则，不提供卡上绕过。

**7. 测试（669 R-04）**：在 v2 第 11 条之上补：
- mode 与 enabled 的四种先后（含等时），以及领取和 Close 的调度先后不改变政策；
- 关闭取证轮次的过期与重开，「ready 后进程停三天」不关 done；
- `in_main` 遇到旧 do_not_merge 卡记 moot；外部撤销算处置；
- `landed_unverified` 区间：恢复后再失效开新触发；
- late_revert 在关闭后撤销时发卡；
- 规则在关闭前一刻换版本。

**8. 工作量**：按 669 估 29–44 小时（单人有效工时）。剩余合计：B3 余量约 18–30（核心记录、触发、引擎已完成）+ B4 29–44 + 验收 8–12。开门估 **11-06 至 11-09**（比 §11.9 晚约一天，原因是 B4 复核上调）。

### 11.10 实现记录：B3、B4 与设计稿的差异（2026-10-28 18:1x；platform `w31/s3-wiring-a` `48d3467a`）

实测问题库后改了两处，复核后又改了几处。下面是与 §11.6 v3、§11.8 v3 不同之处，以及已知留待后续的项：

- **ci_stuck、parked_long 不发卡，只在落地状态里显示**：问题库给运行时总共 3 张未读卡、每小时 6 张新卡（所有运行时卡共享，实测 `questions/types.go` 的 open / protected / hourly 配额）。这两类通知会挤占需要 Owner 决定的卡。停放到 6 小时上限会变成 `failed{bound}`，那时再问。
- **`in_main` 不做外部证据刷新**：改为发一张 `in_main` 卡（「算作已交付 / 算作未交付」），答复写 `landing_disposed{owner_delivered | owner}`。在规则明确 none 时，`owner_delivered` 算交付。理由：领取前就已在 main 的根很少见，而外部合入的结构化证据链（§11.8 v3 第 3 条）工作量大；先给 Owner 一个合法出口。
- **非 §8 的处理记录用独立的 `landing_card_outcome`**，不给 `landing_answer` 加 v2；§8 的三种选择仍写 `landing_answer`。两种记录都按问题号查、校验归属后才返回（670 R-01）。
- **额度错误（429）只暂停新建卡 30 分钟**（仅内存），收尾与按 key 找回照跑。
- **已知、留待后续**（未在本轮实现，开门前要么实现、要么写明接受）：
  - Ask 的端到端期限：问题库的状态存储不吃 context，卡片流可能被慢调用占住（670 R-05）；
  - 按 prep 查询 `unconfirmed`、`lost` 异常（670 R-07）；
  - `/health` 上逐项列出卡能力（670 R-04）；
  - 卡的预算轮转，以及通知卡给决定卡让位（670 R-03）；
  - mission 详情页的落地状态表（接口 `GET /agentrt/landing/missions/{id}` 已有，前端另派）。
