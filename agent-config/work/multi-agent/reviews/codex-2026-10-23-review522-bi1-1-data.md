> 复核 522（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/bi1-1-data-r2`。报告里的 `probes/`、`tests.jsonl` 等证据在本机 `~/agent-work/codex-review-522/`，不进仓库。

# Review 522 · W-31 BI-1 切片 1 · 第一轮

结论：**先修**。发现 8 项 A、1 项 B。主要问题是 BI mission 的继承开卡路径没有接上文字保护，以及部分证据、名额和身份规则只在 Go store 中成立，持有正常运行时 DML 权限的写入者仍可绕过。

审查对象为 `/Users/vision-mac-trader/agent-work/bi1-1` 的 HEAD **`31d0efead4b78e60e065cced7c18b4271ffae2ae`**，基线 **`ca645debff6d545ef7ad6e3fa9762921f9dad4b3`**。指定分支 `w31/bi1-1-data-r2` 当前不存在，因此按简报使用 HEAD；基线上共有 `7231b420`、`22288707`、`a7f6d003`、`105c51bc`、`31d0efea` 五个提交。审查前后该工作树均无改动。

已对照定稿设计指定章节、515/516/518 三轮设计复核及回应、实施者的 22 项选择和五项设计异议。下文代码路径均相对于被审查仓库。没有将切片 2 的路由、令牌配置、事件隐藏、问题页及 `request_owner` 尚未交付本身列为缺陷；A1 是本切片新增的 `TakeIssue` 已会调用的另一条开卡路径。

## A：STG 前必须修复

### A1 — TakeIssue 的封外 mission 开出普通卡，绕过已经上线的 BI 文字保护

**位置：** `api/internal/agentrt/store/issuetake.go:91`、`:95`；调用链证据为 `store/missiondecide.go:51`、`:65`、`store/planchange.go:612`、`api/internal/server/questions_wire.go:134`、`api/internal/questions/transition.go:112`。**设计：§4.4、§5.3、§十一 I-D7 与 Owner 的 Y=A。**

正常接单创建封外 mission 时，传入的 `ask` 原样交给 `proposeMissionTx → askMission`。后者生成普通的 `Mission: <title>` 卡，正文包含 goal、success 等 mission 材料，只在正文写 `Work: BI-n`。`store.Card` 没有 `WorkID` 字段，现有 `agentRuntimeAsk` 也不发送 `work_id`，因此卡片库看见的 `Question.WorkID` 是空串。1b 的 `businessIssueCard()` 只检查这个字段，不检查正文。

即使 crew 已正确裁剪 mission 材料，Owner 在这张卡的正常 “none + 文字” 入口解释需求、引用她的原话，仍会被接受；通用卡片投影保留答复文字，viewer 等读者可以取得。后续给真正的 BI 卡加模板和评估过滤，也识别不到这张未标记的卡。这重新打开了 518 指出的答复文字泄露路径。

**离线实测：** 捕获实际 `askMission` 构造的 Card，确认它只有正文里的 BI 编号，没有 WorkID；用相同形状的 Question 调用实际 `parseAnswer`，`allow_text=false` 下仍接受合成私有标记，实际 `public()` 投影保留标记。仅补上 `Question.WorkID=BI-522` 的对照即拒绝该文字。没有使用真实原话，也没有启动 HTTP 服务。

**修法与防线：** 使所有由 BI 工作派生的开卡路径携带可识别的 BI 身份，并遵守中性内容、无文字答复、无自动评估的契约。加一次真正从 `TakeIssue` 封外分支出发的开卡、答文字、通用读取负向测试；当前 `issues_test.go:610` 的回调只返回卡号，未检查卡的身份和内容。

### A2 — Agent 自提议也能使用 fault_small，跳过 Owner 优先级

**位置：** `api/internal/agentrt/store/issuetake.go:192`，尤其 `:196`。**设计：§4.3 常备例外、§7.4 第 4 条、§十一 I-D5 A。**

`fault_small` 只检查规则开关、`risk_class=small`、分类 `fault` 以及没有已有优先级证据，没有检查 `served_person` 非空或排除自提议。于是 Agent 的 `kind=proposal, served_person=NULL` 问题，在 Owner 只确认 brief、crew 分类为 small/fault 后，仍可不经 Owner 定优先级接单；mission 只要符合 dev 常备授权即可 active。确认 brief 与定优先级是两个独立决定，前者不能代替后者。

**离线实测：** 对实际 `takePredicate` 提供当前有效规则、Owner 已确认的自提议、small/fault 分类、空名额和无 priority 证据，结果无错误并返回 `exception=fault_small`。这是使用模拟查询结果的 Go 谓词探针，不是真库集成测试。

**修法与防线：** 对自提议无条件要求当前 B 的 Owner 优先级，先于常备例外处理；故障例外至少要求确有被服务人。增加自提议 small/fault 的拒绝用例，并保留人的 small/fault 正向用例。

### A3 — 决策点不属于 D 的哈希，保持方案正文不变即可删掉 Owner 闸门

**位置：** `api/internal/agentrt/store/issueevidence.go:129`、`:167`、`:169`；`store/issuetake.go:328`、`:344`。**设计：§4.3 第 5、6 条，§7.1、§7.2。**

`PutDesign` 把正文 `Text` 与额外的 `Decisions` 分开接受；D 只计算 `Text` 的哈希，`Decisions` 不与正文头部核对，也不进入哈希。接单时，Owner 必须决定哪些点、哪几个字母允许继续，完全来自当前 `issue_design_put` 事件的这份额外元数据。

反例：原方案正文明确有 D1，元数据为 `D1 → A`，独立复核已经通过，但 Owner 尚未决定，接单被拒。再调用 `PutDesign`，保持 Text 逐字相同、令 Decisions 为空；新文字行的 D 仍相同，旧复核仍有效，但现在决策列表默认为 `[]`，即使 large 规则要求第 6 条，也没有任何未决点。也可在同一 D 下改变 Proceed，让原本不允许继续的 Owner 选择变成允许继续。

**离线实测：** 同一 B、D 和复核证据下，实际 `takePredicate` 在有 D1 元数据时拒绝；移除元数据后通过。`PutDesign` 允许这一写法、且仅哈希正文，已逐行核对；未在真库执行两次写入。

**修法与防线：** 将规范化决定表放入所确认、所复核的方案正文，从该正文解析并核对；或使决定表和正文共同定义不可分离的方案版本，所有复核及 Owner 证据绑定该版本。测试同正文删点、改 Proceed 和正文头部与参数不一致三种情况。

### A4 — 正确类型的伪造 issue_taken 能绕过接单证据和产品名额

**位置：** `api/internal/agentrt/migrations/0009_issues.sql:722`、`:730`、`:733`；`:540`、`:550`、`:918`。**设计：§4.2 守卫、§4.3 接单谓词及产品锁、§4.4、§十切片 1。**

`guard_issue_work` 对 INSERT 只验证事件是 `issue_taken`、B 是当前 B、mission 的 work_id 匹配且未终态。`guard_issue` 对 active 主要验证事件类型。二者均不读取 brief 确认、classification、Owner priority、review、Owner decisions、有效规则或产品名额，也不拿产品锁。延迟 BI 检查只验证关联行存在。

因此正常 runtime role 可以在同一事务中：创建 BI mission；追加合乎 Go 词表、但声称闸门已过的 `issue_taken`；插入当前 B 的 `issue_work`；更新问题为 active、version 加一。已有 brief 但尚未确认、没有任何分类/优先级/复核，甚至没有有效 intake-gates，也不触发上述守卫的拒绝。对同产品不同问题重复此操作，不受 one-live-per-issue 索引限制，产品锁和产品上限均被绕过。

这不是旧二进制单独建 mission 的既有测试场景：那个场景没有关联行，确实会被延迟检查拒绝；这里同时提供了一行未经过真正接单检查的关联。`issue_taken` 这个名字不证明 Go 的 `takePredicate` 运行过。

**验证性质：** 依据全部相关触发器和 grants 静态推导；未真库执行。**修法与防线：** 把关键谓词和产品级串行化落实到数据库可强制的写入入口，并防止正常 DML 绕过。负向测试须使用 runtime role、正确事件类型和合法关联，同时分别缺一项证据、无规则、超产品名额；不能只测错误事件类型或缺关联。

### A5 — 结案守卫只认事件类型，正确类型的事件即可在无回答时结案

**位置：** `api/internal/agentrt/migrations/0009_issues.sql:553`、`:557`、`:584`；对照 Go 检查 `api/internal/agentrt/store/issueclose.go:102`。**设计：§4.3 结案谓词、§7.4 第 6 条、§十切片 1。**

对任意尚未结案的问题，runtime role 追加 `issue_state_changed`，正文使用合法 `change=close`，然后执行：

```sql
UPDATE agentrt.issue
SET state = 'closed', conclusion = 'resolved', version = version + 1
WHERE issue_id = '<该问题编号>';
```

现有守卫只检查结论变化的事件类型、不能直接改已有结论等条件；没有检查最新试用问、当前 B、confirmed/partly、工作绑定或最新 supports。表 CHECK 也只保证 closed 与 conclusion 同步。因此完全没有交付、没有她的回答的问题可被标 resolved。相同路径以线程写者设置 declined，也绕过“只有 Owner 或本人接单前撤回”的限制；already_possible 的无在途工作和确认条件同样只在 Go 里。

**验证性质：** 静态触发器反例，未真库执行。`issueclose_test.go:347` 只验证用 `issue_replied` 关案会失败，没有用正确的 `issue_state_changed` 验证无依据关案也会失败。

**修法与防线：** 数据库按结论检查真正的结案依据，并绑定本次关闭事件中的 ask；以 runtime role 对 resolved、partial、already_possible、declined 分别做“正确事件、错误事实”的负向测试。

### A6 — 直接写入时，外部 Agent 的产品范围、撤销和日限并未统一生效

**位置：** `api/internal/agentrt/migrations/0009_issues.sql:448`、`:464`、`:610`、`:619`；对照 `api/internal/agentrt/store/intake.go:296`。**设计：§4.6 新 actor 的身份检查、§5.2、§7.4 第 4、5 条；简报要求守卫覆盖直接 runtime DML。**

三个同源缺口：

- `guard_issue` 仅在 INSERT 分支查询 intake_client。UPDATE 分支对 `issue_added`/`issue_answered` 的 Agent 写者不再检查当前范围或撤销状态。已撤销 Agent 的合法 `issue_added` 事件配合 `UPDATE issue SET waiting_on=..., version=version+1` 仍没有对应身份拒绝；也没有要求事件命名的文字真的插入。
- `guard_issue_text` 校验是否同一被服务人或自己的提议，`intake_voice_ok` 校验撤销和人，但二者都未检查该 issue.product 是否仍在 client.products 内。一个只获 screening 范围的 Agent，可在同一被服务人的 finance 问题上，用正确 issue_added 事件直接插入 reading/proposal。
- 10/20/3 的日限计数只在 `intakeDaily`，由 SubmitIssue/AddToIssue 调用。合法事件配合法 INSERT 可越过提交、补充和自提议日限；数据库没有计数、限额检查或对应的 Agent 串行锁。即使 Owner 把 daily_submits 设为 0，匹配人物及产品的新 issue INSERT 仍不因日限被拒。

**验证性质：** 静态核对，未真库执行。现有 `intake_test.go:140` 只通过 store 测日限，不能覆盖这些旁路。

**修法与防线：** 对每种 Agent 写入统一验证当前 client 身份、撤销和产品，再按实际语义计日限并串行化；补直接 SQL 的超限、撤销后 UPDATE、同人跨产品 INSERT 负向测试。不要只在 HTTP 或重放前增加检查。

### A7 — 没有两轮停线约束，第三轮通过可直接替代 Owner 裁决

**位置：** `api/internal/agentrt/store/issueevidence.go:238`、`:270`；`store/issuetake.go:313`；`api/internal/agentrt/migrations/0009_issues.sql:250`。**设计：§7.2 的“最多两轮”、§4.3 第 5 条、Owner 既定停线规矩。**

RecordReview 只要求 Round ≥ 1，不读取此前轮次、不限制重复/倒退/第三轮。SQL 也只有 review_round ≥ 1。接单只要最新 review 为 pass 就接受，不检查该 pass 是否已经越过两轮停线。

第一、二轮均为 fix 后，crew 可以直接记录第三轮 pass，不需要 Owner 的 review_dispute，也不需要 Owner 批准窄确认。重复使用 Round=1 也没有总次数约束。现有测试覆盖了“两轮 fix 后 Owner proceed”，没有覆盖“第三轮 pass 无 Owner”这个绕法。

**离线实测：** 实际 `issueEvidence` 将 round=3 的 pass 认作合格复核，未要求 Owner 证据；写入侧及 SQL 没有更强限制，已静态核对。

**修法与防线：** 服务端和数据库依据真实复核历史执行轮次与停线规则；需要额外复核时须有明确的 Owner 授权依据。增加两轮 fix 后直接第三轮 pass、重复轮次和伪造跳轮的拒绝测试。

### A8 — 作废问时可以同时改写答者、答复通道和原话时间

**位置：** `api/internal/agentrt/migrations/0009_issues.sql:683`、`:686`、`:689`。**设计：§4.2 一问只答一次及身份守卫、§5.4 的转述来源和撤销后追查。**

`guard_issue_ask` 在修改 superseded_at 时，只比较 verdict、words_text_id、answered_at 三列，然后立即 RETURN NEW；后面的完整答复比较和 `intake_voice_ok` 不执行。said_at、answered_by_actor_id、answer_channel 被遗漏。

对一条已由 Agent 回答、尚未作废的 confirm_brief 问，线程可使用正常 issue_state_changed/supersede 事件，在同一次 UPDATE 中作废它并把 answered_by_actor_id 改为 owner、answer_channel 改为 console，甚至改 said_at。保留那三列即可通过当前分支，所有相关非空和 actor 外键仍可满足。这不会令已作废问重新获得接单效力，但会把历史上的“经某 Agent 转述”改成另一种来源，破坏按 answered_by_actor_id 追查被撤销 Agent 的回答。

**验证性质：** 静态触发器反例，未真库执行。**修法与防线：** 作废只允许 superseded_at 改变，其余整行保持不变；特别补“作废 + 改答者/通道/said_at”的负向测试，覆盖已答与未答问。

## B：应修复

### B1 — 负向测试没有逐项覆盖新增守卫，若删除关键分支仍可保持测试通过

**位置：** `api/internal/agentrt/store/intake_test.go:264`、`:371`，`store/issues_test.go:401`，`store/issueclose_test.go:347`；对应 `migrations/0009_issues.sql:610`、`:759`。**设计：§4.6“逐项写负向测试”、§十切片 1。**

已有真库测试确实使用 runtime/owner/reader 身份，覆盖 served、降级、跨人合并、部分复合外键和无关联 BI mission，方向正确。但除了 A 项的缺测外，仍没有直接打到 `guard_issue_text` 的错误正文哈希、文字 creator 与事件 writer 不一致、错误 text_kind，以及 `guard_issue_check` 的旧 B/D、错误 report_text kind 等新增分支的负向测试。只让 store 拒绝参数，或只测试曾经产生的合法数据，不能证明数据库防线还在。

另一个例子是 `TestIssueTablesHoldTheirRows` 对 legacy_imported 只实际写 person；它没有逐表验证七张新表均不能被 legacy 写入。代码中的排除列表目前正确，但删漏其中某一张表不会被这条测试发现。

补一张“守卫条件 → runtime role 下最小反例 → 预期拒绝”的测试矩阵，使用正确事件类型且只违反目标条件。无需为本报告另造通用测试框架。

## 22 项实施选择的核对

仅列涉及未满足的 Owner 决定或被实现弱化的项；其余选择未发现与定稿决定冲突。对草图 NULL 比较、预取 identity ID、补充接口所需列及 close_check 事件类型的四项调整，未发现推翻 Owner 方案的问题。

| 选择 | 判定 |
|---|---|
| #7：试用答复后 awaiting_user → active | 这个显示状态调整与流程一致；但 SQL 实际允许任何 issue_answered 从 awaiting_user 回 active，不验证就是该次试用答复。不能将它当接单或工作存在的证明，见 A4。 |
| #11：fault_small 只在无 priority 证据且 tenant=dev 时适用 | 所加限制成立，但没有保留“Agent 自提议一律由 Owner 定优先级”的决定，见 A2。 |
| #19：数据库限制 Agent 只能写它看得见的问题 | 实际缺少 UPDATE 的 client 检查，以及文字写入的产品范围检查，见 A6。 |

方案决定表额外参数及复核轮次停线的缺口不属于报告中已明确列出的 22 项选择，分别见 A3、A7，不能据此认为 Owner 已同意这些行为。

## 迁移、隐私、并发与兼容核对

- **旧迁移字节：** `git diff ca645deb -- 'api/internal/agentrt/migrations/000[1-8]*'` 为空。只有一个前向 0009。actor/event 旧取值保留；不新增问题产物种类。
- **同签名替换：** 核对了 only_liveness、event_may_write、event_names_row。移除新增 intake/issue 分支和 legacy 排除条件后，旧分支逐字一致；attempt 的 LIKE 转义也一致。同名同参数替换保留旧属主与 ACL 的方式正确。
- **授权：** 新七表、四个 identity 序列和新函数逐项授 runtime；text/check 只 SELECT/INSERT，状态表增加 UPDATE，无新 DELETE。对照 infra `k8s/data/role-matrix/expected.yaml:304`，该矩阵按 schema 的 DML 并集记权限，原来已有 idempotency DELETE，因此新增表不需要把矩阵改成逐表授权。未实测安装后的 ACL。未把 PROD agent_reader 的 pg_read_all_data 读取能力列为新缺陷，这是设计明文接受的残余风险。
- **文字主路径：** Submit/Add/DraftBrief/Answer/Design/Review/Reply/Close 的正文均进入 issue_text；没有发现这些正常路径自动将 issue_text.body 复制进事件、产物、日志或 mission。TakeIssue 接收另外的 MissionProposal，工程材料公开是 §4.4/§5.3 已决定的裁剪边界；它不构成自动正文清洗。仍存在 A1 的派生决策卡答复旁路。通用 events 当前看见 issue 元数据，是切片 2 要增加隐藏的已知阶段状态，本报告不重复记 A。
- **正常 store 锁序：** TakeIssue 为 writer → 产品锁 → issue FOR UPDATE → mission 编号锁 → 事件流；MergeIssues 先按数字顺序锁两条问题；Close/Park/Reopen 先问题行再问行、再事件流。mission 终态触发器只 UPDATE issue_work，不锁 issue。issue 文本/问/证据事件没有 AttemptID，也没有在持 mission stream 后新增读取 live attempt 的锁操作；未静态发现简报提醒的“流锁 → 延迟 attempt 外键”死锁模式在这些新增路径重现。A4/A6 的直接写入则没有同等串行化。
- **终态与旧写入者：** mission_80_end_issue_work 在原有 mission UPDATE 同语句结束关联，复用当前 mission_state_changed；普通 mission 无关联时不改新表。延迟 BI 检查针对未来 INSERT/UPDATE work_id；它不会反查迁移之前已经存在的 BI mission。没有读取现场数据，故不能证明部署库不存在这种存量，也不能宣称迁移已在现有数据上安全通过。
- **跨流游标：** 抽出的 EventsAfter 保留同一语句快照 xmin、水位以下事务过滤、(txid,event_id) 排序和满页游标；LatestEvents 保留原 latest 语义。未发现此次抽取导致的乱序提交漏读。现有 TestEventsAfterKeepsLateCommits 确实构造了小号事务晚提交的情形，但本次环境未能运行它。
- **旧/新交叉：** 已静态对照原 MoveMission/Append 与新终态触发器、旧直接建 BI mission 与延迟检查、旧 AuthFile 对独立 intake_tokens 键的行为。实施者所述真旧二进制交叉探针没有被本次独立重跑；不能将其自述当作本次测试结果。没有检查或操作 STG/PROD 发布链现场。

## §十切片 1 交付对照

“done”仅表示相应实现齐备且静态核对成立；涉及 PostgreSQL 的项目不表示本次真库验收已通过。

| §十第 1 行项目 | 状态 | 依据或缺口 |
|---|---|---|
| 单一前向迁移、七张表、旧迁移不变 | done | 0009；0001–0008 diff 为空 |
| agent actor、事件类型 SQL/Go 两侧 | done | 新词表及 kindOf/CheckWriter 接线齐备 |
| 显式表、序列、函数授权 | done | 静态完整；未实测 ACL |
| require_event、专用守卫、只追加和禁止删除 | partly | A4–A6、A8，及 B1 的负向测试缺口 |
| legacy_imported 排除新表 | done | 七表明确排除；测试覆盖待扩大 |
| only_liveness 同签名替换、served 单调推进 | done | 条件和原分支正确；真库四类探针未执行 |
| mission 终态自动结束 issue_work | done | 数据库 AFTER UPDATE 触发器；本次未运行 |
| BI work-id 保留与提交时检查 | partly | 独立建 BI mission 被挡；伪造关联仍可通过，A4 |
| 提交、补充、brief、问答、证据、状态、合并、回执 store | partly | 功能存在；A1–A3、A6–A8 |
| intake-gates 解析、规范化、收紧、未知种类拒绝 | done | 新规则测试及相关离线测试通过 |
| 原子 take、版本、在途工作产品名额 | partly | 正常 store 路径成立；A2–A4、A7 |
| 当前 B/D 的接单证据谓词 | partly | 决定表脱离 D、停线和自提议优先级缺口 |
| 最新交付问、当前 B、最新 supports 的结案谓词 | partly | Go 主路径齐备；数据库关闭旁路 A5 |
| 共用跨流游标与乱序提交测试 | done | 算法保留；测试存在，本次未真库运行 |
| 要求的负向测试与旧/新交叉验证 | partly | 大部分场景已写；B1 和 A 项反例缺测，真库及真旧二进制未独立执行 |

## 实际检查与限制

1. **通过：** `go build ./...`；`go vet ./internal/agentrt/... ./internal/server/`；`git diff --check ca645deb HEAD`。Go 缓存使用简报指定的共享路径，`GOPROXY=off`、`GOSUMDB=off`，TMPDIR 设在本目录。
2. **五个离线行为探针通过：** 自提议 fault_small；同 D 删决策点后完整接单谓词放行；第三轮 pass 算有效复核；实际 askMission 不携带 BI 卡身份；未标记卡接受并公开答复文字、标记对照拒绝。源文件、Go overlay 和输出保存在本目录 `probes/`。overlay 只增加审查测试，没有修改被审查工作树。模拟事务查询的探针验证 Go 分支，不代替 SQL、锁或事务提交测试。
3. **尝试运行：** `go test ./internal/agentrt/... ./internal/server/ -count=1 -json`。顶层测试记录为 162 pass、437 skip、2 fail（含子测试的全部记录为 263 pass、515 skip、2 fail）；13 个包 pass、2 个包无测试、2 个包 fail。两处失败是 TestNotConfigured 与 TestEvidenceFromGitea 的 httptest 无法监听本机端口并 panic，均为沙箱 bind 拒绝；不是据此认定代码回归。数据库/Redis 测试因没有可用夹具而跳过，不能称整套测试通过。完整输出为 `tests.jsonl`。
4. **未能做真库检查：** 按简报尝试 PostgreSQL 17 initdb，失败于 shmget：Operation not permitted；尝试配置 mmap 后仍同样失败。Redis 在 127.0.0.1:56522 的 bind 被拒，日志明确记录 abort。因此未能创建角色、应用 0009、以 AGENTRT_TEST_REQUIRED=1 跑真库套件、执行 A4–A6/A8 SQL 反例、并发名额/死锁探针、存量数据迁移或真旧二进制交叉验证。没有成功启动的测试服务需要保留；PostgreSQL 初始化已自行清除未完成的数据目录内容，Redis 启动中止。未执行任何 DROP DATABASE。
5. 全程未联网查询、访问集群、使用 MCP/SSH、提交、发版或改动指定工作树。只写本报告所在目录与共享 Go 缓存；没有修改工作区技术债台账，因为简报明确禁止写到其他目录。

先修：A1（BI mission 卡文字旁路）、A2（自提议跳过优先级）、A3（同哈希改决策闸门）、A4（直接接单绕过证据和名额）、A5（直接结案绕过本人回答）、A6（Agent 范围/撤销/日限旁路）、A7（两轮停线未强制）、A8（作废时可改答复来源）。
END OF REPORT
