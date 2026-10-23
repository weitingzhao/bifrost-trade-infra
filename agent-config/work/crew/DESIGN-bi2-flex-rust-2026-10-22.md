# BI-2：Flex 插件换成 Rust（第一块）—— 设计

> **状态：设计（大级），统筹线程已审读，交 Codex 独立复核 517 号（gpt-6-astra）**。级别按 `DESIGN-crew-intake-2026-10-22.md` §7.2 算**大级**（新外部依赖、可能的新表、公开仓库的隐私边界）。
> 需求说明以 Owner 2026-10-22 23:15 CDT 确认的为准，本稿不改它。
> 引用缩写：`fq/` = `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/`（HEAD `bf6c61c`，0.13.2）；
> `core/` = `bifrost-trade-core` **origin/main `a87e39f`（0.61.0）** 的 `src/bifrost_core/`（本机 core 检出停在 0.36.2，是旧的，见 §10.2）。
> 所有数字只写计数，不写金额、不写持仓。

---

## 零、一页看完

- **换什么**：一个服务整体换。Python 的 `flex-query-api`（:8791，17 条路由）和 `flex-query-worker`（队列、重试、补跑、心跳 :8080），
  连同它借用的 core 写库路径（Flex 成交、佣金、现金流水三张表），换成一个 Rust 程序。Deployment 名、Service、端口、表、指标名、JSON 形状都不变。
- **为什么不是为了省资源**：现在 7 天峰值 API 约 73 MiB、worker 约 42 MiB，CPU 几毫核；作业 p50 约 1 秒（§8 基线）。收益在类型和债，不在机器。
- **怎么证明一样**：先录**业务级对照测试**，让现行 Python 先过；Rust 再过同一套；然后并跑 ≥10 个运行日。
  - 真报表和真行只在集群里：Python worker 加一个**录制器**，每次尝试把 IB 原始回包、写库计划、写前写后的相关行存进插件命名空间的私有卷（PVC），永不进 git。
  - 仓库里只放**按结构合成的假报表**：从真报表抽「形状」（字段、格式、边角情况），不抽值，再生成明显是假的数据；预期结果由 Python 版算出来。
- **并跑时 Rust 写哪**：**写进影子 Pod 自带的临时 Postgres**（sidecar，emptyDir）。影子 Pod 不拿 Golden Source 的账号、不拿 IB token、不连 Redis，
  只读录制卷，按录到的「写前状态」重放，和录到的「写后状态」逐行比。生产表在结构上碰不到；**不需要任何 PROD DDL**。
- **不加 IB 请求**：影子只重放，不调 IB（1018 限流按 token 算，多打一倍请求会伤到生产作业）。
- **切换**：同一个 Deployment 换镜像（Recreate），回滚就是换回上一个 Python tag。Dagster、Console、Trade 都不用改。
- **Rust 的防线第一天就开**：`unwrap/expect/panic/索引/字符串切片/as 转换` 全部 deny，`#[allow]` 必须写理由，`.clone()` 计数只减不增。
- **要 Owner 定的 9 件**（§10）：最关键的三件是 Rust 工具链（架构级）、录制卷放哪、并跑写哪。推荐都在文中。
- **Owner 要动手的**：批准几次 `plugin-flex-query` 命名空间的 apply（C 级），在 agent-06 上跑一次装 Rust 的主机脚本，批准平台加一个任务仓库。没有 PROD DDL。
- **留给下一块的样板**：录制器 → 私有语料、形状合成夹具、先跑旧版的对照框架、Rust 工作区模板（lint/棘轮/镜像/CI）、按重放并跑、同 Deployment 换镜像切换、数字台账。

---

## 一、Python 版今天做什么（行为契约）

对照测试要钉住的就是这一节。凡是「怪」的地方先照搬（§1.7），切换后再按正常改动修。

### 1.1 进程、入口、谁在调

| 项 | 现状 | 依据 |
|---|---|---|
| API | uvicorn :8791，FastAPI，17 条路由 | `fq/api/app.py:21-35`，`scripts/run_api.py` |
| worker | 单进程轮询 5 秒；健康 :8080 `/health` `/healthz` `/ready` | `fq/worker/loop.py:100-220`，`fq/worker/health.py:11-46` |
| 触发 | Dagster `research_flex_morning_schedule`，`30 6 * * 1-6` America/New_York，`POST /flex/ingest/enqueue {"slot":…}`，头 `X-Flex-Query-Write-Token` | `bifrost-research/src/bifrost_research/orchestration/schedules.py:117-127`，`plugin_batch_assets.py:75-108` |
| 闸门 | Dagster `flex_gate` 读 `/flex/config/summary` 和 `/flex/dashboard/freshness-kpis` | `plugin_batch_assets.py:331-345`，`orchestration/flex_husbandry.py:24,102` |
| Console | 平台代理 `/api/v1/plugins/flex-query/api/*` → :8791；状态页读两个 Deployment 名、`flex-query-health:8080/health`、`/flex/coverage/freshness` | `bifrost-platform/api/internal/flexquery/config.go:9-15`，`service.go:236-245`，`console/src/api/flexQueryPlugin.ts:288-397` |
| Trade UI | 经 Trade 网关 `/api/plugin/flex-query/*`：summary、trigger、upload-xml、config/write、coverage/freshness | `bifrost-trade-frontend/src/api/flexQueryPlugin.ts:40-104` |
| 读这些表的 | Trade 经 core 读 `brokerage.*` FDW 视图（`core/portfolio/reader/executions.py` 等）；Research 读 `raw_broker.executions_final` 等（`engines/journal_distill.py`、`repositories/journal_memory.py`、`engines/option_pinned/entry.py`） | grep |
| 告警 | `BifrostFlexIngest{Failed,MissedPlan,Stale,ScrapeDown}`、`BifrostFlexWorker{Down,Silent}`、`BifrostFlexToken{Missing,Expiring}`、`BifrostFlexCashCoverageGap` | `bifrost-trade-infra/k8s/monitoring/bifrost-alerting-rules.yaml` |

