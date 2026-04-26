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
    ADD COLUMN IF NOT EXISTS last_1d_reactions   JSONB;            -- array of past 1-day post-earnings moves

CREATE INDEX IF NOT EXISTS idx_earnings_calendar_sp500_date
    ON earnings_calendar (earnings_date DESC, is_s_p_500 DESC NULLS LAST);

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
    strat_daily       VARCHAR(10),
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


-- ─────────────────────────────────────────────────────────
-- HELPER: auto-update updated_at on market_data_daily
-- ─────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

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
CREATE TABLE IF NOT EXISTS model_routing (
    role          VARCHAR(32)  PRIMARY KEY,
    provider      VARCHAR(32)  NOT NULL,   -- 'vertex' | 'anthropic' | 'openai'
    model         VARCHAR(64)  NOT NULL,
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_by    VARCHAR(64)
);

INSERT INTO model_routing (role, provider, model) VALUES
    ('analyst',           'vertex', 'gemini-2.0-flash'),
    ('bull',              'vertex', 'gemini-2.0-flash'),
    ('bear',              'vertex', 'gemini-2.0-flash'),
    ('judge',             'vertex', 'gemini-2.0-flash'),
    ('trader',            'vertex', 'gemini-2.0-flash'),
    ('risk',              'vertex', 'gemini-2.0-flash'),
    ('portfolio_manager', 'vertex', 'gemini-2.0-flash')
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
    latency_ms      INTEGER,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_insight_reports_ticker_asof UNIQUE (ticker, as_of)
);

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
                    CHECK (trigger IN ('on_demand','scheduled','local_dev')),
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
