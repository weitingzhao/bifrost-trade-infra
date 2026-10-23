> 复核 530（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/r3-35-online`（第 3 轮 3.5 在线状态）。报告里的 `probes/`、日志等证据在本机 `~/agent-work/codex-review-530/`，不进仓库。

# Review 530 — W-31 3.5，第五轮窄确认

审查范围：`~/agent-work/r3-35` 的 `c9e1207ef0251a5b402bcc8d5e5de2d52e3661e4..75c3d6f4b55b75990c10bee5123d37e77c58a059`，仅 `10ef3050`、`75c3d6f4` 对 review 529 A-1、A-2、B-1 的修正及其直接边界。不重开其他关闭项。

**结论：先修。A-1 可以关闭；A-2、B-1 仍未关闭。** 五连接采样已按 Owner 选择实现，但不能据此承诺部分实例故障时的确定告警时限；20 秒 deadline 已覆盖 guard 的正常调用路径，但事务错误后的回滚仍可无限等待。

| 项目 | 关闭判定 | 代码与测试依据 |
|---|---|---|
| A-1：旧 claim 掩盖短停服恢复 | **关闭** | `api/internal/agentrt/controller/presence.go:53` 独立记录 probe 的中断／恢复，`:161` 取三个起点的最大值；原探针改为正确断言后通过，25 秒、5 秒、连续两次中断均在恢复后 +35 秒首次满足失联模型。 |
| A-2：部分实例未就绪反复推进起点 | **未关闭** | `api/internal/server/agentrt_wire.go:495` 的五次采样能解决双端点严格轮询情形，但全失败批次仍可反复触发 `presence.go:59`、`:161`；真实 aggregator + controller 的离线组合探针复现持续压住失联。详见 A。 |
| B-1：guard 数据库等待无上限 | **未关闭** | `presence.go:112` 和 `api/internal/agentrt/store/presencejudge.go:97` 修好了调用 context 与锁超时；但 guard 所用 `api/internal/agentrt/store/write.go:28` 在回滚时移除 deadline。真实 pgx + 内存协议探针复现越过截止时间。详见 B。 |

下列产品路径相对于 `~/agent-work/r3-35/`；`probes/` 和日志相对于本审查目录。infra 清单仅作静态辅助证据，不代表线上配置。

## A — A-2 仍是概率缓解，部分可用时仍能长期不报真实失联

位置：`api/internal/server/agentrt_wire.go:477`、`:485`、`:495`；`api/internal/agentrt/controller/presence.go:59`、`:141`、`:149`、`:161`。

实现符合已选的机械方案：每轮启动五个并发请求，禁用连接复用，任一 ready 就成功，全部失败才判 no；失败原因排序去重。双端点严格逐连接轮询时，单个未就绪实例不再制造整个 pass 的 no。这部分成立。

但**五条新连接不保证覆盖五个不同端点，也不保证至少命中一个就绪端点**。`1/32` 只适用于两个等权端点、每条连接独立随机选择的假设；即便完全满足该假设，连续出现多轮全失败的概率也不为零。当前代码没有给恢复起点的反复推进设上限，也没有为“不断重置宽限、一直无法完成判定”另计持续时间。每个孤立 no 后的 yes 都再给 30 秒，短 no 片段又达不到两分钟的 `presence_unjudged` 门槛。

`probes/server_extra_test.go:204` 的 `TestReview530ServiceSamplingAndPresence` 把真实 `serviceTakesCalls` 接到真实 `Controller.Presence`；HTTP 用内存 RoundTripper，数据库替身捕获真实 HostsSQL 参数，再按生产沉默表达式计算模型。所有主机最后联系均在 t=0，之后没有 claim；假设始终有一个 API 端点可以服务。结果如下：

| 端点分配输入 | 结果 |
|---|---|
| 两端点按请求轮询，一个始终 ready | +35 秒首次满足失联模型；未触发 unjudged。 |
| 两端点按请求轮询，每轮交换谁 ready | +35 秒首次满足失联模型；未触发 unjudged。 |
| 仅 +25 秒那一轮五次全落到未就绪端点，其余轮正常 | 恢复起点变为 +30 秒，首次满足失联模型在 **+65 秒**。一个坏批次已足以打破持续服务时的 +35 秒预算。 |
| +25、+55、+85……每 30 秒一轮五次全失败，其余轮正常 | 到 +300 秒起点已推进到 **+300 秒**，失联一直不满足模型；**无 unjudged 告警、无留言**。相同序列可继续，代码没有总延迟上限。 |
| 所有采样始终落到未就绪端点，但另有 ready 端点 | 不判断主机；两分钟门槛后一次 unjudged 告警和留言。避免了完全静默，但仍不能按时检测真实失联。 |
| 全部端点确实未就绪 | 同样暂停判断并产生一次 unjudged，符合停服保护。 |

这不是仅把旧探针的单次结果直接塞进 controller：五个采样的真实聚合函数也参与了复现。测试通过表示成功确认上述行为，**不表示失联告警已通过验收**；没有执行真实 SQL、写出真实 host_offline 或实测 Kubernetes 调度。

实现者的 `api/internal/server/agentrt_probe_test.go:28` 测试 Service 在 `:35` 强制逐连接轮询。该输入可以证明这类分配已修好，不能代表真实 kube-proxy 的所有模式。iptables 随机选择不会保证每批覆盖；IPVS 需要结合调度器、其他连接和实际配置判断，不能等同于这个只接测试流量的严格轮询替身。conntrack 让已建立连接的流量保持后端映射；禁用 HTTP keep-alive 消除了复用旧连接的问题，并未取得端点覆盖保证。若 Service 开启 ClientIP 亲和，同一 workers 源 IP 的五条新连接也可能持续落在同一个未就绪端点。缓存中 Kubernetes API 的定义明确支持 ClientIP 亲和及默认 10800 秒粘滞期（`~/agent-work/.cache/go-mod/k8s.io/api@v0.32.3/core/v1/types.go:5243`、`:5261`）。

静态检查的现有 `bifrost-trade-infra/k8s/base-platform/manifest.yaml:176` 没有设置 sessionAffinity；不能声称当前生产已启用亲和，或当前生产正在受此故障影响。本轮不能检查线上 kube-proxy 模式、真实 conntrack 或实际端点权重。即使没有亲和，前述重复坏批次仍是随机采样允许的输入。

**给 Owner 的选项：**

1. **保留确定时限要求（推荐）**：继续保持 A-2 未关闭，决定是否允许引入能反映整体 agentrt 可接入性的可靠入口／聚合证据；验收必须覆盖重复全失败批次和持久端点偏向。仅继续增加采样数不能给出确定保证。任何放宽 readiness／RBAC 等限制的决定由 Owner 作出，本轮不实施。
2. **明确接受概率承诺**：将多实例部分故障时的“35 秒内告警”改为有部署前提的概率目标，明确不保证最坏延迟，并决定如何对反复推进起点但未完成判定的状态发出提示。这样可签收五次采样方案，但不能把现有实现描述成已经消除长期压住告警的可能。

## B — B-1 的正常调用已有限时，错误回滚仍能拖住整个 pass

位置：`api/internal/agentrt/controller/presence.go:112`、`:136`、`:157`、`:169`；`api/internal/agentrt/store/presencejudge.go:92`、`:97`；`api/internal/agentrt/store/write.go:28`；`api/internal/agentrt/controller/controller.go:652`、`:663`。

新建的 20 秒 parent context 确实传给 probe、LatestClaim、PresenceUnjudged／PresenceJudged 和 store.Presence；状态开关事务在读流头前设置 `lock_timeout='5s'`。原 B-1 探针已检测到 deadline 和 lock_timeout；新增阻塞连接池替身在约 51 ms 的缩短预算内返回 deadline error。这些修正成立。

遗漏发生在事务返回错误后的清理：guard 的 `LatestClaim` 与状态开关均走 `InTx`。`InTx` 的 defer 调用 `tx.Rollback(context.WithoutCancel(ctx))`，**同时移除了取消信号和截止时间**。若语句先返回普通数据库错误（包括 lock_timeout），而随后的 ROLLBACK 应答迟迟不到，parent deadline 不会再终止该等待。lock_timeout 约束不了等待网络应答。这时 `Presence` 仍未返回，循环也到不了失败跟踪／下一轮重试。

这不是一个新立项去审 common helper：该 helper 早已存在；这里仅追踪本轮 B-1 所声称“整个 presence pass 有界”的 guard 调用链，确认修复仍不完整。

证据：`probes/controller_extra_test.go:76` 的 `TestReview530RollbackOutlivesPassDeadline` 使用当前缓存版本的**真实 pgx 驱动**，以 `net.Pipe` 在内存中提供 PostgreSQL 协议对端。它让真实 `Controller.Presence → LatestClaim → InTx` 收到 SQLSTATE 55P03，然后在真实 ROLLBACK 请求处暂停应答。把 pass 预算缩短为 50 ms，截止时间过去后再观察 100 ms，pass 仍未返回；约 **152 ms** 时主动释放回滚应答，才返回原始数据库错误。若不释放，代码中没有应用侧截止时间。没有 DNS、TCP、端口监听或真实 PostgreSQL；这验证的是驱动及清理路径，不是假装执行真实 SQL 或持有真实锁。

驱动源码也支持该观察：`~/agent-work/.cache/go-mod/github.com/jackc/pgx/v5@v5.11.0/tx.go:220` 的 Rollback 用传入 context 执行 `rollback`；池事务在同版本 `pgxpool/tx.go:37` 原样委托该调用。生产使用连接池不会自行补回这个 deadline。

实现者的 `api/internal/agentrt/controller/presence_test.go:466` 仅覆盖阻塞 acquire 和持有 seat 锁，没有覆盖“先收到数据库错误，随后回滚应答停住”。本轮没有真库独立复测 seat 锁；旧探针确认的是 deadline／lock_timeout 接线，不是实际 PostgreSQL 的取消耗时。

**给 Owner 的选项：**

1. **补齐有界清理（推荐）**：将 presence 所用事务的回滚／连接弃置也纳入明确预算；清理失败须丢弃连接且让 pass 能返回，不用脱离控制的后台 goroutine 隐藏等待。保留普通池等待和锁等待回归，再加入本次“错误后回滚无应答”探针。
2. **接受有界额外清理时间**：若清理必须独立于已取消的 pass context，就给它单独的短上限，并把对外承诺写成“20 秒执行预算 + 有界清理预算”。仍须消除当前的无限等待；不能原样签收为完整有界。

## C — A-1 已关闭；其余验证、负载与限制

### A-1 的代码和回归

`api/internal/agentrt/controller/presence.go:53` 的 probe 状态独立于历史 claim，`:59` 在 no 后首次 yes 记录 probeBack，`:161` 取 Started、合并证据恢复时点、probeBack 的最大值。因此 30 秒内的旧 claim 仍能支持按历史时点判读，但不再抹掉 probe 亲眼观察到的短停服恢复。

原样重跑 `TestReview529ShortOutageRetainsOldFloor` 时，旧缺陷断言失败：+35 秒捕获到的起点已是 +25 秒，而不是 0。保留其时序、改为应当保护恢复宽限的断言后通过。`probes/controller_extra_test.go:17` 的三个时序还确认：25 秒停服在 +25 恢复，+60 首次满足失联模型；5 秒停服在 +15 恢复，+50 首次满足；连续两次中断在 +25 最后恢复，+60 首次满足。均没有在恢复后 30 秒内满足失联模型，也没有在稳定恢复后额外延迟超过一次 5 秒 pass。

这足以关闭 A-1 的“旧 claim 隐藏恢复边沿”缺陷。A 中采样误报中断后反复后移，是 A-2 尚未解决的交互边界，不重开 A-1。实现者的真实数据库测试在 `api/internal/agentrt/controller/presence_test.go:425`；本轮三项子测试均因未设 AGENTRT_TEST_PG 跳过，不能算独立真库通过。

### 五次探测的开销和 20 秒预算

`api/internal/server/agentrt_wire.go:477`、`:498` 每个 workers controller 每 5 秒至多发起五个请求，约每秒一个请求、每轮最多五条新连接；获得 ready 后取消剩余请求。API 角色仍用进程内 Ready，不产生这组 HTTP 探测。`api/internal/server/server.go:607` 的 health 路径读内存状态；`api/internal/server/agentrt_schema.go:100`、`:123` 读取缓存 schema 状态，不是每个探测查数据库。静态上未发现五次探测会直接制造数据库查询或明显的无界并发。

`TestReview530FreshConnectionsWithoutListeners` 用同样 Transport 配置和可接受复用的内存 HTTP 对端，两个全失败 pass 建立了十条新连接；`TestReview530ServiceProbeBudgetAndErrors` 中五个并发挂起请求在约 51 ms 的缩短 probe 预算内共同失败，同一种原因只记录一次。前者是等价 Transport 配置的组件验证，实际 platformProbe 配置本身另经静态核对。

没有测量实际 API CPU、连接追踪表或高负载延迟，不能把每秒一个请求写成容量实测。新的总预算也确实更严格：probe 若用满 3 秒，后续数据库阶段最多剩约 17 秒；旧 store.Presence 的 20 秒不再是额外预算（`api/internal/agentrt/store/presencepass.go:67` 的 child context 不能延长 parent）。因此原来可在单独 store 预算内完成、但总耗时超过 20 秒的 pass 现在会被中断。这是整轮预算的直接含义；未发现普通快速成功路径被无故截断的证据，也没有线上延迟数据证明 17 秒余量足够。B 的回滚遗漏之外，不据此另立未经证实的新缺陷。

### 实际执行与证据

所有 Go 命令使用 BRIEF 指定的共享 GOCACHE／GOMODCACHE，以及 `GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local GOTELEMETRY=off`、`-mod=readonly`；TMPDIR／GOTMPDIR 指向本目录 `tmp/`。显式移除 PostgreSQL、Redis 和 fixture 写入测试开关。

| 检查 | 结果 |
|---|---|
| `git diff --check c9e1207e..75c3d6f4` | 退出 0；目标 HEAD 核对为完整 `75c3d6f4b55b75990c10bee5123d37e77c58a059`。 |
| `go test ./internal/agentrt/... ./internal/server ./cmd/agentd -run '^$'` | 只编译测试，退出 0，见 `compile.log`。 |
| 第四轮指定探针原样重跑 | 见 `round4-original.log`：A-1 的旧缺陷断言失败；B-1 两个旧“没有 deadline／lock_timeout”的断言失败；A-2 的交替 pass 输入仍复现持续重置。旧断言失败是修正证据，不是产品回归。原探针不含五次 aggregator，A-2 另有本轮组合验证。 |
| 调整 A-1／B-1 预期后的旧探针 + 本轮离线探针 | 见 `offline-probes.log`；覆盖真实 controller、guard 写路径和真实 aggregator，含明确标注的数据库替身及时间模型。 |
| 同组探针的最终并发检查 | `-race -run '^TestReview(529\|530)'`，退出 0，见 `offline-race.log`；最终版本另覆盖 ready 端点按轮交换，共 13 个顶层测试。缺陷复现测试 PASS 不等于产品验收 PASS。 |
| 实现者的 A-1／B-1 测试 | 见 `implementer-tests.log`：A-1 三个真库子测试均 SKIP；B-1 的阻塞 acquire 前半段执行后，在真库 setup 处 SKIP，seat 锁部分未执行。 |
| 实现者的 Service 网络测试 | `TestTheProbeAsksOnFreshConnections` 需要 httptest 绑定端口，未运行；`TestPresenceThroughAPartlyReadyService` 需要真库及监听端口，未运行。没有把编译通过当作其行为通过。 |
| 目标工作树 | 审查前后 `git status --porcelain` 为空；未修改目标工作树。 |

可复跑最终离线探针：

```sh
export GOCACHE="$HOME/agent-work/.cache/go-build"
export GOMODCACHE="$HOME/agent-work/.cache/go-mod"
export GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local GOTELEMETRY=off
export TMPDIR=/Users/vision-mac-trader/agent-work/codex-review-530/tmp
export GOTMPDIR="$TMPDIR"
unset AGENTRT_TEST_PG AGENTRT_TEST_REDIS AGENTRT_TEST_REQUIRED CONSOLE_PRESENCE_FIXTURE_WRITE
go -C /Users/vision-mac-trader/agent-work/r3-35/api test -mod=readonly -race \
  -overlay=/Users/vision-mac-trader/agent-work/codex-review-530/overlay.json \
  ./internal/agentrt/controller ./internal/server \
  -run '^TestReview(529|530)' -count=1 -timeout=60s -v
```

未检查：真实 PostgreSQL 的 SQL 判定、事务并发、seat 锁超时／取消耗时；真实 Kubernetes 的 iptables／IPVS／conntrack／sessionAffinity 与端点分配；实际 API 负载、双副本故障注入和 STG／PROD 行为。没有联网、访问集群／MCP／SSH、启动 PostgreSQL、绑定端口、提交或写入本目录与共享缓存之外。

先修

END OF REPORT
