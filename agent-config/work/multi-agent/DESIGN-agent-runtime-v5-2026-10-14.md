# 多 Agent 协作运行时：设计 v5（v4 的修订）

- **状态**：v5 草稿，2026-10-14 起草（W-31 第 2 轮 2.0）。**待 Codex 独立复核、待 Owner 确认**；确认之前不是实现依据。
- **和 v4 的关系**：v5 是 `DESIGN-agent-runtime-2026-10-08.md`（v4）的修订，不是重写。v4 和 Owner 定稿的原则（§1）、总体结构（§2）、规则集（§3）、岗位目录（§4）、参谋长的职责与边界（§5.1–5.3）、租户与算力（§6）、发布与副作用（§9）、借鉴与粘合剂策略（§17、§18）、手机端（§19）、进展可观察的要求（§20）、测试编号 T01–T18 都保留。本文只写改了什么、为什么，以及第 2 轮怎么做。和 ADR（`ADR-ops-architecture.md` §1、§5、§12）冲突时以 ADR 为准；v5 里要改 ADR 的地方列在 §7。
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
| 3 | 计划进运行时 | 运行时只有 mission 和任务；进展由事件算（v4 §20.1） | 新增**计划结构**：轮 → 项 → 步，编号一经分配不变；每一步带一条「何时算做完」的规则，只由事件推进（审批执行、提问回答、任务验收、CI 结果、门禁测试通过）。LLM 只能**提议**改计划，不能手改状态。「架构对照」也是计划数据，每行的勾由它对应的验收测试结果算出来 | 第 2 轮的计划和进展一换轮次就退化，因为编号和状态由 LLM 手写（Owner 10-13 晚；`board2.py:481-484` 的注释记了一次：第 2 轮的「2.0-1」认不出） |
| 4 | 分流 | 按各家剩余额度分流（v4 §6、§12 阶段 2） | **按能力和额度分流**：先按岗位筛出能胜任的（资格考试、基准题集、在岗成绩、实测的硬约束），再在里面按额度挑。数据层有「执行者 × 模型 × 岗位 × 任务类别」的成绩表和硬约束表；放宽候选名单要 Owner 签 | Owner 2026-10-13 晚 |
| 5 | 租约 | 任务级租约 120 秒、心跳 30 秒、`FOR UPDATE SKIP LOCKED`（v4 §7.2） | 租约挂在**尝试**（attempt）上，带隔离号（lease epoch）：过期先进「过期待续」，宽限期内同一主机可以续；过了宽限期判「丢失」，按任务的副作用类别决定重派还是挂起。沿用审批执行器已经在 PROD 跑的做法（`approvals/execution.go:14-33,355-357`） | Agent 主机会睡；只有一台主机时，任务要能等它醒，又不能让醒来的旧进程写坏状态 |
| 6 | 决策卡 | 新表 `agentrt.decision`（v4 §7.5） | **复用已在 PROD 的「提问」**（`questions/types.go:46-72` 已有选项、推荐、`meanwhile` 即「不回复会怎样」、`work_id`），加两个字段：`owner_duty`（三件事里的哪一件）和 `task_id`。待 Owner 定（§7 第 3 条） | 同一个概念不存两处；提问入口和 Owner 的手机通知已经接好 |
| 7 | 身份 | `actor` 一层 | 身份分**工具**和**模型提供方**两层（ADR §12.10「身份分工具与模型两层」）：执行者是工具（`exec:cursor`），每次尝试记下实际用的模型和提供方；独立验收按提供方判（ADR §12.5）。主机另有一张表；`agentd` 每台主机一把令牌（§7 第 5 条） | Cursor 一家能跑 Claude、GPT、Grok 等多家模型 |
| 8 | 参谋长的形态 | 一个 24 小时在线的席位，跑在 mini 上（v4 §5.2） | 第 2 轮用**任务**实现席位：控制器在固定时点、Owner 说话、出现阻塞时生成 `brief` / `plan` 任务，由坐席的候选执行；Owner 的对话入口是「提问」和信箱（加厂商的 Remote Control 作补充，§4）。24 小时在线随第 3 轮的 mini 虚拟机到位 | 第 2 轮只有一台会睡的 Agent 主机，常驻会话做不到 24 小时；任务形态在主机醒来后自然接着做，状态都在平台 |
| 9 | 基准与考场 | 用 Harbor 或 inspect_swe 做考场，第 0 阶段测 Cursor 20 次（v4 §11） | Gate A 用 `agentd` 本身跑 6 道回放题（§5.2）；20 题全集在 2.4 跑，作为能力成绩的初始数据。外部考场（Harbor / inspect_swe）放到第 3 轮之后 | 第 2 轮的被测对象就是这套运行时；先让它自己跑通 |
| 10 | 进展 | 运行时阶段 1 起由事件算（v4 §20.4） | 2.5 交付：PROD Console 的 Progress 页**完全由接口生成**（计划栏、架构对照、现场、需要他做的事），本机看板（`~/agent-work/status/`）退役；验收是停掉 Agent 主机上的看板程序后 PROD 页照常正确（T24） | Owner 10-13 晚 |
| 11 | 环境 | 状态库和 Redis 只在 PROD | 状态库分 DEV / STG / PROD 三个库；DEV 库给 Agent 主机上 `bdev` 跑的本地 platform-api 开发用。事实只认 PROD | 开发在 Agent 主机上的本地平台进行，需要一份可丢的库 |
| 12 | 第 1 轮已建好、直接成为运行时一部分的 | —（v4 写于第 1 轮之前） | 审批单与编号、执行器领单、提问、ntfy 通知、线程心跳、发版策略与冻结的代码和闸门、CI 门禁、按摘要核对、提交血缘、派工记录的事件格式。逐项见 §3 | 第 1 轮 75 步 2026-10-13 22:11 做完（`WORK.md` W-31「第 1 轮逐项」） |
| 13 | 厂商自带、不必自建的 | v4 §17、§18 有原则，没逐家核对 | 逐家核对了本机命令行的 `--help` 和公开文档，结论分「自建 / 用厂商的 / 先用厂商的、留接口」三类（§4） | 粘合剂策略（ADR §12.2 第 6、7 条） |

## 2. 现状清点

### 2.1 平台（PROD）

