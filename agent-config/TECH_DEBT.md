# Bifrost 技术债（未结）

> **这份文件只放没还完的债。** 历史在 git 里，这里不留。审计扫出来的、日常工作里撞上的，都直接在这里加一条，编号接着当前最大号往下排。每条必须有证据（`文件:行`）、修法和防线。条目正文保留英文，标识符照抄。
>
> **每一项怎么走（Owner 2026-10-06）**
> 1. **状态**只有五种：`未开始` → `在做` → `观察中（到 MM-DD，看什么）` → `待你签收`；签收后删掉这一项。
> 2. **验收**：每项写一条验收命令和预期结果。进 `待你签收` 之前必须重跑它，把 `验收结果：PASS|FAIL 日期 提交号` 写回这一项。没有新的 PASS，不能进 `待你签收`。
> 3. **待你签收**：进这个状态时，在下面「待你签收」一节加一行：改了什么、验收结果、加了哪条防线（`RATCHETS.md`）、**后续**（引出的新编号，或「无后续：理由」）。Owner 回复「签收 TD-n」或「打回 TD-n：原因」。
> 4. **签收后**：删掉这一项和「待你签收」里那一行；「还债顺序」里把编号移到「已还」，计划进度一直看得见。提交信息写签收、防线和后续。打回的，状态回到 `在做`，原因写进 `下一步`。
> 5. **自上次以来**：下面「上次查看」记着 Owner 上次看过的提交。台账页从那个提交起生成变化清单（新增、关闭、状态变化、防线增减）。Owner 说「看过了」，就把它改成当前提交。

上次查看：4b4c957（2026-10-06，Owner 说「看过了」）

## 待你签收

（暂无）

**未结 66 项**：P0 0 · P1 5 · P2 30 · P3 31；要你批的 34 项（从总览表的审批列算）。

## 主题（第 2 轮）

- **Green while wrong: jobs succeed on zero, partial or garbage output** — The dominant round-2 class. Engines, gates, ingest handlers and writers convert failures into success: empty lists read as answers, exceptions become 0 or 'unknown', truncation is a field nobody checks, freshness bumps on zero-row jobs. Dagster and Flex show green; only manual metadata reading finds it. Fix pattern: raise or record reasons, and add output checks per asset. (TD-91, TD-92, TD-93, TD-94, TD-97, TD-100, TD-101, TD-106, TD-113, TD-116)
- **Session and calendar truth comes from the wall clock on UTC pods** — Session dates are derived from current_date/date.today() on UTC hosts at 02:30 UTC, producing next-day and Saturday stamps (SEPA, option_universe), a day-late alert judge, and a calendar that silently forgets holidays on a failed read. One session_today() helper plus a nightly session-date sweep closes the class. (TD-87, TD-98, TD-93, TD-97, TD-111)
- **Broker money ledger integrity (Flex / IB)** — The cash and commission ledgers have a 5-month hole the fixed window cannot refill, a writer that reports failure as success, a dedupe key that ignores IB's own id, mixed commission signs, DEV-routed reads and no tests on the money path; the gateway health signal is permanently false-red. (TD-91, TD-103, TD-114, TD-115, TD-116, TD-117, TD-104, TD-122)
- **Gates that do not gate** — CI runs after delivery and never blocks it (research and Trade); plugins and infra have code-health baselines but no CI; preflight D10 matching misses non-curl clients and in-place edits; operator streams use a denylist; no alert watches Dagster schedules or research/plugin 5xx. Making CI gate release is the single highest-leverage ratchet. (TD-95, TD-96, TD-105, TD-99, TD-109)
- **Hand-kept copies and dead config drift** — Schedule rosters, max-pain/PCR math, Black-Scholes and risk-free readers, declared indexes, spine copies, instance configs and suspended CronJobs exist in several places that have drifted from the source of truth. Generate from one source or delete; ratchet with manifest and catalog checks. (TD-108, TD-102, TD-110, TD-107, TD-112, TD-118, TD-119, TD-120, TD-121, TD-123, TD-124, TD-125)

## 先看这几条

- **TD-87** — SEPA 全部晚一个交易日、周五落到周六。代码已修（research 0.180.0）；历史 101,673 行要在 10-07 02:30 UTC 批处理前由 Owner 跑 restate，命令在备份目录 README。
- **TD-91** — 现金流水写库失败被记成「成功、0 行」。TD-88 刚补完五个月的洞，这个写入方再静默失败一次，新的覆盖告警要到月底才响。
- **TD-92** — Research 的引擎资产永远是绿的：按标的失败、0 行写入、跳过都只进元数据。TD-89 停了三天没人发现就是这一类。
- **TD-95** — 没有任何发布等 CI：research 0.172–0.174 是在 CI 红着的时候发的，trade-api main 从 10-04 起 CI 是红的，三个插件仓库自 09-29 起 32 次提交 0 次 CI。`RATCHETS.md` 里的测试类防线在这之前都只是提醒。
- **TD-96** — preflight 的 D10 闸门只认 curl；修改稿在 `REQUEST-td96-preflight-d10-2026-10-06/`，等 Owner 审。

- **TD-130** — 真正在生产数据层上动手的 Ops 自动修复跑在 Owner 的笔记本上（本机 bdev 的 platform-api），集群里 STG/PROD 那两份在空转；10-05 到 10-06 对备份 MinIO 的重启和补备份都是它做的。

## 还债顺序

### 第 0 波 · 第 1 轮收尾

目标：第 1 轮剩下的三项按已排的日期收掉。TD-85 剩 Golden Source 的 PUBLIC CONNECT；TD-51 等 Loki 闸门后随下一次 Trade 发布；TD-80 C2-b 改号 core 0.49.0 与 TD-51 同发。

项：TD-85, TD-51, TD-80 · 已还：TD-21

### 第 1 波 · 正在出错的数据与「绿着的失败」

目标：先让失败变红。错数据先修数据（TD-87 restate），再把引擎、闸门、写入方从「出错也报成功」改成失败即失败：引擎资产按输出判定、husbandry gate 失败即关、日历读失败报错、写入方失败抛错。不需要 Owner 批的先做。

项：TD-87, TD-91, TD-92, TD-93, TD-94, TD-97, TD-101, TD-136, TD-156, TD-157 · 已还：TD-88, TD-89, TD-90, TD-113

### 第 2 波 · 让闸门真的卡住

目标：一个开关让所有测试类防线生效（CI 卡发布），再补上调度存活告警、D10 闸门的非 curl 写法、operator 流白名单、本机常驻任务和密钥轮换的盲区、spine 副本同步。

项：TD-95, TD-96, TD-99, TD-100, TD-105, TD-109, TD-121, TD-152, TD-153, TD-155

### 第 3 波 · 交易日与日历只有一个来源

目标：所有「今天 / 本 session」都从 `db/calendar` 的一个函数来，代替 11 个私有 helper 和 44 处 `date.today()`；dbt 补 grain 测试；IV / 回测的定价参数统一。

项：TD-98, TD-110, TD-111, TD-112, TD-128, TD-129

### 第 4 波 · 券商资金账本（Flex / IB）

目标：现金与佣金账本可信：按 IB transactionID 去重（改表）、佣金一种符号、资金路径有测试、Flex 不再经 DEV 库读配置、IB Gateway 健康与镜像可追溯。

项：TD-103, TD-104, TD-114, TD-117, TD-122 · 已还：TD-115, TD-116

### 第 5 波 · 副本、死重与清单

目标：删掉没人用的（挂起的 CronJob、退役脚本、无调用路由），手抄的副本改成从一处生成（调度名单、max-pain / PCR），清单的应用顺序与 Argo 归属理顺。

项：TD-102, TD-106, TD-107, TD-108, TD-118, TD-119, TD-120, TD-123, TD-124, TD-125, TD-154 · 已还：TD-126

### 第 6 波 · 备份链与自动修复（10-06 日常发现）

目标：备份 MinIO 已搬到 NAS（infra 1ee0ac2，已接监控 ba03488），把剩下的收尾：自动修复只在 PROD 一处动手、失败记录不再被删、platform 的新检查上线、稳定一周后退役集群里的 MinIO 残留，再处理 WAL 体量和 CNPG 1.30 的备份插件。

项：TD-130, TD-131, TD-132, TD-133, TD-134, TD-135

### 第 7 波 · 数据缺口（10-06 由 Data Gaps 看板并入）

目标：Data Gaps 看板上未结的 15 项并入台账：先把每日快照的写入修对（TD-137）再接读侧和三页，归因行补上价格，Research 侧已就绪的一个版本（0.185.0）发出去，长期限 IV 锥在 10-31 前从 option_daily 回填，其余按 Owner 已定的口径排。

项：TD-137, TD-138, TD-139, TD-140, TD-142, TD-143, TD-144, TD-145, TD-146, TD-148, TD-149, TD-150, TD-151, TD-158, TD-159 · 已还：TD-141, TD-147

## 数据边界（接受并留座）

> 订阅或市场本身没有的数据：接受，页面留座并写明原因；不算债、不编号，订阅或市场变化时重开（§5「缺数据先分原因」）。来自 Data Gaps 看板，10-06 并入。

- **已确认的财报日历（◉）** — 订阅里没有：10-06 `/research/events/calendar?days=60` 8 行，全是 ws:macro 与 ws:corporate，财报 0 行；插件只有 8-K Item 2.02 的过去财报。页面写 estimated · confirmed dates not in the subscription；预计日 expected_next 在跑（NVDA → 2026-11-18，track n=4、中位误差 0 天）。依据：看板 R2.a，10-06 实测。还在写「no earnings date reaches this side」的四处在 TD-150。
- **merger / spinoff 与 IB Flex 公司行为报表** — Owner 2026-09-17 裁定不做，除非重开：vendor 只给 dividend 与 split（抽样 17 名 833 行，0 merger、0 spinoff），能填的只有 Flex 的公司行为报表，没有接。依据：`bifrost-trade-frontend/src/layout/designNotes/portfolio.ts:76`；看板 B4.2-3。
- **CUE 只有调整合约** — CUE 1:30 合股（除权 2026-04-24）后交易所没有挂标准系列，只剩 10-16 到期的 14 个 CUE1 合约（10-05 OI 14 行）：市场本来没有，max pain / ATM IV / GEX / flow / PCR 留空是对的。依据：看板 R10.CUE，10-06 实测。页面上的说明在 TD-150。

## 需要你拍板

### 现金写入失败要改成抛错吗？（改 core 公开接口）

- 推荐：B。core 新增严格版写入函数（失败抛错、返回写入与跳过数），旧函数保留一个版本；Flex 插件改调新函数，解析出行数 > 0 而写入 0 时任务失败。做法同第 1 轮 TD-80 C2-a。
- 选项：A：直接改 `upsert_account_transactions` 的语义并抬高下游下限 · B：新增严格版、旧版留一版 · C：只在插件侧判断（core 不动）
- 项：TD-91

### 让 CI 卡住发布吗？（跨仓库发版）

- 推荐：A。`release.sh stg/prod` 和 deliver-research / build-research-dagster 在该 SHA 的 CI 未成功时拒绝（Owner 可用 `--allow-red <理由>` 放行）；先修好 trade-api main 的红，三个插件仓库补上 CI 触发。
- 选项：A：发布前要求同 SHA 的 CI 成功 · B：deliver 流水线里先跑 lint-test 再构建 · C：维持现状，只在发布后告警
- 项：TD-95

### 三个改表 / 迁移顺序项一起批吗？

- 推荐：一起批，分开执行。TD-103 加 `flex_transaction_id` 列、从 `raw_extra` 回填（169 行都有）、部分唯一索引；TD-107 用 CONCURRENTLY 补建 financials 的索引；TD-119 迁移 Job 拆成单独的 kustomization，先迁移后部署。
- 选项：A：三项都做 · B：只做 TD-103（钱）· C：都推后
- 项：TD-103, TD-107, TD-119

### 安全收口四项

- 推荐：都做。TD-85 收回 Golden Source 上 PUBLIC 的 CONNECT（先给 `market_reader` 等显式授权）；TD-105 operator 流改成显式白名单；TD-121 密钥轮换时重启所有挂这个 Secret 的 research Deployment；TD-96 按修改稿应用。
- 选项：A：四项都做 · B：先做 TD-96、TD-105（D10 相关）· C：只做 TD-96
- 项：TD-85, TD-96, TD-105, TD-121

### 删除两组死重吗？

- 推荐：删。TD-124 39 个永久挂起的 CronJob（25 research + 14 market-data + 1 孤儿）连同 verify 脚本里的检查；TD-125 TIBM 时代的 verify 脚本和已不存在 schema 的 flex_ops SQL。
- 选项：A：两组都删 · B：先删 TD-124 · C：都保留
- 项：TD-124, TD-125

### IB Gateway 的健康与镜像

- 推荐：A。网关健康哈希写 `updated_at`、Trade 的服务行指向 `data/ib-gateway`（TD-104）；镜像改走集群内 Tekton 构建、按 digest 钉版本（TD-122）。
- 选项：A：两项都做 · B：只做 TD-104 · C：维持本机构建
- 项：TD-104, TD-122

### 19 条没人调用的 research 路由

- 推荐：B。先加 Deprecation 头和访问日志观察一个版本，零命中再删（同第 1 轮 TD-40）；Agent / 蒸馏的手动触发改成「启动对应的 Dagster job」。
- 选项：A：直接删 · B：先观察一版再删 · C：保留
- 项：TD-123

### Ops 自动修复只在 PROD 动手吗？失败的备份记录保留吗？

- 推荐：A。PROD 的 platform-workers 作为唯一会动手的 autopilot：先干看一遍它拿到真实检查清单后会触发什么（09-22 那条顾虑），接上并在 PROD 审计日志里确认它在动手，**之后**本机 bdev 的 platform-api 才设 `PLATFORM_ROLE=api`（顺序反了就没有一份在动手）；STG 只观测不动手。修复工具不再删除失败的 Backup 记录，30 天后再清理（这一项不依赖前面的顺序，可以先做）。
- 选项：A：只 PROD 动手 + 保留失败记录 · B：本机先停，其余以后再定 · C：维持现状
- 项：TD-130, TD-131

### 备份链的三项后续

- 推荐：TD-132 现在发布（STG 再 PROD，只带 a332cff 一个提交）；TD-134 调大检查点间隔并开 `wal_compression`（只需 reload，不重启）；TD-135 在把 CNPG 升到 1.30 之前装 cert-manager 并换 Barman Cloud Plugin，单独排期。
- 选项：A：三项都按推荐 · B：先做 TD-132、TD-134 · C：只做 TD-132
- 项：TD-132, TD-134, TD-135

### 快照三列的 PROD DDL 与 core 0.51.0 单独发布

- 推荐：A。等 Code Refactor 那批（core 0.49.0 / 0.50.0 + api 0.10.0）PROD 通过后单独发 core 0.51.0 + infra deaa2ca。DDL 只有三条：`account_nav_daily` ADD COLUMN IF NOT EXISTS `cushion` / `excess_liquidity` / `maint_margin_req`（double precision、可空、无默认、不回填，10-05 起已存的行留 NULL）；无自加项；无不可逆步骤（不要时可 DROP COLUMN）。行为变化：收盘时陈旧的账户当天不写、20:30 的 `all` 补抓，U17113214 不再每天写 NAV。每个环境先跑 db-init 再换镜像，否则 capture 的 INSERT 缺列失败。
- 选项：A：按这三列确认并单独发 · B：并进下一批 Trade 发布一起发 · C：先不发（每晚继续锁进副账户的盘中值，压力历史继续丢）
- 项：TD-137

### 数据缺口的三处设计 / DDL

- 推荐：TD-144 做，评判记在 `candidate_pool.source_ref.persona`（零 DDL，只往后记，不回填）；TD-146 先不建，Agrees with you 列保持灰显并写明原因，等你要开始记手动判词时再按 database-design 出 `journal.*` 新表设计；TD-148 按清单确认：`strategy_plan` 的 source_kind CHECK 先删后加、只放宽（加 `lens`、`backtest_run`），PROD 0 行、无新列、无回填，core 的两处词表同改（改公开接口，core 抬小版本）。
- 选项：A：按推荐 · B：TD-144、TD-146 都出新表设计，TD-148 照做 · C：只做 TD-148，两列都保持灰显
- 项：TD-144, TD-146, TD-148

## 总览

