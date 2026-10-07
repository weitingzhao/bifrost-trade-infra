# 台账 · Pine × 回测：向 TradingView 取长补短

> 起于 2026-10-06 · 持续更新 · 只给 Owner 与 Agent 用，用于评估和跟踪差距，不对外。
> 目标（Owner 2026-10-06）：**不是做一个 TradingView**，而是借鉴它在**画图、策略、回测**上的长处，变成对期权交易**有实际业务价值**的能力。和 TradingView 拼广度既不现实，也没有必要。
> 判断一条值不值得做，只问一个问题：**它能不能让一笔期权交易的决定更好（选标、择时、选结构、放行权价、管理、复盘）**，并且结论能被真实期权价和前瞻样本验证。

**状态**：✅ 已有 · 🟡 部分 · ⬜ 没有，计划做 · ⏸ 暂停（已有结论，等新的前提才重开）· ➖ 有意不做（理由见 §6）
**价值**：高 / 中 / 低（对期权交易决定的价值，不是对「像不像 TradingView」）
**更新规则**：
- 线程做完就改对应行的状态和证据（版本或提交），并在 §7 追加一行。
- 状态必须有实测证据，不写推测。
- 每月或每完成一个批次，重评一次 §0 的分数。

---

## 0. 总览（2026-10-06 晚重评，依据当天 Pine 五轮预注册回放 + P1 两轮全 universe 研究）

分数 1–5，按「对期权交易决定的帮助」打分，不按功能多少。括号里是 10-06 上午的重评。

| 支柱 | TradingView | Bifrost | 说明 |
|---|:-:|:-:|---|
| 画图（看懂价格与价位） | 4 | 4（4） | K 线按 K-LINE-SPEC 重做；Pine 价格线与 Design Rev .161 回执都已上 PROD（fe `a9cbd02a` + `198a8ccf`，STG `kk259` · PROD `cdw6r`）。TV 仍胜在画线工具、多周期、对比叠加、盘中 |
| 策略（脚本能表达什么） | 5 | 3（3） | 数值 plot、`strategy()` 交易明细、期权上下文（S6：12 个序列，research 0.195.0 + runner 0.3.0）都已接入，能写 TV 写不了的期权条件。仍缺参数（S4）和多周期（S5，最后一根 bar 会重绘，暂不放开）。**表达力已不是瓶颈**：五轮回放里没有一个信号因为「写不出来」而失败。**但在 UI 上写、试、改、存这条工作流约 1.5 分（10-06 实测，见 S9、S12–S15），这是现在的瓶颈** |
| 回测（真实价格、诚实统计） | 3 | 4（4） | 能在一天内回答「这个想法能不能赚钱、能不能超过基准」：次日入场、快照补链、结算 walk-2、按周聚类 bootstrap、预注册加一次性样本外、与机械基准逐周配对，已跑完五轮、41 个候选。主要短板在数据，不在方法：期权日线约两年，没有 bid/ask（滑点是分档代理，B10），GEX 和偏度不到两个月。缺一份脚本一份报告（B7），影响小 |
| 验证（前瞻样本说话） | 2 | 3（3） | 机械来源的历史先验为正，门槛已改为高、低 IV 各 ≥ 10 条（0.190.0 起，现行 0.195.0）。Pine 来源五轮未过，**按预注册停止**（V2）。账本里只有机械来源在攒前瞻样本 |
| 期权上下文（IV、GEX、dealer 价位） | 1 | 4（4） | Bifrost 独有，已经能喂进 Pine。但作为择时或选标信号，在两年样本里都没有超过「每周机械卖」。对人工判断仍有价值（墙、γ、锥、IV 状态）。GEX 和偏度要再积累历史才能检验 |

**五轮回放的结论（10-06）**——决定接下来做什么，比分数更重要：
1. **41 个候选，没有一个通过样本外、超过机械基准**：
   - 一、二轮：内置脚本择时，加 IV rank 过滤、Pine 出场、按价位放行权价，32 个；
   - 三轮：期权上下文择时（单票），3 个；
   - 四轮：选标，3 个加 1 个对照；
   - 五轮：ETF 挑周，3 个。

   另外 P1 线程的两轮全 universe 研究（反向信号出场、按线放行权价、价位止损、短 DTE）也都不改默认，唯一为正的格子 Supertrend buy → 20Δ 45 天（+8.5/笔）CI 跨 0。
2. **同结构、同成本下，单票卖 put 输给 SPY**：随机单票对同周 SPY 20Δ，样本内 −1.50%，样本外 −6.35%，CI 上界都 < 0。择时再好也补不回这个差距；第三轮 H2「自身为正、配对为负」就是这样输的。
3. **ETF 上挑周的效果会随样本翻转**：「VRP > 0 才卖」样本内 Δ +2.03%，样本外 −1.15%。两年里只有几次波动事件，「避开某种状态」的规则分不清是规律还是运气。
4. **「每周机械卖 put」仍是最好的规则**：SPY 30Δ / SPY·QQQ·IWM 20Δ，1.5 倍滑点下每单位风险约 +1.1%~+1.25%，CI 下界 > 0。五轮里各段的「全部周」数字与它一致。任何新来源要证明的是超过它。
5. **账本的两个结构问题已处理**：
   - 流动性：0.182 起入场最多顺延 3 天，0.187 起机械来源免成交量门槛，回放里 void 约 1%；
   - 门槛：改为各 ≥ 10 条，0.190.0 起计时。

**方向调整**：Pine 从「找建议来源」退回到「研究与看图工具」。
1. **Pine 作为建议来源：停止**（按预注册）。只在以下任一条件满足时重开，每次仍先预注册、留样本外：
   - 期权历史再积累至少一年（约 2027-10）；
   - 拿到真实 bid/ask 成本（订阅问题）；
   - 换新的结构族，例如 put 价差：封顶单票尾部，可能改变「单票输给 SPY」这一条。
2. **账本**：只靠机械来源攒前瞻样本；V3 门槛看板在跑满一个月后再做。
3. **Pine 作为工具，保持现状**：Pine library（含 Option context 面板，fe `f6b11f7e` 已在 main，随下次 Satellite 发布）、K 线 Pine 线、Simulator 的 Pine 选项，留给人工研究。B7（一脚本一报告）、S4、S5 都降为低优先，有具体研究需要再做。
4. **数据**：
   - TD-172（期限结构 2026-07→09 的洞）回填后，TERM_30_60 才能完整用于研究；
   - GEX 和偏度满一年历史后，可作为新的预注册假设重开 S6 的检验（约 2027-08/09）。

