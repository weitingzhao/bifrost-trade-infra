# Screening 档案与授权最小版：方案（W-31 第 3 轮 3.1）

> **状态：方案，等 Owner 过目。** 只读调查后写成，没有改代码、建表、派任务或改规则。
> 2026-10-22 凌晨（CDT 10-21 23:xx）写。起因：Owner 10-21 23:2x 定「D1 A」，第 3 轮主线是 Screening 最小业务闭环，先做本文这一步。
> 依据：
> - `agent-config/work/multi-agent/PLAN-round3-draft-2026-10-22.md` 第三节；
> - 共享记忆 `project_crew_business_issue_handoff`（「当前收敛顺序 2026-10-19」、后续设计顺序表第 1 行、Screening 授权样例）和 `project_crew_product_takeover_design`；
> - 下面各节注明的代码位置。
>
> 代码基线（本文所有行号以此为准）：
>
> | 仓库 | 提交 |
> |---|---|
> | bifrost-trade-frontend | `28bf801f` |
> | bifrost-research | `73694cc` |
> | bifrost-trade-api | `c947a89` |
> | bifrost-platform | origin/main（10-21 晚） |
> | bifrost-trade-infra | `dfb2b28` |
>
> 行号来自两次只读代码调查；第二节的规则和本文关键结论我逐处对过代码。
> 不确定的地方写「待确认」，没有用数据核实的写「未核实」。

收口标准（后续设计顺序表第 1 行）：**读完能知道 Screening 能做什么、谁能决定什么；具体未定参数先形成方案。**

---

## 零、一页看完

- **现在能做的**：
  - 太太在 Trade 驾驶舱的 `Research › Stock screen`（`/research/stocks`）上，从约 3,800 只美股里按条件筛选。
  - 条件在 9 个阶段里开关，按 SEPA、Radar、Premium 三个模型排序，逐只看「为什么留下、为什么被筛掉」。
  - 可以存 screen、把候选加进 Candidate Pool、对候选「Plan this」。
  - 筛选在浏览器里做，服务器每个交易日晚上算一次分数。
  - 不能做的：
    - 看历史某天的筛选结果；
    - 导出；
    - 改、删已存的 screen；
    - 页面头上看数据日期。
- **方法基线**：
  - 核心是 SEPA：Minervini 趋势模板 11 条 + 基本面 8 条 + 动量 10 个信号 + 期权结构。
  - 综合分 = 基本面 30% + 趋势 35% + 动量 20% + 期权 15%，分 A+/A/B/C/D 和 PIVOT/SETUP/WATCH/AVOID。
  - 缺值一律按「不通过」算。
  - 每个交易日纽约时间 22:30 跑一次。
  - 10-21 实测：PROD 评了 3,793 只，数据日 2026-10-21。
- **数据范围**：
  - Research 只读 `raw_market.*`，只写 `dw_stock.*`、`features.*`、`research.*`。
  - Trade 前端经 Research API 读（trade-api 那边也只是 HTTP 转发），不碰 Golden Source 的库。
  - **没有发现越过 D13 的写入。**
- **谁能决定什么**：沿用 Owner 10-19 已定的授权方向（第四节）。
  - 太太：提问题、给事实、确认自己用得好不好。
  - 业务参谋：调查、解释、提议、组织试用、据实结束。
  - 建设负责人：在常备授权内接单、开发、验证、交付到分支和 STG。
  - 总参谋长：跨产品冲突和无人承接。
  - Owner：改选股方法、加数据、读账户内容、超预算、架构和 PROD 发布。
  - **运行时里现在还没有「太太」「业务参谋」「建设负责人」这三种身份**，最小版先用兼任和代录（第五节 S3、S6）。
- **要 Owner 定的 10 件**：第五节。每件都有推荐，推荐里没有架构级改动。
  - 没回的照推荐走，事后审计（Owner 10-11 的规矩）。
  - 例外：**S2 要 Owner 自己动手**（改 Secret）；**S4 要 Owner 告诉我们一个事实**（太太平时从哪里找我们）。

---

## 一、Screening 现在能做什么（能力清单）

路径前缀：
- `FE` = `bifrost-trade-frontend/src`
- `RS` = `bifrost-research/src/bifrost_research`
- `TA` = `bifrost-trade-api/src/bifrost_api`

### 1. 页面

