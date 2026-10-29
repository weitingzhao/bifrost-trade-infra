# 统筹提交走落地（「过渡期结束」核心块，设计稿 v1，2026-10-28 22:3x 统筹）

依据：Owner 决定 A（CUT §11.14）。S5、S6 初稿统计：Owner 手推的提交里，platform 73.3% 碰治理底线包、infra 61.8% 只改文档，绝大多数是统筹会话自己写的提交；落地现在只搬运运行时执行者产出的、被接受的尝试。目标：统筹的提交也成为被接受的尝试，从而由落地身份推 main；碰底线的，逐件经 Owner 的 D 级单放行。安全前提「只有落地身份推 main」不变。

## 1. 现状（代码事实）

- 尝试只由 agentd 经 `POST /agentrt/attempts/{id}/{action}`（claim → start → heartbeat → persist → submit）产生，`api/internal/agentrt/agentrtapi/api.go:144-146`；令牌角色 `claim`（agentd）。
- 领取派活按岗位规则 `job:implementer` 的候选（executor/provider/model）与主机登记，`route_json` 例：`implementer/exec:claude/anthropic/*`。
- 验收：确定性验收 + 异家评审（评审方 provider 必须与实现方不同），通过后任务 `accepted`。
- 落地：`LandingCandidates` 读 accepted 的 implement 任务；`EligibleToClaim` 依次判 mode、before_enable、stale（goal 类须有产出计划）、result（单提交在 base 上）、history、terminal、floor、dependencies、rule（路径、纯展示、行数与文件数上限）、limit。
- 外部工作（`store/externalwork.go`）只登记与观察，不产生尝试。

## 2. 设计

### 2.1 统筹作为外部执行者

- 新执行者种类 `external`：主机 `coordinator-mbp`（登记在运行时主机表，类别 external，不跑 agentd 进程，没有心跳循环）；岗位候选 `implementer/external:coordinator/anthropic/*`。
- 只有显式指派的任务才派给它：任务字段 `executor_pin = "external:coordinator"`（新增于任务提议，非空时路由只取这一候选，其余执行者不领；为空保持现状）。避免运行时把普通任务派给统筹，也避免执行者领走统筹的提交。
- 交付工具 `scripts/agent-host/handin.sh <task> <branch>`（统筹本机）：用 coordinator 主机的 agentd 令牌（`~/.config/bifrost/coordinator-agentd.token`，600，不进仓库），依次 claim（只认 pin 给自己的任务）→ start → persist（`pushed_ref = refs/heads/agent/<task>/a1`、`pushed_commit`，与 agentd 同格式）→ submit。分支由统筹本人身份推到 Gitea 的 `agent/**`（未保护，现有 code write 即可）。
- 一致性：persist 前服务端读 Gitea 核对 ref 指向 commit、commit 的父等于任务 base、单提交（与 `SingleCommit` 同判据），不符拒绝。尝试的 `executor` 记 `external:coordinator`，provider `anthropic`。

### 2.2 验收与评审

- 确定性验收照常（`store/repos.go` 的 Verify 命令在 06 的验收机上跑）。
- 异家评审：实现方 provider = anthropic，评审路由排除 anthropic（现有规则即如此），由 codex 或 cursor 执行者评审。评审 spec 写明「这是统筹提交，按任务 spec 与 diff 审」。
- 统筹提交多为大改动（数百至数千行）：评审 `hard_limit_s` 按 diff 规模给（新增：proposal 可设，上限 3 小时）。

### 2.3 落地：两条路

- **规则内**：路径、行数都在当前规则内的统筹提交，与运行时任务完全同路（v1 规则只放 console 展示类；S5a、S6 定稿后扩大）。
- **底线放行（D 级单）**：floor 或 rule 拒绝时，任务停在 `unclaimed:floor` / `unclaimed:rule`（已可见，`df81a4f4`）。统筹建 D 级单 `approve_guardrail_landing`：参数 `{env: prod, task, attempt, commit, base, paths_digest, changed_lines, reason}`；Owner 在 ops.bifrost.lan 批。执行动作只做一件事：在仓库落地流写 `landing_override{task, attempt, commit, approval_id, paths_digest}`（controller 写入，校验 approval 已批准、参数与尝试一致）。
- `EligibleToClaim` 新增：存在与 `(task, attempt, commit)` 完全一致、未过期（批准后 24 小时）的 override 时，**跳过 floor 与 rule 两条**，其余（mode、before_enable、stale、result、history、terminal、dependencies、limit）照判；第二道闸同样在锁内重读 override。override 不跨提交：任何重放（main 前进后的 k+1）产生新的 R，需要新单——除非 R 与原 commit 的 tree 差异只来自 main 前进（不重签：§2.4）。
- 每日额度：override 落地照计入 `max_landings_per_day`；Owner 可在单上看到「今天第 n 件」。

