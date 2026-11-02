# DESIGN — 技术债进运行时（R5:5.8-1）· 2026-11-01 r4 · 第二部分

> 本文件是设计的第五至第十二节；状态、依据、修订记录和第零至第四节在 `DESIGN-tech-debt-runtime-2026-11-01.md`（为符合 infra 的 Markdown ≤500 行棘轮拆成两份，内容不变）。文中「（2.2）」「（4.3）」这类节号指两份合起来的同一套编号。

## 五、依赖

### 5.1 两张表各管什么

| 边 | 表 | 例子（真实条目） |
|---|---|---|
| `blocks`（needs=landed / closed） | `debt_edge` | TD-475（规则循环每 15 秒、每个步骤都重放一遍落地流）落地后，TD-476（读接口每次整条重放、PROD OOM）的缓存才好做〔推断的依赖，两条里都没写〕 |
| `part_of` | `debt_edge` | 「数据完整度执行清单」下的 TD-172、TD-142 挂在同一个伞下 |
| `follows_from` | `debt_edge` | TD-395 签收时引出 TD-406 |
| `related` | `debt_edge` | TD-476 与 TD-478（STG 512Mi 低于启动峰值） |
| 重复 | `debt.duplicate_of`（只存这一处） | 合并时用 |
| `paid_by_step` | `debt_ref` → `plan_node` | 由某个计划步来还 |
| `waits_on_owner` | `debt_ref` → 问题 `Q63` / 审批 `#255` / `debt_decision` | TD-473 的上线等 #255（`owner_run_command`，D 级，`covers=apply`）；TD-144「Owner 10-07 暂缓」，等「数据缺口的三处设计 / DDL」那一组（`covers=start`） |
| `guarded_by` | `debt_ref` → `ratchet` | TD-473 → `test_dagster_pods_have_a_reaping_pid_1` |
| `raised_by_issue` | `debt_ref` → `issue` | 一条吐槽查下来是缺陷 |
| `reclassified_as` | `debt_ref` → `accepted_gap` | 订阅里没有的数据，从债改成边界 |

### 5.2 跨仓库

TD-172：段 1 是 `bifrost-platform-plugin-market-data`（补原始数据），段 2 是 `bifrost-research`（排在段 1 之后，重算派生）。台账写着「本批已批准，扩大/短腿另批」，
所以段 2 的 `apply_gate` 不是 none，扩大那一批记成一条 `waits_on_owner(covers=apply, debt_part_id=段 2)`。
同一个仓库多段的例子：改公开接口常走「新增 → 下游切换 → 删旧」三段，core 出现两次（ordinal 1 和 3）。

### 5.3 gate 的意思，以及什么算「覆盖」（S5）

- 台账「审批」一栏说的大多是**动手那一步要你批**（PROD DDL、`apply_manifest` C 级、发版），不是「开工前要你批」。所以 `apply_gate` 挂在段上，**不挡开工**，只挡那一段的落地或应用。
- 真正要先问你的（选方案、改公开接口的方向），记成一条 `waits_on_owner(covers=start)`。
- 「覆盖」只认显式的连接：`waits_on_owner` 指向的那张审批单**已执行**；或那个问题**已答，而且所选的项在 `go_options` 里**；或 `debt_decision` 已答，同样要求所选的项在 `go_options` 里。平台不去猜哪张单对应哪个 gate。

### 5.4 各种去向

| 发生了什么 | 去向 |
|---|---|
| 审批被拒 | 这条 `debt_ref` 结束，`outcome='rejected'`；债的状态不变，`waiting_on=crew`，提示「重新设计或撤回」 |
| 问题选了 `go_options` 以外的项 | `outcome='declined'`；不自动关；`waiting_on=crew`，提示「撤回，或改成接受的缺口」（后者要 Owner 的 `gap_accepted`） |
| 计划步被 dropped / 改挂 | `paid_by_step` 结束，`outcome='dropped'` 或 `'rebound'`；只提示，不改状态 |
| 挡路的债以 duplicate 关闭 | 并债时把还活着的边改接到留下的那条上（`ended_why='rewired_by_merge'` 加一条新边，同一个事务） |
| 挡路的债 withdrawn / boundary / superseded | 边结束，`ended_why='blocker_withdrawn'`，视为放行，并提示被挡的那条复核一下 |
| `needs='landed'` 何时满足 | 挡路的债处于 `watching`、`awaiting_signoff`、`closed` 之一 |
| `needs='closed'` 何时满足 | 挡路的债 `closed`（任何结论都算；duplicate 先改接） |

### 5.5 「能开工」是算出来的；环在合并后的图上拒

```text
ready(d) = d.state ∈ {open, doing}
       ∧ 每条活着的 blocks(x → d)，x 都满足 needs                 （没有这种边 = 满足）
       ∧ 每条活着的 waits_on_owner(covers=start) 都已被覆盖        （没有 = 满足）
       ∧ 有段时：至少一段的前置段都已落地；没有段 = Unknown（不算 ready，提示「补仓库」）
waiting_on(d) ∈ {crew, owner, debt:<id>, time:<watch_until>, none}
```

等待图 = `blocks`（被挡的等挡路的）∪ `part_of`（伞等子条关闭）。写这两种边时，先拿债图锁（`pg_advisory_xact_lock`，固定键），再在**合并后**的图上用 `WITH RECURSIVE` 从目标往下走；能回到源头就返回 409 `cycle`，并给出环的路径。
段的先后在一条债之内另查。测试：A 挡 B 之后再写 B 挡 A，被拒；`blocks(needs=closed)` 加上一条反向的 `part_of`，被拒；两个事务各写半个环，恰好一个成功。