| v4 组件 | 现状 | 证据 |
|---|---|---|
| `agentrt` 内核 | 没有 | `api/internal/` 下没有 `agentrt` 包（`5021b0f` 的目录清单） |
| 推理网关 | 没有 | 同上 |
| 平台用的 PG / 独立的库 | **没有**。平台今天不用 PG | PROD `platform-api`、`platform-workers` 两个 Deployment 的环境变量名里没有任何 PG 相关的（只有 `REDIS_IB_PLATFORM_PASS`、`PLATFORM_ROLE`、`PLATFORM_DATA_DIR`）；`api/go.mod` 只有 `github.com/redis/go-redis/v9`（第 10 行），没有 PG 驱动，`database/sql` / `pgx` 在 `internal/` 下零引用。`bifrost_platform` 库在不在：只读身份列不出 CNPG 的 `Database` 对象（Forbidden），**未直接核实**；`AGENT_FACTS.md:431` 只列了 `bifrost_dev` / `bifrost_stg` / `bifrost_prod` / `bifrost_golden_source` |
| 平台现有的状态存储 | 已有：statefile，每个键一个 ConfigMap | `statefile/statefile.go:1-14`；`statefile/k8sstate/k8sstate.go:26-34`（`platform-state-<key>`，**每个键上限 900 KiB**），冲突重试 5 次（`:130,167`）。PROD 现有 10 个键：`approvals`、`agent-threads`、`agent-progress/state.json`、`audit/*`（2 个）、`checklist/signals.json`、`patrol/state.json`、`release_cycles_platform.json`、`release-policy-freeze`、`release-policy-reminders` |
| 审批状态机 | 已有 | `approvals/types.go:8-25`：`pending → approved → running → executed / failed`，另有 `rejected`、`expired`、`unknown`；存 statefile 键 `approvals`（`server/server.go:351`）；路由 `approvals/handler.go:21-44`（建单 operator，批 / 驳 admin，领单 executor） |
| 编号 | 已有（审批 `#n`、提问 `Qn`）；工作项 `W-n` 仍由 LLM 在 `WORK.md` 发号 | `approvals/types.go:36-38`、`approvals/store.go:470-478`（`nextNumber`）；`questions/types.go:47-48` |
| 执行器领单（审批） | 已有，有租约 | `approvals/execution.go:22-25`（租约 60 秒、心跳 20 秒、过期 10 分钟后判 `unknown`），`:355-357`（宽限期内可续）；主机执行器 S0-0c 搁置（`WORK.md` S0-0c 状态行） |
| 通知 | 已有（ntfy） | `approvalnotify/notify.go:1-11`：经 .50 的告警中转发到 ntfy；网页推送 S0-0e 未开始 |
| 提问入口（决策卡的雏形） | **部分**：代码在 PROD，PROD 上还没有任何一条记录 | 结构 `questions/types.go:46-72`；路由 `questions/handler.go:17-37`（建 reporter，答 admin）；MCP 工具 `ask_owner`、`wait_for_answer`、`ack_answer`、`withdraw_question`（`mcp/platform/src/index.ts:553-605`）。PROD 命名空间里没有 `platform-state-questions`（第一次写入才建，`server/questions_wire.go:26`）。缺 `owner_duty` |
| 线程心跳 | 已有 | 路由 `server/server.go:479`；事件和状态 `agentthreads/threads.go:74-101`；阈值 `agentthreads/config.go:38-44`（回合中 10 分钟静默、主机 3 分钟失联）；PROD 有 `platform-state-agent-threads` |
| 主机心跳路由 | **部分**：路由在，没有主机在报 | `server/server.go:481` → `agentthreads/handler.go:78-97`；正文只有 `host` 和三家的 `wired` / `token`（`agentthreads/threads.go:246-256`），没有容量、没有租约。脚本 `agent-config/scripts/host-heartbeat.js:1-15`（launchd 每分钟一次）**没有在任何主机加载**（`WORK.md`「宿主心跳与未接入监测」状态行；本机 `~/Library/LaunchAgents` 里没有它的 plist） |
| 协作进展（Progress 页） | **部分（过渡）**：开发机算好、推到平台；平台只存最新一份 | 本机 `~/agent-work/status/board2.py` 每 2 秒算一次，每 15 秒（`board2.py:819-821`）瘦身后调 `publish-result.js` → `scripts/progress-publish.js` → `PUT /api/v1/agent/progress`（`server/server.go:483`）。平台只留最新一份、上限 256 KiB、5 分钟没更新标过期（`agentprogress/document.go:23-27`；`server/agent_progress_wire.go:11-15` 自称「过渡桥」）。推上去的文档里有 `roadmap.arch`（架构对照）和 `roadmap.round`（本轮步骤），但 Console 只解析 `goal`、`note`、`generated_from`、`stages`、`groups`、`exit`（`console/src/api/agentProgressBoard.ts:135-146`），**这两块在 PROD 页上不显示**。开发机睡了，页面过 5 分钟变「过期」 |
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
| 提问（questions） | 就是 v4 的「决策卡」：加 `owner_duty`、`task_id` 两个字段（§7 第 3 条） | 不退役 |
| ntfy 通知（`approvalnotify`、`notice`） | 运行时的「主机失联」「任务挂起要你定」等通知走同一条路 | 不退役；网页推送不在第 2 轮 |
| 线程心跳（`agentthreads`） | 留给交互线程（统筹线程、参谋长的交互会话）；`agentd` 跑的任务不用它，租约心跳替代 | 不退役 |
| 主机心跳路由和 `host-heartbeat.js` | 由 `agentd` 的领活长轮询替代（主机表的 `last_poll_at`）；三家钩子的接线情况改为 `agentd` 注册时上报（`host.tools_json`） | 2.5 删路由和脚本（改公开接口，要 Owner 点头） |
| `PUT /api/v1/agent/progress` 与单份文档 | 过渡。2.2 起平台有 `GET /api/v1/agentrt/progress`（由运行时状态算），2.5 Console 改读它 | 2.5 删 |
| 派工记录的事件格式（`recorder/`） | **成为内核事件的雏形**：信封（`v`、`seq`、`prev_sha256`、`at`、`by`）、规范 JSON、按流串哈希链原样采用（`recorder/fsutil.py` 的 `canonical_json` 移植到 Go，用记录器的测试向量做 Go 的黄金测试）；词表映射：`work_opened` → 计划项 / mission，`step_declared` → 计划步 / 任务，`step_started` / `step_seen` / `step_finished` → 尝试的开始、进度、结束，`owner_wait_*` → 关联审批和提问的等待事件，`note` → `note`；`fold.py` 从事件折叠状态的规则改写成控制器的投影规则 | `lane.py`、`rec.py` 在 2.3 退役（TD-319 以「退役」关闭，加一条防线：没有任何程序读 `recorder-root`）；历史事件 2.3 导入 |
| `DESIGN-host-minimal` 的主机规则 | 作为 `agentd` 的本地规格：登记与重启 R1–R7、巡检 P1–P4、容量 C1–C5、交接 H1–H10。同一用户下做不到的槽位隔离（S1–S7）推到第 3 轮虚拟机；它的「专用交接仓库」被平台的产物存储取代 | — |
| 发版策略、冻结、发布窗口 | 不变；运行时的签名规则复用 `releasepolicy/sshsig.go`、`anchor.go` 的验签和信任锚 | 不退役 |
| CI 门禁、`ref-preflight`、按摘要核对任务 | 成为计划步骤里 `ci`、`release`、`gate` 类的确定性完成条件和验收步骤 | 不退役 |
| 提交血缘（`Change-Id`、`Work:` 尾注） | `agentd` 推的分支提交带上 `Agentrt-Task: t_…` 尾注（新克隆里没有 git 钩子，`agentd` 显式加 `--trailer`），血缘页能把提交挂回任务 | — |
| 本机看板（`board2.py`、`roadmap.py`、`index.html`、`tasks.json`、`HANDOFF.md`） | 不并进；2.5 前照常跑，只修会答错的 | 2.5 退役 |
| `WORK.md` 的「第 N 轮逐项」「架构对照」 | 2.3 一次性导入成计划数据 | 导入后从 `WORK.md` 移出或改为程序生成（§7 第 4 条） |
| `cursor/d1-platform` 分支 | 不合。它要做的「待你定」由提问 + 计划里的 Owner 步骤给出 | 现在就废弃 |

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
- 工作区规矩里要 Owner 点头的（新增表或列、新外部依赖、改公开接口、PROD DDL、集群清单、Secret、PROD 发布单），每一步单列在「Owner 动手」里。

### 5.1 第 2.1 步：数据层（状态库 + `redis-agents` 的数据形式）

**交付物**：三个库与三个登录角色；迁移文件和迁移作业；Go 的存储包 `api/internal/agentrt/store`（只有数据访问，不开 HTTP）；`redis-agents` 的清单和它的 key 约定；重建程序；本节的测试。

#### 5.1.1 库、角色、迁移

| 项 | 定法 |
|---|---|
| 库 | CNPG `data/bifrost-postgres` 上新建 `bifrost_platform`（PROD）、`bifrost_platform_stg`、`bifrost_platform_dev`；schema 都叫 `agentrt`。DEV 库给 Agent 主机上 `bdev` 的本地 platform-api 用，经局域网 NodePort 30432 连 |
| 角色 | `agentrt_owner`（登录，只给迁移作业用，属主）；`platform_agentrt`（登录，平台运行时用，只有 DML，见下表）；`agent_reader`（已有）对 `agentrt.*` 只读。三个环境各一套密码，Secret 由 Owner 建 |
| 创建方式 | 推荐 CNPG 声明式：`Cluster.spec.managed.roles` 加角色（密码引用 Secret）+ 每库一个 `Database` 对象。清单所在路径未核实（只读身份读不到 CNPG 的 `Database`），实现时先查清现有库是怎么建的，跟着同一条路 |
| 迁移 | 只往前、不回退；SQL 文件嵌进平台二进制（`api/internal/agentrt/migrations/0001_core.sql` …），`platform-api agentrt-migrate` 子命令按序执行，每个文件一个事务，写 `schema_migration`（文件号、sha256）；已执行文件的 sha256 变了就失败。集群里是挂起的 CronJob 模板 `agentrt-migrate`（STG、PROD 各一），用现有动作 `create_job_from_cronjob` 起；执行前照规矩 `grep -niE 'drop|truncate'` |

