-- Every (ticker, month) that holds 1-min bars in market_data_intraday: the
-- input list for the re-framing migration
--   python -m gcp.fetchers.fetch_alphavantage_intraday --replace-months <list>
-- (CLAUDE.md 3.9). Read-only. Run with --timeout 600 (measured 333 s) and
-- check the summary is not truncated (39,311 rows vs the 50,000 cap).
--
-- Loose index scan (CLAUDE.md 3.8): one descent of (ticker, interval, ts) per
-- ticker, then one per month found, never a scan of the rows. Measured
-- 2026-09-26: 39,311 pairs over 2,590 tickers in 333 s. A classifier that
-- reads every row timed out at 540 s on 1/16 of the catch-all partition.
--
-- A month is keyed by (ts - 2 h) in UTC, the same framing as
-- fetch_alphavantage_intraday.month_replace_window: [M-01 02:00Z, M+1-01 02:00Z)
-- holds month M in both timestamp conventions.
WITH RECURSIVE tk AS (
    SELECT min(ticker) AS t FROM market_data_intraday
    UNION ALL
    SELECT (SELECT min(ticker) FROM market_data_intraday WHERE ticker > tk.t)
      FROM tk WHERE tk.t IS NOT NULL
), m AS (
    SELECT tk.t AS ticker,
           (SELECT min(ts) FROM market_data_intraday
             WHERE ticker = tk.t AND interval = '1min') AS ts
      FROM tk WHERE tk.t IS NOT NULL
    UNION ALL
    SELECT m.ticker,
           (SELECT min(i.ts) FROM market_data_intraday i
             WHERE i.ticker = m.ticker AND i.interval = '1min'
               AND i.ts >= ((date_trunc('month', (m.ts AT TIME ZONE 'UTC') - interval '2 hours')
                             + interval '1 month' + interval '2 hours') AT TIME ZONE 'UTC'))
      FROM m WHERE m.ts IS NOT NULL
)
SELECT ticker, to_char((ts AT TIME ZONE 'UTC') - interval '2 hours', 'YYYY-MM') AS month
  FROM m
 WHERE ts IS NOT NULL
 ORDER BY 1, 2
