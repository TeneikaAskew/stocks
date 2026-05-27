-- ============================================================
-- STRAT ENGINE DATA VALIDATION (run before any training round)
-- ============================================================
-- Checks every strat_features_{tf} + strat_features_levels_{tf} table for:
--   - row counts per ticker
--   - date coverage gaps
--   - null counts on critical cols (strat_candle, OHLC, label-relevant)
--   - VIX same-day leak status
--   - class balance per ticker × TF
--   - schema/column drift between TF tables
--   - prev_strat_candle session contamination (still in source)
--   - forward-return populations
--   - 4h table existence
-- ============================================================

-- (1) Row counts per ticker × TF in strat_features_{tf}
SELECT '1m'  AS tf, ticker, count(*) AS n, count(DISTINCT bar_date) AS days,
       min(bar_date) AS first_day, max(bar_date) AS last_day
  FROM strat_features_1m WHERE strat_candle IS NOT NULL
 GROUP BY ticker
UNION ALL SELECT '5m', ticker, count(*), count(DISTINCT bar_date), min(bar_date), max(bar_date)
  FROM strat_features_5m WHERE strat_candle IS NOT NULL GROUP BY ticker
UNION ALL SELECT '15m', ticker, count(*), count(DISTINCT bar_date), min(bar_date), max(bar_date)
  FROM strat_features_15m WHERE strat_candle IS NOT NULL GROUP BY ticker
UNION ALL SELECT '30m', ticker, count(*), count(DISTINCT bar_date), min(bar_date), max(bar_date)
  FROM strat_features_30m WHERE strat_candle IS NOT NULL GROUP BY ticker
UNION ALL SELECT '60m', ticker, count(*), count(DISTINCT bar_date), min(bar_date), max(bar_date)
  FROM strat_features_60m WHERE strat_candle IS NOT NULL GROUP BY ticker
UNION ALL SELECT '4h',  ticker, count(*), count(DISTINCT bar_date), min(bar_date), max(bar_date)
  FROM strat_features_4h  WHERE strat_candle IS NOT NULL GROUP BY ticker
 ORDER BY 1, 2;

-- (2) Null-count audit on key columns per TF for IWM
SELECT '1m' AS tf,
       count(*) AS n,
       count(*) FILTER (WHERE strat_candle IS NULL) AS null_candle,
       count(*) FILTER (WHERE close IS NULL OR high IS NULL OR low IS NULL OR open IS NULL) AS null_ohlc,
       count(*) FILTER (WHERE volume IS NULL) AS null_volume,
       count(*) FILTER (WHERE rsi_14 IS NULL) AS null_rsi14,
       count(*) FILTER (WHERE ema_20 IS NULL) AS null_ema20,
       count(*) FILTER (WHERE vix_close IS NULL) AS null_vix,
       count(*) FILTER (WHERE total_gex IS NULL) AS null_gex,
       count(*) FILTER (WHERE prev_strat_candle IS NULL) AS null_prev,
       count(*) FILTER (WHERE bar_date IS NULL) AS null_bar_date
  FROM strat_features_1m WHERE ticker = 'IWM'
UNION ALL SELECT '5m', count(*),
       count(*) FILTER (WHERE strat_candle IS NULL),
       count(*) FILTER (WHERE close IS NULL OR high IS NULL OR low IS NULL OR open IS NULL),
       count(*) FILTER (WHERE volume IS NULL),
       count(*) FILTER (WHERE rsi_14 IS NULL),
       count(*) FILTER (WHERE ema_20 IS NULL),
       count(*) FILTER (WHERE vix_close IS NULL),
       count(*) FILTER (WHERE total_gex IS NULL),
       count(*) FILTER (WHERE prev_strat_candle IS NULL),
       count(*) FILTER (WHERE bar_date IS NULL)
  FROM strat_features_5m WHERE ticker = 'IWM'
UNION ALL SELECT '15m', count(*),
       count(*) FILTER (WHERE strat_candle IS NULL),
       count(*) FILTER (WHERE close IS NULL OR high IS NULL OR low IS NULL OR open IS NULL),
       count(*) FILTER (WHERE volume IS NULL),
       count(*) FILTER (WHERE rsi_14 IS NULL),
       count(*) FILTER (WHERE ema_20 IS NULL),
       count(*) FILTER (WHERE vix_close IS NULL),
       count(*) FILTER (WHERE total_gex IS NULL),
       count(*) FILTER (WHERE prev_strat_candle IS NULL),
       count(*) FILTER (WHERE bar_date IS NULL)
  FROM strat_features_15m WHERE ticker = 'IWM'
UNION ALL SELECT '30m', count(*),
       count(*) FILTER (WHERE strat_candle IS NULL),
       count(*) FILTER (WHERE close IS NULL OR high IS NULL OR low IS NULL OR open IS NULL),
       count(*) FILTER (WHERE volume IS NULL),
       count(*) FILTER (WHERE rsi_14 IS NULL),
       count(*) FILTER (WHERE ema_20 IS NULL),
       count(*) FILTER (WHERE vix_close IS NULL),
       count(*) FILTER (WHERE total_gex IS NULL),
       count(*) FILTER (WHERE prev_strat_candle IS NULL),
       count(*) FILTER (WHERE bar_date IS NULL)
  FROM strat_features_30m WHERE ticker = 'IWM'
