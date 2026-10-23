> 复核 527（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/r3-35-online`（第 3 轮 3.5 在线状态）。报告里的 `probes/`、日志等证据在本机 `~/agent-work/codex-review-527/`，不进仓库。

# Review 527 — W-31 round 3 / 3.5 最后一轮窄复核

审查基线：`95ac365efd28a677aba7e77d0376282dd625993b` → `f0e54286f53f7fe0d4b488696d661b5863deaaa6`，包含 `ca212de6`、`9f7f048c`、`f0e54286`。目标 worktree 的 HEAD 与给定末提交一致。只检查 526 的关闭情况及这三次修复带来的缺口，不重开上一轮接受的范围。

结论：A2、B1、B2 可以关闭；A1 的正常清理误报路径已修，但新增的 contact 判定存在 A3；A1b 仍不能完整关闭。下面的 A 项交给 Owner 选方案。本报告没有修改实现、治理台账或目标 worktree。

## 关闭表

以下实现路径均相对于 `~/agent-work/r3-35/`；`probes/` 相对于本审查目录。真库测试的“已有覆盖”指代码中存在该测试，不表示本环境执行通过。

| 原项 | 判定 | 代码及测试证据 |
| --- | --- | --- |
| A1：同步 prune 超过 30 秒误报失联 | **已关闭，但有新缺口 A3** | `api/internal/agentrt/agentrtapi/prune.go:56` 在清单读取及报告期间刷新 contact；`:124` 仅非空清单开启 round；`api/internal/agentrt/store/presencelive.go:45` 对开启后的 165 秒给宽限，报告或下一次 claim 关闭（`:113`；`agentrtapi/api.go:392`）。HostsSQL 和 liveAttempts 使用同一 SQL 判定（`store/presence.go:69`、`store/progress.go:350`）。已有 `TestAPruningHostIsNotLost`（`store/presencelive_test.go:76`）覆盖 2 分钟、超预算、关闭后 31 秒及只关闭一次；本次真库部分跳过。常量绑定测试及开 round 的解码探针通过。 |
| A1b：平台 Recreate 造成全体主机假失联 | **未关闭，基础同步启动场景已修** | `api/internal/agentrt/controller/controller.go:568` 设置 controller 的启动时间；`store/presencelive.go:53` 从较晚时间算 silence；`store/presence.go:240`、`:467` 将宽限中的候选保留为 unknown。已有 `TestARestartedPlatformWaitsForTheHosts`（`store/presencelive_test.go:132`）、`TestPresenceCountsFromTheControllersStart`（`controller/presence_test.go:123`）。但生产 API 的 Started 早于 DB ready，且与 workers 没有共同恢复时点，见 A1b 详情。 |
| A2：另一个岗位 unknown 时宣告所有岗位恢复 | **已关闭** | `api/internal/agentrt/store/presence.go:375` 按每个岗位候选的最佳结果区分 unserved / unknown；`store/presencepass.go:302` 明列 unknown，`:306` 两类都空才说全部恢复。已有 `TestAnExecutorBackIsNotEveryJobCovered`（`store/presencelive_test.go:226`）。适配后的 526 离线探针 `probes/presence_review_test.go:62` 实际通过：claude 恢复、codex 为 null 时只说 claude 恢复，并列 implementer 未知，没有全体恢复句。 |
| B1：维护主机恢复仍播报 | **已关闭** | `api/internal/agentrt/store/presence.go:226` 定义统一 watched 范围，输入 controls 包括全局和主机控制（`:71`）；`store/presencepass.go:122` 对范围外的旧告警生成 quiet close，`:172` 写 note 后跳过播报，`:224` 全 quiet 时不发消息。已有 `TestAHostTakenOutOfWorkIsNotToldBack`（`store/presencelive_test.go:270`）覆盖 drain / stop / retired、恢复轮询、解除控制后不补发旧恢复。离线探针 `probes/presence_review_test.go:34` 对三类均通过。 |
| B2：最新状态读取随事件历史扫描 | **已关闭；未独立重验执行计划** | `api/internal/agentrt/store/presence.go:51` 通过 event_stream 的主键读 last_seq，再以 `(event_stream_id, seq)` 唯一键取事件（索引定义 `migrations/0001_core.sql:198`、`:221`）；offers / prune / presence 都走此方式，`store/presencepass.go:146` 不再过滤旧流历史找最后匹配。`TestPresenceReadsAreBounded`（`store/presencebound_test.go:75`）确实以 4,000 → 44,000 无关事件执行 ANALYZE / EXPLAIN，并包含从未记录的流。简报提供的 buffers 结果与此测试相符，但本轮该测试跳过，不能把提供的数据当成本轮测量。 |

## A：先修，或由 Owner 明确接受能力边界

### A1b — 宽限从各进程启动开始，仍可能把平台尚未恢复的时间归罪于主机

位置：`api/internal/server/agentrt_wire.go:78`、`:110`、`:119`、`:132`；`api/internal/agentrt/agentrtapi/controls.go:164`；`api/internal/agentrt/agentrtapi/plan.go:231`；`api/internal/agentrt/store/presencelive.go:53`。

API 在 wire 时就固定 `Started=time.Now()`，随后才后台重试连接 DB；这段时间路由持续 503。重试可持续超过 30 秒（`server/agentrt_wire.go:275`），连接成功时没有更新 API.Started。workers 则在自己的 DB 连接成功后才创建并 Start controller。因此“同一条判定规则”实际带了不同、且 API 侧可能已经过期的起点。

一个具体时序：API 在 t=0 建对象，t=60 才连接 DB，主机之前最后一次成功 contact 是 t=-1。API 在 t=60 刚能答 `/hosts`、`/progress` 就将该主机判 lost；主机 t=70 成功重试，明明是恢复接入后 10 秒，Console 仍先出现假失联。`probes/touch_review_test.go:87` 调用真实 listHosts 捕获参数，确认传入的仍是 t=0；其时间边界计算是 SQL 模型，未执行 PostgreSQL。

另一个方向：workers 已在 t=0 启动，API 的接活入口到 t=60 才能用；即使 workers 自己的 DB 正常，它在 t=35 的 presence pass 就能给所有未联系的主机写 offline / unavailable 留言。反过来单独重启 API 又会把 workers 已判 offline 的主机暂时变为 unknown，形成 Console 与留言不一致。现有两个启动测试只给定单个 since，没有覆盖 API ready 晚于该 since 或两个角色错开的生产接线。

建议 Owner 二选一：

- **推荐修复**：API 的宽限至少从 agentrt 路由真正可用时开始；workers 对平台造成的接入中断使用同一恢复依据。补 API 延迟连接、workers 先于 API 恢复、单独重启任一角色的测试。仅把各自 Started 改为自己的 ready 时间，仍不足以覆盖另一个角色晚恢复。
- 接受“只豁免本进程启动后的 30 秒”，并明确 Recreate / 分角色发布仍可能假报全体掉线；相应收窄 A1b 的验收承诺。当前不能声称“平台发版不会造成全体假失联”已完成。

### A3（A1 修复带入）— attempt 的 contact 可以长期掩盖停止接活，165 秒并不是这条路径的上限

位置：`api/internal/agentrt/agentrtapi/api.go:522`；`api/internal/agentrt/store/presencelive.go:79`、`:45`；`api/internal/agentrt/store/presence.go:219`、`:465`。

TouchHost 将任何 attempt action 的到达写成 `last_poll_at`，hostOnlineSQL 对新鲜 contact 与 prune 宽限取 OR；后续 judgeCandidate 只要主机 online 且旧 offered 匹配，就继续判 confirmed available。代码没有另一项“最近仍在领取”的时间依据。因此 prune 已经过期、claim 主循环已经停住，只要独立 attempt goroutine 仍发送 contact，该主机和所有旧 offered 对应的执行者仍会被当作能接活，可以持续远超 165 秒。

这是实际控制流允许的故障形态：claim 与每项 Run 是不同 goroutine（`api/cmd/agentd/main.go:205`、`:216`），keepLease 自行定时发送 heartbeat（`api/internal/agentd/deliver.go:96`）。主循环在 Recover 失败时不 claim（`cmd/agentd/main.go:167`），遇到不明进程组也明确停止接活（`:182`；`agentd/deliver.go:588`）。一个既有尝试的 heartbeat 并不能证明这条接活循环健康；若它仍为其他执行者提供者，那些执行者也会一起保持 available。

`probes/presence_review_test.go:84` 调用真实 judgeExecutors，确认“只有最近 contact、保留旧 offers”的输入仍输出 available=true、无 unserved / unknown。探针没有制造真实进程死锁，也没有证明 STG 曾发生此故障；从 contact 到 online 的部分由上列 SQL 静态确认。

这里**不能称物理主机已死**：它还有请求到达，按协调者指定的 contact 定义保持 host online 是合理的。新增缺口在于把这份存活证据继续当作“执行者可以接新活”的证据。这也不重开上一轮已接受的满槽或单项任务授权限制。

建议 Owner 二选一：

- **推荐修复**：保留任意 contact 证明主机活着，同时为执行者可接活保留独立的领取新鲜度；正常 prune 在明确的有限宽限内豁免。补“claim 停住、另一项尝试持续 heartbeat、prune 已超预算”的测试，不能继续无期限 confirmed available。
- 明确接受在线状态只监测连通性、无法检测接活循环挂住；收窄 available 的文字与一分钟承诺。这是接受一个监测盲区，不是已经证明 165 秒后都会报出故障。

## B：应修

### B3（新）— 清理请求取消后，最后一次 TouchHost 同步等待且没有截止时间

位置：`api/internal/agentrt/agentrtapi/prune.go:222`、`:225`；`api/internal/agentrt/store/presencelive.go:77`；`api/internal/agentrt/store/write.go:24`。

keepTouching 的退出函数先等待后台刷新结束，再用 `context.WithoutCancel(ctx)` 做最后一次同步 touch。该 context 同时失去原请求的取消和 deadline；TouchHost 自身没有另设短 timeout。即使 agentd 已经断开，handler 仍可能无限等待连接池、表级锁或数据库 I/O，取消请求不再能释放这次等待。

离线探针 `probes/touch_review_test.go:36` 对真实 keepTouching / TouchHost / InTx 使用可控 DB 替身：取消请求后，最后一次 BeginTx 收到 `Err()==nil`、无 deadline 的 context；finish 要等探针手动放行 DB 才返回。它证明缺失上界，不是实测 PostgreSQL 锁等待。应给这种 best-effort touch 设置很短的独立超时，不能因记录 contact 阻塞已经结束的业务请求。

TouchHost 的 `FOR NO KEY UPDATE SKIP LOCKED` 确实会避开被 claim / control 持有的**行锁**；它在自己的短事务内完成，随后 attempt 才开始另一个事务，没有发现它引入 host → attempt / attempt → host 的持锁循环。SKIP LOCKED 不代表连接池、表锁、网络也不等待。没有真库条件，不能作“热路径无锁竞争 / 无死锁”的负载结论。

## C：边界核对、验证和未验证部分

### 清理预算与单独重启

- 不再有 contact、不再开启新 round，且 reader 不重新启动时，prune 宽限本身有明确上界：开启时刻起 **165 秒内** online，超过后失效（`store/presencelive.go:32`、`:47`）。它不会因为 presence 一直读就续期。正常运行的 5 秒 pass 与 5 秒 UI 轮询还会加最多约 10 秒；不能继续把 prune 中的真实断电承诺为 40 秒发现。这一放宽是协调者明确要求的预算。
- 报告及下一次 claim 均调用 ClosePruneRound；先读、锁流、再读后追加一次 closed（`store/presencelive.go:113`），有重复关闭测试。独立解码探针 `probes/prune_round_review_test.go:19` 通过，没有发现开启状态读不出的错误。
- 普通 host 判 lost 的时间下界取最近 contact +30 秒、reader Started +30 秒；存在有效 prune 时还须等它过期。单独重启 workers 会重新给一次 30 秒宽限，这是协调者指定的 controller-start 策略；已有 offline 的流头仍保留，unknown 不生成 back turn（`store/presencepass.go:127`、`:132`），没有发现凭重启就伪造恢复或重复发同一告警。连续重启会连续延迟判定，因此预算不应被解释为跨任意平台重启的绝对墙钟上界。角色起点错开的问题见 A1b。

### 新流、GET 写入、读取权限

- 新状态流的事件仍是既有 `note` / `policy_alert`；本次没有迁移、表列或通用 append 路由。流名、seq / hash 链仍由原 Append 与数据库 trigger 管理（`store/event.go:87`；`migrations/0002_guards.sql:67`）。流头读取不需要扫描旧 host / controller 流。`RecordHostDisk` 的旧历史扫描仍存在（`store/hostdisk.go:73`），是简报明确留在 TD-415 的既有路径，本轮不重开。
- `GET /prunes` 现在有副作用：刷新 contact，交出至少一条分支时追加 opened。Prunable 空结果是 nil（`store/prune.go:133`），因此 `ps != nil` 在当前实现中不会为空清单开启宽限；反复非空 GET 会写多次 opened 并重置该轮起点。正常 agentd 每 10 分钟执行一次 prune，随后 claim 关闭，不是每秒稳定写事件（`agentd/prune.go:31`；`cmd/agentd/main.go:174`）。没有发现 GET 直接删除分支、延长 attempt 租约或绕过 D10 的变化。
- 两种 `/events` 读取都能看到这些新前缀（`agentrtapi/api.go:713`、`:727`；`agentrtapi/events.go:83`）。GET /prunes 仍只给绑定本机的 agentd token（`agentrtapi/api.go:136`、`:226`），viewer / operator 不能借普通读取开启 round。events 的读角色没有扩大（`:102`、`:155`），原 issue / intake / exam 的屏蔽规则未被这些前缀绕过。
- 新流只增加 offers、磁盘低水位布尔值、prune 开闭、主机及执行者状态等元数据；presence artifact 的内容仍是 ID、岗位、时间和原因，没有复制任务正文、Owner 对话或凭证。Console 的事件解析接受任意非空 stream 字符串（`console/src/api/agentRuntimeEvents.ts:26`），未发现新前缀导致解析失败。没有发现本次新增秘密暴露或现有消费者必须使用 host/controller 前缀才能工作的问题。

### 本轮实际执行

全部 Go 命令使用指定的共享 GOCACHE / GOMODCACHE、`GOPROXY=off`、`GOSUMDB=off`、`-mod=readonly`，TMPDIR / GOTMPDIR 在本目录；显式移除 `AGENTRT_TEST_PG`、`AGENTRT_TEST_REDIS`、`AGENTRT_TEST_REQUIRED` 等连接环境变量。没有联网、连接或启动数据库、绑定端口、访问集群、MCP、SSH 或提交。除本目录与共享缓存外没有写入。

- **通过**：`go test -mod=readonly ./internal/agentrt/... ./internal/server -run '^$'`，只编译测试目标，见 `go-compile.log`；Console `./node_modules/.bin/tsc --noEmit --incremental false`，见 `tsc.log`；给定提交范围的 `git diff --check`。
- **通过**：overlay 下 7 项 Review527 离线探针、`TestPruneSilenceCoversAgentdsBudget`、TaskStatusOrder / LiveOrder / NeverPolled 的纯单元测试，见 `go-probes.log`。首次运行时离线 Rows 替身漏实现 CommandTag，已在本目录补齐并重跑通过；没有把探针自身的崩溃归为产品缺陷。
- **重跑 526 探针**：A2、B1 和 unknown 保留情景只适配新函数签名与批量读流头的 DB 替身，断言改为修复后的结果，均通过。原 `TestReview526SuccessfulPruneCanOutlastPresence` 原样复用，仍复现 Prune 无 claim 的 35 秒空档及 TaskStatus 的旧 fallback；它通过不表示生产缺陷未修，因为旧 LiveForTest 没有赋本次新增的 hostSilent，生产 liveAttempts 现由 SQL 提供这个字段（`store/progress.go:93`、`:192`、`:367`）。A1 的生产 SQL 关闭判断以上表静态链路和已有真库回归为据，未用旧探针冒充全链路验证。
- **跳过**：上表中的 6 组真库回归（包括 B1 的各子测试）。日志明确显示缺少 AGENTRT_TEST_PG 而 skip（`agentrttest/db.go:41`）。尤其 `TestAHostTakenOutOfWorkIsNotToldBack` 外层显示 PASS、三个子测试均 SKIP，不能计为真库通过。
- **未验证**：本轮 EXPLAIN / BUFFERS、PostgreSQL 并发与锁竞争、实际 Recreate / 故障恢复耗时、真实 API / workers 启动先后、STG 的 heartbeat-only 故障、浏览器视觉和 Console Vitest。提供的执行计划数据属于实现者证据；本轮没有新增运行环境测量。

可复跑离线探针：在目标 `api/` 下使用上述离线环境及断开的测试连接变量，执行 `go test -mod=readonly -overlay=/Users/vision-mac-trader/agent-work/codex-review-527/overlay.json ./internal/agentrt/store ./internal/agentrt/agentrtapi -run '^TestReview52[67]' -count=1 -v`。

先修：A1b（宽限起点未覆盖实际接入恢复与分角色时序）、A3（仅有 attempt contact 可长期掩盖接活循环失效）；或由 Owner 明确选择接受上述能力边界。

END OF REPORT
