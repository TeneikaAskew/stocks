-- P7 reverification of P5's "flip_cross PUT × FTFC-DOWN at 15m, live=76.7%"
-- finding. The original live audit claimed 76.7% hit rate; P5's 10-year
-- backfill on `gamma_events` found only 14 PUT events with hit_15m = 33.3%.
-- This query runs the same calculation against the new bar-level dataset.
--
-- A "flip-cross PUT" bar at 5m: prev_close > flip_price AND close < flip_price
-- (price crossed DOWN through the dealer-flip price during this bar).
-- "FTFC-DOWN" approximation: 60m close < flip_price (higher-TF agreement).
--
-- We join 5m to 60m on the matching higher-TF time bucket so both sides
-- come from the same bar-level foundation. fwd_3bars (15-min horizon at
-- 5m TF) is the "15m" equivalent the live audit cited.
WITH flip_5m AS (
  SELECT
    s.ticker,
    s.ts,
    s.bar_date,
    s.close,
    s.flip_price,
    LAG(s.close) OVER (PARTITION BY s.ticker ORDER BY s.ts) AS prev_close,
    s.fwd_ret_5bars_bps,
    s.fwd_ret_15bars_bps,
    date_trunc('hour', s.ts) AS hour_bucket
  FROM strat_features_5m s
  WHERE s.flip_price IS NOT NULL
),
crosses AS (
  SELECT *
  FROM flip_5m
  WHERE prev_close IS NOT NULL
    AND prev_close > flip_price       -- previous bar above flip
    AND close < flip_price            -- this bar below flip (PUT-aligned cross)
),
joined AS (
  SELECT
    c.ticker,
    c.ts,
    c.bar_date,
    c.close,
    c.flip_price,
    c.fwd_ret_5bars_bps,
    c.fwd_ret_15bars_bps,
    h.close      AS close_60m,
    h.flip_price AS flip_60m
  FROM crosses c
  LEFT JOIN strat_features_60m h
    ON h.ticker = c.ticker AND h.ts = c.hour_bucket
)
SELECT
  ticker,
  count(*)                                                            AS n_flip_put_5m,
  count(*) FILTER (WHERE close_60m < flip_60m)                        AS n_ftfc_down,
  round(avg(CASE WHEN fwd_ret_5bars_bps  < 0 THEN 1.0 ELSE 0 END)::numeric * 100, 1) AS hit_pct_down_fwd5,
  round(avg(CASE WHEN fwd_ret_15bars_bps < 0 THEN 1.0 ELSE 0 END)::numeric * 100, 1) AS hit_pct_down_fwd15,
  round(avg(fwd_ret_5bars_bps)::numeric, 2)                           AS mean_bps_fwd5,
  round(avg(fwd_ret_15bars_bps)::numeric, 2)                          AS mean_bps_fwd15,
  round(avg(CASE WHEN close_60m < flip_60m AND fwd_ret_15bars_bps < 0 THEN 1.0
                 WHEN close_60m < flip_60m                            THEN 0
                 ELSE NULL END)::numeric * 100, 1)                    AS hit_pct_ftfc_down_fwd15
FROM joined
GROUP BY ticker
ORDER BY ticker;
