# Review 538 — 4.1 第二稿复审

结论：先改。第一片收窄、失败先开问题、自动修复放 S4、infra 放 S6，方向成立；首轮多数要求已经进入正文。但还不能按「全部采纳」直接签署：同一个 `eligible()` 会拒绝已经成功落地的 STG 待发布结果；新增事件与数据库 CHECK 不相容；P0 的验收不能证明没有间接取得或使用 main 凭证的路径。另有关闭条件、最终闸门锁、窗口清理和恢复入口未闭合。

这是设计复审。「已关闭」表示设计回应及验收要求足以关闭原意见，不表示尚未实现的代码已经通过测试。本轮不扩展到 534 的其他意见，也不审查与本次修改无关的历史问题。剩余事项在文末列成 Owner 选项，不要求自动开始第三轮。

版本与路径：

- `CUT`：`/Users/vision-mac-trader/agent-work/r4-landing/agent-config/work/multi-agent/CUT-landing-2026-10-24.md`，第二稿 573 行，HEAD `71b235d7f25382d1745c1becc83d3b59796cacbe`。
- `I/`：上述 `r4-landing/` 工作树。核对了 `047ea5ca..71b235d7`；差异只有 CUT，工作树干净，没有实现代码变化。
- `P/`：`/Users/vision-mac-trader/Desktop/stocks/bifrost-platform/` 的本地 `origin/main` 对象 `82b3e9d798f098bbb2ce0bd4ed925892e116199e`。以下 platform 源码均由 `git show origin/main:<path>` 读取，行号属于此对象。
- 首轮依据：`/Users/vision-mac-trader/agent-work/codex-review-533/{REPORT,RESPONSE}.md`，以及 `codex-review-534/REPORT.md` B1。

## 1. A1–A11、534 B1 的逐项裁决