### 1.2 向 IB 取数、解析

- 两步：`SendRequest`（`t`、`q`、`v=3`，可选 `fd/td` 或 `p`）→ `ReferenceCode`；`GetStatement` 最多轮询 24 次、间隔 5 秒，超时 60/90 秒，UA 固定 `Python/3.10`。`fq/client/flex_client.py:75-80,110-160,197-228`
- **报表就绪**只认含 `<FlexStatement>` 的 `<FlexQueryResponse>`；`<FlexStatementResponse>`（Warn 或 Fail，1019 是 Warn）、非 XML 都继续轮询，耗尽后抛出带 `[NNNN]` 的错误文本。`flex_client.py:167-194`
- 日期范围 >366 天在客户端就拒；只给一边日期也拒。`flex_client.py:125-141`
- **成交**（`parse_trades_xml`，`:439-704`）：遍历所有 `<Trade>`，属性去空白；`dateTime` 按 `FLEX_LOCAL_TZ`（默认纽约）墙钟解释，只有日期取当地零点（`:47-73,488-495`）；
  `contract_key = symbol|sec_type|expiry|str(float(strike))|right`，**用的是 Python 的浮点 repr**（`150.0`）（`:520-539`）；未知属性进 `raw_extra`（`:631-687`）；
  一条都没解析出而正文含 `CashTransaction` 时报错「用错 Query」（`:697-703`）。
- **现金流水**（`parse_cash_transactions_xml`，`:242-436`）：元素优先、属性兜底；账户缺省取报表级；`ts` **故意只取日期、按 UTC**（它是唯一键的一部分，`:349-378`）；
  无日期的行跳过并计数；`raw_extra` 是**全部属性**（不是只放未知的，`:382-386`）；类型归一 `deposit/withdrawal/transfer/dividend/other`（`:92-107`）。

### 1.3 窗口、分段、回退

- **trades**：无显式日期时 `to=昨天`（`date.today()`，容器本地时区）；库里没有 Flex 成交 → `init`，回看 `init_days`；否则 `incremental`，回看「距最新 trade_date 的天数 + default_days」。`fq/orchestration/trades.py:157-184`
- **transactions**：`from = min(各「有 Flex 成交的账户」最后一笔现金日, 昨天 - default_days)`，按 ≤364 天分段，显式日期也分段。`fq/orchestration/transactions.py:47-110,177-188`
- 天数来自 `ops_jobs.flex_settings`（无行时 30/360），读失败就让作业失败（TD-116）。`fq/orchestration/config_rw.py:153-170`
- 回退链（query 默认期 → `period=5`）只在 `fallback` 为真时走；排队作业 `fallback=false`，手动触发默认也是 false。`trades.py:38-110`，`transactions.py:267-297`，`fq/scheduler/daily.py:103`，`fq/api/manual_ops.py:81`
- 查询行按 `sort_order, id`，每行先 host 后 secondary token，query id 逗号拆分；**写库顺序就是这个顺序**（同一 exec_id 出现两次，后写的赢）。`config_rw.py:98-149`

### 1.4 写库（三张 raw_broker 表 + ops_jobs）

| 表 | 冲突键 | 写法 | 依据 |
|---|---|---|---|
| `raw_broker.executions_raw_flex` | `(exec_id)`，部分索引 `exec_id<>''`；另有唯一 `(account_id, trade_id)` | 54 列 `ON CONFLICT DO UPDATE` **全列覆盖**；无 exec_id 时合成 `flex_<acct>_<trade_id>`；一次作业一个事务 | `core/portfolio/reader/accounts.py:726-735,849-872`，`core/persistence/postgres/brokerage_ddl.py:382-406` |
| `raw_broker.commissions` | `(exec_id)` | 有「有意义」字段才写；0 当「没说」；`COALESCE(新, 旧)`；Flex 保留 IB 符号；**TWS/网关也写这张表** | `accounts.py:943-966`，`core/persistence/postgres/commissions.py:43-116` |
| `raw_broker.transactions` | 有 `flex_transaction_id`：`(account_id, flex_transaction_id)` 部分唯一索引；没有：`(account_id, ts, amount, type, report_date)` | 前者覆盖 ts/amount/type/report_date、其余 COALESCE；后者只 COALESCE；缺账户/ts/report_date 的行跳过；写入 0 行算失败 | `accounts.py:1140-1304`，`transactions.py:221-237` |
| `ops_jobs.job_flex_ingest` / `flex_ingest_freshness` / `flex_worker_heartbeat` / `flex_settings` | 见右 | 进程启动时跑幂等 DDL 和 `ADD COLUMN IF NOT EXISTS`；全部时间用 `clock_timestamp()` | `fq/schema/ddl.py:39-170,197-298` |
| `raw_broker.settings_flex` | — | `POST /flex/config/write` 整表替换，与 `flex_settings` 同一事务 | `config_rw.py:225-320` |

- 只连 Golden Source，登录 `flex_writer`（`ops_jobs` 可 CREATE，`raw_broker` 只 DML）。`bifrost-trade-infra/k8s/data/role-matrix/expected.yaml:224-234`
- 副作用：成交作业结束发一条 Trade 消息中心事件（Redis stream，话题 `portfolio.flex_executions`，`redis-live-prod`），失败只记 WARNING。`fq/orchestration/notify.py:14,73-115`
- `new_rows` = 作业开始后 `created_at >= since` 的行数。`fq/worker/handlers.py:79-98`

### 1.5 队列、重试、补跑、心跳