### 2.4 main 前进后的重放

- 统筹提交的 base 常落后 main。现有落地对 k 用 `prepared` 在当时的 main 上重放（cherry-pick）。重放成功、改动路径集合与 `paths_digest` 一致时，override 仍适用（审的是同一组路径上的同一份补丁）；重放冲突则 `failed{stale}`，统筹在新 main 上重做并提新任务。

### 2.5 不变的安全边界

- D10 相关路径（`daemon-scale-zero`、`daemon-observe-safe`）、Secret、RBAC、NetworkPolicy、`.env*`、`go.mod/go.sum` 的变更：override 也不放（`LandingFloorHard`，新的硬底线子集，规则与 D 级单都放不开），仍由 Owner 手推或走现有 PROD 发布单。
- 统筹令牌只有 claim 角色、只领 pin 给自己的任务；不能批审批、不能写落地流的其他记录。
- infra 接入（S6）之前，override 只对 platform 生效。

## 3. 对 S5、S6 的影响

- S5：D2 选 B（底线经 D 级单由落地身份推）由本块实现；S5a（console 数据层 + 12 个 api 叶子包放进第 2 版规则）保留，用来减少 D 级单数量。S5b 并入本块。
- S6：D2（统筹文档通道）由本块覆盖（infra 的统筹文档作为统筹提交走规则内路径）；S6-1 多仓库化、S6-3 ci-infra 是前提，S6-7 取消。
- B5：统筹提交也走落地后，main 上的非落地提交大幅减少，B5 的 `stg_blocked`（整个 P 归属）不再常态化，B5 的价值随之成立。

## 4. 分块与工时（单人有效工时，未经复核）

| 块 | 内容 | 小时 |
|---|---|---|
| C-1 | 外部执行者：主机类别、`executor_pin`、路由只取 pin、claim 只给 pin 主机 | 6–9 |
| C-2 | handin 工具与服务端 persist 一致性核对（ref、父、单提交） | 5–8 |
| C-3 | 评审时限按规模、评审 spec 模板 | 2–3 |
| C-4 | `approve_guardrail_landing` 动作（D 级）、`landing_override` 记录与校验 | 6–9 |
| C-5 | 资格与第二道闸读 override、`LandingFloorHard`、重放后路径一致判定 | 6–9 |
| C-6 | Console：落地状态与目标详情显示「等 D 级单」与单号链接 | 3–5 |
| C-7 | 测试（旧代码上会红）与 PROD 实测一次（规则内一件、override 一件） | 5–8 |
| 合计 | | 33–51 |

## 5. 需要 Owner 决定的点

- **E1 统筹的执行者身份**：A 独立主机 `coordinator-mbp` 与专用 agentd 令牌（推荐，可单独吊销、审计清楚）；B 复用本机 `mbp-dev` 主机。
- **E2 override 的有效期**：A 批准后 24 小时内领取（推荐）；B 不设期限，直到该尝试终结。
- **E3 硬底线子集**：A 照 §2.5 列表（推荐）；B 再加 `api/internal/approvals/**`（审批代码也不许经 override 落地）；C 不设硬底线。
- **E4 一件 D 级单的粒度**：A 一个提交一张单（推荐）；B 一个统筹工作单元（多提交）一张单——需要多提交落地，超出现有单提交前提。

## 6. 测试清单（旧代码上必须红）

1. 未 pin 的任务不派给 coordinator；pin 的任务只有 coordinator 能 claim。
2. persist 的 ref 不指向所报 commit、父不等于 base、多提交：拒绝。
3. 实现方 anthropic 的尝试不被 anthropic 评审。
4. floor 拒绝的统筹提交停在 `unclaimed:floor`；有一致的 override 后被领取；override 的 commit、attempt 或 paths_digest 不一致：不领。
5. `LandingFloorHard` 路径：有 override 也不领。
6. override 过期后不领；第二道闸在锁内重读 override，批准撤销后不推。
7. main 前进后重放成功且路径一致：override 仍适用；路径集合变化：不适用。
8. override 落地计入当日额度。