| 条目 | 裁决 | 第二稿、代码依据及切片验收 |
|---|---|---|
| A1 凭证隔离 | **未关闭** | P0 已加入 `CUT:142-156,521`，直接撤权方向正确；但只查指定 Secret 的 GET、令牌推送和文件名，覆盖不了 CI 共享克隆目录及发布任务注入管理员令牌。`I/k8s/cicd/tekton/task-git-clone-gitea.yaml:32-42,58-80`、`task-gitea-mirror-sync.yaml:35-40,73-78`。S0 的「STG 改保护被拒」有独立价值，不能代替其他身份与间接路径的验收，见第 2 节。 |
| A2 决定卡绕底线 | **关闭但带来新洞** | `CUT:235-252,545` 明确硬拒绝、没有「合」、首版不设软例外，关闭原卡片旁路。S1①（`:522`）能单独抓住它；与 `I/agent-config/CLAUDE.md:230-231` 的问题回答不算批准相符。但新写死的「信任边界」名单漏了真实审批实现，不能据此安全放宽 S5，见第 5 节。 |
| A3 收紧、额度、启用时刻 | **未关闭** | `CUT:182,254-268,332-337` 补齐完整重判和不移动的启用时刻；S1②、S3①分别覆盖换版和 CI 中收紧。可是锁法只写 mission/节点及仓库流，未与规则写入的锁衔接；按租户的额度也不能靠按仓库流锁原子扣减。`P/api/internal/agentrt/store/rules.go:239-252`、`event.go:136-144`，见第 4 节。 |
| A4 accepted → blocked 错误转换 | **已关闭** | `CUT:371-380,393,524` 改为根任务唯一落地 issue，明确不调 `failWork`、不算执行者失败；S3④和 S4 第三次失败用例可检验。确实避开 `P/api/internal/agentrt/store/kernel.go:132-143,176-192` 不存在的 accepted 出边。issue 的动作仍须重走资格和底线，不能绕过 A2。 |
| A5 替代链、关闭、清理 | **未关闭；替代链主体已采纳** | `CUT:383-400,456,526` 已定义根→替代→有效结果、同事务幂等及五项 S4 用例，正确回应 `P/api/internal/agentrt/store/propose.go:754-777`、`prune.go:377-408` 的旧行为。但 S3 已有 declined/stale，关闭条件却列到 S4；`:381` 说撤规则算了结，`:392` 又说保持 mission 开着；`:426` 的全部 stg_verified 也未豁免 declined。见第 3 节。 |
| A6 旧 main 等待、有界恢复 | **已关闭（等待上限需明确取严）** | `CUT:322-331` 已分 Missing/Unknown/Running/Failed、每轮先看 main、6 小时/8 次总限；`:310` parked 不占活动位。S2①②（`:523`）分别能抓旧 M0 永红和 Missing/Unknown 混淆。原来的事实源 `P/api/internal/delivery/release_policy_facts.go:241-244,283-302` 确实不足，需按稿实现新判法。`:361` 的窗口 24 小时不得覆盖总 6 小时；建议明写两者取早，并增加到时让位测试。若要窗口可等满 24 小时，应由 Owner 明确把它排除在总限外，不能实现时自行选。 |
| A7 精确发布快照与核验 | **关闭但带来新洞** | `CUT:409-422` 固定 P/U、审整个发布差异，关闭用 main 浮动构建的问题；`P/api/internal/delivery/run_spec.go:25-42`、`I/k8s/cicd/tekton/pipeline-deliver-platform.yaml:48-70` 支持传两个完整 SHA。但 `:416` 的同一 eligible 检查会挡全部正常待发布结果；`:421` 所指 smoke 实际检查 Trade，见第 3、7 节。S3⑤需改成「定下 P 后 main 又前进」才验证钉 SHA。 |
| A8 待发布、重试、mission 完成 | **关闭但带来新洞** | `CUT:404-406,424-426` 补了独立 pending、20 分钟攒批上限、失败重试和完成门槛；S3⑥有针对性。新资格冲突使它仍不能成功发布；稳定 run 身份与有意重试的身份尚未区分，declined 的关闭也矛盾。`P/api/internal/delivery/service.go:282-285,332-363`、`P/api/internal/agentrt/store/close.go:40-45,74-90`，见第 3 节。 |
| A9 窗口权限、租约、互斥 | **未关闭；撤回首轮“PROD 无 delete”断言** | 作者更正成立，证据见第 6 节。`CUT:351-367` 已补 op/paths/token、CAS 释放和 TOCTOU 交 Owner；但共享窗口读过期对象时仍会无条件 Delete，只替换 Release 不够。`P/api/internal/delivery/window_store.go:183-211`。S3⑦须增加过期读取与新 acquire 并发，不能只测主动 Release。 |
| A10 外部副作用协议 | **未关闭** | `CUT:280-306` 的确定性 R、先意图后动作、祖先对账、六个断点是实质改进。但 `:286`「只改 vocab.go、不改库」为事实错误，所有新类型都会违反现有 DB CHECK；固定 op 的 run 也不能直接重跑已经失败的对象。`P/api/internal/agentrt/migrations/0009_issues.sql:44-63`、`store/event.go:122-128`、`delivery/service.go:332-363`，见第 3 节。 |
| A11 revert 后当前结果 | **关闭但带来新洞** | `CUT:430-433,422,524` 的历史/当前状态分开及 S3⑨关闭「祖先即有效」的旧问题；标准 revert 的认法与 `P/api/internal/lineage/mainresults.go:20-69`、`I/scripts/agentrt/merge_accepted.py:342-363` 相符。但 `:436-438` 先停规则后承诺自动重发，正被 `:416` 拦住，恢复入口仍需定，见第 7 节。未把原认法不识别人手反向编辑重开成新议题。 |
| 534 B1 活已过时仍落地 | **关闭但带来新洞** | `CUT:177-195,500-501` 已补 drop/no_merge/计划替代/曾落地检查和线性化分界；S1⑥、S3②③对应原反例。`P/api/internal/agentrt/store/planchange.go:540-570` 证明确有必要。但把领取资格不加区分地复用于 STG 造成矛盾；目标计划的精确识别仍在 `:572` 延后。`P/api/internal/agentrt/store/planresult.go:247-249,279-287` 有可用的创建来源和 plan used 证据，S1 必须落实并有正反用例，见第 3 节。 |

## 2. P0 现在不可按所写四项验收证明

P0 不只是「删一条 STG RoleBinding」。首轮 A1/B2/B3 和本轮 BRIEF 要求检查所有可得到 main 能力的路径。这里应把专用 lander 的预期权限作为唯一明确例外；一般平台身份、执行/评审任务、CI 不能另有管理员或 main 能力。第二稿既保留专用 workers 凭证，又使用同一个平台 SA，必须明确边界是受信代码还是独立身份，不能混用这两种保证。

