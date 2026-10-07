# Trade System 完成度评估 + Backtest 现状（2026-10-04）

只读评估：没有改代码或配置，也没有 push。数据库只做了目录查询和轻量聚合（`kubectl exec` 进 CNPG 跑 `psql`，2026-10-05 04:40 UTC 前后）。
判断标准是一个专业美股期权交易者每天要做的事。D10 实盘下单冻结是有意为之，不算缺陷；本文只说明冻结边界在哪里、冻结之前代码已经做到哪一步。

---

## 0. 一句话结论

**Bifrost 现在是一个很强的「看」的驾驶舱，但「做」和「验」这两个闭环还没合上。**

- **强项（已达专业水准）**：研究选标、波动率分析（IV rank、期限结构、SVI、GEX、max pain）、持仓展示、成交账本对账。
- **短板**：三块共用的底座缺失。它们同时卡住了下单、复盘和回测。
  1. **期权 NBBO（bid/ask）**：链、筛选、回测成交价都用不了点差。
  2. **每日持仓、mark、Greeks、NAV 快照**：所以 Greeks 归因、TWR、Sharpe、R 倍数都算不出来。
  3. **Plan ↔ Trade ↔ Backtest 的关联**：所以「是否按计划执行」「实盘对比回测」都量不了。
- **下单（E 段）**：问题不只是 D10 冻结。代码层**根本没有发单适配器**，`ib_operator` 协议里没有 place/cancel。即使明天解冻，也不会有任何一张订单发出去。

### 各阶段评分

| 阶段 | 评分 | 一句话 |
|---|---|---|
| A 行情与期权链 | ★★★☆☆ 可用 | EOD 分析很完整；盘中只有 3 次快照，加上 IB 对单个合约的报价 |
| B 研究选标 | ★★★★☆ 成熟 | SEPA、Vol ratings、12 个 lens、合约筛选、Copilot 都已上线；事件雷达没有数据源 |
| C 策略构建 | ★★☆☆☆ 半成品 | 有到期 payoff 和 T+0 曲线；没有交互式多腿 builder、T+n、组合 POP |
| D 风控与 Greeks | ★★★☆☆ 读侧可用 | 组合 Greeks、β-delta、Stress、CAR、Backing 都有；限额有 9/12 条 unwritten，也不执行 |
| E 下单执行 | ★☆☆☆☆ 缺失 | 没有订单票据、combo、改单撤单；daemon FSM 完整，但只到模拟成交（D10 有意冻结） |
| F 持仓管理 | ★★★★☆ 可用 | 多账户、按 Trade 分组、到期/指派推演、账本对账；roll 链、调整建议、pin risk 缺失 |
| G 复盘归因 | ★★☆☆☆ 半成品 | Performance 日历和 Review 六值已有；Greeks 归因、TWR、R 倍数被缺失的日快照卡住 |
| H 回测 | ★★☆☆☆ 早期 | 五套互相独立的评估，没有组合级引擎；期权数据其实已有两年，但从没用来跑过；有若干正确性 bug |

---

## 1. 逐阶段评估

图例：✅ 已有 · 🟡 半成品 · ❌ 缺失。路径相对于各 repo 根目录。前端路由注册在 `bifrost-trade-frontend/src/lib/router.tsx`。

### A. 行情与期权链 — ★★★☆☆

