# 统筹提交走落地 · 设计 v2（2026-10-28 23:xx 统筹分叉，回应复核 677）

依据：Owner 决定 A（CUT §11.14）；v1 `DESIGN-coordinator-landing-2026-10-29.md`；复核 677（`~/agent-work/codex-work-677/REPORT.md`，8 阻断，其中 B-01..B-06 与本块有关，R-01、R-02、R-05、R-06、R-07 有关）。代码基线 platform main `cb47820d`。本稿**取代 v1**；S6 初稿里的「统筹文档直推通道（S6-7、D2-A）」与 S5 初稿的 S5b 一并作废，由本块实现（677 N-02）。

本稿只定**共同契约**与本块（platform 闭环）；S6 多仓与 S5 放开在本块之后、各自修订（677「统一实施顺序」）。

---

## 0. 677 逐条结论（本块）

| 条 | 结论 | 本稿位置 |
|---|---|---|
| B-01 pin 不是身份 | 采纳：服务端登记 external principal，host→executor/provider/tenant/repo/role 固定，客户端不得覆盖；外部主机只领 pin 给自己的 implement；pin 只在提议时由特定写者设定、不可变 | §1 |
| B-02 硬底线自保护 | 采纳：结构校验独立且总先执行；最小可信边界清单（审批/鉴权、override 与底线实施代码、落地凭据与推送限制、装配、构建入口、依赖清单）列为 hard，普通 grant 永远放不开；修改它走 §3.4 的特殊流程 | §3 |
| B-03 跳过 rule 过宽 | 采纳：三层分离——不可豁免前提、可逐项豁免的软检查、始终生效的全局条件；grant 列明豁免哪几项与实际规模，不再有笼统 skipRule；缺规则明确拒绝 | §3.2、§4.4 |
| B-04 审批-授权-撤销-推送一致性 | 采纳：grant 只由审批执行上下文写入（仿 `server/agentrt_nomerge.go:44`）；完整绑定；以「持 grant 锁提交 `main_intent`」为消费界点；撤销早于消费则不推，晚于消费如实告知「已交给推送」；提交不确定按 `store/nomerge_reconcile.go:28` 读回 | §4 |
| B-05 等待与终态冲突 | 采纳：软底线不再出生即 `failed{floor}`，改为持久 `awaiting_approval`（不占在途位），独立的审批等待上限；六小时上限对它暂停计时；拒绝、过期、撤销、任务取消都有收尾 | §5 |
| B-06 路径集合不等于同一授权对象 | 采纳：区分 A（接受的实现）与 R（待推提交）；先准备 R、在 R 上跑 CI，grant 绑定 `R + M0 + A`；main 前进产生新 R 即重批（第一版不沿用）；保留现有 Replay 的父、血缘、交集、patch-id 检查 | §6 |
| R-01 handin 顺序与恢复 | 采纳：按 task 精确领取的新接口与幂等键；服务端分配 attempt/ref；固定顺序 report → start → computed → persist → submit；续租；超时读回不重领；salvage 与 persist 共用一致性校验 | §2 |
| R-02 漏列接线 | 采纳：迁移、actor/host 登记、事件词表、路由回放、规则（job/envelope/capability）、服务端生成的标准 spec、评审时限由 diff 规模算出，全部列入分块 | §1.3、§2.4、§8 |
| R-05 规则 schema 与额度 | 采纳（共同契约部分）：全租户每日总额度不变；grant 落地照占总额度与在途位；规则版本单调递增，按实际内容编号 | §3.3 |
| R-06 测试能检出错误实现 | 采纳：新增能力测试先有同入口成功对照，再只改一个条件；断言原因、事件、额度、push 次数、最终 refs | §9 |
| R-07 Owner 看到的材料 | 采纳：审批单由服务端生成，绑定完整 diff、路径、A/base、R/M0、规模、硬/软判定、豁免项、验收与评审记录、R 的 CI、未完成项；批准时重验 | §4.5 |

不在本块：B-07（S5 的叶子包论证）、B-08、R-03、R-04（S6）——分别在 S5、S6 修订中回应。

---

## 1. External principal（B-01、R-02）

### 1.1 登记

