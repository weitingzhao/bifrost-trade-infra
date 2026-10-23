Review 515 · BI-1 接业务设计 · 第 1 轮

结论：先修。共 7 项 A、5 项 B；未列 C。问题是设计中的权限、证据绑定和事务边界尚不足以兑现所声明的保证，并非对 §7.5 需求本身提出异议。

本次按 Ops 模式只读审查。`DESIGN.md` 与 infra `6f10cbc03a75559412d8a1ef8406d5301da78736:agent-config/work/crew/DESIGN-crew-intake-2026-10-22.md` 的字节完全一致。以下 platform 代码证据均来自 `36481b9002a93d25f978b4eaad1253c58c6b4e6f`，infra 证据均来自上述 infra 提交，均经 `git show` 读取。没有把其他会话工作树中的改动当作基线。

**A1 — 只把 intake 加进七个 RequireAny 路由，不能把它限制在这七个路由内。**

设计：§5，`DESIGN.md:242`、`DESIGN.md:243`；§6，`DESIGN.md:275`。

代码：platform `api/internal/actuation/auth.go:156`、`api/internal/actuation/auth.go:212`；`api/internal/server/server.go:567`。`Require(min)` 比较角色等级，`roleLevel` 只把 executor、agentd 降到 0，未列出的角色默认是 1，与 viewer 相同。配置加载也接受非空的新角色字符串（`auth.go:115`）。因此若按设计只改七个路由的显式允许列表，新 intake 令牌仍能通过其他 `Require(RoleViewer)` 接口，例如读取 Pod 日志；这不是原本无鉴权的 LAN 公共接口，而是获得了新的受保护读取权限。

必须把 `intake` 在角色阶梯中的等级明确设为 0，并核对整个平台的鉴权入口。测试要用真实 intake principal 遍历受保护路由，覆盖 runtime 的 read/stop/propose/upload，以及 runtime 外的 viewer 路由。现有 runtime 的能力表使用显式角色列表，本身不会因新增角色自动放开 stop；漏洞在另一套阶梯鉴权。

**A2 — 禁止 agentd 调接业务接口，仍会从通用产物和事件接口泄露全部问题原文。**

设计：§4.3，`DESIGN.md:204`、`DESIGN.md:207`；§5，`DESIGN.md:245`；§12，`DESIGN.md:480`。

代码：platform `api/internal/agentrt/agentrtapi/api.go:96`、`api/internal/agentrt/agentrtapi/api.go:134`、`api/internal/agentrt/agentrtapi/api.go:619`、`api/internal/agentrt/agentrtapi/api.go:675`；`api/internal/agentrt/agentrtapi/artifacts.go:23`；`api/internal/agentrt/store/artifactsearch.go:194`。

agentd 有通用 read 能力，可搜索产物、按 id 取正文、读指定或全局事件流。目前只排除考试产物和考试事件流。把人的原话存为 `issue` 产物、把引用放入 `issue:BI-n`，不改这些旧入口，agentd 就能先找到 id 再下载任何问题的三段正文；无需获派该问题的任务。新路由上的拒绝与这里无关。

需设计一套覆盖搜索、直接下载、单流和全局事件读取的可见性规则。执行者确有需要时，只交付经裁剪的任务材料，明确这与“可任意读取接业务原文”的区别。还不能仅按 `artifact_kind == issue` 隐藏：`api/internal/agentrt/store/write.go:44` 按正文哈希去重，冲突时保留首次元数据；同一正文先以 `other` 存入会绕过仅按种类的过滤。现有考试隔离已经通过事件引用补了这一类情况（`api.go:637`），接业务也需要基于用途或引用关系的隔离。增加不同 kind 的相同正文、已知哈希直读、事件流旁路测试。

**A3 — 跨问题用全局 event_id 作游标，会永久漏掉较晚提交的回音。**

设计：§2.1，`DESIGN.md:65`；§4.3，`DESIGN.md:209`。

代码：platform `api/internal/agentrt/migrations/0001_core.sql:204`；`api/internal/agentrt/migrations/0002_guards.sql:67`；`api/internal/agentrt/agentrtapi/events.go:27`、`api/internal/agentrt/agentrtapi/events.go:124`。

事件号是 identity，事件链只按各自 stream 加锁。事务 T1 为 BI-2 取得事件 100 后尚未提交；T2 为 BI-3 取得 101 并先提交。同一人的 `get_updates` 读到 101、保存游标后，T1 才提交；以后查询 `event_id > 101` 永远读不到 100。“至少送达一次”因此不成立。现有跨流事件接口已经明确记录此问题，并使用事务快照安全水位和 `(txid, event_id)` 游标解决。