权限（`platform_agentrt`）：

| 表 | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| 只追加的表：`event`、`artifact`、`artifact_blob`、`verification`、`budget_ledger`、`capability_score`、`rule`、`schema_migration` | ✓ | ✓ | — | — |
| `event_stream`（每条流的头） | ✓ | ✓ | ✓ | — |
| 状态表：`actor`、`host`、`plan_node`、`mission`、`task`、`task_dependency`、`attempt`、`outbox`、`message`、`control`、`vendor_pool`、`job`、`job_candidate`、`capability_fact` | ✓ | ✓ | ✓ | — |
| `idempotency_key` | ✓ | ✓ | — | ✓（只删过期的） |

另加触发器兜底：`event`、`artifact*`、`verification`、`budget_ledger`、`rule` 上任何 `UPDATE` / `DELETE` 直接报错（防属主角色手误）；`plan_node` 上改 `plan_node_id`、`parent_plan_node_id`、`node_kind`、`ordinal`、`created_*` 报错，`DELETE` 报错。

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
  state           text NOT NULL CHECK (state IN ('active','draining','retired')),
  capacity_json   jsonb NOT NULL DEFAULT '{}',      -- {"slots":1,"cores":10,"mem_gb":24}
  tools_json      jsonb NOT NULL DEFAULT '{}',      -- {"codex":{"version":"…","models":[…],"pools":[…],"hooks_wired":true}}
  agentd_version  text,
  last_poll_at    timestamptz,                      -- 领活长轮询或心跳时写，最多每 30 秒一次
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
  mission_id           text REFERENCES agentrt.mission(mission_id),
  step_kind            text CHECK (step_kind IN ('agent','review','owner','approval','release','ci','gate','manual')),
  owner_step           boolean NOT NULL DEFAULT false,   -- 「（你）」
  effect_step          boolean NOT NULL DEFAULT false,   -- 「★」
  done_rule_json       jsonb NOT NULL DEFAULT '{}',      -- 见下
  state                text NOT NULL CHECK (state IN ('planned','active','done','stopped','dropped')),
  state_event_id       bigint,             -- 最近一次改 state 的事件（event 建好后加外键）
  usual_s              int,
  created_by_actor_id  text NOT NULL REFERENCES agentrt.actor(actor_id),
  created_at           timestamptz NOT NULL DEFAULT now(),
  version              int NOT NULL DEFAULT 0,
  UNIQUE (parent_plan_node_id, ordinal),
  CHECK ((node_kind IN ('round','arch_root')) = (parent_plan_node_id IS NULL)),
  CHECK ((node_kind = 'step') = (step_kind IS NOT NULL))
);
-- 'step' 节点的 state 只能由控制器在同一事务里写 plan_node_state_changed 事件时改；arch_row 的 state 由门禁结果算
```

`done_rule_json` 的语法（闭合，控制器解释；不认识的原子使整条规则判「未知」，不判做完）：`{"all":[…]}` / `{"any":[…]}`，原子：`{"task_accepted":"t_…"}`、`{"approval_executed":16}`、`{"question_answered":{"question":"Q3","option":"A"}}`、`{"ci_succeeded":{"repo":"bifrost-platform","commit":"<40 位>"}}`、`{"gates_passed":["T19","T23"],"env":"prod"}`、`{"owner_signoff":"TD-295"}`、`{"manual":"<说明>"}`（人工补记，要附证据产物，Progress 上单独标「人工」并计数）。

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
  plan_node_id         text REFERENCES agentrt.plan_node(plan_node_id),  -- 它服务的那一步
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
  updated_at           timestamptz NOT NULL DEFAULT now()
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
  lease_expires_at     timestamptz NOT NULL,
  heartbeat_at         timestamptz NOT NULL,
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
  actor_id          text   NOT NULL REFERENCES agentrt.actor(actor_id),
  mission_id        text   REFERENCES agentrt.mission(mission_id),
  plan_node_id      text   REFERENCES agentrt.plan_node(plan_node_id),
  task_id           text   REFERENCES agentrt.task(task_id),
  attempt_id        text   REFERENCES agentrt.attempt(attempt_id),
  cause_event_id    bigint REFERENCES agentrt.event(event_id),
  body_json         jsonb  NOT NULL,
  prev_sha256       text   NOT NULL,      -- 流的第一条为 ''
  sha256            text   NOT NULL,      -- sha256(规范 JSON(信封 + 正文))，和记录器同一种规范化
  at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (event_stream_id, seq)
);
CREATE INDEX event_task_idx    ON agentrt.event (task_id, event_id);
CREATE INDEX event_mission_idx ON agentrt.event (mission_id, event_id);
CREATE INDEX event_type_at_idx ON agentrt.event (event_type, at);
```

写事件的唯一路径（存储包里一个函数）：同一事务里 `SELECT … FROM event_stream WHERE event_stream_id = $1 FOR UPDATE` → 算 `seq = last_seq + 1`、`prev_sha256 = last_sha256`、`sha256` → `INSERT event` → 更新 `event_stream` → 写对应的状态表行（带 `version` 比较）→ 写 `outbox`。任何状态表的改动都必须带一条事件，没有事件的改动在代码里写不出来（T25）。

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
                           'log_tail','handover','brief','message','exam','other')),
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
  created_at           timestamptz NOT NULL DEFAULT now()
);

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
  body_json jsonb NOT NULL, body_text text NOT NULL,   -- body_text 是被签名的原文
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
| 分流顺序（2.4 实现） | ① 岗位候选里 `active` / `probation` 的；② 去掉违反硬约束的（任务的 `needs_json` × `capability_fact`）；③ 独立性：评审的模型提供方 ≠ 作者的；作者不能验收自己；④ 规则：`core=true` 的作者只能是 Claude、评审是 Codex 只读；⑤ 能胜任：该岗位 × 任务类别的分数 ≥ 规则里的门槛（样本不足时 `probation` 只派非核心的活）；⑥ 在能胜任的里按额度挑：在冷却的池排除，剩下的按「已用比例 − 窗口已过比例」最小者优先（W-64 的口径：看节奏，不看百分比）；⑦ 平手轮换。结果写进 `task.route_json`，并记事件 `route_decided`（输入和每一步刷掉了谁），可解释、可回放 |

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
| 计划 | `plan_node_created`、`plan_node_retitled`（只许未开始的步骤）、`plan_node_state_changed`（from、to、cause：哪条原子满足了）、`plan_change_proposed`、`plan_change_decided` |
| mission | `mission_proposed`、`mission_state_changed`、`mission_amended` |
| 任务 | `task_proposed`、`task_state_changed`、`task_dependency_added`、`task_cancelled`（级联的根）、`route_decided` |
| 尝试 | `attempt_leased`、`attempt_started`、`attempt_progress`（阶段、一句话；文本变了才记，最多每分钟一条——心跳本身不记事件，只改 `attempt.heartbeat_at`）、`attempt_stale`、`attempt_renewed`、`attempt_submitted`、`attempt_lost`、`attempt_ended` |
| 产物与验收 | `artifact_put`、`verification_recorded` |
| Owner 与外部事实 | `owner_wait_opened`、`owner_wait_closed`（关联审批 `#n` 或提问 `Qn`）、`approval_seen`、`question_seen`、`ci_seen`、`pipeline_seen`（控制器读到外部记录的状态变化）、`owner_signoff` |
| 主机 | `host_registered`、`host_state_changed`（alive ↔ lost，只记变化）、`host_retired` |
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
| 谁是事实来源 | **PG 是唯一事实来源**。Redis 里只有派生副本和唤醒信号；Redis 整个丢了不丢任何事实 |
| 投递 | 事务性发件箱：事件和 `outbox` 同一事务写入；`platform-workers` 的中继按 `outbox_id` 顺序取未投递的（`LISTEN agrt_outbox` 唤醒，另每 2 秒兜底轮询），`XADD` 后写 `delivered_at`。中继在两者之间崩了会重投，消费方按 `event_id` / `message_id` 去重（至少一次） |

