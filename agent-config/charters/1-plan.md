# 领域 1「立法」章程（2026-11-24 改写；原「需求与计划」占位页）

出处：Owner 2026-11-23。他在参谋长线程里说了四件事，参谋长转主统筹，主统筹再转本线：

- 闭环排最前面，唯一 owner 是本线。
- 「我们一个个做，先做立法」。
- 「立法的那些 ticket 和行政要执行的 ticket 应该分开，因为标准不一样、内容不一样、难度不一样」。
- 修法票得对着系统里真实的法的记录做增、删、改。

本线的英文标识 `plan` 先不改，会话标题是「0 立法」。

标注：【量】是读代码或线上记录得到的；【推】是推断。读的是 `bifrost-platform` 的 `origin/main` 和 PROD 库（`agent_reader`）。

## 1. 管哪块

立法 = 法的名录 + 修法票的内容规则 + 闭环 + 计划树。

### 1.1 法的名录【量】

- 每条法是一条事件流 `law:<n>`，事件类型 `law_recorded`（迁移 0044，登记在 plan 名下），流里最后一条就是这条法现在的样子。代码在 `api/internal/agentrt/planstore/lawregister.go`。
- 名录有两个写入方：
  - **转录。** 控制器的 `laws` 一步读 infra main 上的 `agent-config/OWNER_LAW.md`。名录里没有的行、文件里改过的行，记成 `transcribed`，带文件名和提交号。
  - **批过的 `law_amend` 卡。**
    - 新增：拿下一个号。
    - 修改：记新的一版。
    - 废止：状态标「废止」。
    - 一条法被卡改过之后，以卡为准，文件不再动它。
- 读函数：
  - `CurrentLaws` / `CurrentLaw`：取当前版本。
  - `NextLawNumber`：取下一个号，名录为空时返回空。审批的建卡校验调这两个。
- 2026-11-24 PROD 有 83 条：82 条从 `OWNER_LAW.md` 转录，第 83 条是 #719（结构弹性）批来的。`OWNER_LAW.md` 的文字本线不改。它搬不搬进名录、怎么搬，由主统筹和 Owner 定。

### 1.2 修法票的内容规则

- 【量】现在在 `api/internal/actions/law_amend.go`，即 approvals 的 `actions` 包。包含读参数、对名录校验、卡面摘要（`ReadLawAmend`、`CheckLawAmend`、`lawAmendSummary`）。文件头写明「定义归立法，改动由立法提」。
- 【推】搬进 plan 的包之后再改归属表，见第 6 节交接。

### 1.3 闭环（开票 → 批 → 计划 → 读数 → 结论 → 归因）【量】

- 批过的 `law_amend` 卡，由 `laws` 一步落成最新一轮里的一个条目，每条标准一个步骤，开始时没有完成规则（没量）。
- 决定依据记成卡的 `approval.card.executed` 事件，Owner 不批第二次。代码在 `planstore/law.go`、`planloop.Loop.Laws`。
- 步骤可以记笔记（`post_plan_note`）：
  - 审计线写结论：「结论 sN：达到|部分|没达到|没核｜标准版本 appr_…｜读数 … @UTC」。
  - 审计线写归因：「归因 sN：类别 法|Agent|工具｜原因｜去向｜标准版本」。
  - 审计和诊断 2026-11-24 起并成一条线。

### 1.4 计划树【量】

- 代码在 `api/internal/agentrt/plan*`，包括 planstore、planloop、planapi、planpace、planreadings、planview、planimport、planwiring 里 plan 的部分。
- 表：`agentrt.plan_node`、`plan_node_binding`、旧的 `mission`。
- 计划的变化是事件，不是单独的表。

## 2. 对外的口子（合约）

- **公开包：** 【量】`config/domain-ownership.json` 里 plan 那一行的 `public_packages`，即 planapi、planloop、planpace、planreadings、planstore。
- **请求应答：** 【量】`GET /api/v1/agentrt/plan`、`/plan/{id}`、`/plan-view`、`/plan-pace`、`/progress`，`POST /plan/proposals`、`/plan/{id}/notes`（架构行和步骤）、`/plan/{id}/signoff`。
- **MCP 工具：** 【量】`get_plan`、`get_plan_view`、`post_plan_note`、`propose_plan_change`、`propose_plan_import`。
- **进程内读口：** 【量】`planstore.CurrentLaw`、`NextLawNumber`、`CurrentLaws`，给行政的建卡校验用。
- **订阅：** 【量】读审批库里已执行的 `law_amend` 卡，经装配层注入的 `Sources.Laws`。
- **事件：** 【量】plan 名下的事件类型见 `bus/registry/ledger/types.yaml`，其中新增了 `law_recorded`。
- **欠着的：** 【推】给人看的名录读接口（`GET /laws`、MCP `get_laws`）和 Console 的名录页。

