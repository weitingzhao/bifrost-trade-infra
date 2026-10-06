# Bifrost 技术债（未结）

> **这份文件只放没还完的债。** 一项修完、上线、对应的防线也到位之后，直接删掉这一条，提交信息写上它对应的防线（`RATCHETS.md` 里的那一行）。历史在 git 里，这里不留。
> 审计扫出来的、日常工作里撞上的，都直接在这里加一条，编号接着当前最大号往下排。每条必须有证据（`文件:行`）、修法和防线。
> 防线登记在同目录的 [`RATCHETS.md`](RATCHETS.md)。条目正文保留英文，标识符照抄。

更新：2026-10-06 · 第 1 轮（Trade UI 之下，10-01）剩 3 项 · 第 2 轮（Research + 插件，10-06：40 条发现，反向核实 22 成立、18 修正、0 推翻、3 合并）+ Build Desk

**未结 45 项**：P0 0 · P1 6 · P2 19 · P3 20；要你批的 10 项。

## 主题（第 2 轮）

- **Green while wrong: jobs succeed on zero, partial or garbage output** — The dominant round-2 class. Engines, gates, ingest handlers and writers convert failures into success: empty lists read as answers, exceptions become 0 or 'unknown', truncation is a field nobody checks, freshness bumps on zero-row jobs. Dagster and Flex show green; only manual metadata reading finds it. Fix pattern: raise or record reasons, and add output checks per asset. (TD-89, TD-90, TD-91, TD-92, TD-93, TD-94, TD-97, TD-100, TD-101, TD-106, TD-113, TD-116)
- **Session and calendar truth comes from the wall clock on UTC pods** — Session dates are derived from current_date/date.today() on UTC hosts at 02:30 UTC, producing next-day and Saturday stamps (SEPA, option_universe), a day-late alert judge, and a calendar that silently forgets holidays on a failed read. One session_today() helper plus a nightly session-date sweep closes the class. (TD-87, TD-98, TD-93, TD-97, TD-111)
- **Broker money ledger integrity (Flex / IB)** — The cash and commission ledgers have a 5-month hole the fixed window cannot refill, a writer that reports failure as success, a dedupe key that ignores IB's own id, mixed commission signs, DEV-routed reads and no tests on the money path; the gateway health signal is permanently false-red. (TD-88, TD-91, TD-103, TD-114, TD-115, TD-116, TD-117, TD-104, TD-122)
- **Gates that do not gate** — CI runs after delivery and never blocks it (research and Trade); plugins and infra have code-health baselines but no CI; preflight D10 matching misses non-curl clients and in-place edits; operator streams use a denylist; no alert watches Dagster schedules or research/plugin 5xx. Making CI gate release is the single highest-leverage ratchet. (TD-95, TD-96, TD-105, TD-99, TD-109)
- **Hand-kept copies and dead config drift** — Schedule rosters, max-pain/PCR math, Black-Scholes and risk-free readers, declared indexes, spine copies, instance configs and suspended CronJobs exist in several places that have drifted from the source of truth. Generate from one source or delete; ratchet with manifest and catalog checks. (TD-108, TD-102, TD-110, TD-107, TD-112, TD-118, TD-119, TD-120, TD-121, TD-123, TD-124, TD-125)

## 总览

