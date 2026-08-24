# Golden Source retention matrix

Single reference for **data retention** on `bifrost_golden_source`. Canonical schema names only.

| Schema | Table / object | Partitioning | Retention | Drop / trim owner |
|--------|----------------|--------------|-----------|-------------------|
| `raw_market` | `stock_daily` | Year | **No TTL** — long history | `ops_jobs.ensure_year_partitions` (add only) |
| `raw_market` | `stock_minute` | Month | **TBD** — confirm with Owner | `ops_jobs.ensure_month_partitions` |
| `raw_market` | `stock_snapshot` | None (daily upsert) | **TBD** | — |
| `raw_market` | `stock_movers` | None | **TBD** | — |
| `raw_market` | `option_daily` / `option_minute` | Month | **TBD** | partition maintenance in Plugin DDL |
| `raw_market` | `option_trades` | Day | **~30 days** | `ops_jobs.drop_option_trades_partitions_older_than` (default 30d) |
| `raw_market` | `option_snapshot` / `option_open_interest` | Day / month mix | **TBD** | Plugin partition helpers |
| `raw_market` | `ticker`, `stock_financials`, `corporate_action`, etc. | None | **No TTL** | — |
| `features_daily` | `max_pain_daily`, `atm_iv_daily`, `pcr_daily`, `iv_percentile_daily` | Month | **No TTL** | Research + Plugin partition DDL |
| `ops_jobs` | `job_ingest` | None | **Completed rows: 90d** (recommended Cron; not always automated) | Future: dedicated cleanup CronJob |
| `ops_jobs` | `job_flex_ingest` | None | **Completed rows: 90d** (recommended) | Future: Flex Query cleanup job |
| `ops_jobs` | `ingest_freshness`, `flex_ingest_freshness` | None | **No TTL** — status snapshots | — |
| `ops_jobs` | `data_source_void` | None | **No TTL** — operator ack records | — |
| `raw_broker` | `executions_raw_*`, `transactions`, `account`, `positions` | None | **No TTL** — compliance / audit | — |
| `raw_broker` | `open_orders`, `contract_quote_live` | None | Operational (live state) | — |
| `features_option` / `features_signals` / `features_forecasts` / `features_backtests` | engine output tables | Mostly month / none | **No TTL** (research history) | Research CronJobs write only |
| `dw_stock` | dbt marts (`mart_sepa_*`, etc.) | None | **No TTL** — rebuilt by dbt | dbt run |
| `ops_dbt` | Elementary metadata | None | **TBD** — align with dbt artifact policy | edr / dbt |
| Trade `public.*` | strategy / gate / preference | None | **No TTL** — env-isolated config | per-env DDL |
| **Retired** | `public.ops_audit_log` (Trade) | Was monthly | **Retired Wave 6** | platform-api audit (90d policy on control plane) |

## Compat shims (not retention targets)

| Shim | Canonical | Notes |
|------|-----------|-------|
| `data_ops.ingest_freshness` (view) | `ops_jobs.ingest_freshness` | platform-api probe; remove after probe cutover |
| `flex_ops.*` (views) | `ops_jobs.*` | **DEPRECATED** Wave 6.3 |

## Authority

- Partition functions: `bifrost-platform-plugin-market-data/src/bifrost_market_data/schema/ddl.py`
- Trade per-env DDL: `bifrost-trade-core/docs/DATABASE.md`
- Spine decision: **D-Wave-6.3** in `bifrost-platform/config/ops-context.yaml`