- **入队去重**：`payload_hash = sha256(json.dumps(sort_keys, (",",":"), default=str))[:16]`，`fallback`、`catchup` 不算身份；`(kind, hash)` 在 pending/running 时唯一。`fq/scheduler/enqueue.py:18-67`，`daily.py:36,81-120`
- **认领**：`FOR UPDATE SKIP LOCKED`，`not_before` 到期才可领，按 `priority DESC, created_at, id`。`fq/worker/claim.py:57-92`
- **分类**（`fq/worker/retry.py:28-73`）：错误文本里任何 `[1018]` → throttled；1010–1017、1020 或配置类关键词 → config；1003–1009、1019、1021 → not_ready；网络/库关键词 → transient；其余 unknown。
- **计划**（`retry.py:114-138`）：config 直接失败；用满次数失败；not_ready/throttled 延后 1800 秒，throttled 还把**所有 pending** 一起推后；transient 120、unknown 300；配置最小 30 秒（`:94`）。
- 部分账户失败 = 作业没完成（抛错重试）。`handlers.py:21-31`
- 卡住的 running 超过 7200 秒退回 pending（延后 600 秒）或失败。`claim.py:17-20,95-135`
- 补跑：空闲时每 12 轮检查一次，计划时刻过了 45 分钟（`catchup_grace_sec`）、一天内没有该类作业，就自己入队（按当地日期去重）。`fq/worker/catchup.py:21-95`，`loop.py:110,161-167`
- 计划/偏差：`schedule.yaml` 的 cron 只解析分、时、星期（日、月被忽略），按时区逐分钟匹配。`fq/scheduler/cronutil.py:37-79`；偏差 = 计划后 2 小时窗口。`fq/api/ingest_dashboard.py:55-64`
- 库断线：0/5/10/20/40/60 秒重连，用尽进程退出。`loop.py:33-83`

### 1.6 HTTP 契约（谁在读）

- 写接口：`enqueue`、`jobs/{id}/run-now`（throttled 冷却中 409，`force` 放行）、`trigger`、`upload-xml`（同步执行，也落一行 job）、`config/write`（带 token 字段一律 409）。`fq/api/ingest.py:31-148`，`manual_ops.py:65-118`，`config_summary.py:134-174`
- 读接口：`/health`、`/metrics`、`/flex/ops/check`、`/flex/dashboard/freshness-kpis`、`/flex/ingest/{kinds,jobs,queue-summary,queue-dashboard}`、`/flex/config/summary`、`/flex/coverage/{db-summary,freshness,raw-peek}`。
- 鉴权：没配写令牌时写接口**全开**；带 `X-Bifrost-Trade-Gateway: 1` 也放行。`fq/api/deps.py:28-57`
- `/metrics`：手写文本，告警读其中 6 个名字（§1.1）；另有 `http_requests_total`、`http_request_duration_*`。`fq/api/metrics.py:53-137`，`http_metrics.py:44-53`
- JSON 里时间是 Python `isoformat()`（微秒为 0 时省略），偏移随库会话时区。

### 1.7 怪癖清单（先照搬，各有一条测试钉住）

| # | 怪癖 | 依据 | 处理 |
|---|---|---|---|
| Q1 | contract_key 用 Python 浮点 repr | `flex_client.py:536` | Rust 实现 Python 的 repr 规则 |
| Q2 | 数字用 Python `float()`/`int()` 的接受集（空白、`+`、下划线、`inf`） | `:344,512,526` | 照搬；形状抽取会告诉我们真数据里有没有 |
| Q3 | 现金 `raw_extra` 是全部属性，成交是未知属性 | `:382,683` | 照搬 |
| Q4 | 现金属性值不去空白（除 transactionID） | `:300-341` | 照搬 |
| Q5 | trades 不分段，窗口 >366 天直接失败（README 写的是两类都分段） | `trades.py:186-222` 对 `README.md`「Fetch windows」 | 照搬并记 TD |
| Q6 | worker 读镜像里烤进去的 `schedule.yaml`，API 读 ConfigMap | Dockerfile、`deployment-worker.yaml`（无 schedule 卷） | Rust 镜像同样烤一份；切换后两边都挂 ConfigMap（单独改） |
| Q7 | 写令牌为空时写接口全开；网关头可被集群内任何调用方伪造 | `deps.py:34-41` | 照搬，另记 TD |
| Q8 | 死代码：`trim_old_jobs`、`summarize_categories`、`update_freshness`、`next_catchup_window`、`flex-query-schedule` CLI | 无调用方 | **不移植**（行为不变） |
| Q9 | 传输层错误的文本来自 urllib/psycopg2，分类靠子串 | `retry.py:40-53` | 分类一致是硬要求；文本见 D-R7 |
| Q10 | FastAPI 自带 `/docs`、`/openapi.json` | — | 无调用方（未核实），不移植 |

---

## 二、业务级对照测试

### 2.1 两层语料

| 层 | 内容 | 放哪 | 谁能跑 |
|---|---|---|---|
| **A：合成** | 按真报表「形状」生成的假报表 + Python 版算出的预期（行、写库计划、作业行、API 答复） | 仓库 `tests/characterization/`（公开） | 所有人；agent-06 沙箱（无网）、Tekton CI |
| **B：真实** | 录制器录下的真回包 + 写前/写后真行 | 集群私有卷，永不出集群 | 只有集群里的 Job 和影子 Pod；输出只有计数和哈希 |

为什么两层：B 才是需求里说的「真报表、真行」；但 agent 在 06 上碰不到它（06 只出公网 443 和 Gitea，`bifrost-trade-infra/scripts/agent-host/agent-egress.nft`），A 才能进它们的检查。

### 2.2 录制器（Python 版加的唯一一段，Python 0.14.0）

