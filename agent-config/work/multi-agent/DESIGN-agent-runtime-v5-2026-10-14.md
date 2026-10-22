# 多 Agent 协作运行时：设计 v5（v4 的修订）

- **状态**：**v5 已由 Owner 确认（2026-10-14，§7 八条都选 A），是第 2 轮的实现依据**。修订 2（按 Codex 复核 142 的最小修法）之后的确认复核（复核 143）剩 1 项 A（R3 余项：迁移与新建任务并发），Owner 同意照建议补（5.1.1「步骤锁」、T32 加一种），这一处没有再复核，2.1 写到它时由 Codex 复核代码。复核 141 每一条怎么处理的见 §11，复核 142 的见 §12。§7 第 8 条的 ADR 修订在实现前改进 ADR。
- **和 v4 的关系**：v5 是 `DESIGN-agent-runtime-2026-10-08.md`（v4）的修订，不是重写。v4 和 Owner 定稿的原则（§1）、总体结构（§2）、规则集（§3）、岗位目录（§4）、参谋长的职责与边界（§5.1–5.3）、租户与算力（§6）、发布与副作用（§9）、借鉴与粘合剂策略（§17、§18）、手机端（§19）、进展可观察的要求（§20）、测试编号 T01–T18 都保留。本文只写改了什么、为什么，以及第 2 轮怎么做。和 ADR（`ADR-ops-architecture.md` §1、§5、§12）冲突时以 ADR 为准，§7 第 8 条列出的条款除外：Owner 确认 v5 就是确认这几处 ADR 修订，实现前把它们改进 ADR。
- **本稿吸收的 Owner 要求（2026-10-13 晚，经统筹方转达，都是硬要求）**：
  1. 协作进展最终由平台从运行时状态生成，显示在 PROD Console 的 Progress 页；Agent 主机停了，页面照常显示真实状态（§5.5、§6）。
  2. 设计里不写「开发机」，写「Agent 主机」：第 2 轮是开发机，第 3 轮是 mini 的虚拟机；任何状态都不能只存在 Agent 主机上（§6）。
  3. 现在由 LLM（统筹线程）手工维护的活，逐条改成程序维护（§9）。
  4. **从内往外**：先做数据层（PG 状态库、`redis-agents` 的数据形式），再做接口，最后做界面（§5 的 2.1 → 2.5）。不做内核之前的外层小版本。
  5. 分发任务按**能力和额度**，先判断谁能胜任，再在能胜任的里按额度挑（§5.1、§5.4）。
  6. 分工（Owner 2026-10-13 23:16，`WORK.md` W-31「分工」）：第 2 轮的核心部分（数据层、Redis 数据形式、内核接口、`agentd`、总线与叫停）由 Claude 写、Codex 只读复核；外围活（测试样板、文档、按已定接口填的页面）交 Codex 或 Cursor 写、Claude 验收。
- **证据口径**：平台源码读的是 `bifrost-platform` 的 `origin/main` `5021b0f`（2026-10-13 21:03）；它和 PROD 正在跑的 `38500f9`（审批单 #16，10-13 20:52 发完）之间 `api/`、`mcp/` 没有差异（`git diff --stat 38500f9 origin/main -- api mcp` 为空），所以下文的 `文件:行` 就是 PROD 的行为。平台源码路径省略前缀 `bifrost-platform/api/internal/`。集群用只读身份 `bifrost-agent` 读，时间 2026-10-13 23:00–23:20 CDT；没有读任何 Secret 的内容。没核实的写「未核实」。
- **编号**：W-31。新测试从 T19 接着编（§5.6）。

---

## 1. v5 相对 v4 改了什么

| # | 方面 | v4 是什么 | v5 改成什么 | 为什么 |
|---|---|---|---|---|
| 1 | 运行位置 | `agentd` 第 0 阶段在 MacBook，第 2 阶段迁进 mini 虚拟机（v4 §8、§12） | 设计只认「**Agent 主机**」这个角色。第 2 轮的 Agent 主机是开发机（Mac16,1，10 核，24 GB，会睡），第 3 轮换成 mini 上的虚拟机；换主机只换主机登记和登录，不改平台和数据（§6.3） | Owner 2026-10-13 22:58：先在开发机上把架构做完，再搬虚拟机；10-13 晚：「本机」将来是外置服务器 |
| 2 | 分阶段 | 第 0 步（工作区即代码、Gitea 做主、私有仓库、根目录白名单、硬编码路径、编号、D1、RP、心跳、进展）→ 阶段 0–5 | 第 2 轮按**从内往外**分五步：2.1 数据层 → 2.2 接口层与 `agentd` → 2.3 总线与叫停、本机文件迁进平台 → 2.4 多厂商、按能力和额度分流、参谋长 → 2.5 界面（Progress 页全由接口生成，本机看板退役）。第 3 轮搬 mini 虚拟机。v4 阶段 3–5 在第 3 轮之后。v4 第 0 步里和运行时无关的几项不在第 2 轮（§8） | Owner 2026-10-13：架构做完前不做业务；按他的经验先定数据存储形式，再基于 API 构建 UI |
| 3 | 计划进运行时 | 运行时只有 mission 和任务；进展由事件算（v4 §20.1） | 新增**计划结构**：轮 → 项 → 步，编号一经分配不变；每一步带一条「何时算做完」的规则，只由事件推进（审批执行、提问回答、任务验收、CI 结果、门禁测试通过）。LLM 只能**提议**改计划，不能手改状态。任务挂在哪一步由控制器按提议的上下文写、库里的触发器校验，填错就拒（5.1.1、5.1.2）。「架构对照」也是计划数据，每行的勾由它对应的验收测试结果对照当前部署算出来 | 第 2 轮的计划和进展一换轮次就退化，因为编号和状态由 LLM 手写（Owner 10-13 晚；`board2.py:481-484` 的注释记了一次：第 2 轮的「2.0-1」认不出） |
| 4 | 分流 | 按各家剩余额度分流（v4 §6、§12 阶段 2） | **按能力和额度分流**：先按岗位筛出能胜任的（资格考试、基准题集、在岗成绩、实测的硬约束），再在里面按额度挑。数据层有「执行者 × 模型 × 岗位 × 任务类别」的成绩表和硬约束表；放宽候选名单要 Owner 签 | Owner 2026-10-13 晚 |
| 5 | 租约 | 任务级租约 120 秒、心跳 30 秒、`FOR UPDATE SKIP LOCKED`（v4 §7.2） | 租约挂在**尝试**（attempt）上，带隔离号（lease epoch）：过期先进「过期待续」，宽限期内同一主机可以续；过了宽限期判「丢失」。接管按副作用类别：`none` / `branch` 宽限后可重派（重复计算是写明的代价，每个任务只有一次尝试能被验收），`external` 等旧尝试确认结束才动；平台每次写入都在同一事务里按数据库时间查隔离号（§6.2 接管协议）。沿用审批执行器已经在 PROD 跑的做法（`approvals/execution.go:14-33,355-357`） | Agent 主机会睡；只有一台主机时，任务要能等它醒，又不能让醒来的旧进程写坏状态 |
| 6 | 决策卡 | 新表 `agentrt.decision`（v4 §7.5） | **复用已在 PROD 的「提问」**（`questions/types.go:46-72` 已有选项、推荐、`meanwhile` 即「不回复会怎样」、`work_id`），加两个字段：`owner_duty`（三件事里的哪一件）和 `task_id`。待 Owner 定（§7 第 3 条） | 同一个概念不存两处；提问入口和 Owner 的手机通知已经接好 |
| 7 | 身份 | `actor` 一层 | 身份分**工具**和**模型提供方**两层（ADR §12.10「身份分工具与模型两层」）：执行者是工具（`exec:cursor`），每次尝试记下实际用的模型和提供方；独立验收按提供方判（ADR §12.5）。主机另有一张表；`agentd` 每台主机一把令牌（§7 第 5 条） | Cursor 一家能跑 Claude、GPT、Grok 等多家模型 |
| 8 | 参谋长的形态 | 一个 24 小时在线的席位，跑在 mini 上（v4 §5.2） | 第 2 轮用**任务**实现席位：控制器在固定时点、Owner 说话、出现阻塞时生成 `brief` / `plan` 任务，由坐席的候选执行；Owner 的对话入口是「提问」和信箱（加厂商的 Remote Control 作补充，§4）。24 小时在线随第 3 轮的 mini 虚拟机到位 | 第 2 轮只有一台会睡的 Agent 主机，常驻会话做不到 24 小时；任务形态在主机醒来后自然接着做，状态都在平台 |
| 9 | 基准与考场 | 用 Harbor 或 inspect_swe 做考场，第 0 阶段测 Cursor 20 次（v4 §11） | Gate A 用 `agentd` 本身跑 6 道回放题（§5.2）；20 题全集在 2.4 跑，作为能力成绩的初始数据。外部考场（Harbor / inspect_swe）放到第 3 轮之后 | 第 2 轮的被测对象就是这套运行时；先让它自己跑通 |
| 10 | 进展 | 运行时阶段 1 起由事件算（v4 §20.4） | 2.5 交付：PROD Console 的 Progress 页**完全由接口生成**（计划栏、架构对照、现场、需要他做的事），本机看板（`~/agent-work/status/`）退役；验收是停掉 Agent 主机上的看板程序后 PROD 页照常正确（T24） | Owner 10-13 晚 |
| 11 | 环境 | 状态库和 Redis 只在 PROD | 状态库分 DEV / STG / PROD 三个库，每个库有本环境自己的两个登录角色（5.1.1）；DEV 库给 Agent 主机上 `bdev` 跑的本地 platform-api 开发用。事实只认 PROD | 开发在 Agent 主机上的本地平台进行，需要一份可丢的库 |
| 12 | 第 1 轮已建好、直接成为运行时一部分的 | —（v4 写于第 1 轮之前） | 审批单与编号、执行器领单、提问、ntfy 通知、线程心跳、发版策略与冻结的代码和闸门、CI 门禁、按摘要核对、提交血缘、派工记录的事件格式。逐项见 §3 | 第 1 轮 75 步 2026-10-13 22:11 做完（`WORK.md` W-31「第 1 轮逐项」） |
| 13 | 厂商自带、不必自建的 | v4 §17、§18 有原则，没逐家核对 | 逐家核对了本机命令行的 `--help` 和公开文档，结论分「自建 / 用厂商的 / 先用厂商的、留接口」三类（§4） | 粘合剂策略（ADR §12.2 第 6、7 条） |
| 14 | 结果离开主机 | 收尾时才传产物、推分支、提交（v4 §8） | 一次尝试的结束分三件事：算完（`attempt_computed`）→ 落到平台（`attempt_persisted`：产物进平台、分支推上 Gitea、平台核过）→ 提交。只有落到平台的尝试能被验收。运行中每 5 分钟传一次检查点；过期的尝试仍可把结果保全到自己的分支（`attempt_salvaged`），不改任务状态（5.2、§6.2） | 复核 141 A1：算完没传的结果会随主机丢。剩下的只有「最后一个平台确认的检查点之后、主机彻底坏掉」那一段，作为硬要求 2 的例外请 Owner 定（§7 第 7 条） |

## 2. 现状清点

### 2.1 平台（PROD）

| v4 组件 | 现状 | 证据 |
|---|---|---|
| `agentrt` 内核 | 没有 | `api/internal/` 下没有 `agentrt` 包（`5021b0f` 的目录清单） |
| 推理网关 | 没有 | 同上 |
| 平台用的 PG / 独立的库 | **没有**。平台今天不用 PG | PROD `platform-api`、`platform-workers` 两个 Deployment 的环境变量名里没有任何 PG 相关的（只有 `REDIS_IB_PLATFORM_PASS`、`PLATFORM_ROLE`、`PLATFORM_DATA_DIR`）；`api/go.mod` 只有 `github.com/redis/go-redis/v9`（第 10 行），没有 PG 驱动，`database/sql` / `pgx` 在 `internal/` 下零引用。`bifrost_platform` 库在不在：只读身份列不出 CNPG 的 `Database` 对象（Forbidden），**未直接核实**；`AGENT_FACTS.md:431` 只列了 `bifrost_dev` / `bifrost_stg` / `bifrost_prod` / `bifrost_golden_source` |
| 平台现有的状态存储 | 已有：statefile，每个键一个 ConfigMap | `statefile/statefile.go:1-14`；`statefile/k8sstate/k8sstate.go:26-34`（`platform-state-<key>`，**每个键上限 900 KiB**），冲突重试：Write 最多尝试 3 次（`:88`），Update 最多尝试 5 次（`:130`）。PROD 现有 10 个键：`approvals`、`agent-threads`、`agent-progress/state.json`、`audit/*`（2 个）、`checklist/signals.json`、`patrol/state.json`、`release_cycles_platform.json`、`release-policy-freeze`、`release-policy-reminders` |
| 审批状态机 | 已有 | `approvals/types.go:8-25`：`pending → approved → running → executed / failed`，另有 `rejected`、`expired`、`unknown`；存 statefile 键 `approvals`（`server/server.go:351`）；路由 `approvals/handler.go:21-44`（建单 operator，批 / 驳 admin，领单 executor） |
| 编号 | 已有（审批 `#n`、提问 `Qn`）；工作项 `W-n` 仍由 LLM 在 `WORK.md` 发号 | `approvals/types.go:36-38`、`approvals/store.go:470-478`（`nextNumber`）；`questions/types.go:47-48` |
| 执行器领单（审批） | 已有，有租约 | `approvals/execution.go:22-25`（租约 60 秒、心跳 20 秒、过期 10 分钟后判 `unknown`），`:355-357`（宽限期内可续）；主机执行器 S0-0c 搁置（`WORK.md` S0-0c 状态行） |
| 通知 | 已有（ntfy） | `approvalnotify/notify.go:1-11`：经 .50 的告警中转发到 ntfy；网页推送 S0-0e 未开始 |
| 提问入口（决策卡的雏形） | **部分**：代码在 PROD，PROD 上还没有任何一条记录 | 结构 `questions/types.go:46-72`；路由 `questions/handler.go:17-37`（建 reporter，答 admin）；MCP 工具 `ask_owner`、`wait_for_answer`、`ack_answer`、`withdraw_question`（`mcp/platform/src/index.ts:553-605`）。PROD 命名空间里没有 `platform-state-questions`（第一次写入才建，`server/questions_wire.go:26`）。缺 `owner_duty` |
| 线程心跳 | 已有 | 路由 `server/server.go:479`；事件和状态 `agentthreads/threads.go:74-101`；阈值 `agentthreads/config.go:38-44`（回合中 10 分钟静默、主机 3 分钟失联）；PROD 有 `platform-state-agent-threads` |
| 主机心跳路由 | **部分**：路由在，没有主机在报 | `server/server.go:481` → `agentthreads/handler.go:78-97`；正文只有 `host` 和三家的 `wired` / `token`（`agentthreads/threads.go:246-256`），没有容量、没有租约。脚本 `agent-config/scripts/host-heartbeat.js:1-15`（launchd 每分钟一次）**没有在任何主机加载**（`WORK.md`「宿主心跳与未接入监测」状态行；本机 `~/Library/LaunchAgents` 里没有它的 plist） |
| 协作进展（Progress 页） | **部分（过渡）**：开发机算好、推到平台；平台只存最新一份 | 本机 `~/agent-work/status/board2.py` 每 2 秒算一次（`board2.py:837`），每 15 秒（`board2.py:832`）瘦身后调 `publish-result.js` → `scripts/progress-publish.js` → `PUT /api/v1/agent/progress`（`server/server.go:483`）。平台只留最新一份、上限 256 KiB、5 分钟没更新标过期（`agentprogress/document.go:23-27`；`server/agent_progress_wire.go:11-15` 自称「过渡桥」）。推上去的文档里有 `roadmap.arch`（架构对照）和 `roadmap.round`（本轮步骤），但 Console 只解析 `goal`、`note`、`generated_from`、`stages`、`groups`、`exit`（`console/src/api/agentProgressBoard.ts:135-146`），**这两块在 PROD 页上不显示**。开发机睡了，页面过 5 分钟变「过期」 |
| 发版策略 | **部分：代码和闸门在，策略从没签过** | `releasepolicy/policy.go:1-26`（ssh 签名，读 `cicd/bifrost-release-policy`）；该 ConfigMap 现在 **0 个数据键**（`data:` 与 `binaryData:` 都空），即没有生效的签名策略，所有 C 级发版照旧人工批；卡在 Owner 生成签名私钥（`WORK.md` S0-8「下一步」） |
| 冻结 | 已有（ConfigMap 版），现在未冻结 | `cicd/bifrost-release-freeze` 的 `frozen=false`；PROD `platform-state-release-policy-freeze` 的 `frozen_at` 为空；TD-310 的信任锚已在 PROD。另一套「冻结是一条记录」的协议只有离线判定（`releasefreeze/decision.go:14`），没接线，集群里没有那个资源类型 |
| 发布窗口 | 已有 | 路由 `server/server.go:517-518`；`cicd/bifrost-release-window` 现在不存在（没人持有） |
| 提交血缘 | 已有 | `server/server.go:469-477` |
| 规则集（完整） | 没有；只有上面那份没签的发版策略 | — |
| 岗位、候选、参谋长、资格考试 | 没有 | — |
| 预算 / 额度账本 | 没有；本机 `~/agent-work/status/usage.py`、`cursor-quota.json` 手工读数 | — |
| 产物存储 | 没有；任务书和报告在 `~/agent-work/<事>/` | `DESIGN-host-minimal-2026-10-12.md` §3「平台今天没有收产物的地方」 |
| MCP | 部分：审批和提问的工具在，运行时的工具没有 | `mcp/platform/src/index.ts:514-605` |

### 2.2 infra 与 Agent 主机

| 组件 | 现状 | 证据 |
|---|---|---|
| 派工记录（W-66） | **部分：不可信、不接线** | `agent-config/scripts/recorder/STATUS.md:1-8`（TD-319 关之前任何决定都不许读它的输出）；事件格式 `recorder/events.py:1-5,159-165`（`v=2`、`seq`、`prev_sha256`、按文件串哈希链）；事件词表 `recorder/model.py:11-16,291-347`（`work_opened`、`step_declared`、`step_started`、`step_seen`、`step_finished`、`record_seen`、`owner_wait_*`、`note` 等）；`lane.py:90-135` 派活（后台起 `rec.py run` 包装子进程），`:229-262` 的 `start` / `record` / `stop` / `status`；事件根目录 `~/agent-work/recorder-root` |
| 主机守护进程 `agentd` | 没有；最小版设计停在第 3 稿 | `DESIGN-host-minimal-2026-10-12.md:3`（三次复核「先修」，Owner 定先量再改）；W-67 搁置 |
| 本机看板 | 有，只在本机 | `~/agent-work/status/`：`roadmap.py` 从 `WORK.md` 解析「架构对照」「第 N 轮逐项」；`board2.py:481-489` 的 `step_id_of` 按任务名前缀认计划步骤（过渡做法）；`tasks.json` 是手写行 |
| 线程心跳包装 | 已有 | `agent-config/scripts/thread-heartbeat.js` |
| 平台 CI 的 PG / Redis | 没有 | `k8s/cicd/tekton/pipeline-ci-platform.yaml` 的 `test-api` 只用 `golang:1.25-bookworm`，没有 sidecar（v4 §13 的开放问题仍在） |
| 硬编码的家目录路径 | 大幅减少 | 12 个仓库的 `origin/main` 里只剩 infra 48 行，全在历史报告和计划文档里（`git grep -c`，10-13）；v4 记的是 10-08 三个仓库 103 行。本机看板脚本另有写死的路径（不进仓库，2.5 退役） |
| Gitea | 仍在 `ubt-k3s-01`（v4 第 0 步要搬 05） | Pod `gitea-…` 在 `ubt-k3s-01`；每晚加密备份已在跑（第 1 轮 ④） |
| Agent 主机（开发机） | Mac16,1，10 核，24 GB；会睡 | `sysctl hw.model hw.ncpu hw.memsize`；`pmset -g` |

### 2.3 集群

| 项 | 现状 |
|---|---|
| CNPG | 只有一个集群 `data/bifrost-postgres`：2 实例，在 `ubt-k3s-02`、`ubt-k3s-04`（`nodeSelector node-role=postgres`，必需的反亲和），存储 30 Gi，`spec.managed.roles` 为空；局域网 NodePort `bifrost-postgres-lan` 30432；Trade 三个环境库和 Golden Source 都在它上面 |
| `redis-agents` | **没有**。现有 Redis：`data/redis-dev`（局域网 30379，无密码，只 DEV）、`data/redis-ib`、`data/redis-live-prod`、`data/redis-live-stg`、`cicd/argocd-redis` |
| 平台命名空间 | `bifrost-platform-prod`：`platform-api` 1/1、`platform-workers` 1/1、`platform-console` 2/2；镜像 `bifrost-platform-api:prod` |

### 2.4 和 `WORK.md`「架构对照」（核对于 10-13 23:01）对不上的

1. 「[x] 你只做三件事：审批单、手机通知、提问入口｜在正式环境」：提问入口在 PROD 一次都没用过（没有记录），手机通知是 ntfy、网页推送没开始。提问入口这一半应是 [~]。
2. 「[~] 规则集：…｜只有发版策略」：发版策略**没有签过**，PROD 的策略 ConfigMap 是空的；今天生效的签名规则是零条。按「验收测试算数」应是 [ ]（代码在、没签）。
3. 「[~] 派工记录与进展看板｜…（2.3 迁进平台）」：PROD 的 Progress 页收到了架构对照和本轮步骤，但不显示（见上表）。按从内往外，界面迁移改到 2.5。
4. 表里缺的行（v4 有、表里没有）：计划结构进运行时；产物存储；预算 / 额度账本；按能力分流；发布队列（v4 §9、ADR §12.7）；v4 第 0 步的工作区即代码、Gitea 做主。建议前四行补进表（第 2 轮做），后两项在表里写明「第 2 轮不做」（§8）。

