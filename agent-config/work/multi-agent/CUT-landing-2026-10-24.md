# 切法：4.1 交房——验收通过的活由运行时自己合进 main（2026-10-24，第 2 稿）

**这份文档回答什么**：Owner 10-23 23:3x 定「D4 A」：验收通过的活由运行时自动进 main，先 bifrost-platform、bifrost-trade-infra，PROD 仍按发版策略，规则由 Owner 签。本文写三件事：
- 今天一件活从 agentd 推分支到进 main 实际怎么走（§1，带 `文件:行`）；
- 运行时自己合、自己发 STG，要哪些前置条件、步骤、记录，出错怎么办（§2）；
- 分几片做、每片怎么验收、哪几片要 Owner（§3）。

**Owner 要定什么**：
- §4 的七个架构级选择；
- §2.3 规则 `landing:dev` 的可判定契约；
- 动手的几样：撤掉 STG 对 Gitea 管理员令牌的读取（TD-432）、签规则、在 Gitea 建身份并加进 main 的推送名单、批发布单。

全部待定点在 §5 一张表里。

**第 2 稿相对第 1 稿**（`047ea5ca`）：回应 Codex 复核 533（结论「先改」），以及 4.6 复核 534 的 B1。逐条回应在 `~/agent-work/codex-review-533/RESPONSE.md`。主要改动：
- 第一片收窄成「只合 platform 的 Console 文案和纯展示组件」（B6）；
- 加前置条件 P0：STG 拿不到 Gitea 管理员令牌（A1）；
- 硬底线和可申请的例外分开（A2）；
- 一条共用的资格判定，用在领取、推 main 前、发 STG 前三处，包括「计划和 mission 仍要这件活」（A3、534 B1）；
- 落地写成有操作号、先记意图再动手、可对账的协议（A10）；
- STG 发布钉死两个提交号，「待发布」单独记录（A7、A8）；
- 第一片的失败只开落地问题，自动修复挪到 S4（A4、A5）；
- 旧的 20 件与 D-L5 对齐（§2.2）。

**读的版本**：
- infra `639edc9`；
- platform `origin/main` = `82b3e9d7`；
- PROD、STG 运行时库，10-24 05:xxZ 只读查询（`agent_reader`）；
- 集群只读 `kubectl get`。

第 2 稿**还没有复核**。

---

## 0. 一段话

今天运行时把活做到 `accepted` 就停了，要统筹线程手工 cherry-pick、跑整套、经 `push-main.sh` 推（TD-383）。

推荐的做法：PROD 的 platform-workers 多一个「落地」循环。每件落地是一次有编号、逐步记在运行时库里的操作：
1. 在 main 最新提交上用固定的时间戳重放收下的提交，得到候选 R；
2. 推到 `land/prod/<任务>/<k>`，CI 随推送起；
3. 推 main 之前，按当前规则和当前计划再完整判定一次资格；
4. CI 绿、窗口不挡、main 没动，才把同一个 R 快进推到 main；
5. 发 STG 时钉死 platform 和 ui 两个提交号，核对发布差异的权限、镜像摘要和健康检查。

第一片只开放 platform 的 Console 文案和纯展示组件，一件在途；冲突、检查失败都开成明确的落地问题，不自动修。前置条件是先切断 STG 拿 Gitea 管理员令牌的路（TD-432）。落地身份只在 platform 一个仓库 main 的推送名单里，令牌只挂进 PROD 的 platform-workers。

---

## 1. 现状实读

### 1.1 一件 implement 任务今天怎么走到 main

| 步 | 谁 | 实读 |
|---|---|---|
| 建任务 | 控制器 | base 取当时 main 的头：`store/planresult.go:247-249` |
| 提交、推分支 | agentd（06） | 尾注 `Agentrt-Task`、`Change-Id`、`Work`，没有 `Claude-Session`：`agentd/workspace.go:343-350`；只许推 `refs/heads/agent/`：`:355-358`；分支名：`store/kernel.go:78-81` |
| 验收 | 控制器 | 确定性检查 → 异家评审 → `accepted`：`store/accept.go:13-21`、`:398-407`；检查命令写死在 `store/repos.go:68-95`（只有 platform、infra） |
| 状态 | — | `accepted` 没有出边：`kernel.go:132-143`；`failWork` 也按这张表走：`kernel.go:180-192`；库里有 CHECK：`migrations/0001_core.sql:135-136` |
| 依赖 | 控制器 | 依赖的任务 `accepted` 就放行，不看进没进 main；被依赖的任务被取消或驳回才挡：`store/propose.go:754-777` |
| 撤计划步骤 | Owner 的计划变更 | `dropStep` 只把步骤改成 dropped；步骤上已 `accepted` 的任务不算「未完成」，原样留着：`store/planchange.go:540-570` |
| mission 结束 | 控制器 | 任务全部 `accepted` 就关成 done：`store/close.go:40-45` |
| 进 main | **统筹线程手工** | `merge_accepted.py apply --push`（§1.2） |
| 补记 | 控制器 | 每 5 分钟读一次 main，见到收下的提交就记 `note{landed}`，被 revert 的不算：`controller.go:426-442`、`store/prune.go:364-437` |
| 删分支 | agentd | `store/prune.go:16-47`，`landed` 之后 24 小时 |

### 1.2 `merge_accepted.py`（infra `scripts/agentrt/merge_accepted.py`）

- 只接「任务 base 上的一个提交」：`:391-400`。
- 认 `git revert` 的标准格式：`:329-384`。
- `plan` 判断「已在 main」时，丢掉了 `landed()` 返回的「曾落地后被撤销」这个理由：`:464-466`（复核 534 B1 指出）。
- 改写提交信息时写死「Until the release queue, the coordinator merges…」，并给 `Work` 加 `TD-383`：`:410-445`。
- 在干净 worktree 里 cherry-pick，跑 platform 的整套和 code-health：`:472-540`。
- `--push` 只对 platform：`:71-75`。

### 1.3 TD-383、TD-387、TD-432

- TD-383（`TECH_DEBT.md:2706-2717`）：收下的活由统筹线程经 `push-main.sh` 合，运行时按规则删分支。只剩「PROD 上第一条 `pruned`」没验收，而 PROD 已有 23 条。
- TD-387（`:2653-2664`）：platform 任务的检查不跑 code-health，收下的修复要到推 main 时才被拒。
- TD-432（统筹线程正在记，P1）：STG、PROD 的平台身份都能读 Gitea 管理员令牌，见 §1.5。

