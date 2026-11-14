---
feat_id: FEAT-DATA-001
req_ids: [REQ-CAP-001, REQ-CAP-002, REQ-DATA-001]
issues: [1190]
canvases: []
done_when:
  - "tests/gcp/test_intraday_replace_months.py::test_label_copies_at_true_keys_do_not_make_a_refetch_short passes: one session whose refetch holds 842 bars is stored as those 842 true-UTC rows, plus 206 Eastern-labelled rows at UTC 04:00 to 07:59, plus 34 Eastern-labelled copies of refetched bars at UTC 08:00 to 10:59 on keys no refetched bar uses; replace_month returns dry_run without --commit and replaced with it, the frame handed to the swap holds the 842 bars, and the result reports label_copies=34 and label_dropped=206 (on main the same rows return incomplete_refetch with missing ['<day> (842/876)']); ::test_label_region_rows_alone_never_made_a_refetch_short holds the same session without the 34 copies and returns dry_run before and after the change"
  - "tests/gcp/test_intraday_replace_months.py::test_previous_months_late_bars_are_spared_and_not_asked_of_this_month passes: with bars of 2018-02-28 at 21:04, 22:10 and 23:37 Eastern stored at their true keys, replace_month for 2018-03 returns replaced, reports carry_in=3, and calls the swap with those three keys in spare_ts and none of them in the frame (on main: incomplete_refetch, missing ['2018-02-28 (0/2)']); ::test_a_months_own_late_bars_past_the_window_are_written passes: replace_month for 2018-02 with a refetch that holds those three bars returns replaced, reports tail=3, and makes a second swap over [2018-03-01 02:00Z, 2018-03-01 04:38Z) whose frame is the three bars and whose spare_ts holds every other key stored in that range (on main a committed run raises ValueError '3 row(s) fall outside'); a refetched row at or after the next month's Eastern midnight is still refused"
  - "tests/gcp/test_intraday_replace_months.py passes three cases in which a short refetch is still refused with nothing handed to the swap: ::test_a_short_refetch_is_still_refused_on_a_clean_month (the refetch lacks every bar of 05:00 to 06:59 Eastern that is stored as a true-UTC row, and no label row is stored); ::test_a_short_refetch_is_still_refused_beside_label_copies (the same refetch against the first item's stored rows: label_copies=34 and incomplete_refetch); ::test_a_month_held_only_under_the_eastern_label_keeps_todays_floor (961 Eastern-labelled rows and no true-UTC row: a refetch of 961 bars returns replaced with label_copies=0, and a refetch without the 04:00 to 07:59 Eastern bars returns incomplete_refetch with missing ['<day> (721/961)'])"
  - "tests/gcp/test_intraday_replace_months.py::test_a_returned_late_bar_does_not_stand_in_for_a_missing_window_bar passes: bars of 2018-02-28 are stored at 09:30, 20:59 and 21:04 Eastern at their true keys and the refetch of 2018-02 holds only 20:59 and 21:04; replace_month returns incomplete_refetch with missing ['2018-02-28 (1/2)'], with and without --commit, and nothing is handed to either swap"
  - "tests/gcp/test_intraday_replace_months.py::test_a_tail_key_rewritten_during_the_run_is_not_overwritten passes: a row stored at a tail key gets new values and a new inserted_at after the snapshot and before the second swap takes its lock, with no key added or removed; the second swap rolls back, the month's status is tail_not_written, the stored row keeps the newer values, the RETRY line is printed and run_replace_months exits 1; with the tail strip unchanged the same month is replaced and its tail written"
  - "tests/gcp/test_intraday_replace_months.py::test_every_month_prints_an_uncounted_line passes: run_replace_months logs, for every listed month and with or without --commit, one line 'UNCOUNTED TICKER,YYYY-MM rows=<n> uncounted=<n> share=<p>% label_dropped=<n> label_copies=<n> by_utc_hour=<HH:n,...> carry_in=<n> tail=<n>', whose numbers equal the counts of the fixture written out in the test, and a month with none of these prints the line with zeros"
  - "tests/gcp/test_intraday_replace_months.py::test_a_month_over_the_uncounted_bound_is_refused passes: REPLACE_MAX_UNCOUNTED_SHARE equals 0.25; a month whose uncounted rows are 26% of its stored rows returns uncounted_over_bound with and without --commit, nothing is handed to the swap, run_replace_months prints its RETRY line and exits 1; the same month at 25% is replaced"
  - "tests/gcp/test_intraday_replace_months.py::test_the_swap_spares_the_listed_keys passes on the mocked engine the file already uses (the lock statement and the DELETE both exclude the keys of spare_ts, a frame that holds a spared key is refused before the transaction opens, and the delete-ratio check counts the rows deleted), and tests/integration/test_intraday_replace_spare.py passes in the integration-tests CI job on real Postgres: a window of ten rows swapped with two keys in spare_ts leaves those two rows equal in every column, inserted_at included, deletes the other eight and inserts the frame"
  - "make test passes on the PR head; lib/eastern_time.py, platform/api, gcp/deploy.sh and the files under gcp/queries/ are not in the PR's diff; month_replace_window, REPLACE_SHORT_TOLERANCE and REPLACE_MAX_DELETE_RATIO are unchanged; the existing cases of tests/gcp/test_intraday_replace_months.py keep every assertion they make and change only where they stub the stored-row read, with each changed line listed in the PR body"
  - "02-FEATURE-CATALOG FEAT-DATA-001 record shows Status and Last reviewed for this PR, 12-PR-ISSUE-TRACEABILITY lists it, the branch run of python3 scripts/maintenance/docs_audit.py reports nothing that origin/main does not, and python3 scripts/gate/spec_gate.py --pr origin/main passes"