| 编号 | 级别 | 领域 | 标题 | 审批 |
|---|---|---|---|---|
| [TD-85](#td-85) | P1 | trade (round 1) | One database password reaches everything: any DEV pod can write PROD Trade and all of Golden Source | 安全/凭据（要你批） |
| [TD-87](#td-87) | P1 | research-data | SEPA features are stamped with the next calendar day (UTC current_date at 02:30 UTC): every SEPA row is one session late and Friday sessions land on Saturday | 不用批 |
| [TD-91](#td-91) | P1 | flex-ib | A failed cash-transactions write is recorded as a successful run: core returns 0 on any exception and the job counts it as 'ok, 0 rows' | 改公开接口 |
| [TD-51](#td-51) | P2 | trade (round 1) | Query-parameter vocabulary drift for expiry, option side, time ranges and limits; no pagination | 改公开接口 |
| [TD-92](#td-92) | P2 | research-control | Engine assets never fail: per-symbol failures, zero-row writes and skips are only metadata, reasons are discarded, and research_trading_day is green regardless of output | 不用批 |
| [TD-93](#td-93) | P2 | research-data | db/calendar.py turns read failures into wrong answers: a failed holiday read makes holidays sessions, a failed universe read swaps the engine universe for 'whatever OI was ingested' or nothing | 不用批 |
| [TD-94](#td-94) | P2 | research-control | husbandry_gate fails open: a probe exception leaves verdict 'unknown', which passes, and the gate never checks that the doctor's session is the one being closed | 不用批 |
| [TD-95](#td-95) | P2 | research-control | No release path is gated on CI: deliver-research ships SHAs whose CI is red (CI starts 7s after deliver), and release.sh never checks CI for Trade | 跨仓库发版 |
| [TD-96](#td-96) | P2 | agent-governance | preflight.js D10 rule only recognises curl: python requests, wget --post-data and sed -i on the daemon scale-zero patch all pass | 安全/凭据（要你批） |
| [TD-97](#td-97) | P2 | research-data | alert_scan judges each session once, a day late, and never revisits; composite_high has never fired because every >=90 score appeared on a later scan recompute | 不用批 |
| [TD-98](#td-98) | P2 | research-data | 'Today' is resolved by 11 private helpers plus 44 bare date.today() calls on UTC pods; option_universe stamps tomorrow's date | 不用批 |
| [TD-99](#td-99) | P2 | research-control | No scheduler liveness alarm: a stopped, renamed or never-ticking Dagster schedule, or a hung daemon, produces no alert; no PrometheusRule targets research | 不用批 |
| [TD-100](#td-100) | P2 | research-control | Event Radar SEC ingest runs from a Mac tmux loop on the shared checkout; it read .env once and failed 157 ticks over ~35.6h after a password rotation; the cluster event_radar slot never ingests and stays green | 不用批 |
| [TD-101](#td-101) | P2 | market-data | Doctor slot staleness reads a per-kind freshness row that other slots and zero-row jobs also refresh, so a stopped policed slot still reads fresh | 不用批 |
| [TD-102](#td-102) | P2 | market-data | Plugin's deprecated live max-pain and PCR routes duplicate Research and skip the adjusted-contract filter: different strikes on the same day, and trade-api SEPA PCR reads the contaminated one | 改公开接口 |
| [TD-103](#td-103) | P2 | flex-ib | The cash parser never stores IB's transactionID, so dedupe falls back to (account, day, amount, type, report_date) and same-amount items overwrite each other | 改表 |
| [TD-104](#td-104) | P2 | flex-ib | Trade Ops reports all three IB Gateway services 'offline' on PROD: the gateway's health hashes have no updated_at, and the service rows point at retired StatefulSets | 跨仓库发版 |
| [TD-105](#td-105) | P2 | flex-ib | DEV/STG operator streams accept every op except two (a denylist), so any op added later is open to DEV and STG by default | 安全/凭据（要你批） |
| [TD-106](#td-106) | P2 | market-data | Nightly trim (now with W3 archive) runs synchronously behind Dagster's 60s HTTP timeout; retries start overlapping trims and the recorded outcome is the retry's | 跨仓库发版 |
| [TD-107](#td-107) | P2 | market-data | Indexes declared for the six financials entity tables never reach a deployed DB (the migration returns early); live differs from fresh install | 改表 |
| [TD-108](#td-108) | P2 | research-control | Three hand-kept copies of the Dagster schedule roster have drifted; Console looks up a renamed corporate schedule and has no mapping for seven newer slots | 不用批 |
| [TD-109](#td-109) | P2 | ops-platform | PROD platform-api reads a deployed ops-context.yaml copy last synced 2026-08-24: about 33 spine decisions missing (D-Journal-Stores, D-Ops-Split, D-Wave-10..13) | 跨仓库发版 |
| [TD-80](#td-80) | P3 | trade (round 1) | Core facade: an 85-method read/write StatusReader inside 'monitor.reader', alias import paths, verb drift | 改公开接口 |
| [TD-110](#td-110) | P3 | research-data | Stored IV features solve Black-Scholes at r=0 while the backtester uses treasury rates from two separate readers; further BS copies in gex and opex | 不用批 |
| [TD-111](#td-111) | P3 | research-data | dbt: the pass_count range generic test sits in the singular folder (errors when selected, never applied); key intermediates lack grain tests; nothing ties eval_date to the session | 不用批 |
| [TD-112](#td-112) | P3 | research-data | option_surface_iv_daily upserts per (symbol, trade_date, expiry) and never deletes, so expiries a re-walk dropped keep their old smile | 不用批 |
| [TD-114](#td-114) | P3 | flex-ib | raw_broker.commissions mixes two sign conventions: Flex writes cost as negative, the TWS/gateway path writes it as positive | 不用批 |
| [TD-117](#td-117) | P3 | flex-ib | 'Latest Flex date in DB' after an import is one run behind: read through FDW in the same transaction as the pre-import read | 不用批 |
| [TD-118](#td-118) | P3 | market-data | option-refresh re-enumerates names with no listed options every run; its 7-day 'finished' lookback reads a table kept 48h | 不用批 |
| [TD-119](#td-119) | P3 | market-data | Schema-migrate Job and worker Deployments are applied in one `kubectl apply -k` with no ordering; a table-adding release fails the jobs that land in the DDL window | 改表 |
| [TD-120](#td-120) | P3 | research-control | Dagster Deployments are applied by hand outside Argo; a second, unmounted dagster_instance.yaml lacks the run_monitoring that catches zombie runs | 跨仓库发版 |
| [TD-121](#td-121) | P3 | research-control | Research pods read bifrost-research-secrets once at start (optional: true); the OpenAI key rotation helper restarts only research-api | 安全/凭据（要你批） |
| [TD-122](#td-122) | P3 | flex-ib | The IB Gateway image is built on the Mac and imported to nodes with ctr under a reused tag: no registry, no digest, no recorded source SHA | 跨仓库发版 |
| [TD-123](#td-123) | P3 | research-control | About 19 deployed research-api routes have no caller in frontend, platform, trade-api or MCP, including manual POST triggers that run engine code outside Dagster | 改公开接口 |
| [TD-124](#td-124) | P3 | research-control | 39 permanently suspended CronJobs (25 research, 14 market-data, plus an orphan pinned to 0.10.0) are still deployed and re-pinned every release; research ones carry a stale 26-name watchlist and the verify script contradicts the one active CronJob | 删除（要你批） |
| [TD-125](#td-125) | P3 | flex-ib | Retired IB topology still referenced: TIBM-era verify scripts at the top of scripts/, flex_ops compat SQL for a schema that no longer exists | 删除（要你批） |
| [TD-128](#td-128) | P3 | research-data | Pine signal rows mix adjustment bases: nightly runs rewrite only the last ~10 sessions on today's adjusted bars, older rows stay on the basis of their last full rebuild | 不用批 |
| [TD-129](#td-129) | P3 | research-data | The event backtest picks option legs from option_daily only; since mid-August 2026 it keeps ~10 strikes a side, so a target delta silently lands on the nearest strike that is left | 不用批 |
| [TD-130](#td-130) | P1 | ops-control | ops-autopilot acts on the shared cluster's data layer from the Owner's laptop (local bdev platform-api, role all); the in-cluster STG/PROD autopilots idle on an empty checklist, and each of the three keeps its own throttle | 要你批 |
| [TD-131](#td-131) | P2 | ops-control | repair_cnpg_wal_store deletes failed Backup CRs, erasing the record of failed backups | 要你批 |
| [TD-132](#td-132) | P2 | ops-control | bifrost-platform a332cff (checks and WAL repair aware of the NAS MinIO) is on main but not released to STG/PROD | 发布（要你批） |
| [TD-133](#td-133) | P3 | data | Leftovers of the in-cluster MinIO after the move to the NAS (deploy/minio at 0, its PVC/PV, an empty EndpointSlice, the backup-retry CronJob) | 要你批 |
| [TD-134](#td-134) | P2 | data | WAL is ~19.5 GiB/day (4.2 GiB compressed) because checkpoints run every 5 minutes without wal_compression | 要你批 |
| [TD-135](#td-135) | P3 | data | Native barmanObjectStore backups are removed in CloudNativePG 1.30; the Barman Cloud Plugin that replaces them needs cert-manager, which the cluster does not have | 新依赖（要你批） |
| [TD-136](#td-136) | P2 | research-data | GEX writes levels for an expiry whose open interest is all zero: walls and zero_gamma fall on an arbitrary strike, 1,534 rows on 496 names, and terrain and scan copy them | 已批（观察中） |
| [TD-137](#td-137) | P1 | trade-data | The daily snapshot capture locks an account's intraday book into the day (first write wins, no freshness test) and account_nav_daily stores no margin-pressure fields | 改表 + 发布（要你批） |
| [TD-138](#td-138) | P2 | trade-data | The daily position and NAV snapshots have no reader: no trade-api route, no Research or frontend read, and three pages still say the snapshot does not exist | 不用批 |
| [TD-139](#td-139) | P3 | trade-data | Snapshot Greeks carry no quality flag (vendor / degraded / missing): only mark_source and greeks_asof are stored | 不用批 |
| [TD-140](#td-140) | P2 | trade-data | Position attribution rows have no price, intraday or after the close: their only price source is contract_quote_live, which only the frozen daemon writes | 不用批 |
| [TD-142](#td-142) | P2 | research-data | The 90-day IV cone has 31–39 sessions of history and there is no 180-day tenor: ATM IV was stored only to 90 DTE before 2026-08-05 | 要你批 |
| [TD-143](#td-143) | P3 | research-data | Hypotheses never link to trades: linked_opportunity_ids is empty on all 91 rows, and only Research's own create / patch writes it | 不用批 |
| [TD-144](#td-144) | P3 | research-data | Settled candidates are not attributed to the judge (persona) that put them forward, so the Personas bench track-record columns stay grey | 要你批 |
| [TD-145](#td-145) | P3 | research-data | Settled candidates carry no regime label, so the Personas bench 'Best regime' column has nothing to group by | 不用批 |
| [TD-146](#td-146) | P3 | research-data | No store accepts a hand verdict, so the Personas bench 'Agrees with you' column cannot be computed | 要你批 |
| [TD-148](#td-148) | P3 | trade-data | A trade cannot name the lens or backtest run it came from: trade has no such column and strategy_plan.source_kind does not allow lens / backtest_run | 改表（要你批） |
| [TD-149](#td-149) | P2 | market-data | CTVA's adjusted daily bars ignore its 2026-10-01 spin-off, so every return-based feature on CTVA sees an ~84% one-day drop | 不用批 |
| [TD-150](#td-150) | P3 | frontend | Pages report gaps that are not there: 'no earnings date reaches this side', 'carry nothing at all' for names the vendor answered, and no note that CUE lists only adjusted contracts | 不用批 |
| [TD-151](#td-151) | P3 | research-data | The macro calendar is empty: features.macro_event_daily has 0 rows because macro_ingest has no scheduled caller | 不用批 |
| [TD-158](#td-158) | P3 | research-data | Earnings estimates are served one name per request, so no universe-wide page can show an Earn column | 不用批 |
| [TD-159](#td-159) | P3 | market-data | No read says how many standard and adjusted option contracts a name has, so "only adjusted contracts are listed" is inferred in the browser from ticker shapes | 不用批 |
| [TD-152](#td-152) | P2 | ops-platform | promtail drops log lines (ingester_error) around 02:00–03:15 and 22:xx UTC, so every Loki-based release gate can come out INCONCLUSIVE | 不用批 |
| [TD-153](#td-153) | P3 | ops-platform | loki_gate.py only knows the pre-0.10.0 log line ('deprecated query params'); after api 0.10.0 refused callers log 'retired query params' and the gate cannot see them | 不用批 |
| [TD-154](#td-154) | P3 | trade (round 1) | api test_request_bodies asserts on a plain MagicMock that removed facade methods were not called — it can never fail | 不用批 |
| [TD-155](#td-155) | P2 | ops-platform | Pushes to GitHub main do not trigger CI until the Gitea pull mirror syncs, so a commit can be released before its CI ever ran | 跨仓库发版 |
| [TD-156](#td-156) | P2 | research-control | research_signal_hit_schedule fires at 00:10 UTC, before the 02:30 UTC batch writes the night's features, so it judges the previous night's features | 不用批 |
| [TD-157](#td-157) | P3 | research-data | GEX writes a wall on an arbitrary strike when one side of an expiry has no gamma exposure: 1,762 levels rows on 244 names, terrain reads both walls | 要你批 |

## 条目

### TD-85

**P1 · trade (round 1) · One database password reaches everything: any DEV pod can write PROD Trade and all of Golden Source**

- **状态**：观察中（到 10-07，看 `data_writer` 撤掉 `raw_broker` 权限后一个插件日内有无权限报错）
- **验收**：Golden Source 的 `datacl` 里没有 PUBLIC 的 CONNECT（`=c`），且 Postgres 日志 24 小时内 `data_writer` / `flex_writer` 的 `permission denied` 为 0：`kubectl -n data exec -i bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -X -At -c "SELECT datacl FROM pg_database WHERE datname = current_database()"`
- **现在**：D1–D8 全部执行完：三环境 Trade 运行时用 `trade_app_<env>` 登录；D4 已在三个 Trade 库收回 PUBLIC 的 CONNECT 和 CREATE（10-06，验证 74/74）；D7 ConfigMap 已合入；D6 收口完成，`data_writer` 在 `raw_broker` 上的写权已撤（core 0.48.2，10-06）。
- **下一步**：Golden Source 上 PUBLIC 仍能 CONNECT（D6 范围，未排期，要你批）；`data_writer` 撤权后再看一个插件日的权限报错。（10-07）
- **Claim**: Measured 2026-10-04 (read-only): nine Secret keys hold the same value, the bifrost password (PGPASSWORD and GOLDEN_SOURCE_PASSWORD in bifrost-{dev,stg,prod}-secrets, flex-query postgres-password / trade-pg-password, market-data postgres-password). bifrost can INSERT into 320 Golden Source tables and CREATE in raw_broker and research; analytics_writer inherits bifrost and can write all 19 tables of bifrost_prod.public. PUBLIC has CONNECT/TEMP on all four databases and CREATE on public in the Trade databases. D13 is not enforced at the database layer in either direction.
- **Evidence**:
  - `REQUEST-trade-runtime-db-role-plan-2026-10-04.md:1` — ``
- **Impact**: A compromised or misconfigured DEV workload can modify PROD trading data and the Research store; Research can write Trade tables.
- **Fix**: Per-env runtime roles trade_app_<env> (NOINHERIT, own database only; Golden Source only raw_broker and ops_feedback), bifrost kept for db-init/CNPG; Secret switch per env with one-patch rollback; then revoke PUBLIC CONNECT/CREATE, rotate the bifrost password, and separately drop analytics_writer's bifrost membership after Research gets explicit grants.
- 审批 安全/凭据（要你批） · 代价 L · 风险 medium · repos: bifrost-trade-infra, bifrost-research

### TD-87

**P1 · research-data · SEPA features are stamped with the next calendar day (UTC current_date at 02:30 UTC): every SEPA row is one session late and Friday sessions land on Saturday**

- **状态**：在做（代码已上线；等 Owner 跑历史数据重排）
- **验收**：`SELECT count(*) FROM features.stock_signal_sepa_daily WHERE extract(isodow FROM trade_date) IN (6,7)` 为 0，且下一次 research_trading_day 里 asset check `sepa_projection:sessions_are_trading_days` 通过
- **现在**：代码已修并上线（research 0.180.0，10-06）：七张 SEPA mart 改用 `sepa_session()`（源表最新交易日），`sepa_projection` 写纽约 session；防线 dbt 测试 `sepa_session_is_newest_trading_day` + Dagster asset check `sepa_projection:sessions_are_trading_days` + 静态测试。历史行还没改：写 PROD Golden Source 被 auto mode 拦下，交 Owner。
- **下一步**：Owner 跑 `~/bifrost-backups/golden-source/2026-10-06_td87-sepa-restate/` 里的 restate.py（101,673 → 94,759 行，删碰撞 6,914 行，09-01 的行实为 08-27 收盘、按数据改到 08-27）和 SEPA lens 重走；须在 10-07 02:30 UTC 批处理前，否则先重跑 dry run。跑完删掉本条。（10-07）
- **Claim**: All seven SEPA marts set eval_date = current_date. The database runs in Etc/UTC and research_trading_day fires at 22:30 New York (02:30 UTC the next day). mart_sepa_feature_daily turns eval_date into trade_date, and sepa_projection copies MAX(trade_date) into features.stock_signal_sepa_daily. So the Monday 10-05 session is stored as 2026-10-06 and Friday sessions as Saturday. signal_hit (_load_sepa_triggers WHERE trade_date = %s), the backtest event source and every join on trade_date pair SEPA with the following session; signal_hit walks only trading days, so Friday SEPA triggers are never read and Monday sessions have no SEPA input.
- **Measured**: MEASURED (re-checked by verifier). show timezone = Etc/UTC; no role/profile timezone override. dw_stock.mart_sepa_feature_daily holds only 2026-10-06 (3,742 rows) while int_stock_daily_enriched max(trade_date) = 2026-10-05. features.stock_signal_sepa_daily since 07-01: 5 Saturday dates, 1 Sunday, 1 Monday (09-28, a manual run); 21,016 of 101,673 rows in the last 60 days fall on a weekend. It is the only features/research/dw_stock/journal table with weekend trade_dates. lens_hit lens='sepa' has 1 Monday vs 3-5 for every other weekday.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/dbt/models/marts/mart_sepa_technical_eval.sql:45` — `current_date as eval_date,`
  - `bifrost-research/src/bifrost_research/dbt/models/marts/mart_sepa_feature_daily.sql:9` — `w.eval_date as trade_date,`
  - `bifrost-research/src/bifrost_research/orchestration/sepa_projection.py:80` — `SELECT MAX(trade_date) FROM dw_stock.mart_sepa_feature_daily`
  - `bifrost-research/src/bifrost_research/orchestration/schedules.py:85` — `cron_schedule="30 22 * * 1-5",`
- **Impact**: Stored data is wrong now. SEPA lens hit rate, forward returns, SEPA backtests (entries one session late; Friday signals enter Monday) and the screener eval_date all describe the wrong session. Friday SEPA triggers never reach lens_hit; Monday lens_hit has no SEPA input.
- **Fix**: Derive the session from the data, not the clock: eval_date = (select max(trade_date) from int_stock_daily_enriched), or pass --vars '{as_of: <NY session>}' from the Dagster asset; sepa_projection passes the NY session explicitly. Then restate stock_signal_sepa_daily (Research-owned) by shifting each row to the last session on or before trade_date - 1 (dry run first) and re-walk the SEPA lens with delete-then-insert.
- **Ratchet**: (1) dbt test on mart_sepa_feature_daily: trade_date = max(bar_date) of source and is_trading_day (gives dim_trading_calendar a reader or replaces it). (2) Nightly session-date sweep (~30 lines SQL) as asset check/Prometheus rule: no features.*/research.* row with trade_date on a weekend, holiday or later than the newest SPY bar.
- 审批 不用批 · 代价 M · 风险 med · repos: bifrost-research

### TD-91

**P1 · flex-ib · A failed cash-transactions write is recorded as a successful run: core returns 0 on any exception and the job counts it as 'ok, 0 rows'**

- **状态**：未开始
- **Claim**: core upsert_account_transactions catches every exception, logs a warning and returns 0; the plugin turns that into ok:true 'Upserted 0 transaction(s)', _require_ok accepts it, record_freshness(ok=True) advances last_success, and no BifrostFlexIngest* alert fires. A lost grant (TD-86 class), lock timeout or type error drops a day's cash rows silently. It also returns len(rows), including rows skipped for missing account_id/report_date. core tests/test_connect_helpers.py:118 currently pins the silent 0 return, so this is a deliberate contract change. The trades path does not have this flaw (returns False → ok:false).
- **Measured**: CODE-READ for the failure path; jobs 151-185 all wrote 11-16 rows. Precedent is real: TD-86 broke a different writer on 10-05 via dropped grants.
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1417` — `logger.warning("upsert_account_transactions failed: %s", e)`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1413` — `return len(rows)`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/transactions.py:104` — `msg = f"Upserted {n} transaction(s) from {len(entries)} Flex account(s)."`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/worker/handlers.py:30` — `inserted = int(data.get("count") or data.get("inserted") or 0)`
- **Impact**: Cash ledger rows can stop landing while the plugin, its metrics and Ops Console report healthy runs: the failure-as-success class TD-08 fixed for reads, now on a money writer.
- **Fix**: Make upsert_account_transactions raise on DB errors (or return (written, skipped) and let the caller raise). Update test_connect_helpers.py:118 and bump core per the versioning rule since the plugin depends on the return. In the plugin treat parsed rows > 0 with written == 0 as ok:false; report skipped separately.
- **Ratchet**: Core test: a raising cursor must propagate. Plugin test: rows>0 with written 0 must raise. code-health metric: `except Exception` blocks in persistence writers ending in return 0/False without re-raise; baseline may only fall.
- 审批 改公开接口 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-platform-plugin-flex-query

### TD-51

**P2 · trade (round 1) · Query-parameter vocabulary drift for expiry, option side, time ranges and limits; no pagination**

- **状态**：在做（api 0.10.0 在 main、CI 绿；等 Owner 跑合并 Trade 发布）
- **验收**：`python3 scripts/release/loki_gate.py td51-query-aliases` 零命中；发布后 PROD `/health` 的 api 版本为删除旧名的那一版，旧查询名返回 422
- **现在**：Research 和 Dagster 已改用新的查询参数名（research 0.161.0 起）。api 侧删除旧名与整套别名机制的提交 `a4757c5` 已备好。
- **下一步**：跑 Loki 闸门（`loki_gate.py td51-query-aliases`），10-05 夜批后旧名零命中就随下一次 Trade 发布上线。（10-06）
- **Claim**: Expiry has two names (expiry/expiration) and four format rules: YYYYMMDD on /bars, YYYY-MM-DD on /research/greeks, either format on option-snapshots and similar, and 'any format' on link-candidates. Option side is option_right in some routes and right in others. Time ranges are spelled four ways: since_ts/until_ts, opened_at_from/until, trade_date_from/to and date_from/to. limit=0 means unlimited on GET /executions, and the FE always sends it; the /transactions limit is unbounded. No route takes offset, page or cursor, and at least 12 lists return count = len(page). The tier screener is the only one that returns a real total.
- **Evidence**:
  - `bifrost-trade-api/src/bifrost_api/market/routers/market_data.py:71` — `expiry: Optional[str] = Query(None, description="Option expiry YYYYMMDD (with asset=option)")`
  - `bifrost-trade-api/src/bifrost_api/research/routers/greeks.py:300` — `expiry: Optional[str] = Query(None, description="Filter to one expiry YYYY-MM-DD")`
  - `bifrost-trade-frontend/src/api/trading.ts:40` — `tradingUrl(`/executions?limit=0&source_scope=${scope}`)`
  - `bifrost-trade-api/src/bifrost_api/strategy/routers/plans.py:74` — `return {"items": items, "count": len(items)}`
- **Impact**: Callers send the wrong format. Readers treat a truncated count as the total (memory a_limited_count_is_a_floor). Unbounded /executions grows with history.
- **Fix**: Publish one shared Query vocabulary (expiry YYYY-MM-DD, option_right, from/to with a unit) and accept the old names as aliases. Add total plus a cursor, starting with /executions and /transactions.
- 审批 改公开接口 · 代价 M · 风险 med · repos: bifrost-trade-api, bifrost-trade-frontend

### TD-92

**P2 · research-control · Engine assets never fail: per-symbol failures, zero-row writes and skips are only metadata, reasons are discarded, and research_trading_day is green regardless of output**

- **状态**：观察中（到 10-07 02:30 UTC 批处理，看 16 个引擎的 output_ok 检查都执行了）
- **验收**：`kubectl -n research logs deploy/dagster-daemon --since=3h | grep ASSET_CHECK_EVALUATION` 在 research_trading_day 里有 16 个 engines 的 output_ok；ERROR 级失败会发 `BifrostDagsterAssetCheckFailed`
- **验收结果**：部分 PASS 2026-10-06 a242b22：32 个 output_ok 检查已加载，intraday run 两个检查通过；批处理待今晚
- **Claim**: engine_assets._metadata wraps any result into MaterializeResult; run_gex/run_iv_surface/run_flow do `failed += 1` and drop result['error']; run_slot returns a non-raising 'skipped: no symbols'. No Dagster asset checks exist; only gex_intraday raises on zero output (added after three green weeks of 646-669/669 failures). The only other net is signal_health's 36h/72h computed_at freshness on a subset of tables, which misses partial failures, zero-row writes, wrong-date writes and tables such as research.option_pinned_contract. Silent failures like TD-89 and TD-97 are visible only by reading run metadata by hand.
- **Measured**: MEASURED. ops_dagster.runs research*/market*, 14 days: 1,026 SUCCESS, 1 FAILURE (memory_distill, TD-86), 1 CANCELED. 10-06 run metadata: gex 42 failed / 1,366 ok over 2 sessions (~3%, about 15-22 names a night), flow 41, surface 41, momentum skipped 4, vrp skipped 7, option_pinned rows_written 0, all green. Most failing names entered option_universe in the last few days (onboarding lag); persistent invisible gaps: NVR (in universe since 09-08, 0 OI rows since 08-01, never a GEX row) and GRML (since 09-24, no OI); QRVO stock_daily stops at 10-02.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/engine_assets.py:36` — `def _metadata(result: dict[str, Any]) -> dict[str, Any]:`
  - `bifrost-research/src/bifrost_research/scheduler/engines.py:108` — `failed += 1`
  - `bifrost-research/src/bifrost_research/orchestration/research_aux_schedules.py:51` — `return MaterializeResult(metadata=meta(result if isinstance(result, dict) else {}))`
  - `bifrost-research/src/bifrost_research/orchestration/engine_assets.py:300` — `result = runners.run_option_pinned_contract()`
- **Impact**: A broken engine looks the same as a working one on the Ops schedule view and in failure_alerts. NVR and GRML have had no GEX/surface/flow for weeks and nothing says why; onboarding lag, upstream gaps and bugs are indistinguishable.
- **Fix**: Return failures as {symbol: error} (capped) plus per-reason counts from gex/surface/flow. Add Dagster asset checks (or raise in runners) with floors against a trailing baseline: rows_written >= 50% of the 10-run median, failure share among names past the onboarding window <= ceiling, a past-onboarding name failing 2+ sessions, mode != skipped twice running. Route check failures through failure_alerts; push persistent per-reason gaps to the Data Gaps ledger.
- **Ratchet**: Test enumerating ENGINE_ASSETS and RESEARCH_AUX_ASSETS: each has a registered asset check or an explicit opt-out with reason. Unit test: every slot summary carrying symbols_failed carries a failures-by-reason dict. code-health metric: bare `failed += 1` in scheduler/ (baseline 3, falling).
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research

### TD-93

**P2 · research-data · db/calendar.py turns read failures into wrong answers: a failed holiday read makes holidays sessions, a failed universe read swaps the engine universe for 'whatever OI was ingested' or nothing**

- **状态**：在做（10-06 还债第 B 路：Research 日期/日历/dbt/定价）
- **Claim**: fetch_closed_holiday_dates' inner _rows() catches any exception, rolls back and returns [] with no log, so today and every future holiday become sessions (past dates fall back to index bars); cached_closed_days' warning cannot fire and fetch_recent_trading_days (6 callers) gets no signal. In the same module, load_symbols_from_universe_rule catches every exception and returns []; load_symbols_from_env_or_query then falls back to SELECT DISTINCT underlying FROM raw_market.option_open_interest LIMIT 5000, also swallowing errors, and RESEARCH_WATCHLIST overrides the rule entirely. ~12 engines share this loader and materialize SUCCESS on a different universe or none. dw_stock.dim_trading_calendar is a third calendar definition with no reader anywhere.
- **Measured**: Partly MEASURED. git grep finds no reader of dim_trading_calendar in any repo. research.option_universe has 713 readable rows today; TD-86 shows unrelated db-init runs do drop grants on Research-read objects. Both swallows are CODE-READ; no failure observed tonight.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/db/calendar.py:61` — `except Exception:`
  - `bifrost-research/src/bifrost_research/db/calendar.py:66` — `return []`
  - `bifrost-research/src/bifrost_research/db/calendar.py:223` — `LIMIT 5000`
  - `bifrost-research/src/bifrost_research/db/calendar.py:209` — `env = (os_environ_watchlist())`
- **Impact**: One grant or timeout regression silently brings back holiday sessions in forward projections (forecast sessions, settlement, opex) or writes features for the plugin's whole ingested set (resident tier is ~7x storage) or for nothing, under green runs. The dead dbt model invites a fourth calendar copy.
- **Fix**: Log at warning and propagate: holiday read failure raises or tags the result 'calendar_degraded' surfaced in metadata/asset check; universe read errors propagate, OI fallback only on UndefinedTable/empty table; engines raise when the resolved universe is empty on a trading day and log universe_source + count in every summary. Make dim_trading_calendar the single SQL calendar bounded by the NY date, or delete it.
- **Ratchet**: Tests: holiday query raising → fetch_recent_trading_days does not return a known holiday (or raises); universe loader re-raises InsufficientPrivilege and QueryCanceled; engine summary carries universe_source and symbols>0 on a trading day. Shared broad-except grep ratchet (see TD-113).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-94

**P2 · research-control · husbandry_gate fails open: a probe exception leaves verdict 'unknown', which passes, and the gate never checks that the doctor's session is the one being closed**

- **状态**：观察中（到 10-07 02:30 UTC 批处理，看闸门放行且 expected_session = market_session）
- **验收**：今晚 husbandry_gate 的 metadata：`gate=pass`、`expected_session == market_session`；探针失败时 run 变红（12 个单测覆盖）
- **Claim**: Since research a241f30/47af11e (09-28) the gate reads a freshly computed doctor report (refresh=true, 600s timeout), which fixed the stale-session and empty-report runs of 09-16..09-26. What remains: any doctor/Flex probe exception is logged as a warning and the verdict stays 'unknown'; the gate raises only on critical/failed/stale/none, so 'unknown' passes, and no assertion ties doctor.session to the session being closed. dbt and every engine then run with the EOD gate off.
- **Measured**: MEASURED. Before the 09-28 fix: unknown verdicts passed on 09-16, 09-25, 09-26; wrong-session 'healthy' on 09-22 (gated 09-18) and 09-24 (gated 09-22). All 6 runs since 09-29 carry the right session and generated_at. tests/orchestration/test_husbandry_gate.py has no all-probes-fail case.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/plugin_batch_assets.py:148` — `except Exception as exc:  # noqa: BLE001`
  - `bifrost-research/src/bifrost_research/orchestration/plugin_batch_assets.py:169` — `if eod_verdict == "critical":`
- **Impact**: Latent: on a night the plugin is down or doctor computation exceeds 600s, dbt, SEPA and all engines rebuild on a possibly incomplete session and report SUCCESS, the 09-05 'recomputed on partial data' class the gate exists to stop.
- **Fix**: Treat 'unknown' as failure for EOD and Flex checks (raise; explicit override config for manual runs). Compute the expected session via fetch_recent_trading_days and raise when doctor.session differs or generated_at is missing.
- **Ratchet**: test_husbandry_gate.py: (a) all probes raise → asset raises; (b) doctor.session != expected → raises; (c) generated_at missing → raises.
- 审批 不用批 · 代价 S · 风险 med · repos: bifrost-research

### TD-95

**P2 · research-control · No release path is gated on CI: deliver-research ships SHAs whose CI is red (CI starts 7s after deliver), and release.sh never checks CI for Trade**

- **状态**：未开始
- **Claim**: pipeline-deliver-research goes mirror-sync → clone → build/pin-check → gitops-sync → rollout → verify and never reads the bifrost-ci-python result for the revision it ships; both start from the same push ~7s apart, so a red CI cannot stop a release. It also accepts revision=main instead of a SHA. release.sh (Trade) likewise does not check CI status. CI is a post-hoc report.
- **Measured**: MEASURED. research 0.172.0, 0.173.0 (twice) and 0.174.0 delivered while their CI runs (hkrvq, bjgln, z96rg, sccxz) Failed; the only failed task was a code-health false positive (pine image tag counted), fixed in infra 1984dac; lint-test passed, so nothing broken shipped. Ratchet inventory: trade-api main CI red since 10-04 (test_bs_core_switch::test_core_reproduces_the_recorded_research_math), 14 of 28 runs failed in 7 days, api 0.9.0 released anyway; the three plugin repos had 32 commits and infra 120 commits since 09-29 with 0 CI runs; Tekton metrics are not scraped.
- **Evidence**:
  - `bifrost-trade-infra/k8s/cicd/tekton/pipeline-deliver-research.yaml:126` — `- name: pin-check`
  - `bifrost-trade-infra/k8s/cicd/tekton/pipeline-ci-python.yaml:14` — `CI gate for Python repos — ruff lint + pytest (skipping IB/DB markers);`
  - `bifrost-trade-infra/scripts/release/release.sh` — `(no reference to ci-* PipelineRun status; CODE-READ per ratchet inventory)`
- **Impact**: A real ruff/pytest failure reaches the Golden Source writers (research) or Trade with nothing to stop it. Every test-based ratchet in this ledger is advisory until CI gates release.
- **Fix**: Add a lint-test (ruff + pytest + code-health) task on the cloned SHA ahead of build in pipeline-deliver-research and pipeline-build-research-dagster, or require a Succeeded ci-* run for that exact SHA. Reject non-40-char revisions. release.sh refuses stg/prod unless the SHA's CI Succeeded (--allow-red <reason> for Owner).
- **Ratchet**: Infra check-script YAML assertion: every deliver pipeline has a lint-test task in build's runAfter and validates revision as a SHA. BifrostCIMainRed alert (scrape tekton controller metrics): any repo's latest main ci-* Failed > 2h.
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-research

### TD-96

**P2 · agent-governance · preflight.js D10 rule only recognises curl: python requests, wget --post-data and sed -i on the daemon scale-zero patch all pass**

- **状态**：未开始
- **Claim**: The monitor /control/* rule requires curl-style -X/--request/-d/--data/--json/-F flags, and guard-file protection recognises rm/mv/truncate. A POST via python requests/httpx, wget --post-data, or an in-place edit of k8s/overlays/stg/daemon-scale-zero.patch.yaml with sed -i/tee/cp is allowed. The gate covers only agent tool calls; humans and CI do not pass through it.
- **Measured**: MEASURED by the ratchet-inventory pass (sample strings fed to preflight.js locally): `sed -i … daemon-scale-zero.patch.yaml`, `python3 -c requests.post('…/api/monitor/control/arm')` and `wget --post-data … /control/arm` each returned ALLOW. test.js (42 cases) passes but has no case for these forms and runs in no CI. Not adversarially re-verified.
- **Evidence**:
  - `bifrost-trade-infra/agent-config/scripts/agent-guard/preflight.js:107` — `/\/(account-sync\/)?control\/[\w-]+/.test(cmd) &&`
  - `bifrost-trade-infra/agent-config/scripts/agent-guard/preflight.js:109` — `/\bcurl\b[^|;&]*\s(-d|--data[\w-]*|--json|-F|--form)\b/.test(cmd))`
- **Impact**: The D10 hard boundary's mechanical layer can be bypassed by an ordinary alternate client or file edit; only the spine/overlay layer remains. Same class as TD-07.
- **Fix**: Owner-applied (agents must not edit guard files): extend d10Rules to match /control/ writes via requests/httpx .post/.put/.delete, wget --post-data/--method, http(ie) POST; extend the guard-file rule to sed -i/tee/cp/>/kubectl patch|edit|apply on the scale-zero/observe-safe patches and daemon replicas. Add one DENY case per form to test.js.
- **Ratchet**: test.js gains a DENY case per bypass form and runs blocking in a new ci-infra pipeline (see ratchet proposal 'ci-infra').
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-97

**P2 · research-data · alert_scan judges each session once, a day late, and never revisits; composite_high has never fired because every >=90 score appeared on a later scan recompute**

- **状态**：观察中（到 10-07 02:30 UTC 批处理，看 alert_scan 判的是当天 session）
- **验收**：今晚 alert_scan 的 metadata：`as_of == session == 2026-10-06`；`--dry-run --rejudge 25` 能重新判出 composite_high
- **Claim**: alert_scan runs at 22:30 UTC and takes as_of = MAX(trade_date) of the scan table, so session X is judged at 18:30 ET on X+1. It writes each date once. The scan engine re-walks the last 3 sessions, and the only composite_score >= 90 rows (META 08-31; AVGO/HUM/NKE/PEP/PSX/VLO 09-24) appeared on those later recomputes, so composite_high has produced nothing and the job is green.
- **Measured**: MEASURED. features.stock_signal_alert_daily since 08-28 (21 dates): hit_rate_drop 38, weight_shift 51, composite_high 0. META 08-31 was written 09-03 02:32; the six 09-24 names 09-29 02:36. 99th percentile score since 09-01 is 78.6; 7 qualifying rows ever.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/research_aux_schedules.py:473` — `"30 22 * * 1-5",`
  - `bifrost-research/src/bifrost_research/engines/alert_scan/entry.py:50` — `cur.execute(f"SELECT MAX(trade_date) FROM {TABLE_STOCK_SIGNAL_SCAN_DAILY}")`
  - `bifrost-research/src/bifrost_research/engines/alert_scan/entry.py:63` — `WHERE trade_date = %s AND composite_score >= 90`
- **Impact**: The headline alert kind is dead (small volume: 7 rows in ~5 weeks); digest and Copilot readers never see top-composite names; other kinds arrive a session late.
- **Fix**: Re-evaluate the last N scan dates with replace-per-(trade_date, kind) semantics so a recompute can raise or retract an alert, and move the job into research_trading_day with deps on engines/scan (removes the lag).
- **Ratchet**: Unit test parsing every ScheduleDefinition: an aux job whose engine reads a table written by research_trading_day may not fire between 20:00 and 02:30 UTC (small reads→writers map next to the assets). Asset check: judged as_of equals the latest NY session.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-98

**P2 · research-data · 'Today' is resolved by 11 private helpers plus 44 bare date.today() calls on UTC pods; option_universe stamps tomorrow's date**

- **状态**：在做（10-06 还债第 B 路：Research 日期/日历/dbt/定价）
- **Also (paydown lane A, 10-06)**：`engines/pine/build.py:191` `end = as_of or date.today()` — UTC date on the 02:30 UTC run, the next calendar day.
- **Claim**: Eight helpers return the New York date (_today_ny), three return the UTC date (_today in option_universe, option_pinned, terrain_backfill), and 44 date.today() calls return UTC because no research pod sets TZ. db/calendar.fetch_recent_trading_days also defaults to the UTC date. decline_memory.py documents the wrong 'same host' assumption, and the `noqa: DTZ011` there does nothing because ruff selects only E4/E7/E9/F. Anything run by research_trading_day (02:30 UTC) through _today()/date.today() gets the next calendar day.
- **Measured**: MEASURED. No TZ env on research-api, dagster-daemon, dagster-webserver, research-mcp, research-pine or api-research. In dagster-daemon, date.today() = 2026-10-06 while NY was 10-05. research.option_universe: 678 rows last_seen 2026-10-06; entered_on on Saturdays (10-03: 6, 09-26: 9, 09-19: 24). candidate_pool path is latent (writers run when UTC and NY agree).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/option_universe/entry.py:85` — `return datetime.now(timezone.utc).date()`
  - `bifrost-research/src/bifrost_research/engines/option_universe/entry.py:227` — `"last_seen": as_of if seen else (prev["last_seen"] if prev else as_of),`
  - `bifrost-research/src/bifrost_research/copilot/harness/decline_memory.py:320` — `trade_date=date.today(),  # noqa: DTZ011`
  - `bifrost-research/src/bifrost_research/db/calendar.py:181` — `end = as_of or datetime.now(timezone.utc).date()`
- **Impact**: option_universe stores wrong dates and its liquidity/liveness windows shift a day; any engine adopting date.today() for a session stamp repeats TD-87. Each copy is a place the session rule can drift.
- **Fix**: One session_today() (latest NYSE session <= NY date) and ny_now() in db/calendar.py; replace the 11 helpers and stamp-carrying date.today() calls. Set TZ=America/New_York on Dagster/research pods only as a defensive layer.
- **Also (found by the TD-87 fix, 10-06)**: `engines/option_pinned/entry.py` `_today()` and `engines/forecast/terrain_backfill.py` `_today()` (UTC); `engines/backtest/event_query.py:160,1322`, `engines/brief/synth.py:79,486`, `copilot/agents/_context.py:26`, `copilot/harness/readiness.py:29` (`date.today()`); `lenses/exhibit_lenses.py:532` (`CURRENT_DATE - 30`). `db/calendar.latest_closed_session` (0.180.0) is the shared NY-session helper to adopt.
- **Ratchet**: Enable ruff DTZ (DTZ005/DTZ011) for src/ with a falling baseline; code-health grep fails on a new `def _today`/`def _today_ny` outside db/calendar.py.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research

### TD-99

**P2 · research-control · No scheduler liveness alarm: a stopped, renamed or never-ticking Dagster schedule, or a hung daemon, produces no alert; no PrometheusRule targets research**

- **状态**：在做（10-06 还债第 C 路：调度与编排）
- **Claim**: bifrost_run_failure_alert fires only on FAILURE runs and executes inside dagster-daemon. Nothing alerts on a schedule that stops producing runs (STOPPED in the instance DB, which the Makefile warns about), a schedule renamed/removed in code, or a daemon alive but not ticking. /research/orchestration/status computes overdue only for research_trading_day and only when the page (or the platform checklist handler) is requested. BifrostAPIHighErrorRate/CrashLooping match bifrost-* namespaces only; research-api and plugins have no http_requests_total.
- **Measured**: MEASURED. All PrometheusRules: only three freshness-type alerts (backup drill, Flex ingest, market-data doctor); none for research/Dagster. ops_dagster.daemon_heartbeats is live but unread. A 49-min gap in event_radar cadence on 09-24 matches the 0.108/0.109-dagster crash loop. Today all 40 schedules RUNNING/DECLARED_IN_CODE.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/failure_alerts.py:64` — `@run_failure_sensor(`
  - `bifrost-research/Makefile:45` — `# Instance DB may keep STOPPED even when DefaultScheduleStatus.RUNNING — flip explicitly.`
- **Impact**: The September failure class (forecast had no producer from 08-30 while green; trading_day STARTED for 20.5h) is caught only when a human looks; a stopped schedule looks like a quiet night.
- **Fix**: Export bifrost_dagster_schedule_last_success_seconds{schedule} from ops_dagster (research-api /metrics or a small exporter) with expected cadence from the roster; add BifrostDagsterScheduleOverdue (age > 2x cadence, calendar-aware) and BifrostDagsterDaemonHeartbeatStale (> 5 min); extend crash-loop/workload/5xx rules to namespace research and plugin-*.
- **Ratchet**: The PrometheusRules themselves, plus a research test that every ScheduleDefinition has a cadence entry in the exporter table so new schedules are covered automatically.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research, bifrost-trade-infra

### TD-100

**P2 · research-control · Event Radar SEC ingest runs from a Mac tmux loop on the shared checkout; it read .env once and failed 157 ticks over ~35.6h after a password rotation; the cluster event_radar slot never ingests and stays green**

- **状态**：在做（10-06 还债第 C 路：调度与编排）
- **Claim**: The only producer of SEC 8-K input for features.event_signal_radar_daily is scripts/event_radar_watch.sh under bdev on the Owner's Mac, running uncommitted shared-checkout code as Trade role 'bifrost'. It sources .env once and swallows every failure with '|| echo ... will retry'. The cluster's event_radar_cron asset has no input mount and returns idle/sample_fallback every 30 minutes, green. (The Mac placement is a documented choice: no PVC mount, launchd lacks LAN permission.)
- **Measured**: MEASURED. ~/.bifrost-dev/logs/event-radar-watch.log: 158 'sec source failed' lines (1 on 09-28 QueryCanceled; 84 on 10-04; 73 on 10-05) from 10-04 09:15 to 10-05 20:52, all password auth failures for 'bifrost', until a manual restart at 20:54:31. Watermark kept loss at zero because no new filings landed in that window (145 filings written after restart). event_radar_cron, 30 days: 684 idle, 332 sample_fallback, 0 file_ingest.
- **Evidence**:
  - `bifrost-research/scripts/event_radar_watch.sh:16` — `set -a; source .env; set +a`
  - `bifrost-research/scripts/event_radar_watch.sh:25` — `|| echo "$(date '+%F %T') sec source failed (will retry next tick)"`
  - `bifrost-research/src/bifrost_research/orchestration/runners.py:181` — `"mode": "idle",`
- **Impact**: A research feed depends on the laptop being awake (it sleeps at night), a tmux session, credentials never re-read and unreleased code; failure is visible only in a local log. A rotation across a filing night delays events until someone notices, while the green Dagster schedule hides the dependency from Console.
- **Fix**: Move SEC 8-K collection into Dagster as an asset writing the batch directly as analytics_writer and raising on failure. Make the cluster asset raise (not 'idle') when its input mount is absent, or delete it. Interim: watcher re-sources .env each tick and exits non-zero after N consecutive failures so bdev-supervise/bdev status surface it.
- **Ratchet**: Freshness alert: max(computed_at) of features.event_signal_radar_daily older than 2 trading days. Test: run_event_radar raises when input_dir does not exist.
- 审批 不用批 · 代价 M · 风险 med · repos: bifrost-research, bifrost-trade-infra

### TD-101

**P2 · market-data · Doctor slot staleness reads a per-kind freshness row that other slots and zero-row jobs also refresh, so a stopped policed slot still reads fresh**

- **状态**：在做（10-06 还债第 D 路：market-data）
- **Claim**: After any done job the worker upserts ops_jobs.ingest_freshness keyed by dimension only, bumping last_run_at even for 0-row or skipped jobs, with status always 'ok'. The doctor's stale:<slot> check (and Console adherence, ingest_dashboard._evidence_for_fire) reads that row by dimension, and several policed slots share a dimension: reference with ticker-details (ticker_sync), option-refresh with option-contract-expired (option_contract), corporate with corporate-backfill (dividends). If the reference walk stops, stale:reference stays ok while ticker-details runs.
- **Measured**: MEASURED. ingest_freshness.ticker_sync last_run_at 2026-10-06 03:30:26 rows_written=1 (a detail job) while the last universe walk finished 10-05 21:30:27 (600 detail vs 2 universe jobs). option_expiration frozen since 09-06 and stock_daily_unadjusted at 10-02, both 'ok'. All 23 rows status 'ok'.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/freshness.py:85` — `ON CONFLICT (dimension) DO UPDATE SET`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/doctor.py:1709` — `fresh = _freshness(conn)`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/daily.py:2690` — `_add("ticker_sync", {"mode": "universe"}, pri=priority)`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/daily.py:2739` — `_add("ticker_sync", {"mode": "detail", "symbol": sym}, pri=priority)`
- **Impact**: Doctor and Console report reference and option-refresh healthy whether or not they ran; any zero-row run counts as freshness ('firing is not delivery' class), hiding a stopped catalogue walk.
- **Fix**: Key freshness by (dimension, slot) via a slot field in job payloads, or have the doctor check slot adherence from job evidence of the slot's own payload shape. Bump last_run_at only when rows_written > 0 (or add last_nonzero_at). Drop the constant status column or write real statuses.
- **Ratchet**: Unit test derived from the slot→kinds map and contracts.staleness_by_slot(): no policed slot shares a freshness dimension with another slot (explicit allowlist otherwise).
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-102

**P2 · market-data · Plugin's deprecated live max-pain and PCR routes duplicate Research and skip the adjusted-contract filter: different strikes on the same day, and trade-api SEPA PCR reads the contaminated one**

- **状态**：未开始
- **Claim**: The plugin keeps a 'transition' copy of Research's max-pain math plus its own PCR query, both reading raw_market.option_open_interest with no adjusted-root predicate (Research added not_adjusted_contract_sql on 10-01). OI from adjusted roots (O:HON2…, O:MOD1…) is summed into standard chains. trade-api sepa_engine/stock_option_pcr.py calls fetch_pcr_aggregate against this route.
- **Measured**: MEASURED (re-run by verifier) for 2026-10-05: plugin vs Research max pain HON 12-18 210 vs 220, FDX 12-18 310 vs 300, GME 10-16 23 vs 22.5, MOD 10-16 same strike but OI 19,510 vs 9,848. 424 adjusted-root OI rows across 19 underlyings that day. Loki 7 days: /max-pain/compute called only by the probe; /options/analytics/pcr 4 times (trade-api SEPA PCR).
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/analytics.py:613` — `FROM raw_market.option_open_interest`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/pcr.py:65` — `FROM raw_market.option_open_interest`
  - `bifrost-research/src/bifrost_research/engines/adjusted_contracts.py:22` — `return f"substr({column}, 3, length({column}) - 17) !~ '[0-9]$'"`
- **Impact**: Wrong pin strikes for names with corporate-action roots from the plugin route; SEPA option-PCR condition in trade-api computed from contaminated OI; two implementations already disagree.
- **Fix**: Retire /market/analytics/max-pain/compute(+history) and analytics/max_pain_math.py (no real callers); point trade-api fetch_pcr_aggregate at Research's filtered PCR. Until then add the adjusted predicate to every plugin aggregate read of option_open_interest/snapshot/daily.
- **Ratchet**: Plugin test grepping api/*.py: aggregate reads of raw_market.option_(open_interest|snapshot|daily) must contain the adjusted-root predicate or be allowlisted. Register max-pain in the cross-repo duplication metric so a second compute_max_pain_curve fails the scan.
- 审批 改公开接口 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data, bifrost-trade-api

### TD-103

**P2 · flex-ib · The cash parser never stores IB's transactionID, so dedupe falls back to (account, day, amount, type, report_date) and same-amount items overwrite each other**

- **状态**：未开始
- **Claim**: parse_cash_transactions_xml reads transactionID only from a child element; the attribute fallback covers every other field but not this one, so on IB's attribute-style rows flex_transaction_id is always NULL. The UNIQUE key then uses a date-only ts, amount, and a type that maps fees/interest/withholding to 'other'. Two distinct same-day same-amount transactions collapse and the second DO UPDATE overwrites symbol/description/raw_extra. A row with no dateTime gets ts=now(), re-inserted every run.
- **Measured**: MEASURED: flex_transaction_id NULL on 121/121 rows while raw_extra->>'transactionID' is present on all 121. 89 rows typed 'other'. 30 (account, ts, type, report_date) groups hold >1 row, separated only by amount; 6 have coinciding absolute amounts. A collapse leaves no trace, so none observed directly.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/client/flex_client.py:288` — `transaction_id = _text(elem, "transactionID") or _text(elem, "TransactionID")`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/client/flex_client.py:367` — `ts_parsed = datetime.now(timezone.utc)`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1372` — `ON CONFLICT (account_id, ts, amount, type, report_date) DO UPDATE SET`
- **Impact**: Fees, dividends or withholding can be under-counted by exact duplicates, and the surviving row's description can belong to the other transaction, on a money table read by Transfer & Pay and net cash-flow.
- **Fix**: Read transactionID from the attribute too; backfill flex_transaction_id from raw_extra; add a partial UNIQUE index on (account_id, flex_transaction_id) as the conflict target when present (old key only for id-less rows); drop the now() fallback (skip and count dateless rows).
- **Ratchet**: After backfill, NOT NULL/CHECK on flex_transaction_id for flex-sourced rows. Parser test with an attribute-only <CashTransaction> fixture (made-up values): id set, two same-day same-amount rows yield two dicts with different ids.
- 审批 改表 · 代价 M · 风险 med · repos: bifrost-platform-plugin-flex-query, bifrost-trade-core

### TD-104

**P2 · flex-ib · Trade Ops reports all three IB Gateway services 'offline' on PROD: the gateway's health hashes have no updated_at, and the service rows point at retired StatefulSets**

- **状态**：未开始
- **Claim**: trade-api judges liveness from the health hash's updated_at (missing = dead). The gateway writes ws_ib_ingestor/ws_ib_account_agent/ws_ib_operator without updated_at and never has since 07-04. /ops/market-ingest/services shows runtime_status=inactive 'managed@platform-ib-gateway (offline)'; platform satellite maps 'inactive' to ReachFail and the endpoint is a Tier-B probe. The rows also name retired ib-operator/ib-market-gateway/ib-account-agent workloads and systemd units. TD-31's contract covers key names, not field names.
- **Measured**: MEASURED: PROD /api/monitor/ops/market-ingest/services returns inactive/offline for all three, naming deployments that do not exist, while data/ib-gateway has been Running 3d12h with 0 restarts. git log -S shows the gateway never wrote updated_at into these hashes.
- **Evidence**:
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/writer.py:74` — `self._write_hash(IB_INGESTER_HEALTH_KEY, {"env": self._env, "plugin": "ib-gateway", **fields})`
  - `bifrost-trade-api/src/bifrost_api/ops/market_ingest_health_clear.py:138` — `if updated <= 0 or (now - updated) > _HEALTH_RECENT_MAX_S:`
  - `bifrost-trade-api/src/bifrost_api/ops/market_ingest_display.py:66` — `"display_active": "managed@platform-ib-gateway (offline)",`
  - `bifrost-trade-api/src/bifrost_api/ops/market_ingest_config.py:71` — `"systemd_unit": "bifrost-ib-operator.service",`
- **Impact**: An always-red health signal trains people to ignore it; a real gateway outage looks like today's false one, and the market-ingest satellite/Tier-B probe is permanently fail.
- **Fix**: Gateway writes updated_at=time.time() into the three hashes (timestamp + age check per the liveness rule) or sets a TTL of a few write periods. Retarget the Trade service rows to deployment data/ib-gateway and drop retired systemd units.
- **Ratchet**: Extend tests/contracts/redis_ib_keys.json with required hash fields per health key (updated_at, connected/host_connected): plugin test asserts the writer emits them; core and trade-api tests assert readers use only listed fields.
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-platform-plugin, bifrost-trade-api, bifrost-trade-core

### TD-105

**P2 · flex-ib · DEV/STG operator streams accept every op except two (a denylist), so any op added later is open to DEV and STG by default**

- **状态**：未开始
- **Claim**: READ_ONLY_OPS = ALL_OPS minus disconnect_all/reconnect_all, and op_allowed_on_stream accepts READ_ONLY_OPS on the env streams, whose ACL users may XADD. The guard test asserts ALL_OPS - READ_ONLY_OPS == {disconnect_all, reconnect_all}, which still passes after a new op is added, and the env-stream test parametrises over READ_ONLY_OPS itself.
- **Measured**: CODE-READ. ALL_OPS today = fetch, refresh, ping and the two connection ops, so nothing is exposed now.
- **Evidence**:
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/protocol.py:27` — `READ_ONLY_OPS: Tuple[str, ...] = tuple(op for op in ALL_OPS if op not in ("disconnect_all", "reconnect_all"))`
  - `bifrost-platform-plugin/src/bifrost_plugin/ib_gateway/operator.py:89` — `return stream not in IB_OPERATOR_ENV_CMD_STREAMS or op in READ_ONLY_OPS`
  - `bifrost-platform-plugin/tests/test_operator_streams.py:27` — `assert set(ALL_OPS) - set(READ_ONLY_OPS) == {"disconnect_all", "reconnect_all"}`
- **Impact**: Under D10, a future execution-adjacent op would be reachable from DEV/STG without anyone choosing it; the TD-21 boundary depends on reviewers remembering to extend a denylist.
- **Fix**: Make READ_ONLY_OPS an explicit literal allowlist and PROD_ONLY_OPS explicit; assert every op in ALL_OPS is in exactly one set.
- **Ratchet**: Test fails when ALL_OPS gains a member not classified in exactly one of READ_ONLY_OPS/PROD_ONLY_OPS; optionally a preflight warning on diffs adding to ALL_OPS.
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-platform-plugin

### TD-106

**P2 · market-data · Nightly trim (now with W3 archive) runs synchronously behind Dagster's 60s HTTP timeout; retries start overlapping trims and the recorded outcome is the retry's**

- **状态**：未开始
- **Claim**: The trim runs inline in POST /market/ingest/enqueue-slot with budgets totalling ~960s (240 job trim, 2x300 snapshot, 2x60 dated, statements up to 900s), while the Dagster client gives up at 60s and RetryPolicy fires a second trim during the first. The archive is safe under overlap (REPEATABLE READ + rowcount check makes the second pass error and roll back, 'never raises'), but Dagster's SUCCESS/FAILURE and logged result describe the retry, and overlapping passes contend on the same rows. From the first night with real rows to archive (~345k intraday option_snapshot rows/session at ~1,550 rows/s ≈ 220s) every first attempt will time out.
- **Measured**: MEASURED. ops_dagster.event_logs: 8 STEP_UP_FOR_RETRY for market_trim_job in 30 days, 2 FAILURE runs (09-09 883s, 09-10 821s). Run f70b9294 (10-01): STEP_START 02:15:07.43, retry 02:16:07.52 (exactly 60s), restart 02:17:10, success in 14s with trimmed: 0. /archive is empty; 10-06 retention_archive 0 rows on all passes.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/plugin_http.py:25` — `timeout: float = 60.0,`
  - `bifrost-research/src/bifrost_research/orchestration/market_slot_schedules.py:32` — `ENQUEUE_RETRY = RetryPolicy(max_retries=3, delay=60, backoff=Backoff.EXPONENTIAL)`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/ingest.py:225` — `result = enqueue_slot(`
  - `bifrost-platform-plugin-market-data/k8s/base/configmap-schedule.yaml:181` — `snapshot_budget_sec: 300`
- **Impact**: Dagster and Console show trim outcomes from the retry; a FAILURE run (as 09-09/09-10) does not mean the trim failed. Once archiving has real rows, every night runs a timed-out attempt plus duplicate, contended scans. No archived row is lost or duplicated.
- **Fix**: Single-flight async trim: endpoint takes pg_try_advisory_lock, returns 202 'already running' to a second caller, runs in a background task and writes its full result (including archive_runs) to ops_jobs; the Dagster asset polls, or uses a trim-specific client timeout larger than the budget sum.
- **Ratchet**: Plugin test: sum of trim budget keys < exported TRIM_CLIENT_TIMEOUT_SEC; cross-repo parity test that Research's market_trim asset uses it. Test: two concurrent enqueue_slot('trim') produce exactly one trim. Alert on any STEP_UP_FOR_RETRY for market_trim_job.
- 审批 跨仓库发版 · 代价 M · 风险 med · repos: bifrost-platform-plugin-market-data, bifrost-research

### TD-107

**P2 · market-data · Indexes declared for the six financials entity tables never reach a deployed DB (the migration returns early); live differs from fresh install**

- **状态**：未开始
- **Claim**: create_financials_entity_tables declares {table}_symbol_period_date and {table}_period_date_symbol for ratios, short_interest, short_volume, income_statement, balance_sheet and cash_flow, but is reachable only via migrate_stock_financials_split, which returns when stock_financials is already a view (true everywhere). period_date_symbol was written to stop the full scan behind 'who is held on the latest day' that blew a 120s budget; only short_volume has it (added by hand).
- **Measured**: MEASURED pg_indexes on bifrost_golden_source: the six tables have only pkey + filing_date (short_volume also period_date_symbol); 11 declared indexes absent. pg_stat_user_tables: ratios 4,197 seq scans / 278M tuples, balance_sheet 1,451 / 267M, short_volume (4.98 GB) 1,524 / 3.58B.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/schema/wave8_migrations.py:173` — `if relkind == "v":`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/schema/wave8_migrations.py:71` — `CREATE INDEX IF NOT EXISTS {table}_symbol_period_date`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/schema/wave8_migrations.py:84` — `CREATE INDEX IF NOT EXISTS {table}_period_date_symbol`
- **Impact**: Schema in code is not the schema in the DB (same class as option_oi_indexes_never_existed); the 'latest day held' latency fix exists on one of six tables.
- **Fix**: Remove symbol_period_date from code (redundant with PK prefix). Move period_date_symbol into an unconditional idempotent step on the superuser apply_ddl path (tables owned by postgres), built CONCURRENTLY with Owner DDL approval.
- **Ratchet**: CI applies plugin DDL to an empty Postgres and snapshots the index catalog; weekly read-only diff of the snapshot vs live pg_index in GS fails on any declared-but-absent index.
- 审批 改表 · 代价 M · 风险 med · repos: bifrost-platform-plugin-market-data

### TD-108

**P2 · research-control · Three hand-kept copies of the Dagster schedule roster have drifted; Console looks up a renamed corporate schedule and has no mapping for seven newer slots**

- **状态**：在做（10-06 还债第 C 路：调度与编排）
- **Claim**: The canonical roster is HUSBANDRY_SCHEDULE_JOBS in research. (1) Platform Console maps corporate/option-trades to market_corporate_trades_schedule, which no longer exists (now market_corporate_schedule), and has no mapping for fundamentals-market, ratios-market, intraday-chain, treasury, ticker-details, corporate-backfill, option-depth. (2) verify_husbandry_schedulers.sh asserts retired schedules and only WARNs when absent. (3) k8s/orchestration/README lists research_morning_prep_schedule, a wrong ratios cron, and 'Outside Dagster: IB only' though research-harness runs as a CronJob.
- **Measured**: MEASURED. ops_dagster.runs: market_corporate_trades_job last ran 2026-09-05; market_corporate_job 30 runs through 10-05. Live roster lists 40 schedules, none market_corporate_trades_schedule. Code ratios cron '10 5-8,11,14,20 * * *'. Console miss itself CODE-READ.
- **Evidence**:
  - `bifrost-platform/console/src/lib/market-data/slotScheduler.ts:35` — `corporate: 'market_corporate_trades_schedule',`
  - `bifrost-platform/console/src/lib/market-data/queuePulseModel.ts:41` — `corporate: 'market_corporate_trades_schedule',`
  - `bifrost-research/scripts/verify_husbandry_schedulers.sh:130` — `market_corporate_trades_schedule \`
  - `bifrost-research/k8s/orchestration/README.md:29` — `| `market_ratios_market_schedule` | `10 2-20/3 * * *` UTC |`
- **Impact**: Ops Console shows wrong state for the corporate slot and none for seven slots; the runbook script passes regardless; the README misleads the next agent.
- **Fix**: Research roster is the only source: /research/orchestration/status returns slot→schedule; Console drops SLOT_TO_DAGSTER_SCHEDULE/KIND_TO_DAGSTER_SCHEDULE literals. Rewrite verify_husbandry_schedulers.sh to iterate `dagster schedule list` and fail on missing/STOPPED. Generate or delete the README table.
- **Ratchet**: Research test: every *_schedule name in k8s README and scripts/*.sh exists in RESEARCH_SCHEDULES. Platform test against a fixture captured from /research/orchestration/status (or remove the maps).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform, bifrost-research

### TD-109

**P2 · ops-platform · PROD platform-api reads a deployed ops-context.yaml copy last synced 2026-08-24: about 33 spine decisions missing (D-Journal-Stores, D-Ops-Split, D-Wave-10..13)**

- **状态**：未开始
- **Claim**: bifrost-trade-infra/k8s/overlays/platform-prod/config/ops-context.yaml is mounted as ConfigMap bifrost-platform-config by PROD platform-api and platform-workers. It is a hand-kept copy of bifrost-platform config/ops-context.yaml and has not been synced since 0170331 (2026-08-24), so Ops Console on the cluster shows a spine ~6 weeks stale. platform CI's check_spine_catalog.sh does not compare the deployed copies.
- **Measured**: MEASURED by the ratchet-inventory pass: 17 decision ids in the PROD copy vs 50 on platform origin/main (diff 502/538 lines); a quick regex recount here gives 22 vs 55 '- id: D…' lines. Last commit touching the copy: 0170331 2026-08-24. Not adversarially re-verified; whether D10 state read by preflight comes from this copy was not checked (preflight reads the workspace spine).
- **Evidence**:
  - `bifrost-trade-infra/k8s/overlays/platform-prod/config/ops-context.yaml:41` — `headline: "TIBM W3 signed — STG read-path complete (D10 BLOCKED)"`
- **Impact**: Owner and agents reading the cluster Console see a stale decision set (missing D-Journal-Stores and later program decisions), undermining 'code → Console Governance catalogs → spine' priority.
- **Fix**: Generate the ConfigMap at build/deliver time from the platform repo's config/ops-context.yaml (delete the infra copy), or add a sync step plus CI parity check.
- **Ratchet**: CI check (ci-infra or ci-platform): deployed copies' decision-id set equals platform main's; better, the copy no longer exists.
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-trade-infra, bifrost-platform

### TD-80

**P3 · trade (round 1) · Core facade: an 85-method read/write StatusReader inside 'monitor.reader', alias import paths, verb drift**

- **状态**：在做（core 0.49.0 在 main、CI 绿；等 Owner 跑合并 Trade 发布）
- **验收**：core 0.49.0 的 `make test` 与 api 的 `make test` 通过；PROD `/api/account/health` 的 `core_version` 为 0.49.0
- **现在**：C1、C2-a 已上线。C2-b（`StatusReader` 门面只读、删 5 个写方法和 R4 别名）已备在分支 `td-batch/2026-10-04-lane-aj`。
- **下一步**：0.48.0 / 0.48.1 / 0.48.2 已被其他改动占用，C2-b 改号为 core 0.49.0，和 TD-51 一起发。（10-06）
- **Claim**: StatusReader, documented as 'Read status from Redis daemon IPC + PostgreSQL', has 85 methods, many of which write (instances, categories, watchlist, instrument classes). monitor.reader exports write functions, and *_write modules sit in the reader directory. Model analysis passes through 4 hops. Pure re-export modules (monitor/redis_url, config/startup, daemon_ib_edge, ib_probe_derived) give one symbol several import paths. Facade names differ from module names (list_strategy_instances wraps list_instances; list_dims_for_type wraps list_dims_by_type, and two different modules both define list_dims_by_type). get_ has 121 unique names and list_ has 20, with mixed create/insert/save/set/write/upsert verbs. ingestor and ingester are both used (92 vs 45 occurrences).
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/monitor/reader/common.py:33` — `"""Read status from Redis daemon IPC + PostgreSQL for business tables."""`
  - `bifrost-trade-core/src/bifrost_core/monitor/reader/__init__.py:1` — `"""Reader package: DB read/write facade.`
  - `bifrost-trade-core/src/bifrost_core/monitor/reader/common.py:418` — `result = template_config_module.list_dims_by_type(self._conn, dim_type)`
- **Impact**: Package names say nothing about domain or side effects, so a 'reader' change can write. Grep-based discovery misses the implementations.
- **Fix**: Split by domain (strategy/, portfolio/, market/, status/) into read and write modules, keeping monitor.reader as a re-export shim for one minor release. Make facade names match module names, adopt a verb table for new code, and delete the pure re-exports. Do TD-20 first.
- 审批 改公开接口 · 代价 L · 风险 med · repos: bifrost-trade-core, bifrost-trade-api, bifrost-trade-worker

### TD-110

**P3 · research-data · Stored IV features solve Black-Scholes at r=0 while the backtester uses treasury rates from two separate readers; further BS copies in gex and opex**

- **状态**：在做（10-06 还债第 B 路：Research 日期/日历/dbt/定价）
- **Claim**: iv_solver.solve_iv/bs_price/bs_delta default rate=0.0, and iv_solver.py:346/350/520/533, atm_iv.py:389, earnings_moves.py:54 and canonical_pnl omit rate. backtest/event_query._risk_free_rate and sim/chain.py each read raw_market.treasury_yield on their own; gex/exposure.approx_bs_gamma and opex_cycle/vanna_charm._norm_cdf are more BS copies. Features and backtests compute different IV/delta for the same contract. TD-42 fixed this class only in Trade.
- **Measured**: Inconclusive. Most stored IV since 08-05 is vendor_snapshot (4.26M rows); 19,435 Brent 'ok' rows (06-24..09-25) show median near-ATM put-call gap -2.3/-3.0 vol pts vs vendor -1.5/-2.3, partly carry/dividends. Copy drift CODE-READ; _risk_free_rate's own docstring admits research BS ran at r=0.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/atm_iv.py:389` — `iv, _status = solve_iv(spot_f, strike_f, max((exp - trade_date).days, 1) / 365.0, mid, right)`
  - `bifrost-research/src/bifrost_research/engines/backtest/event_query.py:685` — `def _risk_free_rate(conn: Any, on_or_before: date, cache: dict[date, float] | None = None) -> float:`
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:81` — `def approx_bs_gamma(`
- **Impact**: Matters where the Brent fallback fills IV30 and where backtest-selected strikes are compared with feature deltas.
- **Fix**: One research pricing module (bs_price/delta/gamma/vanna/charm, solve_iv) with keyword-required rate, plus one cached treasury reader; pass the rate in iv_solver and atm_iv.
- **Ratchet**: code-health grep metric: `def .*norm_cdf|def .*bs_(price|delta|gamma)|math.erf` outside the pricing module, baseline 0 after merge; rate keyword-required so a 0.0 default cannot return.
- 审批 不用批 · 代价 M · 风险 med · repos: bifrost-research

### TD-111

**P3 · research-data · dbt: the pass_count range generic test sits in the singular folder (errors when selected, never applied); key intermediates lack grain tests; nothing ties eval_date to the session**

- **状态**：在做（10-06 还债第 B 路：Research 日期/日历/dbt/定价）
- **Claim**: tests/assert_pass_count_range.sql defines a {% test %} block under the singular-test path; it errors whenever selected and no yml applies it, so pass_count has only warn-level anomaly checks. int_stock_daily_enriched (incremental on symbol, trade_date) and int_stock_crs have only not_null tests. mart_sepa_tier_options is absent from yml. No test checks eval_date/trade_date against the session, which let TD-87 through.
- **Measured**: MEASURED. ops_dbt.dbt_run_results: 14 error rows for assert_pass_count_range (08-21..09-28 manual full selections), never pass. Nightly builds run 82 tests, all pass, none on pass_count range or session. Grain clean today (1,656,685 = distinct; 382,026 = distinct).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/dbt/tests/assert_pass_count_range.sql:13` — `{% test assert_pass_count_range(model, column_name, min_value, max_value) %}`
  - `bifrost-research/src/bifrost_research/dbt/models/intermediate/_intermediate__models.yml:24` — `- name: int_stock_daily_enriched`
- **Impact**: A broken incremental merge or a SEPA date shift passes dbt build green.
- **Fix**: Move the macro to tests/generic/ and apply to pass_count (0-8, 0-11); add dbt_utils.unique_combination_of_columns on (symbol, trade_date) for both intermediates; add an expression/relationship test that eval_date/trade_date is a trading day and <= max(bar_date); document tier_options.
- **Ratchet**: CI check: `dbt ls --resource-type model` vs yml; fail on any model without a grain test.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-112

**P3 · research-data · option_surface_iv_daily upserts per (symbol, trade_date, expiry) and never deletes, so expiries a re-walk dropped keep their old smile**

- **状态**：在做（10-06 还债第 B 路：Research 日期/日历/dbt/定价）
- **Claim**: engines/volatility/surface.py writes with batch_upsert on (symbol, trade_date, expiry) and has no DELETE; expiries a later re-walk no longer produces keep the old fit beside the new one. Same class already fixed for signal_hit, gex, flow, pcr and max_pain.
- **Measured**: MEASURED. 122 rows in 98 of 12,635 (symbol, trade_date) groups are >1h older than their group's newest fit, up to 6d 21h; span 2026-07-14..09-03; only 10 are 0DTE.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/surface.py:588` — `conflict_keys=("symbol", "trade_date", "expiry"),`
- **Impact**: Small but wrong: surface reads for those days mix two fits; class stays open for any expiry-filter change.
- **Fix**: Delete-then-insert per (symbol, trade_date) in one transaction; one-off cleanup of the 122 rows (Research-owned).
- **Ratchet**: code-health metric listing batch_upsert targets whose conflict key is wider than (symbol, trade_date) with no DELETE in the module; fails on a new one without an allowlist comment.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-114

**P3 · flex-ib · raw_broker.commissions mixes two sign conventions: Flex writes cost as negative, the TWS/gateway path writes it as positive**

- **状态**：在做（core 0.50.0 在 main，随合并 Trade 发布上线；之后 Owner 跑 6 行存量改写）
- **验收**：GS 上跑 `db-steps.d/sql/2026-10-06-td114-commission-sign-dryrun.sql`：三个环境都上 0.50.0 且改写后需改写行数为 0（现在 6）
- **Claim**: Flex stores ibCommission as IB sends it (negative charge, positive rebate); the TWS commissionReport path writes IB API's positive cost into the same column and key. Flex re-imports overwrite to the Flex sign; TWS-only fills keep the opposite sign. No reader normalises (accounts_helpers.py:402-404 adds commission into period totals).
- **Measured**: MEASURED. Flex-backed: 435 negative, 15 positive (all rebates matching net_cash - proceeds to 4 dp), 32 NULL. TWS-only: 4 positive (~1.04-1.05), 0 negative, 33 NULL. 12 orphan commission rows. Reading TWS positives as costs relies on IB API docs.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/client/flex_client.py:551` — `commission = _f("ibCommission")`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1053` — `INSERT INTO {GOLDEN_COMMISSIONS} (exec_id, commission, currency, realized_pnl, yield_, yield_redemption_date)`
- **Impact**: Small amounts today, but per-trade cost and PnL reads including TWS-only fills get the cost sign backwards.
- **Fix**: Normalise at write time (keep Flex sign, negate TWS commissionReport value), backfill TWS-only rows, decide on the 12 orphans.
- **Ratchet**: Data-gaps/doctor SQL check: no exec_id whose commission sign disagrees with sign(net_cash - proceeds - taxes) on its Flex row; unit test on the TWS writer's sign.
- 审批 不用批 · 代价 S · 风险 med · repos: bifrost-trade-core

### TD-117

**P3 · flex-ib · 'Latest Flex date in DB' after an import is one run behind: read through FDW in the same transaction as the pre-import read**

- **状态**：观察中（到 10-07 06:30 ET 定时运行，看 after = data_to）
- **验收**：`select result->'result'->>'data_to', result->'result'->>'last_flex_date_after' from ops_jobs.job_flex_ingest where kind='flex-trades' order by id desc limit 1` 两值相等
- **Claim**: fetch_flex_trades_and_upsert_executions reads stats_before and stats_after on one Trade-DB connection with no commit between; brokerage.executions is a postgres_fdw view whose remote snapshot lasts the local transaction, so stats_after cannot see rows just written. The value reaches the UI.
- **Measured**: MEASURED in ops_jobs.job_flex_ingest: job 183 data_to 10-02 but after = 09-30; job 178 09-30 vs 09-28; job 172 09-28 vs 09-22. Each 'after' equals the previous run's data.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/trades.py:318` — `stats_after = get_flex_executions_stats(conn)`
  - `bifrost-trade-frontend/src/components/accounts/ExecutionImport.tsx:62` — `parts.push(`Latest Flex date in DB: ${r.last_flex_date_after}.`)`
- **Impact**: Operator is told the DB stops earlier than it does, inviting re-runs that burn IB's 1018 throttle.
- **Fix**: Read stats from GS raw_broker.executions_raw_flex on a fresh connection, or commit before stats_after.
- **Ratchet**: Integration test on real Postgres: after write_account_executions_to_db, last_flex_date_after = max(trade_date) written.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-flex-query

### TD-118

**P3 · market-data · option-refresh re-enumerates names with no listed options every run; its 7-day 'finished' lookback reads a table kept 48h**

- **状态**：在做（10-06 还债第 D 路：market-data）
- **Claim**: stalest_underlyings sorts never-enumerated names first, so names with no listed options are re-fetched at the head of every six-hourly batch forever. The 7-day finished-jobs guard feeds only the fresh ramp list (not the rotation) and is bounded by TRIM_KEEP_HOURS=48.
- **Measured**: MEASURED: 136 of 1,240 option_contract jobs in 48h wrote 0 rows; 17 names (ATLCL, ESQ, PLPC, NVR, NPK…) enqueued every run, always 0 rows.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/daily.py:2545` — `# Never enumerated sorts before any timestamp.`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/daily.py:638` — `AND created_at >= now() - interval '7 days'`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/scheduler/enqueue.py:165` — `TRIM_KEEP_HOURS = 48.0`
- **Impact**: ~12% of each 144-name rotation wasted on an uncapped plan; stated cycle time overstated; the 7-day comment is false.
- **Fix**: On zero contracts record a symbol_source_void ('no listed options', retry-after date) and exclude those names from fresh and stalest lists.
- **Ratchet**: Unit test: a name with a recent zero-row void is excluded from both lists; lint that no job_ingest lookback interval exceeds TRIM_KEEP_HOURS.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-119

**P3 · market-data · Schema-migrate Job and worker Deployments are applied in one `kubectl apply -k` with no ordering; a table-adding release fails the jobs that land in the DDL window**

- **状态**：未开始
- **Claim**: k8s/base lists job-wave8-schema-migrate next to the Deployments, and `make deploy` applies base before waiting on the Job. Ordering lives only in a skill procedure. Jobs in the 30-60s DDL window fail loudly (failed:<kind>, doctor-retryable), not silently.
- **Measured**: CODE-READ plus documented 09-24 incident (56 sec_filings_symbol jobs died during a 40s gap). Live Deployments have no initContainers.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/k8s/base/kustomization.yaml:23` — `- job-wave8-schema-migrate.yaml`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/db/schema_guard.py:24` — `def assert_no_legacy_schemas(conn: Any) -> None:`
- **Impact**: Operator toil and delayed slot data on each table-adding release; depends on a manual three-step order.
- **Fix**: Move the Job into its own kustomization; `make deploy` deletes the old Job, applies the migration, waits for complete, then applies base. A schema_version gate in workers is optional hardening.
- **Ratchet**: Test that `kustomize build k8s/base` contains no kind: Job and that the deploy target applies the migration kustomization and waits before base.
- 审批 改表 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-120

**P3 · research-control · Dagster Deployments are applied by hand outside Argo; a second, unmounted dagster_instance.yaml lacks the run_monitoring that catches zombie runs**

- **状态**：未开始
- **Claim**: Argo app bifrost-research excludes orchestration/**, and pipeline-build-research-dagster only builds; nothing checks the -dagster tag matches the release pin. k8s/orchestration/dagster_instance.yaml is an unreferenced second instance config missing the run_monitoring block added after trading_day sat STARTED 20.5h on 09-08.
- **Measured**: MEASURED. Argo exclude '{orchestration/**,dbt/Dockerfile,**/_archived/**,_archived/**}'. kubectl diff of dagster.yaml rc=0 today; daemon and webserver run 0.175.0-dagster = pin. dagster_instance.yaml lacks the 15-line run_monitoring block and has no references.
- **Evidence**:
  - `bifrost-research/k8s/orchestration/dagster_instance.yaml:1` — `# Mounted as $DAGSTER_HOME/dagster.yaml — Postgres instance storage on Golden Source.`
  - `bifrost-research/k8s/orchestration/dagster.yaml:50` — `run_monitoring:`
  - `bifrost-trade-infra/k8s/cicd/tekton/pipeline-deliver-research.yaml:113` — `# base = Research API + CronJob engines. The Dagster image is a`
- **Impact**: Drift risk only today, but API and daemon on different code versions would write features with a different engine than the API reads; the duplicate file can undo a hard-won fix.
- **Fix**: Delete dagster_instance.yaml. Add a verify step asserting dagster-daemon image == '<pin>-dagster', or bring orchestration/** under Argo with image ignoreDifferences.
- **Ratchet**: verify-research assertion on the daemon tag (fails deliver); test that k8s/ holds exactly one dagster instance config.
- 审批 跨仓库发版 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-infra

### TD-121

**P3 · research-control · Research pods read bifrost-research-secrets once at start (optional: true); the OpenAI key rotation helper restarts only research-api**

- **状态**：未开始
- **Claim**: research-api, research-mcp, dagster-daemon and dagster-webserver envFrom bifrost-research-secrets with optional: true. sync_openai_secret.sh patches the key and restarts only deployment/research-api, so the daemon (scheduled LLM agents) and MCP keep the old key until the next release. No rotation helper exists for analytics_writer. (DB rotation of 'bifrost' does not touch these pods; infra bifrost-password-rotate.sh already derives holder Deployments.)
- **Measured**: CODE-READ for cluster pods; secret key names checked live (OPENAI_API_KEY, DEEPSEEK_API_KEY, ANALYTICS_PG_PASSWORD present).
- **Evidence**:
  - `bifrost-research/scripts/sync_openai_secret.sh:41` — `kubectl -n "$NS" rollout restart deployment/research-api`
  - `bifrost-research/k8s/orchestration/dagster.yaml:98` — `- secretRef:`
- **Impact**: After an OpenAI/DeepSeek key rotation, scheduled agents and Copilot via MCP fail until a manual restart; optional: true lets pods start without credentials instead of failing fast.
- **Fix**: Restart every Deployment in namespace research that mounts the secret (derive the list as infra holder_deployments() does); add a checksum/secret annotation or reloader; drop optional: true for required keys.
- **Ratchet**: Lint over k8s/: every Deployment envFrom-ing bifrost-research-secrets carries the checksum annotation and none mark required keys optional; grep check that rotation helpers never hard-code one deployment.
- 审批 安全/凭据（要你批） · 代价 S · 风险 low · repos: bifrost-research

### TD-122

**P3 · flex-ib · The IB Gateway image is built on the Mac and imported to nodes with ctr under a reused tag: no registry, no digest, no recorded source SHA**

- **状态**：未开始
- **Claim**: deployment.yaml runs bifrost-platform-plugin-ib-gateway:0.3.0 with IfNotPresent; the tag exists only in each node's containerd and the repo has no build pipeline (unlike flex-query). Different code can run under the same version and nothing reports which commit is live.
- **Measured**: MEASURED: live pod on ubt-k3s-04 runs a bare tag with local imageID sha256:cd51d656…; flex-query uses 192.168.10.73:30500/bifrost-flex-query:0.9.0; no k8s/cicd in the repo.
- **Evidence**:
  - `bifrost-platform-plugin/k8s/ib-gateway/base/deployment.yaml:22` — `image: bifrost-platform-plugin-ib-gateway:0.3.0`
  - `bifrost-platform-plugin/k8s/ib-gateway/base/deployment.yaml:23` — `imagePullPolicy: IfNotPresent`
- **Impact**: The process holding both TWS connections and redis-ib writes is the least reproducible deploy; rollback and audit depend on one laptop.
- **Fix**: Tekton build to the in-cluster registry (copy flex-query's pipeline-build.yaml), pin by digest, expose git SHA in the health hash.
- **Ratchet**: code-health metric: manifests whose image lacks registry host or digest = 0 for plugin repos; preflight warning on `ctr images import`.
- 审批 跨仓库发版 · 代价 M · 风险 med · repos: bifrost-platform-plugin, bifrost-trade-infra

### TD-123

**P3 · research-control · About 19 deployed research-api routes have no caller in frontend, platform, trade-api or MCP, including manual POST triggers that run engine code outside Dagster**

- **状态**：未开始
- **Claim**: Uncalled GETs: /analytics/sepa/technical-filter, /analytics/sepa/screening-ranked, /research/sepa/candidates, /research/volatility/surface, /research/forecast/{hourly,settlement,backtest}, /research/backtest/regime-stats, /research/canonical-pnl/coverage. Uncalled POSTs: forecast/terrain/compute, forecast/sessions/compute, forecast/settle, event-radar/run, events/ingest, backtest/aggregate, journal/memory/distill, agents/digest/run, agents/weekly-policy/run, hypothesis/{id}/retire. Most POSTs run engine code synchronously in the API pod with no run record or failure alert, and distill/digest can race their scheduled runs.
- **Measured**: MEASURED: live /openapi.json (208 path×methods) vs git grep on origin/main of frontend, platform, trade-api, infra and research mcp/copilot, with manual re-check. Callers outside these repos (Hermes, curl) not checked.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/api/wave4.py:1191` — `@router.post("/forecast/settle", dependencies=[Depends(require_owner)])`
  - `bifrost-research/src/bifrost_research/api/agents.py:80` — `@agents_router.post("/digest/run", dependencies=[Depends(require_owner)])`
  - `bifrost-research/src/bifrost_research/api/journal.py:327` — `@router.post("/memory/distill")`
  - `bifrost-research/src/bifrost_research/api/sepa.py:153` — `@router.get("/screening-ranked")`
- **Impact**: Extra surface to secure and test after the 0.163-0.168 auth work; a second, unobserved write path beside Dagster.
- **Fix**: Delete uncalled read routes and calculator POSTs; move agent/distill triggers to 'launch the Dagster job' via GraphQL; follow trade-api's TD-40 retirement pattern (test_retired_routes.py).
- **Ratchet**: Port the TD-40 route-caller check: CI diffs app.routes against a committed callers manifest; test that no research-api route imports engines.*.entry run functions directly.
- 审批 改公开接口 · 代价 M · 风险 low · repos: bifrost-research

### TD-124

**P3 · research-control · 39 permanently suspended CronJobs (25 research, 14 market-data, plus an orphan pinned to 0.10.0) are still deployed and re-pinned every release; research ones carry a stale 26-name watchlist and the verify script contradicts the one active CronJob**

- **状态**：未开始
- **Claim**: Since the Dagster migration all engine CronJobs are suspend: true but still applied (research by Argo auto-sync; market-data via k8s/base), and each release rewrites their image tags. Research manifests hardcode RESEARCH_WATCHLIST to 26 names including SATS (renamed ECHO); unsuspending one would double a writer on the wrong universe. verify_husbandry_schedulers.sh requires research-harness suspended while it is suspend: false, so the landing check can only fail. market-data k8s/cronjob-option-backfill.yaml sits outside kustomization at 0.10.0; each slot cron is written in three places.
- **Measured**: MEASURED. research: 25 CronJobs SUSPEND=True (17 manifest files, 12 set RESEARCH_WATCHLIST), harness active; all pinned 0.175.0. plugin-market-data: 14 CronJobs SUSPEND=True, last scheduled 08-29/30, image 0.77.0. Market-data skill says 'Do not unsuspend'.
- **Evidence**:
  - `bifrost-research/k8s/engines/cronjob-scan.yaml:67` — `value: "SPY,QQQ,IWM,SPX,NVDA,AAPL,META,GOOG,AMZN,MSFT,TSLA,PLTR,MU,MRVL,ANET,CAVA,CBRS,DAVE,DDOG,ECHO,HIMS,NBIS,NNE,RKLB,SATS,SPCX"`
  - `bifrost-research/k8s/engines/cronjob-harness.yaml:17` — `suspend: false`
  - `bifrost-research/scripts/verify_husbandry_schedulers.sh:67` — `research-harness \`
  - `bifrost-platform-plugin-market-data/k8s/base/cronjob-daily.yaml:25` — `# last three forever: these have all been suspended since 2026-08-29`
- **Impact**: Release churn and review noise; a one-line footgun that doubles writers; the documented landing check is permanently red so nobody runs it.
- **Fix**: Delete suspended CronJob manifests in both repos (keep research-harness or move it into Dagster) and the orphan backfill CronJob; flip the verify script's CronJob block to 'must not exist'. Deletes in Argo-pruned paths need Owner sign-off.
- **Ratchet**: CI check: `kustomize build` contains no kind: CronJob unless allowlisted with a reason (research baseline 26 → 1, market-data 14 → 0); test that no k8s manifest sets RESEARCH_WATCHLIST.
- 审批 删除（要你批） · 代价 S · 风险 low · repos: bifrost-research, bifrost-platform-plugin-market-data

### TD-125

**P3 · flex-ib · Retired IB topology still referenced: TIBM-era verify scripts at the top of scripts/, flex_ops compat SQL for a schema that no longer exists**

- **状态**：未开始
- **Claim**: Five plugin scripts reference the retired ib-operator/ib-market-gateway/ib-account-agent StatefulSets, plus per-wave verify-trade-ib-w{1,2,3}-* scripts, although TIBM rollout scripts already moved to scripts/archive. The flex repo keeps golden_source_flex_ops_compat_views.sql and drop_trade_flex_ops_legacy.sql for a flex_ops schema that does not exist. Current-gateway verify scripts (verify-ib-gateway*.sh, verify-redis-ib.sh) are live.
- **Measured**: MEASURED: no sts/deploy named ib-operator/ib-market-gateway/ib-account-agent; pg_namespace has no flex_ops.
- **Evidence**:
  - `bifrost-platform-plugin/scripts/verify-trade-cutover.sh:17` — `LEGACY_STS=(ib-market-gateway ib-account-agent ib-operator)`
- **Impact**: Readers and agents treat these as live procedures.
- **Fix**: Move TIBM-wave and cutover verify scripts with Makefile targets into scripts/archive; delete the two flex_ops SQL files and their CLAUDE.md mention on Owner approval; trade-api service rows are retargeted under TD-104.
- **Ratchet**: Per-repo CI grep ratchet: references to ib-operator/ib-market-gateway/ib-account-agent outside scripts/archive, falling baseline.
- 审批 删除（要你批） · 代价 S · 风险 low · repos: bifrost-platform-plugin, bifrost-platform-plugin-flex-query, bifrost-trade-api

### TD-128

**P3 · research-data · Pine signal rows mix adjustment bases: nightly runs rewrite only the last ~10 sessions on today's adjusted bars, older rows stay on the basis of their last full rebuild**

- **状态**：未开始（归 Pine 线程）
- **Claim**: The Pine build runs scripts on raw_market.stock_daily adjusted closes. Nightly (incremental) runs replace only the last ~10 sessions; a split or large dividend re-adjusts the whole history, so after one the older rows of that name were computed on a different price basis than the new ones until a script's next full rebuild (which happens only when its source changes or on a manual --full).
- **Measured**: Design reading (thread B, 2026-10-06); last full rebuild 2026-10-06 04:17–04:25 UTC (8 scripts, about 7 minutes with CHUNK 25).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/pine/build.py:210` — `since = None if rebuild else end - timedelta(...)`
  - `bifrost-research/src/bifrost_research/engines/pine/build.py:226` — `_write(..., replace_from=since, ...)`
- **Impact**: Signal dates on names with corporate actions can disagree with what the script would print today; signal-stats and backtests read the stale ones.
- **Fix**: A weekly full rebuild (weekend Dagster schedule, CHUNK 25 because the runner blocks /health on 100-name full-history batches), or a nightly per-symbol full rebuild of names with a split in the last N days.
- **Ratchet**: Dagster metadata records each script's last full rebuild; an alert when it is older than 8 days.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-129

**P3 · research-data · The event backtest picks option legs from option_daily only; since mid-August 2026 it keeps ~10 strikes a side, so a target delta silently lands on the nearest strike that is left**

- **状态**：未开始（归 Pine 线程）
- **Claim**: `_pick_option` reads candidate contracts from raw_market.option_daily. Since mid-August 2026 option_daily keeps about ten strikes either side of spot per expiry, so a 20–30 delta leg 30–45 days out is usually missing and the nearest remaining strike (often 35–40 delta) is priced instead, with no skip or flag. The simulator (0.175.0) and the suggestion ledger (0.174.1) fill from the 16:00 option_snapshot and skip off-target picks; the event backtest does not.
- **Measured**: Thread B 2026-10-06 on the simulator path: without the fill a 20-delta SPY put picked −0.35, QQQ −0.38 (2026-08-17..10-02); with it −0.20 ± 0.003. The event backtest path shares the option_daily source.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/backtest/event_query.py:781` — `_pick_option`
  - `bifrost-research/src/bifrost_research/engines/backtest/event_query.py:823` — `FROM raw_market.option_daily`
- **Impact**: Event backtests of delta-targeted structures after mid-August run a different trade than the template names.
- **Fix**: Read the snapshot day bars where option_daily lacks the contract (walk.snapshot_day_bars) and skip legs further than 0.05 from the target delta, counting the skip.
- **Ratchet**: A test with an option_daily chain thinned to ATM ±10 strikes that asserts either the target delta within 0.05 or an off-target skip.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-130

**P1 · ops-control · ops-autopilot acts on the shared cluster's data layer from the Owner's laptop (local bdev platform-api, role all); the in-cluster STG/PROD autopilots idle on an empty checklist, and each of the three keeps its own throttle**

- **状态**：未开始（要你批）。依赖：本机这份先不停（Owner 2026-10-06）——停了就没有任何一份 autopilot 在动手；等 PROD 接上真实清单之后再停本机。
- **Claim**: Three platform-api processes run the patrol autopilot loop against the one k3s cluster: platform-workers in bifrost-platform-stg and bifrost-platform-prod (PLATFORM_ROLE=workers) and the Owner's local bdev platform-api, where PLATFORM_ROLE is unset and therefore `all`. Only the local one reads the real checklist; the in-cluster ones idle on an empty checklist (Owner 2026-09-22: leave as is). So the actions on data/minio and the backups came from a dev laptop: repair_cnpg_wal_store every 15 minutes from 10-05 19:30 to 10-06 02:00 (all failed), a rollout restart of deploy/minio plus an on-demand Backup at 10-06 04:45, another restart at 05:15. The "same target not twice in 24h" throttle is kept per process.
- **Measured**: MEASURED 2026-10-06. Audit log of the local platform-api (MCP bifrost-platform → http://127.0.0.1:8780, get_audit_log) lists those actions; `curl 127.0.0.1:8780/health` → role all, background_loops true; kubectl: platform-workers 1 replica with PLATFORM_ROLE=workers in both namespaces. Again at 2026-10-06 16:15:07 UTC (12:15 New York, market hours): the local autopilot ran repair_cnpg_wal_store, deleted the failed Backup bifrost-postgres-ondemand-20261006-044532 and started bifrost-postgres-ondemand-20261006-161507, a full base backup.
- **Evidence**:
  - `bifrost-platform/api/internal/config/role.go:33` — `PLATFORM_ROLE`; unset or unknown means all
  - `bifrost-platform/api/internal/server/server.go` — `role.RunsWorkers()` gates the patrol, ibgateway auto-repair and data-clone loops
  - `bifrost-platform/config/patrol-skills/ops-autopilot.yaml` — every 15 minutes; tools include rollout_restart_deployment and trigger_cnpg_backup
- **Impact**: The process that restarts production backup infrastructure and starts backups is the least controlled one: it sleeps with the laptop, runs whatever is in the shared checkout and restarts on every bdev change. Several copies can each restart or back up the same target.
- **Fix**: In this order, so that exactly one autopilot acts at every moment: (1) dry look at what the PROD platform-workers autopilot would trigger with the real checklist; (2) give it the real checklist and confirm in the PROD audit log that it acts; (3) only then `PLATFORM_ROLE=api` in bifrost-platform/.env on the Owner's Mac and `bdev restart platform-api`; (4) STG observe only (a switch such as `PATROL_AUTOPILOT=off`, or report-only). Stopping the local one first leaves zero acting autopilots, a failure nobody notices.
- **Ratchet**: Outside the cluster, background loops start only with an explicit opt-in (for example `PLATFORM_ALLOW_LOCAL_LOOPS=1`); a test on the role default.
- **验收**: `curl -s 127.0.0.1:8780/health` shows background_loops false; the PROD audit log shows the autopilot's actions and the local one shows none.
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-platform

### TD-131

**P2 · ops-control · repair_cnpg_wal_store deletes failed Backup CRs, erasing the record of failed backups**

- **状态**：未开始（要你批）
- **Claim**: RepairPostgresWalStore calls deleteStuckBackupCRs, which deletes every bifrost-postgres-* Backup in phase failed or walArchivingFailing before it starts an on-demand Backup. CloudNativePG itself only deletes completed backups that are no longer in the object-store catalog. The failed 10-03 and 10-04 03:00 backups and the failed 10-03 manual one were gone from the cluster within hours; only Prometheus and a MinIO trace kept the evidence. On 10-06 16:15 UTC it deleted bifrost-postgres-ondemand-20261006-044532 (stopped on the Owner's request during the MinIO cutover) the same way. Independent of TD-130: can be fixed while the local autopilot is still the acting one.
- **Measured**: MEASURED 2026-10-06: the Backup CRs of those three runs are absent; CNPG v1.27.4 `pkg/management/postgres/backup.go` deleteBackupsNotInCatalog skips every phase but completed.
- **Evidence**:
  - `bifrost-platform/api/internal/cluster/postgres_wal_repair.go` — `pickStuckBackupNames`, `deleteStuckBackupCRs`
- **Impact**: Failure history for postmortems exists only in metrics; whoever looks at the cluster after the repair ran sees no failed backup.
- **Fix**: Stop deleting failed Backups; a separate sweep removes failed Backup CRs older than 30 days.
- **Ratchet**: A test that RepairPostgresWalStore issues no delete for a failed Backup.
- **验收**: After a failed backup and a repair run, `kubectl -n data get backups` still lists the failed one.
- 审批 要你批 · 代价 S · 风险 low · repos: bifrost-platform

### TD-132

**P2 · ops-control · bifrost-platform a332cff (checks and WAL repair aware of the NAS MinIO) is on main but not released to STG/PROD**

- **状态**：在做（下一步：Owner 批发布，STG 后 PROD）
- **Claim**: Since the MinIO cutover (infra 1ee0ac2) the in-cluster Console reports "MinIO backup … scaled to zero" and "WAL archive … MinIO not ready" (degraded) for a healthy store, and the in-cluster repair tool would rollout-restart the 0-replica deploy/minio. a332cff reads Service data/minio, checks the external MinIO's /minio/health/cluster and never touches deploy/minio for an external MinIO.
- **Measured**: Local platform-api against the cluster after a332cff: MinIO backup ok "MinIO @ 192.168.10.20:9000 healthy", WAL archive ok (both degraded before). Last STG and PROD builds were a6794c4, bifrost-ui unchanged since: the release ships only a332cff.
- **Evidence**:
  - `bifrost-platform/api/internal/cluster/minio_backend.go` — `resolveMinioBackend`
  - `bifrost-platform/api/internal/cluster/postgres_wal_repair.go` — external branch of `RepairPostgresWalStore`
- **Fix**: Run bifrost-deliver-platform, then bifrost-deliver-platform-prod.
- **Ratchet**: `minio_backend_test.go` TestRepairWithUnhealthyExternalMinioLeavesDeploymentAlone (fails on the old code).
- **验收**: STG and PROD `GET /api/v1/cluster/postgres` → minio.id minio-backup-external, reachability ok; the clone-platform result commit is a332cff or later.
- 审批 发布（要你批） · 代价 S · 风险 low · repos: bifrost-platform

### TD-133

**P3 · data · Leftovers of the in-cluster MinIO after the move to the NAS (deploy/minio at 0, its PVC/PV, an empty EndpointSlice, the backup-retry CronJob)**

- **状态**：观察中（到 10-13，看每天 03:00 的备份都 completed、BifrostMinIONas* 没有告警）
- **Claim**: Kept for a week as the rollback path: deploy/minio (replicas 0 on purpose), PVC data/minio-data and PV pvc-871b4689-… (nfs-hot; its directory is the live data directory of the NAS MinIO), the controller's empty EndpointSlice minio-wv44q, the CronJob data/backup-retry (only needed while backups failed on NFS), and the data directory still under the provisioner's /volume1/k3s-hot path.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/minio/deployment.yaml` — replicas 0
  - `bifrost-trade-infra/k8s/data/backup-retry.yaml`
  - `bifrost-trade-infra/k8s/data/minio/nas/README.md` — "After a week of good backups"
- **Fix**: After 10-13: delete deploy/minio and backup-retry; delete the PVC and PV objects only (reclaim policy Retain, archiveOnDelete false: the directory stays — check again first); move the directory to its own share by a rename inside /volume1 and update the compose volume path (Owner, sudo); delete minio-wv44q.
- **Ratchet**: None new: BifrostMinIONasDown / DriveOffline / SpaceLow cover the store itself.
- **验收**: `kubectl -n data get deploy,pvc,cronjob | grep -E 'minio|backup-retry'` is empty; the NAS MinIO lists 272+ GiB and the next 03:00 backup completes.
- 审批 要你批 · 代价 S · 风险 med · repos: bifrost-trade-infra

### TD-134

**P2 · data · WAL is ~19.5 GiB/day (4.2 GiB compressed) because checkpoints run every 5 minutes without wal_compression**

- **状态**：未开始（要你批）
- **Claim**: bifrost-postgres runs with checkpoint_timeout 300 s, max_wal_size 1024 MB and wal_compression off. Each checkpoint makes the next change to every page write a full page image, so WAL is dominated by full pages. Archived WAL is 129 of the 272 GiB backup bucket.
- **Measured**: MEASURED 2026-10-06: cnpg_collector_wal_bytes 7-day average 19.48 GiB/day; 1,986 timed checkpoints in 7 days; full-page-image byte share upper bound 0.98 (8 KiB per FPI).
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/cluster.yaml` — spec.postgresql.parameters (no checkpoint or wal_compression settings)
- **Impact**: Backup storage and the WAL replay after a restore grow with it; the 30-day backup bucket is about 300 GiB and rising.
- **Fix**: checkpoint_timeout 15min, max_wal_size 4GB, wal_compression lz4 (reload, no restart); measure WAL per day for a week. Cost: crash recovery replays more WAL (about a minute instead of seconds).
- **Ratchet**: An alert when WAL per day goes above the new baseline by a margin.
- **验收**: A week after the change, cnpg_collector_wal_bytes per day is at most half of 19.48 GiB.
- 审批 要你批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-135

**P3 · data · Native barmanObjectStore backups are removed in CloudNativePG 1.30; the Barman Cloud Plugin that replaces them needs cert-manager, which the cluster does not have**

- **状态**：未开始（要你批：新依赖）
- **Claim**: Applying the Cluster on 10-06 printed "Native support for Barman Cloud backups and recovery is deprecated and will be completely removed in CloudNativePG 1.30.0". The operator is 1.27.4. The plugin needs cert-manager; no cert-manager namespace or CRDs exist.
- **Evidence**:
  - `bifrost-trade-infra/k8s/data/cluster.yaml` — spec.backup.barmanObjectStore
  - `bifrost-trade-infra/k8s/system/cnpg-operator/kustomization.yaml` — operator version pin
- **Impact**: An operator upgrade past 1.29 would stop WAL archiving and backups.
- **Fix**: Before that upgrade: install cert-manager, deploy plugin-barman-cloud, move the Cluster to an ObjectStore plus plugin configuration, verify a backup and a restore drill.
- **Ratchet**: install-cnpg-operator.sh refuses a version of 1.30 or later while the Cluster still uses barmanObjectStore.
- **验收**: A completed Backup with method plugin and a restore drill that passes.
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-trade-infra

### TD-136

**P2 · research-data · GEX writes levels for an expiry whose open interest is all zero: walls and zero_gamma fall on an arbitrary strike, 1,534 rows on 496 names, and terrain and scan copy them**

- **状态**：观察中（到 10-08，看 10-07 与 10-08 两次夜批后「验收」的 SQL 仍为 0）
- **进展（10-06，Owner 批「现在修」）**：research 0.185.0（a83abd1，pin 16b0f67）上线：`exposure.has_gamma_exposure`，没有 gamma 暴露的到期日不写分布也不写 levels（判定用两面 wall 的 gex 都为 0，覆盖 1,182 行零 OI 和 352 行「只有远离现价的行权价、gamma 舍入为 0」）；整天都没有暴露的名字清空当天并报 `No gamma exposure`；盘中 GEX 同样不写。Dagster 0.185.0-dagster 16:50 UTC apply。回填 Job `research-gex-zero-exposure-purge-0185`（`engines/gex/zero_exposure_purge`）：删 levels 1,534 行、分布 24,413 行，terrain 重算 104 行，scan 重算 145 行。核对：退化 levels 剩 0；levels 总数 70,974 → 69,440；没有 terrain 行再读到退化行；145 行 scan 的 regime 与 pin_score 全部与 terrain 一致。备份 `~/bifrost-backups/golden-source/2026-10-06_gex-zero-exposure-td136/`。防线：`tests/engines/test_gex_zero_exposure.py`（签收时登记进 RATCHETS.md）。后续：TD-157（单边）。
- **Claim**: compute_gex_levels takes the call wall with max(call_gex) and the put wall with min(put_gex); when every contract of an expiry has open_interest 0, every gex is 0, both walls become the first strike in the distribution, no sign flip exists, and zero_gamma falls back to the strike nearest spot. The row is written with total_net_gex 0 and call/put_wall_gex 0. Same class as max pain's zero-OI rows, fixed in research 0.155.0 (the expiry is skipped); GEX was not covered. Found on 10-06 checking CTVA after its 10-01 spin-off: the new standard series listed on 10-02 with OI 0 produced three such rows (walls and zero_gamma all 12.5, spot 11.92).
- **Measured**: MEASURED 10-06, read-only on Golden Source: features.option_metric_gex_levels_daily has 1,534 rows with total_net_gex = 0, all with call_wall_gex = put_wall_gex = 0; 1,186 name-sessions, 496 names, 07-06 → 10-05; still written nightly (09-28: 32, 09-29: 25, 09-30: 11, 10-01: 376, 10-02: 52, 10-05: 34).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:192` — `call_wall = max(distribution, key=lambda r: float(r.get("call_gex") or 0))`
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:220` — zero_gamma fallback to the strike nearest spot
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:560` — every expiry in by_exp is written, no zero-OI guard
  - `bifrost-research/src/bifrost_research/engines/forecast/terrain.py:182` — walls_reach_spot reads these walls; CTVA 10-02 terrain gamma zone 12.44–12.56 and scan gex_notional 0 came from them
- **Impact**: Levels pages, terrain (pin score, gamma zone, regime) and scan read a wall and a zero-gamma level where no open interest exists. One night after a corporate action (10-01: 376 rows) touches many names at once.
- **Fix**: In compute_gex_for_symbol skip an expiry whose summed open interest is 0 (write no distribution and no levels row), as max_pain does since 0.155.0; the session is already replaced delete-then-write, so the next recompute clears it. One-off: back up and delete the 1,534 rows, then recompute terrain and scan on the affected name-sessions (pattern: engines/adjusted_contract_purge --max-pain).
- **Ratchet**: A test that compute_gex_for_symbol writes nothing for an expiry whose contracts all have open_interest 0; a nightly check that features.option_metric_gex_levels_daily has no row with total_net_gex = 0 and both wall gex = 0.
- **验收**: `SELECT count(*) FROM features.option_metric_gex_levels_daily WHERE total_net_gex = 0 AND COALESCE(call_wall_gex,0) = 0 AND COALESCE(put_wall_gex,0) = 0` returns 0 after two nightly runs.
- 审批 已批（Owner 10-06）· 代价 S · 风险 low · repos: bifrost-research

### TD-137

**P1 · trade-data · The daily snapshot capture locks an account's intraday book into the day (first write wins, no freshness test) and account_nav_daily stores no margin-pressure fields**

- **状态**：在做（代码就绪，已推为分支、未合并：core `fix/w4-snapshot-stale-accounts` = 9013ba2（0.51.0，基于 0.50.0；lint 过、单测 1287 过、test-db 100 过）· infra `fix/w4-snapshot-evening-all` = deaa2ca。**接手步骤**：① 等 Code Refactor 那批 Trade 发布（core 0.49.0 / 0.50.0 + api 0.10.0）在 PROD 通过——它会直接告诉 Owner；② 把 core 分支 rebase 到最新 main，若 0.51.0 已被占用就改下一个号（pyproject、DATABASE.md change log、snapshot_ddl.py / daily.py 注释与两个测试文件里的版本），重跑 `make lint && make test && make test-db`；③ Owner 逐项确认 PROD DDL：`account_nav_daily` ADD COLUMN IF NOT EXISTS `cushion` / `excess_liquidity` / `maint_margin_req`（double precision、可空、无默认、不回填），无自加项、无不可逆步骤，行为变化见本条 Fix；④ `release.sh window && git push` core main，Owner 跑 release.sh stg → prod（单独一批）；**每个环境在当天 16:20 ET 前跑完 db-init**，否则 capture 因缺列失败、丢一整天；⑤ api 镜像带上新 core 之后再合并推 infra 分支并同步 bifrost-stg / bifrost-prod（旧镜像跑晚间 `all` 会重读 attribution 而在 enrich 前退出）；⑥ 次日核 `account_nav_daily` 的 `account_updated_at ≥ 收盘` 与三列非空，写验收结果）
- **验收**：每个 Trade 库（`bifrost_dev` / `bifrost_stg` / `bifrost_prod`）发布后的 session：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_prod -X -At -c "SELECT count(*) FROM account_nav_daily WHERE snapshot_date >= '<发布日>' AND account_updated_at < (snapshot_date + time '16:00') AT TIME ZONE 'America/New_York'"` 为 0（NYSE 提前收盘日按提前收盘时间比），且 `SELECT snapshot_date, count(cushion), count(*) FROM account_nav_daily GROUP BY 1 ORDER BY 1 DESC LIMIT 3` 最新一天 count(cushion) = count(*)
- **现在**：Owner 10-06 定：B1.b (a) 跳过陈旧账户、晚间补抓，不加 stale 列；B1.c (a) 加三列，不存整份 summary_extra。修复已 rebase 到 core 0.50.0 并改号 0.51.0：lint 通过；单测 1287 passed（跳过已知的本机 py_vollib 失败）；test-db 100 passed；kustomize 三环境可渲染。10-06 的 16:20 抓取仍按 0.48.2 跑。
- **下一步**：Code Refactor 那批 PROD 通过（它会通知）→ 推 core 9013ba2 / infra deaa2ca → `release.sh stg` / `prod`（要你批）→ 每环境先跑 db-init 建列再换镜像 → 同步 bifrost-stg / bifrost-prod。20:05–20:40 UTC 不起发布。在此之前不推 core / api / infra / frontend 的 main。
- **Claim**: capture() inserts NAV and positions with ON CONFLICT DO NOTHING, so the first run of a date wins, and it copies every brokerage.account row with no freshness test. The secondary account's TWS logs off at 11:00 New York every weekday (TWS Auto log off), so the 16:20 capture stores that account's intraday values as the day's; the 20:30 job only enriches marks and Greeks. An account last synced 2026-05-11 (U17113214) still gets a NAV row every day. Separately, account_nav_daily has no column for Cushion / ExcessLiquidity / MaintMarginReq although brokerage.account.summary_extra carries all three keys for all three accounts; this history only accumulates forward, so every night without the columns is a day that cannot be refilled (SNAPSHOT-SPEC §1.1 pressure history).
- **Measured**: MEASURED 10-06 on the CNPG replica: 10-05 rows for U8829175 in DEV and STG have account_updated_at and positions_updated_at 15:48 UTC (11:48 New York, intraday); the PROD 10-05 row is a manual re-capture by another session at 22:48 UTC. First night 10-05: DEV 31 / STG 30 / PROD 31 position rows, NAV 3 rows per database. summary_extra: the three keys present on all three accounts (key names only were read).
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/portfolio/snapshot/daily.py:174` — `SELECT %s, account_id, net_liquidation, total_cash, buying_power, updated_at`
  - `bifrost-trade-core/src/bifrost_core/portfolio/snapshot/daily.py:177` — `ON CONFLICT (snapshot_date, account_id) DO NOTHING`
  - `bifrost-trade-core/src/bifrost_core/portfolio/snapshot/daily.py:187` — `ON CONFLICT ON CONSTRAINT position_snapshot_daily_uq DO NOTHING`
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/snapshot_ddl.py:69` — `buying_power double precision,`
  - `bifrost-trade-infra/k8s/overlays/prod/position-snapshot.cronjob.yaml:13` — `schedule: "20 16 * * 1-5"`
  - `bifrost-trade-infra/k8s/overlays/prod/position-snapshot.cronjob.yaml:113` — `command: [python, -m, bifrost_core.portfolio.snapshot, enrich]`
- **Impact**: P&L Explain, the Performance return basis and the Accounts curve (TD-138) will read the secondary account's intraday values as its close; a dead account adds a constant NAV row; Backing's pressure history and the Room-to-add lookback have nothing to read.
- **Fix**: core 9013ba2 (0.51.0): capture works per account; an account whose brokerage.account updated_at is older than the session close (16:00 New York, or the NYSE early close from market.us_market_holiday) is skipped with its positions and listed in stale_accounts; an account already captured for the date is left alone; the empty-attribution refusal counts only the accounts being written. infra deaa2ca: the 20:30 CronJob runs `all` (capture, then enrich), which takes an account that came back after the close. account_nav_daily gains cushion / excess_liquidity / maint_margin_req (ADD COLUMN IF NOT EXISTS, double precision, nullable, no default, no backfill; parsed from summary_extra, non-finite → NULL). Ordering risk: an image at 0.51.0 in an environment whose db-init has not run fails the capture INSERT on the missing columns.
- **Ratchet**: core tests in 9013ba2: test_capture_skips_a_stale_account_whole_and_lists_it, test_evening_rerun_takes_only_the_account_that_came_back, test_positions_without_an_account_row_count_as_stale, test_session_close_reads_an_early_close (db), test_margin_columns_are_additive_and_idempotent (db). No separate nightly check: the writer itself refuses a stale account and prints it as stale_accounts in the Job log; the 验收 SQL is the spot check.
- 审批 改表 + 发布（要你批） · 代价 S · 风险 med · repos: bifrost-trade-core, bifrost-trade-infra

### TD-138

**P2 · trade-data · The daily position and NAV snapshots have no reader: no trade-api route, no Research or frontend read, and three pages still say the snapshot does not exist**

- **状态**：未开始
- **验收**：PROD 读接口返回 200 且有行：`curl -s -o /dev/null -w '%{http_code}' http://192.168.10.73:30881/api/account/portfolio/nav-history` → 200（若实现时取了别的路由名，把命令改成那个）；`git -C bifrost-trade-api grep -c 'position_snapshot_daily\|account_nav_daily' origin/main -- src` 至少 1 个文件；`git -C bifrost-trade-frontend grep -n 'Nothing stores one' origin/main -- src/pages/portfolio/pnlExplain` 无输出
- **下一步**：等 10-06 收盘后有两天数据再开工：api 读接口 → 前端按 SNAPSHOT-SPEC §5 改三页；TD-139 的 quality 在这一步一起定。TD-137 上线前读侧要按 account_updated_at 过滤盘中行。
- **Claim**: Since 10-05 position_snapshot_daily and account_nav_daily are written nightly in all three Trade databases, but trade-api, Research and the frontend have no reference to either table, and GET /api/account/portfolio/nav-history, /snapshots and /api/monitor/status/history answer 404 on PROD. PnlExplainPage, PerformanceReturnBasis, the Transfer & Pay downstream band and the Accounts net-liquidation curve keep their not-wired state, and the P&L Explain model text still says nothing stores a snapshot.
- **Measured**: MEASURED 10-06: 10-05 rows DEV 31 / STG 30 / PROD 31, option Greeks 13/13; `git grep` for both table names on origin/main: 0 files in bifrost-trade-api (8a78042) and bifrost-research (a242b22), only core's writer; the three routes 404 on PROD.
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/snapshot_ddl.py:24` — `POSITION_SNAPSHOT_DAILY = "position_snapshot_daily"`
  - `bifrost-trade-frontend/src/pages/portfolio/pnlExplain/PnlExplainPage.tsx:348` — `⚠ needs the daily snapshot`
  - `bifrost-trade-frontend/src/pages/portfolio/pnlExplain/pnlExplainModel.ts:47` — `'The four attributions need a per-day snapshot of positions, marks and vendor Greeks. Nothing stores one, so Δ, Γ, vega and θ have no reading`
  - `bifrost-trade-frontend/src/pages/portfolio/performance/PerformanceReturnBasis.tsx:95` — `per account — net liquidation plus its snapshot time (SNAPSHOT-SPEC §1.1).`
- **Impact**: The stored history reaches no page: P&L Explain attribution and its Today / WTD / MTD windows, the Performance return basis, Transfer & Pay downstream and the Accounts curve stay grey while the data accumulates.
- **Fix**: trade-api read routes over both tables through a core reader (per account and date range, NAV history; positions per session with a trade_id rollup for SNAPSHOT-SPEC §2), then the three frontend items in SNAPSHOT-SPEC §5. Until TD-137 ships, the reader drops NAV rows whose account_updated_at is before that session's close.
- **Ratchet**: trade-api route test that reads the snapshot tables on a seeded DB; frontend test that P&L Explain stops rendering the not-wired text when the route returns rows.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-trade-core, bifrost-trade-api, bifrost-trade-frontend

### TD-139

**P3 · trade-data · Snapshot Greeks carry no quality flag (vendor / degraded / missing): only mark_source and greeks_asof are stored**

- **状态**：未开始（随 TD-138 读侧一起定：派生还是加列）
- **验收**：TD-138 的读接口对每个 OPT 行都给出 `greeks_quality` ∈ {vendor, degraded, missing}，且 missing 的个数等于 `SELECT count(*) FILTER (WHERE sec_type='OPT' AND delta IS NULL) FROM position_snapshot_daily WHERE snapshot_date = (SELECT max(snapshot_date) FROM position_snapshot_daily)`（同上的 CNPG 副本只读命令）
- **Claim**: SNAPSHOT-SPEC §1.3 asks for a quality field per option row so P&L Explain phase 2 can mark degraded Greeks instead of reading them as exact; position_snapshot_daily stores mark_source and greeks_asof only. Not biting yet: every option row of 10-05 has vendor values.
- **Measured**: MEASURED 10-06: 10-05 OPT rows 13/13 with delta present in all three databases.
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/snapshot_ddl.py:44` — `mark_source text,`
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/snapshot_ddl.py:51` — `greeks_asof timestamptz,`
  - `design/trade/SNAPSHOT-SPEC.md:61` — `(vendor / degraded / missing)`
- **Impact**: The first night a vendor Greek is missing or stale, P&L Explain phase 2 has no way to say so.
- **Fix**: Prefer deriving on read in the TD-138 reader: vendor when greeks_asof is that session and delta is present; missing when delta is null; degraded when greeks_asof is older than the session or mark_source is not vendor. Add a column only if the read cannot tell degraded apart (that would be 改表, back to the Owner).
- **Ratchet**: Unit test of the derivation over the three cases; the route contract test asserts the field on every OPT row.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-api

### TD-140

**P2 · trade-data · Position attribution rows have no price, intraday or after the close: their only price source is contract_quote_live, which only the frozen daemon writes**

- **状态**：未开始（口径 Owner 10-06 已定：(a) 没有活报价时读最近一次 vendor EOD 并标 mark_source）
- **验收**：收盘 enrich 之后：`curl -s http://192.168.10.73:30881/api/account/executions/position-attribution | python3 -c 'import json,sys;r=json.load(sys.stdin)["items"];print(len(r),sum(x.get("price_mid") is None and x.get("price_last") is None for x in r),sorted({str(x.get("mark_source")) for x in r}))'` → 第二个数为 0，第三项不含 None
- **Claim**: get_position_instance_attribution takes price_mid / price_last only from a LEFT JOIN on brokerage.contract_quote_live, filtered to rows younger than 4 hours (TD-02, core 0.28.2). Under D10 the daemon does not run, so the table has 13 rows, newest 2026-03-28, and every attribution row has no price and no unrealized_pnl_est, intraday and after the close. The 09-29 reading that stocks had prices was March prices the freshness rule now excludes.
- **Measured**: MEASURED 10-06 after the close: GET /api/account/executions/position-attribution → PROD and DEV 31 rows each; OPT 13/13 and non-OPT 18/18 with price_mid, price_last and unrealized_pnl_est null; brokerage.contract_quote_live 13 rows, max(updated_at) 2026-03-28. (09-29: 30 rows, OPT 12/12 null, non-OPT 2/18 null.)
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/executions.py:1576` — `cql.mid AS price_mid, cql.last AS price_last`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/executions.py:1578` — `LEFT JOIN {CONTRACT_QUOTE_LIVE} cql`
  - `bifrost-trade-core/src/bifrost_core/portfolio/quote_freshness.py:33` — `def fresh_quote_sql(alias: str) -> str:`
- **Impact**: Positions and Ledger show no unrealized P&L for any position; anything that reads attribution prices reads nothing.
- **Fix**: Where no fresh live quote exists, take the newest position_snapshot_daily.mark for the contract (vendor EOD, written by the nightly enrich) and return mark_source and its date; intraday stocks may use the plugin daily-close fallback TD-02 already uses. The snapshot capture itself calls this reader, so the fallback must not become the snapshot's own mark (enrich stays its source). Nothing here writes contract_quote_live or touches the daemon (D10).
- **Ratchet**: core test: with contract_quote_live empty and a snapshot mark present, the row carries that price with mark_source vendor EOD; with a fresh live quote, the live one wins.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-frontend

### TD-142

**P2 · research-data · The 90-day IV cone has 31–39 sessions of history and there is no 180-day tenor: ATM IV was stored only to 90 DTE before 2026-08-05**

- **状态**：未开始（方向 Owner 10-06 已采纳：从 option_daily 回填；执行前列范围交你确认；须在 10-31 前做，W3 11-01 起删 option_daily 最老一个月，之后只能读归档）
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -At -c "SELECT count(DISTINCT trade_date) FROM features.option_metric_atm_iv_daily WHERE symbol='NVDA' AND expiry-trade_date>90 AND atm_iv IS NOT NULL"` ≥ 150（回填前 39 左右）；TD-141 的 iv-cone 命令里 NVDA 的 90 档 n ≥ 60、withheld 为 False，且出现 180 档
- **Claim**: The ATM IV store kept only expiries up to 90 DTE before 2026-08-05 (the Brent pass is still capped at DTE_MAX = 90), so the cone's 90-day horizon has fewer than MIN_SESSIONS (60) sessions and its percentiles are withheld; there is no 180-day horizon at all. It fills by itself around early November. raw_market.option_daily holds the long-dated bars to backfill from.
- **Measured**: MEASURED 10-06: iv-cone 90d NVDA 39, SPY 31, AAPL 32 sessions; no 180d. raw_market.option_daily: NVDA bars with trades at 150–220 DTE on 154 sessions, earliest 2025-11-10.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/iv_solver.py:53` — `DTE_MAX = 90`
  - `bifrost-research/src/bifrost_research/engines/volatility/atm_iv.py:366` — `AND (o.expiry - o.bar_date) BETWEEN {DTE_MIN} AND {DTE_MAX}`
  - `bifrost-research/src/bifrost_research/repositories/iv_cone.py:36` — `MIN_SESSIONS = 60`
- **Impact**: History's cone withholds 90-day percentiles for every name and has no long tenor for calendars and longer-dated structures.
- **Fix**: One-off Research backfill of long-tenor ATM IV into features.option_metric_atm_iv_daily from option_daily with the Brent method and the DTE cap lifted to about 220 for that pass only; first list the range (symbols × sessions × expected rows, which sessions already have >90 DTE rows) for the Owner. Then add 180 to the cone's tenors. Writes Research-owned features.* only (D13).
- **Ratchet**: A test that the longest cone tenor is inside the DTE range the ATM IV writers store, so the cone and the store cannot drift apart again.
- 审批 要你批 · 代价 M · 风险 med · repos: bifrost-research

### TD-143

**P3 · research-data · Hypotheses never link to trades: linked_opportunity_ids is empty on all 91 rows, and only Research's own create / patch writes it**

- **状态**：未开始（口径 Owner 10-06 已定：Research 读 Trade 的 plan 派生，不新增跨载荷写入方；链到 trade_id）
- **验收**：在 DEV 上用一个 hypothesis 建 plan（source_kind='hypothesis'）并关联成交后，Research 的 hypothesis 读接口带出该 trade_id；`git -C bifrost-trade-frontend grep -n 'BROKEN_LINK' origin/main -- src/pages/review/objectives` 指向派生链接而不是 `hypothesis.linked_opportunity_ids`
- **Claim**: research.hypothesis holds 91 rows (active 65 · archived 25 · validated 1) and none has linked_opportunity_ids; the objective chain in the frontend names exactly that column as its broken link. Trade's strategy_plan already carries source_kind='hypothesis' with source_ref and trade_id, so the link can be derived, but plans are PROD 0 · STG 0 · DEV 3 (all manual) and trade-api GET /plans has no source_kind filter.
- **Measured**: MEASURED 10-06 on the replica (Golden Source and the three Trade databases).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/api/hypothesis.py:69` — `linked_opportunity_ids: list[str] = Field(default_factory=list)`
  - `bifrost-trade-frontend/src/pages/review/objectives/objectiveChainModel.ts:48` — `export const BROKEN_LINK = 'hypothesis.linked_opportunity_ids'`
  - `bifrost-trade-api/src/bifrost_api/strategy/routers/plans.py:72` — `status: Optional[str] = Query(None, description="draft, intended, filled or cancelled"),`
- **Impact**: /review/objectives shows the chain broken at the hypothesis for every objective; the Hypothesis Board's record stays thin.
- **Fix**: Research derives hypothesis → trade_id at read time from Trade plans with source_kind='hypothesis', source_ref = the hypothesis id and trade_id set. Read path (trade-api GET /plans with a source_kind filter, or another read path) is listed with the build; no new writer into either store (D13). The frontend chain reads the derived link. Links appear only once plans are used.
- **Ratchet**: Research test: a plan with source_kind hypothesis and a trade_id yields the link, a cancelled plan does not; frontend test that the chain is not broken when the link exists.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research, bifrost-trade-api, bifrost-trade-frontend

### TD-144

**P3 · research-data · Settled candidates are not attributed to the judge (persona) that put them forward, so the Personas bench track-record columns stay grey**

- **状态**：未开始（要你定：要不要做、记在哪；见「需要你拍板」）
- **验收**：选 A 时，上线后：`SELECT count(*), count(*) FILTER (WHERE source_ref ? 'persona') FROM research.candidate_pool WHERE source='harness' AND trade_date >= '<上线日>'`（Golden Source 副本只读）两数相等且 > 0
- **Claim**: research.candidate_pool has 129 rows and none carries a persona key in source_ref; no other table records which judge proposed which candidate. JudgeTrackRecord's four track-record columns and the Pilot Console bench bar have nothing to read.
- **Measured**: MEASURED 10-06 on the Golden Source replica.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/repositories/candidate_pool.py:24` — `"source_ref",`
  - `bifrost-trade-frontend/src/pages/copilot/personas/JudgeTrackRecord.tsx:15` — `*   a per-judge verdict against the outcome that followed, so the design's`
- **Impact**: The bench cannot say which judge earns its weight.
- **Fix**: Recommended: the harness writes source_ref.persona (and the judge model) when it inserts a candidate; forward only, no DDL, no backfill; candidate-outcome /summary groups by it. Alternative: a new research.* table if one candidate can carry several judges' votes (design first, database-design skill).
- **Ratchet**: Test that the harness insert path sets source_ref.persona; an asset check that new harness candidates without it are 0.
- 审批 要你批 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-frontend

### TD-145

**P3 · research-data · Settled candidates carry no regime label, so the Personas bench 'Best regime' column has nothing to group by**

- **状态**：在做（后端已上 research 0.186.0（995a890）：/rows 每行带 regime / regime_scope / regime_date，/summary?by_regime=true 按 regime 分组；10-06 GS 副本实测 127 个已结算候选 111 个名字 regime、16 个 SPY、0 个无标签；`tests/api/test_candidate_outcome_rows_regime.py` 5 passed。剩前端：JudgeTrackRecord 的 Best regime 列接 /summary?by_regime=true，设样本数门槛。**接手**：前端没有分支，从 main 新开；JudgeTrackRecord.tsx 的 Best regime 列读 `/research/candidate-outcome/summary?source=<src>&days=<n>&by_regime=true` 的 `data.by_regime`，取 hit_rate 最高且样本数过门槛的 regime；需 research 用户令牌（require_owner）；Journal Settled 的 Right / Wrong 拆分同时改读 TD-147 的 `/rows?source=&days=`）
- **验收**：`kubectl -n research exec deploy/research-api -- python -c "import bifrost_research;print(bifrost_research.__version__)"` ≥ 0.185.0；在 research origin/main 上 `python -m pytest tests/api/test_candidate_outcome_rows_regime.py -q` 通过；前端接上后 `git -C bifrost-trade-frontend grep -n 'by_regime' origin/main -- src` 至少一行
- **Claim**: No candidate's lens_snapshot has a regime key and Golden Source has no market-level regime table; the per-name regime lives in features.stock_forecast_terrain_daily (06-24 → 10-05). SPY was range on 25 of the 26 candidate days, so a market label would separate nothing.
- **Measured**: MEASURED 10-06: 0 candidates with lens_snapshot ? 'regime'. With 3109b04 on the replica: of 127 settled candidates 111 take the name's regime, 16 fall back to SPY, 0 unlabelled (the join takes that session or the newest within 7 days before it, since 15 candidate dates fall on weekends); the LATERAL join runs in about 2 ms. Side reading, small sample: harness 5d hit trending 19/24, range 24/64.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/api/candidate_outcome.py:136` — `@router.get("/rows", dependencies=[Depends(require_owner)])`
  - `bifrost-trade-frontend/src/pages/copilot/personas/JudgeTrackRecord.tsx:56` — `{ column: 'Best regime', missing: 'settled outcomes carry no regime label' },`
- **Impact**: The bench cannot say in which market a judge is right.
- **Fix**: 3109b04: /rows adds regime, regime_scope and regime_date per row, derived at read time as COALESCE(name terrain, SPY) (precedent: /research/signal-decay); /summary?by_regime=true groups by it. No table or column. Then JudgeTrackRecord's Best regime reads /summary?by_regime=true with a sample floor.
- **Ratchet**: tests/api/test_candidate_outcome_rows_regime.py (3109b04).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-frontend

### TD-146

**P3 · research-data · No store accepts a hand verdict, so the Personas bench 'Agrees with you' column cannot be computed**

- **状态**：未开始（要你定：要不要建手动判词库；要的话是新表，先出设计；见「需要你拍板」）
- **验收**：建了的话：`git -C bifrost-research grep -n 'verdict' origin/main -- src/bifrost_research/schema` 出现新表的 DDL，且 `git -C bifrost-trade-frontend grep -n "column: 'Agrees with you'" origin/main -- src` 无输出（列不再登记为缺数据）
- **Claim**: Nothing records a hand verdict beside the machine's on the same name; JudgeTrackRecord greys 'Agrees with you' for that reason.
- **Measured**: CODE-READ 10-06: no verdict table under bifrost_research/schema on origin/main a242b22.
- **Evidence**:
  - `bifrost-trade-frontend/src/pages/copilot/personas/JudgeTrackRecord.tsx:23` — `* - **Agrees with you** needs a hand verdict beside a machine one on the same`
  - `bifrost-trade-frontend/src/pages/copilot/personas/JudgeTrackRecord.tsx:24` — `*   name. The hand-verdict store (Vision §4 · §9.3) does not exist yet.`
- **Impact**: One of the bench's columns stays grey; no agreement rate between the Owner and the judges.
- **Fix**: If wanted: a journal.* table keyed by research user (D-Journal-Stores), one row per (user, symbol, trade_date) verdict with an optional note, written from the bench; designed with the database-design skill before any DDL. If not: the column keeps its stated reason and this item is closed as not wanted.
- **Ratchet**: If built: a DB test of the store and the frontend column test. If not built: none needed (the page already states why).
- 审批 要你批 · 代价 M · 风险 low · repos: bifrost-research, bifrost-trade-frontend

### TD-148

**P3 · trade-data · A trade cannot name the lens or backtest run it came from: trade has no such column and strategy_plan.source_kind does not allow lens / backtest_run**

- **状态**：未开始（口径 Owner 10-06 已定：(b) plan 的 source_kind 加 lens / backtest_run，经 plan → trade 派生；DDL 清单待你逐项确认，见「需要你拍板」）
- **验收**：三个 Trade 库各跑：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_prod -X -At -c "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='strategy_plan'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%source_kind%'"` 含 `'lens'` 与 `'backtest_run'`
- **Claim**: PROD trade has trade_id, strategy_opportunity_id, account_id, opened_at, label, created_at, updated_at and no public table has a lens, backtest or run_id column. strategy_plan.source_kind is checked against manual | symbol | hypothesis | inbox_draft | roll, and core repeats the same five in the reader and the request schema. Outcome / Lineage keep the lens and run chips grey (design D3, Owner 2026-09-17).
- **Measured**: MEASURED 10-06 on bifrost_prod (columns of trade; the CHECK definition).
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/persistence/postgres/trade_ddl.py:124` — `CHECK (source_kind IN ('manual', 'symbol', 'hypothesis', 'inbox_draft', 'roll')),`
  - `bifrost-trade-core/src/bifrost_core/monitor/reader/strategy_plan.py:593` — `_SOURCE_KINDS = ("manual", "symbol", "hypothesis", "inbox_draft", "roll")`
  - `bifrost-trade-core/src/bifrost_core/monitor/schemas/strategy_plans.py:17` — `SourceKind = Literal["manual", "symbol", "hypothesis", "inbox_draft", "roll"]`
  - `design/trade/DECISIONS.md:1232` — `**D3 · Outcome 的 lens / run 链条**(Owner 2026-09-17)`
- **Impact**: Record's Lens cut has a single 'no lens recorded' row and 'vs backtest' is a dash everywhere.
- **Fix**: DDL per environment through db-init: drop the source_kind CHECK on strategy_plan (name read from pg_constraint; default strategy_plan_source_kind_check) and add it back with 'lens' and 'backtest_run'. Widening only: existing rows pass, PROD has 0 plans, no new column, no backfill, reversible while no row uses the new values. Code: core _SOURCE_KINDS and SourceKind gain the two values (public interface: core minor bump, trade-api lower bound raised), source_ref carries the lens id or backtest run id; frontend Outcome / Lineage read them through the trade's plan.
- **Ratchet**: core test that the DDL CHECK list, _SOURCE_KINDS and SourceKind are the same set (three copies pinned together).
- 审批 改表（要你批） · 代价 S · 风险 low · repos: bifrost-trade-core, bifrost-trade-api, bifrost-trade-frontend

### TD-149

**P2 · market-data · CTVA's adjusted daily bars ignore its 2026-10-01 spin-off, so every return-based feature on CTVA sees an ~84% one-day drop**

- **状态**：观察中（到 10-16，看数据源 adjusted=true 是否把分拆算进去）
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -At -c "SELECT bar_date, close, close_unadjusted FROM raw_market.stock_daily WHERE symbol='CTVA' AND bar_date BETWEEN '2026-09-28' AND '2026-10-02' ORDER BY 1"` 中 09-30 的 close ≠ close_unadjusted；且 `SELECT trade_date, rv_20d FROM features.stock_signal_vrp_daily WHERE symbol='CTVA' AND trade_date >= '2026-10-01' ORDER BY 1` 全部 < 1.0
- **现在**：每日定时任务 daily-ctva-adjust-and-unadjusted-close-check 在查（10-02、10-05、10-06 都未复权）。第 2 步 Owner 10-02 已批：数据源复权后重抓 CTVA 日线并重算 10-01 起的派生。
- **下一步**：复权后按已批的第 2 步做；到 10-16 仍不复权，另议：Research 按分拆比例自算（另批）。（10-16）
- **Claim**: The vendor's adjusted and unadjusted CTVA series are identical across the 10-01 spin-off (09-30 77.65 → 10-01 12.57), so raw_market.stock_daily.close carries the drop. VRP takes log(close_t / close_{t-1}) from that column and gives rv_20d about 6.4 from 10-01; momentum, SEPA, terrain and scan read the same bars; each session adds one more affected day, up to 252. The option metrics recovered separately once the standard series listed (closed on the board).
- **Measured**: MEASURED 10-06 13:33 UTC (scheduled check): 09-28 → 10-05 adjusted = unadjusted every day; close_unadjusted coverage on 10-05 100.00% (12,605/12,605, 0 rows off by more than 0.1%); CTVA rv_20d 09-30 0.209 → 10-01 6.438 · 10-02 6.433 · 10-05 6.444.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/ingest/stock_daily_grouped.py:8` — `the adjusted series folds in spin-offs as well as splits (HON 2025-10-29 reads`
  - `bifrost-research/src/bifrost_research/engines/vrp/compute.py:91` — `log_returns.append(math.log(cur / prev))`
  - `bifrost-research/src/bifrost_research/engines/vrp/compute.py:133` — `SELECT bar_date, close`
- **Impact**: CTVA's VRP, momentum, SEPA, terrain and scan are wrong from 10-01 and one more day wrong every session.
- **Fix**: Approved step 2: once the vendor restates, re-pull CTVA daily bars and recompute the derived features from 10-01. If not by 10-16: Research applies the spin ratio to the pre-spin bars itself (separate approval).
- **Ratchet**: For this case the daily scheduled check. For the class (proposed): a nightly sweep that flags any name whose close-to-close |log return| exceeds ln 3 on a day with no split in corporate_action, which catches the next unadjusted spin-off within one night.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data, bifrost-research

### TD-150

**P3 · frontend · Pages report gaps that are not there: 'no earnings date reaches this side', 'carry nothing at all' for names the vendor answered, and no note that CUE lists only adjusted contracts**

- **状态**：在做（代码就绪，已推为分支、未合并：frontend `fix/data-gap-wording` = 024077be（R2.b）· e8e554fc（B4.tail）· 7caac1f8（R10.CUE），基于 d1254adc；lint / build 过，改动文件相关测试 83 例过，全量 vitest 在最后一处改名后未重跑。**接手步骤**：① 等 Code Refactor 那批 Trade 发布（含前端 d1254adc）在 PROD 通过；② rebase 到最新 main，跑 `npm run lint && npm run build && npm run test:run`（全量）；③ 在 :5173 对 DEV 看 Today、Limits、Scan、Vol ratings、Corporate Actions、Symbol?CUE；④ `release.sh window && git push` 前端 main，随下一次 Trade 发布上线。Design 待看三点：Vol ratings 在 All 下 Earn 列部分有数、CUE 各指标块仍写 No reading — wait、440 紧凑版没有这条说明）
- **验收**：`git -C bifrost-trade-frontend grep -n -i 'earnings date reaches this side\|No earnings date on this side\|carry nothing at all\|cannot say whether they pay' origin/main -- src ':!src/layout/designNotes'` 无输出，且 `git -C bifrost-trade-frontend grep -n -i 'only adjusted contracts' origin/main -- src` 至少一行
- **Claim**: Three wording gaps, one batch. (1) Earnings (board R2.b): the shared earnings read from 10-04 (c85b0079 / 1b0baa53 / ca3694a2) gives estimated next dates, but Today checks, Limits, Scan and Vol ratings still say no earnings date reaches this side; TodayFace and stockRatingsModel already changed. (2) Corporate Actions (B4.tail): a name with a single row is treated as not backfilled and names with none are 'carry nothing at all'; after the 09-29 backfill CAOS's one split is a complete answer and CBRS · FN · HIMS · NBIS · NNE · RKLB really have 0 events. (3) CUE (R10.CUE): after the 1:30 reverse split (ex 2026-04-24) only 14 adjusted CUE1 contracts expiring 10-16 exist and no standard series is listed; the pages show empty max pain / ATM IV / GEX / flow / PCR with no reason.
- **Measured**: MEASURED 10-06 on bifrost-trade-frontend origin/main a9cbd02a: the lines below; 'only adjusted contracts' 0 hits; CUE 10-05 open interest 14 rows, all CUE1.
- **Evidence**:
  - `bifrost-trade-frontend/src/pages/home/today/useTodayChecks.ts:186` — `'no future earnings date reaches this side for any name in the book, so the week ahead cannot be read',`
  - `bifrost-trade-frontend/src/utils/limitsModel.ts:284` — `noReading: 'no future earnings date reaches this side, so no window can be drawn',`
  - `bifrost-trade-frontend/src/pages/research/discover/ScanPage.tsx:490` — `title="Days to the next print. No forward earnings date reaches this side — /research/events/calendar answers count 0, and the gap behind it`
  - `bifrost-trade-frontend/src/pages/research/discover/ScanPage.tsx:567` — `title="No earnings date on this side — see the column header."`
  - `bifrost-trade-frontend/src/lib/research/volRatingsModel.ts:46` — `* - an **Earn** column. No forward earnings date reaches this side:`
  - `bifrost-trade-frontend/src/pages/portfolio/corporateActions/corporateActionsModel.ts:211` — `/** Symbols with nothing at all — the feed cannot say whether they pay. */`
  - `bifrost-trade-frontend/src/pages/portfolio/corporateActions/CorporateActionsPage.tsx:391` — `${reach.silent.length} carry nothing at all: ${reach.silent.join(', ')}`
- **Impact**: The pages tell the Owner data is missing where an estimate exists or where the vendor answered zero; CUE's empty metrics read as a failure.
- **Fix**: The four earnings sites read the shared earnings read and say estimated ◎ · confirmed dates not in the subscription (see 数据边界); Corporate Actions says 'vendor answered none' / 'one event on record'; CUE's option metric cells say only adjusted contracts are listed (CUE1, 1:30 reverse split) and the exchange lists no standard series.
- **Ratchet**: A frontend test that searches src (outside designNotes) for the retired phrases and fails on a hit. Manual strength until vitest runs in CI (RATCHETS: FE 守卫测试).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-frontend

### TD-151

**P3 · research-data · The macro calendar is empty: features.macro_event_daily has 0 rows because macro_ingest has no scheduled caller**

- **状态**：未开始（优先级低，可选）
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n data exec -i bifrost-postgres-3 -c postgres -- env PGOPTIONS='-c default_transaction_read_only=on' psql -U postgres -d bifrost_golden_source -X -At -c "SELECT count(*), max(event_date) FROM features.macro_event_daily"` → count > 0 且 max(event_date) ≥ 今天 + 30 天；`git -C bifrost-research grep -n macro_ingest origin/main -- src/bifrost_research/orchestration` 至少一行
- **Claim**: features.macro_event_daily is filled only by scheduler/macro_ingest.py, a CSV drop-zone ingest from Wave R4, and no Dagster schedule, job or CronJob calls it. /research/event-radar/macro/forward and /macro/gap answer 0 rows; the macro rows in /research/events/calendar come from a hand-placed ws:macro file.
- **Measured**: MEASURED 10-06: 0 rows; both routes 0 rows. CODE-READ: `git grep macro_ingest` on origin/main finds no caller in bifrost_research/orchestration or bifrost-trade-infra.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/scheduler/macro_ingest.py:1` — `"""Macro economic calendar CSV ingest (manual drop zone, Wave R4)."""`
  - `bifrost-research/src/bifrost_research/scheduler/macro_ingest.py:98` — `def run_macro_ingest_from_env() -> dict[str, Any]:`
  - `bifrost-research/src/bifrost_research/api/wave4.py:859` — `FROM features.macro_event_daily`
- **Impact**: Event radar has no macro look-ahead (FOMC, CPI, payrolls) from the store.
- **Fix**: Schedule macro_ingest weekly from Dagster over one maintained source (the ws:macro file the calendar already reads, or a vendor feed if the subscription has one). Or, if the calendar's ws:macro rows are enough, retire the two macro routes and the empty table instead (delete, not build).
- **Ratchet**: A Dagster asset check that features.macro_event_daily has a row dated within the next 30 days.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-152

**P2 · ops-platform · promtail drops log lines (ingester_error) around 02:00–03:15 and 22:xx UTC, so every Loki-based release gate can come out INCONCLUSIVE**

- **状态**：未开始
- **Claim**: Release gates that prove 'nobody calls X any more' read Loki. promtail dropped 35 entries 10-02..10-05 and 18 more by 10-06 with reason ingester_error, clustered on ubt-k3s-04 (STG/DEV api pods) at ~03:00Z and ubt-k3s-02 (PROD) at 22:xxZ. loki_gate.py counts the drops and refuses to call a zero a zero.
- **Measured**: MEASURED 10-06 by paydown lane F: TD-51 gate dev 0 / stg 0 / prod 0 hits but INCONCLUSIVE (exit 3) because of 18 dropped entries; Prometheus `sum by (instance,reason)(increase(promtail_dropped_entries_total[1h]))`.
- **Evidence**:
  - `bifrost-trade-infra/scripts/release/loki_gate.py:241` — `res = prom_instant(f"sum(increase(promtail_dropped_entries_total[{secs}s]))", end)`
- **Impact**: Every compatibility-removal gate (TD-51 today, naming gates before it) needs an Owner judgement instead of a mechanical pass; real drops could hide a real caller.
- **Fix**: Find the Loki ingester limit or back-pressure hit at those times (rate / stream limits, ingester memory, the nightly batch log burst) and raise it or shape the burst; alert on promtail_dropped_entries_total > 0.
- **Ratchet**: PrometheusRule on increase(promtail_dropped_entries_total[1h]) > 0 (warning), so a gate's blind spot is visible the day it opens.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-153

**P3 · ops-platform · loki_gate.py only knows the pre-0.10.0 log line ('deprecated query params'); after api 0.10.0 refused callers log 'retired query params' and the gate cannot see them**

- **状态**：未开始
- **Claim**: api 0.10.0 (TD-51) replaces the silent rewrite with a 422 and a WARNING 'retired query params: … user_agent=…'. loki_gate.py's TD-51 check builds its needle from the deprecated-params line only, so after the release a caller still sending old names is invisible to the gate that was built to find it.
- **Measured**: code-read 10-06 (paydown lane F).
- **Evidence**:
  - `bifrost-trade-infra/scripts/release/loki_gate.py:348` — `needle = f'|~ "{td51_group_regex(group)}"'`
  - `bifrost-trade-infra/scripts/release/loki_gate.py:55` — `TD51_NAMES = ("since_ts", "until_ts", "opened_at_from", "opened_at_until", "trade_date_from", "trade_date_to",`
- **Impact**: The 24-hour post-release check for TD-51 has to be done by hand with a raw LogQL query.
- **Fix**: Add a `td51-retired` check that counts 'retired query params' lines (excluding bifrost-release-check) and use it in the post-release step.
- **Ratchet**: A loki_gate test that every gate name has a needle matching the log line the current api version emits (fixture lines from both versions).
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-infra

### TD-154

**P3 · trade (round 1) · api test_request_bodies asserts on a plain MagicMock that removed facade methods were not called — it can never fail**

- **状态**：未开始
- **Claim**: After core 0.49.0 the facade write methods no longer exist; the test still asserts on a bare MagicMock that create_position_category / set_position_category_tag / … were not called. A MagicMock accepts any attribute, so the assertion passes whatever the route does.
- **Measured**: code-read 10-06 (paydown lane F).
- **Evidence**:
  - `bifrost-trade-api/tests/test_request_bodies.py:338` — `for fn in ("create_position_category", "set_position_category_tag", "set_market_streams_symbol_order",`
- **Impact**: A regression that writes through an old path would not be caught by the test that claims to guard it.
- **Fix**: Assert that the matching `*_strict` writers were (or were not) called, on a MagicMock with spec= the real module, so a removed name raises.
- **Ratchet**: Lint rule or test helper: mocks of core facades/modules must use spec= (autospec), so asserting on a non-existent attribute fails.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-trade-api

### TD-155

**P2 · ops-platform · Pushes to GitHub main do not trigger CI until the Gitea pull mirror syncs, so a commit can be released before its CI ever ran**

- **状态**：未开始
- **Claim**: CI is triggered by Gitea webhooks; Gitea mirrors GitHub on a pull interval. On 10-06 core 0.49.0/0.50.0 (16:15/16:23 UTC) and api 0.10.0 had no CI run at all until `make k3s-sync-gitea-mirrors` was run by hand at ~16:30; core's previous CI was 14 h earlier. Together with TD-95 this means release.sh can deliver a SHA that CI has not seen.
- **Measured**: MEASURED 10-06: no ci-python-bifrost-trade-core/api PipelineRun after the pushes; the manual mirror sync created ci-python-bifrost-trade-core-9vgjk and -api-h7scl within seconds.
- **Evidence**:
  - `bifrost-trade-infra/k8s/cicd/tekton/trigger-trade-ci.yaml:225` — `body.repository.name in ['bifrost-trade-core', 'bifrost-trade-api',`
  - `bifrost-trade-infra/scripts/k3s/bootstrap-gitea-mirrors.sh:2` — `# Bootstrap Gitea org + GitHub pull mirrors (Session S7).`
- **Impact**: CI results lag pushes by up to the mirror interval; releases and reviews see 'no CI' and proceed anyway.
- **Fix**: Either a GitHub → Gitea push-mirror / webhook that syncs on push, or have release.sh (and the deliver pipelines, TD-95) sync the mirror and wait for the SHA's CI run before building.
- **Ratchet**: release.sh refuses a SHA with no Succeeded CI run (TD-95's switch) — which makes a missing run as visible as a red one.
- 审批 跨仓库发版 · 代价 S · 风险 med · repos: bifrost-trade-infra

### TD-156

**P2 · research-control · research_signal_hit_schedule fires at 00:10 UTC, before the 02:30 UTC batch writes the night's features, so it judges the previous night's features**

- **状态**：未开始
- **Claim**: signal_hit runs on its own cron ('10 0 * * 1-6' UTC) instead of inside research_trading_day after the feature writers. At 00:10 UTC the night's SEPA / IV / scan features are not written yet, so each walk reads the previous session's features — the same class as TD-97 (judge before writer).
- **Measured**: code-read 10-06 by paydown lane A; not measured.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/orchestration/research_aux_schedules.py:548` — `"research_signal_hit_schedule",`
  - `bifrost-research/src/bifrost_research/orchestration/research_aux_schedules.py:551` — `"10 0 * * 1-6",`
- **Impact**: Lens hit-rates and the alerts and drafts that read them lag a session and can pair features with the wrong session.
- **Fix**: Move signal_hit into research_trading_day after its sources and register it in READS_TRADING_DAY_OUTPUT (the TD-97 ratchet).
- **Ratchet**: tests/orchestration/test_judge_after_writer.py (added for TD-97) covers it once signal_hit is registered as a trading-day reader.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-157

**P3 · research-data · GEX writes a wall on an arbitrary strike when one side of an expiry has no gamma exposure: 1,762 levels rows on 244 names, terrain reads both walls**

- **状态**：未开始（要你批：改写行）
- **Claim**: compute_gex_levels picks the call wall with max(call_gex) and the put wall with min(put_gex) independently. When only one side has exposure (every call gex 0, or every put gex 0), that side's wall is still written: the first strike in the distribution, with wall gex 0. TD-136 (0.185.0) covers only expiries where both sides are empty.
- **Measured**: MEASURED 10-06 after the TD-136 purge, read-only: of 69,440 levels rows, 820 have call_wall_gex 0 with a non-zero put wall and 942 the reverse; 244 names; 169 since 10-01.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/gex/exposure.py:192` — `call_wall = max(distribution, key=lambda r: float(r.get("call_gex") or 0))`, and the put wall on the next line, with no check that the chosen wall has exposure
  - `bifrost-research/src/bifrost_research/engines/forecast/terrain.py:93` — pin_score_from_gex scores spot between the two walls
- **Impact**: terrain's pin score and gamma zone, and the levels pages, can place a call or put wall where no open interest of that side exists.
- **Fix**: Write NULL for a wall whose side has no exposure (call_wall_gex / put_wall_gex 0), so readers treat it as missing (terrain already handles a None wall). One-off: null those walls on the 1,762 rows and recompute terrain and scan on the name-sessions that read them (pattern: engines/gex/zero_exposure_purge).
- **Ratchet**: Extend tests/engines/test_gex_zero_exposure.py with a one-sided distribution; nightly check: no levels row with a non-null wall whose wall gex is 0.
- **验收**: `SELECT count(*) FROM features.option_metric_gex_levels_daily WHERE (major_call_wall IS NOT NULL AND COALESCE(call_wall_gex,0) = 0) OR (major_put_wall IS NOT NULL AND COALESCE(put_wall_gex,0) = 0)` returns 0 after two nightly runs.
- 审批 要你批 · 代价 S · 风险 low · repos: bifrost-research

### TD-158

**P3 · research-data · Earnings estimates are served one name per request, so no universe-wide page can show an Earn column**

- **状态**：未开始（Owner 10-06 加入）
- **验收**：`KUBECONFIG=~/.kube/bifrost-k3s.yaml kubectl -n research exec deploy/research-api -- python -c "import urllib.request,json;d=json.loads(urllib.request.urlopen('http://127.0.0.1:8795/research/narrative/earnings/batch?symbols=NVDA,AAPL,KO').read());print(sorted(d['data']))"` → `['AAPL', 'KO', 'NVDA']`，每个都带 `expected_next`（或带原因的空）；`git -C bifrost-trade-frontend grep -n "is served across the universe" origin/main -- src` → 0 行
- **Claim**: GET /research/narrative/earnings takes exactly one symbol. The frontend's useNamesEarnings issues one query per name, so pages that list hundreds of names (Stock screen, Scan with All, Vol ratings) either fan out hundreds of requests or show no earnings estimate. The data-gap wording batch (TD-150) caps Scan at 60 names and reads only the selected row under All; Stock screen still says no earnings date is served across the universe.
- **Measured**: CODE-READ 10-06 on origin/main: the route signature is `symbol: str = Query(..., min_length=1, max_length=16)`; no batch route exists in api/narrative.py. Stock screen copy states the gap in four places.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/api/narrative.py:233` — `@router.get("/earnings")`
  - `bifrost-research/src/bifrost_research/api/narrative.py:234` — `def earnings_dates(symbol: str = Query(..., min_length=1, max_length=16))`
  - `bifrost-trade-frontend/src/hooks/useNamesEarnings.ts:33` — `export function useNamesEarnings(symbols: readonly string[])` (one query per name)
  - `bifrost-trade-frontend/src/pages/research/stocks/StockScreenPage.tsx:703` — `Earn is — on every row: no earnings date is served across the universe.`
  - `bifrost-trade-frontend/src/pages/research/stocks/stockScreenStages.ts:32` — `'No earnings window or theme is served across the universe: …'`
  - `bifrost-trade-frontend/src/pages/research/stocks/ResultTable.tsx:305`, `RankDrawer.tsx:125` — same wording
- **Impact**: Stock screen's Earn column and Catalyst stage stay empty; Scan under All and Vol ratings under All show earnings only for rows read elsewhere; the earnings veto in rules cannot be applied across a screen.
- **Fix**: Add `GET /research/narrative/earnings/batch?symbols=` (cap ~500 names, one SQL over the 8-K table plus the expected_next rule, same per-name shape and reasons as the single route; additive, nothing removed). Frontend: useNamesEarnings fills its per-name cache from the batch call for lists; then Stock screen, Scan (lift the 60-name cap) and Vol ratings read it and the four "not served across the universe" strings go.
- **Ratchet**: Research test that the batch route returns the same reading as the single route for each name in a fixture; frontend ratchet that no page calls the single-name earnings read inside a list of more than 60 names.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research, bifrost-trade-frontend

### TD-159

**P3 · market-data · No read says how many standard and adjusted option contracts a name has, so "only adjusted contracts are listed" is inferred in the browser from ticker shapes**

- **状态**：未开始（Owner 10-06 加入）
- **验收**：对 CUE（或任一只有调整合约的名字）调用新增的计数读法 → `standard = 0`、`adjusted > 0`；对 NVDA → `standard > 0`；`git -C bifrost-trade-frontend grep -n "isAdjustedOptionTicker" origin/main -- src` → 只剩测试或 0 行
- **Claim**: Research excludes adjusted contracts (OCC root ending in a digit) from every option metric, so a name with only adjusted contracts has empty max pain, ATM IV, GEX, flow and PCR by rule. Nothing served says so. The TD-150 frontend batch infers it by fetching the nearest expiry's snapshot rows and testing each option_ticker's root, copying Research's SQL rule into TypeScript; it reads one expiry only and costs two extra requests on names whose four option exhibits are all missing.
- **Measured**: CODE-READ 10-06: the rule lives in Research `not_adjusted_contract_sql` (27 call sites) and, on the wording branch, in frontend `adjustedListing.ts`; the plugin's `/market/options/snapshots` returns rows with option_ticker but no per-name counts. MEASURED 10-05: CUE 14 open-interest rows, all `CUE1…`.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/adjusted_contracts.py:20` — `def not_adjusted_contract_sql(column: str) -> str:`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/api/options.py:293` — `@router.get("/snapshots")`
  - `bifrost-trade-frontend` branch `fix/data-gap-wording` 7caac1f8 `src/pages/research/analyze/symbol/adjustedListing.ts:26` — `export function isAdjustedOptionTicker(…)` (copy of the Research rule)
- **Impact**: Two copies of one rule (Research SQL, frontend regex) can drift; the note covers only the nearest expiry; any other surface that wants the explanation has to repeat the probe.
- **Fix**: Serve per-name counts once: Research adds `standard_contracts` / `adjusted_contracts` for the latest session (from option_open_interest, using not_adjusted_contract_sql) to an existing per-name read the Symbol page already loads (dossier or options coverage), additive. Frontend reads those fields and deletes its own ticker test.
- **Ratchet**: A frontend ratchet that no file outside tests matches the adjusted-root regex once the field is served; Research test that the counts agree with not_adjusted_contract_sql on a fixture.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-frontend

## 没覆盖到的（下一轮从这里开始）

- Per-engine numerical correctness beyond dates: GEX sign conventions, max-pain, VRP realized-vol windows, vanna/charm, SVI fit, flow maths
- EXPLAIN/plan stability of large raw_market reads by engines (option_snapshot, option_daily, option_open_interest); Dagster/dbt runtime cost (mart_sepa_tier_structure 144s, int_stock_daily_enriched 100s)
- research repositories/* write paths (copilot, journal, hypothesis, playbook) idempotency; copilot harness/agents and LLM provider failure paths; MCP write-tool approval-token validation (copilot/approvals.py)
- research-api read-side routes and their date defaults (api/pine.py, api/opex_cycle.py use date.today()); request-path performance and statement_timeout; callers outside the four consumer repos (Hermes on .50/.52, ad-hoc curl, Cowork)
- signal_hit_fwd_fill ordering inside research_trading_day (may read tonight's sources before they are written; self-heals next night; not measured); event_radar collected_at date basis judged intentional, not verified
- D13 grants: analytics_writer INSERT on ops_jobs.* and CREATE on raw_market/raw_broker; flex-query and market-data DB user switch to flex_writer/data_writer: all belong to open TD-85, not re-reported
- Plugin-side root cause of missing OI for NVR/GRML since 08-01 and QRVO stock_daily stopping at 10-02 (market-data plugin not opened for this)
- Market-data: retention_archive first real export (NFS behaviour, 768Mi API pod memory, serialization vs option-bars upserts); doctor internals beyond staleness/failed sections; Polygon rate limiting/429; per-symbol handlers, sec_filings, symbol_rename/void; plugin iv-percentile/atm-iv/pcr reads vs Research endpoints; dynamically built partition indexes
- IB Gateway live.py internals and ib_ops.py fill capture (D10-adjacent, skimmed only); live redis-ib ACL contents (needs admin password; Loki showed 0 NOPERM/WRONGPASS in 24h); DEV/STG /ops/market-ingest/services; Flex XML upload path and manual-trigger fallback; Flex token rotation scripts (handle secret values)
- core get_net_cash_flow semantics (round-1 Trade read domain); scripts/ one-off migration files in research; pine-runner NetworkPolicy; Loki logs for research-api/dagster; two RUNNING Dagster instigators (selector 8da707eb…) not resolved to names
- TD-96 (preflight bypass forms) and TD-109 (stale PROD ops-context copy) come from the ratchet-inventory pass and were not adversarially re-verified; whether any runtime consumer other than Console reads the stale copy was not checked
- 第 1 轮未覆盖项见 git 历史中本台账前身（artifact 版本 ≤ 48）。尚未扫描的领域：Ops 平台（bifrost-platform）、前端 UI 层、数据层（备份 / NFS / Secret）。

## 怎么做的

第 2 轮（2026-10-06）：10 个 Agent，约 35 分钟，全程只读（数据库只做 read-only 查询）。代码读的是各仓库 origin/main 的干净副本：research 6ed86ad · market-data acba67e · flex f7b5cd9 · IB gateway 插件 39eafe2 · infra d5aa457 · core 756bdb5。四个领域各一个盘点 Agent（Research 数据面、Research 控制面、market-data、flex + IB gateway），每个领域的发现交给一个专门反驳的 Agent 去推翻；另一个 Agent 清点现有防线并对照第 1 轮的各类债；最后一个 Agent 去重、排序、提出待建防线。40 条发现：22 条原样成立，18 条改了说法或优先级，0 条被推翻，3 条合并。之后日常工作里发现的直接加入（TD-127–129 来自 Pine 线程）。
第 1 轮（2026-10-01，Trade UI 之下）的原文在台账页 artifact 版本 ≤ 48 和 git 历史里。
