---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-CAP-002, REQ-DATA-001, REQ-DATA-003, REQ-REPLAY-001]
issues: [1190]
canvases: []
site_source_notes: [ADMIN-06, CHARTS-01, DASHBOARD-01, INSIGHTS-01, JOURNAL-01, JOURNAL-02, LIVE-04, PLAYBOOK-05, SIGNALS-02]
done_when:
  - "tests/gcp/test_recompute_exits.py passes for selection and refusal: EODResolver.find_resolved_alerts(tickers, first, last) issues one strict query and returns exactly the signal_alerts rows with run_kind 'live', is_open false, a non-null exit_ts on a whole minute, a ticker in the list and alert_date in [first, last]; main() with --re-resolve and no --tickers covers SPY, QQQ and IWM; it exits 2 before any query for a ticker other than those three, for a missing --from or --to, for --from after --to, for --to on or after today's Eastern date, for --re-resolve together with --since, --backfill or --revert-run, and when either direction's exit mode is not target_stop; with --commit it exits 2 before any write when bar_recompute_ledger or a marker column is absent; without --re-resolve and --revert-run main() runs the scheduled path, and find_open_alerts and its SQL text are unchanged (on main none of these flags exists and no query selects a closed alert)"
  - "tests/gcp/test_recompute_exits.py passes for the bar read and the dry run, over a fixture of two tickers and two sessions written out in the test with its expected rows: each (ticker, date) is read once with one strict query whose text names interval = '1min' and selects inserted_at, bounded to that Eastern day; for a session stored as true UTC on 2026-10-06 the frame handed to resolve_one equals, index and values, the frame _load_day returns for the same rows; a window that holds one row not proven by lib.eastern_time.proven_true_utc gives every alert of that ticker and date the status unproven_rows and no new value; a window with no row gives no_bars; each alert is resolved by EODResolver.resolve_one and by no other code; the dry run enters no transaction and makes no HTTP request (engine.begin and requests.post are patched to fail the test), writes rows.csv and summary.json under bar-recompute/v1/signal-alert-exits/<run id>/ whose rows equal the expected table (ticker, session date, alert_ts, the four old exit values, the four new ones, changed, status, the bars' row count and sha256), and exits 0 when no alert was refused and 1 when one was; a query raising ConnectionError('connection refused') and one raising KeyError('close') each propagate out of main (on main no code path re-reads the bars of a closed alert)"
  - "tests/gcp/test_signal_monitor_eod_resolver.py passes with five new cases that patch EODResolver._load_day and stub no loader method: with bars from 09:30 to 19:59 Eastern on 2026-10-06, a CALL fired at 15:50 with a 30-minute stop resolves to eod_close at 20:00 UTC with the 15:59 bar's close (on main: time_stop at 20:20 UTC, run 2026-11-14); a target only the 19:59 print reaches resolves to eod_close with the 15:59 close (on main: target_hit at 23:59 UTC); with bars from 04:00 to 07:37 Eastern only, a PUT fired at 09:50 Eastern is not resolved and resolve_one returns None (on main: eod_close at the 07:37 close, run 2026-11-14); with bars that stop at 15:40 Eastern and no trigger, resolve_one returns None; on the half day 2026-11-27 the walk ends at 13:00 Eastern and eod_close is stamped 18:00 UTC; the existing cases pass unmodified except test_resolve_one_eod_close_fallback and test_resolve_one_eod_close_when_alert_after_last_bar, whose bars are moved into the last five minutes of the session with their assertions otherwise unchanged (a prototype of the bound failed exactly those two of the file's 30 cases, run 2026-11-14)"
  - "tests/integration/test_bar_recompute_writes.py passes in the integration-tests CI job on real Postgres for the exits: a committed --re-resolve overwrites exit_ts, exit_reason, exit_price, exit_return_pct and exit_recompute_run of each selected alert and exit_time, exit_price, exit_reason, return_pct and exit_recompute_run of its trades row, and every other column of both rows is equal before and after, is_open included; seeded rows with run_kind 'replay' and 'backfill', an open alert, and a closed alert whose exit_ts carries microseconds are equal before and after in every column; a trades row whose stored exit differs from its alert's stored exit is left equal in every column and reported trade_diverged while its alert is written; an alert whose exit is changed between the run's read and its write is left as the other writer left it and reported changed_underneath; each alert the run wrote has exactly one bar_recompute_ledger row holding its old values, its new values, changed and a basis with the bars' row count, sha256, first and last ts and insert-time range, the build's git commit and the exit configuration; the run's rows of one (ticker, date) commit in one transaction and a failure injected into the second group leaves the first group's alerts, trades and ledger rows committed; a second committed run over the same window writes no row and reports every alert already_current; --revert-run of the first run with --commit restores the four exit fields of each alert and trades row to the old values exactly, sets exit_recompute_run to the revert's run id, writes one ledger row per restored alert with action 'revert', and leaves untouched a row a later write changed (on main the resolver's trades update is guarded by exit_time IS NULL and cannot overwrite a recorded exit)"
  - "tests/gcp/test_recompute_premarket.py passes: premarket_snapshot(...) in gcp/fetchers/fetch_market_data.py is the one place that turns a session's premarket bars, the prior session's close, open and ATR, and the ticker's level parameters into the eleven premarket columns, and compute_and_upsert_daily_indicators calls it, with tests/gcp/test_premarket_filter_params.py, tests/gcp/test_premarket_filter_callers.py and tests/gcp/test_atr5_column.py passing unmodified; main() with --recompute-premarket makes no HTTP request and reads no ALPHA_VANTAGE_API_KEY (requests.get is patched to fail the test), selects only market_data_daily rows of SPY, QQQ and IWM in [--from, --to] that hold a non-null pre_high, pre_low, pre_vwap or gap_pct and a non-null close, and exits 2 before any query for any other ticker, a missing bound, --to on or after today's Eastern date, or --recompute-premarket together with --date or --backfill; for a session whose 04:00 to 09:30 Eastern bars are all proven it returns the eleven values premarket_snapshot gives for those bars, with None where the computation gives none; a window that holds one row not proven gives unproven_rows, a window with no row gives no_bars, and neither has a new value; the daily rows are read with one strict query per ticker and the bars with one strict query per ticker and month whose text names interval = '1min' and selects inserted_at; the dry run enters no transaction, writes rows.csv and summary.json under bar-recompute/v1/daily-premarket/<run id>/ that equal an expected table written out in the test (per ticker and date the old and the new value of each of the eleven columns, changed, status), and exits 0 when no row was refused and 1 when one was; ConnectionError and KeyError from a read propagate out of main (on main the premarket block is inline at fetch_market_data.py:446-542 and no entry point recomputes a past session from stored bars alone)"
  - "tests/integration/test_bar_recompute_writes.py passes on real Postgres for the premarket fields: a committed --recompute-premarket overwrites pre_high, pre_low, pre_vwap, pre_volume, gap_pct, pre_range_atr, pre_fetched_at, pre_excluded_stale_prints, pre_excluded_spikes, pre_filter_status, pre_filter_params and pre_recompute_run of each selected row, writes NULL where the new value is None, and leaves every other column of the row equal apart from updated_at; a row of another ticker, a row with no premarket value, and a row dated today are equal before and after in every column; a row whose premarket values are changed between the read and the write is reported changed_underneath and left; each written row has one bar_recompute_ledger row with old values, new values, changed and basis; a second committed run writes nothing and reports already_current; --revert-run with --commit restores the eleven columns exactly (on main no code writes a NULL over a stored premarket value: the nightly sets a column only when its new value is not None, fetch_market_data.py:518-524)"
  - "tests/gcp/test_intraday_replace_months.py passes with the two assertions at :876 and :879 changed and no other line of the file: BAR_DERIVED_RESULTS names, for signal_alerts exits, the command python -m gcp.signal_monitor_eod_resolver --re-resolve with --from and --to, and for the premarket fields the command python -m gcp.fetchers.fetch_market_data --recompute-premarket with --from and --to; neither entry holds 'NO PATH YET' or '#1190', and the line a committed replace logs after the RECOMPUTE lines no longer says a table has no path (on main both entries read 'NO PATH YET ... (#1190)', fetch_alphavantage_intraday.py:500-503 and :755-757)"
  - "make test passes on the PR head with tests/meta/test_production_writers.py, tests/meta/test_timezone_boundaries.py, tests/fixtures/timezone_boundary_baseline.json, tests/gcp/test_intraday_writers_utc.py and tests/gcp/test_premarket_playbook_resolver.py unmodified, and gcp/deploy.sh, gcp/signal_monitor.py, gcp/backfill_ticker.py, gcp/fetchers/fetch_premarket_refresh.py, lib/eastern_time.py, lib/data_loader.py, platform/api and CLAUDE.md not in the PR's diff; python scripts/export_openapi.py --check passes"
  - "The PR body gives, read-only through scripts/db_query_cr.sh with each execution id: EXPLAIN (ANALYZE, BUFFERS) of the exits' day read for QQQ 2026-05-01, of the premarket bars read for SPY over one month's sessions, and of find_resolved_alerts for the three tickers from 2026-05-01, each written with literals where the code binds parameters and each showing rows read on its scan node; the count of candidates per ticker for both tools on that day; and the count of candidate alerts with a NULL price_at_signal, target_price or direction. It also gives, measured locally against the integration Postgres, the seconds and the statement count of a committed --re-resolve over 900 synthetic alerts on 27 (ticker, date) groups and of a committed --recompute-premarket over 450 synthetic rows in 24 (ticker, month) groups, the first under 120 statements and the second under 240 (on main neither tool exists; measured for this spec on 2026-11-14: 835 candidate alerts on 27 groups, 447 candidate daily rows, the day read 2.7 ms for 1,200 rows, a four-session premarket read 19.7 ms for 1,316 rows with 329 rows a loop, db-query-zzvwq)"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the implementation-source notes of 03-SITE-TRACEABILITY.md hold a (FEAT-DATA-001, component) row for each of the nine declared components that begins with the current source hash (a row an earlier change left is extended: the new hash and this change's prose first, then 'Earlier:' and the earlier prose unchanged), docs/review-evidence/site-source-snapshot.json is regenerated and scripts/maintenance/doc_source_snapshot.py verify accepts it, the generated inventory blocks are re-rendered with scripts/maintenance/doc_inventory.py and tests/scripts/test_check_generated_docs.py passes, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: draft
supersedes: null
---

# Recompute paths for results computed from rewritten 1-minute bars: signal_alerts exits and the daily premarket fields

## Scope

- Issue #1190 asks for recompute tooling for the tables that were computed from the old `market_data_intraday` bars. Two of them have no path at all. This spec supplies those two:
  - **exits**: a bounded force mode of the end-of-day resolver that re-resolves closed alerts and overwrites the exit fields of `signal_alerts` and `trades`;
  - **premarket fields**: a bars-only recompute of `pre_high`, `pre_low`, `pre_vwap`, `gap_pct` and their sibling columns in `market_data_daily`.
- Each has a dry run, a committed run that needs `--commit`, a ledger of what it changed, and a revert.
- It is one spec, under FEAT-DATA-001, for SPY, QQQ and IWM only. No other ticker's row can be selected.
- It adds no job, no schedule and no deploy change. Both tools are modes of entry points that already run as jobs.
- A third need of #1190, a window-bounded force for `historical_signals`, is judged not needed for this cleanup and is not designed here (decision 3). What that leaves is named in "Historical signals".
- Code references are to `main` 20d9c47b (2026-11-14). Every production number has its `db-query` execution id beside it and was read without `--commit` on 2026-11-14.

## Capability

The catalog rows this work was checked against (`docs/product/02-FEATURE-CATALOG.md`):

> | [FEAT-DATA-001](#feat-data-001) | Data platform | Ingestion, storage, freshness | — | fetcher jobs | 64 relations — see [06](06-DATA-ARCHITECTURE.md) | Production but needs remediation | P0 | 1 | 21 | …

> | [FEAT-SIGNAL-001](#feat-signal-001) | Signals / execution | Signal discovery, alerting, exits | `/signals`, `/live` | `/api/signals` | `signal_alerts`, `historical_signals`, `exit_config_overrides` | Production but needs remediation | P0 | 1 | 25 | …

- The capability served is FEAT-DATA-001: the tools exist because the stored bars were rewritten, they are steps of FEAT-DATA-001's runbook, and #1190 is already an issue of the approved FEAT-DATA-001 bucket-copy spec.
- The gate binds a path to a capability only for process files and deploy files (`scripts/gate/spec_gate.py:1116-1128`, `:4836-4841`). `gcp/signal_monitor_eod_resolver.py` and `gcp/fetchers/fetch_market_data.py` are neither, so one FEAT-DATA-001 branch may change both. The approved strict-bar-loader spec (FEAT-DATA-001) already changes the resolver the same way.
- The catalog lists the resolver under FEAT-REPLAY-001's Code and `signal_alerts` under FEAT-SIGNAL-001's Data. One part of this spec changes what the scheduled resolver writes from now on (Design 4). Decisions 2 and 4 put that to the owner.
- Requirements: REQ-CAP-001 and REQ-CAP-002 (capacity, batching, idempotence), REQ-DATA-001 (no silent fallback), REQ-DATA-003 (a derived record carries its source and version), REQ-REPLAY-001 (a recompute runs the production path).
- No canvas is listed: the change adds no job and no route.

## Decisions for the owner

Each is written into the text below as recommended. Striking one changes only the sections named.

1. **Which closed alerts are re-resolved.** Recommended: only the 835 whose stored exit was computed from stored bars by the resolver. The other 2,311 exits were observed by the live monitor from its own quote at the time; the bar rewrite did not change what it saw, and replaying them from bars would replace an observation with a reconstruction. Alternative: all 3,146. (Problem 3, Design 3.)
2. **The resolver's walk ends at the session close, in this change, for the scheduled path too.** Recommended. Today it walks after-hours bars and prices `eod_close` from the day's last stored bar. Recomputing 835 exits on that rule would write the same two errors again, and fixing it later would mean a second recompute of the same rows. Alternatives: recompute on the rule as it is; or fix it first in its own FEAT-SIGNAL-001 spec. (Problem 4, Design 4.)
3. **No window-bounded force for `historical_signals`.** Recommended. The whole history was rewritten, so a full regeneration per ticker is the right scope and the runbook already plans it. Two hazards of that command are reported here and are not fixed here. If the owner wants them fixed before the regeneration, that is a second spec under FEAT-SIGNAL-001. (Historical signals.)
4. **One spec under FEAT-DATA-001 for both tables.** Recommended, on the precedent above. Alternative: the exits half under FEAT-SIGNAL-001, which makes two specs, two plans and two PRs before the runbook's gate lifts.
5. **A ledger table and one marker column on each of the three tables.** Recommended: `bar_recompute_ledger`, `signal_alerts.exit_recompute_run`, `trades.exit_recompute_run`, `market_data_daily.pre_recompute_run`. Alternative: the ledger alone, and a reader joins to it. (Design 2.)
6. **Undo is the ledger, through `--revert-run`.** Recommended. Point-in-time recovery is the backstop for the seven days it covers, never the plan. (Design 2, Close-out.)
7. **The tools refuse any window that holds a bar not proven true UTC.** Recommended. So before the runbook's replace they can run only on sessions from 2026-09-28 on, and the full recompute can only happen after the misplaced rows are gone. No override flag. (Design 2.)
8. **The premarket print filter uses the parameters in force on each session's own date.** Recommended, as the nightly does. The parameters start on 2026-11-12, so earlier sessions are rewritten unfiltered and say so in `pre_filter_status`. Alternative: apply today's thresholds to history, which uses values calibrated after those sessions. (Design 5.)
9. **Only rows that already hold a premarket value are recomputed** (447). Sessions before 2026-04-14 hold none and are not filled. (Design 5.)
10. **Stored results that were computed from the old outcomes are recorded, not restated.** Recommended: `indicator_correlation` rows, stored insight reports, posted weekend reviews and dated audits keep what they said; the run's summary gives the before and after. (Consumers.)
11. **The runbook's step 5 gate lifts after a committed rehearsal on the proven sessions**, not at the merge. (Close-out, steps 3 to 5.)
12. **A five-minute rule for `eod_close`.** It is written only when the session's stored bars reach the last five minutes before the close; otherwise the alert stays unresolved and the run says so. (Design 4.)

## Problem

### 1. Two result tables cannot be recomputed, and the bar cleanup waits on that

- `market_data_intraday` for SPY, QQQ and IWM was rewritten with as-traded bars by a plain upsert on 2026-11-14 (reported to this spec; not re-verified here). Every table computed from the old bars now disagrees with the bars it would be computed from today.
- 82,481 misplaced rows are still stored: Eastern clock times labelled as UTC, at a UTC clock time from 04:00 up to 04:00 Eastern, on 121 dates from 2026-04-06 to 2026-09-25 (IWM 24,517, QQQ 29,030, SPY 28,934; db-query-5lbd6). Removing them needs `fetch_alphavantage_intraday --replace-months --commit`.
- CLAUDE.md 3.9 and #1190 hold that committed run until the result tables have recompute paths. The approved runbook repeats the hold: step 5 "does not start before #1190 allows it", and step 7 lists "Premarket fields of `market_data_daily` and `signal_alerts` exits: no path today (#1190)" (`docs/superpowers/specs/2026-11-13-feat-data-001-intraday-bucket-copy.md`, Close-out).
- The upsert rewrote rows in place, and an upsert keeps a row's `inserted_at`. SPY 2026-05-01 holds 1,200 rows in its Eastern day, none inserted on or after 2026-09-28 (first insert 2026-05-01, last 2026-05-09; db-query-kn5x4). So no row of a session before 2026-09-28 is proven true UTC yet (`lib.eastern_time.proven_true_utc`, `lib/eastern_time.py:379-397`). The replace deletes and inserts, which makes them proven.

### 2. #1190's statements, checked against `main` today

| #1190 says | On `main` 20d9c47b | Evidence |
|---|---|---|
| `premarket_analysis` outcomes have a safe recompute: `PLAYBOOK_RESOLVE_DATE`, `PLAYBOOK_RESOLVE_TICKERS`, `PLAYBOOK_RESOLVE_FORCE=true` | holds | `gcp/premarket_playbook_resolver.py:34-53`, `:440-443`, `:707-709`, `:719`. It reads the regular session at the stored instant (`:474-476`). |
| `historical_signals`: only a full regeneration; `--force` deletes every row of the ticker and strategy | holds, with two hazards #1190 does not name | `gcp/historical_signals.py:127-131`, `scripts/run_historical_signals.py:453-460`. See "Historical signals". |
| `signal_alerts` exits: no path; `find_open_alerts` selects only open rows and `--backfill` uses the same query | holds | `gcp/signal_monitor_eod_resolver.py:140-153`, `:604-613`. Also: the trades mirror is guarded by `exit_time IS NULL` (`:416-425`), so even a re-selected alert could not overwrite its trade. |
| `market_data_daily` premarket fields: no path; `backfill_daily_indicators` never reads intraday bars | holds for a bars-only path | `gcp/fetchers/backfill_daily_indicators.py` names neither the bars table nor a premarket column (searched). |
| the premarket fields "are only computed inside `fetch_market_data` right after its nightly fetch" | changed | Four call sites compute them today, and none is bars-only for given dates. The nightly (`gcp/fetchers/fetch_market_data.py:446-542`); the 08:20 refresh, from a live vendor fetch over the window so far (`gcp/fetchers/fetch_premarket_refresh.py:185-270`); `gcp/backfill_ticker.py:505-560`, after its own vendor refetch of daily and intraday bars; and `scripts/backfill_watchlist_data.py:251`, through the nightly's function. Each also rewrites the indicator and strat columns of the row or fetches from the vendor. |
| needed: the premarket recompute uses `eastern_bounds_utc` over 04:00 to 09:30 ET | already how the nightly reads | `fetch_market_data.py:457-458`. The nightly also filters prints with per-ticker thresholds now (`:500-515`, FEAT-STRAT-001) and records provenance columns (`:525-540`). |

### 3. Which stored exits came from stored bars: 835 of 3,146

Read from production (db-query-97p69, db-query-kxg7x, db-query-5lbd6):

- `signal_alerts` holds 3,146 live rows, all closed: IWM 934, QQQ 1,039, SPY 1,173, alert dates 2026-05-01 to 2026-11-13. It also holds 432 `backfill` and 23 `replay` rows. No other ticker has a live row.
- Each of the 3,146 joins one live `trades` row on `(ticker, entry_time = alert_ts)`, and all 3,146 trades hold the same exit time, price and reason as their alert. None differs and none is open.
- An exit is written by one of two paths, and no column says which:
  - the live monitor's exit watcher, from the live quote, stamped `datetime.now()` (`gcp/signal_monitor.py:2129`, `:2166-2167`, `:2437-2510`);
  - the end-of-day resolver, from stored bars, stamped with a bar's minute or with 16:00 ET (`gcp/signal_monitor_eod_resolver.py:319-335`, `:357-376`).
- The stamp tells them apart. 835 exits sit on a whole minute; 2,311 carry seconds and microseconds. No `alert_ts` sits on a whole minute (0 of 3,146), no exit sits on a whole second that is not a whole minute, and no exit that carries seconds is after 16:00 ET.

| | Alerts | (ticker, date) groups | Dates |
|---|---|---|---|
| whole-minute exits, all | 835 (IWM 270, QQQ 281, SPY 284) | 27 | 15, from 2026-05-01 to 2026-10-26 |
| of them on 2026-05-01, 05-04, 05-05, 05-06, 05-07, 05-08 | 820 (355, 79, 155, 162, 26, 43) | 18 | 6 |
| of them on sessions from 2026-09-28 on | 10 (09-30: 4, 10-01: 2, 10-05: 2, 10-26: 2) | 4 | 4 |
| by reason | time_stop 731, target_hit 87, rsi_extreme 10, eod_close 7 | | |

- The 820 of May were resolved by the one-shot backfill of that month, when the loader handed out the stored clock unconverted (the comment at `gcp/signal_monitor_eod_resolver.py:185-188`) and the table held both conventions. Which bar each alert was walked against cannot be recovered.
- The live monitor's 2,311 exits did not come from stored bars. The rewrite changed nothing they rest on.

### 4. The resolver does not stop at the session close

Found while checking what a recompute would write. Each was run on 2026-11-14 through the real `EODResolver.resolve_one` of `main` with the loader stubbed, and each shows in production.

- **It walks after-hours bars.** `_load_day` loads the whole Eastern day (`:175-180`) and the walk takes every bar at or after the alert (`:311`, `:319`).
  - Run: bars 09:30 to 19:59 ET, a CALL fired at 15:50 ET with a 30-minute stop: `time_stop` at 16:20 ET. A target that only the 19:59 ET print reaches: `target_hit` at 19:59 ET.
  - Production: 75 of the 835 exits are stamped after 16:00 ET (db-query-kxg7x), for example QQQ 2026-10-26, fired 15:59:38 ET, `time_stop` at 16:20 ET (db-query-lrq4n).
- **`eod_close` is priced from the day's last stored bar** (`:357-358`), and stamped 16:00 ET whatever that bar is.
  - Run: with after-hours bars 20 cents above the session, `eod_close` took 100.21, the 19:59 ET close, where the 15:59 ET close was 100.01.
  - Run: with only premarket bars stored, 04:00 to 07:37 ET, a PUT fired at 09:50 ET resolved to `eod_close` at the 07:37 ET close. With the inputs of the production row SPY 2026-09-30 13:50:09 UTC the run returned exit price 764.2 and return +0.3871, which is that row exactly (db-query-p22fg).
  - Production: each of the 7 `eod_close` exits holds a price that a premarket bar of its own day closed at (the 07:37 ET bar for the four SPY rows), and none holds the 15:59 ET close: IWM 2026-07-23 293.79 against 292.10, SPY 2026-09-30 764.20 against 762.46, IWM 2026-10-01 277.89 against 279.05 (db-query-qmtn6, db-query-lrq4n). The four SPY rows are recorded as wins at a price from before they fired.
  - The 16:30 ET run expects the day's bars to be absent (the comment at `:527-538`). On those days they were present and held premarket only. Which writer stores them before 16:30 ET was not traced.

### 5. The premarket fields

Read from production (db-query-msw2z, db-query-pqprn, db-query-qmtn6):

- Each of SPY, QQQ and IWM holds 2,651 daily rows, of which 149 hold premarket fields, from 2026-04-14 to 2026-11-13: 447 rows. Every one of them has a close.
- 147 of each ticker's 149 have no `pre_filter_status` (they predate the filter) and 2 are `ok` (2026-11-12 and 11-13). `pre_fetched_at` is set on 4 of each. `pre_range_atr` is set on 4 of each.
- The level parameters start on 2026-11-12 for all three tickers (`ticker_level_params`, `pm_stale_print_atr` and `pm_spike_atr`); the policy is in force from 2015-01-02.
- 35 of each ticker's 149 sessions are on or after 2026-09-28 (3 in September, 22 in October, 10 in November): 105 rows whose bars are proven today, 342 that wait for the replace.
- 22,505 rows of 2,239 other tickers hold premarket fields. None is touched: their bars were not rewritten.
- The nightly writes the full 04:00 to 09:30 ET window for its own date and overwrites what the 08:20 refresh wrote from a partial window. So a stored historical value is already a full-window value, and a recompute over the same window keeps its meaning.

## Non-goals

- No production write from the implementation PR, and no deploy other than the staging deploy of the API that a merge to `main` starts. Every production step is in Close-out and waits for the owner's own yes.
- No ticker other than SPY, QQQ and IWM. The tools refuse any other before a query.
- No new exit for an open alert through the force mode, and no change to `find_open_alerts`. Open alerts stay with the scheduled path.
- No change to the live monitor (`gcp/signal_monitor.py`), to its exit watcher, or to any exit it wrote.
- No Discord message. The force mode posts no digest and no exit alert; nothing already posted is posted again.
- No change to `journal_entries`, which is the user's own trade log, or to any `trades` row whose stored exit is not its alert's.
- No change to `historical_signals`, `signal_metrics`, `premarket_analysis`, `indicator_correlation`, `insight_reports`, or any `strat_*` table. The runbook's step 7 has their paths.
- No backfill of premarket fields into sessions that hold none, and no change to the nightly's or the 08:20 refresh's own writes. The nightly keeps writing what it writes; only where its block lives changes (Design 5).
- No change to `gcp/backfill_ticker.py`. It keeps its own copy of the premarket block (`:505-560`); that copy is reported, not merged here.
- No general reader migration. `lib/data_loader.py` and `lib/eastern_time.py` are not edited; CLAUDE.md 3.9's Readers step stays held.
- No change to `gcp/deploy.sh`, to a schedule, or to a job's memory, timeout or retries. Those belong to FEAT-DEPLOY-001.
- No edit of `CLAUDE.md` or of the approved bucket-copy spec. Bringing 3.9's text up to date is a FEAT-CICD-001 change (Close-out, step 6).
- No route and no response shape changes. `platform/api` is not in the diff.

## Approaches considered

For the exits:

1. A bounded force mode inside the resolver that runs each alert through `resolve_one` (chosen). The exit rule stays in one function, shared by the scheduled path and the recompute.
2. Set `is_open` back to true on the alerts and let the scheduled path resolve them: it would post a digest for hundreds of old exits, could not touch the trades mirror, leaves no record of the old values, and shows 835 trades as open in between.
3. A script that walks bars itself: a throwaway harness, which CLAUDE.md 3.6 forbids for exactly the reason that it drifts from the production rule.
4. Replay through `scripts/replay_signal_monitor.py`: it decides fires, with `run_kind = 'replay'`. It does not re-resolve the exit of a live alert.

For the premarket fields:

1. Extract the nightly's premarket block into one function and call it from a bars-only mode of the same module (chosen).
2. Call `compute_and_upsert_daily_indicators` per date: it also rewrites every indicator and strat column of the row, and it keeps an old premarket value wherever the new one is None.
3. `fetch_market_data --date D --allow-stale-date`: it refetches from the vendor and writes bars and the daily row.
4. `backfill_ticker`: it refetches daily and intraday bars first.

For what a run leaves behind:

1. A ledger table written in the same transaction as each overwrite, plus a report in the bucket (chosen). The old values are in the database before the transaction that replaces them commits.
2. The bucket report alone: an undo would be hand-written SQL from a CSV.
3. Point-in-time recovery alone: seven days, a whole-instance clone, and no record of which rows changed.

## Design

### 1. What each recompute writes and what it never touches

| | Exits | Premarket fields |
|---|---|---|
| Rows selected | `signal_alerts` with `run_kind = 'live'`, `is_open` false, `exit_ts` not null and on a whole minute, ticker in the run's list, `alert_date` in the window | `market_data_daily` rows of the run's tickers in the window, before today's Eastern date, with a close and at least one of `pre_high`, `pre_low`, `pre_vwap`, `gap_pct` not null |
| Columns overwritten | `signal_alerts`: `exit_ts`, `exit_reason`, `exit_price`, `exit_return_pct`, `exit_recompute_run`. `trades`: `exit_time`, `exit_price`, `exit_reason`, `return_pct`, `exit_recompute_run` | `pre_high`, `pre_low`, `pre_vwap`, `pre_volume`, `gap_pct`, `pre_range_atr`, `pre_fetched_at`, `pre_excluded_stale_prints`, `pre_excluded_spikes`, `pre_filter_status`, `pre_filter_params`, `pre_recompute_run` |
| Inputs, never written | `alert_ts`, `alert_date`, `direction`, `price_at_signal`, `target_price`, `time_stop_minutes` | the daily bars, the level parameter tables |
| Never written | `is_open`; every scoring, level, gate, catalyst and brief column; `inserted_at`; any row that is not selected | open, high, low, close, volume, `adjusted_close`; every indicator and strat column; `data_source`; any row that is not selected |
| Rows never selected | open alerts; `replay` and `backfill` rows; exits the live monitor wrote; other tickers | other tickers; rows with no premarket value; today's row; a row with no close |
| Other tables | `journal_entries` is not read or written | none |

- The trades row is the one with the alert's `ticker`, `entry_time = alert_ts` and `run_kind = 'live'`. It is written only while its stored exit equals the alert's old exit. If it does not, someone changed it: it is left and reported `trade_diverged`, and the alert is still written. An alert with no trades row is written and reported `trade_missing`.
- The whole-minute rule is the selector going forward too: every exit the resolver writes is a bar's minute or the session close, and the live monitor stamps microseconds. No provenance column is added to the live path.
- A premarket column is written as NULL when the computation gives no value. A value from the old bars never stays beside new ones.

### 2. What the two tools share (`gcp/bar_recompute.py`, new)

One small module, imported by both entry points. It is new because neither entry point is the home of a contract the other must follow, and two copies of a ledger writer would drift.

**Run identity.** `run_id` is `CLOUD_RUN_EXECUTION` in a job (Cloud Run sets it; `gcp/db_query_job.py:78-79` reads it the same way), else `local-<UTC timestamp>`. The code version is read from `gcp/build_info.json`, which every image carries (`gcp/deploy.sh:97-98`: git commit, dirty flag, build time); a run outside an image records nulls.

**Proof before placement.** Every bar read selects `inserted_at`, and `require_proven(ts, inserted_at)` refuses the window unless every row is proven by `lib.eastern_time.proven_true_utc`. A proven row is read at its stored instant. Nothing is inferred and `stored_intraday_to_eastern` is not called.

- This is the answer to CLAUDE.md 3.9 for these tools: they read the table only where its rows are known instants. It holds in both orders the runbook could be run in:
  - after the replace, every row of the three tickers is proven (the runbook's step 6 requires `unproven_rows=0` on every month), so nothing is refused;
  - before it, every session before 2026-09-28 is refused, because the 2026-11-14 upsert left the old insert times. The tools cannot produce a value from a table that still holds a misplaced row in the window they read.
- A stale label that the upsert could not overwrite (a minute the vendor has no bar for) is not proven either, so it is caught the same way. The 82,481 known misplaced rows sit outside both tools' windows on their own (before 04:00 ET); the refusal does not rely on that.
- There is no override flag.

**The dry run.** Without `--commit` a run computes every selected row, writes its report, and writes nothing to the database.

- Where: `gs://<GCS_BUCKET>/bar-recompute/v1/<target>/<run_id>/rows.csv` and `summary.json`, with `target` `signal-alert-exits` or `daily-premarket`. `GCS_BUCKET` is set on every job (`gcp/deploy.sh:1127`). The prefix has no lifecycle rule (the bucket's two rules cover `sql-dumps/` and `raw/`, `gcp/deploy.sh:3337-3358`). A run with no `GCS_BUCKET` needs `--report-dir PATH` and writes the same two files there; with neither it exits 2.
- `rows.csv`, one line per selected row: ticker, session date, the row's key, each old value, each new value, `changed`, `status`, the bars' row count and sha256, and `written` (always false in a dry run).
- `summary.json`: the arguments, the run id, the code version, the configuration read, and per ticker and date the counts by status. For exits it also gives, per ticker and over all, the wins and the mean return before and after, where a win is `exit_return_pct > 0`, the label `gcp/indicator_correlation_job.py:463` and `gcp/signal_quality_alarm.py:208` use.
- `changed` is exact: any overwritten value column differs, NULL-safe, with no tolerance. The report carries the values, so the size of a change can be read from it.
- The log has one line per group, for example `RECOMPUTE-EXITS SPY 2026-05-01 candidates=120 changed=37 unchanged=83 refused=0`.
- An upload that fails raises. Nothing is written to the database after a failed report.

**The committed run.** With `--commit`:

1. It computes everything and saves the report first, as the dry run does.
2. It then writes one group at a time, each in one transaction: a (ticker, date) for exits, a (ticker, month) for premarket fields.
3. Each write is a compare-and-set in one statement: `UPDATE … FROM (VALUES …) … WHERE` the key matches and the stored values still equal the old values the run read, `RETURNING` the keys it changed. A row that another writer changed in between is not returned; it is left and reported `changed_underneath`.
4. The same transaction inserts one ledger row per returned key and sets the marker column to the run id.
5. After the last group it saves the report again with `written` filled in.

- A row is written when its new values differ from the stored ones, or when they are equal and its marker is NULL (the run confirmed it against the new bars; the ledger row has `changed` false). A row whose marker is set and whose values are equal is `already_current` and is not written. So a second run over the same window writes nothing, and a Cloud Run retry of a failed execution converges.
- A failure in one group leaves the earlier groups committed, each with its ledger rows, and ends the run non-zero.

**The ledger.** In `gcp/schema.sql`, applied by the owner (Close-out, step 1):

```sql
CREATE TABLE IF NOT EXISTS bar_recompute_ledger (
    id           BIGSERIAL   PRIMARY KEY,
    run_id       TEXT        NOT NULL,
    target       VARCHAR(32) NOT NULL,  -- 'signal-alert-exits' | 'daily-premarket'
    action       VARCHAR(8)  NOT NULL,  -- 'recompute' | 'revert'
    ticker       VARCHAR(10) NOT NULL,
    session_date DATE        NOT NULL,
    row_key      TEXT        NOT NULL,  -- alert_ts in UTC to the microsecond | the date
    old_values   JSONB       NOT NULL,
    new_values   JSONB       NOT NULL,
    changed      BOOLEAN     NOT NULL,
    basis        JSONB       NOT NULL,
    written_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, target, ticker, row_key)
);
ALTER TABLE signal_alerts     ADD COLUMN IF NOT EXISTS exit_recompute_run TEXT;
ALTER TABLE trades            ADD COLUMN IF NOT EXISTS exit_recompute_run TEXT;
ALTER TABLE market_data_daily ADD COLUMN IF NOT EXISTS pre_recompute_run  TEXT;
```

- **How a row says it was recomputed**: its marker column holds the run id of the committed run that last wrote it. NULL means the value is as first written.
- **From which bar basis**: the ledger row's `basis` holds the bars read (row count, first and last `ts`, the earliest and latest `inserted_at`, and a sha256 over the rows' `ts`, open, high, low, close and volume), the code version, and the configuration that decided the value: for exits the exit mode of each direction, the RSI period and the two RSI thresholds; for premarket fields the filter status and parameters and the prior session's close, open and ATR.
- **Old against new**: `old_values` and `new_values` hold every overwritten column; for exits, the alert's and the trade's. One query on the ledger lists every outcome that moved, by run.
- For exits, `old_values` and `new_values` each hold a `signal_alerts` object and a `trades` object, or null for the trade when it was missing or left.
- Numbers are stored as the shortest text that reads back to the same float, and times as UTC text to the microsecond, so a revert restores a value exactly.

**The revert.** `--revert-run RUN_ID`, a dry run unless `--commit`, on the same entry point as the target.

- It reads the ledger rows of that run and target and writes each row's `old_values` back with the same compare-and-set, against that run's `new_values`. A row a later run or another writer changed is left and reported.
- It writes its own ledger rows with action `revert`, and sets the marker to its own run id. The history stays in the ledger; nothing is deleted.
- This is the undo plan. Point-in-time recovery covers the instance for seven days (CLAUDE.md, Backup and disaster recovery) and is the fallback only for a failure the ledger cannot describe; it would be read from a clone, never restored over the live instance. The bucket report is a third, independent copy of the old values.

**Exit codes.** 0: the run finished and refused no row. 1: it finished and at least one row was refused or left (`unproven_rows`, `no_bars`, `bars_incomplete`, `daily_incomplete`, `changed_underneath`, `trade_diverged`), or it failed. 2: refused before any query or write, with the reason on one line.

### 3. Exits: `--re-resolve` on the end-of-day resolver

```
python -m gcp.signal_monitor_eod_resolver --re-resolve --from 2026-05-01 --to 2026-11-13 [--tickers "SPY QQQ"] [--commit]
python -m gcp.signal_monitor_eod_resolver --revert-run <run id> [--commit]
```

- With neither flag `main()` runs the scheduled path. `--tickers` defaults to SPY, QQQ and IWM, which is also the whole set allowed. It is one value, space-separated, the form the fetcher's flag already has (`gcp/fetchers/fetch_market_data.py:1145-1146`), so a job's comma-separated `--args` list needs no escaping.
- **Selection**: `find_resolved_alerts(tickers, first, last)`, one strict query (Design 1's row rule), ordered by date, ticker and alert time. It reads through `gcp.database.query_to_dataframe_strict`, so an outage raises and is never "nothing to do". `find_open_alerts` is not changed.
- **Refused before any query**: a ticker outside the three; a missing bound; a window that reaches today's Eastern date (today's alerts belong to the scheduled path); and a configuration in which either direction's exit mode is not `target_stop`.
  - Why the last: every stored exit reason is `target_hit`, `time_stop`, `rsi_extreme` or `eod_close` (db-query-kxg7x), which only that mode produces. Re-resolving them under `fixed_horizon` would change outcomes for a reason that is not the bars. Each alert's own target and time stop are stored on its row and are used as stored. The RSI period and thresholds come from the configuration, and the ledger records them.
- **Bars**: one strict read per (ticker, date) over the Eastern day `[D 00:00, D+1 00:00)` as UTC instants, the window `_load_day` loads:
  `SELECT ts, open, high, low, close, volume, inserted_at FROM market_data_intraday WHERE ticker = :t AND interval = '1min' AND ts >= :start AND ts < :end ORDER BY ts`.
  - `require_proven` runs on the result. The frame is then shaped as `_load_day` shapes it: a naive UTC index and the RSI computed once over the day's bars (`:189-198`).
  - For a session whose rows the scheduled read places as true UTC, the two frames are equal; `done_when` asserts it. The force mode does not go through `DataLoader`, so it does not depend on the loader's resolver or on its Parquet fallback.
- **The rule**: each alert goes through `EODResolver.resolve_one`, the function the scheduled path runs, with its `_detect_exit` and `_eod_close_resolution`. The force mode holds no exit logic of its own.
- **A NULL input** (`price_at_signal`, `target_price`, `direction`) raises, naming the ticker and the alert. The count of such candidates is a `done_when` measurement; it was not read for this spec.
- **Persist**: Design 2's committed run, a (ticker, date) at a time. The existing `persist` is not changed and stays the scheduled path's writer.
- **Discord**: `_post_digest` is not called on this path.

### 4. The walk ends at the session close (decision 2)

A change to `resolve_one`, so it applies to the scheduled path and to the recompute alike.

- The session's close is `lib.eastern_time.session_close(alert_date)`: 16:00 ET, or 13:00 ET on a half day.
- The walk takes the bars at or after the alert and before the close. `_load_day` still loads the whole day, and the RSI is still computed over all of it, so an RSI value on a session bar is what it is today.
- `eod_close` takes the close of the last bar before the session close, and is stamped with the session close.
- `eod_close` is written only when the day's stored bars reach the last five minutes before the close. Otherwise `resolve_one` returns None, which is what it returns today for a day with no bars:
  - in the scheduled path the existing accounting applies (`:546-552`): a same-day miss before 21:00 ET is benign and is retried by the next run, any other is counted stale and the run exits 1;
  - in the force mode the alert gets `bars_incomplete` and its row is left.
- A trigger found on a bar that is stored is still an exit, on a complete day or not: the bar is real.
- From a prototype applied to `main` on 2026-11-14, run and reverted:
  - the 15:50 ET CALL of Problem 4 resolves to `eod_close` at 16:00 ET with the 15:59 ET close; so does the alert whose target only the 19:59 ET print reaches;
  - with after-hours bars 20 cents higher, `eod_close` takes 100.01, the 15:59 ET close;
  - with premarket bars only, the 09:50 ET PUT is not resolved;
  - of the 30 cases of `tests/gcp/test_signal_monitor_eod_resolver.py`, 28 pass unchanged. The two that fail build their "end of day" from bars at 11:30 to 11:58 ET, and move to the last five minutes of the session.
- What the owner sees from the scheduled job after this: an alert fired in the last minutes of a session resolves to `eod_close` where it would have been a `time_stop` after the close, and a same-day run that finds only premarket bars leaves the alert open for the next run instead of closing it at a premarket price.
- A session the vendor serves thin near the close leaves its open alerts unresolved, and the job exits 1 for it each day until someone closes them. No such session is known since alerts began (the thin sessions the runbook lists are 2021 to 2025).

### 5. Premarket fields: `--recompute-premarket` on the daily fetcher

```
python -m gcp.fetchers.fetch_market_data --recompute-premarket --from 2026-04-14 --to 2026-11-13 [--tickers "SPY QQQ"] [--commit]
python -m gcp.fetchers.fetch_market_data --revert-run <run id> [--commit]
```

- `main()` branches on the two flags before anything else it does, as it already does for `--backfill` (`fetch_market_data.py:1195-1196`). The mode makes no vendor request and needs no API key. `--tickers` keeps the flag's space-separated form; its default `ALL` means SPY, QQQ and IWM here.
- **One function for the computation.** The block at `:446-542` becomes `premarket_snapshot(ticker, session_date, bars, prior, level_params, read_at)`, in the same file.
  - It takes the session's premarket bars, the prior session's close, open and ATR columns, and the ticker's level parameters. It returns the eleven column values, with None where there is none, or nothing when the window holds no premarket bar.
  - `compute_and_upsert_daily_indicators` calls it and keeps its own write rule: a price column is set only when the new value is not None (`:518-524`). The nightly's row is what it is today, and its tests pass unmodified.
  - The recompute calls the same function, so it runs the print filter, the VWAP rule and the provenance rule of today's nightly.
- **Selection**: Design 1's row rule, one strict query.
- **Daily bars**: one strict query per ticker for the dates from 400 calendar days before the window's first date to its last. For each session the frame is the last 250 rows up to that date, which is the nightly's query (`:356-366`) sliced in memory, and `add_all_indicators` runs on it as the nightly runs it. The prior session's close, open, ATR14 and ATR5 are that frame's second-to-last row, as at `:481-498`.
  - A selected row with no close is `daily_incomplete` and is left. None exists today (Problem 5).
- **Bars**: one strict query per ticker and month, one window per selected session, `[04:00, 09:30)` Eastern as UTC instants from `eastern_bounds_utc`, selecting `ts`, open, high, low, close, volume and `inserted_at`, with `interval = '1min'` in the text. The plan of that form reads only the rows it returns (Capacity).
  - `require_proven` runs per session. This reader takes the stored instant and requires proof, which is the form the bucket-copy spec's Design H asks of it.
- **Level parameters**: `load_level_params(query_to_dataframe_strict, tickers, session_date)`, once per session date, as the nightly reads them for its own date (`:326-332`, `:1261-1270`).
  - A session before the ticker's first parameter row gets status `params_unavailable`, and the filter does not run. Run on 2026-11-14 through the real `load_level_params` and `premarket_filter_inputs`, with a policy from 2015-01-02 and no ticker row on or before the session.
  - So 147 of each ticker's 149 rows are rewritten unfiltered: their `pre_filter_status` goes from NULL to `params_unavailable`, their excluded counts stay NULL, and their `pre_range_atr` is NULL, because the ATR reaches the computation only with an `ok` status (`:505-515`).
  - The level builder already refuses a snapshot whose status is not `ok`, a row with no status included (`lib/strat_levels.py:1925-1942`). So no replay that was refused becomes accepted, and none that was accepted is refused, by this.
  - A failed parameter read raises. The recompute never writes `level_params_unavailable` over a stored row.
- **`pre_fetched_at`** is set to the time the run read the bars, which is its meaning in the nightly (`:472`, `:528`).
- **Write**: Design 2's committed run, a (ticker, month) at a time, over the twelve columns of Design 1.

### 6. The replace's RECOMPUTE lines

`BAR_DERIVED_RESULTS` in `gcp/fetchers/fetch_alphavantage_intraday.py:491-504` names, for each result table, its recompute path. The two `NO PATH YET` entries become the two commands above, and the line a committed replace logs afterwards (`:755-757`) no longer says a table has no path. The two assertions that pin the old text change with it (`tests/gcp/test_intraday_replace_months.py:876`, `:879`).

### 7. What bad input gets

`lib.infra_errors.is_infrastructure_error` is the classifier. Both tools let either kind propagate; neither turns a failed read into "no rows".

| Input | Result |
|---|---|
| a ticker outside the three, a missing bound, a window reaching today, conflicting flags | exit 2 before any query |
| exits: an exit mode other than `target_stop` | exit 2 before any query |
| `--commit` with the ledger or a marker column absent | exit 2 before any write |
| no `GCS_BUCKET` and no `--report-dir` | exit 2 |
| a failed query, outage or defect | raises; groups already committed stay committed |
| a failed report upload | raises before any database write |
| a window with a row that is not proven | `unproven_rows`; the rows it covers are left; exit 1 |
| a window with no bar | `no_bars`; left; exit 1 |
| exits: bars that do not reach the last five minutes and no trigger | `bars_incomplete`; left; exit 1 |
| exits: a NULL price, target or direction | raises, naming the alert |
| a row changed between the read and the write | `changed_underneath`; left; exit 1 |
| exits: a trade whose exit is not its alert's | `trade_diverged`; the trade is left, the alert is written; exit 1 |
| premarket: a failed level-parameter read | raises |
| premarket: a session before the ticker's first parameter row | written unfiltered with status `params_unavailable` |
| a second run over the same window | `already_current`; nothing written; exit 0 |

### 8. Other specs this one meets

- **The bucket-copy spec** (`2026-11-13-feat-data-001-intraday-bucket-copy.md`, approved, being implemented). It is not edited.
  - Its Design H table says the two missing paths are run in step 7 "only once its reader is in this table as taking the stored instant or as placing rows by proof". Both readers here take the stored instant and refuse a window that is not proven. They are stricter than `place_stored_rows`, which lets the resolver place an unproven row.
  - Design H expected the exits path to read through `DataLoader._load_intraday_from_sql`. It does not: it has its own strict, proof-requiring read, so the general loader is not touched and the Readers step stays where it is.
  - Both specs edit `gcp/fetchers/fetch_alphavantage_intraday.py`: that one adds the export to `main()`, this one changes two dictionary entries and one log line. Different lines; either order.
  - Where these runs sit in its runbook is in Close-out.
- **The strict-bar-loader spec** (`2026-11-13-feat-data-001-strict-bar-loader.md`, approved; no plan on `main` yet). Both change `gcp/signal_monitor_eod_resolver.py`.
  - That spec moves `_load_day` (`:175`) and `_control_query_ok` (`:235`) to `load_intraday_strict` and wraps the alert loop of `run()` (`:543-572`).
  - This spec changes `resolve_one` (`:310-341`) and `_eod_close_resolution` (`:342-376`), adds methods, and adds flags to `main()` (`:596-615`). It does not edit `_load_day`, `_control_query_ok` or `run()`.
  - **Order: either.** The hunks do not overlap, and the second to land keeps the first's edits.
  - To keep that true, the tests this spec adds stub no loader method. They patch `_load_day` for the scheduled path, and the force mode's read is a query. So that spec's `done_when` count, "its eight load_intraday stubs", holds in both orders.
  - That spec adds the resolver, whole, to `REPLAY_PATH`. The code added here is written to pass its guards in either order: it holds no vendor request, uses no `gcs_reader`, calls no `DataLoader` method, and names the interval in its bar query. Those guards are not on `main` yet, so this was read from that spec's text, not run.
- **FEAT-REPLAY-001** (`#1891`, on `main`): a replay reads bars only from the table. Both tools read only `market_data_intraday`; the premarket mode's test fails on any HTTP request. Their flags (`--re-resolve`, `--recompute-premarket`, `--revert-run`, `--from`, `--to`, `--report-dir`) match none of the guard's flag patterns (`tests/meta/test_production_writers.py:439-440`), so `fetch_market_data.py`, which holds vendor requests for its other modes, is not drawn into `REPLAY_PATH`.
- **The draft two-bar-writers spec**: nothing here writes `market_data_intraday`.
- **The row-writer guard** (`tests/meta/test_production_writers.py:33-53`): it covers code that creates `signal_alerts` or `trades` rows. Both tools only update.
- **FEAT-STRAT-001 per-ticker parameters**: the premarket recompute reads the parameters as the nightly does and changes nothing of theirs. If the runbook's step 7 reruns the calibration for the three tickers, the premarket recompute runs after it.
- New code changes zone only through `lib/eastern_time.py`.

### 9. Consumers: what moves when a committed run writes

Named from the code. None is recomputed by these tools (decision 10).

For the exits (`signal_alerts`, `trades`):

| Consumer | Reads | What happens |
|---|---|---|
| `GET /api/analytics/summary/{ticker}` (`platform/api/routers/analytics.py:131-170`) | `trades.return_pct`, `exit_time` | computed on read: the win rate and returns on the Signals page move with the write |
| the Journal page's pipeline trades (`platform/api/routers/journal.py:1045`, `:1341`) | `trades`, `signal_alerts` | on read: the exit shown for a rewritten trade moves |
| `signal-quality-alarm` (`gcp/signal_quality_alarm.py:199-213`) | `exit_return_pct > 0` over its trailing windows | its next run reads the new values where a window reaches a rewritten alert; no stored table |
| `indicator-correlation` (`gcp/indicator_correlation_job.py:513-517`, 30-day lookback, `indicator_correlation`) | `exit_return_pct` as the win label | rows already stored for windows that reached May 2026 keep the old label; they can be rebuilt with `INDICATOR_CORR_AS_OF`, and are not, by this spec |
| the insight summarizers (`lib/agents/summarizers.py:967`, `:985`, `:1990`) | recent alerts and trades | the next insight run reads the new values; stored `insight_reports` keep what they said |
| `weekend-review` (`gcp/weekend_review.py`, through `gcp/trade_logger.py:176-243`) and `audit-walkforward` (`scripts/analysis/per_factor_walkforward.py`) | `trades.return_pct` by week or window | reviews and reports already posted are not reposted |
| the Discord replay of a signal (`gcp/signal_replay.py:117`) | the alert's exit | on read |
| `scripts/analysis/per_ticker_calibration.py:194-196` and other analysis scripts | exits | on their next run |
| dated documents | figures from the old outcomes | not restated: for example the 736 fires in the comment at `lib/config.py:310-312` and the 2026-08-25 profitability review. `docs/product/07-MODEL-REGISTRY.md` and `docs/EXPERIMENT_REGISTRY.md` are not edited |

- `exit_config_overrides` and `ticker_calibration` are calibrated from bars, not from these outcomes. They are outside this spec.

For the premarket fields:

| Consumer | Reads | What happens |
|---|---|---|
| the level builder, for an as-of replay (`lib/data_loader.py:572-573`, `lib/strat_levels.py:1925-1942`) | the session's snapshot | refused as unfiltered for sessions before 2026-11-12, as it is today for a row with no status |
| the insight summarizer and planner, for an as-of run (`lib/agents/summarizers.py:262-290`, `lib/agents/trade_planner.py:625`) | `pre_*`, `gap_pct`, the status | reads the new values, labelled unfiltered where they are |
| the premarket brief's earnings tables, for an as-of run (`gcp/premarket_brief.py:360`, `:722`) | `gap_pct`, `pre_high`, `pre_low` | reads the new values |
| `premarket_analysis` rows already stored | the levels the brief built at 08:30 from the 08:20 snapshot | not changed: they record what the brief saw |

### 10. Site traceability

`site_source_notes` cannot be widened by the implementation PR, so it is declared by the rule the two sibling specs use: one element per changed job per page, the first Chain row of that page in `docs/product/03-SITE-TRACEABILITY.md` whose Data cell names the job.

| Changed job | Dashboard | Live | Charts | Signals | AI Insights | Playbook | Journal | Admin |
|---|---|---|---|---|---|---|---|---|
| `signal-monitor-eod-resolver` (Design 3, Design 4) | not named | not named | not named | SIGNALS-02 (`:678`) | not named | not named | JOURNAL-02 (`:1042`) | not named |
| `fetch-market-data` (Design 5) | DASHBOARD-01 (`:331`) | LIVE-04 (`:426`) | CHARTS-01 (`:506`) | not named | INSIGHTS-01 (`:750`) | PLAYBOOK-05 (`:905`) | JOURNAL-01 (`:1041`) | ADMIN-06 (`:1123`) |

- Nine elements, each checked on 2026-11-14 to name the job in its Data cell.
- The change to the replace's advisory lines (Design 6) is a log text in `fetch-alphavantage-intraday`. No reader or route of that job changes, so it adds no element.
- Each note says what the source now does: for the two resolver rows, that the walk ends at the session close and that a force mode can rewrite a resolver-written exit with a ledger row; for the seven fetcher rows, that the premarket block is one function, that the nightly's row is unchanged, and that a bars-only mode can rewrite a past session's premarket columns. None claims a change on a page.
- No route and no response shape changes, so the implementation PR has nothing a deployed-site run could show. What a user can see change is data, when a committed run writes: the run's report and the read-only checks of Close-out are its evidence.

### 11. Capacity

| Run | Volume | Velocity | Wall-clock | Timeout and headroom |
|---|---|---|---|---|
| exits, dry run, everything | 835 alerts; 27 day reads of at most about 1,200 rows of seven columns, about 2 MB in all, one group in memory at a time | 1 selection query, 27 bar reads, 2 uploads: 30 round trips | 15 to 60 s at 0.5 to 2 s a round trip | `signal-monitor-eod-resolver`, 3,600 s, 1Gi, no retry (`gcp/deploy.sh:1499-1516`): 60 times under |
| exits, committed, everything | the same, plus 835 ledger rows of about 1 KB | the dry run's 30, plus per group one transaction of 3 statements (alerts, trades, ledger): about 165 round trips with begin and commit | 85 to 330 s | 10 times under; 4 times 330 s is 1,320 s |
| premarket, dry run, everything | 447 rows; about 1,200 daily rows; 24 month reads of at most about 7,600 bars, one month in memory at a time | 1 selection, 3 daily reads, 24 bar reads, 149 parameter reads, 2 uploads: about 180 round trips | 90 to 360 s, plus 447 runs of `add_all_indicators` over 250 rows, not measured | `fetch-market-data`, 5,400 s, 1Gi, 2 retries (`gcp/deploy.sh:2146-2171`): 4 times 360 s is 1,440 s |
| premarket, committed, everything | the same, plus 447 ledger rows | the dry run's 180, plus per group one transaction of 2 statements: about 280 round trips | 140 to 560 s | 4 times 560 s is 2,240 s |

- Measured on production, read-only (db-query-zzvwq): the exits' day read for QQQ 2026-05-01 returned 1,200 rows from an index scan in 2.7 ms; the premarket read over four sessions returned 1,316 rows in 19.7 ms, an index scan of 329 rows a loop, so rows read equal rows returned; the selection read `signal_alerts` whole, 3,601 rows in 255 buffers, and returned 835 in 4.3 ms. The table is small enough that the planner chose not to use `idx_signal_alerts_ticker_date`.
- So the statements cost milliseconds and the round trips are the wall-clock. The round-trip figure is CLAUDE.md Rule 0's; it was not measured for these jobs.
- No per-alert and no per-row statement: every write is one statement per group (REQ-CAP-002). Writing the 835 alerts one transaction each, as the scheduled `persist` does, would be about 2,500 round trips, up to 83 minutes at 2 s, over the timeout.
- Memory: one group at a time, under 10 MB of bars.
- Retries: `signal-monitor-eod-resolver` has none. `fetch-market-data` has two, so a premarket run that exits 1 runs twice more; each attempt is idempotent and prints the same lines.
- A run that exits 1 fails its execution, and the failure notifier files or comments on the job's `gcp-job-failure` issue (the bucket-copy runbook describes the same for its checks). The operator annotates it with the step and the execution id.
- Cost, at about $0.000018 a vCPU-second and $0.000002 a GiB-second (list prices, not re-read): a committed run of either tool is under one cent. Nothing is scheduled. The ledger and the reports are under 2 MB.

## Historical signals (decision 3)

Not designed here. What was read and run, so the runbook's step 7 is not surprised:

- `historical_signals` holds 1,557,534 rows for the three tickers, all `momentum`: QQQ 1,330,858 and IWM 193,206 from 2015-01-02, SPY 33,470 from 2026-01-02. 13 other tickers hold 211,735. `signal_metrics` holds QQQ 27,625, SPY 27,226, IWM 24,322 (db-query-pqprn).
- A window-bounded force would regenerate a slice against indicators warmed up from the slice's own start, and the whole history changed anyway. A full regeneration per ticker is the right scope.
- **Hazard 1: `--force` with `--dry-run` deletes.** `_process_ticker` deletes the ticker's rows first (`scripts/run_historical_signals.py:453-460`) and checks `--dry-run` after generating (`:519-522`). Run on 2026-11-14 with the delete and the bar read stubbed: `--force --dry-run` called `delete_for_ticker('SPY', 'momentum')` and returned 0. There is no dry run of a regeneration.
- **Hazard 2: the delete commits before anything is generated** (`gcp/historical_signals.py:132-133`). A run that fails after it leaves the ticker with no rows until a rerun finishes.
- **Hazard 3: `signal_metrics` rows are keyed to signals that may no longer exist.** Nothing deletes them when a regeneration drops a signal; an explicit `--start` and `--end` rescoring upserts the rows that still have a signal (`scripts/signal_quality_report.py:400-428`). Read, not run.
- If the owner wants a regeneration that can be dry-run and that swaps rows in one transaction per chunk, it is a second spec, under FEAT-SIGNAL-001. It does not gate the runbook's step 5: this table has a path.

## Implementation plan: size

14 tasks, one branch, one PR. Without decision 2 it is 13.

1. Schema: the ledger table and the three marker columns.
2. `gcp/bar_recompute.py`: run id, code version, the proof check, the report rows and summary, and `upload_text_to_gcs` in `gcp/gcs_utils.py`.
3. `gcp/bar_recompute.py`: the batched compare-and-set write, the ledger insert, the revert.
4. Resolver: the walk ends at the session close, with the two fixture moves.
5. Resolver: `find_resolved_alerts`, the flags and the refusals.
6. Resolver: the proof-requiring day read and the dry run.
7. Resolver: the committed run and `--revert-run`.
8. Fetcher: `premarket_snapshot` extracted, the nightly calling it.
9. Fetcher: the selection, the three reads and the dry run.
10. Fetcher: the committed run and `--revert-run`.
11. The integration test on real Postgres, both targets.
12. The RECOMPUTE lines and their two assertions.
13. The PR-body measurements.
14. The nine site notes, the snapshot, the generated inventories, the catalog record, PR traceability.

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box. Each waits for the owner's own yes, read-only ones included, and names its check. The record is kept as comments on the implementation PR and on #1190.

**Before the merge**: the read-only measurements of `done_when`, nothing else.

**After the merge**

1. **Apply the schema**: `./gcp/deploy.sh apply-schema`.
   - Check: `information_schema` shows `bar_recompute_ledger` and the three marker columns; the ledger is empty and no marker is set.
2. **Deploy the two jobs**: `./gcp/deploy.sh eod-resolver` and `./gcp/deploy.sh market-data`, from a checkout of `main` at or after the merge.
   - The first moves the scheduled 16:30 ET resolver to the session-close rule (Design 4). The second moves the nightly fetch and the 08:20 refresh to the image that holds `premarket_snapshot`. The owner's yes covers both.
   - Check: each job's image is the build's digest; the next scheduled run of each exits 0; the next nightly row for SPY has the eleven premarket columns set as on the night before.
3. **Rehearsal, dry**: both tools over the sessions that are proven today.
   - `gcloud run jobs execute signal-monitor-eod-resolver --region us-east1 --args="--re-resolve,--from=2026-09-28,--to=<yesterday>" --wait`
   - `gcloud run jobs execute fetch-market-data --region us-east1 --args="--recompute-premarket,--from=2026-09-28,--to=<yesterday>" --wait`
   - Check: both exit 0; each run's `rows.csv` and `summary.json` are in the bucket; the exits report holds the candidates a read-only count gives for that window (10 on 2026-11-14) and none is `unproven_rows`; the premarket report holds one row per ticker and session (105 on 2026-11-14, plus later sessions); the ledger is still empty.
   - The owner reads both reports. The six `eod_close` rows of 2026-09-30 and 2026-10-01 are expected to change.
4. **Rehearsal, committed**: the same two commands with `,--commit`.
   - Check: the ledger holds one row per report row marked written; the marker is set on exactly those rows; a read-only query shows each rewritten exit equal to its ledger `new_values`; a second dry run reports every row `already_current`.
   - Then `--revert-run` of the exits run as a dry run only, to see that it would restore the old values. It is not committed unless the owner wants the rehearsal undone.
5. **The gate.** With steps 1 to 4 recorded, both "no path" tables have a path that has run on production. That is what #1190 and the runbook's step 5 wait for. The record on #1190 names the two execution ids of step 4.
   - `./gcp/deploy.sh fetchers` then puts the new RECOMPUTE lines into the replace job, so a committed replace prints the two commands. If the runbook's step 1 already ran, this is a second deploy of the fetchers.
6. **CLAUDE.md 3.9** still says not to run `--replace-months --commit` until #1190 lands. Bringing it up to date is a FEAT-CICD-001 change on its own branch, since the gate refuses that file here. Until it merges, the record of step 5 is what says the hold is met.
7. **The runbook's steps 5 and 6 run** (bucket-copy spec): the replace, then the scan that shows `unproven_rows=0` for every month.
8. **In the runbook's step 7, the full recompute.** After step 6 has passed, and after the `ticker_level_params` item of step 7.
   - Dry run of both tools over everything: exits from 2026-05-01, premarket fields from 2026-04-14, both to yesterday. Check: exit 0, no `unproven_rows`; the counts equal the read-only counts (835 and 447 on 2026-11-14, plus later rows); the summary gives, per ticker, how many exits change and the wins and mean return before and after.
   - A row that is `no_bars` or `bars_incomplete` is recorded by name and stays as it is; the owner decides about it. The run then exits 1, which is expected for that case.
   - The owner reads the reports and says yes to each tool separately.
   - Committed run of each. Check: the ledger's rows for the run equal the report's written rows; `SELECT count(*) FROM signal_alerts WHERE exit_recompute_run IS NOT NULL` and the same for `trades` and `market_data_daily.pre_recompute_run` equal them; for three alerts chosen from the report, a read-only query shows the stored exit price equal to the close of the stored bar at the stored exit minute; a second dry run reports everything `already_current`.
   - The record lists the consumers of Design 9 with the before and after from the summary, and answers the replace's two RECOMPUTE lines with the two execution ids.
9. **Undo**, if the owner asks: `--revert-run <run id> --commit` on the same job. Check: the ledger holds the revert's rows and the rows hold their old values.

**After the runbook**: the nine site notes and the plan's status are brought to the deployed state on a `docs/` branch.

## Risks

- **The whole-minute rule misclassifies an exit.** A live exit stamped exactly on a minute would be re-resolved; the chance is about one in sixty million per exit. The integration test seeds both kinds, and the dry run lists every selected row before any write.
- **The force read and the scheduled read drift apart.** They are two reads of one table. `done_when` asserts equal frames for a true-UTC session, and both feed the same `resolve_one`.
- **The session-close rule changes scheduled outcomes** from the deploy on (Design 4). The five cases of `done_when` item 3 state the new behaviour, and the first scheduled run after the deploy is a Close-out check. An alert left open by a thin close fails the job daily until it is closed by hand.
- **A recomputed exit differs for a reason other than the bars**: the RSI period or thresholds in the configuration differ from those in force when the alert fired. The thresholds are 80 and 20 today (`lib/config.py:343-344`, `alert_config.json:58-59`); their history and the period's were not read. The ledger records what each run used.
- **The RSI on a session bar depends on the premarket bars before it**, as it does today, and the live monitor computes its RSI from its own window. A re-resolved `rsi_extreme` follows the resolver's rule, not the monitor's. Unchanged by this spec.
- **Outcome statistics move with no announcement on the site.** 835 of 3,146 exits can change, 820 of them on six sessions of May. The summary's before and after, and Design 9's list, are the record; stored results built on the old outcomes are not restated (decision 10).
- **Premarket values change for two reasons at once**: the bars, and the code. A row written before the print filter existed is recomputed by today's rule, unfiltered. The report cannot separate the two causes; it gives the old and new values and the status.
- **`pre_range_atr` becomes NULL** on the rows that hold it for sessions before 2026-11-12 (at most two a ticker), because those sessions have no `ok` parameters. Listed in the dry run as a change.
- **A month the replace cannot complete stays unproven**, and both tools refuse its sessions with no override. The runbook already keeps such a month open for the owner.
- **A dry run that refuses rows exits 1** and files a failure issue. Before the replace this is avoided by running only the proven window (step 3).
- **`fetch-market-data` retries twice.** A premarket run that exits 1 runs three times. Each attempt is idempotent.
- **The ledger is the undo, and a defect in the ledger write would lose it.** The bucket report is saved before the first write and holds the same old values; point-in-time recovery covers seven days.
- **A second copy of the premarket block stays in `gcp/backfill_ticker.py`** and can drift from `premarket_snapshot`. Reported; not changed here.
- **The nightly's own reads still swallow a failure** (`query_to_dataframe` at `fetch_market_data.py:367` and `:468`). The recompute reads strictly; the nightly's reads are not changed, and the lines that move carry the `AUDIT-2026-05-13` marker CLAUDE.md 3.7 asks for.

## What was not verified

- That the 2026-11-14 rewrite of the whole history happened as reported, and that its values match the vendor: not re-verified here. What was read: the misplaced rows are still stored, and the rows of 2026-05-01 kept their old insert times.
- Which writer stores premarket bars for the current day before 16:30 ET: not traced.
- The wall-clock of either tool on production: not measured. The round-trip figures are Rule 0's.
- Whether any candidate alert holds a NULL price, target or direction: not read.
- Whether `gcloud run jobs execute` accepts the `--args` forms of Close-out for these two jobs: not run. The bucket-copy runbook uses the same form on the fetch job.
- The history of the RSI period and thresholds in the exit configuration: not read.
- Whether the backend architecture canvas depicts either job: not opened.
- Hazard 3 of "Historical signals": read, not run.
- The prototype of Design 4 covered `resolve_one` only. No prototype of the force mode, the ledger write or the premarket mode was built; their SQL was not run on Postgres beyond the three reads measured above.
