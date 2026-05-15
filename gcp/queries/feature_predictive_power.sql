-- Compare predictive power of EPS / past-reaction / pre-drift / news features
-- against the post-earnings outcome on TWO axes:
--   (1) direction: reaction_gap_pct itself
--   (2) movement: ABS(reaction_gap_pct)
--
-- For each feature x against outcome y, returns Pearson corr(x, y)
-- across all historical earnings_reactions rows where both are non-null.

WITH joined AS (
  SELECT
    er.ticker,
    er.reported_date,
    er.reaction_gap_pct,
    ABS(er.reaction_gap_pct)                              AS reaction_mag_pct,
    er.surprise_pct,
    er.drift_5d_pct,
    er.pre_earnings_drift_10d_pct,
    er.max_high_pre_5d_pct,
    GREATEST(er.max_high_pre_5d_pct,
             ABS(er.min_low_pre_5d_pct))                  AS pre_excursion_5d,
    er.pre_report_atr_pct,
    -- prior quarter outcomes (lagged self)
    LAG(er.reaction_gap_pct)         OVER (PARTITION BY er.ticker ORDER BY er.reported_date) AS prior_reaction_gap,
    LAG(ABS(er.reaction_gap_pct))    OVER (PARTITION BY er.ticker ORDER BY er.reported_date) AS prior_reaction_mag,
    -- news sentiment summed in the 7 days BEFORE the report
    (SELECT AVG(ns.overall_sentiment_score)
     FROM news_sentiment ns
     WHERE ns.ticker = er.ticker
       AND ns.published_ts >= er.reported_date - INTERVAL '7 days'
       AND ns.published_ts <  er.reported_date)           AS news_sentiment_7d_pre,
    (SELECT COUNT(*)
     FROM news_sentiment ns
     WHERE ns.ticker = er.ticker
       AND ns.published_ts >= er.reported_date - INTERVAL '7 days'
       AND ns.published_ts <  er.reported_date)           AS news_count_7d_pre
  FROM earnings_reactions er
  WHERE er.reaction_gap_pct IS NOT NULL
)
SELECT
  feature,
  axis,
  n,
  ROUND(corr_val::numeric, 4) AS pearson_r,
  ROUND(ABS(corr_val)::numeric, 4) AS abs_r
FROM (
  SELECT 'EPS surprise %'           AS feature, 'direction' AS axis, COUNT(*) AS n,
         corr(surprise_pct, reaction_gap_pct) AS corr_val
  FROM joined WHERE surprise_pct IS NOT NULL
  UNION ALL
  SELECT 'EPS surprise %',           'movement',  COUNT(*), corr(surprise_pct, reaction_mag_pct)
  FROM joined WHERE surprise_pct IS NOT NULL
  UNION ALL
  SELECT 'drift_5d (close-based)',   'direction', COUNT(*), corr(drift_5d_pct, reaction_gap_pct)
  FROM joined WHERE drift_5d_pct IS NOT NULL
  UNION ALL
  SELECT 'drift_5d (close-based)',   'movement',  COUNT(*), corr(drift_5d_pct, reaction_mag_pct)
  FROM joined WHERE drift_5d_pct IS NOT NULL
  UNION ALL
  SELECT 'pre_excursion_5d (max|range|)', 'direction', COUNT(*), corr(pre_excursion_5d, reaction_gap_pct)
  FROM joined WHERE pre_excursion_5d IS NOT NULL
  UNION ALL
  SELECT 'pre_excursion_5d (max|range|)', 'movement',  COUNT(*), corr(pre_excursion_5d, reaction_mag_pct)
  FROM joined WHERE pre_excursion_5d IS NOT NULL
  UNION ALL
  SELECT 'pre_report_atr_pct',       'direction', COUNT(*), corr(pre_report_atr_pct, reaction_gap_pct)
  FROM joined WHERE pre_report_atr_pct IS NOT NULL
  UNION ALL
  SELECT 'pre_report_atr_pct',       'movement',  COUNT(*), corr(pre_report_atr_pct, reaction_mag_pct)
  FROM joined WHERE pre_report_atr_pct IS NOT NULL
  UNION ALL
  SELECT 'prior_reaction_gap_pct',   'direction', COUNT(*), corr(prior_reaction_gap, reaction_gap_pct)
  FROM joined WHERE prior_reaction_gap IS NOT NULL
  UNION ALL
  SELECT 'prior_reaction_gap_pct',   'movement',  COUNT(*), corr(prior_reaction_gap, reaction_mag_pct)
  FROM joined WHERE prior_reaction_gap IS NOT NULL
  UNION ALL
  SELECT 'prior_reaction_MAGNITUDE', 'direction', COUNT(*), corr(prior_reaction_mag, reaction_gap_pct)
  FROM joined WHERE prior_reaction_mag IS NOT NULL
  UNION ALL
  SELECT 'prior_reaction_MAGNITUDE', 'movement',  COUNT(*), corr(prior_reaction_mag, reaction_mag_pct)
  FROM joined WHERE prior_reaction_mag IS NOT NULL
  UNION ALL
  SELECT 'news_sentiment_7d_pre',    'direction', COUNT(*), corr(news_sentiment_7d_pre, reaction_gap_pct)
  FROM joined WHERE news_sentiment_7d_pre IS NOT NULL
  UNION ALL
  SELECT 'news_sentiment_7d_pre',    'movement',  COUNT(*), corr(news_sentiment_7d_pre, reaction_mag_pct)
  FROM joined WHERE news_sentiment_7d_pre IS NOT NULL
  UNION ALL
  SELECT 'news_count_7d_pre',        'direction', COUNT(*), corr(news_count_7d_pre, reaction_gap_pct)
  FROM joined WHERE news_count_7d_pre IS NOT NULL
  UNION ALL
  SELECT 'news_count_7d_pre',        'movement',  COUNT(*), corr(news_count_7d_pre, reaction_mag_pct)
  FROM joined WHERE news_count_7d_pre IS NOT NULL
) t
ORDER BY axis, abs_r DESC;
