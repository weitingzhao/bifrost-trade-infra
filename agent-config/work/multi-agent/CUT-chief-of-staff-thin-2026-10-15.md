# 参谋长薄版：切法（统筹线程 2026-10-15 晚）

依据：`WORKMODE-owner-chief-of-staff-2026-10-15.md`（Owner 10-15 约 20:05、20:10 定）第三节第 2 条、第四节。按那份文件，实施方案不交 Owner 确认；这里写的实施选择由统筹线程定并留痕（ADR §12.2 第 15 条：定了什么、放弃了什么、为什么、怎么推翻），Owner 事后审计。只有工作区 `CLAUDE.md` §5 的架构级两处（D1、D2）写成决策卡等他定。

事实清单（文件:行）来自 10-15 20:20 的只读盘点，平台按主线 `4287e5a` 读。

## 终点

Owner 在 Console 给一句目标 → 一个新起的 Claude 会话（参谋长席位）读运行时里的记录，交出 mission（目标、什么算好、不做什么、预算）、拆好的任务（各带验收命令）、只有 Owner 能答的决策卡（带默认）→ 控制器按程序查常备授权和结构约束，落成记录 → 授权内的任务照常走实现、验收、评审到 accepted。整个过程里统筹线程写入 0（同 T26 的判据：写入者只有 `controller`、`host:*`、`exec:*`、`seat:chief_of_staff`、`owner`）。

## 现在有什么、缺什么

| 块 | 已有 | 缺 |
|---|---|---|
| 目标进规划 | `plan` 岗位、映射到 `planner` 职位、每个 mission 只许一个在跑的规划任务（`0001_core.sql:125,155`，`store/route.go:50`，`store/claim.go:285`）；`seat:chief_of_staff` 主体（`store/seed.go:21`） | `/goals` 现在直接建一件实现任务（`goals.go:125`）；没有 `job-planner` 规则，规划任务没人能领（`route.go:17`）；常备授权的执行者里没有 `exec:claude` |
| 规划结果落成记录 | `ProposeMission`、`ProposeTasks`（`store/propose.go:227,421`）；提问带推荐、不回复会怎样、属于哪件事（`questions/canonical.go:27`）；`envelopeFit`（`store/envelope.go:50`） | 控制器的验收只收 implement、verify、review（`store/accept.go:411`），交上来的规划任务会一直停在 submitted；没有规划结果的结构；`Ask` 只有 Key、Title、Body（`planchange.go:462`）；没有决定记录 |
| Claude 执行者 | 主体 `exec:claude`（`seed.go:17`）、规则里的候选行（`job-implementer.yaml:14`） | agentd 适配（`executors.go:79` 只有 deterministic、codex、cursor）；`bifrost-agentd` 用户下的登录；MCP 隔离 |

## 三片

**第 1 片：Claude 执行者与规划岗位**（约 1 天）
- agentd 加 `exec:claude`：`claude -p --output-format stream-json`，`--strict-mcp-config` 配空的 MCP 配置（不带任何 MCP 服务器，和 Codex、Cursor 的隔离同一目的），`After` 把结果转成 `report.md`（照 `cursorReport`）。
- 规则：新增 `job-planner.yaml`（候选 `exec:claude`）；`standing-envelope-dev.yaml` 的执行者加 `exec:claude`。两份都是放宽，**要 Owner 签**（定规则）。
- `bifrost-agentd` 用户下登录 Claude：凭证，**只有 Owner 能做**；命令到时候给，不留占位符。
- 验收：STG 上手工建一件规划任务，Claude 执行者领到、交出 report。

**第 2 片：目标先进规划任务**（约 0.5–1 天）
- `/goals` 改成：建 mission + 一件 `plan` 任务（effect none），不再直接建实现任务（**D1**）。
- 规划任务的任务书由控制器在建任务时拼好，把五样记录作为快照放进去：目标、在跑的 mission 清单、规则与常备授权、当前进展、最近的决定记录；原始设计（ADR、设计文档）给仓库路径。规划会话只读任务书，不给它读令牌，也不加新路由。
- 任务书里写明规划结果的结构（见第 3 片）和硬约束：每件任务带验收命令；仓库只能是允许清单里的；最高动作、预算不超过常备授权。