| 页面 | 地址 | 位置 |
|---|---|---|
| **Stock screen**（主页面，导航在 Discover 下） | `/research/stocks` | `FE/layout/routeTable.research.ts:167-179`；`FE/layout/researchNavCatalog.ts:186`；标题 `FE/pages/research/stocks/StockScreenPage.tsx:499` |
| **Stock screen · method**（方法面，四个标签：Models、Conditions、Screens、Queue；没有导航行，从页面上的 ⧉ 进） | `/research/lab/stocks` | `FE/layout/routeTable.research.ts:183-191`；`FE/pages/research/stocks/StockScreenMethodPage.tsx:16-40` |

旧地址（ratings/stocks、screener、explorer、momentum-radar 等）都跳到这两页：`FE/layout/redirectRoutes.ts`。

相邻但不是选股的页面：
- Vol ratings（`/research/scan`）
- Option screen（`/research/contract-screener`，筛期权合约）
- Candidate Pool（`/research/loop/candidates`）

### 2. 能做的事

以下行号都在 `FE/pages/research/stocks/` 下。

| 能力 | 说明 | 位置 |
|---|---|---|
| 选股票池 | All evaluated / Option universe / Watchlist / In the book；S&P 500 灰掉（没有成分数据）。股票池在浏览器里过滤。 | `StockScreenPage.tsx:76-92, 160-166` |
| 选起点 | 5 个预设 + 已存的 screen。5 个预设里只有「2 of 3 models」「Setup shape」能用，另 3 个标「not offered」（缺数据，见第六节） | `stockScreenStages.ts:272-314`；`ScreenPanel.tsx:130-144` |
| 开关条件 | 9 个阶段：模型一致、趋势模板 N/11、成长 N/8、动量 N/10、Radar 等级、结构、情绪、催化剂窗口、Pine 信号、期权适配（另有「质量」阶段整段标缺数据）。每个阶段可设「至少 N 条」。 | `stockScreenStages.ts:76-222`；`StageRow.tsx:192-205` |
| 即时重算 | 没有 Run 按钮，任何改动都在浏览器里重新筛 | `stockScreenModel.ts:412-431` |
| 排序 | 按 SEPA / Radar / Premium / None；SEPA、Premium 可在浏览器里调权重（4 个预设 + 0–60 滑块，只影响本页显示） | `ResultHead.tsx:148`；`RankDrawer.tsx:71-105`；`stockScreenModel.ts:70-75` |
| 看去留依据 | Why 抽屉：分数构成、三个模型各自的线、每个阶段逐条 ✓/✕；被某阶段筛掉的名单（−N） | `WhyDrawer.tsx:129-279`；`StageRow.tsx:172-178` |
| 版本 | 每次改动生成一个版本，可回到某版再分叉；**只在页面内存里，不保存** | `StockScreenPage.tsx:137-138, 201-219` |
| 存 screen | 存为 `stock_screen.v2`（阶段、Pine、股票池）；条件为空或词汇表校验不过时按钮灰掉；手机上不显示该按钮 | `SaveScreenAction.tsx:37-86`；`stockScreenView.ts:86-102, 165-180` |
| 套用已存 screen | v2 原样恢复；v1 把能对上的条件映射过来，对不上的列出名字 | `StockScreenPage.tsx:259-286`；`stockScreenView.ts:105-136` |
| 后续动作 | Pool（加入 Candidate Pool）、Plan this（建策略计划，跳 `/trade/plans`）、SEPA 名可 pin / 存为假设 | `ResultTable.tsx:232-252`；`WhyDrawer.tsx:281-292` |
| Leaders | Radar 跨交易日排行（前 200 行），不受 screen 影响 | `LeadersFace.tsx:49`；`leadersModel.ts:125-141` |
| 方法面 | Models（模型事实与重叠）；Conditions（旧版 v1 筛选，可存 screen）；Screens（列出已存 screen，只读）；Queue（每晚 SEPA 候选与证据，可加入 Watchlist） | `method/ModelsFace.tsx:28`；`method/ConditionsFace.tsx:145-164, 357-508`；`method/ScreensFace.tsx:85-111`；`method/QueueFace.tsx:562` |

### 3. 做不到的

- 看历史某天的结果：所有读都取最新，不带日期；只有 Leaders 能看到跨日。
- 导出：只有 Option screen 能导 CSV。
- 改名、改定义、删除、退役已存 screen：页面上没有，接口里有（第三节）。
- 存版本树：`ScreensFace.tsx:107-111` 自己标了「owed」。
- 「→ Autopilot objective」按钮常灰：`StockScreenPage.tsx:508-513`。
- 页面头上没有数据日期：日期只在 Rank 抽屉的来源行（`StockScreenPage.tsx:403-408`）和方法面 Conditions 的标签上。