### 1.4 Gitea 1.21.11 的保护、推 main 的门槛、CI

**Gitea 保护**
- `main`：推送和合并白名单只有 `maintainers` 和 Owner（`scripts/gitea/protect-repo.sh:5-7`、`:205-218`）。谁都不能删、不能强推（`CUT-gitea-primary-2026-10-17.md:119`）。
- `agent/**`：10-20 由 Owner 去掉保护（`protect-repo.sh:8-12`、`:243-256`）。
- 标签规则：只能在页面上设（`:13`、`:258`）。

**`push-main.sh` 的门槛**，按执行顺序：
1. 窗口关着（`:182-190`、`:273`）；
2. 只快进（`:275-277`）；
3. 新提交都有 `Change-Id` 和 `Claude-Session`（`:290-316`）；
4. CI 绿（`:452-505`），`CI_REPOS` 不含 infra（`:117`）；
5. code-health（`GATED` `:113`、`:534-540`）；
6. 快测：platform 跑 `go vet ./...` 加改到的包（`:375-398`），infra 跑 pytest（`:344-368`）；
7. 再查一次窗口（`:558`）；
8. 推（`:559`）。

**CI**
- 推任何分支都起 CI（`trigger-trade-ci.yaml:221-225`）。只有三条流水线，没有 infra 的（`delivery/ci_run.go:11-17`）。
- ci-platform 跑 `go test ./...` 和 code-health，**不跑 `go vet`**（`pipeline-ci-platform.yaml:175-176`、`:283-292`）。
- 平台判 CI 结果时按「仓库@提交」建索引，**只要有一次成功就算成功**（`release_policy_facts.go:241-244` 与其下的建索引循环）。
- 外部调用方起 CI 只能指定 `revision`，指定不了 ui（`ci_run.go:21-53`）。
- CI 的 code-health 用现克隆的 infra main 上的脚本和基线（`task-code-health.yaml:54`）。
- 实测 10-17～10-24：`bifrost-ci-platform` 146 次，成功 128 次。成功的中位耗时 6.3 分钟，p90 8.3 分钟。

### 1.5 凭证与身份

- **STG 和 PROD 的平台身份都能读 `cicd/gitea-bootstrap`**：`k8s/platform-rbac/10-stg.yaml:137-143`、`20-prod.yaml` 同名绑定、`00-clusterroles.yaml:98-104`。平台代码把里面的 `gitea_admin_token` 当凭证用（`delivery/service.go:1292-1306`）。也就是说，STG 上跑的平台代码今天就能当 Gitea 管理员，包括改分支保护。
- 06 上执行者和 agentd 是同一个系统用户，读不受限（`CUT-agentd-confine-2026-10-19.md:15`）。
- CI 的 TaskRun 没写 `serviceAccountName`，用 cicd 的 default SA（`trigger-trade-ci.yaml:87-92`）。它能不能读 Secret 没查。
- platform-workers 是 1 个副本、Recreate（`k8s/base-platform/manifest.yaml:83-108`）；镜像里没有 git（`k8s/cicd/docker/Dockerfile.platform-api-stg`）。

### 1.6 窗口、发布、STG

**窗口**
- 只有一个 ConfigMap（`delivery/release_window.go:14-19`）。
- 写入时按 `who` 认持有者（`window_store.go:155-163`）。
- 删除不带 resourceVersion 前提；读到过期的窗口会顺手删掉（`:183-211`）。
- PROD 对这一个 ConfigMap 有 delete 权限（`k8s/platform-rbac/45-release-window.yaml:4-23`），STG 没有。

**发布**
- `bifrost-deliver-platform` 的 `revision`、`uiRevision` 默认都是 `main`（`pipeline-deliver-platform.yaml:15-23`）；接口接受 `main`（`delivery/run_spec.go:25-42`）。
- 带操作号起的 run 名是确定的，已存在就报「已存在」、不重建（`delivery/service.go:282-285`、`:332-363`，`actions.CreateAttemptFrom`）。
- `Sources.Deployed("stg")` 读 platform 车道的提交号，并核对 api、workers、console 三个工作负载的镜像摘要（`server/agentrt_sources.go:20-34`、`:87-98`、`:186-218`）。

**STG**
- 发布会先用新 api 镜像、以 `agentrt_owner_stg` 身份跑库迁移（`task-agentrt-migrate-stg.yaml:1-10`、`:99-120`）。
- 现行 STG 发版规则见工作区 `CLAUDE.md:220-224`。

### 1.7 规则与历史结果

- 常备授权只许 `none`、`branch`（`rules/rules.go:81`、`agentrt-rules/prod/standing-envelope-dev.yaml:1-12`）。
- 收紧的判断不信规则自己声明的方向，而是逐项比较（`rules/tighten.go:16-23`）。
- 「问题的回答不是批准」（工作区 `CLAUDE.md:230-231`）。
- 收下、没进 main、也没标 `no_merge` 的：PROD 10 件（M-1、M-2、M-3、M-4、M-13、M-15），STG 10 件（M-2、M-16、M-23、M-24、M-26、M-27、M-103、M-114 等），合计 20 件，就是 4.6 切法 D-L5 说的那 20 条。

---

## 2. 设计

### 2.0 前置条件 P0：STG 拿不到、也间接用不到 main 的写权限（A1，TD-432）

**要做的**
- 删掉 STG 的 RoleBinding `bifrost-platform-gitea-creds-stg`。
- 平台对 Gitea 的读（列分支、读 main、读文件、比对提交）改用一个**只读** Gitea 用户的令牌，每个环境一份 Secret。
- PROD 也一起换成只读，不再读 `gitea-bootstrap`；管理员令牌只留给 Owner 的脚本。
- STG 演练用的写身份另设：只有两个仓库的代码写权限，不进 main 和标签的名单。