两条有源码依据的漏检路径：

1. **CI 的 Secret GET 为 no，仍能拿到克隆凭证。** `I/k8s/cicd/tekton/task-git-clone-gitea.yaml:32-42` 直接以 `secretKeyRef` 注入 `gitea-git-credentials`；`:58-80` 把带用户名/密码的 URL 存为 origin。`pipeline-ci-platform.yaml:40-81,82-86,169-176,207-229` 把同一 source workspace 交给候选代码的 Go/Console 测试。因此测试能读克隆目录的 `.git/config`，无需向 apiserver GET Secret。该凭证是否 main-capable 本次未查；`I/scripts/gitea/rotate-admin-token.sh:2-8` 说明它历史上与管理员令牌相同，更不能默认只读。P0 要逐项验证该身份现在的 scope/团队/分支与标签权限，必要时更换为真正的只读克隆身份，并避免把凭证持久留在共享仓库配置中。
2. **删平台读取绑定，也没有令管理员令牌“只留给 Owner 脚本”。** `I/k8s/cicd/tekton/task-gitea-mirror-sync.yaml:35-40,60-78` 仍注入并使用 `gitea-bootstrap`，`pipeline-deliver-platform.yaml:39-47` 调它。PROD 平台仍能建 PipelineRun/TaskRun（`00-clusterroles.yaml:162-172`、`20-prod.yaml:269-276`）；现有 admission 限定引用任务、禁止 inline，并未把所有管理员凭证使用移出这些任务（`40-admission.yaml:121-135`）。这已足以否定「GET no 即无间接使用」。应把这些具名任务改为最低所需只读权限，或明确隔离其调用权；不是让受检身份试一次 GET 就算通过。

另外，PROD 的 Deployment patch 权限覆盖自己的命名空间（`I/k8s/platform-rbac/00-clusterroles.yaml:115-117`、`20-prod.yaml:181-188`）。所以「只在 workers 挂 Secret」本身不证明同 SA 的其他平台进程无法间接使用它。若 Owner 接受“整个已审批 PROD 代码都是受信主体”，应如实写成该信任假设；若要求平台身份之间也机械隔离，需另做 SA/RBAC/admission 分隔，成本不能藏在一个 Secret 挂载中。

S0 应交付一份不含凭证内容的「身份→可读/可挂载凭证→Gitea 权限→间接执行入口」清单，覆盖 STG/PROD、06 执行/评审、CI 实际 SA、克隆与发布任务；实测读、写 main、合 PR、标签、改保护以及已列间接入口。验收失败则不进 S2/S3。只按文件名/环境变量名检查 06（`CUT:153`）是辅助证据，不是身份权限证明。

## 3. 第二稿新增的资格与事件协议冲突

### 3.1 同一个 eligible 不能原样用于领取、演练和发布

最小成功序列已经构成反例：新 mission → accepted → `eligible=true` → R 推 main 成功 → 写 `stg_pending`。此时 `CUT:189`「main 上从来没有过它」必为假；`:416` 要它再次为真，所以不会有一次正常的 `stg_verified`。这不是缺一个边界测试，而是 ★ 的成功路径不可达。

建议保留一份共用事实判定，显式区分阶段：

- `eligibleToLand`：尚未发生过落地、仍属于当前计划、允许推进 main。
- `eligibleToDeploy`：本操作已经确认落地、R 在固定 P 中仍有效、发布授权仍有效。跳过“从未在 main”条件，保留 no_merge/停止/撤步骤等应阻止新发布的条件。
- `reconcile`：即使撤权/过期，也能确认已发生的副作用；不能先因“已经在 main”判 stale 再跳过对账。这与 `CUT:268,300` 自己的要求一致。

`CUT:181` 只接受 PROD 结果，S2（`:523`）却在 STG 演练；`dry_run` 要到 `landing_prepared`（`:290`）才出现。必须说明演练从何种任务事实取样、如何在领取前确定模式，且无论模式字段如何都没有 main 能力。不要以“为了通过演练”放宽生产资格。

旧 20 件的历史隔离方向可保留：`CUT:182-183,197-201` 的首次启用时间与新 mission 限定独立于 D-L5；D-L5 应逐 mission 确认，不按残留分支数量全标。规则样例 `effective_at=<签名当天>T00:00:00Z`（`:211`）可能早于真正启用，要明确 `landing_enabled.at` 是批准后真正启用的时间，而不是允许事后回填的零点。否则不能无条件宣称当日先前的演练也被隔离。旧 20 件的线上时间本次未读取，不能据此宣称它们已实际被全部排除。