- 新主机类别 `external`；主机 `coordinator-mbp`，`host_kind = external`（迁移见 §1.3）。登记记录（服务端，Owner 签名的 standing envelope 与岗位规则里列出）固定：`executor = coordinator`、`provider = anthropic`、`tool = claude`、`tenant = dev`、允许的 `repo` 集合（第一版只 `bifrost-platform`）、允许的 `role = implement`。
- 令牌：coordinator 专用 agentd 令牌，只映射到 `coordinator-mbp`（与现有 token→host 映射同机制，`agentrtapi/api.go:244`）。令牌在本机 `~/.config/bifrost/coordinator-agentd.token`（600，不进仓库），可单独吊销。

### 1.2 派活与领取

- 任务提议新增字段 `executor_pin`（取值只有 `external:coordinator`，或空）。**设定权限**：只有统筹线程的提议写者（`thread:local_…` 且其 Writer 带 `pin_external` 能力；由 Owner 在 capability 规则里授予）能设；Console 目标、计划者、执行者产生的任务一律不能设。设定后**不可变**；要改指派只能取消该任务并重新提议（审计留在旧任务上）。
- 服务端派活：
  - external 主机**只**领 `executor_pin = external:coordinator` 且 `role = implement` 且 repo 在其允许集合内的任务；verify、review、plan、brief、gate 等一律不领。
  - 普通主机**永不**领带 pin 的任务。
  - claim 请求里的 `tools[]` 对 external 主机**不采信**：服务端用登记的 executor/provider/tool 替换后再与岗位候选匹配；客户端伪报其他 tools 时拒绝（零尝试），不是静默改写。
  - verify/review 子任务不继承 pin，仍走原路由；实现方 provider 记为登记值 `anthropic`，评审路由排除 anthropic。
- 评审方第一版固定 **Codex（openai）**：现有 Cursor 候选的 provider 标签是 `cursor-mix`，不能证明实际模型非 anthropic（677 B-01）。Cursor 等能验证实际 provider 后再纳入。
- 混合来源：第一版只接收「统筹会话亲手写的实现」。统筹提交若包含其他执行者（如 Codex 派活）产出的改动，在提议时列出参与 provider 集合，评审排除集合内全部 provider；集合里同时有 anthropic 与 openai 时，第一版不走本通道（无可用的异家评审方），回到 Owner 手推。

### 1.3 Schema 与规则接线（R-02）

- 迁移 `0010`（agentrt-migrate，PROD 走 Owner 批的 DDL 单）：`host.host_kind` 的 CHECK 加 `external`；`task` 加 `executor_pin text NULL CHECK (executor_pin IN ('external:coordinator'))`；不改 `actor.tool` 的闭合集合（coordinator 用 `claude`）。旧版本兼容：列可空、旧代码不读；先发迁移，再发读它的代码。
- 词表：`task_proposed` 正文加 `executor_pin`；新增 host 登记事件字段 `host_kind=external`；路由 fingerprint / replay 读入 pin（`store/route.go`、路由输入回放）。
- presence：external 主机不心跳、不进「主机失联」告警；Console 主机列表标「external」。
- 规则（需 Owner 签）：`standing-envelope:dev` 加 `coordinator-mbp`；`job:implementer` 加候选 `external:coordinator/anthropic/*`；capability 事实加 `pin_external` 给统筹线程写者。core work 的 `only author_core` 约束（`store/route.go:296`）对 coordinator 适用同样判断：统筹提交若触及 core 路径，coordinator 需有 `author_core`（规则里明确授予）。

---

## 2. Handin（R-01、R-02）

### 2.1 服务端接口

- `POST /agentrt/claim/pinned`（agentd 角色，只对 external 主机开放）：请求带 `task_id` 与幂等键；服务端核对 pin、repo、role、任务状态 ready，返回服务端分配的 `attempt_id`、`attempt_no`、`ref = refs/heads/agent/<task>/a<n>`、`epoch`。同一幂等键重放返回同一结果；不是 pin 给本主机的任务返回 403 且不产生尝试。
- 其余步骤沿用 `POST /attempts/{id}/{action}`：`start`、`heartbeat`、`computed`（附报告 artifact）、`persist`（ref、commit）、`submit`。