## 3. 复用和替换

| 第 1 轮（及更早）的东西 | 怎么并进运行时 | 何时退役 |
|---|---|---|
| 审批单（statefile，`#n`，执行器租约） | **不搬**：ADR §12.3 定了审批、发版策略与冻结、发布窗口、执行器领单都是修复链状态，永远在 statefile。运行时把它们当外部事实：计划里「（你）批发布单」这类步骤的完成规则写 `approval_executed: 16`，控制器读审批记录、把状态变化记成事件（§5.1 的 `approval_seen`） | 不退役 |
| 审批执行器的租约做法 | 照搬语义，不共用代码：租约 + 心跳 + 宽限期内可续 + 过期判未知、开始过的有副作用的不自动重跑（`approvals/execution.go:14-33,342-357`） | — |
| 提问（questions） | 就是 v4 的「决策卡」：加 `owner_duty`、`task_id` 两个字段（§7 第 3 条）。回答永远不算批准（`questions/transition.go:52` 照旧）；终态提问会被裁剪（`questions/store.go:133`），所以控制器看到的回答抄进 PG 的 `question_seen` 事件，作为不可变事实 | 不退役 |
| ntfy 通知（`approvalnotify`、`notice`） | 运行时的「主机失联」「任务挂起要你定」等通知走同一条路 | 不退役；网页推送不在第 2 轮 |
| 线程心跳（`agentthreads`） | 留给交互线程（统筹线程、参谋长的交互会话）；`agentd` 跑的任务不用它，租约心跳替代 | 不退役 |
| 主机心跳路由和 `host-heartbeat.js` | 由 `agentd` 的领活长轮询替代（主机表的 `last_poll_at`）；三家钩子的接线情况改为 `agentd` 注册时上报（`host.tools_json`） | 2.5 删路由和脚本（改公开接口，要 Owner 点头） |
| `PUT /api/v1/agent/progress` 与单份文档 | 过渡。2.2 起平台有 `GET /api/v1/agentrt/progress`（由运行时状态算），2.5 Console 改读它 | 2.5 删 |
| 派工记录的事件格式（`recorder/`） | **成为内核事件的雏形**：信封（`v`、`seq`、`prev_sha256`、`at`、`by`）、规范 JSON、按流串哈希链原样采用（`recorder/fsutil.py` 的 `canonical_json` 移植到 Go，用记录器的测试向量做 Go 的黄金测试）；词表映射：`work_opened` → 计划项 / mission，`step_declared` → 计划步 / 任务，`step_started` / `step_seen` / `step_finished` → 尝试的开始、进度、结束，`owner_wait_*` → 关联审批和提问的等待事件，`note` → `note`；`fold.py` 从事件折叠状态的规则改写成控制器的投影规则 | `lane.py`、`rec.py` 在 2.3 退役（TD-319 以「退役」关闭，加一条防线：没有任何程序读 `recorder-root`）；历史事件 2.3 导入 |
| `DESIGN-host-minimal` 的主机规则 | 不整篇引用（该文没过复核）；逐条按 3.1 的表：继承的、替换的、第 2 轮暂停的 | — |
| 发版策略、冻结、发布窗口 | 不变。运行时的签名规则复用 `releasepolicy/sshsig.go` 的验签函数和 `anchor.go` 的信任锚，但用自己的签名 namespace，执行的规则从验过签的原文解析（5.2「规则」） | 不退役 |
| CI 门禁、`ref-preflight`、按摘要核对任务 | 成为计划步骤里 `ci`、`release`、`gate` 类的确定性完成条件和验收步骤 | 不退役 |
| 提交血缘（`Change-Id`、`Work:` 尾注） | `agentd` 推的分支提交带 `Agentrt-Task: t_…` 尾注（新克隆里没有 git 钩子，`agentd` 显式加 `--trailer`）。原有尾注照旧必须有：`Change-Id`、`Work`（取任务的 `work_id`）；`Claude-Session`、`Claude-Transcript` 按现有钩子的规则，Claude 执行的才有（`scripts/git-hooks/lineage.sh:42-45`）。血缘接口今天不认 `Agentrt-Task`（`lineage/trailers.go:8-11` 只认那几个键，`lineage/types.go:19` 的 `Commit` 没有这一栏）：解析、返回、在血缘页显示是 2.2 的新工作，验收 T36 | — |
| 本机看板（`board2.py`、`roadmap.py`、`index.html`、`tasks.json`、`HANDOFF.md`） | 不并进；2.5 前照常跑，只修会答错的 | 2.5 退役 |
| `WORK.md` 的「第 N 轮逐项」「架构对照」 | 2.3 一次性导入成计划数据，连同派工记录。`TECH_DEBT.md`、`RATCHETS.md` 第 2 轮仍是 markdown（§7 第 4 条、§8） | 导入后从 `WORK.md` 移出（§7 第 4 条）；`W-n` 索引留在 `WORK.md` |
| `cursor/d1-platform` 分支 | 不合。它要做的「待你定」由提问 + 计划里的 Owner 步骤给出 | 现在就废弃 |

### 3.1 借用 `DESIGN-host-minimal` 的范围

该文停在第 3 稿、没过复核（`DESIGN-host-minimal-2026-10-12.md:3`）。`agentd` 只用下表点名的规则；验收以本文的 T 编号为准，不用它的 A1–A29。

| 处理 | 规则 | 在 v5 里怎么用 |
|---|---|---|
| 继承 | R1、R2、R4、R6；C4、C5；H1、H3、H5、H8 | 原样作 `agentd` 的本地规格：先落盘再起进程；同一尝试永不重起；开机号变了记 `host_reboot`；推送可重放（落点是平台和 Gitea，5.2）；等待上限和硬时限分开；没结论不算过；全新目录、检出干净、任务书字段闭合、本机路径扫描（日志尾部和补丁免扫） |
| 替换 | R3、R5、S1–S5 → 进程组 + 本地登记 + 全机锁（§6.2 接管协议）；R7 → 平台签名规则的有效期（5.2）；L1–L6 → `/claim` 长轮询、尝试心跳、租约与死人开关、`agrt:stop`；H4 → 平台在提议时查、`agentd` 起活前再查；H6 → 分流按模型提供方判独立性（5.1.2 第 ③ 步）；H7 → 只收列明的产物、每个 ≤ 1 MiB，「以槽位身份读」暂停；该文 §3 的专用交接仓库 → 平台产物存储 | 同一用户下没有槽位账户；平台有了领活、租约和产物接口 |
| 钉版本的只读例外 | H2 路径闭包 | 检出里的治理层符号链接（`.claude`、`scripts` 等）指向一份钉住提交号的只读治理层检出（`~/agent-work/governance/<commit>/`，去掉写权限），提交号记进尝试的产物，让 preflight 照样生效；除此之外 H2 照旧，链接解析出检出和列明输入之外的就拒收 |
| 暂停到第 3 轮虚拟机 | S6、S7、H9、H10、P1–P4、C1–C3；该文第 7 节 M1–M15、第 8 节 D1–D6 | 都以「专用槽位账户」或「mini 上的一台主机」为前提，同一用户账户下做不到或没有对象。第 2 轮的并发只在领活时按 `free_slots` 控，不在运行中按采样杀 |

## 4. 厂商现成的能力

本机版本：Claude Code 2.1.295、Codex CLI 0.162.0-alpha.17.2、Cursor Agent 2026.10.01-e373342。只看了 `--help`，没有登录、没有跑任务。公开文档 2026-10-13 读。