目标拆分计划也必须在 S1 定下来：现有 `planresult.go:247-249` 在 `off_plan_reason` 中保存来源任务，`:279-287` 以接受计划任务和 `plan used` 原因记录采用；`:108-110` 取得 mission 写锁。这为「最后一次被采用」提供材料，但不能只按任务最新创建时间或最后一次失败的计划尝试判断。需要旧计划被替代、新计划被采用、没有新计划被采用三个对照；判不出拒绝是安全退路，不是 ★ 正常目标可工作的验收。

### 3.2 “只改 vocab.go、不改库”不可实施

`CUT:286-287` 列出 17 个新的顶层事件类型。本轮用本地 Python 提取后，与 `P/api/internal/agentrt/migrations/0009_issues.sql:44-63` 的 `event_type_closed` 集合比对：**17 个全部不在数据库允许集合中**。`P/api/internal/agentrt/store/vocab.go:33-35` 明说必须与 DB 同步，`store/vocab_test.go:13-26` 也直接检查一致性；`store/event.go:122-128` 最终把类型写入该列，不会绕开 CHECK。

Owner 有两个具体选项：

- **推荐：仍用已有 `event_type=note`**，增加有版本、封闭 schema 的 landing 子类型及严格字段/转移校验，流仍可用 `landing:<repo>`。现 `note` 有封闭字段表（`store/vocab.go:151-174`）；不能仅放进无检查的任意 JSON。这样才符合“不加表、无新增 DDL”的第一片成本。
- 使用真正的新事件类型：承认需要 migration、词表一致性测试和 STG→PROD schema 发布/审批；重估 S0–S3。不要把“不建新表”写成“不改库”。

S4 的 `landing_replaces`（`CUT:385`）还不在 `:287` 的所谓封闭词表内，应随同确定扩展策略。S1 必须有真实迁移后数据库的事件写入/折叠测试，纯 Go reducer 测试不能发现 CHECK 拒绝。

### 3.3 幂等重试与终态必须分清

`CUT:282,301,424` 同时要求确定 op/run、已存在就接管，以及失败快照重试两次。`P/api/internal/delivery/service.go:282-285,332-363` 的实际行为是：同一个身份永远指向同一个对象；失败的 PipelineRun 再调用仍返回“已存在”，不会重新执行。

要保存「发布操作 P/U + 有界尝试编号」：返回不确定时复用该尝试的 run；确认失败、决定再试时才原子增加尝试号，生成另一稳定 run 名。重启不能重置 10/30 分钟退避和总次数。CI 的“一次补建、一次重跑”（`CUT:323,328`）同理。现六个断点可以保留，另加“第一次失败后第二次真实执行，创建返回不明后不多执行”的对照。

S3 还不能把关闭语义全推到 S4。`CUT:380-381` 已允许 declined/stale/撤规则了结，`:392` 却规定撤规则 parked 保持 mission 开着，`:426` 又要求结果全部 stg_verified。现 `P/api/internal/agentrt/store/close.go:40-45,74-90` 是全部 accepted 即关，`controller/controller.go:444-450` 照常运行。S3 必须一并修改它：

- 开启 STG 的成功根等到 verified；`stg_release:none` 的成功根也要等确认 main，不能 accepted 即关。
- declined/stale/no_merge 是已处置而未交付，需明确与成功目标的展示区别，不能要求它们生成 stg_verified。
- 撤规则只能选一个定义。推荐保留 parked、mission 未交付；显式“不合”才终结。

原子替代创建、依赖解析和分支起算点可继续放 S4；第一片的关闭与失败终结不能一起延期。

## 4. 最后一道闸还差共享锁和计数的对象

`CUT:193-195,332-337` 的 mission/节点 FOR SHARE 给计划变更定义了分界，应该保留。但规则变更不是更新这两行：`P/api/internal/agentrt/store/rules.go:239-252` 用 capability 锁及 rule advisory lock 写新版本，`CurrentRule`（`:96-120`）只读当前版本。照文中的锁法，收紧仍可在读取旧规则后、写 main intent 前提交，而第二道闸拿不到相互排斥的顺序。

