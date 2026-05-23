-- Empirical validation of Track 3 gamma proximity direction mapping.
-- For each (ticker, snapshot_date) over the last 60 trading days, find
-- the King strike (highest |net_gamma_per_strike|), then walk that day's
-- 1-min intraday bars to detect King-approach events (price first enters
-- 0.5% of the King), then compute the forward 15-minute price change.
--
-- "Hit" rate semantics (validates the direction mapping):
--   approach_from_below = PUT bias → "hit" if price LOWER 15m later
--   approach_from_above = CALL bias → "hit" if price HIGHER 15m later
--
-- A hit rate well above 50% validates the directional mapping. ~50%
-- means it's noise. Significantly below 50% means we should invert.

WITH agg AS (
    SELECT
        ticker, snapshot_date, strike,
        SUM(CASE WHEN option_type='calls' THEN gamma*open_interest ELSE 0 END)
        - SUM(CASE WHEN option_type='puts' THEN gamma*open_interest ELSE 0 END) AS net_gamma
    FROM etf_options_snapshots
    WHERE ticker IN ('SPY','IWM','QQQ')
      AND data_source='alphavantage'
      AND snapshot_date >= current_date - interval '90 days'
      AND gamma IS NOT NULL AND open_interest IS NOT NULL
    GROUP BY ticker, snapshot_date, strike
),
kings AS (
    SELECT DISTINCT ON (ticker, snapshot_date)
        ticker, snapshot_date, strike AS king_strike, net_gamma
    FROM agg
    WHERE abs(net_gamma) > 0
    ORDER BY ticker, snapshot_date, abs(net_gamma) DESC
),
near_bars AS (
    -- Every intraday RTH bar that's within 0.5% of the day's king
    SELECT
        k.ticker, k.snapshot_date, k.king_strike,
        i.ts AS approach_ts,
        i.close AS approach_price,
        (i.close - k.king_strike) / k.king_strike AS approach_dist,
        LAG(i.close) OVER (PARTITION BY k.ticker, k.snapshot_date ORDER BY i.ts) AS prev_close
    FROM kings k
    JOIN market_data_intraday i
      ON i.ticker = k.ticker
     AND i.ts::date = k.snapshot_date
     AND i.interval = '1min'
     AND (i.ts AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '15:45'
    WHERE abs((i.close - k.king_strike) / k.king_strike) <= 0.005
),
first_touches AS (
    -- Only the FIRST bar of each contiguous approach run — i.e. transition
    -- from outside-0.5% (or NULL prev) into within-0.5%. Otherwise every
    -- minute the price stays near the king would count as a new approach.
    SELECT *
    FROM near_bars
    WHERE prev_close IS NULL
       OR abs((prev_close - king_strike) / king_strike) > 0.005
),
with_forward AS (
    -- Forward 15-min close from same day's intraday data
    SELECT
        f.*,
        (SELECT i2.close FROM market_data_intraday i2
         WHERE i2.ticker = f.ticker
           AND i2.interval = '1min'
           AND i2.ts >= f.approach_ts + interval '15 minutes'
         ORDER BY i2.ts ASC LIMIT 1) AS price_15m_later
    FROM first_touches f
)
SELECT
    ticker,
    CASE WHEN approach_dist < 0 THEN 'below_king→PUT bias'
         ELSE 'above_king→CALL bias' END AS approach_side,
    count(*) AS n_approaches,
    -- Hit = price moved in predicted direction
    round(100.0 * avg(
        CASE
          WHEN approach_dist < 0 AND price_15m_later < approach_price THEN 1
          WHEN approach_dist >= 0 AND price_15m_later > approach_price THEN 1
          ELSE 0
        END
    )::numeric, 1) AS hit_rate_15m_pct,
    -- Magnitude — average signed 15m return in direction of bias
    round((avg(
        CASE
          WHEN approach_dist < 0 THEN -(price_15m_later - approach_price) / approach_price
          ELSE  (price_15m_later - approach_price) / approach_price
        END
    ) * 10000)::numeric, 1) AS avg_15m_move_bps_in_bias_direction
FROM with_forward
WHERE price_15m_later IS NOT NULL
GROUP BY ticker, approach_side
ORDER BY ticker, approach_side;
