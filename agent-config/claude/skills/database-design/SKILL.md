---
name: database-design
description: >-
  PostgreSQL 设计标准 — 表命名、主键/外键列名、strategy_* 与 gate_safety_* 边界表、
  jsonb vs 子表、dim 枚举、环境隔离。Use when adding or changing any PostgreSQL table,
  column, DDL, or migration in bifrost-trade-core / api / worker / research.
parity-id: database-design-v4
---

# Database Design Standards (数据库设计标准)

When adding or changing **PostgreSQL** tables in any `bifrost-trade-*` repo, follow the standards below. The **authoritative schema reference** is **`bifrost-trade-core/docs/DATABASE.md`**; Golden Source 侧参见 `bifrost-trade-core/docs/BROKERAGE_GOLDEN_SOURCE.md` 与 `bifrost-trade-infra/docs/GOLDEN_SOURCE_RETENTION.md`。

适用 repo：`bifrost-trade-core`（DDL）、`bifrost-trade-api`（reader）、`bifrost-trade-worker`（data task 写入）。

## 1. Table Naming

- **Strategy-related tables** (option structure, opportunity, allocation): use prefix **`strategy_`**.
  - `strategy_structure`, `strategy_opportunity`, `strategy_allocation`.
- **Safety-boundary tables** (gates): use prefix **`gate_safety_`**.
  - `gate_safety_strategy` (metadata + six dims + `params_json`). **遗留名**：它的意思是 **gate set**（一组限额参数；
    API `/gate-sets`、类 `GateSet*`、界面「Gate」）。表名不改（命名决策包 2026-10-03 D6-A：改表要动 daemon 启动读门禁的
    路径），新代码与文档一律叫 gate set；FK 列名照表名（`gate_safety_strategy_id`）。
  - Retired (Wave 9): `gate_safety_strategy_earnings_dates` (folded into `params_json.strategy.earnings.dates`).
  - Retired (merged into `gate_safety_strategy` in core `0.8.1`): `gate_safety_state`, `gate_safety_intent`, `gate_safety_guard`.
- **Trade entity tables** (naming R3, core 0.45.0): **`trade`**（PK `trade_id`；原 `strategy_instance`）、
  成交归属 **`trade_execution`**（`trade_id`、拆分数量 `split_quantity`；原 `strategy_instance_execution` /
  `allocated_quantity`）、**`trade_review`**（`trade_id`、`tags_added_json` / `tags_dropped_json`）。Trade 不是规则，所以
  不带 `strategy_` 前缀（决策包 D1-A / D6）；`strategy_*` 只放规则链（template / structure / opportunity / allocation / plan）。
  `allocation` 只指资金规则（`strategy_allocation`）；一笔成交按数量分给几个 Trade 叫 **fill split**（`split_quantity`、
  视图 `brokerage.trade_fill_splits`，D7-A）。旧名 `strategy_instance` / `strategy_instance_execution` /
  `brokerage.instance_allocations` 在 R3 → R4 之间只作为兼容视图存在一版：不得在旧名下新建对象或写新代码。
- **Plugin job queues** (Golden Source): `ops_jobs.job_ingest` (Market Data Plugin); Trade `public.job_*` Celery tables retired (0.10.6).
- **User-preference tables**: use prefix **`preference_`** (e.g. `preference_market_streams_symbol_order` for Market Streams symbol order per category).
- Other per-env tables keep existing names (`settings`, `watchlist`, `trade_review`). Daemon IPC (heartbeat / run_status / control) is **not** in PostgreSQL — it is per-env Redis (`bifrost_core.persistence.redis_daemon_state`, core 0.8.0); do not recreate `daemon_*` / `status_*` tables.

## 2. Primary Key Column Name

- **Multi-row tables**：主键列名必须使用 **`<table_name>_id`**（如 `strategy_structure` → `strategy_structure_id`；`gate_safety_strategy` → `gate_safety_strategy_id`）。不得使用通用列名 `id`。
- **Single-row tables（单行表）**：允许使用 **`id`** 作为主键列名，且通常取固定值（如 1）。单行表仍需主键以支持 `UPDATE WHERE …` 与 `INSERT … ON CONFLICT (id) DO UPDATE`；列名 `id` 作为项目约定写入本规则。Trade 库里唯一的单行表是 `settings`（`id = 1`）。

## 3. Foreign Key Column Names

- Name FK columns to match the referenced table's PK column name (e.g. `strategy_structure_id` in `strategy_opportunity` references `strategy_structure.strategy_structure_id`).
- For gate_safety, use **`gate_safety_strategy_id`** (not `boundary_set_id`) when referencing `gate_safety_strategy`. Earnings dates live in `params_json.strategy.earnings.dates` (Wave 9).

## 4. Safety-Boundary Tables: Metadata + `params_json`

- **`gate_safety_strategy`** stores metadata scalars (name, version, six `dim_*`, `is_active`) plus **`params_json jsonb`** for nested strategy/state/intent/guard parameters.
- **Schema validation** is enforced in Python (`bifrost_core.monitor.schemas.gate_params.GateParams`), not in PostgreSQL CHECK constraints.
- Earnings blacklist dates are stored in `params_json.strategy.earnings.dates` (no child table).