---

## 六、生命周期与自动化

### 6.1 三值判定与空集（B2）

- 每个条件取 True / False / Unknown 之一（同 `plan.Tri`，`plan/rule.go:15-33`）。**只有 True 推进，Unknown 永不推进。**
- 「全部 X 都…」在 X 为空时是 **Unknown**，不是 True：
  - 没有段 →「全部段已落地」是 Unknown；
  - 没有挂过 mission →「mission 全部结束」不适用，不触发任何转换；
  - `acceptance_json='[]'` → 验收是 Unknown。
- `flow='manual'` 的债，控制器**不做任何自动转换**，只算出并显示 `waiting_on` 和过期提示。导入的债一律是 `manual`。
  转成 `auto` 要同时满足两条：`acceptance_json` 非空、至少有一段（由 crew 写 `debt_flow_set` 事件）。新登记的债满足这两条就直接是 `auto`。

### 6.2 状态与转换（只对 `flow='auto'` 的债自动进行；manual 的由人按同样的守卫推进）

| 从 → 到 | 触发 | 守卫 |
|---|---|---|
| — → `open` | `file_debt` / 导入 | 项目、标题、优先级、至少一条证据（导入的照收，缺的进报告） |
| `open` → `doing` | 挂上 mission（`debt_work_linked`） | mission 是 `dev` 租户 |
| `doing` → `watching` | 每一段都有落地记录（6.3），而且需要 STG 的段 B5 已稳定 | 有一段是 Unknown 就不动；`watch_until` 从**部署时刻**算（观测到的或声明的），窗口默认 24 小时，可以改长 |
| `watching` → `closed/auto_closed` | 到期后验收 PASS，且这条债不属于 T12 要你签的那一类 | PASS 来自 `ci_evidence` / `promql`，或复核过的 `manual`；用的规格是复核过的那一版（`acceptance_reviewed_sha256` 等于当前规格的哈希）；防线、后续齐全（6.6）。**导入的 PASS 不算** |
| `watching` → `awaiting_signoff` | 到期后验收 PASS，且属于 T12 要你签的那一类 | 6.6 |
| `watching` → `doing` | 验收 FAIL | 结果留着，`waiting_on=crew` |
| `awaiting_signoff` → `closed/signed_off` | Owner 签收 | 只在 PROD（`approvalhome/home.go:14-16`，platform bfa513d6） |
| `awaiting_signoff` → `doing` | Owner 打回，必须写原因 | 原因成为 `next` |
| `closed` → `doing`（重开） | `debt_reopened`：Owner 任何时候；crew 只能重开 7 天内的 `auto_closed`，带理由 | 结论清空；原来的验收运行留着，但不再算数，要新的一次 |
| `doing` → `open` | 挂过至少一个 mission、全部已结束、没有任何一段有落地记录 | 空集不触发 |
| 未关 → `closed/duplicate·withdrawn·boundary·superseded` | crew，带理由 | 按 5.4 改接边；`boundary` 还要 Owner 的 `gap_accepted`（T8） |

不存 `blocked` 状态：「被挡」由 5.5 算出来。

**谁复核什么**：`ci_evidence`、`promql` 的结果由控制器从 CI 和 Prometheus 读出来，作者写不进去（2.2 的写者检查），所以结果本身不另做复核；
真正可能出错的是**规格**——拿哪个测试、哪条查询来证明修好了。所以规格每改一版，都要由作者以外的写者复核一次（`debt_acceptance_reviewed`），自动关闭只认复核过的那一版。
`manual` 的结果照旧要第二个写者核（库里 CHECK）。

### 6.3 什么算「这一段落地了」（S3）

| 仓库 | 落地的证据 | 部署 |
|---|---|---|
| platform、infra（经运行时落地） | 这一段所属 mission 的实现任务都已落地（用 `StepLanded` 同一套折叠，`stepevidence.go:59`）；platform 还要看 B5 STG 稳定（`:73`） | platform 读得到（`agentrt_sources.go:23`）；infra 的清单变化靠 Argo，读不到，要声明 |
| Trade 各仓库、research、插件、shared-ui、finance | crew **声明**提交 → 平台用 Gitea 核实它在 main 上 → main 上有一个**包含它、且 CI 成功的后代提交**（一次推多个提交时 CI 只跑最新的那个，所以不要求正好是这个提交；python 各仓库和前端有 CI 读数，`release_policy_facts.go:50`；finance、ui 没有 → 记 `ci_status='unread'`，这一段只能手工确认） | **读不到**。部署时刻和环境由 crew 声明并附证据（发布 run 名、Argo 记录），记 `deploy_read='declared'`，Console 上标出来 |

尾注 `Work: TD-n` 只用来在页面上**建议**候选提交，原因有三：
- 它本来就是 git hook 从标题和正文里提取的（infra `agent-config/scripts/git-hooks/lineage.sh:10`），分不出「提到」和「修了」；
- TD-91 的修复 `2277054` 根本没有这个尾注；
- research `7fc3244` 一个提交写了五个 TD。

要给债的段加一个 CI watch 来源（今天的 watch 只来自计划规则，`controller.go:271-282`），这一项归 5.8-4。

### 6.4 验收：不让运行时执行任意命令（S9）

`acceptance_json` 是封闭语法（认不得的键直接拒，同 `plan/rule.go` 的做法）：

