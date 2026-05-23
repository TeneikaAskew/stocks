-- Cloud SQL (PostgreSQL 15) schema for the trading system.
--
-- Run via:
--   gcloud sql connect INSTANCE_NAME --user=trading_user --database=trading < gcp/schema.sql
-- or:
--   psql "host=... dbname=trading user=trading_user" < gcp/schema.sql

-- ─────────────────────────────────────────────────────────
-- MARKET DATA
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS market_data_daily (
    id            BIGSERIAL PRIMARY KEY,
    ticker        VARCHAR(10)  NOT NULL,
    date          DATE         NOT NULL,
    open          DOUBLE PRECISION,
    high          DOUBLE PRECISION,
    low           DOUBLE PRECISION,
    close         DOUBLE PRECISION,
    volume        BIGINT,

    -- Moving averages (SMA from lib/indicators, period = suffix)
    ma_5          DOUBLE PRECISION,   -- SMA5
    ma_10         DOUBLE PRECISION,   -- SMA10
    ma_20         DOUBLE PRECISION,   -- SMA20
    ma_50         DOUBLE PRECISION,   -- SMA50
    sma_200       DOUBLE PRECISION,   -- SMA200 (bull/bear line)
    ema_9         DOUBLE PRECISION,
    ema_20        DOUBLE PRECISION,   -- renamed from ema_21 (ema_periods = [9,20,50])
    ema_50        DOUBLE PRECISION,

    -- Momentum
    rsi_14        DOUBLE PRECISION,
    rsi_9         DOUBLE PRECISION,
    rsi_30        DOUBLE PRECISION,
    stoch_rsi_k   DOUBLE PRECISION,
    stoch_rsi_d   DOUBLE PRECISION,
    macd          DOUBLE PRECISION,
    macd_signal   DOUBLE PRECISION,
    macd_histogram DOUBLE PRECISION,

    -- Volatility
    atr_14        DOUBLE PRECISION,
    atr_20        DOUBLE PRECISION,
    bb_upper      DOUBLE PRECISION,
    bb_lower      DOUBLE PRECISION,
    bb_width      DOUBLE PRECISION,
    bb_pct        DOUBLE PRECISION,
    volatility_20d      DOUBLE PRECISION,   -- 20-day annualised historical vol
    volatility_5d       DOUBLE PRECISION,
    high_low_spread     DOUBLE PRECISION,
    high_low_spread_pct DOUBLE PRECISION,

    -- Volume / breadth
    obv           DOUBLE PRECISION,
    rvol          DOUBLE PRECISION,

    -- Pattern
    consecutive_up      INTEGER,
    consecutive_down    INTEGER,

    -- Intraday-derived (VWAP from 1-min bars; stored as EOD value)
    vwap                DOUBLE PRECISION,
    price_vs_vwap       DOUBLE PRECISION,
    price_vs_ema9       DOUBLE PRECISION,
    price_vs_ema20      DOUBLE PRECISION,   -- renamed from price_vs_ema21

    -- Strat fields (populated by analyze_market_data)
    strat_candle        VARCHAR(10),
    strat_combo         VARCHAR(30),
    strat_setup         BOOLEAN,
    ftfc_score          DOUBLE PRECISION,
    ftfc_direction      VARCHAR(10),

    -- Split/dividend-adjusted close from AlphaVantage TIME_SERIES_DAILY_ADJUSTED
    adjusted_close      DOUBLE PRECISION,

    -- Metadata
    data_source   VARCHAR(50),
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_market_data_daily UNIQUE (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_market_data_daily_ticker_date
    ON market_data_daily (ticker, date DESC);


CREATE TABLE IF NOT EXISTS market_data_intraday (
    ticker      VARCHAR(10)  NOT NULL,
    interval    VARCHAR(5)   NOT NULL DEFAULT '1min',  -- '1min','5min','15min','30min','1h'
    ts          TIMESTAMPTZ  NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      BIGINT,
    data_source VARCHAR(50),                            -- 'alphavantage' | 'yfinance'
    inserted_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ticker, interval, ts)
) PARTITION BY LIST (ticker);

-- Per-ticker partitions (add more as needed)
CREATE TABLE IF NOT EXISTS market_data_intraday_spy
    PARTITION OF market_data_intraday FOR VALUES IN ('SPY');
CREATE TABLE IF NOT EXISTS market_data_intraday_iwm
    PARTITION OF market_data_intraday FOR VALUES IN ('IWM');
CREATE TABLE IF NOT EXISTS market_data_intraday_qqq
    PARTITION OF market_data_intraday FOR VALUES IN ('QQQ');
CREATE TABLE IF NOT EXISTS market_data_intraday_spx
    PARTITION OF market_data_intraday FOR VALUES IN ('SPX');
CREATE TABLE IF NOT EXISTS market_data_intraday_other
    PARTITION OF market_data_intraday DEFAULT;

CREATE INDEX IF NOT EXISTS idx_market_data_intraday_lookup
    ON market_data_intraday (ticker, interval, ts DESC);


-- ─────────────────────────────────────────────────────────
-- OPTIONS DATA
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS etf_options_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    ticker              VARCHAR(10)  NOT NULL,
    snapshot_ts         TIMESTAMPTZ  NOT NULL,
    snapshot_date       DATE         NOT NULL,
    market_session      VARCHAR(30),              -- OPEN_VOLATILE, MORNING, etc.

    -- Contract identifiers
    contract_symbol     VARCHAR(50),
    option_type         VARCHAR(5)   NOT NULL,    -- 'calls' | 'puts'
    expiration          DATE         NOT NULL,
    strike              DOUBLE PRECISION NOT NULL,
    in_the_money        BOOLEAN,

    -- Pricing
    bid                 DOUBLE PRECISION,
    ask                 DOUBLE PRECISION,
    mark                DOUBLE PRECISION,   -- (bid+ask)/2 mid price; real from AV, derived for Yahoo
    last_price          DOUBLE PRECISION,
    change              DOUBLE PRECISION,
    percent_change      DOUBLE PRECISION,

    -- Volume / OI
    volume              DOUBLE PRECISION,
    open_interest       DOUBLE PRECISION,

    -- IV
    implied_volatility  DOUBLE PRECISION,

    -- Greeks
    delta               DOUBLE PRECISION,
    gamma               DOUBLE PRECISION,
    theta               DOUBLE PRECISION,
    vega                DOUBLE PRECISION,
    rho                 DOUBLE PRECISION,

    -- Underlying at snapshot time
    underlying_price    DOUBLE PRECISION,

    -- Source: 'alphavantage' (EOD, real Greeks) | 'yahooquery' (intraday, B-S Greeks)
    data_source         VARCHAR(30),

    inserted_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_etf_options_snapshot
        UNIQUE (ticker, snapshot_ts, option_type, expiration, strike)
);

