-- Magnitude Engine — Phase 2 + Phase 4 table DDL.
--
-- Apply via: gh workflow run db-query.yml -f sql_file=gcp/queries/magnitude_engine_schema.sql -f commit=true
--
-- Phase 0 + Phase 1 + Phase 3 use existing tables only (strat_features_*,
-- strat_features_levels_*, economic_events) so this file is NOT required
-- for those phases. It is only required when Phase 2 or Phase 4 is
-- dispatched.
--
-- Walk-forward harness already creates magnitude_walk_forward_results
-- on first dispatch (idempotent CREATE IF NOT EXISTS in mag_walk_forward.py).

-- ─────────────────────── Phase 2: AlphaVantage indicators ──────────────
-- Source: alphavantage.co/query
-- function ∈ {ADX, MFI, ADOSC, AROON, ROC, BBANDS}
-- timeframes: daily + 15min (per spec)
CREATE TABLE IF NOT EXISTS market_data_indicators (
    ticker          VARCHAR(10)  NOT NULL,
    interval        VARCHAR(8)   NOT NULL,         -- 'daily' | '15min'
    ts              TIMESTAMPTZ  NOT NULL,
    -- Pre-computed indicator values from AV's premium endpoints.
    -- Naming follows av_<lowercased function>; AROON splits into up/down.
    av_adx                  DOUBLE PRECISION,
    av_mfi                  DOUBLE PRECISION,
    av_chaikin_ad_osc       DOUBLE PRECISION,
    av_aroon_up             DOUBLE PRECISION,
    av_aroon_down           DOUBLE PRECISION,
    av_roc                  DOUBLE PRECISION,
    av_bbands_upper         DOUBLE PRECISION,
    av_bbands_middle        DOUBLE PRECISION,
    av_bbands_lower         DOUBLE PRECISION,
    av_bbands_bandwidth     DOUBLE PRECISION,
    data_source             VARCHAR(50)  NOT NULL DEFAULT 'alphavantage',
    inserted_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, interval, ts)
) PARTITION BY LIST (ticker);

CREATE TABLE IF NOT EXISTS market_data_indicators_spy
    PARTITION OF market_data_indicators FOR VALUES IN ('SPY');
CREATE TABLE IF NOT EXISTS market_data_indicators_iwm
    PARTITION OF market_data_indicators FOR VALUES IN ('IWM');
CREATE TABLE IF NOT EXISTS market_data_indicators_qqq
    PARTITION OF market_data_indicators FOR VALUES IN ('QQQ');
CREATE TABLE IF NOT EXISTS market_data_indicators_other
    PARTITION OF market_data_indicators DEFAULT;

CREATE INDEX IF NOT EXISTS ix_mdi_lookup
    ON market_data_indicators (ticker, interval, ts DESC);


-- ─────────────────────── Phase 4: cross-asset ──────────────────────────
-- Source: AlphaVantage (VIX) + FRED (DGS10 → ust10y, DTWEXBGS → dxy) +
-- AV daily for oil/gold proxies (USO, GLD).
CREATE TABLE IF NOT EXISTS market_data_cross_asset (
    ticker          VARCHAR(10)  NOT NULL,   -- ticker we're FEATURIZING for
    interval        VARCHAR(8)   NOT NULL,   -- 'daily' | '5min' | '15min'
    ts              TIMESTAMPTZ  NOT NULL,
    -- Computed cross-asset metrics at (ticker, ts) — joined to bar t.
    vix_5m_delta            DOUBLE PRECISION,   -- VIX 5m close-to-close delta
    vix_z_15                DOUBLE PRECISION,   -- VIX 15-bar rolling z
    ust10y_delta            DOUBLE PRECISION,   -- 10Y yield 1-day delta (bp)
    dxy_delta               DOUBLE PRECISION,   -- DXY 1-day delta (%)
    oil_z                   DOUBLE PRECISION,   -- USO 20-day rolling z
    gold_z                  DOUBLE PRECISION,   -- GLD 20-day rolling z
    data_source             VARCHAR(50)  NOT NULL DEFAULT 'mixed',
    inserted_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker, interval, ts)
);

CREATE INDEX IF NOT EXISTS ix_mdca_lookup
    ON market_data_cross_asset (ticker, interval, ts DESC);
