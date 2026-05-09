-- G.P1.10 verification — sibling 2 of 3
-- See gcp/queries/verify_brief_bias_coverage.sql for context + dispatch
-- instructions.

-- Roll-up: any (ticker, day) bucket with a NULL brief_bias since
-- the PR-#310 land date (2026-05-09)? Empty result set is the
-- acceptance signal.
SELECT alert_date, ticker, COUNT(*) AS n_null_bias_alerts
  FROM signal_alerts
 WHERE alert_date >= '2026-05-12'  -- first weekday post-fix-land
   AND ticker IN ('SPY','IWM','QQQ')
   AND brief_bias IS NULL
 GROUP BY alert_date, ticker
 ORDER BY alert_date, ticker
