> 复核 526（Codex gpt-6.1-sol，xhigh），对象 bifrost-platform 分支 `w31/r3-35-online`（第 3 轮 3.5 在线状态）。报告里的 `probes/`、日志等证据在本机 `~/agent-work/codex-review-526/`，不进仓库。

# Review 526 — W-31 round 3 / 3.5 在线状态

审查对象：`bifrost-platform` 的 `c5ad80c2caba48e976ab1b79aee6c49cff91c2ea..95ac365efd28a677aba7e77d0376282dd625993b`，工作树 `~/agent-work/r3-35`。已核对 HEAD 和干净状态，阅读全部 26 个文件的改动，并沿领取、租约、控制、消息、角色和 Console 读取路径检查。以已定的 CUT option A 为范围；未修改被审查工作树，未联网、访问集群、调用 MCP、SSH、启动数据库或监听端口。

发现 **A × 2，B × 2，C × 0**。A1 是 30 秒阈值与现有 agentd 正常维护路径的冲突；A2 是三态未知被恢复留言错误地表述为全面恢复。

## A：STG 前必须修

### A1 — 同步分支清理期间，会把仍工作的主机与执行者误报为失联

位置：`api/internal/agentrt/store/progress.go:44`；传播位置：`api/internal/agentrt/store/progress.go:142`、`api/internal/agentrt/store/presence.go:46`、`api/internal/agentrt/store/presence.go:179`。

30 秒的依据只考虑了长轮询内部每秒一次的 `ClaimNext`，漏掉了两次领取之间的同步维护。现有 `api/cmd/agentd/main.go:174` 每 10 分钟先调用 `d.Prune(ctx)`，返回后才到 `main.go:205` 发下一次 claim。`api/internal/agentd/prune.go:31` 给这轮清理 **2 分钟**工作预算，另有 30 秒报告预算；`prune.go:119` 查询清理清单，`prune.go:137` 顺序读取、删除分支，其间都没有 claim 或主机存活刷新。仅服务端清单收集本身就允许 30 秒（`api/internal/agentrt/agentrtapi/prune.go:32`）。

触发条件：在线主机最后一次领取后进入正常分支清理，该轮耗时超过 30 秒。下一轮 presence 会把它报为 offline；若它是唯一提供者，相应执行者也被报为 unavailable，Chief 留言会称相关岗位不能接活。其上运行的尝试即使独立心跳仍新鲜，也会先被 `TaskStatus` 显示成 `host_lost`。清理完成、领取恢复后，又发一轮恢复留言。清理耗时在既有预算内，不能据此认定机器或执行者掉线。

离线探针 `probes/prune_review_test.go` 调用了真实 `Daemon.Prune`，仅用内存 HTTP transport 代替清单读取，将模型时钟推进 35 秒后成功返回空清单，无网络、实际等待或 Git 删除。随后用真实 `TaskStatus` 判定新鲜心跳的 running 尝试，得到：`status=host_lost`、`host h1 last polled 35 seconds ago`。这是控制流及判定复现，**不是 STG 耗时实测**。

修复要求：在采用 30 秒存活阈值前，使存活轮询能够覆盖清理等同步维护，或用其他可靠的存活依据避免这些正常间隔触发失联；补一个覆盖维护期间主机、执行者和尝试状态的回归测试。只改成 45 秒仍覆盖不了现有 2 分钟清理预算。

### A2 — 有岗位可用性仍为 null 时，Chief 留言会错误宣告所有岗位恢复

位置：`api/internal/agentrt/store/presencepass.go:267`；相关计算：`api/internal/agentrt/store/presence.go:324`。

`jobs_without_executor` 只收集“每个候选都已知不可用”的岗位；某候选为 null 时，该岗位不在这个列表中。`presenceNote` 却把“列表为空 + 任一执行者恢复”直接当成所有岗位都有可用执行者，写出 `Every job has an executor that can take it again.`。

正常的主机加入或升级过渡即可产生这种数据：h1 已记录提供 claude，h2 在线但尚未记录 offered；planner 的 claude 已知可用，implementer 的 codex 仍是 null。若 claude 此前有未恢复告警，本轮会报 claude 恢复，同时错误声称 implementer 也能接活。这里应保留未知，不能把没有确认故障当成确认恢复。

