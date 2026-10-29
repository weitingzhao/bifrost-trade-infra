# 统筹提交走落地 · 设计 v3（2026-10-28 23:xx CDT 统筹分叉，收口复核 679）

**依据**：Owner 决定 A（CUT §11.14，不重开）；v2 `DESIGN-coordinator-landing-v2-2026-10-29.md`；复核 677（`~/agent-work/codex-work-677/REPORT.md`）、复核 679（`~/agent-work/codex-work-679/REPORT.md`，7 阻断 / 7 应修 / 3 小问题，本块相关 B-01..B-05、R-01..R-07、N-02）；B5 v3 §5.1、§17.4（O-1 A：D 级单参数带 `stg: true`）；S6 v2（只为对齐接口，S6 v3 另有人写）。

**实读代码**：platform `cb47820d6ceeff3f97c97d56899d2af1bee0372c`（= PROD；检出 `~/agent-work/codex-work-679/platform`）；infra `85f578ed208a6cb6a1b1e153ac5e1e50f6c2eb90`（检出 `~/agent-work/codex-work-679/infra`）。文中 `文件:行` 均指这两个版本。所有路径为 **repo 相对**、无缩写（platform 的 Go 模块根是 `api/`，`go.mod` 在 `api/go.mod`）。

**本稿取代 v2 全文**（v2 及 v1 只留作历史）。设计复核已满两轮（677、679）：本稿把 679 中属于核心的阻断与应修全部定死，实现者不做临场决定；进入实现后**只做代码复核**，不再做设计复核。文中「必须 / 不得」是契约，「建议」是实现自由度。

**一句话**：统筹会话（Claude）的提交以登记过的外部主体身份交成一次尝试，过确定性验收与 Codex 异家评审；只碰规则内路径的照常由 `agentrt-lander` 落地；碰「软底线」的停在 `awaiting_grant`，统筹建 D 级单、Owner 在 ops.bifrost.lan 批准后由落地身份推送；碰「硬底线」（授权与落地自身的信任闭包，§4）的不进本通道，仍由 Owner 手推。

---

## 1. 对 679 的逐条回应

| 679 | 处理（定稿） | 本稿位置 |
|---|---|---|
| **B-01** pin 的提议权限未绑定可认证身份 | 设 pin 只认**服务端登记、独享的提议主体** `seat:coordinator`（独立令牌，令牌名由服务端配置决定，不来自请求头）；线程头 `X-Bifrost-Session` 只记成审计字段 `via_session`。`Relayed` 代写、计划导入、控制器自动生成的任务一律不得带 pin；幂等重放同样只回给同一主体。同一提议主体的全部 pin 任务都可由 coordinator 主机按 id 精确领取，第一版**不做逐线程隔离**（理由 §2.3）。测试含「同共享令牌、换线程头」反例与独立主体成功对照 | §2.1–§2.3、§6 T1–T4 |
| **B-02** 最小可信边界不是自保护闭包 | 改为**包级 hard**：授权来源 → 事件校验/存储 → 身份与接受证据 → 最终闸 → 携凭据执行 → Owner 决策 UI 的 Go 包整目录（递归，新增同包文件、子包均命中），其非测试依赖由 `go list -deps` 机械求闭包并由测试守住；Console 审批/鉴权/构建入口文件逐个列出，另有「决策与凭据调用点必须在 hard 清单内」的扫描测试。完整清单 §4.2。如实承认：hard 之外的同进程代码（任何能拿到 DB 连接或进程内对象的包）**没有机械自保护**，靠异家评审 + Owner 逐件语义审查。近 30 天粗算 75.9% 的 platform 提交碰 hard（§4.4） | §4 |
| **B-03** 规则收紧后 grant 语义矛盾 | 统一一条：消费时按**当时生效规则**重算软失败集合 `soft_now`，必须 `soft_now ⊆ grant.waives`，否则不推、回到等待、需重批；不可豁免项与始终生效项一律按消费时事实。grant 记下批准时的规则身份（id、版本、正文 sha256）与检查版本 `checks_version`；消费记录写下当时的规则身份与 `soft_now`。不提供「冻结旧软政策」模式 | §3.3、§5.5 |
| **B-04** grant ID 进尾注与先固定 R 循环 | **grant/approval 引用一律不进提交**。R 在准备时固定（只含准备时已知的操作号 `Landed-By: agentrt-prod/<op>`，现有 `landinggit/replay.go:114`）；approval/grant 引用只写在落地流：`main_intent` 事件里的 `landing_grant_use` 段、`landing_grant` 记录、Console 与血缘视图。从 CI、建单、批准到 push 参数，R 逐字不变（T36） | §5.1、§5.5、§5.7 |
| **B-05** awaiting 复用按操作编号的分支 | 每一「代」准备就是**一个普通落地操作** `land:<task>:<k>`：独立的 ref `refs/heads/land/prod/<task>/<k>`、M0、R、committer date、CI；协议加阶段 `awaiting_grant`（v1.2），它**不计入在途**（与「有操作记录」拆开）。main 前进只能产生新操作 k+1（旧操作 `discarded{main_changed}`），旧 ref 永不覆盖；准备并发、推分支响应丢失、重启全部沿用现有操作协议的恢复。代数受现有「每根 8 个操作、不因 retry 清零」约束 | §5.2–§5.4 |
| **R-01** 精确领取、幂等与滚动升级 | 精确领取只换**候选来源**，其余判定（主机状态、全局/主机/任务/mission 控制、mission 活跃与租户、standing envelope、并发、预算、冷却、能力、core、独立性、租赁、提交确认）与 `ClaimNext` 共用一份代码。幂等键绑定主体+路由+键+请求指纹；首个响应丢失用同键取回；换 task 同键 409；失租后用新键得新一代。`core` 在 persist 时由服务端读 diff 派生核对。迁移 → 全部读者 → 确认无旧读者 → 才启用 pin；数据库触发器兜底旧读者。词表/actor/回放改动点逐一列出 | §2.4–§2.7、§7.2 |
| **R-02** 72h/6h 与 B3/B4 结束路径 | 给出唯一的计时与转移表：执行时钟（6h，扣除等待区间）、等待累计（72h）、8 个操作上限，同一 retry epoch 内累计；获批即结束当前等待区间；`main_intent` 之后只对账。拒单、过期、撤销、刷新、迟到旧单都按**操作号**精确归属。新原因 `approval_expired` 进 `RetryableReasons`。无单 / 待批 / 过时单三种显示 | §5.3、§5.4、§5.8 |
| **R-03** grant 证据身份、幂等、不确定结果 | 闭合 schema 与两个规范摘要（`candidate_digest` 供消费比对、`material_digest` 供建单/执行比对）的全部输入（含验收、评审、CI 身份、规则与检查版本、候选代）；唯一键：一张审批至多一个 grant，一个操作同时至多一个有效 grant；create / revoke / consume 各给「读回确认成功 / 确认未写 / 仍未知」处理表；审批状态未知不作为撤销事实 | §5.5–§5.7 |
| **R-05**〔两份、B5〕infra grant 集合与 B5 用途 | 第一版 `GrantSupported = {bifrost-platform}`，**infra 不支持 grant**；删掉一切「hard 文件可走普通 D 单」的说法；「不支持仓库的拒绝」与「hard 优先」分开测。B5 只读 `LandingGrantEvidence`（含 `purpose`、`stg_release`），自己的发布消费另记，不复用、不清除落地 grant 的消费 | §3.4、§8 |
| **R-06**〔两份〕新操作的锁序 | 列出 create/revoke/consume、刷新、拒单/过期结算、到限结算、请求观测、B4 Close 的锁表；全局序：能力 → 规则 → 计划步骤 → 任务 → mission → 当日额度流 → 仓库流（多仓按仓库名升序）；PG 事务内不调审批服务 | §5.9 |
| **R-07**〔两份〕负例被更早拒绝遮蔽 | 测试表逐条写：入口、成功对照、只改的一项、预期拒绝层、删掉哪项检查后应变绿；不可从 HTTP 单独命中的标「内层」；补 679 列出的全部新反例 | §6 |
| **N-02**〔两份〕新增/删除的空侧 | 按变更类别定端点：新增查新端、删除查旧端、修改两端同值、改名/复制两端都查；两端皆空或解析失败才是非法空路径；`..` 路径另由路径合法性拒绝 | §3.1 |
| B-06、B-07、R-04、N-01、N-03（S6） | 不在本稿处理。核心侧接口：CI 读取契约（B-07 影响共享接口）在 §3.5 定；`LandingHard` / `GrantSupported` / 端点语义由本稿提供，S6 只往表里加 infra 行 | §3.5、§8 |

677 各项：本稿在 v2 基础上把 679 判「部分」的核心项全部收口；677 B-07、N-01 属 S5，不在本块。

---

## 2. 外部主体与 handin

### 2.1 两个主体，各管一件事

| 主体 | 令牌（服务端 `config/platform-auth.yaml` 登记） | 能做 | 不能做 |
|---|---|---|---|
| **提议主体** `seat:coordinator` | 角色 `reporter`，名 `seat:coordinator`（座位令牌已是提议者，`agentrtapi/reporter.go:13`）；值来自 `token_env: AGENTRT_COORDINATOR_PROPOSER_TOKEN`；本机 `~/.config/bifrost/coordinator-proposer.token`（600） | 提议 mission 与 task；**唯一能设 `executor_pin`** | 领取、交付、建审批 |
| **执行主体** `agentd:coordinator-mbp` | 角色 `agentd`，绑定主机 `coordinator-mbp`（`actuation/auth.go:75`）；本机 `~/.config/bifrost/coordinator-agentd.token`（600） | 只经 `POST /agentrt/claim/pinned` 领 pin 给自己的 implement，随后 attempt 动作、刷新（§5.4） | 通用 `/claim`、领检查任务、提议 |

