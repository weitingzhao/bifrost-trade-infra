-- naming R3 REVERSE, bifrost_prod, back to core 0.44.0 names (commit)
BEGIN;

SET LOCAL lock_timeout = '5s';

SET LOCAL ROLE bifrost;

DO $r3$ BEGIN
  IF current_database() <> 'bifrost_prod' THEN
    RAISE EXCEPTION 'R3: connected to %, but this SQL is for bifrost_prod', current_database();
  END IF;
  IF (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = to_regclass('brokerage.executions'))
     IS DISTINCT FROM 'bifrost' THEN
    RAISE EXCEPTION 'R3: brokerage.executions is owned by %, this SQL expects bifrost (regenerate with the right --env)',
      (SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = to_regclass('brokerage.executions'));
  END IF;
END $r3$;

DO $r3$ BEGIN
  IF (SELECT relkind FROM pg_class WHERE oid = to_regclass('public.trade')) IS DISTINCT FROM 'r' THEN
    RAISE EXCEPTION 'R3 reverse: public.trade is not a table (not migrated, or already reversed?)';
  END IF;
  IF (SELECT relkind FROM pg_class WHERE oid = to_regclass('public.strategy_instance')) = 'r' THEN
    RAISE EXCEPTION 'R3 reverse: public.strategy_instance is a table already';
  END IF;
END $r3$;

DROP TABLE IF EXISTS pg_temp.r3_before;

CREATE TEMP TABLE r3_before ON COMMIT DROP AS SELECT
  (SELECT count(*) FROM public.trade) AS trade,
  (SELECT count(*) FROM public.trade_execution) AS trade_execution,
  (SELECT count(*) FROM public.trade_execution WHERE split_quantity IS NOT NULL) AS splits,
  (SELECT count(*) FROM brokerage.executions WHERE trade_id IS NOT NULL) AS view_attributed,
  (SELECT count(*) FROM brokerage.trade_fill_splits) AS view_splits;

DROP VIEW brokerage.instance_allocations;

DROP VIEW brokerage.trade_fill_splits;

DROP VIEW brokerage.executions_tws;

DROP VIEW brokerage.executions_fly;

DROP VIEW brokerage.executions_final;

DROP VIEW brokerage.executions;

DROP VIEW IF EXISTS public.strategy_instance_execution;

DROP VIEW IF EXISTS public.strategy_instance;

ALTER TABLE public.trade_review RENAME COLUMN tags_dropped_json TO tags_dropped;

ALTER TABLE public.trade_review RENAME COLUMN tags_added_json TO tags_added;

ALTER TABLE public.trade_review RENAME CONSTRAINT trade_review_trade_id_key TO trade_review_strategy_instance_id_key;

ALTER TABLE public.trade_review RENAME CONSTRAINT trade_review_trade_id_fkey TO trade_review_strategy_instance_id_fkey;

ALTER TABLE public.trade_review RENAME COLUMN trade_id TO strategy_instance_id;

ALTER INDEX public.strategy_plan_trade RENAME TO strategy_plan_instance;

ALTER TABLE public.strategy_plan RENAME CONSTRAINT strategy_plan_trade_id_fkey TO strategy_plan_strategy_instance_id_fkey;

ALTER TABLE public.strategy_plan RENAME COLUMN trade_id TO strategy_instance_id;

ALTER INDEX public.trade_execution_trade_ix RENAME TO strategy_instance_execution_instance_ix;

ALTER INDEX public.trade_execution_whole_uq RENAME TO strategy_instance_execution_whole_uq;

ALTER TABLE public.trade_execution RENAME CONSTRAINT trade_execution_qty_ck TO strategy_instance_execution_qty_ck;

ALTER TABLE public.trade_execution RENAME CONSTRAINT trade_execution_uq TO strategy_instance_execution_uq;

ALTER TABLE public.trade_execution RENAME CONSTRAINT trade_execution_trade_fk TO strategy_instance_execution_instance_fk;

ALTER TABLE public.trade_execution RENAME CONSTRAINT trade_execution_pkey TO strategy_instance_execution_pkey;

ALTER SEQUENCE public.trade_execution_trade_execution_id_seq RENAME TO strategy_instance_execution_strategy_instance_execution_id_seq;

ALTER TABLE public.trade_execution RENAME COLUMN split_quantity TO allocated_quantity;

ALTER TABLE public.trade_execution RENAME COLUMN trade_id TO strategy_instance_id;

ALTER TABLE public.trade_execution RENAME COLUMN trade_execution_id TO strategy_instance_execution_id;