```json
[{"kind":"ci_test","repo":"bifrost-research","path":"tests/orchestration/test_daemon_manifest.py","name":"test_dagster_pods_have_a_reaping_pid_1"},
 {"kind":"promql","query":"max_over_time(kube_pod_container_status_restarts_total{namespace=\"research\",container=\"dagster-daemon\"}[1h])","expect":{"eq":0}},
 {"kind":"owner","say":"python3 scripts/check_admission_guards.py --live","expect":"every *-writes-github-sync-scripts case refused"},
 {"kind":"manual","say":"three Dagster daemons heartbeat within 5 minutes","expect":"…"}]
```

| 类 | 怎么判 | 为什么安全 / 剩余风险 |
|---|---|---|
| `ci_test` | 只用于 CI 真跑测试并卡住的五个仓库：lint 卡住的四个 python 仓库（research、trade-api、trade-core、trade-worker，`pipeline-ci-python.yaml:164-166`）加 platform。**frontend 不能用**：ci-frontend 只有 lint（不卡）和 build，不调用 vitest（`pipeline-ci-frontend.yaml:2,13,106-111`），它的 CI 绿证明不了任何测试（这一条另登记成债，见风险 7）。存在一个 main 上的提交 C，同时满足：C 包含每一段的落地提交（Gitea compare 判祖先）；C 的 CI 成功（`ci_seen`），且 platform 的 Go 测试要求 C 那次运行的 `api-scope=full`（console 范围只跑读 `api/` 以外文件的 Go 测试却仍显示 Succeeded，`pipeline-ci-platform.yaml:5-10`、`task-ci-platform-changes.yaml:4-5`）；在 C 里 `path` 有名为 `name` 的测试；python 测试在该文件里没有 `ib` / `db` 标记（CI 只跑 `-m 'not ib and not db'`，`:218`），Go 测试文件没有 build tag | 运行时**什么都不执行**，用的是 CI 已经跑过的结果。别的 python 仓库（三个插件）没有 pytest 时 CI 照样绿（`:217-220`），不能用；infra、finance 的 CI 不在索引里（`release_policy_facts.go:50`），也不能用 |
| `promql` | 用平台已有的 Prometheus 只读读取〔推断：复用 telemetry 的客户端〕 | 只读的查询语言，有超时 |
| `owner` | 在 PROD 上建一张 Owner 卡，写明在哪台机器上跑什么、看到什么算过；Owner 选 PASS 或 FAIL，并附上输出 | 平台不持有 Owner 身份 |
| `manual` | 一个写者记录结果和证据产物，**另一个写者**复核后才算数（库里有 CHECK） | 防止自己证明自己 |
| SQL、k8s 读 | 先归 `manual`（T9） | 平台没有 `agent_reader` 凭据〔推断〕，给它凭据是安全变更 |
| 在 agent-06 上执行测试 | **先不做**。TD-377 还是未开始：执行者能读到令牌文件和别的尝试的工作区（`TECH_DEBT.md:2856`），Landlock 只挡写（TD-371，`TECH_DEBT.md:33`） | TD-377 关了以后，可以加 `kind:"run_test"`：运行器和参数形状按规则 `acceptance_runners` 的白名单来，不经过 shell，断外网 |

**`ci_test` 仍然证明不了的**（如实写在详情页上）：CI 不出 JUnit，读不到单个测试的结果（已确认）；所以运行时 `pytest.skip`、`skipif` 条件成立时跳过、conftest 里统一加的 `ib` / `db` 标记、参数化后一个用例都没生成，这些情况下测试没跑也算通过。跟进：让 CI 产出 JUnit（改 infra 流水线），登记为一条新债，修好之后 `ci_test` 改成按单个测试的结果判。

导入时现有的验收命令（大多是 `kubectl … exec … psql`）原样存成 `acceptance_text`，**不执行**；`acceptance_json` 由 crew 逐条改写（`debt_acceptance_set` 事件），复核看得见。

### 6.5 证据核对

`code_ref` 类证据由平台用 Gitea 只读账号取 `repo/path@commit` 的那几行，与 `quote` 比对，结果写进 `debt_evidence_check`（`matches` / `moved` / `missing`）。
每周对还没关的债重核一次；`moved` 的补一条新证据（填 `supersedes_id`）。

### 6.6 签收、自动关闭与打回

- **要你签的那一类**（T12-B）：关闭时要接受残余风险的——结论是 `boundary`、要连到接受的缺口、或验收里有 `owner` 类（只有你能跑的那一步）；或者修法改了签名规则或治理文字（段的 `apply_gate='rule_sign'`）。
  其余的自动关闭。DDL、删除、PROD 变更在动手时已经由你批过审批单，验收只确认结果，而且能重开，不算不可逆。
- **关闭的条件**（平台判，缺一条都不关、也不进待你签收）：最新一次非 imported 的验收运行是 PASS；它跑的提交包含每一段的落地提交，并且晚于最后一次 `debt_part_landed`；
  用的是复核过的规格；有 `signoff_summary`；至少一条 `guarded_by`，或一条 `no_ratchet_reason`；有一条 `follows_from` 指向它的新债，或一条 `no_follow_up_reason`。
- **导入的 25 条待你签收**：认 `imported` 的 PASS，以及 `ratchet_text`、`follow_up_text`（25 行都有）。store 写死范围：只对「导入时就是 `awaiting_signoff`、之后没离开过」的债有效；
  一旦被打回或重开，导入的 PASS 就不再算数。签收卡上写明「验收结果是从台账原文导入的，平台没有重跑」。这 25 条都由你签（可以一次批量签），不走自动关闭。
