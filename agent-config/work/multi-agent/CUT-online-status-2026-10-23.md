# 切法：3.5 在线状态（主机掉线、执行者不可用，1 分钟内说出来）

起草 2026-10-23（侧线，只读调查）。依据：`WORK.md` 3.5（第 541–545 行，★「主机掉线或执行者不可用时，Console 和参谋长简报在 1 分钟内说出来」）、`PLAN-round3-draft-2026-10-22.md` 第 99 行、设计 v5 §3 第 101 行、§5.1.2 第 213–217 行、§5.1.4 第 632 行、§5.3 第 742 行、`CUT-round2-2.3-rest-2026-10-21.md` §3 第 2 条（Owner 10-21 定 A：presence 挪到第 3 轮）、`PLAN-T24-stg-2026-10-21.md`。代码读的是 platform main `c5ad80c2`；实测是 10-23 19:0x–19:34Z 的 STG、PROD platform-api 日志（只读 `kubectl logs`）。

**一句话**：主机「在线」今天只在读的时候按 `last_poll_at` 现算，门槛 3 分钟，只有 Console 的 Crew 卡和 Progress 页看得到；没有「从在线变离线」这一刻，所以参谋长、Chief 页、For you 都不会说。执行者只有额度冷却平台知道，「哪台主机提供什么」平台收到了但不存。到「1 分钟」差三样：门槛降到 30 秒、存下每台主机提供的执行者、控制器每 5 秒看一次变化并在 Chief 对话里以平台名义留言。参谋长自己（LLM）做不到 1 分钟：它跑在会掉线的那台机器上。推荐 A：只改平台、不动库、不换 agentd，一天。

## 1. 现在有什么

### 1.1 主机

| 环节 | 现状 | 位置 |
|---|---|---|
| 存活列 | `agentrt.host.last_poll_at`，不带事件写（只有它是 host 表的存活列）；`tools_json`、`agentd_version` 两列**没有任何写入方** | `migrations/0001_core.sql:17-27`；`0009_issues.sql:295` |
| 谁写 | 每次 `ClaimNext` 第一句就 `UPDATE … last_poll_at = clock_timestamp()`；一个领活请求是 25 秒长轮询，里面**每 1 秒**跑一次 `ClaimNext` | `store/claim.go:100`；`agentrtapi/api.go:355-361、425-429` |
| 实测 | STG、PROD 各一台主机在轮询（STG agent-06-stg，PROD agent-06，同一台 06 上的两个 agentd）；30 分钟日志里相邻两次领活的间隔都 < 1 秒（STG 84 次、其中 13 次领到活；PROD 70 次）。正常运行时 `last_poll_at` 最多旧 1–2 秒，**长轮询不是瓶颈** | `bifrost-agentd.service:25-27`、`bifrost-agentd-stg.service` |
| 判定 | `HostLostAfter = 3 * time.Minute`；`HostsSQL` 算 `online`、`poll_age_s`，`GET /hosts` 和 Progress 同一段 SQL；正在跑的尝试的主机过门槛 → `host_lost` | `store/progress.go:40、136-140、725-734`；`agentrtapi/controls.go:161` |
| Console | Work → Crew 卡（「N of M hosts online」、「host lost · last poll …」）、Progress 页 Hosts 段；每 5 秒读一次 `/progress`，现读现算不缓存 | `owner/OwnerCrew.tsx:15-24、61-74`；`progress/ProgressPage.tsx:107`；`api/agentRuntime.ts:4`；`agentrtapi/plan.go:230` |
| For you | 主机条目读的是**老心跳路由** `GET /api/v1/agent/threads` 的 `hosts`；10-21 起没人写（PROD `hosts []`），10-28 要删 → 永远不会报 agentd 主机掉线 | `needs-you/useNeedsYou.ts:81、126`；`api/agentThreads.ts:106、167`；`PLAN-T24` 第 15、41 行 |
| 参谋长简报 | 定时简报 8:00、21:00（Chicago）只发 Chief 页，数据有 `vendor_pools`、没有主机；提醒（Nudges）只管卡住的任务、等他的目标、等他的卡 | `store/briefdue.go:20-33、96-160、202-250` |
| 告警 | 没有主机掉线的 `policy_alert`（规则词表 `vocab.go:427` 里没有）；agentrt、agentd 不出 Prometheus 指标；集群告警规则里没有 agentd | — |