### 2.2 调用顺序

1. 统筹在本机准备提交：父提交 = 任务 `base_commit`；提交信息含唯一 `Agentrt-Task: <task>` 与 `Change-Id`（Replay 的血缘检查需要，`landinggit/replay.go:46`）。**此后不得 amend。**
2. `claim/pinned` → 拿到 attempt 与 ref。
3. 上传报告 artifact（`kind report`）。
4. `start` → `computed`（引用报告）。
5. 以统筹本人身份把提交推到服务端分配的 ref（`agent/**` 未保护，code write 即可）。
6. `persist`（ref、commit）→ `submit`。
- 续租：脚本在 2–6 之间每 60 秒 `heartbeat`（`LeaseTTL=120s`、`Grace=15m`，`store/kernel.go:43`）。
- 恢复：任一步超时，先 `GET /attempts/{id}` 读回状态，按读回结果继续；不盲目重领、不推第二个提交。失租后不再续用旧尝试，重新 `claim/pinned` 得到 a<n+1> 与新 ref。

### 2.3 persist 的一致性校验（与 salvage 共用）

服务端在锁内：读 Gitea 核对 ref 指向所报 commit、commit 只有一个父且等于任务 base、单提交、提交信息血缘尾注与任务一致、repo 在 principal 允许集合内。任一不符拒绝。**salvage 路径（`store/attempt.go` 的丢租回收）调用同一校验**，不能从旧入口绕过父提交检查。验收与评审始终钉这个 A；ref 之后被移动不影响已钉的 A。

### 2.4 标准 spec 与评审时限

- handin 任务的 spec 由服务端标准流程生成（`store/repos.go` 的 Verify 清单 + 统筹写的任务正文），上传方不能删改 verify 命令。
- 评审时限：自动生成 review 任务时由服务端按 A 的 diff 规模计算（`max(1h, 每 300 行 +30m)`，上限 3h），受预算规则约束；不依赖原提议的 `hard_limit_s` 继承（`proposeChecker` 现不传）。

---

## 3. 硬底线与软检查（B-02、B-03、R-05）

### 3.1 三层

1. **不可豁免层**（总先执行，任何 grant 无效）：
   - 结构校验（独立于路径政策）：非常规文件模式（符号链接、子模块、可执行位变化无内容）、二进制、空路径、无法解析的 diff（现 `FloorViolation` 的结构部分，拆出为 `StructuralViolation`）。
   - **最小可信边界**（hard paths，见 3.4 清单）。
   - 全局前提：live 开关、仓库停止（B6）、有效规则存在且在期、规则含该 repo、mode、before_enable、stale、result（单提交）、history、terminal、dependencies。缺规则明确返回 `rule`，不取旧版、不空指针。
2. **可逐项豁免层**（grant 列明豁免哪几项才能过）：
   - `floor_soft`：软底线路径（现 `LandingFloor` 中不属于 hard 的部分，例如 `api/**` 业务代码）；
   - `rule_paths`：不在 allow 内的路径；
   - `presentation`：纯展示判定；
   - `size`：单件文件数与行数上限。
3. **始终生效层**：全租户每日总额度（grant 落地照占）、仓库在途上限、第二道闸其余检查、CI 绿。

### 3.2 grant 只豁免它列出的项

- 资格判定把软检查的失败汇总成一个集合 `soft_refusals ⊆ {floor_soft, rule_paths, presentation, size}`，连同实际文件数、行数写进 `awaiting_approval`（§5）与审批单；grant 的 `waives` 必须**覆盖**当时的集合，且只对绑定的 R 生效。
- 规则在 grant 之后收紧：未消费的 grant 不受新规则的软检查影响（Owner 已逐项看过），但新规则若让 repo 不在规则内、或规则失效，属于不可豁免层，直接拒。

### 3.3 额度与版本（R-05 的共同部分）