- **签收**：`POST /api/v1/agentrt/debts/{id}/signoff`（只限 admin，只在 PROD），写 `debt_signed_off`。再按一次，回第一次的结果。
- **打回**：`POST /debts/{id}/reject {reason}`，状态回 `doing`，原因写进 `reject_reason` 和 `next`。
- **重开**：`POST /debts/{id}/reopen {reason}`；自动关闭的债在「自上次以来」里列 7 天，带一键重开。
- 签收项出现在 Work › Sign-offs（已有 `console/src/pages/shell/agents/WorkSignoffs.tsx`）和「只有你」那一栏；可以多选，但每条各发一次请求、各记一个事件。

### 6.7 推进按事件驱动（吸取 TD-475、TD-476 的教训）

TD-475、TD-476 的根因是规则循环和读接口每次都整条重放落地流。债的推进只在相关读数事件提交之后触发（`ci_seen`、`deploy_seen`、落地流的 `landed`、B5 的 `settled`、`question_seen`、`approval_seen`）：
按 `debt_work → mission → task` 和段的提交找到受影响的债，只评估这几条；到期的观察窗按 `watch_until` 上的索引取。评估结果只在变化时写事件。负载测试是 5.8-4 的验收项。

---

## 七、导入与导出

### 7.1 一次性导入（3a 演练，3b 正式）

导入器读冻结那一提交上的两份文件，产出一个 `agentrt.debt_import/v1` 请求（思路同 `planimport/request.go`）。提议之后有一张 Owner 卡，批了以后由 store 按普通事件写入（`debt_filed{source:import}`…）。
`legacy_imported` 写不了债的表（2.2）。解析规则如下，每条配一个夹具测试，夹具取 de152c7 的真实片段：

1. 按 `## ` 切节；条目只认 `## 条目` 下的。全文任何位置出现 `^### TD-\d+$`、却不在 `## 条目` 下，导入失败（就是 de152c7 之前那 137 条的形状）。
2. 标题行用 `render-tech-debt-page.py:56` 的正则（250 条全部匹配）。
3. 字段行认 `- **键**：`、`- **键**:` 和不加粗的 `- 验收:`；中英文键按第三节映射；认不得的键整段进 `note`，`heading` 存原来的键。
4. 审批行认三种写法：`- 审批 X · 代价 …`（109 条）、`X）· 代价`（缺空格，约 87 条）、`- 审批：X · …`（4 条）；另有 50 条没有。按关键词映射：
   - 「改公开接口」这类方向还没定的 → `waits_on_owner(start)`；
   - 「PROD 变更」「apply_manifest C 级」「准入策略与 RBAC」→ 段上的 `apply_gate`；
   - 「不用批 / 不需要 / 无 / 不要」→ none；
   - 映射不了的进报告；原文一律进 `import_raw`。
5. 状态：先去掉 `**`，取到第一个 `（ ( —— 。 ｜ ：` 之前的部分，映射到四态；映射不了的三种（`待 Owner 改配置`、空串、`**2026-10-28…`）进报告，由统筹逐条定。
   `到 MM-DD` 写进 `watch_until`（年份 2026，芝加哥时区当天 23:59）；过期的 27 条照样是 `watching`，`flow='manual'`，页面上标过期；没写日期的 24 条，`watch_until` 取导入时刻，并进报告。
6. 证据：`` `path:line` — `quote` `` 这种写法（`render-tech-debt-page.py:76`）变成 `code_ref`；新格式里的自由文字证据整段存成 `measurement`，再从中抽出 `path:line` 和短提交号，另建附加的 `code_ref`。
7. `repos:` → 段（ordinal 按列出的顺序，不设先后）；没有的从证据路径推，推出来的进报告；推不出来的没有段（按 6.1 是 Unknown）。项目按 `owns` 建议，跨项目的进报告逐条确认。
8. 波次 → 标签 `wave:<n>`（13 个）；主题 → `theme:<slug>`；「先看这几条」→ `look-first`；数据完整度执行清单 → 伞形债加 `part_of`。
9. 验收结果：条目里的「验收结果：PASS / 部分 PASS / FAIL …」，以及「待你签收」行里的「验收：PASS 日期 提交」→ `debt_acceptance_run(runner='imported', source_sha256=原文哈希, result, ran_at, at_commits=抽出的短提交号)`。
   「待你签收」那一行再拆出 `signoff_summary`、`ratchet_text`、`follow_up_text`；「后续」要认「无后续：理由」这种写法（TD-392、TD-384、TD-378 就是）。
10. 「需要你拍板」12 组 → 12 条 `debt_decision(state='pending')`，组里还开着的成员连 `waits_on_owner(covers=start)`；已关的成员和已过时的组（如 TD-91 那组）进报告，由 crew 核对后标 `dropped` 或重新问（T10）。
11. 「数据边界」3 条 → `accepted_gap(gap_kind='data_boundary')`；「没覆盖到的」「怎么做的」→ `crew` 项目的说明文字。
12. `filed_at`：取 infra git 里第一次出现 `### TD-n` 的提交时间（`git log --reverse -S'### TD-n'`，跨所有分支）；「上次查看 92c0271」→ 各项目的「上次看过」标记。
13. `RATCHETS.md`：`## 现有防线` 240 行 → `ratchet`（按行序发 `R-n`），五列照存，强度取第一个词归类；行里的 TD 号全部进 `td_refs`（历史编号，不建外键）；
    其中还开着的那些（68 个开着的号）另建 `guarded_by`；`## 各类债现在挡没挡住` 和 `## 待建防线` 存成 `crew` 项目的说明。