`probes/presence_review_test.go` 的 `TestReview526RecoveredExecutorDoesNotProveAllJobs` 用真实 `judgeExecutors → presenceTurns → presenceNote` 复现了上述结果；数据库替身只返回先前未恢复的告警。

修复要求：只有确认每个岗位至少有一个可用候选时才输出全面恢复；否则只报告已确认恢复的执行者，或明确仍有未知岗位。补“一个恢复、另一个 null”的留言断言。

## B：应修

### B1 — drain / stop / retired 的豁免没有覆盖恢复播报

位置：`api/internal/agentrt/store/presencepass.go:105`。

离线方向用 `ReportedOffline` 排除了非 active、drain 和 stop；恢复方向仅检查 `open && h.Online`。因此先离线并播报，再由 Owner drain/stop 的主机，在维护中恢复轮询时仍会发送 back-online 事件和 Chief 留言。退休状态也没有恢复方向的过滤。现有领取代码会先更新 `last_poll_at`，然后才按主机状态和控制拒绝接活（`api/internal/agentrt/store/claim.go:100`），所以这种组合可以真实出现。

这违背了此次审查要求中对这些主机不播报的约定；它报的是轮询恢复，未直接把执行者判成可用，因此列 B。离线探针已分别复现 drain、stop 下仍生成恢复 turn。应统一两个方向的适用主机范围，并明确维护期间如何结清原告警，避免解除维护后再补发过时恢复。现有 `TestPresenceSaysNothingItDoesNotKnow` 只测试没有历史告警时的静态豁免，抓不到此路径。

### B2 — 最新状态查询的扫描量随历史增长，没有固定成本上界

位置：`api/internal/agentrt/store/presencepass.go:134`、`api/internal/agentrt/store/presence.go:51`、`api/internal/agentrt/store/presence.go:53`。

这些查询按流、seq 倒序，再过滤 JSON 中的 offered / rule / line_digest / 恢复文字。现有 `api/internal/agentrt/migrations/0001_core.sql:221` 的唯一索引支持流内倒序，却不能直接定位每一种状态的最后记录；没有匹配记录时会检查整条流，有匹配时也须越过之后的无关事件。尤其每个 executor 各查一次共享 controller 流：某个执行者从未不可用，另一执行者持续转换或循环持续报错，它就会每 5 秒反复检查不断增长的历史。HostsSQL 对没有 disk 记录的主机也有同类情况，且 `/progress` 会再次执行这些读取。

当前主机和执行者数量少、状态事件稀疏，不能仅凭静态分析声称 STG 已经超时；但 `LIMIT 1` 并不保证扫描一行，也不能证明“大量事件下仍满足预算”。建议采用能直接读取各状态最新记录的查询/存储安排，并以大量无关事件及“从无匹配记录”的数据检查执行计划和耗时；不能简单加时间窗丢掉仍未恢复的旧告警。此次环境不能运行数据库，未做 EXPLAIN 或负载测量。

## 六项核对结论

### 1. 转换、并发和时间边界

- 主机离线条件是严格 `age > 30 s`，恰好 30 秒在线；`/hosts`、`/progress` 和 controller 共用 HostsSQL，比较口径一致。
- `Presence` 使用 READ COMMITTED 事务，初读发现变化后先获取 Seat 的事务级 advisory lock，再重读视图和历史状态（`presencepass.go:75`）。所有转换记录和一条合并的 Owner 留言同事务提交。正常提交、随后重启和多副本重入的去重设计成立；事务失败不会只留下告警而丢失对应留言。未在本次环境重跑真库并发验证。
- `api/internal/server/agentrt_wire.go:123` 只在 `RunsWorkers()` 时启动 controller；部署声明 API 为 `PLATFORM_ROLE=api`，workers 为单副本 Recreate。API 正常配置下不跑此循环；`all` 或未知角色的回退可让其他进程也运行，Seat 锁仍负责去重。
- 没提供、提供者全离线、账号冷却、额度停止线四类原因均使用运行时已有数据，provider/model 匹配、默认账号、quota 比较与现有 claim/pick 路径一致。磁盘、状态和全局/主机控制也参与可用主机筛选；没有把满槽或单项任务的授权限制当成全局执行者故障，符合此次 option A 的定义。
- 可用主机尚无 offered 记录时，判定为 null；`presenceTurns` 跳过 null，Console 红字只看 `available === false`，没有发现 false-unavailable 路径。A2 是后续全面恢复文案丢失了这层未知。
- 5 秒循环在每轮及时完成的条件下，首次检测落在 **(30, 35] 秒**；Console 再加一次 5 秒读取，理想预算为 40 秒。20 秒 pass timeout、5 秒锁等待上限不是 35 秒完成的证明。A1 和 B2 也说明不能仅凭常量相加作完整验收。