### 4. 前端调用的接口

位置：`FE/pages/research/stocks/useStockScreenData.ts`，基址 `FE/lib/devApiUrl.ts:66-75, 124-137`。

| 读什么 | 接口 | 后端 |
|---|---|---|
| SEPA 全表（每名 11+8 条、分数、排名） | `GET /analytics/sepa/screener-wide?limit=5000` | Research API |
| Radar 等级、动量 | `GET /research/momentum/radar`、`/research/data/readiness/momentum-grades` | Research API；后者经 trade-api 转发 |
| 动量、结构、情绪信号 | `GET /research/data/readiness/tier-stats`、`tier-filter`、`momentum-filter` | trade-api 转发到 Research（`TA/research/analytics_reader.py:1-19, 188-206`，HTTP 代理） |
| Premium 分 | `GET /research/scan?preset=neutral…` | Research API |
| 8-K、财报日 | `GET /research/narrative`、`/research/narrative/earnings/batch` | Research API |
| Pine 信号 | `GET /research/pine/signals`、`/research/pine/scripts` | Research API |
| 已存 screen | `GET/POST /research/screens`、`GET /research/screens/vocabulary`（带 Research 令牌） | Research API |
| 股票池 Watchlist / In the book | `/api/market/watchlist`；monitor 状态里的持仓 | Trade |
| 加候选、建计划 | `POST /research/candidates`（Research）；`POST /api/account/strategies/plans`（Trade） | 各自 |

### 5. Research 后端的接口

| 接口 | 位置 | 读 |
|---|---|---|
| `/analytics/sepa/*`（criteria-stats、screener-wide、fundamental-filter、tier-stats、tier-filter 等） | `RS/api/sepa.py`、`RS/api/sepa_reader.py`、`RS/api/tier_reader.py` | `dw_stock.mart_sepa_*` |
| `/research/sepa/model/daily`、`/research/sepa/model/candidates` | `RS/api/research_engines.py:681, 755` | `features.stock_signal_sepa_daily` |
| `/research/momentum/radar`、`/research/momentum/grades` | `RS/api/research_engines.py:54, 138` | `features.stock_signal_momentum_daily` |
| `/research/scan` | `RS/api/scan.py:261` | `features.stock_signal_scan_daily` |
| `/research/screen`、`/research/screen/coverage`（多「面」筛选，在期权股票池上） | `RS/api/screen.py:68, 114`；`RS/lenses/screen.py` | 9 张 `features.*` 表 |
| `/research/screens`（存 screen：列、建、读、改 PATCH、退役） | `RS/api/saved_screen.py:70-138`；`RS/repositories/saved_screen.py` | `research.saved_screen` |

**服务器端不执行已存的 screen**：没有找到按它跑的作业，只有前端读。`RS/repositories/saved_screen.py:77-80` 的阶段表只用来校验存进来的定义。

---

## 二、方法基线

规则都由 dbt 模型和 Research 引擎在服务器端算好，前端只组合和展示。下表是**现行方法**，第五节 S1 的「改方法」以它为基准。

### 1. 股票池

| 池 | 规则 | 位置 | 10-21 实测 |
|---|---|---|---|
| SEPA 评估池 | `raw_market.ticker` 中 `instrument_type='CS'`、`market='stocks'`、在市、币种 USD | `RS/dbt/models/intermediate/dim_universe.sql:12-16` | 3,793 只（`screener-wide` 的 `count`，limit 5000 未截断） |
| 期权股票池 | 三档：<br>resident = SPY / QQQ / IWM、watchlist 缓存、指数期权根；<br>core = 30 天日均成交额 ≥ 2 亿美元进、< 1.2 亿出；<br>edge = 最新 SEPA 为 SETUP / PIVOT 且分 ≥ 70，保留 130 天；<br>最近收盘须在 14 天内 | `RS/engines/option_universe/entry.py:60-82` | 751 只（`/research/screen/coverage`） |

另外三点：
- SEPA 排名不含基本面数据不足的名字：`mart_sepa_screening_ranked.sql:14-18` 只留 `NOT fund_insufficient` 的。
- Radar、多面筛选在期权股票池上；SEPA 在评估池上。**两个池大小差五倍。**
- 页面上「Option universe」实际按「有 Premium 分」过滤（`StockScreenPage.tsx:163`）。它的提示文字写 691 只，是写死的旧数。

### 2. 规则