复用现有跨流游标算法，再叠加接收者权限和对外投影；不要直接把全局事件号当提交顺序。加双事务乱序提交测试，以及翻页、断线重读和过滤内部事件后的续读测试。

**A4 — take_issue 接收既有 mission_id，唯一索引只能挡关联行，挡不住已经启动的重复工作。**

设计：§2.2，`DESIGN.md:89`；§4.2，`DESIGN.md:174`；§4.4，`DESIGN.md:213`；§7.4，`DESIGN.md:336`、`DESIGN.md:340`。

代码：platform `api/internal/agentrt/agentrtapi/propose.go:48`、`api/internal/agentrt/agentrtapi/propose.go:80`；`api/internal/agentrt/store/propose.go:327`、`api/internal/agentrt/store/propose.go:387`、`api/internal/agentrt/store/propose.go:405`；`api/internal/agentrt/migrations/0001_core.sql:68`。infra `agent-config/agentrt-rules/prod/standing-envelope-dev.yaml:1`。

`mission_id` 外键意味着关联时 mission 已存在，但现有 operator 的 `POST /missions` 在常备授权内会立即把 mission 变成 active，且 `work_id=BI-n` 不触发任何 intake 检查。两个线程可先分别建出同一承诺的 active mission，再竞争 `take_issue`；索引拒绝第二条关联，却不会撤销第二个已提交、可继续投任务的 mission。甚至无需调用 `take_issue`，就能按现有接口启动该 BI 的工作。这与“接单时才建 mission”和“程序挡重复派工”不符。

应由 `take_issue` 接收 mission 定义，在同一事务中检查 issue、规则、优先级和产品名额，创建 mission、绑定承诺并写事件；已有通用 mission/goal 入口对 BI 关联的工作必须执行同一闸门，或禁止独立创建这种关联。`ended_at` 也需要明确由谁、在什么条件下置值并与 mission 生命周期核对，否则可提前释放槽位或永久占住槽位。产品并发上限要在产品级锁内检查，只锁各自 issue 不足以防止两条问题同时占满最后一个名额。验证失败时不得留下 active mission 或可执行 task。

**A5 — 结案没有把“她确认了什么”机械绑定到本次交付。**

设计：§2.1，`DESIGN.md:66`、`DESIGN.md:68`、`DESIGN.md:75`；§2.2，`DESIGN.md:91`；§4.3，`DESIGN.md:188`、`DESIGN.md:196`、`DESIGN.md:199`。

代码：platform `api/internal/agentrt/store/accept.go:23`、`api/internal/agentrt/store/accept.go:87`；`api/internal/agentrt/migrations/0002_guards.sql:492`。现有工程验收会把证据绑定到具体 attempt、轮次、提交，并拒绝用旧结果验收新工作；通用事件和 artifact 外键没有替 issue 自动提供这种关系检查。

本设计的 `confirmed` 同时用于确认需求说明和确认试用，而 `close_issue` 只要求存在被服务人的 confirmed/partly 回答及一个席位产物 id。按这个机械条件，“需求写得对”的回答也满足 resolved 的枚举检查；重开前的试用回答也可能被用于后来一次交付。`expected_version` 只证明写请求使用当前版本，并不能证明其引用的回答针对当前交付。席位用自然语言核对是否支持结论，是有价值的补充，不能替代回答对象的约束。

应明确：`in_reply_to` 属于同一 issue、同一被服务人、对应当前未失效的问题；brief 确认绑定 brief 哈希；业务结案绑定本次 `ready_to_try`、承诺和交付版本。重写 brief、重开、重新交付时使旧确认失效。`resolved`/`partial` 的回答用途和 verdict 对应关系、`already_possible` 的有用性确认也应分别规定，席位核对产物必须绑定同一回答。测试包含错 issue、错人、brief 回答冒充试用回答、旧交付回答和并发换版。

**A6 — “步骤走过”与“证据通过”混在一起，大级可在卡刚开、复核仍有 A 时满足字面的接单条件。**

设计：§4.3，`DESIGN.md:191`、`DESIGN.md:192`、`DESIGN.md:193`；§7.2，`DESIGN.md:320`、`DESIGN.md:324`。

代码：platform `api/internal/agentrt/plan/rule.go:16`、`api/internal/agentrt/plan/rule.go:36`；`api/internal/agentrt/store/accept.go:23`；`api/internal/agentrt/store/cardauto.go:41`。现有完成规则读取绑定对象的具体事实；决策卡也可能由规则回答，不能仅凭“有卡/已答”推断 Owner 本人作了决定。