**结果**：06 上的 agentd 停了，Console 约 3 分 0–5 秒后在 Crew 卡上变红（10-21 T24 实测 3.4 分钟）；Chief 页、For you、简报一直不说。

**参谋长为什么不能自己说**：参谋长是一个简报任务，岗位 `chief_of_staff` 只有一个候选 exec:claude（`briefwait.go:13-25`），每个环境只有 06 一台主机提供它。06 掉线时参谋长也掉线。能在 1 分钟内说的只有平台自己：在 Owner 与参谋长的对话里留一条「From the platform, not the chief of staff」，先例是 `TellWaitingBriefs`（`briefwait.go:163`），Chief 页 5 秒读一次就看到。

### 1.2 执行者

| 「不可用」可能是 | 谁知道 | 今天显示在哪 |
|---|---|---|
| 主机的 `AGENTD_TOOLS` 没写它 | agentd；平台每次领活都收到 `tools` 列表（`claim.go:24-33`）但**不存** | 无 |
| agentd 启动时拒绝（codex、cursor 的 MCP 检查） | 只有 agentd 日志（`mcpguard.go:75`；`cmd/agentd/main.go:131-145`） | 无 |
| agentd 一个都提供不了、或有进程组没清 | agentd **整分钟不轮询**（`main.go:182-187`），平台看到的就是「停止轮询」 | 当成主机掉线，分不出原因 |
| 程序没装、坏了、登录失效 | agentd 启动不查；平台只在尝试失败时知道，同一任务连败 3 次才有 `repeated_failure`（`retry.go:205-214`） | 尝试失败、mission 流上的告警 |
| 账号额度冷却 | 平台 `vendor_pool.cooldown_until`；领活时 `notCooling` 过滤（`claim.go:129`、`pools.go:365`） | Work 的额度卡；定时简报 `vendor_pools` |
| 额度到路由规则的停止线 | 平台（`quotaStop`） | 简报等待说明（`whyNoHostTakes`） |
| 提供它的主机都离线 | 要「每台主机提供什么」，平台没存，**算不出**；`whyNoHostTakes` 自己写着 "the platform does not record whether a host offering … asked"（`briefwait.go:262`） | 无 |
| 主机 drain / pause / stop、磁盘低于下限 | 平台（`control`、`disk_low`） | 控制在 Work；`disk_low` 只推手机 |
| 常设授权或岗位规则不让它做这件任务 | 平台（envelope、`job_candidate`） | 任务等太久时的说明 |

设计 v5 §3 第 101 行原本要 agentd「注册时上报」到 `host.tools_json`，没有实现。

## 2. 差距

1. **门槛 3 分钟**是最大的一块。领活每秒写一次，长轮询和 Console 的 5 秒刷新都不是问题。
2. **没有变化这一刻**：在线只在读时算，没人记「刚才离线了」，所以除了正好开着 Crew 卡的人，谁都不会被告诉。
3. **每台主机提供哪些执行者不存**，除冷却外的「执行者不可用」都算不出。
4. **Chief 页只能靠平台留言**（见 1.1 末段）。
5. **For you 读已退役的心跳源**。
6. 分不清「机器 / agentd 停了」和「agentd 在、但扣着不领」——不改 agentd 做不到（见 B）。

## 3. 选项

### A（推荐）：只改平台，约 1 天

