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

    -- Core indicators (from fetch_market_data.py)
    ma_5          DOUBLE PRECISION,
    ma_10         DOUBLE PRECISION,
    ma_20         DOUBLE PRECISION,
    ma_50         DOUBLE PRECISION,
    ma_390        DOUBLE PRECISION,
    ema_9         DOUBLE PRECISION,
    ema_21        DOUBLE PRECISION,
    ema_50        DOUBLE PRECISION,
    rsi_14        DOUBLE PRECISION,
    rsi_9         DOUBLE PRECISION,
    rsi_30        DOUBLE PRECISION,
    stoch_rsi_k   DOUBLE PRECISION,
    stoch_rsi_d   DOUBLE PRECISION,
    atr_14        DOUBLE PRECISION,
    atr_20        DOUBLE PRECISION,
    obv           DOUBLE PRECISION,
    rvol          DOUBLE PRECISION,
    rvol_10       DOUBLE PRECISION,
    volume_ma_10  DOUBLE PRECISION,
    volume_ma_20  DOUBLE PRECISION,
    volume_usd    DOUBLE PRECISION,

    -- Return / volatility
    return              DOUBLE PRECISION,
    volatility_30min    DOUBLE PRECISION,
    volatility_day      DOUBLE PRECISION,
    volatility_5d       DOUBLE PRECISION,
    volatility_20d      DOUBLE PRECISION,
    intraday_return     DOUBLE PRECISION,
    high_low_spread     DOUBLE PRECISION,
    high_low_spread_pct DOUBLE PRECISION,

    -- lib/indicators extras (add_all_indicators)
    consecutive_up      INTEGER,
    consecutive_down    INTEGER,
    vwap                DOUBLE PRECISION,
    price_vs_vwap       DOUBLE PRECISION,
    price_vs_ema9       DOUBLE PRECISION,
    price_vs_ema21      DOUBLE PRECISION,

    -- Strat fields (populated by analyze_market_data)
    strat_candle        VARCHAR(10),
    strat_combo         VARCHAR(30),
    strat_setup         BOOLEAN,
    ftfc_score          DOUBLE PRECISION,
    ftfc_direction      VARCHAR(10),

    -- Metadata
    data_source   VARCHAR(50),
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_market_data_daily UNIQUE (ticker, date)
);

CREATE INDEX IF NOT EXISTS idx_market_data_daily_ticker_date
    ON market_data_daily (ticker, date DESC);


CREATE TABLE IF NOT EXISTS market_data_intraday (
    id          BIGSERIAL PRIMARY KEY,
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

    CONSTRAINT uq_market_data_intraday UNIQUE (ticker, interval, ts)
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