## 5. Strategy Tables: jsonb for Small 1:N + Catalog Dims

- **`strategy_template`**: `legs_json`, `params_json`, `characteristics_json`. Retired child tables: `strategy_template_leg`, `strategy_template_param`, `strategy_template_characteristic`.
- **`strategy_structure`**: `legs_json`, `meta_json`. Retired: `strategy_structure_leg`, `strategy_structure_meta`.
- **`strategy_opportunity`**: `symbols_json`, `entry_conditions_json`. Retired: `strategy_opportunity_symbol`, `strategy_opportunity_entry_condition`.
- **`strategy_allocation`**: keeps **`strategy_allocation_opportunity`** junction (true N:M). Limits stay scalar (`max_positions`, `max_bp_pct`).
- **Dimension enums**: six PostgreSQL enum types (`dim_direction_t`, …) replace `strategy_dim`; UI catalog is read-only in `strategy_dim_catalog.py`.
- Prefer jsonb when a parent row has **≤ few dozen** child rows; use junction tables for real N:M (allocation ↔ opportunity).

## 6. Where to Define and Update Schemas

- **All** new or changed tables and columns must be documented in **`bifrost-trade-core/docs/DATABASE.md`**（该文件已存在，是唯一权威）。末尾的 public 列附录按 DEV 实库生成，改表后同步更新；`raw_broker.*` 的列写进 `BROKERAGE_GOLDEN_SOURCE.md`。
- After changing the design, add an entry to the change log section.

## 7. Exemption: `raw_broker.*` is vendor-shaped

`bifrost_golden_source.raw_broker.*`（per-env 经 FDW 看到的是 `brokerage.*`）是 IB / Flex 形状的落地层，Rev .111 plan C
决定不改名。§2 / §3 的命名规则**不适用于它**；新增列沿用该表现有风格即可，但新建的 per-env 表仍须守 §1–§3。
豁免范围（列定义见 `bifrost-trade-core/docs/BROKERAGE_GOLDEN_SOURCE.md`）：

- 通用 `id` 主键的多行表：`open_orders.id`（旧 `daemon_open_orders`）、`settings_flex.id`（旧 `settings_ib_flex`）
- 沿用旧表名的键：`transactions.account_transactions_id`；视图 `executions*` 的 `account_executions_id`（per-env 桥表也按它关联）；
  `executions_raw_*.legacy_account_executions_id`（拆表前 `account_executions` 的 id，现写 NULL、无读者）
- 指向 per-env 表却无 FK 的 `executions_raw_*.strategy_opportunity_id` / `strategy_instance_id`（跨库，三环境共用同一行；
  per-env 的表现名 `strategy_opportunity` / `trade`。TD-09 起冻结，不读不写，删除另议 D10′）
- IB 字段名：`commissions.yield_` / `yield_redemption_date`（IB `CommissionReport`，`yield` 是 Python 关键字）

**per-env 环境视图不是 vendor 形状**（naming R3，core 0.45.0）：`brokerage.executions` / `executions_final` /
`executions_fly` / `executions_tws` 把 IB 的 `trade_id` / `related_trade_id` 改叫 **`ib_trade_id` / `ib_related_trade_id`**，
`trade_id` 专指本环境的 Trade（TD-13：一个名字只有一个意思），`strategy_instance_id`（= `trade_id`）兼容列只留一版（R4 删）。
Golden Source 的 `raw_broker.executions*` 视图与原表保持 vendor 名。列对照见 `BROKERAGE_GOLDEN_SOURCE.md`。

**旧名对照**（迁移前 per-env `public` 名 → `raw_broker` / `brokerage` 名）：

| 旧 public 名 | 现名 |
|--------------|------|
| `account` | `account` |
| `account_positions` | `positions` |
| `account_execution_commissions` | `commissions` |
| `account_transactions` | `transactions` |
| `daemon_open_orders` | `open_orders` |
| `contract_quote_live` | `contract_quote_live` |
| `settings_ib_flex` | `settings_flex` |
| `executions_raw_{tws,flex,journal}` | 同名 |
| 视图 `account_executions` / `_final` / `_fly` | 视图 `executions` / `executions_final` / `executions_fly` |

权威映射：`bifrost_core.persistence.postgres.brokerage_tables.LEGACY_TO_BROKERAGE`。

**`public` 里的已知偏差（未豁免，改到这些表时一并修正，改名属架构级变更、先问 Owner）**：
`preference_position_categories.id`（多行表用 `id`）；引用它的 `preference_position_category_tags.category_id` 与
`watchlist.category_id`（FK 名不等于 PK 名，且是 int4 引用 bigint）。带角色前缀的 FK 名（`default_gate_safety_strategy_id`、
`settings.active_*_id`、`parent_strategy_plan_id`、`option_` / `stock_account_executions_id`）以被引用 PK 名结尾，属现行写法。

## 8. Dev/Prod Database Isolation

- Trade (OLTP) 三环境隔离：`bifrost_dev` / `bifrost_stg` / `bifrost_prod`（CloudNativePG @ `data` NS，spine **D2-prime**）
- Research (OLAP) 单实例：`bifrost_golden_source`（无环境隔离）。Research **禁止**写 Trade DB（spine **D13**）
- DDL 变更必须在三个 Trade 环境同步执行。