状态表把 `in_review` 的进入条件定义为复核方独立，把 `owner_deciding` 定义为开了卡；而 active 条件是所需步骤“都走过”。于是当前设计没有区分：已发起复核和有效复核结论、已开决策卡和 Owner 选定允许继续的方案。更新 design 后，也没有结构化规定旧 review 是否仍有效。§7.2 的文字要求比 §4.3 可执行的条件更强，不能把二者留给实现者自行补全。

把 `intake-gates` 定义成证据谓词，而不是历史状态出现过的列表：当前 brief 已确认、当前 design 有合格独立复核、A 已关闭或由 Owner 明确裁决、所有必要卡对当前范围已有允许继续的本人答复。规则答案和 Agent 转述不能冒充本人决定。记录被检查的规则版本和产物哈希，缺失或过期即拒绝。对 `raise_class`、重新分级、换设计与接单采取同一事务锁顺序，级别不得被重分级、重开或合并降回较低值。状态只用于显示等待位置，不能当授权证据。

**A7 — “同产品、同现象归并”跨越了以被服务人为单位的读取和确认边界。**

设计：§2.1，`DESIGN.md:63`、`DESIGN.md:64`；§4.2，`DESIGN.md:159`、`DESIGN.md:170`；§7.3，`DESIGN.md:328`。

代码：platform `api/internal/agentrt/migrations/0001_core.sql:30`、`api/internal/agentrt/migrations/0001_core.sql:204`；`api/internal/agentrt/store/write.go:44`。复用的 artifact/event 存储只有写者和通用正文，没有每位被服务人的访问、确认或合并权限关系；这些必须由新模型提供。

Owner 和太太可能分别提出同产品同现象的问题。按归并规则合成一条后，`issue.served_person` 仍只能保留一个人。若提出方视图返回合并后的全部原话，会泄露另一人的内容；若保留原问题可见性却重定向到不可见的主问题，另一方会失去进展和回音。即使解决读取问题，也不能用一人的试用确认替另一人结案。

首版最简单的修法是只允许同产品、同 `served_person` 的归并；self 提议也应保持其写者边界。跨人重复只关联为同一内部工作，保留各自 issue、回音和确认。若坚持跨人归并，需要显式参与者、逐段可见性与逐人结案模型；这已超出当前四表草图。不能在合并时顺便扩大权限或降低级别。

**B1 — 泄露令牌的实际能力被低估；“原话非空”只能证明有文本，不能证明本人说过。**

设计：§6，`DESIGN.md:269`；§12，`DESIGN.md:482`、`DESIGN.md:483`。

代码：platform `api/internal/actuation/auth.go:195`；`api/internal/agentrt/agentrtapi/propose.go:20`；`mcp/platform/src/runtimeTools.ts:20`。

即使修好 A1，拿到这把令牌且能连 LAN 的人仍可读绑定人的历史问题和回音、补充内容、提交伪造的 `user_words` 和 `user_verdict`；能力不只是“以她名义提问题”。600 文件权限不能阻止同一 macOS 用户下、已有本机命令能力的 Agent 读取文件。服务端验证的是 Agent 的 bearer 身份；`RUNTIME_DATA_NOTE` 也是提示文本，不是来源认证或提示注入隔离机制。

§12 已承认诱导与转述失真，因此这里主要是纠正风险说明和验收措辞：所有此类证据持续标为“Agent 转述”，不得升级成“平台验证了本人说过”。明确盗取令牌后的读范围、伪造确认范围及撤销语义。若要对恶意或被注入的 Agent 也保证本人确认，需要另有由人控制、绑定具体问题内容的确认渠道；仅加一段非空检查和另一个 AI 核对不能提供该保证。

**B2 — “照 0002/0003、放一条签名规则”还缺少几个现有代码不自动支持的接点。**

设计：§4.2，`DESIGN.md:145`、`DESIGN.md:181`；§4.3，`DESIGN.md:198`；§10，`DESIGN.md:412`。

代码：platform `api/internal/agentrt/rules/rules.go:203`、`api/internal/agentrt/rules/rules.go:258`；`api/internal/agentrt/rules/tighten.go:25`；`api/internal/agentrt/store/propose.go:99`、`api/internal/agentrt/store/propose.go:112`；`api/internal/agentrt/store/localpath.go:5`；`api/internal/agentrt/migrations/0002_guards.sql:136`、`api/internal/agentrt/migrations/0002_guards.sql:158`、`api/internal/agentrt/migrations/0002_guards.sql:185`；`api/internal/agentrt/migrations/0003_grants.sql:13`。

应在切片 1/2 的改动清单中点名以下事项，而不是假定现有框架自动接住：