**趋势模板 11 条**：`RS/dbt/models/marts/mart_sepa_technical_eval.sql:46-58`，只评至少有 252 根日线的名字。
- 50 日均量 > 100,000；
- 收盘 ≥ 52 周低 × 1.3；收盘 ≥ 52 周高 × 0.75；
- SMA50 > SMA150；SMA50 > SMA200；SMA150 > SMA200；
- SMA200 高于 20 根前；
- 收盘 > SMA50 / SMA150 / SMA200；
- CRS（252 日收益的全市场百分位）≥ 70。

**基本面 8 条**：`mart_sepa_fundamental_eval.sql:27-63`。
- EPS 季度同比 ≥ 25%；营收季度同比 ≥ 25%；
- EPS、营收连续两季加速；
- EPS、营收 3 年复合 ≥ 15%（两端为正）；
- EPS、营收年度增速加速。

**动量 10 个信号**：`mart_sepa_tier_momentum.sql:117-154`，分数 = 通过数 / 10。

**结构 8 个信号**：`mart_sepa_tier_structure.sql:143-174`。

**情绪 6 个信号**：`mart_sepa_tier_sentiment.sql:71-94`。不进综合分。

**期权结构分**：`mart_sepa_tier_options.sql:60-123`，由 IV 百分位、PCR、零 gamma、墙位等现有分量平均。

### 3. 综合分、分级、排序

**综合分**：`mart_sepa_composite_score.sql:14-20`。

`基本面通过数/8 × 0.30 + 趋势通过数/11 × 0.35 + 动量分 × 0.20 + 期权结构分 × 0.15`

- 没有动量分时按 0 计；没有期权分时按 0.5 计。

**等级**：`mart_sepa_feature_daily.sql:42-67`。

| 等级 | 综合分 |
|---|---|
| A+ | ≥ 0.85 |
| A | ≥ 0.75 |
| B | ≥ 0.60 |
| C | ≥ 0.45 |
| D | 其余 |

**阶段**：

| 阶段 | 条件 |
|---|---|
| STAGE_2A | 趋势 ≥ 8 且综合分 ≥ 0.70 |
| STAGE_2B | 趋势 ≥ 6 |
| STAGE_1 | 综合分 ≥ 0.55 |
| STAGE_4 | 其余 |

**路径**：

| 路径 | 条件 |
|---|---|
| PIVOT | 综合分 ≥ 0.75 且趋势 ≥ 8 |
| SETUP | 综合分 ≥ 0.60 |
| WATCH | 综合分 ≥ 0.45 |
| AVOID | 其余 |

**排名**：按综合分 `rank()`、百分位、十分位，见 `mart_sepa_screening_ranked.sql`。

**Radar**：`RS/engines/momentum/radar.py`。
- 等级：A+ ≥ 85，A ≥ 75，B ≥ 60，C ≥ 45（`:99-109`）；
- 路径：`:111-138`；权重：`:53-63`。

**页面上三个模型的线**：`FE/pages/research/stocks/stockScreenModel.ts:52-58`。
- SEPA：path 为 SETUP 或 PIVOT；
- Radar：A+ 或 A；
- Premium：composite ≥ 70（neutral 预设）。

**页面上的预设**：`stockScreenStages.ts:272-314`。

| 预设 | 内容 | 能用吗 |
|---|---|---|
| 2 of 3 models | 至少两个模型过线 | 能 |
| Setup shape | 趋势 ≥ 9 + 结构收敛 | 能 |
| Growth + cash | — | 缺数据，不提供 |
| Event window | — | 缺数据，不提供 |
| Premium seller | — | 缺数据，不提供 |

**页面默认权重**：Model 35/30/20/15（`stockScreenModel.ts:70-75`）。

### 4. 缺值怎么算

| 哪里 | 怎么算 | 位置 |
|---|---|---|
| SEPA 的每一条（dbt） | `coalesce(…, false)`：**缺值 = 不通过** | 上面各 mart |
| 基本面的筛选和分布接口 | 排除 `insufficient_data` 的名字 | `RS/api/sepa_reader.py:130, 183` |
| 多面筛选（`/research/screen`） | 缺值单独列为 missing，要求的面缺值则不入选 | `RS/lenses/screen.py:258-266, 310-313` |
| 页面 | 模型没覆盖的名字单列「Not rated by …」；条件没数据的 chip 写明原因 | `stockScreenView.ts:44-48`；`StageRow.tsx:219` |

### 5. 数据来源

