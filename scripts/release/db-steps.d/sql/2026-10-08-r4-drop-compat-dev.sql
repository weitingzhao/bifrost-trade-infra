-- naming R4 drop, bifrost_dev, core 0.47.0 (commit)
BEGIN;

SET LOCAL lock_timeout = '5s';

SET LOCAL ROLE bifrost;

DO $r4$ BEGIN
  IF current_database() <> 'bifrost_dev' THEN
    RAISE EXCEPTION 'R4: connected to %, but this SQL is for bifrost_dev', current_database();
  END IF;
END $r4$;

DO $r4$ BEGIN
  IF to_regclass('public.trade_execution') IS NULL OR to_regclass('brokerage.executions_raw_flex') IS NULL THEN
    RAISE EXCEPTION 'R4: public.trade_execution or the brokerage FDW tables are missing; nothing is dropped';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_class WHERE oid IN (to_regclass('public.strategy_instance'),
             to_regclass('public.strategy_instance_execution')) AND relkind <> 'v') THEN
    RAISE EXCEPTION 'R4: public.strategy_instance / strategy_instance_execution is not a view (R3 not applied?); nothing is dropped';
  END IF;
END $r4$;

DO $r4$ BEGIN
  IF EXISTS (SELECT 1 FROM unnest(ARRAY['public.strategy_instance_execution', 'public.strategy_instance', 'brokerage.instance_allocations', 'public.account_execution_instance_allocation', 'brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly', 'brokerage.executions_tws', 'brokerage.trade_fill_splits']) o(name)
             JOIN pg_class c ON c.oid = to_regclass(o.name)
             WHERE pg_get_userbyid(c.relowner) <> 'bifrost') THEN
    RAISE EXCEPTION 'R4: an object to drop or rebuild is not owned by bifrost: %',
      (SELECT string_agg(o.name || '=' || pg_get_userbyid(c.relowner), ', ')
         FROM unnest(ARRAY['public.strategy_instance_execution', 'public.strategy_instance', 'brokerage.instance_allocations', 'public.account_execution_instance_allocation', 'brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly', 'brokerage.executions_tws', 'brokerage.trade_fill_splits']) o(name) JOIN pg_class c ON c.oid = to_regclass(o.name));
  END IF;
END $r4$;

DO $r4$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid JOIN pg_class c ON c.oid = r.ev_class
             WHERE d.refobjid IN (SELECT to_regclass(o) FROM unnest(ARRAY['public.strategy_instance_execution', 'public.strategy_instance', 'brokerage.instance_allocations', 'public.account_execution_instance_allocation', 'brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly', 'brokerage.executions_tws', 'brokerage.trade_fill_splits']) o)
               AND c.oid <> d.refobjid
               AND c.oid NOT IN (SELECT to_regclass(o) FROM unnest(ARRAY['public.strategy_instance_execution', 'public.strategy_instance', 'brokerage.instance_allocations', 'public.account_execution_instance_allocation', 'brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly', 'brokerage.executions_tws', 'brokerage.trade_fill_splits']) o WHERE to_regclass(o) IS NOT NULL)) THEN
    RAISE EXCEPTION 'R4: another view depends on an object this step drops or rebuilds (the rebuild uses CASCADE): %',
      (SELECT string_agg(DISTINCT c.oid::regclass::text, ', ') FROM pg_depend d JOIN pg_rewrite r ON r.oid = d.objid
         JOIN pg_class c ON c.oid = r.ev_class
        WHERE d.refobjid IN (SELECT to_regclass(o) FROM unnest(ARRAY['public.strategy_instance_execution', 'public.strategy_instance', 'brokerage.instance_allocations', 'public.account_execution_instance_allocation', 'brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly', 'brokerage.executions_tws', 'brokerage.trade_fill_splits']) o) AND c.oid <> d.refobjid
          AND c.oid NOT IN (SELECT to_regclass(o) FROM unnest(ARRAY['public.strategy_instance_execution', 'public.strategy_instance', 'brokerage.instance_allocations', 'public.account_execution_instance_allocation', 'brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly', 'brokerage.executions_tws', 'brokerage.trade_fill_splits']) o WHERE to_regclass(o) IS NOT NULL));
  END IF;