ALTER TABLE public.trade_execution RENAME TO strategy_instance_execution;

ALTER INDEX public.trade_account_opened RENAME TO strategy_instance_account_opened;

ALTER INDEX public.trade_opportunity_id RENAME TO strategy_instance_opportunity_id;

ALTER TABLE public.trade RENAME CONSTRAINT trade_strategy_opportunity_id_fkey TO strategy_instance_strategy_opportunity_id_fkey;

ALTER TABLE public.trade RENAME CONSTRAINT trade_id_account_uq TO strategy_instance_id_account_uq;

ALTER TABLE public.trade RENAME CONSTRAINT trade_pkey TO strategy_instance_pkey;

ALTER SEQUENCE public.trade_trade_id_seq RENAME TO strategy_instance_strategy_instance_id_seq;

ALTER TABLE public.trade RENAME COLUMN trade_id TO strategy_instance_id;

ALTER TABLE public.trade RENAME TO strategy_instance;

CREATE OR REPLACE VIEW brokerage.executions AS SELECT u.account_executions_id, u.account_id, u.exec_id, u.exec_time, u.symbol, u.sec_type, u.side, u.quantity, u.price, u.source, u.expiry, u.strike, u.option_right, u.exchange, u.order_id, u.cum_qty, u.contract_key, u.currency, u.asset_category, u.sub_category, u.description, u.conid, u.security_id, u.security_id_type, u.cusip, u.isin, u.figi, u.listing_exchange, u.underlying_conid, u.underlying_symbol, u.underlying_security_id, u.underlying_listing_exchange, u.issuer, u.issuer_country_code, u.trade_id, u.related_trade_id, u.report_date, u.trade_date, u.settle_date_target, u.transaction_type, u.multiplier, u.principal_adjust_factor, u.proceeds, u.taxes, u.net_cash, u.close_price, u.open_close_indicator, u.notes, u.cost, u.fifo_pnl_realized, u.mtm_pnl, u.trade_money, u.fx_rate_to_base, u.acct_alias, u.model, u.raw_extra, si.strategy_opportunity_id, sie.strategy_instance_id, u.created_at
        FROM (
        SELECT executions_raw_flex_id AS account_executions_id,
               account_id, exec_id, exec_time, symbol, sec_type, side, quantity, price, source, expiry, strike, option_right, exchange, order_id, cum_qty, contract_key, currency, asset_category, sub_category, description, conid, security_id, security_id_type, cusip, isin, figi, listing_exchange, underlying_conid, underlying_symbol, underlying_security_id, underlying_listing_exchange, issuer, issuer_country_code, trade_id, related_trade_id, report_date, trade_date, settle_date_target, transaction_type, multiplier, principal_adjust_factor, proceeds, taxes, net_cash, close_price, open_close_indicator, notes, cost, fifo_pnl_realized, mtm_pnl, trade_money, fx_rate_to_base, acct_alias, model, raw_extra, strategy_opportunity_id, strategy_instance_id, created_at
        FROM brokerage.executions_raw_flex
        UNION ALL
        SELECT -(executions_raw_tws_id) AS account_executions_id,
               account_id, exec_id, exec_time, symbol, sec_type, side, quantity, price, source, expiry, strike, option_right, exchange, order_id, cum_qty, contract_key, currency, asset_category, sub_category, description, conid, security_id, security_id_type, cusip, isin, figi, listing_exchange, underlying_conid, underlying_symbol, underlying_security_id, underlying_listing_exchange, issuer, issuer_country_code, trade_id, related_trade_id, report_date, trade_date, settle_date_target, transaction_type, multiplier, principal_adjust_factor, proceeds, taxes, net_cash, close_price, open_close_indicator, notes, cost, fifo_pnl_realized, mtm_pnl, trade_money, fx_rate_to_base, acct_alias, model, raw_extra, strategy_opportunity_id, strategy_instance_id, created_at
        FROM brokerage.executions_raw_tws t
        WHERE NOT EXISTS (
            SELECT 1 FROM brokerage.executions_raw_flex f
            WHERE f.exec_id = t.exec_id
              AND f.exec_id IS NOT NULL AND f.exec_id != ''
              AND t.exec_id IS NOT NULL AND t.exec_id != ''
        )
        UNION ALL
        SELECT -(1000000000 + executions_raw_journal_id) AS account_executions_id,
               account_id, exec_id, exec_time, symbol, sec_type, side, quantity, price, source, expiry, strike, option_right, exchange, order_id, cum_qty, contract_key, currency, asset_category, sub_category, description, conid, security_id, security_id_type, cusip, isin, figi, listing_exchange, underlying_conid, underlying_symbol, underlying_security_id, underlying_listing_exchange, issuer, issuer_country_code, trade_id, related_trade_id, report_date, trade_date, settle_date_target, transaction_type, multiplier, principal_adjust_factor, proceeds, taxes, net_cash, close_price, open_close_indicator, notes, cost, fifo_pnl_realized, mtm_pnl, trade_money, fx_rate_to_base, acct_alias, model, raw_extra, strategy_opportunity_id, strategy_instance_id, created_at
        FROM brokerage.executions_raw_journal
        ) u
        LEFT JOIN public.strategy_instance_execution sie
          ON sie.account_id = u.account_id AND sie.exec_id = u.exec_id
         AND sie.allocated_quantity IS NULL
        LEFT JOIN public.strategy_instance si ON si.strategy_instance_id = sie.strategy_instance_id;

