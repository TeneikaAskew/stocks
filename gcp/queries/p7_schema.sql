-- Phase 7 schema: 5 per-TF strat-features tables.
--
-- One table per timeframe. Each row = one bar at that TF for one ticker.
-- PK is (ticker, ts). Indexes support the analysis queries described in
-- docs/research/2026-05-24/RESEARCH_PLAN_P7.md.
--
-- Apply via:
--   gh workflow run db-query.yml \
--     -f sql_file=gcp/queries/p7_schema.sql \
--     -f commit=true
--
-- Idempotent — CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS.

-- Reusable column definition macro (Postgres doesn't have macros; this
-- comment block documents the common columns. Each CREATE TABLE below
-- repeats them since DDL can't share definitions cleanly.)
--
-- IDENTITY
--   ticker            VARCHAR(16) NOT NULL
--   ts                TIMESTAMPTZ NOT NULL
--   tf                VARCHAR(8)  NOT NULL     -- '1m' / '5m' / '15m' / '30m' / '60m'
--   bar_date          DATE        NOT NULL     -- date(ts AT TIME ZONE 'America/New_York')
--
-- OHLCV (this bar)
--   open, high, low, close DOUBLE PRECISION
--   volume                  BIGINT
--
-- STRAT SEQUENCE (from lib.strat.StratClassifier.detect_combos)
--   strat_candle           VARCHAR(4)        -- '1' | '2U' | '2D' | '3'
--   prev_strat_candle      VARCHAR(4)        -- shift(1) of strat_candle
--   strat_combo            VARCHAR(48)
--   is_continuation        BOOLEAN
--   is_reversal            BOOLEAN
--   is_inside              BOOLEAN
--   strat_setup            BOOLEAN
--   consecutive_1s         SMALLINT
--   trigger_high           DOUBLE PRECISION
--   trigger_low            DOUBLE PRECISION
--
-- INDICATORS (from lib.indicators.add_all_indicators)
--   ema_9, ema_20, ema_50, ema_200          DOUBLE PRECISION
--   sma_50, sma_200                          DOUBLE PRECISION
--   rsi_9, rsi_14                            DOUBLE PRECISION
--   stoch_rsi_k, stoch_rsi_d                 DOUBLE PRECISION
--   macd, macd_signal, macd_histogram        DOUBLE PRECISION
--   atr_14, atr_20                           DOUBLE PRECISION
--   bb_upper, bb_lower, bb_width, bb_pct     DOUBLE PRECISION
--   obv                                       DOUBLE PRECISION
--   rvol, rvol_10                            DOUBLE PRECISION
--   vwap, price_vs_vwap                      DOUBLE PRECISION
--   price_vs_ema9, price_vs_ema20            DOUBLE PRECISION
--   consecutive_up, consecutive_down         INTEGER
--   intraday_return, high_low_spread_pct     DOUBLE PRECISION
--
-- FORWARD RETURNS (computed during job)
--   fwd_close_5bars, fwd_close_15bars, fwd_close_30bars, fwd_close_60bars  DOUBLE PRECISION
--   fwd_ret_5bars_bps, fwd_ret_15bars_bps, fwd_ret_30bars_bps, fwd_ret_60bars_bps  DOUBLE PRECISION
--
-- CONTEXT (joined from market_data_daily + gamma_levels_eod)
--   vix_close              DOUBLE PRECISION
--   vix_tercile            VARCHAR(8)        -- 'LOW' | 'MID' | 'HIGH'  (p33=14.65, p67=19.40 from P1)
--   total_gex              DOUBLE PRECISION
--   gex_tercile            VARCHAR(8)        -- computed from per-ticker 10yr distribution
--   total_vex              DOUBLE PRECISION  -- computed via lib.gamma.total_vex from EOD chain
--   vex_tercile            VARCHAR(8)        -- per-ticker 10yr distribution
--   dealer_regime          VARCHAR(24)       -- '{GEX_X}_{VEX_Y}' — 9 values
--   gamma_regime           VARCHAR(20)       -- positive_gamma | negative_gamma | unknown
--   gamma_balance_price    DOUBLE PRECISION
--   gamma_flip             DOUBLE PRECISION
--   dist_to_gamma_flip_pct DOUBLE PRECISION
--   distance_to_king_pct   DOUBLE PRECISION
--   distance_to_gate_pct   DOUBLE PRECISION
--
-- BOOKKEEPING
--   computed_at            TIMESTAMPTZ DEFAULT now()


-- ─────────────────────────── 1-min ───────────────────────────
CREATE TABLE IF NOT EXISTS strat_features_1m (
    ticker            VARCHAR(16) NOT NULL,
    ts                TIMESTAMPTZ NOT NULL,
    tf                VARCHAR(8)  NOT NULL,
    bar_date          DATE        NOT NULL,
    open              DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION,
    close             DOUBLE PRECISION, volume BIGINT,
    strat_candle      VARCHAR(4),
    prev_strat_candle VARCHAR(4),
    strat_combo       VARCHAR(48),
    is_continuation   BOOLEAN,
    is_reversal       BOOLEAN,
    is_inside         BOOLEAN,
    strat_setup       BOOLEAN,
    consecutive_1s    SMALLINT,
    trigger_high      DOUBLE PRECISION, trigger_low DOUBLE PRECISION,
    ema_9             DOUBLE PRECISION, ema_20 DOUBLE PRECISION, ema_50 DOUBLE PRECISION, ema_200 DOUBLE PRECISION,
    sma_50            DOUBLE PRECISION, sma_200 DOUBLE PRECISION,
    rsi_9             DOUBLE PRECISION, rsi_14 DOUBLE PRECISION,
    stoch_rsi_k       DOUBLE PRECISION, stoch_rsi_d DOUBLE PRECISION,
    macd              DOUBLE PRECISION, macd_signal DOUBLE PRECISION, macd_histogram DOUBLE PRECISION,
    atr_14            DOUBLE PRECISION, atr_20 DOUBLE PRECISION,
    bb_upper          DOUBLE PRECISION, bb_lower DOUBLE PRECISION,
    bb_width          DOUBLE PRECISION, bb_pct DOUBLE PRECISION,
    obv               DOUBLE PRECISION,
    rvol              DOUBLE PRECISION, rvol_10 DOUBLE PRECISION,
    vwap              DOUBLE PRECISION, price_vs_vwap DOUBLE PRECISION,
    price_vs_ema9     DOUBLE PRECISION, price_vs_ema20 DOUBLE PRECISION,
    consecutive_up    INTEGER, consecutive_down INTEGER,
    realized_vol_short DOUBLE PRECISION, mins_since_open DOUBLE PRECISION,
    price_vs_ema9_atr DOUBLE PRECISION, price_vs_ema20_atr DOUBLE PRECISION,
    price_vs_vwap_atr DOUBLE PRECISION, ema_spread_atr DOUBLE PRECISION,
    ema9_slope DOUBLE PRECISION, bb_squeeze DOUBLE PRECISION, rsi_divergence DOUBLE PRECISION,
    intraday_return   DOUBLE PRECISION, high_low_spread_pct DOUBLE PRECISION,
    fwd_close_5bars   DOUBLE PRECISION, fwd_close_15bars DOUBLE PRECISION,
    fwd_close_30bars  DOUBLE PRECISION, fwd_close_60bars DOUBLE PRECISION,
    fwd_ret_5bars_bps DOUBLE PRECISION, fwd_ret_15bars_bps DOUBLE PRECISION,
    fwd_ret_30bars_bps DOUBLE PRECISION, fwd_ret_60bars_bps DOUBLE PRECISION,
    vix_close         DOUBLE PRECISION, vix_tercile VARCHAR(8),
    total_gex         DOUBLE PRECISION, gex_tercile VARCHAR(8),
    total_vex         DOUBLE PRECISION, vex_tercile VARCHAR(8),
    dealer_regime     VARCHAR(24),
    gamma_regime      VARCHAR(20),
    gamma_balance_price DOUBLE PRECISION,
    gamma_flip        DOUBLE PRECISION,
    dist_to_gamma_flip_pct DOUBLE PRECISION,
    distance_to_king_pct DOUBLE PRECISION,
    distance_to_gate_pct DOUBLE PRECISION,
    computed_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS ix_strat_features_1m_combo ON strat_features_1m (ticker, strat_combo);
CREATE INDEX IF NOT EXISTS ix_strat_features_1m_date  ON strat_features_1m (bar_date);


-- ─────────────────────────── 5-min ───────────────────────────
CREATE TABLE IF NOT EXISTS strat_features_5m (
    ticker            VARCHAR(16) NOT NULL,
    ts                TIMESTAMPTZ NOT NULL,
    tf                VARCHAR(8)  NOT NULL,
    bar_date          DATE        NOT NULL,
    open              DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION,
    close             DOUBLE PRECISION, volume BIGINT,
    strat_candle      VARCHAR(4),
    prev_strat_candle VARCHAR(4),
    strat_combo       VARCHAR(48),
    is_continuation   BOOLEAN, is_reversal BOOLEAN, is_inside BOOLEAN,
    strat_setup       BOOLEAN, consecutive_1s SMALLINT,
    trigger_high      DOUBLE PRECISION, trigger_low DOUBLE PRECISION,
    ema_9             DOUBLE PRECISION, ema_20 DOUBLE PRECISION, ema_50 DOUBLE PRECISION, ema_200 DOUBLE PRECISION,
    sma_50            DOUBLE PRECISION, sma_200 DOUBLE PRECISION,
    rsi_9             DOUBLE PRECISION, rsi_14 DOUBLE PRECISION,
    stoch_rsi_k       DOUBLE PRECISION, stoch_rsi_d DOUBLE PRECISION,
    macd              DOUBLE PRECISION, macd_signal DOUBLE PRECISION, macd_histogram DOUBLE PRECISION,
    atr_14            DOUBLE PRECISION, atr_20 DOUBLE PRECISION,
    bb_upper          DOUBLE PRECISION, bb_lower DOUBLE PRECISION,
    bb_width          DOUBLE PRECISION, bb_pct DOUBLE PRECISION,
    obv               DOUBLE PRECISION,
    rvol              DOUBLE PRECISION, rvol_10 DOUBLE PRECISION,
    vwap              DOUBLE PRECISION, price_vs_vwap DOUBLE PRECISION,
    price_vs_ema9     DOUBLE PRECISION, price_vs_ema20 DOUBLE PRECISION,
    consecutive_up    INTEGER, consecutive_down INTEGER,
    realized_vol_short DOUBLE PRECISION, mins_since_open DOUBLE PRECISION,
    price_vs_ema9_atr DOUBLE PRECISION, price_vs_ema20_atr DOUBLE PRECISION,
    price_vs_vwap_atr DOUBLE PRECISION, ema_spread_atr DOUBLE PRECISION,
    ema9_slope DOUBLE PRECISION, bb_squeeze DOUBLE PRECISION, rsi_divergence DOUBLE PRECISION,
    intraday_return   DOUBLE PRECISION, high_low_spread_pct DOUBLE PRECISION,
    fwd_close_5bars   DOUBLE PRECISION, fwd_close_15bars DOUBLE PRECISION,
    fwd_close_30bars  DOUBLE PRECISION, fwd_close_60bars DOUBLE PRECISION,
    fwd_ret_5bars_bps DOUBLE PRECISION, fwd_ret_15bars_bps DOUBLE PRECISION,
    fwd_ret_30bars_bps DOUBLE PRECISION, fwd_ret_60bars_bps DOUBLE PRECISION,
    vix_close         DOUBLE PRECISION, vix_tercile VARCHAR(8),
    total_gex         DOUBLE PRECISION, gex_tercile VARCHAR(8),
    total_vex         DOUBLE PRECISION, vex_tercile VARCHAR(8),
    dealer_regime     VARCHAR(24),
    gamma_regime      VARCHAR(20),
    gamma_balance_price DOUBLE PRECISION,
    gamma_flip        DOUBLE PRECISION,
    dist_to_gamma_flip_pct DOUBLE PRECISION,
    distance_to_king_pct DOUBLE PRECISION,
    distance_to_gate_pct DOUBLE PRECISION,
    computed_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS ix_strat_features_5m_combo ON strat_features_5m (ticker, strat_combo);
CREATE INDEX IF NOT EXISTS ix_strat_features_5m_date  ON strat_features_5m (bar_date);
CREATE INDEX IF NOT EXISTS ix_strat_features_5m_dr    ON strat_features_5m (dealer_regime);


-- ─────────────────────────── 15-min ───────────────────────────
CREATE TABLE IF NOT EXISTS strat_features_15m (
    ticker            VARCHAR(16) NOT NULL,
    ts                TIMESTAMPTZ NOT NULL,
    tf                VARCHAR(8)  NOT NULL,
    bar_date          DATE        NOT NULL,
    open              DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION,
    close             DOUBLE PRECISION, volume BIGINT,
    strat_candle      VARCHAR(4), prev_strat_candle VARCHAR(4),
    strat_combo       VARCHAR(48),
    is_continuation   BOOLEAN, is_reversal BOOLEAN, is_inside BOOLEAN,
    strat_setup       BOOLEAN, consecutive_1s SMALLINT,
    trigger_high      DOUBLE PRECISION, trigger_low DOUBLE PRECISION,
    ema_9             DOUBLE PRECISION, ema_20 DOUBLE PRECISION, ema_50 DOUBLE PRECISION, ema_200 DOUBLE PRECISION,
    sma_50            DOUBLE PRECISION, sma_200 DOUBLE PRECISION,
    rsi_9             DOUBLE PRECISION, rsi_14 DOUBLE PRECISION,
    stoch_rsi_k       DOUBLE PRECISION, stoch_rsi_d DOUBLE PRECISION,
    macd              DOUBLE PRECISION, macd_signal DOUBLE PRECISION, macd_histogram DOUBLE PRECISION,
    atr_14            DOUBLE PRECISION, atr_20 DOUBLE PRECISION,
    bb_upper          DOUBLE PRECISION, bb_lower DOUBLE PRECISION, bb_width DOUBLE PRECISION, bb_pct DOUBLE PRECISION,
    obv               DOUBLE PRECISION, rvol DOUBLE PRECISION, rvol_10 DOUBLE PRECISION,
    vwap              DOUBLE PRECISION, price_vs_vwap DOUBLE PRECISION,
    price_vs_ema9     DOUBLE PRECISION, price_vs_ema20 DOUBLE PRECISION,
    consecutive_up    INTEGER, consecutive_down INTEGER,
    realized_vol_short DOUBLE PRECISION, mins_since_open DOUBLE PRECISION,
    price_vs_ema9_atr DOUBLE PRECISION, price_vs_ema20_atr DOUBLE PRECISION,
    price_vs_vwap_atr DOUBLE PRECISION, ema_spread_atr DOUBLE PRECISION,
    ema9_slope DOUBLE PRECISION, bb_squeeze DOUBLE PRECISION, rsi_divergence DOUBLE PRECISION,
    intraday_return   DOUBLE PRECISION, high_low_spread_pct DOUBLE PRECISION,
    fwd_close_5bars   DOUBLE PRECISION, fwd_close_15bars DOUBLE PRECISION,
    fwd_close_30bars  DOUBLE PRECISION, fwd_close_60bars DOUBLE PRECISION,
    fwd_ret_5bars_bps DOUBLE PRECISION, fwd_ret_15bars_bps DOUBLE PRECISION,
    fwd_ret_30bars_bps DOUBLE PRECISION, fwd_ret_60bars_bps DOUBLE PRECISION,
    vix_close         DOUBLE PRECISION, vix_tercile VARCHAR(8),
    total_gex         DOUBLE PRECISION, gex_tercile VARCHAR(8),
    total_vex         DOUBLE PRECISION, vex_tercile VARCHAR(8),
    dealer_regime     VARCHAR(24), gamma_regime VARCHAR(20),
    gamma_balance_price DOUBLE PRECISION,
    gamma_flip        DOUBLE PRECISION,
    dist_to_gamma_flip_pct DOUBLE PRECISION,
    distance_to_king_pct DOUBLE PRECISION, distance_to_gate_pct DOUBLE PRECISION,
    computed_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS ix_strat_features_15m_combo ON strat_features_15m (ticker, strat_combo);
CREATE INDEX IF NOT EXISTS ix_strat_features_15m_date  ON strat_features_15m (bar_date);
CREATE INDEX IF NOT EXISTS ix_strat_features_15m_dr    ON strat_features_15m (dealer_regime);


-- ─────────────────────────── 30-min ───────────────────────────
CREATE TABLE IF NOT EXISTS strat_features_30m (
    ticker            VARCHAR(16) NOT NULL,
    ts                TIMESTAMPTZ NOT NULL,
    tf                VARCHAR(8)  NOT NULL,
    bar_date          DATE        NOT NULL,
    open              DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION,
    close             DOUBLE PRECISION, volume BIGINT,
    strat_candle      VARCHAR(4), prev_strat_candle VARCHAR(4),
    strat_combo       VARCHAR(48),
    is_continuation   BOOLEAN, is_reversal BOOLEAN, is_inside BOOLEAN,
    strat_setup       BOOLEAN, consecutive_1s SMALLINT,
    trigger_high      DOUBLE PRECISION, trigger_low DOUBLE PRECISION,
    ema_9             DOUBLE PRECISION, ema_20 DOUBLE PRECISION, ema_50 DOUBLE PRECISION, ema_200 DOUBLE PRECISION,
    sma_50            DOUBLE PRECISION, sma_200 DOUBLE PRECISION,
    rsi_9             DOUBLE PRECISION, rsi_14 DOUBLE PRECISION,
    stoch_rsi_k       DOUBLE PRECISION, stoch_rsi_d DOUBLE PRECISION,
    macd              DOUBLE PRECISION, macd_signal DOUBLE PRECISION, macd_histogram DOUBLE PRECISION,
    atr_14            DOUBLE PRECISION, atr_20 DOUBLE PRECISION,
    bb_upper          DOUBLE PRECISION, bb_lower DOUBLE PRECISION, bb_width DOUBLE PRECISION, bb_pct DOUBLE PRECISION,
    obv               DOUBLE PRECISION, rvol DOUBLE PRECISION, rvol_10 DOUBLE PRECISION,
    vwap              DOUBLE PRECISION, price_vs_vwap DOUBLE PRECISION,
    price_vs_ema9     DOUBLE PRECISION, price_vs_ema20 DOUBLE PRECISION,
    consecutive_up    INTEGER, consecutive_down INTEGER,
    realized_vol_short DOUBLE PRECISION, mins_since_open DOUBLE PRECISION,
    price_vs_ema9_atr DOUBLE PRECISION, price_vs_ema20_atr DOUBLE PRECISION,
    price_vs_vwap_atr DOUBLE PRECISION, ema_spread_atr DOUBLE PRECISION,
    ema9_slope DOUBLE PRECISION, bb_squeeze DOUBLE PRECISION, rsi_divergence DOUBLE PRECISION,
    intraday_return   DOUBLE PRECISION, high_low_spread_pct DOUBLE PRECISION,
    fwd_close_5bars   DOUBLE PRECISION, fwd_close_15bars DOUBLE PRECISION,
    fwd_close_30bars  DOUBLE PRECISION, fwd_close_60bars DOUBLE PRECISION,
    fwd_ret_5bars_bps DOUBLE PRECISION, fwd_ret_15bars_bps DOUBLE PRECISION,
    fwd_ret_30bars_bps DOUBLE PRECISION, fwd_ret_60bars_bps DOUBLE PRECISION,
    vix_close         DOUBLE PRECISION, vix_tercile VARCHAR(8),
    total_gex         DOUBLE PRECISION, gex_tercile VARCHAR(8),
    total_vex         DOUBLE PRECISION, vex_tercile VARCHAR(8),
    dealer_regime     VARCHAR(24), gamma_regime VARCHAR(20),
    gamma_balance_price DOUBLE PRECISION,
    gamma_flip        DOUBLE PRECISION,
    dist_to_gamma_flip_pct DOUBLE PRECISION,
    distance_to_king_pct DOUBLE PRECISION, distance_to_gate_pct DOUBLE PRECISION,
    computed_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS ix_strat_features_30m_combo ON strat_features_30m (ticker, strat_combo);
CREATE INDEX IF NOT EXISTS ix_strat_features_30m_date  ON strat_features_30m (bar_date);
CREATE INDEX IF NOT EXISTS ix_strat_features_30m_dr    ON strat_features_30m (dealer_regime);


-- ─────────────────────────── 60-min ───────────────────────────
CREATE TABLE IF NOT EXISTS strat_features_60m (
    ticker            VARCHAR(16) NOT NULL,
    ts                TIMESTAMPTZ NOT NULL,
    tf                VARCHAR(8)  NOT NULL,
    bar_date          DATE        NOT NULL,
    open              DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION,
    close             DOUBLE PRECISION, volume BIGINT,
    strat_candle      VARCHAR(4), prev_strat_candle VARCHAR(4),
    strat_combo       VARCHAR(48),
    is_continuation   BOOLEAN, is_reversal BOOLEAN, is_inside BOOLEAN,
    strat_setup       BOOLEAN, consecutive_1s SMALLINT,
    trigger_high      DOUBLE PRECISION, trigger_low DOUBLE PRECISION,
    ema_9             DOUBLE PRECISION, ema_20 DOUBLE PRECISION, ema_50 DOUBLE PRECISION, ema_200 DOUBLE PRECISION,
    sma_50            DOUBLE PRECISION, sma_200 DOUBLE PRECISION,
    rsi_9             DOUBLE PRECISION, rsi_14 DOUBLE PRECISION,
    stoch_rsi_k       DOUBLE PRECISION, stoch_rsi_d DOUBLE PRECISION,
    macd              DOUBLE PRECISION, macd_signal DOUBLE PRECISION, macd_histogram DOUBLE PRECISION,
    atr_14            DOUBLE PRECISION, atr_20 DOUBLE PRECISION,
    bb_upper          DOUBLE PRECISION, bb_lower DOUBLE PRECISION, bb_width DOUBLE PRECISION, bb_pct DOUBLE PRECISION,
    obv               DOUBLE PRECISION, rvol DOUBLE PRECISION, rvol_10 DOUBLE PRECISION,
    vwap              DOUBLE PRECISION, price_vs_vwap DOUBLE PRECISION,
    price_vs_ema9     DOUBLE PRECISION, price_vs_ema20 DOUBLE PRECISION,
    consecutive_up    INTEGER, consecutive_down INTEGER,
    realized_vol_short DOUBLE PRECISION, mins_since_open DOUBLE PRECISION,
    price_vs_ema9_atr DOUBLE PRECISION, price_vs_ema20_atr DOUBLE PRECISION,
    price_vs_vwap_atr DOUBLE PRECISION, ema_spread_atr DOUBLE PRECISION,
    ema9_slope DOUBLE PRECISION, bb_squeeze DOUBLE PRECISION, rsi_divergence DOUBLE PRECISION,
    intraday_return   DOUBLE PRECISION, high_low_spread_pct DOUBLE PRECISION,
    fwd_close_5bars   DOUBLE PRECISION, fwd_close_15bars DOUBLE PRECISION,
    fwd_close_30bars  DOUBLE PRECISION, fwd_close_60bars DOUBLE PRECISION,
    fwd_ret_5bars_bps DOUBLE PRECISION, fwd_ret_15bars_bps DOUBLE PRECISION,
    fwd_ret_30bars_bps DOUBLE PRECISION, fwd_ret_60bars_bps DOUBLE PRECISION,
    vix_close         DOUBLE PRECISION, vix_tercile VARCHAR(8),
    total_gex         DOUBLE PRECISION, gex_tercile VARCHAR(8),
    total_vex         DOUBLE PRECISION, vex_tercile VARCHAR(8),
    dealer_regime     VARCHAR(24), gamma_regime VARCHAR(20),
    gamma_balance_price DOUBLE PRECISION,
    gamma_flip        DOUBLE PRECISION,
    dist_to_gamma_flip_pct DOUBLE PRECISION,
    distance_to_king_pct DOUBLE PRECISION, distance_to_gate_pct DOUBLE PRECISION,
    computed_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, ts)
);
CREATE INDEX IF NOT EXISTS ix_strat_features_60m_combo ON strat_features_60m (ticker, strat_combo);
CREATE INDEX IF NOT EXISTS ix_strat_features_60m_date  ON strat_features_60m (bar_date);
CREATE INDEX IF NOT EXISTS ix_strat_features_60m_dr    ON strat_features_60m (dealer_regime);
