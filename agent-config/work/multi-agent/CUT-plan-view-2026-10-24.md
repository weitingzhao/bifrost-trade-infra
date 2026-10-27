# 切法：Ops 全计划视图（2026-10-24）

状态：A/A/A 路线已由 PV0 采用；PV1 part 2 按 Work 594 简报实施，本记录不授权发布。

2026-10-26（Work 594，统筹 proceed-on-recommendation，Owner 事后审计）：Q1=A，仅持久化 dev 计划根，首次采用拒绝树内 business mission/task，之后每次绑定检查 dev，其他租户拒绝，无 DDL。Q2=A，本片只做可见性，拒绝非空 bindings；登记与摘要只证明 running/submitted，不证明 done；现有 controller 完成规则不变，四个新增完成原子及可信核验留到 PV2。

2026-10-26（Work 630，统筹 proceed-on-recommendation，Owner 事后审计）：PV2 采用可信核验源方案 A。`external_verified` 只认精确绑定 task/attempt/result 的平台 verification，或 Owner 对准确节点、验收版本及证据的签收；没有适用核验源则保持 Unknown。4.10 五个验收各自命名来源、分别签收，不复用一个结论。该决定授权本片实现，不是发布批准。

2026-10-26 晚（统筹复核 PV2 `057251ee` 并直接修复，proceed-on-recommendation，Owner 事后审计）：两个独立复核找到两个阻断项：结果提交去交付组织找，PROD 上永远 Unknown；每 15 秒每个绑定写一条事件，并在持锁事务里读 Gitea。按推荐定下五点：① 结果先到 `AGENTRT_GIT_ORG` 读，再到交付组织；main 历史按仓库缓存，只增量读新提交。② 观测只在答案变化时写；每个 root 一轮一条 pass，记录每个绑定最后一次读成功的数据库时间（读失败的沿用上一次的时间），绑定集合没变时最多每 10 分钟写一条；Stale 从 60 秒改为 25 分钟；读失败不写任何东西，done 要等到 25 分钟没有一次成功才撤回（False 仍立即撤回）。结果提交读不到时（分支已删、对象已回收），用 main 上写明「cherry picked from」这个结果的提交确认身份；merge revert 写的保留父提交不是该 merge 的父提交时给 Unknown。采集改成独立循环，每分钟一轮，远程读放在事务外，单次读上限 2 分钟。③ 只有 Change-Id 相同、没有确切出处（结果本身，或 cherry-pick 行写明这个结果）时给 Unknown；revert 一个 merge 时，撤销该 merge 带进来的提交；一个提交里有多条 revert 行，每一条都算。④ 采用视图时，保留步骤原有的其他条件，只替换旧版本的绑定原子；`any` 里有绑定原子时拒绝采用。⑤ 带绑定的视图不允许规则自动批准。§12 中与此冲突的写法（60 秒 Stale、每次成功采集都写）以本行为准。未修的几处登记为 TD-445。

2026-10-26 晚（Owner 定，D-PV2-B）：Owner 签收类验收的证据用 B。采用计划时，`owner_signoff` 绑定只固定节点、验收版本（`acceptance_sha256`）和计划版本，不再要求 `evidence[]`；证据（已存产物 ID）在 Owner 签收时附上，写进 `owner_signoff` 事件，并纳入签收摘要。换验收版本仍要重新签收；没有附证据的签收不算 `external_verified` 成立。Console 签收入口要能列出该步骤上 Agent 提交的候选证据，供 Owner 选择后签收。实现排在复核 631 的修复（Work 632）之后，交 Codex。

目标：Owner 从手机看出主线位置、下一步，以及谁在等谁。

## 1. 范围与已定顺序

| 项 | 决定 |
|---|---|
| 主线 | 第 4 轮：包工队自己接活、自己交房 |
| 当前关键项 | 4.1：验收通过后，运行时合入 main、交付 STG |
| 本项位置 | 4.5 的提前片；承接 4.7 的事件推导 |
| 排期 | 与 4.1 并行；先于主机操作策略实施 |
| 顺序依据 | Work 562 的 `BRIEF.md`，Owner 10-24 晚间决定 |
| 旧记录差异 | `WORK.md` 仍写主机策略排第一；本次简报更新了顺序 |
| 页面语言 | 页面控件用 English；计划、主线、支线任务用中文 |
| UI 负责人 | Codex；本切法 PV4 负责最小页面 |
| 视觉设计 | 留给 Owner 的 Design 专轮 |
| 本次交付 | 只写本切法；其余仓库只读，不联网 |

不把本视图设成 4.1 的交付前置。
不因缺少 4.1 新事件而隐藏已有工作。
4.5 的完整现场流、额度调度仍单独实施。
4.7 的执行器、审批合单仍单独实施。

## 2. 本地证据与现有能力

核对基线：infra `1db713a6637c0ff56bb6371d3e72c30d7439767e`。
platform `52a95303b0d3cc42def4124ba42c753e07544b24`。
未查询线上；这些提交号不代表已部署版本。

