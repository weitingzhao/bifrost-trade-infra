# BI-2：Flex 插件换成 Rust（第一块）—— 设计（第 2 版）

> **状态：已按复核 517 第 1 轮修订，等第 2 轮复核**（Codex gpt-6-astra，最多两轮）。级别仍是**大级**（新外部依赖、公开仓库的隐私边界、生产写路径加录制）。
> 上一版：infra `b7535a57` 的 `agent-config/work/crew/DESIGN-bi2-flex-rust-2026-10-22.md`。复核报告 `~/agent-work/codex-review-517/REPORT.md`（9 项 A、4 项 B），逐条答复见 `RESPONSE-517.md`；本版改了什么、为什么，见 §十二。
> 需求说明以 Owner 2026-10-22 23:15 CDT 确认的为准，本稿不改它。
> 引用缩写与版本（行号都按这些提交，用 `git show <sha>:<path>` 读）：
> `fq/` = `bifrost-platform-plugin-flex-query` `bf6c61c`（0.13.2）的 `src/bifrost_flex_query/`；插件仓库其他路径写「插件 `路径`」。
> `core/` = `bifrost-trade-core` origin/main `a87e39f`（0.61.0）的 `src/bifrost_core/`（本机 core 检出不是 main，见 §10.2 #12）。
> `platform` = `36481b9`，`infra` = `b7535a5`，`research` = `73694cc`。
> 所有数字只写计数，不写金额、不写持仓。

---

## 零、一页看完

- **换什么**：一个服务整体换。Python 的 `flex-query-api`（:8791，17 条路由；其中 `trigger`、`upload-xml` 在 API 进程里同步写库）和 `flex-query-worker`（队列、重试、补跑、心跳 :8080），
  连同它借用的 core 写库路径（Flex 成交、佣金、现金流水三张表），换成一个 Rust 程序。Deployment 名、Service、端口、表、指标名、JSON 形状都不变。
- **为什么不是为了省资源**：7 天峰值 API 约 73 MiB、worker 约 42 MiB，CPU 几毫核；作业 p50 约 1 秒（§8）。收益在类型和债，不在机器。
- **怎么证明一样（三层证据）**：
  1. **A 层（公开、合成）**：按 §一 的契约逐条写用例（含鉴权矩阵、两套回退状态机、24 条怪癖、行比较规则、生命周期失败注入），现行 Python 先过并生成期望；Rust 再过同一批。
  2. **B 层（私有、真实）**：Python 0.14.0 加录制器，**在写库事务里面**录写前、每条语句、写后，还录 IB 回包、读到的配置和统计、时钟、整个作业生命周期。
     每个案例先让 **Python 在临时库里重放**，必须复现生产写后状态，案例才算有效；再让 **Rust 重放**，必须与 Python 的重放结果逐行一致（含主键、`created_at` 规则、重复行数）。
  3. **并跑**：按 NYSE 交易日历数**至少 10 个交易日**（运行日另计）。每个计划槽、每次尝试都要对账到「一致」才计数；换了 Rust 候选就从 0 重数。
- **隐私**：真报表、真行、带账户内容的错误文本只在插件命名空间的私有卷和重放 Pod 的内存里。凡读真值的进程都开「私有模式」：日志只有 logger 名、级别和计数；
  异常只出类型、SQLSTATE、类别；输出只有计数、列名和案例内序号，不出键的哈希。泄露金丝雀在 CI 和集群里各跑一遍（§2.6）。
- **并跑时 Rust 写哪**：重放 Deployment（Python 引擎 + Rust 引擎 + 内存盘上的临时 Postgres）。不拿 GS 账号、IB token、Redis，出站全拒。**不需要任何 PROD DDL**，不多打一次 IB。
- **切换**：先停领活、排空，再在同一 Deployment 换镜像 digest 和 args（worker Recreate；API 保持滚动更新，混合版本已测）。回滚 = revert 切换提交（digest、command、args 一起回）。
  「进程回退」与「错误写入修复」分开：修复按 D-R11，每次 Owner 批。
- **Rust 的防线第一天就开**：deny lint 在 Cargo；计数棘轮和基线放在 **infra 的 code-health**（插件仓库里的改动改不动它）；插件接入推 main 的 CI 闸门。
- **Agent 接线**：平台加任务仓库要**同时**换掉 06 上的 agentd 二进制（TestDB 判断编进了 agentd）；agentd 给每次尝试钉 `CARGO_HOME`、`CARGO_TARGET_DIR`；
  所有 cargo 命令带 `--manifest-path rust/Cargo.toml`；缺工具链、缺库、少一条库测试都算失败。
- **要 Owner 定的 11 件**（§10.1）：新增 D-R10（录制器插在哪）、D-R11（写错了怎么修）。最关键的是 D-R1 工具链、D-R2 并跑写哪、D-R3 录制卷（含 worker 对 NAS 的可用性耦合）。
- **Owner 要动手的**：§10.3。没有 PROD DDL。
- **大小**：约 26 个 agent 日（上一版约 17），墙钟约 8 周（其中并跑至少 3 周）。估不准，切片 1 做完再校。
- **留给下一块的样板**：录制器（事务内接缝 + 事件日志）→ 私有语料、形状合成夹具、「旧版重放判有效、新版对旧版重放判等」的对照框架、私有模式与泄露金丝雀、Rust 工作区模板（lint、infra 棘轮、镜像、CI）、按交易日对账的并跑、停领活排空的切换、数字台账。

---

## 一、Python 版今天做什么（行为契约）

对照测试要钉住的就是这一节。凡是「怪」的地方先照搬（§1.7），切换后再按正常改动修。

### 1.1 进程、入口、谁在调

| 项 | 现状 | 依据 |
|---|---|---|
| API | uvicorn :8791，FastAPI，17 条路由；`trigger`、`upload-xml` **在 API 进程里同步**跑编排和 core 写库 | `fq/api/app.py:21-35`，`fq/api/manual_ops.py:65-118` |
| worker | 单进程轮询 5 秒；健康 :8080 `/health` `/healthz` `/ready`，答复里有 `last_error` 原文（截 500）和类别 | `fq/worker/loop.py:100-220`，`fq/worker/health.py:11-46` |
| 触发 | Dagster `research_flex_morning_schedule`，`30 6 * * 1-6` America/New_York（周六收周五），`POST /flex/ingest/enqueue {"slot":…}`，头 `X-Flex-Query-Write-Token` | `research` `orchestration/schedules.py:108-127`，`plugin_batch_assets.py:75-108` |
| 闸门 | Dagster `flex_gate` 读 `/flex/config/summary` 和 `/flex/dashboard/freshness-kpis`；读 `last_ok`、`last_success_at`，所以失败不能前移成功时间 | `plugin_batch_assets.py:331-351`，`orchestration/flex_husbandry.py:42-74` |
| Console | 平台代理 `/api/v1/plugins/flex-query/api/*` → :8791；状态页读两个 Deployment 名、`flex-query-health:8080/health`、`/flex/coverage/freshness` | `platform` `api/internal/flexquery/config.go:9-15`，`service.go:218-253`，`console/src/api/flexQueryPlugin.ts:288-397` |
| Trade UI | 经 Trade 网关 `/api/plugin/flex-query/*`（Traefik 注入 `X-Bifrost-Trade-Gateway: 1`）：summary、trigger、upload-xml、config/write、coverage/freshness | `bifrost-trade-frontend/src/api/flexQueryPlugin.ts:40-104`，`fq/api/deps.py:39-41` |
| 读这些表的 | Trade 经 core 读 `brokerage.*` FDW 视图；**`account_executions_id` 就是 `executions_raw_flex_id`**，对外可见，Ledger 按它改删。Research 读 `raw_broker.executions_final` 等 | `core/persistence/postgres/brokerage_views.py:183`，`core/portfolio/reader/accounts.py:269-302` |
| 别的写者 | Ledger：`update_one_execution`、`delete_one_execution`、`patch_execution`、`delete_execution_strict` 改删 Flex 原始行和佣金；TWS/网关：`update_execution_commission` 写佣金。现金表只有本插件写（已查 core、api、worker、research、platform；core `scripts/db/` 下的一次性迁移脚本除外） | `core/portfolio/reader/accounts.py:978-1012,1307-1486,1541-1698` |
| 告警 | `BifrostFlexIngest{Failed,MissedPlan,Stale,ScrapeDown}`、`BifrostFlexWorker{Down,Silent}`、`BifrostFlexToken{Missing,Expiring}`、`BifrostFlexCashCoverageGap` | `infra` `k8s/monitoring/bifrost-alerting-rules.yaml` |

### 1.2 向 IB 取数、解析

- 两步：`SendRequest`（`t`、`q`、`v=3`，可选 `fd/td` 或 `p`）→ `ReferenceCode`；`GetStatement` 最多轮询 24 次、间隔 5 秒，超时 60/90 秒，UA 固定 `Python/3.10`。`fq/client/flex_client.py:75-80,110-160,197-228`
- **报表就绪**只认含 `<FlexStatement>` 的 `<FlexQueryResponse>`；`<FlexStatementResponse>`（Warn 或 Fail，1019 是 Warn）、非 XML 都继续轮询，耗尽后抛出带 `[NNNN]` 的错误文本。`flex_client.py:167-194`
- 日期范围 >366 天在客户端就拒；只给一边日期也拒。`flex_client.py:125-141`
- **成交**（`parse_trades_xml`，`:439-704`）和**现金流水**（`parse_cash_transactions_xml`，`:242-436`）的字段规则在 §1.7 逐条列（Q1–Q4、Q11–Q20）。现金类型归一 `deposit/withdrawal/transfer/dividend/other` 用子串匹配（`:92-107`），A 层逐条钉。

### 1.3 窗口与回退（复核 A2 改写）

**trades 窗口**（`fq/orchestration/trades.py:157-184`）：

- 只给 from 或 to 中的一个：原样传下去，由客户端报错。两个都给：`range_mode=manual`，不改。
- 都没给：`to = 昨天`，昨天 = `date.today() - 1`（进程本地日期；镜像和两个 Deployment 都没设 TZ，现在是 UTC，§10.2 #1）。
  库里没有 Flex 成交（count=0 或 max_date 为空）→ `init`，`from = 昨天 - init_days`；否则 `incremental`，`from = 昨天 - (max(0, 昨天 - 最新 trade_date) + default_days)`。
- 不分段：窗口超过 366 天在客户端就失败（Q5）。

**cash 窗口**（`fq/orchestration/transactions.py:47-110,171-188`）：

- `last_dates` = 每个账户最后一笔现金的日期。只算在 `executions_raw_flex` 里出现过的账户；**`executions_raw_flex` 一行都没有时，所有有现金行的账户都算**（`:54-66`）。
- `last_dates` 为空 → `init`：`from = 昨天 - max(1, init_days)`；否则 `incremental`：`from = min(最早的 last_date, 昨天 - max(1, default_days))`；`to = 昨天`。
- 显式日期和自动窗口都按 ≤364 天分段（`CHUNK_MAX_SPAN_DAYS = 366 - 2`，`:34`）；日期解析不了就不分段、原样传（`:182-188`）。
- 天数来自 `ops_jobs.flex_settings` 一行（`read_flex_settings` 已 `max(1, …)`，`fq/schema/ddl.py:179-194`），无行用 30/360；读失败让作业失败（TD-116，`fq/orchestration/config_rw.py:157-170`）。

**回退：两套状态机，不是一套。** `allow = _truthy(payload.get("fallback", True))`。排队作业由 `enqueue_slot` 写入 `fallback=false`（`fq/scheduler/daily.py:103`），手动 `trigger` 也默认 false（`manual_ops.py:81`），
所以生产上平时都不回退；但带 `fallback: true` 的请求仍是契约。

trades，每个查询条目（`trades.py:38-110`），最多 3 次 SendRequest：

