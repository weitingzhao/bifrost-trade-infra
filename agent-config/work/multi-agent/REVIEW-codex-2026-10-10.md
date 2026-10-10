# W-31 多 Agent 协作架构独立审查

W-31 的设计和实施计划由 Owner 与 Claude 共同制定，Cursor 正在承担实施工作。Owner 请 Codex 在了解 Stocks 工作区及 W-31 进度后，从独立审查角度检查遗漏、风险和实施顺序，并将结果放到本计划目录供 Claude 与 Cursor 使用。

**审查结论：整体方向合理，现有工作可以继续；开放无人值守执行和自动 PROD 发布前，需要补齐下列门槛。八项意见包含一项已复现实现缺陷，其余为设计契约、实施顺序或验收覆盖问题。**

本文是补充审查意见，不替代 ADR、Owner 的决定或主实施计划，也不自动产生新的批准、任务编号或派工。建议由 Claude 结合最新实现判定采纳、调整、已有覆盖或延期，再由现有协调流程更新正式计划。

## 审查范围与版本

- **日期与作者**：2026-10-10，Codex。
- **读者**：Owner、Claude 规划与协调线程、Cursor 实施线程。
- **状态**：待主计划评估；本文没有分配新的 W-n 或 TD-n。R01 至 R08 只是本报告内的引用编号。
- **范围**：ADR §5 / §12、设计 v4、第 0 步计划、S0-0 审批执行方案、发布队列历史方案、WORK 台账及 T01 至 T18 的定义与阶段归属；抽查 releasepolicy 和 W-48 审批实现。
- **实现证据基线**：platform `7cda6cb2da5c557e950d14ce3232d3b9cf70ad31`；W-48 分支 `65c0054`。数据库草案追溯设计引用的 infra `bf27c80`。
- **原审查计划基线**：infra `f641361e52f264f5252133bdc16209eeeff53fe4`。
- **落盘核对基线**：infra `4259729e2f7f67b8425eabba44c5b2d2899f0270`。已核对其相对原审查基线的计划差异：Console STG 成功记录、W-54 分支交付与待验事项已更新；R07 据此注明已有覆盖。
- **验证边界**：R01 在临时目录复制现有纯函数并运行，没有执行 SQL。其余属于文档与代码审查，没有模拟生产故障、重跑完整验收或验证新分支的全部行为。
- **本次交付**：仅新增本报告；不改应用代码、配置、ADR、WORK 或 TECH_DEBT，不提交或推送，不联系或打断其他线程。

下列绝对路径链接指向共享工作区，行号按落盘核对时的文件记录。后续文件发生变化时，应以这里列明的 Git 基线、章节及函数名定位证据。文中“建议验收”都是待执行建议，不代表已经通过。

## 优先级与处置索引

**P1**：开放对应能力前应解决或形成明确的受限运行边界。不是要求暂停全部 W-31 工作。  
**P2**：补进设计、任务说明或阶段验收，避免规模扩大后返工。

| 编号 | 优先级 | 问题 | 证据性质 | 关联范围 | 建议完成时点 |
|---|---|---|---|---|---|
| R01 | P1 | 增量 DDL 分类器误放行 | 已复现的实现缺陷 | W-42 / S0-8 | 启用自动 DDL 前 |
| R02 | P1 | 自动批准先于发布安全闭环 | 已知缺口与实施顺序风险 | W-42、发布队列、TD-293 至 TD-295 | 无人值守 PROD 发布前 |
| R03 | P1 | 数据库故障恢复链仍可能依赖数据库 | 文档冲突与依赖分析 | S0-4、S0-9、S0-0 卡 7、agentrt | 状态迁移和主仓切换设计定稿前 |
| R04 | P1 | 过期租约执行者恢复的契约不完整 | 故障场景与验收缺口 | agentd、任务租约、Gate A | 自动重新派发任务前 |
| R05 | P2 | 工具厂商不同不等于评审独立 | 身份模型与验收设计问题 | 岗位资格、verification、基准集 | 多厂商验收启用前 |
| R06 | P2 | 订阅额度估计与硬预算混用 | 计量与调度契约缺口 | budget、router、Gate A / T10 | 预算门禁验收前 |
| R07 | P2 | 静默告警时限和事件判定不一致 | 规格冲突；部分已列入后续待验 | W-54 / S0-21 | 真机验收与监测承诺定稿前 |
| R08 | P2 | 退出条件和测试归属未覆盖最新范围 | 实施计划完整性问题 | STEP0、运行时阶段门禁 | 宣告相应阶段完成前 |