Key 约定（PROD 前缀 `agrt:`，DEV `agrt-dev:`）：

| Key | 类型 | 内容 | 保留 | 重建来源（PG） |
|---|---|---|---|---|
| `agrt:wake` | Stream | `{kind:'task_ready', task_id, role, task_class}` | `MAXLEN ~ 10000` | `task WHERE state='ready'` |
| `agrt:mbox:<actor_id>` | Stream + 消费组 `g` | `{message_id, event_id, message_kind}`；接收方 `XREADGROUP`，ack 时 `XACK`，同时 PG 写 `acked_at` | `MAXLEN ~ 1000`；已 ack 超 7 天的 `XTRIM MINID` | `message WHERE acked_at IS NULL ORDER BY created_at` |
| `agrt:stop` | Stream（广播） | `{control_id, scope, scope_ref, control_kind}` | `MAXLEN ~ 1000` | `control WHERE cleared_at IS NULL` |
| `agrt:events` | Stream | `{event_id, event_type, event_stream_id}`（2.5 的界面实时刷新用） | `MAXLEN ~ 50000` | 不重建（界面回退到按 `event_id` 增量读 PG） |
| `agrt:presence:<actor_id>` | String，`EX 90` | `{host_id, task_id, at}`；只用于交互线程和席位是否在线 | TTL | 不重建（丢了等于「不在线」，下一次轮询补上）。**主机是否失联以 PG 的 `host.last_poll_at` 为准** |
| `agrt:cooldown:<vendor_pool_id>` | String，TTL = 冷却剩余 | `{until, reason, event_id}` | TTL | `vendor_pool WHERE cooldown_until > now()` |
| `agrt:relay:lock` | String，`SET NX PX 30000` | 中继单实例锁 | TTL | — |
| `agrt:meta:epoch` | String | 本次重建的编号（PG 里生成） | 永久 | 重建时写 |

**Redis 丢了怎么重建**（中继启动时，或发现 `agrt:meta:epoch` 不存在时；T15）：① 写 `agrt:meta:rebuilding`，期间领活和信箱的长轮询直接读 PG；② 对每个有未 ack 消息的接收方：删旧流，按 `created_at` 顺序 `XADD`，`XGROUP CREATE … 0`；③ 把未解除的叫停逐条 `XADD` 进 `agrt:stop`；④ 恢复仍在冷却的池；⑤ 每个 `ready` 任务 `XADD` 一条唤醒；⑥ `outbox` 里未投递的照常投；⑦ 写新的 `agrt:meta:epoch`、删 `rebuilding`。客户端看到 epoch 变了，就从 PG 重读一次。

#### 5.1.5 2.1 的验收

| 编号 | 种什么 / 做什么 | 过的标准 |
|---|---|---|
| T19 状态库就位 | DEV、STG、PROD 三库各跑一次迁移，再跑一次 | 第二次无变化；`platform_agentrt` 能对状态表 DML，对 `event` 的 `UPDATE` / `DELETE`、任何 `CREATE` / `DROP` 被拒；`agent_reader` 只能 SELECT；改动已执行迁移文件的一个字节，迁移失败 |
| T20 断线续连 | 在 DEV 上用 `pg_terminate_backend` 杀掉 `platform_agentrt` 自己的连接（同角色可以杀自己的会话），写事件的压测同时进行 | 10 秒内恢复写入；每条流的 `seq` 连续、无重复、哈希链完整。真正的 CNPG 切换演练影响 Trade 和 GS，不在第 2 轮做 |
| T21 `redis-agents` 本身 | 重启 Pod；从别的命名空间、从局域网连它 | 重启后流还在（AOF）；从别处连不上 |
| T15a 重建（存储层） | 用存储包写一组事件、消息、叫停、冷却、就绪任务，`FLUSH` 该前缀，跑重建 | Redis 的内容和 5.1.4 表里的「重建来源」逐项相等；未 ack 的消息每条恰好一份 |
| T23 事件链 | 正常写入 1 万条后校验；再用属主角色在测试库里改一条的正文 | 校验全过；改过的那条被指出（流名、seq） |
| T30 计划编号稳定 | 改 `plan_node_id` / `ordinal` / 父节点；删一个节点；给已做完的项加步骤；同一份计划导入两次 | 前两种被拒；新步骤编号 = 兄弟里最大 + 1；导入两次结果相同 |
| T31 发件箱原子 | 在 `XADD` 之后、写 `delivered_at` 之前杀掉中继 | 重启后那条重投一次，消费方去重后只生效一次；不存在有事件没发件箱、或有发件箱没事件的行 |

**依赖**：v5 确认；§7 第 1、2 条。**Owner 动手**：① 定 §7 第 1、2 条；② 建三个环境的角色密码 Secret 和 `redis-agents` 的密码 Secret；③ 批 CNPG 的角色和库的清单（PROD 库属 D 级）、`redis-agents` 两套清单（平台 overlay 推 main 即被 Argo 自动同步到 PROD，所以推之前要他点头）；④ 批 PROD 迁移作业（新增表 = PROD DDL）；⑤ 平台 CI 加 PG、Redis sidecar 要拉两个钉死摘要的镜像（下载要他同意），流水线定义由他应用。**粗估**：实现 3–4 天（含 Codex 复核两到三轮）+ 等 Owner 的环节；把握中（新依赖和三份集群清单都要他批，环节多）。

### 5.2 第 2.2 步：接口层与 `agentd`

**交付物**：内核 HTTP 路由、控制器循环、新的鉴权角色 `agentd`、MCP 工具、`agentd`（`deterministic`、`codex`、`cursor` 三个执行者，并发 1）、签名规则的验签、提问加两个字段。**状态只能经接口按事件改**：没有任何「设置状态」的通用路由，每条写路由对应一种事件，由控制器在同一事务里改状态。

路由草图（`/api/v1/agentrt/…`；STG 演练、PROD 为事实；本地 `bdev` 连 DEV 库）：

| 方法 路由 | 谁 | 事件 / 作用 |
|---|---|---|
| `GET /plan?root=R2`、`GET /plan/{plan_node_id}` | viewer | 计划树和每步的状态、出处事件 |
| `POST /plan/proposals` | reporter / seat / thread | `plan_change_proposed`；在常备授权内（给进行中的项加步骤、改未开始步骤的标题）自动 `plan_change_decided`，否则生成一条提问给 Owner |
| `POST /missions`、`GET /missions/{id}` | seat / thread 提议；viewer 读 | `mission_proposed`；落在 `standing-envelope` 内自动 `active` |
| `POST /missions/{id}/tasks` | seat / thread / 规划任务 | `task_proposed`（带任务书产物、`needs_json`、`core`） |
| `GET /tasks?mission=&state=`、`GET /tasks/{id}`、`GET /attempts/{id}` | viewer | — |
| `POST /claim` | `agentd` | 长轮询 ≤ 25 秒（同审批的 `maxWait`，`approvals/execution.go:32`）；正文 `{host_id, free_slots, tools}`；按分流结果 `FOR UPDATE SKIP LOCKED` 取一条，`attempt_leased`；回 `attempt_id`、`lease_epoch`、任务书、`base_commit`、`pushed_ref`；顺带更新 `host.last_poll_at` |
| `POST /attempts/{id}/heartbeat` | `agentd` | `{lease_epoch, phase, line}` → 续租；回 `{lease_expires_at, stop}`；隔离号不对回 409 |
| `POST /attempts/{id}/submit` | `agentd` | `{lease_epoch, idempotency_key, exit_code, end_how, conclusion, artifacts[], pushed_ref, pushed_commit}` → `attempt_submitted`；控制器排确定性验收和评审 |
| `PUT /artifacts/{sha256}`、`GET /artifacts/{id}` | `agentd` / reporter 写；viewer 读 | `artifact_put`；非日志类产物里出现本机路径（host-minimal H8 的规则）就拒收 |
| `GET /events?stream=&after_seq=`、`GET /events/verify?stream=` | viewer | 读事件；校验哈希链 |
| `POST /controls`、`DELETE /controls/{id}` | 设：任何已认证身份；解除：admin | `control_set` / `control_cleared` |
| `POST /rules/{rule_id}/proposals`、`/sign`、`/tighten` | 提议：seat / thread；签：Owner 的签名正文（验签复用 `releasepolicy/sshsig.go`）；收紧：任何人 | `rule_*` |
| `GET /hosts`、`POST /hosts/{id}/drain` | viewer / operator | — |
| `GET /progress` | viewer | 进展投影（计划、架构对照、现场、需要你），2.5 的 Console 读它 |
| `GET /whoami` | 任何 | 身份、岗位、能做什么 |