- 「全租户每日总额度」是唯一的日额度维度；以后可选加每仓单件上限、每仓在途上限，只能叠加、不能替代。grant 落地计入总额度。
- 规则版本只单调递增，按实际上线内容编号，不绑定 S5/S6 名称；schema 新字段有默认值与规范序列化，`landingTightens` 明确旧版兼容。共享规则层（`rules/landing.go`、`landing/eligibility.go`、`landing/protocol.go`、store gates/facts）由一条变更线合入。

### 3.4 最小可信边界清单（hard paths，第一版）

platform：
- 审批与鉴权：`api/internal/approvals/**`、`approvalhome/**`、`approvalnotify/**`、`actions/**`（含 `tier.go` 分级）、`actuation/**`、`actuationpolicy/**`、`server/auth*.go`、`server/*token*.go`。
- 落地本身与底线实施：`api/internal/agentrt/rules/**`、`agentrt/landing/**`、`agentrt/landinggit/**`、`agentrt/store/landing*.go`、`agentrt/store/*grant*.go`（本块新增）、`agentrt/controller/landing*.go`、`server/agentrt_landing*.go`、`server/agentrt_grant*.go`（本块新增）、`agentrt/agentrtapi/api.go` 中 claim/attempt 路由文件。
- 落地凭据与推送限制、装配：`server/server.go`、`server/agentrt_wire.go`、`api/cmd/**`。
- 构建入口与依赖清单：`go.mod`、`go.sum`、任意深度 `package.json`、`package-lock.json`、`console/vite.config.*`、`console/index.html`、`Dockerfile*`、`Makefile`、`.github/**`、`.husky/**`。
- 秘密与环境：`.env*`。
infra（S6 接入后才相关，第一版全部 hard）：`k8s/**` 全部、`agent-config/**` 中治理层（规则、preflight、hooks、parity）、`scripts/gitea/**`、`scripts/release/**`。

修改 hard 清单所列文件：**不走本通道**，仍由 Owner 手推（现状），并要求该提交带 Codex 复核记录。hard 清单本身写在 `rules/landing.go`（hard paths 常量）且该文件在清单内，所以 grant 通道改不了自己的边界。以后若要让部分 hard 文件也能经审批落地，需单独设计「双人或冷却期」的特殊流程，Owner 另行决定（§10 的 F3）。

---

## 4. Grant（B-04、R-07）

### 4.1 产生

- 新 D 级动作 `approve_guardrail_landing`（actions catalog，tier D，PROD only，参数 schema 闭合）。**统筹不手填授权内容**：统筹调 `request_action` 时只给 `{env: prod, task, attempt}`；服务端在建单时从 `awaiting_approval` 记录生成完整参数与单据材料（§4.5），参数哈希入单。
- 执行：仅在审批执行上下文里（`actions.CreateAttemptFrom(ctx)`，仿 `server/agentrt_nomerge.go:44`）调用 `store.GrantLanding`：在仓库落地流锁内重验——awaiting 记录仍是同一个 `(task, attempt, A, R, M0, soft_refusals, diff 摘要)`、R 的 CI 仍为该次绿、规则仍有效——一致则写 `landing_grant` 记录，否则执行失败（单显示失败原因，不写 grant）。客户端拿着 approval_id 不能自己写 grant。
- `landing_grant` 正文：`{v, grant_id, approval_id, params_hash, env, tenant, repo, task, attempt, A, base, R, M0, diff_digest, paths, changed_files, changed_lines, waives[], granted_at, expires_at}`；`expires_at = 批准时间 + 24h`（从真实批准时刻算，重复执行审批不刷新）。controller 身份写入，校验器闭合。
- 提交不确定：COMMIT 传输错误按 `store/nomerge_reconcile.go:28` 的方式在新事务读回 grant 是否存在，返回 `actions.Uncertain`；不重试写入。

### 4.2 消费

- 领取资格与第二道闸都读「对该 `(task, attempt, R, M0)` 有效、未撤销、未过期、未消费」的 grant。
- **消费界点 = 第二道闸在持仓库落地流锁的同一事务里写 `main_intent`**，同事务写 `landing_grant_consumed{grant_id, op, intent_seq}`。一个 grant 只能被消费一次。
- 过期在领取与第二道闸各查一次（第二道闸用锁内的决定时刻）。

### 4.3 撤销