| 步 | 请求 | 结果 → 下一步 |
|---|---|---|
| 1 | from、to 都有：`fd/td` | 成功 → 步 2。报错：不是 1003（`[1003]` 或 `Statement is not available`）或 `allow=false` → 条目失败（原文）；是 1003 且 allow → 记 `primary_err`，跳步 3 |
| 1' | 缺一边：照传 | 客户端报错 → 条目失败 |
| 2 | — | 有行或 `allow=false` → 返回（空也返回）；否则步 3 |
| 3 | 默认期（无 `fd/td/p`） | 有行 → 返回，`fallback_kind` 为 `query_default_after_1003` 或 `query_default_after_empty`；空 → 步 4；报错 → 若还没有 `primary_err` 就记下它，步 4 |
| 4 | `p=5` | 有行 → 返回 `period5_after_empty_or_1003`；报错 → 有 `primary_err` 时报 `"{primary}; fallback query-default/period=5 also failed: {e}"`，否则报 e |
| 5 | — | 有 `primary_err` → 报它；否则返回空 |

cash，每个查询条目 × 每个分段（`transactions.py:189-202,267-297`），最多 2 次，**没有 `p=5`**：`allow_chunk = allow 且 分段数 == 1`。

| 步 | 请求 | 结果 |
|---|---|---|
| 1 | `fd/td`（或照传） | 成功（含空）→ 结束。**空成功不回退** |
| 2 | 报错，且 `allow_chunk`、from/to 都有、是 1003 | 默认期一次：成功 → 结束；报错 → 错误文本 `"{e}; fallback query-default failed: {e2}"` |
| 2' | 其他报错 | 错误文本 `str(e)`；多分段时加前缀 `"{from}..{to}: "` |

A 层为两套各钉：空成功、1003、1018、默认期失败、期 5 失败、多分段、半边日期、`fallback` 的各种写法（`"0"`、`"no"`、`false`、缺省）；每个用例断言**请求次数和参数**。

- 查询条目：`settings_flex` 按 `sort_order, id`，每行先 host 后 secondary token，query id 按逗号拆；无 token 的角色跳过（`config_rw.py:98-149`）。**写库顺序就是这个顺序**。

### 1.4 写库（三张 raw_broker 表 + ops_jobs）

| 表 | 写法 | 要钉住的 | 依据 |
|---|---|---|---|
| `raw_broker.executions_raw_flex` | 每行一条 `INSERT … ON CONFLICT (exec_id) WHERE exec_id IS NOT NULL AND exec_id != '' DO UPDATE SET` 54 列全覆盖；无 exec_id、有账户和 trade_id 时合成 `flex_<acct>_<trade_id>`；合成不了（缺 trade_id 或缺账户）→ 无冲突目标的普通 INSERT。**整个作业所有查询的行在一个事务里**，任一行出错整批回滚（`42P01` 例外，Q19） | **不写的列**：`executions_raw_flex_id`、`currency`、`strategy_opportunity_id`、`strategy_instance_id`、`legacy_account_executions_id`、`created_at`——已有行的这些列不能变。另有唯一 `(account_id, trade_id) WHERE trade_id <> ''`：与另一 exec_id 的行冲突时整批失败 | `core/portfolio/reader/accounts.py:686-975`，`core/persistence/postgres/brokerage_ddl.py:41-101,380-406` |
| `raw_broker.commissions` | 有「有意义」字段才写（币种非空就算）；`_zero_to_none` 把 0 当「没说」；`COALESCE(新, 旧)`；Flex 保留 IB 符号；跟成交同一事务 | TWS/网关、Ledger 也写 | `accounts.py:943-966`，`core/persistence/postgres/commissions.py:43-116` |
| `raw_broker.transactions` | core 先清洗：strip、`float(ts)`、`int(conid)`，缺账户/ts/report_date 跳过（缺 report_date 时 WARNING 带账户、ts、金额、类型）；有 `flex_transaction_id`：`ON CONFLICT (account_id, flex_transaction_id) WHERE flex_transaction_id IS NOT NULL` 覆盖 ts/amount/type/report_date、其余 COALESCE；没有：`ON CONFLICT (account_id, ts, amount, type, report_date)` 只 COALESCE；`ts` 用 `to_timestamp(%s)`；`report_date`、`available_for_trading_date` 以文本交给 PG 解析；整批一个事务；库错误原样抛出 | 写入 0 行算失败（`transactions.py:221-237`）；库错误的 `str(e)` 进 `result.error`（`:256-258`） | `accounts.py:1140-1304` |
| `ops_jobs.job_flex_ingest` / `flex_ingest_freshness` / `flex_worker_heartbeat` / `flex_settings` | 进程启动时跑幂等 DDL 和 `ADD COLUMN IF NOT EXISTS`；全部时间用 `clock_timestamp()` | §1.5 | `fq/schema/ddl.py:39-170,197-298`，`fq/worker/claim.py` |
| `raw_broker.settings_flex` | `POST /flex/config/write` 整表替换，与 `flex_settings` 同一事务 | — | `config_rw.py:225-320` |

- 只连 Golden Source，登录 `flex_writer`（`ops_jobs` 可 CREATE，`raw_broker` 只 DML）。`infra` `k8s/data/role-matrix/expected.yaml:224-234`
- 副作用：成交作业结束发一条 Trade 消息中心事件（Redis stream，话题 `portfolio.flex_executions`），消息里带错误原文；失败只记 WARNING。`fq/orchestration/notify.py:73-115`
- `new_rows` = 作业开始后 `created_at >= since` 的行数；`created_at` 是 `DEFAULT now()`（写事务的开始时间），所以只数真正新插的行。`fq/worker/handlers.py:79-98`

### 1.5 作业生命周期与事务边界（复核 A4 补）

各步不在一个事务里。录制和重放都按这张表切步（§2.2、§2.4）。

| # | 步骤 | 连接 / 事务 | 这一步失败时 |
|---|---|---|---|
| L1 | 认领：`SELECT … FOR UPDATE SKIP LOCKED`（`not_before` 到期，`priority DESC, created_at, id`）+ `UPDATE running, attempts+1, not_before=NULL` | worker 长连接，一个事务 | 库断：0/5/10/20/40/60 秒重连，用尽进程退出（`loop.py:33-83`） |
| L2 | `since = clock_timestamp()` | dispatch 自开的 `fresh_conn` | 返回 None，`new_rows` 为 None |
| L3 | 读 `settings_flex`、`flex_settings`、成交统计或现金末日 | 插件自开 GS 连接，每次读完 rollback | 作业失败（TD-116） |
| L4 | IB 两步 | — | §1.3 |
| L5 | 业务写：成交（含佣金）或现金 | **core 自开连接、自己 commit**（`accounts.py:686,968`；`:1159,1301`） | 整批回滚。成交：返回 `ok:false, "Failed to write account_executions."`；现金：异常原文进 `result.error` |
| L6 | 成交写后再读统计（`last_flex_date_after`） | 新连接 | 作业失败，**业务行已提交** |
| L7 | 消息中心事件 | Redis | 只 WARNING |
| L8 | `new_rows` | `fresh_conn` | None |
| L9 | freshness 成功行 | `fresh_conn`，单独 commit | 作业按失败走 L10b，**业务行已提交** |
| L10a | 成功：`mark_done(result)` | worker 长连接 | 非连接类错误使进程崩溃；作业停在 running，7200 秒后收回 |
| L10b | 失败：分类 → `mark_retry`；throttled 时再 `defer_pending` 把**其他所有 pending** 推后（`GREATEST(not_before, now+延时)`）；或 `mark_failed` | worker 长连接，各自 commit | 同上 |
| L11 | 失败的 freshness（`record_ingest_outcome`，新连接，`last_error = "类别: 原文"`） | 单独 commit | 只 WARNING |
| L12 | 心跳（计数、`last_error` 截 500） | worker 长连接 | 只 WARNING |
| L13 | 空闲：每 12 轮收回卡住的 running、补跑入队、心跳 | worker 长连接 | 补跑失败只 WARNING |

- **入队去重**：`payload_hash = sha256(json.dumps(sort_keys, (",",":"), default=str))[:16]`，`fallback`、`catchup` 不算身份；`(kind, hash)` 在 pending/running 时唯一。`fq/scheduler/enqueue.py:18-67`，`daily.py:36,81-120`
- **分类**（`fq/worker/retry.py:28-73`）：任何 `[1018]` → throttled；1010–1017、1020 或配置类关键词 → config；1003–1009、1019、1021 → not_ready；网络/库关键词 → transient；其余 unknown。
- **计划**（`retry.py:114-138`）：config 直接失败；用满次数失败；not_ready/throttled 延后 1800 秒；transient 120、unknown 300；配置最小 30 秒（`:94`）。
- 部分账户失败 = 作业没完成（`handlers.py:21-31`）。卡住的 running 超过 7200 秒退回 pending（延后 600 秒）或失败（`claim.py:95-135`）。
- 补跑：计划时刻过了 45 分钟、24 小时内、该类没有更新的作业，就入队，`as_of` 是计划时刻在调度时区的**当地日期**（`fq/worker/catchup.py:21-95`）。
- 计划/偏差：cron 只解析分、时、星期（Q22）；偏差 = 计划后 2 小时窗口（`fq/api/ingest_dashboard.py:55-64`）。

### 1.6 HTTP 契约与鉴权（复核 A1 改写）

- 写接口：`enqueue`、`jobs/{id}/run-now`（throttled 冷却中 409，`force` 放行）、`trigger`、`upload-xml`（同步执行，也落一行 job）、`config/write`。`fq/api/ingest.py:31-148`，`manual_ops.py:65-118`，`fq/api/config_summary.py:134-174`
- 读接口：`/health`、`/metrics`、`/flex/ops/check`、`/flex/dashboard/freshness-kpis`、`/flex/ingest/{kinds,jobs,queue-summary,queue-dashboard}`、`/flex/config/summary`、`/flex/coverage/{db-summary,freshness,raw-peek}`。

**鉴权是两条规则，不是一条**（`fq/api/deps.py:13-57`）：

- 期望令牌 = 配置的 `write_token` 或环境变量 `FLEX_QUERY_WRITE_TOKEN`，去空白。
- 收到的令牌 = `X-Flex-Query-Write-Token` 去空白；为空且 `Authorization` 以 `bearer `（不分大小写）开头时取其后部分去空白。
- 网关头 = `X-Bifrost-Trade-Gateway` 去空白后等于 `"1"`。

| 路由 | 依赖 | 期望令牌为空 | 期望令牌非空 |
|---|---|---|---|
| `enqueue`、`run-now`、`trigger`、`upload-xml` | `require_write_token` | **任何请求都放行** | 令牌相等，或网关头 → 放行；否则 401 `invalid write token` |
| `config/write` | `require_config_write_identity` | **只有网关头放行**；带任何 bearer、任何令牌都 401 | 令牌相等，或网关头 → 放行；否则 401 |
| 其余 GET | 无 | 放行 | 放行 |

- `config/write` 之后的顺序：401 → body 里出现 `host_token`/`secondary_token`（值为 null 也算）409 → 没有可写字段 400 → `accounts` 归一后为空 400 → 写失败 500。
- 路由级依赖先于 `db_conn`，所以 401 在 503（库不可用）之前；body 不是合法 JSON 时的状态码以 Python 生成的期望为准。
- A 层鉴权矩阵：期望令牌 空/非空 × 无凭据/错令牌/对令牌/bearer/网关头/网关头值非 1 × 每条写路由，外加 `config/write` 的 409/400 组合。
- `/metrics`：手写文本，告警读其中 6 个名字（§1.1）；另有 `http_requests_total`、`http_request_duration_*`。`fq/api/metrics.py:53-137`，`fq/api/http_metrics.py:44-53`

### 1.7 怪癖清单（先照搬，各有测试钉住）

