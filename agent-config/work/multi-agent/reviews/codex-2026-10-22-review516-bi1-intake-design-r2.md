Review 516 · W-31 / BI-1 接业务设计 · 第 2 轮（终审）

结论：先修。本轮有 6 项 A、3 项 B、1 项 C。首轮 A3、A6、A7 在设计层关闭；A1、A2、A4 的原修法成立但带来新洞；A5 尚未完整关闭。七张表本身不是主要问题；可以缩小首批操作面和交付顺序，而不撤掉隐私、确认绑定和接单事务这些必要约束。

本次按 Ops 模式只读审查，不评审 Owner 已确认的 §7.5。`DESIGN.md` 与 infra `19a917eb405ac8ec46f088ba40a961ea30f65938:agent-config/work/crew/DESIGN-crew-intake-2026-10-22.md` 字节一致，SHA-256 为 `9501f52d12172c2efd1eb34191d7b4487aa1140c0b06409b114e282ec6610673`。下文 platform 代码均来自 `36481b9002a93d25f978b4eaad1253c58c6b4e6f`，infra 代码均来自上述 infra 提交，经 `git show` 读取；没有用共享工作树的在制改动作证据。“关闭”指修订设计已经回答该项，不代表尚不存在的 intake 实现已经测试通过或上线。

**R2-A1 — 收紧通用 `writer()` 会取消 viewer 已有的停机和收紧规则能力。**

设计：§5.2，`DESIGN.md:410`、`DESIGN.md:412`；§10 切片 2，`DESIGN.md:628`。

代码：platform `api/internal/actuation/auth.go:212`；`api/internal/agentrt/agentrtapi/propose.go:28`；`api/internal/agentrt/agentrtapi/api.go:100`、`:157`、`:163`；`api/internal/agentrt/agentrtapi/controls.go:18`、`:105`；`api/internal/agentrt/agentrtapi/rules.go:81`。既有契约测试：`api/internal/agentrt/agentrtapi/controls_test.go:39`、`:74`，`api/internal/agentrt/agentrtapi/rules_test.go:51`。

`roleLevel` 显式保留 viewer=1、reporter=2、operator=3、admin=4，未知角色和 intake=0，是首轮 A1 的正确修法。问题在同时规定“回落成 thread 只给 reporter/operator，其他角色报错”：viewer 的 `POST /agentrt/controls` 和 `POST /agentrt/rules/{id}/tighten` 原来由 `stop` 能力明确放行，经过 `actorOf()` 后仍调用 `writer()`。按修订稿实现，携带合法 session 的 viewer 会在写者映射处失败；`whoami` 还会一面宣称有 stop，一面返回 actor_error。现有 `TestControlsAndHosts` 明确要求 viewer 暂停成功。这是旧能力回归，不能用新增 intake 的拒绝测试代替。

最小修法：在通用写者映射中显式保留 viewer 的线程身份，以及 admin、seat、agentd 原有映射；能执行什么仍由各路由的能力表决定。intake 显式映射到 `agent:`，只有 intake 路由接受它。也可以把 intake 映射独立成函数，避免修改既有调用者。保留 viewer 暂停、合法 tighten 的正向用例，同时增加 intake 在这些路由上的负向用例。agentd 经 `actorOf` 的 host 分支仍可工作，不应误报成它也必然被这一改动阻断。

**R2-A2 — 把 Owner 最小入口移到现有决策卡后，私有文字的读取边界没有跟着闭合。**

设计：§2.2，`DESIGN.md:107`；§4.3，`DESIGN.md:317`；§5.3，`DESIGN.md:422`、`:424`、`:431`；§7.3，`DESIGN.md:538`；§10 切片 2，`DESIGN.md:628`。

代码：platform `api/internal/questions/handler.go:22`；`api/internal/questions/transition.go:232`、`:246`；`api/internal/questions/types.go:69`、`:133`；`api/internal/server/questions_wire.go:278`、`:292`；`api/internal/agentrt/store/assess.go:508`、`:550`。infra `k8s/overlays/platform-prod/config/platform-auth.yaml:19`。