**验收**（S0 全部过了才开 S2）：
1. 以 STG 的 `bifrost-platform` SA 做 SubjectAccessReview：get `cicd/gitea-bootstrap` 回 no；PROD 同样回 no。
2. 用 STG 的只读令牌和演练令牌各跑一次 `check-step1.sh` 式的探针：推 main、建标签、改分支保护、合 PR 进 main 都被拒；读成功。
3. 06 上执行任务和评审任务用的 agentd 身份照旧跑 probe-protection：推 main、建标签被拒。06 上没有落地令牌、管理员令牌、STG 演练令牌（按文件名和环境变量名核对，不读内容）。
4. cicd 的 default SA（CI 跑执行者写的测试用它）get secrets 回 no。

**只有它能拦住的用例**：STG 上的平台代码调用 Gitea 的分支保护接口，回 401/403，而不是像今天这样能改。

### 2.1 谁执行合入（X1）

| | A. PROD platform-workers 的控制器 | B. 06 上的 agentd | C. Tekton 流水线 |
|---|---|---|---|
| 令牌放哪 | `bifrost-platform-prod/agentrt-lander`，以文件挂进 workers | agentd 家目录 | `cicd/agentrt-lander` |
| 执行者写的代码能不能碰到令牌 | 不能：这个 Pod 里只跑发布单批过的 PROD 代码（前提是 P0） | **能读**（§1.5） | cicd 里能建 Pod 的都能挂它；CI 也在 cicd 跑执行者写的测试 |
| 离线时 | workers 停就不合；操作记在库里，恢复后对账 | 06 停就不合 | Tekton 停就不合 |
| 改动面 | 平台代码、镜像加 git、一个 Secret | agentd 加一种新活；要么接受执行者可读，要么在 06 另起一个系统用户 | 两条流水线（Owner 应用），状态分在两处 |

**推荐 A**，并在 workers 里守住这几条：
- 每次操作用新克隆的干净目录，remote 固定。
- 关掉一切会执行仓库内容的入口：`core.hooksPath=/dev/null`、`GIT_CONFIG_NOSYSTEM=1`、`GIT_CONFIG_GLOBAL=/dev/null`；协议只放 http；不读 `.gitattributes` 里的 filter，不读 `.gitmodules`。
- 令牌经单个 git 子进程的 `http.extraHeader` 环境变量给，不进命令行。
- **这个进程里不跑候选的任何代码和测试**，测试都在 CI 里跑。

agentd 现有的 `isolatedGit`（`workspace.go:389-392`）只挡全局和系统配置，不能当完整的沙箱照搬。

### 2.2 资格：哪些结果会被自动落地；旧的 20 件（A3、534 B1，与 D-L5 对齐）

**同一个资格判定 `eligible()`**，在领取（§2.5 第 1 步）、推 main 前（第 6 步）、发 STG 前（§2.8）三处共用。它绑定这些东西：环境；mission 及其 scope 的版本；任务；收下的那次尝试和提交号；计划节点及其版本。

一件 implement 任务要**同时满足**以下全部条件：

1. 由 **PROD** 运行时收下（STG 只演练）。
2. 收下时间不早于这个仓库的**启用时刻**。启用时刻 = 第一次有一版 `landing` 规则列进这个仓库、并且生效的那一刻。它记成一条 `landing_enabled{repo, rule_version, at}`，只写一次；规则换版、收紧、续期都不移动它（A3）。
3. 所属 mission 创建于启用时刻之后，状态是 active，没有 `no_merge`。
4. **计划和 mission 仍要这件活**：
   - 任务绑着计划节点时，节点状态是 planned、active 或 done，不是 dropped 或 stopped；
   - 任务不在计划上（目标拆出来的任务）时，产生它的计划任务仍是这个 mission 最后一次被采用的计划；
   - 任务本身没被取消，也没被另一个落地任务替代（S4 起，§2.7）。
5. 是「任务 base 上的一个提交」。
6. **main 上从来没有过它**：main 历史上没有任何提交带它的 `Agentrt-Task` 或收下的那个 `Change-Id`，包括「曾落地后被撤销」的（照 `merge_accepted.py` 的 `landed()`，不丢撤销的理由）。有过就不自动合，开问题，要一个新的明确决定。没有 `landed` note 不等于从未落地。
7. 没有终结的落地记录，例如 `declined`。
8. 依赖都已有效落地（§2.7）。

**顺序**：第二道闸（§2.5 第 6 步）在一个事务里，以 FOR SHARE 锁住 mission 行和计划节点后判定，并写 `landing_main_intent`。计划变更改节点时要 UPDATE 同一行，所以两者有先后：
- 在这之前提交的变更（撤步骤、加 `no_merge`、叫停 mission），挡住推送；
- 在这之后的，按「已落地」处理，要撤就走 §2.9。

**旧的 20 件**，两道互不依赖的防线：
- 上面第 2、3 条已经把它们全部排除，D-L5 没做也碰不到它们。
- 照 D-L5（4.6 切法），按 mission 逐项确认属于演练或明确放弃之后，由 Owner 在 Console 批单标 `no_merge`（写库是 Owner 的事），之后 agentd 24 小时内删分支。

`no_merge` 用来解释和清理；不靠它兜住全部历史。`merge_accepted.py list` 届时应只剩 0 件。

### 2.3 规则 `landing:<租户>`：可判定的契约（A2、A3、B3）

第一片的第 1 版：

```yaml
rule_id: landing:dev
rule_version: 1
direction: initial                 # Owner 签
effective_at: <签名当天>T00:00:00Z
expires_at: <生效后 30 天>          # 授权期限，不是验证结论
tenant: dev                        # 租户，不是环境：只有 PROD 控制器凭它推 main
repos:
  - repo: bifrost-platform
    allow: ["console/src/components/**/*.tsx", "console/src/components/**/*.css",
            "console/src/pages/**/*.tsx", "console/src/styles/**/*.css"]
    deny: []                       # 只能在底线之上再加
    stg_release: bifrost-deliver-platform   # 或 none
limits:                            # 按租户、UTC 日
  max_files: 10
  max_changed_lines: 300
  max_landings_per_day: 5
  max_in_flight_per_repo: 1
```

**路径语义**
- 从仓库根锚定，区分大小写，分隔符 `/`；`*` 不跨 `/`，`**` 匹配零到多层。
- 改名的新旧路径都要过；删除也算改动。
- 一律拒绝：符号链接（120000）、子模块（160000）、只改模式位、二进制文件（numstat 给 `-`，不按 0 行算）。
- 行数 = 增加 + 删除。

