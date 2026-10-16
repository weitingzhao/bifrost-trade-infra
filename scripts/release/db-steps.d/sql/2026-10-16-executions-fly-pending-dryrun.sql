-- Generated from core 0.61.0 (a87e39f): the executions_fly statement of view_statements('brokerage') in bifrost_core.persistence.postgres; identical in dev / stg / prod.
-- Dry run: the same replacement inside a transaction that is rolled back.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL ROLE bifrost;
CREATE OR REPLACE VIEW brokerage.executions_fly AS SELECT u.account_executions_id, u.account_id, u.exec_id, u.exec_time, u.symbol, u.sec_type, u.side, u.quantity, u.price, u.source, u.expiry, u.strike, u.option_right, u.exchange, u.order_id, u.cum_qty, u.contract_key, u.currency, u.asset_category, u.sub_category, u.description, u.conid, u.security_id, u.security_id_type, u.cusip, u.isin, u.figi, u.listing_exchange, u.underlying_conid, u.underlying_symbol, u.underlying_security_id, u.underlying_listing_exchange, u.issuer, u.issuer_country_code, u.trade_id AS ib_trade_id, u.related_trade_id AS ib_related_trade_id, u.report_date, u.trade_date, u.settle_date_target, u.transaction_type, u.multiplier, u.principal_adjust_factor, u.proceeds, u.taxes, u.net_cash, u.close_price, u.open_close_indicator, u.notes, u.cost, u.fifo_pnl_realized, u.mtm_pnl, u.trade_money, u.fx_rate_to_base, u.acct_alias, u.model, u.raw_extra, tr.strategy_opportunity_id, te.trade_id, u.created_at
        FROM (
        SELECT -(t.executions_raw_tws_id) AS account_executions_id,
               t.account_id, t.exec_id, t.exec_time, t.symbol, t.sec_type, t.side, t.quantity, t.price, t.source, t.expiry, t.strike, t.option_right, t.exchange, t.order_id, t.cum_qty, t.contract_key, t.currency, t.asset_category, t.sub_category, t.description, t.conid, t.security_id, t.security_id_type, t.cusip, t.isin, t.figi, t.listing_exchange, t.underlying_conid, t.underlying_symbol, t.underlying_security_id, t.underlying_listing_exchange, t.issuer, t.issuer_country_code, t.trade_id, t.related_trade_id, t.report_date, t.trade_date, t.settle_date_target, t.transaction_type, t.multiplier, t.principal_adjust_factor, t.proceeds, t.taxes, t.net_cash, t.close_price, t.open_close_indicator, t.notes, t.cost, t.fifo_pnl_realized, t.mtm_pnl, t.trade_money, t.fx_rate_to_base, t.acct_alias, t.model, t.raw_extra, t.strategy_opportunity_id, t.strategy_instance_id, t.created_at
        FROM brokerage.executions_raw_tws t
        LEFT JOIN (
            SELECT account_id, max(trade_date) AS flex_through
            FROM brokerage.executions_raw_flex
            GROUP BY account_id
        ) w ON w.account_id = t.account_id
        WHERE upper(trim(COALESCE(t.sec_type, ''))) <> 'BAG'
          AND NULLIF(trim(COALESCE(t.account_id, '')), '') IS NOT NULL
          AND NOT EXISTS (
            SELECT 1
            FROM brokerage.executions_raw_flex f
            WHERE f.exec_id = t.exec_id
              AND NULLIF(trim(COALESCE(t.exec_id, '')), '') IS NOT NULL
          )
          AND COALESCE(t.trade_date, (t.exec_time AT TIME ZONE 'America/New_York')::date, (t.created_at AT TIME ZONE 'America/New_York')::date) > COALESCE(w.flex_through, DATE '-infinity')
        ) u
        LEFT JOIN public.trade_execution te
          ON te.account_id = u.account_id AND te.exec_id = u.exec_id
         AND te.split_quantity IS NULL
        LEFT JOIN public.trade tr ON tr.trade_id = te.trade_id;
SELECT count(*) AS pending_rows_with_new_rule FROM brokerage.executions_fly;
ROLLBACK;