**导入验收**：
1. 分布一致：按状态、优先级、项目、仓库分别统计，与源文件相同；
2. 往返比对：用 3a 的导出器把导入结果写回同样形状的 Markdown，与源文件逐条、逐字段比；解析过的字段逐字相等，差异只出现在报告列明的条目上；
3. 报告由另一个工具独立复核；
4. 地板 ≥ 488；
5. 同一个请求导两次，第二次全部是「已存在」；
6. 先在 STG 全量演练一次（号映射成 `TDS-n`，见 2.4）。

### 7.2 以后放哪（T6，按 B1、R2 重算）

| 选项 | 要做的事（逐条） | 结论 |
|---|---|---|
| E1 原路径导出到 git | 硬底线为一个文件开例外（`landing_infra.go:14-16` 与 `doc_policy.py:150-151` 两处）；文件 704,672 字节，超过 256 KiB 上限（`doc_policy.py:209-211`），还得放开内容上限；一次落地最多 5 个文件、1500 行（`:158`），首次 3955 行要分几批；还要一个任务来领导出提交（`landing/protocol.go:42` 的 `claimed`） | 代价最大，为一个文件要动四道防线 |
| E2′ 按项目拆、放进 `work/debt/` | `landing:dev` v6 加上 `agent-config/work/debt/*.md`（你签）；平台的 `InfraLandingAllow` 改代码（`landing_infra.go:5-12`，核心卡）；每份小于 256 KiB（crew 一个项目就可能超，还得再拆）；首次约 4000 行，至少 3 次落地；新 `task_class` 的确定性任务产出提交；读这些文件的脚本不能登记为读者（`registry_overlap`，`doc_policy.py:196-205`）；占每天 24 次落地的份额（`landing-dev.yaml:16-21`） | 可行，但每一处都是新的长期维护面 |
| **E3（推荐）不再进 git** | 冻结（7.3）之后的读面：Console 页、MCP `list_debts` / `get_debt`、`GET /debts/export.md`（只读，按 `visibility` 投影，输出确定）。持久性只靠 PROD 逻辑备份：每天 04:30 UTC 一次（`cronjob-backup.yaml:20`），最多丢一天；14 份日备份加每周冷备（`backup.sh:18-26`），全在同一台 NAS 上。不另做「快照产物」：它存在同一个库的 `artifact_blob`（`0001_core.sql:43-46`），库坏了一起坏，不算缓解 | 不用推、不用落地；当前的树里不再公开开着的安全洞 |
| E4 私有 Gitea 仓库 | 新建一个不在 `gitea-primary.txt`、也不在 github-sync 对账清单（`k8s/cicd/github-sync/cronjob-reconcile.yaml:39-49`）里的私有仓库，平台每天（或每次关闭后合并）用 Gitea API 直接提交导出文件；不经落地、不碰 infra 硬底线、不会自动进 GitHub。代价：平台要一份 Gitea **写**凭据（今天只有只读账号，`delivery/gitea_reader.go:13-21`、TD-432），这是安全决定；推送触发的 github-sync（`trigger-template.yaml`）会不会对新仓库也起一次，要先核实〔未核实〕 | 留得住 git 历史和不连运行时也能读；多一个写凭据和一条写入路径 |

**E3 丢掉、git 能给的**（如实列出）：
1. 文件级的历史和 `git blame`。运行时有每条债的事件流（只追加、哈希链），能回答「谁在什么时候改了什么」，但不能用 git 的工具看。
2. 不连运行时也能读：agent-06 上的执行者、派活目录里的 Codex（不一定能用平台 MCP）、PROD 平台宕机的时候。
3. GitHub 上的一份异地副本。E3 之后，台账唯一的副本是 PROD 库及其在同一台 NAS 上的备份；E4 也只在集群内的 Gitea 里，同样不异地。异地副本是已有的待定事项（TD-218），不是本设计能补的。

**为什么仍推荐 E3**：你要的三件事——不撞号、不冲突、不用你在终端推——E3 都做到了，而且不新增任何凭据或写入路径；E4 多出来的只是第 1、2 条。
E4 可以以后加：导出器在 3a 就有，E4 只是多一个写入者。如果某个不连运行时的读者真的需要（例如 Codex 的复核任务要读台账），再按 E4 做，届时作为安全决定单独批。

### 7.3 冻结与挡手改（3b，同一个窗口）

冻结不只是推一次，要按这个顺序完成：
1. **平台先改读者**（核心卡 + PROD 发布单）：AI 评估（TD-391）今天在 main 上读 `AGENTRT_LEDGER` 指的文件并按标题解析条目（`server/agentrt_assess.go:134-150`、`:258-263`）。改成「库里已导入就读 `agentrt.debt`，还没导入就照旧读 `AGENTRT_LEDGER` 文件」，切换看库里有没有导入记录；有了这个回退，3a 先上 PROD、3b 才导入的这段时间评估不会空窗；另外 STG 演练时号被映射成 `TDS-n`，所以 STG 上评估按同号把 `TD-n` 映射为 `TDS-n` 再查（3a 的验收同时看 STG 已导入和 PROD 未导入两种情形）。
   改成编号是 `TD-` / `TDS-` / `TDD-` 的从 `agentrt.debt` 读；读不到的照旧写进 `NotRead`，不能悄悄变成「没有」。这一版先上 PROD，环境变量还在也不影响。
