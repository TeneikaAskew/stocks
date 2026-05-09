-- Issue #313 backfill — re-label `insight_reports_history.run_kind`
-- from 'manual_replay' to 'scheduled' for rows the daily 8:45 AM ET cron
-- actually wrote, when the scheduler payload didn't include
-- INSIGHT_TRIGGERED_BY=cloud-scheduler:* (fixed in deploy.sh
-- _schedule_insight helper).
--
-- Heuristic: the cron fires at 12:45 UTC (8:45 AM ET) on weekdays for
-- the 3 watchlist tickers SPY/IWM/QQQ. Any row matching those (ticker,
-- written_at-window, triggered_by NULL or empty) was almost certainly
-- the cron, mislabelled.
--
-- Run via:
--   gh workflow run db-query.yml \
--     -f sql_file=gcp/queries/backfill_run_kind_scheduled.sql \
--     -f commit=true
--
-- Without `commit=true` this is a no-op — the wrapper rolls back.
-- Audit run before commit by inspecting the SELECT below first
-- (uncomment, run with commit=false to see the row count, then run
-- with commit=true to apply).

-- Preview what would change (run this first with commit=false):
-- SELECT count(*) AS would_update,
--        run_kind,
--        date_trunc('week', written_at)::date AS week
-- FROM insight_reports_history
-- WHERE ticker IN ('SPY','IWM','QQQ')
--   AND run_kind = 'manual_replay'
--   AND extract(hour from (written_at AT TIME ZONE 'America/New_York')) = 8
--   AND extract(minute from (written_at AT TIME ZONE 'America/New_York')) BETWEEN 40 AND 55
--   AND extract(dow from (written_at AT TIME ZONE 'America/New_York')) BETWEEN 1 AND 5
-- GROUP BY run_kind, week ORDER BY week;

UPDATE insight_reports_history
   SET run_kind = 'scheduled',
       triggered_by = COALESCE(triggered_by, '') ||
                      ' [backfilled-from-cron-time-heuristic-2026-05-09]',
       notes = COALESCE(notes, '') ||
               E'\nIssue #313 backfill 2026-05-09: re-labelled run_kind ' ||
               'manual_replay→scheduled based on (ticker IN SPY/IWM/QQQ ' ||
               'AND written_at within 8:40-8:55 AM ET weekday window).'
 WHERE ticker IN ('SPY','IWM','QQQ')
   AND run_kind = 'manual_replay'
   AND extract(hour from (written_at AT TIME ZONE 'America/New_York')) = 8
   AND extract(minute from (written_at AT TIME ZONE 'America/New_York')) BETWEEN 40 AND 55
   AND extract(dow from (written_at AT TIME ZONE 'America/New_York')) BETWEEN 1 AND 5;

-- Post-update verify: the same window should now show run_kind='scheduled'
SELECT run_kind, count(*)
  FROM insight_reports_history
 WHERE ticker IN ('SPY','IWM','QQQ')
   AND extract(hour from (written_at AT TIME ZONE 'America/New_York')) = 8
   AND extract(minute from (written_at AT TIME ZONE 'America/New_York')) BETWEEN 40 AND 55
   AND extract(dow from (written_at AT TIME ZONE 'America/New_York')) BETWEEN 1 AND 5
 GROUP BY run_kind
 ORDER BY 2 DESC;