| # | 怪癖 | 依据 | 处理 |
|---|---|---|---|
| Q1 | `contract_key = symbol\|sec_type\|expiry\|str(float(strike))\|right`，用 Python 浮点 repr（`150.0`） | `flex_client.py:520-539` | Rust 实现 Python 的 repr 规则 |
| Q2 | 数字走 Python `float()`/`int()` 的接受集（空白、`+`、`_`、`inf`、`nan`）；各字段的差别见 Q12、Q13 | `:343-346,511-518,546-553` | 照搬 |
| Q3 | 现金 `raw_extra` 是全部属性；成交只放未知属性 | `:382-386,631-687` | 照搬 |
| Q4 | 现金属性值解析时不去空白（transactionID 除外）；core 写库时再 strip 大部分文本列，`raw_extra` 保留原样 | `:300-341`；`accounts.py:1216-1254` | 照搬 |
| Q5 | trades 不分段，窗口 >366 天直接失败（README 写的是两类都分段） | `trades.py:186-222` | 照搬并记 TD |
| Q6 | worker 读镜像里烤进去的 `schedule.yaml`，API 读 ConfigMap | 插件 `Dockerfile:19`、`k8s/base/deployment-worker.yaml`（无 schedule 卷） | Rust 镜像同样烤一份 |
| Q7 | 鉴权是两条规则（§1.6）：令牌为空时四条写路由全开，`config/write` 只认网关头；网关头可被集群内任何调用方伪造 | `deps.py:28-57` | 照搬两条规则，另记 TD |
| Q8 | 死代码：`trim_old_jobs`、`summarize_categories`、`update_freshness`、`next_catchup_window`、`flex-query-schedule` CLI | 无调用方 | 不移植（行为不变） |
| Q9 | 传输层和数据库错误的文本来自 urllib/psycopg2，分类靠子串；数据库错误的 DETAIL 带冲突键和值 | `retry.py:40-53` | 分类一致是硬要求；文本见 D-R7 |
| Q10 | FastAPI 自带 `/docs`、`/openapi.json` | — | 无调用方（未核实），不移植 |
| Q11 | 数值列都是 `double precision`，不是 decimal；`-0.0`、`NaN`、`inf` 按位保留（`_f` 接受 `nan`）；`principal_adjust_factor` 是文本 | `brokerage_ddl.py:41-101` | Rust 用 f64，按位比 |
| Q12 | 成交的 `order_id`、`conid`、`underlying_conid` 先过 `str.isdigit()`：`+1`、`-1`、`1_000` 都得 NULL；Unicode 数字过得了 `isdigit` 但 `int()` 抛错，整次解析失败。现金的 `conid` 直接 `int()`（失败为 None）：`+1`→1、`1_000`→1000、` 1 `→1；core 再 `int()` 一次 | `flex_client.py:584,591,598,408-412`；`accounts.py:1246-1250` | 照搬各自规则 |
| Q13 | 千分位：成交的 quantity、price、`_f` 系列去 `,`；**strike 不去**（`1,000` → None → `contract_key` 的 strike 段为空）；现金 amount 去 `,`，现金 `fx_rate_to_base` 不去 | `:511-518,525-528,546-553,344,423-427` | 照搬 |
| Q14 | 币种：成交行 `currency` = 成交币种，没有才用佣金币种（旁边注释说佣金优先，**不按注释改**）；54 列 INSERT 不含 `currency`，所以 `executions_raw_flex.currency` 从不由 Flex 写，这个值去了佣金表。`realized_pnl = fifoPnlRealized`。币种非空就写佣金行（佣金为 0 时 0→NULL→保留旧值） | `:587,627,689-694`；`accounts.py:781-792,943-966` | 照搬 |
| Q15 | XML 解析失败返回空列表（WARNING）；成交 0 行且正文含 `CashTransaction` → 报「用错 Query」；否则 0 行算成功。报表级账户 = **第一个**带 accountId 的 `FlexStatement`，作为整份回包所有缺账户行的后备（多账户回包也一样）。`iter()` 去命名空间匹配标签，子元素 `find("accountId")` 不去命名空间 | `:257-276,455-475,697-703,83-89` | 照搬 |
| Q16 | NULL / `''` / 缺键：成交 `x or None`；现金行空字段不放键；core 去空白后 `or None`；成交 `raw_extra` 为空 dict 时写 NULL（`json.dumps(raw_extra) if raw_extra else None`） | `accounts.py:755-756,1220-1254,1297` | 照搬 |
| Q17 | 顺序与重复：同一作业里同一 exec_id 出现两次，后写的赢（逐行语句、同一事务）；`(account_id, trade_id)` 与另一 exec_id 冲突 → 唯一键错误 → 成交整批回滚 → 文本归 `unknown`，300 秒后重试；exec_id 缺且合成不了（缺 trade_id 或缺账户）→ 普通 INSERT，**每跑一次多一行** | `accounts.py:726-735,859-918`；`brokerage_ddl.py:394-397` | 照搬并记 TD |
| Q18 | 日期：成交的 `reportDate/tradeDate/settleDateTarget` 取 `s[:8]` 按 `%Y%m%d`，ISO 写法（`2026-10-21`）得 NULL；现金的 `report_date`、`available_for_trading_date` 以文本交给 PG 解析（受 DateStyle 影响），ISO 写法能入库 | `flex_client.py:231-239,542-544`；`accounts.py:1254,1267` | Rust 传同样的文本 |
| Q19 | 成交写库遇 `42P01`（表不存在）：回滚、继续下一行（之前的行丢掉） | `accounts.py:924-932` | 照搬（A 层用缺表的临时库钉） |
| Q20 | 时区：成交 `dateTime` 是 `FLEX_LOCAL_TZ`（默认纽约）墙钟；DST 重叠取第一次（fold=0），不存在的墙钟用跳变前的偏移；只有日期取当地零点；core `datetime.fromtimestamp(float, utc)`（微秒取整）。现金 `ts` 只取日期、按 UTC 零点，PG `to_timestamp(float)` | `flex_client.py:42-73,349-379`；`accounts.py:765-772,1191` | 照搬；chrono-tz 的 Ambiguous/None 显式映射到 Python 语义 |
| Q21 | 「今天」不统一：窗口用进程本地日期；入队默认 `as_of` 是入队时刻的 **UTC 日期**；补跑 `as_of` 是计划时刻的**调度时区日期** | `trades.py:166`；`daily.py:97-99`；`catchup.py:49-50` | 照搬，不统一 |
| Q22 | cron 只看分、时、星期（周日 = 0），日、月忽略；逐分钟按 UTC 前进再换到时区判断；`next_fires` 从 `after + 1 分钟` 截到整分开始，终点不含；`previous_fire` 终点不含 | `fq/scheduler/cronutil.py:37-95` | 自己移植，边界分钟各一条测试 |
| Q23 | API 时间：FastAPI 用 `isoformat()`（微秒为 0 时省略，偏移随库会话时区）；部分字段强制 `%Y-%m-%dT%H:%M:%SZ`（`run-now` 的 `was_not_before`、worker `last_claim_at`、看板的 `iso_z`） | `ingest.py:146`，`loop.py:96-97`，`cronutil.py:98-100` | 只对真正的时间戳字段按瞬时比；日期字符串按字符串比 |
| Q24 | `job.result` 用 `json.dumps(…, default=str)`：非 JSON 值变 `str()`（datetime 是空格分隔的 `YYYY-MM-DD HH:MM:SS+00:00`）；`payload_hash` 用规范 JSON 的字节 | `claim.py:150`；`enqueue.py` | result 按 jsonb 比，字符串值逐字节；哈希用 Python 生成的向量钉 |

---

## 二、业务级对照测试

### 2.1 三种证据

| 层 | 内容 | 放哪 | 谁能跑 |
|---|---|---|---|
| **A：合成** | 按契约写的用例 + 按真报表「形状」生成的假报表；期望由 Python 版算出（行、语句、作业行、API 答复） | 仓库 `tests/characterization/`（公开） | 所有人；agent-06 沙箱（无网）、CI |
| **B：真实** | 录制器录下的案例（事件日志，§2.2） | 插件命名空间私有卷，永不出集群 | 只有重放 Deployment（§4.1）；输出只有计数 |
| **并跑** | B 层的新案例，按交易日对账 | 同上 | 同上 |

为什么要 B 层：需求说的是「真报表、真行」；但 agent 在 06 上碰不到它（06 只出公网 443 和 Gitea，`infra` `scripts/agent-host/agent-egress.nft`），A 层才能进它们的检查。

**判等的基准**：B 层里 Rust 对照的是「Python 在同一临时库、同一输入下的重放结果」；生产写后状态只用来判断「这个案例录对了没有」（§2.4 第一行）。

### 2.2 录制器（Python 0.14.0，复核 A4 重写）

**开关**：`FLEX_CAPTURE_DIR`。关着时不装任何接缝，代码路径与 0.13.2 相同（A 层 golden 在加录制器之前生成，加之后照样全过）。

**四个接缝**（D-R10 推荐 A）：

1. **IB 传输**：`flex_client` 里两处 `urlopen`（`:145,213`）改为经一个 transport 函数。录请求（路径、`q`、`v`、`fd/td/p`；**不录 `t`**）和回包（HTTP 状态、正文全文，或异常类型与文本）。
2. **业务写连接**：core 写明的测试接缝 `write_support.connect`（`core/monitor/reader/write_support.py:62-63`；`open_conn` 每次都经它，`:67-77`）。只在录制上下文（contextvar）里、`golden=True` 时包一层代理连接：
   - 第一条语句前，在同一事务里读两个序列的当前值（`pg_sequence_last_value`，权限 §10.2 #4）。
   - 每条 `INSERT` 执行前，在**同一事务**里按这条语句自己的参数读该行现状：成交按 exec_id 和 `(account_id, trade_id)`，佣金按 exec_id，现金按它的冲突键（参数与 INSERT 相同，`to_timestamp` 也相同）。同一键第一次出现时读到的就是写前状态。
   - 记每条语句（SQL 文本的哈希、参数、顺序）。
   - `commit()` 之前，在同一事务里按所有碰过的键读写后状态，记 `pg_current_xact_id()` 和事务开始时间 `now()`；然后 commit，记结果（成功 / 异常类型 + SQLSTATE）。`rollback()`、没 commit 就 close 也记。
   - **不加锁**（不 `FOR UPDATE`），生产写路径的锁行为不变。读的都是本事务视角，提交后别人的改动进不来。剩下的窗口（本事务读写前之后、写之前，别的事务提交了同一键）不靠录制消除，靠 §2.4 的「案例有效」检查发现。
3. **插件自己的连接与函数**：worker 长连接（`WorkerDb._connect`，`loop.py:49-52`）和 `fresh_conn`（`handlers.py:56-59`）也包代理：`defer_pending` 执行前在同一事务里读全部 pending 行（id、not_before）；
   `mark_*`、`record_freshness`、`record_heartbeat` 记语句和参数，并在同一事务里读写后行。读函数（`get_flex_config`、`get_flex_range_days`/`resolve_flex_range_days`、`get_flex_executions_stats`/`read_flex_executions_stats`、`read_last_transaction_dates`）记返回值；
   token 只记「有/无、host/secondary」。消息中心事件记字段。
4. **时钟**：0.14.0 把插件里的 `date.today()`、`datetime.now()`、`time.time()`、`time.sleep()` 收进一个 `clock` 模块（纯搬家；A 层 golden 在搬家前生成），录每次返回值。

**一个案例 = 一次尝试的事件日志**，按 §1.5 的 L1–L12 顺序：认领后的作业行 → 读事件 → IB 交换 → 业务写事务（写前、序列、语句、写后、提交结果）→ 写后读 → 通知 → `new_rows` → freshness → `mark_*` / `defer_pending`（含其他 pending 行前后）→ 心跳计数。
另记：插件 SHA、core SHA（`ci/core-pin`）、镜像 digest、录制器版本、当天 schema 指纹编号。格式带版本（`case.v1`）；A 层合成案例用同一格式，所以 CI 也在跑同一条重放代码。

**完整性**：认领后先写 `started/<job>-<attempt>`；全部写完、算好校验和后，从 `tmp/` 原子改名到 `cases/<job>-<attempt>/`（同一文件系统内 rename）。读者只看 `cases/`。有 started 没有 case = 不完整。