### 2. HostLostAfter 全部生产使用点及副作用

以下是该 store 常量的全部实际生产读取点；其余搜索命中为注释和测试。

| 使用点 | 影响与判断 |
| --- | --- |
| `api/internal/agentrt/store/progress.go:142`，TaskStatus | 提前把活着尝试的显示状态及任务/mission 汇总状态判为 host_lost，reason 改为秒/分钟。它不把 attempt 行改为 lost，也不暂停 mission。A1 会造成误显示。 |
| `api/internal/agentrt/store/presence.go:222`，readPresence | 向 HostsSQL 传入 30 秒，供 `/progress` 与 presence 循环使用；影响在线、执行者可用性及新通知。A1 的通知传播路径。 |
| `api/internal/agentrt/agentrtapi/controls.go:164`，listHosts | 向相同 SQL 传入 30 秒；只读显示，边界一致，同受 A1 影响。 |
| `api/internal/agentrt/store/presencepass.go:206`，lastPollWords | 将阈值写入告警说明；没有额外控制副作用。 |

`HostsSQL` 自身接收秒数参数。租约续期/失效、claim、envelope 和告警执行动作没有读取此常量：`LeaseTTL=120 s`、`Grace=15 min` 未改（`store/kernel.go:42`），Sweep 仍按 lease expiry 判断。不能把此次 UI 的 host_lost 当成租约已失效。旧 `agentthreads.Config.HostLostAfter` 是另一个独立字段，仍为 3 分钟，未被这次修改连带改变。

正常 Recreate 发版若使领取中断超过 30 秒，仍可能产生离线/恢复对；代码没有发布期豁免，且本次不能测实际发布中断。因此 CUT 验收第 3 步仍未完成，不能断言“30 秒已证明发版不假报”。这与 A1 的同步维护路径是两个需要分别覆盖的来源。

### 3. 写量和负载

`RecordHostOffered` 在每个 HTTP claim 请求开始时调用一次，没有放进每秒的 ClaimNext 循环。工具列表排序、去重后比较，不同才锁 host 流，锁后再比较再写；相同列表、仅顺序变化不会增加 note。稳定状态下 presence 只读，不新增事件、artifact 或消息；有变化时每个实体一条转换记录、每个 pass 一条合并 Chief 留言。没有发现按每次轮询写 offered 或在内存保存无界历史的行为。

事件和消息按真实变化追加，历史本身继续增长；读取成本问题见 B2。`readPresence` 还读取完整 capabilities（包括本次判定不用的 restrictions/competence）、job 和 pool；主机存活尝试计数也没有专门的 host_id 索引。小规模下可接受，但未有本轮真库负载证据支持大规模成本结论。运行尝试的留言清单以 10 条为限（`presencepass.go:220`）。

### 4. 隐私和角色

没有新增路由或扩大读角色。新增内容是主机/任务/岗位/执行者标识、提供方/模型名、最后领取时间、控制/磁盘布尔状态及账号冷却/额度说明；没有复制任务正文、Owner 对话、日志尾部或凭证。Chief 通知继续走原有 Owner–Seat 消息与 artifact 权限路径。未发现本次变更引入的秘密或私密正文泄露。

### 5. Console