Pine 定时机、Bifrost 定结构的分工不变（Owner 10-06），但现阶段 Pine 定的时机没有被证明有用。

---

## 1. 画图（Symbol › Price）

| # | TradingView 的长处 | 对期权交易的价值 | Bifrost 现状 | 状态 | 下一步 |
|---|---|---|---|:-:|---|
| G1 | 清晰的价格轴、图层分明、尺寸稳定 | 高：一眼读出价位和距离 | K-LINE-SPEC 落地：固定 px 窗格、右侧价格牌、三层权重、svg 内无文字（fe `c9527e86`，10-06 推 main，未发 DEV/PROD） | ✅ | 随下次前端发布上线；Owner 看过后标 aligned |
| G2 | 指标叠加（BB、MACD、RSI 等） | 中：与模拟器、Signal Decay 同源，入场判断有据 | BB 在价格区，MACD、RSI 是副图，默认关，数值读 Research | ✅ | — |
| G3 | 策略信号画在 K 线上 | 高：看信号在价格上出现在哪 | 一次标一个信号，ink ▲▼，`?signal=ind:/pine:` 可以分享；菜单带窗口内条数 | ✅ | — |
| G4 | ——（TV 没有） | 高 | 期权专属叠加：call/put 墙、zero γ、max pain、±1σ 锥、E/OpEx、交易轨迹、持股成本 | ✅ 独有 | 保持 |
| G5 | 画线工具（水平线、趋势线、斐波那契） | **中–高，只限水平价位**：计划的行权价、止损位、到价提醒都是水平线；趋势线和斐波那契对期权价值低 | 没有。Shell Spec §10 写明不放画线工具 | ⬜ | 先问 Design / Owner：只做「我的价位」水平线，和 Plan、Rules 关联，不做自由画线 |
| G6 | 多周期切换（日、周、月） | 中：用周线看趋势、日线择时 | 超过 130 个 session 自动聚成周 K，不能手动选周期 | 🟡 | 低优先：给窗口段加一个周期开关 |
| G7 | 对比叠加（SPY、板块） | 中：相对强弱影响选标和行权价距离 | 没有 | ⬜ | 排在 P2 之后，可以复用 SPY 日线 |
| G8 | Bar Replay（逐根回放） | 中：复盘时不看未来，练择时、核对信号当时的样子 | 没有 | ⬜ | 低优先；可以先做「把窗口锁在某天」的只读回放 |
| G9 | 盘中 K 线、实时 | 低（对日线级期权卖方） | 只有日线，盘中只有快照 | ➖ | 见 §6 |
| G10 | 指标线画在图上（例：Supertrend 线） | 高：放行权价时直接看到脚本认为的失效位 | 选中画在价格上的 Pine 脚本时，K 线价格区画出它的线（Supertrend、Donchian 上下轨、Ichimoku tenkan/kijun、Chandelier 止损线），工具条多一个 `Line` 开关；振荡器脚本不画。数据来自 research 0.183.0 `/pine/check`（按脚本 id + plots，按需现算）。按 Design Rev .161：ink 50%、单条线在翻转处断开、价格轴牌、十字线读数。fe `a9cbd02a` + `198a8ccf`，10-06 已上 STG/DEV/PROD | ✅ | —（Design 已回答 ASK，回执 `design/uploads/RECEIPT-pine-exit-line-rev161-2026-10-06.md`；需要 Research 身份的画线部分待 Owner 在 DEV/PROD 肉眼确认） |
| G11 | 从图上直接下单 | ——（D10） | 有 Plan this，但不在图上 | ➖ | 只做「从图上的价位生成 Plan 草稿」，不下单（见 §6） |

## 2. 策略（Pine 能表达什么）

