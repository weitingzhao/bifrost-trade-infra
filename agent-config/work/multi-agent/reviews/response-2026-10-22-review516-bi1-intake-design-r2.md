# 复核 516 第 2 轮：逐条回应（随修订稿交第 3 轮窄确认）

- 修订稿：`DESIGN-crew-intake-r3.md`。底稿是 infra 已落地的那份（`19a917eb` 和 `b7535a57` 里逐字节相同，SHA-256 `9501f52d…6610673`，就是第 2 轮读的 `DESIGN.md`）。
- 代码证据都按 `git show <sha>:<path>` 读：bifrost-platform `36481b9002a93d25f978b4eaad1253c58c6b4e6f`、bifrost-trade-infra `b7535a57d884f8227859c643fd129104e22212b0`（本文引到的 infra 文件和 `19a917eb` 相比没有变化）。`路径:行` 不带前缀的指 platform `api/internal/` 下。
- **六条 A 全部接受，都改了设计，没有驳回的。** B1、B2、B3、C1 也全部接受。第 2 轮报告里交 Owner 的两件（R2-A2 的形态、R2-A6 的做法）各写成一道选择题：I-D7、I-D8，推荐项就是本稿已经按着写的做法。
- **7.5（需求说明）一个字没改**：修订稿里 7.5 一节和底稿逐字节相同（该节 SHA-256 `b14cf5e1…df892bd46`，`cmp` 核对过）。没有哪条修法需要改需求说明。
- 按 Owner 10-22 的决定（「接业务设计走 A：修 6 条 A、按复核建议削薄首批，再做一次只针对这 6 条的窄确认复核」），第 3 轮只看六条 A 的修法。削薄首批的改动单独列在末节「削薄首批改了什么」，不在第 3 轮范围内。
- 没有运行任何测试（实现还不存在），没有读集群，没有查 PROD 流水线现场（V9），没有提交或改仓库。

## 逐条

