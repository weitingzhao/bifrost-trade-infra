-- TD-137 / core 0.52.0: three margin columns on account_nav_daily (Owner approved 2026-10-06).
-- Same statements as bifrost-trade-core src/bifrost_core/persistence/postgres/snapshot_ddl.py:78-81.
-- Nullable, no default: catalog-only change, no table rewrite, no backfill (existing rows stay NULL).
ALTER TABLE account_nav_daily ADD COLUMN IF NOT EXISTS cushion double precision;
ALTER TABLE account_nav_daily ADD COLUMN IF NOT EXISTS excess_liquidity double precision;
ALTER TABLE account_nav_daily ADD COLUMN IF NOT EXISTS maint_margin_req double precision;