- **股价、基本面、比率、空头**：Massive / Polygon，经 Market Data Plugin 写入 `raw_market.*`（`RS/dbt/models/sources.yml:7`；`RS/orchestration/market_slot_schedules.py`）。
- **8-K**：`raw_market.sec_8k_filing`。
- **期权指标**：Research 自己的 volatility、gex 引擎写 `features.*`。
- **IB Flex**：不是 SEPA 的输入（`RS/orchestration/sepa_projection_asset.py:29-30`）。
- **期权逐笔**：没有权限（`market_slot_schedules.py:122-125`），所以「Order-flow sentiment」这一面 10-21 实测读到 0 / 751。

### 6. 更新频率

**主作业** `research_trading_day`：每个交易日纽约时间 22:30（`RS/orchestration/schedules.py:94-99`）。跑 dbt、SEPA 投影、动量、scan、期权股票池、信号命中。

**上游定时任务**（`market_slot_schedules.py`，UTC）：

| 内容 | 时间 |
|---|---|
| 日线 | 每天 22:00 |
| 基本面轮转 | 03:00 |
| 全市场比率与空头 | 周二至周六 04:30 |
| ticker 详情 | 03:30 |

**日期的处理**：
- 数据日取最新交易日（`RS/dbt/macros/sepa_session.sql:12-14`）。
- SEPA 投影每晚只写一个交易日，不补跑（`RS/orchestration/sepa_projection.py:273-278`）。
- 读接口取最大日期，**不返回「是否过期」**。
- 前端页面头上不显示日期。

**10-21 23:1x CDT 实测**（只读 GET）：

| 环境 | 结果 |
|---|---|
| PROD | 基本面、技术面的 eval_date 都是 2026-10-21；Radar 2026-10-21 评级 747 只（A 4、B 259、C 447、D 37、A+ 0） |
| STG | 同一日期、同一数字 |
| DEV | 同一日期、同一数字 |

三个环境相同，原因见第三节：只有一个 Research 实例。

---

## 三、数据范围与 D13

| 数据 | 谁写 | 谁读 | 经由 |
|---|---|---|---|
| `raw_market.*`（日线、财报、比率、空头、8-K、ticker） | Market Data Plugin | Research（dbt、引擎），只读 | — |
| `dw_stock.mart_sepa_*`、`dw_stock.dim_universe` | Research dbt（`RS/dbt/profiles.yml:11, 21`） | Research API | — |
| `features.stock_signal_{sepa,momentum,scan}_daily` 等 | Research 引擎、投影 | Research API | — |
| `research.option_universe` | Research 引擎 | Research API | — |
| `research.saved_screen` | Research API（`/research/screens`） | Research API | 前端带 Research 令牌 |
| `research.candidate_pool`、`candidate_outcome` | Research API（Pool 按钮） | Research API | 前端 |
| Trade 的 watchlist、策略计划 | trade-api（Trade 库） | 前端 | `/api/market`、`/api/account` |
| 持仓（In the book） | Trade 的 monitor | 前端，在浏览器里过滤 | monitor 状态 |

**D13 核对结论**：
- `bifrost-research` 的 `src/`、`scripts/` 里没有对 `raw_market.*` 的 INSERT、UPDATE 或 DELETE。
- 选股路径上没有访问 Trade 库。
- trade-api 读 Golden Source 是 HTTP 转发到 Research API，见 `TA/research/analytics_reader.py:1-19`。
- Research 另写 `ops_dbt`（Elementary）和 `ops_dagster`，research 仓库的 CLAUDE.md 列为允许。

**两条和 Screening 直接相关的事实**：

1. **只有一个 Research 实例。**
   - STG、PROD 的 `/api/plugin/research` 都转到 `research` 命名空间的同一个 `research-api`（infra `k8s/overlays/stg/trade-ingressroute.yaml:83-93`；prod 同）。
   - 库是唯一的 `bifrost_golden_source`。
   - 后果一：在 STG 页面上存 screen、加候选，写的是和 PROD 同一张表。
   - 后果二：Research 端的改动没有单独的 STG 可试，一发就是所有环境。
2. **持仓是账户内容。** 「In the book」在太太自己的浏览器里用持仓过滤，这没有问题。但 Agent 读持仓按现行工作模式属于「读账户内容」，要 Owner 签（`WORKMODE-owner-chief-of-staff-2026-10-15.md` 第一节）。

---

## 四、角色与授权

**已定、不再问**：
- 授权方向是 Owner 10-19 定的（记忆 `project_crew_business_issue_handoff`「Owner 确认的授权方向与常备授权最小内容」）。
- Screening 常备授权样例也已记下，预算只定原则、不定数。
- 下表把它落到 Screening 上，并对照现在系统里实际有什么。