| # | TradingView 的长处 | 对期权交易的价值 | Bifrost 现状 | 状态 | 下一步 |
|---|---|---|---|:-:|---|
| S1 | `indicator` 的 buy/sell → 信号 | 高 | 8 个内置脚本 + 用户和社区脚本，每晚全 universe 跑，结果落稀疏表（0.173.0） | ✅ | 10-06 04:17–04:25 UTC 按 0.175 口径全量重建（8 个脚本，最早 2022-02-01，含退市名字）。runner 计算时挡住 /health 的问题已由 runner 0.2.0 修复：每算完一个 series 让出事件循环；实测 100 只 × 800 bar 期间 /health 最慢不到 250 ms |
| S2 | 数值 plot（指标值、止损价） | 高：给行权价和管理规则用 | runner 0.2.0 按请求返回指定标题的逐 bar 数值（按每个点的 time 对日期，预热段为 null）；模拟器用它按价位放行权价（B5）；`/pine/check` 可按脚本 id 取线，脚本行带 `plots` 和 `overlay`（0.183.0）；Chandelier 补上了止损线（v2，全量重建，信号逐条不变）。按需计算，不落库 | ✅ | — |
| S3 | `strategy()`：进出场、止盈止损、仓位都由脚本定 | **高**：出场是脚本逻辑的一半 | runner 0.2.0 返回 strategy 的交易明细（进出 session、价格、id、comment、是否开盘成交）；模拟器用它的平仓作为期权出场（B4）。入场仍读 buy/sell plot，仓位大小由 Bifrost 定（这两点是有意的）。10-06 两轮研究：反向信号、紧止损、失效线止损作为卖方出场都没有带来可用的改善（只有 Donchian 失效线 +3.8/笔） | 🟡 | strategy 的 entry 作入场来源：暂不做（出场研究已有结论，入场仍以 buy plot 为准）；Donchian 失效线止损不进账本规则 v3（Owner 10-06：先不放） |
| S4 | inputs 参数即时调整 | 中–高：同一思路不同参数 | 改参数 = 改源码 + 全量重建；PineTS 支持运行时覆盖（约 28ms 一次） | ⬜ | 过渡做法：一个变体一个脚本 id（Owner 10-06）；真要扫描时建变体表（GS DDL，慢道） |
| S5 | 多周期 `request.security` | 中：周线趋势 + 日线入场 | runner 0.3.0 的数据提供器路径能取周线，但**只放同周期**：实测（PineTS 0.11.0）在一次运行的最后一根 K 线上，周线取的是未走完那周的值，历史 K 线取的是上一个完整周，存下的信号第二晚会变（重绘）。`lookahead_on` 会读到未来，同样拒绝 | ⬜ | 修法：provider 在最后一根 bar 不属于完整周期时少给这一期（Research 知道交易日历，可告诉 runner 该周是否已收），加「周中截断与整段跑结果逐根一致」的测试后再放开 |
| S6 | ——（TV 没有期权数据） | **高，差异化**：「Supertrend 翻多且 IV rank > 50」这类期权条件脚本 | **已上线**（Owner 10-06 选方案 A；research 0.195.0 `b4439a2` · pin `a9ca361` · pine-runner 0.3.0 `2a18c6e` · fe `f6b11f7e` 已推 main、随 10-07 那批 Trade 发布上 PROD（Owner 10-06：不单独发，main 上有 TD-137 待跑 DDL 与 core 0.51.0））：脚本用 `request.security("IV_30", timeframe.period, close)` 读 12 个序列（IV_30、IV_RANK、IV_PCTL、VRP_20/60、VRP_PCTL、TERM_30_60、EARN_LAST、EARN_NEXT、SPY、SPY_IV_30、SPY_IV_RANK），逐日 point-in-time，缺日最多顺延 5 个 session，信号从最晚起点 + 100 个 session 后落库；构建、模拟器、`/pine/check` 共用一个读取器，`GET /pine/context` 给 Pine library 页。GEX、偏度历史不到 2 个月，不放。Dagster 0.195.0-dagster 已由 Owner apply（10-06） | ✅ 工具 | **检验结果（第二段，预注册）：三个带期权条件的脚本样本内都没入选，且都显著输给同周机械 SPY 20Δ**（配对差 CI 上界 < 0），见 V2。工具留作研究用；期限结构 2026-07→09 的洞见 TECH_DEBT TD-172 |
| S7 | library / import | 低 | PineTS 不支持 | ➖ | 见 §6 |
| S8 | `request.financial` 等基本面 | 低（Research 已有基本面与 SEPA） | 不支持 | ➖ | 用 Research 的数据，通过 S6 的序列喂入 |
| S9 | 自己的脚本到处可用（在 UI 上写、改、存） | **高**（Owner 10-06：要能通过 UI 添加、编辑策略脚本） | 代码上有：Research › Backtest › Pine library 标签，「＋ New script」「Copy to my scripts」、Check、Save（fe `3000d3e3` / `2b3c90e3`，PROD 包里都在）。**实际用不了**（10-06 实测）：① `research.pine_script` 只有 8 个内置脚本，从未存进过一个用户脚本；② Check / Save 需要 Research 身份，没设时按钮整排置灰、只显示一行「Set user — runs need a Research identity」，页面上没有可点的 Set user（它只在请求失败后的横幅和 Copilot 面板里出现），是死胡同；③ 入口其实有五处——导航 Research › Validate › Backtest 的「Pine library」标签、K 线信号菜单底部「Manage scripts ↗」、Screener Pine 阶段「Pine library ↗」、Signal Decay、Simulator（10-06 初评写成「跳不进编辑」是错的，已更正）——但导航里没有叫 Pine 的项，不好找 | 🟡 | 第一批（Owner 10-06 开工）：W1 页面上直接设身份 · W2 导航里能直接找到 Pine（加导航项涉及 Shell 设计，待 Owner 定） · W3 runner 超时（见 S10）· W4 在 PROD 真存一个脚本，走完「保存 → 每晚批 → K 线 / Screener 看到信号」验收。之后的工作台能力见 S12–S15 |
| S10 | ——（安全） | 必要 | pine-runner 0.1.1：Node 权限模型 + NetworkPolicy，信号按每个点自带的时间对日期 | ✅ | **超时（W3，Owner 选 A）**：实测死循环由 PineTS 自己拦截，但合法的重脚本（600 根 × 900 × 900）会占住单线程几分钟。runner 0.4.0：脚本在 worker 线程里跑，单个标的 10 秒截止，超时就终止并重建 worker，同请求剩余标的跳过，`/health` 不受影响；镜像加 `--allow-worker`（worker 不多任何权限）。**已上线**：research `9095f44` · 镜像 `bifrost-research-pine:0.4.0`（构建 `kkgzq`）· pin `feb9b23`；10-06 23:4x UTC 集群实测：重脚本 10.0 秒被停、同请求下一个标的跳过、期间 `/health` 最慢 11 ms、之后 Supertrend 0.12 秒结果不变。残余：一次性超大内存分配会让 V8 直接结束进程，由 Kubernetes 重启（与之前相同） |
| S11 | 脚本版本与历史 | 中：改版前后的表现要能比 | version 加 1 触发全量重建，旧版本的信号被覆盖，不保留 | 🟡 | 和 S4 的变体表一起设计 |
| S12 | 编辑器（语法高亮、报错定位到行） | 中–高：写和改的效率 | **后端已上线、前端在 main**（Owner 10-06 选 CodeMirror 6）：Pine 高亮、行号、撤销、查找、括号配对；runner 0.5.0 先做基础检查（括号/引号配对、行尾悬空运算符、块缩进、常用 ta.* 参数个数——这些 PineTS 都会悄悄跑过），保存 / Check / 试跑被拒时按行标红并可点击跳转；PineTS 运行时错误能定位的也带行号。CodeMirror 只随 Pine library 按需加载（gzip 112 KB）。research `1c3b1f3`（runner 0.5.0，pin `8c1b596`，线上 /lint 实测抓到参数个数错、内置脚本零误报）· fe `dfb7858e`（main） | 🟡 | 前端已上 PROD（10-07，fe `3990ebfd`，STG `q478s` → PROD `7ws6b`） |
| S13 | 试跑一篮子（不保存就看效果） | 高：写完立刻知道有没有用 | **后端已上线、前端在 main**（Owner 10-06 选同步接口 + 只出信号统计）：`POST /research/pine/try`，篮子＝关注列表 + SPY/QQQ/IWM（resident 层 21 名）、成交额前 50、或自填 ≤50，窗口 1–6 年；预热与上下文预热同每晚构建，统计用 Signal Decay 同一个 `signal_stats.evaluate`。实测：Supertrend 在 resident 篮子两年，与 Signal Decay 用已存信号算的统计逐个周期完全一致（买 150、卖 152 条），0.6 秒。不落库。research `c7b893d`（0.200.0，pin `f3d739e`，验证轮 `1791333723`；线上实测 21 名 1.9 秒、50 名 4.2 秒，统计与 Signal Decay 一致）· fe `dfb7858e`（main） | 🟡 | 前端已上 PROD（10-07，fe `3990ebfd`）；Dagster 0.200.0 已由 Owner apply（10-07 00:48 UTC 滚动完成）；模拟器摘要（方案 B）以后再议 |
| S14 | 立即运行（存了就有信号） | 中：缩短「改 → 看」的周期 | **后端已上线、前端在 main**（Owner 10-06 选 API 后台线程 + 保存即运行）：`POST /research/pine/scripts/{id}/run`（202，进程内一次一个，409 写明谁在跑），`GET …/run` 与 `GET /runs/{job}` 查进度；保存启用中的新脚本、改过的脚本或重新启用时自动开跑。构建按脚本加会话级咨询锁 `pine-build:<id>`：每晚批等锁，立即运行遇锁就「skipped」，两边不会同时写一个脚本。集群实测（只读干跑，713 名）：Supertrend 全量 41 秒、进程峰值 +165 MB；读两个期权上下文序列的脚本 67 秒、峰值不更高；API 容器上限 512 Mi、平时约 112 MB。任务只在内存（API 单副本），重启即忘。前端：编辑区「Run now」+ 状态行，每 2 秒轮询，跑完刷新库表、报告与 K 线。research `4bf586d`（0.201.0，pin `2c5c501`，验证轮 `1791336320`；线上实测：持锁时 skipped，supertrend recent 重写 10.6 秒、232 行、pod 峰值 205 MB）· fe `00b01896` `5b4a359d`（main） | 🟡 | 前端已上 PROD（10-07，fe `3990ebfd`）；Dagster 0.201.0 已由 Owner apply（10-07 01:34 UTC 滚动完成）；带身份的 POST 接口待 W4 时在 UI 上走一遍 |
| S15 | 检验在 UI 里做（预注册、样本内 / 外、对机械基准） | 中：别人的想法也能被同样严格地筛 | 五轮回放都是 `/stocks/replay-pine-2026-10-06/` 下的离线脚本，UI 里做不了 | ⬜ | B7 已在分支；下一步再考虑把回放工具产品化 |

