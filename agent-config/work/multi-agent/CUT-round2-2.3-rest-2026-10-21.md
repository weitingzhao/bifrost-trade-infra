# 切法：2.3 剩下的部分（Gate B 其余项、本机文件迁进平台）

起草 2026-10-21（侧线，统筹线程 `local_accccb4e…` 派）。依据：设计 v5 §5.3（交付物、本机文件怎么迁的表、Gate B 十项）、`PLAN-round2-2.3-first-slice-2026-10-18.md` 第 27 行、`WORK.md` 2.3、`CUT-gate-b-2026-10-19.md`、`RUN-r2-stars-2026-10-20.md`、`RULE-waits-2026-10-12.md`、PROD / STG 的 `GET /plan` 与问题列表（10-21 12:2x 读）。

**一句话**：Gate B 七项（T03、T04、T07、T11、T12、T13、T14）都已在平台主线，有测试，T04、T11、T13 有 STG 与 PROD 实测，PROD 计划里 `R2:2.3-6`（★ Gate B）已是 done；**还没做完的都在 `R2:2.3-3`**：控制器的等待计时（`wait_limit_passed` 没有写入方）、交互线程和席位的在线、`search_artifacts`、记录器导入真正落到 STG / PROD 和 `lane.py` / `rec.py` 退役、`WORK.md` 第 2 轮表换成指针。其中只有等待计时不碰接口，本线已实现（§4）；其余要么是新路由 / 新读面（§3 等 Owner 定），要么是统筹线程和 Owner 的动作（§2 片 4、片 5）。

## 1. 核对表（只读，10-21 12:0x–12:3x，平台主线 `e98b1487`）

「做完」= 代码在主线 + 有测试 + 设计要求的实测有记录；「部分」= 缺其中一样或只覆盖一半；「没做」= 主线上没有。测试一栏是本线 10-21 在 `e98b1487` 上重跑的结果（`go test -count=1 -v`，带 PG 55432、Redis 56379、`AGENTRT_TEST_REQUIRED=1`，22 个测试全过；输出 `~/agent-work/w31-23-rest/gateb-tests.txt`）。

### 1.1 Gate B 七项