**纯展示的判定**：改到的文件全在 `allow` 里；新增的行不出现指向 `api/`、`lib/`、`hooks/` 的 `import … from`；新增的行不含 `fetch(`、`XMLHttpRequest`、`useQuery`、`useMutation`、`window.location`。这是字符串规则，可判定。语义上算不算「纯展示」仍由评审把关，剩余风险写在 §5。

**硬底线**：写在代码里。规则写什么都放不开，决定卡和例外审批也放不开（A2）。

- platform：
  - `api/cmd/**`、`api/internal/{server,actuation,releasepolicy,delivery,agentrt,agentd}/**`；
  - 迁移和迁移执行器；
  - 任意深度的 `go.mod`、`go.sum`、`package.json`、`package-lock.json`；
  - `console/{vite.config.*,tsconfig*,index.html}`、`console/src/{main.tsx,App.tsx}`、`console/src/{api,lib,hooks,pwa}/**`；
  - `mcp/**`、`agent/**`、`scripts/**`、`config/**`、`Makefile`、`.husky/**`；
  - 任意深度的 `.env*`。

  理由：这些是信任边界、授权、发布、迁移、依赖、构建入口。迁移这一条尤其要紧：STG 发布会用新镜像、以 `agentrt_owner_stg` 跑迁移（§1.6）。
- infra（S6 才用）：
  - `k8s/**`、`agent-config/**`、`scripts/{release,gitea,agent-host}/**`、`scripts/agentrt/rule.sh`、任意深度的 `.env*`；
  - 加一条测试：`allow` 里的每个目录，在 `k8s/`、`agent-config/` 和其他脚本里都没被按路径或模块名引用，有引用就失败。

**碰底线怎么办**：直接拒，开落地问题，写明碰了哪条，以及正规入口：统筹线程或人手经 `push-main.sh`，按现有发布与治理规则。不出「合」的选项。

**软上限**（`limits` 和规则里的 `deny`）：第 1 版**没有例外机制**（X7），超了就开落地问题。以后要例外，用独立的 C 级审批单，绑定仓库、收下的提交号、最终候选号、规则版本、例外项和有效期；候选一变就失效。问题卡的回答不算批准（§1.7）。

**计数**
- 按租户、UTC 日计。
- 只数「推 main 已发出」的操作，成功和结果不明都算。
- 同一操作重试只算一次；演练永不计数。
- 在推 main 前的加锁决策里扣（§2.5 第 6 步）。

**收紧与放宽**：接 `rules/tighten.go`。
- 算收紧的：仓库只减，`allow` 只删条目，`deny` 只增，上限只降，`stg_release` 只改到 `none`，到期只提前。
- 别的都算放宽，要签。
- **停合的开关就是收紧**：去掉仓库不用签名，下一轮就生效。

**续期、换版、过期**
- 在途操作记下领取时的规则版本；换版后在三道闸按新版重判。
- 不再被允许的转成 `parked{rule}`：不退回、不丢，恢复允许后接着走。
- 过期只停新的领取和推送。已经发生的外部动作照常对账：确认落地、删分支、核对 STG。

**按仓库分批发写权限**
- platform main 的推送名单在 S3 发，infra 的在 S6 发。S3 时落地身份对 infra 连代码写权限都没有。
- 标签规则 `*` 只放 `maintainers`，S3 前在两个仓库的页面上核对。

**泄露怎么办**：令牌本身的能力是「有代码写权限、能快进 main」。路径、CI、额度的限制都在控制器里，不是令牌的限制。泄露后：
1. Owner 先把这个用户移出推送名单，再换令牌；
2. 按 Gitea 的推送记录，核查泄露期间这个用户的**全部** ref 和权限变更（任意代码、删文件、非保护分支）。

Gitea 走集群内 HTTP，没有 TLS。在集群内抓包要有节点或网络权限，这一点接受，写在这里。

### 2.4 操作协议（A10；X3：用事件，不建表）

**操作号**：落地是 `land:<任务>:<k>`，`k` 是这件第几次重放；发 STG 是 `stg:<仓库>:<n>`。

**记在哪**：流 `landing:<仓库>` 上，带 `task_id`、`mission_id`。Append 时持流锁，按仓库串行领取就靠它。另在 mission 流上镜像一条摘要给 Console。

**事件类型是封闭的一组**，只改 `store/vocab.go`，不改库：
`landing_enabled`、`landing_claimed`、`landing_prepared{R, M0, dates}`、`landing_branch_intent`、`landing_branch_pushed`、`landing_ci{run, status}`、`landing_main_intent`、`landing_main_result{ok|non_ff|denied|unknown}`、`landing_landed{R}`、`landing_parked{why, retry_at}`、`landing_failed{why}`、`landing_reverted`、`stg_pending`、`stg_intent`、`stg_started{run}`、`stg_verified{P, U, digests}`、`stg_failed`。

- 每种事件的字段固定，`why` 的取值有限。
- `dry_run` 是 `landing_prepared` 上的一个布尔字段，不是一个阶段。带它的操作永不写 `landing_landed`，也不进任何统计（C2）。
- 一个纯函数把这些事件折叠成每个操作的状态。

**外部动作一律先记意图、再动手；结果不明时先查、不重做**：

- **R 可重建**：作者时间取原提交的，提交者时间取 `landing_prepared` 里记的，提交信息是确定的。所以重启后重建出来的还是同一个 SHA。
- **推落地分支**：先记 `landing_branch_intent`。重启后 `ls-remote` 看分支：
  - 等于 R → 补记 `landing_branch_pushed`；
  - 不存在 → 重建同一个 R 再推；
  - 是别的提交 → 不认它，`k+1`，旧分支按 SHA 条件删。
- **推 main**：先记 `landing_main_intent`。结果不明或重启后，判断 R 是不是当前 main 头的祖先、且没被 revert（复用 `lineage.MainResults` 的认法）：是就记 `landing_landed`。不要求 main 头正好是 R，所以人手紧接着推了后继，也不会误判。
- **起 STG 发布**：带着操作号起，run 名就是确定的（§1.6）。报「已存在」就接管那个 run。
- **删分支**：带 SHA 前提（`--force-with-lease=<ref>:<R>` 删除），只删自己推的那个提交。

`RecordLandings` 照旧当兜底，但它只补 `landed`。发布、额度、退回、分支清理的恢复都靠这套协议。