## 3. 用户与依赖

- **用户：**
  - Owner：批修法票，在页面上看几条达到、没到、没量。
  - 各线：读计划、提计划变更。
  - 审计线：判每条标准，归因。
  - 行政（审批线）：建卡时读名录。
- **依赖：**
  - 行政的卡闸门：存储、推送、过期、审计、执行事件、修法票单独通道（track=law）。
  - 底座的事件日志（eventlog）。
  - Gitea 只读访问，用来读 `OWNER_LAW.md`。

## 4. 权限

- **本线自己定：** 名录和计划的代码、修法票的格式和校验规则、闭环怎么接。
- **始终是 Owner 的：**
  - 法本身的增、改、废，由 `law_amend` 卡批。
  - 标准原文。
  - 改裁判规则（LAW-9）。
  - 根 `CLAUDE.md` 的六类。
- **建卡人：** 修法票由主统筹建（Owner 2026-11-24 明说）。本线起草票面，参谋长核标准原文。

## 5. 目标和读数

- **目标：** 任何一件修法的事，从开票到结论全程在系统里走完，Owner 不用进线程问。
- **主读数：** 一件真事里还靠线程或手写的段数。2026-11-24 是 2（临时读数）：第 4 段「标准对读数的对照表」还在笔记里，第 6 段还没发生。
- **另外四条由审计线量：**
  - Owner 能在页面上读出三个数。
  - 做事的线改不了已批的标准。
  - 换一个席位重跑，结论相同。
  - 行政票：Owner 在 Ops 能分开看到两种票、各几张；推给他的行政票只剩六类。
- **第一件真事：** 结构弹性，第 83 条，#719。审计线量的结果是达到 0、没到 5、没量 2（2026-11-24 02:10Z）。第 83 条的改版票（v2）已定稿，由主统筹建卡。
- 台账：Artifact「Plan 闭环台账」，源文件在共享笔记 `domains/1-plan/closed-loop-ledger.html`。

## 6. 和行政（审批线）的交接（2026-11-24，两边已订）

| 东西 | 归谁 | 状态 |
|---|---|---|
| 法的名录（法的记录） | 立法 | 本来就在 plan |
| 修法票的内容规则：读参数、对名录校验、卡面摘要，连同测试 | 立法 | a 已订：先在 `law_amend.go` 文件头写明定义归立法；b 搬进 plan 包，在行政两支进 main 后做，同时改归属表和挂钩 |
| 建卡校验对名录（法号存在、改前原文对得上、新增写「将成为第 N 条」、读不到就拒） | 行政写挂钩，调立法的读口 | `ready/d5-law-register`（8f18c3c3）合入中 |
| 闸门：目录项 `law_amend`（D 级、无执行方）、Owner 批卡、过期、审计、`approval.card.executed` | 行政 | 不动 |
| Ops 上修法票和日常卡分开的通道（track=law） | 行政 | `ready/d5-law-track2`（fb16cdf7）合入中 |
| 两条票标准的量法 | 审计线 | 已交 |

## 7. 和谁有重叠（2026-11-24 主统筹给了默认判断，本线同意）

- **审计线（原 13 Triage，已和审计合并）：** 法的原文和名录归立法。审计只量、只出结论和归因，不写规矩，让量和写不在同一方。审计章程里「维护法的原文」一句由它去掉。「墙的单子」归谁，两条线另行商量。
- **主统筹与 `OWNER_LAW.md` 的过渡：**
  - 过渡期，主统筹照旧手写登记 Owner 的方向（标「未落」），名录照旧每一轮从文件转录。
  - 切换条件，三件都满足：
    - 行政的建卡校验（`ready/d5-law-register`）进 main 并上 PROD。
    - 单独通道（`ready/d5-law-track2`）进 main 并上 PROD。
    - 有一张修法票从建卡校验走到计划落条目、全程核过。第一张候选是 #727（第 83 条改版）。
  - 切换之后：新法只走修法票；`OWNER_LAW.md` 改成名录的渲染视图，由本线出渲染脚本；主统筹停止手写，名录停止转录。
  - 切换那天本线在这里记日期。
  - 这只改登记方式，不改「法要是系统里的东西」这条方向，不找 Owner。
- **地图线：** 归属表里 law_amend 的归属，等内容规则搬包时一起改。