表中 `P/` 指 `bifrost-platform/`；`I/` 指 `bifrost-trade-infra/`。

| 证据 | 已有能力 | 本项缺口 |
|---|---|---|
| `I/agent-config/WORK.md:544` | 第 4 轮目标、三波、4.1–4.10 | 晚间视图优先级尚未写入 |
| `I/agent-config/work/multi-agent/CUT-landing-2026-10-24.md` §2.4、§2.7 | 提议 `note.landing`、落地与交付语义 | 是设计契约；不能当线上事实 |
| `P/api/internal/agentrt/migrations/0001_core.sql:88` | `plan_node` 树、`work_id`、`owner_step`、完成规则、工时 | 无主支线分类、计划级依赖 |
| 同文件 `:233` | `plan_node_binding` | 仅允许 `approval`、`question` |
| 同文件 `:30` | 内容寻址产物；`other` 可存 JSON | 新格式仍需应用层校验 |
| `P/api/internal/agentrt/planimport/request.go:55` | 导入层级、标题、步骤类型、原始台账证据 | 导入证据不核实提交与审批 |
| `P/api/internal/agentrt/store/planimport.go:120` | 原请求存产物；旧勾选变成 manual 证据 | 不能把旧勾选当自动验证 |
| `P/api/internal/agentrt/store/planparse.go:67` | mission 计划产物有任务 `depends_on` | 不是整轮 `plan_node` 之间的关系 |
| `P/api/internal/agentrt/plan/rule.go:138` | 任务、审批、问题、CI、签收、gate 原子 | 缺落地和外部工作验收原子 |
| `P/api/internal/agentrt/store/facts.go:17` | 外部事实先入事件，再评估完成规则 | 需补主线、发布及外部工作适配 |
| 同文件 `:374` | controller 依规则写步骤状态事件 | 不是全部状态都靠手改 |
| `P/api/internal/agentrt/agentrtapi/plan.go:41` | `get_plan` 返回树、状态事件、任务计数 | 没有整计划下一步与等待关系 |
| `P/mcp/platform/src/index.ts:645` | MCP `get_plan`；另有计划变更工具 | 缺聚合读模型、外部登记工具 |
| `P/api/internal/agentrt/store/progress.go:13` | 单次只读快照；任务、主机、等待状态 | 范围是运行时 mission/task |
| `P/api/internal/agentrt/store/progresseta.go:11` | 30 天样本、区间、未知原因 | 未提出的评审不在估算内 |
| `P/api/internal/lineage/mainresults.go:20` | `Agentrt-Task`、cherry-pick、标准 revert | 不覆盖仅有 Work 尾注的外部工作 |
| `P/console/src/pages/shell/owner/OwnerWork.tsx:64` | Work 卡显示计划条目和进度条 | 没有主线、支线和依赖图 |
| `P/console/src/pages/shell/agents/AgentsPlan.tsx` | 计划详情、签收区、架构 gate | 默认折叠；缺整计划定位 |
| `design/codex/ops/COORDINATION.md` | Codex 负责 Console；已有数据修补协调记录 | 不能由统筹另开同页实现 |

## 3. 数据选择：先复用，明确扩展边界

### 3.1 架构点 D-PV1

以下均是待选方案，不是已签决定。

| 选项 | 存储方式 | migration | 成本与限制 |
|---|---|---|---|
| A，推荐 | 现有树 + 版本化产物 + 受校验的 `note` 子协议 | 不需要 | 小规模先交付；图约束由事务代码保证 |
| B | 新建计划元数据、依赖、外部工作表 | 需要 | SQL 约束和索引更强；增加 DDL 与发布成本 |
| C | 完整独立计划库；同步现有树 | 需要 | 两份计划易分叉；迁移与兼容成本最高 |

推荐 A：已有事件、产物、树、完成规则都能复用。
不把 JSON 随意塞进 `done_rule_json` 或既有 binding。
`note` 的字段词表封闭，仍须修改 Go 校验器。
新增顶层事件类型会触发数据库 CHECK，届时必须 migration。
本版保留事件类型 `note`、产物类型 `other`。

| 新协议 | 载体 | 用途 |
|---|---|---|
| `agentrt.plan_view/v1` | `other` JSON artifact | 分类、边、职责、验收、估算输入 |
| `note.plan_view` | `plan:<root>` 流 | 已采用的产物摘要、版本、变更依据 |
| `agentrt.external_work/v1` | `other` JSON artifact | 外部派工说明、执行身份、产物引用 |
| `note.external_work` | `external-work:<id>` 流 | 登记、心跳、提交、核验、取消、重新绑定 |
| `note.plan_observation` | `plan-observation:<root>` 流 | 已验证的提交、评审、发布及采集新鲜度 |

所有对象必须有 `v`、固定 `kind` 和身份引用。
拒绝未知字段、未知版本、悬空引用和跨租户绑定。
文字放产物；事件保存摘要、枚举、引用及短说明。
按现有产物大小上限校验。

