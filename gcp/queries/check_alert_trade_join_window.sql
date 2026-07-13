-- Measures alert_ts <-> entry_time proximity for the examples-alert-enrichment
-- join predicate (task-alerts-enrichment-brief.md). Joins each `trades` row to
-- its nearest signal_alerts row by (ticker, direction), then buckets the
-- |entry_time - alert_ts| distance to pick a tight join window.
WITH nearest AS (
  SELECT DISTINCT ON (t.id)
    t.id AS trade_id, t.ticker, t.direction, t.entry_time,
    sa.id AS alert_id, sa.alert_ts, sa.target_price, sa.time_stop_minutes,
    EXTRACT(EPOCH FROM (t.entry_time - sa.alert_ts)) AS diff_seconds
  FROM trades t
  JOIN signal_alerts sa
    ON sa.ticker = t.ticker AND sa.direction = t.direction
  WHERE t.entry_time IS NOT NULL
  ORDER BY t.id, ABS(EXTRACT(EPOCH FROM (t.entry_time - sa.alert_ts)))
)
SELECT
  (SELECT count(*) FROM trades) AS total_trades,
  count(*) AS trades_with_any_alert_same_ticker_dir,
  count(*) FILTER (WHERE ABS(diff_seconds) <= 5) AS within_5s,
  count(*) FILTER (WHERE ABS(diff_seconds) <= 30) AS within_30s,
  count(*) FILTER (WHERE ABS(diff_seconds) <= 60) AS within_60s,
  count(*) FILTER (WHERE ABS(diff_seconds) <= 300) AS within_5min,
  count(*) FILTER (WHERE ABS(diff_seconds) <= 900) AS within_15min,
  count(*) FILTER (WHERE ABS(diff_seconds) > 900) AS beyond_15min,
  min(diff_seconds) AS min_diff_seconds,
  max(diff_seconds) AS max_diff_seconds,
  avg(diff_seconds) AS avg_diff_seconds
FROM nearest;