END $r4$;

DO $r4$ BEGIN
  IF to_regclass('public.account_execution_instance_allocation') IS NOT NULL THEN
    IF (SELECT count(*) FROM public.account_execution_instance_allocation) <> 2 THEN
      RAISE EXCEPTION 'R4: public.account_execution_instance_allocation has % rows, expected 2 (the frozen rows): export it again and look before dropping',
        (SELECT count(*) FROM public.account_execution_instance_allocation);
    END IF;
    IF (SELECT count(*) FROM public.account_execution_instance_allocation a
  WHERE EXISTS (
    SELECT 1 FROM public.trade_execution te
    JOIN brokerage.executions x ON x.account_id = te.account_id AND x.exec_id = te.exec_id
    WHERE x.account_executions_id = a.account_executions_id
      AND te.account_id = a.account_id
      AND te.trade_id = a.strategy_instance_id
      AND te.split_quantity = a.allocated_quantity::numeric
  )) <> 2 THEN
      RAISE EXCEPTION 'R4: a row of public.account_execution_instance_allocation is not in trade_execution; nothing is dropped';
    END IF;
  END IF;
END $r4$;

DROP TABLE IF EXISTS pg_temp.r4_before;

CREATE TEMP TABLE r4_before ON COMMIT DROP AS SELECT
  (SELECT count(*) FROM public.trade) AS trade,
  (SELECT count(*) FROM public.trade_execution) AS trade_execution,
  (SELECT count(*) FROM public.trade_execution WHERE split_quantity IS NOT NULL) AS splits,
  (SELECT count(*) FROM brokerage.executions WHERE trade_id IS NOT NULL) AS view_attributed,
  (SELECT count(*) FROM brokerage.trade_fill_splits) AS view_splits;

DROP VIEW IF EXISTS public.strategy_instance_execution;

DROP VIEW IF EXISTS public.strategy_instance;

DROP VIEW IF EXISTS brokerage.instance_allocations;

DROP VIEW IF EXISTS brokerage.executions_tws CASCADE;

DROP VIEW IF EXISTS brokerage.trade_fill_splits CASCADE;

DROP VIEW IF EXISTS brokerage.executions_fly CASCADE;

DROP VIEW IF EXISTS brokerage.executions_final CASCADE;

DROP VIEW IF EXISTS brokerage.executions CASCADE;

CREATE OR REPLACE VIEW brokerage.executions AS SELECT u.account_executions_id, u.account_id, u.exec_id, u.exec_time, u.symbol, u.sec_type, u.side, u.quantity, u.price, u.source, u.expiry, u.strike, u.option_right, u.exchange, u.order_id, u.cum_qty, u.contract_key, u.currency, u.asset_category, u.sub_category, u.description, u.conid, u.security_id, u.security_id_type, u.cusip, u.isin, u.figi, u.listing_exchange, u.underlying_conid, u.underlying_symbol, u.underlying_security_id, u.underlying_listing_exchange, u.issuer, u.issuer_country_code, u.trade_id AS ib_trade_id, u.related_trade_id AS ib_related_trade_id, u.report_date, u.trade_date, u.settle_date_target, u.transaction_type, u.multiplier, u.principal_adjust_factor, u.proceeds, u.taxes, u.net_cash, u.close_price, u.open_close_indicator, u.notes, u.cost, u.fifo_pnl_realized, u.mtm_pnl, u.trade_money, u.fx_rate_to_base, u.acct_alias, u.model, u.raw_extra, tr.strategy_opportunity_id, te.trade_id, u.created_at
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
        LEFT JOIN public.trade_execution te
          ON te.account_id = u.account_id AND te.exec_id = u.exec_id
         AND te.split_quantity IS NULL
        LEFT JOIN public.trade tr ON tr.trade_id = te.trade_id;

