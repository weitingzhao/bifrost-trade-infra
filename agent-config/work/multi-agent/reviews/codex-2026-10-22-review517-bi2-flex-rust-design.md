# Review 517 · BI-2 Flex 插件 Rust 设计复核（第 1 轮）

结论：**先修**。整体替换服务、公开合成夹具与私有真实语料分层、离线影子重放的方向成立；但当前稿有 **9 项 A、4 项 B**。主要问题是两处写错的行为契约、真实错误信息的泄露路径、尚不能可靠判等的录制边界，以及验收、回滚和 Agent/CI 接线缺口。以下只审设计是否满足已确认需求，不复议需求。

证据版本：Flex 插件 `bf6c61ca5318da7bdd928d4dfea782065bc48f7e`；core `a87e39f159c7aae2a4da2d5a62434c46ddec7bb0`；Research 本地 `origin/main` 解析为 `73694cca79d27e1bee07b4cb5a4ed1ac8df57338`；platform `36481b9002a93d25f978b4eaad1253c58c6b4e6f`；infra `b7535a57d884f8227859c643fd129104e22212b0`。代码均经 `git show <sha>:<path>` 读取，未用工作树代替这些版本。下文 `fq/` 指插件的 `src/bifrost_flex_query/`，`core/` 指 core 的 `src/bifrost_core/`；其他路径冠以仓库简称。

## A：决定前必须修正

### A1 · 配置写入并不是“空写令牌时全开”

**设计：** §1.6，DESIGN.md:94–96；§1.7 Q7，DESIGN.md:110。

**代码：** `fq/api/deps.py:28–57`；`fq/api/config_summary.py:134–165`；`fq/orchestration/config_rw.py:225–320`。

普通写接口用 `require_write_token`，空 expected token 时放行；但 `/flex/config/write` 单独用 `require_config_write_identity`。它在 expected token 为空且没有网关头时仍返回 **401**，并不会因为任意 bearer 值而放行。设计把这两个鉴权规则合成一个，会把原来不能写配置的请求放进整表替换 query rows、修改拉取天数的路径。

**修正：** 将鉴权按路由列成矩阵，保留配置写入的特殊规则；至少钉住 expected token 空/非空、缺凭据/错凭据/正确凭据、网关头，以及含 token 字段的配置请求。已用纯合成调用验证上述 401 与普通接口放行的区别。

### A2 · 现金流水没有设计所述的三级回退链

**设计：** §1.3，DESIGN.md:63。

**代码：** `fq/orchestration/trades.py:64–110`；`fq/orchestration/transactions.py:191–200,267–297`。

设计将“query 默认期 → period=5”写成共用规则。实际只有 trades 有这条链。现金流水仅在**单分段、显式完整日期、允许 fallback、首请求报 1003/对应 unavailable 文本**时，再试一次 query 默认期；空成功不回退，第二次失败也没有 `period=5`，多分段禁用回退。照统一规则重写会改变实际现金行的窗口，并多打 IB 请求，引入 token 级限流。

**修正：** 分开列两种作业的回退状态机和请求次数；A 层覆盖空成功、1003、1018、默认期失败、多分段。合成探针已确认现金空成功只调用一次、连续 1003 只调用两次且无 `period` 参数。

### A3 · “历史错误文本只去 query id”会把账户内容带出私有语料

**设计：** §2.2，DESIGN.md:130–133；§2.3，DESIGN.md:139–143；§2.4，DESIGN.md:152；§4.2，DESIGN.md:244；§7，DESIGN.md:293。

**代码：** `core/portfolio/reader/accounts.py:1255–1264`；`fq/orchestration/transactions.py:256–258`；`fq/worker/handlers.py:21–29`；`fq/worker/claim.py:155–188`；`fq/worker/loop.py:181–206`。

现金写入异常以 `str(e)` 原样返回，继而进入 job.result、worker 日志与 freshness；数据库错误可能包含冲突键、失败行、金额和描述，去 query id 不是脱敏。更直接的是 core 的“缺 report_date”分支已经在 WARNING 中输出 account_id、ts、amount、type。用现行 Python 镜像跑真实 B 层时，即使比较器只输出计数，调用链仍可能将真值写入容器日志；sidecar PostgreSQL 的错误 DETAIL 也是独立出口。断言失败、traceback、差异产物同样不能只靠最终 verdict 的输出约定保护。

