-- Backfill gamma_flip + dist_to_gamma_flip_pct (and refresh gamma_balance_price)
-- into strat_features_{tf} via a PRIOR-TRADING-DAY join from gamma_levels_eod —
-- matching strat_data_builder's `prior_gamma = gamma_df.shift(1)` semantics
-- (the gamma snapshot from the most recent date STRICTLY BEFORE the bar's date;
-- NOT calendar date-1, so weekends/holidays don't leak). One statement per TF.
-- Prior-date lookup is computed once per DISTINCT (ticker,bar_date) via the
-- `mapped` CTE (not per row). NULL gamma_flip => NULL dist (no fabricated 0).
WITH gday AS (
    SELECT ticker AS tk, snapshot_date AS gdate,
           max(gamma_flip) AS gf, max(gamma_balance_price) AS gbp
    FROM gamma_levels_eod GROUP BY ticker, snapshot_date
),
mapped AS (
    SELECT d.ticker, d.bar_date,
        (SELECT g.gdate FROM gday g
         WHERE g.tk = d.ticker AND g.gdate < d.bar_date
         ORDER BY g.gdate DESC LIMIT 1) AS prior_gdate
    FROM (SELECT DISTINCT ticker, bar_date FROM strat_features_15m) d
)
UPDATE strat_features_15m sf
SET gamma_balance_price = g.gbp,
    gamma_flip = g.gf,
    dist_to_gamma_flip_pct = CASE WHEN g.gf IS NOT NULL AND sf.close > 0
        THEN (sf.close - g.gf) / sf.close * 100 ELSE NULL END
FROM mapped m
JOIN gday g ON g.tk = m.ticker AND g.gdate = m.prior_gdate
WHERE sf.ticker = m.ticker AND sf.bar_date = m.bar_date;