- 加载配置时新增校验：`seat:` 开头的主体名在 `tokens` 里**唯一**（现只校验令牌值唯一，`actuation/auth.go:199`），重名即启动失败。
- 主体绑定写在 Owner 签名的 standing envelope `standing-envelope:dev` 新段 `external_hosts`（规则 schema 扩展，`api/internal/agentrt/rules/`）：
  ```yaml
  external_hosts:
    - host: coordinator-mbp
      pin: external:coordinator
      proposer: seat:coordinator
      executor: exec:claude       # 现有执行者 actor，tool=claude；不新增 actor 词表
      provider: anthropic
      repos: [bifrost-platform]
      roles: [implement]
  ```
  该段只在签名生效版本里存在时有效；删除它是收紧（无需签名），立即停止新 pin 与新领取。

### 2.2 设 pin 的判定（store 层，所有入口共用）

`task_proposed` 带 `executor_pin` 时，`store` 在写入事务内、在 `holdsToken`/`CheckWriter` 之后检查，全部满足才写：
1. `Writer.Relayed == false`（`store/brief.go:120` 的代写不得设 pin）；
2. `Writer.Actor` 等于生效 envelope 里该 pin 的 `proposer`，且 `Writer.Token == Writer.Actor`（座位令牌名即 actor，来自服务端令牌表，不来自请求头）；
3. 角色 `implement`、`effect_class=branch`、repo ∈ 该 pin 的 `repos`、无 `subject_task_id`；
4. 写入事件正文带 `executor_pin` 与审计字段 `via_session`（请求头原值，只记录，不授权；缺省为空串）。

不满足 → `ErrInvalid`（HTTP 422 `pin_not_permitted`），零任务、零事件。计划导入（`agentrt/planimport`）、控制器生成的 verify/review/gate 任务、Console 目标、`Relayed` 写入都**不读也不传** pin 字段；它们的结构体没有该字段（编译期保证），store 校验是第二道。

**不可变**：数据库触发器禁止 `UPDATE` 改 `executor_pin`（§7.1）；改指派只能取消任务、重新提议，审计留在旧任务。

### 2.3 为什么第一版不做逐线程隔离

同一 Owner 的统筹线程（主线程、分叉）属于同一信任域、同一台 Mac、同一提议主体；要防的是「非统筹主体创建或领取 pin 任务」，不是统筹线程之间互相领。逐线程隔离需要一个调用者伪造不了的线程绑定，而线程号是自报的（`agentrtapi/propose.go:20` 的注释原话即「attributes the write, it grants nothing」）。因此：
- 同一 `seat:coordinator` 提议的全部 pin 任务，`coordinator-mbp` 都可按 id 领取（T6 两件都可领是**成功**用例）；
- 误领他线程任务的后果只是操作失误：persist 要求提交带 `Agentrt-Task: <该任务>` 尾注、父提交等于该任务 `base_commit`（§2.5），交错的提交过不了；
- `via_session` 留审计，Console 任务详情显示。

### 2.4 精确领取 `POST /agentrt/claim/pinned`

- 只接受执行主体（角色 agentd、绑定主机的 `host_kind = external`）；其他主体 403 `forbidden`，零尝试。
- 请求 `{host_id, task_id, idempotency_key, free_slots, disk}`；**不收 `tools`**：工具固定取 envelope 里该主机的 `{executor, provider}`。
- 实现：把 `store/claim.go:89` `claimNext` 的事务体拆成 `claimIn(tx, r, src candidateSource, o)`；`ClaimNext` 用分页候选源（现有 `candidates`），`ClaimPinned` 用单任务候选源（`candidateOf` + 条件 `state='ready' AND executor_pin=<该主机的 pin>`）。主机状态、`held` 控制、`perHost` 并发、在跑数、磁盘、`notCooling`、`readCapabilities`、envelope（`envelopeTools`）、`tryCandidate`/`take`（mission 活跃、租户、预算、`pickTool` 的 core 与独立性）、`lease`、`confirmClaim` **全部共用**，不得为 pin 另写一条。
- 通用 `/claim`：调用主体的主机 `host_kind = external` → 403 `external_host`，零尝试；普通主机的候选查询加 `AND t.executor_pin IS NULL`（`store/claim.go:222`），所以普通主机永不领 pin 任务，pin 任务也不挡住后面的普通任务。
- 外部主机的 tools 不参与能力路由以外的选择；它永远不领 verify/review/plan/brief/gate（结构上：pin 只允许 implement，候选源只取 pin 任务）。

### 2.5 handin 顺序与恢复（`infra agent-config/scripts/landing/handin.sh`）

1. 统筹本地准备单提交：父 = 任务 `base_commit`；提交信息带唯一 `Agentrt-Task: <task>` 与 `Change-Id`（`landinggit/replay.go:15–16` 的血缘检查需要）。**此后不得 amend。**
2. `claim/pinned`（幂等键见 §2.6）→ `attempt_id`、`attempt_no`、`ref = refs/heads/agent/<task>/a<n>`、`epoch`。
3. 上传报告 artifact；`start`；`computed`（引用报告）。
4. 以统筹本人身份把提交推到服务端分配的 ref。
5. `persist{ref, commit}` → `submit`。
- 续租：2–5 之间每 60 秒 `heartbeat`（`LeaseTTL=120s`、`Grace=15m`，`store/kernel.go:43`）。
- 恢复：任一步超时先读回（`GET /attempts/{id}`；还没拿到 attempt 时用**同一幂等键**重发 `claim/pinned` 取回原响应）；按读回结果继续，不盲目重领、不推第二个提交。失租（服务端已把尝试记为 `lost`/结束）后，用**新键**重新领取得到 a<n+1> 与新 ref。

### 2.6 幂等

- 键空间：`host:coordinator-mbp | claim_pinned | <key>`，请求指纹 = `canon.Sum({task_id})`（复用 `store/keyed.go` 的 `idempotent`，有效期 ≥ 24 h）。
- 同键同请求：返回同一响应（即使尝试已结束，返回的仍是那次的 attempt，客户端再读回状态）。同键换 task：409 `key_conflict`。并发同键：键锁串行，恰一个租约。
- 任务已有在跑尝试时用新键：409 `state`（`attempt_one_live` 唯一索引，`migrations/0001_core.sql:193`），不产生第二租约。
- 建议键格式 `<task>:<n>`（n 为客户端第几代），服务端不解析。

### 2.7 persist / salvage 一致性校验（共用一个函数）

`store/attempt.go:449` `Persist` 与 `:511` `Salvage` 都调用新函数 `checkPinnedResult(tx, attempt, ref, commit)`（pin 任务专用；普通任务行为不变），服务端读 Gitea：
- ref 等于服务端分配的 `agent/<task>/a<n>`，ref 指向所报 commit；
- 单提交、唯一父 = 任务 `base_commit`；提交信息血缘尾注 `Agentrt-Task` 等于该任务、恰一个 `Change-Id`；
- repo ∈ 主体允许集合；
- **core 派生**：diff 是否碰 `Repos[repo].Core` 目录（`store/core.go`）由服务端计算；碰了而任务 `core=false` → 拒绝 `core_mismatch`（重新以 `core=true` 提议）；`core=true` 时路由要求 review_core 持有者（现有 `store/route.go:296`）。
任一不符拒绝，零状态变化。验收与评审始终钉这个 A；ref 之后被移动不影响已钉的 A。

### 2.8 标准 spec、评审路由与时限

- pin 任务的 spec 必须由 `store.ImplementSpec`（`store/repos.go:221`）以该仓库的 Verify 清单生成，提议时服务端生成并存 artifact；上传方给的 spec 不采用。
- 以 pin 任务为 subject 的 verify/review 子任务：不继承 pin；review 的 `route_json` 由服务端固定为 `["exec:codex"]`（第一版评审方固定 Codex/openai；现有 Cursor 候选 provider 标签 `cursor-mix` 不能证明非 anthropic）。实现方 provider 记登记值 `anthropic`，`Start` 的 provider 核对（`store/attempt.go:150`）保留。
- 评审时限：生成 review 任务时按 A 的 diff 规模算 `hard_limit_s = min(3h, max(1h, 1h + ⌈changed_lines/300⌉ × 30m))`，受预算规则约束。
- **混合来源（F4 A）**：第一版只接收统筹会话亲手写的实现。提议正文须声明 `providers: [anthropic]`；声明含其他 provider 的提议直接拒绝（`mixed_source_not_supported`），回 Owner 手推。服务端无法证明代码来源，这条是**声明 + 异家评审**约束，不是机械证明（§9 残余风险）。

---

## 3. 检查的三层

### 3.1 变更端点（N-02）

`LandingChange`（`rules/landing.go:199`）按类别定「存在的端」：新增 → 新端；删除 → 旧端；修改 → 两端（同值）；改名/复制 → 两端。两端皆空、任一端不是合法 repo 相对路径（`landingPath`，`rules/landing.go:172`，含 `..`、绝对路径、控制字符）→ 结构违例。所有路径检查（hard、软、规则）对**每个存在的端**都做。

### 3.2 三层定义

1. **不可豁免层**（总先执行；任何 grant 都无效；失败即出生终态 `failed{floor}` 或现有对应拒绝）：
   - 结构 `StructuralViolation(changes)`（从现 `FloorViolation` 拆出）：非 `100644/100755` 模式（符号链接、子模块）、模式变化无内容、二进制、负行数、非法/空路径；
   - hard `LandingHard(repo, path)`（§4）；
   - 规则有效性 `ruleValid`（从现 `ruleOK` 拆出，`landing/eligibility.go:64`）：规则存在、kind、租户、生效期内、规则含该 repo；缺规则明确返回 `rule`，不取旧版、不解引用空指针；
   - 全局前提：mode、live、仓库停止（B6）、before_enable、stale、result、history、terminal、dependencies；
   - grant 支持：`GrantSupported(repo)` 且任务带 pin（只影响能否进入等待，见 §3.4）。
2. **可逐项豁免层**（只在最终闸判；结果是集合）`LandingSoftRefusals(rule, repo, changes) ⊆ {floor_soft, rule_paths, presentation, size}`：
   - `floor_soft`：命中现 `LandingFloor`（`rules/landing.go:186`）但不命中 hard 的路径；
   - `rule_paths`：不在该 repo 的 allow 内，或命中 deny；
   - `presentation`：allow 内的展示路径未过 `LandingPresentationOnly`；
   - `size`：文件数或行数超该 repo 有效上限。