| 项 | 结论 | 证据 | 还差 |
|---|---|---|---|
| **T03 同伴越权** | **做完**（按 Owner 10-19「Gate B ① A」的理解：尝试路由；叫停不在内） | 主线 `ee4ad276`（只加测试）；`TestPeerReachesNoOtherAttempt`（`agentrtapi/peer_test.go`）：别的主机的 agentd 令牌打 8 条尝试路由，写持有者主机 → 403 `wrong_host`，写自己主机 → 409 `fenced`，非 agentd 令牌 → 401，一个事件不写、持有者照常心跳；存储层 `TestFenceAndLeaseClock`、`TestEnded`、`TestSalvage`。切法 `CUT-gate-b-2026-10-19.md` 第 14 行 | 没有专门的 STG 实测（设计没要求；路由同一份代码） |
| **T04 交叉传播** | **做完** | 主线 `148e421b`、`1eebd54b`；`TestCrossPropagationChangesNothing`、`TestApprovalClaimInAMessage`、`TestApprovalClaimPhrases`（`store/claims_test.go`）。实测：`RUN-r2-stars-2026-10-20.md` 第 126 行（STG M-26，事件 2125 `policy_alert`，任务照常 accepted）、第 128 行（PROD M-13，事件 1543） | 短语表是绊线，换说法就漏（切法 gate-b 第 15 行 ②）；真正的防线是 T12 |
| **T07 安全停止** | **做完**（本机 bare 仓库） | 主线 `021b84d0`、`93f5eae8`；`TestAStopDuringThePush`（`agentd/safestop_test.go`）：推送卡在 pre-receive 钩子时叫停，放行 → 远端分支 = 平台记的提交、submitted；拒收 → 两边都没有提交 | Gitea 真推送由 T22 ④ 的 STG 走查覆盖（Gate A），不单独再量 |
| **T11 隔离** | **做完到设计写的「部分」** | 主线 `80caed0a`…`8196672c`（复核 340–343 收线）；`TestWorkspaceRef`、`TestWorkspaceRefRefused`、`TestUploadNamingAWorkspace`、`TestHandedInVerifyNamesNoWorkspace`、`TestHandInWithholdsAnotherTasksWorkspace`。写墙（TD-371，主线 21 个提交，`TECH_DEBT.md` 第 32 行「待你签收」PASS 10-19）：06 探针 `confine-probe-stg-20261019T103613`、`T113354` 墙的 11 项全过。实测：`RUN-r2-stars` 第 124、125 行（STG、PROD 各 422 `workspace_ref`、库里无此产物） | 读的隔离、推别的尝试的分支、逃出进程组、同用户令牌是 §7 第 7 条 ② 的第 2 轮例外（第 3 轮虚拟机）；macOS 没有墙；codex 不在 agentd 的墙里（Owner 10-19 选 A） |
| **T12 来源注入** | **做完**（控制器一侧） | 主线 `148e421b`、`93f5eae8`；`TestRepositoryInstructionsChangeNoDecision`（差分：注入文字下任务流转、路由、租约、判定逐条相同）、负对照 `TestAliasesKeepRowsApart` | 评审 LLM 读了仓库后写「VERDICT: pass」是 LLM 层的注入，不属于控制器的判断，防线是「先确定性验证、评审与作者不同提供方」（切法 gate-b 第 19 行残留） |
| **T13 无业务键** | **做完**（按 Owner 10-20 11:5x「★ 三条 A」的口径：agentd 交给执行者的环境） | 主线 `3c4fcf65`；`TestBusinessKeys`、`TestNoExecutorSeesABusinessKey`（`agentd/businesskeys_test.go`）。实测：`RUN-r2-stars` 第 127、129 行（STG、PROD 确定性验收 11 个名字交集 0；codex 自己加的 `GIT_PAGER` 按口径 A 不算，第 168 行） | 无 |
| **T14 根目录只读** | **做完**（按 Owner 10-19「Gate B ② A」改定的标准） | 主线 `7199e43a`；`TestAWalledAttemptLeavesTheRootAsItWas`（`agentd/rootwall_linux_test.go`）。本线 10-21 在本机 Docker 的 Linux 内核（Landlock ABI 6，本机已有的 `busybox:latest`，`--network none`）里重跑：它和 `TestWallHolds`、`TestSetupWallKeepsTheExecutorsHome` 都 PASS（`~/agent-work/w31-23-rest/linuxtest/rootwall.txt`）。06 上的证明是 TD-371 的探针（同 T11） | v5 §5.3 T14 那一行已按 ② A 改写，不再写「被 preflight 拦」 |

另三项（不在这次点名里，顺带核过）：T09 做完（STG 19.65 秒、PROD 22.18 秒，`RUN-r2-stars` 第 130 行；`TestAStopReachesTheTasksChecks` 等重跑过）；T15 接口层做完（`TestBusWipedMidTask`）；T32（经导入）做完到代码（`TestPlanImportCounterExamplesThroughTheRoute`、`TestRecorderImport*` 四个重跑过），记录器那一半没在 STG / PROD 跑过（见 1.3）。

### 1.2 2.3 的其余交付物（设计 v5 §5.3 第 739 行）

