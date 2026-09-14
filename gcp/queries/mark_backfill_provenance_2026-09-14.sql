-- Mark the pre-existing backfilled rows in the three tables that gained a
-- run_kind column on the 2026-09-14 provenance audit. Same contract as
-- gcp/queries/mark_backfill_rows_2026-04-18.sql: atomic, self-checking, a
-- count outside the measured band raises and nothing commits.
--
--   ./scripts/db_query_cr.sh -f gcp/queries/mark_backfill_provenance_2026-09-14.sql --commit
--
-- WHY BANDS AND NOT EXACT COUNTS. The 04-18 query could assert exactly 432
-- and 412 because that population was closed: the script that wrote it is
-- deleted and no live path reproduces those rows. These three are open —
-- the brief, the pipeline and the signals job keep writing — so an exact
-- count would be stale by the time an operator ran it. Each band is the
-- measurement plus the headroom named below, which still fails loudly on a
-- predicate that has gone wrong (the 04-18 lesson: a predicate that matched
-- zero rows read as success).
--
-- MEASURED IN PRODUCTION 2026-09-14 (db-query executions w2lsq, 46sg7):
--   historical_signals   1,553,629 of 1,708,932 rows (90.9%) have
--                        inserted_at more than 7 days after entry_time.
--   insight_reports      70 of 807 rows have created_at more than 2 days
--                        after as_of.
--   premarket_analysis   unmeasurable: the table had no timestamp at all
--                        before this migration, so there is NO attribute
--                        that separates a past BRIEF_AS_OF replay row from
--                        a real morning row. Those rows are deliberately
--                        LEFT as 'live' rather than guessed at. Stating
--                        that here beats a marking rule that looks precise
--                        and is invented (CLAUDE.md §3.11).
DO $$
DECLARE
    n_signals INT;
    n_reports INT;
BEGIN
    -- A signal written more than a week after the bar it describes was not
    -- produced by the live cursor. 7 days is generous: the live path runs
    -- on a 2-day lookback (scripts/run_historical_signals.py --lookback-days).
    UPDATE historical_signals
       SET run_kind = 'backfill'
     WHERE run_kind = 'live'
       AND inserted_at::date - entry_time::date > 7;
    GET DIAGNOSTICS n_signals = ROW_COUNT;

    -- A report generated more than 2 days after its as_of is a
    -- generate_historical_report.py row; the live pipeline writes same-day.
    UPDATE insight_reports
       SET run_kind = 'backfill'
     WHERE run_kind = 'live'
       AND created_at::date > as_of::date + 2;
    GET DIAGNOSTICS n_reports = ROW_COUNT;

    IF n_signals NOT BETWEEN 1500000 AND 1650000 THEN
        RAISE EXCEPTION
            'historical_signals: expected ~1,553,629 backfilled rows (band 1.50M-1.65M), matched %; nothing committed',
            n_signals;
    END IF;
    IF n_reports NOT BETWEEN 50 AND 200 THEN
        RAISE EXCEPTION
            'insight_reports: expected ~70 backfilled rows (band 50-200), matched %; nothing committed',
            n_reports;
    END IF;

    RAISE NOTICE 'marked % historical_signals and % insight_reports as backfill; premarket_analysis left live (no attribute to separate on)',
        n_signals, n_reports;
END $$;
