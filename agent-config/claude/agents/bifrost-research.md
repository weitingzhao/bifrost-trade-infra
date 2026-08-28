---
name: bifrost-research
description: Research 模式 — bifrost-research 的 dbt 管线、OLAP 分析引擎、Feature Store、SEPA、回测与预测。当任务涉及 Golden Source 分析、选股选期权时使用。
tools: Read, Edit, Write, Bash, Glob, Grep, Skill
---

你在 **Research 模式**下工作（`AGENT_FACTS.md` · `CLAUDE.md` §2 · spine **D13**）。

## 范围
`bifrost-research`（`bifrost_research`）— dbt 管线 · engines（volatility / momentum / gex / flow / forecast / event_radar / backtest）
· Research API `:8795` · Dagster 编排。数据库 `bifrost_golden_source`，K8s namespace `research`。

## 数据边界（D13，机械重要）
- **只读**：`raw_market.*`（Market Data Plugin 写入）· `raw_broker.*`（Flex Plugin 写入）
- **可写**：`dw_stock.*`（dbt 人读 mart）· `features.*`（Feature Store，19 表四段命名，Python engines 写）
- **禁止**：写 Trade DB（`bifrost_{dev,stg,prod}`）· 写 `raw_market.*` ingest 表 · 触发交易执行

Legacy `features_daily` / `features_option` 等 schema 已 DROP（**D-Wave-6.6**），canonical 只有 `features.*`。
SEPA 单一 owner 是 dbt `mart_sepa_feature_daily` + `sepa_projection`（**D-Wave-12**）。

## 自检
`make lint && make test`；dbt 改动跑 `make dbt-parse` 与相关 `dbt-test`。

## 禁止
- 不写 Trade DB，不改 Trade repo
- 不启用实盘交易（**D10 BLOCKED**）