| 编号 | 级别 | 领域 | 标题 | 审批 |
|---|---|---|---|---|
| [TD-85](#td-85) | P1 | trade (round 1) | One database password reaches everything: any DEV pod can write PROD Trade and all of Golden Source | 安全/凭据（要你批） |
| [TD-87](#td-87) | P1 | research-data | SEPA features are stamped with the next calendar day (UTC current_date at 02:30 UTC): every SEPA row is one session late and Friday sessions land on Saturday | 不用批 |
| [TD-88](#td-88) | P1 | flex-ib | raw_broker.transactions has no rows for 2026-03-06..2026-08-03, and the fixed 30-day window can never refill it | 不用批 |
| [TD-89](#td-89) | P1 | research-data | option_pinned_contract reads the Trade API list keys that api 0.4.0 removed; the 10-06 run saw 0 held legs and 0 executions and reported success | 不用批 |
| [TD-90](#td-90) | P1 | market-data | option_contract (and option_backfill_plan) report truncated:true as success; SPX already uses 118 of its 120-page cap because the page size is 250, not 1,000 | 不用批 |
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
| [TD-113](#td-113) | P3 | research-data | Playbook trigger emission fails with no log in four places; a failed previous-state lookup records a fresh 'snapshot' instead of comparing | 不用批 |
| [TD-114](#td-114) | P3 | flex-ib | raw_broker.commissions mixes two sign conventions: Flex writes cost as negative, the TWS/gateway path writes it as positive | 不用批 |
| [TD-115](#td-115) | P3 | flex-ib | Money-path tests missing: cash parser untested, cash upsert tested only on connect failure (pinning the silent 0), Flex branches of the executions writer untested; commission INSERT in four copies | 不用批 |
| [TD-116](#td-116) | P3 | flex-ib | The Flex ingest routes query-id, stats and range-day reads through the DEV DB (bifrost_dev) via FDW, with silent fallbacks that can widen the run to 270 days | 不用批 |
| [TD-117](#td-117) | P3 | flex-ib | 'Latest Flex date in DB' after an import is one run behind: read through FDW in the same transaction as the pre-import read | 不用批 |
| [TD-118](#td-118) | P3 | market-data | option-refresh re-enumerates names with no listed options every run; its 7-day 'finished' lookback reads a table kept 48h | 不用批 |
| [TD-119](#td-119) | P3 | market-data | Schema-migrate Job and worker Deployments are applied in one `kubectl apply -k` with no ordering; a table-adding release fails the jobs that land in the DDL window | 改表 |
| [TD-120](#td-120) | P3 | research-control | Dagster Deployments are applied by hand outside Argo; a second, unmounted dagster_instance.yaml lacks the run_monitoring that catches zombie runs | 跨仓库发版 |
| [TD-121](#td-121) | P3 | research-control | Research pods read bifrost-research-secrets once at start (optional: true); the OpenAI key rotation helper restarts only research-api | 安全/凭据（要你批） |
| [TD-122](#td-122) | P3 | flex-ib | The IB Gateway image is built on the Mac and imported to nodes with ctr under a reused tag: no registry, no digest, no recorded source SHA | 跨仓库发版 |
| [TD-123](#td-123) | P3 | research-control | About 19 deployed research-api routes have no caller in frontend, platform, trade-api or MCP, including manual POST triggers that run engine code outside Dagster | 改公开接口 |
| [TD-124](#td-124) | P3 | research-control | 39 permanently suspended CronJobs (25 research, 14 market-data, plus an orphan pinned to 0.10.0) are still deployed and re-pinned every release; research ones carry a stale 26-name watchlist and the verify script contradicts the one active CronJob | 删除（要你批） |
| [TD-125](#td-125) | P3 | flex-ib | Retired IB topology still referenced: TIBM-era verify scripts at the top of scripts/, flex_ops compat SQL for a schema that no longer exists | 删除（要你批） |
| [TD-126](#td-126) | P3 | ops-platform | Build Desk (Ops Console Engineer strip: Briefing / In Flight / Delivery) is a Cursor-era program tracker nobody uses | 删除（要你批） |
| [TD-128](#td-128) | P3 | research-data | Pine signal rows mix adjustment bases: nightly runs rewrite only the last ~10 sessions on today's adjusted bars, older rows stay on the basis of their last full rebuild | 不用批 |
| [TD-129](#td-129) | P3 | research-data | The event backtest picks option legs from option_daily only; since mid-August 2026 it keeps ~10 strikes a side, so a target delta silently lands on the nearest strike that is left | 不用批 |

## 条目

### TD-85

**P1 · trade (round 1) · One database password reaches everything: any DEV pod can write PROD Trade and all of Golden Source**

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

### TD-88

**P1 · flex-ib · raw_broker.transactions has no rows for 2026-03-06..2026-08-03, and the fixed 30-day window can never refill it**

- **Claim**: The cash-transactions job always requests a fixed window of default range days (30) ending yesterday. Unlike trades (days_since_last + default_days) it has no catch-up from the last stored date, and worker/catchup.py only re-enqueues a slot missed within the last day. Five months of fees, dividends, interest and deposits missed while ingest was down will never be fetched by any scheduled run, and /flex/ops/check still says ok.
- **Measured**: MEASURED (read-only on bifrost_golden_source). raw_broker.transactions: max(ts) before July is 2026-03-05, next row 2026-08-04, zero rows for both accounts across 5 months, while executions_raw_flex has 129/41/33/23/41 rows for Mar-Jul. Monthly fees and SGOV monthly dividends recur in Jan-Mar and Aug-Oct, so the hole is missing data. ops_jobs.flex_settings default=30, init=270. GET /api/plugin/flex-query/flex/ops/check verdict 'ok' for flex-transactions.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/transactions.py:64` — `from_date, to_date = get_flex_default_range_dates(config, conn)`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/config_rw.py:316` — `days, _ = resolve_flex_range_days(config, trade_conn)`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/trades.py:177` — `total_days = days_since_last + default_days`
- **Impact**: Transfer & Pay and every net cash-flow / performance read (core get_net_cash_flow sums raw_broker.transactions) under-count fees, dividends and interest for Mar-Jul 2026 without any signal. Any future outage longer than 30 days loses data the same way.
- **Fix**: Apply the trades window rule to transactions: from = min(last stored ts per account, yesterday - default_days), capped at 366 days per IB request. One-time manual backfill 2026-03-01..2026-08-05 via from_date/to_date payload after Owner approval. Add a /flex/ops/check coverage rule flagging any month with executions but zero transactions for an account.
- **Ratchet**: Exported metric bifrost_flex_coverage_gap_months (months with executions_raw_flex rows but zero raw_broker.transactions rows, per account) with a Prometheus rule = 0. Unit test: stored max ts 60 days ago must produce a request window reaching back at least 60 days.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-flex-query, bifrost-trade-infra

### TD-89

**P1 · research-data · option_pinned_contract reads the Trade API list keys that api 0.4.0 removed; the 10-06 run saw 0 held legs and 0 executions and reported success**

- **Claim**: load_held_legs reads payload['attributions'] and load_option_executions reads payload['executions']. Trade API 0.4.0 (3545779, TD-16/TD-17) returns {items, count}. The engine skips only on HTTP exceptions, so an empty list is an answer: mode=written, rows_written=0, and the pins froze at the 10-03 state. The sibling copy forecast/terrain_backfill._rows already reads 'items' first, so the copies have drifted; the unit test still feeds the retired keys and stays green. A downstream regression of TD-17, not a duplicate.
- **Measured**: MEASURED. Dagster materializations 09-25..10-03: held_legs 11-12, executions_seen 330-331, rows_written 60-61. 10-06 02:39 UTC: held_legs 0, closed_recent 0, executions_seen 0, rows_written 0, mode 'written'. PROD /executions/position-attribution?sec_type=OPT returns {items:13, count}; /executions returns {items:519,...} with 331 OPT rows. research.option_pinned_contract unchanged since 2026-10-03 02:39 UTC (held 12, closed_recent 64). No option fills since 10-03, so nothing lost yet.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/option_pinned/entry.py:123` — `rows = (payload or {}).get("attributions") or []`
  - `bifrost-research/src/bifrost_research/engines/option_pinned/entry.py:136` — `rows = (payload or {}).get("executions") or []`
  - `bifrost-research/src/bifrost_research/engines/forecast/terrain_backfill.py:77` — `"""A Trade API list: ``items`` (api 0.2.3+), else the route's old key."""`
  - `bifrost-research/tests/engines/test_option_pinned_contract.py:211` — `"attributions": [`
- **Impact**: Latent data loss: the market-data plugin uses these pins to backfill contracts and to exempt them from retention delete. The next option leg opened or closed is never pinned and its bars can age out; closed_recent pins stop refreshing. Every run stays green.
- **Fix**: Read 'items' with the old key as fallback via one shared list helper (move terrain_backfill._rows into mcp/tools/_trade_api_client). Treat 'API answered, zero held legs, while the table holds live held pins' as a raising skip. Update fixtures to the current envelope.
- **Ratchet**: (1) Research tests load Trade API envelopes from one shared fixture (or trade-api OpenAPI in CI); grep ratchet fails on .get("attributions"|"executions"|"transactions") outside the shared helper. (2) Dagster asset check: fail when held_legs = 0 while option_pinned_contract has reason='held' rows with pin_until > now().
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research, bifrost-trade-api

### TD-90

**P1 · market-data · option_contract (and option_backfill_plan) report truncated:true as success; SPX already uses 118 of its 120-page cap because the page size is 250, not 1,000**

- **Claim**: Whole-market handlers raise on truncation; the per-underlying catalogue handlers do not. option_contract stops at 120 pages (index) / 60 pages, writes what it got and returns done with an unchecked 'truncated' field, with no continuation. The real cap is tighter than the comments assume: polygon/endpoints.py defaults limit=250 while client docstring and handler comment assume 1,000 per page, so '120 pages' is 30,000 contracts. The option-bars slot and the doctor's >=95% chain-coverage denominator both come from this catalogue, so a truncated catalogue drops contracts and inflates coverage. option_backfill_plan behaves the same at 200 pages.
- **Measured**: MEASURED in ops_jobs.job_ingest (48h). SPX live runs used 115/118/118/116 pages for 28,690-29,282 contracts (~248 per page), 97.6% of the effective 30,000 cap. SPY 53/60, SNDK 47/60, QQQ 46/60. 0 of 1,525 option_contract/option_backfill_plan jobs truncated yet.
- **Evidence**:
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/ingest/option_contract.py:48` — `max_pages = int(payload.get("max_pages") or (120 if is_index_option_underlying(storage) else 60))`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/ingest/option_contract.py:151` — `"truncated": bool(data.get("truncated")),`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/ingest/option_backfill.py:268` — `"truncated": bool(data.get("truncated")),`
  - `bifrost-platform-plugin-market-data/src/bifrost_market_data/ingest/financials_market.py:27` — `if data.get("truncated"):`
- **Impact**: Within a few listing cycles (new quarterlies/LEAPS) SPX silently loses its catalogue tail (late SPXW far expiries); bars and chains for those contracts stop, and nothing turns red because the coverage denominator shrinks with it.
- **Fix**: Pass limit=1000 for /v3/reference/options/contracts (builder already clamps to 1000): 4x capacity at no request cost; correct the comments. Make option_contract and option_backfill_plan raise on truncated (as _reject_truncation does) or continue from next_cursor.
- **Ratchet**: Worker-level guard: a result with truncated=true fails the job unless the kind is allowlisted as enqueuing a continuation; a registry test iterates build_handler_registry to assert it. Unit test that the contracts page limit equals the per-page figure the cap math assumes. Doctor finding when pages/max_pages > 0.9.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-platform-plugin-market-data

### TD-91

**P1 · flex-ib · A failed cash-transactions write is recorded as a successful run: core returns 0 on any exception and the job counts it as 'ok, 0 rows'**

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

- **Claim**: Eight helpers return the New York date (_today_ny), three return the UTC date (_today in option_universe, option_pinned, terrain_backfill), and 44 date.today() calls return UTC because no research pod sets TZ. db/calendar.fetch_recent_trading_days also defaults to the UTC date. decline_memory.py documents the wrong 'same host' assumption, and the `noqa: DTZ011` there does nothing because ruff selects only E4/E7/E9/F. Anything run by research_trading_day (02:30 UTC) through _today()/date.today() gets the next calendar day.
- **Measured**: MEASURED. No TZ env on research-api, dagster-daemon, dagster-webserver, research-mcp, research-pine or api-research. In dagster-daemon, date.today() = 2026-10-06 while NY was 10-05. research.option_universe: 678 rows last_seen 2026-10-06; entered_on on Saturdays (10-03: 6, 09-26: 9, 09-19: 24). candidate_pool path is latent (writers run when UTC and NY agree).
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/option_universe/entry.py:85` — `return datetime.now(timezone.utc).date()`
  - `bifrost-research/src/bifrost_research/engines/option_universe/entry.py:227` — `"last_seen": as_of if seen else (prev["last_seen"] if prev else as_of),`
  - `bifrost-research/src/bifrost_research/copilot/harness/decline_memory.py:320` — `trade_date=date.today(),  # noqa: DTZ011`
  - `bifrost-research/src/bifrost_research/db/calendar.py:181` — `end = as_of or datetime.now(timezone.utc).date()`
- **Impact**: option_universe stores wrong dates and its liquidity/liveness windows shift a day; any engine adopting date.today() for a session stamp repeats TD-87. Each copy is a place the session rule can drift.
- **Fix**: One session_today() (latest NYSE session <= NY date) and ny_now() in db/calendar.py; replace the 11 helpers and stamp-carrying date.today() calls. Set TZ=America/New_York on Dagster/research pods only as a defensive layer.
- **Ratchet**: Enable ruff DTZ (DTZ005/DTZ011) for src/ with a falling baseline; code-health grep fails on a new `def _today`/`def _today_ny` outside db/calendar.py.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-research

### TD-99

**P2 · research-control · No scheduler liveness alarm: a stopped, renamed or never-ticking Dagster schedule, or a hung daemon, produces no alert; no PrometheusRule targets research**

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

- **Claim**: engines/volatility/surface.py writes with batch_upsert on (symbol, trade_date, expiry) and has no DELETE; expiries a later re-walk no longer produces keep the old fit beside the new one. Same class already fixed for signal_hit, gex, flow, pcr and max_pain.
- **Measured**: MEASURED. 122 rows in 98 of 12,635 (symbol, trade_date) groups are >1h older than their group's newest fit, up to 6d 21h; span 2026-07-14..09-03; only 10 are 0DTE.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/volatility/surface.py:588` — `conflict_keys=("symbol", "trade_date", "expiry"),`
- **Impact**: Small but wrong: surface reads for those days mix two fits; class stays open for any expiry-filter change.
- **Fix**: Delete-then-insert per (symbol, trade_date) in one transaction; one-off cleanup of the 122 rows (Research-owned).
- **Ratchet**: code-health metric listing batch_upsert targets whose conflict key is wider than (symbol, trade_date) with no DELETE in the module; fails on a new one without an allowlist comment.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-113

**P3 · research-data · Playbook trigger emission fails with no log in four places; a failed previous-state lookup records a fresh 'snapshot' instead of comparing**

- **Claim**: emit_triggers_for_session and emit_triggers_for_terrain_intraday are wrapped in `except Exception: rollback; pass` with no logger (playbook.py:529, scheduler/engines.py:341); their previous-state lookups (playbook.py:756, 827) also swallow and fall back to prev=None, which emits a first-observation 'snapshot'. Representative of 99 broad except handlers with no logger and no raise in engines/lenses/repositories/db/scheduler/orchestration.
- **Measured**: MEASURED healthy today: stock_signal_playbook_trigger_intraday ~2,000 rows over ~700 symbols per session 09-23..10-05. Swallows CODE-READ. AST census: 99 silent broad-except handlers.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/forecast/playbook.py:529` — `# Trigger log is best-effort — do not fail the forecast write path`
  - `bifrost-research/src/bifrost_research/scheduler/engines.py:341` — `except Exception:`
  - `bifrost-research/src/bifrost_research/engines/forecast/playbook.py:827` — `except Exception:`
- **Impact**: If the trigger table breaks (grant, DDL drift, partition) the trigger log stops with no trace and readers see 'no transitions'.
- **Fix**: Keep the forecast path best-effort but log.warning with symbol and exception and count trigger_failures into the slot result for the asset check.
- **Ratchet**: Silent-swallow AST metric in code-health (broad except with no logger and no raise), research baseline 99, may only fall.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

### TD-114

**P3 · flex-ib · raw_broker.commissions mixes two sign conventions: Flex writes cost as negative, the TWS/gateway path writes it as positive**

- **Claim**: Flex stores ibCommission as IB sends it (negative charge, positive rebate); the TWS commissionReport path writes IB API's positive cost into the same column and key. Flex re-imports overwrite to the Flex sign; TWS-only fills keep the opposite sign. No reader normalises (accounts_helpers.py:402-404 adds commission into period totals).
- **Measured**: MEASURED. Flex-backed: 435 negative, 15 positive (all rebates matching net_cash - proceeds to 4 dp), 32 NULL. TWS-only: 4 positive (~1.04-1.05), 0 negative, 33 NULL. 12 orphan commission rows. Reading TWS positives as costs relies on IB API docs.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/client/flex_client.py:551` — `commission = _f("ibCommission")`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1053` — `INSERT INTO {GOLDEN_COMMISSIONS} (exec_id, commission, currency, realized_pnl, yield_, yield_redemption_date)`
- **Impact**: Small amounts today, but per-trade cost and PnL reads including TWS-only fills get the cost sign backwards.
- **Fix**: Normalise at write time (keep Flex sign, negate TWS commissionReport value), backfill TWS-only rows, decide on the 12 orphans.
- **Ratchet**: Data-gaps/doctor SQL check: no exec_id whose commission sign disagrees with sign(net_cash - proceeds - taxes) on its Flex row; unit test on the TWS writer's sign.
- 审批 不用批 · 代价 S · 风险 med · repos: bifrost-trade-core

### TD-115

**P3 · flex-ib · Money-path tests missing: cash parser untested, cash upsert tested only on connect failure (pinning the silent 0), Flex branches of the executions writer untested; commission INSERT in four copies**

- **Claim**: No test of parse_cash_transactions_xml. upsert_account_transactions is tested only in test_connect_helpers.py:118, asserting the silent 0. write_account_executions_to_db is reached only for contract keys; the synthetic flex_{account}_{tradeID} exec_id, the executions_raw_flex conflict update and the commission keep-nonzero upsert have no test. The commission INSERT exists four times (accounts.py 1053, 1122, 1240, 1554).
- **Measured**: CODE-READ grep of both test trees; live: all 33 BookTrade rows carry flex_* synthetic ids, so the branch is in use.
- **Evidence**:
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:812` — `exec_id = f"flex_{account_id}_{trade_id}"`
  - `bifrost-trade-core/src/bifrost_core/portfolio/reader/accounts.py:1053` — `INSERT INTO {GOLDEN_COMMISSIONS} (exec_id, commission, currency, realized_pnl, yield_, yield_redemption_date)`
- **Impact**: Changes to executions, commissions and cash ledgers ship unverified; TD-91 and TD-103 are bugs these tests would have caught.
- **Fix**: Fixture-driven tests with made-up values (never DEV data): attribute-only CashTransaction XML, ExchTrade/BookTrade XML, commission 0 then non-zero. Fold the four commission upserts into one helper.
- **Ratchet**: code-health contract-coverage metric: each public writer in bifrost_core.portfolio.reader.accounts named in at least one test (falling baseline); duplication ratchet on the commission upsert.
- 审批 不用批 · 代价 M · 风险 low · repos: bifrost-trade-core, bifrost-platform-plugin-flex-query

### TD-116

**P3 · flex-ib · The Flex ingest routes query-id, stats and range-day reads through the DEV DB (bifrost_dev) via FDW, with silent fallbacks that can widen the run to 270 days**

- **Claim**: The plugin's trade_postgres is bifrost_dev; brokerage.settings_flex and brokerage.executions there are FDW views back to raw_broker on Golden Source, which the plugin already connects to. open_trade_conn falls back silently to core connection params; get_flex_executions_stats turns any error into count=0, which switches the run to init mode (270-day window, extra IB requests against the 1018 throttle).
- **Measured**: MEASURED: live ConfigMap trade_postgres dbname bifrost_dev; in bifrost_dev brokerage.executions is a view and settings_flex a foreign table on golden_source_server; flex_writer already has SELECT on raw_broker.settings_flex in GS. No failure in history.
- **Evidence**:
  - `bifrost-platform-plugin-flex-query/k8s/base/configmap.yaml:18` — `dbname: bifrost_dev`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/config_rw.py:93` — `return psycopg2.connect(**get_conn_params(config))`
  - `bifrost-platform-plugin-flex-query/src/bifrost_flex_query/orchestration/config_rw.py:351` — `return {"count": 0, "accounts": 0, "min_date": None, "max_date": None}`
- **Impact**: A DEV clone, FDW change or grant reset can stop or widen the real-account ingest: DEV sits upstream of PROD-grade data.
- **Fix**: Read settings_flex and execution stats from GS raw_broker directly; drop trade_postgres once the legacy range-day fallback is removed; make stats failure raise.
- **Ratchet**: Config test fails if any plugin config section names bifrost_dev/stg/prod; test that get_flex_executions_stats errors propagate.
- 审批 不用批 · 代价 M · 风险 med · repos: bifrost-platform-plugin-flex-query

### TD-117

**P3 · flex-ib · 'Latest Flex date in DB' after an import is one run behind: read through FDW in the same transaction as the pre-import read**

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

- **Claim**: Five plugin scripts reference the retired ib-operator/ib-market-gateway/ib-account-agent StatefulSets, plus per-wave verify-trade-ib-w{1,2,3}-* scripts, although TIBM rollout scripts already moved to scripts/archive. The flex repo keeps golden_source_flex_ops_compat_views.sql and drop_trade_flex_ops_legacy.sql for a flex_ops schema that does not exist. Current-gateway verify scripts (verify-ib-gateway*.sh, verify-redis-ib.sh) are live.
- **Measured**: MEASURED: no sts/deploy named ib-operator/ib-market-gateway/ib-account-agent; pg_namespace has no flex_ops.
- **Evidence**:
  - `bifrost-platform-plugin/scripts/verify-trade-cutover.sh:17` — `LEGACY_STS=(ib-market-gateway ib-account-agent ib-operator)`
- **Impact**: Readers and agents treat these as live procedures.
- **Fix**: Move TIBM-wave and cutover verify scripts with Makefile targets into scripts/archive; delete the two flex_ops SQL files and their CLAUDE.md mention on Owner approval; trade-api service rows are retargeted under TD-104.
- **Ratchet**: Per-repo CI grep ratchet: references to ib-operator/ib-market-gateway/ib-account-agent outside scripts/archive, falling baseline.
- 审批 删除（要你批） · 代价 S · 风险 low · repos: bifrost-platform-plugin, bifrost-platform-plugin-flex-query, bifrost-trade-api

### TD-126

**P3 · ops-platform · Build Desk (Ops Console Engineer strip: Briefing / In Flight / Delivery) is a Cursor-era program tracker nobody uses**

- **下一步**：Owner 2026-10-06：倾向删除；拆解清单在修法里，点头后执行。
- **Claim**: Build Desk tracks phased programs from config/programs/*.yaml, lanes from config/lanes.yaml and runtime JSON in $PLATFORM_DATA_DIR/programs (emptyDir in the cluster, wiped on restart), and writes data/briefing/active-pack.md for Cursor's /briefing. No program YAML changed since 2026-09-08, local runtime state since 09-14, the briefing pack since 08-13; three active programs still have every phase pending. Claude Code sessions do not use it (memory, workflows, release.sh).
- **Measured**: git log on bifrost-platform origin/main 1a3327e; data/ file dates on the Mac (2026-10-06).
- **Evidence**:
  - `bifrost-platform/console/src/lib/consoleNavConfig.ts:87` — `ENGINEER_LIFECYCLE_ITEMS`
  - `bifrost-platform/api/internal/devagent/store.go:119` — `programs/*.json`
- **Impact**: About 17.5k console LOC, 4.5k Go LOC, 4k test LOC and 16 MCP tools to keep compiling and reviewing for a workflow that no longer runs; its sidebar badges suggest work queues that are stale.
- **Fix**: Delete the three Build Desk pages, lib/briefing, components/briefing, the Build Desk part of components/delivery, the devagent/lanes/briefing/sessions/sessionsnapshot Go packages, their MCP tools, config/lanes.yaml and config/programs. Untangle first: the operate queue and post-completion → operate hand-off are shared with Ops Desk; skills phase-execution / batch-execution (both sides) and CLAUDE.md §5 point at /programs; verify-three-desks.mjs, consoleNavZones.test.ts and navLens.test.ts assert the label.
- **Ratchet**: Code-health 'unused route' check for platform-api (route with no console/MCP caller fails), same as the trade-api route listing.
- 审批 删除（要你批） · 代价 M · 风险 med · repos: bifrost-platform, bifrost-trade-infra

### TD-128

**P3 · research-data · Pine signal rows mix adjustment bases: nightly runs rewrite only the last ~10 sessions on today's adjusted bars, older rows stay on the basis of their last full rebuild**

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

- **Claim**: `_pick_option` reads candidate contracts from raw_market.option_daily. Since mid-August 2026 option_daily keeps about ten strikes either side of spot per expiry, so a 20–30 delta leg 30–45 days out is usually missing and the nearest remaining strike (often 35–40 delta) is priced instead, with no skip or flag. The simulator (0.175.0) and the suggestion ledger (0.174.1) fill from the 16:00 option_snapshot and skip off-target picks; the event backtest does not.
- **Measured**: Thread B 2026-10-06 on the simulator path: without the fill a 20-delta SPY put picked −0.35, QQQ −0.38 (2026-08-17..10-02); with it −0.20 ± 0.003. The event backtest path shares the option_daily source.
- **Evidence**:
  - `bifrost-research/src/bifrost_research/engines/backtest/event_query.py:781` — `_pick_option`
  - `bifrost-research/src/bifrost_research/engines/backtest/event_query.py:823` — `FROM raw_market.option_daily`
- **Impact**: Event backtests of delta-targeted structures after mid-August run a different trade than the template names.
- **Fix**: Read the snapshot day bars where option_daily lacks the contract (walk.snapshot_day_bars) and skip legs further than 0.05 from the target delta, counting the skip.
- **Ratchet**: A test with an option_daily chain thinned to ATM ±10 strikes that asserts either the target delta within 0.05 or an off-target skip.
- 审批 不用批 · 代价 S · 风险 low · repos: bifrost-research

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
