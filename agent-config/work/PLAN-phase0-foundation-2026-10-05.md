# 阶段 0 · 地基 — 可分派工作项（2026-10-05）

> 依据：`REVIEW-architecture-discussion-round1-2026-10-05.md`（Owner 10-05 采纳方向）。
> 每一项 = 一个线程、一条分支、一个 repo 为主。「风险道」沿用第一轮的定义：
> - **快道**：只读、可再生、加字段或加表、可回滚；
> - **慢道**：GS 或 PROD 的 DDL、删数据、写 raw_broker、跨载荷契约。
>
> 标「需要 Owner 批」的项，实现线程先列计划，等你明确同意后才执行。D10 全部不涉及。

---

## 先对齐：回测深挖线程已经做完的部分

「[Trade System·探索] 回测深挖与 PineTS 评估」线程已经完成以下工作：

- research **0.169.0**：修复 B1–B5、B8–B10，新增 9 个测试。
- research **0.170.0**：逐日期权持仓模拟器 MVP。四种卖方结构；止盈、止损、DTE 平仓、到期结算；**vwap 加分档滑点（价差模型已有初版）**；bootstrap 置信区间。
- 两者都在草稿 PR [weitingzhao/bifrost-research#1](https://github.com/weitingzhao/bifrost-research/pull/1) 与 [weitingzhao/bifrost-trade-frontend#1](https://github.com/weitingzhao/bifrost-trade-frontend/pull/1)，分支 `claude/backtest-deep-dive-la74ak`。
- 它需要的 GS DDL（`backtest_run` 加两列，新增 `backtest_trade` 与 `backtest_equity` 两张表）你 10-05 已批准，**尚未落地**。

所以阶段 0 里的「修 B1–B7」与「价差模型」大部分已经做完，下面只列剩余部分。

**关于 PineTS，需要更正我上一轮的说法**：那个线程在 Node 里实际装了 0.11.0 并跑通了测试。结论是现在不引入，理由如下：

- 它没有任何期权语义；
- 多周期在自定义数据源下会报错；
- 它是 AGPL：打进前端 bundle 就等于分发，会把 trade-frontend 卷进 AGPL；
- 研究栈里现成的 Python 就能算这些指标。

它唯一合理的用法，是你手上有离不开的 TradingView Pine 脚本：那时做一个隔离的 Node sidecar，把脚本输出当作一个新 lens。我同意这个结论。上一轮我把 PineTS 说成「信号层」，前提是你有现成的 Pine 脚本；这件事需要你确认（见文末问题 1）。

---

## 工作项

| # | 工作项 | 主 repo | 风险道 | PROD / GS DDL | 需要 Owner 批 | 依赖 |
|---|--------|---------|--------|---------------|---------------|------|
| **W1** | 收尾并上线回测 0.169/0.170 | bifrost-research（+ trade-frontend） | 慢道（GS DDL） | GS：已批的 3 处变更 | DDL 已批；**发布与执行 ddl-apply 仍需你点头** | — |
| **W2** | B6 / B7 与五套回测收敛 | bifrost-research | 快道（代码）；退役旧表时转慢道 | 收敛本身无；以后删旧表另批 | 收敛方案（哪套保留、哪套退役） | W1 合并后 |
| **W3** | 停止滚动物理删除，改为「先归档再删」 | bifrost-platform-plugin-market-data（+ infra 存储） | **慢道**（删数据行为） | 无 DDL | **是**：归档目标与格式；临时先暂停删除 | — |
| **W4** | 每日持仓快照（含账户 NAV） | bifrost-trade-core（DDL）+ worker 或 api（写入） | **慢道**（Trade 三库 DDL） | **是**：新表进 dev/stg/prod | 建表 09-30 已批；**PROD DDL 清单仍需你确认** | — |
| **W5** | 手工录入数据的定时备份与异地副本 | bifrost-trade-infra | 慢道（Secret 与外部目标） | 无 | **是**：NAS 共享路径与异地目标 | — |

W3、W4、W5 互不依赖，可以和 W1 并行。W2 跟在 W1 后面。

---

### W1 · 回测 0.169/0.170 收尾上线

- **剩余工作**：
  - 草稿 PR 转 ready、过 CI；
  - 前端模拟器页签（PR 里标为「尚未做」）；
  - 发布 research，执行 ddl-apply Job；
  - 跑一次真实 run 核对 `backtest_trade` / `backtest_equity` 落库。
- **验收**：用真实数据复跑那 44 条历史 run 里的期权腿模板，前后差异要能用 B8（出场换约）、B5（铁蝶）等解释。
- **注意**：GS 就是生产库。发布走 `research-release`，并遵守一个版本只由一个会话发布。

### W2 · B6 / B7 与五套回测收敛

- **B6 前视偏差**：财报日现在用的是 `filing_date`，要改成真实发布日（8-K 或 earnings 日历）。
- **B7 幸存者偏差**：退市标的被直接丢掉，要计入；改名后的期权轴已连续，股票轴仍断。
- **收敛（建议，待批）**：
  - 事件回测改为「事件触发入场 + 模拟器管理持仓」；
  - Canonical PnL 降级为「模型价参考」，或由模拟器的真实价格取代；
  - Lens 命中率、候选结算、AI 预测结算保留为「信号评估」类，不再叫回测；
  - 先改名、改口径，旧表等后续再批是否删除。

### W3 · 不可再生数据：先归档再删

实测的现行删除规则（`market-data/scheduler/daily.py` 约 1810–1960 行；`contracts.py:197-211`）：

| 数据集 | 现在保留多久 | 能否重新下载 | 判定 |
|--------|------|------|------|
| `option_snapshot`（当时的 vendor IV / Greeks / OI） | 90 个交易日 | **不能**（只往后积累） | **不可再生，最急** |
| `option_snapshot` 盘中 | 30 天 | 不能 | 不可再生 |
| `option_trades` | 30 天 | 有限 | 视需要而定 |
| `option_daily` | 2 年（按月分区，整月 drop） | vendor 约 2 年，超出就拿不回 | 窗口外不可再生 |
| `short_volume` / SEC filings | 2 年 | 窗口外基本拿不回 | 同上 |
| `stock_daily` | 5 年 | vendor 5 年 | 同上 |
| `option_open_interest` | 未见删除 | — | 保持 |

- **做法**：删除或 drop 分区之前，把将被删除的行导出成 Parquet，写入归档存储，并做校验和登记；导出成功才允许删除。库的体量不变，历史不丢。
- **临时措施（建议今天就做，需你同意）**：先把 `option_snapshot_keep_sessions` 等调大或暂停删除，直到归档上线。只是参数变更，可以回滚。代价是库多占一些磁盘：snapshot 约每天十几万行量级，上线前先实测容量。
- **待你定**：归档目标。可选 NAS 原生共享（推荐），或 data-warehouse MinIO（但 gpu-server 现在 NotReady）。

### W4 · 每日持仓快照

- 方案按 `design/uploads/RECEIPT-portfolio-review-boundary-rev112-2026-09-29.md` §2：
  - 主键 `(snapshot_date, account_id, contract_key)`，按 trade 分摊时每个 trade 一行；
  - 列：qty、mark、underlying close、vendor Δ/Γ/vega/θ/IV；
  - 键名在 Rev .111 改名方案批准前先用 `strategy_instance_id`。
- **另加一行账户级 NAV**：解决 TWR 和 Sharpe 的区间起点是 "not recorded" 的问题。这是 09-30 批准范围之外的**自加项**，需要你确认。
- **只能往后积累，每晚一天上线就永久少一天**，所以排在最前。
- 实现线程先列出 PROD DDL 清单：点名项、自加项、行为变化、回滚方式，等你确认后执行。

### W5 · 手工数据的备份分级

- **范围**：`bifrost_{prod,stg,dev}.public.*`（strategy、review、settings、watchlist 等，约 20 MB），以及 GS 里的 `journal.*`、`research.*`、`ops_feedback.*`、`raw_broker.*`（几 MB 到几十 MB）。
- **做法**：每日一个逻辑 dump CronJob，写到 NAS 原生共享，保留 N 份；再每周一份异地副本；每月一次恢复演练。
- **现状**：CNPG 每日 Barman 备份写到 MinIO，而这个 MinIO 跑在 NAS 的 NFS 上（10-03 出过 InvalidPart）。`~/bifrost-backups` 是本机手工 dump，不定期。
- **待你定**：NAS 共享路径；异地目标（云盘、第二地点 NAS，或加密后放对象存储）。

---

## 需要你回答 / 批准的

1. **PineTS**：你手上有没有离不开的 TradingView Pine 脚本？有，就把它排进阶段 1 作为隔离 sidecar；没有，就按深挖线程的结论不引入。
2. **W3 临时措施**：现在就暂停或放宽 `option_snapshot` 等的滚动删除，直到归档上线？（推荐：是）
3. **W3 / W5 存储目标**：NAS 原生共享的路径，以及异地放在哪里。
4. **W4 自加项**：快照里加账户级 NAV 行？（推荐：是）
5. **W2 收敛方案**：按上面的建议执行？（推荐：是，先改名、改口径，不删表）
6. **分派**：同意后由协调方每项开一个线程、各一条分支。W1 交给回测深挖线程收尾（推荐，它最熟悉），其余各开新线程。

---

## Owner 答复（2026-10-05 19:04 UTC）与据此的定稿

| # | 答复 | 定稿 |
|---|------|------|
| 1 | 在 TradingView 上确实有常用的 Pine 脚本，用来分析股票、回测策略胜率；布林带、MACD 这类衍生指标是必需的 | 新增 **W6 · Pine 脚本 sidecar**（阶段 1，W1 合并后开工）。标准指标（布林带、MACD、RSI 等）在 Research 的 Python 里直接算并入 lens，不需要 PineTS；**你自己的 Pine 脚本**由隔离的 PineTS Node 服务运行，部署在 research ns，只通过 HTTP 交互（AGPL 不进前端 bundle）。服务只读 `stock_daily`，写 `features.stock_signal_pine_daily`；`strategy.*` 在标的上的胜率作为参考，期权层面的胜率交给模拟器。需要你从 TradingView 导出脚本源码（W6 线程会来要）；新表、新运行时由 W6 线程列计划，你确认后再做 |
| 2 | 按推荐 | W3 先暂停或放宽 `option_snapshot` 等的滚动删除（只改参数，可以回滚） |
| 3 | NAS 有 k3s-hot、k3s-cold（热备份、冷备份），以及 agent-trade、agent-ops（终端服务记录） | 见下方「存储放置」 |
| 4 | 按推荐 | W4 快照加账户级 NAV 行 |
| 5 | 是 | W2 先改名、改口径，不删表 |
| 6 | 是 | W1 交回测深挖线程；W2–W6 各开新线程 |

### 存储放置（实测：集群已有 StorageClass `nfs-hot` → `/volume1/k3s-hot`、`nfs-cold` → `/volume1/k3s-cold`；PG 备份所用的 MinIO 的 50Gi PVC 就在 nfs-hot 上）

| 数据 | 放哪 | 理由 |
|------|------|------|
| W3 归档：将被滚动删除的不可再生行情（Parquet，只写一次，很少读取） | **k3s-cold**（`nfs-cold` PVC） | 典型的冷数据：长期保留、按日期目录、写后不改 |
| W5 每日逻辑 dump（手工录入数据） | **k3s-hot** 保留最近 14 份；每周一份复制到 **k3s-cold** 长期保留 | 热：最近的副本恢复快；冷：用来回溯 |
| agent-trade / agent-ops | **不放数据** | 它们是 Agent 与终端服务的记录，混放会让保留与清理策略互相干扰 |

**仍未解决**：k3s-hot、k3s-cold 和现有 PG 备份在同一台 NAS 上。NAS 损坏、失窃或火灾会一次全丢，所以「手工数据 RPO≈0」还差一份异地副本。不阻塞 W3、W5 开工，等 W5 上线后再定。