### 3.2 每个计划项的数据

| 字段 | 位置 | 规则 |
|---|---|---|
| `plan_node_id`、`parent`、`ordinal` | 现有树 | 保留编号和既有深链 |
| `title`、`work_id` | 现有树 | 中文标题；Work 编号不等于步骤编号 |
| `lane_kind` | 视图产物 | `mainline`、`branch`、`support` |
| `mainline_order` | 视图产物 | 显式主线路径；不靠编号猜测 |
| `anchor_node_id` | 视图产物 | 支线贴在哪个主线节点旁 |
| `depends_on[]` | 视图产物 | 前置节点、所需里程碑、原因 |
| `relation` | 视图产物 | `blocks` 或 `related`；只有前者阻塞 |
| `next_responsible` | 视图产物的默认职责 | `owner`、`crew_seat`、`vendor_executor`、`review` |
| `actor_ref`、`seat_ref`、`provider` | 默认职责及运行事实 | 已派执行者覆盖默认职责；厂商名不是岗位 |
| `acceptance[]` | 视图产物 | 中文标准、规则引用、证据要求、目标环境 |
| `done_rule_json` | 现有步骤 | controller 使用；不允许 UI 改完成勾选 |
| `owner_step`、`effect_step` | 现有步骤 | 保留“你”和 ★；不是“现在等你” |
| `estimate` | 视图产物 | 剩余工作区间、评审轮数、来源、信心 |
| `bindings[]` | 视图产物 | mission/task、外部工作、commit、run、review 引用 |
| `execution`、`delivery`、`waiting_on[]` | 只读投影 | 来自事实；不存第二份手工状态 |

`review` 表示下一步责任类型；仍须指明评审岗位或执行者。
`waiting_on[]` 可有多项，不能用单个 owner 字段掩盖多重阻塞。
每个等待包含对象、原因、证据、开始时间和可执行入口。

### 3.3 更新与兼容

| 操作 | 约束 |
|---|---|
| 首次导入 | 先复用现有 import；保留源提交、节摘要和旧证据 |
| 采用视图 | 扩展 `propose_plan_change`；带 `expected_version` |
| 原子更新 | 同事务锁根版本、相关节点、计划流；冲突返回 409 |
| 图校验 | 拒绝环、自依赖、重复主线顺序、缺失前置里程碑 |
| 跨轮依赖 | 显式 root/node 引用；锁涉及的根，统一排序 |
| 计划替换 | 保留旧产物；新事件指向新版本，历史仍可重放 |
| 任务换步 | 复用 `move_task`；外部工作单独记录重新绑定 |
| 旧数据 | 标 `Legacy evidence`；缺分类显示 `Unclassified` |
| 旧接口 | `get_plan` 的树和字段保持兼容 |
| 缓存 | 按计划版本、提交事实集合重建；缓存不是权威 |

新增完成原子需同步解析器、事实读取器、绑定校验和测试。
采用 A 不代表跳过这些改动。
旧导入的 manual 原子保留历史；新步骤不再依赖手改状态。
线下演练可用明确的 Owner 签收事件，附可检查证据。

| 拟增原子 | 参数与语义 |
|---|---|
| `main_effective` | 明确结果绑定；main 含该结果，且未被撤销 |
| `deployment_verified` | 应用、环境、结果绑定；部署及健康核验均通过 |
| `review_valid` | 结果 SHA、评审引用；当前版本的独立复核通过 |
| `external_verified` | 外部工作、验收版本；controller 核验通过 |

前三项按当前有效性重评；条件失效可撤回完成状态。
历史里程碑另存证据，不随投影撤回而删除。
新增原子的绑定由应用层强制，数据库尚无对应专用约束。
这是 A 的明确取舍；PV1 必须测试越权及跨步引用。
若要求数据库也强制这些关系，应选 B。
已采用的新步骤由 controller 推导 active/done，再写既有状态事件。
新旧读取端共享这些步骤状态；新视图另列交付与新鲜度。

## 4. 第 4 轮怎样放到图上

以下是建议布局，须在 PV0 核对后采用。
条目编号顺序不自动变成阻塞顺序。
既定三波保持；4.3、4.4 的设计可先行。