**不拖住生产**（复核 B3）：写盘在后台线程，内存队列有上限（64 MiB）；开始一个案例前查剩余空间，低于 1 GiB 就不录并计数；作业结束后最多等 30 秒，写不完就放弃这个案例（只少一个案例，作业照常）。
录制异常只 WARNING，文本固定、不带值。NFS 用 soft 挂载（D-R3），I/O 卡住时返回错误而不是永远挂起。

**范围**：录 worker 的全部尝试（含失败、补跑）。API 的手动 `trigger`/`upload-xml` 不录：API 不挂卷，免得 Trade 网关跟着依赖 NAS；这两条由 A 层和混合版本测试覆盖，台账里单列为「设计内未录」。

**每天一次 schema 指纹**：worker 空闲时读三张业务表和四张 `ops_jobs` 表的列、类型、默认值、索引（含部分索引谓词）、约束。只有结构，没有数据。重放 Pod 拿它对照自己的建表脚本（防漂移，也回答 §10.2 #2）。

**保留**：至少 60 天；用于签收的并跑案例和切换后观察期的案例保留到退役后 30 天（修复要用，§5.6）。容量：近 30 天两类约 64 个作业，案例为 KB 到 MB 级。

### 2.3 合成夹具（A 层）怎么来

1. 集群里跑**形状抽取**（私有模式），只输出固定结构：
   - 元素名、属性名：只输出在 IB 公开 Flex 字段名白名单（入库文件）里的名字；白名单外的只给个数。
   - 每个属性值的格式类别，取自固定枚举：`digits8`、`digits8;digits6`、`iso-date`、`decimal(scale)`、`decimal-thousands`、`signed`、`empty`、`upper-alpha(1..6)`、`other`。
   - 各类行数按桶：0、1、2–10、11–100、>100。
   - 元素式还是属性式、有无命名空间、有无 XML 声明与编码。
   - **不输出描述模板，不把任何值做字符串替换后输出**（复核 A3）。
2. 输出由统筹线程看一遍再入库。
3. 生成器按形状造假数据：账户 `U000000x`、代码 `ZZA..ZZZ`、整数价格、2001 年的日期；描述字段只用按 IB 公开格式手写的假模板。刻意造边角：0 行报表、1019 Warn、1018、日期缺失、
   同 exec_id 重复、host/secondary 重叠、跨月、跨 DST，以及 §1.7 Q11–Q24 和 §2.5 列出的每一条。
4. 期望由**现行 Python 版**跑出（golden）。golden 文件头记血缘：插件 SHA、core SHA、生成器版本。测试只读 golden，**从不自动重生成**；更新只走 `make golden-update`，产出 diff，由另一家复核（复核 B4）。
5. 防线：夹具守卫测试——夹具里的账户、代码、日期都必须落在假词表里；提交前对 diff 跑金额/账户 grep（`test_fixtures_copied_from_dev.md` 的教训）。

### 2.4 比什么、怎样算一样（复核 A4、A5）

| 对象 | 怎样算一样 |
|---|---|
| **案例有效** | Python 在临时库里从写前状态出发，按录到的读、IB 回包、时钟、失败注入重放，结果必须与生产写后状态**完全相同**（含新行主键：两个序列先 `setval` 到录到的值）。不同 → 「不可判等」：不计入验收，不算 Rust 的错，也不当噪声；单独计数，由框架作者查清（外部写入还是录制有洞）。 |
| 三张业务表 | 多重集合逐行相等，**保留重复行的个数**。浮点按位、时间到微秒、`NULL` 与 `''` 区分、jsonb 按语义。<br>**写前已有的行**：主键、`created_at`、不在写入列里的列（`currency`、`strategy_*`、`legacy_*`）都不能变。<br>**新行**：主键必须相等（两边序列从同一个值起；每条 `INSERT … ON CONFLICT` 不论冲突都消耗一个序列值，所以语句条数和顺序也被钉住）；`created_at` 必须等于各自写事务的开始时间。<br>另查：两个唯一键都无重复；`new_rows` 相等。 |
| 语句 | 每张表的语句条数、顺序、参数相等。这是辅助手段，结论以行为准（参数相同不代表 SQL 保留了同样的列）。 |
| 作业生命周期 | 每一步之后的作业行：status、attempts、error_category、result（jsonb 语义）；freshness 行；心跳计数增量；`defer_pending` 推后的作业集合。时间列按关系比：有没有值、先后、`not_before - updated_at` 与计划延时相差 ≤1 秒。 |
| 失败注入 | 录到的失败（L5–L12 任一步的库错误、传输错误）在重放里同一步注入，比之后的状态。 |
| 读 | 两个引擎的读都从录到的结果注入（不在临时库里重建全表）。Rust 发出的读必须与 Python 同种类、同顺序；对不上录到的读事件就算 Rust 不一致。读的 SQL 本身由 A 层库测试检查。 |
| 重试分类 | A 层：固定错误模板 + 假值造的文本（模板来自代码里的报错串、IB 公开的错误码文本、psycopg2/urllib 的公开报错格式）。B 层：历史真实错误文本**在集群里**分别喂 Python 和 Rust 的分类函数，只输出每类一致/不一致的计数（复核 A3）。 |
| 窗口 | （读到的统计、settings、today）→（from、to、mode、days、分段），A 层全覆盖 |
| API | 只在 A 层：固定库状态、固定时钟，每条路由 × 鉴权矩阵的状态码和 JSON；时间按 Q23；`/metrics` 按样本（名、标签、值）比 |
| 副作用 | 消息中心事件的话题、字段（时间、随机 id 除外） |
| 纯函数 | 固定向量 + 有种子的性质测试（解析、repr、窗口、cron、哈希）；Python 与 Rust 用同一批向量 |

「一样」之外只允许 Owner 批过、单独列名的**有意差异**（D-R7）。

### 2.5 先让 Python 过

- **A 层（切片 1）**：`tests/characterization/`，必须有的用例：
  - 鉴权矩阵（§1.6）；两套回退状态机（§1.3）；Q1–Q24 每条。
  - 行案例（复核 A5）：同一报表连跑两次；批内重复 exec_id 后写赢；两个唯一键互相冲突；缺 exec_id 有 trade_id；缺 exec_id 也合成不了（每跑多一行）；写前已有行的 `strategy_*`、`created_at`、主键保留；比较器对重复行计数的自测。
  - 生命周期失败注入：L5 成功后 L6/L9 失败；L10a 失败；1018 推后其他 pending；卡住收回；补跑入队。
  - 混合版本骨架（先只有 Python 两端，§3.5）。
- **库测试必须真的跑**（复核 B1）：`make test` 仍排除 `db`（插件 `Makefile:16-17`）。新加 `make test-char-db`：没有 `AGENTRT_TEST_PG`（或 CI 的同名变量）就**失败**，不 skip；打印执行条数；条数不得少于 `tests/char-db.manifest` 的条数，manifest 的条数由 infra code-health 棘轮只增不减。
- **B 层（切片 2）**：重放 Deployment 先只有 Python 引擎。每个新案例做「案例有效」检查。**有效率必须 100%**：每个不可判等的案例都要查清，只有确认是外部写入（有对应的 Ledger/TWS 写入可查）的才能排除；查不清就修录制器或框架，不进 Rust。
- **框架自证**（复核 A4）：用合成场景证明「案例有效」检查能抓到问题，每种都必须判为「不可判等」或「不完整」，不能判「一致」：
  (a) 写前读之后、写之前，另一事务改同一佣金；(b) Ledger 式地改一条 Flex 行；(c) 业务已提交、freshness 失败；(d) `mark_done` 失败；(e) 缺一个 IB 回包事件；(f) 新键在写前读之后被别人插入。
- 框架作者与 Rust 作者**不是同一家**。

### 2.6 隐私边界（新，复核 A3）

**哪里可以有真值**：插件命名空间的录制卷（`cases/`、`verdicts/private/`）；重放 Pod 的内存盘和进程内存；生产 GS 本身。
其他地方一律没有：仓库、镜像、构建上下文、日志、指标、verdict 文件、CI 产物、复核报告、提交信息、交接文档、Agent 的上下文。

**私有模式**（形状抽取、Python 引擎、Rust 引擎、修复工具——凡读真值的进程都开）：

- Python：根 logger 换成只输出「logger 名 + 级别 + 计数」的 handler，丢掉消息、参数和 `exc_info`；`sys.excepthook` 只打异常类型。
  这样 core 里带账户、金额的「缺 report_date」WARNING（`accounts.py:1257-1264`）和带 exec_id、`exc_info` 的写库失败 WARNING（`:934-940`）都出不来。
- Rust：凡来自案例的值都包在 `Private<T>` 里，`Debug`/`Display` 只打 `‹private›`；错误类型只带类别、IB 代码、SQLSTATE；`print_stdout`/`print_stderr`/`dbg_macro` 已 deny；panic hook 只打代码位置。
- 异常：引擎捕获全部异常，日志只写类型、SQLSTATE、分类类别；全文写 `verdicts/private/<case>/`。
- Postgres sidecar：`log_min_messages=panic`、`log_min_error_statement=panic`、`log_statement=none`、`log_connections=off`、`log_disconnections=off`、`log_error_verbosity=terse`；
  数据目录 `emptyDir{medium: Memory}`，Pod 删了就没了。错误的 DETAIL 只到客户端（引擎），按上一条处理。
- 输出：verdict 与指标只有计数、表名、列名、案例编号、案例内行序号。**不输出键的哈希**：账户号是 U 加 7 位数字，不加盐的哈希一穷举就还原。序号对应的真值只在 `verdicts/private/`。指标标签只用固定枚举。
- 调试：差异的真值只写 `verdicts/private/diffs/`。Rust 作者拿到的是「列名 + 两边各属哪个格式类别（§2.3 的枚举）」，据此写合成用例复现。复现不了，由 Owner 用 `owner_run_command` 自己看私有差异（Owner 看自己的账户数据不受此限）。

**泄露金丝雀**：一组合成案例，所有自由文本位置都放标记（假账户 `U9CANARY1`、金额 `987654.321`、描述 `CANARY-FREE-TEXT`、IB 错误文本含账户标记），并注入失败
（唯一键冲突让 DETAIL 带标记、缺 report_date、XML 解析失败、IB Fail 体、写库 `42P01`）。用私有模式跑 Python 引擎、Rust 引擎、形状抽取，再在 stdout/stderr、PG 日志、verdict 目录（不含 `private/`）、
`/metrics`、CI 产物、镜像构建上下文里 grep 标记，命中数必须为 0。CI 每次跑；重放 Deployment 启动时先以子进程跑一遍，抓它们的输出和 PG 日志自查，命中就拒绝启动。

**生产日志**：Python 0.13.x 的生产日志今天就会带这些内容（上面两条 core WARNING；worker 的 `msg[:300]`、`msg[:500]`，`loop.py:185-202`）。Python 版只加录制器、不改这些，记 TD，退役时关。
Rust 的生产日志从第一天起只有类别、IB 代码、SQLSTATE、作业号、计数——日志不在契约里。`job.result.error`、`freshness.last_error`、心跳和 `/health` 的 `last_error` 在契约里（Console 读），按 D-R7 处理。

---

## 三、Rust 版

### 3.1 布局（同仓库 `rust/`，Cargo workspace，Python 退役时删 `src/`；复核 B4 精简为 3 个 crate）

| crate | 内容 | 约束 |
|---|---|---|
| `flex-domain`（lib） | 类型（`AccountId`、`ExecId`、`TradeDate`、`QueryRole`、`Kind`、`ErrorCategory`…）、XML 解析、Q1–Q24、窗口与分段、两套回退状态机、分类与重试计划、cron、payload 哈希、NYSE 交易日历（公开数据） | 无 I/O：不准依赖 tokio、sqlx、reqwest、redis（infra code-health 用 `cargo tree` 查） |
| `flex-query`（lib + bin） | `ib`（`trait FlexTransport`）、`store`（sqlx）、`notify`、`worker`、`api`、录制器（同格式）；子命令 `api` / `worker` | 生产镜像只含这个 bin |
| `flex-replay`（bin） | 重放引擎、比较器、对账台账、金丝雀、修复（§5.6） | 只进重放镜像；不编进 reqwest、redis；**候选身份**只算前两个 crate（§4.3） |