- 开关 `FLEX_CAPTURE_DIR`；关着就和现在一模一样。录制失败只记 WARNING，绝不让作业失败。
- 每次尝试一个目录，写：请求参数（不含 token）、每个原始回包（含 Fail/Warn 体）、解析出的行（写库计划，按写入顺序）、
  写前状态（窗口统计、settings 行、按 `exec_id`、`(account_id, trade_id)`、两种现金键选出的现有行、相关 commissions 行）、提交后同一批键的写后状态、
  作业行前后、freshness 行、错误文本与分类、时钟（`now`、`today`）。
- 只录 worker 的作业；手动 trigger/upload 由 A 层覆盖（够用；要录再开）。
- 保留 60 天，按天清理。容量很小：近 30 天两类共约 64 个作业，p50 约 1 秒（§8）。

### 2.3 合成夹具（A 层）怎么来

1. 集群里跑**形状抽取**：读 B 层，只输出结构——出现过哪些元素/属性、每个属性的值格式（如 `\d{8};\d{6}`、几位小数、带千分位、空串）、元素式还是属性式、命名空间、未知属性名、各类行的计数区间、描述的模板（值换成占位符）。不输出任何值。
2. 输出由统筹线程人工看一遍再入库（它决定夹具覆盖什么）。
3. 生成器按形状造假数据：账户 `U000000x`、代码 `ZZA..ZZZ`、整数价格、2001 年的日期等一眼假的值，并刻意造边角：0 行报表、1019 Warn、1018、日期缺失、同 exec_id 重复、host/secondary 重叠、跨月、跨 DST。
4. 预期由**现行 Python 版**跑出来（golden 文件）。
5. 防线：夹具守卫测试——夹具里的账户、代码、日期都必须落在假词表里；提交前对 diff 跑金额/账户 grep（`test_fixtures_copied_from_dev.md` 的教训）。

### 2.4 比什么、怎样算一样

| 对象 | 怎样算一样 |
|---|---|
| 写库计划 | 每张表的参数元组序列逐个相等：浮点按位相等，时间到微秒，字符串逐字节，`NULL` 和 `''` 区分，jsonb 按语义 |
| 落库行 | 从写前状态重放后，三张表逐行相等；不比代理键（`executions_raw_flex_id`、`account_transactions_id`）和 `created_at` |
| 作业生命周期 | status、attempts、error_category、`not_before - now`、result（jsonb 语义）、freshness 行、心跳计数 |
| 重试分类 | 历史错误文本全集 + 构造的组合文本 → 类别和计划一致（`ops_jobs.job_flex_ingest.result->>'error'` 的历史集合在集群里抽，入库前去掉 query id） |
| 窗口 | （统计、settings、today）→（from、to、mode、days、分段） |
| API | 固定库状态、固定时钟下每条路由的状态码和 JSON；时间按瞬时比较；`/metrics` 按样本（名、标签、值）比 |
| 副作用 | 消息中心事件的话题、字段（时间、随机 id 除外） |
| 纯函数 | Python 与 Rust 差分模糊测试：随机 XML、随机 cron/时刻（跨 DST）、随机 payload 的哈希 |

「一样」之外只允许 Owner 批过、单独列名的**有意差异**（初始为空；见 D-R7）。

### 2.5 先让 Python 过

- A 层：`make test` 里新加 `tests/characterization`，夹具由 Python 自己生成，所以首次必然通过；意义在于之后每次改动都被钉住。
- B 层：集群里起一个 Job（Python 镜像 + Postgres 17 sidecar，emptyDir），逐个案例「载入写前状态 → 喂录到的回包 → 跑 → 比写后状态」。
  Python 自己必须 100% 复现自己的写后状态；复现不了的案例说明框架或录制有洞，先修框架，不进 Rust。
- 框架作者与 Rust 作者**不是同一家**（同一家写测试和实现，盲点相同）。

---

## 三、Rust 版

### 3.1 布局（同仓库新目录 `rust/`，Cargo workspace，Python 退役时删 `src/`）

| crate | 内容 | I/O |
|---|---|---|
| `flex-domain` | 类型（`AccountId`、`ExecId`、`TradeDate`、`QueryRole`、`Kind`、`ErrorCategory`…）、XML 解析、日期规则、类型归一、Python 浮点 repr、窗口与分段、分类与重试计划、cron、payload 哈希 | 无 |
| `flex-ib` | IB 两步协议、就绪判断、错误文本；`trait FlexTransport`，测试注入内存实现（沙箱连回环都没有） | HTTPS |
| `flex-store` | 队列、freshness、心跳、settings、三张表写入、统计/覆盖读取；幂等 DDL 与 Python 逐句相同 | Postgres |
| `flex-notify` | 消息中心 XADD，尽力而为 | Redis |
| `flex-query`（bin） | 子命令 `api` / `worker` / `shadow` / `replay`；同一个镜像，Deployment 用 args 选 | — |

### 3.2 主要库（架构级：新外部依赖，见 D-R6）

| 用途 | 推荐 | 备选 / 说明 |
|---|---|---|
| 异步 | tokio | — |
| HTTP 服务 | axum + tower-http | — |
| HTTP 客户端 | reqwest（rustls，webpki 根证书） | ureq（同步） |
| XML | roxmltree（DOM，和 ElementTree 的 `iter()` 一一对应） | quick-xml（流式，报表小，不需要） |
| Postgres | sqlx（离线模式，`.sqlx/` 入库，SQL 编译期校验） | tokio-postgres（运行期校验，少一个宏层） |
| 时间 | chrono + chrono-tz | time |
| 序列化 | serde、serde_json；YAML 选仍在维护的 serde_yaml 分支（未核实哪个） | — |
| 日志 | tracing（JSON） | — |
| 错误 | thiserror；main 里才允许 anyhow | — |
| cron | **自己移植**（30 行，语义与 Python 相同） | `cron` crate 的星期编号和字段数不同，不用 |