| 角色 | 能决定 | 不能决定 | 系统里现在有什么 |
|---|---|---|---|
| **太太**（使用者） | 提出问题或建议、补充事实；**确认自己用的功能好不好用**（体验验收，不用 Owner 再确认一次）；撤回自己还没被接单的建议；在页面上为自己调视图（股票池、条件、权重滑块、存 screen），这是使用，不是改方法 | 发布；资金操作；改服务器端选股方法或阈值；看所有产品资料；其他决定权要 Owner 明确授权。试用通过不等于批准发布 | Research 按令牌区分用户（`RESEARCH_USERS`，`RS/auth/bearer.py:24-33`）；**她有没有自己的用户待确认**（名单在 Secret 里，没读）。Trade 写操作只有一把共用的 operator 令牌（`FE/components/auth/TradeOperatorDialog.tsx`）。运行时没有家庭成员身份（`actor_kind` 只有 host / executor / controller / owner / seat / thread，platform `migrations/0001_core.sql:9`） |
| **Owner** | 目标、规则、权限外事项；**选股方法的实质变化**（清单见 S1）；新数据源、采购、扩大采集；Agent 读账户内容；超预算；降低关键验收；架构级改动（新路由、表、列、外部依赖）；PROD 发布与 Research 发版；签规则 | —（不必替太太确认体验，也不必每个普通改善都签） | Console 审批、签规则、签收 |
| **业务参谋** | 在获准资料内调查、解释已有能力、**主动提议**（标明是参谋提议）、请求评估、核对范围、组织太太试用；工程验证满足且太太明确确认解决时据实结束；已有功能指导一下就解决的，不开发直接结束 | 伪造满意或批准；把沉默算通过；把自己的提议记成太太的要求或 Owner 的批准；派工（接单是建设负责人的事）；改方法 | **没有这个岗位**。运行时只有 `job:chief_of_staff`、`planner`、`implementer`、`reviewer`、`verifier`（infra `agentrt-rules/prod/job-*.yaml`） |
| **建设负责人** | 评估、接单（写清接什么、做到哪、怎么验、什么时候反馈）、开发、验证、交付到分支和 STG（STG 发版 Agent 自己做，Owner 10-14）；超授权的先接调查 | 承诺没授权的完整交付；借修 Bug 改规则；PROD 发布（走审批单）；**Research 发版**（不在 Agent 可自主的 STG 范围内，要 Owner 点头，工作区 CLAUDE.md §5）；超出常备授权 | 没有专门岗位；最接近的是 planner 拆活加 implementer / verifier / reviewer。常备授权 `standing-envelope:dev` v4（PROD）：dev 租户、最高到推分支、每 mission 40 次尝试或 48 小时、执行者 claude / codex / cursor / deterministic、主机 agent-06 |
| **总参谋长** | 跨产品资源与优先级、无人承接、责任争议；看全局；写 mission、出决策卡 | 替 Owner 批权限外动作；改规则；冒充 Owner。任务复杂本身不是升级理由 | 席位在 PROD（`job:chief_of_staff`，资格考试已过） |

**两条接口上的事实**（会影响授权怎么落地）：

- **已存的 screen 没有归属。**
  - `research.saved_screen` 没有 owner 列（`RS/schema/ddl.py:882-895`）。
  - 列表不按用户过滤（`RS/repositories/saved_screen.py:407-418`）。
  - 任何一个 Research 用户都能列出、修改、退役全部 screen。
- **Research 的读接口大多不要令牌**（`RS/api/app.py` 没有全局鉴权），在局域网里能直接读。
  - 写接口和 `/research/screens` 要令牌（`Depends(require_owner)`）。
  - `/research/candidates` 的 POST 可在请求体里指定 `owner_id`。

---

## 五、待 Owner 定的参数（选项 + 推荐）

规矩：
- 没回的照推荐走、事后审计。
- 带「架构级」的选项必须等 Owner。本节的推荐都不是架构级。

### S1　什么算「改选股方法」（要 Owner 定的那条线）

**A（推荐）**：

- **算改方法、要 Owner 定的**：
  - 服务器端的条件和阈值（第二节第 2 条）；
  - 综合分四个权重 30/35/20/15；
  - 等级、阶段、路径的分档；
  - 缺值当不通过的做法；
  - 两个股票池的定义；
  - 窗口（252 日、多面筛选的 7 天）；
  - 页面的默认值：默认预设、默认股票池、默认权重；
  - 新增排名或推荐逻辑；
  - 把「未知」改成「通过」。