修订稿要求 Owner 在现有卡片页确认需求、定优先级和架构分歧，但没有定义这些卡的私有内容怎样展示。现有 `/questions` 和 `/questions/{id}` 对 viewer 及以上开放；`Get/List` 不执行问题读者名单，`Question.public()` 只移除幂等键和指纹，保留标题、正文、选项和答复。因此若沿用卡片正文展示需求说明或内部方案，viewer、reporter、trade-satellite 都能读到；隐藏 `issue:` 事件流对此无效。

还有第二条复制路径：运行时所有未关闭卡片会被 `agentRuntimeOpenCards()` 读成 `AssessItem`，包括正文和选项细节；`GiveAssessment()` 将这些材料写成通用 `task_spec` 产物。只把 intake 卡排除在“规则自动作答”之外，并不会排除这条自动评估路径。它会绕开 §5.3 所要求的 crew 主动裁剪。

这不是说新表本身会泄露，而是切片 2 新增的必要入口尚无满足隔离承诺的内容契约。两种可交 Owner 的修法：推荐通用卡只保存 BI 编号、版本哈希及无敏感内容的选项，切片 2 同时交付一个按问题读者名单取正文的最小确认面；或者给 intake 卡增加明确的受限读取策略，并让自动评估只读裁剪投影。不能将私有全文复制到旧卡后仍宣称“所有文字只在 issue_text”。验收要覆盖卡列表、已知卡 id 直读、答复中的文字，以及自动评估生成的产物；合法 crew/admin 仍能看到所确认的具体版本。

**R2-A3 — 产品名额按显示状态计数，问题暂缓即可释放仍在执行的工作的名额。**

设计：§4.3，`DESIGN.md:289`、`:301`、`:314`、`:323`；§4.4，`DESIGN.md:355`、`:359`；§7.4，`DESIGN.md:547`。

代码：platform `api/internal/agentrt/store/kernel.go:85`、`:101`；`api/internal/agentrt/store/close.go:41`、`:87`；`api/internal/agentrt/store/propose.go:393`。

产品锁解决了两次接单同时看到最后一个空位的问题，但计数对象仍是 `issue.state = active`。反例：上限为 1，BI-2 已接单且 M-1 仍 active；crew 调 `park_issue` 将 BI-2 变成 parked，然后接 BI-3。计数为 0，第二个 mission 可以启动，M-1 并未停止。换 brief 回 clarifying 等显示状态变化也有同类问题。现有 mission 只经自己的状态机改变；修订稿没有规定这些问题状态变化要停止关联工作，且明说问题状态与 mission 状态分开。

最小修法：产品锁内按仍持有名额的业务工作计数，例如本产品存在 `ended_at IS NULL` 的 `issue_work` 的不同 issue 数；明确 awaiting_owner、paused 等非终态工作也占位。同一 issue 增加承诺不应再次按“新问题”占一个名额。显示状态变化不释放工作名额；若另需限制“等待用户确认”的数量，作为另一项业务限制表达。另一种更窄的首版做法是禁止有在途关联时暂缓、改范围或合并，直到工作明确结束。必须覆盖“先暂缓、再接另一条”和正常终态释放的用例，不能仅测两个 take 的并发。

**R2-A4 — 结案谓词仍可使用否定的席位核对，以及换需求后的旧试用回答。**

设计：§4.2，`DESIGN.md:258`、`:259`、`:272`；§4.3，`DESIGN.md:304`、`:330`、`:335`；§7.1，`DESIGN.md:514`。

代码：platform `api/internal/agentrt/store/accept.go:23`、`:30`、`:87`；现有工程验收同时限定检查对象、当前轮次和通过结论，通用事件/外键不会替业务结案补这些判定。

两处仍没有落入所列的程序条件：