| 条目 | 建议类别 | 路径或锚点 | 真正等待什么 |
|---|---|---|---|
| 4.1 自己交房 | `mainline` | 当前首段 | 依落地切法的规则、资格、实证 |
| 4.2 多项目推进 | `mainline` | 4.1 后的业务扩展 | 4.1 上 PROD；Finance 接入签名 |
| 4.3 各应用发布节奏 | `support` | 连接 4.1、4.2、4.10 | 设计先行；实施按第二波 |
| 4.4 统筹搬离电脑 | `mainline` | 后续自主运行段 | 设计和记忆可先行；实施按第二波 |
| 4.5 现场可见 | `support` | 连接所有主线节点 | 本视图提前；完整现场流仍在第二波 |
| 4.6 生命周期 | `support` | 连接 4.1、4.10 | 第一波并行；一周观察仍要单列 |
| 4.7 降低 Owner 负担 | `support` | 连接 4.10 | 第三波；事件推导由本项提供 |
| 4.8 资格流水线 | `support` | 连接 4.2、4.4 | 第二波；题集签名 |
| 4.9 机房后备 | `branch` | 锚在 4.4 | B4 ①先行；其余硬件窗口单列 |
| 4.10 五项验收 | `mainline` | 最后汇合 | 五个度量各自证据齐全 |
| 全计划视图 | `support` | 4.5 的提前片 | 与 4.1 并行，不阻塞 4.1 |
| 主机操作策略 | `support` | 4.7 旁的实施入口 | 全计划视图可用后再实施 |

展示路径建议：4.1 → 4.2 → 4.4 → 4.10。
箭头表达主线叙事；阻塞必须另有 `blocks` 边。
4.4 不因此被错误地锁到 4.2 完成之后。
Screening 闭环保留 4.2 内关联；按第二个仓库接入门槛推进。

4.10 必须显示五个独立验收格：

| 格 | 验收证据 |
|---|---|
| 自己合入过半 | main 代码提交分母；真实推送者和落地记录分子 |
| 每周决定少于 40 | Owner 决定事件；明确统计窗口 |
| MacBook 合盖一夜 | 夜间运行和产物记录；Owner 演练签收 |
| 两产品同时推进 | 两条任务、落地和发布链；时间重叠 |
| 一周无需清理 | 七天磁盘、分支趋势和人工清理记录 |

## 5. 状态由事件计算

### 5.1 事实输入与认定

| 输入 | 关联键 | 可以证明 | 不能证明 |
|---|---|---|---|
| mission/task/attempt | 明确绑定的 ID、版本、attempt | 已派工、执行中、待验收、失败 | 已合 main 或已发布 |
| 独立 review | 被审 SHA、任务轮次、评审产物、身份 | 当前结果已复核；返工原因 | 旧 SHA 的评审覆盖新 SHA |
| main commit | repo、SHA、`Change-Id`、Work、任务引用 | 某结果确实进入 main | 一个 `Work: W-31` 完成整轮 |
| delivery run | 应用、环境、run UID、revision、digest | 正在发布、run 结果 | run 绿即实际部署正确 |
| 部署核验 | 实际 SHA、摘要、rollout、健康证据 | 指定结果已在指定环境核对 | Trade smoke 代替 platform 健康 |
| approval | 精确审批引用、动作与执行结果 | 等 Owner、已批准、已执行 | 已批准等于执行成功 |
| question | 精确问题引用与回答事件 | 设计选择已回答 | 回答等于发版或权限批准 |
| owner_signoff | 节点、验收 ref、版本、证据 | Owner 完成对应验收 | 新版本自动继承旧签收 |
| 外部登记和心跳 | `external_work_id`、run key、seq | 外部任务存在、最近报告时间 | 执行者自称成功即交付 |

Work 尾注先解析成候选关联集合。
若只匹配大项，挂进该项的 `Unlinked evidence`。
只有唯一且明确的步骤绑定，才能参与完成计算。
无尾注、重复关联和扫描截断都显示缺口。
不把历史扫描未发现解释成“从未合入”。

### 5.2 投影规则

| 维度 | 规则 |
|---|---|
| 完成 | acceptance 的所有必要条件满足；每项有证据引用 |
| 主线位置 | 第一个未达验收的主线节点；另列正在并行的节点 |
| 下一步 | 从未满足条件中找可执行动作；沿阻塞边追到责任方 |
| 现在等 Owner | 前置已齐，且有待批单、待答问题或可签收验收 |
| 以后要 Owner | 只列在 `Later`；不计入 `Needs you` |
| 等复核 | 当前 SHA 已提交，所需 review 尚未通过 |
| 等执行者 | 岗位未获可用执行者；展示岗位和供应方事实 |
| 未知 | 采集失败、陈旧、版本不匹配；保留最近已知事实 |
| 停止与取消 | 保留历史；不计作完成；说明取消了哪些依赖 |
| 上级汇总 | 必要子项全部通过才完成；另列 stopped/dropped |

这是确定性投影；同一事实集合得到同一结果。
不调用模型猜状态或下一步。
更改计划意图仍走有依据的计划变更。

| 时序问题 | 处理 |
|---|---|
| 重复事件 | 按来源 ID、对象版本、序号幂等 |
| 乱序到达 | 用来源版本排序；不以到达时间覆盖较新事实 |
| 跨流读取 | 同一数据库只读快照；保存逐流 committed 游标 |
| event_id 空洞 | 不以全局 `max(event_id)` 跳过迟提交事件 |
| 采集停机 | 回扫、补录、重放；显示来源水位与缺口 |
| 后继部署 | 验证目标提交包含关系和撤销情况；不要求永远等于旧 SHA |
| revert/回滚 | 历史成功保留；当前有效性撤回，依赖重新阻塞 |
| 事实过期 | 时间由服务端计算；显示 `Stale`，不继续估 ETA |