建议把现有规则同步锁接进最终决策，统一锁顺序；持锁后重读规则、计划资格及额度，再记意图。必须对并发收紧测试两个次序，不只在 CI 等待中先改规则、之后再进入闸门。

每日额度 `CUT:254-258` 按 tenant，串行却只有 `landing:<repo>`（`:284`）。S6 两仓库时，剩 1 个额度、两仓库同时读 4/5，各自写入就会变成 6/5。`P/api/internal/agentrt/store/event.go:139-144` 只锁传入的一个流。需要 tenant+UTC 日的共同锁/预留，不改变仓库并行度；S6 必须有跨仓库竞争最后一个名额的用例。

`CUT:256` 数“push 已发出”，`:258,334-337` 却在发送前扣。应明确以不可撤销发送意图预留、未发送的确定取消是否返还、unknown 如何保持占用，及跨 UTC 午夜恢复属于哪天。它影响每日限额，不能等实现时任意解释。重放 k 也是新的 op（`:282`），失败重放究竟再扣还是根任务只扣一次，要与计数合同统一。

## 5. 新硬底线名单不是完整的信任边界

`CUT:238-242` 封住 server、actuation、releasepolicy、delivery、agentrt/agentd 等路径，这是改进。但 `P/api/internal/actions/tier.go:26-29` 直接决定 C/D 是否需要审批，`P/api/internal/approvals/handler.go:122-147` 处理批准，二者均不在该硬名单中；`api/internal/actuationpolicy` 也未列入。

**第一片的窄 allow 会拒绝这些文件，所以这不是 S3 的现成立即旁路。** 但 S5 要放宽到“platform 非核心代码”（`CUT:527`），而 `:235,245,556` 宣称硬底线保证信任边界不可能由规则放开。如果规则允许 `api/internal/actions/**`，当前硬名单挡不住；这正是 B3 所要求的实际授权边界，不能靠目录名听起来“非核心”解决。

建议 S3 直接把 `api/**` 全部置于硬底线，保持简单；S5 再以明确代码清单重审需要开放的包，收紧后的底线至少包含 actions、approvals、actuationpolicy。增加“允许 actions/tier.go 的规则仍被硬拒”的测试，它能发现 S1①只测 server 发现不了的漏项。纯展示字符串规则本身的语义局限已在 `CUT:233,558` 如实交 Owner，本轮不重复要求它承担完整语义安全证明。

## 6. A9 争议裁定与仍未关闭的窗口问题

**作者关于 PROD delete 权限的更正完全成立（限仓库清单）。** `I/k8s/platform-rbac/45-release-window.yaml:12-16` 授予对具名 `bifrost-release-window` ConfigMap 的 delete，`:18-28` 绑定到 `bifrost-platform-prod/bifrost-platform`；`kustomization.yaml:11` 确实纳入它。首轮仅看 ClusterRole 和 20-prod 得出“没有 delete”，遗漏这条附加 Role，应撤回。STG 不在该绑定中。线上实际应用情况仍未查。

保留的正确意见是删除无 CAS：`P/api/internal/delivery/window_store.go:211` 主动删除没有前提，`:191-194` 过期读取清理也一样。第二稿 `CUT:358` 只规定 Release 改成带 resourceVersion 的 Update。若 GET 仍调用旧 `getReleaseWindow`，可以发生：读取旧已过期对象 → 另一操作更新为新窗口 → 旧读取执行无条件 Delete，删掉新窗口。新 Release 自己安全也无济于事。

因此要改的是共享窗口的所有自动清理入口，或读过期对象只返回空闲、完全不删除；S3⑦加入这个交错。另需写明续租失败/窗口过期但 run 仍在执行时的阻塞、核对与接管，不把“租约没了”当“外部执行已停”。已有 4.3 设计的接管代次/fencing（`DESIGN-release-lanes-2026-10-24.md:132-153`）不是 `who` 加 op 文本就自动具备的能力。

推 main 与人手浮动发布之间的几秒 TOCTOU 已在 `CUT:363-367,558` 明确交 Owner，属于可见取舍，不再要求第一片偷偷实现整套 4.3。它与上面的误删新窗口是两个问题，接受 TOCTOU 不能视为接受无条件删除。

## 7. STG 的核验与坏落地恢复

两个“没核实”可以用源码进一步缩小：