| # | 发现（一句） | 处理 | 修订稿位置 | 依据的代码证据 |
|---|---|---|---|---|
| R2-A1 | 第 1 轮修法把通用 `writer()` 的 thread 回落收窄到 reporter / operator，会让 viewer 失去现有的暂停和收紧规则能力 | **修了，按构造**：`writer()` 对现有角色一字不改（admin → owner；`seat:` → 席位；其余含 viewer、trade-satellite → `thread:<session>`），`actorOf()` 的 agentd → `host:` 也不动；只在最前面加一条「角色是 intake 就报错」作防御。intake 的写者另走新函数 `intakeWriter()`，只有接业务路由调用。`roleLevel` 失败即关照旧（显式 viewer=1、default=0）。测试：现有 `TestWhoami`、`TestControlsAndHosts`、`rules_test.go` 原样必须过；加写者映射的逐角色表驱动单测和旧角色正向矩阵；intake 打 `/controls`、`/rules/{id}/tighten`、`/whoami` 负向 | 5.2「写者映射」「全路由测试」③；4.6「鉴权配置」；十二 #6；I-D2 | `agentrtapi/propose.go:28-41`（writer：admin、`seat:`、其余 thread）；`agentrtapi/controls.go:18-24`（actorOf 先 agentd 再 writer）、`:105-111`（setControl 用 actorOf）；`agentrtapi/rules.go:81-91`（tightenRule 用 actorOf）；`agentrtapi/api.go:100`（stop 含 viewer）、`:157`、`:163`；`agentrtapi/controls_test.go:39`（viewer → thread:s9）、`:74-77`（viewer 暂停成功）；`agentrtapi/rules_test.go:51`（viewer 收紧走到存储层）；`actuation/auth.go:212-225` |
| R2-A2 | Owner 最小入口用现有决策卡后，卡片库对 viewer 及以上开放、不看读者名单，而且开着的卡会被读成评估材料写进 `task_spec` 产物；私有文字的读边界没闭合 | **修了，按构造（I-D7 A）**：卡由运行时按固定模板生成，`request_owner` 只收问题号、用途、版本，不收文字；卡上只有 `BI-n`、用途、需求说明 / 方案 sha256 前 12 位、只读问题页链接，选项中性（p1…/decline；confirm `<sha12>`/not this version；A/B/C；proceed/stop），无选项细节。`work_id = BI-n`（`workIDPattern` 扩到 `BI-`），`BI-` 卡拒「none + 文字」答复；`agentRuntimeOpenCards()` 跳过 `BI-` 卡，不评估；规则本来认不出这种卡，谓词也拒 `rule` 通道。切片 2 同时交付只读问题页（`GET /agentrt/issues/{id}` 按读者名单 + Console 一页只读），Owner 在页上看全文和完整哈希，在卡片页答。答复落库：选项进 `issue_check`；确认需求说明写 `issue_text`（`response`，`person:owner`，通道 `card`，正文是选项标签）和 `issue_ask` 回答。验收覆盖卡列表、按已知卡号直读、答复文字、评估产物，以及 admin 在问题页能看到所确认的那一版 | 5.3「Owner 的决策卡」与「测试」；4.3（卡那一段）；4.6「卡片库」；2.2 `request_owner`；八开头；十 切片 2；十一 I-D7；十二 #1 | `questions/handler.go:21-25`（Get/List 只要 viewer）、`:32-35`（答卡只 admin）；`questions/transition.go:232-270`（Get/List 不查读者）、`:109-120`（`none` 加文字不受 `allow_text` 管）；`questions/types.go:133-140`（`public()` 只去幂等键和指纹）；`questions/canonical.go:41`（`workIDPattern` 只收 W-/TD-/LANE-）、`:210-217`；`server/questions_wire.go:133-173`（运行时开卡，不带 work_id）、`:268-301`（开着的卡读成 AssessItem，含正文和选项细节）；`agentrt/store/assess.go:497-529`（写 `task_spec` 产物）、`:537-555`（复制标题、正文、选项）；`agentrt/store/cardkinds.go:89-90`（没有任务号的卡认不出种类）；`questions/store.go:104-116`（读库不校验 work_id，旧二进制照常读） |
| R2-A3 | 产品名额按 `issue.state = active` 计，暂缓一条还在执行的问题就能放出名额，再接第二条 | **修了，按构造**：名额在产品锁内数「本产品有在途关联（`issue_work.ended_at IS NULL`）的不同问题数」，不看显示状态；mission 在 proposed / awaiting_owner / active / paused 都算在途；名额只在 mission 进终态时（库里触发器结束关联）释放；同一问题已有在途关联就拒（首批一个问题一个在途 mission），所以加承诺不会重复占名额。另外首批在有在途工作时，暂缓、换需求说明、合并都拒。用例：先暂缓再接另一条（暂缓被拒；直接改状态也不释放名额）、终态释放、等 Owner 批的 mission 占名额 | 4.3 接单谓词第 7 条、`parked` 行、锁的顺序；4.4；7.4 第 5 条；2.2 `park_issue`；十 切片 1；十二 #13；I-D4 | `agentrt/store/kernel.go:85-90`（mission 状态机）、`:101-124`（`moveMission` 唯一入口）、`:123`（唯一一条改 mission 状态的 SQL）；`agentrt/store/close.go:41-45`、`:86-93`（done / stopped 只由 mission 自己的状态机写）；`agentrt/store/propose.go:393-404`（封外 mission 停在 awaiting_owner） |
| R2-A4 | 结案谓词只要求「另有一条 close_check 绑同一问」，结论 `does_not` 也满足；换需求说明后旧试用问不作废，也没钉它对应的需求版本 | **修了，按构造**：`issue_ask.brief_sha256` 记开问时的当前 B（只有澄清阶段的 `needs_info` 可空，`confirm_brief` 必须等于 bound）；`issue_work.brief_sha256` 记接单时的 B；试用问到工作的复合外键带上 `brief_sha256`，所以试用问只能挂在同一版 B 下接的工作上；开问时守卫要求 `brief_sha256 = 当前 B`。结案（resolved / partial）要：最新、未作废的试用问，`brief_sha256 = 当前 B`，回答对，且这一问的**最新一条** `close_check` 结论是 `supports`、绑当前 B；`close_check.result` 限 supports / does_not。`draft_brief` 换版作废所有开着的问；首批有在途工作或开着的试用 / 答疑问时直接拒（不在交付过程中原地换范围）。用例：最新核对 does_not 拒结案；B1 已答后改 B2 拒用旧问结案；旧 B 下的工作不能发试用问 | 4.2 `issue_work`、`issue_ask`、`issue_check` 与守卫；4.3 结案谓词、作废（含第 2 轮反例的推演）；2.1 服务端规则；2.2 `draft_brief`、`reply_to_requester`、`close_issue`；十 切片 1；十二 #14 | `agentrt/store/accept.go:23-28`（工程验收同时限定检查对象、轮次、提交，通用外键不会替业务结案补这些判定）；第 2 轮报告的反例（R1 已 confirmed 后 B1 → B2） |
| R2-A5 | `served_*` 说是不写事件的活跃列，但现有 `only_liveness` 只认 attempt 和 host，`require_event` 会拒；授 UPDATE 也绕不过触发器 | **修了，按复核推荐的第一种**：0009 用 `CREATE OR REPLACE FUNCTION agentrt.only_liveness` 同签名替换，attempt、host 两支逐字照旧，加 `intake_client` 一支：除 `served_txid`、`served_event` 外整行不变，新值两列非空，二元组严格前进，往回走报错；混了别的列就返回 false、照常要事件（回执写 `intake_acked`，设置和撤销写 `intake_client_set`）。表上补 served / acked 成对非空的 CHECK，修了「acked 非空而 served 为空时 CHECK 判 NULL 放行」的洞。用例：纯 served 能过、混入 products / revoked_at 不能过、回执无事件不能过、served 往回走报错 | 4.2 `intake_client` 与守卫第 2 条；4.6「活跃列」；2.1 `get_updates` 规则；十 切片 1 | `agentrt/migrations/0002_guards.sql:112-132`（`only_liveness`）、`:196-199`（先问它，再要 current_event）；`agentrt/migrations/0003_grants.sql:23-27`（UPDATE 授权不绕触发器）、`:35`（函数 EXECUTE 只覆盖当时已有的） |
| R2-A6 | 「0009 后旧二进制会被拒」只是迁移命令的拒绝；PROD 流水线对「库比候选新」只打 note，运行时只告警；旧二进制没有结束关联的钩子，回退后会被新触发器卡住 | **修了，事实先改对，再按构造做兼容（I-D8 A 的 ①）**：文档如实写三处现状（迁移命令拒、运行时只 WARN 不停、PROD 流水线放行）并指出新旧 Pod 并存是每次发版都有的，不只是回退。兼容路径：关联行的 `ended_at` 改由 mission 表上的 `AFTER UPDATE OF state` 触发器在同一语句里写，Go 不加钩子，新旧二进制走同一条 `UPDATE agentrt.mission SET state`；`BI-n` 直建在库里提交时拒（旧二进制失败即关）；intake 令牌只写在新顶层键 `intake_tokens:`，旧 `AuthFile` 只有 `tokens:`、`yaml.Unmarshal` 忽略未知键，所以回退时 intake 令牌是无效令牌，不会按旧阶梯 default 1 变成 viewer（第 1 轮 A1 在回退时不复发）。剩下的降级写明：接业务路由没了、`issue:` 流元数据（无文字）经旧 `/events` 可见、旧二进制会评估 `BI-` 卡（卡上本来没有正文）。交叉验证：新代码测试直接覆盖库内行为；另起上一版二进制连迁到 0009 的本机测试库跑四个探针。I-D8 A 的 ② 让 PROD 流水线对「库比候选新」拒发、Owner 带理由放行，和 STG 一致（STG 的迁移步骤已经拒旧版）——这是 infra PROD 流水线改动，交 Owner | 4.2 守卫（终态触发器、`BI-n` 检查）；4.4 `ended_at`；4.6「结束关联」「鉴权配置」「回退」及其后「旧二进制和 0009 的库」整段；5.2「令牌」；4.3 事件类型（去掉 `issue_work_ended`）；十一 I-D8 与残余风险；十二 #12 | infra `k8s/cicd/tekton/pipeline-deliver-platform-prod.yaml:623-642`（`:638-640` 只打 note）；`agentrt/migrate/migrate.go:145-148`（只迁移命令拒）；`agentrt/migrate/check.go:115-125`（标 ahead）；`server/agentrt_schema.go:13-22`、`:75-76`（「Nothing is stopped」）；`agentrt/store/kernel.go:119-123`（先 Append 再 UPDATE，触发器里的当前事件就是 `mission_state_changed`）；`agentrt/store/event.go:130`（设 `agentrt.event_id`）；`actuation/auth.go:66-68`（`AuthFile` 只有 tokens）、`:98`（非严格 Unmarshal）；infra `pipeline-deliver-platform.yaml:141-148` 与 `task-agentrt-migrate-stg.yaml:103-104`（STG 用候选镜像跑 `platform-api agentrt-migrate`）；`agentrt/migrate/migrate.go:90-95`（`Run` → `RunFiles`） |
| B1 | 五视图不该挡在真实 Dots 试点之前 | **接受**：顺序改成 数据 → 接口（含 Owner 卡和只读问题页）→ 手册 → 一种本机桥 → **试点** → 五视图等（切片 6）。新会话验收不靠五视图，靠按 `BI-n` 查的接口和回执。切片 0b 照旧提前；Owner 转述不能替代试点 | 十 切片 4–6；八开头；九「顺序」；一 Owner 行；零「Owner 的最小入口」「工期」 | `questions/handler.go:32`（既有答卡入口）；`agentrtapi/api.go:118-170`（能力按路由分开） |
| B2 | 首批关掉 join、并行多承诺、复杂合并，不减证据表；本机桥先一种，outbox 后移，离线回「没提交」用同一幂等键重试 | **接受**：一个问题同时一个在途 mission（`issue_work_one_live` 按问题，三列唯一约束和 `commitment` 列留着）；`take_issue` 不再有 `join`，跨人重复各自保留、排队，交付上线后对另一条发 `check_answer` 以 `already_possible` 结案；合并只限两条都没接过单的；本机桥只做 V1 证实可用的那一种，保留每日定时、幂等提交（桥按内容生成键）、游标文件与回执，离线回「没提交」、不存 outbox；七张表一张不减 | 4.2 `issue_work`；4.4；7.3；2.2；3.3；六 A；十 切片 4 与「后移」；十二「刻意不做」 | `agentrt/store/propose.go:350`（`proposeMissionTx`）；`agentrt/store/kernel.go:101`；`agentrt/store/keyed.go:37-44`、`:100-101`（键留 7 天，次日重试仍去重） |
| B3 | 全路由测试应比权限效果，不能要求 intake 与匿名响应逐字相同；参数化路由要防 400/404 误判；保留旧角色正向矩阵 | **接受**：① 闸门层沿用现有 `auth_routes_test.go` 的哨兵做法，把每条路由的中间件链套在哨兵外面，按 principal 比「能不能走到处理函数」，不经真处理函数，所以参数、请求体、没配库都不会造成假阴性；断言 intake 可达 ⊆ 匿名可达 ∪ 7 个接业务路由。② 处理函数自己认令牌的公开路由列显式表：`/auth/capabilities` 允许身份字段不同，`can_operate`、`can_admin` 必须 false。③ 旧角色正向矩阵与写者映射表驱动单测 | 5.2「全路由测试」；零「身份」；十一 I-D2 | `server/server.go:419`（公开的 `/auth/capabilities`）；`actuation/auth.go:136-154`；`server/auth_routes_test.go:21-32`（哨兵）、`:44-77`（chi.Walk） |
| C1 | 第八节写「切片 2 之前」，入口在切片 2 才交付 | **改了**：「切片 2 起、到试点（切片 5）为止」 | 八开头 | `agentrtapi/api.go:118-170`（现有路由没有 intake） |