**测试**：每个「外部已成功、记录还没写」的断点一个用例，共六个——推了落地分支、CI 已起、推了 main、建了 STG run、STG run 已结束、删了分支。每个断点都重启一次，验证不重复、不误退回。

### 2.5 合入步骤（PROD；每个仓库同时最多一件「活动」）

1. **领取**：`eligible()` 为真的，按收下时间排，在流锁下写 `landing_claimed`。`parked` 的不占活动位（A6）。
2. **第一道闸**：先跑 `eligible()`，再按当前规则完整判定：路径、底线、纯展示规则、上限、`stg_release`、规则是否过期。
   - 碰底线：开落地问题；
   - 计划或 mission 不再要它：写 `landing_failed{stale}`，开问题；
   - 规则变了：`parked{rule}`。
3. **重放**：取 main 头 `M0`，在干净目录里 cherry-pick，写 `landing_prepared`。冲突或 patch-id 变了就是失败（§2.7）。
   - **评审只对原提交 A 有效**（B1）：
     - `M0` 等于 base：R 的树和 A 相同，评审结论成立。
     - `M0` 不等于 base，且 base..M0 改过的文件和 A 改的文件有交集：第一片当失败处理；以后见 X6。
     - 没有交集：接受「原补丁评审 + R 上的完整 CI」的剩余语义风险，写进 §5 由 Owner 接受。复核 533 的探针证明，patch-id 相同时语义仍可能变。
   - **提交信息**（C3）：保留原正文。来源段写「Landed by the agent runtime (PROD) under landing:dev v<N>: mission …, task …, attempt …, reviewed by …, accepted …, replayed onto <M0> as <操作号>」。`Work`、`Change-Id`、`Agentrt-Task` 原样保留，**不加 TD-383**。加 `Landed-By: agentrt-prod/<操作号>` 和 cherry-pick 行。
4. **推落地分支**：推到 `land/prod/<任务>/<k>`，按 §2.4 的意图协议。
5. **等 CI**。每一轮先查 main 头、规则和 `eligible()`。main 已不是 `M0` 就丢掉这个候选（`k+1`，回第 3 步），不管 CI 到了哪一步（A6）。按 CI 状态分开处理：
   - **Missing**：10 分钟后按操作号建一次 run，一次性标记写进事件；
   - **Unknown**（读失败）：重读，不当成任何结论；
   - **Running**：超过 30 分钟就 `parked{ci_stuck}` 并开问题；
   - **Succeeded**：必须是这个 R、在 `landing_prepared` 之后建的、最新一次 run 成功。「曾有一次成功」不够（B4）；
   - **Failed**：看 `M0` 自己最新一次 CI——
     - `M0` 成功：按操作号重跑一次（一次性），还红就是失败；
     - `M0` 失败：`parked{main_red}`，每轮复查；main 一动就丢掉候选、重放；
     - `M0` 的 CI 是 Missing、Running 或 Unknown：只等，不判成 main 红。
   - **上限**：一个根任务的操作，从第一次领取起最长 6 小时、最多重放 8 次；到了就写 `landing_failed{bound}` 并开问题。
6. **第二道闸**：一次加锁的决策（锁法见 §2.2「顺序」），依次做完以下几件：
   - 重跑 `eligible()` 和第 2 步的全部规则判定。CI 期间加了 deny、缩了 allow、改了 `stg_release`、加了 `no_merge`、撤了步骤、mission 被叫停，都在这里拦下；
   - 扣当天额度；
   - 确认 main 头仍是 `M0`；
   - 确认窗口不挡（§2.6）；
   - 写 `landing_main_intent`。
7. **推 main**：`git push origin R:refs/heads/main`，不带 force。
   - `ok`：按 §2.4 确认后写 `landing_landed`；
   - `non_ff`：回第 3 步；
   - `denied`：停这个仓库的落地，开问题；
   - `unknown`：按 §2.4 对账。
8. **收尾**：按 SHA 删落地分支，写 `stg_pending`（§2.8）。

### 2.6 和人手抢 main；窗口接口（A9、C1）

**抢 main**：两边都只快进，Gitea 不许强推 main，抢输的一方只会被拒。
- **D2（4.3）上线之前**：不持窗口，抢输就重放，受第 5 步的上限约束。
- **D2 上线之后**：连续抢输两次，第三次从重放到推 main 都持应用车道。

**窗口接口**，现在就按 4.3 的租约来约定（`DESIGN-release-lanes-2026-10-24.md` §2.2、§2.4）：
- `Acquire(op, repo, targetSHA, paths)`：拿到返回 `lease{token, expires}`；被占返回 `held{who, op, run, eta}`。
- `Check(repo, paths, selfToken)`：只回答挡不挡；自己持的不挡自己。
- `Renew(lease)`、`Release(lease)`。

**第一版接今天那一个 ConfigMap**：
- `who` 写 `agentrt-prod/<操作号>`。每次操作不同，所以重启后的新操作和旧发布不会被当成同一个持有者。
- 释放用带 resourceVersion 前提的 Update，把 `expires_at` 设成现在；不用无前提的 Delete（§1.6）。
- 读窗口失败一律当作「挡」。
- 重启后，先找自己操作号名下在跑的 run，接管了再决定要不要新建。
- 等窗口最多 30 分钟，之后 `parked{window}`，按 TD-267 当作暂时性拒绝重试，上限 24 小时。这和 4.3 §2.4 一致。

**TOCTOU**：第 6 步读窗口和第 7 步推送之间有几秒，两次读取不构成互斥。
- 运行时起的 STG 发布一律钉提交号（§2.8），推 main 改变不了它在构建什么。
- 人手用 `main` 起的发布，仍可能撞上这几秒。

严格互斥要等 4.3 给推 main 的入口加共用的最终判定（4.3 §2.3 第 3 条）。这几秒的风险写进 §5，请 Owner 接受。

### 2.7 失败怎么办（A4、A5；X2）

**第一片（S3）只开问题，不自动修。**

- 冲突、patch-id 变了、改动有交集、CI 红、超上限、碰底线、权限被拒、活已过时，都写 `landing_failed{why}`。
- 按根任务开**一个**落地问题：用现有 issues，去重键 `landing:<根任务>`。问题里带证据：
  - 冲突的文件；
  - 两个 patch-id；
  - run 名和最后 40 行（按现有的脱敏）；
  - 碰到的底线条目。