- CI 克隆任务**已经输出提交 SHA**：`I/k8s/cicd/tekton/task-git-clone-gitea.yaml:22-26,83-85`；`pipeline-ci-platform.yaml:56-68` 的 clone-ui 调用它。S0 应核对并接入相应 TaskRun result、持久关联 P/U/CI/infra 版本，不能只读取 `uiRevision=main` 参数。是否已被提升为所需 PipelineRun/审计结果、线上是否保留足够久，仍未核实。
- **`get_stg_smoke` 不是 platform 健康检查**：`P/api/internal/mcp/catalog.go:208` 路由到 delivery STG smoke；`delivery/service.go:678-703,720-730` 检查 STG frontend 和 Trade gateway/API。`Sources.Deployed` 确实读 platform 三类镜像（`server/agentrt_sources.go:23-34,87-98,186-218`），发布 task 也检查 rollout（`I/k8s/cicd/tekton/task-rollout-verify-platform.yaml:55-62`），但这些不使 Trade smoke 变成平台启动/功能验证。`CUT:421,570` 要替换成具体的平台健康/启动证据；加“Trade 绿、平台健康失败仍不得 verified”的用例。

S3⑤的措辞也应改：`CUT:410-411` 是持到窗口之后才确定 P；若“等窗口期间有人推 N”，按正文 P 应该包含 N，不能要求排除 N。应测试“窗口拿到、P/U 固定之后 main 再推进，实际仍发 P/U”，以及对定快照前混入的迁移拒绝自动发。

坏落地手册 `CUT:436-438` 先撤规则停发布，再说“运行时会自己发”，与 `:416` 冲突。被 revert 的 R 本身又不再是有效待发布结果。推荐第一片明确由 Owner/既有发布入口将受检的 revert 或修复按固定 SHA 发到 STG，核实后再决定恢复规则；若要自动恢复，则需另一个明确授权的恢复操作，不能复用被停用的普通待发布路径。

对账也应分别记录 EverLanded 与 CurrentlyEffective。`CUT:300` 的“祖先且未 revert 才记 landed”只处理仍有效的成功；若 push 成功后、记账前已被标准 revert，应记历史已落地及当前已撤销，不能因为 `MainResults` 排除了撤销项（`P/api/internal/lineage/mainresults.go:55-59`）就当作没有发生过推送。增加这一断点组合，避免与新资格的“永不自动重合”打架。

## 8. B1–B6：采纳程度、成本与第一片

| 条目 | 是否如实处理 | 尚需交 Owner 的内容 |
|---|---|---|
| B1 补丁身份与语义评审 | **已采纳并列选择**。`CUT:316-320,544,558` 不再把 A 的评审冒充 R 的评审；有文件交集先失败，无交集风险明示。 | 可选第一片接受此剩余风险，或 M0≠base 一律增加集成复核。S2④只检验交集拒绝；不等于证明无交集安全。S5 改变策略要重签。 |
| B2 X1–X5 隐藏工作量 | **大部分采纳，状态/凭证成本仍不诚实**。`CUT:167-173` git 卫生，S4 替代链，S3 真实权限负测，S6 触发器/索引/手工门槛接线均保留。 | P0 要覆盖共享凭证与间接入口；X3 须在 typed note 与带 migration 新事件间选。`Sources.Deployed` 的能力已确认，健康检查的差额见第 7 节。S2 演练不证明 PROD main 成功及失败恢复，真实成功必须在 S3/★ 留证。 |
| B3 可判定规则与真实权限 | **大部分采纳，未全闭合**。`CUT:207-278` 明确 tenant、glob、rename、mode/binary、额度口径、30 天期限、分仓库发权、标签与泄露后果；HTTP 风险也明写。 | 硬底线遗漏、tenant 额度的原子性、实际启用时间仍须定。Secret “只挂 workers”不等于 SA 隔离。字符串判纯展示的风险已诚实交 Owner，可接受或进一步缩到具名文件。 |
| B4 push-main 门槛替代 | **采纳**。`CUT:441-451` 明确替代，不再声称原样等价；S0 补完整 vet，S6 共用快测清单。 | 最新 CI 语义需要改当前“任一成功”索引（`P/api/internal/delivery/release_policy_facts.go:298-302`）；加“旧成功、新失败/运行中不得通过”的测试。所用 infra 基线记录为审计依据已明示；Owner 签的是这一口径。 |
| B5 可见性与零写入 | **采纳主体，有一处口径尚窄**。`CUT:461-487` 字段、主动 issue、真实推送者和七环节事件链都补入，Gitea 推送者能力列为 S0 前置。 | `:483` 仍只列 `bifrost-mbp`，没有完全吸收首轮“其他手工身份”的提醒；应覆盖窗口内所有非 runtime 推 main/人工 run，并与线程归属关联。S0 若无法拿到推送者，要把 ★ 标为未验证，不能回落到数尾注。别把 Owner 提目标/正式审批与协调线程代写混在一个计数里。 |
| B6 更便宜的第一片 | **已采纳，且确实较小**。`CUT:37-47,371-400,524-528,540` 移走 R3 和 infra，保留成功路径到 STG 及终止失败可见。 | 它省掉的是自动修复图和 infra 接线，不省 P0、持久对账、S3 关闭、真实数据库验证、固定快照发布。`CUT:531` 的 5–6 工作日/Owner 约 2 小时注明把握低是诚实的，但漏算 DDL/凭证路径之前不能把该数当承诺。 |