3. **始终生效层**：全租户每日总额度（grant 落地照占）、仓库在途上限、R 的最新 CI 成功且晚于 prepared、main 仍是 M0、发布窗口空闲、6h/8 次（§5.3）。

### 3.3 软集合在两处算，判据只有一个

- 进入等待时：`soft_at_request` 写进 `awaiting_grant` 记录与审批材料；审批参数的 `waives` **恰等于**它（Owner 不能多选或少选）。
- 消费时（最终闸，持锁、`DecisionAt()`、按当时重选的规则）：重算 `soft_now`；要求 `soft_now ⊆ grant.waives`。
  - 规则收紧使未豁免类别新失败 → 拒绝 `grant_insufficient`，操作留在 `awaiting_grant`，显示「规则已变，需要重批」；
  - 规则放宽使 `soft_now` 为空 → 仍可推；若该操作有有效 grant，`main_intent` 照样带 `landing_grant_use`（消费它，防复用，B5 也能看到）；
  - 同一 R 的 `size` 只可能因上限变化而变，已在 `waives` 里则继续豁免。
- `checks_version`：`rules.LandingChecksVersion`（整数常量，检查语义变化时递增）；grant 记批准时值，消费记当时值，不同只记录、不另作判据（集合子集判据已覆盖）。

### 3.4 支持矩阵（R-05）

| repo | 规则内自动落地 | 软底线经 grant | hard | `stg_release` |
|---|---|---|---|---|
| `bifrost-platform` | 是 | **是**（仅 pin 任务） | 永不 | 由规则定；grant 另带 `stg_release` 位（§8） |
| `bifrost-trade-infra`（S6 接入后） | 只 S6 第一批文档 | **否**（`GrantSupported=false`） | S6 §2.1 表 | `none` |
| 其他 | 否 | 否 | 全部视为 hard（未知仓库失败闭合） | — |

- 非 pin 的运行时任务**不进入等待**：软底线命中仍是现状（`floor` 出生终态、`rule` 暂停等规则），第一版 grant 只服务统筹提交，缩小影响面。
- 「grant 不支持」只在不可豁免层全部通过之后才判（顺序：结构 → hard → 规则有效性 → 全局前提 → 支持），所以 hard 的测试不会被「不支持」遮蔽（T20 与 T26 分开）。
- infra 超限出口：合法拆分，或 Owner 手推；**不存在**普通 D 单放开 infra hard 或 infra 超限的路径。

### 3.5 CI 证据读取契约（核心侧；B5-b 与 S6-3 共用）

把 `api/internal/delivery/landing_drill.go`（`LandingCI`、`landingCIResults`、`landingRevision`、`EnsureLandingCI`、`LandingWindowBlocked`）**整体搬进新包 `api/internal/agentrt/landingci`**（hard）；`delivery` 不再含落地代码，装配在 `api/internal/server/agentrt_landing.go`。契约：
1. 输入 `(repo, R, M0, 兄弟 SHA 集合)`；流水线与结果字段按仓库表映射（platform：`bifrost-ci-platform`，结果 `platform-commit`、`ui-commit`、`infra-commit`，现 `delivery/landing_drill.go:81`）；S6 加 infra 行，不得把 platform 改成统一 `commit`。
2. 先按可信 repo + pipeline + 标签列出**包括无结果在内**的全部 run，按 `creationTimestamp`、再按名字取最新一个；**再**核对它：pipelineRef、参数 revision、结果里的候选 SHA 等于 R、兄弟 SHA 等于输入。最新一个是 Running / 无结果 / Failed / 结果不符 → 状态 Running / Unknown / Failed，**不退选旧绿**（保持现 `LatestCI` 的保证）。
3. `EnsureLandingCI` 同名冲突：比对 pipeline、全部 spec 参数与兄弟 SHA，完全相同才认领，否则拒绝。
4. 结果携带 run 名、UID、创建时刻、状态、实际 SHA，进 `candidate_digest`（§5.6）。

---

## 4. 硬底线（hard）：信任闭包与手推范围

### 4.1 判定规则

- `LandingHard(repo, p)`：repo ≠ `bifrost-platform` 时，在 S6 提供该仓表之前一律 true；platform 下命中 §4.2 任一行即 true。
- Go 包行按**目录前缀**判（递归）：该目录下任何文件——含新增的同包文件、`_test.go`、`testdata/`、构建约束文件、子包——都命中。
- 文件行按全路径相等判；「任意深度」行按基名判。
- 清单常量写在 `api/internal/agentrt/rules/landing_hard.go`（本身在 hard 目录内）。

### 4.2 platform 完整清单（第一版）

**A. Go 包（目录前缀，递归）。** 「根」是链上直接承担职责的包；「依赖」是根的非测试依赖闭包（`go list -deps`，在 cb47820d 实测）。

| 目录 | 链上职责 | 根/依赖 |
|---|---|---|
| `api/internal/approvals/` | 审批状态、执行、渠道/确认号 | 根 |
| `api/internal/approvalhome/` | PROD 归属判定 | 根 |
| `api/internal/approvalnotify/` | 审批通知与 Console 链接 | 根 |
| `api/internal/actions/` | 动作目录、分级、参数哈希、执行上下文 | 根 |
| `api/internal/actuation/` | 令牌→主体、角色 | 根 |
| `api/internal/actuationpolicy/` | 动作策略 | 根 |
| `api/internal/agentrt/store/` | 事件追加与校验、协议记录、领取、尝试、验收、最终闸、grant | 根 |
| `api/internal/agentrt/landing/` | 落地协议与资格 | 根 |
| `api/internal/agentrt/landinggit/` | 携落地凭据的 Git 读写与重放 | 根 |
| `api/internal/agentrt/landingci/`（新） | CI 证据（§3.5） | 根 |
| `api/internal/agentrt/rules/` | 规则解析、签名比较、底线与 hard 常量 | 根 |
| `api/internal/agentrt/controller/` | 落地循环、第二道闸调用、推送 | 根 |
| `api/internal/agentrt/agentrtapi/` | 主体→writer、领取/尝试/提议路由 | 根 |
| `api/internal/agentrt/relay/` | 代写（Relayed）路径 | 根 |
| `api/internal/agentrt/canon/` | 规范编码与摘要 | 根 |
| `api/internal/agentrt/migrate/`、`api/internal/agentrt/migrations/` | 库约束与触发器 | 根 |
| `api/internal/agentrt/agentrttest/` | hard 包测试所用的库夹具（证据） | 根 |
| `api/internal/agentd/` | 确定性验收的执行者（验收证据） | 根 |
| `api/internal/server/` | 装配、落地凭据接线、审批执行器、鉴权中间件 | 根 |
| `api/internal/agentrt/actions/`、`agentrt/gaterun/`、`agentrt/plan/`、`agentrt/planimport/`、`agentrt/planview/`、`agentrt/recorderimport/`、`agentrt/seatproto/` | store/agentrtapi/agentd 的依赖 | 依赖 |
| `api/internal/statefile/`（含 `k8sstate/`）、`api/internal/notice/`、`api/internal/safego/`、`api/internal/localpath/`、`api/internal/questions/`、`api/internal/releasepolicy/`、`api/internal/maintainer/` | 审批存储与上述包的依赖 | 依赖 |
| `api/cmd/` | 全部二进制入口（platform-api、agentd、agentrt-gate 等） | 根 |

全部目录在 cb47820d 存在（`landingci` 为本块新建）。`server` 的其余依赖（research、marketdata 等业务包）**不**列入：它们只被装配挂载，不在授权与落地的调用链上；它们的同进程能力见 §4.3。

**B. 授权来源的进程外部分。**
- `mcp/platform/`（递归）：`bifrost-approve` 持 admin 令牌（`mcp/platform/src/registerApprove.ts`），服务端只把 `channel` 当标签信任（`approvals/service.go:512`）。

**C. Owner 决策 UI 与浏览器侧凭据（Console，逐个文件）。**
- 构建与装载入口：`console/package.json`、`console/package-lock.json`、`console/vite.config.ts`、`console/vitest.config.ts`、`console/tsconfig.json`、`console/tsconfig.node.json`、`console/index.html`、`console/nginx.conf`、`console/public/sw.js`、`console/public/manifest.webmanifest`、`console/src/main.tsx`、`console/src/App.tsx`、`console/src/pwa/`（递归，service worker 可截获请求）。
- 审批与鉴权 API：`console/src/api/approvals.ts`、`console/src/api/approvalsServerContract.ts`、`console/src/api/approvalGoStructParse.ts`、`console/src/api/client.ts`、`console/src/api/serverContact.ts`、`console/src/api/landingGrant.ts`（新）。
- 登录与令牌：`console/src/hooks/PlatformAuthProvider.tsx`、`console/src/hooks/platformAuthContext.ts`、`console/src/hooks/usePlatformAuth.ts`、`console/src/lib/platformAuth.ts`、`console/src/lib/platformAuthUi.ts`、`console/src/lib/signInError.ts`。
- 决策页：`console/src/pages/ApprovalsPage.tsx`、`console/src/pages/ApprovalReviewButton.tsx`、`console/src/pages/approvalDecision.ts`、`console/src/pages/approvalSiblings.ts`、`console/src/pages/approvalWaitingNotice.ts`、`console/src/pages/approvalsReadNotice.ts`、`console/src/pages/CloseUnknownForm.tsx`、`console/src/pages/decisionContact.ts`、`console/src/pages/decisionSignIn.ts`、`console/src/pages/DecisionEnvironment.tsx`、`console/src/pages/useDecisionEnvironment.ts`、`console/src/pages/useDecisionPageResume.ts`、`console/src/pages/serverContactNotice.ts`、`console/src/pages/ServerContactStatus.tsx`、`console/src/pages/shell/needs-you/ApprovalPlanSteps.tsx`、`console/src/pages/shell/needs-you/ApprovalRow.tsx`、`console/src/pages/landing-grant/`（新，递归：授权材料页）。