- `intake-gates` 是新规则种类。现有闭集解析器会拒绝；需增加解析、规范化正文、有效规则读取及“收紧”比较。`Tightens` 对未覆盖种类最终返回 nil，不能只加解析分支而漏掉比较，否则删掉必经步骤也可能被当作无签名收紧。规则不存在、无法解析或过期时应拒绝接单。
- 新 `agent:` actor 需接入 Go 的 `kindOf`/`CheckWriter`。旧的幂等回放检查只对 thread 执行，`store/keyed.go:43`、`store/propose.go:99` 说明不能把它直接当作 intake 的身份及撤销检查；正常读写和命中旧幂等响应前均需验证当前 token 绑定、产品范围和撤销状态。
- 新 artifact kind 除 SQL CHECK 外，还要接入 Go `ArtifactKinds` 和事件 bodies。`legacy_imported` 的现有 body 闭集也不接受任意新增来源字段（`store/vocab.go:127`、`store/vocab.go:166`），导入应明确使用已有格式或扩展词表。
- 新表要显式授 SELECT、必要的序列 USAGE 以及 INSERT/UPDATE；旧 0003 的一次性 GRANT 不覆盖以后新增的表。守卫需扩展 event-to-table 和 event-to-row 映射；`intake_client` 的主键叫 actor_id，`issue_work` 是复合主键，不能直接套“表名 + _id”的不可变身份检查。还要点名风险级别单调、身份绑定和关联键不可被普通更新改写的专用约束。

这些都是既有框架的具体接线成本，应计入估时与负向测试。

**B3 — Console 的“Dots 已读到”没有服务端可保存、可核验的回执。**

设计：§2.1，`DESIGN.md:65`；§3.3–3.4，`DESIGN.md:118`、`DESIGN.md:126`；§8，`DESIGN.md:381`。

代码：platform `api/internal/agentrt/store/messages.go:73`、`api/internal/agentrt/store/messages.go:111`、`api/internal/agentrt/store/messages.go:134`。现有信箱将读取与接收者确认分开，并持久保存 ack；取事件的接口则只返回游标（`agentrtapi/events.go:150`）。

设计把游标保存在 Dots 记忆里，四表没有相应字段，也没有 ack 动词，却要在 Console 和新会话里回答“提出方读到没有”。服务端返回了响应不代表响应抵达；若在发送时推进已读，网络丢包会产生假已读。若以客户端下次传来的 cursor 为回执，也必须明确保存位置、所属 Agent、单调规则、允许确认的范围，并处理最后一页长期没有下一次请求的情况。

可以在现有七工具内给 `get_updates` 增加显式确认上次已接收游标的参数，由桥成功持久化响应后确认；或复用现有信箱的 ack 思路。分别显示“待领取 / Agent 已确认收到 / 已转告用户”，后两者不能混为一谈。只有可持久核验的回执才能支撑 §10 的新会话验收。

**B4 — 数据切片缺少 PROD 迁移的独立前置动作，发版审批单本身不会应用新表。**

设计：§4.2，`DESIGN.md:142`；§10，`DESIGN.md:412`。

代码：infra `k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:526`、`k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:609`、`k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:627`；`k8s/agentrt-migrate/README.md:34`、`k8s/agentrt-migrate/README.md:49`。platform `api/internal/agentrt/migrate/migrate.go:139`。

切片 1 的 Owner 列只写了新表决定、签规则和 PROD 平台发版审批。实际 TD-411 路径是：STG 发布流水线自动先迁移；PROD 只对比候选提交的迁移文件与 `/health.agentrt_schema_applied` 的 id/sha256，缺 0009 就在 rollout 前拒发，必须由 Owner 批准 DDL 并以候选镜像 digest 建迁移 Job，再核对、重发。拿旧 `:prod` 镜像跑原样 Job 不会包含这次新迁移。

把这个依赖、责任人和候选 digest 核对写入切片 1；追加迁移，不改 0001/0002/0003 的已执行字节。实际流水线是否已应用到集群，本轮未查，实施前还需核实，不能从仓库 YAML 推断现场已生效。

**B5 — 3.2 允许在切片 1–3 后启动，但普通问题所需的 Owner 确认和优先级入口在切片 5 才交付。**

设计：§2.2，`DESIGN.md:93`；§9，`DESIGN.md:402`；§10，`DESIGN.md:413`、`DESIGN.md:416`。

代码：platform `api/internal/agentrt/agentrtapi/propose.go:28`；`mcp/platform/src/runtimeTools.ts:10`；`api/internal/agentrt/agentrtapi/api.go:118`。现有本机 runtime MCP 使用线程身份，admin 才映射为 owner；现有路由没有新的 issue 操作，operator crew 不能替代尚未交付的 Owner 操作面。