2. **导入**：导入请求读的是冻结前 main 上的某一个提交 X；冻结之前新发现的债照旧手写进 `TECH_DEBT.md`，读到 X 为止的都随导入进来。
3. **Owner 推一次**（硬底线）：冻结提交的父提交必须**正好是 X**，用 `push-main.sh` 只快进推；main 已经前进了（有人在 X 之后又手写了一条），就拒推，重新导入差额再来。这一次推送包含：
   `TECH_DEBT.md`、`RATCHETS.md` 换成指针（写明去 Console 和 MCP 的哪里看）；`preflight.js` 拒绝对这两条路径的 Edit / Write / `git add`；
   工作区 CLAUDE.md §5「技术债与防线」、Cursor 侧 `workspace.mdc` 同步并 bump `parity-id`（§7）、`AGENT_FACTS.md` 里提到台账的地方；`render-tech-debt-page.py` 删掉（否则你现在看的台账页会读到指针、空几周）。
4. **去掉 overlay 里的 `AGENTRT_LEDGER`**（`k8s/overlays/platform-{prod,stg}/platform-agentrt-env.patch.yaml:63-64`）：STG 那份按工作区 CLAUDE.md §5「STG 发布 A」由 Agent 推并同步；PROD 那份是 `k8s/**` 硬底线，由 Owner 推。每个环境都放在本环境导入完成之后（PROD 即第 2 步之后）；在导入之前去掉，评估就失去回退、又会空一段。
5. 台账页由 3b 的最小签收列表和 MCP 接替，5.8-5 的 Console 页上线后完整替代。

---

## 八、Console

- **Work 里新增一个 `Debt` 标签**（`WorkTabs.tsx` 现在有 round / Sign-offs / Live / Changes）：按项目分组，crew 自己的平台单独一组。
- **项目页**（v3.6 `ProjectPage`）每个项目一块「Open debt」；**只有你**（v3.6 `BoardHome` / `InboxPage`）里的待签收和等你拍板由平台计数。
- 文件：页面的 `.tsx` 放在 `console/src/pages/shell/agents/**`，按规则落地（`landing-dev.yaml:9` 只放 `*.tsx`）；`.ts` 视图模型和 `console/src/api/**` 不在放行里，随核心那一片走卡。界面文字用英文。

| 区块 | 内容 | 数据 |
|---|---|---|
| 顶部一行 | 每个项目：open / doing / watching（其中过期几条）/ awaiting you；本周新登记、本周关闭 | `GET /debts/summary` |
| 筛选 | project、priority、state、`waiting_on`、ready、flow、apply_gate、repo、area、tag、age | 都是 URL 参数 |
| 列表行 | 编号、优先级、标题、项目、状态（观察中带到期日和是否过期）、等谁、账龄、最近一次验收（含 imported 标记） | `GET /debts` |
| 详情 | 字段；证据（Gitea 链接到某个提交上的那一行，加核对结果）；验收规格和每次运行；段与先后、各段的落地提交和部署读数（observed / declared）；依赖的两层列表；mission 与任务；候选提交（尾注建议）；历史；花费 | `GET /debts/{id}` |
| 账龄与还债曲线 | 每个项目未结数按周画；新登记 vs 关闭 | `GET /debts/burndown` |
| 签收 / 打回 | 只在 PROD、只对 admin 显示；打回必须填原因 | 6.6 |
| 自上次以来 | 新增、关闭、状态变化、防线增减 | 事件流 |

---

## 九、「排得好」：以后的挑债（现在只留模型）

- **能不能做**：`ready`（5.5）。**值不值**：优先级、`apply_gate`、风险、账龄、过期的观察、标签。
- **多贵**：登记时估的 `cost`；做完以后的实际花费 = 挂在它上面的 mission 里各个 attempt 的 `budget_ledger`，按 unit 求和（`0001_core.sql:398-406`）。一个 mission 同时还多条债时不平摊，
  写「与 TD-x 共用」；统筹在 Mac 上做、没进运行时的那部分标「未计量」。
- 后续阶段：在一个目标之内，由规则给出候选（ready × 优先级 ÷ 预计花费），挑选的理由记成事件；预计与实际花费的偏差进交付经济记录。

---

## 十、切片（按 S2、R1 重排）

计划里已登记步骤的范围随之调整（3 拆成 3a 和 3b、签收与读者切换挪进 3b、6 变成收尾）；这属于 5.8-2 批准设计的一部分，批了以后用一张 `propose_plan_change` 卡落到计划上。