status: superseded
supersedes: null
---

# Replace-months: late bars across the month boundary and Eastern-label copies no longer make a refetch look short

## Scope

- `fetch_alphavantage_intraday --replace-months` refuses 29 of the 423 SPY, QQQ and IWM ticker-months from 2015-01 to 2026-09 as `incomplete_refetch` in a dry run. This spec changes what the replace counts as held, what its swap deletes, and what it prints, so that those months can be replaced without losing a bar.
- It is a code change to `gcp/fetchers/fetch_alphavantage_intraday.py` and to `replace_rows_in_window` in `gcp/database.py`, for every ticker. The runbook it serves is for SPY, QQQ and IWM only.
- It adds no job, no schedule and no deploy change. It writes nothing by itself: a committed replace stays behind #1190 and the owner's yes (Close-out).
- Code references are to `main` 572a6362 (2026-11-14). Every production number has its execution name beside it and was read without `--commit` on 2026-11-14.

## Status of the decision

- The owner delegated this decision to the delivery session on 2026-11-14: "I need you to make the executive decisions on what needs to be done. I'm giving you that authority." The owner's question was "Why would we keep bad data with good data?"
- The delivery session then decided five points. The measurements below were made after that, and they do not support point 1 as it was put. The delivery session read the measurements and Design 1 to 7 on 2026-11-14 and confirmed the table below, so this file is `approved` under that delegation. The owner was told on 2026-11-14 that the fix differs from the first description given (rows inside the session, told apart by content, and the previous month's late vendor bars spared).

| Point as decided | In this spec |
|---|---|
| 1. A row counts as held only if, read as a true UTC instant, it falls inside 04:00 to 20:00 Eastern; other rows are "out-of-session", are not coverage, and are removed | **Not adopted as put.** The vendor's months hold bars outside that window, 94 of which sit in the next month's window (Problem 2), and the rows that make IWM look short are inside it (Problem 1). Replaced by Design 2 to 5 |
| 2. The guard is unchanged for real bars; a month held only under the Eastern label keeps a floor | Adopted. The formula and `REPLACE_SHORT_TOLERANCE` do not change, and every row read as an Eastern label counts as today (Design 3, Problem 3) |
| 3. Every run prints per month what it would remove, by UTC hour, and a committed run refuses a month over a stated share | Adopted, for the rows that are not counted (Design 6). Bound 25% |
| 4. A committed replace is not retried blindly | Adopted (Design 7, Close-out step 3) |
| 5. Out of scope: the rebuild of the 15 `DERIVED_TS_TABLES`, the recompute tools, other tickers in the runbook | Adopted (Non-goals) |

## Capability

- `docs/product/02-FEATURE-CATALOG.md`, row FEAT-DATA-001: Data platform; ingestion, storage, freshness; fetcher jobs; "Production but needs remediation"; P0.
- Requirements: REQ-CAP-001 and REQ-CAP-002 (capacity, batching, idempotent re-runs), REQ-DATA-001 (no silent substitute for missing data: a month the vendor does not give back whole is refused, never thinned).
- No canvas is listed: no job, route or table is added.

## Problem

### 0. Why the replace is needed, and what the dry run printed

- On 2026-11-14 from 00:02Z to 00:41Z the 1-minute history of SPY, QQQ and IWM was rewritten as traded by a plain upsert (reported by the delivery session; not re-verified here). An upsert overwrites and adds. It deletes nothing and keeps `inserted_at`.
- So most rows are not proven true instants (`lib.eastern_time.proven_true_utc`, `lib/eastern_time.py:379-397`): SPY 2,449,382 of 2,536,918 and IWM 2,019,133 of 2,057,801 (`freshness-watchdog-sf9rk`, read before the one committed month of Problem 2; the saved log is cut off inside QQQ, whose figure was reported as 2,296,427 of 2,371,657). A committed replace deletes and inserts, which gives every row a new `inserted_at`.
- Dry run of `--replace-months` over 141 months per ticker (`fetch-alphavantage-intraday-f265l` SPY, `-rbptm` QQQ, `-4tttz` IWM): SPY 130 `dry_run` and 11 `incomplete_refetch`; QQQ 135 and 6; IWM 129 and 12. Two causes, neither of them a short vendor answer.

### 1. IWM 2026-04 to 2026-09: Eastern-label copies stored at keys inside the session

- IWM's window for 2026-04-10 holds 206 rows at UTC 04:00 to 07:59 (57, 43, 46, 60 by hour), all inserted 2026-04-13 23:28:09Z, at clock times only an Eastern-labelled writer uses, and 876 rows from 08:00Z to 00:00Z of the next day (db-query-wtlm4, db-query-2jg9t). The dry run printed `2026-04-10 (842/876)`.
- **The 206 rows are not what the guard counts.** Each has a stored row exactly four hours later (206 of 206, db-query-2jg9t), so `stored_intraday_to_eastern` drops each as the second row on its Eastern minute (`lib/eastern_time.py:332-336`). Run on `main` on 2026-11-14: a session of true-UTC rows plus label rows at UTC 04:00 to 07:59 returns `dry_run`.
- **The held count of 876 is the true reading.** UTC hours 08 to 19 hold 60 rows each. The vendor's premarket is thinner than that: the label rows of hours 04, 05 and 06 number 57, 43 and 46. The difference, 3 + 17 + 14 = 34, is label rows of the 08:00 to 10:59 Eastern bars, inserted at UTC 08:00 to 10:59 by the same transaction as the 206 (34 rows of the session share its insert time, db-query-hvwdf), on keys where no true bar exists. The upsert never touched them. Read as true instants they are 04:00 to 06:59 Eastern: inside the session, at minutes the vendor has no bar for. 876 minus 34 is 842.
- Each is a copy of the bar four hours later. Over the 126 IWM sessions of 2026-04 to 2026-09, 4,620 rows share an insert time with a label row of UTC 04:00 to 07:59 and hold the volume of the stored row four hours later; 4,617 of them also hold its open, high, low and close (db-query-9jr5s). By month: 397, 555, 645, 1,076, 1,313, 634.
- In the 60 sessions the dry run printed for IWM, that count equals held minus fetched in 58 and differs by one row in 2 (2026-07-02: 65 against 66; 2026-07-06: 55 against 54).
- SPY and QQQ hold the same kind of row, fewer: stored rows minus label rows of UTC 04:00 to 07:59 minus the vendor's rows is 3, 5, 14, 24, 42 and 18 for SPY 2026-04 to 2026-09 and 1, 0, 0, 2, 7 and 2 for QQQ (db-query-hvwdf against the dry run's `inserted`). That is inside the 2% tolerance, so those months pass today.
- So a rule that drops rows outside 04:00 to 20:00 Eastern from the held count changes nothing here: every row that makes IWM look short is inside it.