## R01 增量 DDL 分类器误放行

**优先级 P1。已复现，确定性高。**

**证据。** [ddl.go 的 ClassifyDDL](/Users/vision-mac-trader/Desktop/stocks/bifrost-platform/api/internal/releasepolicy/ddl.go:24) 将文件拆成行，仅对新增行逐行匹配禁止词，最后默认返回通过。[engine.go](/Users/vision-mac-trader/Desktop/stocks/bifrost-platform/api/internal/releasepolicy/engine.go:620) 用该函数判断命中 DDL 路径的变更是否可以按增量 DDL 放行。现有 [ddl_test.go](/Users/vision-mac-trader/Desktop/stocks/bifrost-platform/api/internal/releasepolicy/ddl_test.go:14) 覆盖了同一行内的危险语句，未覆盖下列换行情况。

对基线函数调用 `ClassifyDDL("", after)`，实测结果如下。表中的 `\n` 表示实际换行，不是反斜杠字符。

| 输入 after | 实际结果 | 应有分类 |
|---|---|---|
| `ALTER TABLE orders ALTER\nCOLUMN amount TYPE integer;` | `true, ""` | 改列类型，不应作为增量 DDL 自动放行 |
| `DELETE\nFROM orders;` | `true, ""` | 删除数据，不应自动放行 |
| `CREATE\nINDEX orders_amount ON orders (amount);` | `true, ""` | 非并发建索引，不符合当前允许条件 |
| `SELECT pg_sleep(600);` | `true, ""` | 不能据此证明属于允许的增量 DDL |