### 3.2 主要库（架构级：新外部依赖，见 D-R6）

| 用途 | 推荐 | 备选 / 说明 |
|---|---|---|
| 异步 | tokio | — |
| HTTP 服务 | axum + tower-http | — |
| HTTP 客户端 | reqwest（rustls，webpki 根证书） | ureq（同步） |
| XML | roxmltree（DOM，和 ElementTree 的 `iter()` 一一对应） | quick-xml |
| Postgres | sqlx（离线模式，`.sqlx/` 入库，SQL 编译期校验） | tokio-postgres（运行期校验） |
| 时间 | chrono + chrono-tz | time |
| 序列化 | serde、serde_json；YAML 选仍在维护的 serde_yaml 分支（未核实哪个） | — |
| 日志 | tracing（JSON，字段白名单） | — |
| 错误 | thiserror；main 里才允许 anyhow | — |
| cron | **自己移植**（语义与 Python 相同，Q22） | `cron` crate 的星期编号和字段数不同，不用 |

不用 `sqlx migrate`：它会在 Golden Source 建 `_sqlx_migrations` 表，那是新表。先不用 cargo-chef（复核 B4），切片 4 量过冷构建时长再定。

### 3.3 怎样保持同一契约

- 路由、方法、状态码、`detail` 文本、JSON 键名逐条照搬；路由清单由一条测试对着 Python 的 OpenAPI 清单比（不含 `/docs`）。鉴权按 §1.6 的两条规则分别实现，各有矩阵测试。
- 时间输出按 Q23；客户端都按瞬时解析（TS `Date`、Go `time.Parse`）。
- 错误文本：IB 来的（`[NNNN] message`）、模板文本（`Flex query 1/2 (host …): …`、`flex-trades partial: …`、两套回退的拼接文本）逐字照搬；传输层和数据库错误按 D-R7。分类函数与 Python 同表。
- payload 哈希：实现 Python `json.dumps(sort_keys, separators, ensure_ascii, default=str)` 的规范形，用 Python 生成的向量钉住——切换那一刻 Python 留下的 pending 作业要能和 Rust 的入队去重。
- 写库：同 SQL、同语句顺序、同事务边界（成交整批一个事务、现金整批一个事务、佣金跟着成交行；§1.5 的每一步各自提交）。读：同种类、同顺序。
- UA、轮询次数、超时、延迟默认值、补跑宽限、卡住阈值全部同值。幂等 DDL 与 Python 逐句相同（混合版本时两边都会跑）。
- 时钟、IB、库都经 trait 注入，测试能固定 `now/today` 并按步注入失败。进程本地日期用 `chrono::Local`，镜像同样不设 TZ，有测试钉住。

### 3.4 lint 与棘轮（复核 B1）

- `rust/Cargo.toml` 的 `[workspace.lints]`：
  - `rust`：`unsafe_code = forbid`，`unused_must_use = deny`。
  - `clippy` deny：`unwrap_used`、`expect_used`、`panic`、`todo`、`unimplemented`、`indexing_slicing`、`string_slice`、`as_conversions`、`float_cmp`、`dbg_macro`、`print_stdout`、`print_stderr`、
    `allow_attributes`（只许 `#[expect(…, reason = "…")]`）、`allow_attributes_without_reason`、`clone_on_ref_ptr`、`implicit_clone`；`pedantic` 整组 warn，CI 里 `-D warnings`。
  - **每个 crate 都写 `[lints] workspace = true`**，否则 workspace 的表不生效。
- 测试代码的放行只经 `clippy.toml` 的测试放行键（以钉的 clippy 版本支持的为准，§10.2 #13）和 `#[cfg(test)]` 模块；`#[expect]` 只许加在条目上、带 reason。
- **lint 阳性对照**：CI 里建一个临时 crate（不进 workspace，继承同一张 lints 表），分别写 `unwrap()`、`expect()`、`v[0]`、`&s[..1]`、`x as u8`、`unsafe {}`、`#[allow(…)]`，每个都必须让 clippy 失败。
- **计数棘轮放在 infra 的 code-health**：`scan.sh` 认 `.rs`（今天不认，`infra` `agent-config/scripts/code-health/scan.sh:256-264`），加：单文件行数、`#[expect` 个数、`.clone()` 个数、`unsafe` 个数、`pub` 项个数、直接依赖数、
  每个 crate 有 `[lints] workspace = true`、deny 清单齐全、`flex-domain` 无 I/O 依赖、`tests/char-db.manifest` 条数。基线在 infra 的 `baselines.env`：插件仓库里的改动改不动它。
- **基线怎么起**（复核 B1：从零骨架起「只减不增」与正常实现增长不相容）：切片 3（骨架）定初值；切片 4–7 每个切片收尾可抬一次，是 infra 的单独提交、写理由、由另一家复核（「受审扩容」）；切片 7 完成后只减不增。
  生产代码的 `unsafe`、`unwrap`、`expect`、`panic` 从第一天就是 0（deny）。
- **sqlx 离线**：`.sqlx/` 由 `rust/schema/flex_tables.sql` 生成（只有 DDL、没有数据，从 core DDL 和插件 DDL 摘出，版本化）。CI 起 sidecar 载入这个 schema，跑 `cargo sqlx prepare --check --workspace`，不一致就红；不只靠 `SQLX_OFFLINE=true`。schema 文件与生产是否一致，由 §2.2 的每日指纹在集群里核对。
- `cargo fmt --check`；`cargo deny`（许可证、通告、重复依赖；要联网，只在 CI 跑）；`rust-toolchain.toml` 钉确切版本；`Cargo.lock` 入库，全部命令 `--locked`。

### 3.5 测试

- 单元：`flex-domain` 全部是纯函数，§1.7 每条怪癖至少一条测试。
- A 层对照：`cargo test` 读 `tests/characterization` 同一批夹具、golden 和合成案例（`case.v1`）。
- 库测试：agentd 给的 `AGENTRT_TEST_PG` 是 libpq 键值串（`host=<目录> port=5432 user=<u> sslmode=disable`，`platform` `api/internal/agentd/testdb.go:243-248`），sqlx 只认 URL：写一个小适配函数解析成 `PgConnectOptions`（socket 目录），带单元测试。
  CI 的 sidecar 用同一变量名。变量缺失时库测试**失败**，打印执行条数。
- HTTP 级测试（真起 axum、真用 reqwest 打假 IB）只在 CI 跑（沙箱无回环）。
- **混合版本测试**（CI，复核 A7）：同一个临时库，Python API + Rust worker、Rust API + Python worker：入队去重、认领、run-now、config/write 后 summary、两边的幂等 DDL 先后各跑一遍、心跳写同一行、手动 trigger 落 job 行。
- B 层与并跑：重放 Deployment 的 Rust 引擎（§4.1）。

---

## 四、并跑

### 4.1 重放 Deployment 与隔离模板（D-R2；复核 B3）

- `flex-replay` Deployment，清单在插件 `k8s/replay/`（单独的 kustomization，不在 `k8s/base`）。三个容器：
  - `py-engine`：生产 Python 镜像（digest）+ 私有模式；
  - `rs-engine`：重放镜像（digest），切片 8 起加入；
  - `pg`：Postgres 17（先镜像进集群 registry，钉 digest），数据 `emptyDir{medium: Memory}`。每个案例两个新库 `py_<n>`、`rs_<n>`，用完即删。
- 卷：同一个 PVC 挂两次——`subPath: cases` **只读**；`subPath: verdicts` 可写（verdict、台账、`private/`）。录制只写 `cases/`，重放从不写它（复核 B3 指出上一版要把 verdict 写回只读卷）。
- **隔离模板**（Python 引擎、Rust 引擎、切换后的反向 Python、修复工具的 dry-run 都用这一份）：
  - 标签 `app.kubernetes.io/part-of: bifrost-flex-replay`，不命中 `flex-query-egress`（它选 `part-of: bifrost-flex-query`，放行 data 命名空间全部端口和任意 443，插件 `k8s/base/network-policy.yaml:11-30`）。
    kustomize 的公共标签是 `includeSelectors: false`（插件 `k8s/base/kustomization.yaml:18-23`），不改模板标签——以渲染结果为准，有测试。
  - 自己的 NetworkPolicy：选中 `part-of: bifrost-flex-replay`，`policyTypes: [Egress]`，`egress: []`（连 DNS 都不放）；入站只放 Prometheus 到 metrics 端口。
  - 无 `envFrom`、无 Secret 引用，不挂 `flex-query-config`（它会给出 GS 主机；Python 的 `postgres_connect_kwargs` 缺配置时落到 localhost，`fq/config.py:74-90`，正好指向 sidecar，但仍显式写 sidecar 地址）；
    `automountServiceAccountToken: false`；只用 `default` SA。
  - 引擎里 IB 只有「录制 transport」，Redis 只有内存 sink；缺一个录到的事件就判这个案例失败，不回落到真实网络。Python 引擎把 `urlopen` 和 redis 换成抛错的桩；`flex-replay` 不编进 reqwest 和 redis。
- **渲染清单测试**（CI，`kustomize build k8s/replay`）：逐条断言上面每一项；镜像都是 digest；没有 hostPath。
- `apply_manifest` 的策略已允许 PVC、Job、NetworkPolicy、Deployment 进 `plugin-flex-query`（C 级，`infra` `k8s/cicd/tekton/apply-manifest/actuation-policy.yaml:29-31,41,48-78,124-140`）——仓库配置支持，在线权限和准入策略的要求未验证（§10.2 #6）。

| 选项（D-R2） | 做法 | 评价 |
|---|---|---|
| **A（推荐）** | 上述重放 Deployment | 生产表结构上碰不到；零 DDL；输入完全相同所以结果可比 |
| B | GS 里建 `raw_broker_shadow`，Rust 每天真写，SQL `EXCEPT` 对比 | PROD DDL、授权改动；佣金表有 TWS/网关在写，对比噪声大；账户数据多一份 |
| C | 另建库 `bifrost_flex_shadow` | 隔离最好，搭建最重 |

### 4.2 对账台账（复核 A6）

全部在卷上离线算，不连 GS。

- **分母 1，计划槽**：`schedule.yaml` 的两个槽（周一到周六 06:30 America/New_York）× 日期。
- **分母 2，尝试**：每个案例里有录到的作业行（`attempts`、`max_attempts`、`created_at`、payload 的 `as_of`、`catchup`）。同一作业录到的尝试数少于最终作业行的 `attempts` → 漏录；计划槽没有任何作业 → 漏录或未跑。
- `started/` 有、`cases/` 无 → 不完整。
- **分子**：每个案例在当前候选身份下的 verdict。
- **交易日**：NYSE 交易日历（公开数据，入库在 `flex-domain`，覆盖 2026–2027，有测试断言覆盖并跑期）。一次运行的「被验证交易日」= 运行当地日期之前最近的一个交易日。
  周二到周六的运行对应周一到周五；周一的运行对应上周五（已由周六的运行计过）：它照样要一致（不一致照样清零），但不新增天数；节假日后的运行同理。
- 每个（交易日，作业类）的状态：一致 / 不一致 / 漏录 / 不完整 / 未重放 / 不可判等 / 待定（作业还 pending 或 running）/ 无有效入库（作业最终 failed）。
- **一个交易日计 1 天，当且仅当**：该日两类作业都 done；它们的所有尝试都录全、都有效、都一致。
- 日报：每天 12:00 ET 出一次（只是出报告的时点）；没结束的显示「待定」，之后补判。只出计数、日期、状态、作业号、候选身份。
- 输出位置：`verdicts/ledger.json`（计数）和重放 Pod 的 `/metrics`（`bifrost_flex_replay_cases_total{engine,result}`、`bifrost_flex_replay_days_counted`、`bifrost_flex_replay_mismatch_rows{table}`）。Agent 只看这些。