- 新动作 `revoke_guardrail_landing`（tier D 不必要，tier C 由 Owner 在 Console 点），执行时在同一把仓库落地流锁内：若 grant 未消费，写 `landing_grant_revoked`，之后任何闸都不放行；若已消费，**不写撤销**，执行结果明确返回「已交给推送（op …），不能保证撤销；落地后按正常对账，如需撤回请另做 revert」。
- 不承诺「Git 接收前都可撤销」；需要的话另行设计接收端 fencing（不在本块）。

### 4.4 一致性要点

- 不读审批的 `approved` 状态做授权（批准执行后状态是 `executed`）；授权事实只来自 `landing_grant` 记录。
- 审批文件锁与 PG 锁不同：grant 写入、消费、撤销都只在 PG 仓库落地流锁内判定；审批侧只负责触发执行。

### 4.5 Owner 在审批单上看到的（R-07）

服务端生成、批准时重验，任何一项变化单即失效（执行失败）：
- 任务、mission、统筹线程；A 与 base；R 与 M0（main 前进则需重批）。
- 完整变更路径列表与每个文件的增删行；完整 diff 的链接（Console 的 diff 页，按 R）。
- 硬/软判定：命中的软检查项与原因（例如「api/internal/agentrt/store/close.go 属 floor_soft」「行数 812 > 300」）；**hard 命中则不会出现单**。
- 确定性验收结果、异家评审记录（评审方、结论、评审的是 A；R 与 A 的 patch-id 是否一致）、R 的最新 CI（run 名、结果）。
- 当日总额度已用 / 上限（批准时刻快照，注明「最终以推送时为准」）。
- 有效期（到何时）、撤销入口；执行后显示「已授予本次落地权限」，实际 landed 另显示，不混为一谈。
- approval ID 与 grant ID 进入最终 `main_intent` 与落地提交的说明（`Landed-By` 之外加 `Landing-Grant: <id>`）。

---

## 5. 软底线等待（B-05）

- 资格判定遇到「只有软检查失败」时，**不再**走 `unclaimedEnd` 写出生即 `failed{floor}`；改为写 `awaiting_approval{task, attempt, A, soft_refusals, changed_files, changed_lines, at}`（每 `(task, attempt)` 一条，内容变化才追加）。hard 或结构失败仍出生即 `failed{floor}`（终态不变）。
- `awaiting_approval` **不占在途位**、不开操作（k 不递增）。
- 时限：
  - 首次领取窗口（六小时）对 awaiting 根**暂停计时**；审批等待有独立上限 **72 小时**（与问题卡 TTL 一致），到期写 `failed{approval_expired}`（可由 Owner 用「再试一次」重开）。
  - grant 写入后，执行预算（六小时 / 8 次）**从 grant 时刻起算**，累计重放次数不清零。
- 准备 R（§6）发生在 awaiting 期间：落地循环对 awaiting 根照常做准备与 CI（只为产生 R 与 CI 证据），不推；准备结果写进 awaiting 的后继记录，单据据此生成。
- 收尾：Owner 拒单 → `failed{declined}`（复用 B3 的「不合」语义）；grant 过期 → 回到 awaiting（不自动新单，统筹可再申请）；任务被取消 / mission 停止 → `failed{stale}`；B4 收尾分类把 awaiting 归为「未了结（等审批）」，mission 保持 active。
- 旧 `failed{floor}` 记录不批量复活；需要的走新任务。
- B3：awaiting 不发问题卡（审批单就是 Owner 的出口）；状态接口与目标详情显示「等你批 D 级单 #n」与单号链接。

---

## 6. 重放与授权对象（B-06）

- 定义：**A** = 被接受的实现提交（handin 的 commit）；**R** = 在当时 main（M0）上重放出的待推提交。
- 流程：awaiting 期间落地循环准备 R（现有 Replay：父、血缘、文件交集、patch-id 检查全部保留）、推 `land/prod/<task>/<k>`、等 R 的 CI；grant 绑定 `(A, R, M0)`。
- 推送前 main 前进（M0 变）→ 产生新的 R′ → **原 grant 不适用**，回到 awaiting，生成新单（显示与上一单的差别）。第一版不做「同补丁免重批」。
- 现有重放分类（conflict / overlap / patch_changed）照旧；任何一种都不能用旧 grant 推。
- 「准备与 CI」不需要 grant；「推 main」才需要。两种资格在代码里分开（准备资格不含软检查，推送资格含软检查 + grant）。