- **不算**：
  - 太太在页面上为自己调视图；
  - 如实显示未知、显示依据和日期；
  - 修复明确规则和实现之间的偏差；
  - 同语义、同结果的性能优化。

B：更松，页面的默认预设和默认视图归业务参谋与建设负责人。

理由：A 和 10-19 样例「默认股票池/窗口……须 Owner 决定」一致。

### S2　太太的登录身份（Research 用户）

**A（推荐）**：给太太单独一个 Research 用户。
- 做法：`RESEARCH_USERS` 加一条（改 Secret，**只能 Owner 做**）。
- 她在页面右上角用自己的令牌登录 Research 部分。
- Trade 写操作（Plan this）仍要共用 operator 令牌，所以第一轮试用只用 Research 部分：筛选、存 screen、Pool。

B：她用 Owner 的 Research 用户。缺点：记录分不出是谁做的。

C：先不给她登录，试用时 Owner 在旁边操作。

注：A 也解决不了「screen 没有归属」（S9）。

### S3　太太在业务问题记录里的身份

**A（推荐）**：最小版不给她运行时身份。
- 业务参谋代录，来源写「太太」，她的确认按原话记（时间、入口）。
- 不用 Owner 身份冒充她（兼容边界第 2 条）。

B：新增家庭成员身份（改 `actor_kind` 约束，**架构级**）。

理由：第 2 步只走一条真实问题。等第 3 步外部入口时，身份和入口一起定。

### S4　太太从哪里找业务参谋（入口）——**待 Owner 告诉我们一个事实**

现在没有给她的入口：
- Console 要令牌；
- 运行时里没有她的身份；
- 外部 AI 入口是第 3 步。

| 选项 | 做法 | 代价 |
|---|---|---|
| A | 第一条问题由 Owner 转述（在统筹线程或 Console Chief 页说「太太说……」），业务参谋记来源 | Owner 当传话人，和「Owner 只管三件事」相冲突，只能当一次性的过渡 |
| B | 给她 Console 登录，用 Chief 对话页 | Console 现有角色能不能只开对话、不看运维信息，**待确认**；看到的资料可能过宽 |
| C | 把第 3 步的外部入口提前 | 违背「先闭环、再入口」的顺序 |

**推荐 A，只用于第一条问题**。请 Owner 先说一句：太太平时怎么告诉你 Screening 不好用？如果她已经有固定的地方（例如某个聊天应用），第 3 步就从那里做。

### S5　试用环境

**A（推荐）**：试用放 **STG**（`stg.trader.bifrost.lan`）。
- 只改前端或 Trade 的改进，在 STG 先试；STG 发版 Agent 自己做。
- 要改 Research 的改进，因为只有一个实例（第三节）：
  - 只做向后兼容的新增（新字段、新接口），不改已有返回；
  - 发版照规矩要 Owner 点头。
- 提醒太太：在 STG 存的 screen 和 PROD 是同一张表。

B：给 Research 建 STG 副本。大工程，不在最小版里。

C：直接在 PROD 试。每次都要建 PROD 审批单。

### S6　业务参谋、建设负责人由谁来当

**A（推荐）**：最小版不建新岗位。
- 业务参谋由参谋长席位兼任，记录里标明以哪个职责行事。
- 建设负责人由接单 mission 的 planner 担任；统筹线程在过渡期兼。
- 复核独立性照原规则。

B：新建 `job:business_advisor`、`job:build_lead` 两条岗位规则。要 Owner 签，可以接 3.3 的资格流水线考试上岗。

理由：
- 记忆「职责不等于独立模型、常驻进程；小产品可兼任」。
- 先用一条真实问题看两种职责在哪里冲突，再决定要不要拆。

### S7　投入上限

**A（推荐）**：
- 沿用已签的 `standing-envelope:dev` v4，不另定数：每 mission 40 次尝试或 48 小时。
- 同一业务问题跨 mission 的累计，先在问题记录里手记，不做程序检查。
- 费用和订阅一律另报 Owner。

B：现在定一个累计数，并在 3.2 做程序检查。要 Owner 给数。

注：
- Owner 10-19 说「预算不定数值」，所以推荐 A。
- 墙钟预算从 mission 创建时起算，等待试用的时间也算在内（platform `api/internal/agentrt/store/missionbudget.go:60, 88-102`）。不能说「等待时预算会自动暂停」。
- 超时后 mission 卡住，由 Owner 在卡上加时（`owner_granted_wall_hours`，同文件 `:194-202`）。

