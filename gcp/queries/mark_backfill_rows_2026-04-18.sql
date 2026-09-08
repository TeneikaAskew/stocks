-- Mark the rows scripts/backfill_signals.py (deleted on #1022) bulk-inserted
-- into production on 2026-04-18 02:59 UTC with no provenance marker (#820 R3):
-- 432 signal_alerts rows and the 412 trades rows that join them by
-- (ticker, alert_ts). Every reader now filters run_kind = 'live', so until
-- these are marked they are still counted as live fires and live trades.
--
-- Identified by attributes, measured in production on 2026-09-07 (db-query
-- execution vv4sb): alert_date 2026-03-19..2026-04-13 with total_score 3 and
-- strength_label 'weak' matches exactly 432 alerts; trades inserted between
-- 02:00Z and 04:00Z on 2026-04-18 that join those alerts number exactly 412.
-- The earlier schema.sql comment joined on a.run_kind='backfill' alone, and
-- the alerts are 'live' (the column default backfilled them), so run as
-- written it marked zero rows and read as success.
--
-- Atomic and self-checking: a count other than 432 / 412 raises and nothing
-- commits, so a re-run after success is a loud no-op, not a silent one.
--
--   ./scripts/db_query_cr.sh -f gcp/queries/mark_backfill_rows_2026-04-18.sql --commit
--
-- Verify afterwards:
--   SELECT run_kind, count(*) FROM signal_alerts GROUP BY 1;   -- backfill 432
--   SELECT run_kind, count(*) FROM trades GROUP BY 1;          -- backfill 412
DO $$
DECLARE
    n_alerts INT;
    n_trades INT;
BEGIN
    UPDATE signal_alerts SET run_kind = 'backfill'
     WHERE alert_date BETWEEN '2026-03-19' AND '2026-04-13'
       AND total_score = 3
       AND strength_label = 'weak'
       AND run_kind = 'live';
    GET DIAGNOSTICS n_alerts = ROW_COUNT;

    UPDATE trades t SET run_kind = 'backfill'
      FROM signal_alerts a
     WHERE a.ticker = t.ticker
       AND a.alert_ts = t.entry_time
       AND a.run_kind = 'backfill'
       AND t.inserted_at >= '2026-04-18 02:00Z'
       AND t.inserted_at <  '2026-04-18 04:00Z'
       AND t.run_kind = 'live';
    GET DIAGNOSTICS n_trades = ROW_COUNT;

    IF n_alerts <> 432 OR n_trades <> 412 THEN
        RAISE EXCEPTION 'expected to mark 432 alerts and 412 trades, matched % and %; nothing committed',
            n_alerts, n_trades;
    END IF;
    RAISE NOTICE 'marked % alerts and % trades as backfill', n_alerts, n_trades;
END $$;