**修正：** 真实错误全文留在 B 层，公开分类用例由固定错误模板和假值重建。B 层/影子启动时统一约束 Python、Rust、数据库日志和异常处理，只出固定类别、列名及计数；需要调试的真值只能写私有位置。形状导出采用固定结构白名单，不将未知描述经一般字符串替换后直接公开。用带假账户内容、假金额、自由文本标记的故障案例检查 stdout/stderr、PG 日志、测试产物、镜像上下文，证明标记不会出现。

### A4 · “提交后再查同一批键”不是这次 Python 写入的可靠预期

**设计：** §2.2，DESIGN.md:131–133；§2.5，DESIGN.md:163–164；§4.1，DESIGN.md:236；§10.2 第 3 项，DESIGN.md:353。

**代码：** `core/portfolio/reader/accounts.py:686–688,958–975,995–1007,1341–1374,1425–1446,1457–1479`；`core/persistence/postgres/commissions.py:97–115`；`fq/worker/handlers.py:118–133`；`fq/worker/claim.py:192–210`。

core writer 自己开连接并 commit。插件外层在它前后补 SELECT，读到的不是一个原子前后镜像。TWS/网关会更新同一 commission，Ledger 的 `update_one_execution` 会改 Flex 原始行并写 commission，`delete_one_execution` 会删除这两类行。例如录到 commission=A 后，外部写成 B，Flex 本次发来的 0 被 COALESCE 保留为 B；用 A 重放只能得到 A。提交到录制 SELECT 之间的外部修改也会混入“Python 预期”。这不是 Rust 差异，更不能按“噪声”忽略整行。

录制契约还有同一边界问题：1018 会修改**其他 pending 作业**，不只本次作业行；成功的业务行提交、freshness 提交、mark_done 也并非一个事务。只录一个作业前后状态和一个 `now`，不足以证明完整生命周期及数据库中途失败的行为。

**修正：** 先明确录制在真实写连接/事务中的插入点，捕获哪些读取、哪些写入、commit/rollback 结果，以及如何取得或校验不受并发污染的前后版本。外部写入冲突的案例应明确标为不可判等、不得计入验收，不能把差异自动归为框架错误。补齐受影响队列行、数据库/传输错误事件与时钟序列的重放方式。以并发 commission 更新、Ledger 修改、业务已提交但 freshness/job 更新失败的合成场景验证框架，然后才允许 B 层“Python 100% 自证”放行。

### A5 · 无条件忽略代理键和 created_at 会漏掉可见的入库差异

**设计：** §2.4，DESIGN.md:149–151。

**代码：** `core/portfolio/reader/accounts.py:269–289,859–872,1307–1308`；`core/persistence/postgres/brokerage_views.py:183,204,237`；`core/persistence/postgres/brokerage_ddl.py:100,287–309,383`；`fq/worker/handlers.py:79–91`。

`executions_raw_flex_id` 直接作为对外的 `account_executions_id`，Ledger 按它更新/删除；不是可以随意变动的内部数字。`created_at` 又参与 `new_rows` 计数。已有行被错误重建或更新了这些列，即使业务字段全部相同，当前“逐行一致”定义仍允许通过。写库计划只比较参数元组，也不能替代对 SQL 实际保留字段的检查。

**修正：** 对从 before 载入的已有行，必须断言 PK、created_at 及非更新列保持不变；仅对新增行做明确的代理键映射和时间归一化，同时验证唯一性、引用关系与 new_rows。增加同一报表连续执行两次、重复 exec_id 顺序覆盖、两个唯一键互相冲突、缺 exec_id/trade_id 的案例。比较结果必须保留重复行的数量，不能用集合去重掩盖重复插入。

### A6 · 10 个运行日与“已录到的案例全绿”不能替代 10 个交易日的完整验收

**设计：** §零，DESIGN.md:16；§2.2，DESIGN.md:130；§4.2–4.3，DESIGN.md:242–250；§9，DESIGN.md:325。需求依据：REQUIREMENT.md:8。

**代码：** `bifrost-research/src/bifrost_research/orchestration/schedules.py:108–125`；`fq/scheduler/daily.py:97–103`；`fq/worker/claim.py:77–92`。