**D. 构建、依赖、仓库元数据、配置。**
- `api/go.mod`、`api/go.sum`、`api/Makefile`、`Makefile`；
- 任意深度基名：`package.json`、`package-lock.json`、`go.mod`、`go.sum`、`Dockerfile*`、`.env*`、`.gitattributes`（可改 diff/二进制判定）、`.gitmodules`；
- `.husky/`（递归）；`.github/`（递归；cb47820d 尚不存在，预留，出现即 hard，闭包测试的「存在」断言跳过标「预留」的行）；
- `config/actions-catalog.json`、`config/actuation-policy.yaml`、`config/platform-auth.yaml`。

### 4.3 机械守护与如实边界

- **闭包测试** `api/internal/agentrt/rules/landing_hard_closure_test.go`（随 ci-platform 跑）：对 A 表的全部「根」跑 `go list -deps`，断言每个 `…/api/internal/…` 依赖目录都被 A 表覆盖；断言 A/B/C/D 表中每个非「新」「预留」条目在仓库里存在（防过期）。给 hard 包新增依赖必然修改 hard 文件，因而由 Owner 手推，闭包测试在那次提交上逼着同时更新清单。
- **Console 调用点扫描** `api/internal/agentrt/rules/landing_hard_console_test.go`：扫描 `console/src` 非测试文件，凡出现 `postApprovalDecision`、`postApprovalResolve`、`createApprovalRequest`、`operatorToken`、`APPROVAL_TOKEN_STORAGE_KEY`、`Authorization` 头构造、`navigator.serviceWorker` 的文件必须在 C 表内；新增一个这样的调用点而不入表即红。
- **没有的保护（如实）**：hard 只保证「本通道改不了 hard 目录里的代码与配置」。同一进程里 hard 之外的包（例如 `api/internal/research/`）仍可通过 Go 的任意能力——读环境变量开数据库连接、写 statefile 所在文件、`actions.Execute`（导出函数）、改全局 HTTP 客户端——影响授权链。数据库触发器只约束运行时角色能写什么，区分不了「哪段同进程代码」在写。所以 **hard 之外的同进程代码靠 Codex 异家评审 + Owner 逐件语义审查（每件软底线提交都要 D 级单）**，本稿不宣称机械自保护。§5.6 的执行器回读审批记录、§7.1 的库触发器只把「最便宜的绕法」堵上。
- 以后要缩小 hard（例如把 store 拆成受保护内核与业务部分、或进程隔离），另立设计。

### 4.4 第一版仍由 Owner 手推的范围与粗算占比

手推范围：① 碰 §4.2 任一行的提交（含本块自身的全部实现）；② 混合来源提交（F4 A）；③ 统筹没走 handin 的提交、紧急修复；④ infra 除 S6 第一批文档以外的一切。

**粗算**（只看路径、不看单提交/规模拆分，非精确）：platform `cb47820d`，`git log --no-merges --name-only`，2026-09-28 00:00 至 2026-10-29 00:00 CDT，共 895 个提交：

| 口径 | 提交数 | 占比 |
|---|---:|---:|
| 碰 §4.2 hard | 679 | **75.9%** |
| 碰现 `LandingFloor`（v1 底线） | 845 | 94.4% |
| 碰底线但不碰 hard（软底线，D 级单候选） | 175 | 19.6% |
| 不碰底线（规则内候选） | 50 | 5.6% |

主要来源：`agentrt/store` 320、`server` 154、`agentd` 136、`agentrtapi` 128、`controller` 88、Console 审批/鉴权/构建文件 67、`mcp/platform` 63。敏感度：去掉 `server` 仍有 637（71.2%），去掉 `store` 仍有 570（63.7%）——占比由「这 30 天主要在建运行时本身」决定，不是某一行列宽了。

**含义**：按历史结构，第一版之后约四分之三的 platform 提交仍由 Owner 手推；本通道接走的主要是软底线约五分之一（逐件 D 单）与规则内约 5%。「过渡期结束」在 F3 A 下应读作「信任闭包之外的统筹提交走落地」，不是「Owner 不再手推」。B5 v3 §17.3 预计的「每月数次阻断」要按此修正（统筹另行告知 Owner；不在本稿改 B5）。

---

## 5. 等待、准备代与授权

### 5.1 一条软底线根的完整路径

1. handin 被接受（验收 + Codex 评审）→ 根进入落地范围。
2. 领取资格（`EligibleToClaim`）只判不可豁免层与始终生效层中的在途/额度；**不判软集合**。通过 → 操作 `land:<task>:1` `claimed`。
3. 准备：现有 Replay（父、血缘、文件交集、stable patch-id 全部保留，`landinggit/replay.go`）→ `prepared{R, M0, committer_date}` → 推 `land/prod/<task>/1` → CI。
4. 最终闸（`AuthorizeLandingPush`，`store/landing_live.go:61`）：在现有锁序与检查之后算 `soft_now`：
   - 空 → 照常写 `main_intent`（规则授权）；
   - 非空且该操作有可用 grant 且 `soft_now ⊆ waives` → 写 `main_intent`，同一事件带 `landing_grant_use`（消费，§5.5）；
   - 非空且无可用 grant → 同一事务写 `awaiting_grant`（不预留额度、不推）。
5. 统筹建 D 级单（§5.6）→ Owner 批准 → 执行器写 `landing_grant` → 下一轮最终闸消费 → push → 对账 → `landed`。

### 5.2 协议 v1.2（`api/internal/agentrt/landing/protocol.go`）

- `Version = "1.2"`；`Parse` 接受 `v ∈ {1, "1.1", "1.2"}`，每个 kind 有**最低版本**表（现代码只接受 `1` 与当前 `Version`，`protocol.go:90`——改版本号时必须改成集合，否则全部 v1.1 记录读不出；T45）。
- 新 kind `awaiting_grant`（v1.2）：字段 `soft files lines material`；`soft` 为 `{floor_soft, rule_paths, presentation, size}` 的非空子集（升序、去重），`material` 为 `sha256:` 摘要。
- 转移：
  - `branch_pushed → awaiting_grant`：要求非 DryRun、该 op 的 `CI.status = Succeeded`、`R`/`M0` 已有；
  - `awaiting_grant → main_intent`（与 `branch_pushed → main_intent` 同条件）；
  - `awaiting_grant → ci_seen`（只更新 CI，阶段不变）；
  - `awaiting_grant → discarded{main_changed}`；
  - `awaiting_grant → failed{declined | approval_expired | bound | stale}`；
  - `awaiting_grant → parked` 不允许（等待本身就是暂停）。
- `Active()`（`protocol.go:563`）排除 `awaiting_grant` → `OtherInFlight`（`store/landingfacts.go:105`）不计它。`EndsAtBound()` 包含它。`Terminal()` 不含它。
- `failed{declined}` 从 `awaiting_grant` 写入时，同一事件必须带 `landing_grant_request{op, approval_id, status:"rejected"}`（append 校验强制），把处置绑定到具体审批。
- `RetryableReasons` 加 `approval_expired`。`declined` 仍不可重试。
- 新增 `reasons`：`approval_expired`、`grant_insufficient`（后者只出现在最终闸决定里，不是 failed 原因）。
- 旧代码（v1.1 解析器）读到 v1.2 kind 会整条流读不出 → 失败闭合（不领、不推）；所以回滚只能在流里没有 v1.2 记录时做，否则向前修（Owner 2026-10-19「往前修」）。

### 5.3 计时与预算（唯一定义）

对一个根，按当前 **retry epoch**（首次领取起，或最近一次 Owner `retry` 起，沿用 `landing/drill.go:151` `RootBudget` 的起点）：

| 量 | 定义 | 上限 | 到限 |
|---|---|---|---|
| 等待区间 | 每个 `awaiting_grant` 操作：从进入时刻到「出现有效 grant」或「离开该阶段」的较早者；有效 grant 过期/撤销而未消费时，从过期/撤销时刻重开一段 | — | — |
| 累计等待 `W` | epoch 内全部等待区间之和 | **72 h** | `failed{approval_expired}`（可「再试一次」） |
| 执行时钟 `E` | `now − epoch 起点 − W` | **6 h** | `failed{bound}`（现有） |
| 操作数 `n` | 根的全部操作数（含每一代），**不因 retry 清零**（CUT §5 第 6 项原定） | **8** | `failed{bound}`（现有） |

- `landing.Bound` 改为用 `E` 判 6 h（等待暂停执行时钟）；8 次判据不变。「等窗口、等 main 变绿」仍算执行时间（不变）。
- 到限结算在现有独立对账循环（CUT §11.8 v3 第 6 条，`SettleLandingDrillBounds` 的 PROD 版）里做，与 live 开关无关；最终闸持锁时也查 `E`（现 `store/landing_live.go:133`）。
- **第 71 小时获批**：grant 写入即结束当前等待区间，`W` 停在 71 h，不会在 72 h 被终结；之后受 grant 24 h 有效期与 `E` 约束。
- `main_intent` 之后只对账（`AtMain`），任何计时器都不把它改成 failed。
- retry 开新 epoch：`E` 与 `W` 都从 retry 时刻重算；`n` 不清零。

### 5.4 代、刷新与归属

- 一代 = 一个操作。代内 R、M0、ref、committer date、CI 不可变；main 前进只产生下一代，旧 ref 不覆盖、不复用（解 679 B-05 的 `branch_collision`）。
- **刷新**由需要触发，不随 main 每动一次自动重做（控制 CI 与操作数消耗）：
  - 统筹 `POST /agentrt/landing/refresh {task, op}`（执行主体）：要求 op 是该根最新操作、阶段 `awaiting_grant`、服务端读到的 main 头 ≠ op.M0；写 `discarded{main_changed}`，下一轮领取产生 k+1。
  - 审批执行时 main 已不是 M0（§5.6 第 4 步）→ 执行失败并同样写 `discarded{main_changed}`。
  - 最终闸持有效 grant 但 main ≠ M0 → `discarded{main_changed}`（grant 随旧操作作废）。