成功读取但业务值不变时，也更新采集新鲜度。
不能直接用 `facts.go` 的最后变化时间判断失联。
失败记录不删除旧事实；恢复后用新观测解除未知状态。

### 5.3 正确呈现 4.1

复用落地切法的 `note.landing`，不另建落地状态机。
PV2 先写适配器及 fixture；真实上线后接同版本协议。

| 落地事实 | 页面显示 | 下一步责任 |
|---|---|---|
| task `accepted`，尚无落地 | `Accepted · Not landed` | 落地控制器；未启用则明确说明 |
| `prepared` / 等 CI | `Preparing` / `Waiting for CI` | 控制器或 CI |
| `parked{window}` | `Waiting for release lane` | 窗口持有方；展示关联 run |
| `parked{rule}` | `Policy paused` | 规则负责人；无待批单时不冒充等 Owner |
| `failed{conflict}` 等 | `Landing blocked` | 对应问题的处理岗位 |
| `landed{R}` | `On main` | STG 发布；或按规则已满足交付 |
| `stg_started` | `Deploying to STG` | delivery run |
| `stg_verified` | `Verified on STG` | 后续 PROD 策略或验收 |
| `stg_failed` | `On main · STG failed` | 发布修复；不回退成未合入 |
| `reverted{R}` | `Reverted` | 新决定；不能继续解除依赖 |
| `declined` / `stale` / `no_merge` | `Disposed · Not delivered` | 说明已处置原因 |

mission `done` 仍不能代替 4.1 的 ★。
★ 必须包含真实链路与“统筹线程零写入”的证据。
旧任务缺少落地授权时，不伪造 `queued`。

## 6. 外部派工：`register_external_work`

### 6.1 架构点 D-PV2

| 选项 | 做法 | 取舍 |
|---|---|---|
| A，推荐 | 专用窄登记接口；观测记录不进入调度队列 | 改动少，不伪造 runtime attempt |
| B | 外部执行者也领取 runtime task/lease | 统一调度更强；需重做派工入口和租约 |
| C | 靠提交和日志事后发现 | 最便宜；未提交的工作持续不可见 |

推荐 A；后续可以显式接管到 runtime task。
登记表示“看得见”，不增加执行权限。

| 接口 | 拟定契约 |
|---|---|
| MCP | `register_external_work` |
| HTTP | `POST /api/v1/agentrt/external-work` |
| 必填 | `idempotency_key`、`root`、`plan_node_id`、`source_run_key`、说明产物摘要 |
| 说明产物 | 中文任务、执行者、厂商、repo/branch、验收引用、预估范围 |
| 可选 | `mission_id`、已有 `task_id`、已有产物引用 |
| 返回 | `external_work_id`、持久化事件 ID、计划深链 |
| 后续记录 | `POST /external-work/{id}/events`；固定事件类型及单调 `seq` |
| 身份 | 复用认证 actor；仅已授权统筹或登记方可写自己的记录 |
| 幂等 | 同键同内容返回原记录；同键异内容返回 409 |
| 更新事件 | `started`、`heartbeat`、`submitted`、`cancelled`、`linked` |
| 控制器事件 | `verified`、`verification_failed`；登记方不能自行提交 |

### 6.2 低成本接线

| 时点 | 动作 | 不成功时 |
|---|---|---|
| `codex exec` 启动前 | 派工包装器先登记，再启动进程 | 显式报登记失败；不静默启动新工作 |
| 执行中 | 包装器每 30 秒报告心跳 | 60 秒无报告标 `Unconfirmed` |
| 完成 | 上传报告摘要、提交 SHA、检查结果 | 保留 `Submitted`，等核验 |
| 包装器崩溃 | 重启读取同一 run key；查询后补报 | 不能重复创建或误报已结束 |
| 已在跑的外部任务 | 统筹做一次清单回填；记录原开始时间 | 标 `Backfilled`，不伪造过去心跳 |
| 后来进入 runtime | 原子写 task 绑定 | 两边只显示一个工作实例 |
| 绕过包装器 | 对账提交、已有线程记录、派工清单 | 放 `Unregistered work`，请求补关联 |

运行事实使用 `observed_at` 与 `recorded_at` 两个时间。
原开始时间只作来源声明，不能当服务端心跳。
登记后失联仍显示该工作，不能从列表消失。
不采集命令正文、环境变量、凭证和原始会话内容。

没有登记、没有任何可观测记录的进程无法被平台发现。
验收范围是所有支持的派工入口和一次存量清单对账。
页面显示覆盖范围与漏登记数量，不承诺扫描任意主机。
本次 Work 562 只出方案，不执行登记调用。

## 7. 一个 API 回答整计划

### 7.1 架构点 D-PV3