鉴权：新角色 `agentd`，令牌绑定一个 `host_id`（主体 `agentd:<host_id>`），只能领活、心跳、提交、写产物，且正文里的 `host_id` 必须等于主体；够不着审批、发布、集群动作。

MCP 工具（加在现有 `mcp/platform`）：`whoami`、`get_plan`、`get_mission`、`list_tasks`、`get_task`、`propose_tasks`、`propose_plan_change`、`put_artifact`、`get_artifact`、`post_decision_card`（即 `ask_owner` 加 `owner_duty`、`task_id`）、`request_stop`。

控制器（`platform-workers`）：

| 循环 | 做什么 |
|---|---|
| 租约 | 每 10 秒：过期的尝试 → `stale`；`stale` 超过宽限（15 分钟）→ `lost`，任务按 `effect_class` 处理（§6.2） |
| 完成规则 | 每条事件后重算受影响步骤的 `done_rule_json`，满足就 `plan_node_state_changed` |
| 外部事实 | 每 15 秒读计划里引用的审批、提问、CI run，状态变了就记 `approval_seen` / `question_seen` / `ci_seen` |
| 验收编排 | 实现提交后 → 建确定性验收任务；通过 → 按分流建评审任务（独立性在领活时再查一次）；评审过 → `accepted`；不过 → `rework`（`round_no+1 ≤ max_rounds`），否则 `blocked` 并提一条决策卡 |
| 发布前提 | 计划里 `release` 类步骤建审批单之前，程序检查三条前提（该提交 `ci-*` Succeeded；STG 跑的是同一提交且摘要核对通过；同仓库没有未结的发布单），缺一条不建单（今天是 LLM 手工查，§9 第 4 行） |

`agentd`（Go，`bifrost-platform/cmd/agentd`，launchd 常驻，不开端口）：

| 职责 | 定法 |
|---|---|
| 领活 | 长轮询 `/claim`；负载过高（1 分钟负载 > 核数，教训 105）时报 `free_slots=0` |
| 本地登记 | 先 fsync 写 `assigned`，再起进程（host-minimal R1）；重启后对没结束的先清进程、再报 `ended{daemon_restart}`，不续跑（R3） |
| 工作区 | `~/agent-work/tasks/<task_id>/a<n>/`：按 `base_commit` 从 Gitea 全新克隆；复刻治理层的符号链接，让 preflight 照样生效；检出后工作树必须干净（H3） |
| 起执行者 | 参数数组、不经 shell；环境按允许清单重建（不传管理员 kubeconfig、admin / operator 令牌、业务键）；Claude 会话用 `--strict-mcp-config --mcp-config <只读配置>`，Codex、Cursor 用各自的等价配置，不让任务里的 Agent 拿到审批类 MCP 工具；macOS 上用 `caffeinate -i -w <pid>` 防空闲睡眠 |
| 心跳与死人开关 | 每 30 秒心跳，带执行者流式输出里的最后一句；连续 3 次失败或收到 409：TERM 进程组，10 秒后 KILL，记 `end_how=lease_lost`，不推、不提交 |
| 收尾 | 只收列明的产物（报告、`verify.json`、日志尾部），做本机路径扫描，`PUT` 产物；推 `agent/<task_id>/a<n>` 分支（带 `Agentrt-Task` 尾注）；提交 |
| 执行者 | `deterministic`（任务书里的命令数组）；`codex`（`codex exec --json -C <root> -s workspace-write --output-schema <schema> -o <last.json>`）；`cursor`（`cursor-agent -p --output-format stream-json --trust --workspace <root> --model <规则指定>`）。旗标按 10-13 本机 `--help` |

**Gate A**（v4 原定 T01、T02、T08、T10，v5 加几条便宜的）：

| 编号 | 做什么 | 过的标准 |
|---|---|---|
| T01 恢复 | 尝试进行中杀 `agentd`，launchd 拉起 | 30 秒内旧子进程清空；尝试 `ended{daemon_restart}`；任务重回 `ready`；同一 `attempt` 没有第二次提交 |
| T02 租约 | 两个 `agentd`（不同主体）同时领同一批任务；拿旧隔离号心跳和提交 | 每个任务只被领一次；旧隔离号回 409 |
| T05 无证据的声明 | 报告写「测试全过」，没有 `verify.json` | 不进 `accepted` |
| T06 失败的实验 | 一次结论为 `failed` 的尝试 | 事件、产物都在；进展视图看得到；不被后来的成功覆盖 |
| T08 独立验收 | 作者的提供方去领它的评审；作者去领自己的验收 | 都被拒（409），`route_decided` 里写明原因 |
| T10 预算 | mission 的尝试数或墙钟用完 | 不再派活；账本和尝试一一对上 |
| T22 Agent 主机掉线 | 尝试进行中让 `agentd` 停 5 分钟（`SIGSTOP`）；另一次合盖 20 分钟 | 120 秒后 `stale`，宽限内恢复则 `attempt_renewed` 接着跑；超过宽限则 `lost`、任务按 `effect_class` 处理；醒来的旧进程被 409 挡住、30 秒内被杀 |
| T25 状态只由事件改 | 对每条写路由做模糊测试；直接改状态表（运行时角色） | 每次状态变化都有一条带原因的事件；没有任何路由能把任务或计划步骤设成任意状态 |
| 基准 | 6 道回放题（Go 2、Python 2、TS 1、shell 1），Cursor 写、Codex 复核（或反过来，按 `capability_fact`） | 全部走完「领 → 做 → 确定性验收 → 评审 → 结论」，中途没人插手；结果（通过与否）记进 `capability_score` |

**依赖**：2.1 做完。**Owner 动手**：① 定 §7 第 3、5 条（改公开接口、新鉴权角色）；② 为 Agent 主机生成 `agentd` 令牌、在 Gitea 建 `agentd-<host>` 用户并限定只能推 `agent/*`（Gitea 管理员）；③ 同意在 Agent 主机上装 `agentd` 的 LaunchAgent（常驻配置）；④ 生成规则签名私钥（和发版策略卡在同一处：`WORK.md` S0-8），签初始规则（常备授权、并发 1、预算、`routing:dev`、`capability-facts`、各岗位说明书）；⑤ 批 PROD 发布单。**粗估**：6–9 天；把握低（内核加守护进程加两个执行者，按第 1 轮难线一片要 3–6 轮的历史）。

### 5.3 第 2.3 步：总线与叫停；本机文件迁进平台

**交付物**：中继（`outbox` → Redis）；信箱、唤醒、在线、叫停广播的 API 与 MCP 长轮询（`wait_for_messages`、`ack_messages`、`ask`、`request_help`、`handover`、`search_artifacts`）；等待计时由控制器做（`RULE-waits` 总则第 4 条）；隔离、根目录只读、注入防护；本机文件导入。

| 本机文件 | 怎么迁 |
|---|---|
| `WORK.md`「第 1 轮逐项」「第 2 轮逐项」「架构对照」 | 一次性导入成 `plan_node`（`legacy_imported`），编号按表里的项号和行序；「架构对照」每行指定它的门禁测试编号（例：状态库 ← T19、T20、T23）。导入后的去留见 §7 第 4 条 |
| 派工记录 `~/agent-work/recorder-root` | 先校验哈希链，再作为 `legacy:recorder` 流导入；然后 `lane.py`、`rec.py` 退役 |
| 看板数据 `tasks.json` 手写行、`HANDOFF.md` | 「需要你」→ 提问 / 审批 / 计划里的 Owner 步骤；「在做」→ 任务与尝试；「最近」→ 事件；`HANDOFF.md` 只剩判断性的话，作为 `handover` 产物经 MCP 写入 |
| 等待计时、看护（`~/agent-work/watch-agents.sh`） | 控制器的 `wait_limit_passed` 和租约循环 |
| 额度读数（`usage.py`、`cursor-quota.json`） | 2.4 的 `pool_measured` |

