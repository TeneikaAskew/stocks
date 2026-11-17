---
feat_id: FEAT-REPLAY-001
req_ids: [REQ-REPLAY-001, REQ-REPLAY-002, REQ-DATA-002, REQ-DATA-003, REQ-REL-001, REQ-CAP-001, REQ-CAP-002]
issues: [2027]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "D1 the store is declared and owns its ids: gcp/schema.sql creates schema replay and the tables of Design 1, each with replay_run_id as the first column of its primary key; tests/gcp/test_replay_store.py::test_schema_declares_every_replay_table_keyed_by_run passes by parsing gcp/schema.sql and fails when a table of Design 1 is missing, its key does not start with replay_run_id, a column default in schema replay calls nextval or names an object outside schema replay, or a foreign key in schema replay references a table outside it; tests/integration/test_replay_store_pg.py::test_replay_inserts_use_replay_ids_under_the_replay_role passes on a Postgres built from gcp/schema.sql: connected as a role with SELECT on schema public and write only on schema replay, an insert that omits id into replay.premarket_analysis, replay.premarket_analysis_history and replay.insight_reports_history succeeds, and the last_value of the three live sequences (the BIGSERIAL ids of gcp/schema.sql:1328, :2054, :2350) is unchanged"
  - "D2 the write fence holds every write path: tests/gcp/test_replay_store.py::test_a_run_writes_nothing_outside_the_replay_schema passes: with REPLAY_RUN_ID set and a fake DBAPI connection that records what reaches it, each of gcp.database.upsert_dataframe, bulk_insert_dataframe, bulk_copy_upsert, bulk_copy_update, replace_rows_in_window, execute_sql and execute_returning_scalar (an INSERT ... RETURNING id), a statement run through get_engine().begin() (the calibration writer gcp/calibrate_level_params.py:424-433), a cursor of get_engine().connect().connection (lib.strat_levels.persist_level_map), and a cursor of lib.agents.model_routing.connect() (the insight writer) raises ReplayWriteRefused for an INSERT, UPDATE, DELETE, MERGE, TRUNCATE, COPY ... FROM, SELECT ... INTO or DDL naming a table outside schema replay and the statement never reaches the connection, while the same statement naming the replay.* table of Design 1, and a temporary table, reaches it; with REPLAY_RUN_ID unset the existing tests/gcp/test_database*.py and tests/lib/test_model_routing*.py pass unchanged"
  - "D3 the pull is the nightly's own fetch: tests/gcp/test_replay_full_pull.py::test_pull_uses_fetch_month_and_writes_replay_bars_only passes: with requests.get stubbed to answer a TIME_SERIES_INTRADAY body of four bars (2026-11-16 04:00 to 04:03 ET, the SPY values of Design 8) and a recording connection, the pull sends exactly the params of gcp.fetchers.fetch_alphavantage_intraday.fetch_month (adjusted 'false', entitlement 'realtime', extended_hours 'true', outputsize 'full', month '2026-11') plus apikey, writes four replay.intraday_bars rows whose ts are 2026-11-16 09:00 to 09:03 UTC (lib.eastern_time.eastern_index_to_utc), writes one replay.pulls row with reason 'success', rows 4, the request without the key and the sha256 of the body, and writes no table outside schema replay; ::test_pull_months_cover_each_read_window passes: for sessions 2026-11-09 to 11-16 run on 2026-11-17 the months fetched are 2026-10 and 2026-11 (read_window((2026, 11)) starts 2026-10-25 02:00Z; 2026-12 is after the current Eastern month), and for sessions 2026-10-26 to 10-30 run on 2026-11-17 they are 2026-09, 2026-10 and 2026-11"
  - "D4 the pull never ends quietly: tests/gcp/test_replay_full_pull.py::test_pull_refuses_and_records passes: a ticker other than SPY, QQQ or IWM, a session after the current Eastern date, a run id that exists with other parameters, and the database not configured each exit 1 before any vendor call; a month answered with a rate-limit note or a request error is recorded in replay.pulls with that FETCH_* reason, no bar row is written for it, and the run exits 1; the API key appears in no log line, no row and no object (asserted by searching every captured record for the key)"
  - "D5 the data fixes are the live functions on the live windows: tests/gcp/test_replay_full_pull.py::test_premarket_reads_are_premarket_snapshot_at_each_cutoff passes on tests/fixtures/replay_2026_11/ (the experiment's bars for 2026-11-13 and 11-16, the prior session rows and each session's market_data_daily pre_filter_params): each replay.premarket row equals gcp.fetchers.fetch_market_data.premarket_snapshot on the same bars cut at the same instant with the same prior and filter; with the recorded filter the refresh_0820 reads of 2026-11-16 give pre_high and pre_low SPY 752.90 and 747.96 (cutoff 08:20:58 ET), QQQ 675.49 and 668.33 (08:20:55), IWM 276.97 and 275.74 (08:20:48); ::test_each_read_kind_reads_its_own_source passes: for SPY 2026-11-13, with an as-read record built by gcp.fetchers.premarket_as_read.build_record from the fixture bars before 08:20:57 ET and the full pull beside it, refresh_0820 is computed from the record (pre_high 759.75, filter-only high 759.86) and nightly_0930 from the pull (pre_high 762.67, filter-only high 762.6931, a high set after the refresh), and a nightly_0930 read is never computed from an as-read record; ::test_flags_are_judged_over_the_live_read_window passes on synthetic bars written in the test from 2026-09-24 to 2026-11-08 with one isolated print in the last bar of 2026-10-30 (20:00 ET, the last bar before the 2026-10 month window ends): the replay's 2026-10 flags equal gcp.fetchers.intraday_bar_flags.judge_month over read_window((2026, 10)) cut at the coverage checked_at given, and flag that bar, while judge_month over the month window alone does not flag it (lib/bar_prints.py judges no bar without two neighbours on each side), so the margin is proven to matter"
  - "D6 the brief replays into the store, reads only what it is allowed, and posts nothing: tests/gcp/test_premarket_brief_replay_store.py::test_replay_run_reads_and_writes_the_store_only passes: with REPLAY_RUN_ID, BRIEF_AS_OF=2026-11-16 and BRIEF_POST_TO_DISCORD=true, and a recording connection that logs every statement, (a) the session premarket handed to build_session_levels equals the replay.premarket row (read_kind refresh_0820), (b) no statement reads premarket_analysis or market_data_intraday in schema public (the live basis, the late slot's rows and the dry run's bars are replaced by the run's own rows), (c) every other relation read is in the test's named allowlist of reference reads (market_data_daily rows before the session for the brief tickers, and the session-day and later rows of earnings reporters that the earnings and AMC sections join, gcp/premarket_brief.py:432-433 and :786-787; ticker_level_params, level_param_policy, ticker_calibration, watchlists, etf_options_snapshots, economic_events, earnings_calendar, earnings_reactions and earnings_calibration), and a read of a relation outside it fails the test, (d) every write names replay.premarket_analysis (run_kind 'replay'), replay.premarket_analysis_history or replay.strat_levels with the run id, (e) the null-close cleanup is not run and send_to_discord is never called; without REPLAY_RUN_ID the existing tests/gcp/test_premarket_brief*.py pass unchanged"
  - "D7 the insight replays into the store and reads only what it is allowed: tests/gcp/test_insight_pipeline_replay_store.py::test_replay_run_reads_the_runs_brief_and_writes_the_store_only passes: with REPLAY_RUN_ID, INSIGHT_AS_OF=2026-11-16T08:45:00-05:00, a recording connection, and a usable etf_options_snapshots chain dated 2026-11-13 so that summarize_gamma_levels reaches gamma.build_summary and its rate lookup (lib/agents/summarizers.py:905-909, lib/gamma.py:1086-1088), (a) the level basis is the run's replay.premarket_analysis row and the session premarket the replay.premarket row, and neither LIVE_LEVEL_BASIS_SQL nor SESSION_PREMARKET_SQL (lib/strat_levels.py:3030, :2167) is issued, (b) every other relation read is in the test's named allowlist of reference reads (market_data_daily rows before the session, read by summarize_market_context, the strat status and the backtest analogs; etf_options_snapshots before the session; daily_rates at or before the chain's snapshot date, lib/options_greeks.py:195-205; economic_events, earnings_calendar, news_sentiment, sec_filings and journal_entries under the bounds of D8; ticker_level_params, level_param_policy, model_routing, watchlists, watchlist_history and watchlist_history_origin, the membership at the as-of, gcp/fetchers/_watchlist.py:200-238), the test asserts the daily_rates read was issued, and a read outside the allowlist fails the test, (c) every write names replay.insight_runs, replay.insight_reports or replay.insight_reports_history with the run id, (d) no Discord push is made; a date-only INSIGHT_AS_OF with REPLAY_RUN_ID set exits 1 before any read; without REPLAY_RUN_ID the existing tests/gcp/test_insight_pipeline*.py pass unchanged"
  - "D8 a replay reads no news or filing from after its instant: tests/lib/test_summarizers_as_of_bounds.py::test_catalyst_news_stops_at_the_instant passes against a Postgres fixture (tests/integration) or a query stub that applies the bound SQL: with as_of 2026-11-16T08:45:00-05:00 and catalyst-tagged SPY headlines published at 08:44:59, 08:45:00 and 2026-11-17 08:00 ET, summarize_catalysts returns only the 08:44:59 headline (today 08:45:00 and the next morning are both admitted on origin/main, where the bound is the as_of plus 23 hours 59 minutes, lib/agents/summarizers.py:1723-1737); ::test_same_day_filings_are_left_out_of_a_replay passes: an 8-K with filing_date 2026-11-16 is left out for that as_of and kept for as_of 2026-11-17T08:45:00-05:00 (sec_filings holds a date only, so a filing of the session day cannot be placed before or after 08:45); ::test_reflection_memory_stops_at_the_instant passes: for that as_of, retrieve_similar_journal leaves out a journal entry whose exit_ts or created_at is at or after 08:45 ET (its return_pct is an outcome the morning could not know; lib/agents/summarizers.py:1975-2004 has no time bound on origin/main); with as_of None every query and result equals origin/main's"
  - "D9 the comparison report covers every family: tests/gcp/test_replay_compare.py passes one case per family, each a fixture equal on both sides except one item, where the summary says accurate false and only that family counts one difference: bars (SPY 2026-11-16 04:02 ET volume 7151 stored, 968 replay; a replay holding no bar after 19:50 ET of that session, which must report the 10 stored bars after it as only_stored; and an empty replay for that session, which must report all 960 stored bars as only_stored; on origin/main premarket_as_read.compare_bars reports 0 only_stored for both, run 2026-11-17 on the experiment's bars), flags (one flag on the replay side only; and a replay flag on a bar stamped after the live coverage's checked_at, reported not_published), premarket (IWM 2026-11-16 refresh_0820 low published 275.86, replay 275.74, cause data_revision), trigger (SPY 2026-11-16 calls PMK_H published 754.3772, replay 752.90, cause rule_change), stop (IWM 2026-11-16 calls stop PMK_L published 275.86, replay 275.74, cause data_revision), level pick (calls trigger name PMK_H published, PDH replay, cause level_pick), targets (calls_plan_t1 one cent apart), and the insight plan (InsightReport.stop, lib/agents/schema.py:329, one cent apart; and each of direction, entry_zone, targets and persona_plans in its own case); an all-equal fixture gives accurate true with zero in every family; a missing side is a row with status not_published or not_replayed, never a zero or a skipped line"
  - "D10 the guards hold: tests/meta/test_production_writers.py passes with gcp/replay_full_pull.py registered in REPLAY_PATH and one new entry, REPLAY_FETCH_INTO_STORE, holding exactly (gcp/replay_full_pull.py, pull); a new test there asserts that every write reached from that entry names a replay.* table and that the test fails on a snippet writing market_data_intraday from it; test_only_the_two_fetchers_write_one_minute_bars and test_only_named_entry_points_reach_the_intraday_writers pass with their lists unchanged"
  - "D11 close: make test and make test-integration pass on the PR head; the PR body's Capacity section carries the numbers of this spec's Capacity section re-measured on the head; the FEAT-REPLAY-001 catalog record and the traceability entry name the PR"