- 两 worker 并发、推分支响应丢失、准备后重启：沿用现有操作协议（`claimed` 在仓库流锁下唯一、`branch_intent`→读回→`branch_pushed`）。
- **归属**：审批参数、grant、撤销、请求观测、拒单都带 `op`；只有「op 是该根最新操作且处于 `awaiting_grant`」时才作用于根。旧代的审批迟到批准 → 执行失败（op 不是最新）；迟到拒绝 → 只记观测，不终结新代。
- 每个操作同时至多一张**未结**审批单（pending / approved / running）：建单校验拒绝第二张。

### 5.5 落地流里的授权记录（闭合 schema）

全部写在 `landing:bifrost-platform` 流（`note` 事件，正文用独立键，旧 Fold 忽略它们；`store/vocab.go` 加闭合校验与 append 校验 `checkLandingGrantAppend`）：

| 正文键 | 字段（全部必填，闭合） | 写入者与时机 |
|---|---|---|
| `landing_grant` v1 | `v grant_id approval_id approval_number action params_hash home env tenant repo task attempt op A base R M0 committer_date candidate_digest material_digest waives soft_at_request files lines rule{id,version,sha256} checks_version ci{pipeline,run,uid,created_at,status,sha} purpose stg_release approved_at granted_at expires_at` | 只由审批执行器（§5.6），actor `controller`，持仓库流锁 |
| `landing_grant_revoked` v1 | `v grant_id by at` | 只由撤销入口（§5.7） |
| `landing_grant_request` v1 | `v op approval_id approval_number status params_hash seen_at` | 请求观测循环（§5.8）；`status ∈ {pending, approved, running, executed, failed, rejected, expired, unknown}`；按 `(approval_id, status)` 去重 |
| `landing_grant_use`（`main_intent` 事件的同级段） | `v grant_id candidate_digest soft_now rule{id,version,sha256} checks_version decided_at` | 最终闸，与 `main_intent` 同一事件（消费原子） |

- `grant_id = "lg_" + approval_id`（确定性）；`purpose = "landing_main"`（第一版唯一取值）；`expires_at = approved_at + 24h`，`approved_at` 取审批记录的批准时刻（从审批服务读，重复执行不刷新）。
- 唯一性（append 校验 + 执行器锁内检查）：同一 `approval_id` 至多一条 `landing_grant`；同一 `approval_id` 内容不同 → 拒绝；同一 `op` 在任一时刻至多一个**有效** grant（未撤销、未过期、未被 `landing_grant_use` 引用）。
- **两个摘要**（§5.6 第 3 步定义输入）：`candidate_digest` 只覆盖与规则无关、代内不可变的候选内容；`material_digest` = 它再加上建单时的规则身份与软集合，即 Owner 看到的全部材料。建单与执行比 `material_digest`（规则在建单后变了 → 执行失败、重建单，Owner 不会批一份过时的软集合）；消费只比 `candidate_digest`，规则差异交给 §3.3 的子集判定（否则规则一变 grant 就永远不可用，B-03 的子集判定形同虚设）。
- **可用 grant**（最终闸）= `op` 相同、`R`/`M0`/`A`/`attempt` 与操作一致、`candidate_digest` 等于当前重算值、未撤销、`decided_at < expires_at`、未被消费；随后才做 `soft_now ⊆ waives`。`candidate_digest` 含 R 的 CI 运行身份：R 的最新 CI 换成另一次运行（即使仍绿）也使 grant 不可用、需重建单——第一版接受这份保守。
- 「已消费」唯一定义：流里存在 `main_intent` 事件其 `landing_grant_use.grant_id = G`。没有单独的 consumed 记录。

### 5.6 建单与执行（`approve_guardrail_landing`，tier D，PROD only）

1. **目录**：`api/internal/actions/catalog.go` 与 `config/actions-catalog.json` 加动作；参数闭合：`{env:"prod", repo, task, op, R, material_digest, stg_release}`。参数哈希入单。
2. **建单校验**（`api/internal/server/approval_create_check.go`，已有钩子）：`approvalhome.IsProd()`；repo ∈ `GrantSupported`；任务带 pin；op 是最新操作且 `awaiting_grant`；`R` 一致；`material_digest` 等于服务端当场重算；op 无未结审批单；服务端读 main 头 = op.M0（读 Git 在事务外）。任一不符拒绝建单。统筹用 `request_action` 建单，参数由 `handin.sh status` 原样打印。
3. **材料**（`GET /agentrt/landing/{op}/material`，Console `console/src/pages/landing-grant/`）：两个摘要都用 `canon.Sum`：`candidate_digest = Sum({v, env, tenant, repo, mission, plan_step, task, attempt, op, A, base, R, M0, committer_date, changes:[{old,new,old_mode,new_mode,added,deleted}], patch_sha256(M0..R), files, lines, acceptance:[{verification_id, result}], review:{task, attempt, executor, provider, conclusion, artifact}, review_patch_match(A 与 R 的 stable patch-id 是否一致), ci{pipeline, run, uid, created_at, status, sha, siblings}, stg_release})`；`material_digest = Sum({v, candidate_digest, soft_at_request, rule{id,version,sha256}, checks_version})`。`handin.sh status` 打印的是服务端当场重算值，不是 `awaiting_grant` 记录里的旧值。页面显示全部这些、完整文件表与增删行、patch 正文（≤512 KB；超出只显示文件表并给 Gitea `M0...R` 比较链接，摘要仍覆盖全文）、当日总额度快照（注明以推送时为准）、「main 仍是 M0？」实时指示、有效期、撤销入口、`stg_release=true` 时的文字「批准即授权该提交随 B5 批次发 STG」。hard 命中的变更不会有单。
4. **执行器**（`api/internal/server/agentrt_grant.go`，仿 `server/agentrt_nomerge.go:44`）：
   - `actions.CreateAttemptFrom(ctx)` 必须存在；**并**从审批服务回读该审批记录：action 相符、tier D、状态 running、`params_hash` 相符、批准渠道 ≠ chat、确认号已核、home 为 PROD。只凭上下文不够（`actions.WithCreateAttempt` 是导出函数，同进程任何代码都能构造）；
   - 事务外读 main 头；≠ M0 → 执行失败「main 已前进」，并写 `discarded{main_changed}`（§5.4）；
   - 事务内（锁序 §5.9）重验：op 最新且 `awaiting_grant`、`material_digest` 重算一致（规则变化会改变 `soft`/`rule` 而使其不一致 → 失败，需重建单）、无其他有效 grant、本审批无已存 grant（有且内容相同 → 幂等成功返回原 grant，不改 `expires_at`）→ 写 `landing_grant`。

### 5.7 撤销（F2 A）与三种结果

**撤销入口**：`POST /api/v1/agentrt/landing/grants/{grant_id}/revoke`，只接受 admin（Owner）令牌；Console 授权页按钮。撤销是收紧，不另建审批单。事务内持仓库流锁：未消费 → 写 `landing_grant_revoked`；已消费 → 不写，返回「已交给推送（op …，main_intent 序号 …），不能保证撤销；落地后按正常对账，需要撤回请另做 revert」。不承诺 Git 接收前都可撤（接收端 fencing 不在本块）。

**提交不确定的处理**（COMMIT 传输错误；读回用新事务、先取同一把仓库流锁，等原事务结束，`ctx` 10 s，仿 `store/nomerge_reconcile.go:28`）：

| 动作 | 读回确认已写 | 读回确认未写 | 读回失败 |
|---|---|---|---|
| create（执行器） | 返回成功（同一 grant） | 返回失败（审批单 failed，可重建） | 返回 `actions.Uncertain`；审批单 unknown；**以流为准**：Console 授权页只读流里有无 `landing_grant` |
| revoke | 返回「已撤销」 | 再判：若已被消费 → 「已交给推送」；否则返回失败，可重试 | 返回 503「结果未知，请刷新」；授权页以流为准 |
| consume（`main_intent`） | 现有逻辑：没有内存里的 Authorization 就不推；下一轮看到 `main_intent` → `AtMain` 恢复者对账（推送截止后按 main 读数结束） | 不推；操作仍是 `awaiting_grant`，grant 仍可用 | 不推；同左两种之一由下一轮读流决定 |

审批状态 unknown / failed **不能**作为「grant 不存在」或「已撤销」的事实；只有流里的记录算。

### 5.8 请求观测、显示与 B3/B4

- **请求观测循环**（workers 进程；审批服务在两种角色都装配，`server/approvals_loop.go`）：每 30 s 列出 action=`approve_guardrail_landing` 的审批，对新出现的 `(approval_id, status)` 写 `landing_grant_request`。最新操作的审批变 `rejected` → 同一事件写 `failed{declined}`（§5.2）。`expired`（24 h 未批，`approvals/types.go:26`）只记观测，操作继续等待。
- **显示**（状态接口、目标详情、Landing 行）：
  - 等待且无未结单：「等统筹建 D 级单（op k）」——**不进 Owner 待办**；
  - 有 pending 单且 M0 仍是 main：「等你批 D 级单 #n」+ 链接；
  - 有 pending 单但 main 已前进：「单 #n 已过时，等统筹刷新」——不进 Owner 待办；
  - 有有效 grant：「已授权，等推送」；已消费：「已交给推送」。
- **B3**：等待中不发 `root_failed`/`floor` 卡（审批单就是出口）；`failed{approval_expired}` 走 `root_failed` 卡，`try_again` 可用（`RetryableReasons` 已加）；`failed{declined}`（来自拒单）不发卡（Owner 已决定）。
- **B4**：`awaiting_grant` 归「未了结（等审批）」，mission 保持 active（B4 表第 7 行）；`failed{declined}` 走第 4 行「已处置」，处置依据是同事件里的审批号。
- **mission 停止 / 任务取消 / 计划步骤撤销**（等待中）→ 对账循环写 `failed{stale}`（与 `unclaimedEnd` 同一分类，`store/landing_drill.go:201`）；未消费 grant 随之无用。