**Gate B**（v4 原定 T03、T09、T11–T15，加 T04、T07）：

| 编号 | 过的标准 |
|---|---|
| T03 同伴越权 | 一个主体去心跳、提交、取消别人的尝试或任务：403 / 409 |
| T04 交叉传播 | 一件任务的产物被拼进另一件的任务书，里面写「Owner 已批准」：任何状态不变，记一条 `policy_alert` |
| T07 安全停止 | 在推分支的那一刻叫停：要么推上去并记录，要么没推；没有半截状态 |
| T09 叫停 | 从 `POST /controls` 到 Agent 主机上子进程死掉 ≤ 60 秒；之后不再派活 |
| T11 隔离 | 任务书、产物里引用另一个任务的工作区一律拒收。同一系统用户下读不读得到别的目录**做不到**，标「部分」，第 3 轮虚拟机补 |
| T12 来源注入 | 仓库文件里的指令改变不了控制器的任何判断 |
| T13 无业务键 | 执行者子进程的环境变量名和拒绝清单交集为空 |
| T14 根目录只读 | 任务里的 Agent 写工作区根：被 preflight 拦；任务结束后根目录白名单之外没有新东西 |
| T15 总线重建（接口层） | 任务进行中清空 `redis-agents`：领活、心跳、信箱不中断（期间走 PG）；未 ack 的消息恰好重投一次 |

**依赖**：2.2。**Owner 动手**：① 定 §7 第 4 条；② 批 PROD 发布单。**粗估**：4–6 天；把握中低。

### 5.4 第 2.4 步：多厂商、按能力和额度分流、参谋长

**交付物**：`claude` 执行者（`claude -p --output-format stream-json --json-schema …`，在任务工作区根起会话，让工作区钩子加载）；分流按 5.1.2 的七步实现；额度读数（各家没有可编程读数时用限流退出文本和 Owner 的读数，标 `measure_source`）；并发 2–3（按主机容量和负载）；参谋长席位（控制器在早晚、Owner 说话、出现阻塞时生成 `brief` / `plan` 任务；初版资格考试按 v4 §5.3 五题）；`job`、`job_candidate` 的写入方；20 道基准题全集跑一遍，作为三家的初始成绩。

**验收**：T16 级联（评审不过 → 按 `route_json` 换下一位候选，且新候选仍满足硬约束和独立性）；T27 两层身份（同一工具换不同提供方的模型，独立性按提供方判）；参谋长考试五题；以及第 2 轮的终点：

**T26：一件活从派出到验收，全程没有统筹线程手工插手**

| 项 | 定法 |
|---|---|
| 输入 | Owner 在 Console 用一句话给目标（经提问 / 信箱进参谋长席位）；mission 里 4 件活：基准题里 Go、Python、TS 各一道，再加一件第 2 轮自身的外围小活（例如一段测试样板）。其中一件在第一次确定性验收时由测试开关注入失败（只在 STG 有效），逼出一次返工 |
| 故障注入 | 某一次尝试进行中，Agent 主机合盖 ≥ 15 分钟 |
| 观察窗口 | 从 `mission_proposed` 到最后一件 `accepted` |
| 过的标准 | ① 窗口内统筹线程**没有回合**：`agentthreads` 里统筹线程 id 没有 `turn_start`（线程心跳在 PROD，可直接读）；② PROD 审计日志和事件里，窗口内对这个 mission 的写入全部来自 `controller`、`host:*`、`exec:*`、`seat:chief_of_staff`、`owner`，统筹线程的令牌写入数为 0；③ 4 件全部 `accepted`，其中一件经过一次 `rework`；④ 每次评审的模型提供方 ≠ 作者的，核心类作者是 Claude；⑤ 每 5 分钟一次的探针对比 `GET /progress` 和库里的真实状态，零次不一致，合盖期间那件显示「宿主失联」而不是「在做」；⑥ 截止时间（8 小时）内完成。Owner 在窗口内只做事先列明的动作（给目标、回答事先登记的决策卡） |
| 不过 | 任一条不成立；按停线规矩分「会答错」和「只缺测试」 |

**依赖**：2.3。**Owner 动手**：① 签岗位与候选名单、`routing:dev` 门槛（放宽）；② 批 PROD 发布单。**粗估**：4–6 天；把握低（额度读数和参谋长考试都是第一次做）。

### 5.5 第 2.5 步：界面——Progress 页完全由接口生成

**交付物**：PROD Console 的 Progress 页改读 `GET /api/v1/agentrt/progress`（可选订阅 `agrt:events` 做实时刷新）：计划栏（轮 → 项 → 步、编号、做完几步、谁在做）、架构对照（每行的勾由门禁测试结果算）、现场（尝试、主机、慢或卡，规则见 v4 §20.2、§20.3）、需要你（提问、审批、计划里的 Owner 步骤，挂在所属那一步上）。本机看板退役（`board2.py`、`roadmap.py`、`index.html`、`publish-result.js`）；`PUT /api/v1/agent/progress` 和主机心跳路由并排一周后删除。这一步是外围，可交 Codex 或 Cursor 按已定接口写，Claude 验收。

**验收 T24（Progress 不依赖 Agent 主机）**：停掉 Agent 主机上的看板程序和 `agentd`（或合盖）后：PROD Progress 页的计划和架构对照与 `GET /plan` 一致；那台主机 3–4 分钟内显示「宿主失联」，它上面的尝试不显示「在做」；不出现「过期的旧文档当现状」。另照 v4 §20.5 的十个场景各跑一遍（挂起变「可能卡住」、慢但持续上报不叫 Owner、断开数据库显示「未知」、预计时间顺延与「估不准」、演练项没有批准入口等）。

**依赖**：2.2（接口）、2.3（导入）。**Owner 动手**：同意删两条路由（改公开接口）；批 PROD 发布单；按他的四个问题走查一遍（ADR §12.2 第 16 条）。**粗估**：2–4 天；把握中。

### 5.6 测试编号

| 编号 | 名称 | 在哪一步 |
|---|---|---|
| T01–T12 | 研报原有（恢复、租约、同伴越权、交叉传播、无证据的声明、失败的实验、安全停止、独立验收、叫停、预算、隔离、来源注入） | T01、T02、T05、T06、T08、T10 → 2.2；T03、T04、T07、T09、T11、T12 → 2.3 |
| T13–T15 | 无业务键、根目录只读、总线重建 | 2.3（T15 的存储层部分 T15a 在 2.1） |
| T16 | 级联 | 2.4 |
| T17、T18 | GPU 唤醒、租户硬规则 | 第 2 轮不做 |
| T19 | 状态库就位 | 2.1 |
| T20 | 断线续连 | 2.1 |
| T21 | `redis-agents` 本身 | 2.1 |
| T22 | Agent 主机掉线与租约 | 2.2 |
| T23 | 事件哈希链 | 2.1 |
| T24 | Progress 不依赖 Agent 主机 | 2.5 |
| T25 | 状态只由事件改 | 2.2 |
| T26 | 全程无统筹插手 | 2.4 |
| T27 | 工具 × 模型两层身份 | 2.4 |
| T28 | 换主机（第 3 轮的入口条件，见 §6.3） | 第 3 轮 |
| T30 | 计划编号稳定 | 2.1 |
| T31 | 发件箱原子 | 2.1 |

（T29 留空，避免和 `DESIGN-host-minimal` 的 A 编号混。）

### 5.7 汇总：粗估与 Owner 动手