| 能力 | 状态 | 依据 | 交易者视角的缺口 |
|---|---|---|---|
| 股票实时报价 | ✅ | plugin `ib_gateway/live.py:315-330`（reqMktData，每 2 秒写一次 redis-ib）；trade-api `market/routers/quotes.py`（`/quotes`、SSE `/quotes/stream`） | 只覆盖 watchlist 和持仓，没有盘前盘后或全市场扫描 |
| 期权实时报价 | 🟡 | `live.py:430-470`：按需单次拉取，只有 bid/ask/last/mid，限于持仓或 watchlist 合约；`OptQuoteAgeLabel` 在超过 10 秒时提示陈旧 | 没有实时 IV/Greeks，也没有全链实时 NBBO |
| 期权链 | 🟡 | `/research/symbol?tab=chain`，`SymbolChainFace.tsx:573-596`：strike、expiry、mark、IV 及其相对拟合的偏差、Δ、Θ、vega、OI、vol；**bid/ask 显示为 "—"** | 看不到点差和流动性，不能直接拿来定限价 |
| IV rank / percentile / term / cone | ✅（cone 🟡） | research `engines/volatility/iv_percentile.py`；`features.option_metric_*`；cone 缺 7d/180d（open-data-gaps R4） | 只有 EOD |
| Skew / SVI 曲面 | ✅ 日频 | `engines/vol_surface/svi.py`、`fit.py`；残差热图 `SymbolVolatilityDepth.tsx` | 没有 25Δ RR / BF 时间序列，也没有日内曲面 |
| GEX、gamma wall、max pain、PCR | ✅ | `engines/gex/exposure.py`、`max_pain.py`、`pcr.py`；`SymbolDealerFace`、`SymbolFlowPcr` | GEX 基于固定的 dealer 方向假设 |
| 订单流 / 逐笔 | ❌ | Options Starter 下 `/v3/trades`、`/v3/quotes` 返回 403 | 看不到 sweep 和异动（订阅限制，不是 bug） |
| 财报日历 | 🟡 | 只有估计值（去年同季 8-K + 52 周，`utils/earningsEstimate.ts`）；Benzinga 返回 403 | 确认日期和估计日期分不开，不知道 BMO/AMC |
| 财报 implied move / crush | ✅ 回看 | `engines/volatility/earnings_moves.py`；`/research/history` | 没有对下一次财报的 crush 前瞻，也没有分解出事件波动率 |
| 盘中时效 | — | 链快照：EOD 1 次 + 盘中 3 次（10:30 / 13:00 / 15:30 ET，plugin `config/schedule.yaml`） | 盘中做 vol 决策只能依赖三次快照 |

### B. 研究选标 — ★★★★☆

| 能力 | 状态 | 依据 |
|---|---|---|
| 股票筛选（SEPA / momentum / 保存的 screen） | ✅ | `/research/stocks`；`engines/sepa`、`engines/momentum` |
| Vol ratings（卖方机会排名） | ✅ | `/research/scan`（5 个 lens 合成一个分数，权重可调）；`engines/scan/build.py` |
| 期权合约筛选 | ✅（09-27 才修好） | `/research/contract-screener`；`POST /research/screener` |
| Terrain / forecast / playbook | ✅ | `stock_forecast_terrain_*`；Symbol 页的 scenario tab |
| Lens / signal-hit / decay | ✅ | `lenses/registry.py`（12 个 lens）；`/research/signal-decay`、`signal-health`、`lens-coverage` |
| Watchlist（含 sizing / Kelly / ATR） | ✅ | `/research/watchlist` |
| Copilot | ✅ 只读 | `/research/copilot/trading`（10 个 `trade.*` 只读工具） |
| 事件雷达 | 🟡 基本空转 | `engines/event_radar/ingest.py` 要人工投放；AlertsPage 头注说明 DEV 上 4 个 store 都是 0 行 |

缺口：筛选没有考虑流动性和点差（同样卡在 NBBO）；没有盘中突破触发。

### C. 策略构建 — ★★☆☆☆