| 交付物 | 结论 | 证据 / 还差 |
|---|---|---|
| 中继和重建接进 `platform-workers` | **做完** | 第一版 ①（`PLAN-round2-2.3-first-slice` 第 17 行）；T21、T31 在 STG / PROD 实测（`RUN-r2-stars` 2.1-11） |
| 信箱（`POST /messages`、`GET /messages?wait=`、`POST /messages/ack`） | **做完** | `agentrtapi/messages.go`；长轮询按 PG 每秒查一次，Redis 信号不参与正确性（设计 5.1.4 的「流只报信」） |
| 唤醒 | **做完** | `relay.go:205` `wake` 流；领活和信箱都以 PG 为准 |
| 叫停广播 | **做完** | `relay.go:207` `stop` 流 + 心跳回答 `stop`；T09 两环境实测 |
| 在线 | **部分** | 主机在线按 `host.last_poll_at`（`store/progress.go:719`）做完；**交互线程和席位的 `agrt:presence:<actor>`（设计 5.1.4 第 632 行）没有写入方也没有读面** → §3 第 2 条 |
| MCP：`wait_for_messages`、`ack_messages` | **做完** | `mcp/platform/src/registerMessages.ts` |
| MCP：`ask`、`request_help`、`handover` | **部分（按语义做完）** | 一个 `send_message` 工具带 `kind`（ask / help / handover / note / answer），设计里是三个具名工具；`handover` 的产物 = `put_artifact`（kind `handover`，`api.go:487` 已收）+ `send_message`（kind `handover`）两步。本线判断：不再加三个别名工具（同一条路由、多三个名字，复核和 Console 的工具目录都要跟着改，没有新的业务能力）；要加由统筹线程一句话定 |
| MCP：`search_artifacts` | **没做** | 没有按种类 / 任务 / 作者列产物的路由（只有 `GET /artifacts/{id}`）→ §3 第 1 条 |
| 等待计时由控制器做（`RULE-waits` 总则第 4 条） | **部分 → 本线补** | Owner 一侧的等待已由 2.4 ④ 的 `Nudges`（`store/briefdue.go:96`）计时并经参谋长告诉他（被卡住的任务立刻，mission 和决策卡 2 小时）；租约循环管主机失联（2.2）。**Agent 一侧的等待（尝试超时、就绪没人领、线程没来收信）没人计时，`wait_limit_passed` 在词表和库的约束里却没有写入方**（`store/vocab.go:47`、`migrations/0006`）→ 片 1，已实现（§4） |

### 1.3 本机文件迁进平台（设计 v5 §5.3 第 742–747 行）

| 本机文件 | 结论 | 证据 / 还差 |
|---|---|---|
| `WORK.md`「第 2 轮逐项」 | **做完（导入）／没做（换指针）** | PROD、STG 都有 `R2`（PROD 卡 #4，10-20 04:02Z 落地；`get_plan`）。`CUT-plan-import` §5 第 7 步「同一个 infra 提交里把第 2 轮逐项换成一行指针」没做：`WORK.md` 第 470–500 行仍是整张表，`RUN-r2-stars` 第 4 行称它为快照；本机看板的计划栏仍读它（2.5 片 ② 未做）→ 片 5 |
| `WORK.md`「架构对照」 | **做完（导入）** | PROD 卡 #9（ARCH，17 行），STG 同；勾由门禁求值是 2.5 片 ⑤ |
| `WORK.md`「第 1 轮逐项」 | **没做** | 设计要求导入，`CUT-plan-import` 的范围只写了第 2 轮，没有说第 1 轮不导；PROD / STG 都没有 `R1` → §3 第 3 条 |
| 派工记录 `~/agent-work/recorder-root` | **部分** | 导入入口在主线（`8ef61666`：`POST /plan/imports` 收 `agentrt.recorder_import/v1`、一张卡、落成 `legacy:recorder:<work>`；`agentrt-plan-import recorder`）。本线 10-21 用主线的工具对本机 17 份日志各生成一次请求：1108 条、哈希链全部成立、66 条要掩本机路径（`~/agent-work/w31-23-rest/recorder-req/`，只在本地，没提交）。**STG、PROD 都没导过**：PROD 问题 #1–#20 里没有记录器导入卡；`td393-stg-acceptance` 笔记第 20 行「没在 STG 造」；`WORK.md` 第 491 行「请求格式等你确认」至今没有回复。`lane.py`、`rec.py` 没退役。另：`_observer/`（看板观察轮次，按天一份，今天仍在写）不在导入工具的范围（工具只读 `<work>/events.jsonl`）→ 片 4 |
| 看板手写行 `tasks.json`、`HANDOFF.md` | **部分** | 「需要你」只来自有入口的条目（2.5 片 ③，主线 `6ca64b97`）、「在做」「最近」来自运行时（2.5 片 ④，`82f96fc2`）。看板 `board2.py` 仍在跑、每 15 秒推 PROD；`tasks.json` 的 `works` 手写行（29 行）今天 11:11 还在改；`HANDOFF.md` 10-15 后没再写。`handover` 产物可经现有两个工具写（1.2）。看板退役是 2.5 片 ⑤（T24），不在 2.3 |
| 等待计时、看护 `watch-agents.sh` | **部分 → 本线补** | 租约循环（2.2）做完；`wait_limit_passed` 见 1.2 最后一行 |
| 额度读数 `usage.py`、`cursor-quota.json` | **做完（在 2.4）** | 2.4 片 ①：`pool_measured`、`GET /agentrt/pools`、`POST …/reading` |