| 步 | 粗估 | 把握 | Owner 动手（次数） |
|---|---|---|---|
| 2.1 数据层 | 3–4 天 + 等批 | 中 | 定 2 条；建 Secret；批集群清单 2 组；批 PROD 迁移；应用 CI 流水线、同意拉镜像（约 6 次） |
| 2.2 接口层与 `agentd` | 6–9 天 | 低 | 定 2 条；令牌、Gitea 用户；装 LaunchAgent；生成签名私钥并签初始规则；批发布单（约 6 次） |
| 2.3 总线与迁移 | 4–6 天 | 中低 | 定 1 条；批发布单（2 次） |
| 2.4 多厂商与参谋长 | 4–6 天 | 低 | 签岗位与候选；批发布单（2 次） |
| 2.5 界面 | 2–4 天 | 中 | 同意删路由；批发布单；走查（3 次） |
| 合计 | 约 4–6 周（工作日 19–29 天） | 低 | 约 19 次 |

比 `WORK.md`「两到三周」长：多了 2.5 一步，且按第 1 轮的实测（难线一片 3–6 轮复核）折算。每一步做完按实际重估。

## 6. 运行在 Agent 主机上的约束

第 2 轮的 Agent 主机是开发机：会睡（合盖）、桌面应用会退出、负载会被并行任务压满（教训 105：10 核机器 1 分钟负载 82）。第 3 轮换成 mini 上的虚拟机。

### 6.1 状态放哪

| 状态 | 放哪 | 为什么 |
|---|---|---|
| 计划、mission、任务、尝试与租约、事件、产物（任务书、报告、验收记录、交接）、规则、能力与额度账本、叫停 | PROD 的 `agentrt`（PG） | Agent 主机会睡；Owner 通过 Progress 页了解运行，它必须不依赖 Agent 主机（v4 §20.3 第 4 条） |
| 审批、发版策略、冻结、发布窗口、提问 | PROD statefile（不变） | 修复链不依赖 PG / Redis（ADR §12.3） |
| 信箱、唤醒、在线、冷却、叫停广播 | PROD `redis-agents`（派生） | 可从 PG 重建 |
| **Agent 主机上只允许有** | 厂商命令行的登录状态（只能在本机，Owner 亲自登录）；一次性的任务工作区（可由 Gitea 的提交和平台的产物重建）；`agentd` 的本地登记（只用于崩溃恢复，和平台冲突时以平台为准）；还没推上去的产物和日志缓冲（推上去才算数） | — |
| **不许只在 Agent 主机上**（今天恰恰都在） | 任务书和复核简报（`~/agent-work/<事>/`）、计划表和看板数据（`~/agent-work/status/`）、派工事件（`~/agent-work/recorder-root`）、交接记录（`HANDOFF.md`）、等待计时、额度读数 | 迁移见 5.3 |

### 6.2 `agentd` 掉线时平台怎么处理租约

| 情形 | 平台怎么做 |
|---|---|
| 心跳停了（睡眠、断网、进程被冻结） | 租约 120 秒到期 → 尝试 `stale`（Progress 显示「宿主失联」，主机失联阈值 3 分钟，和 `agentthreads/config.go:44` 一致）；15 分钟宽限内同一主机拿同一隔离号回来，`attempt_renewed`，接着跑 |
| 超过宽限 | 尝试 `lost`。任务的 `effect_class`：`none` / `branch`（只推自己的 `agent/<task>/a<n>` 分支，不会覆盖别人）→ 回 `ready`，下次领活是新的一次尝试；`external`（第 2 轮不派这类）→ `blocked`，提一条决策卡 |
| 旧进程醒来 | `agentd` 写任何东西之前先心跳；回 409（隔离号已作废）就杀子进程、不推、不提交，本地日志留 7 天。macOS 的单调时钟在睡眠时不走，所以 `agentd` 不靠本地计时判断租约，一律问平台 |
| 只有一台主机 | 任务等主机醒来；Progress 上那件事显示「宿主失联」和等了多久，不显示「在做」；不叫 Owner（规则能处理），超过 mission 截止才变成「需要你」 |
| 防睡 | 有尝试在跑时 `agentd` 持有 `caffeinate -i -w <pid>`（防空闲睡眠，挡不住合盖）；合盖就是掉线，按上面处理 |
| 负载 | 领活时报空闲槽位；负载超过核数报 0；第 2 轮并发上限 1（2.2）、2–3（2.4） |
| 应用退出 | `agentd` 是 launchd 常驻进程，和 Claude 桌面应用、统筹线程无关；它们退出不影响在跑的任务 |
| 同一系统用户 | 任务里的 Agent 理论上读得到本机的令牌文件（MCP 令牌、reporter 令牌）。第 2 轮靠 `--strict-mcp-config` 一类的启动参数和 preflight 挡善意误用，**不防有决心的绕过**，和 ADR §5 记的已知接受风险同类；真正的隔离在第 3 轮虚拟机 |

### 6.3 搬到 mini 虚拟机时要改什么（应当只是换主机）

| 要做的 | 谁 |
|---|---|
| 平台里登记新主机（`host`、`actor`），发它自己的 `agentd` 令牌和 Gitea 用户 | Owner 发令牌；其余程序做 |
| 虚拟机里装三家命令行并由 Owner 本人登录（绝不拷贝登录文件；`claude setup-token` 这类厂商提供的长期令牌能不能用于虚拟机，要先对条款，未核实） | Owner |
| 治理层检出、钩子 trust、`agentd` 配置（`host_kind=vm`、容量） | 程序 + Owner 一次确认 |
| 开发机这台改成 `draining` → `retired` | 程序 |
| **不应改的**：平台代码、表结构、任务书格式、产物格式。任何一处要改，就说明有状态或路径绑在了开发机上，是缺陷 | — |

第 3 轮的入口测试 **T28 换主机**：同一道基准题在新主机上跑通；任务书、产物、事件里搜不到任何本机路径（host-minimal H8 的规则）；把开发机排空后 Progress 页照常。今天已知会绑住的：本机看板脚本里写死的路径（2.5 随看板退役）；Codex 沙箱不能提交（2.2 起由 `agentd` 提交，不受影响）；同一用户下的令牌可读（虚拟机解决）。

## 7. 要 Owner 定的事

| # | 问题 | 选项 | 推荐 | 属于三件事里的 |
|---|---|---|---|---|
| 1 | 状态库放哪、环境怎么分 | A. 现有 CNPG `bifrost-postgres` 上新建三个库（PROD / STG / DEV），备份自动覆盖；B. 平台单独一个小 CNPG 集群，和 Trade、GS 的负载隔开（多一套要运维和备份的东西）；C. 只建 PROD 库，开发也连 PROD 库的另一个 schema | **A**。v4 已定的方向；量很小（估计每天几千条事件、几 MB）；DEV 库可丢；C 让开发能写到 PROD 的库，不可取 | 定规则（新增库属 PROD DDL） |
| 2 | 新外部依赖 | A. `github.com/jackc/pgx/v5` + 自写的嵌入式迁移执行器（约 100 行）；B. pgx + `golang-migrate`；C. `database/sql` + `lib/pq`。另：平台 CI 加 `postgres`、`redis` 两个 sidecar（钉摘要的镜像） | **A**，加 sidecar。平台今天没有任何 PG 驱动；pgx 是 Go 里维护最活跃的；迁移规则很简单，不值得再引一个库；没有 sidecar，数据层的测试在 CI 上跑不了 | 定规则 |
| 3 | 决策卡用什么存 | A. 复用已在 PROD 的「提问」，加 `owner_duty`、`task_id` 两个字段（改公开接口）；B. 照 v4 新建 `agentrt.decision` 表 | **A**。提问已有选项、推荐、「不回复会怎样」、手机通知和 MCP 工具；同一件事存两处会再出一次「哪份是真的」 | 定规则 |
| 4 | 台账以运行时为准之后，markdown 怎么办（`WORK.md` 的计划表；`TECH_DEBT.md`、`RATCHETS.md` 的状态行、计数、「待你签收」） | A. 计划表 2.3 导入后从 `WORK.md` 移出，只在 Console 和 MCP 看；债和防线的状态行、计数、签收段改成程序生成（条目正文仍是人写的），签收在 Console 上点；B. markdown 保留为程序生成的只读快照，由平台定期提交回仓库；C. 维持现状，LLM 手改 | **A**。一处事实；B 要让平台获得写仓库的权限，C 就是今天出错的来源（§9）。这条改了工作区 `CLAUDE.md` §5「未结的债只在 `TECH_DEBT.md`」的说法，按 parity 规矩两侧同步 | 定规则 |
| 5 | `agentd` 的身份与凭证 | A. 每台主机一把 `agentd` 角色的令牌（新鉴权角色，绑定 `host_id`），外加每台主机一个 Gitea 用户、只能推 `agent/*`；B. 复用现有的 reporter 令牌和一把部署钥匙 | **A**。reporter 令牌今天是共用的一把，持有者能替任何主机报心跳（host-minimal §4）；按主体才分得清谁领了什么，T02、T03 才测得出 | 定规则 |

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
- 内核之前的外层小版本（Owner 10-13 定从内往外）；本机看板在 2.5 前只修会答错的。