| 选项 | 做法 | 取舍 |
|---|---|---|
| A，推荐 | `GET /api/v1/agentrt/plan-view?root=R4` | 独立只读投影；旧接口不变 |
| B | 扩大现有 `get_plan` | 少一个入口；树读取承担更多语义 |
| C | 前端拼 `plan`、`progress`、lineage、delivery | 容易时间不一致；不推荐 |

MCP `get_plan_view` 透传 A，不复制计算逻辑。
后端复用现有事实与进度函数，避免自调多个 HTTP 接口。

| 响应字段 | 内容 |
|---|---|
| `schema` | `agentrt.plan_view_response/v1` |
| `root`、`plan_version`、`artifact_id` | 采用哪份计划 |
| `as_of`、`source_watermarks`、`freshness` | 数据时点、来源覆盖、陈旧原因 |
| `mainline` | 有序路径、当前节点、已达里程碑、当前有效性 |
| `next` | 下一动作、责任类型与身份、依赖、原因、深链 |
| `waiting_on` | 全部等待边；每条有节点、责任方、来源证据 |
| `owner_waiting` | 当前可行动项；去重后的审批、问题、签收 |
| `owner_later` | 前置未齐的 Owner 步骤，不混进当前计数 |
| `items`、`edges` | 全部 4.1–4.10、支线、配套、明确关联 |
| `external_work`、`coverage` | 已登记、失联、补录及未关联工作 |
| `eta` | 完工范围、信心、依据、未知原因、是否含复核 |
| `recent_changes` | 最新变化、前后值、时间、actor、证据深链 |
| `warnings` | 缺分类、绑定歧义、来源失败、协议不兼容 |

同一 GET 必须返回完整主线摘要和所有 Owner 等待项。
root 不存在返回 404；数据库不可读返回 503。
局部来源失败返回部分结果，并明确 `Unknown`。
不把部分失败转换成“没有等你的事”。
首版限制整树 500 节点；超限明确拒绝，不静默截断。
近期变化默认 20 条；同接口游标翻页，固定快照边界。
同一审批关联多项时只计一次，同时列出全部受影响项。
Viewer 可读；读请求不登记工作、不改变计划。

### 7.2 ETA 与信心

| 情况 | 表现 |
|---|---|
| 有足够历史样本 | 复用同岗位、任务类别的 30 天样本 |
| 尚未派工 | 用已采用计划中的工作区间；标 `Plan estimate` |
| 依赖并行 | 按依赖最长路径；共享席位按实际容量串行 |
| 复核 | 包含计划复核轮数；新增返工重估 |
| 等 Owner、窗口未知、失联 | 完工 ETA 为 `Unknown`；可另示剩余工作量 |
| 部分任务未提出 | 标 `Partial estimate`；不能冒充整项完工时间 |
| 信心 | `low`、`medium`、`high`；同时显示样本数和理由 |

首版最多给 `medium`；`high` 留待预测误差校准后启用。
少于三个同类样本使用 `low` 或 `Unknown`。
显示时间区间和时区，不显示无依据的单点倒计时。

## 8. 最小页面与职责

入口保持 `#work`；全计划位置保持 `#work?section=plan`。
加 `root`、`node` 参数定位节点；旧审批和签收深链继续有效。
页面首屏不要求先展开“Plan and architecture”。

| 区域 | Desktop | Phone |
|---|---|---|
| 顶部 | `Main line`：当前位置、下一步、时间范围 | 同样三条；任务文字中文 |
| Owner 等待 | `Needs you` 常显，显示动作与影响 | 排在首屏；按钮进入原审批、问题或签收入口 |
| 主线 | 一条有序路径；当前段突出 | 单列纵向路径，无横向拖图要求 |
| 支线与配套 | 放在对应主线节点旁 | 放在锚点下面；默认显示摘要 |
| 依赖 | 连线加文字；点击前置可定位 | `Waiting on` 文本列表，可点回主线 |
| 节点详情 | 验收、责任、证据、外部工作 | 点开卡片；长文字可换行 |
| 最近变化 | `Recent changes` | 同样可见，逐页加载 |
| 错误 | `Unknown`、`Stale`、最近成功时间 | 保留结构；不回填假成功 |

示意内容仅作布局，不代表当前运行状态：

```text
Main line
4.1 运行时自己交房
Next · 等独立复核当前实现
Needs you · 1
签自动合入规则 → Review

4.1 运行时自己交房
  Support · 全计划视图
  Support · 生命周期
4.2 两个产品同时推进
4.4 统筹搬离电脑
4.10 五项验收
```

| 实施人 | 文件范围与责任 |
|---|---|
| Codex，PV4 | `owner/OwnerWork.tsx`、计划组件、响应适配与页面测试 |
| 后端实施方，PV1–PV3 | `api/internal/agentrt/`、事实适配、MCP；不代改页面 |
| 统筹 | 写接口交接、安排复核、核对证据和采用版本 |
| Owner | Design 专轮决定最终视觉；本片验收可用性 |

