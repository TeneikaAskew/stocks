-- ============================================================
-- P7 LEAKAGE + DATA INTEGRITY AUDIT
-- ============================================================

-- 1. Are n_test counts really per-ticker, or shared/truncated?
SELECT ticker, count(*) AS n,
       count(DISTINCT bar_date) AS distinct_days,
       min(bar_date) AS first_day, max(bar_date) AS last_day,
       count(*) FILTER (WHERE strat_candle IS NULL) AS null_curr
  FROM strat_features_5m
 WHERE bar_date >= '2026-01-01'
 GROUP BY ticker ORDER BY ticker;

-- 2. Train/test time boundary — verify no overlap, no leak
SELECT ticker,
       max(ts) FILTER (WHERE bar_date < '2026-01-01')  AS last_train_ts,
       min(ts) FILTER (WHERE bar_date >= '2026-01-01') AS first_test_ts,
       count(*) FILTER (WHERE bar_date < '2026-01-01') AS n_train,
       count(*) FILTER (WHERE bar_date >= '2026-01-01') AS n_test
  FROM strat_features_5m
 GROUP BY ticker ORDER BY ticker;

-- 3. Does vix_close use same-day close? (potential leak — VIX close is end-of-day,
--    but an intraday bar at 10am wouldn't yet know that day's VIX close)
--    Sample a few intraday rows and compare vix_close to ^VIX same-day close.
SELECT s.ticker, s.ts::time AS time_of_day, s.bar_date,
       round(s.vix_close::numeric, 2) AS s_vix,
       round((SELECT close FROM market_data_daily
               WHERE ticker = '^VIX' AND date = s.bar_date)::numeric, 2) AS daily_vix_close
  FROM strat_features_5m s
 WHERE s.ticker = 'IWM'
   AND s.bar_date IN (DATE '2026-05-22', DATE '2026-05-15', DATE '2026-05-01')
   AND s.ts::time IN (TIME '14:30', TIME '17:30', TIME '19:30')
 ORDER BY s.bar_date, s.ts;

-- 4. Gamma context: is it joined from PRIOR bar_date (no leak) or same-day (leak)?
SELECT s.ticker, s.bar_date,
       round(s.total_gex::numeric/1e9, 3) AS s_gex_b,
       round((SELECT total_gex FROM gamma_levels_eod
              WHERE ticker = s.ticker AND date = s.bar_date)::numeric/1e9, 3) AS same_day_gex_b,
       round((SELECT total_gex FROM gamma_levels_eod
              WHERE ticker = s.ticker AND date = s.bar_date - 1)::numeric/1e9, 3) AS prior_day_gex_b
  FROM strat_features_5m s
 WHERE s.ticker = 'IWM' AND s.bar_date = '2026-05-22' AND s.ts::time = TIME '14:30';

-- 5. Forward return columns must NOT exist in feature list — verify they're populated
--    (so we know the columns are there to be excluded; if NULL, our drop-set is fine but redundant)
SELECT ticker, count(*) AS n,
       count(fwd_close_5bars)   AS has_fwd5,
       count(fwd_ret_5bars_bps) AS has_fwd5_bps
  FROM strat_features_5m
 WHERE bar_date >= '2026-01-01' AND bar_date <= '2026-05-15'
 GROUP BY ticker ORDER BY ticker;

-- 6. Were any test-set rows also seen during training? (Should be 0 — paranoid sanity)
SELECT count(*) AS train_test_overlap
  FROM strat_features_5m a
  JOIN strat_features_5m b
    ON a.ticker = b.ticker AND a.ts = b.ts
 WHERE a.bar_date < '2026-01-01' AND b.bar_date >= '2026-01-01';

-- 7. Class balance — is the OOS test set radically different from train?
SELECT 'train' AS split, ticker, strat_candle, count(*) AS n
  FROM strat_features_5m
 WHERE bar_date < '2026-01-01' AND strat_candle IS NOT NULL
 GROUP BY ticker, strat_candle
UNION ALL
SELECT 'test' AS split, ticker, strat_candle, count(*) AS n
  FROM strat_features_5m
 WHERE bar_date >= '2026-01-01' AND strat_candle IS NOT NULL
 GROUP BY ticker, strat_candle
 ORDER BY ticker, split, strat_candle;