| 能力 | 状态 | 依据 | 缺口 |
|---|---|---|---|
| 多腿构建器 | 🟡 | `/strategy/*` 七个页面于 09-18 退役，重定向到 `/trade/rules`（`layout/redirectRoutes.ts:15-41`）；规则模板 CRUD 在 trade-api `strategy/routers/strategies.py:87-216`；Payoff 面板的结构只有 single / vertical / covered（`utils/optionDiscovery/discoveryStructure.ts:10`） | **没有逐腿选行权价/到期的交互式 builder**；calendar、diagonal、butterfly、ratio 只是枚举值 |
| 结构对比 Compare | 🟡 reviewing | `/research/compare`：按 active rules 摆出 bear call、bull put、CSP、CC、IC | wing 固定 ±5%；POP / EV / p10 标为 owed |
| 到期 payoff | ✅ | core `portfolio/model/payoff.py:63-278`；`RiskProfilePayoffChart.tsx` | 用内在价值计算，跨期结构表达不对 |
| T+n 曲线 | 🟡 | 只有 T+0 一条：`pages/research/analyze/payoff/PayoffChart.tsx:204` | 没有日期滑杆，也没有 IV 偏移的多条曲线 |
| POP / expected move | 🟡 | `payoffModel.ts:125-168`：只按锚定腿的 σ√T | POP 不是组合级，也没有用 skew/SVI 分布 |
| What-if（新交易对组合的影响） | ❌ | 只有持仓场景矩阵 `RiskProfileScenarioMatrix.tsx` | — |
| Strategy dim 枚举 / Instance / Allocation / Plans | ✅ CRUD | core `monitor/reader/strategy_dim_catalog.py`；`strategies.py:361-530`；`plans.py:50-167` | 没有 wheel 生命周期；instance 和订单只能事后 link-fill |
| Sizing | 🟡 | `/risk/sizing`：per-trade/day/week 预算 "unwritten"；Kelly 只给股票按 ATR 用（`utils/riskSizing.ts`） | 期权没有按 max loss 做 Kelly，风险预算也不落库 |

### D. 风控与 Greeks — ★★★☆☆

| 能力 | 状态 | 依据 | 缺口 |
|---|---|---|---|
| 组合 Greeks、β-weighted Δ | ✅（来源混合） | `/risk/portfolio`（`RiskPortfolioPage.tsx:236-284`）；Δ$ 来自 core `model/core.py:376`，Γ/vega/Θ 用 vendor 腿数据 | 有两份 BS（`pricing/black_scholes.py` 和 research `routers/greeks.py`），没有统一的 Greeks 引擎 |
| Stress（价格 × IV） | 🟡 | core `core.py:431-544`（spot ±5/10/15% × IV ±5pt）；`iv_stress_available:false` 时 vol 轴只有一行 | 没有命名历史场景、skew 冲击、跳空加 IV 联动 |
| CAR、Backing Level | ✅ | `core.py:219-316`；`/portfolio/backing`（85% 闸门） | — |
| Margin / BP | 🟡 | `/risk/margin`：broker 汇总加 Cushion | 没有逐仓位维持保证金，也没有 what-if margin |
| 限额 / 集中度 | 🟡 | `/risk/limits`：12 条规则里 **9 条 unwritten**（`utils/limitsModel.ts:66-74`）；allocation 限额能落库但只在 reader 里读到 | **限额不在任何下单前检查里执行**；breach 不持久化 |
| 告警 | ✅ 只读 | `useAlerts`、`AlertsPopover` | 不推送到外部 |
| 对冲（gamma scalping） | 🟡 冻结 | worker `daemon/strategy/gamma_scalper.py`、`hedge_gate.py`、`guards/execution_guard.py`；`/trade/desk` 的 HedgeMenu | **flatten 只写入了命令，daemon 端只打一行 "not implemented yet"**（`control_heartbeat.py:142-143`） |

### E. 下单执行 — ★☆☆☆☆（D10 有意冻结）

| 能力 | 状态 | 依据 |
|---|---|---|
| 订单票据 / 预览 / what-if margin | ❌ | 前端没有 OrderTicket / submit / cancel 组件；Desk 注释写 "Orders are worked in TWS; the desk copies"（`TradeDeskPage.tsx:18`） |
| Combo / BAG | ❌ | 全部 Python 代码里没有 ComboLeg/BAG |
| 改单撤单 | ❌ | 只有只读的 `/open-orders` |
| 成交回报 | ✅（导入） | trade-api `trading/routers/executions.py`；`/trade/fills` |
| ib_operator | 只读 | core `ib_operator/protocol.py:13-24`：`ALL_OPS` 只有 fetch_* / ping / reconnect，**没有 place、cancel**（已核实） |
| Daemon FSM | ✅ 结构完整 | `daemon/fsm/trading_fsm.py`（BOOT→SYNC→IDLE→ARMED→MONITOR→NEED_HEDGE→HEDGING）、`order_manager.py`（只跟踪状态） |
| Paper | 只有日志级模拟 | `app/gs_trading.py` 写死 `paper_trade=True`、`mock_hedging=True`；`hedge_flow.py:137-160` 只记日志，然后调用 `on_full_fill` 假装成交 |

