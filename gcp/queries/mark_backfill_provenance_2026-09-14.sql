-- Mark the pre-existing backfilled rows in the three tables that gained a
-- run_kind column on the 2026-09-14 provenance audit (#1095). Same contract
-- as gcp/queries/mark_backfill_rows_2026-04-18.sql: atomic, self-checking,
-- a count outside the measured band raises and nothing commits.
--
--   ./scripts/db_query_cr.sh -f gcp/queries/mark_backfill_provenance_2026-09-14.sql --commit --timeout 600
--
-- WHY BANDS AND NOT EXACT COUNTS. The 04-18 query asserted exactly 432 and
-- 412 because that population was closed: the script that wrote it is
-- deleted and no live path reproduces those rows. These three are open, so
-- an exact count would be stale by the time an operator ran it. Each band is
-- the measurement plus headroom, tight enough to still fail loudly on a
-- predicate that has gone wrong (the 04-18 lesson: a predicate matching zero
-- rows read as success).
--
-- MEASURED IN PRODUCTION 2026-09-14 (db-query executions w2lsq, fwcrn,
-- 46dm4, d7z4k):
--
--   historical_signals   1,553,629 of 1,708,932 rows have inserted_at more
--                        than 7 days after entry_time. The live path runs on
--                        a 2-day lookback, so 7 days is generous.
--
--   insight_reports      the delay distribution is bimodal and clean:
--                          delay_days:  0 -> 721 rows
--                                       1 ->  10
--                                       2 ->   6
--                                       3+ ->  70 (long tail out to 33)
--                        The live pipeline writes same-day, every one of
--                        those 721. So ANY delay is a backfill, and the 86
--                        rows at delay >= 1 are all of them. An earlier
--                        revision used `> 2` and left the 16 rows at 1-2 days
--                        marked live; the band could not detect the omission
--                        because it had been measured with the same
--                        threshold (Codex on #1098).
--
--   premarket_analysis   74 of 395 rows have analysis_ts on a later calendar
--                        day than analysis_date, 70 more than a full day
--                        later, 50 more than a week.
--                        An earlier revision of this file claimed the table
--                        had NO timestamp and left every row 'live'. That was
--                        wrong: analysis_ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
--                        has been on the table since gcp/schema.sql:1341, and
--                        premarket_analysis_history already treats it as the
--                        original write time. The claim came from a
--                        column-name scan whose list did not include it — a
--                        proxy quoted without being spot-checked against a
--                        known case (CLAUDE.md §3.11). Caught by Codex.
--                        The brief runs premarket ET, so a real row's
--                        analysis_ts lands on analysis_date. More than a full
--                        day later is a replay. The 4 rows at exactly +1 day
--                        are left alone: a genuine late-evening or early
--                        next-morning manual run is indistinguishable from a
--                        same-day replay at that distance, and marking an
--                        honest row as backfill hides it from the dashboard.
DO $$
DECLARE
    n_signals INT;
    n_reports INT;
    n_briefs  INT;
BEGIN
    UPDATE historical_signals
       SET run_kind = 'backfill'
     WHERE run_kind = 'live'
       AND inserted_at::date - entry_time::date > 7;
    GET DIAGNOSTICS n_signals = ROW_COUNT;

    UPDATE insight_reports
       SET run_kind = 'backfill'
     WHERE run_kind = 'live'
       AND created_at::date > as_of::date;
    GET DIAGNOSTICS n_reports = ROW_COUNT;

    UPDATE premarket_analysis
       SET run_kind = 'replay'
     WHERE run_kind = 'live'
       AND analysis_ts::date > analysis_date + 1;
    GET DIAGNOSTICS n_briefs = ROW_COUNT;

    IF n_signals NOT BETWEEN 1500000 AND 1650000 THEN
        RAISE EXCEPTION
            'historical_signals: expected ~1,553,629 rows (band 1.50M-1.65M), matched %; nothing committed',
            n_signals;
    END IF;
    IF n_reports NOT BETWEEN 60 AND 250 THEN
        RAISE EXCEPTION
            'insight_reports: expected ~86 rows (band 60-250), matched %; nothing committed',
            n_reports;
    END IF;
    IF n_briefs NOT BETWEEN 50 AND 150 THEN
        RAISE EXCEPTION
            'premarket_analysis: expected ~70 rows (band 50-150), matched %; nothing committed',
            n_briefs;
    END IF;

    RAISE NOTICE 'marked % historical_signals backfill, % insight_reports backfill, % premarket_analysis replay',
        n_signals, n_reports, n_briefs;
END $$;