### 5.9 锁序（R-06）

全局序：**能力（共享）→ 规则 `landing:<tenant>`（共享）→ 计划步骤 → 任务 → mission → 当日额度流 → 仓库流（多仓按仓库名升序）**。任何操作只取其子集，且按此序取。

| 操作 | 取的锁（按序） |
|---|---|
| `claim/pinned`、通用 `/claim` | 现有领取锁（全局控制共享、能力共享 → 任务 → mission）；不取落地流 |
| 领取落地操作（含新一代） | 现有 `ClaimLanding` |
| 最终闸（含写 `awaiting_grant`、消费） | 现有 `AuthorizeLandingPush` 全序 |
| 执行器写 grant | 规则（共享）→ 步骤 → 任务 → mission（FOR SHARE）→ 仓库流 |
| 撤销 | 仓库流 |
| 刷新、拒单结算、stale 结算 | 任务 → mission → 仓库流 |
| 到限结算（6 h / 8 次 / 72 h） | 现有 `SettleLandingDrillBounds` 顺序 |
| 请求观测（无终结） | 仓库流 |
| B4 Close | mission → 仓库流（升序）；决定点读规则不加锁（CUT §11.8 v3 第 5 条） |

- PG 事务持上述任一锁时**不得**调用审批服务或取审批存储锁；审批执行器在审批服务的存储锁之外运行（`approvals/execution.go` 的 `claimLocked` 在 `store.update` 内，`actions.Execute` 在其外），所以「审批存储锁 → PG」的方向不存在反向。
- 最终闸在锁内读 Git 是现状（`store/landing_live.go:45` 的函数注释），不扩展到其他操作。

---

## 6. 测试清单（R-07）

原则：每条拒绝都有**同入口、同仓库、同授权**的成功对照，然后只改一项；断言拒绝原因、写入的事件、额度、push 调用次数、最终 refs。「变体」列是故意删掉/弄错该检查的离线实现，测试必须在它上面失败（变体只存在于测试夹具，不改生产防线）。「层」：HTTP = 公网入口；store = 带真库的存储层；unit = 纯函数；DB = 运行时角色直连库。HTTP 打不到的内层检查如实标内层，并有端到端闭环另证。

| # | 层 | 入口 | 成功对照 | 只改一项 | 预期 | 变体（应使测试红） |
|---|---|---|---|---|---|---|
| T1 | HTTP | `POST /missions/{id}/tasks` 带 pin | `seat:coordinator` 令牌 → 任务有 pin，`task_proposed` 带 `executor_pin`、`via_session` | 换成共享 operator 令牌 + 头 `X-Bifrost-Session` 写统筹线程的会话 | 422 `pin_not_permitted`，零任务零事件 | 只验线程头 |
| T2 | HTTP | 同上 | 同上 | envelope 去掉 `external_hosts` | 422，零任务 | 不读 envelope |
| T3 | store（内层） | `Relayed` 写入 | 同一 actor 非 Relayed 成功 | `Relayed=true` | `ErrInvalid` | 忽略 Relayed |
| T4 | DB | 运行时角色 `UPDATE task SET executor_pin` | 改无关列（带事件）成功 | 改 pin | 触发器拒绝 | 去掉触发器 |
| T5 | HTTP | `claim/pinned` | 执行主体领 ready pin 任务 → 1 个尝试，ref `agent/<task>/a1` | 换普通 agentd 令牌 | 403，零尝试 | 只验角色不验 host_kind |
| T6 | HTTP | `claim/pinned` | 同一提议主体两件 pin 任务，各按 id 领取均成功、互不串 | — | 正例（替代 v2「别人的任务」） | 候选源取最早一件 |
| T7 | HTTP | `claim/pinned` | T5 | 任务无 pin | 403 `not_pinned`，零尝试 | 不查 pin |
| T8 | store | `ClaimPinned` | T5 | 分别：主机 stop、mission stop、任务 pause、envelope 过期、预算满、`perHost=0`、主机在跑数满 | 各零租约，原因相符 | 精确领取跳过共用判定 |
| T9 | HTTP | 通用 `/claim` | 普通主机领普通任务 | 执行主体调用 | 403 `external_host`，零尝试 | 只换 tools |
| T10 | store | 通用领取 1000 次随机顺序 | 普通任务照常被领 | 最早的 ready 是 pin 任务 | 普通主机从不领 pin 任务，且照常领后面的普通任务 | 去掉 `executor_pin IS NULL` |
| T11 | DB | 运行时角色插 attempt | 外部主机 + pin 任务成功 | dev 主机 + pin 任务；外部主机 + 无 pin 任务 | 触发器拒绝 | 去掉触发器（模拟旧读者） |
| T12 | store | `ClaimPinned` 幂等 | 同键重发返回同 attempt | 同键换 task；两连接并发同键；失租后旧键重放、新键领取 | 409 `key_conflict`；恰一租约；旧键返回旧 attempt（lost），新键得 a2 | 键不含请求指纹 |
| T13 | store | `ClaimPinned` | T5 | COMMIT 时断连 | `confirmClaim` 读回一致 | 不读回 |
| T14 | HTTP | `persist` / `Salvage` | 合规单提交 | 分别：报 a1 而分配 a2、commit≠ref、父≠base、merge、两提交、缺 `Agentrt-Task`、repo 不在集合 | 两入口都拒，零状态变化 | Salvage 不调共用校验 |
| T15 | HTTP | `persist` | 同上 | 缺报告、缺 computed | 拒（旧防线回归，单列） | — |
| T16 | store | `persist` | diff 不碰 core 且 `core=false` | diff 碰 core 目录、`core=false` | `core_mismatch` | 信任提议的 core |
| T17 | store | review 生成与领取 | pin subject 的 review 只给 `exec:codex` | 伪造 subject 尝试 provider 为空/为 openai | 无人可领 / 不得给 codex 以外 | 继承 pin 或不固定路由 |
| T18 | store | pin 任务提议 | spec 由 `ImplementSpec` 生成 | 上传方给删掉 verify 的 spec | 不采用上传 spec | 采用上传 spec |
| T19 | unit | `landing_hard_closure_test` | 当前清单通过 | 夹具里给根包加一个不在清单的依赖 | 红 | 只列文件不求闭包 |
| T20 | store | 最终闸 | pin 任务只改 `api/internal/research/x.go`（floor_soft）+ 有效 grant → 推 1 次、landed | 路径换成新文件 `api/internal/agentrt/store/zz_new.go` | 领取即 `failed{floor}`，无 awaiting、无单；即使流里塞一条伪造 `landing_grant` 也零 push | 按文件名列 hard |
| T21 | store | 同 T20 | 同 T20 | 分别：`api/internal/server/x.go`、`console/src/pages/ApprovalsPage.tsx`、`mcp/platform/src/x.ts`、`config/platform-auth.yaml`、`api/internal/statefile/x.go`、改名 soft→hard（新端）、删除 hard 文件（旧端）、`.gitattributes` | 全部 `failed{floor}` | 只查新端 |
| T22 | unit+store | 结构 | 普通 100644 文本 | 符号链接、子模块、二进制、只改模式、两端皆空、`../x` | 结构违例（`../x` 由路径合法性先拒，单列，不冒充 hard） | 结构并入软检查 |
| T23 | store | 最终闸 | grant `waives=[floor_soft]`，规则不变 → 推 | 消费前签更紧规则使 `size` 新失败 | `grant_insufficient`，留 `awaiting_grant`，零 push，零预留 | 去掉子集判定 |
| T24 | store | 最终闸 | T23 | 规则放宽使 `soft_now` 为空 | 推；`main_intent` 带 `landing_grant_use` | 不消费 grant |
| T25 | store | 最终闸（真 grant，经执行器写入） | T20 | 分别：规则过期、规则缺失、repo 移出规则、live 关、仓库停止、额度满、mission 停止 | 各自原因，零 push | grant 跳过不可豁免层 |
| T26 | HTTP | 建单 | platform pin 任务建单成功 | infra 仓库的根 | 建单拒绝 `grant_unsupported`（与 T20/T21 的 hard 拒绝分开） | 不查支持集合 |
| T27 | store+HTTP | 执行器 | 真审批服务：D 级、Console 渠道、确认号 → grant 字段齐全 | 分别：`actions.Execute` + 伪造 `WithCreateAttempt`（无审批）、别的 action 的已批单、参数哈希不符、op 非最新、规则变化致摘要不符、main 已前进、home 非 PROD | 不写 grant；main 前进时写 `discarded{main_changed}` | 只信上下文 |
| T28 | store | 执行器 | T27 | 同一审批重复执行 | 一条 grant，`expires_at` 不变 | 每次执行新写 |
| T29 | store | 执行器 | T27 | 同 op 已有有效 grant 时第二张单执行 | 失败 | 不查有效 grant |
| T30 | store（内层） | append | 执行器路径写入成功 | operator/agentd 身份、或缺必填字段直接追加 `landing_grant` | append 校验拒绝；公网无写 grant 的路由（列出路由表断言） | 校验器不闭合 |
| T31 | store 双连接 | 撤销 vs 消费 | — | 撤销先提交；`main_intent` 先提交 | 前者零 push；后者返回「已交给推送」且不写撤销 | 不同锁 |
| T32 | store | create 不确定 | — | COMMIT 后断连 / 前断连 / 读回失败 | 成功 / 失败 / Uncertain；授权页以流为准 | 不读回 |
| T33 | store | revoke 不确定 | — | 同 T32 | 表 §5.7 | 同 |
| T34 | store | consume 不确定 | — | `main_intent` COMMIT 断连 | 任何进程都不推；下一轮对账 | 凭内存重推 |
| T35 | store | 最终闸 | grant 有效 → 推 | 决定时刻 ≥ `expires_at` | 拒「授权过期」，零 push | 只在领取时查期 |
| T36 | unit+store | push 参数 | push 的对象 = `main_intent.R` | 夹具在批准后给 R 加尾注 | SHA 不同 → 拒；不因 tree/patch-id 相同接受 | 用 patch-id 比 |
| T37 | 端到端（STG 不建 grant；PROD 实测一件） | 全流程 | 软 → 等待（另一根同时可领可推）→ 建单 → 批 → 推 → landed → B4 delivered | — | 正例 | — |
| T38 | store | 计时 | 等待 10 h 后批准 → 推（执行前 1 h 计入 `E`） | — | 正例 | 等待计入 `E` |
| T39 | store | 计时 | 第 71 h 获批 → 推 | 两段等待 40 h + 33 h 无 grant | 后者 `failed{approval_expired}`；前者不被终结 | 72 h 从首次等待绝对计 |
| T40 | store | 拒单 | — | 最新 op 的单被拒；刷新后旧 op 的单才被拒 | 前者 `failed{declined}` 带审批号、B4 已处置；后者只记观测、新 op 不受影响 | 按根而非按 op 归属 |
| T41 | store | 刷新 | — | main 前进 → 刷新 | op k `discarded{main_changed}`，k+1 新 ref，旧 ref 字节不变；旧单再执行失败 | 覆盖旧 ref |
| T42 | store 双连接 | 新一代准备 | — | 两 worker 同时领 k+1；推分支响应丢失 | 一代唯一、读回恢复 | — |
| T43 | store | 重启 | — | 等待中、grant 已写未消费时重启 | Fold 后状态一致 | — |
| T44 | store | 8 次 | 第 8 代推成功 | 需要第 9 代 | `failed{bound}` | 代不计入 8 次 |
| T45 | unit | 协议 | v1.1 流在 v1.2 代码下 Fold 一致 | v1.1 解析器读 v1.2 记录 | 解析失败（失败闭合，有意） | `Version` 改单值 |
| T46 | store | stale | — | 等待中 mission 停止 | `failed{stale}`，grant 无用 | — |
| T47 | store | B3 | 等待中无卡 | `approval_expired` | `root_failed` 卡，`try_again` 可用且写出 retry | 未加 RetryableReasons |
| T48 | store 双/三连接 | 锁序 | grant 写入、撤销、Close、最终闸分别单跑成功 | 交错执行（钩子挂住） | 无死锁，结果与串行一致 | 执行器先锁仓库流再锁 mission（应死锁超时被检出） |
| T49 | store | B5 读口 | 已消费且 landed 的 op → 返回证据 | 未消费 / 其他 op / 已撤销 | 无证据 | 返回未消费 grant |
| T50 | DB | 迁移 0010 | 在 PROD 结构副本上 up；无 pin 行时旧代码全部用例通过 | — | 正例 | — |
| T51 | unit | Console 调用点 | 当前 console 通过 | 夹具新增一个调用 `postApprovalDecision` 的非清单文件 | 红 | 不扫描 |

