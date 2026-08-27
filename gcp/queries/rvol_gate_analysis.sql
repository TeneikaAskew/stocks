-- RVOL-gate reconstruction analysis behind the 2026-08-27 enforcement
-- decision (docs/audits/LIVE_PERFORMANCE_REVIEW_2026-08-27.md §3).
-- Checked in so the verdict is reproducible and adversarially sliceable
-- (Codex P2, PR #802).
--
-- Cohort: resolved (exit_return_pct IS NOT NULL), non-replay
-- (run_kind IS DISTINCT FROM 'replay') fires with a stored fire-time
-- rvol; 2,918 rows spanning 2026-03-19 .. 2026-08-27 at analysis time.
-- Verdict reconstruction: rvol >= 1.0 -> 'pass' else 'below', matching
-- gcp/signal_monitor.py:rvol_gate_verdict at the production
-- rvol_gate_min = 1.0. (Zero NULL/NaN rvol rows existed in the cohort;
-- had any existed they belong in 'below'.)
--
-- NOTE: three independent statements. `-f` sends a file as ONE statement,
-- so run each via -q, or all at once:
--   ./scripts/db_query_cr.sh -q "$(grep -v '^--' gcp/queries/rvol_gate_analysis.sql)"
--
-- 1. Monthly performance by reconstructed verdict (the sign-flip table).
SELECT date_trunc('month', alert_date)::date AS mth,
       CASE WHEN rvol >= 1.0 THEN 'pass' ELSE 'below' END AS verdict,
       count(*) AS n,
       count(*) FILTER (WHERE exit_return_pct > 0) AS wins,
       round(avg(exit_return_pct)::numeric, 3) AS avg_ret,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY exit_return_pct))::numeric, 3) AS med_ret
FROM signal_alerts
WHERE rvol IS NOT NULL
  AND exit_return_pct IS NOT NULL
  AND run_kind IS DISTINCT FROM 'replay'
GROUP BY 1, 2
ORDER BY 1, 2;

-- 2. Dose-response across RVOL bands (a real entry filter should show
--    returns rising with the band; observed: flat 49-54% win rates and
--    the >=2.0 band worst at -0.028%).
SELECT CASE WHEN rvol >= 2.0 THEN 'd:>=2.0'
            WHEN rvol >= 1.5 THEN 'c:1.5-2'
            WHEN rvol >= 1.0 THEN 'b:1.0-1.5'
            WHEN rvol >= 0.5 THEN 'a:0.5-1.0'
            ELSE 'z:<0.5' END AS rvol_band,
       count(*) AS n,
       count(*) FILTER (WHERE exit_return_pct > 0) AS wins,
       round((100.0 * count(*) FILTER (WHERE exit_return_pct > 0) / count(*))::numeric, 1) AS win_pct,
       round(avg(exit_return_pct)::numeric, 3) AS avg_ret
FROM signal_alerts
WHERE rvol IS NOT NULL
  AND exit_return_pct IS NOT NULL
  AND run_kind IS DISTINCT FROM 'replay'
GROUP BY 1
ORDER BY 1;

-- 3. Composition slices (strategy/direction/hour) x verdict — the
--    adversarial cut: does any stable sub-population support enforcement
--    that the aggregate hides? (Direction and fire-hour are stored on
--    every row; strategy composition via conditions/strategy_agreement
--    is JSONB and best sliced ad hoc.)
SELECT ticker,
       direction,
       extract(hour FROM alert_ts AT TIME ZONE 'America/New_York')::int AS fire_hour_et,
       CASE WHEN rvol >= 1.0 THEN 'pass' ELSE 'below' END AS verdict,
       count(*) AS n,
       count(*) FILTER (WHERE exit_return_pct > 0) AS wins,
       round(avg(exit_return_pct)::numeric, 3) AS avg_ret
FROM signal_alerts
WHERE rvol IS NOT NULL
  AND exit_return_pct IS NOT NULL
  AND run_kind IS DISTINCT FROM 'replay'
GROUP BY 1, 2, 3, 4
HAVING count(*) >= 20
ORDER BY 1, 2, 3, 4;