---

## 7. 不变的安全边界

- 「只有落地身份推 main」不变；统筹令牌只有 claim 角色、只领 pin 给自己的 implement。
- D 级审批只在 PROD（ops.bifrost.lan）；STG 只演练规则内路径，不在 STG 建 grant 单冒充链路。
- infra 不在本块的 grant 支持集合内（S6 之后另定）。

---

## 8. 分块与工时（单人有效工时）

| 块 | 内容 | 小时 | 与 S6 准备 |
|---|---|---|---|
| C-1 | external principal：迁移 0010、host/actor 登记、`executor_pin`（提议、权限、不可变）、派活与 claim 的服务端约束、路由回放、presence/UI、规则正文（envelope/job/capability） | 16–22 | 串行（store/route、vocab） |
| C-2 | handin：`claim/pinned`、服务端分配 ref、persist/salvage 共用一致性校验、标准 spec、评审时限、`handin.sh`（续租、读回恢复） | 12–16 | 可并行 |
| C-3 | 三层检查：`StructuralViolation` 拆出、hard paths 常量与清单、软检查集合化、缺规则拒绝 | 8–12 | **串行**（rules/landing.go、eligibility.go） |
| C-4 | awaiting_approval：协议记录与转移、首次交接与六小时暂停、72 小时到期、B4 分类与 mission 保持、B3 不发卡、状态接口 | 10–14 | **串行**（protocol.go、store gates） |
| C-5 | grant：两个动作（catalog、参数 schema、执行器装配、PROD home 检查）、`landing_grant/consumed/revoked` 记录与校验、锁内消费、读回恢复、`Landing-Grant` 尾注 | 14–20 | **串行**（landing_live.go、protocol.go） |
| C-6 | 准备与推送资格分离、R 绑定、M0 变化重批 | 6–10 | 串行 |
| C-7 | Console：审批单材料页（服务端生成）、目标详情「等 D 级单」、grant 状态 | 6–9 | 可并行 |
| C-8 | 测试（§9 全部）与 PROD 实测（规则内一件、grant 一件、撤销一次） | 12–18 | — |
| 合计 | | **84–121** | |

对照 677 的 68–100：多出的部分来自 awaiting 状态机与 B3/B4 联动（C-4 单列）、准备/推送资格分离（C-6）、`claim/pinned` 新接口。若 Owner 选第一版**不做撤销动作**（只靠 24 小时过期），C-5 可减 3–4 小时。

实施顺序（677「统一实施顺序」）：C-1 → C-2（规则内 handin 先走通：统筹提交改 console 展示类，验证 external principal 与异家评审）→ C-3 → C-4 → C-6 → C-5 → C-7 → C-8。S6 的 ci-infra 与 Gitea 探针准备可与 C-2、C-7 并行；S6 的多仓改造与 S5 的规则修改在本块合入之后，基于本块的规则层继续。

---

## 9. 测试清单（能检出错误实现，677 R-06）

每个新增拒绝测试先有**同入口、同仓库、同有效授权的成功对照**，再只改一个条件；断言拒绝原因、写入的事件、额度、push 调用次数与最终 refs。

外部身份：
1. pin 任务由 coordinator 经 `claim/pinned` 领到并交付成功（对照）。
2. 普通 agentd 令牌调 `claim/pinned` → 403，零尝试。
3. coordinator 令牌经通用 `/claim` 伪报 `exec:codex/openai` → 拒绝，零尝试。
4. coordinator 令牌领别人的 pin 任务（另一任务 id）→ 403。
5. coordinator 令牌领 verify / review / plan 任务 → 拒绝；该任务随后由普通执行者领走。
6. 普通主机永不领到 pin 任务（派活 1000 次随机顺序）。
7. 非统筹写者提议带 pin 的任务 → 拒绝；改已提议任务的 pin → 拒绝。
8. 评审任务的执行者 provider 不是 anthropic（对照 + 伪造 provider 记录的负例）。