CREATE OR REPLACE VIEW brokerage.executions_final AS SELECT u.account_executions_id, u.account_id, u.exec_id, u.exec_time, u.symbol, u.sec_type, u.side, u.quantity, u.price, u.source, u.expiry, u.strike, u.option_right, u.exchange, u.order_id, u.cum_qty, u.contract_key, u.currency, u.asset_category, u.sub_category, u.description, u.conid, u.security_id, u.security_id_type, u.cusip, u.isin, u.figi, u.listing_exchange, u.underlying_conid, u.underlying_symbol, u.underlying_security_id, u.underlying_listing_exchange, u.issuer, u.issuer_country_code, u.trade_id AS ib_trade_id, u.related_trade_id AS ib_related_trade_id, u.report_date, u.trade_date, u.settle_date_target, u.transaction_type, u.multiplier, u.principal_adjust_factor, u.proceeds, u.taxes, u.net_cash, u.close_price, u.open_close_indicator, u.notes, u.cost, u.fifo_pnl_realized, u.mtm_pnl, u.trade_money, u.fx_rate_to_base, u.acct_alias, u.model, u.raw_extra, tr.strategy_opportunity_id, te.trade_id, u.created_at
        FROM (
        SELECT executions_raw_flex_id AS account_executions_id,
               account_id, exec_id, exec_time, symbol, sec_type, side, quantity, price, source, expiry, strike, option_right, exchange, order_id, cum_qty, contract_key, currency, asset_category, sub_category, description, conid, security_id, security_id_type, cusip, isin, figi, listing_exchange, underlying_conid, underlying_symbol, underlying_security_id, underlying_listing_exchange, issuer, issuer_country_code, trade_id, related_trade_id, report_date, trade_date, settle_date_target, transaction_type, multiplier, principal_adjust_factor, proceeds, taxes, net_cash, close_price, open_close_indicator, notes, cost, fifo_pnl_realized, mtm_pnl, trade_money, fx_rate_to_base, acct_alias, model, raw_extra, strategy_opportunity_id, strategy_instance_id, created_at
        FROM brokerage.executions_raw_flex
        UNION ALL
        SELECT -(1000000000 + executions_raw_journal_id) AS account_executions_id,
               account_id, exec_id, exec_time, symbol, sec_type, side, quantity, price, source, expiry, strike, option_right, exchange, order_id, cum_qty, contract_key, currency, asset_category, sub_category, description, conid, security_id, security_id_type, cusip, isin, figi, listing_exchange, underlying_conid, underlying_symbol, underlying_security_id, underlying_listing_exchange, issuer, issuer_country_code, trade_id, related_trade_id, report_date, trade_date, settle_date_target, transaction_type, multiplier, principal_adjust_factor, proceeds, taxes, net_cash, close_price, open_close_indicator, notes, cost, fifo_pnl_realized, mtm_pnl, trade_money, fx_rate_to_base, acct_alias, model, raw_extra, strategy_opportunity_id, strategy_instance_id, created_at
        FROM brokerage.executions_raw_journal
        ) u
        LEFT JOIN public.trade_execution te
          ON te.account_id = u.account_id AND te.exec_id = u.exec_id
         AND te.split_quantity IS NULL
        LEFT JOIN public.trade tr ON tr.trade_id = te.trade_id;