**第 3 片：规划结果落成记录**（约 1 天）
- 规划结果的结构：report 里一段 JSON —— mission 的修订（什么算好、不做什么、预算）、任务清单（标题、岗位、仓库、验收命令、依赖）、决策卡（问题、选项、推荐、不回复会怎样、属于三件事里哪一件）、决定（定了什么、放弃了什么、为什么、怎么推翻）。
- 控制器加一个循环：读交上来的规划任务 → 按程序检查结构和常备授权 → 修订 mission（事件 `mission_amended`，类型已在词表里，补它的正文结构）→ `ProposeTasks` → 决策卡走通用的 `Ask`（带选项、推荐、不回复会怎样、属于哪件事）→ 写决定记录（**D2**）→ 规划任务 accepted。检查不过：规划任务 rework，理由写清，最多两轮。
- Console：Progress 的 Agents 道里，mission 下先显示规划任务，再显示它拆出来的任务；决策卡已经会进 Needs you。

**走查**：STG 上建一句目标走到 accepted；然后上 PROD（发版单 Owner 批，有迁移时同单写明），Owner 在 Console 给一句目标，看参谋长写出 mission。

合计约 2.5–3 天，不含等签名和登录。谁写：控制器和路由（第 2、3 片）由 Claude 写、Codex 复核；Claude 执行者（第 1 片）交 Codex 或 Cursor 写（按额度），另一家复核。

## 要 Owner 定的两处（架构级，`CLAUDE.md` §5）

**D1　`POST /api/v1/agentrt/goals` 改行为（改公开接口）**
- 问题：Console 的目标是改成先进参谋长，还是另开一条路由？
- A（推荐）：同一条路由改成建 mission + 一件规划任务；返回的字段不变（`task_id` 变成规划任务的 id）。入口只有一个，合原始设计「Owner 只有一个入口：给目标」。
- B：另加 `POST /api/v1/agentrt/goals/plan`，Console 改用它；旧路由保留直接建实现任务。多一条路由，两个入口并存。
- 不回复会怎样：第 1 片照做（不涉及接口）；第 2 片停在 D1 前。
- 属于：定目标（入口怎么接目标）。

**D2　决定记录放在哪（改事件词表）**
- 问题：参谋长的「定了什么、放弃了什么、为什么、怎么推翻」存成什么，供下一个会话读？
- A（推荐）：事件词表加一种 `decision_recorded`，正文有固定字段（决定、放弃的、理由、推翻办法、谁定的、关联 mission 或任务）。要一个迁移（词表约束加一种），随 PROD 发版走，那张单子你批。程序能查字段，不靠模型记格式。
- B：用现有的 `note` 事件，正文按约定写。不用迁移；但 `note` 是自由文本，格式只靠模型记着。这正是 10-15 你否掉「统一格式」的那种情况。
- 不回复会怎样：第 1、2 片照做；第 3 片的决定记录先不写，其余照做。
- 属于：定规则（参谋长的记录要留什么）。

## 统筹线程定的（留痕，Owner 事后审计）

| 定了什么 | 放弃了什么 | 为什么 | 怎么推翻 |
|---|---|---|---|
| 规划结果放在 report 里的一段 JSON | 新加产物种类 `plan` | 不用改数据库约束；控制器按结构校验，一样是程序在查 | 以后需要单独检索规划时，加种类、迁移旧数据 |
| 五样记录由控制器拼进任务书快照 | 给规划会话读令牌、加列表路由 | 不加路由、不扩大权限；会话起来就有全部输入，可复现 | 记录太大放不进任务书时，改成按需读的只读路由（那时是架构级，再问） |
| 「不做什么」存进 mission 的 `scope_json` 的一个键 | 加列 | JSON 已有，加键不改表 | 需要按它查询时再加列 |
| 规划检查不过就 rework，最多两轮 | 直接 rejected | 和实现岗位同一套规矩（停线规矩） | 改控制器的轮数上限 |
| 第 1 片先做 | 先改路由 | 没有执行者和规则，规划任务没人领；第 1 片不碰接口，不用等 D1 | — |

## 不在这一版

早晚简报、信箱、24 小时在线、资格考试、按能力和额度分流（2.4 完整版）；授权外 mission 的决策卡（分支 `w31/agentrt-22-mission-card`，补强）；agentd 跑 Console 的检查（2.2 补强）。