按 COORDINATION 的 Console 归属接线。
相关批次已有后续交回记录，不把“第 3 批尚未完成”当现况。
PV4 开工先核对文件占用，并在协调记录写范围。
现有简报限制前端改 API 字段；本切法签定后才移交新契约。
不新增 npm 依赖；沿用组件、主题与权限检查。
点击区域至少 44px；等待状态同时有文字，不能只靠颜色。

## 9. 切片、估算与验收

单位为人日，按有效工作 8 小时计算。
每片包含一轮独立复核和一轮修正确认。
超过两轮的返工另报；Owner 等待和发布排队不计入人日。

| 片 | 实施 / 复核修正 / 合计 | 交付 | 验收 | 要 Owner |
|---|---|---|---|---|
| PV0 契约与映射 | 0.5 / 0.5 / 1 | 4.1–4.10 分类、依赖、验收映射 | 不把三波变成错误串行；逐条有来源 | 定 D-PV1–3，确认采用的图 |
| PV1 元数据与投影核心 | 1 / 0.5 / 1.5 | 产物校验、版本采用、图解析 | 环、悬空、并发改版被拒；旧 R2/R3 可读 | 无新增动作 |
| PV2 事件与落地适配 | 1.5–2 / 1 / 2.5–3 | 事实关联、完成条件、等待与近期变化 | accepted 不等于 landed；revert 撤销当前有效性 | 无新增动作 |
| PV3 外部登记及聚合 API | 1–1.5 / 0.5 / 1.5–2 | 窄写入口、包装器接线、`plan-view`、MCP | 本地派工全程可见；重试不重复；失联不消失 | 如需新写身份，签最小权限 |
| PV4 最小可用页面 | 1–1.5 / 0.5 / 1.5–2 | Codex 实施桌面、手机视图 | 390×844 手机 30 秒内回答三个问题 | 手机试用约 15 分钟 |
| PV5 对账与交付 | 0.5–1 / 0.5 / 1–1.5 | 存量回填、STG 实证、同版发布证据 | 不询问线程即可定位主线、责任和证据 | PROD 发布按现有审批；最终验收 |

合计 9–11 人日；初始信心 `low`。
PV0 后，PV2 与 PV3 的独立部分可并行。
PV4 可按冻结契约先做 fixture，最终验收必须接真数据。
两条实现线预计 6–8 个工作日，另加 Owner 等待。
PV1 结束后按实测速度重估，不承诺固定上线日。
方案 B 另估 2–3 人日，并增加 PROD DDL 批准。

### 9.1 交付验收矩阵

| 用例 | 必须看到的结果 |
|---|---|
| 4.1 accepted，尚未落地 | 主线停在交房；下一步归落地处理方 |
| 4.1 上 main，STG 失败 | 同时显示已合入和发布失败 |
| 未来 Owner 步骤尚未就绪 | 只在 `Later`，不增加 `Needs you` |
| 主线被支线卡住 | 从主线一跳看见支线及责任方 |
| 同一 Work 有多提交 | 不重复计完成；不自动关闭大项 |
| 外部派工尚无提交 | 登记后 60 秒内可见；展示执行方 |
| 评审针对旧 SHA | 新结果仍待复核 |
| 规则撤回、结果被 revert | 当前位置与依赖同步改变；历史保留 |
| 来源不可读 | 显示未知和最后读数；Owner 计数不归零 |
| 控制器重启、重复回放 | 状态一致；无重复工作或近期变化 |
| 多应用、两环境 | 同名 run、提交不串到错误应用或环境 |
| 手机操作 | 能答“现在在哪、下一步谁做、我现在做什么” |

PV1–PV3 跑 Go、MCP 规定检查及迁移后数据库集成测试。
PV4 跑 Console lint、build、现有检查及关键交互测试。
PV5 核验 390×844、1440×900；Light 与 Dark 均可读。
测 500 节点、2000 条边；首屏 API 目标 p95 小于 1 秒。
性能未达时保留失败证据，再决定缓存或迁移。

## 10. 需要 Owner 的具体事项

| 时点 | 要定什么 | 推荐 | 另一选择 |
|---|---|---|---|
| 开实施前 | D-PV1：数据存储 | A，复用事件与产物 | B，类型化表；C，独立计划库 |
| 开实施前 | D-PV2：外部派工 | A，窄登记与观测 | B，统一租约；C，事后发现 |
| 开实施前 | D-PV3：读取契约 | A，独立聚合只读 API | B，扩现有接口；C，前端拼接 |
| PV0 结束 | 采用分类、关系、验收与估算 | 按本稿映射，逐条补证据 | 修改图，不改既定第 4 轮目标 |
| 接线时 | 若现有身份不够，签登记写权限 | 仅本方工作、固定事件 | 不接该入口，明确覆盖缺口 |
| 上 PROD 前 | 发布批准 | 同提交 STG 核验后走现有审批 | 留在 STG |
| PV5 | 手机验收 | 实际回答三个问题 | 指出缺失信息，回修对应片 |