1. **门槛** `HostLostAfter` 3 分钟 → **30 秒**。一个常量，`/hosts`、Progress、T24 的 `host_lost` 仍是同一口径；`SPEC-agentrt-progress` 第 87、129 行同步改。依据：实测间隔 < 1 秒；agentd 领活报错后睡 15 秒（`main.go:205-209`），30 秒容得下一次报错。
2. **记下每台主机提供什么**：每个领活请求一次（和 `RecordHostDisk` 同一位置，`api.go:374`），和这台主机上次记的不同，才在 `host:<id>` 流记一条 `note`，正文带 `offered`（执行者、提供方、模型）。不写状态表，不改库；`note` 正文加一个可选字段只是 Go 词表（`vocab.go:153`），库里没有约束。没有记录 = 未知，不报。
3. **控制器新循环 `agentrt-presence`，每 5 秒**：
   - 主机：`active`、没有 drain / stop 的主机过门槛 → `host:<id>` 流一条 `policy_alert`（规则 `host_offline`，产物写最后一次领活时间和上面正在跑的尝试）；再轮询 → 一条「back online」`note`。每个方向一次，写法照 `disk_low`（`hostdisk.go:60`）。drain / stop 中的主机是预期的停，不报。
   - 执行者：按岗位候选（`job_candidate` 里 active / probation 的执行者 + 提供方 + 模型），**可用** = 至少一台在线、没有 drain / pause / stop、磁盘不低的主机最近一次领活提供了它，且它的账号没在冷却、没到额度停止线。变成不可用 → `controller` 流一条 `policy_alert`（规则 `executor_unavailable`，写清原因：哪些主机离线或没提供、冷却到几点）；恢复 → `note`。同时点名因此**没有可用候选的岗位**（例如 `chief_of_staff`：参谋长回不了信）。
   - 每次变化在 Owner 与参谋长的对话里留一条「From the platform, not the chief of staff: …」，写法和去重照 `TellWaitingBriefs`。
4. **读接口只加字段**：`GET /progress`、`GET /hosts` 的 `hosts[]` 加 `offered`、`offered_at`；`/progress` 顶层加 `executors[]`（executor、available、why、hosts）。
5. **Console**：Crew 卡每台主机列出它提供的执行者，加一行 Executors；Work、System 顶上的 `RuntimeHealthNotice` 加两类红字（主机离线、执行者不可用）；For you 的主机条目改读 agentrt 主机（老心跳源随 10-28 删路由一起删）。
6. （可后放）定时简报的数据加 `hosts`、`executors`。它改的是参谋长的卷面输入，按 3.3 的规矩要重考；1 分钟验收不靠它。**建议等 3.3 资格流水线上线后再加**。

不放进来的：推手机（Owner 10-18「简报只发 Chief 页」；要的话复用 `DiskPages` 一个循环）。

**时延预算**：主机停 → Crew ≤ 30 + 5 = 35 秒；红字、For you、Chief 页 ≤ 30 + 5 + 5 = 40 秒。冷却引起的执行者不可用 ≤ 10 秒。

**发版会不会假报**：一次 STG 发版如果中断领活超过 30 秒，会出一对「离线 / 恢复」。STG 一天发好几次（`bifrost-platform-stg` 3.5 天 14 个 `agentrt-migrate` Job），所以验收专门量一次（§4 第 3 步）；超了就改 45 秒（预算 45 + 5 + 5 = 55 秒，仍在 1 分钟内）。

**是否架构级**：新表 / 新列：无（不用 `tools_json`，见 C）。新路由：无。新外部依赖：无（不用 Redis，主机在线仍只按 PG，同 v5 §5.1.4）。公开接口：两个读接口只加字段；`GET /events` 会出现两种新规则和一个新的 `note` 字段；`/claim` 不变。按以往「只加字段」的惯例不算改接口，Owner 认为算就在这里点头。行为变化：`host_lost` 从 3 分钟变 30 秒（设计与 SPEC 的数字）。不要新 agentd，不用 Owner 上 06。

**代价**：platform 约 300–400 行 Go，加真库 store 测试（照 `TestProgressCarriesT24sMarks` 的做法）；Console 约 150 行；`controls_test.go:452` 的 179 / 181 秒边界测试跟着改。一次 STG 发版（Agent 做），一张 PROD 发布单（Owner 批）。防线：一条测试，假时钟下主机停 → 40 秒内三处都说（health notice、Chief 留言、`/progress`），且同一次变化只说一次。

**做不到的**：分不清 agentd 停了和 agentd 扣着不领；分不清执行者为什么没提供（没配置还是 MCP 拒绝）；程序缺失、登录失效要等尝试失败才知道。

### B：A 再加 agentd 报原因（多约半天，另要 Owner 两件事）

- agentd 在「进程组没清」「一个都提供不了」时照常领活（`free_slots` 0），不再整分钟不轮询；
- `/claim` 正文加可选的 `refused[]`（执行者 + 原因：MCP、PATH 里找不到）和 `agentd_version`；
- 平台把原因写进同一条 `note`，Chief 页能说「cursor 没提供：这个用户有 2 个 MCP 服务」「agent-06 在，但有一个进程组没清，暂不领活」。

