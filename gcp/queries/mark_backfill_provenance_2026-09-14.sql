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
--
-- ROUND-3 CORRECTION, and it is the important one. The predicates above
-- originally used ONLY created_at / analysis_ts. Both are insert-only
-- defaults: premarket_brief.persist_to_cloud_sql builds canonical rows
-- without analysis_ts and upsert_dataframe updates only the columns in the
-- frame, and the historical-report conflict clause never touched created_at.
-- So a replay that OVERWROTE an existing same-key live row kept the
-- original same-day timestamp and stayed marked live: the rule missed
-- precisely the rows that matter most, and the count bands could not detect
-- it because they were measured with the same timestamps (Codex on #1098).
--
-- Measured 2026-09-14 (db-query dzqhv, rjqn2), joining each canonical row to
-- the latest append-only history entry for its key:
--
--   premarket_analysis   latest history kind   rows   also caught by analysis_ts
--     scheduled                                 243    0
--     replay_refresh                            128   63   <- 65 MISSED
--     backfill                                   15    7
--     manual_update                               5    0
--     manual_replay                               4    0
--
-- A TRAP in the obvious fix, worth stating because it inverts the meaning.
-- `run_kind='backfill'` in the HISTORY tables does not mean the canonical
-- row is backfilled content: scripts/backfill_history_tables.py stamped it
-- on every row it copied IN from the canonical tables when the history
-- tables were created. insight_reports_history carries 465 such rows. Taking
-- history 'backfill' as evidence would have hidden 465 legitimate reports.
-- Only 'replay_refresh' is unambiguous evidence of an as-of run, because
-- _resolve_run_kind_and_update assigns it exactly when BRIEF_AS_OF /
-- INSIGHT_AS_OF is set.
--
-- So the rule is the UNION: the latest history entry says replay_refresh, OR
-- the insert-only timestamp is late. 'manual_update' and 'manual_replay' are
-- left live: the first is assigned before the as-of branch is even tested so
-- it cannot distinguish the two, and the second is a hand-run of that day's
-- own brief.
DO $$
DECLARE
    n_signals INT;
    n_replays INT;
    n_reports INT;
    n_briefs  INT;
    n_extra   INT;
BEGIN
    UPDATE historical_signals
       SET run_kind = 'backfill'
     WHERE run_kind = 'live'
       AND inserted_at::date - entry_time::date > 7;
    GET DIAGNOSTICS n_signals = ROW_COUNT;

    -- insight_reports has TWO non-live writers and the marked rows must
    -- say which one, or migrated rows contradict new writes: INSIGHT_AS_OF
    -- stamps 'replay', generate_historical_report.py stamps 'backfill'
    -- (Codex on #1098 round 4). 'replay_refresh' in the history table is
    -- assigned by exactly the INSIGHT_AS_OF branch, so it is evidence of a
    -- replay and not of a batch backfill. Ordering matters: the replay pass
    -- runs first, and the backfill pass then only sees rows still 'live'.
    --
    -- Measured 2026-09-14 (db-query nzvbq), on the 86 rows the union
    -- predicate matches:  replay_refresh 1,  timestamp-only 85.
    UPDATE insight_reports r
       SET run_kind = 'replay'
     WHERE r.run_kind = 'live'
       AND EXISTS (SELECT 1 FROM (
               SELECT DISTINCT ON (ticker, as_of) ticker, as_of, run_kind
                 FROM insight_reports_history
                ORDER BY ticker, as_of, written_at DESC) h
            WHERE h.ticker = r.ticker AND h.as_of = r.as_of
              AND h.run_kind = 'replay_refresh');
    GET DIAGNOSTICS n_replays = ROW_COUNT;

    UPDATE insight_reports r
       SET run_kind = 'backfill'
     WHERE r.run_kind = 'live'
       AND r.created_at::date > r.as_of::date;
    GET DIAGNOSTICS n_reports = ROW_COUNT;

    -- History FIRST, timestamp as a supplement. See the block above.
    -- Both branches stamp 'replay', unlike insight_reports above: this
    -- table has exactly ONE non-live writer (BRIEF_AS_OF in
    -- premarket_brief.py), so a late analysis_ts is a replay run under a
    -- different trigger, never a batch backfill.
    UPDATE premarket_analysis p
       SET run_kind = 'replay'
      FROM (SELECT DISTINCT ON (analysis_date, ticker) analysis_date, ticker, run_kind
              FROM premarket_analysis_history
             ORDER BY analysis_date, ticker, written_at DESC) h
     WHERE h.analysis_date = p.analysis_date
       AND h.ticker = p.ticker
       AND p.run_kind = 'live'
       AND (h.run_kind = 'replay_refresh'
            OR p.analysis_ts::date > p.analysis_date + 1);
    GET DIAGNOSTICS n_briefs = ROW_COUNT;

    -- Rows with no history entry at all (written before the history table
    -- existed on 2026-04-12) can only use the timestamp.
    UPDATE premarket_analysis p
       SET run_kind = 'replay'
     WHERE p.run_kind = 'live'
       AND p.analysis_ts::date > p.analysis_date + 1
       AND NOT EXISTS (SELECT 1 FROM premarket_analysis_history h
                        WHERE h.analysis_date = p.analysis_date
                          AND h.ticker = p.ticker);
    GET DIAGNOSTICS n_extra = ROW_COUNT;
    n_briefs := n_briefs + n_extra;

    IF n_signals NOT BETWEEN 1500000 AND 1650000 THEN
        RAISE EXCEPTION
            'historical_signals: expected ~1,553,629 rows (band 1.50M-1.65M), matched %; nothing committed',
            n_signals;
    END IF;
    IF n_replays NOT BETWEEN 1 AND 60 THEN
        RAISE EXCEPTION
            'insight_reports replay: expected ~1 row (band 1-60), matched %; nothing committed',
            n_replays;
    END IF;
    IF n_reports NOT BETWEEN 60 AND 250 THEN
        RAISE EXCEPTION
            'insight_reports backfill: expected ~85 rows (band 60-250), matched %; nothing committed',
            n_reports;
    END IF;
    IF n_briefs NOT BETWEEN 110 AND 220 THEN
        RAISE EXCEPTION
            'premarket_analysis: expected ~135 rows (band 110-220), matched %; nothing committed',
            n_briefs;
    END IF;

    RAISE NOTICE 'marked % historical_signals backfill, % insight_reports replay, % insight_reports backfill, % premarket_analysis replay',
        n_signals, n_replays, n_reports, n_briefs;
END $$;