设计明确把验收改为周一至周六的“10 个运行日”。cron 包含非交易日，周六是在收周五数据；执行日期与被验证交易日不能混用，节假日空跑更不能新增一天。重放历史案例可以补类型覆盖，不能补足实际并跑时长。

另外，录制失败只 WARNING 是保护生产的正确选择，但影子只盯“新完成的目录”，没有定义一个独立分母。若恰好漏录了失败/崩溃的尝试，或者关开关后没有新案例，现有指标的 mismatch=0 仍可能被当作全绿；“终态”本身也包括 failed。

**修正：** 用交易日历和明确的 report/session date 计算至少 10 个交易日；运行日另计。建立从计划槽、实际 job/attempt 到完整录制、重放 verdict 的对账，必须区分一致、不一致、漏录、不完整、未重放。缺任意必需证据或只有失败而没有有效入库验证的日期不能签收。每日 12:00 只是出报告时点，尚未结束的重试应显示待定。候选 Rust 提交/镜像 digest 也要绑定这段连续证据，不能中途换版后沿用旧成绩。

### A7 · 当前回滚步骤既漏了 args，也不能保证恢复已经被改错的数据

**设计：** §零，DESIGN.md:22；§5，DESIGN.md:258–262；§11.3，DESIGN.md:394。

**代码：** 插件 `k8s/base/deployment-api.yaml:10–17,30–33`、`k8s/base/deployment-worker.yaml:9–27`、`Dockerfile:26–27`；`core/portfolio/reader/accounts.py:859–869,1201–1211`；`fq/worker/claim.py:57–92,95–131`。

切换明确会把 args 改成 Rust 子命令；回滚却只写“换回 Python tag”。如果保留 Rust args，旧镜像根本起不来。API 当前还是 RollingUpdate，并非摘要所述两个 Deployment 都 Recreate；保留现状会出现短暂混合版本，改变它则会重新引入 API 空窗。

更关键的是，“不改表结构，所以回滚不涉及数据”不成立：Rust 若把非空值错误地 upsert，旧值已经被覆盖，恢复旧二进制不会自动复原；删卷后尤其如此。切换前瞬时检查 running=0，也没有阻止 worker 下一次认领或 API 的同步 trigger/upload。

**修正：** 保存并演练完整的上一版 Deployment 模板（image digest、command/args、必要配置），明确 API rollout 策略和混合版本兼容测试。切换/回滚需有可复核的停止领活与排空步骤，覆盖同步手动调用、pending 冷却作业及崩溃的 running 作业。将“进程回退”和“错误写入修复”分开：保存足够的 before 证据，按已批准方案重放/修复受影响行并保护其他写入者的后续更新；明确何时只能停止自动恢复、交 Owner 处理。Python 镜像与修复所需证据的保留期必须匹配。

### A8 · Agent 接入漏了主机 agentd 更新、缓存传递和 Rust 工作目录

**设计：** §3.5，DESIGN.md:223；§7，DESIGN.md:282–289；§9，DESIGN.md:319–320。

**代码：** `bifrost-platform/api/internal/agentrt/store/repos.go:14–25,68–95,203–205,225–227`；`api/internal/agentd/testdb.go:190–204,243–248`；`api/internal/agentd/executors.go:37–58`；`api/internal/agentd/confine.go:143–165,202–207`；`api/internal/agentd/setup.go:165–178`。

仓库的 TestDB 判断由主机上的 agentd 直接读它**编译进去的** `store.Repos`。仅发 platform PROD API、在 06 装 Rust，并不会让旧 agentd 为 Flex 启动临时数据库。缺库后测试若 skip，恰好绕过最重要的写库对照。

现有 allowlist/homePins 也没有 CARGO_HOME/RUSTUP_HOME，Setup 与 executor 的 HOME 分离。所谓“同 GOMODCACHE 做法”需要实际接线，否则依赖装在 Setup 的默认缓存，offline 验证却看另一处。最后，Verify 是从仓库根执行，而 workspace 在 `rust/`；列出的裸 `cargo fetch/clippy/test/fmt` 找不到该 Cargo.toml。

**修正：** 在切片 3 中加入主机 agentd 的对应版本升级和验收；为 Setup、执行者、独立检查设置同一尝试私有的 Cargo 缓存、固定只读工具链及可写 target。所有命令明确 `rust/Cargo.toml` 或固定进入 `rust/`。缺工具链、缺库、零条必需数据库测试均应失败。完整验收必须从全新尝试冷启动，经历有网 Setup 和无网 Verify，而非只在主机登录 shell 下跑成功。

