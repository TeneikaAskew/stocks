-- Phase 1 universe inventory — which tickers have intraday coverage in
-- market_data_intraday_other, and what aux tables we have for features.

-- Top 200 tickers by intraday bar count in the "other" partition
SELECT ticker, count(*) AS n_bars,
       min(ts)::date AS min_d, max(ts)::date AS max_d,
       count(distinct date_trunc('day', ts)) AS n_trading_days
FROM market_data_intraday_other
WHERE interval = '1min'
GROUP BY ticker
ORDER BY n_bars DESC
LIMIT 200;

-- daily_rates coverage (for risk-free rate in Greeks / feature engineering)
SELECT count(*) AS n_rows, min(date) AS min_d, max(date) AS max_d
FROM daily_rates;

-- news_sentiment coverage
SELECT count(*) AS n_rows, count(distinct ticker) AS n_tickers,
       min(published_at)::date AS min_d, max(published_at)::date AS max_d
FROM news_sentiment;

-- strat_levels coverage
SELECT count(*) AS n_rows, count(distinct ticker) AS n_tickers,
       min(date)::date AS min_d, max(date)::date AS max_d
FROM strat_levels;

-- Existing backtest infrastructure (for benchmarking)
SELECT count(*) AS n_reports, min(created_at)::date AS min_d, max(created_at)::date AS max_d
FROM backtest_reports;

-- earnings_options_snapshots coverage (single-stock options around earnings)
SELECT count(*) AS n_rows, count(distinct ticker) AS n_tickers,
       min(snapshot_date) AS min_d, max(snapshot_date) AS max_d
FROM earnings_options_snapshots;

-- ticker_info — what universe metadata we have
SELECT count(*) AS n_rows
FROM ticker_info;
