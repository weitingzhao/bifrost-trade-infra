# Bifrost Trade 迁移进度追踪

> **目标**：完全替代 `bifrost-trader-engine`，在功能和业务上实现完整重构。所有新代码在 `bifrost-trade-*` 各仓库中实现。当所有模块迁移完成并通过验证后，`bifrost-trader-engine` 将退役。

## 状态定义

| 状态 | 含义 |
|------|------|
| - | 未开始 |
| WIP | 进行中 |
| DONE | 已完成（代码已迁移） |
| VERIFIED | 已验证（测试通过，可运行） |

---

## §1 总览

| 目标 Repo | 模块数 | 已完成 | 进度 |
|-----------|--------|--------|------|
| bifrost-trade-core | 6 | 6 | **VERIFIED**（2026-06-05）— `make test` 146 passed（`not ib and not db`） |
| bifrost-trade-socket | 5 | 5 | **VERIFIED**（2026-06-04）— 23 tests（`not ib`）；`@pytest.mark.ib` 烟雾可选 |
| bifrost-trade-worker | 3 | 3 | **VERIFIED**（2026-06-04）— daemon + celery；189 tests（`not ib and not db`） |
| bifrost-trade-api | 9 | 9 | **Phase 2B CLOSED**（2026-06-04）— 9/9 域 CUTOVER + Owner 签字；Dev `VITE_API_*` → 8765–8773 |
| bifrost-trade-frontend | 4 | 4 | **Phase 2B CLOSED**（2026-06-04）— New Frontend + New API 9/9 域 Owner 签字完成 |

> **Phase 2B CLOSED**（2026-06-04）· **2C-A CLOSED**（2026-06-08）· **K3s STG v2 SIGNED**（2026-06-18）· **Data layer CNPG**（2026-06-29，`.80` 下线）· **Phase 3 Legacy retirement SIGNED**（2026-06-29，决策 D8 — `bifrost-trader-engine` NAS 归档只读）· **Platform IB Gateway + TIBM Rollout**（2026-07-04，Console IBGP/TIBM 全链签收；K3s prod 经 `bifrost-deliver-prod`；legacy IB socket STS 退役；D10 live trading 仍 BLOCKED）

### §1.1 Platform IB Gateway（K3s · 替代 legacy trade-socket IB）

| 组件 | 位置 | 状态 | 说明 |
|------|------|------|------|
| redis-ib + ACL | `data/redis-ib` · bifrost-platform-plugin | **VERIFIED** | Trade NS ExternalName → `redis-ib.data` |
| ib-gateway (live) | `data/ib-gateway` · client_id host **70** / secondary **72** | **VERIFIED** | 替代 ib-market-gateway / ib-operator / ib-account-agent STS |
| Trade 读路径 | bifrost-prod `api-market` → redis-ib | **VERIFIED** | `verify-trade-quotes-e2e` · Monitor `platform_ib_gateway` |
| Celery bars RPC | bifrost-prod `celery-worker` → operator stream | **VERIFIED** | `use_for_celery_bars: true` · gateway RPC |
| Legacy socket STS | bifrost-{dev,stg,prod} | **RETIRED** | Argo 不再拉起；Deliver-prod 不恢复 STS |
| D10 live trading | daemon bifrost-prod | **BLOCKED** | observe-safe；W-block 未 unlock |

GitOps live overlay: `bifrost-platform-plugin/k8s/ib-gateway/overlays/live/` · 验收: `make verify-ib-gateway-program` · `make verify-trade-ib-rollout-prod`

### §1.2 Market Data Golden Source — related tickers / ticker types / stock snapshot

| 项 | 状态 | 说明 |
|----|------|------|
| `market.ticker_related` | **DONE**（2026-08-19） | Plugin ingest `kind=ticker_related` + CronJob `related-rotate` |
| Trade FDW (related) | **DONE** | `MARKET_FOREIGN_TABLES` 含 `ticker_related`；Research ticker-overview 读 FDW |
| `public.ticker_related_tickers` | **RETIRED** | Core DDL DROP；历史数据回填进 Golden Source |
| `market.ticker_type` | **DONE**（2026-08-19） | Plugin ingest `kind=ticker_type`（全量字典，手动 enqueue） |
| Trade HTTP (types) | **DONE** | Plugin `/reference/ticker-types`；Core 删直连 SQL |
| `public.ticker_types` | **RETIRED** | Core DDL DROP；字典迁入 Golden Source |
| `market.stock_snapshot` coverage | **DONE**（2026-08-20） | Plugin `/market/readiness/snapshot-coverage` + `/market/readiness/vendor-gap`；STG/DEV/PROD 全环境 E2E 验证 |
| `public.cache_stock_snapshot` | **RETIRED**（2026-08-20） | Core DDL DROP；Trade readiness 改读 Plugin HTTP；Plugin 0.7.0 / Core 0.10.2；db-init 已在 STG/DEV/PROD 执行（表不存在） |
| Tekton smoke tag isolation | **DONE**（2026-08-20） | `bifrost-build-stg` / kaniko smoke tasks 默认 tag `:stg` → `:smoke`，避免覆盖真实交付镜像 |

---

## §2 bifrost-trade-core（共享库 · 无进程入口）