## 2. 切片

| 片 | 做什么 | 谁 | 改哪些文件 | 验收 | 估时 |
|---|---|---|---|---|---|
| **1 等待计时**（设计范围内，**本线已实现**，§4） | 控制器每一遍按 `RULE-waits` 的上限给运行时自己知道的三种等待计时，越过上限记一条 `wait_limit_passed`（每段等待只记一次）；History 时间线显示它 | 本线（Claude 写，Codex 复核） | `api/internal/agentrt/store/waits.go`（新）、`store/vocab.go`（正文登记）、`controller/controller.go`（接进 facts 那一遍）、`console/src/pages/shell/progress/timelineModel.ts`（时间线一行）及各自的测试 | `store/waits_test.go` 的各条（§4）；`timeline.test.tsx` 加一条；整套 Go、Console 四项、MCP、code-health | 实现与测试约半天；复核两轮约半天 |
| 2 `search_artifacts` | 按种类 / 任务 / mission / 作者 / 时间列产物的元数据，MCP 同名工具 | 等 Owner 定（新路由），定了由本线或统筹线程派 | `agentrtapi/api.go`（路由）、`store/artifacts*.go`、`actions/coverage.go`、`mcp/platform/src/*`、Console 工具目录 | 接口测试：只回元数据不回正文、分页、读权限同 `GET /artifacts/{id}`；MCP 测试 | 选 A 约半天加复核 |
| 3 在线（presence） | 交互线程和席位的在线 | 等 Owner 定（读面是改公开接口） | 视选项 | 视选项 | 选 B 约半天加复核；选 A 0 |
| 4 记录器导入落地、`lane.py` / `rec.py` 退役 | ① Owner 确认请求格式（`agentrt.recorder_import/v1`，10-19 夜就在等）；② 统筹线程在 STG 对 17 份日志各提一次（`agentrt-plan-import recorder` 生成到 `~/agent-work/plan-import/`，MCP `propose_plan_import`），STG 的卡按已签的 card-auto-answer 规则或手工答；核 `legacy:recorder:<work>` 流条数与本地相同；③ PROD 同一批请求，Owner 在 Console 答 17 张卡（或先合并成一张，见 §3 第 4 条）；④ infra 一个提交删 `lane.py`、`rec.py`，`agent-config/scripts/recorder/STATUS.md` 写去向 | 统筹线程 + Owner | 不改平台代码；④ 改 infra 的 `agent-config/scripts/recorder/` | STG、PROD 各 17 条流、1108 条事件、哈希链 `VerifyStream` 过；同一份再提一次回「已导入」（T32 经导入的「两次相同」在真库上） | 统筹线程约 1 小时；Owner 两次（确认格式、PROD 答卡） |
| 5 `WORK.md` 第 2 轮表换指针 | `CUT-plan-import` §5 第 7 步：表换成一行指针（Console / `GET /plan?root=R2`、导入时间、请求摘要）。前提：本机看板的计划栏改读接口（2.5 片 ②），否则看板的计划栏会空 | 统筹线程（在 2.5 片 ② 之后） | infra `agent-config/WORK.md` | 看板计划栏改读接口后与导入前逐步相同；`WORK.md` 不再有第 2 轮表 | 半小时，挂在 2.5 片 ② 后 |
| 6 简报读等待（后续） | 早晚简报的数据里加「上一槽以来越过上限的等待」（`RULE-waits` 总则第 5 条） | 和参谋长考试线协调后做 | `store/briefdue.go` 的数据和说明 | 简报测试 | 约 2 小时；**先问考试线**：改简报说明会改考试题的任务书（`exam/render.go` 用同一个函数），考试线 `chief-exam-s5` 按提交记任务书摘要 |