不用 `sqlx migrate`：它会在 Golden Source 建 `_sqlx_migrations` 表，那是新表。

### 3.3 怎样保持同一契约

- 路由、方法、状态码、`detail` 文本、JSON 键名逐条照搬；路由清单由一条测试对着 Python 的 OpenAPI 生成的清单比（不含 `/docs`）。
- 时间输出：统一按 UTC、照 Python `isoformat()` 的规则写（有无微秒），客户端都是按瞬时解析（TS `Date`、Go `time.Parse`）。
- 错误文本：IB 来的错误（`[NNNN] message`）、模板文本（`Flex query 1/2 (host …): …`、`flex-trades partial: …`）逐字照搬；分类函数与 Python 同表。
- payload 哈希：实现 Python `json.dumps(sort_keys, separators, ensure_ascii, default=str)` 的规范形，用 Python 生成的向量钉住——切换那一刻 Python 留下的 pending 作业要能和 Rust 的入队去重。
- 写库：同 SQL、同顺序、同事务边界（成交整批一个事务，现金整批一个事务，佣金跟着成交行）。
- UA、轮询次数、超时、延迟默认值、补跑宽限、卡住阈值全部同值。
- 时钟、IB、库都经 trait 注入，测试能固定 `now/today`。

### 3.4 第一天起的 lint 与棘轮

`rust/Cargo.toml` 的 `[workspace.lints]`：

- `rust`：`unsafe_code = forbid`，`unused_must_use = deny`。
- `clippy` deny：`unwrap_used`、`expect_used`、`panic`、`todo`、`unimplemented`、`indexing_slicing`、`string_slice`（Python 的 `s[:n]` 在 Rust 里是会 panic 的字节切片）、
  `as_conversions`、`float_cmp`、`dbg_macro`、`print_stdout`、`print_stderr`、`allow_attributes`（只许 `#[expect(…, reason = "…")]`）、`allow_attributes_without_reason`、`clone_on_ref_ptr`、`implicit_clone`；
  `pedantic` 整组 warn，CI 里 `-D warnings` 让它等于 deny。测试代码经 `clippy.toml` 放行 unwrap/expect。
- 棘轮脚本 `rust/ratchets.sh`（基线文件入库，只减不增）：`#[expect]` 个数、`.clone()` 个数、`pub` 项个数、单文件行数上限、依赖数（`cargo tree --depth 1`）。
- `cargo fmt --check`；`cargo deny`（许可证、通告、重复依赖；要联网，只在 CI 跑）；`rust-toolchain.toml` 钉确切版本；`Cargo.lock` 入库，全部命令 `--locked`。
- infra 的 code-health 扫描现在不看 `.rs`（`agent-config/scripts/code-health/scan.sh:213,260`），加上（§6）。

### 3.5 测试

- 单元：`flex-domain` 全部是纯函数，按 §1.7 每条怪癖一条测试。
- A 层对照：`cargo test` 读 `tests/characterization` 同一批夹具和 golden；库测试用 agentd 给的临时库（`AGENTRT_TEST_PG`，unix socket，`bifrost-platform/api/internal/agentd/testdb.go:241-249`），CI 用 sidecar。
- HTTP 级测试（真的起 axum、真的 reqwest 打假 IB）只在 CI 跑（沙箱无回环）。
- 差分模糊：CI 里同一个 Pod 有 Python 和 Rust，跑 §2.4 最后一行。
- B 层：`flex-query replay` 子命令，同 §2.5 的 Job。

---

## 四、并跑

### 4.1 Rust 写哪（D-R2）

| 选项 | 做法 | 要什么 | 评价 |
|---|---|---|---|
| **A（推荐）** | 影子 Pod = `flex-query shadow` + Postgres 17 sidecar（emptyDir）。按录制目录逐个案例：sidecar 里载入写前状态 → Rust 用录到的回包跑完整流程 → 和录到的写后状态、Python 的写库计划比 | 一个只读挂载录制卷的 Deployment、一条 deny-all 出站策略；**不给 GS 账号、IB token、Redis** | 生产表结构上碰不到；零 DDL；输入完全相同所以结果可比 |
| B | GS 里建 `raw_broker_shadow` 三张表，Rust 从某天快照起每天真写，SQL `EXCEPT` 对比 | PROD DDL、授权、role-matrix 改动、结束后删表 | 持久可查；但佣金表有 TWS/网关在写，比对噪声大；账户数据多一份 |
| C | 另建库 `bifrost_flex_shadow` | 集群级 DDL、新角色、跨库比对 | 隔离最好，搭建最重 |

### 4.2 谁触发、什么时候比

- Dagster 只触发 Python，不变。影子不领队列、不入队，只盯录制目录里新完成的尝试（成功和失败都比：失败要比分类和计划）。
- 每个尝试结束后几分钟内出结果；每天 12:00 ET（8 次重试的窗口已过）出日报：当天每个作业 `一致 / 不一致（表、列、键哈希、计数）`。
- 输出只有计数、列名、键的哈希，写在录制卷的 `verdicts/` 和影子的 `/metrics`（`bifrost_flex_shadow_cases_total{result}`、`bifrost_flex_shadow_mismatch_rows{table}`）。Agent 只看这些。

### 4.3 多久、什么时候停

- **通过**：连续 10 个运行日（周一到周六，两类作业都到终态）全部一致，且期间至少见过：一次 not_ready 重试、一次 cash 有行、一次含期权成交、一次跨月（覆盖统计）。没见过的类型用 B 层历史案例补，并在报告里写明。
- **计数**：Rust 的错 → 修完从 0 重数（D-R8）；框架或录制的错 → 修框架、重放当天、不清零。
- **停**：录制让 Python 作业变慢或失败（看作业时长和失败数）→ 关开关；卷满；同一类不一致三次修不好 → 回到设计；Owner 的业务插队 → 暂停（并跑只花墙钟，不花额度）。
- **不调 IB**：并跑期间 Rust 一次都不打 IB（D-R5）。IB 客户端靠录到的协议回包和 HTTP 级测试证明；首个真实调用就是切换后的第一个 06:30。