第 2 轮报告「其余集成核对」里的四点，本稿都照着保留，没有为简化退回：`BI-n` 保留只针对 work_id，goal / brief / assess / gates 的 mission 不填 work_id、行为不变（4.4）；0009 显式授权与主键命名照旧，现在多写了新函数的 EXECUTE 和三个替换函数保留授权（4.2 末）；`Tightens` 只在未知种类的 default 返回错误，不动已有分支末尾的 `return nil`（4.6 规则行，原文「没覆盖的种类」照旧）；非 rule 的 Owner 答复、重放前的身份检查、同人归并、提出方投影、「Agent 转述不是本人认证」都在。

## 首轮 A1–A7：这次修法有没有把它们重新打开

| 首轮项 | 第 2 轮判定 | 本稿之后 |
|---|---|---|
| A1 角色阶梯越权 | 关闭但有新洞（R2-A1） | 阶梯失败即关、`tokens:` 角色闭集照旧；写者映射对旧角色复原；intake 令牌另放一个键，回退时也不会落到 default 1 |
| A2 通用读取泄露 | 关闭但有新洞（R2-A2） | 文字仍只在 `issue_text`；卡只有编号和中性选项、只收选项、不评估；只读问题页按读者名单 |
| A3 跨流游标漏回音 | 关闭 | 算法不动；`served_*` 现在真能写进去（R2-A5） |
| A4 接单前重复派工 | 关闭但有新洞（R2-A3） | 单事务接单、`BI-n` 保留不动；名额改按在途工作；结束关联改由库里触发器做，提前释放、永久占位都由构造挡住 |
| A5 确认未绑本次交付 | 未关闭（R2-A4） | 问和工作都绑 B；结案要当前 B 下最新试用问和最新一条 supports；交付中不许原地换范围 |
| A6 步骤冒充通过 | 关闭 | 证据谓词不动；Owner 决定仍只认 admin、非 rule 的卡答复，现在只认选项键 |
| A7 跨人归并破坏隔离 | 关闭 | 更严：跨人连 join 都不做，不共享 mission |