### 4.3 计数、通过、停（D-R8）

- **候选身份** = `rust/crates/flex-domain`、`rust/crates/flex-query`、`rust/Cargo.lock`、`rust/rust-toolchain.toml` 的 git tree 哈希。每条 verdict 记候选身份和重放镜像 digest。
  切换时部署的生产镜像必须由同一候选身份的提交构建，切换单写明两者（复核 A6：不能中途换版沿用旧成绩）。
- 只改 `flex-replay`（比较器、台账）不改候选身份：用新重放镜像把已计数的日子全部重放一遍，仍全部一致才继续计数；否则按框架错误处理。
- **通过**：同一候选身份下，至少 **10 个计数的交易日**；期间没有「不一致」；并且见过一次 not_ready 重试、一次 cash 有行、一次含期权成交、一次跨月窗口。
  类型覆盖可以用历史案例补（同一候选身份重放，报告写明）；**天数不能用历史案例补**。
- **清零**：任一「不一致」→ 修 Rust → 新候选身份 → 从 0 数。
- **不计也不清零**：漏录、不完整、不可判等、无有效入库的日子。连续 3 个交易日拿不到计数 → 停下查。
- **停**：录制让作业变慢（作业时长中位数比录制前高 50% 以上，或任一作业因录制失败）→ 关录制；卷剩余低于 1 GiB；NAS 故障让 worker 起不来 → 关录制（去掉 capture 组件再 apply，§六）；
  同一类不一致三次修不好 → 回到设计；Owner 的业务插队 → 暂停（并跑只花墙钟，不花额度）。
- **不调 IB**：并跑期间 Rust 一次都不打 IB（D-R5）。IB 客户端靠录到的协议回包和 HTTP 级测试证明；首个真实调用是切换后的第一个 06:30。

---

## 五、切换、回滚、退役（复核 A7 重写）

### 5.1 前提

A 层全绿（Python、Rust、混合版本）；B 层全部历史案例 Rust 一致；并跑通过（§4.3）；回滚演练做过（§5.5）；Owner 批切换单。

### 5.2 停领活与排空

1. 时点：周六两类作业都 done 之后。周日 Dagster 不触发；worker 的补跑只追 24 小时内的计划槽，周六的槽已有作业。
2. 查 `/flex/ingest/queue-summary`：pending=0、running=0。
3. `scale_deployment flex-query-worker` 到 0（随切换单批）。Pod 消失后再查一次 running=0。若有 running（刚好被领走）：扩回 1，等它结束，回到 2。
   （直接杀掉正在跑的作业不丢数据——业务写是 upsert——但它会停在 running 7200 秒，所以宁可等。）
4. API 不停。手动 `trigger`/`upload-xml` 在 API 滚动期间可能落到任一版本上；两版对这两条路由的行为由 A 层和混合版本测试钉住。

### 5.3 切换

- 一个提交只改 `k8s/base`：两个 Deployment 的 image（**digest**）、command/args（`flex-query api` / `flex-query worker`），以及 worker 上的 capture 组件（Rust 版同格式录制，切换前就做进去）。经 `apply_manifest`（C）。
- worker：Recreate（插件 `k8s/base/deployment-worker.yaml:10-11`），apply 后回到 replicas 1。
- API：保持 RollingUpdate（maxSurge 1、maxUnavailable 0，`deployment-api.yaml:13-17`）——不重新引入 Trade 网关的 503 空窗；代价是约 1 分钟的混合版本，已由 §3.5 测过。
- 核对：心跳 `version` 是 1.x、API `/health`、Console 插件页、ConfigMap 与 Secret 引用未变。第一次 Rust 实跑是周一 06:30 ET。

### 5.4 观察 5 个交易日

每天看 freshness、行数、告警。重放 Deployment 反过来：Python 引擎重放 Rust 的案例，Python 的重放必须等于 Rust 的生产写后状态；不等即疑似错误写入，走 §5.6。

### 5.5 进程回滚

- 回滚 = `git revert <切换提交>`，再 `apply_manifest`；之前同样先停领活排空（§5.2）。revert 一次恢复 Python 的 image digest、command/args 和录制配置。
  只换 tag 不行：Rust 的 args 在 Python 镜像里起不来（Python 镜像默认 CMD 是 worker，插件 `Dockerfile:26-27`）。
- **演练**（切换前做一次）：取切换前后两份 `kustomize build` 的 worker、api Pod 模板，套隔离模板，用临时库、假 IB 各起一次：能起、`/health` 通、能入队并领一个作业。按 Python → Rust → Python 走一遍。
- 镜像保留：清单用 digest；Python 镜像 digest 在 registry 保留到退役后 30 天（registry 保留策略待核实，§10.2 #5）。

### 5.6 错误写入修复（与进程回滚分开；D-R11）

「不改表结构」不等于「回滚不涉及数据」。Rust 一旦写错：

- 会自愈的：`executions_raw_flex` 在窗口内的 54 列——回滚后 Python 下一次运行全列覆盖。
- 不会自愈的：错插的新行；被改的主键或 `created_at`（规则禁止，但要防）；窗口外的行；佣金（COALESCE 会留住错的非空值，`commissions.py:108-113`）；现金的 COALESCE 列（`accounts.py:1162-1180`）。
- 发现：反向重放（§5.4）每天发现，错误最多活 1 天。
- 修：`flex-replay repair --case <id>`，私有模式的 Job，用 `flex_writer`；C 级、每次 Owner 批（PROD 数据写）。先 dry-run，只出计数。
  对每个受影响的键：现值仍等于 Rust 当时的写后状态（之后没人动过）→ 改成 Python 重放的写后状态；现值已被别人改过（Ledger、TWS）→ 不动，列给 Owner。
- 交 Owner 的条件：错行涉及 Ledger 改过的行；或错误超过 1 天才发现；或 dry-run 计数超过 50 行。此时停自动修复，由 Owner 决定（含从 CNPG 备份按行取回）。
- 证据保留：Rust 时期的案例（含写前状态）保留到退役后 30 天，与 Python 镜像保留期一致。

### 5.7 退役（观察期过后）

删 `src/`、`pyproject.toml`、Python Dockerfile、Python 录制器、`k8s/replay/`、capture 组件、录制卷；README/CLAUDE.md 改写；台账记数字；关掉「Python 生产日志带账户内容」的 TD（§2.6）。
core 里只给 Flex 用的写库分支（`upsert_account_transactions` 只有本插件在调；`write_account_executions_to_db` 的 flex 分支）留给 core 自己的改动（改公开接口，另批）。

---

## 六、构建、CI、部署（复核 A9、B4）

- **镜像**：多阶段 `rust/Dockerfile`：builder `rust:<钉死版本>-slim-bookworm`（先镜像进集群 registry），`SQLX_OFFLINE=true`；运行层 `debian:bookworm-slim` + ca-certificates（要能 `kubectl exec` 排查，不用 distroless）。
  `/config/schedule.yaml` 照旧烤进去（Q6）。镜像名不变 `bifrost-flex-query`，Rust 用 `1.x`（并跑期 `1.0.0-rc.N`）；重放镜像 `bifrost-flex-replay`。清单一律写 digest。
- **构建流水线** `bifrost-build-flex-query`（名字不变，发布窗口映射不用改：`platform` `api/internal/delivery/release_window.go:21-27`、`infra` `k8s/cicd/tekton/task-release-window.yaml:39-44`）：
  - 加参数 `coreRevision`。今天插件和 core 用同一个 `revision` 克隆（插件 `k8s/cicd/pipeline-build.yaml:37-64`），填插件 SHA 时 core 克隆会失败，所以只能用 `main`——core 跟着 main 漂。
    改后：`revision` = 插件确切 SHA，`coreRevision` = `ci/core-pin` 的 SHA。
  - 加参数 `variant=python|rust|replay`；rust、replay 不克隆 core。冻结检查、发布窗口照旧在最前。产出的 digest 记进发布记录。
- **core 钉版本**（复核 B4）：插件仓库 `ci/core-pin` 一行 SHA。CI、构建、Python B 层、Agent 的兄弟检出都用它。Agent 的兄弟只能跟分支头（`platform` `api/internal/agentd/setup.go:49-74`），
  所以在 core 建分支 `pin/bi2-flex` 指向同一 SHA；检查第一步比对 `git -C ../bifrost-trade-core rev-parse HEAD` 与 `ci/core-pin`，不等就失败。挪钉子是单独提交、另一家复核；挪完重跑 A 层，B 层有效率从新案例重新算。
  不再拿「core 版本号下限测试」当血缘证明（它只证明兼容要求）。
- **CI**：
  - 新流水线 `bifrost-ci-flex-query`，**一条流水线管这个仓库的全部检查**：Python ruff、pytest、`make test-char-db`（PG sidecar）、金丝雀、渲染清单测试、混合版本测试；切片 3 起加 Rust：fmt、clippy、test、sqlx check、lint 阳性对照、`cargo deny`；
    以及 infra 的 code-health `scan.sh`（只扫本仓库）。参数 `repo`、`revision`、`coreRevision`、`infraRevision`。切片 1 就建（只有 Python 部分），早于录制器上线。
  - `infra` `k8s/cicd/tekton/trigger-trade-ci.yaml` 加一个 trigger：`body.repository.name == 'bifrost-platform-plugin-flex-query'`，任意分支推送（写法同 python-ci，`:227-245`）。
  - `infra` `scripts/release/ci_gate.py`：`CI_PIPELINES` 加它（`:20`）；再加「仓库 → 应有的流水线」表，插件只认 `bifrost-ci-flex-query` 的成功。今天 `classify` 见到任一条 CI 流水线对这个 repo@SHA 成功就算过（`:63-77`），若 Python 和 Rust 分两条流水线，Python 绿 Rust 红也会放行。
  - `infra` `scripts/release/push-main.sh`：`GATED` 和 `CI_REPOS` 都加插件（`:113,117`）。
  - 验证（假 CI 结果，进 `scripts/release/test_ci_gate.py` 和 push-main 的测试）：同 SHA 成功 → 过；无记录、失败、别的 SHA 成功、别的流水线成功 → 拒。再用一个超出 Rust 基线的改动证明 code-health 真的跑了、真的红。
  - 依赖缓存 PVC 后置，先量冷构建时长。
- **发布窗口**：照 `release.sh window` / `hold --what bifrost-platform-plugin-flex-query`，一次一个会话。
- **清单布局**：`k8s/base`（生产）、`k8s/components/capture`（给 worker 加卷和开关；关录制 = 去掉这个组件再 apply）、`k8s/replay`（重放 Deployment 和它的策略）、`k8s/cicd`。全部走 `apply_manifest`。
  录制卷：NAS 上的 NFS，RWX（worker 与重放 Pod 可能不在同一节点；local-path 会把 worker 钉在一个节点上），soft 挂载（§10.2 #7）。
- **推 main** 只用 `push-main.sh`。

---

## 七、Agent 怎么做这件活（复核 A8）

- **顺序**（复核 B4）：切片 1–3（Python 框架、录制器、Rust 骨架）由统筹线程派的会话做，以 §六 的 CI 为合入闸门；切片 4 让 agentd 能跑这个仓库；切片 5 起 Rust 主体走 agentd。
  这样仓库条目一次就带上 Rust 检查，不会出现 `Cargo.toml` 还不存在就跑 cargo，也不用发两次平台。