CREATE INDEX IF NOT EXISTS idx_etf_options_ticker_date
    ON etf_options_snapshots (ticker, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_etf_options_expiry
    ON etf_options_snapshots (ticker, expiration, strike);

-- Track 1 (2026-05-23): partial index on REALTIME rows only.
-- The premarket-brief gamma freshness probe needs to find "is there
-- a REALTIME row for this ticker within the last 15 days?" — without
-- this partial index the planner walks every EOD row in date order
-- looking for the rare REALTIME match (5s+ on SPY's 14k contracts/day).
-- The partial index has one entry per REALTIME row only, so the probe
-- becomes index-only and sub-100ms even at table scale.
-- See gcp/premarket_brief.py:_load_gamma_freshness and
-- docs/plans/REALTIME_OPTIONS_MULTITRACK_PLAN.md Track 1.
CREATE INDEX IF NOT EXISTS idx_etf_options_realtime
    ON etf_options_snapshots (ticker, snapshot_ts DESC)
    WHERE market_session = 'REALTIME';


-- Phase A (Heatseeker-style grid): per-snapshot per-strike per-expiration
-- aggregate. Mirrors the 1-D aggregate `lib.gamma.aggregate_by_strike` but
-- keeps the expiration dimension intact so consumers can render the 2-D
-- `strike × expiration` heatmap. CREATE OR REPLACE so re-applying the
-- schema picks up math fixes without dropping dependents.
--
-- Read pattern: usually filtered by (ticker, snapshot_ts) — uses
-- idx_etf_options_realtime for the live path and idx_etf_options_ticker_date
-- for the historical path.
--
-- Sign convention (matches lib.gamma):
--   net_gamma = call_gamma×OI − put_gamma×OI
--   net_vega  = call_vega×OI  − put_vega×OI
--   GEX/VEX dollar conversion stays in the Python layer so callers
--   share one source of truth for the multipliers; this view exposes
--   only the raw aggregates.
--
-- See docs/plans/HEATSEEKER_STYLE_GAMMA_PLAN.md §4.1 for the design.
CREATE OR REPLACE VIEW v_etf_options_node AS
SELECT
    ticker,
    snapshot_ts,
    snapshot_date,
    market_session,
    expiration,
    strike,
    -- Net (calls add, puts subtract) — same sign convention as lib.gamma.
    SUM(
        CASE
            WHEN option_type = 'calls'
                THEN COALESCE(gamma, 0) * COALESCE(open_interest, 0)
            WHEN option_type = 'puts'
                THEN -COALESCE(gamma, 0) * COALESCE(open_interest, 0)
            ELSE 0
        END
    )                                                                AS net_gamma,
    SUM(
        CASE
            WHEN option_type = 'calls'
                THEN COALESCE(vega, 0) * COALESCE(open_interest, 0)
            WHEN option_type = 'puts'
                THEN -COALESCE(vega, 0) * COALESCE(open_interest, 0)
            ELSE 0
        END
    )                                                                AS net_vega,
    -- Per-side gamma×OI (unsigned, so the dollar-conversion layer can
    -- decide whether to subtract puts).
    SUM(CASE WHEN option_type = 'calls'
             THEN COALESCE(gamma, 0) * COALESCE(open_interest, 0) ELSE 0 END) AS call_gamma_oi,
    SUM(CASE WHEN option_type = 'puts'
             THEN COALESCE(gamma, 0) * COALESCE(open_interest, 0) ELSE 0 END) AS put_gamma_oi,
    SUM(CASE WHEN option_type = 'calls'
             THEN COALESCE(vega, 0)  * COALESCE(open_interest, 0) ELSE 0 END) AS call_vega_oi,
    SUM(CASE WHEN option_type = 'puts'
             THEN COALESCE(vega, 0)  * COALESCE(open_interest, 0) ELSE 0 END) AS put_vega_oi,
    -- OI / volume context.
    SUM(CASE WHEN option_type = 'calls' THEN COALESCE(open_interest, 0) ELSE 0 END) AS call_oi,
    SUM(CASE WHEN option_type = 'puts'  THEN COALESCE(open_interest, 0) ELSE 0 END) AS put_oi,
    SUM(CASE WHEN option_type = 'calls' THEN COALESCE(volume, 0) ELSE 0 END)        AS call_volume,
    SUM(CASE WHEN option_type = 'puts'  THEN COALESCE(volume, 0) ELSE 0 END)        AS put_volume
FROM etf_options_snapshots
WHERE data_source = 'alphavantage'
GROUP BY ticker, snapshot_ts, snapshot_date, market_session, expiration, strike;


CREATE TABLE IF NOT EXISTS earnings_options_snapshots (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              VARCHAR(10)  NOT NULL,
    snapshot_ts         TIMESTAMPTZ  NOT NULL,
    snapshot_date       DATE         NOT NULL,

    -- Contract identifiers
    contract_symbol     VARCHAR(50),
    option_type         VARCHAR(5)   NOT NULL,    -- 'calls' | 'puts'
    expiration          DATE         NOT NULL,
    strike              DOUBLE PRECISION NOT NULL,
    in_the_money        BOOLEAN,
    contract_size       VARCHAR(20),

    -- Pricing
    bid                 DOUBLE PRECISION,
    ask                 DOUBLE PRECISION,
    last_price          DOUBLE PRECISION,
    change              DOUBLE PRECISION,
    percent_change      DOUBLE PRECISION,
    last_trade_date     TIMESTAMPTZ,

    -- Volume / OI
    volume              DOUBLE PRECISION,
    open_interest       DOUBLE PRECISION,

    -- IV
    implied_volatility  DOUBLE PRECISION,

    -- Greeks
    delta               DOUBLE PRECISION,
    gamma               DOUBLE PRECISION,
    theta               DOUBLE PRECISION,
    vega                DOUBLE PRECISION,
    rho                 DOUBLE PRECISION,

    -- Underlying at snapshot time
    underlying_price    DOUBLE PRECISION,
    data_source         VARCHAR(30) DEFAULT 'daily_eod',

    inserted_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_earnings_options_snapshot
        UNIQUE (symbol, snapshot_ts, option_type, expiration, strike)
);

CREATE INDEX IF NOT EXISTS idx_earnings_options_symbol_date
    ON earnings_options_snapshots (symbol, snapshot_date DESC);


-- ─────────────────────────────────────────────────────────
-- DAILY RATES (FRED-sourced macro inputs for BSM Greeks)
-- ─────────────────────────────────────────────────────────
-- Populated by gcp.fetchers.fetch_fred_rates. Used by
-- lib.options_greeks.get_rate_and_yield to look up the risk-free
-- rate (DGS3MO 3-month Treasury) and dividend yield per snapshot
-- date so historical backfills don't all share one constant.
-- The fetcher writes the FRED DGS3MO series; sp500_div_yld is a
-- configurable constant (FRED doesn't publish a clean S&P 500
-- dividend-yield series).

CREATE TABLE IF NOT EXISTS daily_rates (
    date           DATE PRIMARY KEY,
    dgs3mo         DOUBLE PRECISION,
    sp500_div_yld  DOUBLE PRECISION,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_rates_date
    ON daily_rates (date DESC);


-- ─────────────────────────────────────────────────────────
-- ARCHIVE TABLES (Yahoo Finance legacy data)
-- ─────────────────────────────────────────────────────────
-- Yahoo data was moved here when the system cut over to AlphaVantage.
-- Production tables should only contain data_source = 'alphavantage'.
-- Archive tables preserve legacy rows (data_source IS NULL or in
-- yfinance/yahoo/yahooquery) for forensics and historical comparison.
-- Structure mirrors the source table via CREATE TABLE ... (LIKE src INCLUDING ...).
-- Populated + maintained by scripts/archive_yahoo_data.py.

CREATE TABLE IF NOT EXISTS archive_yahoo_market_data_daily
    (LIKE market_data_daily INCLUDING ALL);

CREATE TABLE IF NOT EXISTS archive_yahoo_market_data_intraday
    (LIKE market_data_intraday INCLUDING DEFAULTS INCLUDING CONSTRAINTS);

CREATE TABLE IF NOT EXISTS archive_yahoo_etf_options_snapshots
    (LIKE etf_options_snapshots INCLUDING ALL);

CREATE TABLE IF NOT EXISTS archive_yahoo_earnings_options_snapshots
    (LIKE earnings_options_snapshots INCLUDING ALL);


-- ─────────────────────────────────────────────────────────
-- EARNINGS CALENDAR (strategy-level, one row per ticker/date/strategy)
-- Separate from earnings_options_snapshots which stores per-contract
-- options chain data at a different granularity.
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS earnings_calendar (
    id                  BIGSERIAL PRIMARY KEY,

    -- Calendar / identity
    ticker              VARCHAR(10)  NOT NULL,
    earnings_date       DATE         NOT NULL,
    company_name        VARCHAR(200),
    earnings_time       VARCHAR(30),           -- 'premarket', 'postmarket', etc.
    eps_estimate        DOUBLE PRECISION,
    market_cap          DOUBLE PRECISION,
    sector              VARCHAR(100),
    has_options         BOOLEAN,
    expected_move       DOUBLE PRECISION,

    -- Strategy pick (EW-specific; empty string for UW rows)
    strategy            VARCHAR(50) NOT NULL DEFAULT '',
    strike              DOUBLE PRECISION,
    expiration          DATE,
    premium             DOUBLE PRECISION,
    score               DOUBLE PRECISION,

    -- Source tracking
    data_source         VARCHAR(30) NOT NULL,  -- 'alphavantage' | 'unusual_whales' | 'earnings_whispers'
    fetched_at          TIMESTAMPTZ,

    -- AlphaVantage date-of-truth (from SEC filings). Original source-reported
    -- earnings_date is preserved; this column adds AV's date for cross-reference.
    -- For AV rows this equals earnings_date. For EW/UW rows it is populated when
    -- the same ticker exists in the AV fetch, else NULL.
    av_earnings_date    DATE,

    -- Hit / performance tracking (backfilled post-earnings)
    strike_hit          JSONB,                 -- array of 6 price ratios (day 0-5)
    hit_date            DATE,
    max_favorable       JSONB,                 -- per-day max favorable moves
    min_unfavorable     JSONB,                 -- per-day min unfavorable moves

    -- Daily price checks (stock price at each day post-earnings)
    day0_check          DOUBLE PRECISION,
    day1_check          DOUBLE PRECISION,
    day2_check          DOUBLE PRECISION,
    day3_check          DOUBLE PRECISION,
    day4_check          DOUBLE PRECISION,
    day5_check          DOUBLE PRECISION,

    -- Result
    exp_result          DOUBLE PRECISION,      -- price at expiration
    risk_reward         DOUBLE PRECISION,

    -- Technical indicators at hit (JSONB arrays, one value per day 0-5)
    hit_rsi             JSONB,
    hit_sma20           JSONB,
    hit_sma50           JSONB,
    hit_ema9            JSONB,
    hit_ema21           JSONB,
    hit_vwap            JSONB,
    hit_rvol            JSONB,
    hit_atr             JSONB,
    hit_price_vs_sma20  JSONB,
    hit_price_vs_vwap   JSONB,

    -- Daily OHLC + volume (JSONB array of {o, h, l, c, v} objects)
    ohlc_volume         JSONB,

    -- Metadata
    inserted_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_earnings_calendar
        UNIQUE (ticker, earnings_date, strategy, data_source)
);

CREATE INDEX IF NOT EXISTS idx_earnings_calendar_ticker_date
    ON earnings_calendar (ticker, earnings_date DESC);
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_date
    ON earnings_calendar (earnings_date DESC);
CREATE INDEX IF NOT EXISTS idx_earnings_calendar_source
    ON earnings_calendar (data_source, earnings_date DESC);

-- ── UW liquidity / quality enrichments (added 2026-04-26) ──────────────────
-- Idempotent ALTERs so existing deployments pick these up without a rebuild.
-- Populated by the UnusualWhales path in scripts/fetch_earnings_calendar.py;
-- AV-only and EW-only rows leave them NULL, which is fine for ranking
-- (sort uses NULLS LAST) and for the brief's within-tier ordering.
ALTER TABLE earnings_calendar
    ADD COLUMN IF NOT EXISTS is_s_p_500          BOOLEAN,
    ADD COLUMN IF NOT EXISTS stock_volume        BIGINT,
    ADD COLUMN IF NOT EXISTS options_volume      BIGINT,           -- call_vol + put_vol
    ADD COLUMN IF NOT EXISTS open_interest       BIGINT,           -- UW: oi
    ADD COLUMN IF NOT EXISTS rv_1d_last_12q      DOUBLE PRECISION, -- realized vol over last 12 quarters
    ADD COLUMN IF NOT EXISTS last_1d_reactions   JSONB,            -- array of past 1-day post-earnings moves
    -- Beat/miss enrichment (added 2026-04-30) — populated by the Yahoo
    -- Calendars TAS rows after a company reports. Lets the brief render
    -- "EPS 0.44 → 0.41 ❌ miss (-6.8%)" inline so traders see the
    -- expectation delta alongside the pre-market gap reaction.
    ADD COLUMN IF NOT EXISTS eps_actual          DOUBLE PRECISION, -- Yahoo: Reported EPS
    ADD COLUMN IF NOT EXISTS eps_surprise_pct    DOUBLE PRECISION, -- Yahoo: Surprise(%)
    -- EW strike verdict (added 2026-04-30) — populated by
    -- evaluate_ew_strikes.py once a report day's session closes.
    -- The brief renders "Q-1: HIT in 5m, held 142m, day +1.2%" inline
    -- so traders can judge whether a HIT was a tradeable sustained move
    -- or a fakeout, and whether it ran with or against the day's tape.
    ADD COLUMN IF NOT EXISTS ew_high_on_day      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ew_low_on_day       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS ew_close_on_day     DOUBLE PRECISION,
    -- HIT (long-call/long-put strike was crossed intraday)
    -- MISS (strike never touched)
    -- KEPT (covered-call strike held below at close)
    -- ASSIGNED (covered-call strike crossed above by close)
    ADD COLUMN IF NOT EXISTS ew_strike_verdict   VARCHAR(16),
    -- Signed % vs strike: + for above, − for below. Sign convention is
    -- direction-agnostic so the brief can display "HIT +14.6%" or
    -- "MISS -10.1%" without needing the verdict to interpret it.
    ADD COLUMN IF NOT EXISTS ew_strike_move_pct  DOUBLE PRECISION,
    -- Time-to-hit in minutes from regular session open (9:30 AM ET)
    -- to the first bar that crossed strike in the strategy's direction.
    -- A small number means the move happened on the open print; large
    -- numbers mean late-session move. NULL when verdict = MISS.
    ADD COLUMN IF NOT EXISTS ew_minutes_to_hit   INTEGER,
    -- Total minutes during regular session that the underlying was
    -- on the profitable side of strike (above for long calls / spreads,
    -- below for long puts). Distinguishes "5-minute fakeout" from
    -- "sustained intraday momentum".
    ADD COLUMN IF NOT EXISTS ew_minutes_in_zone  INTEGER,
    -- Day's directional bias: signed open-to-close % change. Lets the
    -- brief show "HIT in 5m, day -2.1%" — strike got hit on a counter-
    -- trend pop that immediately faded. Positive = bullish day.
    ADD COLUMN IF NOT EXISTS ew_day_change_pct   DOUBLE PRECISION;

CREATE INDEX IF NOT EXISTS idx_earnings_calendar_sp500_date
    ON earnings_calendar (earnings_date DESC, is_s_p_500 DESC NULLS LAST);

-- ─────────────────────────────────────────────────────────
-- HELPER: set_updated_at() — generic BEFORE UPDATE trigger fn.
-- Defined here, ahead of its first use, so a single-pass apply
-- of this file (psql -f schema.sql -v ON_ERROR_STOP=1) succeeds.
-- Shared by trg_earnings_calendar_updated, trg_market_data_daily_updated,
-- and the other trg_*_updated triggers further down this file.
-- ─────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_earnings_calendar_updated ON earnings_calendar;
CREATE TRIGGER trg_earnings_calendar_updated
    BEFORE UPDATE ON earnings_calendar
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ─────────────────────────────────────────────────────────
-- EARNINGS HISTORY (AlphaVantage EARNINGS endpoint, per-ticker)
-- Backward-looking quarterly EPS history, separate from the
-- forward-looking earnings_calendar table. Used by the ranker to
-- compute historical post-earnings reaction stats (avg T+1 move,
-- direction consistency, surprise vs. price reaction correlation).
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS earnings_history (
    id                  BIGSERIAL PRIMARY KEY,
    ticker              VARCHAR(10)  NOT NULL,
    fiscal_date_ending  DATE         NOT NULL,
    reported_date       DATE,
    reported_eps        DOUBLE PRECISION,
    estimated_eps       DOUBLE PRECISION,
    surprise            DOUBLE PRECISION,
    surprise_pct        DOUBLE PRECISION,
    inserted_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_earnings_history UNIQUE (ticker, fiscal_date_ending)
);

CREATE INDEX IF NOT EXISTS idx_earnings_history_ticker_reported
    ON earnings_history (ticker, reported_date DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_earnings_history_reported
    ON earnings_history (reported_date DESC NULLS LAST);

-- Per-quarter report timing (added 2026-04-30) — populated from AV
-- EARNINGS endpoint's `reportTime` field ('pre-market' | 'post-market').
-- AV is occasionally wrong (e.g. NVDA 2026-02-25 was reported as
-- 'pre-market' but actually released after-hours). The
-- yahoo_report_time column (added 2026-05-01) is the validation
-- source: derived from yfinance.Calendars Event Start Date in ET
-- (>= 16:00 = post-market; <= 09:30 = pre-market). The
-- earnings_reactions populator prefers yahoo_report_time over
-- report_time when both are present.
ALTER TABLE earnings_history
    ADD COLUMN IF NOT EXISTS report_time         VARCHAR(20),
    ADD COLUMN IF NOT EXISTS yahoo_report_time   VARCHAR(20);


-- ─────────────────────────────────────────────────────────
-- EARNINGS REACTIONS (per-quarter post-earnings reaction profile)
-- One row per (ticker, fiscal_date_ending). Joins earnings_history
-- with market_data_daily to compute timing-aware reaction stats:
-- pre-earnings drift, reaction-day gap, intraday range, multi-horizon
-- sustain, direction consistency, reversal flag. Populated by
-- gcp/fetchers/compute_earnings_reactions.py (Phase 1 deliverable).
--
-- The brief reads aggregated 12Q stats from this table to rank
-- tomorrow's reporters by playability_score.
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS earnings_reactions (
    id                          BIGSERIAL PRIMARY KEY,
    ticker                      VARCHAR(10)  NOT NULL,
    fiscal_date_ending          DATE         NOT NULL,
    reported_date               DATE         NOT NULL,

    -- Timing (canonical source: earnings_history.report_time)
    reaction_basis              VARCHAR(3),     -- 'AMC' or 'BMO'

    -- EPS context (denormalized from earnings_history for query speed)
    reported_eps                DOUBLE PRECISION,
    estimated_eps               DOUBLE PRECISION,
    surprise_pct                DOUBLE PRECISION,

    -- Pre-earnings drift (D-10 → D-1)
    d_minus_10_close            DOUBLE PRECISION,
    d_minus_1_close             DOUBLE PRECISION,
    pre_earnings_drift_10d_pct  DOUBLE PRECISION,    -- (D-1 close - D-10 close) / D-10 close × 100

    -- Finer-grained pre-earnings horizons (added 2026-05-14 — symmetric
    -- with sustain_3d/5d/10d post-earnings). Used by the pre-drift
    -- pipeline to surface tickers that consistently run UP or fade DOWN
    -- in the days leading into a print.
    d_minus_5_close             DOUBLE PRECISION,
    d_minus_3_close             DOUBLE PRECISION,
    d_minus_2_close             DOUBLE PRECISION,
    drift_3d_pct                DOUBLE PRECISION,    -- (D-1 close - D-3 close) / D-3 close × 100
    drift_5d_pct                DOUBLE PRECISION,    -- (D-1 close - D-5 close) / D-5 close × 100
    -- Behavioral flags (mirror direction_consistent_5d / is_reversal_5d).
    pre_drift_consistent_5d     BOOLEAN,            -- sign(drift_5d_pct) == sign(drift_3d_pct) AND |drift_5d_pct| >= 1.0
    pre_drift_reverses_into_gap BOOLEAN,            -- sign(drift_5d_pct) != sign(reaction_gap_pct) — known only post-event, useful for backtests
    -- Intraday range over the pre-earnings window (symmetric with the post-
    -- earnings max_high_*d_pct / min_low_*d_pct columns). Anchored at the
    -- START of each window (D-N close), so a positive max_high_pre_5d_pct
    -- means the stock printed at least one intraday high N% above where it
    -- closed 5 trading days before the report. Catches the "ran and gave
    -- back" pattern that pure close-to-close drift misses.
    max_high_pre_3d_pct         DOUBLE PRECISION,   -- (MAX(high) in D-3..D-1  - D-3 close)  / D-3 close  × 100
    min_low_pre_3d_pct          DOUBLE PRECISION,   -- (MIN(low)  in D-3..D-1  - D-3 close)  / D-3 close  × 100
    max_high_pre_5d_pct         DOUBLE PRECISION,
    min_low_pre_5d_pct          DOUBLE PRECISION,
    max_high_pre_10d_pct        DOUBLE PRECISION,
    min_low_pre_10d_pct         DOUBLE PRECISION,

    -- Report day (D)
    d_open                      DOUBLE PRECISION,
    d_high                      DOUBLE PRECISION,
    d_low                       DOUBLE PRECISION,
    d_close                     DOUBLE PRECISION,
    pre_report_gap_pct          DOUBLE PRECISION,    -- (D open - D-1 close) / D-1 close × 100

    -- Day after (D+1)
    d_plus_1_open               DOUBLE PRECISION,
    d_plus_1_high               DOUBLE PRECISION,
    d_plus_1_low                DOUBLE PRECISION,
    d_plus_1_close              DOUBLE PRECISION,
    post_gap_pct                DOUBLE PRECISION,    -- (D+1 open - D close) / D close × 100

    -- Timing-aware reaction (THE column the score uses)
    -- For BMO: equals pre_report_gap_pct (D open vs D-1 close)
    -- For AMC: equals post_gap_pct (D+1 open vs D close)
    reaction_gap_pct            DOUBLE PRECISION,
    reaction_anchor_price       DOUBLE PRECISION,    -- D close (BMO) or D+1 open (AMC)
    reaction_max_run_pct        DOUBLE PRECISION,    -- max(high - open) / open on reaction day
    reaction_max_drawdown_pct   DOUBLE PRECISION,    -- min(low - open) / open on reaction day

    -- Multi-horizon sustain (anchored at reaction_anchor_price)
    d_plus_3_close              DOUBLE PRECISION,
    sustain_3d_pct              DOUBLE PRECISION,
    d_plus_5_close              DOUBLE PRECISION,
    sustain_5d_pct              DOUBLE PRECISION,
    d_plus_10_close             DOUBLE PRECISION,
    sustain_10d_pct             DOUBLE PRECISION,

    -- Computed flags
    direction_consistent_5d     BOOLEAN,            -- sign(reaction_gap) == sign(sustain_5d)
    is_reversal_5d              BOOLEAN,            -- sign flip + |sustain_5d| >= 0.5*|reaction_gap|

    -- Provenance
    inserted_at                 TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_earnings_reactions UNIQUE (ticker, fiscal_date_ending),
    CONSTRAINT ck_earnings_reactions_basis
        CHECK (reaction_basis IS NULL OR reaction_basis IN ('AMC', 'BMO'))
);

CREATE INDEX IF NOT EXISTS idx_earnings_reactions_ticker_reported
    ON earnings_reactions (ticker, reported_date DESC);

CREATE INDEX IF NOT EXISTS idx_earnings_reactions_reported
    ON earnings_reactions (reported_date DESC);

-- ATR context around earnings (added 2026-05-04, refined same day).
-- The first cut (atr_14_d_minus_1 / atr_14_d / day_range_in_atr_units)
-- always picked D as the reaction day, which is wrong for AMC reports —
-- AMC reports drop AFTER D's close, so the reaction trades on D+1.
-- That made every AMC name (the majority) show ~2× ATR ranges when
-- third-party analytics show 6×. Replaced with timing-aware columns:
--
--   pre_report_atr  = ATR through the last full bar BEFORE the reaction
--                     (D-1 for BMO, D for AMC). The "going-in" volatility
--                     regime — the natural denominator for sizing.
--   post_report_atr = ATR through the reaction day (D for BMO, D+1 for
--                     AMC). Includes the spike; delta vs pre is a
--                     regime-shift signal.
--   reaction_day_range = high - low on the reaction-day bar.
--   reaction_day_range_in_atr_units = reaction_day_range / pre_report_atr.
--
-- Computed in compute_earnings_reactions.py from the existing
-- market_data_daily window — pure-join, no extra API calls.
ALTER TABLE earnings_reactions
    ADD COLUMN IF NOT EXISTS pre_report_atr                    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_report_atr_pct                DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS post_report_atr                   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS reaction_day_range                DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS reaction_day_range_in_atr_units   DOUBLE PRECISION;

-- Drop the buggy first-cut columns. No downstream consumers — they were
-- added the same day in the same PR and only my SQL UPDATE populated
-- them. Safer to drop now while the surface area is small than to leave
-- them lurking with wrong values.
ALTER TABLE earnings_reactions
    DROP COLUMN IF EXISTS atr_14_d_minus_1,
    DROP COLUMN IF EXISTS atr_pct_d_minus_1,
    DROP COLUMN IF EXISTS atr_14_d,
    DROP COLUMN IF EXISTS day_range_in_atr_units;

-- Best-exit / worst-drawdown over the swing window (added 2026-05-04).
-- The sustain_*_pct columns above use the CLOSE on day N — but a swing
-- trader can exit at any point during the hold window. These give the
-- actual high/low touched, expressed as % vs reaction_anchor_price
-- (the same anchor the sustain columns use). Bounded by the same
-- anomaly threshold so stock-split artifacts don't poison the values.
ALTER TABLE earnings_reactions
    ADD COLUMN IF NOT EXISTS max_high_3d_pct  DOUBLE PRECISION,    -- best UP exit within 3 trading days
    ADD COLUMN IF NOT EXISTS min_low_3d_pct   DOUBLE PRECISION,    -- worst drawdown within 3 trading days
    ADD COLUMN IF NOT EXISTS max_high_5d_pct  DOUBLE PRECISION,    -- best UP exit within 5 trading days
    ADD COLUMN IF NOT EXISTS min_low_5d_pct   DOUBLE PRECISION,    -- worst drawdown within 5 trading days
    ADD COLUMN IF NOT EXISTS max_high_10d_pct DOUBLE PRECISION,    -- best UP exit within 10 trading days
    ADD COLUMN IF NOT EXISTS min_low_10d_pct  DOUBLE PRECISION;    -- worst drawdown within 10 trading days


-- Pre-earnings drift (D-5/D-3/D-2) — added 2026-05-14 to feed the
-- pre-drift analysis pipeline (symmetric with post-earnings sustain_3d/
-- 5d/10d). Live migration is idempotent; next compute-earnings-reactions
-- run with --force --scope=full populates every historical row.
ALTER TABLE earnings_reactions
    ADD COLUMN IF NOT EXISTS d_minus_5_close             DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS d_minus_3_close             DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS d_minus_2_close             DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS drift_3d_pct                DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS drift_5d_pct                DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_drift_consistent_5d     BOOLEAN,
    ADD COLUMN IF NOT EXISTS pre_drift_reverses_into_gap BOOLEAN,
    -- Intraday high/low over pre-earnings window (symmetric with post-
    -- earnings max_high_*d_pct / min_low_*d_pct). Anchored at D-N close.
    ADD COLUMN IF NOT EXISTS max_high_pre_3d_pct         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS min_low_pre_3d_pct          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS max_high_pre_5d_pct         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS min_low_pre_5d_pct          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS max_high_pre_10d_pct        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS min_low_pre_10d_pct         DOUBLE PRECISION;


-- ─────────────────────────────────────────────────────────
-- SEC EDGAR FILINGS (8-K material events, 10-Q/10-K, etc.)
-- Free real-time material-event catalyst stream. Each row is one
-- form filing per (cik, accession_number). The `items` array holds
-- 8-K item codes (e.g. ['1.01','7.01']) — used by the ranker's
-- catalyst signal to detect M&A (1.01), exec changes (5.02), etc.
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sec_filings (
    id                  BIGSERIAL PRIMARY KEY,
    ticker              VARCHAR(10),               -- nullable: not every CIK has a public ticker
    cik                 VARCHAR(20)   NOT NULL,
    accession_number    VARCHAR(30)   NOT NULL,
    form                VARCHAR(20)   NOT NULL,    -- '8-K', '10-Q', '10-K', etc.
    filing_date         DATE          NOT NULL,
    report_date         DATE,                       -- event date (often == filing_date)
    items               TEXT[],                     -- 8-K item codes
    primary_doc         VARCHAR(200),
    inserted_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_sec_filings UNIQUE (cik, accession_number)
);

CREATE INDEX IF NOT EXISTS idx_sec_filings_ticker_date
    ON sec_filings (ticker, filing_date DESC);

CREATE INDEX IF NOT EXISTS idx_sec_filings_form_date
    ON sec_filings (form, filing_date DESC);

CREATE INDEX IF NOT EXISTS idx_sec_filings_items
    ON sec_filings USING GIN (items);


-- ─────────────────────────────────────────────────────────
-- INSIDER TRANSACTIONS (AlphaVantage INSIDER_TRANSACTIONS endpoint)
-- Form 4 filings: every officer/director/10%-owner buy or sell.
-- The ranker derives a "cluster" signal from these (3+ insiders in
-- 30 days, single insider >$1M, etc.) — strong directional tell on
-- single names.
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS insider_transactions (
    id                  BIGSERIAL PRIMARY KEY,
    ticker              VARCHAR(10)  NOT NULL,
    transaction_date    DATE         NOT NULL,
    executive           VARCHAR(200),
    title               VARCHAR(200),
    transaction_type    VARCHAR(20),     -- 'A' = acquired (buy), 'D' = disposed (sell)
    shares              DOUBLE PRECISION,
    share_price         DOUBLE PRECISION,
    transaction_value   DOUBLE PRECISION, -- shares × share_price (computed)
    inserted_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    -- Same insider can have multiple same-day transactions at different prices;
    -- include the type so we can distinguish a partial sell from a partial buy.
    CONSTRAINT uq_insider_transactions
        UNIQUE (ticker, transaction_date, executive, transaction_type, shares, share_price)
);

CREATE INDEX IF NOT EXISTS idx_insider_transactions_ticker_date
    ON insider_transactions (ticker, transaction_date DESC);


-- ─────────────────────────────────────────────────────────
-- TOP MOVERS (AlphaVantage TOP_GAINERS_LOSERS, daily snapshot)
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS top_movers_daily (
    id                BIGSERIAL PRIMARY KEY,
    snapshot_date     DATE         NOT NULL,
    ticker            VARCHAR(10)  NOT NULL,
    category          VARCHAR(20)  NOT NULL,  -- 'top_gainers' | 'top_losers' | 'most_active'
    rank              INTEGER,
    price             DOUBLE PRECISION,
    change_amount     DOUBLE PRECISION,
    change_pct        DOUBLE PRECISION,
    volume            BIGINT,
    inserted_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_top_movers_daily UNIQUE (snapshot_date, ticker, category)
);

CREATE INDEX IF NOT EXISTS idx_top_movers_date_category
    ON top_movers_daily (snapshot_date DESC, category);


-- ─────────────────────────────────────────────────────────
-- RANKER AUDIT
-- One row per call to lib.agents.ranker.rank_tickers. Captures inputs
-- (weights, candidate count) and outputs (ranked list with full score
-- breakdown) so any past ranking decision is reproducible without
-- having to re-run the SQL signals.
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ranker_runs (
    id                 UUID         PRIMARY KEY,
    run_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    candidate_count    INTEGER      NOT NULL,
    excluded_count     INTEGER      NOT NULL,
    weights_used       JSONB        NOT NULL,
    results            JSONB        NOT NULL,    -- the ranked list with breakdowns
    duration_ms        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_ranker_runs_run_at
    ON ranker_runs (run_at DESC);


-- ─────────────────────────────────────────────────────────
-- SIGNALS & TRADES
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS signal_alerts (
    id                  BIGSERIAL PRIMARY KEY,
    ticker              VARCHAR(10)  NOT NULL,
    alert_ts            TIMESTAMPTZ  NOT NULL,
    alert_date          DATE         NOT NULL,
    direction           VARCHAR(4)   NOT NULL,   -- 'CALL' | 'PUT'

    -- Scoring
    base_score          DOUBLE PRECISION,
    strat_bonus         DOUBLE PRECISION,
    total_score         DOUBLE PRECISION,
    strength_label      VARCHAR(20),
    position_size       DOUBLE PRECISION,

    -- Price context
    price_at_signal     DOUBLE PRECISION,
    target_price        DOUBLE PRECISION,
    time_stop_minutes   INTEGER,

    -- Indicators at signal time
    rsi                 DOUBLE PRECISION,
    rvol                DOUBLE PRECISION,

    -- ORB levels
    orb_5m_high         DOUBLE PRECISION,
    orb_5m_low          DOUBLE PRECISION,
    orb_15m_high        DOUBLE PRECISION,
    orb_15m_low         DOUBLE PRECISION,

    -- Conditions list (JSON array)
    conditions_met      JSONB,

    inserted_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_alerts_ticker_date
    ON signal_alerts (ticker, alert_date DESC);

-- v2 strat refactor: record which Strat level a signal broke (PDH, PDL, PWH, ...).
ALTER TABLE signal_alerts
    ADD COLUMN IF NOT EXISTS level_broken VARCHAR(20);

-- Phase 1.6 — strategy-agreement payload.
-- When momentum + mean_reversion both fire on the same bar AND target the
-- same direction, that's a high-conviction "stacked" signal. We record the
-- agreement payload (which strategies fired, their directions, base_scores,
-- and a composite score that boosts agreement) here so downstream consumers
-- (Discord embed sort, post-mortem queries) can surface stacked signals.
-- Shape when populated:
--   {
--     "agree": true,
--     "strategies":      ["momentum", "mean_reversion"],
--     "directions":      ["CALL", "CALL"],
--     "base_scores":     [4.0, 3.0],
--     "conditions_met":  [
--       ["rsi_thrust_3", "rvol_recent_20", "atr_expansion"],
--       ["consecutive_down", "rsi_oversold_zone", "below_vwap"]
--     ],
--     "composite_score": 5.0
--   }
-- NULL when only one strategy fired (the common case).
-- Per-leg conditions_met added Track D / G.P3.4 so post-mortems can
-- answer "which conditions did momentum hit when stacked with mean-
-- reversion" without joining back to per-strategy tables. Order of
-- inner arrays matches `strategies`.
--
-- Empirical rate (Track D audit 2026-05-08, § 6 / G.P2.9):
-- 17 stacked alerts of 782 fires = 2.2% (per-ticker 1.4-3.2%; QQQ
-- highest). The pre-Phase-0.7.x estimate of ~21% in
-- docs/plans/SIGNAL_QUALITY_TEST_PLAN.md is stale — momentum's gate
-- tightened over subsequent phases, lowering fires without a
-- corresponding schema-doc update.
ALTER TABLE signal_alerts
    ADD COLUMN IF NOT EXISTS strategy_agreement JSONB;


CREATE TABLE IF NOT EXISTS trades (
    id              BIGSERIAL PRIMARY KEY,
    ticker          VARCHAR(10)  NOT NULL,
    direction       VARCHAR(4)   NOT NULL,   -- 'CALL' | 'PUT'
    entry_time      TIMESTAMPTZ,
    entry_price     DOUBLE PRECISION,
    exit_time       TIMESTAMPTZ,
    exit_price      DOUBLE PRECISION,
    exit_reason     VARCHAR(50),
    signal_strength DOUBLE PRECISION,
    total_score     DOUBLE PRECISION,
    position_size   DOUBLE PRECISION,
    return_pct      DOUBLE PRECISION,
    conditions_met  JSONB,
    strat_combo     VARCHAR(30),
    ftfc_score      DOUBLE PRECISION,
    trade_date      DATE,
    inserted_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trades_ticker_date
    ON trades (ticker, trade_date DESC);


-- ─────────────────────────────────────────────────────────
-- PLATFORM JOURNAL (user-authored manual trade log)
-- Separate from the automated pipeline `trades` table so
-- user data and pipeline data are never mixed.
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS journal_entries (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          VARCHAR(10)  NOT NULL,
    direction       VARCHAR(4)   NOT NULL CHECK (direction IN ('CALL', 'PUT')),
    entry_ts        TIMESTAMPTZ  NOT NULL,
    exit_ts         TIMESTAMPTZ  NOT NULL,
    entry_price     DOUBLE PRECISION NOT NULL,
    exit_price      DOUBLE PRECISION NOT NULL,
    return_pct      DOUBLE PRECISION,   -- computed on insert by application layer
    notes           TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_journal_entries_ticker_ts
    ON journal_entries (ticker, entry_ts DESC);

-- Reuse the existing set_updated_at() trigger function defined below
CREATE OR REPLACE TRIGGER set_journal_updated_at
    BEFORE UPDATE ON journal_entries
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ─────────────────────────────────────────────────────────
-- ANALYSIS OUTPUTS
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS premarket_analysis (
    id                BIGSERIAL PRIMARY KEY,
    analysis_date     DATE         NOT NULL,
    ticker            VARCHAR(10)  NOT NULL,
    price             DOUBLE PRECISION,
    rsi               DOUBLE PRECISION,
    rsi_direction     VARCHAR(4),
    consecutive_up    INTEGER,
    consecutive_down  INTEGER,
    signal_status     VARCHAR(50),
    strat_candle      VARCHAR(10),
    strat_combo       VARCHAR(30),
    strat_setup       BOOLEAN,
    ftfc_score        DOUBLE PRECISION,
    ftfc_direction    VARCHAR(10),
    ftfc_labels       JSONB,
    prev_day_high     DOUBLE PRECISION,
    prev_day_low      DOUBLE PRECISION,

    -- Enriched fields (added 2026-04-12)
    change_pct        DOUBLE PRECISION,
    rvol              DOUBLE PRECISION,
    sma200            DOUBLE PRECISION,
    bb_upper          DOUBLE PRECISION,
    bb_lower          DOUBLE PRECISION,
    ema9              DOUBLE PRECISION,
    ema20             DOUBLE PRECISION,
    atr14             DOUBLE PRECISION,
    volatility_20d    DOUBLE PRECISION,
    macd_cross        VARCHAR(10),
    vol_regime        VARCHAR(10),
    above_sma200      BOOLEAN,
    stoch_rsi_k       DOUBLE PRECISION,
    stoch_rsi_d       DOUBLE PRECISION,

    -- Strat-v2 additions (PR #101 brief now writes these per-ticker).
    -- The ALTER TABLE block below also adds them for existing instances,
    -- so the canonical schema and live deployments converge.
    recommended_orb_window  VARCHAR(8),
    recommended_orb_reason  TEXT,
    playbook                TEXT,

    analysis_ts       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_premarket_analysis UNIQUE (analysis_date, ticker)
);

CREATE TABLE IF NOT EXISTS economic_events (
    id              BIGSERIAL PRIMARY KEY,
    event_date      DATE         NOT NULL,
    event_time      TIME,
    event_name      VARCHAR(200) NOT NULL,
    country         VARCHAR(10),
    importance      VARCHAR(10),    -- 'high' | 'medium' | 'low'
    actual          VARCHAR(50),
    forecast        VARCHAR(50),
    previous        VARCHAR(50),
    inserted_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_economic_event UNIQUE (event_date, event_name)
);

CREATE INDEX IF NOT EXISTS idx_economic_events_date
    ON economic_events (event_date DESC);


-- set_updated_at() is defined earlier in this file (just before
-- trg_earnings_calendar_updated) so it exists ahead of its first use.
DROP TRIGGER IF EXISTS trg_market_data_daily_updated ON market_data_daily;
CREATE TRIGGER trg_market_data_daily_updated
    BEFORE UPDATE ON market_data_daily
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ─────────────────────────────────────────────────────────
-- AI INSIGHTS — multi-agent analyst pipeline
-- Tables: insight_reports, insight_runs, model_routing
-- Plus pgvector extension and journal_entries.embedding column
-- for reflection memory.
-- ─────────────────────────────────────────────────────────

-- pgvector extension. On Cloud SQL PG15 this requires the
-- `cloudsql.enable_pgvector` flag. Verify with:
--   psql -c "SHOW cloudsql.enable_pgvector"
-- before first apply.
CREATE EXTENSION IF NOT EXISTS vector;

-- Reflection-memory embedding on journal_entries.
-- Uses Vertex text-embedding-005 (768-dim). Backfilled via
-- scripts/backfill_journal_embeddings.py.
ALTER TABLE journal_entries
    ADD COLUMN IF NOT EXISTS embedding vector(768);

CREATE INDEX IF NOT EXISTS idx_journal_entries_embedding
    ON journal_entries USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);


-- Per-role provider/model routing for the agent pipeline.
-- Drives the /admin model-routing dashboard. Defaults to Vertex
-- Gemini for every role on fresh install (no new secrets required).
--
-- DORMANCY NOTE (audit 2026-05-08 G.P2.4): all 7 roles seed at the
-- same provider/model. The infrastructure (table + UI + per-role
-- /admin/routes API) supports per-role swap (e.g. analyst on cheap
-- Gemini Flash, judge on Claude Opus for harder reasoning) but no
-- production diversification has been justified yet — there's no
-- evidence the marginal cost-vs-quality trade-off is worth the
-- per-role engineering. The dashboard intentionally stays present
-- so an operator can A/B a single role (e.g. judge on Gemini 2.5
-- Pro for one week) without code changes; results would inform a
-- follow-up calibration if any role's per-call cost or output
-- quality justifies it. Until that data exists, treat this as a
-- single-model deployment by design.
CREATE TABLE IF NOT EXISTS model_routing (
    role          VARCHAR(32)  PRIMARY KEY,
    provider      VARCHAR(32)  NOT NULL,   -- 'vertex' | 'anthropic' | 'openai'
    model         VARCHAR(64)  NOT NULL,
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_by    VARCHAR(64)
);

-- Seed routes consistent with the Vertex adapter's default location
-- (`global`, see lib/agents/vertex_adapter.py). gemini-2.0-flash lives
-- ONLY on regional us-east1 and would 404 against the default global
-- endpoint, so a fresh deploy must seed a model that lives on global
-- (gemini-2.5-flash, gemini-3.1-flash-lite, etc). Updated 2026-05-11.
INSERT INTO model_routing (role, provider, model) VALUES
    ('analyst',           'vertex', 'gemini-3.1-flash-lite'),
    ('bull',              'vertex', 'gemini-3.1-flash-lite'),
    ('bear',              'vertex', 'gemini-3.1-flash-lite'),
    ('judge',             'vertex', 'gemini-3.1-flash-lite'),
    ('trader',            'vertex', 'gemini-3.1-flash-lite'),
    ('risk',              'vertex', 'gemini-3.1-flash-lite'),
    ('portfolio_manager', 'vertex', 'gemini-3.1-flash-lite')
ON CONFLICT (role) DO NOTHING;

DROP TRIGGER IF EXISTS trg_model_routing_updated ON model_routing;
CREATE TRIGGER trg_model_routing_updated
    BEFORE UPDATE ON model_routing
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- Cached InsightReport rows. One row per (ticker, as_of). `as_of` is
-- a full timestamp so the daily scheduled run and intra-day on-demand
-- runs coexist; "latest" reads sort DESC.
CREATE TABLE IF NOT EXISTS insight_reports (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          VARCHAR(10)  NOT NULL,
    as_of           TIMESTAMPTZ  NOT NULL,
    report          JSONB        NOT NULL,
    model_versions  JSONB        NOT NULL,
    cost_usd        NUMERIC(10,4),
    -- Per-role USD cost breakdown (e.g. {"analyst:market": 0.0021,
    -- "judge": 0.0008, ...}). Sum of values equals cost_usd within
    -- rounding. Lets dashboards answer "which role is most expensive?"
    -- without re-running the pipeline. Audit 2026-05-08 G.P3.2.
    per_role_cost   JSONB,
    latency_ms      INTEGER,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_insight_reports_ticker_asof UNIQUE (ticker, as_of)
);

-- Migration for existing instances. apply_schema.py is idempotent so
-- this no-ops on fresh installs after the table CREATE above.
ALTER TABLE insight_reports
    ADD COLUMN IF NOT EXISTS per_role_cost JSONB;

CREATE INDEX IF NOT EXISTS idx_insight_reports_ticker_asof
    ON insight_reports (ticker, as_of DESC);

-- GIN index so the history view can filter by direction/conviction
-- inside the JSONB report without full scans.
CREATE INDEX IF NOT EXISTS idx_insight_reports_report_gin
    ON insight_reports USING GIN (report jsonb_path_ops);


-- Durable run-state table for async pipeline execution.
-- The refresh endpoint inserts a `queued` row and enqueues a Cloud
-- Tasks message; the Cloud Run job flips status as it runs.
-- FastAPI BackgroundTasks is only used for local-dev mode.
CREATE TABLE IF NOT EXISTS insight_runs (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker          VARCHAR(10)  NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','done','failed')),
    trigger         VARCHAR(16)  NOT NULL DEFAULT 'on_demand'
                    CHECK (trigger IN ('on_demand','scheduled','local_dev','manual_batch')),
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error           TEXT,
    report_id       UUID REFERENCES insight_reports(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insight_runs_ticker_created
    ON insight_runs (ticker, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_insight_runs_status
    ON insight_runs (status, created_at DESC);

-- Migration: extend insight_runs.trigger CHECK to allow 'manual_batch'
-- (introduced by the batch-guard PR #106 to distinguish ad-hoc gcloud
-- run executions from the daily 8:45 cron). Idempotent — DROP + ADD
-- so re-running schema.sql converges existing instances.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'insight_runs_trigger_check'
    ) THEN
        ALTER TABLE insight_runs
            DROP CONSTRAINT insight_runs_trigger_check;
    END IF;
    ALTER TABLE insight_runs
        ADD CONSTRAINT insight_runs_trigger_check
        CHECK (trigger IN ('on_demand','scheduled','local_dev','manual_batch'));
END $$;


-- ─────────────────────────────────────────────────────────
-- NEWS SENTIMENT (AlphaVantage NEWS_SENTIMENT endpoint)
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS news_sentiment (
    id                       BIGSERIAL    PRIMARY KEY,
    ticker                   VARCHAR(10)  NOT NULL,
    published_ts             TIMESTAMPTZ  NOT NULL,
    title                    TEXT,
    url                      TEXT,
    summary                  TEXT,
    sentiment_score          DOUBLE PRECISION,   -- per-ticker (ticker_sentiment_score)
    relevance_score          DOUBLE PRECISION,   -- per-ticker
    overall_sentiment_score  DOUBLE PRECISION,   -- article-level
    overall_sentiment_label  VARCHAR(20),        -- Bullish/Bearish/Neutral/etc.
    topics                   TEXT[],             -- AV catalyst topics
    source                   VARCHAR(100),
    inserted_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_news UNIQUE (ticker, published_ts, url)
);

CREATE INDEX IF NOT EXISTS idx_news_sentiment_ticker_ts
    ON news_sentiment (ticker, published_ts DESC);

-- Live migration for existing deployments: add the topics + overall
-- sentiment columns introduced alongside the multi-ticker capture
-- rebuild of fetch_news_sentiment.py. Idempotent. Must run BEFORE the
-- GIN index below, because pre-existing deployments lack `topics`.
ALTER TABLE news_sentiment
    ADD COLUMN IF NOT EXISTS overall_sentiment_score DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS overall_sentiment_label VARCHAR(20),
    ADD COLUMN IF NOT EXISTS topics TEXT[];

-- GIN index for fast `topics @> ARRAY['mergers_and_acquisitions']` lookups.
CREATE INDEX IF NOT EXISTS idx_news_sentiment_topics
    ON news_sentiment USING GIN (topics);


-- ============================================================================
-- STRAT_LEVELS — long table of horizontal price markers per ticker per as_of.
-- Populated by lib.strat_levels.persist_level_map(). Used by the premarket
-- brief and signal_monitor for trigger / stop / target rendering.
-- ============================================================================
CREATE TABLE IF NOT EXISTS strat_levels (
    ticker         VARCHAR(10)               NOT NULL,
    as_of          TIMESTAMPTZ               NOT NULL,
    level_name     VARCHAR(50)               NOT NULL,
    price          NUMERIC(12,4)             NOT NULL,
    timeframe      VARCHAR(8),
    level_type     VARCHAR(20),
    -- VARCHAR(16) accommodates the longest Strat classification value
    -- 'Failed_2U' / 'Failed_2D' (9 chars) plus headroom. Original
    -- VARCHAR(8) caused IWM persists to fail with 22001 (string truncation)
    -- while SPY/QQQ persisted because they didn't trigger Failed_2 paths.
    strat_class    VARCHAR(16),
    is_current     BOOLEAN     DEFAULT FALSE,
    period_label   VARCHAR(40),
    -- 2026-05-10 source-data freshness tag. The latest
    -- `market_data_daily.date` used to compute this level. Lets readers
    -- (signal_monitor, brief, downstream analytics) verify the levels
    -- aren't built off stale fetcher data BEFORE acting on them.
    -- Pre-fix the 5/6 brief silently wrote levels computed from
    -- 4/27-latched data into rows stamped as_of=5/6 — every
    -- consumer trusted them. The persist_level_map writer also
    -- now refuses to write when (today - source_data_as_of) >
    -- max_age_days (default 2), so staleness fails fast at write
    -- time instead of polluting downstream consumers.
    source_data_as_of TIMESTAMPTZ,
    inserted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, as_of, level_name)
);

-- 2026-05-10 — additive migration for the source_data_as_of column on
-- existing deploys (the CREATE TABLE clause above is a no-op when the
-- table exists). Without this ALTER the schema-apply script would
-- skip the column and the new persist_level_map writer would error
-- with "column does not exist".
ALTER TABLE strat_levels
    ADD COLUMN IF NOT EXISTS source_data_as_of TIMESTAMPTZ;

-- Migration: widen strat_class for existing instances. Idempotent.
DO $$
BEGIN
    IF (SELECT character_maximum_length
          FROM information_schema.columns
         WHERE table_name='strat_levels' AND column_name='strat_class') < 16 THEN
        ALTER TABLE strat_levels ALTER COLUMN strat_class TYPE VARCHAR(16);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_strat_levels_ticker_as_of_price
    ON strat_levels (ticker, as_of, price);


-- ============================================================================
-- Forward-looking columns for Strat Quarter levels. The columns are added
-- idempotently so that when a future fetcher writes calculate_historical_levels()
-- output the table is ready. Existing rows stay NULL until backfilled.
-- ============================================================================
ALTER TABLE market_data_daily
    ADD COLUMN IF NOT EXISTS prev_quarter_high     DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS prev_quarter_low      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS prev_quarter_open     DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS prev_quarter_close    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS prev_quarter_hl_mid   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS prev_quarter_oc_mid   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS at_prev_quarter_high  SMALLINT,
    ADD COLUMN IF NOT EXISTS at_prev_quarter_low   SMALLINT,
    ADD COLUMN IF NOT EXISTS broke_prev_quarter_high SMALLINT,
    ADD COLUMN IF NOT EXISTS broke_prev_quarter_low  SMALLINT;


-- ============================================================================
-- Pre-market context (4 AM - 9:30 AM ET, computed from extended-hours bars).
-- The 4/27 brief failed because every entry zone was based on Friday's H/L
-- but Monday gapped up significantly — the brief had no signal that pre-
-- market price had already invalidated those levels. These columns let the
-- LLM analyst (and the strat_levels engine) see today's pre-market range
-- alongside the prior-day session, so triggers can be calibrated to current
-- reality instead of yesterday's close.
-- ============================================================================
ALTER TABLE market_data_daily
    ADD COLUMN IF NOT EXISTS pre_high       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_low        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_vwap       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_volume     BIGINT,
    ADD COLUMN IF NOT EXISTS gap_pct        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS pre_range_atr  DOUBLE PRECISION;


-- ============================================================================
-- Catalyst-aware ORB recommendation + Strat playbook persisted by
-- gcp/premarket_brief.py. The playbook column was missed in the original
-- PR #101 schema migration: the brief computed d['playbook'] but
-- upsert_dataframe silently filtered it out (it filters columns not in
-- the table schema), so the rich per-ticker playbook string was lost
-- on every brief run. Adding the column makes the data flow end-to-end.
-- ============================================================================
ALTER TABLE premarket_analysis
    ADD COLUMN IF NOT EXISTS recommended_orb_window VARCHAR(8),
    ADD COLUMN IF NOT EXISTS recommended_orb_reason TEXT,
    ADD COLUMN IF NOT EXISTS playbook TEXT;


-- ============================================================================
-- Track B audit (2026-05-08): data freshness + LLM commentary persistence
-- on `premarket_analysis`. W5 schema for the implementation plan in
-- docs/audit/2026-05-08/track-B-implementation-plan.md. The companion
-- columns on `premarket_analysis_history` are added inside that table's
-- CREATE TABLE definition further down (so fresh-DB applies see them at
-- CREATE time) AND in a deferred ALTER block immediately after the
-- CREATE (so existing-DB applies pick them up).
--
-- Column meanings:
--
--   data_as_of (timestamptz)
--     Per-ticker timestamp of the LAST OHLCV bar the brief used to
--     compute that row's bias / levels / RSI. Read by the W6 writer
--     from `df.iloc[-1].name` after the null-close filter at
--     gcp/premarket_brief.py:724. Lets a single SELECT answer
--     "which morning's brief was based on stale data?" — pre-W6 this
--     required a 4-table join.
--
--   data_freshness_status (varchar(20))
--     Stamp written by the W6 staleness detector. Values:
--       'fresh'             — last bar was 1 trading day before
--                             analysis_date (or Friday→Monday).
--       'STALE_DAILY_DATA'  — gap > 1 trading day with no Monday
--                             exemption. The W6 writer sets per-ticker
--                             status='STALE_DAILY_DATA' on data['status']
--                             so persist_to_cloud_sql skips the canonical
--                             premarket_analysis row and only writes the
--                             history row (audit trail). Track B audit
--                             G.P0.4.
--       NULL                — pre-W6 rows from before the writer landed.
--
--   llm_overview / llm_orb_explanation (text, brief-level)
--   llm_analysis / llm_playbook (text, per-ticker)
--     Gemini-generated commentary that the brief renders into Discord
--     today and discards. W7 wires the writer to persist these for
--     audit-trail replay (the four strings are non-deterministic across
--     LLM calls, but the original morning's text is locked once
--     persisted). Track G G.P2.11 / Track B audit B.11; user-confirmed
--     decision was "persist for audit trail" rather than skip.
--
-- All columns are NULL-able; pre-migration rows stay NULL until the
-- W6 / W7 writers land. Idempotent; re-runs are no-ops.
-- ============================================================================
ALTER TABLE premarket_analysis
    ADD COLUMN IF NOT EXISTS data_as_of            TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_freshness_status VARCHAR(20),
    ADD COLUMN IF NOT EXISTS llm_overview          TEXT,
    ADD COLUMN IF NOT EXISTS llm_orb_explanation   TEXT,
    ADD COLUMN IF NOT EXISTS llm_analysis          TEXT,
    ADD COLUMN IF NOT EXISTS llm_playbook          TEXT;


-- ─────────────────────────────────────────────────────────
-- Brief-playbook outcome tracking (added 2026-05-11)
-- ─────────────────────────────────────────────────────────
--
-- Two halves: STRUCTURED inputs (the trigger / stop / target prices the
-- brief recommended) and RESOLVED outcomes (what actually happened during
-- RTH). The brief writer fills the `*_price` / `*_name` columns at
-- generation time; the EOD resolver job fills the `*_hit_ts` / `*_pnl_*` /
-- `*_excursion_*` columns after market close by walking
-- market_data_intraday for that (date, ticker).
--
-- Pre-this-block the playbook lived only as LLM prose in the `playbook`
-- column — fine for human reading, useless for analytics. Now we can
-- answer "did 5/6 QQQ's recommended CALL trigger actually print, when did
-- it hit T1, was T3 reached, what was the EOD pnl per share / per $10k
-- notional?" via SQL.
--
-- Resolver job: gcp/premarket_playbook_resolver.py
-- Cron: 30 16 * * 1-5 America/New_York (16:30 ET, after RTH close)
-- Idempotent: re-running on the same date overwrites with the same values
ALTER TABLE premarket_analysis
    -- ── STRUCTURED inputs ────────────────────────────────────────────
    ADD COLUMN IF NOT EXISTS calls_trigger_price   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calls_trigger_name    VARCHAR(20),
    ADD COLUMN IF NOT EXISTS calls_stop_price      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calls_stop_name       VARCHAR(20),
    ADD COLUMN IF NOT EXISTS calls_t1_price        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calls_t2_price        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calls_t3_price        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_trigger_price    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_trigger_name     VARCHAR(20),
    ADD COLUMN IF NOT EXISTS puts_stop_price       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_stop_name        VARCHAR(20),
    ADD COLUMN IF NOT EXISTS puts_t1_price         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_t2_price         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_t3_price         DOUBLE PRECISION,

    -- ── RESOLVED outcomes — CALLS leg ────────────────────────────────
    ADD COLUMN IF NOT EXISTS calls_trigger_hit_ts  TIMESTAMPTZ,   -- first bar where high >= trigger
    ADD COLUMN IF NOT EXISTS calls_t1_hit_ts       TIMESTAMPTZ,   -- after trigger, first bar where high >= t1
    ADD COLUMN IF NOT EXISTS calls_t2_hit_ts       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS calls_t3_hit_ts       TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS calls_stop_hit_ts     TIMESTAMPTZ,   -- after trigger, first bar where low <= stop
    ADD COLUMN IF NOT EXISTS calls_reversal_after_trigger BOOLEAN, -- True iff stop_hit_ts > trigger_hit_ts
    ADD COLUMN IF NOT EXISTS calls_time_to_t1_min  INTEGER,       -- minutes from trigger to T1
    ADD COLUMN IF NOT EXISTS calls_mae_pct         DOUBLE PRECISION, -- (trigger - min_low_after_trigger)/trigger * 100
    ADD COLUMN IF NOT EXISTS calls_mfe_pct         DOUBLE PRECISION, -- (max_high_after_trigger - trigger)/trigger * 100
    ADD COLUMN IF NOT EXISTS calls_eod_pnl_pct     DOUBLE PRECISION, -- final realized pct (at first stop/target/EOD close)
    ADD COLUMN IF NOT EXISTS calls_eod_pnl_dollar  DOUBLE PRECISION, -- pct/100 * notional ($10,000 default)

    -- ── RESOLVED outcomes — PUTS leg (mirror of CALLS) ───────────────
    ADD COLUMN IF NOT EXISTS puts_trigger_hit_ts   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS puts_t1_hit_ts        TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS puts_t2_hit_ts        TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS puts_t3_hit_ts        TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS puts_stop_hit_ts      TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS puts_reversal_after_trigger BOOLEAN,
    ADD COLUMN IF NOT EXISTS puts_time_to_t1_min   INTEGER,
    ADD COLUMN IF NOT EXISTS puts_mae_pct          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_mfe_pct          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_eod_pnl_pct      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_eod_pnl_dollar   DOUBLE PRECISION,

    -- ── Resolver metadata ────────────────────────────────────────────
    ADD COLUMN IF NOT EXISTS outcome_resolved_at   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS outcome_resolver_version VARCHAR(20);

CREATE INDEX IF NOT EXISTS idx_premarket_analysis_outcome_resolved
    ON premarket_analysis(outcome_resolved_at) WHERE outcome_resolved_at IS NOT NULL;


-- ============================================================================
-- Live migration: rename premarket_analysis.strat_daily -> strat_candle.
-- The methodology doc renames every "candle classification" surface to
-- a single column name. Idempotent.
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'premarket_analysis' AND column_name = 'strat_daily'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'premarket_analysis' AND column_name = 'strat_candle'
    ) THEN
        ALTER TABLE premarket_analysis RENAME COLUMN strat_daily TO strat_candle;
    END IF;
END $$;


-- ============================================================================
-- HISTORY TABLES — append-only audit trail for brief + insight runs
-- ============================================================================
-- The current `premarket_analysis` and `insight_reports` tables UPSERT on
-- `(analysis_date, ticker)` and `(ticker, as_of)` respectively, which means
-- any same-day re-run destructively overwrites the canonical morning row.
-- These history tables capture every actual run (scheduled, manual, replay,
-- retry) so we can answer "what did the 8:30 brief actually send for AVGO
-- on 4/29?" even after a lunchtime re-run overwrote the current view.
--
-- Schema rules:
--   * Append-only INSERT (no UPSERT, no UPDATE)
--   * Mirror the column set of the parent table verbatim, plus audit metadata
--   * Idempotency for backfill via the unique-constraint over
--     `(parent_pk_columns, written_at)`
--
-- See docs/plans/MORNING_RUN_PROTECTION_PLAN.md for the rationale and the
-- two-phase rollout (this is Phase 1 — schema only, no code change).
-- ============================================================================

CREATE TABLE IF NOT EXISTS premarket_analysis_history (
    id                BIGSERIAL    PRIMARY KEY,
    -- Mirror of premarket_analysis (keep synced when that table evolves)
    analysis_date     DATE         NOT NULL,
    ticker            VARCHAR(10)  NOT NULL,
    price             DOUBLE PRECISION,
    rsi               DOUBLE PRECISION,
    rsi_direction     VARCHAR(4),
    consecutive_up    INTEGER,
    consecutive_down  INTEGER,
    signal_status     VARCHAR(50),
    strat_candle      VARCHAR(10),
    strat_combo       VARCHAR(30),
    strat_setup       BOOLEAN,
    ftfc_score        DOUBLE PRECISION,
    ftfc_direction    VARCHAR(10),
    ftfc_labels       JSONB,
    prev_day_high     DOUBLE PRECISION,
    prev_day_low      DOUBLE PRECISION,
    change_pct        DOUBLE PRECISION,
    rvol              DOUBLE PRECISION,
    sma200            DOUBLE PRECISION,
    bb_upper          DOUBLE PRECISION,
    bb_lower          DOUBLE PRECISION,
    ema9              DOUBLE PRECISION,
    ema20             DOUBLE PRECISION,
    atr14             DOUBLE PRECISION,
    volatility_20d    DOUBLE PRECISION,
    macd_cross        VARCHAR(10),
    vol_regime        VARCHAR(10),
    above_sma200      BOOLEAN,
    stoch_rsi_k       DOUBLE PRECISION,
    stoch_rsi_d       DOUBLE PRECISION,
    recommended_orb_window  VARCHAR(8),
    recommended_orb_reason  TEXT,
    playbook                TEXT,

    -- Track B audit (2026-05-08): data freshness + LLM commentary
    -- persistence. See the comment block above the
    -- `ALTER TABLE premarket_analysis ADD COLUMN data_as_of ...`
    -- migration earlier in this file for the column-by-column
    -- meaning. Adding them inline here ensures fresh-DB applies pick
    -- them up at CREATE time; the deferred ALTER block immediately
    -- after this CREATE catches existing DBs where the table already
    -- exists.
    data_as_of              TIMESTAMPTZ,
    data_freshness_status   VARCHAR(20),
    llm_overview            TEXT,
    llm_orb_explanation     TEXT,
    llm_analysis            TEXT,
    llm_playbook            TEXT,

    -- Audit metadata
    written_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    run_kind          VARCHAR(20)  NOT NULL,
        -- 'scheduled' | 'manual_update' | 'manual_replay' | 'replay_refresh'
        -- 'auto_refresh' | 'backfill'
    triggered_by      VARCHAR(64),
        -- 'cloud-scheduler:premarket-brief-daily'
        -- 'discord:replay:<user_id>' | 'cli:<user>' | 'backfill-script'
    notes             TEXT,

    -- Backfill idempotency: same (date, ticker, written_at) tuple cannot
    -- duplicate. Live runs use NOW() so dupes within microseconds are
    -- effectively impossible; backfill explicitly preserves analysis_ts
    -- so re-running the backfill is a no-op.
    CONSTRAINT uq_pmah_date_ticker_written
        UNIQUE (analysis_date, ticker, written_at)
);

CREATE INDEX IF NOT EXISTS idx_pmah_date_ticker_written
    ON premarket_analysis_history (analysis_date, ticker, written_at DESC);
CREATE INDEX IF NOT EXISTS idx_pmah_run_kind
    ON premarket_analysis_history (run_kind, written_at DESC);


-- Deferred companion of the `ALTER TABLE premarket_analysis` migration
-- earlier in this file. This block has to live AFTER the CREATE TABLE
-- above because Postgres rejects ALTER on a not-yet-existing table —
-- on a fresh DB, the CREATE creates the table with the columns inline
-- and this ALTER no-ops; on an existing DB where the CREATE TABLE IF
-- NOT EXISTS sees the table and skips creation, the ALTER picks up
-- the new columns. Idempotent in both cases. Codex review on PR #335
-- caught the original placement (above the CREATE) and the move-here
-- fix is the resolution.
ALTER TABLE premarket_analysis_history
    ADD COLUMN IF NOT EXISTS data_as_of            TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS data_freshness_status VARCHAR(20),
    ADD COLUMN IF NOT EXISTS llm_overview          TEXT,
    ADD COLUMN IF NOT EXISTS llm_orb_explanation   TEXT,
    ADD COLUMN IF NOT EXISTS llm_analysis          TEXT,
    ADD COLUMN IF NOT EXISTS llm_playbook          TEXT,
    -- Mirror the brief-playbook outcome tracking columns added to
    -- premarket_analysis (2026-05-11). Without them, bulk_insert into
    -- the history table silently drops the structured fields populated
    -- by persist_to_cloud_sql, leaving the audit trail unable to
    -- reconstruct the exact triggers/stops/targets that were
    -- recommended on a given morning. Codex review on PR #444 caught
    -- this on the initial PR; mirror is additive + idempotent.
    ADD COLUMN IF NOT EXISTS calls_trigger_price   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calls_trigger_name    VARCHAR(20),
    ADD COLUMN IF NOT EXISTS calls_stop_price      DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calls_stop_name       VARCHAR(20),
    ADD COLUMN IF NOT EXISTS calls_t1_price        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calls_t2_price        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS calls_t3_price        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_trigger_price    DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_trigger_name     VARCHAR(20),
    ADD COLUMN IF NOT EXISTS puts_stop_price       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_stop_name        VARCHAR(20),
    ADD COLUMN IF NOT EXISTS puts_t1_price         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_t2_price         DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS puts_t3_price         DOUBLE PRECISION;


CREATE TABLE IF NOT EXISTS insight_reports_history (
    id                BIGSERIAL    PRIMARY KEY,
    -- Optional FK to existing insight_runs row. SET NULL on delete so
    -- pruning insight_runs doesn't cascade to history.
    insight_run_id    UUID         REFERENCES insight_runs(id) ON DELETE SET NULL,
    -- Mirror of insight_reports
    ticker            VARCHAR(10)  NOT NULL,
    as_of             TIMESTAMPTZ  NOT NULL,
    report            JSONB        NOT NULL,
    model_versions    JSONB,
    cost_usd          NUMERIC(10,4),
    -- Per-role USD cost breakdown (mirror of insight_reports.per_role_cost).
    per_role_cost     JSONB,
    latency_ms        INTEGER,

    -- Audit metadata
    written_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    run_kind          VARCHAR(20)  NOT NULL,
    triggered_by      VARCHAR(64),
    notes             TEXT,

    CONSTRAINT uq_irh_ticker_asof_written
        UNIQUE (ticker, as_of, written_at)
);

CREATE INDEX IF NOT EXISTS idx_irh_ticker_as_of_written
    ON insight_reports_history (ticker, as_of, written_at DESC);
CREATE INDEX IF NOT EXISTS idx_irh_run_kind
    ON insight_reports_history (run_kind, written_at DESC);

-- Migration for existing instances. Idempotent.
ALTER TABLE insight_reports_history
    ADD COLUMN IF NOT EXISTS per_role_cost JSONB;


-- Migration: extend insight_runs.trigger CHECK to allow 'cache_hit' so
-- /replay can audit-log "user requested cached data" without writing a
-- new insight_reports row. Idempotent — DROP + ADD so re-running
-- schema.sql converges existing instances.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'insight_runs_trigger_check'
    ) THEN
        ALTER TABLE insight_runs
            DROP CONSTRAINT insight_runs_trigger_check;
    END IF;
    ALTER TABLE insight_runs
        ADD CONSTRAINT insight_runs_trigger_check
        CHECK (trigger IN (
            'on_demand', 'scheduled', 'local_dev', 'manual_batch',
            'cache_hit', 'replay_refresh'
        ));
END $$;


-- ============================================================================
-- HISTORICAL_SIGNALS — idempotent home for trading_analysis.py output
-- ============================================================================
-- Each row is one fired setup as defined by the 5-condition voter in
-- trading_analysis.py:generate_technical_signals. Replaces the GCS
-- parquet (data/signals/historical_{ticker}_*_signals.parquet).
--
-- Idempotency: PRIMARY KEY (ticker, entry_time) + INSERT ... ON CONFLICT
-- DO NOTHING. Re-running trading_analysis.py over a date range that's
-- already been processed is a no-op.
-- ============================================================================

CREATE TABLE IF NOT EXISTS historical_signals (
    ticker            VARCHAR(10)      NOT NULL,
    entry_time        TIMESTAMPTZ      NOT NULL,
    trade_type        VARCHAR(4)       NOT NULL,    -- 'call' | 'put'
    entry_price       DOUBLE PRECISION,
    signal_strength   SMALLINT,                     -- 3..5 (count of conditions met)
    conditions_met    VARCHAR(8),                   -- e.g. '4/5'
    duration_minutes  SMALLINT,                     -- bars from entry to MFE peak
    return_pct        DOUBLE PRECISION,             -- 20-min Maximum Favorable Excursion
    best_return       DOUBLE PRECISION,
    best_window_min   SMALLINT,
    return_5min       DOUBLE PRECISION,
    return_10min      DOUBLE PRECISION,
    return_15min      DOUBLE PRECISION,
    return_20min      DOUBLE PRECISION,
    return_30min      DOUBLE PRECISION,
    return_45min      DOUBLE PRECISION,
    return_60min      DOUBLE PRECISION,

    -- Indicators at entry (the ones the API + Charts page need flat)
    entry_rsi         DOUBLE PRECISION,
    entry_ema9        DOUBLE PRECISION,
    entry_ema20       DOUBLE PRECISION,
    entry_vwap        DOUBLE PRECISION,
    entry_volume      BIGINT,

    -- ORB / order-block / prior-period levels — kept in JSONB so the
    -- ~30 less-queried columns from the parquet don't bloat the table
    -- and additions don't need migrations.
    extra             JSONB,

    inserted_at       TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ticker, entry_time)
);

CREATE INDEX IF NOT EXISTS idx_historical_signals_ticker_time
    ON historical_signals (ticker, entry_time DESC);

CREATE INDEX IF NOT EXISTS idx_historical_signals_strength
    ON historical_signals (ticker, signal_strength DESC);

CREATE INDEX IF NOT EXISTS idx_historical_signals_direction
    ON historical_signals (ticker, trade_type, entry_time DESC);


-- ─────────────────────────────────────────────────────────
-- TICKER INFO (Alpha Vantage OVERVIEW cache, per-user ready)
-- ─────────────────────────────────────────────────────────
-- One row per ticker. Populated by lib.ticker_info on first
-- watchlist add or periodic refresh. Provides company name,
-- sector, industry for the news-feed alias-matching pipeline.

CREATE TABLE IF NOT EXISTS ticker_info (
    ticker          VARCHAR(10)  PRIMARY KEY,
    name            VARCHAR(200),
    exchange        VARCHAR(20),
    sector          VARCHAR(100),
    industry        VARCHAR(200),
    market_cap      BIGINT,
    description     TEXT,
    asset_type      VARCHAR(20),        -- 'Common Stock', 'ETF', etc.
    raw_json        JSONB,              -- full AV OVERVIEW response (trimmed)
    inserted_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Peer/relationship data from FinViz + industry screener.
-- Example: {"peers": ["AMD","NVDA","QCOM"], "industry_peers": ["TSM","TXN"]}
ALTER TABLE ticker_info
    ADD COLUMN IF NOT EXISTS relationships JSONB;

CREATE INDEX IF NOT EXISTS idx_ticker_info_sector
    ON ticker_info (sector);

DROP TRIGGER IF EXISTS trg_ticker_info_updated ON ticker_info;
CREATE TRIGGER trg_ticker_info_updated
    BEFORE UPDATE ON ticker_info
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ── news_sentiment: RSS + multi-source support ──────────────────────────────
-- data_source distinguishes AV API rows from RSS-fetched rows.
-- match_method records how the ticker was identified in the article.
ALTER TABLE news_sentiment
    ADD COLUMN IF NOT EXISTS data_source  VARCHAR(20) DEFAULT 'alphavantage',
    ADD COLUMN IF NOT EXISTS match_method VARCHAR(20) DEFAULT 'direct';
    -- data_source: 'alphavantage' | 'rss' | 'finviz'
    -- match_method: 'direct' (AV/SA category) | 'title_regex' | 'alias_match'
    --              | 'relationship' (inferred via peer graph) | 'llm'

CREATE INDEX IF NOT EXISTS idx_news_sentiment_data_source
    ON news_sentiment (data_source, published_ts DESC);

CREATE INDEX IF NOT EXISTS idx_news_sentiment_match_method
    ON news_sentiment (match_method);


-- ── watchlists: per-user ticker subscriptions, durably stored ───────────────
-- Replaces the alert_config.json file-based watchlist that was writing to
-- the trading-platform Cloud Run service's ephemeral filesystem (lost on
-- every restart, never reached the fetcher containers).
--
-- Schema is per-user from day one so a future auth layer can flip on
-- multi-user mode by populating user_id from a session/JWT. Until then
-- writers default to user_id='default'.
--
-- removed_at = NULL means "active". A soft-delete column instead of a
-- DELETE so the audit trail captures intent + history.
CREATE TABLE IF NOT EXISTS watchlists (
    user_id      VARCHAR(64)  NOT NULL DEFAULT 'default',
    ticker       VARCHAR(10)  NOT NULL,
    added_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    removed_at   TIMESTAMPTZ  NULL,
    source       VARCHAR(20)  NULL,        -- 'ui', 'cli', 'admin', 'seed'
    notes        TEXT         NULL,
    -- Per-surface filters: control whether a watchlist ticker drives
    -- the morning brief and/or the AI insight pipeline. Defaults FALSE
    -- so adding a ticker via /watchlist add (e.g. a peer for /similar
    -- comparison like NVDA, AMD, MRVL) doesn't auto-bloat the morning
    -- Discord brief or burn Vertex spend on AI insights. ETFs that
    -- SHOULD drive the brief get the flags set explicitly via the
    -- slash command (`/watchlist add SOXX brief:true insight:true`)
    -- or via UPDATE.
    in_brief     BOOLEAN      NOT NULL DEFAULT FALSE,
    in_insight   BOOLEAN      NOT NULL DEFAULT FALSE,
    PRIMARY KEY (user_id, ticker)
);

-- Active rows lookup — used on every fetcher start. Partial index keeps
-- the index small as removed rows accumulate over time.
CREATE INDEX IF NOT EXISTS idx_watchlists_active
    ON watchlists (user_id) WHERE removed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_watchlists_ticker
    ON watchlists (ticker) WHERE removed_at IS NULL;

-- Live migration: add in_brief / in_insight columns idempotently for
-- instances created before the per-surface filter shipped.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'watchlists' AND column_name = 'in_brief'
    ) THEN
        ALTER TABLE watchlists
            ADD COLUMN in_brief BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'watchlists' AND column_name = 'in_insight'
    ) THEN
        ALTER TABLE watchlists
            ADD COLUMN in_insight BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
END $$;

-- Migration: flip the column DEFAULT from TRUE → FALSE on instances
-- where the original ALTER landed with DEFAULT TRUE (PR #156). This
-- only changes behavior for FUTURE INSERTs that don't supply
-- in_brief / in_insight explicitly — existing rows are not touched.
ALTER TABLE watchlists ALTER COLUMN in_brief   SET DEFAULT FALSE;
ALTER TABLE watchlists ALTER COLUMN in_insight SET DEFAULT FALSE;

-- ── signals: live signal-monitor watchlist source-of-truth ───────────
-- The live signal monitor (gcp/signal_monitor.py) used to read its
-- ticker list from alert_config.json — a static config file. This
-- column promotes the live watchlist to the same DB-backed shape as
-- in_brief and in_insight: query rows where signals = TRUE AND
-- removed_at IS NULL, and that's the live monitor's universe.
--
-- Initial population (idempotent, only runs if no rows are TRUE):
-- IWM, QQQ, SPY get signals=TRUE — the historical alert_config.json
-- watchlist's three core tickers, matching in_brief/in_insight.
-- Re-runs of apply-schema-migrations don't clobber subsequent user
-- toggles because the gate "no rows currently TRUE" only matches on
-- a fresh migration.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'watchlists' AND column_name = 'signals'
    ) THEN
        ALTER TABLE watchlists
            ADD COLUMN signals BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM watchlists WHERE signals = TRUE) THEN
        UPDATE watchlists
           SET signals = TRUE
         WHERE ticker IN ('IWM', 'QQQ', 'SPY')
           AND removed_at IS NULL;
    END IF;
END $$;


-- ─────────────────────────────────────────────────────────
-- TICKER CALIBRATION (Phase 0.6)
-- Per-ticker, quarterly-refreshed thresholds for the multi-tf signal
-- evaluator. Replaces the universal-across-all-tickers THRESHOLDS dict
-- that hard-coded 0.5% as "clean at 60m" for SPY, QQQ, and IWM alike
-- (their typical ATR_60m differs ~2× across them). See
-- docs/plans/SIGNAL_QUALITY_TEST_PLAN.md §3 caveats and Phase 0.6.
--
-- Refresh cadence: quarterly (1st of Jan / Apr / Jul / Oct at 02:00 ET)
-- via the `calibrate-thresholds` Cloud Run Job. Manual override is
-- always available via `gcloud run jobs execute calibrate-thresholds`.
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ticker_calibration (
    ticker             VARCHAR(10)  NOT NULL,
    calibration_date   DATE         NOT NULL,
    lookback_days      INTEGER      NOT NULL DEFAULT 60,

    -- ATR median per timeframe, expressed as % of price (e.g. 0.045 = 0.045%)
    -- Used to scale per-tf clean/wrong/noise thresholds: clean = atr_60m_median × 1.0
    atr_5m_median      DOUBLE PRECISION,
    atr_15m_median     DOUBLE PRECISION,
    atr_30m_median     DOUBLE PRECISION,
    atr_60m_median     DOUBLE PRECISION,
    atr_90m_median     DOUBLE PRECISION,
    atr_120m_median    DOUBLE PRECISION,
    atr_240m_median    DOUBLE PRECISION,

    -- RVOL distribution (relative volume vs 20-day average) — used by the
    -- per-ticker RVOL filter band proposed in §3.4.
    rvol_p25           DOUBLE PRECISION,
    rvol_p50           DOUBLE PRECISION,
    rvol_p75           DOUBLE PRECISION,
    rvol_p95           DOUBLE PRECISION,

    -- RSI distribution (regime indicator) — sanity-check that the
    -- universal CALL_RSI_RANGE / PUT_RSI_RANGE constants in lib/strategies/
    -- config.py are still appropriate for THIS ticker.
    rsi_p10            DOUBLE PRECISION,
    rsi_p25            DOUBLE PRECISION,
    rsi_p50            DOUBLE PRECISION,
    rsi_p75            DOUBLE PRECISION,
    rsi_p90            DOUBLE PRECISION,

    -- Computed clean / wrong / noise thresholds per timeframe (in % of price).
    -- JSONB so future timeframes can be added without schema migration.
    -- Shape: {"5m": {"clean": 0.07, "wrong": -0.10, "noise": 0.05},
    --         "15m": {"clean": 0.10, ...}, ...}
    threshold_clean    JSONB,
    threshold_wrong    JSONB,
    threshold_noise    JSONB,

    -- Per-ticker RVOL filter band (computed from rvol_p25 / rvol_p75)
    rvol_min           DOUBLE PRECISION,
    rvol_max           DOUBLE PRECISION,

    -- Per-ticker ATR-expansion multiplier for the chop-vs-trend gate
    -- proposed in Phase 0.7.1. Replaces the hard-coded 1.3× factor.
    atr_expansion_x    DOUBLE PRECISION DEFAULT 1.3,

    -- Audit metadata
    n_bars_used        INTEGER,                    -- how many 1-min bars went into the calibration
    earliest_bar_date  DATE,
    latest_bar_date    DATE,
    inserted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ticker, calibration_date)
);

CREATE INDEX IF NOT EXISTS idx_ticker_calibration_recent
    ON ticker_calibration (ticker, calibration_date DESC);

-- 2026-05-10 (#250) drift guard. When a quarterly calibration produces
-- a value > 2σ from the rolling 4-row mean for any percentile column,
-- the row is written but flagged. Live resolver in
-- lib/strategies/calibration.py falls back to Tier-B (universal) when
-- drift_flagged=TRUE so a single anomalous calibration window doesn't
-- whipsaw production thresholds. Values > 3σ refuse the write entirely
-- (must --force to override). See scripts/calibrate_thresholds.py
-- _check_drift() for the implementation.
ALTER TABLE ticker_calibration
    ADD COLUMN IF NOT EXISTS drift_flagged BOOLEAN DEFAULT FALSE;


-- ─────────────────────────────────────────────────────────
-- EXIT_CONFIG_OVERRIDES: per-ticker target/stop/time overrides
-- (Track A G.P0.14 — 2026-05-08 audit recommendation)
--
-- The audit's MFE/MAE-based per-ticker calibration found that the
-- universal `lib/config.py:ExitConfig` defaults (target=0.003 / stop=
-- 0.0015) are 1.5–2× too wide for SPY/IWM/QQQ. With the recommended
-- per-ticker targets, QQQ's mean per-trade return flips from −0.0005%
-- to +0.0127% (counterfactual replay over 50 days of cached intraday).
--
-- Read pattern: latest snapshot per ticker, like ticker_calibration.
-- See lib/strategies/exit_config_overrides.py for the read-side helpers.
-- Write pattern: PR-E1 seeds initial values; PR-E7 (quarterly job)
-- writes refreshed values via INSERT ... ON CONFLICT DO UPDATE.
-- ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exit_config_overrides (
    ticker             VARCHAR(10)  NOT NULL,
    calibration_date   DATE         NOT NULL,

    -- Per-ticker exit thresholds. NULL means "use the lib/config.py
    -- ExitConfig default for this knob" — the resolver in
    -- exit_config_overrides.py treats NULL as Tier-A miss and falls
    -- back to Tier-B.
    call_target        DOUBLE PRECISION,   -- e.g. 0.00301 = +30 bps
    put_target         DOUBLE PRECISION,
    call_stop          DOUBLE PRECISION,
    put_stop           DOUBLE PRECISION,
    call_time_stop     INTEGER,            -- minutes
    put_time_stop      INTEGER,

    -- Walk-forward calibration sweep: per-ticker consecutive-bar
    -- pressure window. NULL = use the SignalConfig default.
    consecutive_periods INTEGER,

    -- PR-E3: per-ticker dropped strategy conditions (e.g.
    -- ['stoch_rsi_overbought', 'rsi_overbought_zone'] for IWM/QQQ MR PUT).
    -- NULL = use the strategy's full condition list.
    disabled_conditions JSONB,

    -- Audit 2026-05-08 G.P1.4 follow-up: per-ticker blue-sky synth offset
    -- in ATR units, used by lib/agents/trade_planner.select_trigger_and_regime
    -- when every historical level is cleared by pre-market. Calibrated
    -- from the per-ticker median/mean (RTH high − pre_high)/ATR
    -- distribution on gap-up days. NULL → falls back to the global
    -- default `_BLUE_SKY_ATR_OFFSET` in trade_planner.py.
    blue_sky_atr_offset DOUBLE PRECISION,

    notes              TEXT,
    inserted_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ticker, calibration_date)
);

-- Migration for existing instances. Idempotent.
ALTER TABLE exit_config_overrides
    ADD COLUMN IF NOT EXISTS blue_sky_atr_offset DOUBLE PRECISION;

-- Audit 2026-05-08 G.P1.19: per-ticker direction kill switch.
-- `disabled_directions` JSONB column carries a list like ["PUT"] or
-- ["CALL"] for tickers where one side should not fire at all (until
-- the condition set is rebuilt — temporary disable, not a permanent
-- ban). Read at lib/signals.py:evaluate_signal; alerts return None
-- for the disabled side regardless of score.
ALTER TABLE exit_config_overrides
    ADD COLUMN IF NOT EXISTS disabled_directions JSONB;

-- Walk-forward calibration sweep: per-ticker consecutive-bar window.
-- Written by scripts/run_param_sweep.py; read by
-- lib/strategies/exit_config_overrides.py:get_consecutive_periods().
ALTER TABLE exit_config_overrides
    ADD COLUMN IF NOT EXISTS consecutive_periods INTEGER;

CREATE INDEX IF NOT EXISTS idx_exit_config_overrides_recent
    ON exit_config_overrides (ticker, calibration_date DESC);

-- Initial seed from docs/audit/2026-05-08/recommended_per_ticker_config.json.
-- Idempotent: re-applying schema.sql leaves later quarterly snapshots
-- untouched (PRIMARY KEY conflict → DO NOTHING).
INSERT INTO exit_config_overrides (
    ticker, calibration_date,
    call_target, put_target, call_stop, put_stop,
    call_time_stop, put_time_stop, notes
) VALUES
    ('SPY', '2026-05-08', 0.00184, 0.00202, 0.00075, 0.00075, 25, 25,
     'Audit 2026-05-08 (90-day MFE/MAE p70/p25, n=555). MR-only universe; momentum did not fire.'),
    ('IWM', '2026-05-08', 0.00281, 0.00249, 0.00077, 0.00100, 20, 25,
     'Audit 2026-05-08 (90-day MFE/MAE p70/p25, n=493). MR-only universe; momentum did not fire.'),
    ('QQQ', '2026-05-08', 0.00301, 0.00238, 0.00075, 0.00075, 20, 25,
     'Audit 2026-05-08 (90-day MFE/MAE p70/p25, n=544). Counterfactual: mean per-trade return −0.0005% → +0.0127%.')
ON CONFLICT (ticker, calibration_date) DO NOTHING;

-- Audit 2026-05-08 G.P1.4 follow-up: blue-sky synth offset seed.
-- Derived from db-query.yml run 25588221502 — 12-month window of
-- gap-up days where pre_high IS NOT NULL, computing per-ticker median
-- and mean of (RTH high − pre_high)/ATR. n_extension_events were
-- 7-9 per ticker so values rounded to 0.05 grid for stability:
--
--   Ticker | mean ext | median ext | p75 ext | seeded
--   SPY    | 0.137    | 0.098      | 0.197   | 0.15
--   IWM    | 0.142    | 0.072      | 0.211   | 0.15
--   QQQ    | 0.178    | 0.180      | 0.227   | 0.20
--
-- Conservative rule: use the mean for SPY/IWM (similar distributions)
-- and bump QQQ slightly higher because its median > mean indicates a
-- right-skewed extension distribution (more big follow-throughs).
UPDATE exit_config_overrides
   SET blue_sky_atr_offset = 0.15
 WHERE ticker IN ('SPY', 'IWM') AND calibration_date = '2026-05-08'
   AND blue_sky_atr_offset IS NULL;
UPDATE exit_config_overrides
   SET blue_sky_atr_offset = 0.20
 WHERE ticker = 'QQQ' AND calibration_date = '2026-05-08'
   AND blue_sky_atr_offset IS NULL;

-- Audit 2026-05-08 G.P0.13: drop stoch_rsi_overbought + rsi_overbought_zone
-- from MR PUT scoring on IWM and QQQ specifically. Track E measured these
-- factors anti-correlated with PUT success on those tickers but not SPY,
-- so the drop is per-ticker not global. Live read by lib/signals.py:
-- evaluate_signal via lib/strategies/exit_config_overrides at fire time.
-- PR #329 added the column + live-read code; the IWM/QQQ-specific seed
-- values were never landed. Backfilling now (incident 2026-05-09 caught
-- this drift while investigating disabled_directions).
UPDATE exit_config_overrides
   SET disabled_conditions = '["stoch_rsi_overbought", "rsi_overbought_zone"]'::jsonb
 WHERE ticker IN ('IWM', 'QQQ') AND calibration_date = '2026-05-08'
   AND disabled_conditions IS NULL;

-- NOTE: The QQQ disabled_directions=["PUT"] seed that previously lived
-- here was REMOVED in incident-2026-05-09. A static direction kill switch
-- is too blunt — it suppresses every PUT regardless of daily bias. The
-- 11.1% MR PUT win-rate that justified G.P1.19 was measured pre-PR-#329
-- (before above_vwap was dropped from MR PUT scoring). Future
-- suppression should go through condition-level surgery (the
-- disabled_conditions block above) or a daily-bias-aware mechanism, NOT
-- a static gate. The disabled_directions COLUMN remains in case that
-- mechanism wants it later, but no rows seed it as of this commit.


-- ─────────────────────────────────────────────────────────
-- HISTORICAL_SIGNALS: parallel-strategy support (Phase 0.7)
-- ─────────────────────────────────────────────────────────
-- The historical_signals table is now populated by TWO different signal
-- generators that share an indicator pipeline but encode opposite CALL
-- logic:
--   * 'momentum'       — MarketAnalyzer.generate_technical_signals
--                        (CALL = consec_UP + above_VWAP + above_EMA9 + RSI 25-50)
--   * 'mean_reversion' — lib.signals.evaluate_signal
--                        (CALL = consec_DOWN + below_VWAP + below_EMAs + RSI 25-50)
--
-- Per Phase 0.7's Option B (keep both as parallel research paths), every
-- row carries a `strategy` tag. Existing rows backfill as 'momentum'
-- (status quo — only MarketAnalyzer wrote here before this migration).
--
-- See docs/plans/SIGNAL_QUALITY_TEST_PLAN.md §3.8-3.9 for the apples-to-
-- apples comparison showing the strategies are COMPLEMENTARY, not one-
-- strictly-better. Different (ticker, direction) classes favor different
-- strategies depending on regime.
-- ─────────────────────────────────────────────────────────

-- Step 1: Add the strategy column. Existing rows (all written by
-- MarketAnalyzer) backfill as 'momentum' via the DEFAULT.
ALTER TABLE historical_signals
    ADD COLUMN IF NOT EXISTS strategy VARCHAR(16) NOT NULL DEFAULT 'momentum';

-- Step 2: Add CHECK constraint (idempotent — drop+re-add).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'historical_signals_strategy_check'
    ) THEN
        ALTER TABLE historical_signals
            DROP CONSTRAINT historical_signals_strategy_check;
    END IF;
    ALTER TABLE historical_signals
        ADD CONSTRAINT historical_signals_strategy_check
        CHECK (strategy IN ('momentum','mean_reversion'));
END $$;

-- Step 3: Extend the PRIMARY KEY to (ticker, entry_time, strategy).
-- Both strategies can fire on the same bar minute — today's 5/1 morning
-- audit showed 182 minutes where both fired the same ticker, with 78.6%
-- of those firing OPPOSITE directions. The original PK (ticker, entry_time)
-- would force them to clobber each other on upsert.
DO $$
BEGIN
    -- Drop the old (ticker, entry_time) PK if it exists in that exact form.
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_name = kcu.table_name
        WHERE tc.table_name = 'historical_signals'
          AND tc.constraint_type = 'PRIMARY KEY'
          AND kcu.column_name = 'entry_time'
    ) AND NOT EXISTS (
        -- Skip if the new strategy-aware PK already exists.
        SELECT 1 FROM information_schema.key_column_usage kcu
        JOIN information_schema.table_constraints tc
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'historical_signals'
          AND tc.constraint_type = 'PRIMARY KEY'
          AND kcu.column_name = 'strategy'
    ) THEN
        ALTER TABLE historical_signals
            DROP CONSTRAINT historical_signals_pkey;
        ALTER TABLE historical_signals
            ADD CONSTRAINT historical_signals_pkey
            PRIMARY KEY (ticker, entry_time, strategy);
    END IF;
