---
feat_id: FEAT-REPLAY-001
req_ids: [REQ-REPLAY-001, REQ-REPLAY-002, REQ-DATA-002, REQ-DATA-003, REQ-REL-001, REQ-CAP-001, REQ-CAP-002]
issues: [2027]
canvases:
  - https://claude.ai/artifact/LXZ5iRtXogCyFfApfsxXVN
done_when:
  - "D1 the store is declared: gcp/schema.sql creates schema replay and the tables of Design 1, each with replay_run_id as the first column of its primary key; tests/gcp/test_replay_store.py::test_schema_declares_every_replay_table_keyed_by_run passes by parsing gcp/schema.sql, and fails when any table of Design 1 is missing or its key does not start with replay_run_id"
  - "D2 the write fence: tests/gcp/test_replay_store.py::test_a_run_writes_nothing_outside_the_replay_schema passes: with REPLAY_RUN_ID set, gcp.database.upsert_dataframe, bulk_insert_dataframe, bulk_copy_upsert, replace_rows_in_window and execute_sql with an INSERT, UPDATE or DELETE naming market_data_intraday, market_data_daily, intraday_bar_flags, premarket_analysis, premarket_analysis_history, strat_levels, insight_runs, insight_reports or insight_reports_history raise ReplayWriteRefused before an engine is created (a stub get_engine records no call), and the same calls naming the replay.* table of Design 1 reach the engine; with REPLAY_RUN_ID unset every live write is unchanged (the existing tests/gcp/test_database*.py pass unchanged)"
  - "D3 the pull is the nightly's own fetch: tests/gcp/test_replay_full_pull.py::test_pull_uses_fetch_month_and_writes_replay_bars_only passes: with requests.get stubbed to answer a TIME_SERIES_INTRADAY body of four bars (2026-11-16 04:00 to 04:03 ET, the SPY values of Design 8) and a recording engine, the pull sends exactly the params of gcp.fetchers.fetch_alphavantage_intraday.fetch_month (adjusted 'false', entitlement 'realtime', extended_hours 'true', outputsize 'full', month '2026-11') plus apikey, writes four replay.intraday_bars rows whose ts are 2026-11-16 09:00 to 09:03 UTC (lib.eastern_time.eastern_index_to_utc), writes one replay.pulls row with reason 'success', rows 4, the request without the key and the sha256 of the body, and issues no statement naming a table outside schema replay"
  - "D4 the pull never ends quietly: tests/gcp/test_replay_full_pull.py::test_pull_refuses_and_records passes: a ticker other than SPY, QQQ or IWM, a session after the current Eastern date, a run id that exists with other parameters, and the database not configured each exit 1 before any vendor call; a month answered with a rate-limit note or a request error is recorded in replay.pulls with that FETCH_* reason, no bar row is written for it, and the run exits 1; the API key appears in no log line, no row and no object (asserted by searching every captured record for the key)"
  - "D5 the data fixes are the live functions: tests/gcp/test_replay_full_pull.py::test_premarket_reads_are_premarket_snapshot_at_each_cutoff passes on tests/fixtures/replay_2026_11_16/ (the SPY, QQQ and IWM 2026-11-16 bars of the experiment of 2026-11-17, the prior session row and the session's market_data_daily pre_filter_params): each replay.premarket row equals gcp.fetchers.fetch_market_data.premarket_snapshot on the same bars cut at the same instant with the same prior and filter, and with the recorded filter the refresh_0820 reads give pre_high and pre_low SPY 752.90 and 747.96 (cutoff 08:20:58 ET), QQQ 675.49 and 668.33 (08:20:55), IWM 276.97 and 275.74 (08:20:48); the flag rows equal gcp.fetchers.intraday_bar_flags.judge_month on the same bars"
  - "D6 the brief replays into the store and posts nothing: tests/gcp/test_premarket_brief_replay_store.py::test_replay_run_reads_and_writes_the_store_only passes: with REPLAY_RUN_ID and BRIEF_AS_OF=2026-11-16, BRIEF_POST_TO_DISCORD=true and a recording engine, the session premarket is read from replay.premarket (read_kind refresh_0820) and never from the market_data_daily session row, rows are written to replay.premarket_analysis (run_kind 'replay'), replay.premarket_analysis_history and replay.strat_levels with the run id, no statement names a table outside schema replay, the null-close cleanup is not run, and send_to_discord is never called; without REPLAY_RUN_ID the existing tests/gcp/test_premarket_brief*.py pass unchanged"
  - "D7 the insight replays into the store: tests/gcp/test_insight_pipeline_replay_store.py::test_replay_run_reads_the_runs_brief_and_writes_the_store_only passes: with REPLAY_RUN_ID and INSIGHT_AS_OF set, summarize_session_levels reads the level_basis of the run's replay.premarket_analysis row and never the live row (read_live_level_basis is not called), the session premarket comes from replay.premarket, the insight_runs, insight_reports and insight_reports_history rows go to schema replay with the run id, no statement names a table outside schema replay, and no Discord push is made; without REPLAY_RUN_ID the existing tests/gcp/test_insight_pipeline*.py pass unchanged"
  - "D8 the comparison report: tests/gcp/test_replay_compare.py::test_compare_lists_every_difference_with_its_cause passes on fixture rows copied from the experiment of 2026-11-17 (Design 7): bars SPY 2026-11-16 960 replay and 960 stored, 0 differing; triggers SPY 2026-11-16 calls PMK_H published 754.3772 replay 752.90 cause rule_change, IWM 2026-11-16 puts PMK_L published 275.86 replay 275.74 cause data_revision, QQQ 2026-11-12 puts PMK_L published 679.14 replay 674.76 cause data_revision, SPY 2026-11-11 puts PMK_L 753.99 equal; the summary says accurate false and counts each cause; a published row that is missing is a row with status not_published, never a zero or a skipped line"
  - "D9 the guards hold: tests/meta/test_production_writers.py passes with gcp/replay_full_pull.py registered in REPLAY_PATH and one new entry, REPLAY_FETCH_INTO_STORE, holding exactly (gcp/replay_full_pull.py, pull); a new test there asserts that every write reached from that entry names a replay.* table and that the test fails on a snippet writing market_data_intraday from it; test_only_the_two_fetchers_write_one_minute_bars and test_only_named_entry_points_reach_the_intraday_writers pass with their lists unchanged"
  - "D10 close: make test passes on the PR head; the PR body's Capacity section carries the numbers of this spec's Capacity section re-measured on the head; the FEAT-REPLAY-001 catalog record and the traceability entry name the PR"
