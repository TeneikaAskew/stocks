-- Phase 1 baseline forward-return distributions.
-- For each (ticker, horizon), sample RTH bars and compute fwd-return stats.
-- This gives us the noise floor: what's the unconditional probability
-- of "price up in N bars" so Phase 2 hit-rates have something to beat.

WITH spy_fwd AS (
  SELECT
    'SPY' AS ticker,
    ts,
    close,
    LEAD(close, 5)  OVER w AS c5,
    LEAD(close, 15) OVER w AS c15,
    LEAD(close, 30) OVER w AS c30,
    LEAD(close, 60) OVER w AS c60,
    LEAD(close, 240) OVER w AS c240
  FROM market_data_intraday_spy
  WHERE interval = '1min'
    AND (ts AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '15:45'
  WINDOW w AS (PARTITION BY date_trunc('day', ts AT TIME ZONE 'America/New_York') ORDER BY ts)
),
iwm_fwd AS (
  SELECT
    'IWM' AS ticker, ts, close,
    LEAD(close, 5) OVER w AS c5,
    LEAD(close, 15) OVER w AS c15,
    LEAD(close, 30) OVER w AS c30,
    LEAD(close, 60) OVER w AS c60,
    LEAD(close, 240) OVER w AS c240
  FROM market_data_intraday_iwm
  WHERE interval = '1min'
    AND (ts AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '15:45'
  WINDOW w AS (PARTITION BY date_trunc('day', ts AT TIME ZONE 'America/New_York') ORDER BY ts)
),
qqq_fwd AS (
  SELECT
    'QQQ' AS ticker, ts, close,
    LEAD(close, 5) OVER w AS c5,
    LEAD(close, 15) OVER w AS c15,
    LEAD(close, 30) OVER w AS c30,
    LEAD(close, 60) OVER w AS c60,
    LEAD(close, 240) OVER w AS c240
  FROM market_data_intraday_qqq
  WHERE interval = '1min'
    AND (ts AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '15:45'
  WINDOW w AS (PARTITION BY date_trunc('day', ts AT TIME ZONE 'America/New_York') ORDER BY ts)
),
combined AS (
  SELECT * FROM spy_fwd
  UNION ALL SELECT * FROM iwm_fwd
  UNION ALL SELECT * FROM qqq_fwd
)
SELECT
  ticker,
  count(*) FILTER (WHERE c5 IS NOT NULL) AS n_5m,
  -- 5-min horizon
  round((avg((c5-close)/close)*10000)::numeric, 2)  AS mean_5m_bps,
  round((stddev((c5-close)/close)*10000)::numeric, 2) AS std_5m_bps,
  round(100.0*(count(*) FILTER (WHERE c5 > close))::numeric / NULLIF(count(*) FILTER (WHERE c5 IS NOT NULL),0), 2) AS pct_up_5m,
  -- 15-min
  round((avg((c15-close)/close)*10000)::numeric, 2)  AS mean_15m_bps,
  round((stddev((c15-close)/close)*10000)::numeric, 2) AS std_15m_bps,
  round(100.0*(count(*) FILTER (WHERE c15 > close))::numeric / NULLIF(count(*) FILTER (WHERE c15 IS NOT NULL),0), 2) AS pct_up_15m,
  -- 30-min
  round((avg((c30-close)/close)*10000)::numeric, 2)  AS mean_30m_bps,
  round(100.0*(count(*) FILTER (WHERE c30 > close))::numeric / NULLIF(count(*) FILTER (WHERE c30 IS NOT NULL),0), 2) AS pct_up_30m,
  -- 60-min
  round((avg((c60-close)/close)*10000)::numeric, 2)  AS mean_60m_bps,
  round(100.0*(count(*) FILTER (WHERE c60 > close))::numeric / NULLIF(count(*) FILTER (WHERE c60 IS NOT NULL),0), 2) AS pct_up_60m,
  -- 240-min (4-hour, ~EOD)
  round((avg((c240-close)/close)*10000)::numeric, 2)  AS mean_240m_bps,
  round(100.0*(count(*) FILTER (WHERE c240 > close))::numeric / NULLIF(count(*) FILTER (WHERE c240 IS NOT NULL),0), 2) AS pct_up_240m
FROM combined
GROUP BY ticker
ORDER BY ticker;