handin：
9. 两件 pin 任务，`claim/pinned` 只领指定那件。
10. 第二次尝试使用服务端分配的 `a2` ref；脚本写死 `a1` 推送 → persist 拒绝。
11. 缺报告、缺 computed、缺血缘尾注，分别拒绝。
12. persist 报的 commit 与 ref 不符、父不等于 base、merge 提交、多提交、repo 不在允许集合 → 拒绝；salvage 同样拒绝。
13. persist 超时后读回再继续，不产生第二次提交；失租后旧尝试不可续用。

三层检查：
14. hard 路径（如 `rules/landing.go`、`go.mod`、`.env.x`）命中 → 出生即 `failed{floor}`，不出现审批单；即使有伪造的 grant 记录也不放行。
15. 结构违例（符号链接、二进制）→ 同上。
16. 有效 grant 下分别：规则过期、规则缺失、repo 移出规则、live 关闭、仓库停止、额度已满、mission 停止 → 各自拒绝，原因正确，零 push。
17. grant 的 waives 不覆盖实际软失败集合 → 不放行。

grant：
18. 直接写 `landing_grant` 事件（非审批执行上下文、operator 或 agentd 身份）→ 校验器拒绝。
19. 已批准的另一种 action 的单、参数哈希不符、跨 env / repo / task / attempt 重用 → 执行失败，不写 grant。
20. 审批重复执行只产生一份 grant、不刷新 `expires_at`。
21. 两连接：撤销先提交 → 第二道闸拒绝，零 push；`main_intent` 先提交 → 撤销返回「已交给推送」，不写撤销。
22. 卡在 grant 写入的 COMMIT 不确定、`main_intent` 提交前后、push 响应丢失，各自读回与对账一致。
23. 24 小时边界：领取时有效、第二道闸时已过期 → 拒绝。

等待与重放：
24. 软失败 → awaiting（不占在途位）→ 批准 → 落地完整流程。
25. awaiting 超过 6 小时未批不被 `SettleUnclaimed` 终结；72 小时到期 → `failed{approval_expired}`。
26. 重启后 awaiting 与 grant 状态从流重建一致。
27. 旧 `failed{floor}` 不被误复活。
28. main 前进产生新 R → 旧 grant 不适用，回到 awaiting；同路径不同内容的 A 不能用旧单。
29. B4：awaiting 根让 mission 保持 active；拒单后 mission 按处置收尾。

---

## 10. 仍需 Owner 决定

E1–E4 按 677 推荐收口：**E1 = A**（独立 `coordinator-mbp` 主机与令牌，B-01 的服务端约束）；**E2 = A**（24 小时、从真实批准时刻起、最终消费也验、不可刷新）；**E3 = 扩大后的最小可信边界**（§3.4）；**E4 = A**（一个接受的单提交一张单，绑定 R/M0）。

仍需 Owner 定的：

- **F1 外部执行者的数据库落法**（新增列与约束属架构级）：
  - A 迁移 0010（`host_kind` 加 external、`task.executor_pin` 列，数据库约束强制）——**推荐**，约束在库里、不依赖代码自觉；需批一次 PROD DDL。
  - B 不加列：pin 只写在 `task_proposed` 事件正文，派活时从事件读——不需 DDL，但每个读路径都要记得过滤，漏一处即越权。
- **F2 撤销**：
  - A 做 `revoke_guardrail_landing`（消费前可撤，消费后如实告知）——**推荐**。
  - B 第一版不做撤销，只靠 24 小时过期与「关 live」——省 3–4 小时。
- **F3 hard 清单内文件以后能否经审批落地**：
  - A 永远手推（第一版即此）——**推荐**先这样跑一段。
  - B 以后另设计「审批 + 冷却期（如 24 小时公示）」的特殊流程。
- **F4 混合来源提交**（统筹提交里含 Codex 产出的改动）：
  - A 第一版不走本通道，回到 Owner 手推——**推荐**。
  - B 允许，评审排除全部参与 provider；anthropic 与 openai 同时参与时改用 Cursor（需先能验证其实际 provider）。