END $$;

-- Per-strategy queries get their own covering index. The existing
-- idx_historical_signals_ticker_time still serves strategy-agnostic
-- queries (ranker, charts page) unchanged.
CREATE INDEX IF NOT EXISTS idx_historical_signals_strategy_time
    ON historical_signals (strategy, ticker, entry_time DESC);


-- ─────────────────────────────────────────────────────────
-- SIGNAL_METRICS — Phase 0.5 productionized analysis pipeline
-- ─────────────────────────────────────────────────────────
-- Persisted output of `scripts/signal_quality_report.py`. Replaces the
-- throwaway CSV-based analysis (`scripts/_signal_eval_v*.py`) with a
-- queryable, scheduled, regression-alarmed source of truth for signal
-- quality measurement.
--
-- One row per (ticker, entry_time, strategy) — same composite key as
-- historical_signals so the join is trivial:
--    SELECT h.*, m.cls_60m, m.mfe_60m_atrs
--      FROM historical_signals h
--      JOIN signal_metrics m USING (ticker, entry_time, strategy)
--
-- `status='pending'` rows are intra-day rolling estimates (the 60m/90m/
-- 120m/240m windows haven't closed yet). The hourly Cloud Run Job
-- promotes them to `status='final'` once the windows complete. Phase
-- 0.5 weekly QA reports query only `status='final'`.
--
-- Classification labels (cls_*) match scripts/signal_quality_report.py:
--    'CLEAN_HIT'        — return ≥ +CLEAN_PCT (favorable)
--    'WRONG_DIRECTION'  — return ≤ -CLEAN_PCT (adverse)
--    'NOISE'            — abs(return) < NOISE_PCT
--    'MIXED'            — between NOISE_PCT and CLEAN_PCT
--    'INSUFFICIENT_DATA'— window not yet closed (rolling mode only)

CREATE TABLE IF NOT EXISTS signal_metrics (
    ticker            VARCHAR(10)      NOT NULL,
    entry_time        TIMESTAMPTZ      NOT NULL,
    strategy          VARCHAR(16)      NOT NULL DEFAULT 'momentum',

    evaluated_at      TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    -- Per-timeframe classification (one of CLEAN_HIT, WRONG_DIRECTION,
    -- NOISE, MIXED, INSUFFICIENT_DATA). VARCHAR(20) leaves headroom for
    -- adding labels without a migration.
    cls_5m            VARCHAR(20),
    cls_15m           VARCHAR(20),
    cls_30m           VARCHAR(20),
    cls_60m           VARCHAR(20),
    cls_90m           VARCHAR(20),
    cls_120m          VARCHAR(20),
    cls_240m          VARCHAR(20),

    -- The shortest timeframe at which the signal classified CLEAN_HIT,
    -- or NULL if no timeframe was clean. Used by the weekly QA report
    -- to surface "fast vs slow" winners.
    best_tf           VARCHAR(8),

    -- Per-timeframe MFE-style returns (favorable excursion as fraction,
    -- e.g. 0.012 = +1.2%). Sign convention matches the source row's
    -- direction — already converted from raw return so CALL and PUT
    -- can be classified with the same threshold.
    return_5m         DOUBLE PRECISION,
    return_15m        DOUBLE PRECISION,
    return_30m        DOUBLE PRECISION,
    return_60m        DOUBLE PRECISION,
    return_90m        DOUBLE PRECISION,
    return_120m       DOUBLE PRECISION,
    return_240m       DOUBLE PRECISION,

    -- Volatility context — used to unit-normalize the MFE so signals
    -- on a 0.3% ATR ticker (SPY) and a 2.5% ATR ticker (small-cap) are
    -- comparable.
    atr_5m_pct        DOUBLE PRECISION,
    mfe_60m_atrs      DOUBLE PRECISION,

    status            VARCHAR(12)      NOT NULL DEFAULT 'final'
                      CHECK (status IN ('final','pending')),

    PRIMARY KEY (ticker, entry_time, strategy)
);

CREATE INDEX IF NOT EXISTS idx_signal_metrics_evaluated_at
    ON signal_metrics (evaluated_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_metrics_status_eval
    ON signal_metrics (status, evaluated_at DESC);


-- ─────────────────────────────────────────────────────────
-- TIMEFRAME TAGS — Phase 1
-- ─────────────────────────────────────────────────────────
-- Hypothesis: different signals work on different timeframes — a 5m
-- scalp setup, a 15m breakout, and a 60m trend-continuation are not
-- the same trade and shouldn't be exited on the same time-stop.
--
-- timeframe_tag values:    '5m' | '15m' | '30m' | '60m' | '90m' | '120m' | '240m'
-- expected_hold_min:       upper bound of the timeframe bucket (planned holding period)
--
-- The heuristic that populates these columns lives in
-- lib/strategies/timeframe.py and is intentionally a documented
-- placeholder — it'll be refined from signal_metrics empirical data
-- in a follow-up phase.

ALTER TABLE signal_alerts
    ADD COLUMN IF NOT EXISTS timeframe_tag VARCHAR(8);
ALTER TABLE signal_alerts
    ADD COLUMN IF NOT EXISTS expected_hold_min INTEGER;

ALTER TABLE historical_signals
    ADD COLUMN IF NOT EXISTS timeframe_tag VARCHAR(8);
ALTER TABLE historical_signals
    ADD COLUMN IF NOT EXISTS expected_hold_min INTEGER;

-- ─── Phase 1.5 — catalyst-proximity tagging on every signal ────────
-- Signal quality is materially modified by proximity to known catalyst
-- events (FOMC/CPI/NFP/PCE/GDP, earnings, material 8-Ks). These six
-- columns enrich each fired signal with the closest scheduled or
-- recently-released catalyst so downstream analysis (Phase 0.5 weekly
-- QA, Phase 4 reweighting, Phase 2 cooldown) can stratify by
-- proximity_bucket. Population logic lives in
-- lib/strategies/catalyst_proximity.py — pure helpers + lru_cache'd
-- DB lookup keyed on (ticker, ts.floor('5min')).
--
-- proximity_bucket values:
--   'imminent'  ≤30 min before event      'post'     1-3 h after event
--   'pre'       30 min - 2 h before       'next_day' 3-24 h after event
--   'during'    0-60 min after event       'quiet'   nothing in window
--
-- catalyst_session: which US session the driving event sits in. Lets
-- the analysis separate pre-market 8:30 ET releases (CPI/NFP) from
-- intraday 14:00 ET releases (FOMC) from post-market earnings.
--
-- *_catalyst_type values: 'fomc' | 'cpi' | 'nfp' | 'pce' | 'gdp' |
--   'ism' | 'retail_sales' | 'jobless_claims' | 'beige_book' |
--   'fed_speaker' | 'earnings_pre' | 'earnings_post' | 'sec_8k'

ALTER TABLE signal_alerts
    ADD COLUMN IF NOT EXISTS next_catalyst_min   INTEGER,
    ADD COLUMN IF NOT EXISTS next_catalyst_type  VARCHAR(20),
    ADD COLUMN IF NOT EXISTS last_catalyst_min   INTEGER,
    ADD COLUMN IF NOT EXISTS last_catalyst_type  VARCHAR(20),
    ADD COLUMN IF NOT EXISTS catalyst_session    VARCHAR(12),
    ADD COLUMN IF NOT EXISTS proximity_bucket    VARCHAR(12);

ALTER TABLE historical_signals
    ADD COLUMN IF NOT EXISTS next_catalyst_min   INTEGER,
    ADD COLUMN IF NOT EXISTS next_catalyst_type  VARCHAR(20),
    ADD COLUMN IF NOT EXISTS last_catalyst_min   INTEGER,
    ADD COLUMN IF NOT EXISTS last_catalyst_type  VARCHAR(20),
    ADD COLUMN IF NOT EXISTS catalyst_session    VARCHAR(12),
    ADD COLUMN IF NOT EXISTS proximity_bucket    VARCHAR(12);


-- ─── Exit-watcher columns — entry/exit lifecycle on signal_alerts ──
-- Persists the resolution of each signal: when/why/at-what-price the
-- position was closed. Filled in by gcp/signal_monitor.py:_persist_exit
-- when the in-memory exit-watcher fires a TARGET HIT / TIME STOP /
-- RSI EXTREME alert. is_open lets analytics filter for live-this-minute
-- positions without scanning the whole table.
--
-- exit_reason values:
--   target_hit   — price reached call_target / put_target before time stop
--                  (set by gcp/signal_monitor.py:_persist_exit during the
--                   live in-process exit-watcher loop)
--   time_stop    — call_time_stop / put_time_stop minutes elapsed
--                  (set by gcp/signal_monitor.py:_persist_exit)
--   rsi_extreme  — RSI crossed call_rsi_exit (>=80) / put_rsi_exit (<=20)
--                  (set by gcp/signal_monitor.py:_persist_exit)
--   eod_close    — position still open at session close (16:00 ET); the
--                  in-process watcher only resolves while the SignalMonitor
--                  process is alive, so anything still open at close gets
--                  swept by the daily Cloud Run Job
--                  gcp/signal_monitor_eod_resolver.py at 16:30 ET / 20:30
--                  UTC (cron: 30 16 * * 1-5 America/New_York). Per Track D
--                  audit § 2 / G.P0.10 — implements the schema-anticipated
--                  fallback that previously left ~1,209 alerts with
--                  exit_ts NULL.

ALTER TABLE signal_alerts
    ADD COLUMN IF NOT EXISTS exit_ts          TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS exit_reason      VARCHAR(32),
    ADD COLUMN IF NOT EXISTS exit_price       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS exit_return_pct  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS is_open          BOOLEAN;

-- Track D / G.P3.5: default is_open to FALSE for any future ALTER-added
-- row so schema migrations don't silently leave NULL is_open values that
-- force every downstream filter to write `WHERE is_open IS TRUE OR
-- is_open IS NULL`. The persist path in gcp/signal_monitor.py:_persist_signal_alert
-- still writes `is_open=TRUE` explicitly on insert; this DEFAULT only
-- fills in for rows whose persist path forgets the column or for old
-- rows backfilled by ad-hoc UPDATEs.
ALTER TABLE signal_alerts
    ALTER COLUMN is_open SET DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_signal_alerts_open
    ON signal_alerts (ticker, alert_ts) WHERE is_open IS TRUE;


-- ─── Phase 2 — Brief↔Live coordination (visibility-only) ─────────
-- The premarket brief (premarket_analysis) and the live signal monitor
-- run as parallel systems with no coordination layer. On 2026-05-05 they
-- produced opposite directional opinions on QQQ — brief said PUT, live
-- fired CALL at 9:25 and was correct. We need data to decide whether
-- brief-aligned or brief-opposed live signals win more often, so this
-- phase persists the alignment without changing fire behavior.
--
-- brief_bias values match lib/strategies/brief_bias.py:
--   CALL | PUT | NEUTRAL | CONFLICTED | UNAVAILABLE
-- brief_alignment values:
--   aligned | opposed | NULL (when bias is NEUTRAL/CONFLICTED/UNAVAILABLE)
-- brief_setup_count: 0..5 (the N from "CALL setup (N/5)" in signal_status)

ALTER TABLE signal_alerts
    ADD COLUMN IF NOT EXISTS brief_bias        VARCHAR(16),
    ADD COLUMN IF NOT EXISTS brief_alignment   VARCHAR(16),
    ADD COLUMN IF NOT EXISTS brief_setup_count INTEGER;

-- Phase 1 prereq (issue #404, PR feat/replay-persist-mode):
-- replay-mode signal-monitor writes here too with these tag columns so
-- replay rows are identifiable + queryable but don't pollute live data
-- analysis. Live rows: run_kind='live' (default) AND replay_id IS NULL.
-- Replay rows: run_kind='replay' AND replay_id=<UUID-per-execution>.
-- This unlocks Phase 1 acceptance testing (need full per-fire detail
-- which Cloud Run logs truncate at ~85 records).
ALTER TABLE signal_alerts
    ADD COLUMN IF NOT EXISTS run_kind   VARCHAR(16) NOT NULL DEFAULT 'live',
    ADD COLUMN IF NOT EXISTS replay_id  UUID;

CREATE INDEX IF NOT EXISTS idx_signal_alerts_run_kind
    ON signal_alerts(run_kind) WHERE run_kind != 'live';
CREATE INDEX IF NOT EXISTS idx_signal_alerts_replay_id
    ON signal_alerts(replay_id) WHERE replay_id IS NOT NULL;

-- Phase 1 direction gate (per docs/audits/2026-05-10-risk-reviewer-validation.md):
-- the live signal_monitor reads insight_reports and decides whether
-- to suppress / downgrade / tag the fire. These columns record the
-- gate's view of each fire so we can post-hoc audit decisions and
-- measure missed-winner rate (shadow mode).
ALTER TABLE signal_alerts
    ADD COLUMN IF NOT EXISTS insight_direction  VARCHAR(8),     -- 'long'/'short'/'flat'/null
    ADD COLUMN IF NOT EXISTS insight_conviction VARCHAR(8),     -- 'low'/'medium'/'high'/null
    ADD COLUMN IF NOT EXISTS insight_regime     VARCHAR(20),    -- 'normal'/'extended'/'orb_only'/null
    ADD COLUMN IF NOT EXISTS gate_action        VARCHAR(16),    -- 'pass'/'suppress'/'downgrade'/'tag'/'annotate'
    ADD COLUMN IF NOT EXISTS gate_reason        TEXT,           -- short label, e.g. 'opposing_weak_vs_plan_long'
    ADD COLUMN IF NOT EXISTS thesis_invalidated BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_signal_alerts_gate_action
    ON signal_alerts(gate_action) WHERE gate_action IS NOT NULL;


-- ─────────────────────────────────────────────────────────
-- BACKTEST PIPELINE (Cloud Run job: backtest-pipeline)
-- ─────────────────────────────────────────────────────────
-- These three tables replace the file-based CSV hand-off the
-- backtest pipeline used when it ran as a GitHub Actions job.
-- scripts/run_backtest.py and scripts/run_timeframe_sweep.py
-- write the "simulate" stage output here; scripts/generate_
-- backtest_report.py reads it back, renders the markdown, and
-- records the run in backtest_reports.
--
-- A pipeline run is identified by a `run_id` UUID generated
-- once in scripts/run_pipeline.py and threaded through every
-- sub-step. Re-running with the same run_id is idempotent
-- (ON CONFLICT DO UPDATE on the natural keys below).

-- backtest_trades — one row per simulated trade. Columns mirror
-- lib/backtest.py:BacktestResult.to_dataframe() plus the run/
-- ticker/mode grouping columns.
CREATE TABLE IF NOT EXISTS backtest_trades (
    run_id         UUID             NOT NULL,
    ticker         VARCHAR(10)      NOT NULL,
    use_strat      BOOLEAN          NOT NULL,
    mode           VARCHAR(8)       NOT NULL,   -- 'base' | 'strat'
    trade_seq      INTEGER          NOT NULL,   -- 0-based trade index within (run_id, ticker, mode)

    -- Columns from BacktestResult.to_dataframe()
    entry_time     TIMESTAMPTZ,
    exit_time      TIMESTAMPTZ,
    direction      VARCHAR(4),                  -- 'CALL' | 'PUT'
    entry_price    DOUBLE PRECISION,
    exit_price     DOUBLE PRECISION,
    exit_reason    VARCHAR(16),                 -- 'target' | 'stop_loss' | 'time_stop' | ...
    base_score     INTEGER,
    strat_bonus    INTEGER,
    total_score    INTEGER,
    position_size  DOUBLE PRECISION,
    return_pct     DOUBLE PRECISION,
    mae            DOUBLE PRECISION,            -- Max Adverse Excursion
    mfe            DOUBLE PRECISION,            -- Max Favorable Excursion
    ftfc_score     DOUBLE PRECISION,            -- FTFC alignment at entry (-1..+1)
    orb_trend      INTEGER,                     -- ORB trend at entry (-1, 0, +1)
    conditions     TEXT,                        -- comma-joined conditions_met

    created_at     TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    -- trade_seq makes each simulated trade uniquely addressable so a
    -- re-run with the same run_id converges (ON CONFLICT DO UPDATE)
    -- rather than appending duplicates.
    CONSTRAINT uq_backtest_trades UNIQUE (run_id, ticker, mode, trade_seq)
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_run
    ON backtest_trades (run_id, ticker);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_ticker_created
    ON backtest_trades (ticker, created_at DESC);

-- backtest_sweeps — one row per (timeframe / combo) tested by
-- run_timeframe_sweep.py. Columns mirror the result_to_row()
-- dict that script builds plus the run/ticker grouping columns.
CREATE TABLE IF NOT EXISTS backtest_sweeps (
    run_id         UUID             NOT NULL,
    ticker         VARCHAR(10)      NOT NULL,
    label          VARCHAR(32)      NOT NULL,   -- e.g. '1m', '1m+15m', '5m+30m'
    sweep_type     VARCHAR(16)      NOT NULL,   -- 'single' | 'combo' | 'general_combo'

    trades         INTEGER,
    win_rate       DOUBLE PRECISION,
    avg_win        DOUBLE PRECISION,
    avg_loss       DOUBLE PRECISION,
    pf             DOUBLE PRECISION,            -- profit factor
    expectancy     DOUBLE PRECISION,
    max_dd         DOUBLE PRECISION,            -- max drawdown
    sharpe         DOUBLE PRECISION,

    created_at     TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_backtest_sweeps UNIQUE (run_id, ticker, label)
);

CREATE INDEX IF NOT EXISTS idx_backtest_sweeps_run
    ON backtest_sweeps (run_id, ticker);

CREATE INDEX IF NOT EXISTS idx_backtest_sweeps_ticker_created
    ON backtest_sweeps (ticker, created_at DESC);

-- backtest_reports — one row per pipeline run: the rendered
-- markdown plus structured aggregate metrics for quick querying
-- without re-parsing the markdown.
CREATE TABLE IF NOT EXISTS backtest_reports (
    run_id         UUID             PRIMARY KEY,
    tickers        TEXT[]           NOT NULL,
    report_md      TEXT             NOT NULL,

    -- Aggregate metrics across all tickers in the run (computed in
    -- generate_backtest_report.py from the primary trade set —
    -- strat if available, else base).
    total_trades   INTEGER,
    win_rate       DOUBLE PRECISION,
    expectancy_pct DOUBLE PRECISION,
    sharpe         DOUBLE PRECISION,

    created_at     TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_reports_created
    ON backtest_reports (created_at DESC);

-- ─────────────────────────────────────────────────────────
-- WALK_FORWARD_RESULTS: per-(parameter combo) walk-forward sweep output
--
-- Written by scripts/run_param_sweep.py — one row per parameter
-- combination tested, carrying the out-of-sample aggregate metrics and
-- the cross-fold stability_score the strategic selector ranks on. The
-- selected winner per ticker is also written to exit_config_overrides
-- so the live signal monitor picks it up on the next fire.
--
-- Sibling to backtest_sweeps (which sweeps timeframes); this table
-- sweeps strategy parameters with walk-forward validation.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS walk_forward_results (
    run_id              UUID             NOT NULL,
    ticker              VARCHAR(10)      NOT NULL,
    label               VARCHAR(48)      NOT NULL,   -- encodes the param combo

    -- The swept parameter values for this combo.
    consecutive_periods INTEGER,
    call_target         DOUBLE PRECISION,
    put_target          DOUBLE PRECISION,
    call_time_stop      INTEGER,
    put_time_stop       INTEGER,

    -- Out-of-sample aggregate metrics across the walk-forward folds.
    avg_expectancy_pct  DOUBLE PRECISION,
    avg_win_rate        DOUBLE PRECISION,
    std_expectancy_pct  DOUBLE PRECISION,
    stability_score     DOUBLE PRECISION,   -- fraction of profitable folds, 0..1
    total_folds         INTEGER,
    total_trades        INTEGER,

    -- TRUE for the combo the strategic selector promoted to
    -- exit_config_overrides for this (run_id, ticker).
    selected            BOOLEAN          NOT NULL DEFAULT FALSE,

    created_at          TIMESTAMPTZ      NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_walk_forward_results UNIQUE (run_id, ticker, label)
);

CREATE INDEX IF NOT EXISTS idx_walk_forward_results_run
    ON walk_forward_results (run_id, ticker);

CREATE INDEX IF NOT EXISTS idx_walk_forward_results_ticker_created
    ON walk_forward_results (ticker, created_at DESC);

-- ─────────────────────────────────────────────────────────
-- EARNINGS_CALIBRATION: tuned inputs for the playability score
--
-- Written by scripts/calibrate_earnings.py — the earnings sweep walks
-- the playability backtest over a grid of (min_nq, lookback_quarters)
-- and writes the combo with the best out-of-sample quintile hit-rate
-- spread here. The premarket brief reads the latest row (Tier A) via
-- lib/earnings_reactions.py:get_earnings_calibration(), falling back to
-- the env-var defaults (Tier B) when the table is empty.
--
-- Dated rows — latest wins, prior rows kept for audit.
-- ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS earnings_calibration (
    calibration_date  DATE             PRIMARY KEY,

    -- Tuned knobs (the sweep's winning combo).
    min_nq            INTEGER,         -- min past quarters to score
    lookback_quarters INTEGER,         -- recent-window cap; NULL = all history

    -- Achieved out-of-sample metrics for the winning combo.
    quintile_spread   DOUBLE PRECISION,  -- Q5 - Q1 hit-rate, 0..1
    overall_hit_rate  DOUBLE PRECISION,
    n_predictions     INTEGER,

    notes             TEXT,
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_earnings_calibration_recent
    ON earnings_calibration (calibration_date DESC);

-- Additive migration (2026-05-21): top-quintile dollar attribution.
-- The sweep restricts to Q5 directional archetypes
-- (bullish/bearish/reversal) and computes per-trade P&L over the 5d
-- canonical hold. `best_hold_horizon_days` reports which of
-- {1,3,5,10} maximised payoff_ratio.
-- All columns nullable: a degenerate combo (empty Q5, insufficient
-- sample) writes SQL NULL rather than fabricating $0
-- (CLAUDE.md §3.7 — no silent fallback on financial fields).
ALTER TABLE earnings_calibration
    ADD COLUMN IF NOT EXISTS n_q5_directional          INTEGER,
    ADD COLUMN IF NOT EXISTS avg_win_pct               DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS avg_loss_pct              DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS payoff_ratio              DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS expectancy_pct            DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS expectancy_dollars_per_1k DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS profit_factor             DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS max_drawdown_pct          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS sharpe_per_trade          DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS best_hold_horizon_days    INTEGER;

-- PR-B (2026-05-21): options-side dollar attribution. Sourced from
-- the T-1 close ATM call+put pair (and the delta-20 strangle wings)
-- in earnings_options_snapshots, with exit at T+1 close modelled as
-- intrinsic-only — a conservative bound. n_with_options is reported
-- separately so the % means are computed only over the matched
-- subset (not silently fabricated as 0 for unmatched events per
-- CLAUDE.md §3.7).
ALTER TABLE earnings_calibration
    ADD COLUMN IF NOT EXISTS n_with_options              INTEGER,
    ADD COLUMN IF NOT EXISTS avg_atm_straddle_iv_pct     DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS avg_implied_move_pct        DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS avg_realized_move_pct       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS realized_vs_implied_ratio   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS avg_long_straddle_pnl_pct   DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS avg_short_strangle_pnl_pct  DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS avg_long_call_pnl_pct       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS avg_long_put_pnl_pct        DOUBLE PRECISION;