**冻结的边界**：STG `daemon-scale-zero.patch.yaml`（replicas 0）；PROD `daemon-observe-safe.patch.yaml`（FSM 照常运行，对冲只做模拟）；`preflight.js` 从 spine 读 D10，读不到就按 BLOCKED 处理。
**冻结前做到的程度**：信号 → 意图 → 闸门 → FSM → 状态写入已经全链路跑通。缺的是发单适配器、ack/fill 回调、flatten 执行，以及真正的 paper 通道（独立 IB paper 账户或模拟撮合）。

### F. 持仓管理 — ★★★★☆

| 能力 | 状态 | 依据 | 缺口 |
|---|---|---|---|
| Positions 多账户 | ✅ | `/portfolio/positions`（`PositionsPage.tsx`）；core `positions/position_book.py` | 两账户合并后的净 Greeks / β-delta 视图 |
| 按 Trade 分组（Rev .111） | ✅ | `?instance=` / `TradeTab.tsx` / `account_execution_instance_allocation` | 未归属成交只能手工 link |
| Roll 管理 | 🟡 | 只能识别同日 roll（`utils/ledger/sameDayOptionRolls.ts`），Review 路径上画出接缝 | **没有 roll 链字段（parent_trade）**，看不到跨到期累计 credit；没有 roll 候选 |
| 到期 / 指派 | 🟡 | `/trade/expiration`：逐腿推演 roll/close/expire/assign，提前指派风险（分红对比时间价值） | **pin risk 未建**（`expirationModel.ts:140`）；页面决策不落库 |
| 调整建议 | ❌ | 只有 RoomToAdd 和 ShortLegs 的 cushion 告警 | 没有「被突破 → roll out / roll down / 收窄」的规则 |
| 公司行为 | 🟡 | `/portfolio/corporate-actions`：拆股后的 strike/数量换算 | 没有分拆、合并、非标调整合约 |
| 成交账本 | ✅ | `/portfolio/ledger`：Canonical / Book / Only in TWS / Manual 对账 | Flex 只拉 Trades 和 CashTransactions，没拉 OpenPositions / EquitySummary |
| Calendar | ✅ | `/home/calendar`（Rev .145–.150） | 页面只放链接，不能在日历上直接处理 |

### G. 复盘与归因 — ★★☆☆☆

| 能力 | 状态 | 依据 | 缺口 |
|---|---|---|---|
| Performance | 🟡 | `/portfolio/performance`：期权 P&L 日历（41/41 天逐分一致）、Book/Economic 桥、权益曲线 | **NAV 只有当前值**，区间起点是 "not recorded"（`PerformanceReturnBasis.tsx:38-46`），所以算不了 TWR 和 Sharpe |
| Review（exit 六值） | ✅ 部分受阻 | `/review/trade`；`utils/reviewedTrades.ts:153-180`；`trade_review` 表 | early/late 依赖 plan 的退出日，但**没有任何 plan 关联到持仓**（`reviewContracts.ts:129`）；"vs backtest" 列恒为 —（D3） |
| Greeks 归因（Δ/Γ/vega/θ/残差） | ❌ | `/portfolio/pnl-explain` 只有框架，`pnlExplainModel.ts:1-12` 写明缺每日快照（已核实） | **卖方复盘最核心的问题「这周赚的是 theta 还是方向」答不了** |
| 胜率 / 平均盈亏 / MaxDD | ✅ | trade-api `executions.py:1122-1351`；core `strategy_win_rate.py` | 没有 expectancy、R 倍数，也不能按 regime/DTE/delta 分桶 |
| Journal | ✅ | `/research/journal`（5 个 store 在前端 join）；`journal.*` 表 | 没有结构化的交易前后记录模板 |
| 每日持仓快照 | ❌ | `brokerage.positions` 主键是 `(account_id, contract_key)`，只存当前态；worker 的 greeks_snapshot 只在内存里 | Owner 09-30 已批准建表，但还没建 |