## 3. 回测（真实价格、诚实统计）

| # | TradingView 的长处 | 对期权交易的价值 | Bifrost 现状 | 状态 | 下一步 |
|---|---|---|---|:-:|---|
| B1 | 订单在下一根成交，不偷看 | 高 | 信号类事件从次日起算（0.175.0，entry_timing v2） | ✅ | — |
| B2 | ——（TV 不按期权价回测） | **高，独有** | 模拟器按真实期权日线成交 + 分档滑点 + 保证金 + 管理规则；快照补链 + delta 守卫（0.175.0） | ✅ 独有 | 没有 bid/ask（订阅限制），滑点是分档代理，见 B10 |
| B3 | 多空都能回测 | 高：sell 信号要有看空表达 | 卖权结构：short put、put 价差、**call 价差**（0.177.0，与 put 价差镜像、保证金 = 宽度 − 权利金，含对称性测试）、strangle、condor。回放里 sell → 20Δ call 价差两年 −6%/单位风险（各 IV 段、各年都亏），账本已停发 | 🟡 | 看空表达要换形式再试（如更远的 delta、借方结构、或只在特定 IV 状态），买权和借方价差看 P1 之后的需要 |
| B4 | 脚本决定出场 | 原判 高 → **实测 低**（对 45 DTE 卖方） | 工具已具备：`pine_exit`（auto / strategy / reverse_plot）在 Pine 的出场已知后开盘的第一个 session 执行，和权利金规则谁先到按谁，`exit_reason=pine_exit`，summary 带只用权利金规则的配对差；Simulator 前端可选，结果区「Compared with」面板（fe `a9cbd02a` + `198a8ccf`，三环境已上线）。**实测（10-06 全 universe：713 名 × 2 年 × 8 脚本 × 两侧，60,559 笔）**：16 组里 12 组配对差 ≈ 0；Ichimoku 两侧、Donchian sell 小幅变差（CI 不含 0）；只有 DMI·ADX buy 变好（+16 / 笔 [+0.4, +35]），但这组本身仍是亏的。账本口径回放：Pine 出场只平掉 8%–16% 的仓位，model 均值下降 0.1–0.8 个百分点。原因：持仓约两周，反向信号来不及出现，出现时多在浮亏 | ✅ 工具 · 默认不用 | 默认仍只用权利金规则。原先列的两个假设（①价位止损型 strategy；②更短 DTE）已在 10-06 第二轮测完，见本格末尾，都不改默认。DMI·ADX buy 的「改善」说明它的入场差，应在信号层处理（改进或停用），不靠出场补。报告 `REPORT-pine-p1-exit-study-2026-10-06.md`、`REPORT-pine-buy-iteration-r2-2026-10-06.md`。**10-06 第二轮（价位止损 × DTE，169,869 笔）**：1.5×ATR 紧止损 9 格全负（4 格 CI 不含 0）；信号失效线止损只对 Donchian 有小幅帮助（45 天 +3.8/笔 [+1.2, +6.6]）；14/30 天不改善每笔盈亏（`/stocks/REPORT-pine-p1-stops-dte-2026-10-06.md`）。默认仍是权利金规则 |
| B5 | ——（TV 没有） | 原判 高 → **实测 低–中**（受链覆盖限制） | 工具已具备：`strike_anchor {plot, min_delta, max_delta}`，取入场前一个 session 的 plot 值，put 取锚价及以下、call 取锚价及以上的第一个行权价；delta 只作护栏，超出护栏、锚值缺失、锚价外没有行权价都跳过并计数；Simulator 前端可选（fe `a9cbd02a` + `198a8ccf`，三环境已上线）。**实测（10-06 全 universe）**：按线 − 按 20Δ，Supertrend buy −11.3 / 笔 [−22.2, −1.0]（线放出约 0.16Δ，权利金更少），Donchian buy −7.6 [−15.4, 0.0]，其余分不出差别；「锚价外没有行权价」大量出现（Donchian buy 5,541 次、Supertrend buy 1,067 次），因为链只覆盖 ATM ±约 10 个行权价（B10）。账本口径回放：1.5 倍滑点下与 20Δ 无差别 | ✅ 工具 · 默认不用 | 默认仍按 20Δ。重开的前提是链覆盖改善（B10，牵涉订阅和采集范围）。留一个假设给下一轮预注册：Ichimoku sell 按 kijun 放 +8.2 / 笔（CI 跨 0，1,449 笔），现在还不是结论 |
| B6 | ——（TV 没有基线对照） | 高：信号有没有用，要和不看信号比 | 模拟器没有内建配对基线；Design B3 由前端再跑一次 schedule 来对照 | 🟡 | P1 #5：下沉到后端，直接给差值和 CI |
| B7 | Strategy Tester：一个策略一份报告、交易列表、权益曲线 | 高：一处看完一个脚本 | **简版：后端已上线、前端在 main**（Owner 10-06 选报告页 + 只读摘要接口）：新页 `/research/pine/<id>`（库表每行「Report ↗」）：已存信号（总数、标的数、起止、由哪个版本生成，与源码版本不一致标红）+ 按月信号柱；买卖两侧信号后 edge（Signal Decay 同一方法，`signal-stats` 新增 `detail=true`）；按标的（次数、最后一次、20 日净收益）；最近 50 条信号（冷却期内不计的变淡）；以该脚本入场的模拟运行。新增只读 `GET /research/pine/scripts/{id}/summary`，不加表。全 universe 的 signal-stats 每侧约 10 秒（集群实测）。没有权益曲线：信号本身不是交易，权益曲线在 Simulator 里。research `4bf586d`（线上 summary 0.2 秒、signal-stats detail 每侧 10 秒）· fe `00b01896` `5b4a359d`（main；本机 Vite 接集群 0.201.0 走查过，`5b4a359d` 修了「太新还没有收益的信号被当成冷却期变淡」）。Design 未画，回执已更新 | 🟡 | 前端已上 PROD（10-07，fe `3990ebfd`）；版式交 Design |
| B8 | 参数优化 | 中，**过拟合风险高** | 没有 | ⬜ | P2：只和 walk-forward、样本外检验、多重检验校正一起上 |
| B9 | 组合级回测 | 中 | 没有，每只票各算各的 | ⬜ | P2 之后：共享资金和保证金上限 |
| B10 | 深历史、盘中数据 | 中 | 期权日线约 2 年，股票日线 5 年；option_daily 自 8 月起每个到期日只剩 ATM ±约 10 个行权价（用快照补） | 🟡 | 订阅限制，接受并留座；不追 |
| B11 | Bar Magnifier（盘中撮合） | 低 | 规则按当日价触发、当日价成交（代码里明说偏乐观） | ➖ | 见 §6 |
| B12 | ——（TV 只给原始统计） | **高，Bifrost 领先** | signal-stats v2：扣成本、重叠去重、按 symbol 的 cluster bootstrap 90% CI、排除信号日的基线、退市和改名处理（0.175.0） | ✅ 领先 | Signal Decay 面板按 Design B4 对齐（fe `2b3c90e3`） |

