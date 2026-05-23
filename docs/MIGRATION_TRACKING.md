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
| bifrost-trade-core | 8 | 0 | 0% |
| bifrost-trade-ib-edge | 4 | 0 | 0% |
| bifrost-trade-api | 9 | 0 | 0% |
| bifrost-trade-data | 4 | 0 | 0% |
| bifrost-trade-research | 4 | 0 | 0% |
| bifrost-trade-frontend | 4 | 0 | 0% |

---

## §2 bifrost-trade-core（共享库 + Daemon）

### §2.1 共享库模块

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| config | `src/config/` | `bifrost_core/config/` | settings.py, yaml_config.py | - |
| core | `src/core/` | `bifrost_core/core/` | dict_merge, redis_url, logging, realtime/redis_*, sse/queue_utils | - |
| persistence | `src/persistence/` | `bifrost_core/persistence/` | status_sink, postgres/{connection, ddl, postgres_sink, accounts_sync, stock_ohlc_massive, ticker_reference} | - |
| portfolio | `src/portfolio/` | `bifrost_core/portfolio/` | accounts, symbol_position, model/{core, payoff}, positions/{portfolio, position_book}, reader/*, services/* | - |
| ib_operator (client) | `src/ib_operator/` | `bifrost_core/ib_operator/` | client.py, protocol.py, config.py | - |
| monitor | `src/monitor/` | `bifrost_core/monitor/` | self_check, reader/{status, strategy, gate_safety, watchlist, market, massive_jobs, ...}, schemas/*, services/* | - |

### §2.2 Daemon 模块

| 子模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|--------|----------|----------|---------|------|
| app | `src/daemon/app/` | `bifrost_core/daemon/app/` | gs_trading.py, entry.py, hedge_flow.py, daemon_handlers.py, snapshot.py, ticker_redis.py | - |
| fsm | `src/daemon/fsm/` | `bifrost_core/daemon/fsm/` | daemon_fsm.py, trading_fsm.py, hedge_fsm.py, events.py | - |
| guards | `src/daemon/guards/` | `bifrost_core/daemon/guards/` | execution_guard.py, trading_guard.py | - |
| execution | `src/daemon/execution/` | `bifrost_core/daemon/execution/` | order_manager.py | - |
| strategy | `src/daemon/strategy/` | `bifrost_core/daemon/strategy/` | gamma_scalper.py, hedge_gate.py | - |
| pricing | `src/daemon/pricing/` | `bifrost_core/daemon/pricing/` | black_scholes.py, greeks.py | - |
| market | `src/daemon/market/` | `bifrost_core/daemon/market/` | market_data.py | - |
| core/state | `src/daemon/core/` | `bifrost_core/daemon/core/` | store.py, metrics.py, state/{classifier, composite, enums, snapshot} | - |
| account_sync | `src/daemon/account_sync/` | `bifrost_core/daemon/account_sync/` | app.py, diff_engine.py, heartbeat.py, redis_keys.py, stream_consumer.py | - |
| sink | `src/daemon/sink/` | `bifrost_core/daemon/sink/` | (postgres sink 实现) | - |

---

## §3 bifrost-trade-ib-edge（IB 边缘服务）

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| connector | `src/ib/`, `src/connector/` | `bifrost_ib_edge/connector/` | connection_policy.py, ib.py, flex_client.py | - |
| ingestor | `src/vendor/ib_ingestor/` | `bifrost_ib_edge/ingestor/` | writer.py, redis_keys.py | - |
| account_agent | `src/vendor/ib_account_agent/` | `bifrost_ib_edge/account_agent/` | writer.py, redis_keys.py | - |
| operator | `src/ib_operator/` (service) | `bifrost_ib_edge/operator/` | service.py, executor.py, redis_io.py, health_redis.py | - |

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
| research | 8773 | `backend/research/` | `bifrost_api/research/` | app.py, deps.py, routers/{screener, greeks, max_pain, option_discovery, data_readiness, sepa_*} | - |

---

## §5 bifrost-trade-data（数据管道）

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| workers | `src/workers/` | `bifrost_data/workers/` | celery_app.py, celery_queue_names.py | - |
| bars | `src/bars/` | `bifrost_data/bars/` | tasks.py, backfill.py, ib_operator_transport.py | - |
| massive | `src/massive/` | `bifrost_data/massive/` | tasks.py, celery_queues.py, beat_schedule, massive_job_goal, snapshot_chain_ingest, stock_ohlc_daily_smart, option_*_pool_fill, polygon_stock_tickers | - |
| massive vendor | `src/vendor/massive/` | `bifrost_data/massive/` | client.py, config.py, reader.py, holidays_sync.py, stock_day_gap.py, contracts_reference_*, snapshots_contracts_gap.py | - |

---

## §6 bifrost-trade-research（SEPA 研究流水线）

| 模块 | engine 源 | 目标路径 | 关键文件 | 状态 |
|------|----------|----------|---------|------|
| sepa | `src/research/sepa/` | `bifrost_research/sepa/` | phase1_engine, phase4_engine, fundamentals_engine, fundamentals_ext_engine, technical_engine, crs_engine, momentum/pattern/structure/short_indicators, readiness_snapshot, financials_data, stock_unified_snapshot_refresh | - |
| screener | (from sepa + backend) | `bifrost_research/screener/` | 股票筛选器 | - |
| indicators | (from sepa technical) | `bifrost_research/indicators/` | 技术指标、IV Cone | - |
| api | `backend/research/` (部分) | `bifrost_research/api/` | research-worker 计算入口（SEPA 流水线触发） | - |

### 关于 research 端口 8773 的分工

- **`bifrost-trade-api` 的 research 域（8773）**：HTTP API 展示层，读 PostgreSQL 返回 SEPA 结果、筛选数据、Greeks 分析
- **`bifrost-trade-research` 的 research-worker**：SEPA 四阶段计算引擎，跑流水线后将结果写入 PostgreSQL

---

## §7 bifrost-trade-frontend（React 前端）

### §7.1 基础设施

| 项目 | engine 源 | 状态 |
|------|----------|------|
| index.html + tsconfig | `frontend/` | - |
| main.tsx + App.tsx | `frontend/src/` | - |
| styles/ (5 CSS) | `frontend/src/styles/` | - |
| public/ | `frontend/public/` | - |

### §7.2 API 客户端模块（31 个）

| 域 | 文件数 | engine 源 | 状态 |
|----|--------|----------|------|
| account | 1 | `frontend/src/api/account/` | - |
| market | 2 | `frontend/src/api/market/` | - |
| monitor | 7 | `frontend/src/api/monitor/` | - |
| ops | 2 | `frontend/src/api/ops/` | - |
| portfolio | 1 | `frontend/src/api/portfolio/` | - |
| research | 9 | `frontend/src/api/research/` | - |
| shared | 3 | `frontend/src/api/shared/` | - |
| strategy | 2 | `frontend/src/api/strategy/` | - |
| trading | 2 | `frontend/src/api/trading/` | - |

### §7.3 页面组件（45 个顶层 Page）

| 页面 | engine 源 | 状态 |
|------|----------|------|
| LivePage | `frontend/src/pages/` | - |
| AccountsPage | `frontend/src/pages/` | - |
| OptionScreenerPage | `frontend/src/pages/` | - |
| StockScreenerPage | `frontend/src/pages/` | - |
| StockDataReadinessPage | `frontend/src/pages/` | - |
| PositionsPage | `frontend/src/pages/` | - |
| TradeHistoryPage | `frontend/src/pages/` | - |
| PerformancePage | `frontend/src/pages/` | - |
| ResearchRiskAnalysisPage | `frontend/src/pages/` | - |
| SettingsPage | `frontend/src/pages/` | - |
| TransferPayPage | `frontend/src/pages/` | - |
| ModelAnalysisPage | `frontend/src/pages/` | - |
| BacktestPage | `frontend/src/pages/` | - |
| OptionDiscoveryPage | `frontend/src/pages/` | - |
| OptionGreeksPage | `frontend/src/pages/` | - |
| StrategyStructurePage | `frontend/src/pages/` | - |
| StrategyOpportunityPage | `frontend/src/pages/` | - |
| StrategyInstancesPage | `frontend/src/pages/` | - |
| StrategyWinRatePage | `frontend/src/pages/` | - |
| StrategyAllocationPage | `frontend/src/pages/` | - |
| GatesConfigPage | `frontend/src/pages/` | - |
| StructureTypeConfigPage | `frontend/src/pages/` | - |
| WatchlistPage | `frontend/src/pages/` | - |
| DaemonStatusPage (Settings) | `frontend/src/pages/status/` | - |
| IbEventSubscribePage (Settings) | `frontend/src/pages/` | - |
| CeleryControlPage (Settings) | `frontend/src/pages/celery/` | - |
| MarketIngestOpsPage (Settings) | `frontend/src/pages/` | - |
| ApiHealthOverviewPage (Settings) | `frontend/src/pages/apiOverview/` | - |
| ArchitectureApisPage (Settings) | `frontend/src/pages/architecture/` | - |
| AccountApisPage (Settings) | `frontend/src/pages/account/` | - |
| ResearchApisPage (Settings) | `frontend/src/pages/` | - |
| MassiveApiStatusPage (Settings) | `frontend/src/pages/massive/` | - |
| DataPage (Settings) | `frontend/src/pages/data/` | - |
| DataOverviewSummaryPage (Settings) | `frontend/src/pages/dataOverview/` | - |
| DataOverviewDetailPage (Settings) | `frontend/src/pages/dataOverview/` | - |
| OptionCoveragePage (Settings) | `frontend/src/pages/` | - |
| StockCoveragePage (Settings) | `frontend/src/pages/` | - |
| MassiveStockCoveragePage (Settings) | `frontend/src/pages/` | - |
| FeedMassiveOverviewPage (Settings) | `frontend/src/pages/` | - |
| FeedMassiveCommonPage (Settings) | `frontend/src/pages/` | - |
| FeedMassiveOptionPage (Settings) | `frontend/src/pages/` | - |
| FeedMassiveStockPage (Settings) | `frontend/src/pages/` | - |
| StrategyInstanceDetailPage | `frontend/src/pages/strategy/` | - |

### §7.4 共享组件与工具

| 类别 | 文件数 | engine 源 | 状态 |
|------|--------|----------|------|
| components/ | 26 | `frontend/src/components/` | - |
| hooks/ | 4 | `frontend/src/hooks/` | - |
| utils/ | 16 | `frontend/src/utils/` | - |
| constants/ | 2 | `frontend/src/constants/` | - |

---

## §8 测试迁移

| 目标 Repo | engine 测试源 | 测试文件数 | 状态 |
|-----------|--------------|-----------|------|
| bifrost-trade-core | `tests/test_config*`, `test_daemon_fsm*`, `test_guards*`, `test_portfolio*`, `test_persistence*`, `test_state_*`, `test_gs_trading*` 等 | ~45 | - |
| bifrost-trade-ib-edge | `tests/test_connector_ib*`, `test_ib_operator*`, `test_ib_config*`, `test_subprocess_executor_ingest*` | ~5 | - |
| bifrost-trade-api | `tests/test_research_app*`, `tests/test_massive_app*`, `test_docs_app*`, `test_monitor_status*` | ~8 | - |
| bifrost-trade-data | `tests/test_celery_*`, `test_massive_*`, `test_stock_ohlc_*`, `test_holidays_*` | ~20 | - |
| bifrost-trade-research | `tests/research/sepa/test_*`, `tests/test_sepa_*` | ~15 | - |

---

## §9 变更日志

| 日期 | 变更内容 | 操作人 |
|------|---------|--------|
| 2026-05-22 | 创建迁移追踪文档，初始化所有模块为"未开始"状态 | Agent |