---

## 五、切换、回滚、退役

1. **前提**：A、B 两层全绿；并跑通过；Owner 批切换单。
2. **时机**：周六作业成功后（周日没有作业），留一整天观察；第一次 Rust 实跑是周一 06:30 ET。切换前确认没有 running 作业。
3. **开关**：`k8s/base` 里两个 Deployment 换镜像和 args（`flex-query api` / `flex-query worker`）。名字、Service、端口、Secret、ConfigMap、网络策略不变。worker 是 Recreate，不会两个 worker 同时领活（领活本身也是 `SKIP LOCKED`）。经 `apply_manifest`（`plugin-flex-query` 是 C 级，`bifrost-trade-infra/k8s/cicd/tekton/apply-manifest/actuation-policy.yaml:41`）。
4. **观察 5 个运行日**：每天看 freshness、行数、告警。Rust 版带同格式的录制（同一开关，切换前就做进去），影子反过来用 Python 镜像重放 Rust 的作业，继续逐行比；退役时两边的录制一起删。
5. **回滚**：换回上一个 Python tag 再 apply。前提：Python 镜像 tag 在 registry 里保留到退役后 30 天（保留策略未核实）；Rust 不改表结构，所以回滚不涉及数据。
6. **退役**（观察期过后）：删 `src/`、`pyproject.toml`、Python Dockerfile、录制器、影子 Deployment、录制卷；README/CLAUDE.md 改写；台账记数字。
   core 里只给 Flex 用的写库分支（`upsert_account_transactions` 只有本插件在调；`write_account_executions_to_db` 的 flex 分支）留给 core 自己的改动（改公开接口，另批）。

---

## 六、构建、CI、部署

- **镜像**：多阶段 `rust/Dockerfile`：builder `rust:<钉死版本>-slim-bookworm`（先镜像进集群 registry，Docker Hub 拉取超时过，`flex_plugin_stability.md`），cargo-chef 分层缓存依赖，`SQLX_OFFLINE=true`；
  运行层 `debian:bookworm-slim` + ca-certificates（要能 `kubectl exec` 进去排查，不用 distroless）。`/config/schedule.yaml` 照旧烤进去（Q6）。镜像名不变 `bifrost-flex-query`，Rust 用 `1.x` 版本号（并跑期 `1.0.0-rc.N`）。
- **构建流水线**：沿用名字 `bifrost-build-flex-query`（发布窗口的映射在 `bifrost-platform/api/internal/delivery/release_window.go:26` 和 `bifrost-trade-infra/k8s/cicd/tekton/task-release-window.yaml:43`，名字不变就不用改平台）。
  加参数 `variant=python|rust`；rust 变体**不克隆 core**（现在 core 与插件用同一个 `revision` 参数克隆，`k8s/cicd/pipeline-build.yaml:50-63`，退役后这个耦合一起消失）。冻结检查、发布窗口照旧在最前。
- **CI**：插件今天**没有任何分支 CI**（`trigger-trade-ci.yaml:236-237` 只列了 core/api/worker/research）。新增 `bifrost-ci-rust`：fmt、clippy、test（Postgres sidecar）、`cargo deny`、棘轮脚本、差分模糊、Python 的 `make lint test`（过渡期两套都跑）。依赖缓存用 CI 专用 PVC（只是缓存，正确性靠 `Cargo.lock`）。在 `bifrost-ci-*` 绿之前不建发布单。
- **发布窗口**：照 `release.sh window` / `hold --what bifrost-platform-plugin-flex-query`，一次一个会话。
- **清单**：录制卷 PVC、影子 Deployment（不同的 `part-of` 标签，自己的 deny-all 出站策略，只放行 DNS 和 Prometheus 抓取）、B 层 Job 都放在插件仓库 `k8s/`，走 `apply_manifest`。StorageClass 用哪个未核实（优先 NAS 上的 NFS）。
- **推 main** 只用 `push-main.sh`；它的 code-health 扫描要先认 `.rs`（infra 改动）。

---

## 七、Agent 怎么做这件活

- **任务仓库**：运行时今天只认 `bifrost-platform` 和 `bifrost-trade-infra`（`bifrost-platform/api/internal/agentrt/store/repos.go:68-95`）。要加 `bifrost-platform-plugin-flex-query`：
  - Setup（有网）：`cargo fetch --locked`（进本次尝试的 `CARGO_HOME`，同 Go 的 `GOMODCACHE` 做法，TD-404）；过渡期再建 Python venv、装 `../bifrost-trade-core`（Sibling，main）和 `.[dev]`，照 infra 的钉版本做法。
  - Verify：`cargo fmt --check`、`cargo clippy --workspace --all-targets --locked --offline -- -D warnings`、`cargo test --workspace --locked --offline`、`sh rust/ratchets.sh`、`make lint test`。
  - `TestDB: true`。
  - 这是平台代码改动（Go map），不是配置；走一次平台 PROD 发布（审批单）。做成配置是另一件事，这块不做。
- **agent-06 要装**：rustup 装钉死的 toolchain（含 clippy、rustfmt）到系统目录（如 `/opt/bifrost/rust`，只读），校验发布方的 SHA-256，照 `prepare-agent-06.sh:12-26` 装 Go/Node 的写法；出站 443 已放行 `static.rust-lang.org`、`crates.io`（规则只看端口，`agent-egress.nft`）。由 Owner 在主机上跑。
- **两个要先量的风险**：
  - 检查限时 900 秒（`repos.go:205`）：冷编译 tokio/axum/sqlx/reqwest 加 clippy 再加 test，可能逼近。切片 3 先在 06 上冷跑量一次；不够就让 Setup 预编译依赖，或给仓库单独的限时（平台改动）。
  - 磁盘：每次尝试的 `target/` 可能上 GB（TD-415 的磁盘守卫要算进去）。