---

## 2. Backtest 现状（供集中讨论）

### 2.1 实际上有五套互相独立的「回测」

| # | 是什么 | 代码 | 数据与口径 | 存储 / 页面 |
|---|---|---|---|---|
| ① | **事件回测**（event backtest） | research `engines/backtest/event_query.py`（940 行）、`strategy_templates.py`（8 个模板）、`fills.py`、`walk_forward.py`、`benchmark.py` | 每个事件在入场日和出场日**各取一次 close**；事件类型：earnings / opex / sepa_hit / iv_percentile（sql 未实现） | `research.backtest_run`（只存 summary JSON）；`/research/backtest` Event 页签 |
| ② | **Canonical PnL**（结构模拟） | `engines/backtest/canonical_pnl.py`、`engines/canonical_pnl/compute.py` | **BS 定价 + 单一 ATM IV（不考虑偏斜）+ r=0**；5 种结构（short strangle、PCS、long straddle、CC、short put）；每 ISO 周一个建仓日 | `features.stock_signal_canonical_pnl_daily`；Watchlist / Hypothesis 详情 |
| ③ | **Lens 命中率** | `engines/signal_hit/`；`api/signal_decay.py` | lens 触发后看 T+5 / T+20 的股票前瞻收益 | `features.stock_signal_lens_hit_daily`；`/research/signal-decay` |
| ④ | **候选 / 假设结算** | `engines/candidate_outcome/`；`copilot/agents/hypothesis_resolution.py`；`copilot/harness/validate_hook.py` | T+20 相对 SPY 超额收益，±3% 自动判定；批准假设后自动跑财报回测，win ≥ 50% 就判 validated | `research.candidate_outcome` / `research.hypothesis`；`/research/loop/*` |
| ⑤ | **AI 预测结算** | `engines/backtest/settlement.py`、`regime_stats.py` | 路径命中 / 收盘偏差 | `features.stock_backtest_settlement`；`/research/backtest` Settlement 页签 |

共同点：
- 全部是 Python 逐事件、逐行查库，**不是 bar-by-bar 的事件循环，也不是向量化**（`orchestration/runners.py:202`："Full vectorbt strategy backtests land in a later wave"）。
- **没有组合层面的回测**：没有资金曲线、仓位大小、保证金、同时持有多笔，也不能中途止盈止损或 roll。

### 2.2 数据（2026-10-05 实测）

| 表 | 实测范围 | 回测含义 |
|---|---|---|
| `raw_market.stock_daily` | **2021-09-09 → 2026-10-02**（约 1,364 万行；5 年滚动） | 股票腿事件研究可以回看 5 年 |
| `raw_market.option_daily` | **2024-10-01 → 2026-10-02**（约 4,640 万行；每月 180–220 万行；688 个标的）；字段只有 **OHLCV、vwap、trade_count，没有 bid/ask** | **期权回测其实已经有两年数据了**；但回填只覆盖每张合约到期前 90 天、行权价 ±30% 以内，LEAPS 和深虚做不了 |
| `raw_market.option_snapshot`（vendor IV、Greeks、OI） | **2026-08-05 → 2026-10-02**（约 1,120 万行；只往后积累，保留 90 个交易日） | 历史 Greeks 只有约 2 个月 |
| `raw_market.option_open_interest` | **2026-07-06 → 2026-10-02**（约 578 万行） | OI 历史补不回来 |
| `option_minute` / `stock_minute` | 只有 26 个左右的基准名字，2026-06/08 起 | 做不了日内回测 |
| `features.option_iv_reconstructed_daily` | 2026-06-24 → 2026-10-02（684 个名字） | — |
| `features.stock_signal_lens_hit_daily` | 2024-09-18 → 2026-10-02（约 22 万行，7 个 lens） | — |
| `features.stock_signal_canonical_pnl_daily` | entry 2026-04-06 起，约 306 万行，675 个名字 × 5 种结构；**data_quality 100% 为 `iv_interpolated`，没有一行是 `ok`** | 整张表都是模型价，不是任何真实合约的价格 |
| `research.backtest_run` | **44 条**；最近一次是 09-24；**期权腿的 run 最后一次在 09-01**（当时 option_daily 只有 26 天），之后全部是 `long_stock_event` | 期权数据回填到两年之后，**没有任何人用它跑过期权回测** |

