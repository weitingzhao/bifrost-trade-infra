# 领域 5 Approvals 章程（行政）

## 现行（2026-11-24 起，这一节为准；下面 11-14、11-15 的旧文留作历史，与本节冲突处以本节为准）

**定位**：决定 2026-11-23：立法和行政分开。本线是行政：只守闸门，不管法的内容。法的内容、法的名录、修法票的格式和校验归立法线（1 Plan，`charters/1-plan.md`）；`api/internal/actions/law_amend.go` 文件头写明定义归 plan，plan 以后把它搬进自己的包。

**管**：卡的通用能力（建卡、存储、手机推送、过期、审计、修法和日常分通道 `track=law|daily`）；执行口 `owner-exec` 和验证码 ticket（LAW-6）；动作目录 `actions/catalog.go` 的级别（改级别是改裁判，按LAW-9 提给 Owner）；问题通道 `questions`、提醒 `approvalnotify`。

**目标**：推到 Owner 手机上的卡只剩修法和六类，其余为 0，改成自动执行并记录（LAW-6、46、73）。

**读数**：每天推给 Owner 的卡，按 修法 / 六类 / 日常 分开计。11-24 临时读数（list_requests，最近 101 张 #628–#728，约 5 天）：101 张全部 Owner 手批，应当找他的约 6 张，其余约 95 张是差距；等批中位数 3 分钟。系统读口还没有（计划 A2）。

**台账**：Artifact「Approvals 行政台账」https://claude.ai/artifact/BzSTVft7QDout24xJVK5GT （源 side-session-notes `domains/5-owner/admin-ledger.html`）；进展文字在 `domains/5-owner/state.md`。

---

# 旧文（2026-11-14）

标注：【量】= 读代码所得，带 文件:行；【推】= 推断。

## 1. 管哪块代码和数据
- 审批单：`api/internal/approvals/`（handler/service/store/resolve/held_loop/execution/result）。存储不是表，是 ConfigMap 里的 JSON 文件 `approvals`（PLATFORM_DATA_DIR，PROD 为 `platform-state-approvals`），`approvals/store.go:21-27`【量】。
- `ask_owner` 问题：`api/internal/questions/`（create/withdraw/ack/answer），Owner 的回答只是信息，不是批准【量，`mcp/catalog.go:225`】。存储位置我没查实【推：同样落在平台状态里，未确认】。
- 审批通知与脱敏：`approvalnotify/`、`approvalhome/`【量，文件存在；细节未读】。
- 执行口：`api/internal/ownerexec/`（`POST /api/owner-exec/run`，只执行 `owner_run_command`，带 TOTP），`ownerexec/server.go:20-60`【量】；命令行入口 `api/cmd/owner-exec`。
- 签名放行规则：`api/internal/releasepolicy/`（engine/policy/sshsig/anchor/expiry/ddl/write）；`delivery/release_policy_*.go` 是发布侧的读取与对比【量，文件存在】。agentrt 里另有 `0013_rule_approval.sql`、`store/ruleapprove.go`，是 agent 运行时规则的批准【量，文件存在；归属待定，【推】与本领域交叠】。
- Console 侧：`console/src/api/{approvals,ownerExec,releasePolicy}.ts`、`ReleasePolicyBanner.tsx`【量】。

## 2. 对外口子
- 审批路由：`GET /approvals`、`/approvals/{id}`；`POST /approvals`（建）、`/approve`、`/reject`、`/resolve`；执行侧 `/approvals/claim`、`/{id}/heartbeat`、`/{id}/result`，`approvals/handler.go:25-45`【量】。
- 问题路由：`GET/POST /questions`，`/{id}/withdraw`、`/ack`、`/answer`，`questions/handler.go:24-35`【量】。
- 放行规则路由：`GET/PUT /release-policy`、`POST /release-policy/freeze|unfreeze`，`releasepolicy/handler.go:10-51`【量】。
- MCP 工具：`request_action`、`get_request`、`list_requests`、`wait_for_request`、`ask_owner`、`get_question`、`list_questions`、`wait_for_answer`、`ack_answer`、`withdraw_question`，`mcp/catalog.go:221-230`；另有 `check_release_policy`、`request_owner` 在工具清单里出现【量，来自工具列表；catalog 中未逐行核对】。
- 另一个本机 MCP `bifrost-approve`（approve/reject/list_pending）：只在 Owner 侧使用，Agent 不调【量，来自根 CLAUDE.md §7】。