- 收下的任务状态不动，不调 `failWork`，不计进执行者的成绩。CI 坏了、抢 main 输了，都不是执行者的错。
- 问题上有两个动作：「再试一次」（重新领取一次）和「不合」（写 `landing_failed{declined}`）。
- 算「已了结」的只有三种：「不合」、撤销规则、活已过时。

**S4 才做自动修（R3）**，要先补齐五样：

- **替代关系**：根 → 当前替代 → 有效结果。落地任务由控制器建，同一事务里写 `landing_replaces{root, follow_up}`。依赖、关闭、分支清理都按「根的有效结果」判，不伪造「原提交已进 main」。
- **原子、幂等**：建替代任务、写替代关系、保持 mission active，在同一事务里完成，以操作号去重。
- **关闭条件**：落地范围内每个根都满足其一——
  - 已有效落地（`stg_release` 不是 `none` 时，还要已上 STG）；
  - `declined`；
  - 已过时；
  - mission 本来就 `no_merge`。
- **规则撤销后的根**：`parked{rule}`，mission 保持开着，并挂一个问题。
- **第三次失败**：开一张可操作的卡，不碰 `accepted` 任务的状态。

S4 的验收用例：
- A→B 依赖链：A 冲突，A′ 落地之后 B 才落地；
- 两层退回；
- 「不合」之后 mission 能关；
- 关闭循环和建替代任务并发跑 1000 次，没有一次提前关掉 mission；
- 连续三次失败只出一张卡。

### 2.8 发 STG（A7、A8）

**待发布记录**：每个仓库一条 `stg_pending{R…}`，记录已落地、还没核到 STG 的最高提交。它有自己的状态，不靠新的落地唤醒。

**什么时候发**：这个仓库没有活动的落地，或者最老的待发布已等了 20 分钟，取先到者。持续有新活也压不住已落地的工作。

**怎么发**
1. 用 §2.6 的接口持窗口，操作号 `stg:<仓库>:<n>`。
2. 持到窗口之后定快照：
   - platform 提交 P = 此刻 main 的头，必须包含全部待发布的 R；
   - ui 提交 U = P 那次成功 CI 实际用的 ui。CI 是否记下了 ui 提交号，没核实；没有就在 S0 给 ci-platform 的克隆步骤加一个结果。
3. 发前检查：
   - P 的最新一次 ci-platform run 成功，且用的就是 U；
   - **对整个发布差异判权限**：从上一条 STG 发布记录到 P，改到的每个文件都过 §2.3 的 `allow` 和底线。批里夹着人手提交的迁移之类的，不自动发，开问题「STG 要人发：差异含 X」；
   - 每个待发布 R 的任务 `eligible()` 仍为真，`stg_release` 仍开着，这个仓库没有 `denied` 停合。
4. 起 `bifrost-deliver-platform`，`revision=P`、`uiRevision=U`，都是完整 SHA，带操作号。
5. 核对：
   - run 成功，克隆结果的提交头就是 P；
   - `Deployed("stg")` 等于 P，三个工作负载的镜像摘要都对；
   - 平台的 STG 健康检查正常（MCP 有 `get_stg_smoke`，实现没读）。
6. 逐个确认待发布的 R **在 P 里仍有效**，即没被 revert（A11），写 `stg_verified`；最后放窗口。

**失败**：同一个快照退避重试两次（10 分钟、30 分钟），还不行就写 `stg_failed` 并开问题。待发布照旧显示。main 不回退，往前修。

**mission 的完成**：`stg_release` 开着时，mission 要等它的结果全部 `stg_verified` 才算完成。Console 上「已合入」和「已上 STG」分两列显示，不把前者显示成后者。

### 2.9 被撤销的落地、坏落地怎么救（A11）

- 「曾经落地」是历史事实，保留。
- 每轮按 `lineage.MainResults` 的 revert 认法（复用 `merge_accepted.py:342-363` 的规则）看结果当前还在不在，不在就写 `landing_reverted`。
- 依赖、STG 核对、「已上 STG」都按「当前仍有效」判，不按祖先关系判。
- 已 revert 的成果要重新落地，必须有新的明确决定（§2.2 第 6 条）。

**坏落地的操作手册**：
1. 收紧规则，去掉这个仓库，停掉后续的落地和发布。
2. 在最新的 main 上，经 `push-main.sh` 提交受检的 revert 或修复。
3. 按固定 SHA 重发 STG：运行时会自己发；运行时坏了，由人按现有入口发。
4. **禁止 reset 和强推 main。** PROD 照原审批政策。

### 2.10 代码健康、`push-main.sh` 门槛的逐项替代（B4）

| 现有门槛 | 落地怎么做 | 是否等价 |
|---|---|---|
| 只快进、不强推 | 保留；分清 `non_ff`、`denied`、`unknown` | 等价 |
| `Change-Id` + `Claude-Session` | 要求 `Agentrt-Task` 恰好等于收下的任务，`Change-Id` 恰好一个 | 替代；S7 让 `push-main.sh` 也认它 |
| 确切提交的 CI | 要最新一次、在候选生成之后建的 run；CI 之后不 amend、不 rebase；run 名和所用的 infra 提交进审计 | 更严 |
| code-health | ci-platform 里本来就有；TD-387 在验收阶段提前反馈 | 等价；基线以 run 所用的 infra 提交为准 |
| `go vet ./...` | CI 里没有。S0 把完整的 vet 加进 ci-platform | 补上后等价 |
| infra 快测 | S6 的 `bifrost-ci-infra` 用同一份清单（push-main 的 release、agentrt、agent-host，加运行时检查），清单只放一处 | S6 之前不合 infra |
| 窗口 | 读失败就挡；检查不等于持锁（§2.6） | 等价，TOCTOU 写明 |

### 2.11 分支去留

- `land/<环境>/<任务>/<k>`：落地或失败后按 SHA 条件删。`prune.go` 加一条兜底：超过 24 小时、又没有活动操作的 `land/` 分支也删。今天的正则不认这类分支（`prune.go:58`）。
- `agent/<任务>/a<n>`：规则不变。被替代的根，它收下的那个尝试分支，等有效结果落地后再起算 24 小时。
- 工作目录用完即删，口径和 4.6 对齐。

### 2.12 Owner 看到什么，「统筹线程零写入」怎么量（B5）

