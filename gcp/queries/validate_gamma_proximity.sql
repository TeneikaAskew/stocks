-- Empirical validation of Track 3 gamma proximity direction mapping.
-- For each (ticker, snapshot_date) over the last 90 days, find the King
-- strike (highest |net_gamma_per_strike|), then walk that day's 1-min
-- intraday bars to detect King-approach events (price first enters 0.5%
-- of the King), then compute the forward 15-minute price change.
--
-- HISTORICAL CONTEXT — read before reinterpreting these labels:
--
--   This query was the INITIAL validation that disproved the
--   barrier/rejection thesis baked into the original mapping (PUT from
--   below, CALL from above). Results showed the OPPOSITE — price drifts
--   TOWARD the king (magnet effect), not away. The mapping was inverted
--   in commit a4d3153 (2026-05-23). The production direction is now:
--
--     below_king → CALL   (magnet ↑ — expect continuation up to king)
--     above_king → PUT    (magnet ↓ — expect continuation down to king)
--
--   The "PUT bias from below" / "CALL bias from above" labels and the
--   CASE-WHEN hit predicates below still encode the OLD (pre-inversion)
--   hypothesis — they show the hit rate AGAINST the new production
--   mapping. A "high" number here (~75%) means the OLD bias was correct
--   ~25% of the time and therefore the NEW (inverted) bias is correct
--   ~75% of the time. Flipping the labels would also be valid; we leave
--   them as-is so the historical PR / audit context remains greppable.
--
-- See:
--   - lib/strategies/gamma_proximity.py             — production mapping
--   - docs/audits/gamma_proximity_2026-05-23.md     — full backtest + FTFC results
--
-- This query covers KINGS ONLY. Gate / flip × FTFC validation lives in
-- the audit doc (the queries were dispatched ad-hoc via db-query.yml
-- and aren't committed because the FTFC filter is a runtime concern,
-- not a per-row schema property).

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
day_bars AS (
    -- All RTH bars for the kings' days, with forward 15m + 60m close +
    -- prev close computed via window functions in a single partitioned
    -- pass. LEAD(_, N) assumes 1-min bars are contiguous within RTH
    -- (true for liquid ETFs SPY/IWM/QQQ; missing bars would make the
    -- N-min horizon slightly off but the analysis aggregates over many
    -- touches so noise averages out).
    SELECT
        k.ticker, k.snapshot_date, k.king_strike,
        i.ts AS bar_ts,
        i.close AS bar_close,
        (i.close - k.king_strike) / k.king_strike AS dist,
        LAG(i.close) OVER w AS prev_close,
        LEAD(i.close, 15) OVER w AS price_15m_later,
        LEAD(i.close, 60) OVER w AS price_60m_later
    FROM kings k
    JOIN market_data_intraday i
      ON i.ticker = k.ticker
     AND i.ts::date = k.snapshot_date
     AND i.interval = '1min'
     AND (i.ts AT TIME ZONE 'America/New_York')::time BETWEEN '09:30' AND '15:45'
    WINDOW w AS (PARTITION BY k.ticker, k.snapshot_date ORDER BY i.ts)
),
first_touches AS (
    -- Only the FIRST bar of each contiguous approach run — i.e. transition
    -- from outside-0.5% (or NULL prev) into within-0.5%. Without this
    -- every minute the price stays near the king would count as a new
    -- approach and dominate the sample with autocorrelated dupes.
    SELECT *
    FROM day_bars
    WHERE abs(dist) <= 0.005
      AND (prev_close IS NULL
           OR abs((prev_close - king_strike) / king_strike) > 0.005)
)
SELECT
    ticker,
    CASE WHEN dist < 0 THEN 'below_king→PUT bias'
         ELSE 'above_king→CALL bias' END AS approach_side,
    count(*) AS n_approaches,
    -- Hit = price moved in predicted direction within 15m
    round(100.0 * avg(
        CASE
          WHEN dist < 0  AND price_15m_later IS NOT NULL AND price_15m_later < bar_close THEN 1
          WHEN dist >= 0 AND price_15m_later IS NOT NULL AND price_15m_later > bar_close THEN 1
          WHEN price_15m_later IS NULL THEN NULL  -- end-of-day touches drop from denom
          ELSE 0
        END
    )::numeric, 1) AS hit_rate_15m_pct,
    -- Hit rate over 60m (longer-horizon validation)
    round(100.0 * avg(
        CASE
          WHEN dist < 0  AND price_60m_later IS NOT NULL AND price_60m_later < bar_close THEN 1
          WHEN dist >= 0 AND price_60m_later IS NOT NULL AND price_60m_later > bar_close THEN 1
          WHEN price_60m_later IS NULL THEN NULL
          ELSE 0
        END
    )::numeric, 1) AS hit_rate_60m_pct,
    -- Magnitude — average signed 15m return in direction of bias (bps)
    round((avg(
        CASE
          WHEN dist < 0  AND price_15m_later IS NOT NULL
            THEN -(price_15m_later - bar_close) / bar_close
          WHEN dist >= 0 AND price_15m_later IS NOT NULL
            THEN  (price_15m_later - bar_close) / bar_close
          ELSE NULL
        END
    ) * 10000)::numeric, 1) AS avg_15m_move_bps_in_bias_direction
FROM first_touches
GROUP BY ticker, approach_side
ORDER BY ticker, approach_side;