For you 的主机条目、排序和计数已改用 agentrt 的 `reported_offline`；silent threads 与容量拒绝信息仍保留。旧 host 供应商接线/监测信息不再计入 For you，这是已定 CUT 明确要求的退役源切换；相关状态页组件仍保留，未发现顺带删除线程功能。因禁止联网，本轮未重新核实“旧 hosts 已无人写”的运行事实，依据是给定 CUT 与退役计划。

Work/System 红字直接消费 `/progress` 的 `reported_offline`、`available`、`jobs_without_executor`，与 controller 共用服务端判定，没有前端另算阈值。Crew 增加 offered/executors 文本，布局变化局限于展示这些数据；未发现无关改版。Chief 页与 runtime 查询确为每 5 秒刷新。上述显示会如实传播 A1；A2 则只出现在平台留言的全面恢复断言中。

### 6. 测试能证明什么

- `TestPresenceIsToldWithinTheBudget` 用真实 PostgreSQL 的注册/领取数据，通过 `Controller.Now` 推进判定时钟，覆盖 0、1.3、2.5、4.999 秒相位，直接调用 `Presence`，断言 (30,35] 秒、两项转换合并一条留言、重建 Controller 后不重复及恢复留言。不是 mock 数据库，但也没有启动 `Start/every` 或真实计时全链路；quota、规则和事件时间仍有数据库/真实时钟读取。
- store 测试覆盖恰好 30 秒、刚越界、重复轮次、主机恢复、四种执行者故障原因以及四个并发 pass 的合并计数。转换数和留言数能抓到覆盖情景中的重复和漏报。offered 测试覆盖重复请求、顺序变化和清空；没有并发 claim 的专项断言。
- “not offered” 子测试在第一次 presence 前就已是未提供状态，并容许该轮产生告警（`store/presence_test.go:218`），所以证明了初始不可用只报一次，未单独证明从可用变成未提供的转换。其他三类先验证无变化，再改变数据。
- 这些测试没有覆盖同步清理造成的领取空档、已有告警的维护主机恢复、恢复与 null 并存、大量历史事件、Recreate 发布时延。Console 的预算测试只检查刷新常量；真库 fixture 的展示测试也不是 40 秒端到端验收。

## 本轮实际验证与限制

全部 Go 命令使用简报指定的离线 GOCACHE/GOMODCACHE、`GOPROXY=off`、`GOSUMDB=off`，临时目录位于本审查目录；npm 配置为离线共享缓存。

- **通过**：目标 Go 包编译；`TestTaskStatusOrder`、`TestLiveOrder`、`TestAHostThatNeverPolledSaysTheResultIsNotPersisted`；platform-api 离线构建；Console `tsc --noEmit --incremental false`；`git diff --check`。
- **通过的缺陷复现探针**：本目录 `overlay.json` 将两份探针虚拟加入 store 测试包，运行 `go test -mod=readonly -overlay=/Users/vision-mac-trader/agent-work/codex-review-526/overlay.json ./internal/agentrt/store -run '^TestReview526' -count=1 -v`。四项均通过，即观察到 A1、A2、B1 所述现行为，并确认普通升级未知值维持 null。探针不代替真库测试。
- **跳过**：新 presence/store/controller 真库测试及 Host/API 边界测试。本轮显式移除数据库/Redis 连接环境变量，不尝试连接或启动服务。简报称实现者已以 `AGENTRT_TEST_REQUIRED=1` 运行、分支 CI 也运行，属于提供的证据，未在此独立重验。
- **未能执行**：两组 Console Vitest，使用本目录配置把缓存定向到本目录，进程启动即报 `ERROR: SecItemCopyMatching failed -50`，退出 139；换用已安装的 Node 24 同样失败，未到测试断言阶段。类型检查通过不能替代这些测试。
- **未核验**：真实数据库执行计划、负载/锁竞争、STG 故障与恢复时延、Recreate 发布、运行中旧 hosts 数据、实际页面视觉效果。没有据此编造通过结论。

先修：A1（同步清理触发失联误报）、A2（未知岗位被宣告全面恢复）。

END OF REPORT