本项不需要重新决定 4.1 自动合入规则。
它读取规则和审批结果，不扩大合入或执行权限。
采用推荐 A 无新增表；如实施发现必须 DDL，先更新切法。

## 11. 本次自检与未验证项

| 项 | 结论 |
|---|---|
| 源码核对 | 已查计划导入、规则、事实、API、MCP、Work 页面 |
| 范围核对 | 只新增此文档；没有实施代码或配置变更 |
| 线上状态 | 未验证；本任务禁止联网 |
| 4.1 新协议 | 按切法对接；本地基线未见 `note.landing` 字段 |
| 运行时 R4 实际进度 | 未读取；文中布局和用例不是实时状态 |
| 外部派工覆盖 | 尚需 PV3 入口接线及 PV5 清单对账 |
| 独立复核 | 本稿尚未经过独立复核；估算已包含后续轮次 |

## 12. PV2 方案 A 的实现契约（Work 630，2026-10-26）

- `bindings[]` 使用封闭的 `agentrt.plan_binding/v1`（`v=1`）：`id/version/tenant/root/node/step/acceptance/acceptance_sha256/atom/source`。`version` 等于所采用的 `plan_version`；`node` 是视图节点，`step` 是该节点或其直属步骤的真实数据库 ID。验收 SHA256 覆盖完整 acceptance 对象。绑定身份摘要覆盖整条绑定。
- 运行时结果固定 `mission/task/attempt/round/repo/result`（完整 SHA）；verification 源另外固定 `verification`。外部运行固定 `external_work/external_seq/report`，须是同一步骤的当前 Submitted 记录，若关联 runtime，任务、mission、提交 SHA 同时一致。
- 四个规则原子统一形状：`{"main_effective":{"binding":"<id>","version":1}}`（其余 atom 同形）。采用视图的既有计划决策先写 `plan_changed`，再为对应步骤安装全部绑定的 `all` 规则；不会写 done。跨步引用、未知版本、跨 dev 租户和悬空引用均拒绝。
- 有限来源：`git → main_effective`；`deployment → deployment_verified`；`verification → review_valid/external_verified`；`owner_signoff → external_verified`。verification 必须对应精确任务、attempt、当前 round 和结果；review 还检查当前轮次的 reviewer spec 及独立 executor/provider。登记报告、exit 0、任意 actor 声称 verified 都不构成核验。
- Owner 来源的 `evidence[]` 是已存产物 ID。现有 Owner 专用签收入口使用 `plan-acceptance:<binding-sha256>` 作为 ref；事件保存节点、绑定摘要、验收摘要、计划版本和证据。更换任意一项必须重新签收。4.10 的五个 `rule_ref` 分别命名 `external_verified:4.10:<acceptance-id>:owner_signoff`；静态 fixture 不伪造已签收事件或 runtime ID。人工签收入口仍遵守 PROD 平台唯一入口规则。
- deployment 固定 `application/environment/check/spec_sha256`；实际 Pod digest、rollout 与 release SHA 由现有平台读取器核对，健康 gate 须对应同一实际 SHA、digest 集合和 spec。后继 SHA 通过完整 Git 历史的当前有效性判断；回滚到不包含结果的版本不通过。目前已接实际部署读取器的 application 只有 `bifrost-platform`；其他应用为 Unknown，不借用平台结果。
- Git 与 Gitea 读取器共用 landinggit 的完整历史判断；先固定 main SHA，再分页；保留 cherry-pick、标准 revert/revert-of-revert。只按准确 Change-Id 或准确 task+result/cherry-pick 身份认定；Work 仅是线索。Gitea 上限 200 页 × 50，截断或父链缺失为 Unknown，不能当 Never。
- controller 每次成功采集（业务值不变也一样）写 `note.plan_observation` 到 `plan-observation:<root>`；来源 ID 为 root+绑定摘要，来源版本是该绑定下串行采集的单调版本。同版本同内容幂等、异内容冲突；乱序旧版本不会覆盖较新版本。事件的 `at` 和 `last_success` 来自服务端。失败保留上一份证据与最后成功时间。
- 每个步骤的新原子及依赖从一个 SQL statement snapshot 读取；只读计划视图仍使用 repeatable-read，并返回逐流 committed 水位。超过 60 秒未成功采集为 Stale，读取失败为 Unknown；两者均不当业务失败，也不继续保持新原子的 done。历史事实保留，当前状态回到 active，依赖按所需 milestone 重算。旧规则的 Unknown 行为不变。
- `note.landing` 继续由现有 `landing.State` reducer 重放，任务详情与近期变化直接读取它；生命周期事件不能替代 Git/部署的当前有效性证明。外部工作保留登记方的 Submitted 状态，另投影 controller 的 verification。
- 无新增表、migration、agent 完成写入口或外部依赖。本片不发布、不将静态第 4 轮计划自动采用到运行环境；人工签收或上线核验仍是实际发生后才能写入的事实。