CREATE OR REPLACE VIEW brokerage.executions_fly AS SELECT u.account_executions_id, u.account_id, u.exec_id, u.exec_time, u.symbol, u.sec_type, u.side, u.quantity, u.price, u.source, u.expiry, u.strike, u.option_right, u.exchange, u.order_id, u.cum_qty, u.contract_key, u.currency, u.asset_category, u.sub_category, u.description, u.conid, u.security_id, u.security_id_type, u.cusip, u.isin, u.figi, u.listing_exchange, u.underlying_conid, u.underlying_symbol, u.underlying_security_id, u.underlying_listing_exchange, u.issuer, u.issuer_country_code, u.trade_id AS ib_trade_id, u.related_trade_id AS ib_related_trade_id, u.report_date, u.trade_date, u.settle_date_target, u.transaction_type, u.multiplier, u.principal_adjust_factor, u.proceeds, u.taxes, u.net_cash, u.close_price, u.open_close_indicator, u.notes, u.cost, u.fifo_pnl_realized, u.mtm_pnl, u.trade_money, u.fx_rate_to_base, u.acct_alias, u.model, u.raw_extra, tr.strategy_opportunity_id, te.trade_id, u.created_at
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
        LEFT JOIN public.trade_execution te
          ON te.account_id = u.account_id AND te.exec_id = u.exec_id
         AND te.split_quantity IS NULL
        LEFT JOIN public.trade tr ON tr.trade_id = te.trade_id;

CREATE OR REPLACE VIEW brokerage.executions_tws AS SELECT u.account_executions_id, u.account_id, u.exec_id, u.exec_time, u.symbol, u.sec_type, u.side, u.quantity, u.price, u.source, u.expiry, u.strike, u.option_right, u.exchange, u.order_id, u.cum_qty, u.contract_key, u.currency, u.asset_category, u.sub_category, u.description, u.conid, u.security_id, u.security_id_type, u.cusip, u.isin, u.figi, u.listing_exchange, u.underlying_conid, u.underlying_symbol, u.underlying_security_id, u.underlying_listing_exchange, u.issuer, u.issuer_country_code, u.trade_id AS ib_trade_id, u.related_trade_id AS ib_related_trade_id, u.report_date, u.trade_date, u.settle_date_target, u.transaction_type, u.multiplier, u.principal_adjust_factor, u.proceeds, u.taxes, u.net_cash, u.close_price, u.open_close_indicator, u.notes, u.cost, u.fifo_pnl_realized, u.mtm_pnl, u.trade_money, u.fx_rate_to_base, u.acct_alias, u.model, u.raw_extra, tr.strategy_opportunity_id, te.trade_id, u.created_at
        FROM (
        SELECT -(executions_raw_tws_id) AS account_executions_id,
               account_id, exec_id, exec_time, symbol, sec_type, side, quantity, price, source, expiry, strike, option_right, exchange, order_id, cum_qty, contract_key, currency, asset_category, sub_category, description, conid, security_id, security_id_type, cusip, isin, figi, listing_exchange, underlying_conid, underlying_symbol, underlying_security_id, underlying_listing_exchange, issuer, issuer_country_code, trade_id, related_trade_id, report_date, trade_date, settle_date_target, transaction_type, multiplier, principal_adjust_factor, proceeds, taxes, net_cash, close_price, open_close_indicator, notes, cost, fifo_pnl_realized, mtm_pnl, trade_money, fx_rate_to_base, acct_alias, model, raw_extra, strategy_opportunity_id, strategy_instance_id, created_at
        FROM brokerage.executions_raw_tws
        ) u
        LEFT JOIN public.trade_execution te
          ON te.account_id = u.account_id AND te.exec_id = u.exec_id
         AND te.split_quantity IS NULL
        LEFT JOIN public.trade tr ON tr.trade_id = te.trade_id;

CREATE OR REPLACE VIEW brokerage.trade_fill_splits AS
        SELECT s.account_id, x.account_executions_id, s.trade_id,
               s.split_quantity::double precision AS quantity,
               s.exec_id
        FROM public.trade_execution s
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
        WHERE s.split_quantity IS NOT NULL;

DO $r4$ BEGIN
  IF to_regrole('trade_app_dev') IS NOT NULL THEN
    GRANT SELECT ON brokerage.executions, brokerage.executions_final, brokerage.executions_fly, brokerage.executions_tws, brokerage.trade_fill_splits TO trade_app_dev;
  END IF;