- `issue_check.result` 明确可为 `supports` 或 `does_not`，但 resolved/partial 只要求“另有一条 close_check 绑同一问”。一条结论为 does_not 的核对也满足存在性条件。应读取该问、当前版本的有效核对，要求 `result = supports`，不能任取一条历史正面记录覆盖最新否定结论。
- `draft_brief` 只作废开着的 confirm_brief 并清空 brief_confirmed_ask，不作废已有 ready_to_try/check_answer。假设交付说明 R1 的试用问已获 confirmed，随后需求从 B1 改为 B2；旧试用问仍是最新且未被取代，仍绑定本问题的承诺和 mission。即使按 §4.3 的总则要求新录一条绑定 B2 的 close_check，也没有机械条件证明她对 R1 的回答覆盖 B2；席位核对不能替她确认新增范围。`issue_ask.bound_sha256` 钉的是交付说明自身，没有钉它对应的需求版本；`expected_version` 也不能补上这个语义关系。

最小修法：把结案明确写成“对当前范围、当前交付问的正面席位核对”；换需求范围时失效相关试用/答疑问及结案核对，或首版禁止在交付确认过程中原地换范围，要求走明确重开流程。加入 `does_not` 拒结案、B1 已答后改 B2 拒用旧问结案两条用例。首轮 A5 的错问题/错人、需求确认冒充试用、重开旧问这几类已补齐，但整项尚不能签关闭。

**R2-A5 — `served_*` 声称无需事件更新，却仍被现有状态表守卫拒绝。**

设计：§4.2，`DESIGN.md:180`、`:277`；§4.6，`DESIGN.md:382`；§2.1，`DESIGN.md:95`。

代码：platform `api/internal/agentrt/migrations/0002_guards.sql:115`、`:122`、`:196`、`:199`；`api/internal/agentrt/migrations/0003_grants.sql:23`。

`intake_client.served_txid/served_event` 被规定为“活跃列，不写事件”，同时新状态表按 `require_event` 接守卫。现有 `only_liveness()` 只识别 attempt 和 host；对 intake_client 返回 false，随后 `require_event()` 必须取得本事务的 current_event。§4.6 点名了 event_may_write/event_names_row，却没有扩展 only_liveness。按这份接线清单，普通 get_updates 保存已发送最大游标会被拒绝；若干脆不保存，后续 ack 又无法合法前进。给表授 UPDATE 不会绕过触发器。

最小修法：在 0009 中替换 only_liveness，为 intake_client 增加严格白名单：只有 served 二元组可变化，且完整、非空时单调前进；身份、产品范围、撤销状态、acked_* 同时变化必须仍走事件。或者给 served 更新也定义事件并统一修改文档。推荐前者；acked 更新仍写 intake_acked。增加“纯 served 更新可过、混入 products/revoked_at 更新不可过、ack 无事件不可过”的真库用例。

**R2-A6 — “0009 后旧二进制会被拒绝”不是 PROD 发布链或运行时的实际保证。**

设计：§4.6，`DESIGN.md:386`、`:387`；§12，`DESIGN.md:711`；关联终态守卫，§4.2 `DESIGN.md:281`。

代码：infra `k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:623`、`:627`、`:638`；platform `api/internal/agentrt/migrate/migrate.go:145`；`api/internal/agentrt/migrate/check.go:120`；`api/internal/server/agentrt_schema.go:13`、`:75`；旧终态写入 `api/internal/agentrt/store/kernel.go:119`。

§4.6 引用的是迁移命令 `migrate.RunFiles()` 的拒绝，不是 platform-api 的启动检查。实际 PROD 流水线只拒绝候选缺迁移、已执行文件字节不同等情况；数据库比候选多迁移时，638 行只打印 note，继续放行。运行时把此情况标为 ahead 并告警，代码明确写着“Nothing is stopped”。

本轮离线执行了该提交内嵌的 Python 检查脚本，以内存函数替代目录读取和 HTTP health，结果为：

