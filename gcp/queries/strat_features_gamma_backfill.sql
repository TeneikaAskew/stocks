-- Backfill gamma_flip + dist_to_gamma_flip_pct (and refresh gamma_balance_price)
-- into one strat_features_{tf} table via a PRIOR-TRADING-DAY join from
-- gamma_levels_eod — matching strat_data_builder's `prior_gamma = shift(1)`
-- semantics (gamma snapshot from the most recent date STRICTLY BEFORE the bar's
-- date; not calendar date-1, so weekends/holidays don't leak). gday is
-- MATERIALIZED so the per-date LATERAL lookup hits an 8k-row CTE once instead of
-- recomputing the 91k-row GROUP BY per date. NULL gamma_flip => NULL dist (§3.7).
-- {TF} is substituted by the dispatcher loop.
WITH gday AS MATERIALIZED (
    SELECT ticker AS tk, snapshot_date AS gdate,
           max(gamma_flip) AS gf, max(gamma_balance_price) AS gbp
    FROM gamma_levels_eod GROUP BY ticker, snapshot_date
),
mapped AS MATERIALIZED (
    SELECT d.ticker, d.bar_date, g.gf, g.gbp
    FROM (SELECT DISTINCT ticker, bar_date FROM strat_features_{TF}) d
    JOIN LATERAL (
        SELECT gf, gbp FROM gday g
        WHERE g.tk = d.ticker AND g.gdate < d.bar_date
        ORDER BY g.gdate DESC LIMIT 1
    ) g ON true
)
UPDATE strat_features_{TF} sf
SET gamma_balance_price = m.gbp,
    gamma_flip = m.gf,
    dist_to_gamma_flip_pct = CASE WHEN m.gf IS NOT NULL AND sf.close > 0
        THEN (sf.close - m.gf) / sf.close * 100 ELSE NULL END
FROM mapped m
WHERE sf.ticker = m.ticker AND sf.bar_date = m.bar_date;