## 4. 验证与前瞻

| # | 内容 | 价值 | 现状 | 状态 | 下一步 |
|---|---|---|---|:-:|---|
| V1 | 建议时点落库、到期自动结算、配对 SPY 基线 | 高 | 建议账本 S0 上线（0.174.0/0.174.1）；计数起点 10-05 v2 批 | ✅ | — |
| V2 | Pine 作为建议来源 | 高（原判「最急」）；**实测：现有脚本不够格** | 0.177.0 上线发出方（Supertrend / Donchian；buy → 20Δ short put，sell → 20Δ call 价差）。两年回放（规则完全同线上，7,007 条）：buy 约 −0.2%~−0.7% / 单位风险，sell 约 −6%；择时对比信号后几天入场 ≈ 0；都输给 SPY 同结构。**0.182.0 起 Pine 来源暂停**（规则版本 2，sell 不再映射）；同名对照 `symbol_paired` 口径已建（PROD CHECK 已放宽），代码处于关闭态。离线迭代两轮共 32 个候选：第一轮 3 个进样本外（supertrend 45DTE IV≥50），全部没过 Holm（p 0.34–0.89）；第二轮（Pine 出场 × 按价位放行权价）样本内无一入选；**第三轮（S6，期权上下文，10-06）**：H1 carry put、H2 IV 回落、H3 财报后安静期三个脚本，样本内（实际入场 2025-03→12）都没入选：stress 均值 +0.2% / +1.3% / +0.7%，与同周机械 SPY 20Δ 的配对差 −1.65% / −1.15% / −1.65%，90% CI 整个在 0 以下；H2 自身显著为正（下界 +0.38%），但赚的是「那几周卖 put 本来就赚」；**第四轮（选标，10-06）**：择时固定为每周机械发出日，只换标的。三条选标规则（安静有溢价 / 溢价厚封尾 / 趋势稳健）样本内都没入选，对照组「随便挑单票」也显著输给同周 SPY 20Δ（样本内 −1.50% [−3.10, −0.06]，样本外 −6.35% [−9.37, −3.48]），过滤规则也不比随机好 → 同结构同成本下单票卖 put 赢不了 SPY；**第五轮（ETF 择时，10-06）**：在 SPY/QQQ/IWM 上按条件挑周卖。G1（VRP_20 > 0）样本内 Δ（卖出周 − 跳过周）+2.03%、入选，样本外反转为 −1.15%（p 0.91），失败；G2 趋势、G3 contango 样本内未入选 | ⏸ | **按预注册，Pine 作为建议来源停止**（五轮 41 个候选，没有一个通过样本外、超过机械基准）。重开前提：再多至少一年期权历史，或真实 bid/ask 成本，或新的结构族（如 put 价差）；每次仍先预注册。报告 `REPORT-pine-etf-timing-2026-10-06.md`、`REPORT-pine-name-selection-2026-10-06.md`、`REPORT-pine-options-context-2026-10-06.md`、`REPORT-pine-name-selection-2026-10-06.md`、报告 `REPORT-pine-options-context-2026-10-06.md`、`REPORT-pine-s4-replay-2026-10-06.md`、`REPORT-pine-buy-iteration-2026-10-06.md`、`REPORT-pine-buy-iteration-r2-2026-10-06.md`；工具与结果 `/stocks/replay-pine-2026-10-06/` |
| V3 | 门槛达标看板 | 中 | 门槛写在设计和配置里，没有界面 | ⬜ | S4 跑满一个月后再做 |
| V4 | 纸面交易、到价提醒下单 | ——（D10） | 只出建议，不下单 | ➖ | 见 §6 |

## 5. Bifrost 独有，要保持的优势

- **用真实期权价表达信号**（B2）：TradingView 结构上做不到。
- **统计诚实**（B12）：成本、去重、CI、基线、退市处理。
- **期权上下文**（G4、S6）：墙、γ、锥、IV、GEX；下一步要喂进 Pine。
- **前瞻账本**（V1、V2）：只有前瞻样本才算数，历史回测只作参考。

## 6. 有意不做（理由）

| 项 | 理由 |
|---|---|
| 盘中 K 线、实时、Bar Magnifier（G9、B11） | 订阅和数据成本；日线级期权卖方的决定不依赖盘中 |
| 下单、纸面交易、到价提醒下单（G11、V4） | D10 交易执行冻结；Bifrost 只出建议并结算 |
| library / import、`request.financial`（S7、S8） | PineTS 不支持；基本面走 Research，通过 S6 的序列喂入 |
| 自由画线（趋势线、斐波那契） | 对期权决定价值低；只考虑和计划关联的水平价位（G5） |
| 全品种、全市场广度 | 不现实，也不必要 |