## 9. 现在由 LLM 手工维护、要改成程序维护的活

原则（ADR §12.2 第 13 条）：状态、顺序、闸门、计数、超时、锁、预算、权限、记录，凡是能写成「是或否」的，落成程序；模型提议，程序放行。落点按从内往外排：先有表（2.1），再有接口和控制器（2.2），再迁本机文件（2.3），最后换界面（2.5）。

| # | 活 | 现在怎么做 | 出过的错 | 程序化后由什么维护 | 落在哪一步 |
|---|---|---|---|---|---|
| 1 | **计划结构和状态**：轮 → 项 → 步的编号、谁在做、做完几步、在跑的活对应哪一步 | LLM 手改 `WORK.md`「第 N 轮逐项」「架构对照」并改「核对于」时间；本机 `roadmap.py` 解析它；`board2.py:481-489` 的 `step_id_of` 按派工名的前缀认步骤（过渡：派工名要以「项号-步号」开头才认得出） | 第 2 轮的「2.0-1」按第 1 轮的写法认不出，在跑的活挂不到步骤上（`board2.py:482-484`，Owner 10-13）；全局计划和台账是两份、手抄（教训 51、52）；台账状态落后（ADR §12.2 第 13 条列的当天证据） | `plan_node`（编号分配后不变，触发器挡改号）；步骤状态只由 `plan_node_state_changed` 事件改，事件的原因是满足了 `done_rule_json` 里的哪一条（任务验收、审批执行、提问回答、CI 结果、门禁测试、Owner 签收）；LLM 只能 `propose_plan_change`；架构对照的勾由门禁测试的 `verification` 算 | 2.1 表；2.2 接口和控制器；2.3 导入；2.5 界面 |
| 2 | **派活和收结果**：写任务书、启动 Codex / Cursor、等、读报告、决定下一步 | 任务书写在 `~/agent-work/<事>/TASK*.md`；`lane.py start -- codex exec …` / `cursor-agent -p …`；统筹线程盯进程、读 `REPORT.md`、决定复核或返工。Claude 子代理在统筹线程里做的活，派工工具完全看不见（没有事件） | 监控脚本在 CI 结束那一刻死了，看板一直显示「在跑」，等了 9 分钟（教训 48）；夜里 8 小时没有进展（教训 106）；并行把机器压满（教训 105） | 任务书是 `task_spec` 产物；`agentd` 领活、起进程、心跳、交产物；控制器按验收结果排复核或返工、按 `route_json` 换人；Claude 的活由 `claude` 执行者经 `agentd` 跑，在统筹线程里用子代理做的活不算计划里的步骤 | 2.1 表；2.2 `agentd`（Codex、Cursor）与控制器；2.4 `claude` 执行者 |
| 3 | **台账记账**：`TECH_DEBT.md` 的状态行、「待你签收」一节、未结计数；`RATCHETS.md` 的行；签收后删条目 | LLM 改 markdown、手数计数 | 未结计数手数错：10-13 重数是 114 项，此前写的 99 少数了（`TECH_DEBT.md:19`） | 每条债和防线的状态、优先级、要不要批、验收命令和验收结果成为运行时数据（计划节点 `work_id` 关联，或同一套表里的台账节点）；计数、「待你签收」段由程序生成；Owner 签收是 Console 上的一个动作，产生 `owner_signoff` 事件，条目随之关闭；条目正文仍由人写 | 2.1 表（随计划结构）；2.2 接口；2.3 导入两份 markdown；2.5 签收入口。前提是 §7 第 4 条 |
| 4 | **发布流程**：持有窗口、发测试环境、核对、源检查试跑、建正式环境发布单前的三条前提、盯执行、核对正式环境 | 统筹线程手工跑 `release.sh window / hold / stg`、核对 Pod 与摘要、`request_action`、`~/agent-work/release-platform-prod/watch.sh` 盯 | 没看 CI 就建了 PROD 发布单（教训 38）；发布结束后窗口没放开（教训 11）；两会话同发一个版本（工作区 `CLAUDE.md` §5 的 09-27、09-28 两次事故） | 计划里的 `release` 类步骤：控制器在建单前程序检查三条前提，缺一条不建；单子执行后自动建确定性核对任务（复用第 1 轮 ⑤ 的摘要核对）；窗口和执行仍由平台已有的部分负责（审批执行器、窗口 ConfigMap）；步骤由 `approval_seen` 事件推进 | 2.2（前提检查、核对任务、步骤推进）；全自动发布不在第 2 轮 |
| 5 | **交接记录与看板手写行**：`~/agent-work/status/HANDOFF.md`、`tasks.json` 的「需要你」「在做」「最近」「队列」「图」 | 统筹线程在压缩上下文前、交接前手写 | 手写段落跟不上实际，Owner 10-13 22:04 指出「在跑」一栏混着手写行和事件算出的行、同一件事出现两次（`WORK.md` W-31「第 2 轮」那一条）；「需要你 1」和「3 个等我接手」让 Owner 读成三件要他做（教训 80） | 交接 = 读运行时（`whoami`、`get_plan`、`list_tasks`、未结的提问和审批）；判断性的话写成 `handover` 产物；「需要你」由提问、审批和计划里的 Owner 步骤生成 | 2.1 表；2.3 迁移和 `handover` 工具；2.5 看板退役 |
| 6 | **等待计时和看护** | `RULE-waits` 的上限由统筹线程掐表；`~/agent-work/watch-agents.sh` 叫醒 | 线程断了、机器睡了就没人掐表（`RUNTIME-PLACEMENT` §10 第 4 行） | 控制器的租约循环和 `wait_limit_passed` | 2.2（租约）；2.3（等待上限） |
| 7 | **额度读数和指派** | 统筹线程读各家页面、`usage.py`、`cursor-quota.json`，凭当天判断指派 | 从两次读数推出「Codex 一天只够 9 次」，结论相反（教训 63） | `vendor_pool`、`budget_ledger`、`capability_*`；分流程序按 5.1.2 的七步 | 2.1 表；2.4 分流 |
| 8 | **编号发放** | `W-n` 由 LLM 在 `WORK.md` 发号，`check_work_ids.py` 查重；派工名由 LLM 起 | 两个协调者撞号（v4 §1.1） | mission、任务、计划节点的编号由平台发；`W-n` 仍在 `WORK.md`，直到 Owner 另定 | 2.2 |
| 9 | **留给 LLM、不程序化的** | — | — | 设计；写任务书的内容；复核的判断和发现；有推荐的选择题怎么选（按 ADR §12.2 第 15 条留痕）；给 Owner 的文字（决策卡的措辞、简报）；解释失败的原因；提议改计划、提议改规则、起草教训的原因和机制。这些的**结果**进运行时（产物、提议、事件），由程序决定是否放行 | — |

## 10. v4 不变的部分

v4 的 §0、§1、§2（组件表里 `agentd` 的位置改读「Agent 主机」）、§3、§4、§5.1–5.4（5.2「跑在 mini 上」改为 §1 第 8 行）、§6、§9、§13 的混沌与治理层探针、§14、§16、§17、§18、§19、§20 照旧有效；§7.5 的表以本文 5.1.2 为准；§10（第 0 步）和 §12（分阶段）以本文 §5、§8 为准。