### A9 · 新增 Rust CI 和扫描 .rs，还没有把插件接入推 main 的闸门

**设计：** §6，DESIGN.md:273–276；§9，DESIGN.md:320。

**代码：** `bifrost-trade-infra/scripts/release/push-main.sh:110–117`；`k8s/cicd/tekton/trigger-trade-ci.yaml:221–245`；`agent-config/scripts/code-health/scan.sh:208–218,256–263`。

`push-main.sh` 的 `CI_REPOS` 和 `GATED` 都不包含 Flex 插件。只让扫描器认识 .rs、增加 `bifrost-ci-rust`，仍会让这个仓库走不到 exact-commit CI 和 code-health 分支；没有 CI 或 CI 红的提交仍可能进入 main。“CI 绿之前不建发布单”也不是这个合入闸门。

**修正：** 把插件同时接入分支 webhook/EventListener/TriggerTemplate、CI repo/commit 结果标识，以及 push-main 的 CI_REPOS/GATED；新 Rust CI 要实际运行 code-health。用假 CI 结果验证：同 SHA 成功才通过，无记录、失败、别的 SHA 成功都拒绝；用超出 Rust 基线的变更验证扫描确实被执行。发布构建必须钉住这同一个插件 SHA。

## B：应修正或简化

### B1 · lint、SQL 离线元数据与数据库测试需要证明“真的在检查”

**设计：** §3.2–3.5，DESIGN.md:189,210–225；§6–7，DESIGN.md:269,273,284。

**代码：** 插件 `Makefile:16–24`；`bifrost-platform/api/internal/agentrt/store/repos.go:53–63,87–105`；`api/internal/agentd/testdb.go:243–247`。

现行 `make test` 明确排除 `db`。新 A 层若沿用该标记，文中 `make lint test` 不会执行它；应分别列出必须运行的 Python/Rust 数据库对照目标，并报告执行案例数。`AGENTRT_TEST_PG` 是 libpq key/value 形式，还需显式适配到 Rust 连接选项，不能假设所有驱动都直接接受。

`[workspace.lints]` 还需每个 crate 继承；本稿未说明这一点。应以 lint 阳性用例证明生产 crate 中 unwrap/unsafe/索引确实失败，防止只写配置而未生效。`#[expect]`、测试豁免与棘轮基线需限定作用域并独立复核；“从零骨架起 pub/依赖/clone 数量只减不增”与正常实现增长不相容，应规定首次基线建立及受审扩容方式。

`.sqlx/` 应从版本化的无账户数据 schema 生成，CI 验证它与 SQL/schema 同步；不能只靠 `SQLX_OFFLINE=true`。这样编译通过才具有设计所声称的 SQL 校验意义。本次没有 Rust 工具链，未实跑这些防线，不能把它们标为已验证。

### B2 · 将容易“合理化重写”的字段规则补成逐字段用例

**设计：** §1.2–1.7，DESIGN.md:52–56,61,70,98,104–107；§3.3，DESIGN.md:201–204。

**代码：** `fq/client/flex_client.py:42–73,257–275,343–386,455–495,511–553,584–598,625–694`；`fq/orchestration/transactions.py:47–97`；`core/portfolio/reader/accounts.py:781–790,1215–1297`；`core/persistence/postgres/brokerage_ddl.py:41–100,286–309`；`fq/scheduler/daily.py:97–100`；`fq/scheduler/cronutil.py:82–95`。

建议补齐以下固定案例，而不只依赖随机 XML：

- 数值列在所给 DDL 中是 double precision；不要将金额擅自改成精确 decimal。区分 Python float repr、负零、非有限值、JSON 传递形式与落库形式。`principal_adjust_factor` 本来是文本。
- `order_id/conid/underlying_conid` 先过 `isdigit()`，并非直接按 `int()` 接受集；例如 `+1` 得到 NULL。浮点千分位清洗与 strike 的清洗也不同。
- 币种冲突时现行 parser 实际保留非空 trade currency；54 列执行 INSERT 不含 currency，该字段走 commission。不要根据旁边“佣金币种优先”的注释修正行为。
- 无 Flex 成交时，现金窗口统计会纳入全部已有现金账户；没有 last_dates 才使用 init_days。§1.3 的简述漏了这些分支。
- XML 解析失败返回空列表、首个报表账户被用作全局 fallback、命名空间元素查找的差异、未知属性、NULL/空串/空 JSON、重复行顺序，都应显式覆盖。
- 日期前缀截断、DST 重叠/不存在墙钟的处理、补跑的当地日期与 enqueue 默认 `as_of` 的 UTC 日期、`next_fires` 的边界分钟不能统一成一种“更规范”的解释。API 时间格式有 `isoformat()` 与强制 Z/秒精度两类；只对真正时间字段按瞬时比较，不能误归一化日期字符串。