推荐仍选这一片：platform Console 窄 allow、一个活动操作、失败开 issue、S4 再 R3、S6 再 infra。修复本报告列出的合同矛盾后，它可以安全地作为首片；**当前文字还不能据此证明安全**。纯展示仍由评审判语义，范围小降低后果，不会替代凭证隔离或发布资格正确性。

## 9. “只有该规则能抓到”的验收覆盖

现有切片表不是空泛验收：A2 的硬拒、A3 的换版、A4 的第三次失败、A6 的旧 main、A7 的夹入迁移、A10 的推送后继、A11 的 revert 都有具体现例，应保留。以下独立义务还不能被其中一个“deny 拦下”或一次 ★ 代替：

| 规则/状态义务 | 现有覆盖 | 最小补充，放在哪片 |
|---|---|---|
| eligible 环境、阶段 | S1⑤只查 dry_run 不计数，未查领取 | S2 的合法演练可推进到 CI；STG 永不真推。S3 的合法 PROD 结果能从 landed 进入 deploy，不被“从未落地”拒绝。 |
| 启用时间与 mission 年龄 | S1②④覆盖换版、早收下 | S1 增加“旧 mission、启用后才 accepted”仍拒；签署前当天结果不因零点回填进入；新 mission 合法结果可进入。 |
| 计划仍有效 | S1⑥、S3②覆盖 drop/no_merge | S1 覆盖目标计划被替代与未被替代；S3 覆盖变更与 main intent 并发两个顺序。 |
| 单提交、有效依赖、终态 | 正文列条件；替代链测试在 S4 | S1/S3：两提交拒绝；依赖未落地/已撤销不能落地后继；declined 不重新领取，显式重试不绕底线。S4 五个替代用例照留。 |
| main 从未有过 | S3③覆盖人工落地后 revert | S1/S3 同时覆盖已经有效落地、已撤销、从未落地三态；读取历史失败不得认定“从未”。对账须先识别本操作的已发生成功。 |
| 路径/模式/纯展示 | S1①③覆盖 server、rename、symlink、binary | S1 增加 actions 审批边界；嵌套 `.env*`、删除、模式位和 `**` 零层/边界；新增被禁调用独立于路径测试。 |
| 文件数/行数/日额度/活动位 | 正文规定，切片表无专例 | S1/S3 各限额边界，重启后 unknown 占额，UTC 换日；S6 两仓抢最后一个 tenant 名额。不要用文件数超限用例冒充行数/日限额。 |
| 规则过期/撤 STG/原子收紧 | S3①只覆盖 CI 中 deny | S3 增加 CI 后过期、合入后 stg_release→none、最终闸门并发收紧；已发出动作撤权后照常对账。 |
| 最新 CI 与有界等待 | S0② vet；S2①②旧 main/Missing/Unknown | S2 增加旧绿新红、新 run 尚未结束、6 小时/8 次用尽让位；窗口 24 小时与总限取早。 |
| 持久事件与有意重试 | 六断点在正文，S2/S3各举一例 | S1 真实 DB 写入及词表一致；S3 失败发布新尝试与未知创建接管分别测试。 |
| 窗口清理与健康核验 | S3⑦⑨覆盖一部分 | S3 增加旧过期 GET 不删新锁、失租但 run 在跑不放行；Trade smoke 绿不代表 platform 健康。 |