END $r4$;

DROP TABLE IF EXISTS public.account_execution_instance_allocation;

SELECT what, before, after, before = after AS same FROM (
SELECT 'trade' AS what, b.trade AS before, (SELECT count(*) FROM public.trade) AS after FROM r4_before b
UNION ALL SELECT 'trade_execution' AS what, b.trade_execution AS before, (SELECT count(*) FROM public.trade_execution) AS after FROM r4_before b
UNION ALL SELECT 'splits' AS what, b.splits AS before, (SELECT count(*) FROM public.trade_execution WHERE split_quantity IS NOT NULL) AS after FROM r4_before b
UNION ALL SELECT 'view_attributed' AS what, b.view_attributed AS before, (SELECT count(*) FROM brokerage.executions WHERE trade_id IS NOT NULL) AS after FROM r4_before b
UNION ALL SELECT 'view_splits' AS what, b.view_splits AS before, (SELECT count(*) FROM brokerage.trade_fill_splits) AS after FROM r4_before b
) r;

SELECT o AS dropped, to_regclass(o) IS NULL AS gone FROM unnest(ARRAY['public.strategy_instance_execution', 'public.strategy_instance', 'brokerage.instance_allocations', 'public.account_execution_instance_allocation']) o;

SELECT v AS env_view, CASE WHEN to_regrole('trade_app_dev') IS NULL THEN NULL ELSE has_table_privilege('trade_app_dev', v, 'SELECT') END AS trade_app_dev_select FROM unnest(ARRAY['brokerage.executions', 'brokerage.executions_final', 'brokerage.executions_fly', 'brokerage.executions_tws', 'brokerage.trade_fill_splits']) v;

DO $r4$ BEGIN
  IF EXISTS (SELECT 1 FROM r4_before b WHERE b.trade <> (SELECT count(*) FROM public.trade)
  OR b.trade_execution <> (SELECT count(*) FROM public.trade_execution)
  OR b.splits <> (SELECT count(*) FROM public.trade_execution WHERE split_quantity IS NOT NULL)
  OR b.view_attributed <> (SELECT count(*) FROM brokerage.executions WHERE trade_id IS NOT NULL)
  OR b.view_splits <> (SELECT count(*) FROM brokerage.trade_fill_splits)) THEN
    RAISE EXCEPTION 'R4: a count changed (see the report above); nothing is kept';
  END IF;
  IF to_regclass('public.strategy_instance_execution') IS NOT NULL OR to_regclass('public.strategy_instance') IS NOT NULL OR to_regclass('brokerage.instance_allocations') IS NOT NULL OR to_regclass('public.account_execution_instance_allocation') IS NOT NULL OR EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'brokerage' AND table_name IN ('executions', 'executions_final', 'executions_fly', 'executions_tws', 'trade_fill_splits') AND column_name = 'strategy_instance_id') THEN
    RAISE EXCEPTION 'R4: an object is still there (see the report above); nothing is kept';
  END IF;
  IF to_regrole('trade_app_dev') IS NOT NULL THEN  -- nested: AND does not short-circuit in SQL
    IF NOT (has_table_privilege('trade_app_dev', 'brokerage.executions', 'SELECT') AND has_table_privilege('trade_app_dev', 'brokerage.executions_final', 'SELECT') AND has_table_privilege('trade_app_dev', 'brokerage.executions_fly', 'SELECT') AND has_table_privilege('trade_app_dev', 'brokerage.executions_tws', 'SELECT') AND has_table_privilege('trade_app_dev', 'brokerage.trade_fill_splits', 'SELECT')) THEN
      RAISE EXCEPTION 'R4: trade_app_dev cannot read a rebuilt env view (see the report above); nothing is kept';
    END IF;
  END IF;
END $r4$;

COMMIT;