数据库与双连接用例只在实现验收时运行。

---

## 7. 迁移、接线与上线顺序

### 7.1 迁移 `api/internal/agentrt/migrations/0010_executor_pin.sql`（F1 A）

```sql
-- host: external kind, at most one external host in this version
ALTER TABLE agentrt.host DROP CONSTRAINT host_host_kind_check;
ALTER TABLE agentrt.host ADD CONSTRAINT host_host_kind_check CHECK (host_kind IN ('dev','vm','external'));
CREATE UNIQUE INDEX host_one_external ON agentrt.host (host_kind) WHERE host_kind = 'external';
-- task: the pin, its shape, its immutability
ALTER TABLE agentrt.task ADD COLUMN executor_pin text;
ALTER TABLE agentrt.task ADD CONSTRAINT task_executor_pin_check CHECK (
  executor_pin IS NULL OR (executor_pin = 'external:coordinator' AND role = 'implement' AND effect_class = 'branch'));
CREATE FUNCTION agentrt.pin_immutable() RETURNS trigger ...   -- OLD.executor_pin IS DISTINCT FROM NEW.executor_pin → RAISE
CREATE TRIGGER task_pin_immutable BEFORE UPDATE OF executor_pin ON agentrt.task ...;
-- attempt: a pinned task only on an external host, an external host only on a pinned task
CREATE FUNCTION agentrt.attempt_pin_guard() RETURNS trigger ...  -- (pin IS NOT NULL) <> (host_kind = 'external') → RAISE
CREATE TRIGGER attempt_pin_guard BEFORE INSERT ON agentrt.attempt ...;
CREATE INDEX task_pinned_ready_idx ON agentrt.task (created_at) WHERE state = 'ready' AND executor_pin IS NOT NULL;
-- grants as 0004 does for its function
```

- 不改 `actor.tool` 闭合集合，不新增事件类型（授权记录都是 `note`）。
- 文件首段照 0008 写明：升级顺序、强锁时长（`task`、`host`、`attempt` 都是小表）、旧迁移器拒绝含此文件的库。
- **PROD 执行需 Owner 在线程里单独点头**（PROD DDL 规则）；执行前 `grep -niE 'drop|truncate'`：本文件命中的只有 `DROP CONSTRAINT host_host_kind_check`（随即重建、放宽），须在请求点头时列明。

### 7.2 读者与词表改动点（R-01）

- `store/claim.go`：普通候选 `executor_pin IS NULL`；`claimIn` 拆分；`ClaimPinned`。
- `store/propose.go`：§2.2 校验；`store/vocab.go`：`task_proposed` 加 `executor_pin`、`via_session`；`host_registered` 接受 `host_kind=external`；新增 `landing_grant*`、`landing_grant_use`、`awaiting_grant` 的闭合校验与 append 校验。
- `store/route.go`：路由 fingerprint 与回放读入 pin 与 subject 的固定评审路由。
- `agentrt/relay`：回放与代写路径不读、不写 pin。
- `store/presencejudge.go`：`host_kind=external` 不进「主机失联」；Console 主机列表标 external。
- `actuation/auth.go`：`seat:` 名唯一校验。`agentrtapi/api.go`：`/claim/pinned`、`/landing/refresh` 路由；通用 `/claim` 拒外部主机。
- 不变：`kindOf`（`store/propose.go:112`）、executor actor 形状 `exec:<tool>`、`actor.tool` 集合。

### 7.3 上线顺序

1. platform 提交 C-0（迁移文件 + 全部读者 + 库触发器；pin 设定路径尚无任何主体有权使用）。
2. STG：迁移 → 发布 → 验证（T50 与普通领取回归）。
3. PROD：Owner 点头 → 迁移 → 发布 → 核对全部 platform-api / workers Pod 跑新提交、旧 ReplicaSet 为 0（无旧读者）。
4. 之后各块代码随常规发布上线；**启用**只发生在：Owner 签含 `external_hosts` 的 envelope、配置两个令牌之后。
5. 回滚：先删 envelope 的 `external_hosts`（收紧，免签）→ 取消未终结的 pin 任务 → 才可回退代码；库触发器保证即使旧读者在跑也领不走 pin 任务（失败闭合：旧读者遇最早候选为 pin 任务时本轮报错，不越权）。流里已有 v1.2 记录时不回退代码，向前修。

---

## 8. 与 S6、B5 的接口

**给 S6（v3 由他人同时写）**：
- `rules.LandingHard(repo, p)`、`rules.StructuralViolation`、端点语义（§3.1）、`rules.GrantSupported`（第一版只 platform）在 `api/internal/agentrt/rules/landing_hard.go`；S6 只往表里加 `bifrost-trade-infra` 行（hard 表 = S6 §2.1），不得给 infra 开 grant。
- CI 读取在 `api/internal/agentrt/landingci`（§3.5）；S6-3 的结果映射加在那里，不再改 `delivery`。
- `AGENTRT_LANDING_LIVE_REPOS` 一旦设置（含空集）即为权威；旧 `AGENTRT_LANDING_LIVE=on` 只在新变量未设置时等价于 `{bifrost-platform}`。
- 多仓锁序按仓库名升序（§5.9）；额度流仍是全租户一份。

**给 B5（v3 §5.1 中的 `landing_override{…}` 与 `LandingFloorHard` 改读下列名字）**：
- `store.LandingGrantEvidence(ctx, q, repo, op) (GrantEvidence, bool, error)`：只在「该 op 有 `main_intent` 带 `landing_grant_use`，且 op 已 `landed{R}`」时返回 `{GrantID, ApprovalID, Purpose:"landing_main", STGRelease, Task, Attempt, A, R, M0, CandidateDigest, MaterialDigest, Waives, ApprovedAt, IntentSeq}`；B5 自己核对 `R == c`、`STGRelease == true`。
- `stg_release` 是审批参数（O-1 A：建单默认 true，审批页写明）。B5 的发布消费记在它自己的 `note.stg_release started`，**不写、不清除**任何 `landing_grant*` 记录；落地 grant 只作来源证据。
- hard 判定用 `rules.LandingHard`；hard 提交必然是非落地提交，按 B5 §5.2 第一行阻断。

**共享文件串行合入顺序**（全部是 hard 路径 → 每一步都由 Owner 用 `push-main.sh` 手推）：
1. 核心 C-0 → C-1 → C-2 → C-3 → C-4 → C-5 → C-6 → C-7（C-3 含 `landingci` 抽出）。
2. B5-a（独立子协议，Codex 680 在做，不碰核心文件）可并行；**B5-b 的 CI 选择在 C-3 之后**基于 `landingci`；**B5-c 在 C-5 之后**接 `LandingGrantEvidence`。
3. S6-1 在核心 C-5 合入之后（建议 C-7 之后）；S6-3 的平台侧读取在 C-3 之后改 `landingci`；S6-2 规则部分、S6-4 依次；S5 最后。
4. 每一步基于前一步合入后的 main 修改并重测；规则正文从当时生效版本生成。

---

## 9. 分块与工时（单人有效工时，按 679 口径 100–150 h）