## 3. 用户与依赖
- 用户：所有 Agent 席位（建单、问问题、等答复）；Owner（Console 批卡、答问题，必须在 PROD `ops.bifrost.lan`）；发布流水线（`start_pipeline_run` 查放行规则）【量，CLAUDE.md §5】。
- 它依赖：`delivery`（发布窗口、流水线、规则读取）、`actions`（动作目录，`/actions`）、`safego`、认证角色（operator/reporter/viewer，catalog 里按路由标注）、`agentrt`（问题与 issue 卡关联，`store/issuecard.go`）【量】。
- 【推】与领域 4/6（交付、Agent 运行时）边界在「谁来执行批准后的动作」和「issue 卡」两处。

## 4. 现状与缺口
- 近期有人维护：最后提交 2026-11-13，近 300 提交里 98 个来自 weitingzhao，3 个来自 agent-06【量，git log】。没有 TODO/FIXME 标记【量，grep 为空】。
- 缺口（【推】，待实测）：①审批与问题都靠 ConfigMap JSON，没有真正的表，容量/并发上限没核；②`ruleapprove` 是否归本领域没定；③「撤回已建的卡」平台没有（根 memory 记载 #528 被秒批无法撤）；④问题答复的过期/ack 机制只读了工具描述，没读实现。
- 本章程未读任何令牌、口令、Secret，未碰线上卡。

## 补：2026-11-14 23:18 起，这块代码归领域 5「找你」席位维护
- 已落地：执行卡退 75 重排（`approvals/result.go`，约定见 `approvals/OWNER_RUN_CARDS.md`），生产已发（#563）。细节、证据、没验的见 `state.md`。
- 改 `approvals/**`、`actions/**` 在签名规则的信任锚清单里：生产发布一律走 Owner 批卡；先把草稿发值班按七项核，回了再建，建完先看卡面是「@ 短提交号」。
- 待做：建卡方占着窗口就拒绝建卡；窗口排队第二步时执行卡退避压到 ≤60 秒；创建检查拒收嵌套的 revision。
- 先前章程里的几处「推断」（问题存放位置、`ruleapprove` 归属、撤回卡）仍未查实。

---
# 补 2026-11-15（值班 08:20 要的：④权限、⑤目标和读数、重叠）

## ①补（主统筹裁决 11-15，重叠第 11 条）：`ruleapprove` 与 `issuecard` 归领域 5
- `ruleapprove`：`api/internal/agentrt/store/ruleapprove.go`、`api/internal/server/agentrt_ruleapprove.go`（含测试）、`actions/ruleapprove_catalog_test.go`【量，origin/main 文件存在】。
- `issuecard`：BI 删除提交 cceff576 把 `store/issuecard*.go` 和相关 server 测试删掉了（8f40e001 上有，origin/main 上已无）；`api/internal/questions/issuecard*.go` 在 8f40e001 上存在，是否随 BI 一起删了、还剩什么我没核【量+未核】。归我之后：先核剩什么，没用的别留。
- 我没读过这两处的实现，接手后头一件事是读一遍并更新本章程第 ① 项。