CREATE OR REPLACE VIEW brokerage.executions_final AS SELECT u.account_executions_id, u.account_id, u.exec_id, u.exec_time, u.symbol, u.sec_type, u.side, u.quantity, u.price, u.source, u.expiry, u.strike, u.option_right, u.exchange, u.order_id, u.cum_qty, u.contract_key, u.currency, u.asset_category, u.sub_category, u.description, u.conid, u.security_id, u.security_id_type, u.cusip, u.isin, u.figi, u.listing_exchange, u.underlying_conid, u.underlying_symbol, u.underlying_security_id, u.underlying_listing_exchange, u.issuer, u.issuer_country_code, u.trade_id, u.related_trade_id, u.report_date, u.trade_date, u.settle_date_target, u.transaction_type, u.multiplier, u.principal_adjust_factor, u.proceeds, u.taxes, u.net_cash, u.close_price, u.open_close_indicator, u.notes, u.cost, u.fifo_pnl_realized, u.mtm_pnl, u.trade_money, u.fx_rate_to_base, u.acct_alias, u.model, u.raw_extra, si.strategy_opportunity_id, sie.strategy_instance_id, u.created_at
        FROM (
        SELECT executions_raw_flex_id AS account_executions_id,
               account_id, exec_id, exec_time, symbol, sec_type, side, quantity, price, source, expiry, strike, option_right, exchange, order_id, cum_qty, contract_key, currency, asset_category, sub_category, description, conid, security_id, security_id_type, cusip, isin, figi, listing_exchange, underlying_conid, underlying_symbol, underlying_security_id, underlying_listing_exchange, issuer, issuer_country_code, trade_id, related_trade_id, report_date, trade_date, settle_date_target, transaction_type, multiplier, principal_adjust_factor, proceeds, taxes, net_cash, close_price, open_close_indicator, notes, cost, fifo_pnl_realized, mtm_pnl, trade_money, fx_rate_to_base, acct_alias, model, raw_extra, strategy_opportunity_id, strategy_instance_id, created_at
        FROM brokerage.executions_raw_flex
        UNION ALL
        SELECT -(1000000000 + executions_raw_journal_id) AS account_executions_id,
               account_id, exec_id, exec_time, symbol, sec_type, side, quantity, price, source, expiry, strike, option_right, exchange, order_id, cum_qty, contract_key, currency, asset_category, sub_category, description, conid, security_id, security_id_type, cusip, isin, figi, listing_exchange, underlying_conid, underlying_symbol, underlying_security_id, underlying_listing_exchange, issuer, issuer_country_code, trade_id, related_trade_id, report_date, trade_date, settle_date_target, transaction_type, multiplier, principal_adjust_factor, proceeds, taxes, net_cash, close_price, open_close_indicator, notes, cost, fifo_pnl_realized, mtm_pnl, trade_money, fx_rate_to_base, acct_alias, model, raw_extra, strategy_opportunity_id, strategy_instance_id, created_at
        FROM brokerage.executions_raw_journal
        ) u
        LEFT JOIN public.strategy_instance_execution sie
          ON sie.account_id = u.account_id AND sie.exec_id = u.exec_id
         AND sie.allocated_quantity IS NULL
        LEFT JOIN public.strategy_instance si ON si.strategy_instance_id = sie.strategy_instance_id;