UNION ALL SELECT '60m', count(*),
       count(*) FILTER (WHERE strat_candle IS NULL),
       count(*) FILTER (WHERE close IS NULL OR high IS NULL OR low IS NULL OR open IS NULL),
       count(*) FILTER (WHERE volume IS NULL),
       count(*) FILTER (WHERE rsi_14 IS NULL),
       count(*) FILTER (WHERE ema_20 IS NULL),
       count(*) FILTER (WHERE vix_close IS NULL),
       count(*) FILTER (WHERE total_gex IS NULL),
       count(*) FILTER (WHERE prev_strat_candle IS NULL),
       count(*) FILTER (WHERE bar_date IS NULL)
  FROM strat_features_60m WHERE ticker = 'IWM';

-- (3) VIX leak status — IWM 15m bar on a known day. s_vix should equal prior_vix, NOT same_day.
SELECT '15m'::text AS tf, bar_date,
       round(vix_close::numeric, 2) AS s_vix,
       round((SELECT close FROM market_data_daily WHERE ticker='^VIX' AND date = bar_date)::numeric, 2) AS same_day,
       round((SELECT close FROM market_data_daily WHERE ticker='^VIX' AND date = bar_date - 1)::numeric, 2) AS prior_day,
       CASE
         WHEN abs(vix_close - (SELECT close FROM market_data_daily WHERE ticker='^VIX' AND date = bar_date)) < 0.01
              THEN 'LEAK (same-day match)'
         WHEN abs(vix_close - (SELECT close FROM market_data_daily WHERE ticker='^VIX' AND date = bar_date - 1)) < 0.01
              THEN 'OK (prior-day match)'
         ELSE 'UNCLEAR'
       END AS status
  FROM strat_features_15m
 WHERE ticker = 'IWM' AND bar_date IN (DATE '2026-05-22', DATE '2026-05-15')
   AND ts::time IN (TIME '14:30:00', TIME '17:00:00')
 ORDER BY bar_date, ts;

-- (4) Class distribution per ticker × TF (does every class appear?)
SELECT '15m' AS tf, ticker, strat_candle, count(*) AS n
  FROM strat_features_15m WHERE strat_candle IS NOT NULL GROUP BY ticker, strat_candle
UNION ALL SELECT '60m', ticker, strat_candle, count(*)
  FROM strat_features_60m WHERE strat_candle IS NOT NULL GROUP BY ticker, strat_candle
 ORDER BY 1, 2, 3;

-- (5) Forward-return populations for IWM (last N bars of each TF should have null fwd cols)
SELECT '1m' AS tf,
       count(*) AS n,
       count(*) FILTER (WHERE fwd_ret_5bars_bps IS NULL) AS null_fwd5,
       count(*) FILTER (WHERE fwd_ret_60bars_bps IS NULL) AS null_fwd60
  FROM strat_features_1m WHERE ticker = 'IWM' AND strat_candle IS NOT NULL
UNION ALL SELECT '15m', count(*),
       count(*) FILTER (WHERE fwd_ret_5bars_bps IS NULL),
       count(*) FILTER (WHERE fwd_ret_60bars_bps IS NULL)
  FROM strat_features_15m WHERE ticker = 'IWM' AND strat_candle IS NOT NULL
UNION ALL SELECT '60m', count(*),
       count(*) FILTER (WHERE fwd_ret_5bars_bps IS NULL),
       count(*) FILTER (WHERE fwd_ret_60bars_bps IS NULL)
  FROM strat_features_60m WHERE ticker = 'IWM' AND strat_candle IS NOT NULL;

-- (6) Schema drift: column count per strat_features_{tf} table
SELECT table_name, count(*) AS column_count
  FROM information_schema.columns
 WHERE table_name IN ('strat_features_1m','strat_features_5m','strat_features_15m',
                      'strat_features_30m','strat_features_60m','strat_features_4h')
 GROUP BY table_name ORDER BY table_name;

-- (7) Schema drift on enrichment tables (15m=143 cols expected, others=183 with current_period)
SELECT table_name, count(*) AS column_count
  FROM information_schema.columns
 WHERE table_name LIKE 'strat_features_levels_%'
 GROUP BY table_name ORDER BY table_name;

-- (8) strat_features_4h existence + row count (we know it's 0; confirm table exists)
SELECT 'strat_features_4h_exists' AS check,
       count(*) AS n_columns
  FROM information_schema.columns WHERE table_name = 'strat_features_4h';

-- (9) Recent-data freshness for IWM (newest bar per TF)
SELECT '1m' AS tf, max(ts) AS latest_ts, max(bar_date) AS latest_date FROM strat_features_1m WHERE ticker='IWM'
UNION ALL SELECT '5m', max(ts), max(bar_date) FROM strat_features_5m WHERE ticker='IWM'
UNION ALL SELECT '15m', max(ts), max(bar_date) FROM strat_features_15m WHERE ticker='IWM'
UNION ALL SELECT '30m', max(ts), max(bar_date) FROM strat_features_30m WHERE ticker='IWM'
UNION ALL SELECT '60m', max(ts), max(bar_date) FROM strat_features_60m WHERE ticker='IWM';

-- (10) Trading-day gap check for IWM 15m (any expected business day with 0 bars?)
WITH days AS (
  SELECT generate_series(DATE '2026-01-02', DATE '2026-05-22', '1 day'::interval)::date AS d
), business AS (
  SELECT d FROM days WHERE EXTRACT(dow FROM d) NOT IN (0, 6)
), bars AS (
  SELECT bar_date, count(*) AS n FROM strat_features_15m
   WHERE ticker = 'IWM' AND bar_date >= '2026-01-02' AND bar_date <= '2026-05-22'
   GROUP BY bar_date
)
SELECT b.d AS missing_business_day
  FROM business b LEFT JOIN bars br ON b.d = br.bar_date
 WHERE br.bar_date IS NULL
 ORDER BY b.d LIMIT 30;