| 能力 | Claude Code | Codex | Cursor | 和 v4 的哪一块重叠 |
|---|---|---|---|---|
| 无头执行、结构化输出 | `-p`、`--output-format stream-json`、`--json-schema`、`--include-hook-events`（`claude --help`） | `codex exec --json`（JSONL 事件）、`--output-schema`、`-o`、`--ephemeral`（`codex exec --help`） | `-p`、`--output-format stream-json`（`cursor-agent --help`） | `agentd` 的执行者适配器 |
| 隔离的工作树、沙箱 | `-w/--worktree`；`--restricted`、`--permission-mode` | `--worktree`、`-s read-only / workspace-write`、`-C` | `-w/--worktree`、`--sandbox enabled`、`--mode plan / ask`（只读） | `agentd` 的任务工作区（v4 §8） |
| 钩子（挂 preflight） | 有（工作区 `.claude/settings.json`） | 有（`~/.codex/hooks.json`，要 trust；`--dangerously-bypass-hook-trust`） | 有（用户级 `~/.cursor/hooks.json`） | 宿主强制护栏（v4 §4.1 边界类） |
| 子代理 / 团队 | `--agents`、`--agent` | 未核实 | 未核实 | 任务内部的工具（v4 §18：随便用） |
| 后台 / 常驻会话 | `--bg`、`claude agents --json`、`attach`、`logs`、`stop`、`respawn` | `app-server daemon`（JSON-RPC，标 experimental）、`codex agents`、`codex queue` | `persist`（断开终端仍活） | `agentd` 的进程监管 |
| 远程操控（手机） | `--remote-control`；Remote Control 支持 Pro / Max（[docs](https://code.claude.com/docs/en/remote-control)，10-13） | `remote-control`（experimental） | 未核实 | v4 §19 的对话入口 A |
| 定时 / 云端任务 | Routines：Pro / Max 可用，跑在 Anthropic 云上，触发方式有定时、API、GitHub；默认网络只放行白名单域名；仓库只能是 GitHub（[docs](https://code.claude.com/docs/en/routines)，10-13） | `codex cloud exec / status / list / diff / apply`（experimental） | 云端 Agent（未核实细节） | v4 §8「云端 Agent 只碰公开仓库」 |
| 自托管执行器（厂商的队列、我们的机器） | Self-hosted environments：runner 主动外连领会话、租约约 60 秒、轮询即心跳；**只对 Team / Enterprise 公测**（[docs](https://code.claude.com/docs/en/self-hosted-environments)，10-13）；CLI 有 `--environment` | 未核实 | `agent worker`：My Machines 个人 worker，Agent 循环在 Cursor 云，工具调用在本机，主动外连、不开入口；用网页或 `POST /v1/agents` 指派（API 的认证方式未核实）（`cursor-agent worker --help`；[docs](https://cursor.com/docs/cloud-agent/my-machines)，10-13；适用套餐未写明） | `agentd` + 内核的领活（但队列和状态在厂商云） |
| 代码评审命令 | `ultrareview`（云端多 Agent 评审） | `codex review --commit <SHA>` / `--base` / `--uncommitted`（无头） | `--mode ask` | 验收岗位的「评审」一步 |
| ACP | 未核实（只有第三方适配器） | 未核实 | `agent acp`（启动 ACP 服务；主帮助里不列，子命令帮助在） | v4 §17：给没有钩子的执行者补护栏 |
| Agent SDK | 用 API key 认证；文档写明除非事先批准，不允许第三方产品提供 claude.ai 登录（[docs](https://code.claude.com/docs/en/agent-sdk/overview)，10-13） | — | — | v4 §8「只调官方命令行，不提取令牌」 |
| 订阅额度读数 | 帮助里没有可编程读数的命令，未核实 | 未核实 | 未核实 | 额度账本（v4 §7.4） |

**结论**

| 类别 | 内容 |
|---|---|
| **自建** | 运行时状态（计划、mission、任务、尝试与租约、事件、产物、验收记录、规则、额度与能力账本）；**跨厂商「一家写、另一家审」的强制**；**「权威在代码不在 LLM」**——状态只经控制器按事件改（v4 认定厂商不会替我们做，保持自建）；签名规则集；按能力和额度的分流；`agentd`（薄：领活、起进程、心跳、收产物、死人开关）；进展投影；决策卡的语义 |
| **用厂商的** | 模型与推理；无头执行和结构化输出（`claude -p`、`codex exec`、`cursor-agent -p`）作为执行者适配器的实现；任务内部的子代理、工作树、沙箱；钩子（挂 preflight）；`codex review --commit` 作为评审执行者的一种实现（谁来评审仍由我们按规则定）；Owner 和参谋长交互会话之间的对话用 Claude 的 Remote Control（Pro / Max 可用）作补充入口；macOS 的 `caffeinate` 防空闲睡眠 |
| **先用厂商的、留接口** | 后台 / 常驻会话（`claude --bg`、`cursor-agent persist`、`codex app-server`）：第 2 轮不用，执行者接口留一个「会话型」实现位；自托管执行器（Cursor My Machines、Claude self-hosted environments）：它们把队列和状态放在厂商云，和「状态放我们的」冲突，只能作为某一类任务的执行者适配器（我们的任务镜像过去、结果回来再验收），第 2 轮不用，Claude 那一种还要 Team / Enterprise；云端任务（Routines、Codex cloud、Cursor 云端 Agent）：只做公开仓库的纯代码任务，连不到局域网平台（v4 §8；平台不开公网，v4 §19.3），第 2 轮不用；ACP：Cursor 有，第 3 轮之后接 |

## 5. 分步计划（从内往外）

总则：
- 每一步按验收测试算数；纸面上有不算。每步的「★」那一项在 PROD（或集群）上实测通过才算这一步做完。
- 谁写（Owner 10-13 23:16）：核心部分 Claude 写、Codex 只读复核、复核问题由 Claude 改；外围活（测试样板、文档、2.5 按已定接口填的页面）Codex 或 Cursor 写、Claude 验收；复核问题不退回 Cursor（`WORK.md` W-66「指派规矩再改一处」）。
- 工作区规矩里要 Owner 点头的（新增表或列、新外部依赖、改公开接口、PROD DDL、集群清单、Secret、PROD 发布单），全部列在 5.7 的依赖清单里，每一步的「Owner 动手」指向它的行号。

### 5.1 第 2.1 步：数据层（状态库 + `redis-agents` 的数据形式）

**交付物**：三个库与六个登录角色；迁移文件和迁移作业；Go 的存储包 `api/internal/agentrt/store`（只有数据访问，不开 HTTP），含中继（`outbox` → Redis）和重建两组函数，以及它们对真 Redis 的测试（CI sidecar）；`redis-agents` 的清单和它的 key 约定；本节的测试。2.3 只把中继接进 `platform-workers`、接长轮询和广播。

#### 5.1.1 库、角色、迁移

| 项 | 定法 |
|---|---|
| 库 | CNPG `data/bifrost-postgres` 上新建 `bifrost_platform`（PROD）、`bifrost_platform_stg`、`bifrost_platform_dev`；schema 都叫 `agentrt`。DEV 库给 Agent 主机上 `bdev` 的本地 platform-api 用，经局域网 NodePort 30432 连 |
| 角色 | 同一 CNPG 集群里登录角色是集群级的，一个名字只有一套密码，所以按环境分名：`agentrt_owner_{dev,stg,prod}`（登录，只给本环境的迁移作业用，属主）；`platform_agentrt_{dev,stg,prod}`（登录，本环境的平台运行时用，只有 DML，见下表）；每个角色一个 Secret（共 6 个，Owner 建）。每个库 `REVOKE CONNECT ON DATABASE … FROM PUBLIC`，CONNECT 只给本环境的两个角色和 `agent_reader`（已有，对 `agentrt.*` 只读）。STG、DEV 的身份连不上 PROD 库（T19） |
| 创建方式 | 跟现有的四个库走同一条路（统筹方 10-14 读 infra 文件核实）：库是 CNPG `Database` 对象，写进 `k8s/data/databases.yaml`（现有 `bifrost_dev/stg/prod`、`bifrost_golden_source` 都在这里，属主 `bifrost`），新三个库的属主是本环境的 `agentrt_owner_<env>`。角色**不是** CNPG 托管角色（`k8s/data/cluster.yaml` 里没有 `managed.roles`），而是 db-step：`scripts/release/db-steps.d/*.md` 加 `db-steps.d/sql/*.sql`，照 `sql/2026-10-09-w33-agent-reader.sql` 的样子写；PROD 那一步是 PROD DDL，按规矩 Owner 先点头 |
| 角色矩阵 | 同一次改动把三个库和六个角色登记进 `k8s/data/role-matrix/expected.yaml`（库清单在 `:7-11`，每个角色的授权在其下）。每日 CronJob 按它核对、漂移就 `BifrostDbPrivilegeDrift` 告警，所以「STG、DEV 的身份连不上 PROD 库」每天都查，不只在 T19 里验一次 |
| 备份 | 物理备份（barman，`k8s/data/cluster.yaml:46-59`，保留 30 天）备整个集群，新库自动在内。逻辑备份按「库:schema」逐个导出（`k8s/data/logical-backup/cronjob-backup.yaml:82-86` 的 `TARGETS`），要加 `bifrost_platform:agentrt`；之后每月 1 日 06:00 UTC 的逻辑恢复演练自动覆盖它（告警 `BifrostLogicalBackupDrillStale`）。§7 第 1 条「新库确实在备份和恢复范围里」的验收是两件：逻辑演练里出现 `bifrost_platform:agentrt` 且通过；物理备份恢复到临时集群一次（O11） |
| 迁移 | 只往前、不回退；SQL 文件嵌进平台二进制（`api/internal/agentrt/migrations/0001_core.sql` …），`platform-api agentrt-migrate` 子命令按序执行，每个文件一个事务，写 `schema_migration`（文件号、sha256）；已执行文件的 sha256 变了就失败。整个迁移持 `pg_advisory_lock`：两个同时起，后一个等前一个做完，再发现无事可做。只做扩展型改动（加表、加列、先补数据再加约束），旧二进制在新结构上照常工作。集群里是挂起的 CronJob 模板 `agentrt-migrate`（STG、PROD 各一），用现有动作 `create_job_from_cronjob` 起；执行前照规矩 `grep -niE 'drop\|truncate'`（表格里 `\|` 即 `|`） |

权限（`platform_agentrt_<env>`）：

| 表 | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| 只追加的表：`event`、`artifact`、`artifact_blob`、`verification`、`budget_ledger`、`capability_score`、`rule`、`plan_node_binding`、`schema_migration` | ✓ | ✓ | — | — |
| `event_stream`（每条流的头） | ✓ | ✓ | ✓ | — |
| 状态表：`actor`、`host`、`plan_node`、`mission`、`task`、`task_dependency`、`attempt`、`message`、`control`、`vendor_pool`、`job`、`job_candidate`、`capability_fact` | ✓ | ✓ | ✓ | — |
| `outbox`（投递簿记，不是状态） | ✓ | ✓（`event_id` 须是本事务的事件） | 只许改 `delivered_at`、`tries` | — |
| `idempotency_key` | ✓ | ✓ | — | ✓（只删过期的） |

触发器（数据库层的保证，不只是接口的约定）：
- 只追加的表上任何 `UPDATE` / `DELETE` 报错，属主角色也一样（T23a）。
- **状态表**上每个 `INSERT` / `UPDATE` 要求本事务先 `SET LOCAL agentrt.event_id = <id>`，且这条事件是本事务插入的（`event.txid` 默认 `txid_current()`，触发器比相等）；事件的 `task_id`、`attempt_id`、`mission_id`、`plan_node_id` 在该行有对应列时必须相等。这条检查是即时的（本事务先插的事件读得到）；而事件指向本事务才新建的对象的外键是延期的（5.1.2 `event` 草图里的 `DEFERRABLE INITIALLY DEFERRED`），提交时才核对，所以「先写事件、再建它指向的行」走得通（复核 142 R1）。生命周期和授权状态因此一定带事件（T25）。**唯一的例外是存活列**：只改 `attempt.heartbeat_at`、`attempt.lease_expires_at`、`host.last_poll_at` 的 `UPDATE` 放行、不带事件；`lease_expires_at` 只许往后推，且同一条语句里 `state`、`lease_epoch` 不变；同时改了别的列就照常要事件。心跳续租推的 `lease_expires_at` 算不算存活列，统筹方的决定没写到，取最简单的：算，心跳不写事件。
- `plan_node`：改 `plan_node_id`、`parent_plan_node_id`、`node_kind`、`ordinal`、`created_*` 报错，`DELETE` 报错；父子类型只许 `round → item → step`、`arch_root → arch_row`。
- `task`（建时即时查；建后的改动见下条）：`plan_node_id` 必须指向 `step`；那一步绑了 mission 时 `task.mission_id` 必须等于它；有 `subject_task_id` 的（验收、评审）`plan_node_id`、`off_plan` 必须和对象任务相同（返工是同一个任务 `round_no + 1`，自然同一步）。
- **绑定固定**（复核 142 R3）：一步一经挂了任务，它的 `mission_id`（含从空绑上）和这些任务的 `plan_node_id`、`mission_id` 都固定。确需迁移，只能是一次原子的计划变更（本事务的事件是 `plan_changed`，正文写明迁移），提交时对最终状态重验：这一步下每个任务的 `mission_id` 等于这一步的；验收、评审任务仍和对象同一步；每条 `done_rule` 仍只引用绑在自己这一步的对象。任何一条不合，整个事务回滚。重验用延期的约束触发器（`CREATE CONSTRAINT TRIGGER … DEFERRABLE INITIALLY DEFERRED`），一次变更里先改步骤还是先改任务都不会卡在中间状态；不经 `plan_changed` 的这类 UPDATE 直接拒。
- **步骤锁**（复核 143 的 R3 余项，Owner 2026-10-14 同意照补、未再复核）：挂步骤、改绑、迁移三条路径对同一步先拿同一把行锁，再读最新状态、再校验。`task` 的触发器在检查之前做 `SELECT … FROM agentrt.plan_node WHERE plan_node_id = NEW.plan_node_id FOR SHARE`（改绑时新旧两步都锁），检查用这条锁定语句读回的行（READ COMMITTED 下等锁之后读到的是最新提交的版本）；`plan_changed` 的迁移对它动到的每一步先 `FOR UPDATE`。并发新建任务之间互不挡（都是共享锁），迁移和挂任务互相挡：迁移先拿到锁，挂任务等它提交后读到新的 mission，不合就拒；挂任务先拿到锁，迁移等它提交，提交时的重验看得到新任务，不合就整个迁移回滚。锁加在触发器里，任何写路径都绕不过。
- `task_dependency` 插入先拿依赖图的一把事务级锁（`pg_advisory_xact_lock(<固定键>)`，全库一把），再沿已提交的依赖查，成环就拒。并发插 A→B、B→A 的两个事务，后拿到锁的那个等前一个提交，拿锁之后的查询（READ COMMITTED，新快照）看得到那条边，被拒。
- `verification`：`accepts_attempt = true` 的行要求被验的尝试 `persisted_at` 非空。

#### 5.1.2 表结构草图

命名按 `database-design`：多行表主键 `<表名>_id`，外键沿用被引用主键名（带角色前缀的以它结尾）；jsonb 列以 `_json` 结尾。下面是草图，正式 DDL 随实现和复核定稿后交 Owner。建表顺序按依赖排（`actor` → `rule` → `artifact` → `mission` → `plan_node` → …）。

```sql
-- 谁
CREATE TABLE agentrt.actor (
  actor_id        text PRIMARY KEY,  -- 'host:mbp-dev' 'exec:codex' 'exec:cursor' 'exec:claude' 'exec:deterministic'
                                     -- 'controller' 'owner' 'seat:chief_of_staff' 'thread:local_…'
  actor_kind      text NOT NULL CHECK (actor_kind IN ('host','executor','controller','owner','seat','thread')),
  tool            text CHECK (tool IN ('claude','cursor','codex','deterministic')),
  display_name    text NOT NULL,
  created_at      timestamptz NOT NULL DEFAULT now(),
  retired_at      timestamptz,
  CHECK ((actor_kind = 'executor') = (tool IS NOT NULL))
);

CREATE TABLE agentrt.host (                         -- Agent 主机
  host_id         text PRIMARY KEY,                 -- 'mbp-dev'（第 2 轮）、'mini52-vm1'（第 3 轮）
  actor_id        text NOT NULL UNIQUE REFERENCES agentrt.actor(actor_id),
  host_kind       text NOT NULL CHECK (host_kind IN ('dev','vm')),
  state           text NOT NULL CHECK (state IN ('active','draining','retired')),  -- 在线 / 失联不存，按 last_poll_at 算
  capacity_json   jsonb NOT NULL DEFAULT '{}',      -- {"slots":1,"cores":10,"mem_gb":24}
  tools_json      jsonb NOT NULL DEFAULT '{}',      -- {"codex":{"version":"…","models":[…],"pools":[…],"hooks_wired":true}}
  agentd_version  text,
  last_poll_at    timestamptz,                      -- 存活列：领活长轮询时直接写，不带事件，最多每 30 秒一次
  version         int NOT NULL DEFAULT 0
);

-- 计划：轮 → 项 → 步；架构对照也在这里
CREATE TABLE agentrt.plan_node (
  plan_node_id         text PRIMARY KEY,   -- 'R2'、'R2:2.1'、'R2:2.1-3'、'ARCH'、'ARCH:state-db'；分配后不变
  parent_plan_node_id  text REFERENCES agentrt.plan_node(plan_node_id),
  node_kind            text NOT NULL CHECK (node_kind IN ('round','item','step','arch_root','arch_row')),
  ordinal              int  NOT NULL CHECK (ordinal >= 0),   -- 在兄弟里的位置；只追加，不复用
  label                text NOT NULL,      -- 显示用：'2.1'、'①'、'A'、'2.1-3'
  title                text NOT NULL,
  work_id              text,               -- 'W-31'、'TD-295'
  mission_id           text REFERENCES agentrt.mission(mission_id),   -- step 绑了 mission，挂它的任务必须属于它
  step_kind            text CHECK (step_kind IN ('agent','review','owner','approval','release','ci','gate','manual')),
  owner_step           boolean NOT NULL DEFAULT false,   -- 「（你）」
  effect_step          boolean NOT NULL DEFAULT false,   -- 「★」
  done_rule_json       jsonb NOT NULL DEFAULT '{}',      -- 见下；改它是计划变更，带 plan_changed 事件
  state                text CHECK (state IN ('planned','active','done','stopped','dropped')),  -- 只有 step 存；别的按「计数」算
  state_event_id       bigint,             -- 最近一次改 state 的事件（event 建好后加外键）
  usual_s              int,
  created_by_actor_id  text NOT NULL REFERENCES agentrt.actor(actor_id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  version              int NOT NULL DEFAULT 0,
  UNIQUE (parent_plan_node_id, ordinal),
  CHECK ((node_kind IN ('round','arch_root')) = (parent_plan_node_id IS NULL)),
  CHECK ((node_kind = 'step') = (step_kind IS NOT NULL)),
  CHECK ((node_kind = 'step') = (state IS NOT NULL))
);
-- 父子类型和改号由触发器挡（5.1.1）；step 的 state 只随 plan_node_state_changed 事件改
```

`done_rule_json` 的语法（闭合，控制器解释；不认识的原子使整条规则判「未知」，不判做完）：`{"all":[…]}` / `{"any":[…]}`。原子分两类：
- **历史事实**（一经成立就一直成立，不重验）：`{"task_accepted":"t_…"}`、`{"approval_executed":16}`、`{"question_answered":{"question":"Q3","option":"A"}}`、`{"ci_succeeded":{"repo":"bifrost-platform","commit":"<40 位>"}}`、`{"owner_signoff":"TD-295"}`、`{"manual":"<说明>"}`（人工补记，要附证据产物）。
- **持续条件**：`{"gates_passed":[{"test":"T19","spec_sha256":"<64 位>"}],"env":"prod"}`。每次求值都对照该环境**现在**部署的东西（读平台自己的交付记录：提交和镜像摘要）：只有 `method='gate'`、`check_ref` 等于原子里的测试编号、`verdict='pass'`、`env` 相同、`subject_commit` 和 `deploy_ref_json` 等于现在部署的、`spec_sha256` 等于规则里钉的，且它的 `attempt_id` 确是它 `task_id` 的一次尝试的那条 `verification` 才算（复核 142 B4：一份规格里有几个测试编号时，别的编号的 PASS 不算这一个）。别的提交、别的部署、别的规格都不算；交付记录读不出来，这个原子是 `unknown`，整条不判做完。

**只能引用绑在这一步上的对象**：`task_accepted` 的任务必须 `plan_node_id` 等于这一步；审批号和提问号要先有一行 `plan_node_binding`（随 `plan_changed` 事件写入，即经授权的计划变更）；`owner_signoff` 事件带的 `plan_node_id` 必须等于这一步。存储包写入时校验，不合就拒收。

**计数**（只在这里定一次；T32）：item、round 的状态和「做完几步」都按下面算，不存。分母 = 该项下 `state ≠ 'dropped'` 的步；`stopped` 算没做完；靠 `manual` 原子做完的算做完，并单独标出个数（Progress 标「人工」）；给做完的项加一步，项自然回到没做完。arch_row 的勾 = 它的完成规则此刻的求值（只用持续条件，所以每次新部署都重新判）。step 的规则里有持续条件的，条件不再成立时控制器记 `plan_node_state_changed`（`done → active`，cause `standing_lapsed`）。

```sql
CREATE TABLE agentrt.mission (
  mission_id           text PRIMARY KEY,   -- 'M-1'，平台发号
  work_id              text,
  title                text NOT NULL,
  goal                 text NOT NULL,
  success_json         jsonb NOT NULL,     -- 成功标准
  scope_json           jsonb NOT NULL,     -- 仓库、路径、最高动作级（第 2 轮恒为 'branch'）、禁区
  tenant               text NOT NULL DEFAULT 'dev' CHECK (tenant IN ('dev','business')),
  envelope_rule_id     text, envelope_rule_version int,   -- 落在哪条常备授权里（外键到 rule）
  state                text NOT NULL CHECK (state IN ('proposed','awaiting_owner','active','paused','done','stopped','expired')),
  deadline_at          timestamptz NOT NULL,              -- 默认 7 天
  budget_json          jsonb NOT NULL,                    -- 尝试次数、墙钟、各额度池上限
  spec_artifact_id     text REFERENCES agentrt.artifact(artifact_id),   -- MISSION.yaml
  created_by_actor_id  text NOT NULL REFERENCES agentrt.actor(actor_id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  version              int NOT NULL DEFAULT 0
);

CREATE TABLE agentrt.task (
  task_id              text PRIMARY KEY,   -- 't_' + ULID
  mission_id           text NOT NULL REFERENCES agentrt.mission(mission_id),
  plan_node_id         text REFERENCES agentrt.plan_node(plan_node_id),  -- 它服务的那一步；控制器按提议上下文写（5.2）
  off_plan             boolean NOT NULL DEFAULT false,   -- 计划外的活，Progress 标「计划外」
  off_plan_reason      text,
  parent_task_id       text REFERENCES agentrt.task(task_id),            -- 取消沿它往下传
  subject_task_id      text REFERENCES agentrt.task(task_id),            -- verify / review 的对象
  role                 text NOT NULL CHECK (role IN ('plan','implement','verify','review','brief','other')),
  task_class           text NOT NULL,      -- 'go'、'python'、'ts'、'shell'、'design'、'doc'；能力表按它分
  core                 boolean NOT NULL DEFAULT false,   -- 核心部分（Owner 10-13：Claude 写、Codex 只读复核）
  title                text NOT NULL,
  spec_artifact_id     text NOT NULL REFERENCES agentrt.artifact(artifact_id),   -- 任务书
  repo                 text,
  base_commit          text CHECK (base_commit ~ '^[0-9a-f]{40}$'),
  effect_class         text NOT NULL CHECK (effect_class IN ('none','branch','external')),
  needs_json           jsonb NOT NULL DEFAULT '[]',      -- 能力需求：["listen_ports","git_commit"]
  route_json           jsonb NOT NULL DEFAULT '[]',      -- 分流结果的快照（候选顺序），由控制器写
  state                text NOT NULL CHECK (state IN ('proposed','awaiting_owner','ready','leased','running',
                         'submitted','verifying','accepted','rework','rejected','blocked','paused','cancelled')),
  round_no             int NOT NULL DEFAULT 1,
  max_rounds           int NOT NULL DEFAULT 2,
  usual_s              int,
  hard_limit_s         int NOT NULL,
  version              int NOT NULL DEFAULT 0,           -- 比较后写入
  created_by_actor_id  text NOT NULL REFERENCES agentrt.actor(actor_id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  updated_at           timestamptz NOT NULL DEFAULT now(),
  CHECK (off_plan = (plan_node_id IS NULL)),
  CHECK (off_plan = (off_plan_reason IS NOT NULL))
);
CREATE INDEX task_ready_idx   ON agentrt.task (created_at) WHERE state = 'ready';
CREATE INDEX task_mission_idx ON agentrt.task (mission_id, state);
CREATE INDEX task_plan_idx    ON agentrt.task (plan_node_id);
CREATE UNIQUE INDEX task_one_live_plan ON agentrt.task (mission_id)
  WHERE role = 'plan' AND state IN ('leased','running');            -- v4 7.2：一个 mission 同时只有一张规划任务

CREATE TABLE agentrt.task_dependency (
  task_dependency_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  task_id                text NOT NULL REFERENCES agentrt.task(task_id),
  depends_on_task_id     text NOT NULL REFERENCES agentrt.task(task_id),
  UNIQUE (task_id, depends_on_task_id),
  CHECK (task_id <> depends_on_task_id)
);

CREATE TABLE agentrt.plan_node_binding (               -- 一步上绑的外部对象；只追加
  plan_node_binding_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  plan_node_id         text NOT NULL REFERENCES agentrt.plan_node(plan_node_id),  -- 必须是 step
  bound_kind           text NOT NULL CHECK (bound_kind IN ('approval','question')),
  bound_ref            text NOT NULL,                  -- '16'、'Q3'
  event_id             bigint NOT NULL REFERENCES agentrt.event(event_id),         -- plan_changed
  UNIQUE (plan_node_id, bound_kind, bound_ref)
);

CREATE SEQUENCE agentrt.lease_epoch_seq;              -- 隔离号，全局单调

CREATE TABLE agentrt.attempt (                        -- 一次执行；租约挂在这里
  attempt_id           text PRIMARY KEY,               -- 'a_' + ULID
  task_id              text NOT NULL REFERENCES agentrt.task(task_id),
  attempt_no           int  NOT NULL,
  executor_actor_id    text NOT NULL REFERENCES agentrt.actor(actor_id),   -- 'exec:codex'
  host_id              text REFERENCES agentrt.host(host_id),             -- 平台执行的（审批、CI）为空
  model                text,                           -- 实际用的模型
  model_provider       text,                           -- 'anthropic'、'openai'、'xai'… 独立验收按它判
  lease_epoch          bigint NOT NULL,
  lease_expires_at     timestamptz NOT NULL,           -- 存活列（只许往后推）
  heartbeat_at         timestamptz NOT NULL,           -- 存活列：心跳直接写，不带事件，事件日志回放不出它
  computed_at          timestamptz,                    -- attempt_computed：执行者退出，结果在 agentd 本地
  persisted_at         timestamptz,                    -- attempt_persisted：产物进平台、分支推上 Gitea，平台核过
  state                text NOT NULL CHECK (state IN ('leased','running','stale','submitted','finished','lost','cancelled','failed')),
  started_at           timestamptz,
  ended_at             timestamptz,
  end_how              text CHECK (end_how IN ('exit','hard_limit','over_capacity','cancelled','daemon_restart','host_reboot','lease_lost')),
  exit_code            int,
  conclusion           text CHECK (conclusion IN ('done','failed','none')),
  report_artifact_id   text REFERENCES agentrt.artifact(artifact_id),
  pushed_ref           text,                           -- 'refs/heads/agent/t_…/a2'（每次尝试一个分支，不互相覆盖）
  pushed_commit        text CHECK (pushed_commit ~ '^[0-9a-f]{40}$'),
  UNIQUE (task_id, attempt_no)
);
CREATE UNIQUE INDEX attempt_one_live ON agentrt.attempt (task_id) WHERE state IN ('leased','running','stale');
CREATE INDEX attempt_lease_idx ON agentrt.attempt (lease_expires_at) WHERE state IN ('leased','running','stale');

-- 事件：只追加，按流串哈希链
CREATE TABLE agentrt.event_stream (
  event_stream_id   text PRIMARY KEY,     -- 'plan:R2'、'mission:M-1'、'host:mbp-dev'、'rule'、'system'、'legacy:recorder'
  last_seq          bigint NOT NULL DEFAULT 0,
  last_sha256       text   NOT NULL DEFAULT '',
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE agentrt.event (
  event_id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_stream_id   text   NOT NULL REFERENCES agentrt.event_stream(event_stream_id),
  seq               bigint NOT NULL,
  event_type        text   NOT NULL,      -- 闭合词表，见 5.1.3；Go 里按类型校验正文字段
  -- 下面五个外键提交时才查：同一事务里先写事件、再建它指向的行（mission、计划节点、任务、尝试首建；actor 为种子）
  actor_id          text   NOT NULL REFERENCES agentrt.actor(actor_id) DEFERRABLE INITIALLY DEFERRED,
  mission_id        text   REFERENCES agentrt.mission(mission_id) DEFERRABLE INITIALLY DEFERRED,
  plan_node_id      text   REFERENCES agentrt.plan_node(plan_node_id) DEFERRABLE INITIALLY DEFERRED,
  task_id           text   REFERENCES agentrt.task(task_id) DEFERRABLE INITIALLY DEFERRED,
  attempt_id        text   REFERENCES agentrt.attempt(attempt_id) DEFERRABLE INITIALLY DEFERRED,
  cause_event_id    bigint REFERENCES agentrt.event(event_id),
  body_json         jsonb  NOT NULL,
  prev_sha256       text   NOT NULL,      -- 流的第一条为 ''
  sha256            text   NOT NULL,      -- sha256(规范 JSON(信封 + 正文))，和记录器同一种规范化
  txid              bigint NOT NULL DEFAULT txid_current(),   -- 状态表触发器用它认「同一事务」（5.1.1）
  at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (event_stream_id, seq)
);
CREATE INDEX event_task_idx    ON agentrt.event (task_id, event_id);
CREATE INDEX event_mission_idx ON agentrt.event (mission_id, event_id);
CREATE INDEX event_type_at_idx ON agentrt.event (event_type, at);
```

写事件的唯一路径（存储包里一个函数）：同一事务里（流第一次用时先 `INSERT INTO event_stream … ON CONFLICT DO NOTHING`）`SELECT … FROM event_stream WHERE event_stream_id = $1 FOR UPDATE` → 算 `seq = last_seq + 1`、`prev_sha256 = last_sha256`、`sha256` → `INSERT event` → 更新 `event_stream` → `SET LOCAL agentrt.event_id` → 写对应的状态表行（带 `version` 比较）→ 写 `outbox`。首建 mission、计划节点、任务、尝试时，事件先于它指向的行插入，靠上面的延期外键在提交时核对；提交失败（例如事件指向的行最后没建）整个事务回滚，事件、流头、发件箱一起撤掉，流的 `seq` 不跳号。除存活列外，状态表的改动没有事件就过不了触发器，直接 SQL 也一样（5.1.1，T25）。

**空库的种子顺序**（复核 142 R1；2.1 的种子迁移由 `agentrt-migrate` 用上面同一个函数、在一个事务里、以属主角色做，不关任何触发器；T19）：① 建流 `system`（`event_stream` 不是状态表，不要事件）；② 写第一条事件 `actor_registered`（`system` 流 `seq` 1、`prev_sha256` 为 ''，`actor_id='controller'`：这时 `controller` 那一行还没有，靠延期外键）；③ `SET LOCAL agentrt.event_id`；④ 插 `actor` 的 `controller`、`owner` 两行，以及种子里的执行者、席位和 5.1.2 的初始 `capability_fact`（都是状态表，都挂这条事件）；⑤ 提交，延期外键这时核对通过。之后的身份由 `controller` 或 `owner` 发的 `actor_registered` / `host_registered` 建；别的流第一次写入时由写事件的函数建。

```sql
CREATE TABLE agentrt.outbox (                          -- 事务性发件箱：PG → Redis
  outbox_id     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_id      bigint NOT NULL REFERENCES agentrt.event(event_id),
  topic         text   NOT NULL,       -- 'wake'、'mbox:<actor_id>'、'stop'、'cooldown'、'events'
  payload_json  jsonb  NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  delivered_at  timestamptz,
  tries         int NOT NULL DEFAULT 0,
  UNIQUE (event_id, topic)
);
CREATE INDEX outbox_pending_idx ON agentrt.outbox (outbox_id) WHERE delivered_at IS NULL;

CREATE TABLE agentrt.message (                         -- 信箱的事实（2.3 起用）
  message_id        text PRIMARY KEY,                  -- 'm_' + ULID
  from_actor_id     text NOT NULL REFERENCES agentrt.actor(actor_id),
  to_actor_id       text NOT NULL REFERENCES agentrt.actor(actor_id),   -- 可以是席位 'seat:chief_of_staff'
  mission_id        text REFERENCES agentrt.mission(mission_id),
  task_id           text REFERENCES agentrt.task(task_id),
  message_kind      text NOT NULL CHECK (message_kind IN ('ask','answer','help','handover','note','wake')),
  body_artifact_id  text NOT NULL REFERENCES agentrt.artifact(artifact_id),  -- 正文只当数据，不授权
  event_id          bigint NOT NULL REFERENCES agentrt.event(event_id),
  created_at        timestamptz NOT NULL DEFAULT now(),
  acked_at          timestamptz
);
CREATE INDEX message_unacked_idx ON agentrt.message (to_actor_id, created_at) WHERE acked_at IS NULL;

CREATE TABLE agentrt.artifact (                        -- 按内容寻址；新版本指向它取代的旧版本
  artifact_id            text PRIMARY KEY,             -- 'sha256:<hex>'
  artifact_kind          text NOT NULL CHECK (artifact_kind IN ('task_spec','mission_spec','report','verify','review',
                           'log_tail','checkpoint_patch','handover','brief','message','exam','other')),
  media_type             text NOT NULL,
  size_bytes             bigint NOT NULL CHECK (size_bytes <= 1048576),
  supersedes_artifact_id text REFERENCES agentrt.artifact(artifact_id),
  task_id                text, attempt_id text,         -- 不加外键：任务书先于任务存在
  created_by_actor_id    text NOT NULL REFERENCES agentrt.actor(actor_id),
  created_at             timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE agentrt.artifact_blob (
  artifact_id  text PRIMARY KEY REFERENCES agentrt.artifact(artifact_id),
  body         bytea NOT NULL
);

CREATE TABLE agentrt.verification (
  verification_id      text PRIMARY KEY,              -- 'v_' + ULID
  task_id              text NOT NULL REFERENCES agentrt.task(task_id),        -- 被验的任务
  attempt_id           text NOT NULL REFERENCES agentrt.attempt(attempt_id),  -- 被验的那次尝试
  method               text NOT NULL CHECK (method IN ('deterministic','review','gate')),
  check_ref            text,                           -- method='gate' 时是测试编号 'T19'
  env                  text CHECK (env IN ('dev','stg','prod')),
  verifier_attempt_id  text REFERENCES agentrt.attempt(attempt_id),   -- 谁验的（评审是另一次尝试）
  verdict              text NOT NULL CHECK (verdict IN ('pass','fail','none')),
  evidence_artifact_id text NOT NULL REFERENCES agentrt.artifact(artifact_id),
  subject_commit       text CHECK (subject_commit ~ '^[0-9a-f]{40}$'),
  deploy_ref_json      jsonb,                          -- gate：{"delivery_run":"…","images":{"<名>":"sha256:…"}}
  spec_sha256          text CHECK (spec_sha256 ~ '^[0-9a-f]{64}$'),   -- gate：跑的那份测试规格
  accepts_attempt      boolean NOT NULL DEFAULT false, -- 让任务进 accepted 的那一条
  created_at           timestamptz NOT NULL DEFAULT now(),
  CHECK (method <> 'gate' OR (subject_commit IS NOT NULL AND env IS NOT NULL
                              AND deploy_ref_json IS NOT NULL AND spec_sha256 IS NOT NULL))
);
CREATE UNIQUE INDEX verification_one_accept ON agentrt.verification (task_id) WHERE accepts_attempt;  -- 每个任务只验收一次尝试

CREATE TABLE agentrt.control (                         -- 叫停、暂停、排空；收紧谁都能设，解除只有 Owner
  control_id           text PRIMARY KEY,
  scope                text NOT NULL CHECK (scope IN ('global','mission','task','host')),
  scope_ref            text,
  control_kind         text NOT NULL CHECK (control_kind IN ('stop','pause','drain')),
  reason               text NOT NULL,
  set_by_actor_id      text NOT NULL REFERENCES agentrt.actor(actor_id),
  set_at               timestamptz NOT NULL DEFAULT now(),
  cleared_at           timestamptz,
  cleared_by_actor_id  text REFERENCES agentrt.actor(actor_id)
);
CREATE INDEX control_active_idx ON agentrt.control (scope, scope_ref) WHERE cleared_at IS NULL;

CREATE TABLE agentrt.idempotency_key (
  idempotency_key_id text PRIMARY KEY,                 -- '<actor_id>:<调用方给的键>'
  route              text NOT NULL,
  request_sha256     text NOT NULL,
  response_json      jsonb NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  expires_at         timestamptz NOT NULL
);

CREATE TABLE agentrt.rule (                            -- v4 §7.5 原样：只追加，放宽要签名
  rule_id text NOT NULL, rule_version int NOT NULL,
  body_json jsonb NOT NULL, body_text text NOT NULL,   -- body_text 是原文（有签名时签的就是它；无签名的收紧也有），执行从它解析；body_json 必须等于解析结果的规范 JSON（5.2）
  direction text NOT NULL CHECK (direction IN ('initial','loosen','tighten')),
  signed_by text, signature text,
  effective_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
  proposed_by_actor_id text, evidence_json jsonb NOT NULL DEFAULT '[]',
  PRIMARY KEY (rule_id, rule_version),
  CHECK (direction = 'tighten' OR signature IS NOT NULL)
);
-- rule_id 例：'standing-envelope:dev'、'concurrency'、'budget:dev'、'routing:dev'（取代 v4 的 routing_policy 表）、
-- 'job:implementer'、'capability-facts'、'visibility'。发版策略不在这里，仍在 cicd ConfigMap（修复链，ADR §12.3）
```

**能力与额度**（Owner 10-13 晚：先能力、后额度）：

```sql
CREATE TABLE agentrt.job (                             -- v4 §7.5
  job_id text PRIMARY KEY,                             -- 'chief_of_staff' 'planner' 'implementer' 'verifier' 'reviewer' 'curator' 'courier'
  tenant text NOT NULL CHECK (tenant IN ('dev','business')),
  rule_id text NOT NULL, rule_version int NOT NULL,    -- 说明书是 'job:<job_id>' 规则的某一版
  is_locked boolean NOT NULL DEFAULT false
);

CREATE TABLE agentrt.job_candidate (
  job_candidate_id   text PRIMARY KEY,                 -- 'implementer/exec:cursor/xai'
  job_id             text NOT NULL REFERENCES agentrt.job(job_id),
  executor_actor_id  text NOT NULL REFERENCES agentrt.actor(actor_id),
  model_provider     text NOT NULL,
  model_pattern      text NOT NULL DEFAULT '*',        -- 'grok-*'
  status             text NOT NULL CHECK (status IN ('qualifying','active','probation','demoted','retired')),
  rule_id            text, rule_version int,           -- 最近一次放宽它的签名规则
  qualified_at       timestamptz,
  exam_artifact_id   text REFERENCES agentrt.artifact(artifact_id),
  adapters_json      jsonb NOT NULL DEFAULT '[]',
  version            int NOT NULL DEFAULT 0,
  UNIQUE (job_id, executor_actor_id, model_provider, model_pattern)
);

CREATE TABLE agentrt.capability_fact (                 -- 硬约束：实测的或 Owner 定的；不靠印象
  capability_fact_id text PRIMARY KEY,                 -- 'codex-sandbox-no-listen'
  executor_actor_id  text NOT NULL REFERENCES agentrt.actor(actor_id),
  model_provider     text,                             -- 空 = 这个工具的所有模型
  fact_kind          text NOT NULL CHECK (fact_kind IN ('cannot','must_not','only','prefer')),
  subject            text NOT NULL,                    -- 'listen_port_tests'、'git_commit'、'fix_review_findings'、'author_core'、'review_core'
  scope_json         jsonb NOT NULL DEFAULT '{}',      -- {"job":"implementer","core":true}
  source_kind        text NOT NULL CHECK (source_kind IN ('measured','owner')),
  source             text NOT NULL,                    -- 出处（文件、日期）
  rule_id text, rule_version int,                      -- owner 类经签名规则进来
  recorded_at        timestamptz NOT NULL DEFAULT now(),
  retired_at         timestamptz
);

CREATE TABLE agentrt.capability_score (                -- 量出来的成绩；只追加，每次重算一行
  capability_score_id  text PRIMARY KEY,
  executor_actor_id    text NOT NULL REFERENCES agentrt.actor(actor_id),
  model_provider       text NOT NULL, model text NOT NULL, tool_version text NOT NULL,
  job_id               text NOT NULL REFERENCES agentrt.job(job_id),
  task_class           text NOT NULL, core boolean NOT NULL,
  source               text NOT NULL CHECK (source IN ('exam','benchmark','in_job')),
  window_start timestamptz NOT NULL, window_end timestamptz NOT NULL,
  attempts int NOT NULL, first_pass int NOT NULL, accepted int NOT NULL, rework int NOT NULL,
  review_misses int NOT NULL DEFAULT 0,               -- 评审放过、后来被发现的
  review_false_alarms int NOT NULL DEFAULT 0,
  median_wall_s int,
  score numeric NOT NULL,                             -- 一次通过率的 Wilson 下界（样本少自然偏低）
  computed_from_event_id bigint NOT NULL REFERENCES agentrt.event(event_id),
  computed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (executor_actor_id, model, tool_version, job_id, task_class, core, source, window_end)
);

CREATE TABLE agentrt.vendor_pool (                     -- 额度按「池」，不按厂商（WORK.md W-64）
  vendor_pool_id   text PRIMARY KEY,                   -- 'claude:max'、'cursor:own-models'、'cursor:other-models'、'cursor:grok-weekly'、'codex:plan'
  tool             text NOT NULL,
  window_kind      text NOT NULL CHECK (window_kind IN ('short','weekly','monthly')),
  resets_at        timestamptz,
  used_fraction    numeric CHECK (used_fraction BETWEEN 0 AND 1),
  measured_at      timestamptz,
  measure_source   text CHECK (measure_source IN ('reading','exit_text','owner')),
  cooldown_until   timestamptz,                        -- 被限流后的冷却；Redis 里有一份副本
  version          int NOT NULL DEFAULT 0
);

CREATE TABLE agentrt.budget_ledger (                   -- 只追加
  budget_ledger_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  attempt_id       text REFERENCES agentrt.attempt(attempt_id),
  vendor_pool_id   text REFERENCES agentrt.vendor_pool(vendor_pool_id),
  unit             text NOT NULL CHECK (unit IN ('wall_s','turns','tokens','usd','gpu_s')),
  amount           numeric NOT NULL,
  measured         boolean NOT NULL,                  -- 实测还是估的
  at               timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agentrt.schema_migration (
  schema_migration_id int PRIMARY KEY, sha256 text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now()
);
```

**能力怎么量、存在哪、何时更新、谁能改**：

| 问题 | 定法 |
|---|---|
| 怎么量 | 四个来源，按可信度：① 实测的硬约束（`capability_fact`，`measured`）；② 资格考试（每个岗位一组固定题，v4 §4、§5.3），结果是 `capability_score.source='exam'`；③ 基准题集（v4 §11 的回放题，修复前失败、修复后通过），`source='benchmark'`；④ 在岗成绩：控制器从验收事件算一次通过率、返工率、评审漏判（后来被发现的问题）和误判，`source='in_job'`。分数是一次通过率的 Wilson 下界，样本少时自动偏低。**不由 LLM 打分** |
| 存在哪 | 上面四张表：`job`、`job_candidate`、`capability_fact`、`capability_score`；路由的偏好和阈值在签名规则 `routing:dev` 里 |
| 何时更新 | 每次验收结论（`verification_recorded`）后，控制器增量重算受影响的那一行；主机注册时报的工具版本或模型变了，旧成绩标为旧版本、新版本先回到 `probation` 并排一次考试；每 90 天随规则集续签做一次可替换性演练（v4 §18） |
| 谁能改候选名单 | 放宽（加候选、`probation → active`、删一条 `cannot`）= 新一版签名规则 `job:<id>` 或 `capability-facts`，**只有 Owner 签**；收紧（降级、加 `cannot`）控制器按在岗考核自动做，或任何席位提出，立即生效、事后通知（v4 §3）。每次改动都是事件 |
| 分流顺序（2.2 先用固定候选快照加 ②–④ 的检查，七步全在 2.4 实现；复核 142 B5，见 5.2 交付物） | ① 岗位候选里 `active` / `probation` 的；② 去掉违反硬约束的（任务的 `needs_json` × `capability_fact`）；③ 独立性：评审的模型提供方 ≠ 作者的；作者不能验收自己；④ 规则：`core=true` 的作者只能是 Claude、评审是 Codex 只读；⑤ 能胜任：该岗位 × 任务类别的分数 ≥ 规则里的门槛（样本不足时 `probation` 只派非核心的活）；⑥ 在能胜任的里按额度挑：在冷却的池排除，剩下的按「已用比例 − 窗口已过比例」最小者优先（W-64 的口径：看节奏，不看百分比）；⑦ 平手轮换。结果写进 `task.route_json`，并记事件 `route_decided`（输入和每一步刷掉了谁），可解释、可回放 |

**初始数据**（都是实测或 Owner 定过的，随 2.1 的种子迁移写入；`owner` 类在 2.2 由 Owner 签进 `capability-facts` 规则后生效）：

| `capability_fact_id` | 内容 | 类别 | 出处 |
|---|---|---|---|
| `codex-sandbox-no-listen` | Codex 的沙箱跑不了要监听本机端口的测试 → 这类测试由 `agentd` 的确定性验收在沙箱外跑，不让 Codex 自验 | measured | `WORK.md` W-66「指派规矩再改一处（Owner 2026-10-12 13:24）」；第 1 轮 ⑥ 第二轮修复「它的沙箱跑不了测试」 |
| `codex-sandbox-no-commit` | Codex 的沙箱不能提交 → 提交和推分支由 `agentd` 做 | measured | `RUNTIME-PLACEMENT-2026-10-11.md` §10 第 1 行；同上 W-66 |
| `cursor-no-fix-review-findings` | 复核或验收查出的问题不退回 Cursor；Cursor 只做第一轮实现 | owner | W-66「指派规矩再改一处」（Owner 10-12） |
| `core-author-claude` | `core=true` 的任务作者只能是 Claude | owner | W-31「Owner 2026-10-13 23:16：分工」 |
| `core-review-codex-readonly` | `core=true` 的任务由 Codex 只读复核（`-s read-only` 或 `codex review`） | owner | 同上 |
| `review-other-provider` | 评审的模型提供方不能和作者相同；作者不验收自己 | owner | ADR §12.2 第 3 条、§12.5 |

#### 5.1.3 事件类型（闭合词表；每类正文字段在 Go 里闭合校验，多字段就拒）

| 组 | 事件 |
|---|---|
| 计划 | `plan_node_created`、`plan_node_retitled`（只许未开始的步骤）、`plan_node_state_changed`（from、to、cause：哪条原子满足了，或 `standing_lapsed`）、`plan_change_proposed`、`plan_change_decided`、`plan_changed`（经授权的变更落地：加步骤、绑审批或提问、改完成规则；cause 指向 `plan_change_decided`） |
| mission | `mission_proposed`、`mission_state_changed`、`mission_amended` |
| 任务 | `task_proposed`、`task_state_changed`、`task_dependency_added`、`task_cancelled`（级联的根）、`route_decided` |
| 尝试 | `attempt_leased`、`attempt_started`、`attempt_progress`（阶段、一句话；文本变了才记，最多每分钟一条。心跳本身不记事件，只改存活列，所以事件日志回放不出心跳时间）、`attempt_checkpointed`（`checkpoint_seq`，日志尾部和补丁的产物号，或「检查点过大，未持久化」）、`attempt_stale`、`attempt_renewed`、`attempt_computed`、`attempt_persisted`、`attempt_submitted`、`attempt_lost`、`attempt_ended`、`attempt_salvaged`（过期尝试保全进来的产物和提交；不改任务状态）、`attempt_cancelled`（采纳保全结果时，同一事务里取消这个任务还活着的新尝试；`reason`，`accepted_attempt` 是被采纳的那次 `lost` 尝试；迁移 0005，Owner 10-14 选 A，复核 152 A3） |
| 产物与验收 | `artifact_put`、`verification_recorded` |
| Owner 与外部事实 | `owner_wait_opened`、`owner_wait_closed`（关联审批 `#n` 或提问 `Qn`）、`approval_seen`、`question_seen`（正文带回答的选项、原文、回答者、时间：不可变的副本）、`ci_seen`、`pipeline_seen`、`deploy_seen`（某环境现在部署的提交和镜像摘要变了）（控制器读到外部记录的状态变化）、`owner_signoff`（带 `plan_node_id`） |
| 主机与身份 | `actor_registered`（建 `actor` 行：种子里的 `controller`、`owner`，以后加的执行者、席位）、`host_registered`、`host_state_changed`（`active → draining → retired`；在线 / 失联不是状态，按 `last_poll_at` 算，不记事件）、`host_retired` |
| 控制 | `control_set`、`control_cleared` |
| 规则 | `rule_proposed`、`rule_signed`、`rule_tightened`、`rule_expired` |
| 能力与额度 | `capability_scored`、`candidate_status_changed`、`budget_charged`、`pool_cooldown_set`、`pool_measured` |
| 信箱（2.3 起） | `message_posted`、`message_acked`、`policy_alert`（消息里冒充授权等） |
| 其他 | `note`、`wait_limit_passed`、`legacy_imported`（2.3 一次性导入记录器和 `WORK.md`） |

#### 5.1.4 `redis-agents`

| 项 | 定法 |
|---|---|
| 部署 | PROD：`bifrost-platform-prod/redis-agents`；STG：`bifrost-platform-stg/redis-agents`。1 副本，`appendonly yes`、`appendfsync everysec`，PVC 1 Gi（存储类跟现有 `redis-live-prod`，未核实是哪一个），`maxmemory 256mb`、`maxmemory-policy noeviction`（容量由 MAXLEN 控，不让 Redis 悄悄丢）；密码由 Owner 建 Secret；NetworkPolicy 只放行同命名空间里 `platform-api`、`platform-workers` 两个 Pod；不开 NodePort。**Agent 不直连**，只经 API / MCP 长轮询（v4 §2） |
| DEV | 用现有 `data/redis-dev`（局域网 30379，只 DEV），所有 key 加前缀 `agrt-dev:` |
| 谁是事实来源 | **PG 是唯一事实来源，也是领活和未读消息的唯一查询来源**。Redis 的流只提示「有变化」：长轮询等信号，醒来或超时（≤ 25 秒）都去 PG 查，所以信号丢了只多等一个周期。MAXLEN 裁剪只能丢信号，丢不了事实；Redis 整个丢了不丢任何事实 |
| 投递 | 事务性发件箱：事件和 `outbox` 同一事务写入；中继持 `agrt:relay:lock` 才干活，按 `outbox_id` 顺序取未投递的（`LISTEN agrt_outbox` 唤醒，另每 2 秒兜底轮询），`XADD` 后写 `delivered_at`。中继在两者之间崩了会重投，消费方按 `event_id` / `message_id` 去重（物理上可能两份，逻辑上只生效一次） |

Key 约定（PROD 前缀 `agrt:`，DEV `agrt-dev:`）：

| Key | 类型 | 内容 | 保留 | 重建来源（PG） |
|---|---|---|---|---|
| `agrt:wake` | Stream | `{kind:'task_ready', task_id, role, task_class}` | `MAXLEN ~ 10000` | `task WHERE state='ready'` |
| `agrt:mbox:<actor_id>` | Stream + 消费组 `g` | `{message_id, event_id, message_kind}`；接收方收到信号后按 PG 的未读列表取消息；ack 一律写 PG（`acked_at` + `message_acked`），`XACK` 只是清理 | `MAXLEN ~ 1000`（超出只丢信号，未读以 PG 为准）；已 ack 超 7 天的 `XTRIM MINID` | `message WHERE acked_at IS NULL ORDER BY created_at` |
| `agrt:stop` | Stream（广播） | `{control_id, scope, scope_ref, control_kind}` | `MAXLEN ~ 1000` | `control WHERE cleared_at IS NULL` |
| `agrt:events` | Stream | `{event_id, event_type, event_stream_id}`（2.5 的界面实时刷新用） | `MAXLEN ~ 50000` | 不重建（界面回退到按 `event_id` 增量读 PG） |
| `agrt:presence:<actor_id>` | String，`EX 90` | `{host_id, task_id, at}`；只用于交互线程和席位是否在线 | TTL | 不重建。缺了是「未观测到在线」，不是离线；下一次轮询补上。**主机在线与否只按 PG 的 `host.last_poll_at` 判** |
| `agrt:cooldown:<vendor_pool_id>` | String，TTL = 冷却剩余 | `{until, reason, event_id}` | TTL | `vendor_pool WHERE cooldown_until > now()` |
| `agrt:relay:lock` | String，`SET NX PX 30000`，值是隔离令牌 | 中继和重建共用的单实例锁。拿锁时 `INCR agrt:relay:fence` 得令牌；每 10 秒按值比较续期（Lua），续不上立刻停手；中继和重建的**每一个**写命令（`XADD`、`DEL`、`XGROUP`、冷却的 `SET`、写 `agrt:meta:epoch` / `agrt:meta:rebuilding`、删锁）都在 Lua 里先比对锁的值（复核 142 B6），旧持有者写不进去，复活后也删不掉新持有者的流、标志和锁 | TTL | — |
| `agrt:relay:fence` | String | 隔离令牌计数 | 永久 | 重建时不动 |
| `agrt:meta:epoch` | String | 本次重建的编号（PG 里生成） | 永久 | 重建时写 |

**Redis 丢了怎么重建**（存储包函数，2.1 交付；中继启动时，或发现 `agrt:meta:epoch` 不存在时；T15a、T15）：① 拿 `agrt:relay:lock`（和中继同一把，拿到就等于中继暂停）；② 写 `agrt:meta:rebuilding`，期间领活和信箱的长轮询直接读 PG；③ 从 PG 读快照，按上表的「重建来源」写：每个有未 ack 消息的接收方删旧流、按 `created_at` 顺序 `XADD`、`XGROUP CREATE … 0`；未解除的叫停进 `agrt:stop`；仍在冷却的池；每个 `ready` 任务一条唤醒；④ 写新的 `agrt:meta:epoch`、删 `rebuilding`；⑤ 放开中继，`outbox` 里未投递的照常投。重建期间新发的消息、新设的叫停都先进 `outbox`，⑤ 之后投；ack 写 PG，不会丢；同一条可能既在快照里又在 `outbox` 里，消费方去重。锁过期（重建卡住、没续上）：重建立刻停手，旧持有者的任何写命令都过不了令牌比对（上表），下一个持有者从 ① 重来。客户端看到 epoch 变了，就从 PG 重读一次。

#### 5.1.5 2.1 的验收

| 编号 | 种什么 / 做什么 | 过的标准 |
|---|---|---|
| T19 状态库就位 | DEV、STG、PROD 三库各跑一次迁移，再跑一次；同时起两个迁移；用每个身份连每个库；读 CNPG 的备份记录，并把 PROD 库从最近一次备份恢复到一个临时集群（演练后删）。另：空库启动，只跑迁移和种子，然后 mission → 计划节点 → 任务 → 尝试各在自己的事务里第一次建；再让一个事务的事件指向一个最后没建的任务（复核 142 R1） | 第二次无变化；种子不关触发器就成功，四次首建都过（事件先于对象插入）；指向没建对象的那个事务提交失败，事件、流头、发件箱全部回滚，流的 `seq` 不跳号；两个并发的迁移只有一个做事；`platform_agentrt_<env>` 能对状态表 DML（带事件），对 `event` 的 `UPDATE` / `DELETE`、任何 `CREATE` / `DROP` 被拒，不带 `agentrt.event_id` 直写状态表被拒（T25 的数据库一半）；`agent_reader` 只能 SELECT；STG、DEV 的身份连 PROD 库被拒；改动已执行迁移文件的一个字节，迁移失败；新库在备份里，恢复出来的表和行数对得上 |
| T20 断线续连 | 在 DEV 上用 `pg_terminate_backend` 杀掉 `platform_agentrt_dev` 自己的连接（同角色可以杀自己的会话），写事件的压测同时进行 | 10 秒内恢复写入；每条流的 `seq` 连续、无重复、哈希链完整。真正的 CNPG 切换演练影响 Trade 和 GS，不在第 2 轮做 |
| T21 `redis-agents` 本身 | 重启 Pod；从别的命名空间、从局域网连它 | 重启后流还在（AOF）；从别处连不上 |
| T15a 重建与中继（存储层，真 Redis） | 用存储包写一组事件、消息、叫停、冷却、就绪任务，`FLUSH` 该前缀，跑重建。另三种：一个信箱超过 MAXLEN；重建进行中发消息、ack、设叫停；重建中让锁过期 | 验的是经 PG 查到的事实和逻辑处理次数，不是 Redis 的物理内容（复核 142 R6）：接收方经 PG 得到的未读消息、领活看到的就绪任务、生效的叫停、冷却中的池和种下的逐项相等；按 `message_id` 去重后每条未 ack 的消息逻辑上只处理一次；超过 MAXLEN 的消息仍能从 PG 领到；重建中发的、ack 的、设的都没丢，ack 过的不再被处理（Redis 里可以留着它的陈旧信号，接收方查 PG 后忽略）；锁过期后旧持有者的写命令都被拒，新持有者重建后上面的事实照样成立。Redis 允许裁剪、重复和陈旧信号；只在一个静止、未裁剪、无并发的小夹具里把 Redis 快照和「重建来源」逐项比 |
| T23a 只追加 | 正常写入 1 万条后校验；用运行时角色和属主角色各对只追加的表做 `UPDATE` / `DELETE` | 校验全过；改动全部被拒 |
| T23b 篡改检测 | 在一次性的测试库里，测试夹具以超级用户关掉触发器、改一条事件的正文、再打开，跑校验 | 改过的那条被指出（流名、seq） |
| T32 计划关联与计数 | 把任务挂到 `item`、挂到别的 mission 的步骤；评审任务挂到和对象不同的步骤；依赖成环；`done_rule` 引用别一步的任务或没绑的审批；父子类型错。复核 142 R3 加三种：步骤挂了任务之后把它改绑到另一个 mission；`done_rule` 引用了某任务之后改这个任务的步骤；两个事务并发插 A→B、B→A。复核 143 加一种（两个先后都跑）：事务 A 把已挂 t1 的步骤 S 连同 t1 从 M1 迁到 M2、未提交，事务 B 同时新建 M1 的任务 t2 挂到 S。另按 5.1.2「计数」种一组步骤（含 `dropped`、`stopped`、`manual`，再给做完的项加一步） | 前八种都被拒收并写明原因（经 `plan_changed` 迁移的也在提交时被重验拒掉）；并发的两条依赖只有一条提交成功；迁移与新建交错时，A 先提交则 B 等锁后被拒，B 先提交则 A 提交时重验不合、整个迁移回滚，任何先后都不会留下 M1 的任务挂在 M2 的步骤下；计数和规则逐项相等 |
| T30 计划编号稳定 | 改 `plan_node_id` / `ordinal` / 父节点；删一个节点；给已做完的项加步骤；同一份计划经批量写入夹具写两次 | 前两种被拒；新步骤编号 = 兄弟里最大 + 1；写两次结果相同 |
| T31 发件箱原子 | 在 `XADD` 之后、写 `delivered_at` 之前杀掉中继 | 重启后那条重投一次，消费方去重后只生效一次；不存在有事件没发件箱、或有发件箱没事件的行 |

T30、T32 在 2.1 用存储包的通用批量写入夹具（一组行经写事件的同一个函数写入），不是 2.3 的 `WORK.md` / 记录器导入器；导入器的同样反例在 2.3 验（Gate B「T32（经导入）」，复核 142 R4）。

**依赖**：v5 确认；§7 第 1、2、6、8 条。**Owner 动手**：5.7 的 O1–O11。**粗估**：实现 4–5 天（中继和重建从 2.3 挪进来；含 Codex 复核两到三轮）+ 等 Owner 的环节；把握中（新依赖和三份集群清单都要他批，环节多）。

### 5.2 第 2.2 步：接口层与 `agentd`

**交付物**：内核 HTTP 路由、控制器循环、新的鉴权角色 `agentd`、MCP 工具、`agentd`（`deterministic`、`codex`、`cursor` 三个执行者，并发 1）、结果持久化（检查点、算完 / 落到平台 / 提交、保全、结束通知）、接管协议（§6.2）、完成规则求值（含持续条件）、签名规则的验签、提问加两个字段、血缘认 `Agentrt-Task`。**状态只能经接口按事件改**：没有任何「设置状态」的通用路由，每条写路由对应一种事件，由控制器在同一事务里改状态。分流在 2.2 只做最小版（复核 142 B5）：由 O19 签的初始规则生成一份固定的候选快照（每个岗位的候选及顺序），领活时查独立性和已签的硬约束（5.1.2「分流顺序」②–④）；按成绩和额度排序（⑤⑥）在 2.4。

路由草图（`/api/v1/agentrt/…`；STG 演练、PROD 为事实；本地 `bdev` 连 DEV 库）：

| 方法 路由 | 谁 | 事件 / 作用 |
|---|---|---|
| `GET /plan?root=R2`、`GET /plan/{plan_node_id}` | viewer | 计划树和每步的状态、出处事件；签过的步骤带 `signoffs`（2.5 补，见 §5.5） |
| `POST /plan/proposals` | reporter / seat / thread | `plan_change_proposed`；在常备授权内（给进行中的项加步骤、改未开始步骤的标题）自动 `plan_change_decided`，否则生成一条提问给 Owner |
| `POST /plan/{plan_node_id}/signoff` | 只 admin（Owner） | `owner_signoff`（2.5 补，Owner 2026-10-21；见 §5.5） |
| `POST /missions`、`GET /missions/{id}` | seat / thread 提议；viewer 读 | `mission_proposed`；落在 `standing-envelope` 内自动 `active` |
| `POST /missions/{id}/tasks` | seat / thread / 规划任务 | `task_proposed`（带任务书产物、`needs_json`、`core`） |
| `GET /tasks?mission=&state=`、`GET /tasks/{id}`、`GET /attempts/{id}` | viewer | — |
| `POST /claim` | `agentd` | 长轮询 ≤ 25 秒（同审批的 `maxWait`，`approvals/execution.go:32`）；正文 `{host_id, free_slots, tools, disk_free_bytes?, root_free_bytes?}`；按分流结果 `FOR UPDATE SKIP LOCKED` 取一条，`attempt_leased`；回 `attempt_id`、`lease_epoch`、任务书、`base_commit`、`pushed_ref`；顺带更新 `host.last_poll_at`。**剩余磁盘**（TD-415 第二层，Owner 2026-10-21「agentd 心跳带剩余磁盘，低于下限不派新活并告警，尝试结束后清工作目录」；领活就是主机的心跳）：`disk_free_bytes` 是主机根目录所在卷、`root_free_bytes` 是 `AGENTD_ROOT` 所在卷的可用字节，两个一起带（只带一个回 400，负数回 400）；任一低于下限（默认 15 GiB，平台环境变量 `AGENTRT_DISK_FLOOR_GIB` 可改）就不派活，同 `free_slots=0`，`last_poll_at` 照常更新；跌破时在 `host:<id>` 流记一条 `policy_alert`（`rule=disk_low`，产物写明观测时间、两卷剩余与下限），回到下限或以上记一条 note，每个方向只记一次。推手机由控制器做（循环 `agentrt-disk-pages`，每分钟）：7 天内还没推的记录逐条推，中转收下或没有目标（skipped）就在同一流记「已推」note，失败下一分钟重试，一直失败按控制器循环告警（复核 497 A4）。不带这两个字段（TD-415 之前的 `agentd`）不判 |
| `POST /attempts/{id}/heartbeat` | `agentd` | `{lease_epoch, phase, line}` → 续租（只改存活列，不记事件）；回 `{lease_expires_at, stop}` |
| `POST /attempts/{id}/checkpoint`、`/computed`、`/persist`、`/submit` | `agentd` | 依次记 `attempt_checkpointed`（`checkpoint_seq`、日志尾部和补丁的产物号）；`attempt_computed`（退出码、`end_how`、`conclusion`）；`attempt_persisted`（产物号、`pushed_ref`、`pushed_commit`：平台核对产物都在；推了分支的，再查 Gitea 上 `pushed_ref` 的头就是这个提交；都对才记）；`attempt_submitted`（控制器排确定性验收和评审）。都带幂等键：`checkpoint` 是 `attempt_id + checkpoint_seq`（每次采样一个新号，同一次采样的重试复用它；复核 142 R2）；`computed`、`persist` 是尝试 + 步骤；`submit` 按 `pushed_commit`，没推分支的按尝试。「做成了但回复丢了」重试得到同一结果（顺序见下「写入时的隔离检查」） |
| `POST /attempts/{id}/salvage` | `agentd` | 只收本主机的、已过宽限的尝试：它的产物和它自己分支上的提交 → `attempt_salvaged`。宽限还没过的回「尚在宽限内」，`agentd` 留在本地队列里重试（见下「心跳与死人开关」）。不改任务状态，自己不能让任务被验收：保全的结果要被采纳，只能由控制器另建一个新的验收任务，走正常的验收编排；`lost` 的尝试不会被直接标成 `accepted`，每个任务最多一次采纳（`verification_one_accept`）不变（复核 142 B2）。平台对保全做和 `persist` 同样的核对（产物在平台、Gitea 上本尝试分支的头等于交来的提交），核过就给这次尝试写 `persisted_at`——它说的是结果在哪，和租约无关，尝试的 `state` 仍是 `lost`；所以新验收任务的那条采纳记录指向这次 `lost` 的尝试，`accepts_attempt` 的触发器照常放行。采纳保全结果时，控制器在同一事务里取消这个任务还在跑的新尝试（统筹方补，修订 2 子代理留的缺口） |
| `POST /attempts/{id}/ended` | `agentd` | `attempt_ended`（`end_how`、进程组是否已清）：只收本主机的尝试，只登记「这次尝试在本机确已结束」这个事实。对已是终态（`lost`、`finished`、`cancelled`、`failed`）的尝试也收、不改它的状态；幂等键 = 尝试 + `ended`，重复报得到同一结果（复核 142 B2）。`external` 类的接管等的就是它（§6.2） |
| `PUT /artifacts/{sha256}`、`GET /artifacts/{id}` | `agentd` / reporter 写；viewer 读 | `artifact_put`；按内容寻址，重复上传无害（挂到尝试上要经上面的路由）；报告、交接这类产物里出现本机路径（H8 的规则）就拒收，日志尾部和补丁免扫 |
| `GET /events?stream=&after_seq=`、`GET /events/verify?stream=` | viewer | 读事件；校验哈希链 |
| `POST /controls`、`DELETE /controls/{id}` | 设：任何已认证身份；解除：admin | `control_set` / `control_cleared` |
| `POST /rules/{rule_id}/proposals`、`/sign`、`/tighten` | 提议：seat / thread；签：Owner 的签名正文；收紧：任何人 | `rule_*`；验签和执行见下「规则」 |
| `GET /hosts`、`POST /hosts/{id}/drain` | viewer / operator | — |
| `GET /progress` | viewer | 进展投影（计划、架构对照、现场、需要你），2.5 的 Console 读它 |
| `GET /whoami` | 任何 | 身份、岗位、能做什么 |

鉴权：新角色 `agentd`，令牌绑定一个 `host_id`（主体 `agentd:<host_id>`），只能领活、心跳、交结果、写产物，且正文里的 `host_id` 必须等于主体；够不着审批、发布、集群动作。

**写入时的隔离检查**：`heartbeat`、`checkpoint`、`computed`、`persist`、`submit` 按这个顺序处理（复核 142 B1、B3）：① 鉴别主体；② 带幂等键的路由先查键：命中已提交的操作（同键同摘要）就只读返回存下的原响应，不再查下面几件事（`submit` 成功、回复丢了，尝试已不在活着的状态，重试照样拿回原结果）；同键不同摘要回 409；③ 只有新操作才在**同一个事务**里先 `SELECT … FOR UPDATE` 锁住尝试行（要改任务的连同任务行）、读最新的行，再查四件事：尝试的 `host_id` 等于调用方主体的主机；尝试处在活着的状态（`leased` / `running` / `stale`）；`lease_epoch` 相等；拿到锁之后的数据库时间 `clock_timestamp()`（不用事务开始时的 `now()`）早于 `lease_expires_at` + 宽限。任何一件不成立回 409。不依赖租约循环先跑过（T22 ③、⑤）。

**规则**：签名正文是 `body_text`，签名覆盖 `rule_id`、`rule_version`、`direction`、`effective_at`、`expires_at`（写在正文头里，验签后解析出来和列值比，不等就拒）。用运行时自己的签名 namespace `bifrost-agentrt-rule`；`releasepolicy/sshsig.go:18-19` 的两个 namespace 不复用，发版策略的签名拿到这里无效；验签函数（`:30`）和信任锚复用。带签名的（`initial`、`loosen`，以及任何带签名的输入）平台验过签后**从 `body_text` 解析出规则来执行**；不带签名的收紧照样允许：`body_text` 经同一个闭合解析器解析、和上一版做结构比较证明是收紧后立即生效，也从解析结果执行（复核 142 B7）。两种情况下 `body_json` 都是派生的，必须等于解析结果的规范 JSON，不等就拒存。「收紧」不信调用方填的 `direction`：和上一版做结构比较（授权项只减不增、上限只降不升、有效期只缩不延），比较不过就按放宽处理、要签名。过期、正文有不认识的字段、信任锚为空，一律失败即关（回到更严的默认值）。v4 的三条规则测试照留（T35）。

MCP 工具（加在现有 `mcp/platform`）：`whoami`、`get_plan`、`get_mission`、`list_tasks`、`get_task`、`propose_mission`（10-15 补：原清单漏了，见 LESSONS 139）、`propose_tasks`、`propose_plan_change`、`put_artifact`、`get_artifact`、`post_decision_card`（即 `ask_owner` 加 `owner_duty`、`task_id`）、`request_stop`。

控制器（`platform-workers`）：

| 循环 | 做什么 |
|---|---|
| 租约 | 每 10 秒：过期的尝试 → `stale`；`stale` 超过宽限（15 分钟）→ `lost`，任务按 `effect_class` 处理（§6.2）。这个循环只改状态、发通知；挡住过期写入的是上面的同事务检查 |
| 任务挂步骤 | 按提议的上下文写 `plan_node_id`：在某一步下提的挂这一步；验收、评审继承对象任务；不在计划里的写 `off_plan` 和原因。LLM 可以提，和上下文不合的由存储包拒收 |
| 完成规则 | 每条事件后重算受影响步骤；历史事实成立一次就不再重验，持续条件在 `deploy_seen` 后重算，`GET /progress` 读时也现算（5.1.2） |
| 外部事实 | 每 15 秒读计划里引用的审批、提问、CI run，以及持续条件引用的环境现在部署的提交和镜像摘要（平台自己的交付记录），变了就记 `approval_seen` / `question_seen`（抄下回答）/ `ci_seen` / `deploy_seen` |
| 验收编排 | 实现提交后 → 建确定性验收任务；通过 → 按分流建评审任务（独立性在领活时再查一次）；评审过 → 写一条 `accepts_attempt` 的 `verification`（被验的尝试必须已落到平台）→ `accepted`；不过 → `rework`（`round_no+1 ≤ max_rounds`），否则 `blocked` 并提一条决策卡 |
| 发布前提 | 计划里 `release` 类步骤建审批单之前，程序检查三条前提（该提交 `ci-*` Succeeded；STG 跑的是同一提交且摘要核对通过；同仓库没有未结的发布单），缺一条不建单（今天是 LLM 手工查，§9 第 4 行） |

`agentd`（Go，`bifrost-platform/cmd/agentd`，launchd 常驻，不开端口）：

| 职责 | 定法 |
|---|---|
| 领活 | 长轮询 `/claim`；负载过高（1 分钟负载 > 核数，教训 105）时报 `free_slots=0`；每次带主机根目录和 `AGENTD_ROOT` 两卷的剩余磁盘（TD-415），读不出就不带。平台不认这两个字段（回 400 unknown field，TD-415 之前的平台）就立刻去掉重发，此后 10 分钟内不带，过后再试带（复核 497 A1）：混跑时照常领活，平台发版后自己恢复上报 |
| 本地登记 | 启动时 `flock` 一个全机锁，拿不到就退出：同一台主机只有一个 `agentd`。每个执行者在自己的进程组里起，先停在 `agentd` 自带的启动器里等管道上的放行字节；`{attempt_id, pgid, start}`（`start` 是组长的启动时间，防组号复用）fsync 进登记后才放行（R1）。`agentd` 死在这之间，管道一断启动器就退出，不留没登记的进程组。重启后第一次领活之前：登记里还活着的组（组号和启动时间都对上）先清掉，传最后一个检查点，经 `/ended` 报 `attempt_ended`（`end_how='daemon_restart'`），不续跑；已经算完的尝试接着传结果 |
| 工作区 | `~/agent-work/tasks/<task_id>/a<n>/`：按 `base_commit` 从 Gitea 全新克隆；治理层的符号链接指向钉版本的只读检出（3.1 的 H2 例外），让 preflight 照样生效；检出后工作树必须干净（H3） |
| 起执行者 | 参数数组、不经 shell；环境按允许清单重建（不传管理员 kubeconfig、admin / operator 令牌、业务键）；Claude 会话用 `--strict-mcp-config --mcp-config <只读配置>`，Codex、Cursor 用各自的等价配置，不让任务里的 Agent 拿到审批类 MCP 工具；macOS 上用 `caffeinate -i -w <pid>` 防空闲睡眠 |
| 心跳与死人开关 | 每 30 秒心跳，带执行者流式输出里的最后一句；连续 3 次失败或收到 409：TERM 进程组，10 秒后 KILL，记 `end_how=lease_lost`；之后只走保全（`/salvage`，§6.2），不再 `persist` / `submit`。宽限还没过时保全不发，先在本地排队，每 60 秒重试一次 `/salvage`，平台回「尚在宽限内」就接着排，过了宽限的第一次重试就收；进程组清掉后经 `/ended` 报结束（复核 142 B2） |
| 检查点 | 运行中每 5 分钟：日志尾部，以及工作树有变化时对 `base_commit` 的 `git diff`（未跟踪的文件也算），作为产物上传，`checkpoint` 登记。每次采样先在本地登记里记下新的 `checkpoint_seq`（上一号 + 1）再上传，重试同一次采样用同一个号；平台确认后登记里记下「最后确认的检查点」（复核 142 R2）。补丁超过 1 MiB 就只记「检查点过大，未持久化」 |
| 收尾 | 执行者退出 → `computed` → 只收列明的产物（报告、`verify.json`、日志尾部），做本机路径扫描，`PUT` 产物 → 有改动就推 `agent/<task_id>/a<n>` 分支（带尾注，见 §3）→ `persist` → `submit`。每步失败带同一个幂等键重试；`agentd` 重启后按登记从断点接着传（结果在本地，不重跑执行者）。结束报给平台、进程组确认没了以后结算；其中有证据说明结果已整份交到平台的（登记里的 `handed_over`：提交或保全被收下；接管时这次新采的最后一个检查点日志读到、日志尾和补丁都被收下、补丁不超大、尝试有仓库，并被确认；准备失败的报告和日志尾都被收下、检查点被确认）清空工作区（`a<n>/` 本身留着、为空，同一次尝试再来仍被拒，R2）、删掉 `a<n>.out/`，只认任务号和尝试号算出的那个目录、经 `os.Root` 删（复核 497 A2、A3，499 A-1）；清不掉的条目留作 `unswept`，按间隔重试、不重跑（B2）。没有这个证据的（有一部分被拒、没读到、太大，或重发的是旧检查点），工作区文件照旧保留，登记照常删去，不补传、以后也不再清；进程组没确认没了的尝试照旧整个保留（TD-415） |
| 执行者 | `deterministic`（任务书里的命令数组）；`codex`（`codex exec --json -C <root> -s workspace-write --output-schema <schema> -o <last.json>`）；`cursor`（`cursor-agent -p --output-format stream-json --trust --workspace <root> --model <规则指定>`）。旗标按 10-13 本机 `--help` |

**Gate A**（v4 原定 T01、T02、T08、T10，其余是 v5 加的）：

| 编号 | 做什么 | 过的标准 |
|---|---|---|
| T01 恢复 | 尝试进行中杀 `agentd`，launchd 拉起；`branch` 和 `external` 类各一次（`external` 用种下的任务，第 2 轮不真派） | 30 秒内登记里的进程组清空；尝试 `ended{daemon_restart}`；`branch` 任务回 `ready`，`external` 任务 `blocked` 并有决策卡；同一 `attempt` 没有第二次提交 |
| T02 租约 | 两个 `agentd`（不同主体）同时领同一批任务；拿旧隔离号心跳和提交 | 每个任务只被领一次；旧隔离号回 409 |
| T05 无证据的声明 | 报告写「测试全过」，没有 `verify.json` | 不进 `accepted` |
| T06 失败的实验 | 一次结论为 `failed` 的尝试 | 事件、产物都在；进展视图看得到；不被后来的成功覆盖 |
| T08 独立验收 | 作者的提供方去领它的评审；作者去领自己的验收 | 都被拒（409），`route_decided` 里写明原因 |
| T10 预算 | mission 的尝试数或墙钟用完 | 不再派活；账本和尝试一一对上 |
| T22 Agent 主机掉线与接管 | ① 尝试进行中让 `agentd` 停 5 分钟（`SIGSTOP`）；另一次合盖 20 分钟。② 只停 `agentd`、子进程照跑，越过宽限，再在同一台主机上起第二个 `agentd`，最后放开第一个。③ 暂停控制器（租约循环不跑）越过过期加宽限，再来一次续租。④ 推分支和过期同时发生。⑤ 一次心跳在截止前进入事务，夹具让另一个事务先锁住这条尝试行、到截止之后才放（复核 142 B3） | ① 120 秒后 `stale`，宽限内恢复则 `attempt_renewed` 接着跑；超过宽限则 `lost`、任务按 `effect_class` 处理；醒来的旧 `agentd` 被 409 挡住、30 秒内清掉进程组。② 第二个 `agentd` 拿不到全机锁、不领活；子进程（按约定推自己的分支）晚到的推送落在它自己的分支上，结局是 `attempt_salvaged`；越权推别的尝试的分支不在第 2 轮的保证内（§7 第 7 条 ②）。③ 续租被拒（按数据库时间判，不等循环）。④ 提交落在本尝试的分支上，任务状态不受影响。⑤ 被拒：截止按拿到锁之后的 `clock_timestamp()` 判 |
| T25 状态只由事件改 | 对每条写路由做模糊测试；用运行时角色直接 SQL 写状态表：不带 `agentrt.event_id`、带别的事务的事件、带键对不上的事件、只改存活列、存活列和别的列一起改 | 每次状态变化都有一条带原因的事件；没有路由能把任务或计划步骤设成任意状态；直写只放行「只改存活列」一种 |
| T32（经接口） | 把 T32 的反例（含复核 142 R3 加的三种）经新增任务、改计划两条路由各提交一遍，其中一条是参谋长席位提议的任务挂到别的 mission 的步骤。导入入口 2.3 才有，导入的反例在 Gate B「T32（经导入）」（复核 142 R4） | 都被拒（并发的两条依赖只有一条成功），错误写明违反的是哪一条约束，不留半条记录；复核 141 A3 要的接口层覆盖 |
| T33 证据绑定版本 | 旧提交的 `gate` PASS 留着，环境换成新部署；另一次让交付记录读不出来；再一次用一份含 T19、T20 两个测试编号的规格，只让 T19 过（复核 142 B4） | 旧 PASS 不满足新部署，那一行架构对照不打勾；读不出来时是 `unknown`，不是做完；T19 的 PASS 不让引用 T20 的原子成立 |
| T34 结果持久化 | 八种：上传中途断网；上传成功但回复丢了；推送成功但 `submit` 丢了；上传中途重启 `agentd`；主机永久丢失（删掉本机工作区和登记，不再回来）；连续三个内容不同的检查点，第二个的回复丢了（复核 142 R2）；`submit` 成功、回复丢了，尝试已不在活着的状态时重试（复核 142 B1）；过宽限的旧尝试保全成功，而新尝试还在跑（统筹方补） | 前四种重试后产物、`attempt_persisted`、`attempt_submitted` 各只有一份，任务能被验收；第五种只剩最后一个平台确认的检查点，Progress 显示「结果未持久化」、那个检查点的时间和已多久没有持久化，不显示做完，任务按 `effect_class` 处理；第六种三个检查点各登记一份（`checkpoint_seq` 1、2、3），第二个的重试拿回原响应，第三个不被当成重试；第七种拿回第一次存下的响应，不回 409；第八种保全核过后那次 `lost` 尝试有 `persisted_at`、`state` 仍是 `lost`，控制器建的新验收任务通过后采纳记录指向它，同一事务里新尝试被取消，这个任务只有一条采纳 |
| T35 规则集 | v4 的三条（放宽没签名被拒；收紧立即生效；过期回到默认值）；另：`body_json` 和原文解析结果不等；标成 `tighten` 实际是放宽；用发版策略 namespace 签的；正文有不认识的字段；信任锚为空 | v4 三条照旧；其余全部被拒或失败即关 |
| T36 血缘尾注 | `agentd` 推一个提交 | 提交带 `Agentrt-Task`、`Change-Id`、`Work`；`/api/v1/lineage` 返回它的任务号，血缘页能从提交点到任务 |
| 基准 | 6 道回放题（Go 2、Python 2、TS 1、shell 1），Cursor 写、Codex 复核（或反过来，按 `capability_fact`） | 全部走完「领 → 做 → 确定性验收 → 评审 → 结论」，中途没人插手；结果（通过与否）记进 `capability_score` |

**依赖**：2.1 做完；§7 第 3、5、7 条。**Owner 动手**：5.7 的 O12–O20。**粗估**：8–11 天（复核 141 的 A1、A2 加了结果持久化和接管，以及 T22 的演练、T34 的八种故障）；把握低（内核加守护进程加两个执行者，按第 1 轮难线一片要 3–6 轮的历史）。**第 2 轮最可能超期的一步**：状态机、鉴权、租约与接管、结果持久化、证据求值、两家适配器和 Gate A 都集中在这里，T22、T34 的故障演练失败一次就要多一轮。

### 5.3 第 2.3 步：总线与叫停；本机文件迁进平台

**交付物**：把 2.1 的中继和重建接进 `platform-workers`（只接线）；信箱、唤醒、在线、叫停广播的 API 与 MCP 长轮询（`wait_for_messages`、`ack_messages`、`ask`、`request_help`、`handover`、`search_artifacts`）；等待计时由控制器做（`RULE-waits` 总则第 4 条）；隔离、根目录只读、注入防护；本机文件导入。

（Owner 2026-10-21 13:2x「2.3 的四条都照推荐 A」，`CUT-round2-2.3-rest-2026-10-21.md` §3）**在线**：第 2 轮只做主机在线（按 `host.last_poll_at`），**交互线程和席位的 presence（5.1.4 的 `agrt:presence:<actor_id>`）第 2 轮不做**：线程存活看平台已有的线程心跳（`agentthreads`，T26 就读它），席位第 2 轮是任务形态、不常驻（§1 第 8 行）；presence 随第 3 轮常驻席位做。`ask`、`request_help`、`handover` 由一个 `send_message`（`kind` 取 ask / help / handover / note / answer）承担，`handover` 的产物是 `put_artifact`（kind `handover`）；`search_artifacts` 是只回元数据的 `GET /api/v1/agentrt/artifacts`。

| 本机文件 | 怎么迁 |
|---|---|
| `WORK.md`「第 2 轮逐项」「架构对照」（「第 1 轮逐项」**不导入**，留在 `WORK.md` 作历史：全部做完、没有在跑的活挂在上面。Owner 2026-10-21 13:2x，`CUT-round2-2.3-rest` §3 第 3 条 A） | 一次性导入成 `plan_node`（`legacy_imported`），编号按表里的项号和行序，`W-n` 写进 `work_id`；「架构对照」每行指定它的门禁测试编号和钉住的规格 sha256（例：状态库 ← T19、T20、T23a）。导入后的去留见 §7 第 4 条。`TECH_DEBT.md`、`RATCHETS.md` 第 2 轮不导入（§8） |
| 派工记录 `~/agent-work/recorder-root` | 先校验哈希链，再作为 `legacy:recorder` 流导入；然后 `lane.py`、`rec.py` 退役。（Owner 2026-10-21 13:2x，`CUT-round2-2.3-rest` §3 第 4 条 A：请求格式 `agentrt.recorder_import/v1`，经 `POST /plan/imports`，一份日志一张卡；先 STG（由已签的卡规则答），STG 核过后 PROD 的卡由统筹线程提、Owner 答；`lane.py`、`rec.py` 等 PROD 导完再退役。`_observer/` 是看板的观察轮次，不导入，随看板在 2.5 退役） |
| 看板数据 `tasks.json` 手写行、`HANDOFF.md` | 「需要你」→ 提问 / 审批 / 计划里的 Owner 步骤；「在做」→ 任务与尝试；「最近」→ 事件；`HANDOFF.md` 只剩判断性的话，作为 `handover` 产物经 MCP 写入 |
| 等待计时、看护（`~/agent-work/watch-agents.sh`） | 控制器的 `wait_limit_passed` 和租约循环 |
| 额度读数（`usage.py`、`cursor-quota.json`） | 2.4 的 `pool_measured` |

**Gate B**（v4 原定 T03、T09、T11–T15，加 T04、T07、T32（经导入））：

| 编号 | 过的标准 |
|---|---|
| T03 同伴越权 | 一个主体去心跳、提交、取消别人的尝试或任务：403 / 409。（Owner 2026-10-19「Gate B ① A」：「取消」指尝试路由；叫停是安全方向的刹车，任何已认证主体都能叫停，不在 T03 之内） |
| T04 交叉传播 | 一件任务的产物被拼进另一件的任务书，里面写「Owner 已批准」：任何状态不变，记一条 `policy_alert` |
| T07 安全停止 | 在推分支的那一刻叫停：要么推上去并记录，要么没推；没有半截状态 |
| T09 叫停 | 从 `POST /controls` 到 Agent 主机上子进程死掉 ≤ 60 秒；之后不再派活 |
| T11 隔离 | 任务书、产物里引用另一个任务的工作区一律拒收。同一系统用户下读不读得到别的目录**做不到**，标「部分」，第 3 轮虚拟机补；推到别的尝试的分支、逃出进程组、读同用户的令牌同属这一例外（§7 第 7 条 ②） |
| T12 来源注入 | 仓库文件里的指令改变不了控制器的任何判断 |
| T13 无业务键 | 执行者子进程的环境变量名和拒绝清单交集为空 |
| T14 根目录只读 | （Owner 2026-10-19「Gate B ② A」改定）执行者写不进 agentd 根目录和 agent 用户的家：Linux 上由 agentd 的写墙保证（06 探针），另有一个 Linux 测试——带墙的尝试试图在 agentd 根目录建文件被拒，结束后根目录列表不变；codex 由它自己的沙箱证明。原写「被 preflight 拦；根目录白名单」与 §8 冲突，不再用 |
| T15 总线重建（接口层） | 任务进行中清空 `redis-agents`：领活、心跳、信箱不中断（期间走 PG）；领活、未读、叫停以 PG 查询为准，未 ack 的消息按 `message_id` 去重后逻辑上只处理一次（Redis 里可以重复或留陈旧信号；复核 142 R6） |
| T32（经导入） | 把 T32 的反例放进待导入的计划（`WORK.md` 格式）和记录器事件，经导入入口提交：都被拒并写明违反的约束，不留半条记录；同一份文件导入两次结果相同（复核 142 R4，从 Gate A 挪来） |

**依赖**：2.2；§7 第 4 条。**Owner 动手**：5.7 的 O21–O22。**粗估**：3–5 天（中继和重建挪到了 2.1）；把握中低。

### 5.4 第 2.4 步：多厂商、按能力和额度分流、参谋长

**交付物**：`claude` 执行者（`claude -p --output-format stream-json --json-schema …`，在任务工作区根起会话，让工作区钩子加载）；分流按 5.1.2 的七步实现；额度读数（各家没有可编程读数时用限流退出文本和 Owner 的读数，标 `measure_source`）；并发 2–3（按主机容量和负载）；参谋长席位（控制器在早晚、Owner 说话、出现阻塞时生成 `brief` / `plan` 任务；初版资格考试按 v4 §5.3 五题）；`job`、`job_candidate` 的写入方（2.2 的首批候选由 O19 的签名规则种下）；20 道基准题全集跑一遍，作为三家的初始成绩。

**验收**：T16 级联（评审不过 → 按 `route_json` 换下一位候选，且新候选仍满足硬约束和独立性）；T27 两层身份（同一工具换不同提供方的模型，独立性按提供方判）；参谋长考试五题；以及第 2 轮的终点：

**T26：一件活从派出到验收，全程没有统筹线程手工插手**

| 项 | 定法 |
|---|---|
| 输入 | Owner 经已交付的 API / MCP 用一句话给目标（信箱的 `ask` 进参谋长席位；Console 的入口 2.5 才有，届时再验同一个入口）；mission 里 4 件活：基准题里 Go、Python、TS 各一道，再加一件第 2 轮自身的外围小活（例如一段测试样板）。其中一件在第一次确定性验收时由测试开关注入失败（只在 STG 有效），逼出一次返工 |
| 故障注入 | 某一次尝试进行中，Agent 主机合盖 ≥ 15 分钟 |
| 观察窗口 | 从 `mission_proposed` 到最后一件 `accepted` |
| 过的标准 | ① 窗口内统筹线程**没有回合**：`agentthreads` 里统筹线程 id 没有 `turn_start`（线程心跳在 PROD，可直接读）；② PROD 审计日志和事件里，窗口内对这个 mission 的写入全部来自 `controller`、`host:*`、`exec:*`、`seat:chief_of_staff`、`owner`，统筹线程的令牌写入数为 0；③ 4 件全部 `accepted`，其中一件经过一次 `rework`；④ 每次评审的模型提供方 ≠ 作者的，核心类作者是 Claude；⑤ 每 5 分钟一次的探针对比 `GET /progress` 和库里的真实状态，零次不一致，合盖期间那件显示「宿主失联」而不是「在做」；⑥ 截止时间（8 小时）内完成。Owner 在窗口内只做事先列明的动作（给目标、回答事先登记的决策卡） |
| 不过 | 任一条不成立；按停线规矩分「会答错」和「只缺测试」 |
| 修订（Owner 10-19 22:3x） | ① 改为：**窗口里统筹线程对这个 mission 零写入，mission 没有等过统筹线程**（窗口里 Owner 自己在统筹线程发消息、用 `!` 跑命令开的回合不算插手）。另：④ 只验评审提供方 ≠ 作者（10-19 02:1x）；返工出现就必须收下、没自然出现不算不过（10-18 21:5x）；故障注入为停 06 的 PROD agentd（第二次 4 分 42 秒，Owner 定算数）。**结果：PROD M-12（10-19 21:37–22:11）过，T26 收线**；报告 `REPORT-T26-2026-10-19.md` |

**依赖**：2.3。**Owner 动手**：5.7 的 O23–O25。**粗估**：4–6 天；把握低（额度读数和参谋长考试都是第一次做）。

### 5.5 第 2.5 步：界面——Progress 页完全由接口生成

**交付物**：PROD Console 的 Progress 页改读 `GET /api/v1/agentrt/progress`（可选订阅 `agrt:events` 做实时刷新）：计划栏（轮 → 项 → 步、编号、做完几步、谁在做）、架构对照（每行的勾由门禁测试结果算）、现场（尝试、主机、慢或卡，规则见 v4 §20.2、§20.3）、需要你（提问、审批、计划里的 Owner 步骤，挂在所属那一步上）。本机看板退役（`board2.py`、`roadmap.py`、`index.html`、`publish-result.js`）；`PUT /api/v1/agent/progress` 和主机心跳路由并排一周后删除。这一步是外围，可交 Codex 或 Cursor 按已定接口写，Claude 验收。

**验收 T24（Progress 不依赖 Agent 主机）**：停掉 Agent 主机上的看板程序和 `agentd`（或合盖）后：PROD Progress 页的计划和架构对照与 `GET /plan` 一致；那台主机 3–4 分钟内显示「宿主失联」，它上面的尝试不显示「在做」；不出现「过期的旧文档当现状」。另照 v4 §20.5 的十个场景各跑一遍（挂起变「可能卡住」、慢但持续上报不叫 Owner、断开数据库显示「未知」、预计时间顺延与「估不准」、演练项没有批准入口等）；「结果未持久化」「计划外」「人工」三种标记各种一例。另验 T26 的目标入口：在 Console 上给目标，和 2.4 经 API / MCP 给的进同一个信箱、产生同样的事件。

**依赖**：2.2（接口）、2.3（导入）。**Owner 动手**：5.7 的 O26–O28。**粗估**：2–4 天；把握中。

**2.5 补的两处公开接口（Owner 2026-10-21「缺口 1、2 照推荐加」；T24 场景 8、9 要）**：
- `GET /progress` 加 `owner_next`：下一次需要 Owner 的是哪件事、哪一步、预计几点，跨事依赖取晚的；估不出就 `unknown` 写原因。形状和规则见 `SPEC-agentrt-progress-2026-10-14.md` 第 4 版 §2.7。Console 在 For you 的 Yours 卡里显示。
- 审批单加 `drill`（演练）：`POST /api/v1/approvals` 收 `"drill": true`，所有读方带 `drill`（为假时不出现）；演练单不问发版策略的自动批，批准路由在任何渠道都回 409 `a drill cannot be approved`，所以永远不执行；驳回照常可以关掉它，过期照常；通知写「Drill · #n」「A drill: nothing runs, and it cannot be approved.」，优先级 3，不发提醒。MCP `request_action` 收 `drill`。Console「需要你」把待批的演练单单列一组「Drills」，不计入任何计数；审批页写明是演练、没有 Approve 按钮。审批单存在 statefile，没有迁移，不是 PROD DDL。
- 另两处只改 Console、不改接口：待批项显示它是计划里哪一步（按步骤完成规则里的 `approval_executed` 反查，场景 10）；断库时说最后一次读到是几点（场景 5，交 PROD 运行时 M-33 做）。

**2.5 补的第三处公开接口：Owner 签收这一步**（Owner 2026-10-21「加一个只给我用的「签收这一步」路由和 Console 按钮，记一条 TD；2.4-1 考试那步也先用签收」）。完成规则里的 `owner_signoff` 原子此前没有任何路由、工具或按钮能写，写成签收的步骤永远打不上勾。
- **路由**：`POST /api/v1/agentrt/plan/{plan_node_id}/signoff`，正文 `{"ref": "…"}`。规则只等一个签收时 `ref` 可省，等多个时必须写；多出的字段回 400。写一条 `owner_signoff` 事件：落在这一步所属轮的计划流上，`plan_node_id` 是这一步，正文 `{ref}`，`actor` 是 `owner`。路由不自己求值，控制器下一遍完成规则把这一步推成 `done`（同其他事实）。
- **只给 Owner**：新能力 `signoff`，只有 admin 角色。Agent 持有的令牌（viewer、reporter、operator、seat、`agentd`）在路由前就被拒：平台的角色中间件对没有令牌和角色不对一律回 401 `admin token required`（复核 485 B1）。存储层再查一遍写入人必须是 `owner`，否则 403 `not_owner`。不加给 Agent 用的 MCP 写工具；`get_plan` 读得到 `signoffs`（只读）。admin 令牌是 Owner 的，接受的风险与审批相同（ADR §5：`preflight.js` 拦 Agent 读它）。
- **应答**：200 `{plan_node_id, ref, by, at, event_id, already_signed}`。重复签回 `already_signed: true`，带第一次的 `event_id`、`at`、`by`，什么都不写。
- **锁**（复核 485 A1）：读这一步时先锁住它的行（`FOR UPDATE`），一直持有到提交，再查规则、已签记录和状态，最后写事件。
  - 同时按两次会排队，只记一条（`TestSignOffStepOnceAtATime`）。
  - 计划变更、drop、控制器求值都是先锁步骤行、再写计划流，签收用同一顺序，不会互等成环。
  - 签收不会落在步骤已关或规则已换之后（`TestSignOffStepAndAChangeAtOnce`：drop、改规则、控制器求值三种交错）。
- **拒绝**：没有这个节点 404；不是步骤、规则里没有 `owner_signoff`、`ref` 不是规则里的、等多个却没写 `ref`，都回 422 并写明原因（列出规则等的 `ref`）；这一步已是 `done`、`stopped`、`dropped`（签了也推不动）回 409 `state`。已签过的不管状态，都按重复签回答。
- **读**：`GET /plan?root=`、`GET /plan/{id}` 的节点有签收时多一个键 `signoffs: [{ref, by, at, event_id}]`，从旧到新；没有签收的节点没有这个键。
- **Console**：计划页（`#work?section=plan`）里，规则等签收的步骤下面，已签的写「Signed off <ref> by the Owner, <UTC 到分>」。没签的 `ref` 在这一步还能推动时（不是 `done`、`stopped`、`dropped`）各有一个「Sign off」按钮：只有 Owner 登录（admin，判断同批审批单）才可点，否则写明原因；点了先确认一次；发出后显示平台记下的谁、几点，再重读计划；失败写平台给的原因（应答里的 `message`：什么状态、规则等哪些 ref；含登录令牌就整句隐藏，复核 485 A2），并说明再按一次是安全的。按钮高 44 px，手机上能点。
- **库**：`owner_signoff` 事件类型和 `(plan_node_id, event_id)` 索引早就有，没有迁移，不是 PROD DDL。
- **测试**：`agentrtapi` `TestOwnerSignsAStepOff`（各种令牌被拒、Owner 签、重复签幂等、八个并发只记一条、各种拒绝、签完控制器推成 `done`、`GET /plan` 的 `signoffs`；写 Console 夹具 `agentrt-plan-signoffs.testdb.json`）；`store` `TestSignOffStepOnceAtATime`、`TestSignOffStepAndAChangeAtOnce`、`TestSignOffStepIsTheOwners`；Console `stepSignoffs.test.tsx`（按钮出现和消失的条件、确认、签完的显示、非 Owner 不可点、失败）。

### 5.6 测试编号

| 编号 | 名称 | 在哪一步 |
|---|---|---|
| T01–T12 | 研报原有（恢复、租约、同伴越权、交叉传播、无证据的声明、失败的实验、安全停止、独立验收、叫停、预算、隔离、来源注入） | T01、T02、T05、T06、T08、T10 → 2.2；T03、T04、T07、T09、T11、T12 → 2.3 |
| T13–T15 | 无业务键、根目录只读、总线重建 | 2.3（T15 的存储层部分 T15a 在 2.1，含中继锁和 MAXLEN） |
| T16 | 级联 | 2.4 |
| T17、T18 | GPU 唤醒、租户硬规则 | 第 2 轮不做 |
| T19 | 状态库就位 | 2.1 |
| T20 | 断线续连 | 2.1 |
| T21 | `redis-agents` 本身 | 2.1 |
| T22 | Agent 主机掉线与接管 | 2.2 |
| T23a、T23b | 只追加；篡改检测 | 2.1 |
| T24 | Progress 不依赖 Agent 主机 | 2.5 |
| T25 | 状态只由事件改（数据库保证；直写那一半在 T19 先跑） | 2.2 |
| T26 | 全程无统筹插手 | 2.4 |
| T27 | 工具 × 模型两层身份 | 2.4 |
| T28 | 换主机（第 3 轮的入口条件，见 §6.3） | 第 3 轮 |
| T30 | 计划编号稳定 | 2.1（批量写入夹具）；导入两次在 2.3 |
| T31 | 发件箱原子 | 2.1 |
| T32 | 计划关联与计数 | 2.1（存储层，批量写入夹具）；经接口 2.2；经导入 2.3 |
| T33 | 证据绑定版本 | 2.2 |
| T34 | 结果持久化 | 2.2 |
| T35 | 规则集（含 v4 的三条） | 2.2 |
| T36 | 血缘尾注 | 2.2 |

（T29 留空，避免和 `DESIGN-host-minimal` 的 A 编号混。）

### 5.7 汇总：粗估与 Owner 的依赖清单

计数单位：一行 = Owner 的一个决定、一次批准（一张审批单，或线程里一次点头），或一次亲手操作（在他的终端或管理页上一次做完的一组动作）。§7 的 8 个决定可以在确认 v5 时一次回完，这里按它挡住的那一步排。

| # | 步 | 动作 | 类 | 挡住什么 |
|---|---|---|---|---|
| O1 | 2.1 | 定 §7 第 1 条（状态库、环境、角色） | 决定 | 2.1 全部 |
| O2 | 2.1 | 定 §7 第 2 条（pgx、迁移器、CI sidecar） | 决定 | 2.1 全部 |
| O3 | 2.1 | 定 §7 第 6 条（数据模型与运行时接口） | 决定 | 2.1 全部 |
| O4 | 2.1 | 定 §7 第 8 条（ADR 修订与编号） | 决定 | 2.1 全部 |
| O5 | 2.1 | 建 8 个 Secret（6 个库角色、2 个 `redis-agents` 密码） | 亲手 | O6、O7 |
| O6 | 2.1 | 批三个库的 `Database` 清单（`k8s/data/databases.yaml`）和建六个角色的 db-step（PROD 那一步是 PROD DDL，D 级）；同一改动带角色矩阵和逻辑备份目标（5.1.1） | 批准 | T19 |
| O7 | 2.1 | 批 `redis-agents` 两套清单（平台 overlay 推 main 即被 Argo 同步到 PROD，推之前要他点头） | 批准 | T21 |
| O8 | 2.1 | 同意拉 `postgres`、`redis` 两个钉摘要的镜像（下载） | 批准 | CI 上的存储包测试 |
| O9 | 2.1 | 应用平台 CI 流水线定义（加 sidecar） | 亲手 | 同上 |
| O10 | 2.1 | 批 PROD 迁移作业（新增表 = PROD DDL；正式 DDL 随单给他） | 批准 | T19 的 PROD 部分 |
| O11 | 2.1 | 批恢复演练（PROD 库的备份恢复到临时集群，演练后删） | 批准 | T19 的备份部分 |
| O12 | 2.2 | 定 §7 第 3 条（决策卡） | 决定 | 提问加字段 |
| O13 | 2.2 | 定 §7 第 5 条（`agentd` 身份） | 决定 | 鉴权角色 |
| O14 | 2.2 | 定 §7 第 7 条（结果持久化与尝试隔离两个例外） | 决定 | `agentd` 收尾 |
| O15 | 2.2 | 生成 Agent 主机的 `agentd` 令牌 | 亲手 | 领活 |
| O16 | 2.2 | 在 Gitea 建 `agentd-<host>` 用户，配分支和标签保护（Gitea 管理员） | 亲手 | 推分支 |
| O17 | 2.2 | 同意在 Agent 主机装 `agentd` 的 LaunchAgent（常驻配置） | 批准 | Gate A |
| O18 | 2.2 | 生成规则签名私钥（和发版策略卡在同一处：`WORK.md` S0-8） | 亲手 | O19 |
| O19 | 2.2 | 签初始规则（常备授权、并发 1、预算、`routing:dev`、`capability-facts`、各岗位说明书和首批候选名单，2.2 的固定候选快照由它生成） | 亲手 | Gate A |
| O20 | 2.2 | 批 PROD 发布单 | 批准 | 2.2 做完 |
| O21 | 2.3 | 定 §7 第 4 条（markdown） | 决定 | 导入 |
| O22 | 2.3 | 批 PROD 发布单 | 批准 | 2.3 做完 |
| O23 | 2.4 | 签岗位与候选名单（首批之外的）、`routing:dev` 门槛（放宽） | 亲手 | 分流 |
| O24 | 2.4 | T26 窗口里给目标、回答事先登记的决策卡 | 亲手 | T26 |
| O25 | 2.4 | 批 PROD 发布单 | 批准 | 2.4 做完 |
| O26 | 2.5 | 同意删两条路由（改公开接口） | 批准 | 本机看板退役 |
| O27 | 2.5 | 批 PROD 发布单 | 批准 | 2.5 做完 |
| O28 | 2.5 | 按他的四个问题走查（ADR §12.2 第 16 条） | 亲手 | 第 2 轮收尾 |

合计 28 行：决定 8、批准 11、亲手 9。

| 步 | 粗估（有效工作日） | 把握 | Owner 行 |
|---|---|---|---|
| 2.1 数据层 | 4–5 | 中 | O1–O11 |
| 2.2 接口层与 `agentd` | 8–11 | 低，**最可能超期** | O12–O20 |
| 2.3 总线与迁移 | 3–5 | 中低 | O21–O22 |
| 2.4 多厂商与参谋长 | 4–6 | 低 | O23–O25 |
| 2.5 界面 | 2–4 | 中 | O26–O28 |
| 合计 | 21–31（约 4–6 周） | 低 | 28 |

**4–6 周只是有效工作量**：不含等 Owner 决定和批准的时间，也不含恢复演练（T19 的恢复、T22、T34）失败后重来的时间。最可能超期的是 2.2（理由见 5.2 末尾：A1、A2 加的演练都在这一步）。比 `WORK.md`「两到三周」长：多了 2.5 一步，且按第 1 轮的实测（难线一片 3–6 轮复核）折算。每一步做完按实际重估。

## 6. 运行在 Agent 主机上的约束

第 2 轮的 Agent 主机是开发机：会睡（合盖）、桌面应用会退出、负载会被并行任务压满（教训 105：10 核机器 1 分钟负载 82）。第 3 轮换成 mini 上的虚拟机。

### 6.1 状态放哪

| 状态 | 放哪 | 为什么 |
|---|---|---|
| 计划、mission、任务、尝试与租约、事件、产物（任务书、报告、验收记录、交接）、规则、能力与额度账本、叫停 | PROD 的 `agentrt`（PG） | Agent 主机会睡；Owner 通过 Progress 页了解运行，它必须不依赖 Agent 主机（v4 §20.3 第 4 条） |
| 审批、发版策略、冻结、发布窗口、提问 | PROD statefile（不变） | 修复链不依赖 PG / Redis（ADR §12.3） |
| 信箱、唤醒、在线、冷却、叫停广播 | PROD `redis-agents`（派生） | 可从 PG 重建 |
| **Agent 主机上只允许有** | 厂商命令行的登录状态（只能在本机，Owner 亲自登录）；一次性的任务工作区（可由 Gitea 的提交和平台的产物重建）；`agentd` 的本地登记（只用于崩溃恢复，和平台冲突时以平台为准）；最后一个平台确认的检查点之后的工作，以及算完（`attempt_computed`）到落到平台（`attempt_persisted`）之间的结果 | 后两样在主机只是睡着或重启时不丢（醒来接着传）；**主机永久丢失时会丢**，Progress 把那次尝试标「结果未持久化」，显示最后确认的检查点时间和这次尝试已多久没有持久化，不标做完。平常检查点每 5 分钟一个，断网时传不上去，这一段跟着变长，没有固定上限（复核 142 R2）。这是硬要求 2 的例外，请 Owner 在 §7 第 7 条确认 |
| **不许只在 Agent 主机上**（今天恰恰都在） | 任务书和复核简报（`~/agent-work/<事>/`）、计划表和看板数据（`~/agent-work/status/`）、派工事件（`~/agent-work/recorder-root`）、交接记录（`HANDOFF.md`）、等待计时、额度读数 | 迁移见 5.3 |

### 6.2 `agentd` 掉线时：租约与接管协议

| 情形 | 平台和 `agentd` 怎么做 |
|---|---|
| 心跳停了（睡眠、断网、进程被冻结） | 租约 120 秒到期 → 尝试 `stale`（Progress 显示「宿主失联」，主机失联阈值 3 分钟，和 `agentthreads/config.go:44` 一致）；15 分钟宽限内同一主机拿同一隔离号回来，`attempt_renewed`，接着跑 |
| 平台拒写 | 心跳、检查点、算完、落到平台、提交，每次都在同一事务里查主机、活着的状态、隔离号、数据库时间早于 `lease_expires_at` + 宽限（5.2「写入时的隔离检查」）；不等 10 秒的租约循环 |
| 超过宽限 | 尝试 `lost`，按 `effect_class`：`none` / `branch` → 回 `ready`，下次领活是新的一次尝试。旧尝试可能还在算：**重复计算是接受、写明的代价**；每个任务只有一次尝试能被验收（`verification_one_accept`）；旧尝试晚到的推送按约定落在它自己的 `agent/<task>/a<n>` 分支，最多成为保全（推到别的尝试的分支第 2 轮拦不住，见下「进程组的边界」）。`external`（第 2 轮不派）→ `blocked`，直到旧尝试有确认的结束（`agentd` 经 `/ended` 报的 `attempt_ended`，对已 `lost` 的尝试也收；或 Owner 手工关闭）；确认结束后也不自动重派（副作用可能已发生，同审批执行器），提一条决策卡 |
| 旧 `agentd` 醒来 | 写任何东西之前先心跳；回 409 就 TERM 进程组、10 秒后 KILL，然后**保全**：把产物和本尝试分支上的提交交给 `/salvage`（宽限没过就先在本地排队重试，5.2），平台记 `attempt_salvaged`，不改任务状态；本地日志留 7 天。macOS 的单调时钟在睡眠时不走，所以 `agentd` 不靠本地计时判断租约，一律问平台 |
| `agentd` 重启 | 全机 `flock`，同一台主机只有一个 `agentd`；第一次领活之前清掉登记里还活着的进程组，报 `attempt_ended`（`daemon_restart`）；已经算完的接着传（5.2「本地登记」） |
| 进程组的边界 | 执行者能用 `setsid` 之类甩掉进程组（host-minimal 复核 117 的反例），同一用户下拦不住。第 2 轮接受：旧尝试写不进平台，这一条靠同事务的隔离检查、不靠进程组。推分支没有这样的保证：每台主机一个 Gitea 用户，能推**任何** `agent/*` 分支，逃出进程组的子进程或旧执行者推到别的尝试的分支，第 2 轮拦不住；「推不到别的尝试的分支」只防合作执行者的误用（§7 第 7 条 ② 的隔离例外，和 T11 的「部分」同一个例外，复核 142 R5）。仍然成立的是：已验收的提交和它的验收记录不可变地绑定（`verification` 只追加，记 `attempt_id`、`subject_commit`），分支事后被改不影响已验收的那个提交。第 3 轮虚拟机按整机清 |
| 只有一台主机 | 任务等主机醒来；Progress 上那件事显示「宿主失联」和等了多久，不显示「在做」；不叫 Owner（规则能处理），超过 mission 截止才变成「需要你」 |
| 防睡 | 有尝试在跑时 `agentd` 持有 `caffeinate -i -w <pid>`（防空闲睡眠，挡不住合盖）；合盖就是掉线，按上面处理 |
| 负载 | 领活时报空闲槽位；负载超过核数报 0；第 2 轮并发上限 1（2.2）、2–3（2.4） |
| 应用退出 | `agentd` 是 launchd 常驻进程，和 Claude 桌面应用、统筹线程无关；它们退出不影响在跑的任务 |
| 同一系统用户 | 任务里的 Agent 理论上读得到本机的令牌文件（MCP 令牌、reporter 令牌）。第 2 轮靠 `--strict-mcp-config` 一类的启动参数和 preflight 挡善意误用，**不防有决心的绕过**，和 ADR §5 记的已知接受风险同类（§7 第 7 条 ② 的隔离例外）；真正的隔离在第 3 轮虚拟机 |

### 6.3 搬到 mini 虚拟机时要改什么（应当只是换主机）

| 要做的 | 谁 |
|---|---|
| 平台里登记新主机（`host`、`actor`），发它自己的 `agentd` 令牌和 Gitea 用户 | Owner 发令牌；其余程序做 |
| 虚拟机里装三家命令行并由 Owner 本人登录（绝不拷贝登录文件；`claude setup-token` 这类厂商提供的长期令牌能不能用于虚拟机，要先对条款，未核实） | Owner |
| 治理层检出、钩子 trust、`agentd` 配置（`host_kind=vm`、容量） | 程序 + Owner 一次确认 |
| 开发机这台改成 `draining` → `retired`；排空后撤销它的 `agentd` 令牌和 Gitea 用户 | 程序；撤销由 Owner |
| **不应改的**：平台代码、表结构、任务书格式、产物格式。任何一处要改，就说明有状态或路径绑在了开发机上，是缺陷 | — |

第 3 轮的入口测试 **T28 换主机**：同一道基准题在新主机上跑通；任务书、产物、事件里搜不到任何本机路径（host-minimal H8 的规则）；把开发机排空后 Progress 页照常；旧主机的令牌和 Gitea 用户已撤销（拿它们心跳、推送都被拒）；旧主机上没落到平台的尝试都已保全或标「结果未持久化」。今天已知会绑住的：本机看板脚本里写死的路径（2.5 随看板退役）；Codex 沙箱不能提交（2.2 起由 `agentd` 提交，不受影响）；同一用户下的令牌可读（虚拟机解决）。

## 7. 要 Owner 定的事

| # | 问题 | 选项 | 推荐 | 属于三件事里的 |
|---|---|---|---|---|
| 1 | 状态库放哪、环境和角色怎么分 | A. 现有 CNPG `bifrost-postgres` 上新建三个库（PROD / STG / DEV），每个环境自己的两个登录角色、6 个 Secret，收回 PUBLIC 的 CONNECT（5.1.1）；B. 平台单独一个小 CNPG 集群，和 Trade、GS 的负载隔开（多一套要运维和备份的东西）；C. 只建 PROD 库，开发也连 PROD 库的另一个 schema | **A**，带三个条件：① 共用集群的负载和连接：平台每个环境的连接池上限写死（取最简单的：PROD 10、STG 5、DEV 5），实现前读 `max_connections` 和现有连接峰值（未核实），余量不够先报他；平台库出故障或被压满会波及同集群的 Trade 和 GS，反过来也一样，这是 A 接受的代价；② 备份：新库在不在备份里，2.1 验收时读备份记录核实，并做一次恢复演练（T19、O11），不写「自动覆盖」了事；③ STG、DEV 的身份连不上 PROD 库（T19）。量很小（估计每天几千条事件、几 MB）；DEV 库可丢；C 让开发能写到 PROD 的库，不可取 | 定规则（新增库属 PROD DDL） |
| 2 | 新外部依赖 | A. `github.com/jackc/pgx/v5` + 自写的嵌入式迁移执行器；B. pgx + `golang-migrate`；C. `database/sql` + `lib/pq`。另：平台 CI 加 `postgres`、`redis` 两个 sidecar（钉摘要的镜像） | **A**，加 sidecar。按需求选：中继要 `LISTEN`；状态表触发器要求事务里 `SET LOCAL`；2.3 导入要批量写（`CopyFrom`）——pgx 都直接有。迁移规则只有「按序、一文件一事务、sha256 不许变」，不值得再引一个库。自写迁移器的条件：持 `pg_advisory_lock`；只做扩展型改动；三项测试——同时起两个迁移只有一个做事、改过的文件被拒、旧版本二进制对新结构跑一遍存储包测试。没有 sidecar，数据层的测试在 CI 上跑不了 | 定规则 |
| 3 | 决策卡用什么存 | A. 复用已在 PROD 的「提问」，加 `owner_duty`、`task_id` 两个字段（改公开接口）；B. 照 v4 新建 `agentrt.decision` 表 | **A**。提问已有选项、推荐、「不回复会怎样」、手机通知和 MCP 工具；同一件事存两处会再出一次「哪份是真的」。两条不变：回答永远不算批准（`questions/transition.go:52` 的 `Approval: false` 保持，W-65）；终态提问会被裁剪（`questions/store.go:133`），所以控制器看到的回答（选项、原文、谁、何时）抄进 `question_seen` 事件，作为 PG 里不可变的事实，计划和决定以它为准 | 定规则 |
| 4 | 计划迁进运行时之后，markdown 怎么办 | 第 2 轮只迁 W-31 的计划（轮、项、步、「架构对照」）和派工记录；`TECH_DEBT.md`、`RATCHETS.md` 第 2 轮仍是 markdown，迁它们在第 3 轮或以后、另做数据设计（§8）。A. 计划表 2.3 导入后从 `WORK.md` 移出，只在 Console 和 MCP 看，`WORK.md` 留 `W-n` 索引和指向；B. 计划表保留为程序生成的只读快照，由平台定期提交回仓库；C. 维持现状，LLM 手改 | **A**。一处事实；B 要让平台获得写仓库的权限，C 就是今天出错的来源（§9）。工作区 `CLAUDE.md` §5「未结的债只在 `TECH_DEBT.md`」第 2 轮不变 | 定规则 |
| 5 | `agentd` 的身份与凭证 | A. 每台主机一把 `agentd` 角色的令牌（新鉴权角色，绑定 `host_id`），外加每台主机一个 Gitea 用户、只能推 `agent/*`；B. 复用现有的 reporter 令牌和一把部署钥匙 | **A**。reporter 令牌今天是共用的一把，持有者能替任何主机报心跳（host-minimal §4）；按主体才分得清谁领了什么，T02、T03 才测得出。「只能推 `agent/*`」要在它能写的**每个**仓库上验出来：推 `main` 被拒、推标签被拒、改分支保护被拒（它不是仓库管理员）；2.2 验收时逐仓跑一遍，做法按 Gitea 版本的分支和标签保护、以实测为准。它能推**任何** `agent/*`，同一主机上的尝试之间不隔离，见第 7 条 ②。主机排空时撤销它的令牌和 Gitea 用户（§6.3、T28） | 定规则 |
| 6 | 数据模型与运行时接口 | A. 以 5.1.2 的表结构草图、5.1.3 的事件词表、5.2 的 `/api/v1/agentrt/*` 路由和 MCP 工具作为实现的基础；正式 DDL 实现和复核定稿后另交他，批了才执行（O10）；B. 每张表、每组路由各批一次 | **A**。新增表和新公开接口是架构级的，这里一次披露、一次定；逐张批会让 2.1 停在等批上。正式 DDL 不因这条免批 | 定规则 |
| 7 | 第 2 轮的两个例外：① 硬要求 2——结果持久化的边界；② 尝试之间的隔离（复核 142 R2、R5） | A. 两条都接受。① **最后一个平台确认的检查点之后**的工作、超过 1 MiB 没能落成检查点的补丁、算完到落到平台之间的结果，在**主机永久丢失**时会丢。平常检查点每 5 分钟一个，但断网时传不上去，这一段跟着断网时长变长，不承诺「最多 5 分钟」；Progress 标「结果未持久化」，显示最后确认的检查点时间和这次尝试已多久没有持久化，不标做完。② 第 2 轮的隔离例外：每台主机一个 Gitea 用户，能推**任何** `agent/*` 分支；执行者能甩掉进程组（§6.2「进程组的边界」）；同一用户下的令牌可读（§6.2「同一系统用户」）。所以「旧尝试推不到别的尝试的分支」只防合作执行者的误用，不防有决心的绕过；仍然成立的是已验收的提交和它的验收记录不可变地绑定。和 T11 的「部分」是同一个例外，第 3 轮虚拟机补。B. ① 检查点改成每 1 分钟，平常丢的那一段变小、上传量变成 5 倍，断网时同样没有上限；② 第 2 轮就做按尝试授权的推送入口，加越权推送测试 | **A**。① 主机睡着、重启、断网都不丢（醒来接着传，或保全）；真正丢的只有主机彻底坏掉、还没传的那一段，而且页面上看得出来。② 和 §6.2「同一系统用户」、ADR §5 的已知接受风险同类，真正的隔离在第 3 轮虚拟机 | 定规则（放宽他的硬要求；② 同时改 ADR 的「每次尝试隔离」，见第 8 条 ⑦） |
| 8 | 随 v5 一起改的 ADR 条款 | A. 全部同意，实现前改进 ADR：① `ADR:252`「新建一个库 `bifrost_platform`」→ 三个库、六个角色；`ADR:253` 的 `redis-agents` 加 STG 一套、DEV 借 `redis-dev`（§1 第 11 行、5.1）；② `ADR:254`「迁 PG 的只有 mission、任务、事件和预算」→ 加计划、产物、规则、能力账本；③ `ADR:255`「先是 MacBook」→「Agent 主机」（§1 第 1 行）；④ `ADR:283` 参谋长「24 小时在线，跑在 mini 上」→ 第 2 轮用任务实现，24 小时随第 3 轮（§1 第 8 行）；⑤ `ADR:311`「第 2 期起改由平台发号」→ 推迟到台账迁进运行时（第 3 轮或以后）：`WORK.md` 仍是 Owner 读的索引，计划节点用 `work_id` 带上 `W-n`；mission、任务、计划节点自己的编号第 2 轮就由平台发；⑥ `ADR:338-344` 的分期 → 第 2 轮 2.1–2.5、第 3 轮（§1 第 2 行）；⑦ `ADR:355`「任务自动接管」的门槛「旧执行者失效、每次尝试隔离、不重复副作用」→「`none` / `branch` 类：不要求旧进程先停（它写平台按隔离号被拒），接受重复计算，安全目标是一个任务的结果只被采纳一次（`verification_one_accept`）；`external` 类：旧执行者的结束被确认（`attempt_ended` 或 Owner 手工关闭）才接管，确认后也不自动重派；每次尝试的隔离第 2 轮按第 7 条 ② 的例外」（§6.2，复核 142 R5）。B. 逐条打回（写明哪一条） | **A**。不改这几处，v5 就和「冲突以 ADR 为准」自相矛盾，不能作实现依据 | 定规则 |

## 8. 第 2 轮明确不做的

- 搬到 mini 虚拟机（第 3 轮）；槽位账户与真正的执行隔离（第 3 轮）。
- 推理网关、本地 GPU 杂活池、`local:chat`、业务租户（v4 阶段 3、4；T17、T18）。
- 策展（洞见包）、人工运输（Design）岗位。
- v4 第 0 步里和运行时无关的：工作区即代码与新节点测试、Gitea 搬到 05 / 06 和元数据迁 CNPG、`bifrost-private` 与 design 仓库、根目录白名单的防线、AGENTS.md 合并评估、gitea-mq 合并队列。
- 发布队列（v4 §9、ADR §12.7）和无人值守的 PROD 发布（W-56 全自动部分）；发版策略的签发仍按 S0-8 自己的节奏。
- 网页推送 / PWA（S0-0e、W-44 的推送部分）；手机原生应用（已否）。
- 厂商云端任务（Claude Routines、Codex cloud、Cursor 云端 Agent）、自托管执行器（Cursor My Machines、Claude self-hosted environments）、ACP 适配器、A2A、LiteLLM、Harbor / inspect_swe 外部考场。
- 真正的 CNPG 切换演练（影响 Trade 和 GS）。
- 业务工作和其余技术债（Owner 10-13：架构完成前不做）。
- `TECH_DEBT.md`、`RATCHETS.md` 迁进运行时（状态行、计数、「待你签收」、Console 上签收）：第 3 轮或以后，另做数据设计；`W-n` 改由平台发号随它一起（§7 第 4、8 条）。
- 内核之前的外层小版本（Owner 10-13 定从内往外）；本机看板在 2.5 前只修会答错的。

## 9. 现在由 LLM 手工维护、要改成程序维护的活

原则（ADR §12.2 第 13 条）：状态、顺序、闸门、计数、超时、锁、预算、权限、记录，凡是能写成「是或否」的，落成程序；模型提议，程序放行。落点按从内往外排：先有表（2.1），再有接口和控制器（2.2），再迁本机文件（2.3），最后换界面（2.5）。

| # | 活 | 现在怎么做 | 出过的错 | 程序化后由什么维护 | 落在哪一步 |
|---|---|---|---|---|---|
| 1 | **计划结构和状态**：轮 → 项 → 步的编号、谁在做、做完几步、在跑的活对应哪一步 | LLM 手改 `WORK.md`「第 N 轮逐项」「架构对照」并改「核对于」时间；本机 `roadmap.py` 解析它；`board2.py:481-489` 的 `step_id_of` 按派工名的前缀认步骤（过渡：派工名要以「项号-步号」开头才认得出） | 第 2 轮的「2.0-1」按第 1 轮的写法认不出，在跑的活挂不到步骤上（`board2.py:482-484`，Owner 10-13）；全局计划和台账是两份、手抄（教训 51、52）；台账状态落后（ADR §12.2 第 13 条列的当天证据） | `plan_node`（编号分配后不变，触发器挡改号和错的父子类型）；步骤状态只由 `plan_node_state_changed` 事件改，事件的原因是满足了 `done_rule_json` 里的哪一条（任务验收、审批执行、提问回答、CI 结果、门禁测试、Owner 签收）；任务挂哪一步由控制器按提议上下文写、触发器校验；计数按 5.1.2 的一条规则算；LLM 只能 `propose_plan_change`；架构对照的勾由对照当前部署的 `verification` 算 | 2.1 表；2.2 接口和控制器；2.3 导入；2.5 界面 |
| 2 | **派活和收结果**：写任务书、启动 Codex / Cursor、等、读报告、决定下一步 | 任务书写在 `~/agent-work/<事>/TASK*.md`；`lane.py start -- codex exec …` / `cursor-agent -p …`；统筹线程盯进程、读 `REPORT.md`、决定复核或返工。Claude 子代理在统筹线程里做的活，派工工具完全看不见（没有事件） | 监控脚本在 CI 结束那一刻死了，看板一直显示「在跑」，等了 9 分钟（教训 48）；夜里 8 小时没有进展（教训 106）；并行把机器压满（教训 105） | 任务书是 `task_spec` 产物；`agentd` 领活、起进程、心跳、交产物；控制器按验收结果排复核或返工、按 `route_json` 换人；Claude 的活由 `claude` 执行者经 `agentd` 跑，在统筹线程里用子代理做的活不算计划里的步骤 | 2.1 表；2.2 `agentd`（Codex、Cursor）与控制器；2.4 `claude` 执行者 |
| 3 | **台账记账**：`TECH_DEBT.md` 的状态行、「待你签收」一节、未结计数；`RATCHETS.md` 的行；签收后删条目 | LLM 改 markdown、手数计数 | 未结计数手数错：10-13 重数是 114 项，此前写的 99 少数了（`TECH_DEBT.md:19`） | 第 2 轮不动，仍是 markdown。方向：每条债和防线的状态、验收命令和结果成为运行时数据，计数和「待你签收」由程序生成，签收是 Console 上的一个动作（`owner_signoff` 事件），条目正文仍由人写；表结构和导入另做数据设计 | 第 3 轮或以后（§7 第 4 条、§8） |
| 4 | **发布流程**：持有窗口、发测试环境、核对、源检查试跑、建正式环境发布单前的三条前提、盯执行、核对正式环境 | 统筹线程手工跑 `release.sh window / hold / stg`、核对 Pod 与摘要、`request_action`、`~/agent-work/release-platform-prod/watch.sh` 盯 | 没看 CI 就建了 PROD 发布单（教训 38）；发布结束后窗口没放开（教训 11）；两会话同发一个版本（工作区 `CLAUDE.md` §5 的 09-27、09-28 两次事故） | 计划里的 `release` 类步骤：控制器在建单前程序检查三条前提，缺一条不建；单子执行后自动建确定性核对任务（复用第 1 轮 ⑤ 的摘要核对）；窗口和执行仍由平台已有的部分负责（审批执行器、窗口 ConfigMap）；步骤由 `approval_seen` 事件推进 | 2.2（前提检查、核对任务、步骤推进）；全自动发布不在第 2 轮 |
| 5 | **交接记录与看板手写行**：`~/agent-work/status/HANDOFF.md`、`tasks.json` 的「需要你」「在做」「最近」「队列」「图」 | 统筹线程在压缩上下文前、交接前手写 | 手写段落跟不上实际，Owner 10-13 22:04 指出「在跑」一栏混着手写行和事件算出的行、同一件事出现两次（`WORK.md` W-31「第 2 轮」那一条）；「需要你 1」和「3 个等我接手」让 Owner 读成三件要他做（教训 80） | 交接 = 读运行时（`whoami`、`get_plan`、`list_tasks`、未结的提问和审批）；判断性的话写成 `handover` 产物；「需要你」由提问、审批和计划里的 Owner 步骤生成 | 2.1 表；2.3 迁移和 `handover` 工具；2.5 看板退役 |
| 6 | **等待计时和看护** | `RULE-waits` 的上限由统筹线程掐表；`~/agent-work/watch-agents.sh` 叫醒 | 线程断了、机器睡了就没人掐表（`RUNTIME-PLACEMENT` §10 第 4 行） | 控制器的租约循环和 `wait_limit_passed` | 2.2（租约）；2.3（等待上限） |
| 7 | **额度读数和指派** | 统筹线程读各家页面、`usage.py`、`cursor-quota.json`，凭当天判断指派 | 从两次读数推出「Codex 一天只够 9 次」，结论相反（教训 63） | `vendor_pool`、`budget_ledger`、`capability_*`；分流程序按 5.1.2 的七步 | 2.1 表；2.4 分流 |
| 8 | **编号发放** | `W-n` 由 LLM 在 `WORK.md` 发号，`check_work_ids.py` 查重；派工名由 LLM 起 | 两个协调者撞号（v4 §1.1） | mission、任务、计划节点的编号由平台发；`W-n` 仍在 `WORK.md` 发号，计划节点用 `work_id` 带上它；平台发 `W-n` 推迟到台账迁移（§7 第 8 条） | 2.2；`W-n` 第 3 轮或以后 |
| 9 | **留给 LLM、不程序化的** | — | — | 设计；写任务书的内容；复核的判断和发现；有推荐的选择题怎么选（按 ADR §12.2 第 15 条留痕）；给 Owner 的文字（决策卡的措辞、简报）；解释失败的原因；提议改计划、提议改规则、起草教训的原因和机制。这些的**结果**进运行时（产物、提议、事件），由程序决定是否放行 | — |

## 10. v4 不变的部分

v4 的 §0、§1、§2（组件表里 `agentd` 的位置改读「Agent 主机」）、§3、§4、§5.1–5.4（5.2「跑在 mini 上」改为 §1 第 8 行）、§6、§9、§13 的混沌与治理层探针、§14、§16、§17、§18、§19、§20 照旧有效；§7.5 的表以本文 5.1.2 为准；§10（第 0 步）和 §12（分阶段）以本文 §5、§8 为准；§13 的三条规则测试并进 T35。

## 11. 复核 141 的处理

复核报告：`~/agent-work/codex-review-141/REPORT.md`。处理办法由统筹方定，本稿照写；细节没定的取了最简单的做法，并在正文里写明（例：`lease_expires_at` 算存活列、连接池上限的数）。

| # | 发现 | 改了什么 | 在哪 |
|---|---|---|---|
| A1 | 结果直到收尾才离开主机 | 尝试结束分算完 / 落到平台 / 提交三个事实、各有事件，只有落到平台的能被验收；每 5 分钟检查点（日志尾部、补丁，≤ 1 MiB）；过期尝试可保全到自己的分支（`attempt_salvaged`，不改任务状态）；上传和提交幂等；主机永久丢失只剩检查点，页面标「结果未持久化」，作为硬要求 2 的例外请 Owner 定；T34 | §1 第 14 行、5.1.2、5.1.3、5.2、§6.1、§6.2、§7 第 7 条 |
| A2 | 旧执行者没有失效 | 接管协议：进程组 + 本地登记 + 全机锁，重启先清登记里的组；心跳、上传、提交同一事务查主机、状态、隔离号、数据库时间；`none` / `branch` 宽限后重派（重复计算是写明的代价，每任务只验收一次），`external` 等确认结束；T01 按副作用类别；T22 加三项演练 | 5.1.2（`verification_one_accept`）、5.2、§6.2 |
| A3 | 计划关联靠 LLM 填 | 父子类型、只挂 `step`、同 mission、评审继承的触发器；控制器按上下文写 `plan_node_id`，计划外标 `off_plan`；`done_rule` 只引用绑在本步的对象（`plan_node_binding` + `plan_changed`）；计数规则只定一处；T32 | 5.1.1、5.1.2、5.1.3、5.2 |
| A4 | 证据没绑版本 | `gate` 验收带提交、环境、部署（交付 run 和镜像摘要）、规格 sha256；原子分历史事实和持续条件，持续条件对照现在的部署，读不出是 `unknown`；T33 | 5.1.2、5.2 |
| A5 | 验收依赖倒置 | 中继和重建进 2.1 存储包，2.3 只接线；T26 在 2.4 经 API / MCP 给目标，2.5 验 Console 入口；T23 拆成 T23a、T23b；T25 改成数据库保证（`SET LOCAL agentrt.event_id` + `event.txid`），只有存活列例外 | 5.1、5.1.1、5.1.5、5.2–5.6 |
| A6 | 三个环境的角色落不了地 | 每环境两个角色、六个 Secret，收回 PUBLIC 的 CONNECT；T19 加跨环境连接被拒 | 5.1.1、5.1.5、§7 第 1 条 |
| A7 | §7 不全 | 加第 6 条（数据模型与接口）、第 8 条（ADR 修订，含 `W-n` 发号推迟）；第 4 条收窄到计划，台账第 3 轮或以后 | 文首、§3、§7、§8、§9 |
| A8 | statefile 重试次数说宽了 | Write 3 次（`:88`）、Update 5 次（`:130`）。顺手把 `board2.py` 的行号改成 `:832`、`:837`（复核问题 1 的附注） | 2.1、2.1 表 |
| B1 | Redis 的并发语义 | PG 是领活和未读的唯一查询来源，流只报信；重建拿中继锁（续期 + 隔离令牌），ack 一律进 PG；MAXLEN 只丢信号；presence 缺了是「未观测到在线」；T15a 加三种 | 5.1.4、5.1.5 |
| B2 | 心跳与事件的承诺冲突 | 生命周期和授权状态必带事件；存活列直写、由触发器放行；主机在线 / 失联按时间算，删掉 alive ↔ lost 事件；不再说事件能回放心跳 | 5.1.1、5.1.2、5.1.3 |
| B3 | 验签与执行分离 | 从验过签的原文解析执行；`body_json` 必须等于规范形式；签名覆盖编号、版本、方向、有效期；自己的 namespace；收紧按结构比较；失败即关；T35 含 v4 三条 | §3、5.1.2（`rule`）、5.2 |
| B4 | host-minimal 与血缘的适配 | 3.1 的继承 / 替换 / 暂停表，治理层链接是钉版本的只读例外，H7 / H9 / H10 的槽位部分暂停；`Agentrt-Task` 的解析、返回、显示是 2.2 新工作（T36），原有尾注照旧 | §3、3.1、5.2 |
| B5 | 估算与计数口径 | Owner 依赖清单 28 行（决定 8、批准 11、亲手 9）；4–6 周只算有效工作量；2.2 最可能超期并写明原因；各步按挪动的工作重估（2.1 4–5、2.2 8–11、2.3 3–5 天） | 5.1–5.5 末尾、5.7 |
| B6 | 推荐理由缺条件 | 第 1 条连接上限、负载和备份恢复验收；第 2 条迁移锁、并发、兼容测试和具体需求；第 3 条回答不算批准、回答抄进 PG；第 5 条逐仓验推送限制、排空撤凭证 | §6.3、§7 |

统筹方在修订 1 之后另补两处（2026-10-14，读 infra 文件核实）：5.1.1「创建方式」改为跟现有库同一条路——库是 `k8s/data/databases.yaml` 里的 CNPG `Database`，角色走 db-step（集群清单里没有托管角色），并加「角色矩阵」「备份」两行，O6 随之改写；Gate A 加「T32（经接口）」一行，补 A3 要的接口层覆盖。

## 12. 复核 142 的处理

复核报告：`~/agent-work/codex-review-142/REPORT.md`（审的是 infra `0a03a09` 的修订 1）。这条复核线的两轮已经用完、已停，下一步由 Owner 定；本稿只照报告的最小修法改（报告给了两种修法的，取统筹方选的那一种），不重新设计，改完没有再复核。报告「可以不改」一节的结论（A4、A6、A8 与上轮 B2–B6 关闭）不动。

| # | 发现 | 改了什么 | 在哪 |
|---|---|---|---|
| R1 | 先写事件的协议和即时外键互相卡死 | 事件指向 mission、计划节点、任务、尝试的外键改成 `DEFERRABLE INITIALLY DEFERRED`，提交时核对；`actor_id` 也延期，只为种子；状态触发器仍即时查本事务的事件存在且键相等。写明空库的种子顺序（`system` 流 → 第一条 `actor_registered` → `controller`、`owner` 两行，一个事务、不关触发器），新流第一次写时建；提交失败整个事务回滚、`seq` 不跳号 | 5.1.1 触发器；5.1.2 `event` 草图、写入路径、「空库的种子顺序」；5.1.3（`actor_registered`）；T19 |
| R2 | 周期检查点共用一个幂等键；「最多 5 分钟」 | `checkpoint` 的键改成 `attempt_id + checkpoint_seq`：同一次采样的重试复用、下一次采样换新号，本地登记保存。损失边界改成「最后一个平台确认的检查点之后」，断网时没有固定上限；Progress 显示那个检查点的时间和这次尝试已多久没有持久化 | §1 第 14 行；5.1.3；5.2 路由表、`agentd`「检查点」；§6.1；§7 第 7 条 ①；T34 第五、六种 |
| R3 | 反向改绑和并发加依赖没挡住 | 一步一经挂了任务，它的 mission 绑定和任务的步骤绑定固定；迁移只能是一次原子的 `plan_changed`，提交时重验任务、验收评审和 `done_rule` 引用（延期的约束触发器）。依赖插入在查环之前拿依赖图的一把事务级 advisory lock | 5.1.1；T32 加三种（步骤挂任务后改绑 mission、`done_rule` 引用后改任务的步骤、并发 A→B / B→A） |
| R4 | Gate A 的接口测试依赖 2.3 的导入 | Gate A 的 T32 只经新增任务、改计划两条路由；导入的反例和「导入两次」挪到 Gate B 新行「T32（经导入）」；写明 2.1 的 T30、T32 用存储包的通用批量写入夹具，不是 `WORK.md` / 记录器导入器 | 5.1.5（T30 与表后说明）；5.2 Gate A「T32（经接口）」；5.3 Gate B；5.6 |
| R5 | §7 漏了接管门槛的改变；把分支命名当权限保证 | §7 第 8 条加 ⑦：`ADR:355` 的准确修订（`none` / `branch` 接受重复计算，安全目标是结果只采纳一次；`external` 确认旧执行者结束才接管），推荐 A。§7 第 7 条加 ②：写明第 2 轮的隔离例外（每主机一个 Gitea 用户能推任何 `agent/*`、执行者能逃出进程组、同用户令牌可读），「推不到别的尝试的分支」只防合作执行者的误用；删掉 §6.2 的无条件说法；保留已验收提交和验收记录的不可变绑定；和 T11 互相引用 | §6.2「超过宽限」「进程组的边界」「同一系统用户」；§7 第 5、7、8 条；5.7 O14；T11、T22 ② |
| R6 | T15a 要求 Redis 和 PG 逐项相等 | T15a、T15 改按经 PG 查到的未读、就绪、叫停（和冷却）事实及去重后的逻辑处理次数验收；Redis 允许裁剪、重复、陈旧信号；Redis 快照只在静止、未裁剪、无并发的小夹具里比；「恰好重投一次」改成「逻辑上只处理一次」 | 5.1.5 T15a；5.3 T15 |
| B1 | 重试命中和租约检查的先后 | 先鉴别主体、再查幂等键；命中已提交的操作只读返回原响应；只有新操作才查活着、隔离号、时间 | 5.2「写入时的隔离检查」；T34 第七种（成功 `submit` 后重试） |
| B2 | 保全与结束通知的短窗口 | 宽限内保全只在本地排队、每 60 秒重试，过了宽限才收；新路由 `POST /attempts/{id}/ended`，对已终态的尝试也幂等登记 `attempt_ended`；保全的结果要采纳只能另建新的验收任务，`lost` 的尝试不直接 `accepted`，每任务一次采纳不变 | 5.2 交付物、路由表、`agentd`「本地登记」「心跳与死人开关」；§6.2「超过宽限」「旧 `agentd` 醒来」；统筹方补：保全核过也写 `persisted_at`（尝试仍是 `lost`），采纳记录因此指向它，采纳时取消该任务还在跑的新尝试（5.2 `/salvage` 一行；T34 加一种） |
| B3 | 事务开始时间与锁 | 先 `FOR UPDATE` 锁尝试（和任务）行、读最新的行，截止用 `clock_timestamp()` | 5.2「写入时的隔离检查」；T22 ⑤（截止前进事务、截止后拿到锁） |
| B4 | gate 原子的匹配谓词 | 加 `check_ref` = 原子里的测试编号，且验收记录的任务和尝试对得上 | 5.1.2「持续条件」；T33 加一份规格含多个测试编号的反例 |
| B5 | 2.2 的最小候选选择 | 2.2 用初始签名规则生成的固定候选快照，领活时查独立性和已签的硬约束；成绩和额度排序在 2.4；O19 含首批候选名单 | 5.1.2「分流顺序」；5.2 交付物；5.4 交付物；5.7 O19、O23 |
| B6 | 重建的写命令只点名了 `XADD` | `DEL`、`XGROUP`、冷却的 `SET`、epoch / rebuilding 标志、删锁都在 Lua 里比对持有者令牌 | 5.1.4 `agrt:relay:lock` 行、重建段 |
| B7 | 无签名收紧的措辞 | 无签名收紧照样允许：闭合解析、结构比较证明是收紧后立即生效；「从验过签的原文执行」只说 `initial`、`loosen` 和任何带签名的输入 | 5.1.2 `rule` 注释；5.2「规则」 |