> `bifrost-research/docs/BACKTEST_DATA_COVERAGE.md`（08-31）写的是「option_daily 只有 26 天、stock_daily 15 个月」，**已严重过时**；`event_query.py` 的模块文档和前端 `EventQueryBuilder.tsx:56` 的注释也是同样的旧说法。
> 两条滚动删除：期权 2 年、股票 5 年（`OPTION_WINDOW_DAYS` / `STOCK_WINDOW_DAYS`）。超出的数据会被物理删除，所以**样本只会往前平移，不会变长**。

### 2.3 能力边界

**现在能做**
- 按事件锚定的单次入场/出场（偏移量按日历日算）。
- 多腿期权：跨式、铁鹰、备兑、单腿 call/put。到期日按目标 DTE 选最近的；行权价按「现价 × (1+偏移)」选。
- 佣金每张 0.65（单边）；期权腿用成交价（as-traded）现价；已排除调整合约（0.155.0）。
- 指标：胜率、平均/中位 PnL、Sharpe（假设每周一个事件，按 √52 年化）、MaxDD、MFE/MAE（用股票高低价近似）。
- 样本量标注（少于 5 为「噪音」，少于 30 为「偏少」）；跳过的事件分 `skipped_no_option` / `skipped_no_stock` 分别报。

**现在不能做**
- 滑点：数据里没有 bid/ask，SQL 也没 select 这两列，`FillConfig` 实际只剩佣金在起作用，**滑点恒为 0**。
- 保证金、资金曲线、仓位、组合、同时持仓。
- 止盈止损、roll、提前行权或被指派。
- 按 delta 选行权价（见 B5）。
- 参数扫描、显著性检验。
- **walk-forward 与基准名不副实**：它们是在「每个事件的 PnL + 100」拼出的代理序列上算的；名为 `spy_buy_hold` 的指标其实不是 SPY（`api/backtest_event.py:116-150`）。

### 2.4 正确性问题（代码里已核实，未修复）

| # | 问题 | 证据 | 后果 |
|---|---|---|---|
| B1 | 自动验证钩子查的列名是 `trade_date`，实际列叫 `bar_date`，异常被吞掉，**永远返回 False** | `copilot/harness/validate_hook.py:64,77` | 假设验证从来没有走过期权腿 |
| B2 | 修了 B1 之后，`OPTION_TEMPLATE="short_strangle_30d"` 也不在 `TEMPLATES` 里 | `validate_hook.py:26`；`strategy_templates.py:319-328` | 会抛 ValueError |
| B3 | `_pick_option` 按 `bar_date DESC LIMIT 400` 跨全部行权价和到期日取候选 | `event_query.py:468-540` | 大标的一天就超过 400 张合约，目标到期日可能不在候选里；当天没成交就拿到陈旧 bar；出场时不校验是否同一个 option_ticker |
| B4 | 偏移量按日历日算 | `strategy_templates.resolve_leg_window` | 周五事件 +1 落到周六，回退到周五，持有期变成 0 |
| B5 | `target_delta` 被忽略，而铁鹰的两条卖腿只设了 `target_delta` | `event_query.py:585-587`；`strategy_templates.py:196,218` | **「short_30d_iron_condor」实际是 ATM 铁蝶** |
| B6 | 前视：财报日用 `stock_financials.filing_date`（10-Q/10-K 的提交日）代替发布日 | `event_query.py:145-273` | entry=-1 可能其实已经在财报发布之后 |
| B7 | 幸存者：退市标的前瞻收益为 None，被直接丢掉；改名后的股票轴不连续 | 记忆 delisted_symbols_and_renames | 结果偏乐观 |

