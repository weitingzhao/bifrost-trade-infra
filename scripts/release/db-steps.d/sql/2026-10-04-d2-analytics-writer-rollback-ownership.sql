-- D2 rollback, full (as postgres, bifrost_golden_source, one transaction; only after
-- sql/2026-10-04-d2-analytics-writer-rollback.sql, and only if the Owner wants the owners back as well).
-- Puts back the owners and analytics_writer's direct grants exactly as read (read-only) on 2026-10-04
-- 05:5x UTC: the 122 relations below were owned by bifrost; analytics_writer held the listed privileges
-- on each directly. Partitions first, then parents. A relation Research created after D2 is not listed
-- and keeps analytics_writer as owner. Schemas go back to bifrost only if step 2 ran (no-op otherwise).
--
-- ALTER … OWNER TO bifrost folds analytics_writer's own ACL entry into bifrost's, so the direct grants
-- are given back after the move. bifrost's explicit S/I/U/D/TRUNCATE from step 1 folds into its owner
-- entry: nothing to undo there. raw_broker.executions_final SELECT is revoked last.

\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '120s';

DO $$
DECLARE
  r record;
BEGIN
  FOR r IN SELECT * FROM (VALUES
  ('features.option_metric_atm_iv_daily_default', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2025m08', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2025m09', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2025m10', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2025m11', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2025m12', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m01', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m02', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m03', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m04', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m05', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m06', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m07', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m08', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m09', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m10', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m11', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily_y2026m12', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_default', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2025m08', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2025m09', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2025m10', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2025m11', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2025m12', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m01', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m02', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m03', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m04', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m05', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m06', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m07', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m08', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m09', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m10', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m11', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily_y2026m12', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_default', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2025m08', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2025m09', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2025m10', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2025m11', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2025m12', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m01', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m02', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m03', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m04', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m05', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m06', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m07', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m08', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m09', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m10', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m11', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily_y2026m12', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_default', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2025m08', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2025m09', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2025m10', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2025m11', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2025m12', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m01', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m02', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m03', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m04', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m05', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m06', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m07', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m08', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m09', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m10', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m11', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily_y2026m12', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.event_signal_radar_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.macro_event_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_flow_multi_leg_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_flow_sentiment_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_iv_reconstructed_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_metric_atm_iv_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_metric_gex_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_metric_gex_intraday', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_metric_gex_levels_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_metric_iv_percentile_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_metric_max_pain_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_metric_pcr_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_metric_vanna_charm_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_surface_fit_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.option_surface_iv_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.option_surface_residual_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.stock_backtest_results_period', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.stock_backtest_settlement', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.stock_forecast_hourly', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.stock_forecast_hourly_session', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.stock_forecast_session', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.stock_forecast_terrain_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.stock_forecast_terrain_intraday', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.stock_signal_alert_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.stock_signal_canonical_pnl_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.stock_signal_lens_hit_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.stock_signal_momentum_daily', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('features.stock_signal_playbook_trigger_intraday', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.stock_signal_scan_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.stock_signal_sepa_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.stock_signal_vrp_daily', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('features.v_atm_iv_unified', 'VIEW', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.agent_persona', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.ai_action_log', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.ai_draft', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.backtest_run', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.candidate_outcome', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.candidate_pool', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.copilot_bridge_event', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('research.copilot_session', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.embedding_chunk', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('research.hypothesis', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.loop_policy_template', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.objective', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.objective_run', 'TABLE', 'DELETE, INSERT, SELECT, TRUNCATE, UPDATE'),
  ('research.option_universe', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('research.playbook_case', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('research.playbook_note', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('research.playbook_rule', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE'),
  ('research.saved_screen', 'TABLE', 'DELETE, INSERT, MAINTAIN, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE')
  ) AS t(fq, kind, aw_privs)
  LOOP
    IF to_regclass(r.fq) IS NULL THEN
      RAISE NOTICE 'skip %: gone', r.fq;
      CONTINUE;
    END IF;
    EXECUTE format('ALTER %s %s OWNER TO bifrost', r.kind, r.fq);
    IF r.aw_privs IS NOT NULL THEN
      EXECUTE format('GRANT %s ON %s TO analytics_writer', r.aw_privs, r.fq);
    END IF;
  END LOOP;
END
$$;

DO $$
BEGIN
  IF (SELECT nspowner FROM pg_namespace WHERE nspname = 'features') = 'analytics_writer'::regrole THEN
    ALTER SCHEMA features OWNER TO bifrost;
    GRANT USAGE, CREATE ON SCHEMA features TO analytics_writer;
  END IF;
  IF (SELECT nspowner FROM pg_namespace WHERE nspname = 'research') = 'analytics_writer'::regrole THEN
    ALTER SCHEMA research OWNER TO bifrost;
    GRANT USAGE, CREATE ON SCHEMA research TO analytics_writer;
  END IF;
END
$$;

REVOKE SELECT ON raw_broker.executions_final FROM analytics_writer;

COMMIT;
