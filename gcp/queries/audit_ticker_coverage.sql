-- Per-ticker date-coverage audit for market_data_daily.
--
-- Reports for every ticker:
--   min_date / max_date — actual range present in the table
--   row_count           — bars stored
--   tail_gap_days       — (most-recent ticker's max_date) - this ticker's max_date.
--                         0 = up-to-date; 1-2 = lagging one fetch cycle;
--                         > 7 = stale; > 365 = likely delisted.
--   head_gap_days       — this ticker's min_date - (earliest ticker's min_date).
--                         0 = full history; > 0 = IPO'd N days later than the
--                         earliest ticker in the table (or never backfilled).
--   rows_with_close     — sanity check; should equal row_count for healthy data.
--
-- Used by the time-frame coverage audit to identify head-backfill and
-- tail-backfill candidates, and to confirm convergence after a backfill run.
WITH stats AS (
    SELECT
        ticker,
        MIN(date)                                AS min_date,
        MAX(date)                                AS max_date,
        COUNT(*)                                 AS row_count,
        COUNT(*) FILTER (WHERE close IS NOT NULL) AS rows_with_close
    FROM market_data_daily
    GROUP BY ticker
),
universe AS (
    SELECT
        MIN(min_date) AS earliest_date,
        MAX(max_date) AS latest_date
    FROM stats
)
SELECT
    s.ticker,
    s.min_date,
    s.max_date,
    s.row_count,
    (u.latest_date - s.max_date) AS tail_gap_days,
    (s.min_date    - u.earliest_date) AS head_gap_days,
    s.rows_with_close
FROM stats s, universe u
ORDER BY tail_gap_days DESC, head_gap_days DESC, ticker;