要 Owner：改 agentd ↔ 平台的公开接口（加字段）；06 上换 agentd（`agent-06-owner.sh update-agentd`，要节点口令）。各家登录状态的探针（`codex login status` 之类）每家不同，不在 B 里。**建议 B 不放进 3.5**，等下次本来就要换 06 上的 agentd 时一起做，省一次 Owner 上机。

### C：按设计存进 `host.tools_json`（不推荐）

用现成的列，读「现在提供什么」更直接，合 v5 §3 第 101 行。但写这列要么带事件——host 表只许 `host_registered` / `host_state_changed` / `host_retired` 写（`0009_issues.sql:326-328`），要加新事件类型；要么把它加进存活列豁免（`0009_issues.sql:295` 只有 `last_poll_at`）。两种都是迁移 0010，改的是 T25「状态改动都带事件」的不变式，PROD 迁移随发版：架构级，要 Owner。比 A 多约半天和一轮复核，功能上与 A 相同。A 的 `note` 写法有 `disk_low` 先例，所以不选。

## 4. 验收（STG）

前提：含本切法的平台版本已发 STG 并核对（Pod 的提交、启动日志）。STG 上 gate-b、mbp-dev 停了 5 天（`PLAN-T24` 第 158 行）：上线后第一遍会各报一次「离线」，这是真的。不想看到就先 drain 它们：`POST /controls` 设 drain，任何已登录的令牌都能做（`store/controls.go:11-13`），但**解除只有 Owner**（`agentrtapi/api.go:103`）。

1. **主机掉线（不用 Owner）**：本机用 gate-b 的 STG 令牌（`~/.config/bifrost/agentd-gate-b.token`）起一个 agentd，`AGENTD_TOOLS` 只给 `exec:deterministic=local`。先给 gate-b 设一个 pause，保证它不领 STG 的活（解除要 Owner；gate-b 本来就停着，留着无害，报告里写明）。Crew 显示 gate-b online、Offers deterministic 之后停掉它，记时刻 S。要看到：
   - ≤ S + 35 秒 Crew「gate-b offline」；
   - ≤ S + 40 秒 Work / System 红字、For you 一条、Chief 页一条「From the platform … gate-b stopped polling …」；
   - 再起 agentd，≤ 10 秒「back online」，Chief 页一条恢复；同一次变化各只一条。
2. **执行者不可用**：
   - 2a（不用 Owner）：store 真库测试分别摆出四种原因的变化（没提供、提供它的主机都离线、冷却、额度停止线），各断言 `policy_alert`、Chief 留言、`/progress` 的 `executors` 各一条且只一条。
   - 2b（STG 实测，要 Owner 约 1 分钟）：Owner 在 Console 额度卡给 cursor 的一个池记一次「用完、5 分钟后重置」（手填读数只许 Owner，`pools.go:333`）。≤ 10 秒 Chief 页「exec:cursor unavailable: … cool down until …」、红字出现；5 分钟后「available again」。另一种做法是 drain agent-06-stg 让本机 gate-b 成为唯一提供者，但解除 drain 同样要 Owner，还会停住 STG 的活，所以不用。
3. **发版不假报**：第 1 步之后照常发一次 STG，看有没有 agent-06-stg 的「离线 / 恢复」一对。有就改 45 秒再量一次。
4. **06 整机掉线**（T24 那样 SIGSTOP 或合盖）不单独做：它就是第 1、2 步的合并；下次 Owner 本来要上 06 时顺手看一次。届时 PROD 应同时说：agent-06 离线、四个执行者都不可用、`chief_of_staff` 没有可用候选。

## 5. 要 Owner 定的

1. 选 **A**（推荐）还是 C。
2. B 现在做还是**等下次换 agentd 时一起做**（推荐后者）。
3. 门槛 **30 秒**（推荐；第 3 步量到发版假报就改 45 秒）。
4. 定时简报加主机和执行者：**等 3.3 上线后再加**（推荐），还是现在加、手工重考一次。
5. 验收 2b 要不要他花 1 分钟（推荐要：真实走一遍冷却的路径），或者只靠 2a 的测试。

以上没有新表、新列、新路由、新外部依赖。只有 C 要迁移，只有 B 改 `/claim`。