- **谁写谁审**：Python 对照框架和 Rust 实现分给两家；每个切片的复核由另一家做（作者 Claude → Codex 审，反之亦然）。核心（`flex-domain`、`flex-store`）由强模型写；外围（Dockerfile、CI 清单、ratchets 脚本）可以外包。
- **额度**：后台道。BI-2 同时最多一个在途尝试；有 Owner 的业务（含 Screening）在排队时不派新切片。并跑阶段只花墙钟。运行时按额度路由（`bifrost-platform/api/internal/agentrt/store/claim.go:368`）；按 issue 限并发的开关是否存在未核实。
- **数据纪律**：agent 不读录制卷、不跑带真值的查询；影子和 B 层只给计数。提交信息、PR、交接文档提交前跑金额/账户 grep。

---

## 八、要记的数字（成功标准 5）

| 类别 | 指标 | 基线 / 来源 |
|---|---|---|
| Agent 来回 | 每个切片的尝试数、退回次数、复核轮数 | agentrt 的 attempt / verification |
| 复核发现 | 每轮 A/B/C 数，按类（unwrap/clone、逻辑、测试缺口、契约漂移） | 复核报告 |
| 额度 | 每家消耗 | `agentrt.budget_ledger` |
| 上线问题 | 并跑不一致次数（按类）、切换后 30 天内的事故/回滚/热修 | 影子日报、告警 |
| 代码量 | 生产代码行、测试行、依赖数、`#[expect]` 数、`.clone()` 数、`unsafe` 数 | Python：`src` 5,892 行 + core 的 Flex 写路径约 600 行；测试 3,444 行 / 160 条；4 个直接依赖 + core |
| 资源 | 镜像大小、Pod 内存/CPU 峰值、作业时长、冷构建时长、CI 时长 | 7 天每小时采样峰值：API 约 73 MiB、worker 约 42 MiB，CPU < 10 毫核；近 30 天作业 p50 约 1 秒（trades 完成 32、失败 4，transactions 完成 28） |

记在 BI-2 的问题对象里（运行时对象还没上线前，先记 `bifrost-trade-infra/agent-config/work/crew/BI-2-metrics.md`，只有计数）。回顾时用这张表决定下一块。

---

## 九、切片（按顺序）

| # | 切片 | 大小 | 谁 | 要 Owner |
|---|---|---|---|---|
| 0 | 本设计：统筹线程审 → Codex 独立复核（最多两轮）→ Owner 定 §10 | 半天 + 等 | 统筹 | **定 D-R1…D-R9** |
| 1 | Python 对照框架 + A 层夹具 + 怪癖测试 + 夹具守卫 | M | 家 X | — |
| 2 | 录制器（Python 0.14.0）+ 录制卷 + 形状抽取 + B 层 Job（Python 先自证） | M | 家 X | 批 apply（C）×2 |
| 3 | 平台加任务仓库；agent-06 装 Rust；06 上冷跑量时 | S–M | 统筹 + Owner | **跑主机脚本**；批平台发布 |
| 4 | Rust 工作区骨架：lint、棘轮、Dockerfile、`bifrost-ci-rust`、构建流水线 variant、code-health 认 `.rs` | M | 家 Y | cicd 清单由 Owner apply |
| 5 | `flex-domain`：解析、窗口、分类、cron、哈希、Python repr；A 层纯函数全过；差分模糊 | L | 家 Y | — |
| 6 | `flex-ib` + `flex-store` + worker；A 层库测试全过 | L | 家 Y | — |
| 7 | API 全部路由 + 指标；API 契约测试全过 | M | 家 Y | — |
| 8 | B 层：Rust 重放全部历史案例 | S | 家 Y | 批 apply（C） |
| 9 | 影子 Deployment，并跑 ≥10 个运行日 | S + 2–3 周墙钟 | 统筹盯 | 批 apply（C） |
| 10 | 切换 + 观察 5 个运行日 | S | 统筹 | **批切换单** |
| 11 | 退役 Python、录制器、影子、卷；回顾 | S | 家 X | 批 apply（C） |

X、Y 是两家不同的执行者。大小：S ≈ 半天，M ≈ 1–2 天，L ≈ 3–5 天 agent 时间（估不准，切片 1 做完再校）。

---

## 十、要 Owner 定的；待核实的事实

### 10.1 决定（推荐是第一项）