复现仅执行 Go 分类函数，没有连接数据库或执行表中的 SQL。PostgreSQL 允许关键字之间使用换行，因此前几项不能按“无效 SQL”排除。[PostgreSQL 词法规则](https://www.postgresql.org/docs/current/sql-syntax-lexical.html)

**影响。** 当有效签名策略启用 `additive_ddl` 且其他条件满足时，该分类器可能将需要人工审批的变更误判为自动放行候选。本报告没有证明这些示例已经被发布或执行。

**建议。** 在可靠分类落地前，自动策略排除全部 DDL；现有人工路径继续可用。长期方案采用明确的允许语法和语法解析，对动态 SQL、Python 生成的 SQL、未知语句默认转人工处理。不要仅通过增加几个禁止词修补。

增量结构变更仍需评估锁等待、表重写、数据规模和旧应用兼容性；DDL 类别只是一个条件。[PostgreSQL ALTER TABLE 文档](https://www.postgresql.org/docs/current/sql-altertable.html)

**建议验收。** 上表危险或未知输入全部拒绝自动放行；补多行、注释、动态生成及多语句测试；在策略引擎级证明分类失败会转人工审批。迁移演练另验证锁与语句超时，以及应用回滚后的读写兼容性。

## R02 自动批准先于发布安全闭环

**优先级 P1。属于已知问题的依赖和上线门槛审查。**

**证据。** [STEP0 的 W-42 验收](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md:353) 包含 PROD 自动批准与冻结演练，同节登记 TD-293 至 TD-295。另一方面，[发布队列和自动回滚的排期](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md:659) 在第 0 步之外，只要求第 2 阶段之前可用。[当前回滚方案](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md:469) 明确 `:prod` 是可变标签，回滚要重建旧提交并可能需要 Owner 手工操作。

**影响。** 自动授权可能先于发布串行化、冻结全覆盖和故障恢复成熟。策略本身签名正确，也不代表发布失败后能够自主恢复；重建旧提交还依赖源码、构建工具和外部依赖仍可用。

**建议。** 把无人值守 PROD 的启用条件写成一组共同门槛：入口遵守冻结、逐仓固定 SHA、记录实际部署镜像摘要、保留上一版已验证产物、独立检测失败并回滚、失败与部分完成可追查。对 platform 自身升级，要说明新版控制器无法启动时由谁负责回滚。固定镜像摘要可避免标签移动导致实际内容改变。[Kubernetes 镜像文档](https://kubernetes.io/docs/concepts/containers/images/)

TD-293 至 TD-295 已有登记，应补依赖与验收，不重复开同名问题。受限的人工监督演练和全自动常态运行应分别标记。

**建议验收。** 覆盖批准后分支前进、镜像标签变化、两个发布请求并发、冻结期间的不同入口，以及新版 platform 启动失败。验证部署身份不漂移，冻结确实拒绝执行，回滚使用已验证产物且无需重新构建。数据迁移的恢复规则单独验证，不能用应用回滚代替数据库恢复。

## R03 数据库故障恢复路径的依赖冲突

**优先级 P1。文档冲突可确认，端到端故障行为待验证。**

**证据。** [ADR §12.3](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/ADR-ops-architecture.md:235) 要求发布队列不依赖 PG 或 Redis，保证修数据库的发版仍能走。[S0-0 卡 7](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md:440) 推荐先用 statefile，随后又写运行时第 0 阶段“整体迁到 PG”，同段理由却是审批不该依赖 PG。[设计第 10 节](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md:285) 还安排 Gitea 元数据迁入 CNPG。

**影响。** 队列对象可读不等于修复链可用。审批记录、策略读取、Gitea 鉴权与源码获取、platform 启动健康判断中的任一环节依赖故障数据库，都可能阻断恢复。Owner 应急路径是有价值的兜底，但不能算作系统自主恢复已完成。

**建议。** 列出最小恢复链的依赖：授权记录、执行身份、恢复清单、已构建镜像、状态回写，以及它们对 PG、Redis、Kubernetes API、Gitea 的依赖。澄清卡 7 中哪些状态迁入 PG，哪些维修所需状态独立保留；规定 PG 故障时 platform 的降级启动与接口行为。无需因此先重构全部控制面。

**建议验收。** 在隔离环境分别切断 PG、Redis、Gitea，验证仍能执行设计承诺的恢复动作，或准确进入既定人工路径。恢复后补齐审计，验证不重复执行。记录允许的数据损失和恢复时间目标。

## R04 过期租约执行者恢复后的约束

**优先级 P1。属于任务自动接管的契约和故障测试缺口，不是断言现有审批代码没有租约校验。**

**证据。** [设计 §7.2](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md:176) 有 CAS、原子领取、120 秒租约和每 30 秒心跳；[§8](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md:258) 有连续三次心跳失败杀子进程。设计引用的 v3 草案也已有 `lease_id`，提交 API 要求租约。T02 检查并发领取时只有一个有效持有者。W-48 的审批执行另有 `unknown` 不自动重跑及迟到结果规则，见 [S0-0 §2.4](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/S0-0-approved-execution-PLAN-2026-10-10.md:137)。

**故障场景。** A 在执行中随笔记本睡眠，宿主监控也暂停；租约到期后 B 接管；A 恢复时，旧子进程可能继续写共享分支或调用外部工具。提交 API 拒绝旧结果，仍不足以撤销已经产生的外部副作用。

**建议。** 为每次尝试设独立工作区和分支；醒来或断网恢复后先验证租约；将任务、尝试、租约与授权版本绑定。合并和外部写入口验证当前执行资格，必要时使用递增代次作为隔离令牌。无法确定是否完成的副作用转入待核实状态，不盲目重新执行。

**建议验收。** A 睡眠或暂停后，B 成功接管；恢复 A，验证旧结果不会被接受、旧进程不会继续产生有效外部写、两次尝试不互相覆盖。再覆盖“副作用已发生但回执丢失”和“发出叫停后网络恢复”。

## R05 评审独立性的身份粒度

**优先级 P2。身份模型与验收设计问题。**

**证据。** [设计的岗位和候选](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md:95) 要求评审换一家厂商，同时允许 Cursor 使用 Claude、GPT 等模型。v3 数据库草案的 `actor.vendor` 和“作者与评审 vendor 不同”不足以区分工具提供方与实际模型提供方。[基准集](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md:301) 使用已关闭技术债和固定回放题。

**影响。** Cursor 中的 Claude 与 Claude Code 可能被计为不同厂商，却没有模型层面的差异。换模型也不能消除共同错误，例如作者和验收者共同依赖被修改的测试或过时的规范。

**建议。** 分别记录执行工具、模型提供方、模型版本和会话身份；根据风险定义独立性要求。验收记录绑定提交 SHA、规范版本和测试版本；作者修改验收测试时明确复核流程。模型评审作为补充，确定性验收仍需可信依据。20 道回放题用于起步，后续加入保留答案的题和真实任务。

**建议验收。** 识别“不同工具、同一模型”的组合；作者改测试使错误实现通过时仍能被独立用例发现；验收后提交变化会使原结论失效或要求重验。

## R06 额度计量与硬预算

**优先级 P2。T10 的实现契约需要补齐。**

**证据。** [设计第 6 节](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md:144) 要按订阅剩余额度分流，并限制低频业务占短窗口额度不超过 10%；§7.4 要统一记账。T10 要求预算由代码执行，不能靠 Agent 自报。草案账本允许 measured、vendor_reported、self_reported、estimated 等来源，但未明确各来源的授权用途、过期行为和并发预留。

**影响。** 若平台只看到部分订阅用量，或读到过期估计，就不能准确执行全账户比例上限。多个 Agent 同时读取同一余额后开工，也可能共同超过任务预算。

**建议。** 区分估算的路由偏好与可强制的预算上限。每条额度观测记录来源、时间和未知状态；明确 Owner 在运行时之外使用订阅的影响。领取前预留任务预算，结束后结算；对无法准确测量的订阅额度采用保守并发、时长和调用次数限制。厂商限流记录为资源不足，不直接当作模型能力失败。

**建议验收。** 两个任务同时领取最后一份预算时不会共同透支；额度数据缺失或过期时按既定方式降级；进程崩溃后预留可以核对释放；墙钟与并发限制不依赖模型自报。

## R07 静默告警时限与事件判定

**优先级 P2。规格存在冲突，部分风险已由 W-54 后续记录覆盖。**

**证据。** [S0-21 规格](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md:558) 承诺宿主睡眠、进程挂住或断网时 12 分钟内通知，同时将静默阈值设为 `max(10 分钟, 工具声明超时 + 2 分钟)`；心跳来自回合与工具事件，无令牌不发。

**推导。** 声明 30 分钟超时的工具开始后宿主立即睡眠，按公式可能约 32 分钟才进入静默，无法同时满足无条件的 12 分钟承诺。模型正常长时间思考没有工具事件，也可能被报静默。完全未接入上报的线程则无法用“最后一次心跳过期”发现。

**落盘时更新。** [W-54 结果登记](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md:579) 已记录 platform `c854efe`、console `7b4574d`、infra `5560144` 代码完成、待部署与真机验收；[部署后加验事项](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md:609) 已主动列出 Codex 钩子联网、Cursor 父子线程身份、长思考误报。后者应标“已有识别、待验”，不重复报成全新遗漏。本报告未完整审查这些新分支。

**建议。** 区分宿主存活、会话存活与任务进展。独立定时心跳判断失联，工具事件解释进展；未配置令牌或钩子失败显示“未接入监测”。若当前版本仍只提供事件型静默检测，就准确限定告警时限的适用条件。保留 W-54 只通知、不接管的范围；自主继续工作由运行时租约与常驻宿主验证。

**建议验收。** 延续 W-54 原验收，补 30 分钟工具超时下睡眠、超过 10 分钟的正常思考、无令牌或上报失败、父子会话并行，以及断网后事件迟到的场景。分别记录漏报、误报与实际送达时间。

## R08 阶段退出条件和测试归属

**优先级 P2。计划维护问题，适合由现有协调线程统一处理。**

**证据。** [STEP0 退出条件](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/STEP0-PLAN-2026-10-08.md:683) 仍以 Gitea、路径、RP、进度和存储为主，未明确归纳新增审批执行链及 W-54 的必选或可延期状态。[运行时阶段表](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md:306) 未逐项分配 T04 至 T07、T16 的通过时点。[测试节](/Users/vision-mac-trader/Desktop/stocks/bifrost-trade-infra/agent-config/work/multi-agent/DESIGN-agent-runtime-2026-10-08.md:318) 将 CI 如何提供 PG 和 Redis 留作待定；§7.6 又将运行时接口限定为 PROD。

**影响。** 局部测试通过容易被误认为阶段整体完成；安全停止、失败实验保存、级联重试等要求可能没有实际验收归属。生产权威唯一与测试环境唯一不是同一要求。

**建议。** 维护一张现行的“能力—负责人—依赖—验收—证据提交—环境—门槛”表，明确新增道是否阻塞第 0 步完成。T07 安全停止在无人值守前通过，T16 在级联路由前通过；其余测试随相关能力设置门槛。给 PG/Redis 和状态机故障测试明确隔离环境。评估 Gitea 完整迁移是否必须阻塞受限运行时试点；这是供 Owner 与 Claude 评估的顺序建议，不改写已定方案。

**建议验收。** 每个阶段退出条件都可指向结果与版本；所有测试都有执行时点；过期或不完整证据不能自动算通过。用一个只推分支、不发版的真实 mission 验证完整流程，再逐步开放副作用。

## 建议纳入计划的门槛

| 能力开放 | 建议先满足 | 主要证据 |
|---|---|---|
| 自动 DDL | R01 分类修复、未知拒绝、迁移影响和兼容性验证 | 分类与引擎回归测试、迁移演练 |
| 无人值守 PROD 发布 | R02 发布串行化、固定产物、冻结覆盖、自动回滚 | 多入口冻结与失败恢复演练 |
| 数据库故障时自主修复 | R03 最小恢复链不依赖待修部件 | PG / Redis / Gitea 故障矩阵 |
| 任务自动接管 | R04 旧执行者失效、尝试隔离、重复副作用约束 | 睡眠恢复与回执丢失测试 |
| 跨厂商岗位轮换 | R05 独立身份与可信验收、R06 可执行预算 | 候选资格及并发预算测试 |
| 对外承诺监测时限 | R07 注册覆盖、时限定义、误报与漏报验证 | 三家真机结果 |
| 宣告阶段完成 | R08 当前验收表覆盖实际范围 | 与提交、环境绑定的验收记录 |

这些是审查建议，不是已批准的计划变更。已有 Console、通知和治理工作可以按现有授权推进；需要影响在途工作时，由 Claude 结合依赖和 Owner 已定决策安排。

## 已有设计的有效基础与审查边界

下列内容已存在，本报告没有将其重复列为遗漏：

- PG 为任务事实来源，事件与 outbox 同事务，Redis 可从持久状态恢复。
- 实现者不能自行验收；任务、规则与记忆由本方系统持有。
- W-48 使用 statefile.Update 处理并发写；审批有独立租约和 unknown 状态，失联后不盲目重跑。
- W-48 已有按字节压缩历史记录及裁剪输出尾部的机制，不能仅凭“保留 500 条”推断一定撑爆 ConfigMap。
- 签名策略、冻结、D10 独立边界、Gitea 备份恢复演练和后续虚拟机隔离均已规划。
- 同一 macOS 用户下部分凭证仍可达的风险已被 Owner 明确接受，不在本报告中假装成新发现或重新要求审批。
- 发布队列、自动回滚、mini 常驻和虚拟机尚未完成，并不自动构成缺陷；本报告关注的是开放能力前是否有明确依赖与验收。

本报告不评估全部第三方组件的最新版本、许可证或订阅条款，不宣称已经完成全仓安全审计。新增组件仍按原计划的采用门槛核实。

## Claude 与 Cursor 如何接续

建议 Claude 先按最新分支逐项回应 R01 至 R08，使用以下四种结论，并附理由或证据：

| 结论 | 应记录的内容 |
|---|---|
| 采纳 | 关联既有工作项、修改位置、验收与时点 |
| 调整 | 保留的问题、采用的替代方案及理由 |
| 已有覆盖 | 对应代码提交、测试或演练结果；只有规划时标为待验 |
| 延期或不采纳 | 当前适用范围、接受的影响及复核触发条件 |

优先复核 R01；随后处理 R02、R03 的依赖关系，以及 R04 的故障语义。R07 与 W-54 已列待验事项合并处理，避免重复派工。所有正式编号、计划修改和 Cursor 任务仍由现有协调流程管理。

Codex 可以按明确范围继续提供以下帮助：

- 对 R01 修复做独立复现和回归审查，检查分类器与策略引擎的整体行为。
- 帮助细化任务状态机、租约接管、幂等与 unknown 的契约及故障测试。
- 对发布、审批、Gitea、PG、Redis 的依赖做恢复路径核对，审查演练方案和结果。
- 审查候选身份、跨模型验收与预算门禁；复核 Claude 或 Cursor 给出的提交和证据。
- 在明确文件归属和工作范围后承担获准的独立实现任务；本轮尚未接受任何代码修改任务。

Claude 有疑问时，可把问题、文件或提交号、相关决定及已有测试结果交由 Owner 转到当前 Codex 会话。届时 Codex 可以针对同一证据继续核实。跨应用线程直连是否可用尚未确认；本次不会自动给 Claude 或 Cursor 发消息，也未安排后台持续监控。

