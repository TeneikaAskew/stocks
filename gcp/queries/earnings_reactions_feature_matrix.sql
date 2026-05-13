-- Joined feature matrix for predictive analysis of earnings reactions.
-- One row per (ticker, fiscal_date_ending) with:
--   * native earnings_reactions features
--   * pre-event news sentiment aggregates (-7d → -1d before reported_date)
--   * pre-event insider activity aggregates (-60d → -1d before reported_date)
--   * 12-quarter rolling historical stats per ticker (lagged — uses only PRIOR quarters)
-- Filtered to rows where direction_consistent_5d is non-NULL so the supervised
-- label is defined.

WITH base AS (
    SELECT
        er.ticker,
        er.fiscal_date_ending,
        er.reported_date,
        er.reaction_basis,
        er.surprise_pct,
        er.pre_earnings_drift_10d_pct,
        er.pre_report_gap_pct,
        er.post_gap_pct,
        er.reaction_gap_pct,
        er.reaction_max_run_pct,
        er.reaction_max_drawdown_pct,
        er.sustain_3d_pct,
        er.sustain_5d_pct,
        er.sustain_10d_pct,
        er.direction_consistent_5d,
        er.is_reversal_5d,
        er.pre_report_atr,
        er.pre_report_atr_pct,
        er.post_report_atr,
        er.reaction_day_range_in_atr_units,
        er.max_high_5d_pct,
        er.min_low_5d_pct
    FROM earnings_reactions er
    WHERE er.direction_consistent_5d IS NOT NULL
      AND er.reaction_gap_pct IS NOT NULL
),
news_agg AS (
    SELECT
        b.ticker,
        b.fiscal_date_ending,
        COUNT(ns.id)                                      AS news_count_7d,
        AVG(ns.sentiment_score)                           AS news_avg_sent_7d,
        AVG(ns.overall_sentiment_score)                   AS news_avg_overall_sent_7d,
        MAX(ABS(ns.sentiment_score))                      AS news_max_abs_sent_7d,
        AVG(ns.relevance_score)                           AS news_avg_relev_7d
    FROM base b
    LEFT JOIN news_sentiment ns
      ON ns.ticker = b.ticker
     AND ns.published_ts::date >= b.reported_date - INTERVAL '7 days'
     AND ns.published_ts::date <  b.reported_date
    GROUP BY b.ticker, b.fiscal_date_ending
),
insider_agg AS (
    SELECT
        b.ticker,
        b.fiscal_date_ending,
        SUM(CASE WHEN it.transaction_type = 'A' THEN it.transaction_value ELSE 0 END) AS insider_buy_value_60d,
        SUM(CASE WHEN it.transaction_type = 'D' THEN it.transaction_value ELSE 0 END) AS insider_sell_value_60d,
        COUNT(CASE WHEN it.transaction_type = 'A' THEN 1 END) AS insider_buy_count_60d,
        COUNT(CASE WHEN it.transaction_type = 'D' THEN 1 END) AS insider_sell_count_60d
    FROM base b
    LEFT JOIN insider_transactions it
      ON it.ticker = b.ticker
     AND it.transaction_date >= b.reported_date - INTERVAL '60 days'
     AND it.transaction_date <  b.reported_date
    GROUP BY b.ticker, b.fiscal_date_ending
),
hist_agg AS (
    -- 12-quarter rolling stats using only PRIOR quarters (no look-ahead).
    -- The CASE branches guard on ``prev.id IS NULL`` so the null-extended
    -- row from the LEFT JOIN LATERAL (for tickers with no prior history)
    -- contributes NULL — not 0.0 — to the rate aggregates. Without the
    -- guard, a first-observation quarter would surface as 0% consistent
    -- / 0% reversal / 0% gap-up rather than "missing history".
    SELECT
        b.ticker,
        b.fiscal_date_ending,
        AVG(prev.reaction_gap_pct)                        AS hist12q_avg_gap_pct,
        AVG(ABS(prev.reaction_gap_pct))                   AS hist12q_avg_abs_gap_pct,
        AVG(prev.sustain_5d_pct)                          AS hist12q_avg_sustain_5d_pct,
        AVG(CASE WHEN prev.id IS NULL THEN NULL
                 WHEN prev.direction_consistent_5d THEN 1.0
                 ELSE 0.0 END)                            AS hist12q_consistent_rate,
        AVG(CASE WHEN prev.id IS NULL THEN NULL
                 WHEN prev.is_reversal_5d THEN 1.0
                 ELSE 0.0 END)                            AS hist12q_reversal_rate,
        AVG(CASE WHEN prev.id IS NULL THEN NULL
                 WHEN prev.reaction_gap_pct > 0 THEN 1.0
                 ELSE 0.0 END)                            AS hist12q_gap_up_rate,
        AVG(prev.surprise_pct)                            AS hist12q_avg_surprise_pct,
        COUNT(prev.id)                                    AS hist12q_n
    FROM base b
    LEFT JOIN LATERAL (
        SELECT *
        FROM earnings_reactions p
        WHERE p.ticker = b.ticker
          AND p.fiscal_date_ending < b.fiscal_date_ending
          AND p.direction_consistent_5d IS NOT NULL
        ORDER BY p.fiscal_date_ending DESC
        LIMIT 12
    ) prev ON TRUE
    GROUP BY b.ticker, b.fiscal_date_ending
)
SELECT
    b.*,
    n.news_count_7d, n.news_avg_sent_7d, n.news_avg_overall_sent_7d,
    n.news_max_abs_sent_7d, n.news_avg_relev_7d,
    i.insider_buy_value_60d, i.insider_sell_value_60d,
    i.insider_buy_count_60d, i.insider_sell_count_60d,
    h.hist12q_avg_gap_pct, h.hist12q_avg_abs_gap_pct,
    h.hist12q_avg_sustain_5d_pct, h.hist12q_consistent_rate,
    h.hist12q_reversal_rate, h.hist12q_gap_up_rate,
    h.hist12q_avg_surprise_pct, h.hist12q_n
FROM base b
LEFT JOIN news_agg     n ON n.ticker = b.ticker AND n.fiscal_date_ending = b.fiscal_date_ending
LEFT JOIN insider_agg  i ON i.ticker = b.ticker AND i.fiscal_date_ending = b.fiscal_date_ending
LEFT JOIN hist_agg     h ON h.ticker = b.ticker AND h.fiscal_date_ending = b.fiscal_date_ending;
