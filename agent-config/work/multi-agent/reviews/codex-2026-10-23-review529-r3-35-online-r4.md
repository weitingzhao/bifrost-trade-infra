> 复核 529（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/r3-35-online`（第 3 轮 3.5 在线状态）。报告里的 `probes/`、日志等证据在本机 `~/agent-work/codex-review-529/`，不进仓库。

# Review 529 — W-31 3.5，第 4 轮窄确认：仅 A1b

审查范围：`~/agent-work/r3-35` 的 `0a06bf8aa72f56bfa0949ef17cb73e257f47ae8b..c9e1207ef0251a5b402bcc8d5e5de2d52e3661e4`，包含 `4ca0fd89`、`c9e1207e`。已读第三轮报告和 Owner 选择的完整修复要求；不重开 A3、B3 或其他关闭项。

**结论：A1b 尚不能关闭。** 路由开放前保存恢复时点、移除 up/down 和 10 分钟上限的修正成立；但旧 claim 会掩盖短停服的恢复边沿，仍可能在恢复不足 30 秒时报主机失联。另有部分 API 实例未就绪时反复重置宽限、持续压住真实失联的情形。guard 新增的数据库操作还存在无截止时间的等待路径。

下列产品代码位置均相对于 `~/agent-work/r3-35/`；明确写出的 infra 路径是工作区现有清单的辅助静态证据，不代表集群实测。本轮探针、日志及报告均位于本审查目录。

## A — A1b 的两项阻断

### A-1：旧 claim 保持 up，短停服恢复时不更新恢复起点

位置：`api/internal/agentrt/controller/presence.go:120`、`:122`、`:60`、`:68`、`:145`、`:152`；`api/internal/agentrt/store/presencelive.go:74`、`:82`。

`claimed` 接受 30 秒内的历史 claim，并与 probe 的当前答案 OR 后交给 `platformSeen.see`。只有合并后的 up 从 false 变 true 才更新 back。因此，probe 已经连续失败，但旧 claim 尚未过期时，状态仍是 up；若 API 在 claim 过期前恢复，就完全没有恢复边沿。probe 失败期间把 judge 固定在 last，能避免当时按当前时间误判，却不能保护随后恢复到当前时间的判读。

可复现时序（单位：秒）：

| 时间 | 证据及实际 controller 行为 |
|---|---|
| 0 | workers 起点、主机最后一次 contact/claim；probe 为 yes。 |
| 1–24 | API 停服；5、10、15、20 的 probe 均为 no，但 last=0 仍在 30 秒内，合并后的 up 一直为 true；judge=0。 |
| 25 | API 恢复并回答 yes；合并后的 up 没变，back 不更新为 25。 |
| 35 | 实际调用 `store.Presence` 的 judge=35、since=0；对于 contact=0、无 prune、active 且无 stop/drain 的主机，生产 SQL 的两项沉默判断都已超过 30 秒。距平台恢复只有 **10 秒**。 |

这足以触发后续失联记录：`api/internal/agentrt/store/presencepass.go:125` 根据 `ReportedOffline` 生成 down turn。若主机只是在等待停服期间的请求超时及重试，它仍然活着；客户端默认 HTTP 超时为 40 秒（`api/internal/agentd/client.go:108`），claim 出错后还等 15 秒（`api/cmd/agentd/main.go:208`），不能假定它必在恢复后 10 秒内再次联系成功。API 自身读者的新 Back 不会阻止 workers 先写出错误留言。

证据：`probes/controller_review_test.go:185` 的 `TestReview529ShortOutageRetainsOldFloor` 执行真实 `Controller.Presence`，由数据库替身捕获上述实际 SQL 参数，再按生产 `hostSilentSQL` 的时间表达式做 Go 模型计算。结果确认 +35 时 floor 仍为 0、模型判 lost。**没有执行 PostgreSQL 或实际写入 host_offline**，不将模型冒充真库故障注入。

修正方向：区分“曾在 last 接过请求”和“当前连续接入已恢复”。历史 claim 可以支持按历史时点判读，但不能让已观察到的接入中断在恢复时丢失宽限；同时须保留新 claim 持续到达时对错误 probe 的纠正能力。现有长停服测试在 claim 已过期后恢复，未覆盖此边界（`api/internal/agentrt/controller/presence_test.go:209`）。

### A-2：一次探测失败不是整个 Service 停服；部分实例未就绪可反复压住真实失联

位置：`api/internal/server/agentrt_wire.go:474`、`:484`、`:497`；`api/internal/agentrt/controller/presence.go:69`、`:122`、`:130`、`:142`；`api/internal/server/server.go:627`。

workers 每轮只向 Service 发一个请求；命中未就绪实例便记为 no。已有 API A 始终可接入，而新实例 B 的 agentrt 尚未就绪时，Service 仍可能把探测送到 B：现有 `bifrost-trade-infra/k8s/base-platform/manifest.yaml:53` 的 readiness 只检查 `/health` HTTP 状态，`server.go:628` 对 `agentrt_ready=false` 也返回 200。

假定所有被监控主机确实在 t=0 停止联系，因此没有后续 claim 兜底；A 始终服务，探测因端点选择或连接重建而每 5 秒交替 yes/no。claim 过期后，每个 no 令 up=false，每个 yes 又把 back 改成当前时点。于是每个可以判读的 pass 都处于新宽限内；每个不可判读片段又不足 2 分钟，`presence_unjudged` 也不触发。

证据：`probes/controller_review_test.go:260` 的 `TestReview529ServiceEndpointFlapsKeepResettingFloor` 用上述输入驱动真实 controller，至 +300 秒，传给生产 SQL 的 floor 已反复推进到 +300 秒，真实失联仍被宽限压住，未产生 unjudged 告警或留言。SQL 时间判断仍为离线模型；没有模拟真实 Kubernetes 路由分配。

因此 BRIEF 中已知限制所称“恢复时点后移一次”，**没有代码上的一次性约束或延迟上限**。若连接持续落在未就绪 B，虽能在两分钟后收到不可判读提示，A 持续可接入时的真实主机失联仍不能按时判断；若交替命中，则连这条提示也可能长期没有。这是验收要求涉及的多实例能力情形，不声称当前生产已运行两个 API 副本。

修正方向：让作为停服依据的负证据能反映 Service 整体可接入性，例如从服务端点选择中排除 agentrt 未就绪实例，并验证部分实例故障时的探测行为；不能仅凭一次失败不断重置全局宽限。现有网络测试预先假定退出实例已从 Service 路由中消失（`api/internal/server/agentrt_wire_test.go:385`），没有覆盖 ready/unready 混合端点。

## B — guard 的新增数据库操作可阻塞判定循环

### B-1：claim 读取和 unjudged 开关操作在原有超时保护之外

位置：`api/internal/agentrt/controller/presence.go:109`、`:117`、`:134`、`:138`、`:152`；`api/internal/agentrt/store/presencejudge.go:31`、`:90`、`:98`、`:101`。

3 秒 pctx 只包住 HTTP probe，随后取消；`LatestClaim`、`PresenceUnjudged`、`PresenceJudged` 使用原始循环 ctx。原有 20 秒截止时间和事务内 lock_timeout 要进入 `store.Presence` 才建立（`api/internal/agentrt/store/presencepass.go:67`、`:72`），无法约束这些新增前置操作。`presenceJudging` 本身也未设置截止时间或 lock_timeout。

例如已有 unjudged 告警，API 恢复后，清除操作先等待 chief 的 advisory lock；该锁若被长事务占住，pass 无法到达主机失联判定。同样，probe 错误时若数据库池获取或 LatestClaim 读取卡住，就无法推进到两分钟不可判读提示。循环串行等待 pass 返回后才执行下一轮及失败跟踪（`api/internal/agentrt/controller/controller.go:648`、`:658`），因此长等待期间也不会靠 controller_failing 自动补报。

证据：`probes/controller_review_test.go:362` 的两个子探针调用真实 controller，在连接池入口和清除告警所需的真实 writerLock 调用处捕获 ctx，确认没有 deadline；后一条路径在锁调用前也没有设置 lock_timeout。替身立即返回受控错误，**没有制造真实锁等待，也没有实测数据库的默认超时**。确认的是新增路径缺少应用侧上限；连接池获取本身也不能由服务器 statement_timeout 保证有界。

建议把 guard 的数据库操作纳入整个 pass 的截止时间，并为状态开关的锁等待保留有界失败及重试。此项只针对本轮新增 guard，不重开已关闭的 prune 最后一次 touch 问题。

## C — 已确认的修正、验证与限制

### 成立的部分

- **路由恢复时点的开放顺序已修正。** `api/internal/server/agentrt_wire.go:325` 先存 back，再公布 pool；API.Back 在接线时已绑定（`:97`）。实际 `lateDB.open/Ready/Back` 和 `handleHealth` 的离线组件探针通过，见 `probes/server_review_test.go:21`。这里的假 pool 仅作为 readiness 标记，未调用其连接方法。
- **API 自身读者使用本次路由就绪时点。** `/hosts` 在 `api/internal/agentrt/agentrtapi/controls.go:164` 传 Back，实际 handler 参数探针通过（`probes/api_review_test.go:37`）；`/progress` 在 `api/internal/agentrt/agentrtapi/plan.go:231` 调用 `ProgressSince`，后者传入同一 since（`api/internal/agentrt/store/progress.go:247`）。后一路为静态接线核对，未跑真库投影。
- **旧共享 up/down 依赖和 10 分钟上限已移除。** 对 agentrt/server 源码搜索不再有 `MarkPlatformUp/Down`、`PlatformDownLimit`、`platformBackSQL` 或 `presence:platform`。第三轮针对其流头和 cap 的探针不再适用，未保留旧断言误判新实现。
- **长停服和 workers 重启的正常时序成立。** 真实 controller 加串行数据库替身验证 15 分钟停服期间没有能判 lost 的输入；一次 unjudged 告警及留言，恢复时一次 note 及留言；恢复后 30 秒内不满足 lost，+35 秒满足。workers 单独重启也以其 start 为下限。见 `probes/controller_review_test.go:215`；时间判断是模型，不是 SQL 实测。
- **错误 probe 的兜底与正常清除成立。** 有持续新 claim 时，controller 按 latest claim 判读并返回包含 URL/原始错误的错误；真实 `Presence → track → AlertFailingLoop/NoteLoopPasses` 的串行探针确认稳定同类错误只记一次 controller_failing，probe 恢复后一次 note 清除，后续成功 pass 不重复。见 `probes/controller_review_test.go:284`、`:322`。该告警链测试使用空主机 SQL 替身，不证明真实主机判定结果。
- **稳定状态下没有发现 guard 留言洪泛。** 实际 `PresenceUnjudged/PresenceJudged/Append/postMessageAs` 连续调用各 10 次，只得到一个告警、一个恢复 note、两条留言（`probes/controller_review_test.go:301`）。静态上状态开关先取 seat 锁及流锁，再重读流头（`api/internal/agentrt/store/presencejudge.go:98`、`:104`），具备去重设计；替身不验证 PostgreSQL 并发或回滚。此结论不消除 A-1/A-2 的证据状态错误或 B-1 的等待问题。

### 实际执行

所有 Go 命令使用 BRIEF 指定的共享 `GOCACHE`、`GOMODCACHE`，`GOPROXY=off GOSUMDB=off`，并设 `-mod=readonly`、`GOTOOLCHAIN=local`、`GOTELEMETRY=off`；TMPDIR/GOTMPDIR 指向本目录的 `tmp/`。显式移除真库、Redis 测试开关和 fixture 写入开关。

| 检查 | 结果与证据 |
|---|---|
| 目标提交范围 `git diff --check` | 退出 0。 |
| `go test ./internal/agentrt/... ./internal/server ./cmd/agentd -run '^$'` | 退出 0，只编译测试；见 `go-compile.log`。 |
| 10 个 TestReview529 顶层离线探针 | 退出 0；见 `go-probes.log`。其中 A-1、A-2、B-1 的 PASS 表示成功复现缺口或确认缺少截止时间，不能算产品通过。 |
| 实现者的真库测试 | `TestPresenceWaitsForThePlatform`、`TestAWrongProbeDoesNotSilencePresence`、`TestPresenceCannotBeJudgedIsTold`、`TestTheRoutesOpenWithTheirMoment`、`TestHostsAndControlEdges` 均因未设 AGENTRT_TEST_PG 而 SKIP，不能计为通过。 |
| 目标工作树 | 审查前后 `git status --porcelain` 为空；没有修改目标文件。 |

第三轮 A1b 探针的适配：开放顺序探针改验实际 `lateDB.open` 的先存时点；hosts handler 探针改验 Back 参数；时间边界探针改为驱动实际 controller 并捕获生产 SQL 参数。旧 MarkPlatformUp/Down 流头探针因相关实现删除而不再适用。不重跑范围外 A3/B3 探针。

没有联网、使用集群/MCP/SSH、提交、启动 PostgreSQL、绑定端口或写入本目录与共享缓存之外。`TestTheWorkersAskTheAPIThroughItsService` 会建立 httptest 监听端口，因此没有运行；替代探针使用内存 RoundTripper，核对真实 `apiTakesCalls` 的 ready/未就绪/错误状态/错误 JSON/取消，以及 workers 的默认 URL 接线（`probes/server_review_test.go:60`）。

未验证：真实 PostgreSQL 的 SQL 结果、执行计划、并发锁及取消耗时；完整启动/停服/重连与 HTTP listener 的联动；真实 Kubernetes 端点移除、负载分配及连接复用；OOM/节点丢失、双副本、STG 故障注入；Console Vitest 或浏览器展示。没有把离线替身或时间模型描述成这些环境的实测。

可复跑离线探针：

```sh
export GOCACHE="$HOME/agent-work/.cache/go-build"
export GOMODCACHE="$HOME/agent-work/.cache/go-mod"
export GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local GOTELEMETRY=off
export TMPDIR=/Users/vision-mac-trader/agent-work/codex-review-529/tmp
export GOTMPDIR="$TMPDIR"
unset AGENTRT_TEST_PG AGENTRT_TEST_REDIS AGENTRT_TEST_REQUIRED CONSOLE_PRESENCE_FIXTURE_WRITE
go -C /Users/vision-mac-trader/agent-work/r3-35/api test -mod=readonly \
  -overlay=/Users/vision-mac-trader/agent-work/codex-review-529/overlay.json \
  ./internal/agentrt/controller ./internal/agentrt/agentrtapi ./internal/server \
  -run '^TestReview529' -count=1 -timeout=90s -v
```

### 留给 Owner 的选项

1. **推荐：A1b 保持未关闭，另行决定是否授权修正 A-1/A-2/B-1。** 验收应补短于 claim 有效期的停服恢复、部分实例长期未就绪且所有主机真实停止联系、guard 连接池/锁等待的有界失败；保留已成立的长期停服保护和去重清除行为。本轮不自行实施或开启下一轮。
2. **明确接受收窄边界。** 接受短停服恢复后可能提前报失联；只在探测持续命中可接入实例、guard 数据库调用及时返回时承诺检测预算；部分实例故障可能长期压住主机告警。该选项不符合此前完整修复的验收承诺，须由 Owner 明确选择，不能默认签收为 A1b 已关闭。

先修

END OF REPORT