CREATE OR REPLACE VIEW brokerage.executions_fly AS SELECT u.account_executions_id, u.account_id, u.exec_id, u.exec_time, u.symbol, u.sec_type, u.side, u.quantity, u.price, u.source, u.expiry, u.strike, u.option_right, u.exchange, u.order_id, u.cum_qty, u.contract_key, u.currency, u.asset_category, u.sub_category, u.description, u.conid, u.security_id, u.security_id_type, u.cusip, u.isin, u.figi, u.listing_exchange, u.underlying_conid, u.underlying_symbol, u.underlying_security_id, u.underlying_listing_exchange, u.issuer, u.issuer_country_code, u.trade_id, u.related_trade_id, u.report_date, u.trade_date, u.settle_date_target, u.transaction_type, u.multiplier, u.principal_adjust_factor, u.proceeds, u.taxes, u.net_cash, u.close_price, u.open_close_indicator, u.notes, u.cost, u.fifo_pnl_realized, u.mtm_pnl, u.trade_money, u.fx_rate_to_base, u.acct_alias, u.model, u.raw_extra, si.strategy_opportunity_id, sie.strategy_instance_id, u.created_at
        FROM (
        SELECT -(t.executions_raw_tws_id) AS account_executions_id,
               t.account_id, t.exec_id, t.exec_time, t.symbol, t.sec_type, t.side, t.quantity, t.price, t.source, t.expiry, t.strike, t.option_right, t.exchange, t.order_id, t.cum_qty, t.contract_key, t.currency, t.asset_category, t.sub_category, t.description, t.conid, t.security_id, t.security_id_type, t.cusip, t.isin, t.figi, t.listing_exchange, t.underlying_conid, t.underlying_symbol, t.underlying_security_id, t.underlying_listing_exchange, t.issuer, t.issuer_country_code, t.trade_id, t.related_trade_id, t.report_date, t.trade_date, t.settle_date_target, t.transaction_type, t.multiplier, t.principal_adjust_factor, t.proceeds, t.taxes, t.net_cash, t.close_price, t.open_close_indicator, t.notes, t.cost, t.fifo_pnl_realized, t.mtm_pnl, t.trade_money, t.fx_rate_to_base, t.acct_alias, t.model, t.raw_extra, t.strategy_opportunity_id, t.strategy_instance_id, t.created_at
        FROM brokerage.executions_raw_tws t
        WHERE upper(trim(COALESCE(t.sec_type, ''))) <> 'BAG'
          AND NOT EXISTS (
            SELECT 1
            FROM brokerage.executions_final f
            WHERE f.account_id IS NOT DISTINCT FROM t.account_id
              AND (
                (
                  NULLIF(trim(COALESCE(t.contract_key, '')), '') IS NOT NULL
                  AND NULLIF(trim(COALESCE(f.contract_key, '')), '') IS NOT NULL
                  AND trim(COALESCE(f.contract_key, '')) = trim(COALESCE(t.contract_key, ''))
                )
                OR (
                  upper(trim(COALESCE(t.sec_type, ''))) = 'STK'
                  AND upper(trim(COALESCE(f.sec_type, ''))) = 'STK'
                  AND NULLIF(trim(COALESCE(t.contract_key, '')), '') IS NOT NULL
                  AND NULLIF(trim(COALESCE(f.contract_key, '')), '') IS NOT NULL
                  AND rtrim(trim(COALESCE(t.contract_key, '')), '|')
                      = rtrim(trim(COALESCE(f.contract_key, '')), '|')
                )
                OR (
                  upper(trim(COALESCE(t.sec_type, ''))) = 'STK'
                  AND upper(trim(COALESCE(NULLIF(trim(COALESCE(f.sec_type, '')), ''), NULLIF(trim(split_part(COALESCE(f.contract_key, ''), '|', 2)), '')))) IN ('STK', 'EQUITY', 'FUND', 'ETF', 'ETN', 'ADR', 'CORP', 'STOCK', 'REIT', 'WAR')
                  AND NULLIF(trim(COALESCE(t.symbol, '')), '') IS NOT NULL
                  AND upper(trim(COALESCE(t.symbol, ''))) = upper(trim(COALESCE(f.symbol, '')))
                )
              )
        )
        ) u
        LEFT JOIN public.strategy_instance_execution sie
          ON sie.account_id = u.account_id AND sie.exec_id = u.exec_id
         AND sie.allocated_quantity IS NULL
        LEFT JOIN public.strategy_instance si ON si.strategy_instance_id = sie.strategy_instance_id;