**Console 每件任务**显示：
- 根任务；
- 原提交 A、base、最终落地的 R、`M0`；
- 规则版本（以后还有例外单）；
- CI run；
- 退回链；
- 待发布、发布的 run、P、U、镜像摘要；
- 发布失败、已撤销；
- 下一次重试的时间。

**主动提醒**：任何操作 `parked` 超过 2 小时，或待发布超过 1 小时，就开运行时问题（统筹线程看）。只有要 Owner 动手时才进 For you。

**★ 怎么量**：取一个明确的 mission，看它的完整事件链，七个环节都要有记录：
1. Owner 在 Console 输入目标；
2. 提案和授权；
3. 实现、检查、评审；
4. 落地操作，以及 Gitea 上记录的推送者；
5. CI；
6. STG 的 run 和实际镜像摘要；
7. 这段时间里统筹线程的全部写动作，下面每一类都应为 0：
   - actor 为 `thread:…` 的事件；
   - 平台审计里该会话发起的动作；
   - `bifrost-mbp` 往两个仓库的推送；
   - 手工建的 PipelineRun；
   - 审批和问题上的操作。

**「运行时自己合的占比」**：数 Gitea 推送者是落地身份、且有对应 `landing_landed` 的 main 提交。不只数 `Landed-By`，那个尾注谁都能写。能不能从 Gitea 拿到推送者，在 S0 实测。

### 2.13 与 `RecordLandings`、`merge_accepted.py`

- `RecordLandings` 不改。它跳过已有 `landed` 的，只给人手合的补记，并兜底「推了 main、还没来得及记」的情形。
- `merge_accepted.py list` 当审计用：规则覆盖的仓库里，收下超过 2 小时、既没有活动操作也没有终结记录的，就是落地循环出了毛病。
- `apply` 留给规则之外的活。`plan` 丢掉「曾落地后被撤销」理由的问题（§1.2），在 S7 一起改。

### 2.14 失败模式（摘要；处理见各节）

| 情形 | 结果 |
|---|---|
| 冲突 / patch-id 变了 / 改动有交集 / CI 红 | 开落地问题（S3）；S4 起自动修 |
| 计划步骤被撤、加了 `no_merge`、mission 被叫停（在第二道闸之前） | `landing_failed{stale}`，不推 |
| main 上曾有过它（含已撤销），但还没有 `landed` note | 不推，开问题等新的明确决定 |
| `M0` 的 CI 红 | `parked{main_red}`；main 一动就重放 |
| CI 没起 / 读不到 / 卡住 | 补建一次 run / 重读 / 30 分钟后 parked 并开问题 |
| main 在 CI 期间动了，或推送 `non_ff` | 丢掉候选重放；受 6 小时、8 次上限约束 |
| 推送 `denied` | 停这个仓库的落地，开问题 |
| CI 期间规则被收紧或过期 | 第二道闸拦下，`parked{rule}` |
| 碰底线 | 拒，开问题；不出「合」选项 |
| 推 main 后重启，人手又推了后继 | 按「仍有效的祖先」认成已落地 |
| STG run 建了但结果不明 | 按确定的 run 名接管 |
| STG 发布失败 | 同一快照重试两次，之后开问题；mission 不算完成 |
| 已落地又被 revert | 写 `landing_reverted`，不报「已上 STG」 |
| 落地令牌泄露 | 先移出推送名单、再换令牌，核查泄露期间的全部推送 |
| 规则启用前收下的、属于旧 mission 的 | 永不自动合；D-L5 另外按 mission 确认后标 `no_merge` |

---

## 3. 切片

| 片 | 做什么 | 只有它能拦住的用例（对应复核条目） | 要 Owner |
|---|---|---|---|
| **S0 前置** | P0（TD-432）；ci-platform 加 `go vet ./...` 并记下 ui 提交号；实测 Gitea 能否给出推送者；D-L5 | ① STG SA 读 `gitea-bootstrap` 回 no；STG 平台代码改分支保护回 401/403（A1）② 只有 vet 能抓的错误（自赋值）让 ci-platform 变红（B4） | 应用 RBAC 改动；建只读用户和 STG 演练用户、Secret；应用 Tekton 改动；批 D-L5 的单 |
| **S1 规则与资格（不碰 git）** | `landing:<租户>` 的解析和收紧判断；底线；路径和纯展示规则；`eligible()`；§2.4 的词表和折叠函数 | ① 规则写了 `api/internal/server/**` 也被底线拒，且不出「合」（A2）② 换版不移动启用时刻，上一版下收下的仍在队里（A3）③ 改名的旧路径碰底线、符号链接、二进制 → 拒（B3）④ 启用前收下的、`no_merge` 的 → 不进队 ⑤ 带 `dry_run` 的不计数、不写 `landed`（C2）⑥ **规则生效后收下、再被 `drop_step` 撤掉步骤的任务 → `eligible()` 为假**（534 B1） | 无 |
| **S2 STG 演练** | git 卫生；可重建的 R；推 `land/stg/**`；分状态等 CI；六个断点的恢复；STG 上不推 main | ① 旧 main 永红、新 main 已绿 → 丢掉候选，在新 main 上重放（A6）② CI 为 Missing 时只补建一次；Unknown 不当成 main 红（A6）③ 推了落地分支、还没记录就重启 → 重建出同一个 SHA（A10）④ base..M0 与 A 有交集 → 开问题（B1） | 镜像加 git（刷新 Dockerfile 的 ConfigMap）；STG 演练令牌的 Secret |
| **S3 PROD 第一片（B6）** | 第 1 版规则：只开放 Console 文案和纯展示组件、一件在途；推 main；落地问题；固定 SHA 的 STG 发布和待发布记录；窗口适配；撤销的认定 | ① CI 期间收紧 `deny` → 不推（A3）② **CI 期间给 mission 加 `no_merge`，或撤掉它的计划步骤 → 不推**（534 B1）③ **人手合进去又 revert 了，`RecordLandings` 还没记 → 不推**（534 B1）④ 第三次失败只出一个问题，任务状态不变（A4）⑤ 等窗口期间有人推了 N → 发的是 P 不是 N；差异含人手迁移 → 不自动发（A7）⑥ STG 发布失败 → 重试、开问题，mission 不算完成（A8）⑦ 重启后接管在跑的 run，不建第二个；释放不会删掉别人刚续好的窗口（A9）⑧ 推 main 成功后人手推了后继 → 记已落地、不重放（A10）⑨ 已 revert 的 R 不报「已上 STG」（A11）⑩ 落地身份推 infra main、建标签都被拒 | **签 `landing:dev` 第 1 版**；建 `agentrt-lander`，只加进 platform main 的推送名单，令牌做成 PROD 的 Secret；核对标签规则；**批发布单** |
| **★ 验收** | Owner 在 Console 提一句改 Console 文案的小目标，到进 main、上 STG；按 §2.12 的七项量，统筹线程零写入 | — | 提目标 |
| **S4 自动修（R3）** | §2.7 的替代关系、原子创建、关闭条件、可操作的卡 | §2.7 的五个用例（A5） | 批发布单 |
| **S5 放宽到 platform 非核心代码** | 第 2 版规则（放宽，要签）；X6 选定的评审方式 | 改动有交集时按 X6 处理；底线照旧拦 | 签第 2 版 |
| **S6 infra** | `bifrost-ci-infra` 全套接线：触发器、`isCIPipeline`、CI 索引、`push-main.sh` 的 `CI_REPOS` 和 `ci_gate`；infra 的 `allow` 和引用测试 | ① 碰 `k8s/**`、`agent-config/**` 的永不自动合 ② `allow` 里的目录被 Tekton 任务间接引用 → 测试先红（B2、B3） | 应用流水线；签第 3 版；加进 infra main 的推送名单 |
| **S7** | `push-main.sh` 认 `Agentrt-Task`（恰好等于收下的任务）；按推送者数的占比脚本；`merge_accepted.py plan` 不丢「曾落地后被撤销」；运行时自建 PROD 审批单（可并进 4.3） | 尾注是伪造的提交不进占比 | 无 |