这些大多能放进切片 1，成本低于切换后排查一行差异。

### B3 · 影子隔离的方向正确，但文件/网络契约还有三处矛盾

**设计：** §4.1–4.2，DESIGN.md:236,242–244；§6，DESIGN.md:275；§10.2，DESIGN.md:352,356。

**代码：** 插件 `k8s/base/network-policy.yaml:11–30`、`k8s/base/deployment-worker.yaml:28–64,68–99`、`Dockerfile:18–24`；`fq/config.py:74–112`；`fq/orchestration/notify.py:87–103`；infra `k8s/cicd/tekton/apply-manifest/actuation-policy.yaml:48–78`。

首先，卷只读挂载却要求把 verdict 写回同一录制卷；应保留语料只读，给结果独立可写位置。其次，不给 GS 凭据且拒绝出站的影子不能“每天比一次 GS 目录”；由录制侧输出 schema 指纹，再由影子离线检查，不能为此打开生产连接。最后，B 层 Python Job 与切换后的反向 Python 影子也要使用同一隔离模板，不能复用生产 Deployment 的 envFrom、数据库配置或 Redis 目的地。

不同 part-of 标签确实避开了当前放行 data/443 的策略选择器；应以最终渲染清单校验这一点，并禁用不需要的 ServiceAccount token。Postgres 只向本 Pod/Unix socket 暴露，Prometheus 的放行是入站且只到 metrics 端口。取数/通知必须注入录制 transport/内存 sink，缺录制事件就失败，不回落到真实 IB 或 Redis。

现有 actuation allowlist 已包含 PVC、Job、NetworkPolicy，§10.2 这部分可从“待查”移为“仓库配置支持，在线权限未验证”。仍需确定共享卷访问模式/调度约束、容量、原子完成标记、清理与读者并发，以及磁盘满或 PVC 阻塞时录制不会无限拖住生产；“异常只 WARNING”不能处理阻塞 I/O。

### B4 · 固定 Python 基准血缘，提前最小 CI，减少可后置工程

**设计：** §2.3–2.5，DESIGN.md:142,162–165；§6，DESIGN.md:272–273；§7，DESIGN.md:283；§9，DESIGN.md:317–327；§11.1，DESIGN.md:373。

**代码：** 插件 `k8s/cicd/pipeline-build.yaml:37–66`、`k8s/cicd/Dockerfile:10–13`、`Makefile:38–53`；platform `api/internal/agentd/setup.go:49–73`；infra `scripts/release/push-main.sh:14–23`。

同一 `revision` 同时用于插件和 core，插件专属 SHA 无法用于 core；core sibling 又跟 main，版本下限测试不能证明写库逻辑未漂移。应在切片 1–2 就固定 Python 插件 SHA、core SHA、镜像 digest、语料/比较器版本，Python 构建分开接收两个 revision。测试时只消费已签定 golden，不自动重新生成期望；候选更新基准需独立复核。版本下限只能证明兼容要求，不能代替这一血缘。

保持“Python 的 A/B 层先通过，再写 Rust”的顺序。最小 Python 分支 CI 应提前到录制器部署前；Agent repo 的 Setup/Verify 则要分阶段启用，不能在 Cargo.toml 还不存在的切片 3 就无条件跑 Cargo。

第一块可先保留域逻辑与 I/O 的模块边界，不必同时完成五个独立 crate、cargo-chef 缓存优化、通用框架推广和所有随机模糊组合；在固定对照案例、硬 lint、数据库验证、隐私隔离、回滚演练齐备后按冷构建数据决定这些投入。旧 core 写分支清理、OpenAPI 文档界面的取舍以及下一块推广可继续后置；不得后置前述正确性与验收问题。

## 已核对且成立的部分