另外：Dagster 资产 `runners.run_backtest` 是空壳（`aggregate_accuracy([])`）；`backtest_run` 不存逐事件明细，没法复核或画逐笔分布。

### 2.5 规划现状

- research `docs/plans/RESEARCH_MUSCLE_PLAN.md` 的 Wave RS-C（C1–C4）已完成，注明「真实 walk-forward 是后续工作」。
- `programs/active/market-data-subscription-focus.yaml` P4 的验收项包括「NVDA 3y 12 次财报全部定价」和「5y 股票 / 2y 期权历史可供回测」。数据侧已基本到位，引擎侧没跟上。
- `programs/active/research-loop-automation.yaml` B4（pending）：回测证据要按标的区分。
- spine 里**没有回测的规划条目**；`design/trade/Research Vision.md:79` 把回测定义为 Validate 的一部分；设计稿 `design/trade/Research Backtest.dc.html`。

---

## 3. 讨论回测时要先定的问题（附我的推荐）

1. **回测服务什么决策？** 选项：(a) 假设验证；(b) 卖方结构选型（哪种结构、什么 DTE/delta、何时止盈）；(c) 组合层面的资金曲线。
   **推荐 (b)**。这是期权卖方最常问的问题，也是两年期权日线刚好能回答的。它需要一个带持仓管理（止盈、止损、到期、roll）的 bar-by-bar 引擎，而不是现在的「两个时点各取一次价」。
2. **没有 bid/ask 时成交价怎么算？** close / vwap 加一个按价格或 moneyness 分档的滑点假设，再用最近 90 天的 IB 实时报价校准；还是评估升级 Massive 报价订阅？
   **推荐**先用 vwap 加分档滑点，并在结果上标明口径。
3. **数据保留**：要不要停止物理删除，或把 option_daily、snapshot、OI 归档出滚动窗口，让样本随时间变长？
   **推荐归档**。Greeks 和 OI 现在只有 2–3 个月，越晚开始损失越大。
4. **先修 B1–B5，还是先建新引擎？**
   **推荐先修**。这几个是小改动，但它们正在让自动验证和铁鹰结果失真。
5. **Canonical PnL（BS 合成）和事件回测（真实合约）要不要统一口径？**
   **推荐**：真实合约优先，缺了再用 BS 补，每行标明来源。现在 306 万行全是模型价，UI 上没有明确区分。
6. **判定标准**：validated 要不要最低样本数、置信区间、相对无条件基准的超额？现在 4–5 个事件、胜率 ≥50% 就算通过，lens 命中率在 46–59%。
7. **walk-forward 和 "SPY" 基准**：先下线或改名，还是实现真的？
   **推荐**在真的做出来之前先改名或隐藏，避免误读。
8. **财报事件源**：接 8-K Item 2.02 作为发布日（已有 `sec_8k_filing` 1.57 万行）替代 filing_date，同时解决 B6 和 A 段的财报日历缺口？
9. **回测和交易打通**：trade 加 `backtest_run_id` / `lens_id`（D3，属于架构级 DDL，需要 Owner 批准），`backtest_run` 存逐事件明细，让 Review 的 "vs backtest" 能用？
10. **和日快照的关系**：每日持仓/Greeks 快照（Owner 已批、未建）同时也是「实盘对比回测」的对照样本。要不要和回测一起排期？

---

## 附：本次实测命令（只读）

```bash
export KUBECONFIG=~/.kube/bifrost-k3s.yaml
kubectl -n data exec bifrost-postgres-1 -c postgres -- psql -U postgres -d bifrost_golden_source -tAc "<query>"
```

查询内容：`pg_inherits` 分区与 `reltuples`；`option_daily`、`stock_daily`、`option_snapshot`、`option_open_interest` 的 min/max；两个月分区的 distinct underlying；`canonical_pnl` 的 data_quality 分布；`research.backtest_run` 全表 44 行的 summary。