这些是对本次新增合同及首轮要求的补齐，不要求为所有不相关功能增设验收。

## 10. C1–C4 与最后交给 Owner 的选项

四个次要意见均已处理：C1 在 `CUT:348` 改成 D2/4.3；C2 在 `:290,522` 将 dry_run 独立成字段并排除真实统计；C3 在 `:320` 修正文案、保留 Work、不追加 TD-383（旧行为见 `I/scripts/agentrt/merge_accepted.py:410-445`）；C4 `:67` 使用真实的 `scripts/agentrt/merge_accepted.py`，不是不存在的 agent-config 路径。C2 的演练领取接线问题已单列，不撤回字段层面的修正。

本轮之后，建议将以下选项一次交 Owner，不继续来回修改“默认都采纳”的表述：

| 待定项 | 推荐 | 另一选项与代价 |
|---|---|---|
| 第一片范围 | 保留 B6 的 Console 首片；S3 包含基本关闭、失败处置和发布对账 | 首片同时 R3：把 S4 的替代图、事务、清理及五项验收一并前移，不能按当前 5–6 日估算。 |
| P0 的证明范围 | 做完整凭证/间接入口清单，消除未授权 main 能力后才开 S2/S3；明确专用 lander 例外 | 若只承诺 STG 隔离、信任整个 PROD SA，需重写 P0 的保证与残余权限；不能把四个负测当作完整强隔离结论。 |
| 状态存储 X3 | 现有 note + 严格版本化子协议，不加 DDL | 新顶层事件：增加 migration 与发布/审批成本。两种都要 reducer、合法转移和断点对账。 |
| 资格、关闭、撤规则 | 阶段化资格；S3 即接关闭；撤规则 parked，declined/stale 表示未交付但已处置 | 撤规则即终结：恢复规则不自动复活旧根，另定义重新启动流程及 UI。 |
| 最终闸门与额度 | 接现有规则锁，增加 tenant/day 原子预留；总等待取 6 小时/8 次，窗口 24 小时不能延长它 | 若窗口等待不计总限，写清暂停计时和最长实际历时，并增加相应用例。 |
| 硬底线及恢复 | 第一片硬拒 api/**；S5 重审实际信任边界。坏落地由既有受控入口发固定 SHA 修复 | 现在支持自动恢复：新增明确授权的恢复操作及失败对账，不能称普通队列顺带完成。 |
| 已明示的剩余风险 | 由 Owner 逐项接受无交集语义漂移、纯展示字符串+评审、窗口 TOCTOU、集群 HTTP | 增加最终集成复核、具名纯文案文件或提前做 4.3，分别增加评审/适用范围/实现成本。 |

资格成功路径和数据库事件 CHECK 是客观冲突，不能用“接受剩余风险”跳过。选定方案后应先把这些合同修正，再交实现；不需要为已明确采纳的意见重复征求批准。

## 核验范围与限制

完成了本地版本/差异核对、首轮与回应逐项对照、RBAC Role/RoleBinding/kustomization 核验、事件 schema 与运行时代码交叉检查、克隆凭证/CI/发布/窗口/计划/关闭/血缘代码追踪；运行了一个纯本地 Python 集合比对，确认 17 个新顶层事件均不在现有 DB CHECK，且 S4 的 landing_replaces 未列入第二稿封闭词表。没有运行 SQL 或项目测试，也没有把这个静态比对称为数据库集成测试。

遵守 BRIEF：未联网、未访问集群/数据库、未用 MCP/SSH、未读取 Secret/令牌内容、未提交 Git、未改被审工作树；没有运行 Go 探针，因此没有使用或改变 Go 工具链/模块缓存。报告是本轮唯一写入产物。

未能实测：线上 RBAC/admission 是否与清单一致；各 Gitea 凭证的真实 scope、团队/分支/标签权限；06 和 CI 实际文件/挂载/身份；Gitea 推送者审计能否取得；线上 TaskRun result 保存与索引；旧 20 件的完整运行时任务/mission 时间；真实断网、不确定返回、租约丢失、Pod 重启及 STG 健康行为。首轮 patch-id/vet 探针未重跑，其结论只作为已提供证据引用。新 landing 代码尚不存在，本次未声称它通过端到端验收。

先改

END OF REPORT