### §2.1 共享库模块

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| config | `src/config/` | `bifrost_core/config/` | settings.py, yaml_config.py | **VERIFIED** |
| core | `src/core/` | `bifrost_core/core/` | dict_merge, redis_url, logging, realtime/redis_*, sse/queue_utils | **VERIFIED** |
| persistence | `src/persistence/` | `bifrost_core/persistence/` | status_sink, postgres/{connection, ddl, postgres_sink, accounts_sync, ticker_reference} | **VERIFIED** |
| portfolio | `src/portfolio/` | `bifrost_core/portfolio/` | accounts, symbol_position, model/{core, payoff}, positions/{portfolio, position_book}, reader/*, services/* | **VERIFIED** |
| ib_operator (client) | `src/ib_operator/` | `bifrost_core/ib_operator/` | client.py, protocol.py, config.py | **VERIFIED** |
| monitor | `src/monitor/` | `bifrost_core/monitor/` | self_check, reader/{status, strategy, gate_safety, watchlist, market, massive_jobs, ...}, schemas/*, services/* | **VERIFIED** |

---

## §3 bifrost-trade-socket（WebSocket 边缘服务）

### §3.1 IB 子域（`src/bifrost_socket/ib/`）

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| connector | `src/ib/`, `src/connector/` | `bifrost_socket/ib/connector/` | connection_policy.py, ib.py（`flex_client.py` → Flex Query Plugin `0.2.0`） | **VERIFIED** |
| ingestor | `src/vendor/ib_ingestor/` | `bifrost_socket/ib/ingestor/` | writer.py, redis_keys.py | **VERIFIED** |
| account_agent | `src/vendor/ib_account_agent/` | `bifrost_socket/ib/account_agent/` | writer.py, redis_keys.py | **VERIFIED** |
| operator | `src/ib_operator/` (service) | `bifrost_socket/ib/operator/` | service.py, executor.py, redis_io.py, health_redis.py | **VERIFIED** |
| connection_lifecycle | `run_ib_*` probe + heartbeat + reconnect | `bifrost_socket/ib/connection_lifecycle.py` | `IbBrokerLifecycleConfig`, `ServiceHeartbeatClock`, `heartbeat_reconnect_*`, Message 发布；三服务共用 | **VERIFIED**（2026-06-04） |
| message_center | `src/bifrost/message_center.py` (`IbConnectionStatusTracker`) | `connection_lifecycle` + ingestor/account_agent/operator `_push_health` | Redis `bifrost:msg:center:events` → Monitor SSE → UI Messages | **VERIFIED**（2026-06-05） |

### §3.2 Massive 子域（`src/bifrost_socket/massive/`） — **RETIRED (P7)**

> Trade `massive-ws` / socket `massive/` package retired. Polygon Options WS + public REST ingest →
> **Market Data Plugin** (`bifrost-platform-plugin-market-data`: `polygon-ws-ingestor` → `redis-massive`).
> Rows below are migration archaeology only.

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| massive_ws | `scripts/systemd/run_massive_ws.py` | `bifrost_socket/massive/` | massive_ws_ingestor.py, redis_writer.py, subscription_manager.py | **RETIRED (P7 → Plugin)** |

---

## §4 bifrost-trade-api（9 个 FastAPI 域）

| 域 | 端口 | engine 源 | 目标路径 | 主要文件 | 状态 |
|----|------|----------|----------|---------|------|
| monitor | 8765 | `backend/monitor/` | `bifrost_api/monitor/` | app.py, routers/{status, daemon, config, core, logs, messages} | **CUTOVER** |
| massive | 8766 | `backend/massive/` | `bifrost_api/massive/` | app.py, deps.py, sse.py, routers/{routes, stream} | **RETIRED (P7 → Market Data Plugin)** |
| docs | 8767 | `backend/docs/` | `bifrost_api/docs_api/` | app.py, merge_openapi.py | **CUTOVER** |
| ops | 8768 | `backend/ops/` | `bifrost_api/ops/` | app.py, auth.py, worker_profiles, agent/*, routers/{workers, job_queues, market_ingest}, services/* | **CUTOVER** |
| trading | 8769 | `backend/trading/` | `bifrost_api/trading/` | app.py, routers/executions | **CUTOVER** |
| strategy | 8770 | `backend/strategy/` | `bifrost_api/strategy/` | app.py, routers/strategies | **CUTOVER** |
| portfolio | 8771 | `backend/portfolio/` | `bifrost_api/portfolio/` | app.py, routers/{config, model} | **CUTOVER** |
| market | 8772 | `backend/market/` | `bifrost_api/market/` | app.py, routers/{quotes, watchlist, market_data} | **CUTOVER** |
| research | 8773 | `backend/research/` + `src/research/sepa/` | `bifrost_api/research/` | app.py, sepa/*, screener/*, indicators/*, routers/{screener, greeks, max_pain, option_discovery, data_readiness, sepa_*} | **CUTOVER** |

> **research 域（8773）**：SEPA 四阶段筛选引擎 + 回测 + 历史 Greeks，完整业务逻辑在本 repo 的 `bifrost_api.research` 内实现（含 sepa / screener / indicators 子模块）。

---

## §5 bifrost-trade-worker（Daemon + Celery 数据管道）

### §5.1 交易 Daemon

| 子模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|--------|----------|----------|---------|------|
| app | `src/daemon/app/` | `bifrost_worker/daemon/app/` | gs_trading.py, entry.py, hedge_flow.py, daemon_handlers.py, snapshot.py, ticker_redis.py | - |
| fsm | `src/daemon/fsm/` | `bifrost_worker/daemon/fsm/` | daemon_fsm.py, trading_fsm.py, hedge_fsm.py, events.py | - |
| guards | `src/daemon/guards/` | `bifrost_worker/daemon/guards/` | execution_guard.py, trading_guard.py | - |
| execution | `src/daemon/execution/` | `bifrost_worker/daemon/execution/` | order_manager.py | - |
| strategy | `src/daemon/strategy/` | `bifrost_worker/daemon/strategy/` | gamma_scalper.py, hedge_gate.py | - |
| pricing | `src/daemon/pricing/` | `bifrost_worker/daemon/pricing/` | black_scholes.py, greeks.py | - |
| market | `src/daemon/market/` | `bifrost_worker/daemon/market/` | market_data.py | - |
| core/state | `src/daemon/core/` | `bifrost_worker/daemon/core/` | store.py, metrics.py, state/{classifier, composite, enums, snapshot} | - |
| account_sync | `src/daemon/account_sync/` | `bifrost_worker/daemon/account_sync/` | app.py, diff_engine.py, heartbeat.py, redis_keys.py, stream_consumer.py | - |
| sink | `src/daemon/sink/` | `bifrost_worker/daemon/sink/` | (postgres sink 实现) | - |

### §5.2 Celery 数据管道

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| celery | `src/workers/` | `bifrost_worker/celery/` | celery_app.py, celery_queue_names.py, beat_schedule | - |
| bars | `src/bars/` | `bifrost_worker/data/bars/` | tasks.py, backfill.py, ib_operator_transport.py | - |
| massive | `src/massive/` | `bifrost_worker/data/massive/` | tasks.py, celery_queues.py, massive_job_goal, snapshot_chain_ingest, stock_ohlc_daily_smart, option_*_pool_fill | - |
| massive vendor | `src/vendor/massive/` | `bifrost_worker/data/massive/` | client.py, config.py, reader.py, holidays_sync.py, stock_day_gap.py, contracts_reference_* | - |

---

## §6 bifrost-trade-frontend（React 前端）

**阶段状态**：**Phase 1 CLOSED**（2026-06-04）— 见 [PHASE1_SIGNOFF_MASTER.md](../bifrost-trade-frontend/docs/PHASE1_SIGNOFF_MASTER.md)、[IB_CONNECTION_ACCEPTANCE.md](../bifrost-trade-frontend/docs/IB_CONNECTION_ACCEPTANCE.md)。

### §6.1 基础设施

| 项目 | engine 源 | 状态 |
|------|----------|------|
| index.html + tsconfig | `frontend/` | **DONE** |
| main.tsx + App.tsx | `frontend/src/` | **DONE** |
| styles/ (5 CSS) | `frontend/src/styles/` | **N/A** — 已斩断至 `index.css` + Tailwind（见 `LEGACY_CSS_CUTOFF.md`） |
| public/ | `frontend/public/` | **DONE** |

### §6.1.2 Frontend Legacy CSS 斩断（迁移前基线）

| 项目 | 说明 | 状态 |
|------|------|------|
| `src/lib/chartTokens.ts` | SVG 轴/底使用 `--foreground` / `--card` / `--muted-foreground` / `--border` | **DONE** |
| Discovery 表与 IV Term | shadcn `Table` / `ToggleGroup` / `Checkbox`；无 `data-table` / `od-iv-*` 布局类 | **DONE** |
| `discoveryCharts.css` | 仅 chart-expand + SVG `aspect-ratio`（&lt;200 行） | **DONE** |
| `index.css` | 删除 Legacy monitoring 别名与 `--space-*` / `--text-*` 块 | **DONE** |
| 路由懒加载 | Settings / Strategy（除 Instances）/ Operations / Research（除 Watchlist）/ 大部分 Portfolio | **DONE** |
| 机械检查 | `docs/LEGACY_CSS_CUTOFF.md` | **DONE** |
| Legacy CSS 渐进偿还（Phase 0–3） | `npm run check:legacy-css`；Ledger 628 行、Live 246、InstanceDetail 140、instances 表 147；`docs/LEGACY_CSS_PAYDOWN.md` | **DONE**（2026-05-31） |
| Legacy CSS 偿还（Phase 4–5 余量） | Phase 4.9 Instance Detail + Phase 5 module 删除；`check-legacy-css` guards | **DONE**（2026-06-03） |

### §6.1.1 布局基元（Phase 1 全站 UI 画布）

| 项目 | 说明 | 状态 |
|------|------|------|
| PageShell / PageHeader / PageSection | `src/components/layout/`；AppLayout + SettingsLayout `bg-card` | **DONE**（扫尾 2026-05-31） |
| Card `variant="elevated"` | Accounts、Positions/Performance 图表、Stock Data Readiness 等 canvas 抬高层 | **DONE**（扫尾 2026-05-31） |
| PageHeader 全站统一 | ~30 个 `PageShell` 页 + Watchlist 子 header；`titleSize=large` 用于 Live/Instances 等 | **DONE**（扫尾 2026-05-31） |
| RouteErrorPage | `bg-card` + 英文 UI | **DONE**（扫尾 2026-05-31） |
| Discovery 外壳 | `PageShell` + `option-discovery-root`；无 `legacy-monitoring-shell` | **DONE**（Phase 2） |
| Discovery 页头 / 基元 | `DiscoveryPageHeader`（`PageHeader` + breadcrumb）、`DiscoveryHint` / `DiscoveryIconButton` / `DiscoverySection`；`useDiscoveryNav` | **DONE**（Phase 2） |
| Discovery CSS | Phase 2b：删除 `discoveryScoped` / `discoveryStrikeLadder` / `discoveryShell`；仅 `discoveryCharts.css`（gzip ~4.7 kB）+ Tailwind 组件 | **DONE**（见 `docs/PHASE2_DISCOVERY_ACCEPTANCE.md`） |
| Frontend Legacy CSS 斩断 | `chartTokens.ts`；IV Term / Compare / BS 表 Tailwind；`discoveryCharts.css` &lt;200 行；删 `index.css` Legacy 别名；路由懒加载 | **DONE**（2026-05-31，见 `docs/LEGACY_CSS_CUTOFF.md`） |
| Discovery 功能目视 | 与 Legacy 同 API 对照验收 | **Batch 3 Owner signed**（2026-06-03；`PHASE2_DISCOVERY_ACCEPTANCE.md`） |
| 目视验收清单 | [PHASE1_SIGNOFF_MASTER.md](../bifrost-trade-frontend/docs/PHASE1_SIGNOFF_MASTER.md)（6 批次）+ [PHASE1_UI_ACCEPTANCE.md](../bifrost-trade-frontend/docs/PHASE1_UI_ACCEPTANCE.md) | **Phase 1 CLOSED**（2026-06-04）— Batch 1–6 + Cross-cutting + IB parity + smoke |
| IB Connection 验收 | [IB_CONNECTION_ACCEPTANCE.md](../bifrost-trade-frontend/docs/IB_CONNECTION_ACCEPTANCE.md) | **VERIFIED**（2026-06-04） |
| IB Broker Connection 对齐 | core `ib_socket_status` + socket Redis writers + api `status.py` + frontend `IbBrokerConnection` | **VERIFIED**（2026-06-04；三服务 host/secondary 统一形状；AA `host_ib_probe_*`；Operator 无 probe 后台线程） |

### §6.1.3 分栏符合度治理（2026-05-31）

按侧栏 Menu 五维检查（D/K/S/U/F，满分 10）的架构扫尾；详见计划「Frontend 分栏符合度检查表」。

| 栏目 | 治理要点 | 状态 |
|------|----------|------|
| Research | Discovery hooks + `discovery/*`；Watchlist / Screener / Greeks / Stock Data / Risk | **Batch 3 Owner signed**（2026-06-03） |
| Portfolio | `useTradeLedgerModel`、`useTradeLedgerHandlers`；Performance `pages/portfolio/performance/*`；Trade Ledger `TradeLedgerPage.tsx` + `ledger/*` | **VERIFIED（Batch 2 Owner 2026-06-03）** |
| System | ApiHealth → `ApiHealthPage.tsx` + `settings/apiHealth/*`（Phase 4.16 Dense UI + **4.17 parity**）；Daemon → `settings/daemon/*`；Socket → `settings/socket/*`（Phase 4.18） | **Batch 5 Owner signed**（2026-06-03） |
| Strategy | `useOptionCategory*`；`optionCategory/*` Dense UI 拆分（Phase 4.15） | **Batch 4 Owner signed**（2026-06-03） |
| Settings | Subscribe 三 Tab；Coverage Overview/Option/Stock IB；Feed 子路由；`/settings/ib` | **Batch 6 Owner signed**（2026-06-03–04；IB parity 见 `IB_CONNECTION_ACCEPTANCE.md`） |
| 横切 | Global strip、settings 无 strip、sidebar lamp、canvas 分层、无 data regression | **Cross-cutting Owner signed**（2026-06-03） |

### §6.2 API 客户端模块

> 新 repo 合并重组为 **22** 个 `src/api/**/*.ts` 文件（非 engine 31 文件一一对应）；Phase 2B 起 Dev `VITE_API_*` 指向新 API（8765–8773）。

| 域 | 新 repo 文件 | engine 源 | 状态 |
|----|-------------|----------|------|
| monitor + control + logs + messages | `monitor.ts`, `apiControl.ts`, `logs.ts`, `messages.ts` | `frontend/src/api/monitor/` | **DONE** |
| market + watchlist/bars | `market.ts` | `frontend/src/api/market/` | **DONE** |
| ops + celery | `ops.ts`, `celeryConsole.ts` | `frontend/src/api/ops/` | **DONE** |
| portfolio | `portfolio.ts` | `frontend/src/api/portfolio/` | **DONE** |
| research + data readiness + discovery | `research.ts`, `research/*` | `frontend/src/api/research/` | **DONE** |
| massive + feeds | `massive.ts`, `massive/*` | engine massive + account sidecar 等 | **DONE** |
| strategy | `strategy.ts` | `frontend/src/api/strategy/` | **DONE** |
| trading + executions | `trading.ts` | `frontend/src/api/trading/` | **DONE** |
| docs + api health probes | `docs.ts`, `apiHealthProbes.ts` | `frontend/src/api/` 合并 | **DONE** |

### §6.3 页面组件（45 个顶层 Page）

| 页面 | engine 源 | 状态 |
|------|----------|------|
| LivePage | `pages/market/live/*` | **VERIFIED（Batch 1 Owner 2026-06-03）** |
| AccountsPage | `portfolio/AccountsPage.tsx` + `accounts/*` | **VERIFIED（Batch 1 Owner 2026-06-03）** |
| OptionScreenerPage | `research/ScreenerPage.tsx` + `optionScreener/*` | **Batch 3 Owner signed**（2026-06-03） |
| StockScreenerPage | `research/StockScreenerPage.tsx` + `stockScreener/*` | **Batch 3 Owner signed**（2026-06-03） |
| StockWatchlistPage | `research/StockWatchlistPage.tsx` + `watchlist/*` | **Batch 3 Owner signed**（2026-06-03） |
| StockDataPage | `research/StockDataPage.tsx` | **Batch 3 Owner signed**（2026-06-03） |
| OptionDiscoveryPage | `research/DiscoveryPage.tsx` + `discovery/*` | **Batch 3 Owner signed**（2026-06-03；`PHASE2_DISCOVERY_ACCEPTANCE.md`） |
| OptionGreeksPage | `research/GreeksPage.tsx` + `greeks/*` | **Batch 3 Owner signed**（2026-06-03） |
| ResearchRiskAnalysisPage | `research/RiskModelPage.tsx` | **Batch 3 Owner signed**（2026-06-03） |
| PositionsPage | `portfolio/PositionsPage.tsx` + `charts/*` + `buildInstanceGroups` / `buildInstanceAllGroups`（position-attribution API） | **VERIFIED（Batch 1 Owner 2026-06-03）** |
| TradeHistoryPage | `portfolio/TradeLedgerPage.tsx` + `ledger/*` | **VERIFIED（Batch 2 Owner 2026-06-03）** |
| PerformancePage | `portfolio/PerformancePage.tsx` + `performance/*` | **VERIFIED（Batch 2 Owner 2026-06-03）** |
| SettingsPage | `frontend/src/pages/` | **N/A** — 拆为 `SettingsLayout` + 子路由（Batch 6 已验） |
| TransferPayPage | `portfolio/TransferPayPage.tsx` | **VERIFIED（Batch 2 Owner 2026-06-03）** |
| ModelAnalysisPage | `portfolio/ModelAnalysisPage.tsx` + `modelAnalysis/*` | **VERIFIED（Batch 2 Owner 2026-06-03）** |
| BacktestPage | `research/BacktestPage.tsx` | N/A — both Legacy/New placeholder |
| StrategyStructurePage | `frontend/src/pages/` → `strategy/StructuresPage.tsx` + `StructuresTable` + `structures/*`（Dense 双表 + SegmentControl；Phase 4.11） | **VERIFIED（Batch 4 Owner 2026-06-03）** |
| StrategyOpportunityPage | `frontend/src/pages/` → `strategy/OpportunitiesPage.tsx` + `OpportunitiesTable` + `opportunities/*`（Dense 列表 + SegmentControl；Phase 4.12） | **VERIFIED（Batch 4 Owner 2026-06-03）** |
| StrategyInstancesPage | `strategy/InstancesPage.tsx` + `instances/*` + `InstanceDetailSidebar`（Phase 4.9 Dense 2026-06-03） | **VERIFIED（Batch 1 Owner 2026-06-03）** |
| StrategyWinRatePage | `frontend/src/pages/` → `strategy/WinRatePage.tsx` + `components/strategy/winRate/*`（winRateUi + Card elevated；Phase 4.10 KPI 卡片网格） | **VERIFIED（Batch 4 Owner 2026-06-03）** |
| StrategyAllocationPage | `frontend/src/pages/` → `strategy/AllocationsPage.tsx` + `AllocationsTable` + `allocations/*`（Dense 双 Switch + monitor Current active；Phase 4.14） | **VERIFIED（Batch 4 Owner 2026-06-03）** |
| GatesConfigPage | `frontend/src/pages/` → `strategy/GatesPage.tsx` + `gates/*`（Dense 双 Card + GatesTable + GateSafetyFormSheet；Phase 4.13） | **VERIFIED（Batch 4 Owner 2026-06-03）** |
| StructureTypeConfigPage | `strategy/OptionCategoryPage.tsx` + `optionCategory/*` | **VERIFIED（Batch 4 Owner 2026-06-03）** |
| DaemonStatusPage (`/operations/daemon`) | `frontend/src/pages/status/` + `DaemonEngineOpsSection.tsx` → `settings/DaemonStatusPage.tsx` + `settings/daemon/*` | **VERIFIED（Batch 5 Owner 2026-06-03）** |
| IbEventSubscribePage (Settings) | `frontend/src/pages/` → `settings/SubscribePage.tsx` + `settings/subscribe/*`（三 Tab Dense UI、`postReleaseTickerSubscriptions`、`useSubscribeExecutions` limit 20） | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| CeleryControlPage (Settings) | `frontend/src/pages/celery/` → `operations/CeleryPage.tsx` + `operations/celery/*` | **VERIFIED（Batch 5 Owner 2026-06-03）** |
| MarketIngestOpsPage (Settings → Socket) | `settings/SocketPage.tsx` + `settings/socket/*` | **VERIFIED（Batch 5 Owner 2026-06-03）** |
| ApiHealthOverviewPage (Settings) | `frontend/src/pages/apiOverview/` → `settings/ApiHealthPage.tsx` + `apiHealth/*`（Phase 4.16 Dense UI + 4.17 parity：Services Overview、Shutdown、Log Console） | **VERIFIED（Batch 5 Owner 2026-06-03）** |
| IbConnectionPage (Settings) | `settings/IbConnectionPage.tsx` — connection / Flex | **VERIFIED**（2026-06-04；`IB_CONNECTION_ACCEPTANCE.md`） |
| ArchitectureApisPage (Settings) | `frontend/src/pages/architecture/` → merged into `ApiHealthPage` Architecture tab | **DONE**（2026-06-02） |
| AccountApisPage (Settings) | `frontend/src/pages/account/` → merged into `ApiHealthPage` Account tab | **DONE**（2026-06-02） |
| ResearchApisPage (Settings) | `frontend/src/pages/` → merged into `ApiHealthPage` Research tab | **DONE**（2026-06-02） |
| MassiveApiStatusPage (Settings) | `frontend/src/pages/massive/` → merged into `ApiHealthPage` Massive tab | **DONE**（2026-06-02） |
| DataPage (Settings) | `frontend/src/pages/data/` | **N/A** — 合并入 `coverage/*`（Batch 6 已验） |
| DataOverviewSummaryPage (Settings) | `CoverageOverviewPage.tsx` + `coverage/overview/CoverageOverviewSummaryBody.tsx` | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| DataOverviewDetailPage (Settings) | `CoverageOverviewDetailPage` + `coverage/overview/*` | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| OptionCoveragePage (Settings) | `CoverageOptionPage.tsx` + `coverage/option/OptionCoverageBody.tsx` | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| StockCoveragePage (Settings) | `CoverageStockIbPage.tsx` + `coverage/stock/StockIbCoverageBody.tsx` | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| MassiveStockCoveragePage (Settings) | `CoverageStockMassivePage` + `coverage/stock/*` + `components/massive/MassiveStockOhlcDbEnqueueBlock` | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| FeedMassiveOverviewPage (Settings) | `FeedMassiveOverviewPage` + nested `MassiveSidebarNav` (Overview at `/settings/feed/massive`, Stock/Option/Comm sub-routes) | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| FeedMassiveCommonPage (Settings) | `FeedMassiveCommPage` + `feed/massive/comm/*` | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| FeedMassiveOptionPage (Settings) | `FeedMassiveOptionPage` + `feed/massive/option/*` | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| FeedMassiveStockPage (Settings) | `FeedMassiveStockPage` + `feed/massive/stock/*` | **VERIFIED（Batch 6 Owner 2026-06-03）** |
| StrategyInstanceDetailPage | `frontend/src/pages/strategy/` | **N/A** — 内嵌 `InstanceDetailSidebar`（Batch 1 已验） |

### §6.4 共享组件与工具

| 类别 | 新 repo 规模 | engine 源 | 状态 |
|------|-------------|----------|------|
| components/ | 远超 engine | `frontend/src/components/` | **DONE（evolved）** |
| hooks/ | 83 | `frontend/src/hooks/` | **DONE** |
| utils/ | 扩展 | `frontend/src/utils/` | **DONE（evolved）** |
| constants/ | 扩展 | `frontend/src/constants/` | **DONE（evolved）** |

**Legacy CSS 偿还（2026-05-31）**：已删除全部 `*Legacy.css` 与 `positionsTheme.css`；新增 `components/positions/ui/*` 密集表格原语；Ledger 样式拆为 `TradeLedgerPage.module.css` + `ledgerOptions` + `ledgerStocks`（`ledgerStyles.ts` 合并导出）。追踪见 `bifrost-trade-frontend/docs/LEGACY_CSS_PAYDOWN.md`，CI 检查：`npm run check:legacy-css`。

---

## §7 测试迁移

| 目标 Repo | engine 测试源 | 测试文件数 | 状态 |
|-----------|--------------|-----------|------|
| bifrost-trade-core | `tests/test_config*`, `test_portfolio*`, `test_persistence*` 等 | 146 passed | **VERIFIED**（`not ib and not db`） |
| bifrost-trade-socket | 上述 + `test_message_center_tracker` | 25 passed | **VERIFIED**（`not ib`） |
| bifrost-trade-worker | `test_daemon_fsm*`, `test_guards*`, `test_celery_*`, `test_massive_*`, `test_stock_ohlc_*` 等 | 189 passed | **VERIFIED**（`not ib and not db`） |
| bifrost-trade-api | 单元 + `tests/contract/test_{domain}_parity.py` + `test_cross_repo_integration` | 199 passed（含 contract 24） | **VERIFIED** |

---

## §9 Phase 2A 进度（后端验证与 Dev 栈联调）

> 出口标准见 [`PHASE2A_INTEGRATION_CHECKLIST.md`](./PHASE2A_INTEGRATION_CHECKLIST.md)。Phase 2A 完成后解锁 **Phase 2B**（M6 逐域切 `VITE_API_*`）。

| Sprint | 工作流 | 交付物 | 状态 |
|--------|--------|--------|------|
| 2A.1 | A Harness + Dev compose 9 API + `dev-health` | `docker-compose.dev.yml` 全栈；`make dev-health` | **DONE** |
| 2A.2 | B Socket 测试 ≥20 | socket 23 passed；`test_ib_operator` 等 | **DONE** |
| 2A.3 | C 契约 docs + monitor + market | `tests/contract/test_{docs,monitor,market}_parity.py` | **DONE** |
| 2A.4 | C 剩余 6 域 + D 跨 repo + E 文档 | 9/9 VERIFIED；`PHASE2A_INTEGRATION_CHECKLIST.md`；workspace pytest 隔离 | **DONE** |

| API 域 | 契约测试 | Dev health（`make dev-health`） | VERIFIED |
|--------|----------|--------------------------------|----------|
| docs | `test_docs_parity.py` | :8767 | ✅ |
| monitor | `test_monitor_parity.py` | :8765 | ✅ |
| market | `test_market_parity.py` | :8772 | ✅ |
| trading | `test_trading_parity.py` | :8769 | ✅ |
| portfolio | `test_portfolio_parity.py` | :8771 | ✅ |
| strategy | `test_strategy_parity.py` | :8770 | ✅ |
| ops | `test_ops_parity.py` | :8768 | ✅ |
| massive | `test_massive_parity.py` | :8766 | ✅ |
| research | `test_research_parity.py` | :8773 | ✅ |

---

## §10 Phase 2B 进度（API 逐域切换 M6）

> 签字清单：[PHASE2B_SIGNOFF_MASTER.md](../bifrost-trade-frontend/docs/PHASE2B_SIGNOFF_MASTER.md)。Owner 走查：[PHASE2B_OWNER_WALKTHROUGH.md](../bifrost-trade-frontend/docs/PHASE2B_OWNER_WALKTHROUGH.md)。Dev 栈：`make dev-preflight` / `make dev-health`。

| Sprint | 域 | `VITE_API_*` → New | Batch | Agent gate | Owner | §4 状态 |
|--------|-----|-------------------|-------|------------|-------|---------|
| 2B.1 | docs | `DOCS` → 8767 | 5 | pass 2026-06-04 | **signed 2026-06-04** | **CUTOVER** |
| 2B.2 | monitor | `MONITOR` → 8765 | 1 + 5 | pass 2026-06-04 | **signed 2026-06-04** | **CUTOVER** |
| 2B.2 | market | `MARKET` → 8772 | 1 | pass 2026-06-04 | **signed 2026-06-04** | **CUTOVER** |
| 2B.3 | trading | `TRADING` → 8769 | 2 | pass 2026-06-04 | **signed 2026-06-05** | **CUTOVER** |
| 2B.3 | portfolio | `PORTFOLIO` → 8771 | 1–2 | pass 2026-06-04 | **signed 2026-06-04** | **CUTOVER** |
| 2B.3 | strategy | `STRATEGY` → 8770 | 4 | pass 2026-06-04 | **signed 2026-06-05** | **CUTOVER** |
| 2B.4 | ops | `OPS` → 8768 | 5 | pass 2026-06-04 | **signed 2026-06-04** | **CUTOVER** |
| 2B.4 | massive | `MASSIVE` → 8766 | 6 | pass 2026-06-05 | **signed 2026-06-05** | **RETIRED (P7 → Market Data Plugin)** |
| 2B.4 | research | `RESEARCH` → 8773 | 3 | pass 2026-06-04 | **signed 2026-06-05** | **CUTOVER** |

> **Phase 2B CLOSED（2026-06-04）**：Wave A Session 1–6 + Wave B Session 7–9 Owner **全部已签**；§10 九域 Owner 列均为 signed。见 [PHASE2B_SESSION_TRACKER.md](../bifrost-trade-frontend/docs/PHASE2B_SESSION_TRACKER.md)。

**Phase 2B 出口（已达成）**：9/9 CUTOVER + Owner 签字 + `check_cutover_env.sh` 无 Legacy 端口 → Mac Dev 稳定 → **已解锁 Phase 2C**（[PHASE2C_PROD_DEFERRED.md](./PHASE2C_PROD_DEFERRED.md)）/ Phase 3。

---

## §11 Mac Dev 标准环境（Phase 2B 后）

| 项 | 约定 |
|----|------|
| PG/Redis | 默认 **host/LAN**（`BIFROST_DEV_INFRA=host`），非 Docker 空库 |
| 启动 | `make dev-preflight` · Runbook 见 [PHASE2_API_CUTOVER.md](./PHASE2_API_CUTOVER.md) |
| 单域切换 | `make switch-cutover-domain DOMAIN=<域> MODE=legacy\|new` |
| 生产 compose | [`docker-compose.yml`](./docker-compose.yml) — **Phase 2C 已对齐**；`make prod-preflight` |

---

## §12 Phase 2C 进度（Linux 生产 M7）

> 签字清单：[PHASE2C_SIGNOFF_MASTER.md](./PHASE2C_SIGNOFF_MASTER.md)

| 子阶段 | 内容 | Agent | Owner | 状态 |
|--------|------|-------|-------|------|
| 2C-A | compose + config.prod + 前端 prod build + `prod-health` | Session 0–9 已签 | Owner 2026-06-08 | **CLOSED** |
| 2C-A.1 | Docker 控制面（Ops executor + Daemon/Socket UI） | `verify-2c-a1` 通过 | Session 8 已签 | **Owner 已验** |
| **Local Prod Final** | local 闸门；Session 0–3/8 + L2.8 | Owner 2026-06-04 | L4 CLOSED | **CLOSED** |
| 2C-B | Compose Prod 稳定测试 | D5 已签 | 生产切换待迁移决策 | **稳定测试已签** |
| **K3s 阶段 1** | 集群搭建与试验 | §9 清单 | Owner 2026-06-04 解锁 | **CLOSED**（CNPG + dev/stg/prod 栈 @ K3s） |
| K3s 搬迁 → Legacy | PLATFORM / K3S 文档 | overlay 同步、矩阵 CNPG/redis | 2026-06-29 | **DONE** |
| Phase 3 | Legacy 退役 | `.70` compose 已停；engine NAS 归档；spine 决策 D8 签字 | 2026-06-29 | **CLOSED**（SIGNED — engine retired） |

**主线**（Owner 2026-06-04）：Local Prod Final **CLOSED** → **K3s 阶段 1** → 迁移定稿 → Legacy 退役。见 Ops Console → Program → Deploy Mainline（`deployMainlineCatalog.ts`）。

---

## §13b Brokerage Golden Source（Program: `brokerage-golden-source`）

> IB 账户/持仓/成交迁入 `bifrost_golden_source.brokerage.*`；per-env 经 `postgres_fdw` 只读 JOIN。
> Core `0.6.1`：per-env `_ensure_tables` 跳过已迁表；`db_refresh_schema` 自动 brokerage DDL + FDW。

| Phase | 内容 | 状态 |
|-------|------|------|
| P0 | Schema DDL + roles + FDW (dev/stg/prod) + config | ✅ 2026-08-17 |
| P1 | Writers: account/positions/quotes/open_orders/settings_flex | ✅ |
| P1 data | Copy from bifrost_prod → brokerage.* | ✅ |
| P2 | Writers: executions/commissions/transactions | ✅ |
| P2 data | Copy executions + commissions + transactions | ✅ |
| P3 | Readers: schema-qualify via brokerage_tables | ✅ |
| P4 | Docs + core 0.6.0; legacy public tables retained 30d | ✅ |
| P5 | Hygiene: skip legacy CREATE in ddl.py; watchlist → brokerage.positions; db-init FDW; drop EXECUTIONS_WRITE_LEGACY | ✅ 2026-08-17 |

**Table map**: `account`→`brokerage.account`, `account_positions`→`brokerage.positions`,
`account_execution_commissions`→`brokerage.commissions`, `account_transactions`→`brokerage.transactions`,
`daemon_open_orders`→`brokerage.open_orders`, `settings_ib_flex`→`brokerage.settings_flex`,
views `account_executions*`→`brokerage.executions*`.

---

## §13 Market Data Golden Source（Program: `market-data-golden-source`）

> Trade 消费者从直接 SQL 读 `market.*` 切换为 Plugin API HTTP；详见 `bifrost-trade-api/docs/MARKET_SQL_RESIDUAL.md`。

### Wave 0（Plugin API 补全） — ✅ COMPLETED

| Phase | 内容 | 状态 |
|-------|------|------|
| W0-P1 | Plugin API — stock daily bars + ticker reference | ✅ |
| W0-P2 | Plugin API — option chain, contracts, expirations, OI | ✅ |
| W0-P3 | Plugin API — financials, short interest, SEPA helpers | ✅ |
| W0-P4 | Plugin API — watchlist union endpoint + platform-api proxy | ✅ |

### Wave 1（Trade 消费者切换） — ✅ COMPLETED

| Phase | 内容 | 状态 |
|-------|------|------|
| W1-P1 | market_pg.py stock reads → Plugin API HTTP client (3 functions) | ✅ |
| W1-P2 | market_pg.py option reads → Plugin API HTTP client (6 functions) | ✅ |
| W1-P3 | market_pg.py fundamentals reads → Plugin API HTTP client (2 functions) | ✅ |
| W1-P4 | E2E grep audit + feature flag verification + docs | ✅ |

**已迁移（11 functions in `market_pg.py`）**:

| Function | Plugin API endpoint |
|----------|---------------------|
| `get_stock_day_series_for_sepa` | `GET /stocks/db/bars/daily` |
| `get_stock_day_close_series_for_crs` | `GET /stocks/db/bars/daily/close` |
| `get_spy_close_series` | `GET /stocks/db/bars/daily/spy-close` |
| `get_option_snapshots_latest` | `GET /options/chain/latest` |
| `get_option_snapshots_eod_per_day` | `GET /options/chain/eod` |
| `get_option_open_interest_daily` | `GET /options/oi` |
| `get_option_expirations_from_contracts_db` | `GET /options/expirations/yyyymmdd` |
| `get_strikes_for_expiry_from_contracts_db` | `GET /options/strikes` |
| `get_option_expiration_cache_snapshot` | `GET /options/expirations` |
| `get_short_interest_recent` | `GET /stocks/fundamentals/db/short-interest` |
| `get_short_volume_recent` | `GET /stocks/fundamentals/db/short-volume` |

**Plugin API**: Trade consumers read/write `market.*` exclusively through Plugin API HTTP (`MARKET_DATA_PLUGIN_URL`). SQL fallback has been removed.

**Residual SQL（未迁移，已记录在 `MARKET_SQL_RESIDUAL.md`）**:

| File | Repo | SQL count | Reason |
|------|------|-----------|--------|
| `sepa/financials_data.py` | trade-api | ~33 | Complex jsonb unpacking |
| `sepa/readiness_snapshot.py` | trade-api | ~13 | Readiness coverage queries |
| `routers/data_readiness.py` | trade-api | ~9 | Coverage analysis + jsonb |
| `sepa_engine/stock_option_pcr.py` | trade-api | ~8 | PCR aggregate SQL |
| `routers/greeks.py` | trade-api | ~2 | option_daily reads |
| `monitor/reader/market.py` | trade-core | ~32 | Mixed R/W + minute bars |
| `persistence/.../ticker_reference.py` | trade-core | ~51 | Ticker lifecycle R/W |

### Wave 2（基础设施收敛） — ✅ COMPLETED

| Phase | 内容 | 状态 |
|-------|------|------|
| W2-P1 | K8s — collapse to single Plugin NS + watchlist union mode | ✅ |
| W2-P2 | Retire STG/PROD Plugin overlays (archived to `_archived/`) | ✅ |
| W2-P3 | Golden database rename (`bifrost_golden_source`) + Ops Console governance | ✅ |

**Golden Source 最终架构（2026-08-14）**:

- 单一 Plugin NS `plugin-market-data`，watchlist union mode
- 目标数据库：`bifrost_golden_source`（已创建 + schema 迁移完成，177 张表 ~212MB）
- Trade 消费者通过 Plugin API HTTP 读写，零直接 SQL
- `bifrost_stg` / `bifrost_prod` / `bifrost_dev` market schemas 全部 DROP
- `plugin-market-data-stg` / `plugin-market-data-prod` K8s NS 已删除
- STG/PROD overlays 归档至 `k8s/overlays/_archived/`
- Ops Console catalog 版本 `2026-08-14-golden-source`

---

## §14 Market Data Write Consolidation（Program: `market-data-write-consolidation`）

> Golden Source 后续 — 将 ~148 处 `market.*` 直接 SQL 全部迁移到 Plugin API HTTP；`bifrost_dev` market schemas 已 DROP。

### Wave 0（Plugin WRITE API） — ✅ COMPLETED

| Phase | 内容 | 状态 |
|-------|------|------|
| W0-P1 | POST /stocks/bars/ingest (OHLC batch write + delete) | ✅ |
| W0-P2 | POST /reference/ticker/upsert (ticker metadata write) | ✅ |
| W0-P3 | POST /options/expirations/replace (cache refresh) | ✅ |

### Wave 1（Trade WRITE cutover） — ✅ COMPLETED

| Phase | 内容 | 状态 |
|-------|------|------|
| W1-P1 | IB bars backfill + Market API → Plugin POST | ✅ |
| W1-P2 | StatusSink bars → Plugin POST | ✅ |
| W1-P3 | ticker_reference upsert → Plugin POST | ✅ |
| W1-P4 | option expiration cache → Plugin POST | ✅ |

### Wave 2（Trade READ residual） — ✅ COMPLETED

| Phase | 内容 | 状态 |
|-------|------|------|
| W2-P1 | Plugin SEPA financial aggregate endpoints (9 endpoints) | ✅ |
| W2-P2 | financials_data.py + readiness_snapshot.py → Plugin HTTP | ✅ |
| W2-P3 | Plugin PCR/greeks/coverage endpoints (13 endpoints) | ✅ |
| W2-P4 | PCR/greeks/data_readiness/market.py/ticker READ → Plugin HTTP | ✅ |
| Residual | readiness_snapshot, data_readiness, pcr, ticker_reference, massive_jobs, ddl | ✅ |

### Wave 3（DROP + cleanup） — ✅ COMPLETED

| Phase | 内容 | 状态 |
|-------|------|------|
| W3-P1 | DROP market/market_analytics/data_ops from bifrost_dev | ✅ |
| W3-P2 | 文档更新 + program sign-off | ✅ |

**最终状态**：`bifrost_dev` 仅剩 `public` schema；所有 market 数据读写经 Plugin API → `bifrost_golden_source`。

---

## §15 SEPA Analytics Pipeline (dbt Migration)

> SEPA 评估引擎从 OLTP jsonb 模式迁移为 dbt 正规化分析管线。新管线由 `bifrost-analytics` 项目承载。

| Component | Status | Details |
|-----------|--------|---------|
| bifrost-analytics project | ✅ Created | 21 dbt models (6 staging + 5 intermediate + 10 marts) |
| analytics schema setup | ✅ Deployed 2026-08-20 | `analytics` schema + `analytics_writer`/`analytics_reader` roles on Golden Source |
| dbt CronJob | ✅ Deployed 2026-08-20 | `bifrost-analytics-daily` @ `plugin-market-data` NS, 03:00 ET weekdays |
| Initial dbt run | ✅ 21/21 models PASS | 1.39M enriched rows, 5352 universe, fundamental/sentiment/structure populated |
| Trade API cutover | ✅ Deployed STG+DEV | `SEPA_USE_ANALYTICS=true`, analytics_reader pooled connection to Golden Source |
| Frontend adaptation | ✅ Deployed STG+DEV | `normalizeSnapshotRow()` adapter, 7 files, pipeline `bifrost-deliver-stg` |
| Python engines deprecated | ✅ Moved to `_deprecated/` | 9 engine files with redirect stubs |
| Legacy tables DROP | ✅ Dropped DEV+PROD 2026-08-20; STG 2026-08-21; **SRD DDL CREATE removed core 0.10.7 (2026-08-23)** | `stock_readiness_daily`, `research_sepa_fundamentals_cache`, `job_sepa_phase4` + CASCADE — all Trade DBs; refresh actively DROPs SRD |
| API legacy query guards | ✅ **Retired 2026-08-23** | `data_readiness.py` / `readiness_snapshot.py` legacy SRD SQL removed; writers unconditionally deprecated; `SEPA_USE_ANALYTICS=false` returns explicit error |

**Data depth note:** `market.stock_daily` covers ~162 trading days (2025-06 to 2026-08). CRS/technical models require 252+ days → `sepa_technical_eval`, `sepa_tier_momentum`, `sepa_composite_score`, `sepa_screener_wide` currently empty. Will auto-populate as daily bars accumulate.

**Deployed 2026-08-20:**
1. ✅ Analytics schema + roles on Golden Source CNPG
2. ✅ dbt runner Job (21/21 PASS) + daily CronJob
3. ✅ Trade API `api-research` with `SEPA_USE_ANALYTICS=true` (STG + DEV)
4. ✅ Frontend with normalizer (STG + DEV via `bifrost-deliver-stg`)
5. ✅ Legacy tables DROPPED (DEV + PROD) + all API queries guarded
6. ✅ Legacy tables DROPPED on `bifrost_stg` (2026-08-21) — three-env cleanup complete

---

## §8 变更日志

| 日期 | 变更内容 | 操作人 |
|------|---------|--------|
| 2026-08-23 | **stock_readiness_daily RETIRE (Waves W0–W5)**: core 0.10.7 DROP-only DDL; API legacy SQL stripped; FE screener empty-state; Plugin readiness-refresh retired (CronJob suspend); deliver STG+PROD | Agent |
| 2026-08-20 | **SEPA dbt Migration COMPLETED**: Legacy tables DROPPED (DEV+PROD); all API endpoints guarded by `use_analytics()`; readiness/summary migrated to analytics schema; POST snapshot/backfill return deprecated; tier endpoints graceful empty | Agent |
| 2026-08-20 | **SEPA dbt Migration Wave 6 (Cleanup)**: DDL deprecation markers on `stock_readiness_daily` / `research_sepa_fundamentals_cache` / `v_sepa_symbol_fund_cache_readiness` / `job_sepa_phase4`；§15 added；`bifrost-analytics` added to workspace rules | Agent |
| 2026-08-20 | **Readiness Quality Phase B**: DEV rollout + `db-init-dev`；PROD `bifrost-deliver-prod` + `db-init-prod`；STG `bifrost-deliver-stg` 规范化重建；三环境 readiness `row=13131 gap=118`；`cache_stock_snapshot` 三库均不存在；Tekton smoke 默认 tag 改为 `:smoke` | Agent |
| 2026-08-20 | **Readiness Quality Migration**: `cache_stock_snapshot` → Plugin `market.stock_snapshot`；Plugin 0.7.0 新增 `/market/readiness/snapshot-coverage` + `/market/readiness/vendor-gap`；Trade Core 0.10.2 DDL DROP；API readiness_snapshot 3 处 SQL→HTTP；FE tooltip 更新 | Agent |
| 2026-08-18 | **Flex 引擎内化**: `flex_client` + Flex 编排/配置读写从 Trade core/socket 迁入 `bifrost-platform-plugin-flex-query` `0.2.0`；core `0.7.0`；Monitor `GET /status` 去掉 `config.ib_flex` | Agent |
| 2026-08-14 | **Write Consolidation COMPLETED**: W0 Plugin WRITE API (3 endpoints); W1 Trade WRITE cutover (4 phases — bars/ticker/expiration); W2 Trade READ residual (4+1 phases — SEPA/PCR/greeks/bars/ticker, ~148 SQL → Plugin HTTP); W3 DROP `market`/`market_analytics`/`data_ops` from `bifrost_dev` (19+4+5 objects); CNPG backup `bifrost-postgres-ondemand-20260814-213229` | Agent |
| 2026-08-14 | **Golden Source Post-Cleanup**: CREATE DATABASE `bifrost_golden_source` + pg_dump/restore (177 tables, 212MB); DROP schemas from `bifrost_stg`/`bifrost_prod`; DELETE NS `plugin-market-data-stg`/`plugin-market-data-prod`; remove SQL fallback from `market_pg.py` (-1169 lines); ingress NetworkPolicy fix | Agent |
| 2026-08-14 | **Market Data Golden Source W2 COMPLETED**: W2-P1 single NS converge + watchlist union; W2-P2 STG/PROD overlays archived to `_archived/`; W2-P3 config → `bifrost_golden_source`, Ops Console catalog `2026-08-14-golden-source`, program YAML all phases → completed | Agent |
| 2026-08-14 | **Market Data Golden Source W0+W1 COMPLETED**: 11 market_pg.py functions migrated from direct SQL to Plugin API HTTP; market_data_client.py (11 endpoints); 47 client tests + 78 Plugin API tests; feature flag `MARKET_DATA_SOURCE=plugin` default; residual ~148 SQL documented in `MARKET_SQL_RESIDUAL.md`; program YAML W0-P1–W1-P4 → completed | Agent |
| 2026-07-06 | **Phase 5 Observability (STG)**: Loki + Promtail @ monitoring; PrometheusRule (6 rules) + Alertmanager bifrost-ops-agent webhook; Grafana Trade dashboard ConfigMap; `verify-phase5-observability.sh`; MCP mcp-server-prometheus bridge | Agent |
| 2026-05-23 | 同步当前架构：daemon/celery 归入 worker；SEPA 归入 api.research；移除 data/research 独立 repo | Agent |
| 2026-05-31 | AccountsPage 样式布局迁移：页头 breadcrumb/pill 工具条/KPI/图表/摘要卡/持仓表对齐 Legacy | Agent |
| 2026-05-31 | CeleryPage Phase C：Ops 鉴权门控、URL 深链、跨 Tab 导航、AppHeader Celery 指标、Broker extended + flash | Agent |
| 2026-05-31 | CeleryPage Phase D：彩色 icon toolbar、Queue Summary actionMode、Worker Host 列、flash 动画、Sidebar Celery 指标 | Agent |
| 2026-05-31 | Phase 1 UI 画布扫尾：PageHeader 全站、`titleSize`、elevated 面板、RouteErrorPage、验收清单 | Agent |
| 2026-05-31 | Socket Services 页（Settings → Socket）：Legacy MarketIngestOpsPage 业务/布局对齐 — OpsAuthBar、分组 ingest 表、logical 列、control poll、Local Control Agent、页内 4 源 Logs | Agent |
| 2026-05-31 | bifrost-trade-frontend Legacy CSS 偿还：删除 Positions 五件套 Legacy + theme；`positions/ui` 原语；Ledger CSS 拆分；`check:legacy-css` | Agent |
| 2026-06-03 | Phase 1 收尾：Coverage Overview/Option/Stock IB 业务等价；Instance Detail Phase 4.9；`PHASE1_SIGNOFF_MASTER.md`；机械门禁通过 — **Owner 6 批次验收待签** | Agent |
| 2026-06-03 | **Phase 1 Batch 1 Owner sign-off**（`/market/live`、`/portfolio/positions`、`/portfolio/accounts`、`/strategy/instances`）— 非最终 VERIFIED；横切项待 Batch 2 补验 | Owner |
| 2026-06-03 | Phase 1 **Batch 2 启动**：Portfolio activity 四页 Owner 并排验收进行中；Agent pre-flight（lint/build/check-legacy-css）通过 | Agent |
| 2026-06-03 | **Phase 1 Batch 2 Owner sign-off**（`/portfolio/ledger`、`/performance`、`/model-analysis`、`/transfer`）— 非最终 VERIFIED；横切项仍待 Batch 3 补验 | Owner |
| 2026-06-03 | Phase 1 **Batch 3 启动**：Research 8 路由 + Stock Inspector Owner 并排验收进行中；Agent pre-flight 通过 | Agent |
| 2026-06-03 | **Phase 1 Batch 3 Owner sign-off**（Research 8 路由 + Stock Inspector）— 非最终 VERIFIED；Cross-cutting 待 Batch 4 在 `/strategy/*` 补验 | Owner |
| 2026-06-03 | Phase 1 **Batch 4 启动**：Strategy 配置六页 Owner 并排验收进行中；Agent pre-flight 通过 | Agent |
| 2026-06-03 | **Phase 1 Batch 4 Owner sign-off**（Strategy 六路由）— 非最终 VERIFIED；Cross-cutting 待 Batch 5 补验 | Owner |
| 2026-06-03 | Phase 1 **Batch 5 启动**：System/Operations 四路由 Owner 并排验收进行中；Agent pre-flight 通过 | Agent |
| 2026-06-03 | **Phase 1 Batch 5 Owner sign-off**（api / daemon / celery / socket + logs N/A）— 非最终 VERIFIED；Cross-cutting 待 Batch 6 补验 | Owner |
| 2026-06-03 | Phase 1 **Batch 6 启动**：Settings depth 八路由 Owner 并排验收进行中；Agent pre-flight 通过 | Agent |
| 2026-06-03 | **Phase 1 Batch 6 Owner sign-off**（subscribe / coverage/* / feed/*；`/settings/ib` Batch 6 parity N/A — Massive 历史数据，IB 连接/交易等仍保留）— 非最终 VERIFIED；Cross-cutting 待签 | Owner |
| 2026-06-03 | **Phase 1 Cross-cutting Owner sign-off**（global strip、settings 无 strip、sidebar lamp、canvas、无 data regression） | Owner |
| 2026-06-03 | **Phase 1 Final sign-off** — frontend **Phase 1 VERIFIED**（New Frontend + Legacy API 阶段 1 闭环） | Owner |
| 2026-06-04 | **Frontend Phase 1 CLOSED**：`IB_CONNECTION_ACCEPTANCE.md`（`/settings/ib` parity）；Batch 1 smoke；`MIGRATION_TRACKING` §6 同步；机械门禁通过 — **允许启动底层迁移** | Agent |
| 2026-06-05 | **Backend M0–M5 落地**：core/socket/worker/api 代码迁移 + 测试（core 146、worker 185、socket 4）；`PHASE2_API_CUTOVER.md`；infra `docker-compose.dev.yml` 对齐 socket/worker | Agent |
| 2026-06-04 | **Phase 2A 完成**：Dev 栈 9 API + `dev-health`；socket 23 tests；api contract 24 + 跨 repo；`PHASE2A_INTEGRATION_CHECKLIST.md`；§4 九域 VERIFIED → 解锁 Phase 2B | Agent |
| 2026-06-04 | **Phase 2B 实施**：`PHASE2B_SIGNOFF_MASTER.md`；`PHASE2_API_CUTOVER.md` 扩展；`check_cutover_env.sh`；§10；`.env.development` → 8765–8773；§4 **CUTOVER** | Agent |
| 2026-06-05 | **Phase 2B 分批签字**：`verify-wave-a-sessions`；`PHASE2B_SESSION_TRACKER.md`；Wave A Agent gate 全通过；Wave B 延后 | Agent |
| 2026-06-05 | **Phase 2B 工具链 + Mac Dev Runbook**：`dev_preflight` / `verify-domain-apis` / `switch_cutover_domain`；`PHASE2B_OWNER_WALKTHROUGH` + `PHASE2B_AGENT_VERIFICATION`；host/LAN PG/Redis 默认；`PHASE2C_PROD_DEFERRED.md`；§11 | Agent |
| 2026-06-04 | **Phase 2B CLOSED**：Wave B Session 9（ops）Owner 签字；9/9 域 `PHASE2B_SIGNOFF_MASTER` Pass + Final 四项；frontend/api §1 → Phase 2B CLOSED | Owner |
| 2026-06-04 | **Phase 2C 启动**：`docker-compose.yml` 对齐 socket/worker/daemon；`config.prod.yaml`；`sync_prod_config.sh`；`make prod-*`；`PHASE2C_SIGNOFF_MASTER.md`；前端 `.env.production` | Agent |
| 2026-06-06 | **2C-A.1 立项**：Docker 控制面任务清单；Session 1–9 Owner 冻结；`make verify-2c-a1`；`PHASE2C_A1_DOCKER_CONTROL_PLANE.md` | Agent |
| 2026-06-07 | **2C-A Session 8 Owner sign-off**：Celery + Socket + Daemon docker 控制面；`PHASE2C_SIGNOFF_MASTER` Session 8；下一项 Session 1（Monitor） | Owner |
| 2026-06-08 | **2C-A Session 1 Owner sign-off**：Monitor Global strip、侧栏灯、daemon、allocations、API Network `/api/*`；下一项 Session 2（Market / Live） | Owner |
| 2026-06-08 | **2C-A Session 2 Owner sign-off**：`/market/live` SSE + category groups + watchlist quotes；下一项 Session 3（Portfolio） | Owner |
| 2026-06-08 | **2C-A Session 3 Owner sign-off**：accounts / positions / performance / model-analysis；下一项 Session 4（Ledger） | Owner |
| 2026-06-08 | **2C-A Session 4 Owner sign-off**：`/portfolio/ledger`；下一项 Session 5（Strategy） | Owner |
| 2026-06-08 | **2C-A Session 5 Owner sign-off**：Strategy 7 路由；下一项 Session 6（Research） | Owner |
| 2026-06-08 | **2C-A Session 6 Owner sign-off**：Research 8 路由 + Stock Inspector + stock-data backfill；`financials_feed` Celery 修；下一项 Session 7（Massive） | Owner |
| 2026-06-08 | **2C-A Session 7 Owner sign-off**：coverage/* + feed/massive-*；下一项 Session 9（2C-A Final） | Owner |
| 2026-06-08 | **2C-A Session 9 / Final**：`make prod-health` 12/12 OK（LAN PG/Redis）；**2C-A CLOSED**；下一项 **2C-B** 新 Prod 集群 | Owner |
| 2026-06-18 | **K3s STG v2 SIGNED**：deliver-stg + Tier A smoke + STG release gate + Tier B sign-off；`k3s-stg-v2-deliver` CLOSED；`2c-b-prod-cutover` → IN_PROGRESS；compose→k3s ③/⑤ | Owner |
| 2026-06-04 | **Local Prod Final CLOSED**：L2 Session 0–3/8 + L2.8；L3 D1–D5 Owner 修订（K3s 优先、PG `.80`、Win11×2 TWS、暂缓自动下单）；解锁 **K3s 阶段 1** | Owner |
| 2026-06-08 | **Local Prod Final 立项**：主线 Local Final → 2C-B → K3s → 搬迁 → Legacy；`local_prod_final_gate.sh` L1 通过 | Agent |
| 2026-06-05 | **Socket Message Center**：`IbConnectionStatusTracker` 接入 ingestor/account_agent/operator；`test_message_center_tracker`；prod-local 容器重启后 Redis 流验证 | Agent |
| 2026-06-29 | **Phase 3 Legacy retirement SIGNED（决策 D8）**：Owner 豁免「UI 并排对齐」退役前置（Legacy 已停无法并排；2B 9/9 域已业务等价）；engine NAS 归档只读 + 移出 workspace；spine `legacy-retirement` → SIGNED/closed | Owner |
| 2026-06-29 | **Data layer cutover**：裸机 PG `.80` 下线；CNPG `bifrost-postgres-rw` 承载 dev/stg/prod；Platform 矩阵 postgres→CNPG；prod redis→`redis-live-prod.data.svc`；`ubt-k3s-06`（`.79`）入列 | Agent |
| 2026-06-29 | **Legacy runtime 收尾**：`.70`/`.73`/`.50` 无 Legacy API/compose/systemd 监听；`bifrost-trader-engine` 已 NAS 归档并从 workspace 移除 | Agent |
| 2026-06-04 | **IB Broker Connection 完全对齐**：`bifrost_core.monitor.integrations.ib_socket_status`（v0.2.3）；socket `ib_health_schema` + AA canonical probe keys + ingestor `host_*` mirror；api `status.py` 三服务 `build_ib_socket_status`；frontend `IbBrokerConnection` + `StatusSocketIbBroker`；docker 重建 ib-operator/ingestor/account-agent/api-monitor/frontend | Agent |

## Phase B — Trade API consolidation (2026-08-17)

**8 path domains → 4 process pods** (HTTP path prefixes preserved via Traefik/nginx strip + Service aliases):

| Pod | Port | Absorbs |
|-----|------|---------|
| `api-monitor` | 8765 | monitor + ops + docs |
| `api-account` | 8769 | trading + portfolio + strategy |
| `api-market` | 8772 | market |
| `api-research` | 8773 | research |

Frontend: single `VITE_API_BASE` (Wave B1). Gate B4 PASS (RBAC via `api-ops` SA on monitor).

## Backlog — Frontend `massive` source alias cleanup

**Status**: PLANNED | **Priority**: Low | **Risk**: None (functionally correct, semantically stale)

P7 retired `api-massive` (port 8766) and Polygon WS — all data now flows through Market Data Plugin.
Backend APIs still accept `source='massive'` as a backward-compatible alias, so the frontend works correctly.
However, 15 call sites and 7 type references still hardcode `'massive'` as the source string, creating semantic confusion.

### Files to update (replace `'massive'` → `'plugin'` or remove source param)

| File | Occurrences | Nature |
|------|:-----------:|--------|
| `src/api/research/optionDiscovery.ts` | 7 | Default params `source = 'massive'` |
| `src/api/market.ts` | 1 | `source: params.source ?? 'massive'` |
| `src/hooks/useDiscoveryExpirations.ts` | 2 | Hardcoded `'massive'` in fetch calls |
| `src/hooks/useDiscoverySnapshots.ts` | 2 | Hardcoded `'massive'` in fetch calls |
| `src/hooks/useOptionChainQuotes.ts` | 2 | Hardcoded `'massive'` in fetch calls |
| `src/hooks/useDiscoveryIvTerm.ts` | 2 | Hardcoded `'massive'` in fetch calls |
| `src/hooks/useDiscoveryGreeksCoverage.ts` | 1 | Hardcoded `'massive'` in fetch call |
| `src/components/optionDiscovery/useOptionContractLiquidity.ts` | 2 | Hardcoded `'massive'` |
| `src/components/optionDiscovery/OptionContractDetailFromOpenPosition.tsx` | 2 | Hardcoded `'massive'` |
| `src/components/optionDiscovery/OptionDiscoveryContractChartPanel.tsx` | 1 | `BAR_SOURCE = 'massive'` const |
| `src/components/strategy/instanceDetail/InstanceKlineSection.tsx` | 2 | Hardcoded `'massive'` |
| `src/pages/research/optionScreener/optionScreenerConstants.ts` | 1 | `source: 'massive'` |
| `src/pages/settings/apiHealth/panels/ArchDetailsPanel.tsx` | 1 | Displays `massive_port` config |
| `src/pages/settings/apiHealth/ApiConfiguredRoutesStrip.tsx` | 2 | Label for `'massive'` source |

### Also clean (types / monitor)

| File | Nature |
|------|--------|
| `src/types/monitor.ts` | JSDoc referencing "massive fallback" |
| `src/types/watchlistDbCoverage.ts` | `massive_count`, `massive_total` fields |
| `src/types/stockDataReadiness.ts` | `massive_count`, `last_massive_sync` fields |
| `src/pages/settings/socket/IngestConnectionCell.tsx` | `ws_massive` references |
| `src/utils/socketIngestLamp.ts` + test | `ws_massive` references |
| `src/hooks/useMarketDataPluginStatus.ts` | Comment about retired api-massive |

### Execution plan

1. Backend: add `'plugin'` as canonical source alias (or remove source routing entirely)
2. Frontend: batch-replace `'massive'` → `'plugin'` in all call sites
3. Frontend: update type definitions to drop `massive_*` fields
4. Frontend: remove ArchDetailsPanel `massive_port` display
5. Run `npm run lint && npm run build && npm run check:legacy-css`