不做的（写明理由）：`ask` / `request_help` / `handover` 三个别名工具（1.2）；记录器的 `_observer/`（看板的观察轮次，随看板在 2.5 退役；要留就整目录作为一个 `other` 产物归档，不逐条导入）。

## 3. 要 Owner 定的（每条 2–3 个选项和推荐）

1. **`search_artifacts`（新路由）**。设计 §5.3 的交付物里点了名，没有定形状；交接（`HANDOFF.md` → `handover` 产物）要靠它找「最新的一份交接」。
   - **A（推荐）**：`GET /api/v1/agentrt/artifacts?kind=&task=&mission=&author=&since=&limit=`（read 角色），只回元数据（号、种类、作者、任务、时间、大小、媒体类型），正文仍按号用 `GET /artifacts/{id}` 读；按时间倒序、游标分页、`limit` ≤ 100。MCP `search_artifacts` 同参数。不加表列（`artifact` 表已有这些列，必要时加一个索引，走迁移）。
   - B：不加路由，只做 MCP 工具，在 MCP 里拼现有路由（`list_tasks` → `get_task` → 产物号）。找不到不挂任务的产物（消息正文、交接），交接这条用不上。
   - C：第 2 轮不做，交接改成「发给下一位的 `handover` 消息」，接手的线程读信箱即可；`search_artifacts` 挪到第 3 轮。
2. **交互线程和席位的在线（presence）**。设计 5.1.4 定了 Redis 键 `agrt:presence:<actor>`（90 秒过期），没定谁读、在哪显示；席位在第 2 轮是任务形态（不常驻），线程的存活另有 `agentthreads` 心跳（T26 就是读它）。
   - **A（推荐）**：第 2 轮不做 presence，在设计 §5.3 写明：线程在线看 `agentthreads`，席位第 2 轮不常驻（v5 §1 第 8 行），主机看 `last_poll_at`；presence 随第 3 轮常驻席位做。
   - B：照设计做：线程长轮询 `GET /messages` 时写 presence，`GET /progress` 加 `presence`（线程和席位，缺了写「未观测到在线」）。改 `/progress` 的回答（加字段）。
   - C：只给参谋长页：`GET /messages/thread` 的回答加对方的 presence。
3. **`WORK.md`「第 1 轮逐项」导不导**。设计 §5.3 写了导，`CUT-plan-import` 只做了第 2 轮；第 1 轮早已收尾。
   - **A（推荐）**：不导，在设计 §5.3 写明第 1 轮留在 `WORK.md` 作历史（全部做完、没有在跑的活挂在上面，导进来只多一棵做完的树）。
   - B：照第 2 轮的办法导（生成器要支持第 1 轮的写法，先在本机测试库对账），一张 Owner 卡。
4. **记录器导入的请求格式与卡数**（片 4 ①）。
   - **A（推荐）**：认可 10-19 的格式 `agentrt.recorder_import/v1`（一份日志一个请求、一张卡），PROD 17 张卡由他一次答完；STG 由已签的卡规则答。
   - B：格式照旧，但先加「一张卡导多份日志」（改请求格式，要再复核一轮），PROD 只答一张。
   - C：不逐条导入，17 份日志验过哈希链后各作为一个 `other` 产物归档（设计 gate-b §2 第 3 条的 C），`lane.py` / `rec.py` 照样退役；丢掉按事件查。

**本线按推荐先走、事后可撤的一条判断**（不改接口）：等待越过上限只记事件、在 History 上显示，**不推手机、不发给参谋长**。理由：Owner 一侧的等待已由 `Nudges` 经参谋长告诉他；Agent 一侧「慢但持续上报不叫 Owner」（v4 §20.5 的场景），发给参谋长会为每一次超时起一件简报任务。要叫人（发给派活的线程、或推手机）是后续一句话的事：`calls` 已在事件正文里。

## 4. 片 1 的实现（等待计时）

### 4.1 规则（`RULE-waits` 第 2 节的表，落到运行时自己的事实上）