除两类常备例外外，普通问题需 Owner 定优先级；self 提议还需 Owner 确认 brief。切片 1–3 只有数据、API/crew 工具和手册，不能据此宣布普通 intake 工作流可运行。将最小的 Owner 确认/优先级界面提前，或明确切片 2 同时交付 Owner 可亲自使用的最小入口，再把完整五视图留在切片 5。

V1–V3 的实际能力探针也宜放到数据实现前，与设计定稿并行验证；这不是要求本轮研究厂商产品。否则数天之后才知道 A 不成立，而 B 的网页又不在当前交付表内。当前约 7.5 天的实现粗估还没有充分列出上述权限隔离、规则解析、回执和迁移联调工作，应在修订后重估。Owner 转述只能验证内部流程，不能代替“Dots 提交、读回音、转告她”的试点验收。

已检查并认为方向成立的部分：

- 需求说明与方案分开、把原话/理解/提议分栏、把 Agent 写者与被服务人分开，符合 §7.5；没有把需求本身交给 AI 批准。业务结论也没有直接复用 mission 的工程完成状态。现有 `store/close.go:41` 只据任务验收收 mission，确实不能代表用户试用成功。
- 复用运行时、保留不透明 `product` 键、把方法判断留在产品档案，未发现必须把 Screening、交易协议或产品算法写入 platform 的设计要求。下单请求只收件和解释，不授予交易动作；符合 D10 和双飞轮边界。
- 基线最高迁移为 0008，新增 0009 的前向路径合理；草图所引用的 actor、artifact、mission 主键确为 text。actor 种类、产物种类和事件类型确实是 CHECK/闭集，需要向前扩展；保留旧取值后，没有从四表草图发现必然破坏旧行的字段类型冲突。新 `agent` 的 `tool` 应保持 NULL，现有 `0001_core.sql:14` 将非空 tool 保留给 executor。最终 DDL、守卫与 grants 仍需真库验证。
- 现有 `store/keyed.go:37` 按写者、路由、key 隔离，并比较请求摘要、在事务内保存响应；这是适合复用的基础。它只去重同一次请求，不替代不同 key 的业务唯一性、跨写者锁或 `expected_version` 检查。
- 静态 token 表从环境加载、撤销需额外查 intake_client、删除 Secret 值后需重启的判断与 `auth.go:92` 相符。推荐本机 stdio/CLI、不开公网入口，与 v4 的 `DESIGN-agent-runtime-2026-10-08.md:431`、`:445` 及 v5 的 `DESIGN-agent-runtime-v5-2026-10-14.md:148` 相符。没有把未核实的 Dots/Duet/Grok 能力当成既成事实。
- 手册进入公开仓库、人的姓名和原话进入运行时的分工合理；infra `agent-config/AGENT_FACTS.md:354` 证实公开仓库约束。真实原话还应避免进入实现测试 fixture、提交说明和公开报告；回音会回到厂商侧是设计已知的数据流，投影中排除内部证据是必要的边界。

更简单且仍满足需求的实现形状：保留 issue 与工程 mission 的分离，状态负责显示、当前版本证据负责授权；复用已有安全跨流游标和回执模式；首版限制同一被服务人的归并；由一个事务完成接单和建 mission。先打通“提交 → 确认需求 → Owner 最小分拣入口 → 接单 → 回音 → 接收回执”，再完善五个 Console 视图。这不需要再造通用工作流引擎，也不需要提前做公网连接器。

本次完成的是指定提交上的静态设计审查、调用链/约束核对和文档字节一致性检查。未运行未来 intake 的单元或集成测试，因为对应实现尚不存在；未应用迁移、运行 PostgreSQL 并发事务或执行 HTTP 权限探针。按任务限制，未联网、未访问集群、未用 SSH/MCP、未验证现场 `agentrt_schema_applied`、令牌和 Secret 配置、现有 BI 产物数量、她 Mac 的连通性或 V1–V7 的厂商能力，也未验证真实用户端到端试点。上述并发场景是依据代码构造的反例，不标作已执行测试。没有提交、发版或修改指定仓库；本轮只写本目录的 REPORT.md。

先修：A1（intake 角色阶梯越权）、A2（通用读接口泄露原文）、A3（跨流游标漏回音）、A4（接单前已启动 mission 的旁路）、A5（结案确认未绑定本次交付）、A6（步骤状态代替有效授权证据）、A7（跨人归并破坏隔离与确认）。
END OF REPORT