| 编号 | 问题 | 选项 | 推荐与理由 |
|---|---|---|---|
| **D-R1 架构级** | 引入 Rust 工具链 | A 钉死 stable + crates.io + `Cargo.lock` + `cargo deny`，Setup 里预取；B 再加 `cargo vendor` 把依赖源码入库；C 在集群里建 crates 代理 | **A**。B 让仓库膨胀、复核看不过来；C 是新服务 |
| **D-R2** | 并跑时 Rust 写哪 | A 影子 Pod 内的临时 Postgres（重放录制）；B GS 影子 schema（PROD DDL）；C 另建库 | **A**。零 DDL，生产表结构上碰不到，输入完全相同 |
| **D-R3** | 真报表与真行存哪 | A 插件命名空间的 PVC；B GS 新表 `raw_broker.flex_capture`（新表 + PROD DDL，顺带成为长期原始落地层）；C NAS 上的 MinIO（新凭据） | **A**。不出集群、不加表；丢了只是少几天语料，可以再录。若你想长期留原始报表，选 B，但那是另一件事 |
| **D-R4** | 仓库里放什么夹具 | A 按形状合成；B 真报表脱敏；C 不放（只有 B 层） | **A**。描述字段里有代码和金额，脱敏漏一处就公开；C 让 agent 在 06 上没法跑对照 |
| D-R5 | 切换前 Rust 打不打 IB | A 一次都不打；B 每天在 Python 成功 45 分钟后打一次；C 某个周日人工监督打一次 | **A**。B 每天多一倍请求，1018 按 token 冷却会伤到生产；C 可作为补充 |
| **D-R6 架构级** | 库的选择 | A §3.2 推荐列（sqlx 离线）；B 换 tokio-postgres；C 换 quick-xml | **A**。sqlx 把 SQL 也纳入类型检查，正对「用类型系统控债」 |
| D-R7 | 怪癖与有意差异 | A 切换前严格等价、切换后按正常改动修；B 重写时顺手修 | **A**。只有传输层错误文本（Q9）允许不同：要求类别相同、文本走固定模板，单独列为有意差异 |
| D-R8 | 并跑中出错怎么数 | A Rust 的错清零重数；B 不清零只顺延 | **A**。10 天的意义是连续 |
| D-R9 | 仓库形态 | A 同仓库 `rust/`；B 新仓库 | **A**。CI、发布窗口、任务仓库、Console 引用都不用改名；新仓库是第 13 个公开仓库 |

### 10.2 待核实（落地前查清）

1. GS 的会话时区（影响 API 时间偏移的写法）和 pod 的本地时区（`date.today()`）。
2. 部分唯一索引 `transactions_account_flex_tx_uidx` 的建立位置与 sidecar 建表脚本怎么同步（影子每天比一次 GS 目录与 sidecar 表结构，防漂移）。
3. 除本插件外，谁还会改 `executions_raw_flex` / `transactions`（Ledger 编辑走 core 的 `update_one_execution` / `patch_execution`？）——决定比对时哪些差异算噪声。
4. IB 回包有无 XML 声明、编码、命名空间（形状抽取会给出）。
5. registry 的 tag 保留策略，Python 镜像能否留到退役后 30 天。
6. 插件命名空间可用的 StorageClass；`apply_manifest` 能否写 Job / PVC（`actuation-policy.yaml` 的 resources 段）。
7. 集群里的 `bifrost-build-flex-query` 是否已是仓库版本（`bifrost-trade-infra/docs/RELEASE.md:382-386` 说当时还没 apply）。
8. TD-266（worker 的消息中心）0.13.2 之后的实际行为，Rust 照哪个版本。
9. 06 上冷编译加检查的实际时长、单次尝试 `target/` 的大小。
10. 运行时有没有按 issue 限并发的手段。
11. 本机 `bifrost-trade-core` 检出停在 0.36.2（origin/main 已 0.61.0）；`make docker-build` 用兄弟目录构建，现在会装旧 core——过渡期发 Python 0.14.0 前要先更新检出。
12. Rust 钉哪个 stable 版本、YAML 选哪个维护中的 crate。

---

## 十一、风险、刻意不做、留下的样板

### 11.1 风险与对策

| 风险 | 对策 |
|---|---|
| Python 的浮点 repr、`float()` 接受集、ElementTree 细节造成细微差异 | 怪癖逐条钉测试；差分模糊；形状抽取先告诉我们真数据里有什么 |
| 写库逻辑一份在 core、一份在 Rust，过渡期 core 改了 Flex 写法 | BI-2 期间 core 的 Flex 写路径改动必须同步改 Rust；插件 CI 里加一条测试比对 core 版本号下限 |
| 录制器拖慢或弄坏生产作业 | 开关、尽力而为、只多几次按键 SELECT；看作业时长 |
| 真数据泄露到仓库、提交信息、复核报告、产物 | 两层语料；影子只出计数和哈希；夹具守卫；提交前 grep |
| Agent 写的 Rust 债（unwrap、clone、as、巨函数） | §3.4 第一天的 deny 与棘轮；复核按类计数 |
| 检查超时、磁盘 | 切片 3 先量 |
| 后台道拖太久 | 并跑只花墙钟；每个切片完成写交接记录 |
| 切换时两个 worker 同时领活 | 同一 Deployment、Recreate、`SKIP LOCKED` |

### 11.2 刻意不做

需求说明列的全部：Research 分析与调度、包工队控制面（Go）、前端、IB Gateway 插件、market-data 插件、任何交易动作（D10）。
另外：不加业务能力；不改调度（不加 CronJob，Dagster 照旧）；不修怪癖（切换后再说）；不动 core 的 Flex 写路径（另批）；不移植死代码；不改 Console。D13：Rust 版和现在一样只写 `raw_broker.*` 与本插件的 `ops_jobs.*`。

### 11.3 留给下一块的样板

1. **录制器**：在旧服务里加一个只记不改的开关，攒真输入与写前写后状态，放集群私有卷。
2. **形状合成夹具**：抽结构不抽值，生成一眼假的数据，旧版算预期；加夹具守卫。
3. **对照框架先跑旧版**：A 层（公开、agent 能跑）+ B 层（私有、集群 Job），旧版必须先 100% 自证。
4. **Rust 工作区模板**：crate 分层（纯域 / 外部协议 / 存储 / bin 子命令）、lint 表、棘轮脚本与基线、`rust-toolchain.toml`、sqlx 离线、Dockerfile、`bifrost-ci-rust`、code-health 认 `.rs`。
5. **任务仓库条目模板**：Setup 预取依赖进尝试目录、Verify 固定命令、TestDB。
6. **按重放并跑**：影子 Pod + sidecar 库，不给生产凭据，不重复打外部服务。
7. **同 Deployment 换镜像切换**，回滚只换 tag。
8. **数字台账**：同一张表，回顾时比各块。