- **平台改动**（一个提交，Go；走一次平台 PROD 发布单）：
  - `store.Repos` 加 `bifrost-platform-plugin-flex-query`（今天只有 `bifrost-platform`、`bifrost-trade-infra`，`platform` `api/internal/agentrt/store/repos.go:68-95`）：
    - Siblings：`bifrost-trade-core` @ `pin/bi2-flex`。
    - Setup（有网）：Python venv（`.git/venv`，照 infra 条目的 `-I`、`--only-binary`、钉版本写法）装兄弟 core 和 `.[dev]`；`cargo fetch --locked --manifest-path rust/Cargo.toml`；
      `cargo build --locked --manifest-path rust/Cargo.toml --workspace --all-targets`（预编译依赖，Verify 只增量）。
    - Verify（无网，从仓库根执行）：core 钉子核对；`rustc --version`、`cargo clippy --version` 等于钉的版本；`ruff check`；`pytest -m 'not db'`；`make test-char-db`；
      `cargo fmt --manifest-path rust/Cargo.toml --all --check`；`cargo clippy --manifest-path rust/Cargo.toml --workspace --all-targets --locked --offline -- -D warnings`；
      `cargo test --manifest-path rust/Cargo.toml --workspace --locked --offline`（库测试必须跑，打印条数）。棘轮不放这里：在 CI 的 infra code-health，插件改动改不了。
    - `TestDB: true`。
  - agentd：`homePins`（`platform` `api/internal/agentd/confine.go:160-166`）加 `CARGO_HOME=<tmp>/cargo`、`CARGO_TARGET_DIR=<tmp>/cargo-target`，Setup、执行者、确定性检查拿到同一组值。
    不钉的话，Setup 的 HOME 是 `tmp/home`、执行者的 HOME 是 `home`（`confine.go:148-150`，`setup.go:171-177`），依赖装在一处、离线检查去另一处找。执行者环境的允许表（`executors.go:37-40`）和 stage 的无密钥检查要认这两个名字（以实现时读 `attemptEnv`、`stageKeyless` 为准）。
    工具链不用 rustup 代理，所以不需要 `RUSTUP_HOME`。
  - **06 上的 agentd 二进制要换**：TestDB 由主机上 agentd **编译进去的** `store.Repos` 决定（`testdb.go:184-205`）。只发 platform PROD 不会让旧 agentd 为这个仓库起临时库。
    新二进制 = 同一平台提交构建，更新 `infra` `scripts/agent-host/prepare-agent-06.sh:31` 的二进制名和 `agentd.sha256`，由 Owner 在主机上跑。
  - 06 没有测试库程序时 agentd 只记一行、库测试 skip（`testdb.go:219-221`）。本仓库的库测试入口在没有 `AGENTRT_TEST_PG` 时直接失败，所以 skip 会变成红。
- **agent-06 装 Rust**：独立安装包（不是 rustup）解到 `/opt/bifrost/rust/<版本>`（root 所有、只读），校验发布方 SHA-256，加进 agentd 服务的 PATH；照 `prepare-agent-06.sh` 装 Go/Node 的写法。与换 agentd 同一次跑。
  出站 443 已放行（规则只看端口，`agent-egress.nft`）。
- **冷启动验收**（切片 4 的完成条件）：在 06 上开全新尝试（空缓存）：有网 Setup → 无网 Verify，分别在骨架提交和一个功能多的提交上跑，记时长和 `target/` 大小；
  再做三个反例：工具链路径不存在、主机没有测试库程序、删掉一条库测试——三个都必须红。不以「在主机登录 shell 里跑通」代替。
- **两个要量的风险**：
  - 检查限时 900 秒（`repos.go:203-205`）：Setup 预编译后量 Verify；不够就要平台给仓库单独限时（平台改动，另批）。
  - 磁盘：`target/` 在尝试的 tmp 里，随尝试清理；TD-415 的磁盘守卫要算进去。
- **谁写谁审**：Python 对照框架和 Rust 实现分给两家；每个切片的复核由另一家做（作者 Claude → Codex 审，反之亦然）。核心（`flex-domain`、`flex-query` 的 store/worker）由强模型写；外围（Dockerfile、CI 清单）可以外包。
- **额度**：后台道。BI-2 同时最多一个在途尝试；有 Owner 的业务（含 Screening）在排队时不派新切片。并跑阶段只花墙钟。运行时按额度路由（`platform` `api/internal/agentrt/store/claim.go:368`）；按 issue 限并发的开关是否存在未核实。
- **数据纪律**：agent 不读录制卷、不跑带真值的查询；只看计数、列名和格式类别。提交信息、PR、交接文档提交前跑金额/账户 grep。

---

## 八、要记的数字（成功标准 5）

| 类别 | 指标 | 基线 / 来源 |
|---|---|---|
| Agent 来回 | 每个切片的尝试数、退回次数、复核轮数 | agentrt 的 attempt / verification |
| 复核发现 | 每轮 A/B/C 数，按类（unwrap/clone、逻辑、测试缺口、契约漂移、隐私） | 复核报告（本设计第 1 轮：A 9、B 4） |
| 额度 | 每家消耗 | `agentrt.budget_ledger` |
| 上线问题 | 并跑各状态的天数（一致、不一致、漏录、不可判等…）、清零次数、切换后 30 天内的事故/回滚/热修/修复 DML 次数 | 台账、告警 |
| 录制 | 案例有效率、每个作业多出的语句数和毫秒、放弃/未录的案例数 | 录制器计数、作业时长 |
| 代码量 | 生产代码行、测试行、依赖数、`#[expect]` 数、`.clone()` 数、`unsafe` 数 | Python：`src` 5,892 行 + core 的 Flex 写路径约 600 行；测试 3,444 行 / 160 条；4 个直接依赖 + core |
| 资源 | 镜像大小、Pod 内存/CPU 峰值、作业时长、冷构建时长、CI 时长、06 上 Verify 时长与 `target/` 大小 | 7 天每小时采样峰值：API 约 73 MiB、worker 约 42 MiB，CPU < 10 毫核；近 30 天作业 p50 约 1 秒（trades 完成 32、失败 4，transactions 完成 28） |

记在 BI-2 的问题对象里（运行时对象还没上线前，先记 `infra` `agent-config/work/crew/BI-2-metrics.md`，只有计数）。回顾时用这张表决定下一块。

---

## 九、切片（按顺序，重新估）

| # | 切片 | 大小 | 谁 | 要 Owner |
|---|---|---|---|---|
| 0 | 本设计：统筹审 → Codex 独立复核（最多两轮）→ Owner 定 §10 | 半天 + 等 | 统筹 | **定 D-R1…D-R11** |
| 1 | Python A 层：鉴权矩阵、两套回退、Q1–Q24、行案例、生命周期失败注入、`make test-char-db`、夹具守卫、金丝雀框架；`bifrost-ci-flex-query`（Python 部分）+ trigger + `ci_gate` + `push-main` 接入 | L（3–4 天） | 家 X | 批 cicd apply（C） |
| 2 | 录制器 0.14.0（四个接缝、`clock` 模块、事件日志、非阻塞写、私有模式）；capture 组件 + PVC；形状抽取；重放 Deployment（Python 引擎）+ schema 指纹 + 渲染清单测试；框架自证场景；Python 有效率 100% | L（4–5 天） | 家 X | 插件 0.14.0 发布单；apply（C）×2 |
| 3 | Rust 骨架：3 个 crate、lint 与阳性对照、Dockerfile、构建流水线 `variant` 与 `coreRevision`、CI 加 Rust 步骤、sqlx check、infra code-health 认 `.rs` 并定初始基线 | M（2 天） | 家 Y | 批 cicd apply（C） |
| 4 | 平台任务仓库条目 + agentd 钉 `CARGO_*`；06 装 Rust + 换 agentd；冷启动验收（含三个反例） | M（1.5–2 天） | 统筹 + Owner | 平台发布单；**在 06 上跑主机脚本** |
| 5 | `flex-domain`：A 层纯函数全过 | L（4 天） | 家 Y | — |
| 6 | `flex-query`：IB、store、worker 生命周期与失败注入、录制器；A 层库测试全过 | L（4–5 天） | 家 Y | — |
| 7 | API 全部路由、鉴权矩阵、指标；混合版本测试；`flex-replay` Rust 引擎 | M（2 天） | 家 Y | — |
| 8 | 重放 Deployment 加 Rust 引擎：先重放全部历史案例（B 层），再跟新案例（并跑）；分类一致率在集群里算 | S（半天）+ 墙钟 ≥3 周 | 统筹盯 | apply（C），每换一次候选一次（估 ≤6 次） |
| 9 | 回滚演练 → 停领活排空 → 切换 → 反向重放 → 观察 5 个交易日 | M（1 天）+ 1 周墙钟 | 统筹 | **批切换单**（含 worker 缩到 0） |
| 10 | 退役 Python、录制器、重放、卷；关 TD；回顾 | S | 家 X | apply（C） |

X、Y 是两家不同的执行者。大小：S ≈ 半天，M ≈ 1–2 天，L ≈ 3–5 天 agent 时间。

**合计约 26 个 agent 日（上一版约 17），墙钟约 8 周（上一版 5–7 周）。** 多出来的主要在切片 1、2（契约补全、事务内录制、隐私、框架自证）和切片 4（agentd 与冷启动）。
省下的：5 个 crate 并成 3 个；cargo-chef、CI 缓存 PVC、大范围随机模糊后置；上一版的「B 层 Job」与「影子 Deployment」两个切片并成一个重放 Deployment。

---

## 十、要 Owner 定的；待核实的事实

### 10.1 决定（推荐是第一项）

| 编号 | 问题 | 选项 | 推荐与理由 |
|---|---|---|---|
| **D-R1 架构级** | 引入 Rust 工具链 | A 钉死 stable + crates.io + `Cargo.lock` + `cargo deny`，Setup 里预取；B 再加 `cargo vendor` 把依赖源码入库；C 在集群里建 crates 代理 | **A**。B 让仓库膨胀、复核看不过来；C 是新服务 |
| **D-R2** | 并跑时 Rust 写哪 | A 重放 Deployment（Python、Rust 两个引擎 + 内存盘临时库，重放录制）；B GS 影子 schema（PROD DDL）；C 另建库 | **A**。零 DDL，生产表结构上碰不到，输入完全相同；同一个 Deployment 也是 B 层和反向重放 |
| **D-R3** | 真报表与真行存哪 | A 插件命名空间的 PVC（NAS 上 NFS，RWX，soft 挂载）；B GS 新表 `raw_broker.flex_capture`（新表 + PROD DDL）；C NAS 上的 MinIO（新凭据） | **A**。不出集群、不加表。代价要你知道：**录制期间 worker 的启动依赖 NAS**（NAS 故障时 worker 起不来）；关录制即解除（§4.3「停」）。若想长期留原始报表，选 B，那是另一件事 |
| **D-R4** | 仓库里放什么夹具 | A 按形状合成（白名单结构，不出描述模板）；B 真报表脱敏；C 不放 | **A**。描述字段里有代码和金额，脱敏漏一处就公开；C 让 agent 在 06 上没法跑对照 |
| D-R5 | 切换前 Rust 打不打 IB | A 一次都不打；B 每天在 Python 成功 45 分钟后打一次；C 某个周日人工监督打一次 | **A**。B 每天多一倍请求，1018 按 token 冷却会伤到生产；C 可作补充 |
| **D-R6 架构级** | 库的选择 | A §3.2 推荐列（sqlx 离线）；B 换 tokio-postgres；C 换 quick-xml | **A**。sqlx 把 SQL 也纳入类型检查；`.sqlx/` 由版本化 schema 生成并在 CI 核对 |
| D-R7 | 怪癖与有意差异 | A 切换前严格等价、切换后按正常改动修；B 重写时顺手修 | **A**。有意差异只有两类，都要求**分类相同**：①传输层错误文本（urllib → reqwest）走固定模板；②数据库错误文本，Rust 存「SQLSTATE + 固定模板」，不再把带键和值的 DETAIL 写进 `job.result`、freshness、心跳。生产日志不在契约里（Rust 日志不带值） |
| D-R8 | 并跑中出错怎么数 | A 按候选身份：Rust 的错清零重数；B 不清零只顺延 | **A**。IB、录制原因拿不到计数的日子不计也不清零（§4.3） |
| D-R9 | 仓库形态 | A 同仓库 `rust/`；B 新仓库 | **A**。CI、发布窗口、任务仓库、Console 引用都不用改名 |
| **D-R10 新** | 录制器插在哪 | A 用 core 写明的测试接缝 `write_support.connect`，在插件进程里包一层（不改 core；靠 `ci/core-pin` 钉住 core，挪钉子要重验）；B 给 core 加正式的录制钩子（改 core 公开接口，另批、要发 core）；C 只在事务外录 | **A**。B 更正式但要先动 core；C 已被复核 A4 否定（提交后再查拿不到可靠的前后状态） |
| **D-R11 新** | Rust 写错了怎么修 | A 按案例重放算出 Python 的写后状态，只改「现值仍等于 Rust 写后」的行，先 dry-run，每次你批；B 从 CNPG 备份按时间点取回；C 只回滚进程、靠 Python 下一次运行自愈 | **A，B 兜底**。C 修不了佣金、现金的 COALESCE 列和错插的行；B 会连带别的写入者 |