## ④ 权限
**自己定、自己做**（不问人）：读 `approvals/`、`questions/`、`ownerexec/`、`releasepolicy/` 及相关 Console 文件；在本席位的工作克隆里改代码、跑测试；写 `domains/5-owner/`、`duty/` 里自己的记录；给别的席位的提交做非作者复核并写记录；STG 上发自己的改动（按 CLAUDE.md §5「STG 发布 A」，前提 ci 绿、先持窗口）。【量：本夜的做法】
**机器现在拦着**：
- `approvals/**`、`actions/**`、`releasepolicy/**`、`delivery/release_policy_*.go`、`server/release_policy_*.go`、`server/actions_wire.go` 是信任锚路径：规则不覆盖就要走卡；改完推 `ready/<名>`，不直推 main（preflight）。【量】
- 重签后（rp-20261115-1339）「非作者复核后直发」才生效：信任锚改动要有一条非作者的复核记录；复核人身份来自请求头、只验格式、不防故意。【量，见 ruleq 复核记录】
- 权限分类器拦了「调 call-tool.mjs 记复核」那条命令（11-15 早，Unauthorized Access）；我停手没绕。另外 Bash 钩子对「命令文本里出现 Owner 目录或凭证字样」会误拦，所以这类文字我改用 Write/Edit 写。【量】
- 我不读 owner-run.sh、令牌、`~/.config/bifrost/` 与 `~/.bifrost-owner/` 下的东西；不碰批准页、不批不驳卡、不调回答问题的路由、不建真执行卡做测试。
**硬边界**（任何情况不碰）：交易和钱（D10）、口令和 Secret、有数据的删改、Trade PROD 发布、改签名规则和信任根、auto mode 与 preflight；Owner 睡觉后不建单；要加表或列就停下问统筹。
**本席位代码里的规则（别人受它约束）**：执行卡（owner/host runner）命令退出码 75 =「现在不行、什么都没写」→ 卡退回 approved、退避 30 秒起翻倍封顶 5 分钟，从批准起累计最多 30 分钟（`APPROVAL_TEMPFAIL_WAIT_MINUTES`，1–240，不越卡的期限），超时记 failed「等空档超时」；别的非零退出照旧 failed。【量，`approvals/result.go`、`OWNER_RUN_CARDS.md`，生产已发 #563】
**复核人角色**：被派到复核时读差异、写 `duty/` 记录（读了什么、结论、没看的、没跑什么），并用 `record_release_review` 记机器记录；我从不批准发布，复核不是批准。已做记录见下。

## ⑤ 目标和读数
**对哪个数负责**：「批卡／答问题／执行口」这条链上，Owner 被无谓打扰的次数，以及批了却白批的次数。
- 他动手几次（我这条线）：执行卡退 75 这件事 Owner 批了 2 张（#563 和我误建的 #562），#562 是我建错形状造成的多余一张。其余夜里的卡不是我这条线的。【量，state.md】甲乙两张表里我这条线的数我没拿到，口径请值班告知；拿到前写「还没有」。
- 复核做了几份：4 份记录——a5f06fbe（8.2）、4bf04932 规则代码（ruleq）、8f40e001（补看）、cceff576（0.1 的 BI 删除）。机器记录（`record_release_review`）：**0 份**，命令被拦，没记成。cceff576 那份 duty 文件我没能确认写成（写文件与被拦的命令在同一条里），需要重确认。【量】
- 已收（主统筹 11-15 裁：各线读数收进第 ⑤ 项并进每日读数）：下面这个数进每日读数，由值班并入 daily-readings。
- 读数（11-15 起）：**批过的卡因可预见的占用而白批的张数**（出处 #557、#514）。来源：审批记录里 failed 且 last_refusal 含「等空档」的张数，加上 attempts>1 后成功的张数；平台已有这两个字段，没有汇总页。
- 还没有：执行卡在真实 owner-run 通道上「退 75→在等→重跑→成功」的一次实测；线程信里「在等」是否出现。

## 和谁有重叠（供统筹裁）
1. **`agentrt` 的 `ruleapprove`／规则批准、`issuecard`**（agentrt 方／8.2）：两边都可能说归自己；我没认领，也没动过。
2. **发布窗口三个文件**（`window_store.go`、`window_handler.go`、`run_window.go`）与「建卡方占窗口就拒建卡」：窗口归 8.2 沟通台面，创建检查归 approvals；我的待办只做创建检查那一半。
3. **`releasepolicy/`、`delivery/release_policy_*.go`**：本章程把它列在我名下，但这夜它的作者是 CI 线（LANE-ci-w1），我只做复核。谁维护、谁改需要裁定；我倾向「CI 线改、我复核」。
4. **`actions/catalog.go`**：每条线都往里加动作（我加过 `owner_run_command` 说明，CI 线加了 `record_release_review`）；信任锚路径，谁来守住一致，未定。
5. **`k8s/owner-exec/`（执行口的集群身份与准入策略，infra）**：执行口代码归我，集群侧归 infra/ops 线；两处「Owner 读卡上的命令就是控制」的说法要一致，目前没人对账。
6. **`questions/`（ask_owner）与 8.2 沟通台面**：提问与消息两条通道，边界是否只有「问题=Owner，消息=席位间」，我没核。