| 候选携带 / 数据库已应用 | 实际退出码 |
|---|---:|
| 0001–0008 / 同样 8 个 | 0 |
| 再加模拟 0009 / 仅 8 个 | 1 |
| 仅 0001–0008 / 再加模拟 0009 | **0**，只打印 older build 的 note |
| 0001 的摘要不一致 | 1 |

这里的 0009 仅是检查脚本输入中的虚构 id/摘要，没有执行任何 DDL。结果证明的是这个迁移检查步骤，不代表整个 PROD 发布已运行。

这对本设计有实际影响：0009 要求 mission 进终态时，同事务结束 issue_work；旧二进制没有该钩子。一旦实际回退到旧版本，它仍会尝试工作，已有关联的 mission 在提交时会被新触发器拒绝。不能把“不允许回退”写成已经存在的机械保护。

交 Owner 两种选项：推荐把本次不兼容回退的拒绝条件落实到发布检查，并明确旧进程并存窗口的处理；或设计旧写入者也能遵守的数据库兼容路径，并用旧/新版本交叉验证。在完成其中一项之前，文档应如实写“当前流水线允许 older build，本次迁移后需另加限制”。候选 digest 跑迁移 Job、先批 DDL 再重发的正向流程已修对，不需要推翻。

**B1 — 五视图不应挡在真实 Dots 试点之前。**

设计：§8，`DESIGN.md:570`；§10，`DESIGN.md:628`、`:631`、`:632`。代码：platform `api/internal/questions/handler.go:32`（既有 Owner 答卡入口）、`api/internal/agentrt/agentrtapi/api.go:118`（能力按路由分开）。

切片 2 已承担最小 Owner 入口，五视图仍排在切片 6 试点之前，额外约两天才能证明核心通道成立。建议先完成 R2-A2 所需的安全确认面，再将顺序改为数据/接口/手册/一种可用本机桥 → 真问题试点 → 五视图、批量优先级、累计预算展示等。保留按 BI-n 查询的完整接口和回执证据，新会话验收不依赖五个成品视图。切片 0b 继续提前，Owner 转述不能代替 Dots 试点。

**B2 — 首批可先关掉 join、并行多承诺和复杂合并操作，不必减掉证据表。**

设计：§4.2，`DESIGN.md:224`；§4.4，`DESIGN.md:360`；§7.3，`DESIGN.md:533`；§10，`DESIGN.md:630`。代码：platform `api/internal/agentrt/store/propose.go:350`、`api/internal/agentrt/store/kernel.go:101`、`api/internal/agentrt/store/keyed.go:37`。

建议首批只支持每条问题一个当前承诺、一个在途 mission；跨人重复保留各自 issue 和回音，暂不自动 join，同人的重复优先通过 add_to_issue 补充。这样保留首轮 A7 的隔离修复，也减少共享 mission 的关闭、锁序和恢复联调。遇到真实跨人重复，由 crew 排队，不启动重复工作；需要共享交付时再补关联能力。可以保留 issue_work 的扩展列和唯一约束，晚开放操作面，无须返工改表。

本机桥也先选 V1 实测可用的 stdio 或 CLI 一种。每日触发、幂等提交、游标持久化和 ack 必须保留；离线自动 outbox 可后移，首批离线明确返回未提交，由调用方用同一幂等键重试。不能提前声称已提交。选择切片应由 Owner 定，不改已确认的最终需求。

`issue_text`、`issue_ask`、`issue_check` 分别承载不可公开的文字、具体问答绑定、当前版本证据，不能仅为了恢复“四张表”把它们塞回通用 artifact 或把授权改回状态历史。若要合表成 JSON，仍需同样的隔离、唯一性、外键或等价验证，并没有现成证据表明会更小。优先减少首批功能分支，比减少表数稳妥。

**B3 — 全路由测试应比较权限效果，不能要求 intake 与匿名的响应完全相同。**

设计：§5.2，`DESIGN.md:413`；§11 I-D2，`DESIGN.md:651`。代码：platform `api/internal/server/server.go:419`、`api/internal/actuation/auth.go:136`。