| 步 | 做什么 | 验收 |
|---|---|---|
| **5.8-3a 数据层与接口（PROD 不发号）** | `0011` 的全部表、守卫、授权；store；路由（`/debts`、`/debts/{id}`、`/edits`、`/texts`、`/evidence`、`/edges`、`/refs`、`/work`、`/parts`、`/export.md`）；MCP `file_debt`、`get_debt`、`list_debts`、`edit_debt`、`add_debt_evidence`、`link_debts`、`link_debt_work`；导出器；导入器和报告；AI 评估改从 `agentrt.debt` 读（7.3 第 1 步）；STG 规则（`TDS`）；测试库里建 `platform_agentrt_prod` 角色（`agentd/testdb.go:225` 现在只有 dev 和 stg），库守卫的正向测试才跑得了。STG 由流水线迁移，并在 **STG 全量演练导入**（号映射成 `TDS-n`）；PROD 由你建迁移 Job，之后跑 `logical-backup` 和 `logical-backup-drill` | 并发登记不撞号；STG 发不出 `TD-`（store 与库守卫各一个测试）；PROD 没有规则时登记被拒；守卫：没有事件的写被库拒、`legacy_imported` 写债的表被拒、`agent:` 写者被拒、没有复核者的 manual PASS 被拒；成环被拒（含跨种类）；STG 演练过 7.1 的六条；评估在 STG 上按 `TD-n`→`TDS-n` 读到导入的条目，PROD 未导入时仍读文件、不出现新的 `NotRead`；PROD 备份转储里有 `agentrt` 新表，演练行数一致 |
| **5.8-3b 导入、冻结、签收（同一个窗口）** | 7.3 的第 2–5 步：PROD 导入卡；签 `debt-projects` v1（开放登记）；冻结推送（指针、preflight、治理文字与 parity、删渲染器）；overlay 推送；签收 / 打回 / 重开路由；最小签收列表（Work › Sign-offs 里列出待签的债，`.tsx`） | 导入验收全部通过；冻结提交的父提交等于导入读的提交；冻结后第一条真债的号大于地板且不重复；导入的 25 条在 Console 上能签、能打回；手改两份文件被 preflight 挡住（阳性对照）；PROD 评估读到条目、不出现新的 `NotRead` |
| 5.8-4 联动与验收 | 段的先后与落地记录；CI watch 来源；事件驱动的推进；`flow` 切换；规格复核；`ci_test` 和 `promql` 验收；Owner 卡和手工验收；证据核对；自动关闭与重开（T12） | 一条真实的 platform 债全程不手改走到关闭；FAIL 回 `doing`；Unknown 和空集不动；导入的 PASS 不能触发自动关闭；一条非运行时仓库的债按「声明 + main 上 CI 绿的后代」走到观察中，部署标 declared；负载测试 |
| 5.8-5 Console 页 | 第八节 | 用真实 PROD 读数做夹具测试；签收按钮只在 PROD 出现 |
| 5.8-6 收尾 | 按 T6：E3 下确认没有残留的读者和手写入口；选了 E4 就在这里加写入者 | 仓库脚本和**运行时**都不再读这两份文件：platform 源码里没有 `AGENTRT_LEDGER`、没有 `TECH_DEBT.md` 读取，PROD 与 STG overlay 不再设它；preflight 规则还在 |
| 5.8-7 实测 | 一周 | 基线（11-01）：真实撞号 1 次（`fdf36f8` 对 `497c6ba`，前者只在统筹本机）；10-25 以来改台账的提交 49 个（逐个看是谁推的）；台账页看不见的条目 137 条（已修）。冻结后号由一个发号器发，撞号在结构上不可能，所以量的是：preflight 拒绝手改两份文件的次数、改号提交的数量、不经 `file_debt` 冒出来的 `TD-` 号（git 尾注里有、运行时里没有）→ 都应为 0；Owner 为台账推的提交 → 0；过期观察 27 条 → 有数且在下降 |

第一片只在 STG 动真东西，PROD 在 3a 只多了空表、关着的路由和评估的新读法。真正不可逆的两件事——发出去的号、冻结——都在 3b，在同一个窗口里完成。

---

## 十一、风险与不做的

**风险**
1. **运行时库成了唯一真源**（E3）：库不可用时就登记不了、也读不到；备份每天一次，最多丢一天，全在同一台 NAS 上，没有异地副本（7.2）。缓解是 PROD 逻辑备份和演练（2.5），同一台 NAS 上还有 Barman 的基础备份加 WAL（TD-218），但它从没做过恢复演练，不能算数；MCP 返回 503 时，统筹先记进待办笔记，恢复后补登。
2. **私有正文在库这一层可读**：`agent_reader` 读得到全部正文（4.3、T13）。
3. **导入读错**：两种格式、三种审批写法、三种映射不了的状态、50 条没有审批行。缓解：往返比对 + 报告 + 独立复核 + STG 演练。
4. **自动推进推错**：只有 True 才推进；空集算 Unknown；导入的先走手动；读不到部署的写明 declared；关闭只有签收一条路（或者 T12 选定的那一类自动关闭，你在「自上次以来」里看得见，也能重开）。
5. **性能**：和 TD-475/476 同类，见 6.7。
6. **迁移不可逆**：`0011` 替换共享守卫函数，并对 `event` 加强锁（2.5）；STG 先跑，PROD 由你建 Job。
7. **`ci_test` 的盲点**：CI 不出 JUnit，被 skip、被 conftest 标走的测试也算通过；只在四个 python 仓库和 platform（要求 `api-scope=full`）可用，frontend 的 CI 不跑测试（6.4）。如实标在详情页上，并登记两条跟进债：CI 产出 JUnit；ci-frontend 跑 vitest。
8. **冻结窗口**：冻结推送要求父提交正好是导入读的提交，main 在中间前进了就要重导差额（7.3）。

**不做的**
- 不做自动挑债；不碰 D10；验收没有任何写能力，运行时不执行任意命令。
- 不改业务问题的表和流程，只加一条可选的连接。
- 不迁移 `WORK.md`；W-n 引用的 68 个 TD 号只在详情里反查显示。
- 不判断每条债的修法对不对；导入时不重排优先级、不合并重复。
- 不读 Trade 的版本或健康字段；不用 Gitea Issues；不引入外部依赖。

---

## 十二、待你定（每项都带推荐）