### 10.2 待核实（落地前查清）

1. GS 的会话时区（API 时间偏移）和 pod 本地时区（`date.today()`；镜像与 Deployment 都没设 TZ）。
2. 部分唯一索引 `transactions_account_flex_tx_uidx` 在 GS 上是否存在、谓词是什么（core 的 DDL 里没找到建它的语句，复核也没找到）——由 §2.2 的 schema 指纹回答，并据此写 sidecar 的建表脚本。
3. 三张表还有没有别的写者（已查 core、research、trade-api、trade-worker、platform 的当前提交，没有找到 §1.1 之外的）。
4. `flex_writer` 能否读两个序列（`pg_sequence_last_value` 要 USAGE 或 SELECT）。不能则新行主键退为「唯一、大于写前最大值、两引擎相等」，并请你批一个 SELECT 授权（role-matrix 改动，另批）。
5. registry 的 digest 保留策略，Python 镜像能否留到退役后 30 天。
6. 准入策略对重放 Pod 的要求（sidecar 镜像来源、`emptyDir` 内存盘、SA）；`apply_manifest` 写 PVC、Deployment、NetworkPolicy 的在线权限。
7. NAS 上可用的 NFS StorageClass、能否 soft 挂载、容量。
8. 集群里的 `bifrost-build-flex-query` 是否已是仓库版本（`infra` `docs/RELEASE.md:382-386` 说当时还没 apply）。
9. TD-266（worker 的消息中心）0.13.2 之后的实际行为。
10. 06 上 Setup 预编译后 Verify 的时长、单次尝试 `target/` 的大小（切片 4 量）。
11. 运行时有没有按 issue 限并发的手段。
12. 本机 `bifrost-trade-core` 检出不是 main；发 0.14.0 前用 `ci/core-pin` 的 SHA 构建（插件 `Makefile` 的 `CORE_DIR` 指向干净检出）。
13. Rust 钉哪个 stable 版本、YAML 选哪个维护中的 crate、`clippy.toml` 支持哪些测试放行键。
14. core 仓库能否推 `pin/bi2-flex` 分支（分支保护）；agentd 的兄弟克隆能否跟这个分支。

### 10.3 Owner 要动手的

1. 定 D-R1…D-R11（新增 D-R10、D-R11；D-R2、D-R3、D-R7、D-R8 的内容有细化）。
2. Console 批 C 级：cicd 流水线 apply（切片 1、3）；录制卷与重放 Deployment apply（切片 2）；重放候选更新（切片 8，估 ≤6 次）；退役 apply。
3. 发布单：插件 0.14.0（录制器）；平台 PROD（任务仓库条目 + agentd 的 `CARGO_*`）。
4. 在 agent-06 上跑一次主机脚本：装 Rust 工具链 + 换 agentd 二进制（同一次）。
5. 切换单（含把 worker 缩到 0 的排空步骤）。
6. 若出现错误写入：每次修复 DML 批一次（D-R11）。

---

## 十一、风险、刻意不做、留下的样板

### 11.1 风险与对策

| 风险 | 对策 |
|---|---|
| Python 浮点 repr、`float()`/`int()`/`isdigit()` 接受集、ElementTree 细节、时区造成细微差异 | Q1–Q24 逐条钉；固定向量 + 有种子的性质测试；形状抽取先告诉我们真数据里有什么 |
| 写库逻辑一份在 core、一份在 Rust，过渡期 core 改了 Flex 写法 | `ci/core-pin` 钉住 core；挪钉子是受审提交，挪后重跑 A 层、B 层有效率从新案例重算 |
| 录制器拖慢或弄坏生产作业 | 开关；后台线程、有上限的队列、30 秒放弃；不加锁；看作业时长；停的条件见 §4.3 |
| 录制让 worker 的启动依赖 NAS | 写进 D-R3 让你知道；soft 挂载；capture 是单独组件，关录制即解除 |
| 录得不对，把录制问题当成 Rust 的错（或反过来） | 每个案例先过「Python 重放 = 生产」；不可判等单独计数；框架自证场景 |
| 真数据泄露到仓库、日志、产物、Agent 上下文 | §2.6：私有模式、不出键哈希、泄露金丝雀（CI + 集群启动时）、夹具守卫、提交前 grep |
| Agent 写的 Rust 债（unwrap、clone、as、巨函数），或改掉检查让错的代码过 | deny lint + 阳性对照；棘轮和基线在 infra，插件改动改不了；CI 一条流水线管全部；库测试条数只增不减 |
| 检查超时、磁盘 | Setup 预编译；切片 4 量；TD-415 磁盘守卫 |
| 切换时两个 worker 同时领活，或手动写入撞上混合版本 | 先缩到 0 排空；worker Recreate、`SKIP LOCKED`；API 混合版本有测试 |
| 写错的数据回滚后还在 | §5.6：反向重放每天发现；按案例修，每次你批 |
| 后台道拖太久 | 并跑只花墙钟；每个切片完成写交接记录 |

### 11.2 刻意不做

需求说明列的全部：Research 分析与调度、包工队控制面（Go；本块只改它的仓库条目和 agentd 环境钉，属接线）、前端、IB Gateway 插件、market-data 插件、任何交易动作（D10）。
另外：不加业务能力；不改调度（不加 CronJob，Dagster 照旧）；不修怪癖（切换后再说）；不动 core 的 Flex 写路径（另批）；不移植死代码；不改 Console；
不录 API 的手动 trigger/upload（§2.2）；不改 Python 版的生产日志（记 TD，退役时关）。D13：Rust 版和现在一样只写 `raw_broker.*` 与本插件的 `ops_jobs.*`。

### 11.3 留给下一块的样板

1. **录制器**：在旧服务里加一个只记不改的开关；接缝放在写事务里面（写前、语句、写后都在同一事务），读、外部回包、时钟、生命周期都成事件；原子完成标记；不拖住生产。
2. **形状合成夹具**：白名单结构，不出值、不出模板；生成一眼假的数据；旧版算预期；golden 记血缘、不自动重生成；夹具守卫。
3. **对照框架**：A 层（公开）+ B 层（私有）；B 层先用「旧版重放 = 生产」判案例有效，再用「新版重放 = 旧版重放」判等；框架自证场景。
4. **隐私**：私有模式、`Private<T>`、不出键哈希、泄露金丝雀。
5. **Rust 工作区模板**：crate 分层（纯域 / 带 I/O 的服务 / 重放）、lint 表与阳性对照、infra 里的棘轮与受审扩容、`rust-toolchain.toml`、sqlx 离线与 schema 核对、Dockerfile、一条 CI 流水线、合入闸门接线。
6. **任务仓库条目模板**：Setup 预取并预编译进尝试目录、Verify 固定命令（带 `--manifest-path`）、TestDB、agentd 环境钉、冷启动验收与反例。
7. **按交易日对账的并跑**：计划槽 → 尝试 → 案例 → verdict；候选身份；不计 / 清零的规则。
8. **停领活排空的切换**；回滚 = revert 提交；错误写入修复与进程回退分开。
9. **数字台账**：同一张表，回顾时比各块。

---

## 十二、本版改了什么（对复核 517 第 1 轮）

| 复核 | 改动 | 位置 |
|---|---|---|
| A1 | 鉴权改成两条规则和按路由的矩阵；`config/write` 在令牌为空时只认网关头 | §1.6、Q7、§2.5 |
| A2 | 回退拆成 trades、cash 两套状态机，写明请求次数；cash 无 `p=5`、空成功不回退、多分段不回退 | §1.3 |
| A3 | 新增 §2.6 隐私边界：私有模式、PG 日志压到 panic、不出键哈希、真实错误文本只在集群里比分类、形状抽取只出白名单结构、泄露金丝雀；D-R7 把数据库错误文本列为有意差异 | §2.2、§2.3、§2.4、§2.6、D-R7 |
| A4 | 录制接缝进写事务（core 的 `connect` 接缝）；生命周期按 L1–L13 切步，含其他 pending 行、各步失败；判等改为「Python 重放 = 生产（判有效）」+「Rust 重放 = Python 重放（判等）」；框架自证场景 | §1.5、§2.2、§2.4、§2.5、D-R10 |
| A5 | 已有行的主键、`created_at`、不写的列不能变；新行主键用录到的序列值精确比；多重集合保留重复；补行案例 | §1.4、§2.4、§2.5 |
| A6 | 回到需求的「10 个交易日」：NYSE 日历、被验证交易日的映射、计划槽到 verdict 的对账、八种状态、候选身份绑定、历史案例只补类型不补天数 | §4.2、§4.3 |
| A7 | 停领活排空；切换改 digest + args；回滚 = revert；API 保持滚动并做混合版本测试；回滚演练；错误写入修复单列（D-R11） | §5、§3.5、D-R11 |
| A8 | 平台条目 + 06 上换 agentd 二进制；`CARGO_HOME`/`CARGO_TARGET_DIR` 钉进 homePins；`--manifest-path`；缺库失败；冷启动验收含三个反例 | §七、§3.5 |
| A9 | 一条 `bifrost-ci-flex-query`；trigger、`ci_gate`（含「仓库 → 流水线」表）、`push-main` 的 `CI_REPOS`/`GATED`；假 CI 结果测试 | §六 |
| B1 | 库测试单独目标、缺库失败、条数棘轮；`AGENTRT_TEST_PG` 适配；每 crate 继承 lints；阳性对照；棘轮挪到 infra、受审扩容；`.sqlx/` 从版本化 schema 生成并核对 | §2.5、§3.4、§3.5 |
| B2 | 怪癖从 10 条扩到 24 条（Q11–Q24） | §1.7 |
| B3 | 卷分只读 `cases`、可写 `verdicts`；schema 指纹由录制侧出、重放侧离线比；所有碰真值的 Pod 共用隔离模板；渲染清单测试；非阻塞写、soft 挂载、RWX；actuation 策略改记为「仓库配置支持、在线未验证」 | §2.2、§4.1、§六 |
| B4 | `ci/core-pin` + `coreRevision`；golden 不自动重生成；最小 Python CI 提前到切片 1；crate 5→3，cargo-chef、CI 缓存、大范围模糊后置；切片重排（agentd 在 Rust 骨架之后） | §2.3、§3.1、§六、§七、§九 |
| 自查补充 | ①verdict 里「键的哈希」可被穷举还原账户号，改为案例内序号；②`ci_gate` 见到任一流水线成功就放行，两条流水线会让 Python 绿 Rust 红过关，所以一条流水线 + 仓库到流水线的表；③录制卷让 worker 启动依赖 NAS，写进 D-R3；④API 的手动写入不录，写明理由 | §2.6、§六、D-R3、§2.2 |

**推荐与 Owner 决定**：D-R1…D-R9 的推荐都没有翻；D-R2、D-R3、D-R7、D-R8 的内容细化；新增 D-R10、D-R11。验收口径从上一版自己改的「10 个运行日」回到需求说明的「10 个交易日」。

**大小**：约 17 → 约 26 个 agent 日；墙钟 5–7 周 → 约 8 周。
