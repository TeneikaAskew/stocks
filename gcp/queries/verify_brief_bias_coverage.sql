-- Issue G.P1.10 verification — confirm brief_bias is now populated on
-- every (ticker, day) bucket where the brief published, after Track D's
-- TZ-bug fix in PR #279 + Track A's G.P0.1 fetcher unfreeze in PR #321.
--
-- The db-query.yml workflow's `sql_file` mode treats the entire file
-- as ONE statement (per CLAUDE.md docs and `gcp/queries/run_query.py`).
-- Multi-SELECT files would fail with a multi-command syntax error.
-- Codex review on PR #357 caught this; the file was split into three
-- siblings. Pick the one you want to dispatch:
--
--   gcp/queries/verify_brief_bias_coverage.sql        — this (rollup #1)
--   gcp/queries/verify_brief_bias_post_fix_holes.sql  — rollup #2
--   gcp/queries/verify_brief_bias_distribution.sql    — rollup #3
--
-- Or to run all three in one workflow dispatch, use the `sql` inline
-- input — the workflow splits inline SQL on `;` and runs each
-- statement separately:
--
--   gh workflow run db-query.yml \
--     -f sql="$(cat gcp/queries/verify_brief_bias_coverage.sql \
--                 gcp/queries/verify_brief_bias_post_fix_holes.sql \
--                 gcp/queries/verify_brief_bias_distribution.sql)"
--
-- Run weekly until coverage stays at 100% for 2 consecutive weeks, then
-- close G.P1.10 verification side.

-- Coverage per (ticker, day) bucket — should be 100% null=0 post-fix
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
ORDER BY alert_date DESC, ticker