## 7. 进度记录

| 日期 | 项 | 内容 | 证据 |
|---|---|---|---|
| 2026-10-05 | S1 G3 | Pine 信号上线（脚本库、信号表、五个入口） | research 0.173.0 · fe PR #2/#3 |
| 2026-10-06 | S9 | 用户脚本全站可见；`?signal=` 链接 | fe `3000d3e3` |
| 2026-10-06 | S10 | pine-runner 沙箱、NetworkPolicy、按时间对日期 | pine-runner 0.1.1 · research `450e0d4` / `6a426d5` |
| 2026-10-06 | B1 B2 B12 | 次日入场、快照补链 + delta 守卫、signal-stats v2、构建剔除预热与补 lineage | research 0.175.0 `5c173df` |
| 2026-10-06 | G1 G2 G3 | K 线按 K-LINE-SPEC 重做 | fe `51dad5ce` `c9527e86`（main，未发 DEV/PROD） |
| 2026-10-06 | S1 | 全量重建：行数（前→后）adx 25976→24285 · chandelier 32635→30830 · donchian 70734→66930 · ichimoku 15943→15853 · squeeze 22675→21864 · stoch_rsi 74930→70756 · supertrend 25005→23495 · wavetrend 18604→17943 | 线程 B，0.175.0 镜像一次性 Pod |
| 2026-10-06 | — | 开线程：S4（V2 + B3 call 价差）、P1（S2 + S3 + B4 + B5） | 本台账 |
| 2026-10-06 | S9 B6 B12 | Pine 四个页面按 Design Rev .159 对齐（Stock screen 的 Pine 阶段、Simulator 含前端 schedule 对照、Signal Decay、Pine library） | fe `2b3c90e3`（main，未发 DEV/PROD） |
| 2026-10-06 | B12 | signal-stats v2（重建后，20 日，全部名字，净 10 bps/边）。净收益 edge [90% CI]，CI 下界 > 0 的只有 4 个：wavetrend buy +1.0 [+0.6, +1.3] · supertrend buy +0.5 [+0.3, +0.7] · chandelier buy +0.3 [+0.1, +0.5] · donchian buy +0.3 [+0.1, +0.4]。CI 跨 0：squeeze buy +0.1 · adx buy +0.2 · ichimoku buy +0.0 · stoch_rsi buy −0.1 · supertrend sell −0.1 · chandelier sell −0.2 · adx sell −0.2 · stoch_rsi sell −0.1 · wavetrend sell +0.3 [−0.0, +0.6]。CI 上界 < 0：squeeze sell −0.8 · donchian sell −0.8 · ichimoku sell −1.4 | research 0.175.0 线上接口 · `/stocks/REPORT-pine-p0-honesty-2026-10-06.md` |
| 2026-10-06 | B1 | sepa_hit、iv_percentile_threshold 也改为次日入场；信号类不给 offset 时默认 0，负 offset 拒绝（MCP 路径同样受约束）；entry_timing v3 | research 0.176.0 `c0b2841`（只发 api/mcp）· fe `811bbdb8`（未推送） |
| 2026-10-06 | B1 | SEPA / IV 阈值量纲：SEPA 默认 0.7→70，阈值不在 (1, 100] 拒绝；前端 Event backtest 改发 `threshold`（SEPA 70 / IV 80，0–100），并把信号类 offset 改为默认 0 | research 0.176.1 `6e863b5` · fe `811bbdb8` `8ff918f8`（STG nw6xd · PROD fldtp · DEV，10-06 05:09–05:23 UTC） |
| 2026-10-06 | V2 B3 | 建议账本 S4 上线：模拟器 call 价差；Pine 发出方（Supertrend / Donchian，规则 v1，计数自 10-06 起）；Dagster 边 pine → 账本。首批待 10-06 夜跑核对 | research 0.177.0 `1cc7f28` · pin `3f5fd35` · Dagster 0.177.0-dagster |
| 2026-10-06 | S2 S3 B4 B5 S1 | P1「Pine 定时机，Bifrost 定结构」：runner 返回数值 plot 和 strategy 交易明细，/health 不再被计算挡住；模拟器 Pine 出场（与权利金规则谁先到按谁，带对比）、按 Pine 价位放行权价（带 delta 护栏）。近一年 SPY/QQQ × Supertrend/Donchian 对比：Pine 出场只改变了 41 笔里的 3 笔，3 笔都更差；按 Supertrend 线放行权价与 20Δ 接近。另：发布后发现 Simulator 跑 SPY 一年会把 research-api 打到 OOM（0.174.1 起就是这样，已开后续任务） | research 0.178.0 `191ce92` · pin `d62338e` · pine-runner 0.2.0 · `/stocks/REPORT-pine-p1-exits-strikes-2026-10-06.md` |
| 2026-10-06 | B12 | 指标 signal-stats 改为与 Pine 相同的新口径（次日开盘入场、成本、去重、按方向、聚类 CI、lineage）；方法移到 `engines/signal_stats.py`；Signal Decay 表两类信号同一口径 | research 0.179.0 `9c89798`（05:37 UTC 上线） |
| 2026-10-06 | V2 B3 | 两年回放 S4 规则（2024-11→2026-10，37,721 信号 → 7,007 条）：buy ≈0 且择时无价值，sell −6%；同名对照必须取信号之后（取之前会吃到触发信号的走势，对照 +4%）；结算 27–41% 因次日无成交 void | 一次性只读 Pod 回放 · `/stocks/REPORT-pine-s4-replay-2026-10-06.md` |
| 2026-10-06 | V2 | 0.182.0：Pine 暂停（规则版本 2、去掉 sell）；发出时每腿当日成交 ≥25 张；结算 walk-2 入场最多顺延 3 个交易日；`symbol_paired` 口径（PROD CHECK 已放宽，代码关闭待恢复 Pine） | research 0.182.0 `23fed38` · pin `a4ac63b` · DDL 清单 `/stocks/REQUEST-symbol-paired-ddl-2026-10-06.md` |
| 2026-10-06 | V2 | buy 离线迭代第一轮（预注册在先）：IS 2024-11→2025-12 选出 supertrend 45DTE IV≥50 三个（各 41–49 条），OOS 2026-01→10 全部未过 Holm（p 0.34–0.89）；不加 IV 过滤的 12 个 IS 全负。流动性修复后 void 从 25–41% 降到 ~1% | `/stocks/PREREG-pine-buy-iteration-2026-10-06.md` · `/stocks/REPORT-pine-buy-iteration-2026-10-06.md` |
| 2026-10-06 | V2 B4 B5 | buy 离线迭代第二轮（P1 维度，预注册在先）：8 个候选 IS 无一入选（stress 全负、全输 SPY）；Pine 出场让均值降 0.1–0.8 个百分点，按价位放行权价无改善。两轮共 32 个候选，无一可用 → Pine 来源这条线停在这里 | `/stocks/PREREG-pine-buy-iteration-r2-2026-10-06.md` · `/stocks/REPORT-pine-buy-iteration-r2-2026-10-06.md` |
| 2026-10-06 | G10 S2 B4 B5 | P1 余项：Simulator 前端加 Exit / Short strike 选项和「Pine exit vs premium rules」面板，K 线画 Pine 价格线（fe `a9cbd02a`）；research 0.183.0 `/pine/check` 按脚本 id + plots、脚本行带 plots/overlay；Chandelier 补止损线 v2 并全量重建（30,830 行，信号不变）；Dagster 同步升 0.183.0-dagster | research `cf418a1` `8567e15` · pin `5cb3462` · fe `a9cbd02a` |
| 2026-10-06 | B4 B5 | 全 universe 研究（方案 A）：Pine 反向信号出场对期权卖方基本无用（12/16 组 ≈0，3 组小幅变差，DMI·ADX buy +16/笔 但仍亏）；按 Pine 线放行权价不比 20Δ 好（Supertrend buy −11.3/笔，CI 不含 0）；只用权利金规则时唯一为正的格子是 Supertrend buy → 20Δ short put（+8.5/笔）。默认不改 | `/stocks/REPORT-pine-p1-exit-study-2026-10-06.md` |
| 2026-10-06 | §0 B4 B5 V2 | 台账重评：按 6 份报告重写 §0 分数与结论，B4、B5 改为「工具具备、默认不用」，V2 改为 ⏸ 暂停并写明重开前提；方向从「补 Pine 功能」转向「找更好的信号 + 账本门槛与流动性」 | 本台账（Owner 10-06 要求） |
| 2026-10-06 | V1 V2 S6 | 门槛改为高、低 IV 各 ≥ 10 条（thresholds .3，重新计时；research 分支 `bbd577f`，待推送和发版）；开 S6 线程（期权上下文喂入 Pine，两段式：先能力、后预注册检验，基准是机械来源） | 本台账 |
| 2026-10-06 | V1 | 门槛 thresholds 2026-10-06.3（IV 两段各 ≥ 10 条）上线：research 0.190.0（代码 `4a16906`，pin `b6657ea`），api、mcp、Dagster 都滚到 0.190.0，Pod 内读到 `2026-10-06.3 / 10`；计时从此刻重新开始 | research 0.190.0 |
| 2026-10-06 | S6 S5 | S6 第一段：三侧实测可用序列（GEX、偏度、IV rank 早段不可用，见报告）；Owner 选方案 A；runner 0.3.0 数据提供器 + research 0.191.0 共用读取器 + Pine library 说明面板，8 个内置脚本走两条路径逐条一致；多周期因最后一根 K 线重绘暂不放开（S5）；TD-172 期限结构的洞 | research `b4439a2`（0.195.0）· runner `2a18c6e` · fe `f6b11f7e`· `REPORT-pine-s6-context-series-2026-10-06.md` |
| 2026-10-06 | G10 B4 B5 | Design Rev .161 回执落地：Simulator「From the script」组、「Compared with」分页面板、按卖方好坏着色；K 线 Pine 线 50%、翻转断开、价格牌和读数（fe `198a8ccf`，10-06 已上 STG `kk259`、DEV、PROD `cdw6r`）；回执 `design/uploads/RECEIPT-pine-exit-line-rev161-2026-10-06.md`（3 处文案 app 保留并说明） | fe `198a8ccf` |
| 2026-10-06 | B4 S3 | 第二轮研究：价位止损型 strategy（失效线 / 1.5×ATR）× DTE 45/30/14，713 名、169,869 笔。紧止损一律更差；失效线止损只对 Donchian 有小幅帮助（+3.8/笔）；短 DTE 胜率升、每笔不升。唯一为正的仍是 Supertrend buy + 20Δ + 45 天（+8.5/笔，CI 跨 0） | `/stocks/REPORT-pine-p1-stops-dte-2026-10-06.md` |
| 2026-10-06 | S6 | 发布：research 0.195.0（版本号被并发占到 0.194，连带另一会话的 0.194.0 一起上线，Owner 确认）+ pine-runner 0.3.0；api/mcp/26 个 CronJob/runner 验证通过；Dagster `0.195.0-dagster` 由 Owner apply 后滚动完成（38 个 schedule，定义加载无报错） | research `b4439a2` · pin `a9ca361` · deliver `bifrost-deliver-research-1791314057` · fe `f6b11f7e` · infra `90a57a2`（TD-172） |
| 2026-10-06 | S6 V2 | 第二段（预注册在先）：三个期权条件脚本样本内无一入选，都显著输给同周机械 SPY 20Δ（−1.15%~−1.65% / 单位风险，CI 上界 < 0），不跑样本外；Pine 来源保持暂停，不提议规则 v3 | `/stocks/PREREG-pine-options-context-2026-10-06.md` · `/stocks/REPORT-pine-options-context-2026-10-06.md` |
| 2026-10-06 | S2 S3 B4 B5 G10 | **P1 收尾**：research 0.178.0（runner 0.2.0）/ 0.183.0（Chandelier v2 全量重建）、fe `a9cbd02a` + `198a8ccf`（Design Rev .161）均已上 STG `kk259` · DEV · PROD `cdw6r`。两轮全 universe 研究：Pine 对 45 DTE 卖方的价值在入场；反向信号出场、按线放行权价、紧止损、短 DTE 都不改默认（Donchian 失效线止损 +3.8/笔，Owner 定不进账本 v3）。发布门禁：盘中实时市值漂移列入 `expected.d/always.allow`（infra `a34e779`） | `/stocks/REPORT-pine-p1-exits-strikes-2026-10-06.md`（含收尾一节）· `REPORT-pine-p1-exit-study-2026-10-06.md` · `REPORT-pine-p1-stops-dte-2026-10-06.md` |
| 2026-10-06 | V2 | 第四轮（预注册在先）：固定择时、只换选标。S1–S3 样本内无一入选，对照 C0（随机单票）样本内、样本外都显著输给同周机械 SPY 20Δ（−1.50% / −6.35%，CI 上界 < 0）；结论：现有结构与成本下单票卖 put 赢不了 SPY | `/stocks/PREREG-pine-name-selection-2026-10-06.md` · `/stocks/REPORT-pine-name-selection-2026-10-06.md` |
| 2026-10-06 | V2 | 第五轮（预注册在先，Owner 选方向 A）：SPY/QQQ/IWM 上按 Pine 条件挑周卖。只有 G1（VRP>0）样本内入选（Δ +2.03%），样本外反转（Δ −1.15%，p 0.91）→ 失败；五轮 41 个候选全部未超过机械基准，Pine 来源按预注册停止 | `/stocks/PREREG-pine-etf-timing-2026-10-06.md` · `/stocks/REPORT-pine-etf-timing-2026-10-06.md` |
| 2026-10-06 | §0 | 按五轮回放重评 §0：分数不变（画图 4 · 策略 3 · 回测 4 · 验证 3 · 期权上下文 4），结论改为「41 个候选无一超过机械基准、单票输给 SPY、ETF 挑周随样本翻转」，方向改为 Pine 退回研究与看图工具、建议来源停止并写明重开条件；§8 改为看机械来源前瞻样本与重开条件，下次约 2026-11-06 | 本台账（Owner 10-06 要求） |
| 2026-10-06 | S9 S10 S12–S15 | Owner 指出 UI 上没有写脚本的入口。实测：入口有但走不通（身份死胡同、入口太深、库里 0 个用户脚本）；按工作流打分约 1.5 / 5。S9 ✅→🟡、S10 ✅→🟡（缺超时），新增 S12–S15；第一批 W1–W4 开工 | 本台账 · Owner 10-06 |
| 2026-10-06 | S9 S10 | 第一批：W1 页面上直接 Set user（Pine library、Simulator）fe `c91555e8` 已推 main；W2 独立页面 `/research/pine` + 导航 Research › Validate › Pine library，所有「Manage scripts / Pine library」链接改指向它，Design 回执 `design/uploads/RECEIPT-pine-library-nav-row-2026-10-06.md`（fe `f7e4ee75`，已推 main）；W3 runner 0.4.0 worker + 10 秒截止（已上线，见 S10）；W4 待 10-07 Trade 发布后在 PROD 存第一个脚本验收 | fe `c91555e8` · `f7e4ee75` · research `9095f44` · pin `feb9b23` |
| 2026-10-06 | S12 S13 | 第二批（Owner 选 CodeMirror 6、同步试跑、加基础检查）：runner 0.5.0 基础语法检查 + 报错行号 + `/lint`；research 0.200.0 `POST /pine/try`、保存前检查；前端编辑器 + 出错行标记 + 「Try on a basket」面板；试跑与 Signal Decay 统计逐项一致。均在分支，待批发布 | research `47b71a6` `3dcb2c4` · fe `752a532f` |
| 2026-10-06 | S12 S13 | 第二批发布：runner 0.5.0（pin `8c1b596`）先上，research 0.200.0（pin `f3d739e`）后上，验证轮通过；集群实测 /lint、/run 拒绝带行号、试跑与 Signal Decay 一致；前端 `dfb7858e` 已推 main，随 10-07 Trade 发布 | research `1c3b1f3` `c7b893d` · fe `dfb7858e` |
| 2026-10-06 | S14 B7 | 第三批（Owner 选 API 后台线程、保存即运行、报告页 + 只读摘要接口）：research 0.201.0 立即运行（进程内一次一个、构建按脚本加咨询锁、保存即开跑）+ `GET …/summary` + signal-stats `detail`；前端 Run now、脚本报告页。集群只读干跑实测内存与耗时（见 S14）。均在分支，待批发布 | research `4bf586d` · fe `00b01896` |
| 2026-10-07 | S14 B7 | 第三批发布：research 0.201.0（pin `2c5c501`，验证轮 `1791336320`）上线；线上验证 summary、signal-stats detail、锁与立即运行；前端 `00b01896` + 修正 `5b4a359d` 推 main，随下次 Trade 发布；Dagster 0.201.0 已由 Owner apply | research `4bf586d` `2c5c501` · fe `00b01896` `5b4a359d` |
| 2026-10-07 | S9 S12–S14 B7 | Trade 发布（还债线程执行，Owner 跑 release.sh）：STG `bifrost-deliver-stg-q478s` → PROD `bifrost-deliver-prod-pinned-7ws6b` → DEV，前端 `3990ebfd` 含三批全部 Pine 前端；PROD `:30881` 上 `/research/pine`、`/research/pine/<id>` 与经网关的 summary / run 接口均 200。待 W4：Owner 在 PROD 存第一个脚本 | fe `3990ebfd` |
| 2026-10-07 | S14 | 加锁后第一次夜批：02:30 UTC 定时 run `45915b44` 在 dbt 步失败（pine 在其下游，没跑到）；04:31 UTC 手动重跑 `a5a88fe2` 全部 24 步成功，pine 8 个内置脚本 recent 模式共 3,060 行、errors 0、无 skipped，8 个脚本最后信号都到 10-06 | Dagster `a5a88fe2` |
| 2026-10-07 | V2 | 建议账本首晚核对（as_of 10-06）：02:30 计划夜跑因 dbt generic test 未打包失败（TD-252，0.204.0 已修），04:31 重跑成功；suggestion_ledger：pine paused（rule v2）、结算 walk-2、无 illiquid_leg、无 pine 行、无 symbol_paired 行；结算表仍空（8 条均未出场），walk-2 结算与流动性快照待首批出场 / 下个周首再核；as_of 10-05 baseline/simulator 发了两套（source_version 1/2）待 Owner 看 | `REPORT-research-0188-first-night-2026-10-07.md` |

## 8. 下次重评

- **时间**：约 2026-11-06，届时机械来源在门槛 thresholds 2026-10-06.3（0.190.0 起计时）下跑满一个月。下面任一重开条件提前出现，就提前重评。
- **要看什么**：
  - §0 分数；
  - 机械来源的前瞻样本：baseline 和 simulator 已结算多少条，低 IV、高 IV 两段各离 10 条还差多少，实际结算和历史先验（每单位风险 +1.1%~+1.25%）对不对得上，void 率；
  - Pine 来源的重开条件出现了没有（§0「方向调整」第 1 条）：
    - 期权日线最早日期，即历史是否已比 2024-10 多出一年；
    - bid/ask 订阅状态；
    - 有没有新的结构族（例如 put 价差）提出预注册；
  - 数据：TD-172 回填了没有；GEX、偏度的历史长度；
  - S6 的 Option context 面板（fe `f6b11f7e`）是否已随 Satellite 上 PROD；
  - 8 个内置脚本的 signal-stats v2 只作看图参考，不再作为建议来源的依据。