## 削薄首批改了什么（B1、B2；不在第 3 轮范围内）

第 3 轮可以跳过下面这些；它们只缩小首批的操作面和顺序，不改六条 A 的修法，也不删需求（表和列都在）：

1. `take_issue` 去掉 `join`；跨人重复不共享 mission，排队后用 `check_answer` → `already_possible` 结案（2.2、4.4、7.3）。
2. 一个问题同时只挂一个在途 mission：`issue_work_one_live` 从 `(issue_id, commitment)` 改成 `(issue_id)`（4.2、4.4）。`commitment` 列和三列唯一约束保留，以后开放并行只换这个部分索引。
3. `merge_issues` 只并两条都没接过单、没有开着的试用 / 答疑问的同人问题（2.2、7.3）。
4. Owner 的「调高级别」首批由他在线程里说、crew 用 `classify_issue` 往上调；他自己的按钮、Console 五视图、成批定优先级、「新问题」表单都排到试点之后的切片 6（2.2、7.3、八、十）。谢绝理由首批在线程里说（卡上不能写字，这一条是 R2-A2 带出来的）。
5. 本机桥只做 V1 证实可用的那一种；每日定时、幂等提交、游标文件、回执保留；离线 outbox 和第二种适配后移；离线时回「没提交」，调用方用同一幂等键重提，桥在调用方没给键时按内容生成键（3.3、六 A、十 切片 4）。
6. 切片顺序：0 第 3 轮 → 0b 核实 → 1 数据 → 2 接口与 Owner 入口 → 3 手册 → 4 一种本机桥 → **5 试点** → 6 五视图等；「后移」一行列 join、多承诺、带工作的合并、outbox、第二种适配（十）。
7. 工期：到试点约 10 天（第 2 轮稿到试点约 11.5 天，含五视图）；拿掉约 2.9 天，为六条 A 加约 1.4 天；切片 6 约 2 天；后移约 1.5 天；全部约 13.5 天（零、十）。

