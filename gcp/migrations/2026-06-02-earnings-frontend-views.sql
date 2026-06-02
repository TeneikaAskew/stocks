-- ╭─────────────────────────────────────────────────────────────────────╮
-- │ Earnings frontend data prep — 3 materialized views                  │
-- │                                                                     │
-- │ Pre-computes the joins across earnings_history, earnings_reactions, │
-- │ earnings_options_snapshots, earnings_options_strategy_winners, and  │
-- │ earnings_calendar so the FastAPI router can serve in <10ms instead  │
-- │ of running 5-table joins on every request.                          │
-- │                                                                     │
-- │ Refresh strategy:                                                   │
-- │  - earnings_event_outcomes + earnings_ticker_lean: weekly Sunday    │
-- │    20:00 ET via gcp/refresh_earnings_views.py                       │
-- │  - earnings_upcoming_with_history: daily 07:30 ET (before the brief)│
-- │                                                                     │
-- │ All three are REFRESH MATERIALIZED VIEW CONCURRENTLY-safe (they     │
-- │ have UNIQUE indices) so refreshes don't block readers.              │
-- ╰─────────────────────────────────────────────────────────────────────╯

-- ── 1. earnings_event_outcomes ─────────────────────────────────────────
-- One row per (ticker, reported_date). The canonical per-event view.
--
-- Joins:
--   earnings_reactions (gap%, sustain, drift, MAE/MFE)
--   earnings_history (EPS surprise → beat/meet/miss derived)
--   per-event ATM straddle premium (computed inline via window functions)
--   per-event long/short winner flags (from strategy_winners)
--
-- Beat/meet/miss derivation: ±0.5% deadband on surprise_pct
--   surprise_pct > 0.5  → 'beat'
--   surprise_pct < -0.5 → 'miss'
--   else               → 'meet'

DROP MATERIALIZED VIEW IF EXISTS earnings_event_outcomes CASCADE;