粗估：S0–S3 加 ★，约 5–6 个工作日的实现加复核；Owner 约 2 小时，分 4 次。把握低：S0 的 TD-432 要改平台读 Gitea 的路径，工作量没细估。

---

## 4. 架构级选择

| # | 选项 | 推荐 |
|---|---|---|
| X1 谁执行 | A workers 控制器 / B agentd / C Tekton | **A**，前提 P0 |
| X2 第一片的失败 | 只开问题，S4 再做 R3 / 现在就做 R3 / 加 `landing` 任务状态（PROD DDL） | **只开问题，S4 做 R3** |
| X3 状态记在哪 | 流 `landing:<仓库>` 上的封闭事件 / 新表 `agentrt.landing`（PROD DDL） | **事件** |
| X4 STG 怎么演练 | 只推 `land/stg/**` / 用探针仓库真推（要等 4.2） | **只推 `land/stg/**`**；真推 main 的正反测试放 S3、用真身份 |
| X5 infra 的 CI | 新建 `bifrost-ci-infra` 并全套接线 / 在 06 上对 R 跑运行时检查（更弱） | **新建** |
| X6 base 漂移后的评审（B1） | M0≠base 就加一次集成复核 / 接受「原补丁评审 + R 上完整 CI」的剩余风险，有改动交集的不合 | **第一片取后者**；S5 起有交集的加集成复核 |
| X7 软上限的例外 | 第 1 版不设 / 独立的 C 级单，绑定 SHA 和规则版本 | **第 1 版不设** |

---

## 5. 待 Owner 定的点

| # | 定什么 | 推荐 | 在哪办、怎么回 |
|---|---|---|---|
| 1 | X1–X7 | 见 §4 | 统筹线程；回「4.1 第 2 稿照推荐」或逐条写字母 |
| 2 | P0 / TD-432：撤掉 STG（及 PROD）对 `gitea-bootstrap` 的读取，平台读 Gitea 改用只读身份 | 做，作为 S2 的前置 | 统筹线程出步骤；你应用 RBAC、建用户 |
| 3 | `landing:dev` 第 1 版：`allow` 四条、纯展示的字符串规则、三个上限、30 天到期、`stg_release` 开 | 照 §2.3 | S3 签名时 |
| 4 | 底线清单（代码里写死，规则放不开） | 照 §2.3 | 回「底线照稿」或增删 |
| 5 | 资格判定 `eligible()` 的八条，特别是「计划和 mission 仍要它」「main 上从来没有过它」 | 照 §2.2 | 回「资格照稿」 |
| 6 | 接受的剩余风险：没有改动交集时的语义漂移（B1）；推 main 前几秒的窗口 TOCTOU（§2.6）；「纯展示」只靠字符串规则加评审 | 接受，因为第一片范围小 | 回「剩余风险接受」 |
| 7 | `push-main.sh` 的逐项替代（§2.10），尤其 `Agentrt-Task` 代替 `Claude-Session` | 照表 | 同上 |
| 8 | Owner 看到什么（§2.12）：「已合入」「已上 STG」两列，问题阈值 2 小时 / 1 小时 | 照稿 | 同上 |
| 9 | ★ 怎么量（§2.12 的七项）；占比按推送者数 | 照稿 | 同上 |
| 10 | 旧的 20 件：落地的资格规则本身排除它们；D-L5 按 mission 逐项确认后标 `no_merge`，用于解释和清理 | 两样都做 | D-L5 的单在 Console 批 |
| 11 | 动手的事：S0 应用 RBAC 和 Tekton、建两个 Gitea 用户和 Secret；S3 签第 1 版、建 `agentrt-lander` 并加进 platform main 的名单、核对标签规则、批发布单；S6 再给 infra | — | 到那一片时带具体步骤 |

## 6. 没核实的

- 线上 RoleBinding 是否与清单一致，令牌的 scope，cicd default SA 能不能读 Secret：都放进 S0 的验收实测。
- Gitea 能否按用户给出推送者：S0 实测。
- ci-platform 有没有记下它用的 ui 提交号：没有就在 S0 补。
- 平台 STG 健康检查 `get_stg_smoke` 的实现。
- Gitea 1.21.11 有没有 `fast-forward-only`：推荐方案不依赖它。
- 目标拆出来的任务，「最后一次被采用的计划」的精确判法（`planresult.go` 的 `plan used` 事件）：没读完。S1 实现时补上，判不出就按「已过时」处理。
- 复核 533 的两个探针（patch-id、vet）没有重跑。