现有公开 `/auth/capabilities` 对合法 bearer 返回 authenticated=true、principal 和 role；匿名返回 authenticated=false。intake 在这里与匿名响应不同是正确行为，并未获得业务读取或写入权限。建议将断言改为：七路由外不能新增受保护数据访问或副作用；公共身份自省允许明确列出的身份字段差异。遍历还应给参数化路由有效参数和合适请求体，避免两边都被 400/404 或未配置的数据库挡住而误判鉴权有效。另保留旧角色的正向矩阵，才能发现 R2-A1。

**C1 — 最小入口的交付时间表有一处前后矛盾。**

设计：§8，`DESIGN.md:572` 写“切片 2 之前”，而 §10 `DESIGN.md:628` 才交付 request_owner。代码：platform `api/internal/agentrt/agentrtapi/api.go:118` 的当前路由没有 intake。应改为“切片 2 起、切片 5 之前”，避免把尚未实现的入口当成先决条件已经满足。

**首轮 A1–A7 关闭表**

| 首轮项 | 判定 | 修订设计与代码核对 |
|---|---|---|
| A1 角色阶梯越权 | **关闭但有新洞** | §5.2 `DESIGN.md:410` 显式 viewer=1、default=0，配 LoadAuth 闭集，能堵住 `api/internal/actuation/auth.go:160`、`:212` 的原旁路；但 `DESIGN.md:412` 的通用 writer 改法破坏 `controls.go:18`、`controls_test.go:74` 的 viewer 契约，见 R2-A1。 |
| A2 通用读取泄露 | **关闭但有新洞** | §4.2/5.3 `DESIGN.md:209`、`:422`、`:424` 将正文移出 artifact，并同时处理单流/全局过滤，覆盖 `api.go:619`、`:689`、`events.go:119`、`:127` 的原入口；新决策卡入口仍落在 `questions/handler.go:22`、`questions/types.go:133` 的通用读取与 `questions_wire.go:292` 的产物复制路径，见 R2-A2。 |
| A3 跨流游标漏回音 | **关闭** | §2.1/4.3 `DESIGN.md:76`、`:348` 明确复用 `(txid,event_id)`、同快照 xmin 水位及查询内过滤，对应 `agentrtapi/events.go:124`、`:136`；乱序提交反例已被算法处理。R2-A5 是新加回执存储的守卫接线问题，不是否定游标算法。 |
| A4 接单前重复派工 | **关闭但有新洞** | §4.4 `DESIGN.md:355`、`:357` 改为同事务建 mission，通用入口禁止 BI work_id，另有提交时关联约束；能堵住 `store/propose.go:327`、`:387`、`:405` 的原旁路。产品锁也已加入，但 `DESIGN.md:314` 按显示状态计数仍可错放名额，见 R2-A3。 |
| A5 确认未绑本次交付 | **未关闭** | §4.2/4.3 `DESIGN.md:231`、`:330`、`:335` 已绑定 issue、人、问的用途、交付并处理重开；但否定 close_check 和换需求后的旧试用问仍满足所列结案条件，见 R2-A4。对照 `store/accept.go:23`、`:30`，检查对象和通过结论都须有效。 |
| A6 步骤出现冒充通过 | **关闭** | §4.3/7.2 `DESIGN.md:304`、`:308`、`:312`、`:313`、`:528` 改成当前 B/D 的证据谓词，要求 pass 或两轮后 Owner 明确 proceed；卡必须由 admin 本人答且非 rule。对应 `store/cardkinds.go:48`、`store/vocab.go:150` 和 `questions/handler.go:32`，原先“开卡即通过”的问题已回答。规则解析/收紧接线明确列在 `DESIGN.md:379`。 |
| A7 跨人归并破坏隔离 | **关闭** | §4.2/7.3 `DESIGN.md:280`、`:533`、`:535` 限同产品同人，self 限同写者；跨人保留独立 issue、回音和确认。原通用存储 `migrations/0001_core.sql:30`、`store/write.go:44` 不提供人的权限关系，修订已把该关系交给新表和专用守卫。join 可后移，不能退回跨人合并。 |