### 2. 2015 to 2019: the vendor's own late bars, stored in the next month's window

- The vendor's months hold bars outside 04:00 to 20:00 Eastern. The three tickers hold 6,494 rows after 20:00 Eastern and 8 before 04:00 Eastern, all in 2015 to 2019, inserted between 2026-02-23 and 2026-05-26 (db-query-hhw6t, db-query-hvwdf).
- They are the vendor's: for each of the 382 ticker-months before 2026-04 that reached `dry_run`, the stored rows whose Eastern date is in the month equal the dry run's `inserted` exactly (db-query-hvwdf against the three dry-run logs). That count would be lower by the late rows if the vendor did not return them.
- Seen directly in the first committed replace, SPY 2015-06, run with the owner's yes (`fetch-alphavantage-intraday-jbd95`, 2026-11-14 19:26:48Z to 19:27:14Z, reported by the delivery session): deleted 16,849, inserted 16,849, `intraday_flow_15m` cleared of 1,413 rows and no other derived table; `--verify-months` then reads the month clean (`fetch-alphavantage-intraday-9tgn4`). Before it the window held 16,849 rows, 13 of them after 20:00 Eastern (db-query-hhw6t). After it the window holds 16,849 rows, every one inserted 2026-11-14 19:27:03Z, 13 of them after 20:00 Eastern, the last at 2015-07-01 01:01Z, which is 21:01 Eastern on June 30 (db-query-8d8b6). The vendor returned those 13.
- So a row outside 04:00 to 20:00 Eastern is not junk by definition, and no rule here assumes the vendor never returns one.
- The month window `[M-01 02:00Z, (M+1)-01 02:00Z)` rests on bars ending at 20:00 Eastern (`lib/eastern_time.py:537-547`). A bar of a month's last session at or after 22:00 Eastern (21:00 in winter) lies in the next month's window. 94 rows do, at 02:01Z to 04:59Z on 23 firsts of a month (db-query-9jr5s): IWM 9, QQQ 21, SPY 64.
- The 23 refused months of 2015 to 2019 are exactly the months that follow those 23: `SPY 2018-03 missing=['2018-02-28 (0/20)']` is February's late bars, which March's vendor month cannot return.
- 15 of the 94 lie at 04:00Z to 04:59Z in winter. The resolver reads that hour as Eastern labels of the first (`lib/eastern_time.py:276`), which is why the dry run shows 20 of SPY's 23 rows.
- For 17 of the 23 months that own such rows, the count above shows the vendor returns them (50 rows). The other 6 were themselves refused and have no vendor count (SPY 2015-09, 2018-02, 2018-05, 2019-02; QQQ 2019-02; IWM 2019-02; 44 rows): not checked.
- **A second failure the dry run cannot show.** Run on `main` on 2026-11-14: with February 2018's refetch holding three bars after 21:00 Eastern on the 28th, the dry run of February returns `dry_run`, and the committed run raises `ValueError: replace_rows_in_window(market_data_intraday): 3 row(s) fall outside [2018-02-01 02:00:00+00:00, 2018-03-01 02:00:00+00:00)`. `run_replace_months` reports that as SYSTEMIC and prints RETRY (`gcp/fetchers/fetch_alphavantage_intraday.py:726-730`). So a month that owns such rows fails on commit as well, wherever the vendor still returns them: 17 months by the count above, 6 not checked.
- Treating the 94 rows as out-of-session rows would delete vendor bars: March's swap deletes its whole window and March's refetch does not hold them.