CREATE OR REPLACE VIEW brokerage.executions_tws AS SELECT u.account_executions_id, u.account_id, u.exec_id, u.exec_time, u.symbol, u.sec_type, u.side, u.quantity, u.price, u.source, u.expiry, u.strike, u.option_right, u.exchange, u.order_id, u.cum_qty, u.contract_key, u.currency, u.asset_category, u.sub_category, u.description, u.conid, u.security_id, u.security_id_type, u.cusip, u.isin, u.figi, u.listing_exchange, u.underlying_conid, u.underlying_symbol, u.underlying_security_id, u.underlying_listing_exchange, u.issuer, u.issuer_country_code, u.trade_id, u.related_trade_id, u.report_date, u.trade_date, u.settle_date_target, u.transaction_type, u.multiplier, u.principal_adjust_factor, u.proceeds, u.taxes, u.net_cash, u.close_price, u.open_close_indicator, u.notes, u.cost, u.fifo_pnl_realized, u.mtm_pnl, u.trade_money, u.fx_rate_to_base, u.acct_alias, u.model, u.raw_extra, si.strategy_opportunity_id, sie.strategy_instance_id, u.created_at
        FROM (
        SELECT -(executions_raw_tws_id) AS account_executions_id,
               account_id, exec_id, exec_time, symbol, sec_type, side, quantity, price, source, expiry, strike, option_right, exchange, order_id, cum_qty, contract_key, currency, asset_category, sub_category, description, conid, security_id, security_id_type, cusip, isin, figi, listing_exchange, underlying_conid, underlying_symbol, underlying_security_id, underlying_listing_exchange, issuer, issuer_country_code, trade_id, related_trade_id, report_date, trade_date, settle_date_target, transaction_type, multiplier, principal_adjust_factor, proceeds, taxes, net_cash, close_price, open_close_indicator, notes, cost, fifo_pnl_realized, mtm_pnl, trade_money, fx_rate_to_base, acct_alias, model, raw_extra, strategy_opportunity_id, strategy_instance_id, created_at
        FROM brokerage.executions_raw_tws
        ) u
        LEFT JOIN public.strategy_instance_execution sie
          ON sie.account_id = u.account_id AND sie.exec_id = u.exec_id
         AND sie.allocated_quantity IS NULL
        LEFT JOIN public.strategy_instance si ON si.strategy_instance_id = sie.strategy_instance_id;

CREATE OR REPLACE VIEW brokerage.instance_allocations AS
SELECT s.account_id, x.account_executions_id, s.strategy_instance_id,
       s.allocated_quantity::double precision AS allocated_quantity,
       s.exec_id
FROM public.strategy_instance_execution s
JOIN (
    SELECT executions_raw_flex_id AS account_executions_id, account_id, exec_id
    FROM brokerage.executions_raw_flex
    UNION ALL
    SELECT -(executions_raw_tws_id), account_id, exec_id
    FROM brokerage.executions_raw_tws
    UNION ALL
    SELECT -(1000000000 + executions_raw_journal_id), account_id, exec_id
    FROM brokerage.executions_raw_journal
) x ON x.account_id = s.account_id AND x.exec_id = s.exec_id
WHERE s.allocated_quantity IS NOT NULL;

SELECT what, before, after, before = after AS same FROM (
SELECT 'trade' AS what, b.trade AS before, (SELECT count(*) FROM public.strategy_instance) AS after FROM r3_before b
UNION ALL SELECT 'trade_execution' AS what, b.trade_execution AS before, (SELECT count(*) FROM public.strategy_instance_execution) AS after FROM r3_before b
UNION ALL SELECT 'splits' AS what, b.splits AS before, (SELECT count(*) FROM public.strategy_instance_execution WHERE allocated_quantity IS NOT NULL) AS after FROM r3_before b
UNION ALL SELECT 'view_attributed' AS what, b.view_attributed AS before, (SELECT count(*) FROM brokerage.executions WHERE strategy_instance_id IS NOT NULL) AS after FROM r3_before b
UNION ALL SELECT 'view_splits' AS what, b.view_splits AS before, (SELECT count(*) FROM brokerage.instance_allocations) AS after FROM r3_before b
) r;

DO $r3$ BEGIN
  IF EXISTS (SELECT 1 FROM r3_before b WHERE b.trade <> (SELECT count(*) FROM public.strategy_instance)
  OR b.trade_execution <> (SELECT count(*) FROM public.strategy_instance_execution)
  OR b.splits <> (SELECT count(*) FROM public.strategy_instance_execution WHERE allocated_quantity IS NOT NULL)
  OR b.view_attributed <> (SELECT count(*) FROM brokerage.executions WHERE strategy_instance_id IS NOT NULL)
  OR b.view_splits <> (SELECT count(*) FROM brokerage.instance_allocations)) THEN
    RAISE EXCEPTION 'R3: a count changed across the rename (see the report above); nothing is kept';
  END IF;
END $r3$;

COMMIT;
