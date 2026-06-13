-- Phase 7 — daily_vex cache table.
--
-- Stores total_vex per (ticker, snapshot_date) so the P7 build job
-- doesn't re-compute it from the ~46M etf_options_snapshots rows on
-- every run. Computed once (or incrementally), reused thereafter.
--
-- ~7,500 rows total (3 tickers × ~2,500 dates). Tiny.

CREATE TABLE IF NOT EXISTS daily_vex (
    ticker         VARCHAR(16) NOT NULL,
    snapshot_date  DATE        NOT NULL,
    total_vex      DOUBLE PRECISION,
    spot_estimate  DOUBLE PRECISION,
    computed_at    TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, snapshot_date)
);
CREATE INDEX IF NOT EXISTS ix_daily_vex_date ON daily_vex (snapshot_date);