1. **现有入口清单基本准确。** 静态数到 17 条显式 API 路由；worker 有三个 health 路径。Console 的队列、配置、freshness、手动触发、upload 和 run-now 调用都可在 `bifrost-platform/console/src/api/flexQueryPlugin.ts:288–397` 对上；平台读取 worker 健康及 freshness 的路径见 `api/internal/flexquery/service.go:218–253`。API 的 `/health` 与 worker health 不是同一形状，设计保留两种进程是必要的。
2. **Dagster 无需改调度的判断成立。** `plugin_batch_assets.py:75–108,331–351` 对应 enqueue/config-summary/freshness 门控；`flex_husbandry.py:42–74` 使用 last_ok 和 last_success_at。因此失败不得前移成功时间，不能只保留 HTTP 200 和端点名字。
3. **IB 就绪与重试优先级描述正确。** `fq/client/flex_client.py:167–228` 区分 Warn/Fail 与合法空报表；`fq/worker/retry.py:28–73,114–138` 的优先级为 throttled → config → not_ready → transient → unknown，config/耗尽次数终止，未耗尽的 1018 延迟整条 pending 队列。合成组合错误探针通过。
4. **核心正常写入路径已找到。** Flex 成交 54 列按行 upsert、佣金随成交同事务；现金两种 conflict target 与 COALESCE 规则准确。部分账户写入可以已经 commit，随后 job 仍失败并重试，不能把“作业失败”重写成“全局回滚”。证据为 `accounts.py:859–968,1201–1302` 与 `fq/worker/handlers.py:21–39`。
5. **私有 B 层才满足真实输入/真实入库结果的要求。** A 层便于 Agent 离线开发，不能替代 B 层。设计把 Python B 层 100% 自复现放在 Rust 之前是正确的硬门槛；需要按 A3–A6 补全后才能成立。
6. **不额外请求 IB 的影子方案合理。** 独立临时 PostgreSQL、不发生产凭据、不消费生产队列，可避免重复请求造成限流；无需为 shadow 引入生产 schema。上述是设计方向的判断，不是已验证的集群隔离结论。
7. **保持流水线名可复用发布窗口。** platform `api/internal/delivery/release_window.go:21–27` 与 infra `k8s/cicd/tekton/task-release-window.yaml:39–44` 已映射 `bifrost-build-flex-query`；插件流水线在 clone 前执行 freeze-check/release-window（`k8s/cicd/pipeline-build.yaml:27–38`）。
8. **复盘指标与范围控制基本齐全。** Agent 尝试/退回、复核发现、上线问题、代码量和资源均有登记位置；同仓库分阶段替换、延后 core 公开接口清理，符合按服务替换和不扩展交易能力的范围。

## 本次检查与未检查事项

已完成固定提交的静态交叉核对：解析、窗口、配置、upsert/其他写入者、队列/重试/补跑、freshness、health/metrics、Console/Dagster 消费者、Deployment/NetworkPolicy、构建/发布窗口/CI、Agent repo/TestDB/环境传递。另以 Python 标准库执行源函数的合成探针，验证鉴权例外、现金回退次数、Python strike repr、整数字段过滤、币种优先级、现金 UTC 日期及重试分类；全部通过。没有连接 HTTP 或数据库。

按 BRIEF 限制，**未做**：真实报表/账户行读取；A/B 层真实业务测试；数据库事务、并发、DDL 和权限实测；任何网络、MCP、SSH、集群操作；线上镜像/core 版本、GS 时区/索引、StorageClass、PVC、NetworkPolicy 实效、registry 保留策略、运行资源基线、10 个交易日并跑和回滚演练。未运行 Cargo/clippy/镜像构建/CI；本机 PATH 未发现 cargo/rustc，且当前交付物只是设计。所给 DDL 源文件中未找到现金 transaction-id 部分唯一索引的创建语句，不据此断言线上缺索引，实施前仍须由授权环境确认并固化无数据 schema。

未修改任何被审仓库、未提交、未读取 Secrets 或 .env；报告中没有真实账户内容。上述未做事项不被计作通过。

先修：A1 配置鉴权、A2 现金回退、A3 私有错误与日志泄露、A4 录制事务边界、A5 行比较豁免、A6 交易日与完整性验收、A7 回滚、A8 Agent 接线、A9 CI 合入闸门。
END OF REPORT