status: approved
supersedes: null
---

# Full-pull replay into a separate store (SPY, QQQ, IWM)

## Authority and status

Approved by the owner on 2026-11-17: asked for the ten decisions below, the owner answered "Overcome all blockers", which takes the recommended (first) option on each. The request, relayed from the owner's chat on 2026-11-17: pull the 1-minute bars
fresh from AlphaVantage exactly as the live fetcher does, through the deployed fetcher code path;
apply the data fixes the way live would; store the result in a separate replay store, never over the
live rows or bars; run the brief and the insights on that data as if live; compare bars, premarket
high and low, triggers, stops and quarter targets with what is stored now, showing every difference
and whether the replay is accurate. Start with 2026-11-09 to 2026-11-16 for SPY, QQQ and IWM. "Do no
data changes in place anywhere." If the code cannot do it, say what is missing and draft the spec;
do not work around it.

This spec answers it. Every claim below was read on `origin/main` f6e2a736b or run on 2026-11-17;
what was not checked says so.

## Capability

FEAT-REPLAY-001 (Point-in-time replay + evaluation). Its record is the one that governs where a
replay's bars come from: its Status names #1891, under which replays read 1-minute bars only from
`market_data_intraday` and start no fetch, held by the guard in
`tests/meta/test_production_writers.py` (`REPLAY_PATH` at `:388`, `REPLAY_EXEMPT` at `:420`,
`test_every_replay_entry_point_is_registered` at `:1230`, `test_replay_paths_reach_no_vendor_or_bucket_bar_fetch`
at `:1256`). This spec changes exactly that contract for one new entry point, so it belongs there.
FEAT-DATA-001 owns ingestion into the live tables and is the alternative; it was not picked because
nothing here writes a live table. The change touches files other records list (`gcp/fetchers/`,
`gcp/premarket_brief.py`, `gcp/insight_pipeline_job.py`); the gate binds only workflows and the deploy
surface to an owner, so the job and scheduler wiring in `gcp/deploy.sh` is a separate FEAT-DEPLOY-001
change (Non-goals).

