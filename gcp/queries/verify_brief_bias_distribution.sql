-- G.P1.10 verification — sibling 3 of 3
-- See gcp/queries/verify_brief_bias_coverage.sql for context + dispatch
-- instructions.

-- brief_bias distribution — should reflect the actual brief direction
-- calls, not 'mixed' / NULL on every row.
SELECT brief_bias,
       COUNT(*)                                                  AS n,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER ()::numeric, 1)
                                                                 AS pct_of_total
  FROM signal_alerts
 WHERE alert_date >= CURRENT_DATE - INTERVAL '14 days'
   AND ticker IN ('SPY','IWM','QQQ')
 GROUP BY brief_bias
 ORDER BY n DESC
