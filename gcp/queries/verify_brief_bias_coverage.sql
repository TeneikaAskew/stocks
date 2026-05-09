-- Issue G.P1.10 verification — confirm brief_bias is now populated on
-- every (ticker, day) bucket where the brief published, after Track D's
-- TZ-bug fix in PR #279 + Track A's G.P0.1 fetcher unfreeze in PR #321.
--
-- Pre-fix audit found brief_bias populated only on 5/7 (PR #310 closed
-- the investigation, PR #279 fixed the underlying TZ bug). Track C's
-- verification is to re-run the same SQL from track-C.md result_006
-- against post-fix data and confirm coverage is complete.
--
-- Usage:
--   gh workflow run db-query.yml \
--     -f sql_file=gcp/queries/verify_brief_bias_coverage.sql
--
-- Run weekly until coverage stays at 100% for 2 consecutive weeks, then
-- close G.P1.10 verification side. If any (ticker, day) bucket shows
-- brief_bias=NULL post-2026-05-12 (first weekday after PR #310 +
-- G.P0.1 land), open a follow-up against Track D — the lookup chain
-- still has a hole.

-- 1) Coverage per (ticker, day) bucket — should be 100% null=0 post-fix
SELECT alert_date,
       ticker,
       COUNT(*)                                              AS n_alerts,
       COUNT(brief_bias)                                     AS n_with_bias,
       COUNT(*) - COUNT(brief_bias)                          AS n_null_bias,
       ROUND(100.0 * COUNT(brief_bias)
             / NULLIF(COUNT(*), 0)::numeric, 1)              AS coverage_pct,
       COUNT(*) FILTER (WHERE brief_alignment = 'aligned')   AS n_aligned,
       COUNT(*) FILTER (WHERE brief_alignment = 'opposed')   AS n_opposed,
       COUNT(*) FILTER (WHERE brief_alignment IS NULL)       AS n_alignment_null
FROM signal_alerts
WHERE alert_date >= CURRENT_DATE - INTERVAL '14 days'
  AND ticker IN ('SPY','IWM','QQQ')
GROUP BY alert_date, ticker
ORDER BY alert_date DESC, ticker;

-- 2) Roll-up: any (ticker, day) bucket with a NULL brief_bias since
-- the PR-#310 land date (2026-05-09)? Empty result set is the
-- acceptance signal.
SELECT alert_date, ticker, COUNT(*) AS n_null_bias_alerts
  FROM signal_alerts
 WHERE alert_date >= '2026-05-12'  -- first weekday post-fix-land
   AND ticker IN ('SPY','IWM','QQQ')
   AND brief_bias IS NULL
 GROUP BY alert_date, ticker
 ORDER BY alert_date, ticker;

-- 3) brief_bias distribution — should reflect the actual brief
-- direction calls, not 'mixed' / NULL on every row
SELECT brief_bias,
       COUNT(*)                                                  AS n,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER ()::numeric, 1)
                                                                 AS pct_of_total
  FROM signal_alerts
 WHERE alert_date >= CURRENT_DATE - INTERVAL '14 days'
   AND ticker IN ('SPY','IWM','QQQ')
 GROUP BY brief_bias
 ORDER BY n DESC;