### 3. A month held only under the Eastern label

- Read from `stored_intraday_to_eastern`: on a date written only by the Eastern-labelled writer, rows sit at UTC 04:00 to 20:00. Read as true instants, the rows before 08:00Z (09:00Z in winter) fall before 04:00 Eastern. Run on 2026-11-14: a session of 961 label rows counts 961 as placed today and 721 inside 04:00 to 20:00 Eastern under the true reading.
- So a held count taken from the true reading would let a refetch 240 bars short pass for such a month. The placed count must stay for rows read as labels.
- Whether SPY, QQQ or IWM still hold such a session: no evidence of one. For each ticker, every one of the 126 session dates of 2026-04 to 2026-09 holds rows after 16:00 Eastern under the true reading, where no label can sit; all 82,481 label rows of UTC 04:00 to 07:59, on 121 dates from 2026-04-06 to 2026-09-25, have a stored row four hours later (db-query-48j5r); before 2026-04 only the 8 vendor bars above read before 04:00 Eastern; and for all 394 months that reached `dry_run` the stored true-reading rows are equal to the vendor's or above it, never below. Per session against the vendor's count it was not checked: the dry run prints month totals.
- Other tickers were not read. The design keeps today's floor for them.

## Non-goals

- The rebuild of the 15 `DERIVED_TS_TABLES` after a replace. The replace still clears them for the window; a separate read-only review maps the rebuild.
- The recompute tools (#1190; plan `docs/superpowers/plans/2026-11-14-feat-data-001-recompute-after-bar-rewrite.md`).
- Any ticker other than SPY, QQQ and IWM in the runbook.
- The month window, `stored_intraday_to_eastern`, and every other reader of the table. The 15 winter rows of Problem 2 are still read by the Charts API as 04:00 Eastern bars of the first; that reading is not changed here.
- The bucket copy's month files, which use the same window and so hold the 94 rows in the following month's file.
- No vendor bar is dropped for its time of day. A bar the vendor returns is stored, whatever its Eastern clock time.

## Approaches considered

- **Count as held only rows inside 04:00 to 20:00 Eastern under the true reading** (point 1 as decided). Does not clear the six IWM months, deletes the 94 late bars, and lowers the floor of a label-only month by a quarter. Not taken.
- **Compare held and fetched both inside 04:00 to 20:00 Eastern, let the refetch write back whatever else the vendor returns, and report the rest as removed.** Sound for a late bar inside its own month's window, where the swap already deletes and re-inserts it. It leaves the six IWM months refused, since their extra rows are inside the session; it reports the 94 late bars in the next month's window as removed and deletes them, since that month's refetch does not hold them; and it leaves the owning month's commit raising. Not taken; its aim is kept: held and fetched are compared on one basis, the Eastern date of every bar, as today.
- **Move the window boundary from 02:00Z to 04:00Z.** Takes in 79 of the 94 rows and leaves the 15 winter ones. It changes a boundary that two approved specs, the bucket copy and the session scan use. Not taken.
- **Raise `REPLACE_SHORT_TOLERANCE`.** IWM's excess reaches 95 of 887 bars in a session (2026-08-14), 10.7%. A tolerance that wide stops refusing a refetch that is really short. Not taken.
- **Chosen: decide each case from the refetch itself.** A stored row that is a field-for-field copy of a refetched bar, at the key that bar would have under the Eastern label, is not a bar of its own. A stored row before the month's Eastern midnight belongs to the previous month and is left alone. Everything else is counted and guarded exactly as today.

## Design

### 1. Terms, for one ticker-month M

- **Window**: `month_replace_window(year, month)`, unchanged: `[M-01 02:00Z, (M+1)-01 02:00Z)`.
- **Refetch**: the frame `fetch_month` returns, with its naive Eastern `ts` kept beside the UTC key that `eastern_index_to_utc` gives.
- **Label copy**: a stored row for which the refetch holds a bar whose naive Eastern time equals the row's UTC clock reading, date and minute, and whose open, high, low, close and volume all equal the row's. A NULL field never equals. The comparison is exact.
- **Carry strip**: `[M-01 02:00Z, M-01 00:00 Eastern)`, which is two hours in summer and three in winter.
- **Carry-in**: a stored row in the carry strip that is not a label copy. Read as a true instant its Eastern date is the last day of the previous month.
- **Tail**: the refetched rows of a held session whose UTC key is at or after the window's end. They are M's own late bars.
- All of this is one pure function of the stored rows and the refetch, in `gcp/fetchers/fetch_alphavantage_intraday.py`. It reads nothing.

### 2. The stored-row read

- The snapshot read of `replace_month` returns `ts`, `open`, `high`, `low`, `close` and `volume` for the window, strict, before the refetch as today (`:589`). `_held_session_dates` keeps its signature and its result.
- The locked re-check in `verify()` is unchanged: the placed counts and the digest of the rows under lock must equal the snapshot's (`:633-642`).
- A committed run also takes, before the refetch, the digest of the rows stored in the tail strip `[window end, (M+1)-01 00:00 Eastern)`: the same `_held_digest` (keys, five fields, `data_source`, `inserted_at`) over that range. It is the baseline of the second swap's re-check (Design 5).

### 3. What counts as held

- Rows are placed once over the whole window by `stored_intraday_to_eastern`, as today, and one row is kept per Eastern minute.
- A kept row counts toward its session unless one of two things holds:
  - it is a carry-in;
  - the resolver read it as a true instant, the refetch holds no bar at its key, and it is a label copy.
- Every row the resolver reads as an Eastern label counts as today. So a month held only under the label has today's floor (Problem 3), and the answer to "is the true-reading count complete" is never needed.
- The guard's formula is unchanged: a session is missing when the refetch holds fewer bars for it than `held - int(held * REPLACE_SHORT_TOLERANCE)`. A missing session leaves the month untouched.
- Both sides are counted over the window and nothing else. `held` comes from the window's stored rows, so the refetch's count for a session takes only the refetched bars whose UTC key is inside the window. The tail (Design 5) is counted on neither side: its stored rows lie outside the snapshot, and its swap deletes only keys the refetch returns. Counting it for the refetch alone would let a returned late bar stand in for a window bar the refetch lacks. With bars of 2018-02-28 stored at 09:30, 20:59 and 21:04 Eastern and a refetch holding only the last two, February's window holds two and the refetch one inside it, so the month is `incomplete_refetch`; counted with the tail it read two against two and the main swap deleted 09:30.
- Why discounting a label copy loses nothing: its five fields are the fields of a bar the refetch returns, and that bar is inserted at its true key by the same swap.
- Why a short refetch still fails: a real bar the refetch lacks is discounted only if the refetched bar four or five hours later is equal to it in all five fields. Each such row is judged alone, so a refetch missing a stretch of bars stays short by nearly all of them. Run on 2026-11-14 on a prototype of these rules: a refetch without its 05:00 to 06:59 Eastern bars holds 830 against 927 held and is refused, with and without the 34 copies stored.

### 4. The swap spares the previous month's late bars

- `replace_rows_in_window` gains `spare_ts`, a list of keys inside the window. The lock statement and the DELETE exclude them, a frame that holds one of them is refused before the transaction opens, and the delete-ratio check counts the rows deleted. The derived-table clears keep the whole window.
- `replace_month` passes the carry-in keys. They are not counted (Design 3), not deleted, and not rewritten: they keep their values and their `inserted_at`.
- So a carry-in stays unproven until its own month is replaced (Design 5). A carry-in its own month's refetch does not return stays as it is and shows in the session scan as an unproven row. It is never removed on this month's evidence.

### 5. A month writes its own late bars

- Before the swap, the tail is split from the frame. A tail row at or after `(M+1)-01 00:00 Eastern` is refused as today: it is not a bar of M.
- After the main swap commits, a second swap over `[window end, last tail key + 1 minute)` inserts the tail, with `spare_ts` set to every key stored in that range that the tail does not hold, with the same derived-table clears, and with a `verify` that, under the lock, takes the digest of the tail strip again and rolls back unless it equals the one taken before the refetch (Design 2). The digest covers content and `inserted_at`, not only keys: a writer that inserts, deletes or updates a row of the strip between the snapshot and the lock, for example the nightly upsert writing new values at a key the tail also holds, leaves the tail unwritten, where a key-only check would let the older refetch overwrite the newer row. It deletes only rows at keys the refetch returns for M.
- If the second swap fails or finds the range changed, the month's status is `tail_not_written`, it prints RETRY, and a second run converges: the main swap is idempotent.
- The order of two neighbouring months does not matter. Whichever runs first, the previous month's late bars are spared by the later month and rewritten, with a new `inserted_at`, by their own.
- A dry run computes the same split and writes nothing.

### 6. What every run prints, and the bound

- For every listed month, dry or committed, `run_replace_months` logs one line after the month's status line:
  - `UNCOUNTED TICKER,YYYY-MM rows=<n> uncounted=<n> share=<p>% label_dropped=<n> label_copies=<n> by_utc_hour=<HH:n,...> carry_in=<n> tail=<n>`
  - `rows`: stored rows of the window. `label_dropped`: rows read as Eastern labels that lost their Eastern minute to another row. `label_copies`: rows discounted by Design 3. `uncounted`: their sum, which is what the swap deletes and writes back nowhere. `by_utc_hour`: the uncounted rows by the UTC hour of their key.
  - A kept row the refetch does not return, inside the tolerance, is not in the line; it is the difference between `deleted` and `inserted` that the status line already prints.
- `REPLACE_MAX_UNCOUNTED_SHARE = 0.25`. A month whose `uncounted` is more than that share of `rows` gets the status `uncounted_over_bound`, dry or committed, nothing is handed to the swap, and it prints RETRY.
- Where 25% comes from:
  - Measured maximum among the months that reached `dry_run`, as stored rows minus vendor rows over stored rows: SPY 2026-08, 5,040 of 25,174, 20.02%. QQQ 2026-07 is 5,282 of 26,400, 20.01%.
  - Measured maximum with IWM's label copies added, from stored rows and not from a refetch: IWM 2026-08, 3,753 + 1,313 = 5,066 of 22,503, 22.51%.
  - A session with a bar on every minute, stored in both conventions, gives 240 of 1,201, 19.98%, and 300 of 1,261, 23.79%, in winter.
  - 25% of 22,503 is 5,625, so IWM 2026-08 has 559 rows of room. The deployed dry run prints the real shares before anything is written (Close-out step 2).
- `REPLACE_MAX_DELETE_RATIO` stays as the backstop it is.
- The constant is set from these three tickers. A ticker stored in both conventions with no bars before 08:00 Eastern can exceed it; such a month is refused, which is the safe side, and the constant is re-derived before the tool is run for it.

### 7. Retries

- The job has `maxRetries: 1` (`gcp/deploy.sh:2217`; read from the live job on 2026-11-14), so each dry run ran twice: both executions show one failed and one retried attempt.
- `_HeldChanged` and the digest protect one call of `replace_month` from a writer that lands between its snapshot and its DELETE. They do not make a second pass a no-op. A retry is a new process over the same list: a month that reached `replaced` is deleted and inserted again from a second refetch.
- That second pass is safe for the bars and converges on the vendor's month. It spends every vendor call twice, clears the derived tables again, and repeats whatever made the first pass exit 1.
- `gcloud run jobs execute` has no retry flag; `gcloud run jobs update` has `--max-retries`. The runbook sets the job to 0 for the committed executions and sets it back (Close-out step 3). `gcp/deploy.sh` is not changed.

### 8. What bad input gets

| Input | Result |
|---|---|
| A session's refetch is short beyond the tolerance, after Design 3 | `incomplete_refetch`, as today; nothing written |
| A stored row equal to a refetched bar in four fields of five | counted as held |
| A label copy stored on another price basis than the refetch | not a label copy: counted, so the month is refused as it is today |
| Uncounted rows above 25% of the window | `uncounted_over_bound`; nothing written |
| A frame row at a spared key, or a tail row past the next Eastern midnight | `ValueError` before any transaction, reported SYSTEMIC, as today |
| A writer changes the window or the tail strip between the snapshot and the lock, by a new key or by new values at a held key | `changed_during_replace` or `tail_not_written`; rolled back |
| The refetch returns a session's late bars past the window end but lacks one of its bars inside the window | `incomplete_refetch`; the late bars are not counted for the session |
| A database error on any read | raised; never read as "nothing held" |

### 9. Other specs this one meets

- **The bucket-copy spec** (`2026-11-13-feat-data-001-intraday-bucket-copy.md`, approved). Its runbook step 5 says a month refused twice as `incomplete_refetch` stays open and the owner decides. This spec is that decision's change. Its text is not edited; Close-out says where the steps here sit.
- **The recompute spec** (`2026-11-14-feat-data-001-recompute-after-bar-rewrite.md`, approved). It changes two entries of `BAR_DERIVED_RESULTS` and one log line in the same module, and two assertions near the end of the same test file. This spec changes `replace_month`, adds a log line after `:738-742`, and appends its cases at the end of the test file. Different lines; either order. Its tools read sessions from 2026-04-14 on, and every carry-in measured is of 2015 to 2019.
- **The gaps and basis spec** (`2026-11-13-feat-data-001-intraday-gaps-basis-copy.md`, approved). `proven_true_utc`, `place_stored_rows` and `session_minute_readings` are not changed.
- CLAUDE.md 3.9 and #1190 still hold `--replace-months --commit`.

### 10. Capacity

| Run | Volume | Velocity | Wall-clock | Timeout and headroom |
|---|---|---|---|---|
| dry run, one ticker | 141 windows, 2.0 to 2.5 million rows in all, one window in memory at a time; the largest is 26,400 rows of six columns, about 1.3 MB | per month one stored read and one vendor request: 282 round trips | measured on the code of `main`: 171 to 198 s a pass, 1.2 to 1.4 s a month | 3,600 s, 2Gi: 18 times under |
| committed, one ticker | the same, and the rows are deleted and inserted | per month the dry run's two, a digest read, and one transaction (lock, two verify reads, one DELETE, at most six INSERTs of 5,000 rows, 15 derived DELETEs); a second small transaction for the months with a tail | one month measured: SPY 2015-06, 16,849 rows, about 8 s for the replace inside a 26 s execution (`fetch-alphavantage-intraday-jbd95`, as reported). At that rate per row, a ticker's 2.0 to 2.5 million rows are 950 to 1,190 s, plus the dry run's 171 to 198 s | over a quarter of 3,600 s in one execution, so each ticker runs as two lists of about 70 months, 560 to 700 s each by this estimate |

- Stored rows in the 423 windows: 6,877,010 (SPY 2,506,181, QQQ 2,340,937, IWM 2,029,892; db-query-hhw6t).
- The one timed month cleared rows in one derived table. Months from 2016 on also hold rows in the feature and level tables, and a month's 15 derived DELETEs over those were not timed. The first months of Close-out step 4 give that number before the lists are cut.
- This change adds no round trip to a dry run. To a committed run it adds one key read and one transaction for each month with a tail: 23 of 423 as measured.
- The classification is in memory: one dictionary of at most about 21,000 refetched bars per month.
- No per-row statement. Each month commits by itself, so a failed run keeps the months already done, and the status line per month is the progress log.
- Cost, at about $0.000018 a vCPU-second and $0.000002 a GiB-second (list prices, not re-read), 1 vCPU and 2Gi: a dry pass of one ticker is under one cent, and a committed execution that ran to the whole timeout would be about 8 cents. Nothing is scheduled.

## Close-out

None of these runs from the implementation PR, and none is a `done_when` box. Each waits for the owner's own yes and names its check. The record is kept as comments on the implementation PR.

1. **Deploy**: `./gcp/deploy.sh fetchers`, from a checkout of `main` at or after the merge. Check: the job's image is the build's digest.
2. **Dry run over the 423 months**, one execution per ticker, with the three lists of 2026-11-14 (`gs://adept-mountain-474619-d4-trading-data/intraday-lists/replace-dryrun-{SPY,QQQ,IWM}-20261114.csv`).
   - Pass: every month prints `dry_run`; no `incomplete_refetch`, `uncounted_over_bound` or RETRY line; each execution exits 0.
   - Compared with the numbers here: `label_dropped` sums to 24,517 for IWM, 29,030 for QQQ and 28,934 for SPY; `carry_in` and `tail` each sum to 94 over 23 months; IWM's `label_copies` by month are near 397, 555, 645, 1,076, 1,313 and 634.
   - The 423 UNCOUNTED lines and the three summaries are pasted on the PR. A month that does not print `dry_run` is recorded with its lines, and the owner decides about it before step 4.
3. **Retries off**: `gcloud run jobs update fetch-alphavantage-intraday --region us-east1 --max-retries=0`. Check: `gcloud run jobs describe` shows 0.
   - The 21:00 ET nightly runs on the same job and is not retried while this holds. The owner's yes covers that.
4. **The committed replace** is step 5 of the bucket-copy runbook, as written there, and does not start before #1190 allows it. Two additions:
   - Its timed first months are `IWM,2026-04`, then `SPY,2018-03` and `SPY,2018-02` in that order.
   - Checks, read-only: IWM 2026-04 holds no row at a UTC clock time from 04:00 up to 08:00, and its row count equals the run's `inserted`; the keys of 2018-02-28 after 21:00 Eastern are stored with an `inserted_at` of the February run, in March's window, and March's `deleted` does not include them.
5. **Retries back**: `--max-retries=1`, read back. A later `./gcp/deploy.sh fetchers` leaves the value alone: its update call does not pass the flag (`gcp/deploy.sh:2224-2229`).
6. The bucket-copy runbook's step 6 then runs as written. Its pass condition, `unproven_rows=0` on every MONTH line, covers the carry-ins: one that its own month did not rewrite shows there.

## Risks

- **A real bar is discounted as a label copy.** It needs five equal fields with the bar four or five hours later. `done_when` items 1 and 3 hold both sides: the 34 copies are discounted, and the real bars a short refetch lacks are not.
- **A label copy is missed** because the vendor revised a field. It then counts as held. Three of 4,620 measured rows differ in price, and the two sessions that differ by a row are far inside the tolerance of 16 or more.
- **The bound refuses a month that is fine.** IWM 2026-08 is estimated at 22.51%. Step 2 shows the real shares before any write.
- **A spared carry-in is stale.** It stays, unproven, and the scan lists it. Nothing reads it as proven.
- **The second swap fails after the first committed.** The month's late bars beyond the window are then as they were before the run, the status says so, and a second run writes them.
- **`spare_ts` changes a shared function.** It defaults to empty, and `done_when` item 6 runs the SQL on real Postgres.
- **The six months of Problem 2 with no vendor count.** If the vendor does not return their late rows, those rows stay as spared carry-ins and step 6 lists them.

## What was not verified

- The 2026-11-14 rewrite as reported, and QQQ's unproven count: not re-read.
- No vendor request was made. That the refetch lacks the keys of the label copies is read from counts (held minus fetched against copies, 60 sessions), not key by key.
- IWM sessions beyond the ten the dry run printed per month, and SPY and QQQ label copies under the five-field rule: not read.
- That the vendor returns the late rows of the six months named in Problem 2: not checked.
- Tickers other than SPY, QQQ and IWM: not read.
- The wall-clock of a committed replace: one month, as reported by the delivery session; no month that holds feature or level rows was timed.
- The new rules were run as a prototype on written-out shapes only; `replace_rows_in_window` with `spare_ts` was not run on Postgres.
- Which writer inserted the rows stamped 2026-05-26 among the late bars: not traced.