CREATE MATERIALIZED VIEW earnings_event_outcomes AS
WITH
-- Dedupe source tables FIRST — both earnings_reactions and
-- earnings_history can have multiple rows per (ticker, reported_date)
-- when quarterly + annual reports land on the same date. We pick the
-- row with the MOST DATA (most non-null reaction metrics for
-- reactions, highest |surprise_pct| for history — proxy for "the more
-- recent / more complete data point").
reactions_deduped AS (
    SELECT DISTINCT ON (ticker, reported_date) *
    FROM earnings_reactions
    ORDER BY ticker, reported_date,
             -- Prefer rows with reaction_gap_pct populated; break
             -- ties on highest fiscal_date_ending (latest period).
             (reaction_gap_pct IS NULL),
             fiscal_date_ending DESC NULLS LAST
),
history_deduped AS (
    SELECT DISTINCT ON (ticker, reported_date) *
    FROM earnings_history
    ORDER BY ticker, reported_date,
             (surprise_pct IS NULL),
             fiscal_date_ending DESC NULLS LAST
),
atm_picks AS (
    -- For each (symbol, snapshot_date, expiration, option_type), pick
    -- the strike closest to d_minus_1_close (the underlying at T-1).
    -- ALSO filters to post-event expirations (the straddle must
    -- capture the earnings reaction).
    SELECT
        eos.symbol AS ticker,
        eos.snapshot_date,
        eos.expiration,
        eos.strike AS atm_strike,
        eos.option_type,
        (eos.bid + eos.ask) / 2.0 AS mid_price,
        eos.implied_volatility,
        er.d_minus_1_close AS spot_t_minus_1,
        er.reported_date,
        ROW_NUMBER() OVER (
            PARTITION BY eos.symbol, eos.snapshot_date, eos.expiration, eos.option_type
            ORDER BY abs(eos.strike - er.d_minus_1_close)
        ) AS rank_by_dist
    FROM earnings_options_snapshots eos
    JOIN reactions_deduped er
        ON er.ticker = eos.symbol
       AND er.reported_date = eos.snapshot_date + INTERVAL '1 day'
    WHERE eos.bid IS NOT NULL AND eos.ask IS NOT NULL
      AND eos.bid > 0 AND eos.ask > 0
      AND er.d_minus_1_close IS NOT NULL
      AND er.d_minus_1_close > 0
      AND eos.expiration >= er.reported_date
),
chosen_expiry AS (
    -- One row per (ticker, snapshot_date): the SINGLE earliest
    -- post-event expiration that has at least one ATM strike (rank=1).
    -- Aggregating MIN(expiration) over rank_by_dist=1 rows guarantees
    -- we don't mix call/put from different expiries. The straddle
    -- MUST be priced from one consistent contract pair.
    SELECT
        ticker,
        snapshot_date,
        MIN(expiration) AS chosen_exp
    FROM atm_picks
    WHERE rank_by_dist = 1
    GROUP BY ticker, snapshot_date
),
atm_per_event AS (
    -- Collapse to one row per (ticker, reported_date) using only the
    -- rows that match the chosen_expiry. Now call_mid + put_mid are
    -- guaranteed to come from the SAME expiry, and ditto for IVs and
    -- the strike (call and put are at the same ATM strike by construction).
    SELECT
        ap.ticker,
        ap.snapshot_date + INTERVAL '1 day' AS reported_date,
        MAX(ap.atm_strike)         FILTER (WHERE ap.option_type='calls') AS atm_strike,
        MAX(ap.mid_price)          FILTER (WHERE ap.option_type='calls') AS call_mid,
        MAX(ap.mid_price)          FILTER (WHERE ap.option_type='puts')  AS put_mid,
        MAX(ap.implied_volatility) FILTER (WHERE ap.option_type='calls') AS call_iv,
        MAX(ap.implied_volatility) FILTER (WHERE ap.option_type='puts')  AS put_iv,
        MAX(ap.spot_t_minus_1) AS spot_t_minus_1
    FROM atm_picks ap
    JOIN chosen_expiry ce
        ON ce.ticker = ap.ticker
       AND ce.snapshot_date = ap.snapshot_date
       AND ap.expiration = ce.chosen_exp
    WHERE ap.rank_by_dist = 1
    GROUP BY ap.ticker, ap.snapshot_date
),
long_wins AS (
    -- Per-event flag: which long structures won here?
    SELECT
        eosw.ticker,
        eosw.event_date AS reported_date,
        array_agg(DISTINCT eosw.structure ORDER BY eosw.structure) AS structures,
        MAX(eosw.pnl_pct)::numeric AS best_pnl
    FROM earnings_options_strategy_winners eosw
    WHERE eosw.structure LIKE 'long%'
      AND eosw.calculation_date = (
          SELECT MAX(calculation_date) FROM earnings_options_strategy_winners)
    GROUP BY eosw.ticker, eosw.event_date
),
short_wins AS (
    SELECT
        eosw.ticker,
        eosw.event_date AS reported_date,
        array_agg(DISTINCT eosw.structure ORDER BY eosw.structure) AS structures,
        MAX(eosw.pnl_pct)::numeric AS best_pnl
    FROM earnings_options_strategy_winners eosw
    WHERE eosw.structure LIKE 'short%'
      AND eosw.calculation_date = (
          SELECT MAX(calculation_date) FROM earnings_options_strategy_winners)
    GROUP BY eosw.ticker, eosw.event_date
)
SELECT
    er.ticker,
    er.reported_date,
    er.fiscal_date_ending,
    -- ── EPS / beat-meet-miss ──
    eh.report_time,
    eh.estimated_eps,
    eh.reported_eps,
    eh.surprise_pct AS eps_surprise_pct,
    CASE
        WHEN eh.surprise_pct IS NULL THEN NULL
        WHEN eh.surprise_pct >  0.5  THEN 'beat'
        WHEN eh.surprise_pct < -0.5  THEN 'miss'
        ELSE 'meet'
    END AS beat_meet_miss,
    -- ── Reaction profile ──
    er.reaction_basis,
    er.reaction_gap_pct,
    er.pre_earnings_drift_10d_pct,
    er.sustain_3d_pct,
    er.sustain_5d_pct,
    er.sustain_10d_pct,
    er.direction_consistent_5d,
    er.is_reversal_5d,
    er.reaction_max_run_pct,
    er.reaction_max_drawdown_pct,
    er.d_minus_1_close,
    er.d_plus_1_close,
    -- ── Options-side summary ──
    a.atm_strike,
    a.call_mid,
    a.put_mid,
    (COALESCE(a.call_mid, 0) + COALESCE(a.put_mid, 0))                  AS straddle_premium,
    CASE WHEN a.spot_t_minus_1 > 0
         THEN (COALESCE(a.call_mid, 0) + COALESCE(a.put_mid, 0))
              / a.spot_t_minus_1 * 100.0
         ELSE NULL END                                                  AS implied_move_pct,
    abs(er.reaction_gap_pct)                                            AS realized_move_pct,
    CASE WHEN (COALESCE(a.call_mid, 0) + COALESCE(a.put_mid, 0)) > 0
              AND a.spot_t_minus_1 > 0
         THEN abs(er.reaction_gap_pct)
              / ((COALESCE(a.call_mid, 0) + COALESCE(a.put_mid, 0))
                 / a.spot_t_minus_1 * 100.0)
         ELSE NULL END                                                  AS realized_vs_implied_ratio,
    ((COALESCE(a.call_iv, 0) + COALESCE(a.put_iv, 0)) / 2.0) * 100.0    AS avg_iv_pct,
    -- ── Winner flags ──
    lw.structures      AS long_winner_structures,
    lw.best_pnl        AS best_long_pnl_pct,
    sw.structures      AS short_winner_structures,
    sw.best_pnl        AS best_short_pnl_pct
FROM reactions_deduped er
LEFT JOIN history_deduped eh
    ON eh.ticker = er.ticker
   AND eh.reported_date = er.reported_date
LEFT JOIN atm_per_event a
    ON a.ticker = er.ticker
   AND a.reported_date = er.reported_date
LEFT JOIN long_wins lw
    ON lw.ticker = er.ticker
   AND lw.reported_date = er.reported_date
LEFT JOIN short_wins sw
    ON sw.ticker = er.ticker
   AND sw.reported_date = er.reported_date
WITH NO DATA;

CREATE UNIQUE INDEX idx_eeo_ticker_date
    ON earnings_event_outcomes (ticker, reported_date);
CREATE INDEX idx_eeo_reported_date
    ON earnings_event_outcomes (reported_date DESC);


-- ── 2. earnings_ticker_lean ────────────────────────────────────────────
-- One row per ticker. Aggregate stats: total quarters, beat/meet/miss
-- counts, average gap, lean score (positive = leans long, negative = leans short).

DROP MATERIALIZED VIEW IF EXISTS earnings_ticker_lean CASCADE;

CREATE MATERIALIZED VIEW earnings_ticker_lean AS
SELECT
    ticker,
    COUNT(*)                                                AS total_quarters,
    COUNT(*) FILTER (WHERE beat_meet_miss = 'beat')         AS n_beats,
    COUNT(*) FILTER (WHERE beat_meet_miss = 'meet')         AS n_meets,
    COUNT(*) FILTER (WHERE beat_meet_miss = 'miss')         AS n_misses,
    ROUND(100.0 * COUNT(*) FILTER (WHERE beat_meet_miss = 'beat')
                  / NULLIF(COUNT(*) FILTER (WHERE beat_meet_miss IS NOT NULL), 0), 1)
                                                            AS beat_rate_pct,
    -- ── Reaction stats ──
    ROUND(AVG(reaction_gap_pct)::numeric, 2)                AS avg_gap_pct,
    ROUND(AVG(abs(reaction_gap_pct))::numeric, 2)           AS avg_abs_gap_pct,
    ROUND(STDDEV(reaction_gap_pct)::numeric, 2)             AS stddev_gap_pct,
    ROUND(MAX(reaction_gap_pct)::numeric, 2)                AS max_gap_pct,
    ROUND(MIN(reaction_gap_pct)::numeric, 2)                AS min_gap_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE direction_consistent_5d) / NULLIF(COUNT(*), 0), 1)
                                                            AS dir_consistency_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE is_reversal_5d) / NULLIF(COUNT(*), 0), 1)
                                                            AS reversal_rate_pct,
    -- ── Implied vs realized ──
    ROUND(AVG(implied_move_pct)::numeric, 2)                AS avg_implied_move_pct,
    ROUND(AVG(realized_move_pct)::numeric, 2)               AS avg_realized_move_pct,
    ROUND(AVG(realized_vs_implied_ratio)::numeric, 2)       AS avg_ratio,
    -- ── Lean signal ──
    -- Counts of events where a long structure won vs short.
    COUNT(*) FILTER (WHERE long_winner_structures  IS NOT NULL) AS long_winner_count,
    COUNT(*) FILTER (WHERE short_winner_structures IS NOT NULL) AS short_winner_count,
    -- Lean score: (long - short) / total. Range [-1, +1].
    -- Positive = ticker historically blows through implied → favor long.
    -- Negative = ticker under-realizes implied → premium-sellers' edge.
    ROUND(
        (COUNT(*) FILTER (WHERE long_winner_structures  IS NOT NULL)::numeric
       - COUNT(*) FILTER (WHERE short_winner_structures IS NOT NULL)::numeric)
       / NULLIF(COUNT(*), 0), 3
    )                                                       AS lean_score,
    -- Best historical PnLs (the "would have been" stat for each side).
    ROUND(MAX(best_long_pnl_pct)::numeric, 0)               AS max_long_pnl_pct,
    ROUND(MAX(best_short_pnl_pct)::numeric, 0)              AS max_short_pnl_pct,
    -- Freshness.
    MAX(reported_date)                                      AS last_event_date