| 块 | 内容 | 小时 |
|---|---|---:|
| C-0 | 迁移 0010（列、约束、两个触发器、索引）、全部读者（普通候选过滤、presence、词表）、STG/PROD 上线步骤、T4/T10/T11/T50 | 8–12 |
| C-1 | 提议主体：令牌名唯一、envelope `external_hosts` schema 与签名比较、§2.2 校验（含 Relayed、计划导入、控制器生成）、`via_session`、路由回放、T1–T3 | 12–18 |
| C-2 | 精确领取：`claimIn` 拆分、`ClaimPinned`、幂等、通用 `/claim` 拒外部主机、persist/salvage 共用校验、core 派生、标准 spec、评审路由与时限、`handin.sh`（续租、读回、刷新、状态）、T5–T18 | 16–22 |
| C-3 | 检查拆分：`StructuralViolation`、`LandingHard` 与 §4.2 清单、闭包与 Console 扫描测试、`ruleValid` 拆出、软集合、端点语义、`landingci` 抽出与 §3.5 选择算法、T19–T22、T26 | 14–20 |
| C-4 | 协议 v1.2：`awaiting_grant`、版本集合、`Active` 拆分、计时 `E/W/n`、刷新路由、stale/拒单/过期结算、B3/B4 接线、状态显示、T37–T47 | 14–20 |
| C-5 | 授权：两处目录、建单校验、材料与摘要、执行器（审批回读、main 预读）、grant/revoke/use 记录与校验、最终闸消费与子集判定、撤销入口、三种不确定读回、请求观测循环、B5 读口、锁序、T23–T25、T27–T36、T48–T49 | 18–26 |
| C-6 | Console：授权材料页、撤销按钮、状态文案、审批列表里的软检查与 stg 提示（全部在 hard 清单内）、T51 | 8–12 |
| C-7 | 全量回归、双连接/故障用例跑通、PROD 实测（规则内一件、grant 一件、撤销一次） | 14–20 |
| **合计** | | **104–150** |

- 对照 v2 的 84–121：+20–29 h，来自包级 hard 的闭包与扫描测试、`landingci` 抽出、迁移的读者先行与触发器、按操作建代（协议 v1.2）与累计计时、执行器回读审批与不确定读回表。
- 不含：Owner 等待、CI 排队、Codex 代码复核工时、S6、B5、S5。建议在 C-2、C-5 完成后各送一次代码复核。
- 若 Owner 改选 F2 B（不做撤销），C-5 减 3–4 h。

---

## 10. Owner 决定采纳记录（事后审计）

2026-10-28 23:xx CDT，统筹按复核 679 的推荐全部采纳 A，事后审计；Owner 可随时改选，改选只影响尚未实现的块。

| 项 | 采纳 | 落在本稿 |
|---|---|---|
| F1 外部执行者的数据库落法 | **A 迁移加列与约束（pin 列化）** | §7.1 迁移 0010；§7.3 先迁移、再全部读者、确认无旧读者、才启用；**PROD DDL 执行前须 Owner 在线程里单独点头**（本采纳不等于 DDL 批准） |
| F2 撤销 | **A 实现撤销**：消费前可撤，消费后如实提示「已交给推送」 | §5.7 |
| F3 hard 文件能否经审批落地 | ~~A 第一版保持 Owner 手推特殊路径~~ → **Owner 2026-10-28 23:4x CDT 在线程里改选：信任核心的改动也走「核心级 D 单」**（统筹提问的选项 A） | §12 取代 §4.4 的手推范围 |
| F4 混合来源 | **A 第一版不进自动通道** | §2.8 |

同时沿用 v2 已定：E1 A（独立 coordinator 主机与令牌）、E2 A（24 h、从真实批准时刻起、消费时也验、不可刷新）、E4 A（一个接受的单提交、按操作一张单、绑定 R/M0）。E3 由本稿 §4 的包级闭包取代 v2 的「扩大后的最小可信边界」。B5 O-1 A（`stg_release`）在 §5.6、§8 落地。

本稿没有新的待决项。需要统筹另行告知 Owner 的事实：§4.4 的约 76% 仍手推（粗算）。

---

## 11. 残余风险（如实）

1. **同进程代码无机械隔离**（§4.3）：hard 之外的包能在进程内影响授权链；防线是 Codex 评审 + Owner 对每件软底线提交的语义审查。
2. **审批渠道只是标签**：服务端信任 admin 令牌持有者报的 `channel`（`approvals/service.go:512`）；本机 MCP 持 admin 令牌，靠 `preflight.js` 拦截读取与直调。这是 ADR §5 已接受的风险，本块没有加重也没有消除。
3. **混合来源靠声明**（§2.8）：服务端证明不了提交里没有别家模型写的代码。
4. **main 频繁前进的批准浪费**：Owner 手推多（§4.4）时，待批单容易过时；Console 的「main 仍是 M0？」指示与执行器预读能挡住无效批准，但会增加重建单次数，并消耗每根 8 个操作的预算。
5. **收益有限**：按近 30 天结构，本通道接走约 25% 的 platform 提交（软底线约 20% 需逐件 D 单）；大幅减少手推要等 F3 B 或拆分受保护内核，另立设计。

---

## 12. 核心级 D 单（Owner 2026-10-28 23:4x CDT 在线程里选定，取代 F3 A）

**依据**：统筹提问「信任核心的改动，是否也改成你在 Console 批、落地身份推？」，Owner 回「选 A」。理由（统筹提问时陈述）：Owner 手推时推的是统筹给的 SHA，并不逐行看 diff；Console 批准在信任上与手推等价，并多出留痕、异家复核结论与独立核对入口。本节改动 §4 的语义，不改 §4.2 清单本身。

### 12.1 两层 hard

- `hard_core`：§4.2 A、B、C、D 表全部条目，**除** `hard_absolute`。命中时不再是「Owner 手推特殊路径」，而是：领取照常；准备照常；最终闸算出 `core` 失败项 → 进 `awaiting_grant`，只能被 `approve_core_landing` 的 grant 消费，**不能**被 `approve_guardrail_landing` 的 grant 消费（两种 grant 的 `waives` 类别不交）。
- `hard_absolute`（任何单都放不开，仍走 Owner 手推）：任意深度基名 `.env*`；`.gitmodules`；`.github/`（预留）。理由：秘密不应入库，子模块与仓库外 CI 改变的是「检出什么」，不在本仓 diff 可审范围内。清单常量与 §4.2 同文件，闭包测试照旧。
- 同一提交既有 `hard_core` 又有软失败：只建 `approve_core_landing` 一张单，`waives` 同时列出软失败项（核心级单的展示是软级单的超集）。

### 12.2 `approve_core_landing`（tier D，PROD only）

与 §5.6 同一套建单校验、材料、执行器、撤销、计时与锁序，差异只有：
1. **独立动作名与独立页面标题**「信任核心改动」，单上第一行写：「批准后，此提交改动审批 / 身份 / 落地闸门代码，由落地身份推到 main；之后的审批由新代码处理。」
2. **材料额外字段**（进 `candidate_digest`）：`hard_core_paths`（命中的 §4.2 条目与文件）、`decision_chain:true|false`（是否命中 §4.2 B、C 表或 `approvals*`、`actuation*` 目录）、`trust_review`（见 3）。
3. **信任链复核**：命中 `hard_core` 的任务，标准 spec（§2.8）的异家评审附加固定清单——是否改变谁能批准、批准对象如何展示、令牌如何取得、落地闸门的判定或其旁路；评审结论逐条回答并入 `review.artifact`。缺这一段 → 建单拒绝 `trust_review_missing`。不另加一轮复核（不增加 Codex 工时到每件）。
4. **独立核对入口**：单上给 Gitea 自身的 `M0...R` 比较链接和 `patch_sha256`，并提示「Gitea 页面不经本平台代码渲染」。`decision_chain:true` 时该提示加粗，且页面要求勾选「已在 Gitea 核对」才能点批准（勾选只是 UI 约束，如实写明不是机械保证）。
5. **审批渠道**：批准渠道必须是 Console（`channel=console` 且确认号已核）；chat 渠道拒绝执行（与 §5.6 相同，这里再列一次以防遗漏）。

### 12.3 数量与额度

- 粗算（§4.4）：近 30 天 platform 895 个提交、碰 hard 679 个，平均每天约 22 个碰 hard 的提交。逐提交一张单不可接受。
- **统筹按工作单元压成一个提交再 handin**（handin 前 `git reset --soft <base>` + 一次提交；正文列原提交标题）。每个逻辑单元一张单。统筹估计每天 3–8 张（**未测**，第一周按实数修正）。
- 规则 `max_landings_per_day` 现为 5（PROD `landing:dev` v1），会成为瓶颈：下一版规则由 Owner 签，建议改为 12；规则签名照现行流程，与本节实现分开办。
- 运行时执行者（agentd）的普通任务若命中 `hard_core`，同样走核心级单（不限于统筹提交）。

### 12.4 残余风险的变化

- §11.1「同进程代码无机械隔离」不变。
- 新增：**决策链自改**——一件被批准的决策链提交落地后，后续单的材料由新代码渲染；若它有意或无意改坏了展示，后续批准可能被误导。缓解：12.2 的 4（Gitea 独立核对）与 3（信任链复核）；手推路径有同样的风险（Owner 也不逐行看），所以本节没有使总风险变大。
- §11.5「收益有限」改为：除 `hard_absolute` 外，统筹提交全部走落地，Owner 不再手推 platform main（紧急修复、混合来源 F4 A 例外）。

### 12.5 工时

| 块 | 增量 | 小时 |
|---|---|---:|
| C-3 | 两层 hard、`hard_absolute` 清单与测试、`core` 失败类别 | 3–5 |
| C-5 | `approve_core_landing` 目录与建单校验、`trust_review` 检查、两种 grant 的类别隔离 | 6–9 |
| C-6 | 核心级单的页面：标题、首行说明、Gitea 链接、决策链勾选 | 3–5 |
| C-2 | handin 前压缩为单提交、spec 附加信任链清单 | 2–3 |
| C-7 | PROD 实测加一件核心级单 | 1–3 |
| **合计** | | **15–25** |

核心块合计改为 **119–175 h**。