1. **T1 技术债存在哪？** A 复用 `agentrt.issue`，加一种 kind · **B 新表族 `agentrt.debt*`（推荐：标题 187/250 超过 issue 的 80 字上限，issue 的状态和约束是接业务用的；B 只加不改）** · C Gitea Issues（11-01 你选了 B 方向，没选 C）。
2. **T2 编号怎么发？** **A 保留 `TD-n`；只有 PROD 发号，按 `AGENTRT_ENV` 判断，库里只让 `platform_agentrt_prod` 写 `TD-`；STG 发 `TDS-n`、DEV 发 `TDD-n`；地板 488（推荐）** · B 换新前缀，旧号做别名 · C 按项目分别编号。
3. **T3 项目清单放哪？** **A 签名规则 `debt-projects`（推荐：平台代码里不出现产品名）** · B infra 里的一个普通配置文件 · C 写在平台代码里（违反双飞轮）。另请你看一眼 4.1 的路径划分（`k8s/base/**`、`k8s/data/**`）。
4. **T4 状态用哪几种？** **A 你的四态，加「关闭及结论」；「被挡」算出来，不存（推荐）** · B 另存一个 `blocked` 状态 · C 照搬 issue 的十种状态。
5. **T5 冻结后的两份 Markdown 怎么办？** **A 换成指针（推荐：当前的树里不再列出还开着的安全洞）** · B 保留冻结时的全文，在头部注明 · C 保留全文，并继续由平台更新（也就是 E1 / E2′）。
6. **T6 冻结之后，台账还要不要一份 git 副本？** **E3 不要：运行时 + Console + MCP + 只读导出端点，持久性靠每天一次的 PROD 逻辑备份（推荐：满足不撞号、不冲突、不用你推，且不新增凭据；丢掉的 blame、离线可读、GitHub 副本见 7.2）** ·
   E4 要，放进一个不同步到 GitHub 的私有 Gitea 仓库（留得住 git 历史、离线可读；代价是给平台一份 Gitea 写凭据，属于安全决定，并先核实 github-sync 碰不到它）·
   E1 / E2′ 放回 infra（要动四道防线 / 多处长期维护面，不推荐）。
7. **T7 防线台账怎么办？** A 只做链接，`RATCHETS.md` 继续手写（每关一条债还要你推一次）· **B 导入成 `agentrt.ratchet`，与 `TECH_DEBT.md` 同时冻结（推荐）** · C 维持 Markdown，签收时只查有没有写防线。
8. **T8 数据边界放哪？** **A 单独一种 `accepted_gap`，与 v3.6 的「Accepted risks」合成一个带 `review_at` 的「接受」台账，只有你能接受（推荐）** · B 当作结论为 `boundary` 的债 · C 留在 Markdown 里。
9. **T9 验收由谁、怎么跑？** A 平台在进程内跑 PromQL、SQL、k8s 读（要给平台一个只读库凭据）· **B 只做 `ci_test`（读 CI 证据，只在 CI 真跑测试并卡住的五个仓库：四个 python 仓库加 platform；frontend 的 CI 不跑测试，不在内）和 `promql`；SQL / k8s 读归手工；在 agent-06 上执行等 TD-377 关了再议（推荐）** · C 全部手工。
10. **T10 「需要你拍板」那 12 组怎么搬？** A 导入时直接建 12 张问题卡 · **B 导入成待定事项，由 crew 逐组核对（26 个号里 15 个已关，TD-91 那组已过时），还成立的再问你（推荐）** · C 全部作废。
11. **T11 什么时候冻结，签收怎么按？** **A 3b 导入时冻结，签收、打回、重开路由同时上线；可以多选，每条各记一个事件（推荐）** · B 等到 5.8-6 再冻结（中间两边都在写）· C 同 A，但只能一条一条签。
12. **T12 哪些债要你签收？** A 全部（今天的规矩）·
    **B 只有关闭时要接受残余风险的（结论 `boundary`、连到接受的缺口、验收里有只有你能跑的 `owner` 一步）和修法改了签名规则或治理文字的；其余在验收 PASS（复核过的规格）、防线和后续齐全后自动关闭，在「自上次以来」列 7 天、可一键重开（推荐：DDL、删除、PROD 变更动手时已由你批单，签收只是确认结果）** ·
    C 全部自动关闭，事后抽查。不论选哪项，导入时已在待你签收的 25 条都由你签（可一次批量签），因为它们的 PASS 是导入的、平台没有重跑。
13. **T13 债的正文库层可读，接受吗？**（`agent_reader` 是 `pg_read_all_data`，`visibility` 只在 API 层）
    **A 接受，与 0009 的先例一致（`0009_issues.sql:966-969`）；规定债的正文只写系统和代码的行为，不写家庭财务内容，Finance 的债只引用 Finance 自己记录里的编号；再加一道写入时的扫描：所有正文都按 `store/localpath.go` 的规则拒本机路径，规则里标了 `text_scan: strict` 的项目（Finance）另外拒带货币符号的金额和 8 位以上的连续数字——但放过这几类：7–40 位且至少含一个 a–f 字母的十六进制串，或在 Gitea 上核实过确实是提交号的串；`YYYYMMDD` 日期；发布 run 名这类已知编号格式（全是数字的串不因「像十六进制」而放过）（推荐；扫描只挡明显的数字，挡不住用文字描述的财务情况，所以写作规定仍是主要的那道）** ·
    B 私有正文在应用层加密，钥匙放在平台 Secret 里（新的安全面和钥匙管理）·
    C Finance 的债不进共享运行时，由 Finance 自己记（好处：家庭财务语境一点都不进共享库，符合「各产品业务独立」；代价：Finance 的债又回到手写、没有发号器、没有跨产品依赖、Console 和以后的挑债都看不到它）。