## 给第 3 轮的范围（只看这六处）

| 项 | 在修订稿哪里看 |
|---|---|
| R2-A1 | 5.2「写者映射」「全路由测试」③；4.6「鉴权配置」 |
| R2-A2 | 5.3「Owner 的决策卡」（内容契约、只收选项、不评估、只读问题页、答复落库）和「测试」的卡片部分；4.6「卡片库」；2.2 `request_owner` |
| R2-A3 | 4.3 接单谓词第 7 条；`parked` 行；锁的顺序；7.4 第 5 条 |
| R2-A4 | 4.2 `issue_work.brief_sha256`、`issue_ask.brief_sha256` 与带 `brief_sha256` 的复合外键、`issue_check` 的 close_check CHECK、守卫「`issue_work` 只由 `issue_taken` 插入」那条；4.3 结案谓词、作废 |
| R2-A5 | 4.2 `intake_client` 与守卫第 2 条；4.6「活跃列」 |
| R2-A6 | 4.2 守卫「`issue_work.ended_at` 由库里的触发器写」与 `BI-n` 那条；4.6「回退」及「旧二进制和 0009 的库」；5.2「令牌」；十一 I-D8 |

## 需要 Owner 的

- **新的两道选择题**（第 3 轮之后和 I-D1…I-D6 一起定，都是安全级，必须等他回）：
  - I-D7（R2-A2）：A 推荐——卡只放编号和中性选项、只读问题页看全文（本稿已按它写）；B——卡里放全文、卡片库按读者限读。
  - I-D8（R2-A6）：A 推荐——库对旧写入者兼容（本稿已做）**加** PROD 流水线对「库比候选新」拒发、他带理由放行；B——只做兼容，流水线照旧放行。A 的第二半是 infra 的 PROD 流水线改动，要他批。
- I-D1…I-D6 推荐都不变；I-D2、I-D3、I-D4、I-D6 的描述随修法或削薄改了几个字（各条末尾注明）。
- 新增要他本人做的：切片 4 在 PROD 鉴权配置里加 `intake_tokens:`（和建 Secret 键一起）。
- 新增要他知道的残余风险：回退到不带 0009 的旧二进制时，`issue:` 流的元数据（编号、类型、时间、哈希、`person:` 编号，没有文字）对有 read 能力的令牌可见。
