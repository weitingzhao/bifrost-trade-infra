> 复核 528（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/r3-35-online`（第 3 轮 3.5 在线状态）。报告里的 `probes/`、日志等证据在本机 `~/agent-work/codex-review-528/`，不进仓库。

# Review 528 — W-31 / 3.5 第三轮窄确认

审查范围：仅第二轮的 A1b、A3、B3，以及本次新增的 down 记录和 10 分钟上限。基线 `f0e54286f53f7fe0d4b488696d661b5863deaaa6` → `0a06bf8aa72f56bfa0949ef17cb73e257f47ae8b`，包含简报指定的三个提交。目标工作树 HEAD 匹配，审查前后 `git status --short` 均为空。本轮未重开其他已关闭项。

**结论：A3、B3 已关闭；A1b 未完整关闭，共同恢复时点已修，但新增 down 方案有可用性误判，up 写入与路由开放也有窗口。** 剩余 A1b 交 Owner 选修正或明确接受边界，本报告不扩展实施或开启下一轮。

以下 `api/`、`console/` 路径均相对于 `~/agent-work/r3-35/`；`probes/` 和日志路径相对于本审查目录。真库测试“已有覆盖”不表示本轮执行通过。

## 关闭表

| 原项 | 判定 | 代码与测试证据 |
| --- | --- | --- |
| A1b：平台接入恢复与各 reader 起点错开 | **未关闭；共同 up 已修，down 带入新缺口** | `api/internal/agentrt/store/presencelive.go:74`、`:83`、`:91` 统一使用平台流头；API 不再传 wire 时的 Started（`api/internal/agentrt/agentrtapi/controls.go:164`、`api/internal/agentrt/agentrtapi/plan.go:231`），TaskStatus 的生产输入也使用此 SQL（`api/internal/agentrt/store/progress.go:345`），controller 另保留自身 Started（`api/internal/agentrt/controller/presence.go:29`）。离线实际 handler 探针 `probes/touch_review_test.go:81` 通过。已有 `TestTheHostsWaitForThePlatformsRecovery`（`api/internal/agentrt/store/presencelive_test.go:436`）、`TestAgentRuntimeSaysWhenThePlatformTakesCalls`（`api/internal/server/agentrt_wire_test.go:326`）、API hosts 测试（`api/internal/agentrt/agentrtapi/controls_test.go:459`）本轮均跳过真库部分；未覆盖下述实际开放窗口及较新副本先退出的情况。 |
| A3：只有 attempt heartbeat 仍长期宣称可接新活 | **已关闭；A1b 的平台宽限问题另计** | attempt action 不再 TouchHost（`api/internal/agentrt/agentrtapi/api.go:511`）；contact 取主循环时间和 leased/running attempt heartbeat 的较晚者（`api/internal/agentrt/store/presencelive.go:48`），claiming 单独取主循环 30 秒或有效 prune（`:66`）。`HostPresence.usable` 要求 claiming 为 true（`api/internal/agentrt/store/presence.go:225`），不领取时给明确原因（`:526`）。适配第二轮 A3 探针后，实际 judgeExecutors 返回 unavailable，并经实际 presenceTurns 确认同一告警头不重复生成 turn（`probes/presence_review_test.go:16`），通过。已有真库 `TestAHostThatOnlyHeartbeatsTakesNoWork`（`api/internal/agentrt/store/presencelive_test.go:346`）和 agentd API 路径断言（`api/internal/agentrt/agentrtapi/api_test.go:334`）本轮跳过。 |
| B3：取消 prune 请求后的最后一次 touch 没有 deadline | **已关闭** | `api/internal/agentrt/agentrtapi/prune.go:202` 设置 3 秒，`:229` 用 `WithTimeout(WithoutCancel(ctx), touchLast)` 创建独立 deadline。适配第二轮探针，实际观察到请求已取消、最后一次 BeginTx 的 context 仍有效且有约 3 秒剩余（`probes/touch_review_test.go:38`），通过。新增 `TestTheLastTouchHasADeadline`（`api/internal/agentrt/agentrtapi/touchlast_test.go:29`）用等待 ctx 结束的 DB 替身和 50ms 测试预算，实际通过。此结论针对本项最后一次 touch 的 deadline；没有实测 PostgreSQL I/O 取消及完整 handler 耗时。 |

## A：A1b 仍需修正，或由 Owner 接受收窄后的能力边界

### A1b-1：up 尚未写成，路由已经开放；没有 down 时，workers 也仍能在恢复前误报

位置：`api/internal/server/agentrt_wire.go:121`、`:132`、`:332`、`:455`；`api/internal/agentrt/agentrtapi/api.go:212`；`api/internal/agentrt/store/presencelive.go:83`。

连接成功后，代码先 `late.pool.Store(pool)`，这立即让 configured 中间件放行；随后才异步执行 MarkPlatformUp。写 up 失败会以最长一分钟的间隔重试，路由不会重新变成未就绪，日志也明确承认可能按旧起点判主机。API 的 Started 已删除，此时没有本地新起点兜底。

具体可达时序：旧 up 很早，旧 API 被杀而没有 down；新 API 在 t=60 连上 DB，主机上次成功联系在 t=-1。pool 已公布，但 up 写入尚未提交。t=60 的 `/hosts` 或 presence pass 仍按旧流头判失联，即使主机在 t=70 成功重试，距接入恢复只有 10 秒。写流头等待锁或一次 goroutine 调度交错，就足以产生窗口；持续写入失败会扩大窗口。最窄的这部分修正是：**本次 up 成功提交后再公布路由 Ready**，不能只把重试留在开放后的后台。

另一个窗口发生在新 up 之前，不能仅靠上述排序修正：API 异常退出不写 down，而 workers 仍在运行。假定 workers 在 t=0 启动，API 到 t=60 才能接请求，t=35 的 pass 已可产生全体 offline / unavailable。t=60 写 up 能使后续读数进入宽限，不能撤回此前已经发出的错误留言。首次没有平台流头时也没有“API 尚未可用”的共同依据。实现者已说明 OOM / 节点丢失的限制；这是尚需 Owner 接受的边界，不能算已满足原回复“平台恢复接入前不把沉默归罪于主机”的承诺。

证据：`probes/ready_review_test.go:30` 使用实际 lateDB.Ready 和 markPlatformUp，在写标记失败时观察到 Ready=true，探针通过；这是按生产接线顺序组合的组件探针，没有调用完整 wire 或建立连接。`probes/presence_review_test.go:183` 的时间模型复现 workers 在 +35 秒判 lost、+60 秒 up 后的 +70 秒才受保护。后者只复述 SQL 时间运算，未执行 PostgreSQL。

现有 recovery 真库测试在先写好 up 后才运行 pass（`api/internal/agentrt/store/presencelive_test.go:447`、`:463`），用 `started=up-60s` 表示延迟启动；server 测试直接调用 markPlatformUp（`api/internal/server/agentrt_wire_test.go:348`）。两者均没有实际暂停在 pool 公布和 up 提交之间，也没有在异常退出后的接入中断期间运行 pass，因此不能消除此缺口。

### A1b-2：最后一个 up 的实例退出，不等于平台已无 API；陈旧 down 会抑制真实故障

位置：`api/internal/agentrt/store/presencelive.go:74`、`:104`、`:124`、`:141`；`api/internal/server/agentrt_wire.go:129`。

MarkPlatformDown 只问“流头是否还是本实例的 up”。这能防止旧实例覆盖新实例的 up，却没有记录或检查其他实例是否仍能接请求。

反例：API A 写 up 并一直正常服务；API B 随后写 up，然后 B 退出，A 没有退出。B 仍是流头拥有者，因而成功写入全局 down。A 只在启动时写 up，继续处理请求不会纠正这个 down。此后某台主机真正断电，哪怕其他主机仍经 A 正常领取，它的失联与相关执行者不可用仍会被转成 unknown，直到新的 up 或上限结束。此情形适用于双副本，也适用于滚动替换中新实例先失败、旧实例仍存活；不是声称当前环境已经运行两个副本。

`probes/presence_review_test.go:136` 对真实 MarkPlatformUp / MarkPlatformDown / Append 使用串行 DB 替身，执行 `up(A) → up(B) → down(B)`，确认产生 down，而 A 从未停止。探针通过表示复现了缺口，不表示方案正确。替身不模拟 PostgreSQL 的并发锁。

**10 分钟上限的实际含义是最多额外等到 down 后 10 分 30 秒才可判 lost。** down 时恢复基准为 `min(now, down_at+600s)`，之后 hostSilent / hostClaimLost 还要等严格大于 30 秒。在无新 contact、无有效 prune、无 reader 重启的前提下，5 分钟和 10 分 30 秒时都仍不判失联，10 分 31 秒时才判；再受正常 5 秒 pass / UI 轮询影响。这一点由同一离线时间模型确认（`probes/presence_review_test.go:200`），实现者真库测试也显式要求 cap+30 秒仍不报（`api/internal/agentrt/store/presencelive_test.go:506`）。读取不会给 down 续期，因此没有发现单条 down 导致无限期冻结。

如果唯一 API 确实停服，暂时把主机视为不可观测是合理的；但当前 down 不是“所有 API 都不能接入”的可靠证据。任意选 10 分钟不能补上这一事实，缩短常量也只会缩短盲区。反过来，若唯一 API 停服超过上限，代码在没有接入恢复证据时仍开始归罪于主机，原 A1b 的误报会再出现。**新增 down 加此上限，按当前未收窄的验收承诺不可直接接受。**

最窄修正方向是给 down 的冻结增加当前接入可用性的约束：仍活着的 API 必须能在有界时间内纠正陈旧 down；若要支持双副本，判断须反映仍在服务的实例，不能只看最后启动者的退出。若只支持单实例，应明确并约束这一前提。上限到期但平台接入仍不可观测时，应标明平台不可观测，而不是把到期伪装成恢复时点并据此断言主机掉线。

### 本轮后留给 Owner 的选项

- **推荐修正 A1b**：先提交 up 再开放 Ready；用能反映当前接入能力的共同依据限制 down，处理存活旧副本、写标记失败和无 down 的异常退出。至少补“Ready 前 up 未提交”“A 活着而 B 退出”“API 未恢复期间 workers 先运行”的断言。此处只给选项，不擅自新增接口、表或实现下一阶段。
- **接受收窄的能力边界**：限定为单 API、正常退出写 down 成功且在预算内恢复；明确允许异常退出时误报，以及陈旧 down 时最长约 10 分 30 秒加轮询的检测延迟；超过停服预算仍可能误报。该选择需要 Owner 明确接受，不能由本轮默认代签。

## B：B3 关闭；本轮没有新增 B 项

原先去掉请求取消与 deadline 的最终写入，现在保留独立 3 秒截止时间。第二轮的“无 deadline”断言已改成修复后的断言；实现者的等待型 DB 测试也实际执行通过。未因沿用旧预期的探针失败而误判修复失败。目标工作树未修改。

## C：验证、竞态核对及未验证部分

### up / down 的先后顺序

没有发现“旧 down 把已经提交的新 up 覆盖”的锁竞态：MarkPlatformDown 先锁流再读流头（`api/internal/agentrt/store/presencelive.go:128`），Append 对同一流取 FOR UPDATE（`api/internal/agentrt/store/event.go:103`）。新 up 先提交则旧 down 被身份检查拒绝；旧 down 先提交则后续新 up 成为流头。离线串行替身分别验证了这两个顺序（`probes/presence_review_test.go:138`、`:165`）。这是静态锁顺序核对加串行结果验证，不能冒充真库并发实测。A1b-2 是对多实例可用性建模不完整，区别于此项覆盖竞态。

### A3 的有限宽限和展示

正常主循环请求（claim、prune 清单及报告）仍可证明接活；独立 attempt heartbeat 只证明在线。有效 prune 仍以 165 秒为预算，超预算后 heartbeat 不会让 claiming 继续为 true（`api/internal/agentrt/store/presencelive.go:55`、`:67`）。这是本轮允许的“主循环时间”，没有把 prune 中的正常工作误当停止接活。

`/hosts` 和 `/progress` 都从 HostsSQL 生成 claiming 的 true / false / null（`api/internal/agentrt/store/presence.go:76`、`:294`）；Console 解析该字段（`console/src/api/agentRuntime.ts:211`），在线但不领取显示 `online · not taking work`（`console/src/pages/shell/owner/crewModel.ts:89`），已有相应文字断言（`console/src/pages/shell/owner/__tests__/presence.test.tsx:33`）。本轮类型检查通过，没有执行浏览器或 Vitest。

### 本轮实际执行

全部 Go 命令设置 `GOCACHE=~/agent-work/.cache/go-build`、`GOMODCACHE=~/agent-work/.cache/go-mod`、`GOPROXY=off`、`GOSUMDB=off`，使用 `-mod=readonly`；TMPDIR / GOTMPDIR 均在本审查目录。显式移除 `AGENTRT_TEST_PG`、`AGENTRT_TEST_REDIS`、`AGENTRT_TEST_REQUIRED`、`CONSOLE_PRESENCE_FIXTURE_WRITE`。没有联网、连接或启动 PostgreSQL、绑定端口、使用集群 / MCP / SSH、提交，或写目标工作树及其他目录。写入仅在本审查目录和共享缓存。

- **通过**：`go test -mod=readonly ./internal/agentrt/... ./internal/server ./cmd/agentd -run '^$'`，只编译测试目标，见 `go-compile.log`；Console `./node_modules/.bin/tsc --noEmit --incremental false`，见 `tsc.log`（空输出、退出 0）；指定提交范围的 `git diff --check`。
- **通过**：6 项 TestReview528 离线顶层探针（平台流探针含 3 个子项）；原样复用第二轮 `TestReview527PruneRoundReadsOpened`；`TestTheLastTouchHasADeadline`；prune 预算绑定、TaskStatusOrder / LiveOrder / NeverPolled，以及不做连接的 `TestAgentRuntimeStopsConnecting`。见 `go-probes.log`。初次离线探针通过后，给 A3 探针增加真实 presenceTurns 的不重复断言，重跑同组通过。
- **第二轮探针适用性**：A3 探针增加独立 Claiming 输入，并将预期改为 unavailable；B3 探针改验独立 deadline；A1b 的 API.Started 字段已删除，改验实际 handler 的参数不再传旧起点且 SQL 使用共享流。prune 解码探针原样重跑。没有重跑范围外的 A2 / B1，也没有把旧 526 fallback 探针当作本次生产 SQL 的证据。
- **跳过，不能计为通过**：`TestAHostThatOnlyHeartbeatsTakesNoWork`、`TestTheHostsWaitForThePlatformsRecovery`、`TestAgentRuntimeSaysWhenThePlatformTakesCalls`、`TestAgentdPath`、`TestHostsAndControlEdges`。日志明确显示因缺少 AGENTRT_TEST_PG 而 SKIP。
- **未验证**：真实数据库 SQL 运行结果和执行计划、行锁 / 表锁及流锁并发、数据库 I/O 取消的实际耗时；完整 wire 延迟连接与 HTTP 接入的联动；真实 Recreate、OOM / 节点失联、双副本发布；STG 故障注入、浏览器与 Console Vitest。没有启动服务来绕开限制。时间边界模型、串行 DB 替身和组件探针均已在上述证据处说明限制。

可复跑的本轮探针：在目标 `api/` 下使用上述离线环境，执行：

```sh
go test -mod=readonly \
  -overlay=/Users/vision-mac-trader/agent-work/codex-review-528/overlay.json \
  ./internal/agentrt/store ./internal/agentrt/agentrtapi ./internal/server \
  -run '^(TestReview528|TestReview527PruneRoundReadsOpened|TestTheLastTouchHasADeadline)' \
  -count=1 -timeout=90s -v
```

先修：A1b（up 未提交即开放 Ready；异常退出缺共同停服依据；陈旧 down / 双实例可错误抑制检测，10 分钟上限也未证明平台恢复）。或由 Owner 明确选择上述收窄边界；A3、B3 关闭。

END OF REPORT