### S8　业务参谋和 Agent 能看哪些数据

**A（推荐）**：
- 只读 Screening 的结果和方法数据：第三节表里的 `dw_stock`、`features`、`research` 读接口和已存 screen。
- 不读账户内容。持仓只在太太自己的页面上用；Agent 要读按现行规则请 Owner 签。
- 不向外部 AI 发送数据，第 3 步再定。

B：允许业务参谋读持仓，以理解她的使用场景（Owner 一次性签）。

### S9　已存 screen 的归属

**A（推荐）**：维持共享。
- 家庭两人互相能看、能改；档案写明。
- 将来要分开再改表。

B：现在加 owner 列（改表，**架构级**）。

### S10　方法基线怎么钉、档案放在哪

**A（推荐）**：
- 方法基线用提交号钉：research（dbt 和 API）、frontend（页面条件与预设）各一个，加第二节的规则表。
- 档案放 `agent-config/work/crew/PROFILE-screening.md`。
  - 这个仓库是公开的，所以档案里不写账户内容。
  - 由业务参谋和建设负责人共同维护，方法一变就更新并记新提交号。
- 运行时里的「产品档案」对象，等第 2 步和业务问题记录一起设计。

B：在数据里加方法版本列（改表，**架构级**），或现在就把档案放进运行时。

---

## 六、已知限制与待核实

用于档案的「已知限制」，也是第 2 步业务参谋调查的起点。**都是代码阅读所得，除标「实测」的以外都没有用数据核实。按业务优先的规矩，写进给太太的说明之前要先实测。**

### 1. 缺数据（代码注释所记，2026-09-30 DEV 实测，本轮未重测）

位置：`FE/pages/research/stocks/stockScreenStages.ts:1-27`。
- 质量 7 条（毛利率、FCF、ROE、P/E 等）整段没有全池数据；
- 「在活跃主题里」「30 天无事件」；
- 期权的 OI、价差、周期权；
- S&P 500 成分。

所以 5 个预设里有 3 个不提供。

### 2. 永远为假的信号（代码阅读）

| 现象 | 依据 |
|---|---|
| `short_pct_float` 为空，情绪里两个信号恒为不通过 | `stg_short_interest.sql` 的头注释：FINRA 浮动股接口 404 |
| `rs_gt_spy` 可能恒为不通过 | 它从只含普通股的日线里找 SPY（`mart_sepa_tier_momentum.sql:84-90`、`dim_universe.sql:13`）。**未核实** |
| 扩展基本面 25 条里，4 条利润率恒为不通过；`intangibles_lt_30pct` 实际测的是固定资产占比 | `mart_sepa_fundamental_ext.sql:80-157`。这 25 条不进综合分 |

### 3. 方法上的不一致（代码阅读）

- 技术面评估把每只股票最新的日线和最新的 CRS 各取各的，不核对是不是同一天（`mart_sepa_technical_eval.sql`）。**未核实**。
- API 文档列了 STAGE_2C、STAGE_3、EXTENDED，dbt 从不产出（`RS/api/research_engines.py:685-686`）。
- 仓库里还有一份 Python 版 SEPA（`RS/sepa_fusion.py`），规则不同，只在测试里用。

### 4. 使用上的缺口

- 历史日期、导出、已存 screen 的改和删、版本树、页面头的数据日期，都没有（第一节第 3 条）。
- 页面「Option universe」提示写 691 只，实测期权股票池是 751。两个数字的口径也不同（「有 Premium 分」与 `research.option_universe`）。
- `FE/pages/research/discover/ScanPage.tsx:402` 还写着「nothing saves a screen yet」，已过时。

### 5. 待确认

- 太太现在有没有自己的 Research 用户（S2）。
- 她平时怎么用 Stock screen、多久用一次：**没有使用记录可读**，要问她或 Owner。
- `research.saved_screen` 现在有几行、是谁存的：读要令牌，本轮没读。
- Console 能不能只给她开对话（S4-B）。

---

## 七、这份方案之后

- Owner 回「S1 A、S2 A……」（或只回有异议的几条）。
- 统筹线程把定下的内容写进 `PROFILE-screening.md`，作为 Screening 档案第 1 版，引用本文和上面的提交号。
- 第 3 轮 3.2 从一条真实问题开始，走「提议或反馈 → 评估 → 接单 → 交付 → 太太试用 → 记录结果」。
  - 第一条问题由业务参谋从第六节和太太的反馈里选；
  - 不在本方案里预选，也不自动派工。