其余集成核对：

- `BI-n` 保留只针对 WorkID，不应限制普通 mission。现有 goal、brief、assess、gates 创建的 MissionProposal 不填写 WorkID（platform `store/goal.go:99`、`store/brief.go:149`、`store/assess.go:497`、`store/gates.go:294`，路径均在 `api/internal/agentrt/` 下）。保留它们的内部字段和现有行为时，未发现这项限制必然阻断这些入口；不能为图省事禁止所有非 take 的 mission。
- 0009 扩展 actor/event 闭集、保留已有迁移字节、明确新表 SELECT/INSERT、状态表 UPDATE 和新序列 USAGE，与 `migrations/0003_grants.sql:13`、`:18`、`:23` 的机制相符。`issue_text/issue_check` 只追加、复合引用、新主键命名以及排除新表的 legacy_imported 通配，均比首稿明确。`0002_guards.sql:193` 的身份不变检查确实按 `<table>_id` 工作；剩下的具体缺口是 R2-A5，不能靠 grants 补。
- `Tightens` 应仅在 switch 的未知种类 default 返回错误；现有 concurrency、budget、plan、routing 分支验证成功后共用末尾 `return nil`（platform `api/internal/agentrt/rules/tighten.go:25`、`:70`）。修订写的是“没覆盖的种类”，可以正确实现，不将其误判为已确定回归；实施时不能机械地把末尾 return nil 全改成 error。
- 非 rule 的 Owner 答复、撤销前的身份检查、同人归并、提出方投影，以及明确承认“Agent 转述不是本人认证”，都应保留。无需为了简化恢复首稿已被否定的边界。

**首批范围建议及交 Owner 的选项**

推荐先修上述 A，交付“安全收件 → 需求确认 → 最小 Owner 决定入口 → 原子接单 → 当前交付问答 → 结案 → 新会话可查”的完整窄路径，随后立即做 Dots 真实试点。首批必须保留身份/产品/撤销检查、私有文字和卡片投影、问答及证据版本绑定、非规则 Owner 决定、接单事务及名额约束、安全游标/回执、迁移与旧版本兼容策略，以及相应负向验证。五视图、批量分拣、自动 join、多承诺并行、第二种本机适配和离线 outbox 可分批后移；不是删除最终需求。

本轮是最后一轮，不要求再开第三轮设计复核。剩余问题交 Owner 在具体选项中定：R2-A2 选“引用卡 + 最小私有确认面”或扩展私有卡；R2-A6 选机械禁止不兼容回退或实现兼容路径；其余按上述最小修法补齐。也可以保留约 11 天的完整范围，但仍须先修 A，且工期应包含私有卡接线和旧版本验证，不能以尚未实现的保护作依据。

检查范围与未能完成的检查：已完成文档字节核对、指定快照的鉴权/路由/现有测试审读、游标 SQL、mission 调用链、0002 守卫、0003 grants、规则比较与 PROD 迁移检查的静态核对；离线执行了上述 4 个流水线分支场景。没有运行 Go/前端全套测试，也没有声称未来 intake 测试已通过；0009 与 intake 实现尚不存在，未应用 DDL、未做 PostgreSQL 并发/锁序/触发器测试或实际 HTTP 权限测试。没有联网、集群访问、MCP、SSH、提交或发版；没有验证 PROD 现场流水线、Secret、agent-06 口令持有、她 Mac 的连通性、V1–V9 或外部产品能力，也未执行真实用户试点。本次只写本目录的 REPORT.md。

先修：R2-A1（viewer 既有能力回归）、R2-A2（决策卡及自动评估绕过私有读取边界）、R2-A3（显示状态错误释放产品名额）、R2-A4（结案证据仍可无效）、R2-A5（served 游标更新被守卫拒绝）、R2-A6（回退保护与真实发布链不符）。
END OF REPORT