| 等待（`wait`） | 运行时里是什么 | 从几点起（`since`） | 上限（`limit_s`） | 叫谁（`calls`） |
|---|---|---|---|---|
| `attempt_running`（第 1、2 类） | 在跑的尝试（`attempt.state = 'running'`，有 `started_at`）；`stale` 的由租约循环管，不计 | `started_at` | 2 × 通常时长，不少于下限：实现 / 计划 / 其他 30 分钟，验证 / 评审 / 简报 20 分钟。通常时长先取任务书写的（`task.usual_s`），没有就取这类任务 30 天里被采纳的尝试的中位数（≥ 3 个样本，和 Progress 的「通常」同一个算法），都没有就只用下限（`basis` 写明是哪一种） | 派这件活的一方：验证 / 评审取被验那件任务的提议者；提议者是控制器时取 mission 的提议者 |
| `task_ready`（第 7 类） | 就绪、没人领的任务，它的 mission 在跑，且没有生效的全局 / mission / 任务级叫停或暂停 | 最近一次进入 `ready` 的事件时间 | 同上，下限 30 分钟（「排在前面那件的通常时长 × 2」简化为它自己这一类的通常时长 × 2） | 同上 |
| `message_unread`（第 3 类） | 发给交互线程（`thread:*`）、还没 ack 的消息 | 消息的 `created_at` | 10 分钟 | 那个线程 |

- 每段等待（`wait` + 被等的号 + `since`）只记一次；等待结束后再开始的是新的一段。
- 一遍每种最多记 20 条，余下的下一遍记（不一下涌出一片）。
- 事件：类型 `wait_limit_passed`、写入者 `controller`，都记在自己的 `waits` 流上，事件行带 mission、任务、尝试号（消息的有就带）。**不放在 mission 流上**：事件表的外键在提交时才核（`DEFERRABLE INITIALLY DEFERRED`，提交时对被引用的行加 KEY SHARE），而启动、检查点、提交这些路径是先 `FOR UPDATE` 锁尝试行、再追加 mission 流；记录若先锁 mission 流，两边互等，本机实测 `deadlock detected`（`TestARecordWaitsForNoMissionsStream` 在旧写法上 40P01）。正文：`wait`、`ref`（尝试 / 任务 / 消息号）、`since`、`limit_s`、`basis`（`task_usual` / `history_usual` / `floor`）、`waited_s`、`calls`，以及有通常时长时的 `usual_s`。
- 第 4、5、6 类（等 Owner、等外部）不在这里：Owner 的已由 `Nudges` 计时；外部的第 2 轮没有运行时事实（SPEC §4）。
- 什么都不改：不动任务、尝试、消息的状态，不发消息，不推通知。

### 4.2 实现记录

分支 `w31/23-rest`（worktree `~/agent-work/w31-23-rest/bifrost-platform`，基于主线 `e98b1487`），三个提交：`be5c606c`（实现）→ `5bfad839`（复核 474）→ `0c7ef6cd`（复核 475 的两条 C），头 `0c7ef6cd`，可干净合入当前主线。

| 文件 | 改了什么 |
|---|---|
| `api/internal/agentrt/store/waits.go`（新） | `WaitLimits(ctx, db, now)`：三条查询（上限在 SQL 里算：`GREATEST(floor, ceil(2 × usual))`，`basis` 同时算出），每种一遍最多 20 条、最早的先；`recordWait` 在 `waits` 流的锁下再核一次再写 |
| `store/vocab.go` | `wait_limit_passed` 的正文（`wait`、`ref`、`since`、`limit_s`、`basis`、`waited_s`、`calls`、可选 `usual_s`）和取值校验；`ref` 的前缀必须和 `wait` 对上（`a_` / `t_` / `m_`） |
| `controller/controller.go` | `Waits`：facts 那一遍的最后一步，读 `Now` |
| `console/…/progress/timelineModel.ts`、`ProgressTimeline.tsx` | History 多一种行「Waited past limit」：什么在等、等了多久、上限多少、叫谁、上限从哪来 |