## Problem

### What exists today, step by step

| Step | What exists (read) | Why it is not enough |
|---|---|---|
| 1 Pull from AV as live | `fetch_month` (`gcp/fetchers/fetch_alphavantage_intraday.py:123-185`) sends TIME_SERIES_INTRADAY with `adjusted 'false'`, `entitlement 'realtime'`, `extended_hours 'true'`, `outputsize 'full'` (`:137-147`) and returns the month with naive Eastern stamps. `minute_bars_request` / `fetch_minute_bars` (`gcp/fetchers/fetch_market_data.py:85-179`) send the same request and keep one date. | Every caller writes the live table or nothing: `process_symbol` upserts into `market_data_intraday` (`:329-334`), `--replace-months` swaps months of the live table (`replace_month` `:765`, `replace_rows_in_window` at `:920` and `:948`), the daily fetcher's `write_intraday_to_sql` upserts the live table (`fetch_market_data.py:650-674`). With the database unconfigured `process_symbol` drops the frame. No caller keeps a pull anywhere else. |
| 2 Data fixes as live | Print filter and the extreme rules in `calculate_premarket_context` (`lib/indicators.py:563-843`: stale-close-report-v1, prior-close-print-v1, thin-bar-v1, two-bars-or-body-v1 at `:544-560`); `premarket_snapshot` (`fetch_market_data.py:392-474`, pure, the one function the nightly, the recompute and the brief dry run call); the isolated-print rule (`lib/bar_prints.py`, `RULE_VERSION` `:21`; `judge_month` `gcp/fetchers/intraday_bar_flags.py:247`, pure). | The writers are in place: the nightly premarket write (`fetch_market_data.py:578-628`) and `upsert_premarket` (`fetch_premarket_refresh.py:317`, `ON CONFLICT (ticker, date)` at `:412`) write `market_data_daily`; `--recompute-premarket --commit` rewrites it (`:1491`); `flag_months` writes `intraday_bar_flags` and `intraday_bar_flag_coverage`. The recompute and the dry run read only stored bars (`premarket_bars_sql` `:1379`, `PREMARKET_BARS_SQL` `premarket_brief.py:1028`). No consumer reads a bar flag: the only importers of `intraday_bar_flags` / `bar_prints` are the fetcher and `export_intraday_bars.py` (searched). |
| 3 Separate store | None. No schema, table, env var or argument chooses another target: a search of `lib`, `gcp`, `platform`, `scripts` for `search_path`, `DB_SCHEMA`, `REPLAY_STORE`, `REPLAY_RUN` and similar found nothing; `gcp/database.py` takes only `DB_NAME` for a whole database (`:63`, `:88`). The bucket copy `intraday-bars/v1/1min` is a copy of stored bars that no job, replay or route may read (`export_intraday_bars.py:1-19`). `premarket-as-read/v1` (`premarket_as_read.py:43`) keeps the refresh run's own read, from the first refresh after #2044 deploys; none existed at 12:25 UTC on 2026-11-17 (`gcloud storage ls` matched no object). | Nothing to write a replay into. |
| 4 Brief and insight as live | `BRIEF_AS_OF` (`premarket_brief.py:930`), `BRIEF_NO_PERSIST` (`:4549`), `BRIEF_PREMARKET_FROM_BARS` (`:1105-1185`, `:4689-4694`, dry run only, stored bars cut at the live basis's `fetched_at`); `INSIGHT_AS_OF` (`insight_pipeline_job.py:133`). | A replay writes the live tables in place. `BRIEF_AS_OF` sets `allow_update` (`:3851-3852`) and upserts `premarket_analysis` on `(analysis_date, ticker)` (`:4261`), the table's unique key (`gcp/schema.sql:1371`), so the replay row replaces the published one; `persist_level_map` upserts `strat_levels` on `(ticker, as_of, level_name)` with no run kind (`lib/strat_levels.py:3614-3618`, called at `premarket_brief.py:1777`); the null-close cleanup deletes from `market_data_daily` (`:1289`). The dry run writes nothing but prints only. The brief reads the session premarket from the `market_data_daily` row (`:1616`), not from bars. `INSIGHT_AS_OF` also sets `allow_update` (`insight_pipeline_job.py:307`) and upserts `insight_reports` on `(ticker, as_of)` (`:395`, `:439`), always writes `insight_runs` (`:195-210`), has no dry run, and reads the level basis only from the LIVE brief row (`lib/agents/summarizers.py:528-532`, `lib/strat_levels.py:3030-3034`) and the premarket from `market_data_daily` (`summarizers.py:518-525`). An `INSIGHT_AS_OF` instant does not bound catalyst news: `summarize_catalysts` ends the news window at the instant plus 23 hours 59 minutes (`summarizers.py:1723-1737`; the production query text run on a local Postgres 16 with as_of 2026-11-16 08:45 ET returned headlines stamped 08:45:00, 16:30 and 2026-11-17 08:00 ET), its 8-K read keeps every filing dated the session (`:1739-1752`, a date column), and a date-only `INSIGHT_AS_OF` reads the whole day's sentiment (`:1898-1901`). The outcome resolver updates `premarket_analysis` in place (`gcp/premarket_playbook_resolver.py:895`). |
| 5 Comparison | `premarket_as_read.compare_bars` (`:327`) counts as-read against stored bars. | It keeps only stored bars at or before the newest bar read, and none when the read is empty (`:364-368`), which is right for a refresh read and hides a short full pull. Nothing compares a replay's brief or insight with the published one. |

So: **no**. The code cannot pull from AlphaVantage into a separate store, apply the fixes there, run
the brief and the insight on it and compare, without writing live tables. Every replay path that
writes, writes the live rows.

### It already happened

`premarket_analysis` for 2026-11-10 holds `run_kind 'replay'` for SPY, QQQ and IWM (read-only query,
execution `db-query-fhjzq`). The published 08:31 ET brief (`premarket_analysis_history`, `scheduled`,
written 13:31:16Z) said SPY calls PDH 755.42 with stop PML 750.36; a `BRIEF_AS_OF` run at 22:30:46Z
(`replay_refresh`, triggered by `cloud-run-job`) replaced the canonical row with PMK_H 755.34 and stop
PDC 752.69, and the resolver resolved the replaced row (`outcome_resolved_at` 2026-11-11 02:15Z). A
reader of live rows finds no live 2026-11-10 brief. This is the in-place write the owner forbids.

### What the experiment of 2026-11-17 measured (local, nothing written)

Three AlphaVantage calls through `fetch_month` (SPY, QQQ, IWM, month 2026-11, each answered in 0.69 to
0.86 s, at 12:20 UTC); stored rows read with `./scripts/db_query_cr.sh` without `--commit`
(`db-query-gdxsf` bars, `db-query-fhjzq` daily, brief, flag rows); all computation by production
functions on local files.

- **Bars.** For each ticker and each session 2026-11-09, 10, 11, 12, 13 and 16, the fresh pull and
  `market_data_intraday` hold the same minutes and the same prices and volumes: 16,724 bars, 0 only on
  one side, 0 differing (every stored bar of each session against the pull, with no newest-bar cutoff,
  at `compare_bars`' tolerance and again at 0.0001). Every stored row reads as a
  true UTC instant (`stored_intraday_to_eastern`: 0 label rows, 0 dropped of 30,719).
- **Flags.** `judge_month` on the fresh bars gives the same 188 isolated-print flags for those sessions
  as `intraday_bar_flags` holds, none on one side only. That used November bars only: enough for
  those sessions, not for every flag of the month, whose live read window starts 2026-10-25 02:00Z
  (Design 3).
- **The stored premarket is the old rule, not the brief's read.** `market_data_daily` premarket values
  for 2026-11-05 to 11-13 were rewritten on 2026-11-15 06:01Z by `--recompute-premarket --commit`
  (`pre_recompute_run` = `fetch-market-data-686d7`; the marker is set only by that path,
  `gcp/bar_recompute.py:478-496`); 11-16 by the nightly. All 36 stored highs and lows equal the
  filter-only extremes of the whole premarket (`confirmed.raw_high` / `raw_low`) on the fresh bars.
- **The morning read cannot be reproduced from a pull.** For 2026-11-11 to 11-16 (12 ticker-sessions
  with a recorded `level_basis.premarket`), the high or low the 08:20 brief read differs from the same
  rule on today's bars at the same cutoff in 11 of 12, and no cutoff from 07:50 to 08:20 ET reproduces
  it in those 11 (only SPY 2026-11-12 matches). This extends #2027 (one day, 2026-11-16) to four days.
- **The current rules move the levels.** Under main's rules (v5), the premarket high at the brief's
  cutoff differs from what the brief read in 11 of 12 ticker-sessions and the low in 6; at 09:30 the
  high differs from the stored value in 17 of 18 and the low in 14 of 18 (largest 2.99 and 8.80).
  Of the 33 published trigger and stop legs that are PMK_H or PMK_L, 9 equal the v5 replay value, 9
  differ by the rule change only, 4 by the data revision only and 11 by both. 2026-11-09 and 11-10
  were published with no `level_basis` and no premarket level, so what the current brief would pick
  there needs a brief run (not done here).

## Non-goals

- No change to any live writer or live table, and no change to what the brief, the insight, the
  nightly, the refresh or the resolver do when `REPLAY_RUN_ID` is not set.
- No `gcp/deploy.sh` change: the job that runs the pull, fixes and comparison, and the env wiring of
  the brief and insight jobs for a replay, are a FEAT-DEPLOY-001 spec.
- No outcome scoring of replay rows (the resolver on the replay store) and no signal-monitor replay
  into the store. Both are later specs once the store exists.
- No ticker beyond SPY, QQQ and IWM. No second vendor.
- No change to the existing replay paths: they stay table-only under the #1891 guard.
- No claim that a replay of a session before the first as-read object reproduces the morning
  (Decision 4).
- No retention automation; a run is removed only by `drop --run-id` on the owner's request.

## Decisions (owner, 2026-11-17: the recommended option on each)

Each decision below is settled on its first, recommended option. The alternatives stay listed as the options considered.

1. **Store.** (a) Schema `replay` in the same Cloud SQL database, every table keyed by `replay_run_id`
   first; the vendor's answers kept as bucket objects beside it (recommended: the brief, insight and
   comparison read SQL, and a run is one predicate). (b) Bucket objects only (cheapest: about 0.47 MB
   a ticker-month as Parquet, measured `intraday-bars/v1/1min/SPY/2026-10.parquet` 484,775 bytes;
   but every SQL reader would need a second read path, which CLAUDE.md 3.7.1 and
   `export_intraday_bars.py:11-14` forbid for the tree). (c) A second database through `DB_NAME`
   (no reader change, but it needs copies of every reference table the brief and insight read,
   `market_data_daily` alone 4,211,417,088 bytes measured, and a misset `DB_NAME` is a live write).
2. **Write protection.** The code fence of Design 2 with its tests ships with this spec
   (recommended), and in addition a database role for replay runs with SELECT on `public` and write
   only on schema `replay` (recommended; production config, so the owner's step).
3. **The 2026-11-13 rule "no replay fetches".** Narrow it to: no replay writes a fetched bar anywhere
   but the replay store, and every existing replay path stays table-only (recommended). Or keep it
   and drop this capability.
4. **What the morning read is.** For a session with a premarket-as-read object (from the first
   refresh after #2044 deploys), the 08:20 and 09:20 reads use the object of that refresh; for every
   earlier session they use the full pull cut at the morning cutoff, labelled `vendor_revised`, and the
   report never calls it as-live (recommended; the experiment's 11 of 12). The nightly read always
   uses the pull (Design 4). Or treat the pull as the morning read.
5. **Daily inputs** (prior close, open, ATR, daily bars). Read live `market_data_daily` rows before
   the session, as the brief does, and record the values used (recommended). Pulling adjusted dailies into
   the store is not an option: #2047 removed every adjusted price fetch. Note the daily rows for
   2026-11-05 to 11-13 now say `av_daily_backfill`, so they were rewritten too.
6. **Filter thresholds.** As live: the level parameters in force on the session and the prior ATR
   (recommended). Or the filter the stored row recorded (`_recorded_premarket_filter`, what the dry
   run uses; the experiment used it).
7. **LLM calls.** Real calls for the week (recommended; insight measured at $0.0122 to $0.0128 a
   report), decide for a year after the week's report. Or deterministic fields only.
8. **"Published".** The latest `scheduled` or `live` history row written before 09:30 ET, the owner's
   scoring pick (recommended). Not the canonical row, which can be a replay (2026-11-10).
9. **Quarter targets.** Compare plan targets by the columns both rows hold; once the marks build
   (rule v6, spec r3 in #2053) lands its `plan_t4` and marks ride along with no change here; its
   reach history reads earlier rows of the same replay run (recommended) or live rows.
10. **Wider run.** A year only after the week's report is reviewed; 2015 onward after that.

## Approaches considered

1. Schema `replay` keyed by run, a write fence in `gcp/database.py`, and a `REPLAY_RUN_ID` switch in
   the brief and insight readers (chosen, Decision 1a).
2. Bucket objects with a dry-run brief printing its rows: no SQL change, but the insight has no dry
   run and reads the brief's live row, and every reader needs a bucket path the tree forbids.
3. A cloned database: no reader change, but a large copy, drift, and a live write when misconfigured.

## Design

### 1. The store

Schema `replay`, created by `gcp/schema.sql` (applied by the existing schema job; the apply itself is
the owner's step). Every table has `replay_run_id TEXT NOT NULL` first in its primary key.

- `replay.runs`: run id, requested_at, requested_by, tickers, first and last session, bar source per
  session (`as_read` or `vendor_revised`), `gcp.bar_recompute.code_version()`, status, vendor calls.
- `replay.pulls`: one row per (run, ticker, month): requested_at, answered_at, FETCH_* reason, rows,
  newest ts, the request as sent without the key (`minute_bars_request` shape), sha256 of the body,
  and the bucket object `replay/v1/<run_id>/pulls/<TICKER>/<YYYY-MM>.json.gz` holding the body.
- `replay.intraday_bars`: the columns of `market_data_intraday` plus run id; key (run, ticker,
  interval, ts); ts a true UTC instant.
- `replay.intraday_bar_flags`, `replay.intraday_bar_flag_coverage`: the live columns plus run id.
- `replay.premarket`: (run, ticker, date, read_kind) with read_kind `refresh_0820`, `refresh_0920`
  or `nightly_0930`, the cutoff instant, the bar source, the eleven `PREMARKET_COLUMNS`, the prior
  inputs and `bars_basis`.
- `replay.premarket_analysis`, `replay.premarket_analysis_history`, `replay.strat_levels`,
  `replay.insight_runs`, `replay.insight_reports`, `replay.insight_reports_history`: the live columns
  plus run id, keyed by run then the live key, each column written out in `gcp/schema.sql`.

No table of schema `replay` takes a default, a sequence or a foreign key from schema `public` (D1).
`LIKE ... INCLUDING DEFAULTS` is not used: it copies `nextval('<live sequence>')`. Run on a local
Postgres 16 (2026-11-17, throwaway cluster): the copied default read
`nextval('premarket_analysis_history_id_seq'::regclass)`, one replay insert moved the live sequence
from 1 to 2, and a role with SELECT on `public` and write on `replay` only got `permission denied for
sequence premarket_analysis_history_id_seq`. The three serial ids (`premarket_analysis`,
`premarket_analysis_history`, `insight_reports_history`: BIGSERIAL at `gcp/schema.sql:1328`, `:2054`,
`:2350`; the writers omit the id, e.g. `insight_pipeline_job.py:329-331`) are
`GENERATED BY DEFAULT AS IDENTITY` owned by the replay table: in the same run, inserts as the
restricted role succeeded and the live sequence stayed at 2. Other defaults (`gen_random_uuid()`,
`NOW()`, literals) are written out. `replay.insight_reports_history` references
`replay.insight_runs` on (run id, id), where the live table references `insight_runs` (`:2353`).

### 2. The write fence

`gcp/replay_store.py` holds the run context (`REPLAY_RUN_ID`, validated) and the table map. While a
run id is set, every statement is checked where it reaches the database driver, not in the helpers
alone, because the brief and the insight write past them: `persist_level_map` takes a raw cursor of
`get_engine().connect().connection` (`premarket_brief.py:1776-1781`, `lib/strat_levels.py:3633-3634`), the
calibration writer runs `get_engine().begin()` (`gcp/calibrate_level_params.py:424-433`, reached from
the insight through `_calibrate_on_demand`, `summarizers.py:547-565`), `bulk_copy_update` and
`execute_returning_scalar` open their own connections (`gcp/database.py:895`, `:1091`), and the
insight writes `insight_runs`, `insight_reports` and `insight_reports_history` through
`lib.agents.model_routing.connect()` (`model_routing.py:76-99`; `insight_pipeline_job.py:196`,
`:243`, `:324`, `:384`), which never touches `gcp.database`.

So the DBAPI connection made by `gcp.database`'s engine and the one `model_routing.connect()` returns
are both wrapped: a cursor refuses with `ReplayWriteRefused`, before the statement is sent, any
INSERT, UPDATE, DELETE, MERGE, TRUNCATE, COPY ... FROM, SELECT ... INTO or DDL whose target is not
in schema `replay` or a temporary table. The helpers of `gcp/database.py` check their table argument
first as well, so a refusal names the helper. With no run id nothing changes (D2). `record_job_run`
(`gcp/database.py:1180`) swallows its failure, so no replay entry point calls it; a run records
itself in `replay.runs`. The database role of Decision 2 is the backstop for a path the wrapper
misses. The guard of #1891 registers the new module in `REPLAY_PATH` with one named exemption,
`REPLAY_FETCH_INTO_STORE`, and a new test that every write reached from it names `replay.*` (D10).

### 3. Pull

`python -m gcp.replay_full_pull pull --run-id R --tickers SPY,QQQ,IWM --from FIRST --to LAST`. Target months:
the months holding a session in `[FIRST, LAST]`. Months pulled: every month that holds part of
`read_window(m)` for a target month m (`gcp/fetchers/intraday_bar_flags.py:185-189`: the month window
`[M-01 02:00Z, (M+1)-01 02:00Z)`, `lib/eastern_time.py:550-555`, widened by `READ_MARGIN`, 7 days,
`:56`, on each side), up to the current Eastern month. For 2026-11-09 to 11-16 run on 2026-11-17:
2026-10 and 2026-11, since `read_window((2026, 11))` is `[2026-10-25 02:00Z, 2026-12-08 02:00Z)` and
2026-12 has not begun. One `fetch_month` call per ticker-month, unchanged, paced by
`AlphaVantageConfig.delay_between_calls`; stamps converted with `eastern_index_to_utc`; one
transaction per ticker-month into `replay.intraday_bars`; one `replay.pulls` row per call, whatever
its reason. Refusals and exit codes as D4. The key is read from the environment and redacted.

### 4. Data fixes

`python -m gcp.replay_full_pull fix --run-id R`.

Flags, per ticker and target month: one read of the run's bars over `read_window(month)`, cut where
the live pass's read could reach (bars stamped before the live coverage row's `checked_at` when there
is one, since the live pass read the table as it stood then; the whole window otherwise; the cut is
recorded on the replay coverage row), then `judge_month` over that read, as `flag_months` does
(`intraday_bar_flags.py:397-410`), into the replay flag tables. Judging the month window alone would
lose the neighbours and the 61-bar scale of the bars near each month end. When the cut falls inside
the requested sessions, the month is judged a second time over the whole read window, and its flags
on bars at or after the cut are kept too, marked `judged_with 'full'`, so the comparison sees every
bar of every requested session.

Premarket, per session, `premarket_snapshot` once per read_kind, each from its own source:

| read_kind | Cutoff | Bars |
|---|---|---|
| `refresh_0820` | the live run's recorded `fetched_at` when the live basis has one, else 08:20:00 ET (schedule `20 8 * * 1-5`, `gcp/deploy.sh:4894`) | the session's 08:20 premarket-as-read object when one exists, else the run's pull cut at the cutoff (`vendor_revised`) |
| `refresh_0920` | 09:20 ET, once the late slot (#2020) is deployed | the 09:20 as-read object when one exists, else the pull cut at the cutoff (`vendor_revised`) |
| `nightly_0930` | 09:30 ET | the run's pull, always: an as-read object holds only the bars its refresh read, so a premarket extreme set after 08:20 or 09:20 is not in it (SPY 2026-11-13: filter-only high 759.86 before 08:20:57 ET, 762.6931 by 09:30, measured in the experiment) |

Prior inputs and thresholds per Decisions 5 and 6.

### 5. Brief

`BRIEF_AS_OF=D REPLAY_RUN_ID=R python -m gcp.premarket_brief`: the session premarket comes from
`replay.premarket` (refresh_0820, or refresh_0920 with `BRIEF_RUN_SLOT=late`) instead of the
`market_data_daily` row; daily bars, level parameters and calibration are read as today with the
as-of clock; rows go to the replay tables with run kind `replay` and `triggered_by 'replay:<R>'`;
the null-close cleanup does not run; Discord is never posted, whatever `BRIEF_POST_TO_DISCORD` says.
The earnings and AMC sections join the session-day `market_data_daily` rows of earnings reporters
(`premarket_brief.py:432-433`, `:786-787`); for a past session those rows hold values written after
the morning. They are allowed reads (D6), they feed no SPY, QQQ or IWM level, and they are outside
the comparison.

### 6. Insight

`INSIGHT_AS_OF=<D 08:45 ET> REPLAY_RUN_ID=R python -m gcp.insight_pipeline_job`: the level basis is
the run's own `replay.premarket_analysis` row, the premarket is `replay.premarket`; run, report and
history rows go to schema `replay`; no Discord push. Other inputs are read live with the as-of clock
(the reference reads of D7), as `INSIGHT_AS_OF` does today, with three bounds tightened, each only when
`as_of` is an instant, so a live run (as_of None) is unchanged (D8):

- catalyst news ends at the instant itself, `published_ts < :as_of`, not the instant plus 23 hours
  59 minutes (`summarizers.py:1723-1737`);
- an 8-K dated the session day is left out, because `sec_filings` holds a filing date and no time
  (`:1739-1752`), so it cannot be placed before or after the instant;
- under `REPLAY_RUN_ID` a date-only `INSIGHT_AS_OF` is refused, since `summarize_news_sentiment`
  reads a date as the whole day (`:1898-1901`);
- the reflection memory, `retrieve_similar_journal` (`:1975-2004`, called from
  `lib/agents/orchestrator.py:535`), reads only journal entries whose `exit_ts` and `created_at` are
  before the instant; today it has no time bound, so a replay would read trades closed after the
  morning with their `return_pct`.

The reference reads a replay keeps are the ones D7 lists. Beyond the obvious ones they include
`daily_rates`, which the gamma section reads whenever the chain is usable (`summarize_gamma_levels`
to `gamma.build_summary`, `summarizers.py:905-909`, to `get_rate_and_yield`, `lib/gamma.py:1086-1088`,
`lib/options_greeks.py:195-205`, by the chain's snapshot date or the last date before it), and the
watchlist membership at the as-of (`watchlist_history`, `watchlist_history_origin`,
`gcp/fetchers/_watchlist.py:200-238`), which the job and the backtest analogs resolve.

Other insight readers were read for the same pattern: `summarize_signals_history` also widens a date
to the whole day (`:986`) but is not in the bundle (`:944-959`); the options and gamma reads compare
`snapshot_date < :as_of` with `inclusive_today` False for the insight; the remaining readers were not
checked for intraday leakage (What was not checked).

### 7. Comparison

`python -m gcp.replay_full_pull compare --run-id R` prints, and writes `rows.csv` and `summary.json`
under `replay/v1/<run_id>/compare/`:

The bar comparison does not reuse `premarket_as_read.compare_bars`: that function keeps only the
stored bars at or before the newest bar read and none when the read is empty (`:364-368`), the right
rule for a refresh read that stopped at 08:20 and the wrong one for a full pull, where a truncated or
empty pull would report nothing missing (run 2026-11-17 on the experiment's SPY 2026-11-16 bars: cut
at 19:50 ET, 950 bars, it reported 950 stored and 0 only_stored against 960 stored; empty, all
zeros). The replay's comparator takes both sides by the session's Eastern date
(`lib.eastern_time.market_date`) with no cutoff, and reuses the per-field rules of
`premarket_as_read._counts` (`:309-325`) and its tolerance. A session of the exchange calendar
(`lib.eastern_time.session_schedule`) with no bar on either side is a row with status `no_bars`,
which makes the summary inaccurate.

Seven families, each its own rows and its own count in the summary (D9):

| Family | Replay side | Published side |
|---|---|---|
| bars | `replay.intraday_bars`, every bar of each requested session | `market_data_intraday`, every bar of the same session |
| flags | `replay.intraday_bar_flags` of each requested session, both judges | `intraday_bar_flags`, same rule version; a bar after the live pass's `checked_at` is `not_published` |
| premarket | `replay.premarket` high and low per read_kind, with the filter-only extremes (`confirmed.raw_high` / `raw_low`) | the published row's `level_basis.premarket` for the morning reads, `market_data_daily` for `nightly_0930` |
| triggers | calls and puts trigger name and price | the published row (Decision 8) |
| stops | calls and puts stop name and price | the published row |
| targets | t1 to t3 and every `plan_t` column both rows hold | the published row |
| insight plan | `InsightReport` direction, entry_zone, stop, targets and persona_plans (`lib/agents/schema.py:311-353`) | the live insight report of the session |

Per item: equal, or differs with a cause. For a premarket value, or a trigger, stop or target that is
PMK_H or PMK_L on both sides, the cause comes from the filter-only value of the same read, as in the
experiment: `rule_change` when the filter-only value equals the published one, `data_revision` when
it differs and the replay value equals it, `both` when it differs and the replay value differs from
it too. A different level name is `level_pick`; any other differing item is `value`. A missing side
is `not_published` or `not_replayed`. The summary says accurate only when every item of every family
is equal.

### 8. Fixtures

`tests/fixtures/replay_2026_11/`: the experiment's fresh bars for 2026-11-13 and 2026-11-16 (04:00 to
09:29 ET for the three tickers; SPY 2026-11-16 04:00 to 04:03 ET are 752.55/753.01/749.70/752.20 vol 14169,
752.30/752.90/749.70/752.13 vol 21038, 752.10/752.29/749.74/749.78 vol 7151,
749.73/752.78/749.73/752.07 vol 20902), the prior session daily rows, and each session's recorded
`pre_filter_params`, with the read executions named in a `sources.json`. The cross-month flag case
of D5 uses synthetic bars written in the test.

## Capacity

- **Vendor calls.** One a ticker-month, for each month a target month's read window touches
  (Design 3). The week 2026-11-09 to 11-16: 2 months (2026-10, 2026-11) x 3 = 6; the experiment made
  only the 3 November calls, enough for those sessions' flags but not for the whole month's. A year:
  12 target months and one month on each side, 14 x 3 = 42 (13 x 3 = 39 when the year ends in the
  current month). 2015-01 to 2026-11: 143 target months (143 SPY objects in the bucket copy) plus
  2014-12, 144 x 3 = 432 (whether the vendor answers 2014-12: not checked). Measured 0.69 to 0.86 s
  a call one after another, so a year is under a minute and the whole history about 6 minutes; the
  configured limit is 150 a minute. The daily budget is not checked against the vendor's plan.
- **Volume.** A full month is about 19,200 to 21,130 bars a ticker (October coverage rows: SPY
  21,129, QQQ 21,120, IWM 19,199; 61,448 for the three). At the live SPY partition's 364 bytes a row
  with indexes (911,327,232 bytes over 2,503,499 rows, `db-query-w4l46`): the week, October in full
  plus the November pull of 31,219 rows (10,767, 10,761, 9,691), is about 92,700 rows and 34 MB; a
  year, 14 months, about 860,000 rows and 313 MB a run. Premarket rows: 3 a session a ticker, about
  2,270 a year.
- **Velocity.** Writes in chunks of 5,000 per ticker-month (about 5 statements, about 210 a year for
  42 ticker-months); one bar read per ticker and target month for the flags (its read window, about
  1.4 months of bars) and one per ticker-month for the premarket reads; one brief run per session;
  one insight run per ticker-session.
- **Wall-clock.** Brief executions measured 28 to 110 s (2026-11-13 to 11-16). The week: 6 runs, 3 to
  11 minutes in sequence. A year: 252 runs, 2 to 8 hours in sequence, so striped by session over
  Cloud Run tasks (10 tasks: under an hour). Insight executions measured 32 to 72 s a ticker
  (2026-11-16), mean latency 32.6 to 43.2 s (`insight_reports` since 2026-10-17); the week 18 runs,
  a year 756 runs, 7 to 15 hours in sequence, striped (20 tasks: under an hour). Task timeout at 4x.
- **Cost.** Insight LLM: 18 x about $0.0125 = about $0.23 for the week, about $9.50 a year. Brief
  LLM explanations: not checked. Cloud SQL storage for 313 MB a year-run: price not checked. Max
  retries 0.

## Close-out (the owner's steps, after the merge and the FEAT-DEPLOY-001 wiring)

1. Apply the schema; create the replay role (Decision 2); as that role insert and delete one row in
   each replay table that has an identity id, and read the three live sequences' `last_value`
   before and after, unchanged.
2. Run the week: pull, fix, brief for each session, insight for each ticker-session, compare.
3. Before and after, read-only: `SELECT count(*), max(inserted_at) FROM market_data_intraday WHERE
   ticker IN ('SPY','QQQ','IWM') AND ts >= '2026-11-02'`, the same on `premarket_analysis_history`
   (`written_at`) and `insight_reports_history`, and `SELECT count(*) FROM premarket_analysis WHERE
   run_kind = 'replay'` unchanged; `SELECT count(*) FROM replay.intraday_bars WHERE replay_run_id =
   '<R>'` equal to the sum of `replay.pulls.rows`.
4. Post the comparison report on the PR; decide the wider run.

## Risks

- A reader the switch misses reads live rows: D6 and D7 fail on any relation outside their allowlist
  and on the replaced reads; a reader added later that reads an allowlisted relation for the session
  would show as a difference in the report, not as a live write (the fence holds writes).
- A writer the fence misses: D2 covers the driver connections of `gcp.database` and
  `model_routing.connect()` and every helper; a new connection factory would bypass it, and the role
  of Decision 2 is the backstop.
- A shared sequence or foreign key: D1 parses for them and the integration test inserts as the role.
- News or filings after the instant: D8; other readers are listed as not checked.
- Reading a revised pull as the morning: Decision 4 labels it and the report says it.
- A short or empty pull read as complete: the bar comparison has no newest-bar cutoff (D9).
- The #1891 guard weakened: D10 keeps its lists and adds one named, tested exemption.

## What was not checked

- The vendor's daily call limit and price; Cloud SQL storage price; brief LLM cost.
- Whether every insight input honours `INSIGHT_AS_OF`.
- Whether an `INSIGHT_AS_OF` report's `as_of` can equal a live report's (the upsert key).
- What the current brief would pick on 2026-11-09 and 11-10, and what the replayed insight plans
  would say (no brief or insight was run; the fields compared are named in Design 7).
- How the late 09:20 slot (#2020) records its cutoff once deployed.
- Whether any brief or insight reader other than the three of Design 6 admits a row from after the
  instant (the earnings tables, economic events as revised, options snapshots under a pg8000 text
  parameter, journal entries).
- Whether the vendor answers 2014-12 (the history run's first margin month).