status: draft
supersedes: null
---

# Full-pull replay into a separate store (SPY, QQQ, IWM)

## Authority and status

Draft, not approved. The request, relayed from the owner's chat on 2026-11-17: pull the 1-minute bars
fresh from AlphaVantage exactly as the live fetcher does, through the deployed fetcher code path;
apply the data fixes the way live would; store the result in a separate replay store, never over the
live rows or bars; run the brief and the insights on that data as if live; compare bars, premarket
high and low, triggers, stops and quarter targets with what is stored now, showing every difference
and whether the replay is accurate. Start with 2026-11-09 to 2026-11-16 for SPY, QQQ and IWM. "Do no
data changes in place anywhere." If the code cannot do it, say what is missing and draft the spec;
do not work around it.

This spec is that draft. Every claim below was read on `origin/main` f6e2a736b or run on 2026-11-17;
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
| 4 Brief and insight as live | `BRIEF_AS_OF` (`premarket_brief.py:930`), `BRIEF_NO_PERSIST` (`:4549`), `BRIEF_PREMARKET_FROM_BARS` (`:1105-1185`, `:4689-4694`, dry run only, stored bars cut at the live basis's `fetched_at`); `INSIGHT_AS_OF` (`insight_pipeline_job.py:133`). | A replay writes the live tables in place. `BRIEF_AS_OF` sets `allow_update` (`:3851-3852`) and upserts `premarket_analysis` on `(analysis_date, ticker)` (`:4261`), the table's unique key (`gcp/schema.sql:1371`), so the replay row replaces the published one; `persist_level_map` upserts `strat_levels` on `(ticker, as_of, level_name)` with no run kind (`lib/strat_levels.py:3614-3618`, called at `premarket_brief.py:1777`); the null-close cleanup deletes from `market_data_daily` (`:1289`). The dry run writes nothing but prints only. The brief reads the session premarket from the `market_data_daily` row (`:1616`), not from bars. `INSIGHT_AS_OF` also sets `allow_update` (`insight_pipeline_job.py:307`) and upserts `insight_reports` on `(ticker, as_of)` (`:395`, `:439`), always writes `insight_runs` (`:195-210`), has no dry run, and reads the level basis only from the LIVE brief row (`lib/agents/summarizers.py:528-532`, `lib/strat_levels.py:3030-3034`) and the premarket from `market_data_daily` (`summarizers.py:518-525`). The outcome resolver updates `premarket_analysis` in place (`gcp/premarket_playbook_resolver.py:895`). |
| 5 Comparison | `premarket_as_read.compare_bars` (`:327`) counts as-read against stored bars. | Nothing compares a replay's brief or insight with the published one. |

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
  one side, 0 differing (`compare_bars`, and again at a 0.0001 tolerance). Every stored row reads as a
  true UTC instant (`stored_intraday_to_eastern`: 0 label rows, 0 dropped of 30,719).
- **Flags.** `judge_month` on the fresh bars gives the same 188 isolated-print flags for those sessions
  as `intraday_bar_flags` holds, none on one side only.
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

## Decisions for the owner (recommended first)

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
   refresh after #2044 deploys), the 08:20 and 09:20 reads use that object; for every earlier session
   they use the full pull cut at the morning cutoff, labelled `vendor_revised`, and the report never
   calls it as-live (recommended; the experiment's 11 of 12). Or treat the pull as the morning read.
5. **Daily inputs** (prior close, open, ATR, daily bars). Read live `market_data_daily` rows before
   the session, as the brief does, and record the values used (recommended). Or pull
   TIME_SERIES_DAILY_ADJUSTED full into the store (one call a ticker; note the daily rows for
   2026-11-05 to 11-13 now say `av_daily_backfill`, so they were rewritten too).
6. **Filter thresholds.** As live: the level parameters in force on the session and the prior ATR
   (recommended). Or the filter the stored row recorded (`_recorded_premarket_filter`, what the dry
   run uses; the experiment used it).
7. **LLM calls.** Real calls for the week (recommended; insight measured at $0.0122 to $0.0128 a
   report), decide for a year after the week's report. Or deterministic fields only.
8. **"Published".** The latest `scheduled` or `live` history row written before 09:30 ET, the owner's
   scoring pick (recommended). Not the canonical row, which can be a replay (2026-11-10).
9. **Quarter targets.** Compare plan targets by the columns both rows hold; once the marks build
   (rule v6, spec r3 in #2052) lands its `plan_t4` and marks ride along with no change here; its
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
  (`LIKE ... INCLUDING DEFAULTS`) plus run id, keyed by run then the live key.

### 2. The write fence

`gcp/replay_store.py` holds the run context (`REPLAY_RUN_ID`, validated) and the table map. While a
run id is set, every write function of `gcp/database.py` refuses a target outside schema `replay`
with `ReplayWriteRefused`, before an engine is created (D2). With no run id nothing changes. The
guard of #1891 registers the new module in `REPLAY_PATH` with one named exemption,
`REPLAY_FETCH_INTO_STORE`, and a new test that every write reached from it names `replay.*` (D9).

### 3. Pull

`python -m gcp.replay_full_pull pull --run-id R --tickers SPY,QQQ,IWM --from D1 --to D2`. Months: those
holding `[D1 - 7 days, D2]` (the flag pass reads 7 days past each month end,
`intraday_bar_flags.py:56`). One `fetch_month` call per ticker-month, unchanged, paced by
`AlphaVantageConfig.delay_between_calls`; stamps converted with `eastern_index_to_utc`; one
transaction per ticker-month into `replay.intraday_bars`; one `replay.pulls` row per call, whatever
its reason. Refusals and exit codes as D4. The key is read from the environment and redacted.

### 4. Data fixes

`python -m gcp.replay_full_pull fix --run-id R`. Per ticker-month: one read of the run's bars;
`judge_month` into the replay flag tables; per session `premarket_snapshot` at three cutoffs: the
morning refresh (the live run's recorded `fetched_at` when the live basis has one, else 08:20:00 ET,
the schedule `20 8 * * 1-5`, `gcp/deploy.sh:4894`), the late refresh at 09:20 ET once that slot is
deployed, and 09:30 ET (the nightly's window). Bars come from the as-read object when the session has
one (Decision 4), else from the run's pull. Prior inputs and thresholds per Decisions 5 and 6.

### 5. Brief

`BRIEF_AS_OF=D REPLAY_RUN_ID=R python -m gcp.premarket_brief`: the session premarket comes from
`replay.premarket` (refresh_0820, or refresh_0920 with `BRIEF_RUN_SLOT=late`) instead of the
`market_data_daily` row; daily bars, level parameters and calibration are read as today with the
as-of clock; rows go to the replay tables with run kind `replay` and `triggered_by 'replay:<R>'`;
the null-close cleanup does not run; Discord is never posted, whatever `BRIEF_POST_TO_DISCORD` says.

### 6. Insight

`INSIGHT_AS_OF=<D 08:45 ET> REPLAY_RUN_ID=R python -m gcp.insight_pipeline_job`: the level basis is
the run's own `replay.premarket_analysis` row, the premarket is `replay.premarket`; run, report and
history rows go to schema `replay`; no Discord push. Other inputs are read live with the as-of clock,
as `INSIGHT_AS_OF` does today (whether every reader honours it: not checked).

### 7. Comparison

`python -m gcp.replay_full_pull compare --run-id R` prints, and writes `rows.csv` and `summary.json`
under `replay/v1/<run_id>/compare/`:

- bars and flags, run against `market_data_intraday` and `intraday_bar_flags` (`compare_bars`);
- premarket high and low per read_kind beside the published read (`level_basis.premarket` of the
  published row), the stored `market_data_daily` values, and the filter-only extremes
  (`confirmed.raw_high` / `raw_low`), which split a rule change from a data revision;
- triggers, stops, t1 to t3 and every `plan_t` column both rows hold, names and prices, published
  (Decision 8) against the run's brief row; the insight plan fields of the live and replay reports;
- per item: equal, or differs with cause `rule_change`, `data_revision`, `both` or `level_pick`; a
  missing side is `not_published` or `not_replayed`. The summary says accurate only when every item
  is equal, and counts each cause.

### 8. Fixtures

`tests/fixtures/replay_2026_11_16/`: the experiment's fresh bars for 2026-11-16 (04:00 to 09:29 ET
for the three tickers; SPY 04:00 to 04:03 ET are 752.55/753.01/749.70/752.20 vol 14169,
752.30/752.90/749.70/752.13 vol 21038, 752.10/752.29/749.74/749.78 vol 7151,
749.73/752.78/749.73/752.07 vol 20902), the 2026-11-13 daily rows, and the recorded
`pre_filter_params`, with the read executions named in a `sources.json`.

## Capacity

- **Vendor calls.** One a ticker-month. The week 2026-11-09 to 11-16: 3 (the 7-day margin stays in
  November; first bar 2026-11-02 04:00 ET). A year: 36, plus 3 for a margin month. 2015-01 to
  2026-11: 143 months (143 SPY objects in the bucket copy) x 3 = 429. Measured 0.69 to 0.86 s a
  call; at the configured 150 a minute a year is under a minute and the whole history about 3
  minutes. The daily budget is not checked against the vendor's plan.
- **Volume.** A full month is about 19,200 to 21,130 bars a ticker (October coverage rows: SPY
  21,129, QQQ 21,120, IWM 19,199). A year of three tickers is about 740,000 rows; at the live SPY
  partition's 364 bytes a row with indexes (911,327,232 bytes over 2,503,499 rows, `db-query-w4l46`)
  about 270 MB a run. The week's November pull was 31,219 rows (10,767, 10,761, 9,691), about 11 MB.
  Premarket rows: 3 a session a ticker, about 2,270 a year.
- **Velocity.** Writes in chunks of 5,000 per ticker-month (about 5 statements, 180 a year); one bar
  read per ticker-month for the fixes; one brief run per session; one insight run per ticker-session.
- **Wall-clock.** Brief executions measured 28 to 110 s (2026-11-13 to 11-16). The week: 6 runs, 3 to
  11 minutes in sequence. A year: 252 runs, 2 to 8 hours in sequence, so striped by session over
  Cloud Run tasks (10 tasks: under an hour). Insight executions measured 32 to 72 s a ticker
  (2026-11-16), mean latency 32.6 to 43.2 s (`insight_reports` since 2026-10-17); the week 18 runs,
  a year 756 runs, 7 to 15 hours in sequence, striped (20 tasks: under an hour). Task timeout at 4x.
- **Cost.** Insight LLM: 18 x about $0.0125 = about $0.23 for the week, about $9.50 a year. Brief
  LLM explanations: not checked. Cloud SQL storage for 270 MB: price not checked. Max retries 0.

## Close-out (the owner's steps, after the merge and the FEAT-DEPLOY-001 wiring)

1. Apply the schema; create the replay role (Decision 2).
2. Run the week: pull, fix, brief for each session, insight for each ticker-session, compare.
3. Before and after, read-only: `SELECT count(*), max(inserted_at) FROM market_data_intraday WHERE
   ticker IN ('SPY','QQQ','IWM') AND ts >= '2026-11-02'`, the same on `premarket_analysis_history`
   (`written_at`) and `insight_reports_history`, and `SELECT count(*) FROM premarket_analysis WHERE
   run_kind = 'replay'` unchanged; `SELECT count(*) FROM replay.intraday_bars WHERE replay_run_id =
   '<R>'` equal to the sum of `replay.pulls.rows`.
4. Post the comparison report on the PR; decide the wider run.

## Risks

- A reader the switch misses reads live rows: D6 and D7 assert the named reads; a missed one shows
  as a `level_pick` difference in the report, not as a live write (the fence holds writes).
- A writer the fence misses: D2 covers every write function of `gcp/database.py`; a raw connection
  (`persist_level_map` takes one) is covered by D6's recording engine and by the role of Decision 2.
- Reading a revised pull as the morning: Decision 4 labels it and the report says it.
- The #1891 guard weakened: D9 keeps its lists and adds one named, tested exemption.

## What was not checked

- The vendor's daily call limit and price; Cloud SQL storage price; brief LLM cost.
- Whether every insight input honours `INSIGHT_AS_OF`.
- Whether an `INSIGHT_AS_OF` report's `as_of` can equal a live report's (the upsert key).
- What the current brief would pick on 2026-11-09 and 11-10, and the insight plan fields to compare
  (no brief or insight was run).
- How the late 09:20 slot (#2020) records its cutoff once deployed.