测试：`store/waits_test.go` 六条（过上限才记且只记一次、再次就绪是新的一段；上限取任务书的 / 历史的通常时长、检查的下限 20 分钟；被叫停或暂停、mission 不在跑的不计，解除后从原来的时刻算；线程没收的信 10 分钟、已 ack 的和超过一周的不计；四个并发的 pass 只记一次；和持有尝试行的事务不死锁）、`vocab_values_test.go`（取值和 ref 前缀）、`agentrtapi/waits_test.go`（经 `GET /events` 读出，并生成 Console 夹具 `agentrt-events-waits.testdb.json`）、Console `timeline.test.tsx`（三种行和两种上限来源、不认识的等待也显示）。变异（每个都确认测试变红后改回）：去掉叫停判断、去掉「mission 在跑」、去掉锁下复核、去掉信的期限、系数改 1、检查的下限改 30 分钟、`calls` 只取 mission 的提议者、已 ack 的也算、记录放回 mission 流。

门禁与复核结果见 §5。

## 5. 门禁与复核

**复核**（Codex，目录 `~/agent-work/codex-review-47{4,5}`）：

| 轮 | 对象 | 结论 | 处理 |
|---|---|---|---|
| 474（第 1 轮） | `e98b1487..be5c606c` | 可以合并；0 A、4 B、4 C：B1 去重查询随记录永久增长（建议加表达式索引）；B2 提交失败仍计数；B3 这一步没有时限，持锁时能拖住 facts 那一遍；B4 七个边界没有测试。C1 History 用现在时、1801 秒和 1800 秒都显示 30 min；C2–C4 接受（信的一周期限、`calls` 落到 mission 提议者、不计 leased） | `5bfad839`：B1 不加索引（索引是 DDL，要 Owner），改为按事件时间收窄、走已有的 `(event_type, at)`；B2 只计提交成功的；B3 整步 30 秒、每个事务 `lock_timeout 5s`；B4 四个新测试；C1 过去时、精确到秒 |
| 475（第 2 轮） | `be5c606c..5bfad839` | **可以合并**；474 四条 B 全关，0 A、0 B、2 C：C1 一小时以上仍省掉秒；C2 运行中的尝试没用任务自带的通常时长测边界、没显式测微秒 | `0c7ef6cd` 顺手改，各配在错误写法上变红的测试；**按停线规矩（两轮）收线**，没再起复核 |

每一处修复都做了变异（改回错误写法、测试变红、再改回）：提交失败计数、去掉锁时限、两处时间下界方向反了、运行中的查询丢掉任务自带的通常时长、`since` 截到秒。

**门禁**（本机 PG 17 `55432`、Redis `56379`、`AGENTRT_TEST_REQUIRED=1`；每项退出码存在 `~/agent-work/w31-23-rest/gates-<提交>/`，没有经管道接 `&&`）：

| 头 | go build | go test ./... | golangci-lint（新增，对 origin/main） | 同上，`GOOS=linux` agentd | Console lint / type-check / test / build | MCP `npm test` | code-health |
|---|---|---|---|---|---|---|---|
| **`0c7ef6cd`（最终）** | 0 | **0**：74 个包全过（含 agentd 215 秒） | 0 条 | 0 条 | 0（0 error，5 个原有 warning）/ 0 / 0（161 个文件 1555 个测试）/ 0 | 0（122 个） | OK（800 行以上 12 / 12） |
| `5bfad839` | 0 | 1：只有 agentd 四个起测试库的测试，见下 | 0 条 | 0 条 | 全 0（1555） | 0（122） | OK |

`5bfad839`（以及更早一次）的 agentd 四个失败（`TestTestDBStage`、`TestTestDBStageEndsWithItsGroup`、`TestAKilledStageIsSweptUp`、`TestAPlatformAttemptHasATestDatabaseOfItsOwn`）是本机环境：`initdb` 报 `could not create shared memory segment: No space left on device`，本机 `kern.sysv.shmmni = 32`，当时 `ipcs -m` 32 个段全被别的线的测试库占着；本分支没有改 agentd 的任何文件。最终头那一次共享内存空出来了，同一包 215 秒全过。

另：Gate B 测试在主线 `e98b1487` 上的重跑见 §1 开头；T14 的 Linux 测试本机 Docker 重跑见 §1.1。
