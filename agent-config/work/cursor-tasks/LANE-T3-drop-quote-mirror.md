# LANE-T3 — 删掉没人读的报价镜像与期权兜底（TD-240，worker · api · core · frontend）

先读 `cursor-tasks/README.md`（第 2 轮规则：只推分支，不推 main，不发版、不写库、不做 DDL）。报告写到 `cursor-tasks/reports/LANE-T3.md`。
分支：`cursor/t3-worker`、`cursor/t3-api`、`cursor/t3-core`、`cursor/t3-frontend`（各从 `origin/main` 新开）。

## 背景（Owner 10-08 定：按 B 收尾，表先不删）

LANE-T2 给报价镜像加了开关 `daemon.quote_mirror`（默认关，已上 PROD）。之后核实：

- 镜像只写**持仓股票（STK）**行：`bifrost-trade-worker/src/bifrost_worker/daemon/app/contract_quote_live.py` 的 `sync_contract_quote_live_from_redis`（约 :139–204）。
- 全系统唯一读 `contract_quote_live` 的是 `GET /quotes` 的**期权（OPT）兜底**：`bifrost-trade-api/src/bifrost_api/market/routers/quotes.py:135-141` → core `reader.get_contract_quotes`。它只查期权键，从不读 STK 行；页面的股票报价直接读 Redis（`get_ingester_tick`）。
- 写期权行的 `on_ticker_for_contract_key`（同文件 :42）没有调用方；表里的期权行停在 2026-03-28，读侧有 `fresh_quote_sql` 过滤，所以兜底永远返回空。
- 结论：写的没人读，读的没人写。两头都删。

## 要做

1. **worker**（`cursor/t3-worker`）：删 `daemon/app/quote_mirror.py` 与 `daemon.quote_mirror` 开关（`gs_trading.py` 两处）、`control_heartbeat.py` 里两处 `observe_quote_mirror` 调用；删 `contract_quote_live.py` 里 `on_ticker_for_contract_key`、`get_position_stk_instruments`、`refresh_position_prices`、`sync_contract_quote_live_from_redis` 及 app 上对应的方法绑定；删 `tests/test_quote_mirror_flag.py`。
   - **不动**：`init/refresh/release_ticker_subscriptions` 三个控制命令的处理（它们是控制命令流的一部分，另议）；`mock_hedging`、任何对冲 / 下单代码。
   - 碰到 preflight（D10）拦截就停下写进报告，不要绕过。
2. **api**（`cursor/t3-api`）：`quotes.py` 去掉 `contract_quote_live` 兜底——期权只读 `ib:option:cache:*`，缺的就缺，响应里照实标出缺哪些（看现有字段怎么表达「没有报价」，沿用，不新增字段）；改 `tests/test_market_quotes_opt_cache.py` 对应用例。
3. **core**（`cursor/t3-core`）：删 `monitor/reader/common.py:179` 的 `get_contract_quotes`、`monitor/reader/market.py:145` 的 `get_contract_quotes_conn`、`postgres_sink.py` 的 `write_contract_quote_live`（:215）与 `get_contract_quotes`（:672）、`status_sink.py:59` 的接口方法。**表名常量与 DDL 保留**（表不删）。这是公开接口删除：bump patch（看当时 main 的版本往上加），报告里列出下游（api、worker）以及它们随同一次 Trade 发布克隆 core，不需要抬下限。
4. **frontend**（`cursor/t3-frontend`）：`src/pages/market/live/WatchingStocksPane.tsx:179,183` 两处提示文字还写着 `contract_quote_live`，改成实际来源（期权报价来自 IB Gateway 的期权缓存）。
5. **防线**：core 或 worker 加一条测试——在 `src/` 里搜 `write_contract_quote_live` / `get_contract_quotes` 无命中（排除 DDL 与表名常量），命中即失败。报告写测试名。
6. **门禁**：各仓库 `make lint && make test`；frontend `npx tsc -b && npm run lint && npx vitest run && npm run build`。退出码分开记录。worker / api 的测试要指向 `cursor/t3-core` 的 core（`PYTHONPATH=<core worktree>/src`），共享 checkout 的 core 是旧的。

## 验收（Claude Code 会照跑）

`git grep -nE "write_contract_quote_live|get_contract_quotes|quote_mirror" origin/main -- src` 在 worker / api / core 三个仓库都无输出（合并后）；PROD 发布后 `GET /quotes` 带一个期权合约键仍返回 200。

## 不做

不删表、不写 DDL、不发版、不推 main、不动控制命令流与 D10 相关代码。
