-- Classify each (ticker, session) in market_data_intraday by timestamp
-- convention, without trusting any reference table.
--
-- CLAUDE.md 3.9: the table holds two conventions under the same
-- data_source. Some rows are true UTC instants; others are ET wall-clock
-- stored naively as UTC. Anything that reads bars by instant (the replay
-- harness, walk-forward, feature builders) silently shifts the second kind
-- by 4-5 hours.
--
-- Test: the first 30 minutes of RTH carry far more volume than premarket
-- or 13:30 ET. So compare the volume in the 30 minutes after 09:30 read as
-- a true instant against the 30 minutes after raw clock label 09:30.
--   ratio = v_et_label / v_true_instant
--   < 0.2  -> true-UTC     (opening spike sits at the real instant)
--   > 1.5  -> ET-as-UTC    (opening spike sits at the raw 09:30 label)
--   else   -> mixed        (both writers touched the session; treat as corrupt)
--
-- Validated 2026-09-25 against live signal prices: on 2026-09-24 SPY and
-- QQQ classify ET-as-UTC, and their raw-label bars match live
-- price_at_signal within ~3 bp while the true-instant reading is 25-64 bp
-- off. Over 2024-01-01..2026-09-25 (SPY, QQQ, IWM) the ratio is bimodal:
-- 1,870 sessions < 0.2, 34 > 1.5, 71 in between (mostly IWM since 2026-04).
--
-- Why not compare against market_data_daily: its closes differ from the
-- intraday bars by ~190 bp on 2024 dates under BOTH readings (consistent
-- with dividend adjustment), so it cannot arbitrate.
--
-- Scope: SPY, QQQ, IWM only. Reading every row of every ticker does not fit a
-- statement timeout (1/16 of the catch-all partition alone timed out at
-- 540 s). The all-ticker check after the re-framing migration is
--   python -m gcp.fetchers.fetch_alphavantage_intraday --verify-months <list>
-- with the list regenerated from the table by list_intraday_ticker_months.sql,
-- so a month the migration manifest omitted is checked too (Codex P1 on #1185).
--
-- Usage (read-only):
--   ./scripts/db_query_cr.sh -f gcp/queries/classify_intraday_ts_convention.sql --timeout 300
WITH per_session AS (
    -- One pass over the rows (no per-session subqueries: that shape timed
    -- out at 300 s; this one ran in 84 s on 2026-09-25, CLAUDE.md 3.8).
    -- A missing window sums to NULL; the CASE below coalesces it to 0 so a
    -- session with no bars at one reading is not misread as 'mixed'.
    -- d is the raw UTC-label date, which is the session date under both
    -- conventions because 09:30 ET falls on the same calendar date in UTC.
    SELECT ticker,
           (ts AT TIME ZONE 'UTC')::date AS d,
           sum(volume) FILTER (
               WHERE ts >= ((ts AT TIME ZONE 'UTC')::date + time '09:30') AT TIME ZONE 'America/New_York'
                 AND ts <  ((ts AT TIME ZONE 'UTC')::date + time '10:00') AT TIME ZONE 'America/New_York'
           ) AS v_true_instant,
           sum(volume) FILTER (
               WHERE (ts AT TIME ZONE 'UTC')::time >= time '09:30'
                 AND (ts AT TIME ZONE 'UTC')::time <  time '10:00'
           ) AS v_et_label
    FROM market_data_intraday
    WHERE ticker IN ('SPY', 'QQQ', 'IWM')
      AND interval = '1min'
      AND ts >= '2024-01-01 00:00+00'
    GROUP BY 1, 2
)
SELECT ticker, d AS session_date, v_true_instant, v_et_label,
       CASE
         WHEN coalesce(v_true_instant, 0) + coalesce(v_et_label, 0) = 0 THEN 'no-open-bars'
         WHEN coalesce(v_true_instant, 0) = 0 THEN 'ET-as-UTC'
         -- numeric: volume is BIGINT, and integer division turned a 0.5
         -- ratio into 0 (true-UTC) and 1.8 into 1 (mixed) (Codex P1 on #1185).
         WHEN coalesce(v_et_label, 0)::numeric / v_true_instant > 1.5 THEN 'ET-as-UTC'
         WHEN coalesce(v_et_label, 0)::numeric / v_true_instant < 0.2 THEN 'true-UTC'
         ELSE 'mixed'
       END AS convention
FROM per_session
WHERE extract(isodow FROM d) < 6
ORDER BY ticker, d