FROM earnings_event_outcomes
GROUP BY ticker
WITH NO DATA;

CREATE UNIQUE INDEX idx_etl_ticker
    ON earnings_ticker_lean (ticker);
CREATE INDEX idx_etl_lean
    ON earnings_ticker_lean (lean_score DESC);
CREATE INDEX idx_etl_long_wins
    ON earnings_ticker_lean (long_winner_count DESC);


-- ── 3. earnings_upcoming_with_history ──────────────────────────────────
-- Regular table (not a mat view) — refreshed DAILY at 07:30 ET by the
-- refresh job. Decorates the next N days of earnings_calendar reporters
-- with their lean stats so the frontend can render the "this week" page
-- in a single query.
--
-- Built as a TABLE (not a view) so the refresh job can use TRUNCATE +
-- INSERT semantics with a brief lock window, and so we can attach
-- additional refresh-time computed columns (recommended_structure_*
-- needs the live calibration row, which is easier in app code than SQL).

CREATE TABLE IF NOT EXISTS earnings_upcoming_with_history (
    id                         BIGSERIAL PRIMARY KEY,
    refresh_date               DATE NOT NULL,
    ticker                     TEXT NOT NULL,
    earnings_date              DATE NOT NULL,
    earnings_time              TEXT,
    company_name               TEXT,
    market_cap                 DOUBLE PRECISION,
    sector                     TEXT,
    -- Live-row enrichment from earnings_calendar
    eps_estimate               DOUBLE PRECISION,
    expected_move              DOUBLE PRECISION,        -- in dollars
    prev_close                 DOUBLE PRECISION,
    implied_move_pct           DOUBLE PRECISION,        -- expected_move / prev_close * 100
    options_volume             BIGINT,
    open_interest              BIGINT,
    -- Playability + archetype (computed at refresh time)
    playability_score          DOUBLE PRECISION,
    quintile                   TEXT,                    -- Q1..Q5
    archetype                  TEXT,
    confidence_label           TEXT,
    -- BOTH recommendation modes (user asked for both until they decide)
    recommended_structure_long_only  TEXT,
    recommended_structure_ic_mode    TEXT,
    -- Historical context from earnings_ticker_lean
    total_quarters             INTEGER,
    n_beats                    INTEGER,
    n_meets                    INTEGER,
    n_misses                   INTEGER,
    beat_rate_pct              NUMERIC(5, 1),
    avg_abs_gap_pct            NUMERIC(6, 2),
    dir_consistency_pct        NUMERIC(5, 1),
    reversal_rate_pct          NUMERIC(5, 1),
    avg_ratio                  NUMERIC(5, 2),
    lean_score                 NUMERIC(5, 3),
    long_winner_count          INTEGER,
    short_winner_count         INTEGER,
    -- Last 3 events (jsonb for compact rendering)
    last_3_events              JSONB,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (refresh_date, ticker, earnings_date)
);

CREATE INDEX IF NOT EXISTS idx_euwh_recent
    ON earnings_upcoming_with_history (refresh_date DESC, earnings_date);
CREATE INDEX IF NOT EXISTS idx_euwh_ticker
    ON earnings_upcoming_with_history (ticker, refresh_date DESC);
