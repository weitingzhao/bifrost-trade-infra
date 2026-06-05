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
| bifrost-trade-socket | 5 | 5 | **VERIFIED**（2026-06-05）— 代码 + 4 tests；待 `@pytest.mark.ib` 烟雾 |
| bifrost-trade-worker | 3 | 3 | **VERIFIED**（2026-06-05）— daemon + celery 已迁；185 tests passed |
| bifrost-trade-api | 9 | 9 | **DONE**（2026-06-05）— 9 域代码已迁；契约/集成测试进行中 → 逐域 VERIFIED 后切 `VITE_API_*` |
| bifrost-trade-frontend | 4 | 4 | **Phase 1 CLOSED**（2026-06-04）— New Frontend + Legacy API 业务等价 100%（含 `/settings/ib`） |

> **Backend M0–M5 落地**（2026-06-05）：见 [`PHASE2_API_CUTOVER.md`](./PHASE2_API_CUTOVER.md)。**默认仍指向 Legacy API**；单域 VERIFIED 后才切换 `VITE_API_*`。

---

## §2 bifrost-trade-core（共享库 · 无进程入口）

### §2.1 共享库模块

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| config | `src/config/` | `bifrost_core/config/` | settings.py, yaml_config.py | **VERIFIED** |
| core | `src/core/` | `bifrost_core/core/` | dict_merge, redis_url, logging, realtime/redis_*, sse/queue_utils | **VERIFIED** |
| persistence | `src/persistence/` | `bifrost_core/persistence/` | status_sink, postgres/{connection, ddl, postgres_sink, accounts_sync, stock_ohlc_massive, ticker_reference} | **VERIFIED** |
| portfolio | `src/portfolio/` | `bifrost_core/portfolio/` | accounts, symbol_position, model/{core, payoff}, positions/{portfolio, position_book}, reader/*, services/* | **VERIFIED** |
| ib_operator (client) | `src/ib_operator/` | `bifrost_core/ib_operator/` | client.py, protocol.py, config.py | **VERIFIED** |
| monitor | `src/monitor/` | `bifrost_core/monitor/` | self_check, reader/{status, strategy, gate_safety, watchlist, market, massive_jobs, ...}, schemas/*, services/* | **VERIFIED** |

---

## §3 bifrost-trade-socket（WebSocket 边缘服务）

### §3.1 IB 子域（`src/bifrost_socket/ib/`）

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| connector | `src/ib/`, `src/connector/` | `bifrost_socket/ib/connector/` | connection_policy.py, ib.py, flex_client.py | - |
| ingestor | `src/vendor/ib_ingestor/` | `bifrost_socket/ib/ingestor/` | writer.py, redis_keys.py | - |
| account_agent | `src/vendor/ib_account_agent/` | `bifrost_socket/ib/account_agent/` | writer.py, redis_keys.py | - |
| operator | `src/ib_operator/` (service) | `bifrost_socket/ib/operator/` | service.py, executor.py, redis_io.py, health_redis.py | - |

### §3.2 Massive 子域（`src/bifrost_socket/massive/`）

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| massive_ws | `scripts/systemd/run_massive_ws.py` | `bifrost_socket/massive/` | massive_ws_ingestor.py, redis_writer.py, subscription_manager.py | - |

---

## §4 bifrost-trade-api（9 个 FastAPI 域）

| 域 | 端口 | engine 源 | 目标路径 | 主要文件 | 状态 |
|----|------|----------|----------|---------|------|
| monitor | 8765 | `backend/monitor/` | `bifrost_api/monitor/` | app.py, routers/{status, daemon, config, core, logs, messages} | - |
| massive | 8766 | `backend/massive/` | `bifrost_api/massive/` | app.py, deps.py, sse.py, routers/{routes, stream} | - |
| docs | 8767 | `backend/docs/` | `bifrost_api/docs_api/` | app.py, merge_openapi.py | - |
| ops | 8768 | `backend/ops/` | `bifrost_api/ops/` | app.py, auth.py, worker_profiles, agent/*, routers/{workers, job_queues, market_ingest}, services/* | - |
| trading | 8769 | `backend/trading/` | `bifrost_api/trading/` | app.py, routers/executions | - |
| strategy | 8770 | `backend/strategy/` | `bifrost_api/strategy/` | app.py, routers/strategies | - |
| portfolio | 8771 | `backend/portfolio/` | `bifrost_api/portfolio/` | app.py, routers/{config, model} | - |
| market | 8772 | `backend/market/` | `bifrost_api/market/` | app.py, routers/{quotes, watchlist, market_data} | - |
| research | 8773 | `backend/research/` + `src/research/sepa/` | `bifrost_api/research/` | app.py, sepa/*, screener/*, indicators/*, routers/{screener, greeks, max_pain, option_discovery, data_readiness, sepa_*} | - |

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

> 新 repo 合并重组为 **22** 个 `src/api/**/*.ts` 文件（非 engine 31 文件一一对应）；全部指向 Legacy API（`VITE_API_*`）。

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
| bifrost-trade-core | `tests/test_config*`, `test_portfolio*`, `test_persistence*` 等 | ~15 | - |
| bifrost-trade-socket | `tests/test_connector_ib*`, `test_ib_operator*`, `test_ib_config*`, `test_subprocess_executor_ingest*` | ~5 | - |
| bifrost-trade-worker | `tests/test_daemon_fsm*`, `test_guards*`, `test_state_*`, `test_gs_trading*`, `tests/test_celery_*`, `test_massive_*`, `test_stock_ohlc_*` | ~65 | - |
| bifrost-trade-api | `tests/test_research_app*`, `tests/test_massive_app*`, `test_docs_app*`, `test_monitor_status*`, `tests/research/sepa/test_*`, `tests/test_sepa_*` | ~23 | - |

---

## §8 变更日志

| 日期 | 变更内容 | 操作人 |
|------|---------|--------|
| 2026-05-22 | 创建迁移追踪文档，初始化所有模块为"未开始"状态 | Agent |
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
